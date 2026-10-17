# Agents & Workflows

*[Tiếng Việt](../07-agents-va-workflows.md) · **English***

This is where you create specialised AI assistants (Agents) and chain them into automated pipelines (Workflows). For example: a research agent, a writing agent and a reviewing agent, chained into "research > write > verify" that produces a result in one run.

## What this feature is

- **An Agent** is an "AI employee" with a fixed role. Each agent has: a name, a role description, a detailed working instruction (system prompt), a list of skills it may use, a **model to run on**, and its **own memory** that accumulates over time. The model can come from **any provider you connected** on the Models page: Claude (Claude Code), ChatGPT (Codex), Grok Build CLI, Antigravity CLI, OpenRouter, Anthropic API, OpenAI, Google Gemini, Groq. The picker reads straight from your connected providers, so connecting more adds more choices. Every provider can read and write vault files and use MCP; Claude Code and Codex additionally have shell commands and can browse the web. If the chosen provider fails at runtime, Javis falls back to another brain rather than leaving the agent silent. (Ollama cannot run agents yet, so it does not appear here.) An agent's model is REALLY applied when the workflow runs.
  - Safety note: when a workflow runs **automatically in the background** (the Kanban dispatcher, restricted file-tool mode), the agent always uses Claude Code to keep the safe tool restrictions, even if you picked another provider. Your chosen model applies when you send a message on the **Partners** page.
- **A Workflow** is a chain of steps, each handing one task to one agent. The result of a step can flow into the next. You can attach a **verification step**: another agent playing the reviewer, which by default assumes the result is wrong and must be proven otherwise; if it fails, the workflow retries a few times.
- Every agent and workflow is stored as an **.md file in the vault** (the selected brain), so you can read them, edit them by hand, and Javis can create them from chat.

Related: choosing an agent model in [Models & engines](10-models-and-engines.md); creating and enabling skills to assign in [Skills](06-skills.md).

## Where to find it in Javis

Open **Capabilities > Partners** in the dashboard sidebar (port 7777 by default). The page has **Agents | Workflows** tabs. Skills and Plugins remain in Capabilities.

- Left: choose a tab, search or filter by tag (workflows: by group), then select a partner. Recently used agents and workflows appear first.
- Centre: chat with the selected partner.
- Right: agent settings and conversations, or workflow progress and run history.

On narrow screens, use the list and details buttons to open the side drawers. Switching brains switches the lists and conversations.

## Chatting with an agent

1. Choose **Agents**, then select an agent in the left column.
2. Send a message in the centre. Replies use the agent's configured role, instructions and private memory.
3. Edit its name, role, instructions, skills or model on the right and click **Save**.
4. Use the new conversation button to start a separate chat with the same agent. Each agent can have several conversations; reopen recent conversations on the right to continue.

Partner conversations are separate from Javis's main chat history. Returning to a partner resumes its most recent conversation.

### Unread messages and muting

From 0.205.0 the partner list works like a message list:

- A partner with a new message (you wrote, the partner replied, or a background job reported into its chat) **moves to the top**. Javis Core and the **Pinned** ones still come first.
- A partner card shows its **unread count** in the bottom corner, next to the time. Opening that partner's chat clears it, in every open tab.
- Each card's **⋮** button has **Mute notifications**, with **For 1 hour**, **For 4 hours**, **Until 8:00 AM** or **Until turned back on**. A muted card shows a crossed-out bell and a grey unread count. Messages still reach the chat and the bell, just without a sound or a push notification. Press **Unmute notifications** to turn them back on.

## Creating, searching and Javis Store

Choose a tab and use the create agent or workflow button at the bottom of the left column. **Javis Store** opens the matching package catalogue. Agents are sorted by **tags**, workflows by **group** (see below).

Search matches names, slugs, roles, descriptions and tag names, and supports accent-free typing. Search and the tag filter (group filter on the Workflows tab) work together. Unused items follow recently used items, ordered by name.

