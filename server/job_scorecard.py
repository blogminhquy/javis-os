"""Scorecard of background jobs: each job finds, by its own results, the lightest model that gets it done.

Owner, 10/11/2026: "it has to learn how to learn and adjust the background models itself, to get the job done
or to save tokens as the user intends; it cannot be fixed to a frame I think up". So nobody assigns a model to a
job any more. Three things replace the setting:

  intent     what the owner said they want, in three words: "save", "balanced", "sure". Said in chat (the
             `javis_tune` tool), for everything or for one job. No switch on any page.
  ladder     the provider's chat models from lightest to MAIN's model, ordered once by the main brain from the
             provider's own list (auto_background.py). Javis holds no table of model names.
  scorecard  every run of a job leaves one row: which model, did it get the job done, what it cost. A job that
             failed because of the model climbs one rung for its next run. A job that keeps succeeding tries one
             rung lower; if that try fails it goes back up and remembers the floor.

Each reminder, loop, Kanban route and kind of side work has its own rung. The rules that move it are plain code
(`step`): no model is asked before a job runs, so adjusting costs no tokens and no latency.

What stays fixed, on purpose:
  - a job never runs above MAIN's model, and never on a model the provider did not list;
  - only a failure that is the model's fault moves a rung (a spent quota, a sign-in, a dead connection do not);
  - a run is never repeated here: a job that already sent a message is not sent again, the rung changes for the
    NEXT run;
  - a job whose only signal is "it did not crash" is not lowered on its own, unless the owner asked to save;
  - every change is logged with its reason and can be undone (`undo`), and a model the owner picked by hand on
    the Models page switches all of this off.

Performance: reads come from memory; a finished run does one small SQLite write, off the event loop. Nothing here
runs during a chat turn.
"""
from __future__ import annotations

import asyncio
import contextvars
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from typing import Callable, Dict, List, Optional

from config import STATE_DIR

DB = STATE_DIR / "scorecard.sqlite3"

INTENTS = ("save", "balanced", "sure")
DEFAULT_INTENT = "balanced"
# Consecutive good runs before a job tries one rung lower. 0 = never tries.
PROBE_AFTER = {"save": 3, "balanced": 6, "sure": 0}
# How far the job's result can be trusted. "strong": the job checks its own work (a loop's verify run, a Kanban
# job's status, a learning batch whose JSON parsed). "weak": all we know is that it did not fail.
SIGNAL = {"loop": "strong", "kanban": "strong", "learn": "strong",
          "reminder": "weak", "workflow": "weak", "side": "weak"}
FLOOR_DAYS = 30          # a floor learned from a failed try is forgotten after this long: models and jobs change
KEEP_RUNS = 200          # rows kept per job
CAUSE_MODEL, CAUSE_OTHER = "model", "other"

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None
_jobs: Optional[Dict[str, dict]] = None      # job -> state, the copy every read uses
_meta: Dict[str, str] = {}
_active: contextvars.ContextVar = contextvars.ContextVar("javis_job_run", default=None)
# Called with a change dict when a job moved to another model (main.py turns it into a notice). Never raises.
on_change: Optional[Callable[[dict], None]] = None


# ---------------------------------------------------------------- the rules (pure)

def start_index(tier: str, n: int, intent: str, base: Optional[int] = None) -> int:
    """Where a job with no history starts on a ladder of n rungs (0 = lightest, n-1 = MAIN's model).

    `base`: the rung the main brain named as this tier's starting point when it ordered the ladder; without it,
    the bottom for light work and the middle for handed-over jobs. What the owner asked for moves it one rung."""
    if n <= 1:
        return 0
    if base is None:
        base = 0 if tier == "light" else n // 2
    if intent == "save" and tier != "light":
        base -= 1
    elif intent == "sure":
        base += 1
    return max(0, min(n - 1, base))


