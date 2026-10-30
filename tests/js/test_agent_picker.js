// Searchable agent picker (dashboard/agent-picker.js). Owner, 25/10/2026: the bot form's agent list had no search
// and every option was "name - truncated role". Runs the pure helpers in a vm, then enhance() against a tiny fake DOM
// to prove the native <select> stays in the DOM as the source of truth.
//
//     node tests/js/test_agent_picker.js
const fs = require("fs");
const { napTruoc, coNap } = require("./_thu_tu_nap");   // load order that understands lazy groups (0.417.0)
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "agent-picker.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "style.css"), "utf8");
const INDEX = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");
const CHATBOTS = fs.readFileSync(path.join(ROOT, "dashboard", "chatbots.js"), "utf8");
const STUDIO = fs.readFileSync(path.join(ROOT, "dashboard", "studio.js"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  " + JSON.stringify(extra)));
  if (!cond) fails++;
}

// ---------------------------------------------------------------- a very small DOM, just what enhance() touches
class FakeClassList {
  constructor(el) { this.el = el; }
  _get() { return (this.el.className || "").split(/\s+/).filter(Boolean); }
  add(c) { const l = this._get(); if (!l.includes(c)) l.push(c); this.el.className = l.join(" "); }
  remove(c) { this.el.className = this._get().filter((x) => x !== c).join(" "); }
  contains(c) { return this._get().includes(c); }
  toggle(c, on) { if (on === undefined ? !this.contains(c) : on) this.add(c); else this.remove(c); }
}
class FakeEl {
  constructor(tag) {
    this.tagName = tag.toUpperCase(); this.children = []; this.parentNode = null; this.attrs = {};
    this.className = ""; this.classList = new FakeClassList(this); this.listeners = {}; this.innerHTML = "";
    this.dataset = {}; this.hidden = false; this.id = "";
  }
  appendChild(c) { return this.insertBefore(c, null); }
  insertBefore(c, ref) {
    if (c.parentNode) c.parentNode.removeChild(c);
    const i = ref ? this.children.indexOf(ref) : -1;
    if (i < 0) this.children.push(c); else this.children.splice(i, 0, c);
    c.parentNode = this; return c;
  }
  removeChild(c) { this.children = this.children.filter((x) => x !== c); c.parentNode = null; return c; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === "id") this.id = String(v); }
  getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  dispatchEvent(ev) {
    let n = this;
    while (n) { (n.listeners[ev.type] || []).forEach((fn) => fn.call(n, ev)); if (!ev.bubbles) break; n = n.parentNode; }
    return true;
  }
  contains(x) { while (x) { if (x === this) return true; x = x.parentNode; } return false; }
}
function fakeSelect(agents, value) {
  const sel = new FakeEl("select");
  sel.options = agents.map((a) => ({ value: a.slug, textContent: a.name + " - " + a.role.slice(0, 20),
    dataset: { name: a.name, desc: a.role }, disabled: false }));
  sel._value = value;
  Object.defineProperty(sel, "value", { get() { return this._value; }, set(v) { this._value = String(v); } });
  return sel;
}

const doc = {
  body: new FakeEl("body"),
  createElement: (t) => new FakeEl(t),
  querySelector: () => null,
};
const ctx = {
  window: { t: (k) => k, ic: (n) => "<i " + n + ">", addEventListener() {}, removeEventListener() {},
    matchMedia: () => ({ matches: false }) },
  document: doc,
  Event,
};
vm.createContext(ctx);
vm.runInContext(SRC, ctx);
const AP = ctx.window.JavisAgentPicker;
check("module exposes JavisAgentPicker.enhance", AP && typeof AP.enhance === "function");

const AGENTS = [
  { slug: "dao-dien-anh-quote", name: "Đạo diễn ảnh quote Ngọc Thu",
    role: "Tạo ảnh quote chiêm nghưỡm theo dấu ấn thương hiệu" },
  { slug: "email-writer", name: "Email Writer", role: "Drafts customer emails in the brand voice" },
  { slug: "ke-toan", name: "Kế toán", role: "Đối soát doanh thu cuối tháng" },
  { slug: "sales-bot", name: "Sales Bot", role: "Answers price questions and writes the email follow-up" },
];

// ---------------------------------------------------------------- fold + filter
check("fold strips Vietnamese diacritics and maps d-with-stroke",
  AP.fold("ĐẠO DiỄn") === "dao dien", AP.fold("ĐẠO DiỄn"));
const sel = fakeSelect(AGENTS, "email-writer");
const items = AP.itemsFrom(sel);
check("items read the full name and description from data-name/data-desc",
  items[0].name === AGENTS[0].name && items[0].desc === AGENTS[0].role && items[0].value === "dao-dien-anh-quote");
const names = (list) => list.map((x) => x.value);
check("empty query keeps every agent in order", names(AP.filterItems(items, "  ")).join() === names(items).join());
check("filter by name", names(AP.filterItems(items, "WRITER")).join() === "email-writer");
check("filter by description", names(AP.filterItems(items, "doanh thu")).join() === "ke-toan");
check("diacritic-insensitive: 'dao dien' finds the Đạo diễn agent",
  names(AP.filterItems(items, "dao dien")).join() === "dao-dien-anh-quote");
