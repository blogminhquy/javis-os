/* Hòm thư trên navbar + công tắc thông báo đẩy.

       node tests/js/test_hom_thu_ui.js

   Chủ repo yêu cầu 27/08/2026: làm hòm thư và thông báo đẩy trình duyệt, bấm vào thông báo
   thì QUAY VỀ hội thoại của phần chat.

   Mấy chỗ dễ làm sai mà file này khoá lại:

   1. Bấm một mẩu thư phải mở ĐÚNG hội thoại cũ (`JavisSessions.open`), không phải mở hội
      thoại mới - toàn bộ ngữ cảnh nằm ở hội thoại cũ, hỏi tiếp ở chỗ khác là kể lại từ đầu.
   2. Đã-đọc của thư riêng nằm ở SERVER (`/inbox/read`), không phải localStorage như tin
      chung: điện thoại và máy tính phải đếm giống nhau.
   3. Không bao giờ xin quyền thông báo lúc tải trang. Trình duyệt coi lời xin không do
      người dùng bấm là spam và chặn vĩnh viễn miền đó.
   4. Service worker phải phục vụ từ GỐC site. Đặt ở /static/sw.js thì phạm vi chỉ là
      /static/*, tức là không nhận được push cho trang chủ.
*/
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const html = read("dashboard/index.html");
const noti = read("dashboard/notifications.js");
const push = read("dashboard/push.js");
const sw = read("dashboard/sw.js");
const app = read("dashboard/app.js");
const css = read("dashboard/style.css");
const main = read("server/main.py");

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- 1. Hai tab, không trộn thư riêng với tin phát chung ----
check("panel có tab 'Của tôi' và 'Tin tức'",
  html.indexOf('id="notiTabMine"') !== -1 && html.indexOf('id="notiTabNews"') !== -1);
check("mỗi tab có ô đếm chưa đọc riêng",
  html.indexOf('id="notiTabMineCount"') !== -1 && html.indexOf('id="notiTabNewsCount"') !== -1);
check("thư riêng lấy từ /inbox", noti.indexOf('fetch("/inbox?limit=') !== -1);
check("tin chung vẫn lấy từ /notifications như cũ", noti.indexOf('fetch("/notifications"') !== -1);
check("chấm đỏ trên chuông đếm CẢ HAI tầng",
  /var tong = unread\.length \+ state\.thuChuaDoc/.test(noti));

// ---- 2. Bấm thư = quay về hội thoại cũ ----
check("CANARY: mở thư gọi JavisSessions.open (quay về hội thoại đã hỏi)",
  /window\.JavisSessions\.open\(item\.session_id\)/.test(noti));
check("CANARY: KHÔNG mở hội thoại mới khi đọc thư",
  noti.indexOf("JavisSessions.new()") === -1);
check("thư không gắn hội thoại thì chỉ đánh dấu đã đọc, không nhảy đi đâu",
  /if \(!item\.session_id\) \{ render\(\); return; \}/.test(noti));

// ---- 3. Đã-đọc nằm ở server ----
check("đánh dấu đã đọc gọi /inbox/read", noti.indexOf('fetch("/inbox/read"') !== -1);
check("CANARY: đọc tất cả ở tab thư riêng đi qua API, không chỉ tô lại màu",
  /docThu\(\{ all: true \}\)/.test(noti));
check("mở một hội thoại thì thư của nó tự đánh dấu đã đọc (chống đếm hai lần)",
  /docThu\(\{ session_id: sid \}\)/.test(noti)
  && /window\.JavisInbox\.docPhien\(id\)/.test(app));
check("server có đủ ba lối đánh dấu (một mẩu / cả hội thoại / tất cả)",
  main.indexOf("inbox.doc_het()") !== -1 && main.indexOf("inbox.doc_theo_phien(") !== -1
  && main.indexOf("inbox.danh_dau_doc(") !== -1);

// ---- 4. Chấm đỏ cập nhật sống qua WebSocket ----
check("app.js xử lý sự kiện 'inbox' từ WebSocket", /data\.type === "inbox"/.test(app));
check("thư của hội thoại ĐANG mở thì đánh dấu đọc luôn, còn lại chỉ làm tươi chuông",
  /sid === savedSessionId\) window\.JavisInbox\.docPhien\(sid\)/.test(app));

// ---- 5. Thông báo đẩy: không tự ý xin quyền ----
check("CANARY: chỉ xin quyền TRONG hàm bat() (do người dùng bấm), không gọi lúc tải trang",
  (push.match(/Notification\.requestPermission\(\)/g) || []).length === 1);
