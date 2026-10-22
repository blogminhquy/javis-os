# Webhook platform: staging and pilot pack (prepared, NOT run)

Everything here was prepared in the build session and **none of it was run**. That session's scope excluded real
sources (POSCake, Apps Script, Zalo, Systeme.io), deploys, VPS work and pilots. Each step names what counts as a pass.
Only a pass on a real source may mark an adapter or action "production verified" (spec §10, §16.6).

## Build under test

- Branch `claude/openmausbot-jarvis-research-ewnzc6`, PR #747, version 0.274.0.
- Stage the PR head at the time of staging, and write its exact SHA (`git rev-parse HEAD`) in the staging log before
  starting.
- Last head checked in the build session: **346707cf** (code, version 0.274.0, `main` e36e060a merged in). Commits
  after it change only this file and the README.
  - CI: both `test` jobs green on 346707cf.
  - Full local run of `tests/python/test_*.py` and `tests/js/test_*` on 346707cf: every file green.
  - Independent review of the last code change (the plugin slot reservation): no P1, no P2.
  - If you stage a later head, rerun the three commands below on it first.
- The automated evidence for that SHA: CI green on the PR, plus, on the staging machine:

  ```
  .venv/bin/python tests/python/test_webhook_spec_matrix.py
  .venv/bin/python tests/python/test_webhook_spec_review.py
  .venv/bin/python tools/webhook_bench.py            # the §16 target, measured on THIS machine
  .venv/bin/python tools/webhook_staging_rehearsal.py # parts 1, 2 and 4 on the real host, local receivers
  ```

## Local rehearsal (run in the build session, 2026-10-20)

`tools/webhook_staging_rehearsal.py` runs parts 1, 2 and 4 against the real host (`main.app` under uvicorn in a child
process, a fresh state folder, real sockets and SQLite, local receivers, real SIGKILLs). Every model path raises in the
child. Run on 15a44d59 (code of 346707cf) in the build container: **14 of 14 passed in 217 s**.

| Step | Result |
|---|---|
| 1.1 20 events, SIGKILL after 10, restart | every 202 has an event with a final state; every one reached the receiver |
| 1.2 SIGKILL during a 6 s delivery | after the restart: unknown, sent once, not resent; the owner's notice queued and sent |
| 1.3 a 429, then the same Idempotency-Key | 202, not a duplicate |
| 2.1 simulate, then send the same order | both decide `run` |
| 2.2 the same order with another key | duplicate of the first |
| 2.3 `status` as text; an item without a name | filtered `status_mismatch` / `product_not_found`, nothing sent |
| 4.2 a receiver answering 500 | 5 sends, then paused (breaker notice), no sends during the pause |
| 4.3 `ai_per_hour: 0` | blocked before any model call |
| 4.4 CSV export | phone masked, no formula cell; `raw=1` written to the audit log |
| 4.5 UI at 390 px | no sideways scroll, nothing under 16px, no page error |

Not covered here: anything that needs a real source or a public address (part 3, §16.6). From this container the
network policy refuses `script.google.com` and `pos.pages.fm`, and nothing can reach it from outside. The owner's
guide for capturing POSCake deliveries is `huong-dan-gui-du-lieu-poscake.txt`.

## Fixtures

| Fixture | Origin | Use |
|---|---|---|
| `tests/fixtures/webhooks/signatures.json`: `github_docs_vector` | GitHub's published example | golden check |
| same file: Stripe, Shopify, generic HMAC | computed from the published schemes | golden check |
| same file: `systeme_io_synthetic_*` (raw, php_default, php_unescaped) | **SYNTHETIC** | replace with a captured delivery |
| `test_webhook_spec_matrix.py`: `ORDER`, `SPEC_RULES`, `POSCAKE_ACTIONS` | the spec's §9 illustration | replace field names with the captured POSCake payload |
| `tests/fixtures/webhooks/captured/<provider>-<event>.json` | **to capture** (§16.6, §17) | one per event kind used, customer fields and secrets replaced, header names exactly as received |

