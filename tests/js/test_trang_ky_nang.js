/* Trang Kỹ năng thiết kế lại (0.75.0).

       node tests/js/test_trang_ky_nang.js

   Chủ repo duyệt bản mẫu 05/10/2026. Bốn lỗi cũ mà file này canh không cho quay lại:
   1. Hai ô tick cùng kiểu đứng hai đầu thẻ: ô bật/tắt trông y ô chọn, bấm "chọn" là tắt skill.
   2. Bật/tắt một skill ở trang 3 thì nhảy về trang 1 (vẽ lại cả trang, pager quên số trang).
   3. Nhóm trùng tên ("ai" cạnh "AI", "vận-hành" cạnh "Vận hành") vì ô nhóm gõ tự do.
   4. Mô tả quá 150 ký tự: router cắt im lặng, server từ chối lưu mà form nuốt lỗi.
*/
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const STUDIO = fs.readFileSync(path.join(ROOT, "dashboard", "studio.js"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

const fails = [];
const check = (name, cond, extra) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra !== undefined ? "  [" + extra + "]" : ""));
  if (!cond) fails.push(name);
};
const cat = (tu, den) => {
  const i = STUDIO.indexOf(tu), j = STUDIO.indexOf(den, i + 1);
  if (i < 0 || j < 0) throw new Error("không tìm thấy đoạn: " + tu + " .. " + den);
  return STUDIO.slice(i, j);
};

// ============================================================
// A. Gộp nhóm trùng tên - chạy thật
// ============================================================
const KHOI_NHOM = cat("  function _spNoAccent(s) {", "  function demNhom(items)")
  + "\n const NHOM_MD = \"Chung\";\n const nhomCua = (x) => (x && String(x.group || \"\").trim()) || NHOM_MD;\n"
  + cat("  const _khoaNhom = ", "  const _nhomDangCo = ");
const G = new Function(KHOI_NHOM + "\n return { gopNhomSkill, _khoaNhom };")();

const DS = [
  { slug: "a1", group: "AI" }, { slug: "a2", group: "AI" }, { slug: "a3", group: "ai" },
  { slug: "v1", group: "Vận hành" }, { slug: "v2", group: "vận-hành" }, { slug: "v3", group: "Vận hành" },
  { slug: "b1", group: "Bán hàng" }, { slug: "c1" }, { slug: "c2", group: "  " },
];
const gop = G.gopNhomSkill(DS);
const nhomCuaSlug = (sl) => DS.find((s) => s.slug === sl).group;
check("'ai' gộp về 'AI' (bản đông hơn)", nhomCuaSlug("a3") === "AI", nhomCuaSlug("a3"));
check("'vận-hành' gộp về 'Vận hành'", nhomCuaSlug("v2") === "Vận hành", nhomCuaSlug("v2"));
check("nhóm không trùng giữ nguyên", nhomCuaSlug("b1") === "Bán hàng");
check("thiếu nhóm vẫn về Chung", nhomCuaSlug("c1") === "Chung" && nhomCuaSlug("c2") === "Chung");
check("giữ tên gốc trong file để form biết", DS.find((s) => s.slug === "a3").groupRaw === "ai");
check("báo lại đã gộp những gì", gop.length === 2 && gop.includes("ai → AI") && gop.includes("vận-hành → Vận hành"), gop.join(" | "));
const HOA = [{ slug: "x", group: "marketing" }, { slug: "y", group: "Marketing" }];
G.gopNhomSkill(HOA);
check("hoà số lượng thì ưu tiên tên viết hoa", HOA.every((s) => s.group === "Marketing"), HOA.map((s) => s.group).join());
const DAU = [{ slug: "x", group: "Van hanh" }, { slug: "y", group: "Vận hành" }];
G.gopNhomSkill(DAU);
check("hoà số lượng thì ưu tiên tên có dấu", DAU.every((s) => s.group === "Vận hành"), DAU.map((s) => s.group).join());

