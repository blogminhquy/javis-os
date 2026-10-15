"""Zalo cá nhân: tin chủ nhắn tay vào Hộp thư, và câu báo hết lượt không bao giờ tới khách (0.108.0).

    python tests/run.py zalo_tin_cua_minh      (KHÔNG mạng, MCP giả)

Hai báo cáo 13/10/2026:

1. Tin chủ / nhân viên trả lời bằng điện thoại không vào Hộp thư bot. Gốc ở javis-zalo: `mcp.js` bỏ mọi tin
   `isSelf` khỏi bộ đệm sống. javis-zalo 1.3.0 giữ chúng kèm `isSelf: true`, nên phía Javis phải chịu được:
   - tin tay của chủ vào Hộp thư như "người thật" và bot nhường cuộc chat đó;
   - tiếng vọng câu bot vừa gửi KHÔNG bị ghi lần hai (đã có từ trước);
   - tiếng vọng ẢNH bot vừa gửi cũng không (không có chữ để so, trước đây sẽ bị tính là chủ nhắn tay
     và bot im 10 phút);
   - câu chủ gõ ở Hộp thư (Javis đã tự ghi) không hiện hai lần.
2. Bot đăng nguyên câu "You've hit your session limit · resets 4:40am (UTC)" vào nhóm, tag người hỏi. Câu đó về
   như một câu trả lời bình thường chứ không phải lỗi, nên lọt qua nhánh lỗi kỹ thuật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zself-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CONN = {"id": "zalo-9", "label": "Zalo shop", "connector_id": "zalo"}
GUI, KHO_TIN = [], []
TRA_LOI = {"v": "Dạ còn hàng ạ"}


def _ms(giay_truoc=0):
    return int((time.time() - giay_truoc) * 1000)


async def _goi_gia(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        return {"threads": [{"threadId": "u1", "name": "Khách A", "threadType": "dm"}]}
    if tool == "zalo_get_messages":
        tin = list(KHO_TIN)
        KHO_TIN.clear()
        return {"messages": tin, "cursor": 1, "hasMore": False}
    return {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _goi_gia
zc.CHO_KHACH_IM = 0          # giao từng tin ngay: file này canh các rào khác; cửa sổ chờ ở test_zalo_cho_khach_nhan_xong.py


async def _engine(text, meta, progress, *, channel="", bot=None):
    return {"text": TRA_LOI["v"], "files": []}


chatbot_runtime.wire(answer=_engine, brain_root=lambda b: tempfile.mkdtemp(prefix="brain-"),
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Bán hàng"}, "Ngắn gọn."))


# A counter, not time.time_ns(): on Windows the clock is coarse enough for two messages built in a row
# to share an id, and the store then drops the second one as a duplicate (flaky run seen 14/10/2026).
_SO_TIN = __import__("itertools").count(1)


def _tin(**kw):
    """One message in javis-zalo 1.3.0's live-feed shape (normalizeMessage)."""
    base = {"threadId": "u1", "threadType": "dm", "senderId": "u1", "senderName": "Khách A",
            "isSelf": False, "type": "text", "text": "", "id": f"m{next(_SO_TIN)}", "timestamp": _ms(1)}
    base.update(kw)
    return base


def _hop_thu():
    with conversations._conn() as cx:
        return [(r[0], r[1]) for r in cx.execute("SELECT sender_type, text FROM messages ORDER BY id").fetchall()]


# ============================================================
# 1. engine_notice: chỉ bắt câu báo CHIẾM cả câu trả lời
# ============================================================
en = chatbot_runtime.engine_notice
check("bắt câu hết lượt Claude đúng như ảnh chụp",
      bool(en("You've hit your session limit · resets 4:40am (UTC)")))
check("bắt lỗi engine kiểu API Error / Credit balance",
      bool(en("API Error: 529 overloaded")) and bool(en("Credit balance is too low")))
check("không đụng câu trả lời thật", not en("Dạ bên em còn hàng, anh chị cần mấy cái ạ?"))
check("không đụng câu trả lời dài có TRÍCH câu báo",
      not en("Dạ khi app báo \"You've hit your session limit\" thì anh chờ tới giờ mở lại rồi thử lại ạ. "
             + "Ngoài ra " * 60))
check("rỗng thì thôi", en("") == "" and en(None) == "")

bid, loi = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b",
                                     "account_ids": ["zalo-9"], "muc_quyen": "suggest"})
