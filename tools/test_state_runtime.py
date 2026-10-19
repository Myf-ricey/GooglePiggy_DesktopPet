"""Exercise the frozen observer against an isolated Codex database and logs."""
import ctypes
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import uuid
import zstandard
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from codex_bridge import atomic_json,publish_event
from windows_pet import APP_BUILD

ROOT=Path(__file__).resolve().parents[1]

def main():
    exe=Path(sys.argv[1]).resolve()
    root=ROOT/'qa/state-runtime'/uuid.uuid4().hex
    home=root/'codex';state=root/'state'
    home.mkdir(parents=True);state.mkdir()
    log=home/'child.jsonl';log.touch()
    row=dict(timestamp='1970-01-01T00:02:10Z',type='event_msg',payload=dict(type='task_complete',turn_id='child-turn'))
    data=(json.dumps(row)+'\n'+json.dumps(dict(type='response_item',payload={'output':'x'*(17*1024*1024)}))+'\n').encode()
    Path(str(log)+'.zst').write_bytes(zstandard.ZstdCompressor().compress(data))
    with sqlite3.connect(home/'state_1.sqlite') as db:
        db.execute('create table threads(id text,title text,source text,rollout_path text,updated_at integer)')
        db.executemany('insert into threads values (?,?,?,?,?)',[(f'recent-{i}','','{}','',1000+i) for i in range(256)])
        db.execute('insert into threads values (?,?,?,?,?)',('child','Synthetic child',json.dumps({'subagent':{'thread_spawn':{'parent_thread_id':'root'}}}),str(log),1))
        db.execute('insert into threads values (?,?,?,?,?)',('root','Synthetic root','{}','',1))
    db.close()
    publish_event(state,dict(session_id='root',agent_id='child',event='PostToolUse',turn_id='child-turn',received_at=110))
    publish_event(state,dict(session_id='root',event='Stop',turn_id='parent-turn',received_at=140))
    env=dict(os.environ,CODEX_HOME=str(home))
    env['PATH']=';'.join(p for p in env.get('PATH','').split(';') if 'python' not in p.lower() and 'windowsapps' not in p.lower())
    status=state/'codex-status.json';heartbeat=state/'pig-heartbeat.json'
    def read():
        try:return json.loads(heartbeat.read_text(encoding='utf-8'))
        except (OSError,ValueError):return {}
    def wait(test,timeout=25):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            h=read()
            if test(h):return h
            time.sleep(.1)
        raise AssertionError('Frozen observer timeout: '+json.dumps(read()))
    def start():
        return subprocess.Popen([str(exe),'--status-file',str(status),'--qa-window'],cwd=exe.parent,env=env)
    def close(process):
        h=read()
        if h.get('pid')==process.pid and h.get('hwnd'):
            ctypes.windll.user32.PostMessageW(ctypes.c_void_p(h['hwnd']),0x0010,0,0)
        process.wait(timeout=10)
    def node(h,actor):return next((n for n in h.get('families',[]) if n['id']==actor),{})
    process=start();passed=[]
    try:
        h=wait(lambda h:h.get('pid')==process.pid and h.get('build')==APP_BUILD and node(h,'child').get('status')=='success')
        assert h['selected_family']==''
        passed.append('Frozen observer resolves actor beyond 256 and compressed completion beside empty plaintext')
        passed.append('17 MiB compressed fixture decodes with bundled dependency and no Python PATH')
        publish_event(state,dict(session_id='root',event='UserPromptSubmit',turn_id='new'))
        wait(lambda h:node(h,'root').get('status')=='thinking')
        passed.append('Fresh real-turn start remains active')
        safety=dict(session_id='safety',event='UserPromptSubmit',turn_id='s',source='codex-hook',cwd='/',prompt_preview='You are an expert at upholding safety and compliance standards for Codex ambient suggestions.\n\ncheck')
        publish_event(state,dict(session_id='safety',event='SessionStart'))
        publish_event(state,safety)
        publish_event(state,dict(session_id='safety',event='Stop',turn_id='s'))
        publish_event(state,dict(safety,session_id='normal-safety-quote',cwd='C:/project'))
        wait(lambda h:node(h,'normal-safety-quote').get('status')=='thinking')
        assert not node(read(),'safety')
        publish_event(state,dict(session_id='normal-safety-quote',event='SessionEnd',turn_id='s'))
        passed.append('Frozen observer filters safety check but retains same text in a project')
        for event in ('PreCompact','PostCompact'):
            publish_event(state,dict(session_id='root',event=event,turn_id='new'))
            wait(lambda h:node(h,'root').get('status')==('compacting' if event=='PreCompact' else 'success'))
        publish_event(state,dict(session_id='root',event='PostToolUse',turn_id='new'))
        time.sleep(1.2);assert node(read(),'root')['status']=='success'
        publish_event(state,dict(session_id='root',event='PreToolUse',turn_id='new'))
        wait(lambda h:node(h,'root').get('status')=='working')
        passed.append('Only a fresh tool start resumes after compaction; delayed result cannot')
        close(process);process=start()
        wait(lambda h:h.get('pid')==process.pid and node(h,'root').get('status')=='working' and node(h,'child').get('status')=='success')
        assert not node(read(),'safety')
        passed.append('Restart replay preserves live root without resurrecting finished child')
        publish_event(state,dict(session_id='root',event='Stop',turn_id='new'))
        wait(lambda h:node(h,'root').get('status')=='success' and h.get('selected_family')=='')
        passed.append('Explicit final completion clears active family')
        close(process)
        atomic_json(ROOT/'qa/state-runtime-report.json',dict(passed=True,pass_items=passed))
        print(json.dumps(dict(passed=True,checks=len(passed)),indent=2))
    finally:
        if process.poll() is None:process.terminate();process.wait(timeout=5)

if __name__=='__main__':main()
