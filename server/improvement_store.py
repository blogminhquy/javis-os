"""M0 owner-only immutable asset history in the existing resonance database.

This module never runs an engine, changes canonical files or activates a revision.
Read paths do not initialize the improvement schema or write policy defaults.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path

from improvement_blobs import AssetUnavailable, MAX_ASSET_BYTES, RevisionBlobs  # noqa: F401

SCHEMA_VERSION = 17
_SOURCE = re.compile(r"(?:skills/[a-z0-9][a-z0-9_-]*/SKILL\.md|agents/[a-z0-9][a-z0-9_-]*\.md)")
_SCHEMA = (
    "CREATE TABLE improvement_schema(id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL)",
    "CREATE TABLE improvement_policies(brain_id TEXT PRIMARY KEY, mode TEXT NOT NULL "
    "CHECK(mode IN ('off','suggest')), version INTEGER NOT NULL)",
    "CREATE TABLE improvement_targets(id TEXT PRIMARY KEY, brain_id TEXT NOT NULL, kind TEXT NOT NULL, "
    "canonical_ref TEXT NOT NULL, identity TEXT NOT NULL, source_hash TEXT NOT NULL, "
    "protected_hash TEXT NOT NULL, ownership TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('live','retired')), "
    "generation INTEGER NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL, "
    "current_revision_id TEXT, UNIQUE(id,brain_id), "
    "FOREIGN KEY(current_revision_id,brain_id) REFERENCES improvement_revisions(id,brain_id))",
    "CREATE UNIQUE INDEX improvement_target_live ON improvement_targets(brain_id,kind,canonical_ref) "
    "WHERE status='live'",
    "CREATE TABLE improvement_revisions(id TEXT PRIMARY KEY, target_id TEXT NOT NULL, brain_id TEXT NOT NULL, "
    "parent_id TEXT, manifest_hash TEXT NOT NULL, manifest_json TEXT NOT NULL, content_hash TEXT NOT NULL, "
    "created_at REAL NOT NULL, UNIQUE(target_id,manifest_hash), UNIQUE(id,brain_id), "
    "FOREIGN KEY(target_id,brain_id) REFERENCES improvement_targets(id,brain_id), "
    "FOREIGN KEY(parent_id) REFERENCES improvement_revisions(id))",
    "CREATE TABLE improvement_bundles(id TEXT PRIMARY KEY, brain_id TEXT NOT NULL, manifest_hash TEXT NOT NULL, "
    "manifest_json TEXT NOT NULL, created_at REAL NOT NULL, UNIQUE(brain_id,manifest_hash), UNIQUE(id,brain_id))",
    "CREATE TABLE improvement_bundle_assets(bundle_id TEXT NOT NULL, revision_id TEXT NOT NULL, brain_id TEXT NOT NULL, "
    "PRIMARY KEY(bundle_id,revision_id), FOREIGN KEY(bundle_id,brain_id) REFERENCES improvement_bundles(id,brain_id), "
    "FOREIGN KEY(revision_id,brain_id) REFERENCES improvement_revisions(id,brain_id))",
    "CREATE TABLE improvement_events(id INTEGER PRIMARY KEY AUTOINCREMENT, brain_id TEXT NOT NULL, "
    "event_key TEXT NOT NULL, operation TEXT NOT NULL, request_hash TEXT NOT NULL, result_json TEXT NOT NULL, "
    "actor TEXT NOT NULL, created_at REAL NOT NULL, UNIQUE(brain_id,event_key))",
    "CREATE TRIGGER improvement_revision_parent BEFORE INSERT ON improvement_revisions "
    "WHEN NEW.parent_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM improvement_revisions "
    "WHERE id=NEW.parent_id AND target_id=NEW.target_id AND brain_id=NEW.brain_id) "
    "BEGIN SELECT RAISE(ABORT,'revision_parent_mismatch'); END",
)


class ConflictError(ValueError):
    """Expected generation/version or an idempotency payload no longer matches."""


class SchemaError(RuntimeError):
    """This build cannot safely interpret the installed improvement schema."""


@dataclass(frozen=True)
class SourceSnapshot:
    kind: str
    canonical_ref: str
    source_hash: str
    protected_hash: str
    enabled: bool
    ownership: str
    identity: str
    agent_key: str = ""


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _brain(principal) -> str:
    if principal.kind != "owner" or not principal.brain_id or not principal.id:
        raise PermissionError("owner_required")
    return str(principal.brain_id)


def _schema_version(store) -> int:
    with closing(store._conn()) as connection:
        row = connection.execute("SELECT name FROM sqlite_master WHERE name='improvement_schema'").fetchone()
        if not row:
            return 0
        version = connection.execute("SELECT version FROM improvement_schema WHERE id=1").fetchone()
        if not version or version["version"] not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, SCHEMA_VERSION):
            raise SchemaError("unsupported_improvement_schema")
        return version["version"]


def has_schema(store) -> bool:
    return bool(_schema_version(store))


class _ReadDatabase:
    """Read the existing shared file without running GoalStore initialization."""

    def __init__(self, path: Path):
        self.path = path.absolute()
        self.uri = path.resolve().as_uri() + "?mode=ro"

    def _conn(self):
        connection = sqlite3.connect(self.uri, uri=True, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection


def read_existing(path: Path, blobs: RevisionBlobs, *, qualification_anchor=None):
    """Return metadata access only when an installed compatible schema exists."""
    if not path.is_file():
        return None
    database = _ReadDatabase(path)
    return ImprovementStore(database, blobs, qualification_anchor=qualification_anchor) if has_schema(database) else None


def ensure(store) -> None:
    installed = _schema_version(store)
    from improvement_compose_schema import assert_historical, assert_installed as assert_compose, migrate, migration_transaction
    from improvement_recipe_schema import _assert_absent, assert_installed as assert_recipes, migrate as migrate_recipes
    from improvement_recipe_view_schema import assert_installed as assert_recipe_views, migrate as migrate_recipe_views
    from improvement_activation_schema import assert_installed as assert_activations, migrate as migrate_activations
    from improvement_canary_schema import assert_installed as assert_canaries, migrate as migrate_canaries
    from improvement_routing_schema import assert_installed as assert_routing, migrate as migrate_routing
    from improvement_agent_schema import assert_installed as assert_agents, migrate as migrate_agents
    from improvement_bundle_schema import assert_installed as assert_bundles, migrate as migrate_bundles
    from improvement_team_schema import assert_installed as assert_team, migrate as migrate_team
    from improvement_library_schema import assert_installed as assert_library, migrate as migrate_library
    if installed == SCHEMA_VERSION:
        with closing(store._conn()) as connection:
            assert_compose(connection)
            assert_recipe_views(connection)
            assert_activations(connection)
            assert_canaries(connection)
            assert_routing(connection)
            assert_agents(connection)
            assert_bundles(connection)
            assert_team(connection)
            assert_library(connection)
        return
    with migration_transaction(store) as connection:
        exists = connection.execute("SELECT name FROM sqlite_master WHERE name='improvement_schema'").fetchone()
        installed = connection.execute("SELECT version FROM improvement_schema WHERE id=1").fetchone() if exists else None
        if exists and (not installed or installed["version"] not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, SCHEMA_VERSION)):
            raise SchemaError("unsupported_improvement_schema")
        if installed and installed["version"] == SCHEMA_VERSION:
            assert_compose(connection)
            assert_recipe_views(connection)
            assert_activations(connection)
            assert_canaries(connection)
            assert_routing(connection)
            assert_agents(connection)
            assert_bundles(connection)
            assert_team(connection)
            assert_library(connection)
            return
        if installed and installed["version"] == 16:
            assert_compose(connection)
            assert_recipe_views(connection)
            assert_activations(connection)
            assert_canaries(connection)
            assert_routing(connection)
            assert_agents(connection)
            assert_bundles(connection)
            assert_team(connection)
            store._backup_before("improvement_refinements", ".pre-improvement-m8-library.bak")
            migrate_library(connection)
            connection.execute("UPDATE improvement_schema SET version=? WHERE id=1", (SCHEMA_VERSION,))
            return
        if installed and installed["version"] == 15:
            assert_compose(connection)
            assert_recipe_views(connection)
            assert_activations(connection)
            assert_canaries(connection)
            assert_routing(connection)
            assert_agents(connection)
            assert_bundles(connection)
            store._backup_before("improvement_team_pins", ".pre-improvement-m7-team.bak")
            migrate_team(connection)
            connection.execute("UPDATE improvement_schema SET version=16 WHERE id=1")
            migrate_library(connection)
            connection.execute("UPDATE improvement_schema SET version=? WHERE id=1", (SCHEMA_VERSION,))
            return
        if installed and installed["version"] == 14:
            assert_compose(connection)
            assert_recipe_views(connection)
            assert_activations(connection)
            assert_canaries(connection)
            assert_routing(connection)
            assert_agents(connection)
            store._backup_before("improvement_bundle_activations", ".pre-improvement-m6-bundles.bak")
            migrate_bundles(connection)
            connection.execute("UPDATE improvement_schema SET version=15 WHERE id=1")
            migrate_team(connection)
            connection.execute("UPDATE improvement_schema SET version=16 WHERE id=1")
            migrate_library(connection)
            connection.execute("UPDATE improvement_schema SET version=? WHERE id=1", (SCHEMA_VERSION,))
            return
        if installed and installed["version"] == 13:
            assert_compose(connection)
            assert_recipe_views(connection)
            assert_activations(connection)
            assert_canaries(connection)
            assert_routing(connection)
            store._backup_before("improvement_agent_procedures", ".pre-improvement-m5-agents.bak")
            migrate_agents(connection)
            connection.execute("UPDATE improvement_schema SET version=14 WHERE id=1")
            migrate_bundles(connection)
            connection.execute("UPDATE improvement_schema SET version=15 WHERE id=1")
            migrate_team(connection)
            connection.execute("UPDATE improvement_schema SET version=16 WHERE id=1")
            migrate_library(connection)
            connection.execute("UPDATE improvement_schema SET version=? WHERE id=1", (SCHEMA_VERSION,))
            return
        if installed and installed["version"] == 12:
            assert_compose(connection)
            assert_recipe_views(connection)
            assert_activations(connection)
            assert_canaries(connection)
            store._backup_before("improvement_routing_candidates", ".pre-improvement-m4-routing.bak")
            migrate_routing(connection)
            connection.execute("UPDATE improvement_schema SET version=13 WHERE id=1")
            migrate_agents(connection)
            connection.execute("UPDATE improvement_schema SET version=14 WHERE id=1")
            migrate_bundles(connection)
            connection.execute("UPDATE improvement_schema SET version=15 WHERE id=1")
            migrate_team(connection)
            connection.execute("UPDATE improvement_schema SET version=16 WHERE id=1")
            migrate_library(connection)
            connection.execute("UPDATE improvement_schema SET version=? WHERE id=1", (SCHEMA_VERSION,))
            return
        if installed and installed["version"] == 11:
            assert_compose(connection)
            assert_recipe_views(connection)
            assert_activations(connection)
            store._backup_before("improvement_canaries", ".pre-improvement-m3-canaries.bak")
            migrate_canaries(connection)
            connection.execute("UPDATE improvement_schema SET version=12 WHERE id=1")
            migrate_routing(connection)
            connection.execute("UPDATE improvement_schema SET version=13 WHERE id=1")
            migrate_agents(connection)
            connection.execute("UPDATE improvement_schema SET version=14 WHERE id=1")
            migrate_bundles(connection)
            connection.execute("UPDATE improvement_schema SET version=15 WHERE id=1")
            migrate_team(connection)
            connection.execute("UPDATE improvement_schema SET version=16 WHERE id=1")
            migrate_library(connection)
            connection.execute("UPDATE improvement_schema SET version=? WHERE id=1", (SCHEMA_VERSION,))
            return
        if installed and installed["version"] == 10:
            assert_compose(connection)
            assert_recipe_views(connection)
            store._backup_before("improvement_activations", ".pre-improvement-m2-activations.bak")
            migrate_activations(connection)
            connection.execute("UPDATE improvement_schema SET version=11 WHERE id=1")
            migrate_canaries(connection)
            connection.execute("UPDATE improvement_schema SET version=12 WHERE id=1")
            migrate_routing(connection)
            connection.execute("UPDATE improvement_schema SET version=13 WHERE id=1")
            migrate_agents(connection)
            connection.execute("UPDATE improvement_schema SET version=14 WHERE id=1")
            migrate_bundles(connection)
            connection.execute("UPDATE improvement_schema SET version=15 WHERE id=1")
            migrate_team(connection)
            connection.execute("UPDATE improvement_schema SET version=16 WHERE id=1")
            migrate_library(connection)
            connection.execute("UPDATE improvement_schema SET version=? WHERE id=1", (SCHEMA_VERSION,))
            return
        if installed and installed["version"] == 9:
            assert_compose(connection)
            assert_recipes(connection)
            # The exact authenticated namespace reserves this absent marker;
            # no authority table is created for a trigger-only backup.
            store._backup_before("improvement_recipe_view_scope", ".pre-improvement-m2-recipe-views.bak")
            migrate_recipe_views(connection)
            connection.execute("UPDATE improvement_schema SET version=10 WHERE id=1")
            migrate_activations(connection)
            connection.execute("UPDATE improvement_schema SET version=11 WHERE id=1")
            migrate_canaries(connection)
            connection.execute("UPDATE improvement_schema SET version=12 WHERE id=1")
            migrate_routing(connection)
            connection.execute("UPDATE improvement_schema SET version=13 WHERE id=1")
            migrate_agents(connection)
            connection.execute("UPDATE improvement_schema SET version=14 WHERE id=1")
            migrate_bundles(connection)
            connection.execute("UPDATE improvement_schema SET version=15 WHERE id=1")
            migrate_team(connection)
            connection.execute("UPDATE improvement_schema SET version=16 WHERE id=1")
            migrate_library(connection)
            connection.execute("UPDATE improvement_schema SET version=? WHERE id=1", (SCHEMA_VERSION,))
            return
        _assert_absent(connection)
        if installed and installed["version"] == 8:
            assert_compose(connection)
        if installed and installed["version"] == 7:
            # Unknown same-number drafts must refuse before even the backup.
            assert_historical(connection)
        # Serialize the backup with the migration; two first writers otherwise race on its .tmp file.
        if installed and installed["version"] == 8:
            store._backup_before("improvement_recipes", ".pre-improvement-m2-recipes.bak")
        elif exists:
            store._backup_before("improvement_compositions", ".pre-improvement-m2-compose.bak")
            if installed["version"] < 5:
                store._backup_before("improvement_experiments", ".pre-improvement-m2-experiments.bak")
            if installed["version"] < 6:
                store._backup_before("improvement_preparations", ".pre-improvement-m2-generated.bak")
            store._backup_before("improvement_effective_views", ".pre-improvement-m2-views.bak")
        else:
            store._backup_before("improvement_schema", ".pre-improvement-m0.bak")
        if not exists:
            for statement in _SCHEMA:
                connection.execute(statement)
            _immutable_triggers(connection, ("improvement_revisions", "improvement_bundles",
                                              "improvement_bundle_assets", "improvement_events"))
        if not installed or installed["version"] < 2:
            from improvement_case_schema import SCHEMA, IMMUTABLE
            for statement in SCHEMA:
                connection.execute(statement)
            _immutable_triggers(connection, IMMUTABLE)
        if not installed or installed["version"] < 3:
            from improvement_trial_schema import SCHEMA, IMMUTABLE
            for statement in SCHEMA:
                connection.execute(statement)
            _immutable_triggers(connection, IMMUTABLE)
        if not installed or installed["version"] < 4:
            from improvement_candidate_schema import SCHEMA, IMMUTABLE
            for statement in SCHEMA:
                connection.execute(statement)
            _immutable_triggers(connection, IMMUTABLE)
        if not installed or installed["version"] < 5:
            from improvement_experiment_schema import SCHEMA, IMMUTABLE
            for statement in SCHEMA:
                connection.execute(statement)
            _immutable_triggers(connection, IMMUTABLE)
        if not installed or installed["version"] < 6:
            from improvement_operation_schema import SCHEMA, IMMUTABLE
            for statement in SCHEMA:
                connection.execute(statement)
            _immutable_triggers(connection, IMMUTABLE)
        if not installed or installed["version"] < 7:
            from improvement_view_schema import SCHEMA, IMMUTABLE
            for statement in SCHEMA:
                connection.execute(statement)
            _immutable_triggers(connection, IMMUTABLE)
        if not installed or installed["version"] < 8:
            migrate(connection)
        migrate_recipes(connection)
        if exists:
            connection.execute("UPDATE improvement_schema SET version=9 WHERE id=1")
        else:
            connection.execute("INSERT INTO improvement_schema(id,version) VALUES(1,9)")
        migrate_recipe_views(connection)
        connection.execute("UPDATE improvement_schema SET version=10 WHERE id=1")
        migrate_activations(connection)
        connection.execute("UPDATE improvement_schema SET version=11 WHERE id=1")
        migrate_canaries(connection)
        connection.execute("UPDATE improvement_schema SET version=12 WHERE id=1")
        migrate_routing(connection)
        connection.execute("UPDATE improvement_schema SET version=13 WHERE id=1")
        migrate_agents(connection)
        connection.execute("UPDATE improvement_schema SET version=14 WHERE id=1")
        migrate_bundles(connection)
        connection.execute("UPDATE improvement_schema SET version=15 WHERE id=1")
        migrate_team(connection)
        connection.execute("UPDATE improvement_schema SET version=16 WHERE id=1")
        migrate_library(connection)
        connection.execute("UPDATE improvement_schema SET version=? WHERE id=1", (SCHEMA_VERSION,))


def _immutable_triggers(connection, tables):
    for table in tables:
        for action in ("UPDATE", "DELETE"):
            connection.execute(f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} "
                               "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END")


class ImprovementStore:
    def __init__(self, goal_store, blobs: RevisionBlobs, *, qualification_anchor=None):
        if qualification_anchor is not None:
            from improvement_native_protocol import _digest
            _digest(qualification_anchor)
        self._qualification_anchor = qualification_anchor
        self.store = goal_store
        self.blobs = blobs

    @property
    def qualification_anchor(self):
        """Expected engineering run identity supplied by its trusted factory."""
        return self._qualification_anchor

    @staticmethod
    def _replay(connection, brain: str, key: str, operation: str, payload):
        if not isinstance(key, str) or not 8 <= len(key) <= 160:
            raise ValueError("invalid_event_key")
        row = connection.execute("SELECT * FROM improvement_events WHERE brain_id=? AND event_key=?",
                                 (brain, key)).fetchone()
        if row:
            if row["operation"] != operation or row["request_hash"] != _hash(payload):
                raise ConflictError("event_payload_conflict")
            return json.loads(row["result_json"])
        return None

    @staticmethod
    def _event(connection, principal, key: str, operation: str, payload, result):
        connection.execute("INSERT INTO improvement_events(brain_id,event_key,operation,request_hash,result_json,"
                           "actor,created_at) VALUES(?,?,?,?,?,?,?)",
                           (_brain(principal), key, operation, _hash(payload), _json(result), principal.by, time.time()))

    @staticmethod
    def _policy(connection, brain: str) -> dict:
        row = connection.execute("SELECT mode,version FROM improvement_policies WHERE brain_id=?", (brain,)).fetchone()
        return dict(row) if row else {"mode": "suggest", "version": 0}

    def get_policy(self, principal) -> dict:
        brain = _brain(principal)
        if not has_schema(self.store):
            return {"mode": "suggest", "version": 0}
        with closing(self.store._conn()) as connection:
            return self._policy(connection, brain)

    def set_policy(self, principal, mode: str, *, expected_version: int, event_key: str) -> dict:
        brain = _brain(principal)
        if mode not in ("off", "suggest") or type(expected_version) is not int or expected_version < 0:
            raise ValueError("unsupported_improvement_policy")
        # Turning improvement off must work even when a later guard drifted: an installed current
        # schema skips the full definition audit (policy rows touch no guarded table).
        if _schema_version(self.store) != SCHEMA_VERSION:
            ensure(self.store)
        payload = {"mode": mode, "expected_version": expected_version}
        with self.store._Tx(self.store) as connection:
            replay = self._replay(connection, brain, event_key, "policy", payload)
            if replay is not None:
                return replay
            if self._policy(connection, brain)["version"] != expected_version:
                raise ConflictError("stale_policy")
            result = {"mode": mode, "version": expected_version + 1}
            connection.execute("INSERT INTO improvement_policies(brain_id,mode,version) VALUES(?,?,?) "
                               "ON CONFLICT(brain_id) DO UPDATE SET mode=excluded.mode,version=excluded.version",
                               (brain, mode, result["version"]))
            self._event(connection, principal, event_key, "policy", payload, result)
            return result

    def targets(self, principal) -> list:
        brain = _brain(principal)
        if not has_schema(self.store):
            return []
        with closing(self.store._conn()) as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM improvement_targets WHERE brain_id=? AND status='live' ORDER BY created_at,id", (brain,))]

    @staticmethod
    def _target(connection, brain, target_id):
        row = connection.execute("SELECT * FROM improvement_targets WHERE id=? AND brain_id=?", (target_id, brain)).fetchone()
        if not row:
            raise PermissionError("target_unavailable")
        return row

    def capture(self, principal, source: SourceSnapshot, content: bytes, *, event_key: str,
                expected_generation: int | None = None) -> dict:
        brain = _brain(principal)
        if (not isinstance(source, SourceSnapshot) or not isinstance(content, bytes)
                or len(content) > MAX_ASSET_BYTES or source.kind not in ("skill", "agent")
                or not _SOURCE.fullmatch(source.canonical_ref) or not source.enabled or not source.identity
                or not source.canonical_ref.startswith("skills/" if source.kind == "skill" else "agents/")
                or (source.kind == "agent" and not source.agent_key)
                or (source.kind == "skill" and source.agent_key)
                or source.ownership not in ("user_protected", "user_managed")
                or source.source_hash != hashlib.sha256(content).hexdigest()
                or not re.fullmatch(r"[0-9a-f]{64}", source.protected_hash)
                or (expected_generation is not None and (type(expected_generation) is not int or expected_generation < 1))):
            raise ValueError("invalid_source_snapshot")
        ensure(self.store)
        manifest = asdict(source)
        payload = {"manifest": manifest, "expected_generation": expected_generation}
        with self.store._Tx(self.store) as connection:
            replay = self._replay(connection, brain, event_key, "capture", payload)
            if replay is not None:
                return replay
            if self._policy(connection, brain)["mode"] == "off":
                raise PermissionError("improvement_disabled")
            old = connection.execute("SELECT * FROM improvement_targets WHERE brain_id=? AND kind=? "
                                     "AND canonical_ref=? AND status='live'", (brain, source.kind, source.canonical_ref)).fetchone()
            if old and expected_generation is not None and old["generation"] != expected_generation:
                raise ConflictError("stale_target")
            changed = bool(old and any(old[k] != getattr(source, k) for k in
                                      ("source_hash", "protected_hash", "ownership", "identity")))
            if changed and expected_generation is None:
                raise ConflictError("source_changed")
            if not old and expected_generation is not None:
                raise ConflictError("target_missing")
            now = time.time()
            if old and old["identity"] != source.identity:
                connection.execute("UPDATE improvement_targets SET status='retired',generation=generation+1,updated_at=? "
                                   "WHERE id=?", (now, old["id"]))
                old = None
            if old is None:
                target_id = "it_" + secrets.token_hex(12)
                generation = 1
                connection.execute("INSERT INTO improvement_targets VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                   (target_id, brain, source.kind, source.canonical_ref, source.identity,
                                    source.source_hash, source.protected_hash, source.ownership, "live", 1, now, now, None))
            else:
                target_id = old["id"]
                generation = old["generation"] + int(changed)
                if changed:
                    connection.execute("UPDATE improvement_targets SET source_hash=?,protected_hash=?,ownership=?,"
                                       "generation=?,updated_at=? WHERE id=?",
                                       (source.source_hash, source.protected_hash, source.ownership, generation, now, target_id))
            digest = self.blobs.write(brain, content)
            manifest_hash = _hash(manifest)
            existing = connection.execute("SELECT id FROM improvement_revisions WHERE target_id=? AND manifest_hash=?",
                                          (target_id, manifest_hash)).fetchone()
            if existing:
                revision_id = existing["id"]
            else:
                parent_id = old["current_revision_id"] if old else None
                revision_id = "ir_" + secrets.token_hex(12)
                connection.execute("INSERT INTO improvement_revisions VALUES(?,?,?,?,?,?,?,?)",
                                   (revision_id, target_id, brain, parent_id, manifest_hash,
                                    _json(manifest), digest, now))
            connection.execute("UPDATE improvement_targets SET current_revision_id=? WHERE id=?", (revision_id, target_id))
            result = {"target_id": target_id, "revision_id": revision_id, "generation": generation,
                      "source_hash": digest, "manifest_hash": manifest_hash}
            self._event(connection, principal, event_key, "capture", payload, result)
            return result

    def revisions(self, principal, target_id: str) -> list:
        brain = _brain(principal)
        if not has_schema(self.store):
            raise PermissionError("target_unavailable")
        with closing(self.store._conn()) as connection:
            self._target(connection, brain, target_id)
            return [dict(row) for row in connection.execute("SELECT id,target_id,manifest_hash,content_hash,parent_id,"
                    "created_at FROM improvement_revisions WHERE target_id=? AND brain_id=? ORDER BY rowid", (target_id, brain))]

    def read_revision(self, principal, revision_id: str) -> bytes:
        brain = _brain(principal)
        if not has_schema(self.store):
            raise PermissionError("revision_unavailable")
        with closing(self.store._conn()) as connection:
            row = connection.execute("SELECT content_hash FROM improvement_revisions WHERE id=? AND brain_id=?",
                                     (revision_id, brain)).fetchone()
            if not row:
                raise PermissionError("revision_unavailable")
            digest = row["content_hash"]
        return self.blobs.read(brain, digest)

    def retire(self, principal, target_id: str, *, expected_generation: int, event_key: str) -> dict:
        brain = _brain(principal)
        if type(expected_generation) is not int or expected_generation < 1:
            raise ValueError("invalid_generation")
        ensure(self.store)
        payload = {"target_id": target_id, "expected_generation": expected_generation}
        with self.store._Tx(self.store) as connection:
            replay = self._replay(connection, brain, event_key, "retire", payload)
            if replay is not None:
                return replay
            row = self._target(connection, brain, target_id)
            if row["generation"] != expected_generation or row["status"] != "live":
                raise ConflictError("stale_target")
            connection.execute("UPDATE improvement_targets SET status='retired',generation=generation+1,updated_at=? "
                               "WHERE id=?", (time.time(), target_id))
            result = {"target_id": target_id, "generation": expected_generation + 1, "status": "retired"}
            self._event(connection, principal, event_key, "retire", payload, result)
            return result

    def create_bundle(self, principal, revision_ids: list[str], *, event_key: str) -> dict:
        brain = _brain(principal)
        if not revision_ids or len(revision_ids) > 100 or len(set(revision_ids)) != len(revision_ids):
            raise ValueError("invalid_bundle_assets")
        ensure(self.store)
        assets = sorted(revision_ids)
        with self.store._Tx(self.store) as connection:
            replay = self._replay(connection, brain, event_key, "bundle", assets)
            if replay is not None:
                return replay
            if self._policy(connection, brain)["mode"] == "off":
                raise PermissionError("improvement_disabled")
            manifest = []
            for revision_id in assets:
                row = connection.execute("SELECT id,target_id,manifest_hash,content_hash FROM improvement_revisions "
                                         "WHERE id=? AND brain_id=?", (revision_id, brain)).fetchone()
                if not row:
                    raise PermissionError("revision_unavailable")
                self.blobs.read(brain, row["content_hash"])
                manifest.append(dict(row))
            if len({item["target_id"] for item in manifest}) != len(manifest):
                raise ValueError("multiple_revisions_of_target")
            digest = _hash(manifest)
            old = connection.execute("SELECT id FROM improvement_bundles WHERE brain_id=? AND manifest_hash=?",
                                     (brain, digest)).fetchone()
            bundle_id = old["id"] if old else "ib_" + secrets.token_hex(12)
            if not old:
                connection.execute("INSERT INTO improvement_bundles VALUES(?,?,?,?,?)",
                                   (bundle_id, brain, digest, _json(manifest), time.time()))
                for revision_id in assets:
                    connection.execute("INSERT INTO improvement_bundle_assets VALUES(?,?,?)", (bundle_id, revision_id, brain))
            result = {"bundle_id": bundle_id, "manifest_hash": digest, "revision_ids": assets}
            self._event(connection, principal, event_key, "bundle", assets, result)
            return result

    def events(self, principal) -> list:
        brain = _brain(principal)
        if not has_schema(self.store):
            return []
        with closing(self.store._conn()) as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM improvement_events WHERE brain_id=? ORDER BY id", (brain,))]