### Agent tags

Since 0.100.0 an agent can carry **several tags** (for example Marketing, Writing, Engineering); an agent's old group became one tag. Tags only sort and find agents:

- **Add or remove a tag:** the **...** button on an agent, item **Tags**. Click a tag to add or remove just that tag; the **New tag** box creates and adds one. Other tags stay.
- **Filter:** the bar above the list picks **All agents**, **Untagged** or one tag. An agent with several tags shows under each of them but only once in the list.
- **Rename or delete a tag:** the **...** next to the tag in the filter bar. Renaming applies to every agent with that tag; renaming to an existing name merges the two. Deleting only removes the label, never an agent, chat or goal.
- Tags are not in the settings form: saving the form never changes them.

A tag is **not** a chat group: tagging adds the agent to no group chat. It also picks no reviewer, grants nothing and does not turn on Resonance. Workflows keep their **groups**.

## Creating an Agent (step by step, through the form)

1. Open **Partners > Agents**.
2. Click the create agent button at the bottom left. An editor opens on the right of the screen.
3. Fill in:

| Field | Meaning | Suggestion |
|---|---|---|
| **Name** | The agent name shown on the card. Required. | e.g. "Email specialist" |
| **Role (short description)** | One sentence about what the agent does. | e.g. "Writes sales emails in a friendly voice" |
| **System prompt (detailed working instructions)** | The long, detailed instruction: how the agent works, its principles, the output you expect. | e.g. writing rules, banned words, output format |
| **Skills** | The skills available in the vault; tick the ones the agent may use. | Pick skills matching the role |
| **Model** | A picker with 8 options, see the table below. | Sonnet for balance, Opus for deep reasoning, Haiku for fast and cheap |

4. Click **Save**. If you forget the Name, Javis says "Enter a name".
5. The new agent card appears in the list with a 🤖 icon, the model name and the assigned skill labels. With no skills assigned, the card reads "no skills assigned".

A note on the Skills field: the list comes from the vault's skill folder. If the vault has no skills, the panel says so and notes that you can create the agent now and assign skills later. Creating skills is covered on the [Skills](06-skills.md) page.

### What the Model picker offers

| Option | Group | Runs on |
|---|---|---|
| **Default (per CLI)** | (no group) | See the explanation under the table |
| **Sonnet** | Claude (Claude Code) | Claude Code |
| **Opus** | Claude (Claude Code) | Claude Code |
| **Haiku** | Claude (Claude Code) | Claude Code |
| **Fable** | Claude (Claude Code) | Claude Code |
| **GPT-5.5** | ChatGPT (Codex, requires a ChatGPT login) | Codex CLI |
| **GPT-5.4** | ChatGPT (Codex, requires a ChatGPT login) | Codex CLI |
| **GPT-5.3 Codex** | ChatGPT (Codex, requires a ChatGPT login) | Codex CLI |

Under the Model field there is a note: agents run through the provider's CLI, so choosing Claude means Claude Code and choosing ChatGPT means Codex (which requires being signed into ChatGPT on the machine or VPS). Both read and write vault files and use MCP.

**What "Default (per CLI)" really does:** left empty, Javis takes the **auxiliary model** you set on the **Models** page first (only when that auxiliary model is a Claude model); with no Claude auxiliary model it falls back to the CLI's default. If you want an agent to always run on one specific model regardless of the global configuration, pick that model explicitly instead of leaving it empty.

### An agent's own memory and run log

Besides the `.md` file, each agent has two more things inside the brain's `memory/agents/<slug>/` folder:

