/* iPhone: bấm tải file KHÔNG được thay cả app bằng trang xem file (0.64.46).

       node tests/js/test_ios_tai_file.js

   Chủ dự án gửi ảnh 24/09: app cài ra màn hình chính iPhone, bấm "Tải ảnh PNG" trong chat thì
   cả app biến thành trang "Open in Preview / More..." của iOS, không có nút Back, không còn
   đường về Javis. Nguyên nhân: link tải (<a download>, /files/raw, /files/zip) đi trong CÙNG
   cửa sổ; máy tính và Android thì tải xuống, iOS thì mở trang xem file thay cho app.

   Test này khoá: (1) nhận diện đúng mọi kiểu link tải và không nhận nhầm link thường, (2) nhận
   diện iPhone/iPad (kể cả iPad khai mình là Mac), (3) bộ chặn thật sự được gắn ở pha capture
   và không bao giờ để link tải đi trong cùng cửa sổ trên iOS. Phần chạy thật trên trình duyệt
   đã kiểm tay bằng Chromium giả lập iPhone (xem mô tả PR).

   KHÔNG dùng ký tự em dash. */
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

global.window = { location: { href: "https://javis.example/", origin: "https://javis.example" } };
// Node 22 có sẵn `navigator` CHỈ ĐỌC: gán thẳng không ăn, phải định nghĩa lại.
const datNav = (v) => Object.defineProperty(globalThis, "navigator", { value: v, configurable: true, writable: true });
datNav({ userAgent: "", platform: "", maxTouchPoints: 0 });
const CR = require(path.join(ROOT, "dashboard", "chat-render.js"));
const src = fs.readFileSync(path.join(ROOT, "dashboard", "chat-render.js"), "utf8");

const a = (href, download) => ({
  getAttribute: (k) => (k === "href" ? href : k === "download" ? (download == null ? null : download) : null),
  hasAttribute: (k) => k === "download" && download != null,
});

// ---- 1. Nhận diện link tải ----
for (const [href, dl, mong, ten] of [
  ["/files/raw?brain=brain&path=a.png&dl=1", "", true, "link tải ảnh trong chat (<a download>)"],
  ["/files/raw?brain=brain&path=a.docx", null, true, "link /files/raw không có thuộc tính download"],
  ["/files/zip?brain=brain&path=exports", null, true, "tải cả thư mục (trang Tệp tin)"],
  ["/upload/raw?name=x.pdf", null, true, "file vừa dán vào chat"],
  ["https://javis.example/files/raw?path=x.png", null, true, "URL đầy đủ cùng origin"],
  ["blob:https://javis.example/123", "code.html", true, "tải khối code (blob)"],
  ["#open=wiki%2Fa.md", null, false, "link mở trình sửa trong app"],
  ["https://google.com/files/raw?x=1", null, false, "link ngoài trùng đường dẫn"],
  ["/files/list?path=x", null, false, "API liệt kê file, không phải tải"],
  ["blob:https://javis.example/9", null, false, "blob không có download (ảnh xem trước)"],
]) check((mong ? "nhận là link tải: " : "KHÔNG nhận nhầm: ") + ten, CR.laLinkTaiFile(a(href, dl)) === mong);

// ---- 2. Nhận diện iOS ----
const thu = (ua, platform, tp) => { datNav({ userAgent: ua, platform, maxTouchPoints: tp }); return CR.laIOS(); };
check("iPhone là iOS", thu("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)", "iPhone", 5));
check("iPad khai mình là Mac vẫn là iOS", thu("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "MacIntel", 5));
check("Mac thật không phải iOS", !thu("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "MacIntel", 0));
check("Android không phải iOS (giữ tải thẳng như cũ)", !thu("Mozilla/5.0 (Linux; Android 14)", "Linux armv8l", 5));

// ---- 3. Bộ chặn được gắn đúng chỗ, đúng pha ----
const chan = src.slice(src.indexOf("// TAI FILE TREN IPHONE"), src.indexOf("// Checkbox task"));
check("có bộ chặn tải file trên iPhone", chan.length > 500);
check("gắn ở pha CAPTURE (chạy trước mọi handler khác)", /\}, true\);\s*$/.test(chan.trim() + "\n"));
check("chỉ chạy trên iOS", /if \(!laIOS\(\)\) return;/.test(chan));
check("chặn điều hướng trong cùng cửa sổ", /e\.preventDefault\(\);/.test(chan));
check("ảnh trong chat mở lightbox ngay trong app", /moLightbox\(xem, ten\)/.test(chan));
check("file còn lại mở ở CỬA SỔ MỚI (iOS có nút Xong)", /window\.open\([\s\S]{0,160}?"_blank"\);/.test(chan));
check("blob đi qua bảng chia sẻ của iOS", /chiaSeBlob\(href/.test(chan) && /navigator\.share\(\{ files:/.test(src));
check("không nhận cú bấm đã có người xử lý (ảnh -> lightbox)", /if \(e\.defaultPrevented\) return;/.test(chan));

const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/en.json"), "utf8"));
check("câu báo lỗi có đủ hai thứ tiếng", !!vi["crender.ios_dl_fail"] && !!en["crender.ios_dl_fail"]);

console.log(fails.length ? "\nFAIL: " + fails.join(", ") : "\nTat ca OK");
process.exit(fails.length ? 1 : 0);
