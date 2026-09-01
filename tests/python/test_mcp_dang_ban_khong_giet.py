"""Vòng dò tool KHÔNG được giết phiên MCP đang chạy dở một tool call.

    python tests/run.py mcp_dang_ban_khong_giet      (KHÔNG mạng, không spawn tiến trình)

Khách của chủ repo báo 01/09/2026, nguyên văn: *"Trưa mới lên đc. Nhưng chỉ lên đc 1 đơn.
Lên đơn thứ 2 là lại rớt kết nối"* với Pancake POS.

Chuỗi nhân quả:

  1. Mỗi connection chỉ có MỘT phiên trong pool, và phiên stdio có một khoá: `tools/call`
     giữ khoá suốt lúc chạy (tạo đơn POS có thể lâu).
  2. Vòng dò tool của lượt chat gọi `tools/list` trên CHÍNH phiên đó. Nó xếp hàng chờ khoá,
     chờ quá `tran_dial()` (20 giây) thì bị cắt.
  3. Nhánh xử lý quá hạn `invalidate` phiên - mà đóng phiên stdio là SIGKILL cả cây tiến
     trình (`McpStdioSession.close`). Tức là GIẾT LUÔN cái đơn đang lên dở.
  4. Vòng sau nguồn vắng mặt trong hộp công cụ, nên Javis nói "POS rớt kết nối".

Lý do gốc của dòng `invalidate` đó vẫn đúng và phải giữ: huỷ từ ngoài GIỮA một request NDJSON
để lại nửa câu trả lời trong ống, lần đọc sau lệch pha vĩnh viễn. Nhưng nó chỉ đúng khi request
ĐÃ ĐƯỢC GỬI. Chờ khoá thì chưa gửi byte nào, ống sạch nguyên.

File này khoá đúng ranh giới đó, cộng hai hệ quả đi kèm: nguồn đang bận không được biến mất
khỏi hộp công cụ, và vòng quét phiên rảnh cũng không được đóng phiên đang chạy.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import time

import mcp_client  # noqa: E402

_fails = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten
          + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        _fails.append(ten)


def conn(i, **kw):
    c = {"id": f"c{i}", "connector_id": "x", "label": f"nguồn {i}", "slug": f"s{i}",
         "namespace": f"ns{i}", "transport": "http", "url": f"http://127.0.0.1:9/{i}",
         "command": "", "args": [], "headers": {}, "env": {}, "internal": "", "secrets": {},
         "config": {}, "perm": "full", "deny_tools": [], "is_default": False,
         "auth": None, "connector": {}}
    c.update(kw)
    return c


class PhienGia:
    """Bản rút gọn của một phiên thật: MỘT khoá dùng chung cho list_tools và call_tool, và
    `close()` là giết (ghi lại để test soi được)."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.da_giet = False
        self.so_lan_goi = 0

    async def list_tools(self):
        async with self.lock:
            return [{"name": "pos_tao_don", "description": "lên đơn",
                     "inputSchema": {"type": "object", "properties": {}}}]

    async def call_tool(self, name, arguments):
        async with self.lock:
            self.so_lan_goi += 1
            await asyncio.sleep(_LAU)
            return "đã lên đơn"

    async def close(self):
        self.da_giet = True


_LAU = 0.6            # "tạo đơn POS" chạy lâu
_phien = {}           # key -> PhienGia (giữ tham chiếu để soi sau khi pool vứt đi)


def _make_gia(spec):
    p = PhienGia()
    _phien[spec.get("key")] = p
    return p


mcp_client.SessionPool._make = staticmethod(_make_gia)
pool = mcp_client.SessionPool()
mcp_client.pool = pool          # discover_resolved/warm_pool dùng biến module
spec1 = mcp_client._conn_spec(conn(1))
os.environ["JAVIS_MCP_DISCOVER_TIMEOUT"] = "0.15"      # ngắn hơn hẳn _LAU


