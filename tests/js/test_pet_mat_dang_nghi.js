/* Linh vật lúc ĐANG NGHĨ: hai con mắt phải ĐẢO giữa dáng liếc và hai gạch ngang.

       node tests/js/test_pet_mat_dang_nghi.js

   Vì sao cần một test CHẠY THẬT chứ không dò mã nguồn như test_linh_vat.js: chuyện này nằm
   trong vòng vẽ requestAnimationFrame, và vòng đó có ba cái chốt có thể giết nó trong im lặng -
   prefers-reduced-motion, tab bị ẩn, và trạng thái khác "thinking". Dò chữ trong mã thì cả ba
   ca hỏng đó vẫn xanh. Ở đây dựng một bộ DOM giả tối thiểu, tự quay đồng hồ và tự gọi từng
   khung hình, rồi xem cái gì thật sự được vẽ ra.

   (Trong trình duyệt của phiên Claude không quan sát được: khung xem bị ẩn nên document.hidden
   luôn true, requestAnimationFrame không chạy. Nên đường kiểm duy nhất là ở đây.)

   KHÔNG dùng ký tự em dash. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");

let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

// ---- Bộ DOM giả tối thiểu -------------------------------------------------------------
// Chỉ đủ cho pet.js dựng khung và chạy vòng vẽ. Mỗi nút giữ innerHTML để cuối cùng đọc ra
// được HAI CON MẮT đang là hình gì.
function nutGia() {
  const n = {
    innerHTML: "", hidden: false, dataset: {}, childElementCount: 1,
    style: { setProperty() {}, removeProperty() {} },
    classList: { add() {}, remove() {}, contains: () => false, toggle() {} },
    setAttribute() {}, getAttribute: () => null, addEventListener() {}, appendChild() {},
    getBoundingClientRect: () => ({ top: 0, left: 0, right: 0, bottom: 0, width: 56, height: 56 }),
    querySelectorAll: () => [], focus() {},
  };
  n.querySelector = () => n;
  return n;
}

const nut = {
  ".pet-body": nutGia(), ".pet-menu": nutGia(), ".pet-rig": nutGia(),
  ".pet-ring": nutGia(), ".pet-face": nutGia(), ".pet-eyes": nutGia(), svg: nutGia(),
};
const goc = nutGia();
goc.querySelector = (sel) => nut[sel] || null;

let dongHo = 1000;                 // đồng hồ giả, ms
let khungCho = null;               // callback rAF đang chờ
// MỘT đối tượng media query duy nhất, bật tắt được giữa chừng. pet.js giữ tham chiếu tới nó
// từ lúc init và đọc `.matches` mỗi khung hình, nên thay cả hàm matchMedia sau đó thì không
// ăn thua - bản đầu của test này thay hàm và tưởng đã tắt hiệu ứng, hoá ra chưa tắt gì cả.
const mqGiam = { matches: false, addEventListener() {}, addListener() {} };

global.window = {
  t: (k, d) => d || k,
  ic: () => "",
  innerWidth: 1280, innerHeight: 900,
  matchMedia: () => mqGiam,
  addEventListener() {}, dispatchEvent() {},
  requestAnimationFrame: (fn) => { khungCho = fn; return 1; },
  cancelAnimationFrame: () => { khungCho = null; },
};
global.document = {
  readyState: "complete", hidden: false,
  createElement: () => goc,
  getElementById: () => null,
  addEventListener() {},
  body: { appendChild() {} },
  querySelectorAll: () => [],
};
global.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
global.performance = { now: () => dongHo };
global.requestAnimationFrame = window.requestAnimationFrame;
global.cancelAnimationFrame = window.cancelAnimationFrame;
global.fetch = () => new Promise(() => {});      // không bao giờ trả lời: giữ nguyên cfg mặc định
global.CustomEvent = function () {};
global.FormData = function () { this.append = function () {}; };

require(path.join(root, "dashboard", "pet.js"));
const P = window.JavisPet;
check("pet.js nạp được với DOM giả", !!P && typeof P.setState === "function");

// Dáng mắt ĐANG VẼ. Ba dáng phân biệt được bằng chính hình của chúng, và phải phân biệt được:
// cú CHỚP MẮT cũng là một vệt ngang, nên nếu dáng nghĩ vẽ y hệt dáng chớp thì test không tài
// nào biết mắt đang lim dim nghĩ hay chỉ vừa chớp một cái (xem EYES trong pet.js).
function dangMat() {
  const h = nut[".pet-eyes"].innerHTML;
  if (h.indexOf("ellipse") >= 0) return "liec";
  if (h.indexOf("M-7 -1 H7") >= 0) return "gach";     // hai gạch ngang lúc nghĩ
  if (h.indexOf("M-9 0 H9") >= 0) return "chop";      // đang chớp mắt
  return "khac";
}

// Quay đồng hồ và gọi từng khung hình, trả về dáng mắt đang vẽ sau mỗi bước.
//
// PHẢI nhường lại vòng lặp sự kiện giữa hai khung (await setTimeout 0): cú chớp mắt của pet
// hẹn setTimeout 130ms để mở mắt lại, mà một vòng for đồng bộ thì không bao giờ cho cái hẹn đó
// chạy - cờ `dangChop` kẹt ở true, apDungTrangThai thôi không vẽ nữa và mắt đứng hình ở dáng
// nhắm. Bản đầu của test này quên mất, và nó "bắt" ra hai lỗi không hề có thật.
async function quay(soBuoc, buocMs) {
  const ra = [];
  for (let i = 0; i < soBuoc; i++) {
    dongHo += buocMs;
    const fn = khungCho; khungCho = null;
    if (fn) fn(dongHo);
    await new Promise((r) => setTimeout(r, 0));
    // Đang chớp mắt thì ĐỢI THẬT cho cú chớp xong rồi mới đọc. Đồng hồ ở đây là đồ giả (mỗi
    // khung nhảy 200ms) trong khi cú chớp hẹn bằng setTimeout THẬT 130ms, nên nếu đọc ngay
    // thì một cú chớp trải ra cả chục khung giả và nuốt mất dáng mắt đang muốn đo.
    if (dangMat() === "chop") await new Promise((r) => setTimeout(r, 160));
    ra.push(dangMat());
  }
  return ra;
}

(async () => {

// ---- 1. Đang nghĩ: phải thấy CẢ HAI dáng ----------------------------------------------
P.setState("thinking");
// Bỏ các khung ĐANG CHỚP MẮT ra khỏi phép đo: chớp là chuyện khác, xen vào đều đặn, và nó
// không nói gì về chuyện mắt có đảo dáng hay không.
const chuoi = (await quay(90, 200)).filter(x => x !== "chop");
const soLiec = chuoi.filter(x => x === "liec").length;
const soGach = chuoi.filter(x => x === "gach").length;
check("lúc nghĩ có lúc mắt liếc (dáng lục trí nhớ)", soLiec > 0);
check("lúc nghĩ có lúc mắt thành HAI GẠCH NGANG", soGach > 0);
// Đảo qua đảo lại chứ không phải đổi một lần rồi thôi.
let doi = 0;
for (let i = 1; i < chuoi.length; i++) if (chuoi[i] !== chuoi[i - 1]) doi++;
check("đảo qua lại nhiều lần trong 18 giây (" + doi + " lần)", doi >= 4);
// ...nhưng không đảo như đèn nháy: mỗi dáng phải giữ được hơn một giây.
let dai = 1, ngan = 99;
for (let i = 1; i < chuoi.length; i++) {
  if (chuoi[i] === chuoi[i - 1]) dai++;
  else { ngan = Math.min(ngan, dai); dai = 1; }
}
check("mỗi dáng giữ trên một giây, không nháy (" + ngan * 0.2 + "s)", ngan * 200 >= 1000);

// ---- 2. Trạng thái KHÁC thì mắt đứng yên ----------------------------------------------
P.setState("idle");
const idle = (await quay(40, 200)).filter(x => x !== "chop");
check("lúc rảnh mắt KHÔNG đảo (chỉ có dáng của idle)", new Set(idle).size === 1);
P.setState("speaking");
const noi = (await quay(40, 200)).filter(x => x !== "chop");
check("lúc trả lời mắt cũng đứng yên", new Set(noi).size === 1);

// ---- 3. Vào lại trạng thái nghĩ thì bắt đầu từ dáng liếc, không nháy ngay --------------
P.setState("thinking");
const dauTien = (await quay(3, 200)).filter(x => x !== "chop");      // 600ms đầu
check("vừa vào trạng thái nghĩ thì còn ở dáng liếc, chưa đổi ngay",
  dauTien.every(x => x === "liec"));

// ---- 4. Tắt hiệu ứng (prefers-reduced-motion) thì không đảo gì cả ----------------------
// Vòng vẽ thoát sớm ở nhánh đó, nên mắt phải đứng nguyên - đây chính là ca mà dò mã nguồn
// không bao giờ bắt được.
mqGiam.matches = true;
P.setState("thinking");
const tatHieuUng = (await quay(40, 200)).filter(x => x !== "chop");
check("tắt hiệu ứng thì mắt đứng yên, không đảo", new Set(tatHieuUng).size === 1);

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - mắt linh vật lúc đang nghĩ");
})();
