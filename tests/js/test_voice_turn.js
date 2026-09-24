/* Đạo diễn hội thoại bằng giọng (dashboard/voice-turn.js) - thuần, chạy bằng node.

       node tests/js/test_voice_turn.js

   Voice V1 (docs/dev/2026-09-voice-v1-spec.md mục 3). Khoá các luật mượn từ livekit/agents:
     1. Endpointing hai ngưỡng: câu kết bằng liên từ / dấu phẩy thì chờ lâu, còn lại chờ ngắn.
     2. Cụm CHỜ ("khoan", "đợi chút", "wait") -> không gửi, sang waiting_for_user, dừng đọc.
     3. Cụm DỪNG ("thôi", "stop") -> dừng đọc / dừng lượt, không gửi.
     4. Chen ngang: tạm dừng trước; có chữ -> dừng thật và nhớ phần đã đọc; không chữ -> phát tiếp.
     5. Không bao giờ chốt lượt rỗng.
     6. Tin nền chỉ đọc khi rảnh; đang nói thì hoãn tới lúc rảnh.
     7. Mất WebSocket thì trạng thái là reconnecting, đè lên mọi thứ khác. */
const T = require("../../dashboard/voice-turn.js");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}
const types = (acts) => acts.map(a => a.type);
const has = (acts, t) => acts.some(a => a.type === t);

// ---- 1. Endpointing ----
const v = new T.VoiceTurn();
check("mặc định minDelay 800, maxDelay 2200", v.opts.minDelay === 800 && v.opts.maxDelay === 2200);
check("câu xong -> chờ ngắn", v.delayFor("mở trang việc") === 800);
check("kết bằng 'và' -> chờ dài", v.delayFor("mở chrome và") === 2200);
check("kết bằng dấu phẩy -> chờ dài", v.delayFor("mở chrome,") === 2200);
check("kết bằng 'then' (Anh) -> chờ dài", v.delayFor("open chrome then") === 2200);
check("looksUnfinished chuỗi rỗng = false", T.looksUnfinished("") === false);
v.micOn();
let a = v.interim("mở trang");
check("interim: arm_endpoint kèm ms + state user_speaking", has(a, "arm_endpoint") && v.state === "user_speaking");
a = v.interim("mở trang việc và");
check("interim mới tính lại ms (bounce)", a.find(x => x.type === "arm_endpoint").ms === 2200);

// ---- 2. Cụm CHỜ ----
check("normalize: bỏ dấu câu, thường hoá", T.normalize("  Khoan, ĐÃ! ") === "khoan đã");
check("isWaitPhrase: 'khoan'", T.isWaitPhrase("khoan"));
check("isWaitPhrase: 'Khoan đã nhé'", T.isWaitPhrase("Khoan đã nhé"));
check("isWaitPhrase: 'Javis ơi, đợi anh chút'", T.isWaitPhrase("Javis ơi, đợi anh chút"));
check("isWaitPhrase: 'để mình nghĩ đã'", T.isWaitPhrase("để mình nghĩ đã"));
check("isWaitPhrase: 'hold on'", T.isWaitPhrase("hold on"));
check("isWaitPhrase: câu dài 'khoan, mở chrome' KHÔNG phải cụm chờ", !T.isWaitPhrase("khoan, mở chrome"));
check("isWaitPhrase: 'đợi' một mình", T.isWaitPhrase("đợi"));
const w = new T.VoiceTurn();
w.micOn(); w.interim("khoan");
a = w.endpoint("khoan");
check("endpoint CHỜ: có hold, không commit", has(a, "hold") && !has(a, "commit"));
check("endpoint CHỜ: state waiting_for_user", w.state === "waiting_for_user");
a = w.interim("mở trang việc");
check("nói tiếp khi đang chờ -> user_speaking", w.state === "user_speaking");
a = w.endpoint("mở trang việc");
check("rồi gửi bình thường", has(a, "commit") && w.state === "processing");
const w2 = new T.VoiceTurn();
w2.micOn(); w2.ttsStart();
a = w2.endpoint("từ từ");
check("CHỜ khi Javis đang đọc: dừng đọc + chờ", has(a, "stop_tts") && has(a, "hold") && w2.state === "waiting_for_user");
a = w2.waitTimeout();
check("hết 90 giây chờ -> về listening", w2.state === "listening");

