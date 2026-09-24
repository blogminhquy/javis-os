/* Voice V2 - dây nối giữa dashboard và server (làn nhanh, nghe bằng Groq, bậc Live).

       node tests/js/test_voice_v2_day_noi.js

   Chỗ hỏng LẶNG LẼ nhất của đợt này: quên cờ `voice` trong khung WS là làn nhanh không bao giờ
   chạy mà không có lỗi nào; quên bọc onTranscript là Groq không bao giờ được hỏi. Test khoá:
     1. app.js gửi `voice: _tuGiong`, cờ bật khi đạo diễn commit; nạp cài đặt giọng từ /settings.
     2. voice.js ghi âm song song khi sttUpload, gửi /stt, bỏ đoạn dở khi mic tắt vì TTS.
     3. voice-live.js: PCM16 16 kHz lên, phát 24 kHz, interrupted xả hàng đợi, có sendText.
     4. app.js: chế độ live thì nút mic mở phiên Live, keep-alive không mở Web Speech.
     5. console.js có thẻ cài đặt V2 đọc /voice/options và lưu section voice; i18n đủ; index.html nạp voice-live.js. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const app = read("dashboard/app.js"), voice = read("dashboard/voice.js"), live = read("dashboard/voice-live.js");
const consoleJs = read("dashboard/console.js"), html = read("dashboard/index.html");
const vi = JSON.parse(read("dashboard/i18n/vi.json")), en = JSON.parse(read("dashboard/i18n/en.json"));
const main = read("server/main.py");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// 1
check("app.js: khung WS mang voice: _tuGiong (V3: hoặc đang rảnh tay)", /ws\.send\(JSON\.stringify\(\{ message: outMsg[\s\S]{0,200}voice: _tuGiong \|\| handsFree/.test(app));
check("app.js: commit từ đạo diễn bật cờ _tuGiong", /if \(c\) _tuGiong = true;/.test(app));
check("app.js: gửi xong hạ cờ", /_tuGiong = false;\s*\n\}/.test(app));
check("app.js: đọc mode + stt_provider từ /settings", /voiceMode = v\.mode \|\| "standard";/.test(app) && /voice\.sttUpload = v\.stt_provider === "groq";/.test(app));
check("app.js: xuất JavisVoiceMode.refresh cho trang Cài đặt", /window\.JavisVoiceMode = \{ refresh: napCaiDatGiong/.test(app));
check("server: nhánh voice chỉ khi payload.voice + mode fast", /payload\.get\("voice"\)/.test(main) && /_vconf\.get\("mode"\) == "fast"/.test(main));

// 2
check("voice.js: bọc onTranscript qua _quaStt", /this\.onTranscript = \(text\) => \{ this\._quaStt\(text, _userTranscript\); \};/.test(voice));
check("voice.js: MediaRecorder start(250) khi sttUpload", /if \(!this\.sttUpload \|\| !this\.micStream/.test(voice) && /rec\.start\(250\)/.test(voice));
// POST language, partial capture and fallback execute in test_voice_capture_lifecycle.js.
check("voice.js: mic tắt vì TTS thì bỏ đoạn ghi", /_muteRecognition\(\) \{[\s\S]{0,700}this\._stopRecorder\(\)\.catch/.test(voice));
check("voice.js: file quá nhỏ (dưới 2 KB) không gửi", /blob\.size < 2000/.test(voice));

// 3
check("live: 16 kHz lên, 24 kHz xuống", /IN_RATE = 16000, OUT_RATE = 24000/.test(live));
check("live: interrupted -> flushPlayback", /d\.type === "interrupted"\) \{[\s\S]{0,120}flushPlayback\(\)/.test(live));
check("live: gửi Int16 buffer nhị phân", /ws\.send\(floatToPcm16\(f32\)\.buffer\)/.test(live));
check("voice.js: tải trước đoạn KẾ trong hàng đợi khi ở khúc cuối", /_preloadNextQueued\(\) \{/.test(voice)
      && /this\._chunkIndex !== this\.ttsChunks\.length - 1\) return;/.test(voice) && /else this\._preloadNextQueued\(\);/.test(voice));
check("voice.js: enqueue lúc đang đọc thì tải trước ngay", /else this\._preloadNextQueued\(\);   \/\/ đang đọc/.test(voice));
check("voice.js: preload khớp theo URL, không theo index", /this\._preloaded\.url === url/.test(voice) && !/_preloaded\.i === i/.test(voice));
check("server: làn nhanh chỉ đẩy câu đã khép qua split_speakable", /voice_brain\.split_speakable\(text, sent_upto, final\)/.test(main));
check("live: có sendText và stop", /sendText: sendText, sendContext: sendContext/.test(live) && /type: "stop"/.test(live));
check("live: phát nối tiếp theo nextAt", /nextAt = t \+ ab\.duration/.test(live));
check("live: bị ngắt thì đo ms đã phát TRƯỚC khi xả rồi gửi khung played",
      /var ms = playedMs\(\);[\s\S]{0,80}flushPlayback\(\);[\s\S]{0,80}sendJson\(\{ type: "played", ms: ms \}\)/.test(live));
check("live: sendContext chỉ gửi khi đổi", /if \(text === lastCtx/.test(live) && /type: "context"/.test(live) && /sendContext: sendContext/.test(live));
check("live: nhận reconnected", /d\.type === "reconnected"/.test(live));
check("app.js: phiên Live gửi ngữ cảnh giao diện định kỳ", /setInterval\(guiNguCanhLive, 1500\)/.test(app) && /JavisVoiceLive\.sendContext\(ctx\)/.test(app));
check("server: ask_javis chạy nền bằng create_task, không await trong vòng đọc", /asyncio\.create_task\(_run_tool\(ev\)\)/.test(main));
check("server: nhận khung context và played", /d\.get\("type"\) == "context"/.test(main) && /d\.get\("type"\) == "played"/.test(main));
check("server: goaway -> reconnect", /if ev\.get\("type"\) == "goaway":/.test(main) && /await prov\.reconnect\(\)/.test(main));

// 4
check("app.js: chế độ live -> batLive/tatRanhTay ở nút mic", /if \(voiceMode === "live"\) \{/.test(app) && /batLive\(\)/.test(app) && /else tatRanhTay\(\);/.test(app));
check("app.js: keep-alive không mở Web Speech khi live", /handsFree && voiceMode !== "live" && !voice\.isListening/.test(app));
check("app.js: bản ghi Javis khi live ghi vào hội thoại", /recordTurn\("javis", _liveJavisText\.trim\(\)/.test(app));
check("app.js: Esc hủy toàn bộ phiên giọng", /e\.code === "Escape"[\s\S]{0,500}tatRanhTay\(\)/.test(app));

// 5
check("console.js: thẻ V2 đọc /voice/options", /fetch\("\/voice\/options"/.test(consoleJs) && /renderVoiceV2Card\(\)/.test(consoleJs));
check("console.js: lưu section voice với mode/brain/stt/live", /saveSetting\("voice", data\)/.test(consoleJs) && /stt_provider: \$\("v2Stt"\)\.value/.test(consoleJs));
check("index.html: nạp voice-live.js", /voice-live\.js\?v=/.test(html));
["settings.v2_title", "settings.v2_mode_fast", "settings.v2_brain", "settings.v2_stt", "settings.v2_live", "app.live_error"].forEach(k =>
  check("i18n vi+en có " + k, typeof vi[k] === "string" && typeof en[k] === "string"));

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - voice v2 dây nối");
