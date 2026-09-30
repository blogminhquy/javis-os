/* Trang Hội thoại - MỘT trang cho hộp thư khách, kênh và nhân viên AI (Chatbot V2, 0.61.0).
 *
 * Ba tab, cùng một chỗ trên thanh bên:
 *   - Hộp thư:  mọi tin khách từ mọi kênh (`/conversations`), đọc lại, tiếp quản, và từ 0.61.0
 *               TRẢ LỜI KHÁCH NGAY TỪ ĐÂY khi kênh có năng lực đó (`/conversations/{id}/reply`).
 *   - Tài khoản bot: mọi tài khoản kênh, MỘT khuôn thẻ bất kể kênh (`/channels/accounts`): bot
 *               Telegram, bot Zalo, Zalo cá nhân, và kênh thêm sau này. Không kênh nào có mục riêng.
 *               Từ 0.62.4 tab này LỌC THEO BRAIN đang mở: tài khoản bot thuộc về một brain, nên
 *               đứng ở brain nào chỉ thấy tài khoản của brain đó (cộng tài khoản chưa gán chủ).
 *               Công tắc "mọi brain" để tìm lại một tài khoản đã gán nhầm chỗ.
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

  // Brain đang mở. Cùng cách chatbots.js lấy, để hai tab của cùng một trang không lệch nhau.
  function brain() { try { return (window.currentBrainPath && window.currentBrainPath()) || "brain"; } catch (e) { return "brain"; } }

  // Danh sách brain, đọc từ CHÍNH ô chọn brain của app (#graphSource). Không gọi /brains
  // riêng: `currentBrainPath()` sinh khoá từ ô đó, nên lấy chỗ khác là hai không gian khoá
  // khác nhau và tài khoản rơi vào một brain không ai mở được.
  function dsBrain() {
    var src = document.getElementById("graphSource");
    var ds = [];
    if (!src) return ds;
    [].forEach.call(src.options, function (o) {
      var v = o.value.indexOf("path:") === 0 ? o.value.slice(5) : "brain";
      // `data-brain-name` là TÊN THƯ MỤC sạch (brains-ui.js gắn). Nhãn hiển thị của ô chọn có
      // đuôi đếm note (" · 19"), lấy nguyên là ra "brain Shop Giay · 19" trên thẻ tài khoản.
      var ten = (o.dataset && o.dataset.brainName) || (o.textContent || "").trim().replace(/\s*·\s*\d+\+?$/, "");
      if (!ds.some(function (x) { return x.v === v; })) ds.push({ v: v, ten: ten || v });
    });
    return ds;
  }

  // Khoá brain -> TÊN đọc được. Khoá thật là "brain" (brain mặc định cũ) hoặc một đường dẫn
  // tuyệt đối; dán nguyên nó lên thẻ thì ra "brain brain" hoặc một dòng path dài ngoẵng.
  // Không tra được tên (brain đã xoá) thì lấy đoạn cuối đường dẫn, cùng lắm là khoá thô.
  function tenBrain(v) {
    if (!v) return "";
    var hit = dsBrain().filter(function (x) { return x.v === v; })[0];
    if (hit) return hit.ten;
    var m = String(v).replace(/[\\/]+$/, "").split(/[\\/]/);
    return m[m.length - 1] || String(v);
  }

  var NHIP = 5000;          // nhịp tự làm mới, như trang Chatbot
  var TRANG = 60;           // số hội thoại một trang
  var TABS = ["inbox", "kenh", "chatbot"];
  var _host = null, _timer = null, _tab = "inbox";
  var _items = [], _stats = {}, _dauVet = "";
  var _kenhLoc = "", _botLoc = "", _tkLoc = "", _q = "";
  var _statusLoc = "", _typeLoc = "";   // bộ lọc dropdown (0.65.3), lưu ở trình duyệt qua JavisConvFilters
  var _facets = null, _botList = [];    // số đếm cho dropdown và các bot có hội thoại (server cấp, toàn hòm thư)
  var _chon = null;         // id hội thoại đang mở
  var _msgs = [], _conv = null, _dauVetTin = "", _silence = null;   // _silence: vì sao bot im ở tin khách cuối
  var _running = false;     // bot của cuộc chat đang mở có đang chạy không (server cấp)
  var _actBusy = "";        // "answer" | "draft" khi đang chờ bot soạn
  var _actNote = null;      // {text, err}: dòng nói kết quả của lần bấm gần nhất, sống qua các lần vẽ lại khung
  var _kenhDS = [];         // các LOẠI kênh (server: id, nhan, logo, kind, nang_luc...)
  var _tk = [];             // mọi tài khoản kênh, một khuôn
  var _dauVetTK = "";
  var _tkMoiBrain = false;  // tab Tài khoản bot: đang xem của MỌI brain thay vì brain đang mở
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
      var d = await api("/channels/accounts?brain=" + encodeURIComponent(brain()) +
                        (_tkMoiBrain ? "&tat_ca=1" : ""));
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
    return true;
  }

  // ---------------------------------------------------------------- HỘP THƯ
  function renderInbox(body) {
    if (_cho) {
      // Mở từ nơi khác (nút trên thẻ bot, tab Tài khoản bot): lọc đúng thứ được chỉ, bỏ tình trạng và loại đã lưu để
      // khỏi giấu mất hội thoại người ta muốn xem.
      _botLoc = _cho.bot_id || ""; _kenhLoc = _cho.channel || ""; _tkLoc = _cho.account_key || "";
      _statusLoc = ""; _typeLoc = "";
      _cho = null;
      saveFilters();
    } else if (window.JavisConvFilters) {
      var saved = window.JavisConvFilters.load();
      _botLoc = saved.bot; _statusLoc = saved.status; _typeLoc = saved.type; _kenhLoc = saved.channel;
    }
    body.innerHTML =
      '<div class="ht-wrap">' +
        '<div class="ht-stats"></div>' +
        '<div class="ht-bar">' +
          '<input class="ht-search" placeholder="' + esc(window.t("ht.tim_ph")) + '">' +
          '<select class="ht-f ht-f-bot" aria-label="' + esc(window.t("ht.f_aria_bot")) + '"></select>' +
          '<select class="ht-f ht-f-status" aria-label="' + esc(window.t("ht.f_aria_status")) + '"></select>' +
          '<select class="ht-f ht-f-type" aria-label="' + esc(window.t("ht.f_aria_type")) + '"></select>' +
          '<select class="ht-f ht-f-channel" aria-label="' + esc(window.t("ht.f_aria_kenh")) + '" hidden></select>' +
        '</div>' +
        '<div class="ht-fsum">' +
          '<span class="ht-fcount"></span><span class="ht-loc"></span>' +
          '<button type="button" class="ht-fclear" hidden>' + esc(window.t("ht.f_clear")) + '</button>' +
        '</div>' +
        '<div class="ht-body">' +
          '<div class="ht-list"><div class="ht-empty">' + esc(window.t("common.loading")) + '</div></div>' +
          '<div class="ht-thread"><div class="ht-empty ht-thread-empty">' + ic("messages-square") +
            '<div>' + esc(window.t("ht.chon_mot")) + '</div></div></div>' +
        '</div>' +
      '</div>';
    var s = body.querySelector(".ht-search");
    s.oninput = function () { _q = s.value.trim(); tai(); };
    body.querySelector(".ht-f-bot").onchange = function (e) { _botLoc = e.target.value; onFilterChange(); };
    body.querySelector(".ht-f-status").onchange = function (e) { _statusLoc = e.target.value; onFilterChange(); };
    body.querySelector(".ht-f-type").onchange = function (e) { _typeLoc = e.target.value; onFilterChange(); };
    body.querySelector(".ht-f-channel").onchange = function (e) { _kenhLoc = e.target.value; onFilterChange(); };
    body.querySelector(".ht-fclear").onclick = function () {
      _botLoc = _statusLoc = _typeLoc = _kenhLoc = _tkLoc = "";
      onFilterChange();
    };
    taiTK(false).catch(function () {}).then(function () { tai(); if (_chon) taiTin(false); });
  }

  function filterState() { return { bot: _botLoc, status: _statusLoc, type: _typeLoc, channel: _kenhLoc }; }
  function saveFilters() { if (window.JavisConvFilters) window.JavisConvFilters.save(filterState()); }
  function onFilterChange() { saveFilters(); tai(); }

  // `im` = nhịp tự động: không xoá danh sách đang hiện, mạng hỏng một nhịp thì giữ màn hình cũ.
  async function tai(im) {
    var box = _host && _host.querySelector(".ht-list");
    if (!box) return;
    var url = "/conversations?limit=" + TRANG + "&account_id=" + encodeURIComponent(_tkLoc) +
      "&q=" + encodeURIComponent(_q) + (window.JavisConvFilters ? window.JavisConvFilters.query(filterState()) : "");
    try {
      var d = await api(url);
      _items = d.items || [];
      _stats = d.stats || {};
      _facets = d.facets || null;
      _botList = d.bots || [];
      if (d.channels) _kenhDS = d.channels;
      var vet = JSON.stringify([_items, _stats, _facets, _botList]);
      if (im && vet === _dauVet) return;
      _dauVet = vet;
    } catch (e) {
      if (!im) box.innerHTML = '<div class="ht-empty">' + esc(window.t("ht.loi_tai")) + ' ' + esc(e.message) + '</div>';
      return;
    }
    veStats();
    paintFilters();
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

  // Bộ lọc dropdown (0.65.3): một hàng chung với ô tìm, số đếm nằm trong từng lựa chọn (chip chiếm quá nhiều chỗ khi
  // chạy nhiều bot). Phần dựng chuỗi <option> nằm ở conversations-filters.js.
  var FILTER_SEL = { bot: ".ht-f-bot", status: ".ht-f-status", type: ".ht-f-type", channel: ".ht-f-channel" };

  function paintFilters() {
    var F = window.JavisConvFilters;
    if (!_host || !F) return;
    var st = filterState();
    var html = {
      bot: F.botOptions(_botList, _facets, st.bot),
      status: F.statusOptions(_facets, st.status),
      type: F.typeOptions(_facets, st.type),
      channel: F.channelOptions(_stats.theo_kenh || {}, st.channel, nhanKenh),
    };
    Object.keys(FILTER_SEL).forEach(function (k) {
      var sel = _host.querySelector(FILTER_SEL[k]);
      if (!sel) return;
      // Đang mở dropdown thì KHÔNG dựng lại: nhịp tự làm mới 5 giây sẽ đóng nó giữa chừng, đúng lúc người ta chọn.
      if (document.activeElement !== sel && sel.dataset.sig !== html[k]) {
        sel.innerHTML = html[k];
        sel.dataset.sig = html[k];
      }
      sel.value = st[k];
      sel.classList.toggle("on", !!st[k]);
    });
    // Kênh chỉ đáng có khi hòm thư có từ 2 kênh (hoặc đang lọc theo một kênh).
    var ch = _host.querySelector(FILTER_SEL.channel);
    if (ch) ch.hidden = Object.keys(_stats.theo_kenh || {}).length < 2 && !st.channel;
    var active = F.activeCount(st) + (_tkLoc ? 1 : 0);
    var cnt = _host.querySelector(".ht-fcount");
    if (cnt) cnt.textContent = window.t(active ? "ht.f_count_f" : "ht.f_count",
      { n: _items.length >= TRANG ? TRANG + "+" : _items.length, f: active });
    var clr = _host.querySelector(".ht-fclear");
    if (clr) clr.hidden = !active;
    // Đang lọc theo MỘT tài khoản (mở từ tab Tài khoản bot): một chip có nút bỏ.
    var tkChip = _tkLoc ? (_tk.filter(function (a) { return a.account_key === _tkLoc; })[0] || null) : null;
    var loc = _host.querySelector(".ht-loc");
    if (loc) {
      loc.innerHTML = tkChip ? '<button type="button" class="ht-loc-chip on ht-loc-tk">' + logoKenh(tkChip.channel) + ' ' +
        esc(tkChip.label) + ' ' + ic("x") + '</button>' : "";
      var bo = loc.querySelector(".ht-loc-tk");
      if (bo) bo.onclick = function () { _tkLoc = ""; tai(); };
    }
  }

  function veDanhSach() {
    var box = _host.querySelector(".ht-list");
    if (!box) return;
    if (!_items.length) {
      var coNguon = _tk.some(function (a) { return a.ghi; });
      box.innerHTML = '<div class="ht-empty">' + ic("messages-square") +
        '<b>' + esc(_q || _kenhLoc || _botLoc || _tkLoc || _statusLoc || _typeLoc ? window.t("ht.khong_khop") : window.t("ht.chua_co")) + '</b>' +
        (!coNguon ? '<div>' + esc(window.t("ht.chua_co_goi_y")) + '</div>' +
          '<button class="s-btn ht-mo-kenh" type="button">' + ic("plug") + ' ' + esc(window.t("ht.tab_kenh")) + '</button>' : "") +
        '</div>';
      var nut = box.querySelector(".ht-mo-kenh");
      if (nut) nut.onclick = function () { chonTab("kenh"); };
      return;
    }
    var F = window.JavisConvFilters;
    box.innerHTML = _items.map(function (c) {
      var ten = c.title || c.customer_name || c.external_chat_id;
      var ai = c.last_sender_type === "ai" ? window.t("ht.bot") + ": "
             : c.last_sender_type === "human" ? window.t("ht.ban") + ": " : "";
      // Dòng thẻ: tên bot (chỉ khi có từ 2 bot, một bot thì là nhiễu) và tình trạng. Không có thẻ nào thì không có dòng.
      var tags = [];
      if (_botList.length >= 2 && c.bot_name) {
        tags.push('<span class="ht-bot-tag c' + (F ? F.botColor(c.bot_id) : 0) + '">' + esc(c.bot_name) + '</span>');
      }
      if (c.mode === "human") tags.push('<span class="ht-mode">' + esc(window.t("ht.mode_human")) + '</span>');
      else if (c.need_reply) tags.push('<span class="ht-need">' + esc(window.t("ht.tag_need")) + '</span>');
      return '<button type="button" class="ht-item' + (c.id === _chon ? " on" : "") +
          (c.unread_count ? " unread" : "") + '" data-id="' + c.id + '">' +
        '<span class="ht-item-ic">' + (c.chat_type === "group" ? ic("users") : ic("user-round")) + '</span>' +
        '<span class="ht-item-text">' +
          '<span class="ht-item-top"><strong>' + esc(ten) + '</strong>' +
            '<small class="ht-item-time">' + esc(gio(c.last_message_at)) + '</small></span>' +
          (tags.length ? '<span class="ht-item-tags">' + tags.join("") + '</span>' : "") +
          '<span class="ht-item-sub">' + logoKenh(c.channel) +
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
    _actNote = null;
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
      var vet = JSON.stringify([d.conversation, d.messages, d.bot_silence, d.bot_running]);
      if (im && vet === _dauVetTin) return;
      _dauVetTin = vet;
      _conv = d.conversation; _msgs = d.messages || []; _silence = d.bot_silence || null; _running = !!d.bot_running;
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
        // Công tắc hai nấc thay nút Tiếp quản nhỏ (0.65.4): thấy ngay cuộc chat đang do ai lo và gạt được bằng một chạm.
        (laBot
          ? '<div class="ht-seg" role="group" aria-label="' + esc(window.t("ht.sw_aria")) + '">' +
              '<button type="button" class="ht-seg-b' + (human ? "" : " on") + '" data-m="ai" aria-pressed="' + (!human) + '">' +
                ic("bot") + ' ' + esc(window.t("ht.sw_auto")) + '</button>' +
              '<button type="button" class="ht-seg-b' + (human ? " on" : "") + '" data-m="human" aria-pressed="' + human + '">' +
                ic("hand") + ' ' + esc(window.t("ht.sw_mine")) + '</button>' +
            '</div>'
          : "") +
      '</div>' +
      '<div class="ht-msgs">' + _msgs.map(veTin).join("") + renderSilenceLine(c) + '</div>' +
      (laBot ? renderStatusLine(c, human) + renderActions(c, human, guiDuoc) : "") +
      (guiDuoc ? veCompose(c, laBot, human) :
        '<div class="ht-foot">' + esc(window.t("ht.kenh_khong_gui", { kenh: nhanKenh(c.channel) })) + '</div>');
    box.querySelector(".ht-back").onclick = dongThread;
    box.querySelectorAll(".ht-seg-b").forEach(function (b) {
      b.onclick = function () { if (b.dataset.m !== (human ? "human" : "ai")) doiMode(c.id, b.dataset.m); };
    });
    box.querySelectorAll(".ht-act").forEach(function (b) { b.onclick = function () { onAction(c, b); }; });
    var why = box.querySelector(".ht-silent-why");
    if (why) why.onclick = function () {
      if (window.JavisReplyPolicy) window.JavisReplyPolicy.openPanel({ id: c.bot_id, name: c.bot_name || "" });
    };
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

  // Một dòng nói ai đang trực cuộc chat này. Đứng riêng (không nhét vào ô nhập) để hai nút hành động ở lát sau có chỗ
  // và dòng này không bao giờ bị nút đẩy xuống hàng.
  function renderStatusLine(c, human) {
    // Bot đang tắt mà vẫn ghi "đang trực" là nói dối: khách nhắn vào sẽ không ai đáp. Nói thẳng, và chỉ cách bật.
    var off = !human && !_running;
    var key = human ? "ht.st_human" : off ? "ht.st_off" : (c.bot_name ? "ht.st_ai" : "ht.st_ai_0");
    return '<div class="ht-status ' + (human ? "human" : off ? "off" : "ai") + '">' + ic(human ? "hand" : off ? "circle-stop" : "bot") +
      ' <span>' + esc(window.t(key, { bot: c.bot_name || window.t("ht.bot") })) + '</span></div>';
  }

  // Hai nút hành động (0.65.5), cùng cao và chia đôi bề ngang: "Trả lời giúp tin này" (bot trả lời NGAY tin khách cuối, dù bộ
  // phán xử đã chọn im) và "Gợi ý câu trả lời" (bot soạn nháp vào ô nhập, chưa gửi). Chế độ Tôi trả lời thì nút thứ hai là "Trả
  // lại cho bot". Nút chưa dùng được VẪN HIỆN, chạm vào nói lý do (nút ẩn hay xám câm thì không ai biết phải làm gì để bật nó).
  function renderActions(c, human, guiDuoc) {
    var lastCustomer = !!_msgs.length && _msgs[_msgs.length - 1].sender_type === "customer";
    var hasCustomerMsg = _msgs.some(function (m) { return m.sender_type === "customer" && (m.text || "").trim(); });
    var whyAnswer = human ? "ht.why_human" : !guiDuoc ? "ht.why_nosend" : !_running ? "ht.why_off" : !lastCustomer ? "ht.why_done" : "";
    var whyDraft = !hasCustomerMsg ? "ht.why_nomsg" : !guiDuoc ? "ht.why_nosend" : "";
    function actionButton(a, icon, label, why, pri) {
      var isBusy = _actBusy === a;
      return '<button type="button" class="ht-act' + (pri ? " pri" : "") + (why ? " off" : "") + (isBusy ? " busy" : "") +
        '" data-a="' + a + '"' + (why ? ' data-why="' + why + '" aria-disabled="true"' : "") + (_actBusy ? " disabled" : "") + '>' +
        ic(isBusy ? "loader" : icon) + ' <span>' + esc(window.t(isBusy ? "ht.act_busy" : label)) + '</span></button>';
    }
    var row = human
      ? actionButton("draft", "sparkles", "ht.act_draft", whyDraft, false) + actionButton("back", "bot", "ht.act_back", "", false)
      : actionButton("answer", "zap", "ht.act_answer", whyAnswer, true) + actionButton("draft", "sparkles", "ht.act_draft", whyDraft, false);
    return '<div class="ht-acts">' + row + '</div>' +
      (_actNote ? '<div class="ht-acts-note' + (_actNote.err ? " err" : "") + '">' + ic(_actNote.err ? "triangle-alert" : "info") +
        ' <span>' + esc(_actNote.text) + '</span></div>' : "");
  }

  function setActionNote(text, err) {
    _actNote = text ? { text: text, err: !!err } : null;
    var box = _host && _host.querySelector(".ht-thread");
    var cu = box && box.querySelector(".ht-acts-note");
    if (cu) cu.parentNode.removeChild(cu);
    var acts = box && box.querySelector(".ht-acts");
    if (acts && _actNote) {
      acts.insertAdjacentHTML("afterend", '<div class="ht-acts-note' + (_actNote.err ? " err" : "") + '">' +
        ic(_actNote.err ? "triangle-alert" : "info") + ' <span>' + esc(_actNote.text) + '</span></div>');
    }
  }

  async function onAction(c, b) {
    var a = b.dataset.a;
    if (a === "back") return doiMode(c.id, "ai");
    if (b.dataset.why) return setActionNote(window.t(b.dataset.why), false);      // chưa dùng được: nói vì sao
    if (_actBusy) return;
    var box = _host.querySelector(".ht-thread");
    var ta = box && box.querySelector(".ht-compose textarea");
    if (a === "draft" && ta && ta.value.trim() && !confirm(window.t("ht.act_overwrite"))) return;
    _actBusy = a;
    setActionNote("", false);
    veThread();
    var loi = "", text = "", d = {};
    try {
      var r = await fetch("/conversations/" + c.id + "/ai-reply", { method: "POST", body: fd({ mode: a === "draft" ? "draft" : "send" }) });
      try { d = await r.json(); } catch (e) { d = {}; }
      if (!r.ok || d.ok === false) loi = (d && d.error) || window.t("cb.loi_ma", { ma: r.status });
      text = (d && d.text) || "";
    } catch (e) { loi = e.message; }
    _actBusy = "";
    _dauVetTin = "";
    await taiTin(false);
    var ta2 = _host.querySelector(".ht-thread .ht-compose textarea");
    if (loi) {
      // Không gửi được mà bot đã soạn xong: đổ vào ô nhập để chủ gửi tay, khỏi mất công soạn lại.
      if (text && ta2) { ta2.value = text; }
      setActionNote(window.t(text ? "ht.act_send_failed" : "ht.act_fail", { err: loi }), true);
      return;
    }
    if (d.silent) return setActionNote(window.t("ht.act_silent"), false);
    if (a === "draft") {
      if (ta2) { ta2.value = text; ta2.focus(); }
      return setActionNote(window.t("ht.act_drafted", { bot: c.bot_name || window.t("ht.bot") }), false);
    }
    tai(true);
    setActionNote(window.t(d.taught ? "ht.act_sent_taught" : "ht.act_sent"), false);
  }

  // "Bot im: lý do" ngay dưới tin khách cuối, lấy từ nhật ký bộ phán xử, khỏi phải mở menu Bộ phán xử để hỏi vì sao.
  function renderSilenceLine(c) {
    var s = _silence;
    if (!s || !c.bot_id) return "";
    var RP = window.JavisReplyPolicy;
    var lyDo = s.code ? (RP ? RP.codeLabel(s.code) : s.code) : (s.reason || "");
    if (!lyDo) return "";
    var diem = (s.score == null) ? "" : " (" + Number(s.score).toFixed(2) +
      (s.threshold != null ? " / " + Number(s.threshold).toFixed(2) : "") + ")";
    return '<div class="ht-silent">' + ic("info") + ' <span>' + esc(window.t("ht.silent", { why: lyDo + diem })) + '</span>' +
      (RP ? ' <button type="button" class="ht-silent-why">' + esc(window.t("ht.silent_why")) + '</button>' : "") + '</div>';
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

  // ---------------------------------------------------------------- TÀI KHOẢN BOT
  function renderKenh(body) {
    body.innerHTML =
      '<div class="ht-kenh">' +
        '<div class="ht-bar">' +
          '<p class="ht-intro ht-kenh-intro">' + esc(window.t("ht.kenh_intro2")) + '</p>' +
          '<button class="s-btn ht-them-tk" type="button">' + ic("plus") + ' ' + esc(window.t("ht.them_tk")) + '</button>' +
        '</div>' +
        // Nói THẲNG đang lọc theo brain nào. Không nói thì một danh sách ngắn đi trông hệt
        // như mất dữ liệu, và đó đúng là cái bẫy mà việc lọc này dễ tạo ra.
        '<div class="ht-tk-loc">' +
          '<span class="ht-tk-loc-txt">' + ic("brain") + ' ' +
            esc(_tkMoiBrain ? window.t("ht.tk_loc_tat_ca") : window.t("ht.tk_loc_brain", { brain: tenBrain(brain()) })) +
          '</span>' +
          '<button class="s-btn-ghost ht-tk-doi-loc" type="button">' +
            esc(_tkMoiBrain ? window.t("ht.tk_chi_brain_nay") : window.t("ht.tk_xem_moi_brain")) + '</button>' +
        '</div>' +
        '<div class="ht-acc-grid"><div class="ht-empty">' + esc(window.t("common.loading")) + '</div></div>' +
      '</div>';
    body.querySelector(".ht-them-tk").onclick = function () { moThemTK(); };
    body.querySelector(".ht-tk-doi-loc").onclick = function () {
      _tkMoiBrain = !_tkMoiBrain;
      renderKenh(body);
    };
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

  // Ô chọn brain cho tài khoản. Danh sách đổ từ CHÍNH ô chọn brain của app (#graphSource),
  // không gọi /brains riêng: `currentBrainPath()` sinh giá trị từ ô đó, nên lấy chỗ khác là
  // hai không gian khoá khác nhau và lưu xong tài khoản rơi vào một brain không ai mở được.
  function veChonBrain(sel, cur) {
    if (!sel) return;
    var ds = dsBrain();
    // Brain đang gán mà không còn trong danh sách (đã xoá, đã đổi tên): VẪN bày ra và chọn
    // sẵn, để bấm Lưu không âm thầm chuyển tài khoản sang brain khác.
    if (cur && !ds.some(function (x) { return x.v === cur; })) ds.push({ v: cur, ten: cur });
    sel.innerHTML = '<option value="">' + esc(window.t("ht.brain_chua_gan")) + '</option>' +
      ds.map(function (x) {
        return '<option value="' + esc(x.v) + '"' + (x.v === cur ? " selected" : "") + '>' + esc(x.ten) + '</option>';
      }).join("");
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
    // BRAIN hiện khi nó là thông tin MỚI, không phải lúc nào cũng hiện:
    //   - đang xem "mọi brain": mỗi thẻ phải tự nói nó thuộc về đâu;
    //   - tài khoản CHƯA gán chủ: nó hiện ở mọi brain, và đó là thứ người dùng cần biết để gắn;
    //   - bot trực nằm ở brain KHÁC chủ tài khoản: dữ liệu cũ lệch nhau, nói ra để còn sửa.
    // Lọc theo brain rồi mà thẻ nào cũng dán tên brain đang mở thì chỉ là tiếng ồn.
    var brNay = brain();
    var brTK = a.brain || "";
    var botBr = a.bot_brain || "";
    var nhanBrain = "";
    if (a.kind === "bot") {
      if (!brTK) nhanBrain = window.t("ht.tk_chua_brain");
      else if (botBr && botBr !== brTK) nhanBrain = window.t("ht.tk_bot_brain_khac", { brain: tenBrain(botBr) });
      else if (_tkMoiBrain || brTK !== brNay) nhanBrain = window.t("ht.o_brain", { brain: tenBrain(brTK) });
    }
    // Có bot trực thì thẻ nói về bot dù kênh là kiểu "account" (Zalo cá nhân gắn được bot từ 0.64.80).
    var botDong = (a.kind === "bot" || a.bot_id)
      ? (a.bot_id
          ? '<span>' + ic(a.bot_icon || "headset") + ' ' + esc(window.t("ht.tk_bot_truc")) + ' <b>' + esc(a.bot_name) + '</b>' +
            (a.bot_enabled ? "" : ' <span class="ht-warn">(' + esc(window.t("ht.bot_tat")) + ')</span>') + '</span>'
          : '<span class="ht-warn">' + ic("triangle-alert") + ' ' + esc(window.t("ht.tk_chua_bot")) + '</span>')
      : '<span>' + ic("user-round") + ' ' + esc(window.t("ht.tk_cua_ban")) + '</span>';
    if (nhanBrain) botDong += '<span class="ht-nhe">' + ic("brain") + ' ' + esc(nhanBrain) + '</span>';
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
          (!a.bot_id
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
      // Tài khoản đang có bot trực: GỠ KHỎI BOT RỒI XOÁ ngay tại đây, trong một lần hỏi.
      //
      // Bản cũ nhảy sang tab Chatbot mở form con bot ấy, và đó là ngõ cụt đúng trong trường
      // hợp hay gặp nhất: bot thuộc một brain, tài khoản kênh thì toàn cục, nên con bot đang
      // giữ tài khoản này thường nằm ở brain KHÁC brain đang mở. Tab Chatbot chỉ nạp bot của
      // brain đang mở nên không thấy nó, và người dùng nhận một câu bảo "đổi brain rồi thử
      // lại" mà không biết đổi sang brain nào (chủ repo báo 21/09).
      var hoi = a.bot_id
        ? window.t(a.bot_mot_tk ? "ht.xoa_go_bot_cuoi" : "ht.xoa_go_bot",
                   { ten: a.label, bot: a.bot_name, brain: a.bot_brain || "?" })
        : window.t("ht.xn_xoa_tk", { ten: a.label });
      if (!confirm(hoi)) return;
      try {
        var r = await api("/channels/accounts/" + encodeURIComponent(a.id) + "/delete",
                          { method: "POST", body: fd({ go_khoi_bot: a.bot_id ? "1" : "" }) });
        // Bot mất tài khoản cuối cùng thì server tắt nó đi. Nói ra, vì đó là hệ quả người
        // dùng không thấy trên màn hình này (con bot nằm ở trang khác, có khi ở brain khác).
        if (r && r.bot_tat) alert(window.t("ht.da_tat_bot", { bot: r.bot_tat }));
      } catch (e) { alert(window.t("ht.loi_doi") + " " + e.message); }
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
  // tích sẵn tài khoản vừa nối). Không truyền thì chỉ nạp lại tab Tài khoản bot như cũ.
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
          channel: chon, token: t, label: box.querySelector("#htLabel").value.trim(), bot_username: uname,
          // Thêm từ brain nào thì thuộc brain đó: tab này lọc theo brain, tài khoản vừa thêm
          // mà không gắn chủ thì nó lơ lửng ở mọi brain.
          brain: brain() }) });
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
      // Đổi brain chủ (0.62.4). Đây là lối thoát khi lỡ thêm tài khoản ở brain khác: không có
      // nó thì chỉ còn cách xoá rồi thêm lại, mà xoá là mất luôn lịch sử hội thoại của nó.
      (a.kind === "bot"
        ? '<label>' + esc(window.t("ht.lb_brain_tk")) + '</label>' +
          '<select id="htBrain"></select>' +
          '<div class="cb-hint">' + esc(window.t("ht.hint_brain_tk")) + '</div>'
        : "") +
      '<div class="ht-form-acts">' +
        '<button class="s-btn-ghost ht-close" type="button">' + esc(window.t("common.cancel")) + '</button>' +
        '<button class="s-btn ht-save" type="button">' + esc(window.t("common.save")) + '</button>' +
      '</div></div></div>');
    document.body.appendChild(box);
    var dong = function () { if (box.parentNode) box.parentNode.removeChild(box); };
    box.onmousedown = function (e) { if (e.target === box) dong(); };
    box.querySelector(".ht-close").onclick = dong;
    veChonBrain(box.querySelector("#htBrain"), a.brain || "");
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
        var oBr = box.querySelector("#htBrain");
        var than = { label: box.querySelector("#htLabel").value.trim(),
                     token: box.querySelector("#htToken").value.trim(), bot_username: uname };
        if (oBr) than.brain = oBr.value;   // không có ô (kind account) thì KHÔNG gửi = không đụng
        await api("/channels/accounts/" + encodeURIComponent(a.id) + "/update", { method: "POST", body: fd(than) });
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
