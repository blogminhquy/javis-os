"""Javis Core follow-ups (0.188.0): the chat's brain wins, a quieter Javis Core, a hard memory block for Claude
Code, and a source on every new memory.

    python tests/python/test_javis_core_followups.py

Owner, 16/10/2026, after reviewing 0.185.0-0.187.0: "làm luôn nhé" for the four picked improvements.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
import time
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="javis-core-follow-")
os.environ["JAVIS_STATE_DIR"] = STATE

import claude_sdk_engine  # noqa: E402
import inbox  # noqa: E402
import main  # noqa: E402
import memory_control as MC  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


main.cfgmod.gate_active = lambda: False
client = TestClient(main.app, base_url="http://127.0.0.1")
store = main.get_store()
OTHER = Path(tempfile.mkdtemp(prefix="javis-follow-other-"))

# ---- 1. the chat's brain wins ----
check("the default brain is 'brain' in the picker's terms", main._brain_ui_value(main._brain_key("brain")) == "brain")
check("another brain is path:<dir>", main._brain_ui_value(main._brain_key(str(OTHER))) == f"path:{main._brain_key(str(OTHER))}")
sid = store.create_session(brain=main._brain_key(str(OTHER)), channel="web")
d = client.get(f"/sessions/{sid}", params={"limit": 5}).json()
check("a chat says which brain it belongs to (picker value and name)",
      d.get("brain_ui") == f"path:{main._brain_key(str(OTHER))}" and d.get("brain_name") == OTHER.name, d)
inbox.add("Báo cáo của brain khác", kind="report", session_id=sid, brain=main._brain_key(str(OTHER)))
it = client.get("/inbox").json()["items"][0]
check("a bell item carries the picker value of its brain", it.get("brain_ui") == f"path:{main._brain_key(str(OTHER))}", it)
src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
import json  # noqa: E402
got = []
with client.websocket_connect("/ws", headers={"host": "127.0.0.1:7777", "origin": "http://127.0.0.1:7777"}) as ws:
    ws.send_text(json.dumps({"message": "chào", "brain": "brain", "session_id": sid}))
    t0 = time.time()
    while time.time() - t0 < 20:
        m = json.loads(ws.receive_text())
        got.append(m)
        if m.get("type") in ("brain_follow", "response", "turn_done", "error"):
            break
fol = [m for m in got if m.get("type") == "brain_follow"]
check("a turn sent with brain A in a chat of brain B runs on B and tells the dashboard (over the real WebSocket)",
      fol and fol[0]["session_id"] == sid and fol[0]["brain_ui"] == f"path:{main._brain_key(str(OTHER))}"
      and store.get_session(sid)["brain"] == main._brain_key(str(OTHER)), [m.get("type") for m in got])
app = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
noti = (ROOT / "dashboard" / "notifications.js").read_text(encoding="utf-8")
check("the chat shows whose it is, with a switch button", "function veNhanBrain(ten, uiVal)" in app
      and 'data.type === "brain_follow"' in app and "sess.brain_ui !== graphSource.value" in app)
check("clicking a bell item of another brain switches the brain first, only on that click",
      "if (chuyenBrainNeuCan(item)) { setTimeout(function () { moThuTiep(item); }, 450); return; }" in noti and "gs.dispatchEvent(new Event(\"change\"))" in noti)

# ---- 2. a quieter Javis Core ----
cfg = main.cfgmod.read_settings()
cfg.setdefault("telegram", {}).update({"enabled": True, "token": "1:a", "chat_id": "111,222", "owner_chat_id": "111"})
main.cfgmod.write_settings(cfg)
rt = main._report_route("", str(OTHER), "report", quiet=True)
check("a run that went fine is not posted into Javis Core", rt["chat"] == "" and not rt.get("routing"))
rt = main._report_route("", str(OTHER), "report", quiet=False)
check("a report that needs the owner still is", rt["chat"] != "")
check("a colleague's Telegram report is not copied into the owner's Javis Core",
      main._report_route("222", str(OTHER), "answer")["chat"] == "")
check("the owner's own Telegram report is", main._report_route("111", str(OTHER), "answer")["chat"] != "")
cs = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("the owner Telegram field is a select of the allowed ids", '<select class="js-input" id="${id("owner")}">' in cs)

# ---- 3. hard memory block for Claude Code ----
V = Path(tempfile.mkdtemp(prefix="javis-follow-vault-"))
(V / "memory").mkdir()
rules_on = MC.claude_deny_rules(str(V))
check("learning on: only the switch and the forgotten list are off limits",
      "Write(memory/learning.json)" in rules_on and "Edit(memory/forgotten.json)" in rules_on
      and not any("memory/**" in r for r in rules_on))
MC.set_learning(V / "memory", False)
rules_off = MC.claude_deny_rules(str(V))
check("learning off: Write/Edit/MultiEdit/NotebookEdit under memory/ are denied, relative and absolute",
      {"Write(memory/**)", "Edit(memory/**)", "MultiEdit(memory/**)", "NotebookEdit(memory/**)"} <= set(rules_off)
      and f"Write(//{V.as_posix().lstrip('/')}/memory/**)" in rules_off, rules_off)
eng = claude_sdk_engine.ClaudeSDK(system_prompt="x", cwd=str(V))
eng.javis_vault = str(V)
opts = eng._options()
check("a Claude Code turn in that brain carries the deny rules (they hold in bypassPermissions)",
      "Write(memory/**)" in (opts.disallowed_tools or []), getattr(opts, "disallowed_tools", None))
MC.set_learning(V / "memory", True)
opts = eng._options()
check("switched back on, the turn may write memory again (only the two control files stay blocked)",
      "Write(memory/**)" not in (opts.disallowed_tools or []) and "Write(memory/learning.json)" in (opts.disallowed_tools or []))

# ---- 4. a source on every new memory ----
mem = V / "memory"
(mem / "facts").mkdir(exist_ok=True)
(mem / "facts" / "moi.md").write_text("---\ntype: preference\ncreated: 2026-10-16\n---\nThích báo cáo buổi sáng.\n", encoding="utf-8")
(mem / "facts" / "co-nguon.md").write_text("---\ntype: user\nsource: chat 2026-10-01\n---\nTên là Quý.\n", encoding="utf-8")
old = mem / "facts" / "cu.md"
old.write_text("---\ntype: user\n---\nCũ.\n", encoding="utf-8")
os.utime(old, (time.time() - 7200, time.time() - 7200))
done = MC.stamp_new_facts(mem, source="chat 2026-10-16 (abcd1234)", since=time.time() - 1800)
check("a memory written this turn without a source gets one", done == ["moi"]
      and "source: chat 2026-10-16 (abcd1234)" in (mem / "facts" / "moi.md").read_text(encoding="utf-8"), done)
check("one that had a source keeps it; an old one is not touched",
      "source: chat 2026-10-01" in (mem / "facts" / "co-nguon.md").read_text(encoding="utf-8")
      and "source:" not in old.read_text(encoding="utf-8"))
check("every saved chat turn runs the stamp", "memory_control.stamp_new_facts(_brain_memory_dir(brain)" in src)

print()
if fails:
    print(f"FAIL - {len(fails)} check(s)")
    raise SystemExit(1)
print("OK - test_javis_core_followups: all pass")
