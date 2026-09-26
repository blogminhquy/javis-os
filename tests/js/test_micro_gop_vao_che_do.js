/* Thẻ "Chế độ nói chuyện" GỘP ba mục micro (ngôn ngữ nghe, im lặng rồi gửi, ngắt lời) và nút
   Lưu chế độ đứng dưới cùng thẻ (chủ dự án chốt 17/09). Kèm ba mặc định mới: chế độ Làn nhanh,
   im lặng rồi gửi 1,2 giây, và lựa chọn "Đa ngôn ngữ" cho ngôn ngữ nghe.

   Ba mục micro là node TĨNH (app.js gắn tay bắt một lần lúc tải trang) nên console.js phải DỜI
   node vào thẻ chứ không vẽ lại, và phải trả node về nhà trước khi ghi đè host - thiếu bước đó
   thì lần vẽ lại thứ hai xoá sạch ba ô.

   Chạy: node tests/js/test_micro_gop_vao_che_do.js
   Ghi chú: KHÔNG dùng ký tự em dash. */
"use strict";
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "..");
const doc = (p) => fs.readFileSync(path.join(root, p), "utf8");
const html = doc("dashboard/index.html");
const cs = doc("dashboard/console.js");
const app = doc("dashboard/app.js");
const voice = doc("dashboard/voice.js");
const css = doc("dashboard/style.css");
const main = doc("server/main.py");
const cfg = doc("server/config.py");
const vi = JSON.parse(doc("dashboard/i18n/vi.json"));
const en = JSON.parse(doc("dashboard/i18n/en.json"));

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- 1. index.html: ba mục micro có nhà riêng và mang đúng id để console.js dời ----
check("index.html: có nhà #qsMicHome (là .qs-block để đứng một mình vẫn ra thẻ) bọc #qsMicFields",
  /<div class="qs-block" id="qsMicHome"[^>]*>\s*<div id="qsMicFields">/.test(html));
check("index.html: nhãn MICRO là tiêu đề PHỤ (.qs-sub) trong thẻ, không còn là nhãn thẻ riêng",
  /<div class="qs-sub" data-i18n="qs.mic">/.test(html) && !/<div class="popover-label" data-i18n="qs.mic">/.test(html));
check("index.html: ba ô vẫn giữ id cũ để app.js gắn tay bắt",
  /id="recLangSel"/.test(html) && /id="endpointSel"/.test(html) && /id="qsBarge"/.test(html));
check("index.html: ngôn ngữ nghe có lựa chọn Đa ngôn ngữ (value=auto) kèm câu nói thật về hai máy nghe",
  /<option value="auto" data-i18n="qs.rec_auto_opt">/.test(html) && /data-i18n="qs.rec_auto_hint"/.test(html));
check("index.html: nhãn (mặc định) chuyển từ 0,8 giây sang 1,2 giây",
  /value="1200" data-i18n="qs.endpoint_slow_opt">[^<]*mặc định/.test(html)
  && !/value="800" data-i18n="qs.endpoint_mid_opt">[^<]*mặc định/.test(html));

// ---- 2. console.js: dời node vào thẻ, trả về nhà trước khi vẽ lại ----
const iCard = cs.indexOf("async function renderVoiceV2Card()");
const card = cs.slice(iCard, iCard + 9000);
check("console.js: trả micro về nhà TRƯỚC khi host.innerHTML ghi đè",
  card.indexOf("traMicVeNha();") > 0 && card.indexOf("traMicVeNha();") < card.indexOf("host.innerHTML ="));
check("console.js: ghép micro vào thẻ vào Nâng cao trước điểm neo",
  /gheMicVaoThe\(host\.querySelector\("#v2AdvancedEnd"\)\);/.test(card));
check("console.js: ghép bằng insertBefore vào cha của điểm neo và ẩn nhà cũ",
  /truoc\.parentNode\.insertBefore\(micFields, truoc\)/.test(card) && /micHome\.hidden = true/.test(card));
