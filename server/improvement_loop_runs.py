"""Owner-started self-learning runs for one user skill (product side of server/improvement_loop.py).

The owner keeps examples with known answers next to the skill (`skills/<slug>/examples.json`, a list of
`{"prompt": ..., "expected": ..., "family"?: ...}`); Javis can write that file from chat. The host splits them
deterministically into tuning and sealed qualification cases (at least 10 sealed, so a verdict is possible), runs
the loop with the brain's selected engine in text-only mode (no tools, no MCP, no files) on the skill BODY only,
and stores the report. The frontmatter (name, description, group...) is never handed to the improver.

Nothing changes until the owner presses Apply, which is offered only for a "helped" verdict on a sealed set not
used before, and writes the original frontmatter plus the chosen body only if the skill file is still the exact
bytes the run started from, after keeping a backup under the state folder. System and pack skills are refused.

Runs are files under `<state>/improvement/loops/<brain-key>/`, one at a time per brain, each with the server boot
id and a heartbeat: a run left "running" by a restart or a hung engine is marked interrupted, and the owner can
cancel. Zero setup: no key, package or setting beyond the engine the user already selected.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Callable

import improvement_loop as L
from improvement_store import ConflictError

MAX_EXAMPLES = 40
MAX_EXAMPLES_BYTES = 1_000_000
MIN_TUNING, MIN_QUALIFICATION = 3, 10
MAX_PROMPT_CHARS = 6000
STALE_AFTER_S = 900  # no progress for 15 minutes: the run is not coming back
_RUN = re.compile(r"ilr_[0-9a-f]{24}")
BOOT_ID = secrets.token_hex(8)  # one per server process


def _norm(value):
    if isinstance(value, bool):
        return ("bool", value)  # True must not equal 1
    if isinstance(value, dict):
        return {str(k): _norm(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        items = [_norm(v) for v in value]
        try:
            return sorted(items, key=lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True, default=str))
        except TypeError:
            return items
    if isinstance(value, str):
        return value.strip()
    return value


def parse_json_output(text: str):
    text = text.strip()
    if "```" in text:
        text = text.split("```")[1]
        text = text[4:] if text.startswith("json") else text
    first = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if first < 0:
        raise ValueError("no_json")
    last = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[first:last + 1])


def check(case, output: str) -> dict:
    """Structured answers compare field by field (lists as sets); plain text answers compare after trimming."""
    expected = case.answer
    if isinstance(expected, (dict, list)) or expected is None:
        try:
            got = parse_json_output(output) if expected is not None else json.loads(output.strip() or "null")
        except Exception:  # noqa: BLE001
            return {"pass": False, "score": 0.0, "feedback": "the answer must be JSON in the skill's format"}
        if isinstance(expected, dict) and isinstance(got, dict):
            keys = sorted(expected)
            right = [k for k in keys if _norm(got.get(k)) == _norm(expected[k])]
            wrong = [f"{k}: expected {json.dumps(expected[k], ensure_ascii=False)}, got "
                     f"{json.dumps(got.get(k), ensure_ascii=False)}" for k in keys if k not in right]
            return {"pass": not wrong, "score": len(right) / max(1, len(keys)),
                    "feedback": "all fields correct" if not wrong else "; ".join(wrong)[:1500]}
        ok = _norm(got) == _norm(expected)
        return {"pass": ok, "score": 1.0 if ok else 0.0, "feedback": "correct" if ok else "different answer"}
    ok = output.strip().casefold() == str(expected).strip().casefold()
    return {"pass": ok, "score": 1.0 if ok else 0.0, "feedback": "correct" if ok else f"expected {expected}"}


def split_frontmatter(text: str) -> tuple:
    """(frontmatter block incl. fences, body). The improver only ever sees the body. CRLF and a BOM are normalised
    first, so a file saved on Windows splits too (Apply writes LF)."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end > 0:
            return text[:end + 5], text[end + 5:]
    return "", text


