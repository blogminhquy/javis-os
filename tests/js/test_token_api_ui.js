/* Trang Cài đặt > Token API: chỗ DUY NHẤT tạo được credential cho Javis CLI.

       node tests/js/test_token_api_ui.js

   Token là cửa mới vào một máy chủ đang phơi ra Internet, và giao diện này là nơi người dùng
   gặp nó lần đầu. Ba thứ dưới đây hỏng thì hỏng theo kiểu im lặng, nên phải canh:

   1. **Bản thô chỉ tồn tại đúng một lần.** Máy chủ băm token khi lưu, `/auth/tokens` không
      bao giờ trả lại bản thô. Nếu UI đi lấy `t.token` từ danh sách thì nó sẽ hiện "undefined"
      cho mọi token cũ - và người dùng kết luận sai rằng token hỏng chứ không phải rằng nó
      vốn không xem lại được. Bản thô chỉ được đọc từ phản hồi của lệnh TẠO.
   2. **Phải nói thẳng là không xem lại được**, ngay lúc token hiện ra. Nói sau là muộn.
   3. **Thu hồi phải hỏi lại.** Bấm nhầm là một máy đang chạy mất kết nối ngay lập tức, và
      không có đường hoàn tác - token cũ đã băm, không dựng lại được. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const CON = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Có mặt trong trang Tài khoản
// ============================================================
check("trang Cài đặt có mục Token API", /<h3>Token API \(cho CLI\)<\/h3>/.test(CON));
check("có ô đặt tên token", /id="tkName"/.test(CON));
check("có chọn phạm vi", /id="tkScope"/.test(CON));
check("hai phạm vi đúng như máy chủ nhận", /value="chat"/.test(CON) && /value="full"/.test(CON));
check("có nút tạo", /id="tkCreate"/.test(CON));

// Gọi đúng ba endpoint của máy chủ, không tự nghĩ ra đường mới.
check("tạo gọi POST /auth/tokens", /fetch\("\/auth\/tokens", \{ method: "POST", body: fd \}\)/.test(CON));
check("liệt kê gọi GET /auth/tokens", /fetch\("\/auth\/tokens"\)/.test(CON));
check("thu hồi gọi đúng đường", /fetch\("\/auth\/tokens\/revoke", \{ method: "POST", body: fd \}\)/.test(CON));

// ============================================================
// 2. Bản thô: hiện một lần, và nói rõ là một lần
// ============================================================
const khoiTao = CON.slice(CON.indexOf('document.getElementById("tkCreate").onclick'),
                          CON.indexOf('const wsStatus = document.getElementById("acWsStatus")'));
check("bóc được khối tạo token để soi", khoiTao.length > 200);
check("bản thô lấy từ phản hồi lệnh TẠO", /esc\(r\.token \|\| ""\)/.test(khoiTao));
check("CANARY: nói thẳng là đóng trang thì không xem lại được",
  /không xem lại được/.test(khoiTao));
check("có nút copy vì token dài, gõ tay là chép sai", /id="tkCopy"/.test(khoiTao));
check("chỉ đường luôn cho người dùng dán vào máy kia", /javis login /.test(khoiTao));

// Danh sách token KHÔNG có bản thô - máy chủ chỉ trả tên, tiền tố, phạm vi, mốc dùng. UI mà
// đọc t.token ở đây là hiện "undefined" cho mọi token cũ và người dùng tưởng token hỏng.
const khoiList = CON.slice(CON.indexOf("async function renderTokens()"),
                           CON.indexOf("// ---- Lưu 1 section settings ----"));
check("bóc được khối danh sách để soi", khoiList.length > 200);
check("CANARY: danh sách KHÔNG cố đọc bản thô", !/\bt\.token\b/.test(khoiList));
check("danh sách hiện tiền tố để nhận ra token nào", /t\.prefix/.test(khoiList));
// Soi ĐIỀU KIỆN chứ không soi tên trường: `last_used_at` còn xuất hiện ở nhánh in ngày, nên
// chỉ tìm tên trường thì một bản ghim cứng `const dung = false` vẫn lọt - đúng thứ làm mọi
// token trông như chưa ai dùng, tức là che mất một token lạ đang chạy.
check("mốc dùng cuối quyết định bởi chính dữ liệu máy chủ trả",
  /Number\(t\.last_used_at\) > 0/.test(khoiList));
check("token chưa dùng lần nào cũng nói rõ", /chưa dùng lần nào/.test(khoiList));
check("chưa có token nào thì nói rõ, không để trống", /Chưa có token nào/.test(khoiList));

// ============================================================
// 3. Thu hồi là không hoàn tác được
// ============================================================
check("CANARY: thu hồi phải hỏi lại", /confirm\("Thu hồi token này\?/.test(khoiList));
check("lời hỏi nói rõ hậu quả", /mất kết nối ngay/.test(khoiList));
check("thu hồi xong thì vẽ lại danh sách", /renderTokens\(\);\s*\n\s*\};/.test(khoiList));

// ============================================================
// 4. Chưa tạo token thì không có token - nói đúng điều đó
// ============================================================
// Đây là điểm bảo mật quan trọng nhất của cả tính năng: KHÔNG có token mặc định. Người dùng
// phải hiểu ngay rằng cửa này đóng cho tới khi chính họ mở.
check("CANARY: nói rõ chưa tạo thì không đường nào vào",
  /chưa tạo thì không đường nào vào/.test(CON));

// ============================================================
// 5. CSS đi kèm
// ============================================================
check("khối token mới có kiểu riêng để không lướt qua mất", /\.tk-new \{/.test(CSS));
check("bản thô cho bôi đen cả cụm", /user-select: all/.test(CSS));
check("danh sách token có kiểu", /\.tk-row \{/.test(CSS));

// ============================================================
// 6. Tài liệu và CLI phải chỉ ĐÚNG trang
// ============================================================
// Lỗi thật, bắt được ngay ngày phát hành: cả tài liệu lẫn lời nhắc trong `javis login` đều ghi
// "Cài đặt > Token API", trong khi mục đó do renderAccount() vẽ, tức là trang **Tài khoản**.
// Người dùng vào Cài đặt, không thấy gì, và kết luận tính năng chưa có. Không một dòng lỗi nào
// xuất hiện - đây đúng loại sai mà chỉ test mới bắt được, còn người thì đọc mãi vẫn trượt.
check("mục Token API do renderAccount vẽ (tức là trang Tài khoản)",
  CON.indexOf("async function renderAccount(") < CON.indexOf("<h3>Token API (cho CLI)</h3>")
  && CON.indexOf("<h3>Token API (cho CLI)</h3>") < CON.indexOf("async function renderTokens("));

const NOI = [
  ["cli/javis_cli/client.py", "thông báo 401 của CLI"],
  ["cli/javis_cli/commands.py", "lời nhắc lúc javis login"],
  ["docs/24-cli-terminal.md", "tài liệu CLI"],
  ["docs/14-bao-mat-tai-khoan.md", "tài liệu bảo mật"],
  ["docs/17-khac-phuc-su-co.md", "tài liệu sự cố"],
];
for (const [f, ten] of NOI) {
  const t = fs.readFileSync(path.join(ROOT, f), "utf8");
  check(`CANARY: ${ten} không chỉ nhầm sang trang Cài đặt`,
    !/Cài đặt\s*(>|&gt;)\s*Token API/.test(t));
}
// Và phải chỉ ĐÚNG chỗ, chứ không phải chỉ "không sai".
const DOC = fs.readFileSync(path.join(ROOT, "docs", "24-cli-terminal.md"), "utf8");
check("tài liệu CLI chỉ đúng trang Tài khoản", /Tài khoản\s*(>|&gt;)?\s*.{0,40}Token API|\*\*Tài khoản\*\*/.test(DOC));

