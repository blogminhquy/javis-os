# POSCake: cutover to the webhook platform, and the way back (0.274.0, spec §9, §16, §17)

**Known and not known.** This repository has no POSCake webhook contract: no documented signature, no event names, no
payload schema, no statement of whether POSCake can send a custom header. Javis does **not** guess any of it
(`provider: poscake` is refused when saved). Everything below that depends on POSCake's real data is a step to run
on staging with the owner, not a fact. Nothing here was run against POSCake, Apps Script or Zalo.

## What the first real delivery showed (2026-10-22)

The owner captured one real POSCake delivery (a test order, `event_type: create`) with webhook.site. Its masked copy is
`tests/fixtures/webhooks/captured/poscake-order-create.json`; `tests/python/test_webhook_capture.py` pins what follows.

- **Headers:** only `content-type: application/json` and `user-agent: mint/1.9.3`. No signature, no custom header. So
  POSCake authenticates with the older hook's `?token=` address (below); a new hook refuses it (401, measured).
- **Event:** `event_type` (`create` here); the order's state is `status` (a number: `0` with `status_name: "new"`).
  What the other numbers mean (confirmed, paid, cancelled...) is still the owner's to state.
- **Order ids:** `id` is the shop's order number (739, equal to `system_id`), `shop_id` the shop.
- **Products:** the name is `items[*].variation_info.name` (also `display_id`, `product_display_id`). There is **no**
  `items[*].name`: the illustrative configuration below would ignore every real order (`product_not_found`).
- **Masking:** the masked view and the fixture keep ids, amounts, counts, product names and times; e-mails, phones,
  names, addresses, Facebook ids, staff, avatar, payment and tracking links are hidden (checked on this payload).
- **Run on the real host** (local, the same body): with the real field names the order ran once; the same body sent
  again was a duplicate; no model was called.

Corrected filter for a paid-order trigger, once the owner names the paid status number `<P>`:

```json
{"filter": {"all": [
  {"path": "status", "op": "eq", "value": <P>},
  {"path": "items[*].variation_info.name", "op": "contains", "value": "TRỢ LÝ AI JAVIS", "quantifier": "any",
   "case_sensitive": false, "reason": "product_not_found"}]}}
```

## The target configuration (spec §9)

One hook, three parts: a filter on paid orders that contain the product, a business key per order and status, and two
actions that do not need AI.

```json
{
  "rules": {
    "filter": {"all": [
      {"path": "status", "op": "eq", "value": 1},
      {"path": "items[*].name", "op": "contains", "value": "TRỢ LÝ AI JAVIS", "quantifier": "any",
       "case_sensitive": false, "reason": "product_not_found"}
    ]},
    "dedup": {"policy_version": 1, "business_paths": ["shop_id", "id", "status"], "ttl_s": 604800,
              "missing": "quarantine"},
    "correlation": "id"
  },
  "actions": [
    {"id": "to_apps_script", "type": "http_forward", "url": "https://script.google.com/macros/s/<id>/exec",
     "body_mode": "raw", "redirect_profile": "google_apps_script", "retry_safety": "manual_on_ambiguous",
     "delivery_ref": "query"},
    {"id": "to_poscake_zalo", "type": "plugin", "plugin": "poscake-zalo", "handler": "order_received"}
  ]
}
```

Field names (`status`, `items[*].name`, `shop_id`, `id`) are the spec's illustration. The first real delivery (above)
confirms `status`, `shop_id` and `id` but puts the product name at `items[*].variation_info.name`, and a new order has
`status` 0: use the corrected filter above. The same configuration is exercised with fakes by
`tests/python/test_webhook_spec_matrix.py` (`SPEC_RULES`, `POSCAKE_ACTIONS`).

## How POSCake authenticates

- The hook that receives POSCake today was migrated from `webhooks.json`. It is an **older hook**, so its address
  with `?token=` keeps working. Add the rules and actions above **to that hook** (Configuration, Advanced) instead of
  creating a new one, unless step 2 shows POSCake can send a header. An older hook keeps `notify: all` (one
  message per order): set **Notifications** to `errors_only` there too, once its actions run without AI.
