"""Personal Zalo bot: on-duty alerts reach a person, and the owner's role file beats Javis's default (0.155.0).

    python tests/run.py bot_zalo_nguoi_truc      (no network, fake MCP)

Two bugs found on a real bot on 2026-10-15:

1. `handoff_to` did nothing on personal Zalo. The alert always went out through Telegram's `sendMessage`
   URL, which the Zalo transport does not have; the exception was swallowed, so the bot told the customer
   "a person will help you" and nobody was told. /nhanvien and "stuck on N messages" broke the same way.
2. The paragraph Javis adds for personal Zalo ("private matters: do NOT reply, write [IM_LANG]") came
   AFTER the owner's role file and overrode it: the role file said a student sharing something personal
   still gets one short reply, yet "Thầy ơi con buồn quá, con mới chia tay người yêu" ended in agent_silent.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpnt-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CONN = {"id": "zalo-1", "label": "Zalo của tôi", "connector_id": "zalo"}
GUI = []
HONG = {"v": False}


async def _goi_gia(conn, tool, args):
    if tool == "zalo_send_message":
        if HONG["v"]:
            return {"success": False, "error": "Không tìm thấy cuộc trò chuyện"}
        GUI.append(dict(args))
        return {"success": True}
    return {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _goi_gia

AGENT = {"v": ({"name": "Trợ lý", "role": "Trợ lý lớp học"},
               "Học sinh kể chuyện riêng thì vẫn đáp một câu ngắn rồi kéo về việc lớp.")}
chatbot_runtime.wire(answer=lambda *a, **k: None, brain_root=lambda b: tempfile.mkdtemp(prefix="brain-"),
                     read_agent=lambda br, slug: AGENT["v"])

bid, loi = chatbot_store.create_bot({"name": "Trợ lý Zalo", "agent_slug": "tro-ly", "brain": "b",
                                     "account_ids": ["zalo-1"], "muc_quyen": "suggest",
                                     "handoff_to": "u-giao-vu"})
check("tạo bot Zalo cá nhân có người trực", bool(bid) and not loi, loi)
cfg = chatbot_store.get_bot(bid)
META = {"chat_id": "u1", "chat_type": "private", "user_name": "Phụ huynh A", "account_id": "zalo-1"}

# ============================================================
# 1. handoff_to on personal Zalo
# ============================================================
check("id thường là chat riêng", chatbot_runtime.handoff_target(" 123 ") == ("123", "private"))
check("nhom:<id> và group:<id> là nhóm",
      chatbot_runtime.handoff_target("nhom:g9") == ("g9", "group")
      and chatbot_runtime.handoff_target("Group: g9") == ("g9", "group"))


async def chay():
    ok, err = await chatbot_runtime._gui_nhan_vien(cfg, "u-giao-vu", "u1", "Bí 2 câu liên tiếp.", META)
    check("báo người trực qua Zalo cá nhân THÀNH CÔNG (trước đây gọi _url của Telegram và nuốt lỗi)", ok, err)
    check("gửi tới đúng người trực, kiểu chat riêng, qua MCP của kênh",
          GUI and GUI[-1]["threadId"] == "u-giao-vu" and GUI[-1]["threadType"] == 0, GUI)
    check("tin báo có tên người nhắn và lý do (không chỉ một dãy số id)",
          GUI and "Phụ huynh A" in GUI[-1]["text"] and "Bí 2 câu" in GUI[-1]["text"], GUI)
    check("câu vừa gửi được nhớ làm tiếng vọng (không bị tưởng là chủ nhắn tay trong chat đó)",
          ("zalo-1", "u-giao-vu") in zc._DA_GUI)

    ok, err = await chatbot_runtime._gui_nhan_vien(cfg, "nhom:g-giao-vu", "u1", "Xin gặp người.", META)
    check("nhom:<id> gửi vào NHÓM (threadType 1)", ok and GUI[-1]["threadId"] == "g-giao-vu"
          and GUI[-1]["threadType"] == 1, GUI[-1] if GUI else err)

    HONG["v"] = True
    ok, err = await chatbot_runtime._gui_nhan_vien(cfg, "u-sai", "u1", "Xin gặp người.", META)
    check("gửi hỏng thì trả lỗi thật của kênh", not ok and "Không tìm thấy" in err, err)
    check("và lỗi đó nằm lại để thẻ bot báo đỏ", "Không tìm thấy" in chatbot_runtime.loi_bao_nguoi(bid))
    HONG["v"] = False
    ok, _ = await chatbot_runtime._gui_nhan_vien(cfg, "u-giao-vu", "u1", "Xin gặp người.", META)
    check("lần báo sau tới nơi thì thẻ hết đỏ", ok and chatbot_runtime.loi_bao_nguoi(bid) == "")

    # /nhanvien goes through the same path.
    n = len(GUI)
    res = await chatbot_runtime._make_command_fn(cfg)("nhanvien", "", "u1", dict(META))
    await asyncio.sleep(0.05)
    check("/nhanvien nói với khách là đang chuyển người", "chuyển" in (res or {}).get("reply", ""), res)
    check("/nhanvien báo người trực thật qua Zalo", len(GUI) == n + 1 and GUI[-1]["threadId"] == "u-giao-vu"
          and "chủ động xin gặp" in GUI[-1]["text"], GUI[n:])

    ok, err = await chatbot_runtime.gui_nguoi_truc(cfg, "", "x")
    check("chưa khai người nhận thì báo rõ, không gửi gì", not ok and err, err)

    # Telegram still goes through its own channel module.
    tg = channels.module("telegram")
    goc, da = tg.gui, []

    async def _tg_gui(tk, chat_id, text, chat_type="private"):
        da.append((tk.get("token"), chat_id, chat_type))
        return True, ""
    tg.gui = _tg_gui
    try:
        tid, tloi = chatbot_store.create_bot({"name": "TG", "agent_slug": "t", "brain": "b",
                                             "token": "123:abc", "channel": "telegram", "handoff_to": "-100"})
        ok, err = await chatbot_runtime._gui_nhan_vien(chatbot_store.get_bot(tid), "-100", "9", "x", {})
        check("Telegram vẫn gửi bằng token của bot tới chat id đã khai", ok and da == [("123:abc", "-100", "private")],
              (tloi, err, da))
    finally:
        tg.gui = goc


asyncio.run(chay())

# ============================================================
# 2. The owner's role file beats Javis's personal-Zalo default
# ============================================================
_bot = {"name": "Trợ lý", "agent": {"brain": "b", "slug": "tro-ly"}, "_kenh_luot": "zalo_personal"}
p = chatbot_runtime.build_bot_prompt(_bot)
check("Zalo cá nhân vẫn có đoạn mặc định (im khi không chắc)", "[IM_LANG]" in p)
check("đoạn mặc định nói thẳng hướng dẫn vai của chủ THẮNG nó", "LUÔN thắng đoạn này" in p)
check("đoạn mặc định đứng TRƯỚC file Agent (luật chủ đọc sau cùng)",
      0 <= p.index("Zalo CÁ NHÂN của chủ") < p.index("Học sinh kể chuyện riêng"), p)
check("lệnh im chuyện riêng chỉ áp cho loại tin hướng dẫn vai KHÔNG nói tới",
      p.index("hướng dẫn vai KHÔNG nói tới") < p.index("chuyện riêng tư, chuyện gia đình"))
check("Telegram không có đoạn này", "[IM_LANG]" not in chatbot_runtime.build_bot_prompt(dict(_bot, _kenh_luot="telegram")))
AGENT["v"] = ({}, "")
p0 = chatbot_runtime.build_bot_prompt(_bot)
check("bot không nạp được Agent vẫn giữ mặc định an toàn (im)",
      "[IM_LANG]" in p0 and "chưa nạp được hướng dẫn" in p0)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
