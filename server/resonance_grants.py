"""Luật quyền thuần của Resonance A4 (thiết kế docs/superpowers/specs/2026-10-10-resonance-a4-handoff-grants-design.md).

Không đọc kho, không gọi model. Kho (`resonance_store`) và hợp đồng nộp (`resonance`) gọi các hàm ở đây trong giao dịch
của chúng:
- `path_key`: khoá đường chuẩn hoá của MỘT đích sản phẩm (mục 4.3 bước 2, D15). Từ chối đoạn `.` hay `..` trước khi
  resolve; không mở alias. Khoá là đường tương đối POSIX, chữ thường trên Windows.
- `narrow`: quyền con chỉ là PHẦN GIAO của quyền cha và cái con xin (mục 5.4). Xin trường lạ hay thiếu: phần giao rỗng.
- `allows`: một quyền có cho thao tác trên đúng đích không.
- `fingerprint`: dấu vân tay của MỘT lời nộp (mục 4.3 bước 5).
- `ENGINE_CAPS`: khả năng thật của từng engine do host khai (mục 6.1).

A4 KHÔNG cấp quyền từ lời chat (D1): không có hàm nào ở đây đọc lời người dùng.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional

POLICY_VERSION = "grants.v1"
ACTIONS = ("read_deliverable", "submit", "publish")
# Thao tác của quyền gốc A4. `communicate` không có trong A4 (D8): không đường nào trong hợp đồng giao việc cho trợ lý khác.
ROOT_ACTIONS = ("read_deliverable", "submit", "publish")
SOURCES = ("owner_approved", "legacy_frozen")


def path_key(brain_root: str, rel: Any) -> Optional[str]:
    """Khoá đường của một đích sản phẩm, hay None khi đường không được nhận.

    Từ chối trước khi resolve: rỗng, đường tuyệt đối, bắt đầu bằng gạch chéo, ký tự điều khiển, đoạn `.` hay `..`
    (kể cả `a/../a/x.md` mà `_brain_file` nhận vì nó resolve vẫn trong brain). Rồi qua `_brain_file` (resolve thật,
    chặn symlink trỏ ra ngoài), đuôi `.md`/`.txt`, thư mục cấm. Khoá là đường tương đối POSIX của file đã resolve,
    chữ thường trên Windows."""
    import resonance as R
    raw = str(rel if rel is not None else "").strip()
    if not raw or not brain_root or any(ord(ch) < 32 for ch in raw):
        return None
    if raw.startswith(("/", "\\")) or Path(raw).is_absolute() or (len(raw) > 1 and raw[1] == ":"):
        return None
    parts = raw.replace("\\", "/").split("/")
    if any(p in ("", ".", "..") for p in parts):
        return None
    f = R._brain_file(brain_root, raw)
    if f is None or f.suffix.lower() not in R.PUBLISH_SUFFIXES or not R._publish_allowed(brain_root, f):
        return None
    try:
        key = f.relative_to(Path(brain_root).resolve()).as_posix()
    except Exception:  # noqa: BLE001
        return None
    return key.lower() if os.name == "nt" else key


def deliverable_raw(criteria) -> str:
    """Đường sản phẩm THÔ của revision (đường `artifact_contract` đầu tiên), chưa chuẩn hoá. Có đường thô mà không có
    khoá đường nghĩa là đích không được nhận: mục tiêu vẫn CẦN phạm vi và bị chặn, không phải "không cần phạm vi"."""
    for c in criteria or ():
        if isinstance(c, dict) and c.get("evaluator") == "artifact_contract" and (c.get("params") or {}).get("path"):
            return str(c["params"]["path"])
    return ""


def deliverable_key(brain_root: str, criteria) -> str:
    """Khoá đường của sản phẩm DUY NHẤT một revision cần: đường `artifact_contract` đầu tiên (`_deliverable_rel`).
    Rỗng khi revision không có đường hay đường không được nhận."""
    for c in criteria or ():
        if isinstance(c, dict) and c.get("evaluator") == "artifact_contract" and (c.get("params") or {}).get("path"):
            return path_key(brain_root, c["params"]["path"]) or ""
    return ""


def _set(v) -> list:
    if not isinstance(v, (list, tuple)):
        return []
    return sorted({str(x) for x in v if isinstance(x, str) and x})


def narrow(parent: dict, request: dict) -> tuple:
    """Quyền con = phần giao của cha và cái con xin. Trả (grant dict, "") hay (None, lý do).

    `goal_id` và `brain_id` phải trùng. Thao tác lạ hay trường không phải danh sách: phần giao rỗng ở trường đó.
    `recipients` (communicate) chỉ có khi cha có; A4 không cấp nên luôn rỗng."""
    if not isinstance(parent, dict) or not isinstance(request, dict):
        return None, "invalid"
    if str(parent.get("goal_id") or "") != str(request.get("goal_id") or "") or \
            str(parent.get("brain_id") or "") != str(request.get("brain_id") or ""):
        return None, "scope_mismatch"
    want_actions = request.get("actions")
    acts = [a for a in _set(want_actions) if a in ACTIONS and a in _set(parent.get("actions"))]
    if isinstance(want_actions, (list, tuple)) and any(a not in ACTIONS for a in _set(want_actions)):
        acts = []
    out = {
        "goal_id": str(parent.get("goal_id") or ""), "brain_id": str(parent.get("brain_id") or ""),
        "actions": acts,
        "write_paths": [x for x in _set(request.get("write_paths")) if x in _set(parent.get("write_paths"))],
        "read_paths": [x for x in _set(request.get("read_paths")) if x in _set(parent.get("read_paths"))],
        "recipients": [x for x in _set(request.get("recipients")) if x in _set(parent.get("recipients"))],
    }
    return out, ""


def allows(grant: Optional[dict], action: str, key: str) -> bool:
    """Quyền `grant` có cho `action` trên đích `key` (khoá đường) không. Thiếu gì cũng là không."""
    if not grant or action not in ACTIONS or not key:
        return False
    if action not in _set(grant.get("actions")):
        return False
    paths = _set(grant.get("read_paths") if action == "read_deliverable" else grant.get("write_paths"))
    return key in paths


def fingerprint(binding_id: str, key: str, sha256: str, source: str) -> str:
    """Dấu vân tay toàn thao tác của một lời nộp: liên kết, đích, nội dung, nguồn."""
    return hashlib.sha256(json.dumps([str(binding_id), str(key), str(sha256), str(source)],
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


# Khả năng thật của từng engine (mục 6.1). `turn_key`: mang được khoá lượt tới hub; `submit_tool`: nộp qua
# `javis_submit_deliverable`; `observed_write`: biên nhận Write có id (chỉ Claude Code). Việc nền giữ nguyên danh sách
# của A1 tới A3 (D5). Grok và Antigravity không truyền khoá lượt nên không nhận bàn giao chat (D4).
ENGINE_CAPS = {
    "anthropic-cli": {"turn_key": True, "submit_tool": True, "observed_write": True},
    "openai-oauth": {"turn_key": True, "submit_tool": True, "observed_write": False},
    "grok-cli": {"turn_key": False, "submit_tool": False, "observed_write": False},
    "antigravity-cli": {"turn_key": False, "submit_tool": False, "observed_write": False},
}
API_PROVIDERS = ("openrouter", "anthropic-api", "openai", "gemini", "groq", "deepseek", "ollama", "ollama-local",
                 "openai-compat")


def engine_caps(provider: str) -> dict:
    p = str(provider or "").strip()
    if p in ENGINE_CAPS:
        return dict(ENGINE_CAPS[p])
    api = p in API_PROVIDERS
    return {"turn_key": api, "submit_tool": api, "observed_write": False}
