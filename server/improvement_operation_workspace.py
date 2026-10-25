"""Real operation-ID workspace/journal; its brain lock is the actual solver lock."""
from __future__ import annotations

import json
import shutil
import stat
import threading
from pathlib import Path

from improvement_blobs import MAX_ASSET_BYTES, check_ancestry
from improvement_experiment_protocol import _id
from improvement_operation_protocol import operation_materialization
from improvement_sandbox import (TrialWorkspace, _private_directory, _atomic, _bytes_hash,
                                  _try_workspace_lifetime_lock, _workspace_mutation_lock)
from improvement_store import _json, _hash

_RECEIPT = {"operation_id", "attempt", "role", "purpose", "path", "input_path", "output_root", "input_hash", "request_hash"}


class OperationWorkspaceCleanupError(RuntimeError):
    def __init__(self):
        super().__init__("operation_workspace_cleanup_failed")


class OperationWorkspace:
    def __init__(self, root, *, brain_barrier):
        if type(brain_barrier) is not TrialWorkspace:
            raise TypeError("concrete_solver_brain_barrier_required")
        self.root = Path(root).absolute()
        if self.root != brain_barrier.root.parent / "operations":
            raise ValueError("operation_workspace_root_mismatch")
        check_ancestry(self.root)
        self.brain_barrier = brain_barrier
        self._owned = {}
        self._ownership = threading.RLock()

    def _paths(self, identifier, attempt):
        _id(identifier)
        if type(attempt) is not int or attempt not in (1, 2):
            raise ValueError("invalid_operation_attempt")
        path = self.root / identifier / ("attempt-" + str(attempt))
        journal = self.root / ".journal" / (_bytes_hash((identifier + ":" + str(attempt)).encode()) + ".json")
        check_ancestry(path)
        check_ancestry(journal)
        if not path.resolve().is_relative_to(self.root.resolve()) or path == self.root:
            raise ValueError("invalid_operation_workspace")
        return path, journal

    def acquire_execution(self, brain, identifier, attempt):
        self._paths(identifier, attempt)
        handle = self.brain_barrier.acquire_brain_execution(brain)
        if handle is None:
            return None
        try:
            lifetime = _try_workspace_lifetime_lock(self.root, ".lifetimes", identifier + ":" + str(attempt))
            if lifetime is None:
                handle.close()
                return None
            handles = handle, lifetime
            with self._ownership:
                self._owned[id(handles)] = (handles, identifier, attempt)
            return handles
        except BaseException:
            handle.close()
            raise

    def release_execution(self, handles):
        with self._ownership:
            entry = self._owned.get(id(handles))
            if entry is None or entry[0] is not handles:
                raise ValueError("operation_lifetime_unowned")
            TrialWorkspace.release_execution(handles)
            del self._owned[id(handles)]

    def cleanup_owned(self, identifier, attempt, expected, handles):
        """Runner calls only after worker/checker close, while both locks remain held."""
        with self._ownership:
            entry = self._owned.get(id(handles))
            if (entry is None or entry[0] is not handles or entry[1:] != (identifier, attempt)
                    or any(handle.closed for handle in handles)):
                raise ValueError("operation_lifetime_unowned")
            if expected is None:
                path, journal = self._paths(identifier, attempt)
                record = self._journal(identifier, attempt, path, journal)
                expected = record["receipt"] if record is not None else None
            return self._cleanup(identifier, attempt, expected)

    def _lock(self, identifier, attempt):
        return _workspace_mutation_lock(self.root, identifier + ":" + str(attempt))

    def _journal(self, identifier, attempt, path, journal, expected=None):
        if not journal.exists():
            return None
        check_ancestry(journal)
        with journal.open("rb") as source:
            raw = source.read(16385)
        if len(raw) > 16384:
            raise ValueError("invalid_operation_journal")
        record = json.loads(raw)
        if type(record) is not dict or set(record) != {"state", "input_hash", "receipt"}:
            raise ValueError("invalid_operation_journal")
        receipt = record["receipt"]
        if (type(receipt) is not dict or set(receipt) != _RECEIPT or record["state"] not in ("preparing", "prepared", "cleaned")
                or receipt["operation_id"] != identifier or type(receipt["attempt"]) is not int or receipt["attempt"] != attempt
                or receipt["path"] != str(path) or receipt["input_path"] != str(path / "input.json")
                or receipt["output_root"] != str(path / "outputs") or receipt["input_hash"] != record["input_hash"]
                or (receipt["role"], receipt["purpose"]) not in (("improver", "improve_propose"),
                    ("semantic_reviewer", "improve_evaluate"), ("composer", "improve_compose"))
                or (expected is not None and (type(expected) is not dict or set(expected) != _RECEIPT
                                              or _json(receipt) != _json(expected)))):
            raise ValueError("invalid_operation_journal")
        from improvement_experiment_protocol import _digest
        _digest(receipt["input_hash"])
        _digest(receipt["request_hash"])
        return record

    def prepare(self, identifier, attempt, value):
        manifest = operation_materialization(value)
        if manifest["operation_id"] != identifier:
            raise ValueError("operation_identity_changed")
        raw = _json(manifest).encode("utf-8")
        path, journal = self._paths(identifier, attempt)
        with self._lock(identifier, attempt):
            prior = self._journal(identifier, attempt, path, journal)
            if prior is not None:
                if prior["state"] != "prepared" or prior["input_hash"] != _bytes_hash(raw):
                    raise ValueError("operation_workspace_conflict")
                self.validate(prior["receipt"])
                return prior["receipt"]
            if path.exists():
                raise ValueError("operation_workspace_orphaned")
            _private_directory(path)
            (path / "outputs").mkdir(mode=0o700)
            receipt = {"operation_id": identifier, "attempt": attempt, "role": manifest["request"]["role"],
                "purpose": manifest["request"]["purpose"], "path": str(path), "input_path": str(path / "input.json"),
                "output_root": str(path / "outputs"), "input_hash": _bytes_hash(raw), "request_hash": _hash(manifest["request"])}
            journal.parent.mkdir(exist_ok=True)
            record = {"state": "preparing", "input_hash": receipt["input_hash"], "receipt": receipt}
            _atomic(journal, _json(record).encode())
            _atomic(path / "input.json", raw)
            (path / "input.json").chmod(0o400)
            record["state"] = "prepared"
            _atomic(journal, _json(record).encode())
            return receipt

    def validate(self, receipt):
        if type(receipt) is not dict or set(receipt) != _RECEIPT:
            raise ValueError("invalid_operation_receipt")
        path, journal = self._paths(receipt["operation_id"], receipt["attempt"])
        record = self._journal(receipt["operation_id"], receipt["attempt"], path, journal, receipt)
        if record is None or record["state"] != "prepared":
            raise ValueError("operation_workspace_unprepared")
        inputs = path / "input.json"
        check_ancestry(inputs)
        with inputs.open("rb") as source:
            raw = source.read(2 * MAX_ASSET_BYTES + 1)
        if len(raw) > 2 * MAX_ASSET_BYTES or _bytes_hash(raw) != receipt["input_hash"]:
            raise ValueError("operation_input_changed")
        manifest = operation_materialization(json.loads(raw))
        request = manifest["request"]
        if (manifest["operation_id"] != receipt["operation_id"] or _hash(request) != receipt["request_hash"]
                or request["role"] != receipt["role"] or request["purpose"] != receipt["purpose"]):
            raise ValueError("operation_receipt_changed")
        return manifest

    def cleanup_proven(self, identifier, attempt, expected):
        self._paths(identifier, attempt)
        handle = _try_workspace_lifetime_lock(self.root, ".lifetimes", identifier + ":" + str(attempt))
        if handle is None:
            return False
        try:
            return self._cleanup(identifier, attempt, expected)
        finally:
            handle.close()

    def _cleanup(self, identifier, attempt, expected):
        path, journal = self._paths(identifier, attempt)
        with self._lock(identifier, attempt):
            record = self._journal(identifier, attempt, path, journal, expected)
            check_ancestry(path)
            if record is None and (path.exists() or expected is not None):
                raise ValueError("operation_cleanup_unproven")
            if record is not None and expected is None:
                raise ValueError("operation_cleanup_unproven")
            resolved = path.resolve()
            if not resolved.is_relative_to(self.root.resolve()) or resolved == self.root.resolve():
                raise ValueError("invalid_operation_cleanup_target")

            def unlock(function, name, error):
                candidate = Path(name)
                check_ancestry(candidate)
                if not candidate.resolve().is_relative_to(resolved):
                    raise ValueError("invalid_operation_cleanup_child")
                candidate.chmod(stat.S_IREAD | stat.S_IWRITE)
                function(name)

            if path.exists():
                shutil.rmtree(path, onexc=unlock)
            if record is not None:
                record["state"] = "cleaned"
                _atomic(journal, _json(record).encode())
            final = self._journal(identifier, attempt, path, journal, expected)
            if path.exists() or (final is not None and final["state"] != "cleaned"):
                raise ValueError("operation_cleanup_incomplete")
            return True
