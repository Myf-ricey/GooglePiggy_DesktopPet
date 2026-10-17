"""Windows update transport and recoverable installation. No GUI/account access.

Trust is HTTPS GitHub release metadata + its SHA-256 asset digest, not Sparkle
or publisher signing. Missing digests fail closed. Tests inject transports;
production endpoints cannot be changed by environment variables.
"""
from __future__ import annotations
import hashlib
import json
import os
import queue
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen
from codex_bridge import atomic_json

REPO = 'Myf-ricey/GooglePiggy_DesktopPet'
API = 'https://api.github.com/repos/' + REPO + '/releases'
WEB = 'https://github.com/' + REPO + '/releases/'
MANIFEST = 'windows-update.json'
MAX_PACKAGE = 512 * 1024 * 1024
MAX_EXPANDED = 1536 * 1024 * 1024


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}', value):
        raise ValueError('不支持的版本号')
    parts = tuple(int(p) for p in value.split('.'))
    return parts + (0,) * (4-len(parts))


@dataclass(frozen=True)
class Release:
    version: str
    notes: str
    url: str
    asset_url: str
    size: int
    digest: str


def parse_releases(rows):
    result = []
    for row in rows:
        if not isinstance(row, dict) or row.get('draft') is not False or row.get('prerelease') is not False:
            continue
        tag = row.get('tag_name', '')
        if not isinstance(tag, str) or not re.fullmatch(r'v[0-9]+(?:\.[0-9]+){1,3}-windows', tag):
            continue
        number = tag[1:-8]
        if row.get('html_url') != WEB + 'tag/' + tag:
            continue
        name = f'GooglePiggy-{number}-windows-x64.zip'
        assets = row.get('assets')
        if not isinstance(assets, list):
            continue
        matches = [a for a in assets if isinstance(a, dict) and a.get('name') == name and
                   type(a.get('size')) is int and 0 < a['size'] <= MAX_PACKAGE and
                   a.get('browser_download_url') == WEB + 'download/' + tag + '/' + name]
        if len(matches) != 1:
            continue
        asset = matches[0]
        bullets = [line.strip()[2:].replace('**','').replace('`','') for line in str(row.get('body') or '').splitlines()
                   if line.strip().startswith(('- ', '* '))][:3]
        notes = '\n'.join('• '+line for line in bullets)[:180] or '新版已发布，点击更新即可下载并安装。'
        result.append(Release(number, notes, row['html_url'], asset['browser_download_url'], asset['size'], str(asset.get('digest') or '')))
    return result


def read_page(page):
    request = Request(API + f'?per_page=100&page={page}', headers={'User-Agent':'GooglePiggy-Windows', 'Accept':'application/vnd.github+json'})
    with urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise ValueError('更新服务暂时不可用')
        data = response.read(8_000_001)
    if len(data) > 8_000_000:
        raise ValueError('更新响应过大')
    rows = json.loads(data)
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError('无效的更新响应')
    return rows


def check_releases(current, fetch=read_page):
    found = []
    for page in range(1, 6):
        rows = fetch(page)
        found.extend(parse_releases(rows))
        if len(rows) < 100:
            break
    else:
        raise ValueError('更新列表分页未完成，请稍后重试')
    if not found:
        raise ValueError('暂未找到有效的 Windows 正式版本')
    latest = max(found, key=lambda r: version(r.version))
    return latest if version(latest.version) > version(current) else None


