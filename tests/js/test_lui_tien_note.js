/* Lùi / Tiến giữa các note trong trình sửa của Javis.

       node tests/js/test_lui_tien_note.js

   Vì sao có file này. Đọc wiki là đi theo chuỗi [[wikilink]]: bấm một cái là rời khỏi note
   đang đọc. Trước bản này KHÔNG có đường về - phải đi tìm lại file cũ trong cây, nên mỗi cú
   bấm link là một quyết định một chiều.

   Ba thứ file này canh, vì cả ba đều thuộc loại hỏng ÂM THẦM:

     1. Luật cắt nhánh TIẾN. Đang đứng giữa vệt mà mở một note mới thì phần phía trước phải
        rụng, y như trình duyệt. Quên cắt thì bấm Tiến nhảy sang một nhánh người ta đã bỏ, và
        không ai đoán ra vì sao lại tới đó.
     2. Chữ đang gõ dở. Rời file mà chưa lưu là mất bài, không một lời báo. Nút Lùi/Tiến làm
        chuyện rời file xảy ra thường xuyên hơn hẳn, nên đây thành cái bẫy nếu không vá.
        Và lưu HỎNG thì phải Ở LẠI - đi tiếp lúc đó là vứt bài người ta vừa viết.
     3. Vệt trỏ vào file đã đổi tên / đã xoá / thuộc brain cũ. Bấm Lùi rơi vào đường dẫn không
        còn tồn tại.

   Luật đi vệt được tách thành hàm THUẦN `_neVetMoi` nên test gọi thẳng vào nó (moi mã nguồn
   ra chạy trong vm), không phải dựng cả DOM. Phần còn lại kiểm ở mức mã nguồn. */
const fs = require("fs");
const path = require("path");
const vm = require("node:vm");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const CON = D("console.js");
const CSS = D("style.css");
const HTML = D("index.html");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Luật đi vệt - chạy THẬT hàm trong console.js
// ============================================================
const dau = CON.indexOf("function _neVetMoi(");
const cuoi = CON.indexOf("\n  }", dau);
check("moi được hàm luật đi vệt ra khỏi console.js", dau > 0 && cuoi > dau);
const src = CON.slice(dau, cuoi + 4);
const vetMoi = vm.runInNewContext(src + "; _neVetMoi", {});

const nut = (r) => ({ rel: r, name: r.split("/").pop(), ext: ".md" });
const di = (st, r, max) => vetMoi(st.lichSu, st.viTri, nut(r), max || 50);

let st = { lichSu: [], viTri: -1 };
st = di(st, "a.md");
check("mở note đầu tiên -> vệt có 1 bước, đang đứng ở đó",
  st.lichSu.length === 1 && st.viTri === 0);

st = di(st, "b.md");
st = di(st, "c.md");
check("đi tiếp 2 note -> vệt a,b,c và đứng ở c",
  st.lichSu.map(n => n.rel).join(",") === "a.md,b.md,c.md" && st.viTri === 2);

// Bấm lại chính file đang đứng (vd bấm lại nó trong cây) thì không đẻ thêm bước.
st = di(st, "c.md");
check("mở lại đúng file đang đứng -> không đẻ thêm bước",
  st.lichSu.length === 3 && st.viTri === 2);

// Lùi hai bước rồi mở note MỚI: nhánh tiến (b, c) phải rụng.
st.viTri = 0;
st = di(st, "z.md");
check("CANARY: lùi rồi mở note mới -> nhánh TIẾN bị cắt",
  st.lichSu.map(n => n.rel).join(",") === "a.md,z.md" && st.viTri === 1);

// Lùi rồi mở LẠI đúng note đang đứng thì không cắt gì (vì rơi vào luật 1).
let st2 = { lichSu: [nut("a.md"), nut("b.md"), nut("c.md")], viTri: 1 };
st2 = di(st2, "b.md");
check("lùi rồi mở lại chính nó -> giữ nguyên nhánh tiến",
  st2.lichSu.length === 3 && st2.viTri === 1);

// Trần: vệt là để quay lại chỗ vừa đọc, không phải nhật ký cả phiên.
let st3 = { lichSu: [], viTri: -1 };
for (let i = 0; i < 8; i++) st3 = di(st3, `n${i}.md`, 3);
check("quá trần -> rụng đầu, giữ đúng số bước", st3.lichSu.length === 3);
check("quá trần -> giữ mấy bước GẦN NHẤT",
  st3.lichSu.map(n => n.rel).join(",") === "n5.md,n6.md,n7.md" && st3.viTri === 2);

// Đường dẫn rỗng không được làm bẩn vệt.
const st4 = vetMoi([nut("a.md")], 0, { rel: "" }, 50);
check("bước rỗng bị bỏ qua", st4.lichSu.length === 1 && st4.viTri === 0);

// ============================================================
// 2. Nút bấm: MỜ chứ không ẩn, và tooltip GỌI TÊN file sẽ tới
// ============================================================
check("có khung riêng cho nút Lùi/Tiến trong thanh tiêu đề", HTML.indexOf('id="neNav"') > 0);
check("nút Lùi/Tiến đứng TRƯỚC tên file (đúng chỗ trình duyệt để nó)",
  HTML.indexOf('id="neNav"') < HTML.indexOf('id="neTitle"'));