check("accented query also matches", names(AP.filterItems(items, "kế TOÁN")).join() === "ke-toan");
check("filter by slug", names(AP.filterItems(items, "sales-bot")).join() === "sales-bot");
check("name matches rank before description-only matches",
  names(AP.filterItems(items, "email")).join() === "email-writer,sales-bot", names(AP.filterItems(items, "email")));
check("no match gives an empty list", AP.filterItems(items, "zzz").length === 0);

// ---------------------------------------------------------------- rows
const html = AP.rowsHtml(items, "email-writer", 0, "apx");
check("one row per agent with listbox option semantics",
  (html.match(/role="option"/g) || []).length === 4 && html.includes('id="apx-3"'));
check("the selected row is marked and checked",
  /class="ap-row is-sel"[^>]*aria-selected="true"/.test(html) && html.includes("<i check>"));
check("the active row is marked", /class="ap-row is-active"[^>]*id="apx-0"/.test(html));
check("row shows the name and the full description",
  html.includes('class="ap-row-name">Email Writer<') && html.includes(AGENTS[0].role));
check("rows escape HTML", AP.rowsHtml([{ value: "x", name: "<b>", desc: "\"q\"" }], "", -1, "a").includes("&lt;b&gt;"));

// ---------------------------------------------------------------- enhance + choose against the fake DOM
const parent = new FakeEl("div");
const sibling = new FakeEl("button");
parent.appendChild(sel); parent.appendChild(sibling);
let changes = 0, lastVal = "";
sel.addEventListener("change", function () { changes++; lastVal = this.value; });
let bubbled = 0;
parent.addEventListener("change", () => { bubbled++; });
const p = AP.enhance(sel, { title: "Pick" });
check("enhance returns a picker", !!p && !!p.btn);
check("the select stays in the DOM, inside the picker wrapper", sel.parentNode === p.wrap && p.wrap.parentNode === parent);
check("the wrapper takes the select's place (before the + New Agent button)",
  parent.children[0] === p.wrap && parent.children[1] === sibling);
check("the native select is hidden", sel.hidden === true && sel.classList.contains("ap-native"));
check("the button shows the chosen agent's name and description",
  p.btn.innerHTML.includes("Email Writer") && p.btn.innerHTML.includes("brand voice"));
check("enhancing twice reuses the same picker", AP.enhance(sel) === p && parent.children.length === 2);

check("choose() updates the hidden select value", AP.choose(sel, "ke-toan") === true && sel.value === "ke-toan");
check("choose() fires change on the select and it bubbles", changes === 1 && lastVal === "ke-toan" && bubbled === 1);
check("the button follows the change", p.btn.innerHTML.includes(AGENTS[2].name));
check("choosing the current value fires nothing", AP.choose(sel, "ke-toan") === false && changes === 1);

// ---------------------------------------------------------------- wiring, styles, strings
check("index.html loads agent-picker.js before studio.js and chatbots.js",
  napTruoc("agent-picker.js", ["studio.js", "chatbots.js"], INDEX));
check("the bot form enhances #cbAgent and passes the full role",
  CHATBOTS.includes('JavisAgentPicker.enhance(box.querySelector("#cbAgent")') && CHATBOTS.includes("data-desc="));
check("workflow steps enhance both agent selects",
  STUDIO.includes('enhance(row.querySelector(".st-agent")') && STUDIO.includes('enhance(row.querySelector(".st-verify-agent")'));
// Only the picker's own rules (selectors with .ap-): slicing to the end of the file also measured every block
// written after it, such as the GitHub picker (0.368.0), which follows its own type sizes.
const apCss = (CSS.slice(CSS.indexOf(".ap-native")).match(/[^{}]*\{[^}]*\}/g) || [])
  .filter((rule) => /\.ap-/.test(rule.split("{")[0])).join("\n");
const sizes = (apCss.match(/font-size:\s*([\d.]+)px/g) || []).map((s) => parseFloat(s.replace(/[^\d.]/g, "")));
check("every picker text is at least 16px", sizes.length > 0 && sizes.every((n) => n >= 16), sizes);
check("phone layout is a bottom sheet with tall touch rows",
  /\.ap-layer\.is-phone \.ap-pop \{[^}]*bottom: 0/.test(CSS) && /\.ap-layer\.is-phone \.ap-row \{ min-height: 56px/.test(CSS));
check("descriptions clamp to two lines", /\.ap-row-desc \{[^}]*-webkit-line-clamp: 2/.test(CSS));
check("no em dash or en dash in the module or this test",
  !/[\u2013\u2014]/.test(SRC) && !/[\u2013\u2014]/.test(fs.readFileSync(__filename, "utf8")));
for (const k of ["ap.title", "ap.title_step", "ap.title_verify", "ap.search_ph", "ap.empty", "ap.close", "ap.none"])
  check("i18n key in vi and en: " + k, !!VI[k] && !!EN[k] && VI[k] !== EN[k]);
check("the empty message keeps the {q} slot in both languages", VI["ap.empty"].includes("{q}") && EN["ap.empty"].includes("{q}"));

if (fails) { console.log(fails + " FAIL"); process.exit(1); }
console.log("all ok");
