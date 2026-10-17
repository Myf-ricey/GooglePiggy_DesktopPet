"""Deterministic Windows-port domain, transport, rendering and hook checks."""
import hashlib
import json
import random
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from animation_clock import AnimationClock,load_manifest
from family_store import FamilyStore
from leisure import Leisure
from codex_bridge import publish_event,actor_path,atomic_json
from codex_observer import CodexObserver,latest_lifecycle,unread_ids
from windows_pet import WindowsPet,family_tail_rects
import pig_pet as win

ROOT = Path(__file__).resolve().parents[1]
CLIPS = load_manifest(ROOT/'assets/macos-resources')


class PortTests(unittest.TestCase):
    def test_unconfirmed_stale_prompt_does_not_leave_ghost_task(self):
        # Real incident: UserPromptSubmit exists, but the actor has no SQLite
        # row, rollout path, tool activity or completion event.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            now=1700001000
            publish_event(root,dict(session_id='missing-thread',turn_id='t1',event='UserPromptSubmit',status='thinking',received_at=now-120))
            store=FamilyStore()
            observer=CodexObserver(store,root,home=root)
            observer.poll(now)
            self.assertEqual(store.roots(now),[])
            self.assertEqual(store.work_tokens(),set())
            self.assertEqual(store.selected,'')
            self.assertFalse(store.nodes['missing-thread'].unread)
            self.assertIsNone(store.nodes['missing-thread'].completion)
            publish_event(root,dict(session_id='missing-thread',turn_id='t1',event='PostToolUse',status='working',received_at=now+1))
            observer.poll(now+1)
            self.assertEqual(store.roots(now+1),[])
            publish_event(root,dict(session_id='missing-thread',turn_id='t2',event='UserPromptSubmit',status='thinking',received_at=now+2))
            observer.poll(now+2)
            self.assertTrue(store.nodes['missing-thread'].active)

    def test_fresh_or_confirmed_work_does_not_expire(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            now=1700001000
            publish_event(root,dict(session_id='fresh',turn_id='t1',event='UserPromptSubmit',status='thinking',received_at=now-5))
            publish_event(root,dict(session_id='tool-active',turn_id='t1',event='PreToolUse',status='working',received_at=now-120))
            store=FamilyStore()
            observer=CodexObserver(store,root,home=root)
            observer.poll(now)
            self.assertTrue(store.nodes['fresh'].active)
            self.assertTrue(store.nodes['tool-active'].active)

    def event(self,store,actor,event,turn='t1',now=1,agent='',**extra):
        p = dict(session_id=actor,event=event,turn_id=turn,agent_id=agent,token=f'{actor}-{event}-{now}-{agent}',**extra)
        result = store.ingest(p,now)
        store.reconcile(now)
        return result

    def test_family_isolation_and_selection(self):
        s = FamilyStore()
        self.event(s,'A','UserPromptSubmit')
        self.event(s,'B','UserPromptSubmit',now=2)
        self.event(s,'B','PreToolUse',now=3)
        self.assertEqual(s.nodes['A'].status,'thinking')
        self.assertEqual(s.selected,'B')
        s.select('A')
        self.event(s,'B','PostToolUse',now=4)
        self.assertEqual(s.selected,'A')
        self.event(s,'A','SubagentStart',agent='C',now=5)
        self.event(s,'A','SubagentStop',agent='C',now=6)
        self.assertTrue(s.nodes['A'].active)
        self.assertEqual(len(s.children('A',7)),1)
        self.assertEqual(len(s.children('A',10)),0)

    def test_retired_turn_and_duplicate(self):
        s = FamilyStore()
        self.event(s,'A','UserPromptSubmit')
        self.event(s,'A','UserPromptSubmit','t2',2)
        self.assertFalse(self.event(s,'A','Stop','t1',3))
        p = dict(session_id='A',event='PreToolUse',turn_id='t2',token='same')
        self.assertTrue(s.ingest(p,4))
        self.assertFalse(s.ingest(p,5))
        self.assertEqual(s.nodes['A'].turn,'t2')

    def test_pause_compact_resume(self):
        s = FamilyStore()
        self.event(s,'A','UserPromptSubmit')
        self.event(s,'A','SubagentStart',agent='C',now=2)
        self.event(s,'A','Interrupt',now=3)
        for e in ('PostToolUse','Stop','PostCompact','TaskCompleteFallback'):
            self.assertFalse(self.event(s,'A',e,now=4))
        self.assertTrue(s.paused(s.nodes['C']))
        self.assertEqual(s.work_tokens(),set())
        self.event(s,'A','ResumeDetected','t2',5,status='working')
        self.assertFalse(s.paused(s.nodes['C']))
        self.event(s,'A','PreCompact','t3',6)
        self.assertFalse(self.event(s,'A','PostToolUse','t3',7))
        self.event(s,'A','PostCompact','t3',8)
        self.assertEqual(s.nodes['A'].status,'success')
        self.assertFalse(self.event(s,'A','PostCompact','t3',9))

    def test_completion_and_unread_unknown(self):
        s = FamilyStore()
        self.event(s,'A','UserPromptSubmit')
        self.event(s,'B','UserPromptSubmit',now=2)
        self.event(s,'B','Stop',now=3)
        self.assertEqual(s.selected,'A')
        self.assertTrue(s.nodes['B'].unread)
        self.assertIsNone(unread_ids({}))
        value = {'electron-thread-read-state-v1':{'version':1,'unreadByIdentity':{'one':{'local:here':['A']}}}}
        self.assertEqual(unread_ids(value),{'A'})
        value['electron-thread-read-state-v1']['unreadByIdentity']['two'] = {}
        self.assertIsNone(unread_ids(value))
        self.event(s,'A','Stop',now=4)
        s.reconcile(8)
        self.assertEqual(s.selected,'')

    def test_reading_resume_and_hold(self):
        c = AnimationClock(CLIPS,random.Random(1))
        c.update('A','t1','reading',0)
        c.update('B','t1','reading',3)
        self.assertGreaterEqual(c.position('A',5)[1],63)
        self.assertLess(c.position('B',3.5)[1],63)
        c.update('A','t1','carrot',5)
        c.update('A','t1','reading',10)
        self.assertEqual(c.position('A',10),('reading',CLIPS['reading'].frame(5)))
        c.update('A','t2','reading',11)
        self.assertEqual(c.position('A',11),('reading',0))
        c.update('A','t2','question',12)
        self.assertEqual(c.position('A',100),('question',24))
        c.update('B','t2','jump',12)
        self.assertIsNone(c.position('B',20))

    def test_packing_complete_segments(self):
        c = AnimationClock(CLIPS,random.Random(7))
        c.update('A','t1','packing',0)
        first = c.position('A',0)[0]
        duration = CLIPS[first].total_duration/1000
        self.assertEqual(c.position('A',duration-.01)[0],first)
        c.position('A',duration+.01)
        self.assertEqual(len(c.tracks['A'].packing),2)
        before = list(c.tracks['A'].packing)
        c.update('A','t1','packing',duration+.01)
        self.assertEqual(c.tracks['A'].packing,before)

    def test_manifest_timing_and_rgba(self):
        expected = {'reading':(301,8040,63),'left':(30,600,0),'snack':(259,12600,0),'sleep_entry':(139,6440,0)}
        for key,values in expected.items():
            c = CLIPS[key]
            self.assertEqual((len(c.frames),c.total_duration,c.loop_start),values)
        for key,c in CLIPS.items():
            for spec in c.frames.specs:
                self.assertTrue((c.frames.root/spec['file']).exists())
            self.assertEqual(c.frames[0].size,(640,640))
            self.assertEqual(c.frames[0].mode,'RGBA')

    def test_sleep_distribution_and_snack_branches(self):
        l = Leisure(0,random.Random(42))
        samples = [l.interval()/60 for _ in range(100000)]
        self.assertTrue(all(3<=t<=30 for t in samples))
        self.assertAlmostEqual(sum(samples)/len(samples),10,delta=.15)
        self.assertAlmostEqual(sum(8<=t<=12 for t in samples)/len(samples),.5,delta=.015)
        for choice,expected in [(.2,[200]),(.5,[100]),(.85,[100,200]),(.95,[])]:
            l.reset(0,300,choice)
            self.assertEqual(l.snacks,expected)

    def test_deadline_drag_busy_and_tail(self):
        l = Leisure(0,random.Random(8))
        l.reset(0,300,.85)
        l.tick(100,False)
        self.assertEqual(l.snacks,[200])
        l.tick(301,False)
        self.assertEqual(l.phase,'awake')
        self.assertEqual(l.deadline,300)
        l.tick(302,True)
        self.assertEqual(l.phase,'entering')
        l.cancel()
        self.assertEqual(l.deadline,300)
        l.tick(303,True)
        l.position(CLIPS,310)
        self.assertEqual(l.phase,'sleeping')
        epoch = l.sleep_epoch
        l.click(311,False)
        tail = l.tail_epoch
        l.click(311.5,False)
        self.assertEqual(l.tail_epoch,tail)
        self.assertEqual(l.sleep_epoch,epoch)
        l.click(312,True)
        self.assertEqual(l.position(CLIPS,313.19)[0],'left')
        self.assertIsNone(l.position(CLIPS,313.21))
        self.assertEqual(l.phase,'awake')

    def test_concurrent_events_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def write(i):
                publish_event(root,dict(session_id='A' if i%2 else 'B',turn_id='t1',event='PostToolUse',status='working'))
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(write,range(100)))
            files = list((root/'family-events').glob('*.json'))
            self.assertEqual(len(files),100)
            self.assertEqual({json.loads(p.read_text())['session_id'] for p in files},{'A','B'})
            self.assertTrue(actor_path(root,'A').exists())
            self.assertFalse((root/'codex-status.json').exists())

    def test_utf8_lifecycle_and_observer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            log=root/'session.jsonl'
            record={'type':'event_msg','timestamp':'2026-10-09T16:00:00Z','payload':{'type':'task_started','turn_id':'t2'}}
            log.write_bytes(('中'*100000+'\n'+json.dumps(record)+'\n').encode())
            self.assertEqual(latest_lifecycle(log)[:2],('task_started','t2'))
            s=FamilyStore()
            publish_event(root,dict(session_id='A',turn_id='t1',event='UserPromptSubmit',status='thinking'))
            observer=CodexObserver(s,root,enabled=False)
            observer.poll()
            self.assertEqual(s.selected,'A')
            observer.poll()
            self.assertEqual(len(s.seen),1)

    def test_suggested_reply_sessions_do_not_become_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=FamilyStore()
            observer=CodexObserver(store,tmp,enabled=False)
            marker='This is an app-generated request for a suggested next user message. The user did not write this mess'
            for actor in ('suggestion-1','suggestion-2','suggestion-3'):
                for i,event in enumerate(('SessionStart','UserPromptSubmit','Stop','SessionEnd')):
                    observer.ingest(dict(session_id=actor,event=event,turn_id='t1',received_at=100+i,
                        prompt_preview=marker if event=='UserPromptSubmit' else ''))
                    self.assertEqual(store.roots(100+i),[])
                    self.assertEqual(store.work_tokens(),set())
            observer.metadata['real']={'thread_title':'Real conversation'}
            observer.ingest(dict(session_id='real',event='UserPromptSubmit',turn_id='t1',received_at=110,prompt_preview=marker))
            observer.ingest(dict(session_id='real',agent_id='child',event='SubagentStart',turn_id='c1',received_at=111))
            self.assertEqual([n.id for n in store.roots(112)],['real'])
            self.assertEqual([n.id for n in store.children('real',112)],['child'])

    def test_ambient_suggestions_do_not_become_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = '# Overview\n\nGenerate 0 to 3 hyperpersonalized suggestions for what this user can do with Codex in th'
            store = FamilyStore()
            observer = CodexObserver(store, tmp, enabled=False)
            for i, event in enumerate(('SessionStart', 'UserPromptSubmit', 'PostToolUse', 'Stop', 'SessionEnd', 'TaskCompleteFallback')):
                observer.ingest(dict(session_id='ambient', event=event, received_at=100+i,
                    prompt_preview=marker if event == 'UserPromptSubmit' else ''))
            self.assertNotIn('ambient', store.nodes)
            observer.metadata['real'] = {'thread_title': 'User task'}
            observer.ingest(dict(session_id='real', event='UserPromptSubmit', received_at=110, prompt_preview=marker))
            self.assertTrue(store.nodes['real'].active)
            observer.ingest(dict(session_id='quoted', event='UserPromptSubmit', received_at=111, prompt_preview='Explain: ' + marker))
            self.assertTrue(store.nodes['quoted'].active)

    def test_metadata_preserves_explicit_parent(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with sqlite3.connect(root/'state_5.sqlite') as db:
                db.execute('CREATE TABLE threads(id TEXT, title TEXT, source TEXT, rollout_path TEXT)')
                db.execute("INSERT INTO threads VALUES('C','child','','')")
            db.close()
            s=FamilyStore()
            self.event(s,'A','SubagentStart',agent='C')
            observer=CodexObserver(s,root,home=root)
            observer.refresh_metadata(time.time())
            self.assertEqual(s.nodes['C'].parent,'A')

    def test_installer_preserves_other_hooks_and_registers_twelve(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            fake=home/'codex-pig-hook.ps1'
            fake.write_text("Write-Output '{}'",encoding='utf-8')
            original={'hooks':{'Stop':[{'hooks':[{'type':'command','command':f'powershell.exe -File "{fake}"','timeout':3}]}]}}
            atomic_json(home/'hooks.json',original)
            import os
            env=dict(os.environ,CODEX_HOME=str(home))
            result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'install.ps1'),'-NoAutostart','-NoDesktopShortcut','-NoStart','-NoEnableHookFeature'],env=env,capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            config=json.loads((home/'hooks.json').read_text(encoding='utf-8'))['hooks']
            self.assertEqual(len(config),12)
            self.assertEqual(len(config['Stop']),2)
            self.assertIn(str(fake),config['Stop'][1]['hooks'][0]['command'])
            self.assertEqual(config['PermissionRequest'][0]['hooks'][0]['timeout'],600)

    def test_four_edges_all_family_sizes(self):
        screen=(0,0,1920,1080)
        bodies={'left':(-5,450,170,600),'right':(1750,450,1925,600),'top':(850,-5,1020,145),'bottom':(850,935,1020,1085)}
        for edge,body in bodies.items():
            main=win.tail_window_rect(edge,body,screen)
            for count in range(4):
                rects=family_tail_rects(edge,main,screen,count)
                self.assertEqual(len(rects),count+1)
                axis=1 if edge in ('left','right') else 0
                for a,b in zip(rects,rects[1:]):
                    self.assertGreaterEqual(b[axis]-a[axis+2],4)
                for r in rects:
                    self.assertGreaterEqual(r[axis],screen[axis])
                    self.assertLessEqual(r[axis+2],screen[axis+2])

    def test_render_parity_cold_selector_and_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            pet=WindowsPet(CLIPS,ROOT/'qa/report.json',ROOT,Path(tmp)/'codex-status.json',False)
            image=pet.compose('reading',100)
            self.assertEqual(image.tobytes(),CLIPS['reading'].frames[100].tobytes())
            pet.selector_visible=True
            pet.compose('idle',0).save(ROOT/'qa/windows-cold-empty.png')
            self.assertIsNotNone(pet.selector_rect)
            self.assertEqual(pet.selector_rows,[])
            pet.selector_visible=False
            pet.permission_request_id='synthetic'
            pet.permission_request={'request_id':'synthetic','summary':'允许 GooglePiggy 写入本次测试报告吗？'}
            pet.compose('question',24).save(ROOT/'qa/windows-permission-short.png')
            self.assertIn('allow',pet.permission_buttons)
            pet.permission_request['summary']='这是一段需要完整阅读的长权限说明。'*50
            pet.compose('question',24).save(ROOT/'qa/windows-permission-long.png')
            self.assertEqual(set(pet.permission_buttons),{'allow','deny'})

    def test_child_permission_forces_question_and_matched_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            pet=WindowsPet(CLIPS,ROOT/'qa/report.json',ROOT,root/'codex-status.json',False)
            now=time.time()
            self.event(pet.store,'A','UserPromptSubmit',now=now)
            self.event(pet.store,'A','SubagentStart',agent='C',now=now+.001)
            self.event(pet.store,'A','PermissionRequest',agent='C',now=now+.002,permission_request_id='child-permission')
            atomic_json(root/'permission-requests/child-permission.request.json',dict(request_id='child-permission',session_id='A',agent_id='C',turn_id='t1',summary='子代理请求权限'))
            pet._poll_bridge(force=True)
            pet._resolve_visual()
            self.assertEqual(pet.current_key,'question')
            pet.compose()
            pet._write_permission_decision('deny')
            response=json.loads((root/'permission-requests/child-permission.response.json').read_text(encoding='utf-8'))
            self.assertEqual(response['request_id'],'child-permission')
            self.assertEqual(response['decision'],'deny')


if __name__=='__main__':
    (ROOT/'qa').mkdir(exist_ok=True)
    runner=unittest.TextTestRunner(verbosity=2)
    result=runner.run(unittest.defaultTestLoader.loadTestsFromTestCase(PortTests))
    atomic_json(ROOT/'qa/windows-port-tests.json',{'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':[str(t) for t,_ in result.failures+result.errors]})
    sys.exit(0 if result.wasSuccessful() else 1)
