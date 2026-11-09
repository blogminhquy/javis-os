/* The file editors save by themselves, keep a local copy, and take dictation (2026-11-09).

   Customer report (Star Global, 09/11/2026): rewriting an email draft in the note editor, a stray touchpad swipe made
   the browser go Back and every word typed since the last Save press was lost, several times. They asked for Google
   Docs style autosave, a mic like the chat box, and lines that wrap instead of running off to the right (the sideways
   scroll back is the swipe that went Back).

   Run: node tests/js/test_editor_autosave.js */
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const { napTruoc } = require("./_thu_tu_nap.js");

const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + JSON.stringify(extra) + "]"));
  if (!cond) fails.push(name);
}

// ---- a tiny browser: localStorage, timers we drive by hand, input events ----
const mem = {};
global.localStorage = {
  getItem: (k) => (k in mem ? mem[k] : null),
  setItem: (k, v) => { mem[k] = String(v); },
  removeItem: (k) => { delete mem[k]; },
};
let clock = 0;
const timers = [];
global.setTimeout = (fn, ms) => { const t = { fn, at: clock + (ms || 0), id: timers.length + 1 }; timers.push(t); return t.id; };
global.clearTimeout = (id) => { const t = timers.find((x) => x.id === id); if (t) t.fn = null; };
async function advance(ms) {
  clock += ms;
  for (;;) {
    const due = timers.filter((t) => t.fn && t.at <= clock).sort((a, b) => a.at - b.at)[0];
    if (!due) break;
    const fn = due.fn; due.fn = null; fn();
    await new Promise((r) => setImmediate(r));
  }
  for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r));
}
function box(value) {
  const ls = [];
  return { value, addEventListener: (n, f) => { if (n === "input") ls.push(f); },
    removeEventListener: (n, f) => { const i = ls.indexOf(f); if (i >= 0) ls.splice(i, 1); },
    type(v) { this.value = v; ls.slice().forEach((f) => f()); }, listeners: ls };
}

const A = require(path.join(ROOT, "dashboard/editor-autosave.js"));

