# Tasks and Dataview in notes

*[Tiếng Việt](../19-task-va-dataview.md) · **English***

Since version 0.9.216, notes in a Javis brain are far more "alive" in the Obsidian sense: a `- [ ]` checkbox in a note is **clickable and saves itself**, and a ` ```dataview ` block **actually runs** inside the dashboard, showing task lists, note lists and summary tables pulled from the whole brain. Both features are inspired by two well-known Obsidian plugins, **Tasks** and **Dataview**, reimplemented compactly by Javis with no need to install Obsidian or any plugin.

## 1. Clickable task checkboxes

### What the feature is

In a markdown file, a task line written in the standard syntax:

```markdown
- [ ] Call customer A back
- [x] Close the steel batch quote
```

Javis used to display these boxes decoratively, and ticking one meant opening Source mode and hand-editing `[ ]` into `[x]`. Now clicking the box is enough: the tick appears, the text is struck through, and **the file is saved immediately**, with no 💾 Save button needed.

### Where you can tick

- **The Files page** (**Brain** group on the left nav rail): open an `.md` file and stay in **Edit** mode (the rendered view, the default). Clicking a checkbox ticks it and saves.
- **The file editor opened from chat** (clicking a file link in one of Javis's answers): exactly the same, ticking saves.
- **Inside a chat message**: checkboxes are display-only and not clickable. The reason: chat content is not bound to any file to write back to.
- **In dataview block results**: clickable, writing straight into the source file holding that task (see part 2).

### Typing tasks quickly with the suggestion menu (Obsidian style, condensed)

In a note's **Edit** mode, Javis offers suggestions like Obsidian's Tasks plugin but trimmed down so it is not overwhelming:

1. Type `- [ ]` at the start of a line then **press space**, and the line becomes a real task with a checkbox. Inside a bullet list you only need `[ ]` then space.
2. Standing at the **end of a task line**, press space to open a 6-item menu: 📅 due date, ⏳ scheduled date, 🛫 start date, and the 3 priority levels ⏫🔼🔽.
3. Choose a date item and a second menu opens: **Today / Tomorrow / This weekend / Next week / Pick a date…** (opening a calendar). Once chosen, Javis inserts `📅 2026-07-28` straight into the line in proper obsidian-tasks format, so every query block understands it.

Navigate with the up and down arrows plus Enter, or with the mouse. Esc closes it, and typing on dismisses the menu so it never gets in the way of writing.

### Date and priority markers (Tasks plugin style)

Javis understands the emoji markers the obsidian-tasks plugin uses, written inline in the task:

| Marker | Meaning | Example |
|---|---|---|
| 📅 | Due date | `- [ ] Submit the report 📅 2026-08-01` |
| ⏳ | Scheduled date | `- [ ] Draft the slides ⏳ 2026-07-30` |
| 🛫 | Start date | `- [ ] Tet campaign 🛫 2026-12-01` |
| ✅ | Completion date | added automatically when ticked |
| 🔺 ⏫ 🔼 🔽 ⏬ | Priority from highest to lowest | `- [ ] Handle the complaint ⏫` |

Two automatic behaviours matching the Tasks plugin:

- A task **with a date marker** (📅/⏳/🛫/🔁) gets `✅ 2026-07-28` (that day) appended when ticked; unticking removes the ✅ date.
- An ordinary checklist item (no markers at all) only turns `[ ]` into `[x]` when ticked, adding **nothing** to your text.

A task with a 📅 that is past due shows a red badge in dataview results so it catches the eye.

## 2. The dataview block, querying notes like a database

### What the feature is

Insert a code block with the `dataview` language into any note:

````markdown
```dataview
TASK WHERE !completed
```
````

When you open that note in Javis (or when Javis pastes such a block into a chat answer), the block is no longer shown as code but **runs a real query** across every `.md` note in the selected brain and draws the result: unfinished tasks, grouped by file, each tickable.

Three query kinds:

- `TASK` - lists `- [ ]` / `- [x]` task lines, grouped by file, with working checkboxes.
- `LIST` - lists notes (one link per line, clicking opens the note).
- `TABLE` - a table: one row per note, columns taken from frontmatter or file information.

### Supported clauses

Write them in Dataview's familiar order: the query kind on the first line, then optional `FROM`, `WHERE`, `SORT`, `LIMIT`.

**FROM, narrowing the data source:**

````markdown
```dataview
TASK FROM "01 - Daily"
```
````

- `"folder"` - only notes in that folder (subfolders included).
- `#tag` - only notes carrying that tag (in frontmatter or written as `#tag` in the body).
- Combined: `FROM "05 - Work" OR #project`, `FROM "notes" AND -#archive` (a `-` or `!` excludes).
- With no `FROM`, the whole brain is scanned.

