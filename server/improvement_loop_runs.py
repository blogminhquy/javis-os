"""Owner-started self-learning runs for one user skill (product side of server/improvement_loop.py).

The owner keeps examples with known answers next to the skill (`skills/<slug>/examples.json`, a list of
`{"prompt": ..., "expected": ..., "family"?: ...}`); Javis can write that file from chat. The host splits them
deterministically into tuning and sealed qualification cases, runs the loop with the brain's selected engine in
text-only mode (no tools, no MCP, no files), and stores the report. Nothing changes until the owner presses Apply,
which writes the chosen text to the owner's own skill file only if the file is still the exact bytes the run
started from, after keeping a backup next to it. System and pack skills are refused.

Runs are files under `<state>/improvement/loops/<brain-key>/`, one at a time per brain. Zero setup: no key,
package or setting beyond the engine the user already selected.
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

MAX_EXAMPLES = 60
MIN_TUNING, MIN_QUALIFICATION = 3, 4
MAX_PROMPT_CHARS = 6000
_RUN = re.compile(r"ilr_[0-9a-f]{24}")


def _norm(value):
    if isinstance(value, dict):
        return {str(k): _norm(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        items = [_norm(v) for v in value]
        try:
            return sorted(items, key=lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True))
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
    if isinstance(expected, (dict, list)):
        try:
            got = parse_json_output(output)
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


def load_cases(root: Path, slug: str) -> list:
    path = Path(root) / "skills" / slug / "examples.json"
    if not path.is_file():
        raise FileNotFoundError("examples_missing")
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
    # Deterministic split by family hash: about one third tuning, the rest sealed for the verdict.
    ordered = sorted(cases, key=lambda c: hashlib.sha256(c[0].encode("utf-8")).hexdigest())
    n_tuning = max(MIN_TUNING, len(ordered) // 3)
    if len(ordered) - n_tuning < MIN_QUALIFICATION:
        raise ValueError("examples_count")
    return [L.Case(f"{'t' if i < n_tuning else 'q'}{i + 1:02d}", family, "tuning" if i < n_tuning else "qualification",
                   prompt, expected) for i, (family, prompt, expected) in enumerate(ordered)]


class LoopRuns:
    def __init__(self, state_dir: Path, *, engines: Callable, protected: Callable[[str, str], bool],
                 clock: Callable[[], float] = time.time, spawn: Callable = None):
        """`engines(brain)` -> (solve, improve) for the brain's selected engine in text-only mode.
        `protected(brain, slug)` -> True for system/pack skills. `spawn(fn)` runs fn in the background."""
        self.root, self.engines, self.protected, self.clock = Path(state_dir), engines, protected, clock
        self.spawn = spawn or (lambda fn: threading.Thread(target=fn, daemon=True, name="javis-improvement-loop").start())
        self._lock = threading.Lock()

    def _dir(self, brain: str) -> Path:
        path = self.root / "improvement" / "loops" / hashlib.sha256(brain.encode("utf-8")).hexdigest()[:24]
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _save(self, brain, run):
        target = self._dir(brain) / f"{run['run_id']}.json"
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
        temp.replace(target)

    def get(self, brain: str, run_id: str) -> dict:
        if type(run_id) is not str or not _RUN.fullmatch(run_id):
            raise ValueError("invalid_loop_run")
        path = self._dir(brain) / f"{run_id}.json"
        if not path.is_file():
            raise PermissionError("loop_run_unavailable")
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self, brain: str, slug: str) -> list:
        runs = [json.loads(p.read_text(encoding="utf-8")) for p in self._dir(brain).glob("ilr_*.json")]
        return sorted([r for r in runs if r.get("slug") == slug], key=lambda r: r["created_at"], reverse=True)[:10]

    def status(self, brain: str, slug: str) -> dict:
        import skill_router as SR
        try:
            cases = load_cases(Path(brain), slug)
            examples = {"ok": True, "tuning": sum(c.split == "tuning" for c in cases),
                        "qualification": sum(c.split == "qualification" for c in cases)}
        except (OSError, ValueError) as error:
            examples = {"ok": False, "reason": str(error)}
        return {"examples": examples, "protected": bool(self.protected(brain, slug)),
                "exists": SR.read_skill_asset(Path(brain), slug) is not None, "runs": self.list(brain, slug)}

    def start(self, brain: str, slug: str, *, k: int = 1) -> dict:
        import skill_router as SR
        if type(slug) is not str or not SR.valid_file_slug(slug):
            raise ValueError("invalid_skill")
        if self.protected(brain, slug):
            raise PermissionError("skill_protected")
        canonical = SR.read_skill_asset(Path(brain), slug)
        if canonical is None:
            raise PermissionError("skill_unavailable")
        cases = load_cases(Path(brain), slug)
        with self._lock:
            if any(r.get("state") == "running" for r in
                   (json.loads(p.read_text(encoding="utf-8")) for p in self._dir(brain).glob("ilr_*.json"))):
                raise PermissionError("loop_run_busy")
            run = {"run_id": "ilr_" + secrets.token_hex(12), "slug": slug, "state": "running", "k": int(k),
                   "base_hash": canonical.content_hash, "created_at": self.clock(), "progress": [], "result": None,
                   "error": ""}
            self._save(brain, run)
        solve, improve = self.engines(brain)
        text = canonical.content.decode("utf-8")

        def work():
            def on_event(kind, data):
                run["progress"].append({"kind": kind, **{k: v for k, v in data.items() if k != "tuning"}})
                self._save(brain, run)
            try:
                result = L.Loop(cases, solve=solve, improve=improve, check=check, width=3, on_event=on_event).run(
                    text, k=run["k"], qualification_repeats=2)
                run["result"] = {**result.to_dict(), "chosen_text": result.versions.get(result.chosen, text)}
                run["state"] = "done"
            except Exception as error:  # noqa: BLE001 - a failed run is reported, nothing is applied
                run["state"], run["error"] = "failed", f"{type(error).__name__}: {error}"[:300]
            run["finished_at"] = self.clock()
            self._save(brain, run)
        self.spawn(work)
        return {k: run[k] for k in ("run_id", "slug", "state", "created_at")}

    def apply(self, brain: str, run_id: str) -> dict:
        """The owner applies the chosen text to their own skill: only if the file is unchanged since the run."""
        import skill_router as SR
        run = self.get(brain, run_id)
        result = run.get("result") or {}
        if run.get("state") != "done" or result.get("chosen") in (None, "base"):
            raise PermissionError("loop_run_nothing_to_apply")
        if (result.get("report") or {}).get("verdict") == "hurt":
            raise PermissionError("loop_run_hurt")
        if self.protected(brain, run["slug"]):
            raise PermissionError("skill_protected")
        canonical = SR.read_skill_asset(Path(brain), run["slug"])
        if canonical is None or canonical.content_hash != run["base_hash"]:
            raise PermissionError("loop_run_skill_changed")
        path = Path(brain) / canonical.relative_path
        backup = path.with_name(f"SKILL.md.bak-{int(self.clock())}")
        backup.write_bytes(canonical.content)
        temp = path.with_suffix(".tmp")
        temp.write_bytes((result["chosen_text"].rstrip() + "\n").encode("utf-8"))  # LF, never CRLF on Windows
        temp.replace(path)
        run["applied_at"], run["backup"] = self.clock(), backup.name
        self._save(brain, run)
        return {"run_id": run_id, "applied": True, "backup": backup.name}
