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

    def test_system_disabled_startup_is_not_reported_enabled(self):
        class Key:
            def __enter__(self): return self
            def __exit__(self,*args): pass
        def query(key,name):
            return (b'\x03'+b'\0'*11,3) if getattr(key,'approved',False) else ('pet.exe',1)
        def openkey(root,path):
            k=Key(); k.approved='StartupApproved' in path; return k
        with patch.object(win.winreg,'OpenKey',side_effect=openkey),patch.object(win.winreg,'QueryValueEx',side_effect=query):
            self.assertFalse(win.is_autostart_enabled())

    def test_first_start_registers_once_and_preserves_opt_out(self):
        with patch.object(win.winreg,'OpenKey',side_effect=FileNotFoundError),patch.object(win,'set_autostart') as register:
            win.configure_first_autostart(Path('C:/Pet'))
            register.assert_called_once_with(True,Path('C:/Pet'))
        with patch.object(win.winreg,'OpenKey',side_effect=FileNotFoundError),patch.object(win,'set_autostart') as register:
            win.configure_first_autostart(Path('C:/Pet'),previous_install=True)
            register.assert_called_once_with(False,Path('C:/Pet'))
        class Key:
            def __enter__(self): return self
            def __exit__(self,*args): pass
        for preference in (0,1):
            with patch.object(win.winreg,'OpenKey',return_value=Key()),patch.object(win.winreg,'QueryValueEx',return_value=(preference,4)),patch.object(win,'set_autostart') as register:
                win.configure_first_autostart(Path('C:/Pet'))
                register.assert_not_called()

    def test_compaction_is_not_task_completion(self):
        p=WindowsPet.__new__(WindowsPet); p.store=FamilyStore(); p.permission_request=None
        p.hidden_family='root'; p.hidden_since=2; p.hidden_tokens=set()
        for event,now in [('UserPromptSubmit',1),('PreCompact',3),('PostCompact',4)]:
            p.store.ingest(dict(session_id='root',event=event,turn_id='t'),now)
        self.assertFalse(p.activity_requires_visible_pet)
        p.store.ingest(dict(session_id='root',event='Stop',turn_id='t'),5)
        self.assertTrue(p.activity_requires_visible_pet)

if __name__=='__main__': unittest.main()
