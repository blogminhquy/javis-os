/* Mascot menu: add features and reorder them in Settings > Mascot (pet-menu.js).

       node tests/js/test_pet_menu.js

   Owner, 2026-11-05: "Chỉ cần thêm và sắp xếp vị trí thôi là ok rồi. Và cho phần này vào trong phần cài đặt linh vật."
   This file LOADS the real pet-menu.js with a small fake DOM and drives the card: arrows, Discard, Add feature,
   Save (ok, network error, conflict) and a damaged saved menu. It also checks the wiring around it: pet.js builds
   its menu from it, the Settings page shows the card, leaving with unsaved changes asks first. No em dash here. */
"use strict";
const fs = require("fs");
const path = require("path");
const { napTruoc } = require("./_thu_tu_nap");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const vi = JSON.parse(read("dashboard/i18n/vi.json")), en = JSON.parse(read("dashboard/i18n/en.json"));
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails++;
}
const tick = () => new Promise((r) => setTimeout(r, 0));

// ---- pure helpers ----
const H = require(path.join(ROOT, "dashboard", "pet-menu.js"));
check("default menu is the six the pet always had", H.DEFAULT_ITEMS.join() === "chat,agent,workflow,mic,pet,teams");
check("addItem adds at the end", H.addItem(["a", "b"], "c").join() === "a,b,c");
check("addItem never adds the same feature twice", H.addItem(["a", "b"], "a").join() === "a,b");
check("moveItem only reorders, nothing is lost", H.moveItem(["a", "b", "c"], 0, 2).join() === "b,c,a" && H.moveItem(["a", "b"], 1, -5).join() === "b,a");
check("normalize: no saved menu = default", H.normalize(null).items.join() === H.DEFAULT_ITEMS.join() && H.normalize(null).state === "default");
check("normalize: a damaged menu shows the default meanwhile", H.normalize({ state: "invalid", rev: 3, items: ["x"] }).items.join() === H.DEFAULT_ITEMS.join());
check("normalize keeps a custom order and drops duplicates", H.normalize({ state: "custom", rev: 2, items: ["teams", "chat", "teams"] }).items.join() === "teams,chat");
check("search ignores Vietnamese diacritics", H.matches("tro chuyen", "Trò chuyện") && H.matches("đồ", "Đồ thị") && H.matches("do thi", "Đồ thị"));
check("search with an empty box shows everything", H.matches("", "anything"));
check("catalog ids are unique", new Set(H.CATALOG.map((c) => c.id)).size === H.CATALOG.length);
check("every default item is in the catalog", H.DEFAULT_ITEMS.every(H.known));
H.CATALOG.forEach((c) => {
  check("label of " + c.id + " exists in vi and en", typeof vi[c.label] === "string" && typeof en[c.label] === "string");
  if (c.sub) check("description of " + c.id + " exists in vi and en", typeof vi[c.sub] === "string" && typeof en[c.sub] === "string");
});

// ---- the real module in a small fake browser ----
function stub(tag) {
  const el = {
    tagName: tag || "div", _html: "", isConnected: true, disabled: false, listeners: {}, value: "", _sel: {},
    get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
    querySelector(sel) { return (this._sel[sel] = this._sel[sel] || stub()); },
    querySelectorAll() { return []; }, addEventListener(k, fn) { (this.listeners[k] = this.listeners[k] || []).push(fn); },
    remove() { this.isConnected = false; doc.body.kids = doc.body.kids.filter((x) => x !== this); },
    focus() {}, contains: () => true, appendChild(c) { this.kids.push(c); }, kids: [],
  };
  return el;
}
const ls = {};
const winListeners = {};
const fired = [];
let fetchPlan = [];
const posts = [];
const win = {
  t: (k, v) => { let s = vi[k]; if (typeof s !== "string") return k; if (v) Object.keys(v).forEach((x) => { s = s.replace("{" + x + "}", v[x]); }); return s; },
  ic: (n) => "<svg data-ic=\"" + n + "\"/>",
  localStorage: { getItem: (k) => (k in ls ? ls[k] : null), setItem: (k, v) => { ls[k] = String(v); } },
  navigator: { mediaDevices: { getUserMedia() {} } },
  addEventListener(k, fn) { (winListeners[k] = winListeners[k] || []).push(fn); },
  removeEventListener(k, fn) { winListeners[k] = (winListeners[k] || []).filter((f) => f !== fn); },
  dispatchEvent(ev) { fired.push(ev); (winListeners[ev.type] || []).slice().forEach((f) => f(ev)); return true; },
  JavisNav: { iconName: (id) => ({ tasks: "list-checks", files: "folder-tree" })[id] || "", has: (id) => id !== "account" },
  JavisLeaveGuard: { fn: null, set(f) { this.fn = f; }, clear(f) { if (!f || this.fn === f) this.fn = null; } },
};
const doc = {
  body: stub("body"), voice: true,
  getElementById(id) { if (id === "voiceBtn") return this.voice ? stub() : null; return this.body.kids.find((k) => k.id === id) || null; },
  createElement: (t) => stub(t),
};
global.CustomEvent = function (type, o) { this.type = type; this.detail = o && o.detail; };
global.FormData = function () { this.d = {}; this.append = (k, v) => { this.d[k] = v; }; };
global.fetch = (url, o) => {
  if (o && o.method === "POST") posts.push(o.body.d);
  const step = fetchPlan.shift();
  if (!step) return Promise.reject(new Error("offline"));
  if (step === "fail") return Promise.reject(new Error("offline"));
  return Promise.resolve({ ok: step.status === 200, json: () => Promise.resolve(step.body) });
};
const say = (status, body) => ({ status, body });

