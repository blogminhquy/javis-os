/* Dải việc nền chỉ được hiện khi có việc THẬT SỰ đang chạy hoặc đang kẹt.

       node tests/js/test_dai_viec_nen.js

   Chủ repo báo (2026-08-07, kèm ảnh): "sao lại hiển thị 9 việc nền như này? anh không muốn
   vào chat mà hiện ra như này đâu." Chín cái trong ảnh là chín NHẮC HẸN đang đợi tới giờ -
   không chạy, không hỏng, không cần ai làm gì, và trang Việc định kỳ đã liệt kê sẵn. Bản đầu
   của dải gom chúng vào mức xám "đang chờ tới giờ" rồi dựng một khối chữ giữa khung chat.

   Test này khoá hai luật: mức "idle" thì ẩn hẳn, và khi có hiện thì chỉ vẽ đúng mấy việc gây
   ra mức đó (chứ không đổ cả hàng đợi ra), tối đa 4 chip. */
const { quyetDinh } = require("../../dashboard/background-strip.js");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

function nhac(i) {
  return { kind: "reminder", id: "r" + i, title: "Nhắc " + i, status: "pending", mine: false };
}
function viec(i, status, extra) {
  return Object.assign({ kind: "task", id: "t" + i, title: "Việc " + i, status: status,
    mine: false, stalled: false }, extra || {});
}

// ---- 1. Ca chủ repo chụp được: 9 nhắc hẹn chờ tới giờ -> ẩn hẳn ----
const CHIN_NHAC = {
  ok: true, level: "idle", count: 9, mine_count: 0, running_count: 0, stalled_count: 0,
  orchestration: "off", items: [1, 2, 3, 4, 5, 6, 7, 8, 9].map(nhac), truncated: 0
};
let q = quyetDinh(CHIN_NHAC);
check("9 nhắc hẹn chờ tới giờ: dải ẩn hẳn", q.hien === false);
check("9 nhắc hẹn chờ tới giờ: không dựng chip nào", q.chips.length === 0);
check("9 nhắc hẹn chờ tới giờ: không có dòng tiêu đề nào", q.dau === "");

check("loop đang bật nhưng chưa tới giờ cũng ẩn", quyetDinh({
  level: "idle", items: [{ kind: "loop", id: "l1", title: "Canh doanh thu", status: "enabled" }]
}).hien === false);
check("rỗng hoàn toàn: ẩn", quyetDinh({ level: "idle", items: [] }).hien === false);
check("dữ liệu hỏng / không có gì: ẩn chứ không nổ", quyetDinh(null).hien === false
  && quyetDinh({}).hien === false);

// ---- 2. Có việc đang chạy thật -> hiện, và chỉ hiện việc đang chạy ----
const DANG_CHAY = {
  level: "run", running_count: 1, stalled_count: 0, orchestration: "auto", count: 10,
  items: [viec(1, "running", { mine: true })].concat([1, 2, 3, 4, 5, 6, 7, 8, 9].map(nhac))
};
q = quyetDinh(DANG_CHAY);
check("có việc đang chạy: dải hiện, tông xanh", q.hien === true && q.muc === "run");
check("có việc đang chạy: chỉ vẽ việc đang chạy, không kèm 9 nhắc hẹn", q.chips.length === 1
  && q.chips[0].status === "running");
check("có việc đang chạy: tiêu đề nói đúng số", q.dau.indexOf("1 việc đang chạy ngầm") === 0);
check("việc của chính hội thoại này được đếm riêng",
  q.dau.indexOf("1 của hội thoại này") !== -1);
check("đang chạy thì không kèm cảnh báo điều phối", q.warn === "");

