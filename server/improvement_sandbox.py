"""Host-owned trial workspaces and fixture-only capabilities, with no live dispatcher."""
from __future__ import annotations

import contextlib
import csv
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
import winproc

from improvement_blobs import MAX_ASSET_BYTES, check_ancestry
from improvement_cases import _digest, _fields, _frozen, _text, validate_public_contract
from improvement_store import _SOURCE, _hash, _json
from evidence_store import redact

_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
_DEVICE = re.compile(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])", re.I)
_SOURCE_FIELDS = {"source_version", "data_period", "timezone", "cutoff", "schema"}


class WorkspaceCleanupError(RuntimeError):
    def __init__(self):
        super().__init__("trial_workspace_cleanup_failed")


def _bytes_hash(content):
    return hashlib.sha256(content).hexdigest()


class FixtureBroker:
    """A capability reads only preloaded, hash-verified data for one grant."""

    def __init__(self, fixtures: list[dict], grant_hash: str):
        _digest(grant_hash)
        if not isinstance(fixtures, list) or len(fixtures) > 100:
            raise ValueError("invalid_trial_fixtures")
        self._grant_hash = grant_hash
        self._fixtures, self.events = {}, []
        for fixture in _frozen(fixtures):
            _fields(fixture, {"snapshot_id", "hash", "content", "source"})
            identifier = fixture["snapshot_id"]
            if not isinstance(identifier, str) or not _IDENTITY.fullmatch(identifier) or identifier in self._fixtures:
                raise ValueError("invalid_trial_fixture_id")
            _digest(fixture["hash"])
            if not isinstance(fixture["content"], str) or len(fixture["content"].encode("utf-8")) > MAX_ASSET_BYTES:
                raise ValueError("invalid_trial_fixture_size")
            if _bytes_hash(fixture["content"].encode("utf-8")) != fixture["hash"]:
                raise ValueError("trial_fixture_hash_mismatch")
            _fields(fixture["source"], _SOURCE_FIELDS)
            for value in fixture["source"].values():
                _text(value)
            self._fixtures[identifier] = fixture

    @property
    def grant_hash(self):
        return self._grant_hash

    @property
    def fixtures(self):
        return _frozen(self._fixtures)

    def read(self, capability_id, args: dict, snapshot_version, grant_hash) -> dict:
        valid = isinstance(args, dict) and set(args) == {"snapshot_id"} and isinstance(args.get("snapshot_id"), str)
        fixture = self._fixtures.get(args["snapshot_id"]) if valid else None
        matched = bool(capability_id == "fixture.read" and fixture and grant_hash == self.grant_hash
                       and snapshot_version == fixture["source"]["source_version"])
        event = {"sequence": len(self.events) + 1, "status": "fixture_hit" if matched else "fixture_miss",
                 "snapshot_id": fixture["snapshot_id"] if fixture else None, "capability_id": "fixture.read"}
        self.events.append(dict(event))
        return {**event, **(_frozen(fixture) if matched else {"reason": "fixture_miss"})}


