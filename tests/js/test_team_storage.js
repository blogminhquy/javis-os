// 19/11/2026: the Info tab of a team shows the newest few pictures, files and links with "See all"; "See all" opens the
// storage view (Kho lưu trữ) in the same panel: three tabs, a search box, rows grouped by day, a pager. Owner: "phần file
// với link trong nhóm cần phân trang ... zalo nó làm xem tất cả này xong ấn vào thì nó vào kho lưu trữ".
//
//     node tests/js/test_team_storage.js
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(root, "dashboard", f), "utf8");
const vi = JSON.parse(read("i18n/vi.json"));
const en = JSON.parse(read("i18n/en.json"));
const T = require(path.join(root, "dashboard", "teams.js"));
const src = read("teams.js");
const css = read("console.css");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  " + String(extra).slice(0, 400)));
  if (!cond) fails++;
}

const now = Date.now() / 1000;
const DAY = 86400;

// ---- Info: a short list, "See all" only when there is more ----
check("Info shows 6 pictures, 3 files, 3 links", T.PREVIEW.image === 6 && T.PREVIEW.file === 3 && T.PREVIEW.link === 3);
check("See all appears only when the list holds more than it shows",
  T.seeAllHtml("file", 3) === "" && T.seeAllHtml("file", 4).includes('data-as-open="file"') && T.seeAllHtml("image", 7).includes(vi["teams.storage_see_all"]));
check("Info draws the newest few and the true totals from the server",
  /imgs\.slice\(0, PREVIEW\.image\)/.test(src) && /docs\.slice\(0, PREVIEW\.file\)/.test(src) && /links\.slice\(0, PREVIEW\.link\)/.test(src)
  && src.includes("var c = I.counts || { images: imgs.length, files: docs.length, links: links.length };")
  && src.includes('tw("teams.info_files", { n: c.files })'));
check("the server's counts are kept with the lists", src.includes("counts: (d && d.counts) || null"));

// ---- a file row ----
const f1 = T.fileRowHtml({ name: "bao-cao.pdf", path: "a/bao-cao.pdf", brain_path: "a/bao-cao.pdf", size: 1887436, exists: true, ts: now,
  manual: true, id: "f1", description: "Báo cáo quý" }, true);
check("a file row: the extension tile in its kind's colour, the name, the size", f1.includes('data-ft="pdf"') && f1.includes(">PDF<")
  && f1.includes("bao-cao.pdf") && f1.includes("1,8 MB"), f1);
check("on Info the row also says the day", /\d{1,2}:\d{2}/.test(f1));
check("a document of the team keeps its pencil and its X", f1.includes('data-info-desc="file"') && f1.includes('data-info-del-file="f1"')
  && f1.includes("Báo cáo quý"));
const gone = T.fileRowHtml({ name: "x.md", path: "x.md", exists: false, ts: now - 3 * DAY }, false);
check("a file that is no longer there says so, like Zalo", gone.includes("tm-as-gone") && gone.includes(vi["teams.storage_gone"]), gone);
check("found in the messages (no id): no X", !gone.includes("data-info-del-file"));
const dir = T.fileRowHtml({ name: "Brief", path: "Brief/", brain_path: "Brief/", dir: true, exists: true, ts: now }, false);
check("a folder document opens the Files page (a button, not a raw link)", dir.includes('data-info-open-dir="Brief/"') && dir.includes('data-ft="dir"')
  && !dir.includes("/files/raw"), dir);
const long = T.fileRowHtml({ name: "hop-dong.docx", path: "hop-dong.docx", exists: true, ts: now }, false);
check("a four-letter extension gets the smaller tile font", long.includes('data-long="1"') && long.includes(">DOCX<"));
check("sizes: bytes, KB with one decimal, MB", T.sizeText(512) === "512 B" && T.sizeText(98000) === "95,7 KB" && T.sizeText(0) === "");

