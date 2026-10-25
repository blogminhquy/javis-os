"""M4 skill routing surface: description-only candidates and a deterministic routing evaluator.

Spec 9.2 and 16.1: the skill `description` is its own behaviour surface. A routing candidate changes
only that value; the body, every other frontmatter key, name, enabled state and group stay byte-equal.

The evaluator measures Javis's own lazy router (the deterministic `LazySkillSource._score` ranking
used for API engines) over two metadata views: the current skills, and the same skills with the
target's candidate description. Native CLI engines choose skills by model judgement; that routing is
not measured here and reports must say so.

Case kinds: `positive` (this skill should be chosen), `negative` (no skill should be), `competing`
(another skill should be chosen). The hard gate of spec M4: the candidate may not turn a correct
negative or competing case into a wrong or unnecessary selection.
"""
from __future__ import annotations

import json
import re

import skill_router as SR
from improvement_comparison_results import _statistics

KINDS = ("positive", "negative", "competing")
LABELS = ("correct", "missed", "wrong_skill", "unnecessary", "deferred")
MAX_CASES = 200


def _yaml_scalar(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)  # JSON strings are valid YAML double-quoted scalars


def patch_description(raw: bytes, description: str) -> bytes:
    """Replace only the single-line top-level `description:` value. Anything else refuses."""
    if type(description) is not str:
        raise ValueError("invalid_routing_description")
    description = " ".join(description.split())
    problem = SR.validate_description(description)
    if not description or problem:
        raise ValueError("invalid_routing_description")
    text = raw.decode("utf-8")
    newline = "\r\n" if "\r\n" in text[:4096] else "\n"
    if not text.startswith("---"):
        raise ValueError("routing_frontmatter_required")
    end = text.find(newline + "---", 3)
    if end < 0:
        raise ValueError("routing_frontmatter_required")
    header, rest = text[:end], text[end:]
    lines = header.split(newline)
    hits = [i for i, line in enumerate(lines) if re.match(r"description\s*:", line)]
    if len(hits) != 1:
        raise ValueError("routing_description_line_required")
    index = hits[0]
    value = lines[index].split(":", 1)[1].strip()
    following = lines[index + 1] if index + 1 < len(lines) else ""
    if value in ("|", ">", "|-", ">-", "|+", ">+") or (following[:1] in (" ", "\t") and following.strip()):
        # Block or continued scalars are not edited in V1: the owner can rewrite them by hand.
        raise ValueError("routing_multiline_description_unsupported")
    lines[index] = "description: " + _yaml_scalar(description)
    patched = (newline.join(lines) + rest).encode("utf-8")
    before, after = SR.split_frontmatter(text), SR.split_frontmatter(patched.decode("utf-8"))
    if before is None or after is None or before[1] != after[1]:
        raise ValueError("routing_body_changed")
    old_meta, new_meta = dict(before[0]), dict(after[0])
    if new_meta.get("description") != description:
        raise ValueError("routing_description_not_applied")
    old_meta.pop("description", None); new_meta.pop("description", None)
    if old_meta != new_meta:
        raise ValueError("routing_other_metadata_changed")
    return patched


def _candidates(manifests):
    result = []
    for manifest in manifests:
        slug = manifest["slug"]
        name = str(manifest.get("name") or slug).strip()[:180]
        summary = str(manifest.get("description") or name).strip()[:2000]
        group = str(manifest.get("group") or "Chung").strip()[:120]
        result.append({"slug": slug, "name": slug, "aliases": list(dict.fromkeys((slug, name, group))), "summary": summary})
    return result


def route(query: str, manifests: list, *, min_score: float = 0.24, ambiguity_margin: float = 0.08) -> dict:
    """Same decision the bound lazy router makes: rank by score, refuse low or ambiguous picks."""
    from lazy_skill_runtime import LazySkillSource, _EXPLICIT_RE
    ranked = sorted(((LazySkillSource._score(query, item), item["slug"]) for item in _candidates(manifests)),
                    key=lambda pair: (-pair[0], pair[1]))
    explicit = bool(_EXPLICIT_RE.search(query or ""))
    if not ranked:
        return {"action": "fallback" if explicit else "none", "slug": "", "score": 0.0}
    top_score, top = ranked[0]
    runner = ranked[1][0] if len(ranked) > 1 else 0.0
    if top_score < min_score:
        return {"action": "fallback" if explicit else "none", "slug": "", "score": round(top_score, 6)}
    if runner and top_score - runner < ambiguity_margin:
        return {"action": "fallback", "slug": "", "score": round(top_score, 6)}
    return {"action": "load", "slug": top, "score": round(top_score, 6)}