def _manifest(value):
    manifest = _frozen(value)
    if redact(manifest) != manifest:
        raise ValueError("insufficient_source: trial_input_contains_credentials")
    required = {"version", "brain_id", "bundle_hash", "engine_config_hash", "contract_hash", "grant_hash",
                "baseline_context", "public_contract", "assets", "case", "learning_origin"}
    if type(manifest.get('version')) is int and manifest['version'] in (2, 3, 4):
        required.add('effective_view')
    _fields(manifest, required)
    if type(manifest["version"]) is not int or manifest["version"] not in (1, 2, 3, 4, 5):
        raise ValueError("unsupported_trial_input")
    if manifest['version'] in (2, 3, 4):
        view = manifest['effective_view']
        _fields(view, {'view_id', 'view_hash', 'binding_hash'})
        if type(view['view_id']) is not str or not _IDENTITY.fullmatch(view['view_id']):
            raise ValueError('invalid_trial_view')
        _digest(view['view_hash'])
        _digest(view['binding_hash'])
    _text(manifest["brain_id"], 1000)
    for field in ("bundle_hash", "engine_config_hash", "contract_hash", "grant_hash"):
        _digest(manifest[field])
    if manifest["learning_origin"] not in ("trial", "compose", "qualification"):
        raise ValueError("invalid_trial_origin")
    context = manifest["baseline_context"]
    _fields(context, {"content", "hash", "coverage"})
    if (not isinstance(context["content"], str) or len(context["content"].encode("utf-8")) > MAX_ASSET_BYTES
            or context["coverage"] not in ("complete", "unknown")):
        raise ValueError("invalid_trial_context")
    if _bytes_hash(context["content"].encode("utf-8")) != context["hash"]:
        raise ValueError("trial_context_hash_mismatch")
    acceptance = manifest["public_contract"]
    _fields(acceptance, {"content", "hash"})
    _digest(acceptance["hash"])
    validate_public_contract(acceptance["content"])
    if _hash(acceptance["content"]) != acceptance["hash"]:
        raise ValueError("trial_public_contract_hash_mismatch")
    assets = manifest["assets"]
    if not isinstance(assets, list) or not assets or len(assets) > 100:
        raise ValueError("invalid_trial_assets")
    if manifest['version'] in (2, 3, 4) and (len(assets) != 1 or type(assets[0]) is not dict
            or type(assets[0].get('path')) is not str or not assets[0]['path'].startswith('skills/')):
        raise ValueError('invalid_trial_view_assets')
    paths, identities = set(), set()
    for asset in assets:
        _fields(asset, {"id", "path", "hash", "content"})
        path = asset["path"]
        if not isinstance(path, str) or not _SOURCE.fullmatch(path) or _DEVICE.fullmatch(path.split("/")[1].removesuffix(".md")):
            raise ValueError("invalid_trial_asset_path")
        if path.casefold() in paths or not isinstance(asset["id"], str) or not _IDENTITY.fullmatch(asset["id"]) or asset["id"] in identities:
            raise ValueError("duplicate_trial_asset")
        if not isinstance(asset["content"], str) or len(asset["content"].encode("utf-8")) > MAX_ASSET_BYTES:
            raise ValueError("invalid_trial_asset_size")
        if _bytes_hash(asset["content"].encode("utf-8")) != asset["hash"]:
            raise ValueError("trial_asset_hash_mismatch")
        paths.add(path.casefold())
        identities.add(asset["id"])
    case = manifest["case"]
    _fields(case, {"id", "task", "fixtures"})
    if not isinstance(case["id"], str) or not _IDENTITY.fullmatch(case["id"]):
        raise ValueError("invalid_trial_case_id")
    _text(case["task"], MAX_ASSET_BYTES)
    FixtureBroker(case["fixtures"], manifest["grant_hash"])
    return manifest


def _private_directory(path: Path):
    check_ancestry(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    check_ancestry(path)
    if os.name != "nt":
        path.chmod(0o700)
        return
    identity = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True,
                              timeout=10, check=True, creationflags=winproc.no_window())
    sid = list(csv.reader(identity.stdout.splitlines()))[0][1]
    if not re.fullmatch(r"S-1-[0-9-]+", sid):
        raise OSError("workspace_permissions_unavailable")
    permissions = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r",
        f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "/Q"], capture_output=True, timeout=10,
        creationflags=winproc.no_window())
    if permissions.returncode:
        raise OSError("workspace_permissions_unavailable")