// ---- a link row ----
const l1 = T.linkRowHtml({ url: "https://www.github.com/duwqijlk/muse-protocol", ts: now }, false);
check("a link with no name shows the address without https:// and www.", l1.includes(">github.com/duwqijlk/muse-protocol<") && !l1.includes("tm-as-meta"), l1);
const l2 = T.linkRowHtml({ url: "https://docs.google.com/d/1", label: "Kế hoạch", ts: now, manual: true, id: "l9" }, true);
check("a named link: the name, then the site and the day", l2.includes(">Kế hoạch<") && l2.includes("docs.google.com") && l2.includes('data-info-del-link="l9"'));

// ---- the storage view ----
// Counted back from noon today, local time: from `now`, 0.1 and 1.2 days back crossed midnight whenever the run started
// before 04:48 (CI 20/11/2026 at 04:10 UTC grouped "1.2 days ago" under the day before yesterday).
const noon = new Date();
noon.setHours(12, 0, 0, 0);
const files = [0, 0.1, 1, 1.2, 9].map((d, i) => ({ name: "f" + i + ".md", path: "f" + i + ".md", exists: true, size: 2048,
  ts: noon.getTime() / 1000 - d * DAY }));
const A = { kind: "file", q: "", page: 0, items: files, total: 45, state: "done" };
const view = T.assetsHtml(A, { images: 17, files: 45, links: 27 });
check("a back button to Info and three tabs with their totals", view.includes('data-as-back="1"') && view.includes(vi["teams.storage_title"])
  && ["image", "file", "link"].every((k) => view.includes('data-as-kind="' + k + '"')) && view.includes(">45<") && view.includes(">17<"), view);
check("the tab open is the selected one", /data-as-kind="file" aria-selected="true"/.test(view) && /data-as-kind="image" aria-selected="false"/.test(view));
check("a search box and a pager (20 a page: 45 files are 3 pages)", view.includes('class="tm-as-q"') && view.includes('data-job-page="assets"')
  && view.includes(">1/3<"), view);
check("pictures open the viewer with every picture of the page", view.includes('class="tm-as-body" data-lb-scope="1"'));
const groups = T.byDay(files);
check("rows are grouped by day, newest first", groups.length === 3 && groups[0].label === vi["teams.storage_today"]
  && groups[1].label === vi["teams.storage_yesterday"] && /^Ngày \d{1,2} tháng \d{1,2}/.test(groups[2].label), JSON.stringify(groups.map((g) => g.label)));
const body = T.assetsBodyHtml(A);
check("each day has its heading over its rows", (body.match(/<h5>/g) || []).length === 3 && (body.match(/tm-as-row/g) || []).length === 5);
const imgs = T.assetsBodyHtml({ kind: "image", items: files.map((f) => Object.assign({ image: true }, f)), total: 5, state: "done" });
check("pictures are grouped by month (a day rarely fills a row) in a grid", imgs.includes("tm-as-imgs") && imgs.includes("jv-img-link")
  && (imgs.match(/<h5>/g) || []).length <= 2, imgs.slice(0, 300));
check("an old year is written out", /Tháng \d{1,2}, 20\d\d/.test(T.monthLabel(now - 400 * DAY)) && /, 20\d\d$/.test(T.dayLabel(now - 400 * DAY)));
check("empty kind: its own empty line; a search with nothing: says nothing matches",
  T.assetsBodyHtml({ kind: "image", q: "", items: [], total: 0 }).includes(vi["teams.info_no_images"])
  && T.assetsBodyHtml({ kind: "link", q: "abc", items: [], total: 0 }).includes(vi["teams.storage_no_match"]));
check("loading and a failed read are shown, not a blank panel",
  T.assetsBodyHtml({ kind: "file", items: null }).includes("pg-loading") && T.assetsBodyHtml({ kind: "file", state: "error", err: "Mất mạng" }).includes("Mất mạng"));
check("one page or fewer: no pager", !T.assetsHtml({ kind: "link", items: [], total: 20, state: "done" }, {}).includes("data-job-page"));

