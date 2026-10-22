# Webhook platform: gap analysis against the spec of record

> **Closed (0.274.0).** Every row below was built or is listed as open in the requirements matrix of `README.md`, which is the current record; this file is kept as the gap list at `a6132b9f`.

Spec: `docs/superpowers/specs/2026-10-19-webhook-event-platform-design.md` (supplied 2026-10-19, after M1-M5 were
first built from the owner's brief). Code compared: branch head `a6132b9f`. Each row is a requirement of the spec, what
the code did at that head, and the change. The status column is updated as the work lands; `docs/webhook-platform/
README.md` holds the final requirement -> code -> test -> evidence matrix.

Legend: **ok** already met; **gap** to change; **decision** met in another way, with the reason.

## §4 Storage and ingress

| § | Requirement | At a6132b9f | Change |
|---|---|---|---|
| 4.1 | tables hook_revisions, events, receipts, dedup_keys, deliveries, attempts, notifications | events, dedup, attempts (per claim), biz_keys, branches, breakers, ai_runs; hooks in webhooks.json | gap: hooks + hook_revisions in SQLite, receipts, per-delivery attempts, generation on deliveries, notifications outbox |
| 4.1 | UNIQUE(event_id, action_id, generation) | PK(event_id, action_id) | gap: generation column, table rebuilt in a locked migration |
| 4.1 | WAL, foreign_keys=ON, finite busy_timeout, synchronous=FULL, I/O off the loop | all but foreign_keys | gap: foreign_keys=ON |
| 4.1 | backup with the SQLite backup API | none | gap: `Store.backup()` + rollback tool |
| 4.1 | raw body in the same transaction; file private | ok | |
| 4.1 | payload encryption at rest is an environment decision | not encrypted | decision: documented, left to the environment (disk encryption) |
| 4.2 | hook lookup and limits before reading; stream read with a cap; Content-Length only a hint | stream cap 32 KiB global, read before the token check | gap: token checked before the body, per-hook cap (default 256 KiB, ceiling 2 MiB) |
| 4.2 | 202 `{accepted, event_id, state:"received"}` | `{ok, accepted, run_id, queued}` | gap: add the spec fields (keep `run_id` for old clients) |
| 4.2 | duplicate 200 `{duplicate:true, event_id:<first>}` | `{ok, duplicate, run_id}` | gap: add `event_id` |
| 4.2 | 429 with Retry-After, no new dedup | no Retry-After header | gap |
| 4.2 | 503 with a safe error code | text only | gap: `code` |
| 4.2 | filter/parse AFTER the commit, in the worker | rules evaluated at ingest, ignored events answered 200/422 | gap: evaluation moves to a worker triage stage; every stored event answers 202 |
| 4.2 | verified but unparseable payload stored `quarantined`, no AI | `invalid`, answered 422 | gap: `quarantined` state in the API, 202 |
| 4.2 | unsupported content type refused clearly before actions | text/anything accepted | gap: hooks with rules refuse a content type they cannot parse (quarantined with the reason) |

## §5 Filter

| § | Requirement | At a6132b9f | Change |
|---|---|---|---|
| 5 | ops eq ne in exists gt gte lt lte contains all any not, `[*]` | no `[*]` | gap |
| 5 | `1` differs from `"1"` | numeric strings compared as numbers | gap: strict types; explicit `as` normalisation per condition |
| 5 | missing is missing, never null/0/"" | `ne` on a missing field passed | gap: comparisons on a missing field fail with `missing_field` |
| 5 | contains on an array names any/all | contains on a list = any element equal | gap: `quantifier` required on arrays, substring per element |
| 5 | never stringify an object | `_cmp_str` stringified objects | gap |
| 5 | case_sensitive flag | `case: insensitive` | gap: accept `case_sensitive: false` |
| 5 | depth 64, at most 100 filter nodes | depth 64 ok; 40 leaves, depth 4 | gap: 100 nodes |
| 5 | bad rule refused at save; runtime error -> quarantine with reason | ok (fail closed to invalid) | rename in the API |
| 5 | rule version and reason codes per condition (`status_mismatch`, `product_not_found`, `missing_field`) | rules_rev ok; no codes | gap: automatic codes + owner label `reason` |
| 5 | no PII stored several times in the trace | values stored in the trace | gap: stored trace keeps types and results; values only in simulation |
| 5 | simulation without side effects | ok | |

## §6 Dedup

| § | Requirement | At a6132b9f | Change |
|---|---|---|---|
| 6.1 | provider's stable id, not the attempt id | Systeme used `X-Webhook-Id` | gap: `X-Webhook-Message-Id`; Shopify `X-Shopify-Event-Id` first |
| 6.1 | scope = hook + policy kind | (hook, key) | gap: key carries its policy kind |
| 6.2 | composite key, typed tuple serialised then hashed | one path, plain text stored | gap: `business_paths`, hash only |
| 6.2 | missing field -> quarantine (default) | on_missing accept by default | gap: default quarantine for the spec format |
| 6.2 | TTL 7 days default | 30 days | gap for the spec format |
| 6.2 | filtered events take no business key but keep a delivery receipt | no receipt, no idempotency key kept | gap: every stored event keeps its delivery key |
| 6.2 | keys of different hooks do not block each other | namespace per brain | gap: hook-scoped by default, a shared namespace only when named |

## §7 Worker and retry

| § | Requirement | At a6132b9f | Change |
|---|---|---|---|
| 7 | CAS claim, lease, fencing | ok | |
| 7 | delivery states pending running succeeded retry_wait waiting_result waiting_approval blocked unknown dead cancelled | internal names, no blocked/dead per branch | gap: spec names in the API, `blocked`, `dead` on exhaustion |
| 7 | event states ignored processing waiting done partial_failed failed cancelled | no partial_failed/cancelled | gap |
| 7 | retry 1 / 5 / 30 min, 4 calls in all, jitter ±20 %, Retry-After within a deadline; fake clock and RNG | 10 s / 60 s / 300 s, 3 tries, no jitter | gap: per-hook `retry`, injectable clock/RNG |
| 7 | 429/5xx/timeout after send: retry only with idempotency or at-least-once, else unknown | 429/503 always retried | gap: 503/5xx by retry_safety; 429 stays retry (refused before processing) |
| 7 | 401/403, missing credential, plugin off -> blocked | failed | gap |
| 7 | AI quota -> wait, not counted | failed "AI budget reached" | gap |
| 7 | worker died: retry if proven safe, else unknown | always unknown | gap: retry-safe branches retried |
| 7 | "Process with new configuration": new generation, simulation first, shows effects that may repeat | none | gap |

## §8 Actions

| § | Requirement | At a6132b9f | Change |
|---|---|---|---|
| 8.1 | POST, raw body mode, allowed headers only, own credential, timeout, response cap | ok | alias `body_mode` |
| 8.1 | `Idempotency-Key` / `X-Javis-Event-Id` | Idempotency-Key + X-Javis-Delivery | gap: add X-Javis-Event-Id |
| 8.1 | check the IP after DNS (rebinding) and on every redirect | resolved then connected separately | gap: connection pinned to the checked address |
| 8.1 | Apps Script: check host/IP of each hop | echo host checked, address not | gap |
| 8.1 | Apps Script cannot read headers in doPost(e) | delivery id only in headers in raw mode | gap: owner-approved `delivery_ref: query` |
| 8.2 | `register_event_handler(name, handler, schema, min_mode)`, bound plugin + handler only | register_webhook_handler without schema | gap: new API (old kept), schema, `ai`, `idempotent` |
| 8.2 | envelope: event, delivery, attempt, source, brain, revision, verified metadata, payload, raw hash, business key | partial | gap |
| 8.2 | results completed accepted retryable_error permanent_error unknown waiting_approval | completed/accepted only | gap |
| 8.2 | old callback never runs alongside a retry | possible after a timeout | gap: in-flight guard per delivery |
| 8.2 | AI handler declared, budgeted, enabled in the binding | none | gap |
| 8.3 | tool via the dispatcher | ok | |
| 8.3 | `{{payload.x}}` paths, type kept for a whole-field expression, missing is an error | `{field}` only, missing kept/empty | gap |
| 8.4 | durable dispatch, no second job on retry, ids in prompt | durable checkpoint ok; ids not in the prompt | gap: ids in the prompt and the run record; decision: the delivery row is the durable job (see M3 doc) |
| 8.5 | action id, `when`, `depends_on` (acyclic), at most 10 | no when/depends_on, 8 | gap |

## §10 Verification and secrets

| § | Requirement | At a6132b9f | Change |
|---|---|---|---|
| 10 | generic token: bearer or owner's header; query token only for old hooks, warned | any hook accepts ?token= | gap |
| 10 | GitHub, Shopify, Stripe profiles | ok | Shopify event id |
| 10 | Systeme: HMAC over Systeme's normalised JSON (Unicode, slashes), message id | HMAC over raw bytes | gap: PHP-style normalisations, matched form recorded; adapter stays unverified (docs host unreachable from here) |
| 10 | POSCake not guessed | ok | |
| 10 | encrypted secret, fail closed | own AES-GCM vault, fail closed | decision: kept (adds AAD binding and master-key rotation that `secrets_store` lacks); documented |
| 10 | two signing secrets with a bounded overlap; key version and verify time stored | none | gap |
| 10 | replay never re-signs | ok | |

## §11 Limits

| § | Requirement | At a6132b9f | Change |
|---|---|---|---|
| 11 | no 30/hour cap on code-only processing | 30/hour on every event that runs | gap: ingress 300/min with burst; the hour/day caps become optional |
| 11 | global/IP limit for unauthenticated requests | none | gap |
| 11 | backlog 10 000 events or 256 MiB per hook | 6 due + 200 parked + 200 owed | gap |
| 11 | DB 1 GiB, WAL, free disk, real write result | 256 MiB live pages | gap |
| 11 | AI 30/hour per hook, global ceiling, durable counter | 100/day per hook | gap |
| 11 | concurrency 1/hook, bounded global pool, fair | ok (4 workers, one per hook) | test |
| 11 | raw 7 days, failed/unknown kept, metadata 30 days | ok | |
| 11 | duplicate acknowledged when the backlog is full | ok | |
| 11 | business expiry only when configured, audited | none | gap: optional `expire_after_h` |
| 11 | breaker per target/credential | per hook + action | gap: per target fingerprint |

## §12 Log and notifications

| § | Requirement | At a6132b9f | Change |
|---|---|---|---|
| 12 | page sections Configuration, Events, Health | one card + rules panel | gap |
| 12 | timeline per event | detail with branches | gap |
| 12 | cursor pagination, filters hook/state/order id/correlation/time | hook/state | gap |
| 12 | real test send with preview, own namespace | fixed sample | gap |
| 12 | raw view/export masked by default, audited | unmasked | gap |
| 12 | pause processing differs from stop receiving | one switch, queued events died | gap |
| 12 | modes all/errors_only/daily_digest/none; old hooks all; new non-AI hooks errors_only | all by default | gap: default |
| 12 | digest by code, owner's time zone, one per period after restart | ok (global zone) | gap: per-hook zone |
| 12 | `none` never hides system alerts (disk) | no system alert | gap |
| 12 | errors_only groups repeated errors into one incident | one notice per event | gap |
| 12 | `ai_triage=false` stops model triage; when on, budgeted | triage always for AI failures | gap |
| 12 | health metrics | partial (counts) | gap |

## §13 Modules and compatibility

| § | Requirement | At a6132b9f | Change |
|---|---|---|---|
| 13 | webhook_triggers stays the router; webhook_worker.py, webhook_auth.py | worker inside triggers; verify in webhook_verify.py | gap: split |
| 13 | migrate webhooks.json into SQLite, versioned, idempotent, snapshot, marker | config stays in webhooks.json | gap |
| 13 | old hook = one AI action, no filter added, level kept | ok | |
| 13 | legacy seen_keys as bounded tombstones | ok (7 days) | |
| 13 | public `/hooks/{id}`, admin under `/webhooks/...` behind login | ok | test through the real app |
| 13 | rollback tool: stop worker, export backlog, explicit legacy config, list what the old build cannot run | doc only | gap |

## §15-16 Test matrix, acceptance, benchmark

Every row of §15 gets a named test in `tests/python/test_webhook_spec_matrix.py` (host router, temporary SQLite, fake
HTTP/plugin/tool/model, fail-fast model guard including incident triage, crash tests in subprocesses with a barrier).
§16's benchmark (10 KiB, 5 hooks, 20 req/s for 60 s, p95 ACK < 250 ms, slow actions measured apart) runs over a real
HTTP server; numbers are recorded in the docs. §16.6 (fixtures from real masked POSCake data, staging with receipts) needs
the owner's data and stays open in the staging pack.
