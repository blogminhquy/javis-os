"""Two-way chat names between the inbox and the platform (owner, 27/11/2026).

    python tests/run.py inbox_rename_sync      (no network)

Owner: "khi người dùng sửa tên ở một nhóm hoặc tên của khách hàng trong Zalo thì phải đồng bộ ngược lên Javis, sửa ở
Javis thì đồng bộ về Zalo, có nút sửa tên trên chatbot của Javis, và kiểm tra các nền tảng chat khác". Guarded:

  1. The store keeps the channel's own name apart from the shown one (`channel_title`, `channel_name`): a rename made in
     Javis survives the channel repeating its old name and the owner's own replies echoing the shown title; a NEW name
     from the channel (a rename made over there) replaces it. An old store is seeded so nothing flips on upgrade.
  2. Group names read in bulk (the Zalo thread list) and Zalo friend aliases follow the same rule.
  3. The channel registry says which chats each platform can rename: Zalo groups (name) and friends (alias), Telegram
     groups (title); everything else in Javis only.
  4. The rename route renames on the platform first, keeps the name in Javis even when the platform refuses, and says why.
  5. Zalo: the alias list is parsed, and the quiet beat that reads it never spins the read loop.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sqlite3
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-rename-")

import conversations  # noqa: E402
import channels  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{str(extra)[:300]}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def run(c):
    return asyncio.run(c)


def ev(chat, **kw):
    base = {"channel": "zalo_personal", "account_id": "zalo-1", "external_chat_id": chat, "chat_type": "group",
            "sender_type": "customer", "sender_id": "u1", "sender_name": "Lan", "text": "hi"}
    base.update(kw)
    return conversations.ghi_su_kien(base)


def conv(cid):
    return conversations.chi_tiet(cid)


# ---- 0. An old store gets the new columns seeded with what it shows ----
old_db = conversations.DB_PATH
conversations.close()
old_db.parent.mkdir(parents=True, exist_ok=True)
raw = sqlite3.connect(str(old_db))
raw.executescript(conversations._SCHEMA)
raw.execute("INSERT INTO channel_accounts(id, channel, external_account_id, created_at, updated_at)"
            " VALUES('zalo_personal:zalo-1','zalo_personal','zalo-1',1,1)")
raw.execute("INSERT INTO customers(channel_account_id, external_user_id, name, created_at, updated_at)"
            " VALUES('zalo_personal:zalo-1','old-u','Old Person',1,1)")
raw.execute("INSERT INTO conversations(channel_account_id, external_chat_id, chat_type, title, created_at, updated_at)"
            " VALUES('zalo_personal:zalo-1','old-g','group','Old Group',1,1)")
raw.commit()
raw.close()
db = conversations._conn()
r = db.execute("SELECT title, channel_title FROM conversations WHERE external_chat_id='old-g'").fetchone()
k = db.execute("SELECT name, channel_name FROM customers WHERE external_user_id='old-u'").fetchone()
check("upgrade: channel_title and channel_name start as what is shown", r["channel_title"] == "Old Group" and
      k["channel_name"] == "Old Person", (dict(r), dict(k)))

# ---- 1. Groups: the last rename wins, wherever it was made ----
g = ev("g1", chat_title="Nhóm A")["conversation_id"]
check("a new group takes the channel's name", conv(g)["title"] == "Nhóm A" and conv(g)["channel_title"] == "Nhóm A")
conversations.rename_conversation(g, "Khách sỉ")
ev("g1", chat_title="Nhóm A", text="again")
check("renamed in Javis only: the channel repeating its old name does not undo it", conv(g)["title"] == "Khách sỉ",
      conv(g)["title"])
ev("g1", chat_title="Khách sỉ", sender_type="human", sender_id="", sender_name="Bạn", text="owner reply")
check("the owner's reply echoing the shown title is no rename either", conv(g)["title"] == "Khách sỉ" and
      conv(g)["channel_title"] == "Nhóm A", (conv(g)["title"], conv(g)["channel_title"]))
ev("g1", chat_title="Nhóm B", text="renamed on Zalo")
check("renamed on the platform: the new name comes back to Javis", conv(g)["title"] == "Nhóm B" and
      conv(g)["channel_title"] == "Nhóm B", conv(g)["title"])
conversations.rename_conversation(g, "Nhóm C", channel_title="Nhóm C")
ev("g1", chat_title="Nhóm C", text="after a pushed rename")
check("renamed in Javis AND on the platform: both sides agree", conv(g)["title"] == "Nhóm C" and
      conv(g)["channel_title"] == "Nhóm C")
check("an empty name is refused", conversations.rename_conversation(g, "  ") is False and conv(g)["title"] == "Nhóm C")
check("no such conversation", conversations.rename_conversation(999999, "X") is False)

# ---- 2. A person: the chat title and the customer's name move together ----
p = ev("u9", chat_type="private", sender_id="u9", sender_name="Lan Nguyen")["conversation_id"]
check("a private chat is named after the person", conv(p)["title"] == "Lan Nguyen" and conv(p)["customer_name"] == "Lan Nguyen")
conversations.rename_conversation(p, "Chị Lan VIP")
check("renaming a private chat renames its customer", conv(p)["customer_name"] == "Chị Lan VIP")
ev("u9", chat_type="private", sender_id="u9", sender_name="Lan Nguyen", text="next")
check("her next message (same display name) keeps the owner's name", conv(p)["title"] == "Chị Lan VIP" and
      conv(p)["customer_name"] == "Chị Lan VIP", (conv(p)["title"], conv(p)["customer_name"]))
ev("u9", chat_type="private", sender_id="u9", sender_name="Lan Shop", text="she renamed herself")
check("she changes her own name on the platform: Javis follows", conv(p)["title"] == "Lan Shop" and
      conv(p)["customer_name"] == "Lan Shop", (conv(p)["title"], conv(p)["customer_name"]))

# ---- 3. Group names read in bulk ----
conversations.rename_conversation(g, "Đổi trong Javis")
changed = conversations.sync_group_titles("zalo_personal", "zalo-1", {"g1": "Nhóm C", "nope": "X", "old-g": "?"})
check("bulk: the list repeating the platform's name changes nothing", changed == [] and conv(g)["title"] == "Đổi trong Javis",
      (changed, conv(g)["title"]))
changed = conversations.sync_group_titles("zalo_personal", "zalo-1", {"g1": "Đổi trên Zalo"})
check("bulk: a new name renames the group", changed == [g] and conv(g)["title"] == "Đổi trên Zalo" and
      conv(g)["channel_title"] == "Đổi trên Zalo")
check("bulk: a private chat is never renamed by the group list",
      conversations.sync_group_titles("zalo_personal", "zalo-1", {"u9": "Whatever"}) == [] and conv(p)["title"] == "Lan Shop")

# ---- 4. Zalo friend aliases ----
q = ev("u7", chat_type="private", sender_id="u7", sender_name="Minh")["conversation_id"]
changed = conversations.sync_aliases("zalo_personal", "zalo-1", {"u7": "Anh Minh kho"})
check("alias set on Zalo: the chat and the customer take it", q in changed and conv(q)["title"] == "Anh Minh kho" and
      conv(q)["customer_name"] == "Anh Minh kho" and conv(q)["metadata"].get("channel_alias") == "Anh Minh kho")
ev("u7", chat_type="private", sender_id="u7", sender_name="Minh", text="hello")
check("his messages (own display name) keep the alias", conv(q)["title"] == "Anh Minh kho")
conversations.rename_conversation(q, "Minh (Javis)")
check("same alias list again: a rename made in Javis meanwhile stays",
      conversations.sync_aliases("zalo_personal", "zalo-1", {"u7": "Anh Minh kho"}) == [] and conv(q)["title"] == "Minh (Javis)")
conversations.sync_aliases("zalo_personal", "zalo-1", {"u7": "Minh giao hàng"})
check("alias changed on Zalo: it comes back to Javis", conv(q)["title"] == "Minh giao hàng")
conversations.sync_aliases("zalo_personal", "zalo-1", {})
check("alias removed on Zalo: back to the name his messages carry", conv(q)["title"] == "Minh" and
      conv(q)["customer_name"] == "Minh" and "channel_alias" not in conv(q)["metadata"], conv(q)["title"])
conversations.rename_conversation(q, "Minh mới", alias="Minh mới")
check("a rename pushed as an alias is remembered, so the next list does not undo it",
      conversations.sync_aliases("zalo_personal", "zalo-1", {"u7": "Minh mới"}) == [] and conv(q)["title"] == "Minh mới")

# ---- 5. Which platforms can rename what ----
check("Zalo personal: groups by name, people by alias", channels.rename_kind("zalo_personal", "group") == "title" and
      channels.rename_kind("zalo_personal", "private") == "alias")
check("Telegram: groups only", channels.rename_kind("telegram", "group") == "title" and
      channels.rename_kind("telegram", "private") == "")
check("Messenger, Zalo OA, Zalo Bot, Slack, WhatsApp: Javis only",
      all(channels.rename_kind(ch, t) == "" for ch in ("messenger", "zalo_oa", "zalo", "slack", "whatsapp")
          for t in ("group", "private")))
check("the inbox row says how it renames", conv(g)["rename_remote"] == "title" and conv(q)["rename_remote"] == "alias")

# ---- 6. The route: platform first, Javis always ----
try:
    import routes.conversations as rc
except Exception as e:      # noqa: BLE001
    rc = None
    check("routes.conversations imports", False, e)
if rc:
    calls = []
    real = channels.rename

    async def fake_ok(kenh, tk, chat_id, name, chat_type="private"):
        calls.append((kenh, tk.get("id"), chat_id, name, chat_type))
        return True, ""

    async def fake_no(kenh, tk, chat_id, name, chat_type="private"):
        return False, "not a friend"
    channels.rename = fake_ok
    try:
        r = run(rc.rename_conversation(g, "  Nhóm   mới  "))
        check("route: group renamed on Zalo, spaces tidied, the platform's name remembered",
              r["ok"] and r["remote"] and r["kind"] == "title" and calls[-1] == ("zalo_personal", "zalo-1", "g1", "Nhóm mới", "group")
              and conv(g)["title"] == "Nhóm mới" and conv(g)["channel_title"] == "Nhóm mới", (r, calls))
        n = len(calls)
        r = run(rc.rename_conversation(g, "Nhóm mới"))
        check("route: the same name asks nothing of the platform", r["ok"] and r.get("unchanged") and len(calls) == n)
        r = run(rc.rename_conversation(q, "Minh VIP"))
        check("route: a Zalo friend gets an alias", r["remote"] and r["kind"] == "alias" and
              conv(q)["metadata"].get("channel_alias") == "Minh VIP")
        channels.rename = fake_no
        r = run(rc.rename_conversation(p, "Chị Lan"))
        check("route: the platform refuses, Javis keeps the name and says why", r["ok"] and not r["remote"] and
              "not a friend" in r["warning"] and conv(p)["title"] == "Chị Lan" and
              "channel_alias" not in conv(p)["metadata"], r)
        m = ev("fb1", channel="messenger", account_id="page", chat_type="private", sender_id="fb1", sender_name="An")
        called = []

        async def never(*a, **kw):
            called.append(a)
            return True, ""
        channels.rename = never
        r = run(rc.rename_conversation(m["conversation_id"], "Anh An"))
        check("route: Messenger renames in Javis only, the platform is never asked", r["ok"] and not r["remote"] and
              not r["warning"] and not called and conv(m["conversation_id"])["title"] == "Anh An", r)
        check("route: empty and too long names are refused",
              run(rc.rename_conversation(g, " "))["code"] == "empty" and
              run(rc.rename_conversation(g, "x" * (conversations.MAX_TEN + 1)))["code"] == "too_long")
        check("route: unknown conversation", run(rc.rename_conversation(424242, "x"))["code"] == "not_found")
    finally:
        channels.rename = real

# ---- 7. Telegram explains a refusal ----
import channels.telegram as tg  # noqa: E402


class _Resp:
    status_code = 400
    content = b"x"

    def json(self):
        return {"ok": False, "description": "Bad Request: not enough rights to change chat title"}


class _Client:
    def __init__(self, *a, **kw):
        self.sent = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        _Client.last = (url, json)
        return _Resp()


import httpx  # noqa: E402
real_client = httpx.AsyncClient
httpx.AsyncClient = _Client
try:
    ok, err = run(tg.rename({"token": "123:abc"}, "-100", "Tên mới", "group"))
finally:
    httpx.AsyncClient = real_client
check("Telegram: setChatTitle with the new title", _Client.last[0].endswith("/setChatTitle") and
      _Client.last[1] == {"chat_id": "-100", "title": "Tên mới"}, _Client.last)
check("Telegram: not an admin is said plainly", not ok and ("admin" in err or "quản trị" in err), err)

# ---- 8. Zalo: alias list and the quiet beat ----
import zalo_personal_channel as zc  # noqa: E402
check("alias page parsed, empty rows dropped",
      zc.parse_alias_page({"items": [{"userId": "1", "alias": "A"}, {"userId": "2", "alias": ""}, {"x": 1}]}) == [("1", "A")]
      and zc.parse_alias_page(None) == [])
zc._TT["zalo-1"] = {"ten": {"g1": {"name": "Cũ", "type": "group"}}, "aliases": {}}
zc.note_thread_name("zalo-1", "g1", "Mới")
zc.note_alias("zalo-1", "u7", "Minh")
check("after a rename the reader's own tables carry the new name at once",
      zc._TT["zalo-1"]["ten"]["g1"] == {"name": "Mới", "type": "group"} and zc._TT["zalo-1"]["aliases"]["u7"] == "Minh")
zc._TT.clear()

real_push = zc.push_active
zc.push_active = lambda cid: True
try:
    now = 1000.0
    zc._TT["c1"] = {"alias_due": now - 50, "doc_toi": now + 18}
    w = zc._loop_wait([{"id": "c1"}], {"c1"}, now=now)
    check("a due alias beat waits for the account's next turn, never spins the loop", w is not None and w >= 17, w)
    zc._TT["c1"] = {"alias_due": now + 600}
    check("a pushing account with nothing else to do still wakes for the alias beat",
          abs(zc._loop_wait([{"id": "c1"}], {"c1"}, now=now) - 600) < 1)
    zc._TT["c1"] = {}
    check("before the first beat: sleep until woken, as before", zc._loop_wait([{"id": "c1"}], {"c1"}, now=now) is None)
finally:
    zc.push_active = real_push
    zc._TT.clear()

seen = {}


async def fake_read(conn):
    return {"u7": "Alias X"}
real_read, real_sync = zc.read_aliases, conversations.sync_aliases
zc.read_aliases = fake_read
conversations.sync_aliases = lambda ch, acc, al: seen.update({"args": (ch, acc, al)}) or []
try:
    tt = {}
    run(zc._alias_turn({"id": "zalo-1", "label": "Z"}, tt, now=5000.0))
    first = dict(seen)
    seen.clear()
    run(zc._alias_turn({"id": "zalo-1", "label": "Z"}, tt, now=5100.0))
    check("alias beat: reads, syncs, then waits ALIAS_TTL", first.get("args") == ("zalo_personal", "zalo-1", {"u7": "Alias X"})
          and tt["alias_due"] == 5000.0 + zc.ALIAS_TTL and not seen, (first, tt))

    async def broken(conn):
        return None
    zc.read_aliases = broken
    tt = {}
    run(zc._alias_turn({"id": "zalo-1", "label": "Z"}, tt, now=7000.0))
    check("alias beat: a failed read syncs nothing (never a partial list) and retries later",
          not seen and tt["alias_due"] == 7000.0 + zc.ALIAS_RETRY)
finally:
    zc.read_aliases, conversations.sync_aliases = real_read, real_sync



async def _started():
    tt = {"alias_due": 0}
    calls = []

    async def slow(conn, tt2, now=None):
        calls.append(now)
        await asyncio.sleep(0.2)
    real_turn = zc._alias_turn
    zc._alias_turn = slow
    try:
        t0 = asyncio.get_running_loop().time()
        zc._start_alias_turn({"id": "z"}, tt, now=10.0)
        zc._start_alias_turn({"id": "z"}, tt, now=11.0)        # still running: not started twice
        quick = asyncio.get_running_loop().time() - t0 < 0.1
        await tt["alias_task"]
        return quick, calls
    finally:
        zc._alias_turn = real_turn
quick, started = run(_started())
check("alias beat runs beside the read loop, never twice at once", quick and started == [10.0], (quick, started))
fresh = {}
zc._start_alias_turn({"id": "z"}, fresh, now=100.0)
check("an account's first alias read waits ALIAS_FIRST seconds (javis-zalo is still starting)",
      fresh.get("alias_due") == 100.0 + zc.ALIAS_FIRST and "alias_task" not in fresh, fresh)

# ---- 9. No em or en dash in what this change wrote ----
import pathlib  # noqa: E402
bad = [f for f in ("server/conversations.py", "server/channels/__init__.py", "server/channels/telegram.py",
                   "server/channels/zalo_personal.py", "tests/python/test_inbox_rename_sync.py")
       if any(ch in (pathlib.Path(ROOT) / f).read_text(encoding="utf-8") for ch in (chr(0x2014), chr(0x2013)))]
check("no em or en dash in the touched files", not bad, bad)

conversations.close()
if fails:
    print(f"\nFAILED {len(fails)}: " + " | ".join(fails))
    raise SystemExit(1)
print("\nOK - test_inbox_rename_sync: all pass")
