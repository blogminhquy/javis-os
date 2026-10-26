"""Automatic learning from owner chat: skills, agents and workflows improve themselves from real mistakes.

Owner decision 26/10/2026: Javis learns while the owner talks to it, with nobody approving anything. The flow:

1. Episodes. A chat turn that loaded a skill, an agent chat turn, or a finished workflow run is recorded. The owner's
   next message in that chat is stored with it as the follow-up (a correction, a redo, a complaint).
2. Judge. Later, a text-only call reads the episode and says `ok`, `mistake` or `unsure`. A mistake comes with what
   went wrong, the right behaviour and one self-contained test case.
3. Learning run. After enough mistakes on one target, Javis writes its own cases with grading criteria, runs the
   0.333.0 loop (Harness² sequential recursion, baseline wins ties, sealed paired verdict, regression gate) with a
   grader call, and applies the result only when the verdict is "helped". The old version is kept for undo.

Everything runs text-only (no tools, no MCP), so learning cannot send, buy or post anything. Hard caps keep the
cost bounded: judgments and runs per day, a cool-down per target, a minimum number of mistakes.

Engines and file access come from the host (`Host`), so tests run on fakes and the product runs on the brain's
selected engine.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import improvement_loop as L

JUDGE_PER_DAY = 40
RUNS_PER_DAY = 1
MIN_MISTAKES = 3
COOL_DOWN_S = 3 * 86400
SKIP_UNTESTABLE_S = 14 * 86400
READY_AFTER_S = 2 * 3600       # judged without a follow-up after this long
EXPIRE_AFTER_S = 7 * 86400     # never judged: dropped
MISTAKE_TTL_S = 30 * 86400
JUDGE_BATCH = 3
JUDGE_ATTEMPTS = 3
MIN_CASES, MAX_CASES = 16, 24
MIN_SEALED, MIN_TUNING = 10, 3
TEXT_LIMIT = 6000
KINDS = ("skill", "agent", "workflow")
KEEP_EPISODES_S = 30 * 86400
_PLACEHOLDER = re.compile(r"\{\{\s*\w+\s*\}\}")
_NOT_OWNER_CHANNELS = ("team", "teammate", "bot", "chatbot")


class EngineError(Exception):
    """A model call failed: the work stays queued for a later tick."""


def placeholders(text: str) -> set:
    return set(_PLACEHOLDER.findall(text or ""))


def check_candidate(kind: str, text: str, original: str) -> str:
    """Every text Javis would put live is checked like an owner-applied procedure: no host markers, no wording that
    overrides the owner, no settings lines; a workflow task keeps exactly the placeholders it had."""
    import improvement_agent
    if kind == "agent":
        return improvement_agent.validate_procedure(text)
    reason = improvement_agent.unsafe_reason(text, original)
    if reason:
        raise ValueError(reason)
    if kind == "workflow" and placeholders(text) != placeholders(original):
        raise ValueError("workflow_placeholders_changed")
    return text


SKILL_USE_HOOK = [None]  # set by the host: (brain root, session id, slug) -> None


def note_skill_use_hook(root, session_id: str, slug: str) -> None:
    if SKILL_USE_HOOK[0] is not None:
        SKILL_USE_HOOK[0](root, session_id, slug)


_SKILL_PATH = re.compile(r"(?:^|[\\/])skills[\\/]([^\\/]+)[\\/]SKILL\.md$", re.IGNORECASE)


def skill_from_tool(name: str, args: dict) -> str:
    """The skill slug a native engine tool call loads, or "": Claude Code's `Skill` tool, a read of
    `skills/<slug>/SKILL.md`, or the hub's `javis_use_skill` seen from the CLI side."""
    if not isinstance(args, dict):
        return ""
    if name == "Skill":
        return str(args.get("skill") or args.get("command") or args.get("name") or "").strip().lstrip("/")
    if name.endswith("javis_use_skill"):
        return ""  # the hub records it itself, with the verified slug
    if name in ("Read", "read_file", "javis_read_file"):
        match = _SKILL_PATH.search(str(args.get("file_path") or args.get("path") or ""))
        return match.group(1) if match else ""
    return ""


from improvement_store import ConflictError  # noqa: E402 - target changed since Javis wrote it, or nothing to undo


def _today(clock) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(clock()))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cut(text, limit: int = TEXT_LIMIT) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[:limit] + "\n[...]"


def parse_json(text: str):
    """The first JSON object in a model answer (fenced or bare)."""
    text = str(text or "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no_json")
    return json.loads(text[start:end + 1])


def target_key(kind: str, slug: str, step: int = -1) -> str:
    return f"{kind}:{slug}" + (f"#{step}" if kind == "workflow" else "")


# -- storage -----------------------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS skill_uses(session_id TEXT, brain TEXT, slug TEXT, ts REAL,
    PRIMARY KEY(session_id, brain, slug));
