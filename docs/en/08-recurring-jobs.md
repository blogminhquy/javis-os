# Recurring jobs & reminders

*[Tiếng Việt](../08-viec-dinh-ky.md) · **English***

The **Recurring jobs** page is where you hand Javis work that runs while you are not at the computer: jobs that repeat on a cycle (called **loops**) and reminders at a set time. Each loop wakes on its cycle, does exactly the one task you described, verifies itself, writes a log entry and messages the result to you on Telegram.

This page aggregates jobs from **every brain**, not just the one selected in the sidebar.

## What this feature is

Two kinds of job share one page:

| Kind | Nature | Stored where |
|---|---|---|
| 🔁 **Loop** | Every N minutes it wakes, does one job and stops. It runs forever until you switch it off. | An `.md` file in the brain's `Javis/loops/` |
| ⏰ **Reminder** | A specific moment ("in 30 minutes", "8:30"), or a cron schedule repeating at a fixed time ("7am every day"). | The brain's `Javis/reminders.json` |

The key difference: a loop counts the **gap** between runs, a reminder counts a **clock time**. "Scan orders every 2 hours" is a loop; "report revenue at 7am every day" is a reminder using cron.

You can create **many loops in parallel**, each in its own file. But they run **sequentially**: at any moment the whole system runs exactly one iteration. Javis's scheduler checks every 30 seconds, and each check picks **one** loop, the one most overdue. So the real run time can drift a few dozen seconds from the cycle you set, and several loops due at once queue rather than overlapping.

A loop **can read real data through MCP** (POS, ads, calendar, analytics...) to do its work. Whether it can write files or take real outside actions depends on the **permission level** you pick, see "The three permission levels" below.

Loops can be edited directly by opening the `.md` file in Obsidian or the [File manager](05-file-manager.md) page. Run state (last run, iterations today, error streak) lives separately in `Javis/loop-state.json`, owned by the server, so you can edit the definition file without stepping on it.

## Where to find it in Javis

1. Open the Javis dashboard (`http://localhost:7777` by default).
2. In the left navigation rail, open the **Work** group.
3. Click **Recurring jobs**.

The page opens with the subtitle "Recurring jobs + pending reminders". Top to bottom you see: a short introduction, the **+ Add job** and **■ Stop the running iteration** buttons, a search box, the job cards grouped by brain, and finally the **Recent log** block.

The create/edit form stays hidden until you click **+ Add job** or **Edit** on a card.

## How to use it (step by step)

### Step 1: Click "+ Add job"

The form appears right under the button row.

### Step 2: Pick the job kind

**Job kind** has two buttons: **🔁 Loop** (preselected) and **⏰ Reminder**. Click to switch. The fields below change with the kind.

Note: clicking **Edit** on an existing card locks and dims these two buttons. The form only edits loops; reminders can only be cancelled or moved between brains from the card.

### Step 3: Name and describe it

- **Name**: the short name shown on the card, for example "Read email every 2 hours". Leaving it empty reports "Enter a name".
- **Task description (each iteration, Javis does exactly this)**: this field is **required** and is the most important thing here. Javis does not invent work; each iteration it does exactly what you wrote here, then stops. Leaving it empty reports that Javis needs to know what each iteration should do.

Choosing **⏰ Reminder** relabels the field to "Reminder content (Javis will remind you or do exactly this)", and the empty-field error becomes "Enter the reminder content".

Write the description as specifically as possible: say what to read, what to do, where to save it. Make it self-contained rather than relying on the current chat context, because it runs when nobody is there. For example:

> Each iteration, read 1 unprocessed source in 06 - Sources and propose which Wiki page to create.

> Read today's order count through the POS MCP, and if it is low, draft one promotional caption into 05 - Projects.

### Step 4a (loops): pick the mode and the cycle

- **Mode**: three buttons, **Suggest (read-only)**, **Auto (safe)**, **⚠ Full power**. New jobs default to **Suggest (read-only)**. Read "The three permission levels" below before changing it.
- **Cycle (minutes, minimum 5)**: the number of minutes between runs. The field is prefilled with **120**. Anything under 5 is raised to 5 by the server.

Under the form there is a reminder line: Suggest = read only plus suggestions. Auto (safe) = writes draft files and reads MCP, NO money/orders/publishing. Full power = does everything itself.

### Step 4b (reminders): set "When" and "Type"

