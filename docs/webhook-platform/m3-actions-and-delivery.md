# Webhook platform, M3: actions, branches, delivery ids (0.274.0)

> **Spec alignment (0.274.0).** This note was written from the owner's brief, before the spec of record arrived. Where it differs, the spec and `README.md` (requirements matrix) win. What changed here: deliveries follow the spec's states (succeeded, accepted, unknown, blocked, waiting, dead, cancelled), retry 1 / 5 / 30 minutes with jitter, 4 attempts, 24 h, `retry_safety`; 5xx, timeouts and any redirect after a POST are unknown; 401 / 403 and plugin or permission problems are blocked; `depends_on`; the plugin contract adds retryable_error, permanent_error, unknown and waiting_approval; replay makes a new generation under the current revision. The "Assumptions to reconcile" below are settled by that matrix.

Status: implemented and tested with fakes. No request reached a real receiver: every HTTP call in the tests goes to an
`httpx.MockTransport`, every plugin is a fake or a temporary test plugin, and every model runner raises if called.
**Not verified against a real Apps Script deployment, a real CRM or a real plugin.** Spec of record:
`docs/superpowers/specs/2026-10-19-webhook-event-platform-design.md`, still not in the repository. The choices below
are from the owner's brief, and the open ones are listed under "Assumptions to reconcile".

## What a hook does with an event

A hook may list `actions`. Each action runs as an independent BRANCH of the event:

```json
[{"id": "crm",   "kind": "http", "url": "https://crm.example.com/hooks/order", "body": "fields",
  "headers": {"X-Api-Key": "..."}, "retry": "never"},
 {"id": "sheet", "kind": "apps_script", "url": "https://script.google.com/macros/s/<deployment>/exec"},
 {"id": "ship",  "kind": "plugin", "plugin": "giao-hang", "handler": "new_order"},
 {"id": "ai",    "kind": "ai"}]
```

A hook without `actions` has one branch, `main` of kind `ai` (its task or workflow), which is the behaviour before M3.
`ai` is the only kind that calls a model.

| Field | Meaning |
|---|---|
| `body` | `fields` (the M2 mapped fields plus `_javis`), `event` (`fields`, `payload`, `_javis`), `raw` (the original body and content type) |
| `headers` | the action's own headers (at most 10). `Cookie`, `Host`, `Content-Length`, `Idempotency-Key`, `X-Javis-Delivery` are refused. Values are masked in the dashboard, never copied into the event store, and taken from the hook at run time (a rotated key applies to waiting events) |
| `retry` | `never` (default) or `safe`: the receiver drops a second copy with the same `Idempotency-Key`, so an ambiguous failure may be re-sent |
| `timeout_s` | 1 to 60 (default 15; Apps Script 30) |
| `allow_private` | allows a loopback/private address (and `http://`) for a receiver on the owner's own network |

## Delivery id

Each branch has a delivery id, `dlv_<hash of event id and action id>`. It never changes for that branch: not on an
automatic re-send, not on the owner's Retry. It is sent as `Idempotency-Key`, as `X-Javis-Delivery`, and as
`_javis.delivery_id` in the body. Javis does not promise exactly-once delivery: a receiver that keeps the delivery id
can drop the second copy.

## Outcomes

| Outcome | When | What happens next |
|---|---|---|
| `completed` | 2xx; Apps Script receipt `ok: true`; plugin `completed` | done, never run again |
| `accepted` | 202; plugin `accepted`; Apps Script `accepted: true` | the receiver finishes on its own (the plugin keeps its scheduling and waiting); never run again |
| `retry` | not sent (connect/DNS error); 429 or 503 (the receiver says it did not process it) | re-sent with the same delivery id after 10 s, 60 s, 300 s (or `Retry-After`, at most 1 h); after 3 tries `failed` |
| `unknown` | timeout after sending, 5xx, dropped connection, 301/302/303 after the POST (Post/Redirect/Get: it may have been done), plugin did not answer in 60 s, crash after dispatch | the owner decides (Mark done / Retry). With `retry: safe` it is re-sent instead |
| `failed` | 4xx, 307/308, bad receipt, blocked address, permission, plugin missing or raising, Apps Script asking to sign in | the owner's Retry runs it again (with fresh tries) |
| `cancelled` | the action was removed, or now sends somewhere else (kind, address, allow_private, plugin, tool), since the event arrived | not run |

The event's state follows its branches. A branch still to run (pending, or waiting to be re-sent) puts the event back
in the queue first, so an unknown sibling never stops a busy receiver's resend. Then any `unknown` makes it
`unknown`, any `failed` makes it `failed`, a workflow waiting for an answer makes it `waiting`, and otherwise it is
`done`. The AI branch is the hook's task whatever its id (`main` or `ai`): it runs as long as the hook still has a
task. **A retry, automatic or by the owner, runs only the branches that are not done.** The
others keep their outcome.

## Apps Script: redirect and receipt

