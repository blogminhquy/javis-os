"""The suggested next message once Javis has answered (2026-11-07).

    python tests/run.py next_prompt

Owner, 2026-11-07: Claude shows a likely next message grey in the empty chat box after it answers, and Tab fills it
in; "em xem có thêm được vào javis không?". No network: the background brain (`next_prompt._ASK`) and the quick API
call are fakes. Pins: nothing is asked until Javis has said something; the prompt carries the chat, newest last, with
hidden JAVIS_* blocks dropped and long replies cut from the front (the end holds the question); the quick API key goes
first and the background brain is the fallback; an odd answer ("KHONG", a paragraph, a reply in Javis's voice with a
lead) gives no suggestion; the long dash never comes out; results are cached; the switch in settings turns it off;
the routes never error; main.py runs it on the BACKGROUND model in the no-tool sandbox.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-next-prompt-"))

import main  # noqa: E402
import config as cfgmod  # noqa: E402
import next_prompt  # noqa: E402
import transcript_fix  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://127.0.0.1")
_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


CHAT = [
    {"role": "user", "text": "xem giúp anh 2 PR đang mở"},
    {"role": "assistant", "text": "Đề xuất: PR 1124 tạo nhánh thay thế, PR 1118 tách file test. "
                                  "Anh chọn hướng nào cho mỗi PR?<!-- JAVIS_ASK: {\"question\":\"x\"} -->"},
]
SAID = "ok làm theo đề xuất cho cả 2 PR đi"
seen = []
real_ask = next_prompt._ASK
real_api = next_prompt._ask_api
real_pick = transcript_fix.pick_quick_api


def run(cfg, ctx):
    next_prompt._cache.clear()
    return asyncio.run(next_prompt.suggest(cfg, ctx))


async def fake_brain(prompt):
    seen.append(("brain", prompt))
    return SAID


async def fake_api(pick, prompt):
    seen.append(("api", prompt))
    return "\"" + SAID + "\""


async def boom(*a, **k):
    raise RuntimeError("down")


# ---- main.py wiring ----
check("main.py wires the background brain into the suggestion", real_ask is main._next_prompt_ask)
src = open(os.path.join(SERVER, "main.py"), encoding="utf-8").read()
body = src[src.index("async def _next_prompt_ask"):src.index("next_prompt.wire(ask=_next_prompt_ask)")]
check("the suggestion runs on the BACKGROUND model (_aux_swap), not the main brain",
      "_aux_swap(" in body and "main_spec" not in body)
check("the suggestion runs in the no-tool sandbox, tools stripped",
      "_reply_policy_sandbox_engine(" in body and "aux_engine.strip_tools(" in body)

# ---- the prompt ----
next_prompt._ASK = fake_brain
transcript_fix.pick_quick_api = lambda cfg: None
seen.clear()
r = run({}, CHAT)
check("no API key: the background brain answers", r == {"text": SAID, "source": "brain"})
prompt = seen[0][1] if seen else ""
check("the prompt carries both sides of the chat, newest last",
      prompt.index("xem giúp anh") < prompt.index("Anh chọn hướng nào"))
check("hidden JAVIS_* blocks never reach the model", "JAVIS_ASK" not in prompt)
check("the prompt asks for the USER's words, short, and KHONG when unsure",
      "giọng của NGƯỜI DÙNG" in prompt and "KHONG" in prompt)
long_reply = "mở đầu " + "chữ " * 2000 + "câu hỏi cuối cùng?"
shaped = next_prompt.shape_context([{"role": "assistant", "text": long_reply}])
check("a long reply keeps its END (the question), not its start",
      shaped[0]["text"].endswith("câu hỏi cuối cùng?") and "mở đầu" not in shaped[0]["text"])
check("only the last 6 messages go", len(next_prompt.shape_context([{"role": "user", "text": str(i)} for i in range(20)])) == 6)

# ---- nothing to suggest yet ----
seen.clear()
check("empty chat: no suggestion, no call", run({}, []) == {"text": "", "source": ""} and not seen)
check("the owner spoke last (Javis has not answered): no call",
      run({}, CHAT[:1]) == {"text": "", "source": ""} and not seen)
check("odd context (not a list) is no context", run({}, "x")["text"] == "")

# ---- order: quick API first, background brain as fallback ----
transcript_fix.pick_quick_api = lambda cfg: ("groq", "k", "m", "u")
next_prompt._ask_api = fake_api
seen.clear()
r = run({}, CHAT)
check("an API key on the machine goes first (fast), quotes stripped", r == {"text": SAID, "source": "groq"})
check("the brain is not called when the API answered", [s for s, _ in seen] == ["api"])
next_prompt._ask_api = boom
seen.clear()
r = run({}, CHAT)
check("API fails: the background brain answers", r["text"] == SAID and r["source"] == "brain")
next_prompt._ASK = boom
r = run({}, CHAT)
check("everything fails: an empty suggestion, never an error", r["text"] == "")
next_prompt._ask_api = real_api
transcript_fix.pick_quick_api = lambda cfg: None

# ---- cache ----
next_prompt._ASK = fake_brain
next_prompt._cache.clear()
seen.clear()
asyncio.run(next_prompt.suggest({}, CHAT))
asyncio.run(next_prompt.suggest({}, CHAT))
check("the same chat is asked once (cached)", len(seen) == 1)

# ---- cleaning the answer ----
check("KHONG gives nothing", next_prompt.clean("KHONG") == "" and next_prompt.clean("Không.") == "")
check("a lead is dropped", next_prompt.clean("Câu người dùng sẽ gõ tiếp theo: " + SAID) == SAID)
check("only the first line", next_prompt.clean(SAID + "\nGiải thích: vì...") == SAID)
check("a paragraph is not a suggestion", next_prompt.clean("một " * 40) == "")
check("the long dash never comes out", "—" not in next_prompt.clean("ok — làm đi") and
      "–" not in next_prompt.clean("ok – làm đi"))
check("code fences are dropped", next_prompt.clean("```\n" + SAID + "\n```") == SAID)

# ---- the switch ----
seen.clear()
r = run({"chat": {"suggest_next": False}}, CHAT)
check("switched off: no suggestion and no call", r.get("off") is True and r["text"] == "" and not seen)
check("on by default", next_prompt.enabled({}) and next_prompt.enabled({"chat": {}}))

# ---- the routes ----
check("GET /chat/suggest: on by default", client.get("/chat/suggest").json() == {"enabled": True})
r = client.post("/chat/suggest", json={"context": CHAT})
check("POST /chat/suggest: the suggestion", r.status_code == 200 and r.json().get("text") == SAID)
r = client.post("/chat/suggest", content=b"not json")
check("POST /chat/suggest: bad JSON still answers", r.status_code == 200 and r.json().get("text") == "")
r = client.post("/settings", data={"section": "chat", "data": '{"suggest_next": false}'})
check("POST /settings section chat: saved", r.status_code == 200 and r.json().get("ok") is not False)
check("the switch is stored in settings.chat.suggest_next",
      cfgmod.read_settings().get("chat", {}).get("suggest_next") is False)
check("GET /chat/suggest: now off", client.get("/chat/suggest").json() == {"enabled": False})
r = client.post("/chat/suggest", json={"context": CHAT})
check("POST /chat/suggest while off: nothing", r.json().get("text") == "" and r.json().get("off") is True)
client.post("/settings", data={"section": "chat", "data": '{"suggest_next": true}'})
check("switched back on", client.get("/chat/suggest").json() == {"enabled": True})

next_prompt._ASK = real_ask
transcript_fix.pick_quick_api = real_pick

if _fails:
    print(f"\nFAIL - {len(_fails)} check(s)")
    raise SystemExit(1)
print("\nOK - next_prompt: all pass")
