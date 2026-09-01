// ============================================================
// Javis - Sidebar "Lịch sử hội thoại" TRONG chat workspace (cột trái khi phóng to chat).
// chat-zoom.js tạo khung <aside id="chatSide"> và gọi window.JavisChatSide.mount/refresh;
// module này render nội dung: + Hội thoại mới, tìm kiếm, danh sách nhóm theo thời gian,
// đổi tên/xoá, highlight phiên đang mở. Mở phiên qua window.JavisSessions (app.js).
// (Thay panel trượt bên phải cũ - nút "Lịch sử" góc phải giờ mở thẳng workspace.)
// ============================================================
(function () {
  "use strict";

  // Locale để định dạng số/ngày. Lấy từ i18n chứ KHÔNG khoá "vi-VN": người dùng đổi
  // ngôn ngữ giao diện thì ngày giờ phải đổi theo, nếu không thì nửa màn hình tiếng Anh
  // mà ngày vẫn dd/mm/yyyy kiểu Việt.
  const LOC = () => (window.JavisI18n && JavisI18n.locale()) || "vi-VN";
  function el(html) { var d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstChild; }
  function esc(s) { return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"); }
  function brain() { try { return (window.JavisSessions && window.JavisSessions.brain()) || "brain"; } catch (e) { return "brain"; } }
  function currentId() { try { return (window.JavisSessions && window.JavisSessions.current()) || null; } catch (e) { return null; } }

  function fmtT(ts) {
    try {
      var d = new Date(ts * 1000), now = new Date();
      if (d.toDateString() === now.toDateString())
        return d.toLocaleTimeString(LOC(), { hour: "2-digit", minute: "2-digit" });
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
  // Nhãn project trả về HTML (icon là thẻ <svg>, không phải ký tự) nên phần CHỮ phải tự
  // escape ở đây - tên project do người dùng gõ.
  function projLabelHtml() {
    var cur = curProject();
    if (!cur) return ic("layers") + " Tất cả hội thoại";
    if (cur === "none") return ic("circle") + " Chưa xếp nhóm";
    var p = projById(cur);
    if (!p) return ic("layers") + " Tất cả hội thoại";
    return projIcon(p) + " " + esc(p.name);
  }

  // Icon của một project. Chưa đặt thì lấy icon thư mục làm mặc định - hàng nào cũng có icon
  // thì mắt quét theo cột icon được, và nhìn là biết chỗ này đổi icon được.
  function projIcon(p) { return iconHtml((p || {}).icon) || ic("folder"); }

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
    renderProjChip();
  }

  function renderProjBar() {
    if (!projBar) return;
    var cur = curProject();
    projBar.innerHTML =
      '<button class="cs-proj-cur" type="button" title="Chọn nhóm hội thoại">' +
        '<span class="cs-proj-name">' + projLabelHtml() + '</span>' +
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
    renderProjChip();
    loadList();
  }

  function openProjMenu(anchor) {
    var cur = curProject();
    var rows = [
      { label: "Tất cả hội thoại", icon: "layers", on: !cur, run: function () { chonProject(""); } },
      { label: "Chưa xếp nhóm", icon: "circle", on: cur === "none", run: function () { chonProject("none"); } },
    ];
    if (projects.length) rows.push({ sep: true });
    projects.forEach(function (p) {
      rows.push({
        label: p.name,
        icon: p.icon || "folder",
        right: String(p.session_count || 0),
        on: cur === p.id,
        run: function () { chonProject(p.id); },
        acts: [
          // Chip ở khung chat chỉ hiện khi cuộc ĐANG MỞ thuộc project. Không có lối này thì
          // muốn sửa hướng dẫn của một project khác phải mở một cuộc trong đó trước.
          { icon: "sliders-horizontal", title: "Mở khung project",
            run: function () { closeMenu(); openProjDrawer(p.id); } },
          { icon: "palette", title: "Đổi icon", run: function () { pickIcon(anchor, p.icon || "", function (v) { post("/projects/" + encodeURIComponent(p.id) + "/update", { icon: v }).then(loadProjects); }); } },
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
    if (!r || !r.id) return;
    chonProject(r.id);
    // Mở sẵn một hội thoại trống: bộ lọc vừa trỏ vào project mới nên tin đầu tiên rơi đúng
    // vào đó (JavisProjects.claim). Rồi mở luôn khung project kèm banner chào - một project
    // rỗng thì chưa đổi được gì cho lượt chat nào, phải nói ra chỗ để đổ hướng dẫn vào.
    try { if (window.JavisSessions) window.JavisSessions.new(); } catch (e) {}
    quenPhienProj();
    pdOnboard = true;
    openProjDrawer(r.id);
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
    if (projChiTiet && projChiTiet.id === p.id) { projChiTiet = null; closeProjDrawer(); }
    quenPhienProj();
    if (curProject() === p.id) setCurProject("");
    await loadProjects();
    loadList();
  }

  // ============================================================
  // Khung project: hướng dẫn + tài liệu + link
  // ============================================================
  // Chip nằm ở thanh tiêu đề khung chat, bấm vào mở ngăn kéo này. Cả hai sống trong CÙNG
  // closure với danh sách project ở trên: một mảng `projects`, một chỗ biết brain nào đang
  // mở, nên không có bản thứ hai để trôi lệch.
  //
  // Chip nói về project CỦA LƯỢT CHAT, không phải bộ lọc cột trái. Hai thứ đó khác nhau và
  // server bơm hướng dẫn theo cái thứ nhất (`sessions.project_id`): mở lại một cuộc cũ thuộc
  // project A trong khi cột trái đang lọc project B thì Javis vẫn nhận hướng dẫn của A. Chip
  // mà đọc bộ lọc là nó nói dối đúng vào lúc người dùng cần tin nó nhất.

  var PROJ_INSTR_MAX = 4000;       // gương của PROJECT_INSTRUCTIONS_MAX (server/sessions.py)
  var projChiTiet = null;          // {id,name,icon,instructions,files,links} của project đang mở
  var projTab = "instr";
  var pdEl = null;                 // node ngăn kéo, dựng MỘT lần rồi gắn vào body
  var pdLuuTimer = null;
  var pdOnboard = false;           // banner chào chỉ hiện ngay sau khi tạo project
  var pdFormFile = false, pdFileMode = "search", pdFormLink = false;
  var pdHome = { brain: null, home: "" };   // gốc brain tính theo TRẦN duyệt, cho nhánh tải lên
  var phienProj = { sid: "", pid: "" };     // cache "phiên đang mở thuộc project nào"

  function pdT(k, bien) { return (window.t ? window.t(k, bien) : k); }

  /** Project ĐANG CÓ HIỆU LỰC cho lượt chat hiện tại. */
  async function duAnCuaLuot() {
    var sid = currentId();
    var loc = curProject();
    var locThat = (loc && loc !== "none") ? loc : "";
    // Chưa có phiên = khung chat trống. Tin sau sẽ được JavisProjects.claim() gắn vào đúng
    // project đang lọc, nên chip báo trước điều đó là đúng chứ không phải đoán.
    if (!sid) return locThat;
    if (phienProj.sid === sid) return phienProj.pid;
    var pid = "";
    try {
      var r = await fetch("/sessions/" + encodeURIComponent(sid) + "/meta");
      if (r.ok) {
        var d = await r.json();
        pid = (d && d.project_id) || "";
      } else {
        // 404 = id đã mint ở client nhưng chưa gửi tin nào, hàng trong DB chưa tồn tại.
        pid = locThat;
      }
    } catch (e) { return locThat; }   // mạng hỏng: đừng ghi cache một câu trả lời sai
    phienProj = { sid: sid, pid: pid };
    return pid;
  }

  function quenPhienProj() { phienProj = { sid: "", pid: "" }; }

  // ── Chip ─────────────────────────────────────────────────────────────────────
  async function renderProjChip() {
    var hosts = document.querySelectorAll(".proj-chip-host");
    if (!hosts.length) return;
    var pid = await duAnCuaLuot();
    var p = pid ? projById(pid) : null;
    // Mở thẳng trang chat sau F5 thì `projects` có thể chưa nạp. Nạp rồi thôi, KHÔNG gọi
    // loadProjects() ở đây (nó gọi ngược lại hàm này - vòng lặp vô tận).
    if (pid && !p && !projects.length) {
      try {
        var d = await (await fetch("/projects?brain=" + encodeURIComponent(brain()))).json();
        projects = d.projects || [];
        p = projById(pid);
      } catch (e) {}
    }
    var html = "";
    if (p) {
      var meta = "";
      if (p.file_count) meta += '<span class="pc-n">' + ic("file-text") + (p.file_count) + '</span>';
      if (p.link_count) meta += '<span class="pc-n">' + ic("link") + (p.link_count) + '</span>';
      var coGi = !!(p.has_instructions || p.file_count || p.link_count);
      html = '<button class="proj-chip' + (coGi ? " co-gi" : "") + '" type="button" title="' +
               esc(pdT("proj.chip_title")) + '">' +
               '<span class="pc-ico">' + projIcon(p) + '</span>' +
               '<span class="pc-name">' + esc(p.name) + '</span>' +
               (meta ? '<span class="pc-meta">' + meta + '</span>' : '') +
               '<span class="pc-dot"></span>' +
             '</button>';
    }
    hosts.forEach(function (h) {
      h.innerHTML = html;
      var b = h.querySelector(".proj-chip");
      if (b) b.onclick = function () { openProjDrawer(pid); };
    });
  }

  // ── Ngăn kéo ─────────────────────────────────────────────────────────────────
  function pdDung() {
    if (pdEl) return pdEl;
    pdEl = el(
      '<div class="pd-wrap" id="projDrawer">' +
        '<div class="pd-scrim"></div>' +
        '<div class="pd-panel" role="dialog" aria-modal="true">' +
          '<div class="pd-grip"></div>' +
          '<div class="pd-head">' +
            '<span class="pd-ico"></span>' +
            '<span class="pd-name"></span>' +
            '<button class="pd-hbtn pd-pin" type="button"></button>' +
            '<button class="pd-hbtn pd-ren" type="button"></button>' +
            '<button class="pd-hbtn pd-x" type="button"></button>' +
          '</div>' +
          '<div class="pd-tabs">' +
            '<button class="pd-tab" data-tab="instr" type="button"></button>' +
            '<button class="pd-tab" data-tab="files" type="button"></button>' +
            '<button class="pd-tab" data-tab="links" type="button"></button>' +
          '</div>' +
          '<div class="pd-body"></div>' +
        '</div>' +
      '</div>');
    document.body.appendChild(pdEl);
    pdEl.querySelector(".pd-scrim").onclick = closeProjDrawer;
    pdEl.querySelector(".pd-x").onclick = closeProjDrawer;
    pdEl.querySelector(".pd-x").innerHTML = ic("x");
    pdEl.querySelector(".pd-x").title = pdT("proj.close");
    pdEl.querySelector(".pd-ren").innerHTML = ic("pencil");
    pdEl.querySelector(".pd-ren").title = pdT("proj.rename");
    pdEl.querySelector(".pd-ren").onclick = function () {
      if (!projChiTiet) return;
      renameProject(projChiTiet).then(function () {
        var p = projById(projChiTiet.id);
        if (p) projChiTiet.name = p.name;
        veDrawer();
      });
    };
    pdEl.querySelectorAll(".pd-tab").forEach(function (b) {
      b.onclick = function () { showProjTab(b.dataset.tab); };
    });
    return pdEl;
  }

  async function openProjDrawer(pid) {
    var id = pid || (projChiTiet && projChiTiet.id) || "";
    if (!id) return;
    pdDung();
    pdFormFile = false; pdFormLink = false; pdFileMode = "search";
    pdEl.classList.add("on");
    document.body.classList.add("pd-open");
    projChiTiet = { id: id, name: (projById(id) || {}).name || "", icon: (projById(id) || {}).icon || "", files: [], links: [], instructions: "", dangTai: true };
    veDrawer();
    await napProjChiTiet(id);
    veDrawer();
  }

  function closeProjDrawer() {
    // Lưu ngay cái đang gõ dở. Debounce 800ms nghĩa là đóng nhanh tay là mất chữ vừa gõ,
    // và người dùng không có cách nào biết đã mất.
    xaLuuHuongDan();
    if (pdEl) pdEl.classList.remove("on");
    document.body.classList.remove("pd-open");
    pdOnboard = false;
  }

  async function napProjChiTiet(id) {
    try {
      var r = await fetch("/projects/" + encodeURIComponent(id));
      var d = await r.json();
      if (d && d.project) { projChiTiet = d.project; return; }
    } catch (e) {}
    projChiTiet = { id: id, name: (projById(id) || {}).name || "", loi: true, files: [], links: [] };
  }

  function showProjTab(tab) {
    xaLuuHuongDan();              // rời tab cũng là rời ô nhập
    projTab = (tab === "files" || tab === "links") ? tab : "instr";
    pdFormFile = false; pdFormLink = false;
    veDrawer();
  }

  function veDrawer() {
    if (!pdEl || !projChiTiet) return;
    var p = projChiTiet;
    pdEl.querySelector(".pd-ico").innerHTML = projIcon(projById(p.id) || p);
    pdEl.querySelector(".pd-name").textContent = p.name || "";
    var nf = (p.files || []).length, nl = (p.links || []).length;
    var tabs = pdEl.querySelectorAll(".pd-tab");
    var nhan = [pdT("proj.tab_instr"), pdT("proj.tab_files"), pdT("proj.tab_links")];
    var dem = ["", nf ? String(nf) : "", nl ? String(nl) : ""];
    tabs.forEach(function (b, i) {
      b.innerHTML = esc(nhan[i]) + (dem[i] ? ' <span class="pd-tab-n">' + dem[i] + "</span>" : "");
      b.classList.toggle("on", b.dataset.tab === projTab);
    });
    veNutGhimPhien();
    var body = pdEl.querySelector(".pd-body");
    if (p.dangTai) { body.innerHTML = '<div class="pd-empty">' + esc(pdT("proj.loading")) + "…</div>"; return; }
    if (p.loi) { body.innerHTML = '<div class="pd-empty">' + esc(pdT("proj.err_load")) + "</div>"; return; }
    body.innerHTML =
      (pdOnboard
        ? '<div class="pd-onboard">' + ic("sparkles") + "<span>" + esc(pdT("proj.onboard")) + "</span>" +
          '<button class="pd-ob-x" type="button">' + esc(pdT("proj.onboard_close")) + "</button></div>"
        : "") +
      (projTab === "instr" ? paneHuongDan(p) : projTab === "files" ? paneFile(p) : paneLink(p));
    var obx = body.querySelector(".pd-ob-x");
    if (obx) obx.onclick = function () { pdOnboard = false; veDrawer(); };
    if (projTab === "instr") noiHuongDan();
    else if (projTab === "files") noiFile();
    else noiLink();
  }

  // Nút ghim ở đầu ngăn kéo ghim HỘI THOẠI đang mở lên đầu danh sách - đó là chức năng ghim
  // toàn cục đã có, chỉ bày lại ở đây. Không có phiên đã lưu thì không có gì để ghim, nên ẩn
  // hẳn nút thay vì để nó bấm ra lỗi 404 im lặng.
  function veNutGhimPhien() {
    var b = pdEl.querySelector(".pd-pin");
    var sid = currentId();
    var s = null;
    if (sid && cached && cached.items) {
      for (var i = 0; i < cached.items.length; i++) if (cached.items[i].id === sid) s = cached.items[i];
    }
    if (!s) { b.style.display = "none"; return; }
    b.style.display = "";
    b.innerHTML = ic("pin");
    b.classList.toggle("on", !!s.pinned);
    b.title = pdT("proj.pin_session");
    b.onclick = function () { togglePin(s); b.classList.toggle("on"); };
  }

  // ── Tab Hướng dẫn ────────────────────────────────────────────────────────────
  function paneHuongDan(p) {
    var txt = p.instructions || "";
    return '<div class="pd-pane">' +
      '<textarea class="pd-instr" maxlength="' + PROJ_INSTR_MAX + '" placeholder="' +
        esc(pdT("proj.instr_ph")) + '">' + esc(txt) + "</textarea>" +
      '<div class="pd-instr-foot">' +
        '<span class="pd-hint">' + esc(pdT("proj.instr_hint")) + "</span>" +
        '<span class="pd-save"></span>' +
      "</div>" +
      '<div class="pd-count"></div>' +
      "</div>";
  }

  function noiHuongDan() {
    var ta = pdEl.querySelector(".pd-instr");
    if (!ta) return;
    demChu();
    ta.oninput = function () {
      demChu();
      datTrangThaiLuu("saving");
      clearTimeout(pdLuuTimer);
      pdLuuTimer = setTimeout(function () { luuHuongDan(ta.value); }, 800);
    };
    ta.onblur = function () { xaLuuHuongDan(); };
  }

  function demChu() {
    var ta = pdEl && pdEl.querySelector(".pd-instr");
    var box = pdEl && pdEl.querySelector(".pd-count");
    if (!ta || !box) return;
    var n = ta.value.length;
    var day = n >= PROJ_INSTR_MAX;
    box.className = "pd-count" + (day ? " day" : "");
    box.textContent = day ? pdT("proj.instr_full") : n + "/" + PROJ_INSTR_MAX;
  }

  /** Đẩy ngay cái đang chờ debounce. Gọi khi đóng ngăn kéo / rời tab / rời ô nhập. */
  function xaLuuHuongDan() {
    if (!pdLuuTimer) return;
    clearTimeout(pdLuuTimer); pdLuuTimer = null;
    var ta = pdEl && pdEl.querySelector(".pd-instr");
    if (ta) luuHuongDan(ta.value);
  }

  function datTrangThaiLuu(tt) {
    var s = pdEl && pdEl.querySelector(".pd-save");
    if (!s) return;
    s.className = "pd-save " + tt;
    s.textContent = tt === "saved" ? pdT("proj.instr_saved")
                  : tt === "err" ? pdT("proj.instr_err")
                  : pdT("proj.instr_saving") + "…";
  }

  async function luuHuongDan(v) {
    pdLuuTimer = null;
    if (!projChiTiet) return;
    var r = await post("/projects/" + encodeURIComponent(projChiTiet.id) + "/update",
                       { instructions: v });
    if (r && r.ok) {
      projChiTiet.instructions = v;
      datTrangThaiLuu("saved");
      // Chip đọc `has_instructions` từ danh sách, nên phải nạp lại thì chấm báo mới đúng.
      loadProjects();
    } else {
      datTrangThaiLuu("err");
    }
  }

  // ── Tab File ─────────────────────────────────────────────────────────────────
  // Trả về TÊN icon, không phải chuỗi <svg>: chỗ gọi lo dữ liệu, chỗ vẽ mới gọi ic().
  function icoFile(ten) {
    var e = (String(ten).split(".").pop() || "").toLowerCase();
    if (["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"].indexOf(e) >= 0) return "image";
    if (["md", "txt", "csv", "json", "yaml", "yml", "log"].indexOf(e) >= 0) return "file-text";
    return "file";
  }

  function hangMuc(o) {
    return '<div class="pd-row" data-id="' + esc(o.id) + '">' +
        '<span class="pd-row-ico">' + ic(o.icon) + "</span>" +
        '<span class="pd-row-body">' +
          '<span class="pd-row-name">' + esc(o.ten) + "</span>" +
          '<span class="pd-row-sub">' + (o.subHtml || esc(o.sub || "")) + "</span>" +
        "</span>" +
        '<button class="pd-row-act pd-ghim' + (o.pinned ? " on" : "") + '" type="button" title="' +
          esc(o.pinned ? pdT("proj.pin_off") : o.ghimTitle) + '">' + ic("pin") + "</button>" +
        '<button class="pd-row-act pd-go" type="button" title="' + esc(pdT("proj.remove")) + '">' +
          ic("x") + "</button>" +
      "</div>";
  }

  function paneFile(p) {
    var fs = p.files || [];
    var ghim = fs.filter(function (f) { return f.pinned; });
    var thuong = fs.filter(function (f) { return !f.pinned; });
    var ve = function (f) {
      return hangMuc({ id: f.id, ten: f.name || f.path, sub: f.path,
                       icon: icoFile(f.name || f.path), pinned: !!f.pinned,
                       ghimTitle: pdT("proj.pin_on") });
    };
    var ds = "";
    if (!fs.length) ds = '<div class="pd-empty">' + esc(pdT("proj.files_empty")) + "</div>";
    else {
      if (ghim.length) ds += '<div class="pd-group">' + esc(pdT("proj.pinned_group")) + "</div>" + ghim.map(ve).join("");
      if (thuong.length) ds += (ghim.length ? '<div class="pd-group">' + esc(pdT("proj.other_group")) + "</div>" : "") + thuong.map(ve).join("");
    }
    return '<div class="pd-pane" data-pane="files">' + ds +
      '<button class="pd-add" type="button">' + ic("plus") + " " + esc(pdT("proj.add_file")) + "</button>" +
      (pdFormFile ? formFile() : "") +
      '<div class="pd-note">' + ic("info") + "<span>" + esc(pdT("proj.pin_note")) + "</span></div>" +
      "</div>";
  }

  function formFile() {
    return '<div class="pd-form">' +
      '<div class="pd-modes">' +
        '<button class="pd-mode' + (pdFileMode === "search" ? " on" : "") + '" data-mode="search" type="button">' +
          ic("search") + " " + esc(pdT("proj.mode_search")) + "</button>" +
        '<button class="pd-mode' + (pdFileMode === "upload" ? " on" : "") + '" data-mode="upload" type="button">' +
          ic("upload-cloud") + " " + esc(pdT("proj.mode_upload")) + "</button>" +
      "</div>" +
      (pdFileMode === "search"
        ? '<input class="pd-in pd-fsearch" placeholder="' + esc(pdT("proj.search_ph")) + '">' +
          '<div class="pd-results"><div class="pd-empty">' + esc(pdT("proj.search_hint")) + "</div></div>"
        : '<input type="file" class="pd-file" hidden>' +
          '<button class="pd-drop" type="button">' + ic("upload-cloud") + " " + esc(pdT("proj.dropzone")) + "</button>" +
          '<div class="pd-note pd-up-note">' + ic("info") + "<span>" + esc(pdT("proj.upload_dest")) + "</span></div>") +
      "</div>";
  }

  function noiFile() {
    var pane = pdEl.querySelector('[data-pane="files"]');
    if (!pane) return;
    pane.querySelector(".pd-add").onclick = function () { pdFormFile = !pdFormFile; veDrawer(); };
    pane.querySelectorAll(".pd-row").forEach(function (row) {
      var f = (projChiTiet.files || []).filter(function (x) { return x.id === row.dataset.id; })[0];
      if (!f) return;
      row.querySelector(".pd-ghim").onclick = function () { ghimFile(f); };
      row.querySelector(".pd-go").onclick = function () { goFile(f); };
    });
    pane.querySelectorAll(".pd-mode").forEach(function (b) {
      b.onclick = function () { pdFileMode = b.dataset.mode; veDrawer(); };
    });
    var o = pane.querySelector(".pd-fsearch");
    if (o) {
      o.focus();
      var timer = null;
      o.oninput = function () {
        clearTimeout(timer);
        var q = o.value.trim();
        timer = setTimeout(function () { timFile(q, pane); }, 280);
      };
    }
    var drop = pane.querySelector(".pd-drop");
    var inp = pane.querySelector(".pd-file");
    if (drop && inp) {
      drop.onclick = function () { inp.click(); };
      inp.onchange = function () { if (inp.files && inp.files[0]) taiLen(inp.files[0], drop); };
      drop.ondragover = function (e) { e.preventDefault(); drop.classList.add("over"); };
      drop.ondragleave = function () { drop.classList.remove("over"); };
      drop.ondrop = function (e) {
        e.preventDefault(); drop.classList.remove("over");
        var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (f) taiLen(f, drop);
      };
    }
  }

  async function timFile(q, pane) {
    var box = pane.querySelector(".pd-results");
    if (!box) return;
    if (!q) { box.innerHTML = '<div class="pd-empty">' + esc(pdT("proj.search_hint")) + "</div>"; return; }
    box.innerHTML = '<div class="pd-empty">' + esc(pdT("proj.searching")) + "…</div>";
    var items = [];
    try {
      var d = await (await fetch("/files/search?brain=" + encodeURIComponent(brain()) +
                                 "&mode=name&limit=20&q=" + encodeURIComponent(q))).json();
      items = d.items || [];
    } catch (e) {}
    if (!items.length) { box.innerHTML = '<div class="pd-empty">' + esc(pdT("proj.search_none")) + "</div>"; return; }
    var daCo = {};
    (projChiTiet.files || []).forEach(function (f) { daCo[f.path] = true; });
    box.innerHTML = items.map(function (it) {
      return '<div class="pd-res" data-path="' + esc(it.path) + '" data-name="' + esc(it.name) + '">' +
        '<span class="pd-res-ico">' + ic(icoFile(it.name)) + "</span>" +
        '<span class="pd-res-n"><b>' + esc(it.name) + "</b><i>" + esc(it.path) + "</i></span>" +
        '<button class="pd-res-add" type="button"' + (daCo[it.path] ? " disabled" : "") + ">" +
          esc(daCo[it.path] ? pdT("proj.added") : pdT("proj.add")) + "</button></div>";
    }).join("");
    box.querySelectorAll(".pd-res").forEach(function (r) {
      var b = r.querySelector(".pd-res-add");
      if (b.disabled) return;
      b.onclick = function () { themFile(r.dataset.path, r.dataset.name, b); };
    });
  }

  async function themFile(duong, ten, nut) {
    if (nut) { nut.disabled = true; nut.textContent = pdT("proj.added"); }
    var r = await post("/projects/" + encodeURIComponent(projChiTiet.id) + "/files",
                       { path: duong, name: ten || "" });
    if (!r || !r.ok) {
      alert(pdT("proj.err_add_file") + ": " + ((r && r.error) || ""));
      if (nut) { nut.disabled = false; nut.textContent = pdT("proj.add"); }
      return;
    }
    await napProjChiTiet(projChiTiet.id);
    loadProjects();
    veDrawer();
  }

  /** Gốc brain tính theo TRẦN duyệt. Trần có thể cao hơn gốc brain (localhost duyệt cả ổ
   *  đĩa), nên tải thẳng vào "attachments" là ghi ra ngoài brain. */
  async function homeCuaBrain() {
    var b = brain();
    if (pdHome.brain === b) return pdHome.home;
    var home = "";
    try {
      var d = await (await fetch("/files/list?brain=" + encodeURIComponent(b))).json();
      home = d.home || "";
    } catch (e) {}
    pdHome = { brain: b, home: home };
    return home;
  }

  async function taiLen(file, drop) {
    var cu = drop.innerHTML;
    drop.disabled = true;
    drop.innerHTML = ic("loader") + " " + esc(pdT("proj.uploading")) + "…";
    var home = await homeCuaBrain();
    var thuMuc = (home ? home + "/" : "") + "attachments";
    var up = null;
    try {
      var fd = new FormData();
      fd.append("file", file); fd.append("brain", brain()); fd.append("path", thuMuc);
      up = await (await fetch("/files/upload", { method: "POST", body: fd })).json();
    } catch (e) {}
    drop.disabled = false; drop.innerHTML = cu;
    if (!up || !up.ok) { alert(pdT("proj.err_upload") + ": " + ((up && up.error) || "")); return; }
    await themFile(thuMuc + "/" + up.name, up.name, null);
  }

  async function ghimFile(f) {
    await post("/projects/" + encodeURIComponent(projChiTiet.id) + "/files/" +
               encodeURIComponent(f.id) + "/pin", { pinned: f.pinned ? "0" : "1" });
    await napProjChiTiet(projChiTiet.id);
    veDrawer();
  }

  async function goFile(f) {
    if (!confirm(pdT("proj.confirm_remove_file", { ten: f.name || f.path }))) return;
    await post("/projects/" + encodeURIComponent(projChiTiet.id) + "/files/" +
               encodeURIComponent(f.id) + "/delete", {});
    await napProjChiTiet(projChiTiet.id);
    loadProjects();
    veDrawer();
  }

  // ── Tab Link ─────────────────────────────────────────────────────────────────
  function paneLink(p) {
    var ls = p.links || [];
    var ve = function (l) {
      return hangMuc({ id: l.id, ten: l.label || l.url, icon: "link", pinned: !!l.pinned,
                       ghimTitle: pdT("proj.pin_link_on"),
                       subHtml: '<a href="' + esc(l.url) + '" target="_blank" rel="noopener noreferrer">' +
                                esc(l.url) + "</a>" });
    };
    var ds = ls.length ? ls.map(ve).join("")
                       : '<div class="pd-empty">' + esc(pdT("proj.links_empty")) + "</div>";
    return '<div class="pd-pane" data-pane="links">' + ds +
      '<button class="pd-add" type="button">' + ic("plus") + " " + esc(pdT("proj.add_link")) + "</button>" +
      (pdFormLink
        ? '<div class="pd-form">' +
            '<input class="pd-in pd-lurl" placeholder="' + esc(pdT("proj.link_url_ph")) + '">' +
            '<input class="pd-in pd-llabel" placeholder="' + esc(pdT("proj.link_label_ph")) + '">' +
            '<div class="pd-frow">' +
              '<button class="pd-ok" type="button">' + esc(pdT("proj.add")) + "</button>" +
              '<button class="pd-huy" type="button">' + esc(pdT("proj.cancel")) + "</button>" +
            "</div></div>"
        : "") +
      '<div class="pd-note">' + ic("info") + "<span>" + esc(pdT("proj.link_note")) + "</span></div>" +
      "</div>";
  }

  function noiLink() {
    var pane = pdEl.querySelector('[data-pane="links"]');
    if (!pane) return;
    pane.querySelector(".pd-add").onclick = function () { pdFormLink = !pdFormLink; veDrawer(); };
    pane.querySelectorAll(".pd-row").forEach(function (row) {
      var l = (projChiTiet.links || []).filter(function (x) { return x.id === row.dataset.id; })[0];
      if (!l) return;
      row.querySelector(".pd-ghim").onclick = function () { ghimLink(l); };
      row.querySelector(".pd-go").onclick = function () { goLink(l); };
    });
    var u = pane.querySelector(".pd-lurl");
    if (!u) return;
    u.focus();
    var lb = pane.querySelector(".pd-llabel");
    var them = function () { themLink(u.value, lb.value); };
    pane.querySelector(".pd-ok").onclick = them;
    pane.querySelector(".pd-huy").onclick = function () { pdFormLink = false; veDrawer(); };
    [u, lb].forEach(function (o) {
      o.onkeydown = function (e) { if (e.key === "Enter") { e.preventDefault(); them(); } };
    });
  }

  async function themLink(url, nhan) {
    var u = (url || "").trim();
    if (!u) return;
    var r = await post("/projects/" + encodeURIComponent(projChiTiet.id) + "/links",
                       { url: u, label: (nhan || "").trim() });
    if (!r || !r.ok) { alert(pdT("proj.err_add_link") + ": " + ((r && r.error) || "")); return; }
    pdFormLink = false;
    await napProjChiTiet(projChiTiet.id);
    loadProjects();
    veDrawer();
  }

  async function ghimLink(l) {
    await post("/projects/" + encodeURIComponent(projChiTiet.id) + "/links/" +
               encodeURIComponent(l.id) + "/pin", { pinned: l.pinned ? "0" : "1" });
    await napProjChiTiet(projChiTiet.id);
    veDrawer();
  }

  async function goLink(l) {
    if (!confirm(pdT("proj.confirm_remove_link", { ten: l.label || l.url }))) return;
    await post("/projects/" + encodeURIComponent(projChiTiet.id) + "/links/" +
               encodeURIComponent(l.id) + "/delete", {});
    await napProjChiTiet(projChiTiet.id);
    loadProjects();
    veDrawer();
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
      // r.icon là TÊN icon Lucide, đi qua iconHtml (thẻ <svg>); r.label là chữ nên phải escape.
      var iHtml = r.icon ? iconHtml(r.icon) : "";
      var row = el('<div class="cs-menu-row' + (r.on ? " on" : "") + '">' +
        '<button class="cs-menu-main" type="button">' +
        (iHtml ? '<span class="cs-menu-ico">' + iHtml + '</span>' : '') +
        '<span class="cs-menu-lbl">' + esc(r.label) + '</span>' +
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

  // Bộ chọn icon dùng CHÍNH bộ icon Lucide app đã vendor, không phải emoji. Vì sao:
  // icon Lucide vẽ bằng stroke="currentColor" nên tự đổi màu theo tông SÁNG/TỐI và theo màu
  // chữ chỗ nó đứng, lại giống hệt nhau trên mọi máy - hai thứ emoji không bao giờ làm được
  // (mỗi hệ điều hành vẽ một kiểu, và emoji màu cứng nên tông tối nhìn chói). Cả dashboard
  // đã bỏ emoji vì đúng lý do đó; để riêng chỗ này dùng emoji là lệch khỏi phần còn lại.
  // Giá trị lưu vào DB là TÊN icon (vd "star"), không phải ký tự.
  function tenIcon() {
    try { return (window.Icons && window.Icons.names && window.Icons.names()) || []; }
    catch (e) { return []; }
  }
  // Icon người dùng chọn -> HTML. Tên lạ (bộ icon đổi giữa hai phiên bản, hay ai đó sửa tay
  // DB) thì trả rỗng chứ không để ic() vẽ dấu hỏi kèm cảnh báo console mỗi lần render.
  function iconHtml(name) {
    var n = String(name || "").trim();
    if (!n) return "";
    try { if (!(window.Icons && window.Icons.has(n))) return ""; } catch (e) { return ""; }
    return ic(n, { title: n });
  }
  function pickIcon(anchor, cur, onPick) {
    closeMenu();
    menuEl = document.createElement("div");
    menuEl.className = "cs-menu cs-ico";
    var head = el('<div class="cs-ico-head">' +
      '<input class="cs-ico-in" placeholder="Lọc theo tên icon (star, folder…)">' +
      '<button class="cs-ico-clear" type="button">Xoá icon</button></div>');
    var grid = el('<div class="cs-ico-grid"></div>');
    var tenAll = tenIcon();

    function ve(loc) {
      var q = String(loc || "").trim().toLowerCase();
      var ds = q ? tenAll.filter(function (n) { return n.indexOf(q) !== -1; }) : tenAll;
      grid.innerHTML = "";
      if (!ds.length) {
        grid.appendChild(el('<div class="cs-ico-empty">Không có icon nào tên chứa "' + esc(q) + '".</div>'));
        return;
      }
      ds.forEach(function (n) {
        var b = el('<button class="cs-ico-b' + (n === cur ? " on" : "") + '" type="button" title="' +
                   esc(n) + '">' + ic(n) + "</button>");
        b.onclick = function () { closeMenu(); onPick(n); };
        grid.appendChild(b);
      });
    }

    head.querySelector(".cs-ico-in").oninput = function (ev) { ve(ev.currentTarget.value); };
    head.querySelector(".cs-ico-clear").onclick = function () { closeMenu(); onPick(""); };
    menuEl.appendChild(head);
    menuEl.appendChild(grid);
    ve("");
    placeMenu(anchor);
    try { head.querySelector(".cs-ico-in").focus(); } catch (e) {}
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
        // Icon ở đầu mỗi tab: hai tab đứng cạnh nhau và chỉ khác nhau bằng chữ, nên liếc qua
        // phải đọc mới biết đang ở đâu. Dùng đúng icon rail đang dùng cho hai thứ đó
        // (message-circle cho Trò chuyện, folder-tree cho Tệp tin) để cả app nói cùng một
        // ngôn ngữ hình, chứ không đặt icon mới chỉ riêng chỗ này.
        '<button class="cside-tab" data-tab="chat" type="button">' + ic("message-circle") + ' Hội thoại</button>' +
        '<button class="cside-tab" data-tab="files" type="button">' + ic("folder-tree") + ' Thư mục</button>' +
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
      // KHÔNG có icon riêng cho từng hội thoại. Hàng nào cũng là một cuộc trò chuyện nên icon
      // ở đây không phân loại được gì, chỉ thêm một nút phải bấm và một hàng nút chật thêm.
      // Icon để PHÂN LOẠI thì nằm ở Project - xem openProjMenu.
      var item = el('<div class="cside-item' + (s.id === cur ? " active" : "") + (isRun ? " running" : "") + '">' +
        '<div class="ci-title">' + (isRun ? '<span class="ci-run" title="Đang trả lời">' + ic("loader", { cls: "ic-spin" }) + '</span> ' : '') +
        esc(s.title || s.preview || "(chưa đặt tên)") + '</div>' +
        '<div class="ci-meta"><span>' + fmtT(s.updated_at) + '</span>' +
        (chLabel ? '<span class="ci-badge">' + esc(chLabel) + '</span>' : '') +
        (eng ? '<span class="ci-badge">' + esc(eng) + '</span>' : '') +
        '<span>' + (s.msg_count || 0) + ' tin</span>' +
        '<span class="act">' +
          '<span class="pin' + (s.pinned ? " on" : "") + '" title="' + (s.pinned ? "Bỏ ghim" : "Ghim lên đầu") + '">' + ic("pin") + '</span>' +
          '<span class="mov" title="Chuyển vào project">' + ic("folder") + '</span>' +
          '<span class="ren" title="Đổi tên">' + ic("pencil") + '</span>' +
          '<span class="del" title="Xoá">' + ic("trash-2") + '</span>' +
        '</span>' +
        '</div></div>');
      // Hai nút mới gắn handler RIÊNG kèm stopPropagation, không nhét thêm nhánh vào
      // item.onclick bên dưới. Handler đó là thứ test_chat_side_actions.js bóc ra chạy thật
      // với đúng năm tham số của nó; thêm tên hàm lạ vào là test nổ ReferenceError.
      item.querySelector(".pin").onclick = function (ev) { ev.stopPropagation(); togglePin(s); };
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
        label: p.name,
        icon: p.icon || "folder",
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
    quenPhienProj();
    renderProjChip();
    cached = null;
    loadList();
  }

  window.JavisChatSide = { mount: mount, refresh: refresh, tab: chonTab,
                           chip: renderProjChip, moKhung: openProjDrawer };
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
  // Chip phải tự sống KHÔNG phụ thuộc cột trái: refresh() thoát sớm khi chưa mount sidebar,
  // mà chip còn đứng ở màn Javis nơi cột đó chưa bao giờ mount. Đổi phiên là đổi project có
  // hiệu lực, nên bỏ cache rồi vẽ lại.
  window.addEventListener("javis:sessions-changed", function () {
    quenPhienProj();
    renderProjChip();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && pdEl && pdEl.classList.contains("on")) closeProjDrawer();
  });
  // Đổi ngôn ngữ giao diện: phần khung dựng MỘT lần (nút đóng, nút đổi tên) không tự vẽ lại
  // như thân khung, nên bỏ hẳn node đi để lần mở sau dựng lại bằng từ điển mới.
  window.addEventListener("javis:i18n", function () {
    var dangMo = !!(pdEl && pdEl.classList.contains("on"));
    var id = projChiTiet && projChiTiet.id;
    if (pdEl && pdEl.parentNode) pdEl.parentNode.removeChild(pdEl);
    pdEl = null;
    document.body.classList.remove("pd-open");
    if (dangMo && id) openProjDrawer(id);
    renderProjChip();
  });

  function bindGlobal() {
    var gs = document.getElementById("graphSource");
    if (gs) gs.addEventListener("change", refresh);
    // Nút "Lịch sử" → mở thẳng workspace với sidebar. Đặt INLINE trong hàng nút header
    // (.hud-actions) để không đè lên nút Cài đặt/Reset; fallback về body nếu chưa có header.
    var btn = el('<div id="jv-sess-btn" title="Lịch sử hội thoại">' + ic("history") + ' <span>Lịch sử</span></div>');
    btn.onclick = function () { if (window.JavisChatStage) window.JavisChatStage.showSide(); };
    var host = document.querySelector(".hud-actions");
    (host || document.body).appendChild(btn);
    // Prefetch danh sách sau khi cockpit đã yên: bấm Lịch sử lần đầu là có sẵn dữ liệu.
    // Kèm danh sách project vì chip ở thanh tiêu đề khung chat cần tên + số file/link ngay,
    // trong khi cột trái (nơi vẫn gọi loadProjects) chỉ mount khi mở trang Trò chuyện.
    setTimeout(function () {
      fetchList().catch(function () {});
      loadProjects();
    }, 1500);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bindGlobal);
  else bindGlobal();
})();
