"""Khung Project: hướng dẫn + tài liệu + link gắn vào một nhóm hội thoại.

    python tests/run.py project_khung      (KHÔNG mạng)

Trước đợt này `projects` chỉ là CÁI NHÃN gom hội thoại cho đỡ rối - không đổi hành vi Javis
một chút nào. Đợt 1 dựng phần kho + API để nó mang được nội dung: hướng dẫn riêng, danh sách
tài liệu trong brain, danh sách link.

Hai quyết định đáng canh, vì cả hai đều có cách làm sai trông hợp lý hơn:

1. `project_files` KHÔNG có cột `brain`. Spec ban đầu có. Nhưng project đã thuộc đúng một
   brain (`projects.brain`), và đường dẫn file chỉ có nghĩa trong brain đó. Lưu brain lần nữa
   ở đây là mở cửa cho một project trỏ sang file của brain khác - phá đúng cái rào `_safe_path`
   đang giữ, mà phá bằng DỮ LIỆU chứ không bằng lỗi code, nên không rào nào bắt được. Brain
   luôn lấy từ project.

2. Xoá project thì hội thoại chỉ bị GỠ NHÃN, còn file/link thì XOÁ HẲN. Không phải bất nhất:
   hội thoại có đời sống riêng ngoài project, còn tài liệu-của-project thì không có nghĩa gì
   khi project không còn - để lại là rác mồ côi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-proj-"))

import sessions  # noqa: E402

_fails = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten
          + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        _fails.append(ten)


st = sessions.SessionStore(os.path.join(tempfile.mkdtemp(prefix="javis-proj-db-"), "s.db"))

# ============================================================
# 1. Hướng dẫn: lưu, sửa, gỡ, và CẮT NGAY LÚC LƯU
# ============================================================
pid = st.create_project("Mộc Việt", brain="brain")
check("project mới chưa có hướng dẫn", not (st.get_project(pid) or {}).get("instructions"))

st.update_project(pid, instructions="Tông xanh lá. Tránh xanh dương.")
check("lưu được hướng dẫn",
      st.get_project(pid)["instructions"] == "Tông xanh lá. Tránh xanh dương.")

st.update_project(pid, name="Mộc Việt 2")
check("đổi tên KHÔNG xoá mất hướng dẫn (None = không đụng tới)",
      st.get_project(pid)["instructions"] == "Tông xanh lá. Tránh xanh dương.")

st.update_project(pid, instructions="")
check('truyền "" là GỠ hướng dẫn', st.get_project(pid)["instructions"] == "")

# Cắt ở tầng KHO chứ không chỉ lúc dựng prompt: chặn ở prompt thôi thì kho vẫn phình theo mỗi
# lần gõ, và người dùng thấy chữ mình lưu được nhưng Javis lặng lẽ chỉ đọc một phần.
st.update_project(pid, instructions="x" * (sessions.PROJECT_INSTRUCTIONS_MAX + 500))
check(f"hướng dẫn bị cắt về trần {sessions.PROJECT_INSTRUCTIONS_MAX} ngay lúc lưu",
      len(st.get_project(pid)["instructions"]) == sessions.PROJECT_INSTRUCTIONS_MAX,
      len(st.get_project(pid)["instructions"]))
st.update_project(pid, instructions="Tông xanh lá.")

# ============================================================
# 2. Tài liệu & link
# ============================================================
f1 = st.add_project_file(pid, "05 - Projects/bang-gia.md")
check("thêm file, tên suy từ đường dẫn khi không truyền",
      st.get_project_full(pid)["files"][0]["name"] == "bang-gia.md")
check("thêm CÙNG đường dẫn lần hai trả lại id cũ, không đẻ bản ghi trùng",
      st.add_project_file(pid, "05 - Projects/bang-gia.md") == f1
      and len(st.get_project_full(pid)["files"]) == 1)
check("đường dẫn rỗng bị từ chối", st.add_project_file(pid, "   ") is None)

f2 = st.add_project_file(pid, "06 - Sources/brief.md", "Brief landing")
check("tên tự đặt được giữ",
      any(f["name"] == "Brief landing" for f in st.get_project_full(pid)["files"]))

l1 = st.add_project_link(pid, "https://elegant.vn", "Đối thủ")
check("thêm link", len(st.get_project_full(pid)["links"]) == 1)
check("link trùng URL không đẻ bản ghi thứ hai",
      st.add_project_link(pid, "https://elegant.vn") == l1
      and len(st.get_project_full(pid)["links"]) == 1)

# Ghim đẩy lên đầu - đây là thứ tự người dùng thấy, và cũng là thứ tự đi vào prompt.
st.set_project_file_pinned(pid, f2, True)
check("file được ghim nhảy lên đầu danh sách",
      st.get_project_full(pid)["files"][0]["id"] == f2,
      [f["name"] for f in st.get_project_full(pid)["files"]])
st.set_project_file_pinned(pid, f2, False)
check("bỏ ghim thì về lại thứ tự mới-nhất-trước",
      st.get_project_full(pid)["files"][0]["id"] == f2)   # f2 thêm sau nên vẫn đứng đầu

# ============================================================
# 3. Không được đụng sang project khác dù đoán trúng id
# ============================================================
pid2 = st.create_project("Project khác", brain="brain")
check("xoá file bằng id đúng nhưng SAI project thì không ăn",
      st.remove_project_file(pid2, f1) is False
      and len(st.get_project_full(pid)["files"]) == 2)
check("ghim cũng vậy", st.set_project_file_pinned(pid2, f1, True) is False)
check("link cũng vậy", st.remove_project_link(pid2, l1) is False)

# ============================================================
# 4. Danh sách bên trái: chỉ ĐẾM, không kéo cả hướng dẫn về
# ============================================================
ds = [p for p in st.list_projects("brain") if p["id"] == pid][0]
check("list_projects đếm file", ds["file_count"] == 2, ds)
check("list_projects đếm link", ds["link_count"] == 1, ds)
check("và chỉ báo CÓ hướng dẫn hay không", ds["has_instructions"] == 1, ds)
check("KHÔNG kèm nội dung hướng dẫn (danh sách vẽ lại rất nhiều lần)",
      "instructions" not in ds, list(ds.keys()))
check("cũng không kèm danh sách file/link", "files" not in ds and "links" not in ds)

# ============================================================
# 5. Xoá project: hội thoại GỠ NHÃN, file/link XOÁ HẲN
# ============================================================
st.get_or_create("s-test", brain="brain", engine="cli", model="sonnet")
st.set_project("s-test", pid)
st.delete_project(pid)
check("project đã xoá", st.get_project(pid) is None)
check("get_project_full của project đã xoá trả None", st.get_project_full(pid) is None)
_con_f = st._read("SELECT COUNT(*) c FROM project_files WHERE project_id = ?", (pid,))[0]["c"]
_con_l = st._read("SELECT COUNT(*) c FROM project_links WHERE project_id = ?", (pid,))[0]["c"]
check("file của project bị xoá theo, không để rác mồ côi", _con_f == 0, _con_f)
check("link cũng vậy", _con_l == 0, _con_l)
_ht = st._read("SELECT COUNT(*) c FROM sessions WHERE id = 's-test'")[0]["c"]
check("nhưng HỘI THOẠI vẫn còn (chỉ bị gỡ nhãn)", _ht == 1, _ht)
check("project khác không bị đụng", st.get_project(pid2) is not None)

# ============================================================
# 6. CANARY nguồn: đừng ai thêm lại cột brain vào project_files
# ============================================================
_src = (SERVER / "sessions.py").read_text(encoding="utf-8")
_bang = _src.split("CREATE TABLE IF NOT EXISTS project_files", 1)[1].split(");", 1)[0]
check("CANARY: project_files KHÔNG có cột brain (brain lấy từ project)",
      "brain" not in _bang, _bang)
_main = (SERVER / "main.py").read_text(encoding="utf-8")
_them = _main.split("async def projects_add_file", 1)[1].split("\n@app.", 1)[0]
check("CANARY: route thêm file lấy brain từ PROJECT, không nhận từ client",
      'p.get("brain")' in _them and "brain: str = Form" not in _them, _them[:200])
check("CANARY: và kiểm đường dẫn bằng _safe_path trước khi ghi kho",
      "_safe_path(" in _them, _them[:200])
# ── Tài liệu tải lên phải nằm chỗ BỀN, không phải vùng cache (chủ repo báo 02/09) ─────
# attachments/ bị media_gc dọn theo tuổi (mặc định 30 ngày) và theo trần dung lượng. Tài liệu
# của project thì người dùng gắn vào để dùng lâu dài, nên phải đi vào Sources.
_ui = (ROOT / "dashboard" / "sessions-ui.js").read_text(encoding="utf-8")
_tai = _ui.split("async function taiLen", 1)[1].split("\n  async function", 1)[0]
check("CANARY: tải file của project vào sources, KHÔNG phải attachments",
      '"folder", "sources"' in _tai and "attachments" not in _tai, _tai[:300])
# Tên thư mục thật do SERVER tìm: brain có thể đặt "01 - Sources", và trần duyệt có thể cao
# hơn gốc brain. Đoán bằng chuỗi cứng ở frontend là đẻ ra thư mục thứ hai, file đi lạc.
check("CANARY: không đoán tên thư mục ở frontend, dùng đường dẫn server trả về",
      "up.path" in _tai and "homeCuaBrain" not in _ui, _tai[:300])
_up = _main.split("async def files_upload", 1)[1].split("\n@app.", 1)[0]
check("route upload nhận tên thư mục LOGIC và tự tìm thư mục thật",
      "_THU_MUC_LOGIC" in _up and "_resolve_subfolder" in _up, _up[:300])
check("và trả về đúng đường dẫn đã dùng để caller khỏi ghép lại",
      '"path":' in _up and '"dir":' in _up, _up[:300])
check("tên thư mục lạ bị từ chối, không ghi bừa",
      "Thư mục không hợp lệ" in _up, _up[:300])

# Lưới an toàn: kể cả file đã lỡ nằm trong attachments từ trước, gắn vào project là không
# được dọn nữa. Thiếu cái này thì bản vá chỉ cứu file MỚI, còn file cũ vẫn biến mất im lặng.
check("CANARY: media_gc được truyền danh sách file của project để chừa",
      "all_project_file_paths" in _main and "giu_path" in (SERVER / "media_gc.py").read_text(encoding="utf-8"))
_ses = (SERVER / "sessions.py").read_text(encoding="utf-8")
check("kho trả được mọi đường dẫn file đang gắn vào project",
      "def all_project_file_paths" in _ses)

_link = _main.split("async def projects_add_link", 1)[1].split("\n@app.", 1)[0]
check("CANARY: link chỉ nhận http/https", "^https?://" in _link, _link[:200])

# ── Tải thật một lượt, không chỉ soi cấu trúc ────────────────────────────────────────
# Soi chuỗi chỉ chứng minh code CÓ VIẾT đúng ý; nó không chứng minh file rơi đúng chỗ. Ca dễ
# sai nhất là brain đặt tên "01 - Sources": đoán bằng chuỗi cứng thì đẻ ra thư mục "sources"
# thứ hai nằm cạnh, và người dùng mở Sources ra không thấy file mình vừa tải.
from fastapi.testclient import TestClient  # noqa: E402
import main as _mainmod  # noqa: E402

_brain = tempfile.mkdtemp(prefix="brain-proj-")
os.makedirs(os.path.join(_brain, "01 - Sources"), exist_ok=True)
_c = TestClient(_mainmod.app, base_url="http://127.0.0.1")
_r = _c.post("/files/upload", data={"brain": _brain, "folder": "sources"},
             files={"file": ("bao-cao.pdf", b"%PDF-1.4 test", "application/pdf")}).json()
check("tải lên trả ok kèm đường dẫn đã dùng", _r.get("ok") and _r.get("path"), _r)
check("CANARY: file rơi vào thư mục Sources CÓ SẴN, không đẻ thư mục thứ hai",
      sorted(os.listdir(_brain)) == ["01 - Sources"], sorted(os.listdir(_brain)))
check("và file thật sự nằm trong đó",
      os.listdir(os.path.join(_brain, "01 - Sources")) == ["bao-cao.pdf"])
check("đường dẫn trả về trỏ đúng thư mục đó", "01 - Sources/bao-cao.pdf" in _r.get("path", ""))
_r2 = _c.post("/files/upload", data={"brain": _brain, "folder": "linh-tinh"},
              files={"file": ("x.txt", b"x", "text/plain")})
check("tên thư mục lạ bị chặn 400, không ghi bừa vào brain", _r2.status_code == 400, _r2.text)

print()
if _fails:
    print(f"FAIL {len(_fails)}: " + "; ".join(_fails))
    raise SystemExit(1)
print("TẤT CẢ PASS")
