/* Điện thoại: chỉ MỘT đường được thu mic lúc nghe, không thì nhận dạng câm (0.59.35).

       node tests/js/test_mic_dien_thoai_mot_duong_thu.js

   Người dùng báo 18/09 (KingHoang, qua chủ dự án): "Nghe được ok rồi. Nhưng CHỈ ĐƯỢC 1 LẦN.
   Làm tươi lại web thì lại không nghe được, phải RESET PERMISSION cho mic lại thì mới nghe
   được tiếp." Và: "mặc dù cấu hình vẫn đang cấp quyền nhưng Javis không nghe được".

   Nguyên nhân KHÔNG phải quyền. Trang thu mic bằng HAI đường độc lập: luồng getUserMedia (đo
   mức âm cho hiệu ứng phát sáng, ngắt lời, ghi âm Groq) và SpeechRecognition, thứ thu bằng
   luồng RIÊNG của nó. Máy tính chạy song song được, điện thoại thì không. Bản cũ mở luồng
   getUserMedia ngay trước recognition.start() rồi GIỮ SUỐT ĐỜI TRANG (không chỗ nào tắt
   track), nên:

     - lần đầu, quyền chưa cấp: getUserMedia treo chờ người bấm Cho phép -> nhận dạng kịp
       chiếm mic trước -> nghe được ĐÚNG MỘT LƯỢT;
     - lượt sau, luồng mic đã nằm sẵn -> nhận dạng không còn mic -> câm;
     - tải lại trang, quyền đã cấp nên getUserMedia trả về tức thì -> chiếm trước -> câm ngay;
     - reset quyền -> hộp xin phép quay lại -> lại trễ -> lại nghe được một lượt.

   Ba triệu chứng, một nguyên nhân: cuộc đua giữa hai đường thu mic.

   Chữa: trên điện thoại, lúc NGHE chỉ để SpeechRecognition giữ mic. Luồng getUserMedia chỉ
   sống lúc Javis ĐỌC, là lúc nhận dạng đã bị abort, nên ngắt lời vẫn nguyên vẹn. */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- Luồng mic giả: đếm số lần được xin, và track có bị tắt hay không ----
function micGia() {
  const d = { soLanXin: 0, tracks: [] };
  const getUserMedia = async () => {
    d.soLanXin++;
    const track = { readyState: "live", stop() { this.readyState = "ended"; } };
    d.tracks.push(track);
    return { getTracks: () => [track] };
  };
  d.conSong = () => d.tracks.filter(t => t.readyState === "live").length;
  return { getUserMedia, d };
}

function nhanDangGia() {
  const d = { soLanStart: 0, soLanAbort: 0, dangMo: null };
  class SRGia {
    start() { d.soLanStart++; d.dangMo = this; setTimeout(() => this.onstart && this.onstart(), 0); }
    stop() { const s = this; setTimeout(() => s.onend && s.onend(), 0); }
    abort() { d.soLanAbort++; const s = this; setTimeout(() => s.onend && s.onend(), 0); }
  }
  return { SRGia, d };
}

function napVoice(SRGia, ua, getUserMedia) {
  const an = () => ({ fftSize: 128, getByteFrequencyData() {}, getByteTimeDomainData() {} });
  const ctx = {
    state: "running", resume() {},
    createMediaStreamSource: () => ({ connect() {} }),
    createAnalyser: an,
  };
  const win = {
    SpeechRecognition: SRGia,
    speechSynthesis: { getVoices: () => [], cancel() {}, speak() {}, speaking: false },
    localStorage: { getItem: () => null, setItem() {} },
    AudioContext: function () { return ctx; },
    isSecureContext: true,
  };
  const doc = { addEventListener() {}, createElement: () => ({ play: () => Promise.resolve() }) };
  const nav = { userAgent: ua, platform: "x", maxTouchPoints: 0, mediaDevices: { getUserMedia } };
  const src = fs.readFileSync(path.join(ROOT, "dashboard", "voice.js"), "utf8");
  const AudioGia = function () { return { play: () => Promise.resolve(), setAttribute() {} }; };
  return new Function("window", "localStorage", "navigator", "document", "Audio",
    src + "; return JavisVoice;")(win, win.localStorage, nav, doc, AudioGia);
}

const cho = (ms) => new Promise(r => setTimeout(r, ms));
const UA_ANDROID = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/128.0 Mobile Safari/537.36";
const UA_IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1";
const UA_PC = "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/128.0 Safari/537.36";

