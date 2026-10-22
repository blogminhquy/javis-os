# Webhook platform, M5: operations (0.274.0)

> **Spec alignment (0.274.0).** This note was written from the owner's brief, before the spec of record arrived. Where it differs, the spec and `README.md` (requirements matrix) win. What changed here: limits follow spec §11 (300 per minute, burst 100, backlog 10,000 or 256 MiB, store 1 GiB with the WAL, AI 30 per hour); notifications go through a durable outbox, errors_only groups failures, blocks and unclear outcomes into incidents; masking covers every dashboard text and raw access is audited; failed bodies are kept until the owner settles them; the page has three parts and two switches (pause processing, stop receiving). The "Assumptions to reconcile" below are settled by that matrix.

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
| `daily_digest` | counted in the digest | counted in the digest | **sent at once** (only the owner can settle them: unknown, an approval, a workflow question) |
| `none` | not sent | not sent | not sent; the log and the card's badge still show them |

The digest is sent once a day after 08:00 in the **owner's time zone** (`localefmt.tz`, the same as reminders), never the
server's. A VPS on UTC still digests at 08:00 Vietnam time. One message per hook covers the last 24 hours: runs
done, failed or unknown, waiting for the owner, filtered or duplicate. No model is involved. The dedup key is
`whd:<hook>:<day>`. A delivery that fails is tried again at later sweeps, up to 10 times that day. One hook failing
never stops the others. Events the mode does not send are marked told at once, so they never sit in the resend queue.
A notice resent after a failed delivery is rebuilt from the event with its branches, so an approval request is still
one.

## Quotas and the AI budget

- **Quotas**: hour, day and backlog per hook, counted from the store. They survive a restart. Only events that run
  count (filtered, invalid and duplicate events have their own cap, see M2). Past a quota, the sender gets 429 and
  nothing is stored, so its retry is a fresh event.
- **AI budget**: AI runs of the hook since midnight in the owner's time zone. Each dispatch counts, including retries
  of one event, and runs are kept in their own append-only table. Past the budget, the AI branch
  is `failed` ("AI budget reached for today"). This is decided **before** dispatch, so the model is never called and
  the owner's Retry the next day is safe. Other branches of the event still run. A refusal is not an incident (no
  triage, which may use a model). `ai_per_day: 0` means the hook's own AI branch never calls a model. Tool actions
  through the hub are outside this budget: a tool that itself uses a model (for example image generation) counts
  against nothing here. The budget counts runs, not tokens or money. Javis does not see the cost of a run on a
  subscription plan.

## Circuit breaker

Per hook and per action, for HTTP, Apps Script, plugin and tool branches (AI branches have the budget instead).

- 5 failures in a row open the breaker (`failed`, `unknown`, or an answer of "not sent / busy"). It stays open 10
  minutes, then 20, 40, up to 60 at each reopening. After the cooldown it is half open: ONE attempt goes through (a
  hook runs one event at a time), and a failure reopens it at once.
- While it is open, the branch is not sent. It waits as `retry` until the breaker lets one attempt through, and the
  wait does not use a try. Such parked events do NOT count toward the backlog, which counts only events due now.
  They have their own cap (`PARKED_MAX`, 200 per hook), so one receiver that is down never makes the hook refuse
  events whose other branches run fine.
- The owner is told once per opening, in every mode except `none`. A plain message, no model. A notice that could
  not be delivered is sent again at the next sweep.
- One success closes it. Pointing the action at another address, or removing it, clears it. The card shows "sending
  to <action> is paused".

## Retention and export

- `retention_days` per hook, shorter or longer than the default 30 (up to 365). Events the owner still owes something
  (`unknown`, `waiting` for an answer or an approval) are always kept, with their body, until settled. Bodies of
  other finished events are emptied after 7 days.
- On top of the days, a hook keeps at most 500 finished runs and 200 events the rules stopped. Nothing received in
  the last 25 hours is pruned by these caps, because the day quota and the AI budget count those rows.
- `GET /webhooks/events/export?hook=&since=&until=&format=jsonl|csv&body=0|1` streams the log oldest first, in
  batches. It includes each event's branches, mapped fields and trace. It never includes the hook's configuration or
  a secret. Bodies are included only with `body=1`. In CSV, cells starting with `= + - @` are prefixed with `'` so a
  spreadsheet does not run them as formulas.

## Dashboard

- The card log has a filter (all, needs you = unknown and waiting, failed and dead, ran, filtered and invalid and
  duplicate). Every filter pages with keyset pagination ("older runs"). Export CSV is there too. CSV has a trace
  column, and cells a spreadsheet would run as formulas are neutralised (also after a tab, CR or spaces).
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

## Independent review (M5)

The review of 3cfcbab8, read at acf8af3c, found no P1 and 8 P2 issues, all reproduced and all fixed. The regression
tests in `tests/python/test_webhook_m5_review.py` fail on the reviewed commit.

| Finding | Fix |
|---|---|
| P2 an approval request whose first notice failed was dropped in errors_only/daily_digest | the resend rebuilds the event with its branches |
| P2 a workflow question was silenced in errors_only/daily_digest | `waiting` always needs the owner; the digest counts it as "waiting for you", not done |
| P2 after the cooldown 5 attempts went to a receiver still down | half-open: one attempt, one failure reopens |
| P2 retention deleted events waiting for approval and emptied their body | `waiting` kept like `unknown` in every prune path and in eviction |
| P2 per_day and ai_per_day undercounted after the 500-row cap | nothing from the last 25 h is cap-pruned; AI runs in their own table |
| P2 digest hour and AI-budget midnight in the server's zone | owner's zone (`localefmt.tz`) |
| P2 an AI-budget refusal went to incident triage (model) | only an AI branch that was dispatched and failed is an incident |
| P2 one failing receiver filled the backlog (429 for everything) | parked events have their own cap and do not count as backlog |
| P3 (fixed) | budget counts dispatches; breaker cleared when the target changes and when the hook is deleted (with its digest keys); breaker notice not sent in `none`, resent if undelivered; digest per hook isolated, at most 10 tries a day, window at most 24 h; needs_you paginates; Failed includes dead and Filtered includes invalid and duplicate; CSV neutralises after tab/CR/spaces and has a trace column; the M3 crash test made deterministic |

## Assumptions to reconcile with the spec

1. Mode names, and the rule that "needs you" items are sent at once in `daily_digest`.
2. Digest hour 08:00 local, plain counts.
3. Breaker: 5 failures, a 10-minute cooldown doubling up to 60 minutes, per hook and action.
4. AI budget in runs per local day (default 100), not in tokens or money.
5. Default limits are kept from 0.198.0 (30/hour, 6 waiting), plus a day limit that is off by default.

## Rollback

Settings are extra fields on the hook. Older code ignores them, and the defaults of the older code apply. The
`breakers` and `ai_runs` tables and the `digest_*` meta keys are ignored too. Settle what waits before rolling back
to M3 or M4 code. M4's prune deletes `waiting` events like finished ones, and M3 code reads an `approval` branch as
done. Use the log filter "Needs you".
