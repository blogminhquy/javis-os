/* chat-quote.js - trích dẫn một câu trả lời cũ để hỏi tiếp (0.171.0).

   Chủ repo 15/10/2026: một câu trả lời phía trên đã trôi qua, muốn quay lại hỏi tiếp chuyện đó thì
   phải gõ lại. Nút Trích dẫn dưới mỗi tin đặt đoạn đó lên trên ô nhập; gửi đi thì câu hỏi mang theo
   đoạn trích dạng markdown `> ...` ở đầu tin.

   Vì sao trích dẫn nằm NGAY TRONG CHỮ của tin chứ không ở một trường riêng: mọi bộ não (CLI lẫn API)
   đều đọc được markdown, kho phiên lưu nguyên chữ nên F5 hay mở lại hội thoại vẫn thấy, và link chia
   sẻ hội thoại hiện nó thành khối trích dẫn mà không cần biết gì thêm.

   File này chỉ giữ phần THUẦN để test bằng node: dashboard/test_chat_quote.js. Phần gắn sự kiện nằm
   trong app.js (cần ô nhập và sendMessage). Không dùng ký tự em dash. */
(function () {
  "use strict";

  // Đoạn trích dài cỡ này là đủ để model biết đang nói chỗ nào; dài hơn thì tin phình và bong bóng
  // chiếm cả màn hình. Muốn trích đúng một đoạn thì bôi đen đoạn đó rồi bấm nút.
  var TOI_DA = 1200;

  function gon(text) {
    return String(text == null ? "" : text).replace(/\r\n?/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  }

  // Chữ trích -> các dòng markdown "> ...". Cắt bớt ở TOI_DA và đánh dấu "…" để model biết là đoạn
  // cắt, không phải toàn văn.
  function dinhDang(text, toiDa) {
    var s = gon(text);
    if (!s) return "";
    var n = toiDa || TOI_DA;
    if (s.length > n) s = s.slice(0, n).replace(/\s+\S*$/, "") + " …";
    return s.split("\n").map(function (d) { return d.trim() ? "> " + d : ">"; }).join("\n");
  }

  // Câu gửi đi: đoạn trích, một dòng trống, rồi câu hỏi.
  function ghep(trich, cauHoi) {
    var q = dinhDang(trich);
    var c = String(cauHoi == null ? "" : cauHoi).trim();
    if (!q) return c;
    return c ? q + "\n\n" + c : q;
  }

  // Tách khối trích dẫn ở ĐẦU một tin người dùng (các dòng liền nhau bắt đầu bằng ">").
  function tach(text) {
    var s = String(text == null ? "" : text);
    var dong = s.split("\n");
    var i = 0;
    while (i < dong.length && /^>/.test(dong[i])) i++;
    if (!i) return { quote: "", rest: s };
    var quote = dong.slice(0, i).map(function (d) { return d.replace(/^> ?/, ""); }).join("\n").trim();
    var rest = dong.slice(i).join("\n").replace(/^\s*\n/, "");
    return { quote: quote, rest: rest };
  }

  // HTML của chữ trong bong bóng người dùng: khối trích dẫn (nếu có) rồi câu hỏi. Cả hai đều
  // escape: đây là chữ người dùng gõ, không bao giờ được hiểu thành HTML.
  function utextHtml(text, esc) {
    var t = tach(text);
    if (!t.quote) return esc(text);
    return '<span class="uquote">' + esc(t.quote) + "</span>" + esc(t.rest);
  }

  // Dòng xem trước trên chip phía trên ô nhập: một dòng, ngắn, bỏ ký hiệu markdown (**, `, #, gạch
  // đầu dòng) để chip đọc như chữ thường chứ không như mã nguồn.
  function xemTruoc(text, n) {
    var s = gon(text)
      .replace(/^\s*(#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s?)/gm, "")
      .replace(/\*\*|__|`/g, "")
      .replace(/\s+/g, " ").trim();
    n = n || 90;
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
  }

  var API = { TOI_DA: TOI_DA, dinhDang: dinhDang, ghep: ghep, tach: tach, utextHtml: utextHtml,
              xemTruoc: xemTruoc };
  if (typeof window !== "undefined") window.JavisQuote = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})();
