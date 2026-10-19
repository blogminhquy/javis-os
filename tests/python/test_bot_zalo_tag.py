"""Bot trong nhóm Zalo cá nhân tự TAG người nó đang trả lời (0.65.7).

    python tests/run.py bot_zalo_tag      (KHÔNG mạng, không gọi npx thật: MCP giả và CLI giả)

Chủ dự án (30/09/2026): khách hỏi trong nhóm thì bot mở đầu bằng "@Minh Quý ...". Tool gửi tin của MCP chỉ nhận chữ nên tag đi qua chính
`zalo-agent-cli` (`msg send --mention`), xem `server/zalo_cli.py`. Tin đi dưới TÊN CHỦ vào một nhóm thật, nên những chỗ có thể làm hỏng
được canh kỹ:

  1. HAI TIN. Hết giờ là kết cục KHÔNG RÕ (CLI có thể đã gửi xong mới bị giết). Gửi lại bằng MCP thì nhóm thấy hai câu dưới tên chủ.
     Chỉ khi CLI thất bại RÕ RÀNG mới rơi về gửi thường.
  2. BOT TỰ KHOÁ MIỆNG. Tiếng vọng của tin có tag mang cả "@Tên" nên không khớp câu bot đã nhớ; vòng đọc tưởng chủ vừa tự tay nhắn và bot
     im 10 phút. Phải nhớ luôn bản đã tag.
  3. VỊ TRÍ CHỮ. Zalo đo theo UTF-16 (emoji chiếm 2); "@Quý" không được ăn vào "@Quýnh".
  4. TAG HỎNG MÃI. Mỗi câu trả lời trả thêm vài giây cho một thứ đang hỏng: hỏng liên tiếp thì nghỉ, tin vẫn đi như cũ.
  5. TAG NHẦM. uid đi vào tham số lệnh nên phải là số; chưa biết tên người hỏi thì không có gì để tô, gửi thường.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zptag-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402
import zalo_cli  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


CID = "zalo-1"
GROUP = "5550001"
CONN = {"id": CID, "label": "Javis Vũ", "connector_id": "zalo", "env": {"HOME": "/state/zalo-1"}}
MCP = []          # mỗi lần gọi zalo_send_message
CLI = []          # mỗi lần chạy CLI: {"conn", "command", "pos", "opts", "timeout"}
NEXT = {"r": (True, {"message": {"msgId": "1"}}, "")}


async def fake_goi(conn, tool, args):
    if tool == "zalo_send_message":
        MCP.append(dict(args))
        return {"success": True}
    return {}


async def fake_run_cli(conn, command, positionals=None, options=None, timeout=120):
    CLI.append({"conn": dict(conn), "command": list(command), "pos": list(positionals or []),
                "opts": list(options or []), "timeout": timeout})
    return NEXT["r"]


zc.ket_noi_theo_id = lambda cid: dict(CONN) if cid == CID else None
zc._goi = fake_goi
zalo_cli.run_cli = fake_run_cli


def reset(res=(True, {"message": {"msgId": "1"}}, "")):
    MCP.clear()
    CLI.clear()
    NEXT["r"] = res
    zp._TAG_STATE.clear()
    zc._DA_GUI.clear()


def send(text, chat_type="group", mention=None, chat=GROUP):
    return asyncio.run(zp.gui({"id": CID}, chat, text, chat_type, mention))


LAN = {"uid": "7770001", "name": "Minh Quý"}

# ============================================================
# 1. Dựng chữ có tag
# ============================================================
t, pos, ln = zp.tagged_text("Dạ để em hướng dẫn nhé", "Minh Quý")
check("chưa có @Tên thì đặt '@Tên ' ở ĐẦU tin", t == "@Minh Quý Dạ để em hướng dẫn nhé" and pos == 0 and ln == 9, (t, pos, ln))
t, pos, ln = zp.tagged_text("Dạ anh @minh quý xem giúp nhé", "Minh Quý")
check("model đã tự viết @Tên (khác hoa thường) thì tag đúng chỗ đó, không tag hai lần",
      t == "Dạ anh @minh quý xem giúp nhé" and pos == 7 and ln == 9, (t, pos, ln))
t, pos, ln = zp.tagged_text("Chào @Quýnh nhé", "Quý")
check("CANARY: '@Quý' không ăn vào đầu '@Quýnh' (tên dài hơn của người khác)",
      t == "@Quý Chào @Quýnh nhé" and pos == 0 and ln == 4, (t, pos, ln))
t, pos, ln = zp.tagged_text("🎉 chúc mừng @Minh Quý nhé", "Minh Quý")
check("CANARY: có emoji đứng trước thì vị trí tính theo UTF-16 (emoji = 2), không theo ký tự Python",
      pos == len("🎉 chúc mừng ") + 1 and t[len("🎉 chúc mừng "):].startswith("@Minh Quý"), (t, pos, ln))

check("uid phải là số, tên phải có",
      zp._clean_mention({"uid": "7770001", "name": "Quý"}) == ("7770001", "Quý")
      and zp._clean_mention({"uid": "12; rm -rf", "name": "Quý"}) == ("", "")
      and zp._clean_mention({"uid": "-1", "name": "Quý"}) == ("", "")
      and zp._clean_mention({"uid": "7770001", "name": "   "}) == ("", "")
      and zp._clean_mention({"uid": "", "name": "Quý"}) == ("", "")
      and zp._clean_mention(None) == ("", "") and zp._clean_mention("7770001") == ("", ""))
check("tên có nhiều dấu cách hoặc xuống dòng được gọn về một dòng",
      zp._clean_mention({"uid": "7770001", "name": "Minh   Quý\n"}) == ("7770001", "Minh Quý"))

# ============================================================
# 2. Gửi có tag qua CLI
# ============================================================
reset()
ok, loi = send("Dạ để em hướng dẫn nhé", mention=LAN)
check("nhóm + có người hỏi: gửi bằng CLI, KHÔNG qua MCP", ok and not loi and len(CLI) == 1 and MCP == [], (ok, loi, CLI, MCP))
c = CLI[0]
check("lệnh đúng: msg send <nhóm> <nội dung có tag> -t 1 --mention pos:uid:len",
      c["command"] == ["msg", "send"] and c["pos"] == [GROUP, "@Minh Quý Dạ để em hướng dẫn nhé"]
      and c["opts"] == ["-t", "1", "--mention", "0:7770001:9"], c)
check("chạy trong thư mục phiên của ĐÚNG tài khoản Zalo", c["conn"] == {"home": "/state/zalo-1"}, c["conn"])
check("có trần thời gian riêng cho một dòng chữ (không chờ 120 giây)", c["timeout"] == zp.TAG_TIMEOUT and zp.TAG_TIMEOUT <= 60)
check("CANARY: tiếng vọng của tin CÓ TAG được nhớ (không thì vòng đọc tưởng chủ tự nhắn và bot im 10 phút)",
      zc._la_tieng_vong(CID, GROUP, "@Minh Quý Dạ để em hướng dẫn nhé"))

reset()
ok, _ = send("Dạ anh @Minh Quý xem giúp em", mention=LAN)
check("model đã viết @Tên thì giữ nguyên chữ và tag đúng vị trí đó",
      ok and CLI[0]["pos"][1] == "Dạ anh @Minh Quý xem giúp em" and CLI[0]["opts"][-1] == "7:7770001:9", CLI)

reset()
ok, _ = send("- Bước 1: mở trang Models", mention=LAN)
check("tin bắt đầu bằng '-' vẫn ổn: chữ đã có '@Tên ' đứng đầu nên không thành cờ",
      ok and CLI[0]["pos"][1].startswith("@Minh Quý - Bước 1"), CLI)

# ============================================================
# 3. Khi nào KHÔNG tag
# ============================================================
reset()
ok, _ = send("Dạ em chào anh", chat_type="private", mention=LAN)
check("chat riêng: không tag, gửi thường qua MCP", ok and CLI == [] and len(MCP) == 1 and MCP[0]["threadType"] == 0, (CLI, MCP))

reset()
ok, _ = send("Dạ em chào", mention=None)
check("không biết người hỏi: gửi thường qua MCP (kiểu nhóm)", ok and CLI == [] and len(MCP) == 1 and MCP[0]["threadType"] == 1, (CLI, MCP))
for bad in ({"uid": "7770001", "name": ""}, {"uid": "abc", "name": "Quý"}, {"uid": "", "name": "Quý"}):
    reset()
    ok, _ = send("Dạ em chào", mention=bad)
    check(f"người hỏi thiếu tên hoặc uid lạ {bad}: gửi thường, không chạy CLI", ok and CLI == [] and len(MCP) == 1, (CLI, MCP))

reset()
CONN["env"] = {}
ok, _ = send("Dạ em chào", mention=LAN)
CONN["env"] = {"HOME": "/state/zalo-1"}
check("kết nối chưa có thư mục phiên: gửi thường qua MCP", ok and CLI == [] and len(MCP) == 1, (CLI, MCP))

# ============================================================
# 4. CLI hỏng
# ============================================================
reset((False, None, "Send failed: bạn không còn trong nhóm"))
ok, loi = send("Dạ để em hướng dẫn nhé", mention=LAN)
check("CLI thất bại RÕ RÀNG: rơi về gửi thường qua MCP, chữ NGUYÊN BẢN (không tag), người dùng vẫn nhận được câu trả lời",
      ok and len(CLI) == 1 and len(MCP) == 1 and MCP[0]["text"] == "Dạ để em hướng dẫn nhé" and MCP[0]["threadType"] == 1, (CLI, MCP))

reset((False, None, "máy chưa có Node.js 20+ (lệnh npx)"))
ok, _ = send("Dạ em chào", mention=LAN)
check("máy không có Node: vẫn gửi được bằng MCP", ok and len(MCP) == 1)

reset((False, None, "Zalo quá 40 " + zalo_cli.TIMEOUT_MARK))
ok, loi = send("Dạ để em hướng dẫn nhé", mention=LAN)
check("CANARY: hết giờ là kết cục KHÔNG RÕ nên KHÔNG gửi lại bằng MCP (tránh hai câu dưới tên chủ trong nhóm)",
      ok is False and MCP == [] and "không rõ" in loi, (ok, loi, MCP))

# ============================================================
# 5. Hỏng liên tiếp thì nghỉ
# ============================================================
reset((False, None, "lỗi lạ"))
for _ in range(zp.TAG_FAIL_LIMIT):
    send("Dạ em chào", mention=LAN)
n_cli = len(CLI)
check(f"hỏng {zp.TAG_FAIL_LIMIT} lần liên tiếp thì bắt đầu nghỉ tag", n_cli == zp.TAG_FAIL_LIMIT and zp._tag_paused(CID), (n_cli, zp._TAG_STATE))
MCP.clear()
ok, _ = send("Dạ em chào", mention=LAN)
check("đang nghỉ: KHÔNG chạy CLI nữa (khỏi trả thêm vài giây mỗi câu), tin vẫn đi bằng MCP", ok and len(CLI) == n_cli and len(MCP) == 1)
zp._TAG_STATE[CID]["until"] = time.time() - 1
NEXT["r"] = (True, {"message": {}}, "")
ok, _ = send("Dạ em chào", mention=LAN)
check("hết giờ nghỉ thì thử lại, thành công thì xoá dấu hỏng", ok and len(CLI) == n_cli + 1 and not zp._tag_paused(CID)
      and zp._TAG_STATE[CID]["fails"] == 0, zp._TAG_STATE)

reset((False, None, "lỗi lạ"))
send("a", mention=LAN)
send("b", mention=LAN)
NEXT["r"] = (True, {"message": {}}, "")
send("c", mention=LAN)
NEXT["r"] = (False, None, "lỗi lạ")
send("d", mention=LAN)
send("e", mention=LAN)
check("chỉ đếm hỏng LIÊN TIẾP: một lần thành công ở giữa thì đếm lại từ đầu", not zp._tag_paused(CID), zp._TAG_STATE)

# ============================================================
# 6. Nối vào Transport và channels.gui
# ============================================================
GOI = []


async def fake_gui(tk, chat_id, text, chat_type="private", mention=None):
    GOI.append({"tk": dict(tk), "chat": chat_id, "text": text, "type": chat_type, "mention": mention})
    return True, ""


real_gui = zp.gui
zp.gui = fake_gui
try:
    reset()
    tb = zp.Transport(CID, None, answer_fn=None)
    meta = {"user_id": "7770001", "user_name": "Minh Quý", "chat_id": GROUP}
    asyncio.run(tb._gui(GROUP, "Dạ em chào", "group", meta))
    check("Transport trả lời trong nhóm: truyền người hỏi (uid + tên) xuống lớp gửi",
          GOI[-1]["mention"] == {"uid": "7770001", "name": "Minh Quý"} and GOI[-1]["type"] == "group", GOI)
    check("và vẫn nhớ tiếng vọng của câu gốc TRƯỚC khi gửi", zc._la_tieng_vong(CID, GROUP, "Dạ em chào"))
    asyncio.run(tb._gui("5550002", "Dạ em chào", "private", meta))
    check("Transport trả lời chat riêng: không tag ai", GOI[-1]["mention"] is None, GOI[-1])
    asyncio.run(tb._gui(GROUP, "Dạ em chào", "group"))
    check("không có meta: không có ai để tag, không lỗi", zp._clean_mention(GOI[-1]["mention"]) == ("", ""), GOI[-1])
finally:
    zp.gui = real_gui

FWD = []


async def spy_gui(tk, chat_id, text, chat_type="private", **extra):
    FWD.append(dict(extra))
    return True, ""


mod = channels.module("zalo_personal")
real_mod_gui = mod.gui
mod.gui = spy_gui
try:
    asyncio.run(channels.gui("zalo_personal", {"id": CID}, GROUP, "x", "group", mention=LAN))
    asyncio.run(channels.gui("zalo_personal", {"id": CID}, GROUP, "x", "group"))
finally:
    mod.gui = real_mod_gui
check("channels.gui chuyển `mention` cho kênh, và không thêm gì khi người gọi không truyền", FWD == [{"mention": LAN}, {}], FWD)

# ============================================================
# 6. Tag MỌI người được nhắc "@Tên" trong câu (0.123.0)
# ============================================================
# Báo cáo 14/10/2026: bot được dặn tag "@Minh Quý" và "@Phạm Đại", viết đủ hai tên, nhưng chỉ người
# đang được trả lời có tag thật; tên còn lại là chữ thường nên Zalo không báo ai.
DANH_BA = [{"uid": "7770001", "name": "Minh Quý"}, {"uid": "7770002", "name": "Phạm Đại"},
           {"uid": "7770003", "name": "Minh Quý Trần"}, {"uid": "7770009", "name": "Javis Vũ"}]
zp._danh_ba_nhom = lambda cid, chat: list(DANH_BA)
zc._ID_MINH[CID] = {"uid": "7770009", "ten": "Javis Vũ"}
KHACH = {"uid": "7770005", "name": "Lan"}

reset()
ok, _ = send("Dạ em đã báo @Minh Quý và @Phạm Đại xem giúp chị ạ", mention=KHACH)
c = CLI[0] if CLI else {}
txt = "@Lan Dạ em đã báo @Minh Quý và @Phạm Đại xem giúp chị ạ"
specs = [x for x in c.get("opts", []) if x.count(":") == 2]
check("CANARY: người được trả lời VÀ hai người được nhắc tên đều có tag thật, một lần gửi",
      c.get("pos") == [GROUP, txt] and specs == [
          f"0:7770005:4", f"{txt.index('@Minh Quý')}:7770001:9", f"{txt.index('@Phạm Đại')}:7770002:9"], c)
check("các tag đi sau MỘT cờ --mention (CLI nhận danh sách)", c.get("opts", [])[:3] == ["-t", "1", "--mention"], c)

reset()
ok, _ = send("Anh @minh quy ơi, chị Lan hỏi giá", mention=None)
c = CLI[0] if CLI else {}
check("không có người được trả lời (chủ gõ ở Hộp thư) mà câu có @Tên: vẫn tag, không phân biệt hoa thường và dấu",
      ok and len(CLI) == 1 and MCP == [] and [x for x in c["opts"] if x.count(":") == 2] == ["4:7770001:9"], (CLI, MCP))

reset()
send("Nhờ @Minh Quý Trần kiểm tra", mention=None)
check("tên dài thắng tên ngắn trùng đầu ('@Minh Quý Trần' không thành '@Minh Quý')",
      CLI and [x for x in CLI[0]["opts"] if x.count(":") == 2] == ["4:7770003:14"], CLI)

reset()
send("Chào @Minh Quýnh và @Javis Vũ", mention=None)
check("không ăn vào đầu tên dài hơn ('@Minh Quýnh'), không tự tag chính tài khoản: gửi thường",
      CLI == [] and len(MCP) == 1, (CLI, MCP))

reset()
send("Gửi @Ai Đó lạ nhé", mention=None)
check("@Tên không có trong danh bạ nhóm: gửi thường qua MCP, không chạy CLI", CLI == [] and len(MCP) == 1, (CLI, MCP))

reset()
send("Dạ @Lan ơi, @Lan nhé", mention=KHACH)
check("người được trả lời được nhắc hai lần: chỉ một tag", CLI and len([x for x in CLI[0]["opts"] if x.count(":") == 2]) == 1, CLI)

# ============================================================
# Zalo's own mention markup (0.234.0)
# ============================================================
# Field report 2026-10-19: the group saw `<a_mention href="zm://Profile/..._mention">@Minh</a_mention> Quý Dạ anh`
# as plain code. The markup goes, the person still gets a real tag.
RAW = '<a_mention href="zm://Profile/7770001_mention">@Minh</a_mention> Quý Dạ anh 😊'
check("markup stripped, the @Name between the tags stays",
      zc.strip_mention_markup(RAW) == "@Minh Quý Dạ anh 😊"
      and zc.strip_mention_markup('<A_MENTION href="x">@Lan</A_MENTION>') == "@Lan"
      and zc.strip_mention_markup("Dạ anh <3 nhé") == "Dạ anh <3 nhé" and zc.strip_mention_markup(None) == "")

reset()
ok, _ = send(RAW, mention=LAN)
check("CANARY: group reply carrying the markup goes out clean, tagged at the right spot",
      ok and CLI and CLI[0]["pos"][1] == "@Minh Quý Dạ anh 😊" and CLI[0]["opts"][-1] == "0:7770001:9", CLI)

reset()
ok, _ = send(RAW, chat_type="private")
check("private chat: markup stripped too, and the cleaned text is remembered as our echo",
      ok and MCP and MCP[0]["text"] == "@Minh Quý Dạ anh 😊" and zc._la_tieng_vong(CID, GROUP, "@Minh Quý Dạ anh 😊"), MCP)

ev = zc.chuan_hoa_tin(CONN, {"threadId": GROUP, "type": 1, "senderId": "7770002", "senderName": "Lan",
                             "text": '<a_mention href="zm://Profile/7770001_mention">@Minh Quý</a_mention> xem giúp em'}, {})
check("incoming message: the bot reads @Name, never the markup (so it does not copy it)",
      ev and ev["text"] == "@Minh Quý xem giúp em", ev)

check("không dùng em dash trong file này và code mới", chr(0x2014) not in open(__file__, encoding="utf-8").read()
      and chr(0x2014) not in (SERVER / "channels" / "zalo_personal.py").read_text(encoding="utf-8"))

if fails:
    print("\nFAIL - test_bot_zalo_tag: " + str(len(fails)) + " lỗi: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_bot_zalo_tag: tất cả pass")