- **When**: the time field. See the full list of accepted forms in "What the When field understands" below. Leaving it empty reports an error with examples such as "in 30 minutes", "8:30", "0 7 * * *".
- **Type**: two buttons, **⏰ Remind only** (preselected) and **🤖 Do it and report**.
  - **⏰ Remind only**: at the set time, Javis sends a Telegram message starting with "⏰ Reminder: " followed by your text. No model call, no tokens.
  - **🤖 Do it and report**: at the set time, Javis runs the engine to actually **do** the job and sends the result to Telegram.
- **What it may do** (only shown for 🤖 Do it and report): three levels, defaulting to **Full power**.
  - **Read only**: reads real data through MCP and reads files, then reports. Writes nothing, does nothing outside.
  - **Write files**: adds permission to write draft files in the brain. Still no orders, no spending, no publishing, no messaging.
  - **Full power** (default): every tool you connected, outside actions included. This is the only level that can do things like "send the message at that time", "publish at that time", "book the calendar at that time".

  Why the default is Full power: a reminder does **exactly the one thing you wrote down and scheduled**, which is a chat instruction moved to a later time. Restricting it more than when you sit chatting means telling it "send this for me at 10am tomorrow" and being told at 10am that it was not allowed to send. In exchange, choosing this level shows a red warning box in the form, and the job card carries a **full power** label so one glance tells you. Remember: **it runs when nobody is next to it**, there is no approval step, and sending a message or publishing cannot be undone. Only hand it what you are willing to let it do alone.

### Step 5: Pick the brain

The **Brain (where the job is stored)** field picks which brain holds this job, defaulting to the one in your sidebar. When **editing** an existing loop, this field locks to its own brain. To move a job to another brain, use the **Move to brain…** picker on the card rather than changing it while editing.

### Step 6: Save

Click **💾 Save**. The button reads "Saving..." then returns. On success the form closes and the list reloads. Errors appear next to the button as an orange "⚠ ..." line.

If you picked **⚠ Full power**, a confirmation dialog restates the risk before saving. Cancelling there saves nothing.

### Step 7: Switch the job on

**A loop created from the dashboard is always OFF.** That is deliberate safety: you reread the description, then click **Enable** on its card. Until you do, it never runs.

Reminders are different: once created they are already queued, with nothing to switch on.

## The three permission levels (loop modes)

| Button in the form | Label on the card | What Javis may do |
|---|---|---|
| **Suggest (read-only)** | suggest | Read-only tools, including reading real data through MCP. **No file writes**. Each iteration gives 2 to 3 concrete suggested actions. The safest, and the default. |
| **Auto (safe)** | auto (safe) | Reads MCP and **can write files** in the brain (creating or editing draft notes). Still hard-blocked from money, orders, ads, publishing and messaging. Adds a self-verification step after each iteration. |
| **⚠ Full power** | ⚠ full power | Everything open: every tool and every MCP, **real outside actions** without asking. |

Choosing **⚠ Full power** shows a red warning block in the form, opening with: "**⚠ FULL POWER MODE, high risk.** The loop will take REAL actions through MCP without asking: it may **create or edit orders, run ads (spending real money), send messages and email, publish posts**."

Read that carefully: a full-power loop runs in the background on a schedule, **with nobody approving each step**, and **real actions cannot be undone**. Javis asks for confirmation twice (once on save, once when you click **Enable**) for exactly that reason. If you need this mode, run it in **Suggest (read-only)** for a few iterations first, read the log to see what it intends to do, and write the task description with a genuinely narrow scope.

## What the "When" field understands

It accepts four shapes, with the placeholder showing `in 30 minutes · 8:30 · 0 7 * * * · 2026-07-20 09:00`:

| You type | Javis reads it as |
|---|---|
| `in 30 minutes`, `in 2 hours`, `1.5 hours`, `3 days` | A countdown from now. Units accepted: minutes, hours, days. |
| `8h30`, `8:30`, `8h` | A time of day. If it already passed, it moves to **tomorrow**. |
| `2026-07-20 09:00` | A specific date and time. |
| `0 7 * * *` | A 5-field cron expression (minute, hour, day, month, weekday). This is a **repeating schedule**: it runs at that time and computes the next one. `0 7 * * *` = 7am every day. The macros `@daily`, `@hourly`, `@weekly`, `@monthly` are accepted too. |

All times use Vietnam time (UTC+7). The first three forms are **one-shot** (once run, they leave the pending list); cron repeats until you cancel. A one-shot cannot be more than about a year out.

## The job list

### Grouped by brain

