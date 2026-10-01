/* Giao diện bộ phán xử hội thoại nhóm (0.65.0, gọn lại ở 0.65.1): dòng giải thích trong form bot và panel của bot.

       node tests/js/test_reply_policy_ui.js

   Chạy dưới node với DOM giả tối thiểu. Ba thứ được canh:
     1. Hàm thuần (`formHtml`, `summary`) chạy thật. Từ 0.65.1 form KHÔNG còn ô cài đặt nào: chỉ một dòng giải thích,
        và không còn đường nào để form ghi đè cấu hình của bot.
     2. Hợp đồng với chatbots.js: dòng giải thích chỉ hiện khi chọn Tự đánh giá, có mục menu, lưu bot không gửi reply_policy.
     3. Từ điển: mọi khoá `rp.*` dùng trong module đều có ở cả vi và en, các khoá của ô đã bỏ không còn, mọi mã im có nhãn.
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const MOD = src("dashboard/chatbots-reply-policy.js");
const CB = src("dashboard/chatbots.js");
const HTML = src("dashboard/index.html");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : "")); if (!cond) fails.push(name); };

// ---- nạp module với window giả ----
const win = { t: (k, v) => (v ? k + JSON.stringify(v) : k), JavisI18n: { locale: () => "vi-VN" } };
const ctx = { window: win, document: { createElement: () => ({ set innerHTML(x) {}, firstChild: null }) }, fetch: () => Promise.reject(new Error("no net")), console, Date };
vm.createContext(ctx);
vm.runInContext(MOD, ctx);
const RP = win.JavisReplyPolicy;
check("module chỉ phơi ra bốn hàm: formHtml, summary, openPanel, codeLabel (nhãn mã im cho Hộp thư)",
  RP && JSON.stringify(Object.keys(RP).sort()) === JSON.stringify(["codeLabel", "formHtml", "openPanel", "summary"]), RP && Object.keys(RP).join(","));

// ---- 1. hàm thuần ----
const html = RP.formHtml();
check("form chỉ còn một dòng giải thích, ẩn sẵn (chatbots.js bật khi chọn Tự đánh giá)",
  html.indexOf('id="cbRpBox"') >= 0 && html.indexOf('style="display:none"') >= 0 && html.indexOf("rp.auto_note") >= 0);
check("và KHÔNG có ô nhập, nút bấm hay lựa chọn nào", !/<input|<textarea|<button|<select|type="radio"|type="checkbox"/.test(html), html);
check("summary có chữ khi bot ở Tự đánh giá, rỗng khi không",
  RP.summary({ reply_when: "auto" }) === "rp.tt_on" && RP.summary({ reply_when: "mention" }) === ""
  && RP.summary({ reply_when: "always" }) === "" && RP.summary({}) === "" && RP.summary(null) === "");

// ---- 2. hợp đồng với chatbots.js ----
check("chatbots.js dựng dòng giải thích trong phần chọn khi nào lên tiếng", /RP\.formHtml\(\)/.test(CB));
check("dòng giải thích chỉ hiện khi chọn Tự đánh giá (veRw)", /rpBox\.style\.display = v === "auto" \? "" : "none"/.test(CB));
check("lưu bot KHÔNG gửi reply_policy nữa (form không được ghi đè aliases và người được dạy)",
  CB.indexOf("chung.reply_policy") < 0 && CB.indexOf("RP.read") < 0 && CB.indexOf("RP.bind") < 0);
check("thẻ bot có mục menu Bộ phán xử (chỉ khi Tự đánh giá) và mở panel",
  /b\.reply_when === "auto"\s*\?\s*'<button class="cb-rp"/.test(CB) && /JavisReplyPolicy\.openPanel\(b\)/.test(CB));
check("dòng tóm tắt của thẻ dùng JavisReplyPolicy.summary", /JavisReplyPolicy\.summary\(b\)/.test(CB));
check("index.html nạp module TRƯỚC chatbots.js", HTML.indexOf("chatbots-reply-policy.js") > 0
  && HTML.indexOf("chatbots-reply-policy.js") < HTML.indexOf("/static/chatbots.js"));
check("panel gọi đủ các đường API còn lại", ["/reply-policy", "?limit=100", "/label", "/forget", "/cases/", "/delete"].every((s) => MOD.indexOf(s) >= 0));
check("panel không còn gọi route soạn hồ sơ bằng tay", MOD.indexOf("draft-guidelines") < 0);
check("nhấn 'Là chủ' lưu qua /update với reply_policy JSON", /\/update"[\s\S]{0,120}reply_policy: JSON\.stringify\(\{ trainer_ids: ids \}\)/.test(MOD));
check("nút Đúng/Sai hiện cho mọi quyết định ứng viên (tự học luôn bật)", /x\.candidate \? ' <button/.test(MOD) && MOD.indexOf("learning_enabled") < 0);
check("panel có dòng hướng dẫn thay cho các ô đã bỏ", MOD.indexOf('tt("rp.panel_h")') >= 0);

// ---- 2b. nút Là chủ dễ hiểu hơn (0.65.14): tên rõ nghĩa, nhãn Chủ, bỏ được, Đúng/Sai có chú thích ----
check("nút đổi tên thành 'Đặt làm chủ bot' (không còn 'Là chủ' khó hiểu), có chú thích khi rê chuột",
  VI["rp.is_owner"] === "Đặt làm chủ bot" && /Make bot owner/.test(EN["rp.is_owner"])
  && /class="cb-rp-lnk rp-owner"[^;]*title="' \+ esc\(tt\("rp\.is_owner_tip"\)\)/.test(MOD));
check("người đã là chủ hiện nhãn 'Chủ' ở tin của họ, và không còn nút đặt chủ ở tin đó",
  /chuBot\(\)\.indexOf\(x\.sender_id\) >= 0 \? ' ' \+ chip\("ok", tt\("rp\.owner_badge"\)\)/.test(MOD)
  && /chuBot\(\)\.indexOf\(x\.sender_id\) < 0\s*\? ' <button type="button" class="cb-rp-lnk rp-owner"/.test(MOD));
check("có khối 'Chủ bot' đầu panel: liệt kê người đã đặt kèm nút 'Bỏ chủ', và nói rõ khi chưa có ai thì bot chưa nghe lời dạy của ai",
  /khoiChu\(\)/.test(MOD) && /rp-unowner/.test(MOD) && VI["rp.owner_remove"] === "Bỏ chủ" && /chưa nghe lời dạy của ai/.test(VI["rp.owner_none"]));
check("bỏ chủ lọc đúng người đó ra khỏi danh sách rồi lưu qua CÙNG một hàm lưu (chỉ một chỗ gọi /update)",
  /luuChu\(chuBot\(\)\.filter\(function \(x\) \{ return x !== sid; \}\)\)/.test(MOD)
  && /luuChu\(chuBot\(\)\.concat\(\[b\.dataset\.sid\]\)\)/.test(MOD) && (MOD.match(/\/update"/g) || []).length === 1);
check("chủ chưa có tên trong tin gần đây vẫn hiện (để bỏ được), không lộ id thô",
  /return tt\("rp\.owner_unknown"\)/.test(MOD) && !/chip\("ok", sid\)/.test(MOD));
const thumbKeys = ["rp.thumb_up_reply", "rp.thumb_down_reply", "rp.thumb_up_silent", "rp.thumb_down_silent"];
check("Đúng/Sai có chú thích theo từng dòng (bot nói hay bot im), và có một dòng giải thích chung trên danh sách",
  /noi \? "rp\.thumb_up_reply" : "rp\.thumb_up_silent"/.test(MOD) && /noi \? "rp\.thumb_down_reply" : "rp\.thumb_down_silent"/.test(MOD)
  && thumbKeys.every((k) => VI[k] && EN[k]) && new Set(thumbKeys.map((k) => VI[k])).size === 4 && MOD.indexOf('tt("rp.thumb_hint")') >= 0);
check("nghĩa Sai khớp với nhãn máy ghi (im mà Sai là Im nhầm, nói mà Sai là Chen nhầm)",
  /phải im/.test(VI["rp.thumb_down_reply"]) && /phải nói/.test(VI["rp.thumb_down_silent"]));

// ---- 3. từ điển ----
const keys = new Set([...MOD.matchAll(/"(rp\.[a-z_]+)"/g)].map((m) => m[1]));
keys.add("rp.tt_on");
const thieu = [...keys].filter((k) => !(k in VI) || !(k in EN));
check(`mọi khoá rp.* trong module (${keys.size}) có ở cả vi và en`, thieu.length === 0, thieu.join(","));
check("từ điển vi và en có cùng bộ khoá rp.*", JSON.stringify(Object.keys(VI).filter((k) => k.startsWith("rp.")).sort())
  === JSON.stringify(Object.keys(EN).filter((k) => k.startsWith("rp.")).sort()));
check("không khoá rp.* nào rỗng", Object.keys(VI).filter((k) => k.startsWith("rp.")).every((k) => VI[k].trim() && EN[k].trim()));
const usados = new Set([...keys, ...[...CB.matchAll(/"(rp\.[a-z_]+)"/g)].map((m) => m[1])]);
const chet = Object.keys(VI).filter((k) => k.startsWith("rp.") && !usados.has(k) && !/^rp\.(code|label|source)_/.test(k));
check("không còn khoá rp.* mồ côi (của các ô đã bỏ)", chet.length === 0, chet.join(","));
check("có nhãn sess.bot_badge", VI["sess.bot_badge"] && EN["sess.bot_badge"]);
const codes = [...(/var CODE_LB = \{([\s\S]*?)\};/.exec(MOD) || [])[1].matchAll(/(\w+):\s*"rp\./g)].map((m) => m[1]);
check("bảng mã im có đủ mã bộ máy phát ra", ["no_signal", "junk", "addressed_other", "no_grounding", "rate_limited", "rate_limited_user",
  "just_spoke", "policy_error", "owner_typing", "judge_silent", "below_threshold", "agent_silent", "taken_over"].every((c) => codes.indexOf(c) >= 0), codes.join(","));
check("lời giải thích nói thật về dữ liệu được lưu (400 ký tự, 14 ngày, 180 ngày)",
  ["400", "14", "180"].every((n) => VI["rp.auto_note"].indexOf(n) >= 0 && EN["rp.auto_note"].indexOf(n) >= 0));
check("không dùng em dash trong module và test", ![MOD, fs.readFileSync(__filename, "utf8")].some((t) => t.indexOf(String.fromCharCode(0x2014)) >= 0));

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_reply_policy_ui: tất cả pass");
