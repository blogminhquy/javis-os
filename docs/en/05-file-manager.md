# File manager

*[Tiếng Việt](../05-quan-ly-tep-tin.md) · **English***

The "Files" page is a file manager built into the Javis dashboard. You search for files, browse folders, open and edit text files (.md, .txt...) straight in the browser and save them, upload files, download files (any type), download a whole folder as a .zip, create folders, rename and delete. The entry point is always the "brain" you have selected, with no File Explorer and no shell needed.

## What this feature is

Each Javis brain is really a folder on your machine or VPS holding all of its knowledge: source notes, the Wiki, memory, agents, workflows and so on. The "Files" page lets you see and edit those files visually:

- Search the whole brain by **name** or by **content**.
- Browse the folder tree (click a folder to go in, use the breadcrumb to come back).
- Open a file to read: the editor opens **inside the page**, taking the place of the file list (not a popup window). It is the same editor you use from the chat, so `.md` gets visual editing, a formatting bar and Back/Forward between notes; images and PDFs are viewed in place.
- Edit text files (.md, .txt, .json...) and click save.
- Upload files from your computer into the brain, or download files from the brain (any type, not just .md).
- Download a whole folder: Javis zips it first, then sends it.
- Create folders, create files, rename and delete.

## Browsing scope: how far up you can go

The default entry point is always the root of the selected brain. But the **browse ceiling** (where "↑ Up" stops going up) depends on how you run Javis:

| How you run it | Ceiling | Meaning |
|---|---|---|
| Locally, without a login gate (localhost) | **The disk holding the brain** | You can browse and edit files outside the brain, because the machine is yours |
| Public bind / login required (Docker, VPS) | The brain folder | Locked inside the brain, so the disk is never exposed to the web |
| `JAVIS_FILES_ROOT=brain` (or `vault`) | The brain folder | Locked inside the brain even when running locally |
| `JAVIS_FILES_ROOT=drive` (or `root`) | The disk holding the brain | Forces the wider scope |
| `JAVIS_FILES_ROOT=<path>` | Exactly that folder | A custom ceiling, which must contain the brain |

So on a personal machine, clicking **↑ Up** repeatedly can take you out of the brain all the way to the disk root. The **⌂ Brain** button takes you home instantly. Once you stand at the ceiling, **↑ Up** hides itself. Javis always blocks paths trying to escape the ceiling (`../../` style), and the brain is always inside the ceiling.

How to set environment variables is in [.env configuration](16-env-configuration.md).

## Where to find it in Javis

1. Open the Javis dashboard (port 7777 by default).
2. In the left navigation rail, open the **Brain** group and click **Files**.
3. The page shows a search box on top, a toolbar under it, then the file and folder list. On first entry, Javis shows the root of the selected brain.

If the list reports something like "The Javis server does not have the Files feature", restart the server (run `stop-javis.bat` then `start-javis.vbs`) and reload the page. See [Troubleshooting & FAQ](17-troubleshooting.md).

## Choosing the brain you work in

The file manager always acts on the selected brain. You switch brains in the picker at the left of the dashboard top bar:

1. Find the brain picker in the top bar (default: "Brain Default").
2. Click it and choose the brain you want. Each brain shows as "🧠 brain name" (with a note count when available).
3. The Files page **reloads itself** for the new brain as soon as you switch, with no ↻ and no F5 needed. The vault tree in the left column refreshes too.

Next to the brain picker sit three small buttons:

| Button | Meaning |
|---|---|
| ➕ | Create a new brain in the brains folder |
| 🗑 | Delete the selected brain (you must type its exact name to confirm) |
| 📁 | Pick a brain from any external folder |

Three things to remember about 🗑:

- For a real brain (🧠): it deletes the **whole** brain, not one file. The confirmation says the brain goes into the **RECYCLE BIN (kept 30 days, then permanently deleted)** and that the deletion **SYNCS to every other machine**. You must type the brain name exactly.
- For an external folder entry (📁): it only **removes it from the picker**, touching no data on disk. The confirmation says so explicitly.
- The default brain cannot be deleted; Javis says the starter brain cannot be removed.