(async () => {
  // ---- 1. Android: LÚC NGHE, luồng getUserMedia không được giữ mic ----
  {
    const { SRGia, d: sr } = nhanDangGia();
    const { getUserMedia, d: mic } = micGia();
    const JavisVoice = napVoice(SRGia, UA_ANDROID, getUserMedia);
    const v = new JavisVoice({});
    check("Android: nhận ra là điện thoại", v._laDiDong() === true);
    v.startListening();
    await cho(20);
    check("Android: nhận dạng VẪN được mở (không phá đường nghe)", sr.soLanStart === 1);
    check("Android: không giữ luồng getUserMedia nào khi đang nghe",
      mic.conSong() === 0 && !v.micStream, `xin=${mic.soLanXin} song=${mic.conSong()}`);

    // Lượt thứ HAI - đúng chỗ bản cũ chết ("chỉ được 1 lần").
    v.userStopped = true;
    v.isListening = false;
    v.startListening();
    await cho(20);
    check("Android: lượt thứ HAI vẫn mở nhận dạng và vẫn không ai giành mic",
      sr.soLanStart === 2 && mic.conSong() === 0, `start=${sr.soLanStart} song=${mic.conSong()}`);
  }

  // ---- 2. Android: luồng mic ĐÃ mở (lúc Javis đọc) phải được TRẢ khi quay lại nghe ----
  {
    const { SRGia } = nhanDangGia();
    const { getUserMedia, d: mic } = micGia();
    const JavisVoice = napVoice(SRGia, UA_ANDROID, getUserMedia);
    const v = new JavisVoice({});
    await v._startMicMeter();               // giả cảnh ngắt lời lúc đọc đã mở luồng mic
    check("Android: lúc đọc thì CÓ mở luồng mic (ngắt lời còn sống)",
      mic.conSong() === 1 && !!v.micStream);
    v.startListening();
    await cho(20);
    check("Android: quay lại nghe thì TẮT track, trả mic cho nhận dạng",
      mic.conSong() === 0 && !v.micStream, `song=${mic.conSong()}`);
  }

  // ---- 3. Android: ngắt lời vẫn mở lại được luồng mic trong lúc đọc ----
  {
    const { SRGia } = nhanDangGia();
    const { getUserMedia, d: mic } = micGia();
    const JavisVoice = napVoice(SRGia, UA_ANDROID, getUserMedia);
    const v = new JavisVoice({});
    v.handsFree = true;
    v.bargeEnabled = true;
    v._giuTaiKhiDoc();                       // đúng thứ _speakNext gọi lúc bắt đầu đọc
    await cho(20);
    check("Android: đang đọc thì ngắt lời vẫn có luồng mic để đo",
      mic.conSong() === 1 && !!v.micStream && !!v.inAnalyser, `song=${mic.conSong()}`);
  }

  // ---- 3b. Luồng mic về MUỘN (đang chờ hộp xin quyền) mà đã quay lại nghe -> phải trả ----
  {
    const { SRGia } = nhanDangGia();
    // getUserMedia treo lại, đúng cảnh hộp xin quyền chờ người bấm Cho phép.
    let moKhoa = null;
    const tracks = [];
    const getUserMedia = () => new Promise((resolve) => {
      moKhoa = () => {
        const t = { readyState: "live", stop() { this.readyState = "ended"; } };
        tracks.push(t);
        resolve({ getTracks: () => [t] });
      };
    });
    const JavisVoice = napVoice(SRGia, UA_ANDROID, getUserMedia);
    const v = new JavisVoice({});
    v.handsFree = true; v.bargeEnabled = true;
    v._giuTaiKhiDoc();                       // Javis bắt đầu đọc -> xin mic, nhưng còn treo
    await cho(5);
    v.startListening();                      // đọc xong, quay lại nghe TRONG LÚC còn treo
    await cho(5);
    moKhoa();                                // giờ người dùng mới bấm Cho phép
    await cho(20);
    check("Android: luồng mic về muộn lúc đang nghe thì bị TRẢ, không gán vào",
      tracks.filter(t => t.readyState === "live").length === 0 && !v.micStream,
      `song=${tracks.filter(t => t.readyState === "live").length} micStream=${!!v.micStream}`);
  }

  // ---- 4. iPhone cũng là điện thoại, cùng luật ----
  {
    const { SRGia } = nhanDangGia();
    const { getUserMedia, d: mic } = micGia();
    const JavisVoice = napVoice(SRGia, UA_IPHONE, getUserMedia);
    const v = new JavisVoice({});
    check("iPhone: nhận ra là điện thoại", v._laDiDong() === true);
    v.startListening();
    await cho(20);
    check("iPhone: không giữ luồng getUserMedia khi đang nghe", mic.conSong() === 0);
  }

  // ---- 5. MÁY TÍNH giữ nguyên hành vi cũ: hai đường chạy song song, có phát sáng ----
  {
    const { SRGia, d: sr } = nhanDangGia();
    const { getUserMedia, d: mic } = micGia();
    const JavisVoice = napVoice(SRGia, UA_PC, getUserMedia);
    const v = new JavisVoice({});
    check("PC: KHÔNG bị coi là điện thoại", v._laDiDong() === false);
    v.startListening();
    await cho(20);
    check("PC: vẫn mở luồng mic cho hiệu ứng phát sáng như cũ",
      mic.conSong() === 1 && !!v.micStream, `song=${mic.conSong()}`);
    check("PC: và nhận dạng vẫn chạy", sr.soLanStart === 1);
  }

  console.log(fails.length ? "\nFAIL: " + fails.join(", ") : "\nTat ca OK");
  process.exit(fails.length ? 1 : 0);
})();
