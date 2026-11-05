// The Team message list is updated by key instead of being rebuilt on every event (teams.js listSync): unchanged
// messages keep their nodes (a text selection, an open "Show more", a loaded picture, a finger mid-swipe survive), a
// changed message is replaced in place, new ones go where they belong, gone ones are removed, and the order always
// matches. A randomized run checks the result against a full rebuild.
//
//     node tests/js/test_team_keyed_list.js
"use strict";
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const T = require(path.join(D, "teams.js"));
const teamsJs = fs.readFileSync(path.join(D, "teams.js"), "utf8");
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

// Minimal DOM: an element with an ordered child list.
function El(tag, cls) {
  this.tag = tag; this.cls = cls || ""; this.children = []; this.parentNode = null;
  const self = this;
  this.classList = { contains: (c) => self.cls.split(" ").includes(c) };
}
Object.defineProperty(El.prototype, "firstChild", { get() { return this.children[0] || null; } });
Object.defineProperty(El.prototype, "lastChild", { get() { return this.children[this.children.length - 1] || null; } });
Object.defineProperty(El.prototype, "nextSibling", { get() {
  if (!this.parentNode) return null;
  const k = this.parentNode.children;
  return k[k.indexOf(this) + 1] || null;
} });
El.prototype.removeChild = function (n) {
  const i = this.children.indexOf(n);
  if (i < 0) throw new Error("not a child");
  this.children.splice(i, 1); n.parentNode = null; return n;
};
El.prototype.insertBefore = function (n, ref) {
  if (n.parentNode) n.parentNode.removeChild(n);
  const i = ref ? this.children.indexOf(ref) : this.children.length;
  if (ref && i < 0) throw new Error("ref not a child");
  this.children.splice(i, 0, n); n.parentNode = this; return n;
};
El.prototype.appendChild = function (n) { return this.insertBefore(n, null); };

let made = 0;
// One item's HTML becomes 0, 1 or 2 nodes ("a|b" -> two nodes, "" -> none), each remembering its HTML.
const make = (html) => (html ? html.split("|").map((h) => { made++; const n = new El("div"); n.html = h; return n; }) : []);
const flat = (box) => box.children.map((n) => n.html || "[" + n.cls + "]").join(",");
const expect = (items) => items.map((it) => it.html).filter(Boolean).join("|").split("|").filter(Boolean).join(",");

const box = new El("div");
const btn = new El("button", "jv-new-msg");
box.appendChild(btn);
let items = T.listSync(box, [{ key: "older", html: "older" }, { key: "m1", html: "one" }, { key: "m2", html: "two|two-status" }], null, make);
check("first draw: everything built, the jump button kept last", flat(box) === "older,one,two,two-status,[jv-new-msg]", flat(box));
const one = box.children[1];
made = 0;
items = T.listSync(box, [{ key: "older", html: "older" }, { key: "m1", html: "one" }, { key: "m2", html: "two|two-status" },
  { key: "m3", html: "three" }], items, make);
check("a new message: only it is built, the others keep their nodes", made === 1 && box.children[1] === one
  && flat(box) === "older,one,two,two-status,three,[jv-new-msg]", flat(box));
made = 0;
items = T.listSync(box, [{ key: "older", html: "" }, { key: "m1", html: "one" }, { key: "m2", html: "two*|two-status" },
  { key: "m3", html: "three" }], items, make);
check("a changed message is replaced in place; a bar that went empty is removed", made === 2 && box.children[0] === one
  && flat(box) === "one,two*,two-status,three,[jv-new-msg]", flat(box));
made = 0;
items = T.listSync(box, [{ key: "m0", html: "zero" }, { key: "m1", html: "one" }, { key: "m3", html: "three" }], items, make);
check("older message above, a message removed: right order, untouched nodes kept", made === 1 && box.children[1] === one
  && flat(box) === "zero,one,three,[jv-new-msg]", flat(box));
