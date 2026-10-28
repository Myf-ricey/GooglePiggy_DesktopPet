"""Recover straight alpha from the celebration GIF's black-matted outline.

Only the narrow exterior band is eligible. Enclosed eyes, nostrils and mouth,
frame geometry and animation metadata are left untouched. Run this on the
original exported frames, before GIF palette quantization or PNG delivery.
"""

from collections import deque

import numpy as np
from PIL import Image, ImageFilter


def clean_celebration_edges(image: Image.Image) -> Image.Image:
    rgba = np.array(image.convert("RGBA"))
    bounds = image.getchannel("A").getbbox()
    if bounds is None:
        return image.copy()
    left, top, right, bottom = bounds
    left, top = max(0, left - 8), max(0, top - 8)
    right, bottom = min(image.width, right + 8), min(image.height, bottom + 8)
    region = rgba[top:bottom, left:right].copy()
    rgb = region[:, :, :3].astype(float)
    alpha = region[:, :, 3].copy()

    passable = (rgb.max(axis=2) < 245) | (alpha < 245)
    outside = np.zeros(alpha.shape, dtype=bool)
    queue: deque[tuple[int, int]] = deque()
    height, width = alpha.shape
    for y, x in [
        *((0, x) for x in range(width)),
        *((height - 1, x) for x in range(width)),
        *((y, 0) for y in range(height)),
        *((y, width - 1) for y in range(height)),
    ]:
        if passable[y, x] and not outside[y, x]:
            outside[y, x] = True
            queue.append((y, x))
    while queue:
        y, x = queue.popleft()
        for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if (
                0 <= yy < height and 0 <= xx < width
                and passable[yy, xx] and not outside[yy, xx]
            ):
                outside[yy, xx] = True
                queue.append((yy, xx))

    # Five output pixels cover the scaled source antialiasing, while preventing
    # the exterior flood from modifying any interior facial detail.
    band = np.array(Image.fromarray(alpha).filter(ImageFilter.MinFilter(11))) < 32
    eligible = outside & band & (alpha > 0) & (rgb[:, :, 0] < 245)
    for y, x in zip(*np.where(eligible)):
        color = rgb[y, x]
        red = color[0]
        if red < 1:
            region[y, x] = 0
            continue
        neighbors = rgb[max(0, y - 6):y + 7, max(0, x - 6):x + 7]
        neighbor_alpha = alpha[max(0, y - 6):y + 7, max(0, x - 6):x + 7]
        chroma = color[1:] / red
        similar = (
            (np.max(np.abs(
                neighbors[:, :, 1:] / np.maximum(neighbors[:, :, :1], 1) - chroma
            ), axis=2) < 0.09)
            & (neighbor_alpha >= 245) & (neighbors[:, :, 0] > 180)
        )
        target_red = (
            float(neighbors[:, :, 0][similar].max()) if similar.any()
            else (254.0 if chroma[0] > 0.65 else 228.0)
        )
        coverage = min(1.0, red / max(target_red, red))
        if coverage > 0.98:
            continue
        # Move black-matte coverage out of RGB and into alpha. This preserves
        # premultiplied color (appearance over black), with only rounding error.
        region[y, x, :3] = np.clip(np.rint(color / coverage), 0, 255).astype(np.uint8)
        region[y, x, 3] = round(float(alpha[y, x]) * coverage)

    rgba[top:bottom, left:right] = region
    return Image.fromarray(rgba, "RGBA")
