"""Cài thư viện `playwright` THEO YÊU CẦU ở trang Công cụ, không nhét vào bản cài.

    python tests/run.py cong_cu_thu_vien

Vì sao tính năng này tồn tại: engine ChatGPT Web cần gói Python `playwright`, nặng 46 MB tải về
và 140 MB sau khi cài. Nhét vào `requirements.txt` là bắt MỌI bản cài trả chỗ cho một thứ phần
lớn máy không dùng, mà phần lớn máy chạy Javis là VPS không màn hình. Dockerfile đã ghi sẵn quy
ước này cho chính trình duyệt Chromium, nên thư viện đi cùng đường.

Ràng buộc KHÔNG lách được, và là lý do phải có `--target`: trong Docker, `site-packages` thuộc
root và để chỉ đọc, còn Javis chạy bằng user `javis` (uid 10001). Một `pip install` kiểu thường
sẽ hỏng vì không ghi được, và không nút bấm nào cứu được điều đó. Cài vào thư mục state (ổ gắn
ngoài, ghi được) là đường duy nhất chạy được, và nó còn sống qua mỗi lần cập nhật.

Ba bất biến phải giữ:
  1. Lệnh cài phải ghi vào thư mục GHI ĐƯỢC, không vào site-packages.
  2. Cài xong phải IMPORT ĐƯỢC. Cài mà không nạp vào `sys.path` là người dùng thấy báo xong
     rồi tính năng vẫn kêu thiếu thư viện - kiểu hỏng khó đoán nhất.
  3. Gỡ chỉ đụng thứ CHÍNH JAVIS cài, không bao giờ đụng Python của máy.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-congcu-")

import optional_tools as ot  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + ((f"  [{them}]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1) Công cụ mới có mặt, và không đụng công cụ cũ
# ============================================================

check("có công cụ thư viện playwright", "pylib-playwright" in ot.CONG_CU)
check("công cụ trình duyệt vẫn còn nguyên", "browser" in ot.CONG_CU)

_ds = ot.danh_sach()
check("danh sách trả về cả hai thẻ", len(_ds) == 2)
check("mỗi thẻ có đủ trường màn hình cần",
      all({"id", "ten", "mo_ta", "trang_thai", "ly_do", "go_duoc"} <= set(t) for t in _ds))

_tt = ot.trang_thai("pylib-playwright")
check("chưa cài -> trạng thái chua_cai hoặc san_sang (máy dev có thể đã có sẵn)",
      _tt["trang_thai"] in ("chua_cai", "san_sang"))
check("thẻ nói rõ phải khởi động lại sau khi cài",
      "khởi động lại" in (_tt["ly_do"] + ot._mo_ta_pylib()["mo_ta"]).lower()
      or _tt["trang_thai"] == "san_sang")
check("công cụ lạ thì từ chối nói được", ot.trang_thai("khong-co-that").get("error"))


# ============================================================
# 2) LỆNH CÀI: ghi vào thư mục ghi được, không vào site-packages
# ============================================================
#
# Đây là phần dễ sai nhất và cũng là phần rẻ nhất để soi: chỉ cần dựng lệnh ra rồi đọc.

_lenh, _cwd, _env, _tran, _loi = ot._lenh_cai("pylib-playwright")
check("chạy pip bằng CHÍNH Python đang chạy Javis", _lenh[:3] == [sys.executable, "-m", "pip"])
check("có cờ --target (không có là hỏng trong Docker)", "--target" in _lenh)
check("target trỏ đúng thư mục state ghi được",
      _lenh[_lenh.index("--target") + 1] == str(ot.PYLIBS_DIR))
check("thư mục đó nằm TRONG state dir", str(ot.PYLIBS_DIR).startswith(os.environ["JAVIS_STATE_DIR"]))
check("cài đúng gói playwright", _lenh[-1] == "playwright")
check("có --upgrade (bấm cài lại phải thật sự cài lại)", "--upgrade" in _lenh)
check("KHÔNG dùng --user (trong Docker HOME có thể không ghi được)", "--user" not in _lenh)
check("KHÔNG cài kiểu thường vào site-packages",
      not any(a in _lenh for a in ("--prefix", "--root")))
check("câu lỗi khi máy không có pip nói được", "pip" in _loi)

_lenh_b, _cwd_b, _env_b, _tran_b, _loi_b = ot._lenh_cai("browser")
check("công cụ trình duyệt vẫn dựng đúng lệnh cũ",
      _lenh_b[:2] == ["npx", "-y"] and "chromium" in _lenh_b)
check("trình duyệt vẫn được truyền PLAYWRIGHT_BROWSERS_PATH",
      _env_b.get(ot.ENV_BROWSERS_PATH) == str(ot.BROWSERS_DIR))
check("hai công cụ có trần giờ RIÊNG (cài thư viện nhanh hơn tải trình duyệt)",
      _tran < _tran_b)


# ============================================================
# 3) Cài xong phải IMPORT ĐƯỢC
# ============================================================
#
# Giả lập một bản cài thành công bằng cách dựng đúng hình dạng `pip --target` để lại: một thư
# mục `playwright` trong PYLIBS_DIR. Soi hành vi thật chứ không tin vào chữ trong mã.

check("chưa có gì -> chưa coi là đã cài", not ot._da_cai_pylib())
check("chưa có gì -> nap_pylibs() trả False, không nhét rác vào sys.path",
      not ot.nap_pylibs() and str(ot.PYLIBS_DIR) not in sys.path)

_goi = ot.PYLIBS_DIR / "playwright"
_goi.mkdir(parents=True, exist_ok=True)
(_goi / "__init__.py").write_text("GIA = True\n", encoding="utf-8")

check("thấy thư mục gói -> coi là đã cài", ot._da_cai_pylib() == str(ot.PYLIBS_DIR))
check("nap_pylibs() đưa thư mục vào sys.path",
      ot.nap_pylibs() and str(ot.PYLIBS_DIR) in sys.path)
check("nạp lần hai KHÔNG nhét trùng vào sys.path",
      (ot.nap_pylibs(), sys.path.count(str(ot.PYLIBS_DIR)))[1] == 1)
# Chèn vào CUỐI: bản người dùng chủ động cài trong Python của máy phải thắng bản Javis tải về.
check("thư mục tự cài nằm CUỐI sys.path, không đè bản có sẵn của máy",
      sys.path.index(str(ot.PYLIBS_DIR)) == len(sys.path) - 1
      or str(ot.PYLIBS_DIR) not in sys.path[:3])

_tt2 = ot.trang_thai("pylib-playwright")
check("đã cài -> trạng thái san_sang", _tt2["trang_thai"] == "san_sang")
check("đã cài -> GỠ ĐƯỢC (vì chính Javis cài)", _tt2["go_duoc"])
check("đã cài -> có khai đường dẫn cho người dùng nhìn", _tt2["duong_dan"] == str(ot.PYLIBS_DIR))


# ============================================================
# 4) Gỡ: chỉ đụng thứ Javis cài
# ============================================================

_r = ot.go("pylib-playwright")
check("gỡ được bản Javis cài", _r.get("ok"))
check("gỡ xong thì thư mục biến mất", not ot._da_cai_pylib())
check("gỡ lần hai -> từ chối nói được, không nổ", not ot.go("pylib-playwright").get("ok"))
check("gỡ thư viện KHÔNG đụng thư mục trình duyệt",
      not ot.BROWSERS_DIR.exists() or ot.BROWSERS_DIR.is_dir())

_src = (SERVER / "optional_tools.py").read_text(encoding="utf-8")
check("gỡ đi đúng thư mục theo công cụ, không gõ cứng một chỗ",
      "goc = PYLIBS_DIR if cong_cu ==" in _src)


# ============================================================
# 5) Engine Web phải NẠP thư viện tự cài trước khi thử import
# ============================================================

_wt = (SERVER / "web_transport.py").read_text(encoding="utf-8")
check("web_transport gọi nap_pylibs trước khi import playwright",
      _wt.index("nap_pylibs()") < _wt.index("import playwright  # noqa"))
check("câu báo thiếu thư viện chỉ sang trang Công cụ, không bắt gõ pip",
      "trang Công cụ" in _wt and "pip install playwright`" not in _wt)

check("routes/tools đã nhận id từ client nên không phải sửa gì",
      'd.get("id")' in (SERVER / "routes" / "tools.py").read_text(encoding="utf-8"))

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_cong_cu_thu_vien: tất cả pass")