def trial_system_prompt(input_manifest):
    manifest = _manifest(input_manifest)
    if manifest['version'] in (3, 4):
        asset, view = manifest['assets'][0], manifest['effective_view']
        args = {'view_id': view['view_id'], 'view_hash': view['view_hash'],
                'asset_id': asset['id'], 'content_hash': asset['hash']}
        assets = ('Read the selected skill using mcp__skill__skill_asset_read with these exact arguments:\n'
                  + _json(args) + '\nUse the returned pinned instructions for this task.')
    else:
        assets = _json(manifest['assets'])
    prompt = (manifest["baseline_context"]["content"] + "\n\n<effective_assets>\n"
              + assets + "\n</effective_assets>\n\n<public_acceptance>\n"
              + _json(manifest["public_contract"]["content"]) + "\n</public_acceptance>")
    if len(prompt.encode("utf-8")) > MAX_ASSET_BYTES:
        raise ValueError("insufficient_source: trial_system_prompt_too_large")
    return prompt


def _effective_hash(manifest):
    value = {"context": manifest["baseline_context"]["hash"], "bundle": manifest["bundle_hash"],
             "assets": [{key: asset[key] for key in ("id", "path", "hash")} for asset in manifest["assets"]]}
    if manifest['version'] in (2, 3, 4):
        value['effective_view'] = manifest['effective_view']
    return _hash(value)