Do not confuse this button with the per-row "Delete" button inside the Files page. Details on brains and memory are in [Second Brain: memory, Wiki, INGEST](13-second-brain.md).

## The Files page layout

**Top row, search**, with:

- A search box with a 🔍 icon and the placeholder **Search files across the brain...**. Once it has text, a **✕** button appears (tooltip: "Clear search").
- Two scope chips: **Name** (tooltip: "Search by file name") and **Content** (tooltip: "Search inside text files"). **Name** is the default.
- A meta line on the right showing status: at rest "Search across the brain" (or "Scan text file contents" on the Content chip), and with results "12 results · file name".

**Second row, the toolbar**, with:

- A **breadcrumb** on the left: it starts with "🏠 root folder name", then each subfolder you have entered. Click any link to jump straight back to that level.
- **↑ Up**: go one level up. It hides itself once you are at the ceiling.
- **⌂ Brain** (tooltip: "Back to the brain folder"): return to the brain root from wherever you are.
- **+ Folder**: create a folder.
- **+ File**: create a new (empty) file.
- **⤒ Upload**: pick files from your computer (several at once).
- **⤓ Download folder**: zip the current folder and download it.
- **↻**: reload the current list.

Below sits the list. Each row shows a file type icon, the name, the size (for files) and a group of action buttons. That group is always present (slightly dimmed) and becomes fully visible when you hover the row; on phones and tablets it is visible by default because touchscreens have no hover.

## How to use it (step by step)

### Searching files across the brain

1. Click the **Search files across the brain...** box at the top.
2. Pick a scope: the **Name** chip matches file names, the **Content** chip scans text inside files.
3. Type a keyword. Javis searches shortly after you stop typing; press **Enter** to search immediately.
4. The list below turns into search results. Each row shows the file name, its path, an excerpt (for content searches) and a match label: **File name** or **In content · line 42**.
5. Click **Open** (or click the file name) to open the file.
6. Click **⤓ Download** to download that file directly, without navigating to its folder.
7. Click **Location** to jump to the containing folder; Javis scrolls to the row and highlights it.
8. Clear the search box (or click **✕**, or press **Esc**) to return to the folder list.

A few things to know about search:

- The scan scope is always the **brain root**, even when your browse ceiling reaches the whole disk. Javis deliberately does not scan the entire disk because it would be very slow.
- **Name** search ignores Vietnamese diacritics: typing `bao cao` still finds `báo-cáo.md`. This applies to every file type.
- **Content** search only scans text files (.md, .txt, .json, .yaml, .csv, .py, .js...), skips files over 1MB, and skips the technical folders `.git`, `node_modules`, `__pycache__`, `.obsidian`, `.trash`, `.venv` plus every hidden folder.
- **Content** mode needs at least 2 characters. With one character Javis says at least 2 characters are needed.
- With no matches it shows `No file matches "<keyword>".`
- The **Find note...** box in the left VAULT column has shared this same path since version **0.52.9**. Before that it crawled the whole vault from the browser, one server request per folder, so over the network to a VPS it was much slower than this page's box. Now both are equally fast.

### Browsing folders

1. Click a **folder name** (the row with the 📁 icon) to go in.
2. Use the breadcrumb, **↑ Up** or **⌂ Brain** to come back out.
3. Clicking a **file name** (or its icon) opens the file too: text files, images and PDFs open in the editor on the page, and everything else opens in a new tab.
4. An empty folder shows "Empty folder."

### Opening and editing text files

