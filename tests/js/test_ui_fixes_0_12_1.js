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

// ---- 1. Chuyen tab phai thu zoom chat ----
// Overlay MUON node cua cockpit (#chatArea, #modelBar...). Roi trang ma khong thu thi overlay
// de len trang moi VA cac node do van nam trong overlay chu khong ve cho cu.
const navStart = CONSOLE.indexOf("function navigateTo(id)");
const navEnd = CONSOLE.indexOf("\n  function ", navStart + 10);
check("tim thay navigateTo", navStart !== -1 && navEnd > navStart);
const NAV = CONSOLE.slice(navStart, navEnd);
check("chuyen tab thi thu zoom chat lai", NAV.indexOf("JavisChatStage") !== -1
  && NAV.indexOf("collapse()") !== -1);
// Phai thu TRUOC khi doi trang, khong thi trang moi da render voi overlay con treo.
check("thu zoom TRUOC khi doi store.active",
  NAV.indexOf("collapse()") < NAV.indexOf("store.active = id"));

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
check("lam moi badge engine", CONSOLE.indexOf("window.refreshEngineBadge") !== -1);
// Goi tu console.js chi chay neu app.js CO xuat ra window - thieu buoc nay la truot im lang,
// dung ho loi "code dung ma khong noi duoc" da lap lai nhieu lan.
check("app.js THAT SU xuat refreshEngineBadge ra window",
  APP.indexOf("window.refreshEngineBadge = refreshEngineBadge") !== -1);

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
