"""Personal Zalo: accept friend requests and keep the introduction they carry (0.172.0, server/zalo_friend_intake.py).

    python tests/run.py zalo_ket_ban      (no network, fake CLI and MCP)

The MTM owner asked (2026-10-15): when the bot accepts a friend request it must read the message sent with it and keep
it; someone who already introduced themselves is not asked again, someone who did not is asked. The message only exists
while the request is pending, so before this nobody ever saw it.

The maintainer's review of PR #657 added the rest: a round runs in its own task and never stalls the read loop, a
refused request backs off instead of blocking newer ones, polling is once an hour, nothing is accepted outside
active hours or for a bot that answers only chosen people, intro text is capped, Inbox text is localized, and the form
shows the switch only for a personal Zalo account.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import datetime
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpkb-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402,F401
import chatbot_store  # noqa: E402
import conversations  # noqa: E402
import localefmt  # noqa: E402
import zalo_cli  # noqa: E402
import zalo_friend_intake as fi  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CONN = {"id": "zalo-1", "label": "Toán Thầy Thành", "connector_id": "zalo", "env": {"HOME": "/state/zalo-a"}}
CLI = []            # every CLI call: (command, positionals, home, timeout)
LUOT = []           # every bot turn (text, meta)
GUI = []
READS = [0]         # zalo_get_messages calls (the read loop is alive)
STATE = {"requests": [], "accept_fail": set(), "stall": 0.0, "raise": False}


def req(uid, name, message, t, kind=2):
    return {"dataInfo": {"userId": uid, "displayName": name, "recommType": kind, "recommTime": t,
                         "recommInfo": {"message": message}}}


async def fake_run_cli(conn, command, positionals=None, options=None, timeout=120):
    CLI.append((list(command), list(positionals or []), conn.get("home"), timeout))
    if STATE["raise"]:
        raise RuntimeError("CLI exploded")
    if STATE["stall"]:
        # Like zalo_cli.run: the process is killed at `timeout` and a timeout error comes back.
        await asyncio.sleep(min(STATE["stall"], timeout))
        STATE["stall_done"] = STATE.get("stall_done", 0) + 1
        if STATE["stall"] >= timeout:
            return False, None, f"Zalo quá {timeout} {zalo_cli.TIMEOUT_MARK}"
    if command == ["friend", "recommendations"]:
        return True, {"recommItems": list(STATE["requests"])}, ""
    if command == ["friend", "accept"]:
        uid = (positionals or [""])[0]
        if uid in STATE["accept_fail"]:
            return False, None, "Zalo từ chối"
        STATE["requests"] = [r for r in STATE["requests"] if r["dataInfo"]["userId"] != uid]
        return True, {"ok": True}, ""
    return False, None, "unexpected"


async def fake_goi(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        return {"threads": []}
    if tool == "zalo_get_messages":
        READS[0] += 1
        return {"messages": [], "nextCursor": "1"}
    return {}


zalo_cli.run_cli = fake_run_cli
fi.ACCEPT_GAP = 0
zc._ket_noi = lambda: [dict(CONN)]
zc._goi = fake_goi
_start_that = zc.start
zc.start = lambda: True


async def _answer(text, meta, progress):
    LUOT.append((text, dict(meta)))
    return {"text": "Dạ em đã nhận được thông tin rồi ạ.", "files": []}


def lam_bot(cfg):
    return zp.Transport("zalo-1", [], _answer, cfg_fn=lambda: cfg)


async def xa():
    zc.xa_hang_cho("zalo-1", time.time() + 30)
    await asyncio.sleep(0.3)


def tin_hop_thu(uid):
    ds = conversations.danh_sach(limit=50)
    for c in (ds.get("items") if isinstance(ds, dict) else ds) or []:
        if c.get("external_chat_id") == uid:
            return [m.get("text") for m in conversations.tin_nhan(c["id"], limit=20) or []]
    return None


def reset():
    fi._poll.clear()
    fi._fails.clear()
    CLI.clear()
    STATE.update({"accept_fail": set(), "stall": 0.0, "raise": False, "stall_done": 0})


async def luot():
    """One round the way the read loop starts it: `start_round`, then wait for its task."""
    started = fi.start_round(dict(CONN))
    t = fi._tasks.get("zalo-1")
    if t:
        await t
    return started


def accepts():
    return [c[1][0] for c in CLI if c[0] == ["friend", "accept"]]


async def read_loop(seconds):
    """Run the real read loop (`_vong`) with a short beat for `seconds`; returns how many reads it made."""
    nhip_cu = (zc.NHIP, zc.NHIP_NHANH)
    zc.NHIP, zc.NHIP_NHANH = 0.1, 0.05
    READS[0] = 0
    try:
        zc._TT.pop("zalo-1", None)
        _start_that()
        await asyncio.sleep(seconds)
    finally:
        zc.stop()
        zc.NHIP, zc.NHIP_NHANH = nhip_cu
    return READS[0]


async def chay():
    # ---- settings -------------------------------------------------------------------------------------
    bid, err = chatbot_store.create_bot({"name": "Bot", "agent_slug": "tro-ly", "brain": "b", "channel": "zalo_personal"})
    check("new bot: intake OFF by default (accepting friends acts under the owner's name)",
          not err and chatbot_store.get_bot(bid).get("nhan_ket_ban") is False, err)
    chatbot_store.update_bot(bid, {"nhan_ket_ban": "1"})
    check("switch on from the form", chatbot_store.get_bot(bid)["nhan_ket_ban"] is True)
    chatbot_store.update_bot(bid, {"nhan_ket_ban": "0"})
    check("switch off again", chatbot_store.get_bot(bid)["nhan_ket_ban"] is False)
    check("Transport reads the live setting", lam_bot({"nhan_ket_ban": True}).nhan_ket_ban()
          and not lam_bot({}).nhan_ket_ban() and lam_bot({"nhan_ket_ban": "1"}).nhan_ket_ban())

    # ---- parsing and caps (point 5) ---------------------------------------------------------------------
    rs = fi.received_requests({"recommItems": [req("u2", "B", "", 20), req("u9", "Gợi ý", "", 5, kind=1), req("u1", "A", "hi", 10)]})
    check("only received requests (type 2), oldest first; Zalo suggestions (type 1) ignored",
          [r["uid"] for r in rs] == ["u1", "u2"] and rs[0]["message"] == "hi", rs)
    rs = fi.received_requests({"recommItems": [req("u3", "N" * 5000, "x" * 20000, 1)]})
    check("untrusted message capped at MAX_INTRO, name at MAX_NAME",
          len(rs[0]["message"]) == fi.MAX_INTRO == 500 and len(rs[0]["name"]) == fi.MAX_NAME, (len(rs[0]["message"]), len(rs[0]["name"])))
    ev = fi.intro_event(dict(CONN), {"uid": "u3", "name": "N" * 5000, "message": "x" * 20000, "time": 1})
    check("the inbox event is capped too, even when handed an uncapped request",
          ev["text"].count("x") == fi.MAX_INTRO and len(ev["sender_name"]) == fi.MAX_NAME
          and len(ev["metadata"]["intro"]) == fi.MAX_INTRO)

    # ---- Inbox text follows the interface language (point 6) -------------------------------------------
    tok = localefmt._UI_YEU_CAU.set("vi")
    vi_msg, vi_none = fi.intro_text("Chị là Lan"), fi.intro_text("")
    localefmt._UI_YEU_CAU.reset(tok)
    tok = localefmt._UI_YEU_CAU.set("en")
    en_msg, en_none = fi.intro_text("Chị là Lan"), fi.intro_text("")
    localefmt._UI_YEU_CAU.reset(tok)
    check("Vietnamese interface: Vietnamese inbox text", "Lời nhắn kèm lời mời" in vi_msg and "không kèm lời nhắn" in vi_none,
          (vi_msg, vi_none))
    check("English interface: English inbox text, the person's own words kept as written",
          en_msg.startswith("[Message sent with the friend request") and en_msg.endswith("Chị là Lan")
          and "sent no introduction" in en_none, (en_msg, en_none))

    # ---- who may run (point 4) ---------------------------------------------------------------------------
    cfg = {"nhan_ket_ban": True}
    tb = lam_bot(cfg)
    tb.start()
    noon = datetime.datetime(2026, 10, 15, 12, 0)
    check("switched on, all day, default audience: runs", fi.why_not("zalo-1", noon) == "")
    cfg["audience"] = "chon"
    check("audience 'only chosen people': skipped", fi.why_not("zalo-1", noon) == "chosen_only")
    cfg["audience"] = "garbage"
    check("broken audience value reads as the narrowest ('chon'): skipped", fi.why_not("zalo-1", noon) == "chosen_only")
    cfg["audience"] = "all"
    # 0.172.0 review: a bot that performs real outside actions must not be handed to strangers it befriends.
    for muc in ("auto", "full"):
        cfg["muc_quyen"] = muc
        check(f"bot at '{muc}': skipped (a stranger would drive real actions)", fi.why_not("zalo-1", noon) == "high_level")
    cfg["muc_quyen"] = "read_docs"
    check("bot at 'read_docs': runs", fi.why_not("zalo-1", noon) == "")
    cfg.pop("muc_quyen")
    cfg["gio_truc"] = {"tu": "08:00", "den": "11:00"}
    check("outside active hours: skipped", fi.why_not("zalo-1", noon) == "off_hours")
    check("inside active hours: runs", fi.why_not("zalo-1", datetime.datetime(2026, 10, 15, 9, 0)) == "")
    cfg.pop("gio_truc")
    cfg["nhan_ket_ban"] = False
    check("switched off: skipped", fi.why_not("zalo-1", noon) == "off")
    tb.stop()
    check("no bot on duty: skipped", fi.why_not("zalo-1", noon) == "no_bot")

    def boom():
        raise RuntimeError("config store broken")
    zp_bad = zp.Transport("zalo-1", [], _answer, cfg_fn=boom)
    zp_bad.start()
    check("a broken bot config never raises into the read loop", fi.why_not("zalo-1") == "no_bot")
    zp_bad.stop()

    # ---- off: nothing happens ----------------------------------------------------------------------
    reset()
    tb = lam_bot({"nhan_ket_ban": False})
    tb.start()
    STATE["requests"] = [req("p1", "Hương Lan", "Chị là Lan, mẹ bạn Minh An lớp 2K10 XPT", 100)]
    check("intake off: no round started, no CLI call", not await luot() and not CLI, CLI)
    tb.stop()

    # ---- out of hours / chosen people: requests stay pending, no Zalo call ----------------------------
    now_hm = localefmt.now()
    h = (now_hm.hour + 2) % 24
    cfg = {"nhan_ket_ban": True, "gio_truc": {"tu": f"{h:02d}:00", "den": f"{(h + 1) % 24:02d}:00"}}
    tb = lam_bot(cfg)
    tb.start()
    reset()
    check("out of hours: no round, no CLI call, the request is still pending",
          not await luot() and not CLI and len(STATE["requests"]) == 1, CLI)
    cfg.pop("gio_truc")
    cfg["audience"] = "chon"
    check("audience 'chon': no round, no CLI call, the request is still pending",
          not await luot() and not CLI and len(STATE["requests"]) == 1, CLI)
    tb.stop()

    # ---- on: accept, record, hand to the bot -------------------------------------------------------------
    reset()
    tb = lam_bot({"nhan_ket_ban": True})
    tb.start()
    STATE["requests"] = [req("p1", "Hương Lan", "Chị là Lan, mẹ bạn Minh An lớp 2K10 XPT", 100),
                         req("p2", "Đàm Huệ", "", 200)]
    t0 = time.time()
    await luot()
    check("both requests accepted, in the session of the right connection",
          accepts() == ["p1", "p2"] and all(c[2] == "/state/zalo-a" for c in CLI), CLI)
    check("every CLI call has the short timeout, not run_cli's 120 s default",
          CLI and all(c[3] == fi.CLI_TIMEOUT <= 20 for c in CLI), [c[3] for c in CLI])
    h1 = tin_hop_thu("p1")
    check("CANARY: the introduction is saved in the inbox as the person's first message",
          h1 and any("Chị là Lan, mẹ bạn Minh An lớp 2K10 XPT" in (t or "") for t in h1), h1)
    h2 = tin_hop_thu("p2")
    check("no message: the inbox says so (the bot will ask)", h2 and any("không kèm lời nhắn" in (t or "") for t in h2), h2)
    await xa()
    texts = [x[0] for x in LUOT]
    check("CANARY: the bot receives the introduction (so it does not ask again)",
          any("mẹ bạn Minh An lớp 2K10 XPT" in t for t in texts), texts)
    check("and the empty one too (so it asks for what is missing)", any("không kèm lời nhắn" in t for t in texts), texts)
    check("each person gets one turn", len(LUOT) == 2, LUOT)

    # ---- poll interval and back-off (point 3) ----------------------------------------------------------
    nxt = fi._poll["zalo-1"]["next"] - t0
    check("after a round the next check is POLL_SECONDS (1 hour) away",
          fi.POLL_SECONDS == 3600 and fi.POLL_SECONDS - 1 <= nxt <= fi.POLL_SECONDS + 5, nxt)
    n = len(CLI)
    check("not due yet: start_round does nothing, no Zalo call", not await luot() and len(CLI) == n)
    gaps = []
    for _ in range(4):
        fi._poll["zalo-1"]["next"] = 0
        await luot()
        gaps.append(fi._poll["zalo-1"]["gap"])
    check("nothing pending: still one check an hour", gaps == [3600, 3600, 3600, 3600], gaps)
    check("so at most 86400 / POLL_SECONDS = 24 checks a day", 86400 // fi.POLL_SECONDS == 24)
    STATE["requests"] = [req("p9", "Mới", "", 900)]
    fi._poll["zalo-1"]["next"] = 0
    await luot()
    check("a request arriving does not make it check more often", fi._poll["zalo-1"]["gap"] == fi.POLL_SECONDS)

    LUOT.clear()
    ev = fi.intro_event(dict(CONN), {"uid": "p1", "name": "Hương Lan", "message": "x", "time": 100})
    kq = conversations.ghi_su_kien(ev)
    check("same request written again is a duplicate (fixed message id), never twice", kq.get("trung") is True, kq)

    # ---- refused accepts: stop the round, back off, newer requests reached (point 2) ----------------------
    reset()
    STATE["requests"] = [req("r1", "Bị chặn", "Mẹ bạn Hà lớp 2K11", 300), req("r2", "B", "", 310), req("r3", "C", "", 320)]
    STATE["accept_fail"] = {"r1"}
    await luot()
    check("first refusal stops the round: one accept call, the newer ones not tried yet", accepts() == ["r1"], accepts())
    check("refused: nothing recorded, nothing handed to the bot", tin_hop_thu("r1") is None and not LUOT)
    f = fi._fails.get(("zalo-1", "r1")) or {}
    check("the refused person is backed off for FAIL_BACKOFF", f.get("n") == 1
          and fi.FAIL_BACKOFF - 5 <= f.get("until", 0) - time.time() <= fi.FAIL_BACKOFF, f)
    CLI.clear()
    fi._poll["zalo-1"]["next"] = 0
    await luot()
    check("next round skips the backed-off person and reaches the newer requests", accepts() == ["r2", "r3"], accepts())
    check("they are recorded", tin_hop_thu("r2") is not None and tin_hop_thu("r3") is not None)
    CLI.clear()
    fi._poll["zalo-1"]["next"] = 0
    await luot()
    check("still backed off: no accept call for the refused person at all", accepts() == [], accepts())
    # Let the back-off expire (a round 'later'), fail until MAX_FAILS, then the person is skipped for good.
    later = time.time() + 10 ** 6
    for i in range(fi.MAX_FAILS + 2):
        fi._poll["zalo-1"]["next"] = 0
        await fi.run_once(dict(CONN), now=later + i * 10 ** 6)
        if i == 0:
            f = fi._fails.get(("zalo-1", "r1")) or {}
            check("second refusal: the back-off doubles", f.get("n") == 2
                  and 2 * fi.FAIL_BACKOFF - 5 <= f.get("until", 0) - time.time() <= 2 * fi.FAIL_BACKOFF, f)
    check("after MAX_FAILS refusals: never tried again (no endless failing calls)",
          accepts().count("r1") == fi.MAX_FAILS - 1 and fi.skipped("zalo-1", "r1", later * 10), accepts())
    check("a person who only had back-offs does not make the account poll more often",
          fi._poll["zalo-1"]["gap"] == fi.POLL_SECONDS, fi._poll["zalo-1"])
    STATE["accept_fail"] = set()
    fi._fails.clear()
    CLI.clear()
    fi._poll["zalo-1"]["next"] = 0
    await luot()
    check("once Zalo accepts again (after restart), the person goes through", accepts() == ["r1"] and tin_hop_thu("r1"))

    # ---- a burst is spread over rounds ---------------------------------------------------------------
    reset()
    STATE["requests"] = [req(f"q{i}", f"N{i}", "", 400 + i) for i in range(fi.MAX_PER_ROUND + 3)]
    kq = await fi.run_once(dict(CONN))
    check("at most MAX_PER_ROUND accepted per round, the rest wait", kq["accepted"] == fi.MAX_PER_ROUND and kq["pending"] == fi.MAX_PER_ROUND + 3, kq)

    # ---- switched off mid-round --------------------------------------------------------------------------
    reset()
    tb.stop()
    cfg = {"nhan_ket_ban": True}
    tb = lam_bot(cfg)
    tb.start()
    STATE["requests"] = [req("s1", "A", "", 1), req("s2", "B", "", 2)]
    real_accept = fake_run_cli

    async def off_after_first(conn, command, positionals=None, options=None, timeout=120):
        r = await real_accept(conn, command, positionals, options, timeout)
        if command == ["friend", "accept"]:
            cfg["nhan_ket_ban"] = False
        return r
    zalo_cli.run_cli = off_after_first
    await fi.run_once(dict(CONN))
    zalo_cli.run_cli = fake_run_cli
    check("owner switches it off during a round: no further accepts", accepts() == ["s1"], accepts())
    cfg["nhan_ket_ban"] = True

    # ---- Zalo unreadable / CLI without the command ---------------------------------------------------
    reset()

    async def broken(conn, command, positionals=None, options=None, timeout=120):
        return False, None, "Not logged in"
    zalo_cli.run_cli = broken
    kq = await fi.run_once(dict(CONN))
    check("Zalo cannot be read: an error is returned, nothing raised, backed off",
          kq.get("error") == "Not logged in" and fi._poll["zalo-1"]["next"] - time.time() >= fi.POLL_SECONDS - 5, kq)

    async def old_cli(conn, command, positionals=None, options=None, timeout=120):
        return False, None, "CLI Zalo thoát mã 1. error: unknown command 'recommendations'"
    zalo_cli.run_cli = old_cli
    t0 = time.time()
    kq = await fi.run_once(dict(CONN))
    check("a CLI without the command pauses intake for UNSUPPORTED_WAIT instead of failing every round",
          kq.get("unsupported") and fi._poll["zalo-1"]["next"] - t0 >= fi.UNSUPPORTED_WAIT - 5, kq)
    zalo_cli.run_cli = fake_run_cli

    # ---- the read loop never waits for intake (points 1 and 8) ------------------------------------------
    # A stalled CLI: the call hangs for longer than the whole test window. The real read loop must keep reading
    # meanwhile (awaiting the round inline, as before the review, gives one read and then nothing).
    reset()
    fi.CLI_TIMEOUT = 3.0
    STATE["stall"] = 5.0
    STATE["requests"] = [req("t1", "A", "", 1)]
    reads = await read_loop(0.8)
    check("stalled CLI: a round was started from the read loop", any(c[0] == ["friend", "recommendations"] for c in CLI), CLI)
    check("stalled CLI: the read loop kept reading while the call hung (beat 0.1 s, 0.8 s)", reads >= 4, reads)
    check("stalled CLI: the call carries CLI_TIMEOUT", CLI and CLI[0][3] == fi.CLI_TIMEOUT)
    check("only one round at a time per account, even while it hangs",
          sum(1 for c in CLI if c[0] == ["friend", "recommendations"]) == 1, CLI)
    await asyncio.sleep(0.05)
    check("stopping the read loop cancels the hung round", not fi._tasks and not STATE["stall_done"], (fi._tasks, STATE))

    # A CLI that ignores its timeout altogether: the round's own cap ends it.
    reset()
    fi.CLI_TIMEOUT = 30
    rt = fi.ROUND_TIMEOUT
    fi.ROUND_TIMEOUT = 0.4
    STATE["stall"] = 5.0
    fi.start_round(dict(CONN))
    t = fi._tasks.get("zalo-1")
    t_start = time.time()
    await asyncio.wait_for(asyncio.shield(t), 3)
    check("a round that hangs past ROUND_TIMEOUT is stopped (logged, not raised)",
          t.done() and not t.cancelled() and time.time() - t_start < 1.5)
    check("and a new round is not retried at once afterwards", not fi.due("zalo-1"))
    fi.ROUND_TIMEOUT = rt
    fi.CLI_TIMEOUT = 20

    # Running guard: a second start while a round is running does nothing.
    reset()
    STATE["stall"] = 0.3
    first = fi.start_round(dict(CONN))
    fi._poll["zalo-1"]["next"] = 0          # due again, but the first round is still running
    second = fi.start_round(dict(CONN))
    await fi._tasks["zalo-1"]
    check("running guard: one task per account", first and not second)

    # An exception inside intake: logged, the read loop keeps going.
    reset()
    STATE["raise"] = True
    reads = await read_loop(0.8)
    check("exception in a round: the read loop keeps reading", reads >= 4 and CLI, (reads, CLI))
    STATE["raise"] = False

    reset()
    sr = fi.start_round

    def exploding(conn, now=None):
        raise RuntimeError("bug in start_round")
    fi.start_round = exploding
    reads = await read_loop(0.8)
    fi.start_round = sr
    check("exception while starting a round: the read loop keeps reading", reads >= 4, reads)

    # Out of hours through the real read loop: reads continue, Zalo is never asked about friends.
    reset()
    tb.stop()
    h = (localefmt.now().hour + 2) % 24
    tb = lam_bot({"nhan_ket_ban": True, "gio_truc": {"tu": f"{h:02d}:00", "den": f"{(h + 1) % 24:02d}:00"}})
    tb.start()
    reads = await read_loop(0.6)
    check("out of hours through the read loop: reading goes on, no friend call", reads >= 3 and not CLI, (reads, CLI))
    tb.stop()

    # ---- dashboard (point 7) -------------------------------------------------------------------------
    js = (ROOT / "dashboard" / "chatbots.js").read_text(encoding="utf-8")
    check("bot form has the switch and sends nhan_ket_ban", 'id="cbNhanKetBan"' in js and "nhan_ket_ban:" in js)
    check("the switch sits in a box hidden by default",
          '<div id="cbKbBox" style="display:none">' in js)
    check("shown only while a personal Zalo account is ticked",
          'a.channel === "zalo_personal"' in js and 'querySelector("#cbKbBox").style.display = coZaloCaNhan()' in js)
    check("never sent as on for a bot without a personal Zalo account",
          'nhan_ket_ban: coZaloCaNhan() &&' in js)
    src = (SERVER / "main.py").read_text(encoding="utf-8")
    check("POST /chatbots takes nhan_ket_ban", 'nhan_ket_ban: str = Form("")' in src)
    loop_src = (SERVER / "zalo_personal_channel.py").read_text(encoding="utf-8")
    check("the read loop does not await intake", "await _nhan_loi_moi" not in loop_src and "_nhan_loi_moi(conn)" in loop_src)
    check("no em dash", all(chr(0x2014) not in p.read_text(encoding="utf-8")
                            for p in (SERVER / "zalo_friend_intake.py", ROOT / "tests" / "python" / "test_zalo_ket_ban.py")))


asyncio.run(chay())
print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("Tất cả xanh.")
