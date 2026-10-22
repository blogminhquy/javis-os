# Webhook platform, M1: durable receive and dispatch (0.274.0)

> **Spec alignment (0.274.0).** This note was written from the owner's brief, before the spec of record arrived. Where it differs, the spec and `README.md` (requirements matrix) win. What changed here: the spec decides the store as schema v7 (hooks and revisions in SQLite, receipts, deliveries with generations, a notification outbox, audit); every request is stored and answered 202 before any rule runs, and triage happens in the worker; refusals are 429 / 503 with a code and Retry-After, never 500; a crashed delivery is unknown unless retry-safe, and resends stay within the attempt cap. The "Assumptions to reconcile" below are settled by that matrix.

Status: implemented and tested with fakes (no real model, no real outside system).
Spec of record: `docs/superpowers/specs/2026-10-19-webhook-event-platform-design.md`. **That file was not in the
repository when M1 was written** (it existed only on the owner's machine). M1 was built from the brief the owner gave
with the task; every design choice the spec might decide differently is listed under "Assumptions to reconcile" and
must be checked against the spec before M2 starts.

## What changed

Before 0.274.0 an accepted event lived only in RAM (`deque` per hook). A restart, crash or update between the 202 and
the run lost it, and the sender, already told "accepted", never retried. The idempotency key was written to
`webhooks.json` before the queue decided, so a 429 kept the key and the sender's retry was answered "duplicate"
(the event never ran).

Now:

| Piece | Where |
|---|---|
| Event store (SQLite, WAL, `synchronous=FULL`, file mode 600) | `server/webhook_store.py`, file `STATE_DIR/webhook_events.sqlite3` |
| Receive: event + dedup in one `BEGIN IMMEDIATE` transaction, 202 only after `COMMIT` | `Store.ingest`, `WebhookFeature.accept/_ingest` |
| Limits counted from the store (survive restart): 30/hour, 6 waiting+running per hook, 256 MB disk cap (503) | `Store.ingest` |
| Worker: claim with lease (120 s, heartbeat 30 s) and fencing number | `Store.claim/heartbeat/mark_dispatched/finish`, `WebhookFeature._pump_loop/_run_claimed` |
| Dispatch recorded before the runner is called | `Store.mark_dispatched` |
| Recovery of expired leases: before dispatch -> queued again; after dispatch -> `unknown` | `Store.recover`, `WebhookFeature.sweep` (startup + every 30 s) |
| Failure before dispatch: backoff 5/30/120 s, `dead` after 3 tries | `Store.requeue_before_dispatch` |
| Runner returned an error: `failed`, retried only by the owner | `WebhookFeature._run_event`, `Store.retry` |
| Hook deleted or switched off before the run: `dead`, never run | `_run_event`, `Store.forget_hook` |
| Permission: instruction from the snapshot taken at receipt; level = lower of snapshot and the hook's current level | `_run_event` |
| Owner notice after commit, resent at the next sweep if a crash cut it, dedup key `wh:<hook>:<event>` | `_notify`, `Store.unnotified` |
| Event log API (keyset pagination, no bodies in lists) | `GET /webhooks/events`, `GET /webhooks/events/{id}` |
| Owner actions | `POST /webhooks/events/retry`, `POST /webhooks/events/resolve` (unknown -> done/failed) |
| Dashboard: per-event state, Retry (with a warning), Mark done for unknown, older runs page by page | `dashboard/webhooks.js` |
| Retention: finished events 30 days and 500 per hook; `unknown` kept until resolved | `Store.prune` (hourly) |
| Migration: `seen_keys` from `webhooks.json` imported once as duplicates; the JSON keeps them | `WebhookFeature._import_legacy` |

States: `queued -> running -> done | silent | waiting | failed | unknown | dead`.

## Invariants and their proof

| Invariant | Test (tests/python/test_webhook_store_m1.py unless noted) |
|---|---|
| No ACK and no dedup before the commit | child process killed at `before_commit`: no event, no key; retry gets 202 |
| ACKed event survives a crash before the ACK reaches the sender | child killed at `after_commit`: event and key stored; retry is a duplicate |
| One key accepted once under concurrency | 8 threads and 5 separate processes, one key: exactly one 202 |
| A refused event keeps nothing (the 429 bug) | `test_webhook_triggers_0198.py`: rate 429, backlog 429, retry runs; red on 0.228.0 |
| Limits are not lost by a restart | rate/backlog counted from the store; disk cap -> Busy, nothing stored |
| Two workers never run one event | two `Store` connections on one file, two threads |
| A stale worker cannot write | lease expired and taken over: old fence refused for dispatch, finish, heartbeat |
| No blind retry of a possibly-applied effect | child killed at `after_dispatch` after a fake outside effect: event `unknown`, not re-run, owner told; resolve/retry via routes |
| Retry of the failed branch only | a failed run is not retried alone; owner retry runs it once more; done is not retryable |
| Permissions of now | waiting event received at `full` runs at the hook's new `suggest`; deleted hook -> `cancelled` (0.274.0: a dead event is kept for a retry a deleted hook can never get) |
| Notice not lost | finished-but-unnotified event notified at the next sweep, once, with its own dedup key |
| No model in the webhook core | source check (no engine imports); runners are fakes; `JAVIS_NO_REAL_JUDGE_ENGINE=1` |
| UI | `tests/js/test_webhooks_ui_m1.js`: actions per state, escaping, both languages |

## Assumptions to reconcile with the spec

1. **State names** `queued, running, done, silent, waiting, failed, unknown, dead`. The spec may name them otherwise.
2. **No automatic retry after dispatch** for task/workflow runs (a model run may have sent messages). Only failures
   before dispatch retry on their own. If the spec defines retryable error classes for dispatch, M3 adds them.
3. **Lease 120 s with 30 s heartbeat**, one event per hook at a time, 4 hooks in parallel per process.
4. **Limits**: kept at the 0.198.0 values (30/hour, 6 per hook) plus a 256 MB store cap. M5 makes them configurable.
5. **Dedup scope** `(hook, Idempotency-Key | X-Request-Id)`, kept until the event is pruned (30 days). Business keys
   (typed, namespaced, TTL) are M2.
6. **Snapshot** keeps `name, brain, target, workflow, text, level, chat_id` and a revision hash; the level used is the
   lower of snapshot and current.
7. **Retention** 30 days / 500 finished events per hook; `unknown` kept until resolved.
8. **Owner notice** policy unchanged (every non-silent result). `all / errors_only / daily_digest / none` is M5.

## Rollback

- Code: revert the 0.274.0 commits. The old version ignores `webhook_events.sqlite3` and works from `webhooks.json`.
  Each accepted idempotency key is still mirrored into the hook's `seen_keys` (last 50) and `count`/`last_status` are
  still updated, so the old version keeps recognising recent duplicates. Per-run `history` is no longer written to the
  JSON (it lives in the store), so after a rollback the old cards show the history they had before the upgrade.
- Events still `queued` or `unknown` in the store at rollback time are not run by the old version: list them first with
  `GET /webhooks/events?status=queued` and `?status=unknown`.
- Data: deleting `STATE_DIR/webhook_events.sqlite3*` with the server stopped resets the log; nothing else depends on it.

## Independent review (M1)

An independent review of the first M1 commit found 2 P1 and 5 P2 issues, all fixed with regression tests in
`test_webhook_store_m1.py` (section "review fixes"), red on the reviewed commit:

| Finding | Fix |
|---|---|
| P1 disk cap measured file size, never shrank: store refused forever after filling | live size (`page_count - freelist_count`), `journal_size_limit`, checkpoint after prune, eviction of oldest finished events (bodies first) before refusing; bodies of finished events emptied after 7 days |
| P1 retry result never reached the owner (same notice dedup key) | dedup key names the attempt: `wh:<hook>:<event>:<fence>` |
| P2 one long run delayed other hooks; P2 kick lost during a claim | pump woken by an `asyncio.Event` while runs are active; flag cleared before each claim |
| P2 heartbeat or finish error lost a known result | heartbeat logs and continues; finish retried with backoff; a refused finish keeps the run's result on its attempt (`late_result`) |
| P2 `-wal`/`-shm` world-readable | file created 0600 before SQLite opens it |
| P2 store calls on the event loop, reads outside the lock | reads under the store lock; list/delete/sweep/wait_idle in threads; a post-commit error no longer turns a 202 into a 500 |
| P3 (fixed) | fenced calls require a live lease; any running row blocks its hook; COMMIT failure rolls back; recover() stops after 3 losses before dispatch; retry resets tries; failed notices retried 3 times; dedup keys kept 7 days by age; legacy import retried if the JSON is unreadable; list results trimmed; worker id not exposed; unknown count over the whole log in the UI; error codes in words |
| P3 (kept, noted) | an edited instruction does not apply to events already waiting (snapshot by design; the permission level does apply); rotating a token does not cancel events already received; `incident_hook` on failed task/workflow runs predates M1 and only concerns AI runs (non-AI actions from M3 must not call it) |

## Not in M1 (later milestones)

Filters and mapping, business keys, simulation (M2); HTTP forward, Apps Script, plugin handlers, fan-out (M3);
per-provider signature verification, encrypted secrets, tool actions (M4); notification modes, quotas, AI budget,
circuit breaker, export, full dashboard log (M5).
