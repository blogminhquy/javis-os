// The suggested next message in an empty chat box (chat-suggest.js, 2026-11-07).
//
// Owner, 2026-11-07: after Claude answers, its empty box shows a likely next message in grey and Tab fills it in;
// "em xem có thêm được vào javis không?". Pins: Tab only fills an EMPTY box with no modifier and no IME composition;
// the suggestion is the placeholder, never text in the box (nothing is sent by accident); typing hides it and an empty
// box shows it again; Tab and the Tab chip fill it in; a newer request or a send drops an older answer; switched off
// on the server, nothing shows. Both chat screens use it (owner rule of 2026-11-05): the main chat and Teams.
//
//     node tests/js/test_chat_suggest.js
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const D = path.join(__dirname, "..", "..", "dashboard");
const SRC = fs.readFileSync(path.join(D, "chat-suggest.js"), "utf8");
const P = require(path.join(D, "chat-suggest.js"));
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

// ---- pure parts ----
const tab = (o) => Object.assign({ key: "Tab", shiftKey: false, ctrlKey: false, altKey: false, metaKey: false }, o);
check("Tab in an empty box with a suggestion accepts", P.acceptsKey(tab(), "", "ok", false) === true);
check("Tab in a box with text does not (normal Tab)", P.acceptsKey(tab(), "abc", "ok", false) === false);
check("Shift+Tab never accepts (focus goes back)", P.acceptsKey(tab({ shiftKey: true }), "", "ok", false) === false);
check("no suggestion: Tab moves focus as usual", P.acceptsKey(tab(), "", "", false) === false);
check("mid IME composition: no", P.acceptsKey(tab(), "", "ok", true) === false);
check("another key: no", P.acceptsKey(tab({ key: "Enter" }), "", "ok", false) === false);
const ctx = P.shapeContext([{ role: "user", text: "a" }, { role: "javis", text: " " }, null,
  ...Array.from({ length: 9 }, (_, i) => ({ role: i % 2 ? "user" : "javis", text: "m" + i }))]);
check("context: at most 6, empty dropped, javis read as assistant",
  ctx.length === 6 && ctx.every(m => m.text.trim()) && ctx[ctx.length - 1].role === "assistant");

// ---- the controller in a small fake page ----
function classes() {
  const s = new Set();
  return { add: (c) => s.add(c), remove: (c) => s.delete(c), contains: (c) => s.has(c) };
}
function makeEl(tag) {
  return { tagName: tag, hidden: false, attrs: {}, listeners: {}, children: [], parentNode: null, className: "",
    setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k] || null; },
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
    insertBefore(c, ref) { c.parentNode = this; const i = ref ? this.children.indexOf(ref) : -1; if (i < 0) this.children.push(c); else this.children.splice(i, 0, c); },
    click() { (this.listeners.click || []).forEach(f => f({ preventDefault() {} })); } };
}
function makeInput() {
  const el = makeEl("TEXTAREA");
  Object.assign(el, { value: "", placeholder: "What should I do?", disabled: false, isConnected: true, classList: classes(),
    events: [], focus() {}, setSelectionRange() {}, dispatchEvent(e) { this.events.push(e.type); } });
  el.attrs["data-i18n-ph"] = "bar.input_ph";
  return el;
}
const pending = [];
let enabledOnServer = true;
const posts = [];
function fakeFetch(url, opts) {
  if (!opts || !opts.method || opts.method === "GET") {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ enabled: enabledOnServer }) });
  }
  if (url === "/settings") {
    posts.push(opts.body);
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) });
  }
  return new Promise((resolve) => pending.push((d) => resolve({ ok: true, json: () => Promise.resolve(d) })));
}
class FakeForm { constructor() { this.data = {}; } append(k, v) { this.data[k] = v; } }
const winListeners = {};
const registered = [];
const sandbox = {
  console, Promise, setTimeout, JSON, String, Array, Number,
  document: { readyState: "complete", createElement: makeEl, addEventListener() {} },
  fetch: fakeFetch, FormData: FakeForm, AbortController: class { abort() { this.aborted = true; } },
  Event: class { constructor(t) { this.type = t; } },
};
sandbox.window = { t: (k) => "T(" + k + ")", addEventListener: (t, f) => { winListeners[t] = f; },
  JavisComposerMenu: { register: (it) => registered.push(it) } };
vm.createContext(sandbox);
vm.runInContext(SRC, sandbox);
const S = sandbox.window.JavisSuggest;
const tick = () => new Promise((r) => setTimeout(r, 0));

