// Kho cai dat: nap that packs.js roi GOI that ham cua no.
//
//     node tests/js/test_kho_cai_dat.js
//
// Vi sao file nay ton tai, va vi sao no khac moi test JS con lai trong thu muc nay:
//
// Moi test JS o day deu la canary quet VAN BAN nguon bang regex. Kieu do bat duoc "ai do xoa
// mat co che X", nhung MU hoan toan truoc loi thuc thi. Da tra gia that o 0.55.27: bien
// `_loaiCho` duoc dung o hai cho nhung khong bao gio khai bao. `node --check` xanh (dung cu
// phap), canary xanh (chuoi van con do), bo test Python xanh, CI xanh - va nut "Kho cai dat"
// nem ReferenceError ngay lan bam dau tien. Chi khi mo trinh duyet ra bam moi thay.
//
// Nen test nay NAP module va GOI ham, chu khong doc chuoi. Khong co jsdom trong repo (khong
// co package.json, khong co node_modules) nen DOM la ban gia toi thieu - du de module chay
// het phan dinh nghia va du de goi cac ham da phoi ra.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- DOM gia toi thieu ----
function moiTruong() {
  const daGo = [];
  const win = {
    ic: () => "",
    Alpine: { store: () => ({ go: (id) => daGo.push(id) }) },
  };
  const doc = {
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: () => ({ style: {}, classList: { add() {}, remove() {} },
                            querySelectorAll: () => [], appendChild() {} }),
    body: { appendChild() {} },
  };
  return { win, doc, daGo };
}

const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "packs.js"), "utf8");
const { win, doc, daGo } = moiTruong();

// Trong trinh duyet, `window.Alpine` VA `Alpine` la mot. Ma nguon o day (va ca console.js)
// viet theo doi do: `window.Alpine && Alpine.store(...)`. Hop cat phai dung mo hinh do, neu
// khong thi test do vi mot the gioi khong ton tai - va do gia con te hon xanh gia, no day
// nguoi ta di sua ma dang chay dung.
const _alpineCu = globalThis.Alpine;
globalThis.Alpine = win.Alpine;

let loiNap = null;
try {
  new Function("window", "document", "fetch", SRC)(win, doc, () => Promise.resolve({}));
} catch (e) {
  loiNap = e;
}
check("packs.js nap duoc, khong nem loi luc dinh nghia", !loiNap);
if (loiNap) console.log("     ->", loiNap.message);

const P = win.JavisPacks || {};
check("phoi ra render / moKho / LOAI",
  typeof P.render === "function" && typeof P.moKho === "function" && !!P.LOAI);

// Day la loi that da xay ra: moKho nem ReferenceError vi mot bien chua khai bao.
let loiMo = null;
try { P.moKho("skill"); } catch (e) { loiMo = e; }
check("goi moKho THAT SU chay, khong nem loi", !loiMo);
if (loiMo) console.log("     ->", loiMo.message);
check("va no dieu huong sang trang kho", daGo.includes("packs"));

let loiLa = null;
try { P.moKho("khong-co-that"); } catch (e) { loiLa = e; }
check("loai la cung khong lam vo, van mo kho", !loiLa && daGo.length === 2);

// ---- Hai bang phai khop nhau ----
// console.js noi trang nao ung voi loai nao; packs.js noi loai nao co nhan gi. Hai bang o hai
// file, va lech nhau thi tab dan sang kho voi mot loai khong ton tai - im lang, khong bao loi.
const CON = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const khoiLoaiKho = (CON.match(/const LOAI_KHO = \{([\s\S]*?)\};/) || [])[1] || "";
const loaiTuConsole = [...khoiLoaiKho.matchAll(/:\s*"([a-z]+)"/g)].map(m => m[1]);
check("console.js khai du nam trang nang luc", loaiTuConsole.length === 5);
check("moi loai console.js tro toi deu co trong bang cua packs.js",
  loaiTuConsole.length > 0 && loaiTuConsole.every(k => Object.prototype.hasOwnProperty.call(P.LOAI, k)));
check("bang loai co ca nam loai cong 'bundle' lam cho roi",
  ["agent", "skill", "workflow", "tool", "connector", "bundle"]
    .every(k => Object.prototype.hasOwnProperty.call(P.LOAI, k)));

globalThis.Alpine = _alpineCu;

// ---- Ngon ngu: `JavisI18n.lang` la HAM ----
// Quen cap ngoac thi `v[lang]` tra bang mot object ham, luon truot, va MOI ten goi roi ve
// tieng Anh trong giao dien tieng Viet. Hong lang le: van co chu de hien nen trong nhu goi
// khai thieu ban dich, chu khong nhu mot loi. Da xay ra that trong packs.js tu 0.55.22.
for (const f of ["packs.js", "console.js", "studio.js", "chatbots.js"]) {
  const p = path.join(ROOT, "dashboard", f);
  if (!fs.existsSync(p)) continue;
  const s = fs.readFileSync(p, "utf8");
  // Bat `JavisI18n.lang` khong theo sau boi `(`. Cho phep `lang:` (khai bao trong i18n).
  const xau = [...s.matchAll(/JavisI18n\.lang(?!\s*\()/g)];
  check(`${f} goi JavisI18n.lang() co ngoac, khong lay ham lam chuoi`, xau.length === 0);
}

console.log("");
if (fails.length) {
  console.log(`FAIL - test_kho_cai_dat: ${fails.length} loi: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("OK - test_kho_cai_dat: tat ca pass");
