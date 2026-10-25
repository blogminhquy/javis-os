"""M5 scoped agent procedure overlay: owner-approved procedure text added to an assistant's prompt.

The overlay never edits the agent file or its memory. Owner rules, persona, model/provider/reasoning,
skills list, grants, schedule and the Auto switch therefore stay byte-equal (spec 9.3, A01). The text
itself is checked by the host: bounded size, no host markers, no directive that tries to set model,
provider, reasoning, permissions or skills, no instruction to drop owner rules. Meaning-level
contradiction needs a reviewer and the owner's judgement, so applying requires the owner's explicit
confirmation of the exact text.

Surfaces (spec 16.2): `dm` (dashboard, CLI and Telegram chats with the assistant), `team`, `kanban`,
`workflow`. A surface the owner did not choose never sees the overlay. A dashboard DM session sees it
only when the session was created after the overlay (the conversation keeps the procedure it began
with, I10); revert and suspension take effect on every new prompt at once.

Owner-rule drift (any owner line of the agent file, frontmatter included, or `## Luật chủ dặn` in its
memory) suspends the overlay: the owner changed the ground the procedure was written for.
"""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Callable

import improvement_store as IM

SURFACES = ("dm", "team", "kanban", "workflow")
MIN_CHARS, MAX_CHARS = 20, 2000
_MARKERS = re.compile(r"JAVIS_(RULE|LESSON|ASK|NGHE|BO_QUA)\b|<!--|-->", re.IGNORECASE)
_SETTINGS = re.compile(r"^\s*[-*]?\s*(model|model_provider|provider|reasoning|effort|skills|tools|permissions?|"
                       r"quyền|mức quyền|lịch|schedule|enabled|auto)\s*[:=]", re.IGNORECASE | re.MULTILINE)
_OVERRIDES = re.compile(
    r"(ignore|disregard|bỏ qua|không cần (tuân|theo)|đừng (tuân|theo))\s+(the\s+|mọi\s+|các\s+)?"
    r"(owner|previous|above|chủ|luật|quy tắc|hướng dẫn)|"
    r"(đổi|chuyển|change|switch)\s+(sang\s+)?(model|mô hình|provider|reasoning)", re.IGNORECASE)
_PROCEDURE_HEADER = "# Quy trình đã được chủ duyệt (Javis quản lý)"


def validate_procedure(text) -> str:
    if type(text) is not str:
        raise ValueError("invalid_agent_procedure")
    text = text.replace("\r\n", "\n").strip()
    if not MIN_CHARS <= len(text) <= MAX_CHARS:
        raise ValueError("agent_procedure_size")
    if _MARKERS.search(text):
        raise ValueError("agent_procedure_host_marker")
    if _SETTINGS.search(text):
        raise ValueError("agent_procedure_protected_setting")
    if _OVERRIDES.search(text):
        raise ValueError("agent_procedure_overrides_owner")
    return text


def surfaces(value) -> list:
    if type(value) is not list or not value or len(set(value)) != len(value) or any(x not in SURFACES for x in value):
        raise ValueError("invalid_agent_surfaces")
    return sorted(value)


def owner_rules_hash(agent_text: str, memory_text: str) -> str:
    """Everything the owner wrote for this assistant: agent file lines outside Javis-managed sections
    (frontmatter included) and the `## Luật chủ dặn` bullets of its memory."""
    import agent_rules
    managed = ("## Lịch sử (tự học)", agent_rules.LEARNED_ADDITIONS_HEADER)
    _before, rules, _after = agent_rules.split_section(memory_text or "", agent_rules.OWNER_RULES_HEADER)
    return IM._hash({"agent": agent_rules.owner_lines(agent_text or "", managed),
                     "rules": [agent_rules.normalize(line) for line in rules]})


def prompt_block(text: str) -> str:
    return f"\n\n{_PROCEDURE_HEADER}\n{text}\n"


def _public(row) -> dict:
    keys = ("agent_key", "procedure_id", "owner_rules_hash", "state", "reason", "generation", "created_at", "updated_at")
    return {**{key: row[key] for key in keys}, "overlay_id": row["id"], "surfaces": json.loads(row["surfaces_json"])}


