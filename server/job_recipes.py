"""Recipes: a recurring job stops rediscovering every morning what it already knows how to read.

A reminder such as "7 am: yesterday's sales" runs the same chain every day: search for the tool,
read how to call it, call it, call the next one. Only the dates change. This module watches the
READ calls of a recurring job, and once it has seen the same chain on different days it runs that
chain itself before the model starts and hands the model the results. The model then goes straight
to judging and writing; everything that acts (send, post, order) is still decided by the model, in
that run, every time.

What makes it safe to do unattended:

  Evidence, not guessing. A recipe is used only after two runs on different days produced the same
  chain. Each date in an argument keeps the set of ALL explanations still consistent with every
  run seen ("yesterday", "start of this week", "a fixed date", ...). The recipe is replayed on a
  given day only if every remaining explanation gives the SAME date that day. When they disagree
  (the first Monday, the first of a month), the job runs the normal way, and that run is the new
  evidence that removes the wrong explanations.

  Read only. Only calls the hub classified as reads are recorded, and each is classified again at
  replay time; anything else stops the replay.

  Fail open. A replayed step that errors, a changed task text, a tool that is gone: the job runs
  exactly as it did before recipes existed. Two failed replays in a row delete the recipe.

  Visible. One JSON file per job in <brain>/Javis/recipes/. Delete the file to forget the recipe.

The model is told which arguments were used for every prefetched call, so a wrong period is
visible to it, and it is told it may call any tool again.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

VERSION = 1
MAX_STEPS = 12
MAX_ARGS_CHARS = 6000
PREFETCH_TOTAL_CHARS = 24_000
PREFETCH_STEP_CHARS = 8_000
MIN_OBSERVATIONS = 2
MAX_FAILS = 2
QUERY_TOOL = "javis_query"
_DATE_RE = re.compile(r"(?<!\d)(20\d\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(?!\d)")
_SLOT_RE = re.compile(r"\{\{d(\d+)\}\}")
_REF_RE = re.compile(r"tr_[0-9a-f]{24}")
# Calls that teach the model how to call a tool. Replaying them would only spend characters.
_SKIP_TOOL_RE = re.compile(r"(describe|schema|introspect|help|usage_guide|list_actions)", re.I)

_lock = threading.RLock()
_live: dict = {}          # job -> {"steps": [...], "refs": {ref: step index}, "replayed": bool, "bad": bool}


def enabled() -> bool:
    """`mcp.recipes`: true (default) | false. JAVIS_RECIPES=0|1 wins."""
    v = (os.getenv("JAVIS_RECIPES") or "").strip().lower()
    if v in ("0", "false", "off", "no"):
        return False
    if v in ("1", "true", "on", "yes"):
        return True
    try:
        import config
        return (config.read_settings().get("mcp") or {}).get("recipes", True) is not False
    except Exception:  # noqa: BLE001
        return True


def base_job(job: str) -> str:
    """'reminder:<id>:<slot>' -> 'reminder:<id>': every firing of one reminder shares one recipe."""
    parts = str(job or "").split(":")
    return ":".join(parts[:2]) if len(parts) >= 2 and parts[0] == "reminder" and parts[1] else ""


def today(tz=None) -> date:
    try:
        if tz is None:
            import localefmt
            tz = localefmt.tz()
        return datetime.now(tz).date()
    except Exception:  # noqa: BLE001
        return date.today()


# ---------------------------------------------------------------- dates as explanations

def _add_months(d: date, k: int) -> date:
    m = d.year * 12 + (d.month - 1) + k
    return date(m // 12, m % 12 + 1, 1)


def explain(found: date, run_day: date) -> list:
    """Every explanation of why `found` appears in a call made on `run_day`."""
    out = [["literal", found.isoformat()]]
    n = (found - run_day).days
    if -400 <= n <= 400:
        out.append(["day", n])
    monday = run_day - timedelta(days=run_day.weekday())
    for k in range(-8, 2):
        if found == monday + timedelta(days=7 * k):
            out.append(["week_start", k])
        if found == monday + timedelta(days=7 * k + 6):
            out.append(["week_end", k])
    first = run_day.replace(day=1)
    for k in range(-13, 2):
        start = _add_months(first, k)
        if found == start:
            out.append(["month_start", k])
        if found == start.replace(day=calendar.monthrange(start.year, start.month)[1]):
            out.append(["month_end", k])
    for k in (-1, 0):
        if found == date(run_day.year + k, 1, 1):
            out.append(["year_start", k])
        if found == date(run_day.year + k, 12, 31):
            out.append(["year_end", k])
    return out


def evaluate(explanation: list, run_day: date) -> Optional[date]:
    kind, k = explanation[0], explanation[1]
    try:
        if kind == "literal":
            return date.fromisoformat(k)
        if kind == "day":
            return run_day + timedelta(days=int(k))
        monday = run_day - timedelta(days=run_day.weekday())
        if kind == "week_start":
            return monday + timedelta(days=7 * int(k))
        if kind == "week_end":
            return monday + timedelta(days=7 * int(k) + 6)
        first = run_day.replace(day=1)
        if kind == "month_start":
            return _add_months(first, int(k))
        if kind == "month_end":
            start = _add_months(first, int(k))
            return start.replace(day=calendar.monthrange(start.year, start.month)[1])
        if kind == "year_start":
            return date(run_day.year + int(k), 1, 1)
        if kind == "year_end":
            return date(run_day.year + int(k), 12, 31)
    except (ValueError, TypeError, OverflowError):
        return None
    return None


def skeleton(steps: list) -> tuple:
    """(steps with every date replaced by a slot, the dates found in slot order)."""
    text = json.dumps(steps, ensure_ascii=False, sort_keys=True)
    found = []

    def sub(m):
        found.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        return "{{d%d}}" % (len(found) - 1)
    return _DATE_RE.sub(sub, text), found


def fill(skel: str, dates: list) -> list:
    return json.loads(_SLOT_RE.sub(lambda m: dates[int(m.group(1))].isoformat(), skel))


# ---------------------------------------------------------------- recording a live run

def begin(job: str) -> None:
    key = base_job(job)
    if key and enabled():
        with _lock:
            _live[key] = {"steps": [], "refs": {}, "replayed": False, "bad": False, "paused": False,
                          "replay_failed": False}


def _swap_refs(args: Any, refs: dict, state: dict) -> Any:
    """Replace a stored-result reference by the step that produced it. An unknown reference (from
    another run, or made up) cannot be replayed: the recording is marked unusable."""
    text = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)

    def sub(m):
        if m.group(0) not in refs:
            state["bad"] = True
            return m.group(0)
        return "{{ref%d}}" % refs[m.group(0)]
    return json.loads(_REF_RE.sub(sub, text))


def note_call(job: str, tool: str, args: Any, *, ok: bool, ref: str = "") -> None:
    """One read call a model made during a recurring job (called by the hub)."""
    key = base_job(job)
    if not key:
        return
    with _lock:
        st = _live.get(key)
        if st is None or st["replayed"] or st["paused"]:
            return
        if not ok:
            return                                  # a failed attempt is not part of what worked
        if _SKIP_TOOL_RE.search(str(tool or "")):
            return
        if len(st["steps"]) >= MAX_STEPS:
            st["bad"] = True
            return
        clean = _swap_refs(args if isinstance(args, dict) else {}, st["refs"], st)
        if len(json.dumps(clean, ensure_ascii=False, default=str)) > MAX_ARGS_CHARS:
            st["bad"] = True
            return
        st["steps"].append({"tool": str(tool), "args": clean})
        if ref and ref not in st["refs"]:
            st["refs"][ref] = len(st["steps"]) - 1


def pause(job: str) -> None:
    """Stop recording while the recipe's own calls run (they must not record themselves)."""
    key = base_job(job)
    with _lock:
        if key in _live:
            _live[key]["paused"] = True


