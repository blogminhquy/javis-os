/* Mở một note .md ra sửa rồi bấm Lưu KHÔNG được làm hỏng file.

       node tests/js/test_luu_md_khong_hong.js

   Lỗi thật chủ repo báo 2026-08-13 ("một số file kèm theo .md đang không đọc được"). File gửi
   kèm mở ra thì đầu file là:

       * * *
       status: active
       priority: high
       * * *
       ## 1\. Tóm tắt sản phẩm

   Đó KHÔNG phải cách file được ghi ra. Đó là dấu vết của một vòng lưu qua trình sửa WYSIWYG:

     markdown --mdToHtml--> HTML --turndown--> markdown

   Hai chỗ rò trong vòng đó, cả hai đều là mất dữ liệu thật:

     1. Frontmatter `---...---` rơi vào luật "--- = đường kẻ ngang" của markdown, nên turndown
        ghi lại thành `* * *`. Từ giây đó file KHÔNG còn frontmatter: type, status, created đều
        thành mấy dòng chữ rời, và Javis, dataview lẫn Obsidian đều đọc trượt.
     2. Turndown thoát "1." đầu dòng thành "1\.", mà mdToHtml lại KHÔNG hiểu dấu thoát markdown
        nên lần render sau nó là chữ thật, rồi turndown thoát tiếp chính dấu gạch đó: "1\\.",
        "1\\\."... Mỗi lần mở ra sửa là file bẩn thêm một lớp - lỗi dồn, không tự khỏi.

   File này khoá phần đo được không cần trình duyệt: mdToHtml phải TÁCH frontmatter ra khối
   riêng giữ nguyên văn, phải GỠ dấu thoát, và console.js phải có luật turndown trả frontmatter
   về đúng như cũ. (Vòng round-trip đầy đủ cần turndown - đã đo tay trong Chromium trước khi
   chốt: sau 3 lần lưu liên tiếp nội dung đứng yên, không đổi thêm một ký tự.) */
const fs = require("fs");
const path = require("path");
const { mdToHtml } = require("../../dashboard/chat-render.js");

const ROOT = path.join(__dirname, "..", "..");
const CONSOLE = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const STYLE = fs.readFileSync(path.join(ROOT, "dashboard", "style.css"), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };
const has = (h, s) => h.indexOf(s) !== -1;

// ============================================================
// 1. Frontmatter: khối riêng, giữ nguyên văn, không cho sửa
// ============================================================
const SRC = "---\nstatus: active\npriority: high\n---\n\n# Tiêu đề\n\nNội dung.\n";
let h = mdToHtml(SRC);

check("frontmatter thành khối riêng, không phải <hr>", has(h, 'class="jv-fm"'));
check("CANARY: KHÔNG còn để frontmatter rơi vào luật đường kẻ ngang",
      !has(h.slice(0, h.indexOf("Tiêu đề")), "<hr>"));
check("khối frontmatter khoá lại, không sửa nhầm được", has(h, 'contenteditable="false"'));
check("giữ NGUYÊN VĂN khối gốc để lưu lại đúng từng ký tự", (() => {
  const m = /data-fm="([^"]*)"/.exec(h);
  return !!m && decodeURIComponent(m[1]) === "---\nstatus: active\npriority: high\n---\n";
})());
check("phần thân sau frontmatter vẫn render bình thường", has(h, "<h1>Tiêu đề</h1>"));

// `---` GIỮA bài vẫn là đường kẻ ngang như cũ - chỉ khối ở ĐẦU file mới là frontmatter.
h = mdToHtml("Đoạn một.\n\n---\n\nĐoạn hai.");
check("--- ở giữa bài vẫn là đường kẻ ngang", has(h, "<hr>") && !has(h, "jv-fm"));

// Thiếu dấu đóng thì không phải frontmatter (vd đang stream dở)
h = mdToHtml("---\nstatus: active\n");
check("thiếu dấu đóng thì không nhận nhầm là frontmatter", !has(h, "jv-fm"));

// ============================================================
// 2. Dấu thoát markdown: gỡ ra, để vòng lưu đứng yên
// ============================================================
check("gỡ dấu thoát của turndown: '1\\.' hiện ra '1.'",
      has(mdToHtml("## 1\\. Tóm tắt"), "<h2>1. Tóm tắt</h2>"));
check("gỡ dấu thoát: '\\*' hiện ra dấu sao chứ không phải in nghiêng",
      has(mdToHtml("2 \\* 3 = 6"), "2 * 3 = 6"));
check("đoạn văn bắt đầu bằng '\\-' KHÔNG bị hiểu thành danh sách",
      !has(mdToHtml("\\- không phải gạch đầu dòng"), "<li>"));
check("in đậm/nghiêng THẬT vẫn chạy (gỡ thoát phải chạy SAU)",
      has(mdToHtml("**đậm** và *nghiêng*"), "<strong>đậm</strong>")
      && has(mdToHtml("**đậm** và *nghiêng*"), "<em>nghiêng</em>"));
check("CANARY: dấu gạch chéo trong code KHÔNG bị đụng tới",
      has(mdToHtml("Chạy `find . -name \\*.md` nhé"), "\\*.md"));

// ============================================================
// 3. Đường về: turndown phải trả lại frontmatter nguyên văn
// ============================================================
check("console.js có luật turndown cho frontmatter", has(CONSOLE, 'addRule("jvfrontmatter"'));
check("luật đó đọc lại data-fm chứ không dựng lại từ chữ hiển thị",
      /jvfrontmatter[\s\S]{0,320}getAttribute\("data-fm"\)/.test(CONSOLE));
check("luật đó nằm cùng chỗ với các luật round-trip khác (dataview, code)",
      CONSOLE.indexOf('addRule("jvfrontmatter"') < CONSOLE.indexOf('addRule("jvcodewrap"'));
check("có kiểu dáng cho khối frontmatter", /\.jv-fm\b/.test(STYLE) && /\.jv-fm .jv-fm-body/.test(STYLE));

console.log();
if (fails.length) { console.log(fails.length + " test HỎNG: " + fails.join(", ")); process.exit(1); }
console.log("OK - test_luu_md_khong_hong: tất cả pass");
