#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h:h}"
VERSION=2.10.0
ARCHIVE="$ROOT/cache/Sparkle-${VERSION}.tar.xz"
DEST="$ROOT/cache/sparkle-${VERSION}"
mkdir -p "$ROOT/cache"
if [[ ! -f "$ARCHIVE" ]]; then
    curl --fail --location --silent --show-error --retry 2 \
        "https://github.com/sparkle-project/Sparkle/releases/download/${VERSION}/Sparkle-${VERSION}.tar.xz" -o "$ARCHIVE.tmp"
    mv "$ARCHIVE.tmp" "$ARCHIVE"
fi
printf '%s  %s\n' c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c "$ARCHIVE" | shasum -a 256 -c - >&2
if [[ ! -d "$DEST/Sparkle.framework" ]]; then
    mkdir -p "$DEST"
    tar -xf "$ARCHIVE" -C "$DEST"
fi
printf '%s\n' "$DEST"
