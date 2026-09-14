/* Cắt cụm tự nhiên cho loa (dashboard/voice-chunker.js) - thuần, chạy bằng node.

       node tests/js/test_voice_chunker.js

   Voice V3 (docs/dev/2026-09-voice-v2-spec.md mục 11). Khoá các luật:
     1. Vài từ chưa có dấu -> chưa phát; câu khép -> phát; mấy câu ngắn liền -> gộp một cụm.
     2. Cụm ĐẦU ngắn: đủ 6 từ + dấu phẩy hay liên từ thì cắt ngay; 12 từ không có điểm đẹp thì
        cắt ở khoảng trắng. Cụm SAU không cắt giữa câu trừ khi quá 220 ký tự.
     3. Im lâu (tick) chỉ đẩy khi LOA ĐANG IM và đã có từ 5 từ, cắt ở điểm đẹp.
     4. Khối mã ``` dở thì giữ; khối <!-- ... --> bỏ từ đó về sau; flush đẩy nốt đuôi rồi tính lại
        cụm đầu; dấu chấm trong số thập phân không phải kết câu. */
const C = require("../../dashboard/voice-chunker.js");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}
const j = (a) => JSON.stringify(a);

// ---- 1. Dấu câu ----
let c = new C.Chunker();
check("vài từ chưa có dấu -> chưa phát", j(c.push("Xin lỗi David nhé, chắc", 1000)) === "[]");
check("câu khép -> phát câu, giữ phần dở", j(c.push(" là do mạng. Mình thử lại", 1010)) === j(["Xin lỗi David nhé, chắc là do mạng."]));
check("phần dở còn giữ", c.pending() === " Mình thử lại");
check("flush đẩy nốt đuôi", j(c.flush()) === j([" Mình thử lại"]) && c.pending() === "");
c = new C.Chunker();
check("mấy câu ngắn trong một mẩu -> một cụm", j(c.push("Ừ. Để mình xem. Chắc là", 1)) === j(["Ừ. Để mình xem."]));
c = new C.Chunker();
check("dấu chấm trong số thập phân không kết câu", j(c.push("Doanh thu 1.5 tỷ, tăng", 1)) === "[]");
c = new C.Chunker();
check("xuống dòng là khép", j(c.push("Dòng một\nDòng hai dở", 1)) === j(["Dòng một\n"]));
c = new C.Chunker();
check("dấu hỏi kèm ngoặc kép vẫn là kết câu", j(c.push('Anh muốn xem "cái nào?" Để mình', 1)) === j(['Anh muốn xem "cái nào?"']));

// ---- 2. Cụm đầu ngắn, cụm sau dài ----
c = new C.Chunker();
let out = c.push("Doanh thu hôm nay là mười hai triệu, tăng năm phần trăm so với hôm qua", 1);
check("cụm đầu: đủ 6 từ + dấu phẩy -> cắt ngay sau phẩy", j(out) === j(["Doanh thu hôm nay là mười hai triệu,"]));
check("phần sau còn chờ (cụm sau không cắt giữa câu)", c.pending().trim() === "tăng năm phần trăm so với hôm qua" && j(c.push(" nhờ kênh Shopee đang lên", 2)) === "[]");
check("cụm sau: hết câu mới phát", j(c.push(".", 3)) === j([" tăng năm phần trăm so với hôm qua nhờ kênh Shopee đang lên."]));
c = new C.Chunker();
out = c.push("Mình đã xem số liệu của cả ba kênh và thấy rằng", 1);
check("cụm đầu: cắt TRƯỚC liên từ 'và'", j(out) === j(["Mình đã xem số liệu của cả ba kênh"]) && c.pending() === " và thấy rằng");
c = new C.Chunker();
out = c.push("một hai ba bốn năm sáu bảy tám chín mười mười_một mười_hai mười_ba", 1);
check("cụm đầu: 12 từ không có điểm đẹp -> cắt ở khoảng trắng", out.length === 1 && C.countWords(out[0]) >= 12 && c.pending() === "mười_ba");
c = new C.Chunker();
c.push("Câu đầu xong rồi. ", 1);
const dai = "từ ".repeat(80) + "cuối";
out = c.push(dai, 2);
check("cụm sau quá 220 ký tự -> cắt ở khoảng trắng, không đợi mãi", out.length === 1 && out[0].length <= 221 && out[0].length > 150);
c = new C.Chunker();
c.push("Câu đầu xong rồi. ", 1);
out = c.push("ba bốn năm sáu bảy tám chín, mười mười_một", 2);
check("cụm sau ngắn có phẩy -> KHÔNG cắt (chờ hết câu)", j(out) === "[]");

