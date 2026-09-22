/* Ô chọn model của Agent (Studio) phải đầy đủ như trình chọn model chính.

       node tests/js/test_studio_chon_model_agent.js

   Chủ repo yêu cầu 27/08/2026: trước đó ô này gõ cứng đúng hai nhà (Claude + ChatGPT).
   Sửa cho đúng gồm ba phần, thiếu phần nào cũng thành lỗi âm thầm:

     1. Lấy danh sách từ CÙNG nguồn với trình chọn model chính (/settings -> model.providers),
        để kết nối thêm nhà ở trang Models là ô này có ngay - không phải nhớ sửa hai chỗ.
     2. Lọc theo cờ `agent_ok` server trả về: server chỉ dựng nổi engine agent cho một số
        nhà, bày thêm là hứa suông (agent sẽ lặng lẽ chạy Claude).
     3. Giá trị phải mang theo TÊN NHÀ, không chỉ tên model: cùng một tên model có ở hai nhà
        (gemini-2.5-pro ở Gemini CLI lẫn Gemini API), lưu mỗi tên là server phải đoán.

   Bổ sung 21/09/2026 (0.62.3) - chủ repo: "phần lựa chọn về ui đang khác với chọn model nền
   thực sự, như việc không có tìm kiếm, không khoá những model không chọn được".
     4. Không còn <select> thuần: dùng CHUNG thân bảng chọn với thanh model dưới khung chat
        (window.JavisModelList trong model-list.js), nên có ô tìm và có nhà bị khoá.
     5. Nhà CHƯA cắm key không bị lọc mất nữa - nó hiện ra kèm ổ khoá, model-list.js lo phần
        vẽ. Lọc `configured` như bản cũ là giấu mất lựa chọn người dùng cần biết. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "studio.js"), "utf8");
const LIST = fs.readFileSync(path.join(ROOT, "dashboard", "model-list.js"), "utf8");
const HTML = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");

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
// Bỏ dòng chú thích: canary phải soi MÃ CHẠY, không phải câu giải thích vì sao bỏ nó đi.
const CHAY = FN.split("\n").filter(l => !l.trim().startsWith("//")).join("\n");

// Hai lượt mạng nền của form (danh sách skill + /settings) nằm trong duLieuForm(): nó giữ
// kết quả một lát vì trang Cộng sự dựng lại form này mỗi lần bấm sang một trợ lý khác.
const k = SRC.indexOf("async function duLieuForm(");
const FORM = SRC.slice(k, SRC.indexOf("\n  function quenForm", k));

// ---- 1. Nguồn danh sách ----
check("editAgent lấy dữ liệu form qua duLieuForm()", k !== -1 && FN.indexOf("await duLieuForm()") !== -1);
check("đọc /settings (cùng nguồn với trình chọn model chính)", FORM.indexOf('api("/settings")') !== -1);
check("đọc /skills của đúng brain đang chọn", /api\(`\/skills\?brain=\$\{encodeURIComponent\(b\)\}`\)/.test(FORM));
check("bộ nhớ tạm khoá theo brain và có hạn dùng", /_formCache\.brain === b/.test(FORM) && /FORM_TTL/.test(FORM));
check("duyệt model.providers", /\(st\.model \|\| \{\}\)\.providers/.test(FN));
check("CANARY: không còn gõ cứng riêng hai nhà Claude + ChatGPT",
  CHAY.indexOf("provider=anthropic-cli") === -1);

// ---- 2. Lọc agent_ok, nhưng KHÔNG lọc configured ----
check("lọc theo agent_ok để không bày lựa chọn hứa suông",
  /filter\(p => p\.agent_ok\)/.test(CHAY));
check("CANARY: không lọc `configured` nữa (nhà chưa cắm key phải hiện ra có ổ khoá)",
  CHAY.indexOf("p.agent_ok && p.configured") === -1);
check("vẫn biết đã kết nối nhà nào để chọn câu dẫn phù hợp",
  /const coKetNoi = provs\.some\(p => p\.configured\)/.test(CHAY));

// ---- 3. Giá trị mang theo tên nhà ----
check("có hằng ngăn cách provider::model", SRC.indexOf('const MODEL_SEP = "::"') !== -1);
check("mỗi dòng model ghép kèm nhà", /const val = \(pid, m\) => pid \+ MODEL_SEP \+ m/.test(FN));
check("lưu thì tách ra thành model + model_provider",
  FN.indexOf("model: mName, model_provider: mProv") !== -1);
check("tách bằng chỉ số ký tự đầu tiên (tên model có thể chứa dấu / hay :)",
  FN.indexOf("raw.indexOf(MODEL_SEP)") !== -1);

// ---- 4. Dùng CHUNG thân bảng với thanh model dưới khung chat ----
check("gọi window.JavisModelList.render, không tự dựng bản thứ hai",
  /window\.JavisModelList\.render\(/.test(CHAY));
check("CANARY: không còn <select> cho model của agent",
  CHAY.indexOf('<select id="agModel">') === -1);
check("vẫn còn một ô mang id agModel để chỗ lưu đọc ra (nay là input ẩn)",
  /id="agModel"/.test(FN) && FN.indexOf('box.querySelector("#agModel").value') !== -1);
check("model-list.js được nạp TRƯỚC studio.js trong index.html",
  HTML.indexOf("/static/model-list.js") !== -1
  && HTML.indexOf("/static/model-list.js") < HTML.indexOf("/static/studio.js"));
check("model-list.js cũng được nạp trước model-picker.js (thanh chat dùng chung)",
  HTML.indexOf("/static/model-list.js") < HTML.indexOf("/static/model-picker.js"));

// ---- 5. Không làm hỏng agent cũ / model đã lưu ----
check("agent CŨ chỉ lưu tên model vẫn dò được đúng nhà (không nhảy về Mặc định)",
  /const doanNha = \(m\) =>/.test(CHAY) && /a\.model_provider\) \|\| doanNha\(mModel\)/.test(CHAY));
check("model đã lưu mà nhà đã ngắt vẫn nói rõ 'đang lưu' (khoá i18n studio.saved_suffix)",
  CHAY.indexOf('t("studio.saved_suffix")') !== -1);
check("vẫn còn lựa chọn Mặc định (khoá i18n studio.model_default)",
  CHAY.indexOf('t("studio.model_default")') !== -1);

// ---- 6. Một nhà lỗi không được kéo cả ô chọn chết; Codex vẫn ép lấy live ----
check("model-list.js nuốt lỗi mạng của một nhà, trả mảng rỗng",
  /catch \(e\) \{\s*CACHE\[pid\] = \{ models: \[\], ts: Date\.now\(\) \};/.test(LIST));
check("Codex vẫn ép lấy danh sách live (catalog của nó vốn rỗng)",
  LIST.indexOf('pid === "openai-oauth" ? "&refresh=1"') !== -1);
check("CANARY: studio KHÔNG còn tự gọi /provider/models (đã uỷ cho model-list.js, nạp lười)",
  CHAY.indexOf("/provider/models") === -1);

// ---- 7. Chưa kết nối nhà nào thì nói thẳng, không để ô trống khó hiểu ----
check("có câu dẫn khi chưa kết nối nhà nào (khoá i18n studio.model_none)",
  CHAY.indexOf('t("studio.model_none")') !== -1);

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_studio_chon_model_agent: tat ca pass");
