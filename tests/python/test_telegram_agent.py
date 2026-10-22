"""The owner's Telegram bot talks to an agent (partner): `@<agent> ...` for one message, /agent to pick one.

    python tests/python/test_telegram_agent.py        (no network, scratch brains)

Customer report 0.270 (Code 24): "@TEST-Thẩm định viên ..." over Telegram got an answer from main
Javis and the partner's run log had no turn; /agents only listed agents. Pinned here, through the
real owner bot functions and the real shell (`_tg_answer`), with only the model engine faked:
  1. Mention parsing: name or slug, case and diacritics insensitive, longest name wins, the bot's
     own @username is skipped, several agents with one name is ambiguous, no match is unknown.
  2. A whitelisted chat that writes `@<agent> ...` gets a turn of THAT agent (its prompt, model,
     own session, run log, lesson lines stripped), and the reply names the agent.
  3. Unknown or ambiguous mention: the list is the answer, before any turn runs.
  4. /agent <name> makes the agent answer the whole chat, `@javis` asks Javis once, /agent off goes
     back to Javis; /reset also resets the agent's session.
  5. A chat that is not on the whitelist (or an empty whitelist) never reaches an agent, and the
     customer-facing bot accounts never get the owner functions.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-tg-agent-")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-tg-agent-brains-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402
import telegram_bot  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{detail!r}]"))
    if not cond:
        _fails.append(name)


def write_agent(brain, slug, name, body, model=""):
    d = Path(brain) / "agents"
    d.mkdir(parents=True, exist_ok=True)
    lines = ["---", "type: agent", f"name: {name}", "role: reviewer", "skills: [appraise]"]
    if model:
        lines.append(f"model: {model}")
    lines.append("---")
    (d / f"{slug}.md").write_text("\n".join(lines) + "\n" + body + "\n", encoding="utf-8")


BRAIN = str(main._default_brain_dir())
write_agent(BRAIN, "test-tham-dinh-vien", "TEST-Thẩm định viên", "APPRAISER ROLE BODY", model="sonnet")
write_agent(BRAIN, "writer", "Writer", "WRITER ROLE BODY")
write_agent(BRAIN, "writer-pro", "Writer Pro", "WRITER PRO ROLE BODY")
write_agent(BRAIN, "twin-a", "Twin", "TWIN A BODY")
write_agent(BRAIN, "twin-b", "Twin", "TWIN B BODY")

OWNER, STRANGER = "111", "222"
_s = main.cfgmod.read_settings()
_s["telegram"] = {"enabled": False, "token": "", "chat_id": OWNER}
main.cfgmod.write_settings(_s)

LESSON = "quote the source of every figure"


class FakeClaude:
    runs = []

    def __init__(self, **kw):
        self.system_prompt = kw.get("system_prompt") or ""
        self.cwd = kw.get("cwd")
        self.model = None
        self.session_id = None

    def reset_session(self):
        self.session_id = None

    async def query(self, prompt):
        FakeClaude.runs.append({"system_prompt": self.system_prompt, "model": self.model,
                                "prompt": prompt, "engine": id(self)})
        yield {"type": "text", "content": "Done."}
        yield {"type": "final", "content": "Done.\nJAVIS_LESSON: " + LESSON,
               "session_id": "fake-1", "tokens_in": 1, "tokens_out": 1, "cost_usd": 0}


class Recorder:
    def prepare(self, *a, **k):
        return SimpleNamespace(action="skip", system_prompt="")


async def _none(*a, **k):
    return None


main._FAST_PATH = Recorder()
main._get_adaptive_context = lambda: Recorder()
main.claude_engine = lambda **kw: FakeClaude(**kw)
main._apply_mcp = lambda *a, **k: None
main._chat_provider = lambda mcfg: ("anthropic-cli", "cli", "", "opus")
main.build_system_prompt = lambda *a, **k: "JAVIS MAIN PROMPT"
main.usage_store.record = lambda *a, **k: None
main.channel_context.collect_turn_files = lambda *a, **k: []
main._schedule_cancel_action = _none
main.learn_feature.enqueue = _none


def answer(text, chat=OWNER):
    return asyncio.run(main._tg_owner_answer(text, {"chat_id": chat, "bot_username": "my_javis_bot"}))


def command(cmd, arg="", chat=OWNER):
    return asyncio.run(main._tg_owner_command(cmd, arg, chat, {"chat_id": chat}))


ROWS = main._tg_agent_rows(BRAIN)

# ================================================================
# 1. Mention parsing
# ================================================================
kind, hits, rest = main._tg_agent_mention("@TEST-Thẩm định viên đánh giá giúp bản này", ROWS)
check("mention: the full display name with spaces and diacritics", kind == "agent"
      and hits[0]["slug"] == "test-tham-dinh-vien" and rest == "đánh giá giúp bản này", (kind, hits, rest))
kind, hits, rest = main._tg_agent_mention("@test tham dinh vien: check this", ROWS)
check("mention: no diacritics, other case, trailing colon", kind == "agent"
      and hits[0]["slug"] == "test-tham-dinh-vien" and rest == "check this", (kind, rest))
kind, hits, rest = main._tg_agent_mention("@test-tham-dinh-vien check", ROWS)
check("mention: the slug", kind == "agent" and hits[0]["slug"] == "test-tham-dinh-vien", (kind, hits))
kind, hits, rest = main._tg_agent_mention("@Writer Pro draft a post", ROWS)
check("mention: the longest name wins (Writer Pro over Writer)", kind == "agent"
      and hits[0]["slug"] == "writer-pro" and rest == "draft a post", (kind, hits, rest))
kind, hits, rest = main._tg_agent_mention("@writer, draft a post", ROWS)
check("mention: the shorter name still works", kind == "agent" and hits[0]["slug"] == "writer"
      and rest == "draft a post", (kind, hits, rest))
kind, hits, rest = main._tg_agent_mention("@my_javis_bot @Writer hi", ROWS, "my_javis_bot")
check("mention: the bot's own @username in front is skipped", kind == "agent"
      and hits[0]["slug"] == "writer" and rest == "hi", (kind, rest))
kind, hits, _ = main._tg_agent_mention("@Twin hello", ROWS)
check("mention: two agents with one name is ambiguous", kind == "ambiguous" and len(hits) == 2, (kind, hits))
kind, _, _ = main._tg_agent_mention("@Nobody hello", ROWS)
check("mention: no such agent is unknown", kind == "unknown", kind)
kind, _, rest = main._tg_agent_mention("@javis what time is it", ROWS)
check("mention: @javis is Javis itself", kind == "javis" and rest == "what time is it", (kind, rest))
kind, _, rest = main._tg_agent_mention("hello @Writer", ROWS)
check("mention: only a LEADING mention counts", kind == "" and rest == "hello @Writer", (kind, rest))
check("pick by name: exact only, no partial guess",
      [r["slug"] for r in main._tg_agent_find(ROWS, "thẩm định")] == []
      and [r["slug"] for r in main._tg_agent_find(ROWS, "TEST-THAM-DINH-VIEN")] == ["test-tham-dinh-vien"])

# ================================================================
# 2. A whitelisted chat mentions an agent: a turn of that agent
# ================================================================
out = answer("@TEST-Thẩm định viên đánh giá giúp bản đề xuất")
run = FakeClaude.runs[-1] if FakeClaude.runs else {}
sp = run.get("system_prompt") or ""
check("agent turn: the agent's role body is the prompt", "APPRAISER ROLE BODY" in sp and "JAVIS MAIN PROMPT" not in sp,
      sp[:200])
check("agent turn: the closing channel line names Telegram", "qua Telegram" in sp, sp[-400:])
check("agent turn: runs on the agent's model", run.get("model") == "sonnet", run.get("model"))
check("agent turn: the mention is stripped from what the agent receives",
      "@TEST" not in str(run.get("prompt")) and "đánh giá giúp bản đề xuất" in str(run.get("prompt")), run.get("prompt"))
check("agent turn: the reply names the agent and has no lesson line",
      isinstance(out, dict) and out["text"].startswith("🤝 TEST-Thẩm định viên") and "JAVIS_LESSON" not in out["text"],
      out)
_runs_dir = main._brain_memory_dir(BRAIN) / "agents" / "test-tham-dinh-vien" / "runs"
_runs = "".join(f.read_text(encoding="utf-8") for f in _runs_dir.glob("*.md")) if _runs_dir.is_dir() else ""
check("agent turn: the run is in the partner's run log", "đánh giá giúp bản đề xuất" in _runs, _runs[:200])
check("agent turn: its own stored conversation, keyed <chat>@<slug>",
      bool(main._TG_SID_MAP.get(OWNER + "@test-tham-dinh-vien"))
      and main._TG_SID_MAP.get(OWNER + "@test-tham-dinh-vien") != main._TG_SID_MAP.get(OWNER))
check("agent turn: /retry resends the message as written",
      main._tg_session(OWNER).get("last") == "@TEST-Thẩm định viên đánh giá giúp bản đề xuất")

out = answer("plain question")
check("no mention, nothing picked: Javis answers", "JAVIS MAIN PROMPT" in FakeClaude.runs[-1]["system_prompt"]
      and not out["text"].startswith("🤝"), out)

# ================================================================
# 3. Unknown or ambiguous mention: the list, before a turn
# ================================================================
n = len(FakeClaude.runs)
pre = main._tg_owner_precheck("@Nobody hi", {"chat_id": OWNER})
check("unknown mention: precheck answers with the list", isinstance(pre, dict)
      and "TEST-Thẩm định viên" in pre.get("reply", "") and "/agent" in pre.get("reply", ""), pre)
pre = main._tg_owner_precheck("@Twin hi", {"chat_id": OWNER})
check("ambiguous mention: the list of the matching ones, by slug", isinstance(pre, dict)
      and "twin-a" in pre["reply"] and "twin-b" in pre["reply"] and "Writer" not in pre["reply"], pre)
pre = main._tg_owner_precheck("@Writer", {"chat_id": OWNER})
check("mention with no question: a hint, no empty turn", isinstance(pre, dict) and "/agent writer" in pre["reply"], pre)
check("plain message: precheck lets it through", main._tg_owner_precheck("hello", {"chat_id": OWNER}) is None)
check("no turn ran for any of these", len(FakeClaude.runs) == n, len(FakeClaude.runs) - n)

# ================================================================
# 4. /agent picks a partner for the chat
# ================================================================
res = command("agent", "test tham dinh vien")
check("/agent <name>: picked", "TEST-Thẩm định viên" in res.get("reply", "")
      and main._TG_AGENT_MAP.get(OWNER, {}).get("slug") == "test-tham-dinh-vien", res)
answer("next message without a mention")
check("/agent: a plain message now goes to the agent", "APPRAISER ROLE BODY" in FakeClaude.runs[-1]["system_prompt"])
answer("@javis quick question")
check("/agent: @javis still asks Javis once", "JAVIS MAIN PROMPT" in FakeClaude.runs[-1]["system_prompt"])
answer("@Writer one for the writer")
check("/agent: a mention of another agent wins for that message",
      "WRITER ROLE BODY" in FakeClaude.runs[-1]["system_prompt"])
check("/status shows the picked partner", "test-tham-dinh-vien" in command("status").get("reply", ""))
check("/agent alone shows who answers", "TEST-Thẩm định viên" in command("agent").get("reply", ""))
res = command("agent", "Twin")
check("/agent with an ambiguous name: list, the pick is unchanged", "twin-a" in res.get("reply", "")
      and main._TG_AGENT_MAP.get(OWNER, {}).get("slug") == "test-tham-dinh-vien", res)
res = command("agent", "nobody")
check("/agent with an unknown name: list, the pick is unchanged", "nobody" in res.get("reply", "")
      and main._TG_AGENT_MAP.get(OWNER, {}).get("slug") == "test-tham-dinh-vien", res)
check("the pick survives a restart (stored on disk)",
      main._tg_load_agent_map().get(OWNER, {}).get("slug") == "test-tham-dinh-vien")
command("reset")
_k = OWNER + "@test-tham-dinh-vien"
check("/reset also starts the agent conversation over", not main._TG_SID_MAP.get(_k)
      and main._tg_session(_k).get("sid") is None)
res = command("agent", "off")
check("/agent off: back to Javis", OWNER not in main._TG_AGENT_MAP and "Javis" in res.get("reply", ""), res)
answer("after off")
check("/agent off: Javis answers", "JAVIS MAIN PROMPT" in FakeClaude.runs[-1]["system_prompt"])

# A pick whose agent is gone is dropped with a notice instead of silently answering as Javis.
command("agent", "writer-pro")
(Path(BRAIN) / "agents" / "writer-pro.md").unlink()
out = answer("still there?")
check("deleted agent: Javis answers and says the pick was dropped",
      "JAVIS MAIN PROMPT" in FakeClaude.runs[-1]["system_prompt"] and "writer-pro" in out["text"]
      and OWNER not in main._TG_AGENT_MAP, out)
check("/help mentions /agent and @<name>", "/agent" in command("help").get("reply", ""))

# ================================================================
# 5. Only the owner's whitelisted chats
# ================================================================
out = answer("@TEST-Thẩm định viên hi", chat=STRANGER)
check("not whitelisted: no agent turn", "JAVIS MAIN PROMPT" in FakeClaude.runs[-1]["system_prompt"])
check("not whitelisted: precheck does not reveal the agent list",
      main._tg_owner_precheck("@Nobody hi", {"chat_id": STRANGER}) is None)
res = command("agent", "writer", chat=STRANGER)
check("not whitelisted: /agent refused, nothing picked", STRANGER not in main._TG_AGENT_MAP
      and "Writer" not in res.get("reply", ""), res)
_s = main.cfgmod.read_settings()
_s["telegram"]["chat_id"] = ""
main.cfgmod.write_settings(_s)
check("empty whitelist (answers anyone): no agent routing", not main._tg_owner_chat(OWNER)
      and main._tg_agent_route(OWNER, "@Writer hi")["agent"] is None)

check("menu has /agent", "agent" in {c["command"] for c in telegram_bot.BOT_COMMANDS})
_src = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
_rt = _src[_src.index("def restart_telegram():"):]
_rt = _rt[:_rt.index("\n\n\n")]
check("the owner bot is wired to the owner functions",
      "_tg_owner_answer" in _rt and "_tg_owner_command" in _rt and "_tg_owner_precheck" in _rt)
_cr = (Path(SERVER) / "chatbot_runtime.py").read_text(encoding="utf-8")
check("customer-facing bot accounts never get the owner functions", "_tg_owner_" not in _cr)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
