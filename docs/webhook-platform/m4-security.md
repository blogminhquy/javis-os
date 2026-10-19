# Webhook platform, M4: signatures, encrypted secrets, tools, approval (0.229.0)

Status: implemented and tested with fakes. The tool dispatcher in the tests is a fake, and every signature was
computed in the test from the provider's documented scheme. **No adapter is production verified.** Stripe, GitHub,
Shopify and generic HMAC follow the providers' published schemes. **Systeme.io is unverified**: it was built from
public descriptions only, and its fixture is synthetic. **POSCake is not implemented**: its contract is unknown and
was not guessed. Spec of record: `docs/superpowers/specs/2026-10-19-webhook-event-platform-design.md`, still not in the
repository.

## Signature check per provider

`verify` on the hook (`POST /webhooks`, `POST /webhooks/update`):

| provider | Header | Scheme | Replay | Delivery id (when the sender sends no Idempotency-Key) | Status |
|---|---|---|---|---|---|
| `none` | | the Javis token only (default) | | | |
| `stripe` | `Stripe-Signature: t=..,v1=..` | HMAC-SHA256 of `t.body`, any `v1` | 5 min | event `id` | spec |
| `github` | `X-Hub-Signature-256: sha256=<hex>` | HMAC-SHA256 of the body | | `X-GitHub-Delivery` | spec |
| `shopify` | `X-Shopify-Hmac-Sha256: <base64>` | HMAC-SHA256 of the body | | `X-Shopify-Webhook-Id` | spec |
| `hmac_sha256` | your `header`, `hex`/`base64`, optional `prefix` | HMAC-SHA256 of the body, or of `timestamp.body` with `timestamp_header` | `tolerance_s` (30 to 3600) | | spec |
| `systeme_io` | `X-Webhook-Signature: <hex>` (assumed) | HMAC-SHA256 of the body (assumed) | | `X-Webhook-Id` (assumed) | **unverified** |
| `poscake` | refused when saved: "contract not known" | | | | not built |

Order on receipt:
1. Javis token (always).
2. Size.
3. Signature on the RAW body.
4. Rules (M2).
5. Commit.

A bad signature answers 401, and nothing is stored: no event, no key. A secret that cannot be read (lost key file)
answers 503, so the sender retries later. The secret is never compared with `==`: `hmac.compare_digest` is used.

Normalisation: the adapter sets `_event = {provider, type, id, occurred_at}` (Systeme.io adds `contact`). Rules read
it, for example `{"path": "_event.type", "op": "eq", "value": "contact.created"}`. Javis always sets `_event` (empty
without a provider), so a payload can never forge it.

## Encrypted secrets

`server/webhook_secrets.py`. Header values of actions and the signing secret leave `webhooks.json`. The vault keeps
them AES-256-GCM encrypted in `STATE_DIR/webhook_secrets.json`, with the secret's name as associated data. The hook
keeps `{"$secret": "<hook>/a/<action>/<header>"}` or `{"$secret": "<hook>/verify"}`.

- Keys live in `STATE_DIR/webhook_keys.json`. Both files are mode 600, written atomically (temp file, fsync, rename).
- `JAVIS_WH_MASTER_KEY` (base64 of 32 bytes) replaces the key file.
- Rotation: `POST /webhooks/secrets/rotate` runs in three steps, (1) both keys in the key file, (2) every secret
  re-encrypted under the new key, (3) the old key dropped. A crash after any step leaves every secret readable. If
  one secret cannot be read, nothing is changed (409).
- Plain values saved before M4 are sealed at start (`_migrate_secrets`).
- Header values come from the hook as it is at run time, so a rotated API key applies to waiting events. A secret
  that no longer decrypts fails its branch with "enter it again". The server keeps working.
- Deleting a hook deletes its secrets. Removing a header or a signature check deletes that secret.
- Never shown: the view masks values (`••••`). Saving the masked view back keeps the stored secret, for the same
  provider only.

