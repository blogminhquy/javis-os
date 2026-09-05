# Self-learning: Javis getting smarter over time

*[Tiếng Việt](../22-tu-hoc.md) · **English***

Every conversation with Javis lets something worth keeping slip past: a fact about your work, a concept just explained, a procedure just completed. The **Self-learning** page turns on the loop that picks those up and writes them into the brain, so next time Javis does not have to ask again.

This page covers turning self-learning on, choosing how assertive it is, understanding what it learns and what it blocks, and undoing it when it learns something wrong.

## What this feature is

After a few chat turns, Javis opens a **separate learning process** to re-read the recent conversation and extract knowledge. That process is locked down tightly:

- **Read only.** It may only use `Read`, `Glob`, `Grep`, `LS`. The `Bash`, `WebFetch`, `WebSearch` and `Task` tools are blocked outright.
- **Isolated, no MCP.** It runs with an empty MCP configuration file in strict mode, so it cannot touch the POS, ads, Zalo or any data source you attached. If the empty MCP file cannot be created, Javis refuses to run at all rather than running temporarily with the machine's MCPs.
- **Pinned inside the brain**, with a 240-second time ceiling per learning pass.
- **It does NOT write files.** The only thing it returns is a JSON block describing "what should be learned". The writer is Javis's Python code. That way there is no chance of the model overwriting `MEMORY.md` by mistake, writing outside the brain, or deleting your notes.

Before writing, the code adds two more scans: a **secret-key scan** (API keys, Telegram tokens, JWTs, database connection strings, lines labelled "password") and a **prompt-injection scan** for things like "ignore all previous instructions". Anything caught is blocked, not written, and the reason goes into the log. The same holds in the other direction: the conversation content handed to the learning process has its imperative sentences neutralised, so a message a customer sent in cannot steer the learning loop.

Finally, Javis only allows writes into the brain's `memory/`, `Memory/`, `Wiki/`, `skills/`, `.claude/skills/`, `agents/`, `workflows/` and `Javis/` folders. Any path escaping that list is restored immediately.

## Where to open it in Javis

On the left navigation rail, open the **Brain** group then click **Self-learning** (the 🧠 icon). The page header reads **Self-learning** with the subtitle "Rewire Memory · Wiki · Skill (safe, undoable)".

The page works on the **selected brain**. Switch brains at the top of the screen and come back, and every metric, commit and log follows the new brain.

## How to use it (step by step)

### Step 1: Turn self-learning on

In the **Turn self-learning on** box, click the status button. The button toggles between two labels:

| Button label | Meaning |
| --- | --- |
| `● On` | Javis learns after every few chat turns |
| `○ Off` | Nothing is learned, however much you chat |

The first time you turn it on, the button briefly reads "git-init running...": Javis turns the brain folder into a local git repository. This happens once and **pushes nothing to the network**. With git, each learning pass is a commit, so you can review it and undo it with one button.

Afterwards the note under the button changes to the real result, for example "The brain was git-inited → auto-write is safe and undoable." If the machine has no git, the line starts with "⚠ git failed (git missing?)". It also says "auto will drop to dry-run", but that is old wording: in the current build, self-learning **still writes files normally without git**, it just loses one-touch undo and the backup route. See "What if the machine has no git" below.

Click the button again to turn it off. Turning off saves the state immediately, with no Save configuration needed.

### Step 2: Choose the write mode

The **Write mode** box has three buttons. Click one to select it and the description below changes.

| Button | The on-screen description | What it really does |
| --- | --- | --- |
| **Dry run** | "Only logs 'what would be learned', touching NO files. The safest." | Still runs the analysis and writes to the Learning log, but creates no file in the brain |
| **Suggest** | "Like dry run, so you can review before allowing writes." | Identical to Dry run as far as files go: it lists what it intended to learn and writes nothing |
| **Write automatically** | "Writes straight into Memory/Wiki, git-committed and undoable." | The only mode that genuinely writes files. With git, it adds a commit |

