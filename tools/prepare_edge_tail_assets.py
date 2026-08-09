"""Generate the four transparent tail assets used by the Windows edge mode."""

from __future__ import annotations

import argparse
import ctypes
import sys
import types
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw


PROJECT_DIR = Path(__file__).resolve().parents[1]
EDGE_TAIL_CANVAS_SIZE = 68
EDGE_TAIL_MAX_SUBJECT_SIZE = 60
EDGE_TAIL_MASK_SCALE = 4
EDGE_TAIL_COMMON_CLOCKWISE_TILT_DEGREES = 55
EDGE_TAIL_LEFT_CLOCKWISE_TILT_DEGREES = 50


class _UnusedWinFunction:
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
    if sys.platform != "win32":
        sys.modules.setdefault("winreg", types.SimpleNamespace())
        if not hasattr(ctypes, "WINFUNCTYPE"):
            ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE  # type: ignore[attr-defined]
        if not hasattr(ctypes, "windll"):
            ctypes.windll = _UnusedWindll()  # type: ignore[attr-defined]
    sys.path.insert(0, str(PROJECT_DIR))
    import pig_pet

    return pig_pet


def make_edge_tail_assets(frame: Image.Image, output_dir: Path) -> None:
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
        normalized_y = abs((source_y - curve_center_y) / curve_half_height)
        source_x = curve_tip_x + curve_reach * normalized_y**1.5
        outer_curve_points.append(
            ((source_x - crop_box[0]) * EDGE_TAIL_MASK_SCALE, scaled_y)
        )

    outer_mask_large = Image.new("L", mask_size, 0)
    ImageDraw.Draw(outer_mask_large).polygon(
        outer_curve_points
        + [(mask_size[0], mask_size[1]), (mask_size[0], 0)],
        fill=255,
    )

    attachment_center_x = bbox[2] - body_width * 0.14
    attachment_tip_y = bbox[1] + body_height * 0.56
    attachment_half_width = body_width * 0.27
    attachment_reach = body_height * 0.13
    attachment_curve_points: list[tuple[float, float]] = []
    for scaled_x in range(mask_size[0] + 1):
        source_x = crop_box[0] + scaled_x / EDGE_TAIL_MASK_SCALE
        normalized_x = abs((source_x - attachment_center_x) / attachment_half_width)
        source_y = attachment_tip_y - attachment_reach * normalized_x**1.5
        attachment_curve_points.append(
            (scaled_x, (source_y - crop_box[1]) * EDGE_TAIL_MASK_SCALE)
        )

    attachment_mask_large = Image.new("L", mask_size, 0)
    ImageDraw.Draw(attachment_mask_large).polygon(
        [(0, 0), (mask_size[0], 0)] + list(reversed(attachment_curve_points)),
        fill=255,
    )
    rump_mask_large = ImageChops.multiply(outer_mask_large, attachment_mask_large)
    rump_mask = rump_mask_large.resize(tail.size, Image.Resampling.LANCZOS)
    source_alpha = tail.getchannel("A")
    tail_alpha = ImageChops.multiply(source_alpha, rump_mask)
    tail.putalpha(tail_alpha)

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
    solid_source = source_alpha.point(lambda value: 255 if value >= 192 else 0)
    outline = ImageChops.multiply(outline, solid_source)
    outline = ImageChops.multiply(outline, tail_alpha)
    tail = Image.composite(
        Image.new("RGBA", tail.size, (45, 45, 43, 255)),
        tail,
        outline,
    )
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
        (max(1, round(tail.width * scale)), max(1, round(tail.height * scale))),
        Image.Resampling.LANCZOS,
    )

    unturned_bottom_pose = tail.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    bottom_pose = unturned_bottom_pose.rotate(
        -EDGE_TAIL_COMMON_CLOCKWISE_TILT_DEGREES,
        resample=Image.Resampling.BICUBIC,
        expand=True,
    )
    bottom_visible = bottom_pose.getchannel("A").getbbox()
    if bottom_visible is None:
        raise ValueError("Generated bottom tail is empty")
    bottom_pose = bottom_pose.crop(bottom_visible)

    unturned_left_pose = unturned_bottom_pose.transpose(Image.Transpose.ROTATE_270)
    left_pose = unturned_left_pose.rotate(
        -EDGE_TAIL_LEFT_CLOCKWISE_TILT_DEGREES,
        resample=Image.Resampling.BICUBIC,
        expand=True,
    )
    left_visible = left_pose.getchannel("A").getbbox()
    if left_visible is None:
        raise ValueError("Generated left tail is empty")
    left_pose = left_pose.crop(left_visible)

    oriented = {
        "bottom": bottom_pose,
        "right": bottom_pose.transpose(Image.Transpose.ROTATE_90),
        "top": bottom_pose.transpose(Image.Transpose.ROTATE_180),
        "left": left_pose,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
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
            position = (canvas.width - image.width, (canvas.height - image.height) // 2)
        elif edge == "top":
            position = ((canvas.width - image.width) // 2, 0)
        else:
            position = ((canvas.width - image.width) // 2, canvas.height - image.height)
        canvas.alpha_composite(image, position)
        canvas.save(output_dir / f"{edge}.png", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_DIR / "assets" / "edge-tail",
    )
    args = parser.parse_args()
    pig_pet = import_asset_pipeline()
    source_dir = PROJECT_DIR / "assets" / "source-gifs"
    animations = pig_pet.load_animation_cache(PROJECT_DIR / "cache", source_dir)
    if animations is None:
        animations = pig_pet.build_animations(source_dir)
        pig_pet.save_animation_cache(animations, PROJECT_DIR / "cache", source_dir)
    make_edge_tail_assets(animations["flat"].frames[0], args.output.resolve())


if __name__ == "__main__":
    main()
