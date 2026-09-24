/* Nói chen vào lúc Javis ĐANG NGHĨ, và khúc audio treo im không được làm câm cả câu (0.57.17).

       node tests/js/test_noi_chen_khi_dang_nghi.js

   Chủ dự án báo 15/09, hai chuyện:
     1. "khi đang suy nghĩ để phản hồi thì không nói cắt ngang cũng như nói thêm ngữ cảnh được"
     2. "đôi khi trả lời xong hết nhưng mà không phát voice luôn"

   Chuyện 1: vòng giữ mic trong app.js đòi `!isProcessing` nên mic ĐÓNG suốt thời gian xử lý
   (có khi vài chục giây). Người dùng nói vào chỗ trống, không ai nghe. Bỏ chốt ấy đi thì tin
   nói lúc đang nghĩ đi qua sendMessage: dừng lượt cũ rồi gửi lại. Nhưng phải HOÃN cái gửi lại
   tới khi `turn_done` về, vì server từ chối tin mới khi phiên còn job ("Phiên này đang trả
   lời") mà lệnh Dừng chỉ huỷ job chứ không kết thúc nó tức thì.

   Chuyện 2: thẻ <audio> có thể tắc mà KHÔNG bắn 'error' lẫn 'ended' (stream Edge TTS đứt nửa
   chừng). Chuỗi đọc dừng tại đó, `isPlaying` kẹt true nên enqueueSpeak chỉ xếp hàng chứ không
   mở đọc lại: cả phần còn lại của câu trả lời câm, không có lỗi nào hiện ra. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const app = read("dashboard/app.js");
const voiceSrc = read("dashboard/voice.js");

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- 1. Mic mở cả khi đang xử lý ----
const vongGiu = (app.match(/if \(handsFree && voiceMode !== "live"[\s\S]*?\}, 500\);/) || [""])[0];
check("tìm được vòng giữ mic", !!vongGiu);
check("CANARY: vòng giữ mic KHÔNG còn đòi !isProcessing", !/!isProcessing/.test(vongGiu));
check("vẫn không mở mic trong lúc Javis đang ĐỌC (ngắt lời lo phần đó)",
  /!voice\.isSpeaking\(\)/.test(vongGiu));
check("vẫn chỉ mở khi đang rảnh tay và không phải bậc Live",
  /handsFree && voiceMode !== "live"/.test(vongGiu));
check("vẫn giữ chốt mic hỏng (không mở lại vô hạn khi mic chết)",
  /micHong/.test(vongGiu));

// Execute the production keepalive body with capture closed before first audio.
const keepaliveBody = vongGiu.slice(0, vongGiu.lastIndexOf("}, 500);"));
const keepalive = new Function("handsFree", "voiceMode", "voice", "adaptive", keepaliveBody);
const starts = [];
const pendingVoice = {
  isListening: false, isTranscribing: false, _awaitingFirstAudio: true,
  isSpeaking: () => true, micHong: () => false,
  startListening: (...args) => starts.push(args)
};
keepalive(true, "standard", pendingVoice, {canListen: () => true});
check("closed mic reopens while audio loads without cancelling queued audio",
  starts.length === 1 && starts[0][0] === true && starts[0][1] === true);
pendingVoice._awaitingFirstAudio = false;
keepalive(true, "standard", pendingVoice, {canListen: () => true});
check("actual playback leaves capture to the barge-in controller", starts.length === 1);
pendingVoice._awaitingFirstAudio = true;
keepalive(true, "standard", pendingVoice, {canListen: () => false});
check("hidden/suspended adaptive session cannot reopen capture", starts.length === 1);

// ---- 2. Tin chen ngang được HOÃN tới khi lượt cũ dừng hẳn ----
check("sendMessage: đang chạy + tin từ mic -> stopCurrent rồi ĐẶT TIN CHỜ, không gửi ngay",
  /stopCurrent\(\);\s*\n\s*datTinCho\(msg, opts\);[\s\S]{0,80}return;/.test(app));
check("turn_done tới thì mới gửi tin đang chờ",
  /if \(isActive && _tinChoLuot\) guiTinCho\(\);/.test(app));
check("có lưới thời gian phòng khi lượt cũ chết mà không báo turn_done",
  /_tinChoTimer = setTimeout\(guiTinCho, 5000\);/.test(app));
// 0.58.4: lưới 1,5 giây nổ TRƯỚC turn_done là tin gửi đúng lúc server còn job (bị từ chối),
// hoặc turn_done cũ về sau và xoá sạch lượt mới. Lưới phải rộng hơn thời gian giết engine.
check("lưới không còn là 1,5 giây", !/setTimeout\(guiTinCho, 1500\)/.test(app));
check("trong lúc chờ, câu vừa nói vẫn ở lại màn hình (bong bóng nháp)",
  /function datTinCho\(text, opts\) \{[\s\S]{0,550}nhapGiong\(_tinChoLuot\)/.test(app));
check("lượt bị dừng được ghi nhớ theo id, và turn_done muộn của nó không đụng lượt mới",
  /_luotDaDung\[sid\] = turns\[sid\]\.id/.test(app)
  && /if \(t && t\.id && t\.id !== _idDung\) return;/.test(app));
check("khung của lượt mới về thì thôi chờ turn_done cũ (không kẹt cờ running)",
  /t\.id !== _luotDaDung\[sid\]\) delete _luotDaDung\[sid\];/.test(app));
check("socket nối lại thì xoá sạch danh sách chờ", /_luotDaDung = \{\};\s*\/\/ socket mới/.test(app));

// Chạy THẬT cặp datTinCho/guiTinCho lấy từ nguồn, để chắc nó không gửi hai lần.
const src = (app.match(/let _tinChoLuot = null, _tinChoTimer = null;[\s\S]*?\n\}\n/) || [""])[0]
  + (app.match(/function guiTinCho\(\) \{[\s\S]*?\n\}/) || [""])[0];
check("nhấc được cặp hàm tin chờ", src.indexOf("function guiTinCho") > 0);
const daGui = [];
const moPhong = new Function("sendMessage", "setTimeout", "clearTimeout",
  src + "\nreturn { datTinCho: datTinCho, guiTinCho: guiTinCho, xem: () => _tinChoLuot };");
const api = moPhong((t) => daGui.push(t), () => 1, () => {});
api.datTinCho("nói thêm cái này nữa");
check("đặt xong thì tin nằm chờ, chưa gửi", api.xem() === "nói thêm cái này nữa" && daGui.length === 0);
api.guiTinCho();
check("turn_done về thì gửi đúng một lần", daGui.length === 1 && daGui[0] === "nói thêm cái này nữa");
api.guiTinCho();
check("gọi lần hai (lưới thời gian nổ muộn) KHÔNG gửi lặp", daGui.length === 1);

// ---- 3. Khúc audio treo im thì đi tiếp, không làm câm cả câu ----
check("có bộ canh treo cho khúc audio", /_canhTreo\(audio, onFail\);/.test(voiceSrc));
check("đường iOS cũng được canh", /this\._canhTreo\(a, onFail\);/.test(voiceSrc));
check("hai ngưỡng: chưa phát chờ rộng tay, đang phát cắt sớm",
  /TREO_CHUA_PHAT = 12/.test(voiceSrc) && /TREO_DANG_PHAT = 6/.test(voiceSrc)
  && /im >= \(t > 0 \? JavisVoice\.TREO_DANG_PHAT : JavisVoice\.TREO_CHUA_PHAT\)/.test(voiceSrc));
check("tạm dừng có chủ ý KHÔNG bị tính là treo", /if \(this\._paused\) \{ im = 0; return; \}/.test(voiceSrc));
check("audio đã đổi hoặc đã hết thì thôi canh",
  /if \(this\.currentAudio !== audio \|\| audio\.ended\) \{ this\._huyCanhTreo\(\); return; \}/.test(voiceSrc));
check("huỷ canh ở onended và ở stopSpeaking",
  (voiceSrc.match(/this\._huyCanhTreo\(\);/g) || []).length >= 4);
check("giọng lỗi phải báo lên giao diện",
  /this\.onPlaybackError\("tts-unavailable"\)/.test(voiceSrc));

// Chạy thật vòng canh treo bằng đồng hồ giả: audio đứng im -> phải gọi onFail.
const classSrc = voiceSrc.slice(voiceSrc.indexOf("class JavisVoice"), voiceSrc.lastIndexOf("window.JavisVoice"));
function dungDongHo() {
  let now = 0, id = 0;
  const timers = new Map();
  return {
    setInterval: (fn, ms) => { timers.set(++id, { fn, ms, next: now + ms, rep: true }); return id; },
    setTimeout: (fn, ms) => { timers.set(++id, { fn, ms, next: now + ms, rep: false }); return id; },
    clearInterval: (i) => timers.delete(i),
    clearTimeout: (i) => timers.delete(i),
    chay: (ms) => {
      const het = now + ms;
      while (true) {
        let som = null, somId = 0;
        for (const [k, t] of timers) if (t.next <= het && (som === null || t.next < som.next)) { som = t; somId = k; }
        if (!som) break;
        now = som.next;
        if (som.rep) som.next = now + som.ms; else timers.delete(somId);
        som.fn();
      }
      now = het;
    }
  };
}
const dh = dungDongHo();
const Lop = new Function("window", "localStorage", "setInterval", "clearInterval", "setTimeout", "clearTimeout",
  classSrc + "\nreturn JavisVoice;")(
  { speechSynthesis: { getVoices: () => [], speak() {}, cancel() {} },
    SpeechRecognition: function () { this.start = function () {}; this.stop = function () {}; this.abort = function () {}; } },
  { getItem: () => null, setItem: () => {} },
  dh.setInterval, dh.clearInterval, dh.setTimeout, dh.clearTimeout);

// Khúc chưa bao giờ ra tiếng (Edge tổng hợp mãi không xong).
let hong = 0;
let v = new Lop({ lang: "vi-VN" });
let au = { currentTime: 0, ended: false };
v.currentAudio = au;
v._canhTreo(au, () => hong++);
dh.chay(11000);
check("chưa ra tiếng: 11 giây vẫn kiên nhẫn chờ", hong === 0);
dh.chay(2000);
check("chưa ra tiếng: quá 12 giây thì coi là hỏng, đi tiếp", hong === 1);

// Khúc đang phát bình thường: không được đụng vào.
hong = 0;
v = new Lop({ lang: "vi-VN" });
au = { currentTime: 0, ended: false };
v.currentAudio = au;
v._canhTreo(au, () => hong++);
for (let s = 0; s < 20; s++) { au.currentTime += 1; dh.chay(1000); }
check("đang phát đều: không bao giờ bị cắt oan", hong === 0);

// Đang phát rồi đứng im giữa chừng (stream đứt).
au.currentTime = 20;
dh.chay(5000);
check("đang phát mà đứng im 5 giây: chưa cắt", hong === 0);
dh.chay(2000);
check("đứng im quá 6 giây: cắt, cho cả câu đi tiếp", hong === 1);

// Tạm dừng có chủ ý (nghi chen ngang) thì không tính là treo.
hong = 0;
v = new Lop({ lang: "vi-VN" });
au = { currentTime: 3, ended: false };
v.currentAudio = au;
v._paused = true;
v._canhTreo(au, () => hong++);
dh.chay(30000);
check("đang TẠM DỪNG thì không bị coi là treo", hong === 0);

console.log(fails.length ? "\n" + fails.length + " FAIL" : "\nTat ca OK");
process.exit(fails.length ? 1 : 0);
