"""Engine KHÔNG có tool file native phải đọc được cây mã nguồn của phiên Coding.

    python tests/run.py coding_tool_context

Chặn cứng được gỡ ở đây (spec mục 2.2): trang Coding đổi `cwd` sang repo, nhưng chỉ engine
CLI hưởng vì chỉ chúng có tool file native. Engine API đọc ghi qua `mcp_hub`, mà hub nhận
`vault_root = brain` vô điều kiện, nên một engine như vậy ngồi trong phiên Coding là không đọc
nổi một file nào của repo. (Cảnh đầu tiên là với `chatgpt-web`, đã gỡ ở 0.64.20.)

Phép thử quan trọng nhất KHÔNG phải "repo đọc được", mà là **phiên chat thường không đổi một
chút nào**. Nới rào là việc dễ làm quá tay; thay đổi này chỉ được có tác dụng đúng trong
phiên coding.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-codingctx-")
os.environ["JAVIS_STATE_DIR"] = _TMP

import coding_store  # noqa: E402
import coding_ctx  # noqa: E402
import mcp_hub  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---- Dựng một brain và một repo git thật, nằm ở hai chỗ khác nhau ----

BRAIN = Path(_TMP) / "brain"
(BRAIN / "notes").mkdir(parents=True, exist_ok=True)
(BRAIN / "notes" / "ghi-chu.md").write_text("ghi chú trong brain", encoding="utf-8")

REPO = Path(_TMP) / "du-an"
(REPO / "server").mkdir(parents=True, exist_ok=True)
(REPO / "server" / "auth.py").write_text("def login():\n    return None\n", encoding="utf-8")
_git(["init", "-q"], str(REPO))
_git(["config", "user.email", "t@t"], str(REPO))
_git(["config", "user.name", "t"], str(REPO))
_git(["add", "-A"], str(REPO))
_git(["commit", "-qm", "đầu"], str(REPO))

repo_row = coding_store.them_thu_muc(str(REPO), brain="brain", ten="du-an")
SID = "phien-coding-1"
coding_store.dat_rang_buoc(SID, thu_muc_id=repo_row["id"])


# ---- 1. CodingToolContext đọc đúng kho ----

ctx = coding_ctx.CodingToolContext.from_session(SID)
check("phiên coding -> có workspace_root", ctx.active)
check("workspace_root trỏ đúng repo", Path(ctx.workspace_root) == REPO.resolve())
check("nhận ra đây là repo git", ctx.is_git_repo)
check("mức quyền mặc định là auto (không phải full)", ctx.permission_mode == "auto")
check("auto thì cho ghi", ctx.cho_ghi)
check("auto thì cho chạy lệnh", ctx.cho_chay_lenh)

coding_store.dat_rang_buoc(SID, muc_quyen="suggest")
ctx_s = coding_ctx.CodingToolContext.from_session(SID)
check("suggest thì KHÔNG cho ghi", not ctx_s.cho_ghi)
check("suggest thì KHÔNG cho chạy lệnh", not ctx_s.cho_chay_lenh)
coding_store.dat_rang_buoc(SID, muc_quyen="auto")

check("mô tả cho prompt có nêu thư mục", str(REPO.resolve()) in ctx.mo_ta())
check("mô tả cho prompt có nêu mức quyền", "auto" in ctx.mo_ta())

check("một thư mục -> danh sách gốc có đúng nó", ctx.workspace_roots == (str(REPO.resolve()),))


# ---- 1b. NHIỀU thư mục trong một phiên (0.63.9) ----
#
# Engine CLI chỉ hưởng thư mục CHÍNH vì tool file native của nó chạy theo `cwd`, mà một tiến
# trình chỉ đứng được một chỗ. Engine qua hub KHÔNG chạy tiến trình nào, nên giới hạn đó
# không áp cho nó - và không tận dụng thì nó đọc được ít hơn đúng những thư mục mà trang
# Coding vừa hứa là thuộc việc này, im lặng.

REPO2 = Path(_TMP) / "du-an-hai"
(REPO2 / "lib").mkdir(parents=True, exist_ok=True)
(REPO2 / "lib" / "util.py").write_text("X = 1\n", encoding="utf-8")
repo2_row = coding_store.them_thu_muc(str(REPO2), brain="brain", ten="du-an-hai")
coding_store.dat_rang_buoc(SID, thu_muc_ids=[repo_row["id"], repo2_row["id"]])

ctx2 = coding_ctx.CodingToolContext.from_session(SID)
check("gắn hai thư mục -> cả hai vào danh sách gốc",
      set(ctx2.workspace_roots) == {str(REPO.resolve()), str(REPO2.resolve())})
check("thư mục CHÍNH đứng đầu danh sách",
      ctx2.workspace_roots[0] == str(REPO.resolve()))
check("workspace_root (số ít) vẫn là thư mục chính",
      ctx2.workspace_root == str(REPO.resolve()))
check("mô tả cho prompt có nêu cả thư mục phụ", str(REPO2.resolve()) in ctx2.mo_ta())
check("goc_file_cua_phien trả đúng danh sách đó",
      coding_ctx.goc_file_cua_phien(SID) == ctx2.workspace_roots)
check("phiên thường -> goc_file_cua_phien rỗng",
      coding_ctx.goc_file_cua_phien("phien-chat-thuong") == ())

# Hub phải đọc được file ở thư mục PHỤ, không chỉ thư mục chính.
_p2 = mcp_hub._safe_path(str(BRAIN), "lib/util.py", workspace_root=list(ctx2.workspace_roots))
check("hub đọc được file ở thư mục PHỤ", _p2 == (REPO2 / "lib" / "util.py").resolve())
_p1 = mcp_hub._safe_path(str(BRAIN), "server/auth.py", workspace_root=list(ctx2.workspace_roots))
check("hub vẫn đọc đúng file ở thư mục CHÍNH", _p1 == (REPO / "server" / "auth.py").resolve())
_pb = mcp_hub._safe_path(str(BRAIN), "notes/ghi-chu.md", workspace_root=list(ctx2.workspace_roots))
check("brain vẫn THẮNG khi file có thật trong brain",
      _pb == (BRAIN / "notes" / "ghi-chu.md").resolve())
check("truyền MỘT chuỗi vẫn chạy như cũ (mọi chỗ gọi cũ không phải sửa)",
      mcp_hub._safe_path(str(BRAIN), "server/auth.py", workspace_root=str(REPO))
      == (REPO / "server" / "auth.py").resolve())
check("danh sách RỖNG = không có gốc làm việc nào, y hệt None",
      mcp_hub._goc_lam_viec([]) == [] and mcp_hub._goc_lam_viec(None) == [])

# Trả lại một thư mục cho các phần thử phía dưới.
coding_store.dat_rang_buoc(SID, thu_muc_ids=[repo_row["id"]])


# ---- 2. Phiên KHÔNG phải coding: rỗng, và rỗng là bình thường ----

trong = coding_ctx.CodingToolContext.from_session("phien-chat-thuong")
check("phiên thường -> không active", not trong.active)
check("phiên thường -> workspace_root rỗng", trong.workspace_root == "")
check("phiên thường -> mô tả rỗng (không nhét rác vào prompt)", trong.mo_ta() == "")
check("session_id rỗng không nổ", not coding_ctx.CodingToolContext.from_session("").active)
check("session_id None không nổ", not coding_ctx.CodingToolContext.from_session(None).active)


# ---- 3. Rào đường dẫn: hai gốc ----

def doc(rel, ws=None):
    tools, route = mcp_hub._builtin_tools("full", str(BRAIN), workspace_root=ws)
    return asyncio.run(route["javis_read_file"]["call"]({"path": rel}))


check("KHÔNG có workspace: đọc được file trong brain",
      "ghi chú trong brain" in doc("notes/ghi-chu.md"))
r = doc("server/auth.py")
check("KHÔNG có workspace: file repo KHÔNG đọc được (đúng hành vi cũ)", r.startswith("ERROR:"))
# Lưu ý: đường dẫn tương đối kiểu này ghép vào brain vẫn hợp lệ VỀ MẶT CHỮ, chỉ là không có
# file ở đó - nên câu lỗi là "không có file", không phải "nằm ngoài". Đây chính là lý do rào
# hai gốc phải xét TỒN TẠI chứ không chỉ xét chứa.
check("KHÔNG có workspace: báo không có file (không phải nằm ngoài)", "không có file" in r)
r = doc("../../../etc/passwd")
check("KHÔNG có workspace: thoát ra ngoài brain vẫn bị chặn bằng câu cũ",
      "nằm ngoài bộ não đang làm việc" in r)

ws = str(REPO.resolve())
check("CÓ workspace: đọc được file trong repo", "def login()" in doc("server/auth.py", ws))
check("CÓ workspace: vẫn đọc được file trong brain (không cướp gốc cũ)",
      "ghi chú trong brain" in doc("notes/ghi-chu.md", ws))

r = doc("../../../etc/passwd", ws)
check("CÓ workspace: thoát ra ngoài cả hai gốc vẫn bị chặn", r.startswith("ERROR:"))
check("CÓ workspace: câu lỗi nói rõ MỌI nơi được phép đọc (spec 7.1)",
      "bộ não" in r and "thư mục làm việc" in r)
check("CÓ workspace: câu lỗi in ra thư mục làm việc để model biết mình đang ở đâu", ws in r)


# ---- 4. Vault luôn thắng khi hai gốc cùng nhận ----

(REPO / "notes").mkdir(exist_ok=True)
(REPO / "notes" / "ghi-chu.md").write_text("BẢN TRONG REPO", encoding="utf-8")
check("trùng đường dẫn ở hai gốc -> vault thắng, không lặng lẽ đọc file repo",
      "ghi chú trong brain" in doc("notes/ghi-chu.md", ws))

# Luật chọn gốc phải xét TỒN TẠI rồi mới tới THƯ MỤC CHA. Thiếu bước này thì mọi đường dẫn
# repo rơi vào brain và trả "không có file" - đúng chặn cứng mà tham số này sinh ra để gỡ.
check("file chỉ có ở repo -> đọc từ repo", "def login()" in doc("server/auth.py", ws))
check("file chỉ có ở brain -> đọc từ brain", "ghi chú" in doc("notes/ghi-chu.md", ws))


# ---- 5. Ghi file: cũng theo hai gốc, và vẫn chặn ra ngoài ----

def ghi(rel, noi_dung, ws=None):
    tools, route = mcp_hub._builtin_tools("full", str(BRAIN), workspace_root=ws)
    return asyncio.run(route["javis_write_file"]["call"]({"path": rel, "content": noi_dung}))


ghi("server/moi.py", "# file mới\n", ws)
check("CÓ workspace: file MỚI rơi vào repo vì brain không có thư mục server/",
      (REPO / "server" / "moi.py").is_file())
check("CÓ workspace: file mới KHÔNG rơi nhầm vào brain",
      not (BRAIN / "server" / "moi.py").exists())
ghi("notes/moi.md", "nháp", ws)
check("CÓ workspace: file mới trong thư mục CHỈ brain có thì rơi vào brain",
      (BRAIN / "notes" / "moi.md").is_file())

r = ghi("../../../tmp/ngoai.py", "x", ws)
check("ghi ra ngoài cả hai gốc -> câu lỗi NÓI ĐƯỢC, không ném exception",
      r.startswith("ERROR:"))
check("câu lỗi khi ghi cũng nêu đủ các nơi được phép ghi",
      "bộ não" in r and "thư mục làm việc" in r)
check("câu lỗi khi ghi in ra thư mục làm việc", ws in r)


# ---- 6. Liệt kê thư mục cũng theo hai gốc ----

def ls(rel, ws=None):
    tools, route = mcp_hub._builtin_tools("full", str(BRAIN), workspace_root=ws)
    return asyncio.run(route["javis_list_dir"]["call"]({"path": rel}))


check("CÓ workspace: liệt kê được thư mục trong repo", "auth.py" in ls("server", ws))
check("KHÔNG có workspace: thư mục repo không liệt kê được",
      "auth.py" not in ls("server"))


# ---- 7. Bất biến: phiên thường phải chạy y như trước ----

t1, r1 = mcp_hub._builtin_tools("full", str(BRAIN))
t2, r2 = mcp_hub._builtin_tools("full", str(BRAIN), workspace_root=None)
check("workspace_root=None cho ra đúng bộ tool như không truyền gì",
      [x["fn"] for x in t1] == [x["fn"] for x in t2])
check("thêm workspace KHÔNG thêm bớt tool nào",
      [x["fn"] for x in t1] == [x["fn"] for x in
                                mcp_hub._builtin_tools("full", str(BRAIN), workspace_root=ws)[0]])


# ---- 8. Khoá cache phải chứa workspace, kẻo hai repo dùng chung một route ----

# Soi HÀNH VI chứ không tìm chuỗi trong khoá cache (0.64): bản cũ khẳng định đúng một biểu
# thức `str(workspace_root or "")`, nên đổi gốc từ MỘT chuỗi sang DANH SÁCH là test đỏ dù
# khoá vẫn phân biệt đúng. Cái phải giữ là hai bộ gốc khác nhau cho ra hai khoá khác nhau.
_src = (SERVER / "mcp_hub.py").read_text(encoding="utf-8")
check("hai bộ gốc khác nhau -> hai khoá cache khác nhau (không dùng chung route)",
      mcp_hub._ten_goc([str(REPO)]) != mcp_hub._ten_goc([str(REPO), str(REPO2)]))
check("không có gốc nào -> khoá rỗng, tức phiên chat thường không đổi khoá",
      mcp_hub._ten_goc(None) == "" and mcp_hub._ten_goc([]) == "")
check("khoá cache của discover_all có tính tới gốc làm việc",
      "_ten_goc(workspace_root)" in _src)
check("discover_all truyền workspace_root xuống _builtin_tools",
      "workspace_root=workspace_root)" in _src)


# ---- 9. Sổ hỏng không được làm chết một lượt chat ----

class _KhoHong:
    def cwd_cua_phien(self, *a, **k):
        raise RuntimeError("sổ hỏng")


_that = coding_ctx.coding_store
try:
    coding_ctx.coding_store = _KhoHong()
    check("kho coding hỏng -> trả context rỗng, không ném",
          not coding_ctx.CodingToolContext.from_session(SID).active)
finally:
    coding_ctx.coding_store = _that


# ---- 10. Ranh giới: coding_ctx không kéo theo nửa server ----

_cc = (SERVER / "coding_ctx.py").read_text(encoding="utf-8")
for cam in ("import main", "from main", "fastapi", "import mcp_hub"):
    check(f"coding_ctx thuần, không '{cam}'", cam not in _cc)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_coding_tool_context: tất cả pass")
