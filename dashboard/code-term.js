// ============================================================
// JAVIS OS - Nhóm Code trên rail
//
// console.js gọi window.JavisCode.render(el, id) khi vào một trang thuộc nhóm Code, và
// window.JavisCode.roi() khi rời.
//
// "Code" là một KHU VỰC trên rail chứ không phải một trang: mỗi chức năng là MỘT MỤC trong
// nhóm đó. Hôm nay có Terminal; thêm chức năng sau (trình sửa code, git, chạy test) = thêm
// một dòng vào CHUC_NANG bên dưới + khai id ở console.js (RAIL_ITEMS, RAIL_GROUPS, VIEW_META,
// CODE_PAGES). Không phải dựng lại khung.
//
// xterm.js nạp LƯỜI: 285KB không nên nằm trong đường khởi động của dashboard khi phần lớn lượt
// mở không đụng tới nhóm Code. Lần đầu vào mới tải, các lần sau dùng lại.
// ============================================================
(function () {
  "use strict";

  var WS_GOC = (location.protocol === "https:" ? "wss" : "ws") + "://" + location.host;
  var KHOA_TABS = "javis.code.tabs";      // các tab terminal của TAB TRÌNH DUYỆT này (JSON {ds, chon})
  var KHOA_PHIEN = "javis.code.phien";    // khoá CŨ thời một-phiên; chỉ còn để di cư sang KHOA_TABS

  // ---- Các chức năng của nhóm Code. Thêm chức năng mới = thêm một dòng ở đây. ----
  // `id` phải khớp id mục trên rail (console.js RAIL_ITEMS + CODE_PAGES).
  var CHUC_NANG = [
    { id: "terminal", nhan: "Terminal", icon: "terminal", ve: veTerminal },
  ];

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function ic(ten, opt) { return (window.ic ? window.ic(ten, opt) : ""); }
  function brain() {
    try { return (window.currentBrainPath && window.currentBrainPath()) || "brain"; }
    catch (e) { return "brain"; }
  }
  function nho(k, v) { try { if (v === undefined) return sessionStorage.getItem(k) || ""; sessionStorage.setItem(k, v); } catch (e) {} return ""; }
  function xoaNho(k) { try { sessionStorage.removeItem(k); } catch (e) {} }

  /** Danh sách tab đã lưu của tab trình duyệt này: { ds: [sid...], chon: n } hoặc null.
   *  Bản cũ chỉ nhớ MỘT phiên ở KHOA_PHIEN - gặp thì mang nó sang làm tab đầu tiên, để người
   *  đang chạy lệnh dở lúc cập nhật không bị mất phiên. */
  function docTabs() {
    try {
      var raw = sessionStorage.getItem(KHOA_TABS);
      if (raw) {
        var o = JSON.parse(raw);
        if (o && Array.isArray(o.ds) && o.ds.length) return { ds: o.ds, chon: o.chon | 0 };
      }
    } catch (e) {}
    var cu = nho(KHOA_PHIEN);
    if (cu) { xoaNho(KHOA_PHIEN); return { ds: [cu], chon: 0 }; }
    return null;
  }

  // ============================================================
  // Khung trang
  // ============================================================
  var _dangChay = null;     // { huy: fn } của chức năng đang mở, để dọn khi rời trang

  function render(el, id) {
    // Trang nhóm Code chiếm TRỌN khung nhìn và tự cuộn bên trong (terminal cần chiều cao thật
    // để tính số dòng). Lớp này do console.js gỡ ra khi rời trang.
    el.classList.add("cview-flush");
    el.innerHTML = '<div class="code-page"><div class="code-panel" id="codePanel"></div></div>';
    moChucNang(el, id || CHUC_NANG[0].id);
  }

  function moChucNang(el, id) {
    dongChucNang();
    var panel = el.querySelector("#codePanel");
    var cn = CHUC_NANG.filter(function (c) { return c.id === id; })[0];
    if (!panel) return;
    if (!cn) { panel.innerHTML = '<div class="code-empty">Chức năng "' + esc(id) + '" chưa có.</div>'; return; }
    try { _dangChay = cn.ve(panel) || null; }
    catch (e) { panel.innerHTML = '<div class="code-empty">Lỗi nạp: ' + esc(e.message) + "</div>"; }
  }

  function dongChucNang() {
    var d = _dangChay; _dangChay = null;
    if (d && typeof d.huy === "function") { try { d.huy(); } catch (e) {} }
  }

  // Rời trang Code: console.js gọi trước khi #cviewBody bị ghi đè.
  function roi() { dongChucNang(); }

  // ============================================================
  // Chức năng 1: Terminal (nhiều tab, mỗi tab một phiên shell riêng)
  // ============================================================
  var _napXterm = null;   // Promise nạp thư viện, giữ lại để lần sau không tải nữa

  function napXterm() {
    if (window.Terminal && window.FitAddon) return Promise.resolve();
    if (_napXterm) return _napXterm;
    _napXterm = new Promise(function (ok, loi) {
      var css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "/static/vendor/xterm-5.5.0.css?v=1";
      document.head.appendChild(css);
      taiJs("/static/vendor/xterm-5.5.0.min.js?v=1")
        .then(function () { return taiJs("/static/vendor/xterm-addon-fit-0.10.0.min.js?v=1"); })
        .then(ok, loi);
    });
    return _napXterm;
  }
  function taiJs(src) {
    return new Promise(function (ok, loi) {
      var s = document.createElement("script");
      s.src = src;
      s.onload = ok;
      s.onerror = function () { loi(new Error("Không tải được " + src)); };
      document.head.appendChild(s);
    });
  }

  // Bảng màu theo tông của Javis. xterm vẽ bằng canvas nên KHÔNG đọc được biến CSS - phải
  // truyền màu vào tay, và đổi lại mỗi khi người dùng lật tông.
  function bangMau() {
    var sang = !!(window.javisTheme && window.javisTheme.isLight());
    return sang
      ? { background: "#ffffff", foreground: "#1c1a24", cursor: "#c2410c", cursorAccent: "#ffffff",
          selectionBackground: "rgba(232,93,31,0.22)",
          black: "#3b3b46", red: "#c62828", green: "#15803d", yellow: "#96590a", blue: "#1d4ed8",
          magenta: "#7c3aed", cyan: "#0e7490", white: "#55505f",
          brightBlack: "#6e6878", brightRed: "#d11f1f", brightGreen: "#16a34a", brightYellow: "#b45309",
          brightBlue: "#2563eb", brightMagenta: "#9333ea", brightCyan: "#0891b2", brightWhite: "#1c1a24" }
      : { background: "#0b0b12", foreground: "#e8e8f4", cursor: "#ff7a3c", cursorAccent: "#0b0b12",
          selectionBackground: "rgba(255,122,60,0.28)",
          black: "#2a2a38", red: "#f4565a", green: "#34d36b", yellow: "#f0c020", blue: "#5b9cff",
          magenta: "#b98cff", cyan: "#4dd6d6", white: "#c0c0da",
          brightBlack: "#5a5a72", brightRed: "#ff7b7e", brightGreen: "#6ce89a", brightYellow: "#ffd85c",
          brightBlue: "#8ab8ff", brightMagenta: "#d0b0ff", brightCyan: "#7fe6e6", brightWhite: "#ffffff" };
  }

  function khungCho(chu) {
    return '<div class="code-empty">' + ic("loader", { cls: "ic-xl ic-spin" }) +
      "<div>" + esc(chu || "Đang mở terminal...") + "</div></div>";
  }

  function veTerminal(panel) {
    var song = true;           // panel này còn đang hiển thị không (chống render trễ)
    var doi = { huy: function () { song = false; } };
    panel.innerHTML = khungCho();
    fetch("/terminal/status?brain=" + encodeURIComponent(brain()))
      .then(function (r) { return r.json(); })
      .then(function (st) {
        if (!song) return;
        if (!st.bat) { panel.innerHTML = khungTat(); return; }
        return napXterm().then(function () {
          if (!song) return;
          var t = dungTerminal(panel, st);
          doi.huy = function () { song = false; t.huy(); };
        });
      })
      .catch(function (e) {
        if (!song) return;
        panel.innerHTML = '<div class="code-empty">' + ic("triangle-alert", { cls: "ic-xl ic-warn" }) +
          "<div>Không mở được terminal.</div><div class=\"code-dim\">" + esc(e.message) + "</div></div>";
      });
    return { huy: function () { doi.huy(); } };
  }

  function khungTat() {
    return '<div class="code-empty">' + ic("lock", { cls: "ic-xl ic-dim" }) +
      "<div><b>Terminal đang tắt trên máy này.</b></div>" +
      '<div class="code-dim">Máy chủ đặt biến môi trường <code>JAVIS_TERMINAL=0</code>. ' +
      "Bỏ biến đó rồi khởi động lại Javis là bật lại.</div></div>";
  }

  /** Dựng terminal NHIỀU TAB: mỗi tab là một phiên shell riêng ở server (trần số phiên do
   *  server báo qua `max_phien`). Chuyển tab KHÔNG giết phiên - các tab khuất vẫn giữ
   *  WebSocket riêng nên lệnh của chúng chạy tiếp và output vẫn chảy về. Trả { huy }. */
  function dungTerminal(panel, st) {
    var ong = st.che_do === "ong";     // Windows: không có pty, chạy chế độ gõ theo dòng
    var maxTab = Math.max(1, st.max_phien | 0 || 4);
    panel.innerHTML =
      '<div class="term-wrap">' +
        '<div class="term-tabs" id="termTabs"></div>' +
        '<div class="term-bar">' +
          '<span class="term-dot" id="termDot"></span>' +
          '<span class="term-st" id="termSt">Đang nối...</span>' +
          '<span class="term-cwd" title="Thư mục làm việc">' + ic("folder-tree") + " " + esc(st.cwd) + "</span>" +
          '<span class="term-sp"></span>' +
          '<button class="term-btn" id="termClear" title="Xoá màn hình (Ctrl+L)">' + ic("eraser") + " Xoá</button>" +
          '<button class="term-btn" id="termNew" title="Đóng phiên của tab này rồi mở phiên sạch">' + ic("rotate-cw") + " Khởi động lại</button>" +
        "</div>" +
        (ong ? '<div class="term-note">' + ic("triangle-alert", { cls: "ic-warn" }) +
          " <b>Chế độ đơn giản (Windows).</b> Gõ nguyên một dòng rồi Enter. Không có gợi ý Tab, " +
          "không chạy được chương trình toàn màn hình như <code>vim</code> hay <code>htop</code>." +
          "</div>" : "") +
        '<div class="term-hosts" id="termHosts"></div>' +
      "</div>";

    var tabsEl = panel.querySelector("#termTabs");
    var hosts = panel.querySelector("#termHosts");
    var oSt = panel.querySelector("#termSt");
    var oDot = panel.querySelector("#termDot");
    var tabs = [];            // mỗi phần tử: { so, sid, host, term, fit, ws, dong, dem, boDem, stChu, stMau }
    var chon = -1;            // vị trí tab đang xem trong `tabs`
    var demTab = 0;           // đánh số tab theo thứ tự mở, giữ nguyên khi tab khác đóng

    function ghiTabs() {
      try {
        sessionStorage.setItem(KHOA_TABS, JSON.stringify({
          ds: tabs.map(function (t) { return t.sid || ""; }), chon: chon,
        }));
      } catch (e) {}
    }

    /** Trạng thái là CỦA TỪNG TAB (mỗi phiên nối/đứt độc lập); thanh trên chỉ chiếu trạng
     *  thái của tab đang xem. */
    function trangThai(tb, chu, mau) {
      tb.stChu = chu; tb.stMau = mau || "";
      if (tabs[chon] === tb) {
        if (oSt) oSt.textContent = chu;
        if (oDot) oDot.className = "term-dot " + tb.stMau;
      }
    }
    function gui(tb, o) {
      if (tb.ws && tb.ws.readyState === 1) { tb.ws.send(JSON.stringify(o)); return true; }
      return false;
    }
    /** Bỏ hẳn socket của một tab: GỠ handler TRƯỚC rồi mới đóng.
     *
     * Không gỡ thì `onclose` của socket cũ vẫn nổ sau đó, và nó là hàm tự-nối-lại. Bấm "Khởi
     * động lại" đúng lúc là có hai socket cùng chạy, mỗi cái viết vào một phiên khác nhau -
     * màn hình trộn lẫn hai shell mà nhìn thì tưởng terminal loạn. */
    function ngatWs(tb) {
      var ws = tb.ws;
      if (!ws) return;
      ws.onclose = null; ws.onmessage = null; ws.onerror = null;
      try { ws.close(); } catch (e) {}
      tb.ws = null;
    }

    function noi(tb) {
      var q = "brain=" + encodeURIComponent(brain()) +
              "&cols=" + tb.term.cols + "&rows=" + tb.term.rows +
              "&session=" + encodeURIComponent(tb.sid || "");
      trangThai(tb, "Đang nối...", "");
      var ws = tb.ws = new WebSocket(WS_GOC + "/ws/terminal?" + q);
      ws.onmessage = function (ev) {
        var m;
        try { m = JSON.parse(ev.data); } catch (e) { return; }
        if (m.type === "out") { tb.term.write(m.data || ""); return; }
        if (m.type === "hello") {
          tb.sid = m.session || "";
          ghiTabs();
          trangThai(tb, (m.che_do === "ong" ? "Chế độ đơn giản" : "Đang chạy") + " · " + (m.shell || "shell"), "ok");
          gui(tb, { type: "resize", cols: tb.term.cols, rows: tb.term.rows });
          if (tabs[chon] === tb) tb.term.focus();
          return;
        }
        if (m.type === "exit") {
          trangThai(tb, "Shell đã thoát" + (m.code == null ? "" : " (mã " + m.code + ")"), "off");
          tb.term.write("\r\n\x1b[2m[phiên đã kết thúc - bấm \"Khởi động lại\" hoặc đóng tab này]\x1b[0m\r\n");
          tb.sid = "";
          tb.dong = true;
          ghiTabs();
          return;
        }
        if (m.type === "error") {
          trangThai(tb, "Lỗi", "err");
          tb.term.write("\r\n\x1b[31m" + String(m.error || "Lỗi không rõ").replace(/\n/g, "\r\n") + "\x1b[0m\r\n");
          // Trần số phiên (tính CẢ tab trình duyệt khác) hoặc lỗi mở shell: id cũ đã vô dụng,
          // bỏ đi để lần sau tab này mở phiên mới sạch.
          tb.sid = "";
          tb.dong = true;
          ghiTabs();
        }
      };
      ws.onclose = function () {
        if (tb.dong) return;
        trangThai(tb, "Mất kết nối - đang nối lại...", "err");
        // đóng tab trình duyệt/ngủ máy/đổi mạng: shell vẫn sống, nối lại là thấy nguyên
        tb.dem = setTimeout(function () { noi(tb); }, 1500);
      };
      ws.onerror = function () { try { ws.close(); } catch (e) {} };
    }

    /** Dựng một tab mới (chưa nối): khung xterm riêng + bàn phím riêng + bộ đệm dòng riêng. */
    function taoTab(sid) {
      var tb = {
        so: ++demTab, sid: sid || "", host: document.createElement("div"),
        term: null, fit: null, ws: null, dong: false, dem: null, boDem: "",
        stChu: "Đang nối...", stMau: "",
      };
      tb.host.className = "term-host";
      hosts.appendChild(tb.host);
      tb.term = new window.Terminal({
        fontFamily: "'JetBrains Mono','SF Mono','Fira Code',Consolas,'Liberation Mono',ui-monospace,monospace",
        fontSize: 13,
        lineHeight: 1.2,
        cursorBlink: true,
        scrollback: 5000,
        theme: bangMau(),
        // XUỐNG DÒNG là chỗ hai chế độ khác nhau THẬT, và sai là vỡ ngay trước mắt.
        //
        // Chế độ pty: tty driver của hệ điều hành tự đổi "\n" thành "\r\n" (cờ ONLCR) trước khi
        // chữ ra khỏi shell, nên xterm nhận đủ cả về-đầu-dòng lẫn xuống-dòng.
        //
        // Chế độ ống (Windows): KHÔNG có tty driver nào ở giữa, output tới thẳng còn nguyên
        // "\n" trơ. Với xterm, "\n" chỉ là XUỐNG MỘT DÒNG - con trỏ giữ nguyên cột. Nên mỗi
        // dòng mới bắt đầu ở chỗ dòng trước kết thúc, và cả màn hình trôi thành bậc thang xiên
        // sang phải (chủ repo báo 2026-08-14, kèm ảnh `git help` chữ bay tứ tung).
        //
        // convertEol bảo xterm coi "\n" là "\r\n". CHỈ bật ở chế độ ống: bật luôn ở pty là cướp
        // mất khả năng dùng "\n" trần để dời con trỏ của chương trình toàn màn hình.
        convertEol: ong,
        // Chuột lăn cuộn màn hình chứ không gửi xuống shell trừ khi chương trình xin.
        macOptionIsMeta: true,
      });
      tb.fit = new window.FitAddon.FitAddon();
      tb.term.loadAddon(tb.fit);
      tb.term.open(tb.host);
      try { tb.fit.fit(); } catch (e) {}

      // ---- bàn phím ----
      if (!ong) {
        tb.term.onData(function (d) { gui(tb, { type: "in", data: d }); });
      } else {
        // Chế độ ống KHÔNG có tty driver, nên phần việc của nó (hiện chữ vừa gõ, sửa bằng
        // Backspace, gom một dòng rồi mới gửi) phải làm ở đây.
        tb.term.onData(function (d) {
          for (var i = 0; i < d.length; i++) {
            var c = d[i];
            if (c === "\r") { tb.term.write("\r\n"); gui(tb, { type: "in", data: tb.boDem + "\n" }); tb.boDem = ""; }
            else if (c === "\x7f") { if (tb.boDem) { tb.boDem = tb.boDem.slice(0, -1); tb.term.write("\b \b"); } }
            else if (c === "\x03") { tb.term.write("^C\r\n"); tb.boDem = ""; gui(tb, { type: "sig", name: "int" }); }
            else if (c >= " ") { tb.boDem += c; tb.term.write(c); }
          }
        });
      }
      tb.term.onResize(function (s) { gui(tb, { type: "resize", cols: s.cols, rows: s.rows }); });
      tabs.push(tb);
      return tb;
    }

    function veTabs() {
      var h = tabs.map(function (tb, i) {
        return '<span class="term-tab' + (i === chon ? " act" : "") + '" data-i="' + i + '">' +
          ic("terminal") + '<span class="term-tab-nhan">Phiên ' + tb.so + "</span>" +
          '<button class="term-tab-x" data-x="' + i + '" title="Đóng hẳn phiên này (giết shell)">' + ic("x") + "</button>" +
        "</span>";
      }).join("");
      var day = tabs.length >= maxTab;
      h += '<button class="term-tab-add" id="termTabAdd"' + (day ? " disabled" : "") +
        ' title="' + (day ? "Tối đa " + maxTab + " phiên cùng lúc" : "Mở thêm phiên (tab mới)") + '">' +
        ic("plus") + "</button>";
      tabsEl.innerHTML = h;
    }

    function chonTab(i) {
      if (i < 0) i = 0;
      if (i >= tabs.length) i = tabs.length - 1;
      chon = i;
      tabs.forEach(function (tb, k) { tb.host.classList.toggle("act", k === i); });
      veTabs();
      var tb = tabs[i];
      if (oSt) oSt.textContent = tb.stChu;
      if (oDot) oDot.className = "term-dot " + tb.stMau;
      // Tab vừa khuất không được refit (ResizeObserver chỉ lo tab đang xem) - bù ngay lúc hiện.
      try { tb.fit.fit(); } catch (e) {}
      tb.term.focus();
      ghiTabs();
    }

    function themTab() {
      if (tabs.length >= maxTab) return;   // nút "+" đã disabled, đây chỉ là lưới đỡ
      var tb = taoTab("");
      chonTab(tabs.length - 1);
      noi(tb);
    }

    /** Đóng TAB là đóng hẳn PHIÊN của nó (giết shell) - khác rời trang, vốn chỉ là thôi xem.
     *  Người dùng bấm dấu x trên tab tức là "xong việc với shell này", giữ shell mồ côi chạy
     *  ngầm thêm 30 phút chỉ tổ chiếm mất một suất trong trần số phiên. */
    function dongTab(i) {
      var tb = tabs[i];
      if (!tb) return;
      tb.dong = true;
      clearTimeout(tb.dem);
      ngatWs(tb);
      if (tb.sid) {
        var f = new FormData();
        f.append("session", tb.sid);
        fetch("/terminal/close", { method: "POST", body: f }).catch(function () {});
      }
      try { tb.term.dispose(); } catch (e) {}
      try { hosts.removeChild(tb.host); } catch (e) {}
      tabs.splice(i, 1);
      if (!tabs.length) { themTab(); return; }   // luôn giữ ít nhất một tab
      chonTab(i < chon ? chon - 1 : Math.min(chon, tabs.length - 1));
    }

    tabsEl.addEventListener("click", function (ev) {
      var t = ev.target;
      var x = t.closest && t.closest(".term-tab-x");
      if (x) { dongTab(x.getAttribute("data-x") | 0); return; }
      if (t.closest && t.closest("#termTabAdd")) { themTab(); return; }
      var tab = t.closest && t.closest(".term-tab");
      if (tab) chonTab(tab.getAttribute("data-i") | 0);
    });

    // ---- khung đổi cỡ (thu/mở sidebar, xoay điện thoại, kéo cửa sổ) ----
    var ro = null;
    if (window.ResizeObserver) {
      var hen = null;
      ro = new ResizeObserver(function () {
        clearTimeout(hen);
        hen = setTimeout(function () {
          var tb = tabs[chon];
          if (tb) { try { tb.fit.fit(); } catch (e) {} }
        }, 80);
      });
      ro.observe(hosts);
    }
    var doiTong = function () {
      var mau = bangMau();
      tabs.forEach(function (tb) { tb.term.options.theme = mau; });
    };
    window.addEventListener("javis-theme-change", doiTong);

    // ---- nút ----
    panel.querySelector("#termClear").onclick = function () {
      var tb = tabs[chon];
      if (tb) { tb.term.clear(); tb.term.focus(); }
    };
    // "Khởi động lại": đóng hẳn phiên của TAB ĐANG XEM rồi mở phiên sạch trong cùng tab.
    // Dùng khi shell treo hoặc muốn bắt đầu lại mà không mất chỗ đứng của tab.
    panel.querySelector("#termNew").onclick = function () {
      var tb = tabs[chon];
      if (!tb) return;
      var cu = tb.sid;
      tb.dong = true;
      ngatWs(tb);
      clearTimeout(tb.dem);
      tb.sid = "";
      tb.boDem = "";
      var xong = function () {
        ghiTabs();
        tb.term.reset();
        tb.dong = false;
        noi(tb);
      };
      var f = new FormData();
      f.append("session", cu);
      if (cu) fetch("/terminal/close", { method: "POST", body: f }).then(xong, xong);
      else xong();
    };
    hosts.addEventListener("mousedown", function () {
      setTimeout(function () { var tb = tabs[chon]; if (tb) tb.term.focus(); }, 0);
    });

    // ---- mở lại các tab của lần trước (F5, đổi trang rồi quay lại) ----
    var luu = docTabs();
    var dsSid = luu ? luu.ds.slice(0, maxTab) : [""];
    dsSid.forEach(function (sid) { taoTab(sid); });
    chonTab(luu ? luu.chon : 0);
    tabs.forEach(function (tb) { noi(tb); });
    // Bù một nhát fit sau khi trình duyệt vẽ xong khung (lần fit đầu chạy lúc panel còn đang
    // dựng nên có thể đo hụt vài dòng).
    setTimeout(function () {
      var tb = tabs[chon];
      if (tb) { try { tb.fit.fit(); } catch (e) {} }
    }, 60);

    return {
      huy: function () {
        window.removeEventListener("javis-theme-change", doiTong);
        if (ro) { try { ro.disconnect(); } catch (e) {} }
        tabs.forEach(function (tb) {
          tb.dong = true;
          clearTimeout(tb.dem);
          ngatWs(tb);
          try { tb.term.dispose(); } catch (e) {}
        });
        tabs = [];
        // KHÔNG gọi /terminal/close ở đây: rời trang chỉ là thôi xem. Shell của MỌI tab chạy
        // tiếp để lệnh dài (npm install, git clone) không chết oan, quay lại là thấy nguyên.
      },
    };
  }

  window.JavisCode = { render: render, roi: roi, CHUC_NANG: CHUC_NANG };
})();
