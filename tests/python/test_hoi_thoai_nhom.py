"""Ghim hội thoại, gom vào Project, gắn icon - kho + endpoint.

    python tests/run.py hoi_thoai_nhom

Ba thứ này đi chung một bảng nên test chung một chỗ. Những gì file này canh, theo thứ tự
"hỏng thì đau tới đâu":

1. XOÁ PROJECT KHÔNG ĐƯỢC XOÁ HỘI THOẠI. Người dùng gom nhóm để đỡ rối; một cú bấm nhầm mà
   cuốn theo cả tháng trò chuyện thì không có đường hoàn tác nào. Ràng buộc này CHỈ nằm ở
   tầng code (cột project_id không khai khoá ngoại được vì thêm bằng ALTER TABLE), nên nó
   phải có test canh, không thì lần refactor sau là mất.
2. DB CŨ PHẢI TỰ NÂNG CẤP. Hai cột mới thêm bằng ALTER TABLE; CREATE TABLE IF NOT EXISTS
   không tự thêm cột cho DB đã có sẵn. Ai cũng đang có conversations.db chạy từ lâu.
3. GẮN NHÃN ĐƯỢC TRƯỚC KHI HÀNG TỒN TẠI. Dashboard tự sinh id hội thoại ở phía client ngay
   lúc bấm gửi, còn hàng trong DB thì tới lượt server xử lý mới có. Không có nhánh
   "tạo nếu chưa có" thì tính năng "chat mới rơi vào project đang mở" không chạy được ở
   ĐÚNG tin nhắn đầu tiên - tức là lúc người dùng để ý nhất.

KHÔNG mạng, DB nằm trong thư mục tạm.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import sqlite3
import sys
import tempfile
from pathlib import Path

import sessions

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def store():
    return sessions.SessionStore(Path(tempfile.mkdtemp(prefix="javis-sess-")) / "c.db")


# ============================================================
# 1. Ghim: lên đầu danh sách, và KHÔNG đụng mốc thời gian
# ============================================================
st = store()
cu = st.create_session(brain="brain", title="Cũ")
st.append_message(cu, "user", "câu cũ")
moi = st.create_session(brain="brain", title="Mới")
st.append_message(moi, "user", "câu mới")

thu_tu = [s["id"] for s in st.list_sessions(brain="brain")]
check("chưa ghim thì mới nhất đứng trước", thu_tu == [moi, cu])

truoc = st.get_session(cu)["updated_at"]
st.set_pinned(cu, True)
sau = st.get_session(cu)["updated_at"]
check("ghim xong thì nó lên đầu", [s["id"] for s in st.list_sessions(brain="brain")] == [cu, moi])
# Ghim mà đẩy updated_at lên thì hội thoại đó nhảy nhóm "Hôm nay" và mọi cuộc khác xáo chỗ -
# một thao tác sắp xếp không được phép giả vờ là "vừa nói chuyện".
check("ghim KHÔNG làm mốc thời gian nhảy", truoc == sau)
check("cột pinned trả về cho giao diện", st.list_sessions(brain="brain")[0]["pinned"] == 1)
st.set_pinned(cu, False)
check("bỏ ghim thì về đúng thứ tự thời gian",
      [s["id"] for s in st.list_sessions(brain="brain")] == [moi, cu])

# ============================================================
# 2. Hội thoại KHÔNG có icon riêng - icon là chuyện của Project
# ============================================================
# Hàng nào trong danh sách cũng là một cuộc trò chuyện nên icon ở đó không phân loại được gì,
# chỉ thêm một nút phải bấm và một hàng nút chật thêm. Icon để PHÂN LOẠI thuộc về Project,
# nơi mỗi nhóm thật sự là một thứ khác nhau (chủ repo chốt 2026-08-04).
check("CANARY: kho KHÔNG còn đường đặt icon cho hội thoại", not hasattr(st, "set_icon"))
check("danh sách hội thoại không trả cột icon nữa",
      "icon" not in st.list_sessions(brain="brain")[0])

# ============================================================
# 3. Project: lọc, đếm, và XOÁ THÌ CHỈ GỠ NHÃN
# ============================================================
pid = st.create_project("Khách hàng", icon="folder", brain="brain")
st.set_project(cu, pid)
ds = st.list_projects(brain="brain")
check("project hiện ra kèm số hội thoại", len(ds) == 1 and ds[0]["session_count"] == 1)
check("lọc theo project ra đúng một cuộc",
      [s["id"] for s in st.list_sessions(brain="brain", project=pid)] == [cu])
check('lọc "none" ra cuộc chưa xếp nhóm',
      [s["id"] for s in st.list_sessions(brain="brain", project="none")] == [moi])
check("không lọc thì vẫn thấy cả hai", len(st.list_sessions(brain="brain")) == 2)

st.update_project(pid, name="Khách VIP", icon="")
p = st.get_project(pid)
check("đổi tên project", p["name"] == "Khách VIP")
check("icon rỗng = gỡ icon của project", p["icon"] is None)
st.update_project(pid, icon="message-circle")
check("tên icon có gạch nối vẫn hợp lệ", st.get_project(pid)["icon"] == "message-circle")
st.update_project(pid, icon="  Star ")
check("chuẩn hoá về chữ thường, bỏ khoảng trắng thừa", st.get_project(pid)["icon"] == "star")
for rac in ("🔥", "x" * 60, "a b", "../../etc", "<svg>"):
    st.update_project(pid, icon="star")
    st.update_project(pid, icon=rac)
    check(f"giá trị icon rác {rac[:12]!r} bị từ chối chứ không lọt vào cột",
          st.get_project(pid)["icon"] is None)
st.update_project(pid, name="   ")
check("tên toàn khoảng trắng thì GIỮ tên cũ, không xoá trắng",
      st.get_project(pid)["name"] == "Khách VIP")

n = st.delete_project(pid)
check("xoá project báo đúng số hội thoại được gỡ nhãn", n == 1)
check("CANARY: xoá project KHÔNG xoá hội thoại", len(st.list_sessions(brain="brain")) == 2)
check("hội thoại được gỡ về chưa-xếp-nhóm", st.get_session(cu)["project_id"] is None)
check("project biến mất khỏi danh sách", st.list_projects(brain="brain") == [])

# Project gắn theo brain: đổi brain là danh sách project đổi theo, không lẫn của nhau.
st.create_project("Của brain khác", brain="brain-2")
check("project lọc theo brain", len(st.list_projects(brain="brain")) == 0
      and len(st.list_projects(brain="brain-2")) == 1)

# ============================================================
# 4. Gắn nhãn cho hội thoại CHƯA tồn tại (chat mới trong lúc đang mở project)
# ============================================================
pid2 = st.create_project("Dự án A", brain="brain")
check("không có brain thì từ chối, không đẻ hàng ma",
      st.set_project("chua-ton-tai", pid2) is False)
check("hàng ma đúng là không được tạo", st.get_session("chua-ton-tai") is None)
check("có brain thì tạo hàng rồi gắn nhãn", st.set_project("sid-moi", pid2, brain="brain") is True)
hang = st.get_session("sid-moi")
check("hàng vừa tạo mang đúng brain và đúng project",
      hang["brain"] == "brain" and hang["project_id"] == pid2)
# Lượt chat sau đó gọi get_or_create trên CHÍNH id đó - phải nhận lại hàng cũ (giữ nhãn
# project) chứ không đè lên thành hàng mới trắng trơn.
st.get_or_create("sid-moi", brain="brain", engine="cli", model="opus")
lai = st.get_session("sid-moi")
check("CANARY: lượt chat sau không thổi bay nhãn project",
      lai["project_id"] == pid2 and lai["engine"] == "cli")

# ============================================================
# 5. DB CŨ (chưa có cột mới) phải tự nâng cấp, không mất dữ liệu
# ============================================================
old = Path(tempfile.mkdtemp(prefix="javis-old-")) / "old.db"
con = sqlite3.connect(str(old))
con.executescript("""
CREATE TABLE sessions (id TEXT PRIMARY KEY, title TEXT, brain TEXT NOT NULL DEFAULT 'brain',
  engine TEXT, model TEXT, cli_session_id TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
  msg_count INTEGER NOT NULL DEFAULT 0, parent_session_id TEXT, archived INTEGER NOT NULL DEFAULT 0);
CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL, content TEXT, ts REAL NOT NULL, tool_calls_json TEXT);
INSERT INTO sessions (id,title,brain,created_at,updated_at) VALUES ('cu1','Hội thoại cũ','brain',1,1);
""")
con.commit()
con.close()

st2 = sessions.SessionStore(old)
ds2 = st2.list_sessions(brain="brain")
check("DB cũ mở được và giữ nguyên hội thoại cũ",
      len(ds2) == 1 and ds2[0]["title"] == "Hội thoại cũ")
check("DB cũ có đủ cột mới với giá trị mặc định an toàn",
      ds2[0]["pinned"] == 0 and ds2[0]["project_id"] is None)
idx = {r[0] for r in st2._read("SELECT name FROM sqlite_master WHERE type='index'")}
# Index này phải tạo SAU vòng ALTER. Đặt nhầm vào _SCHEMA_SQL thì DB cũ ném "no such column"
# và huỷ cả lượt khởi tạo schema - app không mở nổi hội thoại nào.
check("index cho cột project được tạo sau khi cột đã tồn tại", "idx_sessions_project" in idx)
st2.set_pinned("cu1", True)
check("hội thoại của DB cũ ghim được ngay", st2.list_sessions(brain="brain")[0]["pinned"] == 1)

# ============================================================
# 6. Endpoint có mặt đúng đường dẫn
# ============================================================
import main  # noqa: E402

duong = {getattr(r, "path", "") for r in main.app.routes}
for p in ("/projects", "/projects/{project_id}/update", "/projects/{project_id}/delete",
          "/sessions/{session_id}/pin", "/sessions/{session_id}/project"):
    check(f"có endpoint {p}", p in duong)
check("CANARY: KHÔNG còn endpoint đặt icon cho hội thoại",
      "/sessions/{session_id}/icon" not in duong)

if fails:
    print("\nFAIL - test_hoi_thoai_nhom: " + str(len(fails)) + " lỗi: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_hoi_thoai_nhom: tất cả pass")
