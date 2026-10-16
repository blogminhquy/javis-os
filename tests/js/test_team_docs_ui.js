// 0.191.0: files, working folder and the info panel of a team (dashboard/teams.js), and the ">" of the folder picker
// (dashboard/composer-folder.js).
//
//     node tests/js/test_team_docs_ui.js
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(root, "dashboard", f), "utf8");
const vi = JSON.parse(read("i18n/vi.json"));
const en = JSON.parse(read("i18n/en.json"));
const CF = require(path.join(root, "dashboard", "composer-folder.js"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 400)));
  if (!cond) fails++;
}

// ---- folder picker: ">" goes inside, the name pins ----
const rows = CF.folderRows([{ name: "05 - Projects", type: "dir", dirs: true }, { name: "Shop", type: "dir" },
  { name: ".git", type: "dir", dirs: true }, { name: "a.md", type: "file" }], "Brain");
check("rows carry whether a folder has folders inside; hidden ones and files left out",
  JSON.stringify(rows) === JSON.stringify([{ name: "05 - Projects", path: "Brain/05 - Projects", dirs: true },
    { name: "Shop", path: "Brain/Shop", dirs: false }]), JSON.stringify(rows));
const cf = read("composer-folder.js");
check("the list asks the server which folders have subfolders, and lists inside the one gone into",
  cf.includes('"/files/list?subdirs=1&brain="') && cf.includes('"&path=" + encodeURIComponent(here.path)'));
check("a folder with folders inside gets a separate '>' button; the name button pins",
  /\(r\.dirs \? '<button type="button" class="cp-in" data-in="'/.test(cf) && cf.includes('data-pin="\' + i + \'"'));
check("inside a folder: a back row and a row to pin the folder you are in",
  cf.includes('data-back="1"') && cf.includes('data-pin-here="1"') && /trail\.push\(\{ name: d\.name, path: d\.path \}\)/.test(cf));
check("the panel is reusable (team chat passes its own brain, folder and pin)", /panelFor: makePanel/.test(cf)
  && /var panel = makePanel\(\);/.test(cf));

// ---- team chat ----
const tm = read("teams.js");
check("'+' menu: attach a file, pin a working folder", tm.includes('data-plus-attach="1"') && tm.includes('data-plus-folder="1"'));
check("attachments upload to /upload and go out with the message; sending waits for uploads",
  tm.includes('fetch("/upload"') && tm.includes("body.attachments = atts.map(") && tm.includes('setNote(tw("teams.attach_wait"))'));
check("the team folder pins on the team's own conversation (same route as the main chat)",
  tm.includes('"/coding/session/" + q(sid) + "/pin"') && tm.includes("window.JavisPinnedFolder && window.JavisPinnedFolder.panelFor"));
check("the team picture opens the info panel", tm.includes('class="tm-ava-btn" data-team-info="1"')
  && /if \(d\.teamInfo\) return S\.side && S\.tab === "info" \? closeSide\(\) : openSide\("info", t\);/.test(tm));
check("the info panel: members, working folder, pictures, files with Add, links with Add, from the conversation assets",
  tm.includes("function infoTabHtml(t)") && tm.includes('"/sessions/" + q(sid) + "/assets?brain="') &&
  tm.includes("data-info-add-file") && tm.includes("data-info-add-link") && tm.includes("tm-info-imgs") && tm.includes('teamUrl("/files")'));
check("info is the first tab of the side panel", tm.includes('var tabs = ["info", "jobs", "team"]'));
check("files sent with a message show as chips, the stored names line is not repeated",
  tm.includes("((m.meta || {}).files || [])") && tm.includes("fileChipHtml"));
const keys = ["teams.tab_info", "teams.info_open", "teams.attach", "teams.attach_err", "teams.attach_wait", "teams.uploading",
  "teams.info_members", "teams.info_folder", "teams.info_files", "teams.info_links", "teams.info_add_file", "teams.info_no_files",
  "cp.pin_top", "cp.pin_here", "cp.pin_open", "cp.pin_no_sub"];
check("i18n vi/en", keys.every((k) => vi[k] && en[k]), keys.filter((k) => !vi[k] || !en[k]).join(","));
const css = read("console.css") + read("style.css");
check("CSS: chips, info panel, the '>' button 44px on touch", css.includes(".tm-attach-chips {") && css.includes(".tm-info-sec {")
  && /\(pointer: coarse\) \{ \.cp-in \{ width: 44px; height: 44px; \}/.test(css));
check("no em dash", !/[–—]/.test(cf + keys.map((k) => vi[k] + en[k]).join("")));

if (fails) { console.log("\nFAIL " + fails); process.exit(1); }
console.log("\nOK test_team_docs_ui");
