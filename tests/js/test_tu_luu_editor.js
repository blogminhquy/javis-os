/* Trình sửa TỰ LƯU sau khi ngừng gõ.

       node tests/js/test_tu_luu_editor.js

   Chủ repo yêu cầu (2026-09-11): "tự động save file ngay khi user gõ xong chữ để tránh mất
   mát dữ liệu".

   Lỗ hổng thật trước bản này: rời file (bấm [[wikilink]], đổi file trong cây) thì openNote đã
   lưu hộ, NHƯNG bấm Escape / nút X / đóng tab thì KHÔNG ai lưu cả - gõ cả buổi rồi bấm Escape
   là mất sạch trong im lặng.

   Bốn chỗ hỏng âm thầm nên phải canh:

     1. Thứ tự lúc đóng. Phải lưu TRƯỚC khi dọn khung soạn: hàm lấy nội dung đọc thẳng từ DOM,
        dọn xong mới gọi là đọc được khung rỗng rồi GHI RỖNG lên file - mất trắng cả note.
     2. Chỗ gắn listener. #neBody sống qua mọi lần mở file; gắn "input" vào đó là mỗi lần mở
        thêm một listener nữa, chồng vô hạn, và một cú gõ bắn N lượt ghi đĩa.
     3. Chốt "có sửa gì chưa". Bản render đổi về markdown luôn lệch đôi chỗ so với file gốc,
        nên tự lưu mà không qua chốt này là chỉ MỞ file ra đọc cũng bị ghi đè định dạng.
     4. Hẹn phải ĐẨY LẠI mỗi lần gõ (debounce), không thì gõ một bài dài thành vài trăm lượt
        ghi đĩa. */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const CON = D("console.js");
const FE = D("file-editor.js");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Trình sửa chính (console.js, trang Tệp tin + deep-link)
// ============================================================
check("có bộ hẹn tự lưu", /function _neAutoHoan\(\)/.test(CON) && /async function _neAutoLuu\(\)/.test(CON));
check("mỗi lần gõ ĐẨY LẠI hẹn từ đầu (debounce)",
      /function _neAutoHoan\(\) \{\s*clearTimeout\(_neAutoHen\);\s*_neAutoHen = setTimeout\(_neAutoLuu, NE_AUTO_MS\);/.test(CON));
const ms = /const NE_AUTO_MS = (\d+)/.exec(CON);
check("khoảng chờ nằm trong khoảng hợp lý 0.5s - 3s", !!ms && +ms[1] >= 500 && +ms[1] <= 3000);
check("CANARY: tự lưu đi qua chốt _neCoSuaChua, không ghi bừa",
      /if \(!_neSaveFn \|\| !_neCoSuaChua\(\)\) return/.test(CON));
check("dùng LẠI _neSaveFn của nút Lưu (nút nháy 'Đã lưu' nên người dùng thấy nó xảy ra thật)",
      /return await _neSaveFn\(\)/.test(CON));
check("ẩn tab thì lưu ngay", /visibilitychange[\s\S]{0,90}_neAutoLuu\(\)/.test(CON));
check("đóng tab thì lưu ngay", /pagehide[\s\S]{0,60}_neAutoLuu\(\)/.test(CON));

// --- Thứ tự trong closeNote: lưu TRƯỚC khi dọn ---
const iClose = CON.indexOf("function closeNote()");
check("tìm được closeNote", iClose > 0);
const than = CON.slice(iClose, CON.indexOf("\n  }", iClose));
const iLuu = than.indexOf("_neSaveFn()");
const iDon = than.indexOf('getElementById("neBody").innerHTML = ""');
const iXoa = than.indexOf("_neSaveFn = null");
check("đóng khung (Escape / nút X) thì LƯU, không im lặng bỏ", iLuu > 0);
check("CANARY: lưu TRƯỚC khi dọn khung soạn (dọn trước là ghi rỗng lên file)", iLuu > 0 && iDon > iLuu);
check("CANARY: lưu TRƯỚC khi bỏ hàm lưu đi", iLuu > 0 && iXoa > iLuu);
check("đóng khung thì huỷ luôn hẹn đang chờ", /_neAutoHuy\(\);/.test(than));
check("chỉ lưu khi có sửa", /if \(_neSaveFn && _neCoSuaChua\(\)\)/.test(than));

// --- Chỗ gắn listener ---
check("CANARY: gắn input vào CHÍNH hai khung soạn, KHÔNG gắn vào #neBody",
      /ta\.addEventListener\("input", _neAutoHoan\)/.test(CON) &&
      /_wysAuto\.addEventListener\("input", _neAutoHoan\)/.test(CON) &&
      !/body\.addEventListener\("input"/.test(CON));
check("có nói rõ vì sao không gắn vào #neBody", /chồng vô hạn/.test(CON));

// ============================================================
// 2. Trình sửa trong khung chat (file-editor.js)
// ============================================================
check("khung chat cũng tự lưu", /function tuLuu\(\)/.test(FE) && /autoHen = setTimeout\(tuLuu, \d+\)/.test(FE));
check("cũng chỉ ghi khi nội dung KHÁC lúc mở", /if \(nay === goc\) return;/.test(FE));
check("chốt mốc trước khi gửi để gõ tiếp vẫn tính là sửa", /goc = nay;/.test(FE));
const iFeClose = FE.indexOf("function close()");
const thanFe = FE.slice(iFeClose, FE.indexOf("\n  }", iFeClose));
check("đóng khung chat thì lưu", /autoFlush\(\)/.test(thanFe));
check("CANARY: cũng lưu TRƯỚC khi dọn elBody",
      thanFe.indexOf("autoFlush()") < thanFe.indexOf('elBody.innerHTML = ""'));
check("khung chat: ẩn tab / đóng tab cũng lưu ngay",
      /visibilitychange[\s\S]{0,160}autoFlush\(\)/.test(FE) && /pagehide[\s\S]{0,160}autoFlush\(\)/.test(FE));
check("gắn input vào textarea và bản render", /querySelectorAll\("textarea, \.ne-wys"\)/.test(FE));

check("KHÔNG dùng ký tự em dash", !CON.includes("—") && !FE.includes("—"));

console.log(fails.length ? "\nFAIL: " + fails.length : "\nTất cả đều xanh");
process.exit(fails.length ? 1 : 0);
