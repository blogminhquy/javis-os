"""0.223.0: nút ghim ở mọi danh sách hội thoại.

    python tests/run.py ghim_hoi_thoai      (KHÔNG mạng)

Chủ dự án (2026-10-19, ảnh ô tìm "sở" ở cột Lịch sử): "ở trong phần tìm và chọn hội thoại cho anh thêm nút ghim ở tất
cả các màn có lịch sử hội thoại". Danh sách hội thoại thường đã có ghim từ trước, còn thiếu hai chỗ:
  1. Kết quả TÌM của cột Lịch sử (trang Trò chuyện, lịch sử của trợ lý / Javis Core, trang Coding: cùng một cột
     `sessions-ui.js`) không có nút ghim, và server không trả trạng thái ghim của kết quả.
  2. Hòm thư bot (trang Hội thoại) chưa có ghim ở đâu cả.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-ghim-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_STATE) / "sessions.db")
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import conversations  # noqa: E402
import sessions  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


if _STATE not in str(conversations.DB_PATH):
    print(f"FAIL kho hòm thư không nằm trong thư mục tạm: {conversations.DB_PATH}. DỪNG.")
    sys.exit(1)

# ---- 1. Kết quả tìm hội thoại mang trạng thái ghim, cuộc đã ghim đứng trước ----
st = sessions.SessionStore(os.environ["JAVIS_SESSIONS_DB"])
cu = st.create_session(title="Đăng ký sở hữu trí tuệ")
st.append_message(cu, "user", "hỏi về sở hữu trí tuệ")
moi = st.create_session(title="Zoom sở khoa học")
st.append_message(moi, "user", "sở khoa học công nghệ tỉnh")
for fts in (True, False):
    st._fts_enabled = fts
    kq = st.search("sở", brain="brain")
    nhan = "FTS" if fts else "LIKE"
    check(f"[{nhan}] mỗi kết quả có trường pinned", kq and all("pinned" in h for h in kq), kq)
    check(f"[{nhan}] chưa ghim: pinned = 0", all(not h["pinned"] for h in kq), kq)
st.set_pinned(cu, True)
for fts in (True, False):
    st._fts_enabled = fts
    kq = st.search("sở", brain="brain")
    nhan = "FTS" if fts else "LIKE"
    check(f"[{nhan}] cuộc đã ghim đứng đầu kết quả tìm", kq and kq[0]["session_id"] == cu and kq[0]["pinned"] == 1,
          [(h["session_id"] == cu, h["pinned"]) for h in kq])
    check(f"[{nhan}] cuộc chưa ghim vẫn có trong kết quả", any(h["session_id"] == moi and not h["pinned"] for h in kq))

ui = (ROOT / "dashboard" / "sessions-ui.js").read_text(encoding="utf-8")
tim = ui[ui.index("async function doSearch"):ui.index("async function delSession")]
check("kết quả tìm vẽ nút ghim", '<span class="pin' in tim and 'ic("pin")' in tim)
check("hàng kết quả đã ghim có vạch ghim như danh sách", '(h.pinned ? " ghim" : "")' in tim)
check("bấm ghim không mở hội thoại", "ev.stopPropagation();" in tim)
check("ghim từ kết quả tìm thì tìm lại đúng câu đó", "togglePin({ id: h.session_id, pinned: h.pinned }, q);" in tim
      and "if (q) doSearch(q); else loadList();" in ui)
check("cả trang Trò chuyện, lịch sử trợ lý và Coding cùng dùng cột này",
      all("JavisChatSide.mount(" in (ROOT / "dashboard" / f).read_text(encoding="utf-8")
          for f in ("console.js", "workspace.js", "coding.js")))

# ---- 2. Hòm thư bot: kho cũ được thêm cột pinned ----
_cu = Path(_STATE) / "kho-cu.db"
db = sqlite3.connect(str(_cu))
db.executescript(conversations._SCHEMA)
db.execute("INSERT INTO conversations(channel_account_id, external_chat_id, title, created_at, updated_at)"
           " VALUES('x:1','c1','Cũ',1,1)")
db.commit()
db.close()
_goc = conversations.DB_PATH
conversations.DB_PATH = _cu
try:
    cot = {r[1] for r in conversations._conn().execute("PRAGMA table_info(conversations)").fetchall()}
    giu = conversations._conn().execute("SELECT title, pinned FROM conversations").fetchone()
    check("kho cũ có thêm cột pinned", "pinned" in cot, cot)
    check("dữ liệu cũ còn nguyên, chưa ghim", giu and giu["title"] == "Cũ" and giu["pinned"] == 0, giu and dict(giu))
finally:
    conversations.close()
    conversations.DB_PATH = _goc


# ---- 3. Hòm thư bot: ghim đưa cuộc chat lên đầu ----
def tin(chat, text, ten):
    return conversations.ghi_su_kien({
        "channel": "zalo_personal", "account_id": "zp1", "account_name": "Nick", "external_chat_id": chat,
        "chat_type": "private", "sender_type": "customer", "sender_id": chat, "sender_name": ten, "text": text})


a = tin("uid_a", "tin cũ", "An")["conversation_id"]
b = tin("uid_b", "tin mới", "Bình")["conversation_id"]
check("(chuẩn bị) mới nhất đứng đầu", [x["id"] for x in conversations.danh_sach()][:2] == [b, a])
truoc = conversations.chi_tiet(a)["updated_at"]
check("ghim được", conversations.dat_ghim(a, True))
ds = conversations.danh_sach()
check("cuộc đã ghim lên đầu dù cũ hơn", [x["id"] for x in ds][:2] == [a, b], [x["id"] for x in ds])
check("hàng danh sách mang pinned", ds[0]["pinned"] == 1 and ds[1]["pinned"] == 0)
check("ghim không đổi giờ cập nhật (không phải tin mới)", conversations.chi_tiet(a)["updated_at"] == truoc)
check("ghim cuộc không có: báo không thấy", not conversations.dat_ghim(99999, True))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)
r = cl.post(f"/conversations/{a}/pin", data={"pinned": "0"})
check("endpoint bỏ ghim", r.status_code == 200 and r.json()["conversation"]["pinned"] == 0, r.text)
check("bỏ ghim thì về lại thứ tự thời gian", [x["id"] for x in conversations.danh_sach()][:2] == [b, a])
r = cl.post(f"/conversations/{a}/pin", data={"pinned": "1"})
check("endpoint ghim", r.status_code == 200 and r.json()["conversation"]["pinned"] == 1, r.text)
check("danh sách qua API cũng xếp cuộc ghim trước",
      [x["id"] for x in cl.get("/conversations").json()["items"]][:1] == [a])
check("endpoint với id không có: 404", cl.post("/conversations/99999/pin", data={"pinned": "1"}).status_code == 404)

js = (ROOT / "dashboard" / "conversations.js").read_text(encoding="utf-8")
check("hàng hòm thư có nút ghim (span, không lồng button trong button)",
      '<span class="ht-pin' in js and 'role="button"' in js)
check("bấm ghim gọi đúng endpoint rồi tải lại danh sách",
      '"/conversations/" + id + "/pin"' in js and "tai(true);" in js[js.index("async function ghim"):])
check("bấm ghim không mở cuộc chat", 'closest(".ht-pin")) { e.stopPropagation(); ghim(x); return; }' in js)
css = (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8")
check("nút ghim luôn hiện trên màn cảm ứng", "@media (hover: none) { .ht-pin { opacity: .6;" in css)

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_ghim_hoi_thoai: all pass")
