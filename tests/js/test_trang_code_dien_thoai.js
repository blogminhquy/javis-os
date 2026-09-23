/* Trang Code phải DÙNG ĐƯỢC trên điện thoại, và thẻ ChatGPT phải gọn.

       node tests/js/test_trang_code_dien_thoai.js

   Ba việc chủ repo báo 23/09, hai cái đầu đã dựng lại THẬT trong Chromium ở 390px trước khi
   sửa - con số đo được chép lại đây vì nó là thứ phân biệt "đoán" với "biết":

   1. **Nút lịch sử bấm không ra menu.** coding.js tự viết phần bật/tắt cột trái và viết sai:
      nó `toggle("side-thu")` - lớp THU GỌN của máy tính - trong khi màn hẹp (<=860px) chỉ
      hiểu lớp `side-open`. Đo được: sau cú bấm, cột trái vẫn nằm ở x = -315, tức ngoài màn
      hình. Sau khi sửa: x = 0.

      Đây là lần thứ ba cùng một kiểu lỗi trong cùng một trang ("dựng bản thứ hai của thứ đã
      có"), nên bản sửa KHÔNG vá tại chỗ mà gom về một hàm dùng chung
      (`window.JavisNeoCotTrai`) cho cả trang Trò chuyện lẫn trang Code.

   2. **Không thấy chỗ thêm thư mục và các chế độ.** Dải chip nhét vào `#modelBar`, mà màn hẹp
      ẩn hẳn node đó (`.model-bar{display:none}`) rồi dời riêng chip model lên header bằng JS.
      Đo được: parent = modelBar, display = none, chip không nhìn thấy. Sau khi sửa: parent =
      cdChipsHep, nhìn thấy được.

   3. **Thẻ ChatGPT quá nhiều chữ.** "Viết hướng dẫn cụ thể ở github rồi dán link vào thôi là
      đc, còn ở trên trang cần gọn gàng." Nên hướng dẫn đi hẳn sang docs/29-chatgpt-web.md, và
      nút "Đóng trình duyệt" bỏ luôn. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

const CD = D("coding.js");
const CON = D("console.js");
const CSS = D("console.css");
const MAIN = fs.readFileSync(path.join(ROOT, "server", "main.py"), "utf8");

// ---- 1. Cột trái: MỘT bản luật, dùng chung ----
check("console.js phát ra hàm dùng chung cho cột trái",
  /window\.JavisNeoCotTrai\s*=\s*_neoCotTrai/.test(CON) && /function _neoCotTrai\(/.test(CON));
check("hàm đó biết màn hẹp dùng lớp side-open, máy tính dùng side-thu", (() => {
  const i = CON.indexOf("function _neoCotTrai(");
  const than = CON.slice(i, CON.indexOf("window.JavisNeoCotTrai", i));
  return /max-width: 860px/.test(than)
    && /hep\(\)\)\s*\{\s*page\.classList\.toggle\("side-open"\)/.test(than)
    && /toggle\("side-thu", thu\)/.test(than);
})());
check("trang Code gọi hàm dùng chung chứ không tự viết",
  /W\.JavisNeoCotTrai\(/.test(CD));
check("trang Code KHÔNG còn tự toggle side-thu như đường chính", (() => {
  // Bỏ CHÚ THÍCH ra trước khi đếm: chú thích giải thích lỗi cũ có nhắc "side-thu", mà đếm
  // cả nó thì phép thử này bắt nhầm chính lời giải thích của bản sửa.
  const ma = CD.replace(/^\s*\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "");
  const dung = ma.match(/side-thu/g) || [];
  // Còn đúng MỘT chỗ: nhánh dự phòng khi console.js chưa nạp, và nó phải nằm sau dấu `:`
  // của toán tử ba ngôi hỏi `W.JavisNeoCotTrai` - tức chỉ chạy khi hàm chung vắng mặt.
  return dung.length === 1
    && /W\.JavisNeoCotTrai\s*\?[\s\S]{0,260}:\s*function \(\) \{[^}]*side-thu/.test(ma);
})());
check("trang Trò chuyện cũng đi qua hàm đó (không để hai bản trôi lệch)",
  /_neoCotTrai\(page,/.test(CON));
check("có ghi lại con số đo được, để lần sau biết đây là lỗi THẬT",
  /x = -315/.test(CON) || /x = -315/.test(CD));

// ---- 2. Dải chip phải NHÌN THẤY ĐƯỢC trên điện thoại ----
check("khung trang có chỗ đứng riêng cho chip ở màn hẹp",
  /id="cdChipsHep"/.test(CD));
check("chọn chỗ đứng THEO BỀ NGANG, không gắn cứng vào modelBar",
  /function hocChip\(\)/.test(CD) && /max-width: 860px/.test(CD)
  && /return document\.getElementById\("modelBar"\)/.test(CD));
check("đổi bề ngang (xoay máy) thì vẽ lại chip ở đúng bên",
  /_mqChip\.addEventListener\("change"/.test(CD));
check("và gỡ người nghe khi rời trang, không chồng chất",
  /_mqChip\.removeEventListener\("change"/.test(CD));
check("chip đổi chỗ thì gỡ khỏi chỗ cũ trước, không nhân đôi",
  /row\.parentElement !== bar\) row\.remove\(\)/.test(CD));
check("có kiểu dáng cho hàng chip màn hẹp, và nó tự ẩn khi rỗng",
  /\.cd-chips-hep:empty\s*\{\s*display:\s*none/.test(CSS));
// CANARY: lý do gốc phải còn ghi lại, kẻo ai đó thấy `hocChip` thừa rồi gắn cứng lại.
check("CANARY: còn ghi vì sao modelBar không dùng được ở màn hẹp",
  /model-bar\{display:none\}|\.model-bar.*display:\s*none/.test(CD) || /modelBar/.test(CD) && /display:none/.test(CD));

// ---- 3. Thẻ ChatGPT gọn ----
const i = CON.indexOf("async function veThreChatGPTWeb");
const the = CON.slice(i, CON.indexOf("async function renderModelsCloudTab", i));
check("bỏ nút Đóng trình duyệt", (() => {
  // Soi PHẦN VẼ RA, không soi cả file: chú thích của bản sửa có nhắc tên nút cũ để nói vì
  // sao nó biến mất, và đó là thứ nên giữ chứ không phải thứ phải xoá.
  const ma = the.replace(/^\s*\/\/.*$/gm, "");
  return !/Đóng trình duyệt/.test(ma) && !/webreset/.test(CON);
})());
check("bỏ luôn endpoint của nút đó, không để lại đường chết",
  !/web-chat\/reset/.test(MAIN) && !/web-chat\/reset/.test(CON));
check("nhưng KHÔNG mất lối thoát: dán cookie tự đóng rồi mở lại trình duyệt", (() => {
  const WT = fs.readFileSync(path.join(ROOT, "server", "web_transport.py"), "utf8");
  const j = WT.indexOf("def _nap_cookie_that");
  return /self\._dong_that\(\)/.test(WT.slice(j, j + 1400));
})());
check("và dọn luôn sổ nghỉ khi dán cookie", /web_state\.dat_lai\(\)/.test(
  MAIN.slice(MAIN.indexOf('@app.post("/web-chat/cookie")'), MAIN.indexOf('@app.post("/web-chat/check")'))));
check("thẻ trỏ sang tài liệu trên GitHub", /29-chatgpt-web\.md/.test(CON));
check("khối chữ hướng dẫn dài đã rời khỏi thẻ",
  !/Memory và Custom instructions/.test(the) && !/bật DevTools \(F12\), vào/.test(the));
check("nhưng vẫn còn đủ thứ để BẤM: ô dán + nút đăng nhập",
  /id="webCookie"/.test(the) && /data-webcookie/.test(the));
check("đã đăng nhập rồi thì không bày ô dán nữa", /\$\{dn \? "" : `/.test(the));

// Cổng /web-chat đòi phiên thật là CHỦ Ý (xem _web_chat_chan). Nhưng bản chạy loopback chưa
// đặt mật khẩu không có phiên nào, và trước 0.64.13 thẻ hiện ra với dòng trạng thái RỖNG -
// không nút, không lời giải thích. Đã dựng lại bằng curl trên một bản chạy 127.0.0.1.
check("bị cổng chặn thì NÓI RA, không hiện thẻ rỗng",
  /d\.ok === false && d\.error/.test(the));
check("và chỉ luôn đường đi tiếp", /Đặt mật khẩu quản trị/.test(the));

// ---- 4. Tài liệu phải có thật và nói đủ ----
const DOC = fs.readFileSync(path.join(ROOT, "docs", "29-chatgpt-web.md"), "utf8");
check("tài liệu có tồn tại và không rỗng", DOC.length > 2000);
for (const [ten, chu] of [["cách cài hai thứ cần", "Công cụ tuỳ chọn"],
                          ["tên cookie phải lấy", "__Secure-next-auth.session-token"],
                          ["ba kiểu dán", "ba kiểu dán"],
                          ["cảnh báo Memory/Custom instructions", "Custom instructions"],
                          ["vì sao không bỏ được trình duyệt", "proof-of-work"],
                          ["bảng xử lý khi không chạy", "Khi không chạy"]]) {
  check(`tài liệu nói ${ten}`, DOC.includes(chu));
}
check("tài liệu KHÔNG dùng em dash (luật CLAUDE.md)", !DOC.includes("—") && !DOC.includes("–"));

console.log();
if (fails.length) { console.log(`THẤT BẠI ${fails.length}: ${JSON.stringify(fails)}`); process.exit(1); }
console.log("OK - test_trang_code_dien_thoai: tất cả pass");
