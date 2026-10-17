"""0.211.0: the Claude Code card on the Models page.

Owner's screenshot 2026-10-17: with the `claude` binary missing, the card showed the same long
"CLI not installed" text three times (status line, yellow box, message after pressing Sign in),
squeezed into a narrow column between stretched buttons, offered a Sign in button that could only
fail, claimed "sign-in is done", and still showed a version line and an Update button.

    python tests/python/test_models_claude_card_0211.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
sys.path.insert(0, str(SERVER))

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. The server says plainly that the CLI is missing ----
import claude_cli as cc  # noqa: E402

_orig = cc.find_claude_cli
cc.find_claude_cli = lambda: None
try:
    d = cc.auth_status(bo_qua_cache=True)
finally:
    cc.find_claude_cli = _orig
check("missing CLI is flagged as cli_missing", d.get("cli_missing") is True and d.get("connected") is False)
check("the full message is still there for callers that print it", "npm install -g @anthropic-ai/claude-code" in d.get("error", ""))

main_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("provider label no longer says OAuth (Javis never reads that token)",
      '"id": "anthropic-cli", "label": "Claude Code"' in main_src)
check("Claude and Codex cards learn whether this is the Docker build",
      main_src.count('item["docker"] = deploy_info.deploy_mode() == "docker"') == 2)
check("and which variable points at the binary", 'item["cli_env"] = "JAVIS_CLAUDE_BIN"' in main_src
      and 'item["cli_env"] = "JAVIS_CODEX_BIN"' in main_src)

# ---- 2. The card ----
js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
start = js.index("async function refreshClaudeCard(")
card = js[start:js.index("async function startClaudeLogin(", start)]
missing = card[card.index("if (d.cli_missing) {"):card.index("// KHÔNG hỏi được")]
check("missing CLI has its own state", "st_no_cli" in missing)
check("and that state offers no Sign in button", "cliLogin" not in missing and "cliRecheck" in missing)
check("a check that disagrees with the drawn card redraws the tab once",
      "el._cliRedrawn" in card and "renderModelsCloudTab(el)" in card)
check("messages are a full-width line, not a span inside the button row",
      '<span id="cliMsg"' not in card and card.count('<div id="cliMsg" class="prov-msg">') == 2)
check("buttons sit in their own row", card.count('<div class="prov-action">') >= 4)
check("the status line no longer prints the raw CLI error", '"○ " + esc(d.error)' not in card)
check("the update row hides when there is no CLI",
      'box.style.display = d.cli_missing ? "none" : ""' in card)
warn = js[js.index("const cliWarn = (ten) => {"):js.index("if (p.kind === \"oauth\") {")]
check("install box: one path, Docker or manual", "p.docker" in warn and "models.cliw_docker" in warn
      and "models.cliw_manual" in warn)
check("install box no longer claims 'sign-in is done' on the Claude card",
      "cli_missing2" not in warn and 'on && p.kind === "oauth"' in warn)
check("the PATH and Windows detail is folded away", "<details" in warn and "models.cliw_help" in warn)
check("the Grok card shows one install hint, not two", 'cliWarn("grok")' not in js)
check("the shield is not green on a card whose CLI is missing",
      '${p.cli_found === false ? "" : "on"}' in js)

# ---- 3. CSS ----
css = (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8")
check("the button row wraps and does not stretch buttons",
      re.search(r"\.prov-action \{[^}]*flex-wrap: wrap;[^}]*align-items: center;", css) is not None)
for sel in (".prov-status", ".prov-note", ".prov-steps", ".prov-msg", ".prov-kind", ".prov-badge",
            ".prov-auth-title", ".prov-auth-note", ".prov-auth-opt", ".prov-auth-warn"):
    m = re.search(re.escape(sel) + r" \{[^}]*font-size: (\d+(?:\.\d+)?)px", css)
    check(f"{sel} text is at least 16px", m is not None and float(m.group(1)) >= 16, m and m.group(1))
check("provider buttons are 16px", ".prov-action .gcard-btn { width: auto; flex: 0 0 auto; margin-top: 0; font-size: 16px; }" in css)
check("commands do not break mid-word", "break-all" not in css[css.index(".prov-steps {"):css.index("/* Nguồn xác thực")])

# ---- 4. Strings ----
import json  # noqa: E402

for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    for k in ("cliw_on", "cliw_off", "cliw_off_key", "cliw_docker", "cliw_manual", "cliw_after", "cliw_after_plain",
              "cliw_help_q", "cliw_help"):
        check(f"{lang}: models.{k}", bool(d.get("models." + k)))
    check(f"{lang}: the old fragments are gone", not any(f"models.cli_missing{n}" in d for n in (2, 3, 4)))
    check(f"{lang}: login note has no arrow chain", "→" not in d["models.cli_login_note"])

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_models_claude_card_0211: all pass")