async def _kich_ban():
    # --- Vòng dò LÀNH: nguồn lên đủ tool, và pool nhớ lại danh sách đó ---
    tools, _ = await mcp_client.discover_resolved([conn(1)])
    check("vòng dò bình thường: nguồn lên đủ tool", [t["name"] for t in tools] == ["pos_tao_don"],
          [t["name"] for t in tools])
    check("pool NHỚ danh sách tool vừa dò được", bool(pool.tool_da_biet(spec1)))
    check("lúc rảnh thì không bị coi là đang bận", pool.dang_goi_tool(spec1) is False)

    # --- Đang lên đơn: cờ bận phải bật ---
    don = asyncio.create_task(pool.call_tool(spec1, "pos_tao_don", {"kh": "Ngọc Bích"}))
    await asyncio.sleep(0.05)
    check("đang chạy tool → pool biết phiên đang bận", pool.dang_goi_tool(spec1) is True)

    # --- Vòng dò rơi vào GIỮA lúc đang lên đơn ---
    bo_qua = set()
    tools2, _ = await mcp_client.discover_resolved([conn(1)], bo_qua=bo_qua)
    p = _phien[spec1.get("key")]
    check("KHÔNG giết phiên đang lên đơn (đây là cả cái bug)", p.da_giet is False)
    check("nguồn VẪN có trong hộp công cụ (dùng lại danh sách lần trước)",
          [t["name"] for t in tools2] == ["pos_tao_don"], [t["name"] for t in tools2])
    check("và không bị đánh dấu là nguồn bị bỏ", bo_qua == set(), bo_qua)

    # --- Vòng quét phiên rảnh cũng không được đụng vào ---
    ent = pool._sessions.get(spec1.get("key"))
    if ent is None:
        # Phiên đã bị vứt ở bước trên (tức là bản đang chạy CHƯA có bản vá) - báo đỏ cho rõ
        # thay vì nổ TypeError giữa chừng rồi giấu mất mấy dòng FAIL bên trên.
        check("phiên đang chạy tool vẫn còn trong pool để mà quét", False, "pool đã vứt phiên")
    else:
        ent["last"] = time.time() - (mcp_client._IDLE_TTL + 60)   # giả vờ đã rảnh rất lâu
        pool._sweep()
        check("vòng quét phiên rảnh KHÔNG đóng phiên đang chạy tool",
              p.da_giet is False and spec1.get("key") in pool._sessions)

    # --- Cái đơn phải về đích nguyên vẹn ---
    ket_qua = await don
    check("đơn chạy xong bình thường, không bị cắt ngang", ket_qua == "đã lên đơn", ket_qua)
    check("gọi tool ĐÚNG MỘT lần (không retry thành đơn trùng)", p.so_lan_goi == 1, p.so_lan_goi)
    check("chạy xong thì hạ cờ bận", pool.dang_goi_tool(spec1) is False)


asyncio.run(_kich_ban())


# ============================================================
# Vế ngược: server TREO THẬT thì vẫn phải vứt phiên như cũ
# ============================================================
# Đây là lý do gốc của dòng `invalidate`. Mất vế này thì một nguồn treo sẽ được tái dùng mãi
# với cái ống stdio lệch pha - hỏng nặng hơn hẳn thứ đang sửa.
class PhienTreo(PhienGia):
    async def list_tools(self):
        await asyncio.sleep(10)     # treo giữa request, KHÔNG phải chờ khoá
        return []


def _make_treo(spec):
    p = PhienTreo()
    _phien[spec.get("key")] = p
    return p


mcp_client.SessionPool._make = staticmethod(_make_treo)
pool2 = mcp_client.SessionPool()
mcp_client.pool = pool2
spec2 = mcp_client._conn_spec(conn(2))


async def _kich_ban_treo():
    bo_qua = set()
    tools, _ = await mcp_client.discover_resolved([conn(2)], bo_qua=bo_qua)
    p = _phien[spec2.get("key")]
    check("server treo (không bận tool) → VẪN vứt phiên như cũ", p.da_giet is True)
    check("và nguồn bị bỏ khỏi vòng này như cũ", tools == [] and bo_qua == {"c2"}, bo_qua)


asyncio.run(_kich_ban_treo())

os.environ.pop("JAVIS_MCP_DISCOVER_TIMEOUT", None)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + "; ".join(_fails[:4]))
    raise SystemExit(1)
print("Tất cả xanh.")
