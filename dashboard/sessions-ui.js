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
  var tabHienTai = "chat", cayEl = null;

  function tabDaLuu() {
    try { return localStorage.getItem(TAB_KEY) === "files" ? "files" : "chat"; }
    catch (e) { return "chat"; }
  }

  // ===== Project (nhóm hội thoại) =====
  // Project đang mở là CHỖ ĐỨNG của người dùng trên MỘT máy, không phải dữ liệu chung, nên
  // nhớ ở localStorage theo brain chứ không lưu server. Ba giá trị: "" = tất cả,
  // "none" = các cuộc chưa xếp nhóm, còn lại là id project ("none" là chuỗi cố định, không
  // bao giờ đụng id thật vì id là uuid hex).
  var PROJ_KEY = "javis.chatside.project";
  var projects = [];      // [{id,name,icon,session_count}] của brain đang xem
  var projBar = null;

  function projKey() { return PROJ_KEY + "." + brain(); }
  function curProject() {
    try { return localStorage.getItem(projKey()) || ""; } catch (e) { return ""; }
  }
  function setCurProject(id) {
    try {
      if (id) localStorage.setItem(projKey(), id);
      else localStorage.removeItem(projKey());
    } catch (e) {}
  }
  function projById(id) {
    for (var i = 0; i < projects.length; i++) if (projects[i].id === id) return projects[i];
    return null;
  }
  function projLabel() {
    var cur = curProject();
    if (!cur) return "Tất cả hội thoại";
    if (cur === "none") return "Chưa xếp nhóm";
    var p = projById(cur);
    return p ? ((p.icon ? p.icon + " " : "") + p.name) : "Tất cả hội thoại";
  }

  async function post(url, fields) {
    var fd = new FormData();
    Object.keys(fields || {}).forEach(function (k) { fd.append(k, fields[k]); });
    try { return await (await fetch(url, { method: "POST", body: fd })).json(); }
    catch (e) { return { error: String(e) }; }
  }

  async function loadProjects() {
    try {
      var d = await (await fetch("/projects?brain=" + encodeURIComponent(brain()))).json();
      projects = d.projects || [];
    } catch (e) { projects = []; }
    // Project đang mở vừa bị xoá (ở tab khác, hoặc brain khác) → về "Tất cả". Không có nhát
    // này thì danh sách rỗng trơn mà người dùng không hiểu vì sao.
    var cur = curProject();
    if (cur && cur !== "none" && !projById(cur)) setCurProject("");
    renderProjBar();
  }

  function renderProjBar() {
    if (!projBar) return;
    var cur = curProject();
    projBar.innerHTML =
      '<button class="cs-proj-cur" type="button" title="Chọn nhóm hội thoại">' +
        '<span class="cs-proj-name">' + esc(projLabel()) + '</span>' +
        '<span class="cs-proj-caret">' + ic("chevron-down") + '</span>' +
      '</button>' +
      (cur ? '<button class="cs-proj-x" type="button" title="Bỏ lọc, xem tất cả">' + ic("x") + '</button>' : '') +
      '<button class="cs-proj-add" type="button" title="Tạo project mới">' + ic("folder-plus") + '</button>';
    projBar.querySelector(".cs-proj-cur").onclick = function (e) { openProjMenu(e.currentTarget); };
    projBar.querySelector(".cs-proj-add").onclick = function () { newProject(); };
    var x = projBar.querySelector(".cs-proj-x");
    if (x) x.onclick = function () { chonProject(""); };
  }

  function chonProject(id) {
    setCurProject(id);
    shown = PAGE;
    cached = null;          // bộ lọc đổi thì cache của bộ lọc cũ không dùng lại được
    renderProjBar();
    loadList();
  }

  function openProjMenu(anchor) {
    var cur = curProject();
    var rows = [
      { label: "Tất cả hội thoại", on: !cur, run: function () { chonProject(""); } },
      { label: "Chưa xếp nhóm", on: cur === "none", run: function () { chonProject("none"); } },
    ];
    if (projects.length) rows.push({ sep: true });
    projects.forEach(function (p) {
      rows.push({
        label: (p.icon ? p.icon + " " : "") + p.name,
        right: String(p.session_count || 0),
        on: cur === p.id,
        run: function () { chonProject(p.id); },
        acts: [
          { icon: "smile", title: "Đổi icon", run: function () { pickIcon(anchor, p.icon || "", function (v) { post("/projects/" + encodeURIComponent(p.id) + "/update", { icon: v }).then(loadProjects); }); } },
          { icon: "pencil", title: "Đổi tên", run: function () { renameProject(p); } },
          { icon: "trash-2", title: "Xoá project", run: function () { delProject(p); } },
        ],
      });
    });
    rows.push({ sep: true });
    rows.push({ label: "＋ Project mới", run: function () { newProject(); } });
    openMenu(anchor, rows);
  }

  async function newProject() {
    var name = prompt("Tên project (nhóm hội thoại):", "");
    if (name == null || !name.trim()) return;
    var r = await post("/projects", { name: name.trim(), brain: brain() });
    await loadProjects();
    if (r && r.id) chonProject(r.id);
  }

  async function renameProject(p) {
    var name = prompt("Tên mới cho project:", p.name || "");
    if (name == null || !name.trim()) return;
    await post("/projects/" + encodeURIComponent(p.id) + "/update", { name: name.trim() });
    await loadProjects();
    renderProjBar();
  }

  async function delProject(p) {
    // Nói THẲNG hội thoại không mất. Người dùng gom nhóm để đỡ rối, không ai muốn một cú bấm
    // nhầm cuốn theo cả tháng trò chuyện - và cũng không có đường hoàn tác nào.
    var n = p.session_count || 0;
    if (!confirm('Xoá project "' + (p.name || "") + '"?\n\n' +
                 (n ? n + " hội thoại trong đó sẽ được gỡ khỏi nhóm chứ KHÔNG bị xoá."
                    : "Project này chưa có hội thoại nào."))) return;
    await post("/projects/" + encodeURIComponent(p.id) + "/delete", {});
    if (curProject() === p.id) setCurProject("");
    await loadProjects();
    loadList();
  }

  // ===== Popover dùng chung cho menu project và bộ chọn icon =====
  var menuEl = null;
  function closeMenu() {
    if (menuEl && menuEl.parentNode) menuEl.parentNode.removeChild(menuEl);
    menuEl = null;
  }
  function placeMenu(anchor) {
    document.body.appendChild(menuEl);
    var rc = anchor.getBoundingClientRect();
    var w = menuEl.offsetWidth, h = menuEl.offsetHeight;
    menuEl.style.left = Math.max(8, Math.min(rc.left, window.innerWidth - w - 8)) + "px";
    var top = rc.bottom + 4;
    if (top + h > window.innerHeight - 8) top = Math.max(8, rc.top - h - 4);
    menuEl.style.top = top + "px";
  }
  function openMenu(anchor, rows) {
    closeMenu();
    menuEl = document.createElement("div");
    menuEl.className = "cs-menu";
    rows.forEach(function (r) {
      if (r.sep) { menuEl.appendChild(el('<div class="cs-menu-sep"></div>')); return; }
      var row = el('<div class="cs-menu-row' + (r.on ? " on" : "") + '">' +
        '<button class="cs-menu-main" type="button"><span class="cs-menu-lbl">' + esc(r.label) + '</span>' +
        (r.right ? '<span class="cs-menu-right">' + esc(r.right) + '</span>' : '') + '</button>' +
        '<span class="cs-menu-acts"></span></div>');
      row.querySelector(".cs-menu-main").onclick = function () { closeMenu(); r.run(); };
      var acts = row.querySelector(".cs-menu-acts");
      (r.acts || []).forEach(function (a) {
        var b = el('<button class="cs-menu-act" type="button" title="' + esc(a.title) + '">' + ic(a.icon) + '</button>');
        b.onclick = function (ev) { ev.stopPropagation(); closeMenu(); a.run(); };
        acts.appendChild(b);
      });
      menuEl.appendChild(row);
    });
    placeMenu(anchor);
  }

  // Bộ chọn icon: một nắm emoji hay dùng + ô gõ tay. KHÔNG kéo thư viện emoji-picker nào về -
  // nó nặng hơn cả tính năng, mà bàn phím hệ điều hành nào cũng có sẵn bảng emoji.
  var EMOJI = ["📌","⭐","🔥","💡","📊","💰","🛒","📦","📈","🎯","🧠","📝","📅","✅","⚙️","🚀",
               "🎨","🖼️","📷","🎵","🍜","☕","🏠","🏢","👤","👥","💬","📣","🔧","🔍","🧪","🧾",
               "❤️","😀","😎","🤖","🌱","🌙","⚡","🐛"];
  function pickIcon(anchor, cur, onPick) {
    closeMenu();
    menuEl = document.createElement("div");
    menuEl.className = "cs-menu cs-emo";
    var grid = el('<div class="cs-emo-grid"></div>');
    EMOJI.forEach(function (em) {
      var b = el('<button class="cs-emo-b' + (em === cur ? " on" : "") + '" type="button">' + esc(em) + "</button>");
      b.onclick = function () { closeMenu(); onPick(em); };
      grid.appendChild(b);
    });
    menuEl.appendChild(grid);
    var foot = el('<div class="cs-emo-foot">' +
      '<input class="cs-emo-in" maxlength="8" placeholder="Dán emoji khác…" value="' + esc(cur) + '">' +
      '<button class="cs-emo-clear" type="button">Xoá icon</button></div>');
    foot.querySelector(".cs-emo-in").onkeydown = function (ev) {
      if (ev.key !== "Enter") return;
      var v = ev.currentTarget.value.trim();
      closeMenu(); onPick(v);
    };
    foot.querySelector(".cs-emo-clear").onclick = function () { closeMenu(); onPick(""); };
    menuEl.appendChild(foot);
    placeMenu(anchor);
  }

  // Bấm ra ngoài thì đóng. Dùng pha CAPTURE để chạy trước handler của chính hàng hội thoại
  // (nếu không, bấm ra ngoài vừa đóng menu vừa mở nhầm một hội thoại).
  document.addEventListener("mousedown", function (e) {
    if (menuEl && !menuEl.contains(e.target)) closeMenu();
  }, true);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeMenu(); });

  // Danh sách chỉ hiện PAGE mục đầu, bấm "Xem thêm" mở thêm PAGE nữa.
  // shown = số mục đang hiện; giữ nguyên qua các lần refresh, chỉ reset khi đổi brain.
  var PAGE = 20, shown = PAGE, lastBrain = null;
  // Kết quả /sessions gần nhất. Prefetch lúc app load để bấm Lịch sử là danh sách hiện
  // NGAY từ cache (fetch mới vẫn chạy nền đè lên sau) - trước đây mở panel mới bắt đầu
  // debounce 150ms + fetch nên user thấy "Đang tải…" delay rõ.
  var cached = null;   // {brain, items}

  async function fetchList() {
    var b = brain(), p = curProject();
    var r = await fetch("/sessions?brain=" + encodeURIComponent(b) + "&limit=" + (shown + 1) +
                        (p ? "&project=" + encodeURIComponent(p) : ""));
    var data = await r.json();
    cached = { brain: b, project: p, items: data.sessions || [] };
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
        '<div class="cside-proj"></div>' +
        '<input class="cside-search" placeholder="Tìm trong mọi hội thoại…">' +
        '<div class="cside-list"></div>' +
      '</div>' +
      '<div class="cside-pane" data-pane="files"></div>';
    listEl = side.querySelector(".cside-list");
    searchEl = side.querySelector(".cside-search");
    projBar = side.querySelector(".cside-proj");
    cayEl = side.querySelector('[data-pane="files"]');
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
    renderProjBar();   // vẽ ngay từ localStorage, khỏi nháy thanh trống trong lúc chờ /projects
    loadProjects();
    loadList();   // lần đầu mở panel: nạp THẲNG, không qua debounce 150ms của refresh()
    chonTab(tabDaLuu());
  }

  /**
   * Đổi tab. Tab "Thư mục" MƯỢN chính panel Vault ở cột trái màn chính chứ không dựng cây
   * riêng - cùng một cây, chỉ đổi chỗ đứng. Nhờ vậy mọi thứ cây đó đã có (tìm theo tên và
   * theo nội dung, tạo file, tạo thư mục, làm mới, tô sáng file đang mở) đi theo luôn, và
   * không có bản thứ hai để trôi lệch.
   *
   * Trả về ngay khi bấm sang tab Hội thoại: node chỉ có một, để nó nằm trong pane đang ẩn thì
   * màn chính mất panel Vault.
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
    if (!window.JavisVaultPanel) return;
    if (tabHienTai === "files" && cayEl) window.JavisVaultPanel.borrow(cayEl);
    else window.JavisVaultPanel.giveBack();
  }

  function refresh() {
    if (!side) return;
    var b = brain();
    if (b !== lastBrain) {
      lastBrain = b; shown = PAGE;
      // Project gắn theo brain, nên đổi brain là danh sách project đổi theo. Không nạp lại thì
      // thanh trên đầu còn treo tên project của brain cũ mà bộ lọc lại đang trỏ vào id lạ.
      renderProjBar(); loadProjects();
      // Cây Vault tự dựng lại khi đổi brain (console.js theo dõi #graphSource), nên ở đây
      // không phải làm gì thêm - đó chính là cái lợi của việc mượn node thay vì nuôi bản hai.
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
      if (cached && cached.brain === brain() && cached.project === curProject() && cached.items.length) {
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
      // Mục ghim gom thành MỘT nhóm trên đầu, không xếp theo thời gian nữa - ghim chính là để
      // thoát khỏi thứ tự thời gian. Server đã sắp pinned trước nên chỉ cần đổi nhãn nhóm.
      var g = s.pinned ? "Đã ghim" : groupOf(s.updated_at || 0);
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
      var icon = (s.icon || "").toString();
      var item = el('<div class="cside-item' + (s.id === cur ? " active" : "") + (isRun ? " running" : "") + '">' +
        '<div class="ci-title">' + (isRun ? '<span class="ci-run" title="Đang trả lời">' + ic("loader", { cls: "ic-spin" }) + '</span> ' : '') +
        (icon ? '<span class="ci-icon">' + esc(icon) + '</span> ' : '') +
        esc(s.title || s.preview || "(chưa đặt tên)") + '</div>' +
        '<div class="ci-meta"><span>' + fmtT(s.updated_at) + '</span>' +
        (chLabel ? '<span class="ci-badge">' + esc(chLabel) + '</span>' : '') +
        (eng ? '<span class="ci-badge">' + esc(eng) + '</span>' : '') +
        '<span>' + (s.msg_count || 0) + ' tin</span>' +
        '<span class="act">' +
          '<span class="pin' + (s.pinned ? " on" : "") + '" title="' + (s.pinned ? "Bỏ ghim" : "Ghim lên đầu") + '">' + ic("pin") + '</span>' +
          '<span class="emo" title="Đổi icon">' + ic("smile") + '</span>' +
          '<span class="mov" title="Chuyển vào project">' + ic("folder") + '</span>' +
          '<span class="ren" title="Đổi tên">' + ic("pencil") + '</span>' +
          '<span class="del" title="Xoá">' + ic("trash-2") + '</span>' +
        '</span>' +
        '</div></div>');
      // Ba nút mới gắn handler RIÊNG kèm stopPropagation, không nhét thêm nhánh vào
      // item.onclick bên dưới. Handler đó là thứ test_chat_side_actions.js bóc ra chạy thật
      // với đúng năm tham số của nó; thêm tên hàm lạ vào là test nổ ReferenceError.
      item.querySelector(".pin").onclick = function (ev) { ev.stopPropagation(); togglePin(s); };
      item.querySelector(".emo").onclick = function (ev) {
        ev.stopPropagation();
        pickIcon(ev.currentTarget, icon, function (v) {
          post("/sessions/" + encodeURIComponent(s.id) + "/icon", { icon: v }).then(refresh);
        });
      };
      item.querySelector(".mov").onclick = function (ev) { ev.stopPropagation(); moveMenu(ev.currentTarget, s); };
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

  async function togglePin(s) {
    await post("/sessions/" + encodeURIComponent(s.id) + "/pin", { pinned: s.pinned ? "0" : "1" });
    cached = null;   // thứ tự vừa đổi → cache cũ vẽ ra danh sách sai thứ tự
    loadList();
  }

  function moveMenu(anchor, s) {
    var rows = [{
      label: "Bỏ khỏi nhóm", on: !s.project_id,
      run: function () { moveTo(s, ""); },
    }];
    if (projects.length) rows.push({ sep: true });
    projects.forEach(function (p) {
      rows.push({
        label: (p.icon ? p.icon + " " : "") + p.name,
        on: s.project_id === p.id,
        run: function () { moveTo(s, p.id); },
      });
    });
    if (!projects.length) {
      rows.push({ sep: true });
      rows.push({ label: "＋ Project mới", run: function () { newProject(); } });
    }
    openMenu(anchor, rows);
  }

  async function moveTo(s, pid) {
    await post("/sessions/" + encodeURIComponent(s.id) + "/project",
               { project_id: pid, brain: brain() });
    await loadProjects();      // số hội thoại của project vừa đổi
    cached = null;
    loadList();
  }

  window.JavisChatSide = { mount: mount, refresh: refresh, tab: chonTab };
  // Cầu nối cho app.js: hội thoại VỪA được mint id trong lúc đang mở một project thì tự rơi
  // vào project đó. Phải gắn nhãn ngay tại lúc bấm gửi vì id sinh ở phía client, còn hàng
  // trong DB thì tới lượt server xử lý mới có - endpoint tự tạo hàng khi nhận kèm brain.
  window.JavisProjects = {
    current: curProject,
    claim: function (sid) {
      var p = curProject();
      if (!sid || !p || p === "none") return;
      post("/sessions/" + encodeURIComponent(sid) + "/project",
           { project_id: p, brain: brain() });
    },
  };

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
