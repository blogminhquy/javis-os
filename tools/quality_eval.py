"""Quality eval: do Javis's answers stay as good after a token saving? (2026-11-17)

    python tools/quality_eval.py run                         # sample set, profile of the Javis CLI
    python tools/quality_eval.py run --set my_set.json --repeat 2 --out before.json
    python tools/quality_eval.py compare before.json after.json   # exit 1 when a task got worse

Owner, 17/11/2026: "anh cần vừa tiết kiệm và vừa không ảnh hưởng đến chất lượng kết quả". Tokens are measured in many
places; this measures the other half. It sends each task of a set to a RUNNING Javis through the same /chat endpoint
the CLI uses (token from `javis login`, or JAVIS_URL + JAVIS_TOKEN), in a fresh session per task, and records:

  - the answer, and how many of the task's key facts it covers (`must`: each item is a list of accepted spellings,
    matched without accents and case, like Graphify's key-fact coverage);
  - anything it must not contain (`must_not`, e.g. the em dash the owner banned);
  - seconds, and the tokens the turn used when Javis runs on this machine (read from the lines usage-events.jsonl
    gained during the task; background jobs running at the same moment are counted too, so run it on a quiet machine).

Run the set before a change and after it (or with a saving switched off and on: JAVIS_RESULT_REPEAT_REFS=0, restart),
then `compare`: per task the token change and the coverage change, and a WORSE flag when coverage drops or a banned
string appears. Models are not deterministic, so --repeat 2 or 3 averages out the noise. A side by side .txt of the
answers is written next to the second file, to read on a phone.

The sample set (tools/eval/sample_set.json) only holds generic tasks. The tasks that matter are the owner's own: copy
it, put in real questions with the facts a good answer must contain.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import unicodedata
import uuid
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SET = ROOT / "tools" / "eval" / "sample_set.json"


def fold(text: str) -> str:
    """Lowercase without accents ("Đơn hàng" -> "don hang"), for lenient matching."""
    text = unicodedata.normalize("NFD", str(text or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()


def score(answer: str, must: list, must_not: list) -> dict:
    folded = fold(answer)
    missing = []
    for group in must or []:
        options = group if isinstance(group, list) else [group]
        if not any(fold(opt) in folded for opt in options):
            missing.append(options[0])
    violations = [s for s in (must_not or []) if s and s in answer]
    total = len(must or [])
    return {"coverage": round((total - len(missing)) / total, 3) if total else 1.0,
            "missing": missing, "violations": violations}


def profile(url: str, token: str) -> tuple[str, str]:
    """URL and token: flags, else JAVIS_URL/JAVIS_TOKEN, else the Javis CLI's default profile."""
    if not (url and token):
        try:
            d = json.loads((Path.home() / ".javis" / "config.json").read_text(encoding="utf-8"))
            p = (d.get("profiles") or {}).get(os.getenv("JAVIS_PROFILE") or d.get("default") or "") or {}
        except (OSError, ValueError):
            p = {}
        url = url or os.getenv("JAVIS_URL") or p.get("url") or ""
        token = token or os.getenv("JAVIS_TOKEN") or p.get("token") or ""
    return url.rstrip("/"), token


class UsageWindow:
    """Tokens written to usage-events.jsonl between `start()` and `stop()` (Javis on this machine only)."""

    def __init__(self, state_dir: Path | None):
        self.path = (state_dir / "usage-events.jsonl") if state_dir else None
        self.offset = 0

    def start(self) -> None:
        try:
            self.offset = self.path.stat().st_size if self.path and self.path.is_file() else 0
        except OSError:
            self.offset = 0

    def stop(self) -> tuple[int | None, int | None]:
        if not self.path or not self.path.is_file():
            return None, None
        tin = tout = 0
        try:
            with self.path.open("rb") as f:
                f.seek(self.offset)
                for line in f.read().decode("utf-8", "replace").splitlines():
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    tin += int(rec.get("in") or 0)
                    tout += int(rec.get("out") or 0)
        except OSError:
            return None, None
        return tin, tout


