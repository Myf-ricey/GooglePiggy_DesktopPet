"""Regression for completed children whose Codex logs were compressed."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zstandard
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from codex_observer import CodexObserver,latest_lifecycle
from family_store import FamilyStore


class CompressedRolloutTests(unittest.TestCase):
    def test_completed_child_is_not_running_after_compression(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); rollout=root/'rollout.jsonl'
            data=(json.dumps(dict(timestamp='1970-01-01T00:02:10Z',type='event_msg',
                payload=dict(type='task_complete',turn_id='child-turn')))+'\n').encode()
            Path(str(rollout)+'.zst').write_bytes(zstandard.ZstdCompressor().compress(data))
            store=FamilyStore(); observer=CodexObserver(store,root,home=root)
            observer.ingest(dict(session_id='parent',agent_id='child',event='PostToolUse',turn_id='child-turn',
                transcript_path=str(rollout),received_at=110))
            observer.ingest(dict(session_id='parent',event='Stop',received_at=140))
            observer.poll(200)
            self.assertFalse(store.nodes['child'].active,'Finished child is still animating because only .jsonl.zst exists')
            self.assertEqual(store.children('parent',200),[])

    def test_latest_lifecycle_from_compressed_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'rollout.jsonl.zst'
            lines=[dict(timestamp='1970-01-01T00:02:00Z',type='event_msg',payload=dict(type='task_started',turn_id='t')),
                   dict(timestamp='1970-01-01T00:02:10Z',type='event_msg',payload=dict(type='task_complete',turn_id='t'))]
            path.write_bytes(zstandard.ZstdCompressor().compress(('\n'.join(map(json.dumps,lines))+'\n').encode()))
            self.assertEqual(latest_lifecycle(path),('task_complete','t',130))

    def test_plaintext_live_turn_wins_over_old_compressed_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'rollout.jsonl'
            def data(kind,turn):return (json.dumps(dict(timestamp='1970-01-01T00:02:10Z',type='event_msg',payload=dict(type=kind,turn_id=turn)))+'\n').encode()
            Path(str(path)+'.zst').write_bytes(zstandard.ZstdCompressor().compress(data('task_complete','old')))
            path.write_bytes(data('task_started','new'))
            self.assertEqual(latest_lifecycle(path),('task_started','new',130))

    def test_corrupt_archive_does_not_fake_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bad.jsonl.zst';path.write_bytes(b'broken')
            self.assertIsNone(latest_lifecycle(path))

if __name__=='__main__':unittest.main(verbosity=2)