(async () => {
  check("the switch sits in the composer + menu", registered.length === 1 && registered[0].id === "suggest-next");
  check("menu hint says On while on", registered[0].hint() === "T(sug.on)");

  const input = makeInput();
  const row = makeEl("DIV"), gap = makeEl("SPAN");
  row.insertBefore(gap, null);
  const c = S.attach({ input: () => input, chipHost: () => [row, gap], composing: () => false });

  let p = c.request([{ role: "user", text: "check 2 PRs" }, { role: "assistant", text: "Which way for each PR?" }]);
  await tick(); await tick();
  check("a request goes to the server", pending.length === 1);
  pending.shift()({ ok: true, text: "ok do both" });
  await p;
  check("the suggestion is the placeholder of the empty box", input.placeholder === "ok do both" && input.value === "");
  check("the box is marked", input.classList.contains("has-suggest"));
  const chip = row.children.find(x => x.className === "sug-tab");
  check("the Tab chip shows before the gap", chip && !chip.hidden && row.children.indexOf(chip) < row.children.indexOf(gap));

  input.value = "h"; c.onInput();
  check("typing hides it and puts the usual placeholder back", input.placeholder === "What should I do?" && chip.hidden);
  check("Tab with text in the box does nothing", c.onKeydown(Object.assign(tab(), { preventDefault() {} })) === false);
  input.value = ""; c.onInput();
  check("an empty box shows it again", input.placeholder === "ok do both");

  let prevented = false;
  const took = c.onKeydown(Object.assign(tab(), { preventDefault() { prevented = true; } }));
  check("Tab fills the box", took && prevented && input.value === "ok do both" && input.events.includes("input"));
  check("then the suggestion is gone", c.current() === "" && input.placeholder === "What should I do?" && chip.hidden);

  // The chip fills it in too (a phone has no Tab key).
  input.value = "";
  p = c.request([{ role: "assistant", text: "Done. Anything else?" }]);
  await tick(); await tick();
  pending.shift()({ ok: true, text: "send me the report" });
  await p;
  chip.click();
  check("the Tab chip fills the box", input.value === "send me the report");

  // A newer request (or a send) drops an older answer that comes late.
  input.value = "";
  const p1 = c.request([{ role: "assistant", text: "one" }]);
  await tick(); await tick();
  const late = pending.shift();
  c.clear();
  late({ ok: true, text: "stale" });
  await p1;
  check("an answer arriving after clear() is dropped", input.placeholder === "What should I do?" && c.current() === "");

  // Javis has not answered yet: nothing asked.
  const before = pending.length;
  await c.request([{ role: "user", text: "hi" }]);
  check("the owner spoke last: no request", pending.length === before);

  // The language switched while a suggestion showed.
  p = c.request([{ role: "assistant", text: "two" }]);
  await tick(); await tick();
  pending.shift()({ ok: true, text: "go" });
  await p;
  input.placeholder = "T(bar.input_ph)";   // applyLang wrote the translation over the suggestion
  winListeners["javis:i18n"]();
  check("after a language switch the suggestion shows again", input.placeholder === "go");
  c.clear();
  check("and clearing restores the TRANSLATED placeholder", input.placeholder === "T(bar.input_ph)");

  // Switched off from the menu: saved on the server, nothing more is asked.
  registered[0].run();
  await tick(); await tick();
  check("the menu switch saves settings.chat.suggest_next", posts.length === 1 &&
    posts[0].data.section === "chat" && JSON.parse(posts[0].data.data).suggest_next === false);
  check("menu hint says Off", registered[0].hint() === "T(sug.off)");
  const n = pending.length;
  await c.request([{ role: "assistant", text: "three" }]);
  check("off: no request", pending.length === n && input.placeholder === "T(bar.input_ph)");

  // ---- wiring on every chat screen ----
  const app = fs.readFileSync(path.join(D, "app.js"), "utf8");
  const teams = fs.readFileSync(path.join(D, "teams.js"), "utf8");
  const html = fs.readFileSync(path.join(D, "index.html"), "utf8");
  check("index.html loads chat-suggest.js before app.js",
    html.indexOf("/static/chat-suggest.js") > 0 && html.indexOf("/static/chat-suggest.js") < html.indexOf("/static/app.js?v="));
  check("main chat: attached to #chatInput with the chip in the composer row",
    /JavisSuggest\.attach\(\{\s*input: \(\) => chatInput/.test(app) && app.includes('getElementById("cpRow")'));
  const kd = app.slice(app.indexOf('chatInput.addEventListener("keydown"'));
  check("main chat: Tab is checked before Enter sends", kd.indexOf("chatSuggest.onKeydown(e)") < kd.indexOf("enterSends"));
  const done = app.slice(app.indexOf('data.type === "turn_done"'));
  check("main chat: a suggestion is asked when a turn ends, not during a voice call",
    /chatSuggest\.request\(/.test(done.slice(0, 6000)) && done.slice(0, 6000).includes("!handsFreeActive()"));
  check("main chat: sending drops the suggestion",
    app.slice(app.indexOf("function sendMessage("), app.indexOf("function sendMessage(") + 300).includes("dropSuggest()"));
  check("main chat: typing shows or hides it", app.includes("chatSuggest.onInput()"));
  check("Teams: attached to .tm-input with the chip before the mic",
    /window\.JavisSuggest\.attach\(/.test(teams) && teams.includes('row.querySelector(".tm-mic")'));
  check("Teams: Tab handled after the @mention list (which also uses Tab)",
    teams.indexOf("sugKey(e)) return;") < teams.indexOf("teamSuggest.onKeydown(e)"));
  check("Teams: asked after an assistant message", /author_kind === "agent"\) queueNextSug\(/.test(teams));
  check("Teams: sending and switching team drop it",
    /stopMic\(\);\s*dropNextSug\(\);/.test(teams) && /keepTeam\(\);\s*dropNextSug\(\);/.test(teams));
  check("Teams: a composer redraw puts it back", teams.includes("if (teamSuggest) teamSuggest.refresh();"));
  const vi = JSON.parse(fs.readFileSync(path.join(D, "i18n", "vi.json"), "utf8"));
  const en = JSON.parse(fs.readFileSync(path.join(D, "i18n", "en.json"), "utf8"));
  check("labels in vi and en", ["sug.menu", "sug.on", "sug.off", "sug.use"].every(k => vi[k] && en[k]));

  if (fails) { console.log("\n" + fails + " FAIL"); process.exit(1); }
  console.log("\nOK - chat_suggest: all pass");
})();