def load_cases(root: Path, slug: str, consumed: frozenset = frozenset()) -> list:
    """`consumed`: sealed families that already judged a candidate of this skill. They join the tuning side (their
    answers are no secret any more) and the sealed side is built only from fresh families."""
    path = Path(root) / "skills" / slug / "examples.json"
    if not path.is_file():
        raise ValueError("examples_missing")
    if path.stat().st_size > MAX_EXAMPLES_BYTES:
        raise ValueError("examples_too_large")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if type(raw) is not list or not MIN_TUNING + MIN_QUALIFICATION <= len(raw) <= MAX_EXAMPLES:
        raise ValueError("examples_count")
    cases, families = [], set()
    for index, item in enumerate(raw):
        if (type(item) is not dict or type(item.get("prompt")) is not str or "expected" not in item
                or not 1 <= len(item["prompt"]) <= MAX_PROMPT_CHARS):
            raise ValueError("examples_shape")
        family = str(item.get("family") or f"example-{index + 1}")
        if family in families:
            raise ValueError("examples_family_repeated")
        families.add(family)
        cases.append((family, item["prompt"], item["expected"]))
    # Deterministic split by family hash: about a quarter tuning (at least 3), the rest sealed (at least 10).
    used = sorted((c for c in cases if c[0] in consumed), key=lambda c: c[0])
    fresh = sorted((c for c in cases if c[0] not in consumed), key=lambda c: hashlib.sha256(c[0].encode("utf-8")).hexdigest())
    n_tuning = max(MIN_TUNING - len(used), len(cases) // 4 - len(used), 0)
    if len(fresh) - n_tuning < MIN_QUALIFICATION:
        raise ValueError("examples_need_fresh_sealed" if used else "examples_count")
    tuning, sealed = used + fresh[:n_tuning], fresh[n_tuning:]
    return ([L.Case(f"t{i + 1:02d}", f, "tuning", p, e) for i, (f, p, e) in enumerate(tuning)]
            + [L.Case(f"q{i + 1:02d}", f, "qualification", p, e) for i, (f, p, e) in enumerate(sealed)])


def consumed_families(runs: list, slug: str) -> frozenset:
    """Sealed families of earlier runs of this skill that judged a real candidate."""
    return frozenset(f for r in runs if r.get("slug") == slug and r.get("state") == "done"
                     and (r.get("result") or {}).get("chosen") not in (None, "base") for f in r.get("sealed_families", []))


def sealed_hash(cases: list) -> str:
    return hashlib.sha256(json.dumps(sorted((c.family, c.prompt) for c in cases if c.split == "qualification"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def estimate_calls(cases: list, k: int = 1) -> int:
    n_t = sum(c.split == "tuning" for c in cases)
    n_q = len(cases) - n_t
    return n_t * (1 + 3 * k) + 3 * k * 1 + 4 * n_q  # tuning rolls, improver calls, 2 arms x 2 repeats sealed


class LoopRuns:
    def __init__(self, state_dir: Path, *, engines: Callable, protected: Callable[[str, str], bool],
                 clock: Callable[[], float] = time.time, spawn: Callable = None):
        """`engines(brain)` -> (solve, improve) for the brain's selected engine in text-only mode, raising when that
        engine cannot run text-only. `protected(brain, slug)` -> True for system/pack skills."""
        self.root, self.engines, self.protected, self.clock = Path(state_dir), engines, protected, clock
        self.spawn = spawn or (lambda fn: threading.Thread(target=fn, daemon=True, name="javis-improvement-loop").start())
        self._lock = threading.Lock()
        self._cancel: set = set()
        self._live: set = set()  # runs whose worker is alive in this process: never marked interrupted

    def _dir(self, brain: str) -> Path:
        path = self.root / "improvement" / "loops" / hashlib.sha256(brain.encode("utf-8")).hexdigest()[:24]
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _save(self, brain, run):
        target = self._dir(brain) / f"{run['run_id']}.json"
        temp = target.with_name(target.name + f".{threading.get_ident()}.tmp")
        temp.write_bytes(json.dumps(run, ensure_ascii=False, indent=1).encode("utf-8"))
        for attempt in range(20):  # Windows refuses replace while a poll holds the file open: retry briefly
            try:
                temp.replace(target)
                return
            except PermissionError:
                time.sleep(0.05)
        temp.replace(target)

    def _read(self, path: Path):
        for attempt in range(20):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except PermissionError:
                time.sleep(0.05)
            except (OSError, ValueError):
                return None  # half-written or vanished: skip it this time
        return None

    def _runs(self, brain: str) -> list:
        runs = []
        for path in self._dir(brain).glob("ilr_*.json"):
            run = self._read(path)
            if run is None:
                continue
            stale = (run.get("state") == "running" and run["run_id"] not in self._live
                     and (run.get("boot_id") != BOOT_ID or self.clock() - run.get("heartbeat_at", 0) > STALE_AFTER_S))
            if stale:  # a restart or a hung engine: never comes back, and must not block the next run
                run.update(state="failed", error="interrupted", finished_at=self.clock())
                self._save(brain, run)
            runs.append(run)
        return sorted(runs, key=lambda r: r["created_at"], reverse=True)

    def get(self, brain: str, run_id: str) -> dict:
        if type(run_id) is not str or not _RUN.fullmatch(run_id):
            raise ValueError("invalid_loop_run")
        for run in self._runs(brain):
            if run["run_id"] == run_id:
                return run
        raise PermissionError("loop_run_unavailable")

    def status(self, brain: str, slug: str) -> dict:
        import skill_router as SR
        if type(slug) is not str or not SR.valid_file_slug(slug):
            raise ValueError("invalid_skill")
        runs = [r for r in self._runs(brain) if r.get("slug") == slug]
        try:
            cases = load_cases(Path(brain), slug, consumed_families(runs, slug))
            examples = {"ok": True, "tuning": sum(c.split == "tuning" for c in cases),
                        "qualification": sum(c.split == "qualification" for c in cases),
                        "estimated_calls": estimate_calls(cases)}
        except (OSError, ValueError) as error:
            examples = {"ok": False, "reason": str(error)}
        runs = runs[:10]
        return {"examples": examples, "protected": bool(self.protected(brain, slug)),
                "exists": SR.read_skill_asset(Path(brain), slug) is not None, "runs": runs}

    def start(self, brain: str, slug: str, *, event_key: str, k: int = 1) -> dict:
        import skill_router as SR
        if type(slug) is not str or not SR.valid_file_slug(slug):
            raise ValueError("invalid_skill")
        if self.protected(brain, slug):
            raise PermissionError("skill_protected")
        canonical = SR.read_skill_asset(Path(brain), slug)
        if canonical is None:
            raise PermissionError("skill_unavailable")
        try:
            frontmatter, body = split_frontmatter(canonical.content.decode("utf-8"))
        except UnicodeDecodeError:
            raise ValueError("skill_not_utf8") from None
        solve, improve = self.engines(brain)  # raises when the selected engine cannot run text-only
        with self._lock:
            runs = self._runs(brain)
            for run in runs:
                if run.get("event_key") == event_key:
                    return {k: run[k] for k in ("run_id", "slug", "state", "created_at")}  # an exact retry
            if any(r.get("state") == "running" for r in runs):
                raise ConflictError("loop_run_busy")
            cases = load_cases(Path(brain), slug, consumed_families(runs, slug))
            seal = sealed_hash(cases)
            reused = any(r.get("sealed_hash") == seal and r.get("state") == "done"
                         and (r.get("result") or {}).get("chosen") not in (None, "base") for r in runs if r.get("slug") == slug)
            run = {"run_id": "ilr_" + secrets.token_hex(12), "slug": slug, "state": "running", "k": int(k),
                   "event_key": event_key, "base_hash": canonical.content_hash, "sealed_hash": seal,
                   "sealed_reused": reused, "sealed_families": sorted(c.family for c in cases if c.split == "qualification"),
                   "boot_id": BOOT_ID, "created_at": self.clock(), "heartbeat_at": self.clock(),
                   "estimated_calls": estimate_calls(cases, k), "progress": [], "result": None, "error": ""}
            self._live.add(run["run_id"])
            self._save(brain, run)

        def work():
            def on_event(kind, data):
                run["progress"].append({"kind": kind, **{k: v for k, v in data.items() if k != "tuning"}})
                run["heartbeat_at"] = self.clock()
                try:
                    self._save(brain, run)
                except OSError:
                    pass  # progress is a convenience; the run goes on and saves its result at the end
            try:
                result = L.Loop(cases, solve=solve, improve=improve, check=check, width=3, on_event=on_event,
                                stop=lambda: run["run_id"] in self._cancel).run(body, k=run["k"], qualification_repeats=2)
                report = dict(result.report)
                if run["sealed_reused"] and report.get("verdict") == "helped":
                    # The same sealed cases already judged an earlier candidate: a repeat cannot prove anything.
                    report.update(verdict="inconclusive", reason="sealed_set_reused")
                run["result"] = {**result.to_dict(), "report": report,
                                 "chosen_text": frontmatter + result.versions.get(result.chosen, body)}
                run["state"] = "done"
            except L.LoopStopped:
                run["state"], run["error"] = "cancelled", "owner_cancel"
            except L.EngineUnavailable as error:
                run["state"], run["error"] = "failed", f"engine_unavailable: {error}"[:300]
            except Exception as error:  # noqa: BLE001 - a failed run is reported, nothing is applied
                run["state"], run["error"] = "failed", f"{type(error).__name__}: {error}"[:300]
            run["finished_at"] = self.clock()
            self._cancel.discard(run["run_id"])
            self._live.discard(run["run_id"])
            try:
                self._save(brain, run)
            except OSError:
                pass  # the heartbeat lapses and the next read marks it interrupted
        self.spawn(work)
        return {k: run[k] for k in ("run_id", "slug", "state", "created_at")}

    def cancel(self, brain: str, run_id: str) -> dict:
        run = self.get(brain, run_id)
        if run.get("state") != "running":
            raise ConflictError("loop_run_not_running")
        self._cancel.add(run_id)
        run["cancel_requested"] = True
        self._save(brain, run)
        return {"run_id": run_id, "cancelling": True}

    def apply(self, brain: str, run_id: str) -> dict:
        """The owner applies the chosen text to their own skill: only a helped verdict, only over unchanged bytes."""
        import skill_router as SR
        with self._lock:
            run = self.get(brain, run_id)
            result = run.get("result") or {}
            if run.get("state") != "done" or result.get("chosen") in (None, "base") or run.get("applied_at"):
                raise PermissionError("loop_run_nothing_to_apply")
            verdict = (result.get("report") or {}).get("verdict")
            if verdict != "helped":
                # Spec: inconclusive, hurt or a regression keeps the current skill.
                raise PermissionError(f"loop_run_{verdict or 'unknown'}")
            if self.protected(brain, run["slug"]):
                raise PermissionError("skill_protected")
            canonical = SR.read_skill_asset(Path(brain), run["slug"])
            if canonical is None or canonical.content_hash != run["base_hash"]:
                raise ConflictError("loop_run_skill_changed")
            backups = self._dir(brain) / "backups"
            backups.mkdir(exist_ok=True)
            backup = backups / f"{run['slug']}-{run_id}.md"
            backup.write_bytes(canonical.content)
            path = Path(brain) / canonical.relative_path
            temp = path.with_name(path.name + f".{run_id}.tmp")
            temp.write_bytes((result["chosen_text"].rstrip() + "\n").encode("utf-8"))  # LF, never CRLF on Windows
            again = SR.read_skill_asset(Path(brain), run["slug"])
            if again is None or again.content_hash != run["base_hash"]:
                temp.unlink(missing_ok=True)
                raise ConflictError("loop_run_skill_changed")
            temp.replace(path)
            run["applied_at"], run["backup"] = self.clock(), str(backup)
            self._save(brain, run)
            return {"run_id": run_id, "applied": True, "backup": backup.name}
