"""Codex must find its home folder even when Windows will not tell it.

    python tests/run.py codex_home_env      (no network)

Customer report 2026-10-04 (Windows, 0.71.0): every ChatGPT turn died with
"Codex lỗi (exit 1): WARNING: proceeding, even though we could not create PATH aliases: Could not
find home directory". Codex finds home with `dirs::home_dir()`, which on Windows asks the user
profile API and ignores USERPROFILE, so a broken or temporary profile leaves Codex blind while
Javis (which reads USERPROFILE/HOME) still sees the ChatGPT sign-in. Javis now hands Codex an
explicit CODEX_HOME on every spawn.

Checks:
  1. codex_env sets CODEX_HOME to <home>/.codex and creates it (Codex canonicalizes it).
  2. A CODEX_HOME the user set is left alone.
  3. Javis not knowing home either adds nothing.
  4. CodexCLI.query really passes it: a fake Codex that fails exactly like the customer's
     without CODEX_HOME answers normally.
  5. The home-directory failure shows a plain-language message, raw Codex lines kept.
  6. Every Codex spawn site (models list, ChatGPT Live app-server) gets the same env.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="javis-codexhome-env-"))
os.environ.setdefault("JAVIS_STATE_DIR", str(TMP / "state"))
os.environ.pop("CODEX_HOME", None)
HOME = TMP / "home"
HOME.mkdir()
os.environ["USERPROFILE"] = str(HOME)
os.environ["HOME"] = str(HOME)

import claude_cli  # noqa: E402
from claude_cli import CodexCLI  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. CODEX_HOME derived from Javis's home, folder created ----
env = claude_cli.codex_env()
check("codex_env sets CODEX_HOME = <home>/.codex", env.get("CODEX_HOME") == str(HOME / ".codex"), env.get("CODEX_HOME"))
check("the folder exists so Codex can canonicalize it", (HOME / ".codex").is_dir())
check("codex_env does not touch the server's own environment", "CODEX_HOME" not in os.environ)
check("the rest of the environment is carried over", env.get("JAVIS_STATE_DIR") == os.environ["JAVIS_STATE_DIR"])

# ---- 2. user-set CODEX_HOME wins ----
os.environ["CODEX_HOME"] = str(TMP / "custom")
check("a CODEX_HOME the user set is kept", claude_cli.codex_env().get("CODEX_HOME") == str(TMP / "custom"))
os.environ.pop("CODEX_HOME")

# ---- 3. Javis does not know home either: add nothing ----
_orig_home = claude_cli._home_dir
claude_cli._home_dir = lambda: Path("")
check("unknown home adds no CODEX_HOME", "CODEX_HOME" not in claude_cli.codex_env())
claude_cli._home_dir = _orig_home

# ---- 4. CodexCLI.query passes it to the real spawn ----
# Fake Codex: without CODEX_HOME it fails like the customer's machine, with it it answers.
SCRIPT = (
    "import json, os, sys\n"
    "h = os.environ.get('CODEX_HOME')\n"
    "if not h:\n"
    "    sys.stderr.write('WARNING: proceeding, even though we could not create PATH aliases: '\n"
    "                     'Could not find home directory\\n')\n"
    "    sys.stderr.write('Error: Could not find home directory\\n')\n"
    "    sys.exit(1)\n"
    "print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'home=' + h}}), flush=True)\n"
    "print(json.dumps({'type': 'turn.completed', 'usage': {}}), flush=True)\n"
)


def run_turn():
    cli = CodexCLI(cwd=str(TMP))
    cli.cli_path = sys.executable
    cli._build_args = lambda: [sys.executable, "-c", SCRIPT]

    async def collect():
        return [e async for e in cli.query("hi")]
    return asyncio.run(collect())


evs = run_turn()
final = next((e for e in evs if e.get("type") == "final"), {})
errs = [e for e in evs if e.get("type") == "error"]
check("Codex answers when Windows hides home (CODEX_HOME passed)",
      final.get("content") == "home=" + str(HOME / ".codex") and not errs, (final, errs))

# Same fake Codex, but Javis cannot find home either: the error must be readable.
claude_cli._home_dir = lambda: Path("")
evs = run_turn()
claude_cli._home_dir = _orig_home
err = next((e.get("content") for e in evs if e.get("type") == "error"), "")
check("home failure explained in plain words", "Codex không tìm thấy thư mục người dùng" in err
      or "Codex could not find the user folder" in err, err)
check("raw Codex line kept for diagnosis", "Could not find home directory" in err, err)

# ---- 5. other failures keep the old wording ----
check("other exits keep the old message",
      claude_cli.codex_error_text(2, ["error: unexpected argument"]) == "Codex lỗi (exit 2):\nerror: unexpected argument")

# ---- 6. every spawn site gets the env ----
import codex_models  # noqa: E402
import codex_realtime  # noqa: E402

seen = {}


class _Dead:
    stdin = stdout = None

    def poll(self):
        return 1

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 1


def _capture(name):
    def factory(argv, **kw):
        seen[name] = (kw.get("env") or {}).get("CODEX_HOME")
        raise OSError("stop here")
    return factory


codex_models.list_models(timeout=1, cli_path="codex-fake", popen_factory=_capture("models"))
check("model list spawn gets CODEX_HOME", seen.get("models") == str(HOME / ".codex"), seen)

srv = codex_realtime.AppServer("codex-fake", popen_factory=_capture("live"))
try:
    srv._spawn()
except OSError:
    pass
check("ChatGPT Live app-server gets CODEX_HOME", seen.get("live") == str(HOME / ".codex"), seen)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("TẤT CẢ OK")
