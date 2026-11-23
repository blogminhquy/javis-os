"""Antigravity (`agy`) resumes the main chat's thread with `--conversation`, and recovers when the thread is gone.

    python tests/run.py agy_resume      (no network, no real agy)

Everything the fake below does was measured on the real agy 1.5.14 on 2026-11-23 (spec section 9):

- M1/M2: `init` carries `conversation_id`; `--conversation <id>` of a known thread keeps that id and remembers.
- M2: `result.usage` adds up the WHOLE conversation on a resumed thread (turn 2 reported 9781 + 2425 input), while
  each step's own `usage` is just that call. So the turn's usage must come from the steps.
- M3/M6: an unknown id (another account, cleaned up) does NOT fail: stderr `warning: conversation "<id>" not found`,
  exit 0, `init` carries a NEW id, and the model answers blind, even running tools. Javis must stop at that `init`,
  before any tool, and rerun the same turn on a fresh thread primed with the saved transcript.
- `agy models` in 1.5.14 rejects `--output-format json` and prints TAB-separated text under a header line.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-agyresume-")
os.environ.pop("JAVIS_AGY_RESUME", None)

import antigravity_cli  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


HELP_NEW = ("Usage: agy [options]\n"
            "  -p, --print, --prompt   Run once and exit. Appended to input on stdin\n"
            "  --output-format <fmt>   text | json | stream-json\n"
            "  --model <slug>          Model to use\n"
            "  --conversation <uuid>   Resume a conversation\n"
            "  --dangerously-skip-permissions  Auto-approve tool calls\n")
HELP_NO_RESUME = HELP_NEW.replace("  --conversation <uuid>   Resume a conversation\n", "")

# Real `agy models` output of 1.5.14 (`cat -A` on 2026-11-23, consumer Google sign-in).
MODELS_1_5_14 = ("Fetching available models...\n"
                 "gemini-3.8-flash-high\tGemini 3.8 Flash (High)\n"
                 "gemini-3.8-flash-medium\tGemini 3.8 Flash (Medium)\n"
                 "gemini-3.8-flash-low\tGemini 3.8 Flash (Low)\n"
                 "claude-sonnet-4-6\tClaude Sonnet 4.6 (Thinking)\n"
                 "claude-opus-4-6-thinking\tClaude Opus 4.6 (Thinking)\n"
                 "gpt-oss-120b-medium\tGPT-OSS 120B (Medium)\n")

FAKE = r'''#!/usr/bin/env python3
import json, os, sys, time, uuid
D = __DIR__
a = sys.argv[1:]
if "--help" in a:
    sys.stdout.write(open(os.path.join(D, "help.txt")).read()); sys.exit(0)
if a and a[0] == "models":
    if "--output-format" in a:
        sys.stderr.write("Error: flags provided but not defined: -output-format\n"); sys.exit(1)
    sys.stdout.write(open(os.path.join(D, "models.txt")).read()); sys.exit(0)
try:
    stdin = sys.stdin.read()
except Exception:
    stdin = ""
asked = a[a.index("--conversation") + 1] if "--conversation" in a else ""
with open(os.path.join(D, "calls.jsonl"), "a") as f:
    f.write(json.dumps({"argv": a, "stdin": stdin}) + "\n")
known_path = os.path.join(D, "known.txt")
known = set(open(known_path).read().split()) if os.path.exists(known_path) else set()
mode = open(os.path.join(D, "mode.txt")).read().strip() if os.path.exists(os.path.join(D, "mode.txt")) else "ok"
lost = bool(asked) and asked not in known
conv = asked if asked and not lost else str(uuid.uuid4())
open(known_path, "a").write(conv + "\n")
if lost:
    sys.stderr.write('warning: conversation "%s" not found\n' % asked); sys.stderr.flush()
def out(ev):
    print(json.dumps(ev, ensure_ascii=False), flush=True)
def step(i, **kw):
    kw.update(conversation_id=conv, step_index=i)
    out({"event": "step_update", "step_update": kw})
out({"event": "init", "conversation_id": conv, "init": {"cwd": os.getcwd(), "permission_mode": "request-review"}})
if asked and mode == "quota":
    sys.stderr.write("Error: RESOURCE_EXHAUSTED: quota exceeded for this model\n"); sys.exit(1)
if asked and mode == "killed":
    import signal; os.kill(os.getpid(), signal.SIGTERM)
if lost:
    time.sleep(1.5)       # Javis must have stopped us by now; reaching the tool means it did not
    open(os.path.join(D, "tool_ran"), "w").write("1")
    step(2, state="ACTIVE", step_type="tool", tool_name="run_command",
         tool_info={"name": "run_command", "parameters": {"CommandLine": "ls"}})
step(0, state="DONE", step_type="user_input")
step(1, state="ACTIVE", step_type="agent_response", text_delta="ANSWER")
step(1, state="DONE", step_type="agent_response", text_delta="\n",
     usage={"input_tokens": 2425, "output_tokens": 105, "thinking_tokens": 104, "cache_read_tokens": 7770,
            "total_tokens": 2530})
out({"event": "result", "result": {"conversation_id": conv, "status": "SUCCESS", "response": "ANSWER\n",
     "num_turns": 2, "usage": {"input_tokens": 12206, "output_tokens": 273, "cache_read_tokens": 7770,
     "total_tokens": 12479}}})
'''


def make_fake(help_text=HELP_NEW, known=(), mode="ok"):
    d = Path(tempfile.mkdtemp(prefix="javis-fakeagy-resume-"))
    p = d / "agy"
    p.write_text(FAKE.replace("__DIR__", repr(str(d))), encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    (d / "help.txt").write_text(help_text, encoding="utf-8")
    (d / "models.txt").write_text(MODELS_1_5_14, encoding="utf-8")
    (d / "known.txt").write_text("".join(k + "\n" for k in known), encoding="utf-8")
    (d / "mode.txt").write_text(mode, encoding="utf-8")
    return str(p), d


def reset_cache():
    antigravity_cli._HELP_CACHE.update(path=None, text="", ts=0.0)
    antigravity_cli._AUTH_CACHE.update(ts=0.0, val=None)


def calls(d):
    f = d / "calls.jsonl"
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def sent(call):
    return "\x00".join(call["argv"]) + call["stdin"]


HISTORY = "HISTORY-MARKER earlier: the secret number is 7"
QUESTION = "QUESTION-MARKER what was the number?"
FRESH = HISTORY + "\n\n" + QUESTION


def turn(cli_path, session_id=None, fresh_prompt=None, prompt=QUESTION):
    reset_cache()
    antigravity_cli.find_antigravity_cli = lambda: cli_path
    g = antigravity_cli.AntigravityCLI(cwd=tempfile.gettempdir())
    g.cli_path = cli_path
    g.session_id = session_id
    g.fresh_prompt = fresh_prompt

    async def go():
        return [ev async for ev in g.query(prompt)]
    return run(go()), g


# ============================================================
# 1. No thread yet: bootstrap prompt, no --conversation, new id picked up
# ============================================================
cli, d = make_fake()
evs, g = turn(cli, prompt=FRESH)
c = calls(d)
check("no thread: one run", len(c) == 1, c)
check("no thread: --conversation not passed", c and "--conversation" not in c[0]["argv"], c)
check("no thread: the bootstrap reaches agy", c and HISTORY in sent(c[0]))
check("no thread: id from `init` kept for the next turn", bool(g.session_id) and not g.thread_lost, g.session_id)
check("no thread: answer arrives", any(e["type"] == "final" and "ANSWER" in e["content"] for e in evs), evs)

# ============================================================
# 2. Known thread: --conversation <id>, only the new question is sent
# ============================================================
cli, d = make_fake(known=["thread-a"])
evs, g = turn(cli, session_id="thread-a", fresh_prompt=FRESH)
c = calls(d)
check("resume: one run", len(c) == 1, c)
check("resume: --conversation <id> passed",
      c and "--conversation" in c[0]["argv"] and c[0]["argv"][c[0]["argv"].index("--conversation") + 1] == "thread-a",
      c)
check("resume: only the new question goes out, not the transcript",
      c and QUESTION in sent(c[0]) and HISTORY not in sent(c[0]))
check("resume: same thread kept", g.session_id == "thread-a" and not g.thread_lost, g.session_id)
check("resume: answer arrives", any(e["type"] == "final" and "ANSWER" in e["content"] for e in evs), evs)
use = [e for e in evs if e["type"] == "usage"]
check("resume: usage is this turn (steps), not the cumulative result.usage",
      use and use[-1]["input_tokens"] == 2425 and use[-1]["cached"] == 7770, use)
check("resume: context_tokens = last call fresh + cached input", use and use[-1].get("context_tokens") == 10195, use)

# ============================================================
# 3. Lost thread (M3/M6): stop at the new `init`, rerun at once on a fresh thread with the bootstrap
# ============================================================
cli, d = make_fake(known=[])
t0 = time.monotonic()
evs, g = turn(cli, session_id="gone-thread", fresh_prompt=FRESH)
time.sleep(2.0)     # give a run that was NOT stopped the time to reach its tool
c = calls(d)
check("lost: two runs in the same turn", len(c) == 2, c)
check("lost: first run asked for the old thread", c and "gone-thread" in c[0]["argv"], c)
check("lost: rerun opens a fresh thread", len(c) == 2 and "--conversation" not in c[1]["argv"], c)
check("lost: rerun carries the bootstrap (history + question)",
      len(c) == 2 and HISTORY in sent(c[1]) and QUESTION in sent(c[1]))
check("lost: the blind run was stopped before any tool", not (d / "tool_ran").exists())
check("lost: no tool call from the blind run reaches the chat", not any(e["type"] == "tool_call" for e in evs), evs)
check("lost: no error shown, the answer arrives",
      not any(e["type"] == "error" for e in evs)
      and any(e["type"] == "final" and "ANSWER" in e["content"] for e in evs), evs)
check("lost: caller told the old thread is gone", g.thread_lost)
check("lost: the NEW fresh thread is the one to save",
      g.session_id and g.session_id != "gone-thread" and (d / "known.txt").read_text().split()[-1] == g.session_id,
      g.session_id)

# ============================================================
# 4. Errors a fresh thread would not fix are NOT rerun (quota) - and a Stop is never rerun
# ============================================================
cli, d = make_fake(known=["thread-q"], mode="quota")
evs, g = turn(cli, session_id="thread-q", fresh_prompt=FRESH)
c = calls(d)
check("quota on resume: no rerun", len(c) == 1, c)
check("quota on resume: the error reaches the chat", any(e["type"] == "error" for e in evs), evs)
check("quota on resume: thread kept for later", not g.thread_lost and g.session_id == "thread-q", g.session_id)

cli, d = make_fake(known=["thread-k"], mode="killed")
evs, g = turn(cli, session_id="thread-k", fresh_prompt=FRESH)
check("killed (Stop) on resume: no rerun", len(calls(d)) == 1, calls(d))
check("killed (Stop): the caller is told the turn was stopped", g.was_stopped)
cli, d = make_fake(known=["thread-a"])
evs, g = turn(cli, session_id="thread-a", fresh_prompt=FRESH)
check("finished turn: not reported as stopped", not g.was_stopped)

# ============================================================
# 5. A CLI without --conversation never resumes: the turn goes out with the bootstrap
# ============================================================
cli, d = make_fake(help_text=HELP_NO_RESUME, known=["thread-a"])
evs, g = turn(cli, session_id="thread-a", fresh_prompt=FRESH)
c = calls(d)
check("old CLI: one run with the bootstrap", len(c) == 1 and HISTORY in sent(c[0]), c)
check("old CLI: --conversation never passed", c and "--conversation" not in c[0]["argv"], c)

# No fresh_prompt (background, Team, workflow) means no resume at all, even with an id around.
cli, d = make_fake(known=["thread-a"])
evs, g = turn(cli, session_id=None, fresh_prompt=None, prompt=FRESH)
check("no fresh_prompt: plain one-shot turn", len(calls(d)) == 1 and "--conversation" not in calls(d)[0]["argv"])

# ============================================================
# 6. JAVIS_AGY_RESUME=0 switches resuming off
# ============================================================
for value, expected in (("0", False), ("false", False), ("off", False), ("", True), ("1", True)):
    os.environ["JAVIS_AGY_RESUME"] = value
    check(f"JAVIS_AGY_RESUME={value!r} -> resume {'on' if expected else 'off'}",
          antigravity_cli.resume_enabled() is expected)
os.environ.pop("JAVIS_AGY_RESUME", None)

# ============================================================
# 7. Golden lines of the real agy 1.5.14 stream (M1, M2, M3)
# ============================================================
M1 = [
    '{"event":"init","conversation_id":"5a310a69-c0e5-411f-8206-3edb06f780aa","init":{"cwd":"/tmp/agyt",'
    '"permission_mode":"request-review"}}',
    '{"event":"step_update","step_update":{"conversation_id":"5a310a69-c0e5-411f-8206-3edb06f780aa","step_index":0,'
    '"state":"DONE","step_type":"user_input"}}',
    '{"event":"step_update","step_update":{"conversation_id":"5a310a69-c0e5-411f-8206-3edb06f780aa","step_index":1,'
    '"state":"ACTIVE","step_type":"agent_response","text_delta":"đã nhớ."}}',
    '{"event":"step_update","step_update":{"conversation_id":"5a310a69-c0e5-411f-8206-3edb06f780aa","step_index":1,'
    '"state":"DONE","step_type":"agent_response","text_delta":"\\n","duration_seconds":3.5,"usage":{"input_tokens":'
    '9781,"output_tokens":168,"thinking_tokens":164,"cache_read_tokens":0,"total_tokens":9949}}}',
    '{"event":"result","result":{"conversation_id":"5a310a69-c0e5-411f-8206-3edb06f780aa","status":"SUCCESS",'
    '"response":"đã nhớ.\\n","num_turns":1,"usage":{"input_tokens":9781,"output_tokens":168,"thinking_tokens":164,'
    '"cache_read_tokens":0,"total_tokens":9949}}}',
]
M2 = [
    '{"event":"init","conversation_id":"5a310a69-c0e5-411f-8206-3edb06f780aa","init":{"cwd":"/tmp/agyt",'
    '"permission_mode":"request-review"}}',
    '{"event":"step_update","step_update":{"conversation_id":"5a310a69-c0e5-411f-8206-3edb06f780aa","step_index":2,'
    '"state":"DONE","step_type":"user_input"}}',
    '{"event":"step_update","step_update":{"conversation_id":"5a310a69-c0e5-411f-8206-3edb06f780aa","step_index":3,'
    '"state":"DONE","step_type":"system_message","duration_seconds":0.0005}}',
    '{"event":"step_update","step_update":{"conversation_id":"5a310a69-c0e5-411f-8206-3edb06f780aa","step_index":4,'
    '"state":"ACTIVE","step_type":"agent_response","text_delta":"7"}}',
    '{"event":"step_update","step_update":{"conversation_id":"5a310a69-c0e5-411f-8206-3edb06f780aa","step_index":4,'
    '"state":"DONE","step_type":"agent_response","text_delta":"\\n","duration_seconds":5.4,"usage":{"input_tokens":'
    '2425,"output_tokens":105,"thinking_tokens":104,"cache_read_tokens":7770,"total_tokens":2530}}}',
    '{"event":"result","result":{"conversation_id":"5a310a69-c0e5-411f-8206-3edb06f780aa","status":"SUCCESS",'
    '"response":"7\\n","num_turns":2,"usage":{"input_tokens":12206,"output_tokens":273,"thinking_tokens":268,'
    '"cache_read_tokens":7770,"total_tokens":12479}}}',
]
M3_HEAD = [
    '{"event":"init","conversation_id":"4b6e6b3a-2435-41f0-8f62-2c88ce8e6623","init":{"cwd":"/tmp/agyt",'
    '"permission_mode":"request-review"}}',
    '{"event":"step_update","step_update":{"conversation_id":"4b6e6b3a-2435-41f0-8f62-2c88ce8e6623","step_index":2,'
    '"state":"ACTIVE","step_type":"tool","tool_name":"run_command","tool_info":{"name":"run_command","parameters":'
    '{"CommandLine":"ls -la /tmp/agyt"}}}}',
]


def feed(lines, cli=None):
    cli = cli or antigravity_cli.AntigravityCLI(cwd=tempfile.gettempdir())
    parts, chan, out = [], {}, []
    for line in lines:
        out += cli._doi_su_kien(json.loads(line), parts, chan)
    return cli, "".join(parts), out


g1, text1, out1 = feed(M1)
check("M1: thread id read from init", g1.session_id == "5a310a69-c0e5-411f-8206-3edb06f780aa", g1.session_id)
check("M1: answer text", text1.strip() == "đã nhớ.", text1)
check("M1: usage", [e for e in out1 if e["type"] == "usage"][-1]["input_tokens"] == 9781, out1)
g2, text2, out2 = feed(M2)
u2 = [e for e in out2 if e["type"] == "usage"][-1]
check("M2: resumed turn usage is the turn's own (2425), not result.usage (12206)", u2["input_tokens"] == 2425, u2)
check("M2: cached input read from cache_read_tokens", u2["cached"] == 7770, u2)
check("M2: answer text", text2.strip() == "7", text2)
g3 = antigravity_cli.AntigravityCLI(cwd=tempfile.gettempdir())
g3.session_id = "00000000-0000-0000-0000-000000000000"
g3, _, out3 = feed(M3_HEAD[:1], g3)
check("M3: an unknown id comes back as ANOTHER id in init (the lost-thread signal)",
      g3.session_id == "4b6e6b3a-2435-41f0-8f62-2c88ce8e6623")

# ============================================================
# 8. `agy models` of 1.5.14 (Việc A): the text list is read in full, the JSON flag that 1.5.14 lacks is survived
# ============================================================
cli, d = make_fake()
reset_cache()
antigravity_cli.find_antigravity_cli = lambda: cli
check("agy models 1.5.14: all six models read",
      antigravity_cli.list_models() == ["gemini-3.8-flash-high", "gemini-3.8-flash-medium", "gemini-3.8-flash-low",
                                        "claude-sonnet-4-6", "claude-opus-4-6-thinking", "gpt-oss-120b-medium"],
      antigravity_cli.list_models())

# ============================================================
# 9. Session store and the main chat wiring
# ============================================================
from sessions import SessionStore  # noqa: E402

store = SessionStore(os.path.join(tempfile.mkdtemp(), "c.db"))
sid = store.get_or_create(None, brain="brain", engine="antigravity-cli", model="m")
store.set_agy_conversation_id(sid, "main|thread-a")
check("store: id saved with its account", (store.get_session(sid) or {}).get("agy_conversation_id") == "main|thread-a")
store.clear_native_threads(sid, keep="antigravity-cli")
check("store: kept while Antigravity runs the turn", (store.get_session(sid) or {}).get("agy_conversation_id"))
store.clear_native_threads(sid, keep="cli")
check("store: cleared when another engine takes a turn", not (store.get_session(sid) or {}).get("agy_conversation_id"))

src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
code = "\n".join(x for x in src.split("\n") if not x.lstrip().startswith("#"))
check("main: only the dashboard chat primes a fallback (background/Team/workflow stay one-shot)",
      code.count(".fresh_prompt = ") == 1, code.count(".fresh_prompt = "))
check("main: the thread is saved with the account that owns it", 'f"{_a_owner}|{acli.session_id}"' in code)
check("main: JAVIS_AGY_RESUME is honoured", code.count("antigravity_cli.resume_enabled()") >= 2)
check("main: a lost thread is cleared", "store.clear_agy_conversation_id, conv_sid" in code)
check("main: a stopped turn does not save its thread", "not acli.was_stopped" in code)

print(f"\n{'ALL GREEN' if not _fails else str(len(_fails)) + ' FAILED'}")
if _fails:
    sys.exit(1)
