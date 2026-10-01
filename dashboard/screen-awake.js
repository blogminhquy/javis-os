/* screen-awake.js - giữ màn hình sáng trong lúc gọi Javis (0.65.22).

   Chủ dự án báo 01/10: trên iPhone (app mở từ màn hình chính), màn hình tự tắt giữa cuộc gọi là
   Javis không nghe, không đáp, vì trình duyệt điện thoại tạm dừng trang và cắt mic khi khoá máy.
   Chủ chọn cách giữ màn hình sáng (Screen Wake Lock) suốt cuộc gọi. Trình duyệt tự nhả khoá khi
   trang bị ẩn (chuyển app, bấm nút nguồn), nên mở lại trang mà vẫn đang gọi thì xin lại.
   Máy không hỗ trợ thì thôi, không hỏi han gì: cuộc gọi vẫn chạy như trước.
   Ghi chú: KHÔNG dùng ký tự em dash. */
(function (root) {
  "use strict";

  function create(opts) {
    opts = opts || {};
    var nav = opts.navigator || root.navigator, doc = opts.document || root.document;
    var want = false, lock = null, pending = null;

    function supported() { return !!(nav && nav.wakeLock && nav.wakeLock.request); }

    function request() {
      if (!want || lock || pending || !supported()) return pending || Promise.resolve(!!lock);
      if (doc && doc.visibilityState && doc.visibilityState !== "visible") return Promise.resolve(false);
      // Gọi request NGAY trong lời gọi hold() (đang ở cú bấm mic): có trình duyệt đòi cử chỉ người dùng.
      var req;
      try { req = nav.wakeLock.request("screen"); } catch (e) { return Promise.resolve(false); }
      pending = Promise.resolve(req).then(function (l) {
        pending = null;
        if (!want) { try { l.release(); } catch (e) {} return false; }   // cúp máy trong lúc đang xin
        lock = l;
        try { l.addEventListener("release", function () { if (lock === l) lock = null; }); } catch (e) {}
        return true;
      }, function () { pending = null; return false; });
      return pending;
    }

    function hold() { want = true; return request(); }

    function release() {
      want = false;
      var l = lock;
      lock = null;
      if (l) { try { l.release(); } catch (e) {} }
    }

    if (doc && doc.addEventListener) {
      doc.addEventListener("visibilitychange", function () {
        if (want && doc.visibilityState === "visible") request();
      });
    }

    return { hold: hold, release: release, active: function () { return !!lock; }, supported: supported };
  }

  var api = { create: create };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.JavisScreenAwake = create();
})(typeof window !== "undefined" ? window : globalThis);