**A fresh install defaults to Write automatically.** If you want to watch for a few days before letting Javis touch the brain, switch to Dry run and read the Learning log for a while.

### Step 3: Choose what to learn

The **What to learn** box has six switches. A filled dot `●` is on, a hollow dot `○` is off. Click to toggle.

| Switch | Default | What it learns |
| --- | --- | --- |
| **Memories (Memory)** | On | Durable facts about you and your business, written into files under `memory/facts/` plus a line added to `MEMORY.md` |
| **Knowledge (Wiki)** | On | Reusable concepts, frameworks and procedures, written as notes in the brain's Wiki folder |
| **Skills (Skill)** | On | Multi-step procedures Javis just performed and judged repeatable, written as `skills/<slug>/SKILL.md` |
| **Roles (Agent)** | **Off** | Specialist roles you asked for repeatedly in conversation, written as `agents/<slug>.md`. An existing role needing improvement is **edited in place** rather than copied |
| **Step chains (Workflow)** | **Off** | Chains of 2 or more steps across roles you have repeated, written as `workflows/<slug>.md` in a disabled state so you review before enabling. An existing chain missing a step, carrying a redundant one or in the wrong order is **edited in place** |
| **Work (Kanban)** | **Off** | Proposals for background work, pushed onto the board on the **Work** page |

The hint line under the buttons reads: "Wiki/Skill are best turned on after you are comfortable with Memories (the Phase 2/3 path). Work = after learning, propose background tasks onto the Work (Kanban) board, only created for real in Write automatically mode, and a task always awaits your approval."

