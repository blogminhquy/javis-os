/* Service worker của Javis - CHỈ để nhận thông báo đẩy.

   Cố ý KHÔNG cache gì cả. Javis là app tự host, người dùng cập nhật bằng cách kéo bản mới
   rồi tải lại trang; một service worker có cache sẽ phục vụ bản cũ và biến mỗi lần nâng cấp
   thành một cuộc đi tìm "sao sửa rồi mà không thấy đổi". Đổi lại, file này chỉ làm đúng hai
   việc: hiện thông báo, và đưa người dùng về đúng chỗ khi họ bấm vào.

   Phục vụ từ GỐC site qua route /sw.js (xem main.service_worker) để phạm vi điều khiển là "/",
   không phải "/static/".

   0.418.0, MỘT NGOẠI LỆ HẸP: đường lùi khi KHÔNG với tới máy chủ. Khách báo 30/10/2026: bấm cập nhật, trang mở lại
   giữa lúc máy chủ (hay đường hầm Cloudflare trước nó) còn khởi động và vỡ hẳn. Mở trang "/" và tải từ điển chữ
   (/static/i18n/*.json) vẫn LUÔN hỏi máy chủ trước và dùng bản mới. Chỉ khi máy chủ không trả lời được (mất mạng, 502,
   503, 504, 520-530) mới đưa ra bản tốt gần nhất đã thấy, để người dùng thấy Javis kèm dải "Đang kết nối lại" thay cho
   trang lỗi. Bản đó có thể cũ hơn máy chủ: freshness.js hỏi phiên bản ngay khi máy chủ lên lại và tải lại trang khi
   lệch. Mọi yêu cầu khác service worker không đụng tới, nên lý do "không cache" ở trên vẫn nguyên. */
const KHO = "javis-khung-v1";
const tam = (s) => s === 502 || s === 503 || s === 504 || (s >= 520 && s <= 530);

function khoaKhung(req) {
  if (req.method !== "GET") return "";
  const u = new URL(req.url);
  if (u.origin !== self.location.origin) return "";
  if (req.mode === "navigate" && u.pathname === "/") return u.origin + "/";
  if (/^\/static\/i18n\/[a-z]{2,3}\.json$/.test(u.pathname)) return u.origin + u.pathname;
  return "";
}

self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil((async () => {
  // Kho của phiên bản trước (đổi tên KHO) thì dọn.
  for (const k of await caches.keys()) if (k.indexOf("javis-khung-") === 0 && k !== KHO) await caches.delete(k);
  await self.clients.claim();
})()));

self.addEventListener("fetch", (event) => {
  const khoa = khoaKhung(event.request);
  if (!khoa) return;   // không gọi respondWith: trình duyệt tự đi như không có service worker
  event.respondWith((async () => {
    try {
      const r = await fetch(event.request);
      if (r.ok && !r.redirected) {
        const kho = await caches.open(KHO);
        await kho.put(khoa, r.clone()).catch(() => {});
        return r;
      }
      if (tam(r.status)) { const cu = await caches.match(khoa); if (cu) return cu; }
      return r;
    } catch (loi) {
      const cu = await caches.match(khoa);
      if (cu) return cu;
      throw loi;
    }
  })());
});

self.addEventListener("push", (event) => {
  let d = {};
  try { d = event.data ? event.data.json() : {}; } catch (e) { d = { body: (event.data && event.data.text()) || "" }; }
  const title = d.title || "Javis";
  const opts = {
    body: d.body || "",
    icon: "/static/icon-192.png",
    badge: "/static/icon-192.png",
    // tag: thông báo cùng tag thì cái mới ĐÈ cái cũ thay vì xếp chồng. Server đặt tag theo
    // id mẩu thư nên mỗi kết quả đúng một dòng, gửi lại không nhân đôi.
    tag: d.tag || "javis",
    data: { url: d.url || "/" },
    renotify: true,
  };
  event.waitUntil(self.registration.showNotification(title, opts));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil((async () => {
    const list = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    // Đã mở Javis ở đâu đó thì FOCUS đúng tab đó rồi nhắn cho nó mở mẩu thư, chứ đừng mở
    // thêm một tab thứ hai - người dùng sẽ có hai bản Javis chạy song song, mỗi bản một
    // hội thoại, và không hiểu vì sao.
    for (const c of list) {
      if (c.url && new URL(c.url).origin === self.location.origin) {
        try { c.postMessage({ type: "javis-open-inbox", url: url }); } catch (e) {}
        return c.focus();
      }
    }
    return self.clients.openWindow(url);
  })());
});
