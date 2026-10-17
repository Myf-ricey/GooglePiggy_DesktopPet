"""Adversarial state observation cases found in the post-deployment audit."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import zstandard
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from codex_observer import CodexObserver,latest_lifecycle
from family_store import FamilyStore


def record(kind,seconds=130,turn='t'):
    return json.dumps(dict(timestamp=f'1970-01-01T00:{seconds//60:02d}:{seconds%60:02d}Z',
        type='event_msg',payload=dict(type=kind,turn_id=turn)))+'\n'


class StateAuditTests(unittest.TestCase):
    def test_empty_plain_file_does_not_mask_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'r.jsonl';path.touch()
            Path(str(path)+'.zst').write_bytes(zstandard.ZstdCompressor().compress(record('task_complete').encode()))
            self.assertEqual(latest_lifecycle(path),('task_complete','t',130))

    def test_delayed_old_log_line_does_not_mask_newer_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'r.jsonl'
            path.write_text(record('task_complete',180)+record('task_started',120),encoding='utf-8')
            self.assertEqual(latest_lifecycle(path),('task_complete','t',180))

    def test_invalid_timestamp_is_not_a_fabricated_terminal_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'r.jsonl'
            path.write_text(record('task_started',120)+record('task_complete').replace('1970-01-01T00:02:10Z','invalid'),encoding='utf-8')
            self.assertEqual(latest_lifecycle(path),('task_started','t',120))

    def test_archive_event_before_large_output_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'r.jsonl.zst'
            data=(record('task_complete')+json.dumps({'type':'response_item','payload':{'output':'x'*(17*1024*1024)}})+'\n').encode()
            path.write_bytes(zstandard.ZstdCompressor().compress(data))
            self.assertEqual(latest_lifecycle(path),('task_complete','t',130))

    def test_active_log_cache_eventually_rechecks_unchanged_stat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'r.jsonl'
            path.write_bytes(record('task_started',120).encode().ljust(256,b' '))
            info=path.stat()
            store=FamilyStore();observer=CodexObserver(store,root,home=root)
            observer.ingest(dict(session_id='target',event='PostToolUse',turn_id='t',received_at=110,transcript_path=str(path)))
            observer.poll(200);self.assertTrue(store.nodes['target'].active)
            path.write_bytes(record('task_complete',130).encode().ljust(256,b' '))
            os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
            observer.poll(216)
            self.assertFalse(store.nodes['target'].active)

    def metadata_fixture(self,root,prompt='ordinary'):
        path=root/'r.jsonl';path.write_text(record('task_complete'),encoding='utf-8')
        with sqlite3.connect(root/'state_1.sqlite') as db:
            db.execute('create table threads(id text, title text, source text, rollout_path text, updated_at integer)')
            db.executemany('insert into threads values (?,?,?,?,?)',[(f'recent-{i}','', '{}','',1000+i) for i in range(256)])
            db.execute('insert into threads values (?,?,?,?,?)',('target','User task','{}',str(path),1))
        db.close()
        (root/'family-events').mkdir()
        (root/'family-events/1.json').write_text(json.dumps(dict(session_id='target',event='UserPromptSubmit',turn_id='t',received_at=110,prompt_preview=prompt)),encoding='utf-8')
        observer=CodexObserver(FamilyStore(),root,home=root)
        observer.poll(200)
        return observer

    def test_active_actor_beyond_recent_256_gets_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            observer=self.metadata_fixture(Path(tmp))
            self.assertTrue('target' in observer.metadata,'Active actor outside recent metadata window was not looked up')
            self.assertFalse(observer.store.nodes['target'].active)

    def test_registered_actor_beyond_recent_256_is_not_filtered(self):
        with tempfile.TemporaryDirectory() as tmp:
            observer=self.metadata_fixture(Path(tmp),'This is an app-generated request for a suggested next user message.')
            self.assertNotIn('target',observer.internal_sessions)
            self.assertIn('target',observer.store.nodes)

    def test_fresh_pretool_resumes_after_compaction_same_turn(self):
        store=FamilyStore()
        for i,event in enumerate(('UserPromptSubmit','PreCompact','PostCompact')):
            store.ingest(dict(session_id='target',event=event,turn_id='t'),100+i)
        self.assertFalse(store.ingest(dict(session_id='target',event='PostToolUse',turn_id='t'),102.5))
        self.assertTrue(store.ingest(dict(session_id='target',event='PreToolUse',turn_id='t'),103))
        self.assertTrue(store.nodes['target'].active)
        self.assertEqual(store.nodes['target'].status,'working')
        self.assertTrue(store.ingest(dict(session_id='target',event='Stop',turn_id='t'),105))
        self.assertFalse(store.ingest(dict(session_id='target',event='PreToolUse',turn_id='t'),106))


if __name__=='__main__':
    from codex_bridge import atomic_json
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(StateAuditTests))
    atomic_json(Path(__file__).resolve().parents[1]/'qa/state-audit-tests.json',dict(tests=result.testsRun,passed=result.wasSuccessful(),failures=[str(t) for t,_ in result.failures+result.errors]))
    sys.exit(0 if result.wasSuccessful() else 1)
