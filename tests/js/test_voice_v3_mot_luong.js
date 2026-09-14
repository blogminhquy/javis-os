/* Voice V3 - nói chuyện mượt, chữ và giọng một luồng (dây nối giữa các module).

       node tests/js/test_voice_v3_mot_luong.js

   Chỗ hỏng LẶNG LẼ của đợt này: quên nối chunker vào khung stream là bộ não chính lại đọc từng
   mẩu như cũ mà không có lỗi nào; quên cờ voice khi gõ chữ lúc rảnh tay là "một luồng" chỉ có
   trên giấy. Test khoá:
     1. index.html nạp voice-chunker.js TRƯỚC app.js; app.js đổ MỌI khung stream qua chunker, flush
        ở response, reset ở turn_done và khi gửi tin mới; không còn enqueueSpeak thẳng từ stream.
     2. Đồng hồ cụm: tick với "loa đang im", câu tiến độ chỉ khi rảnh tay; runActions có speak_filler;
        i18n có app.voice_filler ở cả hai ngôn ngữ, nhiều câu cách nhau bằng |.
     3. Gõ chữ lúc rảnh tay: khung WS voice: _tuGiong || handsFree; khối ngữ cảnh mang voice; ở Live
        thì đẩy vào phiên Live bằng sendText, không mở lượt chat.
     4. channel_context.py dạy bộ não chính khoá kênh=giọng. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const app = read("dashboard/app.js"), html = read("dashboard/index.html");
const vi = JSON.parse(read("dashboard/i18n/vi.json")), en = JSON.parse(read("dashboard/i18n/en.json"));
const ctxPy = read("server/channel_context.py");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// 1
const iChunk = html.indexOf("/static/voice-chunker.js"), iApp = html.indexOf("/static/app.js");
check("index.html nạp voice-chunker.js trước app.js", iChunk > 0 && iApp > iChunk);
check("app.js dựng chunker từ JavisVoiceChunker", /const cum = new window\.JavisVoiceChunker\.Chunker\(\);/.test(app));
check("stream: đổ qua cum.push rồi docCum, bật đồng hồ", /docCum\(cum\.push\(data\.content \|\| "", Date\.now\(\)\), t\);\s*\n\s*batDongHoCum\(\);/.test(app));
check("stream: KHÔNG còn enqueueSpeak thẳng từ khung stream", !/const safeChunk = \(data\.content \|\| ""\)\.replace/.test(app));
check("response: flush phần đuôi rồi mới xét đọc cả câu (tts:false)", /docCum\(cum\.flush\(\), t\);[\s\S]{0,200}if \(!t\.spoke && finalText\) voice\.speak\(finalText\);/.test(app));
check("turn_done: reset chunker", /runActions\(turn\.turnDone\(\)\); cum\.reset\(\);/.test(app));
check("gửi tin mới: reset chunker", /voice\.stopSpeaking\(\);\s*\n\s*cum\.reset\(\);/.test(app));
check("docCum đánh dấu t.spoke và turn.noteSpoke", /if \(t\) t\.spoke = true;\s*\n\s*turn\.noteSpoke\(\);/.test(app));

// 2
check("đồng hồ: tick kèm 'loa đang im' = !voice.isSpeaking()", /cum\.tick\(Date\.now\(\), !voice\.isSpeaking\(\)\)/.test(app));
check("câu tiến độ chỉ khi rảnh tay (handsFree)", /if \(handsFree\) runActions\(turn\.fillerCheck\(Date\.now\(\)\)\);/.test(app));
check("runActions có speak_filler -> noiTienDo", /case "speak_filler": noiTienDo\(\); break;/.test(app));
check("noiTienDo đọc app.voice_filler, tách bằng |", /window\.t\("app\.voice_filler"\)[\s\S]{0,60}split\("\|"\)/.test(app));
check("i18n vi/en có app.voice_filler với từ 2 câu trở lên",
      String(vi["app.voice_filler"] || "").split("|").length >= 2 && String(en["app.voice_filler"] || "").split("|").length >= 2);
check("i18n: câu tiến độ không có em dash", !/—/.test(vi["app.voice_filler"] + en["app.voice_filler"]));

// 3
check("khung WS: voice: _tuGiong || handsFree", /session_id: sid, voice: _tuGiong \|\| handsFree \}\)\)/.test(app));
check("khối ngữ cảnh mang voice: _tuGiong || handsFree", /voice: _tuGiong \|\| handsFree,\s*\n\s*\}\) : "";/.test(app));
check("Live: gõ chữ thì sendText vào phiên Live và return, không đi ws chat",
      /voiceMode === "live" && !atts\.length && window\.JavisVoiceLive && window\.JavisVoiceLive\.isOn\(\)\) \{[\s\S]{0,400}window\.JavisVoiceLive\.sendText\(msg\);\s*\n\s*return;/.test(app));

// 4
check("channel_context.py giải thích kênh=giọng: trả lời như người đang nói, không dàn trang",
      /kênh=giọng/.test(ctxPy) && /không tiêu đề, không bảng, không gạch đầu dòng/.test(ctxPy));

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - voice-v3-mot-luong");