def label(case: dict, decision: dict) -> str:
    expected = case.get("expected") or ""
    if decision["action"] == "fallback":
        return "deferred"  # the legacy full index takes over; neither a hit nor a miss of this router
    chosen = decision["slug"] if decision["action"] == "load" else ""
    if not expected:
        return "unnecessary" if chosen else "correct"
    if chosen == expected:
        return "correct"
    return "wrong_skill" if chosen else "missed"


def validate_cases(cases, slugs) -> list:
    if type(cases) is not list or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError("invalid_routing_cases")
    clean, seen = [], set()
    for case in cases:
        if type(case) is not dict or set(case) - {"query", "expected", "kind"}:
            raise ValueError("invalid_routing_case")
        query, kind, expected = case.get("query"), case.get("kind"), case.get("expected") or ""
        if type(query) is not str or not 1 <= len(query.strip()) <= 500 or kind not in KINDS or type(expected) is not str:
            raise ValueError("invalid_routing_case")
        if (kind == "negative") != (expected == "") or (expected and expected not in slugs):
            raise ValueError("invalid_routing_case_expectation")
        key = " ".join(query.casefold().split())
        if key in seen:
            raise ValueError("duplicate_routing_case")
        seen.add(key)
        clean.append({"query": query.strip(), "expected": expected, "kind": kind})
    if not any(case["kind"] in ("negative", "competing") for case in clean):
        # Without one, the regression gate is empty and any description would pass it.
        raise ValueError("routing_regression_case_required")
    return clean


def evaluate(cases: list, baseline: list, target: str, description: str, *, multiple_tests: int = 1,
             decide=None) -> dict:
    """Paired routing report for one description candidate. Manifests are host-read, never client data.

    `decide(query, descriptions)` is the production decision (the live lazy router with or without the
    overlay); without it the pure `route()` model over the given manifests is used (tests)."""
    slugs = {item["slug"] for item in baseline}
    if target not in slugs:
        raise PermissionError("routing_target_unavailable")
    cases = validate_cases(cases, slugs)
    candidate = [{**item, "description": description} if item["slug"] == target else item for item in baseline]
    if decide is None:
        def decide(query, descriptions):
            return route(query, candidate if descriptions else baseline)
    rows, outcomes = [], {"win": 0, "loss": 0, "tie": 0, "unknown": 0}
    counts = {"baseline": dict.fromkeys(LABELS, 0), "candidate": dict.fromkeys(LABELS, 0)}
    required_losses = 0
    for case in cases:
        before, after = decide(case["query"], None), decide(case["query"], {target: description})
        b, c = label(case, before), label(case, after)
        counts["baseline"][b] += 1
        counts["candidate"][c] += 1
        if b == c or (b != "correct" and c != "correct"):
            outcome = "tie"
        else:
            outcome = "win" if c == "correct" else "loss"
        outcomes[outcome] += 1
        if case["kind"] in ("negative", "competing") and b == "correct" and c in ("wrong_skill", "unnecessary"):
            required_losses += 1
        rows.append({**case, "baseline": {**before, "label": b}, "candidate": {**after, "label": c}, "outcome": outcome})
    stats = _statistics(outcomes, multiple_tests)
    if required_losses:
        verdict = "rejected"
    elif stats["significant"]:
        verdict = "eligible"
    else:
        verdict = "inconclusive"
    return {"version": 1, "target": target, "description": description, "cases": rows, "counts": counts,
            "outcomes": outcomes, "statistics": stats, "required_loss_count": required_losses,
            "mechanical_verdict": verdict, "measured_router": "javis_lazy_router",
            "native_cli_routing": "not_measured", "business_eligibility": "unverified"}


# -- persisted candidates and main-chat overlays ---------------------------------------------------

import secrets
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

