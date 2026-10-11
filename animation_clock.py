"""Manifest clips and actor clocks. Selection never starts an animation."""
from __future__ import annotations
import bisect
import json
import random
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from PIL import Image


class Frames:
    # PNGs are decoded on demand: the complete export would occupy >3 GiB.
    def __init__(self, root, specs):
        self.root, self.specs = root, specs
        self.cache = OrderedDict()

    def __len__(self):
        return len(self.specs)

    def __getitem__(self, index):
        if index not in self.cache:
            with Image.open(self.root / self.specs[index]['file']) as image:
                self.cache[index] = image.convert('RGBA')
        self.cache.move_to_end(index)
        while len(self.cache) > 8:
            self.cache.popitem(last=False)
        return self.cache[index]


class Clip:
    def __init__(self, root, key, spec):
        self.key, self.label, self.source = key, spec['label'], root
        self.frames = Frames(root, spec['frames'])
        self.durations = [f['duration_ms'] for f in spec['frames']]
        self.source_indices = list(range(len(self.frames)))
        self.loop_start = spec.get('loop_start', 0)
        self.ends = []
        total = 0
        for duration in self.durations:
            if duration <= 0:
                raise ValueError('Nonpositive frame duration')
            total += duration
            self.ends.append(total)
        self.total_duration = total

    def frame(self, seconds, hold=False):
        ms = max(0, seconds * 1000)
        if hold:
            ms = min(ms, self.total_duration - .001)
        elif ms >= self.total_duration:
            intro = sum(self.durations[:self.loop_start])
            ms = intro + (ms - intro) % (self.total_duration - intro)
        return min(len(self.frames)-1, bisect.bisect_right(self.ends, ms))


def load_manifest(root: Path):
    data = json.loads((root / 'animation-manifest.json').read_text(encoding='utf-8'))
    if data['format_version'] != 1 or data['window_size'] != 640:
        raise ValueError('Unsupported animation manifest')
    return {key: Clip(root, key, spec) for key, spec in data['animations'].items()}


@dataclass
class Track:
    turn: str
    state: str
    epoch: float
    carried: dict = field(default_factory=dict)
    packing: list = field(default_factory=list)


class AnimationClock:
    def __init__(self, clips, rng=None):
        self.clips, self.rng = clips, rng or random.Random()
        self.tracks = {}

    def update(self, actor, turn, state, now, age=0):
        changed = now - max(0, age)
        track = self.tracks.get(actor)
        if track is None or track.turn != turn:
            self.tracks[actor] = Track(turn, state, changed)
        elif state != track.state:
            transition = max(track.epoch, min(now, changed))
            track.carried[track.state] = track.carried.get(track.state, 0) + transition-track.epoch
            track.state, track.epoch = state, transition

    def position(self, actor, now):
        track = self.tracks.get(actor)
        if track is None:
            return None
        elapsed = track.carried.get(track.state, 0) + max(0, now-track.epoch)
        key, local = track.state, elapsed
        if key == 'packing':
            keys = sorted(k for k in self.clips if k.startswith('packing_'))
            if not track.packing:
                track.packing.append((self.rng.choice(keys), 0))
            while elapsed >= track.packing[-1][1] + self.clips[track.packing[-1][0]].total_duration/1000:
                last, start = track.packing[-1]
                track.packing.append((self.rng.choice(keys), start+self.clips[last].total_duration/1000))
            key, start = track.packing[-1]
            local = elapsed-start
        if key == 'jump' and elapsed >= self.clips[key].total_duration/1000:
            return None
        return key, self.clips[key].frame(local, hold=key in ('jump','question'))