class Checker:
    """Worker emits results; only the owning GUI thread consumes them."""
    def __init__(self, current, fetch=read_page):
        self.current, self.fetch = current, fetch
        self.checking = self.manual = False
        self.results = queue.Queue()

    def check(self, manual=False):
        self.manual |= manual
        if self.checking:
            return
        self.checking = True
        def work():
            try:
                self.results.put((check_releases(self.current, self.fetch), None))
            except Exception as error:
                self.results.put((None, str(error)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            release, error = self.results.get_nowait()
        except queue.Empty:
            return None
        manual = self.manual
        self.checking = self.manual = False
        return release, error, manual


class Cancelled(Exception):
    pass


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(release, path, cancel, progress, opener=urlopen):
    if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', release.digest):
        raise ValueError('此版本缺少 GitHub SHA-256 校验，无法自动安装。')
    expected = WEB + f'download/v{release.version}-windows/GooglePiggy-{release.version}-windows-x64.zip'
    if release.asset_url != expected:
        raise ValueError('更新附件地址不匹配')
    try:
        request = Request(release.asset_url, headers={'User-Agent':'GooglePiggy-Windows'})
        with opener(request, timeout=15) as response, Path(path).open('wb') as stream:
            if response.status != 200:
                raise ValueError('下载失败，请重试')
            received = 0
            while True:
                if cancel.is_set():
                    raise Cancelled()
                chunk = response.read(128*1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > min(release.size, MAX_PACKAGE):
                    raise ValueError('下载长度与发布信息不符')
                stream.write(chunk)
                progress(received/release.size)
        if cancel.is_set():
            raise Cancelled()
        if received != release.size or sha256(path) != release.digest[7:].lower():
            raise ValueError('更新包校验失败，请重新下载')
    except Exception:
        Path(path).unlink(missing_ok=True)
        raise


def safe_name(name):
    parts = PurePosixPath(name).parts
    if not parts or '\\' in name or ':' in name or name.startswith('/') or any(
        p in ('.','..') or p.endswith((' ','.')) or p.split('.')[0].upper() in
        {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))} for p in parts):
        raise ValueError('更新包包含不安全的路径')
    return parts


def validate_tree(folder, expected):
    try:
        manifest = json.loads((folder/MANIFEST).read_text(encoding='utf-8'))
    except (OSError,ValueError) as error:
        raise ValueError('更新包缺少有效的 Windows 更新清单') from error
    if not isinstance(manifest,dict):
        raise ValueError('更新包清单格式无效')
    if manifest.get('version') != expected or manifest.get('platform') != 'windows-x64' or manifest.get('schema') != 1:
        raise ValueError('更新包版本或平台不匹配')
    files = manifest.get('files')
    if not isinstance(files, dict) or 'pig_pet.exe' not in files or 'assets/macos-resources/animation-manifest.json' not in files:
        raise ValueError('更新包清单不完整')
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    if actual != set(files) | {MANIFEST}:
        raise ValueError('更新包文件与清单不符')
    for name, digest in files.items():
        safe_name(name)
        if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest) or sha256(folder/name) != digest:
            raise ValueError('更新包文件校验失败：'+name)
    return manifest


def extract_package(archive, destination, expected):
    destination.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(archive) as package:
            infos = package.infolist()
            if len(infos) > 20000 or sum(i.file_size for i in infos) > MAX_EXPANDED:
                raise ValueError('更新包解压大小超限')
            seen = set()
            for item in infos:
                safe_name(item.filename)
                key = item.filename.rstrip('/').casefold()
                if key in seen or stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError('更新包包含重复文件或链接')
                seen.add(key)
            package.extractall(destination)
        validate_tree(destination, expected)
    except Exception:
        shutil.rmtree(destination)
        raise
    return destination


class Installer:
    def __init__(self, state_dir):
        self.root = Path(state_dir)/'updates'
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False

    def start(self, release):
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        def work():
            job = self.root/uuid.uuid4().hex
            try:
                job.mkdir(parents=True)
                archive = job/'download.zip'
                download(release, archive, self.cancel, lambda p:self.events.put(('downloading',p)))
                self.events.put(('verifying',None))
                package = extract_package(archive, job/'package', release.version)
                self.events.put(('ready',package))
            except Cancelled:
                self.events.put(('cancelled',None))
            except Exception as error:
                self.events.put(('error',str(error)))
            finally:
                self.busy = False
        threading.Thread(target=work, daemon=True).start()


def make_manifest(folder, number):
    version(number)
    files = {p.relative_to(folder).as_posix():sha256(p) for p in sorted(folder.rglob('*'))
             if p.is_file() and p.name != MANIFEST and not any(x in {'qa','cache','__pycache__'} for x in p.relative_to(folder).parts)}
    atomic_json(folder/MANIFEST, {'schema':1,'version':number,'platform':'windows-x64','files':files})


