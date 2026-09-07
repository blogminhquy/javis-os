/* Module dashboard nạp NGOÀI trình duyệt: hàm dịch phải rào đúng và KHÔNG tự gọi chính nó.
 *
 *     python tests/run.py i18n_ngoai_trinh_duyet
 *
 * Vì sao có file này. Một số module (chat-render, dataview, file-editor, background-strip,
 * chat-ask, graph, chat-acts, task-suggest, chat-slash, editor-cmds) được require() thẳng
 * trong test node. Ở đó `window` CHƯA KHAI BÁO, nên đọc `window.t` ném ReferenceError chứ
 * không trả undefined - phải hỏi bằng typeof. Mỗi file vì thế có một hàm rào riêng.
 *
 * Cái bẫy mà file này sinh ra để canh (dính thật ngày 07/09, bản 0.55.14): hàm rào bị sửa
 * thành TỰ GỌI CHÍNH NÓ ở nhánh trình duyệt.
 *
 *     function tw(k, b) {
 *       if (typeof window !== "undefined" && window.t) return tw(k, b);   // <- ĐỆ QUY VÔ HẠN
 *       ...
 *     }
 *
 * Trên trình duyệt `window.t` LUÔN tồn tại (i18n/index.js là script nạp trước), nên mọi lời
 * gọi rơi thẳng vào đệ quy và ném RangeError: khung chat, dải việc nền, trình sửa file cùng
 * chết. Mà TOÀN BỘ 302 test vẫn xanh, vì test chạy dưới node - nơi nhánh đó không bao giờ
 * được đi vào. Đo sai chỗ đau thì lỗi lọt qua cả một bảng xanh.
 *
 * Nên test này KHÔNG chỉ soi mã: nó DỰNG window giả rồi GỌI THẬT, để nhánh trình duyệt được
 * đi vào ít nhất một lần.
 */
const fs = require("node:fs");
const path = require("node:path");
const ROOT = path.resolve(__dirname, "../..");
const D = path.join(ROOT, "dashboard");

let loi = 0;
function check(ten, ok, chi_tiet = "") {
  console.log(`${ok ? "ok  " : "FAIL"} ${ten}${ok ? "" : "  " + chi_tiet}`);
  if (!ok) loi++;
}

const VI = JSON.parse(fs.readFileSync(path.join(D, "i18n", "vi.json"), "utf8"));

// file -> tên hàm rào của nó
const RAO = {
  "background-strip.js": "tw", "chat-acts.js": "tw", "chat-ask.js": "tw",
  "chat-render.js": "tw", "chat-slash.js": "tw", "dataview.js": "tw",
  "file-editor.js": "tw", "task-suggest.js": "tw",
  "editor-cmds.js": "dich", "graph.js": "graphTw",
};

// ---- 1. Hàm rào hỏi bằng typeof, và nhánh trình duyệt gọi window.t chứ KHÔNG tự gọi ----
for (const [ten, ham] of Object.entries(RAO)) {
  const src = fs.readFileSync(path.join(D, ten), "utf8");
  check(`${ten}: có hàm rào ${ham}()`, src.includes(`function ${ham}(`));
  check(`${ten}: hỏi window bằng typeof (đọc thẳng là ReferenceError dưới node)`,
        /typeof window !== "undefined" && window\.t/.test(src));
  // Đây là canary chính: nhánh trình duyệt phải trả về window.t(...), không phải chính nó.
  const tuGoi = new RegExp(`window\\.t\\)\\s*return\\s+${ham}\\(`);
  check(`CANARY: ${ten} nhánh trình duyệt KHÔNG tự gọi ${ham}() (đệ quy vô hạn)`,
        !tuGoi.test(src), "return " + ham + "( ngay sau khi thấy window.t");
}

// ---- 2. Gọi THẬT với window giả: nhánh trình duyệt phải đi qua được ----
// Soi mã bắt được đúng một hình dạng của lỗi. Chạy thật bắt được mọi hình dạng.
const goi = [];
global.window = { t: (k) => "«" + k + "»", ic: () => "", matchMedia: () => ({ matches: false, addEventListener() {} }) };
for (const ten of Object.keys(RAO)) {
  if (ten === "graph.js") continue;   // graph.js không export, cần DOM thật để nạp
  const p = path.join(D, ten);
  let mod = null, sap = "";
  try {
    delete require.cache[require.resolve(p)];
    mod = require(p);
  } catch (e) { sap = String((e && e.message) || e); }
  check(`${ten}: nạp được khi CÓ window (nhánh trình duyệt)`, !sap, sap.slice(0, 90));
  if (mod) goi.push([ten, mod]);
}

// Gọi vào vài hàm thật sự chạm từ điển, để chắc nhánh window.t được đi vào.
try {
  const bs = require(path.join(D, "background-strip.js"));
  const r = bs.quyetDinh({ items: [{ id: 1, title: "x" }], running_count: 2, orchestration: "off" });
  check("background-strip: quyetDinh() lấy chữ QUA window.t", String(r.dau).includes("«"));
} catch (e) {
  check("background-strip: quyetDinh() lấy chữ QUA window.t", false, String(e.message).slice(0, 90));
}
try {
  const cr = require(path.join(D, "chat-render.js"));
  const h = cr.mdToHtml("mở `Javis/loops/x.md` nhé");
  check("chat-render: mdToHtml() chạy trọn khi có window", typeof h === "string" && h.length > 0);
} catch (e) {
  check("chat-render: mdToHtml() chạy trọn khi có window", false, String(e.message).slice(0, 90));
}
delete global.window;

// ---- 3. Mọi khoá gọi qua hàm rào đều phải có trong vi.json ----
// test_i18n.mjs chỉ quét `t("...")` và `window.t("...")`; sau `t` là chữ `w` nên nó trượt hết
// các lời gọi `tw(...)`. Mà gần như toàn bộ module ở trên nay gọi qua `tw`, tức chốt chặn kia
// đang hở đúng phần lớn mã mới. Bịt ở đây.
const thieu = [];
for (const [ten, ham] of Object.entries(RAO)) {
  const src = fs.readFileSync(path.join(D, ten), "utf8");
  const re = new RegExp(`(?<![\\w.$])${ham}\\(\\s*"([a-z0-9_.]+)"`, "g");
  for (const m of src.matchAll(re)) {
    if (m[1].includes(".") && !(m[1] in VI)) thieu.push(`${ten}:${m[1]}`);
  }
}
check("mọi khoá gọi qua hàm rào đều có trong vi.json", thieu.length === 0, thieu.slice(0, 6).join(", "));

console.log("");
if (loi) { console.log(`THẤT BẠI ${loi} mục`); process.exit(1); }
console.log("OK - test_i18n_ngoai_trinh_duyet: tất cả pass");
