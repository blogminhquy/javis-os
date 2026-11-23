"""Improve on the owner's request: an assistant changes itself, the brain, and Javis's own code (2026-11-15).

Owner, 14/11/2026: "khi anh yêu cầu nó cải tiến thì nó cũng có thể thay đổi được chính nó và cải tiến toàn bộ hệ
thống được", then chose the widest scope: everything in the brain AND Javis's source code.

Before this module an assistant at Full access could already write its own file, any skill or workflow, by hand. Three
things were missing, and this is what the tool `javis_improve` (system/plugins/javis-improve) adds on top:

1. A boundary. Only a turn the owner started (`la_chu`, or a Kanban job or reminder the owner set up) may change
   anything here. Auto's own wake-ups and customer bots may not: they can only suggest. The paths are limited to the
   brain's own definitions (agents, skills, workflows, loops, memory, the brain's CLAUDE.md), never plugins, settings or
   anything outside the brain.
2. Backup and undo. Every save keeps the previous bytes, gets an id, and `undo` puts them back (an undo is itself a
   change, so it can be undone). Chat edits had no undo before: the change receipt under an answer only removes NEW
   items.
3. A path for Javis's own code. `attach_source` attaches the official repo to the chat through GitHub in chat
   (github_repos.attach): the server checks, pushes, opens the PR, follows CI and merges on green as for any repo, then
   the Release workflow numbers the version. Only on an install whose GitHub account can push to it (its
   maintainers); every other install gets a prefilled issue link instead (`report_url`, 2026-11-20). Putting that
   release on this install is the owner's own press of the Update button: nothing here starts an update (owner,
   23/11/2026: "anh không muốn tự update mà người dùng phải vào trang update để cập nhật lên").

Plain functions with explicit arguments; main.py wires the update entry point (`wire`). Nothing here calls a model.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Optional

from config import STATE_DIR

SOURCE_REPO = "blogminhquy/javis-os"        # the repo every install updates from (updater.release_source)
STORE_DIR = STATE_DIR / "self_upgrade"
OWNER_SCHEDULED = ("kanban", "reminder")     # background work the owner set up runs with the owner's word
MAX_CHARS = 200_000
DIFF_LINES = 60
HISTORY_KEEP = 300
SKILL_DESC_MAX = 150                         # the skill router cuts descriptions at 150 characters (CLAUDE.md)

# Areas of the brain an owner-requested improvement may change, by the first path parts.
_AREAS = (("agents",), ("skills",), ("workflows",), ("Javis", "loops"), ("memory",))
# Never, even on request: switches and lists the owner sets on pages, and anything hidden.
_DENY_NAMES = {"learning.json", "forgotten.json"}

_LOCK = threading.RLock()
_UPDATE: dict = {"versions": None}


class ImproveError(ValueError):
    pass


def _c(vi: str, en: str) -> str:
    try:
        import localefmt
        return localefmt.chu(vi, en)
    except Exception:  # noqa: BLE001
        return vi


# ── who may ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def owner_turn(turn: Optional[dict]) -> bool:
    """A turn the owner started: the owner's own surface, or background work the owner set up. No turn at all (loops,
    Auto's wake-ups, engines that cannot carry the key) is nobody, never the owner."""
    t = turn or {}
    if not t:
        return False
    if t.get("la_chu"):
        return True
    return str(t.get("kenh") or "") in OWNER_SCHEDULED


