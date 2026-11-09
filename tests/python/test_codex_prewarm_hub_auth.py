"""A prewarmed Codex app-server keeps the hub Bearer and swaps only the turn header (#1220).

    python tests/run.py codex_prewarm_hub_auth

The bug: `codex_steer._recipe` looked for the lane argument with the bare prefix `mcp_servers.javis.http_headers.`.
The flattened hub profile puts `...http_headers.Authorization="Bearer <hub token>"` in argv ahead of the turn key, so
the prewarm replaced the hub Bearer with the lane key. Every prewarmed process then got 401 from /hub/mcp and the next
chat turn ran without a single Javis tool.

Pinned here, with no Codex binary and no network:
  1. argv built from a real hub profile + vault override + turn key: the prewarm keeps `Authorization`,
     `X-Javis-Mode` and `X-Javis-Vault` as they were, and only the `X-Javis-Turn` argument carries the lane key
  2. argv without a turn key (hub turn off): no lane, argv unchanged
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-codex-prewarm-"))

import codex_steer  # noqa: E402
import turn_context  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


class _Cli:
    cwd = tempfile.mkdtemp(prefix="javis-codex-prewarm-cwd-")
    tag = "chat-test"
    sandbox = "workspace-write"
    model = ""
    instructions = ""


class _Stop(Exception):
    pass


def _argv_of_prewarm(args):
    """Run the recipe's opener with `_spawn` stubbed out: returns the argv it would start, or None."""
    seen = {}

    def fake_spawn(argv, cwd, acct_home, tag=""):
        seen["argv"] = list(argv)
        raise _Stop()

    real = codex_steer._spawn
    codex_steer._spawn = fake_spawn
    try:
        opener = codex_steer._recipe(_Cli(), args, None, "thread-1")
        try:
            asyncio.run(opener())
        except _Stop:
            pass
    finally:
        codex_steer._spawn = real
    return seen.get("argv")


home = Path(tempfile.mkdtemp(prefix="javis-codex-prewarm-home-"))
(home / "javis.config.toml").write_text(
    '[mcp_servers.javis]\n'
    'url = "http://127.0.0.1:7777/hub/mcp"\n'
    'startup_timeout_sec = 20\n'
    '[mcp_servers.javis.http_headers]\n'
    '"Authorization" = "Bearer HUB-TOKEN"\n'
    '"X-Javis-Mode" = "full"\n', encoding="utf-8")
profile = codex_steer.profile_overrides("javis", home)
auth_arg = next((a for a in profile if ".http_headers.Authorization=" in a), None)
check("the flattened profile carries the hub Bearer", auth_arg is not None, profile)

vault_arg = 'mcp_servers.javis.http_headers.X-Javis-Vault="/brains/Test"'
turn_arg = f'{turn_context.CODEX_HEADER_KEY}="turn-key-of-the-last-turn"'


def _app_server_argv(overrides):
    out = ["codex"]
    for c in overrides:
        out += ["-c", c]
    return out + ["app-server"]


args = _app_server_argv(profile + [vault_arg, turn_arg])

# 1. Only the turn header is swapped.
argv = _argv_of_prewarm(args)
check("1. the prewarm starts a process", argv is not None)
argv = argv or []
check("1. the hub Bearer survives the prewarm", auth_arg in argv, argv)
check("1. the hub mode header survives", any(a.endswith('X-Javis-Mode="full"') for a in argv), argv)
check("1. the vault header survives", vault_arg in argv, argv)
turn_args = [a for a in argv if a.startswith(turn_context.CODEX_HEADER_KEY + "=")]
check("1. exactly one turn header", len(turn_args) == 1, turn_args)
check("1. the turn header carries a fresh lane key", turn_args and turn_args[0] != turn_arg, turn_args)
check("1. argv keeps its length (one swap, nothing dropped)", len(argv) == len(args), (len(argv), len(args)))

# 2. No turn key: nothing to swap.
args_no_turn = _app_server_argv(profile + [vault_arg])
argv2 = _argv_of_prewarm(args_no_turn) or []
check("2. without a turn key the argv is unchanged", argv2 == args_no_turn, argv2)

if fails:
    raise SystemExit(f"{len(fails)} check(s) failed: {fails}")
print("all ok")