1. Hover the file row and click **Edit**. (Or click the file name directly.)
2. The editor opens **inside the page**, replacing the file list, not as a popup covering the screen. It is exactly the editor you use when opening a file from the chat, so everything matches: text files (.md, .txt, .json, .yaml, .yml, .csv, .js, .ts, .py, .html, .css, .toml, .ini, .log, .sh, .bat, .xml, .svg, .env) get an editing area, and `.md` additionally gets two modes, **Edit** (visual, like a word processor) and **Source** (raw markdown), plus a formatting bar.
3. When done, click **💾 Save** (or `Ctrl` + `S`). On success the button briefly reads **✓ Saved** and then returns to normal.
4. Click **✕** (or press `Esc`) to close and return to the list. The list reloads itself, so a file you renamed or deleted from inside the editor shows its new state.
5. The editor bar also has: rename, delete, **↗** open in a new tab, **⤓ Download**, and a full-screen button.

**The "Properties" block at the top of a `.md` note.** If the file starts with a `---` block (frontmatter: `type`, `status`, `created`...), Javis renders it as a separate block and **locks it against editing** in Edit mode. That is metadata rather than prose, and locking it is exactly what keeps it byte-for-byte intact across saves. To edit metadata, switch to **Source** mode.

### Back / Forward between notes

Reading a wiki note means following a chain of links: click a `[[wikilink]]` and you are in another note. The two arrow buttons **‹ ›** in the **top left**, right before the file name, walk that trail, exactly like a browser's Back/Forward.

- **Click the left arrow** to return to the note you just read, the **right arrow** to go forward again.
- **Hover a button to see where it leads.** The tooltip names the file, for example "Back to: Octagon Offer.md". Four or five links deep, remembering where you came from is not easy, so the button says it for you.
- **When there is nowhere to go, the button dims rather than disappearing.** Buttons that appear and vanish make the title bar jump, and you would never learn they exist.
- **Shortcuts: `Alt` + `←` and `Alt` + `→`.** A mouse with side buttons works too.
- The trail **survives closing the editor** and reopening it (closing it to chat about that same note is common), and **clears when you switch brains**, because every step in the trail belongs to the old brain.
- Opening a new note from the middle of the trail truncates what was ahead, exactly like a browser.

**Leaving a file with unsaved edits makes Javis save first.** Clicking an arrow, a wikilink or another file in the tree: if you edited something and did not click Save, Javis saves before moving. If the save fails (network down, file locked), **Javis does not move at all** and the Save button shows the error, so what you just wrote is never thrown away silently. A file you only opened to read is never written back.

**Whichever file is open is the file Javis works on.** As soon as you open a text file for editing, Javis **pins** it to the chat: an orange chip appears above the input with the file name and the line "open, click to keep editing". From then on, whatever you ask already has that file as an input, so you never paste a path or describe it again. Saying "clean up the overdue section" or "add a conclusion" without naming a file makes Javis write straight into the open file.

The pinned chip differs from an attachment chip in three ways:
- **There is only one.** Opening another file replaces it rather than stacking.
- **It does not disappear after you send.** Attachments vanish once sent; the pin stays for the whole conversation because it is the file you are working on. Closing the editor does not unpin it either, since closing it to chat about that same file is normal.
- **Clicking the chip takes you back to editing.** After closing the editor and chatting for a few turns, click the chip (or focus it with Tab and press Enter) and the file reopens in the editor, with the vault tree on the left expanding to the branch that holds it, so you do not go hunting again. If the file is already open, Javis just brings you back to it without reloading, so unsaved text survives. On phones the chip opens the file in an editor sheet in the middle of the screen. Clicking **✕** on the chip still unpins rather than opening.

Unpin with **✕** on the chip. The pin also clears when you switch brains or delete the pinned file, and it survives F5, so reloading the page does not break your flow.

Notes:
- The **Edit** button only appears for the text file types listed above.
- Files larger than 2MB are not opened for viewing in the browser. Javis suggests downloading instead.
- If the file is binary rather than text, the editor offers **⤓ Download** instead of an editing area.

### Repairing `.md` files broken by older builds

