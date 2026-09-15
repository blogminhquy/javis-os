"""Phiên chat theo kênh cộng sự: agent:<slug>, workflow:<slug>.

    python tests/run.py sessions_kenh_cong_su
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-kenh-")
os.environ["JAVIS_STATE_DIR"] = _TMP
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_TMP) / "conv.db")
# main.py:946 đọc BRAINS_DIR (KHÔNG có tiền tố JAVIS_) để tìm brain "brain" mặc định -
# đặt về thư mục tạm TRƯỚC khi import main, không được đụng vào brains/ thật của máy.
_BRAINS = tempfile.mkdtemp(prefix="javis-kenh-brains-")
os.environ["BRAINS_DIR"] = _BRAINS
# TestClient gửi Host: testserver, không nằm trong allowlist mặc định của web_security.py.
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"

import sessions  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


st = sessions.SessionStore(Path(_TMP) / "conv.db")
a = st.create_session(brain="/b", engine="cli", channel="web")
b = st.create_session(brain="/b", engine="cli", channel="agent:nguoi-viet")
c = st.create_session(brain="/b", engine="cli", channel="workflow:viet-bai")
d = st.create_session(brain="/b", engine="cli", channel="telegram")
for sid in (a, b, c, d):
    st.append_message(sid, "user", "xin chào")

ids = {s["id"] for s in st.list_sessions(brain="/b")}
check("mac dinh loai kenh cong su, giu web + telegram", ids == {a, d})
check("loc dung kenh agent", [s["id"] for s in st.list_sessions(brain="/b", channel="agent:nguoi-viet")] == [b])
check("loc dung kenh workflow", [s["id"] for s in st.list_sessions(brain="/b", channel="workflow:viet-bai")] == [c])
moc = st.moc_cap_nhat_theo_kenh(["/b"], "agent:")
check("moc_cap_nhat_theo_kenh", set(moc) == {"agent:nguoi-viet"} and moc["agent:nguoi-viet"] > 0)
check("channel=* tra ve moi kenh", {s["id"] for s in st.list_sessions(brain="/b", channel="*")} == {a, b, c, d})

# Canary nguồn: learn.py phải gọi list_sessions với channel="*" ở fallback "phiên mới nhất
# của brain" - hội thoại cộng sự cũng là hội thoại của chủ, vòng tự học không được bỏ sót.
_learn_src = (ROOT / "server" / "learn.py").read_text(encoding="utf-8")
check("learn.py fallback dung channel=\"*\"", 'channel="*"' in _learn_src)

# Route: POST /sessions/new
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
cl = TestClient(main.app)
r = cl.post("/sessions/new", data={"brain": "brain", "channel": "agent:khong-ton-tai"})
check("POST /sessions/new agent khong co -> 404", r.status_code == 404)
r = cl.post("/sessions/new", data={"brain": "brain", "channel": "gi-do"})
check("POST /sessions/new kenh sai dang -> 400", r.status_code == 400)
# Tạo một agent thật trong brain test rồi mở phiên
ag_dir = main._agents_dir("brain"); ag_dir.mkdir(parents=True, exist_ok=True)
(ag_dir / "nguoi-viet.md").write_text("---\nname: Người viết\nrole: viết\nmodel: gpt-5\nmodel_provider: openai-oauth\n---\nViết hay.\n", encoding="utf-8")
r = cl.post("/sessions/new", data={"brain": "brain", "channel": "agent:nguoi-viet"})
check("POST /sessions/new agent that -> id", r.status_code == 200 and r.json().get("id"))
row = main.get_store().get_session(r.json()["id"])
check("phien ghi dung kenh va ghim model cua agent", row["channel"] == "agent:nguoi-viet"
      and row.get("pinned_model") == "gpt-5" and row.get("pinned_provider") == "openai-oauth")
r = cl.get("/sessions", params={"brain": "brain", "channel": "agent:nguoi-viet"}).json()
check("GET /sessions?channel= tra dung phien", [s["id"] for s in r["sessions"]] == [row["id"]])

# Slug CO DAU tieng Viet. _slugify giu nguyen chu tieng Viet, nen brain that co han
# "javis-vu~.md" va "kiem-chung-vien.md" (dau day du). Khuon cu ^[a-z0-9][a-z0-9-]*$ chan dung
# nhung file do: bam vao trang Cong su la an 400 kem cau loi THO cua server hien thang ra man
# hinh. Day la thu canh chuyen do.
_slug_vn = "kiểm-chứng-viên"
(ag_dir / (_slug_vn + ".md")).write_text("---\nname: Kiểm chứng viên\nrole: soi\n---\nSoi ky.\n", encoding="utf-8")
r = cl.post("/sessions/new", data={"brain": "brain", "channel": "agent:" + _slug_vn})
check("POST /sessions/new nhan slug co dau tieng Viet", r.status_code == 200 and r.json().get("id"))
check("phien ghi dung kenh co dau",
      main.get_store().get_session(r.json()["id"])["channel"] == "agent:" + _slug_vn)
# Van phai chan thu co the leo ra khoi thu muc hay cat nham kenh.
for xau in ["agent:a/b", "agent:a\\b", "workflow:x y", "agent:", "agent:a:b", "tro-ly:x"]:
    r = cl.post("/sessions/new", data={"brain": "brain", "channel": xau})
    check("POST /sessions/new chan kenh sai dang: " + xau, r.status_code == 400)

# Slug toan DAU CHAM. Day la nua AN TOAN cua viec noi khuon: khuon moi cho qua moi ky tu tru
# gach cheo, hai cham va khoang trang, nen ".." va "." lot khuon. Chung KHONG duoc tro ra
# ngoai thu muc agents/, va quan trong hon: khong duoc doc mot file nao nam ngoai do.
from unittest.mock import patch  # noqa: E402
_da_doc = []
_read_md_that = main._read_md


def _ghi_lai_duong_doc(p, *a, **k):
    _da_doc.append(Path(str(p)).resolve())
    return _read_md_that(p, *a, **k)


# File moi nhu vay nam NGAY TREN thu muc agents - neu ".." tro ra duoc thi no la thu doc trung.
(Path(main._brain_root("brain")) / "bi-mat.md").write_text(
    "---\nname: bí mật\n---\nkhông được đọc\n", encoding="utf-8")
with patch.object(main, "_read_md", _ghi_lai_duong_doc):
    for xau in ["agent:..", "agent:.", "workflow:..", "agent:...", "agent:..md"]:
        r = cl.post("/sessions/new", data={"brain": "brain", "channel": xau})
        check("POST /sessions/new tu choi slug toan dau cham: " + xau,
              r.status_code in (400, 404))
_thu_muc_ag = main._agents_dir("brain").resolve()
_thu_muc_wf = main._workflows_dir("brain").resolve()
check("khong doc file nao ngoai agents/ va workflows/",
      all(str(p).startswith(str(_thu_muc_ag)) or str(p).startswith(str(_thu_muc_wf))
          for p in _da_doc))

print("\nFAIL:" if fails else "\nOK - sessions_kenh_cong_su", fails or "")
sys.exit(1 if fails else 0)
