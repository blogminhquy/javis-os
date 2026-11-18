"""Token bench: how many characters a turn sends to the model, before and after a saving (2026-11-17).

    python tools/token_bench.py                 # all three parts
    python tools/token_bench.py --only loop     # just the tool loop scenarios (no data of this machine)
    python tools/token_bench.py --json out.json # also write the numbers as JSON
    python tools/token_bench.py --state-dir /path/to/state --brains /path/to/brains

Owner, 17/11/2026: save tokens without hurting answers, and show numbers before and after. Three parts:

  1. loop: fixed tool-loop scenarios run through the REAL engine loop (engine.openai_chat_with_mcp) against a fake
     model on localhost, once with the tool-result savings on and once off. Deterministic, no key, no network. The
     number is the sum of every request body the model received in the turn (each round resends the whole
     conversation, so this is what input tokens follow). One scenario has data that changes between two identical
     calls: its saving must stay 0, which shows that no stale result is ever reused.
  2. machine: read-only figures from this machine's own logs, to compare one week with the next: input tokens per
     turn by provider (runtime.db, the turns Javis itself measured) and what the tool result meter kept out of the
     conversation (tool_result_sizes.jsonl). Nothing is written.
  3. skills: how large the installed skills are, and how many are over the 12,000-character limit of the on-demand
     skill path (those fall back to the full skill list and are loaded whole). Input for the next saving step.

The quality side (do answers stay as good?) is tools/quality_eval.py.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import statistics
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "server"
SKILL_ON_DEMAND_LIMIT = 12_000   # lazy_skill_runtime max_body_chars default


# ───────────────────────── 1. tool loop scenarios ─────────────────────────
DOC_A = "Weekly sales report\n" + "".join(f"Order {i:04d}: 2 items, 245.000 VND, shipped\n" for i in range(150))
DOC_B = "Supplier notes\n" + "".join(f"Supplier {i:03d}: pays in 30 days, contact by phone\n" for i in range(90))
ORDERS = {"orders": [{"id": 1000 + i, "customer": "Nguyễn Thị Hồng", "note": "giao buổi chiều",
                      "total": 245000 + i * 1000, "items": [{"sku": "NM-500", "qty": 2}]} for i in range(40)]}


def _scenarios():
    """(name, explanation, tool calls in order: (tool, args)) - the model then answers."""
    return [
        ("reread", "reads report A, then notes B, then report A again, then answers",
         [("read_doc", {"path": "a.md"}), ("read_doc", {"path": "b.md"}), ("read_doc", {"path": "a.md"})]),
        ("reread_twice", "reads report A three times while working through notes B",
         [("read_doc", {"path": "a.md"}), ("read_doc", {"path": "b.md"}), ("read_doc", {"path": "a.md"}),
          ("read_doc", {"path": "b.md"}), ("read_doc", {"path": "a.md"})]),
        ("changed_data", "lists orders, creates one, lists again (the list changed: nothing may be reused)",
         [("list_orders", {}), ("create_order", {"sku": "NM-500"}), ("list_orders", {})]),
        ("plugin_json", "a plugin returns 40 orders as indented, escaped JSON, then two more steps",
         [("plugin_orders", {}), ("read_doc", {"path": "b.md"}), ("read_doc", {"path": "a.md"})]),
    ]


class _Model(BaseHTTPRequestHandler):
    plan: list = []
    seen: list = []
    last: str = ""

    def log_message(self, *a):
        pass

    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
        type(self).seen.append(len(raw))
        type(self).last = raw
        out = json.dumps(type(self).plan.pop(0), ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def _run_loop_scenarios() -> list[dict]:
    os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-token-bench-")
    os.environ["JAVIS_API_STREAM_TOOLS"] = "0"
    os.environ.pop("JAVIS_TOOL_RESULT_SHAPING", None)
    sys.path.insert(0, str(SERVER))
    import engine  # noqa: E402
    import tool_result_reuse  # noqa: E402
    import tool_result_shaper  # noqa: E402

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Model)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    engine.OPENAI_URL = f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"

    state = {"orders": 3}

    async def read_doc(args):
        return DOC_A if args.get("path") == "a.md" else DOC_B

    async def list_orders(args):
        return json.dumps({"orders": [{"id": i, "status": "new"} for i in range(state["orders"])] * 20},
                          ensure_ascii=False)

    async def create_order(args):
        state["orders"] += 1
        return '{"ok":true}'

    async def plugin_orders(args):
        return json.dumps(ORDERS, indent=2)   # what a hand-written plugin often returns

    route = {"read_doc": {"call": read_doc}, "list_orders": {"call": list_orders},
             "create_order": {"call": create_order}, "plugin_orders": {"call": plugin_orders}}
    tools = [{"fn": n, "server": "bench", "name": n, "description": n,
              "schema": {"type": "object", "properties": {}}} for n in route]
    ask = [{"role": "system", "content": "You are a test assistant."},
           {"role": "user", "content": "Tổng hợp giúp tôi."}]

    def plan(calls):
        out = []
        for i, (tool, args) in enumerate(calls):
            out.append({"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [
                {"id": f"c{i}", "type": "function",
                 "function": {"name": tool, "arguments": json.dumps(args)}}]}}]})
        out.append({"choices": [{"message": {"role": "assistant", "content": "Done."}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
        return out

    async def one(calls) -> tuple[int, int]:
        """(characters of every request in the turn, references the model got in place of a repeat)"""
        _Model.plan = plan(calls)
        _Model.seen = []
        state["orders"] = 3
        async for _ in engine.openai_chat_with_mcp("k", "bench", ask, "off", tools, route):
            pass
        last = json.loads(_Model.last)
        refs = sum(1 for m in last["messages"] if m.get("role") == "tool"
                   and str(m.get("content") or "").startswith(tool_result_reuse.REFERENCE_MARK))
        return sum(_Model.seen), refs

    rows = []
    for name, why, calls in _scenarios():
        os.environ["JAVIS_RESULT_REPEAT_REFS"] = "0"
        os.environ["JAVIS_TOOL_RESULT_SHAPING"] = "0"
        tool_result_shaper.settings(force=True)   # the switch is cached for a few seconds
        before, _ = asyncio.run(one(calls))
        os.environ.pop("JAVIS_RESULT_REPEAT_REFS")
        os.environ.pop("JAVIS_TOOL_RESULT_SHAPING")
        tool_result_shaper.settings(force=True)
        after, refs = asyncio.run(one(calls))
        rows.append({"scenario": name, "what": why, "rounds": len(calls) + 1, "chars_before": before,
                     "chars_after": after, "references": refs,
                     "saved_pct": round((before - after) * 100 / before, 1) if before else 0.0})
    srv.shutdown()
    return rows


# ───────────────────────── 2. this machine's own logs (read-only) ─────────────────────────
def _machine(state_dir: Path, days: int) -> dict:
    out: dict = {"state_dir": str(state_dir), "days": days}
    cutoff = time.time() - days * 86400
    db_path = state_dir / "runtime.db"
    if db_path.is_file():
        try:
            db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT provider, actual_input_tokens AS tin, actual_output_tokens AS tout, "
                "estimated_input_tokens AS est FROM runtime_steps "
                "WHERE started_at >= ? AND actual_input_tokens > 0", (cutoff,)).fetchall()
            db.close()
            by: dict = {}
            for r in rows:
                by.setdefault(r["provider"] or "?", []).append(r)
            out["turns"] = {
                prov: {"turns": len(rs),
                       "median_input_tokens": int(statistics.median(r["tin"] for r in rs)),
                       "p90_input_tokens": int(sorted(r["tin"] for r in rs)[int(len(rs) * 0.9) - 1 if len(rs) > 1 else 0]),
                       "total_input_tokens": sum(r["tin"] for r in rs),
                       "median_output_tokens": int(statistics.median(r["tout"] or 0 for r in rs))}
                for prov, rs in sorted(by.items())}
        except sqlite3.Error as e:
            out["turns_error"] = str(e)
    else:
        out["turns_error"] = "runtime.db not found"
    sizes = [state_dir / "tool_result_sizes.jsonl.1", state_dir / "tool_result_sizes.jsonl"]
    kinds: dict = {}
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(cutoff))
    for p in sizes:
        if not p.is_file():
            continue
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if str(rec.get("ts") or "") < since:
                    continue
                k = kinds.setdefault(str(rec.get("shape") or "?"), {"calls": 0, "raw_chars": 0, "sent_chars": 0})
                k["calls"] += 1
                k["raw_chars"] += int(rec.get("raw_chars") or 0)
                k["sent_chars"] += int(rec.get("sent_chars") or 0)
    out["tool_results"] = kinds
    return out


# ───────────────────────── 3. skills ─────────────────────────
def _skills(roots: list[Path]) -> dict:
    sizes = []
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.rglob("SKILL.md"):
            if any(part in {".git", "node_modules", "third_party", ".venv"} for part in p.parts):
                continue
            try:
                sizes.append((len(p.read_text(encoding="utf-8", errors="replace")), str(p)))
            except OSError:
                continue
    sizes.sort(reverse=True)
    over = [s for s in sizes if s[0] > SKILL_ON_DEMAND_LIMIT]
    return {"skills": len(sizes),
            "median_chars": int(statistics.median(s[0] for s in sizes)) if sizes else 0,
            "over_limit": len(over), "limit": SKILL_ON_DEMAND_LIMIT,
            "largest": [{"chars": c, "path": p} for c, p in sizes[:8]]}


def _fmt(n: int) -> str:
    return f"{int(n):,}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", choices=("loop", "machine", "skills"), default="")
    ap.add_argument("--state-dir", default=os.getenv("JAVIS_STATE_DIR") or str(SERVER))
    ap.add_argument("--brains", default=os.getenv("BRAINS_DIR") or str(ROOT / "brains"))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)
    state_dir = Path(a.state_dir)   # read before the loop part points JAVIS_STATE_DIR at a temp folder
    report: dict = {"when": time.strftime("%Y-%m-%d %H:%M")}

    if a.only in ("", "machine"):
        m = report["machine"] = _machine(state_dir, a.days)
        print(f"\n== This machine, last {a.days} days ({m['state_dir']}) ==")
        if m.get("turns"):
            print(f"{'provider':<16}{'turns':>7}{'median in':>12}{'p90 in':>12}{'total in':>14}")
            for prov, t in m["turns"].items():
                print(f"{prov:<16}{t['turns']:>7}{_fmt(t['median_input_tokens']):>12}"
                      f"{_fmt(t['p90_input_tokens']):>12}{_fmt(t['total_input_tokens']):>14}")
        else:
            print("turns: " + str(m.get("turns_error") or "none in this period"))
        if m["tool_results"]:
            print(f"{'tool results':<16}{'calls':>7}{'raw chars':>14}{'sent chars':>14}")
            for kind, k in sorted(m["tool_results"].items()):
                print(f"{kind:<16}{k['calls']:>7}{_fmt(k['raw_chars']):>14}{_fmt(k['sent_chars']):>14}")
        else:
            print("tool results: none logged in this period")

    if a.only in ("", "skills"):
        roots = [ROOT / ".claude" / "skills", Path(a.brains)]
        s = report["skills"] = _skills(roots)
        print(f"\n== Skills ({s['skills']} found) ==")
        print(f"median {_fmt(s['median_chars'])} chars; over the {_fmt(s['limit'])}-char on-demand limit: "
              f"{s['over_limit']}")
        for row in s["largest"]:
            print(f"  {_fmt(row['chars']):>8}  {row['path']}")

    if a.only in ("", "loop"):
        rows = report["loop"] = _run_loop_scenarios()
        print("\n== Tool loop scenarios: characters sent to the model in one turn ==")
        print(f"{'scenario':<14}{'rounds':>7}{'before':>11}{'after':>11}{'saved':>8}{'refs':>6}  what")
        for r in rows:
            print(f"{r['scenario']:<14}{r['rounds']:>7}{_fmt(r['chars_before']):>11}{_fmt(r['chars_after']):>11}"
                  f"{r['saved_pct']:>7}%{r['references']:>6}  {r['what']}")
        print("refs = repeats handed over as a one-line reference. 'changed_data' must show 0: its second list "
              "differs, so it goes out whole; what it saves there is compact JSON only.")

    if a.json:
        Path(a.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwritten: {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
