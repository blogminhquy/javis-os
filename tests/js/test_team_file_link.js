/* A file link in a team chat opens the file where the owner can see it.

       node tests/js/test_team_file_link.js

   Owner, 2026-11-15: files the team writes ("ghi ở marketing/bai-dang/...md") could not be clicked open on the Teams
   page. The click did reach console.js: the docked editor (#noteEditor) opened, but in its own place on the main screen,
   behind the Teams page, because the page had no [data-ne-host] frame for it. No error, no toast, nothing on screen.
   The Partners page (0.59.2) and the Coding page (0.63.4) once broke the same way.

   Guarded here:
   1. The Teams page has its own frame in the chat column, and console.js docks the editor there on that page.
   2. Leaving or redrawing the page gives the editor back before the frame is thrown away.
   3. Opening another team closes a docked file.
   4. A page with no frame at all gets the popup editor instead of a docked open out of sight. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const CON = D("console.js");
const TM = D("teams.js");
const CSS = D("console.css");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };
const between = (src, from, len) => { const i = src.indexOf(from); return i < 0 ? "" : src.slice(i, i + len); };

// ---- 1. the frame and the docking ----
const shell = between(TM, "function shell()", 2600);
check("teams.js shell found", shell.length > 0);
check("CANARY: the team chat column has a frame the editor docks into",
  /<div class="tm-edit" data-ne-host><\/div><\/section>/.test(shell));
check("the frame sits inside .tm-chat (after the composer), so it takes the chat column's place",
  shell.indexOf('class="tm-composer"') < shell.indexOf('class="tm-edit"') &&
  shell.indexOf('<section class="tm-chat">') < shell.indexOf('class="tm-edit"'));

const openNote = between(CON, "async function openNote(rel, it, opts)", 4000);
check("openNote found", openNote.length > 0);
check("CANARY: openNote docks the editor on the Teams page too",
  /classList\.contains\("on-chat"\) \|\| document\.body\.classList\.contains\("on-teams"\)\) _borrowNoteEditor\(\)/.test(openNote));
check("the Teams page still marks the body on-teams", /document\.body\.classList\.add\("on-teams"\)/.test(CON));

check("CSS: an open file shows its frame in the chat column", /\.tm-chat\.edit-on > \.tm-edit \{ display: flex; \}/.test(CSS));
check("CSS: and hides the rest of the column", /\.tm-chat\.edit-on > :not\(\.tm-edit\) \{ display: none; \}/.test(CSS));
check("CSS: the frame is hidden while no file is open", /\.tm-edit \{ display: none;/.test(CSS));
check("CSS: the docked editor drops its floating position, except maximized",
  /\.tm-edit > \.note-editor:not\(\.ne-full\) \{ position: static;/.test(CSS));

// ---- 2. leaving or redrawing gives the editor back ----
const teamsBranch = between(CON, 'if (id === "teams") {', 1600);
check("renderPage Teams branch found", teamsBranch.length > 0);
const leaveAt = teamsBranch.indexOf("_pageLeave = () => {");
check("CANARY: leaving the Teams page gives the editor back to the main screen",
  leaveAt > 0 && teamsBranch.indexOf("_returnNoteEditor();", leaveAt) > leaveAt);
check("drawing the Teams page again gives it back before rendering",
  teamsBranch.indexOf("_returnNoteEditor();") >= 0 && teamsBranch.indexOf("_returnNoteEditor();") < leaveAt);

// ---- 3. another team closes the docked file ----
check("console.js exposes closeNote", /window\.JavisCloseNote = closeNote;/.test(CON));
const openTeam = between(TM, "function openTeam(id, taskId)", 400);
check("CANARY: opening a team closes a file docked in the chat column", /closeDockedFile\(\);/.test(openTeam));
const closeDocked = between(TM, "function closeDockedFile()", 400);
check("only a file docked in THIS page is closed (a file open elsewhere stays)", /S\.el\.contains\(ed\)/.test(closeDocked));
check("closing goes through JavisCloseNote (writes unsaved text)", /window\.JavisCloseNote\(\)/.test(closeDocked));

// ---- 4. no frame: the popup, never an open out of sight ----
const canDock = between(CON, "function _neCanDock()", 700);
check("_neCanDock found", canDock.length > 0);
check("the main screen docks in place", /if \(active === "home"\) return true;/.test(canDock));
check("the Files page docks into its list (#fmEdit)", /on-files"\)\) return !!document\.getElementById\("fmEdit"\)/.test(canDock));
check("a page that hosts the editor needs its [data-ne-host] frame",
  /\(cls\.contains\("on-chat"\) \|\| cls\.contains\("on-teams"\)\) && !!document\.querySelector\("\[data-ne-host\]"\)/.test(canDock));
const openVault = between(CON, "function openVaultPath(fullPath)", 1800);
check("CANARY: openVaultPath docks only where the editor can be seen",
  /!isNarrow\(\) && _neCanDock\(\) && typeof window\.JavisOpenNote === "function"/.test(openVault));
check("otherwise the popup editor opens the file",
  openVault.indexOf("_neCanDock()") < openVault.indexOf("window.JavisEditFile(clean)"));

// ---- openVaultPath run for real: no frame -> popup, frame -> docked ----
const vm = require("vm");
const ovpSrc = CON.slice(CON.indexOf("  function openVaultPath(fullPath) {"),
  CON.indexOf("\n  }\n", CON.indexOf("  function openVaultPath(fullPath) {")) + 4);
const lineRe = (/\n  const LINE_SUFFIX_RE = [^\n]+/.exec(CON) || [""])[0];
const exts = ["VT_IMG_EXTS", "VT_TEXT_EXTS"].map((n) => (new RegExp("\\n  const " + n + " = \\[[^\\]]*\\];").exec(CON) || [""])[0]);
function openOn(dockable) {
  const opened = [];
  const ctx = {
    window: { JavisOpenNote: (p) => opened.push("docked:" + p), JavisEditFile: (p) => opened.push("popup:" + p) },
    _goFileUri: (p) => p, isNarrow: () => false, _vtRaw: (p) => p, _neCanDock: () => dockable,
    openFilesAt: (p) => opened.push("files:" + p),
  };
  vm.createContext(ctx);
  vm.runInContext(lineRe + exts.join("") + "\n" + ovpSrc + "\nthis.openVaultPath = openVaultPath;", ctx);
  ctx.openVaultPath("marketing/bai-dang/2026-11-15-fiona-calibration-14-bai-xuong-lap-rap.md");
  return opened.join(",");
}
check("CANARY run: the screenshot's file on a page with no frame opens in the popup",
  openOn(false) === "popup:marketing/bai-dang/2026-11-15-fiona-calibration-14-bai-xuong-lap-rap.md");
check("run: the same file on a page with a frame opens docked",
  openOn(true) === "docked:marketing/bai-dang/2026-11-15-fiona-calibration-14-bai-xuong-lap-rap.md");

// ---- behaviour of _neCanDock, run on a stub page ----
const fnSrc = canDock.slice(0, canDock.indexOf("\n  }\n") + 4);
function canDockOn(active, classes, nodes) {
  const document = {
    body: { classList: { contains: (c) => classes.includes(c) } },
    getElementById: (id) => (nodes.includes("#" + id) ? {} : null),
    querySelector: (sel) => (nodes.includes(sel) ? {} : null),
  };
  const window = { Alpine: { store: () => ({ active }) } };
  const Alpine = window.Alpine;
  // eslint-disable-next-line no-new-func
  return new Function("window", "document", "Alpine", fnSrc + "\nreturn _neCanDock();")(window, document, Alpine);
}
check("run: main screen -> dock", canDockOn("home", [], []) === true);
check("run: Teams page with its frame -> dock", canDockOn("teams", ["on-teams"], ["[data-ne-host]"]) === true);
check("run: Teams page without a frame -> popup", canDockOn("teams", ["on-teams"], []) === false);
check("run: Chat page -> dock", canDockOn("chat", ["on-chat"], ["[data-ne-host]"]) === true);
check("run: Files page -> dock", canDockOn("files", ["on-files"], ["#fmEdit"]) === true);
check("run: Tasks page (no frame) -> popup", canDockOn("tasks", [], []) === false);
check("run: Chatbot inbox (no frame) -> popup", canDockOn("conversations", [], ["[data-ne-host]"]) === false);

if (fails.length) { console.error("\n" + fails.length + " FAIL"); process.exit(1); }
console.log("\nAll good.");
