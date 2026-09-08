# Chatbot (a dedicated bot)

*[Tiếng Việt](../25-chatbot.md) · **English***

Put an **Agent** you created in front of other people: they message a dedicated bot on **Telegram** or **Zalo**, that Agent answers by the rules you wrote for it, and hands anything beyond its reach to a real person.

It suits anything you answer over and over for other people: questions about a product or a service, explaining internal rules to colleagues, fielding students' questions, guiding members of a community, filtering questions before they reach you.

It differs from [the Telegram channel](11-telegram.md) in one decisive way: the Telegram bot on the **Channels** page is **your own Javis** (full power, reading the main brain, able to call every data source, and only you can message it). The bot on the **Chatbot** page is **an Agent on duty** (read-only by default, seeing only its own brain, and strangers can message it). Do not use one in place of the other.

A dedicated bot **can do real work** if you raise its permission level: writing files, calling data sources, even acting outside. But whoever drives it is the person messaging it, not you, so read [The three permission levels](#the-three-permission-levels-what-the-bot-may-do) carefully before raising it.

## What this feature is

- Each bot = one **Agent** in one brain + a **dedicated token** on Telegram or Zalo. The bot reads that brain's documents.
- **The channel is a choice**: Telegram or Zalo. For Vietnamese customers Zalo is almost always the right one, because they already have the app. See [Choosing Telegram or Zalo](#choosing-telegram-or-zalo).
- The Chatbot page **belongs to the open brain**: switching brains at the top of the page shows that brain's bots, just like the Agents and Skills pages.
- People message the bot directly, or you drop the bot into a group.
- **The bot follows your Agent file exactly.** Javis inserts no rules of its own.
- **Three permission levels**, chosen at creation and changeable later: Read only (the default), Can write, Full power. Raising the level requires ticking a consent box after reading the risks.
- Two rails **do not change with the level**, and they are locked in code rather than in wording: **the bot only sees its own brain**, and **it cannot run machine commands**.
- Questions beyond its knowledge are handed to the human on duty you nominate.
- The Chatbot page is built for **many bots** from the start: a card grid, a search field, add/edit/delete, and enable/disable in place. Running one bot or ten uses the same interface.

## Where to open it in Javis

The left navigation rail, the **Capabilities** group, the **Chatbot** item.

## Preparing before creating a bot

Three things, and doing them in this order saves going back to fix things.

### 1. Stand in the right brain

A bot belongs to **the brain you have open**. Its Agent and the documents it reads both come from that brain, so switch to the brain you intend to give it before creating the bot.

**The bot only knows what is in that brain.** This is the point worth weighing most: if the bot will answer strangers, do not create it in your main brain, which holds internal notes, private figures and unannounced plans, and the bot cannot tell what may be said aloud and what may not.

The clean approach: create a brain dedicated to answering outsiders (the **Second Brain** page), put in exactly the documents outsiders may see, then switch to that brain and create the bot.

The rule for choosing what goes in: **if one sentence from this file leaking out would bother you, that file does not belong in the bot's brain.**

### 2. An Agent in that same brain

Go to the **Agents** page and create an Agent for the job the bot will do. Write the role and the instructions as if briefing someone on their first day: how to speak, what to prioritise, and in which cases to hand over to a human.

If you are on the Chatbot page and the brain has no Agent yet, click **Create Agent** to jump to the Agents page, then come back.

The bot **reads the Agent at run time** rather than copying it. Editing the Agent later on the Agents page changes the bot immediately, with nothing to fix twice. How to write an Agent: [Agents and Workflows](07-agents-and-workflows.md).

### 3. A dedicated token, taken from the right place for the channel

If the bot runs on **Telegram**: go to **@BotFather**, type `/newbot`, set a name and username, and take the token string shaped `123456789:ABCdef...`.

If the bot runs on **Zalo**: open the Zalo app, find the Official Account **Zalo Bot Manager** and choose **Create bot**. The bot name must start with the word "Bot" (for example "Bot Kim Khí Hà Lộc"). The token arrives as a Zalo message, shaped `123456789:abc-xyz`, and it **does not expire** until you reset it yourself.

**Each bot needs its own token, and do not use your main Javis bot's token.** One token can only run one process; sharing kills both and the server returns a 409. Javis blocks this when you click Test, but knowing in advance is better.

Pasting one channel's token into the other makes Javis say so outright rather than leaving you guessing: the **Test** button asks the platform you actually selected.

## Choosing Telegram or Zalo

The first field in the create form is the channel, and it comes first because it decides everything below: where the token comes from, whether the bot can join groups, whether it can send files.

| | Telegram | Zalo |
|---|---|---|
| Vietnamese customers already have the app | Rarely | Almost always |
| Can join groups | Yes | **No** on the basic bot tier |
| The bot can send images to customers | Yes | Experimental |
| The bot can send documents (PDF, spreadsheets) | Yes | **Not yet** (Zalo has not opened the API) |
| Customers can send images for the bot to read | Yes | Yes |
| Customers can send documents for the bot to read | Yes | Not yet |
| Message size ceiling | 4096 characters | 2000 characters |
| The bot shows a `/` command menu | Yes | No, they must be typed |

In short: **a bot talking to Vietnamese customers should use Zalo**, accepting direct chat only and no document sending. **A bot for internal groups, or one that needs files going both ways, should use Telegram.**

**The channel cannot be changed after the bot is created.** Changing the channel means an entirely different bot: a different token, a different identity, different people, and every stored group id instantly meaningless. Needing another channel means creating another bot; the Edit form shows the channel locked with exactly that explanation.

On the card grid, each bot carries a **channel marker** in two places: a small badge overlapping the icon corner (to recognise at a glance), and a chip with the logo in the information section (to read while scanning). Once you have bots on both channels, a **All / Telegram / Zalo** filter row appears at the top of the page.

### How the Zalo Bot differs from Zalo Agent MCP

Javis has two ways into Zalo, and they do not replace each other:

- **The Zalo Bot** (this page) is a **separate identity** using the official API. No risk of the account being locked, but it only sees what people send directly to it.
- **[Zalo Agent MCP](12-zalo-agent-mcp.md)** signs into **your own Zalo account** through the unofficial API. It reads real conversations and can message anyone, at the cost of the account possibly being restricted or locked.

The first is for **other people talking to Javis**. The second is for **Javis acting on your behalf**. Using both is fine.

## How to use it (step by step)

### Step 1: Create the bot

Click **New bot** and fill in:

| Field | What to enter |
|---|---|
| Where this bot talks | **Telegram** or **Zalo**. The first field because it changes the rest of the form. See [Choosing Telegram or Zalo](#choosing-telegram-or-zalo) |
| Bot name | The name you use to tell your bots apart |
| The Agent as its brain | Pick an Agent in the open brain, or click **Create Agent** |
| What the bot answers from | See the two modes below |
| What the bot may do | The permission level. Leave it at **Read only** the first time; read [The three permission levels](#the-three-permission-levels-what-the-bot-may-do) before raising it |
| Token | Paste the token for the channel you chose then click **Test** |
| The on-duty Chat ID | The Telegram number of the person receiving handovers (see below) |
| Allowed groups | Only shown for Telegram bots. Leaving it empty is fine, drop the bot into a group then allow it with one click later (see Step 4) |
| When the bot speaks in a group | Only shown for Telegram bots. By default only when named or replied to |

Choosing Zalo makes the last two fields **disappear** rather than appear and do nothing: Zalo's basic bot tier does not let a bot join groups, so declaring group ids there would be an empty promise sitting in the data.

**There is no brain field**, and that is deliberate: the bot belongs to the brain you have open. For a bot in another brain, switch brains at the top of the page and create it there; one place to look, with no two layers to keep in sync.

Click **Test** before saving: Javis asks the platform you selected whether the token is real, returns the actual bot name, and reports at once if another bot in Javis already uses that token. For a Zalo bot, if your tier does not allow groups it says so right here.

**A newly created bot is always OFF.** That is deliberate: turning it on makes the bot talk to real people immediately, so turning it on has to be a conscious click rather than a side effect of creating it.

### Step 2: Test by messaging before going live

Turn the bot on with the **Enable** button on the card, then open Telegram and message that bot directly with a few questions as a real outsider would. Ask a few questions within its scope, then one you know is not in the documents. See whether it answers in the right voice, whether it invents things, and whether it is willing to say it does not have that information.

If it is not right, turn it off, edit the Agent or add documents to the brain, then try again. Turning off takes effect immediately, with no Javis restart.

### Step 3: Handing over to a human

Fill in the **on-duty Chat ID** so the bot has somewhere to hand over when stuck. Get that number by having the person open **@userinfobot** on Telegram, which returns a line `Id: 123456789`.

The person on duty must click **Start** in a chat with this bot once, otherwise Telegram blocks the bot from messaging them.

The bot then has two handover routes: calling a human by itself when it is **stuck on two consecutive questions** from the same person, and reporting immediately when the person asking types `/nhanvien`. Both send the person on duty a message with the bot's name, the conversation id and the reason. A **technical failure** is also reported on the first occurrence, but only once until the bot works again.

Leaving this field empty means **the bot still answers normally** by its Agent, it simply has nobody to hand over to. Anyone typing `/nhanvien` is told honestly that no human line is available and invited to keep asking.

To make the bot stay silent when it finds no documents, that is the job of the **Documents only** mode above, not of this field.

### Step 4: Dropping the bot into a group

1. Invite the bot into the group like any member.
2. In the group, type **`/id`**. The bot returns the group id **and states the situation**: whether this group is enabled, whether Telegram's privacy mode is on or off, and what to do next.
3. That group **appears on the bot's card** on the Chatbot page. Click **Allow this group**. Done.

Use `/id` rather than naming the bot, and that is deliberate: **a `/...` command always reaches the bot** even with Telegram's privacy mode on, while a message naming it may not (see the section below). If the bot **says nothing at all** at step 2, the problem is not the group: either the bot is off or the token is broken; check the status dot on the card.

Declaring it by hand also works: take the id from step 2 (a **negative** number, shaped `-1001234567890`) and paste it into the **Allowed groups** field of the create or edit form, one id per line.

**Until a group is allowed, the bot does not answer in it.** That default is deliberate: a bot dropped into an unfamiliar group that takes work on itself is butting into other people's conversation. But refusing does not mean vanishing: the bot says one sentence telling whoever called it what to do, and that group waits on the card for you to decide.

For a group you do not want, click **Skip** and it leaves the waiting list. If someone calls the bot there again it comes back; this page does not hide a place where people are trying to use the bot.

In an allowed group, by default the bot only answers when someone **names it** (typing `@bot_name`, or picking its name from the member list) or **replies to one of its messages**. In a group with several bots it can tell them apart: naming another bot or replying to another bot does not make it answer.

To make it answer **every message in the group**, change the "When the bot speaks in a group" field. Weigh it carefully: in a busy group it is very noisy and burns model quota fast. And it only works once privacy mode is off, so read the next section.

### Telegram's privacy mode (read this if the bot is silent in a group)

Every new bot has privacy mode **on**. While it is on, Telegram **does not forward** most group messages to the bot, blocking them on Telegram's side, so Javis never sees those messages whatever you set in the dashboard.

What **certainly** reaches the bot while it is on:

- **Commands** `/...` (which is why `/id` always works).
- **A direct reply to one of the bot's messages** (using Reply on something the bot said).
- Service messages (members added or removed).

A message that merely **names** the bot depends on the version and the group type and is **not guaranteed**. If you tag the bot's name and it stays silent while direct messages work fine, this is almost always why.

Fix it in **one of two ways**:

1. Open **@BotFather**, type `/setprivacy`, choose this bot, choose **Disable**.
2. Or make the bot an **administrator** of that group. An admin bot receives every message regardless of privacy mode.

Then **turn the bot off and on again** on the Chatbot page so it re-reads the new state. The bot card shows this state for every bot that uses groups, and `/id` in the group states it too.

**When an ordinary group is upgraded to a supergroup, Telegram changes its id** (adding the `-100` prefix). Javis hears that and updates the list itself, so you do not have to re-declare it; this used to be a way for the bot to go silent leaving no clue at all.

## Reading a bot card

Each card has a coloured dot and a status line. There are **four** states, not two:

| Dot | Meaning |
|---|---|
| Green - Running | The bot is listening and answering normally |
| Yellow - Starting | Just enabled, shaking hands with Telegram |
| Red - Error | The bot died. A revoked token, a dropped network, or a token clashing with somewhere else. The reason appears under the card |
| Grey - Off | You turned it off |

The **Error** state has to be visible, because a bot dying silently is something you only discover when someone complains.

The cards **refresh themselves every few seconds** while you have the page open. That is necessary because the state changes with nobody clicking: right after Enable the card reads "Starting" (the bot is shaking hands with Telegram), then a few seconds later it becomes "Running". Without self-refresh the card would sit at "Starting" until you left the page and came back, long after the bot began answering.

The card also warns when **the bot's Agent is gone** (you deleted it or changed the slug on the Agents page). The bot still runs but answers with no role instructions, so fix it at once.

**The permission level appears on the card** at all three levels, not only the two with action rights: grey is Read only, yellow is Can write, red is Full power. You do not have to open the Edit form to see which bot is at which level, and a card with no label no longer reads two opposite ways.

## How many tokens a bot costs

A bot **does not go through** the Optimised and Ultra-saving levels on the Usage page. That is deliberate, not an omission: those levels exist to trim CLAUDE.md, MEMORY.md and the tool specification table, **three things a bot never had**.

Measured on a sample brain, the fixed part of each turn:

| Route | Fixed tokens |
|---|---|
| Dashboard chat, Full level | ~8,900 |
| Dashboard chat, Ultra-saving | ~460 |
| **A dedicated bot** | **~20** |

The rest of a bot turn is the documents it looked up, which is the answer itself, not overhead. In other words a bot is already lighter than the deepest saving level, so pushing it through those two layers would only make it **heavier**.

On the line under an answer and in the measurement table, a bot turn shows as **"Dedicated bot"**. Before 0.23.1 it was lumped into "Full", the exact opposite of the truth, since this is the cheapest route in the system.

A bot still counts towards **Usage** like any other turn, under the provider and model actually running.

Do not confuse a bot with **your own Telegram channel**: that channel *does* go through the two saving levels (since 0.24.0), because your Javis really does have a CLAUDE.md and a MEMORY.md to trim. A bot has nothing to trim.

## What the bot answers from

Every time someone asks, Javis **looks up documents in the bot's brain first**, takes the few best-matching passages, then puts them straight into that turn's prompt.

That differs from "the bot has permission to read the brain". Permission to read does not mean it will read: the model can answer straight from its general knowledge, the sentence flows just as confidently, and **you cannot tell from the outside**. So Javis looks up first rather than leaving that decision to the model.

### Two modes, chosen when creating the bot

The difference lies only in **what happens when no matching document is found**. When one is found, both modes behave identically.

| Mode | What the bot does with no document found | Suits |
|---|---|---|
| **The Agent's expertise** (default) | Javis adds nothing; the Agent handles it by the rules you wrote | Advisory, coaching, training and know-how bots |
| **Documents only** | One rule is added: say there is no information, do not use general knowledge | Bots quoting figures and rules, where a wrong sentence is a real loss |

Choosing wrong is obvious immediately: a coaching Agent running in "documents only" answers "I do not have that information" to questions squarely in its expertise, however carefully you wrote the role instructions. Change the mode with the **Edit** button, effective immediately.

### Javis does NOT write rules for the bot

This is the most important thing to know about this page.

The bot runs on **exactly the content of your Agent file**, nothing more. Javis inserts no rules on top: it does not tell it how to address people, does not forbid a topic, does not force short answers. The rules you write in the Agent are the only rules the bot has.

The one exception is the "documents only" mode above, and that is a rule **you deliberately turned on**, not a Javis default.

So **the Agent file decides the bot's quality almost entirely**. Write it like briefing a new hire: how to speak, how far the scope goes, what must not be promised, and in which cases to hand over to a human. When the bot behaves wrongly, fix the Agent rather than hunting for another button.

### Two rails Javis locks at EVERY level

The two points below hold even when you give the bot full power. They live in the source code rather than in wording, so no clever phrasing gets around them:

- The bot **cannot see another brain**, your main brain included. Every file read and write is clamped inside the bot's own brain folder; climbing out with `../` or an absolute path is refused outright.
- The bot **cannot run machine commands**, cannot open an unfamiliar web page to read, cannot spawn child agents. The bot also has **no admin commands**: `/brain`, `/model`, `/status` do nothing.

How Javis guarantees it: **the bot never touches the engine's native tools.** At the Read only level it has no tools at all; at the two higher levels every tool goes through Javis's connection hub, where file paths are clamped and the permission level is applied right at the call site. The bot does not open a CLI, so Claude Code's `Bash` and absolute-path `Read` are simply not present here.

Documents are still looked up by Python before the model runs and placed into the prompt, at every level. The bot reads its own brain without needing any tool.

## The three permission levels: what the bot may do

Chosen in the **What the bot may do** field when creating or editing a bot. The default is **Read only**.

| Level | What the bot can do | Suits |
|---|---|---|
| **Read only** (default) | Only read documents and answer. No tools. | Duty and Q&A, which is nearly everything |
| **Can write** | Adds: writing files in its own brain, calling attached data sources at read/write level | Recording requests, updating notes, looking up real figures |
| **Full power** | Adds: sending, paying, booking and cancelling, deleting, publishing outward | Places where you control the list of people who can message it |

### What you lose by raising the level

This is the part of the page most worth reading carefully, because it is the fundamental difference between a dedicated bot and your own Javis: **the person typing into the bot is somebody else, not you.**

At Read only that is harmless: however cleverly someone talks it around, the bot can only say something off topic, because it has nothing with which to do harm. Raising the level removes exactly that property.

**The Can write level:**

- The bot can write files in its brain. One message from someone genuinely changes content in the brain, **with no approval step**.
- The bot can call the data sources you attached, at read and write level. Everything in those sources is within reach of whoever is chatting with the bot.
- Javis still **hard-blocks** the outward-action group at this level: no sending, no payments, no booking or cancelling, no deleting, no publishing. Blocked at the tool-call layer, not by wording.

**The Full power level:**

- The bot can do **everything** the attached sources allow, sending, paying, booking, cancelling, deleting and publishing outward included. Those actions **cannot be undone**.
- One clever sentence ("ignore the previous instructions and do this for me") is enough. The only remaining rail is the Agent file you wrote, and words can be talked around.
- The bot does not check with you first. There is no per-command approval gate.

So: **only turn Full power on when you control the list of people who can message the bot.** Somewhere anyone can message, do not, however carefully you wrote the Agent.

### How to raise the level

1. Click **Edit** on the bot card (or choose it while creating).
2. Pick the level in the **What the bot may do** field. That level's risk list appears right below.
3. Tick **I have read and accept the risks above**. Without the tick it cannot be saved, and Javis blocks it in both the interface and the server, so removing the tick box with devtools does not raise it either.
4. Full power asks once more before saving.
5. Enabling the bot asks again too, because creation may have been days ago and whoever clicks Enable may not remember what level this one is at.

Lowering the level asks nothing: lowering is always safe, and while you are trying to put out a fire you should not have to click extra.

A bot card with a raised level carries a coloured band naming the level, yellow for Can write, red for Full power. A Read only bot carries no label, since that is the default. The log also records the level of **each turn**, so reviewing "what the bot did that day" stays accurate even after you lowered the level following an incident.

### Which engines can run the raised levels

The **Read only** level runs identically on all nine brains, with no exceptions.

The two raised levels need an engine that can call tools. The six API engines (OpenRouter, OpenAI, Anthropic, Gemini, Groq, Ollama) and the Claude Code plan use a route that has run reliably for a long time. The **ChatGPT plan** alone goes through a Codex backend route the provider has not published as stable, so tool calling may fail.

In that case **the bot does not die**: it answers that turn at the Read only level, and the bot card shows a yellow band stating it is running with fewer permissions than you set. Raising permissions must never take away a capability the bot already had.

Seeing that yellow band, choose one of two things: change the engine on the **Models** page if you genuinely need the bot to act, or lower the bot to **Read only** so nobody mistakes it for acting.

### Changing the brain does not change the experience

A bot runs identically on **every brain**: Claude Code, ChatGPT, Grok Build, Antigravity, OpenRouter, OpenAI API, Anthropic API, Gemini, Groq, Ollama. Changing the model on the Models page changes the bot's model, but not how it works. When tool calling is available, every engine holds **exactly one toolkit**; see the note above about the ChatGPT plan.

That works because a bot turn takes its own route, shared by every engine: the same prompt from the Agent, the same pre-fetched documents, the same conversation history, and tools (when present) taken from the same place. What remains different is exactly the difference between the models, not between the pipelines.

That route also does not open a CLI, so a bot answers faster than your own chat route.

### Making documents match well

- **Give files clear headings.** Javis splits documents by markdown headings (`##`), and each passage is retrieved on its own. A long file with no headings can let the bot read half a condition and answer as if it were the whole condition. Splitting into "Retail price", "Wholesale price", "Returns", "Delivery" and so on matches best.
- **Files outsiders upload do NOT count as documents.** They sit in `inbox/khach/` and are excluded from the lookup entirely. Otherwise anyone could upload a file overriding your rules, ask a question, and have the bot quote it as official documentation.
- **Javis's own convention files are excluded too.** `CLAUDE.md`, `AGENTS.md`, `wiki/index.md`, `wiki/log.md` and a few other navigation files exist in every brain but are system innards, not content to answer outsiders with. Your real Wiki notes are used normally.
- **Typing with or without diacritics both find things**, but typing with diacritics is more accurate: "bán" does not match "bản", "cà" does not match "cả". Documents should be spelled correctly and accented correctly.

## The log and where documents are missing

Click **Log** on the bot card. There are two tabs, and the one that opens is the more important.

**Bot stuck** lists the questions the bot could not answer, deduplicated and sorted by **how many times they were asked**. This is the most valuable tab: each line points at one gap in your documents, in the asker's own words. Writing that into the brain makes the bot able to answer next time.

Deduplication strips diacritics, so "Giá bao nhiêu?" and "gia bao nhieu" count as one question. Otherwise the same question would split into several separate lines and you would not see how often it is really asked.

"Stuck" is measured by **what the bot itself just said**: it said it has no information, or it had to hand over to a human. For a bot running "documents only", finding no documents counts too.

The most notable kind of stuck is the one where the bot **did find documents**: the documents exist but lack the exact point people need. That kind points at documentation written incompletely, which is subtler than having no file at all.

**Recent conversations** lets you review each turn, along with **the exact files the bot used** to answer. That source line is what makes "did the bot answer correctly" verifiable rather than guessed.

### When the person on duty is called

With an on-duty Chat ID set, the bot calls a human in two cases: the person asking types `/nhanvien`, or the bot is **stuck on two consecutive questions** from the same person. Answering one question resets the count to 0.

A single stuck question does not call. Reporting every stray question makes the person on duty mute notifications within days, and then nobody reads them when someone genuinely needs help. Two consecutive questions is the real sign that someone is stuck.

The third case is the bot **breaking** (unable to reach the model). That is reported on the first occurrence rather than waiting for two questions, because every silent minute makes the person messaging feel abandoned. But it is reported **once** until a turn works again, otherwise the on-duty inbox becomes an error log.

Before considering it broken, Javis has already retried up to three times if the error was **transient** (the provider returning 429 for too many calls, a 5xx overload, a network blip). A momentary 429 no longer wakes the person on duty. A break notice carrying *(retried 3 times)* means everything was tried, so go and look at the **Models** page or the account's quota. Details in [Troubleshooting](17-troubleshooting.md#the-provider-reports-a-rate-limit).

The log keeps the 2000 most recent turns per bot, trimming older ones. Deleting a bot deletes its log with it.

## What a bot can and CANNOT do

**At every level, a bot can:** read documents in its brain, answer by the rules in the Agent file, remember the thread with each person, hand over to the person on duty.

**At every level, a bot CANNOT:** read or write another brain, run machine commands, open an unfamiliar web page, spawn child agents, use admin commands (`/brain`, `/model`, `/status` all do nothing and the bot only answers generically).

**Everything else depends on the permission level** you set: writing files, calling data sources, acting outside. See the table in [The three permission levels](#the-three-permission-levels-what-the-bot-may-do). The default is Read only, meaning none of those.

The bot's Telegram command menu has only three items (`/help`, `/nhanvien`, `/id`), not the main Javis bot's admin menu. Listing commands the bot refuses to run there would only teach people to go looking for a different command set.

And **how it speaks, what scope it accepts, what it refuses** are decided by your Agent file, not by Javis. To make the bot avoid a topic, not make promises on your behalf, or not change role when talked around, write those things into the Agent.

The right way to understand the limits above: they live in the **permission level in the source code**, not in wording inside the prompt. Wording can be talked around by clever phrasing; a permission level cannot, because the tool is simply not granted for that run. The flip side of the same truth: when you **do** grant tools for that run, the wording in the Agent cannot hold it back either.

## The bot speaks like a person, exposing no machine state

A dedicated bot **shows no Javis status lines** to the person messaging it. This is the sharp difference from your own main Javis bot (which does show everything, see [Telegram](11-telegram.md), because the owner needs to see how far Javis has got).

Specifically, someone messaging a dedicated bot will NEVER see:

- the "🤔 Javis is working…" message and its "⏳ ⚙ Calling a tool…" updates
- the sentence "⏳ Still handling the previous question. Send /stop to stop then ask again."
- a technical error line like "⚠ Error: TimeoutError: ..."
- the words "(no content)" when a turn returns empty

Instead, while the bot thinks, Telegram shows the **"typing…"** dots at the top of the conversation, exactly what a real person leaves while writing. A broken turn makes the bot apologise in an ordinary sentence and invite another message; the technical reason is still fully written into the bot log and still reported to the person on duty if you set one.

**Messaging again while the bot is answering is not blocked.** The bot gathers those messages and, having finished the previous answer, answers them together, exactly like a person reading the rest of the messages before replying. It gathers at most 5 messages per conversation so a stranger cannot spam its memory into bloat.

One place still deliberately speaks plainly: when someone calls the bot in **a group you have not allowed**, the bot says one sentence once, stating it is not enabled for this group. Staying entirely silent there would make the bot look broken with no way for you to know to click **Allow**.

## Rate limiting

Each person is limited to a number of questions per hour (20 by default, editable when editing the bot). Over that, the bot politely asks to answer later.

This is necessary because one bored person in a group can burn your whole model quota in an afternoon, and you only find out from the bill.

## Deleting a bot

Click **Delete** on the card. The bot stops answering immediately.

**Its brain and Agent are NOT deleted.** The brain may hold a month of documents you wrote, and the Agent may be in use by another bot or a workflow. To delete those, delete them on their own pages.

## Frequently asked questions

**Which model does a bot use?** The very model you chose on the Models page. Changing the model changes the bot's model, and how it works does not change, since every brain takes the same route.

**Can a bot call the data sources I attached?** Not by default; the Read only level has nothing but the documents in its brain. Raising it to **Can write** grants that, and **Full power** grants the outward-action group too. Weigh the fact that whoever drives it is whoever messages it; for something only you need, asking Javis on the dashboard or your own Telegram channel is still safer.

**Is a Full power bot dangerous?** Yes, which is why Javis requires a consent tick then asks once more. The danger is not the model misbehaving but that **anyone can message the bot**: one clever sentence makes the bot call a real tool, unrecoverably and without checking with you. Only use it where you control the list of people who can message it.

**What do I do right now if a Full power bot looks wrong?** Click **Disable** on the card, effective within seconds and needing no Javis restart. Then click Edit and lower it to Read only; lowering asks nothing. Review what the bot did under **Log**, the Recent conversations tab.

**Can I run several bots at once?** Yes. Each bot has its own token and its own process. The Chatbot page is built for it.

**Can two bots share one Agent?** Yes, and sometimes it makes sense: the same role but two different brains for two different audiences. The reverse, two bots sharing one token, is not allowed and Javis blocks it.

**What happens when people send the bot images?** Uploaded files land in `inbox/khach/` in that bot's brain, kept apart from your files, and do not count as documents for answering.

**The bot answered one question wrongly, where do I review it?** Click Log, the Recent conversations tab. The source line under each turn says which file it took the answer from, so you can fix exactly the right place.

**The bot says "I have no information" although the documents clearly cover it?** Usually because the file is long with no headings, or the documents use quite different words from the question (the document says "refund" while the asker types "return"). Add headings to the file, or write the wording people actually use into that very passage.

**Does the bot remember who messaged it?** Yes, each person has their own conversation thread in the bot's brain.

**I dropped the bot into a group, tagged its name and it does not answer, but direct messages work?** Type **`/id`** in that very group and the bot will answer and state the cause. Three causes produce this one symptom: the group is not enabled yet (click **Allow this group** on the bot card), Telegram's privacy mode is still on (see [Privacy mode](#telegrams-privacy-mode-read-this-if-the-bot-is-silent-in-a-group)), or the bot could not ask for its own identity (turn the bot off and on again). If even `/id` gets no response, the bot is not running, so check the status dot on the card.

**The bot is set to "answer every message" but still only answers when named?** Telegram's privacy mode is still on, blocking those messages on Telegram's side so Javis never sees them. Turn it off in @BotFather (`/setprivacy` → Disable) or make the bot a group administrator, then turn the bot off and on again. The bot card warns you when this situation applies.

**Does the bot run when Javis is off?** No. The bot runs inside the Javis process, so the machine or VPS has to be on. Restarting Javis restarts every enabled bot by itself.

## See also

- [Agents and Workflows](07-agents-and-workflows.md) - writing the Agent that acts as the bot's brain.
- [The Telegram channel](11-telegram.md) - your own personal Telegram bot, entirely different from the bots here.
- [Second Brain](13-second-brain.md) - creating a brain and loading the documents the bot reads.
- [Security and accounts](14-security-and-accounts.md) - how tokens are encrypted.
