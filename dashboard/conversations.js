/* Trang Hội thoại - MỘT trang cho hộp thư khách, kênh và nhân viên AI (Chatbot V2, 0.61.0).
 *
 * Hai tab, cùng một chỗ trên thanh bên (từ 0.65.9; trước đó là ba tab Hộp thư | Kênh | Chatbot, và người dùng phải nhảy qua lại
 * giữa "thêm kênh" và "tạo bot"):
 *   - Hộp thư:  mọi tin khách từ mọi kênh (`/conversations`), đọc lại, tiếp quản, và từ 0.61.0
 *               TRẢ LỜI KHÁCH NGAY TỪ ĐÂY khi kênh có năng lực đó (`/conversations/{id}/reply`).
 *   - Bot:      nhân viên AI (chatbots.js dựng vào ô phía trên) và, ngay dưới, mục "Kênh chưa có bot": mọi tài khoản kênh chưa
 *               bot nào trực, MỘT khuôn thẻ bất kể kênh (`/channels/accounts`): bot Telegram, bot Zalo, Zalo cá nhân, và kênh
 *               thêm sau này. Kênh ĐÃ có bot hiện thành chip trên thẻ bot (bấm chip để sửa/xoá kênh đó).
 *               Từ 0.62.4 mục này LỌC THEO BRAIN đang mở: tài khoản bot thuộc về một brain, nên đứng ở brain nào chỉ thấy tài
 *               khoản của brain đó (cộng tài khoản chưa gán chủ, cộng Zalo cá nhân vì nó là kết nối toàn cục). Công tắc "mọi
 *               brain" để tìm lại một tài khoản đã gán nhầm chỗ, kể cả tài khoản đang do bot của brain khác trực.
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
      var ten = (o.dataset && (o.dataset.brainLabel || o.dataset.brainName)) || (o.textContent || "").trim().replace(/\s*·\s*\d+\+?$/, "");
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
  var TRANG = 40;           // số hội thoại một trang (0.65.11: cuộn xuống cuối thì tải trang kế, trước đó cố định 60 và không tải thêm được)
  var MAX_DONG_NHIP = 200;  // nhịp 5 giây làm mới tối đa chừng này dòng đầu; phần đã tải sâu hơn giữ nguyên
  var TIN_TRANG = 40;       // số tin một lần tải (mở hội thoại lấy 40 tin MỚI NHẤT, kéo lên thì lấy thêm 40 tin cũ hơn)
  // Chatbot v5 (2026-10-28): Hội thoại · Bot · Kênh · Thống kê. "kenh" is a tab again (the nicks and Pages, their bot,
  // A.I. per chat); the old id "chatbot" still leads to the Bot tab (console.js, notices and old bookmarks use it).
  var TABS = ["inbox", "bot", "kenh", "thongke"];
  var TAB_CU = { chatbot: "bot" };
  function chuanTab(id) { return TAB_CU[id] || id; }
  var _host = null, _timer = null, _tab = "inbox";
  var _items = [], _stats = {}, _dauVet = "";
  var _kenhLoc = "", _botLoc = "", _q = "";
  var _statusLoc = "", _typeLoc = "";   // bộ lọc (0.65.3), lưu ở trình duyệt qua JavisConvFilters
  var _contactLoc = "";     // 2026-10-25: "1" = only chats where the customer left a phone number or email
  // Chatbot v5 (2026-10-28, docs/dev/2026-10-chatbot-v5-spec.md): who is handling the chat (the quick filters), the ticked
  // channel accounts (the channel picker) and tags any/none (the Filter menu). Saved with the rest by JavisConvFilters.
  var _who = "you", _accs = [], _tagsAny = [], _tagsNone = [], _whoCounts = null;
  var _when = null, _lastBy = "", _pinned = "";   // when the last message came, who wrote it, pinned only (Filter menu)
  var _pick = false, _pickQ = "", _fm = false, _fmCat = "time";   // channel picker / Filter menu open, picker search, menu category
  var _wm = false;          // the "who" dropdown of the list is open
  // Info panel: closed until the owner opens it (owner, 2026-10-29: the chat gets the room), and remembered in this browser.
  var INFO_KEY = "javis_ib_info";
  var _info = (function () { try { return localStorage.getItem(INFO_KEY) === "1"; } catch (e) { return false; } })();
  var _msheet = false;      // the phone's "who replies" sheet is open
  var _aiBusy = "";         // "ask" | "redo" | "send" | "now" while the A.I. writes or a draft goes out
  var _draftEdit = null;    // {ts, text}: the owner's edits to the waiting draft, kept across the 5-second redraws
  var _noteEdit = null;     // {id, text}: the note being typed in the Info panel, same reason
  var _toastT = null;
  var _tags = [];           // the owner's inbox tags [{id, name, color, count}], from the list endpoint
  var _tagPop = false, _tagEdit = 0, _tagNewColor = "green", _tagErr = "";   // thread tag picker: open, tag being edited, new tag colour, last error
  var _facets = null, _botList = [];    // số đếm cho dropdown và các bot có hội thoại (server cấp, toàn hòm thư)
  var _chon = null;         // id hội thoại đang mở
  var _msgs = [], _conv = null, _dauVetTin = "", _silence = null;   // _silence: vì sao bot im ở tin khách cuối
  var _running = false;     // bot của cuộc chat đang mở có đang chạy không (server cấp)
  var _soTrang = 1, _conDS = false, _dangTaiDS = false;   // phân trang danh sách: số trang đã tải, còn trang sau không
  var _conCu = false, _dangTaiCu = false, _vetMeta = "";   // khung tin: còn tin cũ không, đang tải tin cũ, chữ ký phần đầu khung
  var _actNote = null;      // {text, err}: dòng nói kết quả của lần bấm gần nhất, sống qua các lần vẽ lại khung
  var _kenhDS = [];         // các LOẠI kênh (server: id, nhan, logo, kind, nang_luc...)
  var _tk = [];             // mọi tài khoản kênh, một khuôn
  var _dauVetTK = "";
  var _tkMoiBrain = false;  // mục Kênh chưa có bot: đang xem của MỌI brain thay vì brain đang mở
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
  // (i) button (info-tip.js, 0.214.0): explanations sit behind it; without the helper (Node tests) they draw open.
  function infoBtn() { var J = typeof window !== "undefined" && window.JavisInfo; return J ? J.btn(window.t("info.more")) : ""; }
  function infoBody(html) {
    var J = typeof window !== "undefined" && window.JavisInfo;
    return J ? J.body(html) : '<div class="info-body">' + html + "</div>";
  }
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
    if (_cho && _cho.tab && TABS.indexOf(chuanTab(_cho.tab)) >= 0) _tab = chuanTab(_cho.tab);
    host.innerHTML =
      '<div class="cview-section ht-page">' +
        // Từ 0.65.10 đầu trang chung (tiêu đề + dòng phụ đề, cao khoảng 90px) bị ẩn cho trang này: tiêu đề nằm cùng hàng với hai tab.
        '<div class="ht-top">' +
          '<div class="ht-title">' + ic("messages-square") + ' <span>' + esc(window.t("page.conversations.label")) + '</span></div>' +
          '<div class="ht-tabs"></div>' +
        '</div>' +
        '<div class="ht-tab-body"></div>' +
      '</div>';
    veTabs();
    veTab();
    nhip();
    watchTagOutside();
  }

  function veTabs() {
    var b = _host && _host.querySelector(".ht-tabs");
    if (!b) return;
    var NHAN = { inbox: ["ib.tab_inbox", "messages-square"], bot: ["ht.tab_bot", "headset"], kenh: ["ib.tab_kenh", "plug"],
                 thongke: ["ib.tab_stats", "chart-column"] };
    b.innerHTML = TABS.map(function (t) {
      // The Conversations tab counts the chats that need you (Chatbot v5), not unread ones: unread is what the A.I. already handles.
      var canBan = t === "inbox" && _whoCounts ? (_whoCounts.you_total != null ? _whoCounts.you_total : _whoCounts.you) : 0;
      // The Channels tab counts the nicks and Pages that need something (an error, or no bot and none was declined).
      if (t === "kenh" && window.JavisInboxChannels) canBan = window.JavisInboxChannels.jobs(_tk);
      var chuaDoc = canBan ? '<span class="ht-badge" title="' + esc(window.t(t === "kenh" ? "ib.kn_jobs" : "ib.who_you")) + '">' + canBan + '</span>' : "";
      // Phones show the icon only (0.397.0), so the name is also the button's tooltip and its spoken label.
      var ten = window.t(NHAN[t][0]);
      return '<button type="button" class="ht-tab' + (t === _tab ? " on" : "") + '" data-t="' + t + '"' + (t === _tab ? ' aria-current="page"' : "") +
        ' title="' + esc(ten) + '">' + ic(NHAN[t][1]) + ' <span class="ht-tab-t">' + esc(ten) + '</span>' + chuaDoc + '</button>';
    }).join("");
    b.querySelectorAll(".ht-tab").forEach(function (n) {
      n.onclick = function () { chonTab(n.dataset.t); };
    });
  }

  // `chiDatTruoc`: chỉ ghi nhớ tab để lần render tới mở đúng (console.js gọi lúc chuyển từ id
  // trang cũ "chatbots" sang trang này, trước khi trang được dựng).
  function chonTab(id, chiDatTruoc) {
    id = chuanTab(id);
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
    closeRowMenu(false);
    body.innerHTML = "";
    if (_tab === "bot") return renderBot(body);
    if (_tab === "kenh") return renderSub(body, window.JavisInboxChannels, "inbox-channels.js");
    if (_tab === "thongke") return renderSub(body, window.JavisInboxStats, "inbox-stats.js");
    return renderInbox(body);
  }

  function nhip() {
    if (_timer) clearInterval(_timer);
    _timer = setInterval(function () {
      if (!_host || !document.body.contains(_host)) { clearInterval(_timer); _timer = null; closeRowMenu(false); return; }
      if (document.hidden || document.querySelector(".ht-modal")) return;
      if (_tab === "inbox") {
        tai(true);
        if (_chon) taiTin(true);
      } else if (_tab === "kenh") {
        taiTK(true);
      }
    }, NHIP);
  }

  // Tab Bot: chatbots.js dựng danh sách bot (nó tự có nhịp riêng, tự dừng khi ô bị tháo). The nicks and Pages without a
  // bot, which used to sit under it, live on the Channels tab since Chatbot v5.
  function renderBot(body) {
    body.innerHTML = '<div class="ht-tab-bot"><div class="ht-bot-ds"></div></div>';
    var ds = body.querySelector(".ht-bot-ds");
    var fn = window.JavisChatbots && window.JavisChatbots.render;
    if (fn) { try { fn(ds); } catch (e) { ds.innerHTML = '<div class="ht-empty">' + esc(e.message) + '</div>'; } }
    else ds.innerHTML = '<div class="ht-empty">' + esc(window.t("cs.mod_not_ready", { ten: "chatbots.js" })) + '</div>';
  }

  // Channels and Stats tabs (inbox-channels.js, inbox-stats.js) draw themselves from this context: the helpers and
  // actions of this file, so a channel account is listed, edited or deleted one way only.
  function renderSub(body, mod, file) {
    if (!mod) { body.innerHTML = '<div class="ht-empty">' + esc(window.t("cs.mod_not_ready", { ten: file })) + '</div>'; return; }
    try { mod.render(body, subCtx()); } catch (e) { body.innerHTML = '<div class="ht-empty">' + esc(e.message) + '</div>'; }
  }

  function subCtx() {
    return {
      api: api, fd: fd, esc: esc, ic: ic, brain: brain, toast: toast, brainName: function () { return tenBrain(brain()); },
      logo: logoKenh, channel: kenhCua, channelName: nhanKenh, avatar: avatarHtml,
      accounts: function () { return _tk; },
      youByAcc: youByAcc,
      allBrains: function () { return _tkMoiBrain; },
      setAllBrains: function (on) { _tkMoiBrain = !!on; _dauVetTK = ""; return taiTK(false); },
      reloadAccounts: function () { _dauVetTK = ""; return Promise.all([taiTK(false), whoCounts()]).then(function () { veTabs(); }); },
      accountCard: function (a) { return theTK(a); },
      addAccount: function () { moThemTK(); },
      openBot: function (id) {
        chonTab("bot");
        try { document.dispatchEvent(new CustomEvent("javis:chatbot-open", { detail: { bot_id: id } })); } catch (e) { /* old browser */ }
      },
      // Open one chat on the Conversations tab, every filter put aside so it is surely in the list.
      openChat: function (id) { _cho = {}; _chon = id; _msgs = []; _conv = null; _dauVetTin = ""; _vetMeta = ""; chonTab("inbox"); },
      goWho: function (w) { _who = w || ""; saveFilters(); chonTab("inbox"); },
    };
  }

  // The "needs you" counts without drawing the list (Channels tab badges, after a change there).
  async function whoCounts() {
    try {
      var d = await api("/conversations?limit=1");
      if (d.who_counts) _whoCounts = d.who_counts;
    } catch (e) { /* keep the last counts */ }
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
    if (_tab === "kenh" && window.JavisInboxChannels) window.JavisInboxChannels.paint();
    veTabs();
    return true;
  }

  // ---------------------------------------------------------------- HỘP THƯ (Chatbot v5 layout, 2026-10-28)
  // Wide screens: customers | chat | Info. The list head holds the channel picker (tick several nicks and Pages), the
  // search box with the two-level Filter menu, the quick "who is handling it" filters and the active filters as chips.
  // The pure HTML builders live in inbox-v5.js; the drawing and the events are here.
  function renderInbox(body) {
    var F = window.JavisConvFilters;
    if (_cho) {
      // Opened from elsewhere (a bot card, an account card): show exactly what was pointed at, whoever handles it. The
      // saved filters are put aside so they cannot hide the chat the owner wants to see.
      _botLoc = _cho.bot_id || ""; _kenhLoc = _cho.channel || "";
      _accs = _cho.account_key ? [_cho.account_key] : [];
      _who = ""; _statusLoc = ""; _typeLoc = ""; _tagsAny = []; _tagsNone = []; _contactLoc = ""; _q = "";
      _when = null; _lastBy = ""; _pinned = "";
      _cho = null;
      saveFilters();
    } else if (F) {
      var saved = F.load();
      _botLoc = saved.bot; _statusLoc = saved.status; _typeLoc = saved.type; _kenhLoc = saved.channel; _contactLoc = saved.contact;
      _who = saved.who; _accs = saved.accs; _tagsAny = saved.tagsAny; _tagsNone = saved.tagsNone;
      _when = saved.when; _lastBy = saved.lastBy; _pinned = saved.pinned;
    }
    _pick = false; _fm = false; _wm = false;
    body.innerHTML =
      '<div class="ht-wrap ib-v5">' +
        '<div class="ht-body">' +
          '<div class="ht-listcol">' +
            // 0.397.0 (owner, 2026-10-29): the search with Filter inside it, then one row with two dropdowns, "who" on
            // the left and the channel picker on the right. Nothing wraps onto a second line in the narrow column.
            '<div class="ib-lhead">' +
              '<div class="ib-srow"><span class="ib-swrap">' + ic("search") +
                '<input class="ht-search" type="search" placeholder="' + esc(window.t("ib.search_ph")) + '" aria-label="' +
                esc(window.t("ib.search_ph")) + '">' +
                '<button type="button" class="ib-fbtn" aria-haspopup="dialog" aria-expanded="false" aria-label="' + esc(window.t("ib.f_aria")) +
                  '" title="' + esc(window.t("ib.f_aria")) + '">' + ic("sliders-horizontal") + '<span class="ib-fbtn-n" hidden></span></button></span></div>' +
              '<div class="ib-lrow">' +
                '<button type="button" class="ib-whobtn" aria-haspopup="menu" aria-expanded="false" aria-label="' +
                  esc(window.t("ib.quick_aria")) + '"></button>' +
                '<button type="button" class="ib-picker" aria-haspopup="dialog" aria-expanded="false"></button>' +
              '</div>' +
              '<div class="ib-activef"></div>' +
              '<div class="ib-pop ib-wm" role="menu" aria-label="' + esc(window.t("ib.quick_aria")) + '" hidden></div>' +
              '<div class="ib-pop ib-pk" role="dialog" aria-label="' + esc(window.t("ib.pk_aria")) + '" hidden></div>' +
              '<div class="ib-pop ib-fm" role="dialog" aria-label="' + esc(window.t("ib.f_title")) + '" hidden></div>' +
            '</div>' +
            '<div class="ht-sdt" role="status" hidden></div>' +
            '<div class="ht-list"><div class="ht-empty">' + esc(window.t("common.loading")) + '</div></div>' +
          '</div>' +
          '<div class="ht-thread"><div class="ht-empty ht-thread-empty">' + ic("messages-square") +
            '<div>' + esc(window.t("ht.chon_mot")) + '</div></div></div>' +
          '<div class="ht-info" hidden></div>' +
        '</div>' +
      '</div>';
    if (_chon) body.querySelector(".ht-wrap").classList.add("thread-on");     // a chat opened from another tab
    var s = body.querySelector(".ht-search");
    // The query lives in `_q`, which outlives this box: the inbox is rebuilt on every tab or page switch. Put it back in
    // the new box, or the list stays filtered by a search nobody can see and "clearing" the empty box does nothing
    // (owner, 2026-10-25: "1 hội thoại" stuck after searching).
    s.value = _q;
    s.oninput = function () { _q = s.value.trim(); tai(); };
    body.querySelector(".ib-picker").onclick = function () { setPop(_pick ? "" : "pick"); };
    body.querySelector(".ib-fbtn").onclick = function () { setPop(_fm ? "" : "fm"); };
    body.querySelector(".ib-whobtn").onclick = function () { setPop(_wm ? "" : "who"); };
    body.querySelector(".ib-wm").onclick = function (e) {
      var b = e.target.closest && e.target.closest(".ib-wm-o");
      if (!b) return;
      _who = b.dataset.who || "";
      setPop("");
      onFilterChange();
      focusOpener(".ib-whobtn");
    };
    body.querySelector(".ib-activef").onclick = function (e) {
      var b = e.target.closest && e.target.closest("button[data-k]");
      if (!b) return;
      dropFilter(b.dataset.k, b.dataset.v);
      onFilterChange();
    };
    var pk = body.querySelector(".ib-pk"), fm = body.querySelector(".ib-fm");
    pk.addEventListener("input", onPickInput);
    pk.addEventListener("change", onPickChange);
    pk.addEventListener("click", onPickClick);
    fm.addEventListener("change", onFmChange);
    fm.addEventListener("click", onFmClick);
    attachListResize(body);
    watchPopOutside();
    paintHead();
    taiTK(false).catch(function () {}).then(function () { paintHead(); tai(); if (_chon) taiTin(false); });
  }

  function filterState() {
    return { bot: _botLoc, status: _statusLoc, type: _typeLoc, channel: _kenhLoc, contact: _contactLoc,
             who: _who, accs: _accs, tagsAny: _tagsAny, tagsNone: _tagsNone, when: _when, lastBy: _lastBy, pinned: _pinned };
  }
  function saveFilters() { if (window.JavisConvFilters) window.JavisConvFilters.save(filterState()); }
  function onFilterChange() { saveFilters(); paintHead(); tai(); }

  function urlDanhSach(limit, offset) {
    return "/conversations?limit=" + limit + (offset ? "&offset=" + offset : "") +
      "&q=" + encodeURIComponent(_q) + (window.JavisConvFilters ? window.JavisConvFilters.query(filterState()) : "");
  }

  // The channel accounts the picker offers: the ones of the open brain (`/channels/accounts`), each with its key.
  function accList() { return _tk.filter(function (a) { return a && a.account_key; }); }
  function youByAcc() { return (_whoCounts && _whoCounts.you_by_account) || {}; }
  function logoPick(ch) { return logoKenh(ch, "20px"); }

  // The head of the list: picker summary, quick filters with counts, chips for the active filters, the Filter count.
  function paintHead() {
    var V = window.JavisInboxV5, F = window.JavisConvFilters;
    if (!_host || !V) return;
    var accs = accList();
    var sum = V.pickerSummary(accs, _accs);
    var pb = _host.querySelector(".ib-picker");
    if (pb) {
      var chans = sum.channels.length ? sum.channels : [];
      if (!chans.length) accs.forEach(function (a) { if (chans.indexOf(a.channel) < 0) chans.push(a.channel); });
      var sub = sum.one ? nhanKenh(sum.one.channel) : sum.sub;
      // One line since 0.397.0: the names behind "3 places picked" (or "every nick and Page together") are the tooltip.
      var ph = '<span class="ib-stack">' + chans.slice(0, 3).map(function (ch) { return logoKenh(ch, "18px"); }).join("") + '</span>' +
        '<span class="ib-pk-tt"><b>' + esc(sum.title) + '</b></span>' + ic("chevron-down");
      if (pb.dataset.sig !== ph) { pb.innerHTML = ph; pb.dataset.sig = ph; }
      pb.title = sub ? sum.title + ": " + sub : sum.title;
    }
    var wb = _host.querySelector(".ib-whobtn");
    if (wb) {
      var wh = V.whoButtonHtml(_who, _whoCounts, ic);
      if (wb.dataset.sig !== wh) { wb.innerHTML = wh; wb.dataset.sig = wh; }
      wb.classList.toggle("w-you", _who === "you");
    }
    var st = filterState();
    var chips = V.activeChips(st, _tags, _botList);
    if (_kenhLoc) chips.unshift({ k: "channel", v: "", text: nhanKenh(_kenhLoc) });
    var af = _host.querySelector(".ib-activef");
    if (af) af.innerHTML = chips.map(function (c) {
      return '<span class="ib-fchip"><span>' + esc(c.text) + '</span><button type="button" data-k="' + esc(c.k) + '" data-v="' + esc(c.v) +
        '" aria-label="' + esc(window.t("ib.fc_remove", { f: c.text })) + '">' + ic("x") + '</button></span>';
    }).join("");
    var n = F ? F.activeCount(st) : 0;
    var fb = _host.querySelector(".ib-fbtn");
    if (fb) {
      fb.classList.toggle("on", n > 0);
      var nn = fb.querySelector(".ib-fbtn-n");
      if (nn) { nn.textContent = String(n); nn.hidden = !n; }
    }
  }

  function dropFilter(k, v) {
    if (k === "tagsAny") _tagsAny = _tagsAny.filter(function (x) { return x !== v; });
    else if (k === "tagsNone") _tagsNone = _tagsNone.filter(function (x) { return x !== v; });
    else if (k === "type") _typeLoc = "";
    else if (k === "bot") _botLoc = "";
    else if (k === "status") _statusLoc = "";
    else if (k === "contact") _contactLoc = "";
    else if (k === "channel") _kenhLoc = "";
    else if (k === "when") _when = null;
    else if (k === "lastBy") _lastBy = "";
    else if (k === "pinned") _pinned = "";
  }

  // ---- the two popovers: channel picker and Filter menu. One open at a time; they redraw only on the owner's own
  // actions, never on the 5-second refresh, so a tick or a typed search is never lost under the cursor.
  function setPop(which) {
    if (!_host) return;
    _pick = which === "pick"; _fm = which === "fm"; _wm = which === "who";
    if (_pick) _pickQ = "";
    paintPops();
    var f = _pick ? _host.querySelector(".ib-pk .ib-pk-q") : _fm ? _host.querySelector(".ib-fm .ib-fm-cat.on") :
      _wm ? _host.querySelector(".ib-wm .ib-wm-o.on") : null;
    if (f) f.focus();
  }

  function paintPops() {
    var V = window.JavisInboxV5, F = window.JavisConvFilters;
    if (!_host || !V) return;
    var pk = _host.querySelector(".ib-pk"), fm = _host.querySelector(".ib-fm"), wm = _host.querySelector(".ib-wm");
    var pb = _host.querySelector(".ib-picker"), fb = _host.querySelector(".ib-fbtn"), wb = _host.querySelector(".ib-whobtn");
    if (pb) pb.setAttribute("aria-expanded", String(_pick));
    if (fb) fb.setAttribute("aria-expanded", String(_fm));
    if (wb) wb.setAttribute("aria-expanded", String(_wm));
    if (wm) {
      wm.hidden = !_wm;
      wm.innerHTML = _wm ? V.whoMenuHtml(_who, _whoCounts, ic) : "";
    }
    if (pk) {
      pk.hidden = !_pick;
      pk.innerHTML = _pick ? V.pickerHtml(accList(), _accs, youByAcc(), _pickQ, logoPick, nhanKenh, ic) : "";
      pk.querySelectorAll("input[data-half]").forEach(function (x) { x.indeterminate = true; });
    }
    if (fm) {
      fm.hidden = !_fm;
      fm.innerHTML = _fm ? V.filterMenuHtml(filterState(), _fmCat, _tags, _facets, _botList, ic, F ? F.tagChip : null) : "";
    }
  }

  function onPickInput(e) {
    if (!e.target.classList.contains("ib-pk-q")) return;
    _pickQ = e.target.value;
    var pos = e.target.selectionStart;
    paintPops();
    var q = _host && _host.querySelector(".ib-pk .ib-pk-q");
    if (q) { q.focus(); try { q.setSelectionRange(pos, pos); } catch (err) { /* type=search may refuse */ } }
  }

  function onPickChange(e) {
    var t = e.target;
    if (t.classList.contains("ib-pk-all")) _accs = [];
    else if (t.classList.contains("ib-pk-ch")) {
      // Ticking a channel ticks every nick or Page of it (not only the ones the search shows).
      var keys = accList().filter(function (a) { return a.channel === t.dataset.ch; }).map(function (a) { return a.account_key; });
      _accs = _accs.filter(function (k) { return keys.indexOf(k) < 0; });
      if (t.checked) _accs = _accs.concat(keys);
    } else if (t.classList.contains("ib-pk-acc")) {
      var k = t.dataset.k;
      _accs = _accs.filter(function (x) { return x !== k; });
      if (t.checked) _accs.push(k);
    } else return;
    onFilterChange();
    paintPops();
    var again = _host && _host.querySelector(t.classList.contains("ib-pk-acc") ? '.ib-pk-acc[data-k="' + t.dataset.k + '"]'
      : t.classList.contains("ib-pk-ch") ? '.ib-pk-ch[data-ch="' + t.dataset.ch + '"]' : ".ib-pk-all");
    if (again) again.focus();
  }

  function onPickClick(e) {
    var b = e.target.closest && e.target.closest("button");
    if (!b) return;
    if (b.classList.contains("ib-pk-clear")) { _accs = []; onFilterChange(); paintPops(); }
    else if (b.classList.contains("ib-pk-done")) { setPop(""); focusOpener(".ib-picker"); }
    else if (b.classList.contains("ib-pk-manage")) { setPop(""); chonTab("bot"); }
  }

  function onFmChange(e) {
    var t = e.target;
    if (t.dataset.tag != null) {
      var none = _fmCat === "tagsNone";
      var arr = (none ? _tagsNone : _tagsAny).filter(function (x) { return x !== t.dataset.tag; });
      if (t.checked) arr.push(t.dataset.tag);
      if (none) _tagsNone = arr; else _tagsAny = arr;
    } else if (t.name === "ib-type") _typeLoc = t.dataset.v;
    else if (t.name === "ib-bot") _botLoc = t.dataset.v;
    else if (t.name === "ib-st") _statusLoc = t.dataset.v;
    else if (t.classList.contains("ib-fm-contact")) _contactLoc = t.checked ? "1" : "";
    else if (t.classList.contains("ib-fm-pinned")) _pinned = t.checked ? "1" : "";
    else if (t.name === "ib-time") _when = t.dataset.v ? { preset: t.dataset.v } : null;
    else if (t.name === "ib-last") _lastBy = t.dataset.v;
    else return;
    onFilterChange();
    var sel = t.dataset.tag != null ? 'input[data-tag="' + t.dataset.tag + '"]' : t.name ? 'input[name="' + t.name + '"][data-v="' + t.dataset.v + '"]'
      : t.classList.contains("ib-fm-pinned") ? ".ib-fm-pinned" : ".ib-fm-contact";
    paintPops();
    var again = _host && _host.querySelector(".ib-fm " + sel);
    if (again) again.focus();
  }

  function onFmClick(e) {
    var b = e.target.closest && e.target.closest("button");
    if (!b) return;
    if (b.classList.contains("ib-fm-cat")) {
      _fmCat = b.dataset.cat;
      paintPops();
      var on = _host.querySelector('.ib-fm-cat[data-cat="' + _fmCat + '"]');
      if (on) on.focus();
    } else if (b.classList.contains("ib-fm-cal")) {
      // Any days on the calendar (date-range.js); the Filter menu stays open under it.
      if (window.JavisDateRange) window.JavisDateRange.open(b, _when, function (r) { _when = r; onFilterChange(); paintPops(); }, { all: true });
    } else if (b.classList.contains("ib-fm-clear")) {
      clearMenuFilters();
      paintPops();
    } else if (b.classList.contains("ib-fm-done")) { setPop(""); focusOpener(".ib-fbtn"); }
  }

  // "Clear" in the Filter menu, and the same button on an empty list the filters emptied.
  function clearMenuFilters() {
    _tagsAny = []; _tagsNone = []; _typeLoc = _botLoc = _statusLoc = _contactLoc = _lastBy = _pinned = ""; _when = null;
    onFilterChange();
  }

  function focusOpener(sel) { var b = _host && _host.querySelector(sel); if (b) b.focus(); }

  var _popOutside = false;
  function watchPopOutside() {
    if (_popOutside) return;
    _popOutside = true;
    // Crossing 1200px (a window resized, a phone turned): the Info panel follows the state kept for that width.
    try {
      var mq = window.matchMedia("(max-width: 1200px)");
      var follow = function () { if (_host && document.body.contains(_host)) paintInfo(); };
      if (mq.addEventListener) mq.addEventListener("change", follow); else if (mq.addListener) mq.addListener(follow);
    } catch (e) { /* old browser: the panel keeps its state */ }
    document.addEventListener("mousedown", function (ev) {
      if ((!_pick && !_fm && !_wm) || !_host || !document.body.contains(_host)) return;
      var t = ev.target;
      if (t.closest && (t.closest(".ib-pop") || t.closest(".ib-picker") || t.closest(".ib-fbtn") || t.closest(".ib-whobtn") ||
                        t.closest(".dr-pop"))) return;
      setPop("");
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key !== "Escape" || !_host || document.querySelector(".dr-pop")) return;
      if (_msheet) { setSheet(false); return; }
      if (!_pick && !_fm && !_wm) return;
      var from = _pick ? ".ib-picker" : _wm ? ".ib-whobtn" : ".ib-fbtn";
      setPop("");
      focusOpener(from);
    });
  }

  // Số di động Việt Nam đầy đủ (0912345678, 84912345678, +84 912 345 678), cùng luật với `conversations.chuan_hoa_sdt`: chỉ khi đó
  // server mới hỏi Zalo, nên chỉ khi đó mới hiện "Đang hỏi Zalo" (0.216.0).
  function laSdt(q) {
    var t = String(q || "").replace(/[\s.\-()]/g, "");
    return /^\+?(84[35789]\d{8}|0[35789]\d{8})$/.test(t);
  }

  // Dòng báo dưới ô tìm khi ô là một số điện thoại: số đó là Zalo của ai, chưa có cuộc chat, hay Zalo chưa trả lời được.
  // Tìm thấy và cuộc chat đang hiện trong danh sách thì không cần báo gì.
  function veSdt(pl, dangTim) {
    var el = _host && _host.querySelector(".ht-sdt");
    if (!el) return;
    var dong = [];
    if (dangTim) {
      dong.push(window.t("ht.sdt_dang_tim", { so: _q }));
    } else if (pl && pl.results && pl.results.length) {
      var co = pl.results.filter(function (x) { return x.uid; });
      co.forEach(function (x) {
        if (x.shown) return;
        dong.push(window.t(x.has_chat ? "ht.sdt_bi_loc" : "ht.sdt_chua_chat",
          { so: pl.phone, ten: x.name || window.t("ht.sdt_nguoi"), tk: x.account_label }));
      });
      pl.results.forEach(function (x) {
        if (x.error) dong.push(window.t("ht.sdt_loi", { tk: x.account_label, loi: x.error }));
      });
      if (!co.length && !pl.results.some(function (x) { return x.error; })) {
        dong.push(window.t("ht.sdt_khong_co", { so: pl.phone }));
      }
    }
    el.hidden = !dong.length;
    el.innerHTML = dong.map(function (d) { return '<div>' + ic("search") + ' ' + esc(d) + '</div>'; }).join("");
  }

  // `im` = nhịp tự động: không xoá danh sách đang hiện, mạng hỏng một nhịp thì giữ màn hình cũ.
  // Không phải nhịp (mở trang, đổi bộ lọc, gõ tìm) thì về trang đầu; nhịp thì hỏi lại đúng số dòng người dùng đã tải (tối đa MAX_DONG_NHIP).
  async function tai(im) {
    var box = _host && _host.querySelector(".ht-list");
    if (!box) return;
    if (!im) { _soTrang = 1; box.scrollTop = 0; }
    var soDong = im ? Math.min(MAX_DONG_NHIP, TRANG * _soTrang) : TRANG;
    var url = urlDanhSach(soDong, 0);
    var hoi = _q;
    if (!im) veSdt(null, laSdt(hoi));
    try {
      var d = await api(url);
      // Hỏi Zalo một số có thể mất vài giây: người dùng đã gõ tiếp thì kết quả này cũ, không được đè lên kết quả mới hơn.
      if (hoi !== _q) return;
      if (!im || d.phone_lookup) veSdt(d.phone_lookup, false);
      var dau = d.items || [];
      var duoi = im ? _items.slice(soDong) : [];       // phần đã tải sâu hơn nhịp hỏi: giữ nguyên
      _items = dau.concat(duoi);
      if (!duoi.length) _conDS = dau.length >= soDong;
      _stats = d.stats || {};
      _facets = d.facets || null;
      _botList = d.bots || [];
      if (d.who_counts) _whoCounts = d.who_counts;
      if (d.tags) _tags = d.tags;
      if (d.channels) _kenhDS = d.channels;
      var vet = JSON.stringify([_items, _stats, _facets, _botList, _conDS, _tags, _whoCounts]);
      if (im && vet === _dauVet) return;
      _dauVet = vet;
    } catch (e) {
      if (hoi !== _q) return;
      if (!im) veSdt(null, false);
      if (!im) box.innerHTML = '<div class="ht-empty">' + esc(window.t("ht.loi_tai")) + ' ' + esc(e.message) + '</div>';
      return;
    }
    paintHead();
    veDanhSach();
    veTabs();
  }

  // Tải trang kế của danh sách (cuộn tới cuối hoặc bấm Xem thêm). Trang thứ hai trở đi server chỉ trả các dòng, không tính lại số đếm.
  async function taiThem() {
    if (_dangTaiDS || !_conDS || !_host) return;
    _dangTaiDS = true;
    var nut = _host.querySelector(".ht-more-b");
    if (nut) { nut.disabled = true; nut.textContent = window.t("common.loading"); }
    try {
      var d = await api(urlDanhSach(TRANG, _items.length));
      var them = d.items || [];
      var co = {};
      _items.forEach(function (c) { co[c.id] = true; });
      _items = _items.concat(them.filter(function (c) { return !co[c.id]; }));    // có hội thoại mới chen lên đầu thì dòng bị đẩy qua trang, đừng hiện hai lần
      _soTrang++;
      _conDS = them.length >= TRANG;
      _dauVet = "";
    } catch (e) {
      if (nut) { nut.disabled = false; nut.textContent = window.t("ht.xem_them"); }
      _dangTaiDS = false;
      return;
    }
    _dangTaiDS = false;
    veDanhSach();
  }

  // The nick or Page a chat came through: the account's own name, else the label it has on the Channels list.
  function accLabel(c) {
    if (c.account_name) return c.account_name;
    var a = _tk.filter(function (x) { return x.account_key === c.channel_account_id; })[0];
    return a ? a.label || "" : "";
  }

  var EMPTY_WHO = { you: "ib.empty_you", ai: "ib.empty_ai", owner: "ib.empty_owner" };   // the list is empty under one quick filter

  // Avatar: the first letter (a group gets the group icon), with the channel's real logo in the corner (owner, 2026-10-28:
  // "kênh nào thì lấy logo kênh đấy"). In the folded strip (.ht-mini) it is all that shows, with a dot for unread.
  function avatarHtml(c, ten) {
    var ch = String(ten || "?").trim().charAt(0).toUpperCase() || "?";
    var grp = c.chat_type === "group";
    return '<span class="ht-item-ava' + (grp ? " g" : "") + '" aria-hidden="true">' + (grp ? ic("users") : esc(ch)) +
      '<span class="ib-kl">' + logoKenh(c.channel, "21px") + '</span>' +
      (c.unread_count ? '<span class="ht-item-ava-dot"></span>' : "") + '</span>';
  }

  function veDanhSach() {
    var box = _host.querySelector(".ht-list");
    if (!box) return;
    if (!_items.length) {
      closeRowMenu(false);
      var coNguon = _tk.some(function (a) { return a.ghi; });
      var loc = !!(_q || _kenhLoc || _botLoc || _accs.length || _statusLoc || _typeLoc || _tagsAny.length || _tagsNone.length || _contactLoc ||
        _when || _lastBy || _pinned);
      // Only the quick "who" filter hides everything (no chat needs you right now): say it kindly, one tap shows them all.
      if (_who && !loc && (_whoCounts ? ["you", "ai", "owner", "log"].some(function (w) { return _whoCounts[w]; }) : coNguon)) {
        box.innerHTML = '<div class="ht-empty">' + ic(_who === "you" ? "circle-check" : "messages-square") +
          '<b>' + esc(window.t(EMPTY_WHO[_who] || "ib.empty_you")) + '</b>' +
          '<button type="button" class="s-btn-ghost ib-see-all">' + esc(window.t("ib.see_all")) + '</button></div>';
        box.querySelector(".ib-see-all").onclick = function () { _who = ""; onFilterChange(); };
        return;
      }
      // The Filter menu emptied the list: one tap clears it, rather than pointing at channels.
      var menuLoc = window.JavisConvFilters.activeCount(Object.assign(filterState(), { channel: "" })) > 0;
      box.innerHTML = '<div class="ht-empty">' + ic("messages-square") +
        '<b>' + esc(loc || _who ? window.t("ht.khong_khop") : window.t("ht.chua_co")) +
          (!coNguon && !menuLoc ? infoBtn() : "") + '</b>' +
        (menuLoc ? '<button type="button" class="s-btn-ghost ib-empty-clear">' + esc(window.t("ib.f_clear")) + '</button>' :
        // Where messages come from opens from (i); the button to add an account stays visible (0.214.0).
        !coNguon ? infoBody(esc(window.t("ht.chua_co_goi_y"))) +
          '<button class="s-btn ht-mo-kenh" type="button">' + ic("plug") + ' ' + esc(window.t("ht.them_tk")) + '</button>' : "") +
        '</div>';
      var nut = box.querySelector(".ht-mo-kenh");
      if (nut) nut.onclick = function () { chonTab("kenh"); };
      var bo = box.querySelector(".ib-empty-clear");
      if (bo) bo.onclick = clearMenuFilters;
      return;
    }
    var F = window.JavisConvFilters;
    // The redraw (5-second refresh, a menu action) must not drop the keyboard focus: note which row and which control
    // held it, put it back afterwards.
    var ae = document.activeElement, keep = null;
    if (ae && box.contains(ae) && ae.closest) {
      var fr = ae.closest(".ht-item");
      if (fr) keep = { id: fr.dataset.id, sel: ae.classList.contains("ht-rmore") ? ".ht-rmore" : ae.classList.contains("ht-pin") ? ".ht-pin" : "" };
    }
    var V = window.JavisInboxV5;
    var many = _accs.length !== 1;      // several nicks or Pages in view: each row names the one it came through
    box.innerHTML = _items.map(function (c) {
      var ten = c.title || c.customer_name || c.external_chat_id;
      var pre = c.last_sender_type === "ai" ? window.t("ib.pre_ai") : c.last_sender_type === "human" ? window.t("ib.pre_you") : "";
      var who = V && V.WHO.indexOf(c.who) >= 0 ? c.who : "log";
      // The row's coloured edge says who is handling it; the hover text says it in words (Chatbot v5).
      var say = V ? V.whoLabel(who) + ": " + V.whoSentence(c) : "";
      // Nút ghim (0.223.0) là <span role=button>: cả hàng đã là một <button>, nút lồng trong nút là HTML sai.
      // Since the row menu (2026-10-25) pinning lives in "...": only a PINNED row shows its pin (click it to unpin), so
      // unpinned rows stay clean like Zalo's. The "..." is a <span role=button> for the same reason as the pin.
      // The owner's tags: two chips then "+N" (Pancake's list row), on a third line only when the chat has tags. The nick or
      // Page a chat came through is in the row's tooltip since 0.397.0 (it was a line of its own on every row), its
      // channel is the logo on the avatar.
      var userTags = (F && c.tags && c.tags.length) ? F.tagChips(c.tags, 2) : "";
      var accName = many ? accLabel(c) : "";
      return '<button type="button" class="ht-item w-' + who + (c.id === _chon ? " on" : "") +
          (c.unread_count ? " unread" : "") + (c.pinned ? " ghim" : "") + (c.hidden ? " hid" : "") +
          (_rm && _rm.id === c.id ? " menu-on" : "") + '" data-id="' + c.id + '" title="' + esc(accName ? accName + " · " + say : say) + '">' +
        avatarHtml(c, ten) +
        '<span class="ht-item-text">' +
          '<span class="ht-item-top"><strong>' + esc(ten) + '</strong>' +
            (c.contact ? '<span class="ht-has-contact" title="' + esc(window.t("ht.contact_left", { v: c.contact })) + '">' +
              ic(c.contact.indexOf("@") > 0 ? "mail" : "phone") + '</span>' : "") +
            (c.hidden ? '<span class="ht-hid-mark" title="' + esc(window.t("ht.rm_hidden_mark")) + '">' + ic("eye-off") + '</span>' : "") +
            (c.pinned ? '<span class="ht-pin on" role="button" tabindex="0" title="' + esc(window.t("proj.pin_off")) + '" aria-label="' +
              esc(window.t("proj.pin_off")) + '">' + ic("pin") + '</span>' : "") +
            '<small class="ht-item-time">' + esc(gio(c.last_message_at)) + '</small>' +
            '<span class="ht-rmore" role="button" tabindex="0" aria-haspopup="menu" aria-expanded="' + !!(_rm && _rm.id === c.id) +
              '" aria-label="' + esc(window.t("ht.rm_more", { name: ten })) + '" title="' + esc(window.t("ht.rm_more_short")) + '">' +
              ic("ellipsis") + '</span></span>' +
          '<span class="ht-item-sub">' +
            '<small>' + (pre ? '<span class="ib-pre">' + esc(pre) + ' </span>' : "") +
              esc(window.JavisHtMedia ? window.JavisHtMedia.tomTat(c.last_message || "", window.t) : (c.last_message || "")) + '</small>' +
            // Messages in the whole conversation (0.148.0), grey; the red number is only the UNREAD ones (owner, 2026-10-28:
            // v5 dropped it and he reads it to see how far a chat has gone).
            (c.message_count ? '<span class="ht-count" title="' + esc(window.t("ht.so_tin_title", { count: c.message_count })) + '">' +
              esc(window.t("sess.msgs", { count: c.message_count })) + '</span>' : "") +
            (c.unread_count ? '<span class="ht-badge" title="' + esc(window.t("ht.chua_doc_title", { count: c.unread_count })) + '">' +
              c.unread_count + '</span>' : "") +
          '</span>' +
          (userTags ? '<span class="ht-item-utags">' + userTags + '</span>' : "") +
        '</span></button>';
    }).join("") + (_conDS ? '<div class="ht-more"><button type="button" class="s-btn-ghost ht-more-b">' +
                            esc(window.t("ht.xem_them")) + '</button></div>' : "");
    box.querySelectorAll(".ht-item").forEach(function (x) {
      x.onclick = function (e) {
        if (e.target && e.target.closest && e.target.closest(".ht-pin")) { e.stopPropagation(); ghim(x); return; }
        // The "..." opens the row menu and never the conversation.
        if (e.target && e.target.closest && e.target.closest(".ht-rmore")) { e.stopPropagation(); toggleRowMenu(x, false); return; }
        mo(parseInt(x.dataset.id, 10));
      };
      var p = x.querySelector(".ht-pin");
      if (p) p.onkeydown = function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); ghim(x); }
      };
      var more = x.querySelector(".ht-rmore");
      if (more) more.onkeydown = function (e) {
        if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") { e.preventDefault(); e.stopPropagation(); toggleRowMenu(x, true); }
      };
      // Right click (and a long press, where the phone browser reports it as a context menu) opens the same menu.
      x.oncontextmenu = function (e) { e.preventDefault(); openRowMenu(x, false); };
      // Keyboard: the context-menu key or Shift+F10 on a focused row.
      x.onkeydown = function (e) {
        if (e.target === x && (e.key === "ContextMenu" || (e.shiftKey && e.key === "F10"))) { e.preventDefault(); openRowMenu(x, true); }
      };
    });
    // Còn trang sau: nút Xem thêm ở cuối, và tự tải khi cuộn gần tới đáy. Dùng sự kiện cuộn chứ không dùng IntersectionObserver: callback của
    // nó bị trình duyệt hoãn khi khung không được vẽ, còn sự kiện cuộn thì luôn tới (và kiểm thử được).
    var them = box.querySelector(".ht-more");
    if (them) them.querySelector(".ht-more-b").onclick = taiThem;
    box.onscroll = function () { if (_conDS && box.scrollHeight - box.scrollTop - box.clientHeight < 240) taiThem(); };
    if (_conDS && box.clientHeight > 0 && box.scrollHeight <= box.clientHeight + 40) taiThem();       // 40 dòng chưa đủ cao để cuộn (màn rất cao): tải tiếp; clientHeight 0 = đang ẩn, chưa đo được
    if (keep) {
      var kr = box.querySelector('.ht-item[data-id="' + keep.id + '"]');
      var kt = kr && (keep.sel ? kr.querySelector(keep.sel) : kr);
      if (kt) { try { kt.focus({ preventScroll: true }); } catch (e) { kt.focus(); } }
    }
    // An open row menu survives the redraw; its row may have left the list (hidden on another device): then it closes.
    if (_rm) { if (!rmAnchor()) closeRowMenu(false); else placeRowMenu(); }
  }

  // Ghim một cuộc chat lên đầu hòm thư (0.223.0). Server xếp cuộc đã ghim trước, nên chỉ cần tải lại danh sách.
  async function ghim(x) {
    var id = parseInt(x.dataset.id, 10);
    var c = _items.filter(function (k) { return k.id === id; })[0];
    if (!c) return;
    try {
      await api("/conversations/" + id + "/pin", { method: "POST", body: fd({ pinned: c.pinned ? "0" : "1" }) });
    } catch (e) { return; }
    tai(true);
  }

  // ---------------------------------------------------------------- the "..." menu of a row (2026-10-25)
  // Owner, from Zalo's row menu: mark unread/read, pin/unpin, tags, who replies (bot or me), hide/unhide, and copy the
  // phone or email the customer left, all without opening the chat. Desktop: a small menu anchored under the row's
  // "..."; phones (<= 640px): a bottom sheet with large rows. One element on <body>, so the list's own scrolling does not
  // clip it and the 5-second refresh, which redraws the rows, never closes it (the row keeps .menu-on across redraws).
  // What the menu offers is pure data in conversations-filters.js (rowMenuItems / rowMenuHtml / tagMenuHtml).
  var _rm = null;           // open menu: {id, view: "main" | "tags" | "copy", done, err, kb}
  var PHONE_MQ = "(max-width: 640px)";
  function isPhone() { try { return window.matchMedia(PHONE_MQ).matches; } catch (e) { return false; } }
  function rmItem(id) { return _items.filter(function (k) { return k.id === id; })[0] || (_conv && _conv.id === id ? _conv : null); }
  function rmEl() { return document.getElementById("htRowMenu"); }
  function rmAnchor() {
    var row = _host && _rm && _host.querySelector('.ht-item[data-id="' + _rm.id + '"]');
    return row ? (row.querySelector(".ht-rmore") || row) : null;
  }

  function toggleRowMenu(row, kb) {
    var id = parseInt(row.dataset.id, 10);
    if (_rm && _rm.id === id) return closeRowMenu(true);
    openRowMenu(row, kb);
  }

  function openRowMenu(row, kb) {
    var id = parseInt(row.dataset.id, 10);
    if (!rmItem(id)) return;
    closeRowMenu(false);
    _rm = { id: id, view: "main", done: "", err: "", kb: !!kb };
    markRowMenu();
    paintRowMenu(true);
    watchRowMenuOutside();
  }

  // `refocus`: put the keyboard back on the row's "..." (Escape, or the "..." clicked again).
  function closeRowMenu(refocus) {
    var m = rmEl(), bg = document.getElementById("htRowMenuBg");
    if (m) m.parentNode.removeChild(m);
    if (bg) bg.parentNode.removeChild(bg);
    if (!_rm) return;
    var a = refocus ? rmAnchor() : null;
    _rm = null;
    markRowMenu();
    if (a && a.focus) a.focus();
  }

  // The open row keeps its "..." showing (and its time hidden) while the menu is open.
  function markRowMenu() {
    if (!_host) return;
    _host.querySelectorAll(".ht-item").forEach(function (x) {
      var on = !!(_rm && String(_rm.id) === x.dataset.id);
      x.classList.toggle("menu-on", on);
      var b = x.querySelector(".ht-rmore");
      if (b) b.setAttribute("aria-expanded", String(on));
    });
  }

  function paintRowMenu(focusFirst) {
    var F = window.JavisConvFilters, c = _rm && rmItem(_rm.id);
    if (!F || !c) return closeRowMenu(false);
    var phone = isPhone();
    var m = rmEl();
    if (!m) {
      m = document.createElement("div");
      m.id = "htRowMenu";
      m.addEventListener("click", onRowMenuClick);
      m.addEventListener("keydown", onRowMenuKey);
      document.body.appendChild(m);
    }
    if (phone && !document.getElementById("htRowMenuBg")) {
      var bg = document.createElement("div");
      bg.id = "htRowMenuBg";
      bg.className = "ht-rsheet-bg";
      bg.onclick = function () { closeRowMenu(false); };
      document.body.insertBefore(bg, m);
    }
    var ten = c.title || c.customer_name || c.external_chat_id || "";
    var body;
    if (_rm.view === "tags") body = F.tagMenuHtml(_tags, c.tags || [], ic);
    else if (_rm.view === "copy") {
      // No clipboard access (plain http on a VPS address): show the value selected, ready to copy by hand.
      body = '<div class="ht-rm-copy"><div>' + esc(window.t("ht.rm_copy_manual")) + '</div>' +
        '<input class="ht-rm-copyval" readonly value="' + esc(c.contact || "") + '" aria-label="' + esc(window.t(String(c.contact || "").indexOf("@") > 0 ? "ht.rm_copy_email" : "ht.rm_copy_phone")) + '"></div>';
    } else body = F.rowMenuHtml(F.rowMenuItems(c), ic, _rm.done);
    m.className = "ht-rmenu" + (phone ? " ht-rsheet" : "");
    m.setAttribute("role", "menu");
    m.setAttribute("aria-label", window.t("ht.rm_menu", { name: ten }));
    m.innerHTML = (phone ? '<div class="ht-rsheet-h"><span class="ht-rsheet-grip" aria-hidden="true"></span><b>' + esc(ten) + '</b></div>' : "") +
      body + (_rm.err ? '<div class="ht-rm-err" role="alert">' + ic("triangle-alert") + ' <span>' + esc(_rm.err) + '</span></div>' : "");
    placeRowMenu();
    var cv = m.querySelector(".ht-rm-copyval");
    if (cv) { cv.focus(); cv.select(); return; }
    if (focusFirst) {
      var first = m.querySelector(".ht-rm-it");
      // A mouse click leaves the focus where it is (no ring on the first row); keyboard and phones move into the menu.
      if (first && (_rm.kb || phone)) first.focus();
      else if (m.focus) { m.tabIndex = -1; m.focus(); }
    }
  }

  // Desktop: under the "...", right edges aligned; flips above when there is no room below; always inside the window.
  function placeRowMenu() {
    var m = rmEl();
    if (!m || !_rm) return;
    if (m.classList.contains("ht-rsheet")) { m.style.left = m.style.top = ""; return; }
    var a = rmAnchor();
    if (!a) return;
    var r = a.getBoundingClientRect(), vw = window.innerWidth, vh = window.innerHeight;
    var w = m.offsetWidth, h = m.offsetHeight;
    var left = Math.max(8, Math.min(r.right - w, vw - w - 8));
    var top = r.bottom + 4;
    if (top + h > vh - 8 && r.top - h - 4 >= 8) top = r.top - h - 4;
    top = Math.max(8, Math.min(top, vh - h - 8));
    m.style.left = left + "px";
    m.style.top = top + "px";
  }

  var _rmOutside = false;
  function watchRowMenuOutside() {
    if (_rmOutside) return;
    _rmOutside = true;
    document.addEventListener("mousedown", function (ev) {
      if (!_rm) return;
      var m = rmEl();
      if (m && m.contains(ev.target)) return;
      // The same row's "..." toggles it shut through its own click.
      var more = ev.target.closest && ev.target.closest(".ht-rmore");
      if (more && more.closest(".ht-item") && more.closest(".ht-item").dataset.id === String(_rm.id)) return;
      if (ev.target.id === "htRowMenuBg") return;
      closeRowMenu(false);
    }, true);
    // The list scrolls under a desktop menu: keep it on its row. A resize may switch between menu and sheet.
    document.addEventListener("scroll", function () { if (_rm) placeRowMenu(); }, true);
    window.addEventListener("resize", function () { if (_rm) paintRowMenu(false); });
  }

  function onRowMenuKey(e) {
    var m = rmEl();
    if (!m) return;
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); return closeRowMenu(true); }
    if (e.key === "Tab") { closeRowMenu(false); return; }
    var its = [].slice.call(m.querySelectorAll(".ht-rm-it"));
    if (!its.length) return;
    var i = its.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); its[(i + 1) % its.length].focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); its[(i - 1 + its.length) % its.length].focus(); }
    else if (e.key === "Home") { e.preventDefault(); its[0].focus(); }
    else if (e.key === "End") { e.preventDefault(); its[its.length - 1].focus(); }
    else if (e.key === "ArrowRight" && document.activeElement && document.activeElement.dataset.act === "tags") { e.preventDefault(); document.activeElement.click(); }
    else if (e.key === "ArrowLeft" && _rm && _rm.view === "tags") { e.preventDefault(); _rm.view = "main"; _rm.kb = true; paintRowMenu(true); }
  }

  function onRowMenuClick(e) {
    var b = e.target.closest && e.target.closest(".ht-rm-it");
    if (!b || !_rm) return;
    e.stopPropagation();
    var act = b.dataset.act, id = _rm.id;
    _rm.err = "";
    if (act === "tags") { _rm.view = "tags"; _rm.kb = true; return paintRowMenu(true); }
    if (act === "back") { _rm.view = "main"; _rm.kb = true; return paintRowMenu(true); }
    if (act === "tag") return menuToggleTag(id, parseInt(b.dataset.tag, 10), b);
    if (act === "tag_new") return menuNewTag(id);
    if (act === "copy") return menuCopy(id);
    runRowAction(id, act);
  }

  function menuFail(id, err) {
    if (!_rm || _rm.id !== id) return;
    _rm.err = window.t("ht.rm_err", { err: err });
    paintRowMenu(false);
  }

  // Every change updates the row in place first (no flicker), then the list reloads quietly for order and counts.
  async function runRowAction(id, act) {
    var c = rmItem(id);
    if (!c) return closeRowMenu(false);
    try {
      if (act === "read") {
        await api("/conversations/" + id + "/read", { method: "POST" });
        c.unread_count = 0;
      } else if (act === "unread") {
        await api("/conversations/" + id + "/unread", { method: "POST" });
        c.unread_count = Math.max(1, c.unread_count || 0);
      } else if (act === "pin" || act === "unpin") {
        await api("/conversations/" + id + "/pin", { method: "POST", body: fd({ pinned: act === "pin" ? "1" : "0" }) });
        c.pinned = act === "pin" ? 1 : 0;
      } else if (act === "hide" || act === "unhide") {
        await api("/conversations/" + id + "/hide", { method: "POST", body: fd({ hidden: act === "hide" ? "1" : "0" }) });
        c.hidden = act === "hide" ? 1 : 0;
        // Leaves the list it no longer belongs to: hidden out of the normal list, unhidden out of the "Hidden" filter.
        // A search shows both, so there the row stays and only its eye mark changes.
        if (!_q) _items = _items.filter(function (k) { return k.id !== id || (_statusLoc === "hidden") === !!k.hidden; });
      } else if (act === "mode_ai" || act === "mode_draft" || act === "mode_human") {
        var mode = act.slice(5);
        if (modeOf(c) === mode) return closeRowMenu(true);
        await api("/conversations/" + id + "/mode", { method: "POST", body: fd({ mode: mode }) });
        c.mode = mode;
        if (_conv && _conv.id === id) { _conv.mode = mode; _dauVetTin = ""; taiTin(false); }
      } else return;
    } catch (e) { return menuFail(id, e.message); }
    closeRowMenu(!!(_rm && _rm.kb));       // keyboard users land back on the row's "..."
    _dauVet = "";
    veDanhSach();
    tai(true);
  }

  async function menuToggleTag(convId, tagId, btn) {
    var c = rmItem(convId);
    if (!c || !tagId) return;
    var on = !(c.tags || []).some(function (g) { return g.id === tagId; });
    try {
      var d = await api("/conversations/" + convId + "/tags", { method: "POST", body: fd({ tag_id: tagId, on: on ? "1" : "0" }) });
      _items.forEach(function (it) { if (it.id === convId) it.tags = d.tags || []; });
      if (_conv && _conv.id === convId) { _conv.tags = d.tags || []; _vetMeta = metaSig(); veTagRow(); }
    } catch (e) { return menuFail(convId, e.message); }
    // Several tags in a row: the menu stays open on the same row, keyboard focus too.
    if (_rm && _rm.id === convId) {
      var tag = btn && btn.dataset.tag;
      paintRowMenu(false);
      var again = tag && rmEl() && rmEl().querySelector('.ht-rm-tag[data-tag="' + tag + '"]');
      if (again) again.focus();
    }
    _dauVet = "";
    veDanhSach();
    tai(true);
  }

  // New tags are made in the conversation's own Tag picker (name + colour): open the chat with the picker showing.
  async function menuNewTag(convId) {
    closeRowMenu(false);
    await mo(convId);
    _tagPop = true; _tagEdit = 0; _tagErr = "";
    if (!infoOpen()) setInfo(true);
    veTagRow();
    var n = _host && _host.querySelector(".ht-tagpop-nname");
    if (n) n.focus();
  }

  // Clipboard API first (needs https or localhost), then the old select + execCommand path, then the value shown
  // selected so it can be copied by hand.
  async function copyText(text) {
    try {
      if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; }
    } catch (e) { /* fall through */ }
    try {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.cssText = "position:fixed;top:0;left:0;opacity:0;font-size:16px;";
      document.body.appendChild(ta);
      ta.select();
      ta.setSelectionRange(0, text.length);
      var ok = !!(document.execCommand && document.execCommand("copy"));
      document.body.removeChild(ta);
      return ok;
    } catch (e) { return false; }
  }

  async function menuCopy(id) {
    var c = rmItem(id);
    if (!c || !c.contact) return;
    var ok = await copyText(String(c.contact));
    if (!_rm || _rm.id !== id) return;
    if (!ok) { _rm.view = "copy"; return paintRowMenu(false); }
    _rm.done = "copy";
    paintRowMenu(false);
    var b = rmEl() && rmEl().querySelector('.ht-rm-it[data-act="copy"]');
    if (b) b.focus();
    setTimeout(function () { if (_rm && _rm.id === id && _rm.done === "copy") closeRowMenu(true); }, 1100);
  }

  // ---------------------------------------------------------------- một hội thoại
  async function mo(id) {
    closeRowMenu(false);
    if (id !== _chon) { _tagPop = false; _tagEdit = 0; _tagErr = ""; _draftEdit = null; _noteEdit = null; _msheet = false; }
    _chon = id;
    _dauVetTin = "";
    _actNote = null;
    _msgs = []; _conCu = false; _dangTaiCu = false; _vetMeta = "";       // hội thoại khác: tải lại từ tin mới nhất
    _host.querySelector(".ht-wrap").classList.add("thread-on");
    veDanhSach();
    // Read first: an opened chat leaves "Needs you" (owner, 2026-10-28), so the bar above it must not still say it.
    try { await api("/conversations/" + id + "/read", { method: "POST" }); } catch (e) {}
    await taiTin(false);
    tai(true);
  }

  function dongThread() {
    _chon = null;
    _msgs = [];
    _infoN = false; _msheet = false;
    var w = _host.querySelector(".ht-wrap");
    if (w) w.classList.remove("thread-on");
    var th = _host.querySelector(".ht-thread");
    if (th) th.innerHTML = '<div class="ht-empty ht-thread-empty">' +
      ic("messages-square") + '<div>' + esc(window.t("ht.chon_mot")) + '</div></div>';
    paintInfo();
    veDanhSach();
  }

  async function taiTin(im) {
    if (!_chon) return;
    var id = _chon;
    var box = _host.querySelector(".ht-thread");
    if (!box) return;
    // Chưa có tin nào thì lấy 40 tin MỚI NHẤT; đã có thì chỉ hỏi các tin mới hơn tin cuối (nhịp 5 giây trước đây tải lại cả 200 tin rồi
    // vẽ lại toàn bộ khung, và kéo người đang đọc tin cũ về đầu mỗi khi có tin mới).
    var dau = !_msgs.length;
    var moi = [];
    try {
      var d = await api("/conversations/" + id + "/messages?" +
                        (dau ? "limit=" + TIN_TRANG : "after=" + _msgs[_msgs.length - 1].id + "&limit=200"));
      if (_chon !== id) return;
      _conv = d.conversation; _silence = d.bot_silence || null; _running = !!d.bot_running;
      if (dau) { _msgs = d.messages || []; _conCu = !!d.has_more; }
      else {
        // Hai lượt hỏi chồng nhau (nhịp và một hành động) có thể cùng nhận một tin: chỉ nhận tin mới hơn tin cuối THẬT lúc này.
        var cuoi = _msgs.length ? _msgs[_msgs.length - 1].id : 0;
        moi = (d.messages || []).filter(function (m) { return m.id > cuoi; });
        _msgs = _msgs.concat(moi);
      }
    } catch (e) {
      if (!im && dau) box.innerHTML = '<div class="ht-empty">' + esc(window.t("ht.loi_tai")) + ' ' + esc(e.message) + '</div>';
      return;
    }
    // Phần đầu khung (tên, công tắc, dòng trạng thái, nút hành động, lý do bot im) chỉ vẽ lại khi thứ nó phụ thuộc đổi, hoặc khi người gọi
    // đặt `_dauVetTin = ""` để ép vẽ lại. Còn lại chỉ chèn tin mới vào cuối.
    var sig = metaSig();
    if (dau || !_dauVetTin || sig !== _vetMeta || !box.querySelector(".ht-msgs")) {
      _vetMeta = sig; _dauVetTin = "x";
      veThread();
      return;
    }
    if (moi.length) chenTin(moi);
  }

  // Chữ ký của mọi thứ ngoài danh sách tin mà phần đầu khung dựa vào. Tin cuối do ai gửi cũng nằm đây vì nó bật/tắt nút "Trả lời giúp tin này".
  function metaSig() {
    var c = _conv || {}, u = _msgs[_msgs.length - 1] || {};
    return JSON.stringify([c.id, c.mode, c.bot_id, c.bot_name, c.title, c.customer_name, c.channel, c.chat_type, c.account_name,
      c.tags || [], c.contact || "", c.note || "", c.who, c.who_code, c.ai_allowed, c.ai_pending, c.draft || null, c.reply_when,
      c.yield_min, _silence, _running, u.sender_type]);
  }

  // Chèn tin mới vào cuối khung, trước dòng "Bot im" nếu có. Đang ở đáy thì trượt theo tin mới; đang đọc tin cũ thì đứng yên.
  function chenTin(moi) {
    var m = _host && _host.querySelector(".ht-thread .ht-msgs");
    if (!m) return veThread();
    var oDay = m.scrollHeight - m.scrollTop - m.clientHeight < 80;
    var html = moi.map(veTin).join("");
    var sil = m.querySelector(".ht-silent");
    if (sil) sil.insertAdjacentHTML("beforebegin", html); else m.insertAdjacentHTML("beforeend", html);
    if (oDay) m.scrollTop = m.scrollHeight;
  }

  function nutTinCu() {
    return _conCu ? '<button type="button" class="ht-older">' + esc(window.t("ht.tin_cu")) + '</button>' : "";
  }

  // Kéo lên gần đầu khung (hoặc bấm nút) thì tải 40 tin cũ hơn và chèn lên đầu. Giữ chỗ đang đọc bằng cách đo theo ĐÁY khung
  // (scrollHeight - scrollTop): phần chèn nằm phía trên nên scrollTop cũ trỏ vào một chỗ khác hẳn (cùng bẫy đã ghi ở khung chat chính).
  async function taiCu() {
    if (_dangTaiCu || !_conCu || !_chon || !_msgs.length || !_host) return;
    var id = _chon;
    var m = _host.querySelector(".ht-thread .ht-msgs");
    if (!m) return;
    _dangTaiCu = true;
    var nut = m.querySelector(".ht-older");
    if (nut) { nut.disabled = true; nut.classList.add("busy"); nut.textContent = window.t("common.loading"); }
    var tiep = false;
    try {
      var d = await api("/conversations/" + id + "/messages?before=" + _msgs[0].id + "&limit=" + TIN_TRANG);
      if (_chon !== id) { _dangTaiCu = false; return; }
      var cu = d.messages || [];
      _conCu = !!d.has_more && cu.length > 0;
      var m2 = _host.querySelector(".ht-thread .ht-msgs");
      if (cu.length && m2) {
        _msgs = cu.concat(_msgs);
        var tuDay = m2.scrollHeight - m2.scrollTop;
        var cuNut = m2.querySelector(".ht-older");
        if (cuNut) cuNut.parentNode.removeChild(cuNut);
        m2.insertAdjacentHTML("afterbegin", nutTinCu() + cu.map(veTin).join(""));
        m2.scrollTop = m2.scrollHeight - tuDay;
        noiTinCu(m2);
        tiep = _conCu && m2.clientHeight > 0 && m2.scrollHeight <= m2.clientHeight + 40;      // tin ngắn chưa đủ cao để cuộn: tải tiếp cho tới khi cuộn được
      } else if (nut) {
        nut.disabled = false; nut.classList.remove("busy"); nut.textContent = window.t("ht.tin_cu");
      }
    } catch (e) {
      if (nut) { nut.disabled = false; nut.classList.remove("busy"); nut.textContent = window.t("ht.tin_cu"); }
    }
    _dangTaiCu = false;
    if (tiep) taiCu();
  }

  function noiTinCu(m) {
    var nut = m.querySelector(".ht-older");
    if (nut) nut.onclick = taiCu;
  }

  function modeOf(c) { return c && c.mode === "human" ? "human" : c && c.mode === "draft" ? "draft" : "ai"; }

  // The chat column (Chatbot v5): head with the Info button, the "Who replies" bar in the colour of who is handling the
  // chat (three modes when the A.I. may answer here, "Let the A.I. answer here" when not, Allow / Dismiss when someone
  // called it in a chat not allowed yet) plus one sentence about what is going on, the messages, then the draft box
  // and the composer with "A.I. reply" next to Send.
  function veThread() {
    var box = _host.querySelector(".ht-thread");
    if (!box) return;
    var V = window.JavisInboxV5;
    var c = _conv || {};
    var ten = c.title || c.customer_name || c.external_chat_id;
    var guiDuoc = nangLuc(c.channel, "tra_loi_tu_javis");
    var cuon = box.querySelector(".ht-msgs");
    var oDay = !cuon || (cuon.scrollHeight - cuon.scrollTop - cuon.clientHeight < 80);
    var tuDay = cuon ? cuon.scrollHeight - cuon.scrollTop : 0;      // đang đọc giữa chừng thì vẽ lại xong phải đứng đúng chỗ cũ (đo theo đáy)
    // Giữ chữ đang gõ dở (và chỗ con trỏ) khi nhịp tự làm mới vẽ lại khung.
    var oCu = box.querySelector(".ib-cin textarea");
    var nhapDo = oCu ? oCu.value : "", goDo = !!(oCu && document.activeElement === oCu);
    var dCu = box.querySelector(".ib-draft-t"), suaDo = !!(dCu && document.activeElement === dCu);
    var who = V && V.WHO.indexOf(c.who) >= 0 ? c.who : "log";
    var bar = V ? V.modeBarHtml(c, ic) : "";
    var threeModes = !!(c.bot_id && c.ai_allowed);
    var say = V ? V.whoLabel(who) + ": " + V.whoSentence(c) : "";
    // 0.397.0 (owner, 2026-10-29): when the A.I. may answer here the three modes sit in the head (a chip opening a sheet
    // on a narrow column) and the coloured bar under it only shows when the chat needs the owner. Otherwise the bar
    // carries what can be done (Allow, Let the A.I. answer here, Create an A.I.) as before.
    var calm = threeModes && who !== "you";
    var F = window.JavisConvFilters;
    var tags = F && c.tags && c.tags.length ? F.tagChips(c.tags, 3) : "";
    var item = _items.filter(function (k) { return k.id === c.id; })[0] || {};
    var soTin = Number(c.message_count || item.message_count) || 0;
    box.innerHTML =
      '<div class="ht-head">' +
        '<button type="button" class="s-btn-ghost ht-back" aria-label="' + esc(window.t("ib.back")) + '">' + ic("arrow-left") + '</button>' +
        avatarHtml(c, ten) +
        '<div class="ht-head-text"><span class="ib-hname"><strong>' + esc(ten) + '</strong>' +
          '<span class="ib-htags">' + tags + '<button type="button" class="ib-htag-add" aria-label="' + esc(window.t("ht.tag_title")) + '">' +
            ic("plus") + '<span>' + esc(window.t("ht.tag_btn")) + '</span></button></span></span>' +
          '<small>' + chipKenh(c.channel) + (accLabel(c) ? ' · ' + esc(accLabel(c)) : "") +
          (c.chat_type === "group" ? ' · ' + esc(window.t("ht.nhom")) : "") +
          (soTin ? ' · ' + esc(window.t("sess.msgs", { count: soTin })) : "") + '</small></div>' +
        (threeModes ? '<span class="ib-hmode" title="' + esc(say) + '">' + bar + '</span>' + (V ? V.modeChipHtml(c, ic) : "") : "") +
        '<button type="button" class="s-btn-ghost ib-info-btn" aria-expanded="' + infoOpen() + '" aria-label="' + esc(window.t("ib.info_t")) +
          '" title="' + esc(window.t("ib.info_t")) + '">' + ic("info") + '</button>' +
      '</div>' +
      '<div class="ib-aibar w-' + who + '"' + (calm ? " hidden" : "") + '>' +
        '<span class="ib-say"><span class="ib-dot w-' + who + '"></span><span><b>' + esc(V ? V.whoLabel(who) : "") + ':</b> ' +
          esc(V ? V.whoSentence(c) : "") + '</span></span>' +
        (threeModes ? (c.mode === "human" ? '<button type="button" class="ib-link ib-back-ai">' + esc(window.t("ib.back_ai")) + '</button>' : "") : bar) +
      '</div>' +
      '<div class="ht-msgs">' + nutTinCu() + _msgs.map(veTin).join("") + renderSilenceLine(c) + '</div>' +
      (guiDuoc ? veCompose(c) : '<div class="ht-foot">' + esc(window.t("ht.kenh_khong_gui", { kenh: nhanKenh(c.channel) })) + '</div>') +
      '<div class="ib-msheet"' + (_msheet && threeModes ? "" : " hidden") + '>' + (_msheet && threeModes && V ? V.modeSheetHtml(c, ic) : "") + '</div>';
    box.querySelector(".ht-back").onclick = dongThread;
    box.querySelector(".ib-info-btn").onclick = function () { setInfo(!infoOpen()); };
    box.querySelector(".ib-htag-add").onclick = function () { _tagPop = true; _tagEdit = 0; _tagErr = ""; setInfo(true); };
    var chip = box.querySelector(".ib-mchip");
    if (chip) chip.onclick = function () { setSheet(true); };
    box.querySelector(".ib-msheet").onclick = function (e) {
      var b = e.target.closest && e.target.closest("[data-close], .ib-mso, .ib-mso-info");
      if (!b) return;
      setSheet(false);
      if (b.classList.contains("ib-mso")) setWho(c, b.dataset.m);
      else if (b.classList.contains("ib-mso-info")) setInfo(true);
    };
    box.querySelectorAll(".ib-m").forEach(function (b) {
      b.onclick = function () { setWho(c, b.dataset.m); };
    });
    box.querySelectorAll(".ib-allow").forEach(function (b) {
      b.onclick = function () { setWho(c, b.dataset.on === "1" ? modeOf(c) : "off", b.dataset.on !== "1" && !!c.ai_pending); };
    });
    var back = box.querySelector(".ib-back-ai");
    if (back) back.onclick = function () { setWho(c, "ai"); };
    var mk = box.querySelector(".ib-make-bot");
    if (mk) mk.onclick = function () { makeBot(c); };
    var why = box.querySelector(".ht-silent-why");
    if (why) why.onclick = function () {
      if (window.JavisReplyPolicy) window.JavisReplyPolicy.openPanel({ id: c.bot_id, name: c.bot_name || "" });
    };
    var now = box.querySelector(".ib-silent-ask");
    if (now) now.onclick = function () { askNow(c); };
    var m = box.querySelector(".ht-msgs");
    if (oDay) m.scrollTop = m.scrollHeight;
    else if (cuon) m.scrollTop = m.scrollHeight - tuDay;
    noiTinCu(m);
    m.onscroll = function () { if (_conCu && m.scrollTop < 120) taiCu(); };
    if (_conCu && m.clientHeight > 0 && m.scrollHeight <= m.clientHeight + 40) taiCu();      // 40 tin ngắn chưa đủ cao để cuộn thì kéo thêm tin cũ cho tới khi cuộn được
    var dt = box.querySelector(".ib-draft-t");
    if (dt) {
      var dr = c.draft || {};
      if (_draftEdit && _draftEdit.ts === dr.ts) dt.value = _draftEdit.text;
      dt.oninput = function () { _draftEdit = { ts: dr.ts, text: dt.value }; };
      if (suaDo) dt.focus();
      box.querySelector(".ib-dr-drop").onclick = function () { dropDraft(c); };
      box.querySelector(".ib-dr-redo").onclick = function () { aiReply(c, dr.instruction || "", "redo"); };
      box.querySelector(".ib-dr-send").onclick = function () { sendDraft(c); };
    }
    var ta = box.querySelector(".ib-cin textarea");
    if (ta) {
      ta.value = nhapDo;
      if (goDo) { ta.focus(); try { ta.setSelectionRange(nhapDo.length, nhapDo.length); } catch (e) { /* ignore */ } }
      // Same Enter rule as the main chat (JavisActs.enterSends, owner 2026-10-29): on a phone Enter is a new line and the
      // Send button sends; on a computer Enter sends and Shift+Enter is a new line; an IME composition never sends.
      var A = window.JavisActs, soan = A ? A.trackComposition(ta) : function () { return false; };
      ta.onkeydown = function (e) {
        var send = A ? A.enterSends(e, soan()) : e.key === "Enter" && !e.shiftKey && !e.isComposing;
        if (send) { e.preventDefault(); gui(c); }
      };
      // The box is one line and grows with what is typed (up to the CSS max-height), instead of a resize handle.
      var grow = function () { ta.style.height = "auto"; ta.style.height = ta.scrollHeight + "px"; };
      ta.oninput = grow;
      if (nhapDo) grow();
      box.querySelector(".ht-send").onclick = function () { gui(c); };
      var ask = box.querySelector(".ib-ask");
      if (ask) ask.onclick = function () { aiReply(c, ta.value.trim(), "ask"); };
    }
    paintInfo();
  }

  // The phone's "who replies" sheet: drawn inside the chat column, so the 5-second redraw keeps it as it is.
  function setSheet(on) {
    _msheet = !!on;
    var V = window.JavisInboxV5, sh = _host && _host.querySelector(".ht-thread .ib-msheet");
    if (!sh || !V) return;
    sh.hidden = !_msheet;
    sh.innerHTML = _msheet ? V.modeSheetHtml(_conv || {}, ic) : "";
    var f = _msheet ? sh.querySelector(".ib-mso.on") : _host.querySelector(".ib-mchip");
    if (f) f.focus();
  }

  // ---------------------------------------------------------------- Info panel (Chatbot v5)
  // The customer (contact, tags, the owner's note), "A.I. in this chat" (who replies; in a group when the A.I. speaks up;
  // how long it waits after you type), and the channel. Every field is a dropdown; a change shows a toast with Undo.
  function narrow() { try { return window.matchMedia("(max-width: 1200px)").matches; } catch (e) { return false; } }
  // Wide screens keep the owner's choice in this browser; on a narrow one the panel covers the chat, so it opens only
  // when asked and closes when the chat does.
  var _infoN = false;
  function infoOpen() { return narrow() ? _infoN : _info; }
  function setInfo(on) {
    if (narrow()) _infoN = !!on;
    else {
      _info = !!on;
      try { localStorage.setItem(INFO_KEY, _info ? "1" : "0"); } catch (e) { /* private mode: this visit only */ }
    }
    var b = _host && _host.querySelector(".ib-info-btn");
    if (b) b.setAttribute("aria-expanded", String(infoOpen()));
    paintInfo();
    if (infoOpen()) { var x = _host && _host.querySelector(".ht-info .ib-x"); if (x && narrow()) x.focus(); }
    else if (narrow()) {
      // On a phone the Info button is hidden behind the mode chip: give the focus back to whichever shows.
      var back = b && b.offsetParent ? b : _host && _host.querySelector(".ib-mchip");
      if (back) back.focus();
    }
  }

  var YIELD_MIN = [0, 5, 10, 30, 60];
  function paintInfo() {
    var p = _host && _host.querySelector(".ht-info");
    if (!p) return;
    var c = _conv;
    var open = !!(_chon && c && c.id === _chon && infoOpen());
    p.hidden = !open;
    if (!open) { p.innerHTML = ""; return; }
    var t = window.t, k = kenhCua(c.channel);
    var ten = c.title || c.customer_name || c.external_chat_id;
    var nb = p.querySelector(".ib-notebox"), noteFocus = !!(nb && document.activeElement === nb);
    var sel = function (key, label, opts, cur, hint) {
      return '<div class="ib-fld"><label for="ibSet-' + key + '">' + esc(label) + '</label><select id="ibSet-' + key + '" data-set="' + key + '">' +
        opts.map(function (o) {
          return '<option value="' + esc(o[0]) + '"' + (String(o[0]) === String(cur) ? " selected" : "") + '>' + esc(o[1]) + '</option>';
        }).join("") + '</select>' + (hint ? '<p class="ib-hint">' + esc(hint) + '</p>' : "") + '</div>';
    };
    var ai;
    if (c.bot_id) {
      var bot = c.bot_name || t("ht.bot");
      var yOpts = [["", t("ib.i_yield_def")]].concat(YIELD_MIN.map(function (n) { return [String(n), n ? t("ib.i_yield_n", { n: n }) : t("ib.i_yield_0")]; }));
      if (c.yield_min != null && YIELD_MIN.indexOf(c.yield_min) < 0) yOpts.push([String(c.yield_min), t("ib.i_yield_n", { n: c.yield_min })]);
      ai = '<div class="ib-sec"><h4>' + ic("sparkles") + ' ' + esc(t("ib.i_ai")) + '</h4>' +
        sel("who", t("ib.i_who"), [["off", t("ib.i_off")], ["ai", t("ib.m_ai")], ["draft", t("ib.m_draft")], ["human", t("ib.m_human")]],
            c.ai_allowed ? modeOf(c) : "off") +
        (c.chat_type === "group" && c.ai_allowed ? sel("when", t("ib.i_when"),
            [["mention", t("ib.i_when_mention")], ["auto", t("ib.i_when_auto")], ["always", t("ib.i_when_always")]], c.reply_when || "mention") : "") +
        (c.ai_allowed ? sel("yield", t("ib.i_yield"), yOpts, c.yield_min == null ? "" : String(c.yield_min)) +
          '<p class="ib-hint">' + esc(t("ib.i_botwide", { bot: bot })) + '</p>' : "") +
        '<button type="button" class="ib-link ib-open-bot">' + ic("settings") + ' ' + esc(t("ib.i_open_bot", { bot: bot })) + '</button></div>';
    } else {
      ai = '<div class="ib-sec"><h4>' + ic("sparkles") + ' ' + esc(t("ib.i_ai")) + '</h4><p class="ib-muted">' + esc(t("ib.i_nobot")) + '</p>' +
        '<button type="button" class="s-btn ib-make-bot">' + ic("plus") + ' ' + esc(t("ib.make_bot")) + '</button></div>';
    }
    var mail = c.contact && String(c.contact).indexOf("@") > 0;
    p.innerHTML =
      '<div class="ib-ih">' + ic("user-round") + ' <span>' + esc(t("ib.info")) + '</span>' +
        '<button type="button" class="s-btn-ghost ib-x" aria-label="' + esc(t("common.close")) + '">' + ic("x") + '</button></div>' +
      '<div class="ib-sec"><div class="ib-kh">' + avatarHtml(c, ten) + '<span><b>' + esc(ten) + '</b><small>' + logoKenh(c.channel) + ' ' +
          esc(accLabel(c) || k.nhan) + '</small></span></div>' +
        // A group has no one customer to call back: the contact line is for private chats (or a group that left one).
        (c.chat_type !== "group" || c.contact ? '<div class="ib-line">' + ic(mail ? "mail" : "phone") + (c.contact ? '<span>' + esc(c.contact) + '</span>'
          : '<span class="ib-muted">' + esc(t("ib.i_no_contact")) + '</span>') + '</div>' : "") +
        '<div class="ht-tagrow"></div>' +
        '<textarea class="ib-notebox" rows="3" maxlength="4000" placeholder="' + esc(t("ib.i_note_ph")) + '" aria-label="' +
          esc(t("ib.i_note")) + '"></textarea></div>' +
      ai +
      '<div class="ib-sec"><h4>' + ic("plug") + ' ' + esc(t("ib.i_channel")) + '</h4><div class="ib-line">' + logoKenh(c.channel) + ' <span>' +
        esc(k.nhan) + (accLabel(c) ? ' · ' + esc(accLabel(c)) : "") + '</span></div></div>';
    veTagRow();
    var note = p.querySelector(".ib-notebox");
    note.value = _noteEdit && _noteEdit.id === c.id ? _noteEdit.text : (c.note || "");
    note.oninput = function () { _noteEdit = { id: c.id, text: note.value }; };
    note.onblur = function () { saveNote(c.id); };
    if (noteFocus) note.focus();
    p.querySelector(".ib-x").onclick = function () { setInfo(false); };
    p.querySelectorAll("select[data-set]").forEach(function (s) {
      s.onchange = function () { onInfoSet(c, s.dataset.set, s.value); };
    });
    var ob = p.querySelector(".ib-open-bot");
    if (ob) ob.onclick = function () {
      chonTab("bot");
      try { document.dispatchEvent(new CustomEvent("javis:chatbot-open", { detail: { bot_id: c.bot_id } })); } catch (e) { /* old browser */ }
    };
    var mk = p.querySelector(".ib-make-bot");
    if (mk) mk.onclick = function () { makeBot(c); };
  }

  async function saveNote(id) {
    if (!_noteEdit || _noteEdit.id !== id) return;
    var text = _noteEdit.text;
    if (_conv && _conv.id === id && String(_conv.note || "") === text.trim()) { _noteEdit = null; return; }
    try {
      var d = await api("/conversations/" + id + "/note", { method: "POST", body: fd({ note: text }) });
      if (_noteEdit && _noteEdit.id === id && _noteEdit.text === text) _noteEdit = null;
      if (_conv && _conv.id === id && d.conversation) _conv.note = d.conversation.note;
      _vetMeta = metaSig();
      toast(window.t("ib.t_note"));
    } catch (e) { toast(window.t("ht.act_fail", { err: e.message })); }
  }

  async function onInfoSet(c, key, v) {
    if (key === "who") return setWho(c, v);
    if (!c.bot_id) return;
    var patch = {}, prev = {};
    if (key === "when") { patch.reply_when = v; prev.reply_when = c.reply_when || "mention"; }
    else if (key === "yield") { patch.nhuong_tay_phut = v; prev.nhuong_tay_phut = c.yield_min == null ? "" : String(c.yield_min); }
    else return;
    await setBot(c.bot_id, patch, prev, key === "when" ? "ib.t_when" : "ib.t_yield");
  }

  // Bot-wide settings changed from a chat (reply_when, how long the A.I. waits after you type). Same route as the bot form.
  async function setBot(botId, patch, prev, key, noUndo) {
    try { await api("/chatbots/" + encodeURIComponent(botId) + "/update", { method: "POST", body: fd(patch) }); }
    catch (e) { setNote(window.t("ht.act_fail", { err: e.message }), true); return; }
    toast(window.t(key), noUndo ? null : function () { setBot(botId, prev, patch, key, true); });
    refreshChat();
  }

  // "Who replies": off (the A.I. may not answer here) | ai | draft | human. Switching the A.I. on first allows it in this
  // chat (POST /ai), then sets the mode. `dismiss`: the owner said "Dismiss" to someone calling the A.I. in a group.
  async function setWho(c, v, dismiss, noUndo) {
    var wasOn = !!c.ai_allowed, wasMode = modeOf(c);
    if ((v === "off" && !wasOn && !c.ai_pending) || (v !== "off" && wasOn && v === wasMode)) return;
    try {
      if (v === "off") await api("/conversations/" + c.id + "/ai", { method: "POST", body: fd({ on: "0" }) });
      else {
        if (!wasOn) await api("/conversations/" + c.id + "/ai", { method: "POST", body: fd({ on: "1" }) });
        if (v !== wasMode) await api("/conversations/" + c.id + "/mode", { method: "POST", body: fd({ mode: v }) });
      }
    } catch (e) { setNote(window.t("ht.act_fail", { err: e.message }), true); refreshChat(); return; }
    var msg = dismiss ? "ib.t_dismissed" : v === "off" ? "ib.t_ai_off" : !wasOn ? "ib.t_ai_on" : "ib.t_mode_" + v;
    toast(window.t(msg, { bot: c.bot_name || window.t("ht.bot") }), noUndo || dismiss ? null : function () {
      var now = { id: c.id, ai_allowed: v !== "off", mode: v === "off" ? wasMode : v, bot_name: c.bot_name };
      setWho(now, wasOn ? wasMode : "off", false, true);
    });
    refreshChat();
  }

  function refreshChat() {
    _dauVetTin = "";
    if (_chon) taiTin(false);
    tai(true);
  }

  // No bot answers this channel account yet: open the bot form with the account ticked (same path as the account card).
  function makeBot(c) {
    var a = _tk.filter(function (x) { return x.account_key === c.channel_account_id; })[0];
    chonTab("bot");
    try { document.dispatchEvent(new CustomEvent("javis:chatbot-new", { detail: { account_id: a ? a.id : "" } })); } catch (e) { /* old browser */ }
  }

  // A line under the composer about the last action (an error, "the A.I. chose to stay silent").
  function setNote(text, err) {
    _actNote = text ? { text: text, err: !!err } : null;
    var box = _host && _host.querySelector(".ht-thread .ht-compose");
    if (!box) return;
    var cu = box.querySelector(".ib-note");
    if (cu) cu.parentNode.removeChild(cu);
    if (_actNote) box.insertAdjacentHTML("afterbegin", noteHtml());
  }
  function noteHtml() {
    return _actNote ? '<div class="ib-note' + (_actNote.err ? " err" : "") + '" role="status">' + ic(_actNote.err ? "triangle-alert" : "info") +
      ' <span>' + esc(_actNote.text) + '</span></div>' : "";
  }

  // A short message at the bottom of the screen, with Undo when the change can be put back.
  function toast(text, undo) {
    var old = document.getElementById("ibToast");
    if (old) old.parentNode.removeChild(old);
    clearTimeout(_toastT);
    var t = document.createElement("div");
    t.id = "ibToast";
    t.className = "ib-toast";
    t.setAttribute("role", "status");
    t.innerHTML = '<span>' + esc(text) + '</span>' + (undo ? '<button type="button">' + esc(window.t("ib.undo")) + '</button>' : "");
    document.body.appendChild(t);
    if (undo) t.querySelector("button").onclick = function () { if (t.parentNode) t.parentNode.removeChild(t); undo(); };
    _toastT = setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 6000);
  }

  // ---------------------------------------------------------------- tags on a conversation (2026-10-25)
  // Owner: "thêm tag khách hàng", like Pancake's coloured chips. Under the thread header: the phone/email the customer
  // left (if any), this conversation's tags (x takes one off) and a "Tag" button opening the picker, where the owner puts
  // tags on or off, makes a new one (name + colour from the fixed palette) and renames, recolours or deletes one. The
  // row redraws on its own, so ticking several tags keeps the picker open.
  function palette(cur) {
    var F = window.JavisConvFilters;
    return '<span class="ht-sws" role="group" aria-label="' + esc(window.t("ht.tag_colors")) + '">' + (F ? F.TAG_COLORS : []).map(function (k, i) {
      return '<button type="button" class="ht-sw' + (k === cur ? " on" : "") + '" data-c="' + k + '" aria-pressed="' + (k === cur) +
        '" aria-label="' + esc(window.t("ht.tag_color", { n: i + 1 })) + '"></button>';
    }).join("") + '</span>';
  }

  function tagPopHtml(on) {
    var F = window.JavisConvFilters;
    var rows = _tags.map(function (g) {
      if (_tagEdit === g.id) {
        return '<div class="ht-tagpop-edit" data-id="' + g.id + '">' +
          '<input class="ht-tagpop-ename" maxlength="40" value="' + esc(g.name) + '" aria-label="' + esc(window.t("ht.tag_name")) + '">' +
          palette(_tagEditColor || g.color) +
          '<span class="ht-tagpop-eacts">' +
            '<button type="button" class="s-btn ht-tag-save">' + esc(window.t("common.save")) + '</button>' +
            '<button type="button" class="s-btn-ghost ht-tag-cancel">' + esc(window.t("common.cancel")) + '</button>' +
            '<button type="button" class="s-btn-ghost ht-tag-del">' + ic("trash-2") + ' ' + esc(window.t("common.delete")) + '</button>' +
          '</span></div>';
      }
      return '<div class="ht-tagpop-row">' +
        '<button type="button" class="ht-tag-pick' + (on[g.id] ? " on" : "") + '" data-id="' + g.id + '" aria-pressed="' + !!on[g.id] + '">' +
          '<span class="ht-tag-check">' + (on[g.id] ? ic("check") : "") + '</span>' + F.tagChip(g) + '</button>' +
        '<button type="button" class="ht-tag-edit" data-id="' + g.id + '" aria-label="' + esc(window.t("ht.tag_edit", { name: g.name })) +
          '" title="' + esc(window.t("ht.tag_edit", { name: g.name })) + '">' + ic("pencil") + '</button></div>';
    }).join("");
    return '<div class="ht-tagpop" role="dialog" aria-label="' + esc(window.t("ht.tag_title")) + '">' +
      '<div class="ht-tagpop-h"><b>' + esc(window.t("ht.tag_title")) + '</b>' + infoBtn() +
        '<button type="button" class="ht-tag-close" aria-label="' + esc(window.t("common.close")) + '">' + ic("x") + '</button></div>' +
      infoBody(esc(window.t("ht.tag_info"))) +
      (rows ? '<div class="ht-tagpop-list">' + rows + '</div>' : '<div class="ht-tagpop-none">' + esc(window.t("ht.tag_none")) + '</div>') +
      '<div class="ht-tagpop-new">' +
        '<input class="ht-tagpop-nname" maxlength="40" placeholder="' + esc(window.t("ht.tag_new_ph")) + '" aria-label="' + esc(window.t("ht.tag_new_ph")) + '">' +
        palette(_tagNewColor) +
        '<button type="button" class="s-btn ht-tag-create">' + ic("plus") + ' ' + esc(window.t("ht.tag_add")) + '</button>' +
      '</div>' +
      (_tagErr ? '<div class="ht-tagpop-err">' + ic("triangle-alert") + ' <span>' + esc(_tagErr) + '</span></div>' : "") +
    '</div>';
  }

  var _tagEditColor = "", _tagNewText = "", _tagEditText = null;   // picker colour being edited, and what is typed (kept across redraws)
  // The tag chips beside the name in the chat head follow every change made in the Info panel (no thread redraw).
  function paintHeadTags() {
    var h = _host && _host.querySelector(".ht-thread .ib-htags"), F = window.JavisConvFilters;
    if (!h || !_conv || !F) return;
    var add = h.querySelector(".ib-htag-add");
    h.querySelectorAll(".ht-tag, .ht-tag-more").forEach(function (x) { x.remove(); });
    if (add && _conv.tags && _conv.tags.length) add.insertAdjacentHTML("beforebegin", F.tagChips(_conv.tags, 3));
  }

  function veTagRow() {
    paintHeadTags();
    var row = _host && _host.querySelector(".ht-info .ht-tagrow");
    var F = window.JavisConvFilters;
    if (!row || !_conv || !F) return;
    var c = _conv, on = {};
    (c.tags || []).forEach(function (g) { on[g.id] = true; });
    var nOld = row.querySelector(".ht-tagpop-nname");
    var focusNew = !!(nOld && document.activeElement === nOld);
    row.innerHTML =
      (c.tags || []).map(function (g) {
        return '<span class="ht-tag ht-tag-on" data-c="' + F.tagColor(g.color) + '" title="' + esc(g.name) + '"><span class="ht-tag-name">' +
          esc(g.name) + '</span>' +
          '<button type="button" class="ht-tag-x" data-id="' + g.id + '" aria-label="' + esc(window.t("ht.tag_remove", { name: g.name })) +
          '" title="' + esc(window.t("ht.tag_remove", { name: g.name })) + '">' + ic("x") + '</button></span>';
      }).join("") +
      '<button type="button" class="ht-tag-add' + (_tagPop ? " on" : "") + '" aria-expanded="' + _tagPop + '">' + ic("tag") + ' <span>' +
        esc(window.t("ht.tag_btn")) + '</span></button>' +
      (_tagPop ? tagPopHtml(on) : "");
    // What is typed lives in _tagNewText / _tagEditText, so the 5-second refresh redrawing the thread does not wipe it.
    var n = row.querySelector(".ht-tagpop-nname");
    if (n) { n.value = _tagNewText; n.oninput = function () { _tagNewText = n.value; }; if (focusNew) n.focus(); }
    var e = row.querySelector(".ht-tagpop-ename");
    if (e) { if (_tagEditText != null) e.value = _tagEditText; e.oninput = function () { _tagEditText = e.value; }; }
    if (n) n.onkeydown = function (ev) {
      if (ev.key === "Enter" && !ev.isComposing) { ev.preventDefault(); createTag(c.id); }
    };
    if (e) e.onkeydown = function (ev) {
      if (ev.key === "Enter" && !ev.isComposing) { ev.preventDefault(); saveTag(_tagEdit); }
    };
    row.onkeydown = function (ev) { if (ev.key === "Escape" && _tagPop) { closeTagPop(); } };
    row.onclick = function (ev) {
      var b = ev.target.closest && ev.target.closest("button");
      if (!b || !row.contains(b)) return;
      var id = parseInt(b.dataset.id || "0", 10);
      if (b.classList.contains("ht-tag-add")) { _tagPop = !_tagPop; _tagEdit = 0; _tagErr = ""; veTagRow(); }
      else if (b.classList.contains("ht-tag-close")) closeTagPop();
      else if (b.classList.contains("ht-tag-x")) setTag(c.id, id, false);
      else if (b.classList.contains("ht-tag-pick")) setTag(c.id, id, !on[id]);
      else if (b.classList.contains("ht-tag-edit")) {
        var g = _tags.filter(function (x) { return x.id === id; })[0];
        _tagEdit = id; _tagEditColor = g ? g.color : ""; _tagEditText = null; _tagErr = ""; veTagRow();
        var en = row.querySelector(".ht-tagpop-ename"); if (en) en.focus();
      }
      else if (b.classList.contains("ht-tag-cancel")) { _tagEdit = 0; _tagErr = ""; veTagRow(); }
      else if (b.classList.contains("ht-tag-save")) saveTag(_tagEdit);
      else if (b.classList.contains("ht-tag-del")) deleteTag(_tagEdit);
      else if (b.classList.contains("ht-tag-create")) createTag(c.id);
      else if (b.classList.contains("ht-sw")) {
        if (b.closest(".ht-tagpop-edit")) _tagEditColor = b.dataset.c; else _tagNewColor = b.dataset.c;
        b.parentNode.querySelectorAll(".ht-sw").forEach(function (x) {
          x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", String(x === b));
        });
      }
    };
  }

  function closeTagPop() {
    _tagPop = false; _tagEdit = 0; _tagErr = "";
    veTagRow();
    var b = _host && _host.querySelector(".ht-tag-add");
    if (b) b.focus();
  }

  // A click anywhere outside the tag row closes the picker (one listener for the page's life).
  var _tagOutside = false;
  function watchTagOutside() {
    if (_tagOutside) return;
    _tagOutside = true;
    document.addEventListener("mousedown", function (ev) {
      if (!_tagPop || !_host) return;
      var row = _host.querySelector(".ht-info .ht-tagrow");
      if (row && !row.contains(ev.target)) { _tagPop = false; _tagEdit = 0; _tagErr = ""; veTagRow(); }
    });
  }

  // After the tag list changed (made, renamed, recoloured, deleted): the open conversation's chips follow the new names
  // and colours, the list reloads for the row chips and counts.
  function tagsChanged(tags) {
    _tags = tags || _tags;
    var by = {};
    _tags.forEach(function (g) { by[g.id] = g; });
    if (_conv && _conv.tags) {
      _conv.tags = _conv.tags.filter(function (g) { return by[g.id]; }).map(function (g) {
        return { id: g.id, name: by[g.id].name, color: by[g.id].color };
      });
    }
    var keep = function (id) { return !!by[id]; };
    if (_tagsAny.some(function (id) { return !keep(id); }) || _tagsNone.some(function (id) { return !keep(id); })) {
      _tagsAny = _tagsAny.filter(keep); _tagsNone = _tagsNone.filter(keep);
      saveFilters();
      paintHead();
    }
    _vetMeta = metaSig();
    veTagRow();
    tai(true);
  }

  async function setTag(convId, tagId, on) {
    _tagErr = "";
    try {
      var d = await api("/conversations/" + convId + "/tags", { method: "POST", body: fd({ tag_id: tagId, on: on ? "1" : "0" }) });
      if (_conv && _conv.id === convId) { _conv.tags = d.tags || []; _vetMeta = metaSig(); }
      _items.forEach(function (it) { if (it.id === convId) it.tags = d.tags || []; });
    } catch (e) { _tagErr = e.message; }
    veTagRow();
    veDanhSach();
    tai(true);
  }

  async function createTag(convId) {
    var n = _host && _host.querySelector(".ht-tagpop-nname");
    var name = n ? n.value.trim() : "";
    if (!name) { _tagErr = window.t("ht.tag_need_name"); veTagRow(); return; }
    _tagErr = "";
    try {
      var d = await api("/conversations/tags", { method: "POST", body: fd({ name: name, color: _tagNewColor }) });
      _tagNewText = "";
      _tags = d.tags || _tags;
      await setTag(convId, d.tag.id, true);     // made from a conversation's picker: it goes on that conversation
      var n2 = _host && _host.querySelector(".ht-tagpop-nname");
      if (n2) n2.focus();
    } catch (e) { _tagErr = e.message; veTagRow(); }
  }

  async function saveTag(id) {
    var e = _host && _host.querySelector(".ht-tagpop-ename");
    if (!id || !e) return;
    _tagErr = "";
    try {
      var d = await api("/conversations/tags/" + id, { method: "POST", body: fd({ name: e.value.trim(), color: _tagEditColor }) });
      _tagEdit = 0;
      tagsChanged(d.tags);
    } catch (err) { _tagErr = err.message; veTagRow(); }
  }

  async function deleteTag(id) {
    var g = _tags.filter(function (x) { return x.id === id; })[0];
    if (!g || !confirm(window.t("ht.tag_del_confirm", { name: g.name, n: g.count }))) return;
    _tagErr = "";
    try {
      var d = await api("/conversations/tags/" + id, { method: "DELETE" });
      _tagEdit = 0;
      tagsChanged(d.tags);
    } catch (err) { _tagErr = err.message; veTagRow(); }
  }

  // ---------------------------------------------------------------- drag the list column (2026-10-25)
  // Owner: "ở màn chatbot cũng đang chưa kéo được navbar gọn vào theo kiểu kéo thả", like the Partners and Chat pages:
  // the shared col-resize.js handle on the list's right edge, width remembered, double-click resets; dragged past the
  // fold point it snaps into a strip of initials (.ht-mini) whose hover card names the conversation. Wide screens only
  // (console.css hides the handle and ignores the width below 901px).
  var LIST_MIN_W = 260, LIST_MINI_W = 72;
  function attachListResize(body) {
    var CR = window.JavisColResize, wrap = body.querySelector(".ht-wrap"), col = body.querySelector(".ht-listcol");
    if (!CR || !wrap || !col) return;
    var inner = wrap.querySelector(".ht-body");
    var o = { host: wrap, varName: "--ht-list-w", key: "javis_ht_list_w", min: LIST_MIN_W, max: 560, edge: "right",
      label: "ht.resize_list", keep: 420, total: function () { return inner ? inner.clientWidth : 0; },
      snap: { below: CR.FOLD_AT(LIST_MIN_W), to: LIST_MINI_W, onSnap: function (on) {
        wrap.classList.toggle("ht-mini", !!on);
        if (!on) CR.miniTip.hide();
      } } };
    CR.apply(o);
    CR.attach(col, o);
    var list = col.querySelector(".ht-list");
    var card = function (row) {
      if (!wrap.classList.contains("ht-mini")) return;
      var txt = function (sel) { var x = row.querySelector(sel); return x ? x.textContent.trim() : ""; };
      var badge = row.querySelector(".ht-item-sub .ht-badge");
      CR.miniTip.show(row, { ava: '<span class="ht-item-ava">' + esc(txt(".ht-item-ava").charAt(0)) + '</span>',
        name: txt(".ht-item-top strong"), time: txt(".ht-item-time"), sub: txt(".ht-item-sub small"),
        stText: badge ? badge.getAttribute("title") : "", st: badge ? "need" : "" });
    };
    var hide = function () { CR.miniTip.hide(); };
    list.addEventListener("mouseover", function (e) {
      var row = e.target.closest && e.target.closest(".ht-item");
      if (row && !row.contains(e.relatedTarget)) card(row);
    });
    list.addEventListener("mouseout", function (e) {
      var row = e.target.closest && e.target.closest(".ht-item");
      if (row && !row.contains(e.relatedTarget)) hide();
    });
    list.addEventListener("focusin", function (e) { if (e.target.classList && e.target.classList.contains("ht-item")) card(e.target); });
    list.addEventListener("focusout", hide);
    list.addEventListener("click", hide);
  }

  // "A.I. reply" (owner, 2026-10-28: "nhiều khi anh gõ kiểu ra lệnh để nó trả lời khách"): what is typed in the box is an
  // ORDER for the A.I. ("quote 20 cases wholesale, delivery Thursday"); an empty box lets it read the chat and write on its
  // own. The answer is always a draft in the dashed box (kept on the server), never sent by itself. "Rewrite" asks again
  // with the same order.
  async function aiReply(c, lenh, kind) {
    if (_aiBusy) return;
    _aiBusy = kind;
    _actNote = null;
    veThread();
    var d = {}, loi = "";
    try {
      var r = await fetch("/conversations/" + c.id + "/ai-reply", { method: "POST", body: fd({ mode: "draft", instruction: lenh || "" }) });
      try { d = await r.json(); } catch (e) { d = {}; }
      if (!r.ok || d.ok === false) loi = (d && d.error) || window.t("cb.loi_ma", { ma: r.status });
    } catch (e) { loi = e.message; }
    _aiBusy = "";
    if (!loi && !d.silent) {
      _draftEdit = null;
      if (kind === "ask") { var ta = _host && _host.querySelector(".ht-thread .ib-cin textarea"); if (ta) ta.value = ""; }
    }
    _actNote = loi ? { text: window.t("ht.act_fail", { err: loi }), err: true } : d.silent ? { text: window.t("ib.ai_silent"), err: false } : null;
    refreshChat();
  }

  async function sendDraft(c) {
    var t = _host && _host.querySelector(".ht-thread .ib-draft-t");
    var txt = t ? t.value.trim() : "";
    if (!txt || _aiBusy) return;
    _aiBusy = "send";
    veThread();
    try {
      await api("/conversations/" + c.id + "/draft", { method: "POST", body: fd({ action: "send", text: txt }) });
      _draftEdit = null; _actNote = null;
    } catch (e) { _actNote = { text: window.t("ht.act_fail", { err: e.message }), err: true }; }
    _aiBusy = "";
    refreshChat();
  }

  async function dropDraft(c) {
    if (_aiBusy) return;
    try { await api("/conversations/" + c.id + "/draft", { method: "POST", body: fd({ action: "discard" }) }); }
    catch (e) { setNote(window.t("ht.act_fail", { err: e.message }), true); return; }
    _draftEdit = null;
    toast(window.t("ib.t_dropped"));
    refreshChat();
  }

  // "Ask the A.I. to answer this message" under a message the bot stayed silent on: it answers and the reply is sent.
  async function askNow(c) {
    if (_aiBusy) return;
    _aiBusy = "now";
    veThread();
    var d = {}, loi = "";
    try {
      var r = await fetch("/conversations/" + c.id + "/ai-reply", { method: "POST", body: fd({ mode: "send" }) });
      try { d = await r.json(); } catch (e) { d = {}; }
      if (!r.ok || d.ok === false) loi = (d && d.error) || window.t("cb.loi_ma", { ma: r.status });
    } catch (e) { loi = e.message; }
    _aiBusy = "";
    _actNote = loi ? { text: window.t(d.text ? "ht.act_send_failed" : "ht.act_fail", { err: loi }), err: true }
      : d.silent ? { text: window.t("ib.ai_silent"), err: false } : null;
    if (loi && d.text) { var ta = _host && _host.querySelector(".ht-thread .ib-cin textarea"); if (ta) ta.value = d.text; }
    else if (!loi && !d.silent) toast(window.t(d.taught ? "ib.t_sent_taught" : "ib.t_sent"));
    refreshChat();
  }

  // "Bot im: lý do" ngay dưới tin khách cuối, lấy từ nhật ký bộ phán xử, khỏi phải mở menu Bộ phán xử để hỏi vì sao. When the
  // A.I. may answer here and the customer's message is still the last one, one tap asks it to answer that message now.
  function renderSilenceLine(c) {
    var s = _silence;
    if (!s || !c.bot_id) return "";
    var RP = window.JavisReplyPolicy;
    var lyDo = s.code ? (RP ? RP.codeLabel(s.code) : s.code) : (s.reason || "");
    if (!lyDo) return "";
    var diem = (s.score == null) ? "" : " (" + Number(s.score).toFixed(2) +
      (s.threshold != null ? " / " + Number(s.threshold).toFixed(2) : "") + ")";
    var last = _msgs[_msgs.length - 1];
    var canAsk = c.ai_allowed && modeOf(c) === "ai" && _running && last && last.sender_type === "customer";
    return '<div class="ht-silent">' + ic("info") + ' <span>' + esc(window.t("ht.silent", { why: lyDo + diem })) + '</span>' +
      (RP ? ' <button type="button" class="ht-silent-why">' + esc(window.t("ht.silent_why")) + '</button>' : "") +
      (canAsk ? ' <button type="button" class="ib-silent-ask"' + (_aiBusy ? " disabled" : "") + '>' +
        esc(window.t(_aiBusy === "now" ? "ib.ai_busy" : "ib.ask_ai_now")) + '</button>' : "") + '</div>';
  }

  // Ô trả lời khách: Gửi (gửi nguyên văn) và A.I. trả lời (chữ trong ô là lệnh cho A.I.). Nói rõ trước khi bấm gửi: gửi từ đây
  // là TIẾP QUẢN (bot đang trực sẽ im ở cuộc này), và với kênh tài khoản cá nhân thì tin đi dưới tên chính bạn.
  function veCompose(c) {
    var V = window.JavisInboxV5, k = kenhCua(c.channel), t = window.t;
    var laBot = !!c.bot_id;
    var draft = c.draft && String(c.draft.text || "").trim() ? c.draft : null;
    // On a personal account the message goes out under the owner's own name: the box says so in its placeholder
    // (0.397.0, the note line above the box took a row of the chat). The "sending takes over" and "example command"
    // notes went (owner, 2026-10-28: a good UI needs no notes).
    var ten = k.kind === "account" ? accLabel(c) || k.nhan : "";
    // "Enter to send" in the placeholder is a computer's hint only: a phone's Enter is a new line.
    var cham = !!(window.JavisActs && window.JavisActs.touchMain && window.JavisActs.touchMain());
    var ph = ten ? t(laBot ? "ib.cin_ph_as_ai" : "ib.cin_ph_as", { ten: ten }) :
      t(laBot ? "ib.cin_ph_ai" : cham ? "ib.cin_ph_touch" : "ht.gui_ph");
    var busy = _aiBusy === "redo" || _aiBusy === "send" ? _aiBusy : "";
    return '<div class="ht-compose' + (draft ? " has-draft" : "") + '">' + noteHtml() +
      '<div class="ib-cbox">' +
      (draft && V ? V.draftHtml(draft, busy || (_aiBusy ? "x" : ""), ic) : "") +
      '<div class="ib-cin">' +
        '<textarea rows="1" placeholder="' + esc(ph) + '" aria-label="' + esc(t("ib.cin_aria")) + '"></textarea>' +
        (laBot ? '<button type="button" class="s-btn-ghost ib-ask"' + (_aiBusy ? " disabled" : "") + ' title="' + esc(t("ib.ai_reply_t")) +
          '" aria-label="' + esc(t("ib.ai_reply")) + '">' +
          ic(_aiBusy === "ask" ? "loader" : "sparkles") + '<span>' + esc(t(_aiBusy === "ask" ? "ib.ai_busy" : "ib.ai_reply")) + '</span></button>' : "") +
        '<button type="button" class="s-btn ht-send" aria-label="' + esc(t("ht.gui")) + '">' + ic("send") + '<span>' + esc(t("ht.gui")) + '</span></button>' +
      '</div></div>' +
    '</div>';
  }

  async function gui(c) {
    var box = _host.querySelector(".ht-thread");
    var ta = box && box.querySelector(".ib-cin textarea");
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
    var ta2 = box && box.querySelector(".ib-cin textarea");
    if (ta2) ta2.focus();
  }

  function veTin(t) {
    var lop = t.sender_type === "customer" ? "khach" : t.sender_type === "ai" ? "bot"
            : t.sender_type === "human" ? "nguoi" : "hethong";
    var ai = t.sender_type === "customer" ? (t.sender_name || "")
           : t.sender_type === "ai" ? (t.sender_name || window.t("ht.bot"))
           : t.sender_type === "human" ? window.t("ht.ban") : "";
    if (t.message_type === "reaction") return renderReaction(t, lop, ai);
    var than;
    // Ảnh và file khách gửi (0.171.0, ht-media.js): ảnh hiện thẳng trong bong bóng, file thành thẻ bấm tải về. Chỉ còn chú
    // thích thật của khách đi kèm; dòng "đã tải về: <đường dẫn máy chủ>" và link ảnh trần không hiện ra nữa.
    // Owner, 2026-10-25: a photo the owner (or the bot) sends must show as a photo too, so they can check what went out;
    // it used to read "image https://...zdn.vn/....jpg". Any non-text message goes through the same parser.
    var wantMedia = t.sender_type === "customer" || (t.message_type && t.message_type !== "text");
    var media = (wantMedia && window.JavisHtMedia) ? window.JavisHtMedia.phanTich(t, t.conversation_id) : null;
    var coMedia = !!(media && (media.anh || media.file));
    if (coMedia) {
      than = window.JavisHtMedia.html(media, esc, ic, window.t) + (media.chu ? '<div class="ht-chu-thich">' + esc(media.chu) + '</div>' : "");
    } else if (t.sender_type === "ai" && window.mdToHtml) {
      try { than = window.mdToHtml(t.text || "", ""); } catch (e) { than = esc(t.text || ""); }
    } else {
      than = esc(t.text || "");
    }
    var loai = (t.message_type && t.message_type !== "text" && !coMedia)
      ? '<span class="ht-loai">' + ic(t.message_type === "image" ? "image" : t.message_type === "audio" ? "mic" : "paperclip") +
        ' ' + esc(t.message_type) + '</span>' : "";
    var loi = t.metadata && t.metadata.loi
      ? '<div class="ht-msg-loi">' + ic("triangle-alert") + ' ' + esc(t.metadata.loi) + '</div>' : "";
    // Who and when go under the bubble (0.397.0). A private chat's customer is named in the head already, so only a
    // group shows who wrote each message.
    if (lop === "khach" && _conv && _conv.chat_type !== "group") ai = "";
    return '<div class="ht-msg ' + lop + '">' +
      '<div class="ht-bubble">' + loai + than + '</div>' + loi +
      '<div class="ht-msg-h">' + esc(ai) + (ai ? ' · ' : '') + esc(gio(t.created_at)) + '</div>' +
    '</div>';
  }

  // An emoji reaction (0.334.0): one small line beside the side that reacted, the emoji and what it was put on, instead
  // of a bubble that would read as something they wrote.
  function renderReaction(t, lop, ai) {
    var r = (t.metadata && t.metadata.reaction) || {};
    var bieu = r.emoji || r.code || "";
    var quote = String(r.target_text || "").replace(/\s+/g, " ").trim();
    if (quote.length > 80) quote = quote.slice(0, 79) + "…";
    // Who reacted follows the side it came from (owner, 2026-10-28: a customer's heart read "Bot thả cảm xúc"). A
    // customer reaction often has no sender name: a one-to-one chat is named after that customer; a group says "Customer".
    var c = _conv || {};
    var who = ai || (lop === "khach" ? (c.chat_type !== "group" && (c.customer_name || c.title)) || window.t("ht.react_cust")
                     : lop === "nguoi" ? window.t("ht.ban") : window.t("ht.bot"));
    var cau = r.removed ? window.t("ht.react_off", { who: who })
            : quote ? window.t("ht.react_on", { who: who, quote: "\u201c" + quote + "\u201d" })
            : window.t("ht.react_any", { who: who });
    return '<div class="ht-msg ht-react ' + lop + (r.removed ? " off" : "") + '">' +
      '<div class="ht-react-row"><span class="ht-react-emoji">' + esc(bieu) + '</span>' +
      '<span class="ht-react-txt">' + esc(cau) + ' · ' + esc(gio(t.created_at)) + '</span></div>' +
    '</div>';
  }

  // ---------------------------------------------------------------- the account card (Channels tab)
  var TT_TK = {
    running: ["ht.tk_dang_chay", "ok"], starting: ["ht.tk_khoi_dong", "wait"],
    error: ["ht.tk_loi", "err"], off: ["ht.tk_tat", "off"], chua_gan: ["ht.tk_chua_gan", "off"],
  };

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
          // 0.174.0: nhập tin cũ (Zalo cá nhân giữ khoảng 2 tuần). Chủ bấm mới chạy; tin cũ không vào bot, không tính chưa đọc.
          (nl.nhap_lich_su && a.kind === "account"
            ? '<button type="button" class="s-btn-ghost ht-acc-nhap-cu">' + ic("history") + ' ' + esc(window.t("ht.nhap_cu")) + '</button>' : "") +
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
      // Đã đứng ở tab Bot rồi: không dựng lại tab (mất nhịp), chỉ mở form với kênh này tích sẵn.
      if (_tab !== "bot") chonTab("bot");
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
    var nhapCu = c.querySelector(".ht-acc-nhap-cu");
    if (nhapCu) nhapCu.onclick = function () { nhapTinCu(a, nhapCu); };
    var sua = c.querySelector(".ht-acc-sua");
    if (sua) sua.onclick = function () { moSuaTK(a); };
    var kn = c.querySelector(".ht-acc-ket-noi");
    if (kn) kn.onclick = function () { try { window.JavisNav.go("mcp"); } catch (e) {} };
    var xoa = c.querySelector(".ht-acc-xoa");
    if (xoa) xoa.onclick = function () { xoaTK(a); };
    return c;
  }

  // Xoá một tài khoản kênh. Dùng chung cho nút trên thẻ (kênh chưa có bot) và nút trong bảng sửa kênh (mở từ chip trên thẻ bot).
  async function xoaTK(a) {
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
    // Thẻ bot (chatbots.js) còn chip của kênh vừa xoá: nạp lại tab để chip biến mất.
    if (_tab === "bot" || _tab === "kenh") veTab();
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
      '<div class="cb-hint ht-card-hint" id="htCardHint" hidden></div>' +
      '<label id="htTokenLabel"></label>' +
      '<div class="cb-row"><input id="htToken" type="password" placeholder="' + esc(window.t("cb.ph_token")) + '">' +
        '<button class="s-btn-ghost" id="htCheck" type="button">' + esc(window.t("cb.kiem_tra")) + '</button></div>' +
      '<div class="cb-hint" id="htTokenNote"></div>' +
      '<div class="cb-hint ht-webhook" id="htWebhook" hidden></div>' +
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
    // Vietnamese interface opens docs/, every other language docs/en/ (same rule as the owner channel guides).
    function guideUrl(k) {
      var h = (k && k.huong_dan) || {};
      var vi = window.JavisI18n && window.JavisI18n.lang() === "vi";
      var f = vi ? (h.vi || h.en) : (h.en || h.vi);
      if (!f) return "";
      return "https://github.com/blogminhquy/javis-os/blob/main/docs/" + (vi && h.vi ? "" : "en/") + f;
    }
    function apKenh(id) {
      chon = id; uname = ""; meta = {};
      var k = kenhCua(id);
      var lab = box.querySelector("#htTokenLabel");
      lab.textContent = "Token " + k.nhan;
      // A step-by-step guide for channels whose setup takes many clicks (Messenger, 0.436.1). On the label, not in the
      // hint under the field, because the hint is replaced by the result of Check.
      var g = guideUrl(k);
      if (g) lab.insertAdjacentHTML("beforeend", ' · <a class="ht-guide" href="' + esc(g) + '" target="_blank" rel="noopener">'
        + esc(window.t("ht.huong_dan")) + " ↗</a>");
      box.querySelector("#htTokenNote").textContent = (k.lay_token || "") + " " + window.t("cb.token_rieng");
      // A channel with its own card on the Connections page (Messenger, 0.436.2): connecting there is quicker and a Page
      // connected there is already in the channel list, so nobody should connect the same Page twice.
      var hint = box.querySelector("#htCardHint");
      hint.hidden = !k.the_ket_noi;
      hint.innerHTML = k.the_ket_noi ? esc(window.t("ht.the_ket_noi", { kenh: k.nhan })) +
        ' <button type="button" class="s-btn-ghost ht-mo-the">' + esc(window.t("ht.mo_ket_noi")) + '</button>' : "";
      var mo = hint.querySelector(".ht-mo-the");
      if (mo) mo.onclick = function () {
        dong();
        try { window.JavisNav.go("mcp"); } catch (e) {}
        setTimeout(function () { try { window.JavisMessenger && window.JavisMessenger.openForm(null); } catch (e) {} }, 400);
      };
      box.querySelectorAll(".cb-kenh-o").forEach(function (n) { n.classList.toggle("on", n.dataset.k === id); });
      hienWebhook(k);
    }
    // Kênh nhận tin qua webhook (Messenger, 0.134.0): hiện địa chỉ và mã xác minh để dán sang Meta.
    // Hỏi server chứ không tự ghép từ location: sau proxy, chỉ server biết địa chỉ ngoài thật.
    async function hienWebhook(k) {
      var o = box.querySelector("#htWebhook");
      if (!o) return;
      o.hidden = true;
      o.innerHTML = "";
      if (!k.webhook) return;
      try {
        var r = await api("/channels/webhook-info?channel=" + encodeURIComponent(k.id));
        if (chon !== k.id) return;
        o.innerHTML = '<b>' + esc(window.t("ht.wh_url")) + '</b> <code>' + esc(r.webhook_url || "") + '</code>' +
          (r.verify_token ? '<br><b>' + esc(window.t("ht.wh_token")) + '</b> <code>' + esc(r.verify_token) + '</code>' : "") +
          (r.https ? "" : '<br><span class="cb-warn">' + esc(window.t(r.site_verify ? "ht.zo_can_https" : "ht.wh_can_https")) + '</span>') +
          (r.site_verify ? veMaXacThuc(r.site_codes || []) : "");
        o.hidden = false;
        if (r.site_verify) noiMaXacThuc(o);
      } catch (e) {
        o.innerHTML = '<span class="cb-warn">' + esc(e.message) + '</span>';
        o.hidden = false;
      }
    }
    // Zalo OA (0.412.0): Zalo verifies the webhook domain by fetching /zalo_verifier<code>.html before it
    // accepts the webhook, and that happens BEFORE the account exists, so the code is saved on its own here.
    function veMaXacThuc(codes) {
      return '<div class="ht-zo-site"><b>' + esc(window.t("ht.zo_site_lb")) + '</b>' +
        '<div class="cb-row"><input id="htZoSite" placeholder="' + esc(window.t("ht.zo_site_ph")) + '">' +
        '<button class="s-btn-ghost" id="htZoSiteLuu" type="button">' + esc(window.t("ht.zo_site_luu")) + '</button></div>' +
        '<div id="htZoSiteNote">' + (codes.length ? esc(window.t("ht.zo_site_da", { file: "/zalo_verifier" + codes[0] + ".html" })) : "") +
        '</div></div>';
    }
    function noiMaXacThuc(o) {
      var nut = o.querySelector("#htZoSiteLuu");
      if (!nut) return;
      nut.onclick = async function () {
        var note = o.querySelector("#htZoSiteNote");
        var v = o.querySelector("#htZoSite").value.trim();
        if (!v) return;
        try {
          var r = await api("/zalo-oa/site-verification", { method: "POST", headers: { "Content-Type": "application/json" },
                                                            body: JSON.stringify({ code: v }) });
          note.textContent = window.t("ht.zo_site_da", { file: r.file || "" });
        } catch (e) { note.innerHTML = '<span class="cb-warn">' + esc(e.message) + '</span>'; }
      };
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
          // Only a Zalo Bot on a basic plan can be kept out of groups; Messenger, WhatsApp and Zalo OA have no groups at
          // all, so the Zalo sentence read as nonsense there (owner, 2026-11-01).
          (r.vao_duoc_nhom === false && chon === "zalo"
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
        // Kênh đã có bot không còn thẻ riêng để bấm Xoá (nó là chip trên thẻ bot), nên nút xoá nằm ở đây.
        (a.kind === "bot" ? '<button class="s-btn-ghost ht-xoa-tk" type="button">' + esc(window.t("ht.xoa_kenh")) + '</button>' : "") +
        '<button class="s-btn-ghost ht-close" type="button">' + esc(window.t("common.cancel")) + '</button>' +
        '<button class="s-btn ht-save" type="button">' + esc(window.t("common.save")) + '</button>' +
      '</div></div></div>');
    document.body.appendChild(box);
    var dong = function () { if (box.parentNode) box.parentNode.removeChild(box); };
    box.onmousedown = function (e) { if (e.target === box) dong(); };
    box.querySelector(".ht-close").onclick = dong;
    var nutXoa = box.querySelector(".ht-xoa-tk");
    if (nutXoa) nutXoa.onclick = function () { dong(); xoaTK(a); };
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
      if (_tab === "bot" || _tab === "kenh") veTab();
    };
  }

  // Nhập tin cũ của một tài khoản (0.174.0). Dùng chung cho nút trên thẻ kênh và chip Zalo trên thẻ bot (chatbots.js): kênh đã có bot
  // không hiện thẻ ở mục "Kênh chưa có bot", nên chip là đường duy nhất tới nút này.
  async function nhapTinCu(a, nut) {
    if (!confirm(window.t("ht.xn_nhap_cu", { ten: a.label || a.external_id || a.id }))) return;
    var goc = nut ? nut.innerHTML : "";
    if (nut) { nut.disabled = true; nut.textContent = window.t("ht.dang_nhap_cu"); }
    try {
      var r = await api("/channels/accounts/" + encodeURIComponent(a.id) + "/import-history",
                        { method: "POST", body: fd({ channel: a.channel }) });
      var bao = r.so_tin
        ? window.t("ht.da_nhap_cu", { tin: r.so_tin, chat: r.so_cuoc_chat })
        : window.t("ht.khong_co_tin_cu");
      if (r.bo_qua) bao += "\n" + window.t("ht.nhap_cu_bo_qua", { count: r.bo_qua });
      if (r.het_tran) bao += "\n" + window.t("ht.nhap_cu_het_tran");
      alert(bao);
    } catch (e) { alert(window.t("ht.loi_nhap_cu") + " " + e.message); }
    if (nut) { nut.disabled = false; nut.innerHTML = goc; }
    _dauVetTK = "";
    taiTK(true);
  }

  // Sửa một kênh theo id: chip kênh trên thẻ bot (chatbots.js) gọi vào đây. Chưa nạp danh sách kênh thì nạp rồi mới mở.
  async function suaKenh(id) {
    var tim = function () { return _tk.filter(function (x) { return x.id === id; })[0]; };
    var a = tim();
    if (!a) { try { await taiTK(); } catch (e) {} a = tim(); }
    if (a && a.sua_duoc) moSuaTK(a);
  }

  // Mở trang này từ nơi khác (thẻ bot ở tab Chatbot, console.js) với tab hoặc bộ lọc sẵn.
  function moTu(opts) {
    _cho = opts || {};
    var tabMo = chuanTab(_cho.tab || "");
    _tab = TABS.indexOf(tabMo) >= 0 ? tabMo : "inbox";
    if (_host && document.body.contains(_host)) { veTabs(); veTab(); return; }
    try { var s = window.Alpine && Alpine.store("nav"); if (s && s.go) s.go("conversations"); } catch (e) {}
  }

  window.JavisConversations = { render: render, mo: moTu, chonTab: chonTab,
                               themTaiKhoan: moThemTK, suaKenh: suaKenh, tenBrain: tenBrain, nhapTinCu: nhapTinCu };
})();
