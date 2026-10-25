"""Disposable derived Library snapshots; callers must establish authority separately.

No product consumer is wired here. The private owner serializes all calls and
accepts only closed inert projections, never source paths or SurfaceSpec values.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import threading
from pathlib import Path

from evidence_store import redact
from improvement_blobs import check_ancestry, is_link
from improvement_harness2_context import assert_tree_has_no_grader_verdicts
from improvement_harness2_library import Library
from improvement_harness2_tree import SurfaceSpec
from improvement_sandbox import _IDENTITY, _private_directory

_HASH = re.compile(r'[0-9a-f]{64}')
_BOUNDS = {'cue': 1000, 'procedure': 16384, 'evidence_summary': 8192, 'confidence_basis': 4096}
_FIELDS = {'recipe_id', 'manifest_hash', 'verdict', *_BOUNDS}
_VERDICTS = frozenset({'helped', 'hurt', 'no_observed_effect', 'confounded', 'untested'})
_SURFACE = SurfaceSpec(name='derived_recipe_snapshot', always_on=(), always_on_max=0,
                       always_on_cap_reason='No always-on surface', skill_dir='procedures',
                       skill_name_rule='opaque generated digest', trigger_hint='', autotrigger_file='',
                       trigger_line='', subagent_requires_mode=False, plugin_dir=None, hooks_file=None)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _hash(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _text(value, maximum, *, nonempty=False):
    if type(value) is not str or '\0' in value or (nonempty and not value.strip()):
        raise ValueError('invalid_snapshot_text')
    if len(value.encode('utf-8')) > maximum:
        raise ValueError('oversized_snapshot_text')


def _projections(entries):
    if type(entries) is not list or len(entries) > 3:
        raise ValueError('invalid_snapshot_entries')
    result, seen = [], set()
    for item in entries:
        if type(item) is not dict or set(item) != _FIELDS:
            raise ValueError('invalid_snapshot_projection')
        identifier, manifest, verdict = item['recipe_id'], item['manifest_hash'], item['verdict']
        if type(identifier) is not str or not _IDENTITY.fullmatch(identifier) or identifier in seen:
            raise ValueError('invalid_snapshot_recipe_id')
        if type(manifest) is not str or not _HASH.fullmatch(manifest):
            raise ValueError('invalid_snapshot_manifest_hash')
        if type(verdict) is not str or verdict not in _VERDICTS:
            raise ValueError('invalid_snapshot_verdict')
        for field, maximum in _BOUNDS.items():
            _text(item[field], maximum)
        if redact(item) != item:
            raise ValueError('snapshot_contains_credentials')
        assert_tree_has_no_grader_verdicts({'projection.md': '\n'.join(item.values())})
        seen.add(identifier)
        result.append(dict(item))
    if len(_json(result).encode('utf-8')) > 98304:
        raise ValueError('oversized_snapshot_projection')
    names = [_name(item) for item in result]
    if len(set(names)) != len(names):
        raise ValueError('snapshot_name_collision')
    return result


def _name(item):
    # Opaque 128-bit names keep the repeated upstream layout below MAX_PATH on
    # Windows. Full projection/identity hashes still bind returned content.
    return _hash([item['recipe_id'], item['manifest_hash']])[:32]


def _normalized(value):
    # EXPERIENCE/index are generated normalized text, unlike the exact procedure
    # tree. Avoid doubled CRLF when upstream write_text translates LF on Windows.
    return value.replace('\r\n', '\n').replace('\r', '\n')


class RecipeSnapshot:
    """One locked private allocation, readable until closed or poisoned.

    Unexpected filesystem state and vendor failure invalidate publication. A
    failed close remains failed and retryable; it never reports cleanup success.
    """

    def __init__(self, *, brain_id: str, scope_hash: str, engine_config_hash: str, language: str):
        _text(brain_id, 1000, nonempty=True)
        if any(type(value) is not str or not _HASH.fullmatch(value)
               for value in (scope_hash, engine_config_hash)) or language not in ('vi', 'en'):
            raise ValueError('invalid_snapshot_identity')
        self._lock = threading.RLock()
        self._closed = self._poisoned = False
        self._entries = []
        self._identity_hash = _hash([brain_id, scope_hash, engine_config_hash, language])
        self._domain = self._identity_hash[:32]
        self._parent = Path(tempfile.gettempdir()).absolute()
        check_ancestry(self._parent)
        self._parent = self._parent.resolve(strict=True)
        self._parent_identity = self._identity(self._parent)
        self._root = Path(tempfile.mkdtemp(prefix='rs-', dir=self._parent)).absolute()
        self._root_identity = self._identity(self._root)
        self._allowed = self._paths([])
        self._fingerprint = {}
        self._library = Library(self._root, self._domain, _SURFACE)
        try:
            _private_directory(self._root)
            self._vendor(self._library.rebuild_index, _mutation=True)
        except BaseException:
            self._poison()
            self.close()
            raise

    @staticmethod
    def _identity(path):
        info = path.lstat()
        return info.st_dev, info.st_ino

    def _paths(self, entries):
        domain = self._domain
        paths = {domain, f'{domain}/INDEX.md', f'{domain}/harnesses'}
        for item in entries:
            name = _name(item)
            base = f'{domain}/harnesses/{name}'
            paths.update({base, base + '/EXPERIENCE.md', base + '/harness',
                          base + '/harness/procedures', base + '/harness/procedures/recipe-' + name,
                          base + '/harness/procedures/recipe-' + name + '/SKILL.md'})
        return paths

    def _scan(self):
        # Resolve only after rejecting reparse ancestry, and verify the exact
        # allocation and parent identities before any vendor traversal/deletion.
        check_ancestry(self._root)
        if (self._root.parent != self._parent or self._root.resolve(strict=True) != self._root
                or self._identity(self._parent) != self._parent_identity
                or self._identity(self._root) != self._root_identity):
            raise RuntimeError('snapshot_allocation_changed')
        inventory, pending, total = {}, [self._root], 0
        while pending:
            directory = pending.pop()
            check_ancestry(directory)
            with os.scandir(directory) as children:
                for child in children:
                    path = Path(child.path)
                    check_ancestry(path)
                    rel = path.relative_to(self._root).as_posix()
                    if is_link(path) or rel not in self._allowed:
                        raise RuntimeError('unexpected_snapshot_path')
                    info = path.lstat()
                    if stat.S_ISDIR(info.st_mode):
                        inventory[rel] = None
                        pending.append(path)
                    elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                        if info.st_size > 131072:
                            raise RuntimeError('oversized_snapshot_file')
                        total += info.st_size
                        if total > 393216:
                            raise RuntimeError('oversized_snapshot_files')
                        inventory[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
                    else:
                        raise RuntimeError('unexpected_snapshot_node')
                    if len(inventory) > 32:
                        raise RuntimeError('too_many_snapshot_nodes')
        return inventory

    def _check(self):
        if self._scan() != self._fingerprint:
            raise RuntimeError('snapshot_files_changed')

    def _poison(self):
        self._poisoned = True
        self._entries = []

    def _live(self):
        if self._closed or self._poisoned:
            raise RuntimeError('snapshot_unavailable')

    def _vendor(self, operation, *args, _mutation=False, **kwargs):
        self._check()
        try:
            result = operation(*args, **kwargs)
        except BaseException:
            # Known mutation may have partially completed. Remember only a safe
            # generated inventory for cleanup; publication remains poisoned.
            self._poison()
            if _mutation:
                self._fingerprint = self._scan()
            raise
        if _mutation:
            self._fingerprint = self._scan()
        else:
            self._check()
        return result

    def replace(self, entries: list[dict]) -> dict:
        with self._lock:
            self._live()
            projections = _projections(entries)
            cleanup_paths = self._allowed | self._paths(projections)
            try:
                self._check()
                self._allowed = cleanup_paths
                self._vendor(self._library.retain, [_name(item) for item in projections], _mutation=True)
                for item in projections:
                    name = _name(item)
                    tree = {f'procedures/recipe-{name}/SKILL.md': item['procedure']}
                    # Labels keep empty literal fields explicit. The supplied
                    # verdict and confidence are recorded without authentication.
                    experience = {'cue': 'Cue: ' + _normalized(item['cue']),
                                  'lesson': 'Procedure:\n' + _normalized(item['procedure']),
                                  'evidence': 'Evidence: ' + _normalized(item['evidence_summary']),
                                  'confidence': 'Confidence basis: ' + _normalized(item['confidence_basis'])}
                    self._vendor(self._library.add, name, tree, label='derived_snapshot',
                                 why='Supplied verdict: ' + item['verdict'], experience=experience, _mutation=True)
                self._vendor(self._library.rebuild_index, _mutation=True)
                self._allowed = self._paths(projections)
                self._check()
                actual = self._vendor(self._library.entries)
                if actual != sorted(_name(item) for item in projections):
                    raise RuntimeError('snapshot_retention_failed')
                self._entries = projections
                return self._read()
            except BaseException:
                # A swallowed upstream deletion failure must remain cleanable
                # within the already checked old/new generated inventory.
                self._allowed |= cleanup_paths
                self._poison()
                raise

    def _read(self):
        self._check()
        entries = []
        for item in self._entries:
            name = _name(item)
            tree = self._vendor(self._library.tree_of, name)
            if tree != {f'procedures/recipe-{name}/SKILL.md': item['procedure']}:
                raise RuntimeError('snapshot_tree_mismatch')
            self._check()
            experience = (self._library.entry_dir(name) / 'EXPERIENCE.md').read_text(encoding='utf-8')
            entries.append({**item, 'experience_text': experience, 'tree': tree})
        self._check()
        index = self._library.index.read_text(encoding='utf-8')
        self._check()
        identity = {'identity_hash': self._identity_hash, 'entries': entries, 'index_text': index}
        return {'snapshot_hash': _hash(identity), 'entries': copy.deepcopy(entries), 'index_text': index,
                'coverage': 'derived_snapshot', 'authority_status': 'not_checked', 'business_proof': False}

    def read(self) -> dict:
        with self._lock:
            self._live()
            try:
                return self._read()
            except BaseException:
                self._poison()
                raise

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._poison()
            self._check()
            try:
                shutil.rmtree(self._root)
            except OSError:
                remaining = self._scan()
                # A partial delete may only remove previously checked nodes.
                # Never bless changed content or new paths for a retry.
                if any(rel not in self._fingerprint or self._fingerprint[rel] != value
                       for rel, value in remaining.items()):
                    raise RuntimeError('snapshot_cleanup_state_changed')
                self._fingerprint = remaining
                raise
            if self._root.exists() or self._root.is_symlink():
                raise RuntimeError('snapshot_cleanup_failed')
            self._closed = True
            self._fingerprint = {}

    def __enter__(self):
        with self._lock:
            self._live()
            return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