# ── where ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def resolve(brain_root: str, path: str) -> tuple:
    """(absolute Path, relative posix path, area) of a file an improvement may write. Raises ImproveError otherwise."""
    root = Path(str(brain_root or "")).resolve()
    if not str(brain_root or "").strip() or not root.is_dir():
        raise ImproveError(_c("Không rõ brain đang làm việc.", "Unknown working brain."))
    raw = str(path or "").strip().replace("\\", "/")
    if not raw:
        raise ImproveError(_c("Thiếu path.", "Missing path."))
    p = Path(raw)
    full = (p if p.is_absolute() else root / p).resolve()
    try:
        rel = full.relative_to(root).as_posix()
    except ValueError:
        raise ImproveError(_c("Chỉ sửa được file trong brain. Mã nguồn Javis sửa qua op=source.",
                              "Only files inside the brain. Javis's own code goes through op=source."))
    parts = tuple(rel.split("/"))
    if any(x.startswith(".") for x in parts) or parts[-1] in _DENY_NAMES:
        raise ImproveError(_c(f"Không được sửa {rel}.", f"{rel} cannot be changed here."))
    if rel == "CLAUDE.md":
        return full, rel, "brain_rules"
    for area in _AREAS:
        if parts[:len(area)] == area and len(parts) > len(area):
            kind = {"agents": "agent", "skills": "skill", "workflows": "workflow", "Javis": "loop",
                    "memory": "memory"}[area[0]]
            return full, rel, kind
    raise ImproveError(_c(
        f"{rel} không thuộc vùng tự cải tiến (agents/, skills/, workflows/, Javis/loops/, memory/, CLAUDE.md của brain). "
        "Plugin dùng javis_plugin, cài đặt dùng công cụ riêng của nó.",
        f"{rel} is outside what an improvement may change (agents/, skills/, workflows/, Javis/loops/, memory/, the "
        "brain's CLAUDE.md). Plugins go through javis_plugin, settings through their own tools."))


def _frontmatter(text: str) -> Optional[dict]:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    try:
        import fastyaml
        d = fastyaml.safe_load(text[3:end])
    except Exception:  # noqa: BLE001
        return None
    return d if isinstance(d, dict) else None


def validate(kind: str, rel: str, text: str) -> str:
    """"" when the new text keeps the file usable, else why not. Only checks what breaks loading."""
    if not text.strip():
        return _c("Nội dung rỗng. Muốn bỏ một thay đổi thì dùng op=undo.", "Empty content. Use op=undo to drop a change.")
    if len(text) > MAX_CHARS:
        return _c(f"File quá dài (hơn {MAX_CHARS} ký tự).", f"File too long (over {MAX_CHARS} characters).")
    md_def = rel.endswith(".md") and (
        kind in ("agent", "workflow", "loop") or (kind == "skill" and rel.endswith("/SKILL.md")))
    if md_def:
        fm = _frontmatter(text)
        if fm is None:
            return _c("File định nghĩa phải mở đầu bằng khối frontmatter --- hợp lệ.",
                      "A definition file must start with a valid --- frontmatter block.")
        if kind == "skill":
            desc = str(fm.get("description") or "")
            if not desc.strip():
                return _c("Skill cần description.", "A skill needs a description.")
            if len(desc) > SKILL_DESC_MAX:
                return _c(f"description của skill dài {len(desc)} ký tự, tối đa {SKILL_DESC_MAX} (bộ định tuyến cắt ở "
                          f"{SKILL_DESC_MAX}).", f"The skill description is {len(desc)} characters, at most "
                          f"{SKILL_DESC_MAX} (the router cuts there).")
    return ""


# ── the change ledger ───────────────────────────────────────────────────────────────────────────────────────────────

def _brain_dir(brain_root: str) -> Path:
    key = hashlib.sha1(str(Path(str(brain_root)).resolve()).encode("utf-8")).hexdigest()[:12]
    return STORE_DIR / key


def _ledger_path(brain_root: str) -> Path:
    return _brain_dir(brain_root) / "changes.json"


def _load(brain_root: str) -> dict:
    p = _ledger_path(brain_root)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("changes"), list):
            return d
    except Exception:  # noqa: BLE001 - a missing or broken ledger starts over; files themselves are untouched
        pass
    return {"next": 1, "changes": []}


def _save_ledger(brain_root: str, d: dict) -> None:
    p = _ledger_path(brain_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    d["changes"] = d["changes"][-HISTORY_KEEP:]
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _put_blob(brain_root: str, text: str) -> str:
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    p = _brain_dir(brain_root) / "blobs" / f"{sha}.txt"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="")
    return sha


def _get_blob(brain_root: str, sha: str) -> Optional[str]:
    p = _brain_dir(brain_root) / "blobs" / f"{sha}.txt"
    try:
        return p.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None


def _write(full: Path, text: str) -> None:
    full.parent.mkdir(parents=True, exist_ok=True)
    tmp = full.with_name(full.name + ".javis-tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, full)


def _diff(rel: str, old: str, new: str) -> tuple:
    lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(), f"a/{rel}", f"b/{rel}", lineterm="", n=1))
    added = sum(1 for x in lines if x.startswith("+") and not x.startswith("+++"))
    removed = sum(1 for x in lines if x.startswith("-") and not x.startswith("---"))
    shown = lines[:DIFF_LINES]
    if len(lines) > DIFF_LINES:
        shown.append(f"... ({len(lines) - DIFF_LINES} dòng diff nữa)")
    return added, removed, "\n".join(shown)


