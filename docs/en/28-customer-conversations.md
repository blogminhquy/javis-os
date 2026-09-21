# Customer conversations (Inbox)

*[Tiếng Việt](../28-hoi-thoai-khach.md) · **English***

Every message a customer sends to a **dedicated bot** (Telegram or Zalo Bot) and to a connected **personal Zalo account** is gathered into one inbox inside Javis. You read the exchange between the customer and the bot, see which chats the bot is stuck on, and **take over** a chat when a human is needed.

Since 0.61.0 this page also holds the Chatbots: **one item on the rail, three tabs** (Inbox, Channels, Chatbots), and you **reply to customers right inside the Inbox**.

## Where to open it

Left navigation, group **Capabilities**, item **Conversations**. Inside, three tabs:

- **Inbox**: every customer message, read back, take over, reply.
- **Channels**: every account customers write to (Telegram bots, Zalo bots, personal Zalo...), add accounts, turn recording on.
- **Chatbots**: the AI staff on duty for those accounts. See [Chatbots](25-chatbots.md).

Voice works too: "open the customer inbox", "show customer messages", and "open chatbots" lands on the Chatbots tab. Saying just "conversation" still opens the Chat page as before.

## The model

Four concepts, read once and never guess again:

| | What it is |
|---|---|
| **Chatbot** | An AI employee: an Agent, its own brain, a permission level, and the channel accounts it serves (one bot can serve several). |
| **Channel** | Where customers write. Each channel has **accounts**: a Telegram bot token, a Zalo Bot token, a personal Zalo account you scanned a QR for. Later Zalo OA, Facebook, Web Chat. |
| **Conversation** | One exchange with one customer (or one group) on one channel. |
| **Inbox** | Where AI and humans run conversations together: read, take over, hand back. |

Underneath, every channel normalizes its messages into **one common event** and writes into one store: channel account, customer, conversation, message. The inbox never needs to know whether a message came from Telegram or Zalo.

## The Inbox tab

The top shows four numbers: total conversations, conversations active today, unread, and chats currently handled by a human.

The left column lists conversations, newest first. Each row: the customer (or group) name, the channel logo, the last message, the time, and the unread count. There is a search box for names or text, channel chips (shown only once two channels exist) and a bot selector (shown only once two bots exist).

Click a conversation and its history opens on the right: customer messages on the left, bot replies and messages you sent from your phone on the right. A failed bot turn sits there too, with its technical reason, so you can tell "the bot answered wrong" from "the bot is broken".

On a phone the page is one column: tap a conversation to open its history, with a back button. The page refreshes itself every few seconds.

## Reply, take over and hand back

At the bottom of a conversation is a compose box: type and press **Enter** to send (Shift+Enter for a new line). The message goes out through the chat's own channel: a Telegram or Zalo bot sends with that account's token, personal Zalo sends through the very account you scanned, **under your own name** (the compose box says so). A channel that cannot send from Javis yet shows a line saying so instead of the box.

Sending from here in a chat that has a bot **takes the chat over**: the bot stays quiet with this customer until you press **Hand back to AI**. Otherwise the customer would read two voices at once. The **Take over** button at the top of the conversation does the same without sending anything; after pressing it you can also reply in the channel's own app.

Two things to know:

- A bot turn already in progress when you press Take over still sends its reply. Cutting off a message mid-send is more confusing for the customer.
- Takeover is **per chat**, not a bot switch. Other customers keep getting bot replies.

## The Channels tab

Every account customers write to appears as **the same kind of card**, whatever the channel: channel logo and name, account name, state (running, off, error with the reason), the bot on duty, conversation and unread counts, and the channel's capabilities (groups, files, reply from Javis). No channel gets its own section, Zalo included. A channel added later simply shows up as one more card.

Two kinds of account, differing in how you get them, not in how they look:

**Bot accounts** (Telegram, Zalo Bot) are a token. Press **Add account**, pick the channel type, paste the token, press **Check** so Javis asks the right platform which bot it is, give it a display name and Save. A bot account records into the inbox while the bot serving it is enabled; with no bot on duty the card says so and offers **Create a bot**, which opens the form on the Chatbots tab with that account ticked. It can be deleted once no bot serves it; recorded conversations stay.

