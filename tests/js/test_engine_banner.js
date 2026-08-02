/* Test dai bao "chua ket noi Model AI" tren thanh trang thai.
       node tests/js/test_engine_banner.js

   Vi sao co file nay: ban cu ghep ten engine + cau bao loi cua server + huong dan sua,
   ra mot chuoi dai hon ca thanh trang thai nen bi cat cut giua chung - va phan bi cat lai
   dung la phan noi PHAI LAM GI. No con chi sai cho ("mo terminal go /login") vi gio ket noi
   o trang Models. Nguoi dung cung khong can biet "bo nao claude" la gi.

   Kiem tren SOURCE that cua console.js, khong doc thuoc long: doi loi ma quen rao thi CI do. */
const fs = require("fs");
const path = require("path");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "dashboard", "console.js"), "utf8");
const CSS = fs.readFileSync(
  path.join(__dirname, "..", "..", "dashboard", "console.css"), "utf8");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// Lay dung than ham refreshEngineBanner de khong bat nham chuoi o cho khac.
const start = SRC.indexOf("async function refreshEngineBanner()");
const end = SRC.indexOf("\n  function boot()", start);
check("tim thay refreshEngineBanner", start !== -1 && end > start);
const FN = SRC.slice(start, end);

// ---- 1. Khong duoc nhac ten engine hay bat mo terminal ----
check("khong noi 'Bo nao' trong dai bao", FN.indexOf('"Bộ não') === -1);
check("khong bat mo terminal go /login", FN.indexOf("/login") === -1);
check("khong ghep cau bao loi cua server vao dai bao",
  FN.indexOf("rec.message") === -1 || FN.indexOf("b.title") !== -1);

// ---- 2. Phai noi dung viec can lam ----
check("noi ro la chua ket noi Model AI", FN.indexOf("Chưa kết nối Model AI") !== -1);
check("moi nguoi dung bam", FN.indexOf("bấm để kết nối") !== -1);

// ---- 3. Do dai: phai VUA thanh trang thai ----
// Dai bao dung inline tren thanh trang thai canh cac nut khac. Qua ~60 ky tu la chac chan
// bi cat cut o man hinh thuong, va cat cut thi mat dung phan huong dan.
const m = FN.match(/b\.innerHTML\s*=\s*WARN_ICON\s*\+\s*"([^"]*)"/);
check("doc duoc noi dung dai bao", !!m);
if (m) {
  const text = m[1].trim();
  check(`dai bao du ngan (${text.length} ky tu, tran 60)`, text.length <= 60);
  check("dai bao khong con noi chuoi dai", FN.indexOf('+ " " + (ENGINE_FIX_UI') === -1);
}

// ---- 4. Chi tiet ky thuat chuyen vao tooltip, khong bo di ----
// Van can khi di hoi, chi la khong dang chiem cho tren thanh trang thai.
check("van giu chi tiet ky thuat trong tooltip", FN.indexOf("b.title") !== -1);
check("tooltip co nhac trang Models", FN.indexOf("trang Models") !== -1);

// ---- 5. Bam duoc va dan toi dung cho ----
// Bao "chua ket noi" ma khong dua duoc nguoi ta toi cho ket noi thi chi la than phien.
check("dai bao co gan su kien bam", SRC.indexOf('_eb.addEventListener("click"') !== -1);
check("bam thi sang trang Models", SRC.indexOf('navigateTo("models")') !== -1);
check("CSS cho thay bam duoc (con tro tay)",
  /\.engine-banner\s*\{[^}]*cursor:\s*pointer/s.test(CSS));

// ---- 6. Bang chung day la loi THAT tung xay ra ----
check("khong con bang tra ENGINE_FIX_UI cu", SRC.indexOf("ENGINE_FIX_UI") === -1);

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_engine_banner: tat ca pass");
