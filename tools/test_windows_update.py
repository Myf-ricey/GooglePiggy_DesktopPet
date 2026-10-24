"""Offline updater regression; all writes stay in temporary directories."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import windows_update as u
from update_notice import UpdateNotice
from codex_observer import CodexObserver
from family_store import FamilyStore

ROOT=Path(__file__).resolve().parents[1]

def row(number='0.5.2', **changes):
    tag='v'+number+'-windows'
    name=f'GooglePiggy-{number}-windows-x64.zip'
    value=dict(draft=False,prerelease=False,tag_name=tag,html_url=u.WEB+'tag/'+tag,
        body='## Changes\n- **One**\n* `Two`\n- Three\n- Four',
        assets=[dict(name=name,size=3,browser_download_url=u.WEB+'download/'+tag+'/'+name,digest='sha256:'+hashlib.sha256(b'zip').hexdigest())])
    value.update(changes)
    return value


def package(folder,number='0.5.2'):
    folder.mkdir(parents=True)
    (folder/'assets/macos-resources').mkdir(parents=True)
    (folder/'assets/macos-resources/animation-manifest.json').write_text('{}')
    (folder/'pig_pet.exe').write_bytes(b'new')
    (folder/'hooks').mkdir()
    (folder/'hooks/codex-pig-hook.ps1').write_text('new hook')
    u.make_manifest(folder,number)
    return folder


class Response(io.BytesIO):
    status=200


class UpdateTests(unittest.TestCase):
    def test_versions(self):
        self.assertGreater(u.version('0.4.10'),u.version('0.4.9'))
        self.assertEqual(u.version('0.4'),u.version('0.4.0.0'))
        for bad in ('1','v1.2','1.2-beta','１.2','1..2','1.2.3.4.5'):
            with self.assertRaises(ValueError): u.version(bad)

    def test_platform_assets_urls_notes(self):
        rows=[row(),row('8.0',draft=True),row('9.0',prerelease=True),row('10.0',assets=[]),
              row('11.0',tag_name='v11.0-macos'),row('12.0',html_url='https://evil.example/releases/tag/v12.0-windows')]
        parsed=u.parse_releases(rows)
        self.assertEqual([r.version for r in parsed],['0.5.2'])
        self.assertEqual(parsed[0].notes,'• One\n• Two\n• Three')
        broken=row(); broken['assets'][0]['size']=0
        self.assertEqual(u.parse_releases([broken]),[])
        broken=row(); broken['assets'][0]['browser_download_url']='http://github.com/evil.zip'
        self.assertEqual(u.parse_releases([broken]),[])

    def test_pagination_and_failures(self):
        filler=[dict(draft=True)]*100
        self.assertEqual(u.check_releases('0.5.1',lambda p:filler if p==1 else [row()]).version,'0.5.2')
        self.assertIsNone(u.check_releases('0.5.2',lambda p:[row()]))
        for fetch in (lambda p:[],lambda p:filler):
            with self.assertRaises(ValueError): u.check_releases('0.5.1',fetch)
        def fail(page): raise OSError('rate limit/offline')
        with self.assertRaises(OSError): u.check_releases('0.5.1',fail)

    def test_check_coalescing_and_manual_promotion(self):
        gate=threading.Event(); calls=[]
        def fetch(page):
            calls.append(page); gate.wait(3); return [row()]
        checker=u.Checker('0.5.1',fetch)
        checker.check(); checker.check(True); checker.check(True)
        gate.set()
        for _ in range(100):
            result=checker.poll()
            if result: break
            time.sleep(.01)
        self.assertEqual(calls,[1]); self.assertTrue(result[2]); self.assertFalse(checker.checking)

    def test_download_digest_size_cancel_and_retry(self):
        release=u.parse_releases([row()])[0]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'package.zip'; cancel=threading.Event(); progress=[]
            u.download(release,path,cancel,progress.append,lambda *a,**k:Response(b'zip'))
            self.assertEqual(path.read_bytes(),b'zip'); self.assertEqual(progress[-1],1)
            for data in (b'bad',b'z',b'zip too large'):
                with self.assertRaises(ValueError): u.download(release,path,cancel,progress.append,lambda *a,**k:Response(data))
                self.assertFalse(path.exists())
            cancel.set()
            with self.assertRaises(u.Cancelled): u.download(release,path,cancel,progress.append,lambda *a,**k:Response(b'zip'))
            cancel.clear()
            def offline(*a,**kw): raise OSError('offline')
            with self.assertRaises(OSError): u.download(release,path,cancel,progress.append,offline)
            u.download(release,path,cancel,progress.append,lambda *a,**k:Response(b'zip'))
            unsigned=u.Release(release.version,release.notes,release.url,release.asset_url,3,'')
            with self.assertRaises(ValueError): u.download(unsigned,path,cancel,progress.append)

    def test_archive_traversal_duplicates_symlinks_and_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=package(root/'package')
            archive=Path(shutil.make_archive(str(root/'valid'),'zip',source))
            u.extract_package(archive,root/'good','0.5.2')
            with self.assertRaises(ValueError): u.extract_package(archive,root/'wrong','0.5.3')
            self.assertFalse((root/'wrong').exists())
            for i,name in enumerate(('../escaped','/absolute','C:/bad','folder\\bad','aux.txt','folder/name.')):
                with zipfile.ZipFile(root/'bad.zip','w') as z:
                    info=zipfile.ZipInfo('placeholder'); info.filename=name; z.writestr(info,'bad')
                with self.assertRaises(ValueError): u.extract_package(root/'bad.zip',root/str(i),'0.5.2')
            with zipfile.ZipFile(root/'bad.zip','w') as z:
                z.writestr('FILE','1'); z.writestr('file','2')
            with self.assertRaises(ValueError): u.extract_package(root/'bad.zip',root/'duplicate','0.5.2')
            with zipfile.ZipFile(root/'bad.zip','w') as z:
                info=zipfile.ZipInfo('link'); info.external_attr=(0o120777<<16); z.writestr(info,'target')
            with self.assertRaises(ValueError): u.extract_package(root/'bad.zip',root/'link','0.5.2')

    def test_file_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=package(Path(tmp)/'package')
            (source/'pig_pet.exe').write_bytes(b'wrong')
            with self.assertRaises(ValueError): u.validate_tree(source,'0.5.2')

    def test_transaction_success_preserves_extras(self):
        with tempfile.TemporaryDirectory(prefix='猪猪 空格 ') as tmp:
            root=Path(tmp); target=package(root/'installed','0.5.1'); new=package(root/'new')
            (target/'pig_pet.exe').write_bytes(b'old'); (target/'user-settings.json').write_text('settings')
            external=root/'Codex-config'; external.write_text('hooks and autostart untouched')
            backup=u.install_transaction(target,new,'0.5.2',lambda p:p,lambda p,v:True,lambda p:None)
            self.assertEqual((backup/'pig_pet.exe').read_bytes(),b'old')
            self.assertEqual((target/'pig_pet.exe').read_bytes(),b'new')
            self.assertEqual((target/'user-settings.json').read_text(),'settings')
            self.assertEqual(external.read_text(),'hooks and autostart untouched')

    def test_backup_failure_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); target=package(root/'installed','0.5.1'); new=package(root/'new')
            (target/'pig_pet.exe').write_bytes(b'old')
            rename=Path.rename
            def denied(path,to):
                if path==target: raise PermissionError('locked backup')
                return rename(path,to)
            with patch.object(Path,'rename',denied),self.assertRaises(PermissionError):
                u.install_transaction(target,new,'0.5.2',lambda p:self.fail('must not launch'),lambda p,v:True,lambda p:None)
            self.assertEqual((target/'pig_pet.exe').read_bytes(),b'old')

    def test_readonly_stage_and_restart_failure_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); target=package(root/'installed','0.5.1'); new=package(root/'new')
            (target/'pig_pet.exe').write_bytes(b'old'); launches=[]; stopped=[]
            with patch.object(shutil,'copytree',side_effect=PermissionError('readonly')),self.assertRaises(PermissionError):
                u.install_transaction(target,new,'0.5.2',lambda p:None,lambda p,v:True,lambda p:None)
            def launch(p): launches.append((p/'pig_pet.exe').read_bytes()); return len(launches)
            with self.assertRaises(RuntimeError): u.install_transaction(target,new,'0.5.2',launch,lambda p,v:False,stopped.append)
            self.assertEqual(launches,[b'new',b'old']); self.assertEqual(stopped,[1])
            self.assertEqual((target/'pig_pet.exe').read_bytes(),b'old')

    def test_real_windows_file_lock(self):
        import ctypes
        from ctypes import wintypes
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); target=package(root/'installed','0.5.1'); new=package(root/'new')
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
            kernel.CreateFileW.restype=wintypes.HANDLE
            kernel.CloseHandle.argtypes=[wintypes.HANDLE]
            handle=kernel.CreateFileW(str(target/'pig_pet.exe'),0x80000000,1,None,3,0,None)
            self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
            try:
                with self.assertRaises(OSError): u.install_transaction(target,new,'0.5.2',lambda p:self.fail('locked'),lambda p,v:True,lambda p:None)
                self.assertTrue((target/'pig_pet.exe').exists())
            finally: kernel.CloseHandle(handle)

    def test_interrupted_swap_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); target=package(root/'installed','0.5.1')
            (target/'pig_pet.exe').write_bytes(b'old')
            backup=target.with_name(target.name+'.backup-fixture')
            u.atomic_json(u.journal_path(target),dict(target=str(target),backup=str(backup),phase='prepared'))
            target.rename(backup)
            u.recover_transaction(target)
            self.assertEqual((target/'pig_pet.exe').read_bytes(),b'old')
            self.assertEqual(json.loads(u.journal_path(target).read_text())['phase'],'rolled_back')

    def test_metadata_rotation_is_nonfatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'state_1.sqlite').touch()
            observer=CodexObserver(FamilyStore(),root,home=root)
            with patch.object(Path,'stat',side_effect=FileNotFoundError('rotated')):
                observer.refresh_metadata(time.time())

    def test_update_clamps_negative_monitor_at_four_dpi_scales(self):
        from types import SimpleNamespace
        import windows_pet as w
        for scale in (1,1.25,1.5,2):
            work=(-2560,-200,0,1320)
            for origin in ((-2800,-300),(-600,1000)):
                local=tuple(round(v*scale) for v in (230,104,590,620))
                moved=[]
                pet=SimpleNamespace(hwnd=1,dragging=False,edge_transition=None,edge_placement=None,hidden_family='',
                    pending_origin_delta=(0,0),_current_content_local_bounds=lambda:local,
                    _window_rect=lambda hwnd:(*origin,origin[0]+round(640*scale),origin[1]+round(640*scale)),
                    _set_window_origin=lambda hwnd,xy:moved.append(xy))
                pet._screen_bounds_for_local=lambda r:w.WindowsPet._screen_bounds_for_local(pet,r)
                with patch.object(w.win,'enumerate_monitor_infos',return_value=[SimpleNamespace(frame=work,work=work)]):
                    w.WindowsPet._fit_update_notice(pet)
                    first=pet.pending_origin_delta
                    w.WindowsPet._fit_update_notice(pet)
                    self.assertEqual(first,pet.pending_origin_delta)
                self.assertEqual(moved,[], 'Do not move the old bitmap before atomic submission')
                xy=tuple(a+b for a,b in zip(origin,pet.pending_origin_delta))
                bounds=tuple(local[i]+xy[i%2] for i in range(4))
                self.assertTrue(bounds[0]>=work[0] and bounds[1]>=work[1] and bounds[2]<=work[2] and bounds[3]<=work[3])

    def test_notice_geometry_buttons_and_reduced_motion(self):
        from PIL import Image
        import pig_pet as win
        from windows_pet import permission_surface,resize_alpha
        notice=UpdateNotice(u.parse_releases([row()])[0])
        renders=[]
        for t in (0,1):
            canvas=Image.new('RGBA',(640,640))
            notice.draw(canvas,'0.5.1',win.load_ui_font,permission_surface,win.wrap_text_by_width,True,t)
            renders.append(canvas.tobytes())
        self.assertEqual(renders[0],renders[1])
        for scale in (1,1.25,1.5,2):
            image=resize_alpha(canvas,(round(640*scale),round(640*scale)))
            for rect in notice.buttons.values():
                x,y=round((rect[0]+rect[2])/2*scale),round((rect[1]+rect[3])/2*scale)
                self.assertGreater(image.getpixel((x,y))[3],0)
        notice.phase='downloading'; self.assertEqual(set(notice.buttons),{'cancel'})
        for phase in ('verifying','ready','installing'):
            notice.phase=phase; self.assertFalse(notice.buttons)

    def test_long_title_hook_crlf_and_child_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt='User\'s request:\r\n"""\r\n'+('中文请求'*100)+'\r\n"""\r\n\r\nGenerate a title for this conversation:'
            payload=dict(hook_event_name='UserPromptSubmit',session_id='internal-title',prompt=prompt)
            run=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'hooks/codex-pig-hook.ps1')],input=json.dumps(payload,ensure_ascii=False).encode(),capture_output=True,env=dict(os.environ,GOOGLEPIGGY_STATE_DIR=tmp),timeout=15)
            self.assertEqual(run.returncode,0,run.stderr)
            events=list((Path(tmp)/'family-events').glob('*.json')); self.assertTrue(events)
            event=json.loads(events[0].read_text(encoding='utf-8-sig'))
            self.assertEqual(event['internal_request_kind'],'conversation_title')
            self.assertLessEqual(len(event['prompt_preview']),100)
            store=FamilyStore(); observer=CodexObserver(store,tmp,enabled=False)
            observer.poll(); self.assertFalse(store.nodes)
            for name in ('Stop','ResumeDetected','TaskCompleteFallback'):
                observer.ingest(dict(session_id='internal-title',event=name,received_at=time.time()))
            self.assertFalse(store.nodes)
            event.update(session_id='parent',agent_id='child'); observer.ingest(event)
            self.assertIn('child',store.nodes)
            event.pop('agent_id'); event['session_id']='registered'; event['token']='registered-unique'; observer.metadata['registered']={}
            observer.ingest(event); self.assertIn('registered',store.nodes)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(UpdateTests))
    u.atomic_json(ROOT/'qa/windows-update-tests.json',dict(tests=result.testsRun,passed=result.wasSuccessful(),
        failures=[str(t) for t,_ in result.failures+result.errors]))
    sys.exit(0 if result.wasSuccessful() else 1)
