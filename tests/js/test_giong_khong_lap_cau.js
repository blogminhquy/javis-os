/* Điện thoại: bật mic nói một câu, chữ KHÔNG được dài dần ra thành câu lặp (0.59.33).

       node tests/js/test_giong_khong_lap_cau.js

   Chủ dự án báo 18/09 kèm ảnh chụp màn hình: nói "Em có nghe thấy anh nói gì không" trên
   Chrome Android, tin gửi đi thành "...nghe thấy Em có nghe thấy anh Em có nghe thấy anh nói
   Em có nghe thấy anh nói gì Em có nghe thấy anh nói gì không..." - câu cứ được chép lại,
   mỗi lần dài thêm một chữ.

   Nguyên nhân: trong MỘT sự kiện onresult, Chrome Android giao NHIỀU mảnh kết quả, mà mảnh
   sau là bản DÀI HƠN của mảnh trước (cùng một câu, thêm chữ) chứ không phải đoạn tiếp theo.
   Vòng lặp cũ cộng thẳng `interim += transcript` nên chép lại cả câu ở mỗi mảnh. Bản vá
   0.58.x đã chữa việc cộng dồn QUA các sự kiện, nhưng trong CÙNG một sự kiện thì chưa.

   Chữa: nối các mảnh bằng JavisVoice.ghepManh - mảnh mới phủ đoạn đang có thì thay, đoạn mới
   thật thì mới nối thêm. */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

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
const UA_ANDROID = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/128.0 Mobile Safari/537.36";
const CAU = "Em có nghe thấy anh nói gì không";

(async () => {
  const JavisVoiceTinh = napVoice(nhanDangGia().SRGia, UA_ANDROID);

  // ---- 1. ghepManh: ba nước ghép ----
  {
    const g = JavisVoiceTinh.ghepManh;
    check("ghepManh: mảnh dài hơn phủ đoạn cũ -> thay", g("Em có", "Em có nghe") === "Em có nghe");
    check("ghepManh: trùng khít -> không chép hai lần", g("Em có", "Em có") === "Em có");
    check("ghepManh: bỏ qua hoa thường và dấu câu cuối",
      g("em có nghe", "Em có nghe thấy.") === "Em có nghe thấy.");
    check("ghepManh: đoạn mới thật -> nối thêm",
      g("xem doanh thu", "tuần này") === "xem doanh thu tuần này");
    check("ghepManh: mảnh nhiều chữ đã nằm trong đuôi -> bỏ",
      g("xem doanh thu tuần này", "tuần này") === "xem doanh thu tuần này");
    check("ghepManh: mảnh MỘT chữ trùng đuôi vẫn nối (nói lặp thật)",
      g("anh nói gì không", "không") === "anh nói gì không không");
    check("ghepManh: đoạn rỗng", g("", "Em có") === "Em có" && g("Em có", "") === "Em có");
  }

  // ---- 2. Chrome Android: nhiều mảnh tạm cùng lúc, mảnh sau dài hơn mảnh trước ----
  {
    const { SRGia, d } = nhanDangGia();
    const JavisVoice = napVoice(SRGia, UA_ANDROID);
    const gui = [], tam = [];
    const v = new JavisVoice({ onTranscript: (t) => gui.push(t), onInterim: (t) => tam.push(t) });
    v.silenceMs = 20;
    v.userStopped = true;            // khỏi tự mở lại phiên, test chỉ xét một lượt
    v.startListening();
    await cho(5);
    // Đúng hình dạng Chrome Android giao: cả câu được chép lại, dài dần, trong MỘT event.
    const manh = ["Em có", "Em có nghe", "Em có nghe thấy", "Em có nghe thấy anh",
                  "Em có nghe thấy anh nói", "Em có nghe thấy anh nói gì", CAU];
    d.dangMo.onresult(ketQua(manh.map(t => [t, false])));
    check("Android: chữ tạm hiện đúng MỘT câu, không lặp",
      tam[tam.length - 1] === CAU, JSON.stringify(tam[tam.length - 1]));
    d.dangMo.onresult(ketQua(manh.map(t => [t, true])));   // rồi chốt final cũng dạng dài dần
    await cho(60);
    check("Android: tin gửi đi đúng MỘT câu, không lặp",
      gui.length === 1 && gui[0] === CAU, JSON.stringify(gui));
  }

  // ---- 3. Câu thật nhiều đoạn (final + đuôi tạm) vẫn ghép đủ, không bị cắt ----
  {
    const { SRGia, d } = nhanDangGia();
    const JavisVoice = napVoice(SRGia, UA_ANDROID);
    const gui = [];
    const v = new JavisVoice({ onTranscript: (t) => gui.push(t) });
    v.silenceMs = 20;
    v.userStopped = true;
    v.startListening();
    await cho(5);
    d.dangMo.onresult(ketQua([["xem doanh thu", true], ["tháng này", true], ["so tháng trước", false]]));
    await cho(60);
    check("Android: các đoạn KHÁC nhau vẫn được nối đủ",
      gui.length === 1 && gui[0] === "xem doanh thu tháng này so tháng trước", JSON.stringify(gui));
  }

  console.log(fails.length ? "\nFAIL: " + fails.join(", ") : "\nTat ca OK");
  process.exit(fails.length ? 1 : 0);
})();
