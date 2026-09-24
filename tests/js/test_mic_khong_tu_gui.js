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
// Opening-state and deferred-stop behavior execute in test_voice_capture_lifecycle.js.
check("stopListening ghi nợ khi phiên đang mở dở",
  /else if \(this\._starting\) \{[\s\S]{0,400}this\._stopPending = true;/.test(voice));
check("onstart trả nợ: abort ngay, không báo onStart",
  /if \(this\._stopPending\) \{[\s\S]{0,400}this\.userStopped = true;[\s\S]{0,200}abort\(\)[\s\S]{0,60}return;/.test(voice));
check("start() ném InvalidStateError thì GIỮ cờ _starting (phiên cũ vẫn sắp mở)",
  /if \(!e \|\| e\.name !== "InvalidStateError"\) this\._starting = false;/.test(voice));
check("onstart hạ cờ _starting", /onstart = \(\) => \{\s*\n\s*this\._starting = false;/.test(voice));
check("onend hạ cờ _starting", /onend = \(\) => \{\s*\n\s*this\._starting = false;/.test(voice));
check("onerror hạ cờ _starting", /onerror = \(event\) => \{\s*\n\s*this\._starting = false;/.test(voice));

// ---- 2. Barge-in chỉ rình khi người dùng ĐANG nói chuyện bằng giọng ----
// Bản cũ suy: "_resumeAfterTTS chỉ bật trong _muteRecognition, mà chỗ đó đòi isListening ===
// true, vậy cờ ấy đúng bằng đang-nói-chuyện-bằng-giọng". SUY SAI, và nó khoá luôn cái sai vào
// test: trong hội thoại rảnh tay, nói xong là đồng hồ im lặng ĐÓNG mic trước khi câu trả lời
// kịp đọc, nên tới lượt đọc thì isListening đã false, _muteRecognition thoát ngay và cờ không
// bao giờ bật. Ngắt lời vì thế chưa từng chạy một lần nào (chủ dự án thử thật 15/09).
// Chốt đúng là cờ `handsFree` do app.js đồng bộ. Ý ĐỊNH của mục này giữ nguyên: rảnh tay tắt
// thì Javis đọc trong im lặng, không được tự nghe rồi biến tiếng TV thành tin nhắn.
check("_startBargeMonitor thoát sớm khi KHÔNG trong cuộc nói chuyện bằng giọng",
  /_startBargeMonitor\(\) \{[\s\S]{0,1800}if \(!this\._resumeAfterTTS && !this\.handsFree\) return;/.test(voice));
check("app.js đồng bộ handsFree sang voice.js (và tắt ngay khi mic hỏng)",
  /voice\.handsFree = handsFree && voiceMode !== "live";/.test(app)
  && /function tatRanhTay\(\) \{[\s\S]{0,700}voice\.handsFree = false;/.test(app));
// TTS abort during opening/listening is covered by test_voice_capture_lifecycle.js.

// ---- 3. CANARY: mic vẫn là đường TỰ GỬI, nên hai chốt trên phải còn ----
// Không đổi hành vi này (rảnh tay và bấm-giữ-Space đều cần gửi ngay), chỉ ghi lại cho rõ:
// hễ ai bỏ chốt ở mục 1-2 thì tin nhắn ma quay lại ngay.
check("onTranscript vẫn gửi thẳng, không qua bước xác nhận",
  /onTranscript: \(text\) => \{[\s\S]{0,200}if \(text\) sendMessage\(text\);/.test(app));
// Chỗ thứ 5 (0.55.63) là sendMessage TỰ GỌI LẠI CHÍNH NÓ sau khi file đính kèm tải lên
// xong - cùng một lượt Enter của người dùng bị hoãn, không phải một đường gửi mới.
// Chỗ thứ 6 (0.57.17) cùng kiểu HOÃN chứ không phải đường mới: người dùng nói chen ngang lúc
// Javis đang trả lời thì phải dừng lượt cũ trước, mà server chỉ nhận tin mới khi job cũ đã
// dừng hẳn, nên câu ấy được gửi lại khi `turn_done` về (guiTinCho).
// Chỗ thứ 7 (0.58.2) VẪN là hoãn: mất WebSocket thì câu được giữ lại rồi gửi khi nối lại
// (guiTinDutMang). Trước đó chỗ này vứt tin lặng lẽ - trên iPhone là câu nói bốc hơi.
const goiGui = (app.match(/(?<!function )\bsendMessage\(/g) || []).length;
check("chỉ có 8 chỗ gọi sendMessage (giọng nói, thử lại, Enter, nút gửi, sau khi tải file xong, sau khi dừng lượt cũ, sau khi nối lại mạng, sau khi mở agent/workflow)",
  goiGui === 8, goiGui);
// Reconnect sends and cancellation across chats execute in test_voice_app_session.js.
check("chỗ thứ 5 nằm TRONG sendMessage và chỉ chạy sau Promise.all của file đang tải",
  /Promise\.all\(dangTai\.map\(a => a\.xong[\s\S]{0,300}sendMessage\(text, opts\);/.test(app));
check("chỗ thứ 6 là tin hoãn, chỉ gửi sau khi lượt cũ đã dừng",
  /function guiTinCho\(\) \{[\s\S]{0,300}if \(t\) sendMessage\(t\);/.test(app)
  && /if \(isActive && _tinChoLuot\) guiTinCho\(\);/.test(app));

// ---- 4. Server không tự nhập liệu: việc nền luôn là tin của Javis ----
check("push_to_chat ghi vai assistant, không bao giờ là user",
  /def push_to_chat[\s\S]{0,1400}append_message\(sid, "assistant", clean\)/.test(server));
// Năm chỗ ghi vai "user": bốn đường nhập liệu và một thao tác duyệt quy trình.
// Bốn đường nhập liệu là: WebSocket của dashboard,
// tin nhắn đến từ Telegram/Zalo (phiên riêng theo chat_id), và HAI chỗ trong phiên nghe nói
// thẳng `/ws/voice-live` (Voice V2, 0.57.0): chữ người dùng gõ vào phiên Live, và bản ghi CUỐI
// của câu họ vừa NÓI do nhà cung cấp trả về - đó là giọng thật của họ, không phải máy tự nhập.
// Con số này nhích lên là có đường mới đẻ ra tin của người dùng - phải đọc lại xem nó đến từ
// đâu trước khi sửa test.
const ghiUser = (server.match(/append_message\([^)]*"user"/g) || []).length;
check("chỉ 5 chỗ ghi vai user (web + bot + 2 Live + duyệt quy trình)", ghiUser === 5, ghiUser);
const approvalBody = server.slice(server.indexOf('if action == "wf_resume":'), server.indexOf('if action == "resume_now":'));
check("đường ghi thứ năm chỉ thuộc thao tác duyệt quy trình",
  (approvalBody.match(/append_message\([^)]*"user"/g) || []).length === 1
  && approvalBody.includes('store.append_message(_sid, "user", _msg)'));
const liveBody = (server.match(/async def voice_live_ws\([\s\S]*?\n@app\./) || [""])[0];
check("hai chỗ mới nằm TRONG voice_live_ws", (liveBody.match(/append_message\([^)]*"user"/g) || []).length === 2);

// ---- 5. cache-bust ----
const v = (f) => Number((html.match(new RegExp(f.replace(/\./g, "\\.") + "\\?v=(\\d+)")) || [])[1] || 0);
check("voice.js đã bump ?v= (>= 16)", v("voice.js") >= 16, v("voice.js"));

console.log();
check("slash only sends after opening the selected session", /if \(\!opened\) return;[\s\S]{0,150}if \(_slash.message\) sendMessage\(_slash.message\)/.test(app));
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_mic_khong_tu_gui: tat ca pass");
