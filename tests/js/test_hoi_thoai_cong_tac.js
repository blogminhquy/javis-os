/* Công tắc Tự động / Tôi trả lời, dòng trạng thái và dòng "Bot im" của Hộp thư (0.65.4): canh bằng cấu trúc mã.

       node tests/js/test_hoi_thoai_cong_tac.js

   Chủ dự án (2026-09-30) thấy bản mẫu đầu bị lệch: thẻ trạng thái nhỏ hơn hai nút và nút thứ hai rớt xuống dòng. Nên bản thật
   đặt trạng thái ở MỘT dòng riêng, không chung hàng với nút nào. Ba thứ được canh:
     1. Đầu khung: công tắc hai nấc thay nút Tiếp quản nhỏ, gạt bằng một chạm, không làm gì khi bấm đúng nấc đang bật.
     2. Đáy khung: dòng trạng thái đứng riêng (không nằm trong ô nhập), dòng "Bot im: lý do" dưới tin khách cuối.
     3. Từ điển: khoá mới có đủ vi và en, khoá của nút cũ không còn.
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const CV = src("dashboard/conversations.js");
const RP = src("dashboard/chatbots-reply-policy.js");
const CSS = src("dashboard/console.css");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : "")); if (!cond) fails.push(name); };

// ---- 1. công tắc ----
check("đầu khung có công tắc hai nấc Tự động | Tôi trả lời, chỉ với cuộc chat có bot",
  /class="ht-seg" role="group"/.test(CV) && /data-m="ai"/.test(CV) && /data-m="human"/.test(CV) &&
  /\(laBot\s*\?\s*'<div class="ht-seg"/.test(CV));
check("mỗi nấc có aria-pressed cho trình đọc màn hình", /aria-pressed="' \+ \(!human\)/.test(CV) && /aria-pressed="' \+ human/.test(CV));
check("nút Tiếp quản/Trả lại AI kiểu cũ đã bỏ", !/ht-mode-btn/.test(CV) && !/ht\.tra_ai/.test(CV) && !/ht\.tiep_quan/.test(CV) &&
  !/ht-mode-btn/.test(CSS));
check("gạt sang nấc kia mới gọi đổi chế độ, bấm đúng nấc đang bật thì không làm gì",
  /if \(b\.dataset\.m !== \(human \? "human" : "ai"\)\) doiMode\(c\.id, b\.dataset\.m\)/.test(CV));
check("đổi chế độ vẫn đi qua POST /conversations/{id}/mode (không API mới)", /\/mode", \{ method: "POST", body: fd\(\{ mode: mode \}\)/.test(CV));

// ---- 2. dòng trạng thái và bot im ----
check("dòng trạng thái đứng RIÊNG, không nằm trong khối ô nhập (tránh lệch hàng như bản mẫu đầu)",
  /function veTrangThai\(c, human\)/.test(CV) && /\(laBot \? veTrangThai\(c, human\) : ""\) \+\s*\n\s*\(guiDuoc \? veCompose/.test(CV) &&
  !/veTrangThai/.test(CV.slice(CV.indexOf("function veCompose"), CV.indexOf("async function gui"))));
check("dòng trạng thái nói tên bot; bot chưa rõ tên thì nói 'Bot'", /ht\.st_ai_0/.test(CV) && /c\.bot_name \? "ht\.st_ai" : "ht\.st_ai_0"/.test(CV));
check("ghi chú ô nhập không còn nhắc nút Trả lại AI đã bỏ", !/Trả lại AI/.test(VI["ht.gui_tiep_quan"]) && /Tự động/.test(VI["ht.gui_tiep_quan"]));
check("'Bot im: lý do' nằm TRONG vùng tin, ngay sau tin cuối", /_msgs\.map\(veTin\)\.join\(""\) \+ veBotIm\(c\)/.test(CV));
check("lý do lấy nhãn từ bộ phán xử (codeLabel), kèm điểm/ngưỡng khi có; mã lạ thì hiện nguyên mã",
  /RP\.codeLabel\(s\.code\)/.test(CV) && /toFixed\(2\)/.test(CV) && /function codeLabel\(code\)/.test(RP) &&
  /CODE_LB\[code\] \? tt\(CODE_LB\[code\]\) : String\(code \|\| ""\)/.test(RP));
check("nút 'Vì sao' mở đúng bảng Bộ phán xử của bot đó", /JavisReplyPolicy\.openPanel\(\{ id: c\.bot_id, name: c\.bot_name \|\| "" \}\)/.test(CV));
check("nhịp tự làm mới so cả bot_silence (đổi thì vẽ lại)", /JSON\.stringify\(\[d\.conversation, d\.messages, d\.bot_silence\]\)/.test(CV));
check("lý do do server trả được thoát HTML trước khi vẽ", /esc\(window\.t\("ht\.silent", \{ why: lyDo \+ diem \}\)\)/.test(CV));

// hàm codeLabel chạy thật
const win = { t: (k) => k, JavisI18n: { locale: () => "vi-VN" } };
const ctx = { window: win, document: { createElement: () => ({}) }, fetch: () => Promise.reject(new Error("no net")), console, Date };
vm.createContext(ctx);
vm.runInContext(RP, ctx);
check("codeLabel: mã biết thì ra khoá nhãn, mã lạ thì ra nguyên mã, rỗng thì rỗng",
  win.JavisReplyPolicy.codeLabel("below_threshold") === "rp.code_below_threshold" &&
  win.JavisReplyPolicy.codeLabel("ma_la_moi") === "ma_la_moi" && win.JavisReplyPolicy.codeLabel("") === "" &&
  win.JavisReplyPolicy.codeLabel(null) === "");

// ---- CSS ----
check("CSS: công tắc, dòng trạng thái và dòng bot im đều có kiểu; nấc 'Tôi trả lời' đổi sang màu cảnh báo khi bật",
  /\.ht-seg \{/.test(CSS) && /\.ht-seg-b\.on \{/.test(CSS) && /\.ht-seg-b\.on\[data-m="human"\]/.test(CSS) &&
  /\.ht-status \{/.test(CSS) && /\.ht-status\.human/.test(CSS) && /\.ht-silent \{/.test(CSS) && /\.ht-silent-why \{/.test(CSS));
check("CSS điện thoại: công tắc xuống hàng riêng rộng hết chiều ngang, hai nấc chia đôi",
  /@media \(max-width: 640px\) \{\s*\.ht-head \{ flex-wrap: wrap; \}\s*\.ht-seg \{ order: 3; flex: 1 1 100%; \}\s*\.ht-seg-b \{ flex: 1 1 50%; justify-content: center;/.test(CSS));
check("CSS: công tắc không co lại khi tiêu đề dài (flex: none)", /\.ht-seg \{ flex: none;/.test(CSS));

// ---- 3. từ điển ----
const moi = ["ht.sw_aria", "ht.sw_auto", "ht.sw_mine", "ht.st_ai", "ht.st_ai_0", "ht.st_human", "ht.silent", "ht.silent_why"];
check("khoá mới có ở cả vi và en", moi.every((k) => VI[k] && EN[k]), moi.filter((k) => !VI[k] || !EN[k]).join(","));
check("đều được mã dùng", moi.every((k) => CV.indexOf('"' + k + '"') > 0));
check("khoá của nút cũ đã bỏ", ["ht.tra_ai", "ht.tiep_quan", "ht.dang_tiep_quan"].every((k) => !(k in VI) && !(k in EN)));
check("không dùng em dash trong test này", fs.readFileSync(__filename, "utf8").indexOf(String.fromCharCode(0x2014)) < 0);

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_hoi_thoai_cong_tac: tất cả pass");
