"""Read-only, bounded adapters for Codex local metadata and lifecycle logs."""
import json
import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path
import io
import zstandard
from family_store import FamilyStore

UNCONFIRMED_START_GRACE = 45
INTERNAL_PROMPT_PREFIXES = (
    'This is an app-generated request for a suggested next user message.',
    '# Overview\n\nGenerate 0 to 3 hyperpersonalized suggestions for what this user can do with Codex in ',
)


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


def rollout_file(path):
    """Codex retains the original metadata path after archiving as .jsonl.zst."""
    path = Path(path)
    if path.suffix == '.zst':
        return path
    compressed = Path(str(path)+'.zst')
    if path.is_file() and (path.stat().st_size or not compressed.is_file()):
        return path
    return compressed


def lifecycle_in_lines(lines):
    latest = None
    for line in lines:
        try:
            row = json.loads(line)
            p = row.get('payload',{})
            if row.get('type') == 'event_msg' and p.get('type') in {'task_started','task_complete','turn_aborted'} and p.get('turn_id'):
                when = timestamp(row.get('timestamp'),None)
                if when is not None and (latest is None or when >= latest[2]):
                    latest = p['type'], p['turn_id'], when
        except (ValueError, AttributeError):
            continue
    return latest


def compressed_lifecycle(path):
    # Inspect lifecycle rows throughout the bounded archive, retaining no chat
    # text. Oversized tool-output rows are skipped without unbounded buffering.
    if path.stat().st_size > 64*1024*1024:
        return None
    latest, total, discard = None, 0, False
    with path.open('rb') as raw, zstandard.ZstdDecompressor(max_window_size=64*1024*1024).stream_reader(raw,read_across_frames=True) as reader:
        with io.BufferedReader(reader) as stream:
            while True:
                line = stream.readline(1024*1024+1)
                if not line:
                    break
                total += len(line)
                if total > 128*1024*1024:
                    return None
                if discard or len(line)>1024*1024:
                    discard = not line.endswith(b'\n')
                    continue
                observed = lifecycle_in_lines([line.decode('utf-8-sig',errors='replace')])
                if observed and (latest is None or observed[2]>=latest[2]):
                    latest = observed
    return latest


def latest_lifecycle(path):
    try:
        path = rollout_file(path)
        if path.suffix == '.zst':
            return compressed_lifecycle(path)
        with path.open('rb') as stream:
            stream.seek(0,2)
            size, span = stream.tell(), 262144
            while True:
                offset = max(0,size-span)
                stream.seek(offset)
                lines = stream.read().decode('utf-8',errors='replace').splitlines()
                if offset:
                    lines = lines[1:]
                observed = lifecycle_in_lines(lines)
                if observed:
                    return observed
                if not offset or span >= 16777216:
                    return None
                span *= 2
    except (OSError,zstandard.ZstdError):
        return None


