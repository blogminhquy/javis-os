# Webhook platform: staging and pilot pack (prepared, NOT run)

Everything here was prepared in the build session and **none of it was run**. That session's scope excluded real
sources, deploys and pilots. Each step names who runs it and what counts as a pass. A pass on a real source is
the only thing that may mark an adapter or action "production verified".

## Build under test

- Branch `claude/openmausbot-jarvis-research-ewnzc6`, PR #747. The SHA to stage is the PR head at the time of
  staging. At the time of writing the code under review is **787dfbf6** plus the commit that adds this section.
  Record the exact SHA here before starting: `________`.
- Fixtures shipped with it:
  - `tests/fixtures/webhooks/signatures.json`: frozen golden signatures. `github_docs_vector` is GitHub's own
    published example; Stripe, Shopify and generic HMAC were computed from the published schemes; Systeme.io is
    SYNTHETIC.
  - The receipt script for Apps Script: the template in `m3-actions-and-delivery.md`.
- Each captured real delivery goes in `tests/fixtures/webhooks/captured/<provider>-<event>.json` with every secret and
  every customer field replaced, plus the header names exactly as received.

## Budget for staging and pilot

| Item | Staging | Pilot (1 week, 1 shop) |
|---|---|---|
| AI runs | `ai_per_day: 20` per hook | the shop's normal daily volume x 1.5, no more |
| Events | `limits.per_hour: 60`, `per_day: 500` | the shop's busiest hour x 2 |
| Outside actions | request bins and test accounts only | one real receiver, `retry: never` |
| Tools | read-only first; one write tool with `approve: true` | write tools only with `approve: true` |
| Notifications | `all` | `errors_only` |
| Time | half a day | 7 days, a check every morning |

## How to stop (in order of reach)

1. **One action**: remove it from the hook (Rules panel, Actions box, Save). Waiting events cancel that branch, and
   the other branches keep running.
2. **The AI part**: `ai_per_day: 0`. AI branches are refused before a model is called. Outside actions continue.
3. **One hook**: switch it off on its card. New events get 401, and waiting events end `dead` without running.
   Business keys of events that never ran are given back.
4. **Everything outside**: remove the actions of every hook. Only the event log keeps filling.
5. **The source**: point POSCake or Systeme.io back to the old address (`poscake-migration.md`).

Nothing above deletes the log. Export it first (`Export CSV`) if a stop is for an incident.

## How to reconcile (every morning of the pilot, and after any stop)

1. **Counts**: the provider's own delivery log (POSCake, Systeme.io, Stripe dashboard) against Javis's
   `GET /webhooks/events/export?hook=<id>&since=<ts>&format=csv`. Every provider delivery must appear once:
   - as `done`/`silent`;
   - as `filtered`/`invalid`/`duplicate` with its reason;
   - or as a 429 the provider retried.
2. **Needs you**: the log filter "Needs you" (`unknown` and `waiting`). For each `unknown` branch, open Details,
   read the receiver's answer and the delivery id, check the receiver (CRM, sheet row, POS order) for that delivery
   id, then press **Mark done** or **Retry**. Retry sends the same delivery id.
3. **Approvals**: approve or reject what waits. A rejection cancels only that branch.
4. **Breakers**: a card saying "sending is paused" means 5 failures in a row. Fix the receiver, or point the action
   elsewhere (which clears the breaker).
5. **Double effects**: search the receiver for repeated delivery ids (`_javis.delivery_id`, `Idempotency-Key`). Any
   repeat is a defect, so stop the action (step 1 above) and report it with the export.

## 0. Preconditions

