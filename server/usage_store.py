"""
usage_store.py - Kho đếm token/chi phí do CHÍNH JAVIS đo (đa nhà cung cấp).

Vì Javis nhìn thấy token in/out trong mọi phản hồi (Claude Code CLI, Codex, OpenRouter, OpenAI,
Anthropic), đây là con số usage đồng nhất - KHÔNG phụ thuộc provider có lộ hạn mức hay không.
KHÁC với "hạn mức tài khoản" (gói thuê bao) mà đa số provider không cho lấy qua API.

Lưu STATE_DIR/usage.json: { "days": { "YYYY-MM-DD": { "<provider>|<model>": {in,out,turns,cost} } },
                            "total": { "<provider>|<model>": {in,out,turns,cost} } }
- Gộp theo NGÀY (giữ 30 ngày gần nhất) + TỔNG tích luỹ.
- cost: the provider's own figure when it sends one (Claude Code CLI total_cost_usd). Otherwise a
  per-token API provider (usage_parsers.PER_TOKEN_PROVIDERS) is priced from usage_pricing.json;
  a model missing from that table is written as cost null in usage-events.jsonl (unknown, not
  free). Plan-based engines stay 0.
"""
from __future__ import annotations

import localefmt   # múi giờ theo cấu hình, thay UTC+7 nhúng cứng
import json
import os
import threading
import uuid
import math
import hashlib
import time
from datetime import datetime, timezone, timedelta

from collections import OrderedDict

import quota_scheduler          # sổ cái TPM dùng chung (không phụ thuộc ngược, xem module đó)
import usage_parsers            # price table (pure module, no config/DB)
from config import STATE_DIR

_PATH = STATE_DIR / "usage.json"
_EVENTS_PATH = STATE_DIR / "usage-events.jsonl"   # append-only, forward-log cho dashboard token
_LOCK = threading.Lock()
_KEEP_DAYS = 30
_TELEMETRY_ERRORS = {}

# Replay snapshots of TEAM observations stay in this process, not in usage.json (2026-11-13).
#
# A snapshot lets the same observation be recorded twice (a provider that reports a request's tokens more than once)
# without counting it twice. Until now every one of them was written into usage.json and kept 30 days, and every
# record() re-read the whole file, filtered every snapshot and wrote the whole file back. A Team that works a lot adds
# one snapshot per model call (API engines: one per tool round), so the file grew with every turn and each model call of
# ANY chat, team or background job froze the server for longer: measured 100 ms per call at 50,000 snapshots and 520 ms
# at 200,000, on the event loop. Open pages then lost their connection whenever a Team was busy (customer report).
#
# The identity of a team observation carries the `execution_id` of its run, a random id made when the member's turn
# starts (main._team_engine_for). It can only be seen again inside that same run of this process: a restart ends the
# run, and a retry gets a new id. So nothing is lost by keeping these snapshots in memory, oldest out first.
# Snapshots of other executions (improvement work, whose ids are stable across restarts) stay in the file as before.
_TEAM_SNAPSHOTS_MAX = 20_000
_TEAM_SNAPSHOTS: "OrderedDict[tuple, dict]" = OrderedDict()
# Snapshot keys that belong in usage.json. A bare hash there is a team snapshot left by a version before this one.
_EXECUTION_PREFIX = "execution:"
_FILE_SNAPSHOT_PREFIXES = ("improvement:", _EXECUTION_PREFIX)


def note_telemetry_error(execution=None) -> None:
    """Keep an honest process-local coverage signal even if the event file cannot be written."""
    try:
        import turn_context
        ex = execution or (turn_context.current() or {}).get("execution") or {}
        if "operation_id" in ex:
            ex = turn_context.execution_metadata(ex)
            if ex is None:
                return
            key = ("improvement_operation", ex["experiment_id"], ex["operation_id"], ex["execution_id"])
            with _LOCK:
                _TELEMETRY_ERRORS[key] = _TELEMETRY_ERRORS.get(key, 0) + 1
        elif ex.get("team_id"):
            key = (ex["team_id"], ex.get("task_id"), ex.get("execution_id") or ex.get("turn_id"))
            with _LOCK:
                _TELEMETRY_ERRORS[key] = _TELEMETRY_ERRORS.get(key, 0) + 1
        elif ex.get("experiment_id") and ex.get("trial_id"):
            key = ("improvement", ex["experiment_id"], ex["trial_id"], ex.get("execution_id"))
            with _LOCK:
                _TELEMETRY_ERRORS[key] = _TELEMETRY_ERRORS.get(key, 0) + 1
    except Exception:
        pass


