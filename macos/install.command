#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
SOURCE_APP="$SCRIPT_DIR/GooglePiggy.app"
INSTALL_DIR="$HOME/Applications"
DEST_APP="$INSTALL_DIR/GooglePiggy.app"
NO_AUTOSTART=0
NO_CODEX_HOOKS=0
NO_START=0
CODEX_CLI=""

for candidate in \
    "/Applications/ChatGPT.app/Contents/Resources/codex" \
    "/Applications/Codex.app/Contents/Resources/codex"; do
    if [[ -x "$candidate" ]]; then
        CODEX_CLI="$candidate"
        break
    fi
done
if [[ -z "$CODEX_CLI" ]] && command -v codex >/dev/null 2>&1; then
    CODEX_CLI="$(command -v codex)"
fi

for argument in "$@"; do
    case "$argument" in
        --no-autostart) NO_AUTOSTART=1 ;;
        --no-codex-hooks) NO_CODEX_HOOKS=1 ;;
        --no-start) NO_START=1 ;;
        *)
            print -u2 "Unknown option: $argument"
            exit 2
            ;;
    esac
done

if [[ ! -d "$SOURCE_APP" ]]; then
    print -u2 "GooglePiggy.app was not found next to install.command."
    exit 1
fi

mkdir -p "$INSTALL_DIR"
pkill -f "$DEST_APP/Contents/MacOS/GooglePiggy" >/dev/null 2>&1 || true
pkill -x "GooglePiggy" >/dev/null 2>&1 || true
for _ in {1..20}; do
    if ! pgrep -x "GooglePiggy" >/dev/null 2>&1; then
        break
    fi
    sleep 0.05
done
rm -rf "$DEST_APP"
/usr/bin/ditto "$SOURCE_APP" "$DEST_APP"

EXECUTABLE="$DEST_APP/Contents/MacOS/GooglePiggy"
if (( NO_CODEX_HOOKS == 0 )); then
    "$EXECUTABLE" --install-hooks
    if [[ -n "$CODEX_CLI" ]]; then
        "$CODEX_CLI" features enable hooks >/dev/null 2>&1 || true
    fi
fi

if (( NO_AUTOSTART == 0 )); then
    "$EXECUTABLE" --enable-autostart
fi

if (( NO_START == 0 )); then
    /usr/bin/open "$DEST_APP"
fi

print "猪猪桌宠已安装到：$DEST_APP"
if (( NO_CODEX_HOOKS == 0 )); then
    print ""
    print "【Codex 联动还需一次安全确认】"
    if [[ -n "$CODEX_CLI" ]]; then
        print "1. 打开“终端”，运行：\"$CODEX_CLI\""
    else
        print "1. 打开“终端”，运行：codex"
    fi
    print "2. 进入 Codex 后输入：/hooks"
    print "3. 选择：Trust all and continue"
    print "4. 退出终端版 Codex，再新建任务或重启 Codex 桌面版"
    print "Codex 会阻止尚未信任的用户 Hook；只重启不会让它自动生效。"
fi
