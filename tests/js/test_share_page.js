/* Share links page: it must DRAW, and every action must reach the server with the right token.

       node tests/js/test_share_page.js

   History: 0.59.39 built the page (owner 18/09: "anh cần phải có thêm phần quản lý các link share để có thể chủ động
   thu hồi nếu quên"), then search and paging, then link names (0.65.30). Rebuilt 2026-11-06 (owner: change the address
   after /s/, a view counter per link, icon buttons like the Tasks page, keep paging, "tạo lại 1 trang quản lý link hữu
   dụng hơn"): summary row, filter chips, sort, view stats per row, one edit dialog for name + address, revoke asks first.

   This test RUNS renderSharePage for real: it cuts the function out of console.js by counting braces, gives it a fake
   DOM and a fake fetch, then reads the HTML it produced and the network calls it made. No regex over the source: a
   check of that kind once passed while the pet settings page rendered blank (see test_pet_trang_cai_dat.js). */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

function node() {
  const o = {
    _html: "", disabled: false, textContent: "", value: "", title: "", dataset: {}, onclick: null,
    classList: { add() {}, remove() {}, contains: () => false }, style: {},
    setAttribute() {}, addEventListener() {}, appendChild() {}, remove() { o.removed = true; }, select() {}, focus() {},
    querySelector: () => node(), querySelectorAll: () => [],
    get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  };
  return o;
}

function cut(src, decl) {
  const i = src.indexOf(decl);
  if (i < 0) return null;
  let d = 0, j = src.indexOf("{", i);
  const start = j;
  for (; j < src.length; j++) {
    if (src[j] === "{") d++;
    else if (src[j] === "}" && !--d) break;
  }
  return src.slice(start + 1, j);
}

const consoleSrc = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const body = cut(consoleSrc, "async function renderSharePage(el) {");
check("renderSharePage is found in console.js", !!body && body.length > 1200, body ? body.length + " chars" : "missing");

const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const t = (k, p) => {
  let s = typeof vi[k] === "string" ? vi[k] : "!!MISSING:" + k + "!!";
  for (const x in (p || {})) s = s.split("{" + x + "}").join(String(p[x]));
  return s;
};
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const ic = (n) => '<svg data-ic="' + n + '"></svg>';

// A fake element whose children are found IN the HTML it holds, the way a browser does on querySelectorAll. Children
// are remembered per (attribute, value) and forgotten on every innerHTML write, so the node a test clicks is the node
// the code wired up.
function stub(id) {
  const o = node();
  o.id = id || "";
  let kept = new Map();
  o._write = (v) => { o._html = String(v); kept = new Map(); };
  Object.defineProperty(o, "innerHTML", { configurable: true, get() { return o._html; }, set(v) { o._write(v); } });
  o.querySelectorAll = (sel) => {
    const m = /^\[data-([a-z-]+)(?:="([^"]*)")?\]$/.exec(sel);
    if (!m) return [];
    const camel = m[1].replace(/-([a-z])/g, (x, c) => c.toUpperCase());
    const re = new RegExp("data-" + m[1] + '="([^"]*)"', "g");
    const out = [];
    let g;
    while ((g = re.exec(o._html))) {
      if (m[2] !== undefined && g[1] !== m[2]) continue;
      const key = m[1] + "=" + g[1];
      if (!kept.has(key)) { const b = node(); b.dataset[camel] = g[1]; kept.set(key, b); }
      out.push(kept.get(key));
    }
    return out;
  };
  o.querySelector = (sel) => o.querySelectorAll(sel)[0] || null;
  o.insertAdjacentHTML = (where, h) => { o._write(o._html + String(h)); };   // pager() appends its bar
  return o;
}

function constant(name, dflt) {
  const m = new RegExp("const\\s+" + name + "\\s*=\\s*(\\d+)").exec(consoleSrc);
  return m ? Number(m[1]) : dflt;
}
const PER_PAGE = constant("SHARE_PER_PAGE", 20);
const SEARCH_MIN = constant("SHARE_SEARCH_MIN", 1);

// The REAL pager of console.js: the Share page pages through the same machinery as the Skills page.
const pagerBody = cut(consoleSrc, "function pager(box, items, perPage, renderPage, emptyHtml, opts) {");
const realPager = new Function("box", "items", "perPage", "renderPage", "emptyHtml", "opts", "window", pagerBody);

