"""The end of a dictation is fast again and loses nothing (2026-11-13).

    python tests/run.py dictation_speed

Owner, 2026-11-13: "phần đang viết lại câu cho đúng nó rất chậm" and "phần chép lời real time thì nó lại thường bị
sai". No network: the models are fakes. Pins:
  - the word rules give the same answer as before, much faster (similar_from never changes a result);
  - an everyday group of words is not turned into a name ("đã viết" is not "Javis", "cần và" is not "Canva");
  - the names of the MCP connections reach the model's prompt but never the fuzzy rules;
  - the quick API key is asked with thinking turned down and room for the whole sentence, per vendor;
  - an answer cut at the token limit is refused, not taken as the sentence;
  - a long dictation keeps every word, in the rewrite and in POST /stt/fix (it used to be cut at 2000 characters);
  - all the tries together stay inside the time the browser waits;
  - main.py lowers the thinking of the CLI that rewrites (Claude Code flag, Codex config).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import random
import tempfile
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-dictation-speed-"))

import main  # noqa: E402
import nghe_sua  # noqa: E402
import transcript_fix  # noqa: E402
import voice_ear  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://127.0.0.1")
_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- similar_from: the cheap answer for pairs that cannot reach the floor, the exact one for the rest ----
random.seed(3)
letters = "davitkgsnmore"
same = True
for _ in range(3000):
    a = "".join(random.choice(letters) for _ in range(random.randint(1, 9)))
    b = "".join(random.choice(letters) for _ in range(random.randint(1, 9)))
    full = nghe_sua.do_giong(a, b)
    got = nghe_sua.similar_from(a, b, 0.8)
    if (full >= 0.8 and got != full) or (full < 0.8 and got != 0.0):
        same = False
        break
check("similar_from: the full score at or above the floor, 0 below it (3000 random pairs)", same)
check("similar_from: equal keys are 1.0, an empty one is 0.0",
      nghe_sua.similar_from("davit", "davit", 0.8) == 1.0 and nghe_sua.similar_from("", "davit", 0.8) == 0.0)

# ---- speed ----
SPOKEN = ("phần nhận voice khi mà ấn tạm dừng ấy nó rất chậm và khi mà ấn dừng ghi để sửa nó rất chậm và ngay cả cái "
          "phần nhận voice này thì nó thường xuyên bị sai ví dụ anh đọc ravist OS thì nó bị sai em giúp anh tối ưu "
          "tốc độ và cải thiện cái phần chép lời này nhé")
BIG = (["Gmail", "Google Calendar", "Google Drive", "Meta ADS", "Supabase", "Webcake MCP", "Pancake POS", "Notion",
        "Slack", "Zalo", "Shopee", "Haravan", "KiotViet", "TikTok Ads"] + nghe_sua.fix_vocabulary({})
       + ["Từ khoá %d" % i for i in range(60)])[:90]
t0 = time.perf_counter()
nghe_sua.sua(" ".join([SPOKEN] * 5), BIG)
took = time.perf_counter() - t0
print(f"     (400 words, 90 terms: {took * 1000:.0f} ms; it took about 17800 ms before)")
check("rules: a 400-word dictation with 90 terms takes well under two seconds", took < 2.0)

# ---- everyday words are not names ----
TV = nghe_sua.fix_vocabulary({"voice": {"hotwords": "Canva, Pancake"}})
KEEP = [
    "em làm rồi đã viết xong",
    "thôi đã viết rồi",
    "anh cần và em cũng cần",
    "ừ đã việc gì đâu",
    "anh thấy cần va chạm ít thôi",
]
for t in KEEP:
    check(f"everyday words stay: {t!r}", nghe_sua.sua(t, TV) == t)
check("a misheard name is still fixed: David ơi", nghe_sua.sua("David ơi, mở lịch", TV) == "Javis ơi, mở lịch")
check("a name split in two is still fixed: Gia vít ơi", nghe_sua.sua("Gia vít ơi, tóm tắt email", TV).startswith("Javis ơi"))
check("an everyday group spelled like the term is still the term", nghe_sua.sua("mở Javis OS giúp anh", TV) == "mở Javis OS giúp anh")

# ---- the MCP names go to the prompt, not to the rules ----
real_labels = voice_ear._mcp_labels
voice_ear._mcp_labels = lambda: ["Canva", "Webcake MCP"]
seen = []


async def echo(prompt):
    seen.append(prompt)
    return prompt.split("<cau_may_chep>\n", 1)[1].split("\n</cau_may_chep>", 1)[0]


real_ask, real_quick = transcript_fix._ASK, transcript_fix._ask_quick_api
transcript_fix._ASK = echo
transcript_fix._ask_quick_api = None
transcript_fix._rewrite_cache.clear()
res = asyncio.run(transcript_fix.rewrite_transcript({}, "anh cần và em làm trang này", []))
check("rules: an MCP name does not rewrite everyday words", "<cau_may_chep>\nanh cần và em làm trang này\n" in seen[-1])
check("prompt: the MCP names are there for the model", "Canva" in seen[-1] and "Webcake MCP" in seen[-1])
voice_ear._mcp_labels = real_labels

# ---- the quick key's request ----
body = transcript_fix.quick_api_body("groq", "openai/gpt-oss-120b", "sys", "p", "một " * 100)
check("Groq gpt-oss: thinking low, room for the sentence and the thinking",
      body.get("reasoning_effort") == "low" and body["max_tokens"] >= 6 * 100 + 200 + 1000)
body = transcript_fix.quick_api_body("groq", "qwen/qwen3-32b", "sys", "p", "một hai")
check("Groq qwen3: thinking off", body.get("reasoning_effort") == "none")
body = transcript_fix.quick_api_body("groq", "llama-3.3-70b-versatile", "sys", "p", "một hai")
check("Groq llama: no thinking field (it would refuse one)", "reasoning_effort" not in body and body["max_tokens"] > 0)
body = transcript_fix.quick_api_body("gemini", "gemini-2.5-flash", "sys", "p", "một hai")
check("Gemini 2.5 flash: thinking off", body.get("reasoning_effort") == "none")
body = transcript_fix.quick_api_body("deepseek", "deepseek-flash", "sys", "p", "một hai")
check("DeepSeek: thinking switched off out loud", body.get("thinking") == {"type": "disabled"})
body = transcript_fix.quick_api_body("openai", "gpt-5-mini", "sys", "p", "một hai")
check("OpenAI gpt-5: low, max_completion_tokens, no temperature",
      body.get("reasoning_effort") == "low" and "max_completion_tokens" in body and "temperature" not in body
      and "max_tokens" not in body)
body = transcript_fix.quick_api_body("openai", "gpt-4o-mini", "sys", "p", "một hai")
check("OpenAI gpt-4o-mini: as before (temperature 0, max_tokens, no thinking field)",
      body.get("temperature") == 0 and "max_tokens" in body and "reasoning_effort" not in body)
check("quick timeout: 5 s for a short sentence, more for a long one, capped",
      transcript_fix.quick_timeout("một hai") < 5.1 and 5.1 < transcript_fix.quick_timeout("một " * 300)
      <= transcript_fix.QUICK_TIMEOUT_MAX_S)


# ---- an answer cut at the token limit is refused ----
class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class FakeClient:
    answer = None

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        FakeClient.sent = json
        return FakeResponse(FakeClient.answer)


real_client = transcript_fix.httpx.AsyncClient
transcript_fix.httpx.AsyncClient = FakeClient
PICK = ("groq", "gk", "openai/gpt-oss-120b", "https://example.invalid")
FakeClient.answer = {"choices": [{"message": {"content": "Câu bị cắt ở"}, "finish_reason": "length"}]}
try:
    asyncio.run(real_quick(PICK, "p", "câu bị cắt ở giữa chừng"))
    cut_refused = False
except RuntimeError:
    cut_refused = True
check("an answer stopped at the token limit is a failure, not the sentence", cut_refused)
FakeClient.answer = {"choices": [{"message": {"content": "Câu đầy đủ."}, "finish_reason": "stop"}]}
check("a finished answer is the sentence", asyncio.run(real_quick(PICK, "p", "câu đầy đủ")) == "Câu đầy đủ.")
check("the request sent is the one quick_api_body builds", FakeClient.sent.get("reasoning_effort") == "low")
transcript_fix.httpx.AsyncClient = real_client

# ---- a long dictation keeps every word ----
LONG = " ".join(["anh nói một đoạn dài về việc tối ưu tốc độ của phần chép lời"] * 160)   # about 9800 characters
asked = []


async def never(prompt):
    asked.append(prompt)
    return "x"


transcript_fix._ASK = never
transcript_fix._rewrite_cache.clear()
res = asyncio.run(transcript_fix.rewrite_transcript({}, LONG, []))
check("longer than MAX_REWRITE_CHARS: every word kept, no model asked",
      len(LONG) > transcript_fix.MAX_REWRITE_CHARS and res["text"] == LONG and not asked and res["source"] == "rules")

MID = " ".join(["anh nói một đoạn dài về việc tối ưu tốc độ"] * 70)   # about 3000 characters
transcript_fix._ASK = echo
transcript_fix._rewrite_cache.clear()
r = client.post("/stt/fix", json={"text": MID, "final": True, "context": []})
check("POST /stt/fix no longer cuts at 2000 characters", len(MID) > 2000 and r.json().get("text") == MID)
r = client.post("/stt/fix", json={"text": MID})
check("POST /stt/fix without final: a long text keeps every word", r.json().get("text") == MID)


# ---- the whole rewrite stays inside the browser's wait ----
order = []


async def hangs(*a, **k):
    order.append("quick")
    await asyncio.sleep(30)



async def main_late(prompt):
    order.append("main")
    return "x"


transcript_fix._ASK = main_late
transcript_fix._ask_quick_api = hangs
real_budget = transcript_fix.BUDGET_S
transcript_fix.BUDGET_S = 1.5
transcript_fix._rewrite_cache.clear()
t0 = time.monotonic()
res = asyncio.run(transcript_fix.rewrite_transcript(
    {"model": {"main": {"provider": "anthropic-cli"}, "groq_api_key": "gk"}}, "kiểm tra giúp anh", []))
spent = time.monotonic() - t0
transcript_fix.BUDGET_S = real_budget
check("a quick key that hangs is cut at the budget, the CLI is not started too late, the words stay",
      1.3 < spent < 3.0 and order == ["quick"] and res == {"text": "kiểm tra giúp anh", "source": "rules", "ai": False})
check("the budget fits inside the browser's 25-second wait", transcript_fix.BUDGET_S < 25)

transcript_fix._ASK, transcript_fix._ask_quick_api = real_ask, real_quick

# ---- main.py: the CLI that rewrites thinks at the lowest level ----
src = open(os.path.join(SERVER, "main.py"), encoding="utf-8").read()
fn = src[src.index("async def _transcript_rewrite_ask"):src.index("transcript_fix.wire(ask=_transcript_rewrite_ask)")]
check("Claude Code rewrites at effort low, only where the CLI has the flag",
      'claude_cli.co_co("--effort")' in fn and 'base.effort = "low"' in fn)
check("Codex links of the rewrite get a low effort", "_rewrite_low_effort_codex(cli)" in fn)


class CodexCLI:   # same class name as the real engine
    def __init__(self):
        self.model = "gpt-5.5-codex"
        self.extra_config = ["model_reasoning_effort=high", "other=1"]


real_effort = main._codex_effort
main._codex_effort = lambda model, level: "low" if level == "low" else ""
cx = CodexCLI()
main._rewrite_low_effort_codex(cx)
check("Codex: its effort becomes low, other config kept",
      cx.extra_config == ["other=1", "model_reasoning_effort=low"])
main._codex_effort = lambda model, level: ""
cx = CodexCLI()
main._rewrite_low_effort_codex(cx)
check("Codex model without a low level: left at its own", cx.extra_config == ["model_reasoning_effort=high", "other=1"])
main._codex_effort = real_effort
main._rewrite_low_effort_codex(object())   # an engine of another kind: nothing happens, nothing raised
check("another engine is left alone", True)

if _fails:
    print(f"\nFAIL - test_dictation_speed: {len(_fails)}")
    raise SystemExit(1)
print("\nOK - test_dictation_speed: all pass")