- **`MEMORY.md`, its own memory.** Every time the agent runs, Javis reads this file and injects it into the agent's system prompt under the heading `# Your memory:`. This is where long-term knowledge accumulates: house conventions, a client list, mistakes it was corrected on. The file has **two writers**: you by hand, and the agent **adding to it as it runs**. At the end of a task, if it learned something reusable, the agent proposes it and Javis writes it into the `## Lessons (self-learned)` section. Javis holds the pen rather than the model, so there are hard rails: duplicate lessons are dropped, only the 15 newest lines are kept so the memory gets denser rather than longer, and the part you wrote by hand outside that section is never touched. That means the agent gets smarter with each use, with no bulk background job.
- **`runs/`, the run log.** After each workflow step (verification steps included), Javis appends an entry to `runs/<YYYY-MM-DD>.md` with the time, the task given and the result (trimmed). This is where you check "what did this agent do yesterday" without reopening the run panel. This raw log does not go into the brain's git history.

Both are ordinary text files: open, read and edit them through [File manager](05-file-manager.md). To teach an agent something, write it straight into `memory/agents/<slug>/MEMORY.md` and it knows on the next run.

To be clear: this memory belongs to **one agent**; Javis's shared memory about you and the business lives in `memory/MEMORY.md` and `memory/facts/`, see [Second Brain: memory, Wiki, INGEST](13-second-brain.md).

### Editing or deleting an agent

- **Edit**: select the agent, change its settings on the right and click **Save**.
- **⤓ Export**: package the agent (with its skills) into a `.zip` to share, see "Sharing" at the end of this page.
- **Delete**: click **Delete** and confirm in the "Delete agent ...?" dialog. Note: if a workflow uses that agent, its step will point at an agent that no longer exists, so check related workflows afterwards. Deleting an agent does **not** delete `memory/agents/<slug>/`, so its old memory and logs remain on disk.

## Creating a Workflow (step by step, through the form)

Create at least one agent in the **Agents** tab before creating a workflow.

1. Open **Partners > Workflows**.
2. Click the create workflow button at the bottom left.
3. Fill in:
   - **Name**: the workflow name. Required.
   - **Description**: one line about what it does (optional but recommended; it shows on the workflow card).
   - **Group**: a group name so it files into the left column, typed fresh or picked from existing groups. Left empty, it lands in "Chung".
4. In **Steps (each step = 1 agent · use {{input}} and {{prev}})**, every step is a block with:
   - A **Task** field: what this step must do. Two special variables are available:
     - `{{input}}` = the input you type when you run the workflow.
     - `{{prev}}` = the result of the immediately preceding step.
   - A **Verification** section (optional): pick an agent to review this step, and how many retries are allowed. Leave it at "- no verification -" if not needed. The retry count defaults to 1 and ranges from 0 to 5.
5. Click **+ Step** to add another step.
6. Click **Save**. If you forget the Name, Javis says "Enter a name". New workflows are saved in the ready (active) state.

### A step's header row

Each step has a header row, left to right:

| Element | Meaning |
|---|---|
| Number | 1, 2, 3... in run order |
| Summary line | "agent name · task" condensed to one line |
| Agent picker | Change which agent owns this step |
| **↑** | Move the step up (dimmed on the first step) |
| **↓** | Move the step down (dimmed on the last step) |
| **✕** | Delete this step (at the END of the header row) |

**Collapsing and expanding steps:** click the header row (an empty part, not a button or picker) to collapse or expand that step's body. Opening an existing workflow to **edit** collapses every step by default so you see the whole pipeline first; click a step to open it. A **new** workflow has only one step, so it opens expanded.

Text you are typing is not lost when you collapse, reorder or delete another step; Javis captures every step's content before each redraw.

### A 2-step example

- Step 1: agent **Researcher**, task: `Research this topic thoroughly: {{input}}. Find sources, summarise the key insights.`
- Step 2: agent **Writer**, task: `Write a complete article about '{{input}}' based on this research:` then a line break and `{{prev}}`. In Verification, pick the **Verifier** agent with 2 retries.


### Editing, exporting or deleting a workflow

Select a workflow in the left column. The right column has **Edit**, **Export** and **Delete** buttons and its steps. Edit opens the workflow editor; saving refreshes the list and details.