Capture and check with `tools/webhook_capture.py` (tested by `tests/python/test_webhook_capture.py`):

```
# on staging, for each captured event (pick its id in Events): write a masked fixture with the decision it must get
.venv/bin/python tools/webhook_capture.py export --state-dir <STATE_DIR> --event ev_... --expect run \
    --config hook.json --out tests/fixtures/webhooks/captured/poscake-order-paid.json
# then check the hook's rules against every fixture (nothing stored, sent or run)
.venv/bin/python tools/webhook_capture.py check --config hook.json tests/fixtures/webhooks/captured/*.json
```

The export uses the dashboard's allowlist: ids, statuses, times, amounts, counts and product names stay, every other
value becomes a placeholder of the same type, e-mails and phones inside kept texts are masked, and credentials and
bearer links are redacted. With `--config`, the paths the hook's rules read keep their value as received, except an
identity, customer or credential path (listed under `not_kept`). A text a filter compares is written as your own
constant from the rules (the status you filter on, the word you look for), never as the customer's words: the fixture
then gets the decision the real event got. Read each file before committing it.

## 0. Data to collect first (spec §17), with the owner

- [ ] POSCake: 3 to 5 real deliveries per event kind, with headers, customer fields replaced; the shop, order and event
      ids; what each `status` value means; whether POSCake can send a custom header (decides the authentication in
      `poscake-migration.md`).
- [ ] Apps Script: the body it expects, the receipt it returns, how it skips a repeated delivery id, how its 302 echo
      behaves on the deployment used.
- [ ] `poscake-zalo`: where it stores its schedule; whether the same delivery id gives back the same job id.
- [ ] Volumes: the busiest hour, how late an order may be processed, retention wanted, disk available.
- [ ] Per action: at-least-once acceptable, or reconcile before any resend (sets `retry_safety`).

## Budget for staging and pilot

| Item | Staging | Pilot (1 week, 1 shop) |
|---|---|---|
| AI runs | `ai_per_hour: 5` per hook | the shop's normal hourly volume × 1.5, no more |
| Events | `limits.per_minute: 60` | the busiest minute × 2 (default 300) |
| Outside actions | test receivers and test threads only | one real receiver per action, `retry_safety: manual_on_ambiguous` |
| Tools | read-only first; one write tool with `approve: true` | write tools only with `approve: true` |
| Notifications | `all` | `errors_only` |
| Time | half a day | 7 days, a check every morning |

## How to stop (in order of reach)

1. **One action**: remove it (Configuration, Advanced, Actions, Save). Waiting events cancel that delivery; the other
   deliveries continue.
2. **The AI part**: `ai_per_hour: 0`. AI deliveries are blocked before any model is called; outside actions continue.
3. **Processing of one hook**: **Pause processing**. Events are still received and stored within the quotas; nothing
   runs until Resume.
4. **Receiving of one hook**: **Stop receiving**. New requests get 401; events already accepted still run (pause them
   too to hold them).
5. **The source**: point POSCake or Systeme.io back to the old address (`poscake-migration.md`, "The way back").

Nothing above deletes the log. Export it first (Events, Export CSV) if a stop is for an incident.

## How to reconcile (every morning of the pilot, and after any stop)

1. **Counts**: the provider's own delivery list against `GET /webhooks/events/export?hook=<id>&since=<ts>&format=csv`.
   Every provider delivery appears once: done, ignored or quarantined with its reason, waiting for you, or as a 429 the
   provider retried. "Received (202)" on the Health part is not "processed".
2. **Needs you**: Events, filter "Needs you" (unknown, waiting, blocked). For each unknown delivery, open the event:
   the timeline shows the receiver's answer and the delivery id. Check the receiver (sheet row, CRM record, plugin job)
   for that id, then press **Mark done** or **Retry**. Retry sends the same delivery id.
