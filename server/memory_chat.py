"""Memory and lessons handled from chat (0.190.0).

Owner, 16/10/2026, on the 0.187.0-0.188.0 settings: "Những phần đó người dùng không bao giờ dùng, thà nhắn tin bảo
xóa sửa thu hồi rồi AI làm giúp còn tốt hơn." The memory list on the Javis Core card and the lesson lists on an
assistant's settings column are gone from the screen; the person asks in chat and Javis does it with the
`javis_memory` tool (system plugin `javis-memory`), on any engine.

The rules stay where they were (`memory_control`, `agent_lessons`): a forgotten memory keeps only a fingerprint and is
not learnt again, a revoked lesson is not re-learnt by the agent, and the learning switch is a file the model's own
file tools cannot write. This module only puts them behind one tool call.

`wire(Deps(...))` is called once by `main.py`; `run(args, vault_root)` returns the text the model reads.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional

import agent_lessons as AL
import memory_control as MC

OUT_MAX = 7000          # API engines clip tool results at 8000 characters
BODY_PREVIEW = 160


@dataclass
class Deps:
    memory_dir: Callable[[str], Path]                       # vault root -> <brain>/memory
    agents: Callable[[str], List[dict]]                     # vault root -> [{slug, name}]
    agent_key: Callable[[str, str, bool], Optional[str]]    # (root, slug, register) -> agent_key | None
    lesson_store: Callable[[], Any]                         # () -> GoalStore | None
    agent_memory_file: Callable[[str, str], Path]           # (root, slug) -> memory/agents/<slug>/MEMORY.md


_DEPS: List[Optional[Deps]] = [None]


def wire(deps: Deps) -> Deps:
    _DEPS[0] = deps
    return deps


def _clip(text: str) -> str:
    return text if len(text) <= OUT_MAX else text[:OUT_MAX] + "\n…(cắt bớt)"


def _one_line(text: str, n: int = BODY_PREVIEW) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _find_agent(d: Deps, root: str, ref: str):
    """(agent, error). Accepts a slug or a name; names compare without case."""
    ref = str(ref or "").strip()
    if not ref:
        return None, "ERROR: thiếu agent (slug hoặc tên trợ lý)."
    ags = d.agents(root) or []
    for a in ags:
        if a.get("slug") == ref:
            return a, ""
    low = ref.casefold()
    hits = [a for a in ags if str(a.get("name") or "").casefold() == low] or \
           [a for a in ags if low in str(a.get("name") or "").casefold()]
    if len(hits) == 1:
        return hits[0], ""
    if len(hits) > 1:
        return None, "ERROR: nhiều trợ lý khớp: " + ", ".join(f"{a.get('name')} ({a.get('slug')})" for a in hits)
    return None, f"ERROR: không có trợ lý '{ref}' trong brain này."


def _scope_label(scope: str) -> str:
    if scope == "*":
        return "mọi nơi"
    if scope.startswith("dm:"):
        return "chat riêng"
    if scope.startswith("team:"):
        return "nhóm " + scope[5:]
    return scope


# ── memory of the brain ───────────────────────────────────────────────────────

def _op_list(d: Deps, root: str) -> str:
    mem = d.memory_dir(root)
    items = MC.list_memories(mem)
    head = (f"Ghi nhớ mới: {'BẬT' if MC.learning_enabled(mem) else 'TẮT'}. "
            f"Hồ sơ chung: {'có' if MC.read_profile() else 'chưa có'}. Đã quên: {len(MC.forgotten(mem))}.")
    if not items:
        return head + "\nBrain này chưa có ghi nhớ nào."
    lines = [head, f"{len(items)} ghi nhớ (slug | loại | nguồn | ngày | nội dung):"]
    for m in items:
        lines.append(f"- {m['slug']} | {m['type'] or '?'} | {m['source'] or '-'} | {m['updated'] or m['created'] or '-'}"
                     f" | {_one_line(m['title'] if m['title'] != m['slug'] else m['body'])}")
    return _clip("\n".join(lines))


def _op_edit(d: Deps, root: str, args: dict) -> str:
    slug, text = str(args.get("slug") or "").strip(), str(args.get("text") or "").strip()
    if not slug or not text:
        return "ERROR: edit cần slug (xem op=list) và text (nội dung mới)."
    try:
        MC.edit_memory(d.memory_dir(root), slug, text)
    except FileNotFoundError:
        return f"ERROR: không có ghi nhớ '{slug}'. Gọi op=list để xem slug đúng."
    except ValueError:
        return "ERROR: slug hoặc nội dung không hợp lệ."
    return f"Đã sửa ghi nhớ '{slug}' (đánh dấu: chủ sửa)."


def _op_forget(d: Deps, root: str, args: dict) -> str:
    slug = str(args.get("slug") or "").strip()
    if not slug:
        return "ERROR: forget cần slug (xem op=list)."
    try:
        r = MC.forget_memory(d.memory_dir(root), slug)
    except FileNotFoundError:
        return f"ERROR: không có ghi nhớ '{slug}'. Gọi op=list để xem slug đúng."
    except ValueError:
        return "ERROR: slug không hợp lệ."
    return (f"Đã quên '{r['title']}'. Javis không tự học lại điều này từ chat cũ; lịch sử chat không bị xoá. "
            "Brain có git hoặc bản sao lưu thì nội dung cũ vẫn còn trong đó.")


def _op_learning(d: Deps, root: str, args: dict) -> str:
    if "enabled" not in args:
        return f"Ghi nhớ mới đang {'BẬT' if MC.learning_enabled(d.memory_dir(root)) else 'TẮT'}."
    on = args.get("enabled") in (True, 1, "1", "true", "on")
    MC.set_learning(d.memory_dir(root), on)
    return ("Đã BẬT lưu ghi nhớ mới cho brain này." if on else
            "Đã TẮT lưu ghi nhớ mới cho brain này. Những gì đã nhớ vẫn được dùng.")


def _op_profile(args: dict) -> str:
    if "text" not in args:
        cur = MC.read_profile()
        return ("Hồ sơ chung (mọi brain):\n" + cur) if cur else "Chưa có hồ sơ chung."
    saved = MC.write_profile(str(args.get("text") or ""))
    return ("Đã lưu hồ sơ chung, dùng cho mọi brain." if saved else "Đã xoá hồ sơ chung.")


# ── lessons of an assistant ───────────────────────────────────────────────────

def _legacy_file_lines(path: Path) -> List[str]:
    try:
        return AL.legacy_lessons(path.read_text(encoding="utf-8")) if path.is_file() else []
    except OSError:
        return []


def _op_lessons(d: Deps, root: str, args: dict) -> str:
    a, e = _find_agent(d, root, args.get("agent"))
    if e:
        return e
    lines = [f"Bài học của {a.get('name') or a['slug']} ({a['slug']}):"]
    key, store = d.agent_key(root, a["slug"], False), d.lesson_store()
    rows = AL.lessons(store, key, status="active") if key and store is not None else []
    for r in rows:
        lines.append(f"- L{r['id']} | {_scope_label(r['scope'])} | {r['source']} | {_one_line(r['text'], 220)}")
    legacy = _legacy_file_lines(d.agent_memory_file(root, a["slug"]))
    for i, t in enumerate(legacy, 1):
        lines.append(f"- C{i} | bài học cũ (MEMORY.md) | {_one_line(t, 220)}")
    if len(lines) == 1:
        lines.append("Chưa có bài học nào.")
    else:
        lines.append("Mã L... thu hồi bằng op=lesson_revoke; mã C... là dòng cũ trong file, gỡ bằng op=lesson_revoke "
                     "với đúng mã đó.")
    return _clip("\n".join(lines))


def _op_lesson_add(d: Deps, root: str, args: dict) -> str:
    a, e = _find_agent(d, root, args.get("agent"))
    if e:
        return e
    text = str(args.get("text") or "").strip()
    if not text:
        return "ERROR: lesson_add cần text (một câu ngắn trợ lý cần nhớ)."
    store = d.lesson_store()
    key = d.agent_key(root, a["slug"], True)
    if not key or store is None:
        return "ERROR: kho bài học chưa sẵn sàng, thử lại sau vài giây."
    lid = AL.add(store, agent_key=key, scope="*", kind="method", text=text, source="owner", by="owner")
    return f"Đã thêm bài học L{lid} cho {a.get('name') or a['slug']}, dùng ở mọi nơi."


def _remove_legacy_line(path: Path, idx: int) -> Optional[str]:
    """Remove the idx-th (1-based) bullet of the legacy lessons section. Returns its text, or None."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    out, inside, n, gone = [], False, 0, None
    for line in text.splitlines(keepends=True):
        s = line.strip()
        if s.startswith("## "):
            inside = s == AL.LEGACY_HEADER
        elif inside and s.startswith(("- ", "* ")) and s[2:].strip():
            n += 1
            if n == idx and gone is None:
                gone = s[2:].strip()
                continue
        out.append(line)
    if gone is None:
        return None
    path.write_text("".join(out), encoding="utf-8")
    return gone


