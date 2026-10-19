# Webhook event platform (0.233.0): index and requirements matrix

**The spec of record, `docs/superpowers/specs/2026-10-19-webhook-event-platform-design.md`, is not in the repository**
(checked on all remote branches). Everything here was built from the owner's brief. Each milestone doc lists its
"Assumptions to reconcile" with the spec. None of this was run against a real source: see `staging-pilot-pack.md`.

| Doc | What |
|---|---|
| `m1-durable-ingest.md` | durable SQLite store, ACK after commit, lease/fencing, recovery, unknown/dead, the 429 fix |
| `m2-rules-and-simulation.md` | schema, filter, mapping, typed/namespaced business keys with TTL, simulation, trace |
| `m3-actions-and-delivery.md` | HTTP forward, Apps Script with receipt, plugin handlers, branches, delivery ids |
| `m4-security.md` | per-provider signatures, encrypted secrets with rotation, tools via dispatcher, approval |
| `m5-operations.md` | notification modes, quotas, AI budget, circuit breaker, retention, export, dashboard log |
| `poscake-migration.md` | POSCake migration and rollback (contract not guessed) |
| `staging-pilot-pack.md` | staging and pilot steps with pass criteria (prepared, not run) |
| `huong-dan-su-dung.md` | user guide (Vietnamese) |

## Requirements matrix (from the brief)

Status: **done** = built and proven with fakes; **open** = needs a real source or the spec.

| Requirement | Where | Proof | Status |
|---|---|---|---|
| Durable SQLite, ACK after commit | `webhook_store.ingest` | crash before/after commit in a child process | done |
| Worker lease, fencing, recovery | `claim/heartbeat/recover`, branch writes fenced | two workers, stale fence refused, takeover stops the old run | done |
| dead / unknown states | `recover`, `finish` | crash after dispatch, unknown not re-run | done |
| 429 keeps no seen key | `ingest` (key in the same transaction) | `test_webhook_triggers_0198.py` | done |
| Schema filter and mapping, no eval | `webhook_rules.py` | source check, hostile payloads (`test_webhook_m2_review.py`) | done |
| Simulation | `POST /webhooks/simulate` | no write, no run, no send; replay of a logged body | done |
| Business keys with type, namespace, TTL | `biz_keys`, `_key_value` | cross-brain, TTL, concurrency (threads and processes), crash | done |
| Trace | `events.trace`, Details | detail route, UI | done |
| HTTP forward | `run_http` | outcome per status, SSRF guard, secrets bound to the target | done |
| Apps Script redirect and receipt | `run_apps_script` | 302 echo GET, sign-in redirect, receipt checks | done (fakes); open (real deployment) |
| Plugin handlers, completed/accepted, stable delivery id | `register_webhook_handler`, `run_plugin` | host registry per brain, own thread pool | done |
| Independent multi-action, retry only the failed branch | `branches`, `summarize`, `retry` | owner retry runs only the unknown branch, same delivery id | done |
| Per-provider verification | `webhook_verify.py` | Stripe, GitHub, Shopify, HMAC: done (spec); Systeme.io | open (unverified) |
| Systeme.io own normalisation | `normalize("systeme_io")` | synthetic fixture | open (real delivery) |
| POSCake contract not guessed | `validate` refuses `poscake` | test | done (not built by design) |
| Encrypted secrets, key rotation | `webhook_secrets.py` | AES-GCM, AAD, rotation cut midway, env key | done |
| Tools via dispatcher | `_webhook_call_tool` (hub route) | fake dispatcher; level passed | done (fake); open (real tool on staging) |
| Idempotency | dedup + provider delivery id + delivery ids | duplicates in every path | done |
| Approval | branch `approval`, `POST /webhooks/events/approve` | approve, reject, twice, level lowered | done |
| Notifications all/errors_only/daily_digest/none | `_notify`, `_digest` | per mode, digest once a day, no model | done |
| Quotas | `limits` | hour/day/backlog 429, nothing stored | done |
| AI budget | `ai_per_day` | refused before dispatch | done |
| Circuit breaker | `breakers` | open, pause without tries, notice once, close | done |
| Retention and export | `prune(keep_days)`, export route | per-hook retention, JSONL/CSV without secrets | done |
| Paginated dashboard | keyset `page`, filter, Details | UI tests | done |
| Migration and rollback | each doc's Rollback, `poscake-migration.md` | schema upgrade v1 to v6 in place, concurrent upgrade | done |
| No model on non-AI paths | source checks, runners that raise if called | every milestone | done |
| Benchmarks | `test_webhook_ops_m5.py`, rules benchmark in M2 | printed numbers | done |
| Independent review per milestone, P1/P2 resolved | review tables in the M1 to M5 docs | regression tests red on the reviewed commits (`test_webhook_m2_review` to `m5_review`) | done for M1 to M5 |
| Production verified adapters | | | open: needs real deliveries (staging pack) |

## Whole-chain review (M1 to M5 together)

After the per-milestone reviews, an independent review of the whole chain at 787dfbf6 looked for interactions
between milestones. It found 1 P1, 5 P2 and 8 P3 issues, all fixed. The regression tests are in
`tests/python/test_webhook_chain_review.py`.

| Finding | Fix |
|---|---|
| P1 the hook's own sealed reference, sent back with a new address, carried the key along | a reference sent by a client is treated like the mask (same target only), and a made-up one is refused |
| P2 a workflow question left an event `waiting` forever; with no cap, the shared store could fill (503 for every brain) | Mark done closes `waiting` events; approvals and questions expire after 14 days; at most 200 unsettled events per hook (then 429 for that hook only) |
| P2 the M1 poison guard no longer worked once every event has branches | tries kept across losses before any dispatch: dead after `MAX_AUTO_TRIES` |
| P2 an unreadable `webhooks.json` turned accepted events into "hook deleted" and let `create()` wipe the other hooks | `_load` raises on a read or parse error. Events wait (retried with backoff), receive answers 503, create and update refuse |
| P2 the AI branch of a hook whose brain folder is gone ran in the default brain | refused before dispatch (`brain_exists`) |
| P3 (fixed) | incident triage only for an AI branch dispatched in that pass; header values with surrounding spaces refused; the approval request is sent at once (one dedup key with the event's notice), and an approved branch runs at once; a failed event whose business key is live is not pruned or evicted; 4xx refusals do not open the breaker; keys echoed by a receiver are redacted from receipts; the body size is checked before reading; `digest_try` keys removed with the hook |
| P3 (kept, noted) | while a breaker stays open, its parked events are claimed and parked again each cycle (extra `attempts` rows, no extra sends) |
