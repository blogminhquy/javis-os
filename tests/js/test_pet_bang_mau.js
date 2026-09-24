/* Bảng màu linh vật: tông TỐI phải giữ đúng SẮC của tông sáng (0.59.36).

       node tests/js/test_pet_bang_mau.js

   Người dùng báo 18/09: "bảng màu hiện giờ hơi đơn điệu, các màu sắc không thay đổi rõ rệt.
   Ví dụ rất thích linh vật màu cam mà không có."

   Màu cam CÓ SẴN: `amber` ở tông sáng là #F28C28, đúng 30 độ, cam thật. Nhưng tông TỐI của nó
   được đặt tay thành #E8C97A, tức 43 độ - đã trôi sang VÀNG. Cả 12 tông tối đều bị đặt tay
   như vậy: sắc trôi, độ bão hoà bị gọt, độ sáng dồn hết vào dải 63-83%, nên ở giao diện tối
   màu nào cũng hoá pastel nhợt na ná nhau. Người dùng chọn "Hổ phách" rồi nhận về một con pet
   vàng, và kết luận là bảng màu không có màu cam - hoàn toàn hợp lý từ chỗ họ đứng.

   Test này khoá lại luật suy tông tối, thứ đã trôi một lần rồi và sẽ trôi lại nếu ai đó thêm
   màu mới bằng cách đặt tay. Nó KHÔNG khoá từng mã màu cụ thể (đổi gu là quyền của chủ dự án),
   chỉ khoá QUAN HỆ giữa hai tông. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const pet = read("dashboard/pet.js");
const consoleJs = read("dashboard/console.js");
const vi = JSON.parse(read("dashboard/i18n/vi.json"));
const en = JSON.parse(read("dashboard/i18n/en.json"));

const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

function hls(hex) {
  const r = parseInt(hex.slice(1, 3), 16) / 255,
        g = parseInt(hex.slice(3, 5), 16) / 255,
        b = parseInt(hex.slice(5, 7), 16) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
  if (mx === mn) return { h: 0, l, s: 0, xam: true };
  const d = mx - mn;
  const s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
  let h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return { h: h * 60, l, s, xam: false };
}
// Khoảng cách SẮC trên vòng tròn màu (0..180 độ).
const lechSac = (a, b) => { const d = Math.abs(a - b) % 360; return d > 180 ? 360 - d : d; };

// ---- Đọc bảng màu thẳng từ mã nguồn ----
const blk = pet.slice(pet.indexOf("var PALETTES = {"), pet.indexOf("// Cỡ pet."));
const re = /(\w+):\s*\{ key: "pet\.color\.(\w+)",\s*sun: \["(#\w{6})", "(#\w{6})", "(#\w{6})"\], moon: \["(#\w{6})", "(#\w{6})", "(#\w{6})"\] \}/g;
const bang = [...blk.matchAll(re)].map(m => ({
  ten: m[1], key: m[2], sun: [m[3], m[4], m[5]], moon: [m[6], m[7], m[8]],
}));

check("đọc được bảng màu từ pet.js", bang.length >= 20, `thấy ${bang.length}`);
check("khoá `key` luôn khớp tên bảng màu", bang.every(p => p.ten === p.key));

// ---- 1. LUẬT: tông tối giữ đúng sắc của tông sáng ----
// Đây là phép thử trung tâm. Lệch quá 8 độ là mắt thường đã gọi tên khác (30 độ cam so với
// 43 độ vàng, đúng con số của lỗi gốc). Màu xám không có sắc nên miễn.
const troiSac = bang.filter(p => {
  const s = hls(p.sun[0]), m = hls(p.moon[0]);
  return !s.xam && !m.xam && s.s > 0.12 && lechSac(s.h, m.h) > 8;
});
check("không màu nào trôi sắc giữa hai giao diện",
  troiSac.length === 0,
  troiSac.map(p => `${p.ten} ${Math.round(hls(p.sun[0]).h)}do->${Math.round(hls(p.moon[0]).h)}do`).join(", "));

// ---- 2. LUẬT: tông tối không được chói, và không được nhợt hết thành một dải ----
const choi = bang.filter(p => hls(p.moon[0]).l > 0.80);
check("tông tối không màu nào chói lên giữa nền tối (độ sáng <= 80%)",
  choi.length === 0, choi.map(p => `${p.ten} ${Math.round(hls(p.moon[0]).l * 100)}%`).join(", "));

// Độ bão hoà tông tối phải theo sát tông sáng. Bản cũ gọt nó xuống nên màu nào cũng thành
// pastel: đó CHÍNH LÀ cái "không thay đổi rõ rệt" người dùng nói.
const bigot = bang.filter(p => {
  const s = hls(p.sun[0]), m = hls(p.moon[0]);
  return s.s > 0.3 && m.s < s.s * 0.7;
});
check("tông tối không bị gọt bão hoà thành pastel",
  bigot.length === 0,
  bigot.map(p => `${p.ten} ${Math.round(hls(p.sun[0]).s * 100)}%->${Math.round(hls(p.moon[0]).s * 100)}%`).join(", "));

// ---- 3. Phải THẬT SỰ có một màu cam, ở CẢ HAI giao diện ----
// Đúng thứ người dùng đòi. Cam nằm khoảng 15-40 độ, và phải đủ bão hoà để gọi là cam.
const laCam = (hex) => { const c = hls(hex); return c.h >= 15 && c.h <= 40 && c.s >= 0.6; };
check("có bảng màu tên 'cam'", bang.some(p => p.ten === "cam"));
const cam = bang.find(p => p.ten === "cam") || { sun: ["#000000"], moon: ["#000000"] };
check("màu 'cam' ra cam ở giao diện SÁNG", laCam(cam.sun[0]), cam.sun[0]);
check("màu 'cam' ra cam ở giao diện TỐI", laCam(cam.moon[0]), cam.moon[0]);
check("và 'amber' cũng ra cam ở giao diện tối (lỗi gốc)",
  laCam((bang.find(p => p.ten === "amber") || { moon: ["#000"] }).moon[0]),
  (bang.find(p => p.ten === "amber") || { moon: ["?"] }).moon[0]);

// ---- 4. Bảng màu phải TRẢI RỘNG, không dồn cục ----
// "Đơn điệu" đo được: đếm xem có bao nhiêu cung 60 độ được phủ.
const cung = new Set(bang.filter(p => hls(p.sun[0]).s > 0.35).map(p => Math.floor(hls(p.sun[0]).h / 60)));
check("màu no sắc phủ ít nhất 5 trong 6 cung của vòng màu", cung.size >= 5, `phủ ${cung.size}/6`);

// ---- 5. Màu mắt ----
const matBlk = pet.slice(pet.indexOf("var MAU_MAT = {"));
const mats = [...matBlk.slice(0, matBlk.indexOf("};")).matchAll(
  /(\w+):\s*\{ key: "(pet\.eye\.\w+)",\s*mau: "(#\w{6})" \}/g)].map(m => [m[1], m[3], m[2]]);
check("mỗi màu mắt mang đúng khoá i18n của tên nó", mats.every(([k, , key]) => key === "pet.eye." + k));
// 0.64.39: chủ dự án rút về đúng hai màu sẵn (đen, trắng) cộng ô MÀU TỰ CHỌN theo mã.
check("màu mắt có sẵn là đúng đen và trắng", mats.map(m => m[0]).join(",") === "den,trang", mats.map(m => m[0]).join(","));
check("có ô màu mắt tự chọn", /oTuChon\("eye"/.test(pet) && /data-pet-eye-color-hex/.test(pet));
// Con ngươi phải ĐỌC RA là con ngươi trên thân sáng nhất. Nhạt quá là mặt trống trơn.
const matNhat = mats.filter(([, hex]) => hls(hex).l > 0.62 && hex.toLowerCase() !== "#ffffff");
check("màu mắt đều đủ đậm để thấy trên thân sáng (trừ trắng, cố ý)",
  matNhat.length === 0, matNhat.map(m => m.join(" ")).join(", "));

// ---- 6. Nhãn: giao diện phải tra theo khoá, và hai từ điển phải đủ ----
// Ghép chuỗi "pet.eye." + k thì bộ quét i18n (test_i18n.mjs) không thấy khoá, nên phải tra
// qua chính khoá của màu - đúng cách hàng bảng màu vẫn làm.
check("nhãn màu mắt tra qua khoá của màu, không viết cứng và không ghép chuỗi",
  /t\(\(MAU_MAT\[v\.eye\] \|\| MAU_MAT\.den\)\.key\)/.test(pet) && /t\(MAU_MAT\[k\]\.key\)/.test(pet)
  && !/t\("pet\.eye\." \+/.test(consoleJs + pet));
const thieu = [];
for (const p of bang) for (const [ten, d] of [["vi", vi], ["en", en]])
  if (!d["pet.color." + p.ten]) thieu.push(`${ten}:pet.color.${p.ten}`);
for (const [k] of mats) for (const [ten, d] of [["vi", vi], ["en", en]])
  if (!d["pet.eye." + k]) thieu.push(`${ten}:pet.eye.${k}`);
check("mọi màu thân và màu mắt đều có nhãn ở CẢ hai ngôn ngữ", thieu.length === 0, thieu.join(", "));

console.log(fails.length ? "\nFAIL: " + fails.join(", ") : "\nTat ca OK");
process.exit(fails.length ? 1 : 0);
