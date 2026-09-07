// Kho cai dat: O TIM phai go duoc lien mach, khong phai moi lan mot chu cai.
//
//     node tests/js/test_kho_o_tim.js
//
// Vi sao file nay ton tai
// -----------------------
// Chu repo bao lai (2026-09-07): "phan store tim kiem chi viet duoc 1 chu cai 1 lan". Nguyen
// nhan: moi nhip `oninput` goi `veLuoi`, ma `veLuoi` thay sach `host.innerHTML` - o dang go bi
// vut khoi trang va o MOI thay cho no. Doan cu co goi `o.focus()`, nhung `o` la o CU da roi
// khoi trang nen focus vao no khong lam gi ca: con tro roi ve body, phai bam chuot lai moi go
// duoc chu thu hai.
//
// Test nay GO THAT: dung mot DOM gia du de `veKho` chay het, roi ban `oninput` hai lan lien
// tiep nhu nguoi dung go "cl". Neu con tro khong duoc tra lai o moi, nhip thu hai khong con o
// nao dang focus de go vao - va do la dung cai loi can bat.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- DOM gia toi thieu ----
// Chi mo phong dung nhung gi tang kho dung toi: `innerHTML` (dat vao thi o #pkQ cu chet, o moi
// sinh ra dung nhu trinh duyet lam), `getElementById`, va `activeElement` di theo `focus()`.
const doc = {
  activeElement: null,
  getElementById: (id) => doc._nut[id] || null,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: () => ({ style: {}, classList: { add() {}, remove() {} },
                          querySelectorAll: () => [], appendChild() {} }),
  body: { appendChild() {} },
  _nut: {},
};

function oMoi(html) {
  // Doc lai `value=` ma tang kho vua ve ra, y het trinh duyet dung o tu the HTML.
  const m = html.match(/id="pkQ"[^>]*value="([^"]*)"/);
  if (!m) return null;
  const o = {
    id: "pkQ",
    value: m[1].replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">"),
    selectionStart: null, selectionEnd: null,
    soLanFocus: 0,
    focus() { this.soLanFocus++; doc.activeElement = this; },
    setSelectionRange(a, b) { this.selectionStart = a; this.selectionEnd = b; },
  };
  return o;
}

const host = {
  _html: "",
  get innerHTML() { return this._html; },
  set innerHTML(v) {
    this._html = v;
    const o = oMoi(v);
    doc._nut.pkQ = o;                 // o cu vut di, o moi thay cho - dung nhu innerHTML that
    doc._nut.pkLamMoi = { onclick: null };
    doc._nut.pkChon2 = { onclick: null };
    host._oHienTai = o;
  },
  querySelector: (sel) => (sel === "#pkQ" ? doc._nut.pkQ : null),
  querySelectorAll: () => [],
  _oHienTai: null,
};

const win = { ic: () => "<svg></svg>", Alpine: { store: () => ({ go() {} }) } };
const goi = (id, ten, mo) => ({
  id: id, kind: "connector", name: { vi: ten }, description: { vi: mo },
  tier: "data", verified: true, nguon: "kho", author: { name: "Javis" },
  version: "1.0.0", installed: false, download: { url: "https://x/y.zip", sha256: "a" },
  nhom: "Ban hang",
});
const DANH_MUC = {
  ok: true, fetched_at: Math.floor(Date.now() / 1000),
  packs: [
    goi("javis.pancake-pos", "Pancake POS", "Don hang, doanh thu"),
    goi("javis.shopify", "Shopify", "Tra cuu san pham"),
    goi("javis.webcake", "Webcake", "Dung trang ban hang"),
  ],
};

const _alpineCu = globalThis.Alpine;
globalThis.Alpine = win.Alpine;
new Function("window", "document", "fetch",
  fs.readFileSync(path.join(ROOT, "dashboard", "packs.js"), "utf8"))(
  win, doc, () => Promise.resolve({ json: () => Promise.resolve(DANH_MUC) }));
const P = win.JavisPacks || {};

check("packs.js phoi ra veKho / ghiConTro / traConTro",
  typeof P.veKho === "function" && typeof P.ghiConTro === "function"
  && typeof P.traConTro === "function");

// ---- 1. Cap ghi/tra con tro, tach rieng ----
doc._nut.pkQ = null;
check("khong co o tim thi ghiConTro tra ve rong", P.ghiConTro(host) === null);

const oA = { id: "pkQ", value: "c", selectionStart: 1, selectionEnd: 1, soLanFocus: 0,
             focus() { this.soLanFocus++; }, setSelectionRange(a, b) {
               this.selectionStart = a; this.selectionEnd = b; } };
