"""What Javis remembers, and the person's control over it (0.188.0, Javis Core spec sections 10, 12 and 13).

The brain's memory stays where it always was: `memory/MEMORY.md` (the index loaded before every turn) and one file
per memory in `memory/facts/`. This module adds the controls the spec asks for, nothing parallel:

- list: every memory with what its frontmatter says about it (type, origin, source, status, dates);
- edit: change one memory's text or type; it is then marked as edited by the owner;
- forget: delete the memory file and its index line, and remember a FINGERPRINT of it (no content) in
  `memory/forgotten.json`, so neither the learning loop nor the index curator brings it back from old chats;
- learning switch per brain (`memory/learning.json`): off = nothing new is written by the learning loop or by
  agent lessons, and the chat model is told so; what is already remembered is still used.

Limits, stated where the person can read them (docs and the screen): a brain kept in git still has the old text in
its git history, and a backup made before forgetting still has it. Forgetting does not delete chat history; deleting
a chat does not delete memory.

A per-person profile shared by every brain lives in `STATE_DIR/user_profile.md` (spec 10.2). One instance has one
account, so one file. It is loaded before the brain's own memory, which therefore wins where they differ (10.3).
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

import fastyaml

_LOCK = threading.RLock()
FORGOTTEN = "forgotten.json"
LEARNING = "learning.json"
PROFILE_MAX = 4000
_SLUG_RE = re.compile(r"^[^\s/\\:]{1,120}$")


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFC", str(text or "")).lower()
    t = re.sub(r"[`*_>#\-\[\]()|]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def fingerprint(text: str) -> str:
    """A short hash of a memory's normalized text: enough to recognise it again, no content kept."""
    n = _norm(text)
    return hashlib.sha256(n.encode("utf-8")).hexdigest()[:20] if n else ""


def _split(text: str):
    parts = fastyaml.split_frontmatter(text)
    if parts:
        try:
            meta = fastyaml.safe_load(parts[0]) or {}
        except Exception:  # noqa: BLE001
            meta = {}
        return (meta if isinstance(meta, dict) else {}), parts[1].strip()
    return {}, str(text or "").strip()


def _join(meta: dict, body: str) -> str:
    lines = [f"{k}: {v}" for k, v in meta.items() if v is not None and str(v) != ""]
    return "---\n" + "\n".join(lines) + "\n---\n" + body.strip() + "\n"


def valid_slug(slug: str) -> bool:
    s = str(slug or "")
    return bool(_SLUG_RE.match(s)) and ".." not in s and not s.startswith(".")


# ── forgotten list ────────────────────────────────────────────────────────────

def _forgotten_path(mem_dir: Path) -> Path:
    return Path(mem_dir) / FORGOTTEN


