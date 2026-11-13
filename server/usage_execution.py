"""Pure request selection shared by execution usage views and the existing index cache."""
from __future__ import annotations

from collections import defaultdict


def _attempt_key(event):
    ex = event.get("execution") or {}
    return (ex.get("experiment_id") or ex.get("team_id"),
            ex.get("execution_id") or ex.get("turn_id") or event.get("event_id"), ex.get("attempt"))


def _money(events):
    result = {"currency": "USD", "reported_usd": None, "estimated_usd": None,
              "subscription_equivalent_usd": None, "unknown_requests": 0,
              "subscription_requests": 0, "local_requests": 0}
    keys = {"provider_reported": "reported_usd", "estimated": "estimated_usd",
            "subscription_equivalent": "subscription_equivalent_usd"}
    for event in events:
        money = event.get("money") or {}
        key = keys.get(money.get("provenance"))
        amount = money.get("amount")
        if money.get("billing_mode") == "subscription":
            result["subscription_requests"] += 1
        if money.get("billing_mode") == "local":
            result["local_requests"] += 1
        if key and amount is not None and money.get("currency") == "USD":
            result[key] = round((result[key] or 0) + amount, 8)
        elif money.get("provenance") != "local":
            result["unknown_requests"] += 1
    return result


def _attempts(events, details=()):
    """Select requests by provider identity, never by matching token counts or calendar day.

    One pass over `events` and one over `details` (2026-11-13). Each attempt used to scan every event and every detail
    again to find the ones of its CLI session, so the work grew with the square of what a team had ever run: 59 s for a
    team of 3,000 turns on an API engine, on every open of that team (GET /teams/{id}), while the page gave up after
    30 s and asked again. The server then answered nobody (customer report: pages lose their connection when a Team is
    used a lot). The session lookups below give the same answers from tables built once."""
    details = list(details)
    groups = defaultdict(list)
    session_attempts = defaultdict(set)      # CLI session id -> the attempts that ran in it
    for event in events:
        key = _attempt_key(event)
        groups[key].append(event)
        session = (event.get("execution") or {}).get("cli_session_id")
        if session:
            session_attempts[session].add(key)
    session_details = defaultdict(list)      # CLI session id -> its request details, in order
    ambiguous_sessions = set()
    for detail in details:
        session = detail.get("session_id")
        if not session:
            continue
        session_details[session].append(detail)
        if detail.get("ambiguous_session"):
            ambiguous_sessions.add(session)
    for key, group in groups.items():
        fallback = [e for e in group if e.get("event_kind") == "cli_fallback"]
        requests = [e for e in group if e.get("event_kind") in ("request", "cli_detail")]
        anchor = (fallback or requests or group)[-1]
        ex = anchor.get("execution") or {}
        sid = ex.get("cli_session_id")
        ambiguous = bool(sid and (len(session_attempts.get(sid, ())) > 1 or sid in ambiguous_sessions))
        raw = list(session_details.get(sid, ())) if (sid and ex.get("cli_session_new") and not ambiguous) else []
        for detail in raw:
            requests.append({**detail, "event_kind": "cli_detail", "execution": ex,
                "provider": anchor.get("provider"), "raw_observation": True,
                "in": detail["input"] + detail["cache_read"] + detail["cache_create"],
                "out": detail["output"], "tokens_known": True})
        identified, anonymous = {}, []
        for request in requests:
            if request.get("request_id"):
                identity = (request.get("provider"), (request.get("execution") or {}).get("cli_session_id") or sid,
                            request["request_id"])
                prior = identified.get(identity)
                if prior and not request.get("raw_observation") and not prior.get("raw_observation"):
                    request = {**request, "ts": prior.get("ts"), "day": prior.get("day")}
                identified[identity] = request
            else:
                anonymous.append(request)
        yield {"key": key, "group": group, "fallback": fallback,
               "requests": anonymous + list(identified.values()), "raw": raw, "ambiguous_session": ambiguous}


