"""Self-learning loop: Harness² sequential recursion over one skill text, with Javis's baseline rule.

Shape follows harness2/core/recursion.py `run_sequential` (pin 1cfe254e): for t in 1..k, two proposals from the
shared evidence (INV: how the work is done; DOM: the business procedure), each rolled out on the tuning cases,
then one composition over the round pool becomes the next current version. Javis keeps its own contract where
it differs from upstream selection:

- the baseline always stays a candidate and wins ties: a version is chosen only if it beats the baseline on the
  tuning cases by a strict margin;
- the chosen version is judged once on the sealed qualification cases, paired with the baseline, every repeat
  kept; that report alone says whether it helped;
- the improver never sees a qualification case, its answer or its output (evidence boundary, tested);
- nothing is applied here: the result is a report and a candidate text for the owner.

Engines are injected callables, so the same loop runs on fakes in tests and on the brain's selected engine in a
pilot or in the product. `solve(skill_text, prompt) -> text`, `improve(instructions) -> text`,
`check(case, output) -> {"pass": bool, "score": float, "feedback": str}`.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

ANGLES = {
    "INV": ("how the work is done: the steps, checks and output discipline that would have avoided the failures "
            "seen, without changing what the business wants"),
    "DOM": ("the business procedure itself: the conventions, exceptions and decision rules of this kind of work "
            "that the failures show are missing or wrong"),
}
MAX_SKILL_CHARS = 12000


@dataclass(frozen=True)
class Case:
    id: str
    family: str
    split: str  # tuning | qualification
    prompt: str
    answer: object


@dataclass
class Rollout:
    version: str
    case_id: str
    repeat: int
    output: str
    passed: bool
    score: float
    feedback: str
    seconds: float
    error: bool = False


@dataclass
class LoopResult:
    versions: dict = field(default_factory=dict)       # label -> skill text
    notes: dict = field(default_factory=dict)          # label -> why it was kept or refused
    tuning: dict = field(default_factory=dict)         # label -> mean tuning score
    chosen: str = "base"
    qualification: list = field(default_factory=list)  # Rollout rows (base and chosen)
    report: dict = field(default_factory=dict)
    calls: dict = field(default_factory=lambda: {"solve": 0, "improve": 0})

    def to_dict(self) -> dict:
        return {"chosen": self.chosen, "tuning": self.tuning, "notes": self.notes, "report": self.report,
                "calls": self.calls,
                "version_hashes": {k: hashlib.sha256(v.encode("utf-8")).hexdigest() for k, v in self.versions.items()}}


def _evidence(cases: dict, rollouts: list, label: str, limit: int = 6000) -> str:
    """Tuning-only evidence of one version: task, output, checker feedback. Qualification never enters here."""
    parts = []
    for r in rollouts:
        if getattr(r, "error", False):
            continue  # an engine failure says nothing about the skill
        case = cases[r.case_id]
        if case.split != "tuning":
            raise ValueError("evidence_boundary")  # defensive: the loop never passes these
        parts.append(f"### Case {case.id} ({'PASS' if r.passed else 'FAIL'}, score {r.score:.2f})\n"
                     f"Task:\n{case.prompt}\n\nOutput of version {label}:\n{r.output[:1500]}\n\nChecker: {r.feedback}")
    text = "\n\n".join(parts)
    return text[:limit * 4]


def propose_instructions(angle: str, current: str, evidence: str, history: str = "", context: str = "") -> str:
    return (
        "You improve a skill: written instructions an AI assistant follows for one kind of work.\n"
        f"Change ONE thing about {ANGLES[angle]}.\n"
        "Rules: keep everything that works; do not paste case data, names or answers into the skill; write rules "
        "that generalise to new cases of the same work; keep it concise; if the evidence shows no fixable failure, "
        "return the current skill unchanged.\n"
        "Return ONLY the full new skill text between <skill> and </skill>.\n\n"
        f"## Current skill\n<current>\n{current}\n</current>\n\n## Tuning evidence\n{evidence}\n"
        + (f"\n## What the owner said in real use\n{context}\n" if context else "")
        + (f"\n## Earlier attempts in this run\n{history}\n" if history else ""))


def compose_instructions(current: str, pool: list, context: str = "") -> str:
    listing = "\n\n".join(f"## Candidate {label} (tuning score {score:.2f})\n<candidate>\n{text}\n</candidate>"
                          for label, text, score in pool)
    return (
        "You combine improvements to a skill: written instructions an AI assistant follows for one kind of work.\n"
        "Below are the current skill and candidate revisions with their scores on the same tuning cases. Write one "
        "skill that keeps what helped, drops what hurt or did nothing, and stays coherent and concise. Do not paste "
        "case data or answers. If nothing helped, return the current skill unchanged.\n"
        "Return ONLY the full skill text between <skill> and </skill>.\n\n"
        f"## Current skill\n<current>\n{current}\n</current>\n\n{listing}\n"
        + (f"\n## What the owner said in real use\n{context}\n" if context else ""))


def extract_skill(text: str) -> str:
    start, end = text.find("<skill>"), text.rfind("</skill>")
    if start < 0 or end <= start:
        raise ValueError("skill_not_returned")
    skill = text[start + len("<skill>"):end].strip()
    if not 20 <= len(skill) <= MAX_SKILL_CHARS:
        raise ValueError("skill_size")
    return skill


def sign_test(wins: int, losses: int) -> float:
    """Two-sided exact sign test p-value over untied pairs."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


