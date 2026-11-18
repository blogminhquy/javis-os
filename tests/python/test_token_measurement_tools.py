"""The two measuring tools behind the token savings stay honest (2026-11-17).

    python tests/run.py token_measurement_tools     (no network: fake Javis on localhost)

tools/token_bench.py and tools/quality_eval.py are how the owner sees "before and after" for a saving. A meter that
quietly breaks reports a saving that is not there, so:
  1. quality_eval scores key facts without accents or case, catches banned strings, sums the tokens a task added to
     usage-events.jsonl, and `compare` flags a task whose coverage dropped (exit 1) and passes an equal one (exit 0).
  2. token_bench's loop scenarios really run the engine: re-reading saves characters, and the scenario whose data
     changes between two identical calls hands out no reference at all.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import importlib.util
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

fails = []


def check(name, ok, extra=None):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok or extra is None else f"  [{extra}]"))
    if not ok:
        fails.append(name)


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


qe = load("quality_eval")

# ───────────────────────── 1. scoring ─────────────────────────
s = qe.score("Đơn hàng tuần này: 12 đơn, doanh thu 3 triệu", [["don hang"], ["doanh thu", "revenue"], ["lợi nhuận"]],
             ["\u2014"])
check("key facts match without accents or case", s["coverage"] == round(2 / 3, 3) and s["missing"] == ["lợi nhuận"], s)
check("a banned string is reported", qe.score("a \u2014 b", [], ["\u2014"])["violations"] == ["\u2014"])
check("no key facts means full coverage", qe.score("anything", [], [])["coverage"] == 1.0)
check("the sample set loads and has no literal banned dash",
      json.loads((ROOT / "tools/eval/sample_set.json").read_text(encoding="utf-8"))["tasks"]
      and "\u2014" not in (ROOT / "tools/eval/sample_set.json").read_text(encoding="utf-8"))

# ───────────────────────── 2. a run against a fake Javis ─────────────────────────
STATE = Path(tempfile.mkdtemp(prefix="javis-qe-"))
EVENTS = STATE / "usage-events.jsonl"
EVENTS.write_text(json.dumps({"in": 999, "out": 9}) + "\n", encoding="utf-8")   # older activity: not counted
ANSWERS = {"good": "Doanh thu tuần này 3 triệu, 12 đơn hàng.", "bad": "Mình chưa rõ."}
MODE = {"answer": "good"}
SEEN = []


class _Javis(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode()).items()}
        SEEN.append((self.path, self.headers.get("Authorization"), form))
        with EVENTS.open("a", encoding="utf-8") as f:   # the turn's own usage, as Javis writes it
            f.write(json.dumps({"in": 1200, "out": 80}) + "\n")
        raw = json.dumps({"ok": True, "text": ANSWERS[MODE["answer"]], "session": form.get("session")}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


srv = ThreadingHTTPServer(("127.0.0.1", 0), _Javis)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}"
SET = STATE / "set.json"
SET.write_text(json.dumps({"tasks": [{"id": "sales", "ask": "Tuần này bán sao?", "must": [["doanh thu"], ["don"]],
                                      "must_not": ["\u2014"]}]}), encoding="utf-8")
before, after = STATE / "before.json", STATE / "after.json"
code = qe.main(["run", "--set", str(SET), "--url", url, "--token", "jvs_test", "--state-dir", str(STATE),
                "--repeat", "2", "--out", str(before)])
b = json.loads(before.read_text(encoding="utf-8"))["tasks"][0]
check("run: asks /chat with the token, one fresh session per try",
      code == 0 and [x[0] for x in SEEN] == ["/chat", "/chat"] and SEEN[0][1] == "Bearer jvs_test"
      and SEEN[0][2]["session"] != SEEN[1][2]["session"], SEEN)
check("run: coverage of a good answer is full", b["coverage"] == 1.0, b)
check("run: tokens are only those the task added", b["tokens_in"] == 1200 and b["tokens_out"] == 80, b)

MODE["answer"] = "bad"
qe.main(["run", "--set", str(SET), "--url", url, "--token", "jvs_test", "--state-dir", str(STATE),
         "--out", str(after)])
check("compare: a task whose coverage dropped is WORSE (exit 1)", qe.main(["compare", str(before), str(after)]) == 1)
check("compare: an unchanged run passes (exit 0)", qe.main(["compare", str(before), str(before)]) == 0)
side = after.with_suffix(".compare.txt")
check("compare: answers side by side for reading", side.is_file() and "Mình chưa rõ." in side.read_text(encoding="utf-8"))
srv.shutdown()

# ───────────────────────── 3. token_bench loop scenarios ─────────────────────────
tb = load("token_bench")
rows = {r["scenario"]: r for r in tb._run_loop_scenarios()}
check("bench: re-reading a document saves characters", rows["reread"]["saved_pct"] > 10 and
      rows["reread"]["references"] == 1, rows["reread"])
check("bench: changed data hands out no reference", rows["changed_data"]["references"] == 0, rows["changed_data"])
check("bench: indented plugin JSON gets compact", rows["plugin_json"]["saved_pct"] > 10, rows["plugin_json"])

# ───────────────────────── 4. section_ab_eval grading ─────────────────────────
ab = load("section_ab_eval")
loop_case = next(c for c in ab.CASES if c["id"] == "loop")
for note, ans in [("yaml", "javis_schedule op: create\nmode: full\nenabled: false"),
                  ("json", 'javis_schedule({"op": "create", "mode": "full", "enabled": false})'),
                  ("kwargs", 'javis_schedule(op = "create", mode = "full", enabled = false)')]:
    check(f"ab grade: a {note} tool call covers the loop facts", ab.grade(ans, loop_case)["coverage"] == 1.0,
          ab.grade(ans, loop_case))
agent_case = next(c for c in ab.CASES if c["id"] == "agent")
good = "File `agents/x.md` (not `Javis/agents/`)\ntype: agent\nslug: x\nrole: r\ntags: [a]"
check("ab grade: warning against the old folder is not a fault", ab.grade(good, agent_case)["violations"] == [])
check("ab grade: writing into the old folder is", ab.grade(good.replace("`agents/x.md`", "`Javis/agents/x.md`"),
                                                             agent_case)["violations"] != [])
wf_case = next(c for c in ab.CASES if c["id"] == "workflow")
check("ab grade: a workflow whose new agents lack role: is not full",
      ab.grade("workflows/w.md\ntype: workflow\nstatus: 'off'\nsteps:\nagents/a.md description: x", wf_case)["missing"]
      == ["role:"])
check("ab grade: a banned dash is a fault", ab.grade("x \u2014 y", ab.CASES[0])["violations"] == ["\u2014"])

print()
if fails:
    print(f"{len(fails)} FAIL")
    raise SystemExit(1)
print("all ok")
