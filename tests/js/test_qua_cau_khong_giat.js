/* Quả cầu não không giật, không tự thu nhỏ khi nói (0.57.20).

       node tests/js/test_qua_cau_khong_giat.js

   Chủ dự án 15/09: "khi mà nói nhiều lúc quả cầu bị giựt không cố định thậm chí nhiều lúc tự
   zoom out ra luôn".

   Hai triệu chứng, MỘT gốc, và không phải camera:
     - `voice.getLevel()` là trung bình phổ THÔ, đọc lại 60 lần mỗi giây. Tiếng nói lên xuống
       liên tục nên con số đó nhảy loạn từng khung hình, mà nó được nhân THẲNG vào bán kính
       mỗi chấm -> cả quả cầu rung bần bật.
     - Ở nhịp NGHĨ biên độ cũ là 0,16 + 0,3*mức, tức tới 0,46 khi nói to: có lúc MỌI chấm cùng
       co còn 0,54 lần rồi phình lên 1,46 lần, chu kỳ 1,4 giây. Cả quả cầu phình co như bơm
       hơi, và lúc co thì nhìn y hệt "tự zoom out" dù camera không hề đổi.

   Chữa: làm trơn mức âm (lên nhanh, xuống chậm như đồng hồ VU) rồi hạ biên độ nhịp thở. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const src = fs.readFileSync(path.join(root, "dashboard/graph.js"), "utf8");

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- 1. CANARY: không được quay lại kiểu nhân thẳng mức thô ----
check("setLevel không còn gán thẳng mức thô", !/setLevel\(l\) \{ this\.level = l \|\| 0; \}/.test(src));
check("biên độ nhịp NGHĨ cũ (0.16 + 0.3) đã bỏ", !/1 \+ \(0\.16 \+ 0\.3 \* this\.level\)/.test(src));
check("biên độ lúc ĐỌC cũ (0.25) đã bỏ", !/1 \+ 0\.25 \* this\.level/.test(src));

// ---- 2. Làm trơn: chạy thật hàm lấy từ nguồn ----
const m = src.match(/setLevel\(l\) \{[\s\S]*?\n  \}/);
check("tìm được setLevel trong nguồn", !!m);
const dungNao = () => new Function("return { level: 0, " + (m ? m[0] : "setLevel(){}") + " };")();

// Mức âm thô của tiếng nói thật: nhảy loạn từng khung hình.
const thoNoi = [];
for (let i = 0; i < 180; i++) thoNoi.push(i % 7 === 0 ? 0.05 : (i % 3 === 0 ? 0.9 : 0.45));
const g = dungNao();
const tron = thoNoi.map(v => { g.setLevel(v); return g.level; });

const bienDo = (a) => Math.max(...a) - Math.min(...a);
const giat = (a) => { let s = 0; for (let i = 1; i < a.length; i++) s += Math.abs(a[i] - a[i - 1]); return s / (a.length - 1); };
const sauOnDinh = tron.slice(30);

check("mức âm sau khi làm trơn KHÔNG nhảy loạn nữa (giật giảm ít nhất 5 lần)",
  giat(thoNoi) / giat(sauOnDinh) >= 5, (giat(thoNoi) / giat(sauOnDinh)).toFixed(1) + " lần");
check("biên độ dao động thu hẹp rõ", bienDo(sauOnDinh) < bienDo(thoNoi) / 3,
  bienDo(sauOnDinh).toFixed(3) + " so với " + bienDo(thoNoi).toFixed(3));
check("vẫn nằm trong 0..1, không tràn", Math.min(...tron) >= 0 && Math.max(...tron) <= 1);

// Lên NHANH xuống CHẬM: bật tiếng thì bắt kịp, ngắt quãng giữa hai từ thì không rơi thẳng đứng.
const g2 = dungNao();
g2.setLevel(1); const len1 = g2.level;
check("một khung hình đã bắt được phần lớn cú lên", len1 >= 0.25, len1.toFixed(3));
g2.level = 0.8; g2.setLevel(0); const xuong1 = g2.level;
check("xuống chậm hơn lên nhiều (không rơi thẳng đứng)", xuong1 > 0.7, xuong1.toFixed(3));

// Im hẳn một lúc thì phải về gần 0, không treo lơ lửng.
const g3 = dungNao();
g3.level = 1;
for (let i = 0; i < 120; i++) g3.setLevel(0);
check("im 2 giây thì mức về gần 0", g3.level < 0.01, g3.level.toFixed(4));

// ---- 3. Nhịp thở: quả cầu không được phình co như bơm hơi ----
const p = src.match(/const pulse = this\._thinking[\s\S]*?;\n/);
check("tìm được công thức nhịp thở", !!p);
const nhip = new Function("thinking", "level", "t",
  "const self = { _thinking: thinking, level: level };"
  + (p ? p[0].replace(/this\._thinking/g, "self._thinking").replace(/this\.level/g, "self.level") : "const pulse=1;")
  + "return pulse;");

// Quét trọn vài chu kỳ, lấy mức âm CAO NHẤT (trường hợp xấu nhất).
function bienDoNhip(thinking) {
  let lo = 9, hi = -9;
  for (let t = 0; t < 6000; t += 10) { const v = nhip(thinking, 1, t); lo = Math.min(lo, v); hi = Math.max(hi, v); }
  return { lo: lo, hi: hi };
}
const nghi = bienDoNhip(true), doc = bienDoNhip(false);
check("lúc NGHĨ: chấm không bao giờ co dưới 0,8 lần (co sâu nhìn như tự zoom out)",
  nghi.lo >= 0.8, nghi.lo.toFixed(3));
check("lúc NGHĨ: cũng không phình quá 1,2 lần", nghi.hi <= 1.2, nghi.hi.toFixed(3));
check("lúc ĐỌC: dao động trong khoảng hẹp", doc.lo >= 0.95 && doc.hi <= 1.15,
  doc.lo.toFixed(3) + ".." + doc.hi.toFixed(3));
check("vẫn CÓ phản ứng theo giọng (không phải làm chết hiệu ứng)",
  nhip(false, 1, 0) > nhip(false, 0, 0) && (nghi.hi - nghi.lo) > 0.05);

// Nhịp NGHĨ phải CHẬM lại: chu kỳ cũ 1,4 giây nhìn như tim đập gấp.
let doiChieu = 0, truoc = nhip(true, 1, 0) > 1;
for (let t = 10; t < 6000; t += 10) { const nay = nhip(true, 1, t) > 1; if (nay !== truoc) doiChieu++; truoc = nay; }
check("nhịp NGHĨ chậm lại (dưới 5 lần đổi chiều trong 6 giây)", doiChieu <= 5, doiChieu);

console.log(fails.length ? "\n" + fails.length + " FAIL" : "\nTat ca OK");
process.exit(fails.length ? 1 : 0);
