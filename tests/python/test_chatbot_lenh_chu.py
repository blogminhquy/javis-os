"""The owner's order in "Javis soạn" (inbox draft with an instruction) wins over documents and the chat history.

    python tests/run.py chatbot_lenh_chu      (no network, fake engine)

Field report 2026-11-19: earlier in a Zalo chat the bot had said "em đã chuyển anh Đại kiểm tra lịch học". The owner
then typed "lịch đã xác nhận 20h ngày 21 và ngày 22" and pressed Javis soạn; the draft still said "em chưa có lịch
xác nhận, em đã nhờ anh Đại kiểm tra". The order rode only as a soft note BEFORE the customer's words, while the
system prompt said "no document matched: say you have no information". Locked here:
  1. With an order, the system prompt ends with the owner's order block, stated as confirmed facts above the
     documents and the chat history, forbidding "chưa xác nhận" / "đang kiểm tra" hedges.
  2. With an order, the "document-only bot, nothing found, say you do not know" block is NOT in the prompt.
  3. The note in the turn comes AFTER the customer's words (the last thing the model reads).
  4. Without an order, the prompt and the turn text are exactly as before (no order block, no note).
  5. The order never leaks into the next live turn of the same bot.
  6. No fixed list of banned phrases (owner, same day: "không linh hoạt"): one principle, the order wins.
  7. Learning (owner, same day): a sent reply the owner ordered or rewrote goes into the Agent's knowledge file, newest
     on top, one entry per order, attached to the Agent's Documents so the bot reads it; an untouched A.I. draft
     teaches nothing; a later customer question finds it in the bot's document search.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-lenhchu-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them)[:400] + "]") if them != "" and not cond else ""))
    if not cond:
        fails.append(name)


SENDER = "1000000001"      # fake platform ids, never real people
ACCOUNT = "acc-test-1"
BRAIN = Path(tempfile.mkdtemp(prefix="brain-lenhchu-"))
prompts, texts = [], []


async def _answer(text, meta=None, progress=None, channel="telegram", bot=None, **kw):
    prompts.append(chatbot_runtime.build_bot_prompt(bot))
    texts.append(text)
    return {"text": "Dạ lịch học đợt tới là 20h ngày 21 và ngày 22 ạ.", "files": []}


chatbot_runtime.wire(answer=_answer, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Trợ lý thử", "role": "Trực kênh"}, "Luật riêng của Agent."))
bid, loi = chatbot_store.create_bot({"name": "Bot thử", "agent_slug": "tro-ly", "brain": "b",
                                     "token": "1:x", "channel": "zalo", "muc_quyen": "suggest",
                                     "audience": "all", "xac_nhan_rui_ro": True})
check("(setup) bot created", bool(bid) and not loi, loi)
ok, loi = chatbot_store.update_bot(bid, {"nguon_tra_loi": "tai_lieu"})
check("(setup) bot answers from documents only", ok and (chatbot_store.get_bot(bid) or {}).get("nguon_tra_loi") == "tai_lieu",
      loi)

conv = {"id": "c1", "bot_id": bid, "channel": "zalo_personal", "channel_account_id": "zalo_personal:" + ACCOUNT,
        "external_chat_id": SENDER, "chat_type": "private", "title": ""}
msgs = [{"sender_type": "customer", "text": "Cho mình xin lịch học qua zoom", "sender_id": SENDER,
         "sender_name": "Khách", "external_message_id": "x1", "created_at": 1},
        {"sender_type": "ai", "text": "Dạ em đã chuyển anh Đại kiểm tra lịch học đợt tới giúp bác.", "created_at": 2},
        {"sender_type": "customer", "text": "Oke nhắn mình lịch học đợt tới nhé", "sender_id": SENDER,
         "sender_name": "Khách", "external_message_id": "x3", "created_at": 3}]
LENH = "lịch đã xác nhận 20h ngày 21 và ngày 22"

# ---- 1-3. with an order
r = asyncio.run(chatbot_runtime.manual_answer(conv, msgs, draft=True, instruction=LENH))
check("draft with an order answers", r.get("ok") and not r.get("silent"), r)
p, t = prompts[-1], texts[-1]
head = "## LỆNH CỦA CHỦ CHO CÂU TRẢ LỜI NÀY"
check("system prompt carries the owner's order block, with the order", head in p and LENH in p, p[-800:])
check("the order block is the LAST part of the system prompt", p.rstrip().endswith(
    chatbot_runtime._LENH_CHU.format(lenh=LENH).rstrip()), p[-400:])
blk = " ".join((p[p.index(head):] if head in p else "").split())
check("the block puts the owner's newest word above documents and chat history",
      "lời mới nhất của chủ" in blk and "tài liệu" in blk and "trước đó trong cuộc chat" in blk and "theo lệnh" in blk, blk)
# Owner 2026-11-19: no fixed list of banned phrases, so an order like "báo khách là đang kiểm tra" still works.
check("no fixed list of banned phrases in the order texts", not any(
    w in (chatbot_runtime._LENH_CHU + chatbot_runtime._INSTRUCTION_NOTE).lower()
    for w in ("chưa xác nhận", "đang kiểm tra", "đang chờ kiểm tra", "nhờ người khác", "không nói")), blk)
check("document-only bot: 'nothing found, say you do not know' is dropped when the owner gave the answer",
      chatbot_runtime._KHONG_TAI_LIEU_CHAT.strip() not in p, p)
note = chatbot_runtime._INSTRUCTION_NOTE.format(lenh=LENH)
check("the turn: customer's words first, the owner's note after them",
      "Oke nhắn mình lịch học đợt tới nhé" in t and note in t
      and t.index("Oke nhắn mình lịch học đợt tới nhé") < t.index(note) and t.rstrip().endswith(note), t)
# ---- order with no customer message waiting: the note alone
r = asyncio.run(chatbot_runtime.manual_answer(conv, [msgs[1]], draft=True, instruction=LENH))
check("order alone (no customer message): the turn is the note alone", texts[-1] == note and head in prompts[-1],
      texts[-1])
r = asyncio.run(chatbot_runtime.manual_answer(conv, msgs, draft=True, instruction='báo "20h" ngày 21'))
check("a quote in the order cannot break the note's quotes", "\"báo '20h' ngày 21\"" in texts[-1]
      and "\"báo '20h' ngày 21\"" in prompts[-1], texts[-1])

# ---- 4. without an order nothing changes
r = asyncio.run(chatbot_runtime.manual_answer(conv, msgs, draft=True))
check("no order: no order block, no note", head not in prompts[-1] and "Lệnh của chủ" not in texts[-1], texts[-1])
check("no order: the document-only rule still applies", chatbot_runtime._KHONG_TAI_LIEU_CHAT.strip() in prompts[-1],
      prompts[-1][-400:])

# ---- 5. no leak into the next live turn
fn = chatbot_runtime._make_answer_fn(bid)
asyncio.run(chatbot_runtime.manual_answer(conv, msgs, draft=True, instruction=LENH))
before = len(prompts)
meta = {"chat_type": "private", "chat_id": SENDER, "user_id": SENDER, "user_name": "Khách", "platform": "zalo_personal",
        "_kenh": "zalo_personal", "account_id": ACCOUNT, "message_id": "m9", "mentioned": True}
asyncio.run(fn("cho em hỏi", meta))
check("the next live turn has no order block", len(prompts) > before and head not in prompts[-1],
      prompts[-1][-300:] if len(prompts) > before else "no turn")
check("the stored bot never keeps the order", "_lenh_chu" not in (chatbot_store.get_bot(bid) or {}))

# ---- 7. learning from what the owner confirmed
import chatbot_grounding  # noqa: E402
ATTACHED = []
chatbot_runtime._deps["agent_add_doc"] = lambda brain, slug, rel, name="": ATTACHED.append((brain, slug, rel, name))
check("should_learn: the owner's order", chatbot_runtime.should_learn("x", "lịch 21", "x"))
check("should_learn: the owner rewrote the draft", chatbot_runtime.should_learn("Dạ 20h ạ", "", "Dạ 19h ạ"))
check("should_learn: an untouched A.I. draft (spaces aside) teaches nothing",
      not chatbot_runtime.should_learn("Dạ  20h ạ\n", "", "Dạ 20h ạ"))
SENT = "Dạ bác, lịch học đợt tới là 20h ngày 21 và ngày 22 ạ."
r = chatbot_runtime.learn_from_owner(conv, msgs, SENT, LENH, "Dạ em chưa có lịch ạ")
rel = f"{chatbot_runtime.LEARN_DIR}/tro-ly.md"
f = BRAIN / rel
body = f.read_text(encoding="utf-8") if f.is_file() else ""
check("learned: the knowledge file is written in the Agent's brain", r.get("learned") and r.get("path") == rel and f.is_file(), r)
check("learned: the entry holds the question, the owner's order and the sent reply",
      "- Khách hỏi: Oke nhắn mình lịch học đợt tới nhé" in body and f"- Chủ xác nhận: {LENH}" in body
      and f"- Câu đã gửi khách: {SENT}" in body, body)
check("learned: the file is attached to the Agent's Documents", ATTACHED and ATTACHED[-1][1:3] == ("tro-ly", rel), ATTACHED)
r = chatbot_runtime.learn_from_owner(conv, msgs, "Dạ lịch học là 20h ngày 21 và 22 bác nhé.", LENH, "")
body = f.read_text(encoding="utf-8")
check("the same order again keeps one entry, the newest", body.count(f"- Chủ xác nhận: {LENH}") == 1
      and "20h ngày 21 và 22 bác nhé" in body and SENT not in body, body)
r = chatbot_runtime.learn_from_owner(conv, msgs, "Dạ học phí K8 là 2 triệu ạ.", "học phí K8 2 triệu", "")
body = f.read_text(encoding="utf-8")
check("newest entry on top", body.index("học phí K8 2 triệu") < body.index(LENH), body)
r = chatbot_runtime.learn_from_owner(conv, msgs, "Dạ\n## không phải tiêu đề\n- x", "", "Dạ ạ")
check("a multi-line rewrite is learned and stays inside its entry", r.get("learned")
      and "\n## không phải" not in f.read_text(encoding="utf-8") and "Dạ ## không phải tiêu đề - x" in f.read_text(encoding="utf-8"), r)
r = chatbot_runtime.learn_from_owner(conv, msgs, "Dạ vâng ạ", "", "Dạ vâng ạ")
check("an untouched draft is not learned", not r.get("learned") and r.get("reason") == "nothing_new", r)
hits = chatbot_grounding.thu_thap(str(BRAIN), "lịch học đợt tới khi nào", 4, None, "", (rel,))
check("a later customer question finds the confirmed answer in the bot's documents",
      hits.get("co") and LENH in (hits.get("khoi") or ""), hits)
cap = chatbot_runtime.LEARN_MAX_ENTRIES
chatbot_runtime.LEARN_MAX_ENTRIES = 3
for i in range(5):
    chatbot_runtime.learn_from_owner(conv, msgs, f"Dạ mục {i} ạ", f"lệnh số {i}", "")
chatbot_runtime.LEARN_MAX_ENTRIES = cap
check("the file keeps only the newest entries", f.read_text(encoding="utf-8").count("\n## ") <= 3
      and "lệnh số 4" in f.read_text(encoding="utf-8") and "lệnh số 0" not in f.read_text(encoding="utf-8"))
r = chatbot_runtime.learn_from_owner({"bot_id": "khong-co"}, msgs, "x", "y", "")
check("unknown bot: nothing learned, no error", not r.get("learned") and r.get("reason") == "no_agent", r)

check("no em or en dash in the order texts or this test", not any(
    d in s for d in (chr(0x2014), chr(0x2013))
    for s in (chatbot_runtime._LENH_CHU, chatbot_runtime._INSTRUCTION_NOTE, open(__file__, encoding="utf-8").read())))

if fails:
    print(f"\nĐỎ: {len(fails)}: " + " | ".join(fails))
    sys.exit(1)
print("\nOK - test_chatbot_lenh_chu: tất cả pass")
