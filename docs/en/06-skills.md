# Skills

*[Tiếng Việt](../06-skills.md) · **English***

A skill is a packaged capability for Javis: a written instruction that makes the AI do one kind of job your way (writing sales emails, building a sales page, deep research). When you say something matching the skill's description, Javis pulls that instruction in by itself, so you never paste the procedure again.

This page covers managing skills in the dashboard: browsing by group, searching, enabling and disabling, adding, editing, deleting, exporting and importing, calling one by hand from the command menu, and asking Javis to write a skill for you.

## What this feature is

A skill in Javis is a folder containing a `SKILL.md` file at `skills/<slug>/SKILL.md` inside the selected brain (Javis mirrors it into `.claude/skills` so Claude Code can load it natively; older brains that keep skills in `.claude/skills` are migrated into `skills/` automatically). That file has 3 important frontmatter fields:

- `name`: the display name of the skill.
- `description`: a short summary, and this is the **trigger** that decides WHEN the skill activates. This field has its own rules, so read the section below before filling it in.
- `group`: a group name so the dashboard can tidy skills together (Marketing, Sales, Content...). This field is required; leaving it empty drops the skill into "Chung" (General).

The rest of the file is the detailed instruction the AI follows when the skill runs.

The canonical copy lives at `skills/<slug>/SKILL.md`, which is exactly what the dashboard shows and what Javis loads through the router. Javis also keeps a **mirror** at `.claude/skills/<slug>` for Claude Code's native loading. The mirror is identical except for one thing: if `description` is longer than 150 characters, the mirror is trimmed to 150 with an ellipsis (the copy in `skills/` keeps your full text). That only happens with skills imported from an external package or written by hand through the Files page, because skills saved through the form are blocked earlier.

## The `description` rules (read before creating a skill)

This is where people get stuck without knowing why. When you click **💾 Save**, the server checks `description` and **refuses to save** if it breaks either rule:

**1. At most 150 characters.** This is not cosmetic. Javis truncates the description at exactly 150 characters when injecting it into the system prompt and into the `javis_use_skill` tool description, so the excess is lost silently and the skill cannot be routed. The rejection message says exactly that, and tells you to move trigger examples into a `## When to use` section in the body.

**2. No hollow opening phrases.** Blocked openings include "Activate when...", "Use this skill when...", "This skill is used for..." and their Vietnamese equivalents. Every skill opens the same way, so that phrase burns character budget without distinguishing anything. The rejection message suggests the right shape: state the capability directly, for example "Summarise meeting minutes into a task list."

The right way: one sentence stating what the skill **can do**, under 150 characters. Long trigger examples, keyword lists and detailed situations belong in a `## When to use` section in the **body** of `SKILL.md`, where nothing is truncated and which is only read once the skill is loaded. Put briefly: the description is for FINDING, the body is for DOING.

These rules apply both to the dashboard form and to skills proposed by the **Self-learning** page (a violating skill is blocked and listed as skipped).

## How triggering works

A skill activates on its `description` (and you can also call it by hand, see the next section). When you type or say a request, Javis matches it against the `description` of every enabled skill and loads the matching instruction. On Claude Code that is a native load; on other engines Javis injects the skill list into the system prompt and loads through the `javis_use_skill` tool.

So a skill's quality depends heavily on how you write `description`. A description that states the capability and the right keywords fires at the right time. A vague description either never fires or fires on the wrong thing.

Note: skills work on **every engine**. Claude Code loads natively; ChatGPT/Codex, OpenRouter and the OpenAI/Anthropic/Google Gemini APIs use skills through the router (Javis injects the skill list into the system prompt) plus the `javis_use_skill` tool. See [Models & engines](10-models-and-engines.md) for the per-engine details.

## Calling a skill by hand: the "/" command menu

You do not always have to wait for the trigger. Typing **`/`** in the chat opens a menu right above the input:

- Three session commands lead: **`/new` New conversation**, **`/reset` Reset session**, **`/stop` Stop**.
- Below them is the skill list for the selected brain, each row showing `/slug`, the skill name and its description.

How to use it: keep typing to narrow the list (slug matches first, then names), use **arrow up/down** to move, **Enter** or **Tab** to confirm, **Esc** to close. Clicking a row works too.

Picking a skill fills the chat box with `/slug ` and leaves the cursor waiting; type the request and press Enter. Javis turns that into a prompt: "Use the skill `<slug>` for this request: ... If no skill by that name exists, just handle my request normally." Picking a session command runs it immediately, with no Enter.

On Telegram, sending `/<slug>` (with content after it if needed) produces the same shape. One exception: while the engine is OpenRouter, Javis replies that skills need the Claude CLI engine and tells you to send /cli first.

## The router's 20-skill ceiling