def _op_lesson_revoke(d: Deps, root: str, args: dict) -> str:
    a, e = _find_agent(d, root, args.get("agent"))
    if e:
        return e
    ref = str(args.get("id") or "").strip().upper()
    if ref.startswith("C") and ref[1:].isdigit():
        gone = _remove_legacy_line(d.agent_memory_file(root, a["slug"]), int(ref[1:]))
        return f"Đã gỡ bài học cũ: {_one_line(gone, 220)}" if gone else f"ERROR: không có bài học cũ {ref}."
    num = ref[1:] if ref.startswith("L") else ref
    if not num.isdigit():
        return "ERROR: id là mã trong op=lessons, ví dụ L12 hoặc C3."
    key, store = d.agent_key(root, a["slug"], False), d.lesson_store()
    if not key or store is None:
        return f"ERROR: {a.get('name') or a['slug']} chưa có bài học nào."
    r = AL.revoke(store, int(num), by="owner", reason="owner_chat", agent_key=key)
    if not r:
        return f"ERROR: không có bài học L{num} đang dùng của trợ lý này."
    return f"Đã thu hồi bài học L{num}. Trợ lý không tự học lại đúng câu này."


# ── entry point ───────────────────────────────────────────────────────────────

OPS = ("list", "edit", "forget", "learning", "profile", "lessons", "lesson_add", "lesson_revoke")