CREATE TABLE IF NOT EXISTS episodes(id TEXT PRIMARY KEY, brain TEXT, kind TEXT, slug TEXT, session_id TEXT,
    answer_mid INTEGER, request TEXT, answer TEXT, follow_up TEXT, extra TEXT, created_at REAL,
    state TEXT, verdict TEXT, judged_at REAL, attempts INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS episodes_state ON episodes(state, created_at);
CREATE INDEX IF NOT EXISTS episodes_session ON episodes(session_id, state);
CREATE TABLE IF NOT EXISTS mistakes(id TEXT PRIMARY KEY, brain TEXT, target TEXT, kind TEXT, slug TEXT, step INTEGER,
    episode_id TEXT, what TEXT, right_way TEXT, case_prompt TEXT, criteria TEXT, created_at REAL, run_id TEXT);
CREATE INDEX IF NOT EXISTS mistakes_target ON mistakes(brain, target, run_id);
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, brain TEXT, target TEXT, kind TEXT, slug TEXT, step INTEGER,
    state TEXT, started_at REAL, finished_at REAL, verdict TEXT, report TEXT, applied INTEGER DEFAULT 0,
    undo TEXT, new_hash TEXT, undone_at REAL, error TEXT, proposal TEXT, base_sha TEXT);
CREATE INDEX IF NOT EXISTS runs_target ON runs(brain, target, started_at);
CREATE TABLE IF NOT EXISTS counters(brain TEXT, day TEXT, judged INTEGER DEFAULT 0, runs INTEGER DEFAULT 0,
    PRIMARY KEY(brain, day));
