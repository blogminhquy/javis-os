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
     4. channel_context.py dạy bộ não chính khoá kênh=giọng.
     5. Chữ hiện THEO LỜI ĐỌC: voice.js đếm từ đã ra tiếng, voice-live.js đo tiến độ phát, app.js chỉ
        vẽ phần đã đọc, ngắt lời thì đóng băng kèm …, đọc xong mới vẽ markdown đủ. */
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

// 5. Chữ hiện THEO LỜI ĐỌC (karaoke)
const voiceJs = read("dashboard/voice.js"), liveJs = read("dashboard/voice-live.js"), css = read("dashboard/style.css");
check("voice.js: đếm từ đã ra tiếng (spokenWords / resetSpokenWords / demTu)",
      /resetSpokenWords\(\) \{ this\._wordsDone = 0; \}/.test(voiceJs) && /spokenWords\(\) \{/.test(voiceJs) && /static demTu\(s\)/.test(voiceJs));
check("voice.js: khúc đọc xong cộng từ, cả đường máy tính lẫn iOS lẫn giọng trình duyệt",
      (voiceJs.match(/this\._wordsDone \+= JavisVoice\.demTu\(/g) || []).length >= 4);
check("voice.js: enqueueSpeak(opts.uncounted) không tính vào số từ", /if \(opts\.uncounted\) this\._uncounted\.push\(clean\);/.test(voiceJs)
      && /this\._countThis = ui < 0;/.test(voiceJs));
check("voice.js: iOS cũng ghi _chunkIndex (spokenWords cần)", /this\.currentAudio = a;\s*\n\s*this\._chunkIndex = i;/.test(voiceJs));
check("voice-live.js: progress() + resetProgress(), schedMs cộng theo từng khối, xả thì về 0",
      /progress: progress, resetProgress: resetProgress/.test(liveJs) && /schedMs \+= ab\.duration \* 1000;/.test(liveJs)
      && /utterStartAt = 0;\s*\n\s*schedMs = 0;/.test(liveJs));
check("app.js: stream ở phiên giọng -> batTheoLoi thay vì vẽ cả câu", /if \(dangTheoLoi\(\) && data\.tts !== false\) batTheoLoi\(t\.bubble, t\.text, null, false\);/.test(app));
check("app.js: response ở phiên giọng -> batTheoLoi mang ask, vẽ đủ + chip khi đọc xong",
      /if \(dangTheoLoi\(\) && t && finalText\) \{\s*\n\s*batTheoLoi\(msgEl, shownText, ask, false\);/.test(app)
      && /if \(s\.ask\) window\.JavisAsk\.render\(s\.el, s\.ask, true\);/.test(app));
check("app.js: ngắt lời thật -> đóng băng chỗ đã nói kèm …", /a\.interrupted\) \{[^\n]*ketThucTheoLoi\(true\);/.test(app)
      && /takeWords\(full, s\.shown\)\) \+ " …";/.test(app));
check("app.js: Live -> batTheoLoi live, ngắt -> ketThucTheoLoi(true), turn_done -> chuaXong=false",
      /batTheoLoi\(_liveJavisBubble, _liveJavisText, null, true\)/.test(app) && /onInterrupted: \(\) => \{ ketThucTheoLoi\(true\);/.test(app)
      && /_theoLoi\.chuaXong = false;/.test(app));
check("app.js: câu tiến độ và tin nền đọc với uncounted", /opts\.length\)\]\, \{ uncounted: true \}\)/.test(app)
      && /voice\.enqueueSpeak\(t, \{ uncounted: true \}\)/.test(app) && /voice\.enqueueSpeak\(data\.content \|\| "", \{ uncounted: true \}\)/.test(app));
check("app.js: lượt mới reset số từ và vẽ đủ bong bóng cũ", /ketThucTheoLoi\(false\);[^\n]*\n\s*voice\.resetSpokenWords\(\);/.test(app));
check("app.js: vòng vẽ orb gọi nhipTheoLoi", /if \(_theoLoi && \(_stopBtnTick % 3\) === 0\) nhipTheoLoi\(\);/.test(app));
check("style.css: có .theo-loi-cho", /\.theo-loi-cho \{/.test(css));

// 6. Chữ đang nghe hiện trong khung chat (bong bóng nháp), không đè lên khối não
check("app.js: có nhapGiong dựng bong bóng nháp msg-user trong cột chat", /function nhapGiong\(text\)/.test(app) && /className = "msg msg-user msg-nhap-giong"/.test(app));
check("app.js: không còn ghi chữ tạm lên #voiceInterim ngoài nhapGiong", (app.match(/voiceInterim\.textContent = /g) || []).length === 1);
check("app.js: mic Web Speech và Live đều đi nhapGiong", /onInterim: \(text\) => \{\s*\n\s*nhapGiong\(text\);/.test(app) && /else nhapGiong\(text\);/.test(app));
check("app.js: gửi tin thì gỡ bong bóng nháp trước", /voice\.resetSpokenWords\(\);[^\n]*\n\s*nhapGiong\(""\);/.test(app));
check("style.css: có .msg-nhap-giong", /\.msg-nhap-giong \.bubble \{/.test(css));

// 7. Tách nói khỏi làm: câu xác nhận kèm dòng "đang làm nền"
check("app.js: response mang background -> dòng voice-nen dưới bong bóng", /if \(data\.background\) \{/.test(app) && /className = "voice-nen"/.test(app)
      && /window\.t\("app\.voice_bg_task", \{ task:/.test(app));
check("i18n vi/en có app.voice_bg_task với {task}", /\{task\}/.test(vi["app.voice_bg_task"] || "") && /\{task\}/.test(en["app.voice_bg_task"] || ""));
check("style.css: có .voice-nen", /\.voice-nen \{/.test(css));

// 4
check("channel_context.py giải thích kênh=giọng: trả lời như người đang nói, không dàn trang",
      /kênh=giọng/.test(ctxPy) && /không tiêu đề, không bảng, không gạch đầu dòng/.test(ctxPy));

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - voice-v3-mot-luong");
