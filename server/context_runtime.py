"""Trace substrate cho Adaptive Context Runtime Phase 0-6.

Substrate này chỉ làm ba việc:
- gắn task_id/step_id ổn định vào một lượt chat;
- ghi metadata đã redaction để đo payload, usage và quota reservation;
- lưu state tối thiểu trong runtime.db để các phase sau có chỗ mở rộng.

Module này CỐ Ý không lưu raw prompt, message, tool arguments/result hay secret. Registry và
Resolver và Context Compiler Phase 2-4 chạy shadow. Phase 5 chỉ được phép pin một task vào
Fast Path sau admission control; trace vẫn tuyệt đối không lưu nội dung người dùng.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import math
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import config


RUNTIME_VERSION = "adaptive-v5"
RESOLVER_POLICY_VERSION = "deterministic-shadow-v1"
COMPILER_POLICY_VERSION = "adaptive-compiler-shadow-v1"
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
    execution_path: str = "unassigned"
    canary_bucket: Optional[int] = None
    canary_policy_version: str = ""


@dataclass(frozen=True)
class QuotaAdmission:
    allowed: bool
    reservation_id: str
    reason: str
    requested_tokens: int
    used_tokens: int
    limit_tokens: int
    remaining_tokens: int


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
                    execution_path TEXT NOT NULL DEFAULT 'unassigned',
                    canary_bucket INTEGER,
                    canary_policy_version TEXT NOT NULL DEFAULT '',
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
                    created_at REAL NOT NULL,
                    actual_input_tokens INTEGER NOT NULL DEFAULT 0,
                    actual_output_tokens INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_quota_reservations_model
                    ON quota_reservations(provider, model, created_at);
                CREATE TABLE IF NOT EXISTS runtime_capability_leases (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    capability_revision TEXT NOT NULL,
                    schema_hash TEXT NOT NULL,
                    actor_hash TEXT NOT NULL,
                    allowed_effect TEXT NOT NULL,
                    resource_scope_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    invoked_at REAL,
                    FOREIGN KEY(task_id) REFERENCES runtime_tasks(id)
                );
                CREATE INDEX IF NOT EXISTS idx_runtime_leases_task
                    ON runtime_capability_leases(task_id,step_id,status);
                CREATE TABLE IF NOT EXISTS runtime_invocations (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    capability_revision TEXT NOT NULL,
                    args_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_evidence_id TEXT,
                    error_code TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES runtime_tasks(id),
                    FOREIGN KEY(lease_id) REFERENCES runtime_capability_leases(id)
                );
                CREATE INDEX IF NOT EXISTS idx_runtime_invocations_task
                    ON runtime_invocations(task_id,step_id,status);
                CREATE TABLE IF NOT EXISTS runtime_evidence (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_ref_hash TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    artifact_path TEXT NOT NULL,
                    excerpt_encrypted TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    trust TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    FOREIGN KEY(task_id) REFERENCES runtime_tasks(id)
                );
                CREATE INDEX IF NOT EXISTS idx_runtime_evidence_task
                    ON runtime_evidence(task_id,step_id,created_at);
                """
            )
            # Migrate an observe DB created by an earlier build without rewriting state.
            columns = {r[1] for r in db.execute("PRAGMA table_info(runtime_tasks)")}
            if "budget_json" not in columns:
                db.execute("ALTER TABLE runtime_tasks ADD COLUMN budget_json TEXT NOT NULL DEFAULT '{}'")
            if "deadline_at" not in columns:
                db.execute("ALTER TABLE runtime_tasks ADD COLUMN deadline_at REAL")
            if "execution_path" not in columns:
                db.execute("ALTER TABLE runtime_tasks ADD COLUMN execution_path TEXT NOT NULL DEFAULT 'unassigned'")
            if "canary_bucket" not in columns:
                db.execute("ALTER TABLE runtime_tasks ADD COLUMN canary_bucket INTEGER")
            if "canary_policy_version" not in columns:
                db.execute("ALTER TABLE runtime_tasks ADD COLUMN canary_policy_version TEXT NOT NULL DEFAULT ''")
            quota_columns = {r[1] for r in db.execute("PRAGMA table_info(quota_reservations)")}
            if "actual_input_tokens" not in quota_columns:
                db.execute("ALTER TABLE quota_reservations ADD COLUMN actual_input_tokens INTEGER NOT NULL DEFAULT 0")
            if "actual_output_tokens" not in quota_columns:
                db.execute("ALTER TABLE quota_reservations ADD COLUMN actual_output_tokens INTEGER NOT NULL DEFAULT 0")
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
                for table in ("quota_reservations", "runtime_invocations",
                              "runtime_capability_leases", "runtime_evidence",
                              "runtime_evidence_refs", "runtime_events", "runtime_steps"):
                    self._db.execute(f"DELETE FROM {table} WHERE task_id IN ({marks})", old)
                self._db.execute(f"DELETE FROM runtime_tasks WHERE id IN ({marks})", old)
                self._db.commit()
        except Exception:
            pass

    @staticmethod
    def _safe_payload(data: dict | None) -> str:
        """Allowlist scalar metadata. Không có đường nào ghi raw content vào event."""
        out = {}
        sensitive_keys = {
            "content", "prompt", "messages", "message", "user_message", "objective",
            "query", "response", "text", "body", "tools", "args", "result", "secret",
            "source_ref", "path", "api_key", "access_token", "refresh_token",
        }
        for key, value in (data or {}).items():
            if str(key).casefold() in sensitive_keys:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                out[str(key)[:80]] = value[:2000] if isinstance(value, str) else value
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
            "WHERE status IN ('OBSERVED','ADMITTED') AND expires_at<=?",
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
                        "model_profile_revision,budget_json,deadline_at,execution_path,"
                        "canary_bucket,canary_policy_version,created_at,updated_at"
                        ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (trace.task_id, trace.session_id, str(brain or ""), trace.channel,
                         "RUNNING", 1, RUNTIME_VERSION, RESOLVER_POLICY_VERSION,
                         COMPILER_POLICY_VERSION, trace.registry_revision,
                         trace.model_profile_revision,
                         json.dumps(budget, ensure_ascii=False, separators=(",", ":")),
                         deadline_at, trace.execution_path, trace.canary_bucket,
                         trace.canary_policy_version, now, now),
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

    def pin_execution_path(self, trace: Optional[TurnTrace], path: str,
                           bucket: Optional[int], policy_version: str,
                           reason: str = "") -> str:
        """Pin đường chạy đúng một lần cho task; đổi config giữa lượt không đổi task đang chạy."""
        if not trace:
            return "legacy"
        requested = path if path in {"fast", "readonly"} else "legacy"
        try:
            with self._lock:
                db = self._conn()
                with db:
                    row = db.execute(
                        "SELECT execution_path,canary_bucket,canary_policy_version "
                        "FROM runtime_tasks WHERE id=?", (trace.task_id,)
                    ).fetchone()
                    current = str(row["execution_path"] or "unassigned") if row else "unassigned"
                    if current == "unassigned":
                        db.execute(
                            "UPDATE runtime_tasks SET execution_path=?,canary_bucket=?,"
                            "canary_policy_version=?,updated_at=? WHERE id=? AND execution_path='unassigned'",
                            (requested, bucket, str(policy_version or "")[:120], time.time(), trace.task_id),
                        )
                        current = requested
                        self._event(db, trace, "canary.decision", {
                            "execution_path": current,
                            "bucket": bucket,
                            "policy_version": str(policy_version or "")[:120],
                            "reason": str(reason or "")[:120],
                        })
                        row = db.execute(
                            "SELECT execution_path,canary_bucket,canary_policy_version "
                            "FROM runtime_tasks WHERE id=?", (trace.task_id,)
                        ).fetchone()
                    trace.execution_path = current
                    if row:
                        trace.canary_bucket = row["canary_bucket"]
                        trace.canary_policy_version = str(
                            row["canary_policy_version"] or ""
                        )[:120]
                    else:
                        trace.canary_bucket = bucket
                        trace.canary_policy_version = str(policy_version or "")[:120]
                    return current
        except Exception:
            trace.execution_path = "legacy"
            return "legacy"

    def rebase_registry_revision(self, trace: Optional[TurnTrace], revision: str,
                                 reason: str = "source_changed") -> bool:
        """Re-pin có kiểm soát trước model/tool khi discovery thấy source revision mới."""
        if not trace or not revision or trace.execution_path != "unassigned":
            return False
        try:
            with self._lock:
                db = self._conn()
                with db:
                    invocations = db.execute(
                        "SELECT COUNT(*) FROM runtime_invocations WHERE task_id=?",
                        (trace.task_id,),
                    ).fetchone()[0]
                    if invocations:
                        return False
                    changed = db.execute(
                        "UPDATE runtime_tasks SET registry_revision=?,updated_at=? "
                        "WHERE id=? AND status='RUNNING' AND execution_path='unassigned'",
                        (str(revision)[:120], time.time(), trace.task_id),
                    )
                    if changed.rowcount != 1:
                        return False
                    old = trace.registry_revision
                    trace.registry_revision = str(revision)[:120]
                    self._event(db, trace, "registry.rebased", {
                        "old_revision": old, "new_revision": trace.registry_revision,
                        "reason": str(reason or "")[:120],
                    })
                    return True
        except Exception:
            return False

    def record_runtime_event(self, trace: Optional[TurnTrace], event_type: str,
                             data: dict | None = None) -> None:
        """Ghi event metadata allowlist cho runtime phase mới; raw content vẫn bị loại."""
        if not trace:
            return
        safe_type = re.sub(r"[^a-z0-9_.-]", "_", str(event_type or "runtime.event").lower())[:120]
        try:
            with self._lock:
                db = self._conn()
                with db:
                    self._event(db, trace, safe_type, data)
        except Exception:
            pass

    def admit_quota(self, trace: Optional[TurnTrace], provider: str, model: str,
                    input_tokens: int, output_tokens: int, rolling_tpm_limit: int,
                    window_seconds: int = 60) -> QuotaAdmission:
        """Admission atomically theo rolling-window local; fail closed khi limit không biết."""
        requested = max(0, int(input_tokens or 0)) + max(0, int(output_tokens or 0))
        limit = max(0, int(rolling_tpm_limit or 0))
        if not trace or limit <= 0 or requested <= 0:
            return QuotaAdmission(False, "", "quota_unknown", requested, 0, limit, 0)
        now = time.time()
        window = max(1, min(int(window_seconds or 60), 3600))
        try:
            with self._lock:
                db = self._conn()
                with db:
                    self._expire_reservations(db, now)
                    row = db.execute(
                        "SELECT COALESCE(SUM(CASE WHEN status IN ('CONSUMED','RECONCILED') THEN "
                        "actual_input_tokens+actual_output_tokens ELSE "
                        "input_reserved+output_reserved END),0) FROM quota_reservations "
                        "WHERE provider=? AND model=? AND created_at>=? "
                        "AND status IN ('OBSERVED','RECONCILED','ADMITTED','CONSUMED')",
                        (str(provider or "?"), str(model or "?"), now - window),
                    ).fetchone()
                    used = int(row[0] or 0)
                    remaining = max(0, limit - used)
                    if requested > remaining:
                        self._event(db, trace, "quota.rejected", {
                            "provider": provider or "?", "model": model or "?",
                            "requested_tokens": requested, "used_tokens": used,
                            "limit_tokens": limit, "remaining_tokens": remaining,
                            "reason": "rolling_tpm",
                        })
                        return QuotaAdmission(
                            False, "", "rolling_tpm", requested, used, limit, remaining
                        )
                    reservation_id = "qa_" + uuid.uuid4().hex
                    db.execute(
                        "INSERT INTO quota_reservations("
                        "id,task_id,step_id,provider,model,input_reserved,output_reserved,"
                        "status,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (reservation_id, trace.task_id, trace.step_id, provider or "?", model or "?",
                         max(0, int(input_tokens or 0)), max(0, int(output_tokens or 0)),
                         "ADMITTED", now + window, now),
                    )
                    db.execute(
                        "UPDATE runtime_steps SET provider=?,model=?,estimated_input_tokens="
                        "COALESCE(estimated_input_tokens,0)+? WHERE id=?",
                        (provider or "?", model or "?", max(0, int(input_tokens or 0)), trace.step_id),
                    )
                    self._event(db, trace, "quota.admitted", {
                        "provider": provider or "?", "model": model or "?",
                        "requested_tokens": requested, "used_tokens": used,
                        "limit_tokens": limit, "remaining_tokens": remaining - requested,
                    })
                    return QuotaAdmission(
                        True, reservation_id, "admitted", requested, used, limit,
                        remaining - requested,
                    )
        except Exception:
            return QuotaAdmission(False, "", "quota_store_error", requested, 0, limit, 0)

    def consume_quota(self, trace: Optional[TurnTrace], reservation_id: str,
                      input_tokens: int = 0, output_tokens: int = 0) -> None:
        if not trace or not reservation_id:
            return
        tin, tout = max(0, int(input_tokens or 0)), max(0, int(output_tokens or 0))
        try:
            with self._lock:
                db = self._conn()
                with db:
                    changed = db.execute(
                        "UPDATE quota_reservations SET status='CONSUMED',"
                        "actual_input_tokens=?,actual_output_tokens=? "
                        "WHERE id=? AND task_id=? AND status='ADMITTED'",
                        (tin, tout, str(reservation_id), trace.task_id),
                    )
                    if changed.rowcount != 1:
                        return
                    db.execute(
                        "UPDATE runtime_steps SET actual_input_tokens=COALESCE(actual_input_tokens,0)+?,"
                        "actual_output_tokens=COALESCE(actual_output_tokens,0)+? WHERE id=?",
                        (tin, tout, trace.step_id),
                    )
                    self._event(db, trace, "usage.canary", {
                        "input_tokens": tin, "output_tokens": tout,
                    })
        except Exception:
            pass

    def release_quota(self, trace: Optional[TurnTrace], reservation_id: str,
                      reason: str = "setup_failed") -> bool:
        """Nhả reservation trước model call; không dùng để hoàn token đã gửi."""
        if not trace or not reservation_id:
            return False
        try:
            with self._lock:
                db = self._conn()
                with db:
                    changed = db.execute(
                        "UPDATE quota_reservations SET status='RELEASED' "
                        "WHERE id=? AND task_id=? AND status='ADMITTED'",
                        (str(reservation_id), trace.task_id),
                    )
                    if changed.rowcount != 1:
                        return False
                    self._event(db, trace, "quota.released", {
                        "reservation_id": str(reservation_id)[:120],
                        "reason": str(reason or "")[:120],
                    })
                    return True
        except Exception:
            return False

    def create_capability_lease(self, trace: Optional[TurnTrace], capability_id: str,
                                capability_revision: str, schema_hash: str,
                                actor_hash: str, allowed_effect: str,
                                resource_scope: dict, ttl_seconds: int = 120) -> str:
        if not trace or allowed_effect not in {"none", "read"}:
            return ""
        lease_id = "cl_" + uuid.uuid4().hex
        now = time.time()
        scope = resource_scope if isinstance(resource_scope, dict) else {}
        try:
            with self._lock:
                db = self._conn()
                with db:
                    db.execute(
                        "INSERT INTO runtime_capability_leases("
                        "id,task_id,step_id,capability_id,capability_revision,schema_hash,"
                        "actor_hash,allowed_effect,resource_scope_json,status,expires_at,created_at"
                        ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (lease_id, trace.task_id, trace.step_id, capability_id,
                         capability_revision, schema_hash, actor_hash, allowed_effect,
                         json.dumps(scope, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")),
                         "ACTIVE", now + max(1, min(int(ttl_seconds or 120), 900)), now),
                    )
                    self._event(db, trace, "lease.issued", {
                        "lease_id": lease_id, "capability_id": capability_id,
                        "capability_revision": capability_revision,
                        "schema_hash": schema_hash, "allowed_effect": allowed_effect,
                    })
            return lease_id
        except Exception:
            return ""

    def get_capability_lease(self, lease_id: str) -> Optional[dict]:
        try:
            with self._lock:
                row = self._conn().execute(
                    "SELECT * FROM runtime_capability_leases WHERE id=?", (str(lease_id),)
                ).fetchone()
            if not row:
                return None
            out = dict(row)
            out["resource_scope"] = json.loads(out.pop("resource_scope_json") or "{}")
            return out
        except Exception:
            return None

    def revoke_capability_lease(self, trace: Optional[TurnTrace], lease_id: str,
                                reason: str = "cancelled") -> bool:
        if not trace or not lease_id:
            return False
        try:
            with self._lock:
                db = self._conn()
                with db:
                    changed = db.execute(
                        "UPDATE runtime_capability_leases SET status='REVOKED' "
                        "WHERE id=? AND task_id=? AND status='ACTIVE'",
                        (str(lease_id), trace.task_id),
                    )
                    if changed.rowcount != 1:
                        return False
                    self._event(db, trace, "lease.revoked", {
                        "lease_id": str(lease_id)[:120],
                        "reason": str(reason or "")[:120],
                    })
                    return True
        except Exception:
            return False

    def claim_read_invocation(self, trace: Optional[TurnTrace], lease_id: str,
                              capability_id: str, capability_revision: str,
                              schema_hash: str, actor_hash: str, args_hash: str) -> str:
        """Claim lease dùng một lần trước I/O; không lưu arguments, chỉ lưu hash."""
        if not trace:
            return ""
        now = time.time()
        invocation_id = "ri_" + uuid.uuid4().hex
        try:
            with self._lock:
                db = self._conn()
                with db:
                    changed = db.execute(
                        "UPDATE runtime_capability_leases SET status='INVOKING',invoked_at=? "
                        "WHERE id=? AND task_id=? AND step_id=? AND capability_id=? "
                        "AND capability_revision=? AND schema_hash=? AND actor_hash=? "
                        "AND allowed_effect IN ('none','read') AND status='ACTIVE' AND expires_at>?",
                        (now, lease_id, trace.task_id, trace.step_id, capability_id,
                         capability_revision, schema_hash, actor_hash, now),
                    )
                    if changed.rowcount != 1:
                        self._event(db, trace, "invocation.rejected", {
                            "lease_id": lease_id, "capability_id": capability_id,
                            "reason": "lease_mismatch_or_expired",
                        })
                        return ""
                    db.execute(
                        "INSERT INTO runtime_invocations("
                        "id,task_id,step_id,lease_id,capability_id,capability_revision,"
                        "args_hash,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (invocation_id, trace.task_id, trace.step_id, lease_id,
                         capability_id, capability_revision, args_hash, "RUNNING", now, now),
                    )
                    self._event(db, trace, "invocation.started", {
                        "invocation_id": invocation_id, "lease_id": lease_id,
                        "capability_id": capability_id,
                        "capability_revision": capability_revision,
                        "args_hash": args_hash,
                    })
            return invocation_id
        except Exception:
            return ""

    def finish_read_invocation(self, trace: Optional[TurnTrace], invocation_id: str,
                               lease_id: str, status: str,
                               evidence_id: str = "", error_code: str = "") -> bool:
        if not trace:
            return False
        allowed = {"SUCCEEDED", "FAILED_VALIDATION", "FAILED_FINAL", "TIMEOUT"}
        final_status = status if status in allowed else "FAILED_FINAL"
        lease_status = "CONSUMED" if final_status == "SUCCEEDED" else "FAILED"
        try:
            with self._lock:
                db = self._conn()
                with db:
                    changed = db.execute(
                        "UPDATE runtime_invocations SET status=?,result_evidence_id=?,"
                        "error_code=?,updated_at=? WHERE id=? AND task_id=? AND status='RUNNING'",
                        (final_status, str(evidence_id or "")[:120],
                         str(error_code or "")[:120], time.time(), invocation_id, trace.task_id),
                    )
                    if changed.rowcount != 1:
                        return False
                    db.execute(
                        "UPDATE runtime_capability_leases SET status=? WHERE id=? AND task_id=?",
                        (lease_status, lease_id, trace.task_id),
                    )
                    self._event(db, trace, "invocation.finished", {
                        "invocation_id": invocation_id, "lease_id": lease_id,
                        "status": final_status, "evidence_id": evidence_id or "",
                        "error_code": str(error_code or "")[:120],
                    })
            return True
        except Exception:
            return False

    def persist_evidence_metadata(self, trace: Optional[TurnTrace], evidence_id: str,
                                  source_type: str, source_ref: str, content_type: str,
                                  artifact_path: str, excerpt_encrypted: str,
                                  content_hash: str, trust: str,
                                  metadata: dict | None = None,
                                  expires_at: float | None = None) -> bool:
        if not trace or not evidence_id or not artifact_path or not excerpt_encrypted:
            return False
        safe_meta = {str(k)[:80]: v for k, v in (metadata or {}).items()
                     if isinstance(v, (str, int, float, bool)) or v is None}
        source_hash = hashlib.sha256(
            str(source_ref or "").encode("utf-8", errors="replace")
        ).hexdigest()
        try:
            with self._lock:
                db = self._conn()
                with db:
                    db.execute(
                        "INSERT INTO runtime_evidence("
                        "id,task_id,step_id,source_type,source_ref_hash,content_type,"
                        "artifact_path,excerpt_encrypted,content_hash,trust,metadata_json,"
                        "created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (evidence_id, trace.task_id, trace.step_id,
                         str(source_type or "unknown")[:80], source_hash,
                         str(content_type or "text/plain")[:120], artifact_path,
                         excerpt_encrypted, content_hash,
                         str(trust or "tool_result")[:40],
                         json.dumps(safe_meta, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")),
                         time.time(), expires_at),
                    )
                    self._event(db, trace, "evidence.created", {
                        "evidence_id": evidence_id,
                        "source_type": str(source_type or "unknown")[:80],
                        "content_type": str(content_type or "text/plain")[:120],
                        "content_hash": content_hash,
                        "trust": str(trust or "tool_result")[:40],
                    })
            return True
        except Exception:
            return False

    def get_evidence_metadata(self, evidence_id: str) -> Optional[dict]:
        try:
            with self._lock:
                row = self._conn().execute(
                    "SELECT * FROM runtime_evidence WHERE id=?", (str(evidence_id),)
                ).fetchone()
            if not row:
                return None
            out = dict(row)
            out["metadata"] = json.loads(out.pop("metadata_json") or "{}")
            return out
        except Exception:
            return None

    def evidence_retention_snapshot(self, now: float | None = None) -> dict:
        try:
            with self._lock:
                rows = self._conn().execute(
                    "SELECT id,artifact_path,expires_at FROM runtime_evidence"
                ).fetchall()
            ts = float(now or time.time())
            active, expired = set(), []
            for row in rows:
                if row["expires_at"] is not None and float(row["expires_at"]) <= ts:
                    expired.append({"id": row["id"], "artifact_path": row["artifact_path"]})
                else:
                    active.add(str(row["artifact_path"]))
            return {"active_paths": active, "expired": expired}
        except Exception:
            return {"active_paths": set(), "expired": []}

    def delete_evidence_metadata(self, evidence_ids: list[str]) -> int:
        ids = [str(x) for x in evidence_ids or [] if str(x)]
        if not ids:
            return 0
        try:
            with self._lock:
                db = self._conn()
                marks = ",".join("?" for _ in ids)
                with db:
                    changed = db.execute(
                        f"DELETE FROM runtime_evidence WHERE id IN ({marks})", ids
                    )
                return int(changed.rowcount or 0)
        except Exception:
            return 0

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
                        "INSERT INTO quota_reservations("
                        "id,task_id,step_id,provider,model,input_reserved,output_reserved,"
                        "status,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
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
                        "UPDATE quota_reservations SET status='RECONCILED',"
                        "actual_input_tokens=?,actual_output_tokens=? WHERE id=("
                        "SELECT id FROM quota_reservations WHERE task_id=? AND step_id=? "
                        "AND status='OBSERVED' ORDER BY created_at,id LIMIT 1)",
                        (tin, tout, trace.task_id, trace.step_id),
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
            "selection_reason": report.get("selection_reason") or "",
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

    def record_compiler_shadow(self, trace: Optional[TurnTrace], report: dict) -> None:
        if not trace:
            return
        excluded = report.get("excluded") or {}
        excluded_counts = {}
        for reason in excluded.values() if isinstance(excluded, dict) else []:
            excluded_counts[str(reason)] = excluded_counts.get(str(reason), 0) + 1
        data = {
            "status": report.get("status") or "unknown",
            "path": report.get("path") or "unknown",
            "policy_version": report.get("policy_version") or COMPILER_POLICY_VERSION,
            "core_contract_version": report.get("core_contract_version") or "",
            "tokenizer_revision": report.get("tokenizer_revision") or "",
            "tokenizer_method": report.get("tokenizer_method") or "",
            "renderer_revision": report.get("renderer_revision") or "",
            "tokenizer_confidence": report.get("tokenizer_confidence", 0),
            "capsule_hash": report.get("capsule_hash") or "",
            "estimated_input_tokens": report.get("estimated_input_tokens", 0),
            "system_tokens": report.get("system_tokens", 0),
            "user_tokens": report.get("user_tokens", 0),
            "tool_tokens": report.get("tool_tokens", 0),
            "max_input_tokens": report.get("max_input_tokens", 0),
            "reserved_output_tokens": report.get("reserved_output_tokens", 0),
            "budget_source": report.get("budget_source") or "",
            "hard_context_known": bool(report.get("hard_context_known", False)),
            "budget_utilization": report.get("budget_utilization", 0),
            "candidate_count": report.get("candidate_count", 0),
            "selected_count": report.get("selected_count", 0),
            "excluded_count": report.get("excluded_count", 0),
            "selected_ids": ",".join(str(x) for x in (report.get("selected_ids") or [])[:20]),
            "excluded_counts": ",".join(f"{k}:{excluded_counts[k]}" for k in sorted(excluded_counts)),
            "source_count": report.get("source_count", 0),
            "source_map_hash": report.get("source_map_hash") or "",
            "preflight_decision": report.get("preflight_decision") or "",
            "preflight_reasons": ",".join(str(x) for x in (report.get("preflight_reasons") or [])),
            "quota_known": bool(report.get("quota_known", False)),
            "observe_only": True,
            "legacy_memory_owner": bool(report.get("legacy_memory_owner", True)),
            "legacy_history_owner": bool(report.get("legacy_history_owner", True)),
            "calibration_samples": report.get("calibration_samples", 0),
            "median_abs_pct_error": report.get("median_abs_pct_error", 0),
            "latency_ms": report.get("latency_ms", 0),
        }
        try:
            with self._lock:
                db = self._conn()
                with db:
                    self._event(db, trace, "compiler.shadow", data)
        except Exception:
            pass

    def record_quality_shadow(self, trace: Optional[TurnTrace], report: dict) -> None:
        if not trace:
            return
        data = {
            "status": report.get("status") or "unknown",
            "reason_codes": ",".join(str(x) for x in (report.get("reason_codes") or [])),
            "confidence": report.get("confidence", 0),
            "response_chars": report.get("response_chars", 0),
        }
        try:
            with self._lock:
                db = self._conn()
                with db:
                    self._event(db, trace, "quality.shadow", data)
        except Exception:
            pass

    def token_estimate_stats(self, provider: str, model: str, limit: int = 200) -> dict:
        """Sai số estimator legacy so với usage thật; chỉ aggregate, không đọc nội dung."""
        try:
            with self._lock:
                rows = self._conn().execute(
                    "SELECT estimated_input_tokens,actual_input_tokens FROM runtime_steps "
                    "WHERE provider=? AND model=? AND estimated_input_tokens>0 "
                    "AND actual_input_tokens>0 ORDER BY started_at DESC LIMIT ?",
                    (str(provider or "?"), str(model or "?"), max(1, min(int(limit), 1000))),
                ).fetchall()
            errors = sorted(abs(int(r[0]) - int(r[1])) / max(1, int(r[1])) for r in rows)
            if not errors:
                return {"samples": 0, "median_abs_pct_error": 0.0, "p95_abs_pct_error": 0.0}
            mid = errors[len(errors) // 2]
            p95 = errors[min(len(errors) - 1, int(len(errors) * 0.95))]
            return {"samples": len(errors), "median_abs_pct_error": round(mid, 6),
                    "p95_abs_pct_error": round(p95, 6)}
        except Exception:
            return {"samples": 0, "median_abs_pct_error": 0.0, "p95_abs_pct_error": 0.0}

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
