"""Notification ownership, stale I/O and precise Windows selector gestures."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from family_store import FamilyStore
from codex_observer import CodexObserver
from codex_bridge import atomic_json
from animation_clock import load_manifest
from windows_pet import WindowsPet
import pig_pet as win

ROOT = Path(__file__).resolve().parents[1]


def complete(store, actor='A', turn='one', when=100, title='短标题'):
    store.ingest(dict(session_id=actor, turn_id=turn, event='UserPromptSubmit', thread_title=title), when-1)
    store.ingest(dict(session_id=actor, turn_id=turn, event='Stop'), when)
    return store.nodes[actor]


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root/'dismissed-results.json'
        self.store = FamilyStore(self.path)

    def test_only_one_result_removed_and_restart_replay_stays_read(self):
        a = complete(self.store)
        complete(self.store, 'B')
        self.assertTrue(self.store.dismiss_result('A', self.store.result_token(a)))
        self.assertEqual([n.id for n in self.store.roots(110)], ['B'])
        self.assertFalse(self.store.dismiss_result('A', self.store.result_token(a)))
        restored = FamilyStore(self.path)
        self.assertFalse(complete(restored).unread)
        self.assertTrue(complete(restored, 'B').unread)

    def test_same_turn_later_fallback_and_new_turn(self):
        node = complete(self.store)
        token = self.store.result_token(node)
        self.store.dismiss_result('A', token)
        restored = FamilyStore(self.path)
        self.assertFalse(complete(restored, when=105).unread)
        self.assertTrue(complete(restored, turn='two', when=120).unread)
        self.assertFalse(restored.dismiss_result('A', token))

    def test_turnless_earlier_fallback_but_later_result_reminds(self):
        node = complete(self.store, turn='', when=100)
        self.store.dismiss_result('A', self.store.result_token(node))
        self.assertFalse(complete(FamilyStore(self.path), turn='', when=99).unread)
        self.assertTrue(complete(FamilyStore(self.path), turn='', when=110).unread)

    def test_dismiss_does_not_change_task_children_or_animation(self):
        node = complete(self.store)
        self.store.ingest(dict(session_id='A',agent_id='child',turn_id='c',event='SubagentStart'),101)
        before = (node.status,node.completion,node.result,self.store.selected,self.store.work_tokens())
        self.store.dismiss_result('A', self.store.result_token(node))
        self.assertEqual(before,(node.status,node.completion,node.result,self.store.selected,self.store.work_tokens()))
        self.assertEqual([n.id for n in self.store.roots(102)], ['A'])
        self.assertFalse(self.store.dismiss_result('child', ('c',101)))

    def test_failed_write_preserves_notification(self):
        node = complete(self.store)
        with patch('family_store.atomic_json',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.store.dismiss_result('A', self.store.result_token(node))
        self.assertTrue(node.unread)
        self.assertEqual(self.store.dismissed_results,{})

    def test_invalid_receipts_are_ignored(self):
        atomic_json(self.path,dict(bad=None,boolean=dict(turn='x',completed_at=True),
            nan=dict(turn='x',completed_at=float('nan')),valid=dict(turn='one',completed_at=100)))
        self.assertEqual(set(FamilyStore(self.path).dismissed_results),{'valid'})
        self.path.write_text('broken',encoding='utf-8')
        self.assertEqual(FamilyStore(self.path).dismissed_results,{})

    def unread_file(self):
        path=self.root/'.codex-global-state.json'
        atomic_json(path,{'electron-thread-read-state-v1':{'version':1,'unreadByIdentity':{'user':{'local:test':['A']}}}})
        return path

    def test_foreground_sync_and_codex_file_stays_read_only(self):
        node=complete(self.store)
        self.store.dismiss_result('A',self.store.result_token(node))
        path=self.unread_file(); before=path.read_bytes()
        observer=CodexObserver(self.store,self.root,home=self.root)
        observer.poll(110)
        self.assertFalse(node.unread)
        self.assertEqual(path.read_bytes(),before)
        complete(self.store,turn='two',when=120)
        observer.poll(130)
        self.assertTrue(node.unread)

    def test_background_batch_read_before_dismiss_does_not_relight(self):
        node=complete(self.store)
        batch=dict(metadata={},pending=[],observed=[],unread={'A'},rollout_exists={})
        observer=CodexObserver(self.store,self.root,home=self.root)
        from unittest.mock import Mock
        observer.background=Mock()
        observer.background.take.return_value=batch
        self.store.dismiss_result('A',self.store.result_token(node))
        observer.poll(110)
        self.assertFalse(node.unread)
        complete(self.store,turn='two',when=120)
        observer.poll(130)
        self.assertTrue(node.unread)


class SelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clips=load_manifest(ROOT/'assets/macos-resources')

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.pet=WindowsPet(self.clips,self.root/'report.json',ROOT,self.root/'status.json',False)
        self.now=time.time()-10
        complete(self.pet.store,when=self.now,title='中A🙂')
        complete(self.pet.store,'B',when=self.now,title='English long title 中文🙂 '*15)
        self.pet.store.ingest(dict(session_id='running',event='UserPromptSubmit',turn_id='r',thread_title='运行中'),self.now)
        self.pet.selector_visible=True
        self.pet.compose('idle',0)
        self.cursor=patch.object(self.pet,'_cursor_window_position')
        self.point=self.cursor.start()
        self.addCleanup(self.cursor.stop)
        for name in ('SetCapture','ReleaseCapture','MessageBoxW'):
            mock=patch.object(win.user32,name); mock.start(); self.addCleanup(mock.stop)

    def center(self, actor='A'):
        rect=next(r for r,a,t in self.pet.selector_dismiss_rows if a==actor)
        return ((rect[0]+rect[2])/2,(rect[1]+rect[3])/2)

    def down(self, point=None):
        self.point.return_value=point or self.center()
        self.pet._handle_right_button_down()

    def up(self, point=None):
        if point:self.point.return_value=point
        with patch.object(self.pet,'_render_current'),patch.object(self.pet,'_write_heartbeat'):
            return self.pet._handle_right_button_up()

    def test_dot_gap_title_and_ellipsis_clear_only_target(self):
        for actor,kind in [('A','dot'),('A','gap'),('A','title'),('B','ellipsis')]:
            with self.subTest(actor=actor,kind=kind):
                self.pet.store.nodes[actor].unread=True
                self.pet.compose('idle',0)
                r=next(r for r,a,t in self.pet.selector_dismiss_rows if a==actor)
                x={'dot':r[0]+2,'gap':r[0]+12,'title':r[0]+20,'ellipsis':r[2]-2}[kind]
                self.down((x,(r[1]+r[3])/2));self.assertTrue(self.up())
                self.assertFalse(self.pet.store.nodes[actor].unread)

    def test_row_blank_spacing_and_read_rows_do_not_clear(self):
        r=next(r for r,a in self.pet.selector_rows if a=='A')
        for point in [(r[2]-1,(r[1]+r[3])/2),(r[0]+30,r[1]+1),self.center('B')]:
            self.pet.store.nodes['B'].unread=False
            self.pet.compose('idle',0)
            self.down(point); self.up()
            self.assertTrue(self.pet.store.nodes['A'].unread)

    def test_drag_out_and_back_cancels(self):
        self.down(); original=self.point.return_value
        self.point.return_value=(0,0)
        self.pet._wndproc(self.pet.hwnd,win.WM_MOUSEMOVE,2,0)
        self.assertTrue(self.up(original))
        self.assertTrue(self.pet.store.nodes['A'].unread)

    def test_cross_row_cancels(self):
        self.down();self.up(self.center('B'))
        self.assertTrue(self.pet.store.nodes['A'].unread)
        self.assertTrue(self.pet.store.nodes['B'].unread)

    def test_refresh_to_new_result_cancels(self):
        self.down()
        complete(self.pet.store,turn='two',when=self.now+5)
        self.up()
        self.assertTrue(self.pet.store.nodes['A'].unread)

    def test_scroll_capture_focus_and_dpi_cancel(self):
        for message in (0x020A,0x0215,0x001F,0x0008,0x02E0):
            with self.subTest(message=message):
                self.pet.compose('idle',0); self.down()
                with patch.object(win.PigPet,'_wndproc',return_value=0):
                    self.pet._wndproc(self.pet.hwnd,message,0,0)
                self.up();self.assertTrue(self.pet.store.nodes['A'].unread)

    def test_hidden_update_permission_preview_and_switch_block(self):
        for attr,value in [('selector_visible',False),('preview_task',True),('preview_dialog',True),
                           ('update_notice',object()),('permission_request',{'summary':'test'}),('edge_placement',object())]:
            previous=getattr(self.pet,attr)
            self.down();setattr(self.pet,attr,value);self.up()
            self.assertTrue(self.pet.store.nodes['A'].unread)
            setattr(self.pet,attr,previous)
        self.down();self.pet.store.select('B');self.up()
        self.assertTrue(self.pet.store.nodes['A'].unread)

    def test_scale_dpi_and_cached_layout_share_hit_geometry(self):
        for scale in (.5,1,2):
            self.pet.appearance.update({'taskScale':scale})
            self.pet.compose('idle',0)
            point=self.center()
            self.assertEqual(self.pet._selector_dismiss_hit(point)[0],'A')
            for dpi in (1,1.5,2):
                self.pet.scale=dpi;self.pet.compose('idle',0)
                physical=tuple((v+self.pet.canvas_offset[i])*dpi for i,v in enumerate(point))
                with patch.object(win.PigPet,'_cursor_window_position',return_value=physical):
                    actual=WindowsPet._cursor_window_position(self.pet)
                self.assertEqual(self.pet._selector_dismiss_hit(actual)[0],'A')
            cached=self.pet.selector_cache[0]
            with patch.object(ImageDraw.ImageDraw,'textbbox',side_effect=AssertionError('repeated measurement')):
                self.pet.compose('idle',0)
            self.assertIs(self.pet.selector_cache[0],cached)

    def test_scrolled_bottom_clamps_after_deletion_and_hides_last(self):
        for i in range(8):complete(self.pet.store,'extra'+str(i),when=self.now)
        self.pet.selector_scroll=999;self.pet.compose('idle',0)
        visible={a for _,a in self.pet.selector_rows}
        actor=self.pet.selector_dismiss_rows[-1][1]
        self.down(self.center(actor));self.up()
        self.pet.compose('idle',0)
        self.assertNotIn(actor,{a for _,a in self.pet.selector_rows})
        self.assertLessEqual(self.pet.selector_scroll,len(self.pet.store.roots(time.time()))-6)
        self.assertTrue(self.pet.store.nodes['A'].unread)
        self.assertNotIn('A',visible)

    def test_body_right_click_uses_original_menu(self):
        self.down((10,10))
        with patch.object(self.pet,'_show_menu') as menu:
            self.pet._wndproc(self.pet.hwnd,win.WM_RBUTTONUP,0,0)
        menu.assert_called_once()

    def test_fast_second_right_click_uses_double_click_down_message(self):
        self.point.return_value=self.center()
        self.pet._wndproc(self.pet.hwnd,0x0206,0,0)
        self.assertTrue(self.up())
        self.assertFalse(self.pet.store.nodes['A'].unread)


if __name__=='__main__':
    unittest.main(verbosity=2)
