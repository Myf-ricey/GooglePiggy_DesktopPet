"""Appearance contracts: pixels, transforms, state isolation and navigation."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from appearance import Appearance, transforms
from animation_clock import load_manifest
from windows_pet import WindowsPet, permission_surface
from update_notice import UpdateNotice
from windows_update import Release
import pig_pet as win

ROOT = Path(__file__).resolve().parents[1]
CLIPS = load_manifest(ROOT/'assets/macos-resources')


class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pet = WindowsPet(CLIPS, self.root/'report.json', ROOT, self.root/'status.json', False)

    def test_save_validation_and_separate_state(self):
        state = self.root/'status.json'
        state.write_text('{"existing":true}')
        a = self.pet.appearance
        a.update({'petScale': 99, 'dialogScale': float('nan'), 'taskColor':'#123456', 'buttonTextColor':'bad', 'other':1})
        a.save()
        restored = Appearance(a.path)
        self.assertEqual(restored.petScale, 2)
        self.assertEqual(restored.dialogScale, 1)
        self.assertEqual(restored.taskColor, '#123456')
        self.assertIsNone(restored.buttonTextColor)
        self.assertEqual(json.loads(state.read_text()), {'existing':True})

    def test_all_animation_anchors_and_complete_canvas(self):
        for scale in (.5, 1, 2):
            self.pet.appearance.update({'petScale':scale})
            transform = transforms(self.pet.appearance)[0]
            self.assertEqual(transform.rect((410,570,410,570)), (410,570,410,570))
            for key, clip in CLIPS.items():
                self.pet.leisure.sleep_epoch = time.monotonic()
                image = self.pet.compose(key, 0)
                bounds = image.getbbox()
                self.assertIsNotNone(bounds, key)
                self.assertGreaterEqual(bounds[0], 0)
                self.assertLessEqual(bounds[2], image.width)

    def test_dialog_independent_scale_and_button_hits(self):
        p = self.pet
        p.permission_request = {'summary':'权限示例'}
        p.permission_request_id = 'test'
        for ps in (.5, 1, 2):
            for ds in (.5, 1, 2):
                p.appearance.update({'petScale':ps,'dialogScale':ds,'dialogGap':200})
                p.compose()
                r = p.permission_buttons['allow']
                self.assertAlmostEqual(r[2]-r[0],116*ds,delta=1)
                self.assertEqual(p._hit_permission_button(((r[0]+r[2])/2,(r[1]+r[3])/2)), 'allow')
                for dpi in (1.25,1.5,2):
                    p.scale = dpi
                    physical = p._physical_bounds(r)
                    with patch.object(win.PigPet,'_cursor_window_position',return_value=((physical[0]+physical[2])/2,(physical[1]+physical[3])/2)):
                        self.assertEqual(p._hit_permission_button(p._cursor_window_position()),'allow')

    def test_alpha_keeps_text_and_default_gradient(self):
        p = self.pet
        p.permission_request = {'summary':'MMMM 测试文字'}
        p.permission_request_id = 'test'
        for alpha in (.1,.25,1):
            p.appearance.update({'dialogOpacity':alpha,'buttonOpacity':.1})
            layer = Image.new('RGBA',(640,640))
            p._composite_permission_bubble(layer)
            r = p.permission_bubble_rect
            self.assertAlmostEqual(layer.getpixel((270,r[1]+12))[3],255*alpha,delta=2)
            text = layer.crop((270,r[1]+43,500,r[1]+63)).getchannel('A')
            self.assertEqual(text.getextrema()[1],255)
        default = permission_surface((250,150,570,348))
        self.assertNotEqual(default.getpixel((280,180))[:3],default.getpixel((540,320))[:3])
        p.appearance.update({'dialogColor':'#123456'})
        self.assertEqual(p._dialog_surface((250,150,570,348)).getpixel((280,180))[:3],(18,52,86))
        p.appearance.update(Appearance().values)
        self.assertEqual(p._dialog_surface((250,150,570,348)).tobytes(),default.tobytes())

    def test_previews_reset_and_close_never_write_tasks(self):
        p = self.pet
        p.preview_dialog = p.preview_task = True
        before = (dict(p.store.nodes),set(p.observer.opened),set(p.permission_viewed),p.visual_epoch)
        p.appearance.update({'petScale':2,'dialogScale':.5,'taskGap':200})
        p.compose()
        self.assertEqual(p.selector_rows,[])
        self.assertEqual(p.permission_buttons,{})
        p.appearance_events.put(('values',Appearance().values))
        p._poll_appearance()
        self.assertTrue(p.preview_task and p.preview_dialog)
        self.assertEqual(before,(dict(p.store.nodes),set(p.observer.opened),set(p.permission_viewed),p.visual_epoch))
        p.appearance_events.put(('closed',None))
        p._poll_appearance()
        self.assertFalse(p.preview_task or p.preview_dialog)
        self.assertFalse(list(self.root.glob('permission-requests/*.response.json')))

    def test_bulb_is_independent_of_dialog(self):
        p = self.pet
        notice = UpdateNotice(Release('0.5.6','test','','',1,''))
        p.update_notice = notice
        for scale in (.5,1,2):
            p.appearance.update({'petScale':scale})
            first = Image.new('RGBA',(640,640))
            notice.draw_decoration(first,elapsed=0)
            p.appearance.update({'dialogScale':2,'dialogOpacity':.1,'dialogGap':200})
            second = Image.new('RGBA',(640,640))
            notice.draw_decoration(second,elapsed=0)
            self.assertEqual(first.tobytes(),second.tobytes())
            p.compose()
            r = p.update_buttons['update']
            self.assertAlmostEqual(r[2]-r[0],284,delta=1)

    def test_all_task_states_navigate_and_failure_keeps_unread(self):
        p = self.pet
        for status in ('thinking','working','reading','interrupted','success','idle'):
            p.store.ingest({'session_id':'actor','event':'UserPromptSubmit','turn_id':'t'},time.time())
            node = p.store.nodes['actor']
            node.status = status
            node.unread = False
            p.selector_down = 'actor'
            p.selector_rows = [((0,0,100,100),'actor')]
            with patch.object(p,'_cursor_window_position',return_value=(50,50)), patch.object(win.ctypes.windll.shell32,'ShellExecuteW',return_value=33) as shell:
                p._handle_left_button_up()
                self.assertEqual(shell.call_args.args[2], 'codex://threads/actor')
            self.assertIn('actor',p.observer.opened)
        node.unread = True
        p.observer.opened.clear()
        p.selector_down = 'actor'
        with patch.object(p,'_cursor_window_position',return_value=(50,50)), patch.object(win.ctypes.windll.shell32,'ShellExecuteW',return_value=31), patch.object(win.user32,'MessageBoxW'):
            p._handle_left_button_up()
        self.assertTrue(node.unread)
        self.assertEqual(p.observer.opened,set())


if __name__ == '__main__':
    unittest.main(verbosity=2)
