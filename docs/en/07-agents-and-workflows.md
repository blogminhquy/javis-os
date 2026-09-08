# Agents & Workflows

*[Tiếng Việt](../07-agents-va-workflows.md) · **English***

This is where you create specialised AI assistants (Agents) and chain them into automated pipelines (Workflows). For example: a research agent, a writing agent and a reviewing agent, chained into "research > write > verify" that produces a result in one run.

## What this feature is

- **An Agent** is an "AI employee" with a fixed role. Each agent has: a name, a role description, a detailed working instruction (system prompt), a list of skills it may use, a **model to run on**, and its **own memory** that accumulates over time. The model can come from **any provider you connected** on the Models page: Claude (Claude Code), ChatGPT (Codex), Grok Build CLI, Antigravity CLI, OpenRouter, Anthropic API, OpenAI, Google Gemini, Groq. The picker reads straight from your connected providers, so connecting more adds more choices. Every provider can read and write vault files and use MCP; Claude Code and Codex additionally have shell commands and can browse the web. If the chosen provider fails at runtime, Javis falls back to another brain rather than leaving the agent silent. (Ollama cannot run agents yet, so it does not appear here.) An agent's model is REALLY applied when the workflow runs.
  - Safety note: when a workflow runs **automatically in the background** (the Kanban dispatcher, restricted file-tool mode), the agent always uses Claude Code to keep the safe tool restrictions, even if you picked another provider. Your chosen model applies when you click **▶ Run** directly on the Workflows page.
- **A Workflow** is a chain of steps, each handing one task to one agent. The result of a step can flow into the next. You can attach a **verification step**: another agent playing the reviewer, which by default assumes the result is wrong and must be proven otherwise; if it fails, the workflow retries a few times.
- Every agent and workflow is stored as an **.md file in the vault** (the selected brain), so you can read them, edit them by hand, and Javis can create them from chat.

Related: choosing an agent model in [Models & engines](10-models-and-engines.md); creating and enabling skills to assign in [Skills](06-skills.md).

## Where to find it in Javis

In the left navigation rail of the dashboard (port 7777 by default), open the **Capabilities** group. It has 4 items, two of which this page covers:

- **Agents**: managing AI assistants.
- **Workflows**: managing pipelines.

(The other two are Skills and Plugins.) Clicking one opens that page. Everything on these two pages belongs to the selected brain: switching brains switches the agent and workflow lists.

## First: click "Create samples" for a working example

If you are starting from nothing, the fastest route is the built-in sample set.

1. Open the **Workflows** page.
2. In the top right, click **Create samples**.
3. Javis creates 3 agents and 1 sample workflow (all 3 agents preset to the **Sonnet** model):
   - Agent **Researcher**: research, finding material, summarising sources (preassigned the deep-research skill).
   - Agent **Writer**: writing articles from research material (preassigned the salepage-16-buoc skill).
   - Agent **Verifier**: independent review, always assuming the result is wrong until proven otherwise; it creates no content, only grades.
   - Workflow **Research → Write (with verification)**: step 1 researches, step 2 writes and is independently verified, retrying up to 2 times if it fails.

With the samples in place you can run one immediately (see "Running a workflow" below), or open them and adapt them to understand how it works.

Note: the two skills the sample agents reference (deep-research, salepage-16-buoc) are just preassigned names. If your brain does not have them, the agents still run normally, only without the specialised instructions.

## Finding things once you have many: the group column and the search box

Both the Agents and Workflows pages have a **Group** column on the left with per-group counts, plus a search box above the list. It works exactly like the [Skills](06-skills.md) page:

- Click a group to see only the agents (or workflows) in it; click **All** to see everything again.
- The search box filters by name, slug and role (for workflows: name, slug and description). Typing without accents still finds accented results: typing "viet email" finds "Viết email".
- Group and search stack, so picking a group and then typing searches inside that group.
- The **Select all** button (for exporting several items in one package) only takes what is **currently showing**, meaning the right group and the right search.
- On phones, the group column becomes a horizontally scrolling chip strip above the list.

Agents and workflows created before version 0.55.38 have no group and sit in the **Chung** (General) group; nothing is lost. To file them properly, open one for editing and fill in the Group field.

## Creating an Agent (step by step, through the form)

1. Open the **Agents** page.
2. Click **+ Agent** in the top right. An editor opens on the right of the screen.
3. Fill in:

| Field | Meaning | Suggestion |
|---|---|---|
| **Name** | The agent name shown on the card. Required. | e.g. "Email specialist" |
| **Role (short description)** | One sentence about what the agent does. | e.g. "Writes sales emails in a friendly voice" |
| **Group** | A group name so the dashboard files the agent in the left column. Type a new one or pick an existing one (the field suggests). Leave it empty and the agent falls into "Chung". | e.g. Marketing, Sales, Content |
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

Both are ordinary text files: open, read and edit them through [File manager](05-file-manager.md). To teach an agent something, write it straight into `memory/agents/<slug>/MEMORY.md` and it knows on the next run. That is why an empty Agents page reads "No agents yet. Click + Agent to create one (role + skills + its own memory)."

