"""A ChatGPT (Codex) turn never ends as an empty bubble with no reason (25/11/2026).

    python tests/run.py codex_empty_turn      (no network: a fake Codex CLI prints JSONL)

Field report: Claude ran out, the owner switched the chat to GPT-6 astra, and the answer was only
"(không có nội dung trả về - thử lại hoặc đổi model)". Four paths ended a Codex turn with no word and no error:

  1. `codex exec` exited 0 before `turn.completed` (nothing to say why).
  2. `codex exec` exited non-zero with nothing on stderr (the error was only sent when stderr had lines).
  3. app-server: Codex reported an `error`, then the turn "completed" with no answer (the error was dropped).
  4. The turn finished cleanly with no text at all: the chat never asked again (the Claude branch does).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="javis-codex-empty-"))
os.environ["JAVIS_STATE_DIR"] = str(TMP / "state")
os.environ["CODEX_HOME"] = str(TMP / "codexhome")
(TMP / "state").mkdir()
(TMP / "codexhome").mkdir()

from claude_cli import CodexCLI  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{str(extra)[:300]}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def run(events, exit_code=0, stderr=""):
    script = "import json, sys\n" + "\n".join(
        f"print(json.dumps({json.dumps(ev, ensure_ascii=False)}), flush=True)" for ev in events)
    if stderr:
        script += f"\nsys.stderr.write({stderr!r})"
    script += f"\nsys.exit({exit_code})"
    cli = CodexCLI(cwd=str(TMP))
    cli.cli_path = sys.executable
    cli._build_args = lambda: [sys.executable, "-c", script]

    async def go():
        return [e async for e in cli.query("chào")]
    return asyncio.run(go())


START = {"type": "thread.started", "thread_id": "t1"}

evs = run([START, {"type": "turn.started"}])
errs = [e for e in evs if e.get("type") == "error"]
check("exit 0 before turn.completed: one error that says Codex stopped before answering",
      len(errs) == 1 and ("Codex" in errs[0]["content"]), evs)

evs = run([START], exit_code=3)
errs = [e for e in evs if e.get("type") == "error"]
check("non-zero exit with nothing on stderr: still an error, with the exit code",
      len(errs) == 1 and "3" in errs[0]["content"], evs)

evs = run([START, {"type": "turn.failed", "error": {"message": "model not supported"}}])
errs = [e for e in evs if e.get("type") == "error"]
check("a failed turn reports its own error once (no second 'stopped' error)",
      len(errs) == 1 and "model not supported" in errs[0]["content"], evs)

evs = run([START, {"type": "item.completed", "item": {"type": "agent_message", "text": "Dạ, em đây."}},
           {"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 2}}])
check("a normal answer is unchanged, no error",
      not [e for e in evs if e.get("type") == "error"]
      and next(e for e in evs if e.get("type") == "final")["content"] == "Dạ, em đây.", evs)

evs = run([START, {"type": "turn.completed", "usage": {}}])
check("a clean turn with no text: an empty final at this layer, no error (the chat asks again)",
      not [e for e in evs if e.get("type") == "error"]
      and next(e for e in evs if e.get("type") == "final")["content"] == "", evs)

steer = (ROOT / "server" / "codex_steer.py").read_text(encoding="utf-8")
check("app-server: an error then a 'completed' turn with no answer reports the error",
      'if status == "completed" and not messages and error_msg:' in steer)
check("app-server: gone before the turn ended reports it, whatever the exit code",
      "elif started:" in steer and "stopped before answering and reported no error" in steer)

main_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("chat: a ChatGPT turn with no text asks once more in the same thread",
      "await _consume_codex(EMPTY_ANSWER_NUDGE)" in main_src)
check("chat: still nothing, the owner gets a reason and what to do, not an empty bubble",
      "ended the turn without writing anything, even when" in main_src)

print()
if fails:
    print(f"{len(fails)} FAIL")
    raise SystemExit(1)
print("all ok")
