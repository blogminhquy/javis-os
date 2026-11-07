# Kanban question notification diagnostic checkpoint

This is a diagnostic draft, not a notification behavior fix. Maintainer review is requested before any behavior change or deployment.

## Scope and evidence boundary

Base: `75422b3e398dcd035cc1c94a1c6a14da37993785` on upstream `main`.
A reported installation runs 0.488.0; its deployed Git SHA is unavailable. The upstream base reports 0.490.1. These are different builds; do not assume their behavior is identical.

Read-only inspection found a real task blocked at needs_input, with two separate unanswered-question episodes. Each episode had a task event, an inbox item classified as question/urgent, the correct originating web session and a persisted assistant message in that session. The second inbox item was unread and neither item was policy-filtered. Private task identifiers, content, recipients and device identifiers are deliberately excluded.

This evidence does not reproduce a producer, routing or policy failure. An unread inbox record proves server persistence, not that a device displayed it. A persisted chat message proves server delivery to that chat, not that a WebSocket frame was seen by the browser.

## Layer map

- Producer: TasksFeature._report -> _bao_cau_hoi, keyed by task, question ordinal and question hash.
- Policy: _notify_decide -> notify_policy; questions default to urgent, while normal completed jobs remain quiet.
- Inbox/bell: _bo_vao_hom_thu persists inbox.add and publishes the inbox WebSocket event.
- Chat: _notify_owner -> _gui_qua_kenh -> push_to_chat.
- Push: _bo_vao_hom_thu schedules webpush.gui_het. The push return value is not a durable per-notice delivery receipt. Subscription status describes a device's latest attempt, not this particular notice.
- Telegram: explicit web routing does not imply Telegram delivery. No Telegram send was performed for this investigation.

Historical server stdout and device-side receipts were not available. Do not equate absence of a durable push receipt with a failed push.

## Safe reproduction

`python tests/python/test_kanban_notice_path.py`

The test uses a temporary state directory, a synthetic task and session, the actual worker needs_input transition and the real producer/policy/inbox path. Both external channel delivery and web push are mocked. It checks urgent classification, one inbox item, the original chat, bell publication, a mock push call, persisted dedup after inbox reload, a new question, owner mute/off and quiet normal completion. It imports the existing Kanban test harness rather than copying its worker implementation.

Inbox reload is not a whole-server restart or process-crash test. Mocked channel calls are not proof of live browser, Telegram or push-provider receipt. No owner device or external account is contacted by the reproduction.

## Unresolved recovery questions

The code files the inbox item before chat delivery and push completion, then short-circuits a repeated dedup key. There is no per-channel receipt in that path. This is a candidate partial-delivery recovery gap, not evidence that it caused the reported incident. A behavior fix needs a separate failure-injection test and an agreed delivery contract.

Before marking this draft ready, capture sanitized per-notice correlation across producer, policy verdict, inbox persistence, routing, chat append/WebSocket, push scheduling/provider response and device receipt. Record only internal notice keys, stage outcomes and error classes; avoid message bodies, endpoints, secrets and personal recipient identifiers. Compare deployed and upstream implementations first.

Still unverified: automatic retry/replay after transient failure, true process restart dedup, crash between filing and delivery, multi-user/brain recipient isolation under partial failure, and device display. No recovery or notification-storm fix is claimed. Do not replay real blocked tasks to obtain these traces; use isolated synthetic state and mocks.

## Operational constraints

Keep urgent-only defaults, owner mute/off and existing channel permissions. Do not enable global notification groups, copy web notices to arbitrary Telegram users, replay private questions, deploy, restart production or merge this diagnostic draft.
