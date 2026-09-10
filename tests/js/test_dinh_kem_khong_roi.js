/* File đính kèm không được rơi mất: lúc Enter sớm, và lúc mở lại hội thoại.

       node tests/js/test_dinh_kem_khong_roi.js

   Chủ repo báo 2026-09-10: "gửi ảnh hoặc văn bản thì sau khi ấn enter không hiện ở đoạn
   chat, cũng không xem lại là đã gửi ảnh nào hay file nào".

   Hai gốc, hai chỗ:

   1. Enter SỚM. Dán ảnh (hay một đoạn văn dài, tự thành file .txt) rồi gõ câu hỏi và Enter
      ngay, trong khi /upload còn đang chạy. `sendMessage` lọc `a.path` nên file chưa tải xong
      bị bỏ lặng lẽ: tin bay đi tay không, bong bóng không có ảnh, Javis cũng không nhận được
      file. Nay phải ĐỢI upload xong rồi mới gửi; file hỏng thì nói ra chứ không nuốt.

   2. Mở lại hội thoại từ máy chủ (bấm ở Lịch sử, hồi sức sau khi ngủ nền). Server chỉ lưu
      CHỰ đã gửi, kèm khối "[File đính kèm ...]" mà dashboard chèn vào đầu tin. `openStoredSession`
      cắt khối đó đi cho sạch chữ, rồi dựng bong bóng với đính kèm RỖNG. Nay đọc lại danh sách
      file từ chính khối đó (`docDinhKem`) để ảnh và thẻ file quay về bong bóng.

   Phần 2 chạy CHÍNH `docDinhKem` lấy từ source, vì đây là loại lỗi đọc code không thấy. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const APP = D("app.js");
const CSS = D("style.css");
const HTML = D("index.html");
const VI = JSON.parse(D(path.join("i18n", "vi.json")));
const EN = JSON.parse(D(path.join("i18n", "en.json")));

const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
};

function catHam(ten) {
  const i = APP.indexOf("function " + ten + "(");
  if (i < 0) throw new Error("không thấy hàm " + ten + " trong app.js");
  const j = APP.indexOf("\n}\n", i);
  return APP.slice(i, j + 3);
}
// docDinhKem dùng hai hằng khai ngay trên nó; lấy cả hai dòng đó theo.
const hang = (APP.match(/const _KHOI_NGU_CANH = \[[^\n]*\];/) || [""])[0]
  + "\n" + (APP.match(/const _ANH_EXT = [^\n]*;/) || [""])[0];
const fn = new Function(hang + "\n" + catHam("docDinhKem") + "\nreturn { docDinhKem };")();

// ============================================================
// 1. Mở lại hội thoại: đọc lại đính kèm từ khối ngữ cảnh server đã lưu
// ============================================================
const tinAnh =
  "[File đính kèm để ĐỌC (đường dẫn):\n- /root/.javis/upload/anh-san-pham.png\n"
  + "Mặc định: chỉ đọc file rồi trả lời, KHÔNG tự lưu đi đâu.\n"
  + "CHỈ khi user yêu cầu rõ thì mới: chuyển thành .md lưu vào Sources=\"/x/Sources\", kèm frontmatter source.]\n\n"
  + "ảnh này là gì?";
let a = fn.docDinhKem(tinAnh);
check("đọc ra đúng 1 file từ khối đính kèm", a.length === 1, JSON.stringify(a));
check("tên file = đoạn cuối đường dẫn", a[0] && a[0].name === "anh-san-pham.png", JSON.stringify(a));
check("đuôi .png -> kind image", a[0] && a[0].kind === "image", JSON.stringify(a));
check("url trỏ về /upload/raw?name=<tên> (đúng URL /upload đã trả lúc tải lên)",
  a[0] && a[0].url === "/upload/raw?name=anh-san-pham.png", JSON.stringify(a));
check("dòng 'Mặc định:' và 'CHỈ khi...' KHÔNG bị hiểu thành file", a.length === 1);

const tinNhieu =
  "[File đính kèm để ĐỌC (đường dẫn):\n- C:\\Users\\quy\\.javis\\upload\\van-ban-dan-124933.txt\n"
  + "- /root/.javis/upload/bao cao.pdf\nMặc định: chỉ đọc.]\n\nlên outline chi tiết cho tôi";
a = fn.docDinhKem(tinNhieu);
check("nhiều file: đọc đủ 2", a.length === 2, JSON.stringify(a));
check("đường dẫn Windows (dấu \\) vẫn lấy đúng tên", a[0] && a[0].name === "van-ban-dan-124933.txt", JSON.stringify(a));
check("file .txt là kind file, không phải image", a[0] && a[0].kind === "file", JSON.stringify(a));
check("tên có khoảng trắng được mã hoá trong url",
  a[1] && a[1].url === "/upload/raw?name=bao%20cao.pdf", JSON.stringify(a));

// Khối GHIM đứng trước khối đính kèm (file đang mở trong trình sửa + dán thêm ảnh).
const tinGhim =
  "[FILE ĐANG MỞ trong trình sửa của Javis: /brain/wiki/a.md\nĐọc nó trước khi trả lời.]\n\n"
  + "[File đính kèm (đường dẫn), Sources=\"/x/Sources\", Attachments=\"/x/attachments\":\n- /tmp/up/hinh.jpg]\n\n"
  + "/notes lưu lại";
a = fn.docDinhKem(tinGhim);
check("khối ghim đứng trước không che khối đính kèm phía sau", a.length === 1 && a[0].name === "hinh.jpg", JSON.stringify(a));
check("khối ghim KHÔNG bị đọc thành file", !a.some(x => /a\.md/.test(x.name)), JSON.stringify(a));
check("biến thể khối của lệnh skill (/notes) cũng đọc được", a[0] && a[0].kind === "image");

check("tin thường không có khối -> rỗng", fn.docDinhKem("chào Javis").length === 0);
check("null/undefined -> rỗng, không nổ", fn.docDinhKem(null).length === 0 && fn.docDinhKem(undefined).length === 0);
check("khối không có chỗ kết thúc -> rỗng, không đoán",
  fn.docDinhKem("[File đính kèm để ĐỌC:\n- /x/y.png\nkhông có dấu đóng").length === 0);

// Chỗ gọi thật: openStoredSession phải truyền kết quả này vào bong bóng lẫn convo lưu lại.
const i0 = APP.indexOf("async function openStoredSession(");
const thanOpen = APP.slice(i0, APP.indexOf("\n}\n", i0));
check("openStoredSession đọc đính kèm bằng docDinhKem", /docDinhKem\(m\.content/.test(thanOpen));
check("và truyền vào appendUserMessage thay vì mảng rỗng",
  /appendUserMessage\(_sach, _atts, ts\)/.test(thanOpen) && !/appendUserMessage\(_sach, \[\], ts\)/.test(thanOpen));
check("convo lưu lại cũng mang đính kèm (F5 lần sau còn)",
  /convo\.push\(\{ role: "user", text: _sach, atts: _atts, ts \}\)/.test(thanOpen));

// ============================================================
// 2. Enter sớm: đợi upload xong, không gửi thiếu
// ============================================================
const i1 = APP.indexOf("function sendMessage(");
const thanSend = APP.slice(i1, APP.indexOf("\n}\n", i1));
check("sendMessage nhìn thấy file còn đang tải (a.uploading)", /filter\(a => a\.uploading\)/.test(thanSend));
check("còn đang tải thì ĐỢI (Promise.all trên a.xong) rồi tự gọi lại sendMessage",
  /Promise\.all\(dangTai\.map\(a => a\.xong/.test(thanSend) && /sendMessage\(text\)/.test(thanSend));
check("chỉ giữ MỘT lượt chờ (Enter hai lần không thành hai tin)", /if \(!_choTaiLen\)/.test(thanSend));
check("trong lúc chờ có báo cho người dùng biết vì sao tin chưa đi",
  /showActivity\(escapeHtml\(window\.t\("app\.att_wait_send"\)\)\)/.test(thanSend));
check("file tải HỎNG thì chặn gửi và nói ra, không nuốt",
  /some\(a => !a\.uploading && !a\.path\)/.test(thanSend) && /app\.att_failed_send/.test(thanSend));
// Thứ tự: hai cổng trên phải đứng TRƯỚC dòng lọc a.path - đứng sau là file chưa tải xong đã bị lọc mất.
check("cổng 'đang tải' đứng trước dòng lọc a.path",
  thanSend.indexOf("a.uploading") < thanSend.indexOf("filter(a => a.path)"));

// uploadFile phải hứa "xong" và giữ lời trong MỌI nhánh (thành, lỗi HTTP, lỗi mạng, timeout).
const i2 = APP.indexOf("async function uploadFile(");
const thanUp = APP.slice(i2, APP.indexOf("\n}\n", i2));
check("uploadFile gắn lời hứa att.xong", /att\.xong = new Promise/.test(thanUp));
check("lời hứa được giải quyết trong finally (hỏng cũng xong, không treo Enter mãi)",
  /finally \{[\s\S]*_xong\(\)/.test(thanUp));
check("finally cũng hạ cờ uploading để cổng chờ không kẹt", /finally \{[\s\S]*att\.uploading = false/.test(thanUp));

// ============================================================
// 3. Chuỗi giao diện, CSS, cache-bust
// ============================================================
for (const k of ["app.att_wait_send", "app.att_failed_send"]) {
  check("vi.json có " + k, typeof VI[k] === "string" && VI[k].length > 0);
  check("en.json có " + k, typeof EN[k] === "string" && EN[k].length > 0);
}
check("thanh đính kèm vẽ được dòng nhắc (.attach-note)", /className = "attach-note"/.test(APP) && /\.attach-note\b/.test(CSS));
check("gỡ file hay tải file mới thì xoá dòng nhắc cũ",
  (APP.match(/attachNote = "";/g) || []).length >= 3);
check("index.html bump app.js để trình duyệt không giữ bản cũ",
  /app\.js\?v=(10[3-9]|1[1-9]\d|[2-9]\d\d|\d{4,})/.test(HTML), (HTML.match(/app\.js\?v=\d+/) || [])[0]);

console.log();
if (fails.length) {
  console.log("FAIL " + fails.length + ": " + fails.join("; "));
  process.exit(1);
}
console.log("OK - test_dinh_kem_khong_roi: tất cả pass");
