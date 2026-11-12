"""market_live.py - keeps market data fresh in the background and archives it.

A loop started at server start refreshes each market on its own clock, whether or not anyone has the page open:
  Vietnam  every 60 s while HOSE/HNX trade (30 s when someone is watching), every 30 min otherwise
  crypto   every 60 s (30 s when watched), around the clock
  world    every 5 min on weekdays (2 min when watched), every 30 min at weekends

After each refresh, `after_refresh()` hands the price series to market_store (in a worker thread): daily bars go
into the archive, a signal snapshot is taken once per closed session, and once a day the last 60 sessions are
backfilled so the accuracy card has numbers immediately.

Off switch: the toggle on the Markets page (STATE_DIR/market/settings.json) or JAVIS_MARKET_BACKGROUND=0. Tests set
the env var in tests/python/_paths.py so a booted server never reaches the network.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
import sys
import time

import market_data as md

_TASK: asyncio.Task | None = None
_LAST: dict = {"vn": 0.0, "world": 0.0, "crypto": 0.0}
_STATUS: dict = {"started": 0.0, "runs": 0, "errors": 0, "last_error": "", "last": {}}
_PENDING: set = set()


def _settings_path():
    return md._dir() / "settings.json"


def settings() -> dict:
    try:
        d = json.loads(_settings_path().read_text(encoding="utf-8"))
    except Exception:
        d = {}
    return {"background": bool(d.get("background", True)), "paper_telegram": bool(d.get("paper_telegram", True))}


def save_settings(patch: dict) -> dict:
    cur = settings()
    for k in ("background", "paper_telegram"):
        if k in (patch or {}):
            cur[k] = bool(patch[k])
    _settings_path().write_text(json.dumps(cur), encoding="utf-8")
    return cur


def env_off() -> bool:
    return os.getenv("JAVIS_MARKET_BACKGROUND", "1").strip().lower() in ("0", "false", "off", "no")


def enabled() -> bool:
    return not env_off() and settings()["background"]


def interval(kind: str, now: float | None = None) -> float:
    now = now or time.time()
    watched = now - md.LAST_VIEW < 90
    if kind == "vn":
        if md.vn_in_session(now):
            return 30 if watched else 60
        return 900 if watched else 1800
    if kind == "crypto":
        return 30 if watched else 60
    weekend = _dt.datetime.fromtimestamp(now, _dt.timezone.utc).weekday() >= 5
    if weekend:
        return 1800
    return 120 if watched else 300


def status() -> dict:
    return {**_STATUS, "enabled": enabled(), "env_off": env_off(), "running": bool(_TASK and not _TASK.done()),
            "settings": settings(), "intervals": {k: interval(k) for k in _LAST}, "in_session": md.vn_in_session()}


async def _loop():
    await asyncio.sleep(15)
    while True:
        try:
            if enabled():
                now = time.time()
                for kind in ("crypto", "vn", "world"):
                    if now - _LAST[kind] >= interval(kind, now):
                        _LAST[kind] = now
                        try:
                            await md.refresh_section(kind)
                            _STATUS["runs"] += 1
                            _STATUS["last"][kind] = time.time()
                        except Exception as e:  # noqa: BLE001 - one market failing must not stop the others
                            _STATUS["errors"] += 1
                            _STATUS["last_error"] = f"{kind}: {type(e).__name__}: {e}"[:300]
        except Exception as e:  # noqa: BLE001
            print(f"[market] background loop: {type(e).__name__}: {e}", file=sys.stderr)
        await asyncio.sleep(10)


def start() -> bool:
    """Start the loop once. Returns False when switched off by env (tests, or the owner's choice)."""
    global _TASK
    if env_off():
        return False
    if _TASK and not _TASK.done():
        return True
    _STATUS["started"] = time.time()
    _TASK = asyncio.get_running_loop().create_task(_loop())
    return True


# ---------------------------------------------------------------- archive hook

def _today_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")


def snapshot_date(kind: str, data: dict, now: float | None = None) -> str:
    """The session a snapshot belongs to, or "" while that session is still trading."""
    import market_store as ms
    now = now or time.time()
    if kind == "crypto":
        return _dt.datetime.fromtimestamp(now, _dt.timezone.utc).strftime("%Y-%m-%d")
    bench = data.get("bench")
    rows = (data.get("indices") or []) + (data.get("rows") or [])
    b = next((r for r in rows if r.get("symbol") == bench), None)
    d = (b or {}).get("bar_date") or ""
    if not d:
        return ""
    if kind == "vn":
        vnow = md.vn_now(now)
        today = vnow.strftime("%Y-%m-%d")
        closed = d < today or (vnow.hour * 60 + vnow.minute >= 15 * 60 + 5) or vnow.weekday() >= 5
        return d if closed and not md.vn_in_session(now) else ""
    utc = _dt.datetime.fromtimestamp(now, _dt.timezone.utc)
    closed = d < utc.strftime("%Y-%m-%d") or utc.hour * 60 + utc.minute >= 21 * 60 + 15
    return d if closed else ""


def _archive(kind: str, data: dict, series: dict, meta: dict) -> None:
    import market_store as ms
    ms.upsert_bars(kind, series)
    snap = snapshot_date(kind, data)
    if snap and not ms.has_snapshot(kind, snap):
        rows = (data.get("rows") or [])
        ms.save_snapshot(kind, snap, rows, md._pick(rows, kind), source="live")
    today = _today_utc()
    if ms.meta_get("bt_" + kind) != today:
        deep = {k: v for k, v in series.items() if v and len(v.get("c") or []) > 80 and k in meta}
        ms.backtest(kind, deep, meta, md._pick, days=60, kind_analyze="crypto" if kind == "crypto" else "stock")
        ms.meta_set("bt_" + kind, today)


_PAPER_PENDING: set = set()


def _paper(kind: str, data: dict) -> None:
    import market_paper
    market_paper.run(kind, data)


def after_refresh(kind: str, data: dict, series: dict, meta: dict) -> None:
    """Called by market_data.refresh_section. Runs the paper-trading pass and the archive work off the event loop,
    one job of each kind per market at a time."""
    if kind not in _PAPER_PENDING:
        _PAPER_PENDING.add(kind)

        async def paper():
            try:
                await asyncio.to_thread(_paper, kind, data)
            except Exception as e:  # noqa: BLE001 - one failed pass must not stop the next refresh
                print(f"[market] paper {kind}: {type(e).__name__}: {e}", file=sys.stderr)
            finally:
                _PAPER_PENDING.discard(kind)
        try:
            asyncio.get_running_loop().create_task(paper())
        except RuntimeError:
            _PAPER_PENDING.discard(kind)
    if kind in _PENDING or not series:
        return
    _PENDING.add(kind)

    async def run():
        try:
            await asyncio.to_thread(_archive, kind, data, series, meta)
        except Exception as e:  # noqa: BLE001 - the page keeps working without the archive
            print(f"[market] archive {kind}: {type(e).__name__}: {e}", file=sys.stderr)
        finally:
            _PENDING.discard(kind)
    try:
        asyncio.get_running_loop().create_task(run())
    except RuntimeError:
        _PENDING.discard(kind)
