/* Orb chỉ hiện trạng thái THẬT, và voice.js chen ngang kiểu tạm dừng (Voice V1 spec mục 3.5, 4).

       node tests/js/test_orb_trang_thai_that.js

   Khoá dây nối giữa ba file, vì đây là chỗ hỏng LẶNG LẼ: quên một móc là orb nói dối (đứng
   "ĐANG NÓI" khi đã im, không bao giờ hiện "ĐANG KẾT NỐI LẠI"), không có lỗi nào trên console.
     1. app.js: mọi orb đi qua đạo diễn (không còn setOrbState("thinking"/"speaking") rải rác).
     2. app.js: mất WebSocket -> wsDown; hello -> wsUp; tool_call -> toolCall; turn_done -> turnDone.
     3. voice.js: chen ngang cần 5 nhịp (500 ms), tạm dừng qua onBargeStart chứ không giết ngay;
        pause/resume/lastSpokenPrefix có thật; isSpeaking() = false khi đang tạm dừng.
     4. index.html nạp voice-turn.js TRƯỚC voice.js; ui-context/ui-actions TRƯỚC app.js; có hai
        hàng cài đặt mới; từ điển có đủ nhãn orb ở cả vi lẫn en; CSS có lớp cho trạng thái mới. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const app = read("dashboard/app.js");
const voice = read("dashboard/voice.js");
const html = read("dashboard/index.html");
const css = read("dashboard/style.css");
const vi = JSON.parse(read("dashboard/i18n/vi.json"));
const en = JSON.parse(read("dashboard/i18n/en.json"));

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// 1. app.js đi qua đạo diễn
check("app.js dựng đạo diễn từ voice-turn.js", /new window\.JavisVoiceTurn\.VoiceTurn\(/.test(app));
check("app.js không còn setOrbState('thinking') rải rác", !/setOrbState\("thinking"/.test(app));
check("app.js không còn setOrbState('speaking') rải rác", !/setOrbState\("speaking"/.test(app));
check("app.js không còn setOrbState('', ready) rải rác", !/setOrbState\("", window\.t\("orb\.ready"\)\)/.test(app));
check("capNhatOrb là nơi duy nhất gọi setOrbState", (app.match(/setOrbState\(/g) || []).length === 2);   // định nghĩa + capNhatOrb

// 2. sự kiện thật
check("mất WS -> turn.wsDown", /ws\.onclose = \(\) => \{[^\n]*turn\.wsDown\(\)/.test(app));
check("hello -> turn.wsUp", /runActions\(turn\.wsUp\(\)\)/.test(app));
check("tool_call -> turn.toolCall(data.tool)", /turn\.toolCall\(data\.tool/.test(app));
check("turn_done -> turn.turnDone", /data\.type === "turn_done"[\s\S]{0,600}runActions\(turn\.turnDone\(\)\)/.test(app));
check("sendMessage -> turn.turnStart", /setSessionRunning\(sid, true\);\s*\n\s*runActions\(turn\.turnStart\(\)\);/.test(app));
check("tin nền: đọc ngay khi rảnh, hoãn khi bận", /turn\.canSpeakNow\(\)\) voice\.enqueueSpeak/.test(app) && /turn\.defer\(/.test(app));
check("nghe xong đi qua veTinTuGiong (luật CHỜ/DỪNG)", /text = veTinTuGiong\(text\);/.test(app));
check("stop_turn bấm hộ nút Dừng", /case "stop_turn": stopCurrent\(\)/.test(app));
check("pause_tts đặt đồng hồ chen ngang giả theo falseInterruptMs", /case "pause_tts":[\s\S]{0,300}turn\.opts\.falseInterruptMs/.test(app));
check("orb nhãn tool dùng app.orb_tool", /app\.orb_tool/.test(app));
check("dải việc nền báo số cho orb", /window\.JavisOrb\.setBackground/.test(read("dashboard/background-strip.js")));

// 3. voice.js
// 0.57.14: 2 nhịp = 200 ms là đủ để NGHI NGỜ, vì nghi ngờ chỉ dẫn tới một cú nhá tiếng 400 ms
// chứ không dừng hẳn nữa (test_ngat_loi_nha_tieng.js). Bản cũ phải để 5 nhịp vì chạm ngưỡng
// là câm luôn, và chính vì thế một tiếng "thôi" ngắn không bao giờ ngắt được lời Javis.
check("voice.js: 2 nhịp = 200 ms để nghi ngờ", /this\.bargeMinTicks = 2;/.test(voice) && /hits >= this\.bargeMinTicks/.test(voice));
check("voice.js: _bargeIn ưu tiên onBargeConfirm (đã chắc), rồi mới tới onBargeStart cũ",
  /_bargeIn\(\) \{\s*\n\s*if \(this\.onBargeConfirm\)/.test(voice) && /if \(this\.onBargeStart\)/.test(voice));
check("voice.js: có pauseSpeaking/resumeSpeaking", /pauseSpeaking\(\) \{/.test(voice) && /resumeSpeaking\(\) \{/.test(voice));
check("voice.js: isSpeaking() = false khi tạm dừng", /isSpeaking\(\) \{\s*\n\s*if \(this\._paused\) return false;/.test(voice));
check("voice.js: lastSpokenPrefix có thật", /lastSpokenPrefix\(\) \{/.test(voice) && /_spokenChunks\.push\(this\.ttsChunks\[i\]\)/.test(voice));
check("voice.js: độ trễ im lặng hỏi endpointDelay", /this\.endpointDelay\(display\)/.test(voice));
check("voice.js: startListening(tuDong, giuTieng) không giết tiếng khi giữ", /if \(!giuTieng\) \{ this\.synth\.cancel\(\); this\.stopSpeaking\(\); \}/.test(voice));
check("voice.js: đo mạng chậm qua onplaying", /audio\.onplaying = /.test(voice) && /this\.onSlow/.test(voice));
check("voice.js: công tắc bargeEnabled", /if \(!this\.bargeEnabled\) return;/.test(voice));
check("voice.js: onSpeakStart/onSpeakEnd", /this\.onSpeakStart\(\)/.test(voice) && /this\.onSpeakEnd\(\)/.test(voice));

// 4. index.html, i18n, css
const iTurn = html.indexOf("voice-turn.js"), iVoice = html.indexOf("/static/voice.js");
const iCtx = html.indexOf("ui-context.js"), iAct = html.indexOf("ui-actions.js"), iApp = html.indexOf("/static/app.js");
check("index.html: voice-turn.js trước voice.js", iTurn > 0 && iTurn < iVoice);
check("index.html: ui-context.js và ui-actions.js trước app.js", iCtx > 0 && iAct > 0 && iCtx < iApp && iAct < iApp);
const vVoice = +((html.match(/\/static\/voice\.js\?v=(\d+)/) || [])[1] || 0), vApp = +((html.match(/\/static\/app\.js\?v=(\d+)/) || [])[1] || 0);
check("index.html: ?v= voice.js >= 19 và app.js >= 104 (bản Voice V1)", vVoice >= 19 && vApp >= 104);
check("index.html: hàng chọn im lặng (name=endpoint) và công tắc #qsBarge", /name="endpoint"/.test(html) && /id="qsBarge"/.test(html));
["app.orb_waiting", "app.orb_tool", "app.orb_paused", "app.orb_reconnecting", "app.orb_mic_error", "app.orb_slow", "app.orb_background", "qs.endpoint", "qs.barge"].forEach(k => {
  check("i18n vi+en có " + k, typeof vi[k] === "string" && typeof en[k] === "string");
});
check("css: lớp orb waiting/paused/reconnecting/error", /\.orb-state\.waiting/.test(css) && /\.orb-state\.paused/.test(css) && /\.orb-state\.reconnecting/.test(css) && /\.orb-state\.error/.test(css));

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - orb trạng thái thật");
