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
  var KHOA_PHIEN = "javis.code.phien";    // id phiên terminal của TAB TRÌNH DUYỆT này

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
  // Chức năng 1: Terminal
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

  /** Dựng terminal thật: xterm + WebSocket + thanh trạng thái. Trả { huy }. */
  function dungTerminal(panel, st) {
    var ong = st.che_do === "ong";     // Windows: không có pty, chạy chế độ gõ theo dòng
    panel.innerHTML =
      '<div class="term-wrap">' +
        '<div class="term-bar">' +
          '<span class="term-dot" id="termDot"></span>' +
          '<span class="term-st" id="termSt">Đang nối...</span>' +
          '<span class="term-cwd" title="Thư mục làm việc">' + ic("folder-tree") + " " + esc(st.cwd) + "</span>" +
          '<span class="term-sp"></span>' +
          '<button class="term-btn" id="termClear" title="Xoá màn hình (Ctrl+L)">' + ic("eraser") + " Xoá</button>" +
          '<button class="term-btn" id="termNew" title="Đóng phiên hiện tại và mở phiên mới">' + ic("plus") + " Phiên mới</button>" +
        "</div>" +
        (ong ? '<div class="term-note">' + ic("triangle-alert", { cls: "ic-warn" }) +
          " <b>Chế độ đơn giản (Windows).</b> Gõ nguyên một dòng rồi Enter. Không có gợi ý Tab, " +
          "không chạy được chương trình toàn màn hình như <code>vim</code> hay <code>htop</code>." +
          "</div>" : "") +
        '<div class="term-host" id="termHost"></div>' +
      "</div>";

    var host = panel.querySelector("#termHost");
    var oSt = panel.querySelector("#termSt");
    var oDot = panel.querySelector("#termDot");
    var term = new window.Terminal({
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
    var fit = new window.FitAddon.FitAddon();
    term.loadAddon(fit);
    term.open(host);
    try { fit.fit(); } catch (e) {}

    var ws = null, dong = false, dem = null, hangCho = "";
    var boDem = "";           // đệm dòng đang gõ, CHỈ dùng ở chế độ ống

    function trangThai(chu, mau) {
      if (oSt) oSt.textContent = chu;
      if (oDot) oDot.className = "term-dot " + (mau || "");
    }
    function gui(o) {
      if (ws && ws.readyState === 1) { ws.send(JSON.stringify(o)); return true; }
      return false;
    }
    /** Bỏ hẳn socket hiện tại: GỠ handler TRƯỚC rồi mới đóng.
     *
     * Không gỡ thì `onclose` của socket cũ vẫn nổ sau đó, và nó là hàm tự-nối-lại. Bấm "Phiên
     * mới" đúng lúc là có hai socket cùng chạy, mỗi cái viết vào một phiên khác nhau - màn hình
     * trộn lẫn hai shell mà nhìn thì tưởng terminal loạn. */
    function ngatWs() {
      if (!ws) return;
      ws.onclose = null; ws.onmessage = null; ws.onerror = null;
      try { ws.close(); } catch (e) {}
      ws = null;
    }

    function noi() {
      var q = "brain=" + encodeURIComponent(brain()) +
              "&cols=" + term.cols + "&rows=" + term.rows +
              "&session=" + encodeURIComponent(nho(KHOA_PHIEN));
      trangThai("Đang nối...", "");
      ws = new WebSocket(WS_GOC + "/ws/terminal?" + q);
      ws.onmessage = function (ev) {
        var m;
        try { m = JSON.parse(ev.data); } catch (e) { return; }
        if (m.type === "out") { term.write(m.data || ""); return; }
        if (m.type === "hello") {
          nho(KHOA_PHIEN, m.session);
          trangThai((m.che_do === "ong" ? "Chế độ đơn giản" : "Đang chạy") + " · " + (m.shell || "shell"), "ok");
          gui({ type: "resize", cols: term.cols, rows: term.rows });
          term.focus();
          return;
        }
        if (m.type === "exit") {
          trangThai("Shell đã thoát" + (m.code == null ? "" : " (mã " + m.code + ")"), "off");
          term.write("\r\n\x1b[2m[phiên đã kết thúc - bấm \"Phiên mới\" để mở lại]\x1b[0m\r\n");
          xoaNho(KHOA_PHIEN);
          dong = true;
          return;
        }
        if (m.type === "error") {
          trangThai("Lỗi", "err");
          term.write("\r\n\x1b[31m" + String(m.error || "Lỗi không rõ").replace(/\n/g, "\r\n") + "\x1b[0m\r\n");
          // Trần số phiên: id cũ trong tay đã vô dụng, bỏ đi để lần sau mở phiên mới sạch.
          xoaNho(KHOA_PHIEN);
          dong = true;
        }
      };
      ws.onclose = function () {
        if (dong) return;
        trangThai("Mất kết nối - đang nối lại...", "err");
        dem = setTimeout(noi, 1500);     // đóng tab/ngủ máy/đổi mạng: shell vẫn sống, nối lại là thấy nguyên
      };
      ws.onerror = function () { try { ws.close(); } catch (e) {} };
    }

    // ---- bàn phím ----
    if (!ong) {
      term.onData(function (d) { gui({ type: "in", data: d }); });
    } else {
      // Chế độ ống KHÔNG có tty driver, nên phần việc của nó (hiện chữ vừa gõ, sửa bằng
      // Backspace, gom một dòng rồi mới gửi) phải làm ở đây.
      term.onData(function (d) {
        for (var i = 0; i < d.length; i++) {
          var c = d[i];
          if (c === "\r") { term.write("\r\n"); gui({ type: "in", data: boDem + "\n" }); boDem = ""; }
          else if (c === "\x7f") { if (boDem) { boDem = boDem.slice(0, -1); term.write("\b \b"); } }
          else if (c === "\x03") { term.write("^C\r\n"); boDem = ""; gui({ type: "sig", name: "int" }); }
          else if (c >= " ") { boDem += c; term.write(c); }
        }
      });
    }
    term.onResize(function (s) { gui({ type: "resize", cols: s.cols, rows: s.rows }); });

    // ---- khung đổi cỡ (thu/mở sidebar, xoay điện thoại, kéo cửa sổ) ----
    var ro = null;
    if (window.ResizeObserver) {
      var hen = null;
      ro = new ResizeObserver(function () {
        clearTimeout(hen);
        hen = setTimeout(function () { try { fit.fit(); } catch (e) {} }, 80);
      });
      ro.observe(host);
    }
    var doiTong = function () { term.options.theme = bangMau(); };
    window.addEventListener("javis-theme-change", doiTong);

    // ---- nút ----
    panel.querySelector("#termClear").onclick = function () { term.clear(); term.focus(); };
    panel.querySelector("#termNew").onclick = function () {
      var cu = nho(KHOA_PHIEN);
      dong = true;
      ngatWs();
      clearTimeout(dem);
      var f = new FormData(); f.append("session", cu);
      var xong = function () {
        xoaNho(KHOA_PHIEN);
        term.reset();
        dong = false;
        noi();
      };
      if (cu) fetch("/terminal/close", { method: "POST", body: f }).then(xong, xong);
      else xong();
    };
    host.addEventListener("mousedown", function () { setTimeout(function () { term.focus(); }, 0); });

    noi();
    // Bù một nhát fit sau khi trình duyệt vẽ xong khung (lần fit đầu chạy lúc panel còn đang
    // dựng nên có thể đo hụt vài dòng).
    setTimeout(function () { try { fit.fit(); } catch (e) {} }, 60);

    return {
      huy: function () {
        dong = true;
        clearTimeout(dem);
        window.removeEventListener("javis-theme-change", doiTong);
        if (ro) { try { ro.disconnect(); } catch (e) {} }
        ngatWs();
        try { term.dispose(); } catch (e) {}
        // KHÔNG gọi /terminal/close ở đây: rời tab chỉ là thôi xem. Shell chạy tiếp để lệnh
        // dài (npm install, git clone) không chết oan, quay lại là thấy nguyên màn hình.
      },
    };
  }

  window.JavisCode = { render: render, roi: roi, CHUC_NANG: CHUC_NANG };
})();
