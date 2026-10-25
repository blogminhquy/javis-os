/* Form "Thêm link" của ngăn kéo tài liệu (project, cuộc, trợ lý) luôn nói ra kết quả.

       node tests/js/test_them_link_bao_ro.js

   Chủ repo 25/10, ảnh chụp ngăn kéo của một trợ lý: "lỗi khi thêm link trên agent đang không
   thêm được, ấn nút thêm không hiện gì". Server thêm được bình thường; cái hỏng là ba đường
   IM LẶNG của themLink:
   - ô URL trống: `if (!u) return;` không nói gì;
   - link đã có trong danh sách: server trả ok với id cũ, form xoá trắng ô URL, danh sách y
     nguyên, nhìn như bấm mà không ăn;
   - dán thiếu https:// (thói quen chép "docs.google.com/..."): server từ chối bằng một alert.
   Nay cả ba hiện một dòng ngay trong form, hàng trùng sáng lên, và thiếu scheme thì tự thêm. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const SU = fs.readFileSync(path.join(ROOT, "dashboard", "sessions-ui.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "style.css"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

const fails = [];
const check = (ten, ok, them) => {
  console.log((ok ? "ok   " : "FAIL ") + ten + (ok || them === undefined ? "" : "  [" + them + "]"));
  if (!ok) fails.push(ten);
};

const ham = (ten) => (SU.match(new RegExp("(async )?function " + ten + "\\([\\s\\S]*?\\n  \\}")) || [""])[0];
const THEM = ham("themLink");

// 1. Không còn đường thoát im lặng
check("themLink có thân", THEM.length > 0);
check("ô trống không còn `return` im lặng", !/if \(!u\) return;/.test(THEM), THEM.slice(0, 160));
check("ô trống thì báo trong form", /if \(!u\) \{ baoFormLink\(pdT\("proj\.link_need_url"\), true\)/.test(THEM));
check("link trùng được dò TRƯỚC khi gọi server",
  THEM.indexOf("proj.link_dup") > 0 && THEM.indexOf("proj.link_dup") < THEM.indexOf("pdPost("));
check("link trùng làm hàng cũ sáng lên", /nhayHang\(co\.id\)/.test(THEM));
check("lỗi server báo trong form, không bằng alert", !/alert\(/.test(THEM) && /baoFormLink\(pdT\("proj\.err_add_link"\)/.test(THEM));
check("thêm xong cũng nói ra", /baoFormLink\(pdT\("proj\.link_added"\), false\)/.test(THEM));
check("form có chỗ hiện dòng báo", /'<div class="pd-fmsg" role="status" hidden><\/div>'/.test(SU));
check("gõ lại thì dòng báo cũ biến mất", /o\.oninput = function \(\) \{ baoFormLink\(""\); \};/.test(SU));

// 2. Thiếu https:// thì tự thêm, scheme lạ để server chặn như cũ
const chuanHoaUrl = new Function(ham("chuanHoaUrl") + "\nreturn chuanHoaUrl;")();
[
  ["docs.google.com/spreadsheets/d/x/edit", "https://docs.google.com/spreadsheets/d/x/edit"],
  ["https://a.com/x", "https://a.com/x"],
  ["http://a.com", "http://a.com"],
  ["example.com:8080/x", "https://example.com:8080/x"],
  ["javascript:alert(1)", "javascript:alert(1)"],
  ["file:///etc/passwd", "file:///etc/passwd"],
  ["chỉ là chữ", "chỉ là chữ"],
].forEach(([vao, ra]) => check("chuanHoaUrl(" + vao + ")", chuanHoaUrl(vao) === ra, chuanHoaUrl(vao)));

// 3. Từ điển và CSS
["proj.link_need_url", "proj.link_dup", "proj.link_added"].forEach((k) => {
  check("vi có " + k, typeof VI[k] === "string" && VI[k].length > 0);
  check("en có " + k, typeof EN[k] === "string" && EN[k].length > 0);
});
check("link_dup có chỗ cho tên link", VI["proj.link_dup"].includes("{ten}") && EN["proj.link_dup"].includes("{ten}"));
check("CSS cho dòng báo", /\.pd-fmsg \{/.test(CSS) && /\.pd-fmsg\.loi \{/.test(CSS));
check("CSS cho hàng sáng lên", /\.pd-row\.nhay \{ animation: pdNhay/.test(CSS) && /@keyframes pdNhay/.test(CSS));

if (fails.length) { console.log("\n" + fails.length + " FAIL"); process.exit(1); }
console.log("\nOK");