class CodexObserver:
    def __init__(self, store: FamilyStore, state_dir, home=None, enabled=True):
        self.store, self.state_dir = store, Path(state_dir)
        self.home = Path(home or os.environ.get('CODEX_HOME') or Path.home()/'.codex')
        self.enabled = enabled
        self.files, self.modifications, self.opened = set(), {}, set()
        self.log_checked_at, self.log_valid = {}, {}
        self.metadata_at, self.observed_at = 0, 0
        self.metadata = {}
        self.metadata_lookups = set()
        self.internal_sessions = set()
        self.unread_supported = False

    def refresh_metadata(self, now, actors=()):
        if not self.enabled:
            return
        refresh = now-self.metadata_at >= 15
        requested = {a for a in actors if isinstance(a,str) and a}
        requested.update(n.id for n in self.store.nodes.values() if n.active)
        missing = requested - (set() if refresh else self.metadata_lookups)
        if not refresh and not missing:
            return
        if refresh:
            self.metadata_at = now
            self.metadata_lookups = set()
        self.metadata_lookups.update(missing)
        try:
            databases = sorted(self.home.glob('state_*.sqlite'),key=lambda p:p.stat().st_mtime,reverse=True)
            if not databases:
                return
            metadata = {} if refresh else dict(self.metadata)
            with closing(sqlite3.connect(databases[0].as_uri()+'?mode=ro',uri=True,timeout=.2)) as db:
                cols = {row[1] for row in db.execute('PRAGMA table_info(threads)')}
                wanted = [c for c in ('id','name','title','source','rollout_path') if c in cols]
                if 'id' not in cols:
                    return
                order = ' ORDER BY updated_at DESC' if 'updated_at' in cols else ''
                query = 'SELECT '+','.join(wanted)+' FROM threads'
                rows = list(db.execute(query+order+' LIMIT 256')) if refresh else []
                # Keep recent discovery bounded, but resolve every actor that
                # actually emitted hooks before classifying it as unregistered.
                ids = sorted(missing)
                for offset in range(0,len(ids),128):
                    batch = ids[offset:offset+128]
                    rows.extend(db.execute(query+' WHERE id IN ('+','.join('?' for _ in batch)+')',batch))
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
            self.metadata_lookups.update(metadata)
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
        preview = str(p.get('prompt_preview') or '').replace('\r\n', '\n')
        title_request = (p.get('internal_request_kind') == 'conversation_title' or
                         (preview.startswith('User\'s request:\n"""\n') and '\n"""\n\nGener' in preview))
        # Memory consolidation runs in the dedicated memory directory. Require
        # both the exact instruction header and directory, never a title alone.
        cwd = str(p.get('cwd') or '').replace('\\', '/').rstrip('/')
        memory_dir = str(self.home / 'memories').replace('\\', '/').rstrip('/')
        memory_request = (preview.replace('\r\n', '\n').startswith(
            '## Memory Writing Agent: Phase 2 (Consolidation)\nYou are a Memory Writing Agent.') and
            (cwd.casefold() == memory_dir.casefold() or cwd.casefold().endswith('/.codex/memories')))
        # Suggestions/titles must be unregistered. Memory consolidation can have
        # a metadata row, but requires both the exact prompt and dedicated cwd.
        # Preserve explicit and metadata-derived child relationships.
        if (actor and p.get('event') == 'UserPromptSubmit' and (actor not in self.metadata or memory_request) and
            not p.get('agent_id') and not p.get('parent_thread_id') and
            not self.metadata.get(actor, {}).get('parent_thread_id') and
            not getattr(self.store.nodes.get(actor), 'parent', '') and
            (memory_request or title_request or preview.startswith(INTERNAL_PROMPT_PREFIXES))):
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
        directory = self.state_dir/'family-events'
        pending = []
        for file in sorted(directory.glob('*.json')):
            if file.name in self.files:
                continue
            try:
                p = json.loads(file.read_text(encoding='utf-8-sig'))
                if isinstance(p,dict):
                    pending.append((file.name,p))
            except (OSError,ValueError,TypeError):
                pass # Retry partial reads, never mark unreadable events seen.
        self.refresh_metadata(now,(p.get('agent_id') or p.get('session_id') for _,p in pending))
        for name,p in pending:
            self.ingest(p)
            self.files.add(name)
        if self.enabled and now-self.observed_at >= 1:
            self.observed_at = now
            candidates = dict(self.metadata)
            candidates.update({n.id:{'rollout':n.rollout} for n in self.store.nodes.values() if n.rollout})
            for actor, meta in candidates.items():
                path = meta.get('rollout')
                if not path:
                    continue
                try:
                    actual = rollout_file(path)
                    info = actual.stat()
                    modified = (str(actual),info.st_mtime_ns,info.st_size)
                except OSError:
                    continue
                node = self.store.nodes.get(actor)
                retry = now-self.log_checked_at.get(actor,0) >= 15 and (not self.log_valid.get(actor) or node is not None and node.active)
                if self.modifications.get(actor) == modified and not retry:
                    continue
                self.modifications[actor] = modified
                self.log_checked_at[actor] = now
                observed = latest_lifecycle(path)
                self.log_valid[actor] = observed is not None
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
                    not (node.rollout and rollout_file(node.rollout).is_file()) and
                    now-node.last_event > UNCONFIRMED_START_GRACE):
                    self.store.expire_unconfirmed_start(node.id,now)
        self.store.reconcile(now)
