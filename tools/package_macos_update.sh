#!/bin/zsh
# Run AFTER build-macos.sh. Upload both generated files to the matching Release.
set -euo pipefail
ROOT="${0:A:h:h}"
APP="$ROOT/build/macos/GooglePiggy.app"
VERSION=$(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$APP/Contents/Info.plist")
OUT="$ROOT/dist/macos-update-$VERSION"
SPARKLE="$("$ROOT/tools/prepare_sparkle.sh")"
mkdir -p "$OUT"
ARCHIVE="$OUT/GooglePiggy-macos-update-$VERSION.zip"
if [[ -e "$ARCHIVE" ]]; then
    print -u2 "Refusing to overwrite signed update archive: $ARCHIVE. Use a new version or remove this local build explicitly."
    exit 1
fi
codesign --verify --deep --strict "$APP"
/Applications/Keka.app/Contents/MacOS/Keka --cli 7zz a -tzip -snl "$ARCHIVE" "$APP"
/Applications/Keka.app/Contents/MacOS/Keka --cli 7zz t "$ARCHIVE"
cp "$ROOT/RELEASE-NOTES-v${VERSION}-macos.md" "$OUT/GooglePiggy-macos-update-$VERSION.md"
"$SPARKLE/bin/generate_appcast" --account GooglePiggyDesktopPet --maximum-deltas 0 --embed-release-notes \
    --download-url-prefix "https://github.com/Myf-ricey/GooglePiggy_DesktopPet/releases/download/v${VERSION}-macos/" "$OUT"
"$SPARKLE/bin/sign_update" --account GooglePiggyDesktopPet --verify "$OUT/appcast.xml"
print "Upload $ARCHIVE and $OUT/appcast.xml before publishing v${VERSION}-macos."
