"""Javis Core: the built-in system assistant pinned in every brain (0.185.0).

One definition for the whole platform, `system/agents/javis-core.md`, shipped with the app and read
from there. It is never copied into a brain, so a release updates every brain at once, and nothing a
person keeps in a brain (memory, lessons, chats) is touched by that update.

Javis Core is not a persona agent. A chat with it is a normal Javis turn (CLAUDE.md, the brain's
MEMORY.md, every tool) plus one short block with its role (`prompt_block`). Its sessions live on the
channel `agent:javis-core` so the Partners page, the inbox and the chat history treat them like an
assistant's chats, while `workflow_chat.persona_cua_phien` reports no persona for that channel.

Each brain has one DEFAULT Javis Core chat, the place reports without a target chat land in. The
pointer to it is kept in `STATE_DIR/javis_core.json` ({brain_key: session_id}). When that chat is
deleted or archived, the next call makes a new empty one: deleted content is not brought back, and a
new report never lands in a chat the person put away.

Javis Core has no account of its own and grants no rights. Its turns run with the rights of the turn
that called it, like any other chat.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import fastyaml

SLUG = "javis-core"
CHANNEL = "agent:" + SLUG
NAME = "Javis Core"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFINITION_PATH = PROJECT_ROOT / "system" / "agents" / f"{SLUG}.md"
BLOCK_TITLE = "JAVIS CORE"

_lock = threading.RLock()
_def_cache: Dict[str, Any] = {"mtime": None, "value": None}


def is_core_slug(slug: Any) -> bool:
    return str(slug or "").strip().lower() == SLUG


def is_core_channel(channel: Any) -> bool:
    return str(channel or "") == CHANNEL


def definition() -> Dict[str, str]:
    """The platform definition: {name, role, role_en, body}. Cached until the file changes."""
    try:
        mtime = DEFINITION_PATH.stat().st_mtime
    except OSError:
        mtime = None
    with _lock:
        if _def_cache["value"] is not None and _def_cache["mtime"] == mtime:
            return dict(_def_cache["value"])
        meta: Dict[str, Any] = {}
        body = ""
        if mtime is not None:
            try:
                text = DEFINITION_PATH.read_text(encoding="utf-8")
                parts = fastyaml.split_frontmatter(text)
                if parts:
                    meta = fastyaml.safe_load(parts[0]) or {}
                    body = parts[1]
                else:
                    body = text
                if not isinstance(meta, dict):
                    meta = {}
            except Exception:  # noqa: BLE001 - a broken file must not break every chat
                meta, body = {}, ""
        value = {
            "name": NAME,   # fixed display name, whatever the file says
            "role": str(meta.get("role") or ""),
            "role_en": str(meta.get("role_en") or meta.get("role") or ""),
            "body": str(body or "").strip(),
        }
        _def_cache.update(mtime=mtime, value=value)
        return dict(value)


def prompt_block(root: Any = None) -> str:
    """The role block added to a Javis Core turn. Empty when the definition file is missing. With `root` (the brain the
    turn runs in) it ends with the name and style the person gave Javis Core there (owner, 04/11/2026)."""
    body = definition()["body"]
    if not body:
        return ""
    return f"\n\n# === {BLOCK_TITLE} ===\n{body}" + (identity_block(root) if root else "")


def list_entry(last_chat_at: float = 0.0, root: Any = None) -> Dict[str, Any]:
    """The row GET /agents puts first. Same shape as a brain agent, plus the system flags. The caller picks the role
    text for the screen language (`localefmt.chu(role, role_en)`). `name` is the one the person gave it in the brain at
    `root` (owner, 04/11/2026), `system_name` always "Javis Core"."""
    d = definition()
    me = identity(root) if root else {"name": "", "style": ""}
    return {
        "slug": SLUG, "name": me["name"] or NAME, "system_name": NAME, "custom_name": me["name"], "style": me["style"],
        "role": d["role"], "skills": [], "model": "", "model_provider": "",
        "tags": [], "tag_keys": [], "group": "", "pinned": True,
        "avatar": {},
        "system": True, "protected": True,
        "last_chat_at": float(last_chat_at or 0),
    }


# ── the default chat per brain ────────────────────────────────────────────────

def _map_path() -> Path:
    import config as cfgmod
    return Path(cfgmod.STATE_DIR) / "javis_core.json"


def _read_map() -> Dict[str, str]:
    try:
        data = json.loads(_map_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in (data or {}).items() if isinstance(v, str) and v}


def _write_map(data: Dict[str, str]) -> None:
    path = _map_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _usable(row: Optional[dict], brain_key: str, same_brain: Callable[[str, str], bool]) -> bool:
    return bool(row) and is_core_channel(row.get("channel")) and not row.get("archived") \
        and same_brain(str(row.get("brain") or ""), brain_key)


def default_session(store: Any, brain_key: str, *, title: str = NAME,
                    same_brain: Optional[Callable[[str, str], bool]] = None) -> str:
    """The id of this brain's default Javis Core chat, made when missing. Safe to call concurrently:
    the check and the create run under one lock, so two callers never make two chats."""
    brain_key = str(brain_key or "")
    same = same_brain or (lambda a, b: a == b)
    with _lock:
        data = _read_map()
        sid = data.get(brain_key)
        if sid and _usable(store.get_session(sid), brain_key, same):
            return sid
        sid = store.create_session(brain=brain_key, title=title, channel=CHANNEL)
        data[brain_key] = sid
        try:
            _write_map(data)
        except OSError:
            pass   # the chat exists; the next call makes another rather than failing a report
        return sid


def current_default(brain_key: str) -> str:
    """The pointer as stored, without checking or creating (for tests and diagnostics)."""
    return _read_map().get(str(brain_key or ""), "")


# ── the name and style the owner gives Javis Core in one brain (owner, 04/11/2026) ─────────────────────────────────────────
#
# Owner, 04/11/2026: people want to make Javis Core their own. On the first chat it asks what to call it, keeps the
# style the person likes, and the name shows on the Partners page. Kept per brain in `<brain>/Javis/core.json`, next to
# the brain's other Javis files, so it moves with the brain and every brain (often another person) has its own.
# The slug, the channel and the platform definition never change: only what Javis Core is called and how it talks.

IDENTITY_REL = Path("Javis") / "core.json"
_LONG_DASHES = (chr(0x2014), chr(0x2013))   # the owner bans both, everywhere
NAME_MAX = 40
STYLE_MAX = 300


def _identity_path(root: Any) -> Optional[Path]:
    return Path(str(root)) / IDENTITY_REL if str(root or "").strip() else None


def clean_name(raw: Any) -> str:
    """One line, no control characters or long dashes, at most NAME_MAX characters. "" means no own name."""
    s = "".join(" " if (ord(c) < 32 or c in _LONG_DASHES) else c for c in str(raw or ""))
    s = " ".join(s.split())
    return s[:NAME_MAX].strip()


def clean_style(raw: Any) -> str:
    s = "".join(" " if (ord(c) < 32 or c in _LONG_DASHES) else c for c in str(raw or ""))
    return " ".join(s.split())[:STYLE_MAX].strip()


def identity(root: Any) -> Dict[str, Any]:
    """{'name', 'style', 'asked'} of Javis Core in the brain at `root`. Empty name = still called Javis Core."""
    out: Dict[str, Any] = {"name": "", "style": "", "asked": False}
    path = _identity_path(root)
    if path is None:
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    if isinstance(data, dict):
        out["name"] = clean_name(data.get("name"))
        out["style"] = clean_style(data.get("style"))
        out["asked"] = bool(data.get("asked")) or bool(out["name"])
    return out


def set_identity(root: Any, *, name: Any = None, style: Any = None, asked: Optional[bool] = None) -> Dict[str, Any]:
    """Change only the fields given. A name given (even "") counts as asked: the person has answered."""
    path = _identity_path(root)
    if path is None:
        raise ValueError("no brain")
    with _lock:
        cur = identity(root)
        if name is not None:
            cur["name"] = clean_name(name)
            cur["asked"] = True
        if style is not None:
            cur["style"] = clean_style(style)
        if asked is not None:
            cur["asked"] = bool(asked) or bool(cur["name"])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)
        return dict(cur)


def display_name(root: Any) -> str:
    return identity(root)["name"] or NAME


def identity_block(root: Any) -> str:
    """The lines about the name and style added under the role block, for the brain at `root`."""
    me = identity(root)
    lines = []
    if me["name"]:
        lines.append(f"Tên của bạn trong brain này: **{me['name']}** (người dùng đặt). Tự xưng bằng tên này; "
                     "\"Javis Core\" chỉ còn là tên vai trò hệ thống.")
    elif not me["asked"]:
        lines.append("Bạn CHƯA có tên riêng. Trong câu trả lời đầu tiên, làm xong việc người dùng hỏi (nếu có) rồi "
                     "hỏi thêm MỘT câu ngắn, thân thiện: họ muốn gọi bạn là gì, kèm 2-3 tên gợi ý hợp với họ. Gọi "
                     "`javis_core_name` op=asked ngay lượt đó. Họ chọn tên thì lưu bằng op=set name=...; họ bỏ qua "
                     "thì giữ tên Javis Core, không hỏi lại.")
    else:
        lines.append("Bạn chưa có tên riêng. Người dùng đặt tên lúc nào thì lưu bằng `javis_core_name` op=set.")
    if me["style"]:
        lines.append(f"Phong cách đã thống nhất với người dùng: {me['style']}")
    return "\n\n" + "\n".join("- " + x for x in lines)
