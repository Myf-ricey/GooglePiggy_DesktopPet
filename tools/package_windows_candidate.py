"""Package a tested Windows release and a main-baseline source overlay."""
import argparse
import hashlib
import json
import shutil
import uuid
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OVERLAY=[
    'pig_pet.py','codex_bridge.py','animation_clock.py','family_store.py','leisure.py',
    'codex_observer.py','windows_pet.py','pig_pet.spec','install.ps1','uninstall.ps1',
    'build-release.ps1','README.md','README-WINDOWS.md','ASSET-NOTICE.md','WINDOWS-0.4-HANDOFF.md',
    'RELEASE-NOTES-v0.4.2-windows.md','hooks/codex-pig-hook.ps1',
    'tools/package_app_icon.py','tools/test_windows_port.py','tools/test_windows_runtime.py',
    'tools/package_windows_candidate.py','tools/smoke_test.py',
]


def zip_directory(directory,target):
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(directory.rglob('*')):
            if not path.is_file(): continue
            relative=path.relative_to(directory)
            if any(part in {'cache','qa','__pycache__','.git','build','dist'} for part in relative.parts): continue
            if path.suffix in {'.log','.pyc'}: continue
            archive.write(path,relative.as_posix())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline-source',required=True,type=Path)
    parser.add_argument('--source-commit',required=True)
    parser.add_argument('--version',default='0.4.2')
    parser.add_argument('--portable-dir',type=Path,default=ROOT/'dist/GifPigDesktopPet')
    args=parser.parse_args()
    baseline=args.baseline_source.resolve()
    version=args.version
    if not all(part.isdigit() for part in version.split('.')) or len(version.split('.')) != 3:
        parser.error('--version must be a three-part numeric version')
    if len(args.source_commit) != 40 or any(c not in '0123456789abcdef' for c in args.source_commit):
        parser.error('--source-commit must be the published source commit SHA')
    output=ROOT/('releases/windows-'+version)
    output.mkdir(parents=True,exist_ok=True)
    sha=args.source_commit
    stage=ROOT/'qa/source-staging'/uuid.uuid4().hex
    shutil.copytree(baseline,stage,ignore=shutil.ignore_patterns('*.zip','*.dmg','*.exe'))
    for name in OVERLAY:
        target=stage/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,target)
    shutil.copytree(ROOT/'assets/icons',stage/'assets/icons',dirs_exist_ok=True)
    evidence_ignore=shutil.ignore_patterns('*.zip','SHA256SUMS.txt','release-manifest.json')
    shutil.copytree(output,stage/('releases/windows-'+version),dirs_exist_ok=True,ignore=evidence_ignore)
    provenance={'mac_main_baseline':'ba11094445482de445452bbe57d219e0e6c6cf54','windows_source_commit':sha,'version':version+'-windows','tag':'v'+version+'-windows'}
    (stage/'WINDOWS-SOURCE-PROVENANCE.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    portable=args.portable_dir.resolve()
    for name in ('README.md','README-WINDOWS.md','WINDOWS-0.4-HANDOFF.md','RELEASE-NOTES-v0.4.2-windows.md'):
        shutil.copy2(ROOT/name,portable/name)
    shutil.copytree(output,portable/('releases/windows-'+version),dirs_exist_ok=True,ignore=evidence_ignore)
    (portable/'WINDOWS-SOURCE-PROVENANCE.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    targets=[(portable,output/('GooglePiggy-'+version+'-windows-x64.zip')),(stage,output/('GooglePiggy-'+version+'-source.zip'))]
    results=[]
    for directory,target in targets:
        zip_directory(directory,target)
        results.append({'file':target.name,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    results.append({'file':'pig_pet.exe','bytes':(portable/'pig_pet.exe').stat().st_size,'sha256':hashlib.sha256((portable/'pig_pet.exe').read_bytes()).hexdigest()})
    (output/'SHA256SUMS.txt').write_text(''.join(p['sha256']+'  '+p['file']+'\n' for p in results),encoding='ascii')
    provenance['artifacts']=results
    (output/'release-manifest.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(provenance,indent=2))


if __name__=='__main__': main()
