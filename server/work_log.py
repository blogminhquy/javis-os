"""Append-only log of finished background work, one file per brain (0.428.0).

The Tasks page stats (task_stats.py) count what Javis did over any date range. Kanban jobs keep their own events and
loops keep a markdown log, but a reminder keeps only its last run and a page watch only counters, so each finished
reminder run and each page-watch alert adds one JSON line here:

    <brain>/Javis/work-log.jsonl   {"ts": epoch, "kind": "reminder"|"watch", "ref": id, "title": "...",
                                    "status": "ok"|"fail"|"retry"|"stopped", "seconds": n, "mode": "task"|"notify"|...}

Writing never raises (stats must not break the work they count). The file is cut back to its last KEEP lines when it
grows past MAX_BYTES.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

FILE = "work-log.jsonl"
MAX_BYTES = 4_000_000
KEEP = 20000


def path(brain_root: str) -> Path:
    return Path(brain_root) / "Javis" / FILE


def append(brain_root: str, kind: str, ref: str, title: str, status: str, seconds: float = 0, mode: str = "",
           ts: float = 0) -> None:
    try:
        p = path(brain_root)
        p.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": round(float(ts or time.time()), 1), "kind": kind, "ref": str(ref or "")[:80],
               "title": str(title or "")[:160], "status": status, "seconds": round(float(seconds or 0), 1)}
        if mode:
            row["mode"] = mode
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if p.stat().st_size > MAX_BYTES:
            lines = p.read_text(encoding="utf-8").splitlines()[-KEEP:]
            tmp = p.with_suffix(".tmp")
            tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
            tmp.replace(p)
    except Exception as e:  # noqa: BLE001
        print(f"[work-log] not written: {type(e).__name__}: {e}")


def read(brain_root: str, since: float = 0, until: float = float("inf")) -> list:
    out = []
    try:
        with path(brain_root).open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                ts = float(row.get("ts") or 0)
                if since <= ts < until:
                    out.append(row)
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001
        print(f"[work-log] unreadable: {type(e).__name__}: {e}")
    return out
