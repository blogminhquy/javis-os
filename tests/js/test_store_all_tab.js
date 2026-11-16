// Javis Store: an All tab that lists every pack, whatever its kind (owner, 2026-11-16).
//
//     node tests/js/test_store_all_tab.js
//
// Owner: "the Store must have an All tab, to see every app, skill and workflow, easy to search". Before, each tab
// held one kind and the search box only looked inside the open tab, so finding a pack meant guessing its kind first.
// Draws the real grid (`veKho`) and types into the real search box, does not scan the source.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..", "..");
let fails = 0;
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails++;
}

// A host that keeps the handlers `veLuoi` binds, so the test can type and click like a person.
const search = { value: "", oninput: null, oncompositionend: null };
const bound = {};
const host = {
  innerHTML: "",
  querySelector: () => null,
  querySelectorAll: (sel) => {
    const key = sel.replace(/[\[\]]/g, "");
    if (!host.innerHTML.includes(key)) return [];
    const el = { dataset: {}, onclick: null };
    bound[key] = el;
    return [el];
  },
};
const doc = {
  activeElement: null, querySelector: () => null, querySelectorAll: () => [],
  getElementById: (id) => (id === "pkQ" ? search : null),
  createElement: () => ({ style: {}, classList: { add() {}, remove() {} }, querySelectorAll: () => [], appendChild() {} }),
  body: { appendChild() {} },
};
const pack = (o) => Object.assign({
  id: "javis.x", kind: "skill", name: { vi: "X" }, description: { vi: "mo ta" }, tier: "data", verified: true,
  nguon: "kho", author: { name: "Javis" }, version: "1.0.0", installed: false,
  download: { url: "https://x/y.zip", sha256: "a" }, nhom: "Ban hang", upstream: {},
}, o);
const AGENT = pack({ id: "javis.agent-a", kind: "agent", name: { vi: "Tro ly ban hang" } });
const SKILL = pack({ id: "javis.skill-a", name: { vi: "Viet bai" }, upstream: { repo: "a/b", synced: "2026-11-01" } });
const FLOW = pack({ id: "javis.flow-a", kind: "workflow", name: { vi: "Chot don" } });
const TOOL = pack({ id: "javis.tool-a", kind: "tool", name: { vi: "May tinh" } });
const CONN = pack({ id: "javis.conn-a", kind: "connector", name: { vi: "Zalo" }, nhom: "" });
const CRM = pack({ id: "javis.crm", kind: "bundle", name: { vi: "CRM" } });
const ALL = [AGENT, SKILL, FLOW, TOOL, CONN, CRM];

let catalog = { ok: true, fetched_at: Math.floor(Date.now() / 1000), packs: ALL };
// The labels come from the dictionary, so a missing key shows up here as the raw key.
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const win = {
  ic: (t) => "<svg data-ic=\"" + t + "\"></svg>", Alpine: { store: () => ({ go() {} }) },
  t: (k, p) => String(vi[k] || k).replace(/\{(\w+)\}/g, (m, n) => (p && p[n] !== undefined ? p[n] : m)),
};
const alpineBefore = globalThis.Alpine;
globalThis.Alpine = win.Alpine;
new Function("window", "document", "fetch", fs.readFileSync(path.join(ROOT, "dashboard", "packs.js"), "utf8"))(
  win, doc, () => Promise.resolve({ json: () => Promise.resolve(catalog) }));
const P = win.JavisPacks || {};
const type = (text) => { search.value = text; search.oninput({ isComposing: false }); };

