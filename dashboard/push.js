/* push.js - đăng ký thông báo đẩy của trình duyệt (Web Push).

   Ba luật giữ cho phần này không thành phiền phức:

   1. KHÔNG bao giờ tự hỏi quyền lúc tải trang. Trình duyệt tính một lời xin quyền không do
      người dùng bấm là spam, và Chrome chặn vĩnh viễn miền đó sau vài lần bị từ chối - tức
      là hỏng luôn cả những lần sau khi người ta THẬT SỰ muốn bật. Chỉ hỏi khi bấm nút.
   2. Không có secure context thì ẩn hẳn nút, kèm lý do. Web Push đòi https (localhost được
      tính là an toàn); Javis chạy trần bằng IP LAN qua http là không có cách nào lách.
   3. Hụt push không bao giờ đồng nghĩa mất tin: nội dung nằm trong hòm thư ở server. Nút
      này chỉ bật/tắt cái chuông cửa.
*/
(function () {
  "use strict";
  var reg = null;

  function coHoTro() {
    return ("serviceWorker" in navigator) && ("PushManager" in window) && ("Notification" in window);
  }
  function antoan() { return window.isSecureContext === true; }

  function vichLyDo() {
    if (!antoan()) return "Trình duyệt chỉ cho bật thông báo đẩy trên https (hoặc localhost). Javis đang chạy qua http nên chưa bật được.";
    if (!coHoTro()) return "Trình duyệt này không hỗ trợ thông báo đẩy.";
    if (Notification.permission === "denied") return "Bạn đã chặn thông báo cho trang này. Mở phần cài đặt quyền của trình duyệt để bỏ chặn.";
    return "";
  }

  function b64ToU8(base64) {
    var pad = "=".repeat((4 - (base64.length % 4)) % 4);
    var raw = atob((base64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
    var out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }

  async function dangKySW() {
    if (reg) return reg;
    if (!coHoTro() || !antoan()) return null;
    // scope "/" chạy được vì server trả /sw.js từ gốc site kèm Service-Worker-Allowed.
    reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    await navigator.serviceWorker.ready;
    return reg;
  }

  async function dangBat() {
    if (!coHoTro() || !antoan() || Notification.permission !== "granted") return false;
    try {
      var r = await dangKySW();
      if (!r) return false;
      return !!(await r.pushManager.getSubscription());
    } catch (e) { return false; }
  }

  async function bat() {
    var vi = vichLyDo();
    if (vi) return { ok: false, error: vi };
    try {
      var quyen = await Notification.requestPermission();
      if (quyen !== "granted") return { ok: false, error: "Bạn chưa cho phép hiện thông báo." };
      var r = await dangKySW();
      if (!r) return { ok: false, error: "Không đăng ký được service worker." };
      var key = (await (await fetch("/push/key")).json()).key;
      if (!key) return { ok: false, error: "Máy chủ chưa có khoá VAPID." };
      var sub = await r.pushManager.getSubscription();
      // Khoá server đổi (state bị xoá, dựng lại máy) thì đăng ký cũ vô dụng - huỷ rồi đăng
      // ký lại thay vì im lặng giữ một cái không bao giờ nhận được gì.
      if (sub) {
        var cu = sub.options && sub.options.applicationServerKey;
        var khop = cu && btoa(String.fromCharCode.apply(null, new Uint8Array(cu)))
          .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "") === key;
        if (!khop) { try { await sub.unsubscribe(); } catch (e) {} sub = null; }
      }
      if (!sub) {
        sub = await r.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToU8(key) });
      }
      var res = await fetch("/push/subscribe", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subscription: sub.toJSON(), nhan: navigator.userAgent.slice(0, 110) }),
      });
      var d = await res.json();
      return d.ok ? { ok: true } : { ok: false, error: d.error || "Máy chủ từ chối đăng ký." };
    } catch (e) {
      return { ok: false, error: (e && e.message) || String(e) };
    }
  }

  async function tat() {
    try {
      var r = await dangKySW();
      var sub = r && (await r.pushManager.getSubscription());
      if (sub) {
        await fetch("/push/unsubscribe", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: sub.endpoint }),
        });
        await sub.unsubscribe();
      }
      return { ok: true };
    } catch (e) { return { ok: false, error: (e && e.message) || String(e) }; }
  }

  async function thu() {
    try {
      var d = await (await fetch("/push/test", { method: "POST" })).json();
      return d.ok ? { ok: true } : { ok: false, error: "Chưa có trình duyệt nào đăng ký nhận." };
    } catch (e) { return { ok: false, error: (e && e.message) || String(e) }; }
  }

  // Bấm vào thông báo khi Javis đang mở: service worker focus đúng tab này rồi nhắn sang.
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.addEventListener("message", function (ev) {
      var d = ev.data || {};
      if (d.type !== "javis-open-inbox") return;
      try { if (window.JavisInbox) window.JavisInbox.moTu(d.url || ""); } catch (e) {}
    });
  }

  // Đã cấp quyền từ lần trước thì lặng lẽ đăng ký lại lúc tải trang. Không hỏi gì cả - việc
  // hỏi đã xong rồi; đây chỉ là dựng lại đăng ký sau khi xoá cache hoặc đổi khoá server.
  function tuNoiLai() {
    if (!coHoTro() || !antoan() || Notification.permission !== "granted") return;
    setTimeout(function () { bat(); }, 2500);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", tuNoiLai);
  else tuNoiLai();

  window.JavisPush = { batDuoc: function () { return coHoTro() && antoan(); },
                       lyDo: vichLyDo, dangBat: dangBat, bat: bat, tat: tat, thu: thu };
})();
