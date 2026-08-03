// ============================================================
// Javis - Sidebar "Lịch sử hội thoại" TRONG chat workspace (cột trái khi phóng to chat).
// chat-zoom.js tạo khung <aside id="chatSide"> và gọi window.JavisChatSide.mount/refresh;
// module này render nội dung: + Hội thoại mới, tìm kiếm, danh sách nhóm theo thời gian,
// đổi tên/xoá, highlight phiên đang mở. Mở phiên qua window.JavisSessions (app.js).
// (Thay panel trượt bên phải cũ - nút "Lịch sử" góc phải giờ mở thẳng workspace.)
// ============================================================
(function () {
  "use strict";

  function el(html) { var d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstChild; }
  function esc(s) { return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"); }
  function brain() { try { return (window.JavisSessions && window.JavisSessions.brain()) || "brain"; } catch (e) { return "brain"; } }
  function currentId() { try { return (window.JavisSessions && window.JavisSessions.current()) || null; } catch (e) { return null; } }

  function fmtT(ts) {
    try {
      var d = new Date(ts * 1000), now = new Date();
      if (d.toDateString() === now.toDateString())
        return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
      var dd = String(d.getDate()).padStart(2, "0") + "/" + String(d.getMonth() + 1).padStart(2, "0");
      return d.getFullYear() === now.getFullYear() ? dd : dd + "/" + String(d.getFullYear()).slice(2);
    } catch (e) { return ""; }
  }

  function groupOf(ts) {
    var d0 = new Date(); d0.setHours(0, 0, 0, 0);
    var start = d0.getTime() / 1000;
    if (ts >= start) return "Hôm nay";
    if (ts >= start - 86400) return "Hôm qua";
    if (ts >= start - 6 * 86400) return "7 ngày qua";
    return "Cũ hơn";
  }

  var side = null, listEl = null, searchEl = null, searchTimer = null, refreshTimer = null;
  // Cột trái có HAI tab: hội thoại và cây thư mục brain. Nhớ tab đã chọn qua localStorage -
  // ai dùng cây làm chính thì mỗi lần mở chat lại phải bấm sang là phiền vô ích.
  var TAB_KEY = "javis.chatside.tab";
  var tabHienTai = "chat", cayEl = null, cayCtl = null;

  function tabDaLuu() {
    try { return localStorage.getItem(TAB_KEY) === "files" ? "files" : "chat"; }
    catch (e) { return "chat"; }
  }

  // Danh sách chỉ hiện PAGE mục đầu, bấm "Xem thêm" mở thêm PAGE nữa.
  // shown = số mục đang hiện; giữ nguyên qua các lần refresh, chỉ reset khi đổi brain.
  var PAGE = 20, shown = PAGE, lastBrain = null;
  // Kết quả /sessions gần nhất. Prefetch lúc app load để bấm Lịch sử là danh sách hiện
  // NGAY từ cache (fetch mới vẫn chạy nền đè lên sau) - trước đây mở panel mới bắt đầu
  // debounce 150ms + fetch nên user thấy "Đang tải…" delay rõ.
  var cached = null;   // {brain, items}

  async function fetchList() {
    var b = brain();
    var r = await fetch("/sessions?brain=" + encodeURIComponent(b) + "&limit=" + (shown + 1));
    var data = await r.json();
    cached = { brain: b, items: data.sessions || [] };
    return cached;
  }

  function mount(container) {
    if (!container) return;
    side = container;
    shown = PAGE;
    lastBrain = brain();
    side.innerHTML =
      '<div class="cside-tabs">' +
        '<button class="cside-tab" data-tab="chat" type="button">Hội thoại</button>' +
        '<button class="cside-tab" data-tab="files" type="button">Thư mục</button>' +
      '</div>' +
      '<div class="cside-pane" data-pane="chat">' +
        '<button class="cside-new" type="button">＋ Hội thoại mới</button>' +
        '<input class="cside-search" placeholder="Tìm trong mọi hội thoại…">' +
        '<div class="cside-list"></div>' +
      '</div>' +
      '<div class="cside-pane ftree" data-pane="files"></div>';
    listEl = side.querySelector(".cside-list");
    searchEl = side.querySelector(".cside-search");
    cayEl = side.querySelector('[data-pane="files"]');
    cayCtl = null;
    side.querySelector(".cside-new").onclick = function () {
      if (window.JavisSessions) window.JavisSessions.new();
      closeDrawerIfNarrow();
    };
    searchEl.oninput = function () {
      clearTimeout(searchTimer);
      var q = searchEl.value.trim();
      searchTimer = setTimeout(function () { q ? doSearch(q) : loadList(); }, 280);
    };
    side.querySelectorAll(".cside-tab").forEach(function (b) {
      b.onclick = function () { chonTab(b.dataset.tab); };
    });
    loadList();   // lần đầu mở panel: nạp THẲNG, không qua debounce 150ms của refresh()
    chonTab(tabDaLuu());
  }

  /**
   * Đổi tab. Cây thư mục dựng LƯỜI - lần đầu bấm sang mới mount, vì đa số lượt mở chat là để
   * chat chứ không phải duyệt file, mà mount là một lượt gọi mạng.
   */
  function chonTab(tab) {
    if (!side) return;
    tabHienTai = tab === "files" ? "files" : "chat";
    try { localStorage.setItem(TAB_KEY, tabHienTai); } catch (e) {}
    side.querySelectorAll(".cside-tab").forEach(function (b) {
      b.classList.toggle("active", b.dataset.tab === tabHienTai);
    });
    side.querySelectorAll(".cside-pane").forEach(function (p) {
      p.classList.toggle("on", p.dataset.pane === tabHienTai);
    });
    if (tabHienTai === "files" && cayEl && window.JavisFileTree) {
      if (!cayCtl) cayCtl = window.JavisFileTree.mount(cayEl, { brain: brain });
      else cayCtl.refresh();
    }
  }

  function refresh() {
    if (!side) return;
    var b = brain();
    if (b !== lastBrain) {
      lastBrain = b; shown = PAGE;
      // Đổi brain là đổi luôn cây file. Không dựng lại thì tab Thư mục còn treo cây của brain
      // CŨ, mở file ra là mở nhầm brain - im lặng và rất khó ngờ.
      if (cayCtl) cayCtl.reload();
    }
    // debounce nhẹ: response + notifySessions có thể bắn sát nhau
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(function () {
      var q = searchEl && searchEl.value.trim();
      q ? doSearch(q) : loadList();
    }, 150);
  }

  // Màn hẹp: cột lịch sử là drawer trượt đè lên khung chat, nên chọn xong phải tự đóng.
  // Mốc 860px khớp @media của trang Trò chuyện (console.js _injectChatCss); lớp nổi
  // .chat-stage cũ dùng mốc 900 đã bỏ cùng lớp đó.
  function closeDrawerIfNarrow() {
    if (window.innerWidth >= 860) return;
    var page = document.getElementById("chatPage");
    if (page) page.classList.remove("side-open");
  }

  function openSession(id) {
    if (window.JavisSessions) window.JavisSessions.open(id);
    closeDrawerIfNarrow();
  }

  async function loadList() {
    if (!listEl) return;
    // Khung đang trống: vẽ ngay từ cache prefetch (nếu đúng brain) cho hết cảm giác delay;
    // không có cache mới hiện "Đang tải…". Các lần sau giữ danh sách cũ cho khỏi nháy.
    if (!listEl.querySelector(".cside-item")) {
      if (cached && cached.brain === brain() && cached.items.length) {
        renderList(cached.items.slice(0, shown), cached.items.length > shown);
      } else {
        listEl.innerHTML = '<div class="cside-empty">Đang tải…</div>';
      }
    }
    try {
      // Lấy dư 1 mục để biết còn hội thoại phía sau hay không.
      var c = await fetchList();
      renderList(c.items.slice(0, shown), c.items.length > shown);
    } catch (e) {
      // Lỗi mạng thoáng qua: còn danh sách (từ cache) thì giữ nguyên, đừng đập đi
      if (!listEl.querySelector(".cside-item")) listEl.innerHTML = '<div class="cside-empty">Lỗi tải danh sách.</div>';
    }
  }

  function renderList(items, hasMore) {
    if (!items.length) {
      listEl.innerHTML = '<div class="cside-empty">Chưa có hội thoại nào.<br>Bấm ＋ để bắt đầu.</div>';
      return;
    }
    // Bấm "Xem thêm" render lại từ đầu → giữ chỗ cuộn để không bị nhảy lên trên.
    var keepScroll = listEl.scrollTop;
    listEl.innerHTML = "";
    var cur = currentId(), lastGroup = null;
    items.forEach(function (s) {
      var g = groupOf(s.updated_at || 0);
      if (g !== lastGroup) {
        listEl.appendChild(el('<div class="cside-group">' + g + '</div>'));
        lastGroup = g;
      }
      var eng = (s.engine || "").toString().slice(0, 10);
      // Kênh sinh ra hội thoại: web là mặc định nên khỏi ghi, Telegram thì gắn nhãn để
      // khỏi lẫn với cuộc tự mở trên dashboard.
      var ch = (s.channel || "").toString();
      var chLabel = ch === "telegram" ? "TG" : (ch && ch !== "web" ? ch.slice(0, 8) : "");
      var isRun = !!(window.JavisRunning && window.JavisRunning.has(s.id));
      var item = el('<div class="cside-item' + (s.id === cur ? " active" : "") + (isRun ? " running" : "") + '">' +
        '<div class="ci-title">' + (isRun ? '<span class="ci-run" title="Đang trả lời">' + ic("loader", { cls: "ic-spin" }) + '</span> ' : '') + esc(s.title || s.preview || "(chưa đặt tên)") + '</div>' +
        '<div class="ci-meta"><span>' + fmtT(s.updated_at) + '</span>' +
        (chLabel ? '<span class="ci-badge">' + esc(chLabel) + '</span>' : '') +
        (eng ? '<span class="ci-badge">' + esc(eng) + '</span>' : '') +
        '<span>' + (s.msg_count || 0) + ' tin</span>' +
        '<span class="act"><span class="ren" title="Đổi tên">' + ic("pencil") + '</span><span class="del" title="Xoá">' + ic("trash-2") + '</span></span>' +
        '</div></div>');
      // Bấm phải dò theo TỔ TIÊN, không so class của đúng node bị bấm. Nội dung .ren/.del là
      // một <svg> (ic() trả chuỗi SVG), nên chạm vào icon thì e.target LÀ cái svg chứ không
      // phải cái span - so classList kiểu cũ luôn trượt và click rơi xuống openSession.
      // Đó chính là lỗi "hover vào không xoá/đổi tên được": nút có hiện, bấm lại mở hội thoại.
      item.onclick = function (e) {
        var hit = e.target && e.target.closest ? e.target.closest(".ren, .del") : null;
        if (hit && hit.classList.contains("del")) { e.stopPropagation(); delSession(s); return; }
        if (hit && hit.classList.contains("ren")) { e.stopPropagation(); renSession(s); return; }
        openSession(s.id);
      };
      listEl.appendChild(item);
    });
    if (hasMore) {
      var more = el('<button class="cside-more" type="button">Xem thêm ' + PAGE + '</button>');
      more.onclick = function () { shown += PAGE; loadList(); };
      listEl.appendChild(more);
    }
    listEl.scrollTop = keepScroll;
  }

  async function doSearch(q) {
    if (!listEl) return;
    listEl.innerHTML = '<div class="cside-empty">Đang tìm…</div>';
    try {
      var r = await fetch("/sessions/search?q=" + encodeURIComponent(q) + "&brain=" + encodeURIComponent(brain()) + "&limit=40");
      var data = await r.json();
      var hits = data.results || [];
      if (!hits.length) { listEl.innerHTML = '<div class="cside-empty">Không tìm thấy.</div>'; return; }
      listEl.innerHTML = "";
      hits.forEach(function (h) {
        var snip = esc(h.snippet || "").replace(/&gt;&gt;&gt;/g, "<b>").replace(/&lt;&lt;&lt;/g, "</b>");
        var item = el('<div class="cside-item">' +
          '<div class="ci-title">' + esc(h.title || "(chưa đặt tên)") + '</div>' +
          '<div class="ci-snip">' + snip + '</div>' +
          '<div class="ci-meta"><span>' + fmtT(h.ts) + '</span></div></div>');
        item.onclick = function () { openSession(h.session_id); };
        listEl.appendChild(item);
      });
    } catch (e) { listEl.innerHTML = '<div class="cside-empty">Lỗi tìm kiếm.</div>'; }
  }

  async function delSession(s) {
    if (!confirm('Xoá hội thoại "' + (s.title || s.preview || "(chưa đặt tên)") + '"?')) return;
    try { await fetch("/sessions/" + encodeURIComponent(s.id) + "/delete", { method: "POST" }); } catch (e) {}
    if (s.id === currentId() && window.JavisSessions) window.JavisSessions.new();
    refresh();
  }

  async function renSession(s) {
    var t = prompt("Tên mới cho hội thoại:", s.title || s.preview || "");
    if (t == null) return;
    try {
      var fd = new FormData(); fd.append("title", t);
      await fetch("/sessions/" + encodeURIComponent(s.id) + "/rename", { method: "POST", body: fd });
    } catch (e) {}
    refresh();
  }

  window.JavisChatSide = { mount: mount, refresh: refresh, tab: chonTab };

  // Cập nhật khi có lượt chat mới / đổi phiên / đổi brain
  window.addEventListener("javis:sessions-changed", refresh);

  function bindGlobal() {
    var gs = document.getElementById("graphSource");
    if (gs) gs.addEventListener("change", refresh);
    // Nút "Lịch sử" → mở thẳng workspace với sidebar. Đặt INLINE trong hàng nút header
    // (.hud-actions) để không đè lên nút Cài đặt/Reset; fallback về body nếu chưa có header.
    var btn = el('<div id="jv-sess-btn" title="Lịch sử hội thoại">' + ic("history") + ' <span>Lịch sử</span></div>');
    btn.onclick = function () { if (window.JavisChatStage) window.JavisChatStage.showSide(); };
    var host = document.querySelector(".hud-actions");
    (host || document.body).appendChild(btn);
    // Prefetch danh sách sau khi cockpit đã yên: bấm Lịch sử lần đầu là có sẵn dữ liệu
    setTimeout(function () { fetchList().catch(function () {}); }, 1500);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bindGlobal);
  else bindGlobal();
})();