class LoopStopped(Exception):
    """The owner cancelled the run."""


class EngineUnavailable(Exception):
    """Too many engine failures to judge anything: the run fails instead of reporting a fake verdict."""


MAX_ERROR_SHARE = 0.2
EARLY_WINS = 8  # one repeat, 8 wins and no loss: sign test p 0.008


def _same(a: str, b: str) -> bool:
    return " ".join(a.split()) == " ".join(b.split())


class Loop:
    def __init__(self, cases: list, *, solve: Callable, improve: Callable, check: Callable, width: int = 4,
                 clock: Callable[[], float] = time.monotonic, on_event: Callable = lambda kind, data: None,
                 stop: Callable[[], bool] = lambda: False, context: str = ""):
        """`context`: what the owner said about real mistakes (corrections from chat). It never contains a
        qualification case; the improver may read it, the sealed verdict still decides."""
        ids = [c.id for c in cases]
        if len(set(ids)) != len(ids) or any(c.split not in ("tuning", "qualification") for c in cases):
            raise ValueError("invalid_cases")
        tuning_families = {c.family for c in cases if c.split == "tuning"}
        if tuning_families & {c.family for c in cases if c.split == "qualification"}:
            raise ValueError("family_in_both_splits")  # a family seen while tuning cannot judge the result
        self.cases = {c.id: c for c in cases}
        self.tuning = [c for c in cases if c.split == "tuning"]
        self.qualification = [c for c in cases if c.split == "qualification"]
        if not self.tuning or not self.qualification:
            raise ValueError("both_splits_required")
        self.solve, self.improve, self.check = solve, improve, check
        self.width, self.clock, self.on_event, self.stop, self.context = width, clock, on_event, stop, context
        self.result = LoopResult()
        self.errors = 0

    def _one(self, label: str, skill: str, case: Case, repeat: int) -> Rollout:
        if self.stop():
            raise LoopStopped()
        started = self.clock()
        try:
            output, error = self.solve(skill, case.prompt), False
            verdict = self.check(case, output)  # a model grader can fail too: same rule
        except LoopStopped:
            raise
        except Exception as exc:  # noqa: BLE001 - an engine failure is an unknown, never a fake wrong answer
            output, error = f"<engine error: {type(exc).__name__}>", True
            verdict = {"pass": False, "score": 0.0, "feedback": "engine error"}
        row = Rollout(label, case.id, repeat, output, bool(verdict["pass"]), float(verdict["score"]),
                      str(verdict.get("feedback", "")), self.clock() - started)
        row.error = error
        return row

    def _run_jobs(self, jobs: list) -> list:
        with ThreadPoolExecutor(max_workers=max(1, self.width)) as pool:
            rows = list(pool.map(lambda job: self._one(*job), jobs))
        self.result.calls["solve"] += len(jobs)
        failed = sum(r.error for r in rows)
        self.errors += failed
        if failed > max(1, MAX_ERROR_SHARE * len(rows)):
            raise EngineUnavailable(f"{failed} of {len(rows)} engine calls failed")
        return rows

    def _roll(self, label: str, skill: str, cases: list, repeats: int = 1) -> list:
        rows = self._run_jobs([(label, skill, c, r) for c in cases for r in range(1, repeats + 1)])
        self.on_event("rolled", {"version": label, "rows": len(rows), "mean": _mean(rows)})
        return rows

    def _improve(self, instructions: str, fallback: str, label: str) -> str:
        for attempt in (1, 2):  # one retry, as upstream STAGE_ATTEMPTS
            if self.stop():
                raise LoopStopped()
            self.result.calls["improve"] += 1
            try:
                skill = extract_skill(self.improve(instructions))
                self.result.notes[label] = "kept_current" if _same(skill, fallback) else "changed"
                return skill
            except LoopStopped:
                raise
            except Exception as error:  # noqa: BLE001
                self.result.notes[label] = f"fell_back: {type(error).__name__}: {error}"[:200]
        return fallback

    def run(self, base_skill: str, *, k: int = 1, tuning_repeats: int = 1, qualification_repeats: int = 2,
            margin: float = 0.0, early_stop: bool = False) -> LoopResult:
        """`early_stop`: run the sealed pairs one repeat at a time and stop once the answer is clear: the candidate
        does not win more cases than it loses (it cannot be "helped"), or it wins EARLY_WINS cases with no loss and
        no regression. Every stop is still judged by the same report."""
        res = self.result
        res.versions["base"] = base_skill
        base_rows = self._roll("base", base_skill, self.tuning, tuning_repeats)
        res.tuning["base"] = _mean(base_rows)
        current, current_rows, history = base_skill, base_rows, []
        for t in range(1, k + 1):
            evidence = _evidence(self.cases, current_rows, "current")
            past = "\n".join(f"- {lbl}: tuning score {res.tuning[lbl]:.2f}, {res.notes.get(lbl, '')}" for lbl in history)
            pool = [("current", current, _mean(current_rows))]
            for angle in ("INV", "DOM"):
                label = f"{angle.lower()}{t}"
                text = self._improve(propose_instructions(angle, current, evidence, past, self.context), current, label)
                res.versions[label] = text
                rows = self._roll(label, text, self.tuning, tuning_repeats)
                res.tuning[label] = _mean(rows)
                pool.append((label, text, res.tuning[label]))
                history.append(label)
            label = f"c{t}"
            composed = self._improve(compose_instructions(current, pool, self.context), current, label)
            res.versions[label] = composed
            current_rows = self._roll(label, composed, self.tuning, tuning_repeats)
            res.tuning[label] = _mean(current_rows)
            current = composed
            history.append(label)
        # Javis rule: the baseline stays in the choice and wins ties; a text equal to the baseline is not a candidate
        # (an unchanged re-roll beating the baseline's roll is chance, not improvement).
        real = [lbl for lbl in res.tuning if lbl != "base" and not _same(res.versions[lbl], base_skill)]
        best = max(real, key=lambda lbl: (res.tuning[lbl], lbl.startswith("c")), default="base")
        res.chosen = best if best != "base" and res.tuning[best] > res.tuning["base"] + margin else "base"
        self.on_event("chosen", {"chosen": res.chosen, "tuning": res.tuning})
        if res.chosen == "base":
            res.report = {"verdict": "keep_base", "reason": "no_tuning_improvement", "engine_errors": self.errors}
            return res
        # Baseline and candidate run as interleaved pairs, so an outage or rate limit hits both arms alike.
        arms = (("base", base_skill), (res.chosen, res.versions[res.chosen]))
        if early_stop:
            rows = []
            for repeat in range(1, qualification_repeats + 1):
                rows += self._run_jobs([(label, text, c, repeat) for c in self.qualification for label, text in arms])
                if repeat == qualification_repeats:
                    break
                so_far = paired_report([r for r in rows if r.version == "base"], [r for r in rows if r.version != "base"])
                o = so_far["outcomes"]
                if o["loss"] >= o["win"] or (o["win"] >= EARLY_WINS and not o["loss"] and not so_far["regressions"]):
                    self.result.notes["qualification"] = f"early_stop_after_{repeat}"
                    break
            self.on_event("rolled", {"version": "qualification", "rows": len(rows), "mean": _mean(rows)})
            res.qualification = rows
            res.report = paired_report([r for r in rows if r.version == "base"], [r for r in rows if r.version != "base"])
            res.report["engine_errors"] = self.errors
            res.report["repeats"] = max(r.repeat for r in rows)
            return res
        jobs = [(label, text, c, r) for c in self.qualification for r in range(1, qualification_repeats + 1)
                for label, text in arms]
        rows = self._run_jobs(jobs)
        self.on_event("rolled", {"version": "qualification", "rows": len(rows), "mean": _mean(rows)})
        res.qualification = rows
        res.report = paired_report([r for r in rows if r.version == "base"], [r for r in rows if r.version != "base"])
        res.report["engine_errors"] = self.errors
        return res


