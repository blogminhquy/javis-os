"""Immutable encrypted role packets; actual late evidence never renews authority."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from contextlib import closing

import improvement_store as IM
from improvement_blobs import MAX_ASSET_BYTES, AssetUnavailable
from improvement_operation_execution import OperationExecution
from improvement_operation_protocol import operation_packet
from improvement_operation_schema import TERMINAL
from improvement_trial_evidence import decode_trace, _metadata
from improvement_trial_records import _brain
from improvement_observation_history import is_observation2, candidate, reject_v2_history, validate_history


class OperationEvidence:
    def __init__(self, execution):
        if type(execution) is not OperationExecution:
            raise TypeError("concrete_operation_evidence_required")
        self.execution = execution

    def read(self, principal, identifier, attempt, sequence):
        if type(attempt) is not int or attempt not in (1, 2) or type(sequence) is not int or not 1 <= sequence < 2 ** 63:
            raise ValueError("invalid_operation_trace_identity")
        self.execution.records.get(principal, identifier)
        with closing(self.execution.store._conn()) as connection:
            record = connection.execute("SELECT * FROM improvement_operation_observations WHERE operation_id=? AND brain_id=? "
                "AND attempt=? AND sequence=?", (identifier, _brain(principal), attempt, sequence)).fetchone()
            if record is None:
                raise PermissionError("operation_trace_unavailable")
            decoded = decode_trace(self.execution.blobs, _brain(principal), record)
            if is_observation2(decoded):
                attempt_row = connection.execute("SELECT workspace_json FROM improvement_operation_attempts WHERE operation_id=? AND brain_id=? AND attempt=?",
                    (identifier, _brain(principal), attempt)).fetchone()
                receipt = json.loads(attempt_row['workspace_json']) if attempt_row and attempt_row['workspace_json'] else None
                if (type(receipt) is not dict or receipt.get('operation_id') != identifier
                        or type(receipt.get('attempt')) is not int or receipt['attempt'] != attempt):
                    raise AssetUnavailable('operation_trace_identity_drift')
                history = connection.execute("SELECT * FROM improvement_operation_observations WHERE operation_id=? AND brain_id=? AND attempt=? ORDER BY sequence",
                    (identifier, _brain(principal), attempt)).fetchall()
                return validate_history(history, lambda item: decode_trace(self.execution.blobs, _brain(principal), item),
                    kind='operation', receipt=receipt, selected=sequence)
        packet, _ = operation_packet(decoded)
        return packet

    def _proof(self, connection, principal, identifier, packet, digest, token, generation, number, late):
        row = self.execution._row(connection, principal, identifier)
        number = row["attempt"] if number is None else number
        if type(number) is not int or not 1 <= number <= row["attempt"]:
            raise IM.ConflictError("operation_trace_attempt_stale")
        attempt = connection.execute("SELECT * FROM improvement_operation_attempts WHERE operation_id=? AND brain_id=? AND attempt=?",
                                     (identifier, row["brain_id"], number)).fetchone()
        writer = hashlib.sha256(token.encode()).hexdigest()
        if attempt is None or not attempt["writer_hash"] or not secrets.compare_digest(writer, attempt["writer_hash"]):
            raise IM.ConflictError("operation_trace_writer_unbound")
        receipt = json.loads(attempt["workspace_json"]) if attempt["workspace_json"] else None
        native = is_observation2(packet)
        history = connection.execute("SELECT * FROM improvement_operation_observations WHERE operation_id=? AND brain_id=? AND attempt=? ORDER BY sequence",
            (identifier, row['brain_id'], number)).fetchall()
        decode = lambda item: decode_trace(self.execution.blobs, row['brain_id'], item)
        if native:
            if type(receipt) is not dict or receipt.get('operation_id') != identifier or type(receipt.get('attempt')) is not int or receipt['attempt'] != number:
                raise IM.ConflictError('operation_trace_identity_drift')
            from improvement_native_protocol import _canonical
            validate_history(history, decode, kind='operation', receipt=receipt,
                incoming=packet, raw=_canonical(packet), late=late)
        else:
            reject_v2_history(history, decode)
        if not native and packet["type"] != "worker_error" and (receipt is None or any(packet[key] != receipt[key] for key in
                ("operation_id", "attempt", "role", "purpose", "input_hash")) or packet["operation_id"] != identifier):
            raise IM.ConflictError("operation_trace_identity_drift")
        previous = connection.execute("SELECT * FROM improvement_operation_observations WHERE operation_id=? AND brain_id=? "
            "AND attempt=? AND sequence=?", (identifier, row["brain_id"], number, packet["sequence"])).fetchone()
        if previous is not None:
            if previous["payload_hash"] != digest:
                raise IM.ConflictError("operation_trace_payload_conflict")
            decode_trace(self.execution.blobs, row["brain_id"], previous)
            return row, number, previous
        if late:
            if number == row["attempt"] and row["status"] not in TERMINAL:
                raise IM.ConflictError("operation_trace_not_late")
        else:
            self.execution._leased(connection, principal, identifier, generation, token, time.time())
            if number != row["attempt"] or row["status"] not in ("prepared", "running"):
                raise IM.ConflictError("operation_trace_frozen")
            if not native and connection.execute("SELECT 1 FROM improvement_operation_observations WHERE operation_id=? AND brain_id=? "
                    "AND attempt=? AND kind='worker_complete'", (identifier, row["brain_id"], number)).fetchone():
                raise IM.ConflictError("operation_trace_frozen")
            last = connection.execute("SELECT COALESCE(MAX(sequence),0) FROM improvement_operation_observations WHERE "
                "operation_id=? AND brain_id=? AND attempt=?", (identifier, row["brain_id"], number)).fetchone()[0]
            if not native and packet["sequence"] != last + 1:
                raise IM.ConflictError("operation_trace_sequence_gap")
        return row, number, None

    def append(self, principal, identifier, value, *, lease_token, expected_generation=None, attempt=None, late=False):
        brain = _brain(principal)
        native = is_observation2(value)
        packet, raw = candidate(value) if native else operation_packet(value)
        packet_kind = packet['body']['type'] if native else packet['type']
        if type(lease_token) is not str or not 1 <= len(lease_token) <= 256 or type(late) is not bool:
            raise IM.ConflictError("operation_trace_writer_unbound")
        digest = hashlib.sha256(raw).hexdigest()
        with closing(self.execution.store._conn()) as connection:
            _, number, prior = self._proof(connection, principal, identifier, packet, digest, lease_token, expected_generation, attempt, late)
            if prior is not None:
                return _metadata(prior)
        hashes = [self.execution.blobs.write(brain, raw[offset:offset + MAX_ASSET_BYTES])
                  for offset in range(0, len(raw), MAX_ASSET_BYTES)]
        with self.execution.store._Tx(self.execution.store) as connection:
            _, current, prior = self._proof(connection, principal, identifier, packet, digest, lease_token, expected_generation, number, late)
            if prior is not None:
                return _metadata(prior)
            connection.execute("INSERT INTO improvement_operation_observations VALUES(?,?,?,?,?,?,?,?,?)", (
                identifier, brain, current, packet["sequence"], packet_kind, digest, IM._json(hashes), int(late), time.time()))
            return {"sequence": packet["sequence"], "kind": packet_kind, "payload_hash": digest, "late": late}
