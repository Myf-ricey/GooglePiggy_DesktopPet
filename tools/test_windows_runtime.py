"""Isolated native EXE/window and PS5.1 hook IPC integration acceptance.

No injected mouse input or Codex trust changes. Developer commands exercise
the same presentation methods used by mouse and menu handlers.
"""
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from codex_bridge import atomic_json,publish_event,actor_path
from windows_pet import APP_VERSION

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'qa/native-runtime'
TEST_EXE=Path(os.environ.get('GOOGLEPIGGY_TEST_EXE') or ROOT/'dist/GifPigDesktopPet/pig_pet.exe')
HOOK_PATH=TEST_EXE.parent/'hooks/codex-pig-hook.ps1' if '--exe' in sys.argv else ROOT/'hooks/codex-pig-hook.ps1'


def wait_for(test,timeout=8):
    end=time.monotonic()+timeout
    last={}
    while time.monotonic()<end:
        try:
            last=json.loads((STATE/'pig-heartbeat.json').read_text(encoding='utf-8'))
            if test(last): return last
        except (OSError,ValueError): pass
        time.sleep(.08)
    raise AssertionError('Runtime state timeout: '+json.dumps(last))


def command(action,**values):
    atomic_json(STATE/'qa-command.json',dict(id=uuid.uuid4().hex,action=action,**values))
    time.sleep(.08)


def event(actor,name,turn='t1',agent='',**values):
    publish_event(STATE,dict(session_id=actor,turn_id=turn,agent_id=agent,event=name,**values))


def hook(payload):
    env=dict(os.environ,GOOGLEPIGGY_STATE_DIR=str(STATE))
    return subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(HOOK_PATH)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)


