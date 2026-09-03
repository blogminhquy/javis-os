"""Máy chủ MCP xoá phiên: Javis phải TỰ BẮT TAY LẠI, không được im lặng trả hộp rỗng.

    python tests/run.py mcp_phien_het_han      (KHÔNG mạng - giả lập httpx)

Lỗi thật, chủ repo báo 03/09/2026 với Pancake POS "Làng Chài Xưa", và đã tái diễn nhiều lần
trước đó (05/07, 26/08, 02/09): trang Kết nối chấm XANH, quyền đủ, `javis_connections` báo
"ổn", mà không bộ não nào tìm ra một tool POS nào. Người dùng đi tìm lỗi ở token, ở quyền, ở
brain - trong khi cả ba đều đúng.

Gốc rễ nằm ở MỘT dòng thiếu trong `McpHttpSession._rpc`: nó KHÔNG đọc mã HTTP.

Chuẩn Streamable HTTP cho phép máy chủ xoá phiên bất cứ lúc nào (hết hạn, deploy lại, bộ cân
tải đổi máy) và quy định lúc đó máy chủ trả **404**, còn **client PHẢI tự bắt tay lại**. Javis
không đọc mã, nên 404 kèm thân JSON-RPC bị `r.json()` nuốt thành một phản hồi bình thường:

    tools/list -> {"error": {...}}  ->  ((res).get("result") or {}).get("tools", [])  ->  []

Không có ngoại lệ nào được ném ra, và cả dây chuyền phía trên đều đọc "không có ngoại lệ" là
"mọi thứ ổn":

  - `SessionPool._retry` chỉ dựng lại phiên khi CÓ ngoại lệ, nên phiên chết nằm lại trong
    pool; mỗi lần dùng lại còn được gia hạn `last` nên vòng quét phiên rảnh (15 phút) không
    bao giờ dọn tới - càng thử lại càng lâu khỏi. Đúng cảnh "để 15-20 phút thì tự hết".
  - `discover_resolved` thấy 0 tool thì `continue` và KHÔNG ghi vào `bo_qua`, nên hub tưởng
    vòng dò đủ và đóng băng danh sách thiếu nguồn suốt 60 giây.
  - `connect_health` thấy không có ngoại lệ -> `ok=True, tools=0` -> chấm xanh ghi thẳng
    "Hoạt động bình thường (0 công cụ)".

Trách nhiệm: máy chủ Pancake xoá phiên là ĐÚNG chuẩn, không phải lỗi của họ. Bên sai chuẩn là
Javis. Nên bản vá nằm hết ở phía Javis, và test này ghim cả bốn mảnh của nó.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-phien-"))

import httpx          # noqa: E402
import mcp_client     # noqa: E402
import connect_health  # noqa: E402

_fails = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten
          + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        _fails.append(ten)


def _res(status, body=None, text="", sid=None):
    h = {"mcp-session-id": sid} if sid else {}
    req = httpx.Request("POST", "https://mcp-pos.pancake.biz/mcp")
    if body is not None:
        return httpx.Response(status, json=body, headers=h, request=req)
    return httpx.Response(status, text=text, headers=h, request=req)


# ============================================================
# 1. Phân biệt "phiên chết" với "hỏng thật"
# ============================================================
# Ranh giới này phải chính xác cả hai chiều. Bắt thiếu thì lỗi cũ tái diễn; bắt thừa thì key
# sai (401) bị đem đi bắt tay lại vô hạn, và người dùng không bao giờ thấy câu "sai key".
sess = mcp_client.McpHttpSession("https://mcp-pos.pancake.biz/mcp")
check("chưa cầm phiên nào thì 404 KHÔNG phải phiên chết (đó là URL sai)",
      sess._la_phien_chet(_res(404, {"error": {"message": "Session not found"}})) is False)

sess.session_id = "sid-1"
check("đang cầm phiên mà gặp 404 -> phiên chết (đúng chuẩn Streamable HTTP)",
      sess._la_phien_chet(_res(404, {"error": {"message": "Session not found"}})) is True)
# SDK TypeScript - thứ phần lớn máy chủ MCP dùng - trả 400 chứ không 404.
check("400 kèm câu nhắc session -> cũng là phiên chết",
      sess._la_phien_chet(_res(400, text="Bad Request: No valid session ID provided")) is True)
check("CANARY: 401 KHÔNG bao giờ là phiên chết (key sai phải nói là key sai)",
      sess._la_phien_chet(_res(401, {"error": {"message": "Unauthorized"}})) is False)
check("400 vì tham số sai cũng không phải phiên chết",
      sess._la_phien_chet(_res(400, {"error": {"message": "Invalid params: missing action"}})) is False)
check("500 không phải phiên chết", sess._la_phien_chet(_res(500, text="upstream error")) is False)


# ============================================================
# 2. Máy chủ xoá phiên GIỮA CHỪNG: tự bắt tay lại, người dùng không thấy gì cả
# ============================================================
class MayChu:
    """Máy chủ MCP cư xử đúng chuẩn: phiên đã xoá -> 404; initialize không kèm phiên -> cấp mới."""

    def __init__(self):
        self.song = set()
        self.dem = 0
        self.rpc = []
        self.goi_tool = 0

    async def post(self, url, headers=None, json=None, **kw):
        m = (json or {}).get("method")
        sid = (headers or {}).get("Mcp-Session-Id")
        self.rpc.append(m)
        if sid and sid not in self.song:
            return _res(404, {"jsonrpc": "2.0", "id": (json or {}).get("id"),
                              "error": {"code": -32001, "message": "Session not found"}})
        if m == "initialize":
            self.dem += 1
            moi = f"sid-{self.dem}"
            self.song.add(moi)
            return _res(200, {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18"}},
                        sid=moi)
        if m == "tools/list":
            return _res(200, {"jsonrpc": "2.0", "id": 2, "result": {"tools": [
                {"name": "pos_order"}, {"name": "pos_statistics"}, {"name": "pos_shop"}]}})
        if m == "tools/call":
            self.goi_tool += 1
            return _res(200, {"jsonrpc": "2.0", "id": 3,
                              "result": {"content": [{"type": "text", "text": '{"doanh_thu":128500000}'}]}})
        return _res(202, text="")


may = MayChu()
httpx.AsyncClient.post = lambda self, url, **kw: may.post(url, **kw)

SPEC = {"key": "conn-lcx", "transport": "http", "url": "https://mcp-pos.pancake.biz/mcp",
        "headers": {"Authorization": "Bearer k"}, "label": "Pancake POS - Làng Chài Xưa"}
CONN = dict(SPEC, id="conn-lcx", namespace="lang-chai-xua", perm="full",
            connector_id="pancake-pos")
AO = {"id": "conn-ao", "transport": "http", "url": "", "command": "", "namespace": "meta",
      "label": "Meta Ads (connector ảo)", "perm": "full"}


async def _kich_ban():
    t = await mcp_client.pool.list_tools(SPEC)
    check("phiên khoẻ: dò ra đủ tool", len(t) == 3, len(t))

    may.song.clear()          # Pancake deploy lại / phiên hết hạn
    may.rpc.clear()
    t = await mcp_client.pool.list_tools(SPEC)
    check("CANARY: máy chủ vừa xoá phiên -> VẪN đủ tool (tự bắt tay lại)", len(t) == 3, len(t))
    check("và đúng là đã gửi initialize mới chứ không phải may rủi",
          "initialize" in may.rpc, may.rpc)

    bo_qua = set()
    ts, _r = await mcp_client.discover_resolved([CONN], bo_qua=bo_qua)
    check("vòng dò tool của hub cũng liền lại, nguồn không biến mất",
          len(ts) == 3 and not bo_qua, (len(ts), bo_qua))

    rec = await connect_health.check_one(CONN)
    check("đèn sức khoẻ xanh và đếm đúng số tool", rec["ok"] and rec["tools"] == 3, rec)

    # Tool call thật (lên đơn, đọc doanh thu) rơi đúng lúc mất phiên: 404 nghĩa là máy chủ TỪ
    # CHỐI trước khi chạy tool, nên gửi lại là an toàn - không có chuyện lên đơn hai lần.
    may.song.clear()
    may.goi_tool = 0
    r = await mcp_client.pool.call_tool(SPEC, "pos_statistics", {"action": "list"})
    check("gọi tool giữa lúc mất phiên vẫn ra kết quả", "128500000" in str(r), str(r)[:80])
    check("CANARY: và tool chỉ CHẠY ĐÚNG MỘT LẦN (không lên đơn trùng)",
          may.goi_tool == 1, may.goi_tool)

asyncio.run(_kich_ban())


# ============================================================
# 3. Lưới an toàn: máy chủ trả 200 nhưng hộp công cụ RỖNG
# ============================================================
# Không có lỗi nào để bắt ở đây, nên hai chốt dưới là thứ duy nhất ngăn cảnh "xanh mà rỗng"
# quay lại bằng một con đường khác.
class MayRong(MayChu):
    async def post(self, url, headers=None, json=None, **kw):
        m = (json or {}).get("method")
        if m == "initialize":
            return _res(200, {"jsonrpc": "2.0", "id": 1, "result": {}}, sid="sid-rong")
        if m == "tools/list":
            return _res(200, {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}})
        return _res(202, text="")


rong = MayRong()
httpx.AsyncClient.post = lambda self, url, **kw: rong.post(url, **kw)
mcp_client.pool.invalidate("conn-lcx")


async def _kich_ban_rong():
    bo_qua = set()
    ts, _r = await mcp_client.discover_resolved([CONN, AO], bo_qua=bo_qua)
    check("CANARY: nguồn dò ra 0 tool bị ghi là THIẾU (hub cache 10s thay vì đóng băng 60s)",
          ts == [] and "conn-lcx" in bo_qua, bo_qua)
    check("nhưng connector ẢO thì không (nó vốn không có tool, báo thiếu là báo oan)",
          "conn-ao" not in bo_qua, bo_qua)

    rec = await connect_health.check_one(CONN)
    check("CANARY: 0 tool KHÔNG được tô xanh 'Hoạt động bình thường (0 công cụ)'",
          rec["ok"] is False and rec["kind"] == "empty", rec)
    rec = await connect_health.check_one(AO)
    check("connector ảo vẫn xanh như cũ", rec["ok"] is True, rec)

asyncio.run(_kich_ban_rong())


# ============================================================
# 4. Bệnh thật vẫn phải nói đúng bệnh
# ============================================================
async def _sai_key(url, headers=None, json=None, **kw):
    return _res(401, {"error": {"message": "Unauthorized: invalid api key"}})


httpx.AsyncClient.post = lambda self, url, **kw: _sai_key(url, **kw)
mcp_client.pool.invalidate("conn-lcx")


async def _kich_ban_key():
    rec = await connect_health.check_one(CONN)
    check("key sai -> đỏ, và phân loại đúng nhóm auth (UI mọc nút Kết nối lại)",
          rec["ok"] is False and rec["kind"] == "auth", rec)

    # initialize hỏng mà vẫn đánh dấu "đã bắt tay" thì phiên đó mang cờ sai suốt đời, mọi lượt
    # sau gửi đi trong vô vọng mà không ai dựng lại nó.
    s = mcp_client.McpHttpSession("https://mcp-pos.pancake.biz/mcp")
    try:
        await s.ensure_init()
    except Exception:
        pass
    check("CANARY: initialize hỏng thì KHÔNG được đánh dấu đã bắt tay",
          s._init_done is False)

asyncio.run(_kich_ban_key())


# ============================================================
# 5. CANARY nguồn: đừng ai gỡ việc đọc mã HTTP đi nữa
# ============================================================
_src = (SERVER / "mcp_client.py").read_text(encoding="utf-8")
_rpc = _src.split("    async def _rpc(self, method, params=None, notify=False", 1)[1].split(
    "\n    async def ", 1)[0]
check("CANARY: _rpc của HTTP có đọc status_code", "r.status_code >= 400" in _rpc)
check("CANARY: và mã lỗi HTTP được NÉM RA chứ không nuốt thành kết quả rỗng",
      "raise McpHttpError" in _rpc)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + "; ".join(_fails[:4]))
    raise SystemExit(1)
print("Tất cả xanh.")
