/* Javis TỰ HỎI THĂM khi việc nền chạy lâu (0.57.19).

       node tests/js/test_hoi_tham_viec_nen.js

   Chủ dự án 15/09: giao việc xong thì im lặng hàng phút, "anh không rõ nó có chạy nền thật hay
   không"; anh ấy muốn nó nói kiểu "để em xem nhé", "chờ em tý", "em vẫn chưa xong".

   Người thật nhận một việc lâu thì thỉnh thoảng ngẩng lên nói một câu. Nhưng nói dày là tra
   tấn, và chen vào giữa lời người ta là đúng cái tội mà ngắt lời sinh ra để chữa. Nên ba luật:
     - THƯA DẦN: 25 giây, 60, 120, rồi mỗi 180 giây.
     - Chỉ nói khi đạo diễn cho phép (không ai đang nói, loa đang im).
     - Chỉ khi đang rảnh tay và loa bật.
   Số việc lấy từ /background (sổ THẬT của server), không đếm mò ở trình duyệt. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const app = read("dashboard/app.js");
const strip = read("dashboard/background-strip.js");
const vi = JSON.parse(read("dashboard/i18n/vi.json"));
const en = JSON.parse(read("dashboard/i18n/en.json"));

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- 1. Đường số liệu: server -> dải trạng thái -> app ----
check("dải trạng thái đẩy voice_count sang app",
  /window\.JavisOrb\.setVoiceJobs\(\(d && d\.voice_count\) \|\| 0\)/.test(strip));
check("app nhận qua JavisOrb.setVoiceJobs", /setVoiceJobs: \(n\) => datSoViecGiong\(n\)/.test(app));
check("có câu hỏi thăm trong cả hai ngôn ngữ",
  !!vi["app.voice_cho_viec"] && !!en["app.voice_cho_viec"]
  && !!vi["app.voice_cho_viec_lau"] && !!en["app.voice_cho_viec_lau"]);
check("mỗi khoá có nhiều câu để không lặp một câu duy nhất",
  vi["app.voice_cho_viec"].split("|").length >= 3 && en["app.voice_cho_viec"].split("|").length >= 3);
check("câu tiếng Việt CÓ DẤU", /[ạảãáàâăêôơưđ]/i.test(vi["app.voice_cho_viec"]));
check("không có em dash trong câu hỏi thăm",
  (vi["app.voice_cho_viec"] + vi["app.voice_cho_viec_lau"] + en["app.voice_cho_viec"]
   + en["app.voice_cho_viec_lau"]).indexOf("—") === -1);

// ---- 2. Nhấc nguyên khối logic ra chạy thật ----
const m = app.match(/let _soViecGiong = 0[\s\S]*?\n_hoiThamTimer = setInterval\(hoiThamViecNen, 2000\);/);
check("tìm được khối hỏi thăm trong app.js", !!m);

let gio = 1000000;                       // đồng hồ giả
const daNoi = [];
const voiceGia = { ttsEnabled: true, enqueueSpeak: (t, o) => daNoi.push({ t: t, o: o }) };
const turnGia = { rp: true, canSpeakNow: function () { return this.rp; } };
const winGia = { t: (k) => (k === "app.voice_cho_viec_lau"
  ? "Việc này lâu hơn em tưởng.|Vẫn chưa xong, em không quên đâu."
  : "Em vẫn đang xem, chờ chút nhé.|Chưa xong đâu, đợi em tí.") };
const api = new Function("handsFree", "voice", "turn", "window", "setInterval", "Date",
  (m ? m[0] : "") + `
  return {
    dat: datSoViecGiong, hoi: hoiThamViecNen, nhip: nhipHoiTham,
    ranhTay: (v) => { handsFree = v; },
    xem: () => ({ so: _soViecGiong, lan: _lanHoiTham, moc: _mocViecGiong })
  };`)(
  true, voiceGia, turnGia, winGia, () => 0, { now: () => gio });

// Chưa có việc nào: im.
api.hoi();
check("không có việc nền thì không nói gì", daNoi.length === 0);

// Việc nền bắt đầu.
api.dat(1);
check("nhận việc thì ghi mốc", api.xem().so === 1 && api.xem().moc === gio);
gio += 10000;
api.hoi();
check("mới 10 giây: chưa hỏi thăm (nhắc dày là tra tấn)", daNoi.length === 0);
gio += 16000;                            // tổng 26 giây
api.hoi();
check("quá 25 giây: hỏi thăm lần đầu", daNoi.length === 1, JSON.stringify(daNoi));
check("câu hỏi thăm không tính vào chữ hiện theo lời đọc", daNoi[0].o && daNoi[0].o.uncounted === true);
check("dùng bộ câu NGẮN khi mới chờ", daNoi[0].t.indexOf("lâu hơn em tưởng") === -1);

// Nhịp thưa dần.
gio += 30000;
api.hoi();
check("30 giây sau lần đầu: chưa tới nhịp thứ hai (60 giây)", daNoi.length === 1);
gio += 35000;                            // 65 giây kể từ lần hỏi trước
api.hoi();
check("quá 60 giây: hỏi thăm lần hai", daNoi.length === 2);
check("nhịp thứ ba là 120 giây", api.nhip() === 120000);
gio += 125000;
api.hoi();
check("quá 120 giây: hỏi thăm lần ba", daNoi.length === 3);
check("từ lần bốn trở đi lặp 180 giây", api.nhip() === 180000);
check("chờ lâu thì đổi sang bộ câu THỪA NHẬN LÂU",
  daNoi[2].t.indexOf("lâu hơn em tưởng") >= 0 || daNoi[2].t.indexOf("không quên") >= 0,
  daNoi[2].t);

// ---- 3. Ba chốt giữ cho nó không phiền ----
const truoc = daNoi.length;
turnGia.rp = false;                      // người dùng đang nói, hoặc loa đang bận
gio += 400000;
api.hoi();
check("đang nói chuyện dở thì TUYỆT ĐỐI không chen câu hỏi thăm", daNoi.length === truoc);
turnGia.rp = true;
api.hoi();
check("rảnh trở lại thì mới nói", daNoi.length === truoc + 1);

api.ranhTay(false);
gio += 400000;
api.hoi();
check("tắt rảnh tay (quay về gõ chữ) thì im, dải việc nền đã hiện trên màn hình rồi",
  daNoi.length === truoc + 1);
api.ranhTay(true);

voiceGia.ttsEnabled = false;
gio += 400000;
api.hoi();
check("tắt loa thì im", daNoi.length === truoc + 1);
voiceGia.ttsEnabled = true;

// ---- 4. Việc xong thì thôi hỏi thăm ----
api.dat(0);
check("hết việc thì xoá mốc và số lần", api.xem().so === 0 && api.xem().moc === 0 && api.xem().lan === 0);
gio += 400000;
api.hoi();
const sau = daNoi.length;
api.hoi();
check("hết việc thì không bao giờ nói nữa", daNoi.length === sau && sau === truoc + 1);

// Giao việc mới thì đếm lại từ đầu, không kế thừa nhịp thưa của đợt trước.
api.dat(2);
check("đợt việc mới: nhịp về lại 25 giây", api.nhip() === 25000 && api.xem().moc === gio);

console.log(fails.length ? "\n" + fails.length + " FAIL" : "\nTat ca OK");
process.exit(fails.length ? 1 : 0);
