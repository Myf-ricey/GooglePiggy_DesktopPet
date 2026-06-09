# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_dir = Path(SPECPATH)
datas = [
    (str(project_dir / "assets"), "assets"),
    (str(project_dir / "cache"), "cache"),
    (str(project_dir / "hooks"), "hooks"),
    (str(project_dir / "tools"), "tools"),
    (str(project_dir / "README.md"), "."),
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
    hiddenimports=["codex_bridge"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="pig_pet",
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
