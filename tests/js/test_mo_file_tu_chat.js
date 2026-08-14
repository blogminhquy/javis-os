/* Bấm một đường dẫn file trong chat: file sửa được thì MỞ RA SỬA, thư mục mới về trang Tệp tin.

       node tests/js/test_mo_file_tu_chat.js

   Chủ repo báo 2026-08-13: Javis xuất ra file .html rồi gửi link trong chat, muốn bấm vào là
   sửa được ngay, "nhưng thi thoảng nó vẫn bị gửi về folder của quản lý file".

   NGUYÊN NHÂN, và đây là thứ test này canh: cùng MỘT thẻ <a> có HAI đường đi tới đích.

     1. Cú bấm thường  -> chat-render.js bắt được -> moFileVault() -> trình sửa.
     2. Deep-link #open= -> Ctrl/chuột giữa mở tab mới, hoặc F5 khi hash còn trên URL
                         -> console.js đọc hash lúc boot.

   Đường 2 trước đây gọi thẳng openFilesAt() nên đổ vào THƯ MỤC. Hai đường, hai luật, nên cùng
   một file .html lúc mở ra sửa được lúc thì không - đúng chữ "thi thoảng". Nay cả hai cùng gọi
   openVaultPath().

   Hành vi đã ĐO trong Chromium thật trước khi chốt (mdToHtml + click thật, console.js giả lập):
     exports/bao-cao.html  -> class jv-floc     title "Mở ra sửa"              -> JavisOpenVaultPath
     notes/ghi-chu.md      -> class jv-floc     title "Mở ra sửa"              -> JavisOpenVaultPath
     anh/hinh.png          -> class jv-fdownload title "Tải file về"           -> (tải, không mở)
     exports/              -> class jv-floc     title "Mở vị trí trong Tệp tin" -> JavisOpenFiles
     Javis/loops           -> class jv-floc     title "Mở vị trí trong Tệp tin" -> JavisOpenFiles
   CI chỉ có node nên file này khoá phần hợp đồng đọc được từ mã nguồn. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const CONSOLE = D("console.js");
const CR = D("chat-render.js");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Một quyết định dùng chung, không phải hai bản sao
// ============================================================
check("console.js có openVaultPath", /function openVaultPath\s*\(/.test(CONSOLE));
check("và phơi ra cho nơi khác gọi", /window\.JavisOpenVaultPath\s*=\s*openVaultPath/.test(CONSOLE));
check("CANARY: deep-link #open= đi qua openVaultPath, KHÔNG phải openFilesAt "
      + "(đây chính là đường đổ vào thư mục)",
      /#open=\(\.\+\)\$\/\.exec[\s\S]{0,400}?openVaultPath\(decodeURIComponent/.test(CONSOLE));
check("chat-render ưu tiên đúng hàm đó thay vì tự có luật riêng",
      /function moFileVault[\s\S]{0,400}?window\.JavisOpenVaultPath/.test(CR));

// ============================================================
// 2. Luật chọn: file sửa được -> trình sửa; thư mục -> trang Tệp tin
// ============================================================
const than = (CONSOLE.match(/function openVaultPath\s*\([\s\S]*?\n  \}/) || [""])[0];
check("nhận ra thư mục bằng dấu chấm trong tên (cùng luật openFilesAt)",
      /laThuMuc/.test(than) && /indexOf\("\."\)\s*<\s*0/.test(than));
check("file sửa được thì mở TRÌNH SỬA", /VT_TEXT_EXTS\.includes\(duoi\)/.test(than)
      && /JavisOpenNote/.test(than));
check("màn hẹp rơi về modal file-editor chứ không bỏ cuộc", /JavisEditFile/.test(than));
check("CANARY: về trang Tệp tin chỉ là ĐƯỜNG LUI cuối cùng, không phải mặc định",
      than.lastIndexOf("openFilesAt") > than.lastIndexOf("JavisEditFile"));
check(".html nằm trong danh sách sửa được của trình sửa cây",
      /VT_TEXT_EXTS = \[[^\]]*"\.html"/.test(CONSOLE));

// ============================================================
// 3. Chữ trên link phải đúng việc cú bấm đó LÀM
// ============================================================
check("có phân biệt đuôi sửa được khi đặt title", /EDIT_EXT_RE\s*=/.test(CR));
check("file sửa được -> 'Mở ra sửa'", /Mở ra sửa/.test(CR));
check("thư mục -> 'Mở vị trí trong Tệp tin'", /Mở vị trí trong Tệp tin/.test(CR));
check("CANARY: không còn dán một câu 'mở vị trí' cho MỌI thứ (bấm .html mà hứa mở thư mục)",
      !/class="jv-floc[^"]*"[^']*title="Mo vi tri trong Tep tin"/.test(CR));
check("html + htm đều tính là sửa được", /html\?/.test(CR) || /\bhtml\b[\s\S]{0,40}\bhtm\b/.test(CR));

// ============================================================
// 4. Ảnh/pdf/zip vẫn là TẢI VỀ, không lôi vào trình sửa
// ============================================================
check("vẫn giữ nhánh tải file cho ảnh/video/pdf/nén", /DOWNLOAD_EXT_RE\s*=/.test(CR));
check("CANARY: .html KHÔNG bị xếp vào nhóm tải về", !/DOWNLOAD_EXT_RE = [^\n]*\bhtml\b/.test(CR));

console.log();
if (fails.length) { console.log(fails.length + " test HỎNG: " + fails.join(", ")); process.exit(1); }
console.log("OK - test_mo_file_tu_chat: tất cả pass");
