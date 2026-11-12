"""The end of every dictation: the MAIN brain rewrites what the mic heard, in context (2026-11-06).

    python tests/run.py transcript_rewrite

Owner, 2026-11-06: "nói xong ấn Enter hoặc ấn tắt thì nó tự dùng mô hình viết lại thành câu đúng ngữ cảnh", "đừng
chỉ sửa vài từ như Travis hay Jarvis, hãy sửa cả cấu trúc", "dùng ngay chính mô hình chính". No network: the main
brain (`transcript_fix._ASK`) and the quick API call are fakes. Pins: the prompt carries the heard sentence, the
vocabulary and the chat context; fast first (a main brain on an API key first, else an API key on the machine and
the main brain's CLI last); an answer that is not a rewrite (an answer to the
question, a much longer text, empty) or a failure falls through to the quick API and then the rules; results are
cached; POST /stt/fix with `final` runs the rewrite and still never errors; main.py wires the main brain in a
sandbox with no tools; the Whisper prompt keeps "Javis" at its end.

2026-11-12 (owner report, iPad, English user): an English dictation came back translated into Vietnamese. Pins: the
prompt says to keep the language and marks a sentence that is not Vietnamese; a rewrite that turned such a sentence
into Vietnamese is refused, the next model is tried, and with none left the words stay as heard; Vietnamese sounds
turned back into English stay allowed.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-rewrite-"))

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


HEARD = "ok anh vừa thêm cross rồi groq và test thử xem travis os đã nghe được chưa"
MEANT = "Ok anh vừa thêm cả Groq rồi, test thử xem Javis OS đã nghe được chưa."
seen = []


def run(cfg, text, ctx=None):
    transcript_fix._rewrite_cache.clear()
    return asyncio.run(transcript_fix.rewrite_transcript(cfg, text, ctx))


real_ask = transcript_fix._ASK
real_quick = transcript_fix._ask_quick_api

# ---- main.py wires the main brain ----
check("main.py wires the main brain into the rewrite", real_ask is main._transcript_rewrite_ask)
src = open(os.path.join(SERVER, "main.py"), encoding="utf-8").read()
body = src[src.index("async def _transcript_rewrite_ask"):src.index("transcript_fix.wire(ask=_transcript_rewrite_ask)")]
check("the rewrite runs on the MAIN brain (main_spec), not the background model", "spec=aux_engine.main_spec()" in body)
check("the rewrite runs in the no-tool sandbox, tools stripped",
      "_reply_policy_sandbox_engine(" in body and "aux_engine.strip_tools(" in body)


# ---- the prompt ----
async def fake_main(prompt):
    seen.append(prompt)
    return MEANT


transcript_fix._ASK = fake_main
transcript_fix._ask_quick_api = None
res = run({}, HEARD, ["Anh vừa thêm khoá Groq ở trang Models", "Dạ em thấy rồi"])
check("the main brain's rewrite is the answer", res == {"text": MEANT, "source": "main", "ai": True})
p = seen[-1]
check("prompt carries the heard sentence inside its tags", "<cau_may_chep>\n" + HEARD + "\n</cau_may_chep>" in p)
check("prompt carries the chat context", "Anh vừa thêm khoá Groq ở trang Models" in p and "Dạ em thấy rồi" in p)
check("prompt carries the vocabulary (Javis, AI terms)", "Javis" in p and "Groq" in p and "Claude" in p)
check("prompt asks for a rewrite of every mishearing, not a word list", "kể cả những từ không có trong danh sách" in p)
check("prompt forbids answering the sentence", "KHÔNG trả lời" in transcript_fix.REWRITE_SYSTEM)

# cache: same sentence and context, one call
seen.clear()
transcript_fix._rewrite_cache.clear()
asyncio.run(transcript_fix.rewrite_transcript({}, HEARD, ["a"]))
asyncio.run(transcript_fix.rewrite_transcript({}, HEARD, ["a"]))
check("the same sentence and context ask the model once", len(seen) == 1)


# ---- answers that are not a rewrite fall through ----
async def answers(prompt):
    return ("Dạ, em đã kiểm tra rồi ạ. Javis OS đang nghe tốt, khoá Groq đã được nhận, anh có thể thử nói một câu dài "
            "hơn để em xem lại độ chính xác của phần chép lời, và nếu cần em sẽ hướng dẫn anh cách bật thêm tai nghe.")


transcript_fix._ASK = answers
res = run({}, "kiểm tra giúp anh travis đã nghe được chưa")
check("a model that ANSWERS instead of rewriting: the rules are kept", res["source"] == "rules" and not res["ai"])


async def boom(prompt):
    raise RuntimeError("signed out")


quick = []


async def fake_quick(pick, prompt, sentence):
    quick.append(pick[0])
    return "Kiểm tra giúp anh Javis đã nghe được chưa."


transcript_fix._ASK = boom
transcript_fix._ask_quick_api = fake_quick
res = run({"model": {"groq_api_key": "gk"}}, "kiểm tra giúp anh travis đã nghe được chưa")
check("Groq key with a CLI main brain: Groq rewrites", res["source"] == "groq" and quick == ["groq"]
      and res["text"] == "Kiểm tra giúp anh Javis đã nghe được chưa.")
res = run({}, "kiểm tra giúp anh jarvis đã nghe được chưa")
check("no model at all: the word rules still run (Jarvis -> Javis)",
      res["source"] == "rules" and "Javis" in res["text"])


async def wrapped(prompt):
    return 'Câu đã viết lại: "Mở trang Models giúp anh."'


# ---- fast first (owner, 2026-11-06: "làm nhanh trước") ----
order = []


async def main_ok(prompt):
    order.append("main")
    return "Kiểm tra giúp anh Javis đã nghe được chưa."


async def quick_ok(pick, prompt, sentence):
    order.append(pick[0])
    return "Kiểm tra giúp anh Javis đã nghe được chưa."


async def quick_down(pick, prompt, sentence):
    order.append(pick[0])
    raise RuntimeError("down")


transcript_fix._ASK = main_ok
transcript_fix._ask_quick_api = quick_ok
HEARD2 = "kiểm tra giúp anh travis đã nghe được chưa"
CLI_GROQ = {"model": {"main": {"provider": "anthropic-cli"}, "groq_api_key": "gk"}}
order.clear()
res = run(CLI_GROQ, HEARD2)
check("main brain is a CLI and Groq has a key: Groq rewrites, the CLI is never started",
      order == ["groq"] and res["source"] == "groq")
order.clear()
res = run({"model": {"main": {"provider": "openai-oauth"}, "gemini_api_key": "g"}}, HEARD2)
check("main brain is Codex, only a Gemini key: Gemini rewrites", order == ["gemini"] and res["source"] == "gemini")
transcript_fix._ask_quick_api = quick_down
order.clear()
res = run(CLI_GROQ, HEARD2)
check("the quick key fails: the main brain's CLI is the last resort", order == ["groq", "main"] and res["source"] == "main")
transcript_fix._ask_quick_api = quick_ok
order.clear()
res = run({"model": {"main": {"provider": "anthropic-cli"}}}, HEARD2)
check("a CLI and no API key at all: the main brain still rewrites", order == ["main"] and res["source"] == "main")
order.clear()
res = run({"model": {"main": {"provider": "openrouter", "model": "x"}, "openrouter_key": "ok", "groq_api_key": "gk"}},
          HEARD2)
check("main brain is an API key: it goes first, even with a Groq key", order == ["main"] and res["source"] == "main")
check("quick pick: Groq, then the background API, then any key",
      transcript_fix.pick_quick_api({"model": {"deepseek_api_key": "d"}})[0] == "deepseek"
      and transcript_fix.pick_quick_api({"model": {}}) is None)
check("main_is_cli: Claude Code, Codex, Grok, Antigravity are CLIs; OpenRouter is not",
      all(transcript_fix.main_is_cli({"model": {"main": {"provider": p}}})
          for p in ("anthropic-cli", "openai-oauth", "grok-cli", "antigravity-cli"))
      and not transcript_fix.main_is_cli({"model": {"main": {"provider": "openrouter"}}}))

# ---- a sentence comes back in the language it was spoken in (2026-11-12) ----
EN_HEARD = ("but every time i read the first time then i press stop and after that i continue reading the second "
            "time i read even though i speak in english it automatically translates into vietnamese")
EN_MEANT = ("But every time I read the first time, then I press stop, and after that I continue reading, the second "
            "time I read, even though I speak in English, it automatically translates into Vietnamese.")
VI_TRANSLATED = ("Nhưng mỗi lần tôi đọc lần đầu, rồi tôi bấm dừng, và sau đó tôi tiếp tục đọc, thì lần thứ hai tôi "
                 "đọc, mặc dù tôi nói bằng tiếng Anh, nó tự động dịch sang tiếng Việt.")


async def translates(prompt):
    order.append("main")
    return VI_TRANSLATED


async def main_keeps(prompt):
    order.append("main")
    return EN_MEANT


async def quick_translates(pick, prompt, sentence):
    order.append(pick[0])
    return VI_TRANSLATED


check("the translation would have passed the size check alone", transcript_fix.is_safe_rewrite(EN_HEARD, VI_TRANSLATED))
transcript_fix._ASK = translates
transcript_fix._ask_quick_api = None
order.clear()
res = run({}, EN_HEARD)
check("English heard, the model answers in Vietnamese: refused, the words stay as heard",
      res == {"text": EN_HEARD, "source": "rules", "ai": False})
transcript_fix._ask_quick_api = quick_translates
order.clear()
res = run(CLI_GROQ, EN_HEARD)
check("the quick key translates: the main brain is tried next, and refused too",
      order == ["groq", "main"] and res["text"] == EN_HEARD and res["source"] == "rules")
transcript_fix._ASK = main_keeps
order.clear()
res = run(CLI_GROQ, EN_HEARD)
check("the quick key translates, the main brain keeps English: the main brain's sentence",
      order == ["groq", "main"] and res == {"text": EN_MEANT, "source": "main", "ai": True})
transcript_fix._ASK = fake_main
seen.clear()
run({}, EN_HEARD)
check("prompt: a sentence that is not Vietnamese is marked right above it",
      transcript_fix.KEEP_LANGUAGE_NOTE in seen[-1]
      and seen[-1].index(transcript_fix.KEEP_LANGUAGE_NOTE) < seen[-1].index("<cau_may_chep>")
      and "<cau_may_chep>" not in seen[-1][:seen[-1].index(transcript_fix.KEEP_LANGUAGE_NOTE)])
seen.clear()
run({}, HEARD)
check("prompt: a Vietnamese sentence gets no such mark", transcript_fix.KEEP_LANGUAGE_NOTE not in seen[-1])
check("prompt: the rules name the language, whatever language they are written in",
      "bằng đúng ngôn ngữ đó" in transcript_fix.REWRITE_RULES and "KHÔNG dịch" in transcript_fix.REWRITE_SYSTEM
      and "thường là tiếng Việt" not in transcript_fix.REWRITE_SYSTEM)
kl = transcript_fix.keeps_language
check("keeps_language: English fixed in English", kl(EN_HEARD, EN_MEANT))
check("keeps_language: English turned into Vietnamese is a translation", not kl(EN_HEARD, VI_TRANSLATED))
check("keeps_language: a short English sentence too", not kl("thank you very much", "Cảm ơn rất nhiều."))
check("keeps_language: German and Japanese count as not Vietnamese",
      not kl("ich weiß nicht warum es dieses Problem gibt", "Tôi không biết vì sao có vấn đề này.")
      and not kl("なぜこの問題があるのか分かりません", "Tôi không biết vì sao có vấn đề này."))
check("keeps_language: Vietnamese fixed in Vietnamese", kl(HEARD, MEANT))
check("keeps_language: Vietnamese with few marked words is still Vietnamese",
      kl("cho tôi xem doanh thu hôm nay", "Cho tôi xem doanh thu hôm nay của cửa hàng.")
      and not transcript_fix.not_vietnamese("cho tôi xem doanh thu hôm nay"))
check("keeps_language: Vietnamese sounds turned back into English stay allowed",
      kl("mở lót code giúp anh", "Open Claude Code for me."))
check("keeps_language: an English sentence may gain a Vietnamese name",
      kl("send this report to quy and mister nguyen please", "Send this report to Quý and Mr. Nguyễn, please."))
check("keeps_language: letters written as base plus combining marks count the same",
      not kl("thank you very much", __import__("unicodedata").normalize("NFD", "Cảm ơn rất nhiều.")))

transcript_fix._ASK = wrapped
res = run({}, "mở trang mo đồ giúp anh")
check("a lead-in and quotes around the answer are removed", res["text"] == "Mở trang Models giúp anh.")

check("is_safe_rewrite: empty is not a rewrite", not transcript_fix.is_safe_rewrite("một hai ba", ""))
check("is_safe_rewrite: a fixed sentence of the same size is", transcript_fix.is_safe_rewrite(HEARD, MEANT))
check("is_safe_rewrite: a sentence cut to a third is not",
      not transcript_fix.is_safe_rewrite("một hai ba bốn năm sáu bảy tám chín mười", "một hai"))

# ---- the route ----
transcript_fix._ASK = fake_main
r = client.post("/stt/fix", json={"text": HEARD, "final": True, "context": ["x"] * 20})
check("POST /stt/fix final: the rewrite", r.status_code == 200 and r.json().get("ok") and r.json().get("text") == MEANT)
transcript_fix._ASK = boom
transcript_fix._ask_quick_api = real_quick
r = client.post("/stt/fix", json={"text": "travis os", "final": True, "context": "not a list"})
check("POST /stt/fix final: a failing brain and odd context still answer ok", r.status_code == 200 and r.json().get("ok"))

transcript_fix._ASK = real_ask

# ---- the Whisper prompt keeps the assistant's name next to the audio ----
real_labels = voice_ear._mcp_labels
voice_ear._mcp_labels = lambda: ["Kết nối số %d rất dài tên tiếng Việt" % i for i in range(80)]
words = voice_ear.vocab({})
voice_ear._mcp_labels = real_labels
check("vocab: the connections come first, Javis last (closest to the audio)", words[-1] == "Javis")
hw = nghe_sua.goi_y_whisper(words)
check("Whisper prompt: within the length cap and still ending with Javis",
      len(hw) <= nghe_sua.MAX_GOI_Y and hw.endswith("Javis."))

if _fails:
    print(f"\nFAIL - {len(_fails)} check(s)")
    raise SystemExit(1)
print("\nOK - transcript_rewrite: all pass")
