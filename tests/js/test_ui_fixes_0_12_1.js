/* Ba loi UX chu repo bao + loi Groq 429.
       node tests/js/test_ui_fixes_0_12_1.js

   1. Zoom chat khong tu thu khi chuyen tab -> overlay de len trang moi.
   2. Dien thoai: cham vao note mo trinh sua, ma thanh nut tran khoi man hep nen khong thoat duoc.
   3. Doi model o trang Models thi thanh model trong chat khong doi theo.

   Kiem tren SOURCE that, khong doc thuoc long. */
const fs = require("fs");
const path = require("path");

const D = (f) => fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", f), "utf8");
const CONSOLE = D("console.js");
const APP = D("app.js");
const FE = D("file-editor.js");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- 1. Chuyen tab khong duoc de overlay chat treo lai ----
// Loi goc 0.12.1: overlay zoom MUON node cua cockpit (#chatArea, #modelBar...), roi trang ma
// khong thu thi overlay de len trang moi VA cac node do van nam trong overlay.
// 0.12.4 sua tan goc: bo han overlay - phong to gio la CHUYEN sang trang Tro chuyen. Khong con
// lop noi thi khong con gi de treo. Chi tiet duong di moi o test_chat_zoom_sang_trang.js;
// o day chi khoa cai INVARIANT: khong duoc de mot lop noi muon node cua HUD quay lai.
const navStart = CONSOLE.indexOf("function navigateTo(id)");
const navEnd = CONSOLE.indexOf("\n  function ", navStart + 10);
check("tim thay navigateTo", navStart !== -1 && navEnd > navStart);
const NAV = CONSOLE.slice(navStart, navEnd);
// _pageLeave tra node ve HUD truoc khi cviewBody bi ghi de - day moi la duong tra node that.
check("roi trang thi tra node chat ve HUD truoc",
  NAV.indexOf("_pageLeave") !== -1 && NAV.indexOf("leave()") < NAV.indexOf("store.active = id"));
check("CANARY: khong con lop noi muon node cua HUD",
  fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "chat-zoom.js"), "utf8")
    .indexOf("appendChild") === -1);

// ---- 2. Dien thoai: khong mo trinh sua note ----
const onStart = CONSOLE.indexOf("window.JavisOpenNote = function");
const onEnd = CONSOLE.indexOf("\n  };", onStart);
check("tim thay JavisOpenNote", onStart !== -1 && onEnd > onStart);
const ON = CONSOLE.slice(onStart, onEnd);
check("dien thoai thi KHONG mo trinh sua note", ON.indexOf("isNarrow()") !== -1);
// Im lang khong lam gi la dung loi UX vua sua o cho khac - phai noi ly do.
check("khong im lang: co bao ly do cho nguoi dung",
  ON.indexOf("JavisToast") !== -1 || ON.indexOf("alert(") !== -1);
check("chan TRUOC khi goi openNote", ON.indexOf("isNarrow()") < ON.indexOf("openNote("));

// Trinh sua van phai thoat duoc neu toi day bang duong khac (trang Tep tin).
check("trinh sua co CSS cho man hep", FE.indexOf("@media(max-width:700px)") !== -1);
check("thanh nut xuong dong duoc thay vi tran ra ngoai",
  FE.indexOf("flex-wrap:wrap") !== -1);

// ---- 3. Doi model phai dong bo moi cho hien thi ----
check("co ham lam moi dung chung", CONSOLE.indexOf("function refreshModelUi()") !== -1);
check("lam moi thanh chon model", CONSOLE.indexOf("window.initModelBar") !== -1);
// Phep thu "lam moi badge engine" DA BO o 0.52.13 cung luc bo badge engine+model o dau khung
// hoi thoai. Doi model van phai dong bo hai cho con lai (thanh chon model + trang Models); mot
// canary tro vao ham da xoa thi khong canh gi ca, chi do cho vui.

const saveStart = CONSOLE.indexOf("async function saveSetting(section, dataObj)");
const saveEnd = CONSOLE.indexOf("\n  // Đồng bộ mọi chỗ", saveStart);
const SAVE = CONSOLE.slice(saveStart, saveEnd > saveStart ? saveEnd : saveStart + 900);
check("luu cai dat model thi lam moi ngay", SAVE.indexOf("refreshModelUi()") !== -1);
check("chi lam moi khi doi model, khong lam moi bua",
  SAVE.indexOf('section === "model"') !== -1);
check("ve trang chat/home cung lam moi",
  NAV.indexOf("refreshModelUi()") !== -1);

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_ui_fixes_0_12_1: tat ca pass");