async function run(items, opts) {
  opts = opts || {};
  const calls = [];
  const el = stub("");
  const list = stub("shareList");
  const search = stub("shareSearch");
  const sort = stub("shareSort");
  const dialogs = [];
  const parse = el.querySelectorAll;
  el.querySelector = (sel) => {
    if (sel === "#shareList") return el._html.indexOf('id="shareList"') >= 0 ? list : null;
    if (sel === "#shareSearch") return el._html.indexOf('id="shareSearch"') >= 0 ? search : null;
    if (sel === "#shareSort") return el._html.indexOf('id="shareSort"') >= 0 ? sort : null;
    if (sel === "#shareCount") return el._html.indexOf('id="shareCount"') >= 0 ? (el._count = el._count || node()) : null;
    return null;
  };
  el.querySelectorAll = parse;
  // el.innerHTML as the browser sees it: the empty list box filled with its real content.
  Object.defineProperty(el, "innerHTML", {
    configurable: true,
    get() {
      return String(this._html).replace('<div class="share-list" id="shareList"></div>',
        '<div class="share-list" id="shareList">' + list._html + "</div>");
    },
    set(v) { el._write(v); },
  });
  const fakeFetch = async (url, o) => {
    calls.push({ url, body: o && o.body });
    if (url === "/share/list") {
      if (opts.netError) throw new Error("offline");
      return { json: async () => ({ ok: true, items }) };
    }
    if (url === "/share/rename") {
      const b = JSON.parse(o.body);
      if (opts.renameError) return { json: async () => ({ ok: false, error: opts.renameError, field: "slug" }) };
      const slug = String(b.slug || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      return { json: async () => ({ ok: true, ten: b.nhan || "Auto title", slug, url: "/s/" + (slug || b.token) }) };
    }
    return { json: async () => ({ ok: true }) };
  };
  const store = opts.store || {};
  const win = {
    confirm: opts.confirm || (() => true),
    isSecureContext: false,
    JavisPager: (box, arr, per, draw, empty, o) => realPager(box, arr, per, draw, empty, o, win),
    t: t,
  };
  const doc = {
    createElement: () => { const d = stub("dlg"); dialogs.push(d); return d; },
    body: { appendChild() {} },
    addEventListener() {}, removeEventListener() {},
  };
  const ls = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
  await new Function("el", "_renderGen", "ic", "t", "esc", "fetch", "location", "navigator", "window", "document",
    "localStorage", "SHARE_PER_PAGE", "SHARE_SEARCH_MIN", "return (async () => {" + body + "})();")(
    el, 1, ic, t, esc, fakeFetch, { origin: "https://nas.example" }, { clipboard: null }, win, doc, ls,
    PER_PAGE, SEARCH_MIN);
  return { el, list, search, sort, calls, dialogs, store };
}

const st = (views, extra) => Object.assign({ views, visitors: views, last: views ? Date.now() / 1000 - 7200 : 0,
  week: views, days: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, views] }, extra || {});
// A click as the browser delivers it: on the button, bubbling to the list box that handles it.
function press(r, sel) {
  const b = r.list.querySelectorAll(sel)[0];
  if (!b) return Promise.resolve("no button " + sel);
  return Promise.resolve(typeof r.list.onclick === "function" ? r.list.onclick({ target: { closest: () => b } }) : "unwired");
}
const rowsOf = (h) => (h.match(/class="share-row"/g) || []).length;
const tokensOf = (h) => (h.match(/data-token="([^"]*)"/g) || []).map((x) => x.slice(12, -1));