3. **Approvals**: approve or reject what waits. A rejection cancels only that delivery.
4. **Breakers**: a card saying sending is paused means repeated failures at one target. Fix the receiver, or point
   the action elsewhere.
5. **Double effects**: search the receiver for repeated delivery ids (`X-Javis-Event-Id`, `javis_delivery`,
   `_javis.delivery_id`). Any repeat is a defect: stop that action (step 1 above) and report it with the export.

## 1. Durability and recovery (M1), staging, 15 min

| Step | Pass |
|---|---|
| Send 20 events with `curl`, restart the server midway | every 202 has an event with a final or waiting state |
| `kill -9` the server while a slow action runs | after restart that delivery is unknown (or resent once if retry-safe), the owner is told |
| Resend an event with the same `Idempotency-Key` after a 429 | it is received (202), not a duplicate |

## 2. Rules (M2), staging, 15 min

| Step | Pass |
|---|---|
| Test rules on each captured body, then send that body | the decision on receipt equals the simulation's |
| Send the same order twice with two different idempotency keys | the second is ignored as a duplicate of the first |
| A captured order with `status` as text, or a missing item name | ignored with `status_mismatch` (the text "1" is not the number 1) / `product_not_found`, never run |

## 3. Real sources and actions (M3, M4), staging, one per source in use

| Source | How | Pass | Then |
|---|---|---|---|
| Stripe | test-mode endpoint, `stripe trigger invoice.paid` | 202 with no Javis token, a dashboard resend is a duplicate, a changed secret gives 401 | mark `stripe` production verified |
| GitHub | repo webhook with secret, Redeliver | same, `_event.type` like `push` | same |
| Shopify | development store | same | same |
| Systeme.io | test account webhook with secret | header names and the signed form (`signed_form` in the event) as expected; dedup on `X-Webhook-Message-Id` | replace the synthetic fixtures; change the status from `unverified` |
| POSCake | a test shop | capture deliveries; confirm what it signs and whether it sends a header | `poscake-migration.md` |
| Apps Script | the receipt template, access "Anyone" | delivery succeeded with the row number; a resend gives `duplicate: true` from the script; access "Only myself" gives blocked with the sign-in hint | |
| Plugin `poscake-zalo` | a test thread | accepted with a job id; the same delivery id twice gives the same job id; no second message | |
| HTTP forward | a request bin you control | raw bytes unchanged; the same `X-Javis-Event-Id` on the owner's retry | |
| Tool | a read-only tool, then one write tool with approval | approval asked; tool called once at the hook's level | |

## 4. Operations (M5), staging, 1 day

| Step | Pass |
|---|---|
| `notify: daily_digest` | one digest after 08:00 in the chosen time zone, counts match the export |
| Point an action at an address answering 500 | after repeated failures: one paused notice, no sends during the pause |
| `ai_per_hour: 1`, send 2 events | the second waits for the budget; no model call logged |
| Export CSV | opens in a spreadsheet, no formula runs, customer fields masked; `raw=1` appears in the audit |
| UI at phone width | `node tools/webhook_ui_narrow_check.mjs <staging-url> <dir>` exits 0 (no sideways scroll, nothing under 16px) |

## 5. Pilot (one real shop, 1 week)

- One hook in production, `notify: errors_only`, AI budget at the shop's normal volume plus half.
- Daily: "Needs you" empty or resolved; ignored events are only the ones meant to be dropped.
- Exit criteria (spec §16): no lost event (the provider's list matches Javis's count), no double effect, every unknown
  reconciled within a day.
- Ready to go back: `poscake-migration.md`, "The way back"; `rollback.md`.

## Still missing for "production verified"

1. A real delivery from each provider used (part 3). Until then Stripe, GitHub and Shopify are `spec`, Systeme.io is
   `unverified`, POSCake is not built.
2. A real Apps Script deployment through the redirect flow, and `poscake-zalo` returning the same job id.
3. The §17 data, replacing the illustrative field names in the configuration.
4. The benchmark on the target machine (the recorded numbers are from the build container).
