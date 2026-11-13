// The suggested next message in the chat box (chat-suggest.js, 2026-11-07, typing along 2026-11-13).
//
// Owner, 2026-11-07: after Claude answers, its empty box shows a likely next message in grey and Tab fills it in;
// "em xem có thêm được vào javis không?". Pins: the suggestion is the placeholder of the empty box, never text in it
// (nothing is sent by accident); Tab and the Tab chip (a ">" after the text on a touch screen) fill it in, with no
// modifier and no IME composition; a newer
// request or a send drops an older answer; switched off on the server, nothing shows. Both chat screens use it (owner
// rule of 2026-11-05): the main chat and Teams.
//
// 2026-11-13, a user's wish passed on by the owner: the suggestion vanished at the first key. Pins: typing ALONG it
// keeps the rest in grey after the typed text (case and Vietnamese marks do not count); Tab takes the rest and Right
// Arrow at the end of the text takes one word; typing something else hides it and, after a pause, asks the server to
// finish that draft ({draft, hint}), one request at a time, at most `live.max` per turn, never twice for one draft.
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
check("Tab with the start of the suggestion typed accepts the rest", P.acceptsKey(tab(), "ok d", "ok do both", false) === true);
check("Tab with the whole suggestion typed is a normal Tab", P.acceptsKey(tab(), "ok do both", "ok do both", false) === false);

// 2026-11-13: what a suggestion adds after the text already typed.
const SUG = "Em sửa kỹ năng nối hạ tầng luôn nhé";
check("rest: an empty box gets the whole suggestion", P.restOf("", SUG) === SUG);
check("rest: typed along, the rest follows", P.restOf("Em sửa kỹ", SUG) === " năng nối hạ tầng luôn nhé");
check("rest: case and Vietnamese marks do not count (half typed 'su' follows 'sửa')",
  P.restOf("em su", SUG) === "a kỹ năng nối hạ tầng luôn nhé" && P.restOf("EM SUA KY NANG", SUG) === " nối hạ tầng luôn nhé");
check("rest: đ and d are the same letter", P.restOf("danh d", "đánh dấu") === "ấu");
check("rest: decomposed marks (a Mac keyboard) line up with composed ones",
  P.restOf("Em su\u031b\u0309a", SUG) === " kỹ năng nối hạ tầng luôn nhé");
check("rest: other text is not the start of it", P.restOf("Anh", SUG) === "" && P.restOf("Em sửa xong", SUG) === "");
check("rest: nothing left once all of it is typed", P.restOf(SUG, SUG) === "" && P.restOf(SUG + " ạ", SUG) === "");
check("rest: letters of other scripts are compared as they are", P.restOf("か", "がんばって") === "");
check("fold keeps one character per character", P.fold("Đường SỬA").length === 9 && P.fold("Đường SỬA") === "duong sua");
check("next word comes with the space before it", P.nextWord(" năng nối") === " năng" && P.nextWord("a kỹ") === "a" &&
  P.nextWord("nhé") === "nhé");
const right = (o) => Object.assign({ key: "ArrowRight", shiftKey: false, ctrlKey: false, altKey: false, metaKey: false }, o);
const boxAt = (value, at) => ({ value, selectionStart: at == null ? value.length : at, selectionEnd: at == null ? value.length : at });
check("Right Arrow at the end of the text takes a word", P.acceptsWordKey(right(), boxAt("Em sửa"), SUG, false) === true);
check("Right Arrow inside the text only moves the caret", P.acceptsWordKey(right(), boxAt("Em sửa", 2), SUG, false) === false);
check("Right Arrow with a selection, a modifier or an IME open: no",
  P.acceptsWordKey(right(), { value: "Em", selectionStart: 0, selectionEnd: 2 }, SUG, false) === false &&
  P.acceptsWordKey(right({ shiftKey: true }), boxAt("Em"), SUG, false) === false &&
  P.acceptsWordKey(right(), boxAt("Em"), SUG, true) === false);
