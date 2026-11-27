"""Claude Code input tokens spent for nothing, by cause: the "waste" block of the Usage page (2026-11-27).

    python tests/run.py usage_waste      (no network)

Pins:
1. usage_waste.classify counts a large cache write after an idle hour as cold, after a model change as a switch, and
   nothing else: not ordinary growth, not the first request, not a sub-agent, not a request outside the period;
2. the real pipeline (Claude transcript -> usage_index.refresh -> summary) carries the block, and insights warn when
   cold rebuilds pass the threshold;
3. the Usage page draws the block from i18n keys that exist in both languages.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="javis-waste-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["JAVIS_CLAUDE_PROJECTS_DIR"] = str(_TMP / "claude")
os.environ["JAVIS_CODEX_SESSIONS_DIR"] = str(_TMP / "codex")
(_TMP / "state").mkdir(parents=True, exist_ok=True)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import usage_waste as uw  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def ev(ts, write=0, read=0, inp=10, model="claude-opus-5-5", sid="S", day="2026-07-10", activity="chat"):
    return {"ts": ts, "day": day, "model": model, "session_id": sid, "activity": activity,
            "input": inp, "cache_read": read, "cache_create": write}


H = 3600
T0 = 1_780_000_000

# ---- 1. classify ----
r = uw.classify([
    ev(T0, write=80_000),                                   # first request: never a rebuild
    ev(T0 + 60, write=3_000, read=80_000),                  # ordinary growth
    ev(T0 + 2 * H, write=90_000),                           # idle two hours: cold
    ev(T0 + 2 * H + 30, write=95_000, model="claude-sonnet-5-5"),   # model changed: switch
    ev(T0 + 2 * H + 60, write=1_000, read=95_000, model="claude-sonnet-5-5"),
])
check("first request is not a rebuild, growth is not either", r["cold"]["count"] == 1 and r["model_switch"]["count"] == 1, str(r))
check("cold tokens are the cache write", r["cold"]["tokens"] == 90_000)
check("switch tokens are the cache write", r["model_switch"]["tokens"] == 95_000)
check("every request counts toward the base", r["requests"] == 5)
check("shares are of all input tokens", r["cold"]["pct"] == round(90_000 * 100 / r["input_tokens"], 1), str(r["cold"]))

r = uw.classify([ev(T0, write=80_000), ev(T0 + 2 * H, write=19_999)])
check("a small write after a break is not counted", r["cold"]["count"] == 0)

r = uw.classify([ev(T0, write=80_000), ev(T0 + 30 * 60, write=80_000, activity="subagent"),
                 ev(T0 + 40 * 60, write=0, read=80_000)])
check("sub-agent requests are left out of the sequence", r["requests"] == 2 and r["model_switch"]["count"] == 0)

r = uw.classify([ev(T0, write=80_000, sid="A"), ev(T0 + 2 * H, write=80_000, sid="B")])
check("two conversations never make a rebuild", r["cold"]["count"] == 0)

r = uw.classify([ev(T0, write=80_000, day="2026-07-09"), ev(T0 + 2 * H, write=80_000, day="2026-07-10")],
                "2026-07-10", "2026-07-31")
check("the day before the period serves as the previous request only",
      r["cold"]["count"] == 1 and r["requests"] == 1, str(r))

r = uw.classify([ev(T0, inp=10, read=250_000), ev(T0 + 60, read=100_000)])
check("long contexts are counted by size", r["long"]["count"] == 1 and r["long"]["tokens"] == 250_010)

r = uw.classify([None, {"ts": "x"}, {"session_id": "S", "ts": 0}, ev(T0, write=50_000)])
check("broken rows are skipped", r["requests"] == 1)
check("empty input gives zeros", uw.classify([])["input_tokens"] == 0 and uw.classify([])["cold"]["pct"] == 0.0)

# ---- 2. through usage_index ----
import usage_index as ui  # noqa: E402


def line(ts_iso, rid, write, read=0, model="claude-opus-5-5"):
    return {"type": "assistant", "entrypoint": "sdk-cli", "isSidechain": False, "sessionId": "W1",
            "cwd": "D:/Project/Demo", "timestamp": ts_iso,
            "message": {"id": rid, "model": model,
                        "usage": {"input_tokens": 10, "output_tokens": 50, "cache_read_input_tokens": read,
                                  "cache_creation_input_tokens": write}}}


f = _TMP / "claude" / "D--Project-Demo" / "w1.jsonl"
f.parent.mkdir(parents=True, exist_ok=True)
f.write_text("\n".join(json.dumps(x) for x in [
    line("2026-07-10T01:00:00.000Z", "r1", 120_000),
    line("2026-07-10T01:01:00.000Z", "r2", 2_000, read=120_000),
    line("2026-07-10T05:00:00.000Z", "r3", 122_000),
]) + "\n", encoding="utf-8")
ui.refresh()
s = ui.summary("this_month", today=date(2026, 7, 20))
w = s.get("waste") or {}
check("summary carries the waste block", w.get("requests") == 3, str(w))
check("the cold rebuild is found through the real pipeline", (w.get("cold") or {}).get("count") == 1, str(w))
check("a Codex-only view has an empty block",
      (ui.summary("this_month", provider="codex", today=date(2026, 7, 20)).get("waste") or {}).get("requests") == 0)
codes = [i["code"] for i in ui.insights("this_month", today=date(2026, 7, 20))]
check("insights warn about the cold cache", "cache_cold" in codes, str(codes))
check("insight text has no em or en dash",
      all("\u2014" not in (i["title"] + i["detail"]) and "\u2013" not in (i["title"] + i["detail"])
          for i in ui.insights("this_month", today=date(2026, 7, 20))))

# ---- 3. the page ----
js = (Path(ROOT) / "dashboard" / "usage.js").read_text(encoding="utf-8")
check("usage.js draws the block", "wasteHtml(s.waste)" in js)
for lang in ("vi", "en"):
    d = json.loads((Path(ROOT) / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    keys = ["usage.sec.waste", "usage.waste.cold", "usage.waste.model_switch", "usage.waste.long", "usage.waste.hint",
            "usage.th.nguyen_nhan", "usage.th.lan", "usage.th.ty_le_vao"]
    check(f"{lang}: every key exists", all(k in d for k in keys), str([k for k in keys if k not in d]))
    check(f"{lang}: no em or en dash", all("\u2014" not in d[k] and "\u2013" not in d[k] for k in keys if k in d))

if fails:
    print(f"\nFAIL - {len(fails)} test: {fails}")
    sys.exit(1)
print("\nOK - test_usage_waste")