def main():
    global STATE
    STATE.mkdir(parents=True,exist_ok=True)
    # A unique run ID avoids deleting any earlier evidence or stale live state.
    STATE=STATE/uuid.uuid4().hex
    STATE.mkdir()
    argv=[str(TEST_EXE)] if '--exe' in sys.argv else [sys.executable,str(ROOT/'pig_pet.py')]
    process=subprocess.Popen(argv+['--status-file',str(STATE/'codex-status.json'),'--no-codex-observer','--qa-window'],cwd=ROOT)
    passed=[]
    completed=False
    children=[]
    helpers=[]
    try:
        h=wait_for(lambda h:h.get('version')==APP_VERSION and h.get('window_visible'))
        assert h['selected_family']==''
        passed.append('Native cold start, fresh heartbeat, isolated empty state')
        env=dict(os.environ,GOOGLEPIGGY_STATE_DIR=str(STATE))
        for i in range(12):
            p=hook(dict(hook_event_name='UserPromptSubmit',session_id='actor-'+str(i),turn_id='t1',prompt='并发中文任务 '+str(i)))
            p.stdin.write(json.dumps(dict(hook_event_name='UserPromptSubmit',session_id='actor-'+str(i),turn_id='t1',prompt='并发中文任务 '+str(i)),ensure_ascii=False).encode())
            p.stdin.close()
            children.append(p)
        for p in children:
            assert p.wait(timeout=10)==0
            assert not p.stderr.read(),p.stderr.read()
        assert len(list((STATE/'actors').glob('*.json')))==12
        passed.append('12 concurrent PS5.1 hooks preserve all actor files and UTF-8')
        h=wait_for(lambda h:len(h.get('families',[]))==12 and h['current_key']=='reading')
        command('select',actor='actor-0')
        wait_for(lambda h:h['selected_family']=='actor-0' and h['frame_index']>=63)
        command('select',actor='actor-1')
        time.sleep(1)
        command('select',actor='actor-0')
        wait_for(lambda h:h['selected_family']=='actor-0' and h['frame_index']>=63)
        passed.append('Switching actors does not replay reading intro')
        for i in range(4): event('actor-0','SubagentStart',agent='child-'+str(i),status='working')
        wait_for(lambda h:len(h['families'])==16)
        command('capture')
        command('edge',edge='right')
        h=wait_for(lambda h:h['presentation']=='hidden' and h['tail_visible'])
        event('actor-0','PostToolUse',status='working')
        time.sleep(1.3)
        h=wait_for(lambda h:h['presentation']=='hidden')
        assert len(h['hidden_work_tokens'])==16
        passed.append('Active family + 4 children hides; same-turn tool receipt stays hidden')
        event('actor-0','UserPromptSubmit','t2',status='thinking')
        wait_for(lambda h:h['presentation']=='visible' and not h['tail_visible'])
        passed.append('New turn reveals whole family automatically')
        for edge in ('left','top','bottom'):
            command('edge',edge=edge)
            wait_for(lambda h:h['presentation']=='hidden' and h['hidden_edge']==edge)
            command('reveal')
            h=wait_for(lambda h:h['presentation']=='visible')
            rect,work=h['content_screen_rect'],h['monitor_work']
            assert rect[0]>=work[0] and rect[1]>=work[1] and rect[2]<=work[2] and rect[3]<=work[3],(rect,work)
        passed.append('All four physical edges hide/reveal a family on the native window')
        for i in range(1,12): event('actor-'+str(i),'SessionEnd',status='idle')
        event('actor-0','Interrupt','t2',status='interrupted')
        wait_for(lambda h:h['current_key']=='question')
        event('actor-0','PostToolUse','t2',status='working')
        time.sleep(1.1)
        assert wait_for(lambda h:h['current_key']=='question')['current_key']=='question'
        passed.append('Native interrupt remains question after late tool result')
        event('actor-0','UserPromptSubmit','t3',status='thinking')
        event('actor-0','PreCompact','t3',status='compacting')
        wait_for(lambda h:h['current_key'].startswith('packing_'))
        event('actor-0','PostToolUse','t3',status='working')
        wait_for(lambda h:h['current_key'].startswith('packing_'))
        command('capture')
        passed.append('Native compaction resists late tool receipt')
        # Two outstanding permission helpers for distinct actors. Both keep
        # waiting, then return only their own synthetic request_id's answer.
        for i in range(2):
            p=hook({})
            payload=dict(hook_event_name='PermissionRequest',session_id='permission-'+str(i),turn_id='p1',tool_name='exec_command',tool_input={'cmd':'echo synthetic-'+str(i),'justification':'这是第 '+str(i)+' 个隔离协议测试。'})
            p.stdin.write(json.dumps(payload,ensure_ascii=False).encode()); p.stdin.close()
            helpers.append(p)
        deadline=time.monotonic()+8
        requests=[]
        while time.monotonic()<deadline:
            requests=list((STATE/'permission-requests').glob('*.request.json'))
            if len(requests)==2: break
            time.sleep(.1)
        assert len(requests)==2
        time.sleep(.5)
        assert all(p.poll() is None for p in helpers)
        for file in requests:
            p=json.loads(file.read_text(encoding='utf-8'))
            decision='allow' if p['session_id'].endswith('0') else 'deny'
            atomic_json(file.with_name(p['request_id']+'.response.json'),dict(request_id=p['request_id'],decision=decision,message='合成请求拒绝'))
        for p in helpers:
            assert p.wait(timeout=8)==0
            output=json.loads(p.stdout.read().decode('utf-8'))
            assert output['hookSpecificOutput']['decision']['behavior'] in {'allow','deny'}
        assert not list((STATE/'permission-requests').glob('*.request.json'))
        passed.append('Concurrent permission IPC returns matched allow/deny and removes request files')
        same=[]
        for i in range(2):
            p=hook({})
            payload=dict(hook_event_name='PermissionRequest',session_id='same-actor',turn_id='p1',tool_name='exec_command',tool_input={'cmd':'echo same-'+str(i),'justification':'同一 actor 的请求 '+str(i)})
            p.stdin.write(json.dumps(payload,ensure_ascii=False).encode()); p.stdin.close()
            same.append(p); helpers.append(p)
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            requests=list((STATE/'permission-requests').glob('*.request.json'))
            if len(requests)==2: break
            time.sleep(.1)
        assert len(requests)==2
        time.sleep(.5)
        assert all(p.poll() is None for p in same)
        for file in requests:
            p=json.loads(file.read_text(encoding='utf-8'))
            decision='allow' if p['summary'].endswith('0') else 'deny'
            atomic_json(file.with_name(p['request_id']+'.response.json'),dict(request_id=p['request_id'],decision=decision,message='合成拒绝'))
        for i,p in enumerate(same):
            assert p.wait(timeout=8)==0
            output=json.loads(p.stdout.read().decode('utf-8'))
            assert output['hookSpecificOutput']['decision']['behavior']==('allow' if i==0 else 'deny')
        passed.append('Two simultaneous requests from the same actor keep independent request IDs')
        # End all work without touching real Codex sessions.
        h=wait_for(lambda h:len(h['families'])==19)
        for node in h['families']:
            event(node['parent'] or node['id'],'SessionEnd',node['turn'],node['id'] if node['parent'] else '',status='idle')
        wait_for(lambda h:h['selected_family']=='')
        command('rest')
        wait_for(lambda h:h['leisure_phase']=='sleeping',timeout=10)
        command('sleep-click',wake=False)
        wait_for(lambda h:h['leisure_phase']=='sleeping')
        command('capture')
        command('sleep-click',wake=True)
        wait_for(lambda h:h['leisure_phase']=='awake')
        passed.append('Native rest sequence, independent sleeping tail and two-loop wake')
        command('exit')
        assert process.wait(timeout=5)==0
        passed.append('Native GUI exits without orphan process')
        completed=True
    finally:
        if process.poll() is None: process.terminate(); process.wait(timeout=5)
        for p in children+helpers:
            if p.poll() is None: p.terminate()
        report={'platform':'Windows','executable':argv[0],'state_dir':str(STATE),'passed':completed,'expected_checks':12,'pass_items':passed}
        atomic_json(ROOT/'qa/windows-runtime-report.json',report)
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
