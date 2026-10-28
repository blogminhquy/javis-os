/* Bot inbox (Chatbot page, "Hòm thư bot"): the search box after the inbox is rebuilt (owner, 2026-10-25).
 *
 * BUG: after searching, leaving the inbox (Bot tab, another page) and coming back, the list stayed filtered
 * ("1 hội thoại") under an EMPTY search box, so "clearing" the box did nothing. Root cause: the query lives in `_q`,
 * which outlives the search box; renderInbox built a fresh, empty box and never put `_q` back. Opening the inbox from a
 * bot card kept the hidden search too. This test runs the real conversations.js against a tiny fake DOM and fails on
 * the code before the fix.
 *
 *       node tests/js/test_inbox_search_restore.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const MOD = src("dashboard/conversations-filters.js");
const CV = src("dashboard/conversations.js");
const CSS = src("dashboard/console.css");
const HTML = src("dashboard/index.html");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond, extra) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra !== undefined ? "  [" + extra + "]" : ""));
  if (!cond) fails.push(name);
};

// ---------------------------------------------------------------- a tiny fake DOM
// Every selector maps to one fake element. Setting innerHTML "recreates" the elements whose class appears in that HTML
// (they are dropped from the registry, so the next querySelector hands out a fresh, empty one), which is exactly what
// the browser does when the inbox is rebuilt.
function fakeDom() {
  const reg = new Map();
  function forget(html) {
    const tokens = new Set();
    String(html || "").replace(/class="([^"]*)"/g, (m, c) => { c.split(/\s+/).forEach((t) => t && tokens.add(t)); return m; });
    for (const key of [...reg.keys()]) {
      if (key.split(/\s+/).some((part) => tokens.has(part.replace(/^\./, "")))) reg.delete(key);
    }
  }
  function el(sel) {
    const cls = new Set();
    let html = "";
    return {
      sel, value: "", hidden: false, disabled: false, dataset: {}, textContent: "", scrollTop: 0, scrollHeight: 0, clientHeight: 0,
      style: { setProperty() {}, removeProperty() {} },
      classList: { add: (c) => cls.add(c), remove: (c) => cls.delete(c), contains: (c) => cls.has(c),
        toggle: (c, on) => { const v = on === undefined ? !cls.has(c) : !!on; if (v) cls.add(c); else cls.delete(c); return v; } },
      get innerHTML() { return html; },
      set innerHTML(h) { html = String(h); forget(h); },
      querySelector: (s) => get(s), querySelectorAll: () => [],
      setAttribute() {}, getAttribute() { return null; }, removeAttribute() {}, hasAttribute() { return false; },
      addEventListener() {}, appendChild() {}, focus() {}, contains() { return true; }, closest() { return null; },
      insertAdjacentHTML() {}, getBoundingClientRect() { return { width: 0, height: 0 }; },
    };
  }
  function get(s) { if (!reg.has(s)) reg.set(s, el(s)); return reg.get(s); }
  return { el, get };
}

// ---------------------------------------------------------------- load the real modules
const DOM = fakeDom();
const fetched = [];
const CONVS = [
  { id: 1, title: "Tôn Thất Thành", last_message: "a", chat_type: "private", tags: [] },
  { id: 2, title: "Lê Hoàng Hưng", last_message: "b", chat_type: "private", tags: [], contact: "0912345678" },
  { id: 3, title: "Hai Nguyen", last_message: "c", chat_type: "private", tags: [{ id: 5, name: "<b>VIP</b>", color: "red" }] },
];
function fakeFetch(url) {
  fetched.push(url);
  let data = { ok: true };
  if (url.indexOf("/conversations?") === 0) {
    const q = decodeURIComponent((url.match(/[?&]q=([^&]*)/) || [])[1] || "").toLowerCase();
    const items = CONVS.filter((c) => !q || c.title.toLowerCase().indexOf(q) >= 0);
    data = { ok: true, items, stats: {}, facets: { tong: 3, has_contact: 1, status: {}, type: {}, bots: {} }, bots: [],
             tags: [{ id: 5, name: "VIP", color: "red", count: 1 }] };
  } else if (url.indexOf("/channels/accounts") === 0) {
    data = { ok: true, accounts: [], channels: [] };
  }
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
}
const store = {};
const win = {
  t: (k, v) => k + (v ? "#" + Object.keys(v).map((x) => v[x]).join(",") : ""),
  localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } },
};
const doc = {
  hidden: false, activeElement: null, body: { contains: () => true, classList: { add() {}, remove() {} } },
  querySelector: () => null, getElementById: () => null, addEventListener() {}, createElement: () => DOM.el("div"),
};
const ctx = { window: win, document: doc, fetch: fakeFetch, console, setInterval: () => 1, clearInterval() {}, setTimeout, clearTimeout,
  encodeURIComponent, decodeURIComponent, FormData: function () { this.append = () => {}; }, confirm: () => true, alert() {},
  JSON, Object, Array, String, Number, Math, Date, Promise, parseInt };
win.document = doc;
vm.createContext(ctx);
vm.runInContext(MOD, ctx);
vm.runInContext(src("dashboard/inbox-v5.js"), ctx);
vm.runInContext(CV, ctx);
const F = win.JavisConvFilters;
const C = win.JavisConversations;
const flush = async () => { for (let i = 0; i < 12; i++) await new Promise((r) => setTimeout(r, 0)); };
const lastListUrl = () => fetched.filter((u) => u.indexOf("/conversations?") === 0).slice(-1)[0] || "";
const rows = () => (DOM.get(".ht-list").innerHTML.match(/class="ht-item /g) || []).length;
const qOf = (u) => decodeURIComponent((u.match(/[?&]q=([^&]*)/) || [])[1] || "");

(async () => {
  // ---- 1. the search bug, run for real ----
  const host = DOM.el("host");
  C.render(host);
  await flush();
  let box = DOM.get(".ht-search");
  box.value = "Tôn";
  box.oninput();
  await flush();
  check("typing a search asks the server for it", qOf(lastListUrl()) === "Tôn", lastListUrl());
  check("the list shows the one match", rows() === 1, rows());

  C.render(host);          // leave the inbox (tab or page switch) and come back: the inbox is rebuilt from scratch
  await flush();
  box = DOM.get(".ht-search");
  check("REGRESSION: after the inbox is rebuilt, the search box shows the query that still filters the list",
    box.value === qOf(lastListUrl()), "box=" + JSON.stringify(box.value) + " url q=" + JSON.stringify(qOf(lastListUrl())));

  box.value = "";
  box.oninput();
  await flush();
  check("clearing the box brings every conversation back", qOf(lastListUrl()) === "" && rows() === 3, rows());

  box.value = "Hai";
  box.oninput();
  await flush();
  C.mo({ bot_id: "b1" });  // opened from a bot card: show that bot's chats, not the leftover search
  await flush();
  box = DOM.get(".ht-search");
  check("REGRESSION: opening the inbox from a bot card drops a leftover search", qOf(lastListUrl()) === "" && box.value === "",
    "box=" + JSON.stringify(box.value) + " url=" + lastListUrl());

  if (fails.length) { console.log("\nFAILED " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
  console.log("\nOK - test_inbox_search_restore: all pass");
})().catch((e) => { console.log("FAIL crashed: " + (e && e.stack || e)); process.exit(1); });
