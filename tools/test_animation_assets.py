"""Lock the repaired native PNGs and exercise the production frame decoder."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from animation_clock import load_manifest


class AnimationAssetTests(unittest.TestCase):
    def test_repaired_asset_identity_and_tail_transparency(self):
        expected = json.loads((ROOT / 'tools/animation-assets-reference.json').read_text())
        resources = ROOT / 'assets/macos-resources'
        digest = hashlib.sha256()
        for name in expected['png_paths']:
            digest.update((name + '\n').encode())
            digest.update(hashlib.sha256((resources / name).read_bytes()).digest())
        self.assertEqual(digest.hexdigest(), expected['png_sha256'], 'Native PNGs differ from the verified contour repair')
        self.assertEqual(hashlib.sha256((resources / 'animation-manifest.json').read_bytes()).hexdigest(), expected['manifest_sha256'])
        for probe in expected['tail_probes']:
            with Image.open(resources / probe['file']) as frame:
                for point in probe['transparent_core_coordinates']:
                    self.assertEqual(frame.getpixel(tuple(point))[3], 0, (probe['file'], point))

    def test_all_manifest_frames_and_cache_reload_keep_exact_rgba(self):
        resources = ROOT / 'assets/macos-resources'
        count = 0
        for clip in load_manifest(resources).values():
            for index, spec in enumerate(clip.frames.specs):
                with Image.open(resources / spec['file']) as image:
                    self.assertEqual(image.mode, 'RGBA')
                    self.assertEqual(image.size, (640, 640))
                    expected = image.tobytes()
                self.assertEqual(clip.frames[index].tobytes(), expected, spec['file'])
                clip.frames.cache.clear()
                self.assertEqual(clip.frames[index].tobytes(), expected, spec['file'])
                count += 1
        self.assertEqual(count, 2167)


if __name__ == '__main__':
    unittest.main()