check("Right Arrow with nothing on offer: no", P.acceptsWordKey(right(), boxAt("Anh"), SUG, false) === false);
check("a draft worth finishing: one line, two letters or more, not a long text",
  P.liveDraft("ok") && P.liveDraft("ok làm ") && !P.liveDraft("a") && !P.liveDraft(" ") && !P.liveDraft("dòng 1\ndòng 2") &&
  !P.liveDraft("x".repeat(201)));
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
  return { tagName: tag, hidden: false, attrs: {}, listeners: {}, children: [], parentNode: null, className: "", textContent: "",
    setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k] || null; },
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
    appendChild(c) { this.insertBefore(c, null); },
    insertBefore(c, ref) {
      if (c.parentNode) c.parentNode.children = c.parentNode.children.filter(x => x !== c);
      c.parentNode = this;
      const i = ref ? this.children.indexOf(ref) : -1;
      if (i < 0) this.children.push(c); else this.children.splice(i, 0, c);
    },
    get nextSibling() { const k = this.parentNode ? this.parentNode.children : []; return k[k.indexOf(this) + 1] || null; },
    get previousSibling() { const k = this.parentNode ? this.parentNode.children : []; return k[k.indexOf(this) - 1] || null; },
    click() { (this.listeners.click || []).forEach(f => f({ preventDefault() {} })); } };
}
function makeInput() {
  const el = makeEl("TEXTAREA");
  Object.assign(el, { value: "", placeholder: "What should I do?", disabled: false, isConnected: true, classList: classes(),
    events: [], focus() {}, setSelectionRange() {}, dispatchEvent(e) { this.events.push(e.type); } });
  el.attrs["data-i18n-ph"] = "bar.input_ph";
  return el;
}
const pending = [];   // answers owed to "what will the owner say next"
const drafts = [];    // answers owed to "finish this draft": { body, answer(d) }
let enabledOnServer = true;
const WAIT = 15;      // the pause the server asks for, short here
const posts = [];
function fakeFetch(url, opts) {
  if (!opts || !opts.method || opts.method === "GET") {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ enabled: enabledOnServer, live: { wait_ms: WAIT, max: 3 } }) });
  }
  if (url === "/settings") {
    posts.push(opts.body);
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) });
  }
  const body = JSON.parse(opts.body);
  return new Promise((resolve) => {
    const answer = (d) => resolve({ ok: true, json: () => Promise.resolve(d) });
    if (body.draft) drafts.push({ body, answer }); else pending.push(answer);
  });
}
class FakeForm { constructor() { this.data = {}; } append(k, v) { this.data[k] = v; } }
const winListeners = {};
const registered = [];
const sandbox = {
  console, Promise, setTimeout, clearTimeout, JSON, String, Array, Number, Object,
  document: { readyState: "complete", createElement: makeEl, addEventListener() {}, activeElement: null },
  fetch: fakeFetch, FormData: FakeForm, AbortController: class { abort() { this.aborted = true; } },
  Event: class { constructor(t) { this.type = t; } },
};
sandbox.window = { t: (k) => "T(" + k + ")", addEventListener: (t, f) => { winListeners[t] = f; },
  JavisComposerMenu: { register: (it) => registered.push(it) } };
vm.createContext(sandbox);
vm.runInContext(SRC, sandbox);
const S = sandbox.window.JavisSuggest;
const tick = () => new Promise((r) => setTimeout(r, 0));
const pause = () => new Promise((r) => setTimeout(r, WAIT * 4));   // longer than the wait before a draft is sent

