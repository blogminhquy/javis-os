# Composer Pinned Folder + Compact Work Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the composer's "upload every file of a folder" with pinning a working folder per conversation, drop the Coding page's duplicate folder picker, and turn the agent Work tab's chip rows into two compact dropdowns with a smaller type scale.

**Architecture:** The pin reuses the existing per-session folder binding in `coding_store` (the server already runs any session's turn in its bound folder). A new endpoint `POST /coding/session/{sid}/pin` registers and binds in one call; a new prompt block tells non-coding sessions where they are working. The composer side lives in a new `dashboard/composer-folder.js` that plugs into the "+" menu registry through a new generic `panel` item type.

**Tech Stack:** FastAPI (server/main.py, server/routes/coding.py, server/coding_store.py), vanilla JS dashboard, node test scripts (`node tests/js/<file>.js`), Python test scripts (`python tests/python/<file>.py`, run with `D:/Project/Javis-OS/.venv/Scripts/python.exe` and `PYTHONUTF8=1`).

**Spec:** docs/superpowers/specs/2026-10-15-composer-pin-folder-design.md

## Global Constraints

- All code, comments, docstrings, test names and `check(...)` messages in English (owner rule 2026-10-15). User-facing strings go through i18n: Vietnamese with diacritics in `dashboard/i18n/vi.json`, English in `dashboard/i18n/en.json`, same keys in both.
- Never use the em dash character (U+2014) anywhere.
- `t()` keys must be literal strings (test_i18n scans them); no `"prefix." + x`.
- New `.js` files have no Vietnamese in run code; `dashboard/app.js` keeps exactly its current count of Vietnamese run-code lines (test_i18n).
- A normal (non-coding) chat keeps permission level `full`; nothing in this plan may change `_muc_quyen_luot_chat`.
- Version: reserve the next free number above main and above open PR titles (0.154.0 unless claimed). CHANGELOG.md (vi) and CHANGELOG.en.md (en, no Vietnamese) both get the block.
- Python writes text files with `newline=""` or `"\n"` preserved; `dashboard/app.js` contains NUL bytes, edit it byte-safely.
- Many tests are exact-substring canaries: before pushing, `grep -rln` tests/ for every changed file name and removed string.

## Review Focus

- Pin on an empty chat, then send: the very first turn must already run in the pinned folder (pending pin claimed before the turn is sent). Test in Task 2 (claim order canary + createPinState).
- Switching conversations quickly while a pin request is in flight: the chip must show the folder of the conversation that is open, not the previous one. Test in Task 2 (sequence guard in createPinState).
- A relative path containing `..` or pointing outside the browse ceiling sent to `/pin`: rejected with 400, nothing registered. Test in Task 1.
- The pinned folder deleted from disk: turn falls back to the brain, chip shows it as missing instead of crashing. Test in Task 1 (prompt block empty when folder gone) and Task 2 (chip label for `exists: false`).
- Agent Work tab select change fires both `input` and `change`: must load once, not twice. Test in Task 4.

---

### Task 1: Server: pinned folder prompt block and `/pin` endpoint

**Files:**
- Modify: `server/coding_store.py` (add `pinned_folder_prompt` after `khoi_prompt`)
- Modify: `server/routes/coding.py` (deps, `/pin` route, `brain` query on GET session)
- Modify: `server/main.py` (`_khoi_coding`, `CodingDeps(...)` wiring near line 21717)
- Modify: `tests/python/route_table.json` (append the new route at the END)
- Test: `tests/python/test_pinned_folder.py` (new)

**Interfaces:**
- Produces: `coding_store.pinned_folder_prompt(sid: str, brain_root: str) -> str` ("" when no usable folder).
- Produces: `POST /coding/session/{sid}/pin` form `path`, `brain` -> `{ok: true, folder: {id, name, path, exists, is_git} | null, in_brain: bool, brain_rel: str}`; 400 `{ok: false, error}`.
- Produces: `GET /coding/session/{sid}?brain=...` adds `folder` (same shape or null), `in_brain`, `brain_rel`.

- [ ] **Step 1: Write the failing test** `tests/python/test_pinned_folder.py`

```python
"""Pinned working folder for normal chats (0.154.0).

    python tests/python/test_pinned_folder.py
"""
import os, sys, tempfile, shutil, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import _paths  # noqa: F401  (adds server/ to sys.path)

tmp_state = tempfile.mkdtemp(prefix="pin-state-")
os.environ["JAVIS_STATE_DIR"] = tmp_state
import coding_store  # noqa: E402

fails = []
def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  " + str(extra)) if (extra and not cond) else ""))
    if not cond:
        fails.append(name)

try:
    brain = tempfile.mkdtemp(prefix="pin-brain-")
    proj = os.path.join(brain, "projects", "shop-site")
    os.makedirs(proj)
    outside = tempfile.mkdtemp(prefix="pin-out-")

    rec = coding_store.them_thu_muc(proj, brain=brain)
    coding_store.dat_rang_buoc("s-in", thu_muc_id=rec["id"])
    block = coding_store.pinned_folder_prompt("s-in", brain)
    check("block names the absolute working folder", os.path.realpath(proj) in block, block)
    check("block gives the brain-relative path for API brains", "projects/shop-site" in block, block)
    check("block never states a permission level", "Toàn quyền" not in block and "Tự động" not in block and "Plan" not in block, block)

    rec2 = coding_store.them_thu_muc(outside, brain=brain)
    coding_store.dat_rang_buoc("s-out", thu_muc_id=rec2["id"])
    block2 = coding_store.pinned_folder_prompt("s-out", brain)
    check("outside folder: no brain-relative line", "trong brain" not in block2 and os.path.realpath(outside) in block2, block2)

    check("no folder: empty block", coding_store.pinned_folder_prompt("s-none", brain) == "")
    shutil.rmtree(outside)
    check("folder deleted from disk: empty block (turn falls back to the brain)", coding_store.pinned_folder_prompt("s-out", brain) == "")

    import main  # noqa: E402
    row_chat = {"id": "s-in", "channel": "web"}
    row_code = {"id": "s-in", "channel": "coding:phien"}
    check("normal chat with a pin gets the pinned block", "projects/shop-site" in main._khoi_coding(row_chat, brain))
    check("coding session still gets the coding block", main._khoi_coding(row_code, brain) == coding_store.khoi_prompt("s-in"))
    check("normal chat with a pin still runs at full", main._muc_quyen_luot_chat(row_chat) == "full")

    from fastapi.testclient import TestClient  # noqa: E402
    c = TestClient(main.app)
    r = c.post("/coding/session/s-api/pin", data={"path": proj, "brain": brain})
    j = r.json()
    check("pin by absolute path binds the folder", r.status_code == 200 and j.get("ok") and j["folder"]["name"] == "shop-site", j)
    check("pin reports in_brain and brain_rel", j.get("in_brain") is True and j.get("brain_rel") == "projects/shop-site", j)
    check("turn cwd follows the pin", coding_store.cwd_cua_phien("s-api") == os.path.realpath(proj))
    g = c.get("/coding/session/s-api", params={"brain": brain}).json()
    check("GET session with brain returns folder and in_brain", g.get("folder", {}).get("name") == "shop-site" and g.get("in_brain") is True, g)
    bad = c.post("/coding/session/s-api/pin", data={"path": "../../etc", "brain": brain})
    check("relative path escaping the ceiling is rejected", bad.status_code == 400, bad.text)
    check("rejected pin keeps the previous folder", coding_store.cwd_cua_phien("s-api") == os.path.realpath(proj))
    off = c.post("/coding/session/s-api/pin", data={"path": "", "brain": brain}).json()
    check("empty path unpins", off.get("ok") and off.get("folder") is None and coding_store.cwd_cua_phien("s-api") == "", off)
finally:
    shutil.rmtree(tmp_state, ignore_errors=True)

if fails:
    print("\nFAIL - test_pinned_folder: %d" % len(fails)); sys.exit(1)
print("\nOK - test_pinned_folder: all pass")
```

Note: `main._khoi_coding` gains a second parameter `brain` in Step 3; the test calls it with `(row, brain)`. If `_paths` does not exist under that name, copy the import line used at the top of `tests/python/test_khung_go_server.py`. If `TestClient` requires login, copy the auth bypass used in `test_khung_go_server.py`.

- [ ] **Step 2: Run it to verify it fails**

Run: `PYTHONUTF8=1 D:/Project/Javis-OS/.venv/Scripts/python.exe tests/python/test_pinned_folder.py`
Expected: FAIL / AttributeError: module 'coding_store' has no attribute 'pinned_folder_prompt'

- [ ] **Step 3: Implement**

`server/coding_store.py`, after `khoi_prompt`:

```python
def pinned_folder_prompt(sid: str, brain_root: str) -> str:
    """Prompt block for a NORMAL chat that has a pinned working folder (0.154.0).

    Unlike `khoi_prompt` it never states a permission level: a normal chat keeps running at
    `full`, and a line about Plan/Auto would contradict what the hub actually allows. The
    brain-relative path matters for API brains, whose file tools are rooted at the brain.
    Returns "" when the session has no folder or the folder no longer exists.
    """
    cwd = cwd_cua_phien(sid)
    if not cwd:
        return ""
    lines = ["", "# === THƯ MỤC LÀM VIỆC ===", f"Thư mục làm việc: {cwd}"]
    try:
        rel = Path(cwd).resolve().relative_to(Path(brain_root).resolve()).as_posix()
    except (ValueError, OSError):
        rel = ""
    if rel and rel != ".":
        lines.append(f"Thư mục này nằm trong brain: {rel} (công cụ file của brain dùng đường dẫn này).")
    extra = [r["duong_dan"] for r in thu_muc_cua_phien(sid)
             if r["duong_dan"] != cwd and Path(r["duong_dan"]).is_dir()]
    if extra:
        lines.append("Thư mục khác cũng thuộc việc này, dùng ĐƯỜNG DẪN TUYỆT ĐỐI:")
        lines += [f"  - {p}" for p in extra]
    if la_git(cwd):
        branch = nhanh_hien_tai(cwd)
        if branch:
            lines.append(f"Nhánh git: {branch}")
    lines.append("Đọc, sửa và tạo file trong thư mục này trừ khi người dùng nói khác.")
    return "\n".join(lines) + "\n"
```

(The prompt text stays Vietnamese like `khoi_prompt`: prompts sent to the model are content, kept in the same language as the existing coding block. Code, names and comments are English.)

`server/main.py`, replace `_khoi_coding`:

```python
def _khoi_coding(row, brain: str = "") -> str:
    """Working-folder prompt block: the full coding block for Coding sessions, the short pinned
    folder block for every other session with a pinned folder, "" otherwise."""
    try:
        sid = (row or {}).get("id") or ""
        if not sid:
            return ""
        if str((row or {}).get("channel") or "").startswith("coding:"):
            return coding_store.khoi_prompt(sid)
        return coding_store.pinned_folder_prompt(sid, _brain_root(brain) if brain else "")
    except Exception:
        return ""
```

Then update every caller: `grep -n "_khoi_coding(" server/main.py` and pass the brain variable available at each call site (the same value passed to `_cwd_luot_chat(row, brain)` there).

`server/routes/coding.py`: extend deps and add the route.

```python
@dataclass
class CodingDeps:
    brain_keys: Callable[[str], list]
    resolve_path: Callable[[str, str], str] = None   # (brain, rel) -> absolute path, raises ValueError
    brain_root: Callable[[str], str] = None          # brain -> absolute brain root


def _folder_view(r) -> dict:
    """English view of a registered folder for the composer chip."""
    if not r:
        return None
    v = _ve_thu_muc(r)
    return {"id": v["id"], "name": v["ten"], "path": v["duong_dan"], "exists": v["co_that"], "is_git": v["la_git"]}


def _brain_fields(sid: str, brain: str) -> dict:
    """`in_brain` / `brain_rel` of the session's main folder, relative to the brain root."""
    out = {"in_brain": False, "brain_rel": ""}
    tm = coding_store.thu_muc(coding_store.rang_buoc(sid).get("thu_muc") or "")
    if not tm or not brain or not (_DEPS and _DEPS.brain_root):
        return out
    try:
        rel = Path(tm["duong_dan"]).resolve().relative_to(Path(_DEPS.brain_root(brain)).resolve()).as_posix()
        out = {"in_brain": True, "brain_rel": "" if rel == "." else rel}
    except (ValueError, OSError):
        pass
    return out
```

(add `from pathlib import Path` to the imports), inside `_make_router()`:

```python
    @r.post("/coding/session/{sid}/pin")
    async def coding_session_pin(sid: str, path: str = Form(""), brain: str = Form("")):
        """Pin (or unpin with an empty path) the conversation's working folder in one call."""
        raw = str(path or "").strip()
        try:
            if not raw:
                coding_store.dat_rang_buoc(sid, thu_muc_id="")
                return {"ok": True, "folder": None, "in_brain": False, "brain_rel": ""}
            if os.path.isabs(raw):
                target = raw
            else:
                if not (_DEPS and _DEPS.resolve_path):
                    return _400(localefmt.chu("Không đọc được đường dẫn.", "Cannot read path."))
                try:
                    target = _DEPS.resolve_path(brain, raw)
                except ValueError as e:
                    return _400(str(e))
            rec = coding_store.them_thu_muc(target, brain=brain)
            coding_store.dat_rang_buoc(sid, thu_muc_id=rec["id"])
        except coding_store.LoiCoding as e:
            return _400(str(e))
        return {"ok": True, "folder": _folder_view(rec), **_brain_fields(sid, brain)}
```

and in `coding_phien` (GET) add a `brain: str = Query("")` parameter and these keys to its returned dict:

```python
            "folder": _folder_view(tm),
            **_brain_fields(sid, brain),
```

`server/main.py` wiring (line ~21717):

```python
coding_routes.register(app, coding_routes.CodingDeps(
    brain_keys=_brain_keys,
    resolve_path=lambda b, rel: str(_safe_serve_path(b, rel)),
    brain_root=lambda b: str(_brain_root(b))))
```

Check `_safe_serve_path` raises `ValueError` for a path outside the ceiling; if it returns a non-existing path instead, `them_thu_muc` raises `LoiCoding` ("Folder does not exist"), which is also a 400.

Route table: run the repo's route table generator if one exists (`grep -rn "route_table.json" tools/ tests/python/*.py | head`); otherwise append the entry for `POST /coding/session/{sid}/pin` at the END of `tests/python/route_table.json` in the same shape as its neighbours, so other open PRs do not get renumbered.

- [ ] **Step 4: Run the test to verify it passes**

Run: `PYTHONUTF8=1 D:/Project/Javis-OS/.venv/Scripts/python.exe tests/python/test_pinned_folder.py`
Expected: `OK - test_pinned_folder: all pass`. Also run every Python test that mentions `_khoi_coding`, `coding_store` or `route_table`: `grep -lE "_khoi_coding|coding_store|route_table" tests/python/*.py`; all green except the machine-known reds.

- [ ] **Step 5: Commit**

```bash
git add server/coding_store.py server/routes/coding.py server/main.py tests/python/route_table.json tests/python/test_pinned_folder.py
git commit -m "Server: pinned working folder for normal chats (prompt block, /coding/session/{sid}/pin)"
```

---

### Task 2: Composer: pin folder panel and chip, remove folder upload

**Files:**
- Create: `dashboard/composer-folder.js`
- Modify: `dashboard/composer-plus.js` (generic `panel` item support; remove folder upload helpers; English comments)
- Modify: `dashboard/app.js` (remove `JavisAttach.queue`, `_hangDoi`, `_cho`; call `JavisPinnedFolder.claimPending(savedSessionId)` next to `JavisModelBar.claimPending`)
- Modify: `dashboard/index.html` (remove `#folderInput`; add `<script src="/static/composer-folder.js?v=1"></script>` right after composer-plus.js; bump composer-plus.js and app.js `?v=`)
- Modify: `dashboard/style.css` (`.cp-pin` chip)
- Modify: `dashboard/i18n/vi.json`, `dashboard/i18n/en.json`
- Test: `tests/js/test_pinned_folder.js` (new); update `tests/js/test_menu_cong.js`, `tests/js/test_khung_go.js`

**Interfaces:**
- Consumes: `POST /coding/session/{sid}/pin`, `GET /coding/session/{sid}?brain=` (Task 1).
- Produces: `window.JavisPinnedFolder = { claimPending(sid), current() -> folder|null, refresh() }`; event `javis:pinned-folder-changed` on `window` with `detail: {sid, folder}`.
- Produces (pure, node): `folderRows(items) -> [{name, path}]`, `chipLabel(name, max) -> string`, `createPinState() -> {request(sid), accept(seq, sid, data) -> bool, hold(path), takePending() -> path|null}`.
- Produces in composer-plus: registry items may define `panel(container, api)` where `api = {close(), back(), brain()}`; `JavisComposerMenu.openItem(id)` opens an item directly.

- [ ] **Step 1: Write the failing test** `tests/js/test_pinned_folder.js`

```js
/* Pinned working folder in the composer (0.154.0).

       node tests/js/test_pinned_folder.js
*/
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const F = require("../../dashboard/composer-folder.js");
const src = fs.readFileSync(path.join(ROOT, "dashboard/composer-folder.js"), "utf8");
const plus = fs.readFileSync(path.join(ROOT, "dashboard/composer-plus.js"), "utf8");
const app = fs.readFileSync(path.join(ROOT, "dashboard/app.js"), "latin1");
const html = fs.readFileSync(path.join(ROOT, "dashboard/index.html"), "utf8");
const vi = require("../../dashboard/i18n/vi.json"), en = require("../../dashboard/i18n/en.json");
let fails = [];
function check(name, cond, extra) { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  " + extra : "")); if (!cond) fails.push(name); }

const rows = F.folderRows([
  { name: "projects", type: "dir", path: "brain/projects" }, { name: "notes.md", type: "file", path: "brain/notes.md" },
  { name: ".git", type: "dir", path: "brain/.git" }, { name: "node_modules", type: "dir", path: "brain/node_modules" },
  { name: ".obsidian", type: "dir", path: "brain/.obsidian" }, { name: "shop", type: "dir", path: "brain/shop" }]);
check("folder rows keep only real, visible folders", rows.map(r => r.name).join(",") === "projects,shop", JSON.stringify(rows));
check("chip label keeps short names", F.chipLabel("shop", 18) === "shop");
check("chip label cuts long names with an ellipsis", F.chipLabel("a-very-long-project-folder-name", 18) === "a-very-long-proje\u2026");
check("chip label phone width", F.chipLabel("a-very-long-project", 10).length === 10);

const s = F.createPinState();
const a = s.request("s1"), b = s.request("s2");
check("only the newest request for the open session is accepted", s.accept(a, "s1", {}) === false && s.accept(b, "s2", {}) === true);
s.hold("brain/projects");
check("pending pin is taken once", s.takePending() === "brain/projects" && s.takePending() === null);

check("app.js claims the pending folder where it claims the pending model", /JavisModelBar\.claimPending\(savedSessionId\)[\s\S]{0,300}JavisPinnedFolder\.claimPending\(savedSessionId\)/.test(app));
check("composer-folder.js loads after composer-plus.js", html.indexOf("composer-plus.js") < html.indexOf("composer-folder.js"));
check("folder upload input is gone", html.indexOf('id="folderInput"') === -1 && plus.indexOf("folderInput") === -1);
check("folder upload helpers are gone", ["handleFolder", "pickFolderFiles", "runQueue"].every(n => plus.indexOf(n) === -1) && app.indexOf("queue: (files") === -1);
check("pin uses the one-call endpoint", src.indexOf('"/pin"') !== -1);
check("pin fires javis:pinned-folder-changed", src.indexOf('"javis:pinned-folder-changed"') !== -1);
check("browse row opens the shared folder picker", src.indexOf("JavisFolderPicker.open(") !== -1);
check("composer-plus supports panel items", /item\.panel/.test(plus) && /openItem:/.test(plus));
["cp.pin_folder", "cp.pin_search_ph", "cp.pin_browse", "cp.pin_unpin", "cp.pin_outside", "cp.pin_gone", "cp.pin_failed", "cp.pin_empty"]
  .forEach(k => check("i18n key " + k + " in vi and en", !!vi[k] && !!en[k]));
check("old folder upload strings removed", ["cp.folder", "cp.folder_skipped", "cp.folder_over", "cp.folder_empty", "cp.folder_flat"].every(k => !vi[k] && !en[k]));
check("no Vietnamese in composer-folder.js run code",
  !/[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]/i.test(src.replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "")));

if (fails.length) { console.log("\nFAIL - test_pinned_folder: " + fails.length); process.exit(1); }
console.log("\nOK - test_pinned_folder: all pass");
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node tests/js/test_pinned_folder.js`
Expected: FAIL with `Cannot find module '../../dashboard/composer-folder.js'`

- [ ] **Step 3: Implement**

3a. `dashboard/composer-plus.js`:
- Delete `MAX_FOLDER_FILES`, `UPLOAD_PARALLEL`, `SKIP_DIR`, `pickFolderFiles`, `runQueue`, `handleFolder`, `onFolder`, the `folderInput` listener in `init()`, and the `folder` registry entry. Export `pure = { createRegistry, shouldGoBack, brainAttachment }`.
- In `choose(r)`, before the `submenu` branch:

```js
    if (r.item && r.item.panel) { openPanel(r.item); return; }
```

and add:

```js
  // Panel items draw their own body (search box, custom rows) under a back row.
  function openPanel(it) {
    menu.innerHTML = '<button type="button" class="cp-mi cp-back" data-back="1">' + ICON.back + "<span>" + esc(tw(it.label)) + "</span></button>" +
      '<div class="cp-panel"></div>';
    view = [];
    it.panel(menu.querySelector(".cp-panel"), { close: close, back: function () { render(topRows()); }, brain: brain });
  }
  function openItem(id) {
    var it = reg.list().filter(function (x) { return x.id === id; })[0];
    if (!it || !menu) return;
    closeOthers();
    menu.hidden = false; if (btn) btn.setAttribute("aria-expanded", "true");
    if (it.panel) openPanel(it); else render(topRows());
  }
```

- Export: `window.JavisComposerMenu = { register: reg.register, list: reg.list, open: open, close: close, isOpen: isOpen, openItem: openItem, icon: ICON };`
- Translate every Vietnamese comment in the file to English.

3b. `dashboard/app.js` (byte-safe edit, assert each anchor occurs once):
- Remove the `queue: (files, note) => {...},` member and restore `upload: (f) => uploadFile(f),`.
- Remove the `_hangDoi` and `_cho` lines from `uploadFile` (restore `attachNote = "";` before `renderChips();` and drop both `if (att._cho) ...` lines).
- After `try { if (window.JavisModelBar) window.JavisModelBar.claimPending(savedSessionId); } catch (e) {}` add:

```js
    try { if (window.JavisPinnedFolder) window.JavisPinnedFolder.claimPending(savedSessionId); } catch (e) {}
```

`claimPending` must bind synchronously-enough for the first turn: it sends the `/pin` request and the server stores the binding before the WebSocket turn reaches `_cwd_luot_chat`. To guarantee order, `claimPending` returns the fetch promise and app.js keeps sending as today; the turn's server side reads the binding when the turn starts, which is after the pin request in practice. Ruling allowed here: if the visual check shows a race, make `sendMessage` await `window.JavisPinnedFolder.claimPending(...)` (it is already async).

3c. `dashboard/composer-folder.js` (new):

```js
/* composer-folder.js - pin a working folder for the open conversation (0.154.0).
 * The server runs the conversation's turns inside the pinned folder (coding_store binding).
 * Pure helpers are exported for node tests.
 */
(function () {
  "use strict";
  var HIDDEN = /^(\.|node_modules$|__pycache__$|\.venv$)/;

  function folderRows(items) {
    return (items || []).filter(function (x) { return x && x.type === "dir" && !HIDDEN.test(x.name || ""); })
      .map(function (x) { return { name: x.name, path: x.path }; });
  }
  function chipLabel(name, max) {
    var s = String(name || "");
    return s.length <= max ? s : s.slice(0, max - 1) + "\u2026";
  }
  function createPinState() {
    var seq = 0, openSid = "", pending = null;
    return {
      request: function (sid) { openSid = sid; return ++seq; },
      accept: function (n, sid) { return n === seq && sid === openSid; },
      hold: function (p) { pending = p; },
      takePending: function () { var p = pending; pending = null; return p; },
    };
  }

  var pure = { folderRows: folderRows, chipLabel: chipLabel, createPinState: createPinState };
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
  if (typeof document === "undefined") return;

  var state = createPinState(), folder = null, inBrain = false;
  function tw(k, v) { return window.t ? window.t(k, v) : k; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function brain() { try { return (window.JavisSessions && window.JavisSessions.brain()) || "brain"; } catch (e) { return "brain"; } }
  function sid() { try { return (window.JavisSessions && window.JavisSessions.current()) || ""; } catch (e) { return ""; } }
  function getJson(url, opt) { return fetch(url, Object.assign({ credentials: "same-origin" }, opt || {})).then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { j._status = r.status; return j; }); }).catch(function () { return { ok: false, error: tw("cp.pin_failed") }; }); }
  function narrow() { return window.matchMedia && window.matchMedia("(max-width: 860px)").matches; }

  function announce() {
    try { window.dispatchEvent(new CustomEvent("javis:pinned-folder-changed", { detail: { sid: sid(), folder: folder } })); } catch (e) {}
  }
  function renderChip() {
    var host = document.getElementById("cpChips");
    if (!host) return;
    var chip = document.getElementById("pinChip");
    if (!folder) { if (chip) chip.remove(); return; }
    if (!chip) {
      chip = document.createElement("button");
      chip.type = "button"; chip.id = "pinChip"; chip.className = "cp-pin";
      chip.addEventListener("click", function (e) { e.stopPropagation(); if (window.JavisComposerMenu) window.JavisComposerMenu.openItem("folder"); });
      var fast = document.getElementById("fastBtn");
      host.insertBefore(chip, fast ? fast.nextSibling : null);
    }
    chip.classList.toggle("cp-pin-gone", !folder.exists);
    var tip = folder.path + (folder.exists ? "" : "\n" + tw("cp.pin_gone")) + (inBrain ? "" : "\n" + tw("cp.pin_outside"));
    chip.title = tip;
    chip.setAttribute("aria-label", tw("cp.pin_folder") + ": " + folder.name);
    chip.innerHTML = (window.JavisComposerMenu ? window.JavisComposerMenu.icon.folder : "") + "<span>" + esc(chipLabel(folder.name, narrow() ? 10 : 18)) + "</span>";
  }
  function apply(d) {
    folder = (d && d.folder) || null; inBrain = !!(d && d.in_brain);
    renderChip(); announce();
  }
  function refresh() {
    var id = sid(), n = state.request(id);
    if (!id) { apply(null); return Promise.resolve(); }
    return getJson("/coding/session/" + encodeURIComponent(id) + "?brain=" + encodeURIComponent(brain())).then(function (d) {
      if (state.accept(n, id)) apply(d);
    });
  }
  function pin(path) {
    var id = sid();
    if (!id) { state.hold(path); apply({ folder: { name: String(path).split(/[\\/]/).filter(Boolean).pop() || path, path: path, exists: true }, in_brain: !/^([A-Za-z]:|\/)/.test(path) }); return Promise.resolve(""); }
    var body = new FormData(); body.append("path", path); body.append("brain", brain());
    var n = state.request(id);
    return getJson("/coding/session/" + encodeURIComponent(id) + "/pin", { method: "POST", body: body }).then(function (d) {
      if (!d || d.ok === false) return (d && d.error) || tw("cp.pin_failed");
      if (state.accept(n, id)) apply(d);
      return "";
    });
  }
  function claimPending(newSid) {
    var p = state.takePending();
    if (!p || !newSid) return Promise.resolve();
    var body = new FormData(); body.append("path", p); body.append("brain", brain());
    var n = state.request(newSid);
    return getJson("/coding/session/" + encodeURIComponent(newSid) + "/pin", { method: "POST", body: body }).then(function (d) {
      if (d && d.ok !== false && state.accept(n, newSid)) apply(d);
    });
  }

  function panel(box, api) {
    var rowsHtml = function (list) {
      return list.map(function (r, i) {
        return '<button type="button" class="cp-mi" data-pin="' + i + '">' + window.JavisComposerMenu.icon.folder +
          '<span class="cp-mi-lbl">' + esc(r.name) + '</span><span class="cp-mi-hint">' + esc(r.path) + "</span></button>";
      }).join("");
    };
    var head = folder ? '<button type="button" class="cp-mi" data-unpin="1">' + esc(tw("cp.pin_unpin")) +
      '<span class="cp-mi-hint">' + esc(folder.name) + '</span></button><div class="cp-sep"></div>' : "";
    box.innerHTML = head + '<input type="search" class="cp-search" placeholder="' + esc(tw("cp.pin_search_ph")) + '" aria-label="' + esc(tw("cp.pin_search_ph")) + '">' +
      '<div class="cp-results"></div><div class="cp-sep"></div><button type="button" class="cp-mi" data-browse="1">' +
      esc(tw("cp.pin_browse")) + '</button><div class="cp-pin-err" role="status"></div>';
    var input = box.querySelector(".cp-search"), out = box.querySelector(".cp-results"), err = box.querySelector(".cp-pin-err");
    var list = [], timer = 0, seq = 0;
    function show(items) { list = items; out.innerHTML = items.length ? rowsHtml(items) : '<div class="cp-empty">' + esc(tw("cp.pin_empty")) + "</div>"; }
    function load() {
      var q = input.value.trim(), n = ++seq;
      var url = q ? "/files/search?mode=name&include_dirs=1&limit=30&brain=" + encodeURIComponent(brain()) + "&q=" + encodeURIComponent(q)
        : "/files/list?brain=" + encodeURIComponent(brain());
      getJson(url).then(function (d) { if (n === seq) show(folderRows((d && d.items) || []).map(function (r) {
        return { name: r.name, path: r.path || ((d.path ? d.path + "/" : "") + r.name) }; })); });
    }
    function done(msg) { if (msg) { err.textContent = msg; return; } api.close(); var i = document.getElementById("chatInput"); if (i) i.focus(); }
    box.addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      if (b.dataset.unpin) { pin("").then(done); return; }
      if (b.dataset.browse) {
        api.close();
        if (window.JavisFolderPicker) window.JavisFolderPicker.open({ tieuDe: tw("cp.pin_folder"), nhanDung: tw("cp.pin_folder"), demMd: false, brain: brain(),
          chon: function (p) { return pin(p); } });
        return;
      }
      if (b.dataset.pin !== undefined) { var r = list[+b.dataset.pin]; if (r) pin(r.path).then(done); }
    });
    input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(load, 180); });
    input.focus();
    load();
  }

  function init() {
    if (!window.JavisComposerMenu) return;
    window.JavisComposerMenu.register({ id: "folder", order: 20, icon: window.JavisComposerMenu.icon.folder, label: "cp.pin_folder",
      hint: function () { return folder ? folder.name : ""; }, panel: panel });
    window.addEventListener("javis:sessions-changed", refresh);
    window.addEventListener("resize", renderChip);
    refresh();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();

  window.JavisPinnedFolder = { claimPending: claimPending, current: function () { return folder; }, refresh: refresh };
})();
```

Note on `pin("")` (unpin) with no session: `sid()` empty means nothing is bound yet, so clear the held pending path instead: in `pin`, when `!id && !path`, call `state.takePending()` and `apply(null)`.

3d. `dashboard/style.css` (next to `.cp-fast` rules):

```css
.cp-pin { display: inline-flex; align-items: center; gap: 5px; height: 30px; max-width: 190px; padding: 0 10px; border-radius: 999px;
  border: 1px solid var(--border); background: transparent; color: var(--text2); font: inherit; font-size: 12.5px; cursor: pointer; }
.cp-pin:hover, .cp-pin:focus-visible { border-color: var(--accent); color: var(--text); }
.cp-pin .cp-ic { width: 14px; height: 14px; flex: none; }
.cp-pin span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cp-pin-gone span { text-decoration: line-through; opacity: .7; }
.cp-pin-err { color: var(--warn-ink); font-size: 12.5px; padding: 0 10px; }
.cp-pin-err:empty { display: none; }
@media (max-width: 860px) { .cp-pin { max-width: 120px; padding: 0 8px; } }
```

3e. i18n (vi / en), insert next to the other `cp.*` keys, and remove `cp.folder`, `cp.folder_skipped`, `cp.folder_over`, `cp.folder_empty`, `cp.folder_flat`:

| key | vi | en |
|---|---|---|
| cp.pin_folder | Ghim thư mục làm việc | Pin working folder |
| cp.pin_search_ph | Tìm thư mục trong brain... | Find a folder in the brain... |
| cp.pin_browse | Duyệt thư mục khác... | Browse another folder... |
| cp.pin_unpin | Bỏ ghim | Unpin |
| cp.pin_outside | Thư mục ngoài brain: chỉ bộ não CLI làm việc được ở đây. | Outside the brain: only CLI brains can work here. |
| cp.pin_gone | Không còn thấy thư mục này trên đĩa. | This folder is no longer on disk. |
| cp.pin_failed | Không ghim được thư mục này. | Could not pin this folder. |
| cp.pin_empty | Không có thư mục nào | No folders |

3f. `tests/js/test_menu_cong.js`: delete the folder queue checks (`handleFolder`, `pickFolderFiles`, `runQueue`, `JavisAttach.queue`, `_hangDoi`, `_cho`) and the `folder` id from the default-id list; rewrite all remaining check names and comments in English. `tests/js/test_khung_go.js`: remove any `folderInput` expectation, translate check names to English.

- [ ] **Step 4: Run tests to verify they pass**

Run: `node tests/js/test_pinned_folder.js && node tests/js/test_menu_cong.js && node tests/js/test_khung_go.js && node tests/js/test_i18n.mjs`
Expected: all four print `OK`.

- [ ] **Step 5: Commit**

```bash
git add dashboard/composer-folder.js dashboard/composer-plus.js dashboard/app.js dashboard/index.html dashboard/style.css dashboard/i18n/vi.json dashboard/i18n/en.json tests/js/test_pinned_folder.js tests/js/test_menu_cong.js tests/js/test_khung_go.js
git commit -m "Composer: pin a working folder per conversation; drop the folder upload"
```

---

### Task 3: Coding page: drop the duplicate folder picker

**Files:**
- Modify: `dashboard/coding.js`
- Modify: `dashboard/i18n/vi.json`, `dashboard/i18n/en.json` (remove keys no longer used)
- Test: `tests/js/test_trang_coding.js`

**Interfaces:**
- Consumes: event `javis:pinned-folder-changed` (Task 2).

- [ ] **Step 1: Update the test first** (`tests/js/test_trang_coding.js`)

Replace the two checks that expect the folder chip and the in-brain line:
- `"chưa gắn thư mục thì nói rõ đang làm trong bộ não"` becomes:

```js
check("the Coding page no longer shows its own in-brain line (the composer chip shows the folder)",
  !/coding\.in_brain/.test(CD) && !VI["coding.in_brain"] && !EN["coding.in_brain"]);
```

- `"chưa gắn thư mục thì có chip mời chọn VÀ chip mức quyền"` becomes:

```js
check("no folder: only the permission chip, no folder chip",
  (() => { const c = M.chipHtml({}, null);
    return !c.includes('data-cd="thumuc"') && c.includes('data-cd="quyen"')
      && !/data-cd="(nhanh|worktree|diemhoi)"/.test(c); })());
check("with a folder: no folder chip either (the composer chip owns it)",
  !M.chipHtml({ muc_quyen: "auto" }, { id: "1", ten: "x", duong_dan: "/x", la_git: true }).includes('data-cd="thumuc"'));
check("the page refreshes its git chips when the composer pins or unpins", CD.indexOf('"javis:pinned-folder-changed"') !== -1);
check("the folder picker of the Coding page is gone", !/moKhungThemThuMuc|menuThuMuc|chip_pick_folder/.test(CD));
```

- The check `"chữ trên giao diện nói THƯ MỤC"` (needs `coding.add_folder`) is removed together with the key. Keep the "old repo keys removed" check.
- Any other check that reads `coding.add_folder`, `coding.detach_folder`, `coding.forget_folder`, `coding.forget_confirm`, `coding.add_err`, `coding.folder_main`, `coding.folder_gone`: delete it if it only asserted the removed menu.

- [ ] **Step 2: Run it to verify it fails**

Run: `node tests/js/test_trang_coding.js`
Expected: FAIL on the new checks (folder chip still present, `coding.in_brain` still used).

- [ ] **Step 3: Implement in `dashboard/coding.js`**
- `chipHtml`: drop the `thumuc` chip in both branches; with `!tm` return `chipQuyen()`; with a folder return the git chips (when `tm.la_git`) plus `chipQuyen()`. Update its doc comment (English): the folder itself is shown by the composer chip.
- `bamChip`: remove the `thumuc` branch. Delete `menuThuMuc`, `boThuMuc`, `moKhungThemThuMuc`, `chaCuaThuMucDangGan`, and `taiThuMuc` plus `S.thuMuc` if nothing else uses them (`grep -n "taiThuMuc\|S.thuMuc" dashboard/coding.js`).
- `taiRangBuoc`: delete the `#cdIdentity` block; `khung()`: delete the `<div class="cd-id" id="cdIdentity"></div>` node; `veLoi` writes into `#cdChips` instead (prepend a `<small class="ws-err">`), or uses `W.toast` if present.
- In the page's mount (where `active` becomes true) add, and remove in unmount:

```js
  function onPinned(e) { var d = (e && e.detail) || {}; if (active && d.sid && d.sid === sid()) taiRangBuoc(d.sid); }
  // mount:   W.addEventListener("javis:pinned-folder-changed", onPinned);
  // unmount: W.removeEventListener("javis:pinned-folder-changed", onPinned);
```

- Remove i18n keys that are now unused in every file: check each with `grep -rn "<key>" dashboard/*.js`; candidates `coding.in_brain`, `coding.chip_pick_folder`, `coding.add_folder`, `coding.detach_folder`, `coding.forget_folder`, `coding.forget_confirm`, `coding.add_err`, `coding.folder_main`, `coding.folder_gone`.
- New comments in English.

- [ ] **Step 4: Run tests**

Run: `node tests/js/test_trang_coding.js && node tests/js/test_i18n.mjs && node tests/js/test_code_terminal.js`
Expected: all `OK`.

- [ ] **Step 5: Commit**

```bash
git add dashboard/coding.js dashboard/i18n/vi.json dashboard/i18n/en.json tests/js/test_trang_coding.js
git commit -m "Coding page: the composer chip owns the working folder; drop the page's own picker"
```

---

### Task 4: Agent Work tab: two dropdowns and a smaller type scale

**Files:**
- Modify: `dashboard/agent-jobs.js`
- Modify: `dashboard/console.css` (`.aj*` rules around line 2989-3060)
- Modify: `dashboard/i18n/vi.json`, `dashboard/i18n/en.json` (two labels)
- Test: `tests/js/test_agent_jobs_0142.js`

**Interfaces:**
- Produces: `toolbarHtml(data, ui) -> string` exported on the module api (replaces `filterHtml` and `sourceFilterHtml` in `api`).

- [ ] **Step 1: Write the failing test** (append to `tests/js/test_agent_jobs_0142.js`, and replace the two `btn("aj-chip", { ajSource: ... })` clicks with select changes)

```js
// Compact toolbar (0.154.0): two native selects instead of two chip rows.
{
  const data = { counts: { running: 1, waiting: 2, needs_you: 3, done: 4 }, source_counts: { team: 1, chat: 2, auto: 0 } };
  const tb = AJ.toolbarHtml(data, { source: "", filter: "" });
  check("toolbar has a source select and a status select", /<select class="aj-sel aj-src-sel"/.test(tb) && /<select class="aj-sel aj-status-sel"/.test(tb));
  check("options carry their counts", /All[^<]*\(3\)|\(3\)/.test(tb) && tb.indexOf("(10)") !== -1);
  check("selected option follows the ui state", /value="needs_you" selected/.test(AJ.toolbarHtml(data, { source: "", filter: "needs_you" })));
  check("amber dot when something needs you and the filter is elsewhere", tb.indexOf("aj-dot") !== -1);
  check("no amber dot when already filtered to needs you", AJ.toolbarHtml(data, { source: "", filter: "needs_you" }).indexOf("aj-dot") === -1);
  check("no chip rows left", tb.indexOf("aj-chip") === -1);
}
```

In the mounted-flow section, replace:

```js
  host.fire("click", btn("aj-chip", { ajSource: "team" }));
```

with

```js
  host.fire("input", Object.assign(field("aj-src-sel", "team"), {}));
  host.fire("change", field("aj-src-sel", "team"));
```

and assert one load only:

```js
  check("select change reloads once (input + change do not double-load)", calls.length === 1 && /source=team/.test(calls[0].url), calls.map((c) => c.url).join(" | "));
```

then reset with `host.fire("change", field("aj-src-sel", ""));`. The `fire` helper passes `{ target }`; extend it to pass the event type: `fire(t, target) { (L[t] || []).forEach((f) => f({ type: t, target })); }`.

- [ ] **Step 2: Run it to verify it fails**

Run: `node tests/js/test_agent_jobs_0142.js`
Expected: FAIL with `AJ.toolbarHtml is not a function`.

- [ ] **Step 3: Implement**

`dashboard/agent-jobs.js`: replace `sourceFilterHtml` and `filterHtml` with:

```js
  // One compact row: two native selects (keyboard, screen readers and phone pickers work, nothing overflows).
  function toolbarHtml(data, ui) {
    var sc = (data && data.source_counts) || {}, counts = (data && data.counts) || {};
    var partial = data && data.counts_partial && data.counts_partial.done;
    var srcTotal = SOURCES.reduce(function (a, s) { return a + (sc[s] || 0); }, 0);
    var stTotal = BUCKETS.reduce(function (a, b) { return a + (counts[b] || 0); }, 0);
    var opt = function (value, label, n, cur) {
      return '<option value="' + esc(value) + '"' + (cur === value ? " selected" : "") + ">" + esc(label) + " (" + esc(n) + ")</option>";
    };
    var src = ui.source || "", st = ui.filter || "";
    var dot = (counts.needs_you || 0) > 0 && st !== "needs_you" ? '<span class="aj-dot" aria-hidden="true"></span>' : "";
    return '<div class="aj-toolbar">' +
      '<label class="aj-field"><span class="aj-field-lbl">' + esc(tw("ajobs.srcf.label")) + "</span>" +
      '<select class="aj-sel aj-src-sel">' + opt("", tw("ajobs.srcf.all"), srcTotal, src) +
      SOURCES.map(function (s) { return opt(s, tw(SOURCE_CHIP[s]), sc[s] || 0, src); }).join("") + "</select></label>" +
      '<label class="aj-field"><span class="aj-field-lbl">' + esc(tw("ajobs.filter")) + "</span>" + dot +
      '<select class="aj-sel aj-status-sel">' + opt("", tw("ajobs.all"), stTotal + (partial ? "+" : ""), st) +
      ["running", "waiting", "needs_you", "done"].map(function (b) {
        return opt(b, tw(BUCKET_KEY[b]), (counts[b] || 0) + (b === "done" && partial ? "+" : ""), st);
      }).join("") + "</select></label></div>";
  }
```

Use `toolbarHtml(data, ui)` where `sourceFilterHtml(data, ui) + filterHtml(data, ui)` was concatenated in `html()`. Keep `chipHtml` (still used by the assign form's kind toggle). In `onInput(e)` add at the top, after `if (!cl) return;`:

```js
      if (cl.contains("aj-src-sel") || cl.contains("aj-status-sel")) {
        if (e.type === "input") return;            // a select fires input AND change: act once
        if (cl.contains("aj-src-sel")) st.ui.source = t.value; else st.ui.filter = t.value;
        draw(); load(false); return;
      }
```

Remove the now-dead `d.ajFilter` / `d.ajSource` branches in `onClick`. Update the `api` export: replace `filterHtml: filterHtml, sourceFilterHtml: sourceFilterHtml` with `toolbarHtml: toolbarHtml`. If other tests import `filterHtml`/`sourceFilterHtml` (`grep -rn "filterHtml" tests/`), switch them to `toolbarHtml`.

Labels: check `ajobs.srcf.label` and `ajobs.filter` read as short field labels ("Nguồn" / "Trạng thái", "Source" / "Status"); if not, add `ajobs.tb_source` and `ajobs.tb_status` with those values in vi/en and use them.

`dashboard/console.css`: replace `.aj-filters`, `.aj-chip*` (except `.aj-kind .aj-chip`, which the assign form still uses), `.aj-n` sizes, and lower the type scale:

```css
.aj { font-size: 13px; }
.aj-toolbar { display: flex; gap: 8px; align-items: flex-end; }
.aj-field { position: relative; display: flex; flex-direction: column; gap: 3px; flex: 1 1 0; min-width: 0; }
.aj-field-lbl { font-size: 11.5px; color: var(--text3); }
.aj-sel { appearance: none; -webkit-appearance: none; width: 100%; height: 32px; padding: 0 26px 0 10px; border-radius: 9px;
  border: 1px solid var(--border); background: var(--surface-1) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%23999' stroke-width='3'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E") no-repeat right 9px center;
  color: var(--text); font: inherit; font-size: 13px; text-overflow: ellipsis; }
.aj-sel:focus { outline: none; border-color: var(--accent); }
.aj-dot { position: absolute; top: 2px; right: 2px; width: 7px; height: 7px; border-radius: 50%; background: var(--warn-ink); }
.aj-head > .ws-btn, .aj .aj-acts .ws-btn { min-height: 32px; font-size: 13px; }
.aj-text, .aj-help, .aj-foot, .aj-next, .aj-link, .aj .aj-link .aj-link-open { font-size: 13px; }
.aj-title { font-size: 14px; }
.aj-meta, .aj-role, .aj-line, .aj-n { font-size: 12px; }
.aj-sec-h { font-size: 12px; }
.aj-job { padding: 10px; }
@media (pointer: coarse) {
  .aj-sel, .aj-head > .ws-btn, .aj .aj-acts .ws-btn, .aj .aj-link .aj-link-open { min-height: 44px; height: auto; }
}
```

Delete the old 16px declarations these replace (`.aj-head > .ws-btn ... font-size: 16px`, `.aj-text ... 16px`, `.aj-help, .aj-foot ... 16px`, `.aj-n 16px`, `.aj-sec-h 16px`, `.aj-next 16px`, `.aj-link 16px`, `.aj .aj-link .aj-link-open 16px`, `.aj-filters`, `.aj-chip` base and `.aj-sources` rules) rather than overriding them, so the file has one source of truth. Bump `console.css?v=` in index.html.

- [ ] **Step 4: Run tests**

Run: `node tests/js/test_agent_jobs_0142.js && node tests/js/test_i18n.mjs && node tests/js/test_workspace.js`
Expected: all `OK`.

- [ ] **Step 5: Commit**

```bash
git add dashboard/agent-jobs.js dashboard/console.css dashboard/index.html dashboard/i18n/vi.json dashboard/i18n/en.json tests/js/test_agent_jobs_0142.js
git commit -m "Agent Work tab: two compact dropdowns and a smaller type scale"
```

---

### Task 5: Housekeeping: English in PR #663 code, dev convention

**Files:**
- Modify: `dashboard/effort-slider.js`, `tests/js/test_thanh_truot_effort.js`, `tests/js/test_tia_set_fast.js`, `tests/js/test_khung_go.js` (if not done in Task 2), the comments PR #663 added in `dashboard/model-picker.js`, `dashboard/mobile-chat.js`, `dashboard/console.js`, `dashboard/chat-slash.js`, `dashboard/workspace.js`, `dashboard/style.css`, `server/main.py` (`/files/resolve` docstring), `tests/python/test_khung_go_server.py`
- Modify: `docs/quy-uoc-dev.md`

- [ ] **Step 1: Find the lines.** `git diff 1d1b52fa..3c398a8d -U0 -- dashboard server tests | grep '^+' | grep -P '[\x{00C0}-\x{1EF9}]'` lists every added line with Vietnamese letters. User-facing strings in `i18n/*.json` are out of scope.
- [ ] **Step 2: Translate** those comments, docstrings and `check(...)` names to English, keeping meaning. Do not change code behavior or string literals that tests or the UI read.
- [ ] **Step 3: `docs/quy-uoc-dev.md`**: replace the bullet "**Module, tên hàm, comment MỚI:** tiếng Anh. Sửa trong một file sẵn có thì theo ngôn ngữ của file đó cho nhất quán; ..." with: "**Mọi code mới viết tiếng Anh**: tên module, hàm, biến, comment, docstring, tên test và câu in trong `check(...)`, kể cả khi thêm vào một file cũ đang viết tiếng Việt. Không dịch lại phần code cũ không đụng tới. Chữ hiện cho người dùng đi qua i18n (`vi.json` có dấu, `en.json`). Chủ repo chốt 15/10/2026."
- [ ] **Step 4: Run** the whole JS suite (`for f in tests/js/test_*.js tests/js/*.mjs; do node "$f" >/dev/null 2>&1 || echo "RED $f"; done`) and the edited Python test. Expected: no RED.
- [ ] **Step 5: Commit** `git commit -am "English comments and test names for the 0.153.0 composer code; dev convention: all new code in English"`

---

### Task 6: Release: version, changelog, docs, visual check

**Files:**
- Modify: `VERSION`, `CHANGELOG.md`, `CHANGELOG.en.md`, `docs/02-tro-chuyen-va-giong-noi.md`, `docs/en/02-chat-and-voice.md`, and the Coding page docs if they describe "Pick a folder" (`grep -rln "Chọn thư mục\|Pick a folder" docs/`)

- [ ] **Step 1: Reserve the version.** `git fetch origin && git show origin/main:VERSION && gh pr list --state open --json title --jq '.[].title'`; take the next number above both (0.154.0 unless claimed). Write `VERSION`.
- [ ] **Step 2: CHANGELOG blocks** (vi in CHANGELOG.md, en in CHANGELOG.en.md, same `### Cải thiện` / `### Improved` group): pin working folder from "+" (chip next to the bolt, per conversation, brain folders first plus browse), Coding page uses the same chip, agent Work tab dropdowns and smaller text. Phone-screen friendly, no em dash.
- [ ] **Step 3: Docs.** In docs/02 (vi/en) replace the "+" menu row's "attach a whole folder" with "pin a working folder", add the folder chip to the button table, and update the Coding docs section that describes picking a folder.
- [ ] **Step 4: Visual check** on a sandbox server: `JAVIS_PORT=7788 D:/Project/Javis-OS/.venv/Scripts/python.exe server/main.py` from the worktree (background). Check: pin from the menu (brain folder, search, browse), chip shows and tooltip, unpin, pin on an empty chat then send (first turn runs in the folder: ask "pwd" on a CLI brain or read the turn's cwd in the log), Coding page has no folder chip and its git chips refresh after pinning a git folder, agent Work tab dropdowns at desktop and 375px, dark and light. Stop the sandbox and restore its state files exactly as before the run.
- [ ] **Step 5: Full verification.** JS suite all green; Python: every file that greps for a changed file name or removed string, plus test_pinned_folder; known machine-reds only.
- [ ] **Step 6: Commit, push, PR, auto-merge (rebase).** `git commit -am "0.154.0: pin a working folder from the composer, compact agent Work tab"`, `git push -u origin claude/composer-pin-folder`, `gh pr create` (English title and body ending with the Claude Code line), then enable auto-merge with rebase.
