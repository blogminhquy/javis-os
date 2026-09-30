/* Hai nút "Trả lời giúp tin này" và "Gợi ý câu trả lời" của Hộp thư (0.65.5): canh bằng cấu trúc mã.

       node tests/js/test_hoi_thoai_tra_loi_giup.js

   Chủ dự án (2026-09-30): muốn nhanh chóng chọn cho bot tự trả lời ngay trong hòm thư khi đang đúng chế độ. Ba thứ được canh:
     1. Nút: hai nút cùng cao chia đôi bề ngang; nút chưa dùng được VẪN HIỆN và chạm vào nói lý do; không bấm chồng khi đang soạn.
     2. Kết quả: gửi hỏng mà bot đã soạn thì chữ nằm trong ô nhập; bản nháp không đè chữ đang gõ nếu chưa được đồng ý.
     3. Từ điển và CSS đủ.
*/
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const CV = src("dashboard/conversations.js");
const CSS = src("dashboard/console.css");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : "")); if (!cond) fails.push(name); };

const fn = (name) => { const i = CV.indexOf("function " + name + "("); return i < 0 ? "" : CV.slice(i, i + 4500); };
const ACT = fn("renderActions");
const ONACT = CV.slice(CV.indexOf("async function onAction("), CV.indexOf("async function onAction(") + 4500);

// ---- 1. nút ----
check("hàng nút nằm NGAY SAU dòng trạng thái và TRƯỚC ô nhập", /renderStatusLine\(c, human\) \+ renderActions\(c, human, guiDuoc\)/.test(CV));
check("chế độ Tự động: 'Trả lời giúp tin này' (nút chính) + 'Gợi ý câu trả lời'",
  /actionButton\("answer", "zap", "ht\.act_answer", whyAnswer, true\)/.test(ACT) && /actionButton\("draft", "sparkles", "ht\.act_draft", whyDraft, false\)/.test(ACT));