The skill list Javis injects into the system prompt and into the `javis_use_skill` tool description is **cut at 20 skills**. The rest collapses into a single line: "…(+N more skills, see `Javis/index.md`)".

The consequence: if your brain enables more than 20 skills, skills 21 and beyond are **not in the router**, so on router-based engines (ChatGPT/Codex, OpenRouter, OpenAI/Anthropic/Google Gemini API) they will not self-activate. They are still intact and still loadable: calling `/slug` by hand works normally, because the `javis_use_skill` tool accepts any enabled slug, not just the 20 listed.

The fix: turn off skills you do not use so the 20 router slots go to the ones you actually want Javis to catch on its own.

## System skills versus your skills

Javis has 2 kinds of skill:

- **System skills** (cards labelled "system"): default Javis OS features, currently 6:

  | Slug | What it does |
  |---|---|
  | `javis-builder` | Create or edit a Javis capability: agent, skill, workflow, loop, plugin |
  | `ingest-source` | Digest a raw source into the Second Brain, distilled into wiki knowledge |
  | `query-wiki` | Mine knowledge in the Second Brain, answering with citations |
  | `lint-wiki` | Audit wiki health and return a list of issues |
  | `notes` | Save the current message verbatim into `sources/` (images included), distilling it into the wiki when it deserves it |
  | `html-to-webcake` | Turn an HTML page into a `.pke` file that opens in the Webcake page builder |

  The originals live in the app installation folder, not in the brain, so they are **present in every brain** and **update themselves when you update Javis OS**. They cannot be deleted from the dashboard (deleting the files by hand only makes them reinstall on the next start); to stop using one, **disable** it like any skill, and that disabled state survives every update.
- **Your skills**: created with + Skill, through chat, imported from a `.zip`, or proposed by the Self-learning page. These are brain data: switching brains switches the skill set, and app updates never touch them.

You can still **Edit** a system skill. When you do, the copy in the brain becomes yours: Javis keeps your edit and stops updating over it. To go back to the standard version (with automatic updates), delete that skill folder from the brain's `skills/` (through the Files page) and restart; the newest system version is reinstalled clean.

## How a Skill differs from a Plugin

These two are easy to confuse because both sit in the **Capabilities** group in the navigation.

| | Skill | Plugin |
|---|---|---|
| Nature | **KNOW-HOW**: a file of instructions the AI reads and follows | **Real Python CODE** running inside the server process |
| What it produces | A procedure, a template, a set of rules | A new **tool** every engine can call, and/or a **hook** running around each tool call |
| Where it lives | `skills/<slug>/SKILL.md` in the brain | The `plugins/<slug>/` folder (`plugin.yaml` + `plugin.py`) |
| How to enable | Tick the checkbox on the card | Plugins you install also need `JAVIS_ENABLE_USER_PLUGINS=true` and a restart |

How to choose: if you need **instructions** for working with existing tools, write a Skill. If you need a **specific Python action** no source covers (a computation, a data transformation, a simple API call), write a Plugin. And if it is an external data source that already has a server, connect an MCP on the Connections page rather than writing a plugin. Details in [Plugins](20-plugins.md) and [Connections & business data](09-connections-and-business-data.md).

## Where to find it in Javis

Open the dashboard (port 7777 by default), look at the left navigation, open the **Capabilities** group and click **Skills**. That group has 4 items: Agents, Skills, Workflows, Plugins.

The page header reads **Skills** with a status line such as "3/5 enabled · source `skills/`". That tells you how many skills are on out of the total, and reminds you that the source is the current brain's `skills/` folder.

To the right of the title are two buttons: **⤒ Import** (bring an external skill package in) and **+ Skill** (create one).

If the brain has no skills yet, the page reads "This brain has no skills. Click + Skill to create one (saved into `skills/` and grouped)".

## The Skills screen layout

Once skills exist, the screen splits in two:

- **Group column (left):** lists groups, starting with **All**, then each group alphabetically. Each row shows how many skills are in it. Click a group to filter the list down to it.
- **Skill list (right):** on top sit the current group title, how many skills are showing, and a **Find a skill…** box. Below are the skill cards.

Each skill card shows:

1. An enable/disable checkbox at the start.
2. The skill name (with a 🧩 icon). System skills also carry a **system** badge.
3. The `description` line.
4. A last line: 📂 group name · slug. Skills coming from the `.agents` folder add a ".agents" note. That line also ends with usage information (see below).

Disabled skills render dimmed. Hovering a card reveals action buttons on the right: **Edit**, **⤓ Export**, **Delete**. **System** skills only have **Edit** (they cannot be exported or deleted). On screens under 860px those buttons are always visible at the bottom of the card, because phones have no hover.

### The "used N times" and "no usage seen" line

At the end of the group · slug line, Javis shows one of two labels:

