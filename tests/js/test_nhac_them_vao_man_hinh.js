/* Nhắc thêm Javis vào Màn hình chính trên điện thoại - MỖI NGÀY MỘT LẦN.

       node tests/js/test_nhac_them_vao_man_hinh.js

   Chủ repo yêu cầu 27/08/2026: "vào bằng điện thoại mà chưa thêm thì cứ 1 ngày lại nhắc
   lại popup đó 1 lần".

   Vì sao chuyện này đáng làm chứ không phải quảng cáo cài app: iOS CHỈ cho nhận thông báo
   đẩy khi trang đã được "Thêm vào MH chính" (iOS 16.4+). Ai dùng Javis bằng Safari thường
   sẽ không bao giờ nhận được kết quả việc nền, mà cũng không có gì nói cho họ biết vì sao.
   Nút "Mở như app" trên thanh trạng thái lại chỉ hiện ở trình duyệt có beforeinstallprompt
   (Chrome/Edge) - tức là đúng iOS, nơi cần nhất, là nơi không có nút nào.

   Mấy chỗ dễ làm sai mà file này khoá lại:

   1. Nhịp MỘT NGÀY, và mốc phải ghi NGAY LÚC HIỆN chứ không đợi người dùng bấm - đóng bằng
      cách tải lại trang cũng phải tính là đã nhắc, không thì mỗi lần F5 lại bung một lần.
   2. Phải có lối ra vĩnh viễn. Nhắc mãi một người đã quyết định không cài thì họ học cách
      bấm tắt không đọc, và lần có việc thật cũng chịu chung số phận.
   3. iOS không có nút cài nào để bấm. Vẽ nút "Cài" trên Safari là hứa một thứ không tồn tại
      - bên đó phải chỉ đường Chia sẻ → Thêm vào MH chính.
   4. Chỉ được có MỘT chỗ bắt beforeinstallprompt. Trình duyệt bắn nó một lần mỗi phiên và
      chỉ dùng lại được một lần; hai nơi cùng bắt là một nơi mất.

   Năm ca đã dựng thật bằng Chromium giả lập iPhone/Android lúc làm (lần đầu hiện sau đúng
   12 giây, nhắc 2h trước thì im, 25h trước thì hiện lại, đã tắt thì không bao giờ, và bấm
   "Cài Javis" gọi đúng prompt() rồi thôi nhắc hẳn).
*/
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const nudge = read("dashboard/install-nudge.js");
const app = read("dashboard/app.js");
const html = read("dashboard/index.html");
const css = read("dashboard/style.css");

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- 1. Nhịp một ngày ----
check("mốc một ngày tính bằng 24 giờ thật",
  /MOT_NGAY\s*=\s*24 \* 60 \* 60 \* 1000/.test(nudge));
check("nhớ lần nhắc gần nhất trong localStorage", nudge.indexOf("javis.install.nhac_luc") !== -1);
check("chỉ hiện lại khi đã qua đủ một ngày",
  /Date\.now\(\) - luc\) >= MOT_NGAY/.test(nudge));
check("CANARY: ghi mốc NGAY LÚC HIỆN, không đợi người dùng bấm nút nào",
  /ghi\(KEY_LUC, String\(Date\.now\(\)\)\);/.test(nudge)
  && nudge.indexOf("ghi(KEY_LUC") < nudge.indexOf('querySelector("#inudSau")'));

// ---- 2. Lối ra vĩnh viễn ----
check("có nút 'Đừng nhắc nữa'", nudge.indexOf("Đừng nhắc nữa") !== -1);
check("tắt hẳn thì không bao giờ hiện lại",
  /doc\(KEY_TAT\) === "1"\) return false/.test(nudge));
check("cài xong rồi thì thôi nhắc, kể cả khi sau này mở lại bằng tab thường",
  /addEventListener\("appinstalled"[\s\S]{0,80}ghi\(KEY_TAT, "1"\)/.test(nudge));

// ---- 3. Chỉ nhắc đúng người: điện thoại, và CHƯA cài ----
check("đã chạy dạng app thì không nhắc",
  /display-mode: standalone/.test(nudge) && /navigator\.standalone/.test(nudge));
check("chỉ nhắc trên điện thoại (màn hẹp hoặc cảm ứng)",
  /max-width: 860px/.test(nudge) && /pointer: coarse/.test(nudge));
check("CANARY: ba điều kiện đi cùng nhau trước khi vẽ",
  /if \(!laDienThoai\(\) \|\| daLaApp\(\) \|\| !denHen\(\)\) return;/.test(nudge));
check("không bung ngay lúc mở trang (chờ một nhịp)",
  /CHO_TRUOC_KHI_HIEN\s*=\s*\d{4,}/.test(nudge) && /setTimeout\(thu, CHO_TRUOC_KHI_HIEN\)/.test(nudge));

// ---- 4. Hướng dẫn ĐÚNG cho từng trình duyệt ----
check("iOS: chỉ đường Chia sẻ → Thêm vào MH chính",
  nudge.indexOf("Chia sẻ") !== -1 && nudge.indexOf("Thêm vào MH chính") !== -1);
check("CANARY: iOS KHÔNG được vẽ nút Cài (Safari không có hộp cài nào để mở)",
  /coNutCai && !ios \? .*inudCai/.test(nudge));
check("CANARY: iPadOS khai mình là Mac - phải soi maxTouchPoints mới nhận ra",
  /MacIntel.*maxTouchPoints/.test(nudge));
check("trình duyệt không có hộp cài thì chỉ đường qua menu, không hứa nút",
  nudge.indexOf("Thêm vào màn hình chính") !== -1);

// ---- 5. Dùng CHUNG một event beforeinstallprompt với nút trên thanh trạng thái ----
check("app.js mở JavisInstall cho nơi khác dùng chung", /window\.JavisInstall = \{/.test(app));
// Soi ĐÚNG lời đăng ký listener, không soi chữ: file có nhắc tên event trong chú thích
// giải thích vì sao iOS không có nút cài, và đó không phải cái đáng cấm.
check("CANARY: install-nudge KHÔNG tự bắt beforeinstallprompt (bắt hai nơi là mất một nơi)",
  !/addEventListener\(\s*["']beforeinstallprompt["']/.test(nudge));
check("và app.js vẫn là nơi DUY NHẤT bắt event đó",
  (app.match(/addEventListener\("beforeinstallprompt"/g) || []).length === 1);
check("popup mượn hộp cài qua JavisInstall.moHopCai",
  /window\.JavisInstall\.moHopCai\(\)/.test(nudge));
check("moHopCai trả về CÓ CÀI HAY KHÔNG để còn quyết định thôi nhắc",
  /ket && ket\.outcome === "accepted"/.test(app));

// ---- 6. Nạp + style ----
check("install-nudge.js được nạp trong index.html",
  html.indexOf("/static/install-nudge.js?v=") !== -1);
check("có style cho bảng trượt", css.indexOf(".inud-hop") !== -1 && css.indexOf(".inud-wrap") !== -1);
check("chừa chỗ cho thanh cảm ứng dưới đáy iPhone",
  /safe-area-inset-bottom/.test(css.slice(css.indexOf(".inud-hop"))));
const v = (f) => Number((html.match(new RegExp(f.replace(/[.\-]/g, "\\$&") + "\\?v=(\\d+)")) || [])[1] || 0);
check("app.js đã bump ?v= (>= 96)", v("app.js") >= 96, v("app.js"));
check("style.css đã bump ?v= (>= 72)", v("style.css") >= 72, v("style.css"));

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_nhac_them_vao_man_hinh: tat ca pass");
