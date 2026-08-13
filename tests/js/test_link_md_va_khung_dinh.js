/* Link trong file .md phải bấm được, và mở ra thì dùng khung sửa DÍNH chứ không bật popup.

       node tests/js/test_link_md_va_khung_dinh.js

   Lỗi thật chủ repo báo (2026-08-04): "các link trong nội dung .md hiện không hover/click để
   mở và nhảy tới file được".

   Nguyên nhân không nằm ở chỗ thiếu xử lý - xử lý CÓ, nhưng nằm SAU hàng rào
   "đang soạn trong editor thì đừng mở gì cả". Mà bản render của trình sửa CHÍNH LÀ
   contenteditable, nên mọi link markdown trong một file .md đều rơi vào hàng rào đó. Trong
   khi [[wikilink]] ngay cạnh nó thì đi được, vì nhánh wikilink nằm TRƯỚC hàng rào. Hai thứ
   nhìn y hệt nhau mà hành xử khác nhau - đúng loại lỗi đọc code không thấy.

   Nên thứ file này canh là THỨ TỰ trong handler, không phải sự tồn tại của mã. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const CR = D("chat-render.js");
const CONSOLE = D("console.js");
const CSS = D("style.css");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ---- Khối handler click chính (khối có cả wikilink lẫn link file) ----
const iWiki = CR.indexOf('closest("a.jv-wikilink")', CR.indexOf("document.addEventListener(\"click\""));
const iFloc = CR.indexOf('closest("a.jv-floc")', iWiki);
const iRao = CR.indexOf("if (trongTrinhSua(e.target)) return;", iWiki);

check("tìm được nhánh wikilink", iWiki > 0);
check("tìm được nhánh link file vault", iFloc > 0);
check("tìm được hàng rào contenteditable", iRao > 0);

// ============================================================
// 1. ĐÂY LÀ LỖI THẬT: thứ tự
// ============================================================
check("CANARY: nhánh link file nằm TRƯỚC hàng rào contenteditable", iFloc < iRao);
check("nhánh wikilink cũng vẫn trước hàng rào (không được đổi ngược lại)", iWiki < iRao);

// Hàng rào cũ dò bằng chuỗi selector lặp lại ở nhiều chỗ; gom về một hàm để sửa một nơi.
check("hàng rào gom thành hàm dùng chung", /function trongTrinhSua\(node\)/.test(CR));
check("hàm đó dò đúng ba loại khung sửa",
  /trongTrinhSua[\s\S]{0,260}contenteditable="true"[\s\S]{0,80}\.jvfe-modal[\s\S]{0,40}\.note-editor/.test(CR));

// ============================================================
// 2. Ảnh trong bản render KHÔNG được cướp cú bấm
// ============================================================
// Ảnh phải kéo thả và xoá được như một ký tự khi đang soạn; cướp click là không sửa được nữa.
check("CANARY: ảnh trong bản render giữ nguyên hành vi cũ",
  /if \(!\(isImg && trongTrinhSua\(e\.target\)\)\)/.test(CR));

// ============================================================
// 3. Link ngoài trong bản render cũng phải mở được
// ============================================================
// Trong contenteditable, thẻ <a target="_blank"> KHÔNG tự mở tab - trình duyệt chỉ đặt con trỏ.
check("link http trong bản render được mở hộ",
  /trongTrinhSua\(e\.target\) && \/\^\(https\?:\|mailto:\)\/i\.test/.test(CR));
check("mở tab mới kèm noopener", /window\.open\(ext\.getAttribute\("href"\), "_blank", "noopener"\)/.test(CR));

// ============================================================
// 4. Hover phải nói được là bấm được
// ============================================================
check("CSS cho con trỏ link trong bản render", /\.ne-prev a:not\(:has\(img\)\)[\s\S]{0,120}cursor: pointer/.test(CSS));
check("CSS đó chừa ảnh ra (ảnh vẫn để sửa)", /:not\(:has\(img\)\)/.test(CSS));

// ============================================================
// 5. Mở file = khung sửa DÍNH, popup chỉ là đường lui
// ============================================================
check("có hàm mở file dùng chung", /function moFileVault\(rel\)/.test(CR));
// Cắt rộng tay: từ 0.30.2 thân hàm dài thêm vì có nhánh chính mới + khối chú thích giải thích
// vì sao. Cắt 700 ký tự như trước là hai indexOf dưới đây cùng ra -1 rồi "-1 < -1" thành sai -
// test đỏ trong khi hợp đồng không hề đổi.
const mo = CR.slice(CR.indexOf("function moFileVault(rel)"), CR.indexOf("function moFileVault(rel)") + 1600);
// 0.30.2 dời QUYẾT ĐỊNH sang console.js (openVaultPath) để deep-link `#open=` và cú bấm thường
// dùng chung một luật - trước đó hai đường xử khác nhau nên cùng một file .html lúc mở ra sửa
// được lúc thì bị quăng về thư mục. Chuỗi rơi cũ giữ nguyên bên dưới làm đường lui cho bản
// console.js cũ, nên hai check kế tiếp vẫn còn nguyên giá trị.
check("CANARY: quyết định mở ở đâu nằm ở MỘT chỗ dùng chung, không phải bản sao trong chat-render",
  mo.indexOf("window.JavisOpenVaultPath(rel)") >= 0
  && mo.indexOf("window.JavisOpenVaultPath(rel)") < mo.indexOf("window.JavisOpenNote(rel)"));
check("CANARY: đường lui vẫn ưu tiên JavisOpenNote (khung dính) chứ không phải popup",
  mo.indexOf("window.JavisOpenNote(rel)") < mo.indexOf("window.JavisEditFile(rel)"));
check("màn hẹp thì vẫn dùng popup (không đủ chỗ cho khung dính)",
  /matchMedia\("\(max-width: 860px\)"\)/.test(mo));
check("popup vẫn còn làm đường lui khi console.js chưa nạp", mo.indexOf("JavisEditFile") !== -1);
check("wikilink cũng đi qua đúng hàm đó", /moFileVault\(hit\.rel\)/.test(CR));
check("link file cũng đi qua đúng hàm đó", /moFileVault\(trimmed\)/.test(CR));
// Không được quay lại gọi thẳng popup từ nhánh link - đó chính là hành vi cũ.
check("CANARY: nhánh link file không còn gọi thẳng JavisEditFile",
  CR.indexOf("window.JavisEditFile(trimmed)") === -1);

// ============================================================
// 6. Cây thư mục tự sổ tới file vừa mở
// ============================================================
check("console.js phơi hàm xổ cây ra ngoài", /window\.JavisRevealInTree = /.test(CONSOLE));
check("CANARY: đi tới file bằng link thì cây sổ theo",
  /window\.JavisOpenNote = function \(brainRel\)[\s\S]{0,1600}_vtRevealInTree\(ceilingRel\)/.test(CONSOLE));
// Đặt trong openNote thì chính cây gọi openNote khi bấm node cũng dựng lại cây - thừa và chớp.
check("KHÔNG nhét lệnh xổ cây vào trong openNote",
  !/async function openNote\(rel, it\)[\s\S]{0,1200}_vtRevealInTree/.test(CONSOLE));
check("xổ cây bọc try/catch (cây chưa dựng thì không được làm hỏng việc mở file)",
  /try \{ _vtRevealInTree\(ceilingRel\); \} catch \(e\) \{\}/.test(CONSOLE));

if (fails.length) {
  console.log("\nFAIL - test_link_md_va_khung_dinh: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_link_md_va_khung_dinh: tất cả pass");
