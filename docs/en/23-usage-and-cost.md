# Usage: tokens and cost

*[Tiếng Việt](../23-muc-dung-token.md) · **English***

The **Usage** page answers two questions that go together: *how many tokens you burned* and *how to burn fewer*. Javis measures these numbers itself from the real logs on the machine rather than asking the provider, so you also see the part Claude and ChatGPT never reveal: what Javis's own background runs consumed.

At the very top of the page is the **Token saving mode** block with three buttons. It has been here since version 0.24.7; before that it was a separate "Saving" page on the sidebar. They were merged because when they were apart, people read the whole bill and never saw the switch.

This page covers choosing the saving level, then reading each card, each chart and each table, and how to use it to find what is eating your quota.

## What this feature is

Javis sees the input and output tokens of **every** answer, whichever engine ran it (Claude Code, ChatGPT/Codex, OpenRouter, OpenAI, Anthropic). So the numbers here are consistent, **regardless of whether the provider exposes quotas at all**.

Two things to remember before reading any number:

- **This is what YOU HAVE USED, not what remains of a subscription quota.** Most providers do not expose the quota through an API. This page counts what went past, and does not know how much of your plan is left. The one exception is OpenRouter (see below).
- **The cost on the page is a CONVERSION, not real money.** With a Claude or ChatGPT subscription, the dollar figure only answers "what would this have been worth at API prices". Only OpenRouter is real money.

The page gives you: a filter of 8 periods and 4 providers, summary cards with a comparison against the previous period, a per-day token chart, three breakdown bar charts (consumption source / activity / provider), two ranking tables (models and projects), and an auto-generated list of saving suggestions.

## Where to open it in Javis

Open the dashboard (default port 7777). On the left navigation rail, open the **System** group (pinned at the bottom of the rail), then click **Usage** (the 📊 icon).

The page header reads **Usage** with the subtitle "Tokens and cost by day, by provider".

## Token saving mode (the block at the top)

Every time you chat, Javis has to send the model a pile of background information: who it is, which tools it has, what it remembers about you, what was said before. That pile costs money and eats quota. The three buttons here decide how big it is.

- **Off** - the Full mode. Everything, every turn. The safest, the most expensive.
- **Optimised** - only what relates to the question just asked: selective memory, skills loaded on demand.
- **Ultra-saving** - like Optimised, plus a shortcut for simple questions that need no lookup. **This is the default since version 0.24.7.**

Each button states how much it saves as a percentage and how many tokens per turn remain. That figure is **measured on your own brain and memory**, not a marketing number, so two machines will show two different numbers.

If the brain you are running does not support a level, that level's button says outright *"not applicable to the brain in use"*. For example the Ultra-saving shortcut only runs on API-key brains, so on a subscription plan it equals the Optimised level.

Once enough turns have run in both modes within 24 hours, a **measured** number block appears right under the three buttons: tokens per turn in Full mode, tokens per turn while saving, and the percentage saved. Those are real numbers, not estimates.

**A level change takes effect immediately**, no restart needed. If Javis starts answering worse, clicking **Off** returns it to how it was at once.

### Why the default is Ultra-saving

Before 0.24.7 the default was **Off**, and almost nobody turned it on, meaning most people were paying for the most expensive mode without knowing. Measured on a sample brain: Off costs about 8,900 fixed tokens per turn, Ultra-saving about 460.

This is a safe default rather than a gamble: every path in this mode is **fail-closed**. Missing a prerequisite makes that turn drop back to Full mode rather than answering wrong.

If you **ever clicked a level yourself**, Javis pins that choice and no update changes it again, even when you deliberately clicked **Off**. The line under the three buttons tells you whether you are on the default or on your own choice.

## How to use it (step by step)

### Step 1: Open the page and wait for the first scan

On arrival, the page reads "Building the token index...". The first opening makes Javis **re-scan the logs** before drawing, so it can take a few seconds if you have used it for months. Later filter changes do not scan again, only reading the index, so they are very fast.

If the page reports "Could not load token data", the server has not returned anything, see Common problems.

### Step 2: Choose the period

