"""Windows permits top/left/right hiding and keeps bottom releases visible."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from animation_clock import load_manifest
import pig_pet as win
from windows_pet import WindowsPet

ROOT = Path(__file__).resolve().parents[1]
CLIPS = load_manifest(ROOT/'assets/macos-resources')


class EdgePolicyTests(unittest.TestCase):
    def attempt(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            pet = WindowsPet(CLIPS, Path(tmp)/'report.json', ROOT, Path(tmp)/'status.json', False)
            pet.hwnd = 123
            monitor = win.MonitorInfo(frame=(0,0,2560,1600), work=(0,0,2560,1528))
            with patch.object(pet, '_screen_bounds_for_local', return_value=body), \
                    patch.object(pet, '_current_pet_local_bounds', return_value=(334,436,486,570)), \
                    patch.object(pet, '_interaction_monitor', return_value=monitor), \
                    patch.object(pet, '_window_rect', return_value=(0,0,960,960)), \
                    patch.object(pet, '_switch_visual'), \
                    patch.object(pet, '_start_edge_motion', return_value=True) as motion, \
                    patch.object(win, 'enumerate_monitor_infos', return_value=[monitor]):
                result = pet._begin_edge_hide_if_needed()
            return result, pet.edge_placement, pet.edge_transition, motion.called

    def test_bottom_does_not_start_hiding_or_create_tail_placement(self):
        for body in ((500,1450,700,1602), (500,1700,700,1850)):
            with self.subTest(body=body):
                result, placement, transition, moved = self.attempt(body)
                self.assertFalse(result)
                self.assertIsNone(placement)
                self.assertIsNone(transition)
                self.assertFalse(moved)

    def test_other_three_edges_still_hide_including_bottom_corners(self):
        for edge, body in (
                ('left',(-2,500,198,700)), ('right',(2362,500,2562,700)),
                ('top',(500,-2,700,198)), ('left',(-2,1450,198,1602)),
                ('right',(2362,1450,2562,1602))):
            with self.subTest(edge=edge, body=body):
                result, placement, transition, moved = self.attempt(body)
                self.assertTrue(result)
                self.assertEqual(placement.edge, edge)
                self.assertEqual(transition, 'hiding')
                self.assertTrue(moved)


if __name__ == '__main__':
    unittest.main(verbosity=2)
