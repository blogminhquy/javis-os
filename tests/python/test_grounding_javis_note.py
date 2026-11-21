"""The bot's document search reads the customer's words only, never the notes Javis adds to a turn (issue #1701).

    python tests/run.py grounding_javis_note      (no network)

On a personal Zalo account a customer's messages are held while the owner types by hand, then handed to the bot with a
note appended to the text ("[Ghi chú của Javis, không phải lời khách: ...]", `zalo_personal_channel.gop_cho_chu`). The
note is for the model. Before the fix its ~30 words went into the keyword search together with the question, the real
question was diluted below the relevance floor, and the bot said it had no information about a class schedule that was
in its documents.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-gjn-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_grounding as cg  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


BRAIN = Path(tempfile.mkdtemp(prefix="javis-gjn-brain-"))
(BRAIN / "wiki").mkdir()
(BRAIN / "wiki" / "lich-hoc.md").write_text(
    "# Lịch học và giá\n\n"
    "## Chánh Kiến 1\n\n"
    "Lớp Chánh Kiến 1 khai giảng ngày 09-10/01/2027 tại Hà Nội, học phí 3.500.000đ.\n"
    "Lớp Chánh Kiến 1 tiếp theo ngày 20-21/02/2027 tại TP.HCM.\n\n"
    "## Chánh Niệm 2\n\n"
    "Lớp Chánh Niệm 2 khai giảng ngày 15/03/2027 tại Đà Nẵng.\n", encoding="utf-8")
(BRAIN / "wiki" / "noi-quy.md").write_text(
    "# Nội quy lớp\n\nHọc viên đến đúng giờ, tắt điện thoại, mặc trang phục lịch sự.\n", encoding="utf-8")
FILES = ("wiki/lich-hoc.md", "wiki/noi-quy.md")

QUESTION = "A chưa thấy lịch chánh kiến 1"

# The held turn exactly as the channel builds it: the customer's message plus the hand-over note.
now = time.time()
ev = {"external_chat_id": "t1", "sender_id": "u1", "chat_type": "private", "message_type": "text",
      "text": QUESTION, "created_at": now - 30, "external_message_id": "m1", "metadata": {}}
held = zc.gop_cho_chu([ev], cho=600, tay=now - 700)
check("the held turn carries the hand-over note in its text",
      held["text"].startswith(QUESTION) and "[Ghi chú của Javis" in held["text"], held["text"])

plain = cg.thu_thap(BRAIN, QUESTION, 4, None, None, FILES)
noted = cg.thu_thap(BRAIN, held["text"], 4, None, None, FILES)
check("the plain question finds the schedule", plain["co"] and "wiki/lich-hoc.md" in plain["nguon"], str(plain)[:200])
check("the same question with the note finds the same documents",
      noted["co"] and noted["nguon"] == plain["nguon"] and noted["khoi"] == plain["khoi"], str(noted)[:200])

# The owner-has-not-answered wording and a note listing attachments are stripped the same way.
held2 = zc.gop_cho_chu([ev, dict(ev, message_type="file", text="[file]", external_message_id="m2",
                                 metadata={"attachment": {"name": "bao-gia.pdf"}})], cho=600, tay=0)
check("a note that lists an attached file is stripped too",
      cg.customer_words(held2["text"]).startswith(QUESTION) and "Ghi chú của Javis" not in cg.customer_words(held2["text"]),
      cg.customer_words(held2["text"]))

# The "an earlier photo rides along" line of a private turn is Javis's too.
with_photo = QUESTION + "\n[Kèm ảnh khách gửi lúc 16:28 trong cuộc chat này, có thể liên quan tới tin trên]"
check("the earlier-photo line is not searched", cg.customer_words(with_photo) == QUESTION)

# What the customer wrote is never touched: brackets of their own, a quoted note in the middle of a sentence.
own = "cho hỏi [lớp Chánh Kiến 1] còn chỗ không"
check("the customer's own brackets stay", cg.customer_words(own) == own)
mid = "bạn em bảo [Ghi chú của Javis là gì vậy"
check("only a whole note LINE is dropped, not words inside a sentence", cg.customer_words(mid) == mid)
check("a turn that is only the note searches nothing",
      cg.customer_words("[Ghi chú của Javis, không phải lời khách: khách gửi kèm một file.]") == ""
      and cg.thu_thap(BRAIN, "[Ghi chú của Javis, không phải lời khách: khách gửi kèm một file.]", 4, None, None, FILES)
      == {"co": False, "khoi": "", "nguon": []})
check("None and empty are safe", cg.customer_words(None) == "" and cg.customer_words("") == "")

print()
if _fails:
    print(f"RED {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("All green.")