**WHERE, filtering by condition:**

````markdown
```dataview
TASK WHERE !completed AND due <= date(today)
```
````

- With `TASK`, the available fields are: `completed` (ticked or not), `text` (the task content), `due`, `scheduled`, `start`, `done` (dates shaped `2026-08-01`), `priority` (0 highest, 3 default, 5 lowest), `tags`, `file.name`, `file.folder`.
- With `LIST` / `TABLE`, use the note's frontmatter field names directly (`status`, `type`...), plus `tags`, `file.name`, `file.folder`, `file.mtime`.
- Comparisons: `=`, `!=`, `>`, `<`, `>=`, `<=`. Dates compare correctly because they share the `YYYY-MM-DD` format.
- `date(today)`, `date(tomorrow)`, `date(yesterday)`, `date("2026-12-31")`.
- `contains(text, "customer")` - a string containing a string; `contains(tags, "#sales")` - an array containing an element.
- Combine `AND` / `OR` / `!` / parentheses `( )` freely.

**SORT and LIMIT:**

````markdown
```dataview
TASK WHERE !completed SORT due ASC LIMIT 10
```
````

- `SORT field ASC` (ascending, the default) or `DESC` (descending).
- `LIMIT n` - at most n results.

**Columns in TABLE:**

````markdown
```dataview
TABLE status AS "Status", file.folder AS "Folder"
FROM #project
SORT file.mtime DESC
```
````

- List the columns comma separated, with `AS "Column name"` for a nicer heading.
- The first column is always a link to the file; to drop it write `TABLE WITHOUT ID ...`.

### Ticking tasks right in the results

A `TASK` result has checkboxes just like the note does. Ticking one makes Javis write straight into the **source file** holding that task line, even while you are standing in a different summary note. There is a safety rail: if the source file was just edited (the task line is no longer where it was), Javis re-locates the correct line by content; when it cannot be sure it reports "The file changed" and **writes nothing blindly**, so reloading the page and ticking again is all it takes.

### Practical examples

Overdue tasks, most urgent first:

````markdown
```dataview
TASK WHERE !completed AND due < date(today) SORT priority ASC
```
````

A table of running projects, most recently edited first:

````markdown
```dataview
TABLE status AS "Status", deadline AS "Due"
FROM "03 - Projects"
WHERE status != "done"
SORT file.mtime DESC
```
````

Notes mentioning one customer:

````markdown
```dataview
LIST WHERE contains(file.name, "Chị Nga") OR contains(tags, "#chi-nga")
```
````

Tasks in one note or Daily folder this week:

````markdown
```dataview
TASK FROM "01 - Daily" WHERE !completed LIMIT 20
```
````

### The ```tasks block, written in the Tasks plugin language

If you are used to the obsidian-tasks syntax, use it directly, because Javis also understands the ` ```tasks ` block:

````markdown
```tasks
not done
due before today
sort by due
limit 20
```
````

Each line is one condition and the lines AND together (matching the original plugin's semantics). Supported lines:

- `done` / `not done`
- `due|scheduled|starts|done|created before|after|on <today|tomorrow|yesterday|YYYY-MM-DD>` (`due today` works too; `happens` is approximated as `due`)
- `has due date` / `no due date` (likewise for scheduled/start/done/created)
- `description includes <text>` / `description does not include <text>`
- `path includes <text>` / `path does not include <text>`
- `tag includes #x` / `tags do not include #x`
- `priority is [above|below] high|medium|low|none|highest|lowest`
- `sort by due|priority|description|path|... [reverse]`, `limit N` / `limit to N tasks`
- `group by ...`, `hide ...`, `show ...`, `short mode`, `explain` - silently ignored (they do not affect the result)

An unsupported line (`filter by function`, say) makes the block show a warning naming the skipped line, while the remaining lines still run normally.

### The "+ Task" button, adding tasks deliberately

