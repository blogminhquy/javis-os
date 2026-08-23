"""Phiên Telegram phải TỰ XOAY thay vì phình vô hạn, và phải nhận diện được là kênh nào.

    python tests/run.py telegram_sessions        (KHÔNG mạng)

Bối cảnh: 0.9.244 nối Telegram vào kho phiên (xem `test_luu_luot_chat.py` - test đó lo phần
LƯU). Nhưng nối xong thì lộ ra vấn đề ngược lại. Trên dashboard người dùng tự bấm "+ Hội
thoại mới" nên phiên không bao giờ dài mãi; trên Telegram thì gần như KHÔNG AI gõ `/reset`,
nên một Chat ID gắn với một phiên là phiên đó dài vô tận chừng nào server chưa restart. Mở
ra đọc là kéo về cả nghìn tin, vì `openStoredSession` trong `dashboard/app.js` vẽ TOÀN BỘ
`sess.messages` không phân trang (nút "Xem thêm" ở thanh bên chỉ phân trang DANH SÁCH hội
thoại, không phân trang tin trong một cuộc).

Test này phủ đúng phần chữa đó:
  1. `sessions.py` - cột `channel` (mặc định 'web', tự migrate cho DB cũ) và `archive_stale`.
  2. `main.py::_tg_conv_sid` - luật xoay THẬT: giữ phiên khi còn nóng, sang phiên mới khi
     nghỉ lâu / chạm trần tin / phiên bị xoá trên dashboard.
  3. Ràng buộc kiến trúc: xoay chỉ đụng BẢN GHI, không đụng ngữ cảnh engine của phiên.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import os
import sqlite3
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="javis-tgsess-")
os.environ.setdefault("JAVIS_STATE_DIR", _TMP)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sessions import SessionStore  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def _store(name):
    return SessionStore(os.path.join(_TMP, name))


# ============================================================
# 1) Cột channel + archive_stale
# ============================================================
st = _store("chan.db")

sid_web = st.create_session(brain="brain", engine="cli", model="opus")
sid_tg = st.create_session(brain="brain", engine="cli", model="opus", channel="telegram")

check("phiên web mặc định channel='web'", st.get_session(sid_web)["channel"] == "web")
check("phiên Telegram giữ channel='telegram'", st.get_session(sid_tg)["channel"] == "telegram")

st.append_message(sid_tg, "user", "doanh thu hôm nay")
st.append_message(sid_tg, "assistant", "Hôm nay 12 đơn.")
rows = {r["id"]: r for r in st.list_sessions(limit=10)}
check("list_sessions trả về cột channel", "channel" in (rows.get(sid_tg) or {}))
check("list_sessions: channel phiên TG đúng", (rows.get(sid_tg) or {}).get("channel") == "telegram")
check("append_message vẫn đếm đúng msg_count", st.get_session(sid_tg)["msg_count"] == 2)

now = time.time()
st._write(lambda c: c.execute("UPDATE sessions SET updated_at=? WHERE id IN (?,?)",
                              (now - 40 * 86400, sid_tg, sid_web)))
check("archive_stale cất đúng 1 phiên", st.archive_stale("telegram", now - 30 * 86400) == 1)
check("archive_stale: phiên TG nguội đã archived", st.get_session(sid_tg)["archived"] == 1)
check("archive_stale KHÔNG đụng kênh web", st.get_session(sid_web)["archived"] == 0)

sid_fresh = st.create_session(brain="brain", channel="telegram")
check("archive_stale bỏ qua phiên còn nóng",
      st.archive_stale("telegram", now - 30 * 86400) == 0
      and st.get_session(sid_fresh)["archived"] == 0)

check("phiên đã cất KHÔNG hiện ở danh sách mặc định",
      sid_tg not in {r["id"] for r in st.list_sessions(limit=50)})
check("phiên đã cất vẫn lấy được khi xin kèm kho lưu",
      sid_tg in {r["id"] for r in st.list_sessions(limit=50, include_archived=True)})
check("phiên đã cất vẫn tìm được bằng search",
      any(h["session_id"] == sid_tg for h in st.search("doanh thu")))

# ---- DB CŨ (chưa có cột channel) phải tự migrate, không vỡ ----
con = sqlite3.connect(os.path.join(_TMP, "legacy.db"))
con.executescript("""
CREATE TABLE sessions (
    id TEXT PRIMARY KEY, title TEXT, brain TEXT NOT NULL DEFAULT 'brain',
    engine TEXT, model TEXT, cli_session_id TEXT,
    created_at REAL NOT NULL, updated_at REAL NOT NULL,
    msg_count INTEGER NOT NULL DEFAULT 0, parent_session_id TEXT,
    archived INTEGER NOT NULL DEFAULT 0);
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL,
    content TEXT, ts REAL NOT NULL, tool_calls_json TEXT);