class AgentProcedures:
    """Owner commands over procedure candidates and overlays; CAS and event-key idempotent."""

    def __init__(self, assets, *, agent_key: Callable[[str, str, bool], str], read_agent: Callable[[str, str], tuple],
                 clock: Callable[[], float] = time.time):
        """`agent_key(brain, slug, register)` -> the assistant's durable key ("" when none); `register` only when staging.
        `read_agent(brain, slug)` -> (agent file text, memory text), host-read; a missing file raises FileNotFoundError."""
        if type(assets) is not IM.ImprovementStore:
            raise TypeError("concrete_agent_assets_required")
        self.assets, self.store, self.clock = assets, assets.store, clock
        self.agent_key, self.read_agent = agent_key, read_agent

    def _available(self) -> bool:
        return IM._schema_version(self.store) >= 14

    def _identity(self, brain, slug, *, register=False):
        import skill_router as SR
        if type(slug) is not str or not SR.valid_file_slug(slug):
            raise ValueError("invalid_agent")
        agent_text, memory_text = self.read_agent(brain, slug)
        key = str(self.agent_key(brain, slug, register) or "")
        if not key:
            raise PermissionError("agent_unavailable")
        return key, owner_rules_hash(agent_text, memory_text)

    def stage(self, principal, agent_slug: str, text: str, *, source: str = "owner", event_key: str) -> dict:
        brain = IM._brain(principal)
        text = validate_procedure(text)
        if source not in ("owner", "learn", "review"):
            raise ValueError("invalid_agent_procedure_source")
        payload = {"agent_slug": agent_slug, "text": text, "source": source}
        IM.ensure(self.store)
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, "agent_procedure_stage", payload)
            if replay is not None:
                return replay
        try:
            key, rules = self._identity(brain, agent_slug, register=True)
        except FileNotFoundError:
            raise PermissionError("agent_unavailable") from None
        digest = IM._hash(text)
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "agent_procedure_stage", payload)
            if replay is not None:
                return replay
            if self.assets._policy(connection, brain)["mode"] == "off":
                raise PermissionError("improvement_disabled")
            existing = connection.execute("SELECT id FROM improvement_agent_procedures WHERE brain_id=? AND agent_key=? "
                                          "AND text_hash=?", (brain, key, digest)).fetchone()
            identifier = existing["id"] if existing else "iap_" + secrets.token_hex(16)
            if existing is None:
                connection.execute("INSERT INTO improvement_agent_procedures VALUES(?,?,?,?,?,?,?,?,?,?)",
                                   (identifier, brain, key, agent_slug, text, digest, rules, source, principal.by, self.clock()))
            result = {"procedure_id": identifier, "agent_key": key, "agent_slug": agent_slug, "text": text,
                      "owner_rules_hash": rules, "source": source}
            self.assets._event(connection, principal, event_key, "agent_procedure_stage", payload, result)
            return result

    def key(self, principal, agent_slug: str) -> str:
        """The assistant's live key without registering one, or ""."""
        try:
            return self._identity(IM._brain(principal), agent_slug)[0]
        except (FileNotFoundError, PermissionError, ValueError):
            return ""

    def enrolled(self, principal, agent_slug: str) -> bool:
        """An assistant with an active overlay is on the improvement path: its learned additions are staged."""
        brain = IM._brain(principal)
        if not self._available():
            return False
        try:
            key, _rules = self._identity(brain, agent_slug)
        except (FileNotFoundError, PermissionError, ValueError):
            return False
        with closing(self.store._conn()) as connection:
            return bool(connection.execute("SELECT 1 FROM improvement_agent_overlays WHERE brain_id=? AND agent_key=? "
                                           "AND state='active'", (brain, key)).fetchone())

    def stage_learned(self, principal, agent_slug: str, text: str, *, source: str = "learn") -> dict | None:
        """learn.py / agent review: a candidate instead of a live write, only for an enrolled assistant (spec 8.3).
        None when the assistant is not enrolled, so the caller keeps today's behaviour."""
        if not self.enrolled(principal, agent_slug):
            return None
        key = f"{source}-" + IM._hash({"agent": agent_slug, "text": text})[:40]
        return self.stage(principal, agent_slug, text, source=source, event_key=key)

    def procedures(self, principal, agent_slug: str) -> list:
        brain = IM._brain(principal)
        if not self._available():
            return []
        with closing(self.store._conn()) as connection:
            rows = connection.execute("SELECT id,agent_key,agent_slug,text,source,created_at FROM improvement_agent_procedures "
                                      "WHERE brain_id=? AND agent_slug=? ORDER BY created_at DESC LIMIT 50",
                                      (brain, agent_slug)).fetchall()
        return [{**dict(row), "procedure_id": row["id"]} for row in rows]

    def overlays(self, principal, *, agent_key: str | None = None) -> list:
        brain = IM._brain(principal)
        if not self._available():
            return []
        query, args = "SELECT * FROM improvement_agent_overlays WHERE brain_id=?", [brain]
        if agent_key is not None:
            query, args = query + " AND agent_key=?", args + [agent_key]
        with closing(self.store._conn()) as connection:
            return [_public(row) for row in connection.execute(query + " ORDER BY created_at DESC LIMIT 100", args)]

    def apply(self, principal, procedure_id: str, chosen, *, owner_confirmed: bool, event_key: str) -> dict:
        brain = IM._brain(principal)
        if type(procedure_id) is not str or not re.fullmatch(r"iap_[0-9a-f]{32}", procedure_id):
            raise ValueError("invalid_agent_procedure")
        chosen = surfaces(chosen)
        if owner_confirmed is not True:
            # The owner reads the exact text and confirms it keeps their rules (spec 9.3).
            raise PermissionError("agent_procedure_owner_confirmation_required")
        payload = {"procedure_id": procedure_id, "surfaces": chosen}
        IM.ensure(self.store)
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, "agent_overlay_apply", payload)
            if replay is not None:
                return replay
            procedure = connection.execute("SELECT * FROM improvement_agent_procedures WHERE id=? AND brain_id=?",
                                           (procedure_id, brain)).fetchone()
            if procedure is None:
                raise PermissionError("agent_procedure_unavailable")
        try:
            key, rules = self._identity(brain, procedure["agent_slug"])
        except FileNotFoundError:
            raise PermissionError("agent_unavailable") from None
        if key != procedure["agent_key"]:
            raise IM.ConflictError("agent_identity_changed")
        if rules != procedure["owner_rules_hash"]:
            # The owner changed the assistant since the text was written: stage it again on the new ground.
            raise IM.ConflictError("agent_owner_rules_changed")
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "agent_overlay_apply", payload)
            if replay is not None:
                return replay
            if self.assets._policy(connection, brain)["mode"] == "off":
                raise PermissionError("improvement_disabled")
            if connection.execute("SELECT 1 FROM improvement_agent_overlays WHERE brain_id=? AND agent_key=? AND state='active'",
                                  (brain, key)).fetchone():
                raise IM.ConflictError("agent_overlay_busy")
            identifier, now = "iao_" + secrets.token_hex(16), self.clock()
            connection.execute("INSERT INTO improvement_agent_overlays VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                               (identifier, brain, key, procedure_id, IM._json(chosen), rules, "active", "owner_apply",
                                1, principal.by, now, now))
            result = _public(connection.execute("SELECT * FROM improvement_agent_overlays WHERE id=?", (identifier,)).fetchone())
            self.assets._event(connection, principal, event_key, "agent_overlay_apply", payload, result)
            return result

    def revert(self, principal, overlay_id: str, *, expected_generation: int, event_key: str) -> dict:
        brain = IM._brain(principal)
        if type(overlay_id) is not str or not re.fullmatch(r"iao_[0-9a-f]{32}", overlay_id):
            raise ValueError("invalid_agent_overlay")
        if type(expected_generation) is not int or expected_generation < 1 or not self._available():
            raise ValueError("invalid_agent_overlay")
        payload = {"overlay_id": overlay_id, "expected_generation": expected_generation}
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "agent_overlay_revert", payload)
            if replay is not None:
                return replay
            row = connection.execute("SELECT * FROM improvement_agent_overlays WHERE id=? AND brain_id=?",
                                     (overlay_id, brain)).fetchone()
            if row is None:
                raise PermissionError("agent_overlay_unavailable")
            if row["generation"] != expected_generation:
                raise IM.ConflictError("stale_agent_overlay")
            if row["state"] != "active":
                raise IM.ConflictError("agent_overlay_not_active")
            connection.execute("UPDATE improvement_agent_overlays SET state='reverted',reason='owner_revert',"
                               "generation=generation+1,updated_at=? WHERE id=?", (self.clock(), overlay_id))
            result = _public(connection.execute("SELECT * FROM improvement_agent_overlays WHERE id=?", (overlay_id,)).fetchone())
            self.assets._event(connection, principal, event_key, "agent_overlay_revert", payload, result)
            return result

    def reconcile(self, principal) -> list:
        """Suspend overlays whose assistant is gone, re-identified, or whose owner rules changed."""
        brain = IM._brain(principal)
        if not self._available():
            return []
        with closing(self.store._conn()) as connection:
            rows = connection.execute("SELECT o.*,p.agent_slug FROM improvement_agent_overlays o JOIN improvement_agent_procedures p "
                "ON p.id=o.procedure_id AND p.brain_id=o.brain_id WHERE o.brain_id=? AND o.state='active'", (brain,)).fetchall()
        suspended = []
        for row in rows:
            try:
                key, rules = self._identity(brain, row["agent_slug"])
                reason = ("agent_identity_changed" if key != row["agent_key"]
                          else "owner_rules_changed" if rules != row["owner_rules_hash"] else "")
            except (FileNotFoundError, PermissionError):
                reason = "agent_unavailable"
            if not reason:
                continue
            with self.store._Tx(self.store) as connection:
                if connection.execute("UPDATE improvement_agent_overlays SET state='suspended',reason=?,generation=generation+1,"
                        "updated_at=? WHERE id=? AND state='active' AND generation=?",
                        (reason, self.clock(), row["id"], row["generation"])).rowcount:
                    suspended.append({"overlay_id": row["id"], "reason": reason})
        return suspended


