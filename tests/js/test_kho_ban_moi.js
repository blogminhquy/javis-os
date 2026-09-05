// Kho cai dat: phat hien va hien thi BAN MOI cua goi da cai.
//
//     node tests/js/test_kho_ban_moi.js
//
// Vi sao file nay ton tai
// -----------------------
// Nut "Co ban moi vX" da co tu 0.55.34 va no CHAY DUNG. Nhung phep so phien ban chi nam trong
// mot ham ve nut, nen no la thu duy nhat trong ca giao dien biet chuyen do: khong dem duoc,
// khong loc duoc, va khong thay duoc tu tab khac. Luoi loc theo `_kho.loai` va tab mac dinh la
// "Ket noi", nen mot goi Ky nang co ban moi thi khong co gi noi ra - phai tinh co bam dung tab
// moi thay. Chu repo bao lai dung nguyen van: "khong thay Javis co tinh nang cap nhat goi".
//
// Test nay GOI THAT `coBanMoi`, `nutThe`, `theKho` chu khong quet chuoi, cung ly do da viet ro
// trong test_kho_cai_dat.js: mot canary doc chu van xanh y nguyen khi phep so bi dao nguoc, va
// do la dung cai loi can bat nhat o day.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

const win = { ic: () => "<svg></svg>", Alpine: { store: () => ({ go() {} }) } };
const doc = {
  getElementById: () => null, querySelector: () => null, querySelectorAll: () => [],
  createElement: () => ({ style: {}, classList: { add() {}, remove() {} },
                          querySelectorAll: () => [], appendChild() {} }),
  body: { appendChild() {} },
};
const _alpineCu = globalThis.Alpine;
globalThis.Alpine = win.Alpine;
new Function("window", "document", "fetch",
  fs.readFileSync(path.join(ROOT, "dashboard", "packs.js"), "utf8"))(
  win, doc, () => Promise.resolve({}));
const P = win.JavisPacks || {};

check("packs.js phoi ra coBanMoi / nutThe / theKho",
  typeof P.coBanMoi === "function" && typeof P.nutThe === "function"
  && typeof P.theKho === "function");

const goi = (o) => Object.assign(
  { id: "javis.x", kind: "connector", name: { vi: "X" }, description: { vi: "mo ta" },
    tier: "data", verified: true, nguon: "kho", author: { name: "Javis" } }, o);

// ---- 1. Phep so: dung 4 tinh huong, khong phai 1 ----
check("da cai ban cu + kho co ban moi -> CO ban moi",
  P.coBanMoi(goi({ installed: true, installed_version: "1.0.0", version: "1.0.1" })) === true);
check("da cai dung ban kho dang co -> KHONG bao ban moi",
  P.coBanMoi(goi({ installed: true, installed_version: "1.0.1", version: "1.0.1" })) === false);
check("chua cai -> KHONG bao ban moi (no la nut Cai dat, khong phai Cap nhat)",
  P.coBanMoi(goi({ installed: false, installed_version: "", version: "1.0.1" })) === false);
// Goi tha tay vao thu muc khong co hang trong so nen khong co so hieu. Bao "co ban moi" cho no
// la day nguoi dung di cai de len mot thu ho tu dat vao.
check("da cai nhung khong biet dang chay ban nao -> KHONG doan bua",
  P.coBanMoi(goi({ installed: true, installed_version: "", version: "1.0.1" })) === false);

// Connector di kem app: `download.url` rong nen khong tai ve tu dau ca.
check("connector di kem app KHONG bao gio bao ban moi",
  P.coBanMoi(goi({ nguon: "app", installed: true, installed_version: "1.0.0",
                   version: "9.9.9" })) === false);

// ---- 2. Bi HA CAP cung phai keo lai duoc ----
// Kho la nguon su that ve ban dang phat hanh. Neu so kieu "lon hon" thi mot ban moi hong da
// bi rut ve se khoa nguoi dung o dung cai ban hong do.
check("kho rut ve ban cu hon -> VAN keo lai duoc",
  P.coBanMoi(goi({ installed: true, installed_version: "2.0.0", version: "1.9.9" })) === true);

// ---- 3. Nut phai doi theo ----
const nutMoi = P.nutThe(goi({ installed: true, installed_version: "1.0.0", version: "1.0.1" }));
check("nut hien so hieu MOI de biet se keo ve cai gi",
  nutMoi.nhan.indexOf("1.0.1") >= 0 && nutMoi.act === "cai");
const nutDu = P.nutThe(goi({ installed: true, installed_version: "1.0.1", version: "1.0.1" }));
check("dang o ban moi nhat -> nut ve lai la Go cai dat", nutDu.act === "go");

// ---- 4. The phai noi DU HAI SO ----
// Loi that truoc 0.55.42: dong meta lay `g.version` (so cua KHO), nen the cua goi dang chay
// 1.0.0 hien "v1.0.1" ngay tren dong "Da cai tren may" - noi voi nguoi dung rang ho dang chay
// 1.0.1, dung luc ho chay 1.0.0.
const theMoi = P.theKho(goi({ installed: true, installed_version: "1.0.0", version: "1.0.1" }));
check("the noi ro dang chay ban nao", theMoi.indexOf("Đang chạy v1.0.0") >= 0);
check("the noi ro kho co ban nao", theMoi.indexOf("kho có v1.0.1") >= 0);
check("the KHONG con hien tron mot so hieu cua kho nhu the do la ban dang chay",
  theMoi.indexOf("· v1.0.1 ·") < 0);

const theDu = P.theKho(goi({ installed: true, installed_version: "1.0.1", version: "1.0.1" }));
check("da cai va dang moi nhat -> the noi dung the",
  theDu.indexOf("Đã cài v1.0.1") >= 0 && theDu.indexOf("mới nhất") >= 0);

const theChua = P.theKho(goi({ installed: false, version: "1.0.1" }));
check("goi chua cai van hien so hieu cua kho o dong meta",
  theChua.indexOf("v1.0.1") >= 0 && theChua.indexOf("Đã cài") < 0);

// ---- 5. Kham pha xuyen tab: doi mat that su cua tinh nang nay ----
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "packs.js"), "utf8");
check("dem ban moi tren MOI loai, khong chi tab dang mo",
  /const capNhat = ds\.filter\(coBanMoi\)/.test(SRC));
check("co bang bao ban moi dat NGOAI tabs", /kho-bao-moi/.test(SRC));
check("chip tren bang nhay sang dung tab va loc san",
  /data-kho-moi/.test(SRC) && /_kho\.nhom = "Có bản mới"/.test(SRC));
check("tab mang huy hieu so ban moi cua rieng no", /kho-dem moi/.test(SRC));
check("cot ben trai co hang loc 'Co ban moi'", /hangNhom\("Có bản mới"/.test(SRC));
check("danh muc qua cu thi tu lay lai mot lan o nen",
  /CU_QUA/.test(SRC) && /packs\/store\?refresh=1/.test(SRC));
check("va noi ra danh muc lay luc nao", /Danh mục lúc/.test(SRC));

// CSS phai co that, neu khong thi bang bao va huy hieu deu la chu tran khong ai thay.
const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
for (const lop of [".kho-bao-moi", ".kho-chip", ".kho-daicai.moi", ".kho-dem.moi"]) {
  check("console.css co kieu cho " + lop, CSS.indexOf(lop) >= 0);
}

globalThis.Alpine = _alpineCu;

console.log("");
if (fails.length) {
  console.log(`FAIL - test_kho_ban_moi: ${fails.length} loi: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("OK - test_kho_ban_moi: tat ca pass");