## Running a workflow

1. Open **Partners > Workflows** and select a workflow on the left.
2. Send a request in chat. Each message starts one run; its text supplies `{{input}}`.
3. Follow step progress on the right. Steps with verification may retry using the verifier's feedback and the configured retry limit.
4. If approval is required, read the request and use the approval button on the right to continue. Errors and waiting states also appear in chat.
5. The final result arrives in chat. The next message in the same conversation includes the previous result, so you can request a revision, such as "Keep the main points but make it shorter".

**Run history** on the right lists recent runs. Select a run to inspect its details and reopen its conversation when it has a chat session. Recently run workflows move to the top of the list. In Javis's main chat you can also ask "How did the latest workflow run go?" to query saved runs from Partners and Kanban.

Each step still writes its agent log under `memory/agents/<slug>/runs/`. After a connection loss, check run history before sending the request again to avoid duplicate runs.

## Creating agents and workflows in words (through chat)

You are not required to use the form. In the chat with Javis (see [Chat & voice](02-chat-and-voice.md)) you can ask in words, for example:

- "Create an agent that writes sales emails."
- "Create a workflow that researches then writes an article."
- "Add an editing step to workflow X."

Javis then writes the matching .md file into the vault, sets an accent-free slug, tags an agent or files a workflow in a group (reading the tags and groups already used in the brain and picking the closest), assigns sensible skills from what exists, and if a workflow references an agent that does not exist yet, creates that agent first. Afterwards Javis reports briefly which files it created or edited. Return to the Partners page and they are there, with nothing else to do.

This is handy when you can describe the intent in words but do not want to fill in forms, or when you want to adjust several steps at once.

## Where agents and workflows are stored

In the current brain layout, each agent is a file at `agents/<slug>.md` and each workflow at `workflows/<slug>.md`. The `slug` is lowercase, hyphenated and accent-free (so "viết email" becomes `viet-email`).

**Older brains that have not migrated** keep those two folders at `Javis/agents/` and `Javis/workflows/`. Javis detects it: if the new folder exists it uses it, otherwise it uses the old path. So if the Files page shows no `agents/` at the brain root, look inside `Javis/`.

Because they are text files, you can open them through [File manager](05-file-manager.md) to read or edit by hand. The file structure:

- Agent: the frontmatter holds the name, role, tags (`tags`, a list), skill list and model; the body is the detailed system prompt. Its own memory and run log live outside this file, in `memory/agents/<slug>/`.
- Workflow: the frontmatter holds the name, status (active or off), group (`group`), description and the list of steps (each with an agent, a task, and optionally a verifying agent plus a retry count).

Editing by hand works too. Agent: write `tags: [Marketing, Writing]`; once `tags` is present (even `tags: []`) Javis reads only it. An old agent file with just `group: Marketing` still reads as one Marketing tag; the first save adds `tags` and keeps `group` as the first tag so an older Javis can still read it. Workflows and skills use `group`; without it they land in "Chung".

Edit and save a file and the Partners page picks up the new content on the next load.

## Tips

- **Always separate a verification step for important work.** Make the verifier a different agent from the doer, because it is forced into the "assume the result is wrong" role. That is how you reduce sloppy or invented output.
- **One step, one job.** Do not cram "research and write and publish" into one step. Splitting it keeps control and makes each part fixable.
- **Use `{{prev}}` to connect the chain.** A later step that needs the previous result must mention `{{prev}}` in its task, otherwise the agent never sees that output.
- **Reorder with ↑/↓ instead of deleting and redoing.** Wrong order only needs a nudge up or down; the content moves intact.
- **Keep retries moderate.** 1 to 2 is usually enough. Setting them high makes the workflow slow and expensive when the result is hard to reach.
- **Match the model to the job.** Reasoning-heavy steps (analysis, verification) suit Opus; simple, high-volume steps suit Haiku for speed and cost. Details in [Models & engines](10-models-and-engines.md).
- **Assign skills where they belong.** An agent is only strong with the right skills. A sales page agent should carry the sales page skill. Skill management is in [Skills](06-skills.md).
- **Use the private memory for anything repetitive.** Instructions you would otherwise repeat every run belong in `memory/agents/<slug>/MEMORY.md` rather than stuffed into the system prompt.

