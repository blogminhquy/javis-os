// 0.142.0, chủ repo yêu cầu 14/10/2026 sau khi xem trang Cộng sự:
// - thẻ trợ lý có GIỜ NHẮN GẦN NHẤT cùng hàng tên (như danh sách chat);
// - cột phải (Lịch sử, Công việc, Cài đặt) MẶC ĐỊNH ẨN ở màn rộng, bấm nút là hiện, lựa chọn được nhớ;
// - cột danh sách rộng hơn và KÉO ĐƯỢC ở đường biên (cả cột phải), nhớ bề rộng;
// - cột phải ẩn thì chữ trong khung chat giãn ra thay vì dừng ở 72 ký tự.
//
//     python tests/run.py --js cong_su_bo_cuc_0142 -v
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "..", "..");
const src = fs.readFileSync(path.join(ROOT, "dashboard", "workspace.js"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}
const cut = (from, to) => { const i = src.indexOf(from); return src.slice(i, src.indexOf(to, i + from.length)); };

// ───────────── giờ nhắn gần nhất ─────────────
const gioSrc = cut("  function gioNgan(ts, now) {", "  function gioNhanHtml(ts) {");
const g = vm.createContext({ t: (k) => (k === "ws.yesterday" ? vi["ws.yesterday"] : k) });
vm.runInContext(gioSrc + "\nglobalThis.gioNgan = gioNgan;", g);
const now = new Date(2026, 9, 14, 22, 30).getTime();
const at = (y, m, d, hh, mm) => new Date(y, m, d, hh, mm).getTime() / 1000;
check("hôm nay: giờ:phút", g.gioNgan(at(2026, 9, 14, 9, 5), now) === "09:05", g.gioNgan(at(2026, 9, 14, 9, 5), now));
check("hôm qua: chữ Hôm qua", g.gioNgan(at(2026, 9, 13, 23, 59), now) === "Hôm qua");
check("xa hơn: ngày/tháng; khác năm thì kèm năm", g.gioNgan(at(2026, 8, 30, 8, 0), now) === "30/09" &&
  g.gioNgan(at(2025, 11, 31, 8, 0), now) === "31/12/2025");
check("chưa nhắn bao giờ: không ghi gì", g.gioNgan(0, now) === "" && g.gioNgan(undefined, now) === "");
check("0.190.0: thẻ trợ lý: giờ nhỏ đứng cùng cụm với công tắc Auto ở góc dưới phải, chỉ ở tab Trợ lý",
  /\(laAgent \? '<div class="ws-item-end">' \+ gioNhanHtml\(x\.last_chat_at\) \+/.test(src)
  && !/'<\/strong>' \+\s*\(he \? '<span class="ws-sys">'[^\n]*gioNhanHtml/.test(src)
  && /var laAgent = S\.loai === "agent";/.test(src));
check("xong một lượt chat: giờ trên thẻ đổi ngay", /function onTurnDone\(sid\) \{[\s\S]{0,400}ag\.last_chat_at = Date\.now\(\) \/ 1000/.test(src));
check("CSS: tên co giãn; giờ nhỏ 12px, không phóng to trên màn hẹp", /\.ws-item-top \{ display: flex;/.test(css) &&
  /\.ws-item-top > strong \{ flex: 1 1 auto; min-width: 0; \}/.test(css)
  && /\.ws-item-time \{ flex: none; font-size: 12px;/.test(css) && !/\.ws-item-time \{ font-size: 14px; \}/.test(css));

// ───────────── cột phải mặc định ẩn, nhớ lựa chọn ─────────────
const phaiSrc = cut("  function manRong() {", "  // ---------- kéo đường biên");
function dungPhai(narrow, saved) {
  const cls = new Set();
  const store = saved == null ? {} : { javis_ws_right: saved };
  const page = { classList: { contains: (c) => cls.has(c), toggle: (c, on) => { if (on) cls.add(c); else cls.delete(c); } } };
  const ctx = vm.createContext({
    S: { el: { querySelector: () => page } },
    window: { matchMedia: () => ({ matches: narrow }) },
    localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } },
  });
  vm.runInContext(phaiSrc + "\nglobalThis.api = { manRong, nhoPhaiHien, phaiDangHien, datPhai };", ctx);
  return { api: ctx.api, cls, store, page };
}
let w = dungPhai(false, null);
// render(): màn rộng và chưa nhớ "hiện" thì thêm lớp right-open (nghĩa "đang ẩn" ở màn rộng).
if (w.api.manRong() && !w.api.nhoPhaiHien()) w.cls.add("right-open");
check("màn rộng, lần đầu: cột phải ẨN", !w.api.phaiDangHien() && w.cls.has("right-open"));
w.api.datPhai(true);
check("bấm nút: hiện, và nhớ", w.api.phaiDangHien() && w.store.javis_ws_right === "1");
w.api.datPhai(false);
check("bấm lần nữa: ẩn, và nhớ", !w.api.phaiDangHien() && w.store.javis_ws_right === "0");
w = dungPhai(false, "1");
check("đã nhớ hiện: mở trang là hiện", w.api.nhoPhaiHien() === true);
w.api.datPhai(true, true);
check("hiện tạm (mở Cài đặt để xác nhận trợ lý) không ghi đè lựa chọn", w.store.javis_ws_right === "1");
w = dungPhai(true, null);
w.api.datPhai(true);
check("màn hẹp: cột phải là ngăn kéo, hiện = mở ngăn, không ghi nhớ", w.cls.has("right-open") && !("javis_ws_right" in w.store));
check("render: màn rộng mặc định thêm right-open khi chưa nhớ hiện",
  /if \(manRong\(\) && !nhoPhaiHien\(\)\) page\.classList\.add\("right-open"\);/.test(src));

// ───────────── kéo đường biên ─────────────
const keoSrc = cut("  var BE_RONG = {", "  function thuGonCaiDat() {");
const props = {}, store2 = {};
const handlers = {};
const handle = { dataset: { resize: "left" }, addEventListener: (n, f) => { handlers[n] = f; }, setPointerCapture() {} };
const cot = { w: 300, getBoundingClientRect() { return { width: this.w }; } };
const page2 = {
  clientWidth: 1200,
  style: { setProperty: (k, v) => { props[k] = v; cot.w = parseInt(v, 10); }, removeProperty: (k) => { delete props[k]; } },
  classList: { _c: {}, add() {}, remove() {}, toggle(c, on) { this._c[c] = !!on; } },
  querySelectorAll: () => [handle],
  querySelector: () => cot,
};
const k = vm.createContext({ S: { el: null }, document: { getElementById: () => null }, heptLai: () => false, esc: String,
  localStorage: { getItem: (x) => store2[x] || null, setItem: (x, v) => { store2[x] = v; },
  removeItem: (x) => { delete store2[x]; } } });
vm.runInContext(keoSrc + "\nglobalThis.api = { chanBeRong, apBeRong, noiKeoBien };", k);
k.api.noiKeoBien(page2);
handlers.pointerdown({ button: 0, clientX: 300, preventDefault() {}, pointerId: 1 });
handlers.pointermove({ clientX: 380 });
handlers.pointerup({});
check("kéo biên trái sang phải 80px: cột rộng 380px và được nhớ", props["--ws-left-w"] === "380px" && store2.javis_ws_left_w === "380",
  JSON.stringify([props, store2]));
handlers.pointerdown({ button: 0, clientX: 380, preventDefault() {}, pointerId: 1 });
handlers.pointermove({ clientX: 10 });
handlers.pointerup({});
check("0.191.0: kéo quá hẹp: co về dải avatar 72px, trang mang lớp ws-mini",
  props["--ws-left-w"] === "72px" && page2.classList._c["ws-mini"] === true, props["--ws-left-w"]);
handlers.pointerdown({ button: 0, clientX: 72, preventDefault() {}, pointerId: 1 });
handlers.pointermove({ clientX: 190 });
handlers.pointerup({});
check("kéo ra quá ngưỡng: danh sách đầy đủ, ít nhất 220px, bỏ lớp ws-mini",
  props["--ws-left-w"] === "220px" && page2.classList._c["ws-mini"] === false, props["--ws-left-w"]);
check("không rộng quá 45% trang", k.api.chanBeRong("left", 2000, page2) === 540 && k.api.chanBeRong("right", 2000, page2) === 600);
handlers.keydown({ key: "ArrowRight", preventDefault() {} });
check("bàn phím: mũi tên phải nới 16px", props["--ws-left-w"] === "236px", props["--ws-left-w"]);
handlers.dblclick();
check("nhấp đúp: về bề rộng mặc định, quên số đã nhớ", !("--ws-left-w" in props) && !store2.javis_ws_left_w);
store2.javis_ws_right_w = "900";
k.api.apBeRong(page2);
check("mở trang: áp lại bề rộng đã nhớ, vẫn chặn trần", props["--ws-right-w"] === "600px", props["--ws-right-w"]);

check("CSS: cột trái rộng hơn mặc định và theo biến kéo được; tay kéo chỉ ở màn rộng",
  /\.wspage > \.ws-left \{ width: var\(--ws-left-w, clamp\(240px, 24vw, 320px\)\);/.test(css) &&
  /\.wspage > \.ws-right \{ width: var\(--ws-right-w, 350px\);/.test(css) && /\.ws-resize \{ display: none; \}/.test(css) &&
  /cursor: col-resize; touch-action: none;/.test(css));
// 0.181.0: the owner reversed the 120ch widening (answers ran up to the outline bar); the assistant page keeps the main
// chat's 72ch measure.
check("CSS: no 120ch widening on the assistant page any more (same measure as the main chat)",
  !/\.wspage\.right-open \.ws-slot \.msg-javis \.bubble \{ max-width: min\(120ch/.test(css));
// Rà soát trước khi phát hành.
check("đổi khổ màn: đặt lại right-open theo nghĩa mới (màn hẹp đóng ngăn, màn rộng theo lựa chọn)",
  /function theoKhoMan\(\)[\s\S]{0,600}page\.classList\.toggle\("right-open", manRong\(\) \? !nhoPhaiHien\(\) : false\)/.test(src) &&
  /mq\.addEventListener\("change", doi\)/.test(src));
check("lưu cài đặt không thu cột phải khi chủ đã chọn hiện", /function thuGonCaiDat\(\) \{[\s\S]{0,200}if \(manRong\(\) && nhoPhaiHien\(\)\) return;/.test(src));
check("rời tab Công việc thì gỡ tab đó", /if \(S\.tabPhai === "viec"\) ganCongViec\(dangChon\(\)\);[\s\S]{0,300}else if \(_congViec\) \{ _congViec\.destroy\(\); _congViec = null; \}/.test(src));
{
  const page3 = { clientWidth: 1200, querySelector: () => ({ getBoundingClientRect: () => ({ width: 500 }) }) };
  const k3 = vm.createContext({ getComputedStyle: () => ({ display: "block", position: "relative" }) });
  vm.runInContext(keoSrc + "\nglobalThis.chan = chanBeRong;", k3);
  check("kéo hai cột: khung chat giữa luôn còn ít nhất 360px", k3.chan("left", 900, page3) === 340, k3.chan("left", 900, page3));
}
check("laptop hẹp 1061-1240px: cột phải giữ bề rộng mặc định cũ",
  /@media \(min-width: 1061px\) and \(max-width: 1240px\) \{\s*\.wspage > \.ws-right \{ width: var\(--ws-right-w, 272px\); \}/.test(css));
check("tay kéo là separator có nhãn, focus được", /role="separator" aria-orientation="vertical" tabindex="0"/.test(src));
check("i18n đủ vi/en", ["ws.yesterday", "ws.last_chat", "ws.resize_list", "ws.resize_panel", "ws.resize_hint"].every((x) => vi[x] && en[x]));

console.log();
if (fails) { console.log("ĐỎ " + fails + " mục"); process.exit(1); }
console.log("XANH");
