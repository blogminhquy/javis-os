# Second Brain: memory, Wiki, INGEST

*[Tiếng Việt](../13-second-brain-bo-nho-wiki.md) · **English***

The Second Brain is Javis's "external brain": a folder of Markdown notes that Javis reads, accumulates and remembers long term. Because of it, Javis does not just answer questions during a chat but remembers you, remembers your business, and understands you better over time.

This page covers: what the Second Brain contains, how to create and switch between several "brains", how to make Javis remember (long-term memory), and how to "digest" documents (INGEST) so raw files become reusable knowledge.

## What this feature is

A Second Brain (a "brain" or "vault" for short) is a folder on your machine or VPS with these subgroups:

| Layer | Folder | Role |
|---|---|---|
| Sources | `sources/` | Raw notes: articles, screenshots, files you drop in. These are the "originals". |
| Wiki | `wiki/` | Distilled knowledge: concepts, frameworks, procedures, cross-linked with `[[...]]`. |
| Memory | `memory/` | Living memory: what Javis remembers about you and the business. |
| Agents / Workflows | `agents/`, `workflows/` | The operating layer (see [Agents and Workflows](07-agents-and-workflows.md)). |
| Skills | `skills/` | The canonical copy of each skill, one folder per skill at `skills/<slug>/SKILL.md`. Javis mirrors them into `.claude/skills` so Claude Code loads them natively (see [Skills](06-skills.md)). |
| Operating layer | `Javis/` | Whatever chat creates: loops at `Javis/loops/<slug>.md`, per-chat Zalo rules at `Javis/zalo/<slug>.md`, reminders at `Javis/reminders.json`, and the capability index `Javis/index.md` (auto-generated from files, do not edit by hand). |
| Bullet journal | `00 - Dashboard/`, `01 - Daily Log/`, `02 - Weekly Log/`... | Where daily notes and tasks live; Dataview blocks pull from here (see [Tasks and Dataview in notes](19-tasks-and-dataview.md)). |
| Cache area | `attachments/`, `inbox/` | Images and attachments; `inbox/telegram/` is where files sent over Telegram land. **Both folders are caches and expire on their own**, read the dedicated section below before leaving anything valuable here. |

The three core layers of a "second brain" in the proper sense are **Sources + Wiki + Memory**:

- **Sources** holds raw, unprocessed material.
- **Wiki** is refined knowledge, linked into a network, which is exactly what Javis draws in the [Knowledge graph](03-knowledge-graph.md).
- **Memory** is the long-term memory that lets Javis "remember you".

The operating principle: **Sources -> (INGEST) -> Wiki**. Knowledge accumulates gradually, thickening the brain, instead of being rediscovered on every question.

## Where a brain lives on disk

Every brain sits under one parent folder named `brains/`, one subfolder per brain. On a local install that is `brains/` inside the Javis folder; on Docker/VPS it defaults to `/brains` (mounted separately so it can be backed up). Move it with the `BRAINS_DIR` environment variable, see [.env configuration](16-env-configuration.md).

The starting brain is named **Brain Default** and lives at `brains/Brain Default`.

`BRAIN_PATH` is only a legacy variable from when Javis had a single brain, kept around to migrate data into the new structure. Do not use it to point at the working brain.

## Where to open it in Javis

The Second Brain does not live on one dedicated page but is spread across several places on the dashboard (default port `7777`). The left navigation rail groups pages, so you have to open a group to see its items:

1. **Top bar, left corner**: the brain selector plus 3 small buttons ➕ 🗑 📁. This is where you create, choose and delete brains.
2. **The chat box** (the **Javis** screen or the **Chat** page, **Assistant** group): where you drop files to INGEST and say "remember this".
3. **The Self-learning page** (**Brain** group): number of memories learned, the learn-now button, the Curator cleanup, and the block that syncs the brain to GitHub. See [Self-learning](22-self-learning.md).
4. **The Files page** (**Brain** group): browse, edit, upload and download every file in the brain. See [File manager](05-file-manager.md).
5. **The Recurring jobs page** (**Work** group): set up a loop so Javis digests sources on a schedule. See [Recurring jobs and reminders](08-recurring-jobs.md).
6. **The Settings page** (**System** group): the **Interface and Brain** group, item **Brain structure**, to normalise the folders.

## Multi-brain: several brains in one Javis

You can keep several separate brains, for example one for the business and one for personal study. Each brain is an independent second brain: sources, wiki, memory, skills and agents are all its own.

