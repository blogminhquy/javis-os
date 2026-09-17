/* Chân dung TĨNH của linh vật phải luôn có ĐỦ HAI CON MẮT, nằm trong khung.

       node tests/js/test_pet_chan_dung_hai_mat.js

   chanDung() vẽ mọi khuôn mặt KHÔNG cử động của Javis: ô chọn hình dáng và ô chọn cỡ mắt ở
   trang Linh vật, dấu ấn thay logo trên thanh bên, avatar trợ lý. Một chỗ sai là sai cả bốn.

   Vì sao phải CHẠY THẬT chứ không dò mã nguồn: 0.59.30 làm tròn khoảng cách hai mắt bằng
   toFixed() ngay lúc tính, nên nó thành CHUỖI. Mắt trái tính bằng phép trừ, JavaScript tự ép
   chuỗi về số, ra đúng. Mắt phải tính bằng phép cộng, mà cộng với chuỗi là NỐI CHUỖI: cx nhảy
   từ 191 lên 17615, văng ra ngoài khung. Kết quả là mọi chân dung chỉ còn một con mắt, trông
   lệch mà không giống lỗi, nên nhìn qua tưởng là cố ý. Mã nguồn lúc đó đọc vẫn xuôi tai (có
   đủ hai lệnh vẽ ellipse), chỉ có chạy lên rồi đo toạ độ mới bắt được.

   KHÔNG dùng ký tự em dash. */
const path = require("path");
const root = path.join(__dirname, "..", "..");

let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

// ---- DOM giả, lấy nguyên cách làm của test_pet_huong_liec.js ----
function nutGia() {
  const n = {
    innerHTML: "", hidden: false, dataset: {}, childElementCount: 1,
    style: { setProperty() {}, removeProperty() {} },
    classList: { add() {}, remove() {}, contains: () => false, toggle() {} },
    setAttribute() {}, getAttribute: () => null, addEventListener() {}, appendChild() {},
    getBoundingClientRect: () => ({ top: 0, left: 0, right: 0, bottom: 0, width: 56, height: 56 }),
    querySelectorAll: () => [], focus() {},
  };
  n.querySelector = () => n;
  return n;
}
const nut = {
  ".pet-body": nutGia(), ".pet-menu": nutGia(), ".pet-rig": nutGia(),
  ".pet-ring": nutGia(), ".pet-face": nutGia(), ".pet-eyes": nutGia(), svg: nutGia(),
};
const goc = nutGia();
goc.querySelector = (sel) => nut[sel] || null;
const mqGiam = { matches: false, addEventListener() {}, addListener() {} };

global.window = {
  t: (k, d) => d || k,
  ic: () => "",
  innerWidth: 1280, innerHeight: 900,
  matchMedia: () => mqGiam,
  addEventListener() {}, dispatchEvent() {},
  requestAnimationFrame: () => 1,
  cancelAnimationFrame: () => {},
};
global.document = {
  readyState: "complete", hidden: false,
  createElement: () => goc,
  getElementById: () => null,
  addEventListener() {},
  body: { appendChild() {} },
  querySelectorAll: () => [],
};
global.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
global.performance = { now: () => 1000 };
global.requestAnimationFrame = window.requestAnimationFrame;
global.cancelAnimationFrame = window.cancelAnimationFrame;
global.fetch = () => new Promise(() => {});
global.CustomEvent = function () {};
global.FormData = function () { this.append = function () {}; };

require(path.join(root, "dashboard", "pet.js"));
const P = window.JavisPet;
check("pet.js nạp được với DOM giả", !!P && typeof P.previewSvg === "function");

// Đọc từng con mắt trong một chân dung: trả về [{cx, cy, rx, ry}, ...].
function docMat(svg) {
  return [...svg.matchAll(/<ellipse cx="([-\d.]+)" cy="([-\d.]+)" rx="([-\d.]+)" ry="([-\d.]+)"/g)]
    .map((m) => ({ cx: +m[1], cy: +m[2], rx: +m[3], ry: +m[4] }));
}
// Khung nhìn của chân dung, đọc thẳng từ thuộc tính viewBox chứ không chép lại con số: hai
// khung (có vành / không vành) khác nhau, và chúng còn đổi được về sau.
function docKhung(svg) {
  const m = /viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"/.exec(svg);
  return m ? { x: +m[1], y: +m[2], r: +m[1] + +m[3], d: +m[2] + +m[4] } : null;
}

