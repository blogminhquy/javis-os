"""18/11/2026: a message the owner adds in the team chat reaches the member at once.

    python tests/run.py team_steer_merge

Owner: "trong chức năng team khi nhồi thêm lệnh vào chat thì agent đang không đọc ngay mà phải đợi xử lý câu trên rồi mới
đọc câu dưới, anh muốn câu mới nạp ngay vào ngữ cảnh để phó nhóm có thể thay đổi cách làm việc".

1. A newer owner message to a member stops that member's reply to the earlier message (no answer yet) and one turn answers
   both, the newest last. The earlier reply ends `done` with reason `merged`, never an error with Try again.
2. A reply whose answer is already in (sealed) is not stopped: it posts, the newer one answers after.
3. A member running a tool step of a job reads the owner's message at its next tool call (steer_inbox), the waiting reply
   says so, and the reply turn after the step only confirms what changed.
4. The deputy row in the team settings stands out (dashboard).
5. Owner, same day: "khi mà 1 câu xin duyệt đã được trả lời cần tự tắt thông báo đi vì đã xử lý rồi". The approval notice
   is filed under a key; a Reply (Ask) on the card, or any decision that closes it, turns that notice read.

Fake engines only, no model call.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-steer-")
STATE = Path(os.environ["JAVIS_STATE_DIR"])

import sessions  # noqa: E402
import steer_inbox  # noqa: E402
import task_store  # noqa: E402
import team_store  # noqa: E402
import team_runner as TR  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


AGENTS = {"ag_an": ("an", "An"), "ag_binh": ("binh", "Binh")}


class Fake:
    def __init__(self):
        self.calls = []
        self.gates = {}      # agent_key -> list of asyncio.Event the next calls wait on

    def engine_for(self, team, agent_key, role):
        async def run(req):
            self.calls.append(req)
            gates = self.gates.get(agent_key) or []
            if gates:
                await gates.pop(0).wait()
            return {"text": f"{agent_key} answer {len(self.calls)}", "tokens_in": 1, "tokens_out": 1}
        return "fake", "fake-model", run


def world(name):
    d = STATE / name
    d.mkdir()
    ss = sessions.SessionStore(db_path=d / "sessions.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    fake = Fake()

    def agent_info(brain, key):
        slug, nm = AGENTS[key]
        return {"slug": slug, "name": nm, "system": f"You are {nm}."}

    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=fake.engine_for, agent_info=agent_info,
                      publish=lambda ev: None, notify=lambda team_id, text: None)
    tid = team_store.new_team_id()
    sid = ss.create_session(brain="B", channel=f"team:{tid}", title=name)
    tm.create_team("B", name, "", sid, team_id=tid)
    for k in AGENTS:
        tm.add_member(tid, k, AGENTS[k][0])
    tm.set_leader(tid, "ag_an")
    return ss, tm, fake, r, tm.get(tid)


def agent_msgs(ss, team):
    rows = ss.get_team_messages_page(team["session_id"], limit=200)["messages"]
    return [m for m in rows if m.get("author_kind") == "agent"]


async def until(cond, n=400):
    for _ in range(n):
        if cond():
            return True
        await asyncio.sleep(0.01)
    return False


# ---------- 1. a newer message stops the earlier reply and one turn answers both ----------
ss, tm, fake, r, T = world("merge")


async def merge_case():
    gate = asyncio.Event()
    fake.gates["ag_an"] = [gate]          # the first answer hangs: the model is still writing
    a = r.submit(T["team_id"], "Text on the images should be short and in English", client_msg_id="m1")
    check("a fresh owner message may fold earlier ones", a.get("merge") is True, a)
    ta = asyncio.ensure_future(r.run_message(a))
    await until(lambda: len(fake.calls) == 1)
    b = r.submit(T["team_id"], "It is an international project", client_msg_id="m2")
    tb = asyncio.ensure_future(r.run_message(b))
    await asyncio.gather(ta, tb)
    return a, b


a, b = asyncio.run(merge_case())
row_a = tm.reply(T["team_id"], a["message_id"], "ag_an")
row_b = tm.reply(T["team_id"], b["message_id"], "ag_an")
check("1 the earlier reply ends done, reason merged, pointing at the newer message",
      row_a["status"] == "done" and row_a["reason"] == "merged" and row_a["detail"] == str(b["message_id"]), row_a)
check("1 the newer reply is answered", row_b["status"] == "done" and row_b["result_msg_id"], row_b)
check("1 two model calls: the stopped one and the one that answers", len(fake.calls) == 2, len(fake.calls))
last = fake.calls[-1]["prompt"]
check("1 the answering turn reads both messages, oldest first",
      "Text on the images should be short" in last and "international project" in last
      and last.index("Text on the images") < last.index("international project"), last[-600:])
check("1 the answering turn is told the last message wins", "LAST one is the newest" in last)
posted = agent_msgs(ss, T)
check("1 exactly one answer posted, as a reply to the newer message",
      len(posted) == 1 and posted[0]["reply_to"] == b["message_id"], [(m["id"], m["reply_to"]) for m in posted])
check("1 the stopped turn is not counted as ok", [t["status"] for t in tm.turns(T["team_id"])].count("ok") == 1,
      [t["status"] for t in tm.turns(T["team_id"])])

# A Try again of an old message never folds newer ones (no `merge` flag).
check("retry submitted carries no merge flag", "merge" not in (r.retry_reply(T["team_id"], a["message_id"], "ag_an") or {}))

# ---------- 2. an answer already in is not thrown away ----------
ss, tm, fake, r, T = world("sealed")


async def sealed_case():
    a = r.submit(T["team_id"], "First question", client_msg_id="s1")
    # The engine answered (on_result sealed the turn), then posting takes a while: a newer message arrives meanwhile.
    entry_seen = {}
    real_accept = r._accept
    accept_gate = asyncio.Event()
    orig_io = r._io

    async def io(fn, *args, **kw):
        if fn == real_accept and not entry_seen:
            entry_seen["held"] = True
            await accept_gate.wait()
        return await orig_io(fn, *args, **kw)

    r._io = io
    ta = asyncio.ensure_future(r.run_message(a))
    await until(lambda: entry_seen.get("held"))
    b = r.submit(T["team_id"], "Second question", client_msg_id="s2")
    tb = asyncio.ensure_future(r.run_message(b))
    await asyncio.sleep(0.05)
    accept_gate.set()
    await asyncio.gather(ta, tb)
    return a, b


a, b = asyncio.run(sealed_case())
check("2 the sealed answer is posted (not merged)", tm.reply(T["team_id"], a["message_id"], "ag_an")["status"] == "done"
      and tm.reply(T["team_id"], a["message_id"], "ag_an")["reason"] != "merged",
      tm.reply(T["team_id"], a["message_id"], "ag_an"))
check("2 the newer message gets its own answer", len(agent_msgs(ss, T)) == 2 and
      tm.reply(T["team_id"], b["message_id"], "ag_an")["status"] == "done")
check("2 the newer turn only carries its own message", "First question" not in fake.calls[-1]["prompt"].split(
      "The team owner just wrote")[-1], fake.calls[-1]["prompt"][-400:])

# ---------- 3. a running tool step reads the owner's message ----------
ss, tm, fake, r, T = world("steer")


async def steer_case():
    req = {}
    with r._steer_open(T["team_id"], "ag_an", req):
        check("3 the step gets its inbox key", req.get("steer_sid") == r.steer_sid(T["team_id"], "ag_an"))
        steer_inbox.INBOX.attach_tag(req["steer_sid"], "team-abc-turn1")
        check("3 the Claude Code hook finds the step by its tag", steer_inbox.INBOX.has_tag("team-abc-turn1"))
        a = r.submit(T["team_id"], "Use English text on every image", client_msg_id="t1")
        # The reply is queued and claimed (it waits for the member) while the step runs.
        att = tm.claim_reply(T["team_id"], a["message_id"], "ag_an")
        check("3 the message is handed to the running step", r._steer_into_step(
            T["team_id"], "ag_an", a["message_id"], "Use English text on every image"))
        note = steer_inbox.INBOX.take_note_for_tag("team-abc-turn1")
        check("3 the step reads the owner's own words", "Use English text on every image" in note, note)
        await asyncio.sleep(0.05)
        await r.wait_background()
        row = tm.reply(T["team_id"], a["message_id"], "ag_an")
        check("3 the waiting reply says it was read mid-way", row["status"] == "running" and row["reason"] == "steered",
              row)
        body = r._reply_body(T["team_id"], "ag_an", a["message_id"], [(a["message_id"], "Use English text")])
        check("3 the reply after the step only confirms", "You already read" in body, body)
        tm.settle_reply(T["team_id"], a["message_id"], "ag_an", "done", attempt=att)
    check("3 the inbox closes with the step", not steer_inbox.INBOX.running(req["steer_sid"])
          and not steer_inbox.INBOX.has_tag("team-abc-turn1"))
    check("3 no step running: nothing is handed over", not r._steer_into_step(T["team_id"], "ag_an", 999, "x"))


asyncio.run(steer_case())

import claude_sdk_engine  # noqa: E402

# The Claude engine file is pinned by its native qualification (test_plan_limits CANARY): the team step switches the
# steer hook on per engine in main._team_engine_for, and the hook itself reads by tag.
SRC_MAIN = (SERVER / "main.py").read_text(encoding="utf-8")
check("3 the team step switches the Claude steer hook on for its own engine only",
      "eng._steer_on = lambda _t=tag: steer_inbox.INBOX.has_tag(_t)" in SRC_MAIN)
check("3 the Claude steer hook reads the turn by its tag", "take_note_for_tag(self.tag)" in
      (SERVER / "claude_sdk_engine.py").read_text(encoding="utf-8"))
tok = steer_inbox.INBOX.open("team:x:y")
steer_inbox.INBOX.attach_tag("team:x:y", "team-zzz-turn9")
steer_inbox.INBOX.put("team:x:y", "change the plan")
check("3 a note put for the step is read by the engine tag", "change the plan" in
      steer_inbox.INBOX.take_note_for_tag("team-zzz-turn9"))
steer_inbox.INBOX.close("team:x:y", token=tok)
check("3 closing the step forgets its tag", not steer_inbox.INBOX.has_tag("team-zzz-turn9"))

# ---------- 4. dashboard: the deputy stands out, new reply states have words ----------
JS = (ROOT / "dashboard" / "teams.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8")
import json  # noqa: E402
VI = json.loads((ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8"))
EN = json.loads((ROOT / "dashboard" / "i18n" / "en.json").read_text(encoding="utf-8"))
check("4 the deputy row has its own class and badge", "tm-mrow-lead" in JS and "tm-lead-badge" in JS
      and ".tm-mrow-lead" in CSS and ".tm-lead-badge" in CSS)
check("4 the deputy is listed first among members", "b.agent_key === team.leader_key" in JS)
for k in ("teams.leader_role", "teams.reply.steered", "teams.reply.merged"):
    check(f"4 i18n {k} in vi and en", bool(VI.get(k)) and bool(EN.get(k)))
check("4 merged replies keep one quiet line", 'x.reason === "merged"' in JS and ".tm-reply-merged" in CSS)
check("no em dash in the new words", not any("—" in str(d.get(k, "")) or "–" in str(d.get(k, ""))
                                             for d in (VI, EN) for k in ("teams.leader_role", "teams.reply.steered",
                                                                         "teams.reply.merged")))

# ---------- 5. an answered approval request stops ringing ----------
ss, tm, fake, r, T = world("approval")
sent, done = [], []
r._notify_fn = lambda team_id, text, ref="": sent.append((team_id, text, ref))
r.notice_done = done.append
ap = r.approvals.create(team_id=T["team_id"], task_id="job1", step_id="st1", team_rev=1, requested_by="ag_an",
                        kind="question", title="Swap 3 product photos", action="Replace the photos")
r._approval_card(T, "job1", "st1", None, ap)
ref = TR.TeamRunner.approval_ref(ap["approval_id"])
check("5 the approval notice is filed under its own key", sent and sent[-1][2] == ref, sent)
check("5 a Reply (Ask) on the card clears its notice", r.approval_answered(T["team_id"], ap["approval_id"])
      and done == [ref], done)
check("5 a card of another team is not touched", not r.approval_answered("tm_other", ap["approval_id"]))
done.clear()
r._refresh_card(T, r.approvals.get(ap["approval_id"]))
check("5 a pending card that is redrawn keeps its notice", done == [], done)
r.approvals.close_task("job1", "cancelled", "job ended", ("pending",))
r._refresh_card(T, r.approvals.get(ap["approval_id"]))
check("5 a closed request clears its notice", done == [ref], done)
# A host notify without `ref` (older code, other tests) still gets the notice.
plain = []
r._notify_fn = lambda team_id, text: plain.append(text)
r._notify(T["team_id"], "hello", ref="x")
check("5 a notify without ref still delivers", plain == ["hello"], plain)

import inbox  # noqa: E402
a1 = inbox.add("Team asks for approval: A", dedup=ref)
a2 = inbox.add("Team asks for approval: B", dedup="team-approval:other")
check("5 the bell marks only that request's notice read", inbox.read_by_dedup(ref) == 1
      and inbox.lay(a1["id"]).get("read") and not inbox.lay(a2["id"]).get("read"))
check("5 an empty key clears nothing", inbox.read_by_dedup("") == 0)
check("5 the dashboard sends the card id with a Reply", "approval_id: d.ap" in JS)
check("5 the host wires notify(ref) to the bell's dedup and clears it", "dedup=str(ref or \"\")" in SRC_MAIN
      and "notice_done=_team_notice_done" in SRC_MAIN)

print(f"\n{'FAIL' if fails else 'OK'}: {len(fails)} failed")
raise SystemExit(1 if fails else 0)
