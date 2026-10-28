"""Repair confirmed pig-edge matte defects in original normalized exports.

Question marks and all facial details are protected. The question clip has a
neutral dark contour and filled tail holes; jump only needs its remaining tiny
tail gaps repaired after clean_celebration_edges. Do not run on other clips:
their dark prop outlines are intentional. Inputs are straight-alpha RGBA.
"""

from collections.abc import Iterator

import numpy as np
from PIL import Image, ImageFilter


def components(mask: np.ndarray) -> Iterator[np.ndarray]:
    """Four-connected foreground coordinates, without an extra dependency."""
    seen = np.zeros(mask.shape, dtype=bool)
    height, width = mask.shape
    for y0, x0 in zip(*np.where(mask)):
        if seen[y0, x0]:
            continue
        todo = [(y0, x0)]
        seen[y0, x0] = True
        points = []
        while todo:
            y, x = todo.pop()
            points.append((y, x))
            for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if (0 <= yy < height and 0 <= xx < width
                        and mask[yy, xx] and not seen[yy, xx]):
                    seen[yy, xx] = True
                    todo.append((yy, xx))
        yield np.array(points)


def repair_question_alpha(image: Image.Image) -> Image.Image:
    return _repair(image, question=True)


def repair_jump_tail_gaps(image: Image.Image) -> Image.Image:
    return _repair(image, question=False)


def _repair(image: Image.Image, *, question: bool) -> Image.Image:
    original = np.array(image.convert("RGBA"))
    result = original.copy()
    alpha = original[:, :, 3]
    rgb = original[:, :, :3].astype(float)
    tail = np.zeros(alpha.shape, dtype=bool)
    if not alpha.any():
        return image.copy()

    if question:
        # The pig is the largest component; the detached black '?' stays exact.
        body = max(components(alpha > 20), key=len)
        main = np.zeros(alpha.shape, dtype=bool)
        main[body[:, 0], body[:, 1]] = True
        ys, xs = np.where(main)
        left, right = xs.min(), xs.max() + 1
        top, bottom = ys.min(), ys.max() + 1
        region = np.zeros(alpha.shape, dtype=bool)
        region[top:round(top + (bottom - top) * 0.28),
               round(left + (right - left) * 0.80):right] = True
        tail = main & region & (rgb.max(axis=2) < 160) & (alpha > 0)
    else:
        main = alpha > 0
        band = np.array(Image.fromarray(alpha).filter(ImageFilter.MinFilter(11))) < 24
        # In these 61 reviewed frames, the tiny dark islands in the thin tail
        # are within five pixels of transparency. Eyes/nostrils are larger and
        # farther inside; closed eyelids and mouth are also outside this band.
        for points in components((rgb.max(axis=2) < 120) & (alpha > 50)):
            ys, xs = points[:, 0], points[:, 1]
            if len(points) < 40 and band[ys, xs].mean() > 0.75:
                tail[ys, xs] = True

    result[tail] = 0
    coverage_alpha = result[:, :, 3].copy()
    band = np.array(Image.fromarray(coverage_alpha).filter(ImageFilter.MinFilter(11))) < 32
    eligible = main & band & (coverage_alpha > 0) & (rgb[:, :, 0] < 245)
    if not question:
        near_tail = np.array(Image.fromarray(np.uint8(tail) * 255).filter(
            ImageFilter.MaxFilter(7))) > 0
        eligible &= near_tail

    height, width = alpha.shape
    for y, x in zip(*np.where(eligible)):
        color = rgb[y, x]
        top, left = max(0, y - 6), max(0, x - 6)
        neighbors = rgb[top:min(height, y + 7), left:min(width, x + 7)]
        neighbor_alpha = alpha[top:min(height, y + 7), left:min(width, x + 7)]
        pink = ((neighbors[:, :, 0] > 200)
                & (neighbors[:, :, 0] - neighbors[:, :, 1] > 90)
                & (neighbors[:, :, 2] > neighbors[:, :, 1] * 1.2))
        reliable = (((neighbors[:, :, 0] >= 245) | pink)
                    & (neighbor_alpha >= 245)
                    & (neighbors[:, :, 0] - neighbors[:, :, 2] > 30))
        if reliable.any():
            ys, xs = np.where(reliable)
            nearest = np.argmin((ys + top - y) ** 2 + (xs + left - x) ** 2)
            foreground = neighbors[ys[nearest], xs[nearest]]
        else:
            foreground = np.array([254.0, 210.0, 177.0])

        # A neutral dark matte contributes no chroma. Estimate true colored
        # coverage from chroma, rather than turning gray border pixels white.
        foreground_chroma = foreground - foreground.mean()
        color_chroma = color - color.mean()
        coverage = float(np.clip(np.dot(foreground_chroma, color_chroma) /
            max(np.dot(foreground_chroma, foreground_chroma), 1), 0, 1))
        if coverage > 0.98:
            continue
        result[y, x, :3] = foreground.astype(np.uint8)
        result[y, x, 3] = round(float(alpha[y, x]) * coverage)
        if result[y, x, 3] < 5:
            result[y, x] = 0
    return Image.fromarray(result, "RGBA")