The brain selector sits in the left corner of the top bar. Next to it are 3 buttons:

| Button | Label (hover to see) | What it does |
|---|---|---|
| ➕ | Create a new brain in the brains folder | Creates a new second brain |
| 🗑 | Delete the selected brain (confirm by typing the exact name) | Moves the selected brain to the trash (kept 30 days) |
| 📁 | Pick a brain from any external folder | Points at an existing folder of `.md` notes on the machine |

The starting brain is named **Brain Default** and cannot be deleted (it is the "root brain").

### Choosing the working brain

1. Click the brain selector in the left corner of the top bar.
2. Pick the brain you want. Each row shows as `🧠 Brain name · 128`, the number being how many `.md` notes Javis counted in that brain. If the count hits the counting ceiling (5000) a `+` is appended, meaning "at least this many" rather than the true total.
3. All of Javis (chat, graph, memory, agents) switches to that brain immediately. No page reload needed.

### Creating a new brain

1. Click the ➕ button next to the brain selector.
2. Type a name in the prompt that appears ("New brain name:") and confirm.
3. Javis creates a new subfolder in `brains/` with the standard structure ready (sources, agents, workflows, memory, skills, wiki, attachments and the bullet journal set) and immediately switches to the brain you just created.

The brain name has special characters stripped (`: * ? " < > |`), leading and trailing dots removed, and is cut to at most 60 characters for safety.

### Pointing at an existing note folder (external folder)

If you already have a store of `.md` notes somewhere on the machine (an Obsidian vault, say):

1. Click the 📁 button.
2. Pick the folder that holds the `.md` files.
3. Javis uses that folder as a brain. Note: an external folder is only "pointed at", the 🗑 button will not delete it from disk (it only removes it from the list).

Javis tidies the external-folder list itself: any entry whose path collides with a real brain, or that points at a folder deleted from disk, disappears from the menu on its own. When it cannot verify (the server hiccuped) the entry is kept, so nothing is removed by mistake.

### Deleting a brain (to the trash, kept 30 days)

Deleting a brain is **not permanent loss**. Javis moves the whole folder to a local trash and only clears it after 30 days. At the same time Javis writes a "tombstone" so the deletion propagates to every machine syncing along, and if you have GitHub backup on, the delete is pushed to the remote right away rather than waiting for the next cycle.

1. Select the brain you want to delete in the brain selector.
2. Click the 🗑 button.
3. The dialog that appears states clearly: the brain will be moved to the TRASH (kept 30 days, then deleted for good), and the deletion will SYNC to every other machine. It requires you to **type the brain name EXACTLY** to confirm.
4. Type it correctly and the brain goes to the trash, Javis returns to Brain Default, and a notice says the brain was deleted (moved to the 30-day trash, deletion synced to other machines). Type it wrong and you get "the name does not match, deletion cancelled".

The trash is the `brain-trash` folder inside Javis's state folder (`JAVIS_STATE_DIR`; the local install uses the `server/` folder, Docker uses the state volume). Each deletion creates a subfolder shaped like `Brain name__20260729-153012`. Clearing trash older than 30 days runs alongside each brain sync to GitHub.

**Brain Default** cannot be deleted; clicking 🗑 while it is selected reports that the default brain (the starting brain) cannot be removed.

For an external folder (📁), the 🗑 button behaves entirely differently: it asks whether to remove the external folder from the list, stating that it only drops it from the brain menu and does NOT delete data on disk, then removes just the entry. The data on disk is untouched.

### Normalising a brain's structure

If a brain has the old structure (notes under `Javis/agents`, `Memory` capitalised, skills in `.claude/skills`), you can collapse it into the uniform flat layout:

1. Go to **Settings** (**System** group on the rail).
2. Open the **Interface and Brain** group and scroll to **Brain structure**.
3. Click **Normalise the selected brain**, then confirm the dialog, which explains it moves `Javis/agents`→`agents`, `Javis/workflows`→`workflows`, `Memory`→`memory`, with a git backup.

The operation is safe: it only moves when the destination folder does not exist yet, never overwriting. It folds `Javis/agents` into `agents/`, `Javis/workflows` into `workflows/`, `Memory` into `memory/`, and moves old skills from `.claude/skills` into `skills/` (including the disabled-skill branch, so skills you turned off do not come back on).

## `attachments/` and `inbox/` are cache, not storage

This is the rule most likely to lose data if you do not know it in advance. Since version 0.9.247, Javis treats these two folders as a **cache**: material passing through, not knowledge.