def rename_retry(source, destination, attempts=25):
    for attempt in range(attempts):
        try:
            source.rename(destination)
            return
        except OSError:
            if attempt == attempts-1:
                raise
            time.sleep(.2)


def journal_path(target):
    return target.with_name(target.name+'.update-transaction.json')


def recover_transaction(target):
    """Restore an interrupted swap using its recorded, same-parent backup."""
    target = Path(target).resolve()
    path = journal_path(target)
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('phase') in {'committed','rolled_back'}:
        return
    backup = Path(data['backup'])
    if backup.parent != target.parent or not backup.name.startswith(target.name+'.backup-'):
        raise ValueError('恢复记录的备份路径不匹配')
    if backup.exists():
        if target.exists():
            rename_retry(target,target.with_name(target.name+'.failed-'+uuid.uuid4().hex))
        rename_retry(backup,target)
    if not (target/'pig_pet.exe').is_file():
        raise RuntimeError('自动恢复未完成，请使用备份目录：'+str(backup))
    atomic_json(path,dict(data,phase='rolled_back'))


def install_transaction(target, package, expected, launch, healthy, stop):
    """Stage without changing target. Rename creates a complete backup or fails.

    Caller waits for the old process. Only the child returned by launch may be
    stopped on failure. Backup is retained even after a successful upgrade.
    """
    target, package = Path(target).resolve(), Path(package).resolve()
    validate_tree(package, expected)
    if not (target/'pig_pet.exe').is_file() or target == package or target in package.parents:
        raise ValueError('安装目录无效')
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in target.rglob('*')):
        raise ValueError('安装目录包含链接，请手动更新')
    token = uuid.uuid4().hex
    stage = target.with_name(target.name+'.staging-'+token)
    backup = target.with_name(target.name+'.backup-'+token)
    failed = target.with_name(target.name+'.failed-'+token)
    swapped = False
    child = None
    journal = dict(target=str(target),backup=str(backup),stage=str(stage),phase='prepared')
    try:
        shutil.copytree(target, stage)
        # Remove only files owned by the previous package, never user extras.
        try:
            old = json.loads((target/MANIFEST).read_text(encoding='utf-8'))['files']
        except (OSError, ValueError, KeyError):
            old = {}
        new = json.loads((package/MANIFEST).read_text(encoding='utf-8'))['files']
        for name in set(old)-set(new):
            safe_name(name)
            (stage/name).unlink(missing_ok=True)
        shutil.copytree(package, stage, dirs_exist_ok=True)
        # No destructive writes until a complete prepared copy exists.
        atomic_json(journal_path(target),journal)
        rename_retry(target,backup)
        swapped = True
        rename_retry(stage,target)
        child = launch(target)
        if not healthy(child, expected):
            raise RuntimeError('新版启动未通过健康检查')
        atomic_json(journal_path(target),dict(journal,phase='committed'))
        return backup
    except Exception:
        if swapped:
            if child is not None:
                stop(child)
            if target.exists():
                rename_retry(target,failed)
            rename_retry(backup,target)
            atomic_json(journal_path(target),dict(journal,phase='rolled_back'))
            launch(target)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def prepare_helper(app_dir, package, number, status_path, isolated=False):
    """Run a copied frozen runtime outside the installation being replaced."""
    if not getattr(sys, 'frozen', False):
        raise ValueError('源码运行不支持自动覆盖，请使用 Windows 便携版')
    job = package.parent
    runner = job/'helper'
    shutil.copytree(app_dir, runner, ignore=shutil.ignore_patterns('assets','hooks','tools','qa','cache','__pycache__'))
    job_file = job/'install-job.json'
    atomic_json(job_file, dict(target=str(app_dir.resolve()),package=str(package.resolve()),version=number,
        pid=os.getpid(),status=str(status_path.resolve()),isolated=isolated))
    subprocess.Popen([str(runner/'pig_pet.exe'),'--update-helper',str(job_file)],cwd=runner,
                     creationflags=subprocess.CREATE_NO_WINDOW)
    return job_file