def apply_edits(text: str, edits: Iterable[Any]) -> str:
    """Replace each `old` (must occur exactly once) with `new`, in order."""
    out = text
    for i, e in enumerate(list(edits or []), 1):
        if not isinstance(e, dict):
            raise ImproveError(_c(f"Sửa thứ {i} sai dạng.", f"Edit {i} is malformed."))
        old, new = str(e.get("old") or ""), str(e.get("new") if e.get("new") is not None else "")
        if not old:
            raise ImproveError(_c(f"Sửa thứ {i} thiếu old.", f"Edit {i} has no old text."))
        n = out.count(old)
        if n != 1:
            raise ImproveError(_c(f"Sửa thứ {i}: đoạn old xuất hiện {n} lần, phải đúng 1 lần.",
                                  f"Edit {i}: the old text occurs {n} times, it must occur exactly once."))
        out = out.replace(old, new, 1)
    return out


def _record(brain_root: str, entry: dict) -> dict:
    with _LOCK:
        d = _load(brain_root)
        entry["id"] = int(d.get("next") or 1)
        d["next"] = entry["id"] + 1
        d["changes"].append(entry)
        _save_ledger(brain_root, d)
    return entry


def save(brain_root: str, path: str, *, content: Optional[str] = None, edits: Optional[list] = None,
         reason: str = "", actor: str = "", now: Optional[float] = None) -> dict:
    """Write one file of the brain with a backup. `content` (the whole new file) or `edits` ([{old, new}])."""
    full, rel, kind = resolve(brain_root, path)
    if (content is None) == (not edits):
        raise ImproveError(_c("Truyền content (cả file mới) HOẶC edits ([{old, new}]), không cả hai.",
                              "Pass content (the whole new file) OR edits ([{old, new}]), not both."))
    with _LOCK:
        existed = full.is_file()
        old = full.read_text(encoding="utf-8") if existed else ""
        if edits:
            if not existed:
                raise ImproveError(_c(f"{rel} chưa có, tạo mới thì truyền content.",
                                      f"{rel} does not exist; pass content to create it."))
            new = apply_edits(old, edits)
        else:
            new = str(content)
        why = validate(kind, rel, new)
        if why:
            raise ImproveError(why)
        if existed and new == old:
            return {"unchanged": True, "path": rel}
        before = _put_blob(brain_root, old) if existed else ""
        _write(full, new)
        added, removed, diff = _diff(rel, old, new)
        entry = _record(brain_root, {
            "at": float(now if now is not None else time.time()), "path": rel, "kind": kind, "created": not existed,
            "before": before, "after": hashlib.sha256(new.encode("utf-8")).hexdigest(),
            "reason": " ".join(str(reason or "").split())[:300], "actor": str(actor or "")[:120],
            "added": added, "removed": removed, "undo_of": None, "undone_by": None})
    out = dict(entry, diff=diff)
    if kind == "skill":
        slug = rel.split("/")[1]
        try:
            import system_sync
            if system_sync.is_system_skill(slug):
                out["note"] = _c(f"{slug} là skill hệ thống: bản trong brain này đã khác bản gốc nên sẽ không tự cập nhật "
                                 "theo app nữa (hoàn tác để nhận lại cập nhật).",
                                 f"{slug} is a system skill: this brain's copy now differs from the shipped one, so app "
                                 "updates no longer replace it (undo to get updates again).")
        except Exception:  # noqa: BLE001
            pass
    return out


