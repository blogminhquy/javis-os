"""Regression #1722: Codex refused every Javis hub tool call whenever Javis put it in a sandbox.

Javis never runs Codex interactively: `codex exec --ask-for-approval never`, app-server `approvalPolicy: "never"`.
Under a sandbox (read-only for suggest jobs and restricted workflow steps, workspace-write for auto jobs and gated
Team steps) Codex asks for approval before an MCP tool call, so every hub call ended in "MCP tool call requires
approval, but approval policy is never" and background jobs on Codex read no data. Fix: the hub entry of the Codex
profile carries `default_tools_approval_mode = "approve"`; the hub itself still enforces X-Javis-Mode.

Checked here without a Codex binary:
  - the profile still parses as TOML, the key sits in the `javis` server table next to its `url`, headers unchanged;
  - the app-server path (codex_steer.profile_overrides) passes the key as a `-c` override;
  - an extra ChatGPT account's folder (plan_accounts.prepare) gets a copy that carries it, replacing an older copy;
  - the chat channel block tells the model not to "fix" a refusal by editing ~/.codex/config.toml.
When a real Codex is installed (PATH or JAVIS_CODEX_BIN), it must still load the profile (`codex -p <name> mcp list`).

    python tests/run.py codex_hub_tool_approval
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

# Hard-set, not setdefault: this test writes a Codex profile under HOME and account folders under the state dir.
_TMP = Path(tempfile.mkdtemp(prefix="javis-codex-approval-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["HOME"] = str(_TMP / "home")
os.environ["USERPROFILE"] = str(_TMP / "home")
os.environ.pop("CODEX_HOME", None)
for _d in ("state", "home"):
    (_TMP / _d).mkdir(parents=True, exist_ok=True)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_context  # noqa: E402
import codex_steer  # noqa: E402
import mcp_hub  # noqa: E402
import plan_accounts  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def load(path):
    try:
        return tomllib.loads(Path(path).read_text(encoding="utf-8")), True
    except (OSError, tomllib.TOMLDecodeError):
        return {}, False


def hub_entry(cfg):
    return (cfg.get("mcp_servers") or {}).get("javis") or {}


# Read with getattr so this file still runs (and turns RED) on a tree without the fix.
KEY = getattr(mcp_hub, "CODEX_TOOLS_APPROVAL_KEY", "default_tools_approval_mode")
OVERRIDE = f'mcp_servers.javis.{KEY}="approve"'

# ---- the shared profile ----
name = mcp_hub.codex_profile("full")
check("profile written under its usual name", name == mcp_hub.codex_profile_name(), name)
cfg, parsed = load(mcp_hub.codex_profile_path())
check("profile still parses as TOML", parsed)
entry = hub_entry(cfg)
check("hub entry approves its own tool calls", entry.get(KEY) == "approve", entry)
check("the key sits in the server table, not among the HTTP headers", KEY not in (entry.get("http_headers") or {}))
check("hub entry keeps its url (without one Codex refuses the whole file: 'invalid transport')",
      entry.get("url") == mcp_hub.hub_url(), entry.get("url"))
headers = entry.get("http_headers") or {}
check("headers unchanged: hub token, mode full, engine codex",
      str(headers.get("Authorization", "")).startswith("Bearer ") and headers.get("X-Javis-Mode") == "full"
      and headers.get("X-Javis-Engine") == "codex", headers)
check("the profile holds the hub entry only", set(cfg.get("mcp_servers") or {}) == {"javis"}, cfg.get("mcp_servers"))

# ---- app-server (chat turns): the profile is flattened into -c overrides ----
overrides = codex_steer.profile_overrides(name, Path.home() / ".codex")
check("app-server gets the approval as a -c override", OVERRIDE in overrides, overrides)

# ---- an extra ChatGPT account (its own CODEX_HOME) ----
PROVIDER = "openai-oauth"
folder = plan_accounts.home(PROVIDER, "acct2")
check("extra account folder exists", folder is not None and Path(folder).is_dir(), folder)
copy = Path(folder) / mcp_hub.codex_profile_path().name
# A copy left from before the fix: older than account 1's profile, without the key.
copy.write_text('[mcp_servers.javis]\nurl = "http://127.0.0.1:7777/hub/mcp"\n', encoding="utf-8")
old = time.time() - 3600
os.utime(copy, (old, old))
plan_accounts.prepare(PROVIDER, folder)
copy_cfg, copy_parsed = load(copy)
check("extra account's profile copy parses as TOML", copy_parsed)
check("extra account's profile copy approves hub calls too", hub_entry(copy_cfg).get(KEY) == "approve",
      hub_entry(copy_cfg))
check("app-server on the extra account passes the approval",
      OVERRIDE in codex_steer.profile_overrides(name, Path(folder)))

# ---- model guidance: a refusal is not fixed by editing the user's Codex config ----
block = channel_context.build_channel_block("dashboard", port=7777)
check("chat block warns against a hand-written mcp_servers.javis in ~/.codex/config.toml",
      "~/.codex/config.toml" in block and "mcp_servers.javis" in block)

# ---- a real Codex, when installed, still loads the profile ----
codex = os.environ.get("JAVIS_CODEX_BIN") or shutil.which("codex")
if codex:
    env = dict(os.environ, CODEX_HOME=str(Path.home() / ".codex"))
    try:
        version = subprocess.run([codex, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
        r = subprocess.run([codex, "-p", name, "mcp", "list", "--json"], capture_output=True, text=True,
                           timeout=60, env=env, cwd=str(_TMP))
        if "profile" in (r.stderr or "") and "not found" in (r.stderr or ""):
            print(f"skip real Codex check: {version} has no profile files")
        else:
            listed = []
            try:
                listed = [s.get("name") for s in json.loads(r.stdout or "[]")]
            except (ValueError, AttributeError):
                pass
            check(f"real Codex ({version}) loads the profile with the key", r.returncode == 0 and "javis" in listed,
                  (r.stderr or "")[-300:])
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"skip real Codex check: {type(e).__name__}: {e}")
else:
    print("skip real Codex check: no codex binary")

if fails:
    print(f"\nFAIL {len(fails)}: " + "; ".join(fails))
    sys.exit(1)
print("OK - test_codex_hub_tool_approval")
