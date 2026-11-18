"""A completed/read family must not be retained solely by aborted scouts."""
import unittest
from family_store import FamilyStore


class CompletedFamilyVisibilityTests(unittest.TestCase):
    def test_read_finished_parent_with_interrupted_child_leaves_selector(self):
        store=FamilyStore()
        store.ingest(dict(session_id='parent',turn_id='p1',event='UserPromptSubmit'),1)
        store.ingest(dict(session_id='parent',agent_id='scout',turn_id='c1',event='SubagentStart'),2)
        store.ingest(dict(session_id='scout',turn_id='c1',event='Interrupt'),3)
        store.ingest(dict(session_id='parent',turn_id='p1',event='Stop'),4)
        store.dismiss_result('parent',store.result_token(store.nodes['parent']))
        store.ingest(dict(session_id='parent',event='SessionEnd'),5)
        self.assertFalse(store.nodes['parent'].active)
        self.assertFalse(store.nodes['parent'].unread)
        self.assertEqual([n.id for n in store.roots(10)],[])

    def family(self):
        store=FamilyStore()
        store.ingest(dict(session_id='parent',turn_id='p1',event='UserPromptSubmit'),1)
        store.ingest(dict(session_id='parent',agent_id='scout',turn_id='c1',event='SubagentStart'),2)
        return store

    def finish_read(self,store,when=4):
        store.ingest(dict(session_id='parent',turn_id='p1',event='Stop'),when)
        store.dismiss_result('parent',store.result_token(store.nodes['parent']))

    def test_running_child_keeps_read_finished_family(self):
        store=self.family();self.finish_read(store)
        self.assertEqual([n.id for n in store.roots(10)],['parent'])
        self.assertEqual([n.id for n in store.children('parent',10)],['scout'])

    def test_permission_child_keeps_read_finished_family(self):
        store=self.family()
        store.ingest(dict(session_id='scout',turn_id='c1',event='PermissionRequest'),3)
        self.finish_read(store)
        self.assertEqual([n.id for n in store.roots(10)],['parent'])
        self.assertEqual(store.visual(store.nodes['scout'],10),'question')

    def test_interrupted_parent_and_child_remain_during_paused_turn(self):
        store=self.family()
        store.ingest(dict(session_id='scout',turn_id='c1',event='Interrupt'),3)
        store.ingest(dict(session_id='parent',turn_id='p1',event='Interrupt'),4)
        self.assertEqual([n.id for n in store.roots(10)],['parent'])
        self.assertEqual([n.id for n in store.children('parent',10)],['scout'])

    def test_finished_child_keeps_celebration_then_expires(self):
        store=self.family()
        store.ingest(dict(session_id='scout',turn_id='c1',event='SubagentStop'),3)
        self.finish_read(store)
        self.assertEqual([n.id for n in store.roots(5)],['parent'])
        self.assertEqual(store.roots(7),[])

    def test_unread_parent_remains_and_can_be_dismissed(self):
        store=self.family()
        store.ingest(dict(session_id='scout',turn_id='c1',event='Interrupt'),3)
        store.ingest(dict(session_id='parent',turn_id='p1',event='Stop'),4)
        self.assertEqual([n.id for n in store.roots(10)],['parent'])
        self.assertEqual(store.children('parent',10),[])
        self.assertTrue(store.dismiss_result('parent',store.result_token(store.nodes['parent'])))
        self.assertEqual(store.roots(10),[])

    def test_child_history_preserved_and_real_resume_restores_family(self):
        store=self.family()
        store.ingest(dict(session_id='scout',turn_id='c1',event='Interrupt'),3)
        self.finish_read(store)
        self.assertEqual(store.roots(10),[])
        self.assertEqual(store.nodes['scout'].status,'interrupted')
        store.ingest(dict(session_id='scout',turn_id='c2',event='ResumeDetected'),11)
        self.assertEqual([n.id for n in store.roots(12)],['parent'])
        self.assertEqual([n.id for n in store.children('parent',12)],['scout'])


if __name__=='__main__':unittest.main(verbosity=2)
