"""System-verified current-user startup registration; no elevation or tasks."""
import json
import os
from pathlib import Path
import subprocess


def request(action, command, target, *, previous_install=False, legacy_preference=None, **testing_keys):
    script=Path(__file__).resolve().parent/'tools/autostart_registry.ps1'
    shell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    payload=dict(action=action,command=command,target=str(target),previous_install=previous_install,legacy_preference=legacy_preference,**testing_keys)
    try:
        result=subprocess.run([str(shell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script)],
            input=json.dumps(payload,ensure_ascii=False).encode('utf-8'),capture_output=True,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=20)
    except (OSError,subprocess.TimeoutExpired) as error:
        raise OSError('无法核实 Windows 自启动登记，请稍后重试。') from error
    if result.returncode:
        detail=result.stderr.decode('utf-8-sig',errors='replace').strip()
        raise OSError('Windows 自启动操作未确认成功：'+detail[:500])
    try:
        state=json.loads(result.stdout.decode('utf-8-sig'))
        if not isinstance(state.get('enabled'),bool) or not isinstance(state.get('registered'),bool):raise ValueError('invalid status')
        return state
    except (ValueError,AttributeError) as error:
        raise OSError('Windows 自启动校验没有返回有效状态。') from error