check("tạo được bot gắn Zalo cá nhân", bool(bid) and not loi, loi)


async def chay():
    ok, err = chatbot_runtime.start_bot(bid)
    check("bật bot", ok, err)

    # ---- 2. câu hết lượt về như câu trả lời: KHÔNG gửi cho khách ---------------------
    TRA_LOI["v"] = "You've hit your session limit · resets 4:40am (UTC)"
    KHO_TIN.append(_tin(text="Shop còn hàng không ạ?"))
    await zc.doc_mot_lan(dict(CONN))
    await asyncio.sleep(0.3)
    gui_chu = [g.get("text") for g in GUI]
    check("CANARY: câu 'session limit' KHÔNG tới khách", not any("session limit" in (t or "") for t in gui_chu),
          gui_chu)
    # Chủ repo 15/10/2026: hết lượt là trục trặc kỹ thuật, khách không nhận gì (trước đây nhận "đợi em chút xíu").
    check("hết lượt: khách KHÔNG nhận câu nào, kể cả câu xin lỗi", not any(gui_chu), gui_chu)
    check("Hộp thư không ghi câu hết lượt như lời bot",
          not any("session limit" in t and s == "ai" for s, t in _hop_thu()), _hop_thu())
    GUI.clear()
    TRA_LOI["v"] = "Dạ còn hàng ạ"
    await asyncio.sleep(0.05)

    # ---- 3. chủ nhắn tay từ điện thoại (isSelf) vào Hộp thư, bot nhường --------------
    zc._TAY.clear()
    KHO_TIN.append(_tin(isSelf=True, senderId="me-uid", senderName="Chủ shop",
                        text="Anh ơi em gửi báo giá qua mail rồi nhé"))
    await zc.doc_mot_lan(dict(CONN))
    ht = _hop_thu()
    check("tin chủ nhắn tay vào Hộp thư như người thật",
          ("human", "Anh ơi em gửi báo giá qua mail rồi nhé") in ht, ht)
    check("bot nhường cuộc chat chủ vừa nhắn tay", zc.chu_vua_nhan_tay("zalo-9", "u1"))
    check("không gửi gì cho tin của chính mình", not GUI, GUI)

    # ---- 4. tiếng vọng ẢNH bot vừa gửi: không ghi, không tính là chủ nhắn tay ---------
    zc._TAY.clear()
    n0 = len(_hop_thu())
    zc.ghi_da_gui_anh("zalo-9", "u1", 2)
    KHO_TIN.extend([_tin(isSelf=True, senderId="me-uid", type="chat.photo", text="",
                         attachment={"type": "chat.photo", "url": "https://x/a.jpg"}),
                    _tin(isSelf=True, senderId="me-uid", type="chat.photo", text="",
                         attachment={"type": "chat.photo", "url": "https://x/b.jpg"})])
    await zc.doc_mot_lan(dict(CONN))
    check("CANARY: hai ảnh bot gửi quay về không ghi thêm dòng nào", len(_hop_thu()) == n0, _hop_thu()[n0:])
    check("và bot không tự khoá miệng vì tưởng chủ vừa nhắn", not zc.chu_vua_nhan_tay("zalo-9", "u1"))
    KHO_TIN.append(_tin(isSelf=True, senderId="me-uid", type="chat.photo", text="",
                        attachment={"type": "chat.photo", "url": "https://x/c.jpg"}))
    await zc.doc_mot_lan(dict(CONN))
    ht = _hop_thu()
    check("ảnh THỨ BA (chủ tự gửi) vẫn vào Hộp thư và không ghi 'khách gửi'",
          len(ht) == n0 + 1 and ht[-1][0] == "human" and "khách" not in ht[-1][1], ht[n0:])

    chatbot_runtime.stop_bot(bid)


asyncio.run(chay())

# ============================================================
# 5. Câu chủ gõ ở Hộp thư được nhớ là tiếng vọng (Javis đã tự ghi nó)
# ============================================================
src = (SERVER / "routes" / "conversations.py").read_text(encoding="utf-8")
check("trả lời tay ở Hộp thư nhớ tiếng vọng trước khi gửi", "await _gui_tin(c, txt, tieng_vong=True)" in src)
src_ch = (SERVER / "channels" / "zalo_personal.py").read_text(encoding="utf-8")
check("bot gửi ảnh thì nhớ số ảnh trước khi gửi", "zc.ghi_da_gui_anh(self.conn_id, thread, len(anh))" in src_ch)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
