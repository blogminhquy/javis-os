/* Ngắt lời bằng giọng: mẹo NHÁ TIẾNG (0.57.14).

       node tests/js/test_ngat_loi_nha_tieng.js

   Chủ dự án báo 15/09: đang nghe Javis đọc một đoạn dài mà nói chen vào thì nó KHÔNG dừng;
   còn nếu chỉnh cho nhạy hơn thì nó bắt chính tiếng loa ngoài của mình rồi tự câm giữa câu.

   Hai triệu chứng, một gốc: lúc đang đọc, Javis giết hẳn nhận dạng giọng (Web Speech chép
   chính giọng TTS thành tin của người dùng) nên chỉ còn ĐỘ TO của mic làm bằng chứng, mà độ
   to thì giống hệt nhau giữa giọng người và tiếng vọng. Ngưỡng thấp thì nghi oan, ngưỡng cao
   thì điếc. Đường cũ chữa bằng cách tạm dừng rồi đòi nhận dạng trả chữ trong 2 giây, nhưng
   nhận dạng chỉ được mở SAU khi tạm dừng và Chrome mất 0,5 đến 1,5 giây mới có chữ đầu, nên
   một tiếng "thôi" đã nói xong trước khi tai kịp mở.

   Cách mới: đừng đoán, hãy THỬ. Nghi có người nói thì HẠ ÂM LƯỢNG loa xuống một nhá rồi đo
   lại. Vọng đi theo âm lượng nên tụt cả chục lần; giọng người thì không tụt. So mức sau khi
   nhá với mức trước khi nhá là biết, trong 400 ms, không cần chữ.

   Test khoá:
     1. Phép phân biệt (JavisVoice.laNguoiThat) đúng trên các mẫu thật.
     2. Ngưỡng nghi ngờ TỰ HỌC theo nền vọng, không còn đo một lần trong 600 ms đầu.
     3. Nhá tiếng xong mà là vọng thì NÂNG nền rồi đọc tiếp, không dừng.
     4. Âm lượng được áp cho MỌI khúc audio mới, và mọi đường dừng đều trả âm lượng về đầy.
     5. Đạo diễn có bargeConfirmed: dừng hẳn + mở tai, không qua cửa sổ chờ chữ. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const voiceSrc = read("dashboard/voice.js");
const appSrc = read("dashboard/app.js");
const T = require("../../dashboard/voice-turn.js");

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}
const has = (acts, t) => acts.some(a => a.type === t);

// ---- 1. Phép phân biệt vọng / người, chạy THẬT ----
// Nhấc class ra chạy bằng node: voice.js đụng window ở dòng cuối nên nạp phần class thôi.
const classSrc = voiceSrc.slice(voiceSrc.indexOf("class JavisVoice"), voiceSrc.lastIndexOf("window.JavisVoice"));
const JavisVoice = new Function("window", "localStorage", classSrc + "\nreturn JavisVoice;")(
  { speechSynthesis: {}, AudioContext: function () {} },
  { getItem: () => null, setItem: () => {} });

check("hằng số nhá tiếng có mặt",
  JavisVoice.NHA_GAIN === 0.12 && JavisVoice.NHA_TICKS === 4 && JavisVoice.NHA_MIN_HIT === 2);

// Vọng của loa: hạ còn 12% âm lượng thì mức mic tụt theo (0.09 -> ~0.011).
check("vọng loa: nhá xong mức sập -> KHÔNG phải người",
  JavisVoice.laNguoiThat(0.09, [0.012, 0.010, 0.011, 0.009]) === false);
// Giọng người: nhá âm lượng không ảnh hưởng gì tới giọng họ.
check("giọng người: nhá xong mức giữ nguyên -> là người",
  JavisVoice.laNguoiThat(0.09, [0.085, 0.09, 0.08, 0.075]) === true);
// Tiếng "thôi" ngắn: còn tiếng ở 2 nhịp đầu rồi im. Đây chính là ca đường cũ bỏ lọt.
check("tiếng 'thôi' ngắn (2 nhịp rồi im) vẫn tính là người",
  JavisVoice.laNguoiThat(0.09, [0.08, 0.07, 0.008, 0.006]) === true);
// Tiếng ho tắt ngay khi vừa nhá: chỉ 1 nhịp, không đủ.
check("tiếng ho tắt ngay -> không phải người",
  JavisVoice.laNguoiThat(0.09, [0.07, 0.008, 0.006, 0.005]) === false);
// Phòng im hẳn trong lúc nhá.
check("phòng im -> không phải người",
  JavisVoice.laNguoiThat(0.05, [0.004, 0.003, 0.004, 0.003]) === false);
// Loa rất nhỏ (preLevel thấp) thì sàn tuyệt đối giữ cho tiếng ồn lí nhí không thành "người".
check("mức nền lí nhí không vượt sàn NHA_SAN",
  JavisVoice.laNguoiThat(0.01, [0.015, 0.016, 0.014, 0.015]) === false);

// ---- 2. Ngưỡng tự học, không còn hiệu chỉnh một lần ----
check("CANARY: bỏ hẳn kiểu đo nền 600 ms đầu rồi thôi", !/ticks <= 6/.test(voiceSrc));
check("CANARY: bỏ hẳn ngưỡng chết 0.045 viết thẳng trong vòng đo",
  !/Math\.max\(0\.045, baseline/.test(voiceSrc));
check("ngưỡng tính từ nền tự học _echoFloor",
  /const thresh = Math\.max\(JavisVoice\.BARGE_SAN, this\._echoFloor \* 1\.8 \+ 0\.01\);/.test(voiceSrc));
check("nền CHỈ học ở nhịp không nghi ngờ (không kéo theo giọng người)",
  /hits = 0; gan = \[\];\s*\n\s*this\._echoFloor = this\._echoFloor \* 0\.9 \+ rms \* 0\.1;/.test(voiceSrc));
check("nghi ngờ đủ nhịp thì NHÁ TIẾNG, không gọi thẳng _bargeIn",
  /this\._nhaTiengThuXem\(pre\);/.test(voiceSrc));
check("nền hạ dần mỗi lượt đọc mới (cắm tai nghe xong không bị điếc)",
  /this\._echoFloor = this\._echoFloor \* 0\.7;/.test(voiceSrc));
check("chỉ cần 2 nhịp để NGHI NGỜ (nhá tiếng lọc tiếp)", /this\.bargeMinTicks = 2;/.test(voiceSrc));

// ---- 3. Kết luận là vọng thì nâng nền rồi đọc tiếp ----
check("là vọng -> nâng nền THEO BẬC, không nhảy thẳng tới mức vừa đo",
  /this\._echoFloor = Math\.max\(this\._echoFloor, Math\.min\(tran, this\._echoFloor \* 1\.6 \+ 0\.02\)\);/.test(voiceSrc));
check("là vọng -> mở lại bộ rình, KHÔNG dừng đọc",
  /this\._nhoNenVong\(\);\s*\n\s*this\._startBargeMonitor\(\);/.test(voiceSrc));
check("nền vọng được nhớ qua các lần mở trang, có chặn trên chống giá trị rác",
  /localStorage\.setItem\("javis\.nenVong"/.test(voiceSrc)
  && /Math\.min\(0\.3, parseFloat\(localStorage\.getItem\("javis\.nenVong"\)\) \|\| 0\)/.test(voiceSrc));

// Leo bậc chạy thật: một tiếng ho to (0.2) chỉ đẩy được một bậc nhỏ, không treo nền lên 0.21.
const leo = (nen, pre) => Math.max(nen, Math.min(pre * 1.05, nen * 1.6 + 0.02));
check("ho to một lần: nền chỉ leo một bậc", Math.abs(leo(0.005, 0.2) - 0.028) < 1e-9, leo(0.005, 0.2));
check("vọng thật lặp lại: sau vài nhá thì tới nơi", leo(leo(leo(0.005, 0.08), 0.08), 0.08) >= 0.08 * 0.8);
check("nền đã cao hơn thì không bị hạ xuống", leo(0.15, 0.05) === 0.15);
check("là người -> gọi _bargeIn kèm lưới an toàn mở lại bộ rình nếu không ai dừng",
  /if \(laNguoi\) \{\s*\n\s*this\._bargeIn\(\);/.test(voiceSrc)
  && /if \(this\.isPlaying && !this\._paused\) this\._startBargeMonitor\(\);/.test(voiceSrc));

// ---- 4. Âm lượng: áp cho mọi khúc, trả về đầy ở mọi đường dừng ----
const apDung = (voiceSrc.match(/this\._apAmLuong\(/g) || []).length;
check("_apAmLuong được gọi ở cả hai đường phát và hai đường dọn", apDung >= 5, apDung);
check("đường iOS (Audio dùng lại) cũng áp âm lượng",
  /this\.currentAudio = a;\s*\n\s*this\._apAmLuong\(a\);/.test(voiceSrc));
check("đường thường (Audio mới mỗi khúc) cũng áp âm lượng",
  /this\.currentAudio = audio;\s*\n\s*this\._apAmLuong\(audio\);/.test(voiceSrc));
check("stopSpeaking huỷ cuộc thăm dò dở", /this\._stopBargeMonitor\(\);\s*\n\s*this\._huyNha\(\);/.test(voiceSrc));
check("pauseSpeaking cũng huỷ", (voiceSrc.match(/this\._huyNha\(\);/g) || []).length >= 2);

// Chạy thật _apAmLuong để chắc con số đúng chiều.
const v = Object.create(JavisVoice.prototype);
v._dangNha = true;
const fake = { volume: 1 };
v._apAmLuong(fake);
check("đang nhá -> âm lượng xuống 12%", fake.volume === 0.12, fake.volume);
v._dangNha = false;
v._apAmLuong(fake);
check("hết nhá -> âm lượng về đầy", fake.volume === 1, fake.volume);

// ---- 5. Đạo diễn: bargeConfirmed dừng hẳn, không chờ chữ ----
const b = new T.VoiceTurn();
b.micOn(); b.ttsStart();
let a = b.bargeConfirmed("doanh thu tuần này là");
check("bargeConfirmed: stop_tts kèm interrupted + mở tai",
  has(a, "stop_tts") && a.find(x => x.type === "stop_tts").interrupted === true && has(a, "listen"));
check("bargeConfirmed: KHÔNG có pause_tts (không còn cửa sổ chờ chữ 2 giây)", !has(a, "pause_tts"));
check("bargeConfirmed: nhớ phần đã đọc để tin kế tiếp mang ngắt_lời",
  b.interruptedAt === "doanh thu tuần này là");
check("bargeConfirmed: sang user_speaking, hết speaking", b.state === "user_speaking" && b.speaking === false);
check("bargeConfirmed khi KHÔNG đang đọc: không làm gì", new T.VoiceTurn().bargeConfirmed("x").length === 0);
// Đường cũ vẫn còn nguyên (voice.js dùng làm dự phòng khi nơi gọi chưa gắn onBargeConfirm).
const b2 = new T.VoiceTurn();
b2.micOn(); b2.ttsStart();
check("đường cũ bargeStart vẫn còn dùng được", has(b2.bargeStart(), "pause_tts"));

// ---- 6. Chạy THẬT cả vòng, bằng đồng hồ giả ----
// Đo trên trang thật 15/09 bắt được một lỗi mà test theo mẫu chữ không thấy: dòng gieo nền
// bằng mẫu đầu tiên làm ngưỡng lập tức thành 1,8 lần mức đang đo, nên chính mức ấy không bao
// giờ vượt nổi ngưỡng của nó và bộ rình tê liệt hoàn toàn. Vì vậy phải có một test CHẠY cả
// vòng chứ không chỉ soi mã. Đồng hồ giả để chạy tức thì, không phải chờ vài giây thật.
function dungDongHo() {
  let now = 0, id = 0;
  const timers = new Map();
  const api = {
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
    },
    bayGio: () => now
  };
  return api;
}

const dh = dungDongHo();
const Lop = new Function("window", "localStorage", "setInterval", "clearInterval", "setTimeout", "clearTimeout",
  classSrc + "\nreturn JavisVoice;")(
  // SpeechRecognition giả: chỉ để _initRecognition không kêu "trình duyệt không hỗ trợ".
  // Ngắt lời KHÔNG dùng tới nhận dạng nữa, đó chính là điểm của đợt sửa này.
  { speechSynthesis: { getVoices: () => [], speak() {}, cancel() {} },
    SpeechRecognition: function () { this.start = function () {}; this.stop = function () {}; this.abort = function () {}; } },
  { getItem: () => null, setItem: () => {} },
  dh.setInterval, dh.clearInterval, dh.setTimeout, dh.clearTimeout);

// Phòng có loa ngoài: vọng đi THEO âm lượng loa, giọng người thì không.
// LƯU Ý: dựng đúng luồng THẬT của hội thoại rảnh tay, tức `_resumeAfterTTS = false` và mic đã
// ĐÓNG (isListening false). Đặt cờ ấy thành true là dựng một tình huống không bao giờ xảy ra
// và test sẽ xanh trong khi người dùng thật không ngắt lời được - đúng chuyện đã xảy ra 15/09.
function dungPhong(mucVong) {
  const v = new Lop({ lang: "vi-VN" });
  v.bargeEnabled = true; v.handsFree = true; v.isPlaying = true; v.micStream = {};
  v._resumeAfterTTS = false; v.isListening = false;
  v._echoFloor = 0;
  v.currentAudio = { volume: 1, pause() {}, play() { return Promise.resolve(); } };
  v.giongNguoi = 0;
  v.soLanNha = 0;
  const goc = v._nhaTiengThuXem.bind(v);
  v._nhaTiengThuXem = (p) => { v.soLanNha++; goc(p); };
  v.inAnalyser = { fftSize: 128, getByteTimeDomainData(arr) {
    const rms = Math.sqrt(Math.pow(mucVong * v.currentAudio.volume, 2) + Math.pow(v.giongNguoi, 2));
    const c = Math.round(rms * 128);
    for (let i = 0; i < arr.length; i++) arr[i] = 128 + c;
  } };
  v.dungLuc = 0;
  v.onBargeConfirm = () => { v.dungLuc = dh.bayGio(); v.isPlaying = false; };
  return v;
}

// Ca 1: loa ngoài vọng liên tục, KHÔNG có ai nói. Javis phải đọc hết, không tự ngắt lời mình.
const p1 = dungPhong(0.078);
p1._startBargeMonitor();
dh.chay(3000);
check("vọng loa suốt 3 giây: Javis KHÔNG tự ngắt lời mình", p1.dungLuc === 0);
check("vọng loa: nền tự học lên đủ cao để thôi nghi ngờ", p1._echoFloor > 0.03, p1._echoFloor);
check("vọng loa: chỉ nhá tiếng vài lần rồi yên", p1.soLanNha <= 3, p1.soLanNha);
check("vọng loa: âm lượng đã trả về đầy", p1.currentAudio.volume === 1);
check("vọng loa: vẫn đang đọc", p1.isPlaying === true);
p1._stopBargeMonitor(); p1._huyNha();

// Ca 2: nền đã học xong, người nói chen một tiếng "thôi" NGẮN (400 ms) rồi im.
// Đây đúng ca đường cũ bỏ lọt: nhận dạng chưa kịp mở thì tiếng đã dứt.
const p2 = dungPhong(0.078);
p2._startBargeMonitor();
dh.chay(2500);
const batDauNoi = dh.bayGio();
p2.giongNguoi = 0.15;
dh.chay(400);
p2.giongNguoi = 0;
dh.chay(900);
check("nói 'thôi' 400 ms: Javis DỪNG đọc", p2.dungLuc > 0);
check("dừng trong vòng 700 ms kể từ lúc bắt đầu nói",
  p2.dungLuc > 0 && p2.dungLuc - batDauNoi <= 700, p2.dungLuc - batDauNoi);
check("dừng rồi thì âm lượng trả về đầy (khúc sau không bị câm)", p2.currentAudio.volume === 1);
p2._stopBargeMonitor(); p2._huyNha();

// Ca 2b: MẮT XÍCH ĐÃ LÀM HỎNG TẤT CẢ (15/09). Trong hội thoại rảnh tay, nói xong là đồng hồ
// im lặng đóng mic TRƯỚC khi câu trả lời kịp đọc, nên _muteRecognition() thoát ngay và không
// đặt _resumeAfterTTS. Bản cũ lấy đúng cờ ấy làm điều kiện rình, nên ngắt lời chưa từng chạy
// một lần nào dù mọi thứ bên dưới đều đúng. Chốt đúng là "đang nói chuyện bằng giọng".
const p2b = dungPhong(0.078);
check("mic đã đóng + chưa từng có _resumeAfterTTS (đúng luồng thật)",
  p2b.isListening === false && p2b._resumeAfterTTS === false);
p2b._startBargeMonitor();
check("vẫn rình được nhờ cờ rảnh tay", p2b._bargeTimer !== null && p2b._bargeTimer !== undefined);
p2b._stopBargeMonitor();
p2b.handsFree = false;
p2b._startBargeMonitor();
check("tắt rảnh tay thì KHÔNG rình (quay về gõ chữ là Javis đọc trong im lặng)",
  !p2b._bargeTimer);
p2b._stopBargeMonitor(); p2b._huyNha();
check("_pumpQueue giữ luồng mic sống khi đang rảnh tay", /this\._giuTaiKhiDoc\(\);/.test(voiceSrc));
check("_giuTaiKhiDoc nối bộ đo xong mới mở bộ rình (async)",
  /this\._startMicMeter\(\)\.then\(\(\) => this\._startBargeMonitor\(\)\)/.test(voiceSrc));
check("app.js đồng bộ cờ rảnh tay sang voice.js",
  /voice\.handsFree = handsFree && voiceMode !== "live";/.test(appSrc)
  && /voice\.handsFree = false;/.test(appSrc));

// Ca 3: tiếng ho 200 ms giữa lúc đang đọc -> không được cắt câu.
const p3 = dungPhong(0.078);
p3._startBargeMonitor();
dh.chay(2500);
p3.giongNguoi = 0.3;
dh.chay(200);
p3.giongNguoi = 0;
dh.chay(1200);
check("tiếng ho 200 ms: KHÔNG cắt câu", p3.dungLuc === 0 && p3.isPlaying === true);
p3._stopBargeMonitor(); p3._huyNha();

// ---- 7. app.js đã gắn móc mới ----
check("app.js gắn onBargeConfirm vào đạo diễn",
  /onBargeConfirm: \(\) => runActions\(turn\.bargeConfirmed\(voice\.lastSpokenPrefix\(\)\)\)/.test(appSrc));
check("voice.js ưu tiên onBargeConfirm hơn onBargeStart",
  voiceSrc.indexOf("this.onBargeConfirm) {") < voiceSrc.indexOf("if (this.onBargeStart) { try { this.onBargeStart(); return;"));

console.log(fails.length ? "\n" + fails.length + " FAIL" : "\nTat ca OK");
process.exit(fails.length ? 1 : 0);
