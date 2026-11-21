"""zalo_get_history: voice messages carry what they said (zalo_voice_history, JumboKiz 21/11/2026).

    python tests/run.py zalo_voice_history

No network: the downloader and the ear are fakes. Locks: a `chat.voice` message gets `transcript`, a text message is
untouched, the same link is heard once (cache), at most MAX_NEW new links per call (newest first), no ear gives
`transcript_error` instead of a guess, a link off Zalo's CDN is never fetched, an internal caller of the hub gets the
raw result while a model gets the transcript.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-zvoice-"))

import zalo_attachments  # noqa: E402
import zalo_voice_history as zv  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


fetched, heard = [], []


async def fake_fetch(info, inbox, max_bytes=0):
    fetched.append(info["url"])
    p = Path(inbox) / info["name"]
    p.write_bytes(b"AAC" + info["url"].encode())
    return str(p), ""


async def fake_hear(data, name):
    heard.append(name)
    return {"ok": True, "text": "chị nói " + name}


zalo_attachments.fetch_file = fake_fetch
zv.HEAR = fake_hear
zv.CACHE_FILE = Path(os.environ["JAVIS_STATE_DIR"]) / "zv.json"


def voice(i, host="voice-aac-dl.zdn.vn"):
    u = f"https://{host}/1/v{i}.aac"
    return {"msgId": str(i), "type": "chat.voice", "text": u, "attachment": {"type": "chat.voice", "url": u}}


def history(msgs):
    return json.dumps({"threadId": "1", "messages": msgs, "sync": {"complete": True}}, ensure_ascii=False)


def run(x):
    return json.loads(asyncio.run(zv.enrich(x)))


out = run(history([{"msgId": "t", "type": "text", "text": "chào em"}, voice(1)]))
check("voice gets transcript", out["messages"][1].get("transcript") == "chị nói v1.aac")
check("text untouched", "transcript" not in out["messages"][0])
check("note on what a transcript is", "sai" in out.get("transcript_note", ""))

n = len(heard)
out = run(history([voice(1)]))
check("same link heard once (cache)", len(heard) == n and out["messages"][0]["transcript"] == "chị nói v1.aac")

heard.clear()
out = run(history([voice(i) for i in range(10, 16)]))
check("at most MAX_NEW new per call", len(heard) == zv.MAX_NEW)
check("newest heard first", out["messages"][-1].get("transcript") and "transcript_error" in out["messages"][0])

fetched.clear()
out = run(history([voice(99, host="evil.example.com")]))
check("link off Zalo CDN never fetched", not fetched and "transcript" not in out["messages"][0])

zv.HEAR = None
out = run(history([voice(200)]))
check("no ear -> transcript_error, no guess",
      "transcript" not in out["messages"][0] and "bộ nghe" in out["messages"][0].get("transcript_error", ""))
zv.HEAR = fake_hear


async def deaf(data, name):
    return {"ok": False, "ly_do": "khong_nghe_ro"}

zv.HEAR = deaf
out = run(history([voice(300)]))
check("unheard voice explained", "không nghe ra" in out["messages"][0].get("transcript_error", ""))
check("failure not cached", "https://voice-aac-dl.zdn.vn/1/v300.aac" not in json.loads(zv.CACHE_FILE.read_text("utf-8")))
zv.HEAR = fake_hear

check("non-history text untouched", asyncio.run(zv.enrich("ERROR: boom")) == "ERROR: boom")
check("non-string untouched", asyncio.run(zv.enrich({"a": 1})) == {"a": 1})

# Through the hub: an internal caller gets the raw result, a model's turn gets the transcript.
import mcp_hub  # noqa: E402
import tool_result_shaper  # noqa: E402

raw = history([voice(400)])


async def base(args):
    return raw

call = mcp_hub._shaped_call(base, {"conn": {"id": "zalo-x"}, "tool": "zalo_get_history"}, "zalo-x__zalo_get_history", "")
orig = tool_result_shaper.audience
tool_result_shaper.audience = lambda: ""
check("internal caller gets raw", asyncio.run(call({})) == raw)
tool_result_shaper.audience = lambda: "model"
try:
    got = asyncio.run(call({}))
finally:
    tool_result_shaper.audience = orig
check("model gets transcript", "chị nói v400.aac" in (got if isinstance(got, str) else json.dumps(got, ensure_ascii=False)))

if _fails:
    raise SystemExit(f"{len(_fails)} FAIL: {_fails}")
print("all ok")
