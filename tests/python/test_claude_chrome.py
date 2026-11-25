"""Claude in Chrome on an owner chat turn (JAVIS_CLAUDE_CHROME).

The owner asked Javis to drive their signed-in Chrome through the Claude in Chrome extension. Claude Code adds the
extension's tools itself when it gets `--chrome`, and they survive `--strict-mcp-config` (checked by hand with Claude
Code 2.1.331). The tools are native to Claude Code, so the hub's permission levels cannot gate them: the flag goes only
on an owner web chat turn at Full access, never on a safe-background turn, and only on a CLI that knows the flag.

    python tests/run.py claude_chrome
"""
import os
import sys
import tempfile

from _paths import ROOT, SERVER  # noqa: E402,F401

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-chrome-")

import claude_cli  # noqa: E402
from claude_sdk_engine import ClaudeSDK  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


_real_co_co = claude_cli.co_co


def _cli_knows(flag_known):
    def fake(*flags):
        if "--chrome" in flags:
            return flag_known
        return _real_co_co(*flags)
    claude_cli.co_co = fake


def _extra(engine):
    return dict(getattr(engine._options(), "extra_args", None) or {})


_cli_knows(True)
e = ClaudeSDK(tag="chat:abc")
check("a new engine has Chrome off", e.chrome is False)
check("Chrome off: no --chrome on the command line", "chrome" not in _extra(e))
e.chrome = True
check("Chrome on: --chrome is passed as a bare flag", "chrome" in _extra(e) and _extra(e)["chrome"] is None,
      _extra(e))

e2 = ClaudeSDK(tag="chat:abc", system_prompt="hello")
e2.chrome = True
x = _extra(e2)
check("--chrome keeps the system prompt file flag", "chrome" in x and "append-system-prompt-file" in x, x)

bg = ClaudeSDK(tag="loop:x", allowed_tools=["Read"])
bg.chrome = True
check("a safe-background turn never gets --chrome", "chrome" not in _extra(bg))

_cli_knows(False)
old = ClaudeSDK(tag="chat:abc")
old.chrome = True
check("a CLI without --chrome is not handed the flag", "chrome" not in _extra(old))
claude_cli.co_co = _real_co_co

# ---- main._cli_chrome: the switch and the permission level ----
src = (SERVER / "main.py").read_text(encoding="utf-8")
ns = {"os": os}
start = src.index("def _claude_chrome_on()")
end = src.index("def _codex_fast(cli):")
exec(src[start:end], ns)


class _Cli:
    chrome = False


os.environ.pop("JAVIS_CLAUDE_CHROME", None)
c = _Cli()
ns["_cli_chrome"](c, "full")
check("switch unset: Chrome stays off", c.chrome is False)
for v in ("1", "true", "ON", "yes"):
    os.environ["JAVIS_CLAUDE_CHROME"] = v
    c = _Cli()
    ns["_cli_chrome"](c, "full")
    check(f"JAVIS_CLAUDE_CHROME={v} at Full turns Chrome on", c.chrome is True)
os.environ["JAVIS_CLAUDE_CHROME"] = "1"
for mode in ("suggest", "auto"):
    c = _Cli()
    c.chrome = True
    ns["_cli_chrome"](c, mode)
    check(f"a {mode} turn (e.g. /plan) switches Chrome back off", c.chrome is False)
os.environ["JAVIS_CLAUDE_CHROME"] = "0"
c = _Cli()
ns["_cli_chrome"](c, "full")
check("JAVIS_CLAUDE_CHROME=0 keeps Chrome off", c.chrome is False)
os.environ.pop("JAVIS_CLAUDE_CHROME", None)

check("the owner web chat turn sets Chrome after the hub",
      "_apply_mcp(cli, mode=_muc_luot, brain=brain)" in src and "_cli_chrome(cli, _muc_luot)" in src)
check("only one call site (no background, bot or Telegram turn)",
      src.count("_cli_chrome(cli") - src.count("def _cli_chrome(cli") == 1)
for doc in ("docs/16-cau-hinh-env.md", "docs/en/16-env-configuration.md"):
    check(f"{doc} documents JAVIS_CLAUDE_CHROME", "JAVIS_CLAUDE_CHROME" in (ROOT / doc).read_text(encoding="utf-8"))

if fails:
    print("\nFAIL - test_claude_chrome: %d" % len(fails))
    sys.exit(1)
print("\nOK - test_claude_chrome: all pass")
