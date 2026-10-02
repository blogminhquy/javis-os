/* word-count.js - đếm từ và ký tự cho trình sửa file (0.65.32).

   Chủ dự án xin 02/10: thanh công cụ của trình sửa file có thêm số từ và số ký tự. Hàm thuần,
   không đụng DOM, test bằng node được (tests/js/test_dem_tu.js).

   Cách đếm, chọn để khớp thứ người viết nhìn thấy:
   - Ghi chú .md đếm CHỮ HIỆN RA, không đếm cú pháp: bỏ frontmatter, dấu #, *, _, ~, `, dấu đầu
     dòng danh sách và trích dẫn, ô [ ] của checklist, gạch | của bảng, đường dẫn trong
     [chữ](link) và ![ảnh](link) (giữ chữ), [[link|tên]] giữ tên, thẻ HTML.
   - File chữ khác (.txt, code) đếm nguyên văn.
   - Từ: cụm liền nhau có ít nhất một chữ cái hoặc chữ số. Tiếng Việt mỗi tiếng là một từ, như
     Word và Google Docs đếm. Dấu câu đứng riêng ("-", "|") không phải từ.
   - Ký tự: tính cả khoảng trắng, không tính dấu xuống dòng (giống Word). Chuẩn hoá NFC trước,
     để chữ có dấu gõ kiểu tổ hợp (e + dấu) vẫn là một ký tự.
   Ghi chú: KHÔNG dùng ký tự em dash. */
(function () {
  "use strict";

  function boCuPhapMd(src) {
    var s = String(src == null ? "" : src).replace(/\r\n?/g, "\n");
    // Frontmatter ở đầu file.
    s = s.replace(/^---\n[\s\S]*?\n---(\n|$)/, "");
    // Rào khối code: bỏ dòng ``` / ~~~, giữ nội dung bên trong.
    s = s.replace(/^\s*(```|~~~).*$/gm, "");
    // Bảng: bỏ dòng kẻ |---|:---:|, rồi bỏ gạch |.
    s = s.replace(/^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/gm, "");
    // Đường kẻ ngang ---, ***, ___.
    s = s.replace(/^\s*([-*_])(\s*\1){2,}\s*$/gm, "");
    // Ảnh và link: giữ chữ, bỏ đường dẫn.
    s = s.replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1");
    s = s.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1");
    // [[ghi chú|tên hiện]] -> tên hiện; [[ghi chú]] -> ghi chú; ![[ảnh.png]] -> bỏ hẳn.
    s = s.replace(/!\[\[[^\]]*\]\]/g, "");
    s = s.replace(/\[\[([^\]|]*)\|([^\]]*)\]\]/g, "$2");
    s = s.replace(/\[\[([^\]]*)\]\]/g, "$1");
    // Thẻ HTML.
    s = s.replace(/<[^>\n]+>/g, "");
    // Đầu dòng: tiêu đề, trích dẫn, danh sách, checklist.
    s = s.replace(/^\s{0,3}#{1,6}\s+/gm, "");
    s = s.replace(/^\s*(>\s*)+/gm, "");
    s = s.replace(/^\s*([-*+]|\d+[.)])\s+(\[[ xX]\]\s+)?/gm, "");
    // Nhấn mạnh và code trong dòng.
    s = s.replace(/[*_~`]+/g, "");
    s = s.replace(/\|/g, " ");
    return s;
  }

  function dem(text, opts) {
    var s = String(text == null ? "" : text);
    if (opts && opts.md) s = boCuPhapMd(s);
    if (s.normalize) s = s.normalize("NFC");
    var tu = s.match(/[^\s]+/g) || [];
    var words = 0;
    for (var i = 0; i < tu.length; i++) {
      if (/[\p{L}\p{N}]/u.test(tu[i])) words++;
    }
    var motDong = s.replace(/[\r\n]+/g, "");
    var chars = Array.from(motDong).length;
    var charsNoSpace = Array.from(motDong.replace(/\s+/g, "")).length;
    return { words: words, chars: chars, charsNoSpace: charsNoSpace };
  }

  var api = { dem: dem, boCuPhapMd: boCuPhapMd };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.JavisWordCount = api;
})();
