/* Trang Cộng sự: mở một QUY TRÌNH là cột phải về tab Cài đặt (nút Chạy quy trình nằm ở đó),
   còn trợ lý vẫn mở ở Lịch sử như chốt 16/09. Hai loại NHỚ TAB RIÊNG, và tab của quy trình
   không ghi xuống localStorage: "khởi đầu vào luôn cài đặt" là điều chủ dự án muốn (17/09),
   nhớ tab cũ qua F5 là làm ngược lại.

   Chạy: node tests/js/test_tab_quy_trinh_cai_dat.js
   Ghi chú: KHÔNG dùng ký tự em dash. */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.join(__dirname, "..", "..");
const ws = fs.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- 1. Hình dạng nguồn: hai ô nhớ riêng, mặc định đúng ----
check("S có ô nhớ tab theo loại, quy trình mặc định Cài đặt, trợ lý mặc định Lịch sử",
  /tabCua: \{ agent: "lichsu", workflow: "cai" \}/.test(ws));
check("mở trang: tab trợ lý lấy từ localStorage, tab quy trình LUÔN về Cài đặt",
  /S\.tabCua = \{ agent: S\.tabPhai, workflow: "cai" \};\s*\n\s*S\.tabPhai = S\.tabCua\[S\.loai\] \|\| S\.tabPhai;/.test(ws));
check("CANARY: mặc định của trợ lý vẫn là Lịch sử (chốt 16/09 không bị lật)",
  /tabPhai: "lichsu"/.test(ws) && /TAB_PHAI\.indexOf\(r\) >= 0 \? r : "lichsu"/.test(ws));
check("vẽ cột phải chọn tab THEO LOẠI đang xem (cả khi có mục lẫn khi trống)",
  (ws.match(/chonTabPhai\(tabTheoLoai\(\)\)/g) || []).length >= 2
  && /function tabTheoLoai\(\) \{ return \(S\.tabCua && S\.tabCua\[S\.loai\]\) \|\| S\.tabPhai; \}/.test(ws));
check("chỉ tab của trợ lý mới ghi xuống localStorage",
  /if \(S\.loai !== "workflow"\) \{ try \{ localStorage\.setItem\("javis_ws_rtab", S\.tabPhai\); \}/.test(ws));

// ---- 2. Hành vi: bóc chonTabPhai ra chạy thật ----
const iBat = ws.indexOf("  function chonTabPhai(tab) {");
const iKet = ws.indexOf("\n  }\n", iBat) + 4;
const doan = ws.slice(iBat, iKet);
check("bóc được chonTabPhai", iBat > 0 && /function chonTabPhai/.test(doan) && /traCayThuMuc\(\)/.test(doan));

function dungCtx(loai, tabCua) {
  const kho = {};
  const nut = [], khung = [];
  const el = {
    querySelectorAll: (q) => (q === "[data-rtab]" ? nut : q === "[data-rpane]" ? khung : []),
    querySelector: () => null,
  };
  const ctx = {
    S: { loai: loai, el: el, tabPhai: "lichsu", tabCua: tabCua },
    TAB_PHAI: ["lichsu", "files", "cai"],
    localStorage: { getItem: (k) => (k in kho ? kho[k] : null), setItem(k, v) { kho[k] = String(v); } },
    window: { JavisVaultPanel: { borrow() { return true; }, giveBack() {} } },
    traCayThuMuc() {},
    kho: kho,
  };
  vm.createContext(ctx); vm.runInContext(doan, ctx);
  return ctx;
}

// Quy trình: đổi tab thì nhớ TRONG PHIÊN (S.tabCua.workflow) nhưng KHÔNG ghi localStorage.
{
  const c = dungCtx("workflow", { agent: "lichsu", workflow: "cai" });
  c.chonTabPhai("lichsu");
  check("quy trình: đổi sang Lịch sử thì S.tabCua.workflow nhớ", c.S.tabCua.workflow === "lichsu" && c.S.tabPhai === "lichsu");
  check("quy trình: KHÔNG ghi javis_ws_rtab (F5 là về Cài đặt)", !("javis_ws_rtab" in c.kho));
  check("quy trình: ô nhớ của trợ lý không bị đè", c.S.tabCua.agent === "lichsu");
}
// Trợ lý: vẫn nhớ qua localStorage như trước.
{
  const c = dungCtx("agent", { agent: "lichsu", workflow: "cai" });
  c.chonTabPhai("files");
  check("trợ lý: đổi tab thì ghi javis_ws_rtab như cũ", c.kho["javis_ws_rtab"] === "files" && c.S.tabCua.agent === "files");
  check("trợ lý: ô nhớ của quy trình vẫn là Cài đặt", c.S.tabCua.workflow === "cai");
}
// Không có S.tabCua (khung test cũ) thì vẫn chạy, không ném lỗi.
{
  const c = dungCtx("agent", undefined);
  let loi = null;
  try { c.chonTabPhai("cai"); } catch (e) { loi = e; }
  check("thiếu S.tabCua vẫn không ném lỗi", !loi && c.S.tabPhai === "cai");
}

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - tab quy trình mở ở Cài đặt");
