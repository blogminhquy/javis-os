/* iPhone: chữ nghe được KHÔNG được bốc hơi khi WebKit không bao giờ chốt "final" (0.58.4).

       node tests/js/test_ios_chu_tam_khong_mat.js

   Chủ dự án báo 15/09: trên iPhone, nói chuyện một đoạn dài rồi thì sau đó nói vẫn nghe thấy,
   chữ cam nhạt (bong bóng nháp) vẫn hiện, nhưng nói xong là chữ biến mất mà không đi vào
   khung chat.

   Nguyên nhân: onend chỉ gửi `accumulatedTranscript`, mà biến ấy chỉ gom các kết quả có
   `isFinal = true`. WebKit trên iOS hay giao TOÀN chữ tạm (isFinal = false) rồi kết thúc
   phiên mà không bao giờ chốt final, nhất là sau nhiều lượt mở/đóng phiên. Chữ tạm đã hiện
   trên màn hình, nhưng tới onend thì finalText rỗng, onTranscript không được gọi, và vòng
   giữ mic mở phiên mới rồi xoá bong bóng nháp. Người dùng thấy đúng cảnh "hiện rồi mất".

   Chữa: nhớ đuôi chữ tạm của sự kiện onresult cuối; onend mà final không phủ đuôi ấy thì
   ghép đuôi vào. Chrome máy tính chốt final trước onend nên đuôi rỗng, không đổi gì. */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// SpeechRecognition giả: start() mở phiên; test tự bắn onresult/onend theo kịch bản.
function nhanDangGia() {
  const d = { soLanStart: 0, dangMo: null };
  class SRGia {
    start() { d.soLanStart++; d.dangMo = this; setTimeout(() => this.onstart && this.onstart(), 0); }
    stop() { const s = this; setTimeout(() => s.onend && s.onend(), 0); }
    abort() { const s = this; setTimeout(() => s.onend && s.onend(), 0); }
  }
  return { SRGia, d };
}

function napVoice(SRGia, ua) {
  const win = {
    SpeechRecognition: SRGia,
    speechSynthesis: { getVoices: () => [], cancel() {}, speak() {}, speaking: false },
    localStorage: { getItem: () => null, setItem() {} },
    AudioContext: null,
    isSecureContext: true,
  };
  const doc = { addEventListener() {}, createElement: () => ({ play: () => Promise.resolve() }) };
  const src = fs.readFileSync(path.join(ROOT, "dashboard", "voice.js"), "utf8");
  // Audio giả cho _moKhoaAudioIOS (iOS mở khoá phần tử phát tiếng ngay khi bấm mic).
  const AudioGia = function () { return { play: () => Promise.resolve(), setAttribute() {} }; };
  return new Function("window", "localStorage", "navigator", "document", "Audio",
    src + "; return JavisVoice;")(win, win.localStorage,
      { userAgent: ua, platform: "x", mediaDevices: null }, doc, AudioGia);
}

// Kết quả nhận dạng giả: mảng [chữ, isFinal].
function ketQua(cac) {
  return { resultIndex: 0, results: cac.map(([t, f]) => Object.assign([{ transcript: t }], { isFinal: f })) };
}

const cho = (ms) => new Promise(r => setTimeout(r, ms));
const UA_IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1";
const UA_CHROME = "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/128.0 Safari/537.36";

