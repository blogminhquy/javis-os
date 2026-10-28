// 0.148.0, chủ repo yêu cầu 15/10/2026:
// - kéo đổi bề rộng các khung ở trang Trò chuyện (cột Hội thoại/Thư mục) và trang đồ thị (cột Vault, cột hội thoại);
// - trang Chatbot: mỗi cuộc hội thoại có thêm SỐ TIN (như cột Lịch sử của Trò chuyện), khác số đỏ là số tin chưa đọc.
//
//     python tests/run.py --js col_resize_0148 -v
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const CR = require(path.join(ROOT, "dashboard", "col-resize.js"));
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const style = fs.readFileSync(path.join(ROOT, "dashboard", "style.css"), "utf8");
const consoleJs = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const conv = fs.readFileSync(path.join(ROOT, "dashboard", "conversations.js"), "utf8");
const html = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

// ───────────── chặn bề rộng ─────────────
const o = { min: 200, max: 560, total: () => 1200, other: () => 320, keep: 360 };
check("không hẹp hơn min", CR.chan(o, 50) === 200);
check("không rộng quá max", CR.chan(Object.assign({}, o, { other: () => 0 }), 900) === 560);
check("chừa khoang giữa ít nhất 360px sau khi trừ cột bên kia", CR.chan(o, 900) === 520, CR.chan(o, 900));

// ───────────── gắn tay kéo: kéo, bàn phím, nhấp đúp, nhớ ─────────────
const store = {};
global.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); },
  removeItem: (k) => { delete store[k]; } };
const listeners = {};
const handle = { className: "", tabIndex: -1, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; },
  addEventListener(n, f) { listeners[n] = f; }, setPointerCapture() {}, parentNode: null };
global.document = { createElement: () => handle, body: { classList: { add() {}, remove() {} } } };
const col = { w: 260, querySelector: () => null, appendChild(h) { h.parentNode = this; },
  getBoundingClientRect() { return { width: this.w }; } };
const props = {};
const host = { style: { setProperty: (k, v) => { props[k] = v; col.w = parseInt(v, 10); }, removeProperty: (k) => { delete props[k]; } } };
const opt = { host, varName: "--hud-left-w", key: "javis_hud_left_w", min: 200, max: 560, edge: "right", total: () => 1400,
  other: () => 320, keep: 360, label: "common.resize_vault" };
CR.attach(col, opt);
check("tay kéo là separator có nhãn, focus được", handle.attrs.role === "separator" && handle.attrs["aria-orientation"] === "vertical"
  && handle.tabIndex === 0 && handle.className.indexOf("col-resize-right") >= 0);
listeners.pointerdown({ button: 0, clientX: 420, preventDefault() {}, pointerId: 1 });
listeners.pointermove({ clientX: 520 });
listeners.pointerup({});
check("kéo mép phải sang phải 100px: rộng 360px, nhớ", props["--hud-left-w"] === "360px" && store.javis_hud_left_w === "360",
  JSON.stringify([props, store]));
listeners.keydown({ key: "ArrowLeft", preventDefault() {} });
check("mũi tên trái thu 16px", props["--hud-left-w"] === "344px", props["--hud-left-w"]);
listeners.dblclick();
check("nhấp đúp: về mặc định, quên số đã nhớ", !("--hud-left-w" in props) && !("javis_hud_left_w" in store));
store.javis_hud_left_w = "999";
CR.apply(opt);
check("mở trang: áp lại số đã nhớ trong giới hạn", props["--hud-left-w"] === "560px", props["--hud-left-w"]);

// ───────────── nối vào trang ─────────────
check("trang đồ thị: lưới đọc biến bề rộng, thu cột vẫn về 44px",
  style.includes("grid-template-columns: var(--hud-left-w, 260px) minmax(0, 1fr) var(--hud-right-w, 320px);") &&
  style.includes("body.vault-thu .hud-body { grid-template-columns: 44px minmax(0, 1fr) var(--hud-right-w, 320px); }") &&
  style.includes("body.chatcol-thu .hud-body { grid-template-columns: var(--hud-left-w, 260px) minmax(0, 1fr) 44px; }"));
check("trang Trò chuyện: cột Hội thoại đọc biến, gắn tay kéo sau khi dựng cột",
  consoleJs.includes(".chatpage-side{ width:var(--cp-side-w, 280px);") &&
  /window\.JavisColResize\.attach\(sideEl, oSide\)/.test(consoleJs));
check("CSS: tay kéo chỉ ở màn rộng, nằm trọn trong cột, ẩn khi cột thu hay bị mượn",
  /\.col-resize \{ display: none; \}/.test(css) && /\.col-resize-right \{ right: 0; \}/.test(css) &&
  /\.chatpage\.side-thu \.chatpage-side > \.col-resize \{ display: none; \}/.test(css) && /\.cside-pane \.col-resize \{ display: none !important; \}/.test(css));
check("col-resize.js nạp trước app.js và console.js",
  html.indexOf("/static/col-resize.js") > 0 && html.indexOf("/static/col-resize.js") < html.indexOf("/static/app.js") &&
  html.indexOf("/static/col-resize.js") < html.indexOf("/static/console.js"));

// ───────────── số tin ở trang Chatbot ─────────────
// Owner, 2026-10-28: v5 had moved the total into the hover text and he lost it; the grey "N tin" is back on the row,
// before the red unread count (two different numbers), at 16px like the rest of the v5 list.
check("dòng hội thoại: tổng số tin (xám) và số chưa đọc (đỏ) cùng nằm trên dòng",
  /\(c\.message_count \? '<span class="ht-count" title="' \+ esc\(window\.t\("ht\.so_tin_title", \{ count: c\.message_count \}\)\)/.test(conv) &&
  /window\.t\("sess\.msgs", \{ count: c\.message_count \}\)/.test(conv) &&
  conv.indexOf('class="ht-count"') < conv.indexOf('class="ht-badge" title="\' + esc(window.t("ht.chua_doc_title"') &&
  /\.ib-v5 \.ht-count \{ font-size: 16px;/.test(fs.readFileSync(path.join(ROOT, "dashboard/inbox-v5.css"), "utf8")));
check("i18n đủ vi/en", ["common.resize_col", "common.resize_hint", "common.resize_vault", "common.resize_chatcol",
  "common.resize_chatside", "ht.so_tin_title", "ht.chua_doc_title"].every((k) => vi[k] && en[k]));

console.log();
if (fails) { console.log("ĐỎ " + fails + " mục"); process.exit(1); }
console.log("XANH");
