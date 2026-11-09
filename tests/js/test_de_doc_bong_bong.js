/* Bong bóng Javis phải ĐỌC ĐƯỢC, không phải chỗ nhét chữ.

       node tests/js/test_de_doc_bong_bong.js

   Chủ repo gửi ảnh một câu trả lời dài (2026-08-07): "muốn cải thiện lại cách hiển thị của
   Javis cho dễ đọc, xuống cách dòng nhiều hơn chứ đọc khó quá".

   Ba thứ cộng lại làm nên bức tường chữ đó, và sửa thiếu một thứ thì vẫn khó đọc:
     1. giãn dòng chật cho một khối văn xuôi dài;
     2. hai ĐOẠN cách nhau gần bằng hai DÒNG trong cùng đoạn, nên mắt không tách được đoạn;
     3. không giới hạn ĐỘ DÀI DÒNG - trên màn rộng một dòng chạy quá 100 ký tự, đọc hết dòng
        phải dò lại mới tìm ra đầu dòng kế tiếp. Đây là thứ người ta cảm thấy là "mỏi" chứ ít
        khi gọi tên ra được, nên nó cũng là thứ dễ bị chỉnh về như cũ nhất.

   Test này khoá các con số đó theo QUAN HỆ chứ không theo giá trị tuyệt đối: đổi cỡ chữ hay
   tinh chỉnh vài pixel vẫn xanh, chỉ đỏ khi tương quan hỏng (đoạn dính vào nhau, dòng dài
   trở lại, hoặc giãn dòng tụt về mức chật). */
const fs = require("fs");
const path = require("path");

const CSS = fs.readFileSync(path.join(__dirname, "../../dashboard/style.css"), "utf8");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// Lấy thân MỘT rule theo đúng selector (không dính rule ".x .y" hay ".x:hover")
function than(sel) {
  const re = new RegExp("(^|\\})\\s*" + sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") +
                        "\\s*\\{([^}]*)\\}", "m");
  const m = CSS.match(re);
  return m ? m[2] : "";
}
function so(sel, prop) {
  const m = than(sel).match(new RegExp(prop + "\\s*:\\s*([\\d.]+)"));
  return m ? parseFloat(m[1]) : NaN;
}

// ---- 1. Giãn dòng: văn xuôi tiếng Việt có dấu chồng nên cần rộng hơn mức mặc định ----
const lh = so(".msg-javis .bubble", "line-height");
check("bong bóng Javis có đặt giãn dòng", !isNaN(lh));
check("giãn dòng đủ thoáng cho văn xuôi dài (>= 1.7)", lh >= 1.7);

// ---- 2. Đoạn phải tách khỏi đoạn ----
const co = so(".msg-javis .bubble", "font-size");
const mp = so(".msg-javis .bubble p", "margin");
check("có đặt khoảng cách giữa hai đoạn", !isNaN(mp));
// Khoảng trắng giữa hai đoạn (margin, đã gộp) phải LỚN HƠN khoảng trắng giữa hai dòng trong
// cùng đoạn (phần leading = (line-height - 1) * cỡ chữ). Không hơn thì cả khối dính làm một.
const leading = (lh - 1) * co;
check("khoảng cách ĐOẠN lớn hơn khoảng cách DÒNG trong đoạn (mắt tách được đoạn)", mp > leading);
check("đoạn đầu/cuối không đội thêm lề thừa trong bong bóng",
  /margin-top:\s*0/.test(than(".msg-javis .bubble p:first-child")) &&
  /margin-bottom:\s*0/.test(than(".msg-javis .bubble p:last-child")));

// ---- 3. Trần độ dài dòng ----
const bub = than(".msg-javis .bubble");
const mw = bub.match(/max-width:\s*(\d+)ch/);
check("bong bóng có trần độ dài dòng tính bằng 'ch' (đo theo CHỮ, không theo pixel)", !!mw);
if (mw) {
  const ch = parseInt(mw[1], 10);
  // 2026-11-09 (owner, Cộng sự page): answers should use the empty space on the right, so the cap went 72ch -> 100ch.
  // 100ch is about 120 letters of Vietnamese prose, the line length 0.26.1 named as where reading starts to tire.
  check("trần nằm trong khoảng đọc được (60-100 ch)", ch >= 60 && ch <= 100);
}
// Trần đặt trên BONG BÓNG chứ không trên từng đoạn: chặn từng đoạn thì nền bong bóng vẫn rộng
// nguyên, chừa một mảng trống bên phải trông như lỗi hiển thị.
check("khối mã vẫn cuộn ngang được nên trần không bóp mã",
  /\.code-block[^{]*\{[^}]*overflow-x:\s*auto/.test(CSS) ||
  /overflow-x:\s*auto[^}]*white-space:\s*pre/.test(CSS));

// ---- 4. Danh sách và trích dẫn cũng phải thở ----
const mli = so(".msg-javis .bubble li", "margin");
check("mục danh sách có giãn cách", !isNaN(mli) && mli >= 4);
const mul = so(".msg-javis .bubble ul", "margin");
check("danh sách tách khỏi đoạn văn quanh nó", !isNaN(mul) && mul >= 8);
// Danh sách LỒNG thì siết lại - nó thuộc về mục cha, giãn bằng đoạn văn là gãy mạch đọc.
// Rule này khai theo NHÓM selector (ul ul, ul ol, ol ol, ol ul) nên phải bắt cả cụm.
const nest = (CSS.match(/\.msg-javis \.bubble ul ul,[\s\S]*?\{([^}]*)\}/) || [])[1] || "";
const mnest = parseFloat((nest.match(/margin:\s*([\d.]+)/) || [])[1]);
check("danh sách lồng nhau siết hơn danh sách ngoài", !isNaN(mnest) && mnest < mul);
const mbq = so(".msg-javis .bubble blockquote", "margin");
check("trích dẫn tách khỏi văn quanh nó", !isNaN(mbq) && mbq >= mp);

// ---- 5. Tiêu đề: cách phần TRÊN nhiều hơn phần DƯỚI (tiêu đề thuộc về đoạn ngay sau nó) ----
const h = than(".msg-javis .bubble h1, .msg-javis .bubble h2,\n.msg-javis .bubble h4, .msg-javis .bubble h5, .msg-javis .bubble h6")
  || (CSS.match(/\.msg-javis \.bubble h1,[\s\S]*?\{([^}]*)\}/) || [])[1] || "";
const hm = h.match(/margin:\s*(\d+)px\s+0\s+(\d+)px/);
check("tiêu đề có lề trên/dưới riêng", !!hm);
if (hm) {
  check("tiêu đề dính đoạn phía SAU nó hơn đoạn phía trước",
    parseInt(hm[1], 10) > parseInt(hm[2], 10));
}
check("tiêu đề đứng đầu bong bóng không đội lề trên",
  /h1:first-child|h3:first-child/.test(CSS) && /margin-top:\s*0/.test(CSS));

if (fails.length) {
  console.log("\nFAIL - test_de_doc_bong_bong: " + fails.length + " lỗi");
  process.exit(1);
}
console.log("\nOK - test_de_doc_bong_bong: tất cả pass");