INSERT INTO sessions (id, brain, created_at, updated_at) VALUES ('cu', 'brain', 1.0, 1.0);
""")
con.commit()
con.close()

st_old = _store("legacy.db")
check("DB cũ tự thêm cột channel", st_old.get_session("cu")["channel"] == "web")
check("DB cũ ghi tiếp được sau migrate",
      bool(st_old.create_session(brain="brain", channel="telegram")))


# ============================================================
# 2) Luật xoay thật trong main.py::_tg_conv_sid
# ============================================================
import main  # noqa: E402

rot = _store("rotate.db")
BRAIN = "brain"


def _sess_moi():
    """Phiên Telegram sống trong RAM, đúng hình dạng _tg_session() dựng ra."""
    return {"cli": None, "codex": None, "or": None,
            "last": None, "sent": set(), "brain": None}


def _lay(sess):
    return main._tg_conv_sid(rot, sess, BRAIN, "cli", "opus")


def _nghi(sid, giay):
    """Giả lập chat im lặng `giay` giây: lùi updated_at của phiên trong kho."""
    rot._write(lambda c: c.execute("UPDATE sessions SET updated_at=? WHERE id=?",
                                   (time.time() - giay, sid)))


sess = _sess_moi()
s1 = _lay(sess)
check("lượt đầu tạo được phiên", bool(s1))
check("phiên nhớ vào sess['sid'] để lượt sau nối tiếp", sess["sid"] == s1)
check("phiên Telegram gắn channel='telegram'", rot.get_session(s1)["channel"] == "telegram")
# Cột brain giữ KHOÁ CHUẨN (đường dẫn tuyệt đối) chứ không phải nguyên văn "brain" như
# trước - xem main.py::_brain_key và test_phien_telegram_hien_o_thanh_ben.py.
check("phiên ghi brain ở dạng khoá chuẩn",
      rot.get_session(s1)["brain"] == main._brain_key(BRAIN))
check("chat đang nóng thì DÙNG LẠI phiên cũ", _lay(sess) == s1)

# ---- Xoay theo NGHỈ LÂU ----
_nghi(s1, main._TG_CONV_IDLE_S - 60)
check("nghỉ chưa tới ngưỡng thì vẫn giữ phiên", _lay(sess) == s1)
_nghi(s1, main._TG_CONV_IDLE_S + 60)
s2 = _lay(sess)
check("nghỉ quá ngưỡng thì sang phiên MỚI", s2 != s1)
check("phiên mới cũng mang nhãn Telegram", rot.get_session(s2)["channel"] == "telegram")

# ---- Xoay theo ĐỘ DÀI ----
rot._write(lambda c: c.execute("UPDATE sessions SET msg_count=? WHERE id=?",
                               (main._TG_CONV_MAX_MSGS - 1, s2)))
check("chưa chạm trần tin nhắn thì giữ phiên", _lay(sess) == s2)
rot._write(lambda c: c.execute("UPDATE sessions SET msg_count=? WHERE id=?",
                               (main._TG_CONV_MAX_MSGS, s2)))
s3 = _lay(sess)
check("chạm trần tin nhắn thì sang phiên MỚI", s3 != s2)
check("phiên mới bắt đầu từ 0 tin (không phình tiếp)", rot.get_session(s3)["msg_count"] == 0)

# ---- Xoay KHÔNG được đụng ngữ cảnh engine: đó là cả lý do cách này chấp nhận được ----
sess["cli"] = "engine-gia"
sess["or"] = [{"role": "user", "content": "cũ"}]
rot._write(lambda c: c.execute("UPDATE sessions SET msg_count=? WHERE id=?",
                               (main._TG_CONV_MAX_MSGS, s3)))
s4 = _lay(sess)
check("xoay xong vẫn sang phiên mới", s4 != s3)
check("xoay KHÔNG đụng engine Claude CLI của phiên", sess["cli"] == "engine-gia")
check("xoay KHÔNG đụng lịch sử in-memory nhánh API", sess["or"] == [{"role": "user", "content": "cũ"}])

# ---- Phiên bị xoá trên dashboard ----
rot.delete(s4)
s5 = _lay(sess)
check("phiên bị xoá thì mở phiên mới, KHÔNG hồi sinh id cũ", s5 != s4)
check("không hồi sinh: id cũ vẫn không tồn tại", rot.get_session(s4) is None)

# ---- Hai chat khác nhau không lẫn phiên ----
sess_khac = _sess_moi()
check("chat khác có phiên RIÊNG", _lay(sess_khac) != s5)
check("chat cũ không bị đổi phiên vì chat mới", _lay(sess) == s5)

# ---- /reset và đổi brain: main đặt sess['sid'] = None, xoay phải tôn trọng ----
sess["sid"] = None
check("sess['sid'] bị xoá (/reset, đổi brain) thì sang phiên MỚI", _lay(sess) != s5)

# ---- Ngưỡng phải có thật và dương (đổi tên hằng số là test đỏ) ----
check("ngưỡng nghỉ là số dương", isinstance(main._TG_CONV_IDLE_S, int) and main._TG_CONV_IDLE_S > 0)
check("trần tin nhắn là số dương",
      isinstance(main._TG_CONV_MAX_MSGS, int) and main._TG_CONV_MAX_MSGS > 0)
check("ngưỡng cất kho là số dương",
      isinstance(main._TG_CONV_ARCHIVE_DAYS, int) and main._TG_CONV_ARCHIVE_DAYS > 0)

# ---- Cất kho chạy theo nhịp xoay, và chỉ nhắm kênh Telegram ----
cu = rot.create_session(brain=BRAIN, channel="telegram")
cu_web = rot.create_session(brain=BRAIN, channel="web")
rot._write(lambda c: c.execute("UPDATE sessions SET updated_at=? WHERE id IN (?,?)",
                               (time.time() - (main._TG_CONV_ARCHIVE_DAYS + 5) * 86400,
                                cu, cu_web)))
sess["sid"] = None
_lay(sess)   # một lần xoay → kéo theo một lần dọn
check("xoay kéo theo cất phiên Telegram nguội", rot.get_session(cu)["archived"] == 1)
check("cất kho không đụng phiên web nguội", rot.get_session(cu_web)["archived"] == 0)

print()
if _fails:
    print("FAILED (%d): %s" % (len(_fails), ", ".join(_fails)))
    sys.exit(1)
print("ALL PASS")
