"""Small talk takes the lean fast path on every engine (0.345.0).

    python tests/run.py small_talk_fast_path

Measured 27/10/2026 on Claude Code: "chào em" cost about 48k input tokens on the full path, and
27,665 even on the old fast path, because Claude Code still sent every tool schema and the skill
list although no tool may run there. Two things are pinned here:
  1. A message that is ONLY a greeting or a thanks takes the fast path whatever the saving level,
     and nothing else sneaks in with it ("ok làm đi", "chào em, doanh thu hôm nay?").
  2. The Claude Code no-tool path sends no tool at all (`disallowed_tools=["*"]`, measured 183
     input tokens).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-smalltalk-"))
from capability_registry import CapabilityRegistry  # noqa: E402
from capability_resolver import DeterministicResolver  # noqa: E402
from context_compiler import ContextCompiler  # noqa: E402
from context_runtime import ObserveRuntime  # noqa: E402
import fast_path_runtime as fp  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ---- 1. What counts as small talk ----
for text in ("chào em", "Chào em 👋", "cảm ơn em nhé", "Cảm ơn nhiều ạ", "hi Javis", "thanks!",
             "Xin chào", "chào buổi sáng anh", "Thank you so much", "em cảm ơn ạ"):
    check(f"small talk: {text!r}", fp.is_small_talk(text))
for text in ("ok", "ok làm đi", "ok cảm ơn", "chào em, doanh thu hôm nay thế nào?",
             "cảm ơn, gửi tin cho Lan nhé", "cảm ơn em, nhắc anh 7h sáng mai", "em ơi",
             "hi, đọc file báo cáo giúp anh", "chào " * 20, "", "chào em\nxóa lịch họp mai",
             "thanks, now delete the draft"):
    check(f"not small talk: {text[:40]!r}", not fp.is_small_talk(text))


# ---- 2. It takes the fast path with the saving level OFF, on Claude Code ----
def _stack(settings):
    tmp = Path(tempfile.mkdtemp(prefix="javis-smalltalk-stack-"))
    brain = tmp / "brain"
    registry = CapabilityRegistry(tmp / "registry")
    registry.refresh_tools(brain, [], {})
    runtime = ObserveRuntime(tmp / "runtime", settings_reader=lambda: settings)
    trace = runtime.start_turn("session-small-talk", str(brain), "dashboard")
    trace.registry_revision = registry.revision(brain)
    canary = fp.FastPathCanary(registry, DeterministicResolver(registry), ContextCompiler(registry),
                               runtime, settings_reader=lambda: settings)
    return brain, trace, canary


# The "off" saving level on the Usage page is mode "shadow" underneath (config.py), the default.
OFF = {"context_runtime": {"mode": "shadow"}}
brain, trace, canary = _stack(OFF)
plan = canary.prepare(trace, "chào em", str(brain), "dashboard", "anthropic-cli", "claude-opus-5-5",
                      "cli", False, "", "")
check("greeting with saving level off: fast path executes", plan.action == "execute", plan)
check("the capsule carries the greeting and a small system prompt",
      plan.messages and plan.messages[-1].get("content", "").endswith("chào em")
      and sum(len(str(m.get("content") or "")) for m in plan.messages) < 6_000,
      [len(str(m.get("content") or "")) for m in plan.messages])

brain, trace, canary = _stack(OFF)
plan = canary.prepare(trace, "chào em, doanh thu hôm nay thế nào?", str(brain), "dashboard",
                      "anthropic-cli", "claude-opus-5-5", "cli", False, "", "")
check("a real question with saving level off stays on the full path",
      plan.action == "legacy" and plan.reason == "mode_not_canary", plan)

brain, trace, canary = _stack(OFF)
plan = canary.prepare(trace, "cảm ơn em", str(brain), "dashboard", "anthropic-cli",
                      "claude-opus-5-5", "cli", True, "", "")
check("a greeting with an attachment stays on the full path", plan.action == "legacy", plan)

brain, trace, canary = _stack(OFF)
plan = canary.prepare(trace, "thanks!", str(brain), "telegram", "groq", "llama-3.3-70b", "api",
                      False, "", "")
check("other channels and API engines too", plan.action == "execute", plan)


# ---- 3. Claude Code's no-tool path sends no tool schema ----
import main  # noqa: E402

_goc = main._claude_sub_doc
main._claude_sub_doc = lambda cli, prompt, model: cli
try:
    cli = main._claude_sub_stream("", [{"role": "system", "content": "x"}, {"role": "user", "content": "chào em"}],
                                  tiet_kiem=True)
finally:
    main._claude_sub_doc = _goc
check("Claude Code no-tool path disallows every tool", cli.disallowed_tools == ["*"], cli.disallowed_tools)
opts = cli._options()
check("...and the SDK options carry it", "*" in (getattr(opts, "disallowed_tools", None) or []),
      getattr(opts, "disallowed_tools", None))
check("...with the bare system prompt (no claude_code preset)", cli.system_prompt_raw is True)

print()
if fails:
    raise SystemExit(f"FAIL {len(fails)}: " + "; ".join(fails[:4]))
print("All green.")
