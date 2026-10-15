#!/usr/bin/env python3
"""Real Sparkle installation into disposable app bundles; never touches the installed pig."""
import functools, http.server, json, os, plistlib, shutil, subprocess, threading, time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'output/update-install'
if out.exists(): shutil.rmtree(out)
out.mkdir(parents=True)
private_key=out/'fixture-private-key'
public_key=subprocess.check_output(['swift',str(root/'tests/update-install/key.swift'),str(private_key)],text=True).strip()
sparkle=root/'cache/sparkle-2.10.0'
exe=out/'fixture'
subprocess.run(['swiftc','-D','UPDATE_TESTING','-swift-version','5','-F',str(sparkle),'-framework','Sparkle','-framework','AppKit','-Xlinker','-rpath','-Xlinker','@executable_path/../Frameworks',str(root/'macos/Sources/GooglePiggy/UpdateNotice.swift'),str(root/'macos/Sources/GooglePiggy/UpdateInstaller.swift'),str(root/'tests/update-install/main.swift'),'-o',str(exe)],check=True)
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args): pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(out)))
threading.Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}/'

def bundle(path,version,build,feed):
    (path/'Contents/MacOS').mkdir(parents=True)
    shutil.copy2(exe,path/'Contents/MacOS/GooglePiggy')
    subprocess.run(['ditto',str(sparkle/'Sparkle.framework'),str(path/'Contents/Frameworks/Sparkle.framework')],check=True)
    info=plistlib.loads((root/'macos/Info.plist').read_bytes())
    info.update(SUPublicEDKey=public_key,CFBundleIdentifier='com.myf-ricey.GooglePiggyUpdateFixture',CFBundleShortVersionString=version,CFBundleVersion=build,SUFeedURL=feed)
    (path/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    fw=path/'Contents/Frameworks/Sparkle.framework/Versions/B'
    for target in [fw/'Autoupdate',fw/'Updater.app',*list((fw/'XPCServices').glob('*.xpc')),path/'Contents/Frameworks/Sparkle.framework',path]:
        subprocess.run(['codesign','--force','--sign','-',str(target)],check=True,capture_output=True)

try:
    for case in ['valid','tampered','cancel','backup-failure','version-mismatch']:
        work=out/case;downloads=work/'downloads';downloads.mkdir(parents=True)
        feed=base+case+'/downloads/appcast.xml'
        old=work/'installed/GooglePiggy.app';old.parent.mkdir()
        new=work/'new/GooglePiggy.app';new.parent.mkdir()
        bundle(old,'0.5.1','8',feed);bundle(new,'0.5.2','9',feed)
        archive=downloads/'GooglePiggy-update.zip'
        subprocess.run(['/Applications/Keka.app/Contents/MacOS/Keka','--cli','7zz','a','-tzip','-snl',str(archive),str(new)],cwd=new.parent,check=True,stdout=subprocess.DEVNULL)
        subprocess.run([str(sparkle/'bin/generate_appcast'),'--ed-key-file',str(private_key),'--maximum-deltas','0','--download-url-prefix',base+case+'/downloads/',str(downloads)],check=True,stdout=subprocess.DEVNULL)
        if case=='tampered':
            data=bytearray(archive.read_bytes());data[-60]^=1;archive.write_bytes(data)
        sentinel=old.parent/'user-settings.json';sentinel.write_text('{"keep":true}')
        if case=='backup-failure': (old.parent/'GooglePiggy Backups').write_text('block backup creation')
        env=dict(os.environ,GOOGLEPIGGY_TEST_FEED=feed,GOOGLEPIGGY_TEST_CASE=case)
        process=subprocess.Popen([str(old/'Contents/MacOS/GooglePiggy')],env=env,stdout=subprocess.DEVNULL,stderr=(work/'stderr.log').open('w'))
        events=old.parent/'events.txt';text=''
        deadline=time.monotonic()+50
        while time.monotonic()<deadline:
            text=events.read_text() if events.exists() else ''
            if 'RELAUNCHED_0.5.2' in text or 'FAILED:' in text or 'TIMEOUT' in text or (case=='cancel' and 'CANCELLED' in text): break
            time.sleep(.2)
        if process.poll() is None:
            process.wait(timeout=5)
        installed=plistlib.loads((old/'Contents/Info.plist').read_bytes())
        assert sentinel.read_text()=='{"keep":true}'
        if case=='valid':
            assert 'RELAUNCHED_0.5.2' in text,text
            assert installed['CFBundleVersion']=='9'
            backups=list((old.parent/'GooglePiggy Backups').glob('*/GooglePiggy.app/Contents/Info.plist'))
            assert len(backups)==1 and plistlib.loads(backups[0].read_bytes())['CFBundleVersion']=='8'
            assert '等待权限请求处理完' in text,text
        else:
            assert ('CANCELLED' if case=='cancel' else 'FAILED:') in text and installed['CFBundleVersion']=='8',text
            assert 'RELAUNCHED' not in text
        print(f'PASS {case}: {installed["CFBundleShortVersionString"]}; settings retained',flush=True)
finally:
    server.shutdown()
    private_key.unlink(missing_ok=True)
