# Webhook platform, M2: rules, business keys, simulation, trace (0.229.0)

Status: implemented and tested with fakes (no real model, no real outside system).
Spec of record: `docs/superpowers/specs/2026-10-19-webhook-event-platform-design.md`. **Still not in the repository**
(checked on every remote branch). M2 was built from the owner's brief. Every choice the spec might decide differently
is listed under "Assumptions to reconcile".

## What a hook's rules do

`rules` is an optional JSON object on the hook (`POST /webhooks`, `POST /webhooks/update`), validated when saved
(`webhook_rules.validate`). It holds data only, never code. The module is `server/webhook_rules.py`.

```json
{
  "schema":  {"fields": {"data.order.id": {"type": "string", "required": true}}},
  "filter":  {"all": [{"path": "event", "op": "eq", "value": "order.created"},
                      {"any": [{"path": "data.order.total", "op": "gte", "value": 100000},
                               {"path": "data.vip", "op": "eq", "value": true}]}]},
  "mapping": {"order_id": {"path": "data.order.id", "transform": "trim"},
              "email": {"path": "data.customer.email", "transform": ["trim", "lower"]},
              "total": {"path": "data.order.total", "type": "integer", "default": 0},
              "title": {"template": "Đơn {order_id}"}},
  "business_key": {"namespace": "shop", "entity": "order", "field": "order_id", "type": "string", "ttl_s": 2592000}
}
```

Order of evaluation, identical at receipt and in simulation:

| Step | Outcome when it fails | Answer to the sender |
|---|---|---|
| parse (JSON, form, else `{"_text": ...}`) | never fails | |
| schema: required fields, types | `invalid`, logged, never runs, keeps **no** idempotency key (a corrected resend under the same key runs) | 422 with the reason |
| filter: `all` / `any` / `not` over conditions | `filtered`, logged, never runs | 200 `{"ignored": "filtered"}` |
| mapping: named fields, typed, transformed | a type error or missing `required` field is `invalid` | 422 |
| business key | already seen in its scope within its TTL: `duplicate`, logged with `duplicate_of` | 200 `{"duplicate": true, "reason": "business_key", "first"}` |

Operators: `eq ne in not_in exists missing gt gte lt lte contains starts_with ends_with empty not_empty`, with
`"case": "insensitive"` on string comparisons. A numeric string equals its number (`"150000"` = 150000); a boolean is
never a number. A missing path fails every test except `ne`, `not_in`, `missing` and `empty`.

Transforms: `trim lower upper digits string number integer boolean first join length`. Templates substitute
`{name}` of a field mapped ABOVE them, by a plain scan: no attribute access, no format spec.

Business key types: `string` (trimmed), `integer` (canonical, `"007"` = `7`), `email` (lowercase), `phone` (digits;
`+84 912...` = `0912...`). The key is `<entity>:<value>` in `<namespace>`, scoped to the hook's **brain**: two hooks of
one brain sharing a namespace share keys; another brain never matches. `on_missing`: `accept` (default, no dedup) or
`reject` (invalid).

Bounds: rules at most 8 KB, 40 conditions, nesting depth 4, 40 fields, paths of 12 segments, values of 2000 characters,
`in` lists of 50. No regex operator (ReDoS).

## Where it sits

| Piece | Where |
|---|---|
| Evaluation, pure and bounded, before the store transaction | `WebhookFeature._ingest` -> `webhook_rules.evaluate` |
| A bug in evaluation never drops an event: it runs unfiltered, the error is in its trace | `_ingest` |
| Decision, trace, fields, business key: stored with the event in ONE transaction | `Store.ingest(pre=...)`, `_ingest_ignored` |
| Business keys | table `biz_keys(brain, scope, bkey)`, `expires_at`, written with the event; pruned after TTL |
| Key given back when the event dies without running (hook off/deleted, too many losses before dispatch) | `Store._release_keys` |
| Key kept when a run failed after dispatch (it may have acted) | `Store.finish` |
| Ignored events do not count toward the hourly rate; their own log cap 300/hour, keep 200 per hook | `IGNORED_PER_HOUR`, `KEEP_IGNORED_PER_HOOK` |
| Mapped fields reach the run as DATA, inside the fence, markers neutralised | `event_prompt(..., fields)` |
| Rules revision in the snapshot | `hook_snapshot.rules_rev` |
| Simulation: stores nothing, runs nothing, sends nothing | `POST /webhooks/simulate` (`id`, `payload`, optional draft `rules`, or `event` to replay a logged body) |
| Trace in the event detail; business key in the log list | `GET /webhooks/events/{id}` (`trace`, `fields`), `GET /webhooks/events` (`biz_key`) |
| Dashboard: Rules button per card, JSON box, sample box, Test, Save | `dashboard/webhooks.js` (`rulesPanelHtml`, `simHtml`) |
| Store schema v1 -> v2 in place (columns `trace`, `fields`, `biz_key`; table `biz_keys`) | `Store.__init__` |