// ---- wiring ----
check("a page is read from the server by kind, search, offset and limit",
  src.includes('"/assets?brain=" + q(brain()) + "&kind=" + q(A.kind) + "&q=" + q(String(A.q || "").trim())') &&
  src.includes('"&offset=" + ((A.page || 0) * per) + "&limit=" + per') && T.ASSET_PER_PAGE.file === 20 && T.ASSET_PER_PAGE.link === 20);
check("an answer for an older request (typed on, page turned) is dropped", src.includes("if (S.assets !== A || A.seq !== seq || sessionId() !== sid) return;"));
check("typing redraws the rows and the pager only, the search box keeps focus and the phone keyboard",
  /function drawAssets\(\) \{[\s\S]*?box\.querySelector\("\.tm-as-body"\)\.innerHTML = assetsBodyHtml\(A\);\n\s*box\.querySelector\("\.tm-as-pg"\)\.innerHTML = assetsPagerHtml\(A\);/.test(src)
  && src.includes('if (e.target.classList.contains("tm-as-q")) { assetsSearch(e.target.value); return; }'));
check("See all, back, the tabs and the pager are handled", src.includes("if (d.asOpen) return openAssets(d.asOpen);") && src.includes("if (d.asBack) return closeAssets();")
  && src.includes("if (d.asKind) {") && src.includes('if (d.jobPage === "assets") return assetsPage(Number(d.dir));'));
check("the side panel draws the storage view in place of Info while it is open",
  src.includes('S.tab === "info" ? (S.assets ? assetsHtml(S.assets, (S.info && S.info.counts) || {}) : infoTabHtml(S.team))'));
check("another team, closing the panel or pressing the Info tab leaves the storage view",
  src.includes("S.infoFind = null; S.assets = null;") && /function closeSide\(\) \{\n\s*S\.side = false;\n\s*S\.assets = null;/.test(src)
  && src.includes('if (d.tab === "info") S.assets = null;'));
check("Escape empties the search first, then goes back to Info", /if \(e\.target\.value\) \{ e\.target\.value = ""; assetsSearch\(""\); \} else closeAssets\(\);/.test(src));
check("a new file in the team reads the open page again", src.includes("if (S.side && S.tab === \"info\") { if (S.assets) loadAssets(); else drawSide(true); }"));

// ---- words and look ----
const keys = ["teams.info_no_images", "teams.storage_see_all", "teams.storage_title", "teams.storage_back", "teams.storage_tab_images",
  "teams.storage_tab_files", "teams.storage_tab_links", "teams.storage_search_images", "teams.storage_search_files", "teams.storage_search_links",
  "teams.storage_no_match", "teams.storage_gone", "teams.storage_today", "teams.storage_yesterday", "teams.storage_day",
  "teams.storage_day_year", "teams.storage_month", "teams.storage_month_year", "teams.storage_undated"];
check("words vi/en", keys.every((k) => vi[k] && en[k]), keys.filter((k) => !vi[k] || !en[k]).join(","));
check("Zalo's name for it in Vietnamese", vi["teams.storage_title"] === "Kho lưu trữ" && vi["teams.storage_see_all"] === "Xem tất cả");
check("no em dash or en dash", !/[–—]/.test(keys.map((k) => vi[k] + en[k]).join("")));
check("CSS: the head stays on top, the tile takes its kind's colour, a See all button, 44px to press on a phone",
  /\.tm-as-head \{ position: sticky;/.test(css) && css.includes('.tm-as-type[data-ft="pdf"] { --ft: var(--red); }')
  && css.includes("color-mix(in srgb, var(--ft) 14%, transparent)") && css.includes(".tm-info-all {")
  && css.includes("@media (pointer: coarse) { .tm-info-all, .tm-as-back { min-height: 44px; } }"));
check("CSS: no colour written by hand in the new rules",
  !/#[0-9a-f]{3,8}\b|rgba?\(/i.test((css.match(/\/\* 19\/11\/2026 \(owner: "phân trang[\s\S]*?\.tm-as-empty \{[^}]*\}/) || [""])[0]));

if (fails) { console.log("\nFAIL " + fails); process.exit(1); }
console.log("\nOK test_team_storage");
