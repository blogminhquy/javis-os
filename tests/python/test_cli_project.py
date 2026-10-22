"""A conversation's project applies on every channel, not only on the web chat.

    python tests/run.py cli_project        (no network, scratch brains, fake engines)

Customer report 0.270 (codes 9 and 20): a project with three rules was obeyed on the web chat
(3/3) and ignored through the CLI (POST /chat, session already in the project) and Telegram (0/3).
Then a Telegram/CLI conversation idle for 12 hours rotated to a new stored session that was in no
project at all.

What is pinned, through the real /chat endpoint and the real non-WebSocket shell (`_tg_answer`),
with only the model engines faked:
  1. An API engine on the CLI or Telegram sees the project's rules on the turn after the
     conversation was put in the project. Before, the system prompt was built once per RAM session
     (`sess["or"]`), so a project attached later never reached the model until a restart.
  2. The Claude Code engine sees them too (it already did; kept as a guard).
  3. `project` on POST /chat and /chat/stream attaches the conversation before the first turn, by
     id or name of a project of the resolved brain; a project of another brain, a brain that does
     not exist, an unknown project and `project` with `agent` are a 400 and no turn runs.
  4. A rotation after 12 h idle (or 200 messages) keeps the project; a deleted project is not
     revived; a conversation in no project stays in none.
  5. The fast path (whose capsule has no project block) is skipped for a project with rules, and
     still offered to a conversation without one.
  6. `javis --project X "..."` sends the `project` field; without it no field is sent.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-cli-project-")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-cli-project-brains-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{str(detail)[:300]!r}]"))
    if not cond:
        _fails.append(name)


RULE = "START WITH LABEL [EXECUTION BLOCK]"

# ---------------------------------------------------------------- fakes
PROMPTS = []        # the system prompt every engine call saw, in order


class FakeClaude:
    def __init__(self, **kw):
        self.system_prompt = kw.get("system_prompt") or ""
        self.cwd = kw.get("cwd")
        self.model = None
        self.session_id = None

    def reset_session(self):
        self.session_id = None

    async def query(self, prompt):
        PROMPTS.append(self.system_prompt)
        yield {"type": "final", "content": "ok", "session_id": "fake-1",
               "tokens_in": 1, "tokens_out": 1, "cost_usd": 0}


async def fake_api_stream(prov, key, model, msgs, *a, **k):
    PROMPTS.append(msgs[0]["content"] if msgs and msgs[0].get("role") == "system" else "")

    async def gen():
        yield {"type": "text", "content": "ok"}
    return gen()


class Recorder:
    """Stand-in for the fast path and the adaptive context: counts calls, never takes the turn."""

    def __init__(self):
        self.calls = 0

    def prepare(self, *a, **k):
        self.calls += 1
        return SimpleNamespace(action="skip", system_prompt="")


async def _none(*a, **k):
    return None


async def _empty(*a, **k):
    return ""


ENGINE = {"kind": "api"}


def _provider(mcfg):
    if ENGINE["kind"] == "api":
        return ("deepseek", "api", "test-key", "deepseek-chat")
    return ("anthropic-cli", "cli", "", "opus")


FAST, ADAPTIVE = Recorder(), Recorder()
main._FAST_PATH = FAST
main._get_adaptive_context = lambda: ADAPTIVE
main.claude_engine = lambda **kw: FakeClaude(**kw)
main._api_stream_mcp = fake_api_stream
main._tg_compact_bg = lambda *a, **k: None
main._apply_mcp = lambda *a, **k: None
main._chat_provider = _provider
main.usage_store.record = lambda *a, **k: None
main.channel_context.collect_turn_files = lambda *a, **k: []
main._schedule_cancel_action = _none
main.learn_feature.enqueue = _none
main._nhan_nuoi_tien_trinh = _empty
main._canh_bao_hua_suong = _empty

c = TestClient(main.app, base_url="http://127.0.0.1:8080")
st = main.get_store()

DEFAULT = str(main._default_brain_dir())
OTHER = tempfile.mkdtemp(prefix="javis-cli-project-other-")
PID = st.create_project("Execution Block", brain="brain")
st.update_project(PID, instructions=RULE)
OTHER_PID = st.create_project("Other brain project", brain=OTHER)
st.update_project(OTHER_PID, instructions="OTHER BRAIN RULE")


def chat(path="/chat", **data):
    data.setdefault("message", "write the weekly report")
    return c.post(path, data=data)


def sid_of(key):
    return main._TG_SID_MAP.get(key) or (main._TG_SESS.get(key) or {}).get("sid")


def last_prompt():
    return PROMPTS[-1] if PROMPTS else ""


# ============================================================
# 1. API engine, CLI: the project attached after the first turn reaches the next turn
# ============================================================
ENGINE["kind"] = "api"
r = chat(session="late-api")
check("API/CLI: a turn before any project runs", r.status_code == 200 and r.json().get("ok"), r.text)
check("API/CLI: no project yet, no rule in the prompt", RULE not in last_prompt())
sid = sid_of("cli:late-api")
st.set_project(sid, PID)      # what the dashboard's project panel does
chat(session="late-api", message="and now?")
check("API/CLI: the turn after the conversation joined the project sees its rules",
      RULE in last_prompt(), last_prompt()[-300:])
chat(session="late-api", message="once more")
check("API/CLI: and the turn after that still does", RULE in last_prompt())
st.set_project(sid, "")
chat(session="late-api", message="out of the project")
check("API/CLI: taken out of the project, the rules leave the prompt too", RULE not in last_prompt())

# ============================================================
# 2. API engine, Telegram: same shell, same fix
# ============================================================
asyncio.run(main._tg_answer("hello", meta={"chat_id": "9001"}, channel="telegram"))
tg_sid = sid_of("9001")
check("API/Telegram: a stored session exists", bool(tg_sid))
check("API/Telegram: no project yet, no rule", RULE not in last_prompt())
st.set_project(tg_sid, PID)
asyncio.run(main._tg_answer("next", meta={"chat_id": "9001"}, channel="telegram"))
check("API/Telegram: the session's project rules reach the model", RULE in last_prompt(),
      last_prompt()[-300:])

# ============================================================
# 3. Claude Code engine (guard: it already got the prompt every turn)
# ============================================================
ENGINE["kind"] = "cli"
chat(session="late-claude")
st.set_project(sid_of("cli:late-claude"), PID)
chat(session="late-claude", message="and now?")
check("Claude/CLI: the session's project rules reach the model", RULE in last_prompt())

# ============================================================
# 4. `project` on POST /chat attaches the conversation before the first turn
# ============================================================
ENGINE["kind"] = "api"
r = chat(session="first-id", project=PID)
check("project by id: 200", r.status_code == 200 and r.json().get("ok"), r.text)
check("project by id: the FIRST turn already sees the rules", RULE in last_prompt())
check("project by id: the conversation is stored in the project",
      (st.get_session(sid_of("cli:first-id")) or {}).get("project_id") == PID)
chat(session="first-id", message="no field this time")
check("project stays on the conversation for later turns without the field", RULE in last_prompt())

r = chat(session="first-name", project="execution block")
check("project by name (case-insensitive): 200", r.status_code == 200 and r.json().get("ok"), r.text)
check("project by name: stored in the right project",
      (st.get_session(sid_of("cli:first-name")) or {}).get("project_id") == PID)

r = c.post("/chat/stream", data={"message": "stream", "session": "first-stream", "project": PID})
check("/chat/stream takes the field too", r.status_code == 200 and '"response"' in r.text, r.text[:300])
check("/chat/stream: stored in the project",
      (st.get_session(sid_of("cli:first-stream")) or {}).get("project_id") == PID)

n = len(PROMPTS)
r = chat(session="bad-1", project="no-such-project")
check("unknown project: 400", r.status_code == 400 and "no-such-project" in r.text, r.text)
r = chat(session="bad-2", project=OTHER_PID)
check("project of ANOTHER brain: 400 (its rules belong there)", r.status_code == 400, r.text)
r = chat(session="bad-3", project=OTHER_PID, brain=OTHER)
check("the same project with its own brain: 200", r.status_code == 200 and r.json().get("ok"), r.text)
n = len(PROMPTS)
r = chat(session="bad-4", project=PID, brain="/no/such/brain/folder")
check("brain that does not exist: 400 (no fallback to the default brain)", r.status_code == 400, r.text)
Path(DEFAULT, "agents").mkdir(parents=True, exist_ok=True)
Path(DEFAULT, "agents", "helper.md").write_text("---\ntype: agent\nname: helper\n---\nHELPER\n",
                                                encoding="utf-8")
r = chat(session="bad-5", project=PID, agent="helper")
check("project together with agent: 400", r.status_code == 400, r.text)
r = c.post("/chat/stream", data={"message": "x", "session": "bad-6", "project": "nope"})
check("/chat/stream checks before the stream opens: 400", r.status_code == 400, r.text)
check("no rejected request ran a turn", len(PROMPTS) == n, (len(PROMPTS), n))
check("no rejected request created a stored conversation",
      not any(sid_of(f"cli:bad-{i}") for i in (1, 2, 4, 5, 6)))

r = chat(session="plain")
check("no field: the old plain turn", r.status_code == 200 and RULE not in last_prompt())
check("no field: the conversation is in no project",
      not (st.get_session(sid_of("cli:plain")) or {}).get("project_id"))

# ============================================================
# 5. Rotation after 12 h idle keeps the project (code 20)
# ============================================================


def age(sid, seconds):
    st._write(lambda conn: conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?",
                                        (time.time() - seconds, sid)))


old = sid_of("cli:first-id")
age(old, main._TG_CONV_IDLE_S + 60)
chat(session="first-id", message="the next morning")
new = sid_of("cli:first-id")
check("idle 12 h: the conversation rotated to a new stored session", new and new != old, (old, new))
check("idle 12 h: the new session keeps the project",
      (st.get_session(new) or {}).get("project_id") == PID)
check("idle 12 h: and the rules still reach the model", RULE in last_prompt())
check("idle 12 h: the old session keeps its project too",
      (st.get_session(old) or {}).get("project_id") == PID)

old = sid_of("cli:plain")
age(old, main._TG_CONV_IDLE_S + 60)
chat(session="plain", message="the next morning")
new = sid_of("cli:plain")
check("rotation without a project: the new session is in no project",
      new != old and not (st.get_session(new) or {}).get("project_id"))

GONE = st.create_project("Short lived", brain="brain")
chat(session="gone", project=GONE)
old = sid_of("cli:gone")
st.delete_project(GONE)
st._write(lambda conn: conn.execute("UPDATE sessions SET project_id = ? WHERE id = ?", (GONE, old)))
age(old, main._TG_CONV_IDLE_S + 60)
chat(session="gone", message="later")
check("rotation does not revive a deleted project",
      not (st.get_session(sid_of("cli:gone")) or {}).get("project_id"))

# Telegram rotation, through the same shell.
age(tg_sid, main._TG_CONV_IDLE_S + 60)
asyncio.run(main._tg_answer("good morning", meta={"chat_id": "9001"}, channel="telegram"))
tg_new = sid_of("9001")
check("Telegram idle 12 h: rotated and kept the project",
      tg_new != tg_sid and (st.get_session(tg_new) or {}).get("project_id") == PID, (tg_sid, tg_new))

# ============================================================
# 6. Fast path: skipped for a project with rules, offered otherwise
# ============================================================
FAST.calls = 0
chat(session="first-id", message="hi")
check("project with rules: the fast path is not offered", FAST.calls == 0, FAST.calls)
chat(session="plain", message="hi")
check("no project: the fast path is still offered", FAST.calls == 1, FAST.calls)
EMPTY = st.create_project("No rules", brain="brain")
chat(session="norules", project=EMPTY)
check("project without rules: the fast path is still offered", FAST.calls == 2, FAST.calls)

_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("CANARY: the dashboard API Phase 8 base carries the project instructions",
      '_project_block(_row0.get("project_id") or "", chi_huong_dan=True)' in _src)
check("CANARY: both dashboard fast-path offers check the project",
      _src.count('not _project_has_rules(_row0.get("project_id") or "")') == 2)

# ============================================================
# 7. The CLI client: --project sends the field
# ============================================================
sys.path.insert(0, str(ROOT / "cli"))
import javis_cli.__main__ as cli_main  # noqa: E402
import javis_cli.commands as cli_cmd  # noqa: E402

_seen = {}
_orig_hoi, _orig_chat = cli_main.cmd.hoi, cli_main.cmd.chat
cli_main.cmd.hoi = lambda args, cau, session="": _seen.update(cau=cau, project=getattr(args, "project", None)) or 0
cli_main.cmd.chat = lambda args: _seen.update(chat_project=getattr(args, "project", None)) or 0
cli_main.main(["--project", "Execution Block", "write the report"])
check("--project before the question: the value goes to the option, not into the question",
      _seen.get("project") == "Execution Block" and _seen.get("cau") == "write the report", _seen)
cli_main.main(["chat", "--project", "p1"])
check("javis chat --project keeps the project", _seen.get("chat_project") == "p1", _seen)
cli_main.main(["--project", "p2", "chat"])
check("javis --project X chat keeps the project", _seen.get("chat_project") == "p2", _seen)
cli_main.cmd.hoi, cli_main.cmd.chat = _orig_hoi, _orig_chat


class _FakeClient:
    sent = []

    def post(self, path, data):
        _FakeClient.sent.append((path, dict(data)))
        return {"ok": True, "text": "ok"}


cli_cmd._client = lambda args: _FakeClient()
cli_cmd.sys.stderr.isatty = lambda: False
cli_cmd.r.tra_loi = lambda *a, **k: None
cli_cmd.r.duong_chay = lambda *a, **k: None
cli_cmd.hoi(cli_main._parser().parse_args(["-q", "--project", "p3"]), "q")
cli_cmd.hoi(cli_main._parser().parse_args(["-q"]), "q")
check("--project is sent as the `project` form field of /chat",
      _FakeClient.sent and _FakeClient.sent[0][1].get("project") == "p3", _FakeClient.sent)
check("without --project no `project` field is sent",
      len(_FakeClient.sent) == 2 and "project" not in _FakeClient.sent[1][1], _FakeClient.sent)

print()
if _fails:
    print(f"FAIL {len(_fails)}: " + "; ".join(_fails))
    raise SystemExit(1)
print("ALL PASS")
