# Work (Kanban): handing a goal to the AI to run in the background

*[Tiếng Việt](../21-viec-kanban.md) · **English***

The **Work** page is where you hand over a goal and let Javis do it in the background, without sitting and watching the chat box. You write one sentence describing what needs finishing, the AI normalises it into a specification, picks the worker type, claims the job and runs it; when it is done, the result is sent to whoever handed it over.

The easiest thing to misunderstand: this is **not a drag-and-drop Trello board**. You do not drag cards and you do not run each card by hand. This screen is for **watching the queue and handling exceptions**, while the dispatcher does the running.

## What this feature is

Javis treats the work queue as a runtime for the AI. A job goes through this lifecycle:

1. **You hand over a goal** (from the Work page, by saying it in chat, or proposed by the Self-learning page).
2. **The AI specifies it (triage)**: a short run of the background model reads the raw goal and returns JSON with a clear intent, a **capability** (`files`, `research`, `mcp-read`, `code`, `external-write`), an **execution_mode** (`suggest`, `auto`, `full`) and a list of **completion conditions**. This step executes nothing.
3. **Into the queue**: the task moves to a ready state, waiting its turn.
4. **The dispatcher claims the task**: each task is held by exactly one worker (locked with an SQLite transaction), with a 90-second lease and a heartbeat every 20 seconds.
5. **The worker runs**: a headless AI process works inside the brain, verifies its own result then reports briefly.
6. **The end**: completed, or stopped waiting for you (missing information, missing permission, or because you ticked "Require result approval").

Workers share the **background engine** with the other background features, so Claude Code, ChatGPT/Codex and the API providers (OpenRouter, OpenAI, Anthropic, Google Gemini) can all run this queue. See [Models and engines](10-models-and-engines.md).

Do not confuse three similarly named things:

| Thing | What it is | Where to read |
| --- | --- | --- |
| **Work** (this page) | The queue of ONE-OFF jobs the AI runs in the background | this page |
| **Recurring jobs** | Loops on a cycle and reminders at a fixed time | [Recurring jobs and reminders](08-recurring-jobs.md) |
| `- [ ]` checkboxes in notes | Tasks you tick yourself in a markdown file | [Tasks and Dataview in notes](19-tasks-and-dataview.md) |

## Where to open it in Javis

On the left navigation rail, open the **Work** group then click **Work**. The page title is **Work (Kanban)** with the subtitle "The AI specifies, dispatches and runs background tasks".

The board is bound to the **brain selected** at the top of the dashboard. Switching brains switches the board, one queue per brain.

Right under the title is a dot and a line about the dispatcher:

- "Dispatcher running · up to 2 workers" (a bright dot): the server's dispatch process is alive.
- "Dispatcher not running" (a dark dot): the dispatch process has not come up.

An important note: that line only says whether the process is alive, **not** whether this brain's board runs automatically. What decides that is the **Dispatcher mode** just below.

## How to use it (step by step)

### Step 1: Choose the dispatcher mode

The **Dispatcher mode** block has 3 buttons:

| Button | What it actually means |
| --- | --- |
| **Off** | The default for a new board. The AI claims nothing. |
| **Observe** | The AI also claims nothing. Use it when you want to line jobs up first then run them yourself. |
| **AI runs itself** | The dispatcher scans the queue and runs work on its own. |

Only **AI runs itself** makes work run automatically. The other two leave the dispatcher idle for this brain, and the difference lies in the **Pause AI** button: that button sets the mode to **Off** AND cancels every running worker of the current brain.

A mode change takes effect immediately, with no restart.

### Step 2: Hand over a goal

Click **+ Hand over a goal** in the right corner to open the form (click again to close). The form has:

- **Goal**: a short sentence stating what needs finishing. The placeholder suggests: "Analyse this week's best sellers and draft 3 posts". Left empty, Javis reports "Enter a title".
- **Context and desired output**: a multi-line field, natural writing is fine. This is where you state the output you want (which file, where, how long, which source for the figures). Left empty, Javis reuses the Goal field.
- **Route**: choose **Let the AI pick the worker** (the default) to let the AI decide, or pick a **Workflow: `<name>`** entry to force the job through that workflow. The workflow list comes from the selected brain, see [Agents and Workflows](07-agents-and-workflows.md).
- **Priority**: **🔺 High**, **🔼 Medium** (the default), **🔽 Low**. High-priority work is claimed first when the queue is busy.
- **Exception**: the **Require result approval** checkbox. Ticked, a finished job does not close itself but stops at "Needs exception approval" waiting for you to look.

Click **Hand to the AI** to create it, or **Cancel** to close the form.

A small note on duplicate protection: if the board still has an unfinished job with the same title (matched after stripping diacritics and special characters), Javis returns that existing job rather than creating a copy.

### Step 3: Read the board

The KPI row has 4 numbers:

| KPI | What it counts |
| --- | --- |
| **Workers running** | How many workers are genuinely running for this brain |
| **Waiting** | Total work awaiting specification, awaiting dependencies and awaiting its turn |
| **Needs you** | Blocked work plus work awaiting your approval |
| **Completed in 24h** | Work that moved to completed in the last 24 hours |

Below are 4 panels:

- **Active** (sub-label "N workers"): work running right now.
- **AI queue** (sub-label "N tasks"): work awaiting specification, dependencies or its turn.
- **Needs you** (sub-label "N exceptions"): blocked work and work awaiting approval. When empty it reads "No exceptions. The AI is running normally."
- **Recent history** (sub-label "24 hours and latest"): completed and cancelled work, at most 20 cards.

An empty panel reads "No tasks yet."

Each work card carries: the priority icon and title, a status pill in the right corner, an information line (capability, "attempt 1/3", the last change time as "just now" / "12 minutes" / "3 hours"), then the block reason (in orange) or the first 240 characters of the result, and finally a row of action buttons.

The board refreshes itself every 3 seconds, so you never need to click anything to see progress.

### Step 4: Open one job's detail

Click a card's body to open the detail drawer sliding in from the edge of the screen. It contains:

- The full intent content (the version the AI specified, not your original raw sentence).
- An information line: status, capability, "mode `<suggest|auto|full>`", "priority `<1|2|3>`".
- The same action buttons as on the card.
- **The block reason** (if any).
- **The full result** (if any).
- **Runs (N)**: each time a worker held the job, with the run's status and start time, and any error shown.
- **The lifecycle log**: every event of the job, for example `created`, `claimed`, `specified`, `retry_scheduled`, `blocked`, `completed`, `operator_move`, `auto_archive`.

Close the drawer with the **×** in the top corner, the **Esc** key, or by clicking the dark backdrop.

### Step 5: Handle exceptions

Depending on the status, the card (and the detail drawer) shows these buttons:

| Button | Shown when | What it does |
| --- | --- | --- |
| **✓ Approve exception** | the job awaits approval | Marks it completed |
| **↻ Retry** | the job is blocked or awaiting approval | Pushes it back into the queue to run again |
| **Stop task** | the job is running | Cancels the running worker |
| **Remove from board** | any job not running | Archives it, leaving the board without losing the history |

**Remove from board** asks for confirmation first, explaining the task will be archived so no history is lost. A running job must be stopped with **Stop task** before it can be removed. If an action fails, Javis shows the server's error verbatim, or "Could not update the task".

## A job's states

This table translates in full the words shown on the status pill.

| Words on screen | Internal state | Meaning |
| --- | --- | --- |
| **AI is specifying** | `triage` | A new job waiting for (or currently being) normalised into a runnable specification |
| **Waiting on dependencies** | `todo` | The job has dependencies and must wait for its parent jobs |
| **In the queue** | `ready` | Specified, waiting its turn to be claimed by a worker |
| **Running** | `running` | A worker holds it and is executing |
| **Needs exception approval** | `review` | Finished, but you asked to approve the result |
| **Needs attention** | `blocked` | Blocked: missing information, missing permission, or an error that exhausted the retries |
| **Completed** | `done` | Finished |
| **Cancelled** | `cancelled` | You stopped it, or the worker was cancelled midway |
| (not shown on the board) | `archived` | Archived: either you clicked Remove from board, or it was auto-cleared 3 days after finishing |

