/* Hover vào một hội thoại phải ĐỔI TÊN / XOÁ được.

       node tests/js/test_chat_side_actions.js

   Lỗi thật chủ repo báo (0.12.3): "trong khung chat khi hover vào không xóa và sửa được tiêu
   đề của hội thoại". Nút CÓ hiện khi hover, bấm vào thì lại mở hội thoại đó.

   Nguyên nhân: nội dung nút là một <svg> (ic() trả về chuỗi SVG chứ không phải font icon), nên
   chạm vào icon thì e.target LÀ cái svg, không phải cái <span class="del">. Handler cũ so
   e.target.classList.contains("del") nên luôn trượt và rơi xuống nhánh mở hội thoại. Vùng bấm
   thực tế của span gần như chỉ còn viền 1-2px quanh icon - tức là hầu như không bấm trúng.

   Đây là lỗi CHỈ lộ ra khi chạy thật: đọc code thấy "có xử lý xoá" là tưởng xong. Nên test này
   chạy CHÍNH handler lấy từ source, với cây node mô phỏng đúng chỗ icon nằm trong span. */
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
  "e", "s", "delSession", "renSession", "openSession",
  m[1] + "\n"
);
function bam(target) {
  calls = [];
  const e = {
    target: target,
    stopPropagation: () => calls.push("stop"),
  };
  fn(e, { id: "sess-1" },
     () => calls.push("del"), () => calls.push("ren"), () => calls.push("open"));
  return calls;
}

// Cây node đúng như renderList dựng: .cside-item > .ci-meta > .act > span.del > svg.ic
const item = node("cside-item");
const meta = node("ci-meta", item);
const act = node("act", meta);
const spanDel = node("del", act);
const svgDel = node("ic", spanDel);       // <svg> do ic("trash-2") sinh ra
const spanRen = node("ren", act);
const svgRen = node("ic", spanRen);
const title = node("ci-title", item);

// ---- 1. Bấm THẲNG vào span (viền quanh icon) - vốn đã chạy từ trước ----
check("bấm span Xoá → gọi xoá", bam(spanDel).indexOf("del") !== -1);
check("bấm span Đổi tên → gọi đổi tên", bam(spanRen).indexOf("ren") !== -1);

// ---- 2. ĐÂY MỚI LÀ LỖI THẬT: bấm trúng icon bên trong span ----
// Icon choán gần hết vùng nút, nên đây là cú bấm mà người dùng thực hiện gần như MỌI lần.
check("CANARY: bấm vào ICON Xoá (svg trong span) → vẫn gọi xoá",
      bam(svgDel).indexOf("del") !== -1);
check("CANARY: bấm vào ICON Đổi tên (svg trong span) → vẫn gọi đổi tên",
      bam(svgRen).indexOf("ren") !== -1);
check("bấm icon Xoá KHÔNG được mở hội thoại", bam(svgDel).indexOf("open") === -1);
check("bấm icon Đổi tên KHÔNG được mở hội thoại", bam(svgRen).indexOf("open") === -1);

// ---- 3. Không được bắt nhầm: bấm chỗ khác vẫn phải mở hội thoại ----
check("bấm tiêu đề → mở hội thoại", bam(title).indexOf("open") !== -1);
check("bấm tiêu đề KHÔNG gọi xoá/đổi tên",
      bam(title).indexOf("del") === -1 && bam(title).indexOf("ren") === -1);
check("bấm vào chính hàng → mở hội thoại", bam(item).indexOf("open") !== -1);

// ---- 4. Chặn nổi bọt: hàng cha và drawer đều có handler riêng ----
check("xoá thì chặn nổi bọt (drawer/hàng cha không nuốt cú bấm)",
      bam(svgDel).indexOf("stop") !== -1);
check("đổi tên thì chặn nổi bọt", bam(svgRen).indexOf("stop") !== -1);

// ---- 5. Không quay lại cách so class của ĐÚNG node bị bấm ----
check("CANARY: không còn so e.target.classList (cách cũ luôn trượt khi bấm icon)",
      SRC.indexOf('e.target.classList.contains("del")') === -1
      && SRC.indexOf('e.target.classList.contains("ren")') === -1);

// ---- 6. Lớp chắn thứ hai bên CSS ----
// Icon không nhận chuột thì e.target luôn là span, kể cả nếu ai đó viết lại handler kiểu cũ.
check("CSS cho icon trong nút thôi nhận chuột",
      /\.ci-meta \.act span \.ic \{[^}]*pointer-events:\s*none/.test(CSS));

// ---- 7. Nút phải THẤY được: hover mới hiện là chủ ý, nhưng phải có rule đó ----
check("hover vào hàng thì nút hiện ra", /\.cside-item:hover \.act \{[^}]*opacity:\s*1/.test(CSS));

if (fails.length) {
  console.log("\nFAIL - test_chat_side_actions: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_chat_side_actions: tất cả pass");
