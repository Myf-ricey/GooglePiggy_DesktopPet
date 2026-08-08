#!/usr/bin/env python3
"""Export the Windows pet's normalized animation pipeline for the native Mac app."""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
import types
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

EDGE_REVEAL_FRAME_COUNT = 19
EDGE_REVEAL_FRAME_DURATION_MS = 45
EDGE_REVEAL_KEYFRAMES = (
    # progress, upward lift in px, vertical scale
    (0.00, 0.0, 1.00),
    (0.12, 0.0, 0.94),
    (0.32, 11.0, 1.08),
    (0.50, 18.0, 1.03),
    (0.72, 5.0, 0.95),
    (0.84, 2.0, 1.03),
    (1.00, 0.0, 1.00),
)
EDGE_TAIL_CANVAS_SIZE = 68
EDGE_TAIL_MAX_SUBJECT_SIZE = 60
EDGE_TAIL_MASK_SCALE = 4
EDGE_TAIL_COMMON_CLOCKWISE_TILT_DEGREES = 55
EDGE_TAIL_LEFT_CLOCKWISE_TILT_DEGREES = 50


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
    bbox = frame.getchannel("A").getbbox()
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


def edge_reveal_motion(progress: float) -> tuple[float, float]:
    """Interpolate one soft bounce using smooth, art-directable keyframes."""

    progress = min(1.0, max(0.0, progress))
    for start, end in zip(
        EDGE_REVEAL_KEYFRAMES[:-1],
        EDGE_REVEAL_KEYFRAMES[1:],
        strict=True,
    ):
        if progress > end[0]:
            continue
        span = max(0.0001, end[0] - start[0])
        local = (progress - start[0]) / span
        eased = local * local * (3.0 - 2.0 * local)
        lift = start[1] + (end[1] - start[1]) * eased
        scale_y = start[2] + (end[2] - start[2]) * eased
        return lift, scale_y
    return EDGE_REVEAL_KEYFRAMES[-1][1:]


def make_edge_reveal_animation(pig_pet, base):
    """Create a one-shot idle-style bounce for leaving the screen edge."""

    base_frame = base.frames[0]
    subject_box = base_frame.getchannel("A").getbbox()
    if subject_box is None:
        raise ValueError("The selected edge reveal frame is empty")
    subject = base_frame.crop(subject_box)
    frames: list[Image.Image] = []
    denominator = max(1, EDGE_REVEAL_FRAME_COUNT - 1)
    for index in range(EDGE_REVEAL_FRAME_COUNT):
        progress = index / denominator
        lift, scale_y = edge_reveal_motion(progress)
        resized_height = max(1, round(subject.height * scale_y))
        resized = subject.resize(
            (subject.width, resized_height),
            Image.Resampling.LANCZOS,
        )
        canvas = Image.new("RGBA", base_frame.size, (0, 0, 0, 0))
        bottom = subject_box[3] - round(lift)
        top = bottom - resized_height
        canvas.alpha_composite(resized, (subject_box[0], top))
        frames.append(pig_pet.clear_transparent_rgb(canvas))

    return pig_pet.Animation(
        key="edge_reveal",
        label="触边跳出",
        source=base.source,
        frames=frames,
        durations=[EDGE_REVEAL_FRAME_DURATION_MS] * len(frames),
        source_indices=[0] * len(frames),
    )


