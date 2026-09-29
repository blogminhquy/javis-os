"""Bot chuyên trách: "bot trả lời ai" (`audience` + `people`), 0.64.85.

    python tests/run.py bot_doi_tuong      (KHÔNG mạng, MCP giả)

Chủ dự án muốn chọn được bot trả lời ai: mọi cuộc chat trên kênh, hay ai nhắn riêng cũng được còn
nhóm thì chọn, hay chỉ những người và nhóm đã chọn. Trước đó chat riêng luôn trả lời tất cả mọi
người và nhóm chỉ có một ô dán id. Xem docs/superpowers/specs/2026-09-30-form-bot-va-doi-tuong-tra-loi-design.md.

Bốn thứ file này canh:

  1. MÔ HÌNH. `nhom` (mặc định) là hành vi từ trước tới nay nên bản ghi cũ không đổi. Sai thì sai về
     phía IM LẶNG: giá trị hỏng đọc là `chon` (hẹp nhất), đặt giá trị lạ thì giữ giá trị cũ.
  2. CỔNG. Bảng 3 audience x (chat riêng, nhóm) khớp đúng thiết kế, và `reply_when` vẫn quyết
     "khi nào lên tiếng" trong nhóm.
  3. IM MÀ KHÔNG BIẾN MẤT. Người/nhóm chưa được chọn thì bot im tuyệt đối nhưng hiện lên danh sách
     chờ duyệt kèm loại (người hay nhóm) để chủ bấm Cho phép.
  4. CHỌN TỪ HỘP THƯ. Danh sách cuộc chat đã biết cho ô chọn, không bắt dán id.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-doituong-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_cuoc_chat  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


G, G2 = "5550001", "5550009"       # nhóm đã chọn / nhóm lạ
P, Q = "5550002", "5550003"        # người đã chọn / người lạ
CONN = {"id": "dt-1", "label": "Javis Vũ", "connector_id": "zalo"}
CONN2 = {"id": "dt-2", "label": "Nick hai", "connector_id": "zalo"}   # mỗi tài khoản chỉ một bot
zc._ket_noi = lambda: [dict(CONN), dict(CONN2)]

# ============================================================
# 1. Mô hình dữ liệu
# ============================================================
check("AUDIENCE có đúng ba giá trị", chatbot_store.AUDIENCE == ("all", "nhom", "chon"))
bid, loi = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b",
                                     "account_ids": ["dt-1"], "groups": G})
check("tạo bot không nói gì về audience thì là `nhom` (đúng hành vi từ trước tới nay)",
      not loi and chatbot_store.get_bot(bid)["audience"] == "nhom", loi)
check("`people` mặc định là danh sách rỗng", chatbot_store.get_bot(bid)["people"] == [])
check("CANARY: bản ghi CŨ không có khoá `audience` được đọc là `nhom`, không đổi hành vi",
      chatbot_store._public({"id": "x", "groups": []}).get("audience") == "nhom")
check("CANARY fail-closed: bản ghi có `audience` nhưng giá trị hỏng thì đọc là `chon` (hẹp nhất)",
      chatbot_store._public({"id": "x", "audience": "tuy-y"}).get("audience") == "chon")

b2, loi2 = chatbot_store.create_bot({"name": "Hai", "agent_slug": "hai", "brain": "b",
                                     "audience": "chon", "people": f"{P}\n{Q}\nlinh tinh {P}"})
check("tạo với audience=chon và people (chuỗi nhiều dòng)", not loi2, loi2)
bb = chatbot_store.get_bot(b2)
check("people lưu đúng, bỏ chữ lạc và trùng", bb["audience"] == "chon" and bb["people"] == [P, Q], bb["people"])

ok, err = chatbot_store.update_bot(b2, {"audience": "khong-ro"})
check("đặt audience lạ thì GIỮ giá trị cũ (không rơi về mặc định)",
      chatbot_store.get_bot(b2)["audience"] == "chon")
ok, err = chatbot_store.update_bot(b2, {"audience": "all"})
check("nâng lên `all` mà chưa xác nhận thì bị từ chối", not ok and err == chatbot_store.LOI_CHUA_XAC_NHAN_DOI_TUONG, (ok, err))
check("và bot vẫn ở `chon`", chatbot_store.get_bot(b2)["audience"] == "chon")
ok, err = chatbot_store.update_bot(b2, {"audience": "all", "xac_nhan_rui_ro": True})
check("có xác nhận thì nâng lên `all` được", ok and chatbot_store.get_bot(b2)["audience"] == "all", err)
ok, err = chatbot_store.update_bot(b2, {"audience": "chon"})
check("HẠ xuống `chon` KHÔNG đòi xác nhận (đừng dựng rào đúng lúc chủ đang dập sự cố)", ok, err)
ok, err = chatbot_store.update_bot(b2, {"people": f"{Q}"})
check("sửa danh sách người", ok and chatbot_store.get_bot(b2)["people"] == [Q])
b3, loi3 = chatbot_store.create_bot({"name": "Ba", "agent_slug": "ba", "brain": "b", "audience": "all"})
check("tạo thẳng `all` mà chưa xác nhận cũng bị từ chối (rào ở KHO, không chỉ ở route)",
      b3 is None and loi3 == chatbot_store.LOI_CHUA_XAC_NHAN_DOI_TUONG, (b3, loi3))
b4, loi4 = chatbot_store.create_bot({"name": "Bốn", "agent_slug": "bon", "brain": "b", "audience": "all",
                                     "xac_nhan_rui_ro": True})
check("tạo `all` có xác nhận thì được", bool(b4) and not loi4, loi4)
check("`can_xac_nhan` vẫn đúng cho mức quyền như cũ",
      chatbot_store.can_xac_nhan("full", False) and not chatbot_store.can_xac_nhan("suggest", False)
      and not chatbot_store.can_xac_nhan("full", True))

# ============================================================
# 2. Cổng: 3 audience x (chat riêng, nhóm), reply_when giữ nguyên nghĩa
# ============================================================
base = {"groups": [G], "people": [P], "reply_when": "mention"}
rieng = lambda cid: {"chat_type": "private", "chat_id": cid}          # noqa: E731
nhom = lambda cid, tag=False: {"chat_type": "group", "chat_id": cid, "mentioned": tag}   # noqa: E731
im = chatbot_runtime._ly_do_im

nh = dict(base, audience="nhom")
check("nhom: chat riêng ai cũng được", im(nh, rieng(Q)) == "" and im(nh, rieng(P)) == "")
check("nhom: nhóm đã chọn + gọi tên -> được", im(nh, nhom(G, True)) == "")
check("nhom: nhóm lạ -> im (chưa bật)", im(nh, nhom(G2, True)) == "nhom_chua_bat")

ch = dict(base, audience="chon")
check("chon: người đã chọn -> được", im(ch, rieng(P)) == "")
check("chon: người lạ -> im, mã riêng để hiện lên danh sách chờ", im(ch, rieng(Q)) == "nguoi_chua_chon")
check("chon: nhóm đã chọn + gọi tên -> được", im(ch, nhom(G, True)) == "")
check("chon: nhóm lạ -> im (chưa bật)", im(ch, nhom(G2, True)) == "nhom_chua_bat")

al = dict(base, audience="all")
check("all: chat riêng ai cũng được", im(al, rieng(Q)) == "")
check("all: nhóm lạ + gọi tên -> được (không cần khai nhóm)", im(al, nhom(G2, True)) == "")
check("all: nhóm lạ nhưng không ai gọi tên -> vẫn theo reply_when=mention (im)",
      im(al, nhom(G2, False)) == "khong_goi_ten")
check("all + reply_when=auto: cho đi tiếp để bộ đánh giá quyết",
      im(dict(al, reply_when="auto"), nhom(G2, False)) == "")
check("all + reply_when=always: trả lời mọi tin", im(dict(al, reply_when="always"), nhom(G2, False)) == "")
check("CANARY: bản ghi cũ (không audience) cư xử như `nhom`",
      im(base, rieng(Q)) == "" and im(base, nhom(G2, True)) == "nhom_chua_bat")
check("CANARY fail-closed: audience hỏng cư xử như `chon`",
      im(dict(base, audience="tuy-y"), rieng(Q)) == "nguoi_chua_chon")

# ============================================================
# 3. Im mà không biến mất: danh sách chờ có cả người, kèm loại
# ============================================================
b5, _ = chatbot_store.create_bot({"name": "Chon", "agent_slug": "chon", "brain": "b", "account_ids": ["dt-2"],
                                  "audience": "chon", "people": P, "groups": G})
_chan = chatbot_runtime._make_precheck_fn(b5)
r = _chan("Xin chào", dict(chat_type="private", chat_id=Q, user_name="Người Lạ", user_id=Q))
check("người chưa chọn: precheck im lặng (không nói câu cố định nào)", r == {}, r)
cho = chatbot_runtime.nhom_cho(b5)
check("nhưng hiện lên danh sách chờ, kèm loại `private` và tên người",
      any(x["chat_id"] == Q and x.get("loai") == "private" and x.get("ten") == "Người Lạ" for x in cho), cho)
check("người đã chọn thì không bị chặn", _chan("Chào", dict(chat_type="private", chat_id=P)) is None)
chatbot_runtime.bo_nhom_cho(b5, Q)
check("cho phép/bỏ qua thì ra khỏi danh sách chờ", not any(x["chat_id"] == Q for x in chatbot_runtime.nhom_cho(b5)))

sk = chatbot_runtime._make_event_fn(b5)
asyncio.run(sk("thay_nhom", {"chat_id": G2, "chat_title": "Nhóm lạ"}))
check("nhóm mới thấy trong `chon` hiện lên danh sách chờ với loại `group`",
      any(x["chat_id"] == G2 and x.get("loai") == "group" for x in chatbot_runtime.nhom_cho(b5)))
chatbot_store.update_bot(b5, {"audience": "all", "xac_nhan_rui_ro": True})
chatbot_runtime.bo_nhom_cho(b5)
asyncio.run(sk("thay_nhom", {"chat_id": G2, "chat_title": "Nhóm lạ"}))
check("với `all` mọi nhóm đã được phép nên KHÔNG có gì để chờ duyệt",
      not any(x["chat_id"] == G2 for x in chatbot_runtime.nhom_cho(b5)))

# ============================================================
# 4. Chọn từ Hộp thư
# ============================================================
now = time.time()
for i, (chat, loai, ten, ai) in enumerate([
        (P, "private", "", "Học viên A"), (Q, "private", "", "Học viên B"),
        (G, "group", "Lớp Javis OS", "Học viên A"), (G2, "group", "", "Học viên C")]):
    conversations.ghi_su_kien({
        "channel": "zalo_personal", "account_id": "dt-2", "account_name": "Nick hai",
        "external_chat_id": chat, "chat_type": loai, "chat_title": ten, "sender_type": "customer",
        "sender_id": ai + chat, "sender_name": ai, "message_type": "text", "text": f"tin {i}",
        "external_message_id": f"m{i}", "created_at": now - 100 + i})
chatbot_store.update_bot(b5, {"audience": "chon", "people": P, "groups": G})
bot5 = chatbot_store.get_bot(b5)
ds = chatbot_cuoc_chat.danh_sach(bot5.get("accounts") or [], "", 50, chatbot_runtime.nhom_cho(b5), bot5)
by = {d["id"]: d for d in ds}
check("liệt kê đủ cuộc chat đã biết của tài khoản, cả nhóm lẫn người", set(by) >= {P, Q, G, G2}, list(by))
check("có loại và tên hiển thị (người: tên khách; nhóm: tên nhóm)",
      by[G]["loai"] == "group" and by[G]["ten"] == "Lớp Javis OS" and by[P]["loai"] == "private"
      and by[P]["ten"] == "Học viên A", (by[G], by[P]))
check("nhóm chưa rõ tên hiện tên dự phòng, KHÔNG mượn tên người nhắn",
      by[G2]["ten"].startswith("Nhóm") and "Học viên C" not in by[G2]["ten"], by[G2])
check("cờ `da_chon` khớp danh sách của bot (people và groups)",
      by[P]["da_chon"] and by[G]["da_chon"] and not by[Q]["da_chon"] and not by[G2]["da_chon"])
tim = chatbot_cuoc_chat.danh_sach(bot5.get("accounts") or [], "Lớp", 50, [], bot5)
check("ô tìm lọc theo tên", [d["id"] for d in tim] == [G], [d["id"] for d in tim])
chatbot_runtime._ghi_nhom_cho(b5, {"chat_id": G2, "chat_type": "group", "chat_title": "Nhóm lạ"}, "hi")
ds2 = chatbot_cuoc_chat.danh_sach(bot5.get("accounts") or [], "", 50, chatbot_runtime.nhom_cho(b5), bot5)
check("cuộc chat đang chờ duyệt được đánh dấu `cho`", {d["id"]: d for d in ds2}[G2]["cho"])
check("và xếp lên đầu (chủ cần thấy chúng trước)", ds2[0]["id"] == G2, [d["id"] for d in ds2])

# ============================================================
# 5. Đầu nối route
# ============================================================
_SRC = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("route tạo và sửa bot nhận audience và people",
      "audience: str = Form(" in _SRC and "people: str = Form(" in _SRC)
check("có route cho phép/gỡ MỘT người và route liệt kê cuộc chat",
      '"/chatbots/{bot_id}/people"' in _SRC and '"/chatbots/chats"' in _SRC)
check("route liệt kê cuộc chat đăng ký TRƯỚC route có {bot_id} (không thì 'chats' bị coi là id bot)",
      _SRC.index('"/chatbots/chats"') < _SRC.index('"/chatbots/{bot_id}/log"'))

# ============================================================
# 6. Đầu-cuối trên Zalo cá nhân (MCP giả): người ngoài danh sách im, người trong danh sách được trả lời
# ============================================================
GUI, KHO, LUOT = [], [], []


async def _goi_gia(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        return {"threads": [{"threadId": G, "name": "Lớp Javis OS", "threadType": "group"},
                            {"threadId": G2, "name": "Nhóm lạ", "threadType": "group"},
                            {"threadId": P, "name": "Học viên A", "threadType": "dm"},
                            {"threadId": Q, "name": "Học viên B", "threadType": "dm"}]}
    if tool == "zalo_get_messages":
        tin = list(KHO)
        KHO.clear()
        return {"messages": tin, "cursor": 0, "hasMore": False}
    return {}


async def _engine(text, meta, progress, *, channel="", bot=None):
    LUOT.append(text)
    return {"text": "Dạ em đây ạ", "files": []}


zc._goi = _goi_gia
zc.THU_LAI_TEN_GIAY = 0
chatbot_runtime.wire(answer=_engine, brain_root=lambda b: tempfile.mkdtemp(prefix="brain-dt-"),
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Trợ lý"}, "Trả lời ngắn."))
chatbot_store.delete_bot(bid)          # nhả tài khoản dt-1 cho bot thử đầu-cuối


def _tin(chat, ai, text, mid, loai, **them):
    m = {"threadId": chat, "from": ai, "senderName": "Ai đó", "type": "text", "text": text,
         "id": mid, "ts": int(time.time()), "threadType": loai}
    m.update(them)
    return m


async def dau_cuoi():
    e2e, loi = chatbot_store.create_bot({"name": "E2E", "agent_slug": "e2e", "brain": "b",
                                         "account_ids": ["dt-1"], "audience": "chon",
                                         "people": P, "groups": G, "reply_when": "mention"})
    assert e2e, loi
    ok, err = chatbot_runtime.start_bot(e2e)
    assert ok, err

    async def doc(cho=0.3):
        await zc.doc_mot_lan(dict(CONN))
        await asyncio.sleep(cho)

    KHO.append(_tin(Q, Q, "Xin chào, cho hỏi chút", "e1", 0))
    await doc()
    check("audience=chon: người NGOÀI danh sách nhắn riêng thì bot im, không tốn lượt model",
          not GUI and not LUOT, (GUI, LUOT))
    check("nhưng người đó hiện lên danh sách chờ duyệt (loại private, có tên)",
          any(x["chat_id"] == Q and x["loai"] == "private" for x in chatbot_runtime.nhom_cho(e2e)),
          chatbot_runtime.nhom_cho(e2e))

    KHO.append(_tin(P, P, "Em chào anh", "e2", 0))
    await doc()
    check("người TRONG danh sách nhắn riêng thì được trả lời, đúng chat riêng",
          len(GUI) == 1 and GUI[0]["threadId"] == P and GUI[0]["threadType"] == 0, GUI)

    GUI.clear()
    chatbot_store.update_bot(e2e, {"people": [P, Q]})
    chatbot_runtime.bo_nhom_cho(e2e, Q)
    KHO.append(_tin(Q, Q, "Anh ơi cho em hỏi", "e3", 0))
    await doc()
    check("cho phép người đó (sửa danh sách) thì tin kế tiếp được trả lời NGAY, không cần khởi động lại",
          len(GUI) == 1 and GUI[0]["threadId"] == Q, GUI)

    GUI.clear()
    del LUOT[:]
    KHO.append(_tin(G2, "7770001", "@Javis Vũ cho hỏi", "e4", 1))
    await doc()
    check("audience=chon: nhóm lạ có tag vẫn im (chưa cho phép)", not GUI and not LUOT, (GUI, LUOT))

    ok, err = chatbot_store.update_bot(e2e, {"audience": "all", "xac_nhan_rui_ro": True})
    assert ok, err
    chatbot_runtime.bo_nhom_cho(e2e)
    KHO.append(_tin(G2, "7770001", "@Javis Vũ hỏi cái này", "e5", 1))
    await doc()
    check("audience=all: nhóm CHƯA khai mà có tag thì được trả lời (type=1 vào đúng nhóm)",
          len(GUI) == 1 and GUI[0]["threadId"] == G2 and GUI[0]["threadType"] == 1, GUI)

    GUI.clear()
    KHO.append(_tin(G2, "7770001", "cả nhà ăn cơm chưa", "e6", 1))
    await doc()
    check("audience=all vẫn theo reply_when: nhóm không ai gọi tên thì im", not GUI, GUI)
    chatbot_runtime.stop_bot(e2e)


asyncio.run(dau_cuoi())

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
