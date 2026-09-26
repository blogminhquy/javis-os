/* Test bo boc khoi JAVIS_ASK. Chay tay / CI:
       node dashboard/test_chat_ask.js
   KHONG can trinh duyet: chi test ham thuan extract(). */
const { extract, render } = require("../../dashboard/chat-ask.js");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- 1. Khoi hop le ----
const okBlock = 'Doanh thu hom nay 250k.\n\n<!-- JAVIS_ASK: {"question":"Xem ky nao?","header":"Ky","options":[{"label":"Tuan nay","desc":"7 ngay"},{"label":"Thang nay","desc":"Tu mung 1"}]} -->';
let r = extract(okBlock);
check("hop le: clean bo sach khoi", r.clean === "Doanh thu hom nay 250k.");
check("hop le: doc dung question", r.ask && r.ask.question === "Xem ky nao?");
check("hop le: doc dung header", r.ask && r.ask.header === "Ky");
check("hop le: doc dung 2 lua chon", r.ask && r.ask.options.length === 2 &&
  r.ask.options[0].label === "Tuan nay" && r.ask.options[1].desc === "Tu mung 1");

// ---- 2. Khong co khoi ----
r = extract("Chi la cau tra loi binh thuong.");
check("khong khoi: ask = null", r.ask === null);
check("khong khoi: clean giu nguyen text", r.clean === "Chi la cau tra loi binh thuong.");

// ---- 3. JSON hong: KHONG duoc nuot cau tra loi, van phai bo khoi rac ----
r = extract('Cau tra loi that.\n\n<!-- JAVIS_ASK: {"question": broken json here -->');
check("json hong: ask = null", r.ask === null);
check("json hong: van giu cau tra loi", r.clean === "Cau tra loi that.");
check("json hong: khoi rac bi bo, khong lo ra man hinh", r.clean.indexOf("JAVIS_ASK") === -1);

// ---- 4. Thua lua chon -> cat con 4 ----
const many = '<!-- JAVIS_ASK: {"question":"Chon?","options":[{"label":"a"},{"label":"b"},{"label":"c"},{"label":"d"},{"label":"e"},{"label":"f"}]} -->';
r = extract(many);
check("thua lua chon: cat con 4", r.ask && r.ask.options.length === 4);
check("thua lua chon: giu 4 cai dau", r.ask && r.ask.options[3].label === "d");
check("thieu desc: desc thanh chuoi rong", r.ask && r.ask.options[0].desc === "");

// ---- 5. options rong / thieu question -> coi nhu khong co khoi ----
r = extract('Text.\n<!-- JAVIS_ASK: {"question":"Chon?","options":[]} -->');
check("options rong: ask = null", r.ask === null);
check("options rong: van bo khoi", r.clean === "Text.");
r = extract('<!-- JAVIS_ASK: {"options":[{"label":"a"}]} -->');
check("thieu question: ask = null", r.ask === null);

// ---- 6. Khoi nam GIUA bai (khong phai cuoi) van boc duoc ----
r = extract('Dau bai.\n<!-- JAVIS_ASK: {"question":"Chon?","options":[{"label":"a"}]} -->\nCuoi bai.');
check("khoi giua bai: van doc duoc ask", r.ask && r.ask.question === "Chon?");
check("khoi giua bai: clean noi lai 2 dau", r.clean === "Dau bai.\n\nCuoi bai.");

// ---- 7. Song chung voi JAVIS_METRICS ----
const both = 'Bao cao.\n<!-- JAVIS_METRICS: [{"label":"Doanh thu","value":"250k"}] -->\n<!-- JAVIS_ASK: {"question":"Chon?","options":[{"label":"a"}]} -->';
r = extract(both);
check("song chung metrics: doc duoc ask", r.ask && r.ask.question === "Chon?");
check("song chung metrics: KHONG dung vao khoi metrics", r.clean.indexOf("JAVIS_METRICS") !== -1);

// ---- 8. Dau vao khong phai chuoi ----
r = extract(null);
check("dau vao null: khong no", r.ask === null && r.clean === "");

// ---- 9. Nhan dai hon tran: extract() phai CAT SAN - thu hien = thu gui ----
// (hoi quy cho loi chip hien mot dang, gui mot dang khi nhan qua 40 ky tu)
const longLabel = "a".repeat(300);
const longBlock = '<!-- JAVIS_ASK: {"question":"Chon?","options":[{"label":"' + longLabel + '"}]} -->';
r = extract(longBlock);
check("nhan dai: da bi cat con <= 40 ky tu", r.ask && r.ask.options[0].label.length <= 40);
check("nhan dai: cat dung con 39 + dau …", r.ask && r.ask.options[0].label === "a".repeat(39) + "…");
check("nhan dai: KHONG con nguyen 300 ky tu (thu gui phai bang thu hien)",
  r.ask && r.ask.options[0].label !== longLabel);

// ---- 10. Nhan ngan (<= 40 ky tu): giu nguyen, KHONG them "…" ----
const shortLabel = "Tuan nay";
const shortBlock = '<!-- JAVIS_ASK: {"question":"Chon?","options":[{"label":"' + shortLabel + '"}]} -->';
r = extract(shortBlock);
check("nhan ngan: giu nguyen khong doi", r.ask && r.ask.options[0].label === shortLabel);
check("nhan ngan: khong bi them dau …", r.ask && r.ask.options[0].label.indexOf("…") === -1);

// ---- 11. Nhan dai DUNG BANG tran (40 ky tu): giu nguyen, khong thua "…" ----
// (hoi quy: cut() truoc day cat ca khi chi du 1 ky tu vi dung ">" thay vi ">=")
const exactLabel = "b".repeat(40);
const exactBlock = '<!-- JAVIS_ASK: {"question":"Chon?","options":[{"label":"' + exactLabel + '"}]} -->';
r = extract(exactBlock);
check("nhan dung tran 40: giu nguyen", r.ask && r.ask.options[0].label === exactLabel);
check("nhan dung tran 40: khong thua dau …", r.ask && r.ask.options[0].label.indexOf("…") === -1);

const oldDocument = global.document;
global.document = { createElement: () => ({}) };
const host = { querySelector: () => null, appendChild: () => {} };
const chip = render(host, { question: "Chọn?", options: [
  { label: "Có", desc: "Gửi ngay <script>" }
] }, true);
check("chip vẽ nhãn và mô tả thành hai phần riêng",
  chip.innerHTML.includes('<span class="jv-ask-chip-label">Có</span>') &&
  chip.innerHTML.includes('<span class="jv-ask-chip-desc">Gửi ngay &lt;script&gt;</span>'));
global.document = oldDocument;

if (fails.length) {
  console.log("\nFAIL - " + fails.length + " test: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_chat_ask: tat ca pass");
