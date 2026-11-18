"""Actor/turn state; transport and Codex observation are separate adapters."""
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from codex_bridge import atomic_json

ACTIVE = {'thinking','working','compacting','permission','interrupted'}
BEGINS = {'UserPromptSubmit','SubagentStart','PreCompact','ResumeDetected'}
EVENT_STATUS = {'SessionStart':'idle','UserPromptSubmit':'thinking','PreToolUse':'working',
    'PostToolUse':'working','Stop':'success','TaskCompleteFallback':'success','Interrupt':'interrupted',
    'PreCompact':'compacting','PostCompact':'success','SubagentStart':'working',
    'SubagentStop':'success','SessionEnd':'idle','PermissionRequest':'permission'}


@dataclass
class Node:
    id: str
    parent: str = ''
    title: str = ''
    turn: str = ''
    retired: set = field(default_factory=set)
    active: bool = False
    status: str = 'idle'
    created: float = 0
    changed: float = 0
    last_event: float = 0
    completion: float | None = None
    unread: bool = False
    result: bool = False
    result_completed_at: float | None = None
    payload: dict = field(default_factory=dict)
    rollout: str = ''
    observation_expired: bool = False
    turn_started: float = 0


class FamilyStore:
    def __init__(self, receipts_path=None):
        self.nodes, self.seen = {}, set()
        self.selected = ''
        self.pending = None
        self.receipts_path = Path(receipts_path) if receipts_path else None
        self.dismissed_results = {}
        if self.receipts_path:
            try:
                values = json.loads(self.receipts_path.read_text(encoding='utf-8'))
                if isinstance(values, dict):
                    self.dismissed_results = {actor: value for actor, value in values.items()
                        if isinstance(value, dict) and isinstance(value.get('turn'), str)
                        and type(value.get('completed_at')) in (int, float)
                        and math.isfinite(value['completed_at'])}
            except (OSError, ValueError):
                pass

    def result_token(self, node):
        return (node.turn, node.result_completed_at) if node.result_completed_at is not None else None

    def is_result_dismissed(self, node):
        receipt = self.dismissed_results.get(node.id)
        return bool(receipt and node.result_completed_at is not None and
            ((node.turn and node.turn == receipt['turn']) or
             receipt['completed_at'] >= node.result_completed_at))

    def dismiss_result(self, actor, token):
        node = self.nodes.get(actor)
        if not node or node.parent or not node.unread or token is None or token != self.result_token(node):
            return False
        receipts = dict(self.dismissed_results)
        receipts[actor] = dict(turn=node.turn, completed_at=node.result_completed_at)
        # Commit before changing the live notification, so a failed write can
        # be retried and never claims to survive a restart.
        if self.receipts_path:
            atomic_json(self.receipts_path, receipts)
        self.dismissed_results = receipts
        node.unread = False
        return True

    def ingest(self, p, now):
        session, agent = p.get('session_id',''), p.get('agent_id','')
        if not session:
            return False
        token = p.get('token')
        if token and token in self.seen:
            return False
        if token:
            self.seen.add(token)
        actor, event, turn = agent or session, p.get('event',''), p.get('turn_id','')
        parent = session if agent else p.get('parent_thread_id','')
        node = self.nodes.setdefault(actor, Node(actor, parent, p.get('thread_title') or p.get('prompt_preview') or '线程 '+actor[:8], created=now))
        if parent and parent != actor:
            node.parent = parent
            self.nodes.setdefault(parent, Node(parent, title='线程 '+parent[:8], created=now))
        begins = event in BEGINS
        if turn and turn in node.retired:
            return False
        if now < node.last_event:
            return False
        if node.observation_expired:
            if begins or event in {'PreToolUse','PermissionRequest'} and now >= node.changed:
                node.observation_expired = False
            else:
                return False
        if begins and turn and turn != node.turn:
            if node.turn:
                node.retired.add(node.turn)
            node.turn, node.completion = turn, None
            node.turn_started = now
        elif turn and node.turn and turn != node.turn:
            return False
        if not node.turn:
            node.turn = turn
        if event == 'SessionStart' and node.active:
            return False
        if node.status == 'interrupted' and event not in BEGINS | {'PermissionRequest','SessionEnd'}:
            return False
        if (event in {'PreToolUse','Stop','TaskCompleteFallback'} and node.payload.get('event') == 'PostCompact' and
            now > node.last_event):
            # Compaction may end while the same turn continues. A fresh tool
            # start is authoritative; a late tool result alone cannot resume.
            node.completion = None
        if node.completion is not None and not begins and event in {'PreToolUse','PostToolUse','Stop','SubagentStop','TaskCompleteFallback'}:
            return False
        if node.status == 'compacting' and event in {'PreToolUse','PostToolUse'}:
            return False
        if event == 'PostCompact' and node.status != 'compacting':
            return False
        status = p.get('status') or EVENT_STATUS.get(event,'idle')
        if status != node.status or begins:
            node.changed = now
        node.status, node.last_event, node.payload = status, now, p
        node.active = status in ACTIVE
        if event in {'Stop','SubagentStop','TaskCompleteFallback','SessionEnd','PostCompact'}:
            node.active, node.completion = False, now
        if event in {'Stop','TaskCompleteFallback'} and not node.parent:
            node.result_completed_at = now
            node.unread, node.result = not self.is_result_dismissed(node), True
        if begins:
            node.active, node.completion, node.unread, node.result = True, None, False, False
            node.result_completed_at = None
            if not node.parent:
                self.pending = actor
        if not self.selected:
            self.selected = node.parent or actor
        return True

    def children(self, actor, now):
        parent = self.nodes.get(actor)
        return sorted((n for n in self.nodes.values() if n.parent == actor and
            not (n.status == 'interrupted' and parent and
                 (n.last_event < parent.turn_started or
                  not parent.active and parent.completion is not None)) and
            (n.active or n.completion is not None and now-n.completion < 2.84)), key=lambda n:n.created)

    def roots(self, now):
        return sorted((n for n in self.nodes.values() if not n.parent and
            (n.active or n.unread or self.children(n.id,now))), key=lambda n:n.created)

    def working(self, node, now):
        return node.status != 'interrupted' and (node.active or any(c.active and c.status != 'interrupted' for c in self.children(node.id,now)))

    def reconcile(self, now):
        roots = self.roots(now)
        running = [n for n in roots if self.working(n,now)]
        if self.pending and any(n.id == self.pending for n in running):
            self.selected = self.pending
        elif not any(n.id == self.selected for n in running):
            if running:
                self.selected = max(running,key=lambda n:n.last_event).id
            elif not any(n.id == self.selected and n.active for n in roots):
                paused = [n for n in roots if n.active]
                current = self.nodes.get(self.selected)
                if paused:
                    self.selected = max(paused,key=lambda n:n.last_event).id
                elif not current or current.completion is None or now-current.completion >= 2.84:
                    self.selected = ''
        self.pending = None

    def select(self, actor):
        self.selected, self.pending = actor, None

    def work_tokens(self):
        return {n.id+':'+n.turn for n in self.nodes.values() if n.active and not self.paused(n)}

    def expire_unconfirmed_start(self, actor, now):
        node = self.nodes[actor]
        node.active, node.status, node.changed = False, 'idle', now
        node.observation_expired = True
        # Unknown liveness is neither a completed result nor a celebration.
        node.unread, node.result = False, False

    def paused(self, node):
        parent = self.nodes.get(node.parent)
        return node.status == 'interrupted' or parent is not None and parent.status == 'interrupted'

    def visual(self, node, now):
        if node.parent:
            if self.paused(node):
                return 'idle'
            return 'jump' if node.completion is not None else 'question' if node.status in {'permission','error'} else 'carrot'
        if not node.active and any(c.active and not self.paused(c) for c in self.children(node.id,now)):
            return 'carrot'
        return {'thinking':'reading','working':'carrot','compacting':'packing',
            'interrupted':'question','permission':'question','error':'question','success':'jump'}.get(node.status,'idle')
