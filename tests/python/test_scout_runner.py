"""The host side of javis_scout: `main._scout_run` builds a READ-ONLY run on the background model.

    python tests/run.py scout_runner      (no network, no engine is spawned)

scout.py refuses nesting and caps the run; what makes a scout unable to write or act is how the
host builds its engine. This file pins that construction: a read-only allowlist, the hub at the
`suggest` level for the scout's own brain, the owner's background engine with the scout's tag,
its own short system prompt, a wall-clock limit, and a clean answer when the engine is not ready.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-scout-runner-")

import main          # noqa: E402
import mcp_hub       # noqa: E402
import scout         # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


_seen = {}


class _CLI:
    def __init__(self, **kw):
        _seen["engine_kw"] = kw
        self.max_wall_s = None
        self.ready = True

    def is_available(self):
        return self.ready

    async def query(self, prompt):
        _seen["prompt"] = prompt
        yield {"type": "tool_call", "name": "x"}
        yield {"type": "usage", "input": 1200, "output": 80}
        yield {"type": "final", "content": "FINDINGS: 42", "tokens_in": 300, "tokens_out": 20}


def _fake_apply(cli, mode="full", brain=None):
    _seen["hub_mode"], _seen["hub_brain"] = mode, brain
    return cli


def _fake_swap(cli, mode=None, tag=None):
    _seen["swap_mode"], _seen["swap_tag"] = mode, tag
    return cli


main.claude_engine = lambda **kw: _CLI(**kw)
main._apply_mcp = _fake_apply
main._aux_swap = _fake_swap
main._loop_mcp_allow = lambda: ["mcp__javis"]
BRAIN = tempfile.mkdtemp(prefix="scout-runner-brain-")

check("the host handed its runner to scout.py at import", scout._runner is main._scout_run and scout.available())
out = asyncio.run(main._scout_run(BRAIN, "PROMPT", "scout-quick", 123))
kw = _seen["engine_kw"]
check("the report and the token count come back", out["text"] == "FINDINGS: 42" and out["usage"] == {"input": 1500, "output": 100}, out)
check("only read tools and the hub are allowed", kw["allowed_tools"] == ["Read", "Glob", "Grep", "LS", "mcp__javis"], kw["allowed_tools"])
check("no write or shell tool is in the allowlist",
      not {"Write", "Edit", "Bash", "WebFetch", "Task"} & set(kw["allowed_tools"]))
check("the scout has its own short prompt, not the brain's", kw["system_prompt"] == scout.SYSTEM_PROMPT and len(kw["system_prompt"]) < 2500)
check("it works in the scout's own brain", kw["cwd"] == BRAIN and _seen["hub_brain"] == BRAIN)
check("the hub enforces the read-only level", _seen["hub_mode"] == "suggest")
check("the owner's background engine is used, with the scout's tag", _seen["swap_mode"] == "suggest" and _seen["swap_tag"] == "scout-quick" and kw["tag"] == "scout-quick")
check("the prompt is passed through untouched", _seen["prompt"] == "PROMPT")


class _Down(_CLI):
    def is_available(self):
        return False

main.claude_engine = lambda **kw: _Down(**kw)
out = asyncio.run(main._scout_run(BRAIN, "PROMPT", "scout", 60))
check("an engine that is not ready answers cleanly, nothing runs", out["text"] == "" and "not ready" in out["error"], out)

# ---- the Usage page line built from the hub's own meter ----
_real_stats = mcp_hub.result_size_stats
check("nothing measured: no line on the Usage page", main._tool_result_insight() is None)
mcp_hub.result_size_stats = lambda days=7, top=10: {
    "calls": 40, "raw_chars": 2_400_000, "sent_chars": 60_000, "saved_chars": 2_340_000, "saved_pct": 97.5,
    "saved_tokens_est": 780_000, "stored": 12, "over_cap": 20, "shaping_on": True,
    "by_tool": [{"source": "POS", "tool": "pos_order", "calls": 20, "raw_chars": 2_000_000, "sent_chars": 40_000}]}
item = main._tool_result_insight()
check("with savings: one info line with the share kept out and the heaviest tool",
      item and item["level"] == "info" and "97.5%" in item["title"] and "POS pos_order" in item["detail"], item)
mcp_hub.result_size_stats = lambda days=7, top=10: {
    "calls": 40, "raw_chars": 2_400_000, "sent_chars": 2_400_000, "saved_chars": 0, "saved_pct": 0.0,
    "saved_tokens_est": 0, "stored": 0, "over_cap": 20, "shaping_on": False,
    "by_tool": [{"source": "POS", "tool": "pos_order", "calls": 20, "raw_chars": 2_000_000, "sent_chars": 2_000_000}]}
item = main._tool_result_insight()
check("switched off with large results: a warning that says so", item and item["level"] == "warn" and "20" in item["detail"], item)
mcp_hub.result_size_stats = _real_stats
from fastapi.testclient import TestClient  # noqa: E402
os.environ.setdefault("JAVIS_REQUIRE_LOGIN", "0")
resp = TestClient(main.app).get("/connect/result-stats?days=3")
check("the stats endpoint answers", resp.status_code in (200, 401, 403) and (resp.status_code != 200 or "saved_pct" in resp.json()),
      (resp.status_code, resp.text[:120]))

if _fails:
    raise SystemExit(f"{len(_fails)} FAIL: " + "; ".join(_fails))
print("All green")
