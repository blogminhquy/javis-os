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
// 0.65.28: trong cuộc gọi KHÔNG dừng lượt cũ nữa (chủ dự án báo 02/10: "Đã dừng lượt này" liên
// tục, mô hình bị cắt); câu xếp hàng và gửi khi lượt xong. Ngoài cuộc gọi (mic một lần) vẫn dừng rồi gửi.
check("tin từ mic lúc đang gọi thì XẾP HÀNG, không dừng lượt cũ",
  /if \(!\(_tuGiong \|\| handsFree\)\) return;[\s\S]{0,400}if \(handsFree\) \{ xepCauChoLuot\(msg, opts\); return; \}\s*\n\s*stopCurrent\(\);/.test(app));

// ---- 3. Cắt lời chỉ làm Javis im, lượt đang chạy viết nốt (0.65.28) ----
const b = new T.VoiceTurn();
b.micOn(); b.turnStart(); b.ttsStart();
check("trước khi cắt lời: đang xử lý và đang đọc", b.processing === true && b.speaking === true);
let a = b.bargeConfirmed("doanh thu tuần này");
check("cắt lời -> stop_tts + listen, KHÔNG stop_turn",
  has(a, "stop_tts") && has(a, "listen") && !has(a, "stop_turn"));
check("cắt lời -> lượt vẫn đang chạy (processing giữ nguyên), Javis thôi đọc", b.processing === true && b.speaking === false);
check("app.js: stop_tts lúc lượt còn chạy thì đánh dấu im phần còn lại của lượt",
  /case "stop_tts": \{[\s\S]{0,600}if \(_tLuot && _tLuot\.running\) \{ _tLuot\.imLoa = true; cum\.reset\(\); \}/.test(app));
check("app.js: lượt đã bị cắt lời thì không đưa chữ ra loa nữa", /function docCum\(chunks, t\) \{\s*\n\s*if \(t && t\.imLoa\) return;/.test(app));

// ---- 4. Hàng chờ câu nói trong cuộc gọi: chạy THẬT cặp xepCauChoLuot/guiCauChoLuot từ nguồn ----
const nguon = (app.match(/let _cauChoLuot = \[\], _cauChoOpts = null;[\s\S]*?\nfunction guiCauChoLuot\(\) \{[\s\S]*?\n\}/) || [""])[0];
check("nhấc được cặp hàm câu chờ lượt", nguon.indexOf("function guiCauChoLuot") > 0);
const daGui = [], nhap = [];
const moi = { handsFree: true, running: true, speaking: false, queue: [] };
const api = new Function("env", "sendMessage", "nhapGiong",
  "let handsFree = env.handsFree; const savedSessionId = 's1';"
  + "const turns = { get s1() { return { running: env.running }; } };"
  + "const voice = { isSpeaking: () => env.speaking, isPaused: () => false, get speechQueue() { return env.queue; } };"
  + nguon + "\nreturn { xep: xepCauChoLuot, gui: guiCauChoLuot, xem: () => _cauChoLuot.slice() };")(
  moi, (t, o) => daGui.push([t, o]), (t) => nhap.push(t));
api.xep("Nói chung là cũng ổn", { x: 1 });
api.xep("còn cái này nữa");
check("hai câu nói lúc đang trả lời được xếp hàng, hiện thành nháp ghép", api.xem().length === 2
  && nhap[nhap.length - 1] === "Nói chung là cũng ổn còn cái này nữa" && daGui.length === 0);
api.gui();
check("lượt cũ còn chạy thì CHƯA gửi", daGui.length === 0);
moi.running = false; moi.speaking = true;
api.gui();
check("lượt xong mà loa còn đọc thì CHƯA gửi (không cắt câu trả lời đang đọc)", daGui.length === 0);
moi.speaking = false;
api.gui();
check("lượt xong và loa im thì gửi ĐÚNG MỘT tin ghép", daGui.length === 1 && daGui[0][0] === "Nói chung là cũng ổn còn cái này nữa"
  && daGui[0][1] && daGui[0][1].x === 1);
api.gui();
check("gọi lại lần nữa không gửi lặp", daGui.length === 1);
check("turn_done và lúc loa đọc xong đều gọi gửi câu chờ",
  /if \(isActive\) guiCauChoLuot\(\);/.test(app) && /onSpeakEnd: \(\) => \{ runActions\(turn\.ttsEnd\(\)\); setTimeout\(guiCauChoLuot, 0\); \}/.test(app));
check("cúp máy thì bỏ câu đang chờ", /_cauChoLuot = \[\]; _cauChoOpts = null;\s*\/\/ 0\.65\.28: cúp máy/.test(app));

// Không có lượt nào chạy (đang đọc tin nền chẳng hạn) thì đừng bịa ra stop_turn.
const b2 = new T.VoiceTurn();
b2.micOn(); b2.ttsStart();
const a2 = b2.bargeConfirmed("");
check("không có lượt đang chạy thì KHÔNG có stop_turn", !has(a2, "stop_turn") && has(a2, "stop_tts"));

console.log(fails.length ? "\n" + fails.length + " FAIL" : "\nTat ca OK");
process.exit(fails.length ? 1 : 0);
