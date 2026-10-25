import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from family_store import FamilyStore
from codex_observer import CodexObserver
from windows_pet import WindowsPet
import pig_pet as win

PREFIX='You are an expert at upholding safety and compliance standards for Codex ambient suggestions.\n\n'

class HandoffTests(unittest.TestCase):
    def test_hidden_family_ignores_new_activity_and_waits_for_children(self):
        p=WindowsPet.__new__(WindowsPet)
        p.store=FamilyStore(); p.permission_request=None
        p.store.ingest(dict(session_id='root',event='UserPromptSubmit',turn_id='t'),1)
        p.hidden_tokens=p.store.work_tokens(); p.hidden_family='root'; p.hidden_since=2
        p.store.ingest(dict(session_id='other',event='UserPromptSubmit',turn_id='t'),3)
        self.assertFalse(p.activity_requires_visible_pet)
        p.store.ingest(dict(session_id='root',agent_id='child',event='SubagentStart'),4)
        p.store.ingest(dict(session_id='root',event='Stop',turn_id='t'),5)
        self.assertFalse(p.activity_requires_visible_pet)
        p.store.ingest(dict(session_id='root',agent_id='child',event='SubagentStop'),6)
        self.assertTrue(p.activity_requires_visible_pet)

    def test_safety_filter_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            for repeat in range(2):
                s=FamilyStore(); o=CodexObserver(s,Path(tmp),home=Path(tmp),enabled=False)
                o.ingest(dict(session_id='safety',event='SessionStart',received_at=1))
                o.ingest(dict(session_id='safety',event='UserPromptSubmit',prompt_preview=PREFIX+'check',source='codex-hook',cwd='/',received_at=2))
                o.ingest(dict(session_id='safety',event='Stop',received_at=3))
                self.assertNotIn('safety',s.nodes)

    def test_safety_counterexamples(self):
        cases=[dict(cwd='C:/'),dict(cwd='/project'),dict(source='other'),dict(prompt_preview='Quote '+PREFIX),dict(prompt_preview=PREFIX.rstrip()),dict(agent_id='child'),dict(parent_thread_id='parent')]
        with tempfile.TemporaryDirectory() as tmp:
            for extra in cases+[{'registered':True},{'metadata_parent':True},{'node_parent':True}]:
                with self.subTest(extra=extra):
                    s=FamilyStore(); o=CodexObserver(s,Path(tmp),home=Path(tmp),enabled=False)
                    if extra.get('registered') or extra.get('metadata_parent'):
                        o.metadata['normal']={'parent_thread_id':'parent' if extra.get('metadata_parent') else ''}
                    if extra.get('node_parent'):
                        s.ingest(dict(session_id='normal',event='SessionStart',parent_thread_id='parent'),1)
                    p=dict(session_id='normal',event='UserPromptSubmit',prompt_preview=PREFIX,source='codex-hook',cwd='/',received_at=2)
                    p.update(extra); o.ingest(p)
                    self.assertIn(extra.get('agent_id','normal'),s.nodes)

    def test_startup_query_failure_is_not_reported_enabled(self):
        with patch.object(win,'autostart_request',side_effect=OSError('provider unavailable')):
            self.assertIn('未确认',win.autostart_menu_label())
            with self.assertRaises(OSError):win.is_autostart_enabled()

    def test_existing_install_still_reconciles_system_registration(self):
        with patch.object(win,'autostart_request',return_value={'enabled':False}) as check,patch.object(win,'write_json_atomic'):
            win.configure_first_autostart(Path('C:/Pet'),previous_install=True)
            check.assert_called_once_with('reconcile',Path('C:/Pet'),True)

    def test_compaction_is_not_task_completion(self):
        p=WindowsPet.__new__(WindowsPet); p.store=FamilyStore(); p.permission_request=None
        p.hidden_family='root'; p.hidden_since=2; p.hidden_tokens=set()
        for event,now in [('UserPromptSubmit',1),('PreCompact',3),('PostCompact',4)]:
            p.store.ingest(dict(session_id='root',event=event,turn_id='t'),now)
        self.assertFalse(p.activity_requires_visible_pet)
        p.store.ingest(dict(session_id='root',event='Stop',turn_id='t'),5)
        self.assertTrue(p.activity_requires_visible_pet)

if __name__=='__main__': unittest.main()
