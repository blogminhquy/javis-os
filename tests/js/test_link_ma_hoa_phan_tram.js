/* Link markdown trỏ vào vault mà đường dẫn bị mã hoá phần trăm thì vẫn phải mở đúng file.

       node tests/js/test_link_ma_hoa_phan_tram.js

   Lỗi thật chủ repo báo (2026-08-12): trong `AGENTS.md` bấm vào hai link "LLM Wiki" và
   "Bullet Journal số hoá" thì không mở ra gì cả. Bấm xong KHÔNG có gì xảy ra - không lỗi,
   không thông báo, không cả một dòng đỏ ở console. Vòng đầu chỉ chữa triệu chứng: đổi hai
   link đó sang [[wikilink]] cho nó chạy. Nhưng lỗi ở tầng dashboard nên nó quay lại ngay
   khi gặp link markdown khác - đúng như chủ repo báo lần hai.

   Gốc: đường dẫn trong link markdown là URL-ish. Obsidian, VS Code và cả AI đều ghi
   "07%20-%20Wiki/LLM%20Wiki.md" chứ không ghi khoảng trắng trần. Tên THẬT trên đĩa thì
   không hề có %20. Không gỡ mã hoá thì dashboard đi hỏi server một file tên
   "07%20-%20Wiki" - thứ không bao giờ tồn tại.

   Ảnh còn tệ hơn một bậc: fileUrl() mã hoá THÊM lần nữa, ra "%2520". Server giải mã một
   lần được lại đúng "%20", vẫn trượt, và ô ảnh thành ô xám.

   Hai bờ phải giữ cùng lúc, nên test canh cả hai:
   1. Đường dẫn VAULT thì gỡ mã hoá (nó sẽ đi thẳng tới tên file trên đĩa).
   2. URL NGOÀI thì TUYỆT ĐỐI không gỡ - "%E1%BB%87" trong link Wikipedia là một phần của
      địa chỉ mạng, gỡ ra là hỏng link. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const { mdToHtml } = require(path.join(ROOT, "dashboard", "chat-render.js"));
const CR = fs.readFileSync(path.join(ROOT, "dashboard", "chat-render.js"), "utf8");
const CONSOLE = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// data-vault-path là thứ handler click thật sự đem đi mở file (chat-render.js: moFileVault).
// Soi ĐÚNG thuộc tính đó, không soi href - href là deep-link cho Ctrl+click, sai ở đó không
// làm chết cú bấm thường.
const vaultPath = (md) => {
  const m = /data-vault-path="([^"]*)"/.exec(mdToHtml(md));
  return m ? m[1] : null;
};

// ============================================================
// 1. Chính hai link chủ repo báo
// ============================================================
check("CANARY: link có %20 mở đúng tên file thật",
  vaultPath("[LLM Wiki](07%20-%20Wiki/obsidian-system/LLM%20Wiki.md)")
  === "07 - Wiki/obsidian-system/LLM Wiki.md");
check("CANARY: chữ tiếng Việt mã hoá cũng ra đúng",
  vaultPath("[BuJo](07%20-%20Wiki/C%C3%A2u%20l%E1%BB%87nh.md)")
  === "07 - Wiki/Câu lệnh.md");

// ============================================================
// 2. Không được phá những đường dẫn vốn đang chạy
// ============================================================
check("đường dẫn khoảng trắng trần giữ nguyên",
  vaultPath("[x](07 - Wiki/LLM Wiki.md)") === "07 - Wiki/LLM Wiki.md");
// decodeURIComponent ném lỗi với "100%.md" (%.m không phải %hh). Bắt lại rồi giữ nguyên,
// vì dấu % đó là ký tự THẬT trong tên file chứ không phải mã hoá.
check("tên file có dấu % thật không bị nuốt",
  vaultPath("[x](bao-cao/100%.md)") === "bao-cao/100%.md");
// "+" là ký tự hợp lệ trong tên file. decodeQueryPart() đổi "+" thành khoảng trắng vì đó là
// luật của query string - đem luật đó sang đường dẫn là hỏng file có dấu cộng.
check("CANARY: dấu + trong tên file KHÔNG thành khoảng trắng",
  vaultPath("[x](ghi-chu/a+b.md)") === "ghi-chu/a+b.md");

// ============================================================
// 3. URL ngoài phải giữ nguyên mã hoá
// ============================================================
const ngoai = mdToHtml("[VN](https://vi.wikipedia.org/wiki/Vi%E1%BB%87t_Nam)");
check("CANARY: URL ngoài giữ nguyên phần trăm",
  ngoai.indexOf("https://vi.wikipedia.org/wiki/Vi%E1%BB%87t_Nam") >= 0);
check("URL ngoài không bị biến thành link vault", ngoai.indexOf("data-vault-path") < 0);

// ============================================================
// 4. Ảnh: mã hoá đúng MỘT lần
// ============================================================
// %2520 = đã mã hoá hai lần. Server giải một lần ra "%20", vẫn không có file đó, ô ảnh xám.
const anh = mdToHtml("![a](attachments/a%20b.png)");
check("CANARY: ảnh không bị mã hoá chồng (%2520)", anh.indexOf("%2520") < 0);
check("ảnh gửi lên server đúng một lớp mã hoá", /path=attachments%2Fa%20b\.png/.test(anh));
check("ảnh giữ tên thật ở data-vault-path",
  /data-vault-path="attachments\/a b\.png"/.test(anh));

// ============================================================
// 5. Bấm trượt phải NÓI RA, không được im
// ============================================================
// Trước bản này file-không-tồn-tại và file-nhị-phân rơi chung một cửa, và người dùng nhận
// đúng một câu "loại file này không xem trực tiếp - hãy tải về". Câu đó sai sự thật khi link
// trỏ trượt, lại còn mời tải một thứ không có - nên người ta đi nghi ngờ loại file thay vì
// nghi ngờ cái link, tức là tìm sai hướng ngay từ đầu.
check("có nhánh riêng cho file không tìm thấy", /_neRenderMissing/.test(CONSOLE));
check("CANARY: 404 đi nhánh riêng, không rơi vào 'hãy tải về'",
  /resp\.status === 404.*_neRenderMissing/s.test(
    CONSOLE.slice(CONSOLE.indexOf("const isMd = ext") - 900, CONSOLE.indexOf("const isMd = ext"))));
check("báo lỗi in ra ĐƯỜNG DẪN đã thử (để còn sửa được link)",
  /Link trỏ tới <code>\$\{esc\(rel\)\}/.test(CONSOLE));
check("file nhị phân / quá to VẪN mời tải về", /_neRenderDownload\(body, actions, rel, it\)/.test(CONSOLE));

// ============================================================
// 6. Wikilink kẹt trạng thái 'bận' thì chết hẳn
// ============================================================
// jv-wl-busy chặn mọi cú bấm sau đó, nên một lỗi không ai bắt là link đó chết cho tới khi vẽ
// lại cả bài - đúng triệu chứng "thi thoảng bấm không mở được file tiếp theo".
const kh = CR.slice(CR.indexOf("function openWikilink("), CR.indexOf("function moFileVault("));
check("bóc được khối openWikilink", kh.length > 200);
check("CANARY: wkResolve hỏng thì gỡ lớp bận ra", /\.catch\(function \(\) \{[\s\S]*jv-wl-busy/.test(kh));

console.log("");
if (fails.length) { console.log("THẤT BẠI " + fails.length + ": " + fails.join(", ")); process.exit(1); }
console.log("OK - test_link_ma_hoa_phan_tram: tất cả pass");
