"""Hộp đen lỗi giao diện phía máy chủ (0.416.0): nhận, gom nhóm, giới hạn, xoá.

    python tests/run.py loi_may_khach      (KHÔNG mạng)

Lỗi JS của trình duyệt khách trước đây chỉ biết được qua ảnh chụp màn hình (khách báo 30/10/2026). dashboard/loi-may-khach.js
gửi về POST /client-errors, server/loi_may_khach.py giữ theo nhóm, trang Sức khoẻ đọc GET /client-errors.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="javis-loi-")
os.environ["JAVIS_STATE_DIR"] = _tmp
sys.path.insert(0, str(SERVER))
import config as cfgmod  # noqa: E402
cfgmod.STATE_DIR = __import__("pathlib").Path(_tmp)
import loi_may_khach as L  # noqa: E402

_fails = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        _fails.append(ten)


UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)"
loi = {"msg": "x is not defined", "src": "/static/app.js", "dong": 42, "cot": 7, "loai": "error", "stack": "at f", "trang": "chat"}

check("một lỗi được ghi", L.ghi({"version": "0.416.0", "errors": [loi]}, UA) == 1)
L.ghi({"version": "0.416.0", "errors": [loi, dict(loi)]}, UA)
ds = L.danh_sach()
check("cùng thông điệp, file, dòng thì gom một nhóm và đếm số lần", len(ds) == 1 and ds[0]["count"] == 3, ds)
check("nhóm mang phiên bản, máy, trang", ds[0]["version"] == "0.416.0" and "iPhone" in ds[0]["ua"] and ds[0]["trang"] == "chat")
L.ghi({"errors": [dict(loi, dong=43)]})
check("khác dòng là nhóm khác, mới nhất đứng đầu", len(L.danh_sach()) == 2 and L.danh_sach()[0]["dong"] == 43)

check("dữ liệu lạ không làm hỏng gì", L.ghi(None) == 0 and L.ghi({"errors": "x"}) == 0 and L.ghi({"errors": [1, {"msg": ""}]}) == 0)
nhieu = [{"msg": f"loi {i}", "src": "/static/a.js", "dong": i} for i in range(50)]
check("một lượt gửi tối đa 20 lỗi", L.ghi({"errors": nhieu}) == L.TOI_DA_MOI_LUOT == 20)
dai = L.ghi({"errors": [{"msg": "a" * 5000, "stack": "s" * 9000}]}) and [g for g in L.danh_sach() if g["msg"].startswith("aaa")][0]
check("thông điệp và ngăn xếp bị cắt ngắn", len(dai["msg"]) == 500 and len(dai["stack"]) == 2000)
for k in range(8):
    L.ghi({"errors": [{"msg": f"k{k}-{i}", "dong": i} for i in range(20)]})
check("giữ tối đa 100 nhóm", len(L.danh_sach()) == L.TOI_DA_NHOM == 100)
L.xoa_het()
check("xoá hết thì danh sách rỗng", L.danh_sach() == [])

MAIN = (SERVER / "main.py").read_text(encoding="utf-8")
check("có POST /client-errors, GET /client-errors, POST /client-errors/clear",
      '@app.post("/client-errors")' in MAIN and '@app.get("/client-errors")' in MAIN and '@app.post("/client-errors/clear")' in MAIN)
check("ghi file chạy ở luồng phụ, không chặn vòng sự kiện", "asyncio.to_thread(loi_may_khach.ghi" in MAIN)
check("file hộp đen nằm trong .gitignore (STATE_DIR mặc định là server/)",
      "server/client_errors.json" in (ROOT / ".gitignore").read_text(encoding="utf-8"))

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + "; ".join(_fails[:4]))
    raise SystemExit(1)
print("Tất cả xanh.")
