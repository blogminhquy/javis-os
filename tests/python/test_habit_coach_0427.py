"""Habit coach and Google Calendar on the Tasks page (0.427.0).

Expected:
  - Core's answer is read as JSON; a line too long, with a long dash, or with a placeholder its key may not use is
    dropped (the fixed line stays); habits that do not exist are ignored;
  - the prompt carries each habit's state and how each nudge style worked so far;
  - refresh_coach saves today's lines; GET /my-tasks returns them (without the log);
  - the daily reminder uses Core's nudge for that habit, logs its style, and ticking the habit that day marks the
    nudge as followed, which the next prompt counts;
  - no model, or a model error: nothing is saved and the fixed lines stay;
  - gcal_read finds a calendar connection and its list tool, fills the time window from the tool's own schema,
    reads JSON answers and workspace-mcp's plain lines, skips cancelled events, and says "not connected" without one;
  - GET /my-tasks/calendar caches for five minutes.

Run:
    python tests/python/test_habit_coach_0427.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (see tests/python/_paths.py)
import asyncio
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import gcal_read  # noqa: E402
import my_tasks  # noqa: E402

fails = []


def check(name, cond, info=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not info else f"  [{info}]"))
    if not cond:
        fails.append(name)


# ---- parsing Core's answer ----
ans = """Sure: {"head": {"all": "Xong cả {n}, mình tự hào ghê", "part": "Còn {left} thôi, cố lên {bad}",
 "mile": "Thêm {left} ngày là chạm mốc {n} của {name}", "week": "x""" + "y" * 200 + """"},
 "habits": {"m_a": {"frozen": "{name} đang đóng băng, chuỗi {n} ngày chờ bạn", "nudge": "Mình chờ {name} nãy giờ — làm đi mà", "style": "sulk"},
            "m_ghost": {"nudge": "x"}}}"""
got = my_tasks.parse_coach(ans, {"m_a"})
check("JSON inside prose is read", bool(got))
check("a line with a placeholder its key may not use is dropped", "part" not in got["head"], got["head"])
check("a line too long is dropped", "week" not in got["head"])
check("good lines are kept", got["head"].get("all", "").startswith("Xong cả {n}") and "{left}" in got["head"].get("mile", ""))
check("the long dash becomes a comma", "—" not in got["habits"]["m_a"]["nudge"] and ", làm đi mà" in got["habits"]["m_a"]["nudge"])
check("a habit that does not exist is ignored", "m_ghost" not in got["habits"])
check("the nudge keeps its style", got["habits"]["m_a"]["style"] == "sulk")
check("an answer with no JSON is refused", my_tasks.parse_coach("I cannot help", {"m_a"}) is None)
check("fill() puts today's numbers in", my_tasks.fill("Chuỗi {n} ngày của {name}", n=5, name="đọc sách") == "Chuỗi 5 ngày của đọc sách")

log = [{"style": "sulk", "sent": 1, "done": 2}, {"style": "sulk", "sent": 1, "done": 0}, {"style": "cheer", "sent": 1, "done": 0},
       {"style": "fixed", "sent": 1, "done": 1}]
stats = my_tasks.style_stats(log)
check("style stats count sends and follow-ups", stats["sulk"] == {"sent": 2, "done": 1} and stats["cheer"] == {"sent": 1, "done": 0})
p = my_tasks.coach_prompt([{"id": "m_a", "title": "Đọc sách", "cur": 4, "frozen": True, "done_today": False, "rest": False,
                            "usual": "21:10", "last14": "ffffffffffffit"}], stats, True)
check("the prompt carries the habit's state", "id=m_a" in p and "streak 4" in p and "frozen=true" in p and "21:10" in p)
check("the prompt carries what worked", "sulk: sent 2, done after 1" in p)
check("the prompt asks for Vietnamese with bạn/mình", "Vietnamese" in p and "bạn" in p)
check("the prompt itself has no long dash", "—" not in p and "–" not in p)

# ---- refresh, tick, check, GET ----
brain = Path(tempfile.mkdtemp(prefix="javis-coach-"))


def atomic_write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


sent, asked = [], []


async def notify(chat_id, text, brain="", dedup=""):
    sent.append((text, dedup))
    return True, ""


async def ask(prompt):
    asked.append(prompt)
    return json.dumps({"head": {"all": "Xong hết {n} rồi!", "start": "Bắt đầu thôi"},
                       "habits": {"m_due": {"nudge": "{name}: chuỗi {n} ngày đang đợi bạn đó nha", "style": "challenge",
                                            "frozen": "{name} đóng băng rồi"}}})

# A zone where it is about noon now, so the 05:00 coach gate and the 00:00 reminder are both open whenever this runs.
_utc = datetime.now(timezone.utc)
TZ = timezone(timedelta(hours=12 - _utc.hour))
now = datetime.now(TZ)
today = now.date().isoformat()
feat = my_tasks.MyTasks(my_tasks.MyTasksDeps(brain_root=lambda b: str(brain), atomic_write_text=atomic_write,
                                             scheduler_brains=lambda: [], notify=notify, tz=lambda: TZ, ask=ask))
feat.save("brain", {"rev": 0, "projects": [], "tasks": [
    {"id": "m_due", "title": "Read 30 minutes", "date": today, "repeat": {"unit": "day", "n": 1},
     "habit": {"start": today, "remind": "time", "at": "00:00"}, "done_dates": {}},
    {"id": "m_plain", "title": "Pay bills", "date": today, "repeat": {"unit": "day", "n": 1}, "habit": None, "done_dates": {}}]})

check("refresh_coach saves today's lines", asyncio.run(feat.refresh_coach("brain", today)) is True)
c = feat.load_coach("brain")
check("the store holds today's date, head and habit lines",
      c["date"] == today and c["head"]["all"] == "Xong hết {n} rồi!" and c["habits"]["m_due"]["style"] == "challenge")
check("only habits go into the prompt", "m_due" in asked[0] and "m_plain" not in asked[0])

feat._coach_tried.clear()
asyncio.run(feat.tick())
check("the reminder uses Core's nudge with today's numbers", sent and sent[0][0] == "Read 30 minutes: chuỗi 0 ngày đang đợi bạn đó nha", sent)
check("Core is not asked again the same day (lines already saved)", len(asked) == 1)
entry = (feat.load_coach("brain")["log"] or [{}])[-1]
check("the nudge is logged with its style", entry.get("id") == "m_due" and entry.get("style") == "challenge" and not entry.get("done"))
feat.check("brain", "m_due", today, "me", True)
entry = feat.load_coach("brain")["log"][-1]
check("ticking the habit that day marks the nudge as followed", bool(entry.get("done")))
check("and the next prompt counts it", my_tasks.style_stats(feat.load_coach("brain")["log"])["challenge"] == {"sent": 1, "done": 1})

app = FastAPI()
app.include_router(feat.router)
cl = TestClient(app)
r = cl.get("/my-tasks", params={"brain": "brain"}).json()
check("GET /my-tasks returns today's coach lines", r["coach"]["date"] == today and r["coach"]["head"]["all"] == "Xong hết {n} rồi!")
check("with the frozen line per habit, but not the log or nudges", r["coach"]["habits"] == {"m_due": {"frozen": "{name} đóng băng rồi"}}
      and "log" not in r["coach"])


async def broken(prompt):
    raise RuntimeError("background engine not ready")

feat2 = my_tasks.MyTasks(my_tasks.MyTasksDeps(brain_root=lambda b: str(brain), atomic_write_text=atomic_write, ask=broken))
before = feat2.load_coach("brain")
check("no model: nothing saved, fixed lines stay", asyncio.run(feat2.refresh_coach("brain", today)) is False
      and feat2.load_coach("brain") == before)

# ---- gcal_read ----
check("the Google Calendar connector counts as a calendar", gcal_read.is_calendar({"connector_id": "google-calendar"}))
check("a custom connection named calendar counts", gcal_read.is_calendar({"connector_id": "custom", "label": "Lịch công ty (Calendar)"}))
check("Gmail does not", not gcal_read.is_calendar({"connector_id": "gmail", "label": "Gmail"}))
tools = [{"name": "create_event"}, {"name": "list_calendars"},
         {"name": "list_events", "inputSchema": {"properties": {"calendarId": {}, "timeMin": {}, "timeMax": {}, "maxResults": {}},
                                                 "required": ["calendarId"]}}]
tool = gcal_read.pick_tool(tools)
check("list_events is picked, never create_event", tool and tool["name"] == "list_events")
check("a read tool about events is found by its name", gcal_read.pick_tool([{"name": "delete_event"}, {"name": "get_upcoming_events"}])["name"] == "get_upcoming_events")
args = gcal_read.build_args(tool, "2026-10-31T00:00:00+07:00", "2026-11-14T00:00:00+07:00", {})
check("the time window and calendar fill the tool's own argument names",
      args == {"calendarId": "primary", "timeMin": "2026-10-31T00:00:00+07:00", "timeMax": "2026-11-14T00:00:00+07:00", "maxResults": 100})
ws = {"name": "get_events", "inputSchema": {"properties": {"user_google_email": {}, "time_min": {}, "time_max": {}},
                                            "required": ["user_google_email"]}}
check("workspace-mcp gets the email from its connection", gcal_read.build_args(ws, "a", "b", {"env": {"USER_GOOGLE_EMAIL": "x@y.z"}})["user_google_email"] == "x@y.z")
check("a required argument Javis cannot fill: the tool is not called", gcal_read.build_args(ws, "a", "b", {}) is None)

j = json.dumps({"items": [
    {"id": "e1", "summary": "Họp nhà cung cấp", "start": {"dateTime": "2026-10-31T09:00:00+07:00"}, "end": {"dateTime": "2026-10-31T10:00:00+07:00"},
     "location": "Kho", "htmlLink": "https://calendar.google.com/event?eid=1"},
    {"id": "e2", "summary": "Nghỉ lễ", "start": {"date": "2026-11-02"}, "end": {"date": "2026-11-03"}},
    {"id": "e3", "summary": "Đã huỷ", "status": "cancelled", "start": {"dateTime": "2026-10-31T11:00:00+07:00"}}]})
ev = gcal_read.parse_events(j)
check("JSON events are read, cancelled ones skipped", [e["id"] for e in ev] == ["e1", "e2"])
check("an all-day event is marked", ev[1]["all_day"] and ev[1]["start"] == "2026-11-02" and not ev[0]["all_day"])
check("place and link are kept", ev[0]["location"] == "Kho" and ev[0]["link"].startswith("https://calendar.google.com"))
txt = ('Successfully retrieved 1 events:\n- "Gọi khách sỉ" (Starts: 2026-10-31T14:00:00+07:00, Ends: 2026-10-31T14:30:00+07:00) '
       'ID: abc123 | Link: https://calendar.google.com/event?eid=2')
ev = gcal_read.parse_events(txt)
check("workspace-mcp's plain lines are read", len(ev) == 1 and ev[0]["title"] == "Gọi khách sỉ" and ev[0]["id"] == "abc123"
      and ev[0]["end"].startswith("2026-10-31T14:30"), ev)


class FakePool:
    def __init__(self, raw):
        self.raw, self.calls = raw, []

    async def list_tools(self, spec):
        return tools

    async def call_tool(self, spec, name, args):
        self.calls.append((name, args))
        return self.raw


pool = FakePool(j)
res = asyncio.run(gcal_read.events("brain", "s", "e", conns=[{"connector_id": "google-calendar", "label": "Google Calendar"},
                                                              {"connector_id": "gmail"}], pool=pool, spec_of=lambda c: c))
check("events() asks only the calendar connection", len(pool.calls) == 1 and pool.calls[0][0] == "list_events")
check("and returns its events with the source", res["ok"] and res["connected"] and [e["source"] for e in res["events"]] == ["Google Calendar"] * 2)
res = asyncio.run(gcal_read.events("brain", "s", "e", conns=[{"connector_id": "gmail"}], pool=pool, spec_of=lambda c: c))
check("no calendar connected: says so, calls nothing", res == {"ok": True, "connected": False, "events": [], "sources": []} and len(pool.calls) == 1)
res = asyncio.run(gcal_read.events("brain", "s", "e", conns=[{"connector_id": "google-calendar", "label": "G"}],
                                   pool=FakePool("ERROR: token expired"), spec_of=lambda c: c))
check("an MCP error comes back as an error, not an empty calendar", not res["ok"] and "token expired" in res["error"])

calls = []


async def cal(brain, start, end):
    calls.append((start, end))
    return {"ok": True, "connected": True, "events": [{"id": "x"}]}

feat3 = my_tasks.MyTasks(my_tasks.MyTasksDeps(brain_root=lambda b: str(brain), atomic_write_text=atomic_write,
                                              tz=lambda: TZ, calendar=cal))
app3 = FastAPI()
app3.include_router(feat3.router)
c3 = TestClient(app3)
r1 = c3.get("/my-tasks/calendar", params={"brain": "brain", "days": 14}).json()
r2 = c3.get("/my-tasks/calendar", params={"brain": "brain", "days": 14}).json()
check("GET /my-tasks/calendar returns the events", r1["events"] == [{"id": "x"}] and r2 == r1)
check("and caches them for five minutes", len(calls) == 1)
check("the window starts today at 00:00 and spans the days asked",
      calls[0][0].startswith(today + "T00:00:00") and (datetime.fromisoformat(calls[0][1]) - datetime.fromisoformat(calls[0][0])).days == 14)
feat4 = my_tasks.MyTasks(my_tasks.MyTasksDeps(brain_root=lambda b: str(brain), atomic_write_text=atomic_write))
app4 = FastAPI()
app4.include_router(feat4.router)
check("no calendar wiring: not connected", TestClient(app4).get("/my-tasks/calendar").json() == {"ok": True, "connected": False, "events": []})

print(f"\n{len(fails)} failed" if fails else "\nall passed")
raise SystemExit(1 if fails else 0)
