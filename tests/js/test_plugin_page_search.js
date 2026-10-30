/* Plugins page: search box, status filter, own plugins first, compact switch cards (0.249.0).

       node tests/js/test_plugin_page_search.js

   Owner, 20/10/2026: "phần plugin có thể thêm thanh tìm kiếm được không, quá trình dùng lâu
   mình tạo thêm nhiều plugin thì tìm để bật tắt rất lâu". The page was one long column of tall
   cards, the 20 built-in plugins first and the user's own ones at the very bottom.
*/
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const JS = D("console.js");
const VI = JSON.parse(D("i18n/vi.json"));
const EN = JSON.parse(D("i18n/en.json"));

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

const start = JS.indexOf("function _injectPluginCss() {");
const page = JS.slice(start, JS.indexOf("async function renderSelfImprove(el) {", start));
check("found the plugin CSS and renderPlugins", start > 0 && page.includes("async function renderPlugins(el) {"));

// ---- 1. Search ----
check("the page has a search box", /id="plSearch"/.test(page) && /type="search"/.test(page));
check("search is accent-insensitive (shared _vtNoAccent)", /_vtNoAccent\(\[p\.name, p\.slug, p\.description/.test(page));
check("search also matches tool and hook names", /\(p\.tools \|\| \[\]\)\.join\(" "\)/.test(page) && /\(p\.hooks \|\| \[\]\)\.join\(" "\)/.test(page));
check("every typed word must match (AND, not OR)", /words\.every\(w => h\.includes\(w\)\)/.test(page));
check("Escape clears the search", /e\.key === "Escape"/.test(page) && /setQuery\(""\)/.test(page));
check("no match shows a message with a clear button", /cs\.pl_no_match/.test(page) && /cs\.pl_clear/.test(page));
check("search box is 16px (no iOS zoom on focus)", /\.pl-search input\{[^}]*font-size:16px/.test(page));

// ---- 2. A toggle must not wipe the search ----
// load() runs again after every toggle or remove. If it rebuilt the toolbar the typed text and
// the focus would vanish under the person's fingers.
const load = (page.match(/async function load\(\) \{[\s\S]*?\n    \}/) || [""])[0];
check("load() builds the shell only on the first load", /if \(first \|\| !document\.getElementById\("plCards"\)\) buildShell\(d\)/.test(load));
check("load() redraws the list, not the page", /drawList\(\);/.test(load) && !/el\.innerHTML\s*=/.test(load));
check("after a toggle the focus returns to the same plugin's switch", /ui\.refocus = p\.slug/.test(page) && /\.pl-sw`\);/.test(page));

// ---- 3. Filter and grouping ----
check("All / On / Off filter, Errors only when there are errors", /\["all", "cs\.pl_f_all"\], \["on", "cs\.pl_f_on"\], \["off", "cs\.pl_f_off"\]\]\.concat\(cnt\.err/.test(page));
check("groups in order: yours, store, built-in",
  /const GROUPS = \[\["mine", "cs\.pl_grp_mine"\], \["pack", "cs\.pl_grp_pack"\], \["bundled", "cs\.pl_grp_bundled"\]\]/.test(page));
check("user and vault plugins both land in 'yours'",
  /const groupOf = \(p\) => p\.source === "bundled" \? "bundled" : p\.source === "pack" \? "pack" : "mine"/.test(page));

// ---- 4. Compact card ----
check("on/off is a switch with role=switch and a label", /class="pl-sw" role="switch" aria-checked=/.test(page) && /cs\.pl_sw_aria/.test(page));
check("store plugins are managed in the store, not switched here: no switch on their card",
  /const right = p\.source === "pack" \|\| p\.removed \? ""/.test(page));
// 0.420.0, owner's iPhone screenshot: a "Manage in Javis Store" button on every store card took half the phone's width and
// squeezed the name and description into a sliver. One link on the store group's heading, the card text gets the width.
check("one 'manage in the store' link on the store group heading", /g === "pack" \? `<button type="button" class="pl-act pl-goto" data-goto-packs="1">/.test(page));
check("a card with no switch drops the right column", /\$\{right \? `<div class="pl-right">\$\{right\}<\/div>` : ""\}/.test(page));
check("reinstall sits with the other actions under the text", /p\.removed \? `<button type="button" class="pl-act undel">/.test(page));
check("long descriptions clamp to two lines with the rest in (i)", /pl-ds j-clamp2/.test(page) && /dongDai \? infoBody/.test(page));
check("a plugin with many tools shows the first few and +N", /TOOLS_SHOWN/.test(page) && /\+\$\{tools\.length - TOOLS_SHOWN\}/.test(page));
check("the optional tools block hides itself when empty", /id="ctTuyChon"[^>]*hidden/.test(page) && /oCt\.hidden = !ctCards\.children\.length/.test(page));
check("phone layout: search full width, 16px text", /@media \(max-width: 860px\)\{[\s\S]*?\.pl-search\{flex-basis:100%/.test(page) && /\.pl-ds,\.pl-nm\{font-size:16px\}/.test(page));

// ---- 5. Strings in both dictionaries ----
const keys = ["cs.pl_search_ph", "cs.pl_clear", "cs.pl_filter_aria", "cs.pl_f_all", "cs.pl_f_on", "cs.pl_f_off",
  "cs.pl_f_err", "cs.pl_grp_mine", "cs.pl_grp_pack", "cs.pl_grp_bundled", "cs.pl_no_match", "cs.pl_no_match_f",
  "cs.pl_sw_aria", "cs.pl_summary"];
const missing = keys.filter(k => !VI[k] || !EN[k]);
check("every new string exists in vi.json and en.json" + (missing.length ? " (missing: " + missing.join(", ") + ")" : ""), !missing.length);
check("no em or en dash in the new strings", keys.every(k => !/[–—]/.test((VI[k] || "") + (EN[k] || ""))));
check("index.html bumps console.js", /console\.js\?v=(18[2-9]|19\d|[2-9]\d\d)/.test(D("index.html")));

if (fails.length) { console.log("\nFAIL " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_plugin_page_search: all pass");