A few paths worth knowing:

- After the specification step, the job is **not** counted as having used an attempt; the count is restored so execution gets a full 3 attempts.
- A transient error (timeout, rate limit, 429, network loss, a busy engine) sends the job **back** to the queue by itself, up to 3 times, logging `retry_scheduled`. Only when the attempts run out does it move to "Needs attention".
- A worker that dies without sending a heartbeat has its job reclaimed into the queue with a `reclaimed` event, so nothing hangs forever at "Running".
- A worker that finds it is missing a decision or data returns a result starting with `[[NEEDS_INPUT]]`, moving the job to "Needs attention" with exactly one line of reason.

## Quick reference of buttons and states

| Button at the top of the page | What it does |
| --- | --- |
| **+ Hand over a goal** | Opens/closes the hand-over form |
| **Run a tick now** | Forces the dispatcher to claim and run one ready job of this brain immediately. It works even in Off or Observe mode. With no ready job, nothing happens |
| **↻** | Reloads the board at once, without waiting for the 3-second tick |
| **Pause AI** | Sets the mode to **Off** and cancels every running worker of this brain |

## What a background worker can and cannot do

A worker is a **headless** AI session: no screen, no asking you mid-run, no signed-in browser, no hands of yours to click a button. It only has the toolkit matching the capability the specification step chose:

| Capability | Allowed | Blocked |
| --- | --- | --- |
| `files` | Reading, writing and organising files in the brain | Bash, web search |
| `research` | The file tools plus reading the web and web search | Bash |
| `mcp-read` | The file tools plus reading real data through MCP connections | Bash, web search |
| `code` | The file tools plus Bash (editing and testing code) | Reading the web, web search |
| `external-write` | The file tools plus MCP, but see the rule right below | Bash, web search |

The most important rule: an `external-write` job (sending a message, publishing, creating an order, booking a calendar slot, changing anything outside) **only runs when the execution_mode is `full`**. Without that level, the job is blocked immediately with the reason that the task needs an outside action and only a mode=full worker may execute it. The specification step does not hand out `full` either: it only keeps `full` when your own wording in the goal clearly grants permission to act (phrases like "full power", "send it yourself", "publish it yourself", "no need to ask"). With no such permission it drops to `auto` so the kernel blocks it.

In other words: by default Javis does **not** spend money, send messages or publish from the work queue. To let it, you have to say so plainly in the goal.

Beyond that, a worker also cannot see source repositories outside the brain, and cannot do anything requiring the owner to sign in (cookies, OTP, scanning a QR code, changing a password).

## Getting results: back to where you handed the job over

Every job that ends completed, awaiting approval or blocked **sends a notice by itself** to the channel it came from, briefly:

- `✅ The job '<title>' completed.` with the first few lines of the result.
- `✅ The job '<title>' is done and needs exception approval.`
- `⚠ The job '<title>' is blocked and needs your attention.` with a `Reason: ...` line.

Every notice ends with a pointer to the Work page, because the full detail lives here rather than being crammed into a message.

Who receives it and where:

- **Handed over in the dashboard chat** → the result appears as a Javis message **in that very conversation**. The server writes it into the session history before pushing it, so closing the tab or refreshing and coming back still shows it. If you are viewing another conversation, the message sits in the original session and that session rises in the **History** list.
- **Handed over from a Telegram chat** → reported to the person who wrote (the job carries their chat id).
- **No clear owner** (created by hand outside chat) → reported to the **first Telegram ID** in the whitelist; with the bot off, that step is skipped and the job still runs normally. See [The Telegram channel](11-telegram.md).

> Before 0.9.289 only the Telegram route existed. Anyone handing over work on the web without Telegram attached got absolute silence afterwards: no status, no reply. Now web chat is a genuine reporting channel and Telegram is no longer required.

### Which jobs ring the bell (since 0.52.7)

The **Notifications** bell in the top bar only shows a red dot (and only sends a push notification outside the browser) for work that **needs your hands**:

