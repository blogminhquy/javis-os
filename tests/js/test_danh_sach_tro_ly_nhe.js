/* Danh sách trợ lý xin bản NHẸ, còn trình sửa tự đi lấy system prompt.

       node tests/js/test_danh_sach_tro_ly_nhe.js

   Vì sao (đo thật, xem tests/python/test_agents_danh_sach_nhe.py): GET /agents trên một brain
   14 trợ lý trả 366 KB, trong đó 363 KB là system prompt của từng người - thứ cột trái không
   bao giờ hiện. Mọi danh sách phải xin `prompt=0`.

   Nhưng đổi lại có một cái bẫy MẤT DỮ LIỆU, và nó im lặng: mục trong danh sách nay không còn
   `prompt`, nên nếu trình sửa cứ thế đổ vào ô textarea thì ô đó RỖNG - trông hệt một trợ lý
   chưa viết prompt. Người dùng sửa tên rồi bấm Lưu là ghi đè prompt thật bằng chuỗi rỗng.
   Nên: trình sửa gọi /agents/get, và lượt đó HỎNG thì KHÔNG được mở form ra. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const doc = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const ST = doc("studio.js"), WS = doc("workspace.js"), CB = doc("chatbots.js");
const VI = JSON.parse(doc("i18n/vi.json")), EN = JSON.parse(doc("i18n/en.json"));

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ---- 1. Mọi chỗ lấy DANH SÁCH đều xin bản nhẹ ----
check("workspace.js (cột trái trang Cộng sự) xin prompt=0",
  /api\("\/agents\?brain=" \+ b \+ "&prompt=0"\)/.test(WS));
check("studio.js loadAgents (lưới thẻ) xin prompt=0",
  /\/agents\?brain=\$\{encodeURIComponent\(brain\(\)\)\}&prompt=0`\);\s*\n\s*_agState\.agents/.test(ST));
check("studio.js editWorkflow (ô chọn agent của từng bước) xin prompt=0",
  /\/agents\?brain=\$\{encodeURIComponent\(brain\(\)\)\}&prompt=0`\);\s*\n\s*agentsCache/.test(ST));
check("chatbots.js (ô chọn agent của bot) xin prompt=0",
  /"\/agents\?brain=" \+ encodeURIComponent\(br \|\| "brain"\) \+ "&prompt=0"/.test(CB));
// CANARY: còn sót một chỗ gọi /agents danh sách mà quên prompt=0 là chỗ đó kéo lại 366 KB.
// Soi cả BIỂU THỨC gọi, không chỉ tới dấu nháy: workspace/chatbots nối chuỗi bằng dấu +
// nên "&prompt=0" nằm ở mảnh sau, cắt ở dấu nháy là tưởng nhầm chúng quên.
const sot = [["studio.js", ST], ["workspace.js", WS], ["chatbots.js", CB]]
  .flatMap(([f, src]) => {
    const ra = [];
    let at = src.indexOf("/agents?brain=");
    while (at !== -1) {
      const cauGoi = src.slice(at, at + 160).split("\n")[0];
      if (cauGoi.indexOf("prompt=0") === -1) ra.push(f + ": " + cauGoi.slice(0, 90));
      at = src.indexOf("/agents?brain=", at + 1);
    }
    return ra;
  });
check("CANARY: không còn lời gọi danh sách /agents nào quên prompt=0  [" + sot.join(" | ") + "]",
  sot.length === 0);

// ---- 2. Trình sửa tự lấy prompt, và hỏng thì KHÔNG mở form ----
const k = ST.indexOf("async function layAgentDay(");
const LAY = ST.slice(k, ST.indexOf("\n  }", k));
check("có layAgentDay()", k !== -1);
check("layAgentDay gọi /agents/get theo đúng slug + brain",
  /\/agents\/get\?slug=\$\{encodeURIComponent\(a\.slug\)\}&brain=\$\{encodeURIComponent\(brain\(\)\)\}/.test(LAY));
check("tạo mới (chưa có slug) thì không gọi mạng", /if \(!a \|\| !a\.slug\) return null;/.test(LAY));
check("người gọi đã cầm bản đầy đủ thì dùng luôn, không gọi lại",
  /if \(typeof a\.prompt === "string"\) return a;/.test(LAY));
check("CANARY: hỏng thì trả false, KHÔNG rơi về chuỗi rỗng (đó là đường mất prompt)",
  /return false;/.test(LAY) && LAY.indexOf('prompt: ""') === -1 && LAY.indexOf('|| ""') === -1);

const i = ST.indexOf("async function editAgent(");
const FN = ST.slice(i, ST.indexOf("\n  function ", i));
check("editAgent lấy form và prompt SONG SONG (không nối đuôi thêm một nhịp mạng)",
  /Promise\.all\(\[duLieuForm\(\), layAgentDay\(a\)\]\)/.test(FN));
check("CANARY: lấy hỏng thì dừng hẳn, không dựng form", /if \(day === false\) \{/.test(FN)
  && FN.slice(FN.indexOf("if (day === false) {"), FN.indexOf("if (day) a = day;")).indexOf("return;") !== -1);
check("có nút thử lại để người dùng không kẹt", /editAgent\(a, opts\)/.test(FN));
check("dùng bản đầy đủ để dựng form", /if \(day\) a = day;/.test(FN));

// ---- 3. Câu báo lỗi lấy từ từ điển, đủ cả hai thứ tiếng ----
check("có khoá studio.ag_load_err ở vi.json và en.json",
  !!VI["studio.ag_load_err"] && !!EN["studio.ag_load_err"]);
check("editAgent dùng khoá đó chứ không gõ cứng chữ", /t\("studio\.ag_load_err"\)/.test(FN));

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - danh sach tro ly nhe");
