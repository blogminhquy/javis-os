"""POST /stt/fix and transcript_fix: the live bubble's words fixed by rules, then a model (2026-11-06).

    python tests/run.py transcript_fix

No network: the model call (`transcript_fix._ask_model`) is replaced by fakes. Pins: rules always run (Jarvis ->
Javis, Groq kept), Groq wins when its key is set, otherwise the background model only when it is an API with a key,
a model that rewrites the sentence or fails falls back to the rules, and the route never errors. 2026-11-12: a model
that turns an English sentence into Vietnamese is refused too.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-fix-"))

import main  # noqa: E402
import transcript_fix  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://127.0.0.1")
_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def fix(cfg, text):
    return asyncio.run(transcript_fix.fix_transcript(cfg, text))


# ---- which model ----
check("no key at all: rules only", transcript_fix.pick_model({"model": {}}) is None)
p = transcript_fix.pick_model({"model": {"groq_api_key": "gk", "openai_api_key": "ok",
                                         "auxiliary": {"provider": "openai"}}})
check("a Groq key wins over the background model", p and p[0] == "groq" and p[1] == "gk")
p = transcript_fix.pick_model({"model": {"openai_api_key": "ok", "auxiliary": {"provider": "openai", "model": "gpt-x"}}})
check("no Groq: the background model when it is an API with a key", p and p[0] == "openai" and p[2] == "gpt-x")
check("background model without its key: rules only",
      transcript_fix.pick_model({"model": {"auxiliary": {"provider": "openai"}}}) is None)
check("background model is Claude Code: rules only",
      transcript_fix.pick_model({"model": {"auxiliary": {"provider": "anthropic-cli"}}}) is None)

# ---- rules only ----
r = fix({"model": {}}, "tôi hỏi Jarvis OS nhé")
check("rules: Jarvis OS -> Javis OS", r == {"text": "tôi hỏi Javis OS nhé", "source": "rules", "ai": False})
check("rules: Groq is kept, not turned into Grok", fix({"model": {}}, "tôi dùng Groq")["text"] == "tôi dùng Groq")
check("empty text stays empty", fix({"model": {}}, "  ")["text"] == "")

# ---- model pass ----
seen = []


async def fake_ok(pick, sentence, terms):
    seen.append((pick[0], sentence, "Javis OS" in terms))
    return sentence.replace("Clod", "Claude")


transcript_fix._ask_model = fake_ok
r = fix({"model": {"groq_api_key": "gk"}}, "mở Clod giúp Jarvis OS")
check("model: gets the rules' output and the AI terms", seen and seen[-1] == ("groq", "mở Clod giúp Javis OS", True))
check("model: its fix is returned", r == {"text": "mở Claude giúp Javis OS", "source": "groq", "ai": True})
n = len(seen)
fix({"model": {"groq_api_key": "gk"}}, "mở Clod giúp Jarvis OS")
check("model: the same sentence is answered from the cache", len(seen) == n)


async def fake_rewrite(pick, sentence, terms):
    return sentence + " và đây là một đoạn giải thích dài model tự thêm vào"


transcript_fix._ask_model = fake_rewrite
r = fix({"model": {"groq_api_key": "gk"}}, "báo cáo hôm nay")
check("model rewrites the sentence: rules kept", r == {"text": "báo cáo hôm nay", "source": "rules", "ai": False})


async def fake_translate(pick, sentence, terms):
    return "Tôi không biết vì sao vấn đề này tồn tại"


transcript_fix._ask_model = fake_translate
r = fix({"model": {"groq_api_key": "gk"}}, "i don't know why this problem exists")
check("model translates English into Vietnamese: rules kept",
      r == {"text": "i don't know why this problem exists", "source": "rules", "ai": False})
check("the system prompt says to keep the language", "không dịch" in transcript_fix.SYSTEM_PROMPT)


async def fake_fail(pick, sentence, terms):
    raise RuntimeError("down")


transcript_fix._ask_model = fake_fail
r = fix({"model": {"groq_api_key": "gk"}}, "Jarvis ơi")
check("model fails: rules kept, no error", r == {"text": "Javis ơi", "source": "rules", "ai": False})
check("is_safe_fix: a one-word fix is fine", transcript_fix.is_safe_fix("mở Grox giúp tôi", "mở Grok giúp tôi"))
check("is_safe_fix: empty is refused", not transcript_fix.is_safe_fix("a b", ""))

# ---- route ----
main.cfgmod.read_settings = lambda: {"model": {}}
res = client.post("/stt/fix", json={"text": "Jarvis OS ơi"})
check("/stt/fix: 200 with the fixed text", res.status_code == 200 and res.json() == {
    "ok": True, "text": "Javis OS ơi", "source": "rules", "ai": False})
res = client.post("/stt/fix", content=b"not json", headers={"Content-Type": "application/json"})
check("/stt/fix: broken body -> ok=false, no error", res.status_code == 200 and res.json()["ok"] is False)

if _fails:
    print(f"\nFAIL: {len(_fails)} {_fails}")
    raise SystemExit(1)
print("\nOK - transcript_fix")