def forgotten(mem_dir: Path) -> List[dict]:
    try:
        d = json.loads(_forgotten_path(mem_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [x for x in (d.get("items") or []) if isinstance(x, dict)] if isinstance(d, dict) else []


def is_forgotten(mem_dir: Path, *, slug: str = "", text: str = "") -> bool:
    """True when a memory with this slug or this text was forgotten on purpose (checked before any re-learning)."""
    items = forgotten(mem_dir)
    fp = fingerprint(text) if text else ""
    return any((slug and x.get("slug") == slug) or (fp and x.get("fp") == fp) for x in items)


def _remember_forgotten(mem_dir: Path, slug: str, title: str, body: str) -> None:
    items = forgotten(mem_dir)
    items.append({"slug": slug, "fp": fingerprint(body), "title": str(title or slug)[:80],
                  "at": time.strftime("%Y-%m-%d")})
    p = _forgotten_path(mem_dir)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps({"items": items[-2000:]}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


# ── learning switch ───────────────────────────────────────────────────────────

# ── memory writes that leave no file behind (0.190.0) ─────────────────────────
# A lesson revoked or added through the memory tool lives in the lesson store, not under memory/. The turn's receipt
# and the empty-claim check (memory_receipt) still have to know something was written, so the tools note it here.
_ACTIVITY: Dict[str, float] = {}


def note_change(mem_dir) -> None:
    with _LOCK:
        _ACTIVITY[str(Path(mem_dir))] = time.time()


def changed_since(mem_dir, t: float) -> bool:
    return _ACTIVITY.get(str(Path(mem_dir)), 0.0) >= float(t or 0)


def learning_enabled(mem_dir: Path) -> bool:
    try:
        d = json.loads((Path(mem_dir) / LEARNING).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return not (isinstance(d, dict) and d.get("enabled") is False)


def set_learning(mem_dir: Path, on: bool) -> bool:
    p = Path(mem_dir) / LEARNING
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"enabled": bool(on), "updated": time.strftime("%Y-%m-%d")}), encoding="utf-8")
    return bool(on)


LEARNING_OFF_NOTE = ("\n\n# === GHI NHỚ MỚI ĐANG TẮT ===\n"
                     "Người dùng đã tắt việc lưu ghi nhớ mới cho brain này. Vẫn dùng bộ nhớ đã có, nhưng KHÔNG tạo hay "
                     "sửa file trong memory/ và không thêm dòng vào MEMORY.md. Nếu người dùng nhờ nhớ điều gì, nói rõ "
                     "việc ghi nhớ đang tắt và chỉ chỗ bật lại (Javis Core > Trí nhớ).")


# ── list / edit / forget ──────────────────────────────────────────────────────

def _index_titles(mem_dir: Path) -> Dict[str, str]:
    out = {}
    try:
        for line in (Path(mem_dir) / "MEMORY.md").read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*-\s*\[([^\]]+)\]\(facts/([^)]+?)\.md\)\s*(?:[-:]\s*(.*))?$", line)
            if m:
                out[m.group(2)] = m.group(1).strip()
    except OSError:
        pass
    return out


def list_memories(mem_dir: Path) -> List[Dict[str, Any]]:
    facts = Path(mem_dir) / "facts"
    titles = _index_titles(mem_dir)
    out = []
    for f in sorted(facts.glob("*.md")) if facts.is_dir() else []:
        try:
            meta, body = _split(f.read_text(encoding="utf-8"))
        except OSError:
            continue
        if meta.get("superseded_by"):
            continue   # replaced by a newer memory: not in use
        first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
        out.append({
            "slug": f.stem,
            "title": titles.get(f.stem) or first[:80] or f.stem,
            "body": body[:2000],
            "type": str(meta.get("type") or ""),
            "origin": str(meta.get("origin") or ""),
            "provenance": str(meta.get("provenance") or ""),
            "source": str(meta.get("source") or ""),
            "status": str(meta.get("status") or ""),
            "scope": str(meta.get("scope") or ""),
            "created": str(meta.get("created") or ""),
            "updated": str(meta.get("updated") or ""),
        })
    out.sort(key=lambda x: (x["updated"] or x["created"], x["slug"]), reverse=True)
    return out


def edit_memory(mem_dir: Path, slug: str, body: str, type_: Optional[str] = None) -> dict:
    if not valid_slug(slug):
        raise ValueError("bad slug")
    body = str(body or "").strip()
    if not body:
        raise ValueError("empty")
    p = Path(mem_dir) / "facts" / f"{slug}.md"
    with _LOCK:
        if not p.is_file():
            raise FileNotFoundError(slug)
        meta, _old = _split(p.read_text(encoding="utf-8"))
        if type_:
            meta["type"] = str(type_)[:20]
        meta["origin"] = "owner-edited"
        meta["status"] = "confirmed"   # the owner wrote it: a confirmed memory, not a guess
        meta["updated"] = time.strftime("%Y-%m-%d")
        p.write_text(_join(meta, body), encoding="utf-8")
    return {"slug": slug, "updated": meta["updated"]}


