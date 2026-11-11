/* Disk cleanup page (cleanup.js).

       node tests/js/test_cleanup_page.js

   Checks the size formatter, suggested selections, the selection count that warns before a whole group is chosen, that
   every tab draws from sample data, that every string key exists in Vietnamese and English, and that the page is wired
   like the other lazy pages. */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const CL = require(path.join(ROOT, "dashboard/cleanup.js"));
const vi = JSON.parse(read("dashboard/i18n/vi.json")), en = JSON.parse(read("dashboard/i18n/en.json"));

// ---------- helpers ----------
check("sizes read naturally", CL._fmtSize(512) === "512 B" && CL._fmtSize(1536) === "1.5 KB" && CL._fmtSize(3 * 1024 ** 3) === "3 GB");
const dups = [
  { keep: "E:\\a\\x.jpg", copies: ["E:\\b\\x.jpg", "E:\\c\\x.jpg"], size: 100, count: 3, wasted: 200 },
  { keep: "E:\\a\\y.pdf", copies: ["E:\\b\\y.pdf"], size: 50, count: 2, wasted: 50 },
];
check("suggested duplicates are every copy except the keeper",
  JSON.stringify(CL._suggestedDups(dups)) === JSON.stringify(["E:\\b\\x.jpg", "E:\\c\\x.jpg", "E:\\b\\y.pdf"]));
let info = CL._selectionInfo(dups, { "E:\\b\\x.jpg": true, "E:\\b\\y.pdf": true }, false);
check("selection counts files and bytes", info.count === 2 && info.bytes === 150 && info.unsafe === 0);
info = CL._selectionInfo(dups, { "E:\\a\\y.pdf": true, "E:\\b\\y.pdf": true }, false);
check("a group with every copy chosen is flagged", info.unsafe === 1);
const sim = [{ keep: "p/big.jpg", count: 2, bytes: 10, files: [{ path: "p/big.jpg", size: 90, w: 1200, h: 900 }, { path: "p/small.jpg", size: 10, w: 600, h: 450 }] }];
check("suggested look-alikes skip the keeper", JSON.stringify(CL._suggestedSimilar(sim[0])) === JSON.stringify(["p/small.jpg"]));
check("look-alike selection uses each photo's own size", CL._selectionInfo(sim, { "p/small.jpg": true }, true).bytes === 10);
check("progress text per phase", CL._progressText({ progress: { phase: "full", done: 3, total: 9 } }).indexOf("cl.prog.full") === 0
  && CL._progressText({}) === "cl.prog.start");

// ---------- render ----------
const base = { roots: ["E:\\"], images: true, minKb: 0, sel: { "E:\\b\\x.jpg": true }, msg: "",
  drives: [{ path: "E:\\", kind: "local", total: 2e12, free: 1e12 }, { path: "Z:\\", kind: "network", unc: "\\\\nas\\share" }],
  status: { running: true, roots: ["E:\\"], progress: { phase: "walk", files: 10, bytes: 1000 } },
  overview: { files: 10, bytes: 5000, dup_groups: 2, dup_wasted: 250, offline: 0,
    categories: [{ category: "image", files: 3, bytes: 300 }, { category: "weird", files: 1, bytes: 1 }],
    folders: [{ path: "E:\\a", files: 4, bytes: 400 }], biggest: [{ path: "E:\\a\\x.jpg", size: 100 }],
    roots: [{ root: "E:\\", scanned_at: 1700000000 }] },
  dups: { total: 3, wasted: 250, groups: dups }, sim: { pillow: true, total: 1, groups: sim },
  batches: [{ id: "b1", at: 1700000000, note: "", files: 2, bytes: 200, state: "quarantined", items: [{ src: "E:\\b\\x.jpg", size: 100 }] },
    { id: "b0", at: 1600000000, note: "", files: 0, bytes: 0, state: "restored", items: [] }] };
