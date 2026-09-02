/* Đọc bằng mic không còn dán chồng câu, và loa đi theo mic.

       node tests/js/test_mic_doc_chong_va_loa_theo_mic.js

   Chủ repo gửi ảnh 02/09: tin nhắn ĐỌC BẰNG MIC trên điện thoại thành "Ok Ok Ok Ok có Ok có
   vẻ Ok có vẻ ở Ok có vẻ ở bản ..." - mỗi mảnh nghe được lại chép cả câu tới lúc đó thêm một
   lần. Cùng ảnh đó: thanh nhập trên điện thoại có kẹp giấy, mic, gửi - KHÔNG có nút loa, nên
   không có chỗ nào bật/tắt giọng Javis.

   Gốc lỗi thứ nhất nằm ở voice.js: onresult làm `accumulated += final` từ resultIndex trở
   đi. Chrome Android giao resultIndex đứng ở 0 và final là CẢ câu tới lúc đó, nên cộng dồn là
   chép lại câu ấy ở mỗi sự kiện. Chữa: dựng lại từ toàn bộ event.results mỗi lần, và giữ
   phần đã nghe ở phiên trước trong _committed.

   Gốc lỗi thứ hai: style.css giấu #ttsToggleBar trên màn hẹp "để dời vào ngăn kéo", rồi
   0.48.3 bỏ luôn nút loa của ngăn kéo. Chữa theo ý chủ repo: loa đi theo mic, và trả nút loa
   về thanh nhập để thấy trạng thái. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const voice = read("dashboard/voice.js");
const app = read("dashboard/app.js");
const qs = read("dashboard/quick-settings.js");
const css = read("dashboard/style.css");
const html = read("dashboard/index.html");
let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- 1. Nhận giọng: dựng lại, không cộng dồn ----
const onres = (voice.match(/onresult = \(event\) => \{[\s\S]*?\n    \};/) || [""])[0];
check("tìm được onresult", !!onres);
check("CANARY: không còn `accumulatedTranscript +=` (cộng dồn qua sự kiện là gốc lỗi)",
  !/accumulatedTranscript \+=/.test(voice));
check("đọc lại TOÀN BỘ results từ 0, không từ resultIndex",
  /for \(let i = 0; i < event\.results\.length; i\+\+\)/.test(onres) && !/event\.resultIndex/.test(onres));
check("phần final được GÁN LẠI qua _ghepChuyenBien, không nối thêm",
  /this\.accumulatedTranscript = this\._ghepChuyenBien\(final\.trim\(\)\);/.test(onres));

// Chạy thật hàm ghép bằng cách nhấc nó ra khỏi class.
const ghepSrc = (voice.match(/_ghepChuyenBien\(finalNay\) \{[\s\S]*?\n  \}/) || [""])[0];
check("tìm được _ghepChuyenBien", !!ghepSrc);
const ghep = new Function("committed", "finalNay",
  "const self = { _committed: committed, " + ghepSrc.replace(/^_ghepChuyenBien/, "_ghepChuyenBien") + " }; return self._ghepChuyenBien(finalNay);");
check("Android giao final DÀI HƠN final trước thì lấy bản dài, không nối",
  ghep("Ok có", "Ok có vẻ") === "Ok có vẻ", ghep("Ok có", "Ok có vẻ"));
check("final trùng y hệt phần đã chốt thì không nhân đôi", ghep("Ok có vẻ", "Ok có vẻ") === "Ok có vẻ");
check("câu mới thật sự khác thì nối tiếp", ghep("Xin chào", "hôm nay thế nào") === "Xin chào hôm nay thế nào");
check("chưa chốt gì thì lấy nguyên final", ghep("", "Ok") === "Ok");

// ---- 2. Phiên tự mở lại không làm mất nửa câu đầu ----
check("onend tự mở lại thì gói phần đã nghe vào _committed trước",
  /this\._committed = this\._ghepChuyenBien\(""\);\s*\n\s*this\.recognition\.start\(\);/.test(voice));
check("mở nghe CHỦ ĐỘNG là lượt mới: xoá _committed", /clearTimeout\(this\._resumeTimer\);\s*\n\s*this\._committed = "";/.test(voice));
check("gửi xong dọn _committed", /this\._committed = "";\s*\n\s*if \(finalText\) this\.onTranscript\(finalText\);/.test(voice));
// Các chốt cũ của test_mic_khong_tu_gui phải còn nguyên (không được phá lúc sửa onresult).
check("onstart/onend/onerror vẫn hạ _starting ở dòng đầu",
  /onstart = \(\) => \{\s*\n\s*this\._starting = false;/.test(voice)
  && /onend = \(\) => \{\s*\n\s*this\._starting = false;/.test(voice));

// ---- 3. Javis không đọc trùng ----
check("enqueueSpeak bỏ đoạn y hệt đoạn vừa xếp", /if \(clean === this\._lastQueued && !opts\.force\) return;/.test(voice));
check("stopSpeaking xoá dấu vết đoạn cuối để lượt sau đọc lại được", /this\._lastQueued = "";/.test(voice));

// ---- 4. Loa đi theo mic ----
check("quick-settings phơi window.JavisTts.set đi qua applyState", /window\.JavisTts = \{ set: applyState/.test(qs));
check("bấm mic: loa bật/tắt theo handsFree", /window\.JavisTts\.set\(handsFree\)/.test(app));
check("bấm-giữ Space: bật loa", /window\.JavisTts\.set\(true\)/.test(app));
check("Esc (thoát rảnh tay): tắt loa", /window\.JavisTts\.set\(false\)/.test(app));
// Thả Space là hết một câu, không phải tắt nghe - tắt loa ở đó là câu trả lời bị câm.
const keyup = (app.match(/addEventListener\("keyup"[\s\S]*?\}\);/) || [""])[0];
check("CANARY: thả Space KHÔNG tắt loa", !/JavisTts/.test(keyup));
// Không đẻ thêm đường gửi tin (chốt của test_mic_khong_tu_gui).
check("vẫn đúng 4 chỗ gọi sendMessage", (app.match(/(?<!function )\bsendMessage\(/g) || []).length === 4);

// ---- 5. Điện thoại thấy nút loa ----
check("CANARY: màn hẹp KHÔNG còn giấu #ttsToggleBar", !/#ttsToggleBar \{ display: none; \}/.test(css));
check("nút loa xếp cạnh mic trên thanh nhập màn hẹp", /\.hud-voice \.tts-bar-btn \{ order: 3;/.test(css));
check("nút loa vẫn có trong HTML", html.indexOf('id="ttsToggleBar"') !== -1);

// ---- 6. cache-bust ----
const v = (f) => Number((html.match(new RegExp(f.replace(/\./g, "\\.").replace("-", "\\-") + "\\?v=(\\d+)")) || [])[1] || 0);
check("voice.js đã bump (>= 17)", v("voice.js") >= 17, v("voice.js"));
check("app.js đã bump (>= 101)", v("app.js") >= 101, v("app.js"));
check("quick-settings.js đã bump (>= 7)", v("quick-settings.js") >= 7, v("quick-settings.js"));
check("style.css đã bump (>= 80)", v("style.css") >= 80, v("style.css"));

console.log();
if (fails.length) { console.log("ĐỎ " + fails.length + " mục: " + fails.join(", ")); process.exit(1); }
console.log("Tất cả xanh.");
