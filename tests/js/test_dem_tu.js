/* Đếm từ và ký tự trên thanh công cụ của trình sửa file (0.65.32).

   Chủ dự án xin 02/10: thanh công cụ của trình sửa file có thêm số từ và số ký tự.

   Chạy: node tests/js/test_dem_tu.js
   Ghi chú: KHÔNG dùng ký tự em dash. */
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const W = require("../../dashboard/word-count.js");
const cs = fs.readFileSync(path.join(root, "dashboard", "console.js"), "utf8");
const html = fs.readFileSync(path.join(root, "dashboard", "index.html"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(root, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(root, "dashboard", "i18n", "en.json"), "utf8"));

const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + JSON.stringify(extra) + "]"));
  if (!cond) fails.push(name);
}
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ---- 1. Đếm chữ thuần ----
let r = W.dem("Xin chào anh, hôm nay trời đẹp.");
check("tiếng Việt: mỗi tiếng là một từ", r.words === 7, r);
check("ký tự tính cả khoảng trắng", r.chars === 31 && r.charsNoSpace === 25, r);
check("rỗng là 0", eq(W.dem(""), { words: 0, chars: 0, charsNoSpace: 0 }) && eq(W.dem(null), { words: 0, chars: 0, charsNoSpace: 0 }));
check("dấu câu đứng riêng không phải từ", W.dem("a - b | c").words === 3);
check("số là từ", W.dem("Doanh thu 1.234.000 đồng").words === 4);
check("xuống dòng không tính là ký tự", W.dem("ab\ncd").chars === 4 && W.dem("ab\r\ncd").chars === 4);
check("chữ có dấu gõ kiểu tổ hợp vẫn là một ký tự", W.dem("é").chars === 1 && W.dem("é").chars === 1);
check("emoji là một ký tự", W.dem("ok 😀").chars === 4);
check("tiếng Anh", W.dem("Hello world, it's fine").words === 4);

// ---- 2. Ghi chú .md: đếm chữ hiện ra, không đếm cú pháp ----
const md = [
  "---", "title: Kế hoạch", "tags: [a, b]", "---",
  "# Tiêu đề lớn",
  "",
  "Chữ **đậm** và *nghiêng* và `mã`.",
  "- [ ] việc một",
  "- [x] việc hai",
  "1. bước đầu",
  "> trích dẫn",
  "Xem [trang chủ](https://vi.du/a/b) và ![hình mèo](anh/meo.png) và [[Ghi chú khác|ghi chú]] và [[Sổ tay]].",
  "![[anh.png]]",
  "| Cột A | Cột B |",
  "|---|:---:|",
  "| 1 | 2 |",
  "***",
  "<b>đậm html</b>",
  "```js",
  "let x = 1;",
  "```",
].join("\n");
const thuan = W.boCuPhapMd(md);
check("bỏ frontmatter", !/title:|tags:/.test(thuan), thuan);
check("bỏ dấu tiêu đề, nhấn mạnh, code", !/[#*_`]/.test(thuan), thuan);
check("bỏ ô checklist và dấu danh sách", !/\[ \]|\[x\]/.test(thuan) && !/^\s*-\s/m.test(thuan) && !/^\s*1\.\s/m.test(thuan), thuan);
check("bỏ đường dẫn, giữ chữ của link và ảnh", !/https?:|meo\.png/.test(thuan) && /trang chủ/.test(thuan) && /hình mèo/.test(thuan), thuan);
check("[[link|tên]] giữ tên, [[link]] giữ link, ![[ảnh]] bỏ hẳn",
  /ghi chú/.test(thuan) && !/Ghi chú khác/.test(thuan) && /Sổ tay/.test(thuan) && !/anh\.png/.test(thuan), thuan);
check("bỏ dòng kẻ bảng và gạch |", !/\|/.test(thuan) && !/---/.test(thuan) && /Cột A/.test(thuan), thuan);
check("bỏ thẻ HTML, giữ chữ", !/<b>/.test(thuan) && /đậm html/.test(thuan), thuan);
check("giữ nội dung trong khối code, bỏ dòng rào", /let x = 1;/.test(thuan) && !/```/.test(thuan), thuan);
r = W.dem("# Xin chào\n\n**Anh** khỏe *không*?", { md: true });
check(".md: '# Xin chào / **Anh** khỏe *không*?' là 5 từ, đếm ký tự không tính cú pháp",
  r.words === 5 && r.chars === "Xin chàoAnh khỏe không?".length, r);
check("file chữ khác đếm nguyên văn (không bỏ cú pháp)", W.dem("# a", {}).words === 1 && W.dem("# a").chars === 3);

// ---- 3. Dây nối vào trình sửa ----
check("index.html nạp word-count.js trước console.js",
  /<script src="\/static\/word-count\.js\?v=\d+"><\/script>[\s\S]*<script src="\/static\/console\.js/.test(html));
check("console.js: có bộ đếm của trình sửa", /function _neGanDemTu\(/.test(cs));
check("console.js: .md đặt bộ đếm ở thanh công cụ định dạng", /_neGanDemTu\(body\.querySelector\("\.ne-fmt"\)/.test(cs));
check("console.js: file chữ khác đặt bộ đếm ở thanh nút phía trên", /_neGanDemTu\(actions,/.test(cs));
check("console.js: đếm lại khi gõ (input) ở cả hai chế độ", /addEventListener\("input", hen\)/.test(cs));
check("console.js: nút định dạng (chèn chữ không bắn input) cũng đếm lại", /ctx\.onChange\(\)/.test(cs));
for (const k of ["cs.ne_count", "cs.ne_count_title"])
  check("i18n vi+en có " + k, typeof vi[k] === "string" && typeof en[k] === "string");
check("nhãn đếm có chỗ cho số từ và số ký tự", /\{words\}/.test(vi["cs.ne_count"]) && /\{chars\}/.test(vi["cs.ne_count"]));

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - đếm từ và ký tự");
