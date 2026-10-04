# macOS Release Checklist (`v0.4.0`)

## 1. Local build

```zsh
./build-macos.sh
```

Expected outputs:

```text
dist/GooglePiggy-macos-universal.zip
dist/GooglePiggy-macos-universal.dmg
```

The build must finish with:

```text
macos_manifest_test=ok
macos_release_test=ok
```

## 2. Verify artifacts

```zsh
codesign --verify --deep --strict build/macos/GooglePiggy.app
lipo -info build/macos/GooglePiggy.app/Contents/MacOS/GooglePiggy
hdiutil verify dist/GooglePiggy-macos-universal.dmg
/Applications/Keka.app/Contents/MacOS/Keka --cli 7zz t dist/GooglePiggy-macos-universal.zip
```

`lipo` must report both `arm64` and `x86_64`.

## 3. Upload

For one download that supports all Macs, upload:

```text
GooglePiggy-macos-universal-v0.4.0.zip
GooglePiggy-macos-universal.dmg
```

The ZIP is convenient for GitHub Releases; the DMG is convenient for Finder users.

## 4. Architecture-specific CI builds

Pushing a `v*` tag runs `.github/workflows/macos-release.yml` on native Apple
Silicon and Intel runners. It attaches these extra files to the tagged release:

```text
GooglePiggy-macos-arm64.zip
GooglePiggy-macos-arm64.dmg
GooglePiggy-macos-x64.zip
GooglePiggy-macos-x64.dmg
```

## 5. Recommended public-release polish

- Sign with a Developer ID Application certificate instead of ad-hoc signing.
- Submit the app for Apple notarization and staple the ticket before packaging.
- Test `install.command`, Codex thinking/success, permission allow/deny, right-click
  previews, dragging, autostart, and `uninstall.command` on a clean user account.
- Cancel the right-click menu by clicking blank space and confirm the pet remains visible.
- Confirm `/hooks` trust guidance appears after installation and Codex events work after
  trust is granted.
- Use a permission request containing a long path and confirm the body wraps to multiple
  lines instead of truncating after one line.
- Trigger an `apply_patch` permission request and confirm the bubble shows only a Chinese
  action and absolute `/Users/...` path, without `apply_patch` or `*** Begin Patch`.
- Replay a permission event without `tool_input` and confirm the matching Codex
  session/turn/tool record restores all file paths.
- Replay both `{"cmd":"..."}` and `{cmd:"..."}` session formats, including a shell
  command that embeds `apply_patch` and a Chinese `justification`.
- Put a later non-permission shell command in the same turn and confirm recovery still
  selects the permission-bearing call.
- Replay a relative file path and confirm the session working directory expands it to an
  absolute path.
- Remove both hook input and matching session data and confirm the pig does not display a
  vague allow/deny request.
- Confirm create/delete file commands, opening an application, and changing display
  brightness produce explicit Chinese requests.
- Install over a running older copy and confirm the old process exits and the new version
  starts.
- While idle, drag the pet to every physical desktop edge and confirm it hides with only the
  outlined tail visible; internal seams between monitors must not trigger hiding.
- Click every tail and confirm the pet reveals without success fireworks. Start a Codex task
  while hidden and confirm the pet reveals automatically in the correct working state.
- Publish `README-MAC.md` with the release.

## v0.4.0 regression checks

- Run `tools/test_leisure_native.py` after building the app.
- Compile `tests/leisure/main.swift` with `LeisureRoutine.swift` and run it.
- Compile `tests/thread-animation/main.swift` with `ThreadAnimationClock.swift` and run it.
- Verify the context menu has no animation previews.
- Verify the installed LaunchAgent and Codex hooks reference the production app.
- Publish the macOS-only tag `v0.4.0-macos`; retain Windows releases.

Native builds use the checked-in frame resources and must work without `cache/`. The legacy Python `smoke_test.py` belongs to the generated Windows asset pipeline; native release validation runs `--self-test` and `test_macos_release.py`.
