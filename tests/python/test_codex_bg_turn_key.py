"""A reminder (or Kanban job) whose background brain is Codex must reach the hub WITH the turn key.

    python tests/run.py codex_bg_turn_key

The bug: `aux_engine._build_codex` never set `hub_turn`, so the Codex process of a scheduled job called the hub without
`X-Javis-Turn`. The hub bound "nobody", and `javis_team` op=dispatch refused with "không rõ ai đang giao việc (lượt
không có danh tính)". A 5am reminder "wake the marketing team" ran, failed that check, and the team never started.

Pinned here, with no model and no network:
  1. hub on + hub profile: the background Codex carries the key of the bound reminder turn, and that key resolves to a
     turn the team dispatch check accepts (kenh=reminder, also kenh=kanban)
  2. hub off: no override (the profile has no hub entry, an override would be a broken half-entry)
  3. no profile: no override
  4. no bound turn: no override, so a job nobody scheduled still cannot dispatch
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from unittest.mock import patch

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-codex-bg-turn-"))

import aux_engine  # noqa: E402
import config as cfgmod  # noqa: E402
import team_dispatch  # noqa: E402
import turn_context  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


class _Base:
    """The Claude engine a reminder builds before the swap: only the fields `_build_codex` reads."""
    cwd = tempfile.mkdtemp(prefix="javis-codex-bg-cwd-")
    tag = "reminder:r_test"
    system_prompt = "x"
    javis_vault = cwd
    javis_mode = "full"


def _settings(hub=True):
    return {"mcp": {"hub": hub}}


def _override(args):
    return [a for a in args if str(a).startswith(turn_context.CODEX_HEADER_KEY + "=")]


def _build(hub=True, profile="javis-test"):
    with patch.object(cfgmod, "read_settings", lambda: _settings(hub)):
        return aux_engine._build_codex({"provider": aux_engine.CODEX, "model": ""}, _Base(), "full", _Base.tag,
                                       (lambda: profile) if profile else None)


for kenh in ("reminder", "kanban"):
    cc = _build()
    check(f"1 {kenh}: hub on + profile -> hub_turn on", cc.hub_turn is True)
    tok = turn_context.bind(turn_context.make(kenh, chat_id="web:s1", job=f"{kenh}:x"))
    try:
        over = _override(cc._build_args())
        check(f"1 {kenh}: one turn override on the argv", len(over) == 1, over)
        key = over[0].split("=", 1)[1].strip('"') if over else ""
        turn = turn_context.resolve_key(key)
        check(f"1 {kenh}: the key resolves to this job's turn", (turn or {}).get("kenh") == kenh, turn)
        try:
            team_dispatch.check_caller(turn)
            ok = True
        except team_dispatch.DispatchError as ex:
            ok = str(ex)
        check(f"1 {kenh}: team dispatch accepts the scheduled job", ok is True, ok)
    finally:
        turn_context.reset(tok)

cc = _build(hub=False)
tok = turn_context.bind(turn_context.make("reminder", job="reminder:x"))
try:
    check("2 hub off -> hub_turn off", cc.hub_turn is False)
    check("2 hub off -> no override", not _override(cc._build_args()))
finally:
    turn_context.reset(tok)

cc = _build(profile=None)
tok = turn_context.bind(turn_context.make("reminder", job="reminder:x"))
try:
    check("3 no profile -> no override", not _override(cc._build_args()))
finally:
    turn_context.reset(tok)

cc = _build()
check("4 no bound turn -> no override", not _override(cc._build_args()))
try:
    team_dispatch.check_caller(None)
    ok = False
except team_dispatch.DispatchError:
    ok = True
check("4 no turn -> dispatch still refused", ok)

print("PASS" if not fails else f"FAIL {len(fails)}")
raise SystemExit(1 if fails else 0)