## Invariants and their proof

All in `tests/python/test_webhook_rules_m2.py` unless noted.

| Invariant | Test |
|---|---|
| Rules are data: no eval, no regex, no attribute access in templates | a code-looking value stays text; `{0.__class__}` is left as written; source check |
| Bad rules never get saved | unknown part/op, bad paths, depth, count, size, template order, TTL bounds; create and update refuse, old rules kept |
| No dedup before commit (business keys too) | child killed at `before_commit`: no event, no key; resend gets 202 |
| One business key accepted once under concurrency | 8 threads, 8 hooks, one key: one 202 |
| No cross-brain match or leak | same key in another brain: 202; replaying another hook's event: 404 |
| TTL | the same key after its TTL runs; prune removes expired keys |
| A key is not held by an event that never ran | dead and deleted-hook events give their key back; failed-after-dispatch keeps it |
| Ignored events never run, never notify, never eat the rate | 35 filtered then a real event: 202; no runner call, no notice |
| A flood of ignored events cannot push out real history | own log and retention caps |
| The payload cannot change level, target or instruction | `level`, `target`, `text` in the body are ignored; the run gets the hook's |
| Mapped fields stay data | fields block inside `<<< >>>`, markers from the payload neutralised |
| Simulation has no side effect | event and key counts unchanged, no runner call, no send |
| No model in the rules path | source check: no engine, store or network import |
| Upgrade in place | a v1 database opens as v2, keeps and still runs its events |
| Performance | full rules (schema, 9 conditions, 9 fields, key): about 0.2 ms per event here; bound 2 ms |
| UI | `tests/js/test_webhooks_ui_m2.js`: words for the new states, escaping, both languages |

## Assumptions to reconcile with the spec

1. **Rule language** is a JSON object with `schema`, `filter`, `mapping` and `business_key` as above. The spec may use
   JSON Schema, JSONata, JMESPath or its own DSL. The evaluator is isolated in one module so it can be swapped.
2. **State names** `filtered`, `invalid`, `duplicate`, decided at receipt.
3. **Answers to the sender**: 200 for filtered and duplicate (the sender must not retry), 422 for invalid. Some
   providers retry any non-2xx. If the spec says "always 2xx", the 422 becomes a 200 with `{"ignored": "invalid"}`.
4. **Business key scope** is (brain, namespace), shared by the hooks of one brain. Default TTL 30 days, between 60 s
   and 366 days.
5. **Phone normalisation** is Vietnamese only (`84` prefix -> `0`). Other countries are kept as digits.
6. **Ignored events are logged** (with body, for replay) up to 300 per hook per hour, then answered without logging.
7. **Evaluation failure** runs the event unfiltered rather than dropping it. The spec might prefer `invalid`.
8. **Retry** stays limited to failed, unknown and dead events. A filtered or duplicate event cannot be forced to run
   from the log; change the rules and resend, or replay its body in the simulator to check first.

## Rollback

- Reverting M2 to M1 code: the v2 columns and the `biz_keys` table are ignored by M1. Events already `filtered`,
  `invalid` or `duplicate` are finished rows M1 never claims. Rules saved on hooks are ignored (every event runs).
- Reverting to 0.228.0: as in the M1 doc. The store file is ignored.

## Not in M2

HTTP forward, Apps Script, plugin handlers and fan-out (M3) will read the mapped `fields` stored on each event.
Per-provider verification and the Systeme.io normalisation (M4) come before the rules.
