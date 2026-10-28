"""Flat pig skin with one alpha edge, preserving faces and prop artwork.

This is a deterministic post-export operation on the project's RGBA frames.
It does not redraw poses or change clip timing. RGB is constant in the skin;
only the outermost antialiasing changes opacity. A wide, face-excluded matte
check also clears the inverted jump tail holes missed by narrower edge tests.
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter


SKIN_COLOR = np.array([255, 210, 177], dtype=np.uint8)


def component_labels(mask: np.ndarray) -> np.ndarray:
    """Label four-connected horizontal runs without a SciPy dependency."""
    height, width = mask.shape
    labels = np.zeros((height, width), dtype=np.int32)
    parents = [0]
    previous = []

    def find(label):
        while parents[label] != label:
            parents[label] = parents[parents[label]]
            label = parents[label]
        return label

    for y in range(height):
        transitions = np.flatnonzero(np.diff(
            np.r_[False, mask[y], False].astype(np.int8)))
        current = []
        for left, right in zip(transitions[::2], transitions[1::2]):
            label = len(parents)
            parents.append(label)
            labels[y, left:right] = label
            current.append((left, right, label))
            for old_left, old_right, old_label in previous:
                if old_right <= left:
                    continue
                if old_left >= right:
                    break
                a, b = find(label), find(old_label)
                if a != b:
                    parents[a] = b
        previous = current
    lookup = np.array([find(i) for i in range(len(parents))])
    return lookup[labels]


def expand(mask: np.ndarray, size: int) -> np.ndarray:
    return np.array(Image.fromarray(np.uint8(mask) * 255).filter(
        ImageFilter.MaxFilter(size))) > 0


@dataclass
class ContourResult:
    image: Image.Image
    skin: np.ndarray
    cleared_matte: np.ndarray
    protected: np.ndarray


def uniform_pig_contour(image: Image.Image, key: str) -> ContourResult:
    image = image.convert("RGBA")
    source = np.array(image)
    bounds = image.getbbox()
    empty = np.zeros(source.shape[:2], dtype=bool)
    if bounds is None:
        return ContourResult(image.copy(), empty, empty.copy(), empty.copy())

    left, top, right, bottom = bounds
    left, top = max(0, left - 5), max(0, top - 5)
    right, bottom = min(image.width, right + 5), min(image.height, bottom + 5)
    pixels = source[top:bottom, left:right].copy()
    rgb = pixels[:, :, :3].astype(float)
    alpha = pixels[:, :, 3].copy()
    red, green, blue = rgb.transpose(2, 0, 1)
    flesh_hue = (
        (red > 35) & (green > red * 0.68) & (green < red * 0.98)
        & (blue > green * 0.70) & (blue < green * 0.97)
        & (red - green > 8)
    )
    matte = np.zeros(alpha.shape, dtype=bool)

    if key == "jump":
        nose = ((alpha > 200) & (red > 220) & (green > 80)
                & (green < 160) & (blue < 190) & (red - green > 80))
        labels = component_labels(nose)
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        if not sizes.any():
            raise ValueError("Jump frame has no identifiable pink nose")
        ys, xs = np.where(labels == int(sizes.argmax()))
        face = np.zeros(alpha.shape, dtype=bool)
        face[max(0, ys.min() - 30):min(alpha.shape[0], ys.max() + 31),
             max(0, xs.min() - 30):min(alpha.shape[1], xs.max() + 31)] = True
        near_exterior = np.array(Image.fromarray(alpha).filter(
            ImageFilter.MinFilter(27))) < 32
        neutral = ((rgb.max(axis=2) - rgb.min(axis=2) < 20)
                   & (rgb.max(axis=2) < 220))
        matte = ((alpha > 0) & ~face & near_exterior
                 & ((flesh_hue & (red < 235)) | neutral))
        alpha[matte] = 0
        pixels[matte] = 0

    active = alpha > 0
    seed = (np.linalg.norm(rgb - SKIN_COLOR, axis=2) < 18) & (alpha > 180)
    labels = component_labels(flesh_hue & active)
    sizes = np.bincount(labels.ravel())
    seeds = np.bincount(labels.ravel(), weights=seed.ravel(), minlength=len(sizes))
    keep = (sizes >= 12) & (seeds >= 4)
    keep[0] = False
    if key == "reading" and keep.any():
        # The small pig printed on the book cover is prop artwork, not skin.
        candidates = np.flatnonzero(keep)
        largest = candidates[np.argmax(sizes[candidates])]
        keep[:] = False
        keep[largest] = True
    skin = keep[labels]
    pale_edge = ((red > 170) & (green > 120) & (blue > 90)
                 & (red >= green - 2) & (green >= blue - 3)
                 & (blue > green * 0.7) & (green > red * 0.65))
    pink = (blue >= green * 0.95) & (green < red * 0.76) & (red - green > 20)
    skin |= expand(skin, 5) & active & pale_edge & ~pink
    protected = expand((rgb.max(axis=2) < 135) & (alpha > 128), 5)
    protected |= expand(pink & (red > 180) & active, 3)
    if key == "reading":
        protected |= (labels > 0) & ~keep[labels]
    skin &= ~protected

    # Keep source subpixel coverage rather than thresholding the silhouette,
    # which would turn a smooth contour into a staircase at native pet size.
    soft = np.array(Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(0.35)))
    skin |= expand(skin, 3) & matte & (soft > 0) & ~protected
    pixels[:, :, :3][skin] = SKIN_COLOR
    pixels[:, :, 3][skin] = soft[skin]
    # A dark filled hole must become genuinely transparent, not a pale painted
    # spot. Feathering is permitted only along its lighter boundary pixels.
    pixels[matte & (red < 160)] = 0
    newly_transparent = ((pixels[:, :, 3] == 0)
                         & (source[top:bottom, left:right, 3] > 0))
    pixels[newly_transparent] = 0
    source[top:bottom, left:right] = pixels

    def full(mask):
        result = empty.copy()
        result[top:bottom, left:right] = mask
        return result

    return ContourResult(Image.fromarray(source, "RGBA"), full(skin),
                         full(matte), full(protected))