def step(state: dict, outcome: str, cause: str, n: int, intent: str, signal: str, now: float = None) -> dict:
    """One finished run -> the job's next state. `state` holds idx, floor, floor_at, streak, probing.

    Returns the new state; `moved` in it says why the rung changed ("" when it did not)."""
    now = time.time() if now is None else now
    s = {"idx": int(state.get("idx") or 0), "floor": int(state.get("floor") or 0),
         "floor_at": float(state.get("floor_at") or 0), "streak": int(state.get("streak") or 0),
         "probing": bool(state.get("probing")), "moved": ""}
    top = max(0, n - 1)
    s["idx"] = max(0, min(top, s["idx"]))
    if s["floor"] and now - s["floor_at"] > FLOOR_DAYS * 86400:
        s["floor"], s["floor_at"] = 0, 0.0
    if outcome == "fail":
        if cause != CAUSE_MODEL:
            return s                               # not the model's doing: nothing to learn about the rung
        s["streak"] = 0
        if s["probing"]:
            s["probing"] = False
            if s["idx"] < top:
                s["idx"] += 1
                s["floor"], s["floor_at"] = s["idx"], now
                s["moved"] = "probe_failed"
        elif s["idx"] < top:
            s["idx"] += 1
            s["moved"] = "failed"
        return s
    if outcome != "ok":
        return s
    s["streak"] += 1
    if s["probing"]:
        s["probing"] = False                       # the lower rung did the job: it stays
        return s
    need = PROBE_AFTER.get(intent, PROBE_AFTER[DEFAULT_INTENT])
    if need and s["streak"] >= need and s["idx"] > s["floor"] and s["idx"] > 0 \
            and (signal == "strong" or intent == "save"):
        s["idx"] -= 1
        s["probing"] = True
        s["streak"] = 0
        s["moved"] = "probe"
    return s


# ---------------------------------------------------------------- store

def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(str(DB), check_same_thread=False, timeout=10)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.executescript("""
            CREATE TABLE IF NOT EXISTS jobs(job TEXT PRIMARY KEY, kind TEXT, label TEXT, provider TEXT, model TEXT,
                floor_model TEXT, floor_at REAL, streak INTEGER, probing INTEGER, intent TEXT, runs INTEGER,
                fails INTEGER, tokens INTEGER, updated REAL);
            CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, job TEXT, provider TEXT,
                model TEXT, outcome TEXT, cause TEXT, note TEXT, tokens INTEGER, probe INTEGER);
            CREATE INDEX IF NOT EXISTS runs_job ON runs(job, id);
            CREATE TABLE IF NOT EXISTS changes(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, job TEXT, label TEXT,
                provider TEXT, from_model TEXT, to_model TEXT, why TEXT, note TEXT, reverted REAL);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
        """)
        c.commit()
        _conn = c
    return _conn


def _load() -> Dict[str, dict]:
    global _jobs
    with _lock:
        if _jobs is None:
            jobs = {}
            try:
                c = _db()
                cols = ("job", "kind", "label", "provider", "model", "floor_model", "floor_at", "streak", "probing",
                        "intent", "runs", "fails", "tokens", "updated")
                for row in c.execute("SELECT " + ", ".join(cols) + " FROM jobs"):
                    jobs[row[0]] = dict(zip(cols, row))
                for k, v in c.execute("SELECT key, value FROM meta"):
                    _meta[k] = v
            except Exception as e:   # noqa: BLE001 - a broken scorecard must never stop a job
                print(f"[scorecard] load: {type(e).__name__}: {e}", file=sys.stderr)
            _jobs = jobs
        return _jobs


def _persist(fn) -> None:
    """Run a write off the event loop when there is one; at once otherwise (tests, worker threads)."""
    def safe():
        try:
            with _lock:
                fn(_db())
                _db().commit()
        except Exception as e:   # noqa: BLE001
            print(f"[scorecard] write: {type(e).__name__}: {e}", file=sys.stderr)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        safe()
        return
    loop.run_in_executor(None, safe)


def reset_for_tests() -> None:
    global _conn, _jobs
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:   # noqa: BLE001
                pass
        _conn, _jobs = None, None
        _meta.clear()


# ---------------------------------------------------------------- intent

def intent(job: str = "") -> str:
    """What the owner wants for this job: its own intent when one was given, else the general one."""
    jobs = _load()
    own = (jobs.get(job) or {}).get("intent") if job else ""
    v = own or _meta.get("intent") or DEFAULT_INTENT
    return v if v in INTENTS else DEFAULT_INTENT