(async () => {
  check("both dictionaries name the tab", vi["store.kind.all"] === "Tất cả" && en["store.kind.all"] === "All");

  // ---- 1. Opening the Store with no kind asked for lands on All ----
  await P.veKho({}, host, false, "");
  const h = host.innerHTML;
  check("the Store opens on the All tab", /class="kho-tab on" data-kho-loai="all"/.test(h));
  check("All is the first tab, before Recommended",
    h.indexOf('data-kho-loai="all"') !== -1 && h.indexOf('data-kho-loai="all"') < h.indexOf('data-kho-loai="repo"'));
  check("the All tab counts every pack",
    new RegExp('data-kho-loai="all">[^<]*<span class="kho-dem">' + ALL.length + "</span>").test(h));
  check("the All tab lists a pack of every kind", ALL.every(g => h.includes(g.id)));
  check("the phone dropdown lists All first", /<select[^>]*id="pkLoai"[^>]*><option value="all" selected/.test(h));
  // Beside it sits the group dropdown, whose first option also reads "All": the kind one spells out "All kinds".
  check("the phone dropdown names it All kinds", h.includes('<option value="all" selected>Mọi loại (' + ALL.length + ")"));
  check("the search box says it covers All", h.includes("Tìm trong Tất cả"));

  // ---- 2. A card on the All tab says what kind it is ----
  const card = (html, id) => {
    const at = html.indexOf(id + " ·");
    return html.slice(html.lastIndexOf('<div class="cat-card', at), at);
  };
  check("an All card carries its kind", card(h, "javis.agent-a").includes(">Trợ lý<"));
  check("an All card keeps its group", card(h, "javis.agent-a").includes(">Ban hang<"));
  check("a pack with no group shows its kind once",
    card(h, "javis.conn-a").split(">Kết nối<").length === 2);

  await P.veKho({}, host, false, "agent");
  check("a kind tab does not repeat the kind on its cards", !card(host.innerHTML, "javis.agent-a").includes(">Trợ lý<"));

  // ---- 3. Search on All finds a pack of any kind ----
  await P.veKho({}, host, false, "all");
  type("chot don");
  check("searching All finds a workflow", host.innerHTML.includes("javis.flow-a") && !host.innerHTML.includes("javis.agent-a"));
  type("zalo");
  check("searching All finds a connector", host.innerHTML.includes("javis.conn-a") && !host.innerHTML.includes("javis.flow-a"));

  // ---- 4. A search that finds nothing in a kind tab offers the same search on All ----
  await P.veKho({}, host, false, "agent");
  type("zalo");
  const hm = host.innerHTML;
  check("a miss in a kind tab shows no card", !hm.includes("javis.conn-a"));
  check("a miss in a kind tab offers to search All, with the count", hm.includes("data-kho-search-all") && hm.includes("(1)"));
  bound["data-kho-search-all"].onclick();
  const hj = host.innerHTML;
  check("the offer jumps to the All tab", /class="kho-tab on" data-kho-loai="all"/.test(hj));
  check("the jump keeps the typed words", hj.includes('value="zalo"') && hj.includes("javis.conn-a"));

  await P.veKho({}, host, false, "agent");
  type("khong-co-goi-nao-ten-the-nay");
  check("a miss everywhere offers nothing", !host.innerHTML.includes("data-kho-search-all"));
  await P.veKho({}, host, false, "all");
  type("khong-co-goi-nao-ten-the-nay");
  check("a miss on All itself offers nothing", !host.innerHTML.includes("data-kho-search-all"));

  // ---- 5. The update strip still jumps to real kinds only ----
  catalog = { ok: true, fetched_at: Math.floor(Date.now() / 1000),
    packs: [AGENT, Object.assign({}, SKILL, { installed: true, installed_version: "1.0.0", version: "1.1.0" })] };
  await P.veKho({}, host, false, "all");
  const hu = host.innerHTML;
  check("the update strip has a chip for the kind, not for All",
    hu.includes('data-kho-moi="skill"') && !hu.includes('data-kho-moi="all"'));
  check("the All tab carries the new-version badge", /data-kho-loai="all">[\s\S]*?kho-dem moi/.test(hu.split('data-kho-loai="repo"')[0]));

  // ---- 6. An empty catalog still draws All, and lands there ----
  catalog = { ok: true, fetched_at: Math.floor(Date.now() / 1000), packs: [] };
  await P.veKho({}, host, false, "all");
  check("an empty Store still opens on All", /class="kho-tab on" data-kho-loai="all"/.test(host.innerHTML));

  globalThis.Alpine = alpineBefore;
  if (fails) { console.log("\nFAIL - test_store_all_tab: " + fails); process.exit(1); }
  console.log("\nOK - test_store_all_tab");
})();
