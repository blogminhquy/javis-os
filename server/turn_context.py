"""Who is talking in the current turn, for tool hooks (the `turn` key of pre/post_tool_call).

Before this module a hook only saw `tool_name, args, mode, vault_root`. A plugin wrapping an MCP
that answers each person with their OWN permissions (a shop app where every staff member sees
only their own work) had no way to tell which person a chatbot turn was answering: the model
only sees "[Display name] text", and a display name is not an identity anyone can trust.

The `turn` dict (a fresh copy per read, so one hook cannot edit what the next one sees):

    {"kenh": str, "sender_id": str, "chat_type": "private" | "group", "chat_id": str,
     "la_chu": bool}

    kenh       channel of the turn: "zalo_personal", "telegram", "zalo", "dashboard", "cli"...
    sender_id  platform id of the person who sent THIS message, "" when unknown. In a group it
               is still the sender, never the group.
    chat_type  "group" or "private"
    chat_id    the conversation (the group id in a group). Not a person.
    la_chu     True on the owner's own surfaces (dashboard, admin channels). Always False for a
               dedicated bot, whatever its permission level: a bot answers other people.

Resonance A1 adds three keys, filled by the host only for a dashboard chat turn:

    session_id  the stored chat session of the turn, "" elsewhere
    message_id  id of the user's message in that session, 0 when unknown
    agent       {"key", "slug", "config_version"} when the session is a chat with an assistant
                registered in the Resonance registry, else None. Resolved by the host from the
                stored session row and the registry, never from anything the model says.

0.207.0 adds `team_gate`: the id of the tool gate of a Team Work/Help step (team_gate.py), "" elsewhere. Set by the
team runner, never from model output; the hub uses it to let one approved outside action through.

0.238.0 adds `job`: "kanban:<task id>" while a Kanban worker runs, "" elsewhere. Set by the task runner, never from
model output; once_ledger.py keys its once-only record of outside actions on it.

No turn at all (loops, engines that cannot carry the key yet) -> `turn` is
None. A hook that needs an identity must read None as "nobody", never as "the owner".

Two transports, one source of truth:
  - In-process engines (the API engines, plugin tools inside the Claude SDK) call hub routes in
    the turn's own asyncio context, so the hook reads the ContextVar directly.
  - CLI engines (Claude Code, Codex) call the hub over HTTP from a child process, i.e. from a
    different request context. The turn issues an opaque random key (`issue_key`), the engine
    sends it as the `X-Javis-Turn` header, and the hub maps it back (`resolve_key`). The header
    carries no identity of its own: a forged, stale or missing key resolves to None, and a key
    dies with the turn that issued it.
"""
from __future__ import annotations

import contextvars
import re
import secrets
import threading
import time
from typing import Optional

HEADER = "X-Javis-Turn"
# Codex takes per-process header overrides through `-c`. No quotes around the header name, same
# reason as mcp_hub.CODEX_VAULT_KEY (Codex keeps the quotes and the header becomes invalid).
CODEX_HEADER_KEY = "mcp_servers.javis.http_headers." + HEADER

# Safety net only: a key is dropped when its turn ends (`reset`). This bounds the table if a turn
# is killed without reaching its `finally`. Long enough for a slow tool (the CLI tool timeout is
# one hour).
_KEY_TTL_S = 6 * 3600

_GROUP_TYPES = frozenset({"group", "supergroup", "channel"})


class _Binding:
    # `alive` goes False in `reset`. Tasks spawned during a turn copy the context, so they still
    # hold this binding after the turn ends; a dead binding must read as "no turn" there, and
    # must not mint a fresh key for a turn that is over.
    __slots__ = ("turn", "keys", "alive")

    def __init__(self, turn: dict):
        self.turn = turn
        self.keys: list = []
        self.alive = True


class Token:
    """What `bind` returns. Hand it back to `reset` in a `finally`."""
    __slots__ = ("_cv", "_binding")

    def __init__(self, cv_token, binding: Optional[_Binding]):
        self._cv = cv_token
        self._binding = binding


