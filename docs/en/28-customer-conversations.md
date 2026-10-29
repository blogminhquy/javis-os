# Customer conversations (Inbox)

*[Tiếng Việt](../28-hoi-thoai-khach.md) · **English***

Every message a customer sends to a **dedicated bot** (Telegram or Zalo Bot) and to a connected **personal Zalo account** is gathered into one inbox inside Javis. You read the exchange between the customer and the bot, see which chats the bot is stuck on, and **take over** a chat when a human is needed.

Since 0.61.0 this page also holds the Chatbots: **one item on the rail, three tabs** (Inbox, Channels, Chatbots), and you **reply to customers right inside the Inbox**.

## Where to open it

Left navigation, group **Capabilities**, item **Conversations**. Inside, three tabs:

- **Conversations**: every customer message, who is handling which chat, reply, let the AI draft.
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

## The Conversations tab

Since 0.372.0 (Chatbot v5) a computer shows **three columns**: the customers on the left, the chat in the middle and the **Info** panel on the right. Since 0.397.0 Info **starts closed** so the chat gets the room; the ⓘ button at the right of the chat head opens it (Javis remembers your choice in that browser), and below 1200px wide it slides over the chat. The type on a computer is also smaller: 14px lists, 15px messages, with the messages in a centred column.

**On a phone** (since 0.397.0): no "Chatbot" title at the top, and the four tabs show their icon only (a long press or a screen reader still gives the name). An open chat **fills the screen**: one head row with the back button, the customer's name, the channel and a violet **mode button** (for example "AI replies ▾"). It opens a sheet from the bottom with the three modes, a line on what each does, and **Customer info and AI settings**. The compose box is one row with two round buttons: ✨ for an AI draft, the arrow to send.

**Who is handling this chat.** The server works out one state per chat and every part of the page reads it:

| Colour | Name | When |
|---|---|---|
| yellow | **Needs you** | a customer waits with nobody on it, someone called the AI in a group you have not allowed yet, the AI wrote a draft waiting for you |
| violet | **AI is handling** | the AI may answer here and the bot is running |
| blue | **You are handling** | you chose I reply and the customer is not waiting |
| grey | **Logged only** | the AI does not answer here (not allowed, no bot, bot off) and nobody waits |

Each row has a **left edge** in that colour, an avatar with the **channel's logo** in its corner, the name, the time, the last message (with "AI:" or "You:" in front), the **chat's message count** (grey, for example "11 msgs") then the unread count (red), and a third line only when the chat has tags: up to two plus "+n". Hovering a row gives the nick or Page name (when several are in view) and one sentence on what is going on.

At the top of the left column:

- **Search** (name, phone number, text), with the **Filter** button as an icon inside the box: a two-level menu with Time (when the last message came: today, last 7, 30 or 90 days, last month, week or month to date, or days picked on the calendar), Has tag, Without tag, Chat type, Answering bot, Status (unread, waiting longest, hidden), Last message by (customer, AI, you) and Customer info (left a phone or email, pinned chats only). Active filters show as chips with an x underneath.
- Under it, **two dropdowns** (since 0.397.0, instead of four quick filters that wrapped onto two lines):
  - On the left, **who handles it**: the button always shows the current view with its count, for example "Needs you 4". It opens four choices, each with a line on what it means: **Needs you** (customers waiting for your reply or approval), **AI handles** (the AI is answering the customer), **You handle** (you took over, the AI stays quiet), **All** (every chat, logged-only ones too). The page first opens on **Needs you**; when nothing needs you it says so, with **Show all**.
  - On the right, the **channel picker**: opens the list of nicks and Pages with checkboxes, grouped by channel with real logos. Ticking a channel ticks all of it; each one shows its **Needs you** count. Nothing ticked means everything. It has a search box, **Clear**, **Done** and **Manage channels**. Hovering the button names the places picked.

Every choice is remembered in the browser. The number on the **Conversations** tab is the **Needs you** count.

**"A customer waits"** (one reason for Needs you): the customer wrote last, nobody answered, **you have not opened the chat since** (opening it takes it off Needs you until the customer writes again), and the message is more than a friend-request notice ("accepted your friend request").

