"""2026-11-09: the "..." menu of a chat in the history column, archiving and "mark as unread".

    python tests/run.py luu_tru_hoi_thoai      (KHÔNG mạng)

Owner (design approved as an HTML mock-up): the four icons on each row fold into one "..." menu; it adds share, export
as .md, mark as unread and archive. An archived chat leaves the list but keeps every message (Javis still remembers it,
search still finds it); the "Archived" row at the bottom of the column lists them; a new message from a person brings
one back. "Xem thêm" is gone: the list loads more by itself.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-luutru-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)
st = main.get_store()
B = main._brain_key("brain")
ids = []
for i in range(5):
    sid = st.create_session(brain=B, engine="cli", channel="web", title=f"Chat {i}")
    st.append_message(sid, "user", f"hỏi về nước mắm {i}")
    st.append_message(sid, "assistant", f"trả lời {i}")
    st.mark_read(sid, time.time() + 5)
    ids.append(sid)


def listed(**q):
    r = cl.get("/sessions", params=dict({"brain": "brain", "limit": 50}, **q)).json()
    return [s["id"] for s in r["sessions"]], r.get("archived_count")


# ---- 1. Archive ----
before = st.get_session(ids[1])["updated_at"]
r = cl.post(f"/sessions/{ids[1]}/archive", data={"archived": "1"}).json()
check("lưu trữ: ok", r.get("ok") and r.get("archived") is True, r)
live, n = listed()
check("hội thoại đã lưu trữ rời khỏi danh sách", ids[1] not in live and len(live) == 4, live)
check("danh sách báo số hội thoại đã lưu trữ", n == 1, n)
arch, n2 = listed(archived=1)
check("xem mục Đã lưu trữ: chỉ ra hội thoại đã lưu trữ", arch == [ids[1]], arch)
check("hai câu trả lời cùng một con số", n2 == 1, n2)
check("nội dung còn nguyên", len(st.get_messages(ids[1])) == 2 if hasattr(st, "get_messages")
      else st.get_session(ids[1])["msg_count"] == 2)
check("lưu trữ không đổi giờ cập nhật (đưa trở lại thì nằm đúng chỗ cũ)", st.get_session(ids[1])["updated_at"] == before)
hits = cl.get("/sessions/search", params={"q": "nước mắm 1", "brain": "brain"}).json()["results"]
check("tìm kiếm vẫn tìm thấy hội thoại đã lưu trữ, có cờ archived",
      any(h["session_id"] == ids[1] and h["archived"] == 1 for h in hits), hits)
check("kết quả tìm mang project_id để vẽ nhãn", all("project_id" in h for h in hits))
meta = cl.get(f"/sessions/{ids[1]}/meta").json()
check("meta của hội thoại báo archived (thanh tiêu đề hiện nhãn)", meta.get("archived") == 1, meta.get("archived"))

r = cl.post(f"/sessions/{ids[1]}/archive", data={"archived": "0"}).json()
check("đưa trở lại danh sách", r.get("ok") and ids[1] in listed()[0] and listed()[1] == 0)

# ---- 2. A new message from a person brings an archived chat back; a reply from Javis does not ----
cl.post(f"/sessions/{ids[2]}/archive", data={"archived": "1"})
st.append_message(ids[2], "assistant", "báo cáo nền")
check("tin của Javis không kéo hội thoại đã lưu trữ ra lại", ids[2] not in listed()[0])
st.append_message(ids[2], "user", "nhắn tiếp")
check("người nhắn tiếp thì hội thoại tự trở lại danh sách", ids[2] in listed()[0])

# ---- 3. Mark as unread ----
rows = {s["id"]: s for s in cl.get("/sessions", params={"brain": "brain"}).json()["sessions"]}
check("trước đó: đã đọc", rows[ids[3]]["unread"] is False)
r = cl.post(f"/sessions/{ids[3]}/unread").json()
check("đánh dấu chưa đọc: chấm đỏ quay lại", r.get("ok") and r.get("unread") is True, r)
rows = {s["id"]: s for s in cl.get("/sessions", params={"brain": "brain"}).json()["sessions"]}
check("danh sách thấy hội thoại đó chưa đọc", rows[ids[3]]["unread"] is True)
cl.post(f"/sessions/{ids[3]}/read")
rows = {s["id"]: s for s in cl.get("/sessions", params={"brain": "brain"}).json()["sessions"]}
check("mở ra đọc thì hết chưa đọc", rows[ids[3]]["unread"] is False)

# ---- 4. The column ----
js = (ROOT / "dashboard" / "sessions-ui.js").read_text(encoding="utf-8")
css = (ROOT / "dashboard" / "style.css").read_text(encoding="utf-8")
check("menu của hàng có đủ mục", all(f'"{a}"' in js for a in ("pin", "proj", "rename", "share", "export", "unread",
                                                               "archive", "restore", "delete", "del_yes")))
check("xoá hỏi lại ngay trong menu, không dùng confirm()", 'if (act === "delete") { _sm.view = "del"; return veMenuDong(true); }' in js
      and "confirm(window.t(\"sess.del_q\"" not in js)
check("đổi tên ngay tại hàng", "function doiTenTaiDong(s)" in js and 'class="ci-ren-in"' in js)
check("xuất .md dùng chung với lệnh /export", "window.JavisLenh.xuatHoiThoai(s.id)" in js
      and "xuatHoiThoai: xuatHoiThoai" in (ROOT / "dashboard" / "chat-lenh.js").read_text(encoding="utf-8"))
check("chia sẻ link mở đúng hội thoại của hàng", "moChiaSeHoiThoai(nut || document.body, s.id)" in js)
check("mục Đã lưu trữ ghim ở đáy cột, có số đếm", "function ganChanLuuTru()" in js and '"&archived=1"' in js
      and "archived_count" in js)
check("bỏ nút Xem thêm: tự tải khi cuộn tới cuối", "IntersectionObserver" in js and 'class="cside-more" type="button"' not in js)
check("hội thoại đang mở đã lưu trữ: thanh tiêu đề có nhãn và nút đưa trở lại", 'class="cs-arch-chip"' in js
      and "luuTru({ id: sidNay }, false)" in js)
check("menu dùng chung kiểu với hòm thư bot (ht-rmenu, tấm trượt trên điện thoại)",
      'm.className = "ht-rmenu cs-rmenu" + (phone ? " ht-rsheet" : "")' in js)
check("CSS: nhãn project chữ thường, không viền", ".ci-meta > .ci-proj {" in css and "font-weight: 400" in css.split(".ci-meta > .ci-proj {")[1].split("}")[0]
      and "border:" not in css.split(".ci-meta > .ci-proj {")[1].split("}")[0])
for lang in ("vi", "en"):
    dd = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    import re
    keys = set(re.findall(r'"(sess\.[a-z_]+)"', js))
    need = [k for k in keys if not dd.get(k)]
    check(f"{lang}: đủ chữ cho cột hội thoại", not need, need)

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_luu_tru_hoi_thoai: all pass")