## Sharing: Export / Import (agents, skills, workflows)

You can package an agent, skill or workflow into **one `.zip`** to send to someone else, and take someone else's package into your brain.

- **Export:** each agent / skill / workflow card has a **⤓ Export** button that downloads a `.zip`. The package **includes dependencies** so the recipient can run it immediately: exporting a workflow includes the agents it uses and those agents' skills; exporting an agent includes its skills. **System** skills are not packaged, because every brain already has them.
- **Safety:** on import, Javis blocks unusual paths inside the package (nothing may be written outside the agent/skill/workflow folders) and limits the size to guard against malicious files. Even so, only import packages from sources you trust, because skill content is instructions the AI follows.

Note: an exported package only contains definition files. **An agent's memory and run log do not travel with it**, so the recipient gets the role and the skills, not the memories.

## Share a whole Team

On the Teams page, a team's **⋯** menu has **Share team**: it downloads one `.team.javis.zip` file with the team's partners, their skills, the leader and the pinned messages (as shared instructions). The file holds **no** chat history, keys, passwords, models or Auto switches; text that looks like an API key, a bot token or a `password: ...` line is replaced with `[REDACTED]` before writing.

The person who receives it presses **Import team** at the top of the team list, picks the file, sees which partners and how many skills come in, and confirms. A partner already in the brain under the same name keeps the receiver's version; models and Auto are the receiver's choice afterwards. An older Javis can still open the file with the Import button on the Partners page (it then adds the partners without building the team).

Every chat turn that creates, edits or removes a schedule, loop, partner, workflow or skill also leaves a small line under the answer ("Created schedule: ..."). New items get an **Undo** button: it cancels the schedule or deletes the loop, partner, workflow or skill just created.

## A Team waiting for your approval (from 0.207.0)

In a job given to a Team, when a member needs your decision (pick a plan, spend money, send or post something outside) that step **really stops**: the job moves to **Waiting for your approval**, frees the team's slot for its other jobs, and the chat shows an **Approval request** card with what will be done, the scope, the impact, the evidence and the exact calls that will run. Before, "@Owner please approve?" was taken as the result and the job closed itself.

- **Approve**: the member carries on in a new step, and only the exact approved calls run, each once. A restart or a rerun of the step never repeats an action that already ran.
- **Ask for changes**: write what should change; the member brings a new proposal (as a new card).
- **Reject**: write the reason; the job stops there, and you edit the job to give a new direction or cancel it.
- **Revoke approval**: take back an approval that was not used yet.

Editing or cancelling the job voids its old cards. Words in the chat (yours or a member's) never stand in for the Approve button. Each click carries its own key, so a retry on a flaky connection does not act twice, and a second tab is told the request was already decided.

**The team's permission** (Team tab, **The team's outside actions**):
- **Needs your approval** (default, older teams too): members read, search, write files in the brain and the team folder, and run read-only commands on their own. Sending, posting, paying, ordering, deleting data or other machine commands are stopped BEFORE they run and become an approval card.
- **The team acts without asking**: the same rights as your private chat with each member (how Teams ran from 0.194.0 to 0.206.0).

With Needs your approval, Claude Code, Codex (with its own sandbox) and the API-key brains stop an action before it runs. Grok Build only does the in-scope part (an approved action cannot run on Grok). Antigravity cannot stop its own tools, so that step is refused with an explanation: move the member to another brain or turn on "The team acts without asking".

## A Team's department mandate (from 0.208.0)

The Team tab has a **Department mandate** section. Older teams have none, so nothing runs on its own until you set one and press **Turn on**.

