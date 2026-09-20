/* Trang Hội thoại - Hộp thư khách hàng (Chatbot V2, bản V1: trình xem + tiếp quản).
 *
 * Đọc kho hội thoại của server (`/conversations`): mọi tin khách gửi tới bot chuyên trách
 * (Telegram, Zalo Bot) và tới tài khoản Zalo cá nhân đã bật ghi. Hai cột: danh sách hội thoại
 * bên trái, lịch sử tin bên phải. Trên điện thoại thì một cột: bấm một hội thoại là mở lịch sử,
 * có nút quay lại.
 *
 * Trang này KHÔNG phải cái chuông (notifications.js / JavisInbox): chuông là hòm thư của CHỦ
 * (kết quả việc nền), còn đây là hội thoại giữa KHÁCH và bot. Tiền tố riêng: .ht-*, ht.*,
 * window.JavisConversations.
 *
 * Chưa có ở V1: gõ trả lời khách từ đây. Có: Tiếp quản (bot im ở cuộc chat đó) và Trả lại AI.
 * Ghi chú: KHÔNG dùng ký tự em dash. */
(function () {
  "use strict";

  var NHIP = 5000;          // nhịp tự làm mới, như trang Chatbot
  var TRANG = 60;           // số hội thoại một trang
  var _host = null, _timer = null;
  var _items = [], _stats = {}, _dauVet = "";
  var _kenhLoc = "", _botLoc = "", _q = "";
  var _chon = null;         // id hội thoại đang mở
  var _msgs = [], _conv = null, _dauVetTin = "";
  var _kenhTT = null;       // payload /conversations/channels (bot + tài khoản Zalo)
  var _cho = null;          // bộ lọc chờ áp khi trang mở từ nơi khác (nút trên thẻ bot)

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
  function nhanKenh(id) {
    var c = ((_kenhTT && _kenhTT.channels) || []).filter(function (x) { return x.id === id; })[0];
    return c ? c.nhan : (id || "");
  }
  // Logo kênh: Zalo cá nhân dùng chung logo Zalo, còn lại theo tên kênh.
  function logoKenh(id) {
    var k = id === "zalo_personal" || id === "zalo_oa" ? "zalo" : id;
    return (window.Icons && Icons.kenh) ? Icons.kenh(k, { size: "13px" }) : "";
  }
  function chipKenh(id) {
    return '<span class="ht-chip">' + logoKenh(id) + " " + esc(nhanKenh(id)) + "</span>";
  }

  // ---------------------------------------------------------------- khung trang
  function render(host) {
    _host = host;
    if (_cho) { _botLoc = _cho.bot_id || ""; _kenhLoc = _cho.channel || ""; _cho = null; }
    host.innerHTML =
      '<div class="cview-section ht-wrap">' +
        '<div class="ht-stats"></div>' +
        '<div class="ht-bar">' +
          '<div class="ht-loc"></div>' +
          '<select class="ht-bot"><option value="">' + esc(window.t("ht.moi_bot")) + '</option></select>' +
          '<input class="ht-search" placeholder="' + esc(window.t("ht.tim_ph")) + '">' +
          '<button class="s-btn-ghost ht-kenh-btn" type="button">' + ic("plug") + ' ' +
            esc(window.t("ht.kenh")) + '</button>' +
        '</div>' +
        '<div class="ht-body">' +
          '<div class="ht-list"><div class="ht-empty">' + esc(window.t("common.loading")) + '</div></div>' +
          '<div class="ht-thread"><div class="ht-empty ht-thread-empty">' + ic("messages-square") +
            '<div>' + esc(window.t("ht.chon_mot")) + '</div></div></div>' +
        '</div>' +
      '</div>';
    var s = host.querySelector(".ht-search");
    s.oninput = function () { _q = s.value.trim(); tai(); };
    host.querySelector(".ht-bot").onchange = function (e) { _botLoc = e.target.value; tai(); };
    host.querySelector(".ht-kenh-btn").onclick = moKenh;
    taiKenh().then(function () { tai(); });
    nhip();
  }

  function nhip() {
    if (_timer) clearInterval(_timer);
    _timer = setInterval(function () {
      if (!_host || !document.body.contains(_host)) { clearInterval(_timer); _timer = null; return; }
      if (document.hidden || document.querySelector(".ht-modal")) return;
      tai(true);
      if (_chon) taiTin(true);
    }, NHIP);
  }

  async function taiKenh() {
    try { _kenhTT = await api("/conversations/channels"); } catch (e) { _kenhTT = _kenhTT || { bots: [], zalo_personal: [], channels: [] }; }
    var sel = _host && _host.querySelector(".ht-bot");
    if (!sel) return;
    var cu = sel.value;
    sel.innerHTML = '<option value="">' + esc(window.t("ht.moi_bot")) + '</option>' +
      (_kenhTT.bots || []).map(function (b) {
        return '<option value="' + esc(b.id) + '">' + esc(b.name) + ' (' + esc(b.channel_label) + ')</option>';
      }).join("");
    sel.value = _botLoc || cu || "";
    if (sel.value !== (_botLoc || "")) sel.value = "";
    // Chọn bot chỉ có nghĩa khi có từ hai bot; một bot thì ô chọn là câu hỏi không ai hỏi.
    sel.style.display = (_kenhTT.bots || []).length >= 2 ? "" : "none";
  }

  // `im` = nhịp tự động: không xoá danh sách đang hiện, mạng hỏng một nhịp thì giữ màn hình cũ.
  async function tai(im) {
    var box = _host && _host.querySelector(".ht-list");
    if (!box) return;
    var url = "/conversations?limit=" + TRANG +
      "&channel=" + encodeURIComponent(_kenhLoc) + "&bot_id=" + encodeURIComponent(_botLoc) +
      "&q=" + encodeURIComponent(_q);
    try {
      var d = await api(url);
      _items = d.items || [];
      _stats = d.stats || {};
      if (d.channels && _kenhTT) _kenhTT.channels = d.channels;
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
  }

  function veStats() {
    var b = _host.querySelector(".ht-stats");
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
    var co = Object.keys((_stats.theo_kenh) || {});
    if (_kenhLoc && co.indexOf(_kenhLoc) < 0) co.push(_kenhLoc);
    if (co.length < 2 && !_kenhLoc) { b.innerHTML = ""; return; }
    var chips = [{ id: "", nhan: window.t("ht.tat_ca") }].concat(co.map(function (k) { return { id: k, nhan: nhanKenh(k) }; }));
    b.innerHTML = chips.map(function (c) {
      return '<button type="button" class="ht-loc-chip' + (c.id === _kenhLoc ? " on" : "") +
        '" data-k="' + esc(c.id) + '">' + (c.id ? logoKenh(c.id) + " " : "") + esc(c.nhan) + '</button>';
    }).join("");
    b.querySelectorAll(".ht-loc-chip").forEach(function (x) {
      x.onclick = function () { _kenhLoc = x.dataset.k; tai(); };
    });
  }

  function veDanhSach() {
    var box = _host.querySelector(".ht-list");
    if (!_items.length) {
      var coBot = _kenhTT && (_kenhTT.bots || []).some(function (b) { return b.enabled; });
      var coZalo = _kenhTT && (_kenhTT.zalo_personal || []).some(function (z) { return z.theo_doi; });
      box.innerHTML = '<div class="ht-empty">' + ic("messages-square") +
        '<b>' + esc(_q || _kenhLoc || _botLoc ? window.t("ht.khong_khop") : window.t("ht.chua_co")) + '</b>' +
        (!(coBot || coZalo) ? '<div>' + esc(window.t("ht.chua_co_goi_y")) + '</div>' +
          '<button class="s-btn ht-mo-kenh" type="button">' + esc(window.t("ht.kenh")) + '</button>' : "") +
        '</div>';
      var nut = box.querySelector(".ht-mo-kenh");
      if (nut) nut.onclick = moKenh;
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
    _host.querySelector(".ht-wrap").classList.remove("thread-on");
    _host.querySelector(".ht-thread").innerHTML = '<div class="ht-empty ht-thread-empty">' +
      ic("messages-square") + '<div>' + esc(window.t("ht.chon_mot")) + '</div></div>';
    veDanhSach();
  }

  async function taiTin(im) {
    if (!_chon) return;
    var id = _chon;
    var box = _host.querySelector(".ht-thread");
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
    var c = _conv || {};
    var ten = c.title || c.customer_name || c.external_chat_id;
    var human = c.mode === "human";
    var laBot = !!c.bot_id;
    var cuon = box.querySelector(".ht-msgs");
    var oDay = !cuon || (cuon.scrollHeight - cuon.scrollTop - cuon.clientHeight < 80);
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
      '<div class="ht-foot">' + esc(window.t("ht.chua_tra_loi")) + '</div>';
    box.querySelector(".ht-back").onclick = dongThread;
    var mb = box.querySelector(".ht-mode-btn");
    if (mb) mb.onclick = function () { doiMode(c.id, human ? "ai" : "human"); };
    var m = box.querySelector(".ht-msgs");
    if (oDay) m.scrollTop = m.scrollHeight;
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

  // ---------------------------------------------------------------- kênh (nguồn hội thoại)
  async function moKenh() {
    await taiKenh();
    var k = _kenhTT || { bots: [], zalo_personal: [] };
    var bots = (k.bots || []).map(function (b) {
      return '<div class="ht-src">' +
        '<span class="ht-src-ic">' + ic(b.icon || "headset") + '</span>' +
        '<span class="ht-src-text"><strong>' + esc(b.name) + '</strong>' +
          '<small>' + chipKenh(b.channel) + ' · ' +
            esc(b.enabled ? window.t("ht.bot_bat") : window.t("ht.bot_tat")) + ' · ' +
            esc(window.t("ht.n_hoi_thoai", { count: b.so_hoi_thoai || 0 })) + '</small></span>' +
        '</div>';
    }).join("") || '<div class="ht-empty small">' + esc(window.t("ht.chua_bot")) + '</div>';
    var zalo = (k.zalo_personal || []).map(function (z) {
      return '<div class="ht-src" data-zid="' + esc(z.id) + '">' +
        '<span class="ht-src-ic">' + logoKenh("zalo_personal") + '</span>' +
        '<span class="ht-src-text"><strong>' + esc(z.label) + '</strong>' +
          '<small>' + esc(window.t("ht.n_hoi_thoai", { count: z.so_hoi_thoai || 0 })) +
            (z.theo_doi && z.lan_cuoi ? ' · ' + esc(window.t("ht.doc_luc", { luc: gio(z.lan_cuoi) })) : "") +
          '</small>' +
          (z.loi ? '<small class="ht-warn">' + ic("triangle-alert") + ' ' + esc(z.loi) + '</small>' : "") +
        '</span>' +
        '<label class="ht-switch"><input type="checkbox" class="ht-zalo-on"' + (z.theo_doi ? " checked" : "") + '>' +
          '<span>' + esc(window.t("ht.ghi_hoi_thoai")) + '</span></label>' +
        '</div>';
    }).join("") || '<div class="ht-empty small">' + esc(window.t("ht.chua_zalo")) + '</div>';
    var box = el('<div class="ht-modal"><div class="ht-form">' +
      '<h3>' + esc(window.t("ht.kenh_tieu_de")) + '</h3>' +
      '<p class="ht-intro">' + esc(window.t("ht.kenh_intro")) + '</p>' +
      '<h4>' + esc(window.t("ht.kenh_bot")) + '</h4>' + bots +
      '<h4>' + esc(window.t("ht.kenh_zalo")) + '</h4>' +
      '<p class="ht-intro">' + esc(window.t("ht.kenh_zalo_intro")) + '</p>' + zalo +
      '<div class="ht-form-acts"><button class="s-btn ht-close" type="button">' + esc(window.t("common.close")) + '</button></div>' +
      '</div></div>');
    document.body.appendChild(box);
    var dong = function () { if (box.parentNode) box.parentNode.removeChild(box); };
    box.onmousedown = function (e) { if (e.target === box) dong(); };
    box.querySelector(".ht-close").onclick = dong;
    box.querySelectorAll(".ht-src[data-zid]").forEach(function (n) {
      var cb = n.querySelector(".ht-zalo-on");
      cb.onchange = async function () {
        cb.disabled = true;
        try {
          await api("/conversations/zalo/" + encodeURIComponent(n.dataset.zid) + "/watch",
                    { method: "POST", body: fd({ on: cb.checked ? "1" : "0" }) });
        } catch (e) { alert(window.t("ht.loi_zalo") + " " + e.message); cb.checked = !cb.checked; }
        cb.disabled = false;
      };
    });
  }

  // Mở trang này từ nơi khác (thẻ bot ở trang Chatbot) với bộ lọc sẵn.
  function moTu(opts) {
    _cho = opts || {};
    try { var s = window.Alpine && Alpine.store("nav"); if (s && s.go) s.go("conversations"); } catch (e) {}
  }

  window.JavisConversations = { render: render, mo: moTu };
})();
