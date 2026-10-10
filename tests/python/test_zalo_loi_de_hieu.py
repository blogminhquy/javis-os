"""Thẻ bot Zalo nói đúng lý do tiến trình Zalo chết, không chỉ một dòng cấu hình (0.88.6).

    python tests/run.py zalo_loi_de_hieu      (KHÔNG mạng)

Chủ repo gửi ảnh 10/10/2026: thẻ bot "Phi Yến" báo
    RuntimeError: gọi tool lỗi: RuntimeError: process đóng stdout ([mcp] Config loaded: {"maxMessagesPerPoll":20,...
rồi hết. Vòng đọc giữ 300 ký tự ĐẦU của lỗi, mà dòng "[mcp] Config loaded" (javis-zalo in lúc khởi động) đã
chiếm gần hết, nên dòng lý do thật phía sau bị cắt. Theo src/commands/mcp.js của javis-zalo v1.2.0, sau dòng
đó tiến trình chỉ tự thoát khi: Zalo đá phiên vì tài khoản mở ở nơi khác (mã 3000, "Duplicate Zalo Web
session detected"), đăng nhập lại thất bại, hoặc không dựng được server/bộ nghe.

Điều được ghim: hai lỗi người dùng tự xử được nói bằng lời thường; lỗi khác bỏ dòng cấu hình và giữ phần ĐUÔI.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sys

import localefmt
import zalo_personal_channel as zc

localefmt.dat_ngon_ngu_yeu_cau("vi")   # câu cho người dùng là tiếng Việt; bản tiếng Anh đi cùng hàm chu()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{detail!r}]"))
    if not cond:
        _fails.append(name)


CFG = ('[mcp] Config loaded: {"maxMessagesPerPoll":20,"autoDigestThreshold":50,"bufferMaxAge":"2h",'
       '"bufferMaxSize":500,"historyMaxPerThread":2000,"historyBackfillPages":5,"historyBackfillPageTimeout":"8s",'
       '"groupJoinsMax":5000}')


def loi(*dong):
    return "RuntimeError: gọi tool lỗi: RuntimeError: process đóng stdout (" + " | ".join((CFG,) + dong) + ")"


m = zc.mo_ta_loi(loi("[mcp] Zalo listener started. MCP server ready.", "[mcp] Disconnected (code: 3000). Auto-retrying...",
                     "[mcp] Duplicate Zalo Web session detected. Exiting."))
check("Zalo đá phiên: nói rõ tài khoản mở ở nơi khác", "nơi khác" in m and "Zalo Web" in m and "Config loaded" not in m, m)

m = zc.mo_ta_loi(loi("[mcp] Auto-login failed: Cookie expired"))
check("mất đăng nhập: chỉ đúng chỗ đăng nhập lại", "đăng nhập lại" in m and "QR" in m, m)
m = zc.mo_ta_loi(loi("[mcp] Re-login retry failed: blocked. Exiting."))
check("đăng nhập lại thất bại cũng là mất đăng nhập", "đăng nhập lại" in m, m)

m = zc.mo_ta_loi(loi("[mcp] Failed to start listener: ECONNRESET"))
check("lỗi khác: bỏ dòng cấu hình, giữ lý do thật", "Config loaded" not in m and "ECONNRESET" in m, m)

dai = loi("x" * 500, "[mcp] Failed to start MCP server: boom")
m = zc.mo_ta_loi(dai)
check("lỗi dài: giữ phần ĐUÔI (nơi tiến trình in lý do thoát)", m.endswith("boom)") and len(m) <= 300 and m.startswith("..."), m[-60:])

check("lỗi ngắn thường giữ nguyên", zc.mo_ta_loi("TimeoutError: tool không phản hồi sau 120s") ==
      "TimeoutError: tool không phản hồi sau 120s")

src = (SERVER / "zalo_personal_channel.py").read_text(encoding="utf-8")
check("vòng đọc dùng mo_ta_loi thay cho cắt 300 ký tự đầu",
      'tt["loi"] = mo_ta_loi(f"{type(e).__name__}: {e}")' in src and '{e}"[:300]' not in src)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
