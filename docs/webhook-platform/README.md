# Webhook event platform (0.274.0): index, requirements matrix, evidence

**Spec of record:** `docs/superpowers/specs/2026-10-19-webhook-event-platform-design.md` (committed a6132b9f). Every
section below names the spec section it answers. The gap analysis made before the spec work is
`spec-gap-analysis.md`; every row of it is closed by the matrix below or listed as open.

**Status words.** **done**: built, and proven through the real router or host with a temporary SQLite store and fake
HTTP, plugin, tool and model runners (a fail-fast guard makes every real model path raise). **open**: needs a real
source or the owner's data (spec §16.6, §17), prepared in `staging-pilot-pack.md`. **deviation**: built differently
from the spec's wording, with the reason. No adapter or action is marked "production verified": none was run against a
real source.

| Doc | What |
|---|---|
| `huong-dan-su-dung.md` | user guide (Vietnamese) |
| `poscake-migration.md` | POSCake cutover per §16, and how to go back |
| `rollback.md` | rolling the binary back (§13), what it keeps and what it cannot undo |
| `staging-pilot-pack.md` | staging and pilot: SHA, fixtures, budget, stop and reconcile steps (prepared, not run) |
| `m1-durable-ingest.md` to `m5-operations.md` | design notes per milestone, written before the spec arrived; each opens with what the spec changed |
| `spec-gap-analysis.md` | the gap list against the spec, before the alignment work |

**Main suites.** `tests/python/test_webhook_spec_matrix.py` walks every §15 row and §16.1, 2, 4, 5, 7 (row names start
with `§15 <group>` or `§16.n`). The milestone suites (`test_webhook_store_m1`, `rules_m2`, `m2_review`, `actions_m3`,
`m3_review`, `security_m4`, `m4_review`, `golden_signatures`, `ops_m5`, `m5_review`, `chain_review`,
`triggers_0198`) keep their deeper cases. `test_webhook_spec_review` pins every finding of the reviews of the spec
alignment. `test_webhook_bench_short` runs the §16 benchmark briefly.
`tests/js/test_webhooks_ui_*.js` cover the dashboard, `test_webhooks_ui_spec.js` the §12 layout.

## Requirements matrix

### §3 Guarantees

| Requirement | Code | Proof | Status |
|---|---|---|---|
| No ACK and no dedup key before a durable commit | `Store.ingest` (one transaction: event, delivery key, receipt) | matrix "§15 Lưu bền" (child process killed before and after the commit) | done |
| No exactly-once promise; receipts and reconciliation | `receipts`, `delivery_attempts`, unknown state, export | matrix "§15 Plugin", "§15 Apps Script", staging pack "reconcile" | done |
| A successful delivery is never run again | `Store.retry` (failed ones only), `replay` (new generation, preview names repeats) | matrix "§15 Fan-out", "§15 Replay" | done |
| Snapshot by revision, permissions checked now | `hook_rev` on the event; the worker reads the hook's CURRENT level; retry safety and a plugin's AI grant (`allow_ai`) must hold both when the event arrived and now | `test_webhook_m3_review` "restoring the level runs the blocked deliveries again"; review "R6 P2-3" | done |
| No cookie or token forwarded; no escalation; no cross-brain or plugin leak | `run_http` header allowlist, `plugin_precheck`, tool level from the hook | matrix "§15 Chuyển tiếp", "§15 Plugin", "§15 Tool" | done |
| Non-AI paths never build or call a model, triage and notices included | worker: model only for `kind: ai`; triage only with `ai_triage` | matrix "§15 Không AI", bench guard plus its negative control | done |

### §4 Storage and ingress

| Requirement | Code | Proof | Status |
|---|---|---|---|
| Tables: hooks, revisions, events, receipts, deliveries, attempts, notifications outbox, audit | `webhook_store.py` schema v7, `foreign_keys=ON` | `test_webhook_store_m1` (upgrade in place, concurrent upgrade) | done |
| Order: auth, then size, then read the stream under the cap, then commit, then 202 | `hooks_receive` | `test_webhook_m5_review` "without a valid token the body is never stored"; matrix "§15 Nhận body" | done |
| 202 means stored, shape `{accepted, event_id, state: "received"}` | `hooks_receive` | matrix, `test_webhook_triggers_0198` | done |
| Refusals keep nothing: 429 with `retry_after`, 503 `store_full` / `store_busy` with Retry-After | `Store.ingest`, `js()` | matrix "§15 Lưu bền" (disk reserve), "§15 Tải" (SQL busy, byte quota) | done |
| Busy timeout finite (5 s), WAL counted, checkpoint before refusing for space | `Store._connect`, `used_bytes`, `make_room` | `test_webhook_spec_review` "§4: busy timeout is finite..."; matrix "§15 Tải" (SQL busy answers 503) | done |

### §5 Filters and normalisation without a model

| Requirement | Code | Proof | Status |
|---|---|---|---|
| Strict types (`1` is not `"1"`), missing is not null, explicit `as` conversion | `webhook_rules.eval_condition` | matrix "§15 Filter" | done |
| `[*]` paths with quantifier any / all; `case_sensitive`; empty arrays | `_match_path` | matrix "§15 Filter"; `test_webhook_rules_m2` | done |
| A wrong rule refused at save, never match-all at run time (quarantine) | `validate`, `evaluate_closed` | matrix "§15 Filter: a wrong rule..." | done |
| Limits: 100 nodes, depth 8, JSON depth 64; no eval | `validate`, `parse_payload` | `test_webhook_rules_m2`, `test_webhook_m2_review` (hostile payloads, source check) | done |
| Reason codes, stored trace without values, values only in a simulation | `trace`, `reveal=True` | `test_webhook_ui_spec.js` (no placeholder value), matrix | done |
| Simulation writes nothing, runs nothing, holds no key | `POST /webhooks/simulate` | `test_webhook_rules_m2` | done |

### §6 Duplicates at two levels

