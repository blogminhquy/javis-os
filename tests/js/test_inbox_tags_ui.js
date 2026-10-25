/* Bot inbox (Chatbot page, "Hòm thư bot"), owner's requests of 2026-10-25:
 *   - customer tags like Pancake's coloured chips (max 2 on a row, then "+N"), managed from a conversation's Tag picker,
 *     with a tag filter;
 *   - from the Pancake screenshots: "waiting longest" in the status dropdown and "has phone/email" as its own on/off
 *     filter, so it combines with a status (owner: "tách ô lọc riêng");
 *   - on phones the filters fold behind one Filters button next to the search box;
 *   - the list column drags narrower and snaps into a strip (col-resize.js), like the Partners and Chat pages.
 *
 *       node tests/js/test_inbox_tags_ui.js
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

const win = { t: (k, v) => k + (v ? "#" + Object.keys(v).map((x) => v[x]).join(",") : ""), localStorage: { getItem: () => null, setItem() {} } };
const ctx = { window: win, console, encodeURIComponent, String, Object, Array, Number, JSON };
vm.createContext(ctx);
vm.runInContext(MOD, ctx);
const F = win.JavisConvFilters;

(function () {
  // ---- 2. tags and the new filter choices (pure module) ----
  check("module exposes the tag helpers", ["tagOptions", "tagChips", "tagChip", "tagColor"].every((k) => typeof F[k] === "function") &&
    Array.isArray(F.TAG_COLORS) && F.TAG_COLORS.length === 9);
  check("filter state carries a tag id; anything but digits is dropped", F.sanitize({ tag: "12" }).tag === "12" &&
    F.sanitize({ tag: "1 OR 1" }).tag === "" && F.sanitize({ tag: 5 }).tag === "5" && F.sanitize({}).tag === "");
  check("'waiting longest' asks for need_reply sorted waiting-first", F.query({ status: "waiting" }) === "&status=need_reply&sort=waiting");
  check("'has phone/email' asks for has_contact, not a status", F.query({ contact: "1" }) === "&has_contact=1");
  check("'has phone/email' combines with a status", F.query({ status: "need_reply", contact: "1" }) === "&status=need_reply&has_contact=1");
  check("a browser that saved it as a status keeps the filter", F.sanitize({ status: "contact" }).contact === "1" &&
    F.sanitize({ status: "contact" }).status === "");
  check("has phone/email counts as an active filter", F.activeCount({ contact: "1" }) === 1);
  check("tag filter goes to the server as tag=<id>", F.query({ tag: "7", bot: "b" }) === "&bot_id=b&tag=7");
  check("a tag counts as an active filter", F.activeCount({ tag: "7" }) === 1 && F.activeCount({ tag: "x" }) === 0);
  const so = F.statusOptions({ status: { need_reply: 4 }, has_contact: 2 }, "");
  check("status dropdown gains 'waiting longest' (need-reply count) and no longer holds 'has phone/email'",
    so.indexOf('value="waiting">ht.f_st_wait#4') > 0 && so.indexOf("contact") < 0, so);
  check("the has phone/email toggle carries its own count", F.contactLabel({ has_contact: 2 }) === "ht.f_st_contact#2");
  const to = F.tagOptions([{ id: 1, name: "Chăm", count: 3 }, { id: 2, name: "<i>x</i>", count: 0 }], "2");
  check("tag dropdown: all tags, then each tag with its count, current one selected, names escaped",
    to.indexOf("ht.f_tag_all") > 0 && to.indexOf("Chăm (3)") > 0 && /value="2" selected/.test(to) && to.indexOf("<i>") < 0, to);
  check("a tag deleted while selected still has an option (the dropdown never says 'all' while filtering)",
    /value="9" selected>ht\.f_tag_gone/.test(F.tagOptions([{ id: 1, name: "a", count: 0 }], "9")));
  const four = [1, 2, 3, 4].map((i) => ({ id: i, name: "T" + i, color: i === 2 ? "evil\"><script>" : "green" }));
  const chips = F.tagChips(four, 2);
  check("row chips: two tags then '+N' naming the rest in its tooltip", (chips.match(/class="ht-tag"/g) || []).length === 2 &&
    chips.indexOf('>+2</span>') > 0 && chips.indexOf('title="T3, T4"') > 0, chips);
  check("an unknown colour draws grey, never lands in the HTML", F.tagColor("evil\"><script>") === "gray" && chips.indexOf("<script>") < 0);
  check("no chips, no +N", F.tagChips([], 2) === "" && F.tagChips(null, 2) === "");
  check("server palette and dashboard palette are the same nine colours",
    /TAG_COLORS = \("gray", "red", "orange", "yellow", "green", "teal", "blue", "purple", "pink"\)/.test(src("server/conversations.py")) &&
    JSON.stringify(F.TAG_COLORS) === JSON.stringify(["gray", "red", "orange", "yellow", "green", "teal", "blue", "purple", "pink"]));

  // ---- 2b. wiring in conversations.js ----
  check("list rows draw the owner's tags (max 2 + N) and a phone/mail mark when the customer left one",
    /F\.tagChips\(c\.tags, 2\)/.test(CV) && /ht-has-contact/.test(CV));
  check("tag dropdown sits in the one filter row and hides until a tag exists",
    /class="ht-f ht-f-tag"/.test(CV) && /tg\.hidden = !_tags\.length && !st\.tag/.test(CV));
  check("thread: tag row with the contact, chips that come off, and the Tag picker",
    /class="ht-tagrow"/.test(CV) && /ht-tag-x/.test(CV) && /ht-tag-add/.test(CV) && /function tagPopHtml/.test(CV));
  check("picker calls the tag routes", ['"/conversations/" + convId + "/tags"', '"/conversations/tags"', '"/conversations/tags/" + id']
    .every((s) => CV.indexOf(s) >= 0));
  check("tags are part of the thread header's signature (another device's change redraws it)", /c\.tags \|\| \[\], c\.contact \|\| ""/.test(CV));
  check("a tag made from a conversation's picker goes on that conversation", /await setTag\(convId, d\.tag\.id, true\)/.test(CV));

  // ---- 3. drag the list column ----
  check("list column uses the shared col-resize handle with snap to a strip, remembered width",
    /CR\.attach\(col, o\)/.test(CV) && /key: "javis_ht_list_w"/.test(CV) && /snap: \{ below: CR\.FOLD_AT\(LIST_MIN_W\), to: LIST_MINI_W/.test(CV) &&
    /wrap\.classList\.toggle\("ht-mini", !!on\)/.test(CV));
  check("CSS: width var and handle on wide screens only; the strip shows initials", /\.ht-listcol \{ width: var\(--ht-list-w, 320px\)/.test(CSS) &&
    /\.ht-listcol > \.col-resize \{ display: block;/.test(CSS) && /\.ht-mini \.ht-item-ava \{/.test(CSS) &&
    CSS.indexOf("@media (min-width: 901px) {\n  .ht-listcol { width: var(--ht-list-w") > 0);
  check("index.html loads col-resize.js before conversations.js", HTML.indexOf("/static/col-resize.js") > 0 &&
    HTML.indexOf("/static/col-resize.js") < HTML.indexOf("/static/conversations.js"));

  // ---- 4. text rules ----
  const keys = new Set();
  [MOD, CV].forEach((t) => [...t.matchAll(/"(ht\.(?:tag_[a-z_]+|f_tag_[a-z]+|f_st_(?:wait|contact)|f_aria_tag|contact_left|resize_list))"/g)]
    .forEach((m) => keys.add(m[1])));
  const missing = [...keys].filter((k) => !VI[k] || !EN[k]);
  check(`every new ht.* key (${keys.size}) is in vi and en`, keys.size >= 20 && !missing.length, missing.join(","));
  const newCss = CSS.slice(CSS.indexOf("/* 2026-10-25 (owner"), CSS.indexOf(".ht-sw.on {"));
  const small = [...newCss.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map((m) => +m[1]).filter((n) => n < 16);
  check("new chip, picker and filter text is at least 16px", newCss.length > 1000 && !small.length, small.join(","));
  const dashes = [String.fromCharCode(0x2014), String.fromCharCode(0x2013)];
  check("no em or en dash in the new module code, this test or the new strings",
    ![MOD, fs.readFileSync(__filename, "utf8"), ...[...keys].map((k) => VI[k] + EN[k])].some((t) => dashes.some((d) => t.indexOf(d) >= 0)));

  if (fails.length) { console.log("\nFAILED " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
  console.log("\nOK - test_inbox_tags_ui: all pass");
})();