_CURRENT: contextvars.ContextVar[Optional[_Binding]] = contextvars.ContextVar(
    "javis_turn_context", default=None)
_KEYS: dict = {}          # key -> (turn dict, expires_at)
_LOCK = threading.Lock()  # CLI engines build argv from worker threads too


def make(kenh, sender_id="", chat_type="", chat_id="", la_chu=False, *, session_id="", message_id=0,
         agent=None, authority_seq=None, provider="", team_gate="", job="", execution=None) -> dict:
    """`authority_seq` (Resonance A4): ảnh chụp thứ tự quyền do HOST đọc trước khi engine chạy; None khi lượt không
    thuộc trợ lý nào. `provider`: engine của lượt, để hồ sơ bản nộp ghi đúng khả năng engine.
    `team_gate` (0.207.0): id cổng công cụ của một bước việc nhóm (team_gate.py), "" ngoài bước đó."""
    return {
        "kenh": str(kenh or "").strip(),
        "sender_id": str(sender_id or "").strip(),
        "chat_type": "group" if str(chat_type or "").strip().lower() in _GROUP_TYPES else "private",
        "chat_id": str(chat_id or "").strip(),
        "la_chu": bool(la_chu),
        "session_id": str(session_id or "").strip(),
        "message_id": _int(message_id),
        "agent": _agent(agent),
        "authority_seq": None if authority_seq is None else int(authority_seq),
        "provider": str(provider or "").strip(),
        "team_gate": str(team_gate or "").strip(),
        "job": str(job or "").strip(),
        "execution": execution_metadata(execution),
    }


def _int(v) -> int:
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def _agent(a) -> Optional[dict]:
    if not isinstance(a, dict) or not str(a.get("key") or "").strip():
        return None
    return {"key": str(a["key"]).strip(), "slug": str(a.get("slug") or "").strip(),
            "config_version": _int(a.get("config_version"))}


def _copy(turn: dict) -> dict:
    """Copy one level deeper than dict(): `agent` is a nested dict, and a hook must not be able to
    edit what the next reader (the goal tool, another hook) sees."""
    out = dict(turn)
    if isinstance(out.get("agent"), dict):
        out["agent"] = dict(out["agent"])
    if isinstance(out.get("execution"), dict):
        out["execution"] = dict(out["execution"])
    return out


EXECUTION_FIELDS = ("team_id", "task_id", "step_id", "turn_id", "execution_id", "attempt", "role",
                    "purpose", "job_revision", "cli_session_id", "cli_session_new")
IMPROVEMENT_EXECUTION_FIELDS = ("experiment_id", "trial_id", "case_id", "variant", "repeat", "attempt",
                                "execution_id", "role", "purpose", "learning_origin", "cli_session_id", "cli_session_new")


