/* i18n giao diện: từ điển phải khớp nhau, và file đã dịch KHÔNG được lấm lại tiếng Việt.
 *
 *     python tests/run.py i18n
 *
 * Vì sao có `I18N_MIGRATED`. Việc dịch 3.520 chuỗi giao diện không làm một phát được, nên nó
 * sẽ kéo dài qua nhiều lượt sửa tính năng khác. Không có chốt chặn thì chuyện xảy ra gần như
 * chắc chắn: một lượt sửa tính năng vội nhúng thẳng một chuỗi tiếng Việt vào file vừa dọn,
 * không ai để ý, và vài tháng sau cả file lấm lại như cũ.
 *
 * Test này KHÔNG đòi dịch hết ngay. Nó chỉ đòi: file nào ĐÃ tuyên bố dịch xong thì không được
 * thụt lùi. Dọn tới đâu, thêm tên file vào danh sách tới đó.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const I18N = path.join(ROOT, "dashboard", "i18n");

let loi = 0;
function check(ten, ok, chi_tiet = "") {
  console.log(`${ok ? "ok  " : "FAIL"} ${ten}${ok ? "" : "  " + chi_tiet}`);
  if (!ok) loi++;
}

const doc = (f) => JSON.parse(fs.readFileSync(path.join(I18N, f), "utf8"));
const vi = doc("vi.json");
const en = doc("en.json");

// ---- 1. Khớp key ----
const kVi = Object.keys(vi).sort();
const kEn = Object.keys(en).sort();
const thieu = kVi.filter((k) => !(k in en));
const thua = kEn.filter((k) => !(k in vi));

check("vi.json không rỗng", kVi.length > 20);
// Thiếu key ở bản dịch KHÔNG phải lỗi chết người (nó suy biến về tiếng Việt), nhưng vẫn báo
// để người dịch biết còn nợ gì. Ở giai đoạn này giữ mức cảnh báo cứng cho gọn.
check("en.json không thiếu key nào của vi.json", thieu.length === 0, thieu.slice(0, 8).join(", "));
// Key THỪA thì nguy hiểm hơn: nó nghĩa là bản dịch đang giữ một key đã bị xoá khỏi nguồn,
// hoặc gõ sai tên key - cả hai đều là chữ chết không bao giờ hiện ra.
check("en.json không có key lạ ngoài vi.json", thua.length === 0, thua.slice(0, 8).join(", "));

// ---- 2. Từ điển là DỮ LIỆU, không phải HTML ----
const coThe = (o) => Object.entries(o).filter(([, v]) => /<[a-z/!]/i.test(String(v)));
check("vi.json không chứa thẻ HTML", coThe(vi).length === 0, coThe(vi).map(([k]) => k).join(", "));
check("en.json không chứa thẻ HTML", coThe(en).length === 0, coThe(en).map(([k]) => k).join(", "));

// ---- 3. Chỗ điền {ten} phải khớp giữa hai bản ----
const chua = (v) => (String(v).match(/\{(\w+)\}/g) || []).sort().join(",");
const lechChua = kVi.filter((k) => k in en && chua(vi[k]) !== chua(en[k]));
check("chỗ điền {ten} khớp giữa vi và en", lechChua.length === 0, lechChua.slice(0, 6).join(", "));

// ---- 4. Không em dash (luật toàn dự án) ----
for (const [ten, o] of [["vi.json", vi], ["en.json", en]]) {
  const em = Object.entries(o).filter(([, v]) => String(v).includes("—"));
  check(`${ten} không dùng em dash`, em.length === 0, em.map(([k]) => k).join(", "));
}

// ---- 5. Bản tiếng Anh phải THẬT SỰ được dịch ----
// Chép nguyên tiếng Việt sang en.json thì test khớp key vẫn xanh mà người dùng vẫn thấy
// tiếng Việt. Bắt bằng dấu riêng của tiếng Việt; tên riêng ("Javis", "Telegram") không có dấu
// nên không dính.
const DAU_VIET = /[ăđơưảãạằắẳẵặầấẩẫậẻẽẹềếểễệỉĩịỏõọồốổỗộờớởỡợủũụừứửữựỳỷỹỵ]/i;
const chuaDich = Object.entries(en).filter(([, v]) => DAU_VIET.test(String(v)));
check("en.json không còn chuỗi tiếng Việt", chuaDich.length === 0,
      chuaDich.map(([k]) => k).slice(0, 6).join(", "));

// ---- 6. XƯNG HÔ: dùng "bạn", không dùng "anh" ----
// Javis phục vụ NHIỀU NGƯỜI, không phải một người. Xưng "anh" với người dùng là đoán giới
// tính và đoán quan hệ, và đoán sai với phần lớn người đọc. Chủ repo nói rõ điều này
// (2026-08-14) sau khi thấy chữ "anh" trong chính mấy chuỗi vừa thêm.
//
// Chỉ bắt "anh" đứng RIÊNG làm đại từ. "tiếng Anh", "nước Anh", "giọng Anh" là tên ngôn ngữ
// và quốc gia, hoàn toàn hợp lệ - bắt cả chúng thì test thành thứ phải đi vòng qua.
const XUNG_HO_SAI = /(?<![\p{L}])[Aa]nh(?![\p{L}])/u;
const NGOAI_LE = /(tiếng|nước|người|giọng)\s+[Aa]nh|[Aa]nh\s+ngữ|toàn\s+Anh/iu;
for (const [ten, o] of [["vi.json", vi], ["en.json", en]]) {
  const xau = Object.entries(o).filter(([, v]) => {
    const chuoi = String(v);
    return XUNG_HO_SAI.test(chuoi.replace(NGOAI_LE, ""));
  });
  check(`${ten} xưng "bạn" chứ không xưng "anh" với người dùng`, xau.length === 0,
        xau.map(([k]) => k).join(", "));
}

// ---- 6b. index.html: chữ tiếng Việt tĩnh PHẢI mang data-i18n ----
// Quét xong 0.51.0 thì mọi text node / thuộc tính title-placeholder-aria có dấu Việt trong
// index.html đều đã gắn khoá từ điển. Chốt lại để một dòng HTML thêm sau không lặng lẽ
// đứng ngoài bản dịch. Ngoại lệ là TÊN RIÊNG và chỗ JS tự quản (nút đổi tông do theme.js
// đặt title theo trạng thái sáng/tối - một khoá tĩnh sẽ ghi đè sai một nửa thời gian).
{
  const html = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8")
    .replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>|<!--[\s\S]*?-->/g, "");
  const NGOAI_LE_TEXT = ["Ngọc Thu", "by Minh Quý", "1.10×"];
  const chuaGan = [];
  for (const m of html.matchAll(/<([a-zA-Z0-9]+)((?:[^<>"]|"[^"]*")*)>([^<>]*)/g)) {
    const [, , attrs, text] = m;
    if (DAU_VIET.test(text) && !attrs.includes("data-i18n")
        && !NGOAI_LE_TEXT.some((x) => text.includes(x))) {
      chuaGan.push(text.trim().slice(0, 50));
    }
  }
  check("index.html: text node tiếng Việt nào cũng có data-i18n", chuaGan.length === 0,
        chuaGan.slice(0, 5).join(" | "));

  const attrChuaGan = [];
  for (const m of html.matchAll(/<[a-zA-Z0-9]+((?:[^<>"]|"[^"]*")*)>/g)) {
    const a = m[1];
    if (a.includes('id="themeToggle"')) continue;   // theme.js tự đặt title theo tông
    for (const [att, can] of [["title", "data-i18n-title"], ["placeholder", "data-i18n-ph"],
                              ["aria-label", "data-i18n-aria"]]) {
      const mm = a.match(new RegExp('(?<![-\\w])' + att + '="([^"]*)"'));
      if (mm && DAU_VIET.test(mm[1]) && !a.includes(can)) attrChuaGan.push(`${att}=${mm[1].slice(0, 40)}`);
    }
  }
  check("index.html: title/placeholder/aria tiếng Việt nào cũng có data-i18n-*",
        attrChuaGan.length === 0, attrChuaGan.slice(0, 5).join(" | "));

  // Khoá nhắc trong HTML phải TỒN TẠI trong vi.json - gõ sai tên khoá là chữ trên màn hình
  // bị applyDom thay bằng chính cái khoá sai đó, và không test nào khác nhìn thấy.
  const khoaThieu = [];
  for (const m of html.matchAll(/data-i18n(?:-title|-ph|-aria)?="([^"]+)"/g)) {
    if (!(m[1] in vi)) khoaThieu.push(m[1]);
  }
  check("mọi khoá data-i18n trong index.html đều có trong vi.json", khoaThieu.length === 0,
        khoaThieu.slice(0, 6).join(", "));
}

// ---- 6c. Từ điển KHÔNG được sống sót qua bản cập nhật (khách báo 2026-08-30) ----
// vi.json được fetch không có ?v=, nên thiếu chốt là trình duyệt cache heuristic giữ bản cũ:
// code mới gọi khoá mới, màn hình in nguyên mã khoá kiểu `models.st_connected`. Ba tầng chắn,
// mỗi tầng một canary:
{
  const idx = fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "index.js"), "utf8");
  check("index.js fetch từ điển với cache: no-cache (luôn hỏi lại server, 304 là rẻ)",
        /fetch\("\/static\/i18n\/" \+ ma \+ "\.json", \{ cache: "no-cache" \}\)/.test(idx));
  check("applyDom KHÔNG ghi đè khi thiếu bản dịch (giữ chữ có sẵn thay vì in mã khoá)",
        idx.includes('v === el.getAttribute(attr) ? null : v'));

  const mainPy = fs.readFileSync(path.join(ROOT, "server", "main.py"), "utf8");
  check("server đóng dấu Cache-Control: no-cache cho /static/i18n/*.json",
        mainPy.includes('startswith("/static/i18n/")')
        && mainPy.includes('resp.headers["Cache-Control"] = "no-cache"'));

  // i18n/index.js nạp qua ?v= immutable 1 năm - sửa nội dung file mà quên bump là client cũ
  // giữ bản cũ VĨNH VIỄN. Bản sửa cache này nằm trong v=2, nên v phải >= 2 từ đây trở đi.
  const html = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");
  const mV = html.match(/\/static\/i18n\/index\.js\?v=(\d+)/);
  check("index.html nạp i18n/index.js với v >= 2", mV && parseInt(mV[1], 10) >= 2,
        mV ? mV[0] : "không thấy");
}

// ---- 6d. Mọi khoá t("...") trong JS phải TỒN TẠI trong vi.json ----
// Bản đối xứng của kiểm tra 6b (bên đó lo index.html): gọi một khoá chưa khai là applyDom/t()
// rơi về chính cái khoá, và không test nào khác nhìn thấy cho tới khi người dùng thấy.
{
  const JS_DUNG_T = ["console.js", "studio.js", "theme.js", "app.js", "chat-render.js",
    "sessions-ui.js", "dataview.js", "brains-ui.js", "file-editor.js", "editor-cmds.js",
    "chatbots.js", "model-picker.js", "quick-settings.js", "usage.js", "code-term.js",
    "notifications.js"];
  const thieuJs = [];
  for (const f of JS_DUNG_T) {
    const p = path.join(ROOT, "dashboard", f);
    if (!fs.existsSync(p)) continue;
    const src = fs.readFileSync(p, "utf8");
    for (const m of src.matchAll(/(?<![\w.$])(?:window\.)?t\(\s*"([a-z0-9_.]+)"/g)) {
      if (m[1].includes(".") && !(m[1] in vi)) thieuJs.push(`${f}:${m[1]}`);
    }
  }
  check("mọi khoá t(...) trong JS đều có trong vi.json", thieuJs.length === 0,
        thieuJs.slice(0, 6).join(", "));
}

// ---- 6. CHỐT CHẶN THOÁI LUI ----
// File nào đã dọn xong thì tên nó vào đây. Từ đó trở đi, nhúng một chuỗi tiếng Việt vào file
// đó là test đỏ ngay. Dọn thêm file nào thì thêm tên vào danh sách này.
const I18N_MIGRATED = [
  "dashboard/i18n/index.js",
];

for (const rel of I18N_MIGRATED) {
  const src = fs.readFileSync(path.join(ROOT, rel), "utf8");
  // Bỏ chú thích trước khi soi: giải thích bằng tiếng Việt trong chú thích là chuyện TỐT và
  // là quy ước của repo này. Chỉ mã chạy mới phải sạch.
  const chay = src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((d) => !d.trim().startsWith("//"))
    // Chú thích CUỐI DÒNG cũng phải bóc. Điều kiện "không đứng sau dấu hai chấm" là để
    // không cắt nhầm giữa một URL ("https://..."), chỗ mà hai dấu gạch chéo là dữ liệu
    // chứ không phải chú thích.
    .map((d) => d.replace(/(^|[^:])\/\/.*$/, "$1"))
    .join("\n");
  const dinh = chay.split("\n").map((d, i) => [i + 1, d])
    .filter(([, d]) => DAU_VIET.test(d));
  check(`${rel} không còn chuỗi tiếng Việt trong mã chạy`, dinh.length === 0,
        dinh.slice(0, 3).map(([n, d]) => `${n}: ${d.trim().slice(0, 60)}`).join(" | "));
}

console.log("");
if (loi) {
  console.log(`ĐỎ ${loi} mục`);
  process.exit(1);
}
console.log("Tất cả xanh.");