| Requirement | Code | Proof | Status |
|---|---|---|---|
| Delivery duplicates: sender header (`h:`) or provider id (`p:`), per hook | `dedup` table, `Store.ingest` | matrix "§15 Chống trùng: ten concurrent requests" | done |
| The 429 bug: a refused request keeps no key | same transaction | matrix "§15 Chống trùng: the 429 case" | done |
| Business key: typed tuple, hashed (sha256), scope `hook:<id>:v<n>` or `ns:<ns>:v<n>`, TTL, missing parts quarantine or accept, test events apart | `biz_key`, `triage_commit` | matrix "§15 Chống trùng" (three rows) | done |
| Out-of-order and version handling stays with the plugin (§11) | documented | | done (by design) |

### §7 Durable worker and retry per action

| Requirement | Code | Proof | Status |
|---|---|---|---|
| Lease and fencing; two workers never run one delivery | `claim`, `fence` | matrix "§15 Phục hồi"; `test_webhook_store_m1` | done |
| Retry 1, 5, 30 minutes, jitter ±20 %, 4 attempts, 24 h deadline, Retry-After inside the deadline | `webhook_worker.RETRY_*`, fake clock and RNG | matrix "§15 Retry" (four rows) | done |
| Retry safety: `manual_on_ambiguous` (default), `idempotent`, `at_least_once`; ambiguous results become unknown | `retry_safety`, `_outcome_of` | matrix "§15 Retry: a 5xx ... is unknown" | done |
| States: pending, running, retry_wait, succeeded, accepted, unknown, blocked, waiting, dead, cancelled (spec words in the UI and notices) | `spec_delivery_state`, `spec_event_state` | `test_webhook_ui_spec.js`, `test_webhook_m3_review` | done |
| `depends_on` (acyclic, on succeeded or accepted) | `dep_state`, `summarize` | `test_webhook_actions_m3` | done |

### §8 Actions

| Requirement | Code | Proof | Status |
|---|---|---|---|
| 8.1 HTTP forward: raw bytes and content type, `X-Javis-Event-Id`, no sender cookie or token, SSRF guard with pinned connections, redirects not followed | `run_http`, `_pinned_backend` | matrix "§15 Chuyển tiếp" (DNS rebinding included) | done |
| 8.1 A name that does not resolve is retried (nothing sent) | `_refused` | matrix "§8: a name that does not resolve" | done |
| 8.1 Apps Script profile: echo hop checked, receipt required, sign-in page is blocked, `delivery_ref: query` | `run_apps_script` | matrix "§15 Apps Script" (two rows) | done (fakes); open (real deployment) |
| 8.2 Plugin contract: completed, accepted, retryable_error, permanent_error, unknown, waiting_approval; same delivery id gives the same job | `run_plugin`, `register_event_handler` | matrix "§15 Plugin" (three rows) | done (fake plugin); open (poscake-zalo, §17) |
| 8.2 A slow plugin cannot take every worker | own thread pool (`PLUGIN_THREADS`), `_INFLIGHT` | matrix "§15 Tải: a hook stuck on a slow run" | done |
| 8.3 Tool through the hub dispatcher at the hook's level, typed templates, payload cannot pick the tool | `run_tool`, `tool_args` | matrix "§15 Tool" | done (fake dispatcher); open (real tool on staging) |
| 8.4 AI task or workflow: quota waits, a lost dispatch is not run twice, a partial result is not done | worker AI path | matrix "§15 AI" (three rows), "§15 Chờ chủ" | done |
| 8.5 One hook, many actions (up to 10), each independent | `plan_deliveries` | matrix "§15 Fan-out" | done |

### §9 The POSCake sample configuration

| Requirement | Code | Proof | Status |
|---|---|---|---|
| The spec's own action format is read: `type: http_forward`, `body_mode`, `redirect_profile`, `retry_safety`, `delivery_ref` | `webhook_actions.validate` aliases | `test_webhook_actions_m3` "the spec's own action format (§9) is read" | done |
| The real POSCake payload, headers, status meanings | | | open (§17, owner data) |

### §10 Source verification and secrets

| Requirement | Code | Proof | Status |
|---|---|---|---|
| Profile per source, never one shared formula; the payload cannot pick the algorithm | `webhook_auth.verify_ex` | `test_webhook_golden_signatures`, matrix "§15 Provider" | done |
| Generic token: header of the owner's choice or Bearer; `?token=` only for older hooks; the header cannot be one Javis stores | `token_from_request`, `allow_query`, `token_header_name` | matrix "§10: a NEW hook does not accept the token in the URL"; review "R2 P3" | done |
| A provider-checked hook is authenticated by the provider's signature (the provider cannot add the Javis token); the token never bypasses the signature | `authorize`, `accept_body` | review "R2 P2-5" (real router, signed GitHub delivery) | done |
| GitHub hex `sha256=`, Shopify base64 over raw bytes (id from `X-Shopify-Event-Id`, else `Webhook-Id`), Stripe timestamp with several signatures and tolerance | `webhook_auth.py` | matrix "§15 Provider", "§15 Xác thực" | done (spec); open (real deliveries) |
| Systeme.io: `X-Webhook-Signature` over Systeme's normalised JSON, dedup on `X-Webhook-Message-Id` | `systeme_forms` (raw, php_default, php_unescaped) | synthetic fixtures `systeme_io_synthetic_*` | open: `unverified` until a real delivery (the docs site was unreachable from the build session) |
| POSCake: no preset until its contract is known | `validate` refuses `poscake` | test | done (not built, by design) |
| Encrypted secrets referenced from the config; a missing key blocks with a clear error | `webhook_secrets.py` (AES-256-GCM, name as associated data) | `test_webhook_security_m4`, `test_webhook_m4_review` | **deviation**: the spec names `secrets_store.encrypt_required()`. That store has one Fernet key and no rotation, and the spec also asks for rotation with a key version: a dedicated vault does both. Same rule: no plain secret on disk, no fallback that skips the check |
| Two keys during a bounded overlap (`overlap_h` 1 to 168, default 24); key version and verification time stored | `previous_secret`, `key_version`, `verified_at` | matrix "§15 Xác thực" | done |
| Replay never fakes a new signed request | `replay_confirm` works on the stored, verified event | matrix "§15 Replay" | done |

