# Telegram channel

*[Tiếng Việt](../11-telegram.md) · **English***

Enable the Telegram bot to ask Javis from your phone without opening the dashboard. You message the bot like a person, and Javis answers using the same brain and memory running on your machine or VPS.

## What this feature is

- You create your own Telegram bot (free), paste its token into Javis, and limit it to your account.
- Once enabled, every ordinary message you send the bot gets a Javis answer. The bot shows Telegram's "typing" indicator and also sends a status message whose text updates with progress.
- There are quick commands (starting with `/`) to check status, change model, stop a running answer, start a new conversation and save notes into the brain.
- Over Telegram, Javis still has the full MCP and skill set: asking for sales numbers, ads data, reading and writing vault files all work. This is true for EVERY engine (Claude Code, ChatGPT/Codex, OpenRouter, Claude API, OpenAI API), because Javis's tools go through the MCP Hub rather than being tied to one engine.
- Files go both ways: you send images and documents for Javis to read, and files Javis creates during a turn are sent back to you.
- **Voice commands**: hold the microphone, say a sentence, and Javis transcribes it and acts as if you typed. This needs a Groq API key pasted on the Models page once.
- Answers run in the background: while one is running you can still send `/stop` to cut it short.

For engines and models see [Models & engines](10-models-and-engines.md); for MCP tools see [Connections & business data](09-connections-and-business-data.md).

## Where to find it in Javis

1. Open the Javis dashboard (`http://localhost:7777` by default).
2. In the left navigation rail, open the **Connections** group and click **Channels**.
3. You will see the **Telegram** card with fields for enabling the bot, the Bot token, the allowed Chat IDs, and 2 buttons: **Save & enable** / **Send test**.

## Preparation: getting a Bot token and a Chat ID

These 2 pieces of information are required. Do this in the Telegram app (phone or desktop).

### Getting the Bot token (from BotFather)

1. In Telegram, find the account **@BotFather** (with a blue tick) and open the chat.
2. Type `/newbot` and follow the prompts: give the bot a display name, then a username ending in `bot` (for example `my_javis_bot`).
3. BotFather returns a token like `123456789:ABCdef...`. That is the **Bot token**. Keep it secret; anyone with it controls the bot.

### Getting your Chat ID (and other users')

The Chat ID identifies a Telegram account. Javis uses it as an allow list: only IDs on the list can message the bot.

1. In Telegram, find the bot **@userinfobot**, open the chat and press Start.
2. It replies with `Id: 123456789`. That number is your **Chat ID**.
3. Note it down for the next step.

To let other people (a partner, staff...) share the bot: have each of them do those 2 steps to get their Chat ID, and remember each person must open your bot and press **Start** once (Telegram only lets a bot message people who started it).

## How to use it (step by step)

### Step 1: Configure and enable the bot

1. Open **Channels** (the **Connections** group) on the dashboard and find the **Telegram** card.
2. Tick **Enable Telegram bot**.
3. Paste the token into **Bot token**. (If a token was set before, the label reads "(set)"; leave the field empty to keep it.)
4. Paste the Chat ID into **Allowed Chat IDs**. For several people, separate IDs with commas, for example `123456789, 987654321`.
5. Click **Save & enable**.

Javis saves the configuration and restarts the bot right after you click Save (no separate restart button). The status line under the card reads "✅ Saved, starting the bot…" and updates itself after about 2 seconds.

### Step 2: Check that the bot is receiving

The small line under the 2 buttons is the bot's real state. What each line means:

| Status line | Meaning |
|---|---|
| 🟢 Bot is receiving | The bot is healthy; message it and Javis answers. This line also shows how many chat IDs are allowed, or warns that "ANYONE can message it (no ID restriction)" |
| ⚪ Bot NOT enabled | "Enable Telegram bot" was not ticked and saved |
| ⚪ No bot token | Enabled but no token pasted |
| ⏳ Starting the bot | The bot was just enabled, wait a few seconds |
| 🔴 409 | The same token is being polled elsewhere, or a webhook is still set. See Common problems below |
| ⚠ Bot error | Another error, with details on the line |
| ⚪ Bot stopped | The bot has stopped (not re-enabled) |

