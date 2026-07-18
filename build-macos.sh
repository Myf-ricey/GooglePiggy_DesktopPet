#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h}"
BUILD_ROOT="$PROJECT_DIR/build/macos"
DIST_DIR="$PROJECT_DIR/dist"
APP_NAME="GooglePiggy.app"
APP_DIR="$BUILD_ROOT/$APP_NAME"
RESOURCES_DIR="$APP_DIR/Contents/Resources"
EXECUTABLE_DIR="$APP_DIR/Contents/MacOS"
VERSION="${VERSION:-0.2.3}"
MACHINE_ARCH="$(uname -m)"
BUILD_UNIVERSAL="${BUILD_UNIVERSAL:-1}"

case "$MACHINE_ARCH" in
    arm64)
        TARGET_ARCH="arm64"
        HOST_RELEASE_ARCH="arm64"
        ;;
    x86_64)
        TARGET_ARCH="x86_64"
        HOST_RELEASE_ARCH="x64"
        ;;
    *)
        print -u2 "Unsupported architecture: $MACHINE_ARCH"
        exit 1
        ;;
esac

if [[ "$BUILD_UNIVERSAL" == "1" ]]; then
    RELEASE_ARCH="universal"
else
    RELEASE_ARCH="$HOST_RELEASE_ARCH"
fi

if [[ -n "${PYTHON:-}" ]]; then
    BUILD_PYTHON="$PYTHON"
elif [[ -x "$PROJECT_DIR/.venv-macos/bin/python" ]]; then
    BUILD_PYTHON="$PROJECT_DIR/.venv-macos/bin/python"
else
    VENV_DIR="$PROJECT_DIR/.venv-macos-build"
    if [[ ! -x "$VENV_DIR/bin/python" ]]; then
        python3 -m venv "$VENV_DIR"
    fi
    "$VENV_DIR/bin/python" -m pip install --upgrade pip
    "$VENV_DIR/bin/python" -m pip install -r "$PROJECT_DIR/requirements-macos-build.txt"
    BUILD_PYTHON="$VENV_DIR/bin/python"
fi

RELEASE_NAME="GooglePiggy-macos-$RELEASE_ARCH"
RELEASE_DIR="$BUILD_ROOT/$RELEASE_NAME"
ZIP_PATH="$DIST_DIR/$RELEASE_NAME.zip"
DMG_PATH="$DIST_DIR/$RELEASE_NAME.dmg"

/bin/rm -rf "$BUILD_ROOT"
mkdir -p "$RESOURCES_DIR" "$EXECUTABLE_DIR" "$DIST_DIR"
/bin/rm -f "$ZIP_PATH" "$DMG_PATH"
MODULE_CACHE_DIR="$BUILD_ROOT/ModuleCache"
mkdir -p "$MODULE_CACHE_DIR"
export CLANG_MODULE_CACHE_PATH="$MODULE_CACHE_DIR"
export SWIFT_MODULE_CACHE_PATH="$MODULE_CACHE_DIR"

cd "$PROJECT_DIR"
"$BUILD_PYTHON" tools/prepare_effect_assets.py
"$BUILD_PYTHON" tools/export_macos_assets.py --output "$RESOURCES_DIR"
"$BUILD_PYTHON" tools/smoke_test.py
mkdir -p "$RESOURCES_DIR/effects"
/usr/bin/ditto assets/effects "$RESOURCES_DIR/effects"

/usr/bin/ditto macos/Info.plist "$APP_DIR/Contents/Info.plist"
/usr/libexec/PlistBuddy \
    -c "Set :CFBundleShortVersionString $VERSION" \
    "$APP_DIR/Contents/Info.plist"

if [[ "$BUILD_UNIVERSAL" == "1" ]]; then
    /usr/bin/swiftc \
        -O \
        -whole-module-optimization \
        -swift-version 5 \
        -target "arm64-apple-macos13.0" \
        -framework AppKit \
        -framework Foundation \
        macos/Sources/GooglePiggy/*.swift \
        -o "$BUILD_ROOT/GooglePiggy-arm64"
    /usr/bin/swiftc \
        -O \
        -whole-module-optimization \
        -swift-version 5 \
        -target "x86_64-apple-macos13.0" \
        -framework AppKit \
        -framework Foundation \
        macos/Sources/GooglePiggy/*.swift \
        -o "$BUILD_ROOT/GooglePiggy-x86_64"
    /usr/bin/lipo \
        -create \
        "$BUILD_ROOT/GooglePiggy-arm64" \
        "$BUILD_ROOT/GooglePiggy-x86_64" \
        -output "$EXECUTABLE_DIR/GooglePiggy"
else
    /usr/bin/swiftc \
        -O \
        -whole-module-optimization \
        -swift-version 5 \
        -target "$TARGET_ARCH-apple-macos13.0" \
        -framework AppKit \
        -framework Foundation \
        macos/Sources/GooglePiggy/*.swift \
        -o "$EXECUTABLE_DIR/GooglePiggy"
fi

chmod 755 "$EXECUTABLE_DIR/GooglePiggy"
/usr/bin/codesign --force --deep --sign - "$APP_DIR"

"$EXECUTABLE_DIR/GooglePiggy" --self-test
"$BUILD_PYTHON" tools/test_macos_release.py \
    --app "$APP_DIR" \
    --source-dir "$PROJECT_DIR"

mkdir -p "$RELEASE_DIR"
/usr/bin/ditto "$APP_DIR" "$RELEASE_DIR/$APP_NAME"
/usr/bin/ditto macos/install.command "$RELEASE_DIR/install.command"
/usr/bin/ditto macos/uninstall.command "$RELEASE_DIR/uninstall.command"
/usr/bin/ditto README-MAC.md "$RELEASE_DIR/README-MAC.md"
chmod 755 "$RELEASE_DIR/install.command" "$RELEASE_DIR/uninstall.command"

/usr/bin/ditto \
    -c \
    -k \
    --norsrc \
    --noextattr \
    --noqtn \
    --noacl \
    --keepParent \
    "$RELEASE_DIR" \
    "$ZIP_PATH"

if [[ "${BUILD_DMG:-1}" == "1" ]]; then
    /usr/bin/hdiutil create \
        -quiet \
        -fs HFS+ \
        -volname "GooglePiggy $VERSION" \
        -srcfolder "$RELEASE_DIR" \
        -format UDZO \
        "$DMG_PATH"
fi

print "App: $APP_DIR"
print "ZIP: $ZIP_PATH"
if [[ -f "$DMG_PATH" ]]; then
    print "DMG: $DMG_PATH"
fi
