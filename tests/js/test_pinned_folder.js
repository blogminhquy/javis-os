/* Pinned working folder in the composer (0.158.0).

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
check("folder rows build a path from the listing path when items have none",
  F.folderRows([{ name: "a", type: "dir" }], "brain/x")[0].path === "brain/x/a");
check("row hint is the path inside the brain, not from the drive root",
  F.displayPath("Project/Brain/projects/shop", "Project/Brain") === "projects/shop" && F.displayPath("Other/x", "Project/Brain") === "Other/x"
  && F.displayPath("Project/Brain/projects", "") === "Project/Brain/projects");
check("the + menu marks panel items with a chevron like submenus", /sub: !!\(it\.submenu \|\| it\.panel\)/.test(plus));
check("chip label keeps short names", F.chipLabel("shop", 18) === "shop");
check("chip label cuts long names with an ellipsis", F.chipLabel("a-very-long-project-folder-name", 18) === "a-very-long-proje…");
check("chip label phone width is 10 characters", F.chipLabel("a-very-long-project", 10).length === 10);

const s = F.createPinState();
const a = s.request("s1"), b = s.request("s2");
check("only the newest request for the open session is accepted", s.accept(a, "s1") === false && s.accept(b, "s2") === true);
s.hold("brain/projects");
check("pending pin is taken once", s.takePending() === "brain/projects" && s.takePending() === null);

check("app.js claims the pending folder right after the pending model",
  /JavisModelBar\.claimPending\(savedSessionId\)[\s\S]{0,300}JavisPinnedFolder\.claimPending\(savedSessionId\)/.test(app));
check("composer-folder.js loads after composer-plus.js", html.indexOf("composer-plus.js") !== -1 && html.indexOf("composer-plus.js") < html.indexOf("composer-folder.js"));
check("folder upload input is gone", html.indexOf('id="folderInput"') === -1 && plus.indexOf("folderInput") === -1);
check("folder upload helpers are gone",
  ["handleFolder", "pickFolderFiles", "runQueue"].every(n => plus.indexOf(n) === -1) && app.indexOf("queue: (files") === -1 && app.indexOf("_hangDoi") === -1);
// Held pin, claim, failed claim and brain switch are exercised for real in test_pinned_folder_flow.js.
check("claiming without a session id keeps the held pin (found in the sandbox check)",
  /function claimPending\(newSid\) \{\s*if \(!newSid\) return null;/.test(src));
check("nothing held: claimPending returns null so the first message is not delayed", /if \(!p\) return null;/.test(src));
// Review 0.158.0: the first turn could start before the /pin POST landed and run in the brain.
check("app.js keeps the claim promise and sends the first turn only after it settles",
  /_pinWait = window\.JavisPinnedFolder\.claimPending\(savedSessionId\)/.test(app)
  && /const _w = _pinWait; _pinWait = null;\s*if \(_w\) _w\.then\(_send, _send\); else _send\(\);/.test(app));
check("if the socket drops while the first turn waits for the pin, the text goes back to the input with a notice",
  /const _send = \(\) => \{\s*if \(!ws \|\| ws\.readyState !== WebSocket\.OPEN\) \{[\s\S]{0,400}chatInput\.value = msg;[\s\S]{0,120}ghiChuThoang\(/.test(app));
check("a failed claim clears the chip and says why in the composer", /apply\(null\);\s*if \(window\.JavisAttach\) window\.JavisAttach\.note\(/.test(src));
check("pin uses the one-call endpoint", src.indexOf('"/pin"') !== -1);
check("pin fires javis:pinned-folder-changed", src.indexOf('"javis:pinned-folder-changed"') !== -1);
check("browse row opens the shared folder picker", src.indexOf("JavisFolderPicker.open(") !== -1);
check("composer-plus supports panel items and opening one item", /item\.panel/.test(plus) && /openItem:/.test(plus));
["cp.pin_folder", "cp.pin_search_ph", "cp.pin_browse", "cp.pin_unpin", "cp.pin_outside", "cp.pin_gone", "cp.pin_failed", "cp.pin_empty"]
  .forEach(k => check("i18n key " + k + " in vi and en", !!vi[k] && !!en[k]));
check("old folder upload strings removed",
  ["cp.folder", "cp.folder_skipped", "cp.folder_over", "cp.folder_empty", "cp.folder_flat"].every(k => !vi[k] && !en[k]));
check("no Vietnamese in composer-folder.js run code",
  !/[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]/i.test(src.replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "")));
check("no em dash in composer-folder.js", src.indexOf("—") === -1);

if (fails.length) { console.log("\nFAIL - test_pinned_folder: " + fails.length); process.exit(1); }
console.log("\nOK - test_pinned_folder: all pass");
