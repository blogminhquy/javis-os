"""Lượt chat không được chết vì một nguồn MCP chậm.

    python tests/run.py khoi_dong_cham

Không cần pytest, không chạm mạng, không spawn engine.

Bối cảnh (chủ repo báo, 2026-08-11): gõ một câu dài nhờ tạo 2 trang checkout trên Webcake,
chờ rất lâu rồi nhận đúng hai dòng này trên dashboard:

    SDK engine: Exception: Control request timeout: initialize
    (không có nội dung trả về - thử lại hoặc đổi model)

Chuỗi nhân quả, đọc từ dưới lên:
  1. `claude` lúc khởi động phải đấu XONG mọi MCP server rồi mới nhận việc.
  2. Nó đấu vào hub Javis, hub trả tool bằng `mcp_client.discover_resolved`.
  3. Hàm đó dò TUẦN TỰ từng connection, mỗi connection được chờ hết trần của transport
     (http 60s, stdio 90s lúc init). Chục connector là tổng thời gian tính bằng phút.
  4. Agent SDK chỉ chờ control request `initialize` đúng 60 giây rồi ném exception.
  5. Javis in nguyên chuỗi tiếng Anh đó ra cho người dùng.

Ba chỗ đều sai nên test khoá cả ba: dò song song có trần từng nguồn (bước 3), nới trần chờ
khởi động (bước 4), và dịch lỗi ra câu chỉ được việc phải làm (bước 5).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import re
import sys
import time

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


import mcp_client  # noqa: E402
import claude_sdk_engine as eng  # noqa: E402


def _conn(i, **kw):
    c = {"id": f"c{i}", "url": f"http://127.0.0.1:9/{i}", "namespace": f"ns{i}",
         "label": f"nguồn {i}"}
    c.update(kw)
    return c


# ============================================================
# 1. Dò SONG SONG: tổng thời gian ~ nguồn chậm nhất, không phải tổng mọi nguồn
# ============================================================
_gọi = []


async def _cham(spec):
    _gọi.append(spec.get("key"))
    await asyncio.sleep(0.30)
    return [{"name": "t", "description": "d", "inputSchema": {"type": "object"}}]


_that = mcp_client.pool.list_tools
mcp_client.pool.list_tools = _cham
try:
    conns = [_conn(i) for i in range(5)]
    t0 = time.time()
    tools, route = asyncio.run(mcp_client.discover_resolved(conns))
    mat = time.time() - t0
finally:
    mcp_client.pool.list_tools = _that

check(f"5 nguồn x 0.30s dò song song xong dưới 1.0s (thật: {mat:.2f}s, tuần tự sẽ là ~1.5s)",
      mat < 1.0)
check("vẫn đủ tool của cả 5 nguồn", len(tools) == 5)
check("mỗi nguồn được dò đúng 1 lần", sorted(_gọi) == [f"c{i}" for i in range(5)])
# Thứ tự phải bám thứ tự conns: _mk_fn chống trùng bằng hậu tố, đảo thứ tự là tên tool đổi
# giữa hai lần dò và model mất tool nó vừa thấy ở lượt trước.
check("thứ tự kết quả bám đúng thứ tự conns",
      [t["namespace"] for t in tools] == [f"ns{i}" for i in range(5)])


# ============================================================
# 2. Một nguồn treo KHÔNG được kéo cả lượt chờ theo
# ============================================================
async def _mot_treo(spec):
    if spec.get("key") == "c2":
        await asyncio.sleep(30)       # nguồn chết - treo tới khi bị cắt
    return [{"name": "t", "description": "d", "inputSchema": {"type": "object"}}]


_bo = []
_inval_that = mcp_client.pool.invalidate
mcp_client.pool.invalidate = lambda k: _bo.append(k)
mcp_client.pool.list_tools = _mot_treo
os.environ["JAVIS_MCP_DISCOVER_TIMEOUT"] = "0.4"
try:
    t0 = time.time()
    tools2, _ = asyncio.run(mcp_client.discover_resolved([_conn(i) for i in range(5)]))
    mat2 = time.time() - t0
finally:
    mcp_client.pool.list_tools = _that
    mcp_client.pool.invalidate = _inval_that
    os.environ.pop("JAVIS_MCP_DISCOVER_TIMEOUT", None)

check(f"nguồn treo bị cắt đúng hạn, cả vòng xong dưới 1.5s (thật: {mat2:.2f}s)", mat2 < 1.5)
check("4 nguồn khoẻ vẫn lên tool đầy đủ", len(tools2) == 4)
check("nguồn treo không lọt vào danh sách tool",
      all(t["namespace"] != "ns2" for t in tools2))
# Huỷ từ ngoài cắt ngang giữa một request NDJSON: phiên stdio còn nửa câu trả lời trong ống,
# tái dùng là lệch pha vĩnh viễn. Phải vứt phiên chứ không chỉ bỏ qua vòng này.
check("phiên của nguồn bị cắt bị vứt (invalidate), không tái dùng", _bo == ["c2"])


# ============================================================
# 3. Trần dò từng nguồn đọc được từ biến môi trường
# ============================================================
check("mặc định có trần (không phải vô hạn)", mcp_client.tran_dial() == 20.0)
for raw, mong in (("0", None), ("-5", None), ("7.5", 7.5), ("linh tinh", 20.0)):
    os.environ["JAVIS_MCP_DISCOVER_TIMEOUT"] = raw
    check(f"JAVIS_MCP_DISCOVER_TIMEOUT='{raw}' → {mong}", mcp_client.tran_dial() == mong)
os.environ.pop("JAVIS_MCP_DISCOVER_TIMEOUT", None)


# ============================================================
# 4. Trần chờ `claude` khởi động: SDK chỉ nhận qua env, sàn cứng 60s
# ============================================================
def _sach():
    os.environ.pop("JAVIS_CLAUDE_INIT_TIMEOUT", None)
    os.environ.pop("CLAUDE_CODE_STREAM_CLOSE_TIMEOUT", None)


_sach()
check("mặc định nới lên 300s (SDK để 60s là quá ngắn cho máy đấu nhiều MCP)",
      eng.ap_tran_khoi_dong() == 300.0)
check("ghi đúng env mà SDK đọc, đơn vị mili giây",
      os.environ.get("CLAUDE_CODE_STREAM_CLOSE_TIMEOUT") == "300000")

_sach()
os.environ["JAVIS_CLAUDE_INIT_TIMEOUT"] = "900"
check("đặt biến Javis → theo người dùng", eng.ap_tran_khoi_dong() == 900.0)
check("env SDK đi theo", os.environ.get("CLAUDE_CODE_STREAM_CLOSE_TIMEOUT") == "900000")

_sach()
os.environ["JAVIS_CLAUDE_INIT_TIMEOUT"] = "10"
check("đặt thấp hơn sàn 60s của SDK → kẹp về 60, không tự lừa mình",
      eng.ap_tran_khoi_dong() == 60.0)

_sach()
os.environ["JAVIS_CLAUDE_INIT_TIMEOUT"] = "linh tinh"
check("giá trị rác → về mặc định chứ không làm nổ lượt chat", eng.ap_tran_khoi_dong() == 300.0)

_sach()
os.environ["CLAUDE_CODE_STREAM_CLOSE_TIMEOUT"] = "123000"
check("ai tự đặt biến của SDK thì tôn trọng, không đè", eng.ap_tran_khoi_dong() is None)
check("giá trị người dùng đặt còn nguyên",
      os.environ.get("CLAUDE_CODE_STREAM_CLOSE_TIMEOUT") == "123000")
_sach()


# ============================================================
# 5. Lỗi phải đọc ra được VIỆC PHẢI LÀM, không phải chuỗi tiếng Anh trần
# ============================================================
_loi_init = eng.loi_de_hieu(Exception("Control request timeout: initialize"), 300.0)
check("hết giờ khởi động: không còn ném nguyên chuỗi SDK ra mặt người dùng",
      "Control request timeout" not in _loi_init)
check("nói rõ thủ phạm là nguồn dữ liệu MCP", "nguồn" in _loi_init.lower())
check("chỉ đúng chỗ bấm để sửa", "trang Kết nối" in _loi_init)
check("nêu cả biến môi trường cho người biết chỉnh", "JAVIS_CLAUDE_INIT_TIMEOUT" in _loi_init)
check("nêu đúng con số trần đang áp dụng", "300s" in _loi_init)
check("trần None (người dùng tự đặt env SDK) vẫn ra câu đọc được, không ra 'Nones'",
      "None" not in eng.loi_de_hieu(Exception("Control request timeout: initialize")))
check("lỗi lạ thì GIỮ NGUYÊN chuỗi gốc - đoán bừa nguyên nhân còn tệ hơn",
      eng.loi_de_hieu(ValueError("abc")) == "SDK engine: ValueError: abc")

# Quy tắc cứng của dự án: không em/en dash trong chuỗi người dùng đọc.
for ten, s in (("hết giờ khởi động", _loi_init),
               ("control request khác", eng.loi_de_hieu(Exception("Control request timeout: interrupt")))):
    check(f"thông báo '{ten}' không có em/en dash", "—" not in s and "–" not in s)


# ============================================================
# 6. Đường dây thật: engine phải NỚI trần trước khi dựng client và DÙNG hàm dịch lỗi
# ============================================================
_sdk = (SERVER / "claude_sdk_engine.py").read_text(encoding="utf-8")
_than = _sdk.split("async def query")[1]
check("engine nới trần trước khi dựng ClaudeSDKClient",
      _than.index("ap_tran_khoi_dong()") < _than.index("ClaudeSDKClient(options="))
check("engine trả lỗi qua loi_de_hieu chứ không f-string thô",
      "loi_de_hieu(e, tran_init)" in _than
      and not re.search(r'"SDK engine: \{type\(e\)', _than))

_mc = (SERVER / "mcp_client.py").read_text(encoding="utf-8")
check("discover_resolved dò song song bằng gather", "asyncio.gather" in _mc)
check("mỗi nguồn có trần riêng bằng wait_for", "asyncio.wait_for(_lay()" in _mc)

if _fails:
    print(f"\nFAIL - test_khoi_dong_cham: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_khoi_dong_cham: tất cả pass")
