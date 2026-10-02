/* AI sửa ảnh rồi GHI ĐÈ đúng đường dẫn cũ: tin mới phải hiện ẢNH MỚI (0.65.33).

       node tests/js/test_anh_sua_cung_ten.js

   Chủ dự án báo 02/10: nhờ AI sửa một ảnh nó vừa tạo, AI sửa đúng và giữ nguyên đường dẫn, thì
   khung chat vẫn hiện ảnh cũ tới khi tải lại trang. Lý do: cùng một URL /files/raw thì trình
   duyệt dùng lại ảnh đã nạp. Nay mỗi bong bóng của Javis mang một "phiên bản" ảnh (mốc giờ của
   tin), gắn thành &v= vào đường ảnh: tin mới luôn tải ảnh mới, tin cũ dựng lại vẫn đúng URL cũ
   nên tải lại trang không tải lại ảnh vô cớ.

   Ghi chú: KHÔNG dùng ký tự em dash. */
"use strict";
const fs = require("fs");
const path = require("path");
const { mdToHtml } = require("../../dashboard/chat-render.js");
const app = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "app.js"), "utf8");

const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}
global.currentBrainPath = () => "brains/Brain Default";
const srcs = (h) => [...h.matchAll(/<img[^>]* src="([^"]*)"/g)].map(m => m[1].replace(/&amp;/g, "&"));
const thu = (h) => ((h.match(/data-jv-thu="([^"]*)"/) || [])[1] || "").replace(/&amp;/g, "&").split("|").filter(Boolean);

const ANH = "![cách làm](attachments/cach-lam.png)";

// ---- 1. Không có phiên bản: y như cũ (trình sửa .md, nơi khác) ----
let h = mdToHtml(ANH);
check("không truyền anhV: đường ảnh giữ nguyên, không có &v=", srcs(h).length === 1 && !/[?&]v=/.test(h), h);

// ---- 2. Có phiên bản: ảnh chính và mọi đường dự phòng đều mang &v= ----
h = mdToHtml(ANH, null, { anhV: "1790000000123" });
check("ảnh chính mang &v= của bong bóng", srcs(h)[0].endsWith("&v=1790000000123"), srcs(h)[0]);
const hThu = mdToHtml("![x](anh/cach-lam.png)", null, { anhV: "1790000000123" });
check("đường dự phòng (thử attachments/ khi 404) cũng mang &v=",
  thu(hThu).length > 0 && thu(hThu).every(u => u.endsWith("&v=1790000000123")), thu(hThu).join(" | "));
check("link phóng to (lightbox) mở đúng ảnh mới", /class="jv-img-link" href="[^"]*&amp;v=1790000000123"/.test(h));
const h2 = mdToHtml(ANH, null, { anhV: "1790000009999" });
check("hai tin khác nhau thì hai URL khác nhau (tin mới nạp ảnh mới)", srcs(h)[0] !== srcs(h2)[0]);
check("cùng một tin dựng lại (stream nhiều khung) thì URL y hệt, không nạp lại mỗi khung",
  srcs(mdToHtml(ANH, null, { anhV: "1790000000123" }))[0] === srcs(h)[0]);
check("ảnh wikilink ![[...]] cũng mang &v=",
  srcs(mdToHtml("![[attachments/cach-lam.png]]", null, { anhV: "42" }))[0].endsWith("&v=42"));
check("ảnh ngoài (https) không bị gắn &v=",
  srcs(mdToHtml("![x](https://vi.du/a.png)", null, { anhV: "42" }))[0] === "https://vi.du/a.png");
check("phiên bản không rò sang lượt render sau",
  !/[?&]v=/.test(mdToHtml(ANH)));
check("trình sửa .md (không truyền anhV) không bị gắn &v=, lưu lại không đổi đường dẫn",
  !/[?&]v=/.test(mdToHtml(ANH, null, { trinhSua: true })));

// ---- 3. Dây nối ở app.js ----
check("markdownToHtml chuyển anhV sang chat-render",
  /function markdownToHtml\(text, brain, anhV\) \{[\s\S]{0,200}window\.mdToHtml\(text, brain, anhV \? \{ anhV: String\(anhV\) \} : undefined\)/.test(app));
check("bong bóng stream có phiên bản riêng, giữ suốt lượt", /function createStreamingBubble\(\) \{[\s\S]{0,160}div\.dataset\.anhV = String\(Date\.now\(\)\);/.test(app));
check("tin dựng lại từ lịch sử dùng mốc giờ của chính nó", /div\.dataset\.anhV = String\(ts === undefined \? Date\.now\(\) : \(ts \|\| ""\)\);/.test(app));
check("mọi chỗ vẽ lại bong bóng của Javis đều chuyển phiên bản",
  /markdownToHtml\(t\.text, undefined, t\.bubble\.dataset\.anhV\)/.test(app)
  && /markdownToHtml\(shownText, undefined, msgEl\.dataset\.anhV\)/.test(app)
  && /markdownToHtml\(s\.text, undefined, s\.el\.dataset\.anhV\)/.test(app)
  && /markdownToHtml\(_liveJavisText, undefined, _liveJavisBubble\.dataset\.anhV\)/.test(app));

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - ảnh sửa cùng tên hiện ảnh mới");
