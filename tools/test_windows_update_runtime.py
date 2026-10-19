"""Isolated frozen EXE update, rollback and notice acceptance on Windows."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from codex_bridge import atomic_json,publish_event
from windows_update import make_manifest

ROOT=Path(__file__).resolve().parents[1]

def read(path):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError): return {}

def until(predicate,timeout=45):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        value=predicate()
        if value: return value
        time.sleep(.1)
    raise AssertionError('Timed out waiting for isolated updater')

def main():
    candidate=Path(sys.argv[1]).resolve()
    old=Path(sys.argv[2]).resolve() if len(sys.argv)>2 else candidate
    from windows_pet import APP_VERSION
    version=APP_VERSION.removesuffix('-windows')
    old_version='0.5.1' if old != candidate else version
    root=ROOT/'qa/update-native'/('中文 空格 '+uuid.uuid4().hex)
    root.mkdir(parents=True)
    target=root/'安装目录'; shutil.copytree(old,target)
    state=root/'state'; state.mkdir()
    status=state/'codex-status.json'; heartbeat=state/'pig-heartbeat.json'
    make_manifest(target,old_version)
    (target/'user-settings.json').write_text('preserve user settings',encoding='utf-8')
    # Isolation is passed to restarted processes by the real helper.
    process=subprocess.Popen([str(target/'pig_pet.exe'),'--qa-window','--no-codex-observer','--status-file',str(status)],cwd=target)
    passed=[]; current_pid=process.pid
    def command(action,**values):
        atomic_json(state/'qa-command.json',dict(id=uuid.uuid4().hex,action=action,**values))
    def hmatch(**values):
        h=read(heartbeat)
        return h if all(h.get(k)==v for k,v in values.items()) else None
    try:
        until(lambda:hmatch(pid=process.pid,window_visible=True,version=old_version+'-windows'))
        assert not read(heartbeat)['update_checking']
        passed.append('Frozen isolated GUI starts without network checks')
        command('update-preview')
        h=until(lambda:hmatch(update_visible=True,update_phase='available'))
        c,w=h['content_screen_rect'],h['monitor_work']
        assert c[0]>=w[0] and c[1]>=w[1] and c[2]<=w[2] and c[3]<=w[3],(c,w)
        command('capture')
        until(lambda:list((state/'captures').glob('*.png')))
        passed.append('Native 150% DPI notice stays in monitor work area; captured PNG')
        publish_event(state,dict(session_id='permission-fixture',event='UserPromptSubmit',turn_id='t1',prompt_preview='Synthetic task'))
        until(lambda:read(heartbeat).get('selected_family')=='permission-fixture')
        request=state/'permission-requests/test.request.json'
        atomic_json(request,dict(request_id='test',session_id='permission-fixture',turn_id='t1',summary='合成权限优先级测试'))
        until(lambda:hmatch(update_visible=False,current_key='question'))
        package=root/'upgrade/package'; shutil.copytree(candidate,package); make_manifest(package,version)
        command('update-install',package=str(package),version=version)
        until(lambda:hmatch(update_phase='ready',update_visible=False))
        time.sleep(1)
        assert process.poll() is None and not (package.parent/'helper-ready.json').exists()
        passed.append('Permission bubble takes priority and defers restart')
        request.unlink()
        result_file=package.parent/'install-result.json'
        result=until(lambda:read(result_file),90)
        assert result.get('success'),result
        h=until(lambda:hmatch(version=APP_VERSION,window_visible=True) if read(heartbeat).get('pid')!=process.pid else None)
        current_pid=h['pid']
        assert process.wait(timeout=5)==0
        assert (Path(result['backup'])/'pig_pet.exe').exists()
        assert (target/'user-settings.json').read_text(encoding='utf-8')=='preserve user settings'
        passed.append('Copied helper waits for exact EXE, backs up, replaces, restarts and preserves extra settings')
        # Manifest is valid but this synthetic payload cannot execute: real
        # CreateProcess failure must restore the complete previous installation.
        broken=root/'rollback/package'; shutil.copytree(candidate,broken)
        (broken/'pig_pet.exe').write_bytes(b'not a Windows executable')
        make_manifest(broken,'0.5.4')
        command('update-install',package=str(broken),version='0.5.4')
        failed=until(lambda:read(broken.parent/'install-result.json'),90)
        assert failed.get('success') is False,failed
        old_pid=current_pid
        h=until(lambda:hmatch(version=APP_VERSION,window_visible=True) if read(heartbeat).get('pid')!=old_pid else None)
        current_pid=h['pid']
        assert (target/'user-settings.json').read_text(encoding='utf-8')=='preserve user settings'
        passed.append('Real restart failure restores previous EXE and relaunches it')
        command('exit')
        time.sleep(1)
        atomic_json(ROOT/'qa/windows-update-runtime.json',dict(passed=True,pass_items=passed,state_dir=str(state),root=str(root)))
        print(json.dumps(dict(passed=True,pass_items=passed,state_dir=str(state)),ensure_ascii=False,indent=2))
    finally:
        # Only this test's known HWND/PID; never touches the real user's pet.
        h=read(heartbeat)
        if h.get('pid') in (process.pid,current_pid) and h.get('hwnd'):
            ctypes.windll.user32.PostMessageW(ctypes.c_void_p(h['hwnd']),0x0010,0,0)
        if process.poll() is None:
            process.terminate(); process.wait(timeout=5)

if __name__=='__main__': main()