const HINH = Object.keys(P.shapes());
const CO_MAT = Object.keys(P.eyeSizes());
check("có đủ hình dáng để soi (" + HINH.length + ")", HINH.length >= 6);
check("có đủ cỡ mắt để soi (" + CO_MAT.length + ")", CO_MAT.length >= 3);

// ---- 1. Mọi hình, mọi cỡ mắt, cả hai kiểu khung: luôn đúng HAI con mắt nằm trong khung ----
let loi = [];
HINH.forEach((hinh) => {
  CO_MAT.forEach((co) => {
    [false, true].forEach((vanh) => {
      const ten = hinh + "/" + co + (vanh ? "/có vành" : "");
      const svg = P.previewSvg(hinh, "amber", { mat: "den", coMat: co, vanh: vanh });
      const mat = docMat(svg);
      const khung = docKhung(svg);
      if (mat.length !== 2) { loi.push(ten + ": có " + mat.length + " mắt"); return; }
      if (!khung) { loi.push(ten + ": không đọc được viewBox"); return; }
      mat.forEach((e, i) => {
        // Cả con mắt, không riêng tâm nó, phải nằm gọn trong khung. Toạ độ văng ra ngoài là
        // con mắt biến mất khỏi màn hình mà không có lỗi nào được ném ra.
        if (!Number.isFinite(e.cx) || !Number.isFinite(e.cy)) loi.push(ten + ": mắt " + i + " toạ độ không phải số");
        else if (e.cx - e.rx < khung.x || e.cx + e.rx > khung.r) loi.push(ten + ": mắt " + i + " ra ngoài khung (cx=" + e.cx + ")");
        else if (e.cy - e.ry < khung.y || e.cy + e.ry > khung.d) loi.push(ten + ": mắt " + i + " tràn trên/dưới (cy=" + e.cy + ")");
      });
      // Hai con mắt phải RỜI nhau, không chồng lên nhau thành một vệt.
      if (mat.length === 2 && Math.abs(mat[0].cx - mat[1].cx) <= mat[0].rx + mat[1].rx) {
        loi.push(ten + ": hai mắt chồng lên nhau");
      }
    });
  });
});
check("mọi chân dung đều đủ hai mắt, rời nhau, nằm trong khung" + (loi.length ? " -> " + loi.slice(0, 6).join("; ") : ""),
  loi.length === 0);

// ---- 2. Hai con mắt phải ĐỐI XỨNG quanh hướng liếc, không con to con nhỏ ----
{
  const mat = docMat(P.previewSvg("circle", "amber", { mat: "den" }));
  check("hai mắt cùng cỡ và cùng độ cao",
    mat.length === 2 && mat[0].rx === mat[1].rx && mat[0].ry === mat[1].ry && mat[0].cy === mat[1].cy);
}

// ---- 3. Cỡ mắt thật sự làm mắt TO LÊN, và nới khoảng cách theo ----
{
  const do_ = (co) => {
    const m = docMat(P.previewSvg("star", "amber", { mat: "den", coMat: co }));
    return { rx: m[0].rx, cach: Math.abs(m[1].cx - m[0].cx) / 2 };
  };
  const t = do_("thuong"), n = do_("to"), r = do_("rat_to");
  check("mắt to dần theo cỡ đã chọn", t.rx < n.rx && n.rx < r.rx);
  check("khoảng cách hai mắt nới theo", t.cach < n.cach && n.cach < r.cach);
  // Nới ÍT hơn mức mắt phình: nới đủ hệ số thì hai con mắt dạt ra hai bên thái dương.
  check("nới ít hơn mức mắt phình", r.cach / t.cach < r.rx / t.rx);
}

// ---- 4. Avatar trợ lý giữ cỡ mắt THƯỜNG, không ăn theo lựa chọn của con pet ----
{
  P.setCfg({ eyeSize: "rat_to" });
  const troLy = docMat(P.previewSvg("circle", "blue", {}));      // không truyền coMat
  const cuaPet = docMat(P.markSvg());
  check("avatar trợ lý vẫn cỡ mắt thường", troLy.length === 2 && troLy[0].rx === 7.2);
  check("dấu ấn thanh bên theo đúng cỡ mắt của pet", cuaPet.length === 2 && cuaPet[0].rx > 7.2);
}

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - chân dung tĩnh của linh vật");
