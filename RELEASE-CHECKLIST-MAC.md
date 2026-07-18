# macOS Release Checklist

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
smoke_test=ok
macos_manifest_test=ok
macos_release_test=ok
```

## 2. Verify artifacts

```zsh
codesign --verify --deep --strict build/macos/GooglePiggy.app
lipo -info build/macos/GooglePiggy.app/Contents/MacOS/GooglePiggy
hdiutil verify dist/GooglePiggy-macos-universal.dmg
unzip -tq dist/GooglePiggy-macos-universal.zip
```

`lipo` must report both `arm64` and `x86_64`.

## 3. Upload

For one download that supports all Macs, upload:

```text
GooglePiggy-macos-universal.zip
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
- Publish `README-MAC.md` with the release.