def execution_metadata(value) -> Optional[dict]:
    """Allow only host identifiers, never prompts or credentials, into usage telemetry."""
    if not isinstance(value, dict):
        return None
    if "operation_id" in value:
        required = {"experiment_id", "operation_id", "attempt", "execution_id", "role", "purpose", "learning_origin"}
        if not required <= set(value) or set(value) - required - {"cli_session_id", "cli_session_new"}:
            return None
        for key in ("experiment_id", "operation_id"):
            if not isinstance(value[key], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value[key]):
                return None
        purposes = {"improver": "improve_propose", "semantic_reviewer": "improve_evaluate", "composer": "improve_compose"}
        if (type(value["role"]) is not str or value["role"] not in purposes
                or value["purpose"] != purposes[value["role"]] or value["learning_origin"] != "compose"
                or value["execution_id"] != "improvement_operation:" + value["operation_id"]
                or type(value["attempt"]) is not int or value["attempt"] not in (1, 2)):
            return None
        sid = value.get("cli_session_id")
        if sid is not None and (not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}", sid)):
            return None
        if "cli_session_new" in value and (type(value["cli_session_new"]) is not bool or not sid):
            return None
        return dict(value)
    if value.get("experiment_id") or value.get("trial_id"):
        if value.get("team_id"):
            return None
        for key in ("experiment_id", "trial_id", "case_id", "variant"):
            identifier = value.get(key)
            if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", identifier):
                return None
        if (value.get("execution_id") != "improvement_trial:" + value["trial_id"]
                or value.get("role") != "solver" or value.get("purpose") != "improve_probe"
                or value.get("learning_origin") not in ("trial", "compose", "qualification")
                or any(type(value.get(key)) is not int or not 1 <= value[key] <= 1_000_000 for key in ("repeat", "attempt"))):
            return None
        sid = value.get("cli_session_id")
        if sid is not None and (not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}", sid)):
            return None
        if "cli_session_new" in value and (type(value["cli_session_new"]) is not bool or not sid):
            return None
        return {key: value[key] for key in IMPROVEMENT_EXECUTION_FIELDS if key in value}
    if not value.get("team_id"):
        return None
    return {key: value.get(key) for key in EXECUTION_FIELDS if key in value}


def from_meta(kenh, meta, la_chu: bool) -> dict:
    """Turn from a channel message `meta` (the dict every poller builds: user_id, chat_id,
    chat_type). `user_id` is the sender, so a group message names the person, not the group.

    A `member_join` event is not a message: its "sender" is the newcomer, who wrote nothing, and
    the turn runs on group history anyone in the group could have written. Acting as the
    newcomer would let a member plant a request and then add a manager to run it with the
    manager's rights, so a join turn names nobody (`sender_id` "")."""
    m = meta or {}
    sender = "" if m.get("member_join") else m.get("user_id")
    return make(kenh, sender, m.get("chat_type"), m.get("chat_id"), la_chu)


def bind(turn: Optional[dict]) -> Token:
    """Make `turn` the current turn until `reset`. `None` binds "no turn" on purpose: the hub
    does that for a request without a valid key, so it never inherits an ambient turn."""
    b = _Binding(_copy(turn)) if turn else None
    return Token(_CURRENT.set(b), b)


def reset(token: Token) -> None:
    """Undo `bind` and kill every key this binding issued, so a CLI child process still running
    after the turn (a background command) can no longer act as that person."""
    b = token._binding
    if b is not None:
        b.alive = False
        if b.keys:
            with _LOCK:
                for k in b.keys:
                    _KEYS.pop(k, None)
    _CURRENT.reset(token._cv)


def current() -> Optional[dict]:
    b = _CURRENT.get()
    return _copy(b.turn) if b is not None and b.alive else None


def issue_key() -> Optional[str]:
    """Opaque key for the current turn, for an engine that reaches the hub over HTTP. One key per
    turn (reused if the engine queries twice, e.g. a resume retry). None when there is no turn,
    and then the engine sends no header at all."""
    b = _CURRENT.get()
    if b is None or not b.alive:
        return None
    if b.keys:
        return b.keys[0]
    key = secrets.token_urlsafe(24)
    now = time.time()
    with _LOCK:
        for k in [k for k, (_, exp) in _KEYS.items() if exp < now]:
            _KEYS.pop(k, None)
        _KEYS[key] = (_copy(b.turn), now + _KEY_TTL_S)
    b.keys.append(key)
    return key


def resolve_key(key) -> Optional[dict]:
    """The turn behind a key from the `X-Javis-Turn` header, or None for anything not issued by
    a live turn in THIS process."""
    k = str(key or "").strip()
    if not k:
        return None
    with _LOCK:
        ent = _KEYS.get(k)
    if ent is None or ent[1] < time.time():
        return None
    return _copy(ent[0])


def codex_override() -> Optional[str]:
    """`-c` value carrying the current turn's key to a Codex process, or None without a turn."""
    key = issue_key()
    return f'{CODEX_HEADER_KEY}="{key}"' if key else None
