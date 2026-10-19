# Webhook platform: staging and pilot pack (prepared, NOT run)

Everything here was prepared in the build session and **none of it was run**. That session's scope excluded real
sources, deploys and pilots. Each step names who runs it and what counts as a pass. A pass on a real source is
the only thing that may mark an adapter or action "production verified".

## 0. Preconditions

- [ ] A staging Javis on 0.229.0, with its own state folder (not the production one).
- [ ] `JAVIS_WH_MASTER_KEY` set, or `webhook_keys.json` backed up with `webhook_secrets.json`.
- [ ] The automated suites green on that build:
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