- **"used N times, last on <date>"** when the skill has been loaded at least once.
- **"no usage seen"** (dim, italic) when 30 days have passed with no usage signal.

This is a **one-way positive signal** and needs to be read correctly so a skill is not condemned unfairly: Javis can only count loads that go through the `javis_use_skill` tool. Claude Code loading a skill natively through `.claude/skills` does **not** pass the counter. So "used N times" is certainly true, while "no usage seen" only means there is no evidence, **not** that the skill is useless. Hovering the label shows this explanation. Nothing is disabled or deleted based on this label; you decide.

The figures are stored in `Javis/skill-usage.json` in the brain, separate from `SKILL.md`, so using a skill does not create junk changes in the brain's git history.

## Searching skills

Type into the **Find a skill…** box at the top of the list. Javis filters as you type, matching the keyword against the name, description and slug. The search filter stacks on the group filter: while a specific group is selected, the search only runs inside it; click **All** first to search everything.

## Enabling and disabling one skill

1. Open the **Skills** page.
2. Find the skill you want to change.
3. Click the checkbox at the start of its card. Ticked is on, unticked is off.

When you disable a skill, Javis moves its folder into a separate place named `.disabled` (the path becomes `skills/.disabled/<slug>`) and removes the mirror in `.claude/skills`. That is a **real** disable: a skill inside `.disabled` is no longer loaded by any engine, so Javis stops using it. Enabling moves the folder back to `skills/<slug>` and mirrors it again for Claude's native path.

Enabling and disabling never deletes content. You can turn a skill off temporarily and back on at any time without losing what you wrote.

If something goes wrong, Javis reports that the state could not be changed, along with the reason.

## Adding a skill (step by step)

1. On the **Skills** page, click **+ Skill**.
2. Fill in the form:
   - **Skill name**: something memorable, for example "Write sales emails".
   - **Group**: type a group name, for example "Marketing". This field suggests groups you already use, so you can click one and stay consistent. Do not leave it empty (it would land in "Chung").
   - **Description (decides when the skill activates)**: one sentence stating what the skill does, **under 150 characters**, not opening with "Activate when..." (see "The `description` rules" above). Breaking the rules makes the server refuse and the skill is not saved.
   - **Content (SKILL.md, the instructions for the AI)**: write the detailed instruction the AI follows (steps, templates, rules). This is where the `## When to use` section with full trigger examples belongs. Leave it empty and Javis generates a minimal body from the name and description.
3. Click **💾 Save**. To abandon it, click **Cancel**.

On save, Javis derives the **slug** from the name: lowercase, Vietnamese accents removed, spaces replaced by hyphens (so "Viết email" becomes `viet-email`). An accent-free ASCII slug makes skill loading more reliable on every engine. The `skills/<slug>/SKILL.md` folder is created automatically; you never create files by hand.

## Editing a skill

1. Hover the skill card and click **Edit**.
2. The form reappears with the skill's current content (name, group, description, SKILL.md content).
3. Change what you need.
4. Click **💾 Save**.

Editing keeps the slug and folder and only overwrites `SKILL.md`. This is where you tune `description` so the skill triggers more accurately, or add a step to the instructions.

Editing a **disabled** skill keeps it disabled after saving; Javis does not switch it on.

## Changing a skill's group

The simplest way: click **Edit**, change the **Group** field, then **💾 Save**. The group is only a label in the frontmatter; changing it does not affect whether the skill is loaded, only where it appears in the group column.

## Deleting a skill

1. Hover the skill card and click **Delete**.
2. Javis asks to confirm: `Delete skill "<name>"? The whole skills/<slug> folder will be removed.`
3. Agree to delete.

Deletion is final: the whole skill folder is removed from disk, with no recycle bin. If you only want to stop using it for now, **disable** it instead. System skills have no Delete button.

## Exporting and importing skills

- **⤓ Export** (on each skill card): downloads a `.zip` of that skill to send to someone else. **System** skills have no such button because every brain already has them.
- **⤒ Import** (top of the page, next to + Skill): pick a file to bring into the selected brain. It accepts `.zip` (a Javis package), a single `.md`, or a Claude `.skill` package (Javis recognises the `SKILL.md` inside and files it correctly). Javis asks first: "If an agent/skill/workflow with the SAME NAME exists, OVERWRITE it with the new one?" Click OK to overwrite, Cancel to keep the old ones and only import what is missing. Afterwards Javis lists what was imported and what was skipped.

Note: skill content is instructions the AI follows, so only import packages from sources you trust. Details on packaging with dependencies are in [Agents & Workflows](07-agents-and-workflows.md).

## Asking Javis to create a skill in words

