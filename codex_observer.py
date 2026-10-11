"""Read-only, bounded adapters for Codex local metadata and lifecycle logs."""
import json
import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path
from family_store import FamilyStore

UNCONFIRMED_START_GRACE = 45
SUGGESTED_REPLY_PREFIX = 'This is an app-generated request for a suggested next user message.'


def timestamp(value, fallback=0):
    try:
        return datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()
    except (ValueError, TypeError):
        return fallback


def unread_ids(value):
    state = value.get('electron-thread-read-state-v1', {})
    identities = state.get('unreadByIdentity')
    if state.get('version') != 1 or not isinstance(identities, dict) or len(identities) != 1:
        return None
    hosts = next(iter(identities.values()))
    if not isinstance(hosts, dict):
        return None
    local = [ids for key, ids in hosts.items() if key.startswith('local:')]
    if len(local) != 1 or not isinstance(local[0], list) or not all(isinstance(i,str) for i in local[0]):
        return None
    return set(local[0])


def latest_lifecycle(path):
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0,2)
            size, span = stream.tell(), 262144
            while True:
                offset = max(0,size-span)
                stream.seek(offset)
                lines = stream.read().decode('utf-8',errors='replace').splitlines()
                if offset:
                    lines = lines[1:]
                for line in reversed(lines):
                    try:
                        row = json.loads(line)
                        p = row.get('payload',{})
                        if row.get('type') == 'event_msg' and p.get('type') in {'task_started','task_complete','turn_aborted'} and p.get('turn_id'):
                            return p['type'], p['turn_id'], timestamp(row.get('timestamp'))
                    except (ValueError, AttributeError):
                        continue
                if not offset or span >= 16777216:
                    return None
                span *= 2
    except OSError:
        return None


