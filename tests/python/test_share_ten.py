"""Tên của link chia sẻ (0.65.30).

    python tests/run.py share_ten

Chủ dự án chọn 01/10: link mới tự lấy tên theo TIÊU ĐỀ file, sửa tên được ngay ở trang Chia sẻ,
và ô tìm kiếm tìm được theo tên. Trước đó trang Chia sẻ chỉ hiện tên file, mà mỗi app nhỏ nằm
trong thư mục riêng nên cả loạt link cùng tên "index.html", không phân biệt được.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-share-ten-")
_BRAINS = tempfile.mkdtemp(prefix="javis-share-ten-brains-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["BRAINS_DIR"] = _BRAINS

BRAIN = os.path.join(_BRAINS, "brain")
for d in ("apps/doanh-thu", "apps/lich", "notes"):
    os.makedirs(os.path.join(BRAIN, d), exist_ok=True)


def ghi(rel, text):
    with open(os.path.join(BRAIN, rel), "w", encoding="utf-8") as f:
        f.write(text)


ghi("apps/doanh-thu/index.html", "<!doctype html><html><head><meta charset=utf-8>\n"
    "<TITLE>  Bảng doanh thu &amp; chi phí\n tháng 9 </TITLE></head><body>x</body></html>")
ghi("apps/lich/index.html", "<!doctype html><h1>Không có thẻ title</h1>")
ghi("notes/ke-hoach.md", "---\ntitle: \"Kế hoạch quý 4\"\ntags: [a]\n---\n# Tiêu đề phụ\n\nchữ")
ghi("notes/ghi-chu.md", "\n\n# Ghi chú họp sáng\n\nNội dung")
ghi("notes/thuan.md", "chỉ có chữ, không có tiêu đề")
ghi("notes/so-lieu.txt", "a,b,c")

import share_render  # noqa: E402
import share_store  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

cl = TestClient(main.app, base_url="http://127.0.0.1")
_loi = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _loi.append(name)


def P(rel):
    return Path(BRAIN) / rel


# ---- 1. Lấy tiêu đề từ file ----
check(".html: lấy <title>, gỡ thực thể và gộp khoảng trắng",
      share_render.tieu_de_file(P("apps/doanh-thu/index.html")) == "Bảng doanh thu & chi phí tháng 9",
      share_render.tieu_de_file(P("apps/doanh-thu/index.html")))
check(".html không có <title>: rỗng (để rơi về tên thư mục/file)",
      share_render.tieu_de_file(P("apps/lich/index.html")) == "")
check(".md: title trong frontmatter thắng tiêu đề #",
      share_render.tieu_de_file(P("notes/ke-hoach.md")) == "Kế hoạch quý 4")
check(".md: dòng # đầu tiên", share_render.tieu_de_file(P("notes/ghi-chu.md")) == "Ghi chú họp sáng")
check(".md không tiêu đề: rỗng", share_render.tieu_de_file(P("notes/thuan.md")) == "")
check("đuôi khác: rỗng", share_render.tieu_de_file(P("notes/so-lieu.txt")) == "")
check("file không tồn tại: rỗng, không ném lỗi", share_render.tieu_de_file(P("khong-co.md")) == "")
ghi("notes/dai.md", "# " + "x" * 500)
check("tiêu đề quá dài bị cắt còn 120 ký tự", len(share_render.tieu_de_file(P("notes/dai.md"))) == 120)
check("tên dự phòng: index.html lấy tên thư mục chứa nó",
      share_render.ten_du_phong("apps/lich/index.html") == "lich"
      and share_render.ten_du_phong("notes/thuan.md") == "thuan.md")

# ---- 2. Kho: đổi tên ----
b = share_store.tao(BRAIN, "notes/thuan.md", "Tên A")
check("tạo kèm tên thì giữ tên", b["nhan"] == "Tên A")
r = share_store.doi_ten(b["token"], "  Tên   mới  ")
check("đổi tên: gọn khoảng trắng, lưu lại", r and r["nhan"] == "Tên mới"
      and share_store.doc(b["token"])["nhan"] == "Tên mới")
check("đổi tên quá dài bị cắt còn 120 ký tự", len(share_store.doi_ten(b["token"], "y" * 300)["nhan"]) == 120)
check("tên rỗng: xoá tên tay, về tên tự động", share_store.doi_ten(b["token"], "")["nhan"] == "")
check("token lạ: None", share_store.doi_ten("khong-co", "x") is None)

# ---- 3. Route ----
t1 = cl.post("/share/create", json={"brain": BRAIN, "path": "apps/doanh-thu/index.html"}).json()
check("tạo link .html: tên tự lấy theo <title>",
      share_store.doc(t1["token"])["nhan"] == "Bảng doanh thu & chi phí tháng 9")
t2 = cl.post("/share/create", json={"brain": BRAIN, "path": "apps/lich/index.html"}).json()
check("không có tiêu đề: tên là thư mục chứa index.html", share_store.doc(t2["token"])["nhan"] == "lich")
t3 = cl.post("/share/create", json={"brain": BRAIN, "path": "notes/ghi-chu.md", "nhan": "Tên tự chọn"}).json()
check("client gửi tên thì dùng tên đó", share_store.doc(t3["token"])["nhan"] == "Tên tự chọn")

# Link cũ (trước 0.65.30) không có tên: danh sách tự tính, không ghi đè kho.
cu = share_store.tao(BRAIN, "notes/ke-hoach.md", "")
ds = {x["token"]: x for x in cl.get("/share/list").json()["items"]}
check("danh sách trả `ten` cho mọi link",
      ds[t1["token"]]["ten"] == "Bảng doanh thu & chi phí tháng 9" and ds[t3["token"]]["ten"] == "Tên tự chọn")
check("link cũ không tên: danh sách tự lấy tiêu đề file", ds[cu["token"]]["ten"] == "Kế hoạch quý 4"
      and share_store.doc(cu["token"])["nhan"] == "")

rr = cl.post("/share/rename", json={"token": t1["token"], "nhan": "Báo cáo cho sếp"}).json()
check("POST /share/rename đổi tên và trả tên mới", rr.get("ok") is True and rr.get("ten") == "Báo cáo cho sếp")
rr = cl.post("/share/rename", json={"token": t1["token"], "nhan": ""}).json()
check("đổi về rỗng thì tên quay lại tiêu đề file", rr.get("ten") == "Bảng doanh thu & chi phí tháng 9")
check("đổi tên token lạ: ok=false", cl.post("/share/rename", json={"token": "zz", "nhan": "x"}).json().get("ok") is False)

print()
if _loi:
    print(f"ĐỎ {len(_loi)} mục: " + "; ".join(_loi[:6]))
    sys.exit(1)
print("Tất cả xanh.")
