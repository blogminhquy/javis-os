# Composer: pin a working folder, and a compact agent Work tab

Status: approved by the owner on 2026-10-15 (chat). Follows PR #663 (0.153.0, composer redesign).

## Why

1. The "+" menu item "Add folder" uploads every file of a folder as attachments. The owner does not want
   that: a folder is a place to work in (a code project), not a pile of attachments. Claude Code shows the
   working folder as a small chip under its input; Javis should do the same, as compactly as possible.
2. The Coding page has its own "Pick a folder" chip and menu. Once the composer can pin a folder, that
   duplicate is not needed.
3. The agent Work tab ("Công việc") filters with two horizontally scrolling chip rows and 16px text in a
   ~300px column. It looks crude and wastes space. The owner wants dropdowns and smaller text.

## What exists today (facts the design relies on)

- `coding_store` keeps a per-session binding (`rang_buoc`): main folder id (`thu_muc`), extra folders
  (`thu_mucs`), branch, worktree, permission level. Folders are registered per brain with
  `POST /coding/folders` (`duong_dan`, `brain`) and bound with `POST /coding/session/{sid}` (`thu_muc`).
- `main._cwd_luot_chat(row, brain)` already runs ANY session's turn in `coding_store.cwd_cua_phien(sid)`
  when the session has a folder, otherwise in the brain root. Only the prompt block (`_khoi_coding`) and
  the permission level (`_muc_quyen_luot_chat`) are limited to `coding:` channel sessions.
- `JavisFolderPicker.open({...})` (folder-picker.js) is a shared folder browser on `GET /browse`.
- `GET /files/search?mode=name&include_dirs=1` searches names inside the brain root.
- `JavisModelBar.claimPending(sid)` is called by app.js when the first message mints a session id; the
  same moment is where a folder pinned on an empty chat must be applied.
- `javis:sessions-changed` fires when the open session changes.

## Design

### A. Pin a working folder from the composer

**Menu.** The "+" item `folder` changes label to "Pin working folder" and becomes a submenu panel (same
pattern as "Pick a file from the brain"):
- a search box (debounced, `GET /files/search?mode=name&include_dirs=1`, folders only);
- with an empty query: the top-level folders of the brain (from `GET /files/list` of the brain root),
  hidden and heavy folders excluded (`.git`, `node_modules`, `.obsidian`, `.trash`, dot folders);
- a last row "Browse another folder..." that opens `JavisFolderPicker` (owner chose: brain first, plus
  browsing outside the brain, like the Coding page today);
- when a folder is pinned, two extra rows on top: the current folder (disabled, shows the name) and
  "Unpin".

**Chip.** When the open conversation has a pinned folder, a chip appears in `.cp-chips` right after the
Fast mode bolt: folder icon + folder name, cut to 18 characters with an ellipsis; `title` = full path,
plus "Only CLI brains can work outside the brain" when the folder is outside the brain root. Clicking
the chip opens the "+" menu directly on the folder panel. No chip when nothing is pinned. On phones the
chip shows the icon and at most 10 characters.

**Scope.** Per conversation. A new conversation starts unpinned. Pinning on an empty chat (no session id
yet) is held client-side and applied in the same place `claimPending` runs, before the first turn is
sent, so the first turn already runs in the folder.

**Server.**
- New `POST /coding/session/{sid}/pin` (form: `path`, `brain`). `path` is either absolute (from the
  folder browser, same trust as `POST /coding/folders` today) or relative as `/files/list` and
  `/files/search` return it (resolved with main's read-only `_safe_serve_path`, locked to the browse
  ceiling). It registers the folder (`coding_store.them_thu_muc`, idempotent per path and brain) and
  binds it as the main folder (`dat_rang_buoc(thu_muc_id=...)`) in one call. Empty `path` unpins.
  Response: `{ok, folder: {id, name, path, exists, is_git}, in_brain, brain_rel}` or 400 with a message.
  One call instead of two keeps a half-done pin (registered but not bound) impossible from the UI.