def _atomic(path, content):
    check_ancestry(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".trial-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _try_workspace_lifetime_lock(root, namespace, key):
    """Shared OS primitive; the caller supplies its actual ownership namespace."""
    _private_directory(root)
    directory = root / namespace
    check_ancestry(directory)
    directory.mkdir(exist_ok=True)
    path = directory / (_bytes_hash(key.encode()) + ".lock")
    check_ancestry(path)
    handle = open(path, "a+b", buffering=0)
    try:
        if not handle.seek(0, os.SEEK_END):
            handle.write(b"\0")
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        from improvement_native_lifetime import fence_busy
        if fence_busy(path):
            handle.close()
            return None
    except OSError as error:
        handle.close()
        if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            return None
        raise
    except BaseException:
        handle.close()
        raise
    return handle


@contextlib.contextmanager
def _workspace_mutation_lock(root, key):
    _private_directory(root)
    lock_root = root / ".locks"
    lock_root.mkdir(exist_ok=True)
    lock = lock_root / (_bytes_hash(key.encode()) + ".lock")
    check_ancestry(lock)
    with open(lock, "a+b", buffering=0) as handle:
        if not handle.seek(0, os.SEEK_END):
            handle.write(b"\0")
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


class TrialWorkspace:
    def __init__(self, root: Path):
        self.root = Path(root).absolute()

    def _paths(self, trial_id, attempt):
        if not isinstance(trial_id, str) or not _IDENTITY.fullmatch(trial_id) or type(attempt) is not int or not 1 <= attempt <= 1_000_000:
            raise ValueError("invalid_trial_attempt")
        path = self.root / trial_id / f"attempt-{attempt}"
        journal = self.root / ".journal" / (_bytes_hash(f"{trial_id}:{attempt}".encode()) + ".json")
        check_ancestry(path)
        check_ancestry(journal)
        if not path.resolve().is_relative_to(self.root.resolve()) or path == self.root:
            raise ValueError("invalid_trial_workspace")
        return path, journal

    def _try_lifetime_lock(self, namespace, key):
        """An OS-held lock disappears on host death, unlike the durable journal."""
        return _try_workspace_lifetime_lock(self.root, namespace, key)

    @staticmethod
    def release_execution(handles):
        # Closing releases these kernel locks on both platforms. The worker is
        # launched without inherited handles; only its owning host holds them.
        for handle in reversed(handles):
            handle.close()

    def acquire_execution(self, brain_id, trial_id, attempt):
        self._paths(trial_id, attempt)
        brain = self.acquire_brain_execution(brain_id)
        if brain is None:
            return None
        try:
            workspace = self._try_lifetime_lock(".lifetimes", f"{trial_id}:{attempt}")
            if workspace is None:
                brain.close()
                return None
            return brain, workspace
        except BaseException:
            brain.close()
            raise

    def acquire_brain_execution(self, brain_id):
        """Exclude the actual runner without inventing a workspace identity."""
        _text(brain_id, 1000)
        return self._try_lifetime_lock(".executions", brain_id)

    def _cleanup_record(self, trial_id, attempt, path, journal, expected_receipt):
        if not journal.exists():
            return
        check_ancestry(journal)
        with journal.open("rb") as source:
            raw = source.read(16385)
        if len(raw) > 16384:
            raise ValueError("trial_cleanup_journal_invalid")
        record = json.loads(raw)
        _fields(record, {"state", "input_hash", "receipt"})
        receipt = record["receipt"]
        _fields(receipt, {"trial_id", "attempt", "path", "input_path", "output_root", "input_hash", "effective_hash"})
        _digest(receipt["input_hash"])
        _digest(receipt["effective_hash"])
        if (record["state"] not in ("preparing", "prepared", "cleaned")
                or record["input_hash"] != receipt["input_hash"]
                or type(receipt["attempt"]) is not int or receipt["attempt"] != attempt
                or receipt["trial_id"] != trial_id or receipt["path"] != str(path)
                or receipt["input_path"] != str(path / "input.json")
                or receipt["output_root"] != str(path / "outputs")
                or (expected_receipt is not None and receipt != expected_receipt)):
            raise ValueError("trial_cleanup_journal_invalid")
        return record

    def cleanup_proven(self, trial_id, attempt, expected_receipt):
        """Clean and verify one recorded attempt while the caller holds its brain lock.

        False means a live attempt holds its lifetime. Kept cleaned journals are
        replay protection; verify their exact bounded receipt, never erase them.
        This method grants no database authority to release experiment capacity.
        """
        path, journal = self._paths(trial_id, attempt)
        handle = self._try_lifetime_lock(".lifetimes", f"{trial_id}:{attempt}")
        if handle is None:
            return False
        try:
            with self._lock(trial_id, attempt):
                self._cleanup_record(trial_id, attempt, path, journal, expected_receipt)
                self._cleanup_in_lock(path, journal)
                record = self._cleanup_record(trial_id, attempt, path, journal, expected_receipt)
                if path.exists() or (record is not None and record["state"] != "cleaned"):
                    raise ValueError("trial_cleanup_incomplete")
                return True
        finally:
            handle.close()

    def try_cleanup(self, trial_id, attempt):
        """Recovery must never remove a workspace still held by a live runner."""
        path, journal = self._paths(trial_id, attempt)
        if not path.exists() and not journal.exists():
            return False
        handle = self._try_lifetime_lock(".lifetimes", f"{trial_id}:{attempt}")
        if handle is None:
            return False
        try:
            self.cleanup(trial_id, attempt)
            return True
        except Exception:
            raise WorkspaceCleanupError() from None
        finally:
            handle.close()

    @contextlib.contextmanager
    def _lock(self, trial_id, attempt):
        with _workspace_mutation_lock(self.root, f"{trial_id}:{attempt}"):
            yield

    def prepare(self, trial_id, attempt, input_manifest):
        manifest = _manifest(input_manifest)
        encoded = _json(manifest).encode("utf-8")
        path, journal = self._paths(trial_id, attempt)
        with self._lock(trial_id, attempt):
            if journal.exists():
                prior = json.loads(journal.read_text(encoding="utf-8"))
                if prior["input_hash"] != _bytes_hash(encoded) or prior["state"] != "prepared":
                    raise ValueError("trial_workspace_conflict")
                self.validate(prior["receipt"])
                return prior["receipt"]
            if path.exists():
                raise ValueError("trial_workspace_orphaned")
            _private_directory(path)
            outputs = path / "outputs"
            outputs.mkdir(mode=0o700)
            inputs = path / "input.json"
            receipt = {"trial_id": trial_id, "attempt": attempt, "path": str(path), "input_path": str(inputs),
                       "output_root": str(outputs), "input_hash": _bytes_hash(encoded),
                       "effective_hash": _effective_hash(manifest)}
            journal.parent.mkdir(exist_ok=True)
            record = {"state": "preparing", "input_hash": receipt["input_hash"], "receipt": receipt}
            _atomic(journal, _json(record).encode())
            _atomic(inputs, encoded)
            inputs.chmod(0o400)
            record["state"] = "prepared"
            _atomic(journal, _json(record).encode())
            return receipt

    def validate(self, receipt):
        _fields(receipt, {"trial_id", "attempt", "path", "input_path", "output_root", "input_hash", "effective_hash"})
        path, journal = self._paths(receipt["trial_id"], receipt["attempt"])
        if receipt["path"] != str(path) or receipt["input_path"] != str(path / "input.json") or receipt["output_root"] != str(path / "outputs"):
            raise ValueError("trial_workspace_mismatch")
        check_ancestry(Path(receipt["input_path"]))
        raw = Path(receipt["input_path"]).read_bytes()
        if _bytes_hash(raw) != receipt["input_hash"]:
            raise ValueError("trial_input_changed")
        record = json.loads(journal.read_text(encoding="utf-8"))
        if record["state"] != "prepared" or record["receipt"] != receipt:
            raise ValueError("trial_journal_mismatch")
        manifest = _manifest(json.loads(raw))
        if receipt["effective_hash"] != _effective_hash(manifest):
            raise ValueError("trial_effective_hash_mismatch")
        return manifest

    def cleanup(self, trial_id, attempt):
        path, journal = self._paths(trial_id, attempt)
        if not path.exists() and not journal.exists():
            return
        with self._lock(trial_id, attempt):
            self._cleanup_record(trial_id, attempt, path, journal, None)
            self._cleanup_in_lock(path, journal)

    def _cleanup_in_lock(self, path, journal):
        # Check the final resolved target immediately before recursive removal on Windows and Unix.
        check_ancestry(path)
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root.resolve()) or resolved == self.root.resolve():
            raise ValueError("invalid_trial_cleanup_target")

        def unlock(function, name, error):
            candidate = Path(name)
            check_ancestry(candidate)
            if not candidate.resolve().is_relative_to(resolved):
                raise ValueError("invalid_trial_cleanup_child")
            candidate.chmod(stat.S_IREAD | stat.S_IWRITE)
            function(name)

        if path.exists():
            shutil.rmtree(path, onexc=unlock)
        if journal.exists():
            record = json.loads(journal.read_text(encoding="utf-8"))
            record["state"] = "cleaned"
            _atomic(journal, _json(record).encode())