check("chế độ Tôi trả lời: 'Gợi ý câu trả lời' + 'Trả lại cho bot' (và không có nút Trả lời giúp)",
  /human\s*\?\s*actionButton\("draft"[\s\S]{0,120}actionButton\("back", "bot", "ht\.act_back"/.test(ACT));
check("nút 'Trả lời giúp' chỉ dùng được khi: không tiếp quản, kênh gửi được, bot đang chạy, tin cuối là của khách",
  /whyAnswer = human \? "ht\.why_human" : !guiDuoc \? "ht\.why_nosend" : !_running \? "ht\.why_off" : !lastCustomer \? "ht\.why_done" : ""/.test(ACT) &&
  /sender_type === "customer"/.test(ACT));
check("nút 'Gợi ý' cần có tin khách và kênh gửi được (dùng được cả lúc đang tiếp quản)",
  /whyDraft = !hasCustomerMsg \? "ht\.why_nomsg" : !guiDuoc \? "ht\.why_nosend" : ""/.test(ACT));
check("nút chưa dùng được VẪN HIỆN (không ẩn, không disabled câm): có data-why, aria-disabled, và chạm vào thì nói lý do",
  /data-why="' \+ why/.test(ACT) && /aria-disabled="true"/.test(ACT) && /if \(b\.dataset\.why\) return setActionNote\(window\.t\(b\.dataset\.why\), false\)/.test(ONACT));
check("đang soạn thì khoá cả hai nút và hiện 'Đang soạn…', không cho bấm chồng",
  /_actBusy \? " disabled" : ""/.test(ACT) && /ht\.act_busy/.test(ACT) && /if \(_actBusy\) return;/.test(ONACT));
check("bấm 'Trả lại cho bot' chỉ gạt chế độ về Tự động (API cũ, không API mới)", /if \(a === "back"\) return doiMode\(c\.id, "ai"\)/.test(ONACT));
check("gọi đúng endpoint với mode send hoặc draft", /\/ai-reply", \{ method: "POST", body: fd\(\{ mode: a === "draft" \? "draft" : "send" \}\)/.test(ONACT));

// ---- 2. kết quả ----
check("gửi hỏng mà bot đã soạn: chữ đổ vào ô nhập để chủ gửi tay, kèm dòng báo lỗi",
  /if \(text && ta2\) \{ ta2\.value = text; \}/.test(ONACT) && /ht\.act_send_failed/.test(ONACT) && /d\.text|\(d && d\.text\)/.test(ONACT));
check("Agent chọn im thì nói thẳng, không gửi gì", /if \(d\.silent\) return setActionNote\(window\.t\("ht\.act_silent"\), false\)/.test(ONACT));
check("bản nháp đổ vào ô nhập và đưa con trỏ vào, chưa gửi", /ta2\.value = text; ta2\.focus\(\)/.test(ONACT) && /ht\.act_drafted/.test(ONACT));
check("ô nhập đang có chữ thì HỎI trước khi đè bằng bản nháp", /ta\.value\.trim\(\) && !confirm\(window\.t\("ht\.act_overwrite"\)\)/.test(ONACT));
check("gửi xong nói có dạy bot hay không (taught)", /d\.taught \? "ht\.act_sent_taught" : "ht\.act_sent"/.test(ONACT));
check("gửi xong tải lại tin và danh sách; dòng ghi chú sống qua lần vẽ lại khung",
  /await taiTin\(false\)/.test(ONACT) && /tai\(true\)/.test(ONACT) && /_actNote \? '<div class="ht-acts-note/.test(ACT));
check("đổi cuộc chat thì bỏ dòng ghi chú cũ", /_chon = id;\s*_dauVetTin = "";\s*_actNote = null;/.test(CV));
check("giao diện đọc bot_running từ server", /_running = !!d\.bot_running/.test(CV));
check("lỗi mạng cũng được báo, không nuốt", /catch \(e\) \{ loi = e\.message; \}/.test(ONACT));

// ---- 3. CSS + từ điển ----
check("CSS: hai nút cùng cao, chia đôi bề ngang, chữ dài thì cắt bằng dấu ba chấm chứ không rớt dòng",
  /\.ht-acts \{ display: grid; grid-template-columns: 1fr 1fr;/.test(CSS) && /\.ht-act \{ height: 34px;/.test(CSS) &&
  /\.ht-act span \{[^}]*text-overflow: ellipsis; white-space: nowrap/.test(CSS));
check("CSS: nút chính, nút chưa dùng được (viền đứt), dòng ghi chú lỗi", /\.ht-act\.pri \{/.test(CSS) && /\.ht-act\.off, \.ht-act\.pri\.off \{[^}]*dashed/.test(CSS) &&
  /\.ht-acts-note\.err \{/.test(CSS));
check("CSS: ô nhập không còn viền trên ngay sau hàng nút (khỏi hai đường kẻ)", /\.ht-acts ~ \.ht-compose \{ border-top: 0; \}/.test(CSS));
const moi = ["ht.act_answer", "ht.act_draft", "ht.act_back", "ht.act_busy", "ht.why_human", "ht.why_off", "ht.why_done", "ht.why_nosend", "ht.why_nomsg",
  "ht.act_sent", "ht.act_sent_taught", "ht.act_drafted", "ht.act_silent", "ht.act_fail", "ht.act_send_failed", "ht.act_overwrite"];
check("khoá mới có ở cả vi và en", moi.every((k) => VI[k] && EN[k]), moi.filter((k) => !VI[k] || !EN[k]).join(","));
check("đều được mã dùng", moi.every((k) => CV.indexOf('"' + k + '"') > 0), moi.filter((k) => CV.indexOf('"' + k + '"') < 0).join(","));
check("lý do khi nút tắt nói rõ cách bật lại", /Tự động/.test(VI["ht.why_human"]) && /tab Bot/.test(VI["ht.why_off"]));
check("tên hàm mới bằng tiếng Anh (quy ước từ 0.65.0)", ["renderActions", "setActionNote", "onAction", "renderStatusLine", "renderSilenceLine"].every((n) => CV.indexOf("function " + n + "(") > 0));
check("không dùng em dash trong test này", fs.readFileSync(__filename, "utf8").indexOf(String.fromCharCode(0x2014)) < 0);

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_hoi_thoai_tra_loi_giup: tất cả pass");
