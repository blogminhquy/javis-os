/* Thẻ Giọng nói gọn (0.65.19, docs/dev/2026-10-voice-call-spec.md mục 5).

   Bấm mic là gọi Javis, nên trang Cài đặt chỉ còn: dòng "Đang dùng", Giọng Javis (danh sách đổi
   theo đường gọi); Nâng cao có Đường gọi, Bộ não trả lời nhanh (trả lại ở 0.65.25), Tốc độ đọc,
   ElevenLabs. Mọi ô tự lưu, không còn nút Lưu. Phần máy tự lo (ngôn ngữ nghe, im lặng rồi gửi,
   ngắt lời, nhịp hội thoại, tai nghe lại, đọc trả lời bằng giọng, key OpenAI) không còn ô nhập.

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
for (const id of ["vcNow", "vcVoice", "vcTry", "vcAdvanced", "vcEngine", "vcBrainBox", "vcBrain", "vcBrainModelRow", "vcBrainModel", "rateSel", "vcEleven", "vcElKey", "vcElVoice", "vcReadRow", "vcReadVoice", "vcReadTry", "vcElVoiceSel", "vcElModel", "vcStatus", "v2LastErr", "voiceSel"])
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
check("0.65.22: công tắc Tập trung đã gỡ (im 30 giây thì ngắt, nói là nối lại)", !card.includes('id="vcFocus"') && !/vcFocus/.test(cs));
for (const k of ["settings.vc_title", "settings.vc_voice", "settings.vc_advanced",
  "settings.vc_engine", "settings.vc_engine_auto", "settings.vc_engine_api", "settings.vc_engine_basic", "settings.vc_hear_call", "settings.vc_hear_read", "settings.vc_hear_basic",
  "settings.vc_now_brain", "settings.vc_reason_auto_api", "settings.vc_reason_auto_basic", "settings.vc_reason_chosen_unavailable",
  "settings.vc_detail_no_cli", "settings.vc_detail_no_login", "settings.vc_detail_old_cli", "settings.vc_saved",
  "settings.vc_group_edge", "settings.vc_eleven_opt", "settings.vc_read_voice", "settings.vc_read_info", "settings.vc_el_info",
  "settings.vc_el_voice", "settings.vc_el_mine", "settings.vc_el_premade", "settings.vc_el_loading", "settings.vc_el_load_fail",
  "settings.vc_el_custom", "settings.vc_el_model", "settings.vc_el_model_flash", "settings.vc_el_model_v3", "settings.vc_el_model_turbo",
  "settings.vc_el_model_v2", "settings.vc_openai_note", "settings.v2_last_error",
  "settings.vc_brain", "settings.vc_brain_hint", "settings.vc_brain_auto", "settings.vc_brain_auto_pick",
  "settings.vc_brain_main", "settings.vc_brain_unavailable", "settings.vc_brain_model", "settings.vc_brain_model_default",
  "settings.vc_brain_model_default_named", "settings.vc_brain_model_missing", "settings.vc_brain_model_loading"])
  check(`i18n vi+en có ${k}`, typeof vi[k] === "string" && typeof en[k] === "string");
check("câu lỗi làn nhanh không còn bảo chọn bộ não khác rồi Lưu", !/rồi Lưu/.test(vi["settings.v2_last_error"]));

// ---- 3. Chạy renderVoiceCard() thật trên DOM giả ----
const start = cs.indexOf("  const OPENAI_TTS_VOICES");
const end = cs.indexOf("\n  }\n", cs.indexOf("async function renderVoiceCard()")) + 4;
const src = cs.slice(start, end);

class El {
  constructor(id) { this.id = id; this.hidden = false; this.value = ""; this.checked = false; this.open = false; this.textContent = ""; this._html = ""; this.options = []; this.focused = false; this.events = [];
    const cls = new Set();
    this.classList = { add: (c) => cls.add(c), remove: (c) => cls.delete(c), contains: (c) => cls.has(c),
                       toggle: (c, on) => (on === undefined ? (cls.has(c) ? cls.delete(c) : cls.add(c)) : on ? cls.add(c) : cls.delete(c)) }; }
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

async function run(options, edgeVoice = "vi-VN-HoaiMyNeural", models = null) {
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
    // /voice/brain-models trả danh sách model của một bộ não (0.65.26), mọi URL khác là /voice/options.
    fetch: async (url) => ({ json: async () => {
      ctx.urls.push(url);
      if (url.startsWith("/voice/brain-models")) return models || { ok: true, models: [] };
      if (url.startsWith("/voice/elevenlabs/voices")) return ctx.elVoices || { ok: false, error: "no key" };
      ctx.lastUrl = url;
      return options;
    } }), urls: [],
    saveSetting: async (section, data) => { saves.push([section, data]); return { ok: true }; },
    window: { JavisVoiceMode: { refresh: () => refreshes.push(1) }, JavisVoiceCatalog: require("../../dashboard/voice-catalog.js") },
    setTimeout: () => 0, clearTimeout: () => {}, Event: class { constructor(type) { this.type = type; } },
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
  // 0.298.0: the top lines say what you will hear: the call path and its voice, then the reading voice.
  check("ChatGPT Live: dòng nghe ghi đường gọi kèm giọng (nam/nữ) và giọng đọc",
    $("vcNow").innerHTML.includes('settings.vc_hear_call{"engine":"ChatGPT Live","voice":"Juniper · settings.vc_g_f"}')
    && $("vcNow").innerHTML.includes("settings.vc_hear_read"));
  check("ChatGPT Live: ô giọng là giọng của gói, chọn sẵn juniper", $("vcVoice").options.length === 3 && $("vcVoice").value === "juniper");
  check("ChatGPT Live: tốc độ đọc ẩn (chỉ đường Cơ bản)", $("vcRateRow").hidden === true);
  check("ChatGPT Live: Đường gọi hiện Tự động", $("vcEngine").value === "auto");
  $("vcVoice").value = "maple"; await $("vcVoice").onchange();
  check("ChatGPT Live: đổi giọng tự lưu chatgpt_voice", JSON.stringify(r.saves.at(-1)) === '["voice",{"chatgpt_voice":"maple"}]');
  check("tự lưu xong thì đường gọi của nút mic nạp lại", r.refreshes.length === 1 && $("vcStatus").textContent === "settings.vc_saved");
  $("vcTry").onclick();
  check("ChatGPT Live: Nghe thử phát mẫu thu sẵn", r.ctx.played === "/static/voices/maple.mp3");
  $("vcEngine").value = "basic"; await $("vcEngine").onchange();
  check("Đường gọi: đổi là tự lưu call_engine", r.saves.some(s => s[1].call_engine === "basic"));

  // 3b. Live qua API, rơi xuống vì chưa nối ChatGPT: giọng của nhà cung cấp, không có nghe thử.
  r = await run(base({ engine: "api", live_provider: "gemini", setting: "auto", reason: "auto_api", detail: "no_login" },
    { voice: { focus_mode: false, live_voice: "Kore" } }));
  const now = r.els.vcNow.innerHTML;
  check("Live API: dòng Đang dùng ghi tên nhà cung cấp, lý do rơi xuống và cách bật ChatGPT Live",
    now.includes('call.engine_api{\\"provider\\":\\"Gemini\\"}') && now.includes("settings.vc_reason_auto_api") && now.includes("settings.vc_detail_no_login"));
  check("Live API: ô giọng là giọng Gemini, giữ giọng đã lưu", r.els.vcVoice.options.length === 2 && r.els.vcVoice.value === "Kore");
  check("Live API: không có nút nghe thử", r.els.vcTry.hidden === true);
  r.els.vcVoice.value = "Puck"; await r.els.vcVoice.onchange();
  check("Live API: đổi giọng tự lưu live_voice", JSON.stringify(r.saves.at(-1)) === '["voice",{"live_voice":"Puck"}]');

  // 3c. Cơ bản: giọng Edge (+ OpenAI khi có key) + ElevenLabs; chọn giọng là chọn nhà cung cấp.
  r = await run(base({ engine: "basic", live_provider: "", setting: "basic", reason: "chosen", detail: "no_cli" },
    { voice_brain: { id: "antigravity", label: "Antigravity" }, last_error: { error: "hết hạn mức", label: "Antigravity", at: Date.now() / 1000 } }));
  const b = r.els;
  check("Cơ bản: Đang dùng kèm bộ não trả lời nhanh, không nhắc ChatGPT Live khi đã chọn Cơ bản",
    b.vcNow.innerHTML.includes("settings.vc_now_brain") && !b.vcNow.innerHTML.includes("vc_detail"));
  check("Cơ bản: giọng Edge đang dùng được chọn sẵn", b.vcVoice.value === "edge:vi-VN-HoaiMyNeural");
  check("Cơ bản: chưa có key OpenAI thì không có giọng OpenAI, có lời nhắc trang Models",
    !b.vcVoice.options.some(o => o.value.startsWith("openai:")) && b.vcOpenaiNote.hidden === false);
  check("Cơ bản: có giọng ElevenLabs riêng", b.vcVoice.options.some(o => o.value === "elevenlabs"));
  check("Cơ bản: tốc độ đọc hiện", b.vcRateRow.hidden === false);
  check("lỗi làn nhanh gần nhất hiện ra", b.v2LastErr.hidden === false && b.v2LastErr.innerHTML.includes("settings.v2_last_error"));
  b.vcVoice.value = "edge:en-US-EmmaMultilingualNeural"; await b.vcVoice.onchange();
  check("Cơ bản: đổi giọng Edge ghi vào kho #voiceSel (app.js lưu localStorage)",
    b.voiceSel.value === "en-US-EmmaMultilingualNeural" && b.voiceSel.events.includes("change"));
  // 0.298.0: the Edge voice is saved on the server too, so the phone and voice notes use the same voice.
  check("Cơ bản: giọng Edge cũng lưu lên máy chủ", JSON.stringify(r.saves.at(-1)) === '["voice",{"tts_provider":"edge","edge_voice":"en-US-EmmaMultilingualNeural"}]');
  b.vcVoice.value = "elevenlabs"; await b.vcVoice.onchange();
  // 0.255.0: the ElevenLabs block sits right under the list, out of Advanced.
  check("Cơ bản: chọn ElevenLabs là lưu tts_provider, hiện khối ElevenLabs ngay dưới, trỏ vào ô key",
    JSON.stringify(r.saves.at(-1)) === '["voice",{"tts_provider":"elevenlabs"}]' && !(b.vcAdvanced && b.vcAdvanced.open) && b.vcEleven.hidden === false && b.vcElKey.focused);
  b.vcElKey.value = " sk_test "; await b.vcElKey.onchange();
  check("ElevenLabs: key mới tự lưu rồi xoá khỏi ô", JSON.stringify(r.saves.at(-1)) === '["voice",{"elevenlabs_key":"sk_test"}]' && b.vcElKey.value === "");
  const n = r.saves.length; b.vcElKey.value = ""; await b.vcElKey.onchange();
  check("ElevenLabs: ô key để trống thì không gửi gì (giữ key cũ)", r.saves.length === n);

  r = await run(base({ engine: "basic", live_provider: "", setting: "auto", reason: "auto_basic", detail: "no_cli" },
    { tts: { provider: "openai", openai_voice: "nova", openai_key_set: true, elevenlabs_voice: "", elevenlabs_key_set: false } }));
  check("Cơ bản tự rơi xuống: nói lý do và cách bật ChatGPT Live",
    r.els.vcNow.innerHTML.includes("settings.vc_reason_auto_basic") && r.els.vcNow.innerHTML.includes("settings.vc_detail_no_cli"));
  check("Cơ bản + OpenAI: giọng OpenAI đang dùng được chọn sẵn", r.els.vcVoice.value === "openai:nova" && r.els.vcOpenaiNote.hidden === true);
  r.els.vcVoice.value = "openai:coral"; await r.els.vcVoice.onchange();
  check("Cơ bản + OpenAI: đổi giọng lưu cả nhà cung cấp lẫn giọng",
    JSON.stringify(r.saves.at(-1)) === '["voice",{"tts_provider":"openai","openai_tts_voice":"coral"}]');

  // 3c2. 0.255.0 (owner: "đang thiếu ElevenLabs"): on ChatGPT Live the reading voice gets its own row.
  const settle0 = () => new Promise(res => setImmediate(res));
  r = await run(base({ engine: "chatgpt", live_provider: "chatgpt", setting: "auto", reason: "auto", detail: "" },
    { tts: { provider: "edge", openai_voice: "alloy", openai_key_set: false, elevenlabs_voice: "", elevenlabs_key_set: false,
      elevenlabs_model: "", elevenlabs_models: [{ id: "eleven_flash_v2_5", vi: true }, { id: "eleven_multilingual_v2", vi: false }] } }));
  const c = r.els;
  check("ChatGPT Live: row Giọng đọc tin nhắn shows with Edge and ElevenLabs, live voices stay above",
    c.vcReadRow.hidden === false && c.vcReadVoice.options.some(o => o.value === "elevenlabs")
    && c.vcReadVoice.value === "edge:vi-VN-HoaiMyNeural" && c.vcVoice.value === "juniper");
  check("ChatGPT Live: the Edge note about multilingual voices stays hidden", c.vcVoiceNote.hidden === true);
  check("ElevenLabs model list: Flash v2.5 first and picked when nothing is saved",
    c.vcElModel.value === "eleven_flash_v2_5" && c.vcElModel.options[0].textContent === "settings.vc_el_model_flash"
    && c.vcElModel.options[1].textContent === "settings.vc_el_model_v2");
  c.vcReadVoice.value = "elevenlabs"; await c.vcReadVoice.onchange();
  check("ChatGPT Live: picking ElevenLabs as reading voice saves tts_provider, not chatgpt_voice, shows the block",
    JSON.stringify(r.saves.at(-1)) === '["voice",{"tts_provider":"elevenlabs"}]' && c.vcEleven.hidden === false && c.vcElKey.focused);
  r.ctx.elVoices = { ok: true, voices: [{ id: "mine1", name: "Quy clone", category: "cloned", gender: "", accent: "" },
    { id: "21m00", name: "Rachel", category: "premade", gender: "female", accent: "american" }] };
  c.vcElKey.value = "sk_x"; await c.vcElKey.onchange(); await settle0(); await settle0();
  check("ElevenLabs: after the key is saved the account's voices load by name, own voices first",
    r.ctx.urls.includes("/voice/elevenlabs/voices") && c.vcElVoiceSel.hidden === false && c.vcElVoice.hidden === true
    && c.vcElVoiceSel.options.map(o => o.value).join() === "mine1,21m00" && c.vcElVoiceSel.options[1].textContent === "Rachel · female, american");
  c.vcElVoiceSel.value = "21m00"; await c.vcElVoiceSel.onchange();
  check("ElevenLabs: picking a voice saves its id", JSON.stringify(r.saves.at(-1)) === '["voice",{"elevenlabs_voice":"21m00"}]');
  c.vcElModel.value = "eleven_v3"; await c.vcElModel.onchange();
  check("ElevenLabs: picking a model saves it", JSON.stringify(r.saves.at(-1)) === '["voice",{"elevenlabs_model":"eleven_v3"}]');
  r = await run(base({ engine: "basic", live_provider: "", setting: "basic", reason: "chosen", detail: "" },
    { tts: { provider: "elevenlabs", openai_voice: "alloy", openai_key_set: false, elevenlabs_voice: "oldid", elevenlabs_key_set: true,
      elevenlabs_model: "eleven_multilingual_v2", elevenlabs_models: [{ id: "eleven_flash_v2_5", vi: true }, { id: "eleven_multilingual_v2", vi: false }] } }));
  await settle0(); await settle0();
  check("Basic: no separate reading row, ElevenLabs block open, list failure falls back to the Voice ID box",
    r.els.vcReadRow.hidden === true && r.els.vcEleven.hidden === false && r.els.vcElVoiceSel.hidden === true
    && r.els.vcElVoice.hidden === false && r.els.vcElVoice.value === "oldid" && r.els.vcElVoiceMsg.textContent === "no key");
  check("Basic: a saved Multilingual v2 is shown as saved", r.els.vcElModel.value === "eleven_multilingual_v2");

  // 3f. 0.298.0 (owner 23/10: "cài đặt là nữ nhưng khi nói là giọng nói nam"): live voices carry male/female,
  // grouped; a call voice of the other gender than the reading voice is flagged with a one-click fix.
  r = await run(base({ engine: "chatgpt", live_provider: "chatgpt", setting: "auto", reason: "auto", detail: "" }, { chatgpt_voice: "cove" }));
  const m = r.els;
  check("0.298.0: live voices grouped female first, each labelled",
    m.vcVoice.innerHTML.indexOf("settings.vc_grp_f") > -1 && m.vcVoice.innerHTML.indexOf("settings.vc_grp_f") < m.vcVoice.innerHTML.indexOf("settings.vc_grp_m")
    && m.vcVoice.options.some(o => o.textContent === "Cove · settings.vc_g_m"));
  check("0.298.0: the first row is named the call voice on ChatGPT Live", m.vcVoiceLbl.textContent === "settings.vc_voice_call");
  check("0.298.0: male call voice with a female reading voice is flagged",
    m.vcMismatch.hidden === false && m.vcMismatchFix.textContent === 'settings.vc_mismatch_fix{"voice":"Juniper · settings.vc_g_f"}');
  m.vcMismatchFix.onclick(); await settle0();
  check("0.298.0: one click picks a female call voice, saves it and clears the warning",
    JSON.stringify(r.saves.at(-1)) === '["voice",{"chatgpt_voice":"juniper"}]' && m.vcMismatch.hidden === true);
  check("0.298.0: 'saved' shows right beside the field that changed", m.vcVoiceSaved.classList.contains("on") && m.vcVoiceSaved.textContent.includes("settings.vc_saved_short"));
  m.vcReadVoice.value = "edge:en-US-EmmaMultilingualNeural"; await m.vcReadVoice.onchange();
  check("0.298.0: reading voice saved on the server with its own 'saved' mark",
    JSON.stringify(r.saves.at(-1)) === '["voice",{"tts_provider":"edge","edge_voice":"en-US-EmmaMultilingualNeural"}]' && m.vcReadSaved.classList.contains("on"));
  r = await run(base({ engine: "basic", live_provider: "", setting: "basic", reason: "chosen", detail: "" },
    { tts: { provider: "edge", edge_voice: "en-US-EmmaMultilingualNeural", openai_voice: "alloy", openai_key_set: false, elevenlabs_voice: "", elevenlabs_key_set: false } }));
  check("0.298.0: the Edge voice saved on the server wins over this browser's copy",
    r.els.vcVoice.value === "edge:en-US-EmmaMultilingualNeural" && r.els.vcMismatch.hidden === true
    && r.els.vcVoiceLbl.textContent === "settings.vc_voice" && r.els.vcNow.innerHTML.includes("settings.vc_hear_basic"));

  // 3d. Bộ não trả lời nhanh (0.65.25, chủ dự án xin trả lại ô này để tự chỉnh).
  const CHOICES = [{ id: "antigravity", label: "Antigravity", available: false },
    { id: "codex", label: "ChatGPT", available: true }, { id: "groq", label: "Groq", available: false }];
  r = await run(base({ engine: "chatgpt", live_provider: "chatgpt", setting: "auto", reason: "auto", detail: "" },
    { brain_choices: CHOICES, brain_auto: "codex", voice: { mode: "fast", brain_provider: "" } }));
  const br = r.els.vcBrain;
  // 0.65.31: đường đang dùng là ChatGPT Live thì cả khối bộ não + Model ẩn, không tải danh sách model.
  check("ChatGPT Live: khối Bộ não trả lời nhanh ẩn, không tải danh sách model",
    r.els.vcBrainBox.hidden === true && !r.ctx.urls.some(u => u.startsWith("/voice/brain-models")));
  check("Bộ não: Tự động ghi bộ não máy đang chọn, được chọn sẵn",
    br.value === "auto" && br.options[0].textContent === 'settings.vc_brain_auto_pick{"brain":"ChatGPT"}');
  check("Bộ não: có Bộ não chính và đủ các bộ não, cái chưa sẵn được đánh dấu",
    br.options.map(o => o.value).join() === "auto,main,antigravity,codex,groq"
    && br.options[2].textContent === 'settings.vc_brain_unavailable{"brain":"Antigravity"}' && br.options[3].textContent === "ChatGPT");
  br.value = "codex"; await br.onchange();
  check("Bộ não: chọn một bộ não là lưu làn nhanh với bộ não đó",
    JSON.stringify(r.saves.at(-1)) === '["voice",{"mode":"fast","brain_provider":"codex"}]');
  br.value = "main"; await br.onchange();
  check("Bộ não: chọn Bộ não chính là lưu chế độ Chuẩn",
    JSON.stringify(r.saves.at(-1)) === '["voice",{"mode":"standard","brain_provider":""}]');
  br.value = "auto"; await br.onchange();
  check("Bộ não: chọn Tự động là xoá bộ não đã chọn",
    JSON.stringify(r.saves.at(-1)) === '["voice",{"mode":"fast","brain_provider":""}]');
  r = await run(base({ engine: "basic", live_provider: "", setting: "basic", reason: "chosen", detail: "" },
    { brain_choices: CHOICES, brain_auto: "", voice: { mode: "standard", brain_provider: "codex" } }));
  check("Cơ bản: khối Bộ não trả lời nhanh hiện", r.els.vcBrainBox.hidden === false);
  check("basic path: the Live-only box stays hidden", r.els.vcLiveBox.hidden === true);
  check("Bộ não: chế độ Chuẩn đã lưu hiện Bộ não chính; không gói nào sẵn thì Tự động không kèm tên",
    r.els.vcBrain.value === "main" && r.els.vcBrain.options[0].textContent === "settings.vc_brain_auto");
  r = await run(base({ engine: "basic", live_provider: "", setting: "basic", reason: "chosen", detail: "" },
    { brain_choices: CHOICES, brain_auto: "codex", voice: { mode: "fast", brain_provider: "groq" } }));
  check("Bộ não: bộ não chọn tay từ bản cũ được giữ", r.els.vcBrain.value === "groq");
  r = await run(base({ engine: "api", live_provider: "gemini", setting: "auto", reason: "auto_api", detail: "no_login" },
    { brain_choices: CHOICES, brain_auto: "codex", voice: { mode: "fast", brain_provider: "codex", live_voice: "Kore" } }));
  check("Live qua API: khối Bộ não trả lời nhanh cũng ẩn", r.els.vcBrainBox.hidden === true);
  check("Live over an API key: TV filter and reply pace show, defaults on/normal",
    r.els.vcLiveBox.hidden === false && r.els.vcLiveProactive.value === "on" && r.els.vcLiveTurn.value === "normal");
  r.els.vcLiveTurn.value = "fast"; await r.els.vcLiveTurn.onchange();
  check("reply pace saves live_turn", JSON.stringify(r.saves.at(-1)) === '["voice",{"live_turn":"fast"}]');
  r.els.vcLiveProactive.value = "off"; await r.els.vcLiveProactive.onchange();
  check("TV filter saves live_proactive", JSON.stringify(r.saves.at(-1)) === '["voice",{"live_proactive":false}]');
  r = await run(base({ engine: "basic", live_provider: "", setting: "auto", reason: "auto_basic", detail: "no_cli" },
    { brain_choices: CHOICES, brain_auto: "codex", voice: { mode: "fast", brain_provider: "" } }));
  check("Tự động mà đang rơi xuống Cơ bản: khối Bộ não trả lời nhanh hiện (nó đang được dùng thật)",
    r.els.vcBrainBox.hidden === false);

  // 3e. Model của bộ não (0.65.26): mỗi bộ não nhớ model riêng, danh sách tải riêng cho đúng bộ não.
  const settle = () => new Promise(res => setImmediate(res));
  const MODELS = { ok: true, models: [{ id: "gpt-a", label: "GPT A" }, { id: "gpt-b", label: "GPT B" }] };
  r = await run(base({ engine: "basic", live_provider: "", setting: "basic", reason: "chosen", detail: "" },
    { brain_choices: CHOICES, brain_auto: "codex", voice: { mode: "fast", brain_provider: "", brain_models: { codex: "gpt-b", groq: "llama" } } }),
    undefined, MODELS);
  await settle(); await settle();
  const ms = r.els.vcBrainModel;
  check("Model: Tự động thì chỉnh model của bộ não máy đang chọn, tải đúng danh sách của nó",
    r.els.vcBrainModelRow.hidden === false && r.ctx.urls.includes("/voice/brain-models?provider=codex"));
  check("Model: có Mặc định rồi đủ danh sách, model đã lưu được chọn sẵn",
    ms.options.map(o => o.value).join() === ",gpt-a,gpt-b" && ms.value === "gpt-b"
    && ms.options[0].textContent === "settings.vc_brain_model_default");
  ms.value = "gpt-a"; await ms.onchange();
  check("Model: đổi model là lưu kèm tên bộ não",
    JSON.stringify(r.saves.at(-1)) === '["voice",{"brain_model_for":"codex","brain_model":"gpt-a"}]');
  ms.value = ""; await ms.onchange();
  check("Model: chọn Mặc định là lưu chuỗi rỗng cho bộ não đó",
    JSON.stringify(r.saves.at(-1)) === '["voice",{"brain_model_for":"codex","brain_model":""}]');
  r = await run(base({ engine: "basic", live_provider: "", setting: "basic", reason: "chosen", detail: "" },
    { brain_choices: [{ id: "claude", label: "Claude", available: true, default_model: "haiku" }], brain_auto: "",
      voice: { mode: "fast", brain_provider: "claude", brain_models: { claude: "opus-cu" } } }),
    undefined, { ok: true, models: [{ id: "sonnet", label: "Sonnet" }] });
  await settle(); await settle();
  const mc = r.els.vcBrainModel;
  check("Model: Mặc định ghi tên model mặc định của hãng",
    mc.options[0].textContent === 'settings.vc_brain_model_default_named{"model":"haiku"}');
  check("Model: model đã lưu mà danh sách không còn vẫn hiện, được đánh dấu",
    mc.value === "opus-cu" && mc.options[1].textContent === 'settings.vc_brain_model_missing{"model":"opus-cu"}');
  r = await run(base({ engine: "basic", live_provider: "", setting: "basic", reason: "chosen", detail: "" },
    { brain_choices: CHOICES, brain_auto: "codex", voice: { mode: "standard", brain_provider: "" } }), undefined, MODELS);
  await settle();
  check("Model: Bộ não chính thì ẩn ô Model và không tải danh sách",
    r.els.vcBrainModelRow.hidden === true && !r.ctx.urls.some(u => u.startsWith("/voice/brain-models")));

  if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
  console.log("\nOK - thẻ Giọng nói gọn");
})().catch(e => { console.error(e); process.exit(1); });
