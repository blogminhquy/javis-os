"""Trợ lý tên có dấu ("bống-work.md") mở Cài đặt, sửa, xoá, xuất được; trợ lý mới đặt tên không dấu (0.88.1).

    python tests/run.py agent_slug_co_dau      (KHÔNG mạng, brain tạm)

Chủ repo báo 09/10/2026 kèm ảnh: trang Cộng sự, tab Cài đặt của trợ lý "Bống Work" luôn báo "Không tải
được trợ lý này" dù trợ lý vẫn chạy. File của nó là `agents/bống-work.md`: `_slugify` của POST /agents
giữ nguyên chữ Việt, còn GET /agents/get (và xoá, xuất) kiểm slug bằng `valid_slug` chỉ nhận A-Z0-9,
nên mọi trợ lý đặt tên có dấu đều hỏng ở mấy chỗ đó. Bộ mẫu Studio còn dính một lỗi cùng gốc: quy
trình mẫu gọi bước kiểm chứng `kiem-chung-vien` nhưng file tạo ra là `kiểm-chứng-viên.md`.

Điều được ghim:
  1. Trợ lý tên có dấu đọc được qua GET /agents/get, cả khi tên file trên đĩa ở dạng tách dấu (NFD,
     macOS) còn slug từ trình duyệt ở dạng dựng sẵn (NFC).
  2. Xoá và xuất được trợ lý tên có dấu.
  3. Vẫn chặn slug thoát thư mục: `../x`, `a/b`, `..\\x`, rỗng.
  4. Trợ lý và quy trình MỚI đặt tên file không dấu; bộ mẫu Studio khớp tên quy trình mẫu gọi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import pathlib
import sys
import tempfile
import unicodedata
from urllib.parse import quote

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-agslug-")
import main  # noqa: E402
import skill_router  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{detail!r}]"))
    if not cond:
        _fails.append(name)


BRAIN = pathlib.Path(tempfile.mkdtemp(prefix="javis-brain-agslug-"))
AG = BRAIN / "agents"
AG.mkdir(parents=True)


def tao(slug, name):
    (AG / f"{slug}.md").write_text(f"---\ntype: agent\nname: {name}\nrole: vai\n---\nPrompt của {name}.",
                                   encoding="utf-8")


tao("bống-work", "Bống Work")
tao(unicodedata.normalize("NFD", "người-giải-thích"), "Người giải thích")
c = TestClient(main.app, base_url="http://127.0.0.1:8080")
q = quote(str(BRAIN), safe="")

# ---- 1. Đọc ----
r = c.get(f"/agents/get?slug={quote('bống-work')}&brain={q}")
check("GET /agents/get đọc được trợ lý tên có dấu",
      r.status_code == 200 and r.json().get("prompt") == "Prompt của Bống Work.", (r.status_code, r.text[:120]))
r = c.get(f"/agents/get?slug={quote(unicodedata.normalize('NFC', 'người-giải-thích'))}&brain={q}")
check("file tên dạng tách dấu (NFD) vẫn tìm ra bằng slug dạng dựng sẵn (NFC)",
      r.status_code == 200 and "Người giải thích" in r.json().get("prompt", ""), (r.status_code, r.text[:120]))

# ---- 2. Xuất, xoá ----
r = c.get(f"/export?kind=agent&slug={quote('bống-work')}&brain={q}&deps=0")
check("xuất được trợ lý tên có dấu", r.status_code == 200 and r.content[:2] == b"PK", (r.status_code, r.text[:120]))
r = c.post("/agents/delete", data={"slug": "bống-work", "brain": str(BRAIN)})
check("xoá được trợ lý tên có dấu", r.status_code == 200 and not (AG / "bống-work.md").exists(), r.text[:120])

# ---- 3. Vẫn chặn thoát thư mục ----
for xau in ("../x", "a/b", "..\\x", "a\\b", "", "-x", ".hidden", "x:y"):
    check(f"chặn slug {xau!r}", not skill_router.valid_file_slug(xau))
check("slug skill vẫn chỉ ASCII như cũ", not skill_router.valid_slug("bống-work") and skill_router.valid_slug("bong-work"))

# ---- 4. Tạo mới: tên file không dấu ----
r = c.post("/agents", data={"name": "Đội Bống Work", "role": "vai", "prompt": "p", "brain": str(BRAIN)})
check("trợ lý mới đặt tên file không dấu", r.status_code == 200 and (AG / "doi-bong-work.md").is_file(),
      (r.status_code, sorted(p.name for p in AG.iterdir())))
r = c.post("/workflows", data={"name": "Quy trình Bống", "steps": "[]", "brain": str(BRAIN)})
check("quy trình mới đặt tên file không dấu", r.status_code == 200 and (BRAIN / "workflows" / "quy-trinh-bong.md").is_file(),
      (r.status_code, r.text[:120]))

SEED = pathlib.Path(tempfile.mkdtemp(prefix="javis-brain-seed-"))
r = c.post("/studio/seed", data={"brain": str(SEED)})
check("bộ mẫu: trợ lý kiểm chứng khớp tên quy trình mẫu gọi (kiem-chung-vien)",
      (SEED / "agents" / "kiem-chung-vien.md").is_file(), sorted(p.name for p in (SEED / "agents").glob("*.md")))

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