def save_animation_gif(animation, output_path: Path) -> None:
    """Save an inspectable GIF alongside the PNG sequence used by AppKit."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    animation.frames[0].save(
        output_path,
        format="GIF",
        save_all=True,
        append_images=animation.frames[1:],
        duration=animation.durations,
        loop=0,
        disposal=2,
        optimize=True,
    )


def make_edge_tail_assets(frame: Image.Image, output_dir: Path) -> None:
    """Export the flat pig's curled tail for each desktop edge.

    The source crop includes the curl and a generous rump attachment. Both cut
    sides are closed with rounded, outlined curves before the art is tilted, so
    direction-specific rotation cannot turn a rectangular crop seam into view.
    Field feedback currently sets the left pose to 50° clockwise and the other
    poses to 55° clockwise. Right, top, and bottom still share exact 90°
    relationships so the Windows port can reproduce them deterministically.
    """

    bbox = frame.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("The selected tail frame is empty")
    body_width = bbox[2] - bbox[0]
    body_height = bbox[3] - bbox[1]
    crop_box = (
        max(0, bbox[2] - round(body_width * 0.43)),
        max(0, bbox[1] - round(body_height * 0.09)),
        min(frame.width, bbox[2] + round(body_width * 0.10)),
        min(frame.height, bbox[1] + round(body_height * 0.62)),
    )
    tail = frame.crop(crop_box)

    # The pig body continues through the crop's left and bottom edges. Close
    # both with curves before applying the directional tilt; this keeps every
    # rotated orientation free of straight crop seams.
    curve_center_y = bbox[1] + body_height * 0.23
    curve_tip_x = bbox[2] - body_width * 0.36
    curve_half_height = body_height * 0.24
    curve_reach = body_width * 0.14
    mask_size = (
        tail.width * EDGE_TAIL_MASK_SCALE,
        tail.height * EDGE_TAIL_MASK_SCALE,
    )
    outer_curve_points: list[tuple[float, float]] = []
    for scaled_y in range(mask_size[1] + 1):
        source_y = crop_box[1] + scaled_y / EDGE_TAIL_MASK_SCALE
        normalized_y = abs(
            (source_y - curve_center_y) / curve_half_height
        )
        source_x = curve_tip_x + curve_reach * normalized_y**1.5
        outer_curve_points.append((
            (source_x - crop_box[0]) * EDGE_TAIL_MASK_SCALE,
            scaled_y,
        ))

    outer_mask_large = Image.new("L", mask_size, 0)
    ImageDraw.Draw(outer_mask_large).polygon(
        outer_curve_points
        + [
            (mask_size[0], mask_size[1]),
            (mask_size[0], 0),
        ],
        fill=255,
    )

    attachment_center_x = bbox[2] - body_width * 0.14
    attachment_tip_y = bbox[1] + body_height * 0.56
    attachment_half_width = body_width * 0.27
    attachment_reach = body_height * 0.13
    attachment_curve_points: list[tuple[float, float]] = []
    for scaled_x in range(mask_size[0] + 1):
        source_x = crop_box[0] + scaled_x / EDGE_TAIL_MASK_SCALE
        normalized_x = abs(
            (source_x - attachment_center_x) / attachment_half_width
        )
        source_y = attachment_tip_y - attachment_reach * normalized_x**1.5
        attachment_curve_points.append((
            scaled_x,
            (source_y - crop_box[1]) * EDGE_TAIL_MASK_SCALE,
        ))

    attachment_mask_large = Image.new("L", mask_size, 0)
    ImageDraw.Draw(attachment_mask_large).polygon(
        [
            (0, 0),
            (mask_size[0], 0),
        ]
        + list(reversed(attachment_curve_points)),
        fill=255,
    )
    rump_mask_large = ImageChops.multiply(
        outer_mask_large,
        attachment_mask_large,
    )
    rump_mask = rump_mask_large.resize(tail.size, Image.Resampling.LANCZOS)
    source_alpha = tail.getchannel("A")
    tail_alpha = ImageChops.multiply(source_alpha, rump_mask)
    tail.putalpha(tail_alpha)

    # Continue the source artwork's dark outline along both new rump curves.
    # They read as a natural cartoon silhouette at every rotated angle.
    outline_large = Image.new("L", mask_size, 0)
    outline_draw = ImageDraw.Draw(outline_large)
    outline_draw.line(
        outer_curve_points,
        fill=255,
        width=2 * EDGE_TAIL_MASK_SCALE,
    )
    outline_draw.line(
        attachment_curve_points,
        fill=255,
        width=2 * EDGE_TAIL_MASK_SCALE,
    )
    outline = outline_large.resize(tail.size, Image.Resampling.LANCZOS)
    solid_source = source_alpha.point(
        lambda value: 255 if value >= 192 else 0
    )
    outline = ImageChops.multiply(outline, solid_source)
    outline = ImageChops.multiply(outline, tail_alpha)
    outline_ink = Image.new("RGBA", tail.size, (45, 45, 43, 255))
    tail = Image.composite(outline_ink, tail, outline)
    tail.putalpha(tail_alpha)

    visible = tail.getchannel("A").getbbox()
    if visible is None:
        raise ValueError("Generated rounded tail crop is empty")
    tail = tail.crop(visible)
    scale = min(
        1.10,
        EDGE_TAIL_MAX_SUBJECT_SIZE / tail.width,
        EDGE_TAIL_MAX_SUBJECT_SIZE / tail.height,
    )
    tail = tail.resize(
        (
            max(1, round(tail.width * scale)),
            max(1, round(tail.height * scale)),
        ),
        Image.Resampling.LANCZOS,
    )
    # Right, top, and bottom use the 55° common pose. Left is tuned to 50°, so
    # it must be tilted independently from its
    # unturned 90° base instead of being derived from the common pose.
    unturned_bottom_pose = tail.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    bottom_pose = unturned_bottom_pose.rotate(
        -EDGE_TAIL_COMMON_CLOCKWISE_TILT_DEGREES,
        resample=Image.Resampling.BICUBIC,
        expand=True,
    )
    bottom_visible = bottom_pose.getchannel("A").getbbox()
    if bottom_visible is None:
        raise ValueError("Generated tilted bottom tail is empty")
    bottom_pose = bottom_pose.crop(bottom_visible)

    unturned_left_pose = unturned_bottom_pose.transpose(
        Image.Transpose.ROTATE_270
    )
    left_pose = unturned_left_pose.rotate(
        -EDGE_TAIL_LEFT_CLOCKWISE_TILT_DEGREES,
        resample=Image.Resampling.BICUBIC,
        expand=True,
    )
    left_visible = left_pose.getchannel("A").getbbox()
    if left_visible is None:
        raise ValueError("Generated tilted left tail is empty")
    left_pose = left_pose.crop(left_visible)

    oriented = {
        "bottom": bottom_pose,
        "right": bottom_pose.transpose(Image.Transpose.ROTATE_90),
        "top": bottom_pose.transpose(Image.Transpose.ROTATE_180),
        "left": left_pose,
    }
    assets: dict[str, Image.Image] = {}
    for edge, image in oriented.items():
        visible = image.getchannel("A").getbbox()
        if visible is None:
            raise ValueError(f"Generated edge tail is empty: {edge}")
        image = image.crop(visible)
        canvas = Image.new(
            "RGBA",
            (EDGE_TAIL_CANVAS_SIZE, EDGE_TAIL_CANVAS_SIZE),
            (0, 0, 0, 0),
        )
        if edge == "left":
            position = (0, (canvas.height - image.height) // 2)
        elif edge == "right":
            position = (
                canvas.width - image.width,
                (canvas.height - image.height) // 2,
            )
        elif edge == "top":
            position = ((canvas.width - image.width) // 2, 0)
        else:
            position = (
                (canvas.width - image.width) // 2,
                canvas.height - image.height,
            )
        canvas.alpha_composite(image, position)
        assets[edge] = canvas
    output_dir.mkdir(parents=True, exist_ok=True)
    for edge, image in assets.items():
        image.save(output_dir / f"{edge}.png", optimize=True)


def export(output_dir: Path) -> None:
    pig_pet = import_asset_pipeline()
    source_dir = PROJECT_DIR / "assets" / "source-gifs"
    cache_dir = PROJECT_DIR / "cache"
    animations = pig_pet.load_animation_cache(cache_dir, source_dir)
    if animations is None:
        animations = pig_pet.build_animations(source_dir)
        pig_pet.save_animation_cache(animations, cache_dir, source_dir)
    mac_animations = dict(animations)
    mac_animations["edge_reveal"] = make_edge_reveal_animation(
        pig_pet,
        animations["idle"],
    )

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

    for key, animation in mac_animations.items():
        frame_dir = animation_root / key
        frame_dir.mkdir(parents=True, exist_ok=True)
        frame_records: list[dict[str, object]] = []
        for index, (frame, duration) in enumerate(
            zip(animation.frames, animation.durations, strict=True)
        ):
            relative_path = Path("animations") / key / f"{index:03d}.png"
            frame.save(output_dir / relative_path, optimize=True)
            visible_bounds = frame.getchannel("A").getbbox()
            if visible_bounds is None:
                raise ValueError(f"Animation frame is empty: {relative_path}")
            frame_records.append(
                {
                    "file": relative_path.as_posix(),
                    "duration_ms": int(duration),
                    # [left, top, right, bottom] in 640px window coordinates.
                    "visible_bounds": list(visible_bounds),
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
    save_animation_gif(
        mac_animations["edge_reveal"],
        animation_root / "edge-reveal.gif",
    )
    make_edge_tail_assets(
        animations["flat"].frames[0],
        output_dir / "edge-tail",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.output.expanduser().resolve())


if __name__ == "__main__":
    main()
