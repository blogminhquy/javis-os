/* Trang Cài đặt linh vật phải VẼ RA ĐƯỢC, không chỉ "trông có vẻ đúng" (0.59.37).

       node tests/js/test_pet_trang_cai_dat.js

   Lỗi thật, chủ dự án gửi ảnh 18/09: mở Cài đặt > Linh vật thì chỉ thấy tiêu đề và một đường
   kẻ, bên dưới TRỐNG TRƠN. Không hộp lỗi, không dòng đỏ, không gì cả.

   Nguyên nhân: bản 0.59.36 đặt `nhanMat` ở scope của renderPetCard nhưng để nó đọc `mats`,
   biến chỉ được khai bên trong `ve()`. Mỗi lần vẽ là một ReferenceError ném ra giữa lúc dựng
   chuỗi template, nên `host.innerHTML = ...` không bao giờ chạy tới. Trang rỗng.

   VÌ SAO KHÔNG TEST NÀO BẮT ĐƯỢC. Phép thử của 0.59.36 soi MÃ NGUỒN bằng regex: nó hỏi "trong
   console.js có dòng nhanMat tra theo khoá không". Có. Xanh. Trong khi tính năng chết hẳn.
   Soi chữ không thay được việc CHẠY: một biến ngoài tầm với đọc lên vẫn y hệt một biến đúng.

   Nên test này NẠP THẬT pet.js, BÓC THẬT hàm renderPetCard ra khỏi console.js, chạy nó với
   một cái DOM giả, rồi soi chuỗi HTML nó trả về. Bóc bằng cách đếm ngoặc nên nó bám theo mã
   nguồn thật; hàm đổi tên hay biến mất thì test này đỏ, và đỏ như vậy là ĐÚNG. */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- DOM giả, vừa đủ cho một lần vẽ ----
function nut() {
  const o = {
    _html: "", disabled: false, textContent: "", dataset: {}, classList: { add() {}, remove() {}, contains: () => false },
    style: { setProperty() {} }, setAttribute() {}, addEventListener() {}, appendChild() {},
    querySelector: () => nut(), querySelectorAll: () => [],
    get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  };
  return o;
}

function napPet() {
  const el = () => nut();
  const win = {
    JavisPet: null, matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener() {}, innerWidth: 1280, innerHeight: 800,
  };
  const doc = {
    documentElement: { dataset: { javisTheme: "dark" }, getAttribute: () => "dark", classList: { contains: () => false } },
    addEventListener() {}, querySelectorAll: () => [], querySelector: () => el(),
    getElementById: () => el(), createElement: () => el(), createElementNS: () => el(), body: el(),
  };
  new Function("window", "document", "localStorage", "navigator", "matchMedia",
    "requestAnimationFrame", "cancelAnimationFrame", "getComputedStyle",
    fs.readFileSync(path.join(ROOT, "dashboard", "pet.js"), "utf8"))(
    win, doc, { getItem: () => null, setItem() {} }, { userAgent: "node" }, win.matchMedia,
    () => 0, () => {}, () => ({ getPropertyValue: () => "" }));
  return win;
}

// ---- Bóc renderPetCard ra khỏi console.js bằng cách đếm ngoặc ----
function bocHam(src, khai) {
  const i = src.indexOf(khai);
  if (i < 0) return null;
  let d = 0, j = src.indexOf("{", i);
  const dau = j;
  for (; j < src.length; j++) {
    if (src[j] === "{") d++;
    else if (src[j] === "}" && !--d) break;
  }
  return src.slice(dau + 1, j);
}

const consoleSrc = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const than = bocHam(consoleSrc, "function renderPetCard(host, tuMayChu) {");
check("bóc được hàm renderPetCard khỏi console.js", !!than && than.length > 2000,
  than ? than.length + " ký tự" : "không thấy");

const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const win = napPet();
const P = win.JavisPet;

const t = (k) => (typeof vi[k] === "string" ? vi[k] : "!!THIEU:" + k + "!!");
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const host = nut();
let noRender = null;
try {
  new Function("host", "tuMayChu", "window", "t", "esc", "SAVE_ICON", "Icons", than)(
    host, null, win, t, esc, "<svg/>", { warn: () => "" });
} catch (e) {
  noRender = e;
}
check("VẼ ĐƯỢC, không ném lỗi giữa chừng", noRender === null,
  noRender && noRender.constructor.name + ": " + noRender.message);

const html = host.innerHTML;
check("trang KHÔNG rỗng (đúng cái ảnh báo lỗi 18/09)", html.length > 1000, html.length + " ký tự");

// ---- Đủ năm hàng chọn ----
for (const [ten, dau] of [
  ["hình dáng", "data-pet-shape="], ["cỡ", "data-pet-size="], ["màu thân", "data-pet-palette="],
  ["màu mắt", "data-pet-eye="], ["cỡ mắt", "data-pet-eye-size="],
]) check("có hàng chọn " + ten, html.includes(dau));

// ---- Mọi màu đều ra ô, và mọi nhãn đều dịch được ----
const soO = (dau) => (html.match(new RegExp(dau.replace(/[-[\]{}()*+?.\\^$|]/g, "\\$&"), "g")) || []).length;
check("vẽ đủ ô cho MỌI màu thân", soO("data-pet-palette=") === Object.keys(P.palettes()).length,
  `${soO("data-pet-palette=")} ô / ${Object.keys(P.palettes()).length} màu`);
check("vẽ đủ ô cho MỌI màu mắt", soO("data-pet-eye=") === Object.keys(P.eyeColors()).length,
  `${soO("data-pet-eye=")} ô / ${Object.keys(P.eyeColors()).length} màu`);
check("không nhãn nào thiếu bản dịch", !html.includes("!!THIEU:"),
  (html.match(/!!THIEU:[^!]+!!/g) || []).slice(0, 4).join(", "));

// ---- Mỗi màu mắt mang ĐÚNG tên của nó, không phải cùng một tên ----
// Đây là lỗi 0.59.36 đã sửa: bản cũ viết cứng "trắng thì Trắng, còn lại Đen".
const tenMat = Object.keys(P.eyeColors()).map(k => vi["pet.eye." + k]);
const thieuTen = tenMat.filter(n => !html.includes(`title="${n}"`));
check("mỗi màu mắt hiện ĐÚNG tên riêng của nó", thieuTen.length === 0, thieuTen.join(", "));
check("và các tên đó khác nhau thật", new Set(tenMat).size === tenMat.length);

console.log(fails.length ? "\nFAIL: " + fails.join(", ") : "\nTat ca OK");
process.exit(fails.length ? 1 : 0);
