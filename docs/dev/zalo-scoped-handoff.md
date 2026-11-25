# Scoped Zalo pricing and case handoff

This feature lets a personal Zalo bot at `auto` request a service price and deliver a confirmed case to one owner-configured contact. Generic send tools remain subject to their existing permission checks.

## Configuration

An owner sets `price_contact` through the existing bot update API. Example with placeholder values:

```json
{"price_contact": {"account_id": "configured-zalo-account", "thread_id": "staff-private-thread", "label": "Case staff"}}
```

The bot must have that account assigned, and the account must be enabled with full send permission. The model cannot choose a different recipient. The feature currently has no dashboard configuration control.

## Flow

- Call `javis_request_service_price` with an empty object to read bounded conversation context. Supply a concise service description and supporting source message IDs to request a price. Read the conversation to resolve short requests such as "please quote".
- Use `javis_service_price_requests` and `javis_service_price_reply` in the configured staff conversation to associate a quote with its customer.
- After the customer confirms the service and fee, call `javis_handoff_confirmed_case`. Read context first and supply the company, scope, fee, confirmation reference, and supporting message references.
- For incorporation, use `case_type="new_company"` and omit the tax ID. The company name must occur in the selected sources. For existing companies, the tax ID must occur in the selected sources.
- Select relevant customer image references from `image_messages` using `image_message_ids`. Staff images, earlier case images and arbitrary paths are excluded. If available images are unrelated, explain using `no_case_images_reason`.
- The fixed customer acknowledgement is sent only after text and all requested images have successful receipts. Inspect `attachments` and `customer_notified` before claiming completion. The prompt instructs the bot to stay silent after the tool has already acknowledged the customer.

## Delivery and limits

Delivery state is stored in `bot_price_requests.sqlite3` under the configured state directory. Text, each image, and customer acknowledgement have separate durable claims. Calls can resume completed stages without repeating them. A timeout after a send has uncertain delivery and is not automatically resent; an operator must inspect actual delivery before retrying manually.

Context is bounded to the current conversation and current message, using up to 80 recent messages. Attachments use the existing validated image fetcher and account outbox, and temporary files are cleaned up. This does not add a general cross-chat send permission.

## Verification

`python tests/python/test_bot_price_request.py` exercises pricing scope, context references, handoff validation, new companies, images, partial delivery, retries, acknowledgement, revoked permission and ordinary-send denial with mocked delivery. No real Zalo message is sent.

This contribution integrates feature code into the upstream source. Installation-specific `.pth` hooks, backup archives and local patch manifests are intentionally not part of it.
