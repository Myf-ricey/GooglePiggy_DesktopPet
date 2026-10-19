# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_dir = Path(SPECPATH)
datas = [
    (str(project_dir / "assets"), "assets"),
    (str(project_dir / "hooks"), "hooks"),
    (str(project_dir / "tools"), "tools"),
    (str(project_dir / "README.md"), "."),
    (str(project_dir / "README-WINDOWS.md"), "."),
    (str(project_dir / "RELEASE-NOTES-v0.5.4-windows.md"), "."),
    (str(project_dir / "WINDOWS-0.4-HANDOFF.md"), "."),
    (str(project_dir / "ASSET-NOTICE.md"), "."),
    (str(project_dir / "install.ps1"), "."),
    (str(project_dir / "uninstall.ps1"), "."),
    (str(project_dir / "start-pig-pet.cmd"), "."),
    (str(project_dir / "启动猪猪桌宠.cmd"), "."),
]

analysis = Analysis(
    ["pig_pet.py"],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=["codex_bridge", "windows_pet", "family_store", "animation_clock", "codex_observer", "leisure", "windows_update", "update_notice", "windows_animation_timer", "tools.profile_windows_animation"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Development bytecode must not enter the portable payload or its manifest.
analysis.datas = [entry for entry in analysis.datas
                 if '__pycache__' not in Path(entry[0]).parts and not entry[0].endswith('.pyc')]
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="pig_pet",
    icon=str(project_dir / "assets" / "icons" / "piggy-idle-v2.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    contents_directory=".",
)

collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="GifPigDesktopPet",
)