import improvement_store as IM

MAIN_SELECTOR = {"context": "main"}


def main_scope_hash() -> str:
    """The brain's own main chat. Assistant chats list skill names only, so descriptions never route there."""
    return IM._hash(MAIN_SELECTOR)


def _slug_of(canonical_ref: str) -> str:
    match = re.fullmatch(r"skills/([a-z0-9][a-z0-9_-]{0,127})/SKILL\.md", canonical_ref or "")
    if not match:
        raise PermissionError("routing_target_unsupported")
    return match.group(1)


def _overlay_public(row) -> dict:
    keys = ("target_id", "candidate_id", "canonical_ref", "base_hash", "description", "state", "reason", "generation",
            "created_at", "updated_at")
    return {**{key: row[key] for key in keys}, "overlay_id": row["id"], "scope": dict(MAIN_SELECTOR)}


class Routing:
    """Owner commands: evaluate a description candidate, apply it to the main chat, revert, reconcile."""

    def __init__(self, assets, *, clock=time.time, registry=None):
        """`registry`: the live capability registry, so evaluation runs the production lazy router."""
        if type(assets) is not IM.ImprovementStore:
            raise TypeError("concrete_routing_assets_required")
        self.assets, self.store, self.blobs, self.clock = assets, assets.store, assets.blobs, clock
        self.registry = registry

    def _decider(self, brain):
        if self.registry is None:
            return None
        from lazy_skill_runtime import LazySkillSource
        source = LazySkillSource(self.registry)

        def decide(query, descriptions):
            selected = source.resolve(Path(brain), query, descriptions=descriptions)
            return {"action": selected.action, "slug": selected.slug if selected.action == "load" else "",
                    "score": selected.score, "reason": selected.reason}
        return decide

    def _available(self) -> bool:
        return IM._schema_version(self.store) >= 13

    def evaluate(self, principal, target_id: str, description: str, cases: list, *, event_key: str) -> dict:
        brain = IM._brain(principal)
        payload = {"target_id": target_id, "description": description, "cases": cases}
        IM.ensure(self.store)
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, "routing_evaluate", payload)
            if replay is not None:
                return replay
            if self.assets._policy(connection, brain)["mode"] == "off":
                raise PermissionError("improvement_disabled")
            target = self.assets._target(connection, brain, target_id)
            if target["kind"] != "skill" or target["status"] != "live":
                raise PermissionError("target_unavailable")
        slug = _slug_of(target["canonical_ref"])
        canonical = SR.read_skill_asset(Path(brain), slug)
        if canonical is None or canonical.relative_path != target["canonical_ref"]:
            raise PermissionError("skill_unavailable")
        meta = SR.split_frontmatter(canonical.text)[0]
        if SR.ban_dich(meta, "description"):
            # V1 overlays the base description only; a translated description would be swapped silently.
            raise ValueError("routing_translated_description_unsupported")
        patched = patch_description(canonical.content, description)
        if SR.split_frontmatter(patched.decode("utf-8"))[0].get("description") == meta.get("description"):
            raise ValueError("routing_description_unchanged")
        description = SR.split_frontmatter(patched.decode("utf-8"))[0]["description"]
        report = evaluate(cases, SR.list_skill_manifests(Path(brain)), slug, description, decide=self._decider(brain))
        report_blob = self.blobs.write(brain, IM._json(report).encode("utf-8"))
        content_hash = self.blobs.write(brain, patched)
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "routing_evaluate", payload)
            if replay is not None:
                return replay
            if self.assets._policy(connection, brain)["mode"] == "off":
                raise PermissionError("improvement_disabled")
            if self.assets._target(connection, brain, target_id)["status"] != "live":
                raise PermissionError("target_unavailable")
            identifier = "irc_" + secrets.token_hex(16)
            connection.execute("INSERT INTO improvement_routing_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                               (identifier, brain, target_id, canonical.content_hash, description, content_hash,
                                IM._hash(report), report_blob, report["mechanical_verdict"], principal.by, self.clock()))
            result = {"candidate_id": identifier, "target_id": target_id, "description": description,
                      "verdict": report["mechanical_verdict"], "report": report}
            self.assets._event(connection, principal, event_key, "routing_evaluate", payload, result)
            return result

    def candidates(self, principal, *, target_id: str) -> list:
        brain = IM._brain(principal)
        if not self._available():
            return []
        with closing(self.store._conn()) as connection:
            rows = connection.execute("SELECT id,target_id,description,verdict,created_at FROM improvement_routing_candidates "
                                      "WHERE brain_id=? AND target_id=? ORDER BY created_at DESC LIMIT 50",
                                      (brain, target_id)).fetchall()
        return [{**dict(row), "candidate_id": row["id"]} for row in rows]

    def overlays(self, principal, *, target_id: str | None = None) -> list:
        brain = IM._brain(principal)
        if not self._available():
            return []
        query, args = "SELECT * FROM improvement_routing_overlays WHERE brain_id=?", [brain]
        if target_id is not None:
            query, args = query + " AND target_id=?", args + [target_id]
        with closing(self.store._conn()) as connection:
            return [_overlay_public(row) for row in connection.execute(query + " ORDER BY created_at DESC LIMIT 100", args)]

    def apply(self, principal, candidate_id: str, *, event_key: str) -> dict:
        brain = IM._brain(principal)
        if type(candidate_id) is not str or not re.fullmatch(r"irc_[0-9a-f]{32}", candidate_id):
            raise ValueError("invalid_routing_candidate")
        payload = {"candidate_id": candidate_id}
        IM.ensure(self.store)
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, "routing_apply", payload)
            if replay is not None:
                return replay
            candidate = connection.execute("SELECT * FROM improvement_routing_candidates WHERE id=? AND brain_id=?",
                                           (candidate_id, brain)).fetchone()
            if candidate is None:
                raise PermissionError("routing_candidate_unavailable")
            if candidate["verdict"] == "rejected":
                raise PermissionError("routing_candidate_rejected")
            target = self.assets._target(connection, brain, candidate["target_id"])
        slug = _slug_of(target["canonical_ref"])
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "routing_apply", payload)
            if replay is not None:
                return replay
            if self.assets._policy(connection, brain)["mode"] == "off":
                raise PermissionError("improvement_disabled")
            current = self.assets._target(connection, brain, candidate["target_id"])
            canonical = SR.read_skill_asset(Path(brain), slug)
            if current["status"] != "live" or canonical is None:
                raise PermissionError("skill_unavailable")
            if canonical.content_hash != candidate["base_hash"]:
                raise IM.ConflictError("routing_base_changed")
            scope = main_scope_hash()
            if connection.execute("SELECT 1 FROM improvement_routing_overlays WHERE brain_id=? AND target_id=? "
                                  "AND scope_hash=? AND state='active'", (brain, current["id"], scope)).fetchone():
                raise IM.ConflictError("routing_scope_busy")
            identifier, now = "iro_" + secrets.token_hex(16), self.clock()
            connection.execute("INSERT INTO improvement_routing_overlays VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (identifier, brain, current["id"], candidate_id, current["canonical_ref"], candidate["base_hash"],
                                candidate["description"], scope, "active", "owner_apply", 1, principal.by, now, now))
            result = _overlay_public(connection.execute("SELECT * FROM improvement_routing_overlays WHERE id=?",
                                                        (identifier,)).fetchone())
            self.assets._event(connection, principal, event_key, "routing_apply", payload, result)
            return result

    def revert(self, principal, overlay_id: str, *, expected_generation: int, event_key: str) -> dict:
        brain = IM._brain(principal)
        if type(overlay_id) is not str or not re.fullmatch(r"iro_[0-9a-f]{32}", overlay_id):
            raise ValueError("invalid_routing_overlay")
        if type(expected_generation) is not int or expected_generation < 1 or not self._available():
            raise ValueError("invalid_routing_overlay")
        payload = {"overlay_id": overlay_id, "expected_generation": expected_generation}
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "routing_revert", payload)
            if replay is not None:
                return replay
            row = connection.execute("SELECT * FROM improvement_routing_overlays WHERE id=? AND brain_id=?",
                                     (overlay_id, brain)).fetchone()
            if row is None:
                raise PermissionError("routing_overlay_unavailable")
            if row["generation"] != expected_generation:
                raise IM.ConflictError("stale_routing_overlay")
            if row["state"] != "active":
                raise IM.ConflictError("routing_overlay_not_active")
            connection.execute("UPDATE improvement_routing_overlays SET state='reverted',reason='owner_revert',"
                               "generation=generation+1,updated_at=? WHERE id=?", (self.clock(), overlay_id))
            result = _overlay_public(connection.execute("SELECT * FROM improvement_routing_overlays WHERE id=?",
                                                        (overlay_id,)).fetchone())
            self.assets._event(connection, principal, event_key, "routing_revert", payload, result)
            return result

    def reconcile(self, principal) -> list:
        """Suspend overlays whose base changed for good (edit, disable, delete, retired target)."""
        from improvement_activation import _source_gone
        brain = IM._brain(principal)
        if not self._available():
            return []
        with closing(self.store._conn()) as connection:
            rows = connection.execute("SELECT o.*,t.status AS target_status,t.identity FROM improvement_routing_overlays o "
                "JOIN improvement_targets t ON t.id=o.target_id AND t.brain_id=o.brain_id "
                "WHERE o.brain_id=? AND o.state='active'", (brain,)).fetchall()
        pending = []
        for row in rows:
            slug = _slug_of(row["canonical_ref"])
            if row["target_status"] != "live":
                pending.append((row, "target_retired"))
            elif _source_gone(brain, slug):
                pending.append((row, "source_unavailable"))
            else:
                from improvement_activation import _file_identity
                canonical = SR.read_skill_asset(Path(brain), slug)
                try:
                    replaced = _file_identity(brain, row["canonical_ref"]) != row["identity"]
                except OSError:
                    replaced = False
                if canonical is not None and (canonical.content_hash != row["base_hash"] or replaced):
                    pending.append((row, "canonical_changed"))
        suspended = []
        for row, reason in pending:
            with self.store._Tx(self.store) as connection:
                if connection.execute("UPDATE improvement_routing_overlays SET state='suspended',reason=?,"
                        "generation=generation+1,updated_at=? WHERE id=? AND state='active' AND generation=?",
                        (reason, self.clock(), row["id"], row["generation"])).rowcount:
                    suspended.append({"overlay_id": row["id"], "reason": reason})
        return suspended


