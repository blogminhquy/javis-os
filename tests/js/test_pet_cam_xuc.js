/* Linh vật 0.64.39: thêm cảm xúc. NẠP THẬT pet.js rồi gọi API công khai, soi đôi mắt được vẽ.

       node tests/js/test_pet_cam_xuc.js

   Chủ dự án báo 24/09 hai chuyện:
     1. Bật mic, nói vào, mà pet không tỏ ra là ĐÃ BẮT được giọng: "đang chờ nghe" và "đang
        nghe thấy" là cùng một dáng mắt.
     2. Tắt mic thì pet quá ít cảm xúc: bấm vào hay vừa trả lời xong đều trơ ra.
   Test này khoá lại từng phản ứng, và khoá luôn luật quan trọng nhất: phản ứng KHÔNG được nói
   dối trạng thái thật (đang nói mà nhảy cẫng lên giữa câu, đang lỗi mà cười).

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
    style: { setProperty() {} }, setAttribute() {}, addEventListener() {}, appendChild() {},
    querySelector: () => nut(), querySelectorAll: () => [], getBoundingClientRect: () => ({ width: 72, height: 72, top: 0, left: 0 }),
    get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  };
}
let now = 1000;
const hangRaf = [];
// Đồng hồ giả: setTimeout chạy khi nhip() đẩy thời gian qua mốc của nó (chớp mắt 130ms,
// gỡ hoạt ảnh 900ms), giống hệt trình duyệt chứ không chạy ngay hay không bao giờ chạy.
let hangHen = [];
const henGio = (cb, ms) => { hangHen.push({ luc: now + (ms || 0), cb }); return hangHen.length; };
const created = [];
const win = {
  matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {}, dispatchEvent() {},
  innerWidth: 1280, innerHeight: 800, javisTheme: { isLight: () => true, on() {} },
};
const doc = {
  readyState: "complete", addEventListener() {}, querySelectorAll: () => [], querySelector: () => nut(),
  getElementById: () => null, body: nut(), activeElement: null,
  createElement: () => {
    const e = nut();
    // Giữ đúng MỘT đối tượng cho từng phần con, như DOM thật, để soi lại được sau này.
    const con = {};
    e.querySelector = (sel) => (con[sel] = con[sel] || nut());
    created.push(e);
    return e;
  },
};
new Function("window", "document", "localStorage", "fetch", "requestAnimationFrame", "cancelAnimationFrame",
  "performance", "CustomEvent", "FormData", "setTimeout", "clearTimeout",
  fs.readFileSync(path.join(ROOT, "dashboard", "pet.js"), "utf8"))(
  win, doc, { getItem: () => null, setItem() {} }, () => Promise.reject(new Error("offline")),
  (cb) => { hangRaf.push(cb); return hangRaf.length; }, () => {}, { now: () => now },
  function () {}, function () { this.append = () => {}; }, henGio, () => {});
const P = win.JavisPet;
const el = created[0];
const mat = () => el.querySelector(".pet-eyes").innerHTML;
// Chạy vòng vẽ MỘT nhịp ở thời điểm `t` (không chạy mãi: mỗi nhịp tự xin nhịp sau).
function nhip(t) {
  now = t;
  const den = hangHen.filter(h => h.luc <= t);
  hangHen = hangHen.filter(h => h.luc > t);
  den.forEach(h => h.cb());
  const ds = hangRaf.splice(0); ds.forEach(cb => cb(t));
}

// ---- 1. Mic bắt được giọng ----
P.setState("listening");
const choNghe = mat();
P.setState("hearing");
check("đã bắt giọng thì mắt KHÁC lúc đang chờ nghe", mat() !== choNghe && /rx="9\.6"/.test(mat()));
check("vành quay theo trạng thái hearing", el.dataset.state === "hearing");
P.react("nghe");
nhip(now + 100);
check("bắt thêm chữ thì cả mặt gật nhẹ (scale)", /scale\(/.test(el.querySelector(".pet-rig").style.transform || ""),
  el.querySelector(".pet-rig").style.transform);

// ---- 2. Đang nghĩ -> đang viết khi chữ chảy về ----
P.setState("thinking");
P.react("viet");
check("chữ trả lời chảy về thì chuyển sang viết", el.dataset.state === "writing" && /cy="7"/.test(mat()));
P.setState("idle");
P.react("viet");
check("không đang nghĩ thì 'viet' không đổi gì", el.dataset.state === "idle");

// ---- 3. Trả lời xong ----
P.setState("speaking");
const dangNoi = mat();
P.react("xong");
check("đang ĐỌC thành tiếng thì chưa nhảy (không chen ngang câu đang nói)", mat() === dangNoi && !el.dataset.anim);
P.setState("idle");
nhip(now + 16);
check("đọc xong mới vui: mắt cười", /pet-line/.test(mat()) && /Q0 -7/.test(mat()), mat());
check("và nhảy lên một cái", el.dataset.anim === "hop", el.dataset.anim);
nhip(now + 2000);
check("hết phản ứng thì trả về đúng trạng thái nghỉ", /<ellipse rx="7\.2" ry="17\.5"\/>/.test(mat()), mat());
P.setState("thinking");
P.react("xong");
P.setState("error");
P.setState("idle");
nhip(now + 16);
check("lượt LỖI thì không vui dù trước đó đã báo xong", !/Q0 -7/.test(mat()), mat());

// ---- 4. Phản ứng tay ----
P.react("click");
check("bấm vào thì có biểu cảm và cú bẹp",
  mat() !== "" && (nhip(now + 16), el.dataset.anim === "squish"));
P.react("choang");
check("bấm dồn dập thì chóng mặt", /M-8 -8 L8 8/.test(mat()));

// ---- 5. Ngủ gật khi ngồi không ----
nhip(now + 5000);
P.setState("idle");
nhip(now + 100000);
check("ngồi không lâu thì ngủ gật", el.dataset.ngu === "1" && /M-9 6 H9/.test(mat()), mat());
P.setState("thinking");
check("có việc thì tỉnh ngay", el.dataset.ngu === undefined);

console.log(fails.length ? "\nFAIL: " + fails.join(", ") : "\nTat ca OK");
process.exit(fails.length ? 1 : 0);
