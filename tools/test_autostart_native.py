"""Exercise the shipped broker through Windows, using disposable registry names."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from windows_autostart import request


def powershell(code):
    prefix="[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); $ErrorActionPreference='Stop'; $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value; "
    p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode((prefix+code).encode('utf-16-le')).decode()],capture_output=True,check=True,timeout=20)
    return json.loads(p.stdout.decode('utf-8-sig')) if p.stdout else None


def main():
    token=uuid.uuid4().hex
    key='Software\\GooglePiggy\\AutostartDiagnostics\\'+token
    name='GooglePiggy-QA-'+token
    keys=dict(run_key=key+'\\Run',preference_key=key+'\\Preferences',approved_key=key+'\\Approved',value_name=name)
    command='"'+sys.executable+'" -c "pass"'
    passed=[]
    def call(action,**overrides):
        return request(action,command,sys.executable,**dict(keys,**overrides))
    def mutate(method,sub,field='',value=''):
        extra=(';'+field+'='+value) if field else ''
        return powershell("Invoke-CimMethod -Namespace root/default -ClassName StdRegProv -MethodName "+method+" -Arguments @{hDefKey=[uint32]2147483651;sSubKeyName=($sid+'\\"+sub+"');sValueName='"+name+"'"+extra+"} | Select-Object ReturnValue | ConvertTo-Json")
    try:
        state=call('reconcile',previous_install=False)
        assert state['enabled'] and state['preference']==1
        passed.append('Fresh install creates a system-visible startup entry and reads it back')
        assert mutate('DeleteValue',keys['run_key'])['ReturnValue']==0
        assert not call('inspect')['enabled']
        assert call('reconcile',previous_install=True)['enabled']
        passed.append('Saved enabled preference repairs a missing system Run entry')
        assert mutate('SetStringValue',keys['run_key'],'sValue',"'C:\\missing\\pig_pet.exe'")['ReturnValue']==0
        assert not call('inspect')['enabled']
        assert call('reconcile',previous_install=True)['command']==command
        passed.append('Stale/moved executable is reported disabled and repaired to current path')
        call('disable')
        assert not call('reconcile',previous_install=False)['registered']
        passed.append('Explicit user opt-out survives a subsequent startup/installation')
        call('enable')
        powershell("Invoke-CimMethod -Namespace root/default -ClassName StdRegProv -MethodName CreateKey -Arguments @{hDefKey=[uint32]2147483651;sSubKeyName=($sid+'\\"+keys['approved_key']+"')} | Out-Null")
        assert mutate('SetBinaryValue',keys['approved_key'],'uValue','([byte[]](3,0,0,0,0,0,0,0,0,0,0,0))')['ReturnValue']==0
        assert not call('reconcile')['enabled']
        assert call('inspect')['system_disabled']
        assert call('enable')['enabled']
        passed.append('Windows Startup Apps disabling is preserved until explicit user enable')
        try:
            request('enable','"C:\\missing\\pig_pet.exe"','C:\\missing\\pig_pet.exe',**keys)
            raise AssertionError('Missing executable was accepted')
        except OSError:pass
        assert call('inspect')['command']==command
        passed.append('Missing executable is rejected without replacing the previous registration')
        real_run='Software\\Microsoft\\Windows\\CurrentVersion\\Run'
        call('enable',run_key=real_run)
        rows=powershell("@(Get-CimInstance Win32_StartupCommand | Where-Object {$_.Name -eq '"+name+"'} | Select-Object Name,Command) | ConvertTo-Json -Compress")
        if isinstance(rows,dict):rows=[rows]
        assert rows and len(rows)==1 and rows[0]['Command']==command
        call('disable',run_key=real_run)
        assert not call('inspect',run_key=real_run)['registered']
        passed.append('Independent Win32_StartupCommand sees enable and removal; no admin elevation')
        report={'passed':True,'checks':passed,'test_value':name}
        out=Path(__file__).resolve().parents[1]/'qa/autostart-20261025/native-broker.json'
        out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
    finally:
        call('disable',run_key='Software\\Microsoft\\Windows\\CurrentVersion\\Run')
        for suffix in ('Run','Preferences','Approved',''):
            sub=key+('\\'+suffix if suffix else '')
            assert sub.startswith('Software\\GooglePiggy\\AutostartDiagnostics\\'+token)
            powershell("Invoke-CimMethod -Namespace root/default -ClassName StdRegProv -MethodName DeleteKey -Arguments @{hDefKey=[uint32]2147483651;sSubKeyName=($sid+'\\"+sub+"')} | Out-Null")


if __name__=='__main__':main()