def set_intent(level: str, job: str = "") -> bool:
    """Record what the owner asked for. An empty level on a job hands it back to the general intent."""
    level = str(level or "").strip().lower()
    if level and level not in INTENTS:
        return False
    jobs = _load()
    with _lock:
        if job:
            st = jobs.setdefault(job, _blank(job, "", ""))
            st["intent"] = level
            st["streak"], st["probing"] = 0, 0
            if level:
                # A new wish starts the job over from where that wish puts it; the old rung was found under another one.
                st["model"], st["floor_model"], st["floor_at"] = "", "", 0.0
            row = dict(st)
            _persist(lambda c: _save_job(c, row))
        else:
            if not level:
                return False
            _meta["intent"] = level
            _persist(lambda c: c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('intent', ?)", (level,)))
    return True


def _blank(job: str, kind: str, label: str) -> dict:
    return {"job": job, "kind": kind, "label": label, "provider": "", "model": "", "floor_model": "",
            "floor_at": 0.0, "streak": 0, "probing": 0, "intent": "", "runs": 0, "fails": 0, "tokens": 0,
            "updated": 0.0}


def _save_job(c, st: dict) -> None:
    c.execute("INSERT OR REPLACE INTO jobs(job, kind, label, provider, model, floor_model, floor_at, streak, probing, "
              "intent, runs, fails, tokens, updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (st["job"], st.get("kind") or "", st.get("label") or "", st.get("provider") or "", st.get("model") or "",
               st.get("floor_model") or "", float(st.get("floor_at") or 0), int(st.get("streak") or 0),
               int(bool(st.get("probing"))), st.get("intent") or "", int(st.get("runs") or 0),
               int(st.get("fails") or 0), int(st.get("tokens") or 0), float(st.get("updated") or 0)))


# ---------------------------------------------------------------- one run

class Run:
    """One run of one job. Built by `run()`; the engine layer and the job's runner fill it in."""

    def __init__(self, job: str, kind: str, label: str = ""):
        self.job, self.kind, self.label = str(job), str(kind or "side"), str(label or "")[:120]
        self.provider = ""
        self.ladder: List[str] = []
        self.model: Optional[str] = None       # the model this run was sent to (None = the scorecard was not asked)
        self.answered: Optional[str] = None    # the model that really answered, when a fallback chain ran
        self.link_cause = ""                   # why the chosen model did not answer, when another one did
        self.outcome, self.cause, self.note = "", "", ""
        self.tokens = 0
        self.probe = False

    # -- called by aux_engine.read_spec
    def choose(self, provider: str, ladder, tier: str, main_model: str, start_model: str = "") -> str:
        """The model this job runs now. `ladder`: lightest first; MAIN's model is added on top when missing.
        Asked more than once in one run (a verify pass, a second fork), it keeps answering the same model."""
        if self.model is not None and self.provider == str(provider or ""):
            return self.model
        rungs = [m for m in (ladder or []) if m]
        main_model = str(main_model or "")
        if main_model not in rungs:
            rungs.append(main_model)
        self.provider, self.ladder = str(provider or ""), rungs
        st = _load().get(self.job) or {}
        cur = st.get("model") if st.get("provider") == self.provider else None
        if cur in rungs and (cur or main_model == "") and st.get("runs"):
            idx = rungs.index(cur)
        else:
            base = rungs.index(start_model) if start_model in rungs else None
            idx = start_index(tier, len(rungs), intent(self.job), base)
        self.model = rungs[idx]
        self.probe = bool(st.get("probing")) and cur == self.model
        return self.model

    # -- called by aux_engine._FallbackChain
    def link_answered(self, model) -> None:
        self.answered = str(model or "")

    def link_failed(self, model, quota: bool) -> None:
        if self.model is not None and str(model or "") == self.model and not self.link_cause:
            self.link_cause = CAUSE_OTHER if quota else CAUSE_MODEL

    def add_tokens(self, n) -> None:
        try:
            self.tokens += max(0, int(n or 0))
        except (TypeError, ValueError):
            pass

    # -- called by the job's runner
    def ok(self, note: str = "") -> None:
        self.outcome, self.cause, self.note = "ok", "", str(note or "")[:200]

    def fail(self, cause: str = CAUSE_MODEL, note: str = "") -> None:
        self.outcome = "fail"
        self.cause = cause if cause in (CAUSE_MODEL, CAUSE_OTHER) else CAUSE_OTHER
        self.note = str(note or "")[:200]