- Files in those two folders older than **30 days** are cleared automatically. If total size exceeds the **300MB** ceiling, Javis clears oldest first until it is back under the ceiling.
- `.md` notes that happen to sit in those folders are spared and never cleared.
- Javis sweeps every 6 hours. The temporary stage folder (where a file you just pasted into the chat box lands) has its own shorter limit: **3 days**.
- Both folders are **outside the brain's git**, so they do not travel with the GitHub backup and do not bloat repo history.
- An expired image reappearing in a conversation shows as a grey dashed box reading **"Image expired"** instead of a broken-image icon.
- To turn automatic clearing off entirely, set `enabled: false` under the `media` key in `settings.json`. The day and size thresholds are configured there too.

The practical conclusion: move documents you want to keep long term into `sources/` or `wiki/`, do not leave them in `attachments/` or `inbox/`. Details in [File manager](05-file-manager.md).

## Long-term memory: making Javis "remember you"

The living memory sits at `memory/` inside the selected brain and contains:

- `memory/MEMORY.md`: the index, one line per memory. This file is preloaded ahead of every question, so Javis always has a baseline memory of you.
- `memory/facts/*.md`: the detail of each memory, one file per fact.
- `memory/conversations/YYYY-MM-DD.md`: raw conversation logs, the raw material for learning.

Javis sorts memories into 4 kinds: information about you (`user`), how you like to work (`preference`), facts about the business (`business`), and settled decisions (`decision`).

### The MEMORY.md index has a context ceiling

Because `MEMORY.md` is loaded into **every** chat turn, it has a ceiling of about **20,000 characters** (change it with the `JAVIS_MEMORY_INDEX_MAX` environment variable). When a thickening brain goes over the ceiling, Javis steps down gradually, favouring keeping the memory count intact:

1. Shorten each line's description to 100 characters, then to 60.
2. Keep only the title and file path, dropping the description.
3. Only as a last resort drop lines, and when it does Javis states how many memories are not listed plus where to read on in `Memory/facts/`.

So no memory is lost, the index just displays more tersely; the full detail stays in `memory/facts/` and Javis can read it at any time.

### Conversation logs are masked for secrets before being written

Before writing into `memory/conversations/`, Javis masks anything that looks like a secret you happened to paste into chat: API keys (`sk-`, `xai-`, `gsk_`, `hf_`, `tvly-`), GitHub tokens (`ghp_`, `gho_`, `github_pat_`), Google keys (`AIza`), JWTs, Telegram bot tokens, the `Authorization` header, and passwords inside database connection strings. They are replaced by a shortened form like `sk-abc...wxyz` or `***`.

On top of that, any message longer than 4,000 characters has its middle cut out (keeping the first 2,800 and last 1,000 characters) with a line stating how much was cut, so the log does not balloon.

Two more things worth knowing:

- Conversations over **Telegram** are also written into `memory/conversations/` just like web chat, and also feed the self-learning loop. See [The Telegram channel](11-telegram.md).
- The `memory/conversations/` folder is in the brain's `.gitignore`, so raw logs do **not** reach the GitHub backup. Git only versions distilled knowledge: `facts/`, `wiki/`, `skills/`, `MEMORY.md`.

### Seeing how many memories were learned

The memory count is on the **Metrics** line of the **Self-learning** page (**Brain** group), shaped like `Metrics · Memories: 87 · Wiki: 42 · MEMORY.md: 18363B ...`. The "Memories" number is exactly the file count in `memory/facts/` for the selected brain; switch brains and the number follows.

The old "LONG-TERM MEMORY" widget in the chat column has been removed; everything about learning and memory now lives on the Self-learning page.

### Forcing Javis to remember something

While chatting, just say it plainly:

- "remember this"
- "make a note that ..."

When you use those phrases, Javis is required to create a new memory immediately: it writes a file in `memory/facts/` and adds a line to `MEMORY.md`. For example "Remember this: my shop is closed on Sundays" is stored as a `business` fact.

Javis only records durable, memorable things. It skips the transient and does not duplicate an existing memory (a duplicate updates the old file).

### Learning from conversations (the consolidation loop)

This is the loop that makes Javis smarter over time: re-read recent conversations, extract new facts, merge duplicates, drop memories that are now wrong, and **distil reusable concepts into the Wiki**.

The loop now runs automatically at the server layer after each chat turn (with a debounce delay), through a read-only, isolated learning process; the writer is trusted code, not the AI. It is on by default.

