"""The suggested next message once Javis has answered (2026-11-07).

    python tests/run.py next_prompt

Owner, 2026-11-07: Claude shows a likely next message grey in the empty chat box after it answers, and Tab fills it
in; "em xem có thêm được vào javis không?". No network: the background brain (`next_prompt._ASK`) and the quick API
call are fakes. Pins: nothing is asked until Javis has said something; the prompt carries the chat, newest last, with
hidden JAVIS_* blocks dropped and long replies cut from the front (the end holds the question); the quick API key goes
first and the background brain is the fallback; an odd answer ("KHONG", a paragraph, a reply in Javis's voice with a
lead) gives no suggestion; the long dash never comes out; results are cached; the switch in settings turns it off;
the routes never error; main.py runs it on the BACKGROUND model in the no-tool sandbox.

2026-11-13, a user's wish passed on by the owner: "suy đoán tiếp nội dung gõ sau khi người dùng muốn điều chỉnh, kiểu
chức năng dự đoán thông minh trên iPhone". Pins for finishing a draft: the prompt carries the chat, the draft and the
suggestion that was showing; the answer is only what comes AFTER the draft (the model returns the whole sentence, the
typed part is cut off, marks and case not counting); a reply that does not start with the draft gives nothing; the
browser is told how patiently to ask (often on an API key, slowly and a few times on the background brain); and only
one brain completion runs at a time.
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

# ---- 2026-11-13: finishing a draft the owner is typing ----
DRAFT = "ok làm PR 1124 tr"
FULL = "ok làm PR 1124 trước, PR 1118 để sau"
REST = "ước, PR 1118 để sau"


async def fake_brain_full(prompt):
    seen.append(("brain", prompt))
    return FULL


async def fake_api_full(pick, prompt):
    seen.append(("api", prompt))
    return "Câu hoàn chỉnh: \"" + FULL + "\""


def finish(cfg, ctx, draft, hint=""):
    next_prompt._cache.clear()
    return asyncio.run(next_prompt.complete(cfg, ctx, draft, hint))


check("a draft keeps ONE trailing space (the last word is finished) and folds the rest",
      next_prompt.shape_draft("ok   làm  ") == "ok làm " and next_prompt.shape_draft("  ok làm") == "ok làm")
check("too short, several lines or very long: not a draft to finish",
      next_prompt.shape_draft("a") == "" and next_prompt.shape_draft(" ") == "" and
      next_prompt.shape_draft("dòng 1\ndòng 2") == "" and next_prompt.shape_draft("x" * 201) == "" and
      next_prompt.shape_draft(None) == "")
check("only what comes after the draft is returned", next_prompt.clean_completion(FULL, DRAFT) == REST)
check("a finished word: the rest starts with its space",
      next_prompt.clean_completion("ok làm theo đề xuất", "ok làm") == " theo đề xuất")
check("a draft ending in a space: the rest starts with the word",
      next_prompt.clean_completion("ok làm theo đề xuất", "ok làm ") == "theo đề xuất")
check("marks and case do not count when cutting the typed part off",
      next_prompt.clean_completion("Em sửa kỹ năng code trước nhé", "em sua ky nang code") == " trước nhé")
check("decomposed marks from the keyboard line up with the model's composed ones",
      next_prompt.clean_completion("Em sửa kỹ năng code trước", "Em su\u031b\u0309a") == " kỹ năng code trước")
check("an answer that does not start with the draft is a reply, not a continuation",
      next_prompt.clean_completion("Được, em làm ngay", "ok làm ") == "" and
      next_prompt.clean_completion("trước, PR 1118 để sau", DRAFT) == "")
check("nothing added, KHONG, or a paragraph: nothing",
      next_prompt.clean_completion(DRAFT, DRAFT) == "" and next_prompt.clean_completion("KHONG", DRAFT) == "" and
      next_prompt.clean_completion(DRAFT + " và" * 40, DRAFT) == "")
check("the long dash never comes out of a completion",
      "—" not in next_prompt.clean_completion("ok làm PR 1124 trước — rồi báo anh", "ok làm PR 1124"))
parts = next_prompt.split_completion("Chỉ đánh dấu luật nền thôi nhé", "chi danh dau luat n")
check("the whole sentence comes back in the model's own spelling, next to the rest",
      parts == {"text": "ền thôi nhé", "full": "Chỉ đánh dấu luật nền thôi nhé"})
parts = next_prompt.split_completion("ok làm theo đề xuất ", "ok   làm ")
check("the whole sentence keeps one space where the draft ended in spaces",
      parts == {"text": "theo đề xuất", "full": "ok làm theo đề xuất"})
check("not a continuation: no whole sentence either", next_prompt.split_completion("Được ạ", "ok làm") == {"text": ""})
check("quotes, a lead and a second line are dropped before cutting",
      next_prompt.clean_completion("Câu hoàn chỉnh: \"" + FULL + "\"\nGiải thích: vì...", DRAFT) == REST)

next_prompt._ASK = fake_brain_full
transcript_fix.pick_quick_api = lambda cfg: None
seen.clear()
r = finish({}, CHAT, DRAFT, SAID)
check("no API key: the background brain finishes the draft", r == {"text": REST, "full": FULL, "source": "brain"})
prompt = seen[0][1] if seen else ""
check("the prompt asks for the WHOLE sentence starting with what was typed",
      "BẮT ĐẦU bằng đúng nguyên văn phần đã gõ" in prompt and "<da_go>\n" + DRAFT + "\n</da_go>" in prompt)
check("the prompt carries the chat and the suggestion that was showing",
      "Anh chọn hướng nào" in prompt and "<goi_y_cu>\n" + SAID + "\n</goi_y_cu>" in prompt and
      prompt.index("<hoi_thoai>") < prompt.index("<goi_y_cu>") < prompt.index("<da_go>"))
check("hidden JAVIS_* blocks never reach the model here either", "JAVIS_ASK" not in prompt)
seen.clear()
finish({}, CHAT, DRAFT)
check("no suggestion was showing: the prompt has no such block", seen and "<goi_y_cu>" not in seen[0][1])
seen.clear()
check("too short a draft: nothing, no call", finish({}, CHAT, "a") == {"text": "", "source": ""} and not seen)
check("the owner spoke last: nothing, no call", finish({}, CHAT[:1], DRAFT) == {"text": "", "source": ""} and not seen)
r = finish({"chat": {"suggest_next": False}}, CHAT, DRAFT)
check("switched off: no completion and no call", r.get("off") is True and r["text"] == "" and not seen)
next_prompt._cache.clear()
asyncio.run(next_prompt.complete({}, CHAT, DRAFT))
asyncio.run(next_prompt.complete({}, CHAT, DRAFT))
check("the same draft is asked once (cached)", len(seen) == 1)
asyncio.run(next_prompt.complete({}, CHAT, DRAFT + "ước"))
check("a longer draft is a new question", len(seen) == 2)
transcript_fix.pick_quick_api = lambda cfg: ("groq", "k", "m", "u")
next_prompt._ask_api = fake_api_full
seen.clear()
r = finish({}, CHAT, DRAFT)
check("an API key goes first for a draft too", r["text"] == REST and r["source"] == "groq" and [s for s, _ in seen] == ["api"])
next_prompt._ask_api = boom
r = finish({}, CHAT, DRAFT)
check("API fails: the background brain finishes it", r["text"] == REST and r["source"] == "brain")
next_prompt._ASK = boom
check("everything fails: nothing, never an error", finish({}, CHAT, DRAFT)["text"] == "")
next_prompt._ask_api = real_api

# How patiently the browser asks.
check("an API key: asked often", next_prompt.live_policy({}) == next_prompt.LIVE_API)
transcript_fix.pick_quick_api = lambda cfg: None
check("only the background brain: asked slowly and a few times per turn",
      next_prompt.live_policy({}) == next_prompt.LIVE_BRAIN and
      next_prompt.LIVE_BRAIN["wait_ms"] > next_prompt.LIVE_API["wait_ms"] and
      next_prompt.LIVE_BRAIN["max"] < next_prompt.LIVE_API["max"])
check("switched off: never asked", next_prompt.live_policy({"chat": {"suggest_next": False}}) is None)
next_prompt._ASK = None
check("no key and no brain: never asked", next_prompt.live_policy({}) is None)


# One brain completion at a time: a CLI turn takes seconds, typing must not stack them.
async def two_at_once():
    gate = asyncio.Event()
    started = []

    async def slow_brain(prompt):
        started.append(prompt)
        await gate.wait()
        return FULL

    next_prompt._ASK = slow_brain
    next_prompt._cache.clear()
    first = asyncio.create_task(next_prompt.complete({}, CHAT, DRAFT))
    await asyncio.sleep(0)
    second = await next_prompt.complete({}, CHAT, DRAFT + "ư")
    turn = asyncio.create_task(next_prompt.suggest({}, CHAT))   # the turn's own suggestion is not held back
    await asyncio.sleep(0)
    n = len(started)
    gate.set()
    return await first, second, await turn, n, await next_prompt.complete({}, CHAT, DRAFT + "ư")


first, second, turn, n, again = asyncio.run(two_at_once())
check("while one brain completion runs, the next answers busy at once", first["text"] == REST and second.get("busy") is True and
      second["text"] == "")
check("the suggestion for a finished turn still runs next to it", n == 2 and turn["source"] == "brain")
check("a busy answer is not remembered: the same draft is finished later", again["text"] == REST[1:] and again["source"] == "brain")
check("the count is back to zero afterwards", next_prompt._brain_live[0] == 0)


async def brain_breaks():
    next_prompt._ASK = boom
    next_prompt._cache.clear()
    await next_prompt.complete({}, CHAT, DRAFT)
    return next_prompt._brain_live[0]


check("a completion that fails gives the place back", asyncio.run(brain_breaks()) == 0)
next_prompt._ASK = fake_brain
next_prompt._cache.clear()

# ---- the routes ----
check("GET /chat/suggest: on by default, with the pace for finishing drafts",
      client.get("/chat/suggest").json() == {"enabled": True, "live": next_prompt.LIVE_BRAIN})
r = client.post("/chat/suggest", json={"context": CHAT})
check("POST /chat/suggest: the suggestion", r.status_code == 200 and r.json().get("text") == SAID)
check("the suggestion answer carries the pace too (a key added later shows up without a reload)",
      r.json().get("live") == next_prompt.LIVE_BRAIN)
next_prompt._ASK = fake_brain_full
r = client.post("/chat/suggest", json={"context": CHAT, "draft": DRAFT, "hint": SAID})
check("POST /chat/suggest with a draft: the rest of the sentence, and the whole of it",
      r.status_code == 200 and r.json().get("text") == REST and r.json().get("full") == FULL)
r = client.post("/chat/suggest", json={"context": CHAT, "draft": 7})
check("an odd draft is no draft: the turn's suggestion is asked instead", r.status_code == 200 and "live" in r.json())
r = client.post("/chat/suggest", json=["not", "a", "dict"])
check("POST /chat/suggest: an odd body still answers", r.status_code == 200 and r.json().get("text") == "")
next_prompt._ASK = fake_brain
next_prompt._cache.clear()
r = client.post("/chat/suggest", content=b"not json")
check("POST /chat/suggest: bad JSON still answers", r.status_code == 200 and r.json().get("text") == "")
r = client.post("/settings", data={"section": "chat", "data": '{"suggest_next": false}'})
check("POST /settings section chat: saved", r.status_code == 200 and r.json().get("ok") is not False)
check("the switch is stored in settings.chat.suggest_next",
      cfgmod.read_settings().get("chat", {}).get("suggest_next") is False)
check("GET /chat/suggest: now off", client.get("/chat/suggest").json() == {"enabled": False, "live": None})
r = client.post("/chat/suggest", json={"context": CHAT})
check("POST /chat/suggest while off: nothing", r.json().get("text") == "" and r.json().get("off") is True)
r = client.post("/chat/suggest", json={"context": CHAT, "draft": DRAFT})
check("POST /chat/suggest with a draft while off: nothing", r.json().get("text") == "" and r.json().get("off") is True)
client.post("/settings", data={"section": "chat", "data": '{"suggest_next": true}'})
check("switched back on", client.get("/chat/suggest").json().get("enabled") is True)

next_prompt._ASK = real_ask
transcript_fix.pick_quick_api = real_pick

if _fails:
    print(f"\nFAIL - {len(_fails)} check(s)")
    raise SystemExit(1)
print("\nOK - next_prompt: all pass")
