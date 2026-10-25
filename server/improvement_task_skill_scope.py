"""Owned ordinary task skill snapshots, never activation or native authority.

The factory requires the actual live host turn and running runtime rows. Header
discovery is bounded and descriptor checked. Selected bytes live in existing M0
encrypted blobs/events; a snapshot is not a revision, improvement grant or view.
Lazy/hub consumers use this private scope; HTTP/native resume remain separate.
"""
from __future__ import annotations

from contextlib import closing
import contextvars
import hashlib
import json
import os
from pathlib import Path
import stat
import threading

import context_runtime as CR
import improvement_store as IM
from improvement_blobs import AssetUnavailable, RevisionBlobs, check_ancestry
from resonance_store import GoalStore, Principal
from skill_asset_io import open_skill_source
import skill_router as SR
import turn_context as TC

_CONSTRUCT = object()
_CURRENT = contextvars.ContextVar('javis_owned_task_skill_scope', default=None)
_SCOPE = 'ordinary_task_skill_scope'
_ASSET = 'ordinary_task_skill_asset'
_HEADER_BYTES = 16384
_MAX_SKILLS = 1000


class ScopeUnavailable(PermissionError):
    """A bound task cannot silently switch to an ordinary mutable-file read."""


def _fail():
    raise ScopeUnavailable('task_skill_scope_unavailable')


def _copy(value):
    return json.loads(IM._json(value))


def _owners(assets, principal):
    if (type(assets) is not IM.ImprovementStore or type(assets.store) is not GoalStore
            or type(assets.blobs) is not RevisionBlobs or type(principal) is not Principal):
        _fail()
    try:
        brain = IM._brain(principal)
        root = Path(brain)
        if not root.is_absolute() or '..' in root.parts or not root.is_dir(): _fail()
        check_ancestry(root)
        if str(root.resolve(strict=True)) != brain: _fail()
    except (OSError, ValueError, AssetUnavailable):
        _fail()
    return root


def _permission(info):
    return [stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid]


def _header(root, slug):
    """One bounded descriptor read; do not persist or interpret any body prefix."""
    try:
        selected = SR.resolve_skill_file(root, slug)
        if selected is None: _fail()
        path = selected.resolve(strict=True)
        relative = path.relative_to(root).as_posix()
        before = path.stat()
        with open_skill_source(root, path, SR.SKILL_ASSET_MAX_BYTES) as handle:
            opened = os.fstat(handle.fileno())
            raw = handle.read(_HEADER_BYTES)
            finished = os.fstat(handle.fileno())
        after = path.stat()
        if (SR._skill_stamp(before) != SR._skill_stamp(opened)
                or SR._skill_stamp(opened) != SR._skill_stamp(finished)
                or SR._skill_stamp(finished) != SR._skill_stamp(after)
                or before.st_ctime_ns != after.st_ctime_ns or opened.st_ctime_ns != finished.st_ctime_ns
                or selected.resolve(strict=True) != path or SR.resolve_skill_file(root, slug) != selected): _fail()
        metadata, frontmatter_hash = SR._frontmatter_header(raw)
        # The ordinary router interprets only these string fields. Preserve all
        # raw translations now rather than rereading a new language later.
        projection = {key: value for key, value in metadata.items() if type(key) is str and type(value) is str
            and (key in ('name', 'description', 'group') or SR._KHOA_NGON_NGU_RE.fullmatch(key))}
        return {'slug': slug, 'relative_path': relative, 'frontmatter_hash': frontmatter_hash,
            'permission': _permission(after), 'metadata': projection}
    except (OSError, ValueError, RuntimeError):
        _fail()


def _inventory(root):
    candidates = set()
    try:
        for relative in SR._READ_BASES:
            base = root / relative
            if not base.exists(): continue
            with os.scandir(base) as entries:
                for entry in entries:
                    if SR._SLUG_RE.fullmatch(entry.name) and entry.is_dir():
                        candidates.add(entry.name)
                        if len(candidates) > _MAX_SKILLS: _fail()
        result = []
        for slug in sorted(candidates):
            if SR.resolve_skill_file(root, slug) is not None:
                result.append(_header(root, slug))
        return result
    except (OSError, ValueError, RuntimeError):
        _fail()


