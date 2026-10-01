/* Thẻ Giọng nói gọn (0.65.19, docs/dev/2026-10-voice-call-spec.md mục 5).

   Bấm mic là gọi Javis, nên trang Cài đặt chỉ còn: dòng "Đang dùng", Giọng Javis (danh sách đổi
   theo đường gọi), Tập trung; Nâng cao có Đường gọi, Tốc độ đọc, ElevenLabs. Mọi ô tự lưu, không
   còn nút Lưu. Phần máy tự lo (ngôn ngữ nghe, im lặng rồi gửi, ngắt lời, nhịp hội thoại, tai nghe
   lại, bộ não giọng, đọc trả lời bằng giọng, key OpenAI) không còn ô nhập.

   Phần 1 soi khung tĩnh và dây nối; phần 2 CHẠY renderVoiceCard() thật trên DOM giả cho ba đường
   gọi và kiểm cái gì được lưu khi đổi từng ô.

   Chạy: node tests/js/test_voice_settings_simple.js
   Ghi chú: KHÔNG dùng ký tự em dash. */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.join(__dirname, "..", "..");
const doc = (p) => fs.readFileSync(path.join(root, p), "utf8");
const html = doc("dashboard/index.html");
const cs = doc("dashboard/console.js");
const app = doc("dashboard/app.js");
const vi = JSON.parse(doc("dashboard/i18n/vi.json"));
const en = JSON.parse(doc("dashboard/i18n/en.json"));

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- 1. Khung tĩnh: đúng ba ô và Nâng cao, các ô cũ đã gỡ hẳn (không chỉ ẩn) ----
const card = html.slice(html.indexOf('id="voiceCard"'), html.indexOf("<!-- THƯƠNG HIỆU."));
for (const id of ["vcNow", "vcVoice", "vcTry", "vcFocus", "vcAdvanced", "vcEngine", "rateSel", "vcEleven", "vcElKey", "vcElVoice", "vcStatus", "v2LastErr", "voiceSel"])
  check(`thẻ Giọng nói có #${id}`, card.includes(`id="${id}"`));
check("Đường gọi có đủ bốn lựa chọn", ["auto", "chatgpt", "api", "basic"].every(v => card.includes(`<option value="${v}"`)));
check("tên đường gọi viết ChatGPT Live, không có chữ song công", card.includes(">ChatGPT Live<") && !/song công/i.test(card + JSON.stringify(vi)));
for (const id of ["qsTts", "recLangSel", "endpointSel", "qsBarge", "adaptiveMode", "adaptivePace", "adaptiveReset", "adaptiveExport",
  "qsMicHome", "qsMicFields", "vpV2Host", "ttsProviderHost", "vpSave", "testVoiceBtn", "vpOaKey"])
  check(`ô cũ #${id} đã gỡ khỏi index.html`, !html.includes(`id="${id}"`));
check("không còn nút Lưu trong thẻ", !/<button[^>]*>[^<]*Lưu/.test(card));
check("kho giọng Edge #voiceSel ẩn và nằm trong thẻ", /<select id="voiceSel" name="voice" hidden/.test(card));

