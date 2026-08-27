/* Phóng to khung chat = SANG TRANG "Trò chuyện", không còn lớp nổi.

       node tests/js/test_chat_zoom_sang_trang.js

   Chủ repo yêu cầu (0.12.4): "nên tắt luôn cái khung zoom của bên Javis và thay vào đó khi
   zoom to thì sang trang trò chuyện, bên trang trò chuyện có nút thu nhỏ lại về màn Javis".

   Vì sao đúng: lớp nổi .chat-stage và trang Trò chuyện MƯỢN CHUNG đúng bốn node của HUD
   (#chatArea, #attachBar, #modelBar, #hudVoice). Hai chỗ giành một bộ node nên phải rải các
   nhát "đang mở thì thu lại" khắp navigateTo / openFilesAt / renderChat - và mỗi chỗ quên là
   một lỗi node bị nuốt (đã dính ở 0.12.1). Bỏ lớp nổi là bỏ luôn cả họ lỗi đó.

   Test này khoá hai chiều: lớp nổi phải BIẾN MẤT, và đường đi mới phải CÓ THẬT ở cả hai đầu
   (bấm phóng to thì sang trang; ở trang có nút về). Thiếu đầu nào cũng là kẹt người dùng. */
const fs = require("fs");
const path = require("path");

const D = (f) => fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", f), "utf8");
const ZOOM = D("chat-zoom.js");
const CONSOLE = D("console.js");
const CSS = D("style.css");
const APP = D("app.js");
const SESS = D("sessions-ui.js");
const HTML = D("index.html");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// Bỏ comment trước khi soi: các file này có nhắc tên lớp nổi cũ trong phần giải thích lý do
// bỏ nó - quét cả comment là bắt nhầm chính lời giải thích đó.
const khongComment = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
const ZOOM_CODE = khongComment(ZOOM);
const CONSOLE_CODE = khongComment(CONSOLE);
const CSS_CODE = CSS.replace(/\/\*[\s\S]*?\*\//g, "");

// ---- 1. Lớp nổi phải biến mất khỏi CODE ----
check("CANARY: không còn dựng lớp nổi .chat-stage", ZOOM_CODE.indexOf("chat-stage") === -1);
check("không còn gắn body.chat-zoomed", ZOOM_CODE.indexOf("chat-zoomed") === -1);
check("không còn bê node của HUD sang chỗ khác",
      ZOOM_CODE.indexOf("getElementById(\"chatArea\")") === -1
      && ZOOM_CODE.indexOf("appendChild") === -1);
check("không còn tự đo toạ độ khung (việc đó chỉ lớp nổi mới cần)",
      ZOOM_CODE.indexOf("getBoundingClientRect") === -1
      && ZOOM_CODE.indexOf("ResizeObserver") === -1);

// ---- 2. Và biến mất khỏi CSS ----
// Để lại rule chết thì lần sau đọc CSS sẽ tưởng lớp nổi còn sống.
check("CANARY: CSS hết rule .chat-stage", !/\.chat-stage[\s{.,:]/.test(CSS_CODE));
check("CSS hết rule body.chat-zoomed", CSS_CODE.indexOf("chat-zoomed") === -1);
check("CSS hết rule .chat-side (cột trái của lớp nổi)", !/\.chat-side[\s{.,:]/.test(CSS_CODE));
// Nhưng CSS của DANH SÁCH hội thoại phải còn - trang Trò chuyện dùng chính nó.
check("giữ lại CSS danh sách hội thoại (.cside-item)", /\.cside-item \{/.test(CSS_CODE));
check("giữ lại CSS ô tìm kiếm (.cside-search)", /\.cside-search \{/.test(CSS_CODE));
check("giữ lại CSS nút Lịch sử (#jv-sess-btn)", /#jv-sess-btn \{/.test(CSS_CODE));

// ---- 3. Chiều ĐI: bấm phóng to → sang trang Trò chuyện ----
check("còn bắt nút phóng to", ZOOM.indexOf('getElementById("chatZoomBtn")') !== -1);
check("CANARY: phóng to là chuyển sang trang chat", /goTo\(["']chat["']\)/.test(ZOOM_CODE));
check("chuyển trang qua đúng store điều hướng của console.js",
      /store\(["']nav["']\)/.test(ZOOM_CODE) && /\.go\(id\)/.test(ZOOM_CODE));
check("không nhảy trang khi đã ở sẵn trang đó (tránh nháy)",
      /active === id/.test(ZOOM_CODE));

// ---- 4. Chiều VỀ: trang Trò chuyện phải có nút thu nhỏ ----
// Thiếu nút này là người dùng vào được mà không ra được bằng đúng chỗ vừa bấm.
check("CANARY: trang Trò chuyện có nút thu nhỏ", CONSOLE.indexOf('id="cpMinBtn"') !== -1);
check("nút thu nhỏ đưa về màn Javis",
      /#cpMinBtn["']\)\.onclick = \(\) => navigateTo\(["']home["']\)/.test(CONSOLE_CODE));
check("nút thu nhỏ có chữ cho biết nó làm gì", /Thu nhỏ/.test(CONSOLE));

// ---- 5. Các API cũ vẫn gọi được, và trở thành vô hại ----
// console.js/sessions-ui.js còn gọi JavisChatStage. Bỏ hẳn object là vỡ trang.
check("còn xuất window.JavisChatStage", ZOOM.indexOf("window.JavisChatStage") !== -1);
check("CANARY: isOpen() luôn false (các nhát 'thu lại' còn sót thành vô hại)",
      /isOpen: function \(\) \{ return false; \}/.test(ZOOM_CODE));
check("nút Lịch sử vẫn có đường vào", ZOOM.indexOf("showSide") !== -1
      && SESS.indexOf("JavisChatStage.showSide()") !== -1);

// ---- 6. Không còn chỗ nào chờ lớp nổi ----
check("CANARY: navigateTo không còn nhát thu lớp nổi",
      CONSOLE_CODE.indexOf("JavisChatStage") === -1);
check("sessions-ui đóng drawer bằng #chatPage chứ không phải .chat-stage",
      SESS.indexOf('getElementById("chatPage")') !== -1
      && khongComment(SESS).indexOf(".chat-stage") === -1);
// Mốc màn hẹp phải KHỚP @media của trang Trò chuyện, nếu không có dải cỡ màn mà drawer mở
// ra rồi chọn xong không tự đóng.
check("mốc màn hẹp khớp trang Trò chuyện (860px)",
      /innerWidth >= 860/.test(SESS) && CONSOLE.indexOf("@media (max-width:860px)") !== -1);

// ---- 7. Ô nhập cao hơn: mốc phải chuyển sang trang chat ----
// Trước đây nó bám .chat-zoomed. Bỏ lớp nổi mà quên đổi mốc là mất luôn tính năng gõ dài.
// 0.47.3: trần trang chat đổi từ 220px cứng sang 40% màn hình (nở theo chữ kiểu claude.ai)
// - canary giữ đúng Ý ĐỊNH gốc: mốc phân biệt là body.on-chat, không phải .chat-zoomed.
check("CANARY: ô nhập trang chat cao hơn, mốc bám body.on-chat (không phải .chat-zoomed)",
      /classList\.contains\("on-chat"\)\s*\?\s*Math\.round\(window\.innerHeight \* 0\.4\)/.test(APP)
      && APP.indexOf('classList.contains("chat-zoomed")') === -1);

// ---- 8. Trình duyệt phải nạp lại file tĩnh đã sửa ----
const v = (f) => {
  const m = HTML.match(new RegExp(f.replace(".", "\\.") + "\\?v=(\\d+)"));
  return m ? Number(m[1]) : -1;
};
check("chat-zoom.js được bump phiên bản", v("chat-zoom.js") >= 6);
check("sessions-ui.js được bump phiên bản", v("sessions-ui.js") >= 7);
check("style.css được bump phiên bản", v("style.css") >= 53);
check("nút phóng to đổi lời chú thích cho đúng việc nó làm",
      /id="chatZoomBtn"[^>]*title="[^"]*Trò chuyện/.test(HTML));

if (fails.length) {
  console.log("\nFAIL - test_chat_zoom_sang_trang: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_chat_zoom_sang_trang: tất cả pass");
