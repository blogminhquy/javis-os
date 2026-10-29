"""Javis Core, the notification commander (0.403.0; owner 29/10/2026: "trao quyền quyết định đấy cho bộ phán xử của
Jarvis Core", "1. Tự động  2. Mặc định chỉ tin khẩn", "chấm theo hệ thống resonance về việc phản hồi của emoji").

    python tests/run.py notify_commander

Spec: docs/dev/2026-10-javis-core-chi-huy-thong-bao.md sections 3 to 6. No network, no model.
- every group defaults to "urgent only"; reminders, questions, customers waiting and "Javis is not usable" ring;
  the rest is kept in the bell as filtered (read, no push, not copied to Javis Core's chat or the owner's Telegram);
  a chat that asked for the work still gets it;
- groups and levels from the producer; the same kind ringing a 4th time in 6 hours is filtered (never an urgent one);
- feedback in the Resonance emoji set plus "Needed" / "Not needed": Javis Core changes rules on its own, says so in
  its chat, never silences an urgent kind by itself, and every change can be undone;
- the owner's "off" drops a group; Core's "off" still lets urgent notices ring;
- routes /inbox/react and /notify/policy*, the `javis_notify` chat tool (owner only), the bell's filter UI.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="javis-notify-cmd-")
os.environ["JAVIS_STATE_DIR"] = STATE
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import inbox  # noqa: E402
import main  # noqa: E402
import mcp_hub  # noqa: E402
import notify_policy as NP  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


if STATE not in str(NP.STORE):
    print(f"FAIL the policy store is not in the temp dir: {NP.STORE}. STOP.")
    sys.exit(1)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


main.cfgmod.gate_active = lambda: False
client = TestClient(main.app, base_url="http://127.0.0.1")
BR = Path(tempfile.mkdtemp(prefix="javis-notify-brain-"))
KB = main._brain_key(str(BR))
cfg = main.cfgmod.read_settings()
cfg.setdefault("telegram", {}).update({"enabled": True, "token": "123:abc", "chat_id": "111"})
main.cfgmod.write_settings(cfg)
sent, pushes = [], []


async def fake_channel(owner_chat, text, **kw):
    sent.append((owner_chat, text))
    return True, ""


async def fake_push(*a, **k):
    pushes.append(a)
    return 0

main._gui_qua_kenh = fake_channel
main.webpush.gui_het = fake_push
core = main.javis_core.default_session(main.get_store(), KB, same_brain=main._cung_brain)


def items():
    return {x["title"]: x for x in inbox.danh_sach(300)}


# ---- 1. the default: urgent only ----
st = NP.status()
check("every group starts on 'urgent only'", all(g["mode"] == "urgent" and g["set_by"] == "default" for g in st["groups"]) and
      st["default"] == "urgent" and len(st["groups"]) == len(NP.GROUPS), st["groups"])
check("levels: a reminder and a question are urgent, a quiet notice is info, the rest important",
      NP.level_of(group="reminder") == "urgent" and NP.level_of(group="question") == "urgent" and
      NP.level_of(quiet=True, group="job") == "info" and NP.level_of(group="job") == "important" and
      NP.level_of(level="urgent", quiet=True) == "urgent")
check("groups: explicit wins, a job asking the owner is a question, else the source",
      NP.group_of(group="cost", source="reminder") == "cost" and NP.group_of(viec={"status": "hoi"}) == "question" and
      NP.group_of(dedup="ask:t1:0:x") == "question" and NP.group_of(source="reminder") == "reminder" and
      NP.group_of(source="zalo") == "connection" and NP.group_of(source="store") == "update" and
      NP.group_of(kind="answer") == "job" and NP.group_of(kind="system") == "other")
check("a kind: numbers, ids and links do not matter, the quoted name does",
      NP.signature("Việc 'Kiểm tra đơn' lỗi lần 3 https://x.y/a") == NP.signature("Việc 'Kiểm tra đơn' lỗi lần 14") and
      NP.signature("Việc 'Kiểm tra đơn' lỗi") != NP.signature("Việc 'Đăng bài' lỗi"))

sent.clear(); pushes.clear()
run(main._notify_owner("", "⚠ Loop 'Quét giá' đã tự tạm dừng", kind="system", source="loop", level="important"))
it = items().get("⚠ Loop 'Quét giá' đã tự tạm dừng") or {}
check("an important system notice: filtered, read, no push, no Telegram",
      it.get("filtered") is True and it.get("read") is True and it.get("why") == "mode" and it.get("group") == "job" and
      not pushes and not sent, (it, sent, pushes))
run(main._notify_owner("", "Nhắc bạn: gọi nhà cung cấp", kind="report", source="reminder", brain=str(BR)))
it = items().get("Nhắc bạn: gọi nhà cung cấp") or {}
check("a reminder: urgent, rings, reaches Javis Core's chat and the owner's Telegram",
      not it.get("filtered") and not it.get("read") and it.get("level") == "urgent" and
      ("web:" + core) in [s[0] for s in sent] and "111" in [s[0] for s in sent], (it, sent))
sent.clear()
web = main.get_store().create_session(brain=KB)
run(main._notify_owner("web:" + web, "✅ Việc 'Báo cáo' đã hoàn thành.", kind="answer", quiet=True,
                       viec={"kind": "task", "status": "done", "title": "Báo cáo", "id": "t9"}))
it = items().get("✅ Việc 'Báo cáo' đã hoàn thành.") or {}
check("a filtered result still reaches the chat that asked for it", it.get("filtered") and ("web:" + web) in [s[0] for s in sent],
      (it, sent))
sent.clear(); pushes.clear()
run(main._bo_vao_hom_thu("", "Bot Shop cần người thật: Lan", kind="system", source="chatbot", level="urgent"))
it = items().get("Bot Shop cần người thật: Lan") or {}
check("a customer waiting for a person rings and pushes", not it.get("filtered") and not it.get("read") and pushes, (it, pushes))
cau = "Zalo (Shop): Lan asked to join the group"
src = (SERVER / "main.py").read_text(encoding="utf-8")
check("CANARY: the engine down is urgent, broken connections after a restart are important",
      'connect_health.on_engine_down = lambda text: _loop_notify(text, source="engine", level="urgent")' in src and
      'connect_health.on_connections_down = lambda text: _loop_notify(text, source="connections", level="important")' in src)
check("CANARY: every chatbot notice is urgent (a customer waits), team questions are urgent questions",
      'level="urgent"))' in src.split("notify=lambda text: _bo_vao_hom_thu(\"\", text, kind=\"system\", source=\"chatbot\"")[1][:200]
      and 'group="question" if asks else "team"' in src)
check("a team asking the owner is recognised", bool(main._TEAM_ASKS_OWNER.search('Nhóm "Bán hàng" xin duyệt: Chạy QC')) and
      not main._TEAM_ASKS_OWNER.search('Việc nhóm "X" bị chặn: thiếu file'))

# ---- 2. repeats ----
NP.set_mode("connection", "all", set_by="owner")
pushes.clear()
for i in range(5):
    run(main._bo_vao_hom_thu("", f"Kết nối POS hỏng lần {i + 1}", kind="system", source="connections"))
rep = [x for x in inbox.danh_sach(300) if x["title"].startswith("Kết nối POS hỏng")]
check("the same kind rings 3 times in 6 hours, then is filtered as a repeat",
      sum(1 for x in rep if not x.get("filtered")) == 3 and sum(1 for x in rep if x.get("why") == "repeat") == 2, rep)
for i in range(5):
    run(main._bo_vao_hom_thu("", f"Javis chưa dùng được lần {i + 1}", kind="system", source="engine", level="urgent"))
rep = [x for x in inbox.danh_sach(300) if x["title"].startswith("Javis chưa dùng được")]
check("an urgent notice is never filtered as a repeat", len(rep) == 5 and not any(x.get("filtered") for x in rep), rep)

# ---- 3. feedback and Javis Core's own changes ----
sent.clear()
# A system notice has no brain: Javis Core speaks in the default brain's Core chat.
core0 = main.javis_core.default_session(main.get_store(), main._brain_key("brain"), same_brain=main._cung_brain)
pos = next(x for x in inbox.danh_sach(300) if x["title"] == "Kết nối POS hỏng lần 1")
r = client.post("/inbox/react", json={"id": pos["id"], "value": "angry", "axis": "not_needed"}).json()
check("'Not needed' on a kind: Core filters that kind and says so in its chat",
      r.get("ok") and r["reaction"]["value"] == "angry" and any(c["kind"] == "kind" and c["to"] == "mute" and c["set_by"] == "core"
                                                                for c in r["changes"]) and
      any(s[0] == "web:" + core0 and "Kết nối POS hỏng" in s[1] for s in sent), (r, sent))
run(main._bo_vao_hom_thu("", "Kết nối POS hỏng lần 99", kind="system", source="connections"))
check("...and the next one of that kind is filtered as muted", items()["Kết nối POS hỏng lần 99"].get("why") == "muted")
check("an invalid reaction is refused", client.post("/inbox/react", json={"id": pos["id"], "value": "fire"}).status_code == 400)

eng = next(x for x in inbox.danh_sach(300) if x["title"] == "Javis chưa dùng được lần 1")
r = client.post("/inbox/react", json={"id": eng["id"], "axis": "not_needed"}).json()
mute = next((c for c in r.get("changes") or [] if c["kind"] == "kind"), {})
check("'Not needed' on an urgent kind is the owner's own rule (Core never silences urgent by itself)",
      mute.get("set_by") == "owner" and mute.get("to") == "mute", r)
run(main._bo_vao_hom_thu("", "Javis chưa dùng được lần 100", kind="system", source="engine", level="urgent"))
check("...so that urgent kind is now filtered", items()["Javis chưa dùng được lần 100"].get("why") == "muted")
check("undo puts the rule back", client.post("/notify/policy/undo", json={"id": mute.get("id")}).json().get("ok") and
      not [x for x in NP.status()["rules"] if x["key"] == mute.get("target")])

# group score: four angry reactions on job notices move the group one notch down, by Core
NP.set_mode("job", "all", set_by="owner")
for i in range(4):
    run(main._bo_vao_hom_thu("", f"Việc 'Dọn kho {i}' xong", kind="answer", quiet=True))
ids = [x["id"] for x in inbox.danh_sach(300) if x["title"].startswith("Việc 'Dọn kho")]
changes = []
for iid in ids:
    changes += client.post("/inbox/react", json={"id": iid, "value": "angry"}).json().get("changes") or []
grp = [c for c in changes if c["kind"] == "group"]
check("a group scoring -4 is moved one notch down by Core (all -> important)",
      len(grp) == 1 and grp[0]["from"] == "all" and grp[0]["to"] == "important" and grp[0]["set_by"] == "core" and
      NP.mode_of("job")["mode"] == "important", changes)
check("undo of a group change gives the owner's previous mode back",
      client.post("/notify/policy/undo", json={"id": grp[0]["id"] if grp else ""}).json().get("ok") and NP.mode_of("job")["mode"] == "all")

# "Needed" on a filtered notice makes that kind always ring
NP.set_mode("cost", "urgent", set_by="owner")
run(main._notify_owner("", "Ngân sách API đã dùng 80%", kind="system", source="cost", level="important"))
cost = items()["Ngân sách API đã dùng 80%"]
r = client.post("/inbox/react", json={"id": cost["id"], "axis": "needed"}).json()
check("'Needed' on a filtered notice: that kind always rings from now on",
      cost.get("filtered") and any(c["to"] == "always" for c in r.get("changes") or []), r)
run(main._notify_owner("", "Ngân sách API đã dùng 85%", kind="system", source="cost", level="important"))
check("...and rings", not items()["Ngân sách API đã dùng 85%"].get("filtered"))

# emoji on a notice opened in Javis Core's chat are Javis Core's feedback on that notice (owner, 2026-10-29)
NP.set_mode("job", "all", set_by="owner")
run(main._notify_owner("", "Việc 'Sao lưu ảnh' xong", kind="answer", quiet=True))
bk = items()["Việc 'Sao lưu ảnh' xong"]
cite = client.post("/javis-core/cite", json={"source": "inbox", "id": bk["id"], "brain": "brain"}).json()
csid = cite.get("id")
cmsg = [m for m in main.get_store().get_messages(csid) if f"javis-cite:inbox:{bk['id']}" in str(m.get("content") or "")]
check("'Open in Javis Core' puts the notice in Core's chat with the item's marker", cite.get("ok") and len(cmsg) == 1, cite)
sent.clear()
rr = client.post(f"/sessions/{csid}/messages/{cmsg[0]['id']}/reaction?brain=brain",
                 json={"value": "angry", "reasons": [], "axis": "should_silent", "comment": "", "nonce": "n-cite-1"})
check("an emoji (and 'should stay quiet') on that chat message reaches Javis Core's judge: that kind is muted",
      rr.status_code == 200 and any(r["rule"] == "mute" and "sao lưu ảnh" in r["sig"] for r in NP.status()["rules"]) and
      any("Sao lưu ảnh" in t for _c, t in sent), (rr.text, NP.status()["rules"], sent))
rr = client.post(f"/sessions/{csid}/messages/{cmsg[0]['id']}/reaction?brain=brain",
                 json={"value": "angry", "reasons": [], "axis": "should_silent", "comment": "", "nonce": "n-cite-1"})
check("the same nonce sent again is a replay and changes nothing more", rr.status_code == 200 and
      len([c for c in NP.status(100)["changes"] if "sao lưu ảnh" in str(c.get("target"))]) == 1)
plain = main.get_store().create_session(brain=KB)
main.get_store().append_message(plain, "assistant", f"Không phải chat Core <!-- javis-cite:inbox:{bk['id']} -->")
pm = main.get_store().get_messages(plain)[-1]
n0 = len(NP.status(100)["changes"])
client.post(f"/sessions/{plain}/messages/{pm['id']}/reaction?brain=brain",
            json={"value": "love", "reasons": [], "axis": "should_speak", "comment": "", "nonce": "n-plain-1"})
check("a reaction in an ordinary chat is not notice feedback, even with the marker", len(NP.status(100)["changes"]) == n0)
NP.set_mode("reminder", "urgent", set_by="owner")
sent.clear()
run(main._notify_owner("", "Nhắc bạn: kiểm kho", kind="report", source="reminder", brain=str(BR)))
rem = items()["Nhắc bạn: kiểm kho"]
check("a notice that lands in Javis Core's chat carries its marker there (so it can take emoji), not on Telegram",
      any(c == "web:" + core and f"javis-cite:inbox:{rem['id']}" in t for c, t in sent) and
      all("javis-cite" not in t for c, t in sent if c == "111"), sent)

# ---- 4. off ----
NP.set_mode("update", "off", set_by="owner")
d = NP.decide("update", "urgent", "Bản vá")
check("the owner's 'off' drops a group, urgent included", d["verdict"] == "drop" and NP.status()["groups"][NP.GROUPS.index("update")]["dropped"] >= 1)
NP.set_mode("agent", "off", set_by="core")
check("Core's 'off' still lets an urgent notice ring and filters the rest",
      NP.decide("agent", "urgent", "Trợ lý A cần bạn")["verdict"] == "loud" and NP.decide("agent", "important", "Trợ lý A nói")["verdict"] == "quiet")
r = client.post("/notify/policy/group", json={"group": "agent", "mode": "important"}).json()
check("route: the owner sets a group's mode", r.get("ok") and NP.mode_of("agent") ["mode"] == "important" and
      NP.mode_of("agent")["set_by"] == "owner")
check("route: an invalid group or mode is refused", client.post("/notify/policy/group", json={"group": "x", "mode": "all"}).status_code == 400)
pol = client.get("/notify/policy").json()
check("route: the policy lists groups, rules and changes with a sentence each",
      pol.get("ok") and len(pol["groups"]) == len(NP.GROUPS) and all(c.get("text") for c in pol["changes"]), pol)
check("the rules store is in the state dir", (Path(STATE) / "notify_policy.json").is_file())

# ---- 5. the chat tool ----
spec = importlib.util.spec_from_file_location("javis_notify_plugin", ROOT / "system/plugins/javis-notify/plugin.py")
plug = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plug)
out = plug._chay({"op": "set", "group": "Kết nối", "mode": "off"}, None)
check("tool: set a group by its shown name", "Kết nối và đăng nhập" in out and NP.mode_of("connection")["mode"] == "off" and
      NP.mode_of("connection")["set_by"] == "owner", out)
out = plug._chay({"op": "mute", "text": "Ngân sách API"}, None)
check("tool: mute a kind found by words of a recent notice", "Đã lọc" in out and
      any(r["rule"] == "mute" and r["group"] == "cost" for r in NP.status()["rules"]), out)
out = plug._chay({"op": "unmute", "text": "Ngân sách API"}, None)
check("tool: unmute removes that kind's rule", "Đã bỏ luật riêng" in out, out)
out = plug._chay({"op": "status"}, None)
check("tool: status lists every group and recent changes", all(NP.group_name(g) in out for g in NP.GROUPS) and "Thay đổi gần đây" in out, out)
cid = NP.status()["changes"][0]["id"]
check("tool: undo by id", plug._chay({"op": "undo", "id": cid}, None).startswith("Đã hoàn tác"))
check("tool: bad input is an error", plug._chay({"op": "set", "group": "xyz", "mode": "all"}, None).startswith("ERROR") and
      plug._chay({"op": "nope"}, None).startswith("ERROR"))
check("the tool is the owner's only (a customer bot never sees it)", "javis_notify" in mcp_hub.OWNER_ONLY_TOOLS)
yml = (ROOT / "system/plugins/javis-notify/plugin.yaml").read_text(encoding="utf-8")
check("the plugin ships enabled at the safe level", "slug: javis-notify" in yml and "enabled: true" in yml and "min_mode: safe" in yml)
core_md = (ROOT / "system/agents/javis-core.md").read_text(encoding="utf-8")
check("Javis Core's role says it is the notification commander and uses javis_notify", "javis_notify" in core_md)

# ---- 6. the bell ----
js = (ROOT / "dashboard/notifications.js").read_text(encoding="utf-8")
html = (ROOT / "dashboard/index.html").read_text(encoding="utf-8")
vi = json.loads((ROOT / "dashboard/i18n/vi.json").read_text(encoding="utf-8"))
en = json.loads((ROOT / "dashboard/i18n/en.json").read_text(encoding="utf-8"))
check("bell: filtered notices leave the main list for a 'Filtered (N)' view",
      "!!x.filtered === loc" in js and '"noti.filtered_n"' in js and "data-noti-filtered" in js)
check("bell: only Needed / Not needed on a notice, sent to /inbox/react; no emoji there (they go on it in Javis Core)",
      'data-react-a="needed"' in js and 'data-react-a="not_needed"' in js and '"/inbox/react"' in js and
      "JavisReactions" not in js and "data-react-v" not in js and "noti-emo" not in js)
check("bell: a Filter tab with each group's mode, rules and undo", 'id="notiTabFilter"' in html and '"/notify/policy/group"' in js and
      '"/notify/policy/undo"' in js and '"/notify/policy/rule"' in js)
keys = set()
import re  # noqa: E402
for m in re.finditer(r'"(noti\.[a-z_]*[a-z])"', js):
    keys.add(m.group(1))
keys |= {f"noti.grp_{g}" for g in NP.GROUPS} | {f"noti.mode_{m}" for m in NP.MODES} | {"noti.filter_btn"}
miss = sorted(k for k in keys if k not in vi or k not in en)
check("every noti.* key the bell uses is in vi and en", not miss, miss)
check("long explanations sit behind (i): the filter's text is only in an info pair", "JavisInfo.pair(" in js and
      len(vi["noti.filter_info"]) > 100)
check("short texts stay under 100 characters", all(len(vi[k]) <= 100 and len(en[k]) <= 100 for k in keys if k != "noti.filter_info"),
      [k for k in keys if k != "noti.filter_info" and (len(vi.get(k, "")) > 100 or len(en.get(k, "")) > 100)])
check("English writes AI plainly, no 'A.I.'", not any("A.I." in en[k] for k in keys))
def _ver(name):
    m = re.search(re.escape(name) + r"\?v=(\d+)", html)
    return int(m.group(1)) if m else 0


# At least the 0.403.0 versions: a later release bumps them again, so an exact number would break on every bump.
check("cache versions bumped", _ver("notifications.js") >= 11 and _ver("style.css") >= 151)

dashes = [chr(0x2014), chr(0x2013)]
texts = [Path(__file__).read_text(encoding="utf-8"), (SERVER / "notify_policy.py").read_text(encoding="utf-8"),
         (ROOT / "system/plugins/javis-notify/plugin.py").read_text(encoding="utf-8"), yml] + [vi[k] + en[k] for k in keys]
check("no em or en dash in the new code and strings", not any(d in t for t in texts for d in dashes))

print()
if fails:
    raise SystemExit(f"FAIL {len(fails)}: " + "; ".join(fails[:6]))
print("TẤT CẢ PASS")
