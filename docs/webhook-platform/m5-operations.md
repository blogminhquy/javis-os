# Webhook platform, M5: operations (0.229.0)

Status: implemented and tested with fakes (no real model, no real outside system). Spec of record:
`docs/superpowers/specs/2026-10-19-webhook-event-platform-design.md`, still not in the repository. The choices below are
from the owner's brief; the open ones are under "Assumptions to reconcile".

## Settings per hook

`POST /webhooks` and `POST /webhooks/update` take these fields. A value out of range is refused, never clamped.

| Field | Values | Default |
|---|---|---|
| `notify` | `all`, `errors_only`, `daily_digest`, `none` | `all` |
| `limits.per_hour` | 1 to 600 events that run | 30 |
| `limits.per_day` | 0 (no limit) to 20 000 | 0 |
| `limits.backlog` | 1 to 50 waiting or running | 6 |
| `ai_per_day` | 0 to 5000 AI runs per local day | 100 |
| `retention_days` | 1 to 365 | 30 |

## Notifications

| Mode | Done | Failed / dead | Unknown, approval needed |
|---|---|---|---|
| `all` | sent | sent | sent at once |
| `errors_only` | not sent | sent | sent at once |
| `daily_digest` | counted in the digest | counted in the digest | **sent at once** (only the owner can settle them) |
| `none` | not sent | not sent | not sent; the log and the card's badge still show them |

The digest is sent once a day after 08:00 local time, one message per hook. It holds plain counts: runs done, failed
or unknown, filtered or duplicate. No model is involved. The dedup key is `whd:<hook>:<day>`. A delivery that fails is
tried again at the next sweep, and the day is marked done only once a delivery succeeds. Events the mode does not send
are marked told at once, so they never sit in the resend queue.

## Quotas and the AI budget

- **Quotas**: hour, day and backlog per hook, counted from the store. They survive a restart. Only events that run
  count (filtered, invalid and duplicate events have their own cap, see M2). Past a quota, the sender gets 429 and
  nothing is stored, so its retry is a fresh event.
- **AI budget**: AI branches of the hook that reached a model since local midnight. Past the budget, the AI branch
  is `failed` ("AI budget reached for today"). This is decided **before** dispatch, so the model is never called and
  the owner's Retry the next day is safe. Other branches of the event still run. `ai_per_day: 0` means the hook never
  calls a model. The budget counts runs, not tokens or money. Javis does not see the cost of a run on a subscription
  plan.

## Circuit breaker

Per hook and per action, for HTTP, Apps Script, plugin and tool branches (AI branches have the budget instead).

- 5 failures in a row open the breaker (`failed`, `unknown`, or an answer of "not sent / busy"). It stays open 10
  minutes, then 20, 40, up to 60 at each reopening.
- While it is open, the branch is not sent. It waits as `retry` until the breaker lets one attempt through, and the
  wait does not use a try. The event stays queued, so the hook's backlog limit pushes back on the sender (429)
  instead of piling up.
- The owner is told once per opening. A plain message, no model.
- One success closes it. The card shows "sending to <action> is paused".

## Retention and export

- `retention_days` per hook, shorter or longer than the default 30 (up to 365). `unknown` events are always kept
  until resolved. Bodies of finished events are still emptied after 7 days.
- `GET /webhooks/events/export?hook=&since=&until=&format=jsonl|csv&body=0|1` streams the log oldest first, in
  batches. It includes each event's branches, mapped fields and trace. It never includes the hook's configuration or
  a secret. Bodies are included only with `body=1`. In CSV, cells starting with `= + - @` are prefixed with `'` so a
  spreadsheet does not run them as formulas.

## Dashboard

- The card log has a filter (all, needs you, failed, ran, filtered), keyset pagination ("older runs"), and Export
  CSV.
- The Rules panel holds the settings above (notification mode, limits, AI budget, retention) with the rules, actions
  and signature check.
- When a breaker is open, the card says so.

## Invariants and their proof

All in `tests/python/test_webhook_ops_m5.py` unless noted.

| Invariant | Test |
|---|---|
| A quota refusal stores nothing | third event over `per_hour: 2`: 429, two events stored; per-day limit |
| Settings are checked | out-of-range, boolean-as-number, unknown keys and unknown modes are refused |
| Non-AI notifications never call a model | digest and breaker notices are plain text built from counts |
| What needs the owner is never silenced by a quiet mode | approval request sent at once in `daily_digest`; `none` sends nothing and marks it told (no resend loop) |
| Digest | nothing before 08:00; a failed delivery is sent again; exactly one message per day with the counts |
| AI budget before dispatch | second run of the day refused, model called once, `dispatched_at` 0; next day the retry runs; budget 0 never calls |
| Breaker | opens after 5, one notice, no send while open (no try used), the AI branch still runs, one attempt after the cooldown, success closes |
| Retention | 2-day hook drops a 3-day-old run, the default keeps it, a 90-day hook keeps a 40-day-old run |
| Export | every event with branches; no snapshot, no secret, no body by default; formulas neutralised |
| Benchmarks | durable receive about 2000-2600 events/s here (synchronous=FULL; bound 20/s); 200 events through receive, worker and a fake run in about 2 s (bound 60 s) |
| UI | `tests/js/test_webhooks_ui_m5.js` |

## Assumptions to reconcile with the spec

1. Mode names, and the rule that "needs you" items are sent at once in `daily_digest`.
2. Digest hour 08:00 local, plain counts.
3. Breaker: 5 failures, a 10-minute cooldown doubling up to 60 minutes, per hook and action.
4. AI budget in runs per local day (default 100), not in tokens or money.
5. Default limits are kept from 0.198.0 (30/hour, 6 waiting), plus a day limit that is off by default.

## Rollback

Settings are extra fields on the hook. Older code ignores them, and the defaults of the older code apply. The
`breakers` table and the `digest_*` meta keys are ignored too.
