/* Trang Hội thoại - MỘT trang cho hộp thư khách, kênh và nhân viên AI (Chatbot V2, 0.61.0).
 *
 * Ba tab, cùng một chỗ trên thanh bên:
 *   - Hộp thư:  mọi tin khách từ mọi kênh (`/conversations`), đọc lại, tiếp quản, và từ 0.61.0
 *               TRẢ LỜI KHÁCH NGAY TỪ ĐÂY khi kênh có năng lực đó (`/conversations/{id}/reply`).
 *   - Kênh:     mọi tài khoản kênh, MỘT khuôn thẻ bất kể kênh (`/channels/accounts`): bot
 *               Telegram, bot Zalo, Zalo cá nhân, và kênh thêm sau này. Không kênh nào có mục riêng.
 *   - Chatbot:  nhân viên AI (chatbots.js dựng, chạy trong tab này).
 *
 * Luật sống còn của file này: KHÔNG đoán gì theo id kênh. Logo, nhãn, năng lực đều do server
 * trả trong danh sách kênh (`channels`); thêm kênh ở server là trang này vẽ được ngay.
 *
 * Trang này KHÔNG phải cái chuông (notifications.js / JavisInbox): chuông là hòm thư của CHỦ
 * (kết quả việc nền), còn đây là hội thoại giữa KHÁCH và cửa hàng. Tiền tố riêng: .ht-*, ht.*,
 * window.JavisConversations. Ghi chú: KHÔNG dùng ký tự em dash. */
