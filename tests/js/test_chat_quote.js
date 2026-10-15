/* Test trich dan cau tra loi cu (chat-quote.js, 0.171.0). Chay tay / CI:
       node tests/js/test_chat_quote.js
   Chu repo 15/10/2026: muon hoi tiep mot cau tra loi da troi qua thi phai go lai. Nut Trich dan
   dat doan do len o nhap; gui di thi cau hoi mang doan trich dang "> ..." o dau tin.
   Ghi chu: KHONG dung ky tu em dash o bat ky dau. */
const Q = require("../../dashboard/chat-quote.js");

const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// ---- 1. Định dạng đoạn trích ----
check("mỗi dòng mở đầu bằng '> '", Q.dinhDang("dòng một\ndòng hai") === "> dòng một\n> dòng hai");
check("dòng trống trong đoạn trích vẫn nằm trong khối", Q.dinhDang("a\n\nb") === "> a\n>\n> b");
check("chữ rỗng thì không trích gì", Q.dinhDang("   ") === "");
const dai = "chữ ".repeat(800);
const q = Q.dinhDang(dai);
check("đoạn quá dài bị cắt và đánh dấu …", q.length < dai.length && q.endsWith("…"), q.length);
check("đoạn cắt không quá trần", q.length <= Q.TOI_DA + 10, q.length);

// ---- 2. Ghép với câu hỏi ----
const tin = Q.ghep("Giá sỉ là 45k một chai.", "Vậy lấy 100 chai thì sao?");
check("đoạn trích đứng trước, cách câu hỏi một dòng trống",
      tin === "> Giá sỉ là 45k một chai.\n\nVậy lấy 100 chai thì sao?", JSON.stringify(tin));
check("không có đoạn trích thì giữ nguyên câu hỏi", Q.ghep("", "hỏi") === "hỏi");

// ---- 3. Tách lại khi vẽ bong bóng / mở lại hội thoại ----
const t = Q.tach(tin);
check("tách ra đúng đoạn trích", t.quote === "Giá sỉ là 45k một chai.", t.quote);
check("tách ra đúng câu hỏi", t.rest === "Vậy lấy 100 chai thì sao?", JSON.stringify(t.rest));
check("tin không trích dẫn: rest là nguyên văn", Q.tach("chào").quote === "" && Q.tach("chào").rest === "chào");
const nhieu = Q.tach(Q.ghep("a\n\nb", "hỏi"));
check("đoạn trích nhiều đoạn tách lại đủ", nhieu.quote === "a\n\nb" && nhieu.rest === "hỏi", JSON.stringify(nhieu));

// ---- 4. HTML trong bong bóng: có khối trích, và luôn escape ----
const h = Q.utextHtml("> <b>trích</b>\n\ncâu <i>hỏi</i>", esc);
check("có khối uquote", h.indexOf('<span class="uquote">') === 0, h);
check("CANARY: chữ trong đoạn trích được escape", h.indexOf("&lt;b&gt;trích&lt;/b&gt;") > 0, h);
check("CANARY: câu hỏi được escape", h.indexOf("câu &lt;i&gt;hỏi&lt;/i&gt;") > 0, h);
check("tin thường: chỉ escape, không thêm khối", Q.utextHtml("x < y", esc) === "x &lt; y");

// ---- 5. Dòng xem trước trên chip ----
check("xem trước gộp về một dòng", Q.xemTruoc("a\n\nb   c") === "a b c");
check("xem trước bỏ ký hiệu markdown", Q.xemTruoc("Giá **45k**\n\n- Từ 100 chai: `5%`") === "Giá 45k Từ 100 chai: 5%",
      Q.xemTruoc("Giá **45k**\n\n- Từ 100 chai: `5%`"));
check("xem trước dài thì cắt", Q.xemTruoc("x".repeat(200)).length === 90);

console.log();
if (fails.length) {
  console.log("ĐỎ " + fails.length + " mục: " + fails.join(", "));
  process.exit(1);
}
console.log("Tất cả xanh.");
