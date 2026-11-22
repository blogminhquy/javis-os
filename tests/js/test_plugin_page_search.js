/* Plugins page: Tasks-page layout, search, one flat list with source tags, drawer for details (2026-11-20).

       node tests/js/test_plugin_page_search.js

   Owner, 20/10/2026: "phần plugin có thể thêm thanh tìm kiếm được không, quá trình dùng lâu mình tạo thêm nhiều plugin
   thì tìm để bật tắt rất lâu" (search, 0.249.0).
   Owner, 20/11/2026, approving an HTML mock-up: "thiết kế lại trang plugin cho nó tối giản, dễ hiểu hơn ... các nút trong
   cũng không được đẹp kiểu như trang nhiệm vụ", then "bị thiếu nút cài file zip rồi" and "phần tất cả ấy không cần chia
   ra thành 3 phần mà thêm tag vào là được rồi, vì đã phân lại ở sidebar rồi mà".
*/
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const JS = D("console.js");
const CSS = D("console.css");
const VI = JSON.parse(D("i18n/vi.json"));
const EN = JSON.parse(D("i18n/en.json"));

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

const start = JS.indexOf("function _injectPluginCss() {");
const page = JS.slice(start, JS.indexOf("async function renderSelfImprove(el) {", start) > 0
  ? JS.indexOf("async function renderSelfImprove(el) {", start) : JS.indexOf("// Trang Webhook (0.204.0)", start));
check("found the plugin CSS and renderPlugins", start > 0 && page.includes("async function renderPlugins(el) {"));

