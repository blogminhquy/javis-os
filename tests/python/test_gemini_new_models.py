"""Gemini 4 and the newer Gemini 3 models on the Gemini API brain (owner's report, 15/11/2026).

Two silent gaps once Gemini 4 (Hydrogen, Argon, Carbon) arrived:

1. The Effort level never reached Gemini 4. `engine._gemini_is_reasoning` listed versions by hand ("2.5",
   "gemini-3"), so a `gemini-4-*` id read as a model that cannot think and no `reasoning_effort` was sent.
2. The cost estimate fell to the bare "gemini" price row (0.30 USD per 1M input tokens), so Gemini 4 read
   several times cheaper than it is, while Gemini 3.5 Flash-Lite was priced as Gemini 3 Pro.

    python tests/run.py gemini_new_models

No network: engine.httpx.AsyncClient is replaced by a fake that records every request.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ["JAVIS_API_STREAM_TOOLS"] = "0"   # the tool loop on its non-stream path: one POST per round
os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-gemini-new-"))
import engine  # noqa: E402
import usage_parsers  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


# 1. Which Gemini models take reasoning_effort.
THINKS = ["gemini-4-hydrogen", "gemini-4-argon", "gemini-4-carbon", "gemini-3.5-flash-lite", "gemini-3.1-pro",
          "gemini-3.1-pro-preview", "gemini-3.8-flash", "gemini-3-pro", "gemini-2.5-flash", "gemini-2.5-pro",
          "gemini-2.5-flash-lite", "models/gemini-4-argon", "google/gemini-4-hydrogen", "gemini-5-neon",
          "gemini-10-xenon", "gemini-flash-latest", "gemini-2.0-flash-thinking-exp", "GEMINI-4-ARGON"]
NO_THINK = ["gemini-2.0-flash", "gemini-2.0-flash-001", "gemini-1.5-pro", "gemini-1.5-flash-8b",
            "gemma-3-27b-it", "learnlm-2.0-flash-experimental", "", None]
for mid in THINKS:
    check("thinks, so Effort is sent: %s" % mid, engine._gemini_is_reasoning(mid))
for mid in NO_THINK:
    check("no thinking, so no Effort (a 400 otherwise): %r" % (mid,), not engine._gemini_is_reasoning(mid))


# 2. The real request: Gemini 4 carries the Effort level, Gemini 2.0 does not.
class _Resp:
    status_code = 200
    headers = {}
    text = ""

    def json(self):
        return {"choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": {}}


class _Client:
    sent = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None, **k):
        _Client.sent.append(dict(json or {}))
        return _Resp()


engine.httpx.AsyncClient = _Client


def sent_payload(model, reasoning):
    _Client.sent = []

    async def go():
        async for _ in engine.gemini_chat_with_mcp("k", model, [{"role": "user", "content": "hi"}],
                                                   reasoning, [], {}):
            pass
    asyncio.run(go())
    return _Client.sent[0] if _Client.sent else {}


p = sent_payload("gemini-4-hydrogen", "low")
check("Gemini 4 Hydrogen, Effort low: reasoning_effort=low is sent", p.get("reasoning_effort") == "low", p)
p = sent_payload("gemini-4-argon", "high")
check("Gemini 4 Argon, Effort high: reasoning_effort=high is sent", p.get("reasoning_effort") == "high", p)
p = sent_payload("gemini-2.0-flash", "high")
check("Gemini 2.0 Flash: no reasoning_effort even with Effort high", "reasoning_effort" not in p, p)
p = sent_payload("gemini-4-argon", "off")
check("Effort off: nothing is sent, as for every provider", "reasoning_effort" not in p, p)


# 3. Price table (usage_pricing.json): the newest models each land on their own row.
prices = usage_parsers.load_prices()


def row(model):
    return prices.get(usage_parsers._khoa_gia(model, prices), {})


check("Gemini 4 Hydrogen: 1.50 in / 7.50 out", row("gemini-4-hydrogen").get("in") == 1.5
      and row("gemini-4-hydrogen").get("out") == 7.5, row("gemini-4-hydrogen"))
for mid in ("gemini-4-argon", "gemini-4-carbon", "google/gemini-4-argon"):
    check("%s: the Gemini 4 row (4 in / 20 out), not the bare gemini row" % mid,
          row(mid).get("in") == 4.0 and row(mid).get("out") == 20.0, row(mid))
check("Gemini 3.5 Flash-Lite: its own price, not Gemini 3 Pro's", row("gemini-3.5-flash-lite").get("in") == 0.3
      and row("gemini-3.5-flash-lite").get("out") == 2.5, row("gemini-3.5-flash-lite"))
check("Gemini 3.1 Pro (and -preview): 2 in / 12 out", row("gemini-3.1-pro-preview").get("in") == 2.0
      and row("gemini-3.1-pro-preview").get("out") == 12.0, row("gemini-3.1-pro-preview"))
check("older rows are untouched: gemini-2.5-flash stays 0.30", row("gemini-2.5-flash").get("in") == 0.3)
cost = usage_parsers.estimate_cost({"model": "gemini-4-hydrogen", "input": 1_000_000, "output": 1_000_000}, prices)
check("estimate_cost: 1M in + 1M out on Hydrogen is 9 USD", abs(cost - 9.0) < 1e-9, cost)


# 4. The input-price table behind the savings estimate (main._GIA_INPUT_1M) agrees with usage_pricing.json.
#    Read from the source, so this file does not pay for importing the whole server.
import ast  # noqa: E402

src = (SERVER / "main.py").read_text(encoding="utf-8")
table = None
for node in ast.parse(src).body:
    if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "_GIA_INPUT_1M" for t in node.targets):
        table = ast.literal_eval(node.value)
check("main._GIA_INPUT_1M found", isinstance(table, dict))
table = table or {}


def input_price(model):
    m = model.lower()
    for key in sorted(table, key=len, reverse=True):
        if key in m:
            return table[key]
    return None


for mid in ("gemini-4-hydrogen", "gemini-4-argon", "gemini-4-carbon", "gemini-3.5-flash-lite", "gemini-3.1-pro"):
    check("savings estimate matches the price table for %s" % mid, input_price(mid) == row(mid).get("in"),
          (input_price(mid), row(mid).get("in")))

if fails:
    print("\nFAIL - test_gemini_new_models: %d" % len(fails))
    sys.exit(1)
print("\nOK - test_gemini_new_models: all pass")
