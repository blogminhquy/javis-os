"""Observed installed release closure and externally reviewed launch admission.

Inventory and self-hashes do not authorize execution. The separate host-reviewed
registration source is intentionally outside this fingerprint. No CLI, account,
SDK client, process creation, .pth or discovered package code is executed here.
Declared-file coverage is not an import sandbox or initial-section proof.
"""
from __future__ import annotations

import ast
import base64
import csv
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import sysconfig


_MAX_FILES = 4096
_MAX_BYTES = 64 * 1024 * 1024
_AUTHORITY = 'improvement_native_qualifications.py'
_SEEDS = ('improvement_native_release.py', 'improvement_native_bootstrap.py',
    'improvement_fixed_worker_launch.py', 'improvement_native_image.py',
    'improvement_native_capture.py', 'improvement_native_capture_win32.py',
    'improvement_image_channel.py', 'improvement_private_channel.py',
    'improvement_native_protocol.py', 'improvement_native_sdk.py',
    'improvement_native_worker.py', 'improvement_native_profile.py',
    'improvement_native_decisions.py', 'improvement_native_observation.py',
    'improvement_query_dispatch.py', 'improvement_read_outcome_broker.py',
    'improvement_read_outcome_proof.py')
_OMIT = {'__pycache__', '_bundled', 'tests', 'test', 'testing', 'docs', 'doc',
         'demos', 'demo', 'examples', 'samples'}
_METADATA = {'METADATA', 'RECORD', 'WHEEL', 'top_level.txt', 'entry_points.txt'}
_COVERAGE = {'authority': 'unknown', 'unlisted_import_exclusion': 'unknown',
             'initial_loaded_sections': 'unknown', 'dynamic_import_closure': 'unknown'}


def _fail(reason='invalid'):
    raise ValueError('native_release_' + reason)


def _copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False))


def _fingerprint(content):
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None: _fail()


def _pin(value):
    fields = {'version', 'provider', 'engine_id', 'model', 'reasoning', 'cli_path', 'cli_hash',
              'cli_version', 'sdk_version', 'profile_version', 'profile_hash'}
    if type(value) is not dict or any(type(key) is not str for key in value) or set(value) != fields: _fail()
    if type(value['version']) is not int or value['version'] != 1: _fail()
    for key in fields - {'version'}:
        if type(value[key]) is not str or not value[key] or '\x00' in value[key] or len(value[key]) > 32766: _fail()
    for key in ('cli_hash', 'profile_hash'): _digest(value[key])
    from improvement_native_bootstrap import _absolute
    _absolute(value['cli_path'])
    if (value['provider'] != 'anthropic-cli' or value['engine_id'] != 'claude-sdk'
            or value['reasoning'] not in ('low', 'medium', 'high', 'xhigh', 'max')): _fail()
    return _copy(value)


def _identity(info):
    # Windows Python3.12 exposes different ctime semantics through stat/fstat.
    # Compare ctime only within the same API, never as cross-API identity.
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _directory(path):
    from improvement_blobs import check_ancestry
    path = Path(path).absolute()
    check_ancestry(path)
    if not path.is_dir(): _fail('directory_unavailable')
    return path