doc._nut.pkQ = oA;
doc.activeElement = null;
check("o tim co nhung KHONG dang go thi khong ghi gi", P.ghiConTro(host) === null);

doc.activeElement = oA;
const nho = P.ghiConTro(host);
check("dang go thi ghi lai dung vi tri con tro",
  !!nho && nho.dau === 1 && nho.cuoi === 1 && nho.cu === oA);

// Ve lai: o A chet, o B thay cho.
const oB = { id: "pkQ", value: "c", selectionStart: null, selectionEnd: null, soLanFocus: 0,
             focus() { this.soLanFocus++; }, setSelectionRange(a, b) {
               this.selectionStart = a; this.selectionEnd = b; } };
doc._nut.pkQ = oB;
P.traConTro(host, nho);
check("tra con tro cho o MOI chu khong phai o cu", oB.soLanFocus === 1 && oA.soLanFocus === 0);
check("con tro ve dung cho no dang dung, khong nhay xuong cuoi",
  oB.selectionStart === 1 && oB.selectionEnd === 1);

// Go chen vao GIUA chuoi: con tro phai o lai giua.
doc.activeElement = oB; oB.value = "cake"; oB.selectionStart = 2; oB.selectionEnd = 2;
const nho2 = P.ghiConTro(host);
const oC = { id: "pkQ", value: "cake", selectionStart: null, selectionEnd: null, soLanFocus: 0,
             focus() { this.soLanFocus++; }, setSelectionRange(a, b) {
               this.selectionStart = a; this.selectionEnd = b; } };
doc._nut.pkQ = oC;
P.traConTro(host, nho2);
check("go chen vao giua chuoi thi con tro o lai giua",
  oC.selectionStart === 2 && oC.selectionEnd === 2);

// ---- 2. Go THAT hai chu lien tiep qua duong ve lai ----
(async () => {
  await P.veKho({ querySelector: () => null, querySelectorAll: () => [] }, host, false, "connector");

  const o1 = doc._nut.pkQ;
  check("ve xong kho thi co o tim va no rong", !!o1 && o1.value === "");
  check("chua go thi luoi con du 3 muc", (host.innerHTML.match(/data-kho-act/g) || []).length >= 3);

  // Nhip 1: nguoi dung bam vao o roi go "c".
  doc.activeElement = o1;
  o1.value = "c"; o1.selectionStart = 1; o1.selectionEnd = 1;
  o1.oninput({ isComposing: false });

  const o2 = doc._nut.pkQ;
  check("go chu thu nhat thi o bi thay moi (luoi ve lai)", o2 !== o1);
  check("o moi giu nguyen chu vua go", o2 && o2.value === "c");
  // Day la cai lam cho "chi go duoc 1 chu cai 1 lan": neu con tro khong theo sang o moi thi
  // khong con o nao nhan phim, nguoi dung phai bam chuot lai.
  check("con tro CHUYEN sang o moi, khong roi ve body", doc.activeElement === o2);
  check("con tro dung o cuoi chu vua go", o2 && o2.selectionStart === 1);

  // Nhip 2: go tiep chu thu hai NGAY, khong bam chuot lai.
  o2.value = "cl"; o2.selectionStart = 2; o2.selectionEnd = 2;
  o2.oninput({ isComposing: false });

  const o3 = doc._nut.pkQ;
  check("go duoc chu thu hai lien mach", o3 && o3.value === "cl" && o3 !== o2);
  check("con tro van con trong o sau chu thu hai", doc.activeElement === o3);
  check("loc that su chay: 'cl' khong khop muc nao",
    host.innerHTML.indexOf("Khong co muc nao khop") !== -1
    || host.innerHTML.indexOf("Không có mục nào khớp") !== -1);

  // ---- 3. Bo go tieng Viet: dang dung chu thi DUNG ve lai ----
  // Gboard telex / bo go san cua macOS dung mot chu qua nhieu nhip `input` co `isComposing`.
  // Ve lai giua chung la o dang dung chu bi vut di, dau thanh mat theo.
  o3.value = "cla"; o3.selectionStart = 3;
  o3.oninput({ isComposing: true });
  check("dang dung chu (IME) thi KHONG ve lai", doc._nut.pkQ === o3);
  o3.oncompositionend();
  check("bo go chot chu xong moi loc", doc._nut.pkQ !== o3 && doc._nut.pkQ.value === "cla");

  if (_alpineCu === undefined) delete globalThis.Alpine; else globalThis.Alpine = _alpineCu;
  console.log(fails.length ? "\nFAIL: " + fails.join(" | ") : "\nTat ca xanh.");
  process.exit(fails.length ? 1 : 0);
})();
