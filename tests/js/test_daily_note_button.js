/* The "Today's note" button on the Vault toolbar, and its Ctrl/Cmd+D shortcut.

       node tests/js/test_daily_note_button.js

   The button finds the Daily Log folder and opens today's note, creating it from a template when
   it is missing. Three places break SILENTLY, so they are guarded:

     1. Folder name. Real vaults have "01 - Daily Log", "Daily Log" and "Daily" (the server matches
        them just as flexibly in STANDARD_STRUCTURE). Hard-coding one name creates a second folder
        right next to the one in use, and each day's note lands in two different places.
     2. Date. toISOString() is UTC, so in the evening in Vietnam (UTC+7) the note jumps to
        TOMORROW. The date must come from local time.
     3. Overwrite. Writing the template again on a second click the same day wipes everything
        written since morning. */
const fs = require("fs");
const path = require("path");
const vm = require("node:vm");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const CON = D("console.js");
const HTML = D("index.html");
const VI = JSON.parse(D("i18n/vi.json"));
const EN = JSON.parse(D("i18n/en.json"));

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Pure functions - run the REAL code from console.js
// ============================================================
const start = CON.indexOf("const _VT_DAILY_RE");
const end = CON.indexOf("  // Open TODAY's note", start);
check("the daily-note helpers can be pulled out of console.js", start > 0 && end > start);

const ctx = { window: { t: (k) => "<" + k + ">" }, LOC: () => "vi-VN" };
const src = CON.slice(start, end) + "; ({ _VT_DAILY_RE, _vtTodayDate, _vtDailyFolder, _vtDailyTemplate })";
const H = vm.runInNewContext(src, ctx);

// --- 1a. Finding the folder ---
const dir = (n) => ({ name: n, type: "dir" });
check("matches a numbered folder", H._vtDailyFolder([dir("01 - Daily Log")]) === "01 - Daily Log");
check("matches an unnumbered folder", H._vtDailyFolder([dir("Daily Log")]) === "Daily Log");
check("matches the short name", H._vtDailyFolder([dir("daily")]) === "daily");
check("CANARY: a vault without the folder uses the standard name so /files/write creates it",
  H._vtDailyFolder([dir("wiki"), dir("sources")]) === "01 - Daily Log");
check("a FILE with the same name is not taken for the folder",
  H._vtDailyFolder([{ name: "Daily Log", type: "file" }]) === "01 - Daily Log");
check("look-alike names are not matched by mistake",
  H._vtDailyFolder([dir("Daily Logs"), dir("My Daily Log")]) === "01 - Daily Log");
check("an empty or missing list does not blow up", H._vtDailyFolder(null) === "01 - Daily Log");

// --- 1b. The date in LOCAL time, not UTC ---
// 23:30 on the 11th in UTC+7 is 16:30 the same day in UTC, but 00:30 on the 12th is still the
// 11th in UTC. The dates below are built in LOCAL time, so the test holds in any CI time zone.
check("the date follows local time, zero-padded", H._vtTodayDate(new Date(2026, 8, 5, 23, 30)) === "2026-09-05");
check("CANARY: just after midnight does not jump to another day",
  H._vtTodayDate(new Date(2026, 0, 1, 0, 30)) === "2026-01-01");
check("no argument means today", /^\d{4}-\d{2}-\d{2}$/.test(H._vtTodayDate()));