check("console.js: máy chủ cũ (không đọc được /voice/options) vẫn hiện ba mục micro",
  /settings\.v2_load_fail[\s\S]{0,200}gheMicVaoThe\(null\)/.test(card));
check("console.js: chế độ mặc định trên màn hình là Làn nhanh",
  /const cheDo = v\.mode \|\| "fast";/.test(card) && /optA\("fast", t\("settings\.v2_mode_fast"\), cheDo\)/.test(card));
check("console.js: Làn nhanh chưa có bộ não thì gợi sẵn bộ não ĐANG SẴN đầu tiên",
  /find\(p => p\.id && p\.available\)/.test(card) && /naoChon, !p\.available && p\.id !== ""/.test(card));

// ---- 3. app.js: mặc định im lặng rồi gửi = 1,2 giây ở CẢ HAI chỗ đọc khoá ----
check("app.js: khởi tạo VoiceTurn mặc định 1200",
  /minDelay: parseInt\(localStorage\.getItem\("javis\.endpoint"\) \|\| "1200", 10\) \|\| 1200,/.test(app));
check("app.js: ô chọn trong Cài đặt mặc định 1200",
  /const ep = localStorage\.getItem\("javis\.endpoint"\) \|\| "1200";/.test(app)
  && /if \(!epSel\.value\) epSel\.value = "1200";/.test(app)
  && (app.match(/parseInt\(epSel\.value, 10\) \|\| 1200;/g) || []).length === 2);
check("CANARY: không còn sót mặc định 800 nào", !/\|\| "800"/.test(app) && !/\|\| 800[;,]/.test(app));

// ---- 4. voice.js + main.py: "auto" đi đúng hai đường nghe ----
check("voice.js: setRecognitionLang('auto') bật langAuto và KHÔNG ghi đè this.lang (phần đọc còn giọng Việt)",
  /this\.langAuto = lang === "auto";\s*\n\s*if \(!this\.langAuto\) this\.lang = lang;/.test(voice));
check("voice.js: máy nghe trình duyệt giữ tiếng Việt dự phòng khi Groq tự dò",
  (voice.match(/this\.recognition\.lang = this\.lang;/g) || []).length >= 2);
// Real FormData language snapshot is tested in test_voice_capture_lifecycle.js.
check("main.py: /stt đổi 'auto' thành '' (Whisper tự dò), rỗng vẫn về None (mặc định vi)",
  /ngon_ngu = "" if lang\.lower\(\) == "auto" else \(lang\.split\("-"\)\[0\]\.strip\(\) or None\)/.test(main));

// ---- 5. config.py: mặc định Làn nhanh ----
check("config.py: voice.mode mặc định là fast", /"mode": "fast",/.test(cfg) && !/"mode": "standard",\s*#/.test(cfg));

// ---- 6. từ điển + css ----
["qs.rec_auto_opt", "qs.rec_auto_hint", "qs.mic_local", "qs.endpoint_slow_opt", "cs.ov_auto_btn_fix"].forEach(k => {
  check("i18n vi+en có " + k, typeof vi[k] === "string" && typeof en[k] === "string");
});
check("i18n: (mặc định) nằm ở 1,2 giây, không ở 0,8 giây",
  /mặc định/.test(vi["qs.endpoint_slow_opt"]) && !/mặc định/.test(vi["qs.endpoint_mid_opt"])
  && /default/.test(en["qs.endpoint_slow_opt"]) && !/default/.test(en["qs.endpoint_mid_opt"]));
check("i18n: câu chú thích micro nói rõ nút Lưu chế độ không lưu ba mục này",
  /Lưu chế độ/.test(vi["qs.mic_local"]) && /Save mode/.test(en["qs.mic_local"]));
check("css: có lớp .qs-sub cho tiêu đề phụ trong thẻ", /\.qs-sub \{/.test(css));

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - micro gộp vào thẻ Chế độ nói chuyện");