def replay_done(vault_root: str, job: str, ok: bool) -> None:
    """After a replay attempt: a good one makes this a replayed run; a failed one counts against the recipe and the
    run goes on the normal way, recorded from scratch."""
    key = base_job(job)
    with _lock:
        st = _live.get(key)
        if st is None:
            return
        st["paused"] = False
        if ok:
            st["replayed"] = True
            return
        st.update(steps=[], refs={}, bad=False, replay_failed=True)
    old = load(vault_root, job)
    if old is not None:
        old["fails"] = int(old.get("fails") or 0) + 1
        if old["fails"] >= MAX_FAILS:
            forget(vault_root, job)
        else:
            _save(vault_root, key, old)


def _path(vault_root: str, key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key)[:120]
    return Path(vault_root) / "Javis" / "recipes" / f"{safe}.json"


def load(vault_root: str, job: str) -> Optional[dict]:
    key = base_job(job)
    if not key or not vault_root:
        return None
    try:
        data = json.loads(_path(vault_root, key).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and data.get("version") == VERSION else None
    except (OSError, ValueError):
        return None


def _save(vault_root: str, key: str, data: dict) -> None:
    p = _path(vault_root, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def forget(vault_root: str, job: str) -> None:
    key = base_job(job)
    if key and vault_root:
        try:
            _path(vault_root, key).unlink()
        except OSError:
            pass


def task_sha(text: str, mode: str) -> str:
    return hashlib.sha256((str(mode or "") + "\n" + " ".join(str(text or "").split())).encode("utf-8")).hexdigest()[:24]


def finish(vault_root: str, job: str, *, ok: bool, task: str, mode: str, run_day: Optional[date] = None) -> str:
    """Close the recording of one run. Returns what happened, for logs and tests:
    "" | replayed | learned | confirmed | narrowed | reset | dropped."""
    key = base_job(job)
    with _lock:
        st = _live.pop(key, None) if key else None
    if not key or st is None or not vault_root or not enabled():
        return ""
    run_day = run_day or today()
    sha = task_sha(task, mode)
    old = load(vault_root, job)
    if st["replayed"]:
        if old is not None:
            old["replays"] = int(old.get("replays") or 0) + 1
            old["last_replay"] = run_day.isoformat()
            old["fails"] = 0 if ok else int(old.get("fails") or 0) + 1
            if old["fails"] >= MAX_FAILS:
                forget(vault_root, job)
                return "dropped"
            _save(vault_root, key, old)
        return "replayed"
    if not ok or st["bad"] or not st["steps"]:
        return ""
    skel, dates = skeleton(st["steps"])
    slots = [explain(d, run_day) for d in dates]
    if (old is not None and old.get("task_sha") == sha and old.get("skeleton") == skel
            and len(old.get("slots") or []) == len(slots)):
        if run_day.isoformat() in (old.get("days") or []):
            return ""                                           # a second run on the same day proves nothing
        merged = []
        for prev, now in zip(old["slots"], slots):
            keep = [e for e in prev if e in now]
            if not keep:
                old = None                                      # no explanation survives: start over
                break
            merged.append(keep)
        if old is not None:
            old["slots"] = merged
            old["days"] = (old.get("days") or [])[-9:] + [run_day.isoformat()]
            old["observations"] = int(old.get("observations") or 1) + 1
            if not st.get("replay_failed"):
                old["fails"] = 0
            _save(vault_root, key, old)
            return "confirmed" if old["observations"] == MIN_OBSERVATIONS else "narrowed"
    _save(vault_root, key, {
        "version": VERSION, "job": key, "task_sha": sha, "mode": str(mode or ""), "skeleton": skel,
        "slots": slots, "days": [run_day.isoformat()], "observations": 1, "replays": 0, "fails": 0,
        "recorded_at": int(time.time()),
        "note": "Read calls Javis repeats for this recurring job before the model starts. Delete this file to "
                "forget it.",
    })
    return "learned" if old is None else "reset"


# ---------------------------------------------------------------- replay

def plan(recipe: Optional[dict], task: str, mode: str, run_day: Optional[date] = None) -> Optional[list]:
    """The concrete steps for `run_day`, or None when the recipe must not be used today."""
    if not recipe or not enabled():
        return None
    if recipe.get("task_sha") != task_sha(task, mode) or int(recipe.get("observations") or 0) < MIN_OBSERVATIONS:
        return None
    if int(recipe.get("fails") or 0) >= MAX_FAILS:
        return None
    run_day = run_day or today()
    dates = []
    for slot in recipe.get("slots") or []:
        values = {evaluate(e, run_day) for e in slot}
        if len(values) != 1 or None in values:
            return None                                         # the explanations disagree today: do not guess
        dates.append(values.pop())
    try:
        steps = fill(recipe["skeleton"], dates)
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    return steps if isinstance(steps, list) and steps else None


def _is_read(route: dict, tool: str, args: dict) -> bool:
    if tool == QUERY_TOOL:
        return True                                            # javis_query checks its own source
    ent = route.get(tool) or {}
    conn = ent.get("conn")
    if not conn or not ent.get("tool"):
        return False
    try:
        import mcp_catalog
        return mcp_catalog.classify(mcp_catalog.get(conn.get("connector_id")), ent["tool"], args) == "read"
    except Exception:  # noqa: BLE001
        return False


async def replay(steps: list, route: dict) -> Optional[list]:
    """Run the steps through the guarded route. [(tool, args, result)] or None when any step fails."""
    import mcp_client
    import tool_result_shaper
    # the tool search may hide a recorded tool: javis_query's entry carries every route of this tool list
    route = (route.get(QUERY_TOOL) or {}).get("full_route") or route
    out, refs, used = [], {}, 0
    for i, step in enumerate(steps):
        tool = str(step.get("tool") or "")
        text = json.dumps(step.get("args") or {}, ensure_ascii=False)
        missing = [m for m in re.findall(r"\{\{ref(\d+)\}\}", text) if int(m) not in refs]
        if missing:
            return None
        args = json.loads(re.sub(r"\{\{ref(\d+)\}\}", lambda m: refs[int(m.group(1))], text))
        if tool not in route or not _is_read(route, tool, args):
            return None
        try:
            with tool_result_shaper.for_model():
                result = str(await mcp_client.call_route(route, tool, args))
        except Exception:  # noqa: BLE001
            return None
        if result.lstrip().startswith("ERROR:"):
            return None
        found = _REF_RE.search(result[:600])
        if found:
            refs[i] = found.group(0)
        shown = result if len(result) <= PREFETCH_STEP_CHARS else result[:PREFETCH_STEP_CHARS]
        used += len(shown)
        if used > PREFETCH_TOTAL_CHARS:
            return None                                         # too much to hand over: run the normal way
        out.append((tool, args, shown))
    return out


def prompt_block(results: list, run_day: Optional[date] = None) -> str:
    """What the model reads about the prefetched data (model-facing, Vietnamese like the job prompt)."""
    run_day = run_day or today()
    lines = [
        "",
        "",
        f"DỮ LIỆU JAVIS ĐÃ LẤY SẴN ({run_day.isoformat()}): đây là các lệnh ĐỌC mà việc này đã tự gọi ở những lần chạy "
        "trước, Javis vừa chạy lại cho kỳ hiện tại. Dùng luôn, không cần tìm tool hay gọi lại. KIỂM TRA tham số "
        "(nhất là ngày) của từng lệnh có khớp việc được giao không; sai kỳ hoặc thiếu dữ liệu thì cứ gọi tool như "
        "bình thường. Mọi hành động ra ngoài (gửi, đăng, tạo) vẫn do bạn quyết định và tự làm.",
    ]
    for i, (tool, args, result) in enumerate(results, 1):
        lines.append(f"\n[{i}] {tool} {json.dumps(args, ensure_ascii=False)}\n{result}")
    return "\n".join(lines)