def recovery_registration(job_file, enabled):
    import winreg
    job = json.loads(Path(job_file).read_text(encoding='utf-8'))
    if job.get('isolated'):
        return
    name = 'GooglePiggyRecovery-'+hashlib.sha256(job['target'].encode()).hexdigest()[:12]
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\RunOnce') as key:
        if enabled:
            winreg.SetValueEx(key,name,0,winreg.REG_SZ,subprocess.list2cmdline([sys.executable,'--update-recover',str(job_file)]))
        else:
            try: winreg.DeleteValue(key,name)
            except FileNotFoundError: pass


def run_recovery(job_file):
    job_file = Path(job_file)
    job = json.loads(job_file.read_text(encoding='utf-8'))
    try:
        recover_transaction(Path(job['target']))
        recovery_registration(job_file,False)
        args = [str(Path(job['target'])/'pig_pet.exe'),'--status-file',job['status']]
        if job.get('isolated'): args += ['--qa-window','--no-codex-observer']
        subprocess.Popen(args,cwd=job['target'],creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as error:
        atomic_json(job_file.with_name('recovery-error.json'),{'error':str(error)})
        recovery_registration(job_file,True)


def run_helper(job_file):
    """Handshake, wait for precisely the owning process, swap and health-check."""
    import ctypes
    from ctypes import wintypes
    job_file = Path(job_file)
    result_file = job_file.with_name('install-result.json')
    handle = None
    old_exited = False
    try:
        job = json.loads(job_file.read_text(encoding='utf-8'))
        target = Path(job['target']).resolve()
        status = Path(job['status'])
        api = ctypes.WinDLL('kernel32',use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
        api.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
        handle = api.OpenProcess(0x100000|0x1000,False,job['pid'])
        size = wintypes.DWORD(32768)
        name = ctypes.create_unicode_buffer(size.value)
        if not handle or not api.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(size)) or Path(name.value).resolve() != target/'pig_pet.exe':
            raise ValueError('原进程身份不匹配；取消安装')
        recovery_registration(job_file,True)
        atomic_json(job_file.with_name('helper-ready.json'),{'ready':True})
        if api.WaitForSingleObject(handle,60000) != 0:
            raise TimeoutError('桌宠未退出，已取消替换')
        if job_file.with_name('abort.json').exists():
            raise RuntimeError('安装已取消')
        old_exited = True
        def launch(folder):
            args = [str(folder/'pig_pet.exe'),'--status-file',str(status)]
            if job.get('isolated'):
                args += ['--qa-window','--no-codex-observer']
            return subprocess.Popen(args,cwd=folder,creationflags=subprocess.CREATE_NO_WINDOW,
                                    env=dict(os.environ,GOOGLEPIGGY_UPDATE_START=str(folder.resolve())))
        def stop(child):
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=15)
        def healthy(child, expected):
            end = time.monotonic()+30
            while time.monotonic() < end and child.poll() is None:
                try:
                    h = json.loads((status.parent/'pig-heartbeat.json').read_text(encoding='utf-8'))
                    if h.get('pid') == child.pid and h.get('version') == expected+'-windows' and h.get('window_visible'):
                        return True
                except (OSError,ValueError):
                    pass
                time.sleep(.2)
            return False
        backup = install_transaction(target,Path(job['package']),job['version'],launch,healthy,stop)
        atomic_json(result_file,{'success':True,'backup':str(backup)})
        recovery_registration(job_file,False)
    except Exception as error:
        atomic_json(result_file,{'success':False,'error':str(error)})
        # A pre-swap failure also needs the old GUI restarted. Transaction
        # rollback already restarts it; single-instance gating prevents twins.
        if old_exited:
            try:
                recover_transaction(target)
                launch(target)
                recovery_registration(job_file,False)
            except Exception:
                pass
        else:
            recovery_registration(job_file,False)
    finally:
        if handle:
            api.CloseHandle(handle)