const iBat = push.indexOf("async function bat()");
const iXin = push.indexOf("Notification.requestPermission()");
check("CANARY: lời xin quyền nằm bên trong bat()", iXin > iBat && iBat !== -1);
check("tự nối lại chỉ khi ĐÃ được cấp quyền từ trước",
  /Notification\.permission !== "granted"\) return;[\s\S]{0,120}setTimeout/.test(push));
check("ẩn nút + nói lý do khi không phải secure context (http trần)",
  /isSecureContext/.test(push) && /https/.test(push));
check("nút hỏng thì GIỮ lý do trên màn hình, không vẽ đè bằng ghi chú mặc định",
  /veNutPush\(r\.ok \? "" : \(r\.error/.test(noti) && /async function veNutPush\(loi\)/.test(noti));

// ---- 5b. Đẩy tới MỌI thiết bị, và nói rõ máy nào hỏng ----
// Lỗi thật chủ repo báo 27/08: bấm Gửi thử trên điện thoại thì máy tính hiện thông báo còn
// điện thoại không - mà màn hình vẫn báo "đã gửi" vì CÓ máy nhận được.
check("CANARY: Gửi thử đọc kết quả theo TỪNG thiết bị, không chỉ cờ ok chung",
  /d\.devices \|\| \[\]/.test(push) && /hong\[0\]|hong\.length/.test(push));
check("báo đủ mấy máy nhận được chứ không nói 'đã gửi' chung chung",
  /Đã gửi tới " \+ \(r\.so/.test(noti));
check("nêu ĐÍCH DANH dịch vụ đẩy đang hỏng", /mot\.dich_vu \+ " không nhận được"/.test(push));
check("ô công tắc nói số thiết bị đang nhận", /JavisPush\.thietBi\(\)/.test(noti));
check("server trả danh sách thiết bị kèm lỗi lần gửi gần nhất",
  main.indexOf('"loi_lan_cuoi"') !== -1 && main.indexOf('"devices": chi_tiet') !== -1);

// ---- 6. Service worker phục vụ từ GỐC site ----
check("CANARY: server có route /sw.js riêng (không để ở /static/)",
  /@app\.get\("\/sw\.js"\)/.test(main));
check("trả kèm Service-Worker-Allowed: /", main.indexOf('"Service-Worker-Allowed": "/"') !== -1);
check("client đăng ký đúng /sw.js với scope /", /register\("\/sw\.js", \{ scope: "\/" \}\)/.test(push));
check("sw.js có handler push + notificationclick",
  sw.indexOf('addEventListener("push"') !== -1 && sw.indexOf('addEventListener("notificationclick"') !== -1);
check("CANARY: bấm thông báo thì FOCUS tab Javis đang mở, không đẻ tab thứ hai",
  sw.indexOf("c.focus()") !== -1 && sw.indexOf("matchAll") !== -1);
check("sw.js KHÔNG cache gì (tránh phục vụ bản cũ sau khi cập nhật)",
  sw.indexOf("caches.open") === -1 && sw.indexOf('addEventListener("fetch"') === -1);

// ---- 7. Đường về từ thông báo hệ điều hành ----
check("push mang tham số mo_thu để về đúng mẩu thư", main.indexOf("mo_thu=") !== -1);
check("client đọc mo_thu rồi mở đúng thư đó", noti.indexOf('get("mo_thu")') !== -1);
check("xoá tham số khỏi URL để F5 không mở lại", /history\.replaceState/.test(noti));

// ---- 8. CSS + cache-bust ----
check("có style cho tab và ô công tắc push",
  css.indexOf(".noti-tabs") !== -1 && css.indexOf(".noti-push") !== -1);
check("nhãn loại thư có màu riêng", css.indexOf(".noti-kind.report") !== -1);
const v = (f) => Number((html.match(new RegExp(f.replace(/[.\-]/g, "\\$&") + "\\?v=(\\d+)")) || [])[1] || 0);
check("push.js được nạp", html.indexOf("/static/push.js?v=") !== -1);
check("notifications.js đã bump ?v= (>= 3)", v("notifications.js") >= 3, v("notifications.js"));
check("app.js đã bump ?v= (>= 95)", v("app.js") >= 95, v("app.js"));
check("style.css đã bump ?v= (>= 71)", v("style.css") >= 71, v("style.css"));

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_hom_thu_ui: tat ca pass");
