/* Cột nhóm cho trang Agents và Workflows, dùng CHUNG khung với trang Skills.

       node tests/js/test_nhom_agent_workflow.js

   Trang Skills có cột nhóm từ lâu; Agents và Workflows thì không, nên brain dùng vài tháng
   là hai danh sách phẳng vài chục dòng phải dò bằng mắt. Việc này mở cột nhóm cho cả hai.

   Điều đáng canh KHÔNG phải là "có cột nhóm hay chưa" mà là CÓ ĐÚNG MỘT khung. Chép khung
   lọc ra ba bản cho ba trang thì ba bản trôi lệch nhau ngay lần sửa đầu tiên: sửa cách bỏ
   dấu ở trang này, quên hai trang kia, và người dùng gặp một trang tìm được "viet email"
   còn trang bên cạnh thì không. Đây đúng là bài học của khối chọn skill trong màn sửa Agent
   (xem test_chon_skill_va_phan_trang.js), nên phần lớn test này canh chuyện dùng chung.

   Phần cuối canh một bẫy MẤT CHỮ trong form sửa Workflow: render() chạy lại mỗi lần thêm
   hoặc xoá bước, nên ô nào lấy value từ `w` sẽ bị vẽ đè về giá trị cũ, im lặng. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "studio.js"), "utf8");

const fails = [];
const check = (name, cond, extra) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
};

// ============================================================
// A. Chạy THẬT khung nhóm dùng chung (không chỉ soi chữ trong file)
// ============================================================
// Bóc đúng khối dùng chung rồi chạy nó với vài hàm giả (t/ic/LOC), để test bắt được lỗi
// hành vi chứ không chỉ lỗi thiếu chữ.
const i0 = SRC.indexOf("  const NHOM_MD =");
const i1 = SRC.indexOf("  function switchTab(");
check("tìm thấy khối khung nhóm dùng chung", i0 !== -1 && i1 > i0);

const esc = (s) => (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const KHOI = SRC.slice(i0, i1);
const M = new Function("esc", "t", "ic", "LOC", KHOI +
  "\n return { NHOM_MD, nhomCua, demNhom, locTheoNhom, khungNhomHtml, nhomDatalist };")(
  esc, (k) => k, () => "", () => "vi-VN");

check("nhóm mặc định là Chung", M.NHOM_MD === "Chung");
check("thiếu group → Chung", M.nhomCua({ name: "a" }) === "Chung");
check("group rỗng/toàn khoảng trắng → Chung", M.nhomCua({ group: "   " }) === "Chung");
check("group có khoảng trắng thừa được cắt", M.nhomCua({ group: " Marketing " }) === "Marketing");

const DS = [
  { slug: "viet-email", name: "Viết email", group: "Marketing", role: "soạn email" },
  { slug: "chot-don", name: "Chốt đơn", group: "Bán hàng", role: "trả lời khách" },
  { slug: "cu", name: "Agent cũ", role: "chưa xếp nhóm" },
];
const dem = M.demNhom(DS);
check("đếm theo nhóm đúng", dem["Marketing"] === 1 && dem["Bán hàng"] === 1 && dem["Chung"] === 1, JSON.stringify(dem));

const blob = (a) => `${a.name} ${a.slug} ${a.role || ""}`;
check("nhóm ALL không lọc gì", M.locTheoNhom(DS, { cat: "ALL", q: "" }, blob).length === 3);
check("lọc đúng nhóm", M.locTheoNhom(DS, { cat: "Bán hàng", q: "" }, blob).map(x => x.slug).join() === "chot-don");
check("mục chưa xếp nhóm nằm trong Chung (không biến mất)",
  M.locTheoNhom(DS, { cat: "Chung", q: "" }, blob).map(x => x.slug).join() === "cu");
// Gõ không dấu vẫn ra: người dùng gõ nhanh trên điện thoại hiếm khi bỏ dấu đầy đủ.
check("tìm không dấu ra kết quả có dấu", M.locTheoNhom(DS, { cat: "ALL", q: "viet email" }, blob).length === 1);
check("tìm hoạt động cùng lúc với lọc nhóm",
  M.locTheoNhom(DS, { cat: "Marketing", q: "chot" }, blob).length === 0);

const html = M.khungNhomHtml(DS, { cat: "ALL", q: "" },
  { bodyId: "agCards", bodyCls: "cards", searchId: "agSearch", searchPh: "tìm" });
check("khung có đủ chip nhóm", html.includes("Marketing") && html.includes("Bán hàng") && html.includes("Chung"));
check("khung có ô tìm đúng id", html.includes('id="agSearch"'));
check("khung chừa chỗ cho danh sách của từng trang", html.includes('id="agCards"') && html.includes('class="cards"'));
check("chip ALL đếm đúng tổng số", /data-cat="ALL"[\s\S]*?<span class="n">3</, html.match(/data-cat="ALL"[\s\S]{0,120}<span class="n">3</) !== null);

// Tên nhóm do người dùng gõ vào frontmatter, nên nó là chữ NGƯỜI LẠ có thể gửi qua gói .zip
// chia sẻ năng lực. Nhét thẳng vào innerHTML là một lỗ XSS.
const hiem = M.khungNhomHtml([{ slug: "x", name: "x", group: '<img src=x onerror=alert(1)>' }],
  { cat: "ALL", q: "" }, { bodyId: "b", searchId: "s", searchPh: "" });
check("tên nhóm được escape trước khi vào HTML", !hiem.includes("<img src=x"));
check("gợi ý nhóm trong form cũng escape", !M.nhomDatalist([{ group: '"><script>' }], "l").includes("<script>"));

// ============================================================
// B. CẢ BA trang dùng đúng MỘT khung đó
// ============================================================
check("khung nhóm chỉ có MỘT bản", (SRC.match(/function khungNhomHtml\(/g) || []).length === 1);
for (const [trang, state, oId] of [["Workflows", "_wfState", "wfSearch"],
                                   ["Agents", "_agState", "agSearch"],
                                   ["Skills", "_skState", "skSearch"]]) {
  check(`trang ${trang} có trạng thái nhóm + ô tìm riêng`,
    SRC.includes(`const ${state} = { cat: "ALL", q: ""`) && SRC.includes(`searchId: "${oId}"`));
  check(`trang ${trang} vẽ bằng khung chung`,
    new RegExp(`khungNhomHtml\\(all, ${state},`).test(SRC));
  check(`trang ${trang} nối sự kiện bằng hàm chung`,
    new RegExp(`ganKhungNhom\\(panel, ${state},`).test(SRC));
}
// Không còn khung riêng của trang Skills (lớp .sk2 cũ) sống song song với khung chung.
check("CANARY: không còn khung nhóm riêng của trang Skills", !SRC.includes('class="sk2-side"'));

check("thẻ agent hiện nhóm của nó", SRC.includes('class="ag-group"'));
check("hàng workflow hiện nhóm của nó", SRC.includes('class="wf-group"'));
check("bấm Chọn tất cả chỉ lấy mục ĐANG HIỆN (đúng nhóm + đúng ô tìm)",
  SRC.includes("_wfFiltered().map(w => w.slug)") && SRC.includes("_agFiltered().map(a => a.slug)"));

// ============================================================
// C. Form: chọn nhóm được, và gửi kèm lúc lưu
// ============================================================
for (const [ten, oId, list] of [["Agent", "agGroup", "agGroupList"], ["Workflow", "wfGroup", "wfGroupList"]]) {
  check(`form ${ten} có ô nhập nhóm`, SRC.includes(`id="${oId}"`));
  check(`form ${ten} gợi ý nhóm đang có (khỏi đẻ Marketing và marketing song song)`,
    SRC.includes(`nhomDatalist(`) && SRC.includes(`"${list}"`));
}
check("lưu Agent gửi kèm group", /group: box\.querySelector\("#agGroup"\)\.value\.trim\(\) \|\| NHOM_MD/.test(SRC));
check("lưu Workflow gửi kèm group", /group: nhom\.trim\(\) \|\| NHOM_MD/.test(SRC));

// ---- Bẫy mất chữ trong form Workflow ----
// render() chạy lại mỗi lần thêm/xoá/đảo bước. Ô nào đọc value từ `w` sẽ bị vẽ đè về giá trị
// cũ: gõ tên workflow rồi bấm "+ Bước" là mất tên, không một thông báo nào.
const iw = SRC.indexOf("async function editWorkflow(");
const FNW = SRC.slice(iw, SRC.indexOf("\n  // ===== Agents =====", iw));
check("form Workflow giữ tên/mô tả/nhóm trong biến, không đọc lại từ w mỗi lần vẽ",
  /let ten = w \? \(w\.name \|\| ""\) : "";/.test(FNW) && /let nhom = w \? nhomCua\(w\) : NHOM_MD;/.test(FNW));
check("captureSteps() hứng cả ba ô trước khi vẽ lại",
  /if \(oNe\) ten = oNe\.value;/.test(FNW) && /if \(oNh\) nhom = oNh\.value;/.test(FNW));
check("CANARY: ô tên/mô tả không còn lấy giá trị thẳng từ w",
  !FNW.includes('value="${esc(w ? w.name : "")}"') && !FNW.includes('value="${esc(w ? w.description : "")}"'));

if (fails.length) {
  console.log(`\nFAIL ${fails.length} muc: ` + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_nhom_agent_workflow: tat ca pass");
