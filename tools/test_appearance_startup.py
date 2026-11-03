"""The first cropped bitmap must preserve the original startup foot anchor."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from animation_clock import load_manifest
import pig_pet as win
from windows_pet import WindowsPet

ROOT=Path(__file__).resolve().parents[1]
CLIPS=load_manifest(ROOT/'assets/macos-resources')


def first_frame(work=(0,0,1920,1040), pet_scale=.8, dpi=1):
    with tempfile.TemporaryDirectory() as tmp:
        pet=WindowsPet(CLIPS,Path(tmp)/'report.json',ROOT,Path(tmp)/'status.json',False)
        pet.appearance.update({'petScale':pet_scale})
        pet.hwnd=123
        start=(work[2]-640-36,work[3]-640-36)
        submitted=[]
        def submit(p,hwnd,pixels,width,height,origin=None):
            image=Image.frombytes('RGBA',(width,height),pixels,'raw','BGRA')
            submitted.append((origin,width,height,image.getchannel('A').getbbox()))
        with patch.object(pet,'_window_rect',return_value=(*start,start[0]+640,start[1]+640)), \
                patch.object(win.user32,'GetDpiForWindow',return_value=round(96*dpi)), \
                patch.object(win.PigPet,'_render_layered_window',submit):
            pet._render_current()
        origin,width,height,bbox=submitted[-1]
        body=tuple(v+origin[i%2] for i,v in enumerate(bbox))
        anchor=tuple(origin[i]+round((v+pet.canvas_offset[i])*dpi) for i,v in enumerate((410,570)))
        return dict(origin=origin,size=(width,height),body=body,anchor=anchor)


class StartupTests(unittest.TestCase):
    def test_1920_1080_saved_eighty_percent_starts_on_screen(self):
        frame=first_frame()
        self.assertGreater(win.rect_intersection_area(frame['body'],(0,0,1920,1040)),0,frame)
        self.assertEqual(frame['anchor'],(1654,934),frame)

    def test_saved_sizes_preserve_startup_anchor_across_dpi_and_layouts(self):
        # Each rectangle is an individual monitor work area, never a bounding
        # rectangle spanning gaps between displays. No physical second display.
        for work in ((0,0,1920,1040),(1920,0,3840,1040),
                     (0,1080,1920,2120),(-1920,0,0,1040),(0,-1080,1920,-40)):
            for dpi in (1,1.25,1.5,2):
                for size in (.5,.8,1,2):
                    with self.subTest(work=work,dpi=dpi,size=size):
                        frame=first_frame(work,size,dpi)
                        expected=(work[2]-36-round(230*dpi),work[3]-36-round(70*dpi))
                        # Separate crop/anchor rounding can differ by one pixel.
                        self.assertLessEqual(max(abs(a-b) for a,b in zip(frame['anchor'],expected)),1,frame)
                        body=frame['body']
                        self.assertTrue(body[0]>=work[0] and body[1]>=work[1]
                                        and body[2]<=work[2] and body[3]<=work[3],frame)


if __name__=='__main__':
    unittest.main(verbosity=2)
