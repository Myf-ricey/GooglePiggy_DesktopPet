# Cross-platform Release Checklist

Use this checklist before publishing GooglePiggy `v0.2.3` or a later release.

## 1. Source package

- Keep the existing Windows runtime, installer, PowerShell hook, build script, and workflow.
- Include the native macOS AppKit runtime, installer, uninstaller, build script, and workflow.
- Include `README.md`, `README-MAC.md`, `MACOS-PORTING.md`, and this checklist.
- Do not include `.git/`, virtual environments, `build/`, `cache/`, `dist/`, `qa/`,
  `__pycache__/`, `.DS_Store`, or personal test files.
- Confirm the artwork under `assets/` may be redistributed; see `ASSET-NOTICE.md`.

The prepared source overlay is:

```text
GooglePiggy-GitHub-source-v0.2.3.zip
```

Extract it into a clone of the existing Windows repository and replace files with the
same names. Review the diff before committing.

## 2. Windows verification

On Windows 10/11 x64:

```powershell
python -m pip install -r requirements-dev.txt
python tools\prepare_effect_assets.py
python pig_pet.py --qa-only
python tools\smoke_test.py
.\build-release.ps1
```

Expected artifact:

```text
dist\GifPigDesktopPet-windows-x64.zip
```

Manual checks:

- Desktop shortcut and current-user autostart work.
- Codex thinking, completion, and permission events reach the pet.
- Permission allow/deny is returned to Codex.
- Existing Windows install and uninstall behavior is unchanged.

## 3. macOS verification

On macOS 13 or later:

```zsh
./build-macos.sh
codesign --verify --deep --strict build/macos/GooglePiggy.app
lipo -info build/macos/GooglePiggy.app/Contents/MacOS/GooglePiggy
hdiutil verify dist/GooglePiggy-macos-universal.dmg
unzip -tq dist/GooglePiggy-macos-universal.zip
```

Expected tests and artifacts:

```text
smoke_test=ok
macos_manifest_test=ok
macos_release_test=ok
dist/GooglePiggy-macos-universal.zip
dist/GooglePiggy-macos-universal.dmg
```

`lipo` must report both `arm64` and `x86_64`.

Regression checks from the first macOS test cycle:

- Cancelling the right-click menu does not hide or terminate the pet.
- Newly installed Codex hooks clearly instruct the user to complete `/hooks` trust.
- Thinking and completion animations run after trust is granted.
- Permission summaries wrap onto multiple lines instead of truncating after one line.
- `apply_patch` permission requests show a localized action and absolute `/Users/...`
  path, never the raw patch protocol or internal tool name.
- When a hook omits `tool_input`, the same session/turn/tool record restores the exact
  operation and target instead of displaying a generic fallback.
- Session recovery accepts both quoted JSON fields and unquoted JavaScript object fields,
  including shell-wrapped patches and a later non-permission command in the same turn.
- Relative targets are expanded from the session working directory; if neither hook nor
  session contains details, the pig leaves authorization to Codex instead of presenting a
  vague allow/deny question.

## 4. GitHub upload

Commit the source overlay only after reviewing it. A `v*` tag starts both workflows:

```text
.github/workflows/windows-release.yml
.github/workflows/macos-release.yml
```

Recommended tag:

```text
v0.2.3
```

Attach these locally verified universal Mac assets to the GitHub Release:

```text
GooglePiggy-macos-universal.zip
GooglePiggy-macos-universal.dmg
```

The workflows additionally produce Windows x64, macOS arm64, and macOS x64 assets.
Use `RELEASE-NOTES-v0.2.3.md` as the starting release description.

## 5. Public-release polish

- Replace the ad-hoc Mac signature with a Developer ID Application signature when
  available.
- Submit the Mac app for Apple notarization and staple the ticket.
- Test installation on a clean Windows user and a clean macOS user.
- Verify every downloadable asset against `SHA256SUMS.txt`.
