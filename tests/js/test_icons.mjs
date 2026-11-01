/* Test RUNTIME cua tang icon. Chay tay / CI:
       node tests/js/test_icons.mjs

   Test Python (tests/python/test_icons.py) chi doc MA NGUON - no khong chung
   minh duoc ic() thuc su tra ve SVG dung. File nay nap that hai file vendor +
   icons.js vao mot DOM toi thieu roi goi ham that.

   Diem quan trong nhat o duoi: Icons.msg() phai escape chuoi tu server. Toan bo
   viec di tru nay bien textContent thanh innerHTML o rat nhieu cho, nen day la
   rao chan XSS duy nhat. Neu test do vo thi dung sua test, sua icons.js. */
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}
const has = (h, s) => String(h).indexOf(s) !== -1;

// --- DOM toi thieu: du cho icons.js chay, khong keo ca jsdom vao. ------------
function fakeEl(tag) {
  const el = {
    tagName: String(tag).toUpperCase(),
    id: "",
    _html: "",
    _attrs: {},
    children: [],
    parentNode: null,
    setAttribute(k, v) { this._attrs[k] = String(v); },
    getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; },
    get innerHTML() { return this._html; },
    // Chi can du de render() lay ra "phan tu dau tien": bam lay the <svg ...>
    set innerHTML(v) {
      this._html = v;
      const m = /^\s*(<svg[\s\S]*<\/svg>)\s*$/.exec(v);
      this.children = m ? [{ tagName: "SVG", outerHTML: m[1], id: "" }] : [];
    },
    get firstElementChild() { return this.children[0] || null; },
  };
  return el;
}

const scope = { nodes: [] };
const doc = {
  readyState: "complete",
  createElement: fakeEl,
  querySelectorAll: (sel) => (sel === "[data-ic]" ? scope.nodes : []),
  addEventListener: () => {},
};
const sandbox = { window: {}, document: doc, console };
sandbox.window.document = doc;
vm.createContext(sandbox);
for (const f of ["dashboard/vendor/lucide-icons.js", "dashboard/icons.js"]) {
  vm.runInContext(fs.readFileSync(path.join(ROOT, f), "utf8"), sandbox, { filename: f });
}
const { ic, Icons } = sandbox.window;

// --- 1. Bo icon nap duoc -----------------------------------------------------
check("vendor nap duoc, co icon", Icons.count() > 100);
check("ic() phoi ra toan cuc", typeof ic === "function");

// --- 2. ic() dung khuon SVG --------------------------------------------------
const svg = ic("save");
check("ic() tra ve the svg", /^<svg /.test(svg) && svg.endsWith("</svg>"));
check("ic() dung currentColor de tu doi mau theo tong", has(svg, 'stroke="currentColor"'));
check("ic() khong to dac mac dinh", has(svg, 'fill="none"'));
check("ic() co lop .ic de CSS bat duoc", has(svg, 'class="ic"'));
check("ic() co cỡ 1em de co theo cỡ chữ", has(svg, 'width="1em"') && has(svg, 'height="1em"'));
check("ic() an khoi trinh doc man hinh khi khong co title", has(svg, 'aria-hidden="true"'));
check("ic() co ruot that (khong phai the rong)", svg.length > 60);

// --- 3. Tuy chon -------------------------------------------------------------
check("opts.cls them class", has(ic("x", { cls: "ic-err" }), 'class="ic ic-err"'));
check("opts.size dat co cu the", has(ic("x", { size: "18px" }), "width:18px"));
const titled = ic("x", { title: "Đóng" });
check("opts.title tao the <title>", has(titled, "<title>Đóng</title>"));
check("opts.title chuyen sang role=img", has(titled, 'role="img"'));
check("co title thi KHONG con aria-hidden", !has(titled, "aria-hidden"));

// --- 4. Cache khong lam lan cac bien the -------------------------------------
check("cache khong tron cls voi ban goc",
  ic("save") !== ic("save", { cls: "ic-lg" }) && ic("save") === ic("save"));

// --- 5. Icon thieu thi LO RA, khong im lang ----------------------------------
const warned = [];
const realWarn = console.warn;
console.warn = (...a) => warned.push(a.join(" "));
const bogus = ic("khong-he-ton-tai-dau");
console.warn = realWarn;
check("icon thieu van tra ve svg thay cho (khong ra chuoi rong)", /^<svg /.test(bogus));
check("icon thieu thi canh bao ra console", warned.length === 1);
check("canh bao chi ra dung cach sua", has(warned[0] || "", "gen_icons.py"));
check("Icons.missing() ghi lai ten sai", Icons.missing().includes("khong-he-ton-tai-dau"));
check("Icons.has() phan biet dung", Icons.has("save") && !Icons.has("khong-he-ton-tai-dau"));

// --- 6. RAO CHAN XSS: Icons.msg() phai escape chuoi tu server ---------------
// Day la cho de vo nguy hiem nhat cua ca dot di tru.
const evil = '<img src=x onerror="alert(1)">';
const m = Icons.msg("triangle-alert", evil);
check("msg(): khong de the HTML tho chay", !has(m, "<img src=x"));
check("msg(): dau nhon bi escape", has(m, "&lt;img"));
check("msg(): dau nhay bi escape", !has(m, 'onerror="alert(1)"'));
check("msg(): van co icon o dau", /^<svg /.test(m));
check("msg(): giu lai chu doc duoc", has(Icons.msg("check", "Đã lưu"), "Đã lưu"));
check("msg(): chuoi rong/null khong vo", typeof Icons.msg("check", null) === "string");

// Hai loi tat warn/ok phai escape y het msg() - chung la duong di cua ~40 cho.
check("warn(): escape chuoi tu server", !has(Icons.warn(evil), "<img src=x"));
check("warn(): to mau canh bao", has(Icons.warn("x"), "ic-warn"));
check("ok(): escape chuoi tu server", !has(Icons.ok(evil), "<img src=x"));
check("ok(): to mau thanh cong", has(Icons.ok("x"), "ic-ok"));

// 0.438.2 (owner, 01/11/2026): the Meta mark is the official logo file, not a hand-drawn stroke, and the file ships.
check("kenh(meta): the official logo file inside the svg box", has(Icons.kenh("meta"), 'href="/static/logos/meta.png"') && !has(Icons.kenh("meta"), "stroke="));
check("kenh(meta): the logo file is in the repo", fs.existsSync(path.join(ROOT, "dashboard/logos/meta.png")));

// --- 7. render() thay <i data-ic> trong HTML tinh ---------------------------
const holder = fakeEl("div");
const target = fakeEl("i");
target.setAttribute("data-ic", "search");
target.setAttribute("class", "vs-ico");
target.parentNode = {
  replaced: null,
  replaceChild(nw) { this.replaced = nw; },
};
scope.nodes = [target];
Icons.render(doc);
const out = target.parentNode.replaced;
check("render() thay the <i> bang svg that", out && out.tagName === "SVG");
check("render() giu lai class co san de CSS cu con an",
  out && has(out.outerHTML, "vs-ico"));
check("render() bo dung icon duoc yeu cau", out && out.outerHTML.length > 60);

if (fails.length) {
  console.log(`\nFAIL - test_icons.mjs: ${fails.length} loi`);
  process.exit(1);
}
console.log("\nOK - test_icons.mjs: tat ca pass");
