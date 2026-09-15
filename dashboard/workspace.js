/* workspace.js - trang Cộng sự: chat với từng trợ lý và từng quy trình trên cùng khung chat.

   Ba cột: trái = danh sách (Trợ lý | Quy trình), giữa = khung chat MƯỢN của app (console.js
   mượn/trả node, file này chỉ nhận slot), phải = cài đặt trợ lý hoặc tiến độ + lịch sử chạy.

   Mỗi cộng sự có phiên riêng trong kho phiên (kênh agent:<slug> / workflow:<slug>). Gửi tin
   vẫn đi đường WebSocket thường của app.js; server nhìn kênh của phiên mà rẽ nhánh. Khung
   wf_event (tiến độ từng bước) app.js chuyển vào onWfEvent() ở đây.

   Phần thuần (sapXep, loc, tienDoMoi, apDung, phanTram) phơi ra để test bằng node.
   Ghi chú: KHÔNG dùng ký tự em dash. Chữ hiện ra lấy từ từ điển window.t. */
(function () {
  "use strict";
  var t = function (k, v) { return (window.t ? window.t(k, v) : k); };
  var ic = function (n, o) { return (window.ic ? window.ic(n, o) : ""); };
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]; }); }
  function khongDau(s) { return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase(); }
  function brain() { try { return window.JavisSessions ? window.JavisSessions.brain() : "brain"; } catch (e) { return "brain"; } }
  async function api(url, opt) { var r = await fetch(url, opt); return r.json(); }
  function fd(o) { var f = new FormData(); Object.keys(o).forEach(function (k) { f.append(k, o[k]); }); return f; }

  function avatar(a, size, state) { return window.JavisAvatar ? window.JavisAvatar.html(a, size, state) : ic("bot"); }
  function agentOf(slug) { return S.agents.find(function (a) { return a.slug === slug || a.name === slug; }) || {slug: slug || ""}; }
  var opening = 0, ready = false, active = false, pendingCommand = null;
  function chatReady(value) {
    ready = value;
    var input = document.getElementById("chatInput");
    if (input) input.disabled = !value;
    var files = S.el && S.el.querySelector("#wsFiles"); if (files) files.disabled = !value;
    var run = S.el && S.el.querySelector("#wsRun");
    if (run) run.disabled = !value;
  }
  function onChatState(state) {
    if (!active || !S.el || S.loai !== "agent") return;
    S.el.querySelectorAll(".ws-id .agent-avatar, .aa-preview .agent-avatar, .ws-item.on .agent-avatar").forEach(function (el) { el.dataset.state = state || "idle"; });
  }
  // ---------- phần thuần ----------
  // Xếp theo MỐC GẦN NHẤT chứ không theo tên: cộng sự vừa dùng xong là cộng sự sắp dùng lại.
  // Mục chưa có mốc rơi xuống dưới và xếp theo tên cho ổn định (không nhảy lung tung mỗi lần vẽ).
  function sapXep(ds, khoa) {
    return ds.slice().sort(function (a, b) {
      var ma = Number(a[khoa] || 0), mb = Number(b[khoa] || 0);
      if (ma !== mb) return mb - ma;
      return String(a.name || "").localeCompare(String(b.name || ""), "vi");
    });
  }
  function loc(ds, q, nhom) {
    var nq = khongDau(q || "").trim();
    return ds.filter(function (x) {
      if (nhom && (x.group || "Chung") !== nhom) return false;
      if (!nq) return true;
      var text = khongDau([x.name, x.role, x.description, x.slug, x.group].join(" "));
      return nq.split(/\s+/).every(function (word) { return text.indexOf(word) >= 0; });
    });
  }
  function bucMoi(i) { return { i: i, agent: "", trang_thai: "cho", loi: "" }; }
  function tienDoMoi(n) {
    var buoc = [];
    for (var i = 0; i < n; i++) buoc.push(bucMoi(i));
    return { buoc: buoc, hien_tai: -1, trang_thai: "cho", cho_duyet: null, run_id: "" };
  }
  // Máy trạng thái của MỘT lần chạy, ăn thẳng sự kiện của execute_workflow (server/workflow_chat.py).
  // Tách khỏi phần vẽ để test bằng node: đây là chỗ dễ sai nhất mà nhìn màn hình không ra.
  function apDung(st, ev) {
    var i = Number(ev.i);
    if (ev.type === "start") {
      st.run_id = ev.run_id || "";
      while (st.buoc.length < Number(ev.steps || 0)) st.buoc.push(bucMoi(st.buoc.length));
      st.trang_thai = "dang";
    } else if (ev.type === "step_start") {
      while (st.buoc.length <= i) st.buoc.push(bucMoi(st.buoc.length));
      st.buoc[i].agent = ev.agent || st.buoc[i].agent;
      st.buoc[i].trang_thai = "dang";
      st.hien_tai = i; st.trang_thai = "dang";
    } else if (ev.type === "step_done") {
      // Bước đã mang dấu HỎNG thì không có sự kiện nào sau đó xoá được dấu ấy. Server hiện
      // không còn gửi step_done sau step_error nữa, nhưng luật phải tự đứng được ở đây: máy
      // trạng thái này còn ăn lại sự kiện của phiên cũ, và một tích xanh sai còn tệ hơn
      // không có tích nào.
      if (st.buoc[i] && st.buoc[i].trang_thai !== "loi") st.buoc[i].trang_thai = "xong";
    } else if (ev.type === "step_error") {
      // Bước mà động cơ đã báo lỗi là bước HỎNG, không phải bước "đang làm dở". Trước 0.59.2
      // đây chỉ ghi câu lỗi vào .loi rồi để step_done đè trạng thái thành "xong", nên cột
      // phải hiện tích xanh cho đúng cái bước vừa chết.
      if (st.buoc[i]) { st.buoc[i].trang_thai = "loi"; st.buoc[i].loi = ev.content || st.buoc[i].loi; }
    } else if (ev.type === "wait_user") {
      st.trang_thai = "cho";
      st.cho_duyet = { node: ev.node || "", prompt: ev.prompt || "", task_id: ev.task_id || "", code: ev.code || "" };
    } else if (ev.type === "error") {
      st.trang_thai = "loi";
      // Lỗi của một BƯỚC mang sẵn số bước; lỗi chung (luồng đứt) thì không, lúc đó đánh dấu
      // bước đang chạy. Bước "cho" (chưa tới lượt) giữ nguyên - nó không hỏng, nó không chạy.
      var k = isFinite(i) ? i : st.hien_tai;
      if (k >= 0 && st.buoc[k] && st.buoc[k].trang_thai !== "xong") {
        st.buoc[k].trang_thai = "loi";
        st.buoc[k].loi = ev.content || st.buoc[k].loi;
      }
    } else if (ev.type === "stopped") {
      // Người dùng bấm Dừng giữa chừng. KHÔNG phải lỗi (không có gì hỏng) và cũng không phải
      // xong (chưa ra kết quả), nên nó là một trạng thái thứ ba. Thiếu nhánh này thì máy trạng
      // thái đứng mãi ở "dang": icon bên trái quay không ngừng và cột phải vẫn ghi "Đang chạy
      // Bước 1/3" cho một lần chạy đã chết từ lâu (chủ dự án báo 15/09).
      st.trang_thai = "dung"; st.cho_duyet = null;
      st.buoc.forEach(function (b) { if (b.trang_thai === "dang") b.trang_thai = "cho"; });
    } else if (ev.type === "done") {
      st.trang_thai = "xong"; st.cho_duyet = null;
      // Bước đã hỏng thì KHÔNG đổi thành xong. Server không còn gửi `done` sau một bước hỏng,
      // nhưng luật ở đây phải tự đứng được: máy trạng thái này còn ăn sự kiện của phiên cũ
      // mở lại, và một tích xanh sai còn tệ hơn không có tích nào.
      st.buoc.forEach(function (b) { if (b.trang_thai !== "loi") b.trang_thai = "xong"; });
    }
    return st;
  }
  function phanTram(st) {
    if (!st.buoc.length) return 0;
    if (st.trang_thai === "xong") return 100;
    return Math.round(st.buoc.filter(function (b) { return b.trang_thai === "xong"; }).length / st.buoc.length * 100);
  }

  // ---------- trạng thái trang ----------
  // tabPhai = tab đang mở ở cột phải: "cai" (cài đặt trợ lý / tiến độ quy trình), "lichsu"
  // (lần chạy + hội thoại cũ của cộng sự này) hay "files" (cây thư mục MƯỢN của màn chính).
  var TAB_PHAI = ["cai", "lichsu", "files"];   // ba tab cột phải, thứ tự đúng như lúc vẽ
  var S = { loai: "agent", q: "", nhom: "", agents: [], workflows: [], chon: { agent: null, workflow: null },
            el: null, tienDo: {}, sessionCuaPhien: {}, tabPhai: "cai" };   // tienDo[session_id] = tiến độ lần chạy đang xem

  function danhSach() { return S.loai === "agent" ? S.agents : S.workflows; }
  function kenh(item) { return (S.loai === "agent" ? "agent:" : "workflow:") + item.slug; }
  function dangChon() { var slug = S.chon[S.loai]; return danhSach().find(function (x) { return x.slug === slug; }) || null; }
  function cacBuoc(item) { return (item && item.steps) || []; }
  // Khổ màn hình mà cột trái là NGĂN KÉO (xem khối .wspage trong console.css) - phải khớp số
  // 900px bên đó, lệch nhau là nút đóng/mở nói một đằng màn hình làm một nẻo.
  function heptLai() { try { return window.matchMedia("(max-width: 900px)").matches; } catch (e) { return false; } }
  // So theo SLUG chứ không so theo địa chỉ object: taiDanhSach() thay cả mảng bằng object mới
  // sau mỗi lần chạy xong, nên một lời gọi vẽ đang chờ mạng sẽ thấy "khác object" dù vẫn đúng
  // cộng sự đang mở, rồi âm thầm bỏ không vẽ.
  function conDangXem(item) { var x = dangChon(); return !!(item && x && x.slug === item.slug); }

  async function taiDanhSach() {
    var b = encodeURIComponent(brain());
    var r = await Promise.all([api("/agents?brain=" + b), api("/workflows?brain=" + b)]);
    S.agents = sapXep(r[0].agents || [], "last_chat_at");
    S.workflows = sapXep((r[1].workflows || []).filter(function (w) { return w.status === "active"; }), "last_run_at");
  }

  // ---------- dựng khung ----------
  function render(el, opts) {
    S.el = el; active = true; ready = false;
    el.innerHTML =
      '<div class="wspage" id="wsPage">' +
        '<aside class="ws-left" id="wsLeft">' +
          '<div class="ws-seg"><button type="button" data-loai="agent">' + ic("bot") + ' ' + esc(t("ws.tab_agent")) + '</button>' +
          '<button type="button" data-loai="workflow">' + ic("workflow") + ' ' + esc(t("ws.tab_workflow")) + '</button></div>' +
          // Ô tìm KHÔNG mở sẵn (chủ repo yêu cầu): cột trái chỉ rộng 210-260px, một ô nhập
          // nằm đó suốt ngày ăn mất một dòng mà chín trên mười lần người dùng không gõ gì.
          // Bấm nút kính lúp mới bung ra, gõ xong xoá hết rồi rời đi là nó tự thu lại.
          '<div class="ws-filters" id="wsFilters">' +
            '<select class="ws-group" id="wsGroup" aria-label="' + esc(t("studio.groups")) + '"></select>' +
            // Ô nhập được GIEO LẠI từ S.q, và nút mang aria-controls trỏ vào nó: câu đang lọc
            // phải luôn NHÌN THẤY ĐƯỢC. Dựng khung với ô rỗng trong khi S.q còn chữ là danh
            // sách thiếu người mà không có gì trên màn hình giải thích vì sao.
            '<button type="button" class="ws-ico ws-search-btn" id="wsSearchBtn" aria-controls="wsSearch" ' +
            'aria-expanded="' + (S.q ? "true" : "false") + '" ' +
            'title="' + esc(t("ws.search_ph")) + '" aria-label="' + esc(t("ws.search_ph")) + '">' + ic("search") + '</button>' +
            // data-esc: khai với trình sửa note (console.js _neOTextNgoai) rằng ô này TỰ xử
            // Esc. Bộ bắt phím của trình sửa gắn ở mức document + capture nên nếu không khai
            // thì Esc ở đây đóng mất file đang mở thay vì xoá chữ đang gõ.
            '<input class="ws-search" id="wsSearch" data-esc' + (S.q ? "" : " hidden") + ' value="' + esc(S.q) + '" placeholder="' + esc(t("ws.search_ph")) + '">' +
          '</div>' +
          '<div class="ws-list" id="wsList"></div>' +
          '<div class="ws-left-foot"><button type="button" class="ws-btn" id="wsNew">' + ic("plus") + ' ' + esc(t("ws.new_item")) + '</button>' +
          '<button type="button" class="ws-btn" id="wsImport">' + esc(t("ws.upload_agent")) + '</button>' +
          '<button type="button" class="ws-btn" id="wsStore">' + ic("package") + ' Javis Store</button></div>' +
        '</aside>' +
        '<div class="ws-main">' +
          '<div class="ws-bar">' +
            '<button type="button" class="ws-ico" id="wsLeftBtn" title="' + esc(t("ws.toggle_list")) + '">' + ic("panel-left") + '</button>' +
            '<div class="ws-id" id="wsIdentity"></div>' +
            '<button type="button" class="ws-btn" id="wsFiles">' + ic("paperclip") + ' ' + esc(t("ws.files_links")) + '</button>' +
            '<button type="button" class="ws-btn" id="wsNewChat">' + esc(t("sess.new_chat")) + '</button>' +
            // Bộ icon chưa đóng gói "panel-right" (xem icons.manifest.json) và thêm icon mới
            // phải chạy gen_icons tải mạng - lật gương panel-left bằng CSS rẻ hơn mà cùng nghĩa.
            '<button type="button" class="ws-ico lat" id="wsRightBtn" title="' + esc(t("ws.toggle_panel")) + '">' + ic("panel-left") + '</button>' +
          '</div>' +
          '<div class="ws-slot" id="wsSlot"></div>' +
          // Chỗ đứng cho TRÌNH SỬA khi mở một file .md từ chat hay từ cây thư mục, y như
          // #chatPageEdit của trang Trò chuyện. Thiếu nó thì _borrowNoteEditor() không tìm
          // được khung nào để mượn và cú bấm vào link file lặng lẽ không làm gì cả.
          '<div class="ws-edit" id="wsEdit"></div>' +
        '</div>' +
        '<aside class="ws-right" id="wsRight">' +
          '<button type="button" class="ws-ico ws-panel-close" aria-label="' + esc(t("common.close")) + '">' + ic("x") + '</button>' +
          // Hai tab của cột phải: Cài đặt | Thư mục. Dùng lại đúng lớp .cside-tabs/.cside-pane
          // của cột trái trang Trò chuyện - cùng một kiểu tab, không đẻ bộ lớp thứ hai.
          '<div class="cside-tabs ws-rtabs">' +
            '<button type="button" class="cside-tab" data-rtab="cai">' + ic("settings") + ' ' + esc(t("ws.tab_settings")) + '</button>' +
            '<button type="button" class="cside-tab" data-rtab="lichsu">' + ic("history") + ' ' + esc(t("ws.tab_history")) + '</button>' +
            '<button type="button" class="cside-tab" data-rtab="files">' + ic("folder-tree") + ' ' + esc(t("sess.tab_files")) + '</button>' +
          '</div>' +
          '<div class="cside-pane ws-rpane" data-rpane="cai" id="wsRightSet"></div>' +
          '<div class="cside-pane ws-rpane" data-rpane="lichsu" id="wsRightHistory"></div>' +
          '<div class="cside-pane ws-rpane" data-rpane="files" id="wsRightFiles"></div>' +
        '</aside>' +
      '</div>';
    if (opts && opts.borrow) opts.borrow(el.querySelector("#wsSlot"));
    el.querySelectorAll("[data-loai]").forEach(function (b) { b.onclick = function () { S.loai = b.dataset.loai; S.nhom = ""; luuChon(); veTrai(); chonMacDinh(); }; });
    noiODoTim(el);
    el.querySelectorAll("[data-rtab]").forEach(function (b) { b.onclick = function () { chonTabPhai(b.dataset.rtab); }; });
    el.querySelector(".ws-panel-close").onclick = function () { el.querySelector("#wsPage").classList.remove("right-open"); };
    el.querySelector("#wsNew").onclick = taoMoi;
    el.querySelector("#wsImport").onclick = function () {
      if (window.JavisStudio) window.JavisStudio.importItems(async function () {
        if (!active) return;
        await taiDanhSach(); veTrai(); chonMacDinh();
      });
    };
    el.querySelector("#wsFiles").onclick = function () { if (ready && window.JavisChatSide) window.JavisChatSide.moKhungCuoc(); };
    el.querySelector("#wsStore").onclick = function () { if (window.JavisPacks && window.JavisPacks.moKho) window.JavisPacks.moKho(S.loai, "workspace", t("page.workspace.label")); };
    el.querySelector("#wsNewChat").onclick = function () { var x = dangChon(); if (x) moPhien(x, true); };
    var page = el.querySelector("#wsPage");
    el.querySelector("#wsLeftBtn").onclick = function () { page.classList.toggle("left-open"); };
    el.querySelector("#wsRightBtn").onclick = function () { page.classList.toggle("right-open"); };
    // Chạm NỀN MỜ (pseudo-element của chính .wspage nên cú chạm rơi vào page) = đóng ngăn kéo.
    // Màn hẹp: ngăn kéo che gần hết bề ngang nên nếu không có đường này thì mở ra là kẹt.
    page.addEventListener("click", function (e) {
      if (e.target !== page) return;
      page.classList.remove("left-open"); page.classList.remove("right-open");
    });
    // Nhớ chỗ đang đứng: mở lại trang mà rơi về mục đầu danh sách thì mỗi lần ghé qua trang
    // khác rồi quay lại là mất chỗ, trong khi cộng sự đang dùng thường chỉ là một hai mục.
    try { var l = localStorage.getItem("javis_ws_loai"); if (l === "agent" || l === "workflow") S.loai = l; S.chon.agent = localStorage.getItem("javis_ws_agent"); S.chon.workflow = localStorage.getItem("javis_ws_workflow"); } catch (e) {}
    try { var r = localStorage.getItem("javis_ws_rtab"); S.tabPhai = TAB_PHAI.indexOf(r) >= 0 ? r : "cai"; } catch (e) { S.tabPhai = "cai"; }
    chonTabPhai(S.tabPhai);
    taiDanhSach().then(function () { if (pendingCommand) { var cmd = pendingCommand; pendingCommand = null; selectCommand(cmd); } else { veTrai(); chonMacDinh(); } }).catch(function () { if (pendingCommand) { pendingCommand.resolve(false); pendingCommand = null; } veLoi(t("ws.err_session")); });
  }
  async function selectCommand(cmd) {
    S.loai = cmd.kind; S.chon[cmd.kind] = cmd.slug; S.q = ""; S.nhom = "";
    luuChon(); veTrai();
    var item = dangChon();
    if (!item) { cmd.resolve(false); return; }
    cmd.resolve(await moPhien(item, false));
  }
  function openCommand(kind, slug) {
    return new Promise(function (resolve) {
      var cmd = {kind: kind, slug: slug, resolve: resolve};
      if (active) { selectCommand(cmd); return; }
      if (!window.JavisNav) { resolve(false); return; }
      if (pendingCommand) pendingCommand.resolve(false);
      pendingCommand = cmd;
      window.JavisNav.go("workspace");
    });
  }
  // Mở trang Cộng sự ở ĐÚNG tab (menu nhanh của linh vật: "Trợ lý" / "Quy trình"). Khác
  // openCommand ở chỗ không nhắm tới một cộng sự cụ thể: chỉ chuyển tab rồi để chonMacDinh()
  // chọn mục gần nhất. Ghi localStorage TRƯỚC khi đổi trang, vì render() dựng lại S.loai từ
  // đó - đặt S.loai xong mới điều hướng thì render() lấy giá trị cũ ghi đè lên ngay.
  function openTab(kind) {
    var loai = kind === "workflow" ? "workflow" : "agent";
    // KHÔNG đụng vào S.q: ô tìm là một node DOM đang hiện chữ, xoá trạng thái mà không xoá ô
    // là danh sách đầy đủ nằm dưới một câu lọc vẫn nhìn thấy được. Nhóm thì khác - veTrai()
    // vẽ lại ô chọn theo S.nhom nên hai bên vẫn khớp.
    S.loai = loai; S.nhom = "";
    luuChon();
    if (active) { veTrai(); chonMacDinh(); return true; }
    if (!window.JavisNav) return false;
    window.JavisNav.go("workspace");
    return true;
  }
  function luuChon() { try { localStorage.setItem("javis_ws_loai", S.loai); if (S.chon.agent) localStorage.setItem("javis_ws_agent", S.chon.agent); if (S.chon.workflow) localStorage.setItem("javis_ws_workflow", S.chon.workflow); } catch (e) {} }

  // ---------- ô tìm thu gọn ----------
  // Nút kính lúp bung ô nhập ra; ô nhập RỖNG mà mất tiêu điểm thì tự thu lại. Esc xoá chữ,
  // vẽ lại danh sách đầy đủ rồi thu - nếu chỉ thu mà không xoá thì danh sách vẫn đang lọc
  // theo một câu không còn nhìn thấy ở đâu, và người dùng tưởng cộng sự của mình biến mất.
  function moODoTim(el, mo) {
    var o = el.querySelector("#wsSearch"), nut = el.querySelector("#wsSearchBtn");
    if (!o || !nut) return;
    o.hidden = !mo;
    nut.setAttribute("aria-expanded", mo ? "true" : "false");
    if (mo) o.focus(); else nut.focus();
  }
  function noiODoTim(el) {
    var o = el.querySelector("#wsSearch"), nut = el.querySelector("#wsSearchBtn");
    if (!o || !nut) return;
    nut.onclick = function () { if (o.hidden) moODoTim(el, true); else if (!o.value.trim()) moODoTim(el, false); else o.focus(); };
    o.oninput = function (e) { S.q = e.target.value; veDanhSach(); };
    o.onblur = function () { if (!o.value.trim()) { o.hidden = true; nut.setAttribute("aria-expanded", "false"); } };
    o.onkeydown = function (e) {
      if (e.key !== "Escape" && e.key !== "Esc") return;
      e.preventDefault(); e.stopPropagation();
      o.value = ""; S.q = ""; veDanhSach(); moODoTim(el, false);
    };
  }

  // ---------- tab cột phải ----------
  // Cây thư mục là node MƯỢN của màn chính, chỉ có MỘT bản. Rời tab (hay rời trang) mà không
  // trả thì màn chính và trang Trò chuyện mất hẳn panel Vault - cùng bài học với tab Thư mục
  // của trang Trò chuyện (xem sessions-ui.js chonTab).
  function traCayThuMuc() { try { if (window.JavisVaultPanel) window.JavisVaultPanel.giveBack(); } catch (e) {} }
  function chonTabPhai(tab) {
    var el = S.el; if (!el) return;
    S.tabPhai = TAB_PHAI.indexOf(tab) >= 0 ? tab : "cai";
    try { localStorage.setItem("javis_ws_rtab", S.tabPhai); } catch (e) {}
    el.querySelectorAll("[data-rtab]").forEach(function (b) { b.classList.toggle("active", b.dataset.rtab === S.tabPhai); });
    el.querySelectorAll("[data-rpane]").forEach(function (p) { p.classList.toggle("on", p.dataset.rpane === S.tabPhai); });
    var host = el.querySelector("#wsRightFiles");
    if (S.tabPhai === "files" && host && window.JavisVaultPanel) window.JavisVaultPanel.borrow(host);
    else traCayThuMuc();
  }

  function veTrai() {
    var el = S.el; if (!el) return;
    el.querySelectorAll("[data-loai]").forEach(function (b) { b.classList.toggle("on", b.dataset.loai === S.loai); });
    var nhoms = {}; danhSach().forEach(function (x) { var g = x.group || "Chung"; nhoms[g] = (nhoms[g] || 0) + 1; });
    if (S.nhom && !nhoms[S.nhom]) S.nhom = "";
    // Một Ô CHỌN chứ không phải hàng chip (chủ repo yêu cầu): brain thật có cả chục nhóm, mà
    // chip thì xuống dòng thành một mảng chiếm gần nửa cột trái, đẩy danh sách cộng sự xuống
    // dưới. Số đếm giữ lại trong nhãn từng dòng nên vẫn biết nhóm nào đông.
    var sel = el.querySelector("#wsGroup");
    var groups = [{name: "", label: t("ws.all_groups"), count: danhSach().length}].concat(Object.keys(nhoms).sort().map(function (g) { return {name:g, label:g, count:nhoms[g]}; }));
    sel.innerHTML = groups.map(function (g) { return '<option value="'+esc(g.name)+'">'+esc(g.label)+' ('+g.count+')</option>'; }).join('');
    sel.value = S.nhom;
    sel.onchange = function () { S.nhom = sel.value; veTrai(); };
    el.querySelector("#wsNew").innerHTML = ic("plus") + " " + esc(S.loai === "agent" ? t("ws.new_agent") : t("ws.new_workflow"));
    el.querySelector("#wsImport").textContent = t(S.loai === "agent" ? "ws.upload_agent" : "ws.upload_workflow");
    veDanhSach();
  }
  // Quy trình này có lần chạy nào ĐANG chạy không? Đọc thẳng từ S.tienDo (máy trạng thái ăn
  // wf_event) chứ không nuôi một cờ riêng: cờ riêng thì lúc chạy xong, lỗi, hay dừng chờ duyệt
  // phải nhớ tắt ở cả ba chỗ, quên một chỗ là icon quay mãi không dừng. apDung() đã đặt
  // trang_thai về "xong"/"loi"/"cho" ở cả ba đường đó, nên chỉ cần so đúng một giá trị.
  function dangChay(slug) {
    return Object.keys(S.tienDo).some(function (sid) {
      return S.sessionCuaPhien[sid] === slug && S.tienDo[sid] && S.tienDo[sid].trang_thai === "dang";
    });
  }
  function veDanhSach() {
    var el = S.el; if (!el) return;
    var ds = loc(danhSach(), S.q, S.nhom), chon = S.chon[S.loai];
    var host = el.querySelector("#wsList");
    if (!ds.length) { host.innerHTML = '<div class="ws-empty">' + esc(t("ws.empty")) + '</div>'; return; }
    host.innerHTML = ds.map(function (x) {
      // "Đang chạy" phải đọc được BẰNG CHỮ, không chỉ bằng icon quay: người tắt hiệu ứng
      // (prefers-reduced-motion, xem style.css) và trình đọc màn hình không thấy vòng quay
      // nào cả, nên thêm một chữ vào dòng phụ và một <title> vào icon.
      var chay = S.loai === "workflow" && dangChay(x.slug);
      var phu = S.loai === "agent" ? (x.group || "Chung") + " · " + (x.role || "") : (x.group || "Chung") + " · " + cacBuoc(x).length + " " + t("studio.steps");
      if (chay) phu += " · " + t("ws.running");
      return '<button type="button" class="ws-item' + (x.slug === chon ? " on" : "") + '" aria-pressed="' + (x.slug === chon) + '" data-slug="' + esc(x.slug) + '">' +
        '<span class="ws-item-ic">' + (S.loai === "agent" ? avatar(x, 42)
          : (chay ? ic("loader", { cls: "ic-spin", title: t("ws.running") }) : ic("workflow"))) + '</span>' +
        '<span class="ws-item-text"><strong>' + esc(x.name) + '</strong><small>' + esc(phu) + '</small></span></button>';
    }).join("");
    host.querySelectorAll("[data-slug]").forEach(function (b) {
      b.onclick = function () {
        S.chon[S.loai] = b.dataset.slug; luuChon(); veDanhSach(); moPhien(dangChon(), false);
        // Chọn xong thì đóng ngăn kéo - nhưng CHỈ ở khổ màn hình có ngăn kéo. Màn rộng lớp này
        // mang nghĩa ngược (đang ẩn cột), gỡ nó là bày lại cột người dùng vừa cố ý ẩn đi.
        if (heptLai()) S.el.querySelector("#wsPage").classList.remove("left-open");
      };
    });
  }
  function chonMacDinh() {
    var ds = danhSach();
    // Danh sách RỖNG (brain mới tinh, hay tab Quy trình khi chưa có quy trình nào): không có
    // phiên nào để mở nên phải KHOÁ ô nhập lại. Bỏ quên chốt này thì ô nhập vẫn sáng trong khi
    // `ready` còn false từ render(), người dùng gõ xong bấm gửi và KHÔNG CÓ GÌ xảy ra: canSend()
    // trả false, app.js lặng lẽ quay ra, màn hình không nói một lời nào.
    if (!ds.length) { chatReady(false); veGiua(null, t("ws.none_yet")); vePhai(null); return; }
    if (!ds.some(function (x) { return x.slug === S.chon[S.loai]; })) S.chon[S.loai] = ds[0].slug;
    veDanhSach(); return moPhien(dangChon(), false);
  }

  // ---------- phiên ----------
  // Mở phiên của cộng sự đang chọn: có phiên cũ thì mở tiếp (F5 hay quay lại vẫn còn hội
  // thoại), chưa có thì xin server một phiên TRỐNG đúng kênh. Phải xin trước tin đầu tiên,
  // vì kho phiên phải biết kênh thì lượt đầu mới đi đúng đường (server/main.py: /sessions/new).
  async function moPhien(item, moiHan) {
    var ticket = ++opening;
    chatReady(false); veGiua(item);
    if (!item) return false;
    var still = function () { return active && ticket === opening && conDangXem(item); };
    try {
      vePhai(item);
      var b = encodeURIComponent(brain()), ch = kenh(item), id = null;
      if (!moiHan) {
        var r = await api("/sessions?brain=" + b + "&channel=" + encodeURIComponent(ch) + "&limit=1");
        if (!still()) return false;
        if (r.sessions && r.sessions[0]) id = r.sessions[0].id;
      }
      if (!id) {
        var n = await api("/sessions/new", { method: "POST", body: fd({ brain: brain(), channel: ch }) });
        if (!still()) return false;
        // Câu lỗi của server (vd "channel phải là agent:<slug>...") là chữ cho NHẬT KÝ, không
        // phải chữ cho màn hình: nó nói về khuôn dữ liệu bên trong, không nói người dùng phải
        // làm gì, và không đi qua từ điển nên bản tiếng Anh vẫn ra tiếng Việt. Ghi ra console
        // cho người sửa lỗi, còn màn hình dùng câu của mình.
        if (!n.id) { try { console.warn("POST /sessions/new:", n.error); } catch (e2) {} throw new Error(t("ws.err_session")); }
        id = n.id;
      }
      S.sessionCuaPhien[id] = item.slug;
      if (window.JavisSessions) await window.JavisSessions.open(id, still);
      if (!still()) return false;
      if (!window.JavisSessions || window.JavisSessions.current() !== id) throw new Error(t("ws.err_session"));
      chatReady(true);
      toMoiLichSu();   // phiên vừa đổi: tô lại hàng đang mở ở tab Lịch sử
      if (S.loai === "workflow") veBuoc(item, tienDoHienTai(item));
      return true;
    } catch (e) {
      if (still()) { veLoi(t("ws.err_session")); if (window.JavisSessions) window.JavisSessions.new(); }
      return false;
    }
  }
  async function chayQuyTrinh() {
    var item = dangChon();
    if (!ready || S.loai !== "workflow" || !item || !window.JavisSend) return;
    var td = tienDoHienTai(item);
    if (td.trang_thai === "dang" || td.cho_duyet) return;
    var input = document.getElementById("chatInput");
    window.JavisSend((input && input.value.trim()) || t("ws.run_default"));
  }
  function veLoi(msg) { var el = S.el && S.el.querySelector("#wsIdentity"); if (el) {
    el.innerHTML += '<small class="ws-err">' + esc(msg) + '</small><button type="button" class="ws-btn" id="wsRetry">' + esc(t("ws.retry_session")) + '</button>';
    el.querySelector("#wsRetry").onclick = function () { moPhien(dangChon(), false); };
  } }
  // `nhac` = câu thay cho lời mời chọn mục, dùng khi danh sách rỗng (chưa có gì để chọn cả).
  function veGiua(item, nhac) {
    var el = S.el && S.el.querySelector("#wsIdentity"); if (!el) return;
    if (!item) {
      el.innerHTML = '<strong>' + esc(nhac || t("ws.pick_one")) + '</strong>';
      if (nhac) { var o = document.getElementById("chatInput"); if (o) o.placeholder = nhac; }
      return;
    }
    var phu = S.loai === "agent" ? (item.group || "Chung") + " · " + (item.role || "") : t("ws.wf_sub", { n: cacBuoc(item).length });
    el.innerHTML = (S.loai === "agent" ? avatar(item, 42) : ic("workflow")) + '<div><strong>' + esc(item.name) + '</strong><small>' + esc(phu) + '</small></div>';
    var inp = document.getElementById("chatInput");
    if (inp) inp.placeholder = S.loai === "agent" ? t("ws.ph_agent", { ten: item.name }) : t("ws.ph_workflow");
  }

  function thuGonCaiDat() {
    var page = S.el && S.el.querySelector("#wsPage");
    if (page) page.classList.toggle("right-open", !window.matchMedia("(max-width: 1060px)").matches);
  }
  async function sauLuu(item, loai) {
    await taiDanhSach();
    if (!active || S.loai !== loai || S.chon[loai] !== item.slug) return;
    veTrai(); veGiua(dangChon());
    // Retry session setup after saving; never unlock a chat bound to the wrong agent.
    if (!ready && !await moPhien(dangChon(), false)) return;
    thuGonCaiDat();
    var input = document.getElementById("chatInput");
    if (input) input.focus();
  }

  // ---------- cột phải ----------
  function vePhai(item) {
    var host = S.el && S.el.querySelector("#wsRightSet"); if (!host) return;
    // TRẢ cây thư mục về trước khi vẽ lại cột phải. Vẽ lại chỉ ghi vào khung Cài đặt, nhưng
    // cây là node mượn và chỉ có một bản: trả rồi mượn lại theo tab đang mở là luật gọn nhất,
    // khỏi phải nhớ chỗ nào được phép ghi đè chỗ nào không.
    traCayThuMuc();
    if (!item) { host.innerHTML = ""; veLichSu(null); chonTabPhai(S.tabPhai); return; }
    if (S.loai === "agent") {
      host.innerHTML = '<div class="ws-rtitle">' + esc(t("ws.agent_settings")) + '</div><div class="ws-form" id="wsAgentForm"></div>' +
        '<div class="ws-acts"><button type="button" class="ws-btn" id="wsExport">' + esc(t("studio.export")) + '</button>' +
        '<button type="button" class="ws-btn danger" id="wsDel">' + esc(t("common.delete")) + '</button></div>';
      // MƯỢN chính trình sửa agent của Studio (studio.js), không dựng bản thứ hai: chọn model,
      // chọn skill, nhóm... đã nằm ở đó, chép lại là hai bản trôi lệch nhau ngay lần sửa đầu.
      if (window.JavisStudio && window.JavisStudio.editAgent) {
        window.JavisStudio.editAgent(item, { host: host.querySelector("#wsAgentForm"), dsNhom: S.agents,
          onSaved: async function () { await sauLuu(item, "agent"); } });
      }
      host.querySelector("#wsExport").onclick = function () { window.JavisStudio && window.JavisStudio.exportItem("agent", item.slug); };
      host.querySelector("#wsDel").onclick = async function () {
        if (!confirm(t("studio.del_ag", { ten: item.name }))) return;
        await api("/agents/delete", { method: "POST", body: fd({ slug: item.slug, brain: brain() }) });
        S.chon.agent = null; await taiDanhSach(); veTrai(); chonMacDinh();
      };
    } else {
      var td = tienDoHienTai(item);
      host.innerHTML = '<div class="ws-workflow-head">'+ic("workflow")+'<h3>'+esc(item.name)+'</h3><p>'+esc(item.description || t("ws.wf_sub", {n:cacBuoc(item).length}))+'</p>'+
        '<button type="button" class="ws-btn primary ws-run-button" id="wsRun">'+ic("play")+' '+esc(t("ws.run"))+'</button></div>'+ '<div class="ws-rtitle">' + esc(t("ws.wf_progress")) + '</div>' +
        '<div class="ws-prog"><div style="width:' + phanTram(td) + '%"></div></div>' +
        '<div class="ws-status" id="wsWfStatus">' + esc(nhanTienDo(td)) + '</div>' +
        '<div class="ws-steps" id="wsSteps"></div>' +
        '<div class="ws-acts"><button type="button" class="ws-btn" id="wsEditWf">' + esc(t("ws.edit_steps")) + '</button>' +
        '<button type="button" class="ws-btn" id="wsExport">' + esc(t("studio.export")) + '</button>' +
        '<button type="button" class="ws-btn danger" id="wsDel">' + esc(t("common.delete")) + '</button></div>';
      host.querySelector("#wsRun").onclick = chayQuyTrinh;
      veBuoc(item, td);
      host.querySelector("#wsEditWf").onclick = function () { window.JavisStudio && window.JavisStudio.editWorkflow(item, { onSaved: async function () { await sauLuu(item, "workflow"); } }); };
      host.querySelector("#wsExport").onclick = function () { window.JavisStudio && window.JavisStudio.exportItem("workflow", item.slug); };
      host.querySelector("#wsDel").onclick = async function () {
        if (!confirm(t("studio.del_wf", { ten: item.name }))) return;
        await api("/workflows/delete", { method: "POST", body: fd({ slug: item.slug, brain: brain() }) });
        S.chon.workflow = null; await taiDanhSach(); veTrai(); chonMacDinh();
      };
    }
    veLichSu(item);
    chonTabPhai(S.tabPhai);
  }
  function tenAgent(slug) { var a = S.agents.find(function (x) { return x.slug === slug; }); return a ? a.name : (slug || ""); }
  // Tiến độ ĐANG XEM: lần chạy sống của phiên đang mở nếu có, không thì khung rỗng dựng từ
  // các bước khai trong file quy trình (để cột phải vẫn nói được quy trình này làm những gì).
  function tienDoHienTai(item) {
    var sid = window.JavisSessions ? window.JavisSessions.current() : null;
    if (sid && S.tienDo[sid]) return S.tienDo[sid];
    var buocs = cacBuoc(item);
    var td = tienDoMoi(buocs.length);
    td.buoc.forEach(function (b, i) { b.agent = tenAgent((buocs[i] || {}).agent); });
    return td;
  }
  function nhanTienDo(td) {
    if (td.trang_thai === "dang") return t("ws.running_step", { a: td.hien_tai + 1, b: td.buoc.length });
    if (td.trang_thai === "xong") return t("ws.done");
    if (td.trang_thai === "loi") return t("ws.failed");
    if (td.trang_thai === "dung") return t("ws.stopped");
    if (td.cho_duyet) return t("ws.waiting");
    return t("ws.ready");
  }
  function veBuoc(item, td) {
    var host = S.el && S.el.querySelector("#wsSteps"); if (!host) return;
    var buocs = cacBuoc(item);
    host.innerHTML = td.buoc.map(function (b, i) {
      var step = buocs[i] || {};
      var task = (step.name || step.title || step.task || "").replace(/\{\{input\}\}/g, t("ws.input_label")).replace(/\{\{prev\}\}/g, t("ws.previous_result"));
      var agent = agentOf(step.agent || b.agent);
      var nhan = { cho: t("ws.step_wait"), dang: t("ws.step_doing"), xong: t("ws.step_done"), loi: t("ws.step_err") }[b.trang_thai];
      return '<div class="ws-step ' + b.trang_thai + '"><span class="ws-num">' + (b.trang_thai === "xong" ? ic("check") : (i + 1)) + '</span>' +
        '<strong>' + esc(task.slice(0, 80) || t("ws.step_n", { n: i + 1 })) + '</strong><small>' + esc(nhan) + (b.loi ? ": " + esc(b.loi) : "") + '</small>' +
        '<div class="ws-who">' + avatar(agent, 26, b.trang_thai === "dang" ? "thinking" : "idle") + ' ' + esc(agent.name || b.agent || step.agent) + '</div></div>';
    }).join("") + (td.cho_duyet ? '<div class="ws-wait">' + esc(t("studio.wait1")) + ' "' + esc(td.cho_duyet.node) + '"' + (td.cho_duyet.prompt ? ": " + esc(td.cho_duyet.prompt) : "") +
      '<div><button type="button" class="ws-btn primary" id="wsApprove">' + esc(t("studio.approve")) + ' ' + esc(td.cho_duyet.code) + '</button><small>' + esc(t("studio.wait_warn")) + '</small></div></div>' : "");
    var ap = host.querySelector("#wsApprove");
    if (ap) ap.onclick = function () {
      ap.disabled = true;
      var sid = window.JavisSessions ? window.JavisSessions.current() : null;
      if (!sid || !window.JavisWsSend) return;
      window.JavisWsSend({ action: "wf_resume", session_id: sid, task_id: td.cho_duyet.task_id, node: td.cho_duyet.node, code: td.cho_duyet.code, brain: brain() });
      td.cho_duyet = null; td.trang_thai = "dang"; veBuoc(item, td);
    };
    var run = S.el.querySelector("#wsRun");
    if (run) { run.disabled = !ready || td.trang_thai === "dang" || !!td.cho_duyet; run.textContent = t(td.trang_thai === "dang" ? "ws.running" : "ws.run"); }
    var stt = S.el.querySelector("#wsWfStatus"); if (stt) stt.textContent = nhanTienDo(td);
    var pg = S.el.querySelector(".ws-prog > div"); if (pg) pg.style.width = phanTram(td) + "%";
  }
  // ---------- tab LỊCH SỬ (cột phải) ----------
  // Trước 0.59.3 lịch sử nằm DƯỚI ĐÁY khung Cài đặt: muốn xem lần chạy hôm qua thì phải cuộn
  // qua hết form sửa trợ lý, qua ba nút Xuất/Xoá, qua danh sách bước. Chủ dự án nói thẳng là
  // không tiện. Nay nó là một TAB riêng, ngang hàng với Cài đặt và Thư mục, đúng kiểu cột lịch
  // sử của trang Trò chuyện: bấm một cái là ra, không phải cuộn tìm.
  function veLichSu(item) {
    var host = S.el && S.el.querySelector("#wsRightHistory"); if (!host) return;
    if (!item) { host.innerHTML = '<div class="ws-empty">' + esc(t("ws.pick_one")) + '</div>'; return; }
    host.innerHTML =
      (S.loai === "workflow"
        ? '<div class="ws-rtitle">' + esc(t("ws.history_runs")) + '</div><div class="ws-runs" id="wsRuns"></div>'
        : "") +
      '<div class="ws-rtitle">' + esc(t("ws.history_chats")) + '</div><div class="ws-chatside" id="wsSess"></div>';
    if (S.loai === "workflow") taiLichSu(item);
    // Danh sách hội thoại là CHÍNH cột lịch sử của trang Trò chuyện (sessions-ui.js), gắn vào
    // đây ở chế độ lọc theo kênh: cùng ô tìm, cùng nhóm theo ngày, cùng ghim / đổi tên / xoá,
    // cùng nút "Xem thêm". Chủ dự án yêu cầu đúng trải nghiệm ấy chứ không phải một danh sách
    // rút gọn khác; và một bản thứ hai thì lệch dần khỏi bản gốc ngay từ lần sửa đầu tiên.
    if (window.JavisChatSide && window.JavisChatSide.mount) {
      window.JavisChatSide.mount(host.querySelector("#wsSess"), {
        kenh: kenh(item), chiHoiThoai: true,
        onNew: function () { var x = dangChon(); if (x) moPhien(x, true); },
      });
    }
  }
  // Tô lại hàng của phiên ĐANG MỞ trong danh sách LẦN CHẠY mà không tải lại gì cả: vẽ lại cả
  // tab chỉ để đổi một cái viền là tốn một request và làm danh sách nháy một nhịp.
  // (Danh sách hội thoại bên dưới là cột lịch sử mượn của trang Trò chuyện, nó tự tô hàng đang
  // mở mỗi lần app.js gọi JavisChatSide.refresh - không đụng tay vào đây.)
  function toMoiLichSu() {
    var el = S.el; if (!el) return;
    var cur = window.JavisSessions ? window.JavisSessions.current() : null;
    el.querySelectorAll("#wsRuns [data-sid]").forEach(function (b) {
      b.classList.toggle("on", !!cur && b.dataset.sid === cur);
    });
  }
  function moPhienCu(sid) {
    if (!sid || !window.JavisSessions) return;
    Promise.resolve(window.JavisSessions.open(sid)).then(toMoiLichSu).catch(function () {});
  }
  async function taiLichSu(item) {
    var host = S.el && S.el.querySelector("#wsRuns"); if (!host) return;
    var r = await api("/workflows/runs?brain=" + encodeURIComponent(brain()) + "&slug=" + encodeURIComponent(item.slug) + "&limit=20");
    // Vẽ trễ: người dùng có thể đã đổi sang mục khác trong lúc chờ mạng. Ghi vào khung của
    // mục cũ là lịch sử của quy trình A nằm dưới tên quy trình B.
    if (!conDangXem(item)) return;
    host = S.el && S.el.querySelector("#wsRuns"); if (!host) return;
    var ds = r.runs || [];
    if (!ds.length) { host.innerHTML = '<div class="ws-empty">' + esc(t("ws.no_runs")) + '</div>'; return; }
    var curSid = window.JavisSessions ? window.JavisSessions.current() : null;
    host.innerHTML = ds.map(function (x) {
      var d = new Date(Number(x.started_at || 0) * 1000);
      return '<button type="button" class="ws-run ' + esc(x.status) + (x.session_id && x.session_id === curSid ? " on" : "") + '" data-sid="' + esc(x.session_id || "") + '">' +
        '<span class="ws-run-avatars">' + Array.from(new Set((x.steps || []).map(function (b) { return b.agent; }).filter(Boolean))).slice(0, 3).map(function (slug) { return avatar(agentOf(slug), 22); }).join('') + '</span><span>' + esc(gioPhut(d)) + '</span>' +
        '<span class="ws-run-st">' + esc(x.nhan || x.status || "") + '</span><small>' + esc(loiNguoiGo(x.input).slice(0, 60)) + '</small></button>';
    }).join("");
    host.querySelectorAll("[data-sid]").forEach(function (b) { b.onclick = function () { moPhienCu(b.dataset.sid); }; });
  }
  // Bỏ khối "[NGỮ CẢNH GIAO DIỆN: ...]" mà dashboard chèn trước câu hỏi: kho lần chạy lưu
  // nguyên chuỗi đã gửi, nên dòng lịch sử mà in thô thì 60 ký tự đầu là khối đó chứ không phải
  // câu người dùng gõ. Dùng lại chính hàm của app.js, đừng viết bản thứ hai để rồi lệch nhau.
  function loiNguoiGo(s) {
    try { return window.chuNguoiGo ? window.chuNguoiGo(s || "") : String(s || ""); }
    catch (e) { return String(s || ""); }
  }
  // Ngày giờ theo NGÔN NGỮ giao diện, không khoá "vi-VN": đổi sang tiếng Anh mà ngày vẫn
  // dd/mm là nửa màn hình nói một kiểu (cùng lý do với LOC() bên studio.js).
  function gioPhut(d) {
    var loc = (window.JavisI18n && window.JavisI18n.locale && window.JavisI18n.locale()) || "vi-VN";
    try { return d.toLocaleString(loc, { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" }); }
    catch (e) { return d.toLocaleString(); }
  }
  // ---------- sự kiện quy trình từ WebSocket ----------
  // app.js chuyển MỌI khung wf_event vào đây, kể cả của phiên đang không mở: ghi theo
  // session_id để mở lại phiên đó là thấy ngay tiến độ, không phải chạy lại từ đầu.
  function onWfEvent(frame) {
    var sid = frame.session_id, ev = frame.event || {}; if (!sid) return;
    var item = dangChon();
    // Phiên mở từ cột LỊCH SỬ đi thẳng qua JavisSessions.open (module lịch sử lo), không qua
    // moPhien nên chưa có tên trong sổ "phiên nào của cộng sự nào". Lần chạy đầu tiên ở đó mà
    // thiếu dòng này thì icon quay ở cột trái không bao giờ bật: dangChay() tra sổ không thấy.
    if (item && !S.sessionCuaPhien[sid] &&
        window.JavisSessions && window.JavisSessions.current() === sid) {
      S.sessionCuaPhien[sid] = item.slug;
    }
    if (!S.tienDo[sid]) {
      var n = (item && S.loai === "workflow" && S.sessionCuaPhien[sid] === item.slug) ? cacBuoc(item).length : Number(ev.steps || 0);
      S.tienDo[sid] = tienDoMoi(n);
    }
    apDung(S.tienDo[sid], ev);
    // Vẽ lại danh sách trái ở MỌI sự kiện, kể cả của phiên đang không mở: icon quay ở hàng
    // quy trình đọc từ S.tienDo, nên không vẽ lại thì bắt đầu chạy mà hàng vẫn đứng im, và
    // chạy xong rồi mà vẫn quay.
    if (S.loai === "workflow") veDanhSach();
    var cur = window.JavisSessions ? window.JavisSessions.current() : null;
    if (item && S.loai === "workflow" && cur === sid) {
      veBuoc(item, S.tienDo[sid]);
      // Xong / lỗi / chờ duyệt = lịch sử chạy vừa có dòng mới và mốc "chạy gần nhất" vừa đổi,
      // nên danh sách bên trái phải xếp lại. Không làm thì quy trình vừa chạy vẫn nằm cuối.
      if (ev.type === "done" || ev.type === "error" || ev.type === "wait_user") { taiLichSu(item); taiDanhSach().then(veTrai); }
    }
  }

  // Lượt của một phiên vừa KẾT THÚC (app.js gọi ở khung turn_done). Đây là lưới an toàn cuối
  // cùng cho tiến độ: server bắn `stopped` khi người dùng bấm Dừng, nhưng lượt còn có thể chết
  // theo những đường không kịp phát sự kiện nào (engine bị giết, WebSocket rớt giữa chừng, tiến
  // trình máy chủ khởi động lại). Lượt xong rồi mà tiến độ vẫn "dang" thì chắc chắn nó sẽ không
  // bao giờ nhúc nhích nữa - đóng nó lại ở đây, đừng để icon quay vĩnh viễn.
  function onTurnDone(sid) {
    if (!sid || !S.tienDo[sid] || S.tienDo[sid].trang_thai !== "dang") return;
    apDung(S.tienDo[sid], { type: "stopped" });
    if (S.loai === "workflow") veDanhSach();
    var item = dangChon();
    var cur = window.JavisSessions ? window.JavisSessions.current() : null;
    if (item && S.loai === "workflow" && cur === sid) veBuoc(item, S.tienDo[sid]);
  }

  // ---------- tạo mới ----------
  function taoMoi() {
    if (!window.JavisStudio) return;
    var loai = S.loai;
    var sau = async function (saved) {
      await taiDanhSach(); if (!active || S.loai !== loai) return;
      if (saved && saved.slug) S.chon[loai] = saved.slug;
      veTrai();
      if (await chonMacDinh()) { thuGonCaiDat(); document.getElementById("chatInput").focus(); }
    };
    // Không truyền `host`: tạo mới vẫn mở modal của Studio (cột phải đang là form của mục
    // đang chọn, vẽ đè lên đó thì người dùng tưởng mình đang sửa mục cũ).
    if (S.loai === "agent") window.JavisStudio.editAgent(null, { dsNhom: S.agents, onSaved: sau });
    else window.JavisStudio.editWorkflow(null, { onSaved: sau });
  }

  // Rời trang: trả ô nhập về lời mời chung. veGiua() đổi placeholder thành "Nhắn cho <trợ lý>",
  // mà ô nhập là node MƯỢN của app - không trả lại thì sang trang Trò chuyện nó vẫn mời người
  // dùng nhắn cho một cộng sự không còn ở đâu trên màn hình. console.js gọi hàm này trong
  // _pageLeave, ngay trước khi trả node chat về HUD.
  // console.js cũng trả cây trong _returnChatNodes, nhưng trả ở đây nữa là đúng chỗ: tab Thư
  // mục là của trang NÀY mượn, nên trang này tự dọn lấy chứ không phó thác cho người gọi.
  // Hàm trả kiểm _vaultSlot trước nên gọi hai lần vẫn vô hại.
  function roi() {
    active = false; opening++; chatReady(true);
    traCayThuMuc();
    // XOÁ câu đang tìm. S.q sống ở mức module còn ô nhập chết theo DOM của trang, nên giữ lại
    // là lần sau quay vào danh sách đã bị lọc mà ô tìm thì rỗng và đang thu: người dùng thấy
    // cộng sự của mình biến mất, không có gì trên màn hình nói vì sao.
    S.q = "";
    var inp = document.getElementById("chatInput");
    if (inp) inp.placeholder = t("bar.input_ph");
  }

  window.JavisWorkspace = { render: render, roi: roi, openCommand: openCommand, openTab: openTab, onTurnDone: onTurnDone, canSend: function () { return !active || ready; }, onChatState: onChatState, chayQuyTrinh: chayQuyTrinh, onWfEvent: onWfEvent, sapXep: sapXep, loc: loc, tienDoMoi: tienDoMoi, apDung: apDung, phanTram: phanTram, dangChay: dangChay, tabPhai: chonTabPhai, state: function () { return S; } };
})();
