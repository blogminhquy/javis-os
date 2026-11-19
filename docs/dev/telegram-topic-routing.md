# Telegram topic routing

Topic destinations are stored as `<chat_id>:topic:<message_thread_id>` in existing durable recipient fields.
Unthreaded identifiers remain unchanged. The transport splits destinations into Telegram API fields only at send time.

## Behavior

- Incoming Telegram metadata retains the raw chat ID for admission checks and includes the thread ID.
- The queue, steering inbox, stop/reset, engine sessions and stored conversation links are topic-specific.
- Text chunks, status messages, typing, media fallbacks and callbacks preserve the originating topic.
- Reminder, loop and Kanban tools inherit the topic from host turn context when no different recipient is specified.
- `/topic <group>` binds a notification group to the current topic on the owner bot. `/topic` lists routes and keys;
  `/topic off <group>` removes one. The caller's parent chat must already be on the owner bot's allow-list.
- Notification group defaults apply to untargeted notices and notices explicitly addressed to the owner chat.
  An explicit other recipient or explicit topic takes precedence. A web-addressed job still reports to its web chat.
- Group defaults do not bypass notification filtering or recipient allow-lists.
- Closed, deleted or inaccessible topics are not retried in General. The existing inbox retains background reports.
- Settings routes live in `telegram.topic_routes`, separate from release code. No existing reminders are edited.

## Boundaries

This patch does not create topics or change the Telegram allow-list. The target forum/group must exist and the bot
must have permission to send there. Topic mode in a private bot chat also depends on Telegram support and settings.
The feature does not move old messages between topics.

The chatbot inbox currently stores messages without a topic discriminator. Topic engine sessions and reply-policy
windows are separated, and threadless shared inbox history is deliberately excluded from topic prompt bootstrapping.
The chatbot inbox UI itself is still grouped by chat. No claim is made that its manual reply composer selects topics.
This patch does not change which bot token the existing background reporting service uses.

## Validation

Run `python tests/python/test_telegram_topics.py`, the existing Telegram agent/session/model/status regressions,
`test_bot_private_history.py`, and `python tools/release.py check`. Tests use scratch state and fake HTTP; no bot
credentials or outside messages are required. Live Telegram delivery and release CI still require integration testing.