@contextmanager
def run(job: str, kind: str = "side", label: str = "", settle: bool = True):
    """`with job_scorecard.run("reminder:abc", "reminder", "Báo cáo 7h") as r:` around building the engine and
    running it. The runner calls r.ok() or r.fail(cause); no verdict leaves the rung untouched.

    settle=False: the verdict comes after the block (a Kanban job is checked by a separate engine, which must
    not run inside the job's own block); the runner then calls `settle(r)` itself."""
    r = Run(job, kind, label)
    token = _active.set(r)
    try:
        yield r
    finally:
        _active.reset(token)
        if settle:
            globals()["settle"](r)


def settle(r: "Run") -> None:
    """Close one run: apply the rules to its verdict. Safe to call once per run; never raises."""
    if r is None or getattr(r, "_settled", False):
        return
    r._settled = True
    try:
        _settle(r)
    except Exception as e:   # noqa: BLE001 - never let bookkeeping break the job
        print(f"[scorecard] settle {r.job}: {type(e).__name__}: {e}", file=sys.stderr)


def active() -> Optional[Run]:
    return _active.get()


def _settle(r: Run) -> None:
    if r.model is None or not r.ladder:
        return                                    # background model picked by hand, or the engine was never built
    outcome, cause = r.outcome, r.cause
    if r.answered is not None and r.answered != r.model:
        # Another link of the chain did the job: the chosen model did not, whatever the job's own verdict says.
        outcome, cause = "fail", (r.link_cause or CAUSE_MODEL)
    if outcome not in ("ok", "fail"):
        return
    jobs = _load()
    now = time.time()
    with _lock:
        st = jobs.setdefault(r.job, _blank(r.job, r.kind, r.label))
        st["kind"], st["label"] = r.kind, (r.label or st.get("label") or "")
        n = len(r.ladder)
        idx = r.ladder.index(r.model)
        floor = r.ladder.index(st["floor_model"]) if st.get("floor_model") in r.ladder \
            and st.get("provider") == r.provider else 0
        new = step({"idx": idx, "floor": floor, "floor_at": st.get("floor_at"), "streak": st.get("streak"),
                    "probing": st.get("probing")}, outcome, cause, n, intent(r.job),
                   SIGNAL.get(r.kind, "weak"), now)
        before = r.model
        st.update({"provider": r.provider, "model": r.ladder[new["idx"]],
                   "floor_model": r.ladder[new["floor"]] if new["floor"] else "", "floor_at": new["floor_at"],
                   "streak": new["streak"], "probing": int(new["probing"]), "updated": now,
                   "runs": int(st.get("runs") or 0) + 1,
                   "fails": int(st.get("fails") or 0) + (1 if outcome == "fail" and cause == CAUSE_MODEL else 0),
                   "tokens": int(st.get("tokens") or 0) + r.tokens})
        row = dict(st)
        run_row = (now, r.job, r.provider, r.model, outcome, cause, r.note, r.tokens, int(r.probe))
        change = None
        if new["moved"] and st["model"] != before:
            change = {"ts": now, "job": r.job, "label": st["label"], "kind": r.kind, "provider": r.provider,
                      "from_model": before, "to_model": st["model"], "why": new["moved"], "note": r.note}

    def write(c):
        _save_job(c, row)
        c.execute("INSERT INTO runs(ts, job, provider, model, outcome, cause, note, tokens, probe) "
                  "VALUES(?,?,?,?,?,?,?,?,?)", run_row)
        c.execute("DELETE FROM runs WHERE job = ? AND id <= (SELECT id FROM runs WHERE job = ? ORDER BY id DESC "
                  "LIMIT 1 OFFSET ?)", (r.job, r.job, KEEP_RUNS))
        if change:
            cur = c.execute("INSERT INTO changes(ts, job, label, provider, from_model, to_model, why, note) "
                            "VALUES(?,?,?,?,?,?,?,?)", (change["ts"], change["job"], change["label"],
                                                         change["provider"], change["from_model"],
                                                         change["to_model"], change["why"], change["note"]))
            change["id"] = cur.lastrowid
    _persist(write)
    if change and on_change:
        try:
            on_change(change)
        except Exception as e:   # noqa: BLE001
            print(f"[scorecard] on_change: {type(e).__name__}: {e}", file=sys.stderr)


