/* nap-cham.js - nạp code của từng trang khi cần (0.417.0).

   Đo ngày 30/10/2026: lúc mở app, 72% code JS được tải và đọc nhưng không hề chạy, vì đó là code của các trang khác
   (Nhóm, Hội thoại, Chatbot, Store, Thống kê, Webhook...). Các file LỚN mà chỉ một trang dùng giờ không còn nằm trong
   index.html; danh sách của chúng nằm trong khối <script id="javis-lazy"> (máy chủ gắn khoá ?v= y như mọi file khác).

   CSS riêng của một trang (inbox-v5.css, inbox-compact.css của trang Hội thoại) đi cùng nhóm, đứng trước JS, và trang
   chỉ vẽ khi nó đã áp xong. Nạp sau style.css/console.css y như vị trí cũ cuối index.html, nên thứ tự ưu tiên không đổi.

   Hai đường nạp, để không có chỗ nào thấy "module chưa sẵn sàng":
   - TRANG: console.js renderPage chờ `JavisNapCham.cho(nhóm)` trước khi vẽ trang đó. Chỗ gọi chéo (thông báo mở một
     nhóm Teams, nút Store ở trang Cộng sự...) cũng chờ đúng nhóm nó cần.
   - NỀN: trang mở xong và rảnh thì nạp nốt mọi nhóm, lần lượt, đúng thứ tự cũ trong index.html. Nên hầu như lúc người
     dùng bấm sang trang khác thì code đã nằm sẵn, chỉ khác là nó không còn chặn lúc mở app.

   File trong một nhóm chạy ĐÚNG thứ tự khai (nhóm sau có thể dựa vào nhóm trước); hỏng một file thì nhóm vẫn báo xong để
   trang tự hiện câu "chưa sẵn sàng" như cũ, không treo. */
(function () {
  "use strict";

  var NHOM = null;           // tên nhóm -> [url]
  var daNap = {};            // url -> Promise
  var dangNhom = {};         // tên nhóm -> Promise
  var xongNhom = {};         // tên nhóm -> true khi mọi file đã chạy

  function bang() {
    if (NHOM) return NHOM;
    try { NHOM = JSON.parse(document.getElementById("javis-lazy").textContent || "{}"); } catch (e) { NHOM = {}; }
    return NHOM;
  }

  // .css thành <link> (chờ nó áp xong rồi mới báo xong, để trang không vẽ lúc chưa có kiểu), .js thành <script>.
  function napFile(url) {
    if (daNap[url]) return daNap[url];
    daNap[url] = new Promise(function (xong) {
      var laCss = /\.css(\?|$)/.test(url);
      var s = document.createElement(laCss ? "link" : "script");
      if (laCss) { s.rel = "stylesheet"; s.href = url; } else { s.src = url; s.async = false; }
      s.onload = function () { xong(true); };
      s.onerror = function () { delete daNap[url]; xong(false); };
      (laCss ? document.head : document.body).appendChild(s);
    });
    return daNap[url];
  }

  // Nạp một nhóm (hay một danh sách nhóm). Trả Promise xong khi mọi file đã chạy.
  function cho(ten) {
    if (Array.isArray(ten)) return Promise.all(ten.map(cho));
    var ds = bang()[ten];
    if (!ds) return Promise.resolve(false);
    if (dangNhom[ten]) return dangNhom[ten];
    var p = ds.reduce(function (truoc, url) { return truoc.then(function () { return napFile(url); }); }, Promise.resolve());
    dangNhom[ten] = p.then(function () { xongNhom[ten] = true; return true; });
    return dangNhom[ten];
  }

  function daXong(ten) {
    return Array.isArray(ten) ? ten.every(daXong) : !!xongNhom[ten] || !bang()[ten];
  }

  // Nạp nhóm rồi gọi fn: dùng cho chỗ gọi chéo sang module của trang khác (bấm thông báo, nút Store...). Nhóm đã nạp thì
  // gọi NGAY, cùng nhịp với cú bấm, để những việc trình duyệt chỉ cho làm trong cú bấm (mở cửa sổ, chọn file) vẫn chạy.
  function goi(ten, fn) {
    if (daXong(ten)) { try { return Promise.resolve(fn()); } catch (e) { return Promise.reject(e); } }
    return cho(ten).then(function () { return fn(); });
  }

  function napNen() {
    var ten = Object.keys(bang());
    ten.reduce(function (truoc, t) { return truoc.then(function () { return cho(t); }); }, Promise.resolve());
  }
  function henNen() {
    var chay = function () { setTimeout(function () { (window.requestIdleCallback || setTimeout)(napNen, { timeout: 4000 }); }, 600); };
    if (document.readyState === "complete") chay(); else window.addEventListener("load", chay);
  }

  window.JavisNapCham = { cho: cho, goi: goi, daXong: daXong, nhom: function () { return bang(); } };
  henNen();
})();
