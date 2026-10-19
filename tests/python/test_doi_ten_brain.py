"""0.219.0: đổi tên bộ não mà không gãy liên kết.

    python tests/run.py doi_ten_brain      (KHÔNG mạng)

Nhóm chat của chủ (2026-10-19): "cái brain đó ko đổi tên đc ạ" / "sao lại fix cứng thế". Javis nhận diện một bộ não bằng
THƯ MỤC ("brain" = Brain Default, còn lại `path:<thư mục>`), và địa chỉ đó nằm khắp nơi: trình duyệt, bot, nhắc việc,
vòng lặp, việc nền, sao lưu git, link `/brains/<thư mục>/...` trong note. Đổi tên thư mục là cắt hết. Nên đổi tên chỉ đổi
TÊN HIỂN THỊ, lưu trong chính bộ não (`Javis/brain.json`), thư mục giữ nguyên.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-doiten-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import brain_label as bl  # noqa: E402
import git_brain  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. Module ----
d = Path(tempfile.mkdtemp(prefix="brain-")) / "Brain Default"
d.mkdir()
check("chưa đặt tên: hiện tên thư mục", bl.display(d) == "Brain Default" and bl.read(d) == "")
check("đặt tên: trả tên mới", bl.write(d, "  Gsmsuppliers   Kho  ") == "Gsmsuppliers Kho")
check("tên nằm TRONG brain, ở Javis/brain.json", (d / "Javis" / "brain.json").is_file())
check("đọc lại đúng tên", bl.display(d) == "Gsmsuppliers Kho")
check("thư mục không đổi", d.is_dir() and d.name == "Brain Default")
check("file tên được sao lưu git như chữ", git_brain.la_file_chu("Brain Default/Javis/brain.json"))
check("tên quá dài bị cắt, xuống dòng bị gộp", bl.clean("a\nb" + "x" * 100) == ("a b" + "x" * 100)[:60])
check("để trống: về tên thư mục và dọn file", bl.write(d, "") == "Brain Default" and not (d / "Javis" / "brain.json").exists())
(d / "Javis").mkdir(exist_ok=True)
(d / "Javis" / "brain.json").write_text('{"khac": 1}', encoding="utf-8")
bl.write(d, "Tên mới")
check("giữ các khoá khác trong file", '"khac": 1' in (d / "Javis" / "brain.json").read_text(encoding="utf-8"))
(d / "Javis" / "brain.json").write_text("hỏng{", encoding="utf-8")
check("file hỏng: không vỡ, dùng tên thư mục", bl.display(d) == "Brain Default")

# ---- 2. Endpoint ----
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)
r = cl.get("/brains").json()
mac_dinh = [b for b in r["brains"] if b["is_default"]][0]
check("danh sách brain có label (mặc định = tên thư mục)", mac_dinh["label"] == mac_dinh["name"] == "Brain Default", mac_dinh)

r = cl.post("/brains/label", data={"brain": "brain", "label": "Kho Gsmsuppliers"}).json()
check("đổi tên được Brain mặc định", r.get("ok") and r["label"] == "Kho Gsmsuppliers" and r["folder"] == "Brain Default", r)
b = [x for x in cl.get("/brains").json()["brains"] if x["is_default"]][0]
check("danh sách hiện tên mới, thư mục và đường dẫn giữ nguyên",
      b["label"] == "Kho Gsmsuppliers" and b["name"] == "Brain Default" and b["path"].endswith("Brain Default"), b)
check("brain mặc định vẫn là thư mục cũ", Path(main._brain_root("brain")).name == "Brain Default")

v = cl.get("/viec/all").json()
ten_viec = [x.get("name") for x in (v.get("brains") or []) if x.get("is_default")]
check("trang Việc hiện tên mới của brain", ten_viec == ["Kho Gsmsuppliers"], (ten_viec, list(v)[:6]))
import mcp_hub  # noqa: E402
check("ghi chú brain trong kết quả tool dùng tên mới",
      mcp_hub._ten_hien_brain(main._brain_root("brain")) == "Kho Gsmsuppliers")
src = (SERVER / "main.py").read_text(encoding="utf-8")
check("Telegram /brain khớp cả tên mới lẫn tên thư mục",
      'return [x.lower() for x in (b.get("label") or "", b["name"]) if x]' in src)
check("không còn chỗ hiện tên brain bằng Path(_brain_root(...)).name",
      "Path(_brain_root(brain)).name" not in src and "Path(_brain_root(sess[\"brain\"])).name" not in src)

cl.post("/brains/new", data={"name": "Marketing"})
r = cl.post("/brains/label", data={"brain": "Marketing", "label": "kho gsmsuppliers"})
check("trùng tên một brain khác (không phân biệt hoa thường): từ chối", r.status_code == 409, r.text)
p_mkt = str(Path(os.environ["BRAINS_DIR"]) / "Marketing")
r = cl.post("/brains/label", data={"brain": "path:" + p_mkt, "label": "Nhóm MKT"}).json()
check("đổi tên brain thường bằng địa chỉ path:", r.get("ok") and r["label"] == "Nhóm MKT", r)
check("thư mục brain thường không đổi", Path(p_mkt).is_dir() and not (Path(p_mkt).parent / "Nhóm MKT").exists())
r = cl.post("/brains/label", data={"brain": "path:" + tempfile.gettempdir(), "label": "x"})
check("thư mục ngoài BRAINS_DIR: không cho đặt tên", r.status_code == 404)
r = cl.post("/brains/label", data={"brain": "Marketing", "label": ""}).json()
check("để trống: về tên thư mục", r.get("ok") and r["label"] == "Marketing", r)
r = cl.post("/brains/delete", data={"name": "Marketing", "confirm": "Marketing"}).json()
check("xoá vẫn theo tên THƯ MỤC như cũ", r.get("ok"), r)

# ---- 3. Giao diện ----
js = (ROOT / "dashboard" / "brains-ui.js").read_text(encoding="utf-8")
check("ô chọn brain hiện label", "(b.label || b.name) + n" in js)
lenh = (ROOT / "dashboard" / "chat-lenh.js").read_text(encoding="utf-8")
check("lệnh /brain trong chat nhận cả tên thư mục cũ",
      "if (!k.hit && !k.nhieu.length) k = khopTen(brains, arg, function (b) { return b.name; });" in lenh)
cs = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("các ô chọn brain ở Cài đặt và trang Việc hiện label",
      cs.count("name: b.label || b.name, path: b.path") == 3)
check("nút đổi tên gọi đúng endpoint với địa chỉ brain đang chọn",
      'fetch("/brains/label"' in js and 'fd.append("brain", sel.value)' in js)
html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
check("có nút Đổi tên cạnh nút tạo và xoá brain", 'id="renameBrainBtn"' in html)
import json  # noqa: E402

for lang in ("vi", "en"):
    dd = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    check(f"{lang}: đủ chữ", all(dd.get(k) for k in ("top.brain_rename", "brains.rename_prompt", "brains.rename_failed",
                                                      "brains.rename_net_err")))

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_doi_ten_brain: all pass")
