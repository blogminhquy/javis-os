/* Hai lỗi giao diện trong ảnh chủ repo chụp trên điện thoại (0.12.5).

       node tests/js/test_badge_va_khung_chat_hep.js

   1. Badge ghi "CLI · openai/gpt-oss-120b" trong khi thanh model ngay bên cạnh ghi "Groq".
      refreshEngineBadge chỉ có hai nhánh: openrouter, hoặc CLI. Chọn Groq/Gemini/OpenAI đều
      rơi vào nhánh CLI. Không chỉ xấu: CLAUDE.md bắt Javis phải trả lời ĐÚNG engine đang
      chạy, mà chính giao diện lại đang nói sai.

   2. Hàng tiêu đề trang Trò chuyện vỡ trên màn hẹp: "Trò chuyện với Javis" xuống BỐN dòng,
      chữ "Thu nhỏ" xuống hai dòng, đẩy khung chat tụt hẳn xuống. Đây là hồi quy do chính nút
      Thu nhỏ thêm ở 0.12.4 - hàng vốn đã chật, thêm một nút chữ nữa là vỡ. */
const fs = require("fs");
const path = require("path");

const D = (f) => fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", f), "utf8");
const APP = D("app.js");
const CONSOLE = D("console.js");
const HTML = D("index.html");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- 1. Badge phải biết đủ tám bộ não ----
check("có bảng nhãn engine", APP.indexOf("const ENGINE_LABEL") !== -1);
for (const [id, nhan] of [["anthropic-cli", "Claude Code"], ["openai-oauth", "ChatGPT"],
                          ["openrouter", "OpenRouter"], ["openai", "OpenAI"],
                          ["anthropic-api", "Anthropic"], ["gemini", "Gemini"],
                          ["groq", "Groq"], ["ollama", "Ollama"]]) {
  check(`badge biết '${id}' là "${nhan}"`,
        new RegExp('"?' + id + '"?\\s*:\\s*"' + nhan + '"').test(APP));
}
// Đây là lỗi thật: mọi provider không phải openrouter đều bị dán nhãn CLI.
check("CANARY: không còn nhánh 'không phải openrouter thì là CLI'",
      APP.indexOf('(isOr ? "OpenRouter" : "CLI")') === -1);
check("nhãn lấy từ bảng chứ không đoán", APP.indexOf("ENGINE_LABEL[engine]") !== -1);
check("engine lạ vẫn hiện được gì đó, không rỗng trơ",
      /ENGINE_LABEL\[engine\] \|\| engine \|\| "/.test(APP));

// ---- 2. Và phải đọc model chính theo ĐÚNG thứ tự server dùng ----
// _effective_main trong main.py: model.main nếu đã đặt, không thì suy từ trường engine cũ.
// Đọc thiếu bước model.main là badge đứng ì ở CLI cho mọi provider API.
check("có hàm suy ra model chính", APP.indexOf("function _mainProviderModel") !== -1);
const i0 = APP.indexOf("function _mainProviderModel");
const MAIN_FN = APP.slice(i0, APP.indexOf("\n}", i0));
check("CANARY: ưu tiên model.main như server", MAIN_FN.indexOf("m.main") !== -1
      && MAIN_FN.indexOf("main.provider") !== -1);
check("vẫn lùi về trường engine cũ cho cấu hình chưa có main",
      MAIN_FN.indexOf('m.engine === "openrouter"') !== -1);
check("refreshEngineBadge dùng hàm đó, không tự đoán lại",
      /refreshEngineBadge[\s\S]{0,320}_mainProviderModel/.test(APP));

// Panel Mức dùng cũng phải biết Groq/Gemini, nếu không nó hiện trần id provider.
check("bảng nhãn panel Mức dùng có Groq và Gemini",
      /_PROV_LABEL = \{[^}]*groq: "Groq"/.test(APP) && /_PROV_LABEL = \{[^}]*gemini: "Gemini"/.test(APP));

// ---- 3. Hàng tiêu đề trang Trò chuyện phải gọn một dòng trên màn hẹp ----
const iMq = CONSOLE.indexOf("@media (max-width:860px)");
check("tìm được media query của trang Trò chuyện", iMq !== -1);
const MQ = CONSOLE.slice(iMq, iMq + 900);
check("CANARY: màn hẹp thì nút Thu nhỏ chỉ còn icon", /\.cp-min span\{\s*display:none/.test(MQ));
check("CANARY: tiêu đề cấm xuống dòng", /\.cp-title\{[^}]*white-space:nowrap/.test(MQ));
check("tiêu đề dài thì cắt bằng dấu ba chấm", /\.cp-title\{[^}]*text-overflow:ellipsis/.test(MQ));
// Trong flexbox, thiếu min-width:0 thì ellipsis không bao giờ ăn - phần tử cứ nở ra.
check("tiêu đề có min-width:0 (thiếu là ellipsis vô hiệu)",
      /\.cp-title\{[^}]*min-width:0/.test(MQ));
check("nhãn engine cũng tự cắt thay vì đẩy hàng",
      /\.cp-engine\{[^}]*text-overflow:ellipsis/.test(MQ) && /\.cp-engine\{[^}]*min-width:0/.test(MQ));

// Ẩn được chữ là nhờ nó nằm trong <span>. Để chữ trần thì không cách nào ẩn mà giữ icon.
check("CANARY: chữ 'Thu nhỏ' nằm trong <span> để ẩn được",
      CONSOLE.indexOf("<span>Thu nhỏ</span>") !== -1);
// Ẩn chữ thì trình đọc màn hình mất nghĩa của nút, nên phải có nhãn thay thế.
check("nút vẫn có nhãn cho trình đọc màn hình khi ẩn chữ",
      /id="cpMinBtn"[\s\S]{0,160}aria-label="Thu nhỏ/.test(CONSOLE));

// ---- 4. Trình duyệt phải nạp lại file đã sửa ----
const v = (f) => {
  const m = HTML.match(new RegExp(f.replace(".", "\\.") + "\\?v=(\\d+)"));
  return m ? Number(m[1]) : -1;
};
check("app.js được bump phiên bản", v("app.js") >= 76);
check("console.js được bump phiên bản", v("console.js") >= 91);

if (fails.length) {
  console.log("\nFAIL - test_badge_va_khung_chat_hep: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_badge_va_khung_chat_hep: tất cả pass");
