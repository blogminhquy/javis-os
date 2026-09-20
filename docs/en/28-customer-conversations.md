# Customer conversations (Inbox)

*[Tiếng Việt](../28-hoi-thoai-khach.md) · **English***

Every message a customer sends to a **dedicated bot** (Telegram or Zalo Bot) and to a connected **personal Zalo account** is gathered into one inbox inside Javis. You read the exchange between the customer and the bot, see which chats the bot is stuck on, and **take over** a chat when a human is needed.

This is the first release of the Conversation layer of Chatbot V2: a **viewer** plus takeover. Replying to customers straight from Javis, customer cards and follow-up reminders come in later releases, on this same data foundation.

## Where to open it

Left navigation, group **Capabilities**, item **Conversations**. On the **Chatbots** page every bot card has a **Conversations** button that opens the inbox filtered to that bot.

Voice works too: "open the customer inbox", "show customer messages". Saying just "conversation" still opens the Chat page as before.

## The model

Four concepts, read once and never guess again:

| | What it is |
|---|---|
| **Chatbot** | An AI employee: an Agent, its own brain, a permission level, the channels it may stand on. |
| **Channel** | Where customers write: Telegram, Zalo Bot, personal Zalo. Later Zalo OA, Facebook, Web Chat. |
| **Conversation** | One exchange with one customer (or one group) on one channel. |
| **Inbox** | Where AI and humans run conversations together: read, take over, hand back. |

Underneath, every channel normalizes its messages into **one common event** and writes into one store: channel account, customer, conversation, message. The inbox never needs to know whether a message came from Telegram or Zalo.

## The Conversations page

The top shows four numbers: total conversations, conversations active today, unread, and chats currently handled by a human.

The left column lists conversations, newest first. Each row: the customer (or group) name, the channel logo, the last message, the time, and the unread count. There is a search box for names or text, channel chips (shown only once two channels exist) and a bot selector (shown only once two bots exist).

Click a conversation and its history opens on the right: customer messages on the left, bot replies and messages you sent from your phone on the right. A failed bot turn sits there too, with its technical reason, so you can tell "the bot answered wrong" from "the bot is broken".

On a phone the page is one column: tap a conversation to open its history, with a back button. The page refreshes itself every few seconds.

## Take over and hand back

At the top of a bot conversation there is a **Take over** button. Press it and the bot goes **quiet in that one chat**: customer messages still land in the inbox, but Javis no longer calls the engine to answer. You reply in the Telegram or Zalo app as usual, then press **Hand back to AI**.

Two things to know:

- A bot turn already in progress when you press Take over still sends its reply. Cutting off a message mid-send is more confusing for the customer.
- Takeover is **per chat**, not a bot switch. Other customers keep getting bot replies.

## Channels feeding the inbox

Press **Channels** at the top of the page to see the sources.

**Dedicated bots** record automatically while enabled. Nothing to install: every bot turn writes one customer message and one bot reply. The commands `/help`, `/id` and `/nhanvien` are conversation too, so they are recorded. Messages in groups the bot is not yet allowed in are **not** stored.

**Personal Zalo** matters for Vietnamese customers, because not every seller has a Zalo OA. Accounts you scanned a QR for on the **Connections** page (Zalo Agent MCP) appear here with a **Record conversations** switch. Turn it on and Javis reads new messages every 20 seconds through the MCP and writes them into the inbox.

Three plain facts about personal Zalo:

- **Off by default.** Turning it on keeps your Zalo session alive continuously through an unofficial API, meaning the account is signed in 24/7 on the machine running Javis. That is your choice, not Javis's. Use a secondary account.
- **Stored from the moment you turn it on.** No old history is pulled. Messages you send from your phone show as "You".
- **The bot does not reply over this channel yet.** Sending under your own identity deserves its own decision; in this release personal Zalo is a read channel.

## Where data lives and what is kept

The store sits in the Javis state folder (`customer_conversations.sqlite3`), separate from the chat session store. **Text** is kept long term; images, files and voice keep only the message type and a description, the original files follow Javis's normal cleanup. A message read twice (after a restart, say) never creates a second row.

Deleting a bot does **not** delete its conversations: customer history is your asset.

## For anyone adding a channel

A new channel only has to normalize its messages into the common event (`channel`, `account_id`, `external_chat_id`, `sender_type`, `text`, `external_message_id`, `created_at`) and call the store. The inbox and takeover work immediately, with no UI change. API:

- `GET /conversations` list with stats, filtered by `channel`, `bot_id`, `q`.
- `GET /conversations/{id}/messages` message history.
- `POST /conversations/{id}/read`, `POST /conversations/{id}/mode` (`ai` or `human`).
- `GET /conversations/channels`, `POST /conversations/zalo/{conn_id}/watch`.

## Troubleshooting

- **Bot enabled but no conversations**: the store only records from this release on; send the bot a test message. Still empty, check the bot's Log tab on the Chatbots page.
- **Personal Zalo shows a red error under Channels**: usually an expired QR session or a machine without Node.js 20. Check the Zalo connection on the Connections page and rescan the QR if needed. The reader retries after 90 seconds.
- **Pressed Take over but the bot still answered once**: that turn was already running before the click. From the next message on, the bot stays quiet.

## See also

- [Chatbot (a dedicated bot)](25-chatbots.md)
- [The Zalo Bot channel](26-zalo-bot-channel.md)
- [Zalo Agent MCP](12-zalo-agent-mcp.md)
