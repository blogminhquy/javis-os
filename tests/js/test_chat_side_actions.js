/* Hover vào một hội thoại phải mở được menu "..." (đổi tên, xoá, ghim...), và bấm chỗ khác thì mở hội thoại.

       node tests/js/test_chat_side_actions.js

   Lỗi thật chủ repo báo (0.12.3): "trong khung chat khi hover vào không xóa và sửa được tiêu
   đề của hội thoại". Nút CÓ hiện khi hover, bấm vào thì lại mở hội thoại đó.

   Nguyên nhân: nội dung nút là một <svg> (ic() trả về chuỗi SVG chứ không phải font icon), nên
   chạm vào icon thì e.target LÀ cái svg, không phải cái <span class="del">. Handler cũ so
   e.target.classList.contains("del") nên luôn trượt và rơi xuống nhánh mở hội thoại. Vùng bấm
   thực tế của span gần như chỉ còn viền 1-2px quanh icon - tức là hầu như không bấm trúng.

   Đây là lỗi CHỈ lộ ra khi chạy thật: đọc code thấy "có xử lý xoá" là tưởng xong. Nên test này
   chạy CHÍNH handler lấy từ source, với cây node mô phỏng đúng chỗ icon nằm trong nút.

   2026-11-09 (owner, mock-up approved): the four icons of a row (pin, move, rename, delete) folded into one "..."
   button that opens the row menu. The same trap stands: the button's content is an <svg>. */
const fs = require("fs");
const path = require("path");

const D = (f) => fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", f), "utf8");
const SRC = D("sessions-ui.js");
const CSS = D("style.css");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- Mock DOM tối thiểu: chỉ cần quan hệ cha-con + classList + closest ----
// closest ở đây cài ĐÚNG như trình duyệt cho họ selector đang dùng (danh sách class ngăn bởi
// dấu phẩy): xét CHÍNH node trước, rồi lần lên cha. Cài sai chỗ này là test tự dối mình.
function node(cls, parent) {
  const n = {
    _cls: (cls || "").split(/\s+/).filter(Boolean),
    parentNode: parent || null,
    classList: { contains: (c) => n._cls.indexOf(c) !== -1 },
    closest(sel) {
      const want = sel.split(",").map((s) => s.trim().replace(/^\./, "")).filter(Boolean);
      let cur = n;
      while (cur) {
        if (want.some((c) => cur._cls.indexOf(c) !== -1)) return cur;
        cur = cur.parentNode;
      }
      return null;
    },
  };
  return n;
}

// ---- Lấy CHÍNH handler trong source ra chạy ----
const m = SRC.match(/item\.onclick = function \(e\) \{\n([\s\S]*?)\n      \};/);
check("tìm được handler bấm vào một hội thoại", !!m);
if (!m) { console.log("\nFAIL - test_chat_side_actions: không đọc được handler"); process.exit(1); }

let calls = [];
const fn = new Function(
  "e", "s", "item", "toggleMenuDong", "openSession",
  m[1] + "\n"
);
function bam(target, rowState) {
  calls = [];
  const e = {
    target: target,
    stopPropagation: () => calls.push("stop"),
  };
  const row = rowState || {};
  fn(e, { id: "sess-1" }, row, () => calls.push("menu"), () => calls.push("open"));
  return calls;
}

// Cây node đúng như renderList dựng: .cside-item > .ci-meta > button.ci-more > svg.ic
const item = node("cside-item");
const meta = node("ci-meta", item);
const more = node("ci-more", meta);
const svgMore = node("ic", more);          // <svg> do ic("ellipsis") sinh ra
const title = node("ci-title", item);

// ---- 1. Bấm THẲNG vào nút "..." ----
check("bấm nút ... → mở menu của hàng", bam(more).indexOf("menu") !== -1);

// ---- 2. Lỗi thật cũ: bấm trúng icon bên trong nút ----
check("CANARY: bấm vào ICON ... (svg trong nút) → vẫn mở menu", bam(svgMore).indexOf("menu") !== -1);
check("bấm icon ... KHÔNG được mở hội thoại", bam(svgMore).indexOf("open") === -1);
check("mở menu thì chặn nổi bọt (hàng cha không nuốt cú bấm)", bam(svgMore).indexOf("stop") !== -1);

// ---- 3. Bấm chỗ khác vẫn phải mở hội thoại ----
check("bấm tiêu đề → mở hội thoại", bam(title).indexOf("open") !== -1);
check("bấm tiêu đề KHÔNG mở menu", bam(title).indexOf("menu") === -1);
check("bấm vào chính hàng → mở hội thoại", bam(item).indexOf("open") !== -1);

// ---- 4. Nhấn giữ đã mở menu: cú chạm kết thúc nhấn giữ không mở thêm hội thoại ----
const giu = { _nhanGiu: true };
check("sau nhấn giữ, cú chạm kết thúc KHÔNG mở hội thoại", bam(title, giu).indexOf("open") === -1);
check("cờ nhấn giữ chỉ nuốt đúng một cú chạm", giu._nhanGiu === false && bam(title, giu).indexOf("open") !== -1);

// ---- 5. Không quay lại cách so class của ĐÚNG node bị bấm ----
check("CANARY: không so e.target.classList (cách cũ luôn trượt khi bấm icon)",
      SRC.indexOf("e.target.classList.contains(") === -1);

// ---- 6. Lớp chắn thứ hai bên CSS ----
check("CSS cho icon trong nút ... thôi nhận chuột",
      /\.ci-more \.ic, \.ci-more svg \{[^}]*pointer-events:\s*none/.test(CSS));

// ---- 7. Nút phải THẤY được ----
check("hover vào hàng thì nút ... hiện ra", /\.cside-item:hover \.ci-more[^{]*\{[^}]*opacity:\s*1/.test(CSS));
check("màn cảm ứng (không có hover) luôn thấy nút ...", /@media \(hover: none\) \{\s*\.ci-more \{[^}]*opacity:\s*1/.test(CSS));
check("chuột phải và nhấn giữ cũng mở menu",
      SRC.indexOf("item.oncontextmenu = function (e) { e.preventDefault(); moMenuDong(item, s, false); };") !== -1
      && SRC.indexOf('item.addEventListener("touchstart"') !== -1);

// ---- 8. HÀNG ĐÃ GHIM nhìn ra được, không chờ rê chuột ----
// 2026-11-09 (owner): a small pin before the title, always visible; no bar on the left any more.
check("hàng ghim mang lớp riêng", /\(s\.pinned \? " ghim" : ""\)/.test(SRC));
check("hàng ghim có dấu ghim trước tiêu đề", SRC.indexOf('(s.pinned ? \'<span class="ci-pin"') !== -1);
check("dấu ghim tô màu nhấn", /\.ci-pin \{[^}]*color:\s*var\(--accent\)/.test(CSS));
check("CANARY: bỏ vạch màu bên trái của hàng ghim (chủ dự án duyệt bản thiết kế 09/11)",
      !/\.cside-item\.ghim \{[^}]*border-left/.test(CSS));

if (fails.length) {
  console.log("\nFAIL - test_chat_side_actions: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_chat_side_actions: tất cả pass");