// ---- 2. Dây nối ----
check("console.js: thẻ đọc /voice/options?brains=0 (không chờ agy models)", /fetch\("\/voice\/options\?brains=0"/.test(cs));
check("console.js: mở tab Giọng nói là vẽ lại thẻ", /if \(tab === "voice"\) renderVoiceCard\(\);/.test(cs));
check("console.js: không còn hàm thẻ V2 cũ", !/renderVoiceV2Card/.test(cs));
check("app.js: ngôn ngữ nghe theo ngôn ngữ giao diện", /function recLangTheoGiaoDien\(\)/.test(app) && /const recNow = recLangTheoGiaoDien\(\);/.test(app));
check("app.js: đổi ngôn ngữ giao diện thì đổi ngôn ngữ nghe", /addEventListener\("javis:i18n", \(\) => \{\s*\n\s*const lang = recLangTheoGiaoDien\(\);/.test(app));
check("app.js: ngắt lời bằng giọng luôn bật", /voice\.bargeEnabled = true;/.test(app) && !/getItem\("javis\.bargeIn"\)/.test(app));
check("app.js: im lặng rồi gửi mặc định 1,2 giây, giữ mức cũ hợp lệ",
  /turn\.opts\.minDelay = \[500, 800, 1200\]\.includes\(ep\) \? ep : 1200;/.test(app)
  && /minDelay: parseInt\(localStorage\.getItem\("javis\.endpoint"\) \|\| "1200", 10\) \|\| 1200,/.test(app));
check("app.js: nút Nghe thử của đường Cơ bản đi qua window.JavisVoiceSample", /window\.JavisVoiceSample = \(\) => voice\.speak\(/.test(app));
for (const k of ["settings.vc_title", "settings.vc_voice", "settings.vc_focus", "settings.vc_focus_hint", "settings.vc_advanced",
  "settings.vc_engine", "settings.vc_engine_auto", "settings.vc_engine_api", "settings.vc_engine_basic", "settings.vc_now",
  "settings.vc_now_brain", "settings.vc_reason_auto_api", "settings.vc_reason_auto_basic", "settings.vc_reason_chosen_unavailable",
  "settings.vc_detail_no_cli", "settings.vc_detail_no_login", "settings.vc_detail_old_cli", "settings.vc_saved",
  "settings.vc_group_edge", "settings.vc_eleven_opt", "settings.vc_openai_note", "settings.v2_last_error"])
  check(`i18n vi+en có ${k}`, typeof vi[k] === "string" && typeof en[k] === "string");
check("câu lỗi làn nhanh không còn bảo chọn bộ não khác rồi Lưu", !/rồi Lưu/.test(vi["settings.v2_last_error"]));

// ---- 3. Chạy renderVoiceCard() thật trên DOM giả ----
const start = cs.indexOf("  const OPENAI_TTS_VOICES");
const end = cs.indexOf("\n  }\n", cs.indexOf("async function renderVoiceCard()")) + 4;
const src = cs.slice(start, end);

class El {
  constructor(id) { this.id = id; this.hidden = false; this.value = ""; this.checked = false; this.open = false; this.textContent = ""; this._html = ""; this.options = []; this.focused = false; this.events = []; }
  set innerHTML(v) {
    this._html = v;
    this.options = [...v.matchAll(/<option value="([^"]*)"( selected)?>([^<]*)<\/option>/g)].map(m => ({ value: m[1], selected: !!m[2], textContent: m[3] }));
    const sel = this.options.find(o => o.selected) || this.options[0];
    this.value = sel ? sel.value : "";
  }
  get innerHTML() { return this._html; }
  focus() { this.focused = true; }
  dispatchEvent(e) { this.events.push(e.type); }
}

async function run(options, edgeVoice = "vi-VN-HoaiMyNeural") {
  const els = {};
  const $ = (id) => els[id] || (els[id] = new El(id));
  $("voiceCard");
  const edge = $("voiceSel");
  edge.options = ["en-US-EmmaMultilingualNeural", "vi-VN-HoaiMyNeural"].map(v => ({ value: v, textContent: v }));
  edge.value = edgeVoice;
  const saves = [], refreshes = [];
  const ctx = {
    document: { getElementById: $ }, _renderGen: 0, _settings: {}, WARN_ICON: "!",
    esc: (s) => String(s), t: (k, p) => (p ? k + JSON.stringify(p) : k),
    fetch: async (url) => ({ json: async () => (ctx.lastUrl = url, options) }),
    saveSetting: async (section, data) => { saves.push([section, data]); return { ok: true }; },
    window: { JavisVoiceMode: { refresh: () => refreshes.push(1) } }, Event: class { constructor(type) { this.type = type; } },
    Audio: class { constructor(src) { ctx.played = src; } play() { return Promise.resolve(); } pause() {} },
    Date, Math, Number, Array, String, JSON, Promise,
  };
  vm.createContext(ctx);
  vm.runInContext(src + "\nthis.renderVoiceCard = renderVoiceCard;", ctx);
  await ctx.renderVoiceCard();
  return { ctx, els, saves, refreshes };
}
const LIVE = [
  { id: "chatgpt", voices: ["juniper", "maple", "cove"], default_voice: "juniper" },
  { id: "gemini", voices: ["Puck", "Kore"], default_voice: "Puck" },
];
const base = (call, extra = {}) => Object.assign({
  ok: true, call, live_providers: LIVE, chatgpt_voice: "juniper", voice: { focus_mode: true, live_voice: "" },
  tts: { provider: "edge", openai_voice: "alloy", openai_key_set: false, elevenlabs_voice: "", elevenlabs_key_set: false },
  voice_brain: { id: "", label: "" }, last_error: {},
}, extra);

(async () => {
  // 3a. ChatGPT Live: chín giọng của gói, nghe thử phát mẫu thu sẵn, đổi giọng lưu chatgpt_voice.
  let r = await run(base({ engine: "chatgpt", live_provider: "chatgpt", setting: "auto", reason: "auto", detail: "" }));
  const $ = (id) => r.els[id];
  check("ChatGPT Live: đọc options không kèm danh sách bộ não", r.ctx.lastUrl === "/voice/options?brains=0");
  check("ChatGPT Live: dòng Đang dùng ghi ChatGPT Live", $("vcNow").textContent === 'settings.vc_now{"engine":"ChatGPT Live"}');
  check("ChatGPT Live: ô giọng là giọng của gói, chọn sẵn juniper", $("vcVoice").options.length === 3 && $("vcVoice").value === "juniper");
  check("ChatGPT Live: tốc độ đọc ẩn (chỉ đường Cơ bản)", $("vcRateRow").hidden === true);
  check("ChatGPT Live: Đường gọi hiện Tự động", $("vcEngine").value === "auto");
  $("vcVoice").value = "maple"; await $("vcVoice").onchange();
  check("ChatGPT Live: đổi giọng tự lưu chatgpt_voice", JSON.stringify(r.saves.at(-1)) === '["voice",{"chatgpt_voice":"maple"}]');
  check("tự lưu xong thì đường gọi của nút mic nạp lại", r.refreshes.length === 1 && $("vcStatus").textContent === "settings.vc_saved");
  $("vcTry").onclick();
  check("ChatGPT Live: Nghe thử phát mẫu thu sẵn", r.ctx.played === "/static/voices/maple.mp3");
  $("vcFocus").checked = false; await $("vcFocus").onchange();
  check("Tập trung: tắt là tự lưu focus_mode false", JSON.stringify(r.saves.at(-1)) === '["voice",{"focus_mode":false}]');
  $("vcEngine").value = "basic"; await $("vcEngine").onchange();
  check("Đường gọi: đổi là tự lưu call_engine", r.saves.some(s => s[1].call_engine === "basic"));

  // 3b. Live qua API, rơi xuống vì chưa nối ChatGPT: giọng của nhà cung cấp, không có nghe thử.
  r = await run(base({ engine: "api", live_provider: "gemini", setting: "auto", reason: "auto_api", detail: "no_login" },
    { voice: { focus_mode: false, live_voice: "Kore" } }));
  const now = r.els.vcNow.textContent;
  check("Live API: dòng Đang dùng ghi tên nhà cung cấp, lý do rơi xuống và cách bật ChatGPT Live",
    now.includes('call.engine_api{\\"provider\\":\\"Gemini\\"}') && now.includes("settings.vc_reason_auto_api") && now.includes("settings.vc_detail_no_login"));
  check("Live API: ô giọng là giọng Gemini, giữ giọng đã lưu", r.els.vcVoice.options.length === 2 && r.els.vcVoice.value === "Kore");
  check("Live API: không có nút nghe thử", r.els.vcTry.hidden === true);
  check("Tập trung: đọc đúng giá trị đã lưu", r.els.vcFocus.checked === false);
  r.els.vcVoice.value = "Puck"; await r.els.vcVoice.onchange();
  check("Live API: đổi giọng tự lưu live_voice", JSON.stringify(r.saves.at(-1)) === '["voice",{"live_voice":"Puck"}]');

  // 3c. Cơ bản: giọng Edge (+ OpenAI khi có key) + ElevenLabs; chọn giọng là chọn nhà cung cấp.
  r = await run(base({ engine: "basic", live_provider: "", setting: "basic", reason: "chosen", detail: "no_cli" },
    { voice_brain: { id: "antigravity", label: "Antigravity" }, last_error: { error: "hết hạn mức", label: "Antigravity", at: Date.now() / 1000 } }));
  const b = r.els;
  check("Cơ bản: Đang dùng kèm bộ não trả lời nhanh, không nhắc ChatGPT Live khi đã chọn Cơ bản",
    b.vcNow.textContent.includes("settings.vc_now_brain") && !b.vcNow.textContent.includes("vc_detail"));
  check("Cơ bản: giọng Edge đang dùng được chọn sẵn", b.vcVoice.value === "edge:vi-VN-HoaiMyNeural");
  check("Cơ bản: chưa có key OpenAI thì không có giọng OpenAI, có lời nhắc trang Models",
    !b.vcVoice.options.some(o => o.value.startsWith("openai:")) && b.vcOpenaiNote.hidden === false);
  check("Cơ bản: có giọng ElevenLabs riêng", b.vcVoice.options.some(o => o.value === "elevenlabs"));
  check("Cơ bản: tốc độ đọc hiện", b.vcRateRow.hidden === false);
  check("lỗi làn nhanh gần nhất hiện ra", b.v2LastErr.hidden === false && b.v2LastErr.innerHTML.includes("settings.v2_last_error"));
  b.vcVoice.value = "edge:en-US-EmmaMultilingualNeural"; await b.vcVoice.onchange();
  check("Cơ bản: đổi giọng Edge ghi vào kho #voiceSel (app.js lưu localStorage)",
    b.voiceSel.value === "en-US-EmmaMultilingualNeural" && b.voiceSel.events.includes("change"));
  check("Cơ bản: Edge vẫn là nhà cung cấp thì không gửi gì lên máy chủ", r.saves.length === 0);
  b.vcVoice.value = "elevenlabs"; await b.vcVoice.onchange();
  check("Cơ bản: chọn ElevenLabs là lưu tts_provider và mở Nâng cao, trỏ vào ô key",
    JSON.stringify(r.saves.at(-1)) === '["voice",{"tts_provider":"elevenlabs"}]' && b.vcAdvanced.open && b.vcEleven.hidden === false && b.vcElKey.focused);
  b.vcElKey.value = " sk_test "; await b.vcElKey.onchange();
  check("ElevenLabs: key mới tự lưu rồi xoá khỏi ô", JSON.stringify(r.saves.at(-1)) === '["voice",{"elevenlabs_key":"sk_test"}]' && b.vcElKey.value === "");
  const n = r.saves.length; b.vcElKey.value = ""; await b.vcElKey.onchange();
  check("ElevenLabs: ô key để trống thì không gửi gì (giữ key cũ)", r.saves.length === n);

  r = await run(base({ engine: "basic", live_provider: "", setting: "auto", reason: "auto_basic", detail: "no_cli" },
    { tts: { provider: "openai", openai_voice: "nova", openai_key_set: true, elevenlabs_voice: "", elevenlabs_key_set: false } }));
  check("Cơ bản tự rơi xuống: nói lý do và cách bật ChatGPT Live",
    r.els.vcNow.textContent.includes("settings.vc_reason_auto_basic") && r.els.vcNow.textContent.includes("settings.vc_detail_no_cli"));
  check("Cơ bản + OpenAI: giọng OpenAI đang dùng được chọn sẵn", r.els.vcVoice.value === "openai:nova" && r.els.vcOpenaiNote.hidden === true);
  r.els.vcVoice.value = "openai:coral"; await r.els.vcVoice.onchange();
  check("Cơ bản + OpenAI: đổi giọng lưu cả nhà cung cấp lẫn giọng",
    JSON.stringify(r.saves.at(-1)) === '["voice",{"tts_provider":"openai","openai_tts_voice":"coral"}]');

  if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
  console.log("\nOK - thẻ Giọng nói gọn");
})().catch(e => { console.error(e); process.exit(1); });