// ============================================================
// 7. Có đường sang tài liệu, và đường đó phải còn thật
// ============================================================
// Người dùng cầm chuỗi `jvs_...` trong tay mà không biết bước kế tiếp là `pip install javis-cli`
// thì token vừa tạo thành rác. Link chết cũng hỏng im lặng như vậy: đổi tên file tài liệu thì
// trang vẫn vẽ ra bình thường, chỉ có người bấm mới lãnh 404. Nên soi cả hai đầu.
const LINKS = [
  ["docs/24-cli-terminal.md", "tài liệu CLI"],
  ["docs/14-bao-mat-tai-khoan.md", "tài liệu bảo mật"],
];
for (const [f, ten] of LINKS) {
  check(`thẻ Token API có link tới ${ten}`, CON.includes("/blob/main/" + f));
  check(`CANARY: ${ten} còn tồn tại đúng đường đó`, fs.existsSync(path.join(ROOT, f)));
}
check("link mở tab mới, không cuốn người dùng ra khỏi dashboard",
  /24-cli-terminal\.md" target="_blank" rel="noopener"/.test(CON));
check("lúc token vừa hiện thì chỉ luôn cách cài CLI", /pip install javis-cli/.test(khoiTao));
check("khối link có kiểu riêng", /\.tk-docs \{/.test(CSS));

console.log("");
if (fails.length) { console.log("THẤT BẠI " + fails.length + ": " + fails.join(", ")); process.exit(1); }
console.log("OK - test_token_api_ui: tất cả pass");