`doPost` runs when Google receives the POST. Google then answers `302` to a one-time address on
`script.googleusercontent.com` that holds the script's output. Javis:

1. POSTs once to the `/exec` address and does not follow redirects. A POST is never repeated.
2. Reads the `Location` with a plain GET (no body, none of the action's headers), and only on
   `script.googleusercontent.com`. Any other host is `unknown`, because the script may have run.
3. Treats the JSON it gets as the receipt. `{"ok": true}` means completed. It must echo `delivery_id` when it sends
   one, and a receipt naming another delivery is refused. `{"ok": false, "error": ...}` means failed. Google's
   sign-in page means failed, with the hint that the deployment must allow "Anyone".

A script that keeps the delivery id makes a second copy harmless:

```javascript
function doPost(e) {
  var body = JSON.parse(e.postData.contents);
  var id = body._javis && body._javis.delivery_id;
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var props = PropertiesService.getScriptProperties();
    if (id && props.getProperty(id)) {
      return out({ok: true, delivery_id: id, duplicate: true});
    }
    var sheet = SpreadsheetApp.getActive().getSheetByName("Orders");
    sheet.appendRow([new Date(), body.order_id, body.email, body.total]);
    if (id) props.setProperty(id, String(sheet.getLastRow()));
    return out({ok: true, delivery_id: id, row: sheet.getLastRow()});
  } catch (err) {
    return out({ok: false, delivery_id: id, error: String(err)});
  } finally {
    lock.releaseLock();
  }
}
function out(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
```

Script properties hold about 500 KB, so clear old ids now and then (for example with a time-driven trigger), or keep
them in a sheet column.

## Plugin handlers

A plugin registers a handler in `register(ctx)`:

```python
def register(ctx):
    def new_order(delivery, ctx):
        # delivery: delivery_id (stable: keep it, drop a second copy), event_id, hook_id, action_id, brain,
        #           fields, payload, level
        job = queue_shipment(delivery["fields"], key=delivery["delivery_id"])
        return {"status": "accepted", "ref": job.id}       # or "completed" when done now
    ctx.register_webhook_handler("new_order", new_order, min_mode="full", description="Create a shipment")
```

- Only an ENABLED plugin visible to the hook's brain is found: that brain's own vault plugins, plus bundled, pack
  and global ones. Another brain's vault plugin never is (`plugins_host.find_webhook_handler`).
- `min_mode` is checked against the hook's level AT RUN TIME (`readonly` any level, `safe` auto and full, `full`
  full only).
- A plain function runs in a thread of the handlers' own pool (4 threads), so a handler that hangs cannot use up the
  server's shared pool. When all 4 are busy, a branch is not sent and retries later. A handler that takes more than
  60 s is `unknown`, because it may have acted. Raising, or any answer other than `completed` or `accepted`, is
  `failed`.

## Permissions and safety

- `http` and `apps_script` send data out, so they need the hook at level `full`. The level used is the lower of the
  snapshot and the hook's current level (M1).
- The incoming request's headers (cookies, tokens) are never forwarded.
- Every resolved address must be public: loopback, private, link-local (169.254.169.254, the cloud metadata
  address), CGNAT, multicast, reserved and IPv4-mapped forms are refused unless `allow_private`. Redirects are not
  followed. Residual risk: DNS can change between the check and the connection (rebinding). The check reduces
  this risk but does not remove it.
- `JAVIS_WH_NO_NETWORK=1` makes the default transport refuse every request. Tests use it as a fail-fast guard.
- Only an `ai` branch reaches Javis Core's incident triage. A hook with only outside actions never calls a model.

## Where it sits

| Piece | Where |
|---|---|
| Validation, delivery ids, HTTP / Apps Script / plugin runners, address check | `server/webhook_actions.py` |
| Branch rows, dispatch before effect, outcome, per-branch recovery, retry of the unfinished branches only, resolve | `server/webhook_store.py` (`branches`, `branch_*`, `summarize`, `requeue_branches`, `recover`, `retry`, `resolve`) |
| Runner: branches in parallel, current-permission checks, removed actions cancelled, secrets from the current hook | `WebhookFeature._run_event` |
| Plugin handler registry | `plugins_host.PluginContext.register_webhook_handler`, `find_webhook_handler`, `webhook_handlers` |
| Dashboard: actions box, Details per event (branches, delivery id, receipt ref, trace) | `dashboard/webhooks.js` |
| Wiring | `server/main.py` (`plugin_handler`) |

## Invariants and their proof

All in `tests/python/test_webhook_actions_m3.py` unless noted.