// ============================================================
// B. Đọc mục "Dùng khi nào" trong SKILL.md - chạy thật
// ============================================================
const P = new Function(cat("  function phanDungKhiNao(body) {", "  function veChiTiet()") + "\n return phanDungKhiNao;")();
const THAN = "# Viết email\n\n## When to use\n- Khi cần **email** bán hàng\n* Khi chăm khách `cũ`\n1. Khi ra mắt sản phẩm\n\n## Cách làm\n- Bước một\n";
const W = P(THAN);
check("lấy đúng ba gạch đầu dòng của mục When to use", W.length === 3, JSON.stringify(W));
check("bỏ ký hiệu markdown trong gạch đầu dòng", W[0] === "Khi cần email bán hàng" && W[1] === "Khi chăm khách cũ", JSON.stringify(W));
check("dừng ở tiêu đề kế tiếp", !W.includes("Bước một"));
check("nhận cả tiêu đề tiếng Việt", P("### Dùng khi nào\n- A\n").join() === "A");
check("không có mục thì trả rỗng", P("Chỉ có thân bài.\n- gạch\n").length === 0);
check("CANARY: mục 'Dùng khi nào' ẩn được dù khối mục là flex (hidden không bị display đè)",
  /\.sk3-d-sec\[hidden\]\{display:none\}/.test(STUDIO));

