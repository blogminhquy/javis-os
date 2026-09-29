"""Khuôn THAM SỐ THẬT của MCP zalo-agent-cli 1.6.2 mà Javis gọi (0.64.84).

    python tests/run.py zalo_mcp_khuon      (KHÔNG mạng, MCP giả)

Chủ thử ngày 29/09/2026: bot trả lời trong nhóm Zalo, câu trả lời hiện trong Hộp thư nhưng KHÔNG
tới nhóm; chat riêng thì vẫn tới. Đọc mã nguồn MCP ở tag v1.6.2 (src/mcp/mcp-tools.js,
message-buffer.js) mới thấy tài liệu mcp-guide.md và mã Javis lệch với thứ MCP thật sự đọc:

  - `zalo_send_message` đọc `threadType` (0 = chat riêng, mặc định; 1 = nhóm), KHÔNG phải `type`.
    MCP bỏ qua khoá lạ, nên mọi tin gửi vào nhóm đi như chat riêng và Zalo không giao được.
  - `zalo_get_messages` đọc `since` (SỐ NGUYÊN, số thứ tự toàn cục của bộ đệm) và `limit` (1..100),
    KHÔNG có `cursor`. Trả về tin CŨ NHẤT TRƯỚC, tối đa `limit` tin, kèm `cursor` (số, của tin cuối
    lô) và `hasMore`. Javis truyền `cursor` nên mỗi lần đọc lại 100 tin cũ nhất; bộ đệm giữ tới 500
    tin mỗi cuộc chat trong 2 giờ nên nick ở nhiều nhóm sôi nổi sẽ không bao giờ đọc tới tin mới.
  - Số thứ tự đó đếm lại từ đầu mỗi lần tiến trình MCP khởi động, nên `since` cũ giữ qua một lần
    khởi động lại là bỏ qua tin mới. Vì vậy `since` chỉ được giữ trong RAM và gắn với số hiệu
    PHIÊN MCP (`mcp_client.pool.epoch`).
  - `zalo_list_threads` trả `threadType` ("group" | "dm" | "unknown") và `name` (có thể null).

Bài học chung: một tham số MCP viết sai tên KHÔNG báo lỗi (bị lặng lẽ bỏ qua), nên đúng loại lỗi
này chỉ bắt được bằng một test khẳng định TÊN khoá thật, không phải bằng việc "gọi mà không lỗi".
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpkhuon-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_log  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402
import mcp_client  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as kenh  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CONN = {"id": "zk-1", "label": "Javis Vũ", "connector_id": "zalo"}
CALLS = []              # (tool, args)
DAP = {}                # tool -> hàm trả kết quả giả


async def _goi_gia(conn, tool, args):
    CALLS.append((tool, dict(args or {})))
    fn = DAP.get(tool)
    return fn(args or {}) if fn else {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _goi_gia
zc.THU_LAI_TEN_GIAY = 0

# ============================================================
# 1. Gửi: khoá kiểu cuộc chat là `threadType`
# ============================================================
DAP["zalo_send_message"] = lambda a: {"success": True, "messageId": "m1"}


async def gui_thu():
    ok1, e1 = await kenh.gui({"id": "zk-1"}, "5550001", "Chào cả nhóm", "group")
    ok2, e2 = await kenh.gui({"id": "zk-1"}, "5550002", "Chào bạn", "private")
    return ok1, ok2


ok_n, ok_r = asyncio.run(gui_thu())
gui_nhom = [a for t, a in CALLS if t == "zalo_send_message"][0]
gui_rieng = [a for t, a in CALLS if t == "zalo_send_message"][1]
check("gửi vào nhóm và chat riêng đều báo thành công", ok_n and ok_r)
check("CANARY: gửi nhóm mang `threadType`=1 (khoá MCP thật đọc, không phải `type`)",
      gui_nhom.get("threadType") == 1, gui_nhom)
check("gửi chat riêng mang `threadType`=0", gui_rieng.get("threadType") == 0, gui_rieng)
check("vẫn kèm `type` như tài liệu mcp-guide, cho bản MCP đọc khoá đó (MCP bỏ qua khoá lạ)",
      gui_nhom.get("type") == 1 and gui_rieng.get("type") == 0)
check("id cuộc chat và nội dung đi nguyên vẹn",
      gui_nhom["threadId"] == "5550001" and gui_nhom["text"] == "Chào cả nhóm")

# ============================================================
# 2. Đọc: `since` là số nguyên gắn với phiên MCP, không phải `cursor`
# ============================================================
EP = {"v": 1}
zc._epoch = lambda conn: EP["v"]
BUFFER = {"trang": [], "da_tra": []}


def _msg(i, thread="5550001"):
    return {"id": f"k{i}", "threadId": thread, "text": f"tin {i}", "from": "7770001",
            "ts": int(time.time()), "threadType": "group"}


def _get_messages(a):
    # Giả đúng hành vi MCP: chỉ trả tin có số thứ tự > since, cũ nhất trước, tối đa limit.
    since = int(a.get("since") or 0)
    tat_ca = [(i, m) for i, m in BUFFER["tin"] if i > since]
    lo = tat_ca[:int(a.get("limit") or 100)]
    return {"messages": [m for _, m in lo],
            "cursor": (lo[-1][0] if lo else since),
            "hasMore": len(tat_ca) > len(lo)}


DAP["zalo_get_messages"] = _get_messages
DAP["zalo_list_threads"] = lambda a: {"threads": [
    {"threadId": "5550001", "name": "Lớp Javis OS", "threadType": "group"}]}

BUFFER["tin"] = [(1, _msg(1)), (2, _msg(2)), (3, _msg(3))]


def lay(tool):
    return [a for t, a in CALLS if t == tool]


CALLS.clear()
asyncio.run(zc.doc_mot_lan(dict(CONN)))
a0 = lay("zalo_get_messages")[0]
check("lần đọc đầu KHÔNG gửi since (chưa biết mình đang ở đâu trong bộ đệm)", "since" not in a0, a0)
check("KHÔNG BAO GIỜ gửi khoá `cursor` (MCP không có khoá đó)",
      all("cursor" not in a for a in lay("zalo_get_messages")))
check("giới hạn lô nằm trong khoảng MCP cho phép (1..100)",
      all(1 <= a.get("limit", 100) <= 100 for a in lay("zalo_get_messages")))

BUFFER["tin"].append((4, _msg(4)))
CALLS.clear()
kq = asyncio.run(zc.doc_mot_lan(dict(CONN)))
a1 = lay("zalo_get_messages")[0]
check("lần hai gửi `since` = số thứ tự tin cuối lần trước, là SỐ NGUYÊN", a1.get("since") == 3
      and isinstance(a1["since"], int), a1)
check("chỉ nhận đúng tin mới (không đọc lại 3 tin cũ)", kq["moi"] == 1 and kq["trung"] == 0, kq)

# Phiên MCP khởi động lại: số thứ tự đếm lại từ 1, since cũ sẽ bỏ qua tin mới -> phải đọc từ đầu
EP["v"] = 2
BUFFER["tin"] = [(1, _msg(11)), (2, _msg(12))]     # tiến trình mới, bộ đệm mới
CALLS.clear()
kq = asyncio.run(zc.doc_mot_lan(dict(CONN)))
a2 = lay("zalo_get_messages")[0]
check("CANARY: phiên MCP đổi thì KHÔNG dùng since cũ (không thì bỏ qua tin mới)",
      "since" not in a2 and kq["moi"] == 2, (a2, kq))

# Phiên đổi NGAY TRONG lúc gọi (tiến trình chết và dựng lại giữa chừng): đọc lại từ đầu
lan_goi = {"n": 0}
goc = DAP["zalo_get_messages"]


def _doi_phien_giua_chung(a):
    lan_goi["n"] += 1
    if lan_goi["n"] == 1:
        EP["v"] = 3          # phiên bị dựng lại trong lúc lượt này chạy
        return {"messages": [], "cursor": int(a.get("since") or 0), "hasMore": False}
    return goc(a)


DAP["zalo_get_messages"] = _doi_phien_giua_chung
BUFFER["tin"] = [(1, _msg(21)), (2, _msg(22))]
CALLS.clear()
kq = asyncio.run(zc.doc_mot_lan(dict(CONN)))
check("phiên đổi giữa lúc gọi thì đọc lại từ đầu ngay trong lượt đó, không mất tin",
      len(lay("zalo_get_messages")) == 2 and "since" not in lay("zalo_get_messages")[1]
      and kq["moi"] == 2, (lay("zalo_get_messages"), kq))
DAP["zalo_get_messages"] = goc

# hasMore: lô đầy thì đọc tiếp NGAY trong cùng lượt, không chờ nhịp 20 giây
EP["v"] = 4
BUFFER["tin"] = [(i, _msg(100 + i)) for i in range(1, 251)]
zc.LIMIT = 100
CALLS.clear()
kq = asyncio.run(zc.doc_mot_lan(dict(CONN)))
gm = lay("zalo_get_messages")
check("bộ đệm 250 tin: đọc liên tiếp 3 lô trong một lượt", len(gm) == 3 and kq["moi"] == 250,
      (len(gm), kq))
check("mỗi lô sau dùng since = cursor của lô trước", gm[1].get("since") == 100 and gm[2].get("since") == 200,
      gm)

# cursor không phải số (khuôn trong tài liệu ghi chuỗi) thì KHÔNG dùng: an toàn hơn là đoán
EP["v"] = 5
DAP["zalo_get_messages"] = lambda a: {"messages": [_msg(900)], "nextCursor": "cursor_abc", "hasMore": False}
asyncio.run(zc.doc_mot_lan(dict(CONN)))
CALLS.clear()
asyncio.run(zc.doc_mot_lan(dict(CONN)))
check("cursor dạng chữ thì lần sau vẫn không gửi since", "since" not in lay("zalo_get_messages")[0])
DAP["zalo_get_messages"] = _get_messages

# ============================================================
# 3. `SessionPool.epoch`: số hiệu phiên đổi khi phiên bị dựng lại
# ============================================================
pool = mcp_client.SessionPool()
spec = {"key": "epoch-test", "transport": "http", "url": "http://127.0.0.1:9/mcp"}   # dựng phiên không gọi mạng
check("chưa có phiên thì epoch = 0", pool.epoch(spec) == 0)
pool._get(spec)
e1 = pool.epoch(spec)
check("có phiên thì epoch > 0", e1 > 0)
check("cùng phiên thì epoch giữ nguyên", pool.epoch(spec) == e1)
pool.invalidate("epoch-test")
pool._get(spec)
check("phiên dựng lại thì epoch KHÁC (số không bao giờ tái dùng)", pool.epoch(spec) not in (0, e1))

# ============================================================
# 4. Tên nhóm: cuộc chat lạ (kể cả tin đã có threadType) làm mới bảng tên
# ============================================================
# Nhóm mới vào chưa có trong bảng tên (làm mới 5 phút một lần) thì cuộc chat không có tiêu đề, và
# Hộp thư lấy tên NGƯỜI NHẮN ĐẦU TIÊN làm tên nhóm (chủ thấy nhóm "Test Bot Zalo" hiện là "Minh Quý").
EP["v"] = 6
zc._TT.clear()
DAP["zalo_list_threads"] = lambda a: {"threads": [
    {"threadId": "5550001", "name": "Lớp Javis OS", "threadType": "group"}]}
BUFFER["tin"] = [(1, _msg(31))]
asyncio.run(zc.doc_mot_lan(dict(CONN)))       # nạp bảng lần đầu
DAP["zalo_list_threads"] = lambda a: {"threads": [
    {"threadId": "5550001", "name": "Lớp Javis OS", "threadType": "group"},
    {"threadId": "5559000", "name": "Test Bot Zalo", "threadType": "group"}]}
BUFFER["tin"] = [(1, _msg(32, "5559000"))]   # tin có threadType, thread chưa có trong bảng
EP["v"] = 7
CALLS.clear()
asyncio.run(zc.doc_mot_lan(dict(CONN)))
check("tin từ cuộc chat lạ: hỏi lại bảng tên NGAY dù tin đã có threadType", len(lay("zalo_list_threads")) >= 1)
with conversations._conn() as cx:
    tieu_de = [r[0] for r in cx.execute(
        "SELECT title FROM conversations WHERE external_chat_id='5559000'").fetchall()]
check("cuộc chat nhóm mới mang đúng TÊN NHÓM, không phải tên người nhắn", tieu_de == ["Test Bot Zalo"], tieu_de)

# Thread không bao giờ có trong bảng: không hỏi lại mỗi nhịp 20 giây
BUFFER["tin"] = [(1, _msg(33, "5559111"))]
EP["v"] = 8
CALLS.clear()
asyncio.run(zc.doc_mot_lan(dict(CONN)))
n1 = len(lay("zalo_list_threads"))
BUFFER["tin"] = [(1, _msg(34, "5559111"))]
EP["v"] = 9
asyncio.run(zc.doc_mot_lan(dict(CONN)))
check("cuộc chat vẫn không có trong bảng thì KHÔNG hỏi lại dồn dập (nhớ lần thử gần nhất)",
      len(lay("zalo_list_threads")) == n1, (n1, len(lay("zalo_list_threads"))))

# Bảng tên đọc `threadType` (khoá thật) chứ không chỉ `type` (khuôn trong tài liệu)
ten = asyncio.run(zc._nap_ten(dict(CONN), {}, cuong_buc=True))
check("bảng tên nhận ra nhóm qua `threadType` của list_threads",
      (ten.get("5559000") or {}).get("type") == "group", ten)

# Hộp thư: nhóm chưa biết tên không được lấy tên người nhắn làm tên nhóm
ds = conversations.danh_sach(channel="zalo_personal")
nhom_la = [d for d in ds if d.get("external_chat_id") == "5559111"]
check("nhóm vẫn chưa biết tên hiện là 'Nhóm …<đuôi id>', không mượn tên người nhắn",
      nhom_la and nhom_la[0]["title"].startswith("Nhóm") and nhom_la[0]["title"].endswith("9111"),
      [d["title"] for d in ds])

# ============================================================
# 5. Gửi lỗi phải để lại dấu ở nhật ký bot (trước đây chỉ lướt qua vài giây)
# ============================================================
bid, loi = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b",
                                     "account_ids": ["zk-1"], "muc_quyen": "suggest",
                                     "groups": "5550001", "reply_when": "mention"})
DAP["zalo_send_message"] = lambda a: (_ for _ in ()).throw(RuntimeError("Zalo từ chối gửi vào nhóm"))


async def gui_loi():
    tb = kenh.Transport("zk-1", "", None, cfg_fn=lambda: chatbot_store.get_bot(bid) or {})
    await tb._gui("5550001", "Dạ em đây ạ", "group")
    return tb


tb = asyncio.run(gui_loi())
ds = chatbot_log.doc(bid, 10)
check("gửi Zalo lỗi thì ghi vào nhật ký bot kèm lý do thật",
      ds and "Gửi Zalo lỗi" in ds[0]["loi"] and "từ chối" in ds[0]["loi"], ds[:1])
check("và ghi câu định gửi để chủ biết bot đã nói gì mà không tới nơi",
      ds and ds[0]["dap"] == "Dạ em đây ạ" and ds[0]["chat_id"] == "5550001", ds[:1])

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