// ---- 2b. V3: nói lắp / lặp vẫn là CHỜ; ậm ừ lúc nghĩ thì chờ lâu ----
check("isWaitPhrase V3: 'từ từ đợi đợi đợi chút' (lặp) vẫn là CHỜ", T.isWaitPhrase("từ từ đợi đợi đợi chút"));
check("isWaitPhrase V3: 'khoan khoan đợi mình chút nhé'", T.isWaitPhrase("khoan khoan đợi mình chút nhé"));
check("isWaitPhrase V3: 'đợi mình xem lại số liệu' KHÔNG phải CHỜ (có từ ngoài bộ)", !T.isWaitPhrase("đợi mình xem lại số liệu"));
check("isWaitPhrase V3: 'để mình' (không có cụm trọn) KHÔNG phải CHỜ", !T.isWaitPhrase("để mình"));
check("isStopPhrase V3: 'thôi thôi dừng lại' (lặp) là DỪNG", T.isStopPhrase("thôi thôi dừng lại"));
check("isStopPhrase V3: 'thôi dừng việc đó lại' KHÔNG phải DỪNG", !T.isStopPhrase("thôi dừng việc đó lại"));
check("endpointing V3: kết bằng 'ừm' -> chờ dài", v.delayFor("cho anh xem doanh thu ừm") === 2200);
check("endpointing V3: kết bằng 'kiểu' -> chờ dài", v.delayFor("anh muốn nó kiểu") === 2200);
check("endpointing V3: 'vậy à' là câu hỏi xong -> chờ ngắn", v.delayFor("hôm nay lỗ vậy à") === 800);
check("chỉ gọi Javis -> chờ thêm để nghe phần yêu cầu", v.delayFor("Javis ơi") === 2200);

// ---- 3. Cụm DỪNG ----
check("isStopPhrase: 'thôi'", T.isStopPhrase("thôi"));
check("isStopPhrase: 'dừng lại đi'", T.isStopPhrase("dừng lại đi"));
check("isStopPhrase: 'stop'", T.isStopPhrase("stop"));
check("isStopPhrase: 'thôi mở chrome' KHÔNG phải", !T.isStopPhrase("thôi mở chrome"));
const s = new T.VoiceTurn();
s.micOn(); s.ttsStart();
a = s.endpoint("thôi");
check("DỪNG khi đang đọc: stop_tts, không commit", has(a, "stop_tts") && !has(a, "commit") && s.state === "listening");
const s2 = new T.VoiceTurn();
s2.micOn(); s2.turnStart();
a = s2.endpoint("dừng lại");
check("DỪNG khi đang xử lý: stop_turn", has(a, "stop_turn") && !has(a, "commit"));

// ---- 4. Chen ngang ----
const b = new T.VoiceTurn();
b.micOn(); b.turnStart(); b.turnDone(); b.ttsStart();
check("đang đọc: state speaking", b.state === "speaking");
a = b.bargeStart();
check("bargeStart: pause_tts + listen, state interrupted", has(a, "pause_tts") && has(a, "listen") && b.state === "interrupted");
check("bargeStart lần hai khi đã interrupted: không làm gì", b.bargeStart().length === 0);
a = b.bargeTimeout();
check("không có chữ: resume_tts + abort_listen, về speaking", has(a, "resume_tts") && has(a, "abort_listen") && b.state === "speaking");
a = b.bargeStart();
a = b.interim("mở");
check("có chữ khi đang tạm dừng: stop_tts interrupted=true", a.some(x => x.type === "stop_tts" && x.interrupted) && b.state === "user_speaking");
check("interim khi tạm dừng cũng arm_endpoint", has(a, "arm_endpoint"));
b.setInterruptedAt("Doanh thu tháng này tăng");
a = b.endpoint("cho xem chi tiết");
check("commit mang interruptedAt rồi xoá", a.find(x => x.type === "commit").interruptedAt === "Doanh thu tháng này tăng" && b.interruptedAt === "");
const b2 = new T.VoiceTurn();
check("bargeStart khi KHÔNG đang đọc: không làm gì", b2.bargeStart().length === 0);
check("bargeTimeout khi không interrupted: không làm gì", b2.bargeTimeout().length === 0);
const b3 = new T.VoiceTurn();
b3.micOn(); b3.ttsStart(); b3.bargeStart();
a = b3.interim("...");
check("chữ không có ký tự -> vẫn tạm dừng", a.length === 0 && b3.state === "interrupted");