The first row is 8 period buttons: **Today**, **Yesterday**, **This week**, **Last week**, **This month**, **Last month**, **3 months**, **This year**. The selected period is highlighted. The page opens on **This month** by default.

Each period compares itself against the equivalent preceding one, and the comparison appears right under the "Total tokens" card.

### Step 3: Filter by provider

Just to the right of the period buttons is a joined group of 4: **All** (the default), **Claude Code**, **ChatGPT**, **API**. Click one to see a single source.

This filter affects the summary cards, the chart and the breakdown tables. The **Suggestions** section at the bottom of the page always computes across every provider, ignoring this filter.

### Step 4: Read the summary cards

The card row right under the filters:

| Card | The number | The line below |
|---|---|---|
| **Total tokens** | Total tokens in the period (cache-read tokens included) | "▲ x%" or "▼ x%" with "vs the previous period"; with no prior figure it reads "no figure for the previous period" |
| **Tokens/day** | The daily average across the period | "average in the period" |
| **Cache hit** | The percentage of input tokens that were cache reads | "context reuse (high = cheap)" |
| **Sessions** | Sessions that produced tokens in the period | "avg ... /session" - average tokens per session |
| **Converted cost** | Money converted at API list prices | "at API prices" |
| **OpenRouter left** | The real remaining balance (shown only when an OpenRouter key is attached) | "real money spent $..." |

Note the arrow colours: **▲ (up) is red, ▼ (down) is green**. Here up is bad news, not good.

About **Cache hit**: "Total tokens" includes cache-read tokens so it looks very large. A high cache hit means most of that huge number is only re-reading old context (very cheap) rather than loading new. Read these two cards together.

### Step 5: Look at the per-day token chart

The **Tokens by day** section draws one bar per day. Each bar stacks 3 colours by provider, with a legend right below:

- **Claude** - the interface accent colour
- **ChatGPT** - green
- **API** - blue

The horizontal axis shows days of the month. Hovering a bar shows a tooltip like "2026-07-29: 12.3M tokens". Long periods (3 months, This year) make the chart scroll horizontally.

### Step 6: Find what is eating tokens

Below the chart are three horizontal bar charts, the most important part of the page:

- **Consumption source (you vs Javis)** - two rows: "You typing" and "Javis (running itself)".
- **Activity** - four rows: "Chat", "Background (loop/schedule)", "Subagent", "Manual".
- **Provider** - "Claude Code", "ChatGPT/Codex", "API (OpenRouter...)".