(async () => {
  check("the switch sits in the composer + menu", registered.length === 1 && registered[0].id === "suggest-next");
  check("menu hint says On while on", registered[0].hint() === "T(sug.on)");

  const input = makeInput();
  const row = makeEl("DIV"), gap = makeEl("SPAN"), card = makeEl("DIV");
  row.insertBefore(gap, null);
  card.appendChild(input);
  card.appendChild(row);
  sandbox.document.activeElement = input;
  let composing = false, quiet = false;
  const c = S.attach({ input: () => input, chipHost: () => [row, gap], composing: () => composing, quiet: () => quiet });
  // The grey rest after typed text: a layer right after the box, [typed (unseen), rest].
  const ghost = () => card.children.find(x => String(x.className).split(" ").includes("sug-ghost")) || null;
  // [typed (unseen), the rest but its last word, [its last word, the ">" of a touch screen]]
  const greyRest = () => { const g = ghost(); return g && !g.hidden ? g.children[1].textContent + g.children[2].children[0].textContent : null; };
  const goButton = () => ghost().children[2].children[1];
  const type = (text) => { input.value = text; input.selectionStart = input.selectionEnd = text.length; c.onInput(); };

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
  check("nothing shows while the box holds all of it", c.showing() === "" && input.placeholder === "What should I do?" && chip.hidden);
  // Owner on a computer, 2026-11-13: "xóa vẫn bị mất gợi ý". A sentence taken whole stays on offer until it is sent.
  type("ok do b");
  check("deleting part of a taken suggestion brings the rest back", c.showing() === "oth" && greyRest() === "oth" && !chip.hidden);
  type("");
  check("emptying the box after taking it shows the suggestion again", input.placeholder === "ok do both" && greyRest() === "ok do both");

  // ---- 2026-11-13: the suggestion stays while the owner types along it ----
  input.value = "";
  p = c.request([{ role: "user", text: "rà spec" }, { role: "assistant", text: "Anh muốn em sửa kỹ năng nối hạ tầng không?" }]);
  await tick(); await tick();
  pending.shift()({ ok: true, text: SUG });
  await p;
  check("an empty box: the suggestion is its placeholder, drawn by the layer while the box hides its own copy",
    input.placeholder === SUG && greyRest() === SUG && ghost().children[0].textContent === "" &&
    input.classList.contains("sug-ghosted"));
  // Owner, 2026-11-13: "hiện ngay sau cùng khung chữ gợi ý, đừng hiện cùng hàng với voice và các nút. Ví dụ ngay sau
  // chữ 'luôn nhé >' thì có nút đấy".
  check("the > of a touch screen stands right after the last word, tied to it",
    ghost().children[2].className === "sug-ghost-tail" && ghost().children[2].children[0].textContent === "nhé" &&
    goButton().className === "sug-go" && ghost().children[1].textContent === "Em sửa kỹ năng nối hạ tầng luôn ");
  check("the > is a button with a name, out of the Tab order (Tab already takes the suggestion)",
    goButton().type === "button" && goButton().attrs["aria-label"] === "T(sug.use)" && goButton().tabIndex === -1);
  type("Em s");
  check("typing along keeps the rest in grey after the typed text",
    greyRest() === "ửa kỹ năng nối hạ tầng luôn nhé" && ghost().children[0].textContent === "Em s");
  check("the layer sits right after the box, so it paints over it", card.children.indexOf(ghost()) === card.children.indexOf(input) + 1);
  check("the box gets its usual placeholder back and the chip stays", input.placeholder === "What should I do?" && !chip.hidden &&
    input.classList.contains("has-suggest"));
  type("em sua ky");
  check("typed without marks or capitals it still follows", greyRest() === " năng nối hạ tầng luôn nhé" && c.showing() === " năng nối hạ tầng luôn nhé");
  let stopped = false;
  check("Right Arrow at the end takes ONE word, in the suggestion's own spelling",
    c.onKeydown(Object.assign(right(), { preventDefault() { stopped = true; } })) === true && stopped &&
    input.value === "Em sửa kỹ năng" && greyRest() === " nối hạ tầng luôn nhé" && c.current() === SUG);
  input.selectionStart = input.selectionEnd = 2;
  check("Right Arrow inside the text is left to the caret", c.onKeydown(Object.assign(right(), { preventDefault() {} })) === false);
  input.selectionStart = input.selectionEnd = input.value.length;
  composing = true;
  check("mid IME composition neither key takes anything",
    c.onKeydown(Object.assign(tab(), { preventDefault() {} })) === false && c.onKeydown(Object.assign(right(), { preventDefault() {} })) === false);
  composing = false;
  check("Tab with the start typed takes the rest", c.onKeydown(Object.assign(tab(), { preventDefault() {} })) === true && input.value === SUG);
  check("taken whole: nothing shows while the box holds all of it",
    c.showing() === "" && greyRest() === null && chip.hidden && !input.classList.contains("has-suggest"));
  check("and the box shows its own placeholder text again", !input.classList.contains("sug-ghosted"));
  input.selectionStart = input.selectionEnd = input.value.length;   // the caret a real box puts after the taken text
  c.onInput();   // the screen sizes the box to the taken text and tells the suggestion
  await pause();
  check("a taken suggestion may be carried on, with no hint of another way to go (it is the draft itself)",
    drafts.length === 1 && drafts[0].body.draft === SUG && drafts[0].body.hint === "");
  drafts.shift().answer({ ok: true, text: "" });
  await tick(); await tick();
  type(SUG.slice(0, -2));
  check("deleting the end of a taken suggestion brings the rest back in grey",
    greyRest() === "hé" && c.current() === SUG && !chip.hidden && input.classList.contains("has-suggest"));
  let again = false;
  check("and Tab takes it again", c.onKeydown(Object.assign(tab(), { preventDefault() { again = true; } })) === true && again && input.value === SUG);
  type("Em sửa");
  check("word by word to the end, then deleted: still on offer", (() => {
    for (let i = 0; i < 9 && c.showing(); i++) {
      input.selectionStart = input.selectionEnd = input.value.length;
      c.onKeydown(Object.assign(right(), { preventDefault() {} }));
    }
    if (input.value !== SUG) return false;
    type(SUG.slice(0, -4));
    return greyRest() === " nhé";
  })());
  type("");
  check("the box emptied after taking: the suggestion is back whole", input.placeholder === SUG && greyRest() === SUG);

  // ---- 2026-11-13: a draft that goes another way is finished after a pause ----
  input.value = "";
  const CHAT = [{ role: "user", text: "rà spec" }, { role: "assistant", text: "Anh muốn em sửa kỹ năng nối hạ tầng không?" }];
  p = c.request(CHAT);
  await tick(); await tick();
  pending.shift()({ ok: true, text: SUG });
  await p;
  type("Em sửa kỹ năng code");
  check("typing something else hides the suggestion at once", greyRest() === null && chip.hidden && input.placeholder === "What should I do?");
  check("nothing is asked while the owner is still typing", drafts.length === 0);
  await pause();
  check("after a pause the server is asked to finish the draft, with the chat and the suggestion that showed",
    drafts.length === 1 && drafts[0].body.draft === "Em sửa kỹ năng code" && drafts[0].body.hint === SUG &&
    drafts[0].body.context.length === 2 && drafts[0].body.context[1].role === "assistant");
  type("Em sửa kỹ năng code t");
  await pause();
  check("one request at a time: a newer draft waits for the answer on its way", drafts.length === 1);
  drafts.shift().answer({ ok: true, text: " trước, hạ tầng để sau" });
  await tick(); await tick();
  check("the answer still fits the text typed meanwhile: the rest shows in grey", greyRest() === "rước, hạ tầng để sau" && !chip.hidden);
  await pause();
  check("a draft that is being followed asks nothing more", drafts.length === 0);
  check("the > follows the rest that is left", ghost().children[2].children[0].textContent === "sau");
  goButton().click();
  check("a tap on the > takes it", input.value === "Em sửa kỹ năng code trước, hạ tầng để sau" && greyRest() === null);
  type("");
  check("a finished draft taken whole, then the box emptied: the turn's guess is back",
    input.placeholder === SUG && c.current() === SUG);
  type("Em sửa kỹ năng code trước, hạ tầng");
  check("and the finished draft is still on offer for what it starts", greyRest() === " để sau");
  type("ok");
  await pause();
  check("a second draft is asked", drafts.length === 1 && drafts[0].body.draft === "ok");
  drafts.shift().answer({ ok: true, text: "" });
  await tick(); await tick();
  await pause();
  check("no answer for a draft: it is not asked again", drafts.length === 0 && greyRest() === null);
  type("x");
  await pause();
  check("one letter is too little to finish", drafts.length === 0);
  type("ok\nthêm dòng");
  await pause();
  check("a text of several lines is not a draft to finish", drafts.length === 0);
  quiet = true;
  type("đang đọc chính tả");
  await pause();
  check("while the screen dictates nothing is asked", drafts.length === 0);
  quiet = false;
  sandbox.document.activeElement = null;
  type("ô không được chọn");
  await pause();
  check("a box that is not being typed in asks nothing", drafts.length === 0);
  sandbox.document.activeElement = input;
  type("con trỏ ở giữa");
  input.selectionStart = input.selectionEnd = 3;
  await pause();
  check("with the caret inside the text nothing is asked (the end is not what is being written)", drafts.length === 0);
  composing = true;
  type("đang gõ dở");
  await pause();
  check("mid IME composition the draft waits", drafts.length === 0);
  composing = false;
  await pause();
  check("and goes once the composition is over", drafts.length === 1 && drafts[0].body.draft === "đang gõ dở");
  drafts.shift().answer({ ok: true, text: " thôi", busy: false });
  await tick(); await tick();
  type("lần thứ tư");
  await pause();
  check("at most live.max requests per turn (3 here)", drafts.length === 0);

  // A send (clear) drops the answer on its way, and the next turn starts a fresh count.
  input.value = "";
  p = c.request(CHAT);
  await tick(); await tick();
  pending.shift()({ ok: true, text: "" });
  await p;
  type("gửi luôn");
  await pause();
  check("no suggestion for the turn: a draft is still finished", drafts.length === 1 && drafts[0].body.hint === "");
  c.clear();
  drafts.shift().answer({ ok: true, text: " cho anh" });
  await tick(); await tick();
  check("an answer arriving after a send is dropped", greyRest() === null && c.showing() === "");
  type("sau khi gửi");
  await pause();
  check("after a send nothing is asked until Javis answers again", drafts.length === 0);
  // Typed without marks: the server sends the whole sentence in its own spelling, and Tab takes that.
  input.value = "";
  p = c.request(CHAT);
  await tick(); await tick();
  pending.shift()({ ok: true, text: "" });
  await p;
  type("chi danh dau luat n");
  await pause();
  drafts.shift().answer({ ok: true, text: "ền thôi nhé", full: "Chỉ đánh dấu luật nền thôi nhé" });
  await tick(); await tick();
  check("the rest shows after the text as typed", greyRest() === "ền thôi nhé");
  c.onKeydown(Object.assign(tab(), { preventDefault() {} }));
  check("Tab takes the properly written sentence", input.value === "Chỉ đánh dấu luật nền thôi nhé");
  input.value = "";
  p = c.request(CHAT);
  await tick(); await tick();
  pending.shift()({ ok: true, text: "" });
  await p;
  type("ok  làm ");
  await pause();
  drafts.shift().answer({ ok: true, text: "theo đề xuất", full: "ok làm theo đề xuất" });
  await tick(); await tick();
  c.onKeydown(Object.assign(tab(), { preventDefault() {} }));
  check("a whole sentence that does not line up with the typed text is not used: the rest goes after what was typed",
    input.value === "ok  làm theo đề xuất");
  // The server was finishing another draft (busy): it cost nothing, the count is given back.
  input.value = "";
  p = c.request(CHAT);
  await tick(); await tick();
  pending.shift()({ ok: true, text: "", live: { wait_ms: WAIT, max: 1 } });
  await p;
  type("bận 1");
  await pause();
  drafts.shift().answer({ ok: true, text: "", busy: true });
  await tick(); await tick();
  type("bận 2");
  await pause();
  check("a busy answer does not use up the turn's count (live.max is 1 here)", drafts.length === 1);
  drafts.shift().answer({ ok: true, text: "" });
  await tick(); await tick();
  // The server says it cannot finish drafts (no key, no background brain): never asked.
  input.value = "";
  p = c.request(CHAT);
  await tick(); await tick();
  pending.shift()({ ok: true, text: SUG, live: null });
  await p;
  type("không có ai đoán");
  await pause();
  check("live off on the server: typing along still works, nothing is asked", drafts.length === 0);
  type("Em sửa");
  check("typing along needs no server", greyRest() === " kỹ năng nối hạ tầng luôn nhé");
  c.clear();
  check("clear takes the grey rest away", greyRest() === null);

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
  // Owner, 2026-11-13: on a phone "làm 1 mũi tên nhỏ theo kiểu > thôi, không cần cả nút", "đừng hiện cùng hàng với
  // voice và các nút hiện tại", "bôi đậm nút đấy lên một chút".
  const cssTab = fs.readFileSync(path.join(D, "style.css"), "utf8");
  check("the chip in the button row reads Tab and is for a computer only",
    SRC.includes('chip.textContent = "Tab";') && cssTab.includes("@media (pointer: coarse) { .sug-tab { display: none; } }"));
  check("main chat: the chip keeps its one place in the row (no second place for a touch screen)",
    !app.includes("pointer: coarse") || !/chipHost[\s\S]{0,300}pointer: coarse/.test(app));
  // Owner, 2026-11-13, later: "ở phiên bản máy tính ... không có mũi tên >". The > is for every screen.
  const go = cssTab.slice(cssTab.indexOf("\n.sug-go { display: inline-flex;"));
  check("the > shows on a computer too (no media query hides it), with no border and no background, and takes a click",
    !/\.sug-go \{[^}]*display: none/.test(cssTab) &&
    /^\n\.sug-go \{ display: inline-flex;[^}]*pointer-events: auto;[^}]*border: 0; background: none;/.test(go) &&
    SRC.includes('goEl.title = tw("sug.use");'));
  check("the > is darker than the grey text and drawn with a heavy stroke",
    /\.sug-go \{[^}]*color: var\(--text2\);/.test(go) && /stroke-width="3\.2"/.test(SRC) && SRC.includes('<path d="M9 5l7 7-7 7"/>'));
  check("the > is no taller than a line of text (the lines keep their height), with a little room for a mouse and more for a finger",
    /\.sug-go \{[^}]*width: 1em; height: 1em;/.test(go) && /\.sug-go::after \{ content: ""; position: absolute; inset: -4px -6px; \}/.test(go) &&
    go.includes("@media (pointer: coarse) { .sug-go::after { inset: -8px -10px; } }"));
  check("the > never wraps onto a line of its own", cssTab.includes(".sug-ghost-tail { white-space: nowrap; }"));
  check("the chip is not shown over the dictation bar", cssTab.includes(".hud-voice.dictating .sug-tab { display: none; }"));
  const kd = app.slice(app.indexOf('chatInput.addEventListener("keydown"'));
  check("main chat: Tab is checked before Enter sends", kd.indexOf("chatSuggest.onKeydown(e)") < kd.indexOf("enterSends"));
  const done = app.slice(app.indexOf('data.type === "turn_done"'));
  check("main chat: a suggestion is asked when a turn ends, not during a voice call",
    /chatSuggest\.request\(/.test(done.slice(0, 6000)) && done.slice(0, 6000).includes("!handsFreeActive()"));
  check("main chat: sending drops the suggestion",
    app.slice(app.indexOf("function sendMessage("), app.indexOf("function sendMessage(") + 300).includes("dropSuggest()"));
  check("main chat: typing shows or hides it", app.includes("chatSuggest.onInput()"));
  check("main chat: the grey rest may grow the box up to the screen's own limit, and stays out of dictation",
    /maxHeight: \(\) => chatInputCap\(\)/.test(app) && /quiet: \(\) => handsFreeActive\(\)/.test(app) &&
    app.includes("Math.min(chatInput.scrollHeight, chatInputCap())"));
  const inp = app.slice(app.indexOf('chatInput.addEventListener("input"'));
  check("main chat: the suggestion is told AFTER the box is sized to its text",
    inp.indexOf("chatInput.style.height = Math.min") < inp.indexOf("chatSuggest.onInput()"));
  check("Teams: the same limit and dictation rule", /maxHeight: function \(\) \{ return INPUT_MAX_PX; \}/.test(teams) &&
    /quiet: function \(\) \{ return !!\(S && S\.dictState && S\.dictState !== "idle"\); \}/.test(teams));
  check("Teams: the suggestion is told AFTER the box is sized to its text",
    /grow\(e\.target\);[\s\S]{0,120}teamSuggest\.onInput\(\)/.test(teams));
  const css = fs.readFileSync(path.join(D, "style.css"), "utf8");
  check("the grey rest is a layer that never takes a click, its typed part unseen",
    /\.sug-ghost \{[^}]*position: absolute;[^}]*pointer-events: none;/.test(css) &&
    /\.sug-ghost-typed \{ visibility: hidden; \}/.test(css));
  check("a suggestion in an empty box is drawn by the layer (it wraps), the box's own placeholder text unseen",
    css.includes("textarea.sug-ghosted::placeholder { color: transparent; }"));
  check("no timer runs while a suggestion just sits there", !/setInterval|requestAnimationFrame/.test(SRC));
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
