/* Thẻ việc nền trong khung chat (chat-viec.js, 0.64.48).

       node tests/js/test_the_viec_nen.js

   Chủ repo báo 2026-09-24: màn hình việc ngầm trong lúc chat "trông rất chán và thô kệch".
   Kết quả việc nền về khung chat là bong bóng chữ trơn, đầu dòng emoji, cuối dòng câu "Xem
   chi tiết ở trang Việc" không bấm được; dòng giao việc của giọng nói là chữ nghiêng mờ 12.5px
   và F5 là mất. Nay server gắn khối ẩn JAVIS_VIEC, dashboard vẽ thành thẻ. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const APP = D("app.js");
const CSS = D("style.css");
const HTML = D("index.html");
const VI = JSON.parse(D(path.join("i18n", "vi.json")));
const EN = JSON.parse(D(path.join("i18n", "en.json")));

const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
};

// ---- DOM giả tối thiểu ----
function theMoi() {
  const el = {
    _html: "", _cls: new Set(), _nghe: {},
    get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
    classList: {
      add: (c) => el._cls.add(c), contains: (c) => el._cls.has(c),
      remove: (c) => el._cls.delete(c),
    },
    insertAdjacentHTML(vi, h) { this._html = vi === "afterbegin" ? h + this._html : this._html + h; },
    querySelector(sel) {
      if (sel === ".bubble") return el._bubble;
      if (sel === ".viec-mo") return /class="viec-mo"/.test(el._bubble._html) ? el._nut : null;
      if (sel === ".viec-giao") return null;
      return null;
    },
    addEventListener(loai, fn) { this._nghe[loai] = fn; },
  };
  return el;
}
function msgGia(chu) {
  const m = theMoi();
  m._bubble = theMoi(); m._bubble._html = chu;
  m._nut = theMoi();
  return m;
}

const V = require("../../dashboard/chat-viec.js");

// ---- 1. tach: bóc khối, đọc đúng trường ----
let r = V.tach('<!-- JAVIS_VIEC: {"kind":"task","status":"done","title":"Lấy bảng giá","id":"t1"} -->\nKết quả đây.');
check("bóc được khối ở đầu", r.viec && r.viec.title === "Lấy bảng giá" && r.viec.id === "t1", JSON.stringify(r));
check("clean không còn khối", r.clean === "Kết quả đây.", JSON.stringify(r.clean));
r = V.tach("Ừ, để xem ngay.\n\n<!-- JAVIS_VIEC: {\"kind\":\"voice\",\"status\":\"giao\",\"title\":\"doanh thu\"} -->");
check("bóc được khối ở CUỐI (dòng giao việc của giọng nói)", r.viec && r.viec.status === "giao" && r.clean === "Ừ, để xem ngay.");
r = V.tach("<!-- JAVIS_VIEC: {hỏng -->\nChữ");
check("JSON hỏng: không vẽ thẻ nhưng VẪN bóc khối khỏi chữ", r.viec === null && r.clean === "Chữ", JSON.stringify(r));
check("không có khối: giữ nguyên", V.tach("chào").clean === "chào" && V.tach("chào").viec === null);
check("null không nổ", V.tach(null).clean === "");
check("trạng thái lạ rơi về done", V.tach('<!-- JAVIS_VIEC: {"status":"xyz"} -->x').viec.status === "done");

// ---- 2. ve: thẻ kết quả ----
let m = msgGia("<p>Kết quả</p>");
V.ve(m, { kind: "task", status: "done", title: "<b>tên</b>", id: "1" });
check("thẻ gắn lớp msg-viec + viec-done", m.classList.contains("msg-viec") && m.classList.contains("viec-done"));
check("dòng đầu nằm TRƯỚC kết quả", m._bubble._html.indexOf("viec-head") < m._bubble._html.indexOf("Kết quả"));
check("có nhãn trạng thái", m._bubble._html.indexOf("Việc nền xong") !== -1);
check("tên việc được escape", m._bubble._html.indexOf("<b>tên</b>") === -1 && m._bubble._html.indexOf("&lt;b&gt;tên&lt;/b&gt;") !== -1);
check("có nút mở trang Việc bấm được", /class="viec-mo"/.test(m._bubble._html) && typeof m._nut._nghe.click === "function");
m = msgGia("x");
V.ve(m, { status: "blocked", title: "a" });
check("việc bị chặn: lớp viec-blocked + nhãn bị chặn", m.classList.contains("viec-blocked") && m._bubble._html.indexOf("bị chặn") !== -1);

// ---- 3. ve: dòng đã giao (giọng nói) nằm DƯỚI bong bóng, không biến bong bóng thành thẻ ----
m = msgGia("Ừ, để xem ngay.");
V.ve(m, { kind: "voice", status: "giao", title: "doanh thu hôm nay" });
check("dòng giao: không gắn lớp thẻ", !m.classList.contains("msg-viec"));
check("dòng giao: nằm sau câu xác nhận", m._bubble._html.indexOf("viec-giao") > m._bubble._html.indexOf("Ừ, để xem"));
check("dòng giao: có tên việc", m._bubble._html.indexOf("doanh thu hôm nay") !== -1);

// ---- 4. Nối vào app.js ----
const i0 = APP.indexOf("function appendJavisMessage(");
const than = APP.slice(i0, APP.indexOf("\n}\n", i0));
check("appendJavisMessage bóc khối trước khi render markdown",
  /JavisViec\.tach\(text\)/.test(than) && /markdownToHtml\(tv\.clean/.test(than));
check("appendJavisMessage vẽ thẻ khi có khối", /JavisViec\.ve\(div, tv\.viec\)/.test(than));
check("tin push đọc thành tiếng phần chữ, không đọc khối ẩn",
  /const _doc = window\.JavisViec \? window\.JavisViec\.tach\(data\.content/.test(APP));
check("dòng voice-nen cũ đã bỏ", APP.indexOf('"voice-nen"') === -1);
check("giao việc bằng giọng: lưu cục bộ KÈM khối để F5 còn dòng giao",
  /_ghi = finalText \+ "\\n\\n<!-- JAVIS_VIEC: " \+ JSON\.stringify\(_v\)/.test(APP));
check("index.html nạp chat-viec.js", HTML.indexOf('/static/chat-viec.js') !== -1);

// ---- 5. CSS và chữ ----
const khoi = (sel) => { const i = CSS.indexOf(sel + " {"); return i < 0 ? "" : CSS.slice(i, CSS.indexOf("}", i)); };
check("dòng đầu thẻ chữ 16px", /font-size: 16px/.test(khoi(".viec-head")));
check("nút mở trang Việc chữ 16px", /font-size: 16px/.test(khoi(".viec-head .viec-mo")));
check("dòng giao chữ 16px", /font-size: 16px/.test(khoi(".msg-javis .viec-giao")));
check("dải việc nền không còn chữ 11-13px", !/font-size: 1[123]px/.test(khoi(".bg-strip") + khoi(".bg-chip") + khoi(".bg-open")));
for (const k of Object.keys(VI).filter(k => k.startsWith("viec."))) check("i18n en có " + k, !!EN[k]);
check("có đủ nhãn trạng thái", ["viec.st_done", "viec.st_blocked", "viec.st_failed", "viec.st_timeout", "viec.st_cancelled", "viec.mo_trang"].every(k => VI[k]));
check("chat-viec.js không có gạch dài", !/[\u2013\u2014]/.test(D("chat-viec.js")));

// ---- 6. Loop và nhắc hẹn (0.64.49): nhãn theo loại, nút mở trang Việc định kỳ ----
m = msgGia("x");
V.ve(m, { kind: "loop", status: "done", title: "Quét đơn" });
check("loop: nhãn riêng 'Vòng lặp vừa chạy'", m._bubble._html.indexOf("Vòng lặp vừa chạy") !== -1, m._bubble._html);
check("loop: nút mở trang Việc định kỳ", /data-trang="selfimprove"/.test(m._bubble._html) && m._bubble._html.indexOf("Việc định kỳ") !== -1);
m = msgGia("x");
V.ve(m, { kind: "reminder", status: "done", title: "Uống nước" });
check("nhắc hẹn: nhãn 'Nhắc hẹn'", m._bubble._html.indexOf(">Nhắc hẹn<") !== -1, m._bubble._html);
m = msgGia("x");
V.ve(m, { kind: "task", status: "done", title: "a" });
check("việc Kanban: nút vẫn mở trang Việc", /data-trang="kanban"/.test(m._bubble._html));
m = msgGia("x");
V.ve(m, { kind: "loop", status: "timeout", title: "a" });
check("loại không có nhãn riêng thì rơi về nhãn chung", m._bubble._html.indexOf("Việc nền quá giờ") !== -1);

if (fails.length) { console.log("\n" + fails.length + " FAIL"); process.exit(1); }
console.log("\nTất cả ok");
