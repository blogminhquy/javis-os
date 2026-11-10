"""2026-11-09: a whole brain as one .zip file, out and back in, from the brain picker.

    python tests/run.py xuat_nhap_bo_nao      (KHÔNG mạng)

Owner: "có thể xuất bộ não đấy ra thành file và tải lên chỗ khác, icon xuất sửa xóa cũng ở bên cạnh luôn", then "20.000
file ... file text 1gb sẽ được rất nhiều": no fixed size cap, the free disk decides; packing and unpacking run in the
background and the upload goes in pieces, so Cloudflare Tunnel's per-request limits never bite. The export
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

import time  # noqa: E402

bx.CHUNK = 4096   # small pieces, so the test sends several and can resume


def export(brain):
    r = cl.post("/brains/export/start", data={"brain": brain})
    if r.status_code != 200:
        return r, None
    jid = r.json()["id"]
    for _ in range(200):
        st = cl.get("/brains/export/status", params={"id": jid}).json()
        if st.get("status") in ("done", "error"):
            break
        time.sleep(0.05)
    return st, cl.get("/brains/export/file", params={"id": jid})


def upload(data, name="x.zip", label="", resume_test=False):
    r = cl.post("/brains/import/start", data={"size": len(data), "name": name}).json()
    if not r.get("ok"):
        return r
    uid, piece, at = r["id"], r["chunk"], 0
    if resume_test:   # a piece sent for the wrong place: the server says where it stands
        bad = cl.post("/brains/import/chunk", params={"id": uid, "offset": 5}, content=data[:10])
        check("mảnh sai chỗ: 409 kèm vị trí đúng", bad.status_code == 409 and bad.json().get("received") == 0, bad.text)
    while at < len(data):
        c = cl.post("/brains/import/chunk", params={"id": uid, "offset": at}, content=data[at:at + piece]).json()
        at = c["received"]
    f = cl.post("/brains/import/finish", data={"id": uid, "label": label}).json()
    if not f.get("ok"):
        return f
    for _ in range(200):
        st = cl.get("/brains/import/status", params={"id": uid}).json()
        if st.get("status") in ("done", "error"):
            break
        time.sleep(0.05)
    return dict(st.get("result") or {}, ok=st.get("status") == "done", error=st.get("error"))


st, r = export("path:" + str(src))
check("xuất chạy nền: xong, đếm đủ file", st.get("status") == "done" and st["total"] > 0 and st["done"] == st["total"], st)
check("xuất ra file zip, tên theo tên bộ não", r.status_code == 200 and r.headers.get("content-type") == "application/zip"
      and "N%C3%A3o%20Kho.zip" in r.headers.get("content-disposition", ""), r.headers)
zdata = r.content
names = zipfile.ZipFile(io.BytesIO(zdata)).namelist()
check("zip có ghi chú, ảnh và manifest", "Kho Hang/wiki/hang.md" in names and "Kho Hang/attachments/anh.png" in names
      and "Kho Hang/javis-brain.json" in names, names)
check("zip KHÔNG có chat thô và token", not any("conversations" in n or ".grok" in n for n in names), names)
r = cl.post("/brains/export/start", data={"brain": "path:" + tempfile.gettempdir()})
check("thư mục ngoài BRAINS_DIR: không xuất", r.status_code == 404)
check("mã việc lạ: 404", cl.get("/brains/export/file", params={"id": "../../etc"}).status_code == 404)

check("đủ nhiều mảnh để thử gửi từng phần", len(zdata) > 2 * bx.CHUNK, len(zdata))
r = upload(zdata, "Não Kho.zip", resume_test=True)
check("tải lên từng phần: tạo bộ não MỚI, không đè", r.get("ok") and r["name"] == "Kho Hang (2)" and Path(r["path"]).is_dir(), r)
check("giữ tên trong file, thêm (2) khi trùng", r.get("label") == "Não Kho (2)", r)
check("báo đã tắt 1 plugin, 1 vòng lặp, 1 nhắc việc", r.get("paused") == {"plugins": 1, "loops": 1, "reminders": 1}, r)
dst = Path(r["path"])
check("ghi chú về đủ", (dst / "wiki" / "hang.md").read_text(encoding="utf-8") == "# Hàng tồn")
check("plugin về ở trạng thái tắt", "enabled: false" in (dst / "plugins/p1/plugin.yaml").read_text(encoding="utf-8"))
check("vòng lặp về ở trạng thái tắt", "enabled: false" in (dst / "Javis/loops/dem.md").read_text(encoding="utf-8"))
rem = json.loads((dst / "Javis/reminders.json").read_text(encoding="utf-8"))["reminders"]
check("nhắc việc đang chờ thành tạm dừng, việc đã xong giữ nguyên", [x["status"] for x in rem] == ["paused", "done"], rem)
check("bộ não gốc không bị đụng", "enabled: true" in (src / "plugins/p1/plugin.yaml").read_text(encoding="utf-8"))
check("dựng sẵn cấu trúc chuẩn cho bộ não mới", (dst / "Javis" / "README.md").is_file())
names = [b["name"] for b in cl.get("/brains").json()["brains"]]
check("bộ não mới hiện trong danh sách", "Kho Hang (2)" in names, names)
work = Path(_STATE) / "brain-import"
check("dọn sạch mảnh tải lên và thư mục tạm", not list(work.glob("*.part")) and not list(work.glob(".javis-import-*")),
      list(work.iterdir()))

r = upload(zdata, label="Tên riêng")
check("tải lên với tên tự đặt", r.get("ok") and r["label"] == "Tên riêng", r)

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr("../ngoai.md", "x")
    zf.writestr("/tuyet-doi.md", "x")
    zf.writestr("C:/win.md", "x")
    zf.writestr("goc/ok.md", "an toàn")
r = upload(buf.getvalue(), "doc.zip")
got = sorted(p.name for p in Path(r["path"]).rglob("*.md")) if r.get("ok") else []
check("zip có đường dẫn nguy hiểm: chỉ lấy file an toàn", r.get("ok") and r["files"] == 1 and "ok.md" in got
      and not any(n in got for n in ("ngoai.md", "tuyet-doi.md", "win.md")), r)
check("không ghi được ra ngoài", not (Path(os.environ["BRAINS_DIR"]).parent / "ngoai.md").exists())

r = upload(b"khong phai zip")
check("không phải zip: báo lỗi rõ", not r.get("ok") and "zip" in (r.get("error") or ""), r)

# ---- No fixed size cap: the free disk decides ----
_real_free = bx.free_bytes
bx.free_bytes = lambda path: bx.KEEP_FREE + 100
r = cl.post("/brains/import/start", data={"size": 10_000, "name": "to.zip"})
check("không đủ chỗ trống: 507 kèm số cần và số còn", r.status_code == 507 and "GB" in r.json().get("error", ""), r.text)
st, _f = export("path:" + str(src))
check("xuất khi không đủ chỗ: báo lỗi, không nén dở", st.get("status") == "error" and "GB" in st.get("error", ""), st)
bx.free_bytes = _real_free
check("trần số file là 1 triệu, không còn trần 20.000", bx.MAX_FILES >= 1_000_000)

# ---- 3. Picker ----
bp = (ROOT / "dashboard" / "brain-picker.js").read_text(encoding="utf-8")
check("mỗi dòng có Xuất, Đổi tên, Xoá", all(f'actBtn("{a}"' in bp for a in ("export", "rename", "delete")))
check("cuối khung có Tạo, Tải lên, Thư mục ngoài", all(f'data-foot="{a}"' in bp for a in ("new", "import", "folder")))
check("xuất chạy nền rồi mới tải", '"/brains/export/start"' in bp and '"/brains/export/file?id="' in bp)
check("tải lên từng phần, có tiến độ, gửi lại từ chỗ máy chủ báo",
      '"/brains/import/chunk?id="' in bp and "xhr.upload.onprogress" in bp and "r.d.received" in bp)
html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
check("thanh trên cùng không còn nút tạo, sửa, xoá rời",
      not any(f'id="{i}"' in html for i in ("newBrainBtn", "renameBrainBtn", "delBrainBtn")))
check("nút thư mục ngoài cũ chỉ còn ẩn (app.js mở trình chọn từ nó)", 'id="pickFolderBtn" hidden' in html)
for lang in ("vi", "en"):
    dd = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    need = [k for k in set(__import__("re").findall(r't\("(bpick\.[a-z_]+)"', bp)) if not dd.get(k)]
    check(f"{lang}: đủ chữ cho khung chọn não", not need, need)

# ---- 2026-11-10: a brain file from somebody else arrives with nothing armed, however it is spelled ----
import fastyaml  # noqa: E402

_LOOPS = {
    "exact": "---\nname: a\nenabled: true\nmode: full\n---\nx\n",
    "comment": "---\nname: a\nenabled: true # on\nmode: full\n---\nx\n",
    "one": "---\nname: a\nenabled: 1\nmode: full\n---\nx\n",
    "quoted-value": "---\nname: a\nenabled: \"true\"\nmode: full\n---\nx\n",
    "quoted-key": "---\nname: a\n\"enabled\": true\nmode: full\n---\nx\n",
    "upper": "---\nname: a\nEnabled: True\nenabled: yes\nmode: full\n---\nx\n",
    "flow": "---\n{name: a, enabled: true, mode: full}\n---\nx\n",
    "off-already": "---\nname: a\nenabled: false\nmode: full\n---\nx\n",
}
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr("goc/wiki/a.md", "note")
    for k, v in _LOOPS.items():
        zf.writestr(f"goc/Javis/loops/{k}.md", v)
    zf.writestr("goc/plugins/p2/plugin.yaml", "name: p2\nslug: p2\nenabled: true\n")
    zf.writestr("goc/plugins/p2/plugin.py", "def register(ctx): pass\n")
    zf.writestr("goc/.claude/settings.json", '{"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "id"}]}]}}')
    zf.writestr("goc/.claude/settings.local.json", "{}")
    zf.writestr("goc/.claude/hooks/run.sh", "id")
    zf.writestr("goc/.claude/skills/s1/SKILL.md", "---\nname: s1\n---\nhow to")
    zf.writestr("goc/.codex/config.toml", "x = 1")
    zf.writestr("goc/.agents/hooks.json", "{}")
    zf.writestr("goc/.agents/skills/s2/SKILL.md", "---\nname: s2\n---\nhow to")
    zf.writestr("goc/.gemini/settings.json", "{}")
    zf.writestr("goc/sub/.grok/config.toml", "x = 1")
r = bx.import_zip(io.BytesIO(buf.getvalue()), Path(os.environ["BRAINS_DIR"]), filename="la.zip",
                  work_dir=Path(_STATE) / "brain-import")
dst2 = Path(r["path"])
still_on = []
for f in sorted((dst2 / "Javis" / "loops").iterdir()):
    if f.suffix != ".md":
        continue
    m = __import__("self_improve")._FM_RE.match(f.read_text(encoding="utf-8"))
    fm = fastyaml.safe_load(m.group(1)) if m else None
    if isinstance(fm, dict) and bool(fm.get("enabled", False)):
        still_on.append(f.name)
check("no imported loop is on when read the way the loop loader reads it", not still_on, still_on)
check("seven of the eight loops were on and are reported as switched off", r["paused"]["loops"] == 7, r["paused"])
check("a loop that could not be edited safely is set aside, not deleted",
      (dst2 / "Javis/loops/flow.md.off").is_file() and not (dst2 / "Javis/loops/flow.md").exists())
check("a loop already off is left as it was",
      (dst2 / "Javis/loops/off-already.md").read_text(encoding="utf-8") == _LOOPS["off-already"])
check("the body and the other keys of a loop survive",
      "mode: full" in (dst2 / "Javis/loops/comment.md").read_text(encoding="utf-8")
      and (dst2 / "Javis/loops/comment.md").read_text(encoding="utf-8").endswith("---\nx\n"))
check("the plugin comes in switched off", "enabled: false" in (dst2 / "plugins/p2/plugin.yaml").read_text(encoding="utf-8"))
check("Claude Code settings and hooks do not come in",
      not (dst2 / ".claude/settings.json").exists() and not (dst2 / ".claude/settings.local.json").exists()
      and not (dst2 / ".claude/hooks").exists())
check("skills kept under .claude do come in", (dst2 / ".claude/skills/s1/SKILL.md").is_file())
check("other engines' config folders do not come in",
      not any((dst2 / d).exists() for d in (".codex", ".agents/hooks.json", ".gemini", "sub/.grok")))
check("skills kept under .agents do come in", (dst2 / ".agents/skills/s2/SKILL.md").is_file())
check("import_kept_out: spellings of the same folders", bx.import_kept_out(".Codex/config.toml")
      and bx.import_kept_out(".CLAUDE/Settings.json") and not bx.import_kept_out("wiki/.claude-notes.md")
      and not bx.import_kept_out(".claude/skills/a/SKILL.md") and not bx.import_kept_out(".agents/skills/a/SKILL.md")
      and bx.import_kept_out(".agents/skills") and bx.import_kept_out(".claude/hooks/x.sh"))

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_xuat_nhap_bo_nao: all pass")
