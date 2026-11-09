"""Team turns and background work run on Ollama Local without an API key (#1218).

    python tests/run.py ollama_local_team_engine

The bug: `aux_engine.api_key_for("ollama-local")` returned the saved key, which is empty for a plain Ollama at home.
`_ApiAuxEngine.is_available()` read that as "no key", so a Team job failed with "engine ollama-local is not ready"
while the same model answered in a one-to-one chat (the chat path already used the placeholder key "local"). The same
engine class runs background work, whose `query` answered "No API key for ollama-local".

Pinned here, with no Ollama and no network:
  1. api_key_for: endpoint set and no key -> "local"; a saved key wins; no endpoint -> "" (still not ready)
  2. the text-only Team engine on Ollama Local is available and its turn reaches Ollama with the placeholder key
  3. the Team engine with tools (team_engine.build_tools) and a background engine are available too
  4. no endpoint: the Team engine is still refused with a clear reason
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from unittest.mock import patch

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-ollama-team-"))

import aux_engine  # noqa: E402
import engine  # noqa: E402
import team_engine  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


WITH_ENDPOINT = {"model": {"ollama_local_endpoint": "http://127.0.0.1:11434"}}
WITH_KEY = {"model": {"ollama_local_endpoint": "http://127.0.0.1:11434", "ollama_local_key": "proxy-secret"}}
NO_ENDPOINT = {"model": {}}
SPEC = {"provider": "ollama-local", "model": "qwen2.5-coder:14b"}


class _Base:
    """The sandboxed Claude engine a Team turn builds before the swap: only what team_engine reads."""
    system_prompt = "Bạn là trợ lý nhóm."
    allowed_tools = ["javis_nothing"]
    cwd = tempfile.mkdtemp(prefix="javis-ollama-team-cwd-")
    javis_vault = None
    javis_mode = "suggest"
    tag = "team-test"


# 1. the key
check("1. endpoint set, no key -> placeholder", aux_engine.api_key_for("ollama-local", WITH_ENDPOINT) == "local")
check("1. a saved key wins", aux_engine.api_key_for("ollama-local", WITH_KEY) == "proxy-secret")
check("1. no endpoint -> no key", aux_engine.api_key_for("ollama-local", NO_ENDPOINT) == "")

# 2. text-only Team turn
seen = {}


async def fake_stream(api_key, model, messages, reasoning="off"):
    seen["key"], seen["model"] = api_key, model
    yield {"type": "text", "content": "Xong."}


async def _collect(eng):
    return [ev async for ev in eng.query("Tóm tắt việc hôm nay.")]


with patch.object(aux_engine.cfgmod, "read_settings", return_value=WITH_ENDPOINT), \
        patch.object(engine, "ollama_local_stream", fake_stream):
    try:
        eng = team_engine.build(SPEC, _Base(), "team-test", WITH_ENDPOINT)
    except team_engine.TeamEngineUnavailable as e:
        eng = None
        check("2. the Team engine builds", False, e.reason)
    if eng is not None:
        check("2. the Team engine is available", eng.is_available())
        events = asyncio.run(_collect(eng))
        check("2. no 'no API key' error", not any(ev.get("type") == "error" for ev in events), events)
        check("2. the turn answers", any(ev.get("type") == "final" and ev.get("content") == "Xong." for ev in events),
              events)
        check("2. Ollama got the placeholder key and the chosen model",
              seen.get("key") == "local" and seen.get("model") == "qwen2.5-coder:14b", seen)

# 3. Team turn with tools, and a background engine
with patch.object(aux_engine.cfgmod, "read_settings", return_value=WITH_ENDPOINT):
    try:
        tools_eng = team_engine.build_tools(SPEC, _Base(), "team-test", WITH_ENDPOINT, mode="auto")
        check("3. the Team engine with tools is available", tools_eng.is_available())
    except team_engine.TeamEngineUnavailable as e:
        check("3. the Team engine with tools builds", False, e.reason)
    bg = aux_engine._build_api(SPEC, _Base(), "auto", "reminder:test")
    check("3. a background engine on Ollama Local is available", bg.is_available())

# 4. no endpoint: refused, with the reason
with patch.object(aux_engine.cfgmod, "read_settings", return_value=NO_ENDPOINT):
    try:
        team_engine.build(SPEC, _Base(), "team-test", NO_ENDPOINT)
        check("4. no endpoint is refused", False)
    except team_engine.TeamEngineUnavailable as e:
        check("4. no endpoint is refused with the Models page hint", "Ollama" in e.reason, e.reason)

if fails:
    raise SystemExit(f"{len(fails)} check(s) failed: {fails}")
print("all ok")
