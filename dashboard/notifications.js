// Hòm thư navbar - HAI tầng dữ liệu, cố ý không trộn:
//
//   "Của tôi"  = /inbox : thư RIÊNG (kết quả việc nền, báo cáo định kỳ). Đã-đọc nằm ở SERVER
//                nên điện thoại và máy tính đếm giống nhau, và bấm vào là quay về ĐÚNG hội
//                thoại đã hỏi - nội dung đầy đủ nằm ở đó, không phải trong cái thẻ này.
//   "Tin tức"  = /notifications : bản phát hành + tin cộng đồng, phát chung cho mọi người.
//                Từ 0.187.0 đã-đọc cũng nằm ở SERVER (/notifications/read), nên đọc trên điện thoại là
//                máy tính cũng hết chấm; localStorage chỉ còn là bản đệm, và lần đầu được đẩy lên server.
//
// Gộp một danh sách thì một kết quả công việc thật bị chôn dưới mấy dòng changelog.
(function () {
  var READ_KEY = "javis.notifications.read";
  var INIT_KEY = "javis.notifications.initialized";
  var TAB_KEY = "javis.notifications.tab";
  // News items removed with their X (0.408.0). News comes from the changelog feed, so it cannot be deleted at the
  // source: this device remembers the ids and never shows them again, not even under "Show read".
  var HIDE_KEY = "javis.notifications.hidden";
  var MAX_ITEMS = 30;
  var PAGE_SIZE = 5;
  var state = { items: [], read: new Set(), loadedAt: 0, loading: false, visibleCount: PAGE_SIZE,
                thu: [], thuChuaDoc: 0, tab: "mine", view: "list", note: {}, policy: null,
                // 0.408.0 (owner: "read notices must hide, Mark all read must clear them"): both tabs list unread only;
                // `xemDaDoc` is the "Show N read" link at the bottom, for this opening of the panel only.
                xemDaDoc: false, an: new Set(), flash: "" };
  // 0.403.0, Javis Core as the notification commander (docs/dev/2026-10-javis-core-chi-huy-thong-bao.md): notices
  // its rules kept quiet are `filtered` and live under "Filtered"; every card takes the owner's feedback in the
  // two buttons, "Needed" / "Not needed" (owner, 2026-10-29: emoji go on the notice once it is opened in Javis Core's
  // chat, where every answer already takes the six reactions); the "Filter" view sets each group's mode, undoes changes.
  var GROUPS = ["reminder", "question", "chatbot", "connection", "incident", "job", "agent", "team", "cost", "update", "other"];
  var MODES = ["all", "important", "urgent", "off"];
  // Full keys spelled out, so the i18n check finds every one of them.
  var GROUP_KEY = { reminder: "noti.grp_reminder", question: "noti.grp_question", chatbot: "noti.grp_chatbot",
    connection: "noti.grp_connection", incident: "noti.grp_incident", job: "noti.grp_job", agent: "noti.grp_agent",
    team: "noti.grp_team", cost: "noti.grp_cost", update: "noti.grp_update", other: "noti.grp_other" };
  var MODE_KEY = { all: "noti.mode_all", important: "noti.mode_important", urgent: "noti.mode_urgent", off: "noti.mode_off" };
  function icon(n) { return typeof window.ic === "function" ? window.ic(n) : ""; }
  function loadAn() {
    try { state.an = new Set(JSON.parse(localStorage.getItem(HIDE_KEY) || "[]").map(String)); } catch (e) { state.an = new Set(); }
  }
  function saveAn() {
    // Newest 300 are plenty: the feed itself only carries the last few dozen.
    try { localStorage.setItem(HIDE_KEY, JSON.stringify(Array.from(state.an).slice(-300))); } catch (e) {}
  }
  // The X on a card. A real <button> inside the card, so the card's own click handler must skip it.
  function nutX() {
    return '<button type="button" class="noti-x" data-noti-x aria-label="' + esc(window.t("noti.dismiss")) +
      '" title="' + esc(window.t("noti.dismiss")) + '">' + (icon("x") || "&times;") + "</button>";
  }
  // The link under the list: "Show N read notices", or "Hide read notices" while they show.
  function linkDaDoc(nDaDoc) {
    if (state.xemDaDoc) return '<button class="noti-text-btn noti-read-toggle" type="button" data-noti-xemdadoc>' +
      esc(window.t("noti.hide_read")) + "</button>";
    return nDaDoc ? '<button class="noti-text-btn noti-read-toggle" type="button" data-noti-xemdadoc>' +
      esc(window.t("noti.show_read", { count: nDaDoc })) + "</button>" : "";
  }
  // Ngày giờ đi theo NGÔN NGỮ đang chọn, không viết cứng "vi-VN": người đọc bản tiếng Anh
  // mà thấy định dạng ngày kiểu Việt là lạc quẻ. Cả dashboard lấy locale từ đúng chỗ này.
  function LOC() { return (window.JavisI18n && JavisI18n.locale()) || "vi-VN"; }

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
  function saveRead(moi) {
    try { localStorage.setItem(READ_KEY, JSON.stringify(Array.from(state.read).slice(-300))); } catch (e) {}
    // 0.187.0: the server keeps this account's read set, so every device agrees.
    if (moi && moi.length) guiDaDoc({ ids: moi });
  }
  function guiDaDoc(body) {
    try {
      return fetch("/notifications/read", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) }).then(function (r) { return r.json(); }).catch(function () {});
    } catch (e) { return Promise.resolve(); }
  }
  // Read set from the server, merged with this browser's old local one (pushed up once).
  var daDocTuServer = null;
  function taiDaDoc() {
    if (daDocTuServer) return daDocTuServer;
    daDocTuServer = fetch("/notifications/read", { cache: "no-store" }).then(function (r) { return r.json(); })
      .then(function (d) {
        var sv = new Set(((d && d.read) || []).map(String));
        var chiMayNay = Array.from(state.read).filter(function (x) { return !sv.has(x); });
        sv.forEach(function (x) { state.read.add(x); });
        state.serverInit = !!(d && d.initialized);
        if (chiMayNay.length || (!state.serverInit && localStorage.getItem(INIT_KEY) === "1")) {
          state.serverInit = true;
          guiDaDoc({ ids: chiMayNay, initialized: true });
        }
      }).catch(function () {});
    return daDocTuServer;
  }
  function firstRun(items) {
    try {
      if (state.serverInit || localStorage.getItem(INIT_KEY) === "1") return;
      // Không biến toàn bộ lịch sử phiên bản thành hàng trăm tin chưa đọc ở lần mở đầu.
      // Chỉ giữ unread cho bản đang dùng/bản mới và thông báo cộng đồng ưu tiên cao.
      items.forEach(function (item) {
        var important = item.priority === "high" &&
          (item.kind !== "update" || item.is_current || item.update_available);
        if (!important) state.read.add(String(item.id));
      });
      localStorage.setItem(INIT_KEY, "1");
      state.serverInit = true;
      saveRead();
      guiDaDoc({ ids: Array.from(state.read), initialized: true });
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
    var moi = !state.read.has(String(id));
    state.read.add(String(id));
    saveRead(moi ? [String(id)] : null);
    render();
  }
  // 0.204.0: "Read all" reads BOTH tabs. It used to read only the open one, so the bell kept a count after pressing it.
  function markAll() {
    state.xemDaDoc = false;
    // Thư riêng: đã-đọc nằm ở SERVER, nên đánh dấu ở đây phải đi qua API chứ không
    // chỉ tô lại màu trên máy này.
    if (state.thuChuaDoc || state.thu.some(function (t) { return !t.read; })) {
      state.thu.forEach(function (t) { t.read = true; });
      state.thuChuaDoc = 0;
      docThu({ all: true }).then(render);
    }
    if (unreadItems().length) {
      state.items.forEach(function (item) { state.read.add(String(item.id)); });
      saveRead();
      guiDaDoc({ all: true });
    }
    render();
  }
  function kindLabel(kind) {
    if (kind === "marketing") return window.t("noti.kind_marketing");
    if (kind === "community") return window.t("noti.kind_community");
    if (kind === "security") return window.t("noti.kind_security");
    return window.t("noti.kind_update");
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
    if (cach < 60) return window.t("noti.ago_now");
    if (cach < 3600) return window.t("noti.ago_min", { count: Math.floor(cach / 60) });
    if (cach < 86400) return window.t("noti.ago_hour", { count: Math.floor(cach / 3600) });
    return d.toLocaleDateString(LOC(), { day: "2-digit", month: "2-digit" }) + " " +
           d.toLocaleTimeString(LOC(), { hour: "2-digit", minute: "2-digit" });
  }
  function nhanLoai(kind) {
    if (kind === "report") return window.t("noti.card_report");
    if (kind === "system") return window.t("noti.card_system");
    return window.t("noti.card_answer");
  }
  async function docThu(body) {
    try {
      var r = await fetch("/inbox/read", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      var d = await r.json();
      if (typeof d.unread === "number") state.thuChuaDoc = d.unread;
    } catch (e) {}
  }
  // Kênh của hội thoại đích, dạng "agent:<slug>" / "workflow:<slug>" (server ghi vào mẩu thư).
  // Thư CŨ không có trường này nên trả null và mọi thứ chạy y như trước.
  function congSuCuaThu(item) {
    var m = /^(agent|workflow):(.+)$/.exec(String((item && item.channel) || ""));
    return m ? { loai: m[1], slug: m[2] } : null;
  }
  // Bấm một mẩu thư = quay về ĐÚNG hội thoại đã hỏi. Mở hội thoại MỚI ở đây là sai: toàn bộ
  // ngữ cảnh nằm trong hội thoại cũ, hỏi tiếp ở chỗ khác là phải kể lại từ đầu.
  // 0.188.0 (Javis Core spec 9): an item of another brain switches the dashboard to that brain FIRST (only on this
  // click, never when a report arrives), so the chat opens in the right brain and what you type goes there.
  // Returns true when it switched (the caller then waits for the pages to redraw on the new brain).
  function chuyenBrainNeuCan(item) {
    var gs = (typeof document !== "undefined" && document.getElementById) ? document.getElementById("graphSource") : null;
    var v = item && item.brain_ui;
    if (!gs || !v || gs.value === v) return false;
    if (!Array.prototype.some.call(gs.options || [], function (o) { return o.value === v; })) return false;
    gs.value = v;
    gs.dispatchEvent(new Event("change"));
    return true;
  }
  function moThu(item) {
    item.read = true;
    docThu({ id: item.id }).then(render);
    // 0.191.0 (owner, 16/10/2026): a notice with no chat of its own opens in Javis Core (copied there with its source
    // and time, once); a notice that answers a chat opens that chat. No separate "Ask Javis Core" button.
    // 0.335.0: "Store has updates" opens the Javis Store, whose banner lists what can be updated.
    if (item.channel === "store:updates" && (window.JavisPacks || window.JavisNapCham)) {
      closePanel();
      // packs.js nạp chậm (nap-cham.js, 0.417.0).
      var moStore = function () { if (window.JavisPacks && window.JavisPacks.moKho) window.JavisPacks.moKho(""); };
      if (window.JavisNapCham) window.JavisNapCham.goi("packs", moStore); else moStore();
      return;
    }
    if (!item.session_id) { closePanel(); hoiCore("inbox", item.id); return; }
    closePanel();
    if (chuyenBrainNeuCan(item)) { setTimeout(function () { moThuTiep(item); }, 450); return; }
    moThuTiep(item);
  }
  function moThuTiep(item) {
    // Hội thoại của một TRỢ LÝ / QUY TRÌNH phải mở ở trang Cộng sự, không đổ vào khung chat
    // của bộ não chính. Đổ nhầm thì hai chuyện xảy ra cùng lúc: người dùng nhìn một đoạn chat
    // với trợ lý trên màn Javis mà không hiểu vì sao, và phiên đang mở trở thành phiên của
    // trợ lý - tin gõ tiếp bay thẳng vào đó (đúng lỗi bản 0.59.15 đã chữa cho đường rời
    // trang, hòm thư mở lại nó bằng một cửa khác).
    // Thư về một NHÓM chat (kênh "team:<id>", vd. việc nhóm bị chặn) mở đúng nhóm ở trang Nhóm, nơi có nút giải quyết.
    // Đổ vào khung chat chính thì tin gõ tiếp thành tin không tác giả trong phiên nhóm.
    var mNhom = /^team:(.+)$/.exec(String(item.channel || ""));
    // teams.js nạp chậm từ 0.417.0 (nap-cham.js): chưa có thì nạp rồi mở, đừng rơi sang mở nhầm khung chat chính.
    if (mNhom && !window.JavisTeams && window.JavisNapCham) {
      var nhomCho = mNhom[1];
      window.JavisNapCham.goi(["congviec", "teams"], function () {
        if (window.JavisTeams && window.JavisTeams.open) window.JavisTeams.open(nhomCho);
      });
      return;
    }
    if (mNhom && window.JavisTeams && window.JavisTeams.open) {
      var nhom = mNhom[1];
      try { window.JavisTeams.open(nhom); return; } catch (e) {}
    }
    var cs = congSuCuaThu(item);
    if (cs && window.JavisWorkspace && window.JavisWorkspace.openCommand) {
      try {
        window.JavisWorkspace.openCommand(cs.loai, cs.slug, item.session_id);
        return;
      } catch (e) {}
    }
    try {
      if (window.Alpine && Alpine.store("nav") && Alpine.store("nav").active !== "home"
          && Alpine.store("nav").active !== "chat") Alpine.store("nav").go("home");
    } catch (e) {}
    try { if (window.JavisSessions) window.JavisSessions.open(item.session_id); } catch (e) {}
  }
  // Javis Core (0.187.0, spec 7.3): the notice goes into this person's own Javis Core chat, with its source and time,
  // and the chat opens there. The shared notice itself never changes.
  async function hoiCore(src, id) {
    var brain = "brain";
    try { if (window.JavisSessions && window.JavisSessions.brain) brain = window.JavisSessions.brain() || "brain"; } catch (e) {}
    try {
      var r = await (await fetch("/javis-core/cite", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: src, id: id, brain: brain }) })).json();
      if (!r || !r.id) return;
      closePanel();
      if (window.JavisWorkspace && window.JavisWorkspace.openCommand) window.JavisWorkspace.openCommand("agent", "javis-core", r.id);
    } catch (e) {}
  }
  function phanHoiHtml(item) {
    var re = item.reaction || {};
    return '<div class="noti-react" role="group" aria-label="' + esc(window.t("noti.react")) + '">' +
      '<button type="button" class="noti-axis' + (re.axis === "needed" ? " on" : "") + '" aria-pressed="' + (re.axis === "needed") +
        '" data-react-a="needed">' + icon("bell") + esc(window.t("noti.needed")) + "</button>" +
      '<button type="button" class="noti-axis no' + (re.axis === "not_needed" ? " on" : "") + '" aria-pressed="' + (re.axis === "not_needed") +
        '" data-react-a="not_needed">' + icon("bell-off") + esc(window.t("noti.not_needed")) + "</button>" +
      (state.note[item.id] ? '<p class="noti-react-note">' + esc(state.note[item.id]) + "</p>" : "") + "</div>";
  }
  async function guiPhanHoi(item, axis) {
    var re = item.reaction || {};
    var body = { id: item.id, value: "", axis: axis };
    if (re.axis === axis) body.axis = "";   // pressing the lit button again takes it back
    try {
      var r = await (await fetch("/inbox/react", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) })).json();
      if (!r || !r.ok) { state.note[item.id] = (r && r.error) || window.t("noti.react_err"); render(); return; }
      item.reaction = r.reaction || null;
      state.note[item.id] = [window.t("noti.react_saved")].concat(r.messages || []).join(" ");
      state.policy = null;
      // 0.408.0 (owner: "I pressed Not needed and it still shows"): Not needed also reads this notice, so it leaves
      // the list at once. Its card is gone, so what Javis Core learned shows above the list instead.
      if (body.axis === "not_needed") {
        state.flash = state.note[item.id];
        delete state.note[item.id];
        if (!item.read) {
          item.read = true;
          state.thuChuaDoc = Math.max(0, state.thuChuaDoc - 1);
          docThu({ id: item.id }).then(render);
        }
      }
      render();
    } catch (e) { state.note[item.id] = window.t("noti.react_err"); render(); }
  }
  function theThu(item) {
    var chua = !item.read ? " unread" : "";
    var why = item.filtered ? (item.why === "repeat" ? "noti.why_repeat" : item.why === "muted" ? "noti.why_muted" : "noti.why_mode") : "";
    // Where a press takes you: the chat it answers, or Javis Core for a notice with no chat of its own (0.191.0).
    var phu = window.t(item.channel === "store:updates" ? "noti.open_store"
      : !item.session_id || item.channel === "agent:javis-core" ? "noti.open_core" : "noti.reopen_chat");
    return '<article class="noti-card' + chua + '" tabindex="0" role="button" data-thu-id="' + esc(item.id) + '">' +
      '<div class="noti-card-top"><span class="noti-kind ' + esc(item.kind || "answer") + '">' +
      esc(nhanLoai(item.kind)) + '</span><span class="noti-top-r"><span class="noti-time">' + esc(thoiGian(item.ts)) +
      "</span>" + nutX() + "</span></div>" +
      "<h4>" + esc(item.title || window.t("noti.msg_title")) + "</h4>" +
      '<p class="noti-card-body">' + esc(item.body || "") + "</p>" +
      (why ? '<span class="noti-why">' + esc(window.t(why)) + "</span>" : "") +
      (phu ? '<span class="noti-cta">' + phu + "</span>" : "") + phanHoiHtml(item) + "</article>";
  }
  function dauMuc(key) {
    return '<div class="noti-sub-head"><button type="button" class="noti-text-btn" data-noti-back>' + icon("chevron-left") +
      esc(window.t("noti.back")) + "</button><b>" + esc(window.t(key)) + "</b></div>";
  }
  function veHomThu(list) {
    if (state.view === "filter") { veBoLoc(list); return; }
    var loc = state.view === "filtered";
    var cungLoai = state.thu.filter(function (x) { return !!x.filtered === loc; });
    var ds = cungLoai.filter(function (x) { return state.xemDaDoc || !x.read; });
    var docRoi = linkDaDoc(cungLoai.filter(function (x) { return x.read; }).length);
    var nLoc = state.thu.filter(function (x) { return x.filtered && !x.read; }).length;
    var linkLoc = !loc && nLoc ? '<button class="noti-load-more" type="button" data-noti-filtered>' +
      esc(window.t("noti.filtered_n", { count: nLoc })) + "</button>" : "";
    var head = (loc ? dauMuc("noti.filtered_title") : "") +
      (state.flash ? '<p class="noti-flash" role="status">' + esc(state.flash) + "</p>" : "");
    if (!ds.length) {
      // Everything read is not "no messages yet": say the list is clear, and keep the way back to the read ones.
      var trong = cungLoai.length ? esc(window.t("noti.all_clear")) : loc ? esc(window.t("noti.filtered_empty")) :
        esc(window.t("noti.inbox_empty")) + "<br>" + esc(window.t("noti.inbox_empty_sub"));
      list.innerHTML = head + '<div class="noti-empty">' + trong + "</div>" + linkLoc + docRoi;
    } else {
      list.innerHTML = head + ds.slice(0, MAX_ITEMS).map(theThu).join("") + linkLoc + docRoi;
    }
    noiDanhSach(list);
  }
  function noiDanhSach(list) {
    var back = list.querySelector("[data-noti-back]");
    if (back) back.addEventListener("click", function () { state.view = "list"; render(); });
    var mo = list.querySelector("[data-noti-filtered]");
    if (mo) mo.addEventListener("click", function () { state.view = "filtered"; render(); });
    noiXemDaDoc(list);
    list.querySelectorAll("[data-thu-id]").forEach(function (card) {
      function thu() { return state.thu.find(function (x) { return String(x.id) === card.dataset.thuId; }); }
      card.addEventListener("click", function (e) {
        var t = e.target;
        if (t.closest("[data-noti-x]")) { e.stopPropagation(); var x = thu(); if (x) xoaThu(x); return; }
        if (t.closest(".noti-react")) {
          e.stopPropagation();
          var it = thu();
          if (!it) return;
          var a = t.closest("[data-react-a]");
          if (a) guiPhanHoi(it, a.dataset.reactA);
          return;
        }
        var it2 = thu();
        if (it2) moThu(it2);
      });
      card.addEventListener("keydown", function (e) {
        if (e.target !== card) return;
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); var it = thu(); if (it) moThu(it); }
      });
    });
  }
  function noiXemDaDoc(list) {
    var b = list.querySelector("[data-noti-xemdadoc]");
    if (b) b.addEventListener("click", function () { state.xemDaDoc = !state.xemDaDoc; render(); });
  }
  // X on an inbox card: gone from the queue for good (`/inbox/delete`), on every device. It leaves the list at once;
  // a failed delete brings it back on the next load.
  async function xoaThu(item) {
    state.thu = state.thu.filter(function (x) { return x !== item; });
    if (!item.read) state.thuChuaDoc = Math.max(0, state.thuChuaDoc - 1);
    render();
    try {
      var d = await (await fetch("/inbox/delete", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: item.id }) })).json();
      if (d && typeof d.unread === "number") { state.thuChuaDoc = d.unread; render(); }
    } catch (e) { taiThu(); }
  }
  // X on a news card: read, and hidden on this device for good.
  function anTin(id) {
    id = String(id);
    var moi = !state.read.has(id);
    state.read.add(id);
    state.an.add(id);
    saveAn();
    saveRead(moi ? [id] : null);
    render();
  }
  // The "Filter" view: each group's mode, the per-kind rules, Javis Core's recent changes (each can be undone).
  async function taiBoLoc() {
    try { state.policy = await (await fetch("/notify/policy", { cache: "no-store" })).json(); } catch (e) { state.policy = { ok: false }; }
    render();
  }
  async function guiBoLoc(url, body) {
    try {
      var r = await (await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();
      if (r && r.ok) state.policy = r;
    } catch (e) {}
    render();
  }
  function veBoLoc(list) {
    var p = state.policy;
    var head = dauMuc("noti.filter_title");
    var info = window.JavisInfo ? window.JavisInfo.pair(esc(window.t("noti.filter_info")), window.t("noti.filter_info_l")) : "";
    if (!p) { list.innerHTML = head + '<div class="noti-loading">' + esc(window.t("noti.loading")) + "</div>"; taiBoLoc(); noiDanhSach(list); return; }
    if (!p.ok) { list.innerHTML = head + '<div class="noti-empty">' + esc(window.t("noti.load_fail")) + "</div>"; noiDanhSach(list); return; }
    var byG = {};
    (p.groups || []).forEach(function (g) { byG[g.group] = g; });
    var rows = GROUPS.filter(function (g) { return byG[g]; }).map(function (g) {
      var cur = byG[g];
      return '<label class="noti-fg"><span class="noti-fg-n">' + esc(window.t(GROUP_KEY[g])) +
        (cur.set_by === "core" ? '<small>' + esc(window.t("noti.by_core")) + "</small>" : "") + "</span>" +
        '<select data-grp="' + g + '">' + MODES.map(function (m) {
          return '<option value="' + m + '"' + (cur.mode === m ? " selected" : "") + ">" + esc(window.t(MODE_KEY[m])) + "</option>";
        }).join("") + "</select></label>";
    }).join("");
    var rules = (p.rules || []).map(function (r) {
      return '<li><span>' + esc(r.label || r.sig) + ' <small>' + esc(window.t(r.rule === "mute" ? "noti.rule_mute" : "noti.rule_always")) +
        "</small></span>" + '<button type="button" class="noti-text-btn" data-rule="' + esc(r.key) + '">' + esc(window.t("noti.rule_remove")) + "</button></li>";
    }).join("");
    var changes = (p.changes || []).slice(0, 10).map(function (c) {
      return '<li><span>' + esc(c.text || "") + "</span>" + (c.undone ? '<small>' + esc(window.t("noti.undone")) + "</small>"
        : '<button type="button" class="noti-text-btn" data-undo="' + esc(c.id) + '">' + esc(window.t("noti.undo")) + "</button>") + "</li>";
    }).join("");
    list.innerHTML = head + '<div class="noti-filter">' + info + rows +
      "<h5>" + esc(window.t("noti.rules_title")) + "</h5>" + (rules ? '<ul class="noti-fl">' + rules + "</ul>" : '<p class="noti-fl-empty">' + esc(window.t("noti.none")) + "</p>") +
      "<h5>" + esc(window.t("noti.changes_title")) + "</h5>" + (changes ? '<ul class="noti-fl">' + changes + "</ul>" : '<p class="noti-fl-empty">' + esc(window.t("noti.none")) + "</p>") +
      "</div>";
    noiDanhSach(list);
    list.querySelectorAll("select[data-grp]").forEach(function (sel) {
      sel.addEventListener("change", function () { guiBoLoc("/notify/policy/group", { group: sel.dataset.grp, mode: sel.value }); });
    });
    list.querySelectorAll("[data-rule]").forEach(function (b) {
      b.addEventListener("click", function () { guiBoLoc("/notify/policy/rule", { key: b.dataset.rule, rule: "" }); });
    });
    list.querySelectorAll("[data-undo]").forEach(function (b) {
      b.addEventListener("click", function () { guiBoLoc("/notify/policy/undo", { id: b.dataset.undo }); });
    });
  }
  function chonTab(tab) {
    state.view = tab === "filter" ? "filter" : "list";
    if (tab === "filter") state.policy = null;
    state.tab = tab === "news" ? "news" : "mine";
    state.xemDaDoc = false;
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
      ? window.t("noti.unread_n", { count: tong })
      : window.t("noti.all_read");
    // 0.204.0: "Read all" is a real button, lit while something is unread and dimmed (disabled) once nothing is.
    var readAll = byId("notificationReadAll");
    if (readAll) { readAll.disabled = tong === 0; readAll.classList.toggle("has-unread", tong > 0); }

    var tabMine = byId("notiTabMine"), tabNews = byId("notiTabNews");
    if (tabMine && tabNews) {
      tabMine.classList.toggle("active", state.tab === "mine" && state.view !== "filter");
      var tabF = byId("notiTabFilter");
      if (tabF) tabF.classList.toggle("active", state.tab === "mine" && state.view === "filter");
      tabNews.classList.toggle("active", state.tab === "news");
      tabMine.setAttribute("aria-selected", state.tab === "mine" ? "true" : "false");
      tabNews.setAttribute("aria-selected", state.tab === "news" ? "true" : "false");
      var cM = byId("notiTabMineCount"), cN = byId("notiTabNewsCount");
      if (cM) { cM.hidden = !state.thuChuaDoc; cM.textContent = String(state.thuChuaDoc); }
      if (cN) { cN.hidden = !unread.length; cN.textContent = String(unread.length); }
    }
    if (state.tab === "mine") { veHomThu(list); return; }

    var conLai = state.items.filter(function (item) { return !state.an.has(String(item.id)); });
    if (!conLai.length) {
      list.innerHTML = '<div class="noti-empty">' + esc(window.t("noti.news_empty")) + "<br>" +
        esc(window.t("noti.news_empty_sub")) + "</div>";
      return;
    }
    var docRoi = linkDaDoc(conLai.filter(function (item) { return !chuaDoc(item); }).length);
    var limited = conLai.filter(function (item) { return state.xemDaDoc || chuaDoc(item); }).slice(0, MAX_ITEMS);
    if (!limited.length) {
      list.innerHTML = '<div class="noti-empty">' + esc(window.t("noti.all_clear")) + "</div>" + docRoi;
      noiXemDaDoc(list);
      return;
    }
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
      var ctaLabel = (item.cta && item.cta.label) || (kind === "update" ? window.t("noti.cta_update") : "");
      var cta = ctaLabel ? '<span class="noti-cta">' + esc(ctaLabel) + "</span>" : "";
      return '<article class="noti-card' + unreadClass + '" tabindex="0" role="button" data-noti-id="' + esc(id) + '">' +
        '<div class="noti-card-top"><span class="noti-kind ' + esc(kind) + '">' + esc(kindLabel(kind)) + '</span>' +
        '<span class="noti-top-r"><span class="noti-time">' + esc(item.published_at || "") + "</span>" + nutX() + "</span></div>" +
        "<h4>" + esc(item.title || window.t("noti.card_untitled")) + "</h4>" +
        '<p class="noti-card-summary">' + esc(item.summary || "") + "</p>" + body + cta + "</article>";
    }).join("");
    var remaining = limited.length - visible.length;
    var loadMore = remaining > 0
      ? '<button class="noti-load-more" id="notificationLoadMore" type="button">' +
        esc(window.t("noti.load_more", { count: Math.min(PAGE_SIZE, remaining) })) + "</button>"
      : "";
    list.innerHTML = cards + loadMore + docRoi;
    noiXemDaDoc(list);
    list.querySelectorAll("[data-noti-id]").forEach(function (card) {
      function activate() {
        var item = state.items.find(function (x) { return String(x.id) === card.dataset.notiId; });
        if (item) openItem(item);
      }
      card.addEventListener("click", function (e) {
        if (e.target && e.target.closest && e.target.closest("[data-noti-x]")) {
          e.stopPropagation(); anTin(card.dataset.notiId); return;
        }
        activate();
      });
      card.addEventListener("keydown", function (event) {
        if (event.target !== card) return;   // Enter on the X is the X's own click, not "open"
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
    if (!state.items.length && list && state.tab === "news") list.innerHTML = '<div class="noti-loading">' + esc(window.t("noti.loading")) + "</div>";
    try {
      var response = await fetch("/notifications", { cache: "no-store" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      var data = await response.json();
      state.items = Array.isArray(data.items) ? data.items : [];
      state.visibleCount = PAGE_SIZE;
      state.loadedAt = Date.now();
      await taiDaDoc();
      firstRun(state.items);
      render();
    } catch (e) {
      if (list && state.tab === "news") list.innerHTML = '<div class="noti-empty">' +
        esc(window.t("noti.load_fail")) + "<br>" + esc(window.t("noti.load_fail_sub")) + "</div>";
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
    state.flash = "";
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
    // 0.187.0: privacy of the push preview (the setting is per account, on the server).
    var anRow = byId("notificationPushHideRow"), an = byId("notificationPushHide");
    if (anRow && an) {
      anRow.hidden = !on;
      if (!an.dataset.wired) {
        an.dataset.wired = "1";
        try { var st = await (await fetch("/settings", { cache: "no-store" })).json(); an.checked = !!(st.push && st.push.preview === "hidden"); } catch (e) {}
        an.addEventListener("change", function () {
          var f = new FormData(); f.append("section", "push"); f.append("data", JSON.stringify({ preview: an.checked ? "hidden" : "full" }));
          fetch("/settings", { method: "POST", body: f }).catch(function () {});
        });
      }
    }
    nut.textContent = on ? window.t("noti.push_off") : window.t("noti.push_on");
    nut.classList.toggle("primary", !on);
    if (thu) thu.hidden = !on;
    if (ghi) ghi.textContent = loi || (on
      ? window.t("noti.push_on_here")
      : window.t("noti.push_note"));
    if (ghi) ghi.classList.toggle("loi", !!loi);
    if (loi || !on) return;
    // Bật/tắt là việc của TỪNG máy, nên "đang bật ở đây" chưa trả lời được "máy kia có nhận
    // không". Nói luôn số thiết bị máy chủ đang đẩy tới, và nêu đích danh máy nào đang hỏng.
    var tb = await JavisPush.thietBi();
    if (!ghi || !tb.length) return;
    var hong = tb.filter(function (x) { return x.lan_cuoi && !x.ok_lan_cuoi; });
    if (hong.length) {
      ghi.textContent = window.t("noti.push_dev_err", { count: tb.length, dv: hong[0].dich_vu,
        loi: String(hong[0].loi_lan_cuoi || "").slice(0, 80) });
      ghi.classList.add("loi");
    } else {
      ghi.textContent = window.t("noti.push_dev_ok", { count: tb.length });
      ghi.classList.remove("loi");
    }
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
      await veNutPush(r.ok ? "" : (r.error || window.t("noti.push_err")));
    });
    if (thu) thu.addEventListener("click", async function () {
      thu.disabled = true;
      var r = await JavisPush.thu();
      thu.disabled = false;
      if (!ghi) return;
      // Nói rõ ĐỦ MẤY MÁY nhận được, chứ không phải "đã gửi" chung chung: gửi thử trên điện
      // thoại mà chỉ máy tính kêu thì câu "đã gửi" là một câu đúng-nhưng-vô-dụng.
      ghi.textContent = r.ok
        ? window.t("noti.push_test_ok", { count: r.so || 1 })
        : (r.error || window.t("noti.push_test_err"));
      ghi.classList.toggle("loi", !r.ok);
    });
  }

  function init() {
    var trigger = byId("notificationTrigger");
    if (!trigger) return;
    loadRead();
    loadAn();
    taiDaDoc().then(render);
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
    var tf = byId("notiTabFilter");
    if (tf) tf.addEventListener("click", function () { chonTab("filter"); });
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

  // Từ điển về BẤT ĐỒNG BỘ (i18n/index.js fetch xong mới bắn "javis:i18n"). Hòm thư có thể
  // đã vẽ xong trước lúc đó và in ra mã khoá; đổi ngôn ngữ giữa chừng cũng không ăn nếu
  // không nghe. Vẽ lại thẻ, và vẽ lại cả ô thông báo đẩy khi ô đó đang hiện.
  window.addEventListener("javis:i18n", function () {
    render();
    var hop = byId("notificationPush");
    if (hop && !hop.hidden) veNutPush();
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