Each brain gets a block headed `🧠 <brain name>`, with a small **viewing** label on the brain selected in your sidebar and **default** on the default brain. The brain you are viewing is pushed to the top. Brains with no jobs that you are not viewing are hidden to keep things tidy.

Inside each block, loops are listed first, then a **Pending reminders** section.

If the brain you are viewing has no jobs, it reads "No jobs in this brain yet. Click **+ Add job**, or tell Javis in chat." With nothing anywhere, it reads "No recurring jobs or reminders yet."

### The search box

The **🔍 Find a job by name...** box above the list filters cards as you type, **ignoring Vietnamese accents**, so typing "kho" still matches "khô" and "email" still matches "Email". Brain groups with no matching cards hide themselves. With no matches at all it reads "No job matches."

### Reading a loop card

The card starts with `🔁 <job name>` and its slug (the file name) dimmed beside it, with a status in the top right:

| Status | Meaning |
|---|---|
| ⏳ running | This job's iteration is running right now |
| ⚠ auto-paused | It failed 3 times in a row so Javis locked it, see "Auto-pause" |
| ● on | Enabled, running on its cycle |
| ○ off | Disabled, not running (the card is dimmed) |

The second line shows the mode and cycle, for example `auto (safe) · every 120 minutes`, plus advanced information where present: the legacy task type (when it is not "Custom"), `quiet 23-07`, `max 3/day (1 used)`, `⚙ code · <folder>`.

The third line is a short history: `last HH:MM` (or `never run`), the latest verification result (` · ok` when clean, or `· ✓ Pass: ...` / `· ✗ Fail: ...`), and `· next ~HH:MM` when enabled. An auto-paused job adds a `⚠` line with the reason and the time.

### Reading a reminder card

Reminder cards are more compact: the name (or the content if unnamed), then a secondary line with the time and the type. The type is `remind` (remind only), `do + report`, or `script`. `do + report` also shows a permission label (`read only`, `may write files`, or `full power` in red).

The time always states **when it will run**, so you never have to read cron yourself:

- One-shot: `once, next tomorrow 08:30 (in 14 hours)`.
- Cron schedule: the schedule in words, then the next run, for example `7:00 every day · next tomorrow 07:00 (in 14 hours)`. The raw expression is still printed alongside as `0 7 * * *` for anyone who wants to check.
- Interval repeats: `repeats every 60 minutes · next today 15:20 (in 12 minutes)`.

Times today read `today HH:MM`, tomorrow reads `tomorrow HH:MM`, and further out reads `HH:MM DD/MM`.

If the previous run failed (for example the message could not be sent), the card adds a `⚠ previous run failed: ...` line so you can act on it instead of it failing silently forever.

### The buttons on a card

Every button targets that card's own brain, not the brain selected in the sidebar.

On a loop card:

- **Enable** / **Disable**: flip the state. Enabling an **⚠ Full power** job asks for confirmation. Enabling also clears an auto-pause.
- **▶ Run now**: run one iteration immediately, without waiting for the cycle. The button reads "Running..." and the list reloads after about 2.5 seconds. Note: this button does **not** save an open form; it runs what is saved in the file. Running now also clears an auto-pause, because it is a deliberate action on your part.
- **Edit**: reopen the form with this job's content.
- **Delete**: asks to confirm, then removes `Javis/loops/<slug>.md` entirely.
- **Move to brain…**: a picker to move the job to another brain, keeping its file and run state. If the target brain already has a job with the same name, Javis refuses and reports the error rather than overwriting. A running job cannot be moved; try again later.

On a reminder card:

- **Edit**: reopen the form with this reminder's content. You can change the name, content, type and time. For a cron schedule, the "When" field is prefilled with the old expression, and saving recomputes the next run immediately. For a one-shot, the field is empty with the current time shown in the placeholder: **empty means keep the existing time**, so only type when you want to change it.
- **Cancel**: stop it running while keeping the record in history.
- **Delete**: remove it entirely, with no undo.
- **Move to brain…**: move it to another brain, keeping its id and every setting.

## Without Telegram connected, Javis will not create a schedule

Reminders and "do it and report" jobs are only worth anything if, when the time comes, they can **tell someone**, and the only reporting channel today is Telegram. If the Telegram bot is off, has no token, or has no allowed Chat ID, Javis **refuses to create** the job and says exactly what is missing, with a link to the [Channels](11-telegram.md) page to connect it.

This used to be the biggest source of confusion: Javis would build a "report email and calendar every morning" job, the job would run on time, and the result reached nobody, with nothing telling you Telegram was missing.