- [ ] A staging Javis on 0.229.0, with its own state folder (not the production one).
- [ ] `JAVIS_WH_MASTER_KEY` set, or `webhook_keys.json` backed up with `webhook_secrets.json`.
- [ ] The automated suites green on that build:
  - `test_webhook_golden_signatures`
  - `test_webhook_m2_review`, `test_webhook_m3_review`, `test_webhook_m4_review`, `test_webhook_m5_review`
  - `test_webhook_store_m1`
  - `test_webhook_rules_m2`
  - `test_webhook_m2_review`
  - `test_webhook_actions_m3`
  - `test_webhook_m3_review`
  - `test_webhook_security_m4`
  - `test_webhook_ops_m5`
  - `test_webhook_triggers_0198`
  - `tests/js/test_webhooks_ui_m1.js` to `m5.js`

## 1. Durability (M1), staging, 15 min

| Step | Pass |
|---|---|
| Send 20 events with `curl`, restart the server mid-way (`systemctl restart`) | every 202 event has a final state; no event without a state |
| Kill the server (`kill -9`) while a slow task runs | that event becomes `unknown` within 2 min of restart, is NOT re-run, the owner is told |
| Resend an event with the same `Idempotency-Key` after a 429 | it runs (not "duplicate") |

## 2. Rules (M2), staging, 15 min

| Step | Pass |
|---|---|
| Test rules on a captured body, then send that body | the decision on receipt is the simulation's |
| Send the same order twice with two idempotency keys | the second is `duplicate` with the first id |
| Send `{"total": 1e999999}` to a hook with an integer mapping | 422 at once, the dashboard stays responsive |

## 3. Real sources (M3/M4), staging, one per source in use

| Source | How | Pass | Then |
|---|---|---|---|
| Stripe | test-mode webhook endpoint + `stripe trigger invoice.paid` | 202, signature ok, a resend from the Stripe dashboard is `duplicate`; a changed secret gives 401 | mark `stripe` production verified in the doc |
| GitHub | repo webhook with secret, "Redeliver" | as above, `_event.type` like `push` | same |
| Shopify | development store webhook | as above | same |
| Systeme.io | a webhook on a test account, secret set | confirm header names and scheme (`webhook_verify.SYSTEME_IO`); capture one delivery per event used | fix the adapter if different, replace the synthetic fixture, change status from `unverified` |
| POSCake | a test shop | capture deliveries; confirm what POSCake signs, if anything | follow `poscake-migration.md` |
| Apps Script | deploy the receipt template (`m3-actions-and-delivery.md`) with access "Anyone" | branch `completed` with the row number; resend of the event gives `duplicate: true` from the script; with access "Only myself" the branch is `failed` with the "Anyone" hint | |
| HTTP forward | a request bin you control | `Idempotency-Key` equals the delivery id on both tries of a 503 then 200 | |
| Tool | a read-only tool first, then one write tool with approval | approval asked, tool called once at the hook's level, audit line in the hub log | |

## 4. Operations (M5), staging, 1 day

| Step | Pass |
|---|---|
| `notify: daily_digest` for one hook | one digest after 08:00 with matching counts |
| Point an action at an address answering 500 | after 5 events: paused notice, no more sends for 10 min, then one try |
| `ai_per_day: 1`, send 2 events | second AI branch "AI budget reached", no model call in the engine log |
| Export CSV of a hook | opens in a spreadsheet, no formula runs, no secret in the file |

## 5. Pilot (one real shop, 1 week)

- One hook in production, `notify: errors_only`, AI budget at the shop's normal volume plus half.
- Daily check: the filter "Needs you" in the log is empty or resolved, and "Filtered" holds only events meant to be
  dropped.
- Exit criteria: no lost event (POSCake/Systeme.io's own delivery log matches Javis's count), no double effect,
  every `unknown` reconciled within a day.
- Rollback ready: `poscake-migration.md`, "If something is wrong".

## What is still missing for "production verified"

1. A real delivery from each provider (step 3). Until then Stripe, GitHub and Shopify are `spec`, Systeme.io is
   `unverified` and POSCake is not built.
2. A real Apps Script deployment through the 302/echo flow.
3. The spec document itself, to reconcile the assumptions listed in each milestone doc.
