"""Bot chuyên trách tự trả lời trên Zalo CÁ NHÂN (0.64.80).

    python tests/run.py bot_zalo_ca_nhan      (KHÔNG mạng, MCP giả)

Chủ repo hỏi 29/09/2026: "thêm zalo rồi thì làm thế nào để bot phản hồi lại ở zalo cá nhân?" -
lúc đó Zalo cá nhân chỉ GHI tin vào Hộp thư, bot chỉ gắn được Telegram và Zalo Bot, và form "Bot
mới" không hề liệt kê Zalo. Chủ chọn: bot TỰ TRẢ LỜI và TỰ QUYẾT có nên trả lời không, không
công tắc từng người (nick này chủ tự quản lý, đã có Hộp thư để giám sát).

Vì tin gửi đi mang TÊN CHỦ nên các rào dưới đây là phần quan trọng nhất của file này:

  1. Chỉ tin dạng CHỮ: ảnh, tiếng, file bỏ qua. Nhóm CHƯA cho phép cũng bỏ qua (từ 0.64.82 nhóm đã
     cho phép được trả lời, xem test_bot_zalo_nhom.py).
  2. Tin CŨ (bộ đệm MCP lúc mới bật) bỏ qua, kẻo dội lại câu hỏi của hôm qua.
  3. Chủ vừa TỰ TAY nhắn cuộc chat đó thì bot nhường.
  4. Câu bot vừa gửi quay về ở vòng đọc (tin của chính chủ) KHÔNG được ghi lần hai và KHÔNG được
     tính là "chủ tự nhắn" - nếu tính thì bot tự khoá miệng mình sau câu đầu tiên.
  5. Bot viết [IM_LANG] nghĩa là không gửi gì, không ghi như một câu bot nói.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpbot-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_accounts  # noqa: E402
import channels  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CONN = {"id": "zalo-1", "label": "Zalo của tôi", "connector_id": "zalo"}
GUI = []            # mọi lần gọi zalo_send_message
KHO_TIN = []        # tin "MCP" sẽ trả ở lần đọc kế tiếp
TRA_LOI = {"v": "Dạ em chào anh chị ạ"}
LUOT_ENGINE = []


def _ms(giay_truoc=0):
    return int((time.time() - giay_truoc) * 1000)


async def _goi_gia(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        return {"threads": [{"threadId": "u1", "name": "Khách A", "type": "user"},
                            {"threadId": "g1", "name": "Nhóm B", "type": "group"}]}
    if tool == "zalo_get_messages":
        tin = list(KHO_TIN)
        KHO_TIN.clear()
        return {"messages": tin, "nextCursor": "c" + str(time.time())}
    return {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _goi_gia
zc.CHO_KHACH_IM = 0          # giao từng tin ngay: file này canh các rào khác; cửa sổ chờ ở test_zalo_cho_khach_nhan_xong.py


async def _engine(text, meta, progress, *, channel="", bot=None):
    """Thay lõi model: ghi lại lượt và trả câu đã đặt."""
    LUOT_ENGINE.append({"text": text, "channel": channel,
                        "prompt": chatbot_runtime.build_bot_prompt(bot)})
    return {"text": TRA_LOI["v"], "files": []}


chatbot_runtime.wire(answer=_engine, brain_root=lambda b: tempfile.mkdtemp(prefix="brain-"),
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Trợ lý bán hàng"}, "Tư vấn ngắn gọn."))

# ============================================================
# 1. Zalo cá nhân là một kênh gắn được bot, và hiện ra để CHỌN
# ============================================================
zp = channels.spec("zalo_personal")
check("Zalo cá nhân gắn được bot (có Transport) dù là kênh kind=account",
      zp and zp.kind == "account" and zp.nl("bot"))
check("nhưng KHÔNG dùng được để tạo tài khoản bằng token", "zalo_personal" not in channels.bot_token_ids())
# 0.64.82: bot đứng được trong nhóm Zalo đã cho phép, nên form phải hiện phần khai nhóm. Trước đó
# (0.64.80) test này khẳng định điều ngược lại vì bot chỉ trả lời chat riêng. Hành vi mới được
# canh ở test_bot_zalo_nhom.py.
check("form bot hiện phần nhóm cho kênh này (từ 0.64.82 bot trả lời được trong nhóm đã cho phép)",
      next(k for k in channels.cho_giao_dien() if k["id"] == "zalo_personal")["co_nhom"])
tk = channel_accounts.get_account("zalo-1")
check("kết nối Zalo hiện thành tài khoản kênh (bản ảo, mang đúng id kết nối)",
      tk and tk["id"] == "zalo-1" and tk["channel"] == "zalo_personal" and tk["token_set"], tk)
check("có trong danh sách tài khoản để chọn ở form Bot mới",
      any(a["id"] == "zalo-1" for a in channel_accounts.tai_khoan_ao()))
check("kết nối lạ thì không có", channel_accounts.get_account("khong-co") is None)
check("token ảo là chính id kết nối (bộ giám sát coi là có thứ để chạy)",
      channel_accounts.get_token("zalo-1") == "zalo-1")

# ============================================================
# 2. Tạo bot gắn vào Zalo cá nhân
# ============================================================
bid, loi = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b",
                                     "account_ids": ["zalo-1"], "muc_quyen": "suggest"})
check("tạo được bot gắn Zalo cá nhân", bool(bid) and not loi, loi)
b = chatbot_store.get_bot(bid)
check("bot báo có token (để form không coi là thiếu) và kênh là Zalo cá nhân",
      b["token_set"] and b["channel"] == "zalo_personal", (b.get("token_set"), b.get("channel")))
bid2, loi2 = chatbot_store.create_bot({"name": "Hai", "agent_slug": "hai", "brain": "b",
                                       "account_ids": ["zalo-1"]})
check("một tài khoản chỉ một bot", not bid2 and "trực" in loi2, loi2)
check("tài khoản đã có bot thì không còn trong danh sách rảnh",
      bool(chatbot_store.bots_using_account("zalo-1")))


async def chay():
    ok, err = chatbot_runtime.start_bot(bid)
    check("bật bot chạy được và đăng ký với vòng đọc", ok and zc.co_bot("zalo-1"), err)
    st = chatbot_runtime.status(bid)
    check("thẻ bot có trạng thái sống (poller đang chạy)", st["running"], st)

    # ---- một tin khách RIÊNG mới: bot trả lời ---------------------------------------
    KHO_TIN.append({"threadId": "u1", "from": "u1", "senderName": "Khách A", "type": "text",
                    "text": "Bên em còn hàng không?", "id": "m1", "ts": _ms(5), "threadType": 0})
    await zc.doc_mot_lan(dict(CONN))
    await asyncio.sleep(0.3)
    check("khách nhắn riêng thì bot trả lời đúng một lần", len(GUI) == 1, GUI)
    check("gửi tới đúng người, là chat riêng, đúng chữ",
          GUI and GUI[0]["threadId"] == "u1" and GUI[0]["type"] == 0
          and GUI[0]["text"] == "Dạ em chào anh chị ạ", GUI)
    check("model được dạy quyền TỰ QUYẾT im lặng ở kênh này",
          LUOT_ENGINE and "[IM_LANG]" in LUOT_ENGINE[0]["prompt"], LUOT_ENGINE[:1])

    ds = conversations.tin_cua_cuoc_chat("zalo_personal", "zalo-1", "u1") \
        if hasattr(conversations, "tin_cua_cuoc_chat") else None
    if ds is None:
        with conversations._conn() as cx:
            ds = [dict(r) for r in cx.execute(
                "SELECT sender_type, text FROM messages ORDER BY id").fetchall()]
    loai = [x["sender_type"] for x in ds]
    check("Hộp thư có tin khách và câu bot, MỖI cái một lần (không nhân đôi)",
          loai.count("customer") == 1 and loai.count("ai") == 1, loai)

    # ---- tiếng vọng: chính câu bot vừa gửi quay về như tin của chủ ------------------
    KHO_TIN.append({"threadId": "u1", "from": "me", "type": "text", "isSelf": True,
                    "text": "Dạ em chào anh chị ạ", "id": "m2", "ts": _ms(1), "threadType": 0})
    await zc.doc_mot_lan(dict(CONN))
    with conversations._conn() as cx:
        loai = [r[0] for r in cx.execute("SELECT sender_type FROM messages ORDER BY id").fetchall()]
    check("CANARY: tiếng vọng của câu bot KHÔNG bị ghi lần hai thành tin 'người thật'",
          loai.count("human") == 0, loai)
    check("và không bị tính là chủ tự tay nhắn (không thì bot tự khoá miệng sau câu đầu)",
          not zc.chu_vua_nhan_tay("zalo-1", "u1"))

    # ---- rào: nhóm, ảnh, tin cũ -----------------------------------------------------
    GUI.clear()
    KHO_TIN.extend([
        {"threadId": "g1", "from": "u9", "senderName": "Ai đó", "type": "text",
         "text": "Cả nhà ơi", "id": "g-1", "ts": _ms(2), "threadType": 1},
        {"threadId": "u1", "from": "u1", "type": "image", "text": "", "id": "a-1", "ts": _ms(2),
         "threadType": 0},
        {"threadId": "u1", "from": "u1", "type": "text", "text": "Hỏi từ hôm qua", "id": "cu-1",
         "ts": _ms(zc.TUOI_TOI_DA + 600), "threadType": 0},
    ])
    n0 = len(LUOT_ENGINE)
    await zc.doc_mot_lan(dict(CONN))
    await asyncio.sleep(0.3)
    check("nhóm, ảnh và tin cũ: bot KHÔNG trả lời và không tốn một lượt model",
          not GUI and len(LUOT_ENGINE) == n0, (GUI, len(LUOT_ENGINE) - n0))

    # ---- chủ vừa tự tay nhắn cuộc chat này: bot nhường -------------------------------
    KHO_TIN.extend([
        {"threadId": "u1", "from": "me", "type": "text", "isSelf": True, "text": "Để anh trả lời nhé",
         "id": "t-1", "ts": _ms(20), "threadType": 0},
        {"threadId": "u1", "from": "u1", "type": "text", "text": "Vậy giá bao nhiêu anh?",
         "id": "k-2", "ts": _ms(3), "threadType": 0},
    ])
    await zc.doc_mot_lan(dict(CONN))
    await asyncio.sleep(0.3)
    check("chủ vừa tự nhắn thì bot im", not GUI and len(LUOT_ENGINE) == n0, GUI)
    check("nhưng tin khách vẫn vào Hộp thư",
          any(r[0] == "Vậy giá bao nhiêu anh?" for r in _tin_tho()))

    # ---- hết thời gian nhường: bot trả lời lại ---------------------------------------
    zc._TAY[("zalo-1", "u1")] = time.time() - zc.TAY_IM - 5
    KHO_TIN.append({"threadId": "u1", "from": "u1", "type": "text", "text": "Alo anh ơi",
                    "id": "k-3", "ts": _ms(2), "threadType": 0})
    await zc.doc_mot_lan(dict(CONN))
    await asyncio.sleep(0.3)
    check("hết thời gian nhường thì bot trả lời lại", len(GUI) == 1, GUI)

    # ---- bot TỰ QUYẾT im lặng --------------------------------------------------------
    GUI.clear()
    TRA_LOI["v"] = "[IM_LANG]"
    zc._TAY.clear()
    truoc = [r for r in _tin_tho() if r[1] == "ai"]
    KHO_TIN.append({"threadId": "u1", "from": "u1", "type": "text", "text": "Tối nay đi nhậu không?",
                    "id": "k-4", "ts": _ms(2), "threadType": 0})
    await zc.doc_mot_lan(dict(CONN))
    await asyncio.sleep(0.3)
    check("bot viết [IM_LANG] thì không gửi gì", not GUI, GUI)
    check("và không ghi vào Hộp thư như một câu bot nói",
          [r for r in _tin_tho() if r[1] == "ai"] == truoc)

    chatbot_runtime.stop_bot(bid)
    check("tắt bot thì gỡ đăng ký với vòng đọc", not zc.co_bot("zalo-1"))


def _tin_tho():
    with conversations._conn() as cx:
        return [(r[0], r[1]) for r in cx.execute("SELECT text, sender_type FROM messages ORDER BY id").fetchall()]


asyncio.run(chay())

# ============================================================
# 3. Prompt: đoạn "Zalo cá nhân" chỉ có ở kênh này
# ============================================================
_bot = {"name": "Lan", "agent": {"brain": "b", "slug": "lan"}}
check("prompt Telegram KHÔNG có đoạn tự quyết im lặng",
      "[IM_LANG]" not in chatbot_runtime.build_bot_prompt(dict(_bot, _kenh_luot="telegram")))
check("prompt Zalo cá nhân có",
      "[IM_LANG]" in chatbot_runtime.build_bot_prompt(dict(_bot, _kenh_luot="zalo_personal")))

# ============================================================
# 0.172.0 (#666): the owner's role file beats Javis's personal-Zalo default
# ============================================================
# The default paragraph used to sit AFTER the Agent file with a flat "private matters: do NOT answer", so it won over
# what the owner wrote (a teacher's Agent said "a student sharing something personal still gets one short reply", yet
# "Thầy ơi con buồn quá" came out silent, 15/10/2026). It now sits BEFORE the Agent file and says the Agent wins.
chatbot_runtime.wire(answer=_engine, brain_root=lambda b: tempfile.mkdtemp(prefix="brain-"),
                     read_agent=lambda br, slug: ({"name": "Trợ lý", "role": "Trợ lý lớp học"},
                                                  "Học sinh kể chuyện riêng thì vẫn đáp một câu ngắn rồi kéo về việc lớp."))
_bot_ql = {"name": "Trợ lý", "agent": {"brain": "b", "slug": "tro-ly"}, "_kenh_luot": "zalo_personal"}
p = chatbot_runtime.build_bot_prompt(_bot_ql)
check("Zalo cá nhân vẫn có đoạn mặc định (im khi không chắc)", "[IM_LANG]" in p)
check("đoạn mặc định nói thẳng hướng dẫn vai của chủ THẮNG nó", "LUÔN thắng đoạn này" in p)
check("đoạn mặc định đứng TRƯỚC file Agent (luật chủ đọc sau cùng)",
      0 <= p.index("Zalo CÁ NHÂN của chủ") < p.index("Học sinh kể chuyện riêng"), p)
check("lệnh im chuyện riêng chỉ áp cho loại tin hướng dẫn vai KHÔNG nói tới",
      p.index("hướng dẫn vai KHÔNG nói tới") < p.index("chuyện riêng tư, chuyện gia đình"))
check("Telegram không có đoạn này",
      "[IM_LANG]" not in chatbot_runtime.build_bot_prompt(dict(_bot_ql, _kenh_luot="telegram")))
chatbot_runtime.wire(answer=_engine, brain_root=lambda b: tempfile.mkdtemp(prefix="brain-"),
                     read_agent=lambda br, slug: ({}, ""))
p0 = chatbot_runtime.build_bot_prompt(_bot_ql)
check("bot không nạp được Agent vẫn giữ mặc định an toàn (im)",
      "[IM_LANG]" in p0 and "chưa nạp được hướng dẫn" in p0)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