def telemetry_errors(team_id, task_id=None, execution_id=None) -> int:
    with _LOCK:
        return sum(n for key, n in _TELEMETRY_ERRORS.items() if len(key) == 3
                   and key[0] == team_id and (task_id is None or key[1] == task_id)
                   and (execution_id is None or key[2] == execution_id))


def improvement_telemetry_errors(experiment_id, trial_id=None, execution_id=None) -> int:
    with _LOCK:
        return sum(n for key, n in _TELEMETRY_ERRORS.items() if len(key) == 4 and key[0] == "improvement"
                   and key[1] == experiment_id and (trial_id is None or key[2] == trial_id)
                   and (execution_id is None or key[3] == execution_id))


def operation_telemetry_errors(experiment_id, operation_id, execution_id=None) -> int:
    with _LOCK:
        return sum(n for key, n in _TELEMETRY_ERRORS.items() if len(key) == 4 and key[0] == "improvement_operation"
                   and key[1] == experiment_id and key[2] == operation_id
                   and (execution_id is None or key[3] == execution_id))


def _today() -> str:
    return localefmt.now().strftime("%Y-%m-%d")


_PRICE_CACHE = {"mtime": None, "prices": {}}


def _prices() -> dict:
    """The price table, re-read only when usage_pricing.json changes (record() runs every turn)."""
    try:
        mt = os.path.getmtime(usage_parsers._PRICING_PATH)
    except OSError:
        mt = None
    if _PRICE_CACHE["mtime"] != mt or not _PRICE_CACHE["prices"]:
        _PRICE_CACHE["prices"] = usage_parsers.load_prices()
        _PRICE_CACHE["mtime"] = mt
    return _PRICE_CACHE["prices"]


def _cost_for(provider: str, model: str, tin: int, tout: int, cost: float):
    """Cost of one turn: the provider's own figure when it sent one, else the price table for a
    per-token API provider (None when the model is not in the table), else 0.0 (plan-based).

    Until 2026-10-22 every API turn was written with cost 0.0: no engine reports a bill, so DeepSeek
    background work looked free in usage-events.jsonl and in usage.json."""
    if cost > 0:
        return cost
    if str(provider or "").lower() not in usage_parsers.PER_TOKEN_PROVIDERS:
        return 0.0
    try:
        return usage_parsers.cost_or_none(model, tin, tout, _prices())
    except Exception:
        return None