def worker_environment(workspace_root: Path, *, auth_home: Path | None = None) -> dict:
    """Keep host native login discovery, without passing server credentials or authority."""
    workspace_root = Path(workspace_root).absolute()
    home = Path(auth_home) if auth_home is not None else Path.home()
    environment = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT") if name in os.environ}
    standard = os.defpath.split(os.pathsep)
    if os.name == "nt":
        windows = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
        standard += [str(windows), str(windows / "System32")]
    else:
        standard.append("/usr/local/bin")
    environment.update({"PATH": os.pathsep.join(dict.fromkeys([str(Path(sys.executable).parent), *standard])),
        "HOME": str(home), "USERPROFILE": str(home), "TEMP": str(workspace_root / "tmp"), "TMP": str(workspace_root / "tmp"),
        "JAVIS_STATE_DIR": str(workspace_root / "host-state"), "BRAINS_DIR": str(workspace_root / "empty-brains"),
        "OBSIDIAN_VAULT_PATH": str(workspace_root / "empty-vault"), "BRAIN_PATH": str(workspace_root / "empty-brain"),
        "SOURCES_PATH": str(workspace_root / "empty-sources"), "ENABLE_TOOL_SEARCH": "false",
        "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1", "DISABLE_NON_ESSENTIAL_MODEL_CALLS": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "PYTHONIOENCODING": "utf-8"})
    if os.name == "nt":
        environment.update(APPDATA=str(home / "AppData" / "Roaming"), LOCALAPPDATA=str(home / "AppData" / "Local"))
    return environment