def run(a) -> int:
    import httpx   # in Javis's own venv; imported here so `compare` works anywhere

    url, token = profile(a.url, a.token)
    if not url:
        print("No Javis to ask: run `javis login <url>` first, or pass --url and --token.", file=sys.stderr)
        return 2
    spec = json.loads(Path(a.set).read_text(encoding="utf-8"))
    tasks = [t for t in spec.get("tasks") or [] if not a.only or t.get("id") in a.only.split(",")]
    local = (urlparse(url).hostname or "") in ("127.0.0.1", "localhost", "::1")
    state_dir = Path(a.state_dir) if a.state_dir else (
        Path(os.getenv("JAVIS_STATE_DIR") or ROOT / "server") if local else None)
    window = UsageWindow(state_dir)
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    headers = {"User-Agent": "javis-quality-eval"}
    if token:
        headers["Authorization"] = "Bearer " + token
    results = []
    print(f"run {run_id}: {len(tasks)} tasks x {a.repeat} on {url}"
          + ("" if window.path else " (tokens unknown: Javis is not on this machine)"))
    with httpx.Client(timeout=a.timeout) as client:
        for t in tasks:
            tries = []
            for n in range(a.repeat):
                window.start()
                t0 = time.time()
                try:
                    r = client.post(url + "/chat", headers=headers, data={
                        "message": t["ask"], "brain": a.brain, "session": f"eval-{run_id}-{t['id']}-{n}",
                        "host": "quality-eval"})
                    body = r.json() if r.status_code == 200 else {"ok": False, "text": f"HTTP {r.status_code}"}
                except (httpx.HTTPError, ValueError) as e:
                    body = {"ok": False, "text": f"{type(e).__name__}: {e}"}
                seconds = round(time.time() - t0, 1)
                tin, tout = window.stop()
                answer = str(body.get("text") or "")
                s = score(answer, t.get("must"), t.get("must_not"))
                tries.append({"ok": bool(body.get("ok", False)), "seconds": seconds, "tokens_in": tin,
                              "tokens_out": tout, "answer": answer, **s})
            def avg(key):
                vals = [x[key] for x in tries if x[key] is not None]
                return round(statistics.mean(vals), 3) if vals else None
            row = {"id": t["id"], "ask": t["ask"], "tries": tries, "coverage": avg("coverage"),
                   "tokens_in": avg("tokens_in"), "tokens_out": avg("tokens_out"), "seconds": avg("seconds"),
                   "violations": sorted({v for x in tries for v in x["violations"]}),
                   "failed": sum(1 for x in tries if not x["ok"])}
            results.append(row)
            tok = "" if row["tokens_in"] is None else f"  in {int(row['tokens_in']):,} tok"
            print(f"  {t['id']:<22} coverage {row['coverage']:.2f}{tok}  {row['seconds']}s"
                  + (f"  BANNED {row['violations']}" if row["violations"] else "")
                  + (f"  {row['failed']} failed" if row["failed"] else ""))
    out = Path(a.out or f"quality-{run_id}.json")
    out.write_text(json.dumps({"run": run_id, "url": url, "set": str(a.set), "repeat": a.repeat,
                               "tasks": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {out}")
    return 0


def compare(a) -> int:
    before = json.loads(Path(a.before).read_text(encoding="utf-8"))
    after = json.loads(Path(a.after).read_text(encoding="utf-8"))
    old = {t["id"]: t for t in before["tasks"]}
    worse = 0
    lines = []
    sum_before = sum_after = 0
    print(f"{'task':<22}{'coverage':>17}{'tokens in':>24}  verdict")
    for t in after["tasks"]:
        b = old.get(t["id"])
        if not b:
            continue
        cov = f"{b['coverage']:.2f} -> {t['coverage']:.2f}"
        tok = ""
        if b.get("tokens_in") is not None and t.get("tokens_in") is not None:
            sum_before += b["tokens_in"]
            sum_after += t["tokens_in"]
            change = (t["tokens_in"] - b["tokens_in"]) * 100 / b["tokens_in"] if b["tokens_in"] else 0.0
            tok = f"{int(b['tokens_in']):,} -> {int(t['tokens_in']):,} ({change:+.0f}%)"
        bad = t["coverage"] < b["coverage"] - 1e-9 or bool(set(t["violations"]) - set(b["violations"]))
        worse += bad
        print(f"{t['id']:<22}{cov:>17}{tok:>24}  {'WORSE' if bad else 'ok'}")
        lines.append(f"### {t['id']}  ({'WORSE' if bad else 'ok'})\n{t['ask']}\n\n--- before ---\n"
                     f"{b['tries'][0]['answer']}\n\n--- after ---\n{t['tries'][0]['answer']}\n")
    if sum_before:
        print(f"\ntotal input tokens: {int(sum_before):,} -> {int(sum_after):,} "
              f"({(sum_after - sum_before) * 100 / sum_before:+.1f}%)")
    print(f"tasks worse: {worse}")
    side = Path(a.after).with_suffix(".compare.txt")
    side.write_text("\n".join(lines), encoding="utf-8")
    print(f"answers side by side: {side}")
    return 1 if worse else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="send every task of a set to a running Javis")
    r.add_argument("--set", default=str(DEFAULT_SET))
    r.add_argument("--only", default="", help="comma-separated task ids")
    r.add_argument("--repeat", type=int, default=1)
    r.add_argument("--brain", default=os.getenv("JAVIS_BRAIN", ""))
    r.add_argument("--url", default="")
    r.add_argument("--token", default="")
    r.add_argument("--state-dir", default="", help="Javis state folder, to read token usage (local Javis only)")
    r.add_argument("--timeout", type=float, default=900.0)
    r.add_argument("--out", default="")
    c = sub.add_parser("compare", help="compare two runs of the same set")
    c.add_argument("before")
    c.add_argument("after")
    a = ap.parse_args(argv)
    return run(a) if a.cmd == "run" else compare(a)


if __name__ == "__main__":
    raise SystemExit(main())