def undo(brain_root: str, change_id: Any, *, actor: str = "", now: Optional[float] = None) -> dict:
    """Put back the bytes from before change `change_id` (a file it created is removed). The undo is a change too."""
    try:
        cid = int(str(change_id).lstrip("#"))
    except (TypeError, ValueError):
        raise ImproveError(_c("id phải là số (xem op=history).", "id must be a number (see op=history)."))
    with _LOCK:
        d = _load(brain_root)
        ch = next((c for c in d["changes"] if c.get("id") == cid), None)
        if ch is None:
            raise ImproveError(_c(f"Không có thay đổi #{cid}.", f"No change #{cid}."))
        if ch.get("undone_by"):
            raise ImproveError(_c(f"Thay đổi #{cid} đã được hoàn tác bởi #{ch['undone_by']}.",
                                  f"Change #{cid} was already undone by #{ch['undone_by']}."))
        full, rel, kind = resolve(brain_root, ch["path"])
        cur = full.read_text(encoding="utf-8") if full.is_file() else ""
        cur_blob = _put_blob(brain_root, cur) if full.is_file() else ""
        drifted = bool(cur) and hashlib.sha256(cur.encode("utf-8")).hexdigest() != ch.get("after")
        if ch.get("created"):
            if full.is_file():
                full.unlink()
            restored = ""
        else:
            restored = _get_blob(brain_root, ch.get("before") or "")
            if restored is None:
                raise ImproveError(_c(f"Mất bản sao lưu của thay đổi #{cid}.", f"The backup of change #{cid} is gone."))
            _write(full, restored)
        added, removed, diff = _diff(rel, cur, restored)
        entry = {"at": float(now if now is not None else time.time()), "path": rel, "kind": kind,
                 "created": not bool(cur_blob), "before": cur_blob,
                 "after": hashlib.sha256(restored.encode("utf-8")).hexdigest(), "reason": f"undo #{cid}",
                 "actor": str(actor or "")[:120], "added": added, "removed": removed, "undo_of": cid,
                 "undone_by": None, "removed_file": bool(ch.get("created"))}
        entry["id"] = int(d.get("next") or 1)
        d["next"] = entry["id"] + 1
        ch["undone_by"] = entry["id"]
        d["changes"].append(entry)
        _save_ledger(brain_root, d)
    out = dict(entry, diff=diff)
    if drifted:
        out["note"] = _c("File đã bị sửa thêm sau thay đổi đó; bản hiện tại được giữ trong lần hoàn tác này (hoàn tác "
                         f"#{entry['id']} để lấy lại).", "The file changed again after that change; the current text is "
                         f"kept in this undo (undo #{entry['id']} to get it back).")
    return out


def history(brain_root: str, limit: int = 10) -> list:
    with _LOCK:
        d = _load(brain_root)
    return list(reversed(d["changes"]))[:max(1, int(limit))]


# ── Javis's own code ───────────────────────────────────────────────────────────────────────────────────────────────

def source_status(sid: str, brain_root: str) -> dict:
    """Is GitHub connected, and is the official repo attached to this chat (with its worktree)?"""
    import github_repos
    st = github_repos.status()
    attached = None
    if sid:
        for r in github_repos.session_repos(sid, brain_root):
            if str(r.get("full_name") or "").lower() == SOURCE_REPO.lower():
                attached = r
    return {"repo": SOURCE_REPO, "connected": bool(st.get("connected")), "has_git": bool(st.get("has_git")),
            "attached": attached, "can_write": bool(attached) or can_write_source()}


def can_write_source() -> bool:
    """True only when GitHub says the connected account may push to the official repo, i.e. a maintainer's install.

    Every install ships `op=source`, so before 2026-11-20 a user's Javis cloned the public repo, edited it for a whole
    turn and then failed the push with "account X cannot write to blogminhquy/javis-os". Owner, 20/11/2026: keep the
    value (users sending fixes) without that dead end, the smallest way: no write access means no clone and no edit,
    the model writes a bug report instead (`report_url`). Not connected, or GitHub not answering who may push
    (`permissions` missing, 401/403/404), counts as no. Any other failure (network) raises, so a maintainer whose
    GitHub hiccups is told to retry rather than handed a report link."""
    import github_repos
    from github_api import GitHubError
    if not github_repos.status().get("connected"):
        return False
    try:
        meta = github_repos.client().repo(SOURCE_REPO)
    except GitHubError as e:
        if e.status in (401, 403, 404):
            return False
        raise ImproveError(_c(f"Không hỏi được GitHub về {SOURCE_REPO}: {e}. Thử lại sau ít phút.",
                              f"Could not ask GitHub about {SOURCE_REPO}: {e}. Try again in a few minutes."))
    except github_repos.RepoError:
        return False
    except Exception as e:  # noqa: BLE001 - network and the like
        raise ImproveError(_c(f"Không hỏi được GitHub về {SOURCE_REPO} ({type(e).__name__}). Thử lại sau ít phút.",
                              f"Could not ask GitHub about {SOURCE_REPO} ({type(e).__name__}). Try again in a few "
                              "minutes."))
    return (meta.get("permissions") or {}).get("push") is True