// ============================================================
// C. Thẻ skill: một ô CHỌN để xuất + một CÔNG TẮC bật/tắt, không còn hai ô tick
// ============================================================
const THE = cat("  function theSkill(s) {", "  function capNhatChonTatCa(");
check("CANARY: không còn ô tick bật/tắt kiểu cũ (sk2-tog)", STUDIO.indexOf("sk2-tog") === -1);
check("bật/tắt là công tắc role=switch có aria-checked", /class="sk3-sw" role="switch" aria-checked="\$\{on\}"/.test(THE));
check("ô chọn để xuất luôn có trên thẻ (không phải bật chế độ chọn mới thấy)", THE.indexOf('class="sk2-sel"') !== -1);
check("skill hệ thống: ô chọn bị khoá kèm lời giải thích", /s\.system \? " disabled" : ""/.test(THE) && THE.indexOf("studio.sk_pick_sys") !== -1);
check("bấm thân thẻ mở khung chi tiết", /\.sk3-main"\)\.onclick = \(\) => moChiTiet\(s\.slug\)/.test(THE));
check("tick đổi thì thanh xuất cập nhật", /selBox\.addEventListener\("change", veThanhChon\)/.test(THE));
check("cảnh báo mô tả quá trần ngay trên thẻ", /_doDai\(s\.description\) > SKILL_DESC_MAX/.test(THE));
check("không in 'chưa thấy dùng' lên thẻ khi chưa có số liệu", THE.indexOf("studio.unused") === -1);

// ============================================================
// D. Bật/tắt không vẽ lại cả trang (giữ trang đang xem)
// ============================================================
const TOG = cat("  async function toggleSkill(s, enabled) {", "  function capNhatMotThe(s)");
check("CANARY: bật/tắt KHÔNG gọi renderSkillUI (vẽ lại cả trang = về trang 1)", TOG.indexOf("renderSkillUI(") === -1);
check("bật/tắt chỉ thay đúng một thẻ", TOG.indexOf("capNhatMotThe(s)") !== -1);
check("lỗi bật/tắt thì KHÔNG đổi trạng thái trên màn hình", /if \(!r \|\| !r\.ok\) \{[\s\S]*?\} else \{\s*s\.enabled = enabled;/.test(TOG));
check("đổi nhóm/ô tìm/bộ lọc thì về trang 1", /veLai: \(\) => \{ _skState\.page = 0; renderSkillUI\(\); \}/.test(STUDIO)
  && /veDanhSach: \(\) => \{ _skState\.page = 0; renderSkillList\(\); \}/.test(STUDIO));

// ============================================================
// E. Lọc, sắp xếp, chọn nhiều để xuất
// ============================================================
check("có lọc theo trạng thái Tất cả / Đang bật / Đang tắt / Hệ thống",
  /\["all", "studio\.sk_st_all"\], \["on", "studio\.sk_st_on"\],\s*\["off", "studio\.sk_st_off"\], \["system", "studio\.sk_st_sys"\]/.test(STUDIO));
check("có sắp xếp theo hay dùng / tên / đang tắt", /\["used", "studio\.sk_sort_used"\], \["name", "studio\.sk_sort_name"\], \["off", "studio\.sk_sort_off"\]/.test(STUDIO));
check("ô Chọn tất cả gom cả danh sách đang lọc, trừ skill hệ thống",
  /const ds = _skFiltered\(\)\.filter\(s => !s\.system\)\.map\(s => s\.slug\);/.test(STUDIO));
check("CANARY: Chọn tất cả chỉ thêm/bớt phần đang hiện, không xoá lựa chọn ở nhóm khác",
  /ds\.forEach\(sl => \{ if \(du\) _sel\.skill\.delete\(sl\); else _sel\.skill\.add\(sl\); \}\);/.test(STUDIO)
  && !/chonTatCa\("skill"/.test(STUDIO));
check("ô Chọn tất cả có trạng thái chọn một phần", /el\.indeterminate = n > 0 && n < ds\.length;/.test(STUDIO));
check("thanh xuất gọi đúng đường tải gói chung", /skBulkExport"\)\.onclick = \(\) => taiDaChon\("skill"\)/.test(STUDIO));
check("bật/tắt cả loạt chạy tuần tự rồi tải lại mà giữ vị trí", /for \(const s of ds\) \{/.test(STUDIO) && /await taiLaiGiuViTri\(\);/.test(STUDIO));

// ============================================================
// F. Form: đếm 150 ký tự + hiện lỗi server thay vì nuốt
// ============================================================
check("trần mô tả khai một chỗ", /const SKILL_DESC_MAX = 150;/.test(STUDIO));
const FORM = cat("  async function openSkillForm(slug) {", "  async function deleteSkill(");
check("ô mô tả đếm ký tự khi gõ", /desc\.oninput = demMoTa;/.test(FORM));
check("vượt trần thì chặn lưu ngay ở form", /if \(demMoTa\(\)\) \{ desc\.focus\(\); return; \}/.test(FORM));
check("CANARY: lỗi server hiện ra trong form, không đóng form như đã lưu", /if \(!r \|\| r\.error \|\| r\.ok === false\) \{\s*baoLoi\(/.test(FORM));
check("nhóm là ô chọn từ nhóm đang có + Nhóm mới", /<select id="skGroupSel"/.test(FORM) && FORM.indexOf('value="__new__"') !== -1);
check("nhóm trùng tên trong file được chọn về tên chuẩn", /nhoms\.find\(g => _khoaNhom\(g\) === khoa\)/.test(FORM));
check("có Soạn / Xem trước", FORM.indexOf('data-tab="preview"') !== -1 && /window\.mdToHtml/.test(FORM));

// ============================================================
// G. Chữ trên màn hình có đủ hai thứ tiếng
// ============================================================
const khoa = [...new Set([...STUDIO.matchAll(/t\("(studio\.sk_[a-z0-9_]+)"/g)].map((m) => m[1]))];
const thieu = khoa.filter((k) => !VI[k] || !EN[k]);
check("mọi khoá studio.sk_* dùng trong studio.js có ở cả vi.json và en.json", thieu.length === 0, thieu.join(", "));
check("dùng nhiều khoá mới (test không rỗng)", khoa.length >= 30, khoa.length);

if (fails.length) {
  console.log("\nFAIL - test_trang_ky_nang: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_trang_ky_nang: tất cả pass");