(function () {
  "use strict";

  var NHIP = 5000;          // nhịp tự làm mới, như trang Chatbot
  var TRANG = 60;           // số hội thoại một trang
  var TABS = ["inbox", "kenh", "chatbot"];
  var _host = null, _timer = null, _tab = "inbox";
  var _items = [], _stats = {}, _dauVet = "";
  var _kenhLoc = "", _botLoc = "", _tkLoc = "", _q = "";
  var _chon = null;         // id hội thoại đang mở
  var _msgs = [], _conv = null, _dauVetTin = "";
  var _kenhDS = [];         // các LOẠI kênh (server: id, nhan, logo, kind, nang_luc...)
  var _tk = [];             // mọi tài khoản kênh, một khuôn
  var _dauVetTK = "";
  var _cho = null;          // bộ lọc / tab chờ áp khi trang mở từ nơi khác (nút trên thẻ bot)
  var _dangGui = false;

  var ic = function (n) { return window.ic ? window.ic(n) : ""; };
  var LOC = function () { return (window.JavisI18n && JavisI18n.locale()) || "vi-VN"; };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function el(html) { var d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstChild; }
  async function api(url, opts) {
    var r = await fetch(url, opts || {});
    var d = null;
    try { d = await r.json(); } catch (e) { d = {}; }
    if (!r.ok || d.ok === false) throw new Error((d && d.error) || window.t("cb.loi_ma", { ma: r.status }));
    return d;
  }
  function fd(obj) {
    var f = new FormData();
    Object.keys(obj || {}).forEach(function (k) { if (obj[k] != null) f.append(k, obj[k]); });
    return f;
  }
  function gio(ts) {
    if (!ts) return "";
    try {
      var d = new Date(ts * 1000), nay = new Date();
      var cungNgay = d.toDateString() === nay.toDateString();
      return cungNgay ? d.toLocaleTimeString(LOC(), { hour: "2-digit", minute: "2-digit" })
                      : d.toLocaleString(LOC(), { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    } catch (e) { return ""; }
  }

  // ---------------------------------------------------------------- kênh: chỉ đọc từ server
  function kenhCua(id) {
    for (var i = 0; i < _kenhDS.length; i++) if (_kenhDS[i].id === id) return _kenhDS[i];
    return { id: id || "", nhan: id || "", logo: "", kind: "", nang_luc: {} };
  }
  function nhanKenh(id) { return kenhCua(id).nhan || id || ""; }
  function logoKenh(id, size) {
    var k = kenhCua(id);
    return (window.Icons && Icons.kenh && k.logo) ? Icons.kenh(k.logo, { size: size || "13px" }) : "";
  }
  function chipKenh(id) {
    return '<span class="ht-chip">' + logoKenh(id) + " " + esc(nhanKenh(id)) + "</span>";
  }
  function nangLuc(id, khoa) { return !!((kenhCua(id).nang_luc || {})[khoa]); }

  // ---------------------------------------------------------------- khung trang + tab
  function render(host) {
    _host = host;
    if (_cho && _cho.tab && TABS.indexOf(_cho.tab) >= 0) _tab = _cho.tab;
    host.innerHTML =
      '<div class="cview-section ht-page">' +
        '<div class="ht-tabs"></div>' +
        '<div class="ht-tab-body"></div>' +
      '</div>';
    veTabs();
    veTab();
    nhip();
  }

  function veTabs() {
    var b = _host && _host.querySelector(".ht-tabs");
    if (!b) return;
    var NHAN = { inbox: ["ht.tab_inbox", "messages-square"], kenh: ["ht.tab_kenh", "plug"], chatbot: ["ht.tab_chatbot", "headset"] };
    b.innerHTML = TABS.map(function (t) {
      var chuaDoc = (t === "inbox" && _stats.chua_doc) ? '<span class="ht-badge">' + _stats.chua_doc + '</span>' : "";
      return '<button type="button" class="ht-tab' + (t === _tab ? " on" : "") + '" data-t="' + t + '">' +
        ic(NHAN[t][1]) + ' <span>' + esc(window.t(NHAN[t][0])) + '</span>' + chuaDoc + '</button>';
    }).join("");
    b.querySelectorAll(".ht-tab").forEach(function (n) {
      n.onclick = function () { chonTab(n.dataset.t); };
    });
  }

  // `chiDatTruoc`: chỉ ghi nhớ tab để lần render tới mở đúng (console.js gọi lúc chuyển từ id
  // trang cũ "chatbots" sang trang này, trước khi trang được dựng).
  function chonTab(id, chiDatTruoc) {
    if (TABS.indexOf(id) < 0) return;
    _tab = id;
    if (chiDatTruoc && !(_host && document.body.contains(_host))) return;
    if (!_host) return;
    veTabs();
    veTab();
  }

  function veTab() {
    var body = _host && _host.querySelector(".ht-tab-body");
    if (!body) return;
    body.innerHTML = "";
    if (_tab === "kenh") return renderKenh(body);
    if (_tab === "chatbot") return renderChatbot(body);
    return renderInbox(body);
  }

  function nhip() {
    if (_timer) clearInterval(_timer);
    _timer = setInterval(function () {
      if (!_host || !document.body.contains(_host)) { clearInterval(_timer); _timer = null; return; }
      if (document.hidden || document.querySelector(".ht-modal")) return;
      if (_tab === "inbox") {
        tai(true);
        if (_chon) taiTin(true);
      } else if (_tab === "kenh") {
        taiTK(true);
      }
    }, NHIP);
  }

  // Tab Chatbot: chatbots.js dựng vào đúng ô này (nó tự có nhịp riêng, tự dừng khi ô bị tháo).
  function renderChatbot(body) {
    var fn = window.JavisChatbots && window.JavisChatbots.render;
    if (fn) { try { fn(body); } catch (e) { body.innerHTML = '<div class="ht-empty">' + esc(e.message) + '</div>'; } }
    else body.innerHTML = '<div class="ht-empty">' + esc(window.t("cs.mod_not_ready", { ten: "chatbots.js" })) + '</div>';
  }

  // ---------------------------------------------------------------- tài khoản kênh (dùng chung)
  async function taiTK(im) {
    try {
      var d = await api("/channels/accounts");
      _tk = d.accounts || [];
      if (d.channels) _kenhDS = d.channels;
      var vet = JSON.stringify(_tk);
      if (im && vet === _dauVetTK) return false;
      _dauVetTK = vet;
    } catch (e) {
      if (!im) throw e;
      return false;
    }
    if (_tab === "kenh") veKenh();
    if (_tab === "inbox") veChonBot();
    return true;
  }

  // ---------------------------------------------------------------- HỘP THƯ
  function renderInbox(body) {
    if (_cho) {
      _botLoc = _cho.bot_id || ""; _kenhLoc = _cho.channel || ""; _tkLoc = _cho.account_key || "";
      _cho = null;
    }
    body.innerHTML =
      '<div class="ht-wrap">' +
        '<div class="ht-stats"></div>' +
        '<div class="ht-bar">' +
          '<div class="ht-loc"></div>' +
          '<select class="ht-bot"><option value="">' + esc(window.t("ht.moi_bot")) + '</option></select>' +
          '<input class="ht-search" placeholder="' + esc(window.t("ht.tim_ph")) + '">' +
        '</div>' +
        '<div class="ht-body">' +
          '<div class="ht-list"><div class="ht-empty">' + esc(window.t("common.loading")) + '</div></div>' +
          '<div class="ht-thread"><div class="ht-empty ht-thread-empty">' + ic("messages-square") +
            '<div>' + esc(window.t("ht.chon_mot")) + '</div></div></div>' +
        '</div>' +
      '</div>';
    var s = body.querySelector(".ht-search");
    s.oninput = function () { _q = s.value.trim(); tai(); };
    body.querySelector(".ht-bot").onchange = function (e) { _botLoc = e.target.value; tai(); };
    taiTK(false).catch(function () {}).then(function () { tai(); if (_chon) taiTin(false); });
  }

  // Ô chọn bot: dựng từ danh sách tài khoản (tài khoản nào có bot trực). Chỉ hiện khi có từ
  // hai bot; một bot thì ô chọn là câu hỏi không ai hỏi.
  function veChonBot() {
    var sel = _host && _host.querySelector(".ht-bot");
    if (!sel) return;
    var bots = {};
    _tk.forEach(function (a) { if (a.bot_id && !bots[a.bot_id]) bots[a.bot_id] = a.bot_name || a.bot_id; });
    var ids = Object.keys(bots);
    var cu = sel.value;
    sel.innerHTML = '<option value="">' + esc(window.t("ht.moi_bot")) + '</option>' +
      ids.map(function (id) { return '<option value="' + esc(id) + '">' + esc(bots[id]) + '</option>'; }).join("");
    sel.value = _botLoc || cu || "";
    if (sel.value !== (_botLoc || "")) sel.value = "";
    sel.style.display = ids.length >= 2 ? "" : "none";
  }

  // `im` = nhịp tự động: không xoá danh sách đang hiện, mạng hỏng một nhịp thì giữ màn hình cũ.
  async function tai(im) {
    var box = _host && _host.querySelector(".ht-list");
    if (!box) return;
    var url = "/conversations?limit=" + TRANG +
      "&channel=" + encodeURIComponent(_kenhLoc) + "&bot_id=" + encodeURIComponent(_botLoc) +
      "&account_id=" + encodeURIComponent(_tkLoc) + "&q=" + encodeURIComponent(_q);
    try {
      var d = await api(url);
      _items = d.items || [];
      _stats = d.stats || {};
      if (d.channels) _kenhDS = d.channels;
      var vet = JSON.stringify([_items, _stats]);
      if (im && vet === _dauVet) return;
      _dauVet = vet;
    } catch (e) {
      if (!im) box.innerHTML = '<div class="ht-empty">' + esc(window.t("ht.loi_tai")) + ' ' + esc(e.message) + '</div>';
      return;
    }
    veStats();
    veLoc();
    veDanhSach();
    veTabs();
  }

  function veStats() {
    var b = _host.querySelector(".ht-stats");
    if (!b) return;
    var o = [
      ["ht.st_tong", _stats.tong || 0],
      ["ht.st_hom_nay", _stats.hom_nay || 0],
      ["ht.st_chua_doc", _stats.chua_doc || 0],
      ["ht.st_can_nguoi", _stats.can_nguoi || 0],
    ];
    b.innerHTML = o.map(function (x) {
      return '<div class="ht-stat' + (x[0] === "ht.st_can_nguoi" && x[1] ? " warn" : "") + '">' +
        '<b>' + x[1] + '</b><span>' + esc(window.t(x[0])) + '</span></div>';
    }).join("");
  }

  // Chip lọc kênh: chỉ hiện những kênh THẬT SỰ có hội thoại (cộng kênh đang lọc).
  function veLoc() {
    var b = _host.querySelector(".ht-loc");
    if (!b) return;
    var co = Object.keys((_stats.theo_kenh) || {});
    if (_kenhLoc && co.indexOf(_kenhLoc) < 0) co.push(_kenhLoc);
    var tkChip = _tkLoc ? (_tk.filter(function (a) { return a.account_key === _tkLoc; })[0] || null) : null;
    if (co.length < 2 && !_kenhLoc && !tkChip) { b.innerHTML = ""; return; }
    var chips = co.length >= 2 || _kenhLoc
      ? [{ id: "", nhan: window.t("ht.tat_ca") }].concat(co.map(function (k) { return { id: k, nhan: nhanKenh(k) }; }))
      : [];
    b.innerHTML = chips.map(function (c) {
      return '<button type="button" class="ht-loc-chip' + (c.id === _kenhLoc ? " on" : "") +
        '" data-k="' + esc(c.id) + '">' + (c.id ? logoKenh(c.id) + " " : "") + esc(c.nhan) + '</button>';
    }).join("") +
    // Đang lọc theo MỘT tài khoản (mở từ tab Kênh): một chip có nút bỏ.
    (tkChip ? '<button type="button" class="ht-loc-chip on ht-loc-tk">' + logoKenh(tkChip.channel) + ' ' +
              esc(tkChip.label) + ' ' + ic("x") + '</button>' : "");
    b.querySelectorAll(".ht-loc-chip[data-k]").forEach(function (x) {
      x.onclick = function () { _kenhLoc = x.dataset.k; tai(); };
    });
    var bo = b.querySelector(".ht-loc-tk");
    if (bo) bo.onclick = function () { _tkLoc = ""; tai(); };
  }

  function veDanhSach() {
    var box = _host.querySelector(".ht-list");
    if (!box) return;
    if (!_items.length) {
      var coNguon = _tk.some(function (a) { return a.ghi; });
      box.innerHTML = '<div class="ht-empty">' + ic("messages-square") +
        '<b>' + esc(_q || _kenhLoc || _botLoc || _tkLoc ? window.t("ht.khong_khop") : window.t("ht.chua_co")) + '</b>' +
        (!coNguon ? '<div>' + esc(window.t("ht.chua_co_goi_y")) + '</div>' +
          '<button class="s-btn ht-mo-kenh" type="button">' + ic("plug") + ' ' + esc(window.t("ht.tab_kenh")) + '</button>' : "") +
        '</div>';
      var nut = box.querySelector(".ht-mo-kenh");
      if (nut) nut.onclick = function () { chonTab("kenh"); };
      return;
    }
    box.innerHTML = _items.map(function (c) {
      var ten = c.title || c.customer_name || c.external_chat_id;
      var ai = c.last_sender_type === "ai" ? window.t("ht.bot") + ": "
             : c.last_sender_type === "human" ? window.t("ht.ban") + ": " : "";
      return '<button type="button" class="ht-item' + (c.id === _chon ? " on" : "") +
          (c.unread_count ? " unread" : "") + '" data-id="' + c.id + '">' +
        '<span class="ht-item-ic">' + (c.chat_type === "group" ? ic("users") : ic("user-round")) + '</span>' +
        '<span class="ht-item-text">' +
          '<span class="ht-item-top"><strong>' + esc(ten) + '</strong>' +
            '<small class="ht-item-time">' + esc(gio(c.last_message_at)) + '</small></span>' +
          '<span class="ht-item-sub">' + logoKenh(c.channel) +
            (c.mode === "human" ? '<span class="ht-mode">' + esc(window.t("ht.mode_human")) + '</span>' : "") +
            '<small>' + esc(ai + (c.last_message || "")) + '</small>' +
            (c.unread_count ? '<span class="ht-badge">' + c.unread_count + '</span>' : "") +
          '</span>' +
        '</span></button>';
    }).join("");
    box.querySelectorAll(".ht-item").forEach(function (x) {
      x.onclick = function () { mo(parseInt(x.dataset.id, 10)); };
    });
  }

  // ---------------------------------------------------------------- một hội thoại
  async function mo(id) {
    _chon = id;
    _dauVetTin = "";
    _host.querySelector(".ht-wrap").classList.add("thread-on");
    veDanhSach();
    await taiTin(false);
    try { await api("/conversations/" + id + "/read", { method: "POST" }); } catch (e) {}
    tai(true);
  }

  function dongThread() {
    _chon = null;
    var w = _host.querySelector(".ht-wrap");
    if (w) w.classList.remove("thread-on");
    var th = _host.querySelector(".ht-thread");
    if (th) th.innerHTML = '<div class="ht-empty ht-thread-empty">' +
      ic("messages-square") + '<div>' + esc(window.t("ht.chon_mot")) + '</div></div>';
    veDanhSach();
  }

  async function taiTin(im) {
    if (!_chon) return;
    var id = _chon;
    var box = _host.querySelector(".ht-thread");
    if (!box) return;
    try {
      var d = await api("/conversations/" + id + "/messages?limit=200");
      if (_chon !== id) return;
      var vet = JSON.stringify([d.conversation, d.messages]);
      if (im && vet === _dauVetTin) return;
      _dauVetTin = vet;
      _conv = d.conversation; _msgs = d.messages || [];
    } catch (e) {
      if (!im) box.innerHTML = '<div class="ht-empty">' + esc(window.t("ht.loi_tai")) + ' ' + esc(e.message) + '</div>';
      return;
    }
    veThread();
  }

  function veThread() {
    var box = _host.querySelector(".ht-thread");
    if (!box) return;
    var c = _conv || {};
    var ten = c.title || c.customer_name || c.external_chat_id;
    var human = c.mode === "human";
    var laBot = !!c.bot_id;
    var guiDuoc = nangLuc(c.channel, "tra_loi_tu_javis");
    var cuon = box.querySelector(".ht-msgs");
    var oDay = !cuon || (cuon.scrollHeight - cuon.scrollTop - cuon.clientHeight < 80);
    // Giữ chữ đang gõ dở khi nhịp tự làm mới vẽ lại khung.
    var oCu = box.querySelector(".ht-compose textarea");
    var nhapDo = oCu ? oCu.value : "";
    box.innerHTML =
      '<div class="ht-head">' +
        '<button type="button" class="s-btn-ghost ht-back">' + ic("arrow-left") + '</button>' +
        '<div class="ht-head-text"><strong>' + esc(ten) + '</strong>' +
          '<small>' + chipKenh(c.channel) + (c.account_name ? ' · ' + esc(c.account_name) : "") +
          (c.chat_type === "group" ? ' · ' + esc(window.t("ht.nhom")) : "") + '</small></div>' +
        (laBot
          ? '<button type="button" class="s-btn-ghost ht-mode-btn' + (human ? " on" : "") + '">' +
              (human ? ic("bot") + ' ' + esc(window.t("ht.tra_ai")) : ic("hand") + ' ' + esc(window.t("ht.tiep_quan"))) +
            '</button>'
          : "") +
      '</div>' +
      (human ? '<div class="ht-note warn">' + ic("hand") + ' ' + esc(window.t("ht.dang_tiep_quan")) + '</div>' : "") +
      '<div class="ht-msgs">' + _msgs.map(veTin).join("") + '</div>' +
      (guiDuoc ? veCompose(c, laBot, human) :
        '<div class="ht-foot">' + esc(window.t("ht.kenh_khong_gui", { kenh: nhanKenh(c.channel) })) + '</div>');
    box.querySelector(".ht-back").onclick = dongThread;
    var mb = box.querySelector(".ht-mode-btn");
    if (mb) mb.onclick = function () { doiMode(c.id, human ? "ai" : "human"); };
    var m = box.querySelector(".ht-msgs");
    if (oDay) m.scrollTop = m.scrollHeight;
    var ta = box.querySelector(".ht-compose textarea");
    if (ta) {
      ta.value = nhapDo;
      ta.onkeydown = function (e) {
        if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); gui(c); }
      };
      box.querySelector(".ht-send").onclick = function () { gui(c); };
    }
  }

  // Ô trả lời khách. Nói rõ hai điều trước khi bấm gửi: gửi từ đây là TIẾP QUẢN (bot đang
  // trực sẽ im ở cuộc này), và với kênh tài khoản cá nhân thì tin đi dưới tên chính bạn.
  function veCompose(c, laBot, human) {
    var k = kenhCua(c.channel);
    var ghiChu = "";
    if (laBot && !human) ghiChu = window.t("ht.gui_tiep_quan");
    else if (k.kind === "account") ghiChu = window.t("ht.gui_ten_ban", { kenh: k.nhan });
    return '<div class="ht-compose">' +
      (ghiChu ? '<div class="ht-compose-note">' + ic("info") + ' ' + esc(ghiChu) + '</div>' : "") +
      '<div class="ht-compose-row">' +
        '<textarea rows="2" placeholder="' + esc(window.t("ht.gui_ph")) + '"></textarea>' +
        '<button type="button" class="s-btn ht-send">' + ic("send") + ' ' + esc(window.t("ht.gui")) + '</button>' +
      '</div></div>';
  }

  async function gui(c) {
    var box = _host.querySelector(".ht-thread");
    var ta = box && box.querySelector(".ht-compose textarea");
    var nut = box && box.querySelector(".ht-send");
    if (!ta || _dangGui) return;
    var txt = ta.value.trim();
    if (!txt) return;
    _dangGui = true;
    ta.disabled = true; if (nut) nut.disabled = true;
    try {
      await api("/conversations/" + c.id + "/reply", { method: "POST", body: fd({ text: txt }) });
      ta.value = "";
    } catch (e) {
      alert(window.t("ht.loi_gui") + " " + e.message);
    }
    _dangGui = false;
    ta.disabled = false; if (nut) nut.disabled = false;
    _dauVetTin = "";
    await taiTin(false);
    tai(true);
    var ta2 = box && box.querySelector(".ht-compose textarea");
    if (ta2) ta2.focus();
  }

  function veTin(t) {
    var lop = t.sender_type === "customer" ? "khach" : t.sender_type === "ai" ? "bot"
            : t.sender_type === "human" ? "nguoi" : "hethong";
    var ai = t.sender_type === "customer" ? (t.sender_name || "")
           : t.sender_type === "ai" ? (t.sender_name || window.t("ht.bot"))
           : t.sender_type === "human" ? window.t("ht.ban") : "";
    var than;
    if (t.sender_type === "ai" && window.mdToHtml) {
      try { than = window.mdToHtml(t.text || "", ""); } catch (e) { than = esc(t.text || ""); }
    } else {
      than = esc(t.text || "");
    }
    var loai = t.message_type && t.message_type !== "text"
      ? '<span class="ht-loai">' + ic(t.message_type === "image" ? "image" : t.message_type === "audio" ? "mic" : "paperclip") +
        ' ' + esc(t.message_type) + '</span>' : "";
    var loi = t.metadata && t.metadata.loi
      ? '<div class="ht-msg-loi">' + ic("triangle-alert") + ' ' + esc(t.metadata.loi) + '</div>' : "";
    return '<div class="ht-msg ' + lop + '">' +
      '<div class="ht-msg-h">' + esc(ai) + (ai ? ' · ' : '') + esc(gio(t.created_at)) + '</div>' +
      '<div class="ht-bubble">' + loai + than + '</div>' + loi +
    '</div>';
  }

  async function doiMode(id, mode) {
    try {
      await api("/conversations/" + id + "/mode", { method: "POST", body: fd({ mode: mode }) });
    } catch (e) { alert(window.t("ht.loi_mode") + " " + e.message); return; }
    _dauVetTin = "";
    taiTin(false);
    tai(true);
  }

  // ---------------------------------------------------------------- KÊNH
  function renderKenh(body) {
    body.innerHTML =
      '<div class="ht-kenh">' +
        '<div class="ht-bar">' +
          '<p class="ht-intro ht-kenh-intro">' + esc(window.t("ht.kenh_intro2")) + '</p>' +
          '<button class="s-btn ht-them-tk" type="button">' + ic("plus") + ' ' + esc(window.t("ht.them_tk")) + '</button>' +
        '</div>' +
        '<div class="ht-acc-grid"><div class="ht-empty">' + esc(window.t("common.loading")) + '</div></div>' +
      '</div>';
    body.querySelector(".ht-them-tk").onclick = function () { moThemTK(); };
    _dauVetTK = "";
    taiTK(false).catch(function (e) {
      var g = body.querySelector(".ht-acc-grid");
      if (g) g.innerHTML = '<div class="ht-empty">' + esc(window.t("ht.loi_tai")) + ' ' + esc(e.message) + '</div>';
    });
  }

  var TT_TK = {
    running: ["ht.tk_dang_chay", "ok"], starting: ["ht.tk_khoi_dong", "wait"],
    error: ["ht.tk_loi", "err"], off: ["ht.tk_tat", "off"], chua_gan: ["ht.tk_chua_gan", "off"],
  };

  function veKenh() {
    var g = _host && _host.querySelector(".ht-acc-grid");
    if (!g) return;
    if (!_tk.length) {
      g.innerHTML = '<div class="ht-empty">' + ic("plug") +
        '<b>' + esc(window.t("ht.tk_rong")) + '</b><div>' + esc(window.t("ht.tk_rong_goi_y")) + '</div>' +
        '<button class="s-btn ht-them-tk2" type="button">' + ic("plus") + ' ' + esc(window.t("ht.them_tk")) + '</button></div>';
      g.querySelector(".ht-them-tk2").onclick = function () { moThemTK(); };
      return;
    }
    g.innerHTML = "";
    _tk.forEach(function (a) { g.appendChild(theTK(a)); });
  }

  // MỘT khuôn thẻ cho mọi kênh. Khác nhau duy nhất theo LOẠI (kind), không theo tên kênh:
  // kind "bot" có bot trực và không có công tắc; kind "account" có công tắc ghi và không có bot.
  function theTK(a) {
    var k = kenhCua(a.channel);
    var tt = TT_TK[a.state] || TT_TK.off;
    var nl = a.nang_luc || {};
    var chips = [];
    if (nl.nhom) chips.push(ic("users") + " " + esc(window.t("ht.nl_nhom")));
    if (nl.gui_file) chips.push(ic("paperclip") + " " + esc(window.t("ht.nl_file")));
    if (nl.tra_loi_tu_javis) chips.push(ic("send") + " " + esc(window.t("ht.nl_tra_loi")));
    var ten = a.external_id ? (a.tien_to_ten || "") + a.external_id : "";
    var botDong = a.kind === "bot"
      ? (a.bot_id
          ? '<span>' + ic(a.bot_icon || "headset") + ' ' + esc(window.t("ht.tk_bot_truc")) + ' <b>' + esc(a.bot_name) + '</b>' +
            (a.bot_enabled ? "" : ' <span class="ht-warn">(' + esc(window.t("ht.bot_tat")) + ')</span>') + '</span>'
          : '<span class="ht-warn">' + ic("triangle-alert") + ' ' + esc(window.t("ht.tk_chua_bot")) + '</span>')
      : '<span>' + ic("user-round") + ' ' + esc(window.t("ht.tk_cua_ban")) + '</span>';
    var so = '<span>' + ic("messages-square") + ' ' + esc(window.t("ht.n_hoi_thoai", { count: a.so_hoi_thoai || 0 })) +
             (a.chua_doc ? ' · <b>' + esc(window.t("ht.n_chua_doc", { count: a.chua_doc })) + '</b>' : "") + '</span>';
    var lanCuoi = a.lan_cuoi ? '<span>' + esc(window.t("ht.doc_luc", { luc: gio(a.lan_cuoi) })) + '</span>' : "";
    // Bọc câu lỗi trong <span> chứ không để làm text trần: text trần thành một flex item vô
    // danh, CSS không với tới được để cho phép ngắt dòng. Chuỗi lỗi của MCP thường là một cục
    // JSON không có dấu cách nào, nên không bọc là nó tràn ra đè sang thẻ bên cạnh.
    // Giữ nguyên câu lỗi ĐẦY ĐỦ trong title: cắt còn 200 ký tự là vừa đủ để thấy có lỗi mà
    // không đủ để biết lỗi gì.
    var loi = a.loi ? '<div class="ht-acc-loi" title="' + esc(a.loi) + '">' + ic("triangle-alert") +
              '<span>' + esc(String(a.loi).slice(0, 200)) + '</span></div>' : "";
    var congTac = a.kind === "account"
      ? '<label class="ht-switch"><input type="checkbox" class="ht-watch"' + (a.watch ? " checked" : "") + '>' +
        '<span>' + esc(window.t("ht.ghi_hoi_thoai")) + '</span></label>'
      : "";
    var c = el(
      '<div class="ht-acc" data-id="' + esc(a.id) + '">' +
        '<div class="ht-acc-head">' +
          '<span class="ht-acc-logo" style="--kenh:' + esc(a.mau || "var(--accent)") + '">' + logoKenh(a.channel, "22px") + '</span>' +
          '<span class="ht-acc-title"><strong>' + esc(a.label) + '</strong>' +
            '<small>' + esc(k.nhan) + (ten ? ' · ' + esc(ten) : "") + '</small></span>' +
          '<span class="cb-dot ' + tt[1] + '" title="' + esc(a.loi || window.t(tt[0])) + '"></span>' +
          '<span class="cb-state">' + esc(window.t(tt[0])) + '</span>' +
        '</div>' +
        '<div class="ht-acc-meta">' + botDong + '</div>' +
        '<div class="ht-acc-meta">' + so + lanCuoi + '</div>' +
        (chips.length ? '<div class="ht-acc-nl">' + chips.map(function (x) { return '<span>' + x + '</span>'; }).join("") + '</div>' : "") +
        loi +
        '<div class="ht-acc-acts">' +
          congTac +
          '<button type="button" class="s-btn-ghost ht-acc-inbox">' + ic("messages-square") + ' ' + esc(window.t("ht.tab_inbox")) + '</button>' +
          (a.kind === "bot" && !a.bot_id
            ? '<button type="button" class="s-btn-ghost ht-acc-tao-bot">' + ic("headset") + ' ' + esc(window.t("ht.tk_tao_bot")) + '</button>' : "") +
          (a.sua_duoc ? '<button type="button" class="s-btn-ghost ht-acc-sua">' + esc(window.t("common.edit")) + '</button>' : "") +
          (a.kind === "bot"
            ? '<button type="button" class="s-btn-ghost ht-acc-xoa">' + esc(window.t("common.delete")) + '</button>'
            // Kênh kiểu "account" (Zalo cá nhân) không xoá ở đây được: nó là một kết nối bên
            // trang Kết nối. Chỉ đường sang đó, đừng để thẻ câm.
            : '<button type="button" class="s-btn-ghost ht-acc-ket-noi">' + ic("plug") + ' ' +
              esc(window.t("ht.mo_ket_noi")) + '</button>') +
        '</div>' +
      '</div>');
    c.querySelector(".ht-acc-inbox").onclick = function () { _cho = { account_key: a.account_key }; chonTab("inbox"); };
    var tb = c.querySelector(".ht-acc-tao-bot");
    if (tb) tb.onclick = function () {
      chonTab("chatbot");
      try { document.dispatchEvent(new CustomEvent("javis:chatbot-new", { detail: { account_id: a.id } })); } catch (e) {}
    };
    var cb = c.querySelector(".ht-watch");
    if (cb) cb.onchange = async function () {
      cb.disabled = true;
      try {
        await api("/channels/accounts/" + encodeURIComponent(a.id) + "/watch",
                  { method: "POST", body: fd({ on: cb.checked ? "1" : "0", channel: a.channel }) });
      } catch (e) { alert(window.t("ht.loi_doi") + " " + e.message); cb.checked = !cb.checked; }
      cb.disabled = false;
      _dauVetTK = "";
      taiTK(true);
    };
    var sua = c.querySelector(".ht-acc-sua");
    if (sua) sua.onclick = function () { moSuaTK(a); };
    var kn = c.querySelector(".ht-acc-ket-noi");
    if (kn) kn.onclick = function () { try { window.JavisNav.go("mcp"); } catch (e) {} };
    var xoa = c.querySelector(".ht-acc-xoa");
    if (xoa) xoa.onclick = async function () {
      // Server chặn xoá khi còn bot trực. Nói đúng câu đó ở đây, và mở luôn form Sửa của con
      // bot ấy để gỡ tài khoản ra - chứ không bắt người dùng tự đi tìm bot nào đang giữ nó.
      if (!a.xoa_duoc) {
        if (!a.bot_id) return alert(window.t("ht.xoa_khong_duoc"));
        if (!confirm(window.t("ht.xoa_dang_truc", { ten: a.label, bot: a.bot_name }))) return;
        chonTab("chatbot");
        try { document.dispatchEvent(new CustomEvent("javis:chatbot-edit", { detail: { bot_id: a.bot_id } })); }
        catch (e) {}
        return;
      }
      if (!confirm(window.t("ht.xn_xoa_tk", { ten: a.label }))) return;
      try { await api("/channels/accounts/" + encodeURIComponent(a.id) + "/delete", { method: "POST" }); }
      catch (e) { alert(window.t("ht.loi_doi") + " " + e.message); }
      _dauVetTK = "";
      taiTK(true);
    };
    return c;
  }

  // Thêm tài khoản: bước 1 chọn LOẠI kênh (mọi kênh trong sổ, kể cả kênh không nhận token,
  // để người dùng thấy đủ và biết kênh đó nối ở đâu), bước 2 dán token, kiểm, đặt tên.
  //
  // Hàm này là chỗ DUY NHẤT trong dashboard biết cách nối một tài khoản kênh. Form tạo bot
  // (chatbots.js) gọi lại chính nó qua `JavisConversations.themTaiKhoan` thay vì chép một bản
  // thứ hai: trước 0.61.1 có hai form dán token song song, nên hướng dẫn riêng của từng kênh
  // bị nhân đôi và thêm một kênh mới là phải sửa cả hai nơi.
  //
  // `opts.onXong(account)`: gọi khi tài khoản đã tạo xong, để nơi gọi tự làm tiếp (form bot
  // tích sẵn tài khoản vừa nối). Không truyền thì chỉ nạp lại tab Kênh như cũ.
  async function moThemTK(opts) {
    opts = opts || {};
    // Gọi từ tab Chatbot thì sổ kênh có thể chưa nạp: không có nó thì modal hiện ra trống trơn.
    if (!_kenhDS.length) { try { await taiTK(); } catch (e) {} }
    var kenhBot = _kenhDS.filter(function (k) { return k.kind === "bot"; });
    var kenhKhac = _kenhDS.filter(function (k) { return k.kind !== "bot"; });
    var chon = kenhBot.length ? kenhBot[0].id : "";
    var uname = "", meta = {};
    var box = el('<div class="ht-modal"><div class="ht-form">' +
      '<h3>' + esc(window.t("ht.them_tk")) + '</h3>' +
      '<label>' + esc(window.t("ht.lb_loai_kenh")) + '</label>' +
      '<div class="cb-kenh">' + kenhBot.map(function (k) {
        return '<button class="cb-kenh-o' + (k.id === chon ? " on" : "") + '" data-k="' + esc(k.id) + '" type="button">' +
          '<span class="cb-kenh-logo">' + (Icons.kenh ? Icons.kenh(k.logo, { size: "26px" }) : "") + '</span>' +
          '<b>' + esc(k.nhan) + '</b><small>' + esc(k.tom_tat || "") + '</small></button>';
      }).join("") + '</div>' +
      (kenhKhac.length ? '<div class="ht-kenh-khac">' + kenhKhac.map(function (k) {
        return '<div class="ht-src"><span class="ht-src-ic">' + (Icons.kenh ? Icons.kenh(k.logo, { size: "18px" }) : "") + '</span>' +
          '<span class="ht-src-text"><strong>' + esc(k.nhan) + '</strong><small>' + esc(k.tom_tat || "") + ' ' +
          esc(k.kind === "account" ? window.t("ht.kenh_noi_o_ket_noi") : window.t("ht.kenh_sap_co")) + '</small></span>' +
          (k.kind === "account" ? '<button type="button" class="s-btn-ghost ht-di-ket-noi">' + esc(window.t("ht.mo_ket_noi")) + '</button>' : "") +
          '</div>';
      }).join("") + '</div>' : "") +
      '<label id="htTokenLabel"></label>' +
      '<div class="cb-row"><input id="htToken" type="password" placeholder="' + esc(window.t("cb.ph_token")) + '">' +
        '<button class="s-btn-ghost" id="htCheck" type="button">' + esc(window.t("cb.kiem_tra")) + '</button></div>' +
      '<div class="cb-hint" id="htTokenNote"></div>' +
      '<label>' + esc(window.t("ht.lb_nhan_tk")) + '</label>' +
      '<input id="htLabel" placeholder="' + esc(window.t("ht.ph_nhan_tk")) + '">' +
      '<div class="ht-form-acts">' +
        '<button class="s-btn-ghost ht-close" type="button">' + esc(window.t("common.cancel")) + '</button>' +
        '<button class="s-btn ht-save" type="button">' + esc(window.t("common.save")) + '</button>' +
      '</div></div></div>');
    document.body.appendChild(box);
    var dong = function () { if (box.parentNode) box.parentNode.removeChild(box); };
    box.onmousedown = function (e) { if (e.target === box) dong(); };
    box.querySelector(".ht-close").onclick = dong;
    box.querySelectorAll(".ht-di-ket-noi").forEach(function (n) {
      n.onclick = function () { dong(); try { window.JavisNav.go("mcp"); } catch (e) {} };
    });
    function apKenh(id) {
      chon = id; uname = ""; meta = {};
      var k = kenhCua(id);
      box.querySelector("#htTokenLabel").textContent = "Token " + k.nhan;
      box.querySelector("#htTokenNote").textContent = (k.lay_token || "") + " " + window.t("cb.token_rieng");
      box.querySelectorAll(".cb-kenh-o").forEach(function (n) { n.classList.toggle("on", n.dataset.k === id); });
    }
    box.querySelectorAll(".cb-kenh-o").forEach(function (n) { n.onclick = function () { apKenh(n.dataset.k); }; });
    if (chon) apKenh(chon);
    else box.querySelector("#htTokenLabel").textContent = window.t("ht.khong_kenh_token");
    box.querySelector("#htCheck").onclick = async function () {
      var t = box.querySelector("#htToken").value.trim();
      var note = box.querySelector("#htTokenNote");
      var k = kenhCua(chon);
      if (!t) { note.textContent = window.t("cb.dan_token"); return; }
      note.textContent = window.t("cb.dang_hoi", { kenh: k.nhan });
      try {
        var r = await api("/channels/verify-token", { method: "POST", body: fd({ channel: chon, token: t }) });
        uname = r.username || "";
        meta = { vao_duoc_nhom: r.vao_duoc_nhom, account_type: r.account_type || "" };
        note.innerHTML = ic("check", { cls: "ic-ok" }) + " " + esc(window.t("cb.dung_bot")) + " <b>" +
          esc((k.tien_to_ten || "") + uname) + "</b> (" + esc(r.bot_name || "") + ")" +
          (r.vao_duoc_nhom === false
            ? '<br><span class="cb-warn">' + esc(window.t("cb.zalo_khong_nhom", { goi: r.account_type || window.t("cb.goi_co_ban") })) + '</span>'
            : "");
        var lb = box.querySelector("#htLabel");
        if (lb && !lb.value.trim()) lb.value = r.bot_name || uname;
      } catch (e) { note.innerHTML = '<span class="cb-warn">' + esc(e.message) + '</span>'; }
    };
    box.querySelector(".ht-save").onclick = async function () {
      var t = box.querySelector("#htToken").value.trim();
      var k = kenhCua(chon);
      if (!chon) return alert(window.t("ht.khong_kenh_token"));
      if (!t) return alert(window.t("cb.dan_token_kenh", { kenh: k.nhan }) + "\n\n" + (k.lay_token || ""));
      var moi = null;
      try {
        var r = await api("/channels/accounts", { method: "POST", body: fd({
          channel: chon, token: t, label: box.querySelector("#htLabel").value.trim(), bot_username: uname }) });
        moi = r.account || (r.id ? { id: r.id, channel: chon } : null);
      } catch (e) { return alert(window.t("ht.loi_doi") + " " + e.message); }
      dong();
      _dauVetTK = "";
      taiTK(true);
      if (opts.onXong) { try { opts.onXong(moi); } catch (e) {} }
    };
  }

  function moSuaTK(a) {
    var k = kenhCua(a.channel);
    var uname = "";
    var box = el('<div class="ht-modal"><div class="ht-form">' +
      '<h3>' + esc(window.t("ht.sua_tk")) + ' - ' + esc(a.label) + '</h3>' +
      '<label>' + esc(window.t("ht.lb_nhan_tk")) + '</label>' +
      '<input id="htLabel" value="' + esc(a.label) + '">' +
      '<label>Token ' + esc(k.nhan) + ' ' + esc(window.t("cb.token_de_trong")) + '</label>' +
      '<div class="cb-row"><input id="htToken" type="password" placeholder="' + esc(window.t("cb.ph_token")) + '">' +
        '<button class="s-btn-ghost" id="htCheck" type="button">' + esc(window.t("cb.kiem_tra")) + '</button></div>' +
      '<div class="cb-hint" id="htTokenNote">' + (a.external_id ? esc(window.t("cb.dang_dung")) + " " + esc((a.tien_to_ten || "") + a.external_id) : "") + '</div>' +
      (a.bot_id ? '<div class="cb-hint">' + esc(window.t("ht.tk_doi_token_bot", { bot: a.bot_name })) + '</div>' : "") +
      '<div class="ht-form-acts">' +
        '<button class="s-btn-ghost ht-close" type="button">' + esc(window.t("common.cancel")) + '</button>' +
        '<button class="s-btn ht-save" type="button">' + esc(window.t("common.save")) + '</button>' +
      '</div></div></div>');
    document.body.appendChild(box);
    var dong = function () { if (box.parentNode) box.parentNode.removeChild(box); };
    box.onmousedown = function (e) { if (e.target === box) dong(); };
    box.querySelector(".ht-close").onclick = dong;
    box.querySelector("#htCheck").onclick = async function () {
      var t = box.querySelector("#htToken").value.trim();
      var note = box.querySelector("#htTokenNote");
      if (!t) { note.textContent = window.t("cb.dan_token"); return; }
      note.textContent = window.t("cb.dang_hoi", { kenh: k.nhan });
      try {
        var r = await api("/channels/verify-token", { method: "POST", body: fd({ channel: a.channel, token: t, account_id: a.id }) });
        uname = r.username || "";
        note.innerHTML = ic("check", { cls: "ic-ok" }) + " " + esc(window.t("cb.dung_bot")) + " <b>" +
          esc((k.tien_to_ten || "") + uname) + "</b> (" + esc(r.bot_name || "") + ")";
      } catch (e) { note.innerHTML = '<span class="cb-warn">' + esc(e.message) + '</span>'; }
    };
    box.querySelector(".ht-save").onclick = async function () {
      try {
        await api("/channels/accounts/" + encodeURIComponent(a.id) + "/update", { method: "POST", body: fd({
          label: box.querySelector("#htLabel").value.trim(), token: box.querySelector("#htToken").value.trim(),
          bot_username: uname }) });
      } catch (e) { return alert(window.t("ht.loi_doi") + " " + e.message); }
      dong();
      _dauVetTK = "";
      taiTK(true);
    };
  }

  // Mở trang này từ nơi khác (thẻ bot ở tab Chatbot, console.js) với tab hoặc bộ lọc sẵn.
  function moTu(opts) {
    _cho = opts || {};
    if (_cho.tab) _tab = _cho.tab; else _tab = "inbox";
    if (_host && document.body.contains(_host)) { veTabs(); veTab(); return; }
    try { var s = window.Alpine && Alpine.store("nav"); if (s && s.go) s.go("conversations"); } catch (e) {}
  }

  window.JavisConversations = { render: render, mo: moTu, chonTab: chonTab,
                               themTaiKhoan: moThemTK };
})();