CREATE TABLE IF NOT EXISTS skips(brain TEXT, target TEXT, until REAL, reason TEXT, PRIMARY KEY(brain, target));
"""


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(_SCHEMA)
            for table, column, kind in (("episodes", "attempts", "INTEGER DEFAULT 0"), ("runs", "proposal", "TEXT"),
                                        ("runs", "base_sha", "TEXT")):
                if column not in {r[1] for r in c.execute(f"PRAGMA table_info({table})")}:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")

    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def write(self, fn):
        with self._lock, closing(self._conn()) as c:
            with c:
                return fn(c)

    def read(self, sql: str, args=()) -> list:
        with closing(self._conn()) as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]


# -- host --------------------------------------------------------------------------------------------

@dataclass
class Host:
    """Everything the learner needs from the server. All callables are synchronous; the learner runs in a worker
    thread with no event loop."""
    text_call: Callable[[str, str], str]                 # (system, prompt) -> text, brain's engine, text only
    engine_ready: Callable[[str], None]                  # brain -> None, raises PermissionError when unusable
    policy_on: Callable[[str], bool]                     # brain -> learning allowed (improvement policy not "off")
    skill_protected: Callable[[str, str], bool]          # (brain, slug) -> system/pack skill: never touched
    workflows_dir: Callable[[str], Path]                 # brain -> folder of workflow files
    agent_text: Callable[[str, str], str]                # (brain, slug) -> agent file text ("" when missing)
    agent_procedure: Callable[[str, str], dict]          # (brain, slug) -> {"text", "overlay_id", "procedure_id", "generation"}
    agent_apply: Callable[[str, str, str, dict], dict]   # (brain, slug, text, overlay the run started from) -> undo info
    agent_undo: Callable[[str, dict], None]              # (brain, undo info) -> None
    reaction: Callable[[str, int], str] = lambda session_id, mid: ""   # owner's reaction on an answer, as text
    workflow_run: Callable[[str], Optional[dict]] = lambda run_id: None
    backups: Path = None                                 # folder for skill/workflow backups
    # The background model the Models page sets for "tự học": judging, writing cases, grading and writing the
    # revision run here; only doing the test work runs on text_call (the brain's own engine). None = text_call.
    background_call: Optional[Callable[[str, str], str]] = None
    # The owner's "Tự học" page: on/off, write mode (dry-run | suggest | auto) and which kinds may learn.
    settings: Callable[[str], dict] = lambda brain: {"enabled": True, "mode": "auto", "kinds": set(KINDS)}


# -- prompts -----------------------------------------------------------------------------------------

def judge_prompt(kind: str, target_text: str, episode: dict, reaction: str) -> str:
    what = {"skill": "a skill (instructions the assistant loaded for this turn)",
            "agent": "an assistant persona with its learned procedure",
            "workflow": "a workflow (a chain of steps, each run by an assistant)"}[kind]
    return (
        "You review one piece of work an AI assistant did for its owner and decide whether the target below caused "
        "a mistake that better instructions would have avoided.\n"
        f"The target is {what}.\n\n"
        "Say \"mistake\" only when the work was wrong or not what the owner wanted (the owner's follow-up or reaction "
        "shows it, or the answer clearly breaks the request or the target's own instructions) AND clearer or "
        "different instructions in the target would have prevented it. A tool outage, missing data or the owner "
        "simply changing the subject is not a mistake of the target. When unsure, say \"unsure\".\n"
        "Important: the assistant following the target faithfully does NOT make the work right. When the owner "
        "corrects the work with a rule or convention the target does not state (or states wrongly), the target is "
        "missing that rule: that IS a mistake of the target.\n"
        "For a mistake, write one test case that reproduces it WITHOUT tools: the prompt is the owner's original "
        "request with every fact the assistant needs (prices, names, numbers), but NEVER the rule, convention or "
        "correction the answer should follow: that is what the target must teach, so it goes only into 2 to 5 short, "
        "checkable criteria a correct answer meets.\n"
        + ("For a workflow, also give the index of the step at fault (0-based).\n" if kind == "workflow" else "")
        + "Return ONLY JSON: {\"verdict\": \"ok|mistake|unsure\", \"what\": \"...\", \"right\": \"...\", "
        "\"case\": {\"prompt\": \"...\", \"criteria\": [\"...\"]}"
        + (", \"step\": 0" if kind == "workflow" else "") + "}\n\n"
        f"## Target\n{_cut(target_text)}\n\n## Owner's request\n{_cut(episode.get('request'), 3000)}\n\n"
        f"## Assistant's work\n{_cut(episode.get('answer'))}\n\n"
        f"## Owner's next message\n{_cut(episode.get('follow_up') or '(none yet)', 2000)}\n\n"
        f"## Owner's reaction\n{reaction or '(none)'}\n")


def writer_prompt(kind: str, target_text: str, mistakes: list, oks: list) -> str:
    listing = "\n\n".join(
        f"### Mistake {i + 1}\nWhat went wrong: {m['what']}\nRight behaviour: {m['right_way']}\n"
        f"Test prompt:\n{m['case_prompt']}\nCriteria: {json.loads(m['criteria'])}" for i, m in enumerate(mistakes))
    good = "\n\n".join(f"### Good turn {i + 1}\nRequest: {_cut(o['request'], 800)}\nAnswer: {_cut(o['answer'], 800)}"
                       for i, o in enumerate(oks)) or "(none)"
    return (
        f"You write a test set to check whether a revised {kind} fixes real mistakes without breaking what works.\n"
        "Every case must be answerable WITHOUT tools or outside data: put all needed facts (prices, names, numbers) "
        "into the prompt. A prompt is a realistic request as the owner or a customer would write it and NEVER states "
        "the rules, conventions or corrections below: those are what the target must know, so they appear only in "
        "the criteria. If this kind of work cannot be tested that way, return {\"testable\": false}.\n"
        f"Write {MIN_CASES} to {MAX_CASES} cases. Each has a unique short family name, a prompt, 2 to 5 short "
        "checkable criteria, and a type:\n"
        "- \"mistake\": one per mistake below, close to its test prompt;\n"
        "- \"variant\": 2 or 3 per mistake, the same trap in different situations (new facts, new wording);\n"
        "- \"keep\": at least 6 ordinary cases of this work the current version should keep getting right.\n"
        "Every criterion of every case, keep cases included, must agree with the owner's corrections below: where a "
        "correction applies to a keep case, its criteria follow the correction too; never write a case that expects "
        "the behaviour the owner corrected.\n"
        "Return ONLY JSON: {\"testable\": true, \"cases\": [{\"family\": \"...\", \"type\": \"mistake|variant|keep\", "
        "\"prompt\": \"...\", \"criteria\": [\"...\"]}]}\n\n"
        f"## Current {kind}\n{_cut(target_text)}\n\n## Mistakes seen in real use\n{listing}\n\n"
        f"## Turns that went well\n{good}\n")


GRADER_SYSTEM = ("You grade an AI assistant's answer against a list of criteria. Be strict and literal: an answer "
                 "passes only if it meets every criterion. Return ONLY JSON: {\"pass\": true|false, "
                 "\"score\": <fraction of criteria met, 0 to 1>, \"feedback\": \"one sentence naming what is missing\"}")


def grader_prompt(case_prompt: str, criteria: list, output: str) -> str:
    items = "\n".join(f"- {c}" for c in criteria)
    return f"## Task\n{_cut(case_prompt, 3000)}\n\n## Criteria\n{items}\n\n## Answer\n{_cut(output, 4000)}\n"


def build_cases(raw) -> list:
    """Writer output -> loop cases. Mistakes and a third of the keep cases tune; variants and the rest are sealed,
    so the verdict is about the same traps in situations the improver never saw."""
    if not isinstance(raw, dict) or raw.get("testable") is False:
        raise ValueError("untestable")
    items, seen = [], set()
    for row in raw.get("cases") or []:
        if not isinstance(row, dict):
            continue
        family, kind, prompt = str(row.get("family") or "").strip()[:80], row.get("type"), str(row.get("prompt") or "").strip()
        criteria = [str(c).strip()[:300] for c in row.get("criteria") or [] if str(c).strip()][:5]
        if not family or family in seen or kind not in ("mistake", "variant", "keep") or not 10 <= len(prompt) <= 6000 or len(criteria) < 1:
            continue
        seen.add(family)
        items.append((family, kind, prompt, criteria))
    items = items[:MAX_CASES]
    keep = [i for i in items if i[1] == "keep"]
    keep_tuning = {i[0] for i in sorted(keep, key=lambda i: _sha(i[0]))[:max(1, len(keep) // 3)]}
    tuning = [i for i in items if i[1] == "mistake" or i[0] in keep_tuning]
    sealed = [i for i in items if i not in tuning]
    if len(items) < MIN_CASES or len(tuning) < MIN_TUNING or len(sealed) < MIN_SEALED:
        raise ValueError("cases_count")
    return ([L.Case(f"t{n + 1:02d}", f, "tuning", p, c) for n, (f, _k, p, c) in enumerate(tuning)]
            + [L.Case(f"q{n + 1:02d}", f, "qualification", p, c) for n, (f, _k, p, c) in enumerate(sealed)])


# -- targets -----------------------------------------------------------------------------------------

def split_frontmatter(text: str) -> tuple:
    text = text.lstrip("﻿").replace("\r\n", "\n")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end > 0:
            return text[:end + 5], text[end + 5:]
    return "", text


def workflow_steps(text: str) -> list:
    """The `steps` list of a workflow file (steps format only), [] otherwise."""
    import fastyaml
    import yaml
    front, _body = split_frontmatter(text or "")
    try:
        meta = fastyaml.safe_load(front[4:-5]) if front else None
    except yaml.YAMLError:
        return []
    steps = meta.get("steps") if isinstance(meta, dict) else None
    return steps if isinstance(steps, list) and all(isinstance(s, dict) for s in steps) else []


@dataclass
class Target:
    kind: str
    slug: str
    step: int
    text: str                     # the part the learner improves
    system: Callable[[str], str]  # version text -> system prompt of the assistant doing the work
    prompt: Callable[[str, str], str] = lambda version, case_prompt: case_prompt
    meta: dict = field(default_factory=dict)


class Targets:
    def __init__(self, host: Host):
        self.host = host

    def read(self, brain: str, kind: str, slug: str, step: int = -1) -> Optional[Target]:
        return getattr(self, "_read_" + kind)(brain, slug, step)

    def _read_skill(self, brain, slug, step):
        import skill_router as SR
        if self.host.skill_protected(brain, slug):
            return None
        asset = SR.read_skill_asset(Path(brain), slug)
        if asset is None:
            return None
        front, body = split_frontmatter(asset.content.decode("utf-8"))
        return Target("skill", slug, -1, body.strip(), lambda v: (
            "You are a Javis assistant. Follow the skill below.\n\n<skill>\n" + v + "\n</skill>"),
            meta={"hash": asset.content_hash, "front": front, "path": asset.relative_path})

    def _read_agent(self, brain, slug, step):
        agent = self.host.agent_text(brain, slug)
        if not agent:
            return None
        _front, body = split_frontmatter(agent)
        current = self.host.agent_procedure(brain, slug) or {}
        return Target("agent", slug, -1, str(current.get("text") or ""), lambda v: (
            body.strip() + ("\n\n# Learned procedure\n" + v if v.strip() else "")), meta={"current": current})

    def _read_workflow(self, brain, slug, step):
        import yaml
        path = Path(self.host.workflows_dir(brain)) / f"{slug}.md"
        if not path.is_file():
            return None
        raw = path.read_bytes()
        steps = workflow_steps(raw.decode("utf-8"))
        if not isinstance(step, int) or isinstance(step, bool) or not 0 <= step < len(steps):
            return None
        agent_slug = str(steps[step].get("agent") or "")
        persona = split_frontmatter(self.host.agent_text(brain, agent_slug) or "")[1].strip() if agent_slug else ""

        def prompt(version, material):  # what the runner sends: placeholders replaced, nothing added; step 0 has no prev
            return version.replace("{{input}}", material).replace("{{prev}}", material if step > 0 else "")
        return Target("workflow", slug, step, str(steps[step].get("task") or ""), lambda v: (
            persona or "You are a Javis assistant doing one step of a workflow."), prompt,
            meta={"hash": hashlib.sha256(raw).hexdigest(), "path": str(path)})

    # apply returns undo info; undo restores it
    def apply(self, brain: str, target: Target, new_text: str, run_id: str) -> dict:
        new_text = check_candidate(target.kind, new_text, target.text)
        if target.kind == "agent":
            return {"kind": "agent", **self.host.agent_apply(brain, target.slug, new_text, target.meta.get("current") or {})}
        backups = Path(self.host.backups)
        backups.mkdir(parents=True, exist_ok=True)
        if target.kind == "skill":
            import skill_router as SR
            asset = SR.read_skill_asset(Path(brain), target.slug)
            if asset is None or asset.content_hash != target.meta["hash"]:
                raise ConflictError("target_changed")
            path = Path(brain) / asset.relative_path
            old = path.read_bytes()
            new = (target.meta["front"] + new_text.rstrip() + "\n").encode("utf-8")
        else:
            import fastyaml
            import yaml
            path = Path(target.meta["path"])
            old = path.read_bytes()
            if hashlib.sha256(old).hexdigest() != target.meta["hash"]:
                raise ConflictError("target_changed")
            front, body = split_frontmatter(old.decode("utf-8"))
            meta = fastyaml.safe_load(front[4:-5])
            meta["steps"][target.step]["task"] = new_text.strip()
            new = ("---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n" + body).encode("utf-8")
        backup = backups / f"{target.kind}-{re.sub(r'[^A-Za-z0-9_.-]', '_', target.slug)}-{run_id}.bak"
        backup.write_bytes(old)
        temp = path.with_name(path.name + f".auto-{run_id}.tmp")
        temp.write_bytes(new)
        os.replace(temp, path)
        return {"kind": target.kind, "path": str(path), "backup": str(backup), "new_hash": hashlib.sha256(new).hexdigest()}

    def undo(self, brain: str, info: dict) -> None:
        if info.get("kind") == "agent":
            self.host.agent_undo(brain, info)
            return
        path, backup = Path(info["path"]), Path(info["backup"])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != info["new_hash"]:
            raise ConflictError("changed_since")  # the owner or another change touched it: never overwrite that
        temp = path.with_name(path.name + ".undo.tmp")
        temp.write_bytes(backup.read_bytes())
        os.replace(temp, path)


# -- the learner -------------------------------------------------------------------------------------

class AutoLearner:
    def __init__(self, store: Store, host: Host, *, clock: Callable[[], float] = time.time, width: int = 3):
        self.store, self.host, self.clock, self.width = store, host, clock, width
        self.targets = Targets(host)
        self.background = host.background_call or host.text_call
        # One process runs the learner: a run still "running" at start was cut off by a restart.
        self.store.write(lambda c: c.execute("UPDATE runs SET state='failed', error='interrupted', finished_at=? "
                                             "WHERE state='running'", (self.clock(),)))

    def _allowed(self, brain: str, kind: str) -> bool:
        """Learning for this kind is switched on on the "Tự học" page and the brain's improvement policy is not off."""
        try:
            cfg = self.host.settings(brain) or {}
        except Exception:  # noqa: BLE001 - unknown settings: do not learn
            return False
        return bool(cfg.get("enabled")) and kind in set(cfg.get("kinds") or ()) and self.host.policy_on(brain)

    def _mode(self, brain: str) -> str:
        try:
            return str((self.host.settings(brain) or {}).get("mode") or "auto")
        except Exception:  # noqa: BLE001
            return "dry-run"

    # recording (cheap, no model call; safe to call from request handlers)

    def note_skill_use(self, brain: str, session_id: str, slug: str) -> None:
        if not session_id or not slug:
            return
        self.store.write(lambda c: c.execute("INSERT OR REPLACE INTO skill_uses VALUES(?,?,?,?)",
                                             (session_id, brain, slug, self.clock())))

    def observe_turn(self, brain: str, session_id: str, channel: str, request: str, answer: str, answer_mid,
                     turn_started: float = 0) -> list:
        """Close a chat turn: the new request is the follow-up of this chat's open episodes from EARLIER turns;
        skills used in this turn and agent chats become episodes. Returns the new episode ids."""
        if not session_id or str(channel or "").startswith(_NOT_OWNER_CHANNELS):
            return []
        now, created = self.clock(), []
        before = turn_started or now - 5  # a workflow run this very turn started is not its own follow-up

        def tx(c):
            c.execute("UPDATE episodes SET follow_up=? WHERE session_id=? AND brain=? AND state='pending' "
                      "AND follow_up IS NULL AND created_at<?", (_cut(request, 4000), session_id, brain, before))
            slugs = [r[0] for r in c.execute("SELECT slug FROM skill_uses WHERE session_id=? AND brain=?",
                                             (session_id, brain))]
            c.execute("DELETE FROM skill_uses WHERE session_id=? AND brain=?", (session_id, brain))
            targets = [("skill", s) for s in sorted(set(slugs))]
            if str(channel or "").startswith("agent:"):
                targets.append(("agent", str(channel).split(":", 1)[1]))
            targets = [t for t in targets if t[0] in allowed]
            for kind, slug in targets:
                episode_id = "ep_" + secrets.token_hex(8)
                c.execute("INSERT INTO episodes(id, brain, kind, slug, session_id, answer_mid, request, answer, follow_up, extra, "
                          "created_at, state, verdict, judged_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (episode_id, brain, kind, slug, session_id, int(answer_mid or 0), _cut(request, 4000),
                           _cut(answer, 8000), None, "{}", now, "pending", None, None))
                created.append(episode_id)
        allowed = {k for k in KINDS if self._allowed(brain, k)}
        if not allowed:
            self.store.write(lambda c: c.execute("DELETE FROM skill_uses WHERE session_id=? AND brain=?", (session_id, brain)))
            return []
        self.store.write(tx)
        return created

    def observe_workflow(self, brain: str, slug: str, run_id: str, request: str, output: str, session_id: str = "",
                         source: str = "web") -> str:
        """Only runs the owner started in person (Studio or a workflow chat): unattended runs have nobody to react,
        and a busy loop would eat the day's judgments."""
        if source != "web" or not session_id or not self._allowed(brain, "workflow"):
            return ""
        episode_id = "ep_" + secrets.token_hex(8)
        self.store.write(lambda c: c.execute("INSERT INTO episodes(id, brain, kind, slug, session_id, answer_mid, request, answer, follow_up, extra, "
                          "created_at, state, verdict, judged_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            episode_id, brain, "workflow", slug, session_id or "", 0, _cut(request, 4000), _cut(output, 8000), None,
            json.dumps({"run_id": run_id}), self.clock(), "pending", None, None)))
        return episode_id

    # background work: one unit per call, run in a worker thread

    def _count(self, brain: str, column: str) -> int:
        rows = self.store.read(f"SELECT {column} FROM counters WHERE brain=? AND day=?", (brain, _today(self.clock)))
        return int(rows[0][column]) if rows else 0

    def _bump(self, brain: str, column: str) -> None:
        day = _today(self.clock)
        self.store.write(lambda c: (c.execute("INSERT OR IGNORE INTO counters(brain, day) VALUES(?,?)", (brain, day)),
                                    c.execute(f"UPDATE counters SET {column}={column}+1 WHERE brain=? AND day=?", (brain, day))))

    def step(self) -> dict:
        """Judge a few ready episodes, or else run one learning run. Returns what it did."""
        now = self.clock()
        self.store.write(lambda c: (
            c.execute("UPDATE episodes SET state='expired' WHERE state='pending' AND created_at<?", (now - EXPIRE_AFTER_S,)),
            c.execute("DELETE FROM mistakes WHERE run_id IS NULL AND created_at<?", (now - MISTAKE_TTL_S,)),
            c.execute("DELETE FROM skill_uses WHERE ts<?", (now - 86400,)),
            c.execute("DELETE FROM episodes WHERE state!='pending' AND created_at<?", (now - KEEP_EPISODES_S,))))
        judged = self.judge_ready()
        if judged:
            return {"judged": judged}
        target = self.next_target()
        if target is None:
            return {}
        return {"run": self.learn(*target)}

    def judge_ready(self) -> int:
        now, done = self.clock(), 0
        rows = self.store.read("SELECT * FROM episodes WHERE state='pending' AND (follow_up IS NOT NULL OR created_at<?) "
                               "ORDER BY attempts, created_at LIMIT 50", (now - READY_AFTER_S,))
        engines = {}
        for episode in rows:
            if done >= JUDGE_BATCH:
                break
            brain = episode["brain"]
            if not self._allowed(brain, episode["kind"]):
                self._close(episode["id"], "skipped", "learning_off")
                continue
            if self._count(brain, "judged") >= JUDGE_PER_DAY:
                continue
            if brain not in engines:  # an engine that cannot be built is nobody's episode's fault
                try:
                    self.host.engine_ready(brain)
                    engines[brain] = True
                except Exception:  # noqa: BLE001
                    engines[brain] = False
            if not engines[brain]:
                continue
            try:
                self.judge(episode)
            except EngineError as error:  # a failed call: retried later, given up on after a few tries
                print(f"[auto-learning judge] {error}", flush=True)
                tries = int(episode.get("attempts") or 0) + 1
                self.store.write(lambda c: c.execute("UPDATE episodes SET attempts=? WHERE id=?", (tries, episode["id"])))
                if tries >= JUDGE_ATTEMPTS:
                    self._close(episode["id"], "skipped", "engine_failed")
                return done
            except Exception as error:  # noqa: BLE001 - this episode cannot be judged; never block the others
                self._close(episode["id"], "skipped", f"error: {type(error).__name__}"[:60])
            done += 1
        return done

    def _close(self, episode_id: str, state: str, verdict: str) -> None:
        self.store.write(lambda c: c.execute("UPDATE episodes SET state=?, verdict=?, judged_at=? WHERE id=?",
                                             (state, verdict, self.clock(), episode_id)))

    def judge(self, episode: dict) -> str:
        brain, kind, slug = episode["brain"], episode["kind"], episode["slug"]
        extra = json.loads(episode.get("extra") or "{}")
        if kind == "workflow":
            run = self.host.workflow_run(extra.get("run_id", "")) or {}
            steps = run.get("steps") or []
            target_text = self._workflow_text(brain, slug)
            work = "\n\n".join(f"### Step {s.get('i')} ({s.get('agent')})\nTask: {_cut(s.get('task'), 800)}\n"
                               f"Output: {_cut(s.get('output') or s.get('error'), 1500)}" for s in steps)
            episode = {**episode, "answer": (work + "\n\n### Final\n" + str(episode.get("answer") or "")).strip()}
            target = None
        else:
            target = self.targets.read(brain, kind, slug)
            if target is None:
                self._close(episode["id"], "skipped", "target_unavailable")
                return "skipped"
            target_text = target.text if kind == "skill" else target.system(target.text)
        if target_text is None:
            self._close(episode["id"], "skipped", "target_unavailable")
            return "skipped"
        reaction = self.host.reaction(episode["session_id"], episode["answer_mid"]) if episode["answer_mid"] else ""
        try:
            raw = self.background("You are a careful reviewer. Answer with JSON only.",
                                      judge_prompt(kind, target_text, episode, reaction))
        except Exception as error:  # noqa: BLE001
            raise EngineError(f"{type(error).__name__}: {error}") from error
        self._bump(brain, "judged")
        try:
            data = parse_json(raw)
        except ValueError:
            self._close(episode["id"], "judged", "unsure")
            return "unsure"
        verdict = data.get("verdict") if data.get("verdict") in ("ok", "mistake", "unsure") else "unsure"
        case = data.get("case") if isinstance(data.get("case"), dict) else {}
        criteria = [str(c).strip() for c in case.get("criteria") or [] if str(c).strip()][:5]
        step = data.get("step") if kind == "workflow" else -1
        bad_step = kind == "workflow" and not (isinstance(step, int) and not isinstance(step, bool)
                                               and 0 <= step < len(workflow_steps(target_text)))
        if verdict == "mistake" and (not str(case.get("prompt") or "").strip() or not criteria or bad_step):
            verdict = "unsure"  # a mistake Javis cannot turn into a test teaches nothing
        if verdict == "mistake":
            step = int(step) if kind == "workflow" else -1
            self.store.write(lambda c: c.execute("INSERT INTO mistakes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                "mk_" + secrets.token_hex(8), brain, target_key(kind, slug, step), kind, slug, step, episode["id"],
                str(data.get("what") or "")[:600], str(data.get("right") or "")[:600],
                str(case["prompt"])[:6000], json.dumps(criteria, ensure_ascii=False), self.clock(), None)))
        self._close(episode["id"], "judged", verdict)
        return verdict

    def _workflow_text(self, brain, slug):
        path = Path(self.host.workflows_dir(brain)) / f"{slug}.md"
        return path.read_bytes().decode("utf-8") if path.is_file() else None

    def next_target(self) -> Optional[tuple]:
        now = self.clock()
        rows = self.store.read("SELECT brain, target, kind, slug, step, COUNT(*) AS n FROM mistakes WHERE run_id IS NULL "
                               "GROUP BY brain, target HAVING n>=? ORDER BY MIN(created_at)", (MIN_MISTAKES,))
        for row in rows:
            brain, target = row["brain"], row["target"]
            if not self._allowed(brain, row["kind"]) or self._mode(brain) == "dry-run":
                continue  # "Chạy thử" only judges and records what it would learn
            if self._count(brain, "runs") >= RUNS_PER_DAY:
                continue
            if self.store.read("SELECT 1 FROM skips WHERE brain=? AND target=? AND until>?", (brain, target, now)):
                continue
            last = self.store.read("SELECT MAX(started_at) AS t FROM runs WHERE brain=? AND target=?", (brain, target))
            if last and last[0]["t"] and now - last[0]["t"] < COOL_DOWN_S:
                continue
            return brain, row["kind"], row["slug"], row["step"]
        return None

    def learn(self, brain: str, kind: str, slug: str, step: int = -1) -> dict:
        key, run_id, now = target_key(kind, slug, step), "alr_" + secrets.token_hex(8), self.clock()
        self.store.write(lambda c: c.execute("INSERT INTO runs(id, brain, target, kind, slug, step, state, started_at) "
                                             "VALUES(?,?,?,?,?,?,?,?)", (run_id, brain, key, kind, slug, step, "running", now)))

        def finish(state, verdict="", report=None, error="", applied=None):
            self.store.write(lambda c: c.execute(
                "UPDATE runs SET state=?, finished_at=?, verdict=?, report=?, error=?, applied=?, undo=?, new_hash=? "
                "WHERE id=?", (state, self.clock(), verdict, json.dumps(report or {}, ensure_ascii=False), error,
                               1 if applied else 0, json.dumps(applied) if applied else None,
                               (applied or {}).get("new_hash"), run_id)))
            return {"run_id": run_id, "state": state, "verdict": verdict, "error": error, "applied": bool(applied)}

        try:
            self.host.engine_ready(brain)
            mistakes = self.store.read("SELECT * FROM mistakes WHERE brain=? AND target=? AND run_id IS NULL "
                                       "ORDER BY created_at DESC LIMIT 8", (brain, key))
            target = self.targets.read(brain, kind, slug, step)
            if target is None or (kind == "workflow" and not placeholders(target.text)):
                # Gone, protected, or a step that never sees its input: these mistakes cannot teach this target.
                self.store.write(lambda c: c.execute("UPDATE mistakes SET run_id=? WHERE brain=? AND target=? "
                                                     "AND run_id IS NULL", (run_id, brain, key)))
                return finish("skipped", error="target_unavailable" if target is None else "untestable")
            self._bump(brain, "runs")
            oks = self.store.read("SELECT request, answer FROM episodes WHERE brain=? AND kind=? AND slug=? "
                                  "AND verdict='ok' ORDER BY judged_at DESC LIMIT 6", (brain, kind, slug))
            shown = {"skill": target.text, "agent": target.system(target.text),
                     "workflow": f"Step task:\n{target.text}\n\nAssistant doing the step:\n{target.system(target.text)}\n"
                                 "(each test prompt is the material the step receives)"}[kind]
            try:
                cases = build_cases(parse_json(self.background(
                    "You write test sets. Answer with JSON only.", writer_prompt(kind, shown, mistakes, oks))))
            except ValueError as error:
                if str(error) == "untestable":
                    self.store.write(lambda c: c.execute("INSERT OR REPLACE INTO skips VALUES(?,?,?,?)",
                                                         (brain, key, self.clock() + SKIP_UNTESTABLE_S, "untestable")))
                return finish("skipped", error=str(error)[:200])

            def solve(version, case_prompt):
                return self.host.text_call(target.system(version), target.prompt(version, case_prompt))

            def improve(instructions):
                answer = self.background(f"You improve the instructions of a Javis {kind}. Keep their language "
                                             "and style." + (" Keep every {{placeholder}} exactly as it is."
                                                             if kind == "workflow" else ""), instructions)
                check_candidate(kind, L.extract_skill(answer), target.text)  # unsafe text never enters the run
                return answer

            def check(case, output):
                data = parse_json(self.background(GRADER_SYSTEM, grader_prompt(case.prompt, case.answer, output)))
                score = max(0.0, min(1.0, float(data.get("score", 0))))
                return {"pass": bool(data.get("pass")) and score >= 0.999, "score": score,
                        "feedback": str(data.get("feedback") or "")[:300]}

            said = "\n".join(f"- What went wrong: {m['what']} Right behaviour: {m['right_way']}" for m in mistakes)
            loop = L.Loop(cases, solve=solve, improve=improve, check=check, width=self.width, context=said)
            result = loop.run(target.text, k=1, qualification_repeats=2, early_stop=True)
            report = {**result.report, "chosen": result.chosen, "tuning": result.tuning, "case_count": len(cases),
                      "case_list": [{"id": c.id, "family": c.family, "split": c.split, "prompt": _cut(c.prompt, 600),
                                     "criteria": c.answer} for c in cases]}
            lost = set(result.report.get("regressions") or []) | {
                c["case"] for c in result.report.get("cases") or [] if c.get("outcome") == "loss"}
            report["lost_outputs"] = [{"case": r.case_id, "version": r.version, "repeat": r.repeat,
                                       "output": _cut(r.output, 1200), "feedback": r.feedback}
                                      for r in result.qualification if r.case_id in lost][:12]
            used = [m["id"] for m in mistakes]
            self.store.write(lambda c: c.executemany("UPDATE mistakes SET run_id=? WHERE id=?",
                                                     [(run_id, m) for m in used]))
            if result.report.get("verdict") != "helped" or result.report.get("regressions"):
                return finish("done", result.report.get("verdict", "keep_base"), report)
            if not self._allowed(brain, kind):  # the owner switched learning off while this ran
                return finish("done", "helped", {**report, "not_applied": "learning_off"})
            chosen = check_candidate(kind, result.versions[result.chosen], target.text)
            if self._mode(brain) != "auto":  # "Đề xuất": everything is ready, the owner presses Apply
                self.store.write(lambda c: c.execute("UPDATE runs SET proposal=?, base_sha=? WHERE id=?",
                                                     (chosen, _sha(target.text), run_id)))
                return finish("done", "helped", {**report, "not_applied": "suggest_mode"})
            applied = self.targets.apply(brain, target, chosen, run_id)
            return finish("done", "helped", report, applied=applied)
        except L.EngineUnavailable as error:
            return finish("failed", error=f"engine_unavailable: {error}"[:300])
        except Exception as error:  # noqa: BLE001 - a run never stays "running"
            return finish("failed", error=f"{type(error).__name__}: {error}"[:300])

    # owner view

    def history(self, brain: str, limit: int = 20) -> list:
        rows = self.store.read("SELECT id, target, kind, slug, step, state, verdict, started_at, finished_at, applied, "
                               "undone_at, error, report, proposal FROM runs WHERE brain=? ORDER BY started_at DESC LIMIT ?",
                               (brain, limit))
        for row in rows:
            row["proposed"] = bool(row.pop("proposal")) and not row["applied"]
            report = json.loads(row.pop("report") or "{}")
            row["summary"] = {k: report.get(k) for k in ("outcomes", "p_value", "base_pass_rate",
                                                         "candidate_pass_rate", "regressions", "case_count")}
        return rows

    def stats(self, brain: str) -> dict:
        pending = self.store.read("SELECT COUNT(*) AS n FROM episodes WHERE brain=? AND state='pending'", (brain,))[0]["n"]
        open_mistakes = self.store.read("SELECT target, COUNT(*) AS n FROM mistakes WHERE brain=? AND run_id IS NULL "
                                        "GROUP BY target", (brain,))
        return {"pending": pending, "mistakes": {r["target"]: r["n"] for r in open_mistakes},
                "judged_today": self._count(brain, "judged"), "runs_today": self._count(brain, "runs")}

    def apply_proposal(self, brain: str, run_id: str) -> dict:
        """"Đề xuất" mode: the owner applies a helped result; only over the exact text the run started from."""
        rows = self.store.read("SELECT * FROM runs WHERE id=? AND brain=?", (run_id, brain))
        if not rows:
            raise ValueError("run_not_found")
        run = rows[0]
        if run["applied"]:
            return {"run_id": run_id, "applied": True}  # a retry after a lost response
        if not run["proposal"]:
            raise ConflictError("nothing_to_apply")
        if not self.host.policy_on(brain):
            raise PermissionError("improvement_disabled")
        target = self.targets.read(brain, run["kind"], run["slug"], run["step"])
        if target is None or _sha(target.text) != run["base_sha"]:
            raise ConflictError("changed_since")
        applied = self.targets.apply(brain, target, run["proposal"], run_id)
        self.store.write(lambda c: c.execute("UPDATE runs SET applied=1, undo=?, new_hash=? WHERE id=?",
                                             (json.dumps(applied), applied.get("new_hash"), run_id)))
        return {"run_id": run_id, "applied": True}

    def undo(self, brain: str, run_id: str) -> dict:
        rows = self.store.read("SELECT * FROM runs WHERE id=? AND brain=?", (run_id, brain))
        if not rows:
            raise ValueError("run_not_found")
        run = rows[0]
        if run["undone_at"]:
            return {"run_id": run_id, "undone": True}  # a retry after a lost response
        if not run["applied"]:
            raise ConflictError("nothing_to_undo")
        self.targets.undo(brain, json.loads(run["undo"]))
        self.store.write(lambda c: c.execute("UPDATE runs SET undone_at=? WHERE id=?", (self.clock(), run_id)))
        return {"run_id": run_id, "undone": True}
