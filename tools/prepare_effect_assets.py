#!/usr/bin/env python3
"""Remove baked checkerboard backgrounds from the supplied effect images."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


PROJECT_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_DIR / "assets" / "source-effects"
OUTPUT_DIR = PROJECT_DIR / "assets" / "effects"


def colored_foreground(
    source: Path,
    low_chroma: float,
    full_chroma: float,
    keep_largest: bool,
) -> Image.Image:
    rgb = np.asarray(Image.open(source).convert("RGB"), dtype=np.float32)
    maximum = rgb.max(axis=2)
    minimum = rgb.min(axis=2)
    chroma = maximum - minimum
    alpha = np.clip((chroma - low_chroma) / (full_chroma - low_chroma), 0.0, 1.0)
    alpha[alpha < 0.06] = 0.0

    mask = Image.fromarray(np.uint8(alpha * 255), "L")
    if keep_largest:
        mask = keep_largest_component(mask)
    mask = mask.filter(ImageFilter.GaussianBlur(0.25))
    alpha = np.asarray(mask, dtype=np.float32) / 255.0
    alpha[alpha < 0.025] = 0.0

    background = rgb.mean(axis=2, keepdims=True)
    denominator = np.maximum(alpha[:, :, None], 0.08)
    foreground = np.clip(
        (rgb - (1.0 - alpha[:, :, None]) * background) / denominator,
        0,
        255,
    )
    rgba = np.dstack([np.uint8(foreground), np.uint8(alpha * 255)])
    rgba[rgba[:, :, 3] == 0, :3] = 0
    image = Image.fromarray(rgba, "RGBA")
    bbox = image.getbbox()
    if bbox is None:
        raise ValueError(f"No colored foreground found in {source}")
    left, top, right, bottom = bbox
    padding = 4
    return image.crop(
        (
            max(0, left - padding),
            max(0, top - padding),
            min(image.width, right + padding),
            min(image.height, bottom + padding),
        )
    )


def keep_largest_component(mask: Image.Image) -> Image.Image:
    pixels = np.asarray(mask, dtype=np.uint8)
    visible = pixels > 0
    height, width = visible.shape
    seen = np.zeros_like(visible)
    largest: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            if not visible[y, x] or seen[y, x]:
                continue
            component: list[tuple[int, int]] = []
            stack = [(x, y)]
            seen[y, x] = True
            while stack:
                current_x, current_y = stack.pop()
                component.append((current_x, current_y))
                for next_y in range(max(0, current_y - 1), min(height, current_y + 2)):
                    for next_x in range(max(0, current_x - 1), min(width, current_x + 2)):
                        if visible[next_y, next_x] and not seen[next_y, next_x]:
                            seen[next_y, next_x] = True
                            stack.append((next_x, next_y))
            if len(component) > len(largest):
                largest = component

    output = np.zeros_like(pixels)
    for x, y in largest:
        output[y, x] = pixels[y, x]
    return Image.fromarray(output, "L")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sparkle = colored_foreground(
        SOURCE_DIR / "sparkle-source.webp",
        low_chroma=2.0,
        full_chroma=42.0,
        keep_largest=True,
    )
    firework = colored_foreground(
        SOURCE_DIR / "firework-source.webp",
        low_chroma=4.0,
        full_chroma=38.0,
        keep_largest=False,
    )
    sparkle.save(OUTPUT_DIR / "sparkle.png")
    firework.save(OUTPUT_DIR / "firework.png")
    print(f"sparkle={sparkle.size}, firework={firework.size}")


if __name__ == "__main__":
    main()
