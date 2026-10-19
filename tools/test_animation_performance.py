"""Pixel-exact and scheduling regressions supporting the native timing probe."""
import sys
import unittest
import tempfile
import threading
import time
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pig_pet as win
from windows_pet import scaled_frame_bytes,resize_alpha,WindowsPet
from animation_clock import load_manifest,Frames,DecodedFrames
from codex_observer import CodexObserver,ObserverReader
from family_store import FamilyStore
from windows_animation_timer import WindowAnimationTimer

ROOT=Path(__file__).resolve().parents[1]


class AnimationPerformanceTests(unittest.TestCase):
    def test_premultiply_all_channel_alpha_pairs(self):
        rgba=np.zeros((256,256,4),dtype=np.uint8)
        values=np.arange(256,dtype=np.uint8)
        rgba[:,:,0]=values[None,:]
        rgba[:,:,1]=255-values[None,:]
        rgba[:,:,2]=(values*3)[None,:]
        rgba[:,:,3]=np.arange(256,dtype=np.uint8)[:,None]
        wide=rgba.astype(np.uint16)
        expected=rgba.copy()
        expected[:,:,:3]=(wide[:,:,:3]*wide[:,:,3:4]+127)//255
        self.assertEqual(win.premultiplied_bgra(Image.fromarray(rgba)),expected[:,:, [2,1,0,3]].tobytes())

    def test_scaled_pixels_match_original_full_canvas(self):
        clips=load_manifest(ROOT/'assets/macos-resources')
        for key,index in [('idle',10),('carrot',8),('reading',80)]:
            canvas=clips[key].frames[index]
            for size in [(640,640),(800,800),(960,960),(1280,1280),(853,853)]:
                with self.subTest(key=key,size=size):
                    self.assertEqual(scaled_frame_bytes(canvas,size),win.premultiplied_bgra(resize_alpha(canvas,size)))
        # Content touching all edges, including partially transparent pixels.
        rng=np.random.default_rng(7)
        canvas=Image.fromarray(rng.integers(0,256,(640,640,4),dtype=np.uint8))
        self.assertEqual(scaled_frame_bytes(canvas,(960,960)),win.premultiplied_bgra(resize_alpha(canvas,(960,960))))

    def test_clock_does_not_accumulate_callback_work(self):
        clip=load_manifest(ROOT/'assets/macos-resources')['reading']
        intro=sum(clip.durations[:clip.loop_start])/1000
        period=(clip.total_duration/1000-intro)
        for cycles in [1,100,10000]:
            self.assertEqual(clip.frame(intro+period*cycles+.011),clip.frame(intro+.011))

    def test_delivery_jitter_does_not_repeat_or_skip_nominal_frames(self):
        clips=load_manifest(ROOT/'assets/macos-resources')
        pet=SimpleNamespace(animation_sample_time=None,dragging=False,transient_key='reading',
            transient_once=False,animations=clips,visual_epoch=100.0)
        for tick in range(100):
            sample=100.005+tick*.020
            pet.animation_sample_time=sample
            with patch('windows_pet.time.monotonic',return_value=sample+(.019 if tick%2 else 0)):
                WindowsPet._resolve_visual(pet)
            self.assertEqual(pet.frame_index,clips['reading'].frame(sample-100))

    def test_loop_reuses_decoded_pixels_with_bounded_memory(self):
        clips=load_manifest(ROOT/'assets/macos-resources')
        frames=clips['reading'].frames
        originals=[]
        for index in range(len(frames)):
            originals.append(frames[index].tobytes())
        with patch('animation_clock.Image.open',side_effect=AssertionError('warm loop read from disk')):
            for index in range(len(frames)):
                self.assertEqual(frames[index].tobytes(),originals[index])
        self.assertLessEqual(frames.decoded.used,frames.decoded.budget)
        small=DecodedFrames(budget=16)
        for i in range(5):
            small.put(i,((2,2),(0,0,2,2),Image.new('RGBA',(2,2))))
        self.assertEqual(len(small.items),1)
        self.assertEqual(small.used,16)

    def test_blocked_reader_never_blocks_ui_or_overwrites_new_event(self):
        entered, release = threading.Event(),threading.Event()
        now=time.time()
        def read(reader,nodes):
            entered.set()
            release.wait(3)
            return dict(metadata={},pending=[],observed=[('actor',('task_complete','old',now-1))],
                unread=None,rollout_exists={})
        with tempfile.TemporaryDirectory() as tmp,patch.object(ObserverReader,'_read',read):
            store=FamilyStore()
            observer=CodexObserver(store,tmp,home=tmp)
            observer.enable_background()
            try:
                observer.poll()
                self.assertTrue(entered.wait(1))
                start=time.perf_counter()
                for _ in range(100): observer.poll()
                self.assertLess(time.perf_counter()-start,.1)
                self.assertEqual(store.nodes,{})
                observer.ingest(dict(session_id='actor',event='UserPromptSubmit',turn_id='new',received_at=now))
                release.set()
                deadline=time.monotonic()+1
                while observer.background.results.empty() and time.monotonic()<deadline:
                    time.sleep(.005)
                observer.poll()
                self.assertEqual(store.nodes['actor'].turn,'new')
                self.assertTrue(store.nodes['actor'].active)
            finally:
                release.set()
                observer.close()
                observer.background.thread.join(1)

    def test_timer_has_one_pending_notification_and_stops(self):
        # Real Windows high-resolution wait, mocked notification destination.
        timer=WindowAnimationTimer(0)
        try:
            sent=[]
            timer.user.PostMessageW=lambda *a:sent.append(time.perf_counter()) or 1
            time.sleep(.11)
            self.assertEqual(len(sent),1)
            timer.acknowledge()
            time.sleep(.05)
            self.assertEqual(len(sent),2)
        finally:
            timer.close()
        self.assertFalse(timer.thread.is_alive())

    def test_disabled_observer_cannot_start_background_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            observer=CodexObserver(FamilyStore(),tmp,home=tmp,enabled=False)
            observer.enable_background()
            self.assertIsNone(observer.background)

    def test_new_parent_turn_hides_only_old_interrupted_children(self):
        store=FamilyStore()
        store.ingest(dict(session_id='root',event='UserPromptSubmit',turn_id='r1'),1)
        for child in ['paused','working']:
            store.ingest(dict(session_id='root',agent_id=child,event='SubagentStart',turn_id='c1'),2)
        store.ingest(dict(session_id='paused',event='Interrupt',turn_id='c1'),3)
        self.assertEqual(len(store.children('root',4)),2)
        store.ingest(dict(session_id='root',event='UserPromptSubmit',turn_id='r2'),10)
        self.assertEqual([n.id for n in store.children('root',10)],['working'])
        self.assertEqual(store.nodes['paused'].status,'interrupted')
        store.ingest(dict(session_id='paused',event='ResumeDetected',turn_id='c2'),11)
        self.assertEqual(len(store.children('root',12)),2)

    def test_unacknowledged_events_are_retried(self):
        from codex_bridge import publish_event
        with tempfile.TemporaryDirectory() as tmp:
            publish_event(Path(tmp),dict(session_id='a',event='UserPromptSubmit',turn_id='t'))
            reader=ObserverReader(tmp,tmp)
            try:
                request=dict(nodes={},versions={},seen=frozenset())
                first=reader._read(request)
                self.assertTrue(first['pending'])
                self.assertEqual(first['pending'],reader._read(request)['pending'])
                request['seen']=frozenset(n for n,_ in first['pending'])
                self.assertEqual(reader._read(request)['pending'],[])
            finally:
                reader.close()
                reader.thread.join(1)

    def test_late_metadata_cannot_replace_new_hook_path(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as tmp:
            observer=CodexObserver(FamilyStore(),tmp,home=tmp)
            observer.ingest(dict(session_id='a',event='UserPromptSubmit',turn_id='new',received_at=20,transcript_path='new.jsonl'))
            batch=dict(metadata={'a':dict(thread_title='old',parent_thread_id='',rollout='old.jsonl')},
                pending=[],observed=[],unread=None,rollout_exists={},node_versions={'a':10})
            observer.background=Mock()
            observer.background.take.return_value=batch
            observer.poll(21)
            self.assertEqual(observer.store.nodes['a'].rollout,'new.jsonl')
            self.assertEqual(observer.metadata['a']['rollout'],'new.jsonl')


if __name__=='__main__':
    unittest.main()
