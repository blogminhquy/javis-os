# Syncing the brain with GitHub (two-way)

*[Tiếng Việt](../18-sao-luu-github.md) · **English***

This feature syncs **EVERY brain in the brains folder** (all of them: notes, Wiki, memories, agents and workflows) with a **private** GitHub repo of yours, in BOTH directions: pushing this machine's changes up while pulling other machines' changes down. The point: no data lost when a machine dies or a VPS disappears, and **being able to use several machines at once** (home machine plus VPS), with the machines matching each other's data through the repo.

> Keep **every brain inside the brains folder** (creating one with the ➕ button puts it there automatically). Sync takes the whole brains folder as one unit, so any brain outside it (an external folder picked with the 📁 button) is NOT synced along; move it into brains.

Open it at: the **Self-learning** page (**Brain** group on the left nav rail), scrolling down to **⇅ Sync brain with GitHub (two-way)**.

## Why turn it on

The brain is all the knowledge Javis has accumulated about you and your work. It sits on the machine's or VPS's disk. With only one copy, one accident loses everything. Syncing with GitHub gives you:

- An off-machine copy, safe when hardware fails.
- A history of every change (review it, restore an earlier point).
- Working across machines: edit at home, and the VPS picks it up on the next sync, and the other way around.
- A new machine only needs the repo plus token pasted in and one sync to have every brain back in full.

## Requirements

- The machine or VPS must have **git** (the Sync section reports "git is not installed on this machine" if it is missing). The official Docker image already ships git.
- A GitHub account.

## Setup in 3 steps

### Step 1 - Create a private GitHub repo

1. Go to https://github.com/new
2. Give it a name, for example `javis-brain-backup`.
3. Choose **Private** (MANDATORY: the brain holds personal and business data, never make it Public).
4. Do **NOT** tick "Add a README file" (leave the repo empty to avoid a conflict on the first push).
5. Click **Create repository**. Copy the URL, shaped `https://github.com/<your-name>/javis-brain-backup`.

### Step 2 - Create a token (fine-grained)

1. Go to https://github.com/settings/tokens?type=beta (Settings → Developer settings → **Fine-grained tokens** → Generate new token).
2. Name the token and choose an expiry.
3. **Repository access** → Only select repositories → pick exactly the `javis-brain-backup` repo.
4. **Permissions** → Repository permissions → **Contents** → choose **Read and write**.
5. Click Generate and **copy the token** (shaped `github_pat_...`). The token is shown once only, so copy it immediately.

### Step 3 - Paste it into Javis

1. Open the **Self-learning** page → the **⇅ Sync brain with GitHub (two-way)** section.
2. Paste the **repo URL (https)** and the **GitHub token (fine-grained, Contents permission)** into their fields.
3. Check the **Branch** field: it defaults to `main`. If your repo's default branch differs (`master`, say), fix it here or the push goes to the wrong branch.
4. Click **🔌 Test connection**, which must report "Connection OK".
5. Click **⇅ Sync now** for the first run.
6. To automate it: turn the **Automatic** switch on, set **Auto-sync every (hours)** (default 6), then **💾 Save configuration**.

Using several machines: do these 3 steps on EACH machine (same repo, same branch, the same token or separate tokens both work). Turn Automatic on in both places and the machines match each other on the cycle.

## Quick reference of fields and buttons

| Field / button | What it does |
|---|---|
| **Repo URL (https)** | The private GitHub repo receiving the backup, shaped `https://github.com/<you>/<repo>`. |
| **GitHub token (fine-grained, Contents permission)** | The token used to push and pull. Stored locally in `settings.json` encrypted, never pushed to the repo. |
| **Branch** | The branch to push to, `main` by default. Corresponds to the `backup.branch` key in `settings.json`. |
| **Auto-sync every (hours)** | The automatic cycle, 6 by default. |
| **Automatic** | The on/off switch for periodic runs, showing **○ Off** when off. |
| **🔌 Test connection** | Tries the repo plus token, pushing nothing. |
| **⇅ Sync now** | Runs one full sync immediately. |
| **💾 Save configuration** | Writes every field above (the Automatic switch and the hour count included). |

## How it works

Each sync does 4 things in order:

1. **Snapshots** the brains folder into a clean copy (dropping sensitive files and each brain's raw git) and records this machine's changes.
2. **Pulls** the latest version from GitHub and **merges**: different files are combined automatically; when two machines edited THE SAME file, the **more recent edit wins**, and the losing version is kept alongside as `.conflict-<local|remote>-<timestamp>` for you to decide; when one side edited and the other deleted, the edit wins (nothing is lost silently).
3. **Applies the result** back into the machine's brains folder (a file you edited by hand during the sync itself is not overwritten, the machine keeps your copy and the next round merges it).
4. **Pushes** to GitHub (an ordinary push, NOT a force). If another machine pushed in between, Javis pulls, merges again and pushes again.

Safety notes about the mechanism:

- The token is **not** stored in the brain or pushed to the repo. It lives in the local `settings.json` (git-ignored). Error messages mask the token too.
- **Only TEXT files are synced.** Images, video, audio, PDFs and every other binary do not go to the repo; see [Sync INFORMATION only, not media](#sync-information-only-not-media) just below.
- Sensitive files are excluded from sync even when they are text: raw conversations (`memory/conversations`), loop and learn logs (`Javis/loop-log`, `Javis/learn-log`, `Javis/learn-staging`), skill usage statistics (`Javis/skill-usage.json`), lock files, `.tmp` files, and each brain's own `.git`. Those stay on the machine that created them.
- The brain trash (`brain-trash` in the state folder) is OUTSIDE the sync area, so it never reaches the repo.
- A machine with an **empty** brains folder (a new machine, a new volume) is treated as a RESTORE: it only receives data and never pushes an "empty state" that would wipe the backup.
- Deleting a file or brain on one machine deletes it on the others at the next sync (that is what sync means). Because the repo is git, everything remains in the commit history and can be recovered when needed.

## Sync INFORMATION only, not media

This is the most surprising part, so read it carefully once and be done.

**Only text files reach GitHub.** Notes, Wiki, memories, skills, recurring-job configuration, scripts: `.md`, `.txt`, `.html`, `.csv`, `.json`, `.yaml`, `.canvas`, `.py`, `.svg` and a few other text extensions. The full list is `TEXT_EXTS` in `server/git_brain.py`.

**Images, video, audio, PDFs and every other binary do NOT.** They stay on the machine and work normally, they just do not enter git history and do not travel to other machines this way.

### Why block them rather than push everything to be safe

Git is designed to **remember forever**, and that is the fundamental difference from a disk or Google Drive.

At every commit, git takes the file's contents, hashes them, then stores those contents as a compressed object in `.git/objects` (a *blob*). Deleting the file in a later commit only records a line saying "from here on this file is gone"; the blob itself must be kept, because without it you cannot go back to the old commit. `git gc` cannot clean it either, since it still has an owner. In other words: **deleting a file from git does not reclaim space.**

For text, that property is a strength. Git compresses very well and stores only the difference between versions, so an `.md` file edited a hundred times adds up to less than you would think.

For media it is the exact opposite. An `.mp4` or `.jpg` is already codec-compressed, git cannot compress it further, and two renders of the same clip are, to git, two entirely different files rather than one lightly edited file. Every re-export adds another whole object to the store, permanently. A brain with a few hundred MB of media plus a habit of re-editing each clip a few times pushes the repo into multiple GB within months, and a new machine cloning it has to download even the renders you abandoned last year.

Cleaning that up then requires **rewriting the entire history** (`git filter-repo` or BFG). That changes every commit's hash, so every copy on other machines becomes incompatible and has to be downloaded from scratch. For a Javis syncing two ways across several machines, that is a disaster rather than a maintenance task. So the right approach is to keep media out from the start.

### So where do you back media up

Use something that stores the **current state**: Google Drive, OneDrive, an external disk, a NAS. There, deleting really deletes and really reclaims space, exactly what you want for images and video. The two tools divide the work rather than replacing one another: git holds knowledge and its whole history, Drive holds the heavy files at their latest state.

After every **⇅ Sync now**, if media was skipped Javis states it right under the status line: how many files, how many MB in total. Skipping silently would one day leave you believing your images were backed up too, only to learn otherwise when the machine is gone.

### If you want images to travel too: the "Sync images too" switch

Some people genuinely need the images in their brain (screenshots, product photos of a few hundred KB) to follow the knowledge to another machine. Since version 0.46.0, the sync block has an extra **Sync images too** switch (off by default). Turning it on means:

- **jpg / png / gif / webp** images, each up to **10 MB** (change it with the `JAVIS_SYNC_ANH_MAX_MB` environment variable), also reach the repo and sync two ways like text files. Video, audio, PDFs and images over the ceiling still never go; nor does `inbox/`, which is a one-chat transit area.
- Javis **stops clearing `attachments/`** on that machine (it still clears `inbox/`): if backed-up images were cleared by the age rule, the deletion would propagate to every machine and the backup images would vanish, so the two must go together.

Three things to weigh BEFORE turning it on:

1. **Git remembers forever.** Pushed images sit permanently in the repo history; turning the switch off later does not reclaim the space. A private GitHub repo is comfortable at a few hundred MB, enough for working images, not enough for a family photo library.
2. **Sharing a repo across machines means turning it on EVERYWHERE.** A machine with it off treats images as "out of scope": it neither pushes nor receives them, and it also does not delete images another machine uploaded, so mismatched configuration loses nothing, it only means that machine does not see the images.
3. **Video and heavy files still follow the old advice**: Drive, an external disk, a NAS.

### Media in the brain still expires as before

With "Sync images too" OFF, Javis treats `attachments/` and `inbox/` as a cache: every 6 hours, files over **30 days** old are deleted, and if the total passes the **300 MB** ceiling it deletes oldest first until it is back under. This rule has nothing to do with sync, but it is worth knowing because it is why old images vanish from the machine. To keep something long term, pull its content into an `.md` note, move the file into another folder of the brain, or loosen or disable the clearing rule (the `media` key in `settings.json`). How to disable it: [Troubleshooting and FAQ](17-troubleshooting.md).

## Restoring the brain on a new machine

No manual git needed: install Javis, go to **Self-learning → ⇅ Sync brain with GitHub (two-way)**, paste the repo, the token and the right branch, click **⇅ Sync now**, and every brain comes back in full. (The old way, `git clone` straight into the brains folder, still works.)

## Handling .conflict-* files

When two machines edit the same file between syncs, you get an extra file such as `file-name.conflict-local-20260702-101530.md` next to the original:

- The original file = the WINNING version (the one with the more recent edit).
- The `.conflict-*` file = the LOSING version, kept verbatim so you can compare and merge by hand if needed.
- Delete the `.conflict-*` file once you have looked at it (it syncs between machines like any other file).

## Safety notes

- **Always use a Private repo.** A brain can hold business figures, customer names, sometimes even a key you happened to paste into a conversation, and as the section above says, the files you send into chat travel too.
- Give the token an expiry and grant only the **Contents** permission on exactly that repo, nothing broader.
- One repo serves ONE set of brains. Do not point two Javis systems with entirely different purposes at the same repo, as they will mix their data together exactly as sync is designed to.

## Common problems

| Symptom | Cause / what to do |
|---|---|
| "git is not installed on this machine" | Install git on the machine or VPS. The official Docker image already has it. |
| Test connection reports a 403 | The token lacks Contents: Read and write, or the right repo was not selected. |
| The push succeeds but GitHub shows no files on the branch you expected | The **Branch** field differs from the repo's default branch (Javis defaults to `main`). Fix the Branch field to match, Save configuration and sync again. |
| "the push keeps being overtaken" | Several machines are syncing at once, continuously. Click again in a few minutes and the merge mechanism will settle it. |
| "applying the sync locally failed for N files" | Some files are locked or unwritable on the machine (open in another app, say). Nothing is pushed this round (which is safe); close the app holding the file and sync again. |
| Many `.conflict-*` files appear | Two machines frequently edit the same file between syncs. Shorten the Automatic cycle, or split the work so each machine owns an area; handle the conflict files as described above. |
| The backup repo grows very fast | Usually "Sync images too" turned on with an image-heavy brain. Space already in history cannot be reclaimed; from now on limit new images or turn the switch off (old images stay in history). |
| "Sync images too" is on but another machine sees no images | That machine has the switch off, so it does not receive images. Turn it on for every machine sharing the repo. |
| You want to stop the automatic runs | Turn the Automatic switch off and Save configuration. You can still click "Sync now" manually. |

---

Related: [08 - Recurring jobs and reminders](08-recurring-jobs.md) · [13 - Second Brain: memory, Wiki](13-second-brain.md) · [22 - Self-learning](22-self-learning.md) · [17 - Troubleshooting](17-troubleshooting.md)