def _read(path, maximum=_MAX_BYTES):
    from improvement_blobs import check_ancestry
    check_ancestry(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > maximum: _fail('file_unavailable')
    with path.open('rb') as reader:
        opened = os.fstat(reader.fileno())
        if _identity(opened) != _identity(before): _fail('file_changed')
        raw = reader.read(maximum + 1)
        after_read = os.fstat(reader.fileno())
        if (len(raw) > maximum or _identity(after_read) != _identity(opened)
                or after_read.st_ctime_ns != opened.st_ctime_ns): _fail('file_changed')
    check_ancestry(path)
    after = path.lstat()
    if _identity(after) != _identity(before) or after.st_ctime_ns != before.st_ctime_ns: _fail('file_changed')
    return raw


def _relative(name):
    if (type(name) is not str or not name or len(name) > 1000 or '\\' in name or ':' in name
            or name.startswith('/') or any(part in ('', '.', '..') or part.endswith((' ', '.')) for part in name.split('/'))):
        _fail('path')
    return name


def _module_name(relative):
    if relative.endswith('/__init__.py'): return relative[:-12].replace('/', '.')
    return relative[:-3].replace('/', '.')


def _imports(raw, relative):
    try: tree = ast.parse(raw, filename=relative)
    except (SyntaxError, ValueError, RecursionError): _fail('source_syntax')
    package = relative.split('/')[:-1]
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level > len(package): _fail('relative_import')
                base = package[:len(package) - node.level + 1]
                prefix = '.'.join([*base, *([node.module] if node.module else [])])
            else: prefix = node.module or ''
            if prefix: found.add(prefix)
            found.update(prefix + '.' + alias.name for alias in node.names if prefix and alias.name != '*')
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            function = node.func
            if ((isinstance(function, ast.Name) and function.id == '__import__')
                    or (isinstance(function, ast.Attribute) and function.attr == 'import_module')):
                name = node.args[0].value
                if type(name) is str and name and not name.startswith('.'): found.add(name)
    return found


def _normalize(name): return re.sub('[-_.]+', '-', name).lower()


def _record_path(name):
    # Installed commands/manuals/completions are not imports and are never
    # followed outside site-packages. Their RECORD bytes remain pinned. Other
    # traversal/absolute paths still refuse discovery.
    parts = PurePosixPath(name).parts
    if parts and parts[0] == '..':
        index = 0
        while index < len(parts) and parts[index] == '..': index += 1
        if index and index < len(parts) and parts[index] == 'Scripts' and '..' not in parts[index:]: return None
        ancillary = (('share', 'man'), ('share', 'doc'), ('share', 'bash-completion', 'completions'),
                     ('share', 'fish', 'vendor_completions.d'), ('share', 'zsh', 'site-functions'))
        tail = parts[index:]
        if (index and tuple(name.split('/')) == parts and '..' not in tail
                and any(len(tail) > len(prefix) and tail[:len(prefix)] == prefix for prefix in ancillary)):
            _relative('/'.join(tail))
            return None
    _relative(name)
    if (any(part in _OMIT for part in parts) or name.endswith(('.pyc', '.pyo', '.exe'))
            or any(part.endswith('.data') for part in parts)): return None
    if parts[0].endswith('.dist-info') and (len(parts) != 2 or parts[1] not in _METADATA): return None
    return name


def _catalog(packages):
    catalog, modules = {}, {}
    directories = sorted(packages.glob('*.dist-info'), key=lambda path: path.name.casefold())
    if len(directories) > _MAX_FILES: _fail('distribution_limit')
    for directory in directories:
        _directory(directory)
        metadata_raw = _read(directory / 'METADATA', 1024 * 1024)
        metadata = BytesParser().parsebytes(metadata_raw)
        if len(metadata.get_all('Name', [])) != 1 or len(metadata.get_all('Version', [])) != 1: _fail('metadata')
        name = _normalize(metadata['Name'])
        if name in catalog: _fail('distribution_collision')
        record = _read(directory / 'RECORD', 16 * 1024 * 1024)
        rows, folded = [], set()
        try:
            for index, row in enumerate(csv.reader(io.StringIO(record.decode('utf-8')))):
                if index >= 32768 or len(row) != 3: _fail('record')
                relative = _record_path(row[0])
                if relative is None: continue
                if relative.casefold() in folded: _fail('record_collision')
                folded.add(relative.casefold()); rows.append((relative, row[1], row[2]))
                parts = relative.split('/')
                if not parts[0].endswith('.dist-info'):
                    top = parts[0].split('.')[0]
                    if top.isidentifier(): modules.setdefault(top, set()).add(name)
                    if len(parts) > 1 and (parts[0] == 'win32' and (len(parts) == 2 or parts[1] == 'lib')):
                        top = parts[-1].split('.')[0]
                        if top.isidentifier(): modules.setdefault(top, set()).add(name)
        except (UnicodeError, csv.Error): _fail('record')
        if directory.name + '/METADATA' not in {row[0] for row in rows} or directory.name + '/RECORD' not in {row[0] for row in rows}:
            _fail('metadata_unrecorded')
        catalog[name] = (metadata, rows, directory.name + '/RECORD', hashlib.sha256(record).hexdigest(),
                         hashlib.sha256(metadata_raw).hexdigest())
    return catalog, modules


def _inventory(source, packages, seeds, *, sdk_version=None):
    """Private inventory primitive; fixtures do not provide launch authority."""
    source, packages = _directory(source), _directory(packages)
    candidates, folded = {}, {}
    from improvement_blobs import check_ancestry
    visited = 0
    for directory, children, files in os.walk(source, followlinks=False):
        check_ancestry(Path(directory))
        visited += 1 + len(children) + len(files)
        if visited > 65536: _fail('source_catalog_limit')
        children[:] = sorted(name for name in children if name not in _OMIT)
        for name in children: check_ancestry(Path(directory) / name)
        for name in sorted(files):
            if not name.endswith('.py'): continue
            path = Path(directory) / name
            relative = _relative(path.relative_to(source).as_posix())
            if relative == _AUTHORITY: continue
            if len(candidates) >= 16384: _fail('source_catalog_limit')
            if relative.casefold() in folded: _fail('source_collision')
            folded[relative.casefold()] = relative
            module = _module_name(relative)
            if module in candidates: _fail('module_collision')
            candidates[module] = relative
    if type(seeds) is not tuple or any(type(name) is not str for name in seeds): _fail('seeds')
    if len({name.casefold() for name in seeds}) != len(seeds): _fail('source_collision')
    pending = set(seeds) - {_AUTHORITY}
    sources, external = {}, set()
    while pending:
        relative = min(pending); pending.remove(relative); _relative(relative)
        if relative in sources: continue
        raw = _read(source / relative)
        sources[relative] = hashlib.sha256(raw).hexdigest()
        if len(sources) > _MAX_FILES: _fail('file_limit')
        for name in _imports(raw, relative):
            if name.split('.')[0] == _AUTHORITY[:-3]: continue
            pieces = name.split('.')
            local = [candidates['.'.join(pieces[:index])] for index in range(1, len(pieces) + 1)
                     if '.'.join(pieces[:index]) in candidates]
            if local: pending.update(local)
            elif pieces[0] not in sys.stdlib_module_names and pieces[0] not in sys.builtin_module_names:
                external.add(pieces[0])
    catalog, modules = _catalog(packages)
    if sdk_version is not None and ('claude-agent-sdk' not in catalog
            or catalog['claude-agent-sdk'][0]['Version'] != sdk_version): _fail('sdk_changed')
    pending_dist = {'claude-agent-sdk': set(), 'pywin32': set()}
    for module in external:
        if module not in modules: _fail('dependency_missing')
        for name in modules[module]: pending_dist.setdefault(name, set())
    from packaging.requirements import Requirement, InvalidRequirement
    from packaging.markers import default_environment
    environment = default_environment()
    environment.update(os_name='nt', sys_platform='win32', platform_system='Windows', platform_machine='AMD64')
    selected = {}
    while pending_dist:
        name = min(pending_dist); extras = pending_dist.pop(name)
        if name not in catalog: _fail('dependency_missing')
        old = selected.get(name)
        if old is not None and extras <= old: continue
        extras = extras | (old or set()); selected[name] = extras
        metadata = catalog[name][0]
        for value in metadata.get_all('Requires-Dist', []):
            try: requirement = Requirement(value)
            except InvalidRequirement: _fail('requirement')
            if requirement.url is not None: _fail('requirement_url')
            if requirement.marker and not any(requirement.marker.evaluate({**environment, 'extra': extra}) for extra in ({''} | extras)):
                continue
            dependency = _normalize(requirement.name)
            if dependency not in catalog: _fail('dependency_missing')
            if requirement.specifier and not requirement.specifier.contains(catalog[dependency][0]['Version'], prereleases=True):
                _fail('dependency_version')
            pending_dist.setdefault(dependency, set()).update(requirement.extras)
    imports, import_folded = {}, {}
    for name in sorted(selected):
        metadata, rows, record_name, record_hash, metadata_hash = catalog[name]
        for relative, recorded, size in rows:
            if relative.casefold() in import_folded: _fail('import_collision')
            if len(sources) + len(imports) >= _MAX_FILES: _fail('file_limit')
            raw = _read(packages.joinpath(*relative.split('/')))
            digest = hashlib.sha256(raw).hexdigest()
            if relative == record_name.rsplit('/', 1)[0] + '/METADATA' and digest != metadata_hash:
                _fail('metadata_changed')
            if relative == record_name:
                if recorded or size: _fail('record_self_hash')
                if digest != record_hash: _fail('record_changed')
            else:
                expected = 'sha256=' + base64.urlsafe_b64encode(bytes.fromhex(digest)).decode('ascii').rstrip('=')
                if recorded != expected or size != str(len(raw)): _fail('installed_file_changed')
            imports[relative] = digest; import_folded[relative.casefold()] = relative
    return dict(sorted(sources.items())), dict(sorted(imports.items()))


def _runtime_pins():
    if os.name != 'nt': raise OSError('native_release_windows_required')
    from improvement_native_bootstrap import _runtime_paths, _same_path
    from improvement_native_image import ImageReadGuard
    import msvcrt
    paths = _runtime_paths()
    if not _same_path(paths['executable'], getattr(sys, '_base_executable', sys.executable)):
        _fail('base_executable_mismatch')
    result = {}
    for name, value in paths.items():
        path = Path(value); digest = hashlib.sha256(_read(path)).hexdigest()
        with ImageReadGuard(path, digest) as guard, path.open('rb') as reader:
            compared = guard.compare_file_handle(msvcrt.get_osfhandle(reader.fileno()))
            if compared['matches'] is not True: _fail('runtime_changed')
            result[name] = {'path': str(path), **{key: compared['actual'][key]
                for key in ('sha256', 'volume_serial_64', 'file_id_128')}}
    if set(result) != {'executable', 'dll'}: _fail('runtime')
    return result


def observe_release(pin, *, source_root=None, site_packages=None):
    """Read a candidate. Override roots are observations, never authorization."""
    pin = _pin(pin)
    from improvement_claude import PROFILE_SOURCES
    from improvement_native_bootstrap import validate_bootstrap_manifest
    source = _directory(Path(__file__).parent if source_root is None else source_root)
    packages = _directory(sysconfig.get_path('purelib') if site_packages is None else site_packages)
    seeds = tuple(sorted((set(PROFILE_SOURCES) | set(_SEEDS)) - {_AUTHORITY}))
    sources, imports = _inventory(source, packages, seeds, sdk_version=pin['sdk_version'])
    current_profile = _fingerprint({name: sources[name] for name in PROFILE_SOURCES if name != _AUTHORITY})
    if current_profile != pin['profile_hash']: _fail('profile_changed')
    runtime = _runtime_pins()
    content = {'version': 1, 'runtime': {key: value['sha256'] for key, value in runtime.items()},
               'source': sources, 'imports': imports}
    manifests = {kind: validate_bootstrap_manifest({'version': 1, 'entrypoint': kind, 'runtime': runtime,
        'source': {'root': str(source), 'files': sources},
        'imports': {'site_packages': str(packages), 'files': imports}}) for kind in ('guardian', 'trial', 'operation')}
    return _copy({'version': 1, 'fingerprint': _fingerprint(content), 'content': content,
                  'manifests': manifests, 'coverage': _COVERAGE})


def qualified_launch(pin, *, kind, scratch):
    """Only a matching external reviewed registration authorizes these pins."""
    pin = _pin(pin)
    from improvement_native_bootstrap import _absolute
    from improvement_fixed_worker_launch import _policy
    from improvement_native_qualifications import REVIEWED_RELEASES
    if type(kind) is not str or kind not in ('trial', 'operation', 'preflight'): _fail()
    _absolute(scratch)
    prefix = (sys.platform, pin['cli_version'], pin['cli_hash'], pin['sdk_version'], pin['profile_version'], pin['profile_hash'])
    candidates = {key: evidence for key, evidence in REVIEWED_RELEASES.items()
                  if type(key) is tuple and len(key) == 7 and key[:6] == prefix}
    if not candidates: raise PermissionError('native_release_unqualified')
    for key, evidence in candidates.items(): _digest(key[-1]); _digest(evidence)
    observed = observe_release(pin)
    evidence = candidates.get((*prefix, observed['fingerprint']))
    if evidence is None: raise PermissionError('native_release_unqualified')
    manifests = observed['manifests']
    return _copy({'guardian_manifest': manifests['guardian'],
        'policy': _policy({'version': 1, 'bootstrap': manifests['trial' if kind == 'preflight' else kind], 'scratch': scratch}),
        'image_policy': {'version': 1, 'path': pin['cli_path'], 'sha256': pin['cli_hash']},
        'release_fingerprint': observed['fingerprint'], 'qualification_hash': evidence})