### §11 Resource limits and fairness

| Limit | Value | Proof | Status |
|---|---|---|---|
| Body per hook / ceiling | 256 KiB / 2 MiB, read as a stream | matrix "§15 Nhận body" | done |
| Valid ingress per hook | 300 per minute, burst 100 per 10 s; optional per hour and per day | `test_webhook_ops_m5` | done |
| Unauthenticated requests | 30 failures per minute per address (the forwarded address behind a local or private proxy); a valid token always passes | review "R3 P2-3" | done |
| Backlog per hook | 10,000 events or 256 MiB, whichever first, refused before any key is held | matrix "§15 Tải: the byte quota" | done |
| Whole store | 1 GiB including the WAL, 128 MiB of free disk kept | matrix "§15 Lưu bền: store full" | done |
| AI per hook | 30 per hour by default, optional per day, 300 per hour across hooks, durable counter; past it the event waits | matrix "§15 AI / §16.4" | done |
| Concurrency | one EVENT at a time per hook (its deliveries run side by side); a pool of 4 events per process, oldest first, at most 3 of them for hooks with an AI action (or a plugin allowed to use AI), so a code-only hook always finds a slot; a plugin holds at most 2 threads, and a full pool costs no attempt | matrix "§15 Tải: a hook stuck..."; review "R2 P2-4", "R6 P2-10" | done |
| Raw payload / metadata / dedup | body 7 days after it settles; unknown, waiting, blocked, failed and dead keep theirs until the owner settles or deletes the event (counted in the byte quota); mapped fields go with the body; metadata 30 days; delivery keys 7 days, never dropped younger under disk pressure | matrix "§15 Tải: retention never deletes pending"; review "R3 P1-1", "R1 P2-6" | done |
| Breaker per target and credential | `target_key` | `test_webhook_ops_m5` "the breaker is per target" | done |
| Expiry | `expire_after_h`, ends `dead` with an audit line | `test_webhook_m5_review` | done |

### §12 Log, notifications and the page

| Requirement | Code | Proof | Status |
|---|---|---|---|
| Three parts: Configuration, Events, Health, in one popup per hook (0.432.0) that stays open until closed; a new hook opens on Configuration, one with runs on Events; simple setup first, advanced behind a button | `dashboard/webhooks.js`, `dashboard/webhooks.css` | `test_webhooks_ui_spec.js`, `test_webhooks_ui_0432.js`; `tools/webhook_ui_narrow_check.mjs` at 390 px | done |
| Timeline per event (received, verified, parsed, filter, duplicate, dispatch, attempt, receipt, result, notice) | `timeline()` | matrix "§16.5" | done |
| Cursor pages, filters by hook, state, order or correlation id, time range; never the whole DB in memory | `Store.page` (keyset), `/webhooks/events` | `test_webhooks_ui_m1.js`, `test_webhooks_ui_spec.js` | done |
| Test send: the owner's payload, the list of effects first, a test namespace, same permissions and quotas | `test_send` | matrix "§15 UI"; `test_webhooks_ui_spec.js` | done |
| Retry keeps the delivery id and snapshot, re-runs dependents a failure cancelled, never sends an empty body; a failed event can also be closed without resending | `Store.retry`, `Store.resolve`, `close_failed` | matrix "§15 Apps Script: the owner's retry sends the same delivery id"; review "R2 P2-2", "R3 P1-1" | done |
| Process again with the current setup: a new generation under the current revision; the preview names every delivery that may act again (succeeded or unknown), and a confirm after the hook changed is refused | `replay_confirm`, `Store.replay` | review "R2 P2-1", "R6 P2-6" | done |
| A block fixed outside the hook (plugin switched back on, key changed at the receiver) runs again from Retry all blocked; a fix in the hook runs it by itself | `Store.unblock`, `/webhooks/events/retry_blocked` | review "R6 P2-4" | done |
| A test event is marked for the receiver: `_javis.test` in the envelope, `X-Javis-Test: 1` on every HTTP call, `javis_test=1` for Apps Script | `_headers`, `target_url` | review "R6 P2-7" | done |
| Raw view and export masked by default (payload, fields, headers, trace, result, error, correlation, deliveries, timeline, list rows, tool arguments), raw always audited (view, export with or without bodies, simulation of a logged event) | `mask_row()`, `/webhooks/audit` | matrix "§15 UI ... customer data masked"; review "R3 P2-5", "R3 P2-6", "R1 P2-5", "R6 P2-5" | done |
| Pause processing vs stop receiving, two switches | `pause()`, `enabled` | `test_webhooks_ui_spec.js`; `test_webhook_ops_m5` | done |
| Notify modes; older hooks keep `all`, new non-AI hooks start `errors_only` | `create()` | `test_webhook_ops_m5` | done |
| Digest by code in the owner's time zone, one per period, at most one catch-up after a restart; a failed notice is retried alone | outbox `dkey` UNIQUE | matrix "§15 Thông báo" (two rows) | done |
| `none` keeps system alerts; `errors_only` groups failures, blocks and unclear outcomes into incidents; `ai_triage=false` blocks the triage model | `deliver_notifications`, `inc:<hid>` | `test_webhook_ops_m5`, `test_webhook_m5_review`; review "R3 P2-4" | done |
| Health figures; "202 received" never shown as processed | `health()`, `healthHtml` | `test_webhooks_ui_spec.js` | done |

### §13 Modules and compatibility