# -- read time ---------------------------------------------------------------------------------------

def effective_procedure(root, agent_key: str, surface: str, *, agent_text: str, memory_text: str,
                        session_created_at: float | None = None) -> str:
    """The prompt block this assistant should get on this surface, or "" (canonical behaviour)."""
    return effective_overlay(root, agent_key, surface, agent_text=agent_text, memory_text=memory_text,
                             session_created_at=session_created_at)[1]


def effective_overlay(root, agent_key: str, surface: str, *, agent_text: str, memory_text: str,
                      session_created_at: float | None = None) -> tuple:
    """(overlay id, prompt block) served on this surface, or ("", "")."""
    import improvement_activation as IA
    sources = IA._SOURCES[0]
    if sources is None or not agent_key or surface not in SURFACES:
        return "", ""
    database = sources[0]
    try:
        if not database.is_file():
            return "", ""
        brain = str(Path(root).resolve(strict=True))
        connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        with closing(connection):
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='improvement_agent_overlays'").fetchone():
                return "", ""
            row = connection.execute("SELECT o.id,o.surfaces_json,o.owner_rules_hash,o.created_at,p.text FROM improvement_agent_overlays o "
                "JOIN improvement_agent_procedures p ON p.id=o.procedure_id AND p.brain_id=o.brain_id "
                "WHERE o.brain_id=? AND o.agent_key=? AND o.state='active'", (brain, agent_key)).fetchone()
        if row is None or surface not in json.loads(row["surfaces_json"]):
            return "", ""
        if owner_rules_hash(agent_text, memory_text) != row["owner_rules_hash"]:
            return "", ""  # the owner changed the assistant: canonical until the owner re-applies
        if session_created_at is not None and session_created_at < row["created_at"]:
            return "", ""  # a conversation keeps the procedure it began with
        return row["id"], prompt_block(row["text"])
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"[improvement agent] {type(error).__name__}: {error}", file=sys.stderr)
        return "", ""
