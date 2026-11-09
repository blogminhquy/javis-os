// Test logic dọn folder ngoài (📁) của brains-ui.js - mock DOM tối thiểu + fetch + localStorage.
// Chạy: node dashboard/test_brains_ui.mjs
// Kịch bản = đúng bug thật: 📁 "brain" (đã xoá khỏi đĩa) + 📁 trùng path 1 não thật phải bị dọn,
// 📁 folder ngoài hợp lệ (D:\My Bullet Journal) phải GIỮ.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = fs.readFileSync(path.join(__dirname, "../../dashboard/brains-ui.js"), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

const REAL = [
  { name: "Brain Default", path: "D:\\Project\\Javis-OS\\brains\\Brain Default", notes: 90, is_default: true },
  { name: "My Bullet Journal", path: "D:\\Project\\Javis-OS\\brains\\My Bullet Journal", notes: 576 },
  { name: "Ngọc Thu Phạm", path: "D:\\Project\\Javis-OS\\brains\\Ngọc Thu Phạm", notes: 111 },
];
// Server: path nào còn là thư mục.
const EXISTS = {
  "D:\\Project\\Javis-OS\\brain": { exists: false, is_dir: false },          // 📁 brain: đã xoá
  "D:\\My Bullet Journal": { exists: true, is_dir: true },                    // 📁 ngoài hợp lệ
};

// ---- Mock Option ----
class Opt {
  constructor(value = "", text = "") { this.value = value; this.textContent = text; this.dataset = {}; this._parent = null; }
  get nextSibling() { const a = this._parent?._kids; if (!a) return null; const i = a.indexOf(this); return i >= 0 && i + 1 < a.length ? a[i + 1] : null; }
  remove() { const a = this._parent?._kids; if (a) { const i = a.indexOf(this); if (i >= 0) a.splice(i, 1); } this._parent = null; }
}
class Frag { constructor() { this._kids = []; } appendChild(o) { this._kids.push(o); return o; } }

// ---- Mock Select ----
class Select {
  constructor() { this._kids = []; this._value = "brain"; }
  _all() { return this._kids; }
  _match(o, sel) {
    if (sel === "option[data-brain]") return o.dataset.brain !== undefined;
    if (sel === "option[data-custom]") return o.dataset.custom !== undefined;
    if (sel === 'option[value="brain"]') return o.value === "brain";
    // Thư mục ngoài giờ nằm trong <optgroup> (thẻ <option> không nhận được icon
    // nên dùng nhóm để phân biệt). Mock này chỉ dựng Opt phẳng, không dựng
    // optgroup, nên đúng là không khớp gì - trả false thay vì ném lỗi.
    if (sel === "optgroup") return false;
    throw new Error("selector chưa mock: " + sel);
  }
  querySelectorAll(sel) { return this._kids.filter((o) => this._match(o, sel)); }
  querySelector(sel) { return this._kids.find((o) => this._match(o, sel)) || null; }
  appendChild(node) {
    const kids = node instanceof Frag ? node._kids : [node];
    for (const k of kids) { k._parent = this; this._kids.push(k); }
    if (node instanceof Frag) node._kids = [];
    return node;
  }
  insertBefore(node, ref) {
    const kids = node instanceof Frag ? node._kids : [node];
    let idx = ref ? this._kids.indexOf(ref) : -1;
    if (idx < 0) idx = this._kids.length;
    for (const k of kids) k._parent = this;
    this._kids.splice(idx, 0, ...kids);
    if (node instanceof Frag) node._kids = [];
    return node;
  }
  get options() { return this._kids; }
  get selectedIndex() { return this._kids.findIndex((o) => o.value === this._value); }
  get value() { return this._value; }
  set value(v) { this._value = v; }
  dispatchEvent() { return true; }
}

const sel = new Select();
// Trạng thái khởi đầu: default + 2 option 📁 (như app.js đã render từ localStorage).
const def = new Opt("brain", "🧠 Brain Default"); sel.appendChild(def);
const c1 = new Opt("path:D:\\Project\\Javis-OS\\brain", "📁 brain"); c1.dataset.custom = "1"; sel.appendChild(c1);
const c2 = new Opt("path:D:\\My Bullet Journal", "📁 My Bullet Journal"); c2.dataset.custom = "1"; sel.appendChild(c2);
const c3 = new Opt("path:D:\\Project\\Javis-OS\\brains\\My Bullet Journal", "📁 My Bullet Journal"); c3.dataset.custom = "1"; sel.appendChild(c3); // TRÙNG não thật

// localStorage khởi đầu (3 entry, có 1 trùng não thật)
const store = {
  "javis.brains": JSON.stringify([
    { name: "brain", path: "D:\\Project\\Javis-OS\\brain" },
    { name: "My Bullet Journal", path: "D:\\My Bullet Journal" },
    { name: "My Bullet Journal", path: "D:\\Project\\Javis-OS\\brains\\My Bullet Journal" },
  ]),
  "javis.graphSource": "brain",
};

// ---- Globals ----
const btns = {};
global.document = {
  getElementById: (id) => id === "graphSource" ? sel : (btns[id] || (btns[id] = { addEventListener() {} })),
  createElement: () => new Opt(),
  createDocumentFragment: () => new Frag(),
};
global.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
global.window = {};
global.Event = class { constructor(t) { this.type = t; } };
global.fetch = async (url) => {
  if (url === "/brains") return { json: async () => ({ dir: "D:\\...", brains: REAL }) };
  if (url.startsWith("/path/exists?path=")) {
    const p = decodeURIComponent(url.split("path=")[1]);
    const r = EXISTS[p] || { exists: false, is_dir: false };
    return { ok: true, json: async () => ({ path: p, ...r }) };
  }
  throw new Error("fetch chưa mock: " + url);
};