An important note: a successful test does NOT mean the bot is receiving. The test only proves the token and Chat ID are right. To know it is receiving, the status line must read 🟢 **Bot is receiving**.

### Step 3: Send a test message (optional)

1. Click **Send test**.
2. With a valid token and Chat ID, Javis sends a message to your Telegram chat: "✅ Javis Telegram connected. Send any question." The status line reads "✅ Test message sent." (with several IDs it reads "✅ Test sent to 2/3 IDs." plus the failing ID's error).
3. If the token and Chat ID are not saved yet, the test button reports the missing configuration. Click Save & enable first, then try again.

### Step 4: Ask Javis over Telegram

1. Open the chat with your bot in Telegram.
2. Type any question as you would in a normal chat, for example "What tasks do I have today?" or "Summarise my vault for me".
3. The bot shows "typing" plus a temporary status message, then sends the answer. Long answers are split across several messages.
4. If you send another question while it is answering, the bot replies "⏳ Still handling the previous question. Send /stop to cancel and ask again." Only 1 turn runs per person at a time.

## The status message updates itself and stays as a trail

As soon as it receives a question, the bot sends you a real message: **🤔 Javis is working…**. That message is NOT resent; it is **edited in place** as progress happens, always starting with ⏳:

| Text you see | What Javis is doing |
|---|---|
| 🤔 Javis is working… | Just received the question, starting the turn |
| ⏳ ⚙ Calling: `<tool name>` | The Claude engine is calling a tool (Read, Write, an MCP tool...) |
| ⏳ ⚙ Calling tool: `<tool name>` | An API engine (OpenRouter, OpenAI API, Claude API) is calling a tool through the MCP Hub |
| ⏳ ✓ Results in, analysing… | The tool returned data and the engine is reading it |
| ⏳ ✍ Writing the answer… | Text generation has begun |

A few points to know:

- The status message updates at most **once every 2.5 seconds**, so do not expect it to flicker. That limit keeps Telegram from throttling the bot for sending too often.
- The message is **sent silently and does not buzz your phone**. It is only for looking at while you wait. A whole turn has exactly one notification: when the real answer arrives, and the notification shows the answer itself.
- When done, the bot **no longer deletes the status message**. Its final edit becomes a tidy trail line, with the answer as a new message below it. That has been the behaviour since **0.26.4**; before that it was deleted, which made many people think the bot had failed.
- The trail line records which tools that turn called and how long it took, for example `⚙ pos_statistics · Read · 8s`. A turn needing no tools reads `✓ Answered directly · 3s`. That is how you tell a figure genuinely pulled from the POS from a plain answer, and it stays in the history for later checking.
- Typing `/stop` mid-run: the status message becomes **⏹ Stopped.** and no answer follows for that turn.
- The "⚙ Calling..." line is your evidence that Javis is touching real MCPs (POS, ads, calendar, files...) rather than answering from thin air.
- These status messages exist only on **your own Javis bot**. A [dedicated chatbot](25-chatbots.md) talking to customers hides all of it and leaves only a "typing…" indicator, to feel like a person.

## Sending files to the bot, receiving files from it

The bot handles files both ways. This is the fastest route to get a photo or a document into the brain while out and about.

### You send an image or file to the bot

1. Send the image or document straight into the chat, with a caption if you want to be specific.
2. The gateway downloads it into `inbox/telegram/` **of the brain selected for your Telegram session** (changed with `/brain`), then puts that path into the message for the engine to read.
3. Javis reads the file in place and answers as usual. Duplicate names are not overwritten: Javis appends `_1`, `_2`.

Limits to remember:

- **The download ceiling is 20MB** (a Telegram bot API limit, not a Javis one). For larger files the bot says it could not download it and suggests another way to send it.
- **Voice messages ARE understood**, see the section below.
- **Video and video notes: Javis cannot watch them.** The bot politely asks you to type, send a voice message, or resend it as a document.
- A caption can also be a command. Snapping a photo of an invoice with the caption `/notes steel tube invoice today` runs the `/notes` command with that exact photo, rather than treating the whole thing as plain text.
- `inbox/` is a **cache area**, not a knowledge store: files older than **30 days**, or once the cache passes **300MB**, are cleaned automatically. To keep something long term, ask Javis to distil it into a `.md` note or move it into another folder in the brain. See [File manager](05-file-manager.md).

### Voice commands (voice messages)

Hold the microphone button in Telegram, speak, and release. Javis transcribes it and acts exactly as if you had typed it, which is ideal while driving or with your hands full.

**You need one thing: a Groq API key.** Groq is where Javis borrows speech-to-text (the Whisper model). Without it, sending a voice message makes Javis reply that a key is needed, with instructions, rather than staying silent.

To wire it, once:

1. Go to [console.groq.com](https://console.groq.com), sign in and create an API key.
2. Open the Javis dashboard, go to the **Models** page, find the **Groq (API)** provider, paste the key and save.
3. Done. The next voice message is understood immediately, with **no bot restart**.

A few things to know:

- **This key is shared with chat.** If Groq is already wired as a brain, voice messages work with nothing extra. Conversely, wiring the key only for speech is fine too; you do not have to make Groq your main model.
- **Javis understands Vietnamese** (the language hint given to Whisper stops short sentences being guessed as another language and translated).
- **Actions with outside effects are confirmed first.** Sending messages, publishing, booking, spending money, editing files: Javis opens with a line reading "I heard: ..." and waits for you to confirm. Machines can mishear, and those actions cannot be taken back. Asking for numbers, lookups and summaries happens straight away without confirmation.
- **Recordings are not stored in the brain.** Javis transcribes and keeps no `.ogg` file in `inbox/`.
- A voice message with the caption `/notes` still runs that command, with your spoken sentence as the content.
- If nothing could be transcribed (silence, too noisy) or Groq errors, the bot states the reason and asks you to type. There is no silent path.

The Zalo channel understands voice messages too, using the **same Groq key**, so wiring it once serves both. See [Zalo Bot channel](26-zalo-bot-channel.md).

### The bot sends files back to you

Files Javis creates during a turn are **attached right after the answer** without you asking. Three sources qualify:

- Files Javis wrote with the Write tool during that turn.
- Files whose absolute path is mentioned in the final answer.
- Vault images and files embedded as relative markdown, for example `![](attachments/photo.png)`, which is exactly how a freshly generated image comes back.

Limits and behaviour:

- At most **10 files per turn**, each under **50MB** (Telegram's document ceiling).
- Only files **created or edited during that turn** are sent. Mentioning an old file's name does not make the bot resend it, which avoids spam.
- Images (`.jpg .jpeg .png .webp .gif`) under **10MB** are sent as photos (previewable in chat); everything else goes as a document. An image Telegram rejects falls back to being sent as a document.
- If an image was sent separately, the matching `![...](...)` markdown line is stripped from the answer so you do not see a bare text fragment next to the real photo.
- On a failure the bot says so plainly: "⚠ Could not send file `<name>`: `<reason>`".
- Text goes first and files after, for a natural reading order.

## When Javis asks back with a numbered list

On the dashboard, when Javis must ask about an important parameter (which period, which shop...), it draws buttons. Telegram is a plain-text channel with no such buttons, so Javis degrades the option block into a **question plus a numbered list** (at most 4 options):

```
Which period do you want revenue for?
1. This week
2. This month
3. Compare with last month
```

Answer by sending just the number, for example `2`, or by typing what you want in words. Javis reads the number in the context of the question it just asked, so no special syntax is needed.

## Quick commands in Telegram

Typing `/` in the chat (or pressing the bot's Menu button) shows the command list. Available commands:

| Command | Effect |
|---|---|
| `/help` | See the guide and command list |
| `/status` | See the provider, model and brain in use, and whether the bot is busy answering |
| `/skills` | List the skills in the vault (type `/skill-name` to call one) |
| `/notes` | Save the message (with images) into the brain's Sources. Type `/notes <content>`, or send an image with the caption `/notes ...` |
| `/agents` | List agents and say whether any run is in progress |
| `/workflows` | List workflows |
| `/model` | View or change the model. Type `/model` with nothing to open a button picker; or type a name directly (for example `/model sonnet`) |
| `/brain` | View or change the brain (vault) for YOUR session only. Type `/brain` for a button picker; or type a name directly (for example `/brain Kim Khi`). After switching, the conversation resets to load the new brain's memory; other people and the dashboard are unaffected. Files you upload land in the selected brain's inbox |
| `/retry` | Resend the most recent question |
| `/stop` | Stop the running answer immediately |
| `/reset` | Start a new conversation (forgetting the old context) |
| `/cli` | Switch to the Claude engine (Claude Code) |
| `/or` | Switch to the OpenRouter engine (chat + multi-model MCP) |

`/notes` has no special branch inside the bot: it runs through the normal skill path, so it also needs an engine other than OpenRouter (see below). Details of that skill are in [Skills](06-skills.md).

Details on typing `/model`:

- The button picker from `/model`: pick a CONNECTED provider (the one in use has a ✓ and a model count), then a 2-column model grid, 8 models per page, with ◀ ▶ to page. The model list comes DIRECTLY from the provider (OpenRouter shows all several hundred, Antigravity shows exactly the Antigravity IDE lineup) rather than a hardcoded list.
- Typing a name works too: a name with a `/` (for example `openai/gpt-4o`) is an OpenRouter model; `gpt-...` or `...-codex` is a ChatGPT model (requiring OAuth); anything else (`opus`, `sonnet`, `fable`) is a Claude model.
- Since 0.33.7 the picker shows **all 10 providers** like the dashboard Models page, **Antigravity CLI** included; before that it was a hand-written 5-row list, so later providers could not be switched to from a phone. Providers listing no models (commonly: the CLI is installed but not signed in) are hidden for tidiness, except the one in use.
- Typing `/model <model name>` makes Javis look that name up in the real lists of connected providers and switch to the right one. If the name exists at several providers and none is currently in use, it asks rather than guessing, because guessing wrong silently changes which account pays (a subscription versus per-call API billing).

## MCP and skills over Telegram

- **Every engine can use Javis's MCP over Telegram**, because tools go through the MCP Hub rather than being bound to one engine. The bot's own `/help` text says so: ChatGPT/Codex and OpenRouter can both use Javis's MCP. You see it really happening when the status message shows "⚙ Calling tool: ...".
- Call a skill with `/skill-name`. This path does block one case: on the OpenRouter engine, typing `/skill-name` makes the bot say "⚠ Skills need the Claude CLI engine. Send /cli to switch, then /skill-name again."
- Switch engine inside Telegram: `/cli` returns to Claude (the bot replies "✅ Provider: Anthropic (Claude Code), full MCP, POS/Ads/vault questions work."), `/or` moves to OpenRouter (the bot replies "✅ Provider: OpenRouter (`<model>`), chat + multi-model MCP."). Switching here switches the whole Javis system (dashboard and bot share one model configuration).
- To use `/or` you need an OpenRouter key set on the [Models & engines](10-models-and-engines.md) page; without one the bot says "⚠ No OpenRouter key, set it in Models on the dashboard first."

## Access control: only you can use the bot

- The **Allowed Chat IDs** field is the allow list. Only Telegram accounts whose ID is listed can message the bot. A stranger gets: "You are not allowed to use this Javis bot."
- If you leave the Chat ID field empty, anyone who finds the bot can use it. Do not leave it empty, because the bot can touch your vault and your numbers. Always set at least 1 Chat ID.
- To share one bot with more people: add their Chat IDs, comma separated, and click **Save & enable**. The **Send test** button messages ALL IDs and reports which failed (usually someone who has not pressed Start).
- Each person has their **own conversation thread**: each Chat ID's context is separate and does not bleed across, and two people can message at once without waiting for each other. `/reset` and `/stop` only affect the sender's own session. Even so, everyone shares **one vault and the same permissions** (anyone can read and write your data, numbers and brain), so only add IDs you trust. For complete separation of data too, run a separate Javis and bot per person.

## Who receives background notifications

When several people share a bot, you need to know whose phone each notification reaches. Not everything goes to everyone.

| Notification kind | Who receives it |
|---|---|
| The result of each loop iteration on [Recurring jobs](08-recurring-jobs.md) | EXACTLY the person who requested the loop, if that ID is on the allow list. When the requester is unknown (for example a loop created on the web), the **first ID** on the list |
| A finished Kanban job, see [Work / Kanban](21-kanban-work.md) | As above: the requester, or the first ID when unknown |
| A reminder coming due | The chat_id that scheduled it. If the reminder has no chat_id, or that chat_id is no longer on the allow list, it goes to ALL IDs |
| A loop auto-pausing | ALL IDs on the allow list |
| The engine-down light (the brain stopped responding) | ALL IDs on the allow list, once per outage |
| A Zalo message matching a rule, see [Zalo channel](12-zalo-agent-mcp.md) | The owner set in the listener configuration; unset, the first ID |

In short: **work results go to whoever asked for the work**, and **system warnings go to the whole household**.

## Telegram conversations share the dashboard history

Every Telegram exchange is saved exactly as if you chatted on the dashboard: into the conversation history, into the brain's memory log, and into the self-learning loop. In the 🕘 History sidebar, conversations from the bot carry a **TG** label so you do not confuse them with ones you opened on the web. See [Sessions](04-sessions.md).

Conversations are attached to the **brain selected for your Telegram session** (changed with `/brain`), so they only appear while the dashboard is viewing that brain.

### Why Telegram conversations get cut into pieces

On the dashboard you click "＋ New conversation" yourself, so a conversation never grows forever. On Telegram almost nobody types `/reset`, so left alone one Chat ID would be stuck in one endless conversation that is heavy to open. Javis moves to a **new conversation** when:

- you go more than **12 hours** without messaging, or
- the current one is long enough (about **100 exchanges**), or
- you type `/reset`, switch brains with `/brain`, or the server restarts.

The important part: this splitting only affects **the archive you reread**, and does **not touch Javis's memory during the conversation**. You keep messaging normally and Javis keeps the thread; the dashboard simply shows the history in readable pieces rather than one huge block.

Telegram pieces older than **30 days** are archived so the list does not flood. Archived, not deleted: the content is still findable through search.

## Checking the bot's state

Two ways:

1. On the dashboard: open **Channels** (the **Connections** group) and read the status line under the Telegram card (described in Step 2). This is the fastest and clearest way.
2. In Telegram: type `/status`. The bot reports the provider, model, brain in use, your session, and whether it is busy or idle.

The **System** group at the top of the **Settings** page also shows Telegram as "On" or "Off" at a glance, with a button jumping to the **Channels** page; the detailed configuration stays in **Channels**.

## Quick reference: buttons and states

| Button / field | Where | Effect |
|---|---|---|
| Enable Telegram bot | Telegram card, Channels page | Turn the bot on or off. It only takes effect after Save & enable |
| Bot token | Telegram card | The token from BotFather. Once set, leave it empty unless changing it |
| Allowed Chat IDs | Telegram card | The allow list. Several IDs separated by commas |
| Save & enable | Telegram card | Save the configuration and restart the bot immediately |
| Send test | Telegram card | Fire a test message to every ID on the allow list. It does NOT prove the bot is receiving |

## Tips

- After changing the token or Chat IDs, always click **Save & enable** again; Javis restarts the bot with the new configuration and nothing else is needed.
- Very long answers are split into consecutive messages by Telegram, which read normally.
- To ask about a completely new topic without old context, type `/reset` first.
- If the bot rambles or you asked the wrong thing, type `/stop` to cut it, then `/retry` if you want the same question again.
- Snapping a photo of an invoice, business card or price list with the caption `/notes ...` is the fastest way to push something into the brain while standing in a shop.
- Before sending an image or file, check that `/brain` points at the brain you want: the file lands in that brain's inbox, not the default one.
- Telegram cannot render markdown tables, so Javis is instructed to answer this channel in short message style, using bold, italics and `code` instead of tables.
- On a VPS, protect the dashboard with a password on the [Security & accounts](14-security-and-accounts.md) page alongside setting Telegram Chat IDs.

## Common problems

**The status line reads 🔴 409.** The same bot token is being polled elsewhere (another Javis instance, another machine, or a leftover webhook). One token may only run in 1 place. The Javis bot clears webhooks on startup; if 409 persists, stop the other Javis or create a new bot token with BotFather. Afterwards, click **Save & enable** again.

**Send test reports a missing token or Chat ID.** You have not saved both. Fill in the token and Chat ID, click **Save & enable**, then test.

**The test succeeds but messaging the bot gets no reply.** Testing and receiving are different things. Check whether the status line reads 🟢 **Bot is receiving**. If it is ⚪ or 🔴, act on that line (re-enable it, or fix the 409).

**Messaging the bot returns "You are not allowed to use this Javis bot."** The Chat ID set in Javis does not match the account messaging it. Get the right Chat ID from @userinfobot, paste it into the Chat ID field and Save & enable.

**The "🤔 Javis is working…" message never changes.** That turn has not called a tool yet so there is nothing to report, or the engine is waiting. When done it becomes a trail line (`⚙ ...` or `✓ Answered directly`). If it sticks on "🤔" with no answer following, that turn failed; check the status line on the **Channels** page.

**Typing `/skill-name` reports that the Claude CLI engine is needed.** You are on the OpenRouter engine. Type `/cli` to return to Claude, then call the skill again.

**You sent a file and Javis says it cannot read it.** Check 2 things: whether the file is over 20MB (the Telegram bot API download ceiling), and whether it is a video or video note (Javis cannot watch those; send it as a document or type instead).

**Sending a voice message reports that a Groq API key is needed.** Correct: speech recognition runs on Groq's Whisper. Go to the **Models** page, the **Groq (API)** card, paste a key from console.groq.com and save. No bot restart needed.

**Javis mishears you.** Record closer to the microphone, speak slowly, and avoid noise. Very short utterances (one or two words) are also easy to mishear; a full sentence is far more accurate. For actions with outside effects Javis reads back what it heard before acting, so you get a chance to catch it.

**Javis says it created a file but you did not receive it.** Only files created or edited in that same turn, under 50MB, at most 10 per turn, are auto-attached. For an older file, ask Javis to resend it by name.

**An old image in the conversation shows a grey "Image expired" box.** The media cache (`attachments/` and `inbox/`) cleaned files older than 30 days or over the 300MB ceiling. Content already distilled into `.md` notes is untouched.

**You changed the configuration and the bot behaves as before.** Wait a few seconds and reload the **Channels** page so the status line updates. If it still is not 🟢, see [Troubleshooting & FAQ](17-troubleshooting.md).

## Token saving applies to Telegram too

Since **0.24.0**, the level you pick on the Settings page (**Optimised** / **Ultra saving**) applies to the Telegram channel as well, not only dashboard chat.

Before that, both levels were wired only into the dashboard, so enabling them still sent the whole of `CLAUDE.md` + `MEMORY.md` on every Telegram turn. No error appeared; the token bill simply did not drop on the channel most people use most.

What the two levels do:

- **Optimised**: replaces `CLAUDE.md` + `MEMORY.md` with the memories and skills selected for the question you just asked.
- **Ultra saving**: for questions needing no lookup (ordinary Q&A, short calculations), calls the model **exactly once** with a small capsule and no tool table loaded.

Questions needing lookups, data sources or attached files take the full path as before; the shortcut only accepts turns it is certain it can answer. A shortcut that misses (a subscription token expiring, say) also falls back to the full path, so you still get an answer.

Schedule commands ("cancel the reminder...") are always handled by the schedule gateway; the shortcut never steals those turns.

## Related

- [Models & engines](10-models-and-engines.md) - choosing the provider and model for both dashboard and bot.
- [Connections & business data](09-connections-and-business-data.md) - wiring data sources so you can ask for real numbers over Telegram.
- [Recurring jobs & reminders](08-recurring-jobs.md) and [Work / Kanban](21-kanban-work.md) - where the background reports sent to the bot come from.
- [Zalo channel](12-zalo-agent-mcp.md) - the other channel, which reads and reports Zalo messages into this same Telegram bot.
- [File manager](05-file-manager.md) - seeing where uploaded files land in the brain.
- [.env configuration](16-env-configuration.md) - advanced configuration through the environment file.
