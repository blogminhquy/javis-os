"""Javis health scan from outside the server (0.199.0). Read-only, no model calls.

Works while the server is down, so it is the first thing to run when "Javis stopped doing my jobs".

    python tools/sentinel.py                         # human-readable report
    python tools/sentinel.py --json                  # one JSON document
    python tools/sentinel.py --state-dir DIR --brains-dir DIR --hours 48
    python tools/sentinel.py --out ~/javis-health    # also write report.json and report.md there

--out refuses a folder inside the state dir: the scan never writes where Javis keeps its data.
Exit code is always 0; read the report, not the exit code.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import sentinel  # noqa: E402


def _brains(brains_dir: Path) -> list:
    if not brains_dir.is_dir():
        return []
    return [p for p in sorted(brains_dir.iterdir()) if p.is_dir() and (p / "Javis").is_dir()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only Javis health scan")
    ap.add_argument("--state-dir", default=os.getenv("JAVIS_STATE_DIR", str(ROOT / "server")))
    ap.add_argument("--brains-dir", default=os.getenv("BRAINS_DIR", str(ROOT / "brains")))
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    state = Path(a.state_dir).expanduser().resolve()
    report = sentinel.scan(state, _brains(Path(a.brains_dir).expanduser()), window_s=a.hours * 3600)
    if a.out:
        out = Path(a.out).expanduser().resolve()
        if out == state or state in out.parents:
            print("--out must be outside the state dir", file=sys.stderr)
            return 0
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / "report.md").write_text(sentinel.to_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1) if a.json else sentinel.to_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