About the **Work** switch: it is off by default and Javis **actively turned it back off once** on machines that had it on before. The reason is very practical: inspecting a real work board showed nearly everything on it was machine-invented, and most of it was beyond a background worker (needing a sign-in, needing to send something outside, waiting for someone else's approval, touching source code outside the brain). Since then, work is only created when you **say so directly** in chat. The switch remains here for anyone who wants it back.

#### How Javis edits existing roles and chains

When a conversation shows an **existing** agent or workflow getting something wrong, missing a step, carrying a redundant one or assigning the wrong role, Javis edits that file directly rather than creating a near-duplicate beside it. That overwrite has four rails, all enforced by code rather than requested in words:

1. **The file must already exist.** An edit instruction with no file found is skipped, never silently turned into a new file.
2. **A reason is required**, drawn from the conversation itself. No reason means no edit, and the reason appears in the Learning log for you to read.
3. **Whatever is yours is preserved:** the display name you set, the enabled state, the model you chose for the agent, and any unfamiliar lines you added yourself in the frontmatter. Editing a chain never turns it on or off by itself.
4. **You can lock any file.** Adding `learn_lock: true` to the frontmatter forbids self-learning from touching that file, permanently.

On each edit, Javis appends a dated line with the reason to a `## History (self-learned)` section at the end of the file body, keeping the 10 most recent lines. Whatever you wrote by hand outside that section is never touched. And because every learning batch is still git-committed, a wrong edit is undone by clicking **Undo the latest learning run**.

**The recommended gradual path:** turn on Memories alone first, run it for a few days then open `MEMORY.md` to see whether Javis remembered correctly. Once that is fine, add Wiki knowledge. Only once comfortable add Skills, because a wrong skill skews how Javis handles things later. The Roles (Agent) and Step chains (Workflow) switches are also off by default because they create things that appear directly in Studio: only turn them on when you want Javis to build roles and chains from the work you ask for repeatedly, and like skills they pass an independent second review before being written (for an edit that review is stricter: is the reason genuinely grounded, does the new version keep what was already right), and a workflow is always created disabled. Leave the Work switch for last, and only if you genuinely want Javis creating background work on its own.

### Step 4: Turn the Curator on for periodic maintenance

The **Curator (periodic maintenance)** box has a `● On` / `○ Off` button, **off by default**. See the "Curator" section below for what it does.

### Step 5: Save the configuration

Click **💾 Save configuration**. The button reads "Saving..." then "✓ Saved" for about a second and a half before returning.

The write mode, the switches and the Curator **only take effect after you click Save**. The self-learning on/off button alone saves the moment you click it.

### Step 6: Click Learn now to try one pass

Click **▶ Learn now**. Javis saves the current configuration then runs one learning pass on the selected brain. The button reads "Learning..." for about 2.5 seconds then reloads the blocks below.

Note: **Learn now still respects the write mode**. In Dry run, clicking Learn now creates no files, only log entries.

If no chat turn is waiting, Javis takes that brain's most recent conversation session to learn from. A conversation that is too short is skipped silently with no log entry, so seeing nothing new in the Learning log usually means that brain has no content long enough to learn from.

## When Javis learns (the automatic rhythm)

You do not have to click anything. After each chat turn, Javis classifies it then adds it to a per-brain queue:

- A turn that is too short or is only a greeting, "ok" or "thanks" is dropped immediately and does not count.
- A turn with **knowledge-dense** signals (questions like "what is", "how many steps", "formula", "principle", "procedure", "concept", "how to") is flagged separately.
- Saying "remember", "keep this in mind", "save this" flags the turn as **urgent**.

Roughly every 30 seconds, Javis checks the queue and fires a learning batch when one of these holds: **3 turns** accumulated, or an urgent turn plus 30 seconds elapsed, or a knowledge-dense turn plus **3 minutes of silence**, or **10 minutes of silence** with turns still unlearned.

Each batch reads at most the 3 most recent conversation sessions, taking the last 12 messages of each, with the total content cut at about 24,000 characters. So it learns from what **just happened**, not by digging through the whole history.

Only one batch runs at a time. Self-learning, the Curator and the other writing processes share a lock on the brain so they never tread on each other.

## The gates before writing (why Javis learns less than you expect)

This is the part that puzzles people most: the log says "learned" but the file never appears. The reason is that each kind has its own gate.

**Memories (facts):**
- Confidence must be 2 or higher to be written.
- **Add only, never overwrite.** An existing memory file is skipped, unless the new information is marked as replacing the old one. In that case the old file gets a `superseded_by` field plus a history line, and is still not deleted.
- After writing, Javis inserts a line into `MEMORY.md` pointing at the new memory file.

**Wiki knowledge:**
- The density (how structurally explained it is) must be 2 or higher.
- Anything **Javis itself said with no source** may **not** enter the Wiki. It is pushed into `_open-questions.md` for you to verify. This is the rail against Javis poisoning its own memory with its own words.
- A concept duplicating an existing note creates no new note, only a suggested addition.
- A contradiction with an old note causes **no overwrite**: it adds a `## Contradiction` section to the old note with the new view, and opens a question to verify.
- After writing, Javis adds a line to `index.md` (under "## Self-learned") and a line to the Wiki's `log.md`.

**Skills:**
- Before writing, Javis opens **an independent second review**, assuming the proposed skills are wrong or redundant, keeping only what passes.
- A `description` over **150 characters** is blocked (the router truncates at exactly that, so the tail is lost silently), and opening with filler like "Activates when..." is blocked too.
- It **never overwrites an existing skill**, and **never resurrects a skill you turned off**.

**Work (Kanban), when you turn that switch on:**
- At most 3 jobs per batch, with confidence 2 or higher.
- A gate blocks outright the work a background worker certainly cannot do: anything involving a sign-in, cookies, OTP, QR codes, password changes or 2FA, work sending or publishing outside (Zalo, Telegram, email, a Page, comments), work that only waits for someone else's approval, and work touching source code outside the brain. The rejection reason is written into the log.

Everything blocked appears in the Learning log under **Blocked**, with a specific reason. Reading that section tells you at once why a file never appeared.

## Ceilings against burning quota

Self-learning runs on the **background work model**, not the main model. You choose that on the **Models** page (the **Connections** group), where the "◆ Background work model" block states plainly that it serves "loops · Kanban work · reminders · self-learning · digesting sources". Choosing a cheap model there makes self-learning cheap.

Javis also sets three hard ceilings itself, per day and independent of the turn-batching rhythm:

| Ceiling | Default | What happens at the ceiling |
| --- | --- | --- |
| Minimum gap between two batches | 90 seconds | That batch writes no files |
| Batches per day | 40 | Drops to dry run |
| Estimated tokens per day | 300,000 | Drops to dry run |

When downgraded, Javis still analyses and still logs "what would be learned", it just writes no files. The status in the log states the reason, for example "dry-run (daily fork ceiling reached → dropped to dry-run (backpressure))".

Clicking **▶ Learn now** is subject to exactly the same ceilings: the analysis always runs, but producing files requires being in Write automatically mode **and** not having hit any ceiling.

## Curator: periodic maintenance that deletes nothing

The **Curator (periodic maintenance)** button turns on a cleanup round running every **24 hours**. The on-screen description: "Cleans the index, LINTs the Wiki (suggestions only), compacts MEMORY.md. Deletes nothing."

Specifically it does three things:

1. **Rebuilds the memory index.** It scans `memory/facts/` and adds a line to `MEMORY.md` for any memory file lacking one. This is how it catches the case where you created a memory file by hand and forgot the index.
2. **Warns when the index bloats.** `MEMORY.md` is loaded into **every chat turn**, so its length makes every question more expensive. Over about **150 lines**, the Curator logs "⚠ over the index ceiling (~150 lines), consider compacting." It **does not compact by itself**, merging is your call.
3. **Checks Wiki health (LINT).** It finds duplicate notes, orphan notes nobody links to, broken wikilinks, unresolved contradictions and gaps. The result is only a **list of suggestions** written into the log under "Wiki LINT (suggestions, nothing changed)". The Curator never fixes anything and never deletes a note.

The "🩺 LINT Wiki" button that once existed on the dashboard is gone. LINT now runs inside the Curator.

The Curator has three savings worth knowing:

- **An unchanged Wiki skips the round entirely**, calling no model.
- **When something changed, it only inspects the changed notes**, not the whole store. The exception is a detected deletion or rename, which forces a full scan because those two break wikilinks even in unchanged pages.
- **Every 30 days it does one full scan** to catch cross-page problems that accumulate slowly.
- **A brain silent for over 14 days is skipped.** Self-learning's brain list only grows, so without that filter the Curator would run every 24 hours even on brains you abandoned long ago.

To run one round now, click **🧹 Curator now**. The button reads "Cleaning..." then reloads by itself.

## Quick reference of buttons and states

| Button / line | Where | What happens |
| --- | --- | --- |
| `● On` / `○ Off` | The Turn self-learning on box | The first On git-inits the brain then saves immediately. Off saves immediately too |
| `Dry run` / `Suggest` / `Write automatically` | The Write mode box | Chooses the write level. Only Write automatically creates files |
| `● Memories (Memory)` … `○ Work (Kanban)` | The What to learn box | The six switches for kinds of knowledge learned |
| `● On` / `○ Off` | The Curator box | Turns on the 24-hour maintenance round |
| **💾 Save configuration** | The button row | Saves the mode, the switches and the Curator. Shows "Saving..." then "✓ Saved" |
| **▶ Learn now** | The button row | Saves the configuration then runs one learning batch on the selected brain |
| **🧹 Curator now** | The button row | Runs one maintenance round immediately |
| **■ Stop** | The button row | Cancels the running learning batch and Curator round |
| **↶ Undo the latest learning run** | The button row (orange text) | Asks to confirm undoing (git revert) the latest learning run, then git-reverts the last learning commit |

## The "Metrics" line

Right under the button row is a one-line summary of the brain's health, shaped:

`Metrics · Memories: 87 · Wiki: 174 · MEMORY.md: 18363B · Forks today: 3 · Estimated tokens: 41200 · Learning commits: 26`

How to read it:

| Field | Meaning |
| --- | --- |
| **Memories** | The file count in `memory/facts/` |
| **Wiki** | The note count in the Wiki folder (excluding `index`, `log` and files starting with an underscore) |
| **MEMORY.md** | The memory index's size in bytes. This number is loaded into every chat turn, so smaller is cheaper |
| **Forks today** | Learning batches that wrote today, against the ceiling of 40 |
| **Estimated tokens** | Tokens self-learning spent today (a rough estimate), against the ceiling of 300,000 |
| **Learning commits** | Learning commits found in the brain's git history (counting at most the 50 most recent commits) |

## The "What Javis taught itself (latest commits)" block

This block lists at most the 12 most recent learning commits of the brain, each line carrying the commit title, the short hash, the timestamp, and up to 6 changed files.

The commit title is shaped `learn: +2 fact +1 wiki +0 skill (2026-07-29)` for a learning batch, and `curator: reindex memory (2026-07-29)` for a maintenance round. Only those two prefixes count as a "learning commit", so the base commit Javis creates when initialising the repo never appears here and is never touched by the Undo button.

With nothing yet, the block reads "No learning commits yet." If the brain is not a git repository, it shows an orange line saying the brain is not a git repo and to turn Self-learning on to git-init it (only then can commits be reviewed and undone).

**Undoing:** click **↶ Undo the latest learning run**, confirm, and Javis runs `git revert` on the last learning commit. On success it shows a dialog reading "Undone:" with the commit title. Three common failure reasons:

- "The brain is not a git repo"
- "There is no learning commit to undo"
- "Learning files have uncommitted edits, please handle them first: ..." (you are mid-edit on a file inside that commit. Save or revert your edits then try again. An unrelated dirty file does **not** block the undo)

One reassuring point: git here only tracks **distilled knowledge** (memories, Wiki, skills, `MEMORY.md`). Raw logs, the learning log, loop logs, conversation logs, the `attachments/` and `inbox/` folders are all outside, so a revert is always clean and never touches personal files.

## The "Learning log" block

The last block on the page shows at most the 10 most recent entries, gathered from the three newest log files in the brain's `Javis/learn-log/` (one `YYYY-MM-DD.md` file per day).

Each entry has a timestamp, a kind (`learn` or `curator`), the run reason (`auto` when self-fired, `manual` when you clicked), the status (`auto-write` or `dry-run` with the downgrade reason), then the list of what was learned as `fact=[...] wiki=[...] skill=[...]`, plus the commit hash if any. The body is a Vietnamese summary of the batch, along with a **Blocked** section listing each item a gate stopped and why.

With nothing yet, the block reads "No learning log yet."

The log is an ordinary markdown file, openable on the **Files** page (**Brain** group) if you want to read it in full rather than the last 10 entries.

## Syncing the brain with GitHub

Halfway down the page is another block, **⇅ Sync brain with GitHub (two-way)**. It sits here because it is also built on git, but it is a different feature: pushing the whole `brains` folder to a private repo and pulling from another machine. The full guide (creating the repo, creating the token, handling `.conflict-*` files) is on [Backing the brain up to GitHub](18-github-backup.md).

## What if the machine has no git

Self-learning **still runs and still writes files** normally. The Write mode box adds a line: "ℹ The machine has no `git`: Self-learning STILL runs normally, it just has no one-touch undo or GitHub backup. Install git to enable undo and brain backup."

What you lose without git:

- The **↶ Undo the latest learning run** button is unusable.
- The "What Javis taught itself" block is empty, so you cannot review which files each learning run changed.
- The brain cannot be synced to GitHub.

Every other safety rail stays: the learning process is still read only, still scans for secret keys and injected instructions, memories are still add-only, and it still cannot write outside the permitted folders.

Once git is installed, turn self-learning off and back on once so Javis git-inits the brain.

## Tips

- **To make Javis remember something for certain, say "remember ..." plainly in chat.** A sentence with "remember", "keep this in mind", "save this" is flagged urgent and learned in the very next batch instead of waiting for 3 turns.
- **Check that Javis learned correctly through `MEMORY.md` itself.** Open the **Files** page and go to `memory/MEMORY.md`. Each line is one memory. Fix or delete a wrong line right there, which is faster than undoing a whole commit.
- **Keep `MEMORY.md` compact.** This file is loaded into every chat turn. Once the metric passes about 150 lines, it is time to merge small memories into a larger one.
- **For quality Wiki knowledge, state the source.** Anything Javis merely inferred does not enter the Wiki. It is written only when you assert it or cite a named source.
- **Run Dry run for a few days before opening Write automatically** if your brain already holds many handwritten notes and you want to be sure Javis does not disturb your naming.
- **Switch the background work model to a cheap one** on the **Models** page if self-learning eats too much quota. Self-learning does not need the strongest model.

## Common problems

**Self-learning is on, you chatted all afternoon, and nothing was learned.**
Check in order: is the write mode **Write automatically** (Dry run and Suggest create no files); did the chat turns have "substance" (greetings, "ok", "thanks" are dropped); have 3 turns accumulated or 10 minutes of silence passed; and on the Metrics line, has "Forks today" hit 40. The Learning log always has the exact answer.

**The log says it learned but no new file appeared.**
Read the **Blocked** section of that very log entry. Common reasons: the memory duplicated an existing file so nothing was overwritten, the Wiki note was rejected because Javis said it with no source, the concept duplicated an existing note, or the skill's name collided or its `description` ran over 150 characters.

**Clicking Learn now changes nothing.**
If a learning batch or Curator round is mid-run, the new pass is refused. Wait for the running batch to finish (at most 240 seconds) then click again, or click **■ Stop** first.

**Undo reports "Learning files have uncommitted edits".**
You are mid-edit on a file inside that learning commit. Save or revert your edits first, then click again. Javis deliberately refuses to revert over your manual changes.

**Javis learned into the wrong brain.**
This page works on the brain selected at the top of the screen. Switch to the right brain then click Save configuration and Learn now again. The automatic learning loop itself learns into the brain of the conversation, regardless of which brain you have open on this page.

**The Curator is on but never seems to run.**
It runs once every 24 hours, and skips brains silent for over 14 days. Beyond that, when no Wiki note changed it skips the round to save cost, and the log records the reason as "no Wiki note changed". To see it now, click **🧹 Curator now**.

**You are worried self-learning will damage handwritten notes.**
The learning process has no write permission. The writing code does not overwrite an existing memory file, an existing Wiki note or an existing skill, deletes nothing, only edits an existing agent or workflow when there is a clear reason and you have not locked the file, and may only touch the `memory/`, `Wiki/`, `skills/`, `agents/`, `workflows/` and `Javis/` folders. Any path escaping that is restored immediately.

## Related

- [Second Brain: memory and Wiki](13-second-brain.md) - the structure of `memory/facts/`, `MEMORY.md` and the Wiki folder self-learning writes into
- [Skills](06-skills.md) - a self-learned skill sits in the same list as one you wrote, toggled the same way
- [Work (Kanban)](21-kanban-work.md) - where work proposed by the "Work (Kanban)" switch lands
- [Backing the brain up to GitHub](18-github-backup.md) - the sync block lives on this very page
- [Models and engines](10-models-and-engines.md) - choosing the background work model for self-learning
- [File manager](05-file-manager.md) - opening `MEMORY.md`, Wiki notes and learning log files to read or edit by hand
- [Troubleshooting and FAQ](17-troubleshooting.md)