| The job ends as | Result in the chat box | Into the inbox | Red dot + push |
|---|---|---|---|
| Blocked | yes | yes | **yes** |
| Awaiting exception approval | yes | yes | **yes** |
| Finished cleanly | yes | yes | no |

A cleanly finished job still sits in the bell list for you to review, it just does not wake you: the result already landed in the very chat box that handed it over. This changed because the repo owner reported (2026-09-01) that the bell rang constantly mid-conversation.

The trade-off to know: while you are away, a finished job has **nothing** reminding you. To see it, open the bell, or reopen the conversation that handed the work over.

## Seeing background work right in the chat box

Since 0.25.2, right above the chat input there is a **background work strip**. It only appears when something is genuinely alive, and it says exactly one thing: is anything running for you right now.

| Colour | Meaning |
|---|---|
| **Green** | Something is **genuinely running**. The dot blinks. |
| **Yellow** | Work was **handed over but does not run** because the dispatcher mode is not **AI runs itself**. The strip says where to turn it on. |
| **Grey** | Only loops or reminders waiting for their time. |

The strip gathers all three sources: Kanban work, [loops and reminders](08-recurring-jobs.md). Work handed over from the open conversation gets its own outline and its own count ("2 jobs running in the background · 1 from this conversation"), because "the machine is busy" and "my job is running" are two different things. Click **Work page** in the right corner to open the full board.

The strip re-asks the server every few seconds, and asks immediately whenever a chat turn ends or a background job reports back. With no work at all it hides entirely rather than taking space from the chat box.

> Why it exists: before this version the chat box said nothing whatsoever about background work, so "Javis is running my job" and "Javis forgot" looked identical. Finding out meant thinking to open this page yourself, and nobody has a reason to think of that.

## Javis corrects itself when it promises emptily

Also since 0.25.2, at the end of each chat turn the server detects whether the answer promised to report back ("I will tell you as soon as I have results", "I will let you know when it is done", "give me a moment"), then compares that against the background work that actually exists. A promise with nothing running makes Javis append a correction line right under the answer, stating plainly that no report will arrive on its own and what you need to do next.

This is not censorship: it neither blocks nor edits the answer, it only adds the truth underneath. The reason is that an answer turn ends the moment Javis stops speaking, with no mechanism to wake it up to finish, so a promise without background work is a promise that will never arrive.

## Handing work over in words in chat

You are not required to open this page. Saying it plainly in chat, something like "background job: review every Wiki note from this month then list the ones missing links", makes Javis create a job in the queue and attach the identity of whoever is speaking so the result comes back to the right place.

Javis is taught to pick the smallest tool that suffices, so it only creates a job when the job is **one-off and needs to run in the background or needs review**. A question it can answer now gets answered; work that repeats on a cycle or has a fixed time goes to [Recurring jobs and reminders](08-recurring-jobs.md).

Remember that work created through chat still sits in the queue of the brain you are chatting with, and still needs the **AI runs itself** mode to run on its own. If the board is **Off**, the job simply waits until you turn it on or click **Run a tick now**.

Since 0.25.2 Javis **says so at hand-over time**: handing work into a board that is **Off** or in **Observe** makes it report that the job is queued rather than running, plus how to turn it on. Before that it always ended with "the job runs in the background, the result will come back on its own" regardless of the mode, a false promise Javis itself had no way to know was false. The background work strip in the chat box also turns yellow in exactly this situation.

This works on **every brain** since 0.17.1, through the `javis_task` tool. Before that only Claude Code and ChatGPT/Codex could hand work over from chat, because the only route was an HTTP call through a machine command that only those two engines could run. The API engines (OpenRouter, OpenAI, Anthropic, Gemini, Groq, Ollama) accepted the instruction then did nothing, and reported no error. If you ever met "I asked for a job and the board stayed empty", it was most likely this bug.

Two things that tool deliberately does **not** do:

- **It cannot create `full`-level work.** The full level lets a job really act outside (creating orders, spending money, running ads, sending messages) and cannot be undone. Javis only creates `suggest` or `auto`; to get full you raise it yourself on this page, where you can see clearly what you are permitting.
- **It does not move columns, cancel work or approve work awaiting approval.** Those actions need you to see the board, so they stay on this page.

