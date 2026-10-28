/* Bot inbox row menu (owner, 2026-10-25: a "..." on each conversation row, like Zalo's): mark unread/read, pin/unpin,
 * quick tags, who replies (bot or me), hide/unhide with a "Hidden" filter, copy the phone or email the customer left.
 * Desktop opens a small menu under the "...", phones a bottom sheet. This file pins the pure parts (filter state, menu
 * model and HTML) and the wiring that matters (the "..." never opens the chat, Escape and outside clicks close, the
 * 5-second refresh keeps the menu open).
 *
 *       node tests/js/test_inbox_row_menu.js
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
const ICONS = src("dashboard/vendor/lucide-icons.js");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond, extra) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra !== undefined ? "  [" + extra + "]" : ""));
  if (!cond) fails.push(name);
};

let stored = null;
const win = {
  t: (k, v) => k + (v ? "#" + Object.keys(v).map((x) => v[x]).join(",") : ""),
  localStorage: { getItem: () => stored, setItem(k, v) { stored = v; } },
};
const ctx = { window: win, console, encodeURIComponent, String, Object, Array, Number, JSON };
vm.createContext(ctx);
vm.runInContext(MOD, ctx);
const F = win.JavisConvFilters;
const icon = (n) => "[" + n + "]";

// ---- 1. the "Hidden" filter ----
check("status 'hidden' is a valid saved filter", F.sanitize({ status: "hidden" }).status === "hidden");
check("an unknown saved status still falls back to no filter", F.sanitize({ status: "archived" }).status === "");
stored = JSON.stringify({ status: "hidden", bot: "b1", junk: 1 });
const loaded = F.load();
check("a saved state with the hidden filter loads back, junk dropped", loaded.status === "hidden" && loaded.bot === "b1" && !("junk" in loaded));
stored = "{not json";
check("a broken saved state loads as no filter (the list opens on 'Needs you')",
  JSON.stringify(F.load()) === JSON.stringify(Object.assign(F.emptyState(), { who: "you" })));
check("the hidden filter asks the server for status=hidden", F.query({ status: "hidden" }) === "&status=hidden");
check("the hidden filter counts as an active filter", F.activeCount({ status: "hidden" }) === 1);
// Chatbot v5: the status choices live in the Filter menu (inbox-v5.js), one radio each.
vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "inbox-v5.js"), "utf8"), ctx);
const so = win.JavisInboxV5.filterMenuHtml({ status: "hidden" }, "status", [], { status: { unread: 2, need_reply: 1, hidden: 3 } }, [], null, null);
check("Filter menu status ends with 'Hidden (N)', ticked when on", /data-v="hidden" checked> <span>ht\.f_st_hidden#3/.test(so), so);
check("no count from an old server reads 0", win.JavisInboxV5.filterMenuHtml({}, "status", [], { status: {} }, []).indexOf("ht.f_st_hidden#0") > 0);

// ---- 2. what the menu offers ----
const acts = (c) => F.rowMenuItems(c).filter((x) => !x.sep).map((x) => x.act);
const base = { id: 1, unread_count: 0, pinned: 0, tags: [], mode: "ai", bot_id: "", contact: "", hidden: 0 };
check("plain chat: unread, pin, tags, hide (no mode without a bot, no copy without a contact)",
  JSON.stringify(acts(base)) === JSON.stringify(["unread", "pin", "tags", "hide"]), acts(base));
check("unread chat offers 'mark read'; pinned offers 'unpin'; hidden offers 'unhide'",
  JSON.stringify(acts({ ...base, unread_count: 2, pinned: 1, hidden: 1 })) === JSON.stringify(["read", "unpin", "tags", "unhide"]));
const withBot = F.rowMenuItems({ ...base, bot_id: "b", mode: "human" });
const ai = withBot.find((x) => x.act === "mode_ai"), me = withBot.find((x) => x.act === "mode_human");
const dr = withBot.find((x) => x.act === "mode_draft");
check("a bot chat shows the three reply modes of the 'Who replies' bar, the current one checked",
  ai && dr && me && ai.on === false && dr.on === false && me.on === true && ai.radio && dr.radio && me.radio && dr.key === "ib.m_draft");
check("a chat where the A.I. is not allowed offers no reply mode (it is switched on from the chat or Info)",
  !F.rowMenuItems({ ...base, bot_id: "b", ai_allowed: false }).some((x) => /^mode_/.test(x.act || "")));
check("'waiting' counts as the bot answering, like the header switch",
  F.rowMenuItems({ ...base, bot_id: "b", mode: "waiting" }).find((x) => x.act === "mode_ai").on === true);
check("the mode group has its heading", withBot.some((x) => x.sep && x.key === "ht.rm_mode"));
const phone = F.rowMenuItems({ ...base, contact: "0912345678" }).find((x) => x.act === "copy");
const mail = F.rowMenuItems({ ...base, contact: "a@b.vn" }).find((x) => x.act === "copy");
check("copy only with a contact, phone or email wording, the value as second line",
  phone && phone.key === "ht.rm_copy_phone" && phone.icon === "phone" && phone.sub === "0912345678" &&
  mail && mail.key === "ht.rm_copy_email" && mail.icon === "mail");
check("tags row opens a second view and lists the chat's tags",
  F.rowMenuItems({ ...base, tags: [{ id: 1, name: "VIP" }, { id: 2, name: "Sỉ" }] }).find((x) => x.act === "tags").sub === "VIP, Sỉ" &&
  F.rowMenuItems(base).find((x) => x.act === "tags").more === true);
check("hide says the chat comes back when the customer writes", F.rowMenuItems(base).find((x) => x.act === "hide").sub === "ht.rm_hide_sub");
check("no conversation: still a sane menu", acts(null).length === 4);

// ---- 3. menu HTML ----
const h = F.rowMenuHtml(F.rowMenuItems({ ...base, bot_id: "b", contact: "x<y>@z.vn", tags: [{ id: 1, name: "<b>VIP</b>" }] }), icon);
check("rows are menu items; modes are radio rows with aria-checked", /role="menuitem" data-act="unread"/.test(h) &&
  /role="menuitemradio" data-act="mode_ai" aria-checked="true"/.test(h) && /data-act="mode_human" aria-checked="false"/.test(h), h);
check("the checked mode shows a check mark", /data-act="mode_ai"[^]*?<span class="ht-rm-end">\[check\]<\/span>/.test(h));
check("tags row says it opens a submenu", /data-act="tags" aria-haspopup="menu"/.test(h) && h.indexOf("[chevron-right]") > 0);
check("names and contacts are escaped", h.indexOf("<b>VIP") < 0 && h.indexOf("x<y>") < 0 && h.indexOf("x&lt;y&gt;@z.vn") > 0);
check("dividers are separators", /class="ht-rm-sep" role="separator"/.test(h));
const done = F.rowMenuHtml(F.rowMenuItems({ ...base, contact: "0912345678" }), icon, "copy");
check("after copying, the copy row says 'Copied' with a check", /class="ht-rm-it done"[^>]*data-act="copy"/.test(done) &&
  done.indexOf("ht.rm_copied") > 0 && done.indexOf("[check]") > 0);
const tm = F.tagMenuHtml([{ id: 1, name: "VIP", color: "red" }, { id: 2, name: "Sỉ", color: "blue" }], [{ id: 2 }], icon);
check("tags view: back row, one checkbox per tag (checked = on the chat), new tag row",
  /data-act="back"/.test(tm) && /aria-checked="false" data-act="tag" data-tag="1"/.test(tm) &&
  /aria-checked="true" data-act="tag" data-tag="2"/.test(tm) && /data-act="tag_new"/.test(tm) && tm.indexOf('data-c="red"') > 0);
check("tags view with no tags says so and still offers 'new tag'",
  F.tagMenuHtml([], [], icon).indexOf("ht.rm_tags_none") > 0 && /data-act="tag_new"/.test(F.tagMenuHtml([], [], icon)));

// ---- 4. wiring in conversations.js ----
check("each row has a keyboard-reachable '...' (span role=button, tabindex, aria-haspopup)",
  /class="ht-rmore" role="button" tabindex="0" aria-haspopup="menu"/.test(CV));
check("clicking the '...' opens the menu and never the chat",
  /closest\("\.ht-rmore"\)\) \{ e\.stopPropagation\(\); toggleRowMenu\(x, false\); return; \}/.test(CV));
check("Enter, Space or ArrowDown on the '...' opens it with keyboard focus", /e\.key === "ArrowDown"\) \{ e\.preventDefault\(\); e\.stopPropagation\(\); toggleRowMenu\(x, true\)/.test(CV));
check("right click / long press and the context-menu key open the same menu",
  /x\.oncontextmenu = function \(e\) \{ e\.preventDefault\(\); openRowMenu\(x, false\); \}/.test(CV) && /e\.key === "ContextMenu"/.test(CV));
check("Escape closes and returns focus to the '...'; arrows move between rows",
  /e\.key === "Escape"\) \{ e\.preventDefault\(\); e\.stopPropagation\(\); return closeRowMenu\(true\); \}/.test(CV) && /e\.key === "ArrowUp"/.test(CV));
check("a click outside closes it", /document\.addEventListener\("mousedown"[^]*?closeRowMenu\(false\);\s*\}, true\)/.test(CV));
check("the menu lives on <body>, so the list redraw does not remove it", /document\.body\.appendChild\(m\)/.test(CV) &&
  /\(_rm && _rm\.id === c\.id \? " menu-on" : ""\)/.test(CV));
check("a redraw whose row is gone closes the menu, otherwise re-anchors it",
  /if \(_rm\) \{ if \(!rmAnchor\(\)\) closeRowMenu\(false\); else placeRowMenu\(\); \}/.test(CV));
check("phones get a bottom sheet over a scrim", /var PHONE_MQ = "\(max-width: 640px\)"/.test(CV) && /" ht-rsheet"/.test(CV) && /ht-rsheet-bg/.test(CV));
check("opening a chat or switching tab closes the menu", /async function mo\(id\) \{\n    closeRowMenu\(false\);/.test(CV) &&
  /if \(!body\) return;\n    closeRowMenu\(false\);/.test(CV));
check("actions call the routes", ['"/conversations/" + id + "/unread"', '"/conversations/" + id + "/read"', '"/conversations/" + id + "/pin"',
  '"/conversations/" + id + "/hide"', '"/conversations/" + id + "/mode"', '"/conversations/" + convId + "/tags"'].every((s) => CV.indexOf(s) >= 0));
check("a reply-mode change from the menu updates the open thread too", /if \(_conv && _conv\.id === id\) \{ _conv\.mode = mode; _dauVetTin = ""; taiTin\(false\); \}/.test(CV));
check("toggling a tag keeps the menu open and updates the row and an open thread's chips",
  /it\.tags = d\.tags \|\| \[\][^]*?_conv\.tags = d\.tags \|\| \[\]; _vetMeta = metaSig\(\); veTagRow\(\);/.test(CV));
check("copy: Clipboard API, then execCommand, then the value shown to copy by hand",
  /navigator\.clipboard && window\.isSecureContext/.test(CV) && /document\.execCommand\("copy"\)/.test(CV) && /_rm\.view = "copy"/.test(CV));
check("hidden rows carry an eye mark (seen in search and the Hidden filter)", /c\.hidden \? '<span class="ht-hid-mark"/.test(CV));
check("a hidden or unhidden row leaves the list it no longer belongs to (search keeps both)",
  /if \(!_q\) _items = _items\.filter\(function \(k\) \{ return k\.id !== id \|\| \(_statusLoc === "hidden"\) === !!k\.hidden; \}\)/.test(CV));

// ---- 5. CSS, icons, cache, text rules ----
check("CSS: '...' takes the time's place on hover/focus with a mouse, always shown on touch",
  /@media \(hover: hover\) and \(min-width: 641px\) \{\n  \.ht-rmore \{ position: absolute;/.test(CSS) &&
  /\.ht-item:hover \.ht-item-time, \.ht-item:focus-within \.ht-item-time, \.ht-item\.menu-on \.ht-item-time \{ visibility: hidden; \}/.test(CSS));
check("CSS: phone sheet rows are large touch targets", /\.ht-rsheet \.ht-rm-it \{ min-height: 52px;/.test(CSS));
const newCss = CSS.slice(CSS.indexOf("/* Row menu \"...\""), CSS.indexOf(".ht-rsheet-grip"));
const small = [...newCss.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map((m) => +m[1]).filter((n) => n < 16);
check("menu text is at least 16px", newCss.length > 2000 && !small.length, small.join(","));
check("CSS colours come from theme tokens (light and dark)", !/#[0-9a-f]{3,6}\b(?![^;]*var\()/i.test(newCss.replace(/var\(--red, #e5484d\)/g, "")));
["ellipsis", "mail-open", "eye-off", "pin-off", "eye", "copy", "chevron-left", "chevron-right"].forEach((n) => {
  check("icon '" + n + "' is in the bundle", ICONS.indexOf('"' + n + '"') > 0);
});
check("cache-busters bumped", /conversations\.js\?v=(1[5-9]|[2-9]\d)/.test(HTML) && /conversations-filters\.js\?v=[4-9]/.test(HTML) &&
  /lucide-icons\.js\?v=1[2-9]/.test(HTML));
const keys = new Set();
[MOD, CV].forEach((t) => [...t.matchAll(/"(ht\.(?:rm_[a-z_]+|f_st_hidden))"/g)].forEach((m) => keys.add(m[1])));
const missing = [...keys].filter((k) => !VI[k] || !EN[k]);
check(`every new ht.* key (${keys.size}) is in vi and en`, keys.size >= 20 && !missing.length, missing.join(","));
const dashes = [String.fromCharCode(0x2014), String.fromCharCode(0x2013)];
check("no em or en dash in the module, this test or the new strings",
  ![MOD, fs.readFileSync(__filename, "utf8"), ...[...keys].map((k) => VI[k] + EN[k])].some((t) => dashes.some((d) => t.indexOf(d) >= 0)));

if (fails.length) { console.log("\nFAILED " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_inbox_row_menu: all pass");
