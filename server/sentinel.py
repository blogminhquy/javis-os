"""sentinel.py - a read-only health scan that groups failures into issues (0.199.0).

Idea borrowed from OpenMausBot's Sentinel. Failures in Javis are spread over five stores: blocked
Kanban jobs, reminders with an error, loops that paused themselves, webhooks whose last run failed,
and open incidents. Each shows only on its own card. This scan reads all of them, groups failures
that share a cause into one issue (the same error text with numbers and ids masked), and sorts by
how often they happened, so "the Zalo token expired" is one line that failed 14 times instead of
14 cards on three pages.

Plain code, no model calls, read-only everywhere: SQLite is opened with mode=ro, JSON files are
only read. It runs inside the server (GET /sentinel/scan) or out of process
(`python tools/sentinel.py`), so it still works when the server is down. Every input is an explicit
argument; the module imports nothing from the server.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Iterable, List, Optional

WINDOW_S = 24 * 3600
EXAMPLES_PER_ISSUE = 3
SIGNATURE_CHARS = 140

_ID_RE = re.compile(r"\b(?:[0-9a-f]{8,}|[A-Za-z]+_[0-9a-f]{6,})\b", re.I)
_NUM_RE = re.compile(r"\d+")
_SPACE_RE = re.compile(r"\s+")


def signature(error: str) -> str:
    """The cause of a failure with the parts that differ between runs masked: ids, numbers, times."""
    s = str(error or "").strip().splitlines()[0] if str(error or "").strip() else ""
    s = _ID_RE.sub("*", s)
    s = _NUM_RE.sub("#", s)
    s = _SPACE_RE.sub(" ", s).strip().lower()
    return s[:SIGNATURE_CHARS] or "(no error text)"


def _read_json(path: Path) -> Optional[object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def kanban_failures(state_dir: Path, since: float) -> List[dict]:
    db = Path(state_dir) / "kanban.sqlite3"
    if not db.exists():
        return []
    out = []
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
        try:
            rows = con.execute(
                "SELECT id, brain_root, title, block_kind, block_reason, updated_at FROM tasks "
                "WHERE status IN ('blocked', 'failed') AND updated_at >= ? "
                "AND block_kind NOT IN ('needs_input', 'limit')", (since,)).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    for tid, brain, title, kind, reason, at in rows:
        out.append({"source": "kanban", "ref": tid, "brain": brain, "title": title,
                    "error": reason or kind or "", "at": float(at or 0)})
    return out


def reminder_failures(brains: Iterable[Path], since: float) -> List[dict]:
    out = []
    for b in brains:
        d = _read_json(Path(b) / "Javis" / "reminders.json")
        for r in (d or {}).get("reminders", []) if isinstance(d, dict) else []:
            if r.get("error") and float(r.get("fired_at") or 0) >= since:
                out.append({"source": "reminder", "ref": r.get("id"), "brain": str(b),
                            "title": r.get("label") or str(r.get("text") or "")[:80],
                            "error": r.get("error"), "at": float(r.get("fired_at") or 0)})
    return out


def loop_failures(brains: Iterable[Path]) -> List[dict]:
    out = []
    for b in brains:
        d = _read_json(Path(b) / "Javis" / "loop-state.json")
        if not isinstance(d, dict):
            continue
        for slug, st in d.items():
            if not isinstance(st, dict):
                continue
            if st.get("auto_paused_reason") or int(st.get("fail_streak") or 0) > 0:
                out.append({"source": "loop", "ref": slug, "brain": str(b), "title": slug,
                            "error": st.get("auto_paused_reason") or st.get("last_summary") or "loop failed",
                            "at": float(st.get("last_run") or 0)})
    return out


def webhook_failures(state_dir: Path, since: float) -> List[dict]:
    d = _read_json(Path(state_dir) / "webhooks.json")
    out = []
    for h in (d or {}).get("hooks", []) if isinstance(d, dict) else []:
        for r in h.get("history") or []:
            if r.get("status") == "failed" and float(r.get("at") or 0) >= since:
                out.append({"source": "webhook", "ref": h.get("id"), "brain": h.get("brain", ""),
                            "title": h.get("name", ""), "error": r.get("result", ""), "at": float(r.get("at") or 0)})
    return out


def open_incidents(state_dir: Path) -> List[dict]:
    d = _read_json(Path(state_dir) / "incidents.json")
    items = (d or {}).get("incidents", []) if isinstance(d, dict) else []
    return [i for i in items if i.get("status") in ("open", "retrying", "needs_you")]


def scan(state_dir: Path, brains: Iterable[Path], now: Optional[float] = None,
         window_s: float = WINDOW_S) -> dict:
    """One scan. Returns {"scanned_at", "window_h", "issues": [...], "counts": {...}, "incidents": n}."""
    now = time.time() if now is None else float(now)
    since = now - window_s
    brains = [Path(b) for b in brains]
    failures = (kanban_failures(state_dir, since) + reminder_failures(brains, since)
                + loop_failures(brains) + webhook_failures(state_dir, since))
    groups: dict = {}
    for f in failures:
        g = groups.setdefault(signature(f["error"]), {"signature": signature(f["error"]), "count": 0,
                                                      "sources": set(), "examples": [], "first_at": f["at"],
                                                      "last_at": f["at"], "error": str(f["error"])[:300]})
        g["count"] += 1
        g["sources"].add(f["source"])
        g["first_at"] = min(g["first_at"], f["at"])
        g["last_at"] = max(g["last_at"], f["at"])
        if len(g["examples"]) < EXAMPLES_PER_ISSUE:
            g["examples"].append({k: f[k] for k in ("source", "ref", "brain", "title", "at")})
    issues = sorted(groups.values(), key=lambda g: (-g["count"], -g["last_at"]))
    for g in issues:
        g["sources"] = sorted(g["sources"])
    counts: dict = {}
    for f in failures:
        counts[f["source"]] = counts.get(f["source"], 0) + 1
    return {"scanned_at": now, "window_h": round(window_s / 3600, 1), "issues": issues,
            "counts": counts, "incidents": len(open_incidents(state_dir))}


def to_markdown(report: dict) -> str:
    lines = [f"# Javis health scan ({time.strftime('%Y-%m-%d %H:%M', time.localtime(report['scanned_at']))})", ""]
    if not report["issues"]:
        lines.append(f"No failures in the last {report['window_h']} hours.")
    for g in report["issues"]:
        lines.append(f"- **{g['count']}x** [{', '.join(g['sources'])}] {g['error']}")
        for e in g["examples"]:
            lines.append(f"  - {e['source']} {e['ref']}: {e['title']}")
    if report.get("incidents"):
        lines += ["", f"Open incidents: {report['incidents']}"]
    return "\n".join(lines) + "\n"