def run(args: dict, vault_root: str) -> str:
    d = _DEPS[0]
    if d is None:
        return "ERROR: máy chủ đang khởi động, thử lại sau vài giây."
    args = args if isinstance(args, dict) else {}
    op = str(args.get("op") or "").strip()
    root = str(vault_root or "").strip()
    if op == "profile":
        out = _op_profile(args)
        if "text" in args and root:
            MC.note_change(d.memory_dir(root))   # "đã nhớ cách xưng hô" is backed by the shared profile
        return out
    if not root:
        return "ERROR: chưa biết đang ở brain nào nên không đụng được trí nhớ."
    fn = {"list": lambda: _op_list(d, root), "edit": lambda: _op_edit(d, root, args),
          "forget": lambda: _op_forget(d, root, args), "learning": lambda: _op_learning(d, root, args),
          "lessons": lambda: _op_lessons(d, root, args), "lesson_add": lambda: _op_lesson_add(d, root, args),
          "lesson_revoke": lambda: _op_lesson_revoke(d, root, args)}.get(op)
    if fn is not None:
        out = fn()
        wrote = op not in ("list", "lessons") and not (op == "learning" and "enabled" not in args)
        if wrote and not out.startswith("ERROR"):
            MC.note_change(d.memory_dir(root))   # the turn's empty-claim check must not flag a real write
        return out
    return "ERROR: op phải là một trong " + ", ".join(OPS) + "."
