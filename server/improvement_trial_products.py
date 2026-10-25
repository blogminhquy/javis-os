"""Persist exact native products independently of their host acceptance verdicts."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from contextlib import closing
from pathlib import Path

import improvement_cases as IC
import improvement_store as IM
from improvement_blobs import MAX_ASSET_BYTES, AssetUnavailable, check_ancestry
from improvement_trial_evidence import TrialEvidence


def _publish(path, content):
    """Publish a complete host copy without replacing any concurrent owner edit."""
    from improvement_evaluation import _artifact
    check_ancestry(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    check_ancestry(path)
    if path.exists():
        if _artifact(path.parent, path.name).content != content:
            raise IM.ConflictError("trial_output_changed")
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".trial-output-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # Hard-link creation is atomic and fails if another writer won the name.
            os.link(temporary, path)
        except FileExistsError:
            if _artifact(path.parent, path.name).content != content:
                raise IM.ConflictError("trial_output_changed")
    finally:
        os.unlink(temporary)


class TrialProducts:
    def __init__(self, trials):
        self.trials = trials

    def _row(self, connection, table, brain, identifier, attempt):
        if type(attempt) is not int or not 1 <= attempt < 2 ** 63:
            raise ValueError("invalid_trial_attempt")
        self.trials._row(connection, brain, identifier)
        row = connection.execute(f"SELECT * FROM {table} WHERE trial_id=? AND brain_id=? AND attempt=?",
                                 (identifier, brain, attempt)).fetchone()
        if not row:
            raise PermissionError("trial_product_unavailable")
        return row

    def artifact(self, principal, identifier, attempt):
        brain = IM._brain(principal)
        if IM._schema_version(self.trials.store) < 3:
            raise PermissionError("trial_product_unavailable")
        with closing(self.trials.store._conn()) as connection:
            row = self._row(connection, "improvement_trial_artifacts", brain, identifier, attempt)
            raw = self.trials.blobs.read(brain, row["content_hash"])
            if len(raw) != row["byte_size"]:
                raise AssetUnavailable("trial_artifact_size_mismatch")
            return raw

    def receipt(self, principal, identifier, attempt):
        brain = IM._brain(principal)
        if IM._schema_version(self.trials.store) < 3:
            raise PermissionError("trial_product_unavailable")
        with closing(self.trials.store._conn()) as connection:
            row = self._row(connection, "improvement_trial_receipts", brain, identifier, attempt)
            return json.loads(self.trials.blobs.read(brain, row["content_hash"]))

    def _products(self, connection, row, *, principal=None, capability_hash=None):
        from improvement_qualification_records import require_product_store
        from resonance_store import Principal
        # Historical internal callers omitted principal; this only determines
        # the durable domain and confers no execution/product authority.
        require_product_store(self.trials.assets, principal if principal is not None else
            Principal('owner', 'owner', row['brain_id']), connection=connection)
        records = list(connection.execute("SELECT * FROM improvement_trial_observations WHERE trial_id=? AND attempt=? ORDER BY sequence",
                                          (row["id"], row["attempt"])))
        if (not records or records[-1]["kind"] not in ("worker_complete", "drained")
                or any(record["late"] or record["sequence"] != index for index, record in enumerate(records, 1))):
            raise IM.ConflictError("trial_trace_incomplete")
        artifacts, receipts, terminals = {}, {}, []
        reader = TrialEvidence(self.trials)
        first = reader._decode(row['brain_id'], records[0])
        native_history = first.get('version') == 2
        if native_history:
            packets = [first, *(reader._decode(row['brain_id'], record) for record in records[1:])]
            from improvement_native_trace_checks import validated_history, validate_native_trace, require_durable_allow
            from improvement_native_decisions import NativeImageDecisionStore, attempt_scope
            from improvement_sandbox import trial_system_prompt
            attempt = connection.execute('SELECT workspace_json,materialization_hash FROM improvement_trial_attempts WHERE trial_id=? AND attempt=?',
                (row['id'], row['attempt'])).fetchone()
            workspace = json.loads(attempt['workspace_json'])
            manifest = self.trials.workspace.validate(workspace)
            if manifest['version'] not in (4, 5) or IM._hash(manifest) != attempt['materialization_hash']:
                raise IM.ConflictError('trial_native_materialization_mismatch')
            decoded = {item['sequence']: packet for item, packet in zip(records, packets)}
            validated_history(records, lambda item: decoded[item['sequence']], kind='trial', receipt=workspace)
            request = json.loads(row['request_json']); pin = request['engine_config']
            if manifest['version'] == 5 and (request['version'] == 4 or request['variant'] != 'baseline'):
                raise IM.ConflictError('trial_native_baseline_request_mismatch')
            ready = [packet['body'] for packet in packets if packet['body']['type'] == 'worker_ready']
            if len(ready) != 1 or principal is None: raise IM.ConflictError('trial_native_product_boundary_missing')
            capability = ready[0]['capability_hash'] if capability_hash is None else capability_hash
            scope = attempt_scope(kind='trial', brain_id=row['brain_id'], receipt=workspace, config_pin=pin, capability_hash=capability)
            decisions = NativeImageDecisionStore(self.trials.assets)
            prompt = IM._json({'task': manifest['case']['task'], 'fixtures': [
                {key: item[key] for key in ('snapshot_id', 'source')} for item in manifest['case']['fixtures']]})
            native = validate_native_trace(packets, kind='trial', receipt=workspace, pin=pin, capability_hash=capability,
                system_prompt=trial_system_prompt(manifest), user_prompt=prompt, data_hash=workspace['input_hash'],
                read_decision=lambda joined: decisions.read(principal, joined, scope_hash=scope, connection=connection),
                tool_policy='baseline_inline' if manifest['version'] == 5 else 'pinned_skill')
            require_durable_allow(native)
            packets = native['worker_bodies']
        elif records[-1]['kind'] != 'worker_complete':
            raise IM.ConflictError('trial_trace_incomplete')
        else:
            # Preserve the legacy owner's bounded one-packet validation/read
            # order rather than retaining future decrypted engine events.
            packets = (first if number == 0 else reader._decode(row['brain_id'], record)
                for number, record in enumerate(records))
        for packet in packets:
            if not native_history and packet.get('version') == 2:
                raise IM.ConflictError('native_trace_version_mixed')
            if packet["type"] == "worker_error":
                raise IM.ConflictError("trial_worker_failed")
            if packet["type"] != "engine_event":
                continue
            event = packet["event"]
            if not isinstance(event, dict):
                raise IM.ConflictError("invalid_trial_engine_event")
            if event.get("type") == "artifact":
                content = event.get("content")
                if not isinstance(content, str):
                    raise IM.ConflictError("invalid_trial_artifact")
                raw = content.encode("utf-8")
                if len(raw) > MAX_ASSET_BYTES or hashlib.sha256(raw).hexdigest() != event.get("hash"):
                    raise IM.ConflictError("trial_artifact_hash_mismatch")
                artifacts[event["hash"]] = raw
            elif event.get("type") == "installation_receipt":
                receipt = event.get("receipt")
                if not isinstance(receipt, dict) or IM._hash(receipt) != event.get("hash"):
                    raise IM.ConflictError("trial_receipt_hash_mismatch")
                receipts[event["hash"]] = receipt
            elif event.get("type") == "terminal":
                terminals.append(event)
        if len(artifacts) > 1 or len(receipts) > 1 or len(terminals) != 1 or type(terminals[0].get("is_error")) is not bool:
            raise IM.ConflictError("trial_product_ambiguous")
        return artifacts, receipts

    def stage(self, principal, identifier, *, expected_generation, lease_token):
        with self.trials.store._Tx(self.trials.store) as connection:
            row, attempt = self.trials._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            if row["status"] not in {"running", "evaluating"} or attempt["engine_at"] is None:
                raise IM.ConflictError("trial_evaluation_stale")
            request = json.loads(row["request_json"])
            self.trials._current(connection, row["brain_id"], request, trial_id=row["id"], principal=principal)
            workspace = json.loads(attempt["workspace_json"])
            manifest = self.trials.workspace.validate(workspace)
            if IM._hash(manifest) != attempt["materialization_hash"]:
                raise IM.ConflictError("trial_materialization_drift")
            artifacts, receipts = self._products(connection, row, principal=principal)
            contract = json.loads(connection.execute("SELECT contract_json FROM improvement_contracts WHERE brain_id=? AND manifest_hash=?",
                                                     (row["brain_id"], request["pins"]["contract_hash"])).fetchone()[0])
            path = IC.output_path(contract["output"]["path"])
            now = time.time()
            for digest, raw in artifacts.items():
                self.trials.blobs.write(row["brain_id"], raw)
                _publish(Path(workspace["output_root"]) / path, raw)
                old = connection.execute("SELECT content_hash FROM improvement_trial_artifacts WHERE trial_id=? AND attempt=?",
                                         (identifier, row["attempt"])).fetchone()
                if old and old[0] != digest:
                    raise IM.ConflictError("trial_product_changed")
                if not old:
                    connection.execute("INSERT INTO improvement_trial_artifacts VALUES(?,?,?,?,?,?,?)",
                                       (identifier, row["brain_id"], row["attempt"], path, digest, len(raw), now))
            for digest, receipt in receipts.items():
                self.trials.blobs.write(row["brain_id"], IM._json(receipt).encode())
                old = connection.execute("SELECT content_hash FROM improvement_trial_receipts WHERE trial_id=? AND attempt=?",
                                         (identifier, row["attempt"])).fetchone()
                if old and old[0] != digest:
                    raise IM.ConflictError("trial_product_changed")
                if not old:
                    connection.execute("INSERT INTO improvement_trial_receipts VALUES(?,?,?,?,?)",
                                       (identifier, row["brain_id"], row["attempt"], digest, now))
            self.trials._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            if row["status"] == "running":
                connection.execute("UPDATE improvement_trial_attempts SET status='evaluating',updated_at=? WHERE trial_id=? AND attempt=?",
                                   (now, identifier, row["attempt"]))
                connection.execute("UPDATE improvement_trials SET status='evaluating',generation=generation+1,updated_at=? WHERE id=?", (now, identifier))
            return self.trials._public(connection, self.trials._row(connection, row["brain_id"], identifier))
