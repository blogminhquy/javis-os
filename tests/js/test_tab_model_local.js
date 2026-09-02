/* Trang Models tách hai tab, và tab "chạy trên máy" không lặp lại giả định sai của bản demo.

       node tests/js/test_tab_model_local.js

   Bản demo HTML ban đầu có nút "Cài Ollama" tự chạy script và ba trạng thái (chưa cài / đang
   cài / đã cài). Nó chỉ đúng khi Javis và Ollama là CÙNG MỘT máy vật lý. Phần đông người dùng
   chạy Javis trong Docker/VPS, nơi Javis không có quyền - và cũng không có đường - chạy lệnh
   cài trên máy vật lý của người ta. Đây đúng là lý do provider ollama local bị chặn cố ý từ
   đầu (server/config.py), nên file này canh để bản thật không lặp lại nó. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const JS = D("console.js");
const CSS = D("console.css");
const VI = JSON.parse(D(path.join("i18n", "vi.json")));
const EN = JSON.parse(D(path.join("i18n", "en.json")));

const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
};

// Chỉ soi phần tab Local, không soi cả file.
const i = JS.indexOf("// ===== Trang Models: hai tab =====");
const j = JS.indexOf("  async function renderModelsCloudTab(el) {");
check("tìm được khối tab Local", i > 0 && j > i);
const OL = JS.slice(i, j);

// ============================================================
// 1. Tách tab mà KHÔNG đẻ ra tab lồng tab
// ============================================================
check("có thanh hai tab", /class="mtabs"/.test(OL) && /data-mtab="\$\{k\}"/.test(OL)
  && /tab\("cloud",/.test(OL) && /tab\("local",/.test(OL));
check("khung Cloud cũ thành một hàm riêng", /async function renderModelsCloudTab\(el\)/.test(JS));
// renderModels giờ vẽ CẢ thanh tab. Để nguyên các lời tự vẽ lại bên trong khung Cloud gọi
// renderModels(el) là mỗi lần đổi model lại mọc thêm một thanh tab bên trong khung.
check("khung Cloud tự vẽ lại bằng chính nó, không gọi ngược renderModels",
  !/renderModels\(el\)/.test(JS.slice(j)), "còn lời gọi ngược trong khung Cloud");
check("tab đang chọn giữ ở biến module, không đẩy lên server",
  /let _modelTab = "cloud";/.test(OL) && !/fetch\([^)]*modelTab/.test(OL));

// ============================================================
// 2. KHÔNG lặp lại giả định "Javis cài hộ trên máy bạn"
// ============================================================
// Lệnh cài CÓ mặt (dạng chữ để người dùng tự chép), nhưng KHÔNG được có đường nào để bấm
// một nút rồi Javis chạy nó hộ - đó mới là giả định sai.
check("CANARY: không có nút tự cài Ollama nào",
  !/\/ollama-local\/install(?![a-z])/.test(OL) && !/btnInstallOllama/.test(JS)
  && !/ol-cai\b|installOllama/.test(OL));
check("chỉ HIỆN lệnh cài để người dùng tự chạy, kèm nút chép",
  /OL_LENH/.test(OL) && /ol-copy/.test(OL) && /clipboard\.writeText/.test(OL));
check("có lệnh cho cả ba nền tảng", /linux:/.test(OL) && /mac:/.test(OL) && /windows:/.test(OL));
// Bản demo có ba trạng thái vì có bước "đang cài". Bỏ nút cài thì bước đó cũng không còn.
check("chỉ còn HAI trạng thái, không còn 'đang cài'",
  /olVeChuaNoi/.test(OL) && /olVeDaNoi/.test(OL) && !/installing|dangCai/.test(OL));
// Đây là câu quan trọng nhất cả tab: trong Docker, "máy này" là container chứ không phải máy
// người dùng. Nói sai câu này là người dùng cài Ollama vào đúng chỗ vô dụng.
check("Docker được nói RIÊNG, không dùng chung câu với native",
  /st\.deploy_mode === "docker"/.test(OL) && VI["ol.note_docker"] !== VI["ol.note_native"]);
check("và câu đó nói rõ container không phải máy bạn",
  /container/.test(VI["ol.note_docker"] || "") && /container/i.test(EN["ol.note_docker"] || ""));

// 02/09: chủ repo dán thẳng lệnh cài vào TERMINAL CỦA JAVIS và ăn "requires superuser". Dễ
// hiểu - nút copy nằm ngay cạnh mà app thì có sẵn một terminal. Nhưng kể cả cài đúng máy vẫn
// còn hai bức tường nữa, và thiếu một trong hai là "không nối được" mà không hiểu vì sao.
check("bản Docker nói THẲNG là đừng dùng terminal của Javis",
  /terminal/i.test(VI["ol.dk_b1"] || "") && /root/i.test(VI["ol.dk_b1"] || ""));
check("và nói rõ cài vào container thì mất sạch khi cập nhật",
  /cập nhật/i.test(VI["ol.dk_b1"] || ""));
// Ollama mặc định chỉ nghe 127.0.0.1 - container không bao giờ với tới.
check("có bước cho Ollama nghe ra ngoài loopback",
  /OLLAMA_HOST=0\.0\.0\.0/.test(OL) && !!VI["ol.dk_b3"]);
// Không ai đoán được địa chỉ cầu nối Docker, mà bản cũ lại ĐOÁN HỘ SAI: hằng
// OL_DIA_CHI_DOCKER viết cứng 172.17.0.1, tức cổng của mạng bridge MẶC ĐỊNH (docker0). Javis
// cài bằng docker-compose thì nằm trên mạng riêng của project, dải cấp từ 172.18.0.0/16 trở
// đi, nên người dùng điền y như hướng dẫn vẫn không nối được. Server phải DÒ cổng thật.
// Soi phần MÃ THẬT: dòng chú thích vẫn được nhắc lại con số cũ để giải thích vì sao nó sai,
// nhưng nhắc trong chú thích thì không ai điền nhầm được.
const OL_MA = OL.replace(/^\s*\/\/.*$/gm, "");
check("không còn đoán bừa địa chỉ cầu nối bằng số viết cứng",
  !/OL_DIA_CHI_DOCKER\s*=/.test(OL_MA) && !/172\.17\.0\.1/.test(OL_MA));
check("địa chỉ lấy từ server (goi_y_endpoint) chứ không tự chế ở giao diện",
  /st\.goi_y_endpoint/.test(OL));
// 02/09: chủ repo thấy câu "điền địa chỉ này" mà không biết địa chỉ nào - vì nó nằm trong chữ
// xám placeholder, trông như gợi ý chứ không như giá trị, lại bị ô hẹp cắt cụt giữa chừng.
check("và điền THẲNG vào ô nhập, không để trong chữ xám",
  /st\.goi_y_endpoint \? ' value="' \+ esc\(st\.goi_y_endpoint\)/.test(OL));
check("câu hướng dẫn nói là đã điền sẵn, không bắt người dùng tự tìm",
  /điền sẵn/.test(VI["ol.dk_b4"] || ""));
// Dò hụt (mạng Docker lạ, --network=host) mà để ô trống và im lặng là ngõ cụt.
check("dò không ra thì nói thẳng và đưa đúng một lệnh tự tìm",
  /ol\.dk_khong_do_duoc/.test(OL) && /ip route/.test(OL) && !!VI["ol.dk_khong_do_duoc"]);
// Bảo người ta mở 0.0.0.0 mà không nói nó nghe cả từ Internet, và KHÔNG có mật khẩu, là đẩy
// họ vào chỗ hở một máy chủ model công khai.
check("cảnh báo bảo mật khi mở 0.0.0.0, kèm lệnh tường lửa cụ thể",
  /mật khẩu/.test(VI["ol.dk_canh_bao"] || "") && /ufw/.test(VI["ol.dk_canh_bao"] || ""));
// VPS phổ thông không GPU, ít RAM. Không nói trước là để người ta tải 5GB rồi mới thất vọng.
check("nói thẳng VPS chạy model local sẽ chậm",
  /chậm/.test(VI["ol.dk_cham"] || "") && /GPU/.test(VI["ol.dk_cham"] || ""));

// ============================================================
// 3. Nối đúng endpoint backend
// ============================================================
for (const ep of ["/ollama-local/status", "/ollama-local/endpoint", "/ollama-local/specs",
                  "/ollama-local/installed", "/ollama-local/recommended",
                  "/ollama-local/search", "/ollama-local/pull", "/ollama-local/delete"]) {
  check("gọi " + ep, OL.includes(ep));
}
// Ollama không có API huỷ; huỷ = đóng luồng, và lần tải sau tự tiếp tục từ chỗ dở.
check("huỷ tải bằng cách đóng luồng, không gọi endpoint huỷ",
  /AbortController/.test(OL) && !OL.includes("/pull/cancel"));
check("huỷ xong trả thẻ về nút Tải để bấm lại được", /olNoiNutTai\(act, xong\)/.test(OL));
check("tiến độ đọc từ SSE và bỏ qua mốc đóng luồng",
  /startsWith\("data: "\)/.test(OL) && /"__done__"/.test(OL));

// ============================================================
// 4. Đổi cấu hình máy thì gợi ý phải đổi theo
// ============================================================
// Gợi ý ăn theo specs. Lưu specs xong mà không vẽ lại gợi ý thì màn hình đang nói dối.
check("lưu cấu hình xong vẽ lại CẢ phần gợi ý",
  /await olVeSpecs\(el\);\s*\n\s*await olVeGoiY\(el\);/.test(OL));
check("khai tay được nói rõ là thắng số tự đọc",
  /ưu tiên hơn/.test(VI["ol.specs_hint"] || ""));
check("chưa biết cấu hình thì nói thẳng, không đoán bừa",
  /ol\.specs_unknown/.test(OL) && /mức an toàn/.test(VI["ol.specs_unknown"] || ""));
check("mỗi thẻ model hiện lý do nó được gợi ý", /ol-card-note/.test(OL) && /m\.note/.test(OL));

// ============================================================
// 5. i18n + icon
// ============================================================
const khoa = [...new Set((OL.match(/t\("([\w.]+)"/g) || []).map(s => s.slice(3, -1)))];
check("chuỗi đi qua t()", khoa.length > 30, String(khoa.length));
const thieuVi = khoa.filter(k => !(k in VI));
const thieuEn = khoa.filter(k => !(k in EN));
check("mọi khoá có trong vi.json", thieuVi.length === 0, thieuVi.join(", "));
check("và trong en.json", thieuEn.length === 0, thieuEn.join(", "));
// Icon thiếu là icon VÔ HÌNH - lỗi rất khó thấy bằng mắt.
const MAN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "icons.manifest.json"), "utf8"));
const co = new Set(Object.values(MAN.groups).flat());
const icDung = [...new Set((OL.match(/ic\("([a-z0-9-]+)"/g) || []).map(s => s.slice(4, -1)))];
check("mọi icon dùng ở đây đều có thật", icDung.every(n => co.has(n)),
  icDung.filter(n => !co.has(n)).join(", "));
check("có CSS cho thanh tab và tab local", /\.mtabs \{/.test(CSS) && /\.ol-card \{/.test(CSS));

console.log("");
if (fails.length) { console.log("ĐỎ " + fails.length + " mục"); process.exit(1); }
console.log("Tất cả xanh.");