# ---------------------------------------------------------------- the owner's side (javis_tune)

def feedback(job: str, good: bool, note: str = "") -> bool:
    """The owner said a job's result was wrong (or right). A complaint counts as a failure of the model that ran
    it last, so the next run climbs one rung; praise only adds to the good streak."""
    jobs = _load()
    st = jobs.get(job)
    if not st or not st.get("model"):
        return False
    r = Run(job, st.get("kind") or "side", st.get("label") or "")
    r.provider = st.get("provider") or ""
    r.model = st["model"]
    # The ladder is not at hand here; two rungs are enough to say "one up" and the next real run re-reads it.
    r.ladder = _meta_ladder(r.provider, st["model"])
    if good:
        r.ok(note or "owner")
    else:
        r.fail(CAUSE_MODEL, note or "owner")
    _settle(r)
    return True


def _meta_ladder(provider: str, model: str) -> List[str]:
    ladder = _LADDERS.get(provider) or []
    return ladder if model in ladder else [model]


_LADDERS: Dict[str, List[str]] = {}


def remember_ladder(provider: str, ladder) -> None:
    """The last ladder seen for a provider (aux_engine passes it), so feedback and undo can move a rung
    without a run."""
    _LADDERS[str(provider or "")] = [m for m in (ladder or [])]


def status(limit: int = 30) -> dict:
    """What `javis_tune op=status` shows: the general intent, each job's model with its record, recent changes."""
    jobs = _load()
    with _lock:
        rows = sorted(jobs.values(), key=lambda s: -(s.get("updated") or 0))[:limit]
        out = [{"job": s["job"], "label": s.get("label") or "", "kind": s.get("kind") or "",
                "model": s.get("model") or "", "provider": s.get("provider") or "",
                "intent": s.get("intent") or "", "runs": s.get("runs") or 0, "fails": s.get("fails") or 0,
                "tokens": s.get("tokens") or 0, "trying_lower": bool(s.get("probing"))} for s in rows]
    changes = []
    try:
        with _lock:
            for row in _db().execute("SELECT id, ts, job, label, from_model, to_model, why, reverted FROM changes "
                                     "ORDER BY id DESC LIMIT 10"):
                changes.append(dict(zip(("id", "ts", "job", "label", "from_model", "to_model", "why", "reverted"), row)))
    except Exception:   # noqa: BLE001
        pass
    return {"intent": intent(), "jobs": out, "changes": changes}


def undo(change_id: int) -> Optional[dict]:
    """Put a job back on the model it had before one change. The job then holds that model as its floor, so the
    scorecard does not make the same move again for FLOOR_DAYS."""
    try:
        with _lock:
            row = _db().execute("SELECT id, job, provider, from_model, to_model, reverted FROM changes WHERE id = ?",
                                (int(change_id),)).fetchone()
    except Exception:   # noqa: BLE001
        return None
    if not row or row[5]:
        return None
    _, job, provider, from_model, to_model, _ = row
    jobs = _load()
    now = time.time()
    with _lock:
        st = jobs.get(job)
        if not st:
            return None
        st.update({"model": from_model, "provider": provider, "streak": 0, "probing": 0, "updated": now})
        ladder = _LADDERS.get(provider) or []
        if from_model in ladder and to_model in ladder and ladder.index(to_model) < ladder.index(from_model):
            st["floor_model"], st["floor_at"] = from_model, now      # undoing a move down: do not try it again soon
        saved = dict(st)

    def write(c):
        _save_job(c, saved)
        c.execute("UPDATE changes SET reverted = ? WHERE id = ?", (now, int(change_id)))
    _persist(write)
    return {"job": job, "label": saved.get("label") or "", "model": from_model}


def find(query: str) -> List[dict]:
    """Jobs whose key or label holds the words the owner used ("báo cáo sáng", "reminder:abc")."""
    q = " ".join(str(query or "").lower().split())
    if not q:
        return []
    out = []
    for s in _load().values():
        hay = (s["job"] + " " + (s.get("label") or "")).lower()
        if q in hay or all(w in hay for w in q.split()):
            out.append({"job": s["job"], "label": s.get("label") or "", "model": s.get("model") or ""})
    return out[:8]