(async () => {
  // ---- 1. iPhone: chỉ có chữ tạm, không bao giờ final -> vẫn phải gửi ----
  {
    const { SRGia, d } = nhanDangGia();
    const JavisVoice = napVoice(SRGia, UA_IPHONE);
    const gui = [], tam = [];
    const v = new JavisVoice({ onTranscript: (t) => gui.push(t), onInterim: (t) => tam.push(t) });
    v.silenceMs = 20;
    v.startListening();
    await cho(5);
    check("iOS: nhận là iOS (phiên không liên tục)", v._laIOS() === true && v.recognition.continuous === false);
    d.dangMo.onresult(ketQua([["cho anh hỏi", false]]));
    d.dangMo.onresult(ketQua([["cho anh hỏi doanh thu tuần này", false]]));
    check("iOS: chữ tạm đã hiện lên màn hình", tam[tam.length - 1] === "cho anh hỏi doanh thu tuần này");
    await cho(60);   // đồng hồ im lặng nổ -> stop() -> onend, KHÔNG có final nào
    check("iOS: onend không có final vẫn GỬI đúng câu đã hiện",
      gui.length === 1 && gui[0] === "cho anh hỏi doanh thu tuần này", JSON.stringify(gui));
    check("iOS: không tự mở lại phiên (mỗi lượt nói là một phiên)", d.soLanStart === 1);
  }

  // ---- 2. Chrome máy tính: final chốt trước onend -> gửi đúng một lần, không lặp đuôi ----
  {
    const { SRGia, d } = nhanDangGia();
    const JavisVoice = napVoice(SRGia, UA_CHROME);
    const gui = [];
    const v = new JavisVoice({ onTranscript: (t) => gui.push(t) });
    v.silenceMs = 20;
    v.startListening();
    await cho(5);
    d.dangMo.onresult(ketQua([["xem doanh thu", false]]));
    d.dangMo.onresult(ketQua([["Xem doanh thu tháng này.", true]]));   // Chrome chốt lại, đổi hoa/dấu
    await cho(60);
    check("Chrome: final phủ chữ tạm -> gửi đúng câu final, không ghép đuôi cũ",
      gui.length === 1 && gui[0] === "Xem doanh thu tháng này.", JSON.stringify(gui));
  }

  // ---- 3. Chrome: final một phần + đuôi tạm còn dở lúc onend -> ghép, không mất đuôi ----
  {
    const { SRGia, d } = nhanDangGia();
    const JavisVoice = napVoice(SRGia, UA_CHROME);
    const gui = [];
    const v = new JavisVoice({ onTranscript: (t) => gui.push(t) });
    v.silenceMs = 20;
    v.startListening();
    await cho(5);
    d.dangMo.onresult(ketQua([["xem doanh thu", true], ["tuần này", false]]));
    await cho(60);
    check("Chrome: đuôi tạm chưa chốt lúc onend được ghép vào",
      gui.length === 1 && gui[0] === "xem doanh thu tuần này", JSON.stringify(gui));
  }

  // ---- 4. Mic bị tạm ngừng vì Javis đọc: bỏ cả chữ tạm, không gửi ----
  {
    const { SRGia, d } = nhanDangGia();
    const JavisVoice = napVoice(SRGia, UA_IPHONE);
    const gui = [];
    const v = new JavisVoice({ onTranscript: (t) => gui.push(t) });
    v.startListening();
    await cho(5);
    d.dangMo.onresult(ketQua([["tiếng của loa lọt vào", false]]));
    v._muteRecognition();
    await cho(10);
    check("mute: chữ tạm lỡ nghe bị bỏ, không gửi", gui.length === 0, JSON.stringify(gui));
  }

  // ---- 5. Lượt mới không kéo đuôi tạm của lượt trước sang ----
  {
    const { SRGia, d } = nhanDangGia();
    const JavisVoice = napVoice(SRGia, UA_IPHONE);
    const gui = [];
    const v = new JavisVoice({ onTranscript: (t) => gui.push(t) });
    v.silenceMs = 20;
    v.startListening();
    await cho(5);
    d.dangMo.onresult(ketQua([["câu một", false]]));
    await cho(60);
    v.startListening();
    await cho(5);
    d.dangMo.onresult(ketQua([["câu hai", false]]));
    await cho(60);
    check("hai lượt riêng: gửi đúng hai câu, không dính nhau",
      gui.length === 2 && gui[0] === "câu một" && gui[1] === "câu hai", JSON.stringify(gui));
  }

  console.log(fails.length ? `\n${fails.length} FAIL` : "\nOK");
  process.exit(fails.length ? 1 : 0);
})();
