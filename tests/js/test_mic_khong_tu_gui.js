/* Mic không được TỰ chép tiếng động trong phòng thành tin nhắn của người dùng.

       node tests/js/test_mic_khong_tu_gui.js

   Chủ repo báo 01/09/2026: trong khung chat hiện ra một câu anh KHÔNG hề gõ, nội dung như
   lời bài hát nghe nhầm, nằm ở bong bóng bên phải (tức là tin của NGƯỜI DÙNG). Câu hỏi đi
   kèm: "Javis có tự nhập liệu vào chat được không?".

   Câu trả lời của code: server KHÔNG bao giờ ghi được tin vai "user" - mọi kết quả việc nền
   đẩy về đều là "assistant". Chỗ duy nhất sinh ra tin của người dùng là dashboard, và ngoài
   ba đường bấm tay (Enter, nút gửi, nút thử lại) còn MỘT đường tự động: lớp giọng nói nghe
   xong là gọi thẳng sendMessage(), không hỏi lại. Nên mic mở ngoài ý muốn = tin nhắn ma.

   Hai đường mở mic ngoài ý muốn đã bịt, test này giữ cho chúng không mở lại:
     1. Đua trạng thái ở stopListening: bấm rồi thả Space thật nhanh thì onstart chưa chạy,
        isListening còn false, lệnh dừng rơi vào hư không -> mic kẹt mở, onend còn tự khởi
        động lại, và 1.5 giây im lặng sau khi nghe được gì đó là tự gửi.
     2. Barge-in rình suốt đời trang: micStream không bao giờ được đóng, nên mỗi lần Javis đọc
        thành tiếng là bộ rình ngắt lời chạy, và một tiếng động đủ to sẽ TỰ mở mic. */
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const voice = read("dashboard/voice.js");
const app = read("dashboard/app.js");
const html = read("dashboard/index.html");
const server = read("server/main.py");

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- 1. Đua trạng thái: lệnh dừng tới trước khi phiên kịp mở ----
check("startListening đánh dấu _starting trước khi gọi recognition.start()",
  /this\._starting = true;\s*\n\s*this\.recognition\.start\(\);/.test(voice));
check("startListening xoá nợ dừng cũ (_stopPending = false)",
  /this\._stopPending = false;[\s\S]{0,80}this\.recognition\.start\(\);/.test(voice));
check("stopListening ghi nợ khi phiên đang mở dở",
  /else if \(this\._starting\) \{[\s\S]{0,400}this\._stopPending = true;/.test(voice));
check("onstart trả nợ: abort ngay, không báo onStart",
  /if \(this\._stopPending\) \{[\s\S]{0,400}this\.userStopped = true;[\s\S]{0,200}abort\(\)[\s\S]{0,60}return;/.test(voice));
check("start() ném InvalidStateError thì GIỮ cờ _starting (phiên cũ vẫn sắp mở)",
  /if \(!e \|\| e\.name !== "InvalidStateError"\) this\._starting = false;/.test(voice));
check("onstart hạ cờ _starting", /onstart = \(\) => \{\s*\n\s*this\._starting = false;/.test(voice));
check("onend hạ cờ _starting", /onend = \(\) => \{\s*\n\s*this\._starting = false;/.test(voice));
check("onerror hạ cờ _starting", /onerror = \(event\) => \{\s*\n\s*this\._starting = false;/.test(voice));

// ---- 2. Barge-in chỉ rình khi mic đang thật sự mở ----
// _resumeAfterTTS chỉ bật trong _muteRecognition, mà chỗ đó đòi isListening === true.
// Vậy điều kiện này đúng bằng "người dùng đang trong phiên nói chuyện bằng giọng".
check("_startBargeMonitor thoát sớm khi mic không mở (!_resumeAfterTTS)",
  /_startBargeMonitor\(\) \{[\s\S]{0,900}if \(!this\._resumeAfterTTS\) return;/.test(voice));
check("_muteRecognition vẫn là chỗ duy nhất bật _resumeAfterTTS khi đang nghe",
  /_muteRecognition\(\) \{\s*\n\s*if \(!this\.recognition \|\| !this\.isListening\) return;\s*\n\s*this\._resumeAfterTTS = true;/.test(voice));

// ---- 3. CANARY: mic vẫn là đường TỰ GỬI, nên hai chốt trên phải còn ----
// Không đổi hành vi này (rảnh tay và bấm-giữ-Space đều cần gửi ngay), chỉ ghi lại cho rõ:
// hễ ai bỏ chốt ở mục 1-2 thì tin nhắn ma quay lại ngay.
check("onTranscript vẫn gửi thẳng, không qua bước xác nhận",
  /onTranscript: \(text\) => \{[\s\S]{0,200}if \(text\) sendMessage\(text\);/.test(app));
const goiGui = (app.match(/(?<!function )\bsendMessage\(/g) || []).length;
check("chỉ có 4 chỗ gọi sendMessage (giọng nói, thử lại, Enter, nút gửi)", goiGui === 4, goiGui);

// ---- 4. Server không tự nhập liệu: việc nền luôn là tin của Javis ----
check("push_to_chat ghi vai assistant, không bao giờ là user",
  /def push_to_chat[\s\S]{0,1400}append_message\(sid, "assistant", clean\)/.test(server));
// Đúng HAI chỗ ghi vai "user", cả hai đều là lượt hỏi có thật của người dùng: WebSocket của
// dashboard, và tin nhắn đến từ Telegram/Zalo (phiên riêng theo chat_id, không dùng chung id
// với hội thoại web). Con số này nhích lên là có đường mới đẻ ra tin của người dùng - phải
// đọc lại xem nó đến từ đâu trước khi sửa test.
const ghiUser = (server.match(/append_message\([^)]*"user"/g) || []).length;
check("chỉ 2 chỗ trong server ghi vai user, đều là lượt hỏi thật (web + bot)", ghiUser === 2, ghiUser);

// ---- 5. cache-bust ----
const v = (f) => Number((html.match(new RegExp(f.replace(/\./g, "\\.") + "\\?v=(\\d+)")) || [])[1] || 0);
check("voice.js đã bump ?v= (>= 16)", v("voice.js") >= 16, v("voice.js"));

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_mic_khong_tu_gui: tat ca pass");