**Your own accounts** (personal Zalo) come from the **Connections** page (QR scan in Zalo Agent MCP) and appear here with a **Record conversations** switch. Turn it on and Javis reads new messages every 20 seconds through the MCP and writes them into the inbox. Three plain facts about this channel:

- **Off by default.** Turning it on keeps your Zalo session alive continuously through an unofficial API, meaning the account is signed in 24/7 on the machine running Javis. That is your choice, not Javis's. Use a secondary account.
- **Stored from the moment you turn it on.** No old history is pulled. Messages you send from your phone show as "You".
- **No bot on duty.** Replying from the Inbox sends under your own name; a bot answering over this channel deserves its own decision.

## Where data lives and what is kept

The store sits in the Javis state folder (`customer_conversations.sqlite3`), separate from the chat session store. **Text** is kept long term; images, files and voice keep only the message type and a description, the original files follow Javis's normal cleanup. A message read twice (after a restart, say) never creates a second row.

Deleting a bot does **not** delete its conversations, nor the channel accounts it served: customer history is your asset, a token is reusable. Bots created before 0.61.0 (token stored inside the bot) move to the account model automatically on update; token, conversations and allowed groups are all kept.

## For anyone adding a channel

Since 0.61.0 everything the core knows about a channel lives in the **channel registry** (`server/channels/`, one file per channel). A channel file declares: id, name, logo key, kind (`bot` uses a token, `account` uses an existing signed-in session, `webhook` for platforms that call back), capabilities (groups, text, files), how to get a token; and a set of functions: token check and the long-poll transport (bot kind), listing accounts and toggling recording (account kind), `gui` to reply from Javis. Incoming messages are normalized into the common event (`channel`, `account_id`, `external_chat_id`, `sender_type`, `text`, `external_message_id`, `created_at`) and written to the store.

Adding a channel = one file in the registry, one registration line, one logo in `icons.js`. The bot store, the supervisor, the API and all three tabs pick it up; nothing else changes. Details in `docs/dev/2026-09-kenh-hoi-thoai-spec.md`. API:

- `GET /channels` channel types and capabilities; `GET /channels/accounts` every account, one shape.
- `POST /channels/verify-token`, `POST /channels/accounts`, `POST /channels/accounts/{id}/update`, `.../watch` (account kind), `.../delete`.
- `GET /conversations` list with stats, filtered by `channel`, `bot_id`, `account_id`, `q`.
- `GET /conversations/{id}/messages` message history; `POST /conversations/{id}/reply` reply through the channel.
- `POST /conversations/{id}/read`, `POST /conversations/{id}/mode` (`ai` or `human`).
- `GET /conversations/channels` and `POST /conversations/zalo/{conn_id}/watch` are old aliases, still served.

## Troubleshooting

- **Bot enabled but no conversations**: the store only records from the moment the channel was connected; send the bot a test message. Still empty, check the bot's Log tab on the Chatbots tab.
- **Bot card says "no channel account yet"**: the bot serves no token. Press Edit, tick an existing account or paste a new token.
- **Sending from the Inbox fails**: the error text comes from the platform itself (token revoked, customer blocked the bot, Zalo session expired). A message that did not go out is not written to the store.
- **Personal Zalo shows a red error on the Channels tab**: usually an expired QR session or a machine without Node.js 20. Check the Zalo connection on the Connections page and rescan the QR if needed. The reader retries after 90 seconds.
- **Pressed Take over but the bot still answered once**: that turn was already running before the click. From the next message on, the bot stays quiet.

## Want more: the Customer management (CRM) pack

The Store has a **Customer management (CRM)** pack (`javis.khach-hang-crm`, needs 0.60.1 or newer) that sits on this very inbox. Once installed, just ask Javis: "who has waited over 2 hours without a reply", "what did Lan ask", "tag Lan as VIP", "how many new customers this week", "export customers who asked for a price to Excel". It ships a customer-care agent and a daily review workflow. The pack only reads the inbox and writes tags and notes on customers; it never messages anyone.

## See also

- [Chatbot (a dedicated bot)](25-chatbots.md)
- [The Zalo Bot channel](26-zalo-bot-channel.md)
- [Zalo Agent MCP](12-zalo-agent-mcp.md)
