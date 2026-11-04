"""A reminder or loop made in a partner chat reports to that chat and runs as that assistant.

Customer report 2026-11-04: an auto-post job set up in a partner (agent) chat sent its failures to Javis Core. Three
causes, three fixes:

1. javis_schedule left `chat_id` empty (an agent chat never told the model its `web:<id>`), so reports went to Javis
   Core. The tool now takes the chat from the turn the host set, and the agent prompt states the id.
2. The job forgot which assistant made it and ran on the plain Javis prompt. It now carries `agent` and runs as that
   assistant (prompt, memory, owner rules), its JAVIS_LESSON lines going to the assistant's memory.
3. The incident desk always posted to Javis Core. A report now names the chat the job came from and the desk's
   messages go there.

No engine, network or server: fakes record what they receive.

    python tests/python/test_partner_jobs_report_home.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-partner-jobs-"))
sys.path.insert(0, str(ROOT / "system" / "plugins" / "javis-schedule"))

import incident_desk as idk  # noqa: E402
import luot_dang_chay  # noqa: E402
import plugin as sched  # noqa: E402
import reminders  # noqa: E402
import self_improve  # noqa: E402
import turn_context  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def _atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


VAULT = tempfile.mkdtemp(prefix="javis-partner-vault-")


def _with_turn(turn, fn):
    tok = turn_context.bind(turn)
    try:
        return fn()
    finally:
        turn_context.reset(tok)


# ── 1. javis_schedule takes the asking chat and the assistant from the host's turn ──
partner_turn = turn_context.make("dashboard", chat_id="s-partner", la_chu=True, session_id="s-partner")
partner_turn["assistant"] = "dang-bai"   # set by run_turn, like a chatbot turn's bot_id
check("the host's assistant key survives bind/current",
      _with_turn(partner_turn, lambda: (turn_context.current() or {}).get("assistant")) == "dang-bai")
check("partner turn -> web:<session> and its assistant",
      _with_turn(partner_turn, lambda: sched._turn_origin(VAULT)) == ("web:s-partner", "dang-bai"))
check("plain dashboard chat -> its own chat, no assistant",
      _with_turn(turn_context.make("dashboard", session_id="s-core", la_chu=True),
                 lambda: sched._turn_origin(VAULT)) == ("web:s-core", ""))
check("a Kanban worker turn is not guessed into some chat",
      _with_turn(turn_context.make("kanban", chat_id="web:s-x", job="kanban:1"),
                 lambda: sched._turn_origin(VAULT)) == ("", ""))
k = luot_dang_chay.bat_dau("web:s-only", VAULT)
try:
    check("no turn at all: the single running chat of the brain", sched._turn_origin(VAULT) == ("web:s-only", ""))
finally:
    luot_dang_chay.ket_thuc(k)

out = _with_turn(partner_turn, lambda: asyncio.run(sched._do_create(VAULT, {
    "op": "create", "name": "Đăng bài mỗi 2 tiếng", "prompt": "Đăng một bài video lên trang.", "schedule": "120m"})))
loop_file = Path(VAULT) / "Javis" / "loops" / "dang-bai-moi-2-tieng.md"
text = loop_file.read_text(encoding="utf-8") if loop_file.is_file() else ""
check("loop from a partner chat reports to that chat", 'owner_chat: "web:s-partner"' in text)
check("loop from a partner chat names its assistant", 'agent: "dang-bai"' in text)
check("reply says where the result goes and who runs it", "web:s-partner" in out and "dang-bai" in out)

out2 = _with_turn(partner_turn, lambda: asyncio.run(sched._do_create(VAULT, {
    "op": "create", "name": "Báo về Telegram", "prompt": "x", "schedule": "60m", "chat_id": "12345"})))
t2 = (Path(VAULT) / "Javis" / "loops" / "bao-ve-telegram.md").read_text(encoding="utf-8")
check("a chat_id the model passed is kept", 'owner_chat: "12345"' in t2 and 'agent: "dang-bai"' in t2)
check("no 'picked the chat' line when the model named it", "khung chat đang hỏi" not in out2)

sent = []


async def _fake_post(payload, brain_name=""):
    sent.append(payload)
    return "Đã đặt lịch lặp 7:00 mỗi ngày (id r_1)."

_real_post = sched._post_reminder
sched._post_reminder = _fake_post
try:
    _with_turn(partner_turn, lambda: asyncio.run(sched._do_create(VAULT, {
        "op": "create", "name": "Đăng poster", "prompt": "Đăng poster.", "schedule": "0 7 * * *"})))
finally:
    sched._post_reminder = _real_post
check("reminder from a partner chat: chat and assistant in the payload",
      sent and sent[0].get("chat_id") == "web:s-partner" and sent[0].get("agent") == "dang-bai")

# ── 2. the reminder store keeps the assistant and runs as it ──
BRAIN = tempfile.mkdtemp(prefix="javis-partner-brain-")
agent_prompts, finished = [], []


def _agent_prompt(brain, slug):
    if slug != "dang-bai":
        raise FileNotFoundError(slug)
    agent_prompts.append(slug)
    return "SYS-AGENT dang-bai"


def _finish(brain, slug, task, out):
    finished.append((slug, task))
    return "\n".join(x for x in out.splitlines() if not x.startswith("JAVIS_LESSON:"))


async def _send(chat_id, text, **kw):
    return True, ""

feature = reminders.RemindersFeature(reminders.RemindersDeps(
    brain_root=lambda _b: BRAIN, atomic_write_text=_atomic_write, send_telegram=_send,
    build_system_prompt=lambda _b: "SYS-JAVIS", aux_model=lambda: None, safe_tools=[], readonly_tools=[],
    scheduler_brains=lambda: [BRAIN], build_agent_prompt=_agent_prompt, finish_agent_run=_finish))
rem = feature._create(BRAIN, "Đăng poster", cron="0 7 * * *", mode="task", allow_no_channel=True,
                      chat_id="web:s-partner", agent="dang-bai")
check("reminder stores its assistant", rem.get("agent") == "dang-bai")
check("view shows the assistant (Tasks page files it there)", feature._view(rem).get("agent") == "dang-bai")
bad = feature._create(BRAIN, "x", cron="0 7 * * *", mode="task", allow_no_channel=True, agent="../etc/passwd")
check("a path is never stored as an assistant", "agent" not in bad)
check("agent_slug keeps a plain slug only",
      reminders.agent_slug("viet-email") == "viet-email" and reminders.agent_slug("a/b") == ""
      and reminders.agent_slug("..") == "")

seen = []


class FakeCli:
    max_wall_s = 0
    model = None

    def __init__(self, system_prompt="", **kw):
        seen.append(system_prompt)

    def is_available(self):
        return True

    async def query(self, prompt):
        yield {"type": "final", "content": "Đã đăng poster.\nJAVIS_LESSON: luôn kèm hashtag"}

_real_engine = reminders.claude_engine
reminders.claude_engine = FakeCli
try:
    body, err = asyncio.run(feature._run_task(BRAIN, "Đăng poster.", "full", agent="dang-bai"))
    check("run as the assistant: its prompt, not Javis's", seen[-1] == "SYS-AGENT dang-bai")
    check("lesson lines stripped from the posted result", body == "Đã đăng poster." and finished)
    body2, _ = asyncio.run(feature._run_task(BRAIN, "Đăng poster.", "full", agent="da-xoa"))
    check("assistant gone -> plain Javis, job still runs", seen[-1] == "SYS-JAVIS" and "JAVIS_LESSON" in body2)
    asyncio.run(feature._run_task(BRAIN, "Nhắc gọi khách.", "full"))
    check("no assistant -> plain Javis as before", seen[-1] == "SYS-JAVIS")
finally:
    reminders.claude_engine = _real_engine

hooked = []
feature.deps.incident_hook = lambda *a, **kw: hooked.append(kw)


async def _fail(*a, **kw):
    return "", "engine exploded"

feature._run_task = _fail
asyncio.run(feature._fire(BRAIN, dict(rem)))
check("a failed reminder tells the incident desk its chat",
      hooked and hooked[-1].get("chat") == "web:s-partner")

# ── 3. loops keep and use the assistant ──
LOOP_BRAIN = tempfile.mkdtemp(prefix="javis-partner-loops-")
loop_prompts = []


class FakeLoopCli:
    max_wall_s = 0

    def is_available(self):
        return True

    async def query(self, prompt):
        yield {"type": "final", "content": "Đã đăng 1 video.\nJAVIS_LESSON: giờ vàng là 20h"}

lfeat = self_improve.LoopFeature(self_improve.LoopDeps(
    build_system_prompt=lambda b: "SYS-JAVIS", brain_root=lambda b: LOOP_BRAIN, aux_model=lambda: None,
    atomic_write_text=_atomic_write, project_root=Path("."), state_dir=Path(os.environ["JAVIS_STATE_DIR"]),
    safe_tools=["Read"], readonly_tools=["Read"], build_agent_prompt=_agent_prompt, finish_agent_run=_finish))


def _make_cli(loop, cwd, sysprompt, **kw):
    loop_prompts.append(sysprompt)
    return FakeLoopCli()

lfeat._make_cli = _make_cli
d = Path(LOOP_BRAIN) / "Javis" / "loops"
d.mkdir(parents=True, exist_ok=True)
(d / "video.md").write_text("---\nname: Video\ngoal: custom\nmode: suggest\nenabled: false\nagent: dang-bai\n"
                            "owner_chat: web:s-partner\n---\nĐăng một video.\n", encoding="utf-8")
(d / "la.md").write_text("---\nname: La\ngoal: custom\nmode: suggest\nenabled: false\nagent: ../x\n---\nx\n",
                         encoding="utf-8")
lp = lfeat.get_loop("brain", "video")
check("loop file's assistant is read", lp and lp.get("agent") == "dang-bai")
check("a path in a loop file is not an assistant", (lfeat.get_loop("brain", "la") or {}).get("agent") == "")
lfeat.toggle("brain", "video")
check("toggling keeps the assistant", "agent: dang-bai" in (d / "video.md").read_text(encoding="utf-8"))
r = asyncio.run(lfeat.run_cycle("brain", "video", "manual"))
check("loop round runs as the assistant", loop_prompts and loop_prompts[-1] == "SYS-AGENT dang-bai")
check("loop round's lesson line is stripped", "JAVIS_LESSON" not in str(r.get("summary") or ""))

# ── 4. the incident desk posts to the chat the job came from ──
posts = []


async def post_with_chat(brain, text, chat=""):
    posts.append((brain, chat, text))


async def post_old(brain, text):
    posts.append((brain, "<old>", text))

_desk_dir, _old_dir = Path(tempfile.mkdtemp(prefix="javis-inc-")), Path(tempfile.mkdtemp(prefix="javis-inc-"))
desk = idk.IncidentDesk(idk.IncidentDeps(state_dir=lambda: _desk_dir,
                                         post=post_with_chat, ask=None))


async def _desk_run(d, **kw):
    d.report("reminder", kw.pop("ref"), brain="b", **kw)
    await d.wait_idle()

asyncio.run(_desk_run(desk, ref="r_1", title="Đăng poster", error="api key invalid", chat="web:s-partner"))
check("incident notice goes to the job's chat", posts and posts[-1][1] == "web:s-partner")
asyncio.run(_desk_run(desk, ref="r_2", title="Nhắc", error="api key invalid"))
check("no chat -> empty chat (the host routes it to Javis Core)", posts[-1][1] == "")
check("the incident keeps its chat on the list",
      any(i.get("ref") == "r_1" and i.get("chat") == "web:s-partner" for i in desk.list("b")))
old = idk.IncidentDesk(idk.IncidentDeps(state_dir=lambda: _old_dir,
                                        post=post_old, ask=None))
asyncio.run(_desk_run(old, ref="r_3", title="x", error="api key invalid", chat="web:s-partner"))
check("a post that takes no chat still gets the notice", posts[-1][1] == "<old>")

# ── 5. host wiring, read from the source (importing main is slow and needs every dependency) ──
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("agent chat prompt states its web:<id>", "Phiên chat này là `web:{conv_sid}`" in main_src)
check("dashboard turn stamps the assistant of the session",
      '_luot_turn["assistant"] = _session_assistant(conv_sid, brain, store.get_session)' in main_src)
check("incident post routes to the job's chat", "await _notify_owner(chat, text, kind=\"report\", source=\"incident\""
      in main_src)
check("reminders and loops get the assistant prompt", main_src.count("build_agent_prompt=_background_agent_prompt") == 2)
tasks_src = (SERVER / "tasks.py").read_text(encoding="utf-8")
check("a blocked Kanban job tells the desk its chat", 'chat=str(task.get("chat_id") or "")' in tasks_src)
js = (ROOT / "dashboard" / "tasks.js").read_text(encoding="utf-8")
check("Tasks page files reminders and loops under their assistant",
      "if (agent && known[agent]) return agent;" in js and "whoOf(\"l:\" + lp.slug, \"\", lp.agent)" in js)

if _fails:
    print(f"\n{len(_fails)} FAILED")
    sys.exit(1)
print("\nall passed")