| Requirement | Code | Proof | Status |
|---|---|---|---|
| Module split: triggers (routes), store, rules, auth, worker, actions, plugins_host | as named; `webhook_verify.py` is a re-export shim | | done |
| Migration of `webhooks.json` once, idempotent, with a snapshot and a marker; older hook = one AI action, no filter added, level kept | `_migrate_json` | matrix "§15 Tương thích: migrating twice" | done |
| Public `POST /hooks/{id}`, admin under `/webhooks/...` behind the login | `main.py` wiring | matrix "§16.7" (real host, `JAVIS_REQUIRE_LOGIN=1`) | done |
| Old `seen_keys` kept as legacy keys with their age | `import_hooks` | `test_webhook_store_m1` | done |
| Rollback: stop, export the backlog and hold it, write a legacy config, say what will not run; the new store kept; the next upgrade restores each hook's own switches | `server/webhook_rollback.py`, `rollback.md` | matrix "§15 Tương thích / §13"; review "R1 P2-2 / R3 P1-2" | done |

### §14 Delivery order

| Requirement | How | Status |
|---|---|---|
| One PR per milestone under a reserved version | **deviation**: the session was bound to one branch, so PR #747 holds commits grouped by milestone (M1 to M5, then the spec alignment), one version 0.274.0 | deviation (explained in the PR) |

### §15 Test matrix

Every row is a named section of `test_webhook_spec_matrix.py`: Lưu bền (3), Phục hồi, Chống trùng (5), Filter (2),
Nhận body (2), Xác thực (2), Provider, Chuyển tiếp (3), Apps Script (2), Retry (4), Fan-out, Plugin (3), Tool, AI (3),
Chờ chủ, Không AI, Replay, UI, Thông báo (2), Tải (4), Tương thích (3). Crash rows run in child processes that stop at
named crash points (`JAVIS_WH_CRASH_AT`). Narrow screens and languages: `test_webhooks_ui_spec.js` (every key in vi and
en), `test_i18n.mjs`, and `tools/webhook_ui_narrow_check.mjs` (390 px, no sideways scroll, nothing under 16px).

### §16 Acceptance