// A node removed by someone else: rebuild instead of guessing.
box.removeChild(one);
made = 0;
items = T.listSync(box, [{ key: "m0", html: "zero" }, { key: "m1", html: "one" }, { key: "m3", html: "three" }], items, make);
check("cache out of step with the page: full rebuild", made === 3 && flat(box) === "zero,one,three,[jv-new-msg]", flat(box));

// Randomized: many steps of adds, removals, edits, reorders (older pages), empty parts; every step equals a full build.
let seed = 7;
const rnd = (n) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };
let state = [];
for (let i = 0; i < 12; i++) state.push({ key: "m" + i, html: "v0-" + i + (rnd(3) === 0 ? "|s-" + i : "") });
const rbox = new El("div");
rbox.appendChild(new El("button", "jv-new-msg"));
let ritems = T.listSync(rbox, state.map((x) => Object.assign({}, x)), null, make);
let bad = "";
let nextId = 100;
for (let step = 0; step < 400 && !bad; step++) {
  const op = rnd(6);
  if (op === 0 && state.length) state.splice(rnd(state.length), 1);
  else if (op === 1) state.push({ key: "m" + nextId, html: "v0-" + nextId++ });
  else if (op === 2 && state.length) { const k = rnd(state.length); state[k] = { key: state[k].key, html: "v" + step + "-" + state[k].key + (rnd(2) ? "|st" : "") }; }
  else if (op === 3) state.unshift({ key: "m" + nextId, html: "old-" + nextId++ });
  else if (op === 4 && state.length) { const k = rnd(state.length); state[k] = { key: state[k].key, html: "" }; }
  else if (op === 5 && state.length > 1) { const a = rnd(state.length), b = rnd(state.length); const t = state[a]; state[a] = state[b]; state[b] = t; }
  const before = new Map(ritems.map((it) => [it.key, it]));
  ritems = T.listSync(rbox, state.map((x) => Object.assign({}, x)), ritems, make);
  const got = rbox.children.filter((n) => !n.cls).map((n) => n.html).join(",");
  if (got !== expect(state)) bad = "step " + step + ": " + got + " != " + expect(state);
  else if (rbox.lastChild.cls !== "jv-new-msg") bad = "step " + step + ": button not last";
  else ritems.forEach((it) => { const b = before.get(it.key); if (b && b.html === it.html && b.nodes.some((n, i) => n !== it.nodes[i])) bad = "step " + step + ": unchanged " + it.key + " rebuilt"; });
}
check("400 random updates: always the same as a full rebuild, unchanged items never rebuilt", !bad, bad);

check("drawMsgs reconciles by key and rebuilds only for a new team or a page it does not own",
  /var sync = function \(\) \{ return listSync\(box, built\.items, prev, htmlNodes\); \};/.test(teamsJs)
  && /S\.listCache = \{ team: S\.team\.team_id, box: box, items: [^\n]*mutateDom\(sync\) : sync\(\) \};/.test(teamsJs)
  && /S\.listCache = null;/.test(teamsJs) && !/box\.innerHTML = \(S\.jumped/.test(teamsJs));
check("the latest answer's Like corner is marked on the nodes, not baked into the HTML (a new answer would replace the old one)",
  /var c = ctx\(null\);/.test(teamsJs) && /lastRx\.classList\.add\("is-last"\)/.test(teamsJs));
check("an owner's reply status rows are an item of their own (a status change leaves the bubble and its selection alone)",
  /items\.push\(\{ key: "r" \+ m\.id, html: rs \}\);/.test(teamsJs));
check("an update of an older message that is not loaded is not appended at the bottom",
  /Number\(nm\.id\) > Number\(S\.msgs\[S\.msgs\.length - 1\]\.id\)/.test(teamsJs));

if (fails) { console.log("\nFAIL - test_team_keyed_list: " + fails); process.exit(1); }
console.log("\nOK - test_team_keyed_list");