To be clear: this memory belongs to **one agent**; Javis's shared memory about you and the business lives in `memory/MEMORY.md` and `memory/facts/`, see [Second Brain: memory, Wiki, INGEST](13-second-brain.md).

### Editing or deleting an agent

- **Edit**: on the agent card, click **Edit**, change things and click **Save**.
- **⤓ Export**: package the agent (with its skills) into a `.zip` to share, see "Sharing" at the end of this page.
- **Delete**: click **Delete** and confirm in the "Delete agent ...?" dialog. Note: if a workflow uses that agent, its step will point at an agent that no longer exists, so check related workflows afterwards. Deleting an agent does **not** delete `memory/agents/<slug>/`, so its old memory and logs remain on disk.

## Creating a Workflow (step by step, through the form)

You need at least one agent before creating a workflow. With no agents, clicking create tells you to create an Agent first (on the Agents tab) or to click Create samples.

1. Open the **Workflows** page.
2. Click **+ Workflow** in the top right.
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

That is exactly the "Research → Write (with verification)" sample that Create samples generates.

### Reading a workflow card

Each workflow shows as a card with:

- A header row: the workflow name, a status badge (**● Ready** when on, **Archived** when off), the group name, and the step count as "N steps".
- The description line (if you filled the Description field).
- The pipeline diagram: steps numbered 01, 02, ... Each box shows the **task** as its main text and the agent name underneath. Variables are rendered as words for readability: `{{input}}` shows as "input" and `{{prev}}` as "previous result"; any other variable shows its raw name.
- A button row: **▶ Run**, **Edit**, **Archive** or **Activate**, **⤓ Export**, **Delete**.

### Enabling, disabling, editing and deleting a workflow

- **On/off**: click **Archive** to turn a workflow off (the button becomes **Activate**). An archived workflow cannot run: **▶ Run** is dimmed. Click **Activate** to switch it back on.
- **Edit**: click **Edit**, change the steps and click **Save**.
- **Delete**: click **Delete** and confirm in the "Delete workflow ...?" dialog.

## Running a workflow (step by step)

1. On a workflow card in the **● Ready** state, click **▶ Run**.
2. A prompt asks for the input, for example "Input for ... (e.g. the article topic)". Type what you want to feed in (this becomes `{{input}}`) and confirm. Cancelling does not run the workflow.
3. A run panel slides out on the right, showing progress in real time:
   - The top reads "▶ workflow name", with the total step count underneath.
   - The card badge changes to **⏳ Running...**, then **⏳ Step 1/N**, **⏳ Step 2/N**, and so on.
   - In the pipeline diagram, the running step lights up and finished steps get a completion mark.
   - For each step you see the agent name, the task, and the result streaming out as the agent works. If the agent calls a tool, a ⚙ note appears with the tool name.
4. If the step has verification, once the agent finishes you see "🔍 ... verifying..." (with an attempt number when it repeats). Verification ends one of two ways:
   - **✓ Pass**: the step is accepted and flows into the next.
   - **✗ Fail**: with a short reason. The workflow reruns that step ("↻ Retry ...") using the feedback, up to the retry count you set. A retry SEES the previous result plus the feedback so it improves rather than starting over.
   - If it still fails after all retries, the step still ends but carries the warning "⚠ Verification failed after all attempts, review the result". At that point you should read the output yourself.
5. When everything is done, the panel ends with "✓ Workflow complete".
6. Click the panel's close button to dismiss it. Closing the panel also stops what is running.

After each step, Javis writes the result into the run log of the agent that owned it (`memory/agents/<slug>/runs/`), so you can reread it even after closing the panel.

## Creating agents and workflows in words (through chat)

You are not required to use the form. In the chat with Javis (see [Chat & voice](02-chat-and-voice.md)) you can ask in words, for example:

- "Create an agent that writes sales emails."
- "Create a workflow that researches then writes an article."
- "Add an editing step to workflow X."

Javis then writes the matching .md file into the vault, sets an accent-free slug, files it in a group (reading the groups already used in the brain and picking the closest), assigns sensible skills from what exists, and if a workflow references an agent that does not exist yet, creates that agent first. Afterwards Javis reports briefly which files it created or edited. Return to the Agents or Workflows page and they are there, with nothing else to do.

This is handy when you can describe the intent in words but do not want to fill in forms, or when you want to adjust several steps at once.

## Where agents and workflows are stored

In the current brain layout, each agent is a file at `agents/<slug>.md` and each workflow at `workflows/<slug>.md`. The `slug` is lowercase, hyphenated and accent-free (so "viết email" becomes `viet-email`).

**Older brains that have not migrated** keep those two folders at `Javis/agents/` and `Javis/workflows/`. Javis detects it: if the new folder exists it uses it, otherwise it uses the old path. So if the Files page shows no `agents/` at the brain root, look inside `Javis/`.

Because they are text files, you can open them through [File manager](05-file-manager.md) to read or edit by hand. The file structure:

- Agent: the frontmatter holds the name, role, group (`group`), skill list and model; the body is the detailed system prompt. Its own memory and run log live outside this file, in `memory/agents/<slug>/`.
- Workflow: the frontmatter holds the name, status (active or off), group (`group`), description and the list of steps (each with an agent, a task, and optionally a verifying agent plus a retry count).

The `group` field is written the same way for agents, workflows and skills, so editing it by hand works too: write `group: Marketing` and the next page load files it correctly. Without the field it lands in "Chung".

Edit and save a file and the Agents / Workflows page picks up the new content on the next load.

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
- **Import:** each **Agents / Skills / Workflows** page has an **⤒ Import** button. Pick a `.zip` (a Javis package), a single `.md` (agent/workflow), or a **Claude `.skill` package** (Javis recognises the `SKILL.md` inside and files it into the skill folder) to bring it into the selected brain. Javis asks whether to **overwrite** on a name clash: Cancel keeps what you have (importing only what is new), OK overwrites with the package version. Afterwards Javis reports what was imported and what was skipped.
- **Safety:** on import, Javis blocks unusual paths inside the package (nothing may be written outside the agent/skill/workflow folders) and limits the size to guard against malicious files. Even so, only import packages from sources you trust, because skill content is instructions the AI follows.

Note: an exported package only contains definition files. **An agent's memory and run log do not travel with it**, so the recipient gets the role and the skills, not the memories.

## Quick reference: buttons and states

| What you see | Meaning / action |
|---|---|
| **+ Agent** / **+ Workflow** | Open the create form |
| **Create samples** (Workflows page) | Generate 3 agents + 1 workflow that run immediately |
| **⤒ Import** | Bring a `.zip` / `.md` / `.skill` package into the selected brain |
| **⤓ Export** | Download a `.zip` with dependencies to share |
| **● Ready** | The workflow is on and can run |
| **Archived** (badge) | The workflow is off; ▶ Run is dimmed |
| **Archive** / **Activate** (button) | Turn the workflow off / on |
| **N steps** | How many steps the pipeline has |
| **▶ Run** | Run the workflow: ask for input, then open the run panel |
| **↑** / **↓** (in a step) | Reorder steps |
| **✕** (end of a step header) | Delete that step |
| **⏳ Step i/N** | Currently on step i |
| **✓ Pass** / **✗ Fail** | The result of one verification round |
| **↻ Retry k** | Rerunning the step with verification feedback |
| **⚠ Verification failed after all attempts** | Retries exhausted without passing; read it yourself |
| **✓ Workflow complete** | The whole run finished |

## Common problems

- **Clicking + Workflow says there are no agents.** You have not created one. Go to the Agents page and create at least one, or click Create samples on the Workflows page for a ready-made set.
- **▶ Run is dimmed and unclickable.** The workflow is Archived. Click **Activate** to return it to ● Ready, then run.
- **The list is empty, reading "No workflows" or "No agents".** That is the starting state. Click **Create samples** (on Workflows) or **+ Agent** / **+ Workflow** to begin. If it went empty right after switching brains, check which brain you are in.
- **Opening a workflow for editing shows every step collapsed, as if the content is gone.** Nothing is gone. Editing collapses steps by default so you see the whole pipeline; click a step header to open it.
- **The Skills field is empty when creating an agent.** The vault has no skills yet. Create the agent first, create skills on the [Skills](06-skills.md) page, then come back and assign them.
- **You picked a GPT-5.x model but the agent still runs on Claude.** That is by design when the workflow runs automatically in the background: that mode forces Claude Code to keep the tool restrictions. To use Codex, click **▶ Run** directly on the workflow card, with the machine signed into ChatGPT.
- **You left Model empty and the agent runs on an unexpected model.** Empty means it takes the auxiliary model from the Models page first. To fix it, pick a model for the agent explicitly.
- **You cannot find an `agents/` folder in the brain.** Older brains keep them at `Javis/agents/` and `Javis/workflows/`. Open the Files page and look inside `Javis`.
- **A step shows "⚠ Verification failed after all attempts".** The working agent used all its retries and the verifier still failed it. Read that step's output yourself; consider clarifying the task, moving to a stronger model, or raising the retry count and running again.
- **The run panel stops halfway.** Closing the panel aborts the run. A flaky network can also stop it; reopen the workflow and click ▶ Run to start over.
- **The page hangs on "Loading...".** The server is slow or not running. Check that Javis is up on port 7777, then reload. If it persists, see [Troubleshooting & FAQ](17-troubleshooting.md).

## Related

- [Skills](06-skills.md) - creating, enabling and assigning skills to agents.
- [Plugins](20-plugins.md) - the fourth item in the Capabilities group, for tools that run real code.
- [Models & engines](10-models-and-engines.md) - picking the main model, the auxiliary model and the providers.
- [Work / Kanban](21-kanban-work.md) - where workflows run automatically in the background per task.
- [Second Brain: memory, Wiki, INGEST](13-second-brain.md) - telling an agent's private memory apart from Javis's shared memory.
- [File manager](05-file-manager.md) - opening and hand-editing agent, workflow and memory files.
