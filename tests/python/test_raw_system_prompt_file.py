"""Raw (chat-only) system prompt goes through a file, never one huge argv entry (#871, 0.378.0).

    python tests/run.py raw_system_prompt_file

Linux caps ONE command-line argument at MAX_ARG_STRLEN = 131,072 bytes. The chat-only Claude
Code path (dedicated bots, `tiet_kiem=True`) passed the whole system prompt as `--system-prompt
<text>`, so a bot with a ~120 KB agent file plus per-turn context failed every turn with
"[Errno 7] Argument list too long" and the customer got no reply.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-rawsp-"))

import claude_sdk_engine as eng  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


MAX_ARG_STRLEN = 131072
# Vietnamese text: many characters take 2 or 3 bytes, which is how the real file got there.
big = ("Mục 4: câu mẫu trả lời khách hàng, giữ giọng thân thiện. " * 4000)
check("fixture is over the Linux single-argument cap", len(big.encode("utf-8")) > MAX_ARG_STRLEN,
      len(big.encode("utf-8")))

check("installed SDK supports the file type", main._sdk_has_system_prompt_file())

src = (SERVER / "main.py").read_text(encoding="utf-8")
sub = src[src.find("def _claude_sub_stream("):]
check("the chat-only path wraps its raw engine",
      "_raw_prompt_through_file(cli)" in sub[:sub.find("return _claude_sub_doc(")])

cli = eng.ClaudeSDK(system_prompt=big, cwd=str(ROOT), tag="test-raw")
cli.system_prompt_raw = True
main._raw_prompt_through_file(cli)
opts = cli._options()
sp = opts.system_prompt
check("raw prompt is passed as a file", isinstance(sp, dict) and sp.get("type") == "file", type(sp))
path = sp.get("path", "") if isinstance(sp, dict) else ""
check("file holds the exact prompt",
      bool(path) and open(path, encoding="utf-8").read() == big)
check("raw path stays raw: no claude_code preset, no append file",
      "append-system-prompt-file" not in (getattr(opts, "extra_args", None) or {}))
check("file is tracked for cleanup after the turn", path in cli._tmp_files)

# The real command the SDK would spawn: no single argument may cross the kernel cap.
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport  # noqa: E402

t = SubprocessCLITransport(prompt="xin chào", options=opts)
# CI has no `claude` binary; the path is only resolved at connect(), and only the arguments matter here.
t._cli_path = t._cli_path or "claude"
cmd = t._build_command()
longest = max(len(str(a).encode("utf-8")) for a in cmd)
check("no argv entry crosses MAX_ARG_STRLEN", longest < MAX_ARG_STRLEN, longest)
check("command uses --system-prompt-file", "--system-prompt-file" in cmd)
check("command does not inline the prompt", big not in cmd)

cli._cleanup_tmp()
check("cleanup removes the temp file", not os.path.exists(path))

# Fallback: an SDK without the file type keeps the old inline behaviour instead of breaking.
_orig = main._sdk_has_system_prompt_file
main._sdk_has_system_prompt_file = lambda: False
try:
    old = eng.ClaudeSDK(system_prompt="short prompt", cwd=str(ROOT), tag="test-raw")
    old.system_prompt_raw = True
    main._raw_prompt_through_file(old)
    check("old SDK: inline string fallback", old._options().system_prompt == "short prompt")
finally:
    main._sdk_has_system_prompt_file = _orig

# The wrapper is per instance: the class method stays the audited one (trial discovery pins its AST).
fresh = eng.ClaudeSDK(system_prompt="x", cwd=str(ROOT), tag="test-raw")
check("class _options is untouched, other engines keep it",
      vars(eng.ClaudeSDK)["_options"].__module__ == "claude_sdk_engine"
      and "_options" not in vars(fresh) and "_options" in vars(cli))

print(("\n%d FAIL" % len(_fails)) if _fails else "\nTat ca OK")
raise SystemExit(1 if _fails else 0)