If you still want to create it (planning to connect Telegram later), click **Create anyway** next to the warning. The job runs on time and its result is stored in Javis, it simply goes nowhere.

When the Recurring jobs page detects that no reporting channel exists, it shows a warning strip at the top, because jobs created earlier are still running and still not reaching you.

Scheduling in words through chat follows the same rule: Javis must check first whether the data sources are connected and whether there is a place to report to, and if something is missing it says so and asks, rather than creating something for the sake of it.

## Run now and stopping the running iteration

The **■ Stop the running iteration** button at the top of the page aborts whatever iteration is **running system-wide**, whichever job it belongs to. Since only one runs at a time, the button needs no job selection. It only cuts the running process and **does not disable the job**: on the next cycle it runs again. To stop it for good, click **Disable** on the card.

This button does not touch a running "🤖 Do it and report" reminder.

While an iteration is running, the page refreshes the list every 5 seconds so you see the state change.

## The self-verification step

In **Auto (safe)** and **⚠ Full power** modes, after the work is done Javis runs an independent check: a reviewer assumes the result is WRONG, then rereads the relevant files to compare. This verification pass is **always read-only**, even for full-power jobs.

The step is skipped if the iteration failed, or if the result says there was no new work.

The criteria vary by job type:

- Ordinary jobs: does the result match the goal, is it sensible and feasible, did it invent anything or damage a file.
- Jobs touching business data: are the suggestions grounded in real numbers, are they feasible and specific enough, were any figures invented.
- Jobs thickening the Wiki: do they follow the Wiki conventions, is anything invented or missing citations, were any links broken.
- Jobs using the `code` tool profile (settable only in the `.md` file): `python -m py_compile` or `node --check` must be run for every edited file and all must be clean, and the diff must be small (under about 80 lines).

In **Suggest** and **Auto (safe)** modes there is one more hard criterion: detecting any money, order, ad, publishing or messaging action through MCP is an **immediate fail**. In **⚠ Full power**, real actions are permitted, so the criterion becomes: fail only when it did the wrong thing or went beyond the task's scope, caused clear harm, or touched something you did not intend.

The result appears as **✓ Pass** or **✗ Fail** with a short reason, both on the card and in the log.

## Auto-pause after 3 failures

If a loop fails **3 times in a row** (engine errors, or ✗ Fail verifications), Javis locks it and records the reason, for example "Auto-paused 20/07 14:35: 3 consecutive failures or failed verifications". The card switches to **⚠ auto-paused** and stops running until you intervene.

That reason is written to runtime state and does **not** modify your `.md` file. To resume, click **Enable** or **▶ Run now** on the card; both clear the lock and reset the failure streak. Before resuming, read the log to see what broke.

## Reporting to Telegram

This is Javis's default behaviour: **every finished iteration sends its result to Telegram**, to whoever asked for that job. The message starts with `✅ Loop '<job name>' just ran...` (or `⚠` on failure), then the summary and the verification line.

Who receives it:

- Jobs created through chat carry the speaker's chat_id, so they report back to that person.
- Jobs created on the dashboard do not know who you are, so they report to the **first Telegram ID** in the allow list.

To stop one job reporting every iteration because it is too noisy, open `Javis/loops/<slug>.md` and set `notify: false` in the frontmatter.

Reminders go through Telegram too. Reminders created on the dashboard have no attached recipient, so they go to **every ID** in the allow list; reminders set in words through chat go to the person who set them.

Both need the bot enabled, see [Telegram channel](11-telegram.md). Without it, jobs still run and still write logs, they simply send no message.

## Recent log

The last block on the page. Next to the title is a picker to filter:

- **Log for the brain you are viewing**: every loop of the brain selected in the sidebar.
- Or one specific job, shown as `<job name> · <brain name>`.

Javis loads the 200 most recent entries and paginates **10 per page**, with **← Previous** and **Next →** buttons and a counter reading "Page 1/5 · 47 entries". With nothing yet it reads "No log entries."

Each entry starts with a heading such as `## [2026-07-20 14:35] doc-source · loop (custom/auto) - scheduled`, where `scheduled` means it ran on schedule and `manual` means you clicked **▶ Run now**. Below is the summary of what it did, a **Verification** line where present, and a warning line if that iteration is what auto-paused the job.

The log also exists in the brain as real files: `Javis/loop-log/YYYY-MM-DD.md`, one per day. Open them through [File manager](05-file-manager.md) to look further back than 200 entries.

