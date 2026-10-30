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
const { napTruoc, coNap } = require("./_thu_tu_nap");   // load order that understands lazy groups (0.417.0)
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
  check("module exposes the tag helpers", ["tagChips", "tagChip", "tagColor"].every((k) => typeof F[k] === "function") &&
    Array.isArray(F.TAG_COLORS) && F.TAG_COLORS.length === 9);
  // Chatbot v5: several tags, "has any of" and "has none of" (the Filter menu); an old single tag moves to "has any of".
  check("filter state carries tag ids; anything but digits is dropped", JSON.stringify(F.sanitize({ tagsAny: ["12", "1 OR 1", 5] }).tagsAny) === '["12","5"]' &&
    JSON.stringify(F.sanitize({ tag: "1 OR 1" }).tagsAny) === "[]" && JSON.stringify(F.sanitize({ tag: 5 }).tagsAny) === '["5"]' &&
    JSON.stringify(F.sanitize({}).tagsNone) === "[]");
  check("'waiting longest' asks for need_reply sorted waiting-first", F.query({ status: "waiting" }) === "&status=need_reply&sort=waiting");
  check("'has phone/email' asks for has_contact, not a status", F.query({ contact: "1" }) === "&has_contact=1");
  check("'has phone/email' combines with a status", F.query({ status: "unread", contact: "1" }) === "&status=unread&has_contact=1");
  check("a browser that saved it as a status keeps the filter", F.sanitize({ status: "contact" }).contact === "1" &&
    F.sanitize({ status: "contact" }).status === "");
  check("has phone/email counts as an active filter", F.activeCount({ contact: "1" }) === 1);
  check("tag filters go to the server as comma lists", F.query({ tagsAny: ["7"], tagsNone: ["8", "9"], bot: "b" }) === "&bot_id=b&tags_any=7&tags_none=8,9");
  check("each tag counts as an active filter", F.activeCount({ tagsAny: ["7"], tagsNone: ["8"] }) === 2 && F.activeCount({ tagsAny: ["x"] }) === 0);
  vm.runInContext(src("dashboard/inbox-v5.js"), ctx);
  const V = win.JavisInboxV5;
  const so = V.filterMenuHtml({}, "status", [], { status: { need_reply: 4 }, has_contact: 2 }, []);
  check("Filter menu status holds 'waiting longest' (need-reply count) and not 'has phone/email'",
    so.indexOf('data-v="waiting"> <span>ht.f_st_wait#4') > 0 && so.slice(so.indexOf("ib-fm-opts")).indexOf("contact") < 0, so);
  check("the has phone/email choice carries its own count", V.filterMenuHtml({}, "contact", [], { has_contact: 2 }, []).indexOf("ht.f_st_contact#2") > 0);
  const to = V.filterMenuHtml({ tagsAny: ["2"] }, "tagsAny", [{ id: 1, name: "Chăm", color: "green" }, { id: 2, name: "<i>x</i>", color: "red" }], {}, [], null, F.tagChip);
  check("Filter menu tags: every tag as a ticked or unticked chip, names escaped",
    /data-tag="1"> <span class="ht-tag"/.test(to) && /data-tag="2" checked>/.test(to) && to.indexOf("<i>") < 0, to);
  const chipsOn = V.activeChips({ tagsAny: ["9"], tagsNone: ["1"] }, [{ id: 1, name: "Chăm" }]);
  check("a tag deleted while filtered still shows as a chip with an x (the list never looks unfiltered)",
    chipsOn.length === 2 && chipsOn[0].text === "ib.fc_tag##9" && chipsOn[1].text === "ib.fc_notag#Chăm");
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
  check("a deleted tag drops out of the saved tag filters", /_tagsAny = _tagsAny\.filter\(keep\); _tagsNone = _tagsNone\.filter\(keep\);/.test(CV));
  check("Info panel: tag row with chips that come off, and the Tag picker (the contact has its own line there)",
    /class="ht-tagrow"/.test(CV) && /ht-tag-x/.test(CV) && /ht-tag-add/.test(CV) && /function tagPopHtml/.test(CV) &&
    /_host\.querySelector\("\.ht-info \.ht-tagrow"\)/.test(CV));
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
  check("index.html loads col-resize.js before conversations.js", napTruoc("col-resize.js", "conversations.js", HTML));

  // ---- 4. text rules ----
  const keys = new Set();
  [MOD, CV].forEach((t) => [...t.matchAll(/"(ht\.(?:tag_[a-z_]+|f_tag_[a-z]+|f_st_(?:wait|contact)|f_aria_tag|contact_left|resize_list))"/g)]
    .forEach((m) => keys.add(m[1])));
  const missing = [...keys].filter((k) => !VI[k] || !EN[k]);
  check(`every new ht.* key (${keys.size}) is in vi and en`, keys.size >= 14 && !missing.length, missing.join(","));
  const newCss = CSS.slice(CSS.indexOf("/* 2026-10-25 (owner"), CSS.indexOf(".ht-sw.on {"));
  const small = [...newCss.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map((m) => +m[1]).filter((n) => n < 16);
  check("new chip, picker and filter text is at least 16px", newCss.length > 1000 && !small.length, small.join(","));
  const dashes = [String.fromCharCode(0x2014), String.fromCharCode(0x2013)];
  check("no em or en dash in the new module code, this test or the new strings",
    ![MOD, fs.readFileSync(__filename, "utf8"), ...[...keys].map((k) => VI[k] + EN[k])].some((t) => dashes.some((d) => t.indexOf(d) >= 0)));

  if (fails.length) { console.log("\nFAILED " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
  console.log("\nOK - test_inbox_tags_ui: all pass");
})();
