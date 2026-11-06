"""The end of every dictation: the MAIN brain rewrites what the mic heard, in context (2026-11-06).

    python tests/run.py transcript_rewrite

Owner, 2026-11-06: "nói xong ấn Enter hoặc ấn tắt thì nó tự dùng mô hình viết lại thành câu đúng ngữ cảnh", "đừng
chỉ sửa vài từ như Travis hay Jarvis, hãy sửa cả cấu trúc", "dùng ngay chính mô hình chính". No network: the main
brain (`transcript_fix._ASK`) and the quick API call are fakes. Pins: the prompt carries the heard sentence, the
vocabulary and the chat context; the main brain goes first; an answer that is not a rewrite (an answer to the
question, a much longer text, empty) or a failure falls through to the quick API and then the rules; results are
cached; POST /stt/fix with `final` runs the rewrite and still never errors; main.py wires the main brain in a
sandbox with no tools; the Whisper prompt keeps "Javis" at its end.
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
check("main brain fails: the quick API key takes over", res["source"] == "groq" and quick == ["groq"]
      and res["text"] == "Kiểm tra giúp anh Javis đã nghe được chưa.")
res = run({}, "kiểm tra giúp anh jarvis đã nghe được chưa")
check("no model at all: the word rules still run (Jarvis -> Javis)",
      res["source"] == "rules" and "Javis" in res["text"])


async def wrapped(prompt):
    return 'Câu đã viết lại: "Mở trang Models giúp anh."'


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
