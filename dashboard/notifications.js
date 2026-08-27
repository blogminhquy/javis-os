// Hòm thư navbar - HAI tầng dữ liệu, cố ý không trộn:
//
//   "Của tôi"  = /inbox : thư RIÊNG (kết quả việc nền, báo cáo định kỳ). Đã-đọc nằm ở SERVER
//                nên điện thoại và máy tính đếm giống nhau, và bấm vào là quay về ĐÚNG hội
//                thoại đã hỏi - nội dung đầy đủ nằm ở đó, không phải trong cái thẻ này.
//   "Tin tức"  = /notifications : bản phát hành + tin cộng đồng, phát chung cho mọi người.
//                Đã-đọc giữ ở localStorage như cũ (ai đọc trên máy nấy, không cần đồng bộ).
//
// Gộp một danh sách thì một kết quả công việc thật bị chôn dưới mấy dòng changelog.
(function () {
  var READ_KEY = "javis.notifications.read";
  var INIT_KEY = "javis.notifications.initialized";
  var TAB_KEY = "javis.notifications.tab";
  var MAX_ITEMS = 30;
  var PAGE_SIZE = 5;
  var state = { items: [], read: new Set(), loadedAt: 0, loading: false, visibleCount: PAGE_SIZE,
                thu: [], thuChuaDoc: 0, tab: "mine" };

  function byId(id) { return document.getElementById(id); }
  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function safeUrl(value) {
    var url = String(value || "").trim();
    return /^https?:\/\//i.test(url) ? url : "";
  }
  function loadRead() {
    try {
      var raw = JSON.parse(localStorage.getItem(READ_KEY) || "[]");
      state.read = new Set(Array.isArray(raw) ? raw.map(String) : []);
    } catch (e) { state.read = new Set(); }
  }
  function saveRead() {
    try { localStorage.setItem(READ_KEY, JSON.stringify(Array.from(state.read).slice(-300))); } catch (e) {}
  }
  function firstRun(items) {
    try {
      if (localStorage.getItem(INIT_KEY) === "1") return;
      // Không biến toàn bộ lịch sử phiên bản thành hàng trăm tin chưa đọc ở lần mở đầu.
      // Chỉ giữ unread cho bản đang dùng/bản mới và thông báo cộng đồng ưu tiên cao.
      items.forEach(function (item) {
        var important = item.priority === "high" &&
          (item.kind !== "update" || item.is_current || item.update_available);
        if (!important) state.read.add(String(item.id));
      });
      localStorage.setItem(INIT_KEY, "1");
      saveRead();
    } catch (e) {}
  }
  // Bản ĐÃ CÀI thì không bao giờ tính là chưa đọc.
  //
  // Chủ repo báo (2026-08-12): "ấn đọc tất cả rồi, nâng cấp bản mới vẫn hiện các số như là
  // chưa đọc". Đo lại thì cơ chế đánh dấu không hỏng - nó giữ đúng qua cả lần tải lại trang.
  // Chuyện thật sự xảy ra: giữa lúc bấm "Đọc tất cả" và lúc nâng cấp có thêm vài bản phát
  // hành mới. Chúng chưa từng được đọc nên vào hàng chưa đọc, rồi người dùng CÀI CHÍNH CHÚNG,
  // mà chuông vẫn nhắc.
  //
  // Nhắc một bản đang nằm sẵn trong máy là vô nghĩa: thông báo phát hành chỉ đáng chú ý khi
  // nó là thứ mình CHƯA có. Cài xong là hết việc, khỏi cần bấm đọc thêm lần nữa.
  function chuaDoc(item) {
    if (item.kind === "update" && item.installed) return false;
    return !state.read.has(String(item.id));
  }
  function unreadItems() {
    return state.items.filter(chuaDoc);
  }
  function markRead(id) {
    state.read.add(String(id));
    saveRead();
    render();
  }
  function markAll() {
    if (state.tab === "mine") {
      // Thư riêng: đã-đọc nằm ở SERVER, nên đánh dấu ở đây phải đi qua API chứ không
      // chỉ tô lại màu trên máy này.
      state.thu.forEach(function (t) { t.read = true; });
      state.thuChuaDoc = 0;
      docThu({ all: true }).then(render);
      render();
      return;
    }
    state.items.forEach(function (item) { state.read.add(String(item.id)); });
    saveRead();
    render();
  }
  function kindLabel(kind) {
    if (kind === "marketing") return "Tin mới";
    if (kind === "community") return "Cộng đồng";
    return "Cập nhật";
  }
  function openUpdates() {
    closePanel();
    try {
      if (window.Alpine && Alpine.store("nav")) Alpine.store("nav").go("logs");
    } catch (e) {}
  }
  function openItem(item) {
    markRead(item.id);
    var action = item.action || (item.cta && item.cta.action);
    var url = safeUrl(item.cta && item.cta.url);
    if (url) {
      window.open(url, "_blank", "noopener");
      return;
    }
    if (item.kind === "update" || action === "changelog") openUpdates();
  }
  // ---------- Hòm thư "Của tôi" ----------
  function thoiGian(ts) {
    var d = new Date((Number(ts) || 0) * 1000);
    if (!ts || isNaN(d.getTime())) return "";
    var cach = (Date.now() - d.getTime()) / 1000;
    if (cach < 60) return "vừa xong";
    if (cach < 3600) return Math.floor(cach / 60) + " phút trước";
    if (cach < 86400) return Math.floor(cach / 3600) + " giờ trước";
    return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" }) + " " +
           d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  }
  function nhanLoai(kind) {
    if (kind === "report") return "Báo cáo";
    if (kind === "system") return "Hệ thống";
    return "Trả lời";
  }
  async function docThu(body) {
    try {
      var r = await fetch("/inbox/read", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      var d = await r.json();
      if (typeof d.unread === "number") state.thuChuaDoc = d.unread;
    } catch (e) {}
  }
  // Bấm một mẩu thư = quay về ĐÚNG hội thoại đã hỏi. Mở hội thoại MỚI ở đây là sai: toàn bộ
  // ngữ cảnh nằm trong hội thoại cũ, hỏi tiếp ở chỗ khác là phải kể lại từ đầu.
  function moThu(item) {
    item.read = true;
    docThu({ id: item.id }).then(render);
    if (!item.session_id) { render(); return; }
    closePanel();
    try {
      if (window.Alpine && Alpine.store("nav") && Alpine.store("nav").active !== "home"
          && Alpine.store("nav").active !== "chat") Alpine.store("nav").go("home");
    } catch (e) {}
    try { if (window.JavisSessions) window.JavisSessions.open(item.session_id); } catch (e) {}
  }
  function theThu(item) {
    var chua = !item.read ? " unread" : "";
    var phu = item.session_id ? "Mở lại hội thoại →" : "";
    return '<article class="noti-card' + chua + '" tabindex="0" role="button" data-thu-id="' + esc(item.id) + '">' +
      '<div class="noti-card-top"><span class="noti-kind ' + esc(item.kind || "answer") + '">' +
      esc(nhanLoai(item.kind)) + '</span><span class="noti-time">' + esc(thoiGian(item.ts)) + "</span></div>" +
      "<h4>" + esc(item.title || "Javis vừa gửi một tin") + "</h4>" +
      '<p class="noti-card-body">' + esc(item.body || "") + "</p>" +
      (phu ? '<span class="noti-cta">' + phu + "</span>" : "") + "</article>";
  }
  function veHomThu(list) {
    if (!state.thu.length) {
      list.innerHTML = '<div class="noti-empty">Chưa có thư nào.<br>Kết quả việc chạy nền, báo cáo định kỳ và nhắc hẹn sẽ về đây.</div>';
      return;
    }
    list.innerHTML = state.thu.slice(0, MAX_ITEMS).map(theThu).join("");
    list.querySelectorAll("[data-thu-id]").forEach(function (card) {
      function chay() {
        var it = state.thu.find(function (x) { return String(x.id) === card.dataset.thuId; });
        if (it) moThu(it);
      }
      card.addEventListener("click", chay);
      card.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); chay(); }
      });
    });
  }
  function chonTab(tab) {
    state.tab = tab === "news" ? "news" : "mine";
    try { localStorage.setItem(TAB_KEY, state.tab); } catch (e) {}
    state.visibleCount = PAGE_SIZE;
    render();
  }

  function render() {
    var trigger = byId("notificationTrigger");
    var badge = byId("notificationBadge");
    var list = byId("notificationList");
    var summary = byId("notificationSummary");
    if (!trigger || !badge || !list) return;
    var unread = unreadItems();
    // Chấm đỏ trên chuông đếm CẢ HAI tầng: thư riêng chưa đọc + tin chung chưa đọc. Chỉ đếm
    // một bên thì một kết quả công việc vừa về có thể không làm chuông đổi gì cả.
    var tong = unread.length + state.thuChuaDoc;
    trigger.classList.toggle("has-unread", tong > 0);
    badge.hidden = tong === 0;
    badge.textContent = tong > 99 ? "99+" : String(tong);
    if (summary) summary.textContent = tong
      ? tong + " tin chưa đọc"
      : "Bạn đã đọc hết";

    var tabMine = byId("notiTabMine"), tabNews = byId("notiTabNews");
    if (tabMine && tabNews) {
      tabMine.classList.toggle("active", state.tab === "mine");
      tabNews.classList.toggle("active", state.tab === "news");
      tabMine.setAttribute("aria-selected", state.tab === "mine" ? "true" : "false");
      tabNews.setAttribute("aria-selected", state.tab === "news" ? "true" : "false");
      var cM = byId("notiTabMineCount"), cN = byId("notiTabNewsCount");
      if (cM) { cM.hidden = !state.thuChuaDoc; cM.textContent = String(state.thuChuaDoc); }
      if (cN) { cN.hidden = !unread.length; cN.textContent = String(unread.length); }
    }
    if (state.tab === "mine") { veHomThu(list); return; }

    if (!state.items.length) {
      list.innerHTML = '<div class="noti-empty">Chưa có thông báo.<br>Các bản cập nhật và tin từ Javis OS sẽ xuất hiện tại đây.</div>';
      return;
    }
    var limited = state.items.slice(0, MAX_ITEMS);
    var visible = limited.slice(0, state.visibleCount);
    var cards = visible.map(function (item) {
      var id = String(item.id);
      // Dùng CHUNG một luật với con số trên chuông. Trước đây thẻ tự soi state.read, nên chỉ
      // cần hai chỗ lệch nhau một chút là chuông báo 0 mà thẻ vẫn tô đậm kiểu chưa đọc.
      var unreadClass = chuaDoc(item) ? " unread" : "";
      var kind = item.kind || "update";
      // Release chỉ cần tóm tắt; toàn bộ bullet đã có ở trang Nhật ký cập nhật.
      // Tin cộng đồng/marketing được giữ body nhưng clamp bằng CSS để card vẫn gọn.
      var body = kind !== "update" && item.body
        ? '<p class="noti-card-body">' + esc(item.body) + "</p>"
        : "";
      var ctaLabel = (item.cta && item.cta.label) || (kind === "update" ? "Xem chi tiết bản cập nhật →" : "");
      var cta = ctaLabel ? '<span class="noti-cta">' + esc(ctaLabel) + "</span>" : "";
      return '<article class="noti-card' + unreadClass + '" tabindex="0" role="button" data-noti-id="' + esc(id) + '">' +
        '<div class="noti-card-top"><span class="noti-kind ' + esc(kind) + '">' + esc(kindLabel(kind)) + '</span>' +
        '<span class="noti-time">' + esc(item.published_at || "") + "</span></div>" +
        "<h4>" + esc(item.title || "Thông báo") + "</h4>" +
        '<p class="noti-card-summary">' + esc(item.summary || "") + "</p>" + body + cta + "</article>";
    }).join("");
    var remaining = limited.length - visible.length;
    var loadMore = remaining > 0
      ? '<button class="noti-load-more" id="notificationLoadMore" type="button">Tải thêm ' +
        Math.min(PAGE_SIZE, remaining) + " thông báo ↓</button>"
      : "";
    list.innerHTML = cards + loadMore;
    list.querySelectorAll("[data-noti-id]").forEach(function (card) {
      function activate() {
        var item = state.items.find(function (x) { return String(x.id) === card.dataset.notiId; });
        if (item) openItem(item);
      }
      card.addEventListener("click", activate);
      card.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); activate(); }
      });
    });
    var moreButton = byId("notificationLoadMore");
    if (moreButton) moreButton.addEventListener("click", function () {
      state.visibleCount = Math.min(state.visibleCount + PAGE_SIZE, MAX_ITEMS);
      render();
    });
  }
  // Hòm thư tải RIÊNG và tải thường xuyên hơn /notifications: thư riêng là thứ vừa xảy ra,
  // còn changelog thì nửa tiếng mới đổi một lần. Nhốt chung một nhịp là hoặc thư về chậm,
  // hoặc hỏi GitHub quá dày.
  async function taiThu() {
    try {
      var d = await (await fetch("/inbox?limit=40", { cache: "no-store" })).json();
      state.thu = Array.isArray(d.items) ? d.items : [];
      state.thuChuaDoc = Number(d.unread) || 0;
      render();
    } catch (e) {}
  }

  async function load(force) {
    taiThu();
    if (state.loading || (!force && Date.now() - state.loadedAt < 300000)) return;
    state.loading = true;
    var list = byId("notificationList");
    if (!state.items.length && list && state.tab === "news") list.innerHTML = '<div class="noti-loading">Đang tải thông báo…</div>';
    try {
      var response = await fetch("/notifications", { cache: "no-store" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      var data = await response.json();
      state.items = Array.isArray(data.items) ? data.items : [];
      state.visibleCount = PAGE_SIZE;
      state.loadedAt = Date.now();
      firstRun(state.items);
      render();
    } catch (e) {
      if (list && state.tab === "news") list.innerHTML = '<div class="noti-empty">Chưa tải được thông báo.<br>Hãy kiểm tra kết nối rồi thử lại.</div>';
    } finally { state.loading = false; }
  }
  function openPanel() {
    var panel = byId("notificationPanel"), shade = byId("notificationShade"), trigger = byId("notificationTrigger");
    if (!panel || !trigger) return;
    panel.hidden = false; panel.setAttribute("aria-hidden", "false");
    if (shade) shade.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    load(false);
    veNutPush();
  }
  function closePanel() {
    var panel = byId("notificationPanel"), shade = byId("notificationShade"), trigger = byId("notificationTrigger");
    if (panel) { panel.hidden = true; panel.setAttribute("aria-hidden", "true"); }
    if (shade) shade.hidden = true;
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  }
  // ---------- Công tắc thông báo đẩy ----------
  // `loi`: thông báo vừa hỏng thì GIỮ NGUYÊN lý do trên màn hình. Bản đầu vẽ lại dòng ghi
  // chú mặc định ngay sau khi báo lỗi, nên người dùng bấm "Bật" thấy y hệt như chưa bấm -
  // không rõ là chưa chạy, đang chạy, hay đã hỏng.
  async function veNutPush(loi) {
    var hop = byId("notificationPush"), nut = byId("notificationPushToggle");
    var ghi = byId("notificationPushNote"), thu = byId("notificationPushTest");
    if (!hop || !nut || !window.JavisPush) return;
    hop.hidden = false;
    if (!JavisPush.batDuoc()) {
      // Không bấm được thì nói LÝ DO. Một cái nút bấm mãi không lên còn tệ hơn không có nút.
      nut.hidden = true; if (thu) thu.hidden = true;
      if (ghi) ghi.textContent = loi || JavisPush.lyDo();
      return;
    }
    nut.hidden = false;
    var on = await JavisPush.dangBat();
    nut.textContent = on ? "Tắt" : "Bật";
    nut.classList.toggle("primary", !on);
    if (thu) thu.hidden = !on;
    if (ghi) ghi.textContent = loi || (on
      ? "Đang bật trên trình duyệt này"
      : "Báo cả khi bạn không mở Javis");
    if (ghi) ghi.classList.toggle("loi", !!loi);
  }
  function gaNutPush() {
    var nut = byId("notificationPushToggle"), ghi = byId("notificationPushNote");
    var thu = byId("notificationPushTest");
    if (nut) nut.addEventListener("click", async function () {
      if (!window.JavisPush) return;
      nut.disabled = true;
      var dangBat = await JavisPush.dangBat();
      var r = dangBat ? await JavisPush.tat() : await JavisPush.bat();
      nut.disabled = false;
      await veNutPush(r.ok ? "" : (r.error || "Không bật được."));
    });
    if (thu) thu.addEventListener("click", async function () {
      thu.disabled = true;
      var r = await JavisPush.thu();
      thu.disabled = false;
      if (ghi) ghi.textContent = r.ok ? "Đã gửi thử - kiểm tra thông báo của máy." : (r.error || "Gửi thử hỏng.");
    });
  }

  function init() {
    var trigger = byId("notificationTrigger");
    if (!trigger) return;
    loadRead();
    try { state.tab = localStorage.getItem(TAB_KEY) === "news" ? "news" : "mine"; } catch (e) {}
    trigger.addEventListener("click", function () {
      byId("notificationPanel").hidden ? openPanel() : closePanel();
    });
    byId("notificationClose").addEventListener("click", closePanel);
    byId("notificationShade").addEventListener("click", closePanel);
    byId("notificationReadAll").addEventListener("click", markAll);
    byId("notificationRefresh").addEventListener("click", function () { load(true); });
    byId("notificationOpenUpdates").addEventListener("click", openUpdates);
    var tm = byId("notiTabMine"), tn = byId("notiTabNews");
    if (tm) tm.addEventListener("click", function () { chonTab("mine"); });
    if (tn) tn.addEventListener("click", function () { chonTab("news"); });
    gaNutPush();
    veNutPush();
    document.addEventListener("keydown", function (event) { if (event.key === "Escape") closePanel(); });
    document.addEventListener("visibilitychange", function () { if (!document.hidden) load(false); });
    load(true);

    // Deep-link từ thông báo đẩy: /?mo_thu=<id>. Mở panel rồi nhảy thẳng vào mẩu thư đó.
    try {
      var idTu = new URLSearchParams(location.search).get("mo_thu");
      if (idTu) {
        history.replaceState(null, "", location.pathname);   // đừng để tham số dính lại khi F5
        setTimeout(function () { moTheoId(idTu); }, 1200);
      }
    } catch (e) {}
  }

  async function moTheoId(id) {
    await taiThu();
    var it = state.thu.find(function (x) { return String(x.id) === String(id); });
    if (it) moThu(it); else openPanel();
  }

  // API cho phần còn lại của app: app.js gọi refresh() khi WebSocket báo có thư mới, push.js
  // gọi moTu() khi người dùng bấm vào thông báo của hệ điều hành.
  window.JavisInbox = {
    refresh: function () { taiThu(); },
    // Hội thoại đang mở thì thư của nó coi như đã đọc - không thì một kết quả bị đếm hai lần.
    docPhien: function (sid) {
      if (!sid) return;
      docThu({ session_id: sid }).then(function () { taiThu(); });
    },
    moTu: function (url) {
      var id = "";
      try { id = new URL(url, location.origin).searchParams.get("mo_thu") || ""; } catch (e) {}
      if (id && id !== "test") moTheoId(id); else openPanel();
    },
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
