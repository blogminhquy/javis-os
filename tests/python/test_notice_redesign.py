"""The bell redesign, step 1 (owner, 19/11/2026: "the notices are hard to read, people skip them, Javis sends far too
many, even when there is nothing to do"; then: "answers of partners, chats and teams need no notification, a red dot on
the menu is enough").

    python tests/run.py notice_redesign

- notice_text: a headline skips lines that narrate the work, a JAVIS_NOTIFY block gives the title and is never shown;
- a scheduled job that ran fine is a result: delivered to its chat or channel, never a red dot in the bell; it rings
  only when the run says the owner must act; a final failure rings, a network retry does not; a plain reminder rings;
- a notice whose content sits in a chat with its own unread dot is not filed in the bell, unless it needs the owner;
- GET /sessions/unread-summary and GET /teams/unread feed the red dots on the rail (rail-unread.js, index.html).
No network, no model.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="javis-notice-redesign-")
os.environ["JAVIS_STATE_DIR"] = STATE
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import notice_text as NT  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── 1. notice_text ──────────────────────────────────────────────────────────────────────────────────────────────────
seen = "Em kiểm tra hướng dẫn và lượt nhắc đến hạn, rồi đối chiếu lịch sử khách trước khi gửi."
check("the line from the owner's screenshot is narration", NT.is_narration(seen))
check("narration only -> the fallback headline", NT.headline(seen, "Nhắc khách: đã chạy xong") == "Nhắc khách: đã chạy xong")
check("a done line is not narration", not NT.is_narration("Em đã gửi 3 tin nhắc cho khách"))
check("a request to the owner is not narration", not NT.is_narration("Tôi cần bạn duyệt đơn này"))
check("English openers are narration", NT.is_narration("I'll check the list first") and NT.is_narration("Let me look"))
body = ("Em kiểm tra lượt đến hạn.\n\n**Đã gửi 2 tin nhắc** cho khách đến hạn hôm nay.\n- Chị Lan: gia hạn\n"
        '<!-- JAVIS_NOTIFY: {"title": "Đã nhắc 2 khách đến hạn", "line": "Chị Lan, anh Tú", "act": false} -->')
clean, meta = NT.split_block(body)
check("the block is taken out of the text", "JAVIS_NOTIFY" not in clean and "Đã gửi 2 tin nhắc" in clean, clean)
check("the block gives title, line and act", meta == {"title": "Đã nhắc 2 khách đến hạn", "line": "Chị Lan, anh Tú",
                                                      "act": False}, meta)
check("without the block the headline is the first reporting line",
      NT.headline(clean) == "Đã gửi 2 tin nhắc cho khách đến hạn hôm nay.", NT.headline(clean))
check("the summary is the next reporting line", NT.summary(clean, NT.headline(clean)) == "Chị Lan: gia hạn")
broken, m2 = NT.split_block("Kết quả\n<!-- JAVIS_NOTIFY: {not json} -->")
check("a broken block is removed and ignored", broken == "Kết quả" and m2 == {}, (broken, m2))
check("act true is read", NT.split_block('x <!-- JAVIS_NOTIFY: {"title":"t","act":true} -->')[1]["act"] is True)
check("a long job name is cut at a word", NT.short_name("Theo dõi phản hồi nhóm Zalo học viên và báo cáo các phàn "
                                                         "nàn mới đáng chú ý mỗi giờ").endswith("…"))

# ── 2. scheduled jobs (reminders._bell_notice and the firing) ──────────────────────────────────────────────────────
import reminders  # noqa: E402

n = reminders._bell_notice("done", "Nhắc khách", seen, {})
check("a job that ran fine: group job, info (no red dot)", n["group"] == "job" and n["level"] == "info", n)
check("a job that only narrated gets a name-based title", n["title"].startswith("Nhắc khách"), n)
n = reminders._bell_notice("done", "Nhắc khách", clean, {"title": "Khách Lan khiếu nại", "line": "", "act": True})
check("act from the run rings", n["level"] == "urgent" and n["title"] == "Khách Lan khiếu nại", n)
check("a final failure rings", reminders._bell_notice("failed", "Nhắc khách", "boom\nengine timeout", {})["level"] == "urgent")
check("the failure summary is its last line",
      reminders._bell_notice("failed", "Nhắc khách", "boom\nengine timeout", {})["summary"] == "engine timeout")
check("a network retry does not ring", reminders._bell_notice("retrying", "Nhắc khách", "timeout", {}, at="09:05")["level"] == "info")

sent = []


async def fake_send(chat_id, text, viec=None, web="", brain="", dedup="", notice=None):
    sent.append({"chat": chat_id, "text": text, "notice": notice or {}})
    return True, ""


brain = Path(tempfile.mkdtemp(prefix="javis-notice-brain-"))
deps = reminders.RemindersDeps(
    brain_root=lambda _b: str(brain), atomic_write_text=lambda p, t: Path(p).write_text(t, encoding="utf-8"),
    send_telegram=fake_send, build_system_prompt=lambda _b: "", aux_model=lambda: None,
    safe_tools=[], readonly_tools=[], scheduler_brains=lambda: [])
feat = reminders.RemindersFeature(deps)


async def task_ok(_b, _t, _m="", **_kw):
    return body, ""

feat._run_task = task_ok
run(feat._fire(str(brain), {"id": "r1", "mode": "task", "text": "Nhắc khách đến hạn", "label": "Nhắc khách", "chat_id": "web:x"}))
check("the channel never sees the block", "JAVIS_NOTIFY" not in sent[-1]["text"], sent[-1]["text"])
check("the firing passes the run's own headline to the bell",
      sent[-1]["notice"].get("title") == "Đã nhắc 2 khách đến hạn" and sent[-1]["notice"].get("level") == "info",
      sent[-1]["notice"])
run(feat._fire(str(brain), {"id": "r2", "mode": "notify", "text": "Gọi nhà cung cấp", "chat_id": "web:x"}))
check("a plain reminder keeps the reminder group (rings)", sent[-1]["notice"].get("group") == "reminder", sent[-1]["notice"])

src = (Path(SERVER) / "reminders.py").read_text(encoding="utf-8")
check("the job prompt asks for the headline block", "notice_text.PROMPT" in src)

# ── 3. main: delivery, bell, dots ───────────────────────────────────────────────────────────────────────────────────
import inbox  # noqa: E402
import main  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

main.cfgmod.gate_active = lambda: False
BR = Path(tempfile.mkdtemp(prefix="javis-notice-main-"))
KB = main._brain_key(str(BR))
cfg = main.cfgmod.read_settings()
cfg["telegram"] = {"enabled": True, "token": "x", "chat_id": "111", "owner_chat_id": "111"}
main.cfgmod.write_settings(cfg)
out = []


async def fake_channel(owner_chat, text, **_kw):
    out.append((owner_chat, text))
    return True, ""

main._gui_qua_kenh = fake_channel
events = []


async def fake_publish(ev):
    events.append(ev)

main._CHAT_RUNTIME.publish = fake_publish
pushes = []


async def fake_push(*a, **k):
    pushes.append(a)
    return 0

main.webpush.gui_het = fake_push


def items():
    return {x["title"]: x for x in inbox.danh_sach(500)}


# A scheduled job with no chat: still delivered to the owner's Telegram, but no red dot and no push.
run(main._bao_nhac_hen("", "Doanh thu hôm nay 12 đơn", brain=str(BR),
                       notice={"title": "Doanh thu hôm nay: 12 đơn", "group": "job", "level": "info"}))
it = items().get("Doanh thu hôm nay: 12 đơn") or {}
check("a scheduled job's result still goes to the owner's Telegram", "111" in [o[0] for o in out], out)
check("... lands in Javis Core's chat (its own red dot), not in the bell, no push",
      any(o[0].startswith("web:") for o in out) and not it and not pushes, (it, out, pushes))
out.clear()
run(main._bao_nhac_hen("", "Khách Lan khiếu nại", brain=str(BR),
                       notice={"title": "Khách Lan khiếu nại", "summary": "Đòi hoàn tiền", "group": "job", "level": "urgent"}))
it = items().get("Khách Lan khiếu nại") or {}
check("a run that says the owner must act rings", it and not it.get("read") and it.get("summary") == "Đòi hoàn tiền", it)

# A JAVIS_NOTIFY block reaching _notify_owner directly (webhook, any producer): taken out, used as the title.
sid = main.get_store().create_session(brain=KB)
out.clear()
run(main._notify_owner("web:" + sid, 'Đã xử lý.\n<!-- JAVIS_NOTIFY: {"title": "Webhook: 1 đơn mới", "act": true} -->',
                       kind="report", source="webhook"))
check("no channel ever shows the block", out and all("JAVIS_NOTIFY" not in o[1] for o in out), out)
check("act in the block files an urgent notice with its title", (items().get("Webhook: 1 đơn mới") or {}).get("level") == "urgent")

# A plain answer in a chat with its own dot: not in the bell, the rail hears about it.
n0 = len(inbox.danh_sach(500))
events.clear()
run(main._notify_owner("web:" + sid, "Câu trả lời của cộng sự", kind="answer"))
check("a plain answer in a chat is not filed in the bell", len(inbox.danh_sach(500)) == n0)
check("... and fires chat_unread for the rail dot", any(e.get("type") == "chat_unread" for e in events), events)
out.clear()
run(main._notify_owner("web:" + sid, "Kết quả việc nền", kind="answer", dedup="task:x:done:1"))
run(main._notify_owner("web:" + sid, "Kết quả việc nền", kind="answer", dedup="task:x:done:1"))
check("CANARY: a hidden notice still stops a retried report from posting twice", len(out) == 1, out)
check("the hidden notice is kept, read, out of the bell list",
      any(x.get("hidden") and x.get("read") for x in inbox.danh_sach(500, include_hidden=True))
      and not any(x.get("hidden") for x in inbox.danh_sach(500)))
team_sid = main.get_store().create_session(brain=KB, channel="team:t1")
run(main._bo_vao_hom_thu("web:" + team_sid, "Việc nhóm bị chặn", kind="report", source="team", group="team",
                         level="important"))
check("a team notice that does not ask the owner stays out of the bell", "Việc nhóm bị chặn" not in items())
run(main._bo_vao_hom_thu("web:" + team_sid, "Phó nhóm xin duyệt", kind="report", source="team", group="question",
                         level="urgent"))
check("a team approval request still rings", "Phó nhóm xin duyệt" in items())
run(main._bo_vao_hom_thu("", "Bot Zalo mất kết nối", kind="system", source="zalo", level="urgent"))
check("a system notice with no chat is still filed", "Bot Zalo mất kết nối" in items())

# The counts behind the rail dots.
client = TestClient(main.app, base_url="http://127.0.0.1")
store = main.get_store()
c1 = store.create_session(brain=KB)
store.append_message(c1, "user", "hi")
store.append_message(c1, "assistant", "chào anh")
a1 = store.create_session(brain=KB, channel="agent:viet-email")
store.append_message(a1, "assistant", "em đã soạn xong")
r = client.get("/sessions/unread-summary", params={"brain": str(BR)}).json()
check("unread summary counts chat and partner chats", r.get("ok") and r.get("chat", 0) >= 1 and r.get("workspace") == 1, r)
store.mark_read(a1)
r2 = client.get("/sessions/unread-summary", params={"brain": str(BR)}).json()
check("reading the partner chat clears its count", r2.get("workspace") == 0, r2)
t = client.get("/teams/unread", params={"brain": str(BR)}).json()
check("teams unread answers", t.get("ok") is True and "teams" in t, t)

# ── 4. dashboard ────────────────────────────────────────────────────────────────────────────────────────────────────
D = Path(ROOT) / "dashboard"
html = (D / "index.html").read_text(encoding="utf-8")
check("the rail draws a red dot per entry and per folded group",
      'x-show="$store.nav.unread[it.id]"' in html and "$store.nav.groupUnread(g)" in html)
check("rail-unread.js is loaded", "/static/rail-unread.js" in html)
ru = (D / "rail-unread.js").read_text(encoding="utf-8")
check("rail-unread.js reads both counts", "/sessions/unread-summary" in ru and "/teams/unread" in ru)
check("rail-unread.js listens to chat, partner and team events",
      all(e in ru for e in ("javis:session-read", "javis:agent-read", "javis:team-event", "javis:chat-activity")))
app = (D / "app.js").read_text(encoding="utf-8")
check("app.js turns chat_unread into javis:chat-activity", '"chat_unread"' in app and "javis:chat-activity" in app)
nj = (D / "notifications.js").read_text(encoding="utf-8")
check("a card shows the summary line, not the title twice", "function dongPhu(item)" in nj and "item.summary" in nj)
check("a title cut at 120 characters drops its whole first line, no cut-off tail under it",
      'than.indexOf("\\n")' in nj and "than.slice(tieuDe.length)" not in nj)
css = (D / "console.css").read_text(encoding="utf-8")
check("rail rows span the drawer on a phone, so the dots line up on the right",
      "position: relative; width: 100%; background: transparent" in css)

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