// ---- 3. Đã giao mà điều phối tắt -> tông vàng, nói thẳng ----
const KET = {
  level: "stall", running_count: 0, stalled_count: 2, orchestration: "off", count: 12,
  items: [viec(1, "todo", { stalled: true, mine: true }), viec(2, "triage", { stalled: true })]
    .concat([1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(nhac))
};
q = quyetDinh(KET);
check("việc kẹt: dải hiện, tông vàng", q.hien === true && q.muc === "stall");
check("việc kẹt: chỉ vẽ đúng việc kẹt", q.chips.length === 2
  && q.chips.every(function (x) { return x.stalled; }));
check("việc kẹt: nói thẳng là KHÔNG tự chạy",
  q.dau.indexOf("KHÔNG tự chạy") !== -1);
check("việc kẹt: chỉ đúng cách bật", q.warn.indexOf("AI tự vận hành") !== -1
  && q.warn.indexOf("off") !== -1);

// ---- 4. Trần 4 chip ----
const NHIEU = {
  level: "run", running_count: 7, orchestration: "auto",
  items: [1, 2, 3, 4, 5, 6, 7].map(function (i) { return viec(i, "running"); })
};
q = quyetDinh(NHIEU);
check("nhiều việc chạy: cắt còn 4 chip", q.chips.length === 4);
check("nhiều việc chạy: phần dư đếm đúng vào '+N nữa'", q.them === 3);
check("nhiều việc chạy: tiêu đề vẫn nói tổng số thật", q.dau.indexOf("7 việc") === 0);

// ---- 5. Máy chủ đời trước (không có `level`, không có `stalled`) ----
q = quyetDinh({ running_count: 1, items: [viec(1, "running")] });
check("máy chủ cũ không gửi level: suy từ running_count", q.hien === true && q.muc === "run");
q = quyetDinh({ stalled_count: 1, orchestration: "off", items: [viec(1, "todo")] });
check("máy chủ cũ không gửi stalled: vẫn vẽ được chip", q.hien === true && q.chips.length === 1);
q = quyetDinh({ running_count: 0, stalled_count: 0, items: [nhac(1)] });
check("máy chủ cũ, chỉ có nhắc hẹn: vẫn ẩn", q.hien === false);

// ---- 6. Một dòng (2026-10-15): viên thuốc chỉ mang MỘT việc, phần còn lại vào khung chi tiết ----
// Chủ repo: khối ba dòng cũ "chiếm cả màn hình"; chỉ cần hiện 1 việc, bấm vào mới ra chi tiết.
const { tuoi } = require("../../dashboard/background-strip.js");
q = quyetDinh({ level: "run", running_count: 3, items: [
  viec(1, "running"), viec(2, "running", { mine: true }), viec(3, "running")] });
check("viên thuốc mang việc của chính hội thoại này trước", q.chinh && q.chinh.id === "t2");
check("viên thuốc đếm phần còn lại thành +N", q.con === 2);
q = quyetDinh({ level: "run", running_count: 1, items: [viec(1, "running")] });
check("một việc thì không có +N", q.chinh.id === "t1" && q.con === 0);
q = quyetDinh(NHIEU);
check("+N tính theo tổng thật, không theo 4 việc đã cắt", q.con === 6);
const BAY_GIO = 1_800_000_000_000;
check("đã chạy dưới 1 phút: vừa bắt đầu", tuoi(BAY_GIO / 1000 - 20, BAY_GIO) === "vừa bắt đầu");
check("đã chạy 7 phút", tuoi(BAY_GIO / 1000 - 420, BAY_GIO) === "đã chạy 7 phút");
check("đã chạy 1 giờ 7 phút", tuoi(BAY_GIO / 1000 - 4020, BAY_GIO) === "đã chạy 1 giờ 7 phút");
check("không có mốc thời gian: không bịa số", tuoi(0, BAY_GIO) === "vừa bắt đầu");
const SRC = require("fs").readFileSync(require("path").join(__dirname, "../../dashboard/background-strip.js"), "utf8");
check("khung chi tiết đóng sẵn, chỉ mở khi bấm viên thuốc",
  SRC.indexOf("aria-expanded=\"false\"") !== -1 && /class="bg-pop"[^>]*hidden/.test(SRC));
check("bấm ra ngoài hay Esc thì đóng khung chi tiết",
  SRC.indexOf('ev.key === "Escape"') !== -1 && SRC.indexOf("!e.contains(ev.target)") !== -1);
check("không còn hàng chip dàn ngang trên khung nhập", SRC.indexOf('class="bg-chips"') === -1);

if (fails.length) {
  console.log("\nFAIL - test_dai_viec_nen: " + fails.length + " lỗi");
  process.exit(1);
}
console.log("\nOK - test_dai_viec_nen: tất cả pass");