What this protects, honestly: a copied `webhooks.json` (backup, export, a pasted file) holds no secret, and the
secrets file alone is useless. Someone who can read the whole state folder reads the key file too, as with any local
app that must use a secret unattended. **Back up `webhook_keys.json` together with `webhook_secrets.json`.**

## Tools through the dispatcher, with approval

```json
{"id": "pos", "kind": "tool", "tool": "pos_create_order",
 "args": {"phone": "{phone}", "note": "Webhook {name}", "ref": "{_delivery_id}", "qty": 1}, "approve": true}
```

- The call goes through the hub dispatcher (`mcp_hub.discover_all(level)` route, or `javis_run_tool` when the lazy
  menu is on). That route applies the same permission guard as any background run at the hook's level: a `danger`
  tool needs `full`, and the connection's own limit, the rate limit and the audit log all apply. `server/main.py`
  `_webhook_call_tool`.
- Arguments: text may use `{field}` (M2 mapped fields), `{_delivery_id}`, `{_event_id}` and `{_hook_id}`. This is
  one substitution pass (`render_template`): text from the payload is never expanded again and never evaluated. Pass
  `{_delivery_id}` to a tool that dedups.
- Outcome: `ERROR:` means `failed` (only that branch). Timeout (120 s) or a broken call means `unknown`.
- **Approval**: `approve` is `true` by default for `tool` and may be set on any action. The branch waits as
  `approval`, the event is `waiting`, and the owner is told which actions wait. `POST /webhooks/events/approve`
  `{id, action, decision: approve|reject}`:
  - approve: the branch runs at the next pass and is checked again against the hook's current level, so approval
    never lifts a permission;
  - reject: the branch is cancelled.

  Approval is asked only after the permission check, so nothing the hook may not do is offered. The payload cannot
  set `approve`, because it is read from the hook's config. Approving twice is refused (409).

## Invariants and their proof

All in `tests/python/test_webhook_security_m4.py` unless noted.

| Invariant | Test |
|---|---|
| No ACK and no dedup before commit, and not before the signature | bad signature: 401, no event, no key; the Javis token is still required |
| Replay | Stripe timestamp older than 5 min refused; generic HMAC outside `tolerance_s` refused |
| Provider retry is a duplicate | Stripe event id, GitHub delivery id: second delivery `duplicate` |
| No secret leak | `webhooks.json` holds references only; view masked; ciphertext bound to its name; files mode 600 |
| Key rotation | rewrapped, old key dropped, values unchanged; rotation cut after step 1 still readable; env key path; refused when a secret is unreadable |
| No forged `_event` | a payload with `_event.type` on a hook without provider: filtered |
| No blind tool retry | hung tool: `unknown`; `ERROR:` fails only its branch; the owner's Retry runs it once |
| Approval does not escalate | level lowered while waiting: the tool is called at the new level; approve twice refused |
| Payload cannot escalate | `approve`/`level` in the payload ignored; template text not re-expanded |
| Non-AI never calls a model | tool-only hooks: model runner never called |
| POSCake not guessed | `provider: poscake` refused with the reason |
| UI | `tests/js/test_webhooks_ui_m4.js` |

## Assumptions to reconcile with the spec

1. The Systeme.io header names and signature scheme (above). Confirm them on a real account, then mark the adapter
   `spec` and replace the synthetic fixture with a captured delivery (secrets removed).
2. Approval by default for `tool`, and an approval is valid for the owner's later retries of that event.
3. Rotation is by the owner (route), not on a schedule. There is no key escrow.
4. The tool timeout is 120 s, and any `ERROR:` answer counts as "not done". A tool that acted and then answered an
   error would be retried by the owner; pass `{_delivery_id}` to tools that can dedup.

## Rollback

- To M3 code: hooks now hold `{"$secret"}` references, which M3 would send as broken header values. Before rolling
  back, re-enter the header values in plain form (M3 accepts them), or remove those actions. Signature checks are
  ignored by M3, so the Javis token stays the only check.
- `webhook_keys.json` and `webhook_secrets.json` can stay. Older code ignores them.
