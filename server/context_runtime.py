"""Trace substrate cho Adaptive Context Runtime Phase 0-3.

Substrate này chỉ làm ba việc:
- gắn task_id/step_id ổn định vào một lượt chat;
- ghi metadata đã redaction để đo payload, usage và quota reservation;
- lưu state tối thiểu trong runtime.db để các phase sau có chỗ mở rộng.

Module này CỐ Ý không lưu raw prompt, message, tool arguments/result hay secret. Registry và
Resolver Phase 2-3 chạy shadow; chưa được phép chặn, đổi model, rút context hoặc thay dispatch.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import math
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import config


RUNTIME_VERSION = "shadow-v2"
RESOLVER_POLICY_VERSION = "deterministic-shadow-v1"
COMPILER_POLICY_VERSION = "legacy-observe-v1"
REGISTRY_REVISION = "legacy-live"
MODEL_PROFILE_REVISION = "settings-live"

_CURRENT: contextvars.ContextVar[Optional["TurnTrace"]] = contextvars.ContextVar(
    "javis_context_runtime_trace", default=None
)


@dataclass
class TurnTrace:
    task_id: str
    step_id: str
    session_id: str
    channel: str
    had_error: bool = False
    expected_version: int = 1
    registry_revision: str = "registry-unavailable"
    model_profile_revision: str = "models-unavailable"


def current_trace() -> Optional[TurnTrace]:
    return _CURRENT.get()


def bind_trace(trace: Optional[TurnTrace]):
    return _CURRENT.set(trace)


def reset_trace(token) -> None:
    _CURRENT.reset(token)


def event_fields(trace: Optional[TurnTrace]) -> dict:
    if not trace:
        return {}
    return {"task_id": trace.task_id, "step_id": trace.step_id}


def _json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        return len(str(value or ""))


def _content_chars(content: Any) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(_content_chars(x) for x in content)
    if isinstance(content, dict):
        # Chỉ dùng để đếm trong RAM. Không trả hoặc lưu nội dung dict.
        return _json_size(content)
    return len(str(content or ""))


_SYSTEM_MARKERS = (
    ("memory_index_chars", "# === BỘ NHỚ DÀI HẠN"),
    ("agentic_contract_chars", "# === LỚP AGENTIC"),
    ("capability_summary_chars", "# === NĂNG LỰC JAVIS"),
    ("skill_router_chars", "# === SKILL KHẢ DỤNG"),
    ("usage_hint_chars", "# === MỨC DÙNG HÔM NAY"),
    ("channel_contract_chars", "# === KÊNH HỘI THOẠI HIỆN TẠI"),
    ("provider_identity_chars", "[Sự thật hệ thống"),
)


def _system_attribution(content: Any, primary: bool) -> dict:
    """Tách block system theo marker trong RAM; chỉ trả độ dài từng block."""
    out = {
        "core_contract_chars": 0,
        "memory_index_chars": 0,
        "agentic_contract_chars": 0,
        "capability_summary_chars": 0,
        "skill_router_chars": 0,
        "usage_hint_chars": 0,
        "channel_contract_chars": 0,
        "provider_identity_chars": 0,
        "unclassified_system_chars": 0,
    }
    if not isinstance(content, str):
        out["unclassified_system_chars"] = _content_chars(content)
        return out
    starts = []
    for bucket, marker in _SYSTEM_MARKERS:
        pos = content.find(marker)
        if pos >= 0:
            starts.append((pos, bucket))
    starts.sort()
    if not starts:
        out["core_contract_chars" if primary else "unclassified_system_chars"] = len(content)
        return out
    first = starts[0][0]
    out["core_contract_chars" if primary else "unclassified_system_chars"] += first
    for index, (pos, bucket) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(content)
        out[bucket] += end - pos
    return out


def payload_attribution(messages, tools=None, chars_per_token: float = 3.0) -> dict:
    """Trả METADATA kích thước, không trả nội dung.

    chars_per_token chỉ là estimator observe-only. Usage thật từ provider sẽ được reconcile
    để phase sau hiệu chỉnh theo model; tuyệt đối không dùng số này để chặn request ở Phase 1.
    """
    buckets = {
        "system_chars": 0,
        "user_chars": 0,
        "assistant_chars": 0,
        "tool_result_chars": 0,
        "other_chars": 0,
    }
    count = 0
    component_buckets = _system_attribution("", primary=True)
    user_positions = [i for i, m in enumerate(messages or [])
                      if isinstance(m, dict) and str(m.get("role") or "") == "user"]
    last_user = user_positions[-1] if user_positions else -1
    history_user_chars = 0
    current_user_chars = 0
    system_seen = 0
    for index, msg in enumerate(messages or []):
        if not isinstance(msg, dict):
            buckets["other_chars"] += _content_chars(msg)
            count += 1
            continue
        role = str(msg.get("role") or "other")
        n = _content_chars(msg.get("content"))
        key = {
            "system": "system_chars",
            "user": "user_chars",
            "assistant": "assistant_chars",
            "tool": "tool_result_chars",
        }.get(role, "other_chars")
        buckets[key] += n
        if role == "system":
            parts = _system_attribution(msg.get("content"), primary=(system_seen == 0))
            system_seen += 1
            for part, size in parts.items():
                component_buckets[part] += size
        elif role == "user":
            if index == last_user:
                current_user_chars += n
            else:
                history_user_chars += n
        count += 1
    tool_chars = _json_size(tools or []) if tools else 0
    wire_chars = _json_size(messages or []) + tool_chars
    ratio = max(1.0, float(chars_per_token or 3.0))
    estimate = int(math.ceil(wire_chars / ratio)) if wire_chars else 0
    return {
        **buckets,
        **component_buckets,
        "history_user_chars": history_user_chars,
        "current_user_chars": current_user_chars,
        "message_count": count,
        "tool_count": len(tools or []),
        "tool_schema_chars": tool_chars,
        "wire_chars": wire_chars,
        "estimated_input_tokens": estimate,
        "estimate_method": "chars_ratio_observe_v1",
        "chars_per_token": ratio,
    }


class ObserveRuntime:
    """SQLite observe store. Mọi public method đều best-effort, không phá lượt chat."""

    def __init__(self, state_dir: Path | str | None = None,
                 settings_reader: Callable[[], dict] | None = None):
        self.state_dir = Path(state_dir or config.STATE_DIR)
        self.path = self.state_dir / "runtime.db"
        self._settings_reader = settings_reader or config.read_settings
        self._lock = threading.RLock()
        self._db: sqlite3.Connection | None = None
        self._cleaned = False

    def _policy(self) -> dict:
        try:
            raw = (self._settings_reader() or {}).get("context_runtime", {}) or {}
        except Exception:
            raw = {}
        return {
            "mode": str(raw.get("mode") or "observe").lower(),
            "retention_days": max(1, int(raw.get("retention_days") or 14)),
            # Phase 0-1 hard-enforce metadata only dù settings bị sửa tay.
            "store_content": False,
            "export_enabled": bool(raw.get("export_enabled", False)),
            "chars_per_token": max(1.0, float(raw.get("estimate_chars_per_token") or 3.0)),
        }

    def enabled(self) -> bool:
        return self._policy()["mode"] in ("observe", "shadow", "canary", "on")

    def _conn(self) -> sqlite3.Connection:
        with self._lock:
            if self._db is not None:
                return self._db
            self.state_dir.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(str(self.path), check_same_thread=False, timeout=10)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS runtime_tasks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    brain TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    runtime_version TEXT NOT NULL,
                    resolver_policy_version TEXT NOT NULL,
                    compiler_policy_version TEXT NOT NULL,
                    registry_revision TEXT NOT NULL,
                    model_profile_revision TEXT NOT NULL,
                    budget_json TEXT NOT NULL DEFAULT '{}',
                    deadline_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runtime_steps (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    attempt INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT,
                    model TEXT,
                    estimated_input_tokens INTEGER,
                    actual_input_tokens INTEGER,
                    actual_output_tokens INTEGER,
                    started_at REAL NOT NULL,
                    completed_at REAL,
                    error_code TEXT,
                    FOREIGN KEY(task_id) REFERENCES runtime_tasks(id)
                );
                CREATE TABLE IF NOT EXISTS runtime_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    step_id TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runtime_events_task
                    ON runtime_events(task_id, seq);
                CREATE TABLE IF NOT EXISTS runtime_evidence_refs (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_ref_hash TEXT NOT NULL,
                    trust TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES runtime_tasks(id)
                );
                CREATE TABLE IF NOT EXISTS quota_reservations (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_reserved INTEGER NOT NULL,
                    output_reserved INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_quota_reservations_model
                    ON quota_reservations(provider, model, created_at);
                """
            )
            # Migrate an observe DB created by an earlier build without rewriting state.
            columns = {r[1] for r in db.execute("PRAGMA table_info(runtime_tasks)")}
            if "budget_json" not in columns:
                db.execute("ALTER TABLE runtime_tasks ADD COLUMN budget_json TEXT NOT NULL DEFAULT '{}'")
            if "deadline_at" not in columns:
                db.execute("ALTER TABLE runtime_tasks ADD COLUMN deadline_at REAL")
            db.commit()
            self._db = db
            self._cleanup_once()
            return db

    def _cleanup_once(self) -> None:
        if self._cleaned or self._db is None:
            return
        self._cleaned = True
        cutoff = time.time() - self._policy()["retention_days"] * 86400
        try:
            old = [r[0] for r in self._db.execute(
                "SELECT id FROM runtime_tasks WHERE created_at < ?", (cutoff,)
            ).fetchall()]
            if old:
                marks = ",".join("?" for _ in old)
                for table in ("quota_reservations", "runtime_evidence_refs",
                              "runtime_events", "runtime_steps"):
                    self._db.execute(f"DELETE FROM {table} WHERE task_id IN ({marks})", old)
                self._db.execute(f"DELETE FROM runtime_tasks WHERE id IN ({marks})", old)
                self._db.commit()
        except Exception:
            pass

    @staticmethod
    def _safe_payload(data: dict | None) -> str:
        """Allowlist scalar metadata. Không có đường nào ghi raw content vào event."""
        out = {}
        for key, value in (data or {}).items():
            if key in {"content", "prompt", "messages", "tools", "args", "result", "secret"}:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                out[str(key)[:80]] = value
        return json.dumps(out, ensure_ascii=False, separators=(",", ":"))

    def _event(self, db, trace: TurnTrace, kind: str, data: dict | None = None) -> None:
        db.execute(
            "INSERT INTO runtime_events(task_id,step_id,event_type,payload_json,created_at) "
            "VALUES(?,?,?,?,?)",
            (trace.task_id, trace.step_id, kind, self._safe_payload(data), time.time()),
        )

    @staticmethod
    def _expire_reservations(db, now: float | None = None) -> None:
        db.execute(
            "UPDATE quota_reservations SET status='EXPIRED' "
            "WHERE status='OBSERVED' AND expires_at<=?",
            (float(now or time.time()),),
        )

    def start_turn(self, session_id: str, brain: str, channel: str,
                   token_budget: dict | None = None,
                   deadline_seconds: float | None = None) -> Optional[TurnTrace]:
        if not self.enabled():
            return None
        registry_revision, model_revision = REGISTRY_REVISION, MODEL_PROFILE_REVISION
        try:
            from capability_registry import get_registry
            registry = get_registry()
            registry_revision = registry.revision(brain)
            model_revision = registry.model_revision()
        except Exception:
            pass
        trace = TurnTrace(
            task_id="rt_" + uuid.uuid4().hex,
            step_id="rs_" + uuid.uuid4().hex,
            session_id=str(session_id or ""),
            channel=str(channel or "unknown"),
            registry_revision=registry_revision,
            model_profile_revision=model_revision,
        )
        now = time.time()
        budget = token_budget if isinstance(token_budget, dict) else {
            "mode": "observe", "enforced": False,
            "input_tokens": None, "output_tokens": None,
        }
        deadline_at = now + float(deadline_seconds) if deadline_seconds and deadline_seconds > 0 else None
        try:
            with self._lock:
                db = self._conn()
                with db:
                    self._expire_reservations(db, now)
                    db.execute(
                        "INSERT INTO runtime_tasks("
                        "id,session_id,brain,channel,status,version,runtime_version,"
                        "resolver_policy_version,compiler_policy_version,registry_revision,"
                        "model_profile_revision,budget_json,deadline_at,created_at,updated_at"
                        ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (trace.task_id, trace.session_id, str(brain or ""), trace.channel,
                         "RUNNING", 1, RUNTIME_VERSION, RESOLVER_POLICY_VERSION,
                         COMPILER_POLICY_VERSION, trace.registry_revision,
                         trace.model_profile_revision,
                         json.dumps(budget, ensure_ascii=False, separators=(",", ":")),
                         deadline_at, now, now),
                    )
                    db.execute(
                        "INSERT INTO runtime_steps(id,task_id,ordinal,attempt,status,started_at) "
                        "VALUES(?,?,?,?,?,?)",
                        (trace.step_id, trace.task_id, 1, 1, "RUNNING", now),
                    )
                    self._event(db, trace, "task.started", {"channel": trace.channel})
            return trace
        except Exception:
            return None

    def set_route(self, trace: Optional[TurnTrace], provider: str, model: str) -> None:
        if not trace:
            return
        try:
            with self._lock:
                db = self._conn()
                with db:
                    db.execute("UPDATE runtime_steps SET provider=?,model=? WHERE id=?",
                               (str(provider or "?"), str(model or "?"), trace.step_id))
                    self._event(db, trace, "route.observed",
                                {"provider": provider or "?", "model": model or "?"})
        except Exception:
            pass

    def observe_payload(self, trace: Optional[TurnTrace], messages, tools=None,
                        provider: str = "", model: str = "") -> dict:
        if not trace:
            return {}
        meta = payload_attribution(
            messages, tools, chars_per_token=self._policy()["chars_per_token"]
        )
        try:
            with self._lock:
                db = self._conn()
                now = time.time()
                reservation_id = "qr_" + uuid.uuid4().hex
                with db:
                    db.execute(
                        "UPDATE runtime_steps SET provider=COALESCE(NULLIF(?,''),provider),"
                        "model=COALESCE(NULLIF(?,''),model),"
                        "estimated_input_tokens=COALESCE(estimated_input_tokens,0)+? WHERE id=?",
                        (provider, model, meta["estimated_input_tokens"], trace.step_id),
                    )
                    self._event(db, trace, "payload.observed", meta)
                    db.execute(
                        "INSERT INTO quota_reservations VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (reservation_id, trace.task_id, trace.step_id, provider or "?", model or "?",
                         meta["estimated_input_tokens"], 0, "OBSERVED", now + 300, now),
                    )
            return meta
        except Exception:
            return meta

    def record_usage(self, trace: Optional[TurnTrace], input_tokens=0, output_tokens=0) -> None:
        if not trace:
            return
        tin, tout = int(input_tokens or 0), int(output_tokens or 0)
        try:
            with self._lock:
                db = self._conn()
                with db:
                    self._expire_reservations(db)
                    db.execute(
                        "UPDATE runtime_steps SET "
                        "actual_input_tokens=COALESCE(actual_input_tokens,0)+?,"
                        "actual_output_tokens=COALESCE(actual_output_tokens,0)+? WHERE id=?",
                        (tin, tout, trace.step_id),
                    )
                    db.execute(
                        "UPDATE quota_reservations SET status='RECONCILED' WHERE id=("
                        "SELECT id FROM quota_reservations WHERE task_id=? AND step_id=? "
                        "AND status='OBSERVED' ORDER BY created_at,id LIMIT 1)",
                        (trace.task_id, trace.step_id),
                    )
                    self._event(db, trace, "usage.observed",
                                {"input_tokens": tin, "output_tokens": tout})
        except Exception:
            pass

    def add_evidence_ref(self, trace: Optional[TurnTrace], source_type: str,
                         source_ref: str, trust: str = "observed") -> Optional[str]:
        """Lưu ref tối thiểu dạng hash; nội dung và đường dẫn gốc không vào trace Phase 1."""
        if not trace or not source_ref:
            return None
        evidence_id = "re_" + uuid.uuid4().hex
        ref_hash = hashlib.sha256(str(source_ref).encode("utf-8", errors="replace")).hexdigest()
        try:
            with self._lock:
                db = self._conn()
                with db:
                    db.execute(
                        "INSERT INTO runtime_evidence_refs VALUES(?,?,?,?,?,?,?)",
                        (evidence_id, trace.task_id, trace.step_id,
                         str(source_type or "unknown")[:80], ref_hash,
                         str(trust or "observed")[:40], time.time()),
                    )
                    self._event(db, trace, "evidence.ref_observed", {
                        "evidence_id": evidence_id,
                        "source_type": str(source_type or "unknown")[:80],
                        "trust": str(trust or "observed")[:40],
                    })
            return evidence_id
        except Exception:
            return None

    def record_shadow_resolution(self, trace: Optional[TurnTrace], report: dict) -> None:
        """Ghi quyết định shadow đã redaction. Query thô và capability schema không vào trace."""
        if not trace:
            return
        selected = report.get("selected") or []
        selected_ids = ",".join(str(x.get("capability_id") or "") for x in selected[:20])
        filtered = report.get("filtered") or {}
        filtered_counts = ",".join(f"{k}:{filtered[k]}" for k in sorted(filtered))
        data = {
            "policy_version": report.get("policy_version"),
            "registry_revision": report.get("registry_revision"),
            "pinned_registry_revision": trace.registry_revision,
            "revision_mismatch": report.get("registry_revision") != trace.registry_revision,
            "query_hash": report.get("query_hash"),
            "query_term_count": report.get("query_term_count", 0),
            "candidate_count": report.get("candidate_count", 0),
            "selected_count": report.get("selected_count", 0),
            "selected_ids": selected_ids,
            "filtered_counts": filtered_counts,
            "miss_class": report.get("miss_class") or "",
            "cutoff": report.get("cutoff", 0),
            "cutoff_reason": report.get("cutoff_reason") or "",
            "top_score_gap": report.get("top_score_gap", 0),
            "embedding_candidate_count": report.get("embedding_candidate_count", 0),
            "embedding_lexical_overlap": report.get("embedding_lexical_overlap", 0),
            "latency_ms": report.get("latency_ms", 0),
        }
        try:
            with self._lock:
                db = self._conn()
                with db:
                    self._event(db, trace, "resolver.shadow", data)
        except Exception:
            pass

    def note_error(self, trace: Optional[TurnTrace], error_code: str) -> None:
        if not trace:
            return
        trace.had_error = True
        try:
            with self._lock:
                db = self._conn()
                with db:
                    self._event(db, trace, "turn.error", {"error_code": str(error_code)[:120]})
        except Exception:
            pass

    def finish(self, trace: Optional[TurnTrace], status: str = "COMPLETED",
               error_code: str = "") -> bool:
        if not trace:
            return False
        safe_status = status if status in {
            "COMPLETED", "COMPLETED_WITH_ERROR", "FAILED", "CANCELLED"
        } else "FAILED"
        now = time.time()
        try:
            with self._lock:
                db = self._conn()
                with db:
                    changed = db.execute(
                        "UPDATE runtime_tasks SET status=?,version=version+1,updated_at=? "
                        "WHERE id=? AND version=?",
                        (safe_status, now, trace.task_id, trace.expected_version),
                    )
                    if changed.rowcount != 1:
                        self._event(db, trace, "task.version_conflict", {
                            "expected_version": trace.expected_version,
                        })
                        return False
                    db.execute(
                        "UPDATE runtime_steps SET status=?,completed_at=?,error_code=? WHERE id=?",
                        (safe_status, now, str(error_code or "")[:120], trace.step_id),
                    )
                    self._event(db, trace, "task.finished",
                                {"status": safe_status, "error_code": str(error_code or "")[:120]})
                trace.expected_version += 1
                return True
        except Exception:
            return False

    def get_task(self, task_id: str) -> Optional[dict]:
        """Read-only helper cho test/admin tương lai; không trả raw content vì DB không lưu."""
        try:
            with self._lock:
                row = self._conn().execute(
                    "SELECT * FROM runtime_tasks WHERE id=?", (task_id,)
                ).fetchone()
                return dict(row) if row else None
        except Exception:
            return None

    def list_events(self, task_id: str) -> list[dict]:
        try:
            with self._lock:
                rows = self._conn().execute(
                    "SELECT event_type,payload_json,created_at FROM runtime_events "
                    "WHERE task_id=? ORDER BY seq", (task_id,)
                ).fetchall()
                return [{**dict(r), "payload": json.loads(r["payload_json"] or "{}")}
                        for r in rows]
        except Exception:
            return []

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None


_RUNTIME: ObserveRuntime | None = None


def get_runtime() -> ObserveRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = ObserveRuntime()
    return _RUNTIME
