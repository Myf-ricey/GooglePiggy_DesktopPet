"""Paste the actual idle sprite onto a simple background; no generated artwork."""
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
source = root / 'assets/icons/piggy-idle-v2.png'
target = source.with_suffix('.ico')
with np.load(root / 'cache/idle.npz') as cache:
    frame = Image.fromarray(cache['frames'][0])
sprite = frame.crop(frame.getchannel('A').getbbox())
source.parent.mkdir(parents=True, exist_ok=True)
sprite.save(source.parent / 'piggy-idle-original.png')
artwork = Image.new('RGBA', (256, 256))
draw = ImageDraw.Draw(artwork)
draw.rounded_rectangle((4, 4, 251, 251), radius=54, fill='#E8F2ED')
# Native-size sprite pasted unchanged: no resizing, recoloring or redrawing.
artwork.alpha_composite(sprite, ((256 - sprite.width) // 2, (256 - sprite.height) // 2))
artwork.save(source)
artwork.save(target, format='ICO', sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
with Image.open(target) as packaged:
    assert packaged.format == 'ICO'
    assert len(packaged.ico.sizes()) == 7
print(target)
