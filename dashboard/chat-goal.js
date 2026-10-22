// chat-goal.js - kho mục tiêu của /goal và THANH MỤC TIÊU ngay trên khung nhập (0.290.0).
//
// Chủ repo yêu cầu 22/10/2026 (kèm ảnh thanh "Pursuing goal" của Codex): có một mục tiêu thì hiện
// một thanh để bám theo, dừng hay xoá một chạm; nhiều mục tiêu thì hiện số ở đầu, bấm vào xổ ra
// danh sách. Trước bản này /goal chỉ sống trong một biến: đổi sang chat khác là mục tiêu tắt lặng,
// không có chỗ nào nhìn thấy nó đang chạy, muốn dừng phải gõ /goal clear.
//
// Chia đôi như chat-slash.js: phần THUẦN (tạo, tạm dừng, đếm giờ, đọc/ghi kho, dựng HTML) chạy được
// dưới node để test (tests/js/test_chat_goal.js); phần DOM ở cuối file chỉ chạy trong trình duyệt.
// File này chỉ GIỮ và VẼ mục tiêu. Chạy vòng, quyết định vòng tiếp vẫn là việc của chat-lenh.js: nút
// trên thanh gọi window.JavisLenh.goalAct().
//
// Mỗi hội thoại có tối đa MỘT mục tiêu. Mục tiêu chỉ chạy tiếp khi chat của nó đang mở, vì vòng tự
// động là trình duyệt gửi tin vào khung chat đang xem. Rời chat thì nó CHỜ (không tắt như trước),
// quay lại là nó chạy tiếp. Tải lại trang thì mục tiêu đang chạy chuyển sang tạm dừng: vòng lặp nằm
// trong trang nên tải lại là mất, người dùng bấm chạy tiếp là đi vòng sau.
(function () {
  "use strict";

  var KHO_KEY = "javis.goals.v1";
  var TOI_DA_KHO = 8;      // nhiều hơn thế là mục tiêu bị bỏ quên: cái cũ nhất rơi khỏi kho

  // Tên hàm là tw (không phải t) vì test_i18n quét mặt chữ các lời gọi tw để kiểm khoá có thật.
  function tw(khoa, bien) {
    if (typeof window !== "undefined" && window.t) return window.t(khoa, bien);
    try {
      var v = require("./i18n/vi.json")[khoa];
      if (v == null) return khoa;
      return String(v).replace(/\{(\w+)\}/g, function (m, ten) {
        return (bien && bien[ten] != null) ? String(bien[ten]) : m;
      });
    } catch (e) { return khoa; }
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ===================== HÀM THUẦN =====================

  var _dem = 0;
  function taoMucTieu(o, now) {
    o = o || {};
    now = +now || Date.now();
    _dem += 1;
    return {
      id: "g" + now.toString(36) + _dem,
      sid: o.sid || null,
      brain: o.brain || "",
      dk: String(o.dk || ""),
      vong: 1,
      toiDa: +o.toiDa || 5,
      left: "",
      state: "running",       // "running" | "paused"
      batDau: now,
      daChay: 0,              // ms đã chạy trước đoạn hiện tại (tạm dừng thì đồng hồ đứng)
      chayTu: now,            // mốc bắt đầu đoạn đang chạy, 0 khi tạm dừng
      // Trạng thái vòng, KHÔNG lưu xuống kho:
      ket: null,              // kết quả vòng vừa xong {marker, hoiLai} | {loi}
      xongLuot: false,        // lượt của vòng vừa đóng, chưa quyết định vòng tiếp
      tiepNgay: false,        // vòng sau đi luôn, khỏi quyết định (sau tạm dừng, sau tải lại trang)
      catNgang: false,        // lượt đang chạy bị cắt (bấm Dừng, gõ chen ngang): bỏ kết quả của nó
    };
  }

  function thoiGian(g, now) {
    if (!g) return 0;
    now = +now || Date.now();
    var ms = +g.daChay || 0;
    if (g.state === "running" && g.chayTu) ms += Math.max(0, now - g.chayTu);
    return ms;
  }

  // "3h 39m 9s", "12m 3s", "45s". Đơn vị viết tắt giống nhau ở mọi ngôn ngữ, như thanh của Codex.
  function dinhDangThoiGian(ms) {
    var s = Math.max(0, Math.floor((+ms || 0) / 1000));
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    if (h) return h + "h " + m + "m " + x + "s";
    if (m) return m + "m " + x + "s";
    return x + "s";
  }

  function tamDung(g, now) {
    if (!g || g.state !== "running") return false;
    now = +now || Date.now();
    g.daChay = thoiGian(g, now);
    g.chayTu = 0;
    g.state = "paused";
    return true;
  }

  function chayLai(g, now) {
    if (!g || g.state !== "paused") return false;
    g.state = "running";
    g.chayTu = +now || Date.now();
    return true;
  }

  // Trạng thái để HIỆN: mục tiêu đang chạy mà chat của nó không mở thì nó chỉ đang chờ.
  function trangThaiHien(g, sid) {
    if (!g) return "";
    if (g.state === "paused") return "paused";
    return (g.sid && g.sid !== sid) ? "waiting" : "running";
  }

  // Mục tiêu đứng trên thanh: của chat đang mở, không có thì cái đặt gần nhất.
  function chonChinh(ds, sid) {
    ds = ds || [];
    if (!ds.length) return null;
    var cua = ds.filter(function (g) { return g.sid === (sid || null); })[0];
    if (cua) return cua;
    return ds.slice().sort(function (a, b) { return b.batDau - a.batDau; })[0];
  }

  // Kho trong localStorage -> danh sách. Mục tiêu đang chạy khi trang tắt thì nay TẠM DỪNG và vòng sau
  // đi luôn khi bấm chạy tiếp: kết quả vòng cuối đã mất cùng trang, quyết định lại trên đó là đoán.
  // Mục tiêu chưa kịp có id phiên (tin đầu chưa gửi được) thì bỏ.
  function tuKho(raw) {
    var ds;
    try { ds = JSON.parse(raw || "[]"); } catch (e) { return []; }
    if (!Array.isArray(ds)) return [];
    var out = [];
    ds.forEach(function (o) {
      if (!o || typeof o !== "object" || !o.id || !o.sid || !String(o.dk || "").trim()) return;
      var g = taoMucTieu({ sid: o.sid, brain: o.brain, dk: o.dk, toiDa: o.toiDa }, +o.batDau || Date.now());
      g.id = String(o.id);
      g.vong = Math.max(1, +o.vong || 1);
      g.left = String(o.left || "");
      g.daChay = Math.max(0, +o.daChay || 0);
      g.chayTu = 0;
      g.state = "paused";
      g.tiepNgay = true;
      out.push(g);
    });
    return out.slice(-TOI_DA_KHO);
  }

  function veKho(ds, now) {
    now = +now || Date.now();
    return JSON.stringify((ds || []).filter(function (g) { return g && g.sid; }).map(function (g) {
      return { id: g.id, sid: g.sid, brain: g.brain, dk: g.dk, vong: g.vong, toiDa: g.toiDa, left: g.left,
               state: g.state, batDau: g.batDau, daChay: thoiGian(g, now) };
    }));
  }

  // ---- HTML của thanh ----
  var SVG = {
    target: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/></svg>',
    trash: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
    pause: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>',
    play: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4.5v15a1 1 0 0 0 1.5.86l12.5-7.5a1 1 0 0 0 0-1.72L8.5 3.64A1 1 0 0 0 7 4.5z"/></svg>',
    chevron: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 15 6-6 6 6"/></svg>',
  };

  function nhanTrangThai(st) {
    if (st === "paused") return tw("gb.paused");
    if (st === "waiting") return tw("gb.waiting");
    return tw("gb.pursuing");
  }

  function nutDung(g, cls) {
    var chay = g.state === "running";
    return '<button type="button" class="gb-btn ' + (cls || "") + '" data-act="' + (chay ? "pause" : "resume") +
      '" data-id="' + esc(g.id) + '" title="' + esc(chay ? tw("gb.pause") : tw("gb.resume")) +
      '" aria-label="' + esc(chay ? tw("gb.pause") : tw("gb.resume")) + '">' + (chay ? SVG.pause : SVG.play) + "</button>";
  }
  function nutXoa(g) {
    return '<button type="button" class="gb-btn gb-del" data-act="del" data-id="' + esc(g.id) + '" title="' +
      esc(tw("gb.del")) + '" aria-label="' + esc(tw("gb.del")) + '">' + SVG.trash + "</button>";
  }

  // ui = {mo: khung chi tiết đang mở, xo: danh sách đang xổ}. Không có mục tiêu thì chuỗi rỗng.
  function barHtml(ds, sid, now, ui) {
    ds = ds || [];
    ui = ui || {};
    var g = chonChinh(ds, sid);
    if (!g) return "";
    now = +now || Date.now();
    var st = trangThaiHien(g, sid);
    var n = ds.length;
    var h = '<div class="gb-row gb-' + st + '">';
    if (n > 1) {
      h += '<button type="button" class="gb-count" data-act="list" aria-haspopup="true" aria-expanded="' +
        (ui.xo ? "true" : "false") + '" title="' + esc(tw("gb.list", { n: n })) + '" aria-label="' +
        esc(tw("gb.list", { n: n })) + '">' + n + "</button>";
    }
    h += '<span class="gb-ic">' + SVG.target + "</span>";
    h += '<button type="button" class="gb-main" data-act="' + (st === "waiting" ? "open" : "expand") + '" data-id="' +
      esc(g.id) + '" aria-expanded="' + (ui.mo ? "true" : "false") + '">' +
      '<span class="gb-lbl">' + esc(nhanTrangThai(st)) + "</span>" +
      '<span class="gb-txt">' + esc(g.dk) + "</span></button>";
    h += '<span class="gb-time" data-gt="' + esc(g.id) + '">' + dinhDangThoiGian(thoiGian(g, now)) + "</span>";
    h += nutXoa(g) + nutDung(g);
    h += '<button type="button" class="gb-btn gb-exp" data-act="expand" data-id="' + esc(g.id) + '" aria-expanded="' +
      (ui.mo ? "true" : "false") + '" title="' + esc(ui.mo ? tw("gb.collapse") : tw("gb.expand")) + '" aria-label="' +
      esc(ui.mo ? tw("gb.collapse") : tw("gb.expand")) + '">' + SVG.chevron + "</button>";
    h += "</div>";
    if (ui.mo) {
      h += '<div class="gb-detail">';
      h += '<div class="gb-full">' + esc(g.dk) + "</div>";
      h += '<div class="gb-meta">' + esc(nhanTrangThai(st)) + " · " + esc(tw("gb.round", { v: g.vong, n: g.toiDa })) + "</div>";
      if (g.left) h += '<div class="gb-meta">' + esc(tw("gb.left", { left: g.left })) + "</div>";
      if (st === "waiting") {
        h += '<div class="gb-meta">' + esc(tw("gb.waiting_hint")) + "</div>";
        h += '<button type="button" class="gb-open" data-act="open" data-id="' + esc(g.id) + '">' + esc(tw("gb.open")) + "</button>";
      }
      h += "</div>";
    }
    if (ui.xo && n > 1) {
      h += '<div class="gb-pop" role="dialog" aria-label="' + esc(tw("gb.list_title")) + '">';
      h += '<div class="gb-pop-head">' + esc(tw("gb.list_title")) + "</div>";
      ds.slice().sort(function (a, b) { return b.batDau - a.batDau; }).forEach(function (x) {
        var s2 = trangThaiHien(x, sid);
        h += '<div class="gb-item gb-' + s2 + (x.sid === (sid || null) ? " gb-cur" : "") + '">' +
          '<span class="gb-dot" aria-hidden="true"></span>' +
          '<button type="button" class="gb-item-main" data-act="open" data-id="' + esc(x.id) + '">' +
          '<span class="gb-item-txt">' + esc(x.dk) + "</span>" +
          '<span class="gb-item-meta">' + esc(nhanTrangThai(s2)) + " · " + esc(tw("gb.round", { v: x.vong, n: x.toiDa })) +
          ' · <span data-gt="' + esc(x.id) + '">' + dinhDangThoiGian(thoiGian(x, now)) + "</span></span></button>" +
          nutDung(x) + nutXoa(x) + "</div>";
      });
      h += "</div>";
    }
    return h;
  }

  // ===================== KHO (chung cho trình duyệt và node) =====================
  var ds = [];
  var nghe = [];

  function doc() {
    try { ds = tuKho(localStorage.getItem(KHO_KEY)); } catch (e) { ds = []; }
  }
  function luu() {
    try { localStorage.setItem(KHO_KEY, veKho(ds)); } catch (e) { /* chế độ riêng tư, node */ }
    nghe.forEach(function (f) { try { f(); } catch (e) { /* một người nghe hỏng không chặn người khác */ } });
  }

  var api = {
    KHO_KEY: KHO_KEY,
    taoMucTieu: taoMucTieu,
    thoiGian: thoiGian,
    dinhDangThoiGian: dinhDangThoiGian,
    tamDung: tamDung,
    chayLai: chayLai,
    trangThaiHien: trangThaiHien,
    chonChinh: chonChinh,
    tuKho: tuKho,
    veKho: veKho,
    barHtml: barHtml,
    // kho
    ds: function () { return ds.slice(); },
    theoSid: function (sid) { return ds.filter(function (g) { return g.sid === (sid || null); })[0] || null; },
    theoId: function (id) { return ds.filter(function (g) { return g.id === id; })[0] || null; },
    them: function (o, now) {
      var g = taoMucTieu(o, now);
      ds = ds.filter(function (x) { return x.sid !== g.sid; });
      ds.push(g);
      if (ds.length > TOI_DA_KHO) ds = ds.slice(-TOI_DA_KHO);
      luu();
      return g;
    },
    xoa: function (id) { ds = ds.filter(function (g) { return g.id !== id; }); luu(); },
    luu: luu,
    doc: doc,
    nghe: function (f) { nghe.push(f); },
    _datLai: function () { ds = []; nghe = []; },
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window === "undefined" || typeof document === "undefined") return;
  window.JavisGoals = api;
  doc();

  // ===================== THANH (chỉ trình duyệt) =====================
  var ui = { mo: false, xo: false };
  var hen = null;

  function sidHienTai() {
    var s = window.JavisSessions;
    try { return (s && s.current()) || null; } catch (e) { return null; }
  }
  function brainHienTai() {
    var s = window.JavisSessions;
    try { return (s && s.brain()) || ""; } catch (e) { return ""; }
  }
  // Mục tiêu của brain khác không hiện: bấm vào không mở được chat của nó từ brain đang chọn.
  function dsHien() {
    var b = brainHienTai();
    return ds.filter(function (g) { return !g.brain || !b || g.brain === b; });
  }

  function ve() {
    var bar = document.getElementById("goalBar");
    if (!bar) return;
    var list = dsHien();
    if (list.length < 2) ui.xo = false;
    var html = barHtml(list, sidHienTai(), Date.now(), ui);
    bar.innerHTML = html;
    bar.hidden = !html;
    if (hen) { clearInterval(hen); hen = null; }
    if (list.some(function (g) { return g.state === "running"; })) hen = setInterval(demGio, 1000);
  }

  // Mỗi giây chỉ thay chữ đồng hồ, không dựng lại thanh: dựng lại là mất focus của nút đang bấm.
  function demGio() {
    var now = Date.now();
    var els = document.querySelectorAll("#goalBar [data-gt]");
    for (var i = 0; i < els.length; i++) {
      var g = api.theoId(els[i].getAttribute("data-gt"));
      if (g) els[i].textContent = dinhDangThoiGian(thoiGian(g, now));
    }
  }

  function bam(e) {
    var b = e.target.closest("[data-act]");
    if (!b) return;
    var act = b.getAttribute("data-act"), id = b.getAttribute("data-id");
    if (act === "list") { ui.xo = !ui.xo; ve(); return; }
    if (act === "expand") { ui.mo = !ui.mo; ve(); return; }
    ui.xo = false;
    if (window.JavisLenh && window.JavisLenh.goalAct) window.JavisLenh.goalAct(act, id);
    ve();
  }

  api.ve = ve;
  nghe.push(ve);

  function gan() {
    var bar = document.getElementById("goalBar");
    if (!bar) return;
    bar.addEventListener("click", bam);
    // Bấm ra ngoài thì danh sách xổ thu lại, như khung đổi model. Soi đường đi của cú bấm chứ không soi
    // e.target: bấm trong thanh là thanh vẽ lại ngay, nút vừa bấm đã rời DOM nên contains() trả false.
    document.addEventListener("click", function (e) {
      var duong = e.composedPath ? e.composedPath() : [e.target];
      if (ui.xo && duong.indexOf(bar) === -1) { ui.xo = false; ve(); }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && ui.xo) { ui.xo = false; ve(); }
    });
    window.addEventListener("javis:sessions-changed", ve);
    window.addEventListener("javis:i18n", ve);
    ve();
  }
  if (document.getElementById("goalBar")) gan();
  else document.addEventListener("DOMContentLoaded", gan);
})();