// ---- 1. Search ----
check("the page has a search box", /id="plSearch"/.test(page) && /type="search"/.test(page));
check("search is accent-insensitive (shared _vtNoAccent)", /_vtNoAccent\(\[p\.name, p\.slug, p\.description/.test(page));
check("search also matches tool and hook names", /\(p\.tools \|\| \[\]\)\.join\(" "\)/.test(page) && /\(p\.hooks \|\| \[\]\)\.join\(" "\)/.test(page));
check("every typed word must match (AND, not OR)", /words\.every\(w => h\.includes\(w\)\)/.test(page));
check("Escape clears the search", /e\.key === "Escape" && inp\.value/.test(page) && /setQuery\(""\)/.test(page));
check("no match shows a message with a clear button", /cs\.pl_no_match/.test(page) && /data-clear/.test(page));
check("search box is 16px (no iOS zoom on focus)", /\.pl-search input\{[^}]*font-size:16px/.test(page));

// ---- 2. A toggle must not wipe the search ----
const load = (page.match(/async function load\(\) \{[\s\S]*?\n    \}/) || [""])[0];
check("load() builds the shell only on the first load", /if \(first \|\| !document\.getElementById\("plCards"\)\) buildShell\(\)/.test(load));
check("load() redraws the list, not the page", /drawList\(\);/.test(load) && !/el\.innerHTML\s*=/.test(load));
check("after a toggle the focus returns to the same plugin's switch", /ui\.refocus = p\.slug/.test(page) && /\.pl-sw`\);/.test(page));

// ---- 3. Tasks-page layout: a left column that filters, chips on a phone ----
check("left column lists status, source and machine views",
  ["all", "on", "off", "err", "mine", "pack", "bundled", "machine"].every(k => page.includes(`{ k: "${k}",`)));
check("Errors and Software-on-this-machine only show when they have something",
  /\(v\.k === "err" \|\| v\.k === "machine"\) && !count\(v\.k\)/.test(page));
check("the same views draw the phone chips", /chips\.innerHTML = views\.map/.test(page));
check("the left column shows on desktop, the chips on a phone",
  /@media \(max-width: 860px\)\{[\s\S]*?\.pl-side\{display:none\}[\s\S]*?\.pl-chips\{display:flex/.test(page));
check("the page hides the shared header, its title sits in the left column",
  /cv\.classList\.toggle\("cview-pl", id === "plugins"\)/.test(JS) && /\.cview\.cview-pl \.cview-head \{ display: none; \}/.test(CSS)
  && /pl-title">\$\{esc\(tt\("page\.plugins\.label"\)\)\}/.test(page));
check("the view survives leaving and coming back", /let _plView = "all";/.test(JS));
check("the Connections page lands on Software on this machine", /_plView = "machine";[^\n]*\n\s*try \{ Alpine\.store\("nav"\)\.go\("plugins"\)/.test(JS));

// ---- 4. One flat list with source tags (no groups) ----
check("rows are sorted by name in one list", /localeCompare\(b\.name \|\| "", LOC\(\)\)/.test(page) && /host\.innerHTML = `<div class="pl-list">\$\{shown\.map\(rowHtml\)/.test(page));
check("no per-source group headings any more", !/GROUPS/.test(page) && !/pl-group/.test(page));
check("mixed views tag your tools and store tools, built-in gets no tag",
  /const MIXED = new Set\(\["all", "on", "off", "err"\]\)/.test(page)
  && /srcOf\(p\) === "mine"\) return `<span class="pl-tag mine">/.test(page)
  && /srcOf\(p\) === "pack"\) return `<span class="pl-tag pack">/.test(page));
check("a brain-only plugin always says so", /p\.source === "vault"\) return `<span class="pl-tag mine">\$\{esc\(tt\("cs\.pl_src_vault"\)\)\}/.test(page));
check("a row shows the permission in plain words", /cs\.pl_perm_readonly/.test(page) && /cs\.pl_perm_safe/.test(page) && /cs\.pl_perm_full/.test(page));

// ---- 5. Switch, store plugins, drawer ----
check("on/off is a switch with role=switch and a label", /class="pl-sw" role="switch" aria-checked=/.test(page) && /cs\.pl_sw_aria/.test(page));
check("the switch has a 44px tap area", /\.pl-sw\{[^}]*height:44px/.test(page));
check("store plugins are managed in the store: 'By pack' instead of a switch",
  /p\.source === "pack"\s*\? `<button type="button" class="pl-bypack" data-open=/.test(page));
check("tapping a row opens the drawer with commands, slug and version",
  /class="pl-rmain" data-open=/.test(page) && /cs\.pl_d_cmds/.test(page) && /cs\.pl_d_slug/.test(page) && /cs\.pl_d_version/.test(page));
check("remove sits alone at the end of the drawer and asks first in the page",
  /const danger = /.test(page) && /\+ danger \+ `<\/aside>`/.test(page) && /confirmSheet\(tt\("cs\.pl_rm_q"/.test(page));
check("no browser confirm() on this page (it is silent in some app views)", !/confirm\(/.test(page.replace(/confirmSheet\(/g, "")));
check("remove can be undone from the toast", /toast\(tt\("cs\.pl_t_removed", \{ ten: p\.name \}\), \(\) => setRemoved\(p, false\)\)/.test(page));
check("removed plugins fold at the bottom with Reinstall", /data-fold aria-expanded/.test(page) && /data-restore=/.test(page));
check("layers and the toast are cleaned up when the page is left",
  /_pageLeave = \(\) => \{[\s\S]*?closeLayer\(true\);[\s\S]*?removeEventListener\("keydown", onKey\)/.test(page));

// ---- 6. Ways to add a tool ----
check("one Add button opens a sheet with store, chat and .zip", /data-add>/.test(page)
  && /cs\.pl_add_store_t/.test(page) && /cs\.pl_add_chat_t/.test(page) && /class="pl-opt" data-zip>/.test(page));
check("the .zip button also stands on its own in the header", /<button type="button" class="pl-btn" data-zip>\$\{ic\("file-up"\)\}/.test(page));
check("the .zip picker opens inside the click (no await before it)", /if \(d\.zip !== undefined\) \{ closeLayer\(true\); pickZip\(\); return; \}/.test(page));
check("a phone gets a round + in the corner", /class="pl-fab" data-add/.test(page) && /\.pl-fab\{display:grid/.test(page));
check("Ask in chat never overwrites a draft", /if \(!inp\.value\.trim\(\)\) \{ inp\.value = tt\("cs\.pl_chat_prompt"\)/.test(page));
check("the folder help stays reachable in the Add sheet's (i)", /infoPair\(`\$\{esc\(tt\("cs\.pl_dir_a"\)\)\}/.test(page) && /plzip\.btn_info/.test(page) && /cs\.pl_dir_a/.test(page));

// ---- 7. Strings in both dictionaries ----
const keys = ["cs.pl_search_ph", "cs.pl_clear", "cs.pl_filter_aria", "cs.pl_f_all", "cs.pl_f_on", "cs.pl_f_off",
  "cs.pl_f_err", "cs.pl_grp_mine", "cs.pl_grp_pack", "cs.pl_grp_bundled", "cs.pl_no_match", "cs.pl_no_match_f",
  "cs.pl_sw_aria", "cs.pl_add", "cs.pl_v_bundled", "cs.pl_v_machine", "cs.pl_v_machine_short", "cs.pl_sec_source",
  "cs.pl_sec_machine", "cs.pl_tag_mine", "cs.pl_tag_pack", "cs.pl_by_pack", "cs.pl_perm_readonly", "cs.pl_perm_safe",
  "cs.pl_perm_full", "cs.pl_perm_readonly_long", "cs.pl_perm_safe_long", "cs.pl_perm_full_long", "cs.pl_d_remove",
  "cs.pl_rm_q", "cs.pl_rm_body", "cs.pl_undo", "cs.pl_add_store_t", "cs.pl_add_chat_t", "cs.pl_add_zip_d",
  "cs.pl_chat_prompt", "cs.ct_rm_q", "cs.ct_rm_body"];
const missing = keys.filter(k => !VI[k] || !EN[k]);
check("every new string exists in vi.json and en.json" + (missing.length ? " (missing: " + missing.join(", ") + ")" : ""), !missing.length);
check("counted strings have the English plural forms", EN["cs.pl_n_cmds.one"] && EN["cs.pl_n_cmds.other"] && VI["cs.pl_n_cmds.other"]);
check("no em or en dash in the new strings", keys.every(k => !/[–—]/.test((VI[k] || "") + (EN[k] || ""))));
check("index.html bumps console.js", /console\.js\?v=(21[6-9]|2[2-9]\d|[3-9]\d\d)/.test(D("index.html")));

if (fails.length) { console.log("\nFAIL " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_plugin_page_search: all pass");
