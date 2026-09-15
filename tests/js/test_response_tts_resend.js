/* Khung "response" thứ hai (bản sửa lại sau khi bóc JAVIS_LESSON của phiên trợ lý ở trang
   Cộng sự) KHÔNG được làm loa đọc lại lần hai.

       node tests/js/test_response_tts_resend.js

   Bối cảnh (fix round 2, task 5 cộng sự): server gửi khung "response" đầu tiên với text THÔ
   (còn dòng JAVIS_LESSON), rồi gửi thêm một khung "response" thứ hai với text đã sạch kèm
   "tts": false để ép vẽ lại đúng chữ trên bong bóng. Nhưng nhánh xử lý "response" trong
   app.js có một lối gọi voice.speak() DỰ PHÒNG ở cuối cho engine chỉ đọc một lần (API-key,
   phiên trợ lý...), và cờ `t.spoke` trước đó CHỈ được set từ nhánh "stream" (docCum), không
   phải từ chính lối gọi dự phòng đó. Nên khung thứ hai gọi speak() lại lần nữa, cắt ngang rồi
   đọc lại từ đầu. Hai luật phải có trong app.js:
     1. Sau lần gọi voice.speak() dự phòng, PHẢI set t.spoke = true ngay, để khung sau của
        CÙNG lượt không đọc lại nữa.
     2. Cả khối TTS (docCum + speak) phải bị bỏ qua khi data.tts === false, giống hệt cách
        nhánh "stream" đã tôn trọng data.tts !== false. */
const fs = require("fs");
const path = require("path");

// app.js có byte NUL (icon SVG nhúng) - đọc "utf8" thường vẫn ra text được (Node bỏ qua NUL
// trong so sánh chuỗi/regex), đúng cách các test khác trong tests/js/ đang làm.
const APP = fs.readFileSync(path.join(__dirname, "../../dashboard/app.js"), "utf8");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

const iResp = APP.indexOf('else if (data.type === "response")');
check("tìm được nhánh xử lý data.type === \"response\"", iResp !== -1);
const iErr = APP.indexOf('else if (data.type === "error")', iResp);
check("tìm được điểm kết thúc nhánh (nhánh error kế tiếp)", iErr !== -1 && iErr > iResp);
const than = APP.slice(iResp, iErr);

// ---- 1. Khối TTS phải bỏ qua khi data.tts === false, như nhánh "stream" đã làm ----
check("CANARY: khối TTS của nhánh response bị chặn bởi data.tts === false",
      /voice\.ttsEnabled\s*&&\s*t\s*&&\s*data\.tts\s*!==\s*false/.test(than));

// ---- 2. Sau lần gọi voice.speak() dự phòng phải set t.spoke = true ngay ----
// Bắt đúng câu if (!t.spoke && finalText) ... voice.speak(finalText) ... t.spoke = true,
// không quan tâm nó nằm trong khối {..} hay nối bằng "&&" - chỉ cần t.spoke = true đứng
// SAU lời gọi voice.speak(finalText) trong đúng câu lệnh đó.
const mSpeak = than.match(/if\s*\(!t\.spoke\s*&&\s*finalText\)\s*\{?\s*voice\.speak\(finalText\);[^\n]*?t\.spoke\s*=\s*true;/);
check("CANARY: sau voice.speak(finalText) dự phòng có set t.spoke = true ngay trong câu đó",
      mSpeak !== null);

if (fails.length) {
  console.log("\nFAIL - test_response_tts_resend: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_response_tts_resend: tất cả pass");