The key point of this loop: Javis clearly separates two things. Facts about you and the business go to `memory/facts/`. Reusable concepts, frameworks and procedures are distilled into Wiki pages (with `[[wikilink]]`). Each in its own place, which is how the knowledge graph thickens rather than getting mixed up with personal notes.

Turning it on and off, choosing the write mode, choosing what to learn, learning now, seeing "what Javis taught itself", and undoing one learning run: all on the **Self-learning** page. See [Self-learning](22-self-learning.md).

## INGEST: digesting documents into knowledge

INGEST is the process that turns a raw file (an article, a screenshot, a note) into a source in `sources/`, and from there distils it up into the Wiki. The result: Javis summarises, extracts insight, writes the Wiki and may suggest tasks.

### How to use it (step by step)

1. Open the chat box (the **Javis** screen or the **Chat** page).
2. Drop a file into the chat input (drag and drop, the drop zone reads "📎 Drop files here → saved to Sources"), or click the paperclip attach button next to the input (tooltip "Attach a file (image, text, document) → saved to Sources"). Images and text files both work. The file uploads and waits in the staging area.
3. By default Javis **only reads the file and answers**, saving nothing anywhere. If you just want a quick summary, type your question normally.
4. To make Javis save and digest it, say one of these phrases in the message: **"save to source"**, **"ingest"**, or **"write to the second brain"**.
5. Javis then:
   - For a text file: reads it fully and creates a clean `.md` file in `sources/` with source frontmatter.
   - For an image: reads and describes the image content, creates the `.md` in `sources/`, moves the original image into `attachments/` and embeds it back.
6. From that source, Javis extracts insight and updates the Wiki, and may propose tasks if the document opens up work to do.

Remember the cache rule above: the original image in `attachments/` expires after 30 days, while the `.md` in `sources/` stays forever. That is exactly why you should ingest rather than just drop a file and leave it.

### Letting Javis process a batch of sources on a schedule

If you have piled up unprocessed sources, you can hand Javis a **loop** running in the background:

1. Go to **Recurring jobs** (**Work** group on the rail).
2. Click **+ Add job**.
3. Under **Job type**, keep **🔁 Loop**.
4. Set a **Name** (for example "Digest new sources").
5. Fill in **Task description (each cycle Javis does exactly this)**, for example: "Each cycle read 1 unprocessed source in sources and propose the Wiki page to create".
6. Choose the **Mode**: **Suggest (read only)** for suggestions only, or **Auto (safe)** to let it write draft files in the brain.
7. Set the **Cycle (minutes, minimum 5)**, choose the **Brain (where the job is stored)**, then click **💾 Save**.

Details of each mode, how to enable and disable, reading the log and safety tips: [Recurring jobs and reminders](08-recurring-jobs.md).

## Wiki linting (LINT)

Once the Wiki is thick, you should audit it periodically. LINT only **reads and lists problems**, it never fixes anything, so it is very safe.

The standalone "LINT Wiki" button of old is gone. LINT now runs inside the **Curator** on the **Self-learning** page (**Brain** group), described on screen as: clean the index, LINT the Wiki (suggestions only), compact MEMORY.md. Nothing is deleted.

1. Go to **Self-learning** in the **Brain** group on the rail.
2. Click **🧹 Curator now** to run one pass immediately. The button changes to "Cleaning...".
3. Or click the status button under **Curator (periodic maintenance)** to flip it from "○ Off" to "● On", then click **💾 Save configuration** so Javis runs it on a cycle (the Curator is off by default, and the cycle when on is 24 hours).

The result changes nothing, it only pours into the **Learning log** block as "Wiki LINT (suggestions, nothing changed)". It looks for: duplicate pages, pages nobody links to (orphans), broken `[[...]]` links, unresolved contradictions, and thin areas of knowledge (gaps). Read the list and decide yourself what to fix, do not let Javis fix everything at once.

## Quick reference of buttons and states