def _aggregate(events, details=(), telemetry_errors=0):
    observed = []
    money_events = []
    unresolved = missing = missing_requests = persisted_errors = 0
    request_count = 0
    requests_complete = True
    statuses = defaultdict(int)
    attempts = list(_attempts(events, details))
    for attempt in attempts:
        missing_before = missing
        group = attempt["group"]
        lifecycle = [e for e in group if e.get("event_kind") == "execution"]
        fallback, requests = attempt["fallback"], attempt["requests"]
        if attempt["ambiguous_session"]:
            requests_complete = False
            unresolved += 1
        expected = max((e.get("expected_requests") or 0 for e in lifecycle), default=0)
        persisted_errors += max((e.get("telemetry_errors") or 0 for e in group), default=0)
        if expected > len(requests):
            missing_requests += expected - len(requests)
            requests_complete = False
        for event in lifecycle + fallback:
            statuses[event.get("status") or "unknown"] += 1
        if fallback:
            latest = fallback[-1]
            known = [e for e in requests if e.get("tokens_known")]
            reconciled = bool(known) and len(known) == len(requests) and latest.get("tokens_known") and (
                sum(e.get("in") or 0 for e in known) == latest.get("in") and
                sum(e.get("out") or 0 for e in known) == latest.get("out"))
            if reconciled:
                observed.extend(known)
                request_count += len(known)
                # Provider summary owns its API-equivalent amount. Detail replaces tokens
                # and request count, never adds the same monetary observation again.
                money_events.append(latest)
            else:
                if latest.get("tokens_known"):
                    observed.append(latest)
                else:
                    partial = dict(latest)
                    for field in ("in", "out"):
                        values = [r[field] for r in requests if r.get(field) is not None]
                        candidates = ([sum(values)] if values else []) + ([latest[field]] if latest.get(field) is not None else [])
                        partial[field] = max(candidates) if candidates else None
                    observed.append(partial)
                money_events.append(latest)
                requests_complete = False
                unresolved += len(requests)
                if not latest.get("tokens_known"):
                    missing += 1
        elif requests:
            observed.extend(requests)
            money_events.extend(requests)
            request_count += len(requests)
        else:
            missing += 1
            requests_complete = False
        if any(event.get("usage_complete") is False for event in lifecycle):
            if missing == missing_before:
                missing += 1
            requests_complete = False
    known = [e for e in observed if e.get("tokens_known")]
    telemetry_errors = max(telemetry_errors, persisted_errors)
    tokens_complete = len(known) == len(observed) and missing == 0 and missing_requests == 0 and unresolved == 0 and not telemetry_errors
    requests_complete = requests_complete and not telemetry_errors
    money = _money(money_events)
    coverage = {"status": "observed" if events and tokens_complete and requests_complete and not telemetry_errors
                and not money["unknown_requests"] else
                "partial" if events else "unknown", "observed_requests": request_count,
                "unobserved_attempts": missing, "unresolved_events": unresolved,
                "missing_requests": missing_requests,
                "telemetry_errors": telemetry_errors, "tokens_complete": bool(events) and tokens_complete,
                "money_complete": bool(events) and not missing and not missing_requests
                                  and money["unknown_requests"] == 0 and not telemetry_errors,
                "requests_complete": bool(events) and requests_complete,
                "scope": "instrumented_executions", "cli_detail": "linked_and_reconciled_only"}
    return {"attempts": len(attempts), "requests": request_count if requests_complete and events else None,
            "tokens_in": sum(e["in"] for e in observed if e.get("in") is not None)
                         if any(e.get("in") is not None for e in observed) else None,
            "tokens_out": sum(e["out"] for e in observed if e.get("out") is not None)
                          if any(e.get("out") is not None for e in observed) else None,
            "money": money, "coverage": coverage, "statuses": dict(statuses), "cost_behavior": "observe_only"}


def quota_points(events):
    """Keep request observation times; a summary supplies only the unresolved remainder."""
    points = []
    for attempt in _attempts(events):
        fallback, requests = attempt["fallback"], attempt["requests"]
        summary = fallback[-1] if fallback else None
        request_points = [(event["ts"], sum(event.get(field) or 0 for field in ("in", "out")))
                          for event in requests]
        if summary:
            remaining = [summary.get(field) - sum(event.get(field) or 0 for event in requests)
                         if summary.get(field) is not None else 0 for field in ("in", "out")]
            if not summary.get("tokens_known") or all(value >= 0 for value in remaining):
                points.extend((min(at, summary["ts"]), value) for at, value in request_points)
                points.append((summary["ts"], sum(max(0, value) for value in remaining)))
            else:
                # Conflicting observations cannot establish a later request boundary.
                points.append((min([summary["ts"]] + [at for at, _ in request_points]), summary["in"] + summary["out"]))
        else:
            points.extend(request_points)
    return points


