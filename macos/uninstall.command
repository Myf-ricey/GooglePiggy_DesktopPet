#!/bin/zsh
set -euo pipefail

INSTALL_APP="$HOME/Applications/GooglePiggy.app"
INSTALL_EXECUTABLE="$INSTALL_APP/Contents/MacOS/GooglePiggy"
SCRIPT_DIR="${0:A:h}"
FALLBACK_EXECUTABLE="$SCRIPT_DIR/GooglePiggy.app/Contents/MacOS/GooglePiggy"

if [[ -x "$INSTALL_EXECUTABLE" ]]; then
    HELPER="$INSTALL_EXECUTABLE"
elif [[ -x "$FALLBACK_EXECUTABLE" ]]; then
    HELPER="$FALLBACK_EXECUTABLE"
else
    HELPER=""
fi

if [[ -n "$HELPER" ]]; then
    "$HELPER" --uninstall-hooks || true
    "$HELPER" --disable-autostart || true
fi

pkill -f "$INSTALL_EXECUTABLE" >/dev/null 2>&1 || true
rm -f "$HOME/Library/LaunchAgents/com.myf-ricey.GooglePiggyDesktopPet.autostart.plist"
rm -rf "$INSTALL_APP"

print "猪猪桌宠、开机自启动和本项目添加的 Codex hooks 已移除。"
print "运行状态保留在 ~/Library/Application Support/GifPigDesktopPet/。"
