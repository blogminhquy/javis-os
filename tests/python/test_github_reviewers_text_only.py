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
finally:
    main.cfgmod.read_settings, aux_engine.availability, aux_engine._co_binary, main._route_ready = orig

src = (SERVER / "resonance.py").read_text(encoding="utf-8")
check("the rule this follows still stands: text-only accepts Claude's gate or an API engine's no_tools",
      'getattr(first, "no_tools", False) is not True' in src)

print()
if fails:
    print(f"ĐỎ {len(fails)} mục")
    raise SystemExit(1)
print("Tất cả xanh.")
