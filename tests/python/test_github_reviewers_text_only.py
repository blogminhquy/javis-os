"""Who may cross-review a GitHub job (owner, 05/11/2026).

    python tests/run.py github_reviewers_text_only      (no network)

The owner's screenshot: "review chéo bằng openai-oauth không chạy được, bỏ qua lần này" on every job written by Claude.
The reviewer list offered the ChatGPT plan (Codex CLI), but the review turn runs text-only on a stranger's diff and
`resonance.pick_text_only_link` refuses any engine that keeps native file and shell tools (Codex, Grok, Antigravity).
So the review could never run on it. The list now holds only engines that can run text-only and are not resting.
"""
from _paths import ROOT, SERVER  # noqa: F401
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-ghrev-"))

import aux_engine  # noqa: E402
import main  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


settings = {"model": {"order": ["anthropic-cli", "openai-oauth", "grok-cli", "antigravity-cli", "gemini", "deepseek"]}}
orig = (main.cfgmod.read_settings, aux_engine.availability, aux_engine._co_binary, main._route_ready)
resting = set()
main.cfgmod.read_settings = lambda: settings
aux_engine.availability = lambda spec, s=None: (True, "")
aux_engine._co_binary = lambda p: "/usr/bin/x"
main._route_ready = lambda m, p: p not in resting
try:
    got = main._github_reviewers()
    check("plans run through a CLI with native tools are never offered as reviewers",
          not {"openai-oauth", "grok-cli", "antigravity-cli"} & set(got), got)
    check("Claude and API cards are offered, in the Models page order",
          got[:3] == ["anthropic-cli", "gemini", "deepseek"], got)
    resting.add("gemini")
    got = main._github_reviewers()
    check("a card resting out of quota is left out", "gemini" not in got and "deepseek" in got, got)
    resting.clear()
    aux_engine._co_binary = lambda p: ""
    check("Claude Code without its binary is left out", "anthropic-cli" not in main._github_reviewers())

    # Owner, 08/11/2026: "review with the background model, not a model I never set up". The review used to send an
    # empty model, so Groq fell back to llama-3.3-70b-versatile (shut down by Groq) and answered 404.
    settings = {"model": {"order": ["anthropic-cli", "deepseek", "groq"],
                          "auxiliary": {"provider": "groq", "model": "openai/gpt-oss-120b", "reasoning": "high"},
                          "profiles": {"deepseek": {"model": "deepseek-v4-pro", "reasoning": "medium"},
                                       "groq": {"model": "qwen3-32b", "reasoning": "off"}}}}
    got = main._github_reviewers()
    check("the background model's card reviews first", got[:1] == ["groq"], got)
    spec = main._github_reviewer_spec("groq")
    check("the background card reviews on the background model and effort",
          spec == {"provider": "groq", "model": "openai/gpt-oss-120b", "reasoning": "high"}, spec)
    spec = main._github_reviewer_spec("deepseek")
    check("another card reviews on the model and effort picked on that card, never an empty model",
          spec == {"provider": "deepseek", "model": "deepseek-v4-pro", "reasoning": "medium"}, spec)
    check("the chat names the exact model", main._github_reviewer_label("groq") == "groq (openai/gpt-oss-120b)",
          main._github_reviewer_label("groq"))
    check("the chat's own model is named when it reviews its own work",
          main._github_reviewer_label("groq", "qwen3-32b") == "groq (qwen3-32b)", main._github_reviewer_label("groq", "qwen3-32b"))
    settings = {"model": {"order": ["anthropic-cli", "gemini"],
                          "auxiliary": {"provider": "openai-oauth", "model": "gpt-5"}}}
    got = main._github_reviewers()
    check("a background plan that keeps file tools still never reviews", "openai-oauth" not in got, got)
finally:
    main.cfgmod.read_settings, aux_engine.availability, aux_engine._co_binary, main._route_ready = orig

import engine  # noqa: E402
check("Groq's default is no longer the model Groq shut down on 16/08/2026",
      engine.GROQ_DEFAULT_MODEL != "llama-3.3-70b-versatile")

src = (SERVER / "resonance.py").read_text(encoding="utf-8")
check("the rule this follows still stands: text-only accepts Claude's gate or an API engine's no_tools",
      'getattr(first, "no_tools", False) is not True' in src)

print()
if fails:
    print(f"ĐỎ {len(fails)} mục")
    raise SystemExit(1)
print("Tất cả xanh.")