class CodexObserver:
    def __init__(self, store: FamilyStore, state_dir, home=None, enabled=True):
        self.store, self.state_dir = store, Path(state_dir)
        self.home = Path(home or os.environ.get('CODEX_HOME') or Path.home()/'.codex')
        self.enabled = enabled
        self.files, self.modifications, self.opened = set(), {}, set()
        self.metadata_at, self.observed_at = 0, 0
        self.metadata = {}
        self.internal_sessions = set()
        self.unread_supported = False

    def refresh_metadata(self, now):
        if not self.enabled or now-self.metadata_at < 15:
            return
        self.metadata_at = now
        databases = sorted(self.home.glob('state_*.sqlite'),key=lambda p:p.stat().st_mtime,reverse=True)
        if not databases:
            return
        try:
            metadata = {}
            with closing(sqlite3.connect(databases[0].as_uri()+'?mode=ro',uri=True,timeout=.2)) as db:
                cols = {row[1] for row in db.execute('PRAGMA table_info(threads)')}
                wanted = [c for c in ('id','name','title','source','rollout_path') if c in cols]
                if 'id' not in cols:
                    return
                order = ' ORDER BY updated_at DESC' if 'updated_at' in cols else ''
                rows = db.execute('SELECT '+','.join(wanted)+' FROM threads'+order+' LIMIT 256')
                for values in rows:
                    row = dict(zip(wanted,values))
                    parent = ''
                    try:
                        source = json.loads(row.get('source') or '{}')
                        parent = source.get('subagent',{}).get('thread_spawn',{}).get('parent_thread_id','')
                    except (ValueError, AttributeError):
                        pass
                    metadata[row['id']] = {'thread_title':row.get('name') or row.get('title') or '',
                        'parent_thread_id':parent,'rollout':row.get('rollout_path') or ''}
            self.metadata = metadata
        except (sqlite3.Error,OSError):
            return
        for actor, meta in self.metadata.items():
            node = self.store.nodes.get(actor)
            if node:
                if meta['thread_title']:
                    node.title = meta['thread_title']
                if meta['parent_thread_id']:
                    node.parent = meta['parent_thread_id']
                if meta['rollout']:
                    node.rollout = meta['rollout']

    def ingest(self, value):
        p = dict(value)
        actor = p.get('agent_id') or p.get('session_id')
        # The app's suggested-reply sessions emit normal hooks but are not
        # user tasks. Only suppress explicitly marked, unregistered sessions.
        if (p.get('event') == 'UserPromptSubmit' and actor not in self.metadata and
            not p.get('agent_id') and not p.get('parent_thread_id') and
            str(p.get('prompt_preview') or '').startswith(SUGGESTED_REPLY_PREFIX)):
            self.internal_sessions.add(actor)
            self.store.nodes.pop(actor,None) # SessionStart may already exist.
            if self.store.selected == actor:
                self.store.selected = ''
            if self.store.pending == actor:
                self.store.pending = None
        if actor in self.internal_sessions:
            return False
        meta = self.metadata.get(actor,{})
        for key in ('thread_title','parent_thread_id'):
            if meta.get(key):
                p[key] = meta[key]
        when = p.get('received_at') or timestamp(p.get('updated_at'),time.time())
        accepted = self.store.ingest(p,float(when))
        if accepted and actor in self.store.nodes:
            rollout = meta.get('rollout') or p.get('transcript_path')
            if rollout:
                self.store.nodes[actor].rollout = rollout
        return accepted

    def poll(self, now=None):
        now = time.time() if now is None else now
        self.refresh_metadata(now)
        directory = self.state_dir/'family-events'
        for file in sorted(directory.glob('*.json')):
            if file.name in self.files:
                continue
            try:
                p = json.loads(file.read_text(encoding='utf-8-sig'))
                self.ingest(p)
                self.files.add(file.name)
            except (OSError,ValueError,TypeError):
                pass # Retry partial reads, never mark unreadable events seen.
        if self.enabled and now-self.observed_at >= 1:
            self.observed_at = now
            candidates = dict(self.metadata)
            candidates.update({n.id:{'rollout':n.rollout} for n in self.store.nodes.values() if n.rollout})
            for actor, meta in candidates.items():
                path = meta.get('rollout')
                if not path:
                    continue
                try:
                    modified = Path(path).stat().st_mtime_ns
                except OSError:
                    continue
                if self.modifications.get(actor) == modified:
                    continue
                self.modifications[actor] = modified
                observed = latest_lifecycle(path)
                if not observed:
                    continue
                kind, turn, when = observed
                node = self.store.nodes.get(actor)
                if node is None and (kind != 'task_started' or now-when > 600):
                    continue
                if node and when <= node.last_event:
                    continue
                event = {'task_started':'ResumeDetected','task_complete':'TaskCompleteFallback','turn_aborted':'Interrupt'}[kind]
                if node and event == 'ResumeDetected' and node.turn == turn and node.status != 'interrupted':
                    continue
                if node and node.turn != turn and event != 'ResumeDetected':
                    self.ingest({'session_id':actor,'event':'ResumeDetected','status':'working','turn_id':turn,'received_at':when-.001,'token':'observed-start-'+actor+turn})
                self.ingest({'session_id':actor,'event':event,'status':{'ResumeDetected':'working','Interrupt':'interrupted','TaskCompleteFallback':'success'}[event],
                    'turn_id':turn,'received_at':when,'token':'observed-'+actor+kind+turn})
            try:
                value = json.loads((self.home/'.codex-global-state.json').read_text(encoding='utf-8'))
                unread = unread_ids(value)
                self.unread_supported = unread is not None
                if unread is not None:
                    for node in self.store.nodes.values():
                        if node.result and not node.parent and now-(node.completion or now) > 3:
                            node.unread = node.id in unread and node.id not in self.opened
            except (OSError,ValueError):
                self.unread_supported = False
            for node in self.store.nodes.values():
                if (node.active and node.status == 'thinking' and
                    node.payload.get('event') == 'UserPromptSubmit' and
                    node.id not in self.metadata and
                    not (node.rollout and Path(node.rollout).is_file()) and
                    now-node.last_event > UNCONFIRMED_START_GRACE):
                    self.store.expire_unconfirmed_start(node.id,now)
        self.store.reconcile(now)
