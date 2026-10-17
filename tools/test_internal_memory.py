"""Offline regression for issue #3; no Codex process, account or real memory data."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_observer import CodexObserver
from family_store import FamilyStore

MARKER = '## Memory Writing Agent: Phase 2 (Consolidation)\nYou are a Memory Writing Agent.'

class MemoryFilterTests(unittest.TestCase):
    def test_missing_stop_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / 'family-events'
            events.mkdir()
            for i, event in enumerate(('SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PostToolUse')):
                (events / f'{i}.json').write_text(json.dumps(dict(session_id='internal', event=event,
                    cwd=r'C:\Users\fixture\.codex\memories', received_at=100+i,
                    prompt_preview=MARKER if event == 'UserPromptSubmit' else '')))
            for _ in range(2):
                store = FamilyStore()
                observer = CodexObserver(store, root, home=root, enabled=False)
                observer.poll(200)
                self.assertNotIn('internal', store.nodes)
                for event in ('Stop', 'ResumeDetected', 'TaskCompleteFallback', 'SessionEnd'):
                    observer.ingest(dict(session_id='internal', event=event, received_at=201))
                self.assertNotIn('internal', store.nodes)
                self.assertEqual(store.work_tokens(), set())

    def test_identity_and_false_positives(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FamilyStore()
            observer = CodexObserver(store, tmp, home=tmp, enabled=False)
            def submit(actor, prompt=MARKER, cwd=None, **extra):
                observer.ingest(dict(session_id=actor, event='UserPromptSubmit', received_at=100,
                    cwd=cwd or str(Path(tmp)/'memories'), prompt_preview=prompt, **extra))
            submit('custom-home')
            self.assertNotIn('custom-home', store.nodes)
            observer.metadata['registered-internal'] = {'thread_title': 'Memory'}
            submit('registered-internal')
            self.assertNotIn('registered-internal', store.nodes)
            submit('ordinary', prompt='Please organize these notes')
            submit('quote', cwd='/tmp/project')
            submit('parent', agent_id='child')
            for actor in ('ordinary', 'quote', 'child'):
                self.assertTrue(store.nodes[actor].active)
            observer.metadata['metadata-child'] = {'parent_thread_id': 'parent'}
            submit('metadata-child')
            self.assertTrue(store.nodes['metadata-child'].active)

if __name__ == '__main__':
    unittest.main()
