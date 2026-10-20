/* Enter trong trình sửa .md thì tự nối thêm một dòng task/danh sách.

       node tests/js/test_enter_tiep_task.js

   Chủ repo yêu cầu (2026-09-11): đang gõ task mà bấm Enter thì phải có ngay một task mới,
   khỏi phải với tay bấm nút checkbox từng dòng.

   Bốn chỗ hỏng ÂM THẦM nên phải canh:

     1. Thứ tự khuôn. "- [ ] x" cũng khớp khuôn bullet "- x", nên xét bullet trước là Enter
        ra gạch đầu dòng trơn và checkbox rụng mất.
     2. Dòng trống. Không có đường ra khỏi danh sách thì người dùng bị kẹt: Enter đẻ mãi
        task rỗng. Enter trên task rỗng phải GỠ dấu mục.
     3. Ô đã tick. Nối từ "- [x] xong" phải ra "- [ ] " chưa tick, không thì việc mới sinh ra
        đã tự đánh dấu hoàn thành.
     4. Bộ gõ tiếng Việt. Enter lúc đang chốt chữ (isComposing) không phải là xuống dòng,
        cướp nó là gõ tiếng Việt trong editor bị mất chữ. */
const fs = require("fs");
const path = require("path");
const EC = require("../../dashboard/editor-cmds.js");
const SRC = fs.readFileSync(path.join(__dirname, "../../dashboard/editor-cmds.js"), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Đọc dấu mục của một dòng
// ============================================================
const D = EC.dongDanhSach;
check("đọc được task chưa tick", JSON.stringify(D("- [ ] mua sữa")) ===
      JSON.stringify({ loai: "task", indent: "", noiDung: "mua sữa", dau: "- [ ] ", tiep: "- [ ] " }));
check("task đã tick vẫn là task", D("- [x] xong").loai === "task");
check("CANARY: nối từ task đã tick ra ô CHƯA tick", D("- [x] xong").tiep === "- [ ] ");
check("dấu * và + cũng là task", D("* [ ] a").loai === "task" && D("+ [ ] a").loai === "task");
check("CANARY: task xét trước bullet, không bị đọc thành gạch đầu dòng", D("- [ ] a").loai !== "ul");

check("gạch đầu dòng", D("- việc").loai === "ul" && D("- việc").tiep === "- ");
check("danh sách số tăng một", D("3. bước ba").tiep === "4. ");
check("danh sách số kiểu 2) giữ đúng dấu", D("2) hai").tiep === "3) ");
check("số nhiều chữ số vẫn tăng đúng", D("9. chín").tiep === "10. ");
check("giữ nguyên thụt lề của mục con", D("    - con").tiep === "    - ");

check("dòng chữ thường không phải danh sách", D("chỉ là chữ") === null);
check("dòng trống không phải danh sách", D("") === null);
check("tiêu đề không phải danh sách", D("## Tiêu đề") === null);
check("CANARY: đường kẻ --- không bị đọc thành gạch đầu dòng", D("---") === null);
check("nbsp của bản render vẫn khớp khuôn", D("- [ ] việc").loai === "task");

// ============================================================
// 2. Enter ở ô nguồn thô: mô tả thay đổi
// ============================================================
const E = EC.enterDanhSach;
// Áp mô tả thay đổi vào chuỗi để nhìn thấy kết quả thật, "|" là chỗ caret sau khi xong.
function ap(value, pos) {
  const ed = E(value, pos);
  if (!ed) return null;
  const v = value.slice(0, ed.s) + ed.text + value.slice(ed.e);
  const p = ed.s + ed.text.length;
  return v.slice(0, p) + "|" + v.slice(p);
}

check("Enter cuối dòng task -> task mới", ap("- [ ] mua sữa", 13) === "- [ ] mua sữa\n- [ ] |");
check("Enter giữa dòng task -> chữ sau chạy xuống task mới",
      ap("- [ ] mua sữa", 9) === "- [ ] mua\n- [ ] | sữa");
check("Enter cuối dòng bullet -> bullet mới", ap("- việc", 6) === "- việc\n- |");
check("Enter cuối dòng số -> số kế tiếp", ap("1. một", 6) === "1. một\n2. |");

// Dòng chỉ có dấu mục: Enter GỠ dấu mục, người dùng ra khỏi danh sách.
check("Enter trên task rỗng -> gỡ dấu mục", ap("- [ ] ", 6) === "|");
check("Enter trên bullet rỗng -> gỡ dấu mục", ap("- ", 2) === "|");
check("gỡ dấu mục giữ nguyên các dòng khác",
      ap("- [ ] a\n- [ ] \n- [ ] b", 14) === "- [ ] a\n|\n- [ ] b");

check("dòng thường thì Enter chạy bình thường", E("chỉ là chữ", 5) === null);
check("văn bản rỗng thì Enter chạy bình thường", E("", 0) === null);
check("CANARY: caret còn trong dấu mục thì không chèn dấu mục lồng nhau", E("- [ ] a", 3) === null);
check("caret vừa qua dấu mục thì nối được", !!E("- [ ] a", 6));
check("vị trí caret vô nghĩa thì trả null", E("- [ ] a", null) === null && E("- [ ] a", 99) === null);

// Đúng dòng đang đứng, không phải dòng đầu file
check("nối đúng dòng đang đứng trong file nhiều dòng",
      ap("# Ghi chú\n\n- [ ] một\n", 20) === "# Ghi chú\n\n- [ ] một\n- [ ] |\n");
check("thụt lề mục con được giữ khi nối",
      ap("- [ ] cha\n    - [ ] con", 23) === "- [ ] cha\n    - [ ] con\n    - [ ] |");

// ============================================================
// 3. Bộ máy nghe phím trong trình duyệt (đọc mã nguồn)
// ============================================================
const iH = SRC.indexOf("Enter noi dong danh sach / task");
check("có chỗ nghe phím Enter trong phần DOM", iH > 0);
const H = SRC.slice(iH);
check("CANARY: Enter lúc bộ gõ tiếng Việt đang chốt chữ thì không cướp",
      /e\.isComposing \|\| e\.keyCode === 229/.test(H));
check("Shift/Ctrl/Alt + Enter vẫn là của trình duyệt",
      /e\.shiftKey \|\| e\.ctrlKey \|\| e\.metaKey \|\| e\.altKey/.test(H));
check("menu \"/\" hoặc menu gợi ý task đang mở thì nhường Enter cho menu",
      /if \(pop \|\| document\.querySelector\("\.ts-pop"\)\)/.test(H));
check("đang chọn một đoạn thì để yên", /selectionStart !== ta\.selectionEnd/.test(H));
check("chạy ở cả hai chế độ: nguồn thô và bản render",
      /ctx\.mode\(\) === "source"/.test(H) && /liTuCaret\(ctx\.wys\)/.test(H));
check("bản render: task rỗng thì thoát khỏi danh sách", /liTrong\(li\)\) \{ if \(thoatDanhSach\(li\)\)/.test(H));
check("bản render: li mới được dập checkbox vào", /napTask/.test(H) && H.includes("insertAdjacentHTML(\"afterbegin\", CB_HTML)"));
check("CANARY: li mới không kéo theo vệt đã-hoàn-thành", /classList\.remove\("task-done"\)/.test(H));
// Enter ở ĐẦU dòng: Chromium đẩy dòng mới lên TRÊN, caret ở lại dòng cũ. Chỉ xét li đang
// chứa caret là dòng trên đó nằm lại làm gạch đầu dòng trơn.
check("Enter ở đầu dòng: dòng mới phía TRÊN cũng thành task",
      /var tren = li\.previousElementSibling/.test(H) && /dapCheckbox\(tren\)/.test(H));
check("sửa textarea ưu tiên execCommand để còn hoàn tác được",
      /document\.execCommand\("insertText", false, ed\.text\)/.test(H));
check("nhánh dự phòng vẫn bắn sự kiện input", /dispatchEvent\(new Event\("input", \{ bubbles: true \}\)\)/.test(H));
// Nút checkbox và Enter dùng CHUNG một hàm tìm li, không chép hai bản trôi khỏi nhau.
check("hàm tìm li dùng chung cho cả nút checkbox và Enter",
      /function liTuCaret\(wys\)/.test(SRC) && !/function liHienTai\(/.test(SRC));
check("KHÔNG dùng ký tự em dash", !SRC.includes("—"));

console.log(fails.length ? "\nFAIL: " + fails.length : "\nTất cả " + "đều xanh");
process.exit(fails.length ? 1 : 0);