// ---- 5. Không chốt lượt rỗng ----
const e = new T.VoiceTurn();
e.micOn();
a = e.endpoint("");
check("endpoint rỗng: không commit", !has(a, "commit") && e.state === "listening");
a = e.endpoint("   ...  ");
check("endpoint toàn dấu: không commit", !has(a, "commit"));

// ---- 6. Tin nền hoãn ----
const d = new T.VoiceTurn();
d.micOn(); d.ttsStart();
check("đang nói: canSpeakNow false", !d.canSpeakNow());
d.defer("Việc A xong");
a = d.ttsEnd();
check("đọc xong: flush_deferred mang đúng tin", a.some(x => x.type === "flush_deferred" && x.texts[0] === "Việc A xong"));
check("flush xong thì rỗng", d.deferred.length === 0);
const d2 = new T.VoiceTurn();
d2.micOn(); d2.interim("đang nói");
check("người dùng đang nói: canSpeakNow false", !d2.canSpeakNow());

// ---- 6b. V3: câu tiến độ khi xử lý lâu ----
const f = new T.VoiceTurn();
f.micOn(); f.turnStart(1000);
check("filler: mới 1 giây chưa có chữ -> chưa nói", f.fillerCheck(2000).length === 0);
a = f.fillerCheck(3600);
check("filler: quá 2,5 giây chưa có chữ -> speak_filler", has(a, "speak_filler"));
check("filler: chỉ nói MỘT lần mỗi lượt", f.fillerCheck(9000).length === 0);
const f2 = new T.VoiceTurn();
f2.micOn(); f2.turnStart(1000); f2.noteSpoke();
check("filler: đã có chữ ra loa thì không nói", f2.fillerCheck(9000).length === 0);
const f3 = new T.VoiceTurn();
f3.micOn(); f3.turnStart(1000); f3.toolCall("pos_statistics");
check("filler: đang gọi tool thì nói sớm hơn (1,2 giây)", f3.fillerCheck(2300).length === 1);
const f4 = new T.VoiceTurn();
f4.micOn(); f4.turnStart(1000); f4.turnDone();
check("filler: lượt đã xong thì không nói", f4.fillerCheck(9000).length === 0);
const f5 = new T.VoiceTurn();
f5.micOn(); f5.turnStart(1000); f5.fillerCheck(9000); f5.turnDone(); f5.turnStart(20000);
check("filler: lượt mới tính lại từ đầu", f5.fillerCheck(23000).length === 1);

// ---- 7. WebSocket và tool ----
const r = new T.VoiceTurn();
r.micOn(); r.turnStart();
a = r.wsDown();
check("mất WS: reconnecting đè lên processing", r.state === "reconnecting");
a = r.wsUp();
check("WS về: trở lại processing", r.state === "processing");
a = r.toolCall("javis_ui");
check("tool_call: state processing kèm tool", r.state === "processing" && a[a.length - 1].tool === "javis_ui");
a = r.turnDone();
check("turn_done: về listening, tool xoá", r.state === "listening" && r.tool === "");
a = r.errorMic("not-allowed");
check("lỗi mic: state error", r.state === "error");
r.clearError(); r.micOff();
check("micOff: idle", r.state === "idle");
r.setBackground(2); r.setSlow(true);
check("cờ phụ không đổi state", r.state === "idle" && r.background === 2 && r.slow === true);

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - voice-turn");