| Invariant | Test |
|---|---|
| No blind retry | 500, timeout, dropped connection, hung plugin: `unknown`, not re-sent; 503/429/not-sent re-sent with the same delivery id, then `failed` |
| A successful branch is not re-run | branch `crm` unknown, the others done; the owner's Retry calls only `crm` (same delivery id), not the Apps Script, the plugin or the model |
| Branches are independent | one branch failing or unknown does not stop the others |
| Crash mid-event | child killed after the HTTP effect: on recovery both dispatched branches are `unknown`, nothing is re-sent, the owner resolves |
| Apps Script redirect | one POST, then one GET on the echo host only, without the action's headers; a sign-in page, a refusal or another delivery's receipt is not a success |
| Current permissions | at level `auto`, HTTP and Apps Script are refused and a `safe` plugin runs; an action removed while the event waited is `cancelled` |
| No secret leak | header values are masked in the view, absent from the event snapshot and the notice; a rotated key applies to a waiting event; saving the masked view keeps the key |
| No cross-brain plugin | a handler visible to another brain is not found; a vault plugin's handler is found only for its brain |
| No SSRF to private ranges | 127/8, 10/8, 192.168/16, 169.254.169.254, ::1, ::ffff:127.0.0.1, 100.64/10, 0.0.0.0, fd00::/8 refused; a name resolving to any private address is refused |
| Non-AI never calls a model | a hook with only an HTTP action: model runners raise if called, no incident triage |
| No network in tests | `JAVIS_WH_NO_NETWORK=1`: the default transport refuses |
| UI | `tests/js/test_webhooks_ui_m3.js` |

## Assumptions to reconcile with the spec

1. **Action language**: a JSON list on the hook, with kinds `http`, `apps_script`, `plugin`, `ai`.
2. **Retry classes**: only certainly-not-processed failures re-send by themselves. `retry: safe` is the owner's
   statement that the receiver dedups.
3. **Backoff** 10/60/300 s, 3 tries, `Retry-After` honoured up to 1 h.
4. **Apps Script receipt format** `{"ok", "delivery_id", "duplicate"?, "accepted"?, "error"?}`. The spec may define
   another one.
5. **Plugin contract** `handler(delivery, ctx) -> {"status": "completed"|"accepted", "ref", "detail"}`, with a 60 s
   timeout and `min_mode` defaulting to `full`.
6. **Headers as secrets**: stored in `webhooks.json` (mode 600), masked, never in the event store. M4 encrypts them
   with key rotation.
7. **Order of branches**: all branches of one event run in parallel. There is no dependency between them (no "send to
   the CRM, then the sheet with the CRM's id").

## Independent review (M3)

The review of f66c0012, read at d86a15a2, found 1 P1 and 6 P2 issues, all reproduced. All are fixed, with
regression tests in `tests/python/test_webhook_m3_review.py`, which fail on the reviewed commit.

| Finding | Fix |
|---|---|
| P1 a stored header key followed its action to a new address: to a waiting event's old address after an edit, or to any address when the masked view was saved back | a key follows only the same target (`same_target`: kind, address, allow_private, plugin, tool). Saving the mask with a new address is refused ("enter header again"). A waiting event whose action now points elsewhere is `cancelled` |
| P2 hung plain-function plugins used up the shared thread pool: no more ACKs, heartbeats or sweeps | the handlers' own bounded pool. When it is full, the branch is "not sent" and retries later |
| P2 a waiting event's AI run was cancelled and reported done after the owner edited the actions | the AI branch is identified by kind, not by id |
| P2 Apps Script timed out at 15 s; a sign-in redirect was `unknown` | 30 s default; the sign-in redirect is `failed` with the "Anyone" hint |
| P2 an unknown branch stopped a sibling's resend; Mark done then made the event failed | runnable branches first in `summarize`; resolve requeues when a branch still has to run |
| P2 302/303 after a POST counted as refused | 301/302/303 are `unknown`; 307/308 are `failed` |
| P3 (fixed) | a late outcome is kept next to its branch; a run whose lease was taken over is stopped (no two runs at once); `[SILENT]` text never reaches the notice; the owner's retry resets tries; `Retry-After` as an HTTP date; `allow_private` only as boolean `true`; header values printable ASCII; the owner's `Content-Type`/`User-Agent` not duplicated; Test events carry `_javis.test`; answers read up to 64 KB; a receipt is never cut mid-JSON; a branch refused before dispatch releases the business key once the event dies; a gone brain folder looks up no brain's vault plugins; the unknown notice gives the receiver's reason |
| P3 (kept, noted) | action URLs (an Apps Script `/exec` address is a bearer secret too) are stored in the event snapshot and shown in the actions box: put real secrets in headers, which are encrypted (M4) |

## Rollback

- To M2 code: the `branches` table is ignored. A hook with `actions` falls back to its task/workflow (every event
  runs the AI branch only). Remove the actions first if that is not wanted.
- An event that was mid-branch at rollback time shows as `running`/`unknown` in M2's log. Resolve it before rolling
  back, using `GET /webhooks/events?status=unknown`.

## What still needs a real source

- An Apps Script web app deployed with "Anyone" access, called once with the template above, to confirm the
  302/echo flow and the receipt (staging pack, `docs/webhook-platform/staging-pilot-pack.md`).
- A receiver that honours `Idempotency-Key`, before any action is set to `retry: safe`.
