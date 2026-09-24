/* Linh vật 0.64.39: thanh trượt cỡ, màu TỰ CHỌN theo mã màu, và bộ chỉnh dùng chung với
   avatar trợ lý. Test này NẠP THẬT pet.js và gọi API công khai của nó, không soi chữ.

       node tests/js/test_pet_thanh_truot_mau.js

   Chủ dự án yêu cầu 24/09:
     - Kích cỡ và Cỡ mắt thành THANH TRƯỢT thay vì mấy nấc cố định.
     - Bảng màu và màu mắt có thêm ô chọn được MÃ MÀU.
     - Màu mắt rút gọn còn Trắng, Đen và Tùy chọn.
   Những gì dễ hỏng LẶNG LẼ và được khoá ở đây:
     1. Cấu hình cũ ("rat_lon", "to", mắt "nau") phải quy đổi đúng, không rơi về mặc định:
        người đang dùng không được thấy pet mình đổi dáng sau khi cập nhật.
     2. Lúc KÉO thanh trượt không được ghi máy chủ mỗi nhịp (vài chục request một lần kéo).
     3. Màu tự chọn phải qua đúng luật tông tối của bảng màu có sẵn: giữ sắc, không chói.
     4. Mã màu rác không được lọt vào thuộc tính style.

   KHÔNG dùng ký tự em dash. */
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

function nut() {
  return {
    _html: "", dataset: {}, hidden: false, classList: { add() {}, remove() {}, contains: () => false },
    style: { setProperty(k, v) { this[k] = v; } }, setAttribute() {}, addEventListener() {}, appendChild() {},
    querySelector: () => nut(), querySelectorAll: () => [], getBoundingClientRect: () => ({ width: 72, height: 72, top: 0 }),
    get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  };
}
function napPet(theme) {
  const goiMang = [];
  const win = {
    matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {}, dispatchEvent() {},
    innerWidth: 1280, innerHeight: 800,
    javisTheme: { isLight: () => theme === "light", on() {} },
  };
  const doc = {
    readyState: "complete", addEventListener() {}, querySelectorAll: () => [], querySelector: () => nut(),
    getElementById: () => null, createElement: () => nut(), body: nut(), activeElement: null,
  };
  const fetch = (url, o) => { goiMang.push([url, o && o.method]); return Promise.reject(new Error("offline")); };
  new Function("window", "document", "localStorage", "fetch", "requestAnimationFrame", "cancelAnimationFrame",
    "performance", "CustomEvent", "FormData",
    fs.readFileSync(path.join(ROOT, "dashboard", "pet.js"), "utf8"))(
    win, doc, { getItem: () => null, setItem() {} }, fetch, () => 0, () => {}, { now: () => 0 },
    function () {}, function () { this.append = () => {}; });
  return { P: win.JavisPet, goiMang };
}

function hsl(h6) {
  const r = parseInt(h6.slice(1, 3), 16) / 255, g = parseInt(h6.slice(3, 5), 16) / 255, b = parseInt(h6.slice(5, 7), 16) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
  if (mx === mn) return { h: 0, s: 0, l };
  const d = mx - mn, s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
  const h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return { h: h * 60, s, l };
}

// ---- 1. Cấu hình CŨ quy đổi đúng ----
{
  const { P } = napPet("dark");
  P.hydrate({ size: "rat_lon", eyeSize: "to", eye: "nau", palette: "cam" });
  const c = P.get();
  check("cỡ cũ 'rat_lon' quy về đúng 124px", c.size === 124, c.size);
  check("cỡ mắt cũ 'to' quy về hệ số 1.25", c.eyeSize === 1.25, c.eyeSize);
  check("mắt nâu cũ thành ô tự chọn mang đúng mã cũ", c.eye === "custom" && c.eyeColor === "#5a3a28", c.eye + " " + c.eyeColor);
  P.hydrate({ size: "khong-co", eyeSize: "la", eye: "<script>", palette: "khong-co" });
  const d = P.get();
  check("giá trị rác rơi về mặc định", d.size === 72 && d.eyeSize === 1 && d.eye === "den" && d.palette === "cam" && d.shape === "star",
    JSON.stringify(d));
}

