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
      return khongDau([x.name, x.role, x.description, x.slug].join(" ")).indexOf(nq) >= 0;
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
      if (st.buoc[i]) st.buoc[i].trang_thai = "xong";
    } else if (ev.type === "step_error") {
      if (st.buoc[i]) st.buoc[i].loi = ev.content || "";
    } else if (ev.type === "wait_user") {
      st.trang_thai = "cho";
      st.cho_duyet = { node: ev.node || "", prompt: ev.prompt || "", task_id: ev.task_id || "", code: ev.code || "" };
    } else if (ev.type === "error") {
      st.trang_thai = "loi";
      if (st.hien_tai >= 0 && st.buoc[st.hien_tai] && st.buoc[st.hien_tai].trang_thai === "dang") {
        st.buoc[st.hien_tai].trang_thai = "loi";
        st.buoc[st.hien_tai].loi = ev.content || "";
      }
    } else if (ev.type === "done") {
      st.trang_thai = "xong"; st.cho_duyet = null;
      st.buoc.forEach(function (b) { b.trang_thai = "xong"; });
    }
    return st;
  }
  function phanTram(st) {
    if (!st.buoc.length) return 0;
    if (st.trang_thai === "xong") return 100;
    return Math.round(st.buoc.filter(function (b) { return b.trang_thai === "xong"; }).length / st.buoc.length * 100);
  }

  // ---------- trạng thái trang ----------
  var S = { loai: "agent", q: "", nhom: "", agents: [], workflows: [], chon: { agent: null, workflow: null },
            el: null, tienDo: {}, sessionCuaPhien: {} };   // tienDo[session_id] = tiến độ lần chạy đang xem

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
    S.el = el;
    el.innerHTML =
      '<div class="wspage" id="wsPage">' +
        '<aside class="ws-left" id="wsLeft">' +
          '<div class="ws-seg"><button type="button" data-loai="agent">' + ic("bot") + ' ' + esc(t("ws.tab_agent")) + '</button>' +
          '<button type="button" data-loai="workflow">' + ic("workflow") + ' ' + esc(t("ws.tab_workflow")) + '</button></div>' +
          '<input class="ws-search" id="wsSearch" placeholder="' + esc(t("ws.search_ph")) + '">' +
          '<select class="ws-group" id="wsGroup"></select>' +
          '<div class="ws-list" id="wsList"></div>' +
          '<div class="ws-left-foot"><button type="button" class="ws-btn" id="wsNew">' + ic("plus") + ' ' + esc(t("ws.new_item")) + '</button>' +
          '<button type="button" class="ws-btn" id="wsStore">' + ic("package") + ' Javis Store</button></div>' +
        '</aside>' +
        '<div class="ws-main">' +
          '<div class="ws-bar">' +
            '<button type="button" class="ws-ico" id="wsLeftBtn" title="' + esc(t("ws.toggle_list")) + '">' + ic("panel-left") + '</button>' +
            '<div class="ws-id" id="wsIdentity"></div>' +
            '<button type="button" class="ws-btn" id="wsNewChat">' + esc(t("sess.new_chat")) + '</button>' +
            // Bộ icon chưa đóng gói "panel-right" (xem icons.manifest.json) và thêm icon mới
            // phải chạy gen_icons tải mạng - lật gương panel-left bằng CSS rẻ hơn mà cùng nghĩa.
            '<button type="button" class="ws-ico lat" id="wsRightBtn" title="' + esc(t("ws.toggle_panel")) + '">' + ic("panel-left") + '</button>' +
          '</div>' +
          '<div class="ws-slot" id="wsSlot"></div>' +
        '</div>' +
        '<aside class="ws-right" id="wsRight"></aside>' +
      '</div>';
    if (opts && opts.borrow) opts.borrow(el.querySelector("#wsSlot"));
    el.querySelectorAll("[data-loai]").forEach(function (b) { b.onclick = function () { S.loai = b.dataset.loai; luuChon(); veTrai(); chonMacDinh(); }; });
    el.querySelector("#wsSearch").oninput = function (e) { S.q = e.target.value; veDanhSach(); };
    el.querySelector("#wsGroup").onchange = function (e) { S.nhom = e.target.value; veDanhSach(); };
    el.querySelector("#wsNew").onclick = taoMoi;
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
    taiDanhSach().then(function () { veTrai(); chonMacDinh(); });
  }
  function luuChon() { try { localStorage.setItem("javis_ws_loai", S.loai); if (S.chon.agent) localStorage.setItem("javis_ws_agent", S.chon.agent); if (S.chon.workflow) localStorage.setItem("javis_ws_workflow", S.chon.workflow); } catch (e) {} }

  function veTrai() {
    var el = S.el; if (!el) return;
    el.querySelectorAll("[data-loai]").forEach(function (b) { b.classList.toggle("on", b.dataset.loai === S.loai); });
    var nhoms = {}; danhSach().forEach(function (x) { nhoms[x.group || "Chung"] = 1; });
    var sel = el.querySelector("#wsGroup");
    sel.innerHTML = '<option value="">' + esc(t("ws.all_groups")) + '</option>' + Object.keys(nhoms).sort().map(function (g) { return '<option value="' + esc(g) + '"' + (g === S.nhom ? " selected" : "") + '>' + esc(g) + '</option>'; }).join("");
    el.querySelector("#wsNew").innerHTML = ic("plus") + " " + esc(S.loai === "agent" ? t("ws.new_agent") : t("ws.new_workflow"));
    veDanhSach();
  }
  function veDanhSach() {
    var el = S.el; if (!el) return;
    var ds = loc(danhSach(), S.q, S.nhom), chon = S.chon[S.loai];
    var host = el.querySelector("#wsList");
    if (!ds.length) { host.innerHTML = '<div class="ws-empty">' + esc(t("ws.empty")) + '</div>'; return; }
    host.innerHTML = ds.map(function (x) {
      var phu = S.loai === "agent" ? (x.group || "Chung") + " · " + (x.role || "") : (x.group || "Chung") + " · " + cacBuoc(x).length + " " + t("studio.steps");
      return '<button type="button" class="ws-item' + (x.slug === chon ? " on" : "") + '" data-slug="' + esc(x.slug) + '">' +
        '<span class="ws-item-ic">' + ic(S.loai === "agent" ? "bot" : "workflow") + '</span>' +
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
    var ds = danhSach(); if (!ds.length) { veGiua(null); vePhai(null); return; }
    if (!ds.some(function (x) { return x.slug === S.chon[S.loai]; })) S.chon[S.loai] = ds[0].slug;
    veDanhSach(); moPhien(dangChon(), false);
  }

  // ---------- phiên ----------
  // Mở phiên của cộng sự đang chọn: có phiên cũ thì mở tiếp (F5 hay quay lại vẫn còn hội
  // thoại), chưa có thì xin server một phiên TRỐNG đúng kênh. Phải xin trước tin đầu tiên,
  // vì kho phiên phải biết kênh thì lượt đầu mới đi đúng đường (server/main.py: /sessions/new).
  async function moPhien(item, moiHan) {
    veGiua(item); vePhai(item);
    if (!item) return;
    var b = encodeURIComponent(brain()), ch = kenh(item), id = null;
    if (!moiHan) {
      var r = await api("/sessions?brain=" + b + "&channel=" + encodeURIComponent(ch) + "&limit=1");
      if (r.sessions && r.sessions[0]) id = r.sessions[0].id;
    }
    if (!id) {
      var n = await api("/sessions/new", { method: "POST", body: fd({ brain: brain(), channel: ch }) });
      if (!n.id) { veLoi(n.error || t("ws.err_session")); return; }
      id = n.id;
    }
    S.sessionCuaPhien[id] = item.slug;
    if (window.JavisSessions) window.JavisSessions.open(id);
    // Phiên vừa đổi thì tiến độ ở cột phải phải vẽ lại theo phiên MỚI (mỗi phiên một lần chạy).
    if (S.loai === "workflow") { var td = tienDoHienTai(item); veBuoc(item, td); }
  }
  function veLoi(msg) { var el = S.el && S.el.querySelector("#wsIdentity"); if (el) el.innerHTML += '<small class="ws-err">' + esc(msg) + '</small>'; }
  function veGiua(item) {
    var el = S.el && S.el.querySelector("#wsIdentity"); if (!el) return;
    if (!item) { el.innerHTML = '<strong>' + esc(t("ws.pick_one")) + '</strong>'; return; }
    var phu = S.loai === "agent" ? (item.group || "Chung") + " · " + (item.role || "") : t("ws.wf_sub", { n: cacBuoc(item).length });
    el.innerHTML = ic(S.loai === "agent" ? "bot" : "workflow") + '<div><strong>' + esc(item.name) + '</strong><small>' + esc(phu) + '</small></div>';
    var inp = document.getElementById("chatInput");
    if (inp) inp.placeholder = S.loai === "agent" ? t("ws.ph_agent", { ten: item.name }) : t("ws.ph_workflow");
  }

  // ---------- cột phải ----------
  function vePhai(item) {
    var host = S.el && S.el.querySelector("#wsRight"); if (!host) return;
    if (!item) { host.innerHTML = ""; return; }
    if (S.loai === "agent") {
      host.innerHTML = '<div class="ws-rtitle">' + esc(t("ws.agent_settings")) + '</div><div class="ws-form" id="wsAgentForm"></div>' +
        '<div class="ws-acts"><button type="button" class="ws-btn" id="wsExport">' + esc(t("studio.export")) + '</button>' +
        '<button type="button" class="ws-btn danger" id="wsDel">' + esc(t("common.delete")) + '</button></div>' +
        '<div class="ws-rtitle">' + esc(t("ws.recent_chats")) + '</div><div class="ws-sess" id="wsSess"></div>';
      // MƯỢN chính trình sửa agent của Studio (studio.js), không dựng bản thứ hai: chọn model,
      // chọn skill, nhóm... đã nằm ở đó, chép lại là hai bản trôi lệch nhau ngay lần sửa đầu.
      if (window.JavisStudio && window.JavisStudio.editAgent) {
        window.JavisStudio.editAgent(item, { host: host.querySelector("#wsAgentForm"), dsNhom: S.agents,
          onSaved: async function () { await taiDanhSach(); veTrai(); veGiua(dangChon()); } });
      }
      host.querySelector("#wsExport").onclick = function () { window.JavisStudio && window.JavisStudio.exportItem("agent", item.slug); };
      host.querySelector("#wsDel").onclick = async function () {
        if (!confirm(t("studio.del_ag", { ten: item.name }))) return;
        await api("/agents/delete", { method: "POST", body: fd({ slug: item.slug, brain: brain() }) });
        S.chon.agent = null; await taiDanhSach(); veTrai(); chonMacDinh();
      };
      taiPhienGanDay(item);
    } else {
      var td = tienDoHienTai(item);
      host.innerHTML = '<div class="ws-rtitle">' + esc(t("ws.wf_progress")) + '</div>' +
        '<div class="ws-prog"><div style="width:' + phanTram(td) + '%"></div></div>' +
        '<div class="ws-status" id="wsWfStatus">' + esc(nhanTienDo(td)) + '</div>' +
        '<div class="ws-steps" id="wsSteps"></div>' +
        '<div class="ws-acts"><button type="button" class="ws-btn" id="wsEditWf">' + esc(t("ws.edit_steps")) + '</button>' +
        '<button type="button" class="ws-btn" id="wsExport">' + esc(t("studio.export")) + '</button>' +
        '<button type="button" class="ws-btn danger" id="wsDel">' + esc(t("common.delete")) + '</button></div>' +
        '<div class="ws-rtitle">' + esc(t("ws.run_history")) + '</div><div class="ws-runs" id="wsRuns"></div>';
      veBuoc(item, td);
      host.querySelector("#wsEditWf").onclick = function () { window.JavisStudio && window.JavisStudio.editWorkflow(item, { onSaved: async function () { await taiDanhSach(); veTrai(); vePhai(dangChon()); } }); };
      host.querySelector("#wsExport").onclick = function () { window.JavisStudio && window.JavisStudio.exportItem("workflow", item.slug); };
      host.querySelector("#wsDel").onclick = async function () {
        if (!confirm(t("studio.del_wf", { ten: item.name }))) return;
        await api("/workflows/delete", { method: "POST", body: fd({ slug: item.slug, brain: brain() }) });
        S.chon.workflow = null; await taiDanhSach(); veTrai(); chonMacDinh();
      };
      taiLichSu(item);
    }
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
    if (td.cho_duyet) return t("ws.waiting");
    return t("ws.ready");
  }
  function veBuoc(item, td) {
    var host = S.el && S.el.querySelector("#wsSteps"); if (!host) return;
    var buocs = cacBuoc(item);
    host.innerHTML = td.buoc.map(function (b, i) {
      var task = (buocs[i] || {}).task || "";
      var nhan = { cho: t("ws.step_wait"), dang: t("ws.step_doing"), xong: t("ws.step_done"), loi: t("ws.step_err") }[b.trang_thai];
      return '<div class="ws-step ' + b.trang_thai + '"><span class="ws-num">' + (b.trang_thai === "xong" ? ic("check") : (i + 1)) + '</span>' +
        '<strong>' + esc(task.slice(0, 80) || t("ws.step_n", { n: i + 1 })) + '</strong><small>' + esc(nhan) + (b.loi ? ": " + esc(b.loi) : "") + '</small>' +
        '<div class="ws-who">' + ic("bot") + ' ' + esc(b.agent || tenAgent((buocs[i] || {}).agent)) + '</div></div>';
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
    var stt = S.el.querySelector("#wsWfStatus"); if (stt) stt.textContent = nhanTienDo(td);
    var pg = S.el.querySelector(".ws-prog > div"); if (pg) pg.style.width = phanTram(td) + "%";
  }
  async function taiLichSu(item) {
    var host = S.el && S.el.querySelector("#wsRuns"); if (!host) return;
    var r = await api("/workflows/runs?brain=" + encodeURIComponent(brain()) + "&slug=" + encodeURIComponent(item.slug) + "&limit=10");
    // Vẽ trễ: người dùng có thể đã đổi sang mục khác trong lúc chờ mạng. Ghi vào khung của
    // mục cũ là lịch sử của quy trình A nằm dưới tên quy trình B.
    if (!conDangXem(item)) return;
    host = S.el && S.el.querySelector("#wsRuns"); if (!host) return;
    var ds = r.runs || [];
    if (!ds.length) { host.innerHTML = '<div class="ws-empty">' + esc(t("ws.no_runs")) + '</div>'; return; }
    host.innerHTML = ds.map(function (x) {
      var d = new Date(Number(x.started_at || 0) * 1000);
      return '<button type="button" class="ws-run ' + esc(x.status) + '" data-sid="' + esc(x.session_id || "") + '">' +
        '<span>' + esc(gioPhut(d)) + '</span>' +
        '<span class="ws-run-st">' + esc(x.nhan || x.status || "") + '</span><small>' + esc(loiNguoiGo(x.input).slice(0, 60)) + '</small></button>';
    }).join("");
    host.querySelectorAll("[data-sid]").forEach(function (b) { b.onclick = function () { if (b.dataset.sid && window.JavisSessions) window.JavisSessions.open(b.dataset.sid); }; });
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
  async function taiPhienGanDay(item) {
    var host = S.el && S.el.querySelector("#wsSess"); if (!host) return;
    var r = await api("/sessions?brain=" + encodeURIComponent(brain()) + "&channel=" + encodeURIComponent("agent:" + item.slug) + "&limit=8");
    if (!conDangXem(item)) return;
    host = S.el && S.el.querySelector("#wsSess"); if (!host) return;
    var ds = r.sessions || [];
    if (!ds.length) { host.innerHTML = '<div class="ws-empty">' + esc(t("ws.no_chats")) + '</div>'; return; }
    host.innerHTML = ds.map(function (s) { return '<button type="button" class="ws-run" data-sid="' + esc(s.id) + '"><strong>' + esc(s.title || s.preview || t("ws.untitled")) + '</strong></button>'; }).join("");
    host.querySelectorAll("[data-sid]").forEach(function (b) { b.onclick = function () { window.JavisSessions && window.JavisSessions.open(b.dataset.sid); }; });
  }

  // ---------- sự kiện quy trình từ WebSocket ----------
  // app.js chuyển MỌI khung wf_event vào đây, kể cả của phiên đang không mở: ghi theo
  // session_id để mở lại phiên đó là thấy ngay tiến độ, không phải chạy lại từ đầu.
  function onWfEvent(frame) {
    var sid = frame.session_id, ev = frame.event || {}; if (!sid) return;
    var item = dangChon();
    if (!S.tienDo[sid]) {
      var n = (item && S.loai === "workflow" && S.sessionCuaPhien[sid] === item.slug) ? cacBuoc(item).length : Number(ev.steps || 0);
      S.tienDo[sid] = tienDoMoi(n);
    }
    apDung(S.tienDo[sid], ev);
    var cur = window.JavisSessions ? window.JavisSessions.current() : null;
    if (item && S.loai === "workflow" && cur === sid) {
      veBuoc(item, S.tienDo[sid]);
      // Xong / lỗi / chờ duyệt = lịch sử chạy vừa có dòng mới và mốc "chạy gần nhất" vừa đổi,
      // nên danh sách bên trái phải xếp lại. Không làm thì quy trình vừa chạy vẫn nằm cuối.
      if (ev.type === "done" || ev.type === "error" || ev.type === "wait_user") { taiLichSu(item); taiDanhSach().then(veTrai); }
    }
  }

  // ---------- tạo mới ----------
  function taoMoi() {
    if (!window.JavisStudio) return;
    var sau = async function () { await taiDanhSach(); veTrai(); chonMacDinh(); };
    // Không truyền `host`: tạo mới vẫn mở modal của Studio (cột phải đang là form của mục
    // đang chọn, vẽ đè lên đó thì người dùng tưởng mình đang sửa mục cũ).
    if (S.loai === "agent") window.JavisStudio.editAgent(null, { dsNhom: S.agents, onSaved: sau });
    else window.JavisStudio.editWorkflow(null, { onSaved: sau });
  }

  // Rời trang: trả ô nhập về lời mời chung. veGiua() đổi placeholder thành "Nhắn cho <trợ lý>",
  // mà ô nhập là node MƯỢN của app - không trả lại thì sang trang Trò chuyện nó vẫn mời người
  // dùng nhắn cho một cộng sự không còn ở đâu trên màn hình. console.js gọi hàm này trong
  // _pageLeave, ngay trước khi trả node chat về HUD.
  function roi() {
    var inp = document.getElementById("chatInput");
    if (inp) inp.placeholder = t("bar.input_ph");
  }

  window.JavisWorkspace = { render: render, roi: roi, onWfEvent: onWfEvent, sapXep: sapXep, loc: loc, tienDoMoi: tienDoMoi, apDung: apDung, phanTram: phanTram, state: function () { return S; } };
})();