Every block producing a task list (` ```tasks ` or `TASK`) has a **+ Task** button in its top right corner. Clicking it shows a content field plus an optional due-date picker, and Enter or clicking Add finishes it. The new task is written into the file **`Task Inbox.md`** in the brain's dashboard folder, with `📅 due` if you picked a date, and every block on the page refreshes at once. Task Inbox is a task mailbox: add quickly there, then move items into the right Daily/Weekly note when you have time.

That file is **only created the first time you add a task**. Never use the "+ Task" button and it never appears, so the Dashboard folder has no empty file sitting around.

Javis **detects** the dashboard folder rather than hard-coding a name: any top-level folder of the brain named `dashboard` (case insensitive, allowing a numeric prefix like `00 - Dashboard`, `01 - dashboard`, `02_Dashboard`) receives new tasks. Only when a brain has no matching folder does Javis create one named `00 - Dashboard`.

### The default Dashboard page

The dashboard folder is part of the brain's standard structure: a new brain gets `00 - Dashboard` ready-made with a seed file `Dashboard.md` (task blocks for overdue, today, upcoming and no due date). An older brain missing it gets a create button in the vault-structure banner. The seed file is only created when absent, so anything you edit is left alone.

`Task Inbox.md` is **not** part of the seed set (since 0.55.17): it only appears when you first click "+ Task". If an older brain already has that file and you do not use it, just delete it, Javis will not recreate it.

### What is not supported

This is a "lite" build that deliberately covers only the most-used parts. Not there yet:

- `dataviewjs` (blocks running JavaScript), where the block shows a clear notice rather than staying silent.
- `FLATTEN`, arbitrary `GROUP BY` (TASK already groups by file), and the `dur(...)` function for adding and subtracting durations.
- `[[link]]` inside `FROM`.

On unsupported syntax the block shows an error message with the query verbatim so you can fix it, and never breaks the page.

### Performance and technical limits

Dataview is built to stay smooth on a large vault, with several automatic savings:

- **Warm-up at startup**: the server prebuilds the index for every brain right after boot (in the background), so the first dashboard opening does not wait for the whole vault to be parsed.

- **An incremental cache on the server**: the note index is held in RAM, and each call only re-reads and re-parses the files that changed (comparing modification time plus size), reusing what it already has for the rest. On a vault of thousands of notes: the first call after a server start is a little slow, and from the second it is a few tens of milliseconds.
- **ETag / 304**: with no note changed, the server returns an empty payload instead of resending the whole index, and the browser reuses its copy.
- **Narrowing with FROM**: a query using `FROM "folder"` scans only that branch instead of the whole brain. So **write a specific FROM folder** whenever you can; if you only care about the journals, `FROM "01 - Daily Log" OR "02 - Weekly Log" OR "03 - Monthly Log" OR "04 - Future Log"` is far faster than scanning the vault. A `FROM` with only a `#tag` still has to scan the whole brain (tags are scattered everywhere).

The remaining limits:

- The index holds at most **20,000 notes** per brain, skipping `.md` files over 1MB and hidden folders (`.git`, `.obsidian`, `.trash`...).
- The browser keeps results for about **15 seconds** before asking the server again: if you just edited a note and the block has not updated, wait a few seconds then reopen the note holding the block. Ticking a task updates immediately with no wait.
- Tasks **inside a code block** in another note are not picked up by mistake (sample code containing `- [ ]`, for instance).

## Troubleshooting

- **Clicking a checkbox does nothing**: check you are in **Edit** mode (the rendered view) rather than **Source**; in chat, checkboxes are display-only by design. If it still does nothing, the server is probably older than 0.9.216, so update and reload the page (Ctrl+Shift+R).
- **A dataview block sits on "Running query…" forever**: the server has no `/files/mdindex` API (an old build). Update Javis then restart the server.
- **The result is empty although tasks certainly exist**: check the `FROM`, since a folder name must be verbatim (with diacritics and numeric prefix, for example `"05 - Việc"` rather than `"Việc"`); a tag must carry the `#`.
- **It reports "The file changed, reload then tick again"**: the source file was just edited elsewhere (by you or by Javis). Reload the page so the block runs against the new data, then tick again.

See also: [File manager](05-file-manager.md) (opening and editing notes), [Second Brain: memory, Wiki, INGEST](13-second-brain.md) (brain structure), [Troubleshooting and FAQ](17-troubleshooting.md).