// ---- Nạp module (IIFE tự chạy loadBrains(null,true)) ----
eval(SRC);

// loadBrains async → chờ microtask lắng
await new Promise((r) => setTimeout(r, 50));

// ---- Assert ----
const customVals = sel.querySelectorAll("option[data-custom]").map((o) => o.value);
const brainNames = sel.querySelectorAll("option[data-brain]").map((o) => o.dataset.brainName);
const stored = JSON.parse(store["javis.brains"]);

check("📁 'brain' (đã xoá) bị gỡ khỏi menu", !customVals.includes("path:D:\\Project\\Javis-OS\\brain"));
check("📁 trùng não thật bị gỡ khỏi menu", !customVals.includes("path:D:\\Project\\Javis-OS\\brains\\My Bullet Journal"));
check("📁 folder ngoài hợp lệ được GIỮ", customVals.includes("path:D:\\My Bullet Journal"));
check("chỉ còn ĐÚNG 1 option 📁", customVals.length === 1);
check("localStorage còn ĐÚNG 1 entry", stored.length === 1 && stored[0].path === "D:\\My Bullet Journal");
check("🧠 não thật (không default) render đủ 2", brainNames.length === 2 && brainNames.includes("My Bullet Journal") && brainNames.includes("Ngọc Thu Phạm"));
check("option default cập nhật nhãn kèm note", def.textContent.includes("Brain Default") && def.textContent.includes("90"));

// ---- Test 2: fail-safe khi endpoint 404 (server chưa restart) → KHÔNG xoá gì ----
const sel2 = new Select();
sel2.appendChild(new Opt("brain", "🧠 Brain Default"));
const d1 = new Opt("path:D:\\mot\\folder", "📁 folder"); d1.dataset.custom = "1"; sel2.appendChild(d1);
const store2 = { "javis.brains": JSON.stringify([{ name: "folder", path: "D:\\mot\\folder" }]), "javis.graphSource": "brain" };
global.document.getElementById = (id) => id === "graphSource" ? sel2 : (btns[id] || (btns[id] = { addEventListener() {} }));
global.localStorage = { getItem: (k) => (k in store2 ? store2[k] : null), setItem: (k, v) => { store2[k] = String(v); } };
global.fetch = async (url) => {
  if (url === "/brains") return { json: async () => ({ brains: [REAL[0]] }) };
  if (url.startsWith("/path/exists")) return { ok: false, status: 404, json: async () => ({ error: "not found" }) };
  throw new Error("fetch chưa mock: " + url);
};
eval(SRC);
await new Promise((r) => setTimeout(r, 50));
const stored2 = JSON.parse(store2["javis.brains"]);
check("fail-safe: endpoint 404 → GIỮ nguyên entry (không xoá nhầm)", stored2.length === 1 && sel2.querySelectorAll("option[data-custom]").length === 1);

// ---- Test 3 (2026-11-09): make another brain the default. Someone looking at the old default keeps looking at it ----
// Before: Brain Default is the default ("brain") and is on screen. After POST /brains/default the server lists Shop as
// the default, so the "brain" entry now means Shop; the screen must move to the old default by its path, not silently
// show Shop under the same value.
const P_OLD = "D:\\j\\brains\\Brain Default", P_SHOP = "D:\\j\\brains\\Shop";
let lista = [
  { name: "Brain Default", path: P_OLD, notes: 3, is_default: true },
  { name: "Shop", path: P_SHOP, notes: 5, is_default: false },
];
const sel3 = new Select();
sel3.appendChild(new Opt("brain", "Brain Default"));
let changes3 = 0;
sel3.dispatchEvent = () => { changes3 += 1; return true; };
const store3 = { "javis.brains": "[]", "javis.graphSource": "brain" };
const posted = [];
global.document.getElementById = (id) => id === "graphSource" ? sel3 : (btns[id] || (btns[id] = { addEventListener() {} }));
global.localStorage = { getItem: (k) => (k in store3 ? store3[k] : null), setItem: (k, v) => { store3[k] = String(v); } };
global.FormData = class { constructor() { this.f = {}; } append(k, v) { this.f[k] = v; } };
global.window = { t: (k) => k };
global.fetch = async (url, opts) => {
  if (url === "/brains") return { json: async () => ({ brains: lista }) };
  if (url === "/brains/default") {
    posted.push(opts.body.f.brain);
    lista = [{ ...lista[0], is_default: false }, { ...lista[1], is_default: true }];
    return { json: async () => ({ ok: true, name: "Shop", label: "Shop", previous: "Brain Default" }) };
  }
  throw new Error("fetch chưa mock: " + url);
};
eval(SRC);
await new Promise((r) => setTimeout(r, 50));
check("set default: the old default carries its folder path", sel3.querySelector('option[value="brain"]').dataset.brainPath === P_OLD);
changes3 = 0;
const r3 = await global.window.JavisBrains.setDefault("path:" + P_SHOP);
check("set default: posts the chosen brain", r3.ok === true && posted[0] === "path:" + P_SHOP);
check("set default: the 'brain' entry now carries Shop", sel3.querySelector('option[value="brain"]').dataset.brainName === "Shop");
check("set default: the old default is listed by its path", sel3.options.some((o) => o.value === "path:" + P_OLD));
check("set default: the screen stays on the old default", sel3.value === "path:" + P_OLD && store3["javis.graphSource"] === "path:" + P_OLD);
check("set default: pages are told once", changes3 === 1);
check("set default: refuses an entry that is not a listed brain",
  (await global.window.JavisBrains.setDefault("brain")).ok === false && posted.length === 1);

console.log();
if (fails.length) { console.log(`${fails.length} FAIL: ${fails.join(", ")}`); process.exit(1); }
console.log("TẤT CẢ PASS");