const page = (tab, extra) => CL._pageHtml(Object.assign({}, base, { tab }, extra || {}));
let h = page("overview");
check("overview draws tiles, a network drive with its UNC path and the scan progress",
  h.indexOf("cl.tile.wasted") > 0 && h.indexOf("\\\\nas\\share") > 0 && h.indexOf("cl.scanning") > 0 && h.indexOf('data-act="cancel"') > 0);
check("an unknown category falls back to Other", h.indexOf("cl.cat.other") > 0);
check("the page never repeats its own title", h.indexOf("page.cleanup") < 0);
h = page("dups");
check("duplicates list every copy with a checkbox and mark the keeper",
  (h.match(/data-role="sel"/g) || []).length === 5 && h.indexOf("cl.keep") > 0 && h.indexOf('data-act="quarantine"') > 0);
check("a chosen copy is drawn checked", /data-path="E:\\b\\x\.jpg" checked/.test(h));
check("more groups than shown offer Show more", h.indexOf('data-act="more"') > 0);
h = page("similar");
check("look-alikes draw thumbnails through the thumb route", h.indexOf("/filescan/thumb?path=p%2Fbig.jpg") > 0 && h.indexOf("1200x900") > 0);
check("without Pillow the look-alike tab says so", page("similar", { sim: { pillow: false, groups: [], total: 0 } }).indexOf("cl.no_pillow") > 0);
h = page("quarantine");
check("a live batch offers restore and delete for good, a restored one does not",
  (h.match(/data-act="restore"/g) || []).length === 1 && (h.match(/data-act="purge"/g) || []).length === 1);
check("idle with no roots disables Scan", page("overview", { roots: [], status: { running: false } }).indexOf('data-act="scan" disabled') > 0);
check("text is escaped", page("dups", { dups: { total: 1, wasted: 0, groups: [{ keep: "<b>x", copies: ["y"], size: 1, count: 2, wasted: 1 }] } }).indexOf("<b>x") < 0);

// ---------- strings ----------
const src = read("dashboard/cleanup.js");
const keys = Array.from(new Set((src.match(/"cl\.[a-z_.]+"/g) || []).map(s => s.slice(1, -1))));
const missing = keys.filter(k => !(k in vi) || !(k in en));
check("every cl.* key exists in vi and en (" + keys.length + ")", keys.length > 50 && missing.length === 0);
if (missing.length) console.log("   missing:", missing.join(", "));
check("page label and subtitle exist", vi["page.cleanup.label"] && en["page.cleanup.label"] && vi["page.cleanup.sub"] && en["page.cleanup.sub"]);
const all = keys.concat(["page.cleanup.label", "page.cleanup.sub"]);
check("no long dash in the page strings", all.every(k => !/\u2014/.test(vi[k] + en[k])) && !/\u2014/.test(src));

// ---------- wiring ----------
const html = read("dashboard/index.html"), con = read("dashboard/console.js"), ua = read("dashboard/ui-actions.js"), ut = read("server/ui_targets.py");
check("lazy group loads cleanup.css and cleanup.js", /"donodia": \[\s*"\/static\/cleanup\.css\?v=\d+",\s*"\/static\/cleanup\.js\?v=\d+"/.test(html));
check("console.js knows the page, its icon, its group and its mount", con.indexOf('cleanup: "brush-cleaning"') > 0
  && con.indexOf('cleanup: ["donodia"]') > 0 && con.indexOf("window.JavisCleanup.mount(el)") > 0 && /"terminal", "cleanup"\] \}/.test(con));
check("voice and UI actions know the page", ua.indexOf('"cleanup"') > 0 && ut.indexOf('"cleanup"') > 0 && ut.indexOf('"don o dia": "cleanup"') > 0);
check("the page icon exists in the icon bundle", read("dashboard/vendor/lucide-icons.js").indexOf('"brush-cleaning"') > 0);

console.log(fails.length ? `\n${fails.length} failed` : "\nall passed");
process.exit(fails.length ? 1 : 0);