- **Outcome**: what this team is for. **How it is measured**: one criterion per line.
- **Granted sources**, one per line: `folder:reports` (a folder in the brain), `kanban` (failed Kanban jobs of the brain), `mcp:<connection id>` (whether a connection is down), `test:<check command>` (runs at the Coding page's auto level, so it can run code such as `pytest` or `npm test`; only you can set it; a non-zero exit or more than 2 minutes is a failure).
- **Scope**, **observe every**, **observations per day**, **jobs it may open per day**, and **stop opening jobs at N open jobs**.
- For each kind of opportunity (documents changed, Kanban job failed, check command failing, connection down) pick: **Only record it**, **Propose it to me**, **Open a job, wait for my approval** or **Open the job itself**.

Javis reads the sources with code, no model. A source it cannot read shows as **missing** with the reason; no problem is made up. A change becomes an **opportunity** with its source, data version, a reason tied to the outcome and the benefit. The same data never opens twice, an opportunity you **Skip** only returns when the data changes, each source has a cooldown, and a proposal left for 48 hours expires. Past the day's job budget or the open-job limit it only proposes.

A job the mandate opens carries the trace (mandate, version, observation, opportunity) in its request, and its outside actions still go through the approval gate. **Pause** stops observing; **Revoke** cancels the mandate's jobs that have not started and closes open proposals. Every edit is a new version with history.

## Product acceptance for a Team (from 0.209.0)

On the Jobs tab, a waiting or running job has an **Acceptance** button to set criteria, one per line:

- `file: reports/week.md`: the file must exist.
- `contains: posts/a.md | 300 | price, contact`: at least 300 characters and every phrase.
- `json: data.json | revenue, orders`: valid JSON with those keys.
- `cmd: pytest -q`: a check command must exit 0 (runs at the Coding page's auto level).
- `confirm: reports/week.md`: you confirm it yourself.

When a member hands in the result, Javis checks the product itself (the files) against each criterion: **pass**, **fail** or **unclear**, with evidence (path, sha256 hash, size, modified time). A model's opinion is never the verdict.

- All pass: only then is the job **done**.
- A criterion fails: that member gets a fix step saying what failed. Past the fix rounds (2 by default) the job stops at **did not meet the criteria**; edit the job to try again.
- A criterion is unclear or needs your confirmation: the chat shows a **Product acceptance** card with **Passes, close the job** or **Not yet, send back** (with a note). A file that changed after the check cannot be accepted until it is checked again.

Editing the job voids the old evidence. After acceptance, editing a product file shows "The product changed after the check" on the card. A member's learning score only goes up from a passed acceptance or your confirmation, once per job.

## Quick actions and troubleshooting

- **Create:** choose a tab and use the create button at the bottom left, or open **Javis Store**.
- **New conversation:** start a separate session with the selected partner.
- **Edit / Export / Delete:** use the selected partner's right column.
- **Empty list:** check the selected brain, search and tag (or group) filter, then create a partner if needed.
- **Missing settings or history:** use the details button above chat to open the right column, especially on narrow screens.
- **Missing workflow agent:** create that agent first, then select it in the step editor.
- **Connection loss or run error:** read the chat message and run history before sending the request again.
- **Page stuck loading:** check the server on port 7777 and see [Troubleshooting & FAQ](17-troubleshooting.md).

## Related

- [Skills](06-skills.md) - creating, enabling and assigning skills to agents.
- [Plugins](20-plugins.md) - an item in the Capabilities group, for tools that run real code.
- [Models & engines](10-models-and-engines.md) - picking the main model, the auxiliary model and the providers.
- [Work / Kanban](21-kanban-work.md) - where workflows run automatically in the background per task.
- [Second Brain: memory, Wiki, INGEST](13-second-brain.md) - telling an agent's private memory apart from Javis's shared memory.
- [File manager](05-file-manager.md) - opening and hand-editing agent, workflow and memory files.
