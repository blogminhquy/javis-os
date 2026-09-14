/* Việc nền báo xong KHÔNG được khoá cứng khung chat (0.57.16).

       node tests/js/test_viec_nen_khong_khoa_chat.js

   Chủ dự án báo 15/09: "sau khi có 1 đoạn chạy nền hiện ra thì không nói nữa luôn, không nhắn
   tiếp vào khung chat, màn hình bị dừng ở đang suy nghĩ".

   Ba triệu chứng, MỘT gốc, và nó nằm ở dòng định tuyến khung WebSocket:

       const t = sid ? (turns[sid] || (turns[sid] = { ... running: true })) : null;

   Khung `push` (việc nền đẩy kết quả vào khung chat) cũng đi qua dòng đó. Mà `turn_done` đã
   XOÁ turns[sid] khi lượt kết thúc, nên dòng này HỒI SINH một lượt đã chết với cờ running=true
   mà không còn turn_done nào tới để hạ xuống. Dây chuyền hỏng:
     - syncActiveUI đọc cờ ấy -> isProcessing = true -> khoá nút gửi;
     - sendMessage thấy phiên "đang trả lời" -> nuốt lặng mọi tin sau đó;
     - vòng giữ mic trong app.js đòi !isProcessing -> mic không bao giờ mở lại.

   Test này CHẠY THẬT chính biểu thức định tuyến lấy từ app.js, không chỉ soi mẫu chữ. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const app = read("dashboard/app.js");
const T = require("../../dashboard/voice-turn.js");

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}
const has = (acts, t) => acts.some(a => a.type === t);

// ---- 1. Nhấc nguyên biểu thức định tuyến ra chạy ----
const m = app.match(/const KHUNG_LUOT = \[[\s\S]*?\n {2}const t = !sid[\s\S]*?: null\)\);/);
check("tìm được biểu thức định tuyến khung trong app.js", !!m);
const dinhTuyen = new Function("turns", "sid", "data", (m ? m[0] : "const t=null;") + "\nreturn t;");

// Lượt vừa kết thúc: turn_done đã xoá turns[sid].
let turns = {};
const SID = "abc123";

// Khung push của việc nền tới SAU khi lượt đã xong.
let t = dinhTuyen(turns, SID, { type: "push", content: "Kết quả việc nền" });
check("khung push KHÔNG dựng lại lượt đã chết", turns[SID] === undefined);
check("khung push trả t = null (nơi nhận đã tự lo phần hiển thị)", t === null);

turns = {};
t = dinhTuyen(turns, SID, { type: "inbox" });
check("khung inbox cũng không dựng lượt", turns[SID] === undefined);

// Ngược lại: khung của một lượt THẬT vẫn phải dựng bộ đệm và đánh dấu đang chạy, kể cả khi
// đó là phiên nền chưa từng thấy (Lịch sử cần biết phiên đó đang chạy).
turns = {};
t = dinhTuyen(turns, SID, { type: "stream", content: "xin" });
check("khung stream vẫn dựng bộ đệm mới", !!turns[SID] && turns[SID].running === true);
check("khung stream trả đúng bộ đệm vừa dựng", t === turns[SID]);

turns = {};
dinhTuyen(turns, SID, { type: "status", content: "đang nghĩ" });
check("khung status vẫn dựng bộ đệm mới", !!turns[SID] && turns[SID].running === true);

// Đang có lượt chạy thật thì push KHÔNG được đụng vào bộ đệm ấy (tin nền chỉ chèn thêm
// một bong bóng, lượt đang stream vẫn chạy bình thường).
turns = {};
const dang = (turns[SID] = { text: "nửa câu", bubble: {}, spoke: false, running: true });
t = dinhTuyen(turns, SID, { type: "push", content: "việc nền xong" });
check("đang có lượt chạy: push trả đúng bộ đệm đang có, không thay mới", t === dang);
check("đang có lượt chạy: push không đổi cờ running", turns[SID].running === true);

// Chuỗi ĐÚNG như người dùng gặp: lượt giọng xong -> turn_done xoá -> việc nền push về.
turns = {};
dinhTuyen(turns, SID, { type: "stream", content: "Ừ, để xem ngay." });
dinhTuyen(turns, SID, { type: "response", content: "Ừ, để xem ngay." });
delete turns[SID];                                  // turn_done làm đúng việc này
dinhTuyen(turns, SID, { type: "push", content: "Xong việc nền rồi" });
check("CA THẬT: sau việc nền, phiên KHÔNG còn bị coi là đang chạy",
  !(turns[SID] && turns[SID].running));

// ---- 2. sendMessage không được nuốt lặng tin từ mic ----
check("CANARY: bỏ hẳn kiểu nuốt lặng `if (turns[sid].running) return;`",
  !/if \(turns\[sid\] && turns\[sid\]\.running\) return;/.test(app));
check("tin từ mic (hay gõ lúc rảnh tay) thì DỪNG lượt cũ rồi gửi",
  /if \(!\(_tuGiong \|\| handsFree\)\) return;[\s\S]{0,120}stopCurrent\(\);/.test(app));

// ---- 3. Cắt lời thì dừng luôn lượt đang chạy ----
const b = new T.VoiceTurn();
b.micOn(); b.turnStart(); b.ttsStart();
check("trước khi cắt lời: đang xử lý và đang đọc", b.processing === true && b.speaking === true);
let a = b.bargeConfirmed("doanh thu tuần này");
check("cắt lời -> stop_tts + stop_turn + listen",
  has(a, "stop_tts") && has(a, "stop_turn") && has(a, "listen"));
check("cắt lời -> hạ luôn cờ processing (không kẹt 'đang suy nghĩ')", b.processing === false);
check("thứ tự: stop_tts đứng TRƯỚC stop_turn (đóng băng bong bóng theo lời rồi mới dừng lượt)",
  a.findIndex(x => x.type === "stop_tts") < a.findIndex(x => x.type === "stop_turn"));

// Không có lượt nào chạy (đang đọc tin nền chẳng hạn) thì đừng bịa ra stop_turn.
const b2 = new T.VoiceTurn();
b2.micOn(); b2.ttsStart();
const a2 = b2.bargeConfirmed("");
check("không có lượt đang chạy thì KHÔNG có stop_turn", !has(a2, "stop_turn") && has(a2, "stop_tts"));

console.log(fails.length ? "\n" + fails.length + " FAIL" : "\nTat ca OK");
process.exit(fails.length ? 1 : 0);
