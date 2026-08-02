"""Encrypted Evidence Store cơ bản cho Adaptive Runtime Phase 6."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import config
import context_runtime
import secrets_store


EVIDENCE_STORE_VERSION = "evidence-store-v1"
_SECRET_KEYS = {
    "password", "passwd", "secret", "token", "access_token", "refresh_token",
    "api_key", "apikey", "authorization", "cookie", "set-cookie", "client_secret",
    "private_key", "session_token", "id_token", "auth", "credentials",
}
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")
_KEY_RE = re.compile(
    r"\b(?:(?:sk|gsk|rk)[_-]|xox[baprs]-|gh[pousr]_|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|"
    r"AIza[0-9A-Za-z_-]{30,}|ya29\.[0-9A-Za-z_-]{20,})[A-Za-z0-9_-]*\b"
)
# JWT ba đoạn base64url; header luôn bắt đầu bằng eyJ.
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
# Secret nhét trong query string: ?token=..., &api_key=..., ?key=...
_URL_SECRET_RE = re.compile(
    r"(?i)([?&](?:token|access_token|api_?key|key|secret|signature|sig|auth)=)[^&\s\"']{8,}"
)


def _secret_key_name(name: str) -> bool:
    # Khớp cả biến thể có tiền tố/hậu tố kiểu "x-api-key", "openai_api_key".
    folded = name.casefold().replace("-", "_")
    if folded in _SECRET_KEYS or folded.replace("_", "") in {"apikey", "setcookie"}:
        return True
    return any(folded.endswith("_" + k) or folded.startswith(k + "_")
               for k in ("password", "secret", "token", "api_key", "apikey"))


@dataclass(frozen=True)
class Evidence:
    id: str
    ref: str
    task_id: str
    step_id: str
    source_type: str
    content_type: str
    artifact_path: str
    inline_excerpt: str
    content_hash: str
    trust: str
    created_at: float
    expires_at: float | None
    metadata: dict


def _redact_text(value: str) -> str:
    text = _BEARER_RE.sub("Bearer [REDACTED]", str(value or ""))
    text = _KEY_RE.sub("[REDACTED_KEY]", text)
    text = _JWT_RE.sub("[REDACTED_JWT]", text)
    return _URL_SECRET_RE.sub(r"\1[REDACTED]", text)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            name = str(key)
            out[name] = "[REDACTED]" if _secret_key_name(name) else redact(item)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(x) for x in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _serialize(value: Any) -> tuple[str, str]:
    safe = redact(value)
    if isinstance(safe, (dict, list)):
        return (json.dumps(safe, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), default=str), "application/json")
    return _redact_text(str(safe)), "text/plain"


def _excerpt(text: str, max_chars: int) -> str:
    limit = max(200, int(max_chars or 4000))
    if len(text) <= limit:
        return text
    marker = f"\n… [evidence excerpt omitted {len(text) - limit} chars] …\n"
    body = max(2, limit - len(marker))
    head = int(body * 0.7)
    tail = body - head
    omitted = len(text) - head - tail
    marker = f"\n… [evidence excerpt omitted {omitted} chars] …\n"
    # Số chữ số của omitted có thể đổi độ dài marker, nên co body lần cuối.
    body = max(2, limit - len(marker))
    head = int(body * 0.7)
    tail = body - head
    return text[:head] + marker + text[-tail:]


class EvidenceStore:
    def __init__(self, runtime: context_runtime.ObserveRuntime,
                 state_dir: str | Path | None = None,
                 encryptor: Callable[[str], str] | None = None,
                 decryptor: Callable[[str], str] | None = None,
                 ready_check: Callable[[], bool] | None = None):
        self.runtime = runtime
        self.state_dir = Path(state_dir or config.STATE_DIR)
        self.root = self.state_dir / "evidence"
        self.encryptor = encryptor or secrets_store.encrypt_required
        self.decryptor = decryptor or secrets_store.decrypt
        self.ready_check = ready_check or secrets_store.encryption_available
        self._cleaned = False

    def ready(self) -> bool:
        try:
            if not self.ready_check():
                return False
            self.root.mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            return False

    @staticmethod
    def _safe_segment(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_.-]", "_", str(value or "unknown"))[:120]

    def put(self, trace: context_runtime.TurnTrace, source_type: str, source_ref: str,
            result: Any, trust: str = "tool_result", metadata: dict | None = None,
            excerpt_chars: int = 4000, max_artifact_bytes: int = 5_000_000,
            retention_seconds: int = 14 * 86400) -> Evidence:
        if not trace or not self.ready():
            raise RuntimeError("evidence_encryption_unavailable")
        text, content_type = _serialize(result)
        raw_size = len(text.encode("utf-8", errors="replace"))
        if raw_size > max(1024, int(max_artifact_bytes or 5_000_000)):
            raise ValueError("evidence_artifact_too_large")
        evidence_id = "ev_" + uuid.uuid4().hex
        created = time.time()
        expires = created + max(60, int(retention_seconds or 14 * 86400))
        content_hash = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        excerpt = _excerpt(text, excerpt_chars)
        encrypted_artifact = self.encryptor(text)
        encrypted_excerpt = self.encryptor(excerpt)
        task_dir = self.root / self._safe_segment(trace.task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        final_path = task_dir / f"{self._safe_segment(evidence_id)}.enc"
        temp_path = task_dir / f".{self._safe_segment(evidence_id)}.{uuid.uuid4().hex}.tmp"
        temp_path.write_text(encrypted_artifact, encoding="utf-8")
        try:
            os.chmod(temp_path, 0o600)
        except OSError:
            pass
        os.replace(temp_path, final_path)
        relative_path = final_path.relative_to(self.state_dir).as_posix()
        saved = self.runtime.persist_evidence_metadata(
            trace, evidence_id, source_type, source_ref, content_type,
            relative_path, encrypted_excerpt, content_hash, trust,
            metadata={**(metadata or {}), "store_version": EVIDENCE_STORE_VERSION,
                      "artifact_bytes": raw_size},
            expires_at=expires,
        )
        if not saved:
            try:
                final_path.unlink()
            except OSError:
                pass
            raise RuntimeError("evidence_metadata_persist_failed")
        ref = f"evidence://task/{trace.task_id}/step/{trace.step_id}/{evidence_id}"
        return Evidence(
            evidence_id, ref, trace.task_id, trace.step_id, source_type,
            content_type, relative_path, excerpt, content_hash, trust,
            created, expires, dict(metadata or {}),
        )

    def get(self, evidence_id: str) -> Evidence | None:
        meta = self.runtime.get_evidence_metadata(evidence_id)
        if not meta:
            return None
        try:
            excerpt = self.decryptor(meta["excerpt_encrypted"])
            ref = (f"evidence://task/{meta['task_id']}/step/{meta['step_id']}/"
                   f"{meta['id']}")
            return Evidence(
                meta["id"], ref, meta["task_id"], meta["step_id"],
                meta["source_type"], meta["content_type"], meta["artifact_path"],
                excerpt, meta["content_hash"], meta["trust"], meta["created_at"],
                meta["expires_at"], meta.get("metadata") or {},
            )
        except Exception:
            return None

    def get_valid(self, evidence_id: str, now: float | None = None) -> Evidence | None:
        """Evidence chỉ reusable khi metadata, TTL, artifact và content hash đều còn hợp lệ."""
        evidence = self.get(evidence_id)
        if not evidence:
            return None
        if evidence.expires_at is not None and evidence.expires_at <= float(now or time.time()):
            return None
        try:
            content = self.read_artifact(evidence_id)
            digest = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
            return evidence if digest == evidence.content_hash else None
        except Exception:
            return None

    def read_artifact(self, evidence_id: str) -> str:
        meta = self.runtime.get_evidence_metadata(evidence_id)
        if not meta:
            raise FileNotFoundError("evidence_not_found")
        path = (self.state_dir / meta["artifact_path"]).resolve()
        root = self.root.resolve()
        if path != root and root not in path.parents:
            raise ValueError("evidence_path_outside_store")
        return self.decryptor(path.read_text(encoding="utf-8"))

    def cleanup(self, orphan_grace_seconds: int = 3600) -> dict:
        """Xoá evidence hết hạn và orphan cũ; không đụng file vừa tạo chưa kịp ghi DB."""
        if not self.root.exists():
            return {"expired": 0, "orphans": 0}
        snapshot = self.runtime.evidence_retention_snapshot()
        expired_ids = []
        for item in snapshot.get("expired") or []:
            path = (self.state_dir / item["artifact_path"]).resolve()
            if self.root.resolve() in path.parents:
                try:
                    path.unlink()
                except OSError:
                    pass
            expired_ids.append(item["id"])
        self.runtime.delete_evidence_metadata(expired_ids)
        active = set(snapshot.get("active_paths") or set())
        orphans = 0
        cutoff = time.time() - max(60, int(orphan_grace_seconds or 3600))
        for path in self.root.glob("**/*.enc"):
            relative = path.relative_to(self.state_dir).as_posix()
            try:
                if relative not in active and path.stat().st_mtime < cutoff:
                    path.unlink()
                    orphans += 1
            except OSError:
                continue
        return {"expired": len(expired_ids), "orphans": orphans}