## Scheduling in words through chat

You do not have to use this page. Tell Javis directly in [Chat](02-chat-and-voice.md) or over Telegram, for example:

- "Create a job that scans new orders every 2 hours and summarises them."
- "Remind me every day at 7am to check yesterday's revenue."
- "Remind me in 30 minutes to call the customer."
- "Is anything still running?"
- "Cancel the order scanning job."

Javis uses the `javis_schedule` tool (a bundled plugin) to pick the right store: interval schedules become files in `Javis/loops/`; fixed repeating times and one-shots go into the reminder store. The tool sets a proper slug and **blocks duplicate names**: if a job with that name exists, it reports an error and tells you to edit the old one rather than spawning a copy.

Two hard safety rails on this path, which no parameter can change:

- A loop created through chat is **always** `enabled: false` and `mode: suggest`. You must open the Recurring jobs page and click **Enable** for it to run for real.
- If the cycle is unclear (you said "every morning" without a time), the tool reports an error and asks back, never guessing.

## Advanced fields (editable only in the .md file)

The dashboard form is deliberately compact. The following require opening `Javis/loops/<slug>.md` and editing the frontmatter (through [File manager](05-file-manager.md) or Obsidian). Once saved, the dashboard rereads it immediately, with no restart.

| Field | Meaning |
|---|---|
| `quiet_hours` | Quiet hours, in the form `23-07` (no runs from 23:00 to 07:00, Vietnam time). Whole hours only. |
| `max_runs_per_day` | Daily iteration cap. `0` = unlimited. The card shows `max N/day (M used)`. |
| `workspace` | `vault` (default, runs in the brain) or an absolute folder path. A folder that does not exist makes the iteration fail immediately. |
| `tools_profile` | `vault-safe` (default) or `code`. The `code` profile opens Bash, WebFetch and WebSearch and works inside `workspace`, but **disables every MCP**. This is the profile for a loop that edits source code in a folder you assign, and it really does edit files there, so consider it carefully. |
| `ambient_mcp` | Off by default. Set `true` to let the loop see connectors installed on the machine (Gmail, Drive, calendar via claude.ai). Even when on, Bash, WebFetch and WebSearch stay hard-blocked. |
| `owner_chat` | The Telegram chat_id that receives reports. Empty means the first ID in the allow list. |
| `notify` | `false` to turn off per-iteration reporting for this job only. |
| `goal` | The task type. The default, and what the dashboard always creates, is `custom`, meaning each iteration does exactly what the file body says. The legacy values `business`, `brain`, `product` still work for hand-written files, and anything other than `custom` adds a secondary label to the card. |

The **file body** (below the second `---`) is exactly the "Task description" you type in the form.

## Quick reference: buttons and states

| What you see | Meaning / action |
|---|---|
| **+ Add job** | Open the create form |
| **■ Stop the running iteration** | Abort the system-wide running iteration, without disabling the job |
| **🔁 Loop** / **⏰ Reminder** | Pick the job kind (locked while editing) |
| **Suggest (read-only)** | Read only, no file writes. The default |
| **Auto (safe)** | Writes draft files in the brain, no money/orders/publishing |
| **⚠ Full power** | Real outside actions. Confirmed twice |
| **⏰ Remind only** | Sends "⏰ Reminder: ..." at the time |
| **🤖 Do it and report** | Runs the engine at the time and reports the result |
| **What it may do** | The permission level for Do it and report: Read only / Write files / Full power (default) |
| **💾 Save** / **Cancel** | Save or close the form |
| The **🔍 Find a job by name...** box | Filter cards by name, ignoring accents |
| **Enable** / **Disable** | Flip a loop's background running state |
| **▶ Run now** | Run one iteration immediately, clearing an auto-pause |
| **Edit** / **Delete** | Edit or permanently remove the loop file |
| **Move to brain…** | Move the job to another brain |
| **Edit** (on a reminder card) | Change the name, content, type, time or cron expression |
| **Cancel** (on a reminder card) | Stop it running while keeping it in history |
| **Delete** (on a reminder card) | Remove the record entirely, no undo |
| **Create anyway** | Create the schedule even with no reporting channel connected |
| ⏳ running | This job's iteration is running |
| ⚠ auto-paused | 3 consecutive failures, locked automatically |
| ● on / ○ off | Whether it runs on its cycle |
| ✓ Pass / ✗ Fail | The self-verification result |
| **← Previous** / **Next →** | Page through the log, 10 per page |

## Tips

