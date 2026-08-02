"""Capability Registry dẫn xuất cho Adaptive Context Runtime Phase 2.

Registry này không phải nguồn sự thật. Nó có thể dựng lại hoàn toàn từ tool snapshot của
MCP Hub và cấu hình model. Không lưu credential, tool arguments/result hay nội dung chat.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

import config


REGISTRY_SCHEMA_VERSION = "registry-v1"
_WORD_RE = re.compile(r"[^\W_]{2,}", re.UNICODE)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: Any) -> str:
    raw = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def brain_scope(brain: str | Path | None) -> str:
    """Hash scope để Registry không lưu raw path và không trộn capability giữa hai brain."""
    try:
        raw = str(Path(brain or "brain").resolve()).casefold()
    except Exception:
        raw = str(brain or "brain").casefold()
    return "brain_" + _sha(raw)[:20]


def _aliases(tool: dict, route_meta: dict) -> list[str]:
    vals = [tool.get("fn"), tool.get("name"), tool.get("server"), route_meta.get("tool")]
    for extra in (tool.get("aliases"), route_meta.get("aliases")):
        if isinstance(extra, (list, tuple, set)):
            vals.extend(extra)
    conn = route_meta.get("conn") or {}
    vals += [conn.get("namespace"), conn.get("label")]
    out = []
    for value in vals:
        value = str(value or "").strip()
        if value and value not in out:
            out.append(value)
        spaced = value.replace("_", " ").replace("-", " ").strip()
        if spaced and spaced not in out:
            out.append(spaced)
    return out


def _infer_effect(name: str) -> str:
    low = str(name or "").casefold()
    if any(x in low for x in ("delete", "remove", "cancel", "execute", "shell", "danger")):
        return "danger"
    if any(x in low for x in ("write", "create", "update", "send", "post", "edit", "upload")):
        return "write"
    return "read"


def _source(tool: dict, route_meta: dict, scope: str) -> tuple[str, str]:
    source_type = str(route_meta.get("source_type") or "").strip()
    source_id = str(route_meta.get("source_id") or "").strip()
    conn = route_meta.get("conn") or {}
    if conn:
        source_type = "mcp"
        source_id = str(conn.get("id") or conn.get("namespace") or tool.get("server") or "unknown")
    elif not source_type:
        source_type = "builtin"
        source_id = str(tool.get("server") or "javis")
    return source_type, f"{scope}:{source_type}:{source_id}"


class CapabilityRegistry:
    def __init__(self, state_dir: str | Path | None = None):
        self.state_dir = Path(state_dir or config.STATE_DIR)
        self.path = self.state_dir / "capability_registry.db"
        self._db: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._fts = True
        self._revision_cache: dict[str, str] = {}
        self._model_revision_cache: str | None = None

    def _open_raw(self) -> sqlite3.Connection:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(self.path), timeout=10, check_same_thread=False)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA foreign_keys=ON")
            return db
        except Exception:
            db.close()  # Windows: phải nhả handle trước khi quarantine file corrupt.
            raise

    def _schema(self, db: sqlite3.Connection) -> None:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS registry_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS capability_sources (
                source_key TEXT PRIMARY KEY,
                brain_scope TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_id_hash TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                revision TEXT NOT NULL,
                health TEXT NOT NULL,
                capability_count INTEGER NOT NULL,
                active INTEGER NOT NULL,
                last_seen_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_cap_sources_scope
                ON capability_sources(brain_scope,active);
            CREATE TABLE IF NOT EXISTS capabilities (
                capability_id TEXT PRIMARY KEY,
                source_key TEXT NOT NULL,
                brain_scope TEXT NOT NULL,
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                aliases_json TEXT NOT NULL,
                summary TEXT NOT NULL,
                intent TEXT NOT NULL,
                schema_json TEXT NOT NULL,
                schema_hash TEXT NOT NULL,
                capability_revision TEXT NOT NULL,
                side_effect TEXT NOT NULL,
                required_mode TEXT NOT NULL,
                health TEXT NOT NULL,
                active INTEGER NOT NULL,
                metadata_json TEXT NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY(source_key) REFERENCES capability_sources(source_key)
            );
            CREATE INDEX IF NOT EXISTS idx_capabilities_scope
                ON capabilities(brain_scope,active,health);
            CREATE INDEX IF NOT EXISTS idx_capabilities_name
                ON capabilities(brain_scope,name);
            CREATE INDEX IF NOT EXISTS idx_capabilities_source_key
                ON capabilities(source_key);
            CREATE TABLE IF NOT EXISTS model_profiles (
                profile_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                kind TEXT NOT NULL,
                configured INTEGER NOT NULL,
                source_hash TEXT NOT NULL,
                revision TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                active INTEGER NOT NULL,
                updated_at REAL NOT NULL
            );
            """
        )
        try:
            db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS capabilities_fts USING fts5("
                "capability_id UNINDEXED,name,aliases,summary,intent,"
                "tokenize='unicode61 remove_diacritics 2')"
            )
            self._fts = True
        except sqlite3.OperationalError:
            self._fts = False
        db.execute(
            "INSERT INTO registry_meta(key,value) VALUES('schema_version',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (REGISTRY_SCHEMA_VERSION,),
        )
        db.commit()

    def _quarantine_corrupt(self) -> None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        for suffix in ("", "-wal", "-shm"):
            src = Path(str(self.path) + suffix)
            if src.exists():
                try:
                    os.replace(src, Path(str(src) + f".corrupt-{stamp}"))
                except OSError:
                    pass

    def _conn(self) -> sqlite3.Connection:
        with self._lock:
            if self._db is not None:
                return self._db
            db = None
            try:
                db = self._open_raw()
                self._schema(db)
                if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("registry quick_check failed")
            except sqlite3.DatabaseError:
                try:
                    db.close()
                except Exception:
                    pass
                self._quarantine_corrupt()
                db = self._open_raw()
                self._schema(db)
            self._db = db
            return db

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None
            self._revision_cache.clear()
            self._model_revision_cache = None

    @staticmethod
    def schema_hash(schema: Any) -> str:
        """Canonical hash dùng chung giữa discovery, lease và executor."""
        return _sha(schema if isinstance(schema, dict) else {})

    @staticmethod
    def _tool_record(tool: dict, route_meta: dict, scope: str) -> dict:
        name = str(tool.get("fn") or tool.get("name") or "").strip()
        source_type, source_key = _source(tool, route_meta, scope)
        schema = tool.get("schema") if isinstance(tool.get("schema"), dict) else {
            "type": "object", "properties": {}
        }
        effect = str(route_meta.get("effect") or _infer_effect(name)).lower()
        if effect not in ("none", "read", "write", "danger"):
            effect = "read"
        required_mode = str(route_meta.get("required_mode") or "").lower()
        if required_mode not in ("readonly", "safe", "full"):
            required_mode = "readonly" if effect in ("none", "read") else ("safe" if effect == "write" else "full")
        summary = str(tool.get("description") or name).strip()[:2000]
        aliases = _aliases(tool, route_meta)
        payload = {
            "name": name, "aliases": aliases, "summary": summary, "schema": schema,
            "side_effect": effect, "required_mode": required_mode,
        }
        return {
            "source_type": source_type,
            "source_key": source_key,
            "source_id_hash": _sha(source_key)[:24],
            "capability_id": "cap_" + _sha(source_key + "|" + name)[:24],
            "name": name,
            "aliases": aliases,
            "summary": summary,
            "intent": " ".join(_WORD_RE.findall((name + " " + summary).casefold())[:80]),
            "schema": schema,
            "schema_hash": _sha(schema),
            "revision": _sha(payload),
            "side_effect": effect,
            "required_mode": required_mode,
            "health": str(route_meta.get("health") or "healthy"),
            "metadata": {
                "server": str(tool.get("server") or "")[:120],
                "multiplexed": bool(route_meta.get("multiplexed", False)),
            },
        }

    def refresh_tools(self, brain: str | Path, tools: Iterable[dict], route: dict) -> dict:
        """Upsert snapshot theo source. Source không đổi chỉ cập nhật last_seen, không churn revision."""
        scope = brain_scope(brain)
        records = []
        for tool in tools or []:
            if not isinstance(tool, dict):
                continue
            name = str(tool.get("fn") or tool.get("name") or "").strip()
            if not name:
                continue
            records.append(self._tool_record(tool, (route or {}).get(name) or {}, scope))
        grouped: dict[str, list[dict]] = {}
        for record in records:
            grouped.setdefault(record["source_key"], []).append(record)
        now = time.time()
        changed_sources = 0
        with self._lock:
            db = self._conn()
            with db:
                # Sweep phải gồm cả 'plugin': plugin gỡ đi mà không sweep thì capability
                # "healthy" ma tồn tại vĩnh viễn và resolver vẫn chọn nó. 'skill' do
                # refresh_skills sở hữu nên vẫn loại trừ.
                old_keys = {r[0] for r in db.execute(
                    "SELECT source_key FROM capability_sources WHERE brain_scope=? AND active=1 "
                    "AND source_type IN ('mcp','builtin','plugin')", (scope,)
                )}
                new_keys = set(grouped)
                for removed in old_keys - new_keys:
                    db.execute("UPDATE capability_sources SET active=0,updated_at=? WHERE source_key=?", (now, removed))
                    db.execute("UPDATE capabilities SET active=0,updated_at=? WHERE source_key=?", (now, removed))
                    changed_sources += 1
                for source_key, source_records in grouped.items():
                    source_records.sort(key=lambda x: x["name"])
                    source_hash = _sha([{
                        "name": x["name"], "revision": x["revision"], "health": x["health"]
                    } for x in source_records])
                    previous = db.execute(
                        "SELECT source_hash,active FROM capability_sources WHERE source_key=?", (source_key,)
                    ).fetchone()
                    if previous and previous["source_hash"] == source_hash and previous["active"]:
                        db.execute("UPDATE capability_sources SET last_seen_at=? WHERE source_key=?", (now, source_key))
                        continue
                    changed_sources += 1
                    first = source_records[0]
                    db.execute(
                        "INSERT INTO capability_sources VALUES(?,?,?,?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(source_key) DO UPDATE SET source_hash=excluded.source_hash,"
                        "revision=excluded.revision,health=excluded.health,"
                        "capability_count=excluded.capability_count,active=1,"
                        "last_seen_at=excluded.last_seen_at,updated_at=excluded.updated_at",
                        (source_key, scope, first["source_type"], first["source_id_hash"], source_hash,
                         source_hash[:24], "healthy", len(source_records), 1, now, now),
                    )
                    old_ids = [r[0] for r in db.execute(
                        "SELECT capability_id FROM capabilities WHERE source_key=?", (source_key,)
                    )]
                    if self._fts and old_ids:
                        # Một câu DELETE IN (...) = một lần quét FTS thay vì N lần
                        # (capability_id là cột UNINDEXED nên mỗi DELETE là full scan).
                        placeholders = ",".join("?" for _ in old_ids)
                        db.execute(
                            f"DELETE FROM capabilities_fts WHERE capability_id IN ({placeholders})",
                            old_ids,
                        )
                    db.execute("DELETE FROM capabilities WHERE source_key=?", (source_key,))
                    # Dedupe theo capability_id: hai tool trùng tên trong một source không
                    # được phép nổ IntegrityError làm rollback TOÀN BỘ refresh của brain.
                    seen_capability_ids: set[str] = set()
                    for item in source_records:
                        if item["capability_id"] in seen_capability_ids:
                            continue
                        seen_capability_ids.add(item["capability_id"])
                        db.execute(
                            "INSERT INTO capabilities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (item["capability_id"], source_key, scope, "tool", item["name"],
                             _json(item["aliases"]), item["summary"], item["intent"], _json(item["schema"]),
                             item["schema_hash"], item["revision"], item["side_effect"],
                             item["required_mode"], item["health"], 1, _json(item["metadata"]), now),
                        )
                        if self._fts:
                            db.execute(
                                "INSERT INTO capabilities_fts VALUES(?,?,?,?,?)",
                                (item["capability_id"], item["name"], " ".join(item["aliases"]),
                                 item["summary"], item["intent"]),
                            )
                self._set_meta(db, f"last_refresh:{scope}", str(now))
                self._revision_cache.pop(scope, None)
        return {
            "brain_scope": scope,
            "capability_count": len(records),
            "source_count": len(grouped),
            "changed_sources": changed_sources,
            "revision": self.revision(brain),
        }

    def refresh_workflows(self, brain: str | Path, manifests: Iterable[dict]) -> dict:
        """Refresh a derived WorkflowSource: metadata + hợp đồng, KHÔNG kèm thân node.

        Workflow vào Registry với kind `workflow`. Resolver hard-filter kind này khỏi
        đường chọn tool y như `skill`, nên thêm workflow không làm prompt đầu nạp to ra.
        """
        scope = brain_scope(brain)
        source_key = f"{scope}:workflow:brain-workflows"
        records = []
        for manifest in manifests or []:
            if not isinstance(manifest, dict):
                continue
            slug = str(manifest.get("slug") or "").strip()
            if not slug:
                continue
            name = str(manifest.get("name") or slug).strip()[:180]
            summary = str(manifest.get("description") or name).strip()[:2000]
            aliases = list(dict.fromkeys([slug, name]))
            payload = {
                "slug": slug, "name": name, "summary": summary,
                "revision": str(manifest.get("revision") or "")[:128],
                "adapter": str(manifest.get("adapter") or "")[:60],
                "node_count": int(manifest.get("node_count") or 0),
                "max_risk": str(manifest.get("max_risk") or "none")[:20],
                "resumable": bool(manifest.get("resumable")),
                "has_write_node": bool(manifest.get("has_write_node")),
                "nested_slugs": list(manifest.get("nested_slugs") or []),
                "input_contract": manifest.get("input_contract") or {},
                "output_contract": manifest.get("output_contract") or {},
                "path": str(manifest.get("relative_path") or "")[:500],
            }
            records.append({
                "capability_id": "workflow_" + _sha(source_key + "|" + slug)[:24],
                "name": slug, "aliases": aliases, "summary": summary,
                "intent": " ".join(_WORD_RE.findall((name + " " + summary).casefold())[:80]),
                "revision": _sha(payload), "metadata": payload,
            })
        return self._refresh_derived_kind(brain, scope, source_key, "workflow", records)

    def refresh_skills(self, brain: str | Path, manifests: Iterable[dict]) -> dict:
        """Refresh a derived SkillSource using metadata/path only, never SKILL.md bodies."""
        scope = brain_scope(brain)
        source_key = f"{scope}:skill:brain-skills"
        records = []
        for manifest in manifests or []:
            if not isinstance(manifest, dict):
                continue
            slug = str(manifest.get("slug") or "").strip()
            if not slug:
                continue
            name = str(manifest.get("name") or slug).strip()[:180]
            summary = str(manifest.get("description") or name).strip()[:2000]
            group = str(manifest.get("group") or "Chung").strip()[:120]
            aliases = list(dict.fromkeys([slug, name, group]))
            payload = {
                "slug": slug, "name": name, "summary": summary, "group": group,
                "path": str(manifest.get("relative_path") or "")[:500],
                "frontmatter_hash": str(manifest.get("frontmatter_hash") or "")[:128],
            }
            records.append({
                "capability_id": "skill_" + _sha(source_key + "|" + slug)[:24],
                "name": slug, "aliases": aliases, "summary": summary,
                "intent": " ".join(_WORD_RE.findall((name + " " + summary + " " + group).casefold())[:80]),
                "revision": _sha(payload), "metadata": payload,
            })
        return self._refresh_derived_kind(brain, scope, source_key, "skill", records)

    def _refresh_derived_kind(self, brain: str | Path, scope: str, source_key: str,
                              kind: str, records: list[dict]) -> dict:
        """Thân chung cho các source DẪN XUẤT chỉ có metadata (skill, workflow).

        Chúng không phải tool: schema rỗng, effect `read`, và Resolver hard-filter
        theo kind nên chúng không bao giờ lọt vào danh sách tool gửi model.
        """
        records.sort(key=lambda x: x["name"])
        source_hash = _sha([{"name": x["name"], "revision": x["revision"]} for x in records])
        now = time.time()
        with self._lock:
            db = self._conn()
            with db:
                previous = db.execute(
                    "SELECT source_hash,active FROM capability_sources WHERE source_key=?", (source_key,)
                ).fetchone()
                changed = not (previous and previous["source_hash"] == source_hash and previous["active"])
                db.execute(
                    "INSERT INTO capability_sources VALUES(?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(source_key) DO UPDATE SET source_hash=excluded.source_hash,"
                    "revision=excluded.revision,health='healthy',capability_count=excluded.capability_count,"
                    "active=1,last_seen_at=excluded.last_seen_at,updated_at=excluded.updated_at",
                    (source_key, scope, kind, _sha(source_key)[:24], source_hash,
                     source_hash[:24], "healthy", len(records), 1, now, now),
                )
                if changed:
                    old_ids = [r[0] for r in db.execute(
                        "SELECT capability_id FROM capabilities WHERE source_key=?", (source_key,)
                    )]
                    if self._fts and old_ids:
                        placeholders = ",".join("?" for _ in old_ids)
                        db.execute(
                            f"DELETE FROM capabilities_fts WHERE capability_id IN ({placeholders})",
                            old_ids,
                        )
                    db.execute("DELETE FROM capabilities WHERE source_key=?", (source_key,))
                    empty_schema = {"type": "object", "properties": {}}
                    for item in records:
                        db.execute(
                            "INSERT INTO capabilities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (item["capability_id"], source_key, scope, kind, item["name"],
                             _json(item["aliases"]), item["summary"], item["intent"], _json(empty_schema),
                             _sha(empty_schema), item["revision"], "read", "readonly", "healthy", 1,
                             _json(item["metadata"]), now),
                        )
                        if self._fts:
                            db.execute(
                                "INSERT INTO capabilities_fts VALUES(?,?,?,?,?)",
                                (item["capability_id"], item["name"], " ".join(item["aliases"]),
                                 item["summary"], item["intent"]),
                            )
                self._set_meta(db, f"last_refresh_{kind}:{scope}", str(now))
                self._revision_cache.pop(scope, None)
        return {"brain_scope": scope, "capability_count": len(records),
                "changed_sources": int(changed), "revision": self.revision(brain)}

    @staticmethod
    def _set_meta(db: sqlite3.Connection, key: str, value: str) -> None:
        db.execute(
            "INSERT INTO registry_meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value)
        )

    def refresh_model_profile(self, provider: str, model: str, kind: str = "unknown",
                              configured: bool = True, metadata: dict | None = None) -> dict:
        provider, model = str(provider or "unknown"), str(model or "unknown")
        profile_id = "model_" + _sha(provider + "|" + model)[:24]
        safe_meta = {str(k)[:80]: v for k, v in (metadata or {}).items()
                     if isinstance(v, (str, int, float, bool)) or v is None}
        source_hash = _sha({"provider": provider, "model": model, "kind": kind,
                            "configured": bool(configured), "metadata": safe_meta})
        now = time.time()
        with self._lock:
            db = self._conn()
            with db:
                db.execute(
                    "INSERT INTO model_profiles VALUES(?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(profile_id) DO UPDATE SET kind=excluded.kind,"
                    "configured=excluded.configured,source_hash=excluded.source_hash,"
                    "revision=excluded.revision,metadata_json=excluded.metadata_json,"
                    "active=1,updated_at=excluded.updated_at",
                    (profile_id, provider, model, str(kind or "unknown"), int(bool(configured)),
                     source_hash, source_hash[:24], _json(safe_meta), 1, now),
                )
                self._model_revision_cache = None
                self._revision_cache.clear()
        return {"profile_id": profile_id, "revision": source_hash[:24]}

    def revision(self, brain: str | Path | None = None) -> str:
        scope = brain_scope(brain)
        with self._lock:
            if scope in self._revision_cache:
                return self._revision_cache[scope]
            db = self._conn()
            caps = [r[0] for r in db.execute(
                "SELECT capability_revision FROM capabilities "
                "WHERE brain_scope=? AND active=1 ORDER BY capability_id", (scope,)
            )]
            models = [r[0] for r in db.execute(
                "SELECT revision FROM model_profiles WHERE active=1 ORDER BY profile_id"
            )]
            revision = "reg_" + _sha({"caps": caps, "models": models})[:24]
            self._revision_cache[scope] = revision
            return revision

    def model_revision(self) -> str:
        with self._lock:
            if self._model_revision_cache is not None:
                return self._model_revision_cache
            rows = [r[0] for r in self._conn().execute(
                "SELECT revision FROM model_profiles WHERE active=1 ORDER BY profile_id"
            )]
            self._model_revision_cache = "models_" + _sha(rows)[:24]
            return self._model_revision_cache

    def inventory_status(self, brain: str | Path | None = None) -> dict:
        """Độ tươi snapshot capability, kể cả snapshot hợp lệ có 0 capability."""
        scope = brain_scope(brain)
        with self._lock:
            row = self._conn().execute(
                "SELECT value FROM registry_meta WHERE key=?", (f"last_refresh:{scope}",)
            ).fetchone()
        try:
            refreshed_at = float(row[0]) if row else 0.0
        except (TypeError, ValueError):
            refreshed_at = 0.0
        return {
            "ready": refreshed_at > 0,
            "refreshed_at": refreshed_at,
            "age_seconds": max(0.0, time.time() - refreshed_at) if refreshed_at else None,
            "revision": self.revision(brain),
        }

    def search(self, query: str, brain: str | Path, limit: int = 80) -> list[dict]:
        scope = brain_scope(brain)
        terms = list(dict.fromkeys(_WORD_RE.findall(str(query or "").casefold())))
        if not terms:
            return []
        limit = max(1, min(int(limit or 80), 500))
        with self._lock:
            db = self._conn()
            rows = []
            if self._fts:
                match = " OR ".join('"' + t.replace('"', '') + '"*' for t in terms[:20])
                try:
                    rows = db.execute(
                        "SELECT c.*,s.source_type,bm25(capabilities_fts) AS fts_rank FROM capabilities_fts "
                        "JOIN capabilities c ON c.capability_id=capabilities_fts.capability_id "
                        "JOIN capability_sources s ON s.source_key=c.source_key "
                        "WHERE capabilities_fts MATCH ? AND c.brain_scope=? AND c.active=1 "
                        "ORDER BY fts_rank LIMIT ?", (match, scope, limit)
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            if not rows:
                like = "%" + terms[0] + "%"
                rows = db.execute(
                    "SELECT c.*,s.source_type,0.0 AS fts_rank FROM capabilities c "
                    "JOIN capability_sources s ON s.source_key=c.source_key WHERE c.brain_scope=? "
                    "AND c.active=1 AND (lower(c.name) LIKE ? OR lower(c.summary) LIKE ? "
                    "OR lower(c.aliases_json) LIKE ?) ORDER BY c.name LIMIT ?",
                    (scope, like, like, like, limit)
                ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["aliases"] = json.loads(item.pop("aliases_json") or "[]")
            item["schema"] = json.loads(item.pop("schema_json") or "{}")
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            out.append(item)
        return out

    def get_capabilities(self, capability_ids: Iterable[str], brain: str | Path) -> list[dict]:
        """Lấy exact schema theo ID nhưng vẫn hard-scope theo brain; giữ thứ tự resolver."""
        ordered = [str(x) for x in capability_ids or [] if str(x)]
        if not ordered:
            return []
        scope = brain_scope(brain)
        marks = ",".join("?" for _ in ordered)
        with self._lock:
            rows = self._conn().execute(
                f"SELECT c.*,s.source_type FROM capabilities c JOIN capability_sources s "
                f"ON s.source_key=c.source_key WHERE c.capability_id IN ({marks}) "
                "AND c.brain_scope=? AND c.active=1 AND c.health='healthy'",
                (*ordered, scope),
            ).fetchall()
        by_id = {}
        for row in rows:
            item = dict(row)
            item["aliases"] = json.loads(item.pop("aliases_json") or "[]")
            item["schema"] = json.loads(item.pop("schema_json") or "{}")
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            by_id[item["capability_id"]] = item
        return [by_id[x] for x in ordered if x in by_id]

    def get_model_profile(self, provider: str, model: str) -> dict:
        profile_id = "model_" + _sha(str(provider or "unknown") + "|" + str(model or "unknown"))[:24]
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM model_profiles WHERE profile_id=? AND active=1", (profile_id,)
            ).fetchone()
        if not row:
            return {"provider": str(provider or "unknown"), "model": str(model or "unknown"),
                    "kind": "unknown", "configured": False, "metadata": {},
                    "revision": "unobserved"}
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        item["configured"] = bool(item.get("configured"))
        return item

    def integrity_check(self, brain: str | Path | None = None) -> dict:
        scope = brain_scope(brain)
        with self._lock:
            db = self._conn()
            quick = db.execute("PRAGMA quick_check").fetchone()[0]
            caps = db.execute(
                "SELECT COUNT(*) FROM capabilities WHERE brain_scope=? AND active=1", (scope,)
            ).fetchone()[0]
            sources = db.execute(
                "SELECT COUNT(*) FROM capability_sources WHERE brain_scope=? AND active=1", (scope,)
            ).fetchone()[0]
            duplicates = db.execute(
                "SELECT COUNT(*) FROM (SELECT kind,name FROM capabilities WHERE brain_scope=? AND active=1 "
                "GROUP BY kind,name HAVING COUNT(*)>1)", (scope,)
            ).fetchone()[0]
            fts_rows = db.execute("SELECT COUNT(*) FROM capabilities_fts").fetchone()[0] if self._fts else None
        return {"ok": quick == "ok" and duplicates == 0, "quick_check": quick,
                "capabilities": caps, "sources": sources, "duplicate_names": duplicates,
                "fts_enabled": self._fts, "fts_rows": fts_rows,
                "revision": self.revision(brain)}


_REGISTRY: CapabilityRegistry | None = None


def get_registry() -> CapabilityRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = CapabilityRegistry()
    return _REGISTRY
