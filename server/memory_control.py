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
import os
import re
import sys
import threading
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import fastyaml
import main_prompt_rendering
import yaml

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


_FLAT_LINE = re.compile(r"^([A-Za-z_][\w-]*):(?:[ \t]+(.*))?$")


def _salvage(header: str) -> Optional[dict]:
    """Read a header that is not valid YAML but is one `key: value` per line. That is exactly what `_join` wrote before
    it quoted anything (#1165): `description: Note: example` breaks YAML yet every key is still there. Each value is
    read as YAML on its own when it can be (`['tag']` back to a list, a date back to a date), else kept as text.
    Anything else (an indented line, a line with no key) returns None: guessing there could lose data."""
    meta: Dict[str, Any] = {}
    for raw in str(header or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = _FLAT_LINE.match(line)
        if not m:
            return None
        raw_value = (m.group(2) or "").strip()
        value: Any = raw_value
        try:
            parsed = fastyaml.safe_load(raw_value) if raw_value else ""
            # `Note: example` reads as a one-key mapping; the old writer only ever wrote a mapping as `{...}`.
            if not (isinstance(parsed, dict) and not raw_value.startswith("{")):
                value = parsed
        except Exception:  # noqa: BLE001 - not YAML on its own: keep the text as written
            pass
        meta[m.group(1)] = value
    return meta or None


def _read(text: str):
    """(meta, body, state). state: "none" (no frontmatter), "ok" (valid YAML mapping), "salvaged" (see `_salvage`),
    "broken" (a frontmatter block that cannot be read; meta is then {} and must not be written back)."""
    parts = fastyaml.split_frontmatter(text)
    if not parts:
        return {}, str(text or "").strip(), "none"
    try:
        meta = fastyaml.safe_load(parts[0]) or {}
    except Exception:  # noqa: BLE001
        meta = None
    if isinstance(meta, dict):
        return meta, parts[1].strip(), "ok"
    rescued = _salvage(parts[0])
    if rescued is not None:
        return rescued, parts[1].strip(), "salvaged"
    return {}, parts[1].strip(), "broken"


def _split(text: str):
    meta, body, _state = _read(text)
    return meta, body


def _dump(meta: dict) -> str:
    """Frontmatter lines for `meta`. safe_dump quotes whatever YAML needs quoted (a colon, `#`, quotes, a leading
    `[`), so the file reads back to the same values (#1165). Same settings as learn.dump_fm."""
    keep = {k: v for k, v in meta.items() if v is not None and str(v) != ""}
    if not keep:
        return ""
    return yaml.safe_dump(keep, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000)


def _join(meta: dict, body: str) -> str:
    return "---\n" + _dump(meta) + "---\n" + body.strip() + "\n"


def _insert_keys(text: str, extra: dict) -> Optional[str]:
    """Add keys to the frontmatter of `text` without rewriting the ones already there (their quoting, order, comments
    and list style stay byte for byte). None when `text` has no frontmatter block."""
    parts = fastyaml.split_frontmatter(text)
    if not parts:
        return None
    close = len(text) - len(parts[1]) - 3   # where the closing `---` line starts (always right after a newline)
    return text[:close] + _dump(extra) + text[close:]


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
    """slug -> title from MEMORY.md and the secondary indexes (memory_index_files, #934). MEMORY.md wins a tie."""
    import memory_index_files
    out = {}
    for f in memory_index_files.index_files(mem_dir):
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                m = re.match(r"\s*-\s*\[([^\]]+)\]\(facts/([^)]+?)\.md\)\s*(?:[-:]\s*(.*))?$", line)
                if m and m.group(2) not in out:
                    out[m.group(2)] = m.group(1).strip()
        except OSError:
            continue
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
        meta, _old, state = _read(p.read_text(encoding="utf-8"))
        if state == "broken":
            # Writing {} back would drop every key the file has (#1165). The owner fixes the file by hand first.
            raise ValueError("frontmatter unreadable")
        if type_:
            meta["type"] = str(type_)[:20]
        meta["origin"] = "owner-edited"
        meta["status"] = "confirmed"   # the owner wrote it: a confirmed memory, not a guess
        meta["updated"] = time.strftime("%Y-%m-%d")
        p.write_text(_join(meta, body), encoding="utf-8")
    return {"slug": slug, "updated": meta["updated"]}


# Set by main.py: called with (memory dir, {slug, title, learned}) after a memory was forgotten. A memory Javis
# had learned on its own and the owner then removed is the clearest sign there is that the learner got it wrong.
on_forget = None


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
    out = {"slug": slug, "title": title, "index_line_removed": removed_line}
    if on_forget is not None:
        try:
            # `learned`: the self-learning loop wrote this memory (origin: javis-learned), not the owner or a chat.
            on_forget(mem_dir, {**out, "learned": str(meta.get("origin") or "") == "javis-learned"})
        except Exception as e:   # noqa: BLE001 - a listener must not undo the forgetting
            print(f"[memory forget] listener: {type(e).__name__}: {e}", file=sys.stderr)
    return out


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
    # read_profile already strips and caps. Preserve that prepared string exactly,
    # including whitespace at the cap boundary; do not normalize it a second time.
    return main_prompt_rendering.render_profile_block(read_profile(), preserve_full_protected=True)


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


# Background work that may write files, per brain: [brain key, start, end (0.0 while running)] (#1165). A chat turn
# stamps the memories changed while it ran with its own source; a memory a Kanban job, reminder or loop wrote at the
# same moment used to get that chat's source too. While such work runs in the same brain, a memory changed in the
# overlap is left without a source: none is better than a wrong one.
_WRITER_SPANS: List[list] = []
WRITER_SPAN_KEEP_S = 3600
_WRITER_SLACK_S = 1.0     # mtime resolution and the instant between a write and the span's own clock reading


def _brain_key(root) -> str:
    try:
        return os.path.normcase(str(Path(root).expanduser().resolve()))
    except Exception:  # noqa: BLE001
        return os.path.normcase(str(root))


@contextmanager
def background_writer(root, mode: str = "full"):
    """Mark background work in brain `root` that may write files (`auto` and `full`; `suggest` only reads)."""
    if not root or str(mode or "full").strip().lower() not in ("auto", "full"):
        yield
        return
    span = [_brain_key(root), time.time(), 0.0]
    with _LOCK:
        cutoff = time.time() - WRITER_SPAN_KEEP_S
        _WRITER_SPANS[:] = [s for s in _WRITER_SPANS if not s[2] or s[2] >= cutoff]
        _WRITER_SPANS.append(span)
    try:
        yield
    finally:
        span[2] = time.time()


def _writer_spans(mem_dir, since: float) -> List[tuple]:
    """(start, end) of background writers in the brain holding `mem_dir` that overlap `since`..now."""
    mem = _brain_key(mem_dir)
    now = time.time()
    out = []
    with _LOCK:
        for key, start, end in _WRITER_SPANS:
            if (mem == key or mem.startswith(key.rstrip(os.sep) + os.sep)) and (end or now) >= since:
                out.append((start, end or now))
    return out


def stamp_new_facts(mem_dir, *, source: str, since: float) -> List[str]:
    """Give a source to memories written during a turn that did not record one (spec 12.3): the chat and the date.
    The model is asked to, but the server makes sure. Returns the slugs it stamped."""
    facts = Path(mem_dir) / "facts"
    if not facts.is_dir() or not source:
        return []
    done = []
    others = _writer_spans(mem_dir, since)
    for f in facts.glob("*.md"):
        try:
            mtime = f.stat().st_mtime
            if mtime < since:
                continue
            if any(start - _WRITER_SLACK_S <= mtime <= end + _WRITER_SLACK_S for start, end in others):
                continue   # background work in this brain was writing at that moment: whose memory it is, is unknown
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body, state = _read(text)
        if state in ("broken", "salvaged"):
            # Not valid YAML: rewriting it from what could be read loses keys or quoting (#1165). Leave it alone.
            print(f"[memory stamp] {f.name}: frontmatter is not valid YAML, left as is", file=sys.stderr)
            continue
        if meta.get("source") or not body:
            continue
        extra = {"source": source[:120]}
        if not meta.get("status") and meta.get("origin") == "owner-edited":
            extra["status"] = "confirmed"
        # Add the new keys only: rebuilding the whole frontmatter is what dropped the quotes of the other ones.
        new = _insert_keys(text, extra) if state == "ok" else _join(extra, body)
        with _LOCK:
            try:
                f.write_text(new, encoding="utf-8")
                done.append(f.stem)
            except OSError:
                pass
    return done