// ---- 3. Im lâu (tick) ----
c = new C.Chunker({ staleMs: 400 });
c.push("Để mình xem lại số liệu", 1000);
check("tick: chưa quá 400 ms -> không đẩy", j(c.tick(1300, true)) === "[]");
check("tick: quá 400 ms nhưng LOA ĐANG BẬN -> không đẩy", j(c.tick(1500, false)) === "[]");
check("tick: quá 400 ms + loa im + đủ 5 từ -> đẩy ở khoảng trắng cuối", j(c.tick(1500, true)) === j(["Để mình xem lại số"]) && c.pending() === " liệu");
c = new C.Chunker();
c.push("Ừ thì", 1000);
check("tick: dưới 5 từ -> không đẩy dù im lâu", j(c.tick(5000, true)) === "[]");
c = new C.Chunker();
c.push("Câu đầu. ", 900);
c.push("Để mình xem lại số liệu, rồi báo anh ngay", 1000);
out = c.tick(2000, true);
check("tick: có dấu phẩy thì cắt sau phẩy", out.length === 1 && out[0].trim() === "Để mình xem lại số liệu," && c.pending() === " rồi báo anh ngay");
c = new C.Chunker();
out = c.push("Để mình xem lại số liệu rồi", 1000);
check("cụm đầu: liên từ ở cuối -> cắt ngay trước nó, không cần tick", j(out) === j(["Để mình xem lại số liệu"]) && c.first === false);
c = new C.Chunker();
c.push("Để mình xem lại", 1000);
out = c.tick(2000, true);
check("tick: xong thì cụm sau không còn là cụm đầu", out.length === 0 || c.first === false);

// ---- 4. Khối mã, khối điều khiển, flush ----
c = new C.Chunker();
out = c.push("Đây là lệnh:\n```bash\nls -la\n", 1);
check("khối mã dở -> phát dòng trước, giữ khối", j(out) === j(["Đây là lệnh:\n"]) && c.pending().indexOf("```bash") === 0);
out = c.push("```\nXong rồi nhé.", 2);
check("khối mã khép -> BỎ cả khối, câu sau phát", j(out) === j(["Xong rồi nhé."]));
c = new C.Chunker();
out = c.push("Chạy lệnh này ```ls``` là xong.", 1);
check("rào mã giữa dòng: chữ trước rào phát, khối bỏ, chữ sau phát khi khép câu", j(out) === j(["Chạy lệnh này ", " là xong."]));
c = new C.Chunker();
out = c.push("Anh chọn kỳ nào? <!-- JAVIS_ASK: {\"question\":\"x\"", 1);
check("gặp <!-- -> phát phần trước, bỏ phần sau", j(out) === j(["Anh chọn kỳ nào?"]));
check("sau <!-- mọi mẩu mới đều bị bỏ", j(c.push(",\"options\":[]} -->", 2)) === "[]" && j(c.flush()) === "[]");
c = new C.Chunker();
c.push("Câu một. ", 1);
c.flush();
check("flush xong tính lại cụm đầu", c.first === true && c.pending() === "");
c = new C.Chunker();
c.push("```\ncode dở", 1);
check("flush với khối mã dở -> bỏ khối, không đọc", j(c.flush()) === "[]");
c = new C.Chunker();
check("push rỗng / null không lỗi", j(c.push("", 1)) === "[]" && j(c.push(null, 1)) === "[]");
check("countWords", C.countWords("  a b   c ") === 3 && C.countWords("") === 0);
// ---- 5. takeWords (chữ theo lời đọc) ----
check("takeWords: 0 -> rỗng", C.takeWords("một hai ba", 0) === "");
check("takeWords: 2 từ, giữ nguyên khoảng trắng trong", C.takeWords("một  hai ba", 2) === "một  hai");
check("takeWords: quá số từ -> cả chuỗi", C.takeWords("một hai ba", 9) === "một hai ba");
check("takeWords: dấu câu dính từ đi theo từ", C.takeWords("Ừ, để mình xem.", 2) === "Ừ, để");
check("takeWords: null không lỗi", C.takeWords(null, 3) === "");

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - voice-chunker");
