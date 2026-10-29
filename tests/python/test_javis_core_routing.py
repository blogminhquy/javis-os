"""Report routing to Javis Core, no guessed recipient (0.186.0).

    python tests/python/test_javis_core_routing.py

Spec: owner, 16/10/2026 (Javis Core goal, sections 6 and 8; acceptance groups "Định tuyến" and "Thông báo đẩy").

- a report for a chat that exists goes to that chat and is not copied to Javis Core;
- no target chat: the Javis Core chat of the brain the WORK belongs to, never the brain on screen;
- a deleted origin chat: the source brain's Javis Core when the brain is known, else kept in the bell only;
- neither target nor brain: not guessed, kept in the bell marked no_target, sent nowhere;
- no "first Telegram id" and no broadcast to every id: only the owner's own linked chat, or the single id;
- a retry with the same key is filed once and rings once; one channel failing does not lose the report.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="javis-core-route-")
os.environ["JAVIS_STATE_DIR"] = STATE

import inbox  # noqa: E402
import javis_core  # noqa: E402
import main  # noqa: E402

# 0.403.0: Javis Core rings only urgent notices by default (that default is tested in test_notify_commander.py). This
# file checks how important notices are routed, so every group rings from "important" up, as before 0.403.0.
import notify_policy  # noqa: E402
for _g in notify_policy.GROUPS:
    notify_policy.set_mode(_g, "important")
import tasks  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


main.cfgmod.gate_active = lambda: False
client = TestClient(main.app, base_url="http://127.0.0.1")
store = main.get_store()
A = Path(tempfile.mkdtemp(prefix="javis-route-a-"))
B = Path(tempfile.mkdtemp(prefix="javis-route-b-"))
KA, KB = main._brain_key(str(A)), main._brain_key(str(B))


def set_tg(ids, owner=None, enabled=True):
    cfg = main.cfgmod.read_settings()
    t = cfg.setdefault("telegram", {})
    t.update({"enabled": enabled, "token": "123:abc", "chat_id": ids})
    if owner is not None:
        t["owner_chat_id"] = owner
    else:
        t.pop("owner_chat_id", None)
    main.cfgmod.write_settings(cfg)


sent = []


async def fake_channel(owner_chat, text, **kw):
    sent.append(owner_chat)
    return True, ""


real_channel = main._gui_qua_kenh

# ---- 1. the owner's own Telegram ----
set_tg("111")
check("a single allowed id is the owner's", main._owner_telegram_id() == "111")
set_tg("111,222")
check("several ids and no link: nobody (no 'first id')", main._owner_telegram_id() == "")
set_tg("111,222", owner="222")
check("an explicit link on the allow-list wins", main._owner_telegram_id() == "222")
set_tg("111,333", owner="222")
check("a link no longer on the allow-list is ignored", main._owner_telegram_id() == "")
r = client.post("/settings", data={"section": "telegram", "data": '{"chat_id": "111,222", "owner_chat_id": "999"}'})
check("settings refuse to link a chat outside the allow-list",
      r.status_code == 200 and main.cfgmod.read_settings()["telegram"].get("owner_chat_id") == "")
client.post("/settings", data={"section": "telegram", "data": '{"chat_id": "111,222", "owner_chat_id": "222"}'})
check("settings store a valid owner link", main.cfgmod.read_settings()["telegram"].get("owner_chat_id") == "222")

# ---- 2. the routing decision ----
set_tg("111,222")
web_a = store.create_session(brain=KA, channel="web")
rt = main._report_route(f"web:{web_a}", str(B), "answer")
check("an existing chat: that chat, nothing copied to Javis Core", rt["chat"] == web_a and not rt["external"])
rt = main._report_route("", str(A), "report")
core_a = javis_core.current_default(KA)
check("no target: the Javis Core chat of the work's brain", rt["chat"] and rt["chat"] == core_a
      and (store.get_session(core_a) or {}).get("channel") == "agent:javis-core" and rt["brain"] == KA)
rt_b = main._report_route("", str(B), "report")
check("another brain's work goes to that brain's Javis Core", rt_b["chat"] == javis_core.current_default(KB)
      and rt_b["chat"] != core_a)
check("several Telegram ids and no link: no outside channel", rt["external"] == "")
gone = store.create_session(brain=KA, channel="web")
store.delete(gone)
rt = main._report_route(f"web:{gone}", str(A), "answer")
check("a deleted origin chat with a known brain: that brain's Javis Core", rt["chat"] == core_a and rt.get("lost_origin"))
rt = main._report_route(f"web:{gone}", "", "answer")
check("a deleted origin chat and no brain: not guessed", rt["chat"] == "" and rt.get("routing") == "lost_origin")
rt = main._report_route("", "", "report")
check("no target and no brain: not guessed", rt["chat"] == "" and rt["external"] == "" and rt.get("routing") == "no_target")
set_tg("111")
rt = main._report_route("", "", "system")
check("a system notice: the bell plus the owner's own Telegram, no chat", rt["chat"] == "" and rt["external"] == "111")
rt = main._report_route("777", str(A), "answer")
check("0.188.0: someone else's outside chat keeps its channel and is NOT copied into the owner's Javis Core",
      rt["external"] == "777" and rt["chat"] == "")
rt = main._report_route("111", str(A), "answer")
check("the owner's own Telegram: also in Javis Core on the dashboard", rt["external"] == "111" and rt["chat"] == core_a)
rt = main._report_route("111", str(A), "answer", quiet=True)
check("0.188.0: a run that went fine stays out of the Javis Core chat", rt["external"] == "111" and rt["chat"] == "")
rt = main._report_route("", str(A), "report", quiet=True)
check("0.188.0: an untargeted run that went fine: bell (and owner's Telegram) only, not the chat, not an error",
      rt["chat"] == "" and rt["external"] == "111" and not rt.get("routing") and rt["brain"] == KA)

# ---- 3. end to end through _notify_owner ----
main._gui_qua_kenh = fake_channel
try:
    sent.clear()
    inbox.STORE.unlink(missing_ok=True)
    ok, err = run(main._notify_owner("", "✅ Việc 'Báo cáo tuần' đã hoàn thành.", kind="report", brain=str(A),
                                     dedup="task:t1:done:r1"))
    items = inbox.danh_sach(50)
    check("untargeted report: Javis Core chat and the owner's Telegram", ok and sent == [f"web:{core_a}", "111"], sent)
    check("the bell item carries the source brain and opens Javis Core",
          items and items[0]["brain"] == KA and items[0]["session_id"] == core_a
          and items[0]["channel"] == "agent:javis-core", items[:1])
    sent.clear()
    ok, _ = run(main._notify_owner("", "✅ Việc 'Báo cáo tuần' đã hoàn thành.", kind="report", brain=str(A),
                                   dedup="task:t1:done:r1"))
    check("a retry with the same key: filed once, sent once", ok and sent == [] and len(inbox.danh_sach(50)) == 1, sent)
    sent.clear()
    ok, err = run(main._notify_owner("", "Báo cáo lạc", kind="report"))
    it = inbox.danh_sach(50)[0]
    check("no target and no brain: kept in the bell (no_target), sent nowhere",
          sent == [] and it.get("routing") == "no_target" and it["session_id"] == "", (sent, it))
    sent.clear()
    run(main._loop_notify("⚠ Loop 'x' đã tự tạm dừng"))
    it = inbox.danh_sach(50)[0]
    check("loop pause / engine down: the bell (system) and the owner's own chat only, no broadcast",
          sent == ["111"] and it["kind"] == "system", (sent, it))
    set_tg("111,222")
    sent.clear()
    run(main._loop_notify("⚠ Bộ não AI ngừng"))
    check("several ids, no link: the system notice stays in the bell", sent == [], sent)
finally:
    main._gui_qua_kenh = real_channel


async def one_fails(owner_chat, text, **kw):
    sent.append(owner_chat)
    return (False, "telegram down") if not owner_chat.startswith("web:") else (True, "")

set_tg("111")
main._gui_qua_kenh = one_fails
try:
    sent.clear()
    ok, _ = run(main._notify_owner("", "Việc xong", kind="report", brain=str(B)))
    check("one channel failing does not stop the other or the report", ok and len(sent) == 2
          and sent[0] == f"web:{javis_core.current_default(KB)}" and sent[1] == "111"
          and inbox.danh_sach(1)[0]["brain"] == KB, sent)
finally:
    main._gui_qua_kenh = real_channel

# ---- 4. the outside senders no longer guess ----
set_tg("111,222")
ok, err = run(main._gui_qua_kenh("999", "x"))
check("Telegram: an id outside the allow-list is refused, not redirected", ok is False and "danh sách" in err, err)
ok, err = run(main._gui_qua_kenh("", "x"))
check("Telegram: no id at all is refused", ok is False, err)
cfg = main.cfgmod.read_settings()
cfg["zalo_bot"] = {"enabled": True, "token": "t", "chat_id": "aa,bb"}
main.cfgmod.write_settings(cfg)
ok, err = run(main._zalo_send_to("cc", "x"))
check("Zalo: an unlisted chat is refused, not sent to every id", ok is False, err)
ok, err = run(main._zalo_send_to("", "x"))
check("Zalo: an empty chat is refused", ok is False, err)
src = (ROOT / "server" / "owner_channels.py").read_text(encoding="utf-8")
check("Slack/WhatsApp/Discord/Lark: no ids[0] fallback", "ids[0]" not in src.split("async def send_to", 1)[1].split("async def test", 1)[0])
check("no broadcast loop left in _loop_notify", "for cid in ids" not in main.inspect.getsource(main._loop_notify)
      if hasattr(main, "inspect") else "for cid in ids" not in __import__("inspect").getsource(main._loop_notify))

# ---- 5. producers pass their own brain ----
got = {}


def hook(owner_chat, text, *, quiet=False, brain="", dedup="", **kw):
    got.update(brain=brain, dedup=dedup)


check("Kanban: the job's brain and a per-run key reach the report hook",
      tasks._report_extra(hook, "/x/brain", "task:t:done:r") == {"brain": "/x/brain", "dedup": "task:t:done:r"})
check("Kanban: an old hook without those arguments still works",
      tasks._report_extra(lambda owner_chat, text, quiet=False: None, "/x", "k") == {})
si = (ROOT / "server" / "self_improve.py").read_text(encoding="utf-8")
check("loops pass their vault and a per-run key", '"brain": vault_root, "dedup": f"loop:{vault_root}:{slug}:' in si)
rem = (ROOT / "server" / "reminders.py").read_text(encoding="utf-8")
check("reminders pass their brain and a per-firing key", 'kw["brain"] = brain' in rem and "rem:{rem.get('id', '')}" in rem)
tk = (ROOT / "server" / "tasks.py").read_text(encoding="utf-8")
check("blocked-job batches are kept per recipient AND brain",
      'chat_id = str(task.get("chat_id") or "") + _BUCKET_SEP + str(task.get("brain_root") or "")' in tk)
cl = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
check("the prompt no longer teaches the first-Telegram fallback",
      "first Telegram ID" not in cl and "Left empty → the Javis Core chat of the work's brain." in cl)

print()
if fails:
    print(f"FAIL - {len(fails)} check(s)")
    raise SystemExit(1)
print("OK - test_javis_core_routing: all pass")