(async () => {
  const SAMPLE = [
    { token: "tok1", brain: "brain", path: "apps/app.html", ten: "App", slug: "my-app", tao_luc: 1789000000,
      url: "/s/my-app", token_url: "/s/tok1", stats: st(128, { visitors: 34, week: 12 }) },
    { token: "tok2", brain: "brain", path: "ghi-chu.md", ten: "Ghi chú", tao_luc: 1789000100, url: "/s/tok2",
      token_url: "/s/tok2", stats: st(0) },
  ];

  // ---- 1. draws everything ----
  {
    let err = null, r = null;
    try { r = await run(SAMPLE.map((x) => Object.assign({}, x))); } catch (e) { err = e; }
    check("draws without throwing", err === null, err && err.constructor.name + ": " + err.message);
    const html = r.el.innerHTML;
    check("calls /share/list", r.calls.some((g) => g.url === "/share/list"));
    check("one row per live link", rowsOf(html) === SAMPLE.length, rowsOf(html));
    check("full URL from the origin, with the custom address when set",
      html.includes("https://nas.example/s/my-app") && html.includes("https://nas.example/s/tok2"));
    check("shows the full path, to tell two files of the same name apart", html.includes("apps/app.html"));
    check("summary: link count, total views, last 7 days",
      html.includes('<b class="share-total">2</b>') && html.includes("<b>128</b> " + vi["share.views"])
      && html.includes("<b>12</b> " + vi["share.in_7_days"]));
    check("the public-link warning and the counting rules sit in the (i) block",
      html.includes(vi["share.warn"]) && html.includes(vi["share.stats_info"]));
    check("a viewed link shows views, people, 7 days and last view",
      html.includes("<b>128</b>") && html.includes(t("share.visitors", { n: 34 })) && html.includes(t("share.week", { n: 12 }))
      && html.includes(t("share.last_seen", { t: t("share.ago_hour", { n: 2 }) })));
    check("a viewed link has its 14-day chart", (html.match(/class="share-spark"/g) || []).length === 1);
    check("a never-viewed link says so", html.includes(vi["share.never"]));
    for (const [attr, icon] of [["data-share-copy", "copy"], ["data-share-edit", "pencil"], ["data-share-revoke", "trash-2"]]) {
      check("every row has an icon button " + attr + " (" + icon + ")",
        (html.match(new RegExp(attr + '="[^"]*"[^>]*><svg data-ic="' + icon + '"', "g")) || []).length === SAMPLE.length);
    }
    check("every row has an Open icon link in a new tab",
      (html.match(/class="share-ib" href="[^"]+" target="_blank"[^>]*><svg data-ic="external-link"/g) || []).length === SAMPLE.length);
    check("icon buttons carry a readable label and tooltip", html.includes('title="' + vi["share.a_revoke"] + '"')
      && html.includes('aria-label="' + esc(vi["share.a_edit"] + ": App") + '"'));
    check("no text buttons left in rows (owner: icons like the Tasks page)", !/class="gcard-btn/.test(r.list._html));
    check("no missing translation", !html.includes("!!MISSING:"), (html.match(/!!MISSING:[^!]+!!/g) || []).slice(0, 4).join(", "));
  }

  // ---- 2. empty and offline ----
  {
    const r = await run([]);
    check("no links: explains how to create one", r.el.innerHTML.includes(vi["share.empty"]));
    const o = await run([], { netError: true });
    check("offline: says so instead of spinning forever",
      o.el.innerHTML.includes(vi["app.err_net"]) && !o.el.innerHTML.includes("ic-spin"));
  }

  // ---- 3. revoke asks first, then calls the server with the row's token ----
  {
    const asked = [];
    const no = await run(SAMPLE.map((x) => Object.assign({}, x)), { confirm: (q) => { asked.push(q); return false; } });
    await press(no, '[data-share-revoke="tok1"]');
    check("revoke asks before killing the link, naming it", asked.length === 1 && asked[0] === t("share.revoke_ask", { ten: "App" }), asked[0]);
    check("answering No changes nothing", !no.calls.some((g) => g.url === "/share/revoke") && rowsOf(no.el.innerHTML) === 2);

    const r = await run(SAMPLE.map((x) => Object.assign({}, x)));
    check("the list handles clicks on its buttons", typeof r.list.onclick === "function");
    await press(r, '[data-share-revoke="tok1"]');
    const rv = r.calls.find((g) => g.url === "/share/revoke");
    check("Yes calls /share/revoke with that row's token", !!rv && JSON.parse(rv.body).token === "tok1", rv && rv.body);
    check("the revoked link leaves the list at once, totals drop",
      !tokensOf(r.el.innerHTML).includes("tok1") && r.el.innerHTML.includes('<b class="share-total">1</b>'));
  }

  // ---- 4. edit dialog: name and address in one go ----
  {
    const r = await run(SAMPLE.map((x) => Object.assign({}, x)));
    await press(r, '[data-share-edit="tok2"]');
    const d = r.dialogs[r.dialogs.length - 1];
    check("Edit opens a dialog", !!d && d._html.includes('role="dialog"'));
    check("the dialog shows the current name, the /s/ prefix and the token link",
      d._html.includes('value="Ghi chú"') && d._html.includes('class="share-slug-pre">/s/<')
      && d._html.includes("https://nas.example/s/tok2") && d._html.includes(vi["share.slug_note"]));
    d.querySelector("[data-dlg-name]").value = "Kế hoạch";
    d.querySelector("[data-dlg-slug]").value = "Ke Hoach Q4";
    await d.querySelector('[data-dlg="save"]').onclick();
    const g = r.calls.find((x) => x.url === "/share/rename");
    check("Save sends token, name and address together", !!g && JSON.parse(g.body).token === "tok2"
      && JSON.parse(g.body).nhan === "Kế hoạch" && JSON.parse(g.body).slug === "Ke Hoach Q4", g && g.body);
    check("the dialog closes after saving", d.removed === true);
    check("the row shows the new name and the new address without reloading",
      r.list._html.includes(">Kế hoạch<") && r.list._html.includes("https://nas.example/s/ke-hoach-q4"));

    const bad = await run(SAMPLE.map((x) => Object.assign({}, x)), { renameError: "Another link already uses this address" });
    await press(bad, '[data-share-edit="tok1"]');
    const d2 = bad.dialogs[bad.dialogs.length - 1];
    await d2.querySelector('[data-dlg="save"]').onclick();
    check("a refused address shows the server's reason and keeps the dialog open",
      d2.querySelector("[data-dlg-err]").textContent === "Another link already uses this address" && !d2.removed);
    check("and the row keeps its old address", bad.list._html.includes("https://nas.example/s/my-app"));
    d2.querySelector('[data-dlg="close"]').onclick();
    check("Cancel closes the dialog", d2.removed === true);
  }

  // ---- 5. search, filters, sort ----
  function many(n, fn) {
    const out = [];
    for (let i = 0; i < n; i++) {
      out.push(Object.assign({ token: "t" + i, brain: "brain", path: "thu-muc/note-" + i + ".md", tao_luc: 1789000000 + i,
        url: "/s/t" + i, stats: st(0) }, fn ? fn(i) : {}));
    }
    return out;
  }
  {
    const one = await run(many(SEARCH_MIN));
    check("a short list has no search box", one.el.innerHTML.indexOf('id="shareSearch"') < 0, "threshold " + SEARCH_MIN);
    check("the search box shows from the second link", SEARCH_MIN === 1);

    const r = await run(many(5, (i) => (i === 0 ? { path: "ke-hoach/Báo cáo quý.md", slug: "bao-cao-sep" } : {})));
    check("a longer list has the search box", typeof r.search.oninput === "function");
    r.search.value = "bao cao"; r.search.oninput();
    check("typing without marks finds a name with marks", rowsOf(r.list._html) === 1 && r.list._html.includes("Báo cáo quý.md"));
    r.search.value = "bao-cao-sep"; r.search.oninput();
    check("search also matches the custom address", rowsOf(r.list._html) === 1);
    r.search.value = "ke-hoach note"; r.search.oninput();
    check("several words must ALL match, and an empty result says so",
      rowsOf(r.list._html) === 0 && r.list._html.includes(vi["share.no_match"]));
    const shell = r.el._html;
    r.search.value = "note-1"; r.search.oninput();
    check("typing does not redraw the card (the box keeps focus)", r.el._html === shell);
    r.search.value = ""; r.search.oninput();
    check("clearing the search brings the list back", rowsOf(r.list._html) === 5);

    const mix = many(4, (i) => ({ loai: i === 3 ? "hoi_thoai" : "file", path: i === 3 ? "" : "f" + i + ".md",
      stats: st([5, 0, 40, 0][i], { last: [100, 0, 50, 0][i] }) }));
    const f = await run(mix.map((x) => Object.assign({}, x)));
    const chip = (v) => f.el.querySelectorAll('[data-share-filter="' + v + '"]')[0];
    check("four filter chips are drawn", ["all", "file", "chat", "unseen"].every((v) => !!chip(v)));
    chip("chat").onclick();
    check("Conversations shows only conversation links", tokensOf(f.list._html).join() === "t3", tokensOf(f.list._html).join());
    f.el.querySelectorAll('[data-share-filter="unseen"]')[0].onclick();
    check("Never viewed shows only links with zero views", tokensOf(f.list._html).sort().join() === "t1,t3");
    check("a filter shows the match count", f.el._count && f.el._count.textContent === t("share.count", { so: 2, tong: 4 }));
    check("the chosen filter is remembered for next time", JSON.parse(f.store["javis.share.view"]).filter === "unseen");
    f.el.querySelectorAll('[data-share-filter="all"]')[0].onclick();
    f.sort.value = "views"; f.sort.onchange();
    check("Most viewed puts the busiest link first", tokensOf(f.list._html)[0] === "t2" && tokensOf(f.list._html)[1] === "t0");
    f.sort.value = "recent"; f.sort.onchange();
    check("Recently viewed orders by last view", tokensOf(f.list._html).slice(0, 2).join() === "t0,t2");
    f.sort.value = "new"; f.sort.onchange();
    check("Newest orders by creation", tokensOf(f.list._html)[0] === "t3");
    const again = await run(mix.map((x) => Object.assign({}, x)), { store: { "javis.share.view": JSON.stringify({ filter: "chat", sort: "views" }) } });
    check("a remembered filter and sort are applied on open", tokensOf(again.list._html).join() === "t3"
      && again.el._html.includes('<option value="views" selected>'));
  }

  // ---- 6. paging ----
  {
    const total = PER_PAGE * 2 + 3;
    const r = await run(many(total));
    check("one page draws at most " + PER_PAGE + " links", rowsOf(r.list._html) === PER_PAGE, rowsOf(r.list._html));
    check("there is a pager", r.list._html.includes("jv-pager"));
    check("the summary counts every link, not one page", r.el.innerHTML.includes('<b class="share-total">' + total + "</b>"));
    r.list.querySelector('[data-pg="next"]').onclick();
    r.list.querySelector('[data-pg="next"]').onclick();
    check("the last page holds the rest", rowsOf(r.list._html) === total - PER_PAGE * 2, rowsOf(r.list._html));
    await press(r, "[data-share-edit]");
    const d = r.dialogs[r.dialogs.length - 1];
    check("buttons on page 3 work (they were dead past page 1 before 2026-11-06)", !!d && d._html.includes('role="dialog"'));
    await d.querySelector('[data-dlg="save"]').onclick();
    check("editing a link on page 3 stays on page 3", rowsOf(r.list._html) === total - PER_PAGE * 2
      && /data-pg="next"[^>]*disabled/.test(r.list._html));
    r.search.value = "note-1"; r.search.oninput();
    check("searching goes back to page 1 of the results", !/data-pg="prev"[^>]*>/.test(r.list._html) || /data-pg="prev"[^>]*disabled/.test(r.list._html));
  }

  // ---- 7. registered everywhere, labels in both languages ----
  {
    const ui = fs.readFileSync(path.join(ROOT, "dashboard", "ui-actions.js"), "utf8");
    const py = fs.readFileSync(path.join(ROOT, "server", "ui_targets.py"), "utf8");
    check("console.js has an icon for the page", /\n\s*share: "[^"]+",/.test(consoleSrc));
    check("the router knows the share page", /if \(id === "share"\) return renderSharePage\(el\);/.test(consoleSrc));
    check("ui-actions.js lists the share page", /"pet", "share"\]/.test(ui));
    check("ui_targets.py lists the share page and its spoken name", /"pet", "share",/.test(py) && /"chia se": "share"/.test(py));
    const used = new Set((body.match(/t\("(share\.[a-z0-9_.]+)"/g) || []).map((x) => x.slice(3, -1)));
    for (const k of ["page.share.label", "page.share.title", "page.share.sub", "share.heading"]) used.add(k);
    const missing = [...used].filter((k) => typeof vi[k] !== "string" || typeof en[k] !== "string");
    check("every label the page uses exists in BOTH languages (" + used.size + " keys)", missing.length === 0, missing.join(", "));
  }

  console.log(fails.length ? "\nFAIL: " + fails.join(", ") : "\nAll OK");
  process.exit(fails.length ? 1 : 0);
})();
