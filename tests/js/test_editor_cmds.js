/* Bảng lệnh trình soạn .md: nút thanh công cụ + phím tắt + menu gõ "/".

       node tests/js/test_editor_cmds.js

   Chủ repo yêu cầu (2026-07-31): thêm phím tắt cho H1/H2/H3, bullet, danh sách số, trích dẫn,
   code, link, checkbox; thêm nút checkbox vào cùng hàng nút; và gõ "/" trong chế độ Sửa thì sổ
   bảng chọn các chức năng đó kèm phím tắt bên cạnh.

   Hành vi DOM đã đo bằng Chromium thật (24 phép thử: vẽ nút, bấm nút ra checkbox, phím tắt ở cả
   hai chế độ, menu "/" lọc và chèn, Esc đóng) cộng vòng round-trip Sửa -> markdown -> vẽ lại có
   Turndown + plugin GFM thật. CI chỉ có node nên test này khoá phần logic thuần, là phần dễ
   trôi nhất khi ai đó thêm lệnh mới. */
const EC = require("../../dashboard/editor-cmds.js");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}
function ev(o) {
  return Object.assign({ ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, key: "", code: "" }, o);
}
function id(c) { return c ? c.id : null; }

// ---- 1. Bảng lệnh đủ mặt ----
const MONG = ["bold", "italic", "h1", "h2", "h3", "ul", "ol", "task", "quote", "code", "link", "hr"];
check("có đủ 12 lệnh, đúng thứ tự hiển thị", EC.CMDS.map(c => c.id).join(",") === MONG.join(","));
check("lệnh checkbox tồn tại", !!EC.CMDS.find(c => c.id === "task"));
// Nút checkbox phải đứng CÙNG HÀNG, ngay sau hai kiểu danh sách (yêu cầu "cùng hàng với các nút kia").
const iOl = EC.CMDS.findIndex(c => c.id === "ol"), iTask = EC.CMDS.findIndex(c => c.id === "task");
check("checkbox xếp ngay sau danh sách số", iTask === iOl + 1);
check("mọi lệnh đều có nhãn tiếng Việt", EC.CMDS.every(c => c.label && c.label.trim()));
check("mọi lệnh đều vẽ được nút (icon hoặc chữ)",
      EC.CMDS.every(c => c.btn && (c.btn.icon || c.btn.text)));
check("mọi lệnh đều chạy được ở CẢ hai chế độ",
      EC.CMDS.every(c => c.run || (c.wys && c.src)));

// ---- 2. Phím tắt: khớp đúng ----
const KHOP = [
  ["Ctrl+B", { ctrlKey: 1, key: "b" }, "bold"],
  ["Cmd+B (Mac)", { metaKey: 1, key: "b" }, "bold"],
  ["Ctrl+I", { ctrlKey: 1, key: "i" }, "italic"],
  ["Ctrl+Alt+1", { ctrlKey: 1, altKey: 1, code: "Digit1" }, "h1"],
  ["Ctrl+Alt+2", { ctrlKey: 1, altKey: 1, code: "Digit2" }, "h2"],
  ["Ctrl+Alt+3", { ctrlKey: 1, altKey: 1, code: "Digit3" }, "h3"],
  ["Ctrl+Shift+8", { ctrlKey: 1, shiftKey: 1, code: "Digit8" }, "ul"],
  ["Ctrl+Shift+7", { ctrlKey: 1, shiftKey: 1, code: "Digit7" }, "ol"],
  ["Ctrl+Shift+9", { ctrlKey: 1, shiftKey: 1, code: "Digit9" }, "task"],
  ["Ctrl+Shift+.", { ctrlKey: 1, shiftKey: 1, code: "Period" }, "quote"],
  ["Ctrl+E", { ctrlKey: 1, key: "e" }, "code"],
  ["Ctrl+K", { ctrlKey: 1, key: "k" }, "link"],
];
KHOP.forEach(([ten, e, mong]) => check("phím tắt " + ten + " -> " + mong, id(EC.matchCmd(ev(e))) === mong));

// Phím SỐ dùng e.code chứ không phải e.key: giữ Alt trên Mac thì e.key thành "¡", còn
// e.code vẫn là "Digit1". Dùng nhầm e.key là phím tắt tiêu đề chết trên Mac.
check("CANARY: Ctrl+Alt+1 vẫn khớp khi e.key bị Alt đổi thành '¡'",
      id(EC.matchCmd(ev({ ctrlKey: 1, altKey: 1, code: "Digit1", key: "¡" }))) === "h1");

// ---- 3. Phím tắt: KHÔNG được cướp phím của trình duyệt / của app ----
const CAM = [
  ["Ctrl+1 (đổi tab trình duyệt)", { ctrlKey: 1, code: "Digit1", key: "1" }],
  ["Ctrl+2 (đổi tab)", { ctrlKey: 1, code: "Digit2", key: "2" }],
  ["Ctrl+S (lưu note)", { ctrlKey: 1, key: "s" }],
  ["Ctrl+Shift+I (devtools)", { ctrlKey: 1, shiftKey: 1, key: "i" }],
  ["Ctrl+Shift+B (thanh bookmark)", { ctrlKey: 1, shiftKey: 1, key: "b" }],
  ["B trần (đang gõ chữ)", { key: "b" }],
  ["Shift+9 (gõ dấu ngoặc)", { shiftKey: 1, code: "Digit9" }],
];
CAM.forEach(([ten, e]) => check("CANARY: KHÔNG cướp " + ten, EC.matchCmd(ev(e)) === null));

