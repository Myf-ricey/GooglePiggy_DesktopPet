# Release Checklist

Use this checklist before publishing a GitHub release.

## Before Uploading Source

- Confirm `assets/` artwork can be redistributed publicly.
- Choose and add a `LICENSE` file if you want the code to be open source.
- Do not commit generated folders: `.venv-build/`, `build/`, `cache/`, `dist/`, `qa/`.
- Keep source GIF names ASCII-friendly in public packages:
  - `assets/source-gifs/left_fixed.gif`
  - `assets/source-gifs/flat.gif`
  - `assets/source-gifs/jump.gif`
  - `assets/source-gifs/carrot.gif`
  - `assets/source-gifs/question.gif`

## Local Verification

Run:

```powershell
python -m pip install -r requirements-dev.txt
python tools\prepare_effect_assets.py
python pig_pet.py --qa-only
python tools\smoke_test.py
.\build-release.ps1
```

Expected output:

```text
smoke_test=ok
dist\GifPigDesktopPet-windows-x64.zip
```

## GitHub Release

Recommended tag format:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

The workflow `.github/workflows/windows-release.yml` builds the ZIP and uploads it to the tagged release.

## Manual Install Test

On a clean Windows 10/11 x64 machine:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Check:

- The desktop shortcut launches the pet.
- Autostart registry value is created under the current user.
- Codex asks to trust the hook once after restart.
- Thinking state plays carrot.
- Stop state plays jump celebration and returns to idle.
- PermissionRequest shows the question pig bubble, then allow/deny is returned to Codex.
