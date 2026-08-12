// Hộp thư navbar: hợp nhất bản phát hành với thông báo cộng đồng/marketing.
(function () {
  var READ_KEY = "javis.notifications.read";
  var INIT_KEY = "javis.notifications.initialized";
  var MAX_ITEMS = 30;
  var PAGE_SIZE = 5;
  var state = { items: [], read: new Set(), loadedAt: 0, loading: false, visibleCount: PAGE_SIZE };

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
  function render() {
    var trigger = byId("notificationTrigger");
    var badge = byId("notificationBadge");
    var list = byId("notificationList");
    var summary = byId("notificationSummary");
    if (!trigger || !badge || !list) return;
    var unread = unreadItems();
    trigger.classList.toggle("has-unread", unread.length > 0);
    badge.hidden = unread.length === 0;
    badge.textContent = unread.length > 99 ? "99+" : String(unread.length);
    if (summary) summary.textContent = unread.length
      ? unread.length + " thông báo chưa đọc"
      : "Bạn đã đọc tất cả thông báo";

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
  async function load(force) {
    if (state.loading || (!force && Date.now() - state.loadedAt < 300000)) return;
    state.loading = true;
    var list = byId("notificationList");
    if (!state.items.length && list) list.innerHTML = '<div class="noti-loading">Đang tải thông báo…</div>';
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
      if (list) list.innerHTML = '<div class="noti-empty">Chưa tải được thông báo.<br>Hãy kiểm tra kết nối rồi thử lại.</div>';
    } finally { state.loading = false; }
  }
  function openPanel() {
    var panel = byId("notificationPanel"), shade = byId("notificationShade"), trigger = byId("notificationTrigger");
    if (!panel || !trigger) return;
    panel.hidden = false; panel.setAttribute("aria-hidden", "false");
    if (shade) shade.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    load(false);
  }
  function closePanel() {
    var panel = byId("notificationPanel"), shade = byId("notificationShade"), trigger = byId("notificationTrigger");
    if (panel) { panel.hidden = true; panel.setAttribute("aria-hidden", "true"); }
    if (shade) shade.hidden = true;
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  }
  function init() {
    var trigger = byId("notificationTrigger");
    if (!trigger) return;
    loadRead();
    trigger.addEventListener("click", function () {
      byId("notificationPanel").hidden ? openPanel() : closePanel();
    });
    byId("notificationClose").addEventListener("click", closePanel);
    byId("notificationShade").addEventListener("click", closePanel);
    byId("notificationReadAll").addEventListener("click", markAll);
    byId("notificationRefresh").addEventListener("click", function () { load(true); });
    byId("notificationOpenUpdates").addEventListener("click", openUpdates);
    document.addEventListener("keydown", function (event) { if (event.key === "Escape") closePanel(); });
    document.addEventListener("visibilitychange", function () { if (!document.hidden) load(false); });
    load(true);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