Javis **before 0.33.4** had a silent bug: opening a `.md` note in the visual editor and clicking Save turned the `---` block at the top of the note (frontmatter: `type`, `status`, `created`...) into `* * *`, and each further edit added another layer of backslashes to the text (`1.` → `1\.` → `1\\.`). The file still opened, but the metadata was effectively lost, and Javis, dataview and Obsidian all read it wrong from then on.

This build closed that path. For files already damaged:

1. Open the **Files** page. Javis scans the whole brain once when you arrive. **If nothing is broken, nothing appears**: silence is good news.
2. If something is, a yellow panel appears at the top with the file list and what is wrong in each.
3. Click **Repair all N files**. Javis rebuilds the properties block, strips the extra backslashes, and reports how many files it fixed.

Since 0.52.8, a brain that scans **clean** is remembered and **not scanned again** on later visits. That scan reads every `.md` file in the brain, so on a brain with a few thousand notes it made the Files page noticeably slow to open, and the search box sluggish with it. The damage came from a build that no longer exists, so clean once means clean for good. A brain that still has broken files is rescanned on every visit until you click repair. If you copy an old vault in from another machine and want a rescan, open `/files/md-hong?force=1`.

Javis only fixes what **only that bug could produce**: a `* * *` block at the very top of the file wrapping lines that look like metadata, and runs of two or more backslashes. A horizontal rule in the middle of an article, a file with intact frontmatter, or a single backslash you typed deliberately are all left alone.

### When a link misses: Javis goes looking

Paths in the chat sometimes differ from the file name on disk, most often when the chat writes accents ("Kế hoạch...") while the file is saved without them ("Ke Hoach..."). Previously, clicking it landed on an empty page reading "Not a folder". Now:

- If the path points at **a file** (even when it looks like a folder name), Javis opens that file for editing.
- If **nothing is there**, Javis opens the nearest folder that does exist, says exactly what it was looking for, then **searches the brain by name** (ignoring Vietnamese diacritics) and lists files with similar names, one click from opening.
- Opening a file directly in the editor behaves the same: if the file is missing, the editor suggests similar file names instead of just reporting an error.

### Viewing images and PDFs in the dashboard

1. Hover an image row (.png, .jpg, .jpeg, .gif, .webp, .bmp, .ico) or a .pdf and click **View** (tooltip: "Preview"). Clicking the file name gives exactly the same result.
2. Images render in the editor; PDFs embed in a reader in place.
3. The bar also has **↗** to open the file in its own tab and **⤓ Download**. Click **✕** (or `Esc`) to return to the list.

Other file types (video, archives, data files...) have no Edit and no View button, but an **Open** button (tooltip: "Open in a new tab"). In other words, every file row always has exactly one view/open button; only its name changes with the type.

### Creating a file

1. Click **+ File** in the toolbar.
2. Type the file name including the extension, for example `notes.md`.
3. Javis creates an empty file in the current folder. Click **Edit** to write content.

### Creating a folder

1. Click **+ Folder**.
2. Type the folder name.
3. The new folder appears in the current folder.

### Uploading files

1. Click **⤒ Upload**.
2. Pick one or more files from your computer.
3. Javis uploads them into the current folder one by one, then refreshes the list.

If the folder already has a file with the same name, Javis appends a number to the new one (for example `report_1.pdf`) rather than overwriting.

### Downloading a file

1. Click **⤓ Download** on the file row.
2. The browser downloads it, keeping the original name including Vietnamese accents.

This button exists for **every file type**, not just .md: images, PDFs, video, archives, spreadsheets and data files can all be downloaded. Search results carry a **⤓ Download** button next to Open, so finding a file is enough to download it without navigating to its folder.

The view/edit window always has a **⤓ Download** button at the top too, even for a file open in edit mode (previously an editable file only had Save).

### Downloading a whole folder (as .zip)

Two routes, with identical results:

- Click **⤓ Zip** on the folder row in the list.
- Enter the folder and click **⤓ Download folder** in the toolbar.