def _project(row, lang):
    metadata = row['metadata']
    return {'slug': row['slug'], 'name': SR.theo_ngon_ngu(metadata, 'name', lang) or row['slug'],
        'description': SR.theo_ngon_ngu(metadata, 'description', lang)[:SR.SKILL_DESC_MAX],
        'group': metadata.get('group') or 'Chung', 'relative_path': row['relative_path'],
        'frontmatter_hash': row['frontmatter_hash']}


def _event_key(scope_hash, slug=None):
    return ('task-skills:' if slug is None else 'task-skill:') + IM._hash([scope_hash, slug])


def _blob(assets, principal, envelope, fields):
    if type(envelope) is not dict or set(envelope) != fields or type(envelope.get('version')) is not int or envelope['version'] != 1:
        raise AssetUnavailable('task_skill_record_changed')
    raw = assets.blobs.read(principal.brain_id, envelope['blob_hash'])
    try: value = json.loads(raw)
    except (ValueError, UnicodeError): raise AssetUnavailable('task_skill_record_changed') from None
    if IM._json(value).encode() != raw: raise AssetUnavailable('task_skill_record_changed')
    return value


class TaskSkillScope:
    def __init__(self, token):
        if token is not _CONSTRUCT: raise TypeError('host_task_skill_scope_factory_required')

    @classmethod
    def open(cls, assets, principal, *, turn_token, runtime, trace):
        root = _owners(assets, principal)
        if (type(turn_token) is not TC.Token or type(runtime) is not CR.ObserveRuntime
                or type(trace) is not CR.TurnTrace or runtime._db is None): _fail()
        self = cls(_CONSTRUCT)
        self._assets, self._principal, self._root = assets, principal, root
        self._turn_token, self._runtime, self._trace = turn_token, runtime, trace
        self._runtime_db = runtime._db
        self._closed = False
        self._lock = threading.RLock()
        self._hub_cache = {}
        self._turn = TC.current()
        self._trace_identity = (trace.task_id, trace.step_id, trace.session_id, trace.channel)
        self._identity = {'version': 1, 'kind': 'ordinary_task_skill_snapshot', 'brain_id': principal.brain_id,
            'actor': principal.by, 'task_id': trace.task_id, 'step_id': trace.step_id,
            'session_id': trace.session_id, 'channel': trace.channel,
            'message_id': (self._turn or {}).get('message_id'), 'agent': (self._turn or {}).get('agent'),
            'runtime_path': str(runtime.path.absolute()), 'store_path': str(assets.store.path.absolute())}
        self._scope_hash = IM._hash(self._identity)
        self._live()
        IM.ensure(assets.store)
        payload = {'scope_hash': self.scope_hash}
        with assets.store._Tx(assets.store) as connection:
            saved = assets._replay(connection, principal.brain_id, _event_key(self.scope_hash), _SCOPE, payload)
            if saved is None:
                inventory = _inventory(root)
                # Reobserve all selected headers after discovery; no mixed header
                # inventory is published if a source changed during the capture.
                if any(_header(root, item['slug']) != item for item in inventory): _fail()
                record = {'version': 1, 'identity': self._identity, 'inventory': inventory}
                blob_hash = assets.blobs.write(principal.brain_id, IM._json(record).encode())
                saved = {'version': 1, 'scope_hash': self.scope_hash, 'inventory_hash': IM._hash(inventory), 'blob_hash': blob_hash}
                self._live()
                assets._event(connection, principal, _event_key(self.scope_hash), _SCOPE, payload, saved)
            record = _blob(assets, principal, saved, {'version', 'scope_hash', 'inventory_hash', 'blob_hash'})
            if (record.get('version') != 1 or record.get('identity') != self._identity
                    or saved['scope_hash'] != self.scope_hash or IM._hash(record.get('inventory')) != saved['inventory_hash']):
                raise AssetUnavailable('task_skill_scope_changed')
            self._inventory = _copy(record['inventory'])
            self._inventory_hash = saved['inventory_hash']
            self._live()
        return self

    @property
    def root(self): return self._root

    @property
    def scope_id(self): return self._scope_hash

    @property
    def scope_hash(self): return self._scope_hash

    @property
    def inventory_hash(self): return self._inventory_hash

    @property
    def registry_revision(self): return 'task-skill-source-v1:' + self.scope_hash + ':' + self.inventory_hash

    def _live(self):
        token, trace, runtime = self._turn_token, self._trace, self._runtime
        if (self._closed or token._binding is None or token._binding is not TC._CURRENT.get()
                or not token._binding.alive or getattr(token._cv, 'var', None) is not TC._CURRENT
                or CR.current_trace() is not trace or TC.current() != self._turn
                or self._turn is None or self._turn.get('kenh') != 'dashboard' or self._turn.get('la_chu') is not True
                or type(self._turn.get('message_id')) is not int or self._turn['message_id'] <= 0
                or self._turn.get('session_id') != trace.session_id or self._turn.get('chat_id') != trace.session_id
                or (trace.task_id, trace.step_id, trace.session_id, trace.channel) != self._trace_identity
                or runtime._db is not self._runtime_db
                or str(runtime.path.absolute()) != self._identity['runtime_path']
                or str(self._assets.store.path.absolute()) != self._identity['store_path']): _fail()
        if _owners(self._assets, self._principal) != self.root: _fail()
        with runtime._lock:
            task = runtime._db.execute('SELECT * FROM runtime_tasks WHERE id=?', (trace.task_id,)).fetchone()
            step = runtime._db.execute('SELECT * FROM runtime_steps WHERE id=?', (trace.step_id,)).fetchone()
            if (task is None or step is None or task['status'] != 'RUNNING' or step['status'] != 'RUNNING'
                    or step['task_id'] != task['id'] or task['brain'] != self._principal.brain_id
                    or task['session_id'] != trace.session_id or task['channel'] != trace.channel
                    or task['version'] != trace.expected_version): _fail()

    def manifests(self, lang=''):
        with self._lock:
            self._live()
            for item in self._inventory:
                self._source(item, require_header=False)
            self._live()
            return [_project(item, lang) for item in self._inventory]

    def _source(self, item, *, require_header=True):
        observed = _header(self.root, item['slug'])
        if (observed['relative_path'] != item['relative_path'] or observed['permission'] != item['permission']
                or require_header and observed['frontmatter_hash'] != item['frontmatter_hash']): _fail()

    def read(self, slug, expected_manifest=None):
        with self._lock:
            self._live()
            item = next((row for row in self._inventory if type(slug) is str and row['slug'] == slug), None)
            if item is None: _fail()
            if expected_manifest is not None:
                if (type(expected_manifest) is not dict or expected_manifest.get('slug') != slug
                        or expected_manifest.get('relative_path') != item['relative_path']
                        or expected_manifest.get('frontmatter_hash') != item['frontmatter_hash']): _fail()
            self._source(item)
            payload = {'scope_hash': self.scope_hash, 'slug': slug}
            with self._assets.store._Tx(self._assets.store) as connection:
                envelope = self._assets._replay(connection, self._principal.brain_id,
                    _event_key(self.scope_hash, slug), _ASSET, payload)
                if envelope is None:
                    import improvement_activation
                    # Pin whatever this turn should see, the owner-applied overlay included.
                    asset = improvement_activation.effective_skill_asset(self.root, slug, connection=connection)
                    if (asset is None or asset.relative_path != item['relative_path']
                            or asset.frontmatter_hash != item['frontmatter_hash']): _fail()
                    content_hash = self._assets.blobs.write(self._principal.brain_id, asset.content)
                    receipt = {'version': 1, 'scope_hash': self.scope_hash, 'brain_id': self._principal.brain_id,
                        'task_id': self._trace.task_id, 'slug': slug, 'relative_path': asset.relative_path,
                        'frontmatter_hash': asset.frontmatter_hash, 'content_hash': content_hash}
                    blob_hash = self._assets.blobs.write(self._principal.brain_id, IM._json(receipt).encode())
                    envelope = {'version': 1, 'scope_hash': self.scope_hash, 'blob_hash': blob_hash}
                    self._source(item); self._live()
                    self._assets._event(connection, self._principal, _event_key(self.scope_hash, slug), _ASSET, payload, envelope)
                receipt, raw = self._read_receipt(self._assets, self._principal, self.scope_hash, slug, connection)
                self._source(item); self._live()
            return SR.SkillAsset(slug, receipt['relative_path'], raw, receipt['content_hash'], receipt['frontmatter_hash'])

    @staticmethod
    def _read_receipt(assets, principal, scope_hash, slug, connection):
        scope = assets._replay(connection, principal.brain_id, _event_key(scope_hash), _SCOPE, {'scope_hash': scope_hash})
        if scope is None: raise AssetUnavailable('task_skill_scope_missing')
        record = _blob(assets, principal, scope, {'version', 'scope_hash', 'inventory_hash', 'blob_hash'})
        if (scope['scope_hash'] != scope_hash or IM._hash(record.get('identity')) != scope_hash
                or record['identity']['brain_id'] != principal.brain_id or record['identity']['actor'] != principal.by
                or IM._hash(record.get('inventory')) != scope['inventory_hash']):
            raise AssetUnavailable('task_skill_scope_changed')
        item = next((row for row in record['inventory'] if row['slug'] == slug), None)
        envelope = assets._replay(connection, principal.brain_id, _event_key(scope_hash, slug), _ASSET,
            {'scope_hash': scope_hash, 'slug': slug})
        if item is None or envelope is None: raise AssetUnavailable('task_skill_pin_missing')
        receipt = _blob(assets, principal, envelope, {'version', 'scope_hash', 'blob_hash'})
        if (set(receipt) != {'version', 'scope_hash', 'brain_id', 'task_id', 'slug', 'relative_path', 'frontmatter_hash', 'content_hash'}
                or type(receipt['version']) is not int or receipt['version'] != 1
                or envelope['scope_hash'] != scope_hash or receipt['scope_hash'] != scope_hash
                or receipt['brain_id'] != principal.brain_id or receipt['task_id'] != record['identity']['task_id']
                or receipt['slug'] != slug or receipt['relative_path'] != item['relative_path']
                or receipt['frontmatter_hash'] != item['frontmatter_hash']):
            raise AssetUnavailable('task_skill_pin_changed')
        raw = assets.blobs.read(principal.brain_id, receipt['content_hash'])
        if SR._frontmatter_header(raw[:_HEADER_BYTES])[1] != receipt['frontmatter_hash']:
            raise AssetUnavailable('task_skill_pin_changed')
        return receipt, raw

    @classmethod
    def read_receipt(cls, assets, principal, scope_hash, slug):
        """Cold immutable provenance only; never restore a live scope or permission."""
        _owners(assets, principal)
        with closing(assets.store._conn()) as connection:
            receipt, _ = cls._read_receipt(assets, principal, scope_hash, slug, connection)
        return _copy(receipt)

    def close(self):
        with self._lock:
            self._closed = True
            self._hub_cache.clear()


def current(root):
    scope = _CURRENT.get()
    if scope is None: return None
    if type(scope) is not TaskSkillScope: _fail()
    with scope._lock:
        scope._live()
        try:
            if Path(root).resolve(strict=True) != scope.root: _fail()
        except (OSError, ValueError): _fail()
    return scope


def has_binding():
    """A suppression hint only, including dead bindings; never grants authority."""
    return _CURRENT.get() is not None


def bind(scope):
    if type(scope) is not TaskSkillScope: _fail()
    with scope._lock: scope._live()
    return _CURRENT.set(scope)


def reset(token):
    _CURRENT.reset(token)
