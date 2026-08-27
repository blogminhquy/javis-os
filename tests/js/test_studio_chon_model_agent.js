/* Ô chọn model của Agent (Studio) phải đầy đủ như trình chọn model chính.

       node tests/js/test_studio_chon_model_agent.js

   Chủ repo yêu cầu 27/08/2026: trước đó ô này gõ cứng đúng hai nhà (Claude + ChatGPT).
   Sửa cho đúng gồm ba phần, thiếu phần nào cũng thành lỗi âm thầm:

     1. Lấy danh sách từ CÙNG nguồn với trình chọn model chính (/settings -> model.providers),
        để kết nối thêm nhà ở trang Models là ô này có ngay - không phải nhớ sửa hai chỗ.
     2. Lọc theo cờ `agent_ok` server trả về: server chỉ dựng nổi engine agent cho một số
        nhà, bày thêm là hứa suông (agent sẽ lặng lẽ chạy Claude).
     3. Giá trị phải mang theo TÊN NHÀ, không chỉ tên model: cùng một tên model có ở hai nhà
        (gemini-2.5-pro ở Gemini CLI lẫn Gemini API), lưu mỗi tên là server phải đoán. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "studio.js"), "utf8");

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// Bóc đúng thân editAgent để không bắt nhầm chỗ khác trong file.
const i = SRC.indexOf("async function editAgent(");
const j = SRC.indexOf("\n  function ", i);
const FN = SRC.slice(i, j > i ? j : undefined);
check("tìm thấy editAgent", i !== -1 && FN.length > 0);

// ---- 1. Nguồn danh sách ----
check("đọc /settings (cùng nguồn với trình chọn model chính)", FN.indexOf('api("/settings")') !== -1);
check("duyệt model.providers", /\(st\.model \|\| \{\}\)\.providers/.test(FN));
check("CANARY: không còn gõ cứng riêng hai nhà Claude + ChatGPT",
  FN.indexOf('provider=anthropic-cli') === -1);

// ---- 2. Lọc đúng: chạy được (agent_ok) VÀ đã kết nối (configured) ----
check("lọc theo agent_ok để không bày lựa chọn hứa suông",
  /filter\(p => p\.agent_ok && p\.configured\)/.test(FN));

// ---- 3. Giá trị mang theo tên nhà ----
check("có hằng ngăn cách provider::model", SRC.indexOf('const MODEL_SEP = "::"') !== -1);
check("mỗi dòng model ghép kèm nhà", /const val = \(pid, m\) => pid \+ MODEL_SEP \+ m/.test(FN));
check("lưu thì tách ra thành model + model_provider",
  FN.indexOf("model: mName, model_provider: mProv") !== -1);
check("tách bằng chỉ số ký tự đầu tiên (tên model có thể chứa dấu / hay :)",
  FN.indexOf("raw.indexOf(MODEL_SEP)") !== -1);

// ---- 4. Không làm hỏng agent cũ / model đã lưu ----
check("agent CŨ chỉ lưu tên model vẫn dò được đúng dòng (không nhảy về Mặc định)",
  /const hit = \[\.\.\.sel\.options\]\.find\(/.test(FN));
check("model đã lưu mà nhà đã ngắt vẫn hiện 'đang lưu'", FN.indexOf("Model đang lưu") !== -1);
check("vẫn còn lựa chọn Mặc định", /<option value="">Mặc định/.test(FN));

// ---- 5. Một nhà lỗi không được kéo cả ô chọn chết ----
check("mỗi lần hỏi model live đều có nhánh dự phòng",
  /\.catch\(\(\) => \[\]\)/.test(FN));
check("Codex vẫn ép lấy danh sách live (catalog của nó vốn rỗng)",
  FN.indexOf('p.id === "openai-oauth" ? "&refresh=1"') !== -1);

// ---- 6. Chưa kết nối nhà nào thì nói thẳng, không để ô trống khó hiểu ----
check("có câu dẫn khi chưa kết nối nhà nào", FN.indexOf("Chưa kết nối nhà cung cấp nào") !== -1);

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_studio_chon_model_agent: tat ca pass");