| Criterion | Proof | Status |
|---|---|---|
| 1. Every 202 found after a restart with a final or waiting state | matrix "§16.1"; benchmark (1,200 of 1,200) | done |
| 2. No model for non-matching data, duplicates, rule errors; no hidden triage on non-AI branches | matrix "§16.2", "§15 Không AI"; benchmark guard 0 with a positive control | done |
| 3. Retry and replay never repeat a success; unclear outcomes stay unknown | matrix "§15 Replay", "§15 Retry" | done |
| 4. The AI quota loses no accepted order; a full backlog refuses before holding dedup | matrix "§15 AI / §16.4", "§15 Tải" | done |
| 5. The timeline explains why it ran and which handler took it | matrix "§16.5" | done |
| 6. POSCake to Apps Script and to the plugin with masked real fixtures and staging receipts | `staging-pilot-pack.md` steps 3 and 5; `tools/webhook_capture.py` turns captured deliveries into masked fixtures and checks the rules against them (`test_webhook_capture.py`) | **open** (the tooling is ready; it needs the owner's data and a staging run with a public address. Parts 1, 2 and 4 of the pack passed on the real host locally, 14 of 14: `tools/webhook_staging_rehearsal.py`. How to capture POSCake deliveries: `huong-dan-gui-du-lieu-poscake.txt`. First real delivery captured 2026-10-22 (`create`): masked fixture, field names and headers in `poscake-migration.md`; still needed: the other events, the status meanings, Apps Script and plugin receipts on a public staging) |
| 7. Older hooks keep working; admin, raw and replay are not public | matrix "§15 Tương thích", "§16.7" | done |

**Benchmark** (`tools/webhook_bench.py`, real HTTP socket, uvicorn in a child process, 4 vCPU build container,
2026-10-19). Spec target: 10 KiB, 5 hooks, 20 requests per second for 60 s, p95 ACK under 250 ms.

| Run | Sent | Answers | ACK p50 / p95 / p99 / max (ms) | Processing p50 / p95 | Model calls |
|---|---|---|---|---|---|
| Fast receiver | 1,200 in 59.96 s | 1,200 × 202 | 4.66 / 6.66 / 9.86 / 48.46 | 0.01 s / 0.01 s | 0 |
| Every action waits 2 s | 1,200 in 59.96 s | 1,200 × 202 | 5.70 / 9.99 / 15.81 / 39.66 | 34.8 s / 65.0 s (backlog by design) | 0 |
| Fast receiver, again at ac47dac1 (2026-10-20, after the R6 and R7 fixes) | 1,200 in 59.96 s | 1,200 × 202 | 4.68 / 6.23 / 10.75 / 59.72 | 0.01 s / 0.02 s | 0 |
| Every action waits 2 s, again at ac47dac1 | 1,200 in 59.96 s | 1,200 × 202 | 5.96 / 10.07 / 15.81 / 75.98 | 34.9 s / 65.2 s (backlog by design) | 0 |

With a 2 s receiver, processing is bounded by one delivery per hook in a pool of 4 (2 per second), so the backlog
grows while ingress stays at the same latency and every event stays stored. This is the build container, not a VPS
measurement: run the same command on the target machine before a cutover.

### §17 Data to settle before real traffic (all open)

The POSCake payload and headers (masked), shop, order and event ids, status meanings, whether it can send a custom
header; what the Apps Script receives and returns, and how it dedups; where `poscake-zalo` keeps its schedule and
whether it returns the same job id for the same delivery id; peak rates, allowed delay, retention and disk budget;
which actions are at-least-once and which must be reconciled before a resend. `staging-pilot-pack.md` says how to
collect each.

## Tests changed because of the spec

These suites were written before the spec arrived. Their checks now assert the spec's behaviour. No check was deleted
to make a run pass, and no threshold was loosened; each change below follows a spec sentence.

| Before | Now | Spec |
|---|---|---|
| HTTP 503 at a receiver: retried | unknown unless the receiver is declared idempotent; 429 is retried | §7 ambiguous outcomes |
| A plugin raising, or answering outside the contract: failed | unknown (it may have acted) | §8.2 |
| Plugin not installed, off, other brain, or level too low: failed | blocked: runs again by itself after a fix in the hook, or from Retry all blocked after a fix outside it | §7 blocked |
| 401 / 403 at a receiver, Apps Script sign-in page: failed | blocked | §7, §8.1 |
| Apps Script: a page that is not a receipt, or a receipt naming another delivery, AFTER the echo hop: failed | unknown (doPost already ran); the same answer on the first hop stays failed. The matrix's "sign-in" case now sends Google's real 302 to accounts.google.com, which is blocked | §7 ambiguous outcomes, §8.1 (review R6 P2-2) |
| A rejected approval: failed | cancelled | §7 |
| Busy after the last try: failed | dead; the event is partial_failed when another delivery succeeded | §7 |
| Retries: the old delays | 1, 5, 30 minutes with jitter, 4 attempts, 24 h | §7 |
| Rules decided before the 202 (filtered events answered 200, deep JSON 422) | every event is stored and answered 202; the worker filters, quarantines or ignores it | §4.2 |
| A switched-off hook ended its waiting events dead | stop receiving refuses new requests only; accepted events still run (pause is the processing switch) | §12 |
| AI budget per day refused the run | the event waits for room within the hour (default 30 per hour) | §7, §11 |
| Backlog cap of 200 unsettled per hook | 10,000 events or 256 MiB, parked ones included | §11 |
| Breaker per hook | per target and credential | §11 |
| Export carried the raw payload | masked by default; raw only with `raw=1`, audited | §12 |
| Business key `{entity, field}` | `{policy_version, business_paths, ttl_s, missing, namespace}` (the old form is converted on load) | §6.2 |
| Systeme.io deduped on the attempt id | on `X-Webhook-Message-Id`; the golden fixtures gained the two PHP-style forms | §10 |
| 307 / 308 after a POST: failed | unknown, like every redirect after a POST | §7 (review R2 P3) |
| `allow_private` opened every address | link-local and cloud metadata addresses stay refused | §8.1 (review R2 P3) |
| A number out of range (`1e400`, NaN) was kept as text, so a filter on it was filtered | quarantined as `number_out_of_range` | §5 (review R1 P3) |
| Hung handlers filled the whole plugin pool | one plugin holds at most 2 threads; its extra calls wait without spending an attempt | §11 (review R2 P2-4) |
| Notices named the internal states | the spec's words (succeeded, waiting...) | §12 |
| The 0.198 log answered 200 on duplicates without an event id | 200 with the event id | §4.2 |
| Quarantined events never notified the owner (`test_webhook_rules_m2`) | a quarantine is told once, grouped under `errors_only`; ignored events (filtered, duplicate) still are not | §7 table "payload/schema/filter wrong" is an error, §12 (review R8 P2-3) |
| The masked export showed the value of a generic field (`"n": 1`, `test_webhook_ops_m5`) | the key is shown, its value hidden: payloads are masked by allowlist (review R13) | §12 masked by default |
| Deleting a hook made its waiting events dead | cancelled: a dead event keeps its body for the owner's retry, which a deleted hook can never get, so its customer data stayed forever | §11 retention (review R7 P2-3) |

One more edit is not a behaviour change: the stub of `Store.claim` in `test_webhook_store_m1` ("a kick that lands while a
claim is in flight") takes the new `avoid` argument (R6 P2-10). The Apps Script check in the matrix now also counts
rows before the owner's retry and asserts the retry added none, instead of a fixed total.

## Reviews

Milestone reviews (M1 to M5) and the whole-chain review at 787dfbf6 were made against the brief, before the spec.
Their findings and regression tests stay valid and are listed in each milestone doc and in
`test_webhook_m2_review.py` to `test_webhook_chain_review.py`.

The spec alignment was reviewed by three independent reviewers at 11f6ee8e: R1 the store and rules (M1, M2), R2
delivery and security (M3, M4), R3 operations, the UI and the whole chain (M5). Every finding was fixed in 190eadf6,
pinned by `test_webhook_spec_review.py`, and that file was run against 11f6ee8e to confirm each pinned check was red
there (13 failures or hangs). A fourth reviewer (R4) then reviewed the fix commit itself; its findings are fixed in
4537d57f and pinned in the same file. A whole-chain review at 0d02c5ba (R6) found ten P2 issues; each is fixed in the
0.274.0 follow-up commit and pinned in `whole_chain()` of the same file, which was run against the server code of
a79820f2 to confirm the pinned checks were red there. A seventh reviewer (R7) reviewed that fix commit (fc621216):
four P2 and six P3 findings, fixed in the next commit and pinned in `fix_review()`, each red on the server code of
fc621216. Two more reviewers then reviewed the whole chain again at ac47dac1 (R8, M1-M3 and M4-M5 separately): two P1,
eight P2 and their P3 findings, fixed in the next commit and pinned in `chain_review_two()`, each red on the server
code of ac47dac1. A reviewer of that fix commit (R9, at 6d40a873) found one P1 and three P2 in the fixes themselves;
they are fixed in the next commit and pinned in `fix_review_two()`, each red on the server code of 6d40a873 (the P1 row
hangs there, so it was run on its own). The reviewer of that commit (R10, at f4817a74) found one P1 and four P2; fixed
in the next commit and pinned in `fix_review_three()`, each red on the server code of f4817a74 (the re-import row
spins there and was left out of that run). Its reviewer (R11, at a3e2ee07) found no P1 and one P2, fixed next and
pinned in `fix_review_four()`, red on the server code of a3e2ee07. A final reviewer (R12, at 96507d00) found one P1 in
that masking change and no P2; fixed next and pinned in the same function. The review of that fix (R13, at 12b985db)
found the denylist still missing keys, so payload masking moved to an allowlist (pinned in `fix_review_four()`).

| Finding | Fix |
|---|---|
| R1 P1 one event with a lone surrogate stopped triage for every hook | triage guarded per event (quarantined with the fault named); lone surrogates are bad UTF-8 |
| R3 P1 retention emptied failed bodies, then Retry sent an empty body and marked it done | failed and dead bodies kept until settled or deleted; Retry refuses `body_pruned`; owner delete route |
| R3 P1 / R1 P2 rollback then upgrade switched v2 hooks off and re-ran the exported backlog; deleted hooks came back | own switches recorded and restored; exported events held unknown; hooks deleted in the older build stop receiving |
| R2 P2 provider-signed hooks refused real deliveries without the Javis token | the provider signature authenticates; the token never bypasses it |
| R3 P2 junk requests locked out valid senders | valid tokens always pass; per-address throttle on failures only; forwarded address behind a local proxy |
| R2 P2 / R3 P2 replay ran the old revision and cancelled every changed action | replay records the current revision and a fresh retry window |
| R2 P2 retry did not re-run dependents cancelled by a failed dependency | they run again |
| R2 P2 a dependent of a receiver that only accepted the work waited forever | Mark done settles the accepted delivery and releases its dependents |
| R2 P2 a hung plugin exhausted the plugin pool and dead-lettered other plugins | 2 threads per plugin; slot checked before dispatch |
| R1 P2 `not` over a missing field matched; `empty` on `[*]` never passed | three-valued logic; quantifier applied |
| R1 P2 Systeme.io contact data stored in the trace | the trace keeps ids and type; the contact is derived from the body when it runs |
| R3 P2 masked views and exports leaked results, errors, deliveries, timeline | `mask_row` on every dashboard text |
| R3 P2 raw export without bodies and simulation of a logged event were not audited | audited, simulation masked unless raw |
| R3 P2 errors_only sent one notice per blocked or unknown event | grouped into the incident |
| R1 P2 disk pressure dropped delivery keys younger than 7 days | never below their keep time |
| P3 (all fixed) | out-of-range numbers quarantined; 1 and 1.0 one key; NFC compare; retry-safe resends capped; any 3xx after POST unknown; metadata refused with allow_private; token header not a stored header; store faults answer 503; indexes for paging and search; prune in small transactions; ingest re-checks the switch; Stop receiving always saved; catch-up digest from the last cursor |
| R4 (review of the fixes, at 190eadf6) P2 a plugin whose calls hang held its other deliveries forever | the wait for a slot ends at the delivery's deadline: failed, never sent, owner told |
| R4 P2 kept failed bodies could fill the byte quota with no way out | Close (one) and Close all failed (per hook) settle them without resending |
| R4 P2 simulating a logged event revealed values; masking missed texts under a customer block | values only in the raw, audited form; the prompt preview only there; every text under a PII key is masked |
| R4 P3 (all fixed in 4537d57f) | retry window not widened; Stop receiving parses text; prune re-checks status inside the delete; store faults in triage defer; rollback refuses to run twice; a hook stopped mid-ingest does not count against the sender; only failed or dead events deletable; business key texts NFC |
| R6 (whole-chain review at 0d02c5ba) P2 an edit refused for a stale revision had already replaced the live secrets | the revision is checked before any secret is written; a conflict found later puts the old values back |
| R6 P2 Apps Script: an unreadable answer after the echo hop was failed, so Retry wrote a second row | unknown: the script ran, the owner checks the sheet |
| R6 P2 a plugin's AI grant revoked after the event arrived was not checked | the grant must hold then and now, like retry safety |
| R6 P2 a block fixed outside the hook never ran again | Retry all blocked (per hook, audited); the notice says when to press it |
| R6 P2 the correlation value was shown unmasked | masked like every other dashboard text |
| R6 P2 replay preview left out unknown deliveries; a confirm used whatever revision was current | unknown listed as may act again; the confirm carries the previewed revision, 409 when it changed |
| R6 P2 a raw-body test event could not tell the receiver it was a test | `X-Javis-Test` header, `javis_test` query for Apps Script |
| R6 P2 deleting a hook left its unknown, waiting and blocked events where no view shows them; an ingest racing the delete stored an orphan | closed as cancelled with the reason; the ingest refuses (401) |
| R6 P2 a fault in Javis inside one delivery left the event without a settled branch | that delivery is unknown (it may have acted), the others finish |
| R6 P2 hooks with a slow AI action could take every worker slot | at most WORKER_MAX - 1 AI events run at once |
| R7 (review of the R6 fixes, at fc621216) P2 two saves of one hook at once: the losing save's restore put back the key from before both | saves of one hook run one at a time in the process (check, seal, commit); a conflict from another process or a failed commit restores, and a key that cannot be read is never deleted by a restore |
| R7 P2 deleting the last hook left the ingest race open (202 for a deleted hook) | a tombstone per deleted hook; the ingest refuses (401) |
| R7 P2 events queued when their hook was deleted ended dead and were kept forever with their body | cancelled, removed by retention |
| R7 P2 an internal fault before the send marked the delivery "may have acted" | before the dispatch is recorded it is retried within its deadline; after it, unknown |
| R7 P3 (all fixed) | the replay confirm must carry the previewed revision (400 without it, or with a bad one); a correlation is masked like the key it reads (`customer.name`); an Apps Script test event carries `javis_test` even with the delivery id in a header; plugins allowed to use AI count among the AI hooks; the last known AI list keeps the slot protected when it cannot be read |
| R8 (second whole-chain review at ac47dac1, two reviewers: M1-M3 and M4-M5) P1 a dependent waiting on a delivery in retry requeued its event at once: a claim loop writing an attempt row each time (389 in 2 s) | a delivery is due no sooner than what it waits for, down the whole chain |
| R8 P1 rollback left an AI hook with approval or a condition switched on for the older build, which would run it on every event unapproved | an AI action with any field beyond id and kind switches the hook off there |
| R8 P2 replay skipped business dedup: a duplicate replayed sent the order again; a filtered event replayed took no key | the preview names the event holding the key and the confirm refuses; a replay takes the key |
| R8 P2 deleting a partly failed event gave its keys back, so the source's resend ran the succeeded part again | keys are released only when nothing was ever dispatched |
| R8 P2 quarantined events were silent under errors_only and retention wiped them | told (grouped in every mode), body kept for the whole 30-day retention under the per-hook row cap; the owner can delete, replay or close them (R9 corrected the first fix: not exempt from retention, not in the byte quota) |
| R8 P2 `[*]` with known and unknown items gave a definite answer (`not` then matched) | undecided with an unknown item is unknown |
| R8 P2 Retry of an event held at rollback before triage ran every action unfiltered | it goes back through triage |
| R8 P2 errors_only grouped on the receiver's wording (one notice per order id; 502 and 504 alternating) | grouped on the kind of failure (numbers and quoted values removed), every open kind remembered |
| R8 P2 masking missed `ten_khach_hang`, `nguoi_nhan`, `recipient`, `buyer`, numeric CCCD and Zalo ids (view, export, capture fixtures) | the key list widened; numbers under a customer key masked |
| R8 P3 (fixed) | X-Request-ID is a delivery key only for older hooks; the overlap end is Javis's to set and bounded; the failed-auth table forgets finished addresses only; a plugin call that never returned ends unknown at the deadline; a deleted hook's running event dispatches nothing more; Retry all blocked clears the dispatch mark; the incident key is dropped with the hook |
| R8 P3 (kept, noted) | a crash between sealing a rotated signing secret and the commit leaves the new key live without the old one (the provider's in-flight deliveries get 401 and are retried by it); the breaker key is the target plus the secret's name, not its value; GitHub and Shopify delivery ids are not signed, so a captured delivery resent with a new id passes (inherent to those providers); an event whose deliveries all ended `accepted` reads as done, since a plugin's accepted job is its normal success |
| R9 (review of the R8 fixes, at 6d40a873) P1 a chain through a delivery held for approval still spun the event (656 attempt rows in 3 s) | held is transitive down the chain |
| R9 P2 deleting an event every receiver refused (4xx) kept its keys: the resent order was a duplicate of a deleted event | keys are kept only when a delivery succeeded, is unclear, or may have acted |
| R9 P2 quarantine notices: one per event under `all`; a good order between two quarantines re-opened them under errors_only | grouped in every mode, by hook and kind of reason, kept apart from delivery incidents |
| R9 P2 quarantined events were exempt from every retention and counted in the byte quota: a broken rule could refuse every valid order, then fill the store | back under the 30-day retention and the per-hook row cap, outside the byte quota; their body is kept for the whole retention |
| R9 P3 (fixed) | amounts and counts are not masked (only identity numbers: phone, CCCD, Zalo, passport); the incident count resets after each notice; the deleted-hook dispatch check uses the tombstone; rollback ignores empty AI fields; the replay preview judges the business key as the store does |
| R9 P3 (noted) | the three-valued `[*]` logic can now filter an order an older `not(any ...)` filter let through over a sparse array (the changelog says so) |
| R10 (review of the R9 fixes, at f4817a74) P1 deleting an event whose AI run failed mid-turn gave the order back, so a resend called the model again | a failed AI run counts as maybe acted |
| R10 P2 a delivery moved from the v6 store (dispatched, no attempt rows) counted as certainly not acted | dispatched with no attempt rows counts as maybe acted |
| R10 P2 a hook id re-imported after its deletion kept its tombstone: its events were accepted and spun (644 attempt rows in 3 s) | inserting a hook clears its tombstone |
| R10 P2 a quarantine notice that failed to queue was marked told: it and every later one for 6 h were lost | the incident state is written only after the notice is queued |
| R10 P2 numbers under a person's block (so_dien_thoai, dob, id_number, whatsapp) were shown | masked unless the key names an amount or a count |
| R10 P3 (fixed) | a delivery behind a held one and a failed one is cancelled; new rules close the quarantine incident; quarantined events have their own row cap and the recent-event protection; rollback treats 0 as a value |
| R11 (review of the R10 fixes, at a3e2ee07) P2 amount words matched inside other words, so `bank_account`, `account_number`, `tax_code` and `so_giay_to` under a person were shown | amount words match whole words of the key only; bank, account, tax id and document keys are identity numbers, checked first |
| R11 P3 (fixed) | notices of one hook are decided one at a time (read the incident, queue the notice, write the state), so two events failing together are one notice |
| R11 P3 (noted) | a failed AI run that never reached the model (the CLI is missing) also counts as maybe acted: its deleted event keeps the order's key (safe side: no double effect); a crash between queueing a notice and writing the incident state can tell the next failure once more; ids and points under a customer block are masked in the masked view (the audited raw view shows them) |
| R12 (final review, at 96507d00) P1 R11 made `value`, `sum`, `balance` amount words, so a CCCD in a name/value custom field and a phone's `value` showed | generic words are not amounts; an identity key masks every number under it (inherited down the tree); tax numbers are identity keys |
| R12 P3 (fixed) | `tel` matches as a whole word (a hotel is not a phone); notices are sent after the hook's lock is released (the pump never waits behind network sends) |
| R13 (review of R12, at 12b985db) P1 the denylist kept missing keys: `tel1`, `telno`, `telefono` (R12 had made `tel` a whole word), a name/value custom field outside a customer block, a bank account's owner, `ma_so_thue`; the capture tool ignored identity keys | payloads (event body, mapped fields, tool arguments) and captured fixtures are masked by ALLOWLIST: a value is shown only when its key's words say it is safe (ids, statuses, times, amounts, counts, a product's name inside an item list); identity keys and customer blocks win; `keep_leaf` in `webhook_triggers.py` is the one rule both use |
| R14 (review of R13, at 5c6c864b) P1 a kept text came out verbatim, so an e-mail or a phone inside it showed (`client_reference_id`, `metadata.order`); bearer links (`order_status_url`, `hosted_invoice_url`) showed | kept texts still go through the e-mail and phone masking (timestamps stay whole); link keys and any URL with a query string are hidden |
| R14 P2 a captured fixture lost fields the rules read (`mode`, `tags`, `money_to_collect`), so it no longer got the real event's decision | `export --config hook.json` keeps the paths the rules read, never an identity, customer or credential path (listed as `not_kept`) |
| R14 P3 (noted) | an `id` of staff (`creator.fb_id`) and card expiry months under `source` show; numbers on keys not on the allowlist become masked strings in the masked view |
| R15 (review of R14, at c93faa3f) P1 `restore_paths` wrote raw values back: bearer links, customer names, e-mails, and whole objects or lists under a path that ends on one; JSON floats (parsed as Decimals) passed every mask | only a single value is restored, never a link, never under an identity, customer or credential path (`name` only inside an item list), and a kept text still loses e-mails and phones; Decimals are numbers for masking (view and fixture) |
| R15 P2 a payload with a float made the masked detail view answer 500 and the capture export crash; a `$.` path was reported kept but restored nothing | Decimal-safe dumps; paths split by `webhook_rules.parse_path`; actions' `when` paths are read too; form keys split on brackets |
| R16 (review of R15, at 97ffeb10) P1 camelCase identity keys (`nationalId`, `idCard`, `idNumber`) were matched only in snake form; the product context of an item reached every nested object (`line_items[].destination_location.name`) | keys are matched in written, snake and joined forms, with identity words (`identity`, `citizen`, `national`, `id` + card/number); only an item's own fields and its product sub-objects are product; texts are kept only under id, status and time words |
| R16 P2 a restored text the phone masking altered (an EAN barcode, a git tag, a timestamp with an offset) was still listed as kept | such a path is reported as not kept, never written altered; an empty text stays empty |
| R17 (review of R16, at 2fe75507) P1 `restore_paths` judged texts by the denylist: a name under `ho_va_ten` or `ten` and the customer's own words in `message` were written into the fixture | texts are restored by the same allowlist as the scrub; a text a filter compares is written as the OWNER's constant (`eq`/`in` only when it equals one, `contains`/`starts_with` as the constant itself), never as the customer's words; `ho_va_ten`, `ten` and `by` are customer keys |
| R17 P3 (fixed) | a time word keeps only a time (`time_send: "Giao sau 5h tai 12 Le Loi"` is hidden); card fields, `fb_id`, `psid` and `conversation_id` are identity; a timestamp with a spaced offset stays whole |
| Startup (CI `test_khoi_dong_nhe` red on f4817a74, 96507d00, 5c6c864b, 97ffeb10; green on 12b985db, c93faa3f and earlier heads) | `main` registers the webhook routes through `server/webhook_lazy.py`: plain Starlette routes that load the platform at the startup event or the first webhook request; `import main` loads no webhook module (measured idle: branch 3.88, `main` 3.96). `route_table.json` shows these 22 routes as `Route` and one `_IncludedRouter` entry fewer; `test_webhook_spec_review` checks the table matches the feature's routes |
| Full local run at 7e09d529: R4 P2-1 red under load (4 of 6 loops of `second_round` with 6 busy cores) | two deliveries of one plugin could both pass the free-slot check, then one was refused at the call: an attempt spent with nothing sent. The worker now takes the slot in one step with the check, right before the dispatch (`plugin_reserve`), and gives it back if the call never starts. The test also picks the delivery that really waits (claim order across hooks is not fixed). 8 of 8 loops green under the same load |
| Review of the slot reservation (at 346707cf) no P1, no P2. Every path after a reserve gives the slot back once (dispatch refused or raising, cancellation, precheck, envelope, async handler, thread, timeout) | P3 (noted, all older than this change): a slot leaks if the plugin pool were shut down (nothing shuts it), or if the precheck raised inside run_plugin (the worker ran the same check just before); a release frees the count before the semaphore, so a reserve in that instant waits 30 s more (no attempt spent) |
| Startup, second step (CI `test_khoi_dong_nhe` red on 56ee28f2 in 2 of 3 runs; the same ratio measured 4.43 on `main` dd1dccfb on the build machine) | `ws_compat` patches uvicorn when uvicorn loads instead of loading it (a one-shot import hook for `python main.py`), `webpush` loads `cryptography` in the functions that sign or encrypt: about 70 ms less at every start. `test_khoi_dong_nhe` now also guards `uvicorn` and `cryptography`; `test_ws_safari` checks the late patch. The threshold is unchanged |
| Review of the lazy routes (at 65129c1c: the same 45 requests through the real `main.app` at 65129c1c and 9ccbfe2d, with and without the login gate) no P1, no P2; P3 a GET route answered HEAD, so `HEAD /webhooks/events/export?raw=1` wrote an `export_raw` audit row for nothing | HEAD answers 405 as before (pinned in `fix_review_four()`, red on 65129c1c); the routes are left out of `/docs` (nothing reads `/openapi.json`) |
| R18 (review of R17, at 9ccbfe2d) P2 the owner-constant restore compared without case, treated starts_with and ends_with as contains, wrote only the first of several constants, and ignored `ne`; a customer e-mail the owner listed was written | a candidate (the real value when it is an owner constant, the constants, their joint, the placeholder) is written only when every condition on the path answers the same on it as on the real value, and never a value the e-mail or phone masking would change |
| R18 P3 (fixed) | a status or type word keeps only a short code (`status_reason: "Toi muon huy..."` is hidden); restore paths use the same customer-key test as the masking |
| Review of the final merged code (at 0b75f683: both merges of `main`, interactions with `main`, the new fixture) no P1; P2 the POSCake fixture kept one staff account id (digits zeroed, letters intact) under `creator.id`, `editor_id`, `assigning_seller_id` and five more paths: the allowlist keeps any `id` | 0.276.0: keys naming the shop's people (`editor`, `creator`, `seller`, `care`, `marketer`, `staff`, `user`, `owner`, `agent`...) are a person's block (`is_pii_key`), in the masked view and the capture; the fixture was exported again; `test_webhook_capture` checks both (red on 73ec1760). P3: `shop_id`, `warehouse_id` and product ids are kept (the shop's, not a person's; `shop_id` is a business-key part); the rehearsal now deletes its state folder |
| P3 (kept, noted) | an action changed after an event arrived is not sent to the new target by Retry (its secrets were bound to the old one): the delivery is cancelled with a pointer to "Process again with the current setup", which previews first |
