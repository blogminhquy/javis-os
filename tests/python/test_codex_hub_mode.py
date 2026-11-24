"""A background Codex job reaches the hub at ITS OWN permission level (0.117.0).

    python tests/run.py codex_hub_mode      (no network, no codex binary needed)

The shared Codex profile is written with `X-Javis-Mode: full` (the chat path). Before 0.117.0 a
reminder, loop or Kanban job at suggest or auto that ran on Codex reached hub tools at full through
that profile, while Grok and Antigravity already got the job's level. Now `aux_engine._build_codex`
adds a per-process `-c` override, the same way the brain header is pinned.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

_TMP = Path(tempfile.mkdtemp(prefix="javis-codex-mode-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
(_TMP / "state").mkdir(parents=True, exist_ok=True)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import aux_engine  # noqa: E402
import config as cfgmod  # noqa: E402
import mcp_hub  # noqa: E402

# The overrides only exist when the profile's `javis` entry is the hub (hub on, profile written): without it they
# would be a half entry Codex refuses to load (see aux_engine._build_codex).
cfgmod.read_settings = lambda: {"mcp": {"hub": True}}
HUB_PROFILE = lambda: "javis-test"  # noqa: E731

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def _mode_overrides(cfg):
    return [x for x in cfg if str(x).startswith(mcp_hub.CODEX_MODE_KEY + "=")]


base = SimpleNamespace(cwd=str(_TMP), tag="dispatch:t1", system_prompt="", javis_vault=str(_TMP),
                       javis_mode="full")
for mode, want in (("suggest", '"suggest"'), ("auto", '"auto"'), ("full", '"full"')):
    cc = aux_engine._build_codex({"provider": "codex", "model": ""}, base, mode, "dispatch:t1", HUB_PROFILE)
    ov = _mode_overrides(cc.extra_config)
    check(f"CANARY: a {mode} job pins X-Javis-Mode={mode}", ov == [f"{mcp_hub.CODEX_MODE_KEY}={want}"], ov)

cc = aux_engine._build_codex({"provider": "codex"}, SimpleNamespace(**{**vars(base), "javis_mode": "auto"}),
                             None, "reminder", HUB_PROFILE)
check("no explicit mode: the engine's own javis_mode is used",
      _mode_overrides(cc.extra_config) == [f'{mcp_hub.CODEX_MODE_KEY}="auto"'], cc.extra_config)

cfg = []
mcp_hub.dat_codex_mode(cfg, "auto")
mcp_hub.dat_codex_mode(cfg, "suggest")
check("a second call replaces the first (one value in argv)", _mode_overrides(cfg) == [f'{mcp_hub.CODEX_MODE_KEY}="suggest"'], cfg)
cfg = []
mcp_hub.dat_codex_mode(cfg, "weird")
check("an unknown level falls back to the strictest", cfg == [f'{mcp_hub.CODEX_MODE_KEY}="suggest"'], cfg)

key, _ = cfg[0].split("=", 1)
check("the header name has no quotes (Codex keeps quotes in split keys)", '"' not in key.split(".")[-1])

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
