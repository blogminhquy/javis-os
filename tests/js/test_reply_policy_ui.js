/* Giao diện bộ phán xử hội thoại nhóm (0.65.0): khối trong form bot và panel của bot.

       node tests/js/test_reply_policy_ui.js

   Chạy dưới node với DOM giả tối thiểu. Ba thứ được canh:
     1. Hàm thuần (`normalize`, `formHtml`, `read`, `summary`) chạy thật: mặc định khớp server, giá trị lạ về
        phía hẹp nhất, nội dung do chủ gõ KHÔNG chèn được HTML vào form.
     2. Hợp đồng với chatbots.js: khối chỉ hiện khi chọn Tự đánh giá, luôn được đọc khi lưu, có mục menu.
     3. Từ điển: mọi khoá `rp.*` dùng trong module đều có ở cả vi và en, và mọi mã im có nhãn.
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
check("module phơi ra JavisReplyPolicy đủ hàm", RP && ["formHtml", "bind", "read", "normalize", "summary", "openPanel"].every((k) => typeof RP[k] === "function"));

// ---- 1. hàm thuần ----
const N = RP.normalize;
check("mặc định khớp server: tắt, vừa, tài liệu, không học", JSON.stringify(N(undefined)) === JSON.stringify({
  mode: "off", eagerness: "medium", grounding: "docs", guidelines: "", aliases: [], trainer_ids: [], learning_enabled: false }), JSON.stringify(N(undefined)));
check("giá trị lạ về mặc định, không nâng quyền", N({ mode: "bay-gio", eagerness: "ồn", grounding: "x", learning_enabled: "true" }).mode === "off"
  && N({ learning_enabled: "true" }).learning_enabled === false);
check("giữ giá trị hợp lệ", N({ mode: "on", eagerness: "high", grounding: "role", learning_enabled: true, aliases: ["Nhi"], trainer_ids: ["7"] }).eagerness === "high");
check("summary rỗng khi tắt, có chữ khi bật hoặc chạy thử",
  RP.summary({ reply_policy: { mode: "off" } }) === "" && RP.summary({ reply_policy: { mode: "on" } }) === "rp.tt_on"
  && RP.summary({ reply_policy: { mode: "shadow" } }) === "rp.tt_shadow" && RP.summary({}) === "");

const seg = (id, name, ds, cur) => "<seg id=" + id + " cur=" + cur + ">" + ds.map((d) => d.v).join(",") + "</seg>";
const html = RP.formHtml({ mode: "shadow", guidelines: '</textarea><script>alert(1)</script>', aliases: ['a"b', "Nhi"], trainer_ids: ["1", "2"],
  learning_enabled: true }, seg, { canDraft: true });
check("khối form có đủ ô", ["cbRpBox", "cbRpMode", "cbRpEag", "cbRpGround", "cbRpGuide", "cbRpAliases", "cbRpLearn", "cbRpTrainers", "cbRpDraft"]
  .every((id) => html.indexOf(id) >= 0));
check("chế độ hiện tại được chọn sẵn", html.indexOf("cbRpMode cur=shadow") >= 0);
check("nội dung chủ gõ KHÔNG chèn được HTML (luật lên tiếng)", html.indexOf("<script>") < 0 && html.indexOf("&lt;script&gt;") >= 0);
check("dấu nháy trong tên gọi được thoát", html.indexOf('a"b') < 0 && html.indexOf("a&quot;b") >= 0);
check("nút Soạn từ vai trò chỉ có khi đang sửa bot đã tồn tại", RP.formHtml({}, seg, { canDraft: false }).indexOf("cbRpDraft") < 0);
check("ô người dạy bot ẩn khi chưa bật tự học", RP.formHtml({ learning_enabled: false }, seg, {}).indexOf('id="cbRpTrainBox" style="display:none"') >= 0);
check("khối ẩn sẵn (chatbots.js bật khi chọn Tự đánh giá)", html.indexOf('id="cbRpBox" class="cb-rp" style="display:none"') >= 0);

// read(): DOM giả
function fakeBox(v) {
  const radios = { cbRpMode: v.mode, cbRpEag: v.eagerness, cbRpGround: v.grounding };
  const els = { "#cbRpGuide": { value: v.guidelines }, "#cbRpAliases": { value: v.aliases }, "#cbRpTrainers": { value: v.trainers },
                "#cbRpLearn": { checked: v.learn } };
  return { querySelector(sel) {
    const m = /input\[name="(\w+)"\]:checked/.exec(sel);
    if (m) return radios[m[1]] ? { value: radios[m[1]] } : null;
    return els[sel] || null;
  } };
}
const got = RP.read(fakeBox({ mode: "on", eagerness: "high", grounding: "role", guidelines: "Chỉ nói đúng ngành", aliases: "Nhi, cô Mai;\nchị Hoa ",
                              trainers: "111, 222", learn: true }));
check("read() ra đúng khuôn server", got.mode === "on" && got.eagerness === "high" && got.grounding === "role" && got.learning_enabled === true
  && got.guidelines === "Chỉ nói đúng ngành", JSON.stringify(got));
check("read() tách tên gọi và ID theo phẩy, chấm phẩy, xuống dòng", JSON.stringify(got.aliases) === '["Nhi","cô Mai","chị Hoa"]'
  && JSON.stringify(got.trainer_ids) === '["111","222"]', JSON.stringify(got));
const trong = RP.read(fakeBox({ mode: "", eagerness: "", grounding: "", guidelines: "", aliases: "", trainers: "", learn: false }));
check("read() form trống thì về mặc định an toàn (tắt)", trong.mode === "off" && trong.eagerness === "medium" && trong.grounding === "docs"
  && trong.learning_enabled === false && trong.aliases.length === 0);

// ---- 2. hợp đồng với chatbots.js ----
check("chatbots.js dựng khối trong phần chọn khi nào lên tiếng",
  /RP\.formHtml\(b && b\.reply_policy, htmlSeg, \{ canDraft: sua \}\)/.test(CB));
check("khối chỉ hiện khi chọn Tự đánh giá (veRw)", /rpBox\.style\.display = v === "auto" \? "" : "none"/.test(CB));
check("lưu luôn kèm reply_policy đọc từ form (kể cả khi khối đang ẩn)", /chung\.reply_policy = JSON\.stringify\(RP\.read\(box\)\)/.test(CB));
check("thẻ bot có mục menu Bộ phán xử và mở panel", /class="cb-rp"/.test(CB) && /JavisReplyPolicy\.openPanel\(b\)/.test(CB));
check("dòng tóm tắt của thẻ nói khi bộ phán xử đang bật", /JavisReplyPolicy\.summary\(b\)/.test(CB));
check("index.html nạp module TRƯỚC chatbots.js", HTML.indexOf("chatbots-reply-policy.js") > 0
  && HTML.indexOf("chatbots-reply-policy.js") < HTML.indexOf("/static/chatbots.js"));
check("panel gọi đủ các đường API", ["/reply-policy", "?limit=100", "/label", "/forget", "/cases/", "/delete", "/draft-guidelines"].every((s) => MOD.indexOf(s) >= 0));
check("nhấn 'Là chủ' lưu qua /update với reply_policy JSON", /\/update"[\s\S]{0,120}reply_policy: JSON\.stringify\(\{ trainer_ids: ids \}\)/.test(MOD));
check("thumbs chỉ hiện khi bật tự học và là quyết định ứng viên", /hoc && x\.candidate/.test(MOD));

// ---- 3. từ điển ----
const keys = new Set([...MOD.matchAll(/"(rp\.[a-z_]+)"/g)].map((m) => m[1]));
for (const k of ["rp.tt_on", "rp.tt_shadow"]) keys.add(k);
const thieu = [...keys].filter((k) => !(k in VI) || !(k in EN));
check(`mọi khoá rp.* trong module (${keys.size}) có ở cả vi và en`, thieu.length === 0, thieu.join(","));
check("từ điển vi và en có cùng bộ khoá rp.*", JSON.stringify(Object.keys(VI).filter((k) => k.startsWith("rp.")).sort())
  === JSON.stringify(Object.keys(EN).filter((k) => k.startsWith("rp.")).sort()));
check("không khoá rp.* nào rỗng", Object.keys(VI).filter((k) => k.startsWith("rp.")).every((k) => VI[k].trim() && EN[k].trim()));
check("có nhãn sess.bot_badge", VI["sess.bot_badge"] && EN["sess.bot_badge"]);
const codes = [...(/var CODE_LB = \{([\s\S]*?)\};/.exec(MOD) || [])[1].matchAll(/(\w+):\s*"rp\./g)].map((m) => m[1]);
check("bảng mã im có đủ mã bộ máy phát ra", ["no_signal", "junk", "addressed_other", "no_grounding", "rate_limited", "rate_limited_user",
  "just_spoke", "policy_error", "owner_typing", "judge_silent", "below_threshold", "agent_silent", "taken_over"].every((c) => codes.indexOf(c) >= 0), codes.join(","));
check("không dùng em dash trong module và test", ![MOD, fs.readFileSync(__filename, "utf8")].some((t) => t.indexOf(String.fromCharCode(0x2014)) >= 0));

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_reply_policy_ui: tất cả pass");