REPORT_URL_MAX = 7500      # GitHub answers 414 a little above 8 KB of URL; keep room for the browser
_REPORT_CUT = "\n\n_(... cut to fit the link, details on request)_"


def report_url(title: str, body: str, version: str = "") -> str:
    """A link that opens a new issue on the official repo, title and body filled in. Nothing is sent: the person reads
    it and presses Submit themselves (owner, 20/11/2026: the fix proposal of an install that cannot push)."""
    from urllib.parse import quote
    title = " ".join(str(title or "").split())[:200]
    if not title:
        raise ImproveError(_c("Thiếu title: một dòng nói lỗi hay đề xuất là gì.",
                              "Missing title: one line saying what the bug or proposal is."))
    body = str(body or "").strip()
    if version:
        body += f"\n\n---\nJavis v{version}"
    base = f"https://github.com/{SOURCE_REPO}/issues/new?title={quote(title, safe='')}&body="
    room = REPORT_URL_MAX - len(base)
    if len(quote(body, safe="")) <= room:
        return base + quote(body, safe="")
    lo, hi = 0, len(body)
    while lo < hi:                                # longest prefix whose encoded form fits next to the cut note
        mid = (lo + hi + 1) // 2
        if len(quote(body[:mid] + _REPORT_CUT, safe="")) <= room:
            lo = mid
        else:
            hi = mid - 1
    return base + quote(body[:lo].rstrip() + _REPORT_CUT, safe="")


def attach_source(sid: str, brain_root: str) -> dict:
    """Attach the official repo to this chat next to whatever it already has. Returns its row (worktree, branch).

    Only on an install that can push to it (`can_write_source`). Anywhere else nothing is cloned and the answer is
    `{"report": True}`: the model writes a bug report with `report_url` instead of editing code it can never send."""
    import github_repos
    if not sid:
        raise ImproveError(_c("Chỉ gắn được trong một khung chat web (chưa rõ mã phiên).",
                              "Only inside a web chat (no session id)."))
    if not can_write_source():
        return {"repo": SOURCE_REPO, "report": True, "attached": None}
    have = [r["full_name"] for r in github_repos.session_repos(sid, brain_root) if r.get("full_name")]
    if SOURCE_REPO.lower() not in {h.lower() for h in have}:
        try:
            github_repos.attach(sid, brain_root, brain_root, have + [SOURCE_REPO])
        except github_repos.RepoError as e:
            raise ImproveError(str(e))
    got = source_status(sid, brain_root)
    if not got["attached"]:
        raise ImproveError(_c("Gắn repository không thành công.", "Attaching the repository did not work."))
    return got


# ── versions (read only) ────────────────────────────────────────────────────────────────────────────────────────────
# Owner, 23/11/2026: "anh không muốn tự update mà người dùng phải vào trang update để cập nhật lên". Until then
# `javis_improve op=update` started the Update button's path by itself after the turn, so a merged fix put the machine
# on the new release with nobody pressing anything. Now this module only READS the versions; the update itself is the
# owner's press of the button on the Update page (Settings, Updates).

def wire(versions: Optional[Callable[[], Awaitable[tuple]]] = None) -> None:
    """main.py: `versions()` = (current, latest)."""
    if versions is not None:
        _UPDATE["versions"] = versions


def _newer(a: str, b: str) -> bool:
    def key(v):
        return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:3]) or (0,)
    return key(a) > key(b)


async def versions() -> tuple:
    fn = _UPDATE.get("versions")
    if fn is None:
        return "", ""
    try:
        cur, latest = await fn()
        return str(cur or ""), str(latest or "")
    except Exception:  # noqa: BLE001
        return "", ""


async def update_hint() -> dict:
    """What `op=update` answers: the versions and whether a newer release exists. Starts nothing."""
    cur, latest = await versions()
    return {"current": cur, "latest": latest, "newer": bool(cur and latest and _newer(latest, cur))}