## Work proposed by the Self-learning page

The **Self-learning** page has a capability switch named **Work (Kanban)** letting the learning engine propose background jobs from conversations. That switch is **off by default** in the current build, after inspecting a real board and finding that most machine-generated jobs were things a headless worker cannot do (needing cookies, needing to send something outside, only waiting for someone else's approval, touching a repo outside the brain). Work is now only created when you say so directly.

If you turn it back on, these rails still hold:

- At most 3 jobs per learning pass, and only proposals with high enough confidence.
- Proposals containing a secret or a prompt-injection sentence are blocked outright.
- An "impossible job" gate filters out work needing a sign-in, OTP or QR, work sending or publishing outside, work that only waits for someone else's reply, and work touching source code outside the brain. The rejection reason is written into the learning log.
- Work created by Self-learning enters the specification layer exactly like work you hand over, and is **not** forced to await approval: only missing information, missing permission or your own approval flag brings you in.

Details in [Self-learning](22-self-learning.md).

## Where the board's data lives

- **The main source**: the `kanban.sqlite3` file in Javis's state folder (the `JAVIS_STATE_DIR` variable, defaulting to the `server/` folder). It holds the lifecycle, the runs and the event log. It sits deliberately outside the brain so running work is not overwritten by git sync.
- **A readable copy**: `Javis/kanban.json` in the brain, rewritten every time the board changes. That file exists for backup and so older Javis builds can read it; editing it by hand changes nothing in the real queue.
- An old board from earlier Javis versions is imported exactly once, and work stuck "running" under the old process is returned to the queue.
- Work completed or cancelled over **3 days** ago is archived automatically so the board does not bloat.

## Technical limits

| Parameter | Value |
| --- | --- |
| Workers running in parallel | 2 (change it with the `JAVIS_KANBAN_MAX_WORKERS` environment variable, clamped between 1 and 8, counted across all brains) |
| The dispatcher's scan interval | 5 seconds, and woken immediately when new work arrives |
| Task lease / heartbeat | 90 seconds / 20 seconds |
| Time ceiling for the specification step | 3 minutes |
| Time ceiling for one worker run | 15 minutes |
| Maximum retries | 3 |
| Length of result kept | 20,000 characters |
| Screen refresh interval | 3 seconds |

## Calling the API directly

The web page does not cover everything the server can do. The endpoints below are real, for automation or bulk board cleanup (every parameter is form-encoded, with `brain=<brain name>`):

| Endpoint | What it does |
| --- | --- |
| `GET /kanban` | The whole board's data |
| `GET /kanban/health` | The mode, the dispatcher's health, counts by state |
| `GET /kanban/task/show?id=...` | One job with its runs and event log |
| `POST /kanban/task` | Creates a job. Besides the form fields it also accepts `chat_id`, `capability`, `execution_mode`, `deps` (a comma-separated id list) and `idempotency_key` |
| `POST /kanban/run` | Runs exactly one job by id |
| `POST /kanban/task/move` | Moves a job to another state |
| `POST /kanban/purge` | Permanently deletes finished work. By default it only touches archived and cancelled work; add `include_done=1` to touch completed work |
| `POST /kanban/clear` | Wipes the board except running work. Cannot be undone |

The two cleanup endpoints at the end have no button in the interface, exactly as designed: they really delete.

## Tips

- Write goals as "what the output is", not "think about". The more the **Context and desired output** field states the destination file, the length and the data source, the closer the specification step's completion conditions are, and the less the worker wanders.
- Tick **Require result approval** on important work. You spend one extra click but are guaranteed to read the result before it counts as done.
- To try one job now without turning automatic running on: leave the mode at **Observe**, hand over the job, then click **Run a tick now**.
- Work needing real data (revenue, calendar, ads) should name the source in the goal, for example "take it from the POS". The specification step then picks `mcp-read` and only then is the worker given the connections. See [Connections and business data](09-connections-and-business-data.md).
- With a board full of dead experimental jobs, do not delete cards one by one: use **Remove from board** for the few whose history matters and let the rest archive themselves after 3 days.
- Read the **lifecycle log** in the detail drawer before concluding "the AI got it wrong". Very often the answer is there: the job was reclaimed because the lease expired, or downgraded because it belonged to the outside-action group.

## Common problems

**The line at the top says "Dispatcher running" but nothing moves.**
Those are two different things. That line says the server's dispatch process is alive; whether work gets claimed depends on this brain's **Dispatcher mode**. Set it to **AI runs itself**.

**Clicking "Run a tick now" does nothing.**
It means no job is in a ready state: the queue is empty, or work is waiting on dependencies, or 2 workers are already running. Look at the **Waiting** and **Workers running** KPIs to see which case you are in.

**A job sits forever at "AI is specifying".**
The specification step needs a background model run. If the background engine is not ready or is out of quota, the job returns to the queue and retries. Check the [Models and engines](10-models-and-engines.md) page and the [Usage](23-usage-and-cost.md) page. When the background model cannot be reached, Javis still has a fallback branch guessing the capability from keywords so the queue does not stall completely.

**A job is blocked with the reason that the task needs an outside action and only a mode=full worker may execute it.**
This is a safety rail, not a bug. Your job belongs to the group that sends messages, publishes, creates orders or changes something outside. If you genuinely want it done automatically, hand the job over again and state in the goal that you permit acting; if not, let Javis draft it and press send yourself.

**A job is blocked with a reason starting "The worker needs more information".**
The worker found a missing decision where guessing would do harm. Open the detail drawer and read the reason, supply what is missing by handing over a clearer goal, then click **↻ Retry** or delete the old job.

**"Remove from board" or "↻ Retry" cannot be clicked.**
A running job cannot change state. Click **Stop task** first, wait for the card to leave the **Active** panel, then act again.

**A job finished but no report appeared anywhere.**
Work handed over in web chat must carry the chat session id for the result to return to that box. Javis attaches it when you hand over in words in chat; work created by hand on this page or through a curl command has no session id and only goes to Telegram. If the Telegram message is silent: the bot is off, there is no chat id in the whitelist, or the job has no clear owner so the message went to the first Telegram ID rather than the account you had in mind. See [The Telegram channel](11-telegram.md).

**Javis promised "I will wait for the jobs to finish then summarise" and never summarises.**
That is an empty promise and has been banned since 0.9.289: a Javis answer turn ends the moment it stops speaking, with no mechanism to wake it up to summarise. Background work only pushes its **raw** result back into the chat box. For a summary, hand over one more job dedicated to summarising (with `deps` pointing at the earlier jobs), or send another message once the results are in.

**The board is empty although there was work yesterday.**
Three possibilities, in order of likelihood: you are standing in **another brain** (switch brains at the top of the dashboard), the work finished over 3 days ago and was archived, or someone called a cleanup endpoint.

**Background work eats your whole quota.**
Each job is a real AI session. Lower the parallel worker count with `JAVIS_KANBAN_MAX_WORKERS=1`, or set the mode to **Off** when you do not need it. Watch the consumption on the [Usage](23-usage-and-cost.md) page, which separates "Javis running by itself" from "You typing".

## Related

- [Recurring jobs and reminders](08-recurring-jobs.md) - loops on a cycle and reminders at a fixed time.
- [Self-learning](22-self-learning.md) - the learning engine and the work-proposal switch.
- [Agents and Workflows](07-agents-and-workflows.md) - the workflows used in the Route field.
- [Models and engines](10-models-and-engines.md) - which engine runs the workers.
- [The Telegram channel](11-telegram.md) - where work reports arrive.
- [Connections and business data](09-connections-and-business-data.md) - the real data sources for `mcp-read` work.
- [Usage: tokens and cost](23-usage-and-cost.md) - how much background work consumes.
- [Tasks and Dataview in notes](19-tasks-and-dataview.md) - task checkboxes in markdown files, entirely different from this page.
- [.env configuration](16-env-configuration.md) - `JAVIS_STATE_DIR`, `JAVIS_KANBAN_MAX_WORKERS`.
