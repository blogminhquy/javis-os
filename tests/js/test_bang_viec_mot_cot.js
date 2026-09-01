/* Bảng Việc: một cột, có nút Xoá tất cả, và việc kẹt vì thiếu quyền có lối ra.

       node tests/js/test_bang_viec_mot_cot.js

   Chủ repo yêu cầu 01/09 kèm ảnh: "cho anh thêm nút xóa tất cả ở phần bảng cần xử lý và việc
   gần đây, và giúp anh hiển thị 1 cột thôi không cần chia 2 cột như hiện tại đâu".

   Lưới 2 cột cũ chống lại chính thứ nó bày ra: khu "Cần bạn xử lý" nằm cột phải bị bóp còn
   ~1/3 bề ngang, nên mỗi việc kẹt phải cuộn trong một ô hẹp mới đọc hết lý do - trong khi hai
   khu bên trái ("Đang hoạt động", "Hàng đợi AI") thường trống trơn, đúng như trong ảnh. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const JS = D("console.js");
const VI = JSON.parse(D(path.join("i18n", "vi.json")));
const PY = fs.readFileSync(path.join(ROOT, "server", "tasks.py"), "utf8");

const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
};

// ============================================================
// 1. MỘT cột
// ============================================================
const layout = (JS.match(/\.kn-layout\{[^}]*\}/) || [""])[0];
check("kn-layout không còn là lưới 2 cột", !/grid-template-columns/.test(layout), layout);
check("mà xếp dọc", /flex-direction:\s*column/.test(layout), layout);
// Bỏ luôn cái đè lại ở media query: giữ nó là để lại một dòng nói dối về bố cục.
check("media query hẹp không còn đè lại grid-template-columns cho kn-layout",
  !/\.kn-layout\{grid-template-columns/.test(JS));

const ops = (JS.match(/<div class="kn-layout" id="knOps">[\s\S]*?\n      <\/div>/) || [""])[0];
check("bốn khu nằm THẲNG trong kn-layout, không còn hai cột bọc ngoài",
  (ops.match(/<section class="kn-panel"/g) || []).length === 4
  && !/flex-direction:column;gap:14px">\s*<section/.test(ops), ops.slice(0, 200));
// Một cột thì thứ tự đọc chính là thứ tự ưu tiên. Khu cần ra tay phải đứng trước hai khu chỉ
// để liếc trạng thái, không thì 20 ngoại lệ nằm dưới hai khung rỗng.
check("khu Cần bạn xử lý đứng ĐẦU", ops.indexOf("knAttention") < ops.indexOf("knActive"),
  ops.indexOf("knAttention") + " vs " + ops.indexOf("knActive"));
check("và Lịch sử đứng cuối", ops.indexOf("knHistory") > ops.indexOf("knQueue"));

// ============================================================
// 2. Nút Xoá tất cả: đúng hai khu, và hỏi lại bằng hai câu khác nhau
// ============================================================
check("có nút xoá tất cả ở khu Cần bạn xử lý", /id="knWipeAttention" data-panel="attention"/.test(ops));
check("có nút xoá tất cả ở khu Lịch sử", /id="knWipeHistory" data-panel="history"/.test(ops));
check("KHÔNG bày nút đó ở khu Đang hoạt động / Hàng đợi",
  (ops.match(/kn-wipe/g) || []).length === 2, (ops.match(/kn-wipe/g) || []).length);
check("gọi endpoint dọn theo khu", /post\("\/kanban\/panel\/clear", \{ panel: khu \}\)/.test(JS));
check("hỏi lại trước khi dọn", /confirm\(t\(khu === "attention"/.test(JS));
// Hai khu hai hậu quả khác nhau (dọn khỏi bảng vs xoá hẳn) nên KHÔNG được dùng chung một câu.
check("hai câu hỏi lại là hai câu khác nhau",
  VI["kanban.confirm_wipe_attention"] !== VI["kanban.confirm_wipe_history"]);
check("câu của khu Lịch sử nói rõ là không hoàn tác được",
  /không hoàn tác/i.test(VI["kanban.confirm_wipe_history"] || ""));
check("khu rỗng thì nút xám đi", /knWipeAttention"\)\.disabled = !attention\.length/.test(JS));

// ============================================================
// 3. Việc kẹt vì thiếu quyền: có nút cấp quyền, và KHÔNG còn nút Thử lại
// ============================================================
check("nhận diện việc kẹt vì thiếu quyền bằng block_kind",
  /t\.status === "blocked" && t\.block_kind === "capability"/.test(JS));
check("hiện nút cho phép chạy thật", /data-act="grant"/.test(JS));
// Đây là nửa quan trọng nhất: nút Thử lại ở ca này chạy lại đúng nhánh chặn rồi chặn lại y
// hệt, kèm một tiếng chuông nữa - một vòng không có lối ra.
check("và BỎ nút Thử lại ở đúng ca đó", /if \(!canQuyen && \(t\.status === "blocked"/.test(JS));
check("gọi endpoint cấp quyền", /post\("\/kanban\/task\/grant", \{ id \}\)/.test(JS));
check("hỏi lại trước khi cấp quyền", /act === "grant" && !confirm\(t\("kanban\.confirm_grant"\)\)/.test(JS));
check("câu hỏi lại nói thẳng hậu quả không hoàn tác được",
  /KHÔNG hoàn tác/.test(VI["kanban.confirm_grant"] || ""), VI["kanban.confirm_grant"]);

// ============================================================
// 4. Khớp với máy chủ
// ============================================================
check("server có endpoint dọn theo khu", /@router\.post\("\/kanban\/panel\/clear"\)/.test(PY));
check("server có endpoint cấp quyền", /@router\.post\("\/kanban\/task\/grant"\)/.test(PY));
check("server chỉ cấp quyền cho việc bị chặn vì thiếu quyền",
  /block_kind"\) or ""\) != "capability"/.test(PY));
["kanban.wipe", "kanban.act_grant", "kanban.confirm_grant",
 "kanban.confirm_wipe_attention", "kanban.confirm_wipe_history"].forEach((k) =>
  check("vi.json có khoá " + k, typeof VI[k] === "string" && VI[k].length > 0));
// Sàn 122 vì bản trước đã ở 121: đợt này ĐỔI console.js nên nó phải nhích lên, không thì
// trình duyệt giữ bản cũ qua cập nhật và người dùng vẫn thấy bảng Việc hai cột (đúng lỗi từ
// điển cũ bị cache ở 0.52.2). Sàn phải nhích theo mỗi lần đụng file này - đó là chủ ý.
const _v = Number(((D("index.html").match(/console\.js\?v=(\d+)/) || [])[1]) || 0);
check("index.html bump console.js để trình duyệt không giữ bản cũ", _v >= 122, _v);

console.log();
if (fails.length) {
  console.log("FAIL " + fails.length + ": " + fails.join("; "));
  process.exit(1);
}
console.log("Tất cả xanh.");
