# Rolling the webhook platform back (0.274.0, spec §13)

**What a rollback can and cannot do.** Going back to an older Javis build changes the program. It does not undo what
actions already did outside: an order written to a sheet, a Zalo message sent, a CRM record created. Reconcile those
from the receipts before resending anything. The new store (`webhook_events.sqlite3`) is kept as it is, so a later
upgrade picks up where it stopped.

## Why a tool is needed

From 0.274.0 the hooks live in the store, and `webhooks.json` was moved aside to `webhooks.json.migrated` (a copy is
kept as `webhooks.json.pre-0.241-<time>.bak`). An older build started by mistake finds no hook list, so it cannot run an
old configuration beside the new store. A deliberate rollback writes a list the older build can read, with
`server/webhook_rollback.py`, and only that.

## Steps

1. **Stop the server** (`systemctl stop javis`, or close the app). The tool refuses while an event is running under a
   live lease. Pass `--force` only if the server is certainly stopped (for example, it crashed).
2. **See what will happen**, writing nothing:

   ```
   .venv/bin/python server/webhook_rollback.py --state-dir <STATE_DIR> --check
   ```

   The report lists:
   - each hook that will be written **switched off** for the older build, with the reason: actions other than its own
     task, rules, a provider signature, a custom token header, paused processing;
   - every event not settled yet (received, queued, running, unknown, waiting, blocked).
3. **Run it**:

   ```
   .venv/bin/python server/webhook_rollback.py --state-dir <STATE_DIR>
   ```

   It does, in this order:
   - backs the store up with SQLite's backup API: `webhook_events.backup-<time>.sqlite3` (mode 600);
   - exports every unsettled event with its body and deliveries to `webhook_rollback-<time>/backlog.jsonl` (mode 600);
   - writes `webhooks.json` for the older build;
   - records each hook's own switches (enabled, paused) and which hooks it switched off;
   - holds every exported event as **unknown** ("exported at rollback"), so no upgrade later runs it on its own beside
     a manual resend;
   - clears the migration marker and writes `report.txt`.
4. **Install the older build** and start it. Hooks without new features work as before. The ones written off stay off:
   they need what the older build does not have.
5. **Reconcile the backlog** from `backlog.jsonl`. For each event, check the outside system for its delivery id
   (`X-Javis-Event-Id`, `_javis.delivery_id`, the plugin's job id). Resend from the source, or by hand, only what did
   not happen.

## Coming back to 0.274.0 or later

Start the newer build. It imports `webhooks.json` once more:
- each hook gets back its OWN switches (a hook the tool switched off only for the older build is on again, a paused hook
  is paused again);
- changes made in the older build (name, token, target, text, level) become a new revision;
- a hook deleted in the older build stops receiving (kept with its log, audited, not deleted);
- the events held at rollback stay **unknown**: open the Events part, filter "Needs you", and press Mark done (it
  happened) or Retry (it did not) for each, after checking the receipts.

## What is kept, what is lost

| Kept | Lost or not carried |
|---|---|
| The whole store (events, deliveries, receipts, audit), backed up first | Nothing is deleted by the tool |
| Hook ids, tokens (hash), names, brains, chats, levels, history | Actions, rules, signatures and pause, while the older build runs (the hooks using them are off) |
| Delivery keys the older build reads (`seen_keys`, the last 50 per hook) | Events received by the older build are not in the store: they ran there |

The tool is covered by `tests/python/test_webhook_spec_matrix.py` ("§15 Tương thích / §13") and
`tests/python/test_webhook_spec_review.py` (the rollback cycle: switches restored, deleted hooks stopped, held events not
run).