def _append_event(provider: str, model: str, tin: int, tout: int, cost, **metadata) -> None:
    """Ghi them 1 dong vao usage-events.jsonl (append-only) cho indexer dashboard token doc.
    Best-effort: loi thi bo qua, KHONG duoc lam hong luong chat. Nhanh API (openrouter/openai/
    anthropic) khong co log tho nen day la nguon DUY NHAT cho chung; claude/codex indexer lay
    tu log tho nen dong claude/codex o day chi bi indexer bo qua (tranh dem trung)."""
    try:
        now = datetime.now(timezone.utc)
        line = json.dumps({"ts": int(now.timestamp()), "day": _today(),
                           "provider": provider or "?", "model": model or "?",
                           "in": int(tin or 0), "out": int(tout or 0),
                           # null = per-token API model missing from usage_pricing.json
                           "cost": None if cost is None else round(float(cost), 8), **metadata},
                          ensure_ascii=False)
        with open(_EVENTS_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        note_telemetry_error(metadata.get("execution"))


def _drop_team_leftovers(d: dict) -> int:
    """Remove the team snapshots a version before 2026-11-13 kept in usage.json. Returns how many went.

    Their runs ended with the process that wrote them, so none can be replayed (see _TEAM_SNAPSHOTS). The next save
    writes the file without them."""
    snapshots = d.get("event_snapshots")
    if not isinstance(snapshots, dict) or not snapshots:
        return 0
    kept = {k: v for k, v in snapshots.items() if isinstance(k, str) and k.startswith(_FILE_SNAPSHOT_PREFIXES)}
    dropped = len(snapshots) - len(kept)
    if dropped:
        d["event_snapshots"] = kept
    return dropped


def _load() -> dict:
    try:
        if _PATH.exists():
            d = json.loads(_PATH.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                d.setdefault("days", {})
                d.setdefault("total", {})
                _drop_team_leftovers(d)
                return d
    except Exception:
        pass
    return {"days": {}, "total": {}}


def compact() -> int:
    """Rewrite usage.json without the team snapshots an earlier version left in it. Returns how many were removed.

    Called once when the server starts, on a worker thread, so a file that grew to many megabytes is small again
    before the first chat turn reads it. Without this call the first record() does the same clean-up."""
    with _LOCK:
        try:
            if not _PATH.exists():
                return 0
            d = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:
            return 0
        if not isinstance(d, dict):
            return 0
        dropped = _drop_team_leftovers(d)
        if dropped:
            d.setdefault("days", {})
            d.setdefault("total", {})
            _save(d)
        return dropped


def _save(d: dict) -> None:
    try:
        tmp = _PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_PATH)
    except Exception:
        pass


def _project_improvement(provider, model, metadata):
    """Replace the existing legacy/TPM cache from request observations, including interrupted CLI runs."""
    from usage_execution import _aggregate, _attempt_key, quota_points
    identity = json.dumps([provider, model, *_attempt_key(metadata)], separators=(",", ":"))
    snapshot_key = "improvement:" + hashlib.sha256(identity.encode()).hexdigest()
    event = {"provider": provider, "model": model, "ts": time.time(), "day": _today(), **metadata}
    event_key = ("summary" if event["event_kind"] == "cli_fallback" else
                 "request:" + event["request_id"] if event.get("request_id") else usage_parsers.observation_key(event))
    with _LOCK:
        data = _load()
        snapshots = data.setdefault("event_snapshots", {})
        prior = snapshots.get(snapshot_key) or {}
        observations = prior.get("observations") or {}
        previous = observations.get(event_key)
        if previous:
            event["ts"], event["day"] = previous["ts"], previous["day"]
        observations[event_key] = event
        events = list(observations.values())
        result = _aggregate(events)
        money = result["money"]
        current = {"in": result["tokens_in"] or 0, "out": result["tokens_out"] or 0,
                   "cost": sum(money.get(field) or 0 for field in
                               ("reported_usd", "estimated_usd", "subscription_equivalent_usd")),
                   "turns": result["requests"] if result["requests"] is not None else
                            int(any(e.get("tokens_known") for e in events))}
        day = prior.get("day") or event["day"]
        for bucket in (data["days"].setdefault(day, {}), data["total"]):
            aggregate = bucket.setdefault(provider + "|" + model, {"in": 0, "out": 0, "cost": 0.0, "turns": 0})
            for field, value in current.items():
                aggregate[field] += value - prior.get(field, 0)
        snapshots[snapshot_key] = {"day": day, **current, "observations": observations}
        cutoff = (localefmt.now() - timedelta(days=_KEEP_DAYS)).strftime("%Y-%m-%d")
        # Lifetime totals outlive daily retention. Retain improvement idempotency evidence
        # too, or a late provider correction becomes a new bill and a new TPM observation.
        data["event_snapshots"] = {key: value for key, value in snapshots.items()
                                   if key.startswith("improvement:") or value["day"] >= cutoff}
        for old in sorted(data["days"])[:-_KEEP_DAYS]:
            data["days"].pop(old, None)
        _save(data)
        quota_scheduler.observe_snapshot(provider, model, snapshot_key, quota_points(events))


def record(provider: str, model: str, tin=0, tout=0, cost=None, *, execution=None,
           event_id=None, request_id=None, source_id=None, event_kind="request", status=None,
           billing_mode=None, price_version=None, cache_read=0, cache_create=0,
           expected_requests=None, telemetry_errors=0, usage_complete=None) -> None:
    """Cộng dồn 1 lượt vào ngày hôm nay + tổng. Bỏ qua nếu không có token nào (lượt lỗi)."""
    import turn_context
    ex = turn_context.execution_metadata(execution or (turn_context.current() or {}).get("execution"))
    input_known = tin is not None and event_kind != "execution"
    output_known = tout is not None and event_kind != "execution"
    tokens_known = input_known and output_known
    reported = None if cost is None else float(cost)
    if reported is not None and (not math.isfinite(reported) or reported < 0):
        reported = None
    tin, tout = max(0, int(tin or 0)), max(0, int(tout or 0))
    cost = float(reported or 0.0)
    if tin <= 0 and tout <= 0 and cost <= 0 and not ex:
        return
    cost_ev = _cost_for(provider, model, tin, tout, cost)
    cost = float(cost_ev or 0.0)
    metadata = {}
    if ex:
        estimate = None
        if tokens_known:
            prices = _prices()
            estimate = usage_parsers.cost_or_none(model, tin, tout, prices)
            if estimate is not None and (cache_read or cache_create):
                estimate = usage_parsers.estimate_cost({"model": model,
                    "input": max(0, tin - int(cache_read or 0) - int(cache_create or 0)), "output": tout,
                    "cache_read": cache_read or 0, "cache_create": cache_create or 0}, prices)
        mode = billing_mode or ("api" if provider in usage_parsers.PER_TOKEN_PROVIDERS else
                                "local" if provider == "ollama-local" else "subscription")
        if mode == "api":
            amount = reported if reported is not None else estimate
            provenance = "provider_reported" if reported is not None else "estimated" if amount is not None else "unknown"
        elif mode == "local":
            amount, provenance = 0.0, "local"
        else:
            amount = reported if reported is not None else estimate
            provenance = "subscription_equivalent" if amount is not None else "subscription"
        metadata = {"schema": 1, "event_id": str(event_id or request_id or uuid.uuid4().hex),
                    "request_id": str(request_id) if request_id else None,
                    "source_id": str(source_id or provider), "event_kind": event_kind, "status": status,
                    "execution": ex, "tokens_known": tokens_known,
                    "in": tin if input_known else None, "out": tout if output_known else None,
                    "cache_read": cache_read, "cache_create": cache_create,
                    "expected_requests": expected_requests, "telemetry_errors": int(telemetry_errors or 0),
                    "usage_complete": usage_complete if type(usage_complete) is bool else None,
                    "money": {"currency": "USD", "amount": amount, "provenance": provenance,
                              "billing_mode": mode,
                              "price_version": price_version or ("usage_pricing.json:" + str(_PRICE_CACHE["mtime"]))
                              if provenance == "estimated" or (provenance == "subscription_equivalent" and reported is None)
                              else None}}
    key = f"{provider or '?'}|{model or '?'}"
    if ex and ex.get("experiment_id") and provider in {"anthropic-cli", "cli", "claude"}:
        try:
            _append_event(provider, model, tin, tout, cost_ev, **metadata)
        except Exception:
            note_telemetry_error(ex)
        try:
            _project_improvement(provider, model, metadata)
        except Exception:
            note_telemetry_error(ex)
        return
    if ex and (not tokens_known or event_kind == "cli_detail"):
        try:
            _append_event(provider, model, tin, tout, cost_ev, **metadata)
        except Exception:
            note_telemetry_error(ex)
        return
    with _LOCK:
        d = _load()
        day = _today()
        delta_in, delta_out, delta_cost, delta_turns = tin, tout, cost, 1
        if ex:
            # These are replaceable projection snapshots, not another source of bills. Keep
            # the old Telegram aggregate idempotent under the same replay as the index.
            observation = usage_parsers.observation_key({"provider": provider, **metadata})
            in_memory = bool(ex.get("team_id"))   # a team run: see _TEAM_SNAPSHOTS
            if in_memory:
                snapshot_key = (str(_PATH), observation)
                prior = _TEAM_SNAPSHOTS.get(snapshot_key) or {}
            else:
                snapshots = d.setdefault("event_snapshots", {})
                snapshot_key = _EXECUTION_PREFIX + observation
                prior = snapshots.get(snapshot_key) or {}
            if prior:
                day = prior["day"]
                delta_in -= prior["in"]
                delta_out -= prior["out"]
                delta_cost -= prior["cost"]
                delta_turns = 0
            snapshot = {"day": day, "in": tin, "out": tout, "cost": cost}
            if in_memory:
                _TEAM_SNAPSHOTS[snapshot_key] = snapshot
                _TEAM_SNAPSHOTS.move_to_end(snapshot_key)
                while len(_TEAM_SNAPSHOTS) > _TEAM_SNAPSHOTS_MAX:
                    _TEAM_SNAPSHOTS.popitem(last=False)
            else:
                snapshots[snapshot_key] = snapshot
                cutoff = (localefmt.now() - timedelta(days=_KEEP_DAYS)).strftime("%Y-%m-%d")
                d["event_snapshots"] = {k: v for k, v in snapshots.items()
                                        if k.startswith("improvement:") or v["day"] >= cutoff}
        for bucket in (d["days"].setdefault(day, {}), d["total"]):
            e = bucket.setdefault(key, {"in": 0, "out": 0, "turns": 0, "cost": 0.0})
            e["in"] += delta_in
            e["out"] += delta_out
            e["turns"] += delta_turns
            e["cost"] += delta_cost
        for old in sorted(d["days"])[:-_KEEP_DAYS]:   # dọn ngày cũ
            d["days"].pop(old, None)
        _save(d)
    try:
        _append_event(provider, model, tin, tout, cost_ev, **metadata)
    except Exception:
        note_telemetry_error(ex)
    # Sổ cái TPM dùng chung. Đây là điểm móc PHỔ QUÁT: mọi đường gọi model (chat, loop,
    # task nền, nhắc hẹn, Telegram, CLI, Codex) đều đi qua record(), trong khi admit_quota
    # chỉ nhìn thấy bốn đường canary. Thiếu móc này thì hạn mức của TÀI KHOẢN bị đốt vô hình
    # và canary tưởng còn nhiều token hơn thực tế.
    quota_scheduler.observe(provider, model, max(0, delta_in + delta_out))


def _rollup(bucket: dict) -> dict:
    """Gộp các key <provider>|<model> thành list + tổng cộng."""
    items, tot = [], {"in": 0, "out": 0, "turns": 0, "cost": 0.0}
    for key, e in sorted(bucket.items(), key=lambda kv: -(kv[1]["in"] + kv[1]["out"])):
        prov, _, model = key.partition("|")
        items.append({"provider": prov, "model": model, **e})
        for k in tot:
            tot[k] += e.get(k, 0)
    return {"items": items, "total": tot}


def daily(n: int = 14) -> list:
    """Chuỗi n ngày gần nhất (cũ -> mới) để vẽ đồ thị, lấp cả ngày trống cho trục liền mạch:
    [{day, in, out, cost, turns}]."""
    d = _load()
    days = d.get("days", {})
    tz = localefmt.tz()
    today = datetime.now(tz).date()
    out = []
    for i in range(n - 1, -1, -1):
        day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        bucket = days.get(day, {})
        tot = {"in": 0, "out": 0, "cost": 0.0, "turns": 0}
        for e in bucket.values():
            tot["in"] += e.get("in", 0)
            tot["out"] += e.get("out", 0)
            tot["cost"] += e.get("cost", 0.0)
            tot["turns"] += e.get("turns", 0)
        out.append({"day": day, **tot})
    return out


def summary() -> dict:
    d = _load()
    day = _today()
    return {"day": day,
            "today": _rollup(d["days"].get(day, {})),
            "all_time": _rollup(d.get("total", {}))}
