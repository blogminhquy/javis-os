"""Thông báo lỗi MCP stdio phải GIỮ ĐƯỢC dòng nguyên nhân, không nuốt mất nó.

    python tests/run.py loi_mcp_noi_that     (KHÔNG mạng)

Lỗi thật (báo 2026-08-14, thẻ Google Sheets): gói mcp-google-sheets chết ngay dòng
import vì mcp 2.0 bỏ mcp.server.fastmcp. Nguyên nhân nằm gọn một dòng cuối stderr:

    ModuleNotFoundError: No module named 'mcp.server.fastmcp'

Nhưng user không bao giờ thấy dòng đó, vì chuỗi lỗi đi qua BA lớp cắt và cả ba đều cắt
từ ĐẦU, trong khi traceback Python để nguyên nhân ở dòng CUỐI. Một dòng "File .../.cache/
uv/..." đã ~135 ký tự, vừa khít hạn mức [:160] của hub, nên dòng quyết định LUÔN LUÔN
bị vứt - không phải xui một lần mà là cấu trúc. Kèm câu gợi ý gắn cứng "Kiểm tra lại
key/URL" dẫn user đi sai hướng có hệ thống: họ tạo lại key/service account nhiều giờ
trong khi key đúng từ đầu.

Test này ghim 3 hành vi sửa: (1) _err_tail giữ ĐUÔI thay vì giữ đầu, (2) hub giữ đuôi
chuỗi lỗi + đổi gợi ý khi dấu hiệu là crash phụ thuộc, (3) catalog ghim mcp<2 cho hai
gói đã xác nhận gãy. Kèm canary chống ghim bừa: các thẻ uvx đã test chạy tốt với mcp 2.x
thì KHÔNG được ghim <2, ép sai chiều là gãy chiều ngược lại.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. _err_tail giữ ĐUÔI ----
import mcp_client  # noqa: E402

sess = mcp_client.McpStdioSession("echo")

# Dựng đúng hình dạng stderr của vụ thật: traceback dài, dòng nguyên nhân ở cuối.
DONG_CACHE = ('  File "/home/javis/.cache/uv/archive-v0/SAthnrr9ruwms05D/lib/python3.12/'
              'site-packages/mcp_google_sheets/__init__.py", line 1, in <module>')
DONG_NGUYEN_NHAN = "ModuleNotFoundError: No module named 'mcp.server.fastmcp'"
for i in range(30):
    sess._stderr.append(DONG_CACHE)
sess._stderr.append(DONG_NGUYEN_NHAN)

tail = sess._err_tail()
check("CANARY: dòng nguyên nhân (cuối traceback) SỐNG SÓT qua _err_tail",
      DONG_NGUYEN_NHAN in tail)
check("_err_tail có trần độ dài (không đổ nguyên traceback vào thông báo)",
      len(tail) <= 950)
check("deque chứa đủ traceback dài (maxlen >= 31 dòng của vụ thật)",
      len(sess._stderr) == 31)

sess2 = mcp_client.McpStdioSession("echo")
check("_err_tail rỗng khi chưa có stderr", sess2._err_tail() == "")
sess2._stderr.append("   ")
check("_err_tail bỏ qua dòng trắng", sess2._err_tail() == "")

# ---- 2. Hub: giữ đuôi + gợi ý theo dấu hiệu ----
# Đối chiếu trên chính mã nguồn (logic nằm inline trong handler async, dựng cả hub để
# gọi thật thì phải giả lập connection store - không đáng cho một khối except).
src = (SERVER / "mcp_hub.py").read_text(encoding="utf-8")

check("CANARY: hub không còn cắt [:160] từ đầu chuỗi lỗi", "str(e)[:160]" not in src)
check("hub giữ ĐUÔI chuỗi lỗi (cắt [-400:])", 'chi_tiet[-400:]' in src)
check("hub nhận diện crash phụ thuộc qua dấu hiệu", '"ModuleNotFoundError"' in src)
check("crash phụ thuộc thì gợi ý ghim phiên bản, không đổ cho key",
      "KHÔNG phải key" in src)
check("lỗi thường vẫn giữ gợi ý key/URL cũ", "Kiểm tra lại key/URL hoặc thử lại." in src)

# ---- 3. _rpc đợi stderr drain xong mới dựng thông báo ----
src_client = (SERVER / "mcp_client.py").read_text(encoding="utf-8")
check("stdout đóng thì đợi drain stderr rồi mới raise",
      "await self._doi_stderr_xong()" in src_client
      and src_client.index("_doi_stderr_xong()") < src_client.index("process đóng stdout"))

# ---- 4. Catalog: ghim đúng chỗ, không ghim bừa ----
cat = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))
entries = {c["id"]: c for c in (cat if isinstance(cat, list) else cat.get("connectors") or cat.get("items") or [])}


def args_cua(cid):
    return entries.get(cid, {}).get("args") or []


def co_ghim_mcp2(cid):
    a = args_cua(cid)
    return "--with" in a and any("mcp<2" in x for x in a)


check("CANARY: google-sheets ghim mcp<2 (đã xác nhận gãy với mcp 2.x)",
      co_ghim_mcp2("google-sheets"))
# Trước 0.55.36 chỗ này còn kiểm tiktok-ads mắc cùng bệnh. Khuôn đó đã dọn sang repo kho,
# nên phép kiểm đi theo nó - google-sheets ở lại app và vẫn tái hiện đúng cùng một bệnh.

# Chống ghim bừa: các gói này đã test 2026-08-16 và CHẠY TỐT với mcp 2.x. Ép mcp<2 cho
# gói đang cần mcp 2 là tự tạo đúng loại lỗi mình vừa sửa, theo chiều ngược lại.
for cid in ("google-workspace", "google-tasks", "google-keep", "notebooklm", "google-ads"):
    if cid in entries:
        check(f"{cid} KHÔNG bị ghim mcp<2 (đang chạy tốt với mcp 2.x)",
              not co_ghim_mcp2(cid))

if _fails:
    print(f"\nFAIL {len(_fails)} muc: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_loi_mcp_noi_that: tat ca pass")