def forget_memory(mem_dir: Path, slug: str) -> dict:
    """Delete one memory and keep only its fingerprint, so it is not learnt again. Returns what was removed."""
    if not valid_slug(slug):
        raise ValueError("bad slug")
    mem_dir = Path(mem_dir)
    p = mem_dir / "facts" / f"{slug}.md"
    with _LOCK:
        if not p.is_file():
            raise FileNotFoundError(slug)
        meta, body = _split(p.read_text(encoding="utf-8"))
        title = _index_titles(mem_dir).get(slug) or slug
        _remember_forgotten(mem_dir, slug, title, body)
        p.unlink()
        idx = mem_dir / "MEMORY.md"
        removed_line = False
        try:
            lines = idx.read_text(encoding="utf-8").splitlines(keepends=True)
            keep = [ln for ln in lines if f"(facts/{slug}.md)" not in ln]
            removed_line = len(keep) != len(lines)
            if removed_line:
                idx.write_text("".join(keep), encoding="utf-8")
        except OSError:
            pass
    return {"slug": slug, "title": title, "index_line_removed": removed_line}


# ── person profile shared by every brain ──────────────────────────────────────

def _profile_path() -> Path:
    import config as cfgmod
    return Path(cfgmod.STATE_DIR) / "user_profile.md"


def read_profile() -> str:
    try:
        return _profile_path().read_text(encoding="utf-8").strip()[:PROFILE_MAX]
    except OSError:
        return ""


def write_profile(text: str) -> str:
    text = str(text or "").strip()[:PROFILE_MAX]
    p = _profile_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text + ("\n" if text else ""), encoding="utf-8")
    tmp.replace(p)
    return text


def profile_block() -> str:
    """The person's profile for the prompt, before the brain's own memory (which wins where they differ)."""
    t = read_profile()
    return ("\n\n# === HỒ SƠ NGƯỜI DÙNG (chung mọi brain, do người dùng tự viết) ===\n"
            "Cách xưng hô, ngôn ngữ, cách trình bày và mức chi tiết người dùng muốn. Bộ nhớ riêng của brain bên dưới "
            "thắng khi hai bên khác nhau.\n" + t) if t else ""


# ── 0.188.0: hard block for Claude Code, and a source on every new memory ─────────────────────────────────────────

def claude_deny_rules(vault_root) -> List[str]:
    """Permission rules for a Claude Code turn in this brain (`disallowed_tools`; deny rules hold even in
    bypassPermissions). The switch file and the forgotten list are never the model's to write; with learning off
    nothing under memory/ is. Paths are given both relative to the brain (the turn's cwd) and absolute."""
    if not vault_root:
        return []
    mem = Path(vault_root) / "memory"
    rels, tools = [], ("Write", "Edit", "MultiEdit", "NotebookEdit")
    if learning_enabled(mem):
        rels = [f"memory/{LEARNING}", f"memory/{FORGOTTEN}"]
    else:
        rels = ["memory/**"]
    out = []
    for r in rels:
        absolute = "/" + str((Path(vault_root) / r).as_posix()).lstrip("/")
        for t in tools:
            out.append(f"{t}({r})")
            out.append(f"{t}(/{absolute})")   # "//abs/path" = absolute in Claude Code rule syntax
    return out


def stamp_new_facts(mem_dir, *, source: str, since: float) -> List[str]:
    """Give a source to memories written during a turn that did not record one (spec 12.3): the chat and the date.
    The model is asked to, but the server makes sure. Returns the slugs it stamped."""
    facts = Path(mem_dir) / "facts"
    if not facts.is_dir() or not source:
        return []
    done = []
    for f in facts.glob("*.md"):
        try:
            if f.stat().st_mtime < since:
                continue
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body = _split(text)
        if meta.get("source") or not body:
            continue
        meta["source"] = source[:120]
        meta.setdefault("status", "confirmed" if meta.get("origin") == "owner-edited" else "")
        if not meta.get("status"):
            meta.pop("status", None)
        with _LOCK:
            try:
                f.write_text(_join(meta, body), encoding="utf-8")
                done.append(f.stem)
            except OSError:
                pass
    return done