fetchPlan.push(say(200, { ok: true, menu: { state: "default", rev: 0, items: H.DEFAULT_ITEMS } }));   // load() at start
new Function("window", "document", "module", read("dashboard/pet-menu.js"))(win, doc, undefined);
const PM = win.JavisPetMenu;
check("the module exposes JavisPetMenu", !!(PM && PM.renderSettings && PM.menuEntries && PM.current));

(async () => {
  await tick();
  // ---- what the pet shows ----
  let rows = PM.menuEntries({ mic: false });
  check("pet menu: default six in order", rows.map((r) => r.id).join() === "chat,agent,workflow,mic,pet,teams");
  check("pet menu: the mic row says what a press will do", rows[3].label === vi["pet.menu.mic_on"] && PM.menuEntries({ mic: true })[3].label === vi["pet.menu.mic_off"]);
  check("settings list names the mic as a toggle, not by its current state", PM.entry("mic").label === vi["petmenu.mic_label"]);
  check("the assistants item is called Cộng sự, like its page", PM.entry("agent").label === "Cộng sự" && vi["page.workspace.label"] === "Cộng sự");
  win.navigator.mediaDevices = undefined;
  check("mic without browser permission is unavailable, with the reason", PM.entry("mic").why === vi["petmenu.why_mic"]);
  win.navigator.mediaDevices = { getUserMedia() {} };
  check("a page this Javis lacks is unavailable, with the reason", PM.entry("account").why === vi["petmenu.why_page"]);
  check("a page takes the icon of its rail item", PM.entry("tasks").icon.indexOf("list-checks") >= 0);
  check("an unknown id is shown as no longer available", PM.entry("old-thing").gone && PM.entry("old-thing").why === vi["petmenu.why_gone"]);

  // ---- the Settings card ----
  const host = stub();
  fetchPlan.push(say(200, { ok: true, menu: { state: "custom", rev: 4, items: ["teams", "chat", "agent", "workflow", "mic", "pet", "old-thing"] } }));
  PM.renderSettings(host);
  await tick(); await tick();
  let h = host.innerHTML;
  const order = () => [...host.innerHTML.matchAll(/data-i="(\d+)"/g)].length;
  check("card has the title and the one-line description", h.indexOf(vi["petmenu.title"]) >= 0 && h.indexOf(vi["petmenu.desc"]) >= 0);
  check("card shows every saved item, the unknown one included", order() === 7);
  check("the unknown one is marked unavailable, not dropped", h.indexOf(vi["petmenu.gone_name"]) >= 0 && h.indexOf(vi["petmenu.why_gone"]) >= 0);
  // Owner: "kéo lên kéo xuống được chứ ko phải mũi tên". Rows move by dragging; no arrow buttons.
  check("no up/down arrow buttons on the rows", !/data-move=/.test(h) && !/bp-arrow/.test(h));
  check("every row has a drag handle (a button, so the keyboard reaches it)", (h.match(/data-pm-grip/g) || []).length === 7);
  // Owner: "phần này thêm thì có nút x để xóa chứ không phải ẩn". Default items hide (eye); added ones remove (X).
  check("the six default rows have a show/hide eye", (h.match(/data-pm-eye/g) || []).length === 6);
  check("the added row has an X to remove it, a default row never does",
    (h.match(/data-pm-remove/g) || []).length === 1 && /data-i="6"[\s\S]*?data-pm-remove/.test(h)
    && !/data-i="0"[^]*?data-pm-remove[^]*?data-i="1"/.test(h));
  check("nothing to save yet: Save and Discard are disabled", /data-pm-save disabled/.test(h) && /data-pm-cancel disabled/.test(h));
  check("no rename, icon or restore-defaults control", !/data-pm-(rename|icon|delete|reset)/.test(h) && !/type="text"/.test(h));
  check("leaving now asks nothing", win.JavisLeaveGuard.fn && win.JavisLeaveGuard.fn() === "");

  const btn = (attrs, row) => ({
    disabled: false, dataset: attrs.move ? { move: attrs.move } : {},
    classList: { contains: (c) => c === "bp-arrow" && !!attrs.move },
    hasAttribute: (a) => !!attrs[a], getAttribute: (a) => attrs[a],
    closest: (sel) => (sel === ".bp-row" ? { dataset: { i: String(row) } } : null),
  });
  const click = (b) => host.onclick({ target: { closest: () => b } });
  const key = (k, row) => host.onkeydown({ key: k, preventDefault() {}, target: { closest: (sel) => (sel === "[data-pm-grip]"
    ? { disabled: false, closest: () => ({ dataset: { i: String(row) } }) } : null) } });
  key("ArrowDown", 0);
  h = host.innerHTML;
  check("keyboard: Down arrow on the handle moves the row one place", /data-i="0"[\s\S]*?Trò chuyện/.test(h.slice(0, h.indexOf('data-i="1"'))));
  check("a change enables Save and Discard", !/data-pm-save disabled/.test(h) && !/data-pm-cancel disabled/.test(h));
  check("leaving with unsaved changes asks first", win.JavisLeaveGuard.fn() === vi["petmenu.leave"]);
  click(btn({ "data-pm-cancel": true }));
  check("Discard returns to the saved order", /data-pm-save disabled/.test(host.innerHTML) && win.JavisLeaveGuard.fn() === "");
  key("ArrowUp", 0);
  check("keyboard: Up on the first row does nothing", /data-pm-save disabled/.test(host.innerHTML));

  // Show / hide (owner: "phải có cả nút ẩn hiện nữa, để có thể ẩn bớt đi")
  click(btn({ "data-pm-eye": true }, 1));
  h = host.innerHTML;
  check("the eye hides a row: it stays in place, greyed, saying it is hidden",
    order() === 7 && /data-i="1"[^>]*pm-hidden|pm-hidden[^>]*data-i="1"/.test(h) && h.indexOf(vi["petmenu.hidden_note"]) >= 0);
  check("the count says how many are hidden", h.indexOf("7 mục, 1 đang ẩn") >= 0);
  check("hiding is a change to save", !/data-pm-save disabled/.test(h) && win.JavisLeaveGuard.fn() === vi["petmenu.leave"]);
  click(btn({ "data-pm-eye": true }, 1));
  check("the eye again shows it, and nothing is left to save", !/pm-hidden/.test(host.innerHTML) && /data-pm-save disabled/.test(host.innerHTML));
  for (let i = 0; i < 6; i++) click(btn({ "data-pm-eye": true }, i));
  h = host.innerHTML;
  check("the last item still shown cannot be hidden (no empty menu)",
    (h.match(/pm-hidden/g) || []).length === 6 && /data-i="6"[\s\S]*?data-pm-remove[^>]*disabled/.test(h));
  click(btn({ "data-pm-remove": true }, 6));
  check("nor removed when it is the last one shown", order() === 7);
  click(btn({ "data-pm-cancel": true }));
  click(btn({ "data-pm-remove": true }, 0));
  check("the X does nothing on a default item", order() === 7);
  click(btn({ "data-pm-remove": true }, 6));
  h = host.innerHTML;
  check("the X removes an added item from the list", order() === 6 && h.indexOf(vi["petmenu.gone_name"]) < 0);
  check("removing is a change to save", !/data-pm-save disabled/.test(h) && win.JavisLeaveGuard.fn() === vi["petmenu.leave"]);
  click(btn({ "data-pm-cancel": true }));
  check("Discard brings the removed item back", order() === 7);

  // Add feature
  click(btn({ "data-pm-add": true }));
  const pick = doc.body.kids.find((k) => k.id === "petMenuPick");
  check("Add feature opens the picker", !!pick);
  const ph = pick.querySelector(".pm-pick-list").innerHTML;
  check("picker lists the catalog features", (ph.match(/data-pm-pick=/g) || []).length === H.CATALOG.length);
  check("a feature already on the menu says Added and cannot be picked",
    /data-pm-pick="teams" disabled[^>]*>[\s\S]*?Đã thêm/.test(ph));
  check("an unavailable feature shows why and cannot be picked", /data-pm-pick="account" disabled[\s\S]*?Bản Javis này không có trang này/.test(ph));
  check("the picker has a search box", pick.innerHTML.indexOf("data-pm-q") >= 0);
  const pickBtn = (id) => ({ disabled: false, getAttribute: () => id });
  pick.listeners.click[0]({ target: { closest: (s) => (s === "[data-pm-pick]" ? pickBtn("teams") : null) } });
  check("picking one already there adds nothing", order() === 7);
  pick.listeners.click[0]({ target: { closest: (s) => (s === "[data-pm-pick]" ? pickBtn("tasks") : null) } });
  check("picking a new feature adds it at the end and closes the picker",
    order() === 8 && /data-i="7"[\s\S]*Nhiệm vụ/.test(host.innerHTML) && !doc.body.kids.some((k) => k.id === "petMenuPick"));

  // Save: network error keeps the draft and the running menu
  const before = PM.current().join();
  fetchPlan.push("fail");
  click(btn({ "data-pm-save": true }));
  await tick(); await tick();
  check("a failed save says so and keeps the draft", host.innerHTML.indexOf(vi["petmenu.save_err"]) >= 0 && order() === 8);
  check("a failed save does not change the menu in use", PM.current().join() === before);
  check("hidden ids are sent too (none here)", posts[0] && posts[0].hidden === "[]");
  check("it was sent with the revision it was edited from", posts[0] && posts[0].base_rev === "4" && JSON.parse(posts[0].items).slice(-1)[0] === "tasks");

  // Save: conflict
  fetchPlan.push(say(409, { ok: false, code: "conflict", error: vi["petmenu.conflict"], menu: { state: "custom", rev: 5, items: ["chat"] } }));
  click(btn({ "data-pm-save": true }));
  await tick(); await tick();
  check("a conflict is reported with a Reload button, the draft kept", host.innerHTML.indexOf(vi["petmenu.conflict"]) >= 0 && /data-pm-reload/.test(host.innerHTML) && order() === 8);

  // Save: ok
  const saved = ["teams", "chat", "agent", "workflow", "mic", "pet", "old-thing", "tasks"];
  fetchPlan.push(say(200, { ok: true, menu: { state: "custom", rev: 5, items: saved } }));
  fired.length = 0;
  click(btn({ "data-pm-save": true }));
  await tick(); await tick();
  check("a good save says the menu is updated", host.innerHTML.indexOf(vi["petmenu.saved"]) >= 0);
  check("the pet menu uses the new order at once", PM.current().join() === saved.join());
  check("the pet is told (it closes an open menu and rebuilds on the next open)", fired.some((e) => e.type === "javis:pet-menu"));
  check("other windows hear of it through the cache", JSON.parse(ls["javis.pet.menu"]).rev === 5);
  check("the pet menu leaves the unknown id out", PM.menuEntries({}).every((r) => r.id !== "old-thing") && PM.menuEntries({}).length === 7);
  // A hidden item stays saved but the pet leaves it out.
  winListeners.storage.forEach((f) => f({ key: "javis.pet.menu", newValue: JSON.stringify({ state: "custom", rev: 5, items: saved, hidden: ["mic", "pet"] }) }));
  check("the pet menu leaves hidden items out, in the saved order", PM.menuEntries({}).map((r) => r.id).join() === "teams,chat,agent,workflow,tasks");
  check("hidden items stay in the saved list", PM.current().join() === saved.join());
  check("a stored menu with everything hidden falls back to showing all", H.normalize({ state: "custom", rev: 1, items: ["a", "b"], hidden: ["a", "b"] }).hidden.length === 0);

  // Another window saves while this card is clean: it follows.
  winListeners.storage.forEach((f) => f({ key: "javis.pet.menu", newValue: JSON.stringify({ state: "custom", rev: 6, items: saved.concat("files") }) }));
  check("a save in another window shows here when nothing is pending", order() === 9);

  // Damaged saved menu
  const host2 = stub();
  fetchPlan.push(say(200, { ok: true, menu: { state: "invalid", rev: 2, items: H.DEFAULT_ITEMS } }));
  PM.renderSettings(host2);
  await tick(); await tick();
  const h2 = host2.innerHTML;
  check("damaged: the card says so", h2.indexOf(vi["petmenu.invalid"]) >= 0);
  check("damaged: Add and Save are disabled, Reload offered", /data-pm-add disabled/.test(h2) && /data-pm-save disabled/.test(h2) && /data-pm-reload/.test(h2));
  check("damaged: the pet uses the default six meanwhile", PM.current().join() === H.DEFAULT_ITEMS.join());

  // ---- wiring ----
  const pet = read("dashboard/pet.js"), con = read("dashboard/console.js"), html = read("dashboard/index.html");
  const pmSrc = read("dashboard/pet-menu.js");
  check("phone: press and hold on a row picks it up, a quick swipe stays a scroll",
    /var LONG_PRESS = 3\d\d/.test(pmSrc) && /"touchmove"[\s\S]{0,400}e\.preventDefault\(\)/.test(pmSrc) && /\{ passive: false \}/.test(pmSrc)
    && /clearTimeout\(lp\.timer\); lp = null;/.test(pmSrc));
  check("a long press does not open the phone's copy menu", /"contextmenu"/.test(pmSrc) && /-webkit-touch-callout: none/.test(read("dashboard/style.css")));
  check("pet.js builds its menu from the saved list", /PM\.menuEntries\(\{ mic: mic \}\)/.test(pet));
  check("pet.js does not run a disabled row", /if \(!b \|\| b\.disabled\) return;/.test(pet));
  check("pet.js closes an open menu when the menu is saved", /"javis:pet-menu"[\s\S]{0,120}moMenu\(false\)/.test(pet));
  check("Settings > Mascot shows the Mascot menu card", /JavisPetMenu\.renderSettings\(el\.querySelector\("#petMenuBody"\)\)/.test(con));
  check("leaving a page with unsaved changes asks first", /if \(window\.JavisLeaveGuard && !window\.JavisLeaveGuard\.ok\(\)\) return;/.test(con) && /window\.JavisLeaveGuard = \{/.test(con) && /"beforeunload"/.test(con));
  check("JavisNav tells the icon and whether a page exists", /iconName\(id\) \{ return VIEW_ICON\[id\]/.test(con) && /has\(id\) \{/.test(con));
  check("pet-menu.js loads before pet.js", napTruoc("pet-menu.js", ["pet.js"], html));
  ["petmenu.title", "petmenu.desc", "petmenu.count", "petmenu.add", "petmenu.cancel", "petmenu.save", "petmenu.saving",
    "petmenu.saved", "petmenu.save_err", "petmenu.conflict", "petmenu.reload", "petmenu.invalid", "petmenu.load_err",
    "petmenu.search", "petmenu.added", "petmenu.none", "petmenu.close", "petmenu.mic_label", "petmenu.why_mic",
    "petmenu.why_page", "petmenu.why_gone", "petmenu.gone_name", "petmenu.leave", "petmenu.count_hidden", "petmenu.hide",
    "petmenu.show", "petmenu.hidden_note", "petmenu.keep_one", "petmenu.drag_label", "petmenu.remove"]
    .forEach((k) => check("key " + k + " in vi and en", !!vi[k] && !!en[k]));
  check("no em or en dash in pet-menu.js", !/[\u2013\u2014]/.test(read("dashboard/pet-menu.js")));
  check("no em or en dash in the new strings", !Object.keys(vi).filter((k) => k.startsWith("petmenu.")).some((k) => /[\u2013\u2014]/.test(vi[k] + en[k])));

  console.log(fails ? "\nĐỎ: " + fails : "\nXANH");
  process.exit(fails ? 1 : 0);
})();
