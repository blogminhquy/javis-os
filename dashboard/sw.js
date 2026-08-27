/* Service worker của Javis - CHỈ để nhận thông báo đẩy.

   Cố ý KHÔNG cache gì cả. Javis là app tự host, người dùng cập nhật bằng cách kéo bản mới
   rồi tải lại trang; một service worker có cache sẽ phục vụ bản cũ và biến mỗi lần nâng cấp
   thành một cuộc đi tìm "sao sửa rồi mà không thấy đổi". Đổi lại, file này chỉ làm đúng hai
   việc: hiện thông báo, và đưa người dùng về đúng chỗ khi họ bấm vào.

   Phục vụ từ GỐC site qua route /sw.js (xem main.service_worker) để phạm vi điều khiển là "/",
   không phải "/static/". */
self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

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
