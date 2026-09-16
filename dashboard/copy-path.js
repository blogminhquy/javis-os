/* copy-path.js - MỘT chỗ duy nhất lo việc chép một chuỗi vào bảng nhớ tạm.

   Trước file này mỗi màn tự viết lại đoạn navigator.clipboard.writeText của riêng nó (khung
   artifact, trang tên miền, trang Ollama, trang tài khoản...), và mỗi bản lại thiếu một thứ
   khác nhau: chỗ thì không có đường lui khi trình duyệt chặn, chỗ thì báo "đã chép" bằng
   btn.textContent nên nút nào có icon SVG là mất luôn icon sau một giây.

   Hai đường chép, thử lần lượt:
   1. navigator.clipboard - chỉ sống trong ngữ cảnh bảo mật (https hoặc localhost).
   2. một <textarea> ẩn + document.execCommand("copy") - đường DUY NHẤT còn chạy khi Javis
      phục vụ qua http trần trên mạng nội bộ hay trên VPS chưa gắn tên miền, tức là đúng
      cảnh dùng thật của phần lớn người dùng.
   Hỏng cả hai thì bày chuỗi ra trong prompt() để người dùng tự bôi đen - thà xấu còn hơn
   bấm xong không có gì xảy ra và không ai hiểu vì sao.

   Ghi chú: KHÔNG dùng ký tự em dash. */
(function () {
  "use strict";

  function icon(ten) {
    try { return window.ic ? window.ic(ten) : ""; } catch (e) { return ""; }
  }

  function chu(khoa, roiVe) {
    try { var s = window.t && window.t(khoa); return s && s !== khoa ? s : roiVe; }
    catch (e) { return roiVe; }
  }

  function quaApi(text) {
    if (!navigator.clipboard || !window.isSecureContext) return Promise.reject();
    try { return Promise.resolve(navigator.clipboard.writeText(text)); }
    catch (e) { return Promise.reject(e); }
  }

  /** Đường lui cho http trần. Phải nằm TRONG luồng của cú bấm (đừng await gì trước nó) vì
   *  execCommand chỉ được phép chạy khi trình duyệt còn coi là "người dùng vừa thao tác". */
  function quaTextarea(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    // Ngoài màn hình nhưng KHÔNG display:none: thẻ ẩn hẳn thì không select() được.
    ta.style.cssText = "position:fixed;top:0;left:0;width:1px;height:1px;opacity:0;padding:0;border:0";
    document.body.appendChild(ta);
    var ok = false;
    try {
      ta.select();
      ta.setSelectionRange(0, ta.value.length);   // Safari iOS bỏ qua select() trơ
      ok = document.execCommand("copy");
    } catch (e) { ok = false; }
    ta.remove();
    return ok;
  }

  /** Nháy dấu tích ngay trên nút vừa bấm rồi trả nút về nguyên trạng.
   *  Nhớ innerHTML chứ không nhớ textContent: nút ở đây gần như luôn là một icon SVG. */
  function nhay(btn, ok) {
    if (!btn) return;
    if (btn.dataset.saoCu == null) btn.dataset.saoCu = btn.innerHTML;
    var cu = btn.dataset.saoCu;
    var moi = ok ? icon("check") : icon("triangle-alert");
    if (moi) btn.innerHTML = moi;
    btn.classList.add(ok ? "da-chep" : "chep-loi");
    btn.title = ok ? chu("common.copied", "Đã chép") : chu("common.copy_fail", "Không chép được");
    clearTimeout(btn._saoTimer);
    btn._saoTimer = setTimeout(function () {
      btn.innerHTML = cu;
      delete btn.dataset.saoCu;
      btn.classList.remove("da-chep", "chep-loi");
      if (btn.dataset.saoTitle) btn.title = btn.dataset.saoTitle;
    }, 1200);
  }

  /** Chép `text`. `btn` (tuỳ chọn) là nút vừa bấm, dùng để nháy dấu tích.
   *  Trả về Promise<boolean> cho chỗ gọi nào muốn biết kết quả. */
  function chep(text, btn) {
    var s = String(text == null ? "" : text);
    if (!s) return Promise.resolve(false);
    // Giữ lại title gốc TRƯỚC khi nháy đè lên, kẻo nút mất chú thích sau lần bấm đầu.
    if (btn && btn.dataset.saoTitle == null && btn.title) btn.dataset.saoTitle = btn.title;
    var lui = function () {
      // execCommand chỉ chạy khi trình duyệt còn coi là "người dùng vừa thao tác", nên đường
      // lui phải nằm càng gần cú bấm càng tốt.
      var ok = quaTextarea(s);
      nhay(btn, ok);
      if (!ok) { try { window.prompt(chu("common.copy_manual", "Chép tay đoạn này:"), s); } catch (e) {} }
      return ok;
    };
    // Không có clipboard API (http trần) thì đi thẳng đường lui NGAY trong luồng bấm, đừng
    // vòng qua một Promise bị từ chối rồi mới thử - vòng đó có thể đã ăn mất quyền thao tác.
    if (!navigator.clipboard || !window.isSecureContext) return Promise.resolve(lui());
    return quaApi(s).then(function () { nhay(btn, true); return true; }).catch(lui);
  }

  window.JavisCopy = chep;
})();
