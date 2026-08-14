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
