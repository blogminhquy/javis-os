# POSCake to Javis webhooks: migration and rollback

**What is known and what is not.** This repository has no POSCake webhook contract: no documented signature header,
no event names, no payload schema. Javis does **not** guess it. `provider: poscake` is refused when saved, with that
reason. Until POSCake's contract is confirmed against a real account, a POSCake hook uses the Javis token in the URL
(`provider: none`). That is the same protection every hook had before 0.233.0. The shop's rules are written against
the payload as POSCake really sends it, captured in the staging step below.

## Before you start

- [ ] Javis is 0.233.0 or later. Work page, Webhooks: each card shows its state log.
- [ ] Back up `STATE_DIR/webhooks.json`, `webhook_events.sqlite3*`, `webhook_keys.json` and `webhook_secrets.json`.
- [ ] Note which POSCake events you use today (new order, order status, payment...) and what Javis does with each.

## Steps

1. **Create one hook per event kind**, or one hook with a filter. Copy its URL with `?token=` (POSCake can only send
   to a URL, so the token goes in the query). The level is `full` only if the hook must act outside.
2. **Capture one real delivery** on staging (`staging-pilot-pack.md`, step 3). The event log stores the body. Open
   Details: the payload is the contract you build on. Remove customer data before keeping it as a fixture.
3. **Write the rules against that payload**:
   - `schema` holds the fields you rely on (for example the order id);
   - `filter` keeps only the events you want;
   - `mapping` picks `order_id`, `phone`, `total`;
   - `business_key` is `{"namespace": "poscake", "entity": "order", "field": "order_id", "ttl_s": 2592000}`, so a
     resent order runs once.

   Test with the Rules box's **Test rules** button on the captured body: nothing is stored or run.
4. **Choose the actions**: the AI task, a forward to your CRM (`http`), a Google Sheet (`apps_script`, with the receipt
   template in `m3-actions-and-delivery.md`) or a POS tool (`tool`, approval on). Keep `retry: never` unless the
   receiver dedups on `Idempotency-Key`.
5. **Set the notification mode** (`errors_only` is a good start) and the limits. POSCake bursts at opening time, so
   raise `per_hour` if needed.
6. **Point POSCake at the new URL.** Keep the old hook switched OFF, not deleted, for the rollback.
7. **Watch the first day.** In the log, use the filter "Needs you" for unknown or approval events, and "Filtered" for
   events your rules dropped. Use Details to see why.

## If something is wrong (rollback)

- **Rules drop events they should not:** clear the rules (empty box, Save) and every event runs as before. Replay a
  dropped event's body with Test rules after fixing them. Filtered events follow the hook's `retention_days`
  (default 30, at most 200 per hook), with their body for 7 days, and at most 300 per hour are logged.
- **An outside action misbehaves:** remove that action. Waiting events then cancel that branch, and the other
  branches keep running.
- **Go back to the previous Javis version:** see "Rollback" in `m1-durable-ingest.md` to `m4-security.md`.
  - Before rolling back, list events still waiting or unknown with
    `GET /webhooks/events?status=queued` and `?status=unknown`.
  - Re-enter header values in plain form, because older versions cannot read the encrypted references.
  - Switch the old hook back ON in POSCake if you used a new one.
- **Nothing is lost by switching back**: idempotency keys are still mirrored into `webhooks.json` for the older
  version.

## When POSCake's contract is confirmed

Add a `poscake` adapter to `server/webhook_verify.py`: the signature header and scheme, the event name and the
delivery id. Build its test from a captured delivery (secrets removed), and mark it `spec`. Mark it
"production verified" only after a real delivery passed on staging.