**Groups keep only the latest 1,000 messages** (since 0.396.0; 100 from 0.65.12 until then). The inbox stores every message of private chats with customers, but each **group** keeps just its 1,000 newest; older ones are deleted as new ones arrive. This keeps the store from growing forever and stops Javis from holding strangers' words longer than needed (a personal Zalo account in many groups records even groups the bot is not allowed to answer in). The first time after updating to 0.65.12, existing groups with more than 100 messages were cut down to 100 (those messages do not come back with the raise to 1,000); Javis **backs up the whole store file once** before cutting (a `customer_conversations.sqlite3.bak-truoc-cat-nhom-...` file next to the store) and **deletes that backup after 14 days**. To get the cut messages back, copy the backup over the store file within those 14 days. A conversation's "messages ever received" counter does not go down.

**Loads gradually, no lag** (since 0.65.11). The list loads the first 40 rows; scrolling near the bottom loads 40 more (or press **Show more**). The message pane works the same way: opening a conversation loads only the **latest** 40 messages, scrolling up near the top (or pressing **Show older messages**) loads 40 older ones and keeps your place. Every 5 seconds Javis only asks for messages **newer than the last one** and appends them; if you are reading older messages when a new one arrives the pane stays still.

Click a conversation and its history opens in the middle: customer messages on the left (white), AI replies (light violet) and yours (blue) on the right; who and when sit right under each bubble, and the customer is named only in groups. The chat head has the customer's name with the chat's tags and a **+ Tag** button (it opens Info with the tag picker); the line under it gives the channel, the nick and the **message count**. A failed bot turn sits there too, with its technical reason, so you can tell "the bot answered wrong" from "the bot is broken". The page refreshes itself every few seconds.

## Who replies: the chat head and the coloured bar

**The AI may answer here**: the three modes **AI replies**, **AI drafts**, **I reply** sit in the chat head, right of the customer's name (a mode button opening a sheet on a phone). Hovering them gives one sentence on what is going on.

Under the name, a **slim bar** in the colour of the chat's state carries **one sentence** (for example "The AI wrote a reply and waits for you to approve it"). Since 0.397.0 it **only shows when the chat needs you** or there is something to switch on; while the AI handles things quietly it stays hidden so the chat gets the room. The controls that fit:

- In I reply with a customer waiting: **Hand back to the AI**.
- **Not allowed yet**: **Let the AI answer here**. The bot keeps who it answers everywhere else.
- **Someone called the AI in a group not allowed yet**: **Allow** or **Dismiss**.
- **The channel has no bot**: **Create an AI for this channel** opens the bot form with that account ticked.

Every change shows a line at the bottom of the screen with **Undo**.

**AI drafts, I approve** (new in 0.371.0): the bot's turn runs as usual but its reply is **not sent**. It waits **inside the compose box**, above where you type, on a light violet background, and the chat moves to Needs you. Edit it if needed, then **Send** (logged in the inbox as the AI's words), **Rewrite** or **Discard**. A newer customer message replaces a draft not approved yet. Changing the mode keeps a waiting draft; replying by hand drops it.

**Switch the AI off in one chat only**: choose "The AI does not answer here" in the Info panel. Only that chat goes quiet.

## Replying, and the "AI draft" button

The compose box has two buttons:

- **Send**: sends your text as it is. On a computer **Enter** sends and Shift+Enter adds a line. On a phone (since 0.398.0) **Enter adds a line** like in the main chat; press the send button to send.
- **AI draft** (called "AI reply" before 0.397.0): what you typed is an **instruction for the AI**, for example "quote 20 cases wholesale, delivery Thursday". The AI writes a polite reply inside the compose box, naming your instruction, with Discard / Rewrite / Send. With an empty box it reads the chat and writes on its own. **It never sends by itself.** The instruction is read by the AI only and never lands in the inbox.

Under the last customer message, a **"Bot silent: reason"** line appears when the reply policy logged one (for example "Score below threshold (0.52 / 0.60)"), with **Why** opening that bot's reply policy panel, and **Ask the AI to answer this**: the AI answers that message now and sends it, the chat stays in AI replies. If the policy had stayed silent on it, the bot also **learns one more case**. If sending fails after the AI wrote the reply, the text lands in the compose box for you to send by hand.

