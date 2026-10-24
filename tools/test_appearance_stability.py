"""Observe every presentation operation, not just the final settled anchor."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from animation_clock import load_manifest
from windows_pet import WindowsPet
import pig_pet as win

ROOT=Path(__file__).resolve().parents[1]
CLIPS=load_manifest(ROOT/'assets/macos-resources')


class StabilityTests(unittest.TestCase):
    def test_visible_anchor_never_moves_between_geometry_and_bitmap(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=WindowsPet(CLIPS,Path(tmp)/'report.json',ROOT,Path(tmp)/'status.json',False)
            p.appearance.update({'petScale':1.12})
            p.preview_dialog=True
            p.compose('idle',0)
            p.hwnd=123
            p.scale=1.5
            p.scaled_once=True
            screen=[600,700]
            displayed=[round((410+p.canvas_offset[0])*p.scale),round((570+p.canvas_offset[1])*p.scale)]
            samples=[]
            def snapshot(kind):
                samples.append((kind,screen[0]+displayed[0],screen[1]+displayed[1]))
            def move(hwnd,origin):
                screen[:]=origin
                snapshot('move-old-bitmap')
            def submit(pet,hwnd,pixels,width,height,origin=None):
                if origin is not None:
                    screen[:]=origin
                displayed[:]=[round((410+pet.canvas_offset[0])*pet.scale),round((570+pet.canvas_offset[1])*pet.scale)]
                snapshot('submit-new-bitmap')
            snapshot('initial')
            with patch.object(p,'_window_rect',side_effect=lambda hwnd:(*screen,screen[0]+1000,screen[1]+1000)),patch.object(p,'_set_window_origin',side_effect=move),patch.object(win.user32,'GetDpiForWindow',return_value=144),patch.object(win.PigPet,'_render_layered_window',submit):
                for values in ({'petScale':1.14},{'dialogGap':20},{'dialogGap':0},{'petScale':1.12}):
                    p.appearance.update(values)
                    p._render_current()
            dx=max(abs(s[1]-samples[0][1]) for s in samples)
            dy=max(abs(s[2]-samples[0][2]) for s in samples)
            self.assertLessEqual(max(dx,dy),1,repr(samples))


if __name__=='__main__': unittest.main(verbosity=2)
