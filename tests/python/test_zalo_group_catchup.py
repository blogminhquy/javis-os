"""Bill photos sent to tuition groups while the machine was off are read back once the read loop works again.

    python tests/run.py zalo_group_catchup      (no network, no MCP, temp state dir)

Guards (module comment of `zalo_group_catchup`): G1 photos only, G2 groups and switches, G3 bounded window and no baseline,
G4 no photo twice, G5 per-run cap, G6 oldest first, G7 a catch-up turn never speaks, G8 the age gate opens only for a
registered message, G9 kill switch, G10 stop when the bot goes off, G11 summary only to the bell.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zgc-")
os.environ.pop("JAVIS_ZALO_GROUP_CATCHUP", None)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_store  # noqa: E402
import conversations  # noqa: E402
import zalo_group_catchup as zgc  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels.zalo_personal import Transport  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


NOW = time.time()
HOME = tempfile.mkdtemp(prefix="javis-zgc-home-")
CONN = {"id": "zalo-1", "label": "Minh Quy", "connector_id": "zalo", "env": {"HOME": HOME}}
G1, G2, GX = "111", "222", "999"
BOT = {}
zc.ket_noi_theo_id = lambda cid: CONN if cid == "zalo-1" else None


def set_bot(**kw):
    BOT.clear()
    BOT.update({"id": "bot_x", "name": "Sunny", "enabled": True, "accept_group_images": True, "reply_when": "always",
                "groups": [G1, G2],
                "catchup_group_images": {"on": True, "group_ids": [G1, G2, GX], "max_hours": 2, "max_per_run": 30}})
    BOT.update(kw)


def url(n):
    return f"https://photo-stal-1.zdn.vn/jpg/{n}.jpg"


def photo(mid, chat, minutes_ago, caption="", sender="u1"):
    return {"msgId": str(mid), "threadId": chat, "threadType": "group", "senderId": sender, "senderName": "Phu huynh",
            "isSelf": False, "text": caption or url(mid),
            "timestamp": int((NOW - minutes_ago * 60) * 1000), "type": "chat.photo"}


def store_photo(mid, chat, minutes_ago):
    conversations.ghi_su_kien({
        "channel": "zalo_personal", "account_id": "zalo-1", "account_name": "Minh Quy", "external_chat_id": chat,
        "chat_type": "group", "chat_title": "Lop " + chat, "sender_type": "customer", "sender_id": "u1",
        "sender_name": "Phu huynh", "message_type": "image", "text": url(mid), "external_message_id": str(mid),
        "created_at": NOW - minutes_ago * 60, "metadata": {"image_url": url(mid)}}, dem_chua_doc=False, late=True)


class FakeTB:
    def __init__(self):
        self.cfg_fn = lambda: BOT
        self.seen = []
        self.registered_while_running = []

    async def xu_ly(self, ev):
        mid = ev["external_message_id"]
        self.seen.append(mid)
        self.registered_while_running.append(zgc.is_registered("zalo-1", mid))
        zgc.note("zalo-1", mid, answered=True)


# ---- T1: config
cc = chatbot_store.clean_catchup({"on": "true", "group_ids": ["1", 2, "x", "1", None, " 3 "], "max_hours": 999, "max_per_run": 0})
check("config: junk ids dropped, deduped, ranges clamped",
      cc == {"on": True, "group_ids": ["1", "2", "3"], "max_hours": 48, "max_per_run": 1}, cc)
check("config: default is off with no groups",
      chatbot_store.clean_catchup(None) == {"on": False, "group_ids": [], "max_hours": 24, "max_per_run": 30})
check("config: field is patchable", "catchup_group_images" in chatbot_store._PATCHABLE)

# ---- G2/G9: settings
set_bot()
tb = FakeTB()
zc._BOTS["zalo-1"] = tb
st = zgc.settings("zalo-1")
check("settings: groups = intersection with the bot's groups",
      bool(st) and st["chats"] == [G1, G2] and st["skipped_groups"] == [GX], st)
set_bot(catchup_group_images={"on": True, "group_ids": [], "max_hours": 2})
check("settings: empty group_ids = no scan", zgc.settings("zalo-1") is None)
set_bot(catchup_group_images={"on": False, "group_ids": [G1]})
check("settings: off = no scan", zgc.settings("zalo-1") is None)
set_bot(enabled=False)
check("settings: bot off = no scan", zgc.settings("zalo-1") is None)
set_bot(accept_group_images=False)
check("settings: group images off = no scan", zgc.settings("zalo-1") is None)
set_bot()
os.environ["JAVIS_ZALO_GROUP_CATCHUP"] = "0"
check("settings: env kill switch wins", zgc.settings("zalo-1") is None)
os.environ.pop("JAVIS_ZALO_GROUP_CATCHUP")
check("settings: back on after the switch is cleared", zgc.settings("zalo-1") is not None)

# ---- G3: window
check("window: no baseline = None", zgc.compute_window(CONN, NOW, 2) is None)
conversations.ghi_trang_thai("zalo_alive:zalo-1", str(int(NOW - 3600)))
w = zgc.compute_window(CONN, NOW, 2)
check("window: last heartbeat minus margin",
      bool(w) and abs(w[0] - (NOW - 3600 - zgc.ALIVE_MARGIN)) < 2 and w[1] == NOW, w)
conversations.ghi_trang_thai("zalo_alive:zalo-1", str(int(NOW - 30 * 3600)))
w = zgc.compute_window(CONN, NOW, 2)
check("window: clamped to max_hours", bool(w) and abs(w[0] - (NOW - 2 * 3600)) < 2, w)
os.makedirs(os.path.join(HOME, ".zalo-agent-cli"), exist_ok=True)
STATE = os.path.join(HOME, ".zalo-agent-cli", "sync-state.json")
with open(STATE, "w", encoding="utf-8") as f:
    json.dump({"gaps": [{"from": int((NOW - 5400) * 1000), "to": int((NOW - 60) * 1000), "recovered": True}]}, f)
conversations.ghi_trang_thai("zalo_alive:zalo-1", str(int(NOW - 600)))
w = zgc.compute_window(CONN, NOW, 2)
check("window: earliest of heartbeat and a recovered gap start", bool(w) and abs(w[0] - (NOW - 5400)) < 2, w)

# ---- G1: candidates
store_photo("A1", G1, 50)
store_photo("A2", GX, 50)                       # not in the filtered set
HIST = [photo("B1", G1, 40), photo("A1", G1, 50),                      # A1 duplicates route A
        photo("B2", G2, 30, caption="Be Na 3A nop hoc phi"),           # caption, no link: report only
        photo("B3", G1, 400),                                          # outside the window
        dict(photo("B4", G1, 20), isSelf=True),                        # own message
        dict(photo("B5", G1, 20), type="chat.text", text="chu thuong")]  # free text never enters


def hist_fn(c, chats, a, b):
    return [m for m in HIST if a <= m["timestamp"] / 1000 <= b and m["threadId"] in chats and m["type"] == "chat.photo"
            and not m["isSelf"]]


got = zgc.gather(CONN, [G1, G2], NOW - 3600, NOW, history_fn=hist_fn)
ids = [e["external_message_id"] for e in got["events"]]
check("gather: route A + B merged, oldest first, no duplicate", ids == ["A1", "B1"], ids)
check("gather: captioned photo without a link only reported", [x["msg_id"] for x in got["no_image"]] == ["B2"], got["no_image"])
check("gather: free text and own messages never enter", "B5" not in ids and "B4" not in ids)


def boom(*a):
    raise AssertionError("history read")


got_q = zgc.gather(CONN, [G1, G2], NOW - 10, NOW, quick=True, history_fn=boom)
check("gather: a quick restart skips the history file", got_q["events"] == [])


# ---- G4, G6: run
async def run(**kw):
    return await zgc.run_once("zalo-1", pause=0, notify=False, history_fn=hist_fn, **kw)


st1 = asyncio.run(run(reason="t", now=NOW, den=NOW, tu=NOW - 3600))
check("run: oldest first and registered only while the bot runs",
      tb.seen == ["A1", "B1"] and all(tb.registered_while_running), (tb.seen, tb.registered_while_running))
check("run: consumed afterwards", not zgc.is_registered("zalo-1", "A1") and not zgc._REG)
check("run: counts", st1["given"] == 2 and st1["found"] == 2 and len(st1["no_image"]) == 1, st1)
tb.seen.clear()
st2 = asyncio.run(run(reason="t2", now=NOW, den=NOW, tu=NOW - 3600))
check("run: second run gives nothing again (G4)", tb.seen == [] and st2["given"] == 0 and st2["duplicate"] == 2, st2)
zgc._DELIVERED.clear()
zgc._PENDING_FLUSH.clear()
tb.seen.clear()
asyncio.run(run(reason="t3", now=NOW, den=NOW, tu=NOW - 3600))
check("run: the done book survives a restart of RAM", tb.seen == [], tb.seen)

# ---- G5: cap
conversations.ghi_trang_thai("zalo_catchup_done:zalo-1", "{}")
zgc._DELIVERED.clear()
set_bot(catchup_group_images={"on": True, "group_ids": [G1, G2], "max_hours": 2, "max_per_run": 1})
tb.seen.clear()
st3 = asyncio.run(run(reason="cap", now=NOW, den=NOW, tu=NOW - 3600))
check("cap: only max_per_run photos, rest reported", tb.seen == ["A1"] and st3["skipped"].get("over_limit") == 1, st3)


# ---- G10: bot off midway
set_bot()
conversations.ghi_trang_thai("zalo_catchup_done:zalo-1", "{}")
zgc._DELIVERED.clear()


class StopTB(FakeTB):
    async def xu_ly(self, ev):
        await super().xu_ly(ev)
        BOT["enabled"] = False


tb2 = StopTB()
zc._BOTS["zalo-1"] = tb2
st4 = asyncio.run(run(reason="stop", now=NOW, den=NOW, tu=NOW - 3600))
check("stop: bot switched off midway ends the run",
      tb2.seen == ["A1"] and st4.get("skipped_run") == "stopped_midway", (tb2.seen, st4))
set_bot()
zc._BOTS["zalo-1"] = tb

# ---- no baseline -> nothing is read
conversations.ghi_trang_thai("zalo_alive:zalo-1", "0")
os.remove(STATE)
tb.seen.clear()
st5 = asyncio.run(zgc.run_once("zalo-1", reason="nb", now=NOW, den=NOW, pause=0, notify=False))
check("no baseline: nothing read, recorded", st5.get("skipped_run") == "no_baseline" and not tb.seen, st5)

# ---- G11: summary text
txt = zgc.summary_text(zgc.settings("zalo-1"), dict(st1, blocked_text=[{"msg_id": "B1", "text": "Da em chao chi"}]))
check("summary: counts, captioned photo and blocked text named", "2" in txt and "Be Na" in txt and "Da em chao chi" in txt, txt)
check("summary: no Zalo send path",
      "zalo_send" not in open(os.path.join(SERVER, "zalo_group_catchup.py"), encoding="utf-8").read())

# ---- G8, G7: the real Transport
sent = []


class T2(Transport):
    async def _gui(self, thread, cau, chat_type="private", meta=None):
        sent.append(("text", cau))

    async def _gui_anh(self, thread, anh, chat_type="private"):
        sent.append(("img", anh))


calls = []


async def answer(text, meta, _x):
    calls.append(dict(meta, _text=text))
    return {"text": "Da em chao chi", "files": []}


real = T2("zalo-1", [], answer, cfg_fn=lambda: BOT)
zc._BOTS["zalo-1"] = real


def mk_ev(mid, age=40000, md=None):
    return {"channel": "zalo_personal", "account_id": "zalo-1", "external_chat_id": G1, "chat_type": "group",
            "chat_title": "Lop", "sender_type": "customer", "sender_id": "u1", "sender_name": "Phu huynh",
            "message_type": "image", "text": url(mid), "external_message_id": mid, "created_at": time.time() - age,
            "metadata": md if md is not None else {"image_url": url(mid), "doc_bu": {"sent_at": 1}}}


asyncio.run(real.xu_ly(mk_ev("OLD1")))
check("gate: old photo with only a metadata flag is dropped (G8)", calls == [] and sent == [], (calls, sent))
zgc.register("zalo-1", "OLD2")
asyncio.run(real.xu_ly(mk_ev("OLD2")))
check("gate: registered old photo reaches the bot", len(calls) == 1 and calls[0].get("doc_bu") is True, calls)
zgc.flush("zalo-1")
check("done book: a photo whose turn finished is written down", "OLD2" in zgc._load_done("zalo-1"))


async def boom(text, meta, _x):
    raise RuntimeError("turn cut")


bad = T2("zalo-1", [], boom, cfg_fn=lambda: BOT)
zc._BOTS["zalo-1"] = bad
zgc.register("zalo-1", "OLD3")
try:
    asyncio.run(bad.xu_ly(mk_ev("OLD3")))
except RuntimeError:
    pass
zgc.flush("zalo-1")
check("done book: a turn cut midway is NOT written down, so it is read again", "OLD3" not in zgc._load_done("zalo-1"))
zc._BOTS["zalo-1"] = real
check("catch-up turn: marker with the send time in the note",
      bool(calls) and "Đọc bù" in str(calls[0].get("ghi_chu_dau")), calls[0].get("ghi_chu_dau") if calls else "")
check("catch-up turn: free text is NOT sent (G7)", sent == [], sent)
check("catch-up turn: blocked text reported",
      "Da em chao chi" in str(zgc.outcome("zalo-1", "OLD2").get("blocked_text")), zgc.outcome("zalo-1", "OLD2"))
zgc.consume("zalo-1", "OLD2")
asyncio.run(real.xu_ly(mk_ev("NEW1", age=5, md={"image_url": url("NEW1")})))
check("live message: unchanged, reply is sent", len(calls) == 2 and ("text", "Da em chao chi") in sent, (len(calls), sent))
check("live message: marked as delivered to the bot (G4 layer 2)", zgc.already_done("zalo-1", "NEW1", {}))
zc._BOTS.pop("zalo-1", None)


# ---- scheduling (T5)
async def sched():
    zc._BOTS["zalo-1"] = tb
    a = zgc.on_first_read("zalo-1", 100.0, delays=(3600, 7200))
    n_tasks = len(zgc._JOBS["zalo-1"]["tasks"])
    b = zgc.on_first_read("zalo-1", 100.0, delays=(3600, 7200))
    old = list(zgc._JOBS["zalo-1"]["tasks"])
    c = zgc.on_first_read("zalo-1", 200.0, delays=(3600, 7200))
    await asyncio.sleep(0)
    cancelled = all(t.cancelled() or t.cancelling() for t in old)
    zgc.cancel()
    await asyncio.sleep(0)
    return a, n_tasks, b, c, cancelled, bool(zgc._JOBS)


a, n, b, c, canc, left = asyncio.run(sched())
check("schedule: two timed scans, once per epoch", a and n == 2 and not b)
check("schedule: a new epoch cancels the old tasks", c and canc)
check("schedule: stop clears everything", not left)
zc._BOTS.pop("zalo-1", None)
check("schedule: no bot, no tasks", zgc.on_first_read("zalo-1", 300.0) is False)

check("no em dash", chr(0x2014) not in open(__file__, encoding="utf-8").read())

print()
if _fails:
    print(f"{len(_fails)} FAIL: " + ", ".join(_fails))
    sys.exit(1)
print("ALL PASS")
