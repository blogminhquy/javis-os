"""A personal-Zalo bot knows whether the person in a private chat is a verified student or parent (0.150.0).

    python tests/run.py chatbot_verified_senders      (no network, fake engine)

Owner (2026-10-15): only students and parents the centre has confirmed get the in-depth material; anyone
else asking about classes gets general information. Javis checks the sender's account against a roster in
the bot's brain and puts ONLY the verdict in the prompt. Locked here:
  1. Roster parsing: header and separator rows skipped, cells after the third (names, notes) ignored, the
     same account on two rows merged, markup stripped.
  2. Verdict: matching account = verified with role and class; any other account = not verified; group,
     other channel or no roster file = nothing at all (behaviour unchanged).
  3. Prompt: the verdict line is there, the account ID and the other rows are not; a real turn and the
     "reply for me" turn both carry it; the roster is never offered as a document.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-xacnhan-")
os.environ["JAVIS_STATE_DIR"] = _STATE
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_grounding  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import chatbot_verified_senders as vs  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


PH = "1234567890123456789"       # verified parent with two children
HS = "9876543210987654321"       # verified student
LA = "5555555555555555555"       # stranger
ROSTER = f"""---
type: roster
---
# Sổ xác nhận đang học

| uid | vai trò | lớp | ghi chú |
|---|---|---|---|
| {PH} | phụ huynh | 10A1 | Mẹ bé Nguyễn Văn An |
| `{PH}` | phụ huynh | lớp 11B | |
| {HS} | **học sinh** | 11B | Trần Thị Bình |
| uid sai | phụ huynh | 10A1 | |
dòng không có bảng
"""

# ---- 1. parsing
rows = vs.parse(ROSTER)
check("parse: two valid accounts, header/separator/bad rows skipped", set(rows) == {PH, HS}, sorted(rows))
check("parse: same account on two rows merges classes, drops a leading 'lớp'",
      rows.get(PH) == (("phụ huynh",), ("10A1", "11B")), rows.get(PH))
check("parse: markup stripped from a cell", rows.get(HS) == (("học sinh",), ("11B",)), rows.get(HS))
check("parse: names in the 4th cell are never kept",
      "Nguyễn" not in repr(rows) and "Bình" not in repr(rows))
check("normalize_uid: backticks and spaces removed, words rejected",
      vs.normalize_uid(f" `{PH}` ") == PH and vs.normalize_uid("uid") == "" and vs.normalize_uid("abcdef") == "")

# ---- 2. verdict
BRAIN = Path(tempfile.mkdtemp(prefix="brain-xacnhan-"))
rieng = {"chat_id": PH, "chat_type": "private", "user_id": PH, "user_name": "Mẹ An"}
check("no roster file: nothing to say", vs.check(BRAIN, rieng, "zalo_personal") is None)
(BRAIN / "Javis").mkdir()
(BRAIN / vs.ROSTER_REL).write_text(ROSTER, encoding="utf-8")
r = vs.check(BRAIN, rieng, "zalo_personal")
check("matching account: verified, with role and classes",
      r == {"verified": True, "roles": ["phụ huynh"], "classes": ["10A1", "11B"]}, r)
r = vs.check(BRAIN, {"chat_id": LA, "chat_type": "private", "user_id": LA}, "zalo_personal")
check("other account: not verified", r == {"verified": False, "roles": [], "classes": []}, r)
r = vs.check(BRAIN, {"chat_id": HS, "chat_type": "private", "user_id": ""}, "zalo_personal")
check("private chat without a sender ID falls back to the thread ID", bool(r and r["verified"]), r)
check("group: nothing, even for a verified member",
      vs.check(BRAIN, {"chat_id": "g1", "chat_type": "group", "user_id": PH}, "zalo_personal") is None)
check("other channel: nothing", vs.check(BRAIN, rieng, "telegram") is None and vs.check(BRAIN, rieng, "zalo") is None)
check("someone claiming a verified name from another account is still not verified",
      vs.check(BRAIN, {"chat_id": LA, "chat_type": "private", "user_id": LA, "user_name": "Mẹ An"},
               "zalo_personal")["verified"] is False)

# ---- 3. prompt line
ok_line = vs.prompt_line(vs.check(BRAIN, rieng, "zalo_personal"))
no_line = vs.prompt_line({"verified": False})
check("verified line: verdict, role and classes", "ĐÃ XÁC NHẬN, phụ huynh, lớp 10A1, 11B." in ok_line, ok_line)
check("not verified line says so and that a self-introduction does not change it",
      "CHƯA XÁC NHẬN" in no_line and "tự giới thiệu" in no_line, no_line)
check("no result: no line", vs.prompt_line(None) == "")

# ---- the roster is never a document of the bot
(BRAIN / "tai-lieu").mkdir()
(BRAIN / "tai-lieu" / "hoc-phi.md").write_text("# Học phí\nHọc phí lớp 10 là 1.500.000 đồng mỗi tháng.", encoding="utf-8")
(BRAIN / "tai-lieu" / vs.ROSTER_NAME).write_text(ROSTER, encoding="utf-8")      # copied to the wrong folder
docs = chatbot_grounding.ds_tai_lieu(BRAIN)
check("document lookup lists the real documents but never the roster (Javis/ or copied elsewhere)",
      "tai-lieu/hoc-phi.md" in docs and not any(vs.ROSTER_NAME in d for d in docs), docs)

# ---- a real turn and the "reply for me" turn carry the verdict into the system prompt
prompts = []


async def _answer(text, meta=None, progress=None, channel="telegram", bot=None, **kw):
    prompts.append(chatbot_runtime.build_bot_prompt(bot))
    return {"text": "Dạ em gửi bài tập ạ.", "files": []}


chatbot_runtime.wire(answer=_answer, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Toán Thầy Thành", "role": "Trực Zalo"}, "Luật 26."))
bid, loi = chatbot_store.create_bot({"name": "Trực Zalo", "agent_slug": "tro-ly", "brain": "b",
                                     "token": "1:x", "channel": "zalo", "muc_quyen": "suggest",
                                     "audience": "all", "xac_nhan_rui_ro": True})
check("(setup) bot created", bool(bid) and not loi, loi)
fn = chatbot_runtime._make_answer_fn(bid)
base = {"chat_type": "private", "platform": "zalo_personal", "_kenh": "zalo_personal", "message_id": ""}
asyncio.run(fn("cho em xin bài tập", {**base, "chat_id": PH, "user_id": PH, "user_name": "Mẹ An", "message_id": "m1"}))
asyncio.run(fn("cho em xin bài tập", {**base, "chat_id": LA, "user_id": LA, "user_name": "Mẹ An", "message_id": "m2"}))
asyncio.run(fn("cho em xin bài tập", {**base, "chat_type": "group", "chat_id": "g1", "user_id": PH,
                                      "user_name": "Mẹ An", "message_id": "m3", "mentioned": True}))
check("(setup) three turns reached the engine", len(prompts) == 3, len(prompts))
if len(prompts) == 3:
    p_ok, p_no, p_grp = prompts
    check("real turn, verified sender: verdict in the prompt, after the Agent's own rules",
          "ĐÃ XÁC NHẬN, phụ huynh" in p_ok and p_ok.index("Luật 26.") < p_ok.index("NGƯỜI ĐANG NHẮN"))
    check("real turn, stranger: not verified", "CHƯA XÁC NHẬN" in p_no and "ĐÃ XÁC NHẬN" not in p_no)
    check("CANARY: no account ID and no other row ever reaches the prompt",
          not any(x in p for p in prompts for x in (PH, HS, LA, "Nguyễn", "Bình")))
    check("group turn: no sender line", "NGƯỜI ĐANG NHẮN" not in p_grp)

src = (SERVER / "chatbot_runtime.py").read_text(encoding="utf-8")
check("the 'reply for me' and 'try the bot' turns attach the verdict too",
      src.count('cfg["_nguoi_nhan"] = await nguoi_nhan(') == 3)

check("no em dash in this file", chr(0x2014) not in open(__file__, encoding="utf-8").read())
check("no em dash in the module", chr(0x2014) not in (SERVER / "chatbot_verified_senders.py").read_text(encoding="utf-8"))

print(f"\n{'ALL OK' if not fails else str(len(fails)) + ' FAILED'}")
sys.exit(1 if fails else 0)