# -- read time ---------------------------------------------------------------------------------------

def main_chat_descriptions(root) -> dict:
    """{slug: description} the brain's main chat on an API engine should see. Canonical when unsure."""
    import improvement_activation as IA
    from improvement_task_skill_scope import has_binding
    sources = IA._SOURCES[0]
    if sources is None or has_binding():
        return {}  # a bound task scope serves its frozen projection; never mix in live overlays
    database = sources[0]
    try:
        if not database.is_file():
            return {}
        brain = str(Path(root).resolve(strict=True))
        connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        with closing(connection):
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='improvement_routing_overlays'").fetchone():
                return {}
            rows = connection.execute("SELECT o.canonical_ref,o.base_hash,o.description,t.identity FROM improvement_routing_overlays o "
                "JOIN improvement_targets t ON t.id=o.target_id AND t.brain_id=o.brain_id "
                "WHERE o.brain_id=? AND o.scope_hash=? AND o.state='active' AND t.status='live'",
                (brain, main_scope_hash())).fetchall()
        result = {}
        for row in rows:
            slug = _slug_of(row["canonical_ref"])
            canonical = SR.read_skill_asset(Path(brain), slug)  # disabled or edited skills never get an overlay
            if (canonical is not None and canonical.relative_path == row["canonical_ref"]
                    and canonical.content_hash == row["base_hash"]
                    and IA._file_identity(brain, row["canonical_ref"]) == row["identity"]):
                result[slug] = row["description"]
        return result
    except (OSError, ValueError, sqlite3.Error, PermissionError) as error:
        print(f"[improvement routing] {type(error).__name__}: {error}", file=sys.stderr)
        return {}


def with_descriptions(metas: list, descriptions: dict) -> list:
    """Copy of skill metadata rows with owner-applied descriptions; rows without one are untouched."""
    if not descriptions:
        return metas
    return [{**meta, "description": descriptions[meta.get("slug")]} if meta.get("slug") in descriptions else meta
            for meta in metas]
