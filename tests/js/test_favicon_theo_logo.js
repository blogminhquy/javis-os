/* Đổi logo thì ICON TRÊN TAB phải đổi theo ngay (0.59.37).

       node tests/js/test_favicon_theo_logo.js

   Chủ dự án báo 18/09: tải logo riêng lên thì ảnh trong trang đổi ngay, nhưng icon trên tab
   trình duyệt vẫn là hình cũ.

   Hai chỗ kẹt, và cả hai đều nằm ở phía trình duyệt chứ không phải máy chủ:

     1. `/favicon.ico` và `/brand-logo` phía máy chủ ĐÃ trả đúng logo hiện tại. Nhưng
        index.html trỏ `/brand-logo?v=<phiên bản app>`, mà chuỗi `v` chỉ đổi khi app lên bản
        mới. Tải ảnh khác lên thì URL không đổi, trình duyệt không có lý do gì đi lấy lại.
     2. `bustLogos()` sau khi tải lên chỉ chạy qua các thẻ <img>, không đụng tới <link rel=icon>.

   Test này BÓC THẬT hàm bustLogos ra khỏi branding.js rồi chạy nó với một <head> giả, chứ
   không soi mã nguồn bằng regex: một phép thử soi chữ vẫn xanh khi hàm gọi sai biến hay gọi
   nhầm thứ tự (đúng vụ trang Cài đặt linh vật trắng trơn cùng ngày). */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- <head> giả, đủ để theo dõi thẻ link vào ra ----
function taoLink(rel, href) {
  const o = { tagName: "LINK", _at: { rel: rel || "", href: href || "" }, parentNode: null };
  o.setAttribute = (k, v) => { o._at[k] = String(v); };
  o.getAttribute = (k) => (k in o._at ? o._at[k] : null);
  Object.defineProperty(o, "rel", { get: () => o._at.rel, set: (v) => { o._at.rel = String(v); } });
  Object.defineProperty(o, "href", { get: () => o._at.href, set: (v) => { o._at.href = String(v); } });
  return o;
}
function taoHead(banDau) {
  const head = { con: banDau.slice() };
  head.con.forEach((l) => { l.parentNode = head; });
  head.appendChild = (l) => { l.parentNode = head; head.con.push(l); return l; };
  head.removeChild = (l) => { head.con = head.con.filter((x) => x !== l); l.parentNode = null; return l; };
  head.querySelectorAll = (sel) => {
    const muon = (sel.match(/rel="([^"]+)"/g) || []).map((m) => m.slice(5, -1));
    return head.con.filter((l) => muon.includes(l.getAttribute("rel")));
  };
  return head;
}

function bocHam(src, khai) {
  const i = src.indexOf(khai);
  if (i < 0) return null;
  let d = 0, j = src.indexOf("{", i);
  const dau = j;
  for (; j < src.length; j++) {
    if (src[j] === "{") d++;
    else if (src[j] === "}" && !--d) break;
  }
  return { than: src.slice(dau + 1, j), het: j };
}

const src = fs.readFileSync(path.join(ROOT, "dashboard", "branding.js"), "utf8");
const html = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");

// ---- 0. index.html vẫn khai hai thẻ icon trỏ vào logo ----
check("index.html khai <link rel=icon> trỏ /brand-logo", /<link rel="icon" href="\/brand-logo/.test(html));
check("index.html khai apple-touch-icon trỏ /brand-logo", /<link rel="apple-touch-icon" href="\/brand-logo/.test(html));

// ---- 1. Chạy THẬT bustLogos ----
const bust = bocHam(src, "function bustLogos(rieng) {");
const doi = bocHam(src, "function doiFavicon(v) {");
check("bóc được bustLogos và doiFavicon khỏi branding.js", !!bust && !!doi);

const head = taoHead([
  taoLink("icon", "/brand-logo?v=5"),
  taoLink("apple-touch-icon", "/brand-logo?v=5"),
  taoLink("manifest", "/static/manifest.json?v=2"),
]);
const imgs = [{ src: "/brand-logo?v=5" }, { src: "/brand-logo?v=5" }];
const doc = {
  head,
  querySelectorAll: () => imgs,
  createElement: (tag) => (tag === "link" ? taoLink("", "") : {}),
};
let loi = null;
try {
  new Function("document", "window",
    "function doiFavicon(v) {" + doi.than + "}\n" +
    "function bustLogos(rieng) {" + bust.than + "}\n" +
    "bustLogos(true);")(doc, {});
} catch (e) {
  loi = e;
}
check("bustLogos CHẠY ĐƯỢC, không ném lỗi", loi === null, loi && loi.constructor.name + ": " + loi.message);

// ---- 2. Kết quả trên <head> ----
const icons = head.con.filter((l) => ["icon", "apple-touch-icon"].includes(l.getAttribute("rel")));
check("vẫn còn đúng hai thẻ icon (một icon, một apple-touch-icon)",
  icons.length === 2 && new Set(icons.map((l) => l.getAttribute("rel"))).size === 2,
  icons.map((l) => l.getAttribute("rel")).join(", "));

const hrefs = icons.map((l) => l.getAttribute("href"));
check("cả hai thẻ icon đã trỏ sang URL MỚI, không còn ?v=5",
  hrefs.every((h) => /^\/brand-logo\?v=\d{10,}$/.test(h)), hrefs.join(", "));
check("thẻ icon CŨ đã bị gỡ hẳn, không nằm lại trong head",
  !head.con.some((l) => l.getAttribute("href") === "/brand-logo?v=5"),
  head.con.map((l) => l.getAttribute("rel") + "=" + l.getAttribute("href")).join(" | "));
check("KHÔNG đụng tới thẻ manifest",
  head.con.some((l) => l.getAttribute("rel") === "manifest" && l.getAttribute("href") === "/static/manifest.json?v=2"));
check("ảnh logo trong trang vẫn được làm mới như cũ",
  imgs.every((i) => /^\/brand-logo\?v=\d{10,}$/.test(i.src)), imgs.map((i) => i.src).join(", "));
check("ảnh và icon dùng CÙNG một chuỗi bể cache", imgs[0].src === hrefs[0]);

console.log(fails.length ? "\nFAIL: " + fails.join(", ") : "\nTat ca OK");
process.exit(fails.length ? 1 : 0);