The meaning of each label is in [Consumption source and activity type](#consumption-source-and-activity-type) below.

Next are two ranking tables, each showing at most 8 rows:

- **Hungriest models**: the Model, Tokens and Converted columns. Model names are shortened to fit (dropping the `claude-` / `gpt-` prefix, trimming long tails). The Converted column shows "-" when that model is not in the price table.
- **Hungriest projects**: the Project, Tokens and Sessions columns. "Project" is the brain name when Javis recognises which brain the session belonged to, otherwise the working folder name.

### Step 7: Read the Suggestions section

When the figures cross a threshold, Javis generates suggestion cards at the bottom of the page. An ⚠️ card with an orange border is something you should do, a 💡 card with a blue border is a hint. Threshold details are in [Saving suggestions](#saving-suggestions).

No cards at all means every metric is within normal bounds, not that something is broken.

## Quick reference of the 8 periods

Every date boundary follows Vietnam time (UTC+7).

| Button | The period shown | Compared against |
|---|---|---|
| **Today** | Today | Yesterday |
| **Yesterday** | Yesterday | The day before |
| **This week** | Monday to today | The same stretch of last week |
| **Last week** | Monday to Sunday last week | The week before that |
| **This month** | The 1st to today | The same number of opening days last month |
| **Last month** | The whole of last month | The whole month before that |
| **3 months** | The last 90 days | The 90 days immediately before |
| **This year** | 1 January to today | 1 January last year to the same date last year |

The comparison used by "This week" and "This month" is deliberate: a period still in progress is compared only against **the matching stretch** of the previous period, not the whole of it. Otherwise every 3rd of the month would report a 90% drop.

## Consumption source and activity type

This is where you learn **what is eating your quota**, and it is exactly what the provider's own statistics do not show you.

**Consumption source** splits in two:

| Label | What it means |
|---|---|
| **You typing** | Sessions where you opened `claude` in a terminal yourself, not through Javis |
| **Javis (running itself)** | Sessions Javis started through the Agent SDK: dashboard chat, Telegram chat, background work, workflows |

**Activity** splits in four:

| Label | What it means |
|---|---|
| **Chat** | Turns tied to a real conversation session in your history |
| **Background (loop/schedule)** | Turns Javis ran with no conversation session attached: recurring jobs, reminders, Kanban work, digesting sources, self-learning |
| **Subagent** | Turns from a child agent the engine spawned for a side job |
| **Manual** | Turns from sessions you typed yourself outside Javis |

A swelling **Background (loop/schedule)** bar is the clearest sign you have loops running too often. Review them on the **Recurring jobs** page ([Recurring jobs and reminders](08-recurring-jobs.md)) or the **Work** page ([Work / Kanban](21-kanban-work.md)).

One limitation to know: **this split is only accurate for Claude Code.** For ChatGPT/Codex, Javis cannot yet separate background from chat, so every turn falls into "Javis (running itself)" + "Chat". The API branch is the same.

## Converted cost and real money

The **Converted cost** card and the **Converted** column in the model table are computed from a fixed price table (USD per million tokens) shipped with the app at `server/usage_pricing.json`. It currently has prices for the `claude-opus`, `claude-sonnet`, `claude-haiku`, `claude-fable`, `gpt-5` and `gpt-4o` families. Models are matched by longest prefix; **a model absent from the table has its cost counted as 0** and shows "-".

So the converted figure is always an estimate, and always lower than reality if you use a model not in the price table. For more accuracy, edit that file by hand and restart the server.

**OpenRouter's real balance** is the one thing on this page that is real money. The "OpenRouter left" card only appears once you have saved an OpenRouter key on the **Models** page (the Connections group). Javis asks OpenRouter directly how much credit was added and used, then shows the remainder with the line "real money spent $...". With no key there is no card, and no other provider exposes an equivalent figure.

## Saving suggestions

This list is generated from the figures of the period you are viewing. The thresholds live in `server/usage_index.py`:

| Suggestion | Appears when | Level |
|---|---|---|
| **Low cache hit (x%)** | The cache hit is under 50% and the period is large enough (200,000 input tokens or more) | ⚠️ |
| **Background activity takes x% of tokens** | The "Background (loop/schedule)" share reaches 25% of total tokens | ⚠️ |
| **Opus takes x% of tokens** | The `claude-opus` models reach 50% of total tokens | 💡 |
| **A session has ballooned (x input tokens)** | One session loaded 1 million input tokens or more | ⚠️ |
| **Tokens/day up x% against the previous period** | This period's daily tokens are 1.5 times the previous period's or more | ⚠️ |

Each card carries a specific suggested action, for example the low-cache suggestion recommends `/compact` or splitting the session, and the opus suggestion recommends downgrading the model for light work. The 200,000-token threshold on the cache warning exists so the page does not shout after you have used it for a few minutes.

## Where these figures come from

Javis calls no provider API for statistics. It **re-reads the raw logs on your own machine** then builds its own index:

| Source | Where | What it gives |
|---|---|---|
| Claude Code logs | `~/.claude/projects/**/*.jsonl` | The Claude column, cache included, with chat/background/subagent classification |
| Codex logs | `~/.codex/sessions/**/rollout-*.jsonl` | The ChatGPT column, one file per session |
| The internal journal | `usage-events.jsonl` in the state folder | The API column, and the fallback source for Claude/ChatGPT |
| The conversation store | `conversations.db` in the state folder | Used to tell which turns are real chat and which are background runs |

The results are merged into one SQLite database, `usage_index.db`, also in the state folder (set by the `JAVIS_STATE_DIR` variable, see [.env configuration](16-env-configuration.md)).

The scan is **incremental**: a file whose size and modification time are unchanged is skipped entirely. That is why the first scan is slow and later ones are very fast, even with thousands of log files.

The API branch has no raw log to read, so it only has figures **from the moment you upgraded to the version with this feature**. Claude and Codex have history back to when you started using them, because their logs were already on the machine.

If the install cannot read raw logs (typically the Docker build on a VPS, where your `~/.claude` folder is not in the container), Javis builds the figures from the internal journal instead, so the page still shows numbers rather than the zeros it used to. On a day with both sources, the raw log wins so nothing is double counted. The tell: in the "Hungriest projects" table, a row named `(events)` was built from the internal journal, and an `(api)` row is a turn through an API provider.

## Quick reference of buttons and states

| What you see | Meaning / action |
|---|---|
| The 8 period buttons (**Today** ... **This year**) | Change the period viewed; the highlighted one is selected |
| The **All / Claude Code / ChatGPT / API** group | Filter by provider |
| **↻ Refresh** | Re-scans the logs then redraws; while running the button reads "Scanning..." |
| "Building the token index..." | Loading for the first time |
| "Could not load token data." | The server could not be reached |
| "No data yet." | That cell has no figure in the selected period |
| "no figure for the previous period" | The previous period was 0 so no percentage change could be computed |
| ▲ red / ▼ green | Up / down against the previous period |
| An ⚠️ card with an orange border | A warning-level suggestion |
| A 💡 card with a blue border | A hint-level suggestion |

## Tips

- Open **This month** first to see the trend, then click **Today** to inspect a specific day. Reading it the other way round is alarming, because a single day always looks abnormal.
- Suspecting loops run too often, filter to **Claude Code** then look at the "Background (loop/schedule)" bar in the Activity section. It is the one number that tells you outright how much Javis spends while you are not at the machine.
- A low cache hit with high total tokens means the problem is session length, not the number of chat turns. Splitting the session is the cheapest way to bring it down.
- The "Hungriest projects" table is the quick way to see which brain costs most when you use several.
- Only click **↻ Refresh** when you just finished something big and want to see it now. Ordinarily opening the page already scans.

## Common problems

- **The page shows all zeros.** Usually the install cannot read the raw logs, most commonly on Docker/VPS because your `~/.claude` and `~/.codex` folders are not inside the container. In recent builds Javis uses the internal journal as a fallback so figures still appear, but only from your upgrade onwards. If it is still zero after upgrading, no chat turn has been recorded since, so chat a few messages then click **↻ Refresh**.
- **The numbers are far lower than they feel.** Check whether a provider filter is on, and check the selected period. Also, the "You typing" share can only be counted when you run Claude Code on the **same machine** as Javis.
- **A Google Gemini key is attached but the API column does not move.** Gemini turns are written into the internal journal, but the index builder currently only accepts OpenRouter, OpenAI and Anthropic into the API column, so the Gemini share does not reach this chart yet.
- **There is no "OpenRouter left" card.** The card only appears when an OpenRouter key is in the model settings and OpenRouter responds. Go to the **Models** page (the Connections group) and check the key, see [Models and engines](10-models-and-engines.md).
- **The page shows a simple "Today / Cumulative total" table instead of the period filter.** That is the fallback interface, appearing when the new interface file could not load. Reload the page, clearing the browser cache if needed.
- **The converted cost shows "-" for the model you use.** That model is not in the `server/usage_pricing.json` price table. It is maintained by hand, so add a row for your model then restart the server.
- **You just upgraded Javis but the page has not changed.** This page has a backend component, so after an update you need to **restart the server** before reloading the page.

## Related

- [Models and engines](10-models-and-engines.md) - switching models, attaching an OpenRouter key, understanding where each engine records its figures.
- [Recurring jobs and reminders](08-recurring-jobs.md) - where to turn loops down when the "Background (loop/schedule)" bar swells.
- [Work / Kanban](21-kanban-work.md) - background work also counts into the "Javis (running itself)" share.
- [.env configuration](16-env-configuration.md) - the `JAVIS_STATE_DIR` variable decides where the token index lives.
- [Troubleshooting and FAQ](17-troubleshooting.md) - general dashboard errors.