- A **new** hook accepts the key only in a header (`X-Javis-Token`, or one the owner names, or `Authorization:
  Bearer`). Use one only if POSCake can send that header.
- Never switch authentication off to make POSCake fit (spec §10). If POSCake signs its deliveries, its scheme becomes
  an adapter once its documentation is in hand (see the end of this page).

## Before you start

- [ ] Javis 0.274.0 or later on **staging**, with its own state folder.
- [ ] Back up `STATE_DIR/webhook_events.sqlite3*`, `webhook_keys.json` and `webhook_secrets.json`.
- [ ] The data of spec §17 collected (see `staging-pilot-pack.md`, part 0): masked POSCake payloads and headers; ids of
      shop, order and event; what each status means; whether POSCake sends a custom header; what the Apps Script
      receives, returns and dedups; where `poscake-zalo` keeps its schedule and whether it returns the same job id for the
      same delivery id; peak rate, allowed delay, retention and disk budget; which actions are at-least-once and which
      must be reconciled before a resend.

## Cutover (spec §16), one step at a time

1. **Create the v2 configuration on staging** (the hook above, on the staging Javis).
2. **Capture, then simulate.** Point a POSCake test shop at staging, or replay captured bodies with `curl`. Open the
   event, then Configuration, Advanced, **Test rules** with that body: the simulation writes nothing, sends nothing
   and calls no model. Compare its decision for each captured order with what the shop expects (run or ignore, and
   why).
3. **Check the event id, the authentication and the schema.** The timeline shows "received", "parsed", "filter" and
   the reason codes. A field the filter reads but the order lacks makes it ignored (`missing_field`), never matched;
   a business-key field it lacks, or a payload the schema refuses, quarantines it (kept, and you are told). Fix the
   paths until every captured order gets the decision it should.
4. **Run each action into a test receiver.** Point `to_apps_script` at a test deployment of the receipt script
   (`m3-actions-and-delivery.md`), and run `poscake-zalo` against a test thread, never a customer. Use **Send a real
   test** on the Configuration part: it lists what each action will do before it sends, and its event has its own
   duplicate space. Check:
   - the Apps Script returns its receipt;
   - the plugin returns the same job id when the same delivery id is sent twice;
   - Retry sends the same delivery id.
5. **Switch ONE source path** to the new hook. Never let the old plugin path and the new core path both send Zalo
   messages or write orders. Switch the old one off first, or point POSCake at only one of them.
6. **Reconcile** every morning for the first week (`staging-pilot-pack.md`, "How to reconcile"): POSCake's own order
   list against the export of the hook (`Events`, Export CSV), and the receipts of each action. Every order must
   appear once: done, ignored with its reason, or waiting for you.

## The way back

- **The rules drop orders they should not:** fix the condition that drops them (the event's timeline names it), and
  keep the status filter and the business key: clearing the whole rules box would send every status change of every
  order to Zalo and the sheet. Then use "Process again with the current setup" on a dropped event: it previews first,
  and refuses an order that already ran as another event (same business key).
- **One action misbehaves:** remove it from the hook. Waiting events cancel that delivery and the others continue.
  Or press **Pause processing**: events are still received and stored, nothing runs until you resume.
- **Send traffic back to the old path:** point POSCake at the old address again, and switch the new path's Zalo or
  Apps Script action off before switching the old one on. Keep the new store: its delivery keys and receipts tell you
  what already happened.
- **Go back to an older Javis build:** follow `rollback.md`. A binary rollback never undoes what was already sent:
  reconcile the receipts first.

## When POSCake's contract is known

Add a `poscake` profile to `server/webhook_auth.py`: the signature header and scheme, the event name and the
delivery id. Build its golden test from a captured delivery with secrets and customer data replaced (spec §10). Mark
it `spec` once that test passes, and "production verified" only after a real delivery has passed on staging.