Javis measures the folder first, then zips everything inside (keeping the subfolder tree) into a .zip named after the folder, for example `attachments.zip`. A few things to know:

- For folders over 200MB, Javis asks first, showing the file count and estimated size so you do not wait for nothing.
- The safety ceiling is 20,000 files or 2GB. Beyond that Javis says so plainly and suggests downloading subfolders one at a time; this guard exists so one misclick at the disk root does not pull the whole disk into an archive.
- An empty folder makes Javis say there is nothing to download rather than handing you an empty .zip.
- Empty subfolders are still preserved inside the .zip.

The file tree on the notes page has the same **⤓** button: on a file it downloads the file, on a folder it downloads the folder as .zip.

### Renaming

1. Hover the file or folder row and click **Rename**.
2. Type the new name and confirm. An empty name or the same name changes nothing.

Unusual characters in a name are replaced with underscores for safety, so the actual name may differ slightly from what you typed. Vietnamese accents, dots, hyphens, underscores, spaces and parentheses are preserved.

### Deleting

1. Hover the row and click **Delete** (the warning-coloured button).
2. Javis asks to confirm: `Delete "<name>"? This cannot be undone.` It only deletes after you agree.
3. For a folder, deleting removes every file inside it.

Warning: deletion has no recycle bin and cannot be undone. Be sure before you confirm. Javis refuses to delete the brain root or the browse-ceiling folder and says so.

## Two folders are cache areas, keep nothing precious there

Each brain's `attachments/` and `inbox/` are treated by Javis as **cache**, not storage:

- Files in those two folders older than **30 days** are cleaned automatically, and if their total size passes the **300MB** ceiling, Javis cleans oldest first until it is under the ceiling.
- `.md` notes that happen to live there are exempt and never cleaned.
- To disable the cleanup entirely, set `enabled: false` under the `media` key in `settings.json`. The age and size thresholds live there too.
- An expired image reappearing in a conversation becomes a grey dashed box reading **"Image expired"** instead of a broken image icon.

The practical conclusion: move anything you want to keep long term into the brain's sources or Wiki folders, not `attachments/` or `inbox/`.

## Quick reference: buttons and states

| You want | Click | Note |
|---|---|---|
| Find a file by name | Search box + `Name` chip | Ignores Vietnamese diacritics |
| Find text inside files | Search box + `Content` chip | Text files only, skips >1MB, needs ≥2 characters |
| Open a search result | `Open` | Or click the name directly |
| Jump to the containing folder | `Location` | Scrolls to and highlights the row |
| Exit search | `✕` or `Esc` | Back to the folder list |
| Enter a folder | The folder name (📁) | The breadcrumb brings you back |
| Go up one level | ↑ Up | Hides itself at the ceiling |
| Back to the brain root | ⌂ Brain | Needed when you wander outside the brain |
| Refresh the list | ↻ | Switching brains refreshes automatically |
| Read/edit a text file | Edit → 💾 Save | Text files under 2MB only |
| View an image / PDF | View | With ↗ New tab and ⤓ Download |
| Open other file types | Open | Opens in a new tab |
| Create an empty file | + File | Remember the extension, e.g. `.md` |
| Create a folder | + Folder | |
| Bring files in from your computer | ⤒ Upload | Multiple files allowed |
| Take a file to your computer | ⤓ Download | On EVERY file type, search results included |
| Take a whole folder | ⤓ Zip (folder row) or ⤓ Download folder (toolbar) | Zipped; ceiling 20,000 files / 2GB |
| Rename | Rename | Unusual characters become `_` |
| Delete | Delete | Asks to confirm, cannot be undone |

## Tips