// --- 1c. The note template ---
const tpl = H._vtDailyTemplate("2026-09-11");
check("the template has frontmatter type: daily", /^---\ntype: daily\ndate: 2026-09-11\n/.test(tpl));
check("the template's title is the date", tpl.includes("# 2026-09-11"));
check("the template has the weekday in the UI locale", /# 2026-09-11 - \S/.test(tpl));
check("the template has a clickable task line (dataview can pick it up)", tpl.includes("- [ ] "));
check("the template's text goes through the dictionary, not hard-coded",
  tpl.includes("<cs.vt_daily_tasks>") && tpl.includes("<cs.vt_daily_notes>"));

// ============================================================
// 2. The button and its wiring
// ============================================================
check("the Vault toolbar has the button", HTML.includes('id="vtDaily"'));
check("the button sits next to the new file/folder buttons",
  HTML.indexOf('id="vtNewFile"') < HTML.indexOf('id="vtDaily"')
  && HTML.indexOf('id="vtDaily"') < HTML.indexOf('id="vtRefresh"'));
check("the button has a translatable tooltip", HTML.includes('data-i18n-title="vault.daily"'));
check("the button is wired in _vtWire", /getElementById\("vtDaily"\)/.test(CON));
check("clicking the button calls the right function", /dn\.onclick = \(\) => _vtOpenTodayNote\(\)/.test(CON));

// An existing note is only OPENED: /files/read runs first and /files/write sits in the missing branch.
const body = CON.slice(CON.indexOf("async function _vtOpenTodayNote"),
                       CON.indexOf("function _vtWire()"));
check("existence is checked with /files/read before writing",
  body.indexOf("/files/read") > 0 && body.indexOf("/files/read") < body.indexOf("/files/write"));
check("CANARY: an existing note is NOT overwritten", /if \(!exists\) \{/.test(body));
check("the note is always opened for editing at the end", /openNote\(rel,/.test(body));
check("a write error is reported instead of silently opening an empty file",
  body.includes("cs.vt_daily_fail") && /return;/.test(body));

check("the daily note opens in the current frame, not full screen", /openNote\(rel, \{[^}]*\}, \{ inPlace: true \}\)/.test(body));
// 0.432.1: every file now opens in the frame; only the maximize button (or opts.full) goes full screen, and
// `inPlace` still forces the frame even when the editor was left maximized.
check("openNote never goes full screen by itself, inPlace forces the frame",
  /if \(opts && opts\.full\) ed\.classList\.add\("ne-full"\);\s*else if \(!daMo \|\| \(opts && opts\.inPlace\)\) ed\.classList\.remove\("ne-full"\);/.test(CON));
check("CANARY: only a 404 creates a new note, other errors do not overwrite", /exists = r\.status !== 404/.test(body));

// ============================================================
// 2b. The Ctrl/Cmd+D shortcut - run the REAL key handler
// ============================================================
const keyStart = CON.indexOf("function _vtDailyKey");
const keyEnd = CON.indexOf('document.addEventListener("keydown", _vtDailyKey)', keyStart);
check("the daily-note key handler is attached at document level", keyStart > 0 && keyEnd > keyStart);
let calls = 0;
const nav = { platform: "Win32" };
const K = vm.runInNewContext(CON.slice(keyStart, keyEnd) + "; _vtDailyKey",
  { _vtOpenTodayNote: () => { calls++; }, navigator: nav });
// A key target inside the note editor / Vault panel, or outside them (chat box, other pages).
const inEditor = { closest: (sel) => (/#noteEditor/.test(sel) ? {} : null) };
const outside = { closest: () => null };
const press = (o) => { let blocked = false; K(Object.assign({ key: "d", code: "KeyD", target: inEditor, preventDefault: () => { blocked = true; } }, o)); return blocked; };
nav.platform = "Win32";
calls = 0; check("Ctrl+D opens the daily note and blocks the bookmark", press({ ctrlKey: true }) && calls === 1);
calls = 0; check("a Vietnamese keyboard layout still matches by code", press({ ctrlKey: true, key: "đ" }) && calls === 1);
calls = 0; check("holding the key does not keep opening", press({ ctrlKey: true, repeat: true }) && calls === 0);
calls = 0; check("Ctrl+Shift+D is not taken", !press({ ctrlKey: true, shiftKey: true }) && calls === 0);
calls = 0; check("a plain d while typing is not taken", !press({}) && calls === 0);
calls = 0; check("CANARY: Ctrl+D outside the note editor and Vault panel keeps the browser bookmark",
  !press({ ctrlKey: true, target: outside }) && calls === 0);
calls = 0; check("a key event with no element target is ignored", !press({ ctrlKey: true, target: null }) && calls === 0);
calls = 0; check("Windows/Linux: Win+D is not taken", !press({ metaKey: true }) && calls === 0);
nav.platform = "MacIntel";
calls = 0; check("Cmd+D (Mac) opens the daily note", press({ metaKey: true }) && calls === 1);
calls = 0; check("CANARY: Mac: Ctrl+D is left alone (Cmd is the shortcut there)", !press({ ctrlKey: true }) && calls === 0);
nav.platform = "Win32";
check("the tooltip names the shortcut", /Ctrl\+D/.test(VI["vault.daily"]) && /Cmd\+D/.test(EN["vault.daily"]));

// ============================================================
// 3. Dictionary
// ============================================================
for (const k of ["vault.daily", "cs.vt_daily_tasks", "cs.vt_daily_notes", "cs.vt_daily_fail"]) {
  check(`key ${k} exists in both vi and en`, k in VI && k in EN);
}

console.log("");
if (fails.length) { console.log("RED " + fails.length + " checks"); process.exit(1); }
console.log("All green.");
