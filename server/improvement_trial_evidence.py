"""Immutable encrypted trial packets beside the existing call and trial references."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from contextlib import closing

import improvement_cases as IC
import improvement_store as IM
from improvement_blobs import MAX_ASSET_BYTES, AssetUnavailable
from improvement_observation_history import is_observation2, candidate, reject_v2_history, validate_history

MAX_PACKET_BYTES = 8 * 1024 * 1024


def _packet(value):
    packet = IC._frozen(value)
    kind = packet.get("type") if isinstance(packet, dict) else None
    if kind == "worker_error":
        IC._fields(packet, {"version", "sequence", "type", "reason", "error_type"})
        IC._text(packet["reason"], 1000)
        IC._text(packet["error_type"], 128)
    else:
        extras = {"worker_ready": {"capability_hash"}, "engine_start_requested": set(),
                  "engine_event": {"event"}, "fixture_event": {"event"},
                  "worker_complete": {"fixture_events", "tool_denials"}}
        if not isinstance(kind, str) or kind not in extras:
            raise ValueError("invalid_trial_worker_packet")
        IC._fields(packet, {"version", "sequence", "type", "trial_id", "attempt", "input_hash", *extras[kind]})
        IC._digest(packet["input_hash"])
    if (type(packet["version"]) is not int or packet["version"] != 1
            or type(packet["sequence"]) is not int or not 1 <= packet["sequence"] < 2 ** 63):
        raise ValueError("invalid_trial_worker_packet")
    raw = IM._json(packet).encode("utf-8")
    if len(raw) > MAX_PACKET_BYTES:
        raise ValueError("trial_worker_packet_too_large")
    return packet, raw


def _metadata(row):
    return {"sequence": row["sequence"], "kind": row["kind"], "payload_hash": row["payload_hash"], "late": bool(row["late"])}


def decode_trace(blobs, brain, row):
    try:
        hashes = json.loads(row["blob_hashes_json"])
        if not isinstance(hashes, list) or not 1 <= len(hashes) <= MAX_PACKET_BYTES // MAX_ASSET_BYTES:
            raise AssetUnavailable("invalid_trial_trace_chunks")
        raw = b"".join(blobs.read(brain, digest) for digest in hashes)
        if len(raw) > MAX_PACKET_BYTES or hashlib.sha256(raw).hexdigest() != row["payload_hash"]:
            raise AssetUnavailable("trial_trace_hash_mismatch")
        return json.loads(raw)
    except (ValueError, TypeError, UnicodeError) as error:
        raise AssetUnavailable("trial_trace_unavailable") from error


class TrialEvidence:
    def __init__(self, trials):
        self.trials = trials

    def _decode(self, brain, row):
        return decode_trace(self.trials.blobs, brain, row)

    def read(self, principal, identifier, attempt, sequence):
        brain = IM._brain(principal)
        if any(type(value) is not int or value < 1 for value in (attempt, sequence)):
            raise ValueError("invalid_trial_trace_identity")
        if IM._schema_version(self.trials.store) < 3:
            raise PermissionError("trial_record_unavailable")
        with closing(self.trials.store._conn()) as connection:
            self.trials._row(connection, brain, identifier)
            row = connection.execute("SELECT * FROM improvement_trial_observations WHERE trial_id=? AND brain_id=? "
                                     "AND attempt=? AND sequence=?", (identifier, brain, attempt, sequence)).fetchone()
            if not row:
                raise PermissionError("trial_record_unavailable")
            packet = self._decode(brain, row)
            if is_observation2(packet):
                attempt_row = connection.execute("SELECT workspace_json FROM improvement_trial_attempts WHERE trial_id=? AND attempt=?",
                    (identifier, attempt)).fetchone()
                receipt = json.loads(attempt_row['workspace_json']) if attempt_row and attempt_row['workspace_json'] else None
                if (type(receipt) is not dict or receipt.get('trial_id') != identifier
                        or type(receipt.get('attempt')) is not int or receipt['attempt'] != attempt):
                    raise AssetUnavailable('trial_trace_identity_drift')
                history = connection.execute("SELECT * FROM improvement_trial_observations WHERE trial_id=? AND brain_id=? AND attempt=? ORDER BY sequence",
                    (identifier, brain, attempt)).fetchall()
                return validate_history(history, lambda item: self._decode(brain, item), kind='trial', receipt=receipt, selected=sequence)
            return packet

    def append(self, principal, identifier, value, *, lease_token, expected_generation=None, attempt=None, late=False):
        brain = IM._brain(principal)
        native = is_observation2(value)
        packet, raw = candidate(value) if native else _packet(value)
        packet_kind = packet['body']['type'] if native else packet['type']
        if not isinstance(lease_token, str) or not 1 <= len(lease_token) <= 256 or type(late) is not bool:
            raise IM.ConflictError("trial_trace_writer_unbound")
        with self.trials.store._Tx(self.trials.store) as connection:
            trial = self.trials._row(connection, brain, identifier)
            number = trial["attempt"] if attempt is None else attempt
            if type(number) is not int or not 1 <= number <= trial["attempt"]:
                raise IM.ConflictError("trial_trace_attempt_stale")
            row = connection.execute("SELECT * FROM improvement_trial_attempts WHERE trial_id=? AND attempt=?",
                                     (identifier, number)).fetchone()
            writer = hashlib.sha256(lease_token.encode()).hexdigest()
            if not row["writer_hash"] or not secrets.compare_digest(writer, row["writer_hash"]):
                raise IM.ConflictError("trial_trace_writer_unbound")
            receipt = json.loads(row["workspace_json"]) if row["workspace_json"] else None
            history = connection.execute("SELECT * FROM improvement_trial_observations WHERE trial_id=? AND brain_id=? AND attempt=? ORDER BY sequence",
                (identifier, brain, number)).fetchall()
            if native:
                if type(receipt) is not dict or receipt.get('trial_id') != identifier or type(receipt.get('attempt')) is not int or receipt['attempt'] != number:
                    raise IM.ConflictError('trial_trace_identity_drift')
                validate_history(history, lambda item: self._decode(brain, item), kind='trial', receipt=receipt,
                    incoming=packet, raw=raw, late=late)
            else:
                reject_v2_history(history, lambda item: self._decode(brain, item))
            if not native and packet["type"] != "worker_error" and (
                    not receipt or packet["trial_id"] != identifier or type(packet["attempt"]) is not int
                    or packet["attempt"] != number or packet["input_hash"] != receipt["input_hash"]):
                raise IM.ConflictError("trial_trace_identity_drift")
            previous = connection.execute("SELECT * FROM improvement_trial_observations WHERE trial_id=? AND attempt=? AND sequence=?",
                                          (identifier, number, packet["sequence"])).fetchone()
            digest = hashlib.sha256(raw).hexdigest()
            if previous:
                if previous["payload_hash"] != digest:
                    raise IM.ConflictError("trial_trace_payload_conflict")
                self._decode(brain, previous)
                return _metadata(previous)
            if late:
                if number == trial["attempt"] and trial["status"] not in {"completed", "failed", "unknown", "interrupted", "cancelled", "not_run"}:
                    raise IM.ConflictError("trial_trace_not_late")
            else:
                if number != trial["attempt"]:
                    raise IM.ConflictError("trial_trace_attempt_stale")
                if trial["status"] not in {"prepared", "running"}:
                    raise IM.ConflictError("trial_trace_frozen")
                self.trials._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
                if not native and connection.execute("SELECT 1 FROM improvement_trial_observations WHERE trial_id=? AND attempt=? "
                                      "AND kind='worker_complete' LIMIT 1", (identifier, number)).fetchone():
                    raise IM.ConflictError("trial_trace_frozen")
                last = connection.execute("SELECT COALESCE(MAX(sequence),0) FROM improvement_trial_observations "
                                          "WHERE trial_id=? AND attempt=?", (identifier, number)).fetchone()[0]
                if not native and packet["sequence"] != last + 1:
                    raise IM.ConflictError("trial_trace_sequence_gap")
            hashes = [self.trials.blobs.write(brain, raw[offset:offset + MAX_ASSET_BYTES])
                      for offset in range(0, len(raw), MAX_ASSET_BYTES)]
            if not late:
                self.trials._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            connection.execute("INSERT INTO improvement_trial_observations VALUES(?,?,?,?,?,?,?,?,?)",
                (identifier, brain, number, packet["sequence"], packet_kind, digest, IM._json(hashes), int(late), time.time()))
            return {"sequence": packet["sequence"], "kind": packet_kind, "payload_hash": digest, "late": late}