(async () => {
  // ---- 1. pure helpers ----
  check("hash: same text, same fingerprint", A.hash("Dear Team HR") === A.hash("Dear Team HR"));
  check("hash: one letter apart differs", A.hash("Dear Team HR") !== A.hash("Dear Team HQ"));
  const now = 1e12;
  check("pickDraft: draft made from the file on disk comes back",
    A.pickDraft({ base: A.hash("old"), text: "old + new words", ts: now - 1000 }, "old", now) === "old + new words");
  check("pickDraft: file changed since (Javis edited it) wins",
    A.pickDraft({ base: A.hash("old"), text: "old + new words", ts: now - 1000 }, "edited by Javis", now) === null);
  check("pickDraft: a week-old draft is dropped",
    A.pickDraft({ base: A.hash("old"), text: "x", ts: now - 8 * 24 * 3600 * 1000 }, "old", now) === null);
  check("pickDraft: same as the file is nothing to restore",
    A.pickDraft({ base: A.hash("old"), text: "old", ts: now }, "old", now) === null);
  check("pickDraft: junk in storage is ignored", A.pickDraft("nope", "old", now) === null && A.pickDraft(null, "old", now) === null);

  // ---- 2. a pause in typing writes the file ----
  const writes = [];
  let ok = true;
  const ta = box("Dear Team HR,");
  const states = [];
  const ctl = A.attach({ key: "b::mail.md", original: "Dear Team HR,", get: () => ta.value, sources: [ta],
    save: (c, o) => { writes.push({ c, keepalive: !!(o && o.keepalive) }); return Promise.resolve(ok); },
    onStatus: (s) => states.push(s), apply: (t) => { ta.value = t; } });
  check("opening a file writes nothing", writes.length === 0 && states[states.length - 1] === "idle");
  ta.type("Dear Team HR, the board approved");
  check("typing marks it unsaved", ctl.status() === "dirty");
  await advance(600);
  check("a local copy is kept while typing", !!mem[A.DRAFT_PREFIX + "b::mail.md"]);
  check("no write while still inside the pause", writes.length === 0);
  await advance(A.DELAY_MS);
  check("the pause writes the file", writes.length === 1 && writes[0].c === "Dear Team HR, the board approved", writes);
  check("then it shows Saved and drops the local copy", ctl.status() === "saved" && !mem[A.DRAFT_PREFIX + "b::mail.md"]);
  await advance(10000);
  check("nothing new, nothing written again", writes.length === 1);

  // ---- 3. a failed write keeps the words and tries again ----
  ok = false;
  ta.type("Dear Team HR, the board approved the plan");
  await advance(A.DELAY_MS + 10);
  check("failed write shows the error", ctl.status() === "error");
  check("failed write keeps the local copy", !!mem[A.DRAFT_PREFIX + "b::mail.md"]);
  ok = true;
  await advance(6000);
  check("it tries again by itself", ctl.status() === "saved" && writes[writes.length - 1].c.endsWith("the plan"));

  // ---- 4. leaving the page sends the last words with keepalive ----
  ta.type("Dear Team HR, the board approved the plan. Thanks");
  ctl.leaving();
  await advance(1);
  check("page hidden: written at once with keepalive", writes[writes.length - 1].keepalive === true &&
    writes[writes.length - 1].c.endsWith("Thanks"));

  // ---- 5. closing writes what is pending; close(true) after a delete writes nothing ----
  ta.type("final words");
  const n0 = writes.length;
  await ctl.close();
  check("closing writes the last words", writes.length === n0 + 1 && writes[writes.length - 1].c === "final words");
  check("closed editor stops listening", ta.listeners.length === 0);

  const tb = box("doc");
  const w2 = [];
  const c2 = A.attach({ key: "b::gone.md", original: "doc", get: () => tb.value, sources: [tb],
    save: (c) => { w2.push(c); return Promise.resolve(true); } });
  tb.type("doc edited");
  await advance(100);
  await c2.close(true);
  await advance(5000);
  check("a deleted file is not written back", w2.length === 0);

  // ---- 6. a tab that died before the write: the words come back on the next open ----
  mem[A.DRAFT_PREFIX + "b::lost.md"] = JSON.stringify({ base: A.hash("Dear Team HR,"), text: "Dear Team HR, long rewrite", ts: Date.now() });
  const tc = box("Dear Team HR,");
  const w3 = [];
  let restored = false;
  A.attach({ key: "b::lost.md", original: "Dear Team HR,", get: () => tc.value, sources: [tc],
    save: (c) => { w3.push(c); return Promise.resolve(true); }, apply: (t) => { tc.value = t; },
    onRestored: () => { restored = true; } });
  check("the lost words are put back", tc.value === "Dear Team HR, long rewrite" && restored);
  await advance(A.DELAY_MS + 10);
  check("and written to the file", w3[0] === "Dear Team HR, long rewrite");

  mem[A.DRAFT_PREFIX + "b::changed.md"] = JSON.stringify({ base: A.hash("v1"), text: "v1 + mine", ts: Date.now() });
  const td = box("v2 by Javis");
  A.attach({ key: "b::changed.md", original: "v2 by Javis", get: () => td.value, sources: [td],
    save: () => Promise.resolve(true), apply: (t) => { td.value = t; } });
  check("a file changed since keeps its new content", td.value === "v2 by Javis" && !mem[A.DRAFT_PREFIX + "b::changed.md"]);

  // ---- 7. the mic places words where the cursor was ----
  const E = require(path.join(ROOT, "dashboard/editor-dictate.js"));
  const r1 = E.insertPlain("Dear Team HR,", "the board approved", "");
  check("mic: words after the text get one space", r1.value === "Dear Team HR, the board approved" && r1.caret === r1.value.length, r1);
  const r2 = E.insertPlain("Dear ", "Team", "HR");
  check("mic: words in the middle are spaced on both sides", r2.value === "Dear Team HR", r2);
  check("mic: a comma after the words needs no space", E.insertPlain("A", "b", ", c").value === "A b, c");
  check("mic: nothing heard changes nothing", E.insertPlain("ab", "  ", "cd").value === "abcd");
  check("mic: context is the last lines before the cursor",
    JSON.stringify(E.contextLines("a\n\nb\nc\nd\ne")) === JSON.stringify(["b", "c", "d", "e"]));

  // ---- 8. both editors use it, the page loads it in time ----
  const cs = read("dashboard/console.js");
  const fe = read("dashboard/file-editor.js");
  const html = read("dashboard/index.html");
  const css = read("dashboard/style.css");
  check("note editor attaches autosave", /JavisAutosave\.attach\(/.test(cs));
  check("note editor attaches the mic", /JavisEditorDictate\.attach\(/.test(cs));
  check("note editor writes pending words when it closes", /function closeNote\(\)[\s\S]{0,700}_neDropAssist\(\)/.test(cs));
  check("note editor deletes without writing back", /_neDropAssist\(true\)/.test(cs));
  check("popup editor attaches autosave", /AS\.attach\(/.test(fe));
  check("popup editor attaches the mic", /ED\.attach\(/.test(fe));
  check("popup editor writes pending words when it closes (also a Back swipe)", /function close\(\)[\s\S]{0,300}dropAssist\(\)/.test(fe));
  check("index.html loads both before the editors",
    napTruoc("editor-autosave.js", ["file-editor.js", "console.js"], html) &&
    napTruoc("editor-dictate.js", ["file-editor.js", "console.js"], html));
  check("dictate.js is on the page for the mic", /static\/dictate\.js\?/.test(html));
  check("no sideways overscroll while editing (no swipe Back)", /html\.jv-editing[^{]*\{[^}]*overscroll-behavior-x:\s*none/.test(css));
  check("code blocks in the editor wrap", /\.ne-wys \.code-block\s*\{[^}]*white-space:\s*pre-wrap/.test(css));

  // ---- 9. new words on screen exist in both dictionaries ----
  const vi = JSON.parse(read("dashboard/i18n/vi.json"));
  const en = JSON.parse(read("dashboard/i18n/en.json"));
  ["cs.ne_saving", "cs.ne_save_err", "cs.ne_save_err_title", "cs.ne_draft_restored"].forEach((k) =>
    check("i18n " + k, !!vi[k] && !!en[k]));

  for (const f of ["dashboard/editor-autosave.js", "dashboard/editor-dictate.js", "tests/js/test_editor_autosave.js"]) {
    check("no em dash in " + f, !/[\u2013\u2014]/.test(read(f)));
  }

  if (fails.length) { console.log("\n" + fails.length + " FAIL"); process.exit(1); }
  console.log("\nall ok");
})();
