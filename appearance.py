"""Independent, validated appearance settings and shared drawing transforms."""
import math
import re
from dataclasses import dataclass
from pathlib import Path
import json
from PIL import Image, ImageColor
from codex_bridge import atomic_json

RANGES = {
    'petScale': (.5, 2, 1), 'dialogScale': (.5, 2, 1), 'taskScale': (.5, 2, 1),
    'dialogOpacity': (.1, 1, 1), 'buttonOpacity': (.1, 1, 1),
    'taskOpacity': (.1, 1, 237/255), 'dialogGap': (-80, 200, 0), 'taskGap': (0, 200, 8),
}
COLORS = ('dialogColor', 'taskColor', 'dialogTextColor', 'buttonTextColor', 'taskTextColor')


class Appearance:
    def __init__(self, path=None, values=None):
        self.path = Path(path) if path else None
        self.values = {key: spec[2] for key, spec in RANGES.items()}
        self.values.update(dict.fromkeys(COLORS))
        if self.path and self.path.exists():
            try:
                self.update(json.loads(self.path.read_text(encoding='utf-8')))
            except (OSError, ValueError, TypeError):
                pass
        if values:
            self.update(values)

    def __getattr__(self, key):
        if key in self.values:
            return self.values[key]
        raise AttributeError(key)

    def update(self, values):
        if not isinstance(values, dict):
            return
        for key, value in values.items():
            if key in RANGES and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                low, high, _ = RANGES[key]
                self.values[key] = max(low, min(high, value))
            elif key in COLORS and (value is None or isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value)):
                self.values[key] = value

    def save(self):
        if self.path:
            atomic_json(self.path, self.values)

    def color(self, key, fallback):
        return ImageColor.getrgb(self.values[key]) + (255,) if self.values[key] else fallback


@dataclass(frozen=True)
class Transform:
    scale: float = 1
    dx: float = 0
    dy: float = 0

    def rect(self, rect):
        return tuple(round(v*self.scale + (self.dx if i%2 == 0 else self.dy)) for i, v in enumerate(rect))

    def paste(self, canvas, layer, offset=(0, 0)):
        bounds = layer.getbbox()
        if not bounds:
            return
        target = self.rect(bounds)
        size = (max(1, target[2]-target[0]), max(1, target[3]-target[1]))
        sprite = layer.crop(bounds)
        if sprite.size != size:
            sprite = sprite.convert('RGBa').resize(size, Image.Resampling.BILINEAR).convert('RGBA')
        canvas.alpha_composite(sprite, (target[0]+offset[0], target[1]+offset[1]))


def transforms(a):
    # Keep the foot fixed. Dialog attaches to the scaled head, but has its own size.
    pet = Transform(a.petScale, 410*(1-a.petScale), 570*(1-a.petScale))
    dialog = Transform(a.dialogScale, 410*(1-a.dialogScale),
                       570-212*a.petScale-358*a.dialogScale-a.dialogGap)
    task = Transform(a.taskScale, 410*(1-a.taskScale),
                     570-137*a.petScale-a.taskGap-425*a.taskScale)
    return pet, dialog, task


def opacity(image, alpha):
    if alpha == 1:
        return image
    image = image.copy()
    image.putalpha(image.getchannel('A').point(lambda v: round(v*alpha)))
    return image