// ---- 2. Thanh trượt: kẹp khoảng, và KHÔNG ghi máy chủ lúc đang kéo ----
{
  const { P, goiMang } = napPet("dark");
  const truoc = goiMang.length;
  P.setCfg({ size: 999 }, true);
  P.setCfg({ eyeSize: 7 }, true);
  check("lúc kéo (tam) không ghi máy chủ", goiMang.length === truoc, goiMang.length - truoc + " request");
  check("cỡ kẹp ở trần 150px", P.get().size === 150, P.get().size);
  check("cỡ mắt kẹp ở trần 1.5", P.get().eyeSize === 1.5, P.get().eyeSize);
  P.setCfg({ size: 3, eyeSize: 0.1 });
  check("thả tay (không tam) thì ghi máy chủ", goiMang.some(g => g[0] === "/settings" && g[1] === "POST"));
  check("cỡ kẹp ở sàn 44px, mắt ở sàn 0.8", P.get().size === 44 && P.get().eyeSize === 0.8, P.get().size + "/" + P.get().eyeSize);
  P.setCfg({ eyeSize: 1.1500000000000001 });
  check("cỡ mắt làm tròn 2 chữ số (so khớp với bản máy chủ đọc lại)", P.get().eyeSize === 1.15, P.get().eyeSize);
}

// ---- 3. Màu tự chọn ----
{
  const { P } = napPet("dark");
  check("hex chuẩn hoá #abc", P.hex("#ABC") === "#aabbcc" && P.hex("FA4F05") === "#fa4f05");
  check("hex rác bị từ chối", P.hex("red") === "" && P.hex('#12345"><script>') === "" && P.hex("") === "");
  P.setCfg({ palette: "custom", color: "#FA4F05" });
  check("chọn màu thân tự chọn được giữ", P.get().palette === "custom" && P.get().color === "#fa4f05");
  const toi = P.toneOf("custom", "#fa4f05");
  const sac = hsl("#fa4f05"), sacToi = hsl(toi[0]);
  const lech = Math.abs(sac.h - sacToi.h) % 360;
  check("tông tối của màu tự chọn giữ đúng sắc", Math.min(lech, 360 - lech) <= 8, toi[0]);
  check("tông tối của màu tự chọn không chói (58-80%)", sacToi.l >= 0.57 && sacToi.l <= 0.8, Math.round(sacToi.l * 100) + "%");
  P.setCfg({ color: "khong-phai-mau" });
  check("mã rác không ghi đè mã tốt đang có", /^#[0-9a-f]{6}$/.test(P.get().color), P.get().color);
  const svg = P.previewSvg("circle", "custom", { mau: "#123456", mat: "custom", mauMat: "#abcdef", coMat: 1.5 });
  check("chân dung vẽ mắt đúng mã tự chọn", (svg.match(/fill="#abcdef"/g) || []).length === 2);
  check("chân dung vẽ mắt to theo hệ số", /rx="10\.8"/.test(svg));
  const sang = napPet("light").P;
  check("giao diện sáng giữ NGUYÊN mã người dùng gõ", /fill="#123456"/.test(sang.previewSvg("circle", "custom", { mau: "#123456" })));
  check("mắt trắng / đen / tự chọn là đủ ba lựa chọn",
    Object.keys(P.eyeColors()).join(",") === "den,trang");
}

// ---- 4. Bộ chỉnh dùng chung ----
{
  const { P } = napPet("dark");
  const h = P.editorHtml({ shape: "star", palette: "custom", color: "#00ff00", eye: "trang", eyeSize: 1.3, size: 96 }, { size: true, vanh: true });
  check("có thanh trượt cỡ với đúng giá trị", /data-pet-size min="44" max="150" step="2" value="96"/.test(h));
  check("có thanh trượt cỡ mắt với đúng giá trị", /data-pet-eye-size min="0.8" max="1.5" step="0.05" value="1.3"/.test(h));
  check("ô màu thân tự chọn đang được đánh dấu", /data-pet-custom="palette" aria-pressed="true"/.test(h));
  check("ô gõ mã màu hiện đúng mã đang dùng", /data-pet-color-hex value="#00FF00"/.test(h));
  check("mắt trắng đang được đánh dấu", /data-pet-eye="trang" aria-pressed="true"/.test(h));
  const h2 = P.editorHtml({ shape: "circle", palette: "amber" }, {});
  check("avatar trợ lý (không opts.size) không có thanh trượt cỡ thân", !/data-pet-size /.test(h2) && /data-pet-eye-size /.test(h2));
  check("ô gõ mã màu thân gợi ý đúng màu bảng đang chọn", /data-pet-color-hex value="#F28C28"/.test(h2));
  const bom = P.editorHtml({ shape: "circle", palette: "custom", color: '"><img src=x onerror=alert(1)>' }, {});
  check("mã màu độc không lọt vào HTML", !/onerror/.test(bom));
}

console.log(fails.length ? "\nFAIL: " + fails.join(", ") : "\nTat ca OK");
process.exit(fails.length ? 1 : 0);