The message goes out through the chat's own channel: a Telegram or Zalo bot sends with that account's token, personal Zalo sends through the very account you scanned, **under your own name** (the box's placeholder says so, for example "Send as Javis Vu..."). A channel that cannot send from Javis yet shows a line saying so instead of the box.

Sending by hand in a chat in **AI replies** **takes the chat over**: the AI stays quiet with this customer until you pick AI replies again. Otherwise the customer would read two voices at once. Choosing **I reply** does the same without sending anything; after that you can also reply in the channel's own app.

Two things to know:

- A bot turn already in progress when you take over still sends its reply. Cutting off a message mid-send is more confusing for the customer.
- Takeover is **per chat**, not a bot switch. Other customers keep getting bot replies.

## The Info panel

- **Customer**: name, nick or Page, the phone or email they left, **tags** (add, remove, create on the spot) and a **note** only you see (saved when you click out of the box; it belongs to the customer, so their other chats show it too).
- **AI in this chat**: who replies (off here, or one of the three modes); for groups **the AI speaks up when** (called by name, it sees a need, every message); **when you type yourself, the AI waits** how long. The last two are settings of the whole bot, and the panel says so. A link opens the bot's settings.
- **Channel**: the logo, the channel and the nick or Page.

## The Channels tab

Since 0.377.0 every nick and Page lives on the **Channels** tab. On the left: **Connect a new channel**, the **See every brain** switch, then each channel with its real logo and its nicks or Pages; each row says which AI is on duty (or "No AI yet", "No AI needed") and how many chats need you. A channel with two or more places offers **Put an AI on several Pages**: tick them, pick a bot, Save.

Pick a nick or Page and the right side shows:

- **AI on duty for this Page**: one bot dropdown. **Cancel** and **Save** appear only after a change; nothing changes before Save. **No AI needed** means the place is only logged and no longer counts as a job on the tab. Changing the bot moves the place's existing chats to the new bot. A bot left with nothing to serve is switched off, and Javis says so.
- **Info**: a button next to the bot dropdown. It opens the account card in a popup: state, record switch, import history, edit, delete (described below), and **Bot settings** when a bot is on duty. The button shows a red dot when the account has an error. Since 0.404.0 the card no longer sits above the chat list.
- **Groups and people**: one **AI here** switch per chat, a sentence on who is handling it, **Allow** when someone called the AI in a group not allowed yet, and **Open chat**. Every change can be undone. With no AI on duty yet the switch is dimmed and, when pressed, says to pick one in the box above.

The number on the Channels tab counts the places that need you: an account in error, or one with no bot that you did not mark "No AI needed".

## The Stats tab

Press the period button to open the date picker: a quick range (today, yesterday, last 7, 30 or 90 days, last month, week or month to date) or a start and end day on the calendar, then **Apply**. Javis remembers the period you looked at last. Since 0.399.0 the page opens with a **benefit band**: how many messages the AI answered for you (against the period before), its share of all answers, **the time it freed for you** (estimated at 1 minute per AI answer) and **how many answers it sent while you rest** (9 pm to 7 am in the brain's time zone). Four tiles: Customers served (with the new ones, private chats whose first message is in the period), First answer after (the AI against hand replies, the typical value), Hand replies, Waiting for you (opens the Needs you list). A **When customers write** chart has 24 columns, your rest hours in a stronger colour and the busiest hour named. Last, **AI and hand replies per account** (one two-colour bar per account with that account's own AI share) and AI answers by bot. Since 0.401.0 an **account picker** sits next to the period button: pick one account and the whole page counts only that account, so an account where a person types does not lower the share of one only the AI answers. "Hand replies" are messages a person typed, in Javis or on that account's own phone. Numbers come from the Javis inbox.

## The account card

Every account customers write to appears as **the same kind of card**, whatever the channel: channel logo and name, account name, state (running, off, error with the reason), the bot on duty, conversation and unread counts, and the channel's capabilities (groups, files, reply from Javis). No channel gets its own section, Zalo included. A channel added later simply shows up as one more card.

Two kinds of account, differing in how you get them, not in how they look:

**Bot accounts** (Telegram, Zalo Bot) are a token. Press **Add account**, pick the channel type, paste the token, press **Check** so Javis asks the right platform which bot it is, give it a display name and Save. A bot account records into the inbox while the bot serving it is enabled; with no bot on duty the card says so and offers **Create a bot**, which opens the form on the Bot tab with that account ticked. It can be deleted once no bot serves it; recorded conversations stay.

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