const ve = CON.slice(CON.indexOf("function _neVeNutLui()"), CON.indexOf("async function _neDiLichSu("));
check("hết chỗ đi thì MỜ nút chứ không tháo nút", ve.indexOf("b.disabled = !dich") >= 0);
check("tooltip gọi TÊN file sẽ tới, không phải chữ 'Lùi' trơn",
  /\$\{nhan\}: \$\{dich\.name\}/.test(ve));
check("nút trống vẫn nói được vì sao bấm không ăn", ve.indexOf("khiTrong") >= 0);
check("có nhãn cho trình đọc màn hình", ve.indexOf('setAttribute("aria-label"') >= 0);
check("nút mờ vẫn nằm đó chứ CSS không ẩn đi",
  CSS.indexOf(".ne-nav button:disabled { opacity") >= 0
  && CSS.indexOf(".ne-nav button:disabled { display: none") < 0);

// ============================================================
// 3. Phím tắt + nút chuột bên hông
// ============================================================
check("Alt+← lùi", /e\.altKey && e\.key === "ArrowLeft".*_neDiLichSu\(-1\)/s.test(CON));
check("Alt+→ tiến", /e\.altKey && e\.key === "ArrowRight".*_neDiLichSu\(1\)/s.test(CON));
// Chặn ở mousedown mới cắt được hành vi lùi TRANG của trình duyệt (lùi cả trang dashboard là
// mất luôn hội thoại đang mở).
check("nút chuột bên hông: chặn hành vi lùi TRANG ở mousedown",
  /addEventListener\("mousedown"[\s\S]{0,200}preventDefault/.test(CON));
check("nút chuột bên hông: điều hướng ở auxclick",
  /addEventListener\("auxclick"[\s\S]{0,300}_neDiLichSu\(-1\)/.test(CON));

// ============================================================
// 4. Không nuốt chữ đang gõ dở
// ============================================================
const mo = CON.slice(CON.indexOf("async function openNote("), CON.indexOf("async function openNote(") + 1400);
check("rời một file đang sửa dở thì LƯU trước", mo.indexOf("_neCoSuaChua()") > 0);
check("CANARY: lưu hỏng thì Ở LẠI, không đi tiếp",
  /_neSaveFn\(\)\) === false\) return/.test(mo));
const diLs = CON.slice(CON.indexOf("async function _neDiLichSu("), CON.indexOf("async function openNote("));
check("bấm Lùi/Tiến cũng lưu trước khi rời", diLs.indexOf("_neCoSuaChua()") > 0);
check("lưu hỏng thì KHÔNG dịch con trỏ vệt",
  diLs.indexOf("=== false) return") < diLs.indexOf("_neViTri += buoc"));

// Mốc so sánh phải là bản ĐÃ vòng qua markdown, không phải chữ thô đọc từ đĩa: bản render
// WYSIWYG đổi ngược lại luôn lệch đôi chỗ, nên so với file gốc thì mỗi lần chỉ ĐỌC rồi rời đi
// cũng bị tính là có sửa, và Javis âm thầm ghi đè định dạng file đó.
check("mốc 'đã sửa gì chưa' lấy từ chính khung soạn, không phải nội dung thô",
  /_neGocText = _neLayNoiDung\(\)/.test(CON));
check("lưu xong thì dời mốc (không lưu lại lần nữa khi rời file)",
  /_neGocText = content/.test(CON));
check("hàm lưu trả về ĐƯỢC/KHÔNG để chỗ gọi tự động biết đường",
  /return true;[\s\S]{0,400}return false;\n {6}\};/.test(CON));

// ============================================================
// 5. Vệt không được trỏ vào file không còn tồn tại
// ============================================================
const rn = CON.slice(CON.indexOf("async function _neRenameCur("), CON.indexOf("async function _neDeleteCur("));
check("đổi tên file -> vệt cập nhật theo tên mới",
  /_neLichSu\.forEach\(n => \{ if \(n\.rel === rel\)/.test(rn));
const del = CON.slice(CON.indexOf("async function _neDeleteCur("), CON.indexOf("function _neCommonBtns("));
check("xoá file -> rút khỏi vệt", /_neLichSu\.filter\(n => n\.rel !== rel\)/.test(del));
check("xoá file -> con trỏ vệt được kéo về chỗ hợp lệ", del.indexOf("_neViTri = Math.min(") >= 0);
check("đổi brain -> xoá sạch vệt (mọi bước thuộc brain cũ)",
  /JavisPin\.clear\(\);[\s\S]{0,300}_neLichSu = \[\]; _neViTri = -1;/.test(CON));

// Đóng trình sửa thì GIỮ vệt: đóng ra chat về chính note đó rồi mở lại là luồng thường gặp.
const dong = CON.slice(CON.indexOf("function closeNote()"), CON.indexOf("async function _neRenameCur("));
check("đóng trình sửa KHÔNG xoá vệt", dong.indexOf("_neLichSu = []") < 0);

if (fails.length) {
  console.error(`\nFAIL - test_lui_tien_note: ${fails.length} lỗi`);
  process.exit(1);
}
console.log("\nOK - test_lui_tien_note: tất cả pass");