- When you cannot remember where a file is, do not browse by hand: the search box is fastest. If you vaguely remember the content, switch to the **Content** chip, which searches inside files.
- Wiki files and vault notes are all .md, so you can fix them quickly here instead of opening another app. For knowledge edits, though, it is usually easier to let Javis do it through chat. See [Chat & voice](02-chat-and-voice.md) and [Second Brain: memory, Wiki, INGEST](13-second-brain.md).
- Name files after their main point rather than generically. It helps both you and Javis find them again.
- To feed Javis an article, a screenshot of knowledge or a document, upload it into the brain's sources folder and then ask Javis to process it in the chat.
- On a personal machine you can browse out to the whole disk, so look at the breadcrumb before deleting. If "🏠" is not your brain name, you are standing outside the brain.
- Before bulk operations, check that you are in the right brain through the top-bar picker. Editing the wrong brain is the most common mistake.

## Common problems

**The list reports "The Javis server does not have the Files feature".** The server is running an older build without it. Restart it (`stop-javis.bat` then `start-javis.vbs`) and reload the page.

**"Session expired" or a 401 error.** Reload the page and sign in again. See [Security & accounts](14-security-and-accounts.md).

**The ↑ Up button is nowhere to be found.** You are already at the ceiling and it hid itself. Click **⌂ Brain** to return to the brain root.

**You browsed outside the brain and cannot find the way back.** Click **⌂ Brain**. That is the designed behaviour when running locally: the ceiling is the disk, not the brain folder. To lock it inside the brain, set `JAVIS_FILES_ROOT=brain` and restart the server.

**Search does not find a file you know exists.** Three common causes: the file is outside the brain root (search only scans the brain); it is inside a skipped folder such as `.git`, `node_modules`, `.trash`; or you are on the **Content** chip and the file is not text or is over 1MB. Try the **Name** chip.

**Search says "At least 2 characters needed".** **Content** mode needs a keyword of at least 2 characters. Type one more, or switch to the **Name** chip.

**Opening a file reports it is too large to view (>2MB).** It exceeds the in-browser viewing limit. Use **Download** and open it with a suitable application.

**Opening a file reports it is binary and cannot be shown as text.** The file is not text (an archive or a data file, for example). It cannot be edited in the browser, only downloaded.

**Downloading a folder reports it is too large to zip.** The folder exceeds the 20,000 file / 2GB safety ceiling. Go inside and download subfolders one at a time. This happens most often when you are standing at the disk root rather than inside the brain; check the breadcrumb.

**Downloading a folder reports there is nothing to download.** The folder is empty. Javis does not create empty .zip files.

**You clicked Download but no file arrived.** Check the browser's Downloads folder and whether the browser blocks automatic downloads. Large folders also need a few seconds to zip before the browser starts receiving.

**Saving shows "⚠ Error" on the button.** The save failed. Try again; if it persists, check write permissions on the brain folder and the state of the disk, or see [Troubleshooting & FAQ](17-troubleshooting.md).

**A file you just uploaded or created is not visible.** Click **↻** to refresh the list. If it is still missing, check that you are in the right folder and the right brain.

**Images in attachments disappeared.** Most likely they passed 30 days or the folder crossed the 300MB ceiling and was cleaned automatically. See "Two folders are cache areas" above.

**You deleted a file by mistake.** This manager has no recycle bin and the deletion cannot be undone. If your brain sits in a folder backed up by git, you can restore from there; otherwise the file is gone. See [Backing the brain up to GitHub](18-github-backup.md).

**You deleted a whole brain by mistake.** That one is recoverable: a deleted brain goes into the recycle bin and is kept for 30 days before being removed for good.

## Related

- [Second Brain: memory, Wiki, INGEST](13-second-brain.md) - what lives inside a brain.
- [Backing the brain up to GitHub](18-github-backup.md) - keeping change history and recovering deleted files.
- [Tasks & Dataview in notes](19-tasks-and-dataview.md) - writing tasks and query tables in .md files.
- [.env configuration](16-env-configuration.md) - the `JAVIS_FILES_ROOT` variable and the rest.
- [Troubleshooting & FAQ](17-troubleshooting.md)