| You want to | Go to | Click |
|---|---|---|
| Switch the working brain | Top bar, left corner | The brain selector (`🧠 Brain name · note count`) |
| Create a new brain | Top bar, left corner | ➕ |
| Delete a brain (30-day trash) | Top bar, left corner | 🗑, then type the exact brain name |
| Point at an existing Obsidian vault | Top bar, left corner | 📁 |
| Remove an external folder from the menu | Select the external folder, then click | 🗑 (does not touch the disk) |
| See memory count and Wiki page count | Brain group → Self-learning | Read the **Metrics** line |
| Force one learning pass now | Brain group → Self-learning | **▶ Learn now** |
| Lint the Wiki | Brain group → Self-learning | **🧹 Curator now** |
| Undo the latest learning run | Brain group → Self-learning | **↶ Undo the latest learning run** |
| Back the brain up to GitHub | Brain group → Self-learning | The **⇅ Sync brain with GitHub (two-way)** block |
| Browse/edit files in the brain | Brain group → Files | The folder tree on the left |
| Assign a loop that digests sources | Work group → Recurring jobs | **+ Add job** |
| Normalise brain folders | System group → Settings | **Normalise the selected brain** |

## Tips

- **Split brains by purpose.** One brain for business and one for personal keeps the knowledge graph and the memory tidy and less noisy.
- **Say "remember this" for what is durable.** Product niche, main sales channel, pricing decisions. Do not record the transient (busy today, a message just sent), which Javis skips anyway.
- **To digest a document you must say so.** Dropping a file is not enough to save it, you have to add "save to source" or "ingest". Ask an ordinary question and Javis just reads and moves on.
- **Memory travels with the folder.** Change machines or move to a VPS and you only need to point Javis at the right brain folder for every memory and Wiki page to be intact.
- **Do not hand-roll git to sync.** Javis already has the **⇅ Sync brain with GitHub (two-way)** block on the Self-learning page: it pushes the whole brains folder to a private repo and pulls changes back from another machine. Step by step in [Backing the brain up to GitHub](18-github-backup.md).
- **See the knowledge visually** in the [Knowledge graph](03-knowledge-graph.md): every source and Wiki page is a node, `[[...]]` links are the edges.

## Common problems

- **The "LONG-TERM MEMORY" section or the "Learn from conversation now" button is missing from the chat column.** That widget was removed. Everything about learning and memory is now on the **Self-learning** page (**Brain** group): the memory count on the **Metrics** line, manual learning through **▶ Learn now**.
- **The memory count is still 0 after a lot of chatting.** A memory is only written when durable, memorable information appears, or when you say "remember this", or after a learning pass runs. Small talk creates no memories. Also check on the Self-learning page whether self-learning is on and whether the write mode is **Write automatically**.
- **A dropped file never appears in Sources.** That is by design: reading only is the default. You have to include "save to source" or "ingest" in the message for Javis to create the `.md` in `sources/`.
- **Old images in a conversation turn into a grey "Image expired" box.** By design: `attachments/` is a cache and images over 30 days are cleared. Content already extracted into an `.md` in `sources/` at ingest time is still there.
- **You deleted the wrong brain.** It is not lost right away: the folder is in `brain-trash` inside Javis's state folder, named like `Brain name__20260729-153012`, kept 30 days. The safe way to recover: click ➕ and recreate the brain with **exactly the old name** (this removes the tombstone so the brain is not deleted again on sync), then copy the contents from the trash into that folder.
- **A brain reports a non-standard structure.** Go to Settings, the Interface and Brain group, the Brain structure item, and click **Normalise the selected brain** so Javis collapses the folders.
- **Memories did not follow to a new machine.** Check that you pointed at the right brain folder, the one containing `memory/`. Memory lives in the folder, not in the account. To keep two machines matched automatically, turn on GitHub sync, see [Backing the brain up to GitHub](18-github-backup.md).
- **After a GitHub backup, conversation logs and images are missing.** By design: `memory/conversations/`, `attachments/` and `inbox/` are all outside the brain's git. The backup only keeps distilled knowledge.

## Related

- [Self-learning](22-self-learning.md) - turning self-learning on and off, write modes, the Curator, undoing a learning run.
- [File manager](05-file-manager.md) - browsing and editing brain files directly, cache details.
- [Backing the brain up to GitHub](18-github-backup.md) - two-way sync of every brain across machines.
- [Knowledge graph](03-knowledge-graph.md) - seeing Sources and Wiki as a network.
- [Skills](06-skills.md) - skills living in the brain's `skills/`.
- [Agents and Workflows](07-agents-and-workflows.md) - the operating layer in `agents/` and `workflows/`.
- [Recurring jobs and reminders](08-recurring-jobs.md) - assigning a loop that digests sources on a schedule.
- [Tasks and Dataview in notes](19-tasks-and-dataview.md) - the bullet journal set inside the brain.
- [.env configuration](16-env-configuration.md) - the `BRAINS_DIR`, `JAVIS_STATE_DIR` and `JAVIS_MEMORY_INDEX_MAX` variables.