- **Start in Suggest (read-only).** Let it run a few iterations, read the log to judge the quality of its suggestions, and only then move up to **Auto (safe)**.
- **Do not set the cycle too tight.** One iteration every 5 to 10 minutes burns tokens and real machine resources. Most needs are fine with a few hours. Watch the spend in [Usage: tokens & cost](23-usage-and-cost.md).
- **Use a cheap model for background work.** The [Models & engines](10-models-and-engines.md) page has a "Background model" block that applies to loops, Kanban work, reminders and self-learning. Picking a cheap model there saves a lot.
- **Set `quiet_hours` for jobs that run at night.** With Telegram reporting on, a job running at 3am wakes you. Add `quiet_hours: 23-07` to the file, or set `notify: false`.
- **One job, one task.** A description that crams several jobs together makes each iteration do a fragment of each. Splitting them into separate loops, each with its own cycle, also makes the log far easier to read.
- **Do not call a model for work that needs no thinking.** An "⏰ Remind only" reminder costs no tokens at all.

## Common problems

**You created a job and it never runs.** Loops created from the dashboard (and from chat) are **off** by default. Check whether the card is **● on**; if it is **○ off**, click **Enable**.

**Clicking ▶ Run now does nothing visible.** Three possibilities. One, another iteration is running somewhere (only one runs system-wide) so the request was skipped silently; wait a moment and click again. Two, the iteration takes time; wait, reload the page and check **Recent log**. Three, the engine is not ready, see below.

**The card shows ⚠ auto-paused.** That job failed 3 times in a row. Open the log, filter to that job and read the reason. Clarify the task description, then click **Enable** or **▶ Run now** to unlock it.

**Verification keeps reporting ✗ Fail.** The self-check finds the result unsatisfactory (invented figures, wrong Wiki conventions, work beyond scope). Read the reason in the log and open the relevant files through [File manager](05-file-manager.md) to check. Usually the task description is too vague, so each iteration interprets it differently.

**The result says the Claude CLI is not installed.** The brain is not ready on the machine. See [Getting started & first-run setup](01-getting-started.md) and [Troubleshooting & FAQ](17-troubleshooting.md).

**Running on ChatGPT reports `bwrap: Failed to make / slave: Permission denied`.** Codex (ChatGPT) wraps all of its file reads and writes in bubblewrap, and bubblewrap cannot start inside a Docker container, so the background job cannot read a single file. The Docker image since version 0.25.9 already disables that particular sandbox (`JAVIS_CODEX_SANDBOX=off`), so **updating to a newer build** is enough. If you build your own container, set that environment variable, or move background work to the Claude brain. Details in [.env configuration](16-env-configuration.md).

**A loop complains that there is no business data.** It can only read real numbers once you connect a source. Go to [Connections & business data](09-connections-and-business-data.md) to connect a POS, ads account or sales channel. With no source, the iteration stops and says so in one line.

**The job list will not load.** The page shows "Could not load the job list (slow network or timeout)" with a **Retry** link. On a weak VPS or a very large brain, the first load can take too long; Javis already retried once before reporting. Click **Retry**.

**You created a job over Telegram and cannot see it on the dashboard.** It landed in another brain. This page aggregates every brain, so scroll to the other `🧠` blocks, or type the job name into the search box. To move it where it belongs, use **Move to brain…** on the card.

**No Telegram messages arrive.** Check that the bot is enabled and the Chat ID is in the allow list, see [Telegram channel](11-telegram.md). Also check whether the job file has `notify: false`.

**You edited the .md file and the loop vanished from the list.** The file has broken frontmatter (a missing `---` pair, or invalid YAML), so Javis skips it. Reopen the file, compare it with another working loop file, and fix the shape.

## Related

- [Work / Kanban](21-kanban-work.md) - the AI-dispatched queue of one-off jobs, different from the loops on this page.
- [Self-learning](22-self-learning.md) - the dedicated background work for memory and the Wiki, with the Curator and Wiki LINT.
- [Telegram channel](11-telegram.md) - enabling the bot to receive per-iteration reports and reminders.
- [Connections & business data](09-connections-and-business-data.md) - connecting sources so background work can read real numbers.
- [Models & engines](10-models-and-engines.md) - picking a cheap model for background work.
- [File manager](05-file-manager.md) - opening job definition files and log files.
- [Chat & voice](02-chat-and-voice.md) - creating jobs and reminders in words.
- [Plugins](20-plugins.md) - understanding `javis_schedule` and the other bundled tools.
