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
    """The role block added to a Javis Core turn. With `root` (the brain the turn runs in) the instructions, name and
    skills come from that brain's Javis Core file (owner, 05/11/2026), else from the platform definition. Empty when
    there are no instructions at all."""
    if not root:
        body = definition()["body"]
        return f"\n\n# === {BLOCK_TITLE} ===\n{body}" if body else ""
    meta, body = read_core(root)
    if not body:
        return ""
    sk = [str(x) for x in (meta.get("skills") or []) if str(x).strip()]
    extra = f"\n\nSkill bạn được giao dùng trước: {', '.join(sk)}." if sk else ""
    return f"\n\n# === {BLOCK_TITLE} ===\n{body}{extra}" + identity_block(root)


def list_entry(last_chat_at: float = 0.0, root: Any = None) -> Dict[str, Any]:
    """The row GET /agents puts first. Same shape as a brain agent, plus the system flags. With `root` the name, role,
    skills and avatar come from that brain's Javis Core file. The caller picks the role text for the screen language
    (`role_text`). `system_name` is always "Javis Core"."""
    d = definition()
    meta = read_core(root)[0] if root else {}
    me = identity(root) if root else {"name": "", "style": ""}
    return {
        "slug": SLUG, "name": me["name"] or NAME, "system_name": NAME, "custom_name": me["name"], "style": me["style"],
        "role": str(meta.get("role") or d["role"]), "skills": list(meta.get("skills") or []), "model": "",
        "model_provider": "", "tags": [], "tag_keys": [], "group": "", "pinned": True,
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


# ── Javis Core as a brain agent file (owner, 05/11/2026) ──────────────────────────────────────────────────────────
#
# Owner, 05/11/2026: "keep Javis Core exactly like the other agents; it is only the system one you cannot remove, it
# starts with the system prompt I wrote, and Auto is on and cannot be turned off. Picture, name, skills and documents
# change like any agent." So each brain gets a real `agents/javis-core.md`, seeded from the platform definition and
# edited with the same agent editor. Its turns stay full Javis turns (CLAUDE.md, memory, every tool); only the role
# block below them comes from this file.
#
# While the body is still the seeded one (`seed_sha` matches), an app update of the definition reaches it. Once the
# owner edits the instructions, the file is theirs and updates leave it alone.
# The name lives in the file (`name`). The agreed style and whether the name was asked live in `Javis/core.json`.

IDENTITY_REL = Path("Javis") / "core.json"
_LONG_DASHES = (chr(0x2014), chr(0x2013))   # the owner bans both, everywhere
NAME_MAX = 40
STYLE_MAX = 300


# The brain's agents folder. The server points this at its own `_agents_dir` (an older brain may still keep its agents
# in `Javis/agents`, and creating `agents/` next to it would hide them).
AGENTS_DIR: Callable[[Any], Path] = lambda root: Path(str(root)) / "agents"


def core_path(root: Any) -> Optional[Path]:
    return Path(AGENTS_DIR(root)) / f"{SLUG}.md" if str(root or "").strip() else None


def _sha(text: Any) -> str:
    import hashlib
    return hashlib.sha256(str(text or "").strip().encode("utf-8")).hexdigest()[:16]


def _read_file(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}, ""
    parts = fastyaml.split_frontmatter(text)
    if not parts:
        return {}, text.strip()
    try:
        meta = fastyaml.safe_load(parts[0]) or {}
    except Exception:  # noqa: BLE001
        meta = {}
    return (meta if isinstance(meta, dict) else {}), parts[1].strip()


def _write_file(path: Path, meta: Dict[str, Any], body: str) -> None:
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")
    os.replace(tmp, path)


def _legacy_name(root: Any) -> str:
    """A name saved by 0.470.0 in `Javis/core.json`, moved into the file once."""
    path = _identity_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path else {}
    except (OSError, ValueError):
        return ""
    return clean_name((data or {}).get("name")) if isinstance(data, dict) else ""


def ensure_file(root: Any) -> Optional[Path]:
    """The brain's `agents/javis-core.md`, made from the platform definition when missing. A body still equal to the
    seeded one follows an updated definition. `system: true` is always set. None without a brain."""
    path = core_path(root)
    if path is None:
        return None
    with _lock:
        d = definition()
        if path.is_file():
            meta, body = _read_file(path)
            changed = False
            seed = str(meta.get("seed_sha") or "")
            if d["body"] and seed and _sha(body) == seed and _sha(d["body"]) != seed:
                body, meta["seed_sha"], changed = d["body"], _sha(d["body"]), True
            if meta.get("system") is not True or meta.get("slug") != SLUG or meta.get("type") != "agent":
                meta.update({"type": "agent", "slug": SLUG, "system": True})
                changed = True
            if not str(meta.get("name") or "").strip():
                meta["name"], changed = NAME, True
            if changed:
                _write_file(path, meta, body or d["body"])
            return path
        from datetime import date
        meta = {"type": "agent", "name": _legacy_name(root) or NAME, "slug": SLUG, "role": d["role"],
                "skills": [], "system": True, "seed_sha": _sha(d["body"]), "updated": date.today().strftime("%Y-%m-%d")}
        _write_file(path, meta, d["body"])
        return path


def read_core(root: Any):
    """(meta, body) of the brain's Javis Core file, made when missing. ({}, definition body) without a brain."""
    path = ensure_file(root)
    if path is None:
        return {}, definition()["body"]
    meta, body = _read_file(path)
    return meta, body or definition()["body"]


def role_text(meta: Dict[str, Any], lang_pick: Callable[[str, str], str]) -> str:
    """The role line to show: the definition's own text in the screen language while untouched, else the owner's."""
    d = definition()
    role = str((meta or {}).get("role") or "")
    return lang_pick(d["role"], d["role_en"]) if (not role or role == d["role"]) else role


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


def _read_extra(root: Any) -> Dict[str, Any]:
    path = _identity_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path else {}
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def identity(root: Any) -> Dict[str, Any]:
    """{'name', 'style', 'asked'} of Javis Core in the brain at `root`. Empty name = still called Javis Core."""
    out: Dict[str, Any] = {"name": "", "style": "", "asked": False}
    if not str(root or "").strip():
        return out
    meta, _ = read_core(root)
    nm = clean_name(meta.get("name"))
    out["name"] = "" if nm == NAME else nm
    extra = _read_extra(root)
    out["style"] = clean_style(extra.get("style"))
    out["asked"] = bool(extra.get("asked")) or bool(out["name"])
    return out


def set_identity(root: Any, *, name: Any = None, style: Any = None, asked: Optional[bool] = None) -> Dict[str, Any]:
    """Change only the fields given. A name given (even "") counts as asked: the person has answered. The name is
    written into the agent file, the same field the agent editor saves."""
    path = _identity_path(root)
    if path is None:
        raise ValueError("no brain")
    with _lock:
        if name is not None:
            f = ensure_file(root)
            meta, body = _read_file(f)
            meta["name"] = clean_name(name) or NAME
            _write_file(f, meta, body or definition()["body"])
        extra = _read_extra(root)
        extra.pop("name", None)
        if name is not None:
            extra["asked"] = True
        if style is not None:
            extra["style"] = clean_style(style)
        if asked is not None:
            extra["asked"] = bool(asked) or bool(extra.get("asked"))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(extra, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    return identity(root)


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
