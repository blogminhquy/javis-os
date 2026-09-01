/* Badge engine+model ở đầu khung hội thoại đã BỎ - và bỏ cả dây chuyền nuôi nó.

       node tests/js/test_bo_badge_engine.js

   Chủ repo yêu cầu 01/09: "ở trên cùng có dòng ký hiệu model này không cần thiết vì dưới
   khung chat có hiển thị model rồi, nên xóa đi để có phần cho tính năng mới anh sắp update".

   Bỏ một badge thì dễ, nhưng nếu chỉ gỡ cái thẻ HTML thì để lại một dây chuyền chạy không
   tải: `refreshEngineBadge()` vẫn gọi `/settings` mỗi lần đổi model để ghi vào một node không
   còn tồn tại, `MutationObserver` vẫn rình một node null, và trang Trò chuyện vẫn giữ ô phản
   chiếu rỗng. File này khoá việc dọn HẾT dây chuyền đó. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const HTML = D("index.html");
const APP = D("app.js");
const CONSOLE = D("console.js");
const PICKER = D("model-picker.js");
const VI = JSON.parse(D(path.join("i18n", "vi.json")));
const EN = JSON.parse(D(path.join("i18n", "en.json")));

const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
};

// ---- 1. Thẻ và kiểu dáng đã đi ----
check("index.html không còn #engineBadge", !/engineBadge/.test(HTML));
check("style.css không còn .engine-badge", !/\.engine-badge/.test(D("style.css")));
check("console.css không còn luật riêng cho badge", !/engine-badge/.test(D("console.css")));

// ---- 2. Dây chuyền cập nhật đã đi hết, không sót một mắt nào ----
["setEngineBadge", "refreshEngineBadge", "ENGINE_LABEL", "_mainProviderModel"].forEach((n) =>
  check("app.js không còn " + n, !new RegExp("\\b" + n + "\\b").test(APP)));
check("không còn ai gọi refreshEngineBadge qua window",
  !/refreshEngineBadge/.test(CONSOLE) && !/refreshEngineBadge/.test(PICKER));

// ---- 3. Ô phản chiếu ở trang Trò chuyện + observer đã đi ----
check("console.js không còn #cpEngine", !/cpEngine/.test(CONSOLE));
check("và không còn CSS .cp-engine", !/\.cp-engine\b/.test(CONSOLE));
// MutationObserver rình một node đã bị xoá là rò rỉ im lặng: nó không nổ, chỉ không bao giờ
// bắn, và người đọc code sau này tưởng badge vẫn đang được đồng bộ.
check("không còn MutationObserver rình badge", !/_chatEngObs/.test(CONSOLE));
// Tiêu đề trang trước đây phải co lại nhường chỗ cho badge - badge đi rồi thì trả bề ngang.
check("tiêu đề trang Trò chuyện được trả lại bề ngang trên màn hẹp",
  /\.cp-title\{[^}]*flex:1 1 auto/.test(CONSOLE),
  (CONSOLE.match(/\.cp-title\{[^}]*\}/) || [])[0]);

// ---- 4. Từ điển không giữ khoá mồ côi ----
check("vi.json không còn khoá chat.engine_badge", VI["chat.engine_badge"] === undefined);
check("en.json không còn khoá chat.engine_badge", EN["chat.engine_badge"] === undefined);

// ---- 5. Chỗ hiển thị model THẬT SỰ còn lại vẫn nguyên ----
// Lý do bỏ badge là "dưới khung chat đã có model rồi" - nên thanh model bắt buộc phải còn,
// và trang Trò chuyện phải vẫn mượn nó. Bỏ badge mà lỡ tay bỏ luôn chỗ kia là mất sạch.
check("thanh model vẫn còn trong index.html", /id="modelBar"/.test(HTML));
check("và trang Trò chuyện vẫn mượn thanh model",
  /CHAT_NODE_IDS = \[[^\]]*"modelBar"/.test(CONSOLE),
  (CONSOLE.match(/CHAT_NODE_IDS = \[[^\]]*\]/) || [])[0]);

check("index.html bump app.js để trình duyệt không giữ bản cũ",
  /app\.js\?v=(99|\d{3,})/.test(HTML), (HTML.match(/app\.js\?v=\d+/) || [])[0]);
check("và bump console.js", /console\.js\?v=(12[4-9]|1[3-9]\d|[2-9]\d\d)/.test(HTML),
  (HTML.match(/console\.js\?v=\d+/) || [])[0]);

console.log();
if (fails.length) {
  console.log("FAIL " + fails.length + ": " + fails.join("; "));
  process.exit(1);
}
console.log("Tất cả xanh.");