def _mean(rows: list) -> float:
    rows = [r for r in rows if not getattr(r, "error", False)]  # engine failures are unknowns, not zeros
    return round(sum(r.score for r in rows) / len(rows), 4) if rows else 0.0


def paired_report(base_rows: list, cand_rows: list) -> dict:
    """Per qualification case: mean score over valid pairs (both arms answered), candidate vs baseline; sign test.
    A pair where either arm hit an engine error is dropped and counted, never scored as a wrong answer."""
    base = {(r.case_id, r.repeat): r for r in base_rows}
    cand = {(r.case_id, r.repeat): r for r in cand_rows}
    pairs, dropped = {}, 0
    for key in sorted(base):
        b, c = base[key], cand.get(key)
        if c is None or getattr(b, "error", False) or getattr(c, "error", False):
            dropped += 1
            continue
        pairs.setdefault(key[0], []).append((b, c))
    outcomes = {"win": 0, "tie": 0, "loss": 0}
    cases = []
    for case_id, items in sorted(pairs.items()):
        bs, cs = [b for b, _ in items], [c for _, c in items]
        b, c = _mean(bs), _mean(cs)
        outcome = "win" if c > b else "loss" if c < b else "tie"
        outcomes[outcome] += 1
        cases.append({"case": case_id, "base": b, "candidate": c, "outcome": outcome, "pairs": len(items),
                      "base_pass": sum(r.passed for r in bs), "candidate_pass": sum(r.passed for r in cs)})
    p = sign_test(outcomes["win"], outcomes["loss"])
    # Spec Q04: a higher total never excuses breaking work the baseline got fully right. A case the baseline passed
    # on every pair and the candidate failed on any is a regression; one is enough to refuse "helped". With a
    # nondeterministic engine this is deliberately conservative: a flaky miss blocks rather than slips through.
    regressions = [c["case"] for c in cases if c["base_pass"] == c["pairs"] and c["candidate_pass"] < c["base_pass"]]
    verdict = ("hurt" if outcomes["loss"] > outcomes["win"] and p < 0.05 else
               "regression" if regressions else
               "helped" if outcomes["win"] > outcomes["loss"] and p < 0.05 else "inconclusive")
    valid_b = [b for items in pairs.values() for b, _ in items]
    valid_c = [c for items in pairs.values() for _, c in items]
    return {"verdict": verdict, "outcomes": outcomes, "p_value": round(p, 4), "regressions": regressions,
            "dropped_pairs": dropped, "base_mean": _mean(valid_b), "candidate_mean": _mean(valid_c),
            "base_pass_rate": round(sum(r.passed for r in valid_b) / max(1, len(valid_b)), 4),
            "candidate_pass_rate": round(sum(r.passed for r in valid_c) / max(1, len(valid_c)), 4),
            "cases": cases}


def to_json(result: LoopResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