- `GET /coding/session/{sid}` gains an optional `brain` query; with it the response adds `in_brain` and
  `brain_rel` so the chip can render after a reload. New response fields are English; the old
  Vietnamese fields stay as they are.
- `CodingDeps` gains `resolve_path(brain, rel) -> str` and `brain_root(brain) -> str`, wired in main.
- New `coding_store.pinned_folder_prompt(sid, brain_root)`: a short block for NON-coding sessions with a
  folder: working folder (absolute path), the path relative to the brain when it is inside the brain
  (API brains reach files through brain-relative vault tools), extra folders, git branch. It never
  states a permission level: a normal chat keeps running at `full` exactly as today.
- `main._khoi_coding(row)` returns `coding_store.khoi_prompt(sid)` for `coding:` sessions (unchanged) and
  `pinned_folder_prompt(sid, brain_root)` for every other session.
- `_muc_quyen_luot_chat` is unchanged (non-coding stays `full`).

**Removed.** The upload-every-file folder flow: `#folderInput`, `handleFolder`, `pickFolderFiles`,
`runQueue`, `JavisAttach.queue` and the `cp.folder_*` strings that only it used.

**Coding page.** Remove the "Pick a folder" / folder chip and its menu (`thumuc` chip, add/detach/forget
rows, `moKhungThemThuMuc`) and the `#cdIdentity` line ("Working inside the brain..."). The worktree,
branch, restore point and Plan/Auto/Full chips stay and keep reading `/coding/session/{sid}`. The page
refreshes them when the composer pins or unpins (new event `javis:pinned-folder-changed`).

### B. Compact agent Work tab

- Replace the two chip rows (`.aj-filters` sources and buckets) with ONE toolbar row holding two styled
  native `<select>` elements: Source (All, Team, Chat, Auto... with counts) and Status (All, Running,
  Waiting, Needs you, Done, with counts). Native select: keyboard and screen readers work, phones open
  the system picker, nothing overflows a narrow column.
- When `needs_you > 0` and the status filter is not already "needs you", show a small amber dot on the
  status select.
- Type scale for the whole `.aj` panel: body 13px, job title 14px semibold, meta and roles 12px, section
  headings 12px uppercase-free bold. "Assign work" button: 32px high, 13px text. Touch screens
  (`@media (pointer: coarse)`) keep 44px targets.
- The team side panel's Work tab has no chip rows; it is left as is.

### C. Housekeeping carried by this PR

- PR #663 left Vietnamese comments and test check names in new code (`composer-plus.js`,
  `effort-slider.js`, `tests/js/test_menu_cong.js`, `test_thanh_truot_effort.js`, `test_tia_set_fast.js`,
  `test_khung_go.js`). Translate them to English (owner rule 2026-10-15: all code in English).
- `docs/quy-uoc-dev.md`: replace "follow the language of the existing file" with "all new code,
  comments and test names in English, even inside older Vietnamese files".

## Error handling

- Registering or binding fails (path gone, server 400): the folder panel shows the server message in
  the menu and nothing is pinned.
- The pinned folder disappears from disk: `cwd_cua_phien` already returns "" and the turn runs in the
  brain; the chip shows the name struck through with a tooltip "Folder not found" (from `co_that`).
- Switching conversation quickly: the chip only renders the response for the session that is still
  open (sequence counter, same as the model pin).

## Testing

- JS (node, real code): folder rows filter out hidden/heavy folders; chip label truncation (desktop 18,
  phone 10); pending pin is applied once on claim and cleared; Work tab toolbar HTML has two selects with
  counts, keeps the selected option, shows the amber dot only when needs_you > 0 and not selected.
- JS canaries: no `folderInput`/`handleFolder` left; Coding page has no `thumuc` chip; i18n keys in vi/en.
- Python: a non-coding session with a pinned folder gets `pinned_folder_prompt` (path, brain-relative
  path when inside the brain, no permission line) and `_muc_quyen_luot_chat` still returns `full`; a
  coding session still gets `khoi_prompt`.
- Visual check on the sandbox server (port 7788): desktop dark/light, mobile 375, Chat and Coding pages,
  agent Work tab.
