#!/usr/bin/env python3
"""Export the Windows pet's normalized animation pipeline for the native Mac app."""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
import types
from pathlib import Path

from PIL import Image, ImageDraw


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))


class _UnusedWinFunction:
    """Accept ctypes signature declarations without invoking Windows APIs."""

    argtypes: object = None
    restype: object = None

    def __call__(self, *_args: object, **_kwargs: object) -> int:
        return 0


class _UnusedWinLibrary:
    def __getattr__(self, name: str) -> _UnusedWinFunction:
        function = _UnusedWinFunction()
        setattr(self, name, function)
        return function


class _UnusedWindll:
    def __getattr__(self, name: str) -> _UnusedWinLibrary:
        library = _UnusedWinLibrary()
        setattr(self, name, library)
        return library


def import_asset_pipeline():
    """Import pig_pet's platform-neutral asset functions on a non-Windows host."""

    if sys.platform != "win32":
        sys.modules.setdefault("winreg", types.SimpleNamespace())
        if not hasattr(ctypes, "WINFUNCTYPE"):
            ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE  # type: ignore[attr-defined]
        if not hasattr(ctypes, "windll"):
            ctypes.windll = _UnusedWindll()  # type: ignore[attr-defined]
    import pig_pet

    return pig_pet


def make_icon(frame: Image.Image, output_path: Path) -> None:
    bbox = frame.getbbox()
    if bbox is None:
        raise ValueError("The selected icon frame is empty")
    pig = frame.crop(bbox)
    canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle(
        (36, 36, 988, 988),
        radius=218,
        fill=(255, 242, 247, 255),
        outline=(236, 70, 142, 255),
        width=28,
    )
    maximum = 760
    scale = min(maximum / pig.width, maximum / pig.height)
    size = (max(1, round(pig.width * scale)), max(1, round(pig.height * scale)))
    pig = pig.resize(size, Image.Resampling.LANCZOS)
    canvas.alpha_composite(
        pig,
        ((canvas.width - pig.width) // 2, (canvas.height - pig.height) // 2 + 24),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, optimize=True)
    canvas.save(output_path.with_name("AppIcon.icns"), format="ICNS")


def export(output_dir: Path) -> None:
    pig_pet = import_asset_pipeline()
    source_dir = PROJECT_DIR / "assets" / "source-gifs"
    cache_dir = PROJECT_DIR / "cache"
    animations = pig_pet.load_animation_cache(cache_dir, source_dir)
    if animations is None:
        animations = pig_pet.build_animations(source_dir)
        pig_pet.save_animation_cache(animations, cache_dir, source_dir)

    animation_root = output_dir / "animations"
    manifest: dict[str, object] = {
        "format_version": 1,
        "window_size": pig_pet.WINDOW_SIZE,
        "body_anchor_x": pig_pet.BODY_ANCHOR_X,
        "body_anchor_bottom": pig_pet.BODY_ANCHOR_BOTTOM,
        "animations": {},
    }
    animation_manifest = manifest["animations"]
    assert isinstance(animation_manifest, dict)

    for key, animation in animations.items():
        frame_dir = animation_root / key
        frame_dir.mkdir(parents=True, exist_ok=True)
        frame_records: list[dict[str, object]] = []
        for index, (frame, duration) in enumerate(
            zip(animation.frames, animation.durations, strict=True)
        ):
            relative_path = Path("animations") / key / f"{index:03d}.png"
            frame.save(output_dir / relative_path, optimize=True)
            frame_records.append(
                {
                    "file": relative_path.as_posix(),
                    "duration_ms": int(duration),
                }
            )
        animation_manifest[key] = {
            "label": animation.label,
            "source": animation.source.name,
            "frames": frame_records,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "animation-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    make_icon(animations["flat"].frames[0], output_dir / "AppIcon-1024.png")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.output.expanduser().resolve())


if __name__ == "__main__":
    main()
