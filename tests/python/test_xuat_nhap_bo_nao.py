"""2026-11-09: a whole brain as one .zip file, out and back in, from the brain picker.

    python tests/run.py xuat_nhap_bo_nao      (KHÔNG mạng)

Owner: "có thể xuất bộ não đấy ra thành file và tải lên chỗ khác, icon xuất sửa xóa cũng ở bên cạnh luôn". The export
leaves private files out (raw chats, run logs, hub tokens, git), the upload always makes a NEW brain, refuses unsafe
names, and switches off what would run on its own (plugins, loops, pending reminders). The picker carries the buttons.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-xuatnhap-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import brain_export as bx  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. What stays out ----
for rel in ("memory/conversations/2026-11-09.md", ".grok/config.toml", ".agents/mcp_config.json", ".git/config",
            "Javis/learned/bot/x.private.json", "memory/agents/viet/runs/1.md", ".mcp.json", ".env", "Javis/loop-log/a.md",
            "keys/id_ed25519", "a.tmp"):
    check(f"không xuất: {rel}", bx.kept_out(rel))
for rel in ("wiki/a.md", "attachments/anh.png", "agents/viet.md", "skills/x/SKILL.md", "memory/MEMORY.md",
            "memory/agents/viet/MEMORY.md", "Javis/brain.json", ".agents/skills/x/SKILL.md"):
    check(f"có xuất: {rel}", not bx.kept_out(rel))

# ---- 2. Endpoints ----
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)
r = cl.post("/brains/new", data={"name": "Kho Hang"}).json()
check("tạo brain mẫu", r.get("ok"), r)
src = Path(r["path"])
cl.post("/brains/label", data={"brain": "path:" + str(src), "label": "Não Kho"})
files = {
    "wiki/hang.md": "# Hàng tồn", "attachments/anh.png": "PNG",
    "memory/conversations/2026-11-09.md": "chat thô", ".grok/config.toml": "Bearer bi-mat",
    "plugins/p1/plugin.yaml": "name: p1\nslug: p1\nenabled: true\n", "plugins/p1/plugin.py": "def register(ctx): pass\n",
    "Javis/loops/dem.md": "---\nname: dem\nenabled: true\nmode: full\n---\nĐếm hàng.\n",
    "Javis/reminders.json": json.dumps({"reminders": [{"id": "a", "status": "pending"}, {"id": "b", "status": "done"}]}),
}
for rel, txt in files.items():
    p = src / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")

r = cl.get("/brains/export", params={"brain": "path:" + str(src), "probe": 1}).json()
check("đo trước: số file và tên file zip", r.get("ok") and r["files"] > 0 and r["name"] == "Não Kho.zip", r)
r = cl.get("/brains/export", params={"brain": "path:" + str(src)})
check("xuất ra file zip", r.status_code == 200 and r.headers.get("content-type") == "application/zip", r.status_code)
zdata = r.content
names = zipfile.ZipFile(io.BytesIO(zdata)).namelist()
check("zip có ghi chú, ảnh và manifest", "Kho Hang/wiki/hang.md" in names and "Kho Hang/attachments/anh.png" in names
      and "Kho Hang/javis-brain.json" in names, names)
check("zip KHÔNG có chat thô và token", not any("conversations" in n or ".grok" in n for n in names), names)
r = cl.get("/brains/export", params={"brain": "path:" + tempfile.gettempdir(), "probe": 1})
check("thư mục ngoài BRAINS_DIR: không xuất", r.status_code == 404)

r = cl.post("/brains/import", files={"file": ("Não Kho.zip", zdata, "application/zip")}).json()
check("tải lên: tạo bộ não MỚI, không đè", r.get("ok") and r["name"] == "Kho Hang (2)" and Path(r["path"]).is_dir(), r)
check("giữ tên trong file, thêm (2) khi trùng", r.get("label") == "Não Kho (2)", r)
check("báo đã tắt 1 plugin, 1 vòng lặp, 1 nhắc việc", r.get("paused") == {"plugins": 1, "loops": 1, "reminders": 1}, r)
dst = Path(r["path"])
check("ghi chú về đủ", (dst / "wiki" / "hang.md").read_text(encoding="utf-8") == "# Hàng tồn")
check("plugin về ở trạng thái tắt", "enabled: false" in (dst / "plugins/p1/plugin.yaml").read_text(encoding="utf-8"))
check("vòng lặp về ở trạng thái tắt", "enabled: false" in (dst / "Javis/loops/dem.md").read_text(encoding="utf-8"))
rem = json.loads((dst / "Javis/reminders.json").read_text(encoding="utf-8"))["reminders"]
check("nhắc việc đang chờ thành tạm dừng, việc đã xong giữ nguyên", [x["status"] for x in rem] == ["paused", "done"], rem)
check("bộ não gốc không bị đụng", "enabled: true" in (src / "plugins/p1/plugin.yaml").read_text(encoding="utf-8"))
names = [b["name"] for b in cl.get("/brains").json()["brains"]]
check("bộ não mới hiện trong danh sách", "Kho Hang (2)" in names, names)
check("không còn thư mục tạm trong BRAINS_DIR", not any(n.startswith(".") for n in os.listdir(os.environ["BRAINS_DIR"])
                                                         if n.startswith(".javis-import-")))

r = cl.post("/brains/import", files={"file": ("x.zip", zdata, "application/zip")}, data={"label": "Tên riêng"}).json()
check("tải lên với tên tự đặt", r.get("ok") and r["label"] == "Tên riêng", r)

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr("../ngoai.md", "x")
    zf.writestr("/tuyet-doi.md", "x")
    zf.writestr("C:/win.md", "x")
    zf.writestr("goc/ok.md", "an toàn")
r = cl.post("/brains/import", files={"file": ("doc.zip", buf.getvalue(), "application/zip")}).json()
got = sorted(p.name for p in Path(r["path"]).rglob("*.md")) if r.get("ok") else []
check("zip có đường dẫn nguy hiểm: chỉ lấy file an toàn", r.get("ok") and r["files"] == 1 and "ok.md" in got
      and not any(n in got for n in ("ngoai.md", "tuyet-doi.md", "win.md")), r)
check("không ghi được ra ngoài", not (Path(os.environ["BRAINS_DIR"]).parent / "ngoai.md").exists())

r = cl.post("/brains/import", files={"file": ("x.zip", b"khong phai zip", "application/zip")})
check("không phải zip: báo lỗi 400", r.status_code == 400 and not r.json().get("ok"))

# ---- 3. Picker ----
bp = (ROOT / "dashboard" / "brain-picker.js").read_text(encoding="utf-8")
check("mỗi dòng có Xuất, Đổi tên, Xoá", all(f'actBtn("{a}"' in bp for a in ("export", "rename", "delete")))
check("cuối khung có Tạo, Tải lên, Thư mục ngoài", all(f'data-foot="{a}"' in bp for a in ("new", "import", "folder")))
check("xuất đo trước rồi mới tải", '"/brains/export?probe=1&"' in bp)
check("tải lên có tiến độ", "xhr.upload.onprogress" in bp and 'xhr.open("POST", "/brains/import")' in bp)
html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
check("thanh trên cùng không còn nút tạo, sửa, xoá rời",
      not any(f'id="{i}"' in html for i in ("newBrainBtn", "renameBrainBtn", "delBrainBtn")))
check("nút thư mục ngoài cũ chỉ còn ẩn (app.js mở trình chọn từ nó)", 'id="pickFolderBtn" hidden' in html)
for lang in ("vi", "en"):
    dd = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    need = [k for k in set(__import__("re").findall(r't\("(bpick\.[a-z_]+)"', bp)) if not dd.get(k)]
    check(f"{lang}: đủ chữ cho khung chọn não", not need, need)

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_xuat_nhap_bo_nao: all pass")
