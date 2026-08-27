/* Thẻ "Mã TEXT · 30 dòng · bấm để xem" nằm giữa file .md: KHÔNG mở được, KHÔNG xem được.

       node tests/js/test_the_ma_text_trong_trinh_sua.js

   Lỗi thật chủ repo báo 27/08/2026 (ảnh chụp: một thẻ "Ma TEXT / 30 dong · bam de xem"
   nằm giữa AGENTS.md, bấm không ra gì). Hai tầng cộng lại thành nội dung MẤT HÚT:

     1. renderFence thu MỌI fence dài (>= 24 dòng hoặc >= 800 ký tự) thành thẻ artifact -
        hợp lý trong bong bóng chat (đỡ chiếm chỗ, bấm để bung panel), nhưng trong TRÌNH SỬA
        thì đó là nội dung của chính file đang mở: người dùng cần NHÌN THẤY và SỬA tại chỗ.
     2. Handler click đặt nhánh `.jv-art` SAU chốt `trongTrinhSua()`, mà `.note-editor` nằm
        trọn trong chốt đó -> trong trình sửa thẻ chết hẳn, bấm không mở panel.

   Cách chữa: trình sửa truyền {trinhSua:true} nên fence dài giữ nguyên hình khối code
   (turndown đã có luật jvcodewrap nên lưu vẫn trả về đúng fence ```), và nhánh `.jv-art`
   chuyển lên TRƯỚC chốt trongTrinhSua để mermaid/svg/html vẫn bấm xem được ngay trong
   trình sửa (panel chỉ để XEM, không phải editor lồng nhau). */
const fs = require("fs");
const path = require("path");
const { mdToHtml } = require("../../dashboard/chat-render.js");

const ROOT = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const RENDER = read("dashboard/chat-render.js");
const CONSOLE = read("dashboard/console.js");
const HTML = read("dashboard/index.html");

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

const DAI = "```text\n" + Array.from({ length: 30 }, (_, i) => "dong " + (i + 1)).join("\n") + "\n```";

// ---- 1. Trong TRÌNH SỬA: fence dài phải xem được tại chỗ ----
const sua = mdToHtml(DAI, null, { trinhSua: true });
check("trình sửa KHÔNG thu fence dài thành thẻ artifact", sua.indexOf("jv-art") === -1);
check("trình sửa render thành khối code thật", sua.indexOf("code-wrap") !== -1);
const chuThuan = sua.replace(/<[^>]+>/g, "");
check("thấy ĐỦ 30 dòng nội dung (không phải một cái thẻ)",
  chuThuan.trim().split("\n").length === 30, chuThuan.trim().split("\n").length);
check("thấy cả dòng giữa lẫn dòng cuối",
  chuThuan.includes("dong 17") && chuThuan.includes("dong 30"));

// ---- 2. Trong CHAT: giữ nguyên hành vi cũ (thẻ gọn, bấm bung panel) ----
const chat = mdToHtml(DAI);
check("chat vẫn thu fence dài thành thẻ artifact", chat.indexOf("jv-art") !== -1);
check("cờ trinhSua không rò sang lần gọi sau (finally khôi phục)",
  mdToHtml(DAI).indexOf("jv-art") !== -1);

// ---- 3. mermaid/svg/html vẫn là thẻ trong trình sửa (chúng có bản xem trước thật) ----
check("mermaid trong trình sửa vẫn là thẻ xem trước",
  mdToHtml("```mermaid\ngraph TD;A-->B;\n```", null, { trinhSua: true }).indexOf("jv-art") !== -1);
check("code NGẮN vẫn là khối code ở cả hai chế độ",
  mdToHtml("```js\nlet a=1;\n```").indexOf("code-wrap") !== -1
  && mdToHtml("```js\nlet a=1;\n```", null, { trinhSua: true }).indexOf("code-wrap") !== -1);

// ---- 4. CANARY thứ tự trong handler click: .jv-art phải đứng TRƯỚC chốt trongTrinhSua ----
// Đây chính là tầng lỗi thứ hai. Đảo lại thứ tự là thẻ chết trong trình sửa như cũ.
const iArt = RENDER.indexOf('e.target.closest(".jv-art")');
const iChot = RENDER.indexOf("if (trongTrinhSua(e.target)) return;");
check("tìm thấy cả hai mốc trong handler", iArt !== -1 && iChot !== -1);
check("CANARY: nhánh .jv-art đứng TRƯỚC chốt trongTrinhSua", iArt < iChot, iArt + " vs " + iChot);
check("bấm thẻ xong thì dừng hẳn (return), không rơi tiếp xuống các nhánh dưới",
  /openArtifact\(card\.dataset\.art\); return; \}/.test(RENDER));

// ---- 5. console.js phải truyền cờ ở CẢ HAI chỗ render ----
// Thiếu chỗ thứ hai (srcToWys) thì bấm Nguồn rồi quay lại Sửa là thẻ chết hiện về.
check("cả hai lần render của trình sửa đều truyền {trinhSua:true}",
  CONSOLE.split("mdToHtml(ta.value, null, { trinhSua: true })").length - 1 === 2,
  CONSOLE.split("mdToHtml(ta.value, null, { trinhSua: true })").length - 1);
check("không còn lời gọi mdToHtml(ta.value) trần trong trình sửa",
  CONSOLE.indexOf("mdToHtml(ta.value) ") === -1 && CONSOLE.indexOf("mdToHtml(ta.value);") === -1);

// ---- 6. Lưu không được làm hỏng: khối code phải có luật turndown trả về fence ----
check("turndown có luật jvcodewrap (khối code -> fence ``` khi lưu)",
  CONSOLE.indexOf('addRule("jvcodewrap"') !== -1);
check("turndown vẫn giữ luật jvartifact (thẻ mermaid/svg/html -> fence)",
  CONSOLE.indexOf('addRule("jvartifact"') !== -1);

// ---- 7. cache-bust ----
const v = (f) => Number((HTML.match(new RegExp(f.replace(".", "\\.") + "\\?v=(\\d+)")) || [])[1] || 0);
check("chat-render.js đã bump ?v= (>= 10)", v("chat-render.js") >= 10, v("chat-render.js"));
check("console.js đã bump ?v= (>= 116)", v("console.js") >= 116, v("console.js"));

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_the_ma_text_trong_trinh_sua: tat ca pass");
