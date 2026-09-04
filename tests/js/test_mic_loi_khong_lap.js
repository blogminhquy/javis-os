// Mic hong thi PHAI DUNG, khong duoc thu lai vo tan.
//
//     node tests/js/test_mic_loi_khong_lap.js
//
// Loi that, nguoi dung bao 04/09 kem anh chup: hop thoai "Ban can cap quyen microphone cho
// trang nay" hien LIEN TUC va khong tat di duoc, phai dong tab.
//
// Co HAI vong lap, va phai chan ca hai:
//
//   1. `onend` tu mo lai phien khi `userStopped` con false. Loi 'not-allowed' khong dat co do,
//      nen: start -> onerror -> alert -> onend -> start -> onerror -> ...
//   2. Vong giu mic cua che do ranh tay trong app.js chay 500ms MOT LAN. Alert la hop CHAN,
//      nen bam OK xong nua giay sau no no tiep - khong con duong nao bam vao trang nua.
//
// Test nay NAP THAT voice.js va cho chay voi mot SpeechRecognition gia luon bao 'not-allowed'.
// Canary quet chu khong bat duoc loai loi nay: ma nguon van "co ve" dung.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- SpeechRecognition gia: start() luon that bai voi ma loi dat truoc ----
function nhanDangGia(maLoi) {
  const d = { soLanStart: 0 };
  class SRGia {
    start() {
      d.soLanStart++;
      // Trinh duyet that bao loi roi ket thuc phien - dung thu tu do.
      setTimeout(() => {
        if (this.onerror) this.onerror({ error: maLoi });
        if (this.onend) this.onend();
      }, 0);
    }
    stop() {}
    abort() {}
  }
  return { SRGia, d };
}

function napVoice(SRGia) {
  const win = {
    SpeechRecognition: SRGia,
    speechSynthesis: { getVoices: () => [], cancel() {}, speak() {} },
    localStorage: { getItem: () => null, setItem() {} },
    AudioContext: null,
    isSecureContext: true,
  };
  const doc = { addEventListener() {}, createElement: () => ({ play: () => Promise.resolve() }) };
  const src = fs.readFileSync(path.join(ROOT, "dashboard", "voice.js"), "utf8");
  return new Function("window", "localStorage", "navigator", "document",
    src + "; return JavisVoice;")(win, win.localStorage,
      { userAgent: "node", platform: "x", mediaDevices: null }, doc);
}

const cho = (ms) => new Promise(r => setTimeout(r, ms));

(async () => {
  for (const maLoi of ["not-allowed", "service-not-allowed", "audio-capture"]) {
    const { SRGia, d } = nhanDangGia(maLoi);
    const JavisVoice = napVoice(SRGia);
    const loi = [];
    const v = new JavisVoice({ onError: (e) => loi.push(e) });

    v.startListening();
    await cho(60);          // du cho vai vong lap no ra neu con bug

    check(`'${maLoi}': chi thu DUNG MOT lan, khong lap vo tan`, d.soLanStart === 1);
    check(`'${maLoi}': chi bao loi mot lan, khong dap hop thoai lien tuc`, loi.length === 1);
    check(`'${maLoi}': ghi nho la mic hong han`, v.micHong() === maLoi);

    // Duong TU DONG (vong giu mic cua che do ranh tay) khong duoc go cua nua.
    v.startListening(true);
    await cho(60);
    check(`'${maLoi}': duong tu dong bi chan, khong thu lai`, d.soLanStart === 1);
    check(`'${maLoi}': va khong bao loi them lan nao`, loi.length === 1);
  }

  // Nguoi dung BAM NUT thi phai duoc thu lai: ho co the vua cap quyen trong cai dat trinh
  // duyet xong. Mot cai nut bam khong len la thu khong ai chan doan noi.
  {
    const { SRGia, d } = nhanDangGia("not-allowed");
    const JavisVoice = napVoice(SRGia);
    const v = new JavisVoice({ onError: () => {} });
    v.startListening();
    await cho(60);
    v.startListening();          // khong co co tuDong = nguoi dung bam
    await cho(60);
    check("nguoi dung bam nut thi VAN duoc thu lai", d.soLanStart === 2);
  }

  // Loi thoang qua thi khong duoc coi la hong han - mat han kha nang tu hoi phuc.
  {
    const { SRGia, d } = nhanDangGia("network");
    const JavisVoice = napVoice(SRGia);
    const v = new JavisVoice({ onError: () => {} });
    v.startListening();
    await cho(60);
    check("loi mang KHONG bi coi la hong han", !v.micHong());
  }

  // ---- app.js: hai chot chan vong 500ms ----
  const APP = fs.readFileSync(path.join(ROOT, "dashboard", "app.js"), "utf8");
  check("vong giu mic kiem micHong truoc khi mo lai", /micHong\(\)\)\s*\)\s*\{[\s\S]{0,120}startListening\(true\)/.test(APP)
    || (APP.includes("!(voice.micHong && voice.micHong())") && APP.includes("startListening(true)")));
  check("mic hong thi TAT han che do ranh tay", APP.includes("tatRanhTay()"));
  // Cau "hay cap quyen" la loi khuyen KHONG LAM DUOC khi trang khong o ngu canh bao mat:
  // trinh duyet chan thang va khong he hoi quyen, nen khong co nut nao de bam.
  check("ngu canh khong bao mat thi noi dung nguyen nhan", APP.includes("window.isSecureContext"));
  check("may khong co mic cung duoc bao, khong im lang", APP.includes("audio-capture"));

  console.log("");
  if (fails.length) {
    console.log(`FAIL - test_mic_loi_khong_lap: ${fails.length} loi: ${fails.join("; ")}`);
    process.exit(1);
  }
  console.log("OK - test_mic_loi_khong_lap: tat ca pass");
  // Thoat HAN: voice.js de lai dong ho do muc am chay nen, khong co dong nay thi node treo
  // va `tests/run.py` doi mai mai.
  process.exit(0);
})();