// ---- 4. Nhãn phím tắt hiện trong menu và title nút ----
check("nhãn phím tắt của checkbox", EC.keyLabel(EC.CMDS.find(c => c.id === "task")) === "Ctrl+Shift+9");
check("nhãn phím tắt của tiêu đề 1", EC.keyLabel(EC.CMDS.find(c => c.id === "h1")) === "Ctrl+Alt+1");
check("lệnh không phím tắt -> nhãn rỗng", EC.keyLabel(EC.CMDS.find(c => c.id === "hr")) === "");
check("title nút kèm phím tắt", EC.btnTitle(EC.CMDS.find(c => c.id === "task")) === "Checkbox (Ctrl+Shift+9)");
check("title nút không phím tắt thì trơn", EC.btnTitle(EC.CMDS.find(c => c.id === "hr")) === "Kẻ ngang");

// ---- 5. Lọc menu "/" ----
check("gõ '/' trơn -> hiện tất cả", EC.filterCmds("").length === EC.CMDS.length);
check("lọc theo id", EC.filterCmds("h2").map(c => c.id).join() === "h2");
check("lọc KHÔNG dấu vẫn ra (tieu -> Tiêu đề)", EC.filterCmds("tieu").map(c => c.id).join() === "h1,h2,h3");
check("lọc CÓ dấu cũng ra", EC.filterCmds("tiêu").map(c => c.id).join() === "h1,h2,h3");
check("lọc theo từ khoá tiếng Anh (todo -> checkbox)", EC.filterCmds("todo").map(c => c.id).join() === "task");
check("lọc theo từ khoá tiếng Việt (viec -> checkbox)", EC.filterCmds("viec").map(c => c.id).join() === "task");
check("chữ 'đ' quy về 'd' (đậm -> Đậm)", EC.filterCmds("đậm").map(c => c.id).join() === "bold");
check("không khớp gì -> rỗng", EC.filterCmds("zzzz").length === 0);

// ---- 6. "/" chỉ mở menu khi mở đầu một từ ----
check("đầu dòng -> mở", EC.slashTrigger("") === true);
check("sau khoảng trắng -> mở", EC.slashTrigger("ghi chú ") === true);
check("sau nbsp của contenteditable -> mở", EC.slashTrigger("ghi chú ") === true);
check("CANARY: '12/2026' KHÔNG mở", EC.slashTrigger("12") === false);
check("CANARY: 'và/hoặc' KHÔNG mở", EC.slashTrigger("và") === false);
check("CANARY: đường dẫn 'a/b' KHÔNG mở", EC.slashTrigger("a") === false);

// ---- 7. Nhánh chế độ Nguồn chèn đúng cú pháp markdown ----
function ta(v, s, e) { return { value: v, selectionStart: s, selectionEnd: e === undefined ? s : e, focus() {} }; }
function src(id, truoc, sel) {
  const t = ta(truoc, sel[0], sel[1]);
  EC.run(id, { mode: () => "source", ta: t });
  return t.value;
}
check("Nguồn: checkbox -> '- [ ] '", src("task", "mua sữa", [0, 0]) === "- [ ] mua sữa");
check("Nguồn: bullet -> '- '", src("ul", "mua sữa", [0, 0]) === "- mua sữa");
check("Nguồn: danh sách số -> '1. '", src("ol", "mua sữa", [0, 0]) === "1. mua sữa");
check("Nguồn: H1/H2/H3 -> '#'", src("h1", "t", [0, 0]) === "# t" && src("h3", "t", [0, 0]) === "### t");
check("Nguồn: trích dẫn -> '> '", src("quote", "lời", [0, 0]) === "> lời");
check("Nguồn: đậm bọc '**'", src("bold", "đậm", [0, 3]) === "**đậm**");
check("Nguồn: code bọc backtick", src("code", "x=1", [0, 3]) === "`x=1`");
check("Nguồn: kẻ ngang", src("hr", "a", [1, 1]) === "a\n---\n");
// Bôi nhiều dòng thì tiền tố phải gắn TỪNG dòng, và danh sách số phải đếm lên.
check("Nguồn: checkbox nhiều dòng gắn từng dòng",
      src("task", "a\nb\nc", [0, 5]) === "- [ ] a\n- [ ] b\n- [ ] c");
check("Nguồn: danh sách số nhiều dòng đếm 1,2,3",
      src("ol", "a\nb\nc", [0, 5]) === "1. a\n2. b\n3. c");

// ---- 8. run() lành với đầu vào rác ----
check("run() id lạ -> false, không ném", EC.run("khong-co", { mode: () => "source", ta: ta("", 0) }) === false);
check("run() thiếu ctx -> false, không ném", EC.run("task", null) === false);

if (fails.length) {
  console.log("\nFAIL - test_editor_cmds: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_editor_cmds: tất cả pass");
