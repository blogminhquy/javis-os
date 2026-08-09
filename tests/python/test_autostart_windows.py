"""Tự khởi động cùng Windows: bật rồi mà không chạy thì phải NÓI RA vì sao.

    python tests/run.py autostart      (KHÔNG mạng, không đụng registry thật)

Chủ repo gửi ảnh chụp trình duyệt sau khi mở máy (2026-08-09): `localhost:7777` trả
ERR_CONNECTION_REFUSED, kèm "hình như chức năng mở Javis cùng máy startup đang không hoạt động".

Cả tính năng này nằm gọn trong một dòng registry `HKCU\\...\\Run` trỏ `wscript start-javis.vbs`.
Dashboard đọc đúng dòng đó rồi kết luận "Bật". Vấn đề: dòng đó CÒN NGUYÊN trong ít nhất ba
cảnh mà lúc đăng nhập vẫn không có gì chạy, và không cảnh nào để lại lỗi ở đâu:

  1. **Task Manager tắt hộ.** Thẻ Startup không xoá mục trong Run key, nó ghi một cờ 12 byte
     vào `Explorer\\StartupApproved\\Run` rồi Explorer bỏ qua mục đó. Mấy phần mềm "dọn máy,
     tăng tốc khởi động" cũng tắt bằng đúng cờ này. Đây là cảnh im lặng nhất trong ba.
  2. **Thư mục cài đặt đổi chỗ**, lệnh trỏ đường dẫn cũ. Trạng thái đã tính sẵn cờ `stale` từ
     lâu, nhưng trang Cài đặt bỏ qua nó, nên cùng một máy hỏng mà hai trang nói khác nhau.
  3. **Mảnh của dây chuyền biến mất** (`start-javis.vbs` hoặc `.venv\\Scripts\\python.exe`).
     `wscript` không thấy file .vbs thì im, còn `cmd` ghi lỗi vào `javis.log` - một file không
     ai mở ra xem bao giờ.

File này canh phần LOGIC (chạy được trên Linux của CI) và canh việc dashboard thật sự hiện lý
do ra. Phần đọc/ghi registry chỉ có trên Windows nên không mô phỏng ở đây; đổi lại, mọi quyết
định đều nằm trong các hàm thuần dưới đây chứ không nhét trong nhánh `winreg`.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-autostart-"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Cờ StartupApproved: đọc theo BIT, không so bằng
# ============================================================
def _co(byte_dau):
    return bytes([byte_dau] + [0] * 11)


check("cờ 3 = Task Manager đã tắt mục này", main._autostart_bi_chan(_co(3)) is True)
check("cờ 2 = đang bật", main._autostart_bi_chan(_co(2)) is False)
# Windows dùng cả 6 cho trạng thái bật, nên so bằng 2 là đọc sai một nửa số máy.
check("CANARY: cờ 6 cũng là đang bật (so bằng 2 là đọc sai)",
      main._autostart_bi_chan(_co(6)) is False)
check("không có cờ = chưa ai tắt", main._autostart_bi_chan(None) is False)
check("cờ rỗng cũng là chưa ai tắt", main._autostart_bi_chan(b"") is False)
check("cờ hỏng thì không nổ", main._autostart_bi_chan("linh tinh") is False)


# ============================================================
# 2. Thiếu mảnh nào của dây chuyền khởi động
# ============================================================
_tmp = Path(tempfile.mkdtemp(prefix="javis-goc-"))
check("thư mục trống -> thiếu cả hai mảnh",
      set(main._autostart_thieu_gi(_tmp)) == {"start-javis.vbs", r".venv\Scripts\python.exe"})

(_tmp / "start-javis.vbs").write_text("' bo mo phong", encoding="utf-8")
check("có .vbs rồi -> chỉ còn thiếu python của venv",
      main._autostart_thieu_gi(_tmp) == [r".venv\Scripts\python.exe"])

(_tmp / ".venv" / "Scripts").mkdir(parents=True)
(_tmp / ".venv" / "Scripts" / "python.exe").write_text("x", encoding="utf-8")
check("đủ cả hai -> không thiếu gì", main._autostart_thieu_gi(_tmp) == [])


# ============================================================
# 3. Lý do: một câu nói thẳng, và ĐÚNG THỨ TỰ ưu tiên
# ============================================================
check("chưa bật thì không có lý do nào để báo",
      main._autostart_ly_do({"enabled": False, "blocked": True}) == "")

_ly = main._autostart_ly_do({"enabled": True, "blocked": True})
check("bị Windows chặn -> nói rõ chặn ở đâu", "Task Manager" in _ly)
check("và chỉ luôn cách gỡ", "bật lại" in _ly)

_ly = main._autostart_ly_do({"enabled": True, "stale": True})
check("đường dẫn cũ -> nói rõ là đổi chỗ", "đổi chỗ" in _ly and "bật lại" in _ly.casefold())

_ly = main._autostart_ly_do({"enabled": True, "missing": ["start-javis.vbs"]})
check("thiếu file -> gọi tên đúng file thiếu", "start-javis.vbs" in _ly)
check("và chỉ luôn cách dựng lại", "setup.bat" in _ly)

check("bật và mọi thứ ổn -> im lặng, không doạ người dùng",
      main._autostart_ly_do({"enabled": True, "blocked": False, "stale": False,
                             "missing": []}) == "")

# Chặn thắng stale: gỡ chặn xong mới tới lượt lo đường dẫn, chứ sửa đường dẫn trong khi
# Windows vẫn chặn thì bấm bao nhiêu lần cũng không chạy.
_ly = main._autostart_ly_do({"enabled": True, "blocked": True, "stale": True,
                             "missing": ["start-javis.vbs"]})
check("nhiều lỗi cùng lúc -> báo cái phải sửa TRƯỚC", "Task Manager" in _ly)

for _st in ({"enabled": True, "blocked": True}, {"enabled": True, "stale": True},
            {"enabled": True, "missing": ["x"]}):
    check(f"lý do không dùng em dash ({list(_st)[-1]})", "—" not in main._autostart_ly_do(_st))


# ============================================================
# 4. Bật lại phải THẬT SỰ gỡ được chặn, không chỉ ghi lại Run key
# ============================================================
# Ghi lại Run key không đụng gì tới cờ StartupApproved. Thiếu bước gỡ cờ thì nút "Bật tự khởi
# động" trở thành một cái nút không làm gì: bấm xong thẻ vẫn báo bật, mở máy vẫn không có gì.
_MAIN_SRC = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
check("CANARY: bật lại có gỡ cờ chặn của Task Manager",
      "StartupApproved" in _MAIN_SRC and "_AUTOSTART_APPROVED_ON" in _MAIN_SRC)
check("chỉ lật cờ ĐÃ CÓ, không tự tạo mới (không có cờ vốn đã là bật)",
      "if _autostart_bi_chan(raw):" in _MAIN_SRC)
check("trạng thái trả về kèm đường dẫn log để còn chỗ mà soi",
      '"log": str(PROJECT_ROOT / "server" / "javis.log")' in _MAIN_SRC)


# ============================================================
# 5. Dashboard phải HIỆN lý do đó ra, ở CẢ HAI trang
# ============================================================
# Trang Tổng quan và trang Cài đặt cùng đọc một endpoint. Bản trước trang Cài đặt bỏ qua hẳn cờ
# `stale`, nên cùng một máy hỏng mà mở hai trang thì đọc được hai câu trả lời khác nhau.
_JS = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("CANARY: cả hai trang đều hiện `ly_do`", _JS.count("j.ly_do") >= 2)
check("nhãn nói thật khi bật mà không chạy được", "bật nhưng không chạy" in _JS.casefold())
check("dashboard KHÔNG tự dựng lại câu lý do (server là nguồn duy nhất)",
      "Task Manager" not in _JS)

if _fails:
    raise SystemExit(f"\nFAIL - test_autostart_windows: {len(_fails)} lỗi")
print("\nOK - test_autostart_windows: tất cả pass")
