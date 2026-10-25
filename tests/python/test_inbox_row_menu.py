"""Bot inbox row menu, server side (owner, 2026-10-25: a "..." menu on each conversation, like Zalo's).

    python tests/run.py inbox_row_menu      (no network)

Pins what the menu needs from the store and the routes:
  1. Mark unread brings the unread count back (at least 1, a real count is kept); opening (read) clears it again.
  2. Hide takes a conversation out of the inbox list; the "hidden" filter shows exactly the hidden ones; a search
     still finds them; unhide brings it back.
  3. Counts: every facet (and so "All bots (N)") and the unread tab badge leave hidden chats out; `status.hidden`
     counts them once.
  4. A NEW customer message unhides the chat (a customer is never missed); a bot or owner message, or an old message
     imported from history, does not.
  5. An existing store without the column is upgraded in place.
  6. The routes /unread and /hide, and the list route's hidden handling.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-inbox-menu-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_STATE) / "sessions.db")
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import conversations  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


if _STATE not in str(conversations.DB_PATH):
    print(f"FAIL the inbox store is not in the temp dir: {conversations.DB_PATH}. STOP.")
    sys.exit(1)


def msg(chat, text, sender="customer", ts=None, count_unread=True):
    ev = {"channel": "zalo_personal", "account_id": "zp1", "account_name": "Nick", "external_chat_id": chat,
          "chat_type": "private", "sender_type": sender, "sender_id": ("u" + chat) if sender == "customer" else "",
          "sender_name": "Khách " + chat, "text": text}
    if ts:
        ev["created_at"] = ts
    r = conversations.ghi_su_kien(ev, dem_chua_doc=count_unread)
    assert r["ok"], r
    return r["conversation_id"]


def row(cid):
    return conversations.chi_tiet(cid)


def ids(**kw):
    return {r["id"] for r in conversations.danh_sach(limit=100, **kw)}


a = msg("a", "chào shop", ts=1000)
b = msg("b", "hỏi giá", ts=1001)
msg("b", "thêm câu nữa", ts=1002)
c = msg("c", "ok", ts=1003)
conversations.danh_dau_da_doc(a)
conversations.danh_dau_da_doc(c)

# ---- 1. mark unread / read ----
check("a fresh store has the hidden column, every chat visible", row(a)["hidden"] == 0 and row(b)["hidden"] == 0)
check("mark unread on a read chat: count 1", conversations.mark_unread(a) and row(a)["unread_count"] == 1)
check("mark unread keeps a real count", conversations.mark_unread(b) and row(b)["unread_count"] == 2)
check("marked unread shows in the unread filter", ids(status="unread") == {a, b})
before = row(a)["updated_at"]
conversations.mark_unread(a)
check("mark unread is not 'new activity' (updated_at untouched)", row(a)["updated_at"] == before)
check("opening the chat (read) clears it again", conversations.danh_dau_da_doc(a) and row(a)["unread_count"] == 0)
check("mark unread on a missing chat: False", not conversations.mark_unread(99999))

# ---- 2. hide / unhide ----
check("hide", conversations.set_hidden(b, True) and row(b)["hidden"] == 1)
check("the inbox list leaves it out", ids(hidden="exclude") == {a, c})
check("the hidden filter shows only it", ids(hidden="only") == {b})
check("other callers (no flag) still see every chat", ids() == {a, b, c})
check("the bot form's chat picker still sees it", b in {r["id"] for r in conversations.cuoc_chat_cua_tai_khoan("zalo_personal", "zp1")})
check("hidden + status combine: unread hidden chat in the hidden filter", ids(hidden="only", status="unread") == {b})
check("hide a missing chat: False", not conversations.set_hidden(99999, True))

# ---- 3. counts ----
f = conversations.dem_bo_loc()
check("facets leave hidden chats out ('All bots' matches the list)", f["tong"] == 2, f)
check("unread count leaves the hidden unread chat out", f["status"]["unread"] == 0, f["status"])
check("hidden chats are counted once, for the filter option", f["status"]["hidden"] == 1, f["status"])
check("per-bot and per-type counts leave it out too", sum(x["tong"] for x in f["bots"].values()) == 2
      and f["type"]["private"] == 2, f)
st = conversations.thong_ke()
check("unread tab badge leaves the hidden chat out", st["chua_doc"] == 0, st)
check("channel filter counts leave it out", st["theo_kenh"].get("zalo_personal") == 2, st["theo_kenh"])
check("a bot card's total still counts every conversation", st["tong"] == 3, st)

# ---- 4. a new customer message unhides ----
msg("b", "bot đây", sender="ai", ts=1004)
check("a bot message leaves it hidden", row(b)["hidden"] == 1)
msg("b", "dạ shop gửi", sender="human", ts=1005)
check("an owner message leaves it hidden", row(b)["hidden"] == 1)
msg("b", "tin cũ nhập lại", ts=900, count_unread=False)
check("an old message imported from history leaves it hidden", row(b)["hidden"] == 1)
msg("b", "shop ơi còn hàng không", ts=1006)
check("a NEW customer message unhides it", row(b)["hidden"] == 0 and b in ids(hidden="exclude"))
check("and it is unread again", row(b)["unread_count"] >= 1)
conversations.set_hidden(c, True)
conversations.set_hidden(c, False)
check("unhide brings it back", row(c)["hidden"] == 0 and ids(hidden="only") == set())

# ---- 5. an old store is upgraded in place ----
old = Path(_STATE) / "old-store.db"
db = sqlite3.connect(str(old))
db.executescript(conversations._SCHEMA.split("CREATE TABLE IF NOT EXISTS inbox_tags")[0])
db.execute("INSERT INTO channel_accounts(id, channel, external_account_id, created_at, updated_at)"
           " VALUES('zalo_personal:z','zalo_personal','z',1,1)")
db.execute("INSERT INTO conversations(channel_account_id, external_chat_id, title, created_at, updated_at)"
           " VALUES('zalo_personal:z','c1','Old',1,1)")
db.commit()
db.close()
_orig = conversations.DB_PATH
conversations.DB_PATH = old
try:
    cx = conversations._conn()
    cols = {r[1] for r in cx.execute("PRAGMA table_info(conversations)").fetchall()}
    check("old store gets the hidden column, old chats visible", "hidden" in cols
          and cx.execute("SELECT hidden FROM conversations").fetchone()[0] == 0, cols)
    conversations.close()
    cx = conversations._conn()
    check("reopening the upgraded store is a no-op", cx.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 1)
finally:
    conversations.close()
    conversations.DB_PATH = _orig

# ---- 6. routes ----
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)
r = cl.post(f"/conversations/{a}/unread")
check("POST /unread", r.status_code == 200 and r.json()["conversation"]["unread_count"] == 1, r.text)
check("POST /unread on a missing chat: 404", cl.post("/conversations/99999/unread").status_code == 404)
check("POST /read clears it", cl.post(f"/conversations/{a}/read").status_code == 200 and row(a)["unread_count"] == 0)
r = cl.post(f"/conversations/{a}/hide", data={"hidden": "1"})
check("POST /hide hides", r.status_code == 200 and r.json()["conversation"]["hidden"] == 1, r.text)
lst = cl.get("/conversations").json()
check("the list route leaves hidden chats out by default", a not in [x["id"] for x in lst["items"]]
      and lst["facets"]["status"]["hidden"] == 1 and lst["facets"]["tong"] == 2, lst["facets"])
hid = cl.get("/conversations?status=hidden").json()
check("status=hidden lists exactly the hidden chats, flagged", [x["id"] for x in hid["items"]] == [a]
      and hid["items"][0]["hidden"] == 1, hid["items"])
found = cl.get("/conversations?q=" + "Khách a").json()
check("a search still finds a hidden chat", a in [x["id"] for x in found["items"]], [x["id"] for x in found["items"]])
check("other filters keep leaving it out", a not in [x["id"] for x in cl.get("/conversations?status=need_reply").json()["items"]])
r = cl.post(f"/conversations/{a}/hide", data={"hidden": "0"})
check("POST /hide hidden=0 unhides", r.status_code == 200 and r.json()["conversation"]["hidden"] == 0
      and a in [x["id"] for x in cl.get("/conversations").json()["items"]], r.text)
check("POST /hide on a missing chat: 404", cl.post("/conversations/99999/hide", data={"hidden": "1"}).status_code == 404)

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_inbox_row_menu: all pass")
