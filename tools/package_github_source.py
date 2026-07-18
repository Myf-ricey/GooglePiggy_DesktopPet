#!/usr/bin/env python3
"""Create a clean source overlay ZIP for the existing GitHub repository."""

from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_VERSION = "0.2.3"

ROOT_FILES = (
    ".gitattributes",
    ".gitignore",
    "ASSET-NOTICE.md",
    "GITHUB-UPLOAD-GUIDE.md",
    "LICENSE",
    "MACOS-PORTING.md",
    "README-MAC.md",
    "README.md",
    "RELEASE-CHECKLIST-MAC.md",
    "RELEASE-CHECKLIST.md",
    "RELEASE-NOTES-v0.2.2.md",
    "RELEASE-NOTES-v0.2.3.md",
    "build-macos.sh",
    "build-release.ps1",
    "codex_bridge.py",
    "install.ps1",
    "pig_pet.py",
    "pig_pet.spec",
    "requirements-dev.txt",
    "requirements-macos-build.txt",
    "requirements.txt",
    "start-pig-pet.cmd",
    "uninstall.ps1",
    "启动猪猪桌宠.cmd",
)

SOURCE_DIRECTORIES = (
    ".github",
    "assets",
    "hooks",
    "macos",
    "tools",
)

IGNORED_NAMES = {
    ".DS_Store",
    "__pycache__",
}

FORBIDDEN_PARTS = {
    ".git",
    ".venv-build",
    ".venv-macos",
    ".venv-macos-build",
    "__pycache__",
    "build",
    "cache",
    "dist",
    "qa",
}

REQUIRED_PATHS = {
    ".github/workflows/windows-release.yml",
    ".github/workflows/macos-release.yml",
    "pig_pet.py",
    "install.ps1",
    "build-release.ps1",
    "macos/Sources/GooglePiggy/PetController.swift",
    "macos/install.command",
    "build-macos.sh",
    "README.md",
    "README-MAC.md",
}


def ignored(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in IGNORED_NAMES or name.endswith(".pyc")
    }


def copy_sources(destination: Path) -> None:
    for relative in ROOT_FILES:
        source = PROJECT_DIR / relative
        if not source.is_file():
            raise FileNotFoundError(f"Required source file is missing: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    for relative in SOURCE_DIRECTORIES:
        source = PROJECT_DIR / relative
        if not source.is_dir():
            raise FileNotFoundError(f"Required source directory is missing: {relative}")
        shutil.copytree(
            source,
            destination / relative,
            ignore=ignored,
        )


def validate_sources(destination: Path, version: str) -> list[Path]:
    files = sorted(path for path in destination.rglob("*") if path.is_file())
    relative_files = {path.relative_to(destination).as_posix() for path in files}
    missing = sorted(REQUIRED_PATHS - relative_files)
    if missing:
        raise RuntimeError(f"Source package is missing: {', '.join(missing)}")

    for path in files:
        relative = path.relative_to(destination)
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            raise RuntimeError(f"Generated/private path entered package: {relative}")
        if path.name in IGNORED_NAMES or path.suffix == ".pyc":
            raise RuntimeError(f"Ignored file entered package: {relative}")

    build_script = (destination / "build-macos.sh").read_text(encoding="utf-8")
    info_plist = (destination / "macos" / "Info.plist").read_text(encoding="utf-8")
    if f'VERSION="${{VERSION:-{version}}}"' not in build_script:
        raise RuntimeError("build-macos.sh version does not match package version")
    if f"<string>{version}</string>" not in info_plist:
        raise RuntimeError("macOS Info.plist version does not match package version")
    return files


def write_zip(destination: Path, files: list[Path], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in files:
            archive.write(path, path.relative_to(destination).as_posix())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = (
        args.output.expanduser().resolve()
        if args.output
        else PROJECT_DIR
        / "dist"
        / f"GooglePiggy-GitHub-source-v{args.version}.zip"
    )

    with tempfile.TemporaryDirectory(prefix="googlepiggy-github-source-") as root:
        staging = Path(root)
        copy_sources(staging)
        files = validate_sources(staging, args.version)
        write_zip(staging, files, output)

    print(f"github_source_zip={output}")
    print(f"github_source_files={len(files)}")


if __name__ == "__main__":
    main()