You do not have to fill in the form. You can open the chat and ask Javis to create the skill, for example: "Create me a skill for writing Facebook captions for a cosmetics shop, triggering when I ask for sales captions." Javis writes `SKILL.md` and saves it in `skills/`. Chat basics are in [Chat & voice](02-chat-and-voice.md).

When creating a new skill, Javis is instructed to file it in the right group: it reads existing skills to see which groups you use, then picks the closest. Only when none fits does it create a new group, with a short domain name (Marketing, Sales, Content, Operations, Finance, AI, Productivity, Personal). That way new skills do not scatter into "Chung".

## Skills and Agents

On the **Agents** page, creating or editing an agent shows a **Skills** section listing available skills to tick and assign to that agent. Agents can only list skills once the brain has skills in `skills/`; if it has none, the section reads that the vault has no skills yet and that you can create the agent now and assign skills later. Details in [Agents & Workflows](07-agents-and-workflows.md).

## Quick reference: buttons and states

| What you see | Meaning / action |
|---|---|
| **⤒ Import** | Bring a `.zip` / `.md` / `.skill` package into the selected brain |
| **+ Skill** | Open the new skill form |
| Checkbox on the card | Ticked = enabled; unticked = disabled (moved in or out of `.disabled`) |
| **Edit** | Open the edit form |
| **⤓ Export** | Download the skill as a `.zip` to share (absent on system skills) |
| **Delete** | Remove the skill folder entirely (asks to confirm; absent on system skills) |
| **💾 Save** | Save the skill (create or overwrite) |
| **Cancel** | Close the form without saving |
| The **Find a skill…** box | Filter by name, description, slug |
| The **Group** column / **All** | Filter the list by group |
| The **system** badge | A skill that ships with the app, exists in every brain, can be disabled but not deleted |
| A dimmed card | The skill is disabled |
| The "x/y enabled" line | x skills on out of y |
| "used N times, last on …" | The skill was loaded through `javis_use_skill` N times |
| "no usage seen" | No usage signal for over 30 days; a hint, not a verdict |

## Tips

- Write `description` like a headline: state the capability directly, under 150 characters. Push every trigger example and keyword into `## When to use` in the body, where it is neither blocked nor truncated.
- Count the characters before saving. 150 is shorter than it feels, about two short sentences.
- One skill should do one clear thing. Overly broad skills trigger on the wrong requests; splitting them and putting them in the same group is easier to manage.
- Keep the number of enabled skills under 20 so all of them stay in the router. Turn off what you do not need.
- Use groups consistently. In the **Group** field, prefer the suggestions over inventing a new name, so the group column does not fragment.
- To try a skill you are unsure about, create it and **disable** it when unused, rather than deleting and recreating.
- To be certain a skill is used for a given job, call it by hand with `/slug` instead of hoping the trigger catches it.

## Common problems

- **You clicked 💾 Save but the skill does not appear in the list:** almost certainly `description` broke a rule (over 150 characters, or opening with "Activate when..."). The server refused to save and the page simply returned to the list without showing the error. Click **+ Skill** again, shorten the description under 150 characters, drop the hollow opening, and save again.
- **You created a skill but Javis never uses it:** check three things in order. One, is it **enabled** (card not dimmed, checkbox ticked). Two, does `description` state the capability. Three, does the brain have more than 20 skills enabled; if so, yours may have fallen outside the router, so disable some others or call it by hand with `/slug`.
- **The list is empty although you created skills:** make sure you are looking at the right brain. The source is the selected brain's `skills/`; switching brains switches the list.
- **Toggling reports that the state could not be changed:** usually folder write permissions or a locked folder. See [Troubleshooting & FAQ](17-troubleshooting.md).
- **A skill reads "no usage seen" although you know it runs:** that is normal. Javis can only count loads through `javis_use_skill`; Claude Code's native loading bypasses the counter. Do not delete a skill over that label.
- **A skill card has no Delete button:** it is a system skill. To stop using it, disable it.
- **You deleted one by accident:** deletion is final and cannot be recovered from the dashboard. Next time, disable rather than delete when you only want a pause.
- **The group fell into "Chung":** the Group field was empty when you saved. Click **Edit** and fill it in.

## Related

- [Agents & Workflows](07-agents-and-workflows.md) - assigning skills to agents, building step chains, exporting and importing with dependencies.
- [Plugins](20-plugins.md) - when you need a tool that runs real code rather than an instruction.
- [Models & engines](10-models-and-engines.md) - skills run on every engine; see the difference between native (Claude Code) and router (`javis_use_skill`).
- [Chat & voice](02-chat-and-voice.md) - asking Javis to create a skill in words, and the "/" command menu.
- [Self-learning](22-self-learning.md) - where Javis proposes new skills from past conversations.
- [Second Brain: memory, Wiki, INGEST](13-second-brain.md) - understanding the brain that stores skills.
