// chat-lenh.js - lệnh "/" HỆ THỐNG của khung chat web: /help /status /model /brain /retry /usage
// /tasks /compact /plan /memory /export /goal.
//
// Vì sao tách khỏi chat-slash.js: file đó lo NHẬN DIỆN lệnh (parse, menu, route) và phải test được
// bằng node mà không cần trình duyệt. File này lo CHẠY lệnh - gọi máy chủ, đổi model, tải file - nên
// dính vào DOM và fetch. Phần định dạng và phần quyết định của /goal vẫn là hàm thuần, xuất ra
// module.exports để test (tests/js/test_chat_lenh.js), giống chat-ask.js và chat-slash.js.
//
// Nguyên tắc: máy chủ Javis tự xử lý, KHÔNG mượn lệnh có sẵn của Claude Code. Sáu engine API,
// Codex, Grok, Antigravity đều không có /compact hay /plan của Claude Code, nên nếu dựa vào đó thì
// năng lực đổi theo bộ não - trái với nguyên tắc "năng lực của Javis không đổi theo model".
//
// Trả lời của lệnh hiện thành một bong bóng CỤC BỘ (appendLenhReply trong app.js): không gửi cho
// model, không lưu vào hội thoại. Ngoại lệ là /plan, /goal và /retry - ba lệnh này gửi một tin thật.
(function () {
  "use strict";

  // Trần số vòng của /goal. Model đề xuất "chưa xong", MÃ quyết định có chạy tiếp không - nếu không
  // có trần thì một mục tiêu không bao giờ đạt được là một vòng lặp đốt token vô hạn.
  var GOAL_TOI_DA = 8;
  var GOAL_RE = /<!--\s*JAVIS_GOAL:\s*([\s\S]*?)\s*-->/g;

  // Chữ hiện ra lấy từ từ điển. Trong trình duyệt là window.t; dưới node (test) không có window
  // nên đọc thẳng vi.json. Tên hàm là tw chứ không phải t vì test_i18n quét mặt chữ các lời gọi tw để
  // kiểm khoá có thật trong vi.json.
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

  // ===================== HÀM THUẦN (test bằng node) =====================

  // Bóc dòng ẩn JAVIS_GOAL khỏi câu trả lời. Dòng CUỐI thắng; dòng hỏng (JSON sai, thiếu `done`
  // kiểu boolean) coi như không có - bên gọi khi đó DỪNG chứ không đoán "chưa xong".
  function tachMucTieu(text) {
    var s = String(text == null ? "" : text);
    if (s.indexOf("JAVIS_GOAL") < 0) return { clean: s, goal: null };
    var goal = null;
    var clean = s.replace(GOAL_RE, function (_m, j) {
      goal = null;
      try {
        var o = JSON.parse(j);
        if (o && typeof o.done === "boolean") {
          goal = { done: o.done, left: String(o.left || "").trim().slice(0, 300) };
        }
      } catch (e) { /* khối hỏng: bỏ */ }
      return "";
    }).replace(/\n{3,}/g, "\n\n").trim();
    return { clean: clean, goal: goal };
  }

  function chuanSo(s) { return String(s || "").toLowerCase().replace(/\s+/g, " ").trim(); }

  // Sau MỘT vòng của /goal: chạy tiếp hay dừng, và dừng vì sao. `st` = {vong, toiDa, left},
  // `ket` = {loi, hoiLai, marker}. Thứ tự các cổng là thứ tự an toàn: lỗi và câu hỏi ngược đứng
  // trước mọi thứ vì lúc đó người dùng đang cần lên tiếng, không phải Javis cần chạy thêm.
  function quyetDinhVongTiep(st, ket) {
    ket = ket || {};
    if (ket.loi) return { act: "dung", ly: "loi" };
    if (ket.hoiLai) return { act: "dung", ly: "hoi_lai" };
    var m = ket.marker;
    if (!m) return { act: "dung", ly: "khong_bao" };
    if (m.done) return { act: "dung", ly: "dat" };
    if (st.vong >= st.toiDa) return { act: "dung", ly: "het_vong" };
    // Hai vòng liền báo Y HỆT phần còn thiếu = không tiến triển: chạy thêm chỉ tốn token.
    if (st.left && m.left && chuanSo(st.left) === chuanSo(m.left)) {
      return { act: "dung", ly: "khong_tien_trien", left: m.left };
    }
    return { act: "tiep", left: m.left || "" };
  }

  function gonSo(n) {
    n = +n || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "k";
    return String(Math.round(n));
  }
  function tien(x) { return "$" + (+x || 0).toFixed(2); }
  function cat(s, n) { s = String(s || ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; }

  function dinhDangTrangThai(d) {
    d = d || {};
    var model = d.model || tw("lenh.st_default_model");
    var muc = d.pinned ? tw("lenh.st_pin") : tw("lenh.st_follow");
    var dong = [tw("lenh.st_title")];
    dong.push("- " + tw("lenh.st_engine", { nha: d.provider_label || d.provider || "?", model: model, muc: muc }));
    dong.push("- " + tw("lenh.st_brain", { ten: d.brain || "" }));
    if (d.msg_count) {
      var c = tw("lenh.st_chat", { n: d.msg_count });
      if (d.compact_count) c += ", " + tw("lenh.st_compacted", { n: d.compact_count });
      dong.push("- " + c);
    } else {
      dong.push("- " + tw("lenh.st_chat_none"));
    }
    if (d.last_input_tokens) dong.push("- " + tw("lenh.st_ctx", { tok: gonSo(d.last_input_tokens) }));
    dong.push("- " + (d.running ? tw("lenh.st_busy_yes") : tw("lenh.st_busy_no")));
    if (d.version) dong.push("- " + tw("lenh.st_version", { v: d.version }));
    return dong.join("\n");
  }

  function dongDung(nhan, tot) {
    tot = tot || {};
    if (!tot.turns) return "- " + tw("lenh.us_none", { nhan: nhan });
    var chi = (+tot.cost || 0) > 0 ? tw("lenh.us_cost", { tien: tien(tot.cost) }) : "";
    return "- " + tw("lenh.us_line", {
      nhan: nhan, luot: tot.turns, vao: gonSo(tot.in), ra: gonSo(tot.out), chi: chi,
    });
  }

  function dinhDangMucDung(d) {
    d = d || {};
    var hn = d.today || {}, tc = d.all_time || {};
    var dong = [tw("lenh.us_title"), dongDung(tw("lenh.us_today"), hn.total)];
    (hn.items || []).slice(0, 5).forEach(function (it) {
      dong.push("  - " + (it.provider || "?") + " " + (it.model || "") + ": "
        + tw("lenh.us_item", { luot: it.turns || 0, tok: gonSo((it.in || 0) + (it.out || 0)) }));
    });
    dong.push(dongDung(tw("lenh.us_all"), tc.total));
    if (d.openrouter && d.openrouter.remaining != null) {
      dong.push("- " + tw("lenh.us_or", { tien: tien(d.openrouter.remaining) }));
    }
    dong.push("", tw("lenh.us_foot"));
    return dong.join("\n");
  }

  function dinhDangViec(d, moi) {
    d = d || {};
    moi = moi || 5;
    var cot = d.columns || {};
    var dong = [tw("lenh.tk_title")];
    if (d.orchestration === "off") dong.push(tw("lenh.tk_off"));
    else if (d.orchestration === "manual") dong.push(tw("lenh.tk_manual"));
    var nhom = [
      ["running", tw("lenh.tk_running")],
      ["blocked", tw("lenh.tk_blocked")],
      ["review", tw("lenh.tk_review")],
      ["ready", tw("lenh.tk_queue")],
      ["todo", tw("lenh.tk_queue")],
      ["triage", tw("lenh.tk_queue")],
    ];
    var co = false;
    nhom.forEach(function (g) {
      var ds = cot[g[0]] || [];
      if (!ds.length) return;
      co = true;
      dong.push("", "**" + g[1] + " (" + ds.length + ")**");
      ds.slice(0, moi).forEach(function (t) { dong.push("- " + cat(t.title || t.id || "?", 70)); });
      if (ds.length > moi) dong.push("- " + tw("lenh.tk_more", { n: ds.length - moi }));
    });
    if (!co) dong.push(tw("lenh.tk_empty"));
    if (d.completed_24h) dong.push("", tw("lenh.tk_done24", { n: d.completed_24h }));
    dong.push("", tw("lenh.tk_foot"));
    return dong.join("\n");
  }

  // MEMORY.md nằm trong thư mục memory/ và các link trong nó là link TƯƠNG ĐỐI so với thư mục đó,
  // còn khung chat giải link tương đối theo GỐC brain. Không thêm tiền tố thì mọi link trong bong
  // bóng trỏ vào hư không.
  function vaLinkBoNho(md) {
    return String(md || "").replace(/\]\((?!https?:|mailto:|\/|#)([^)\s]+)\)/g, "](memory/$1)");
  }

  function dinhDangBoNho(d) {
    d = d || {};
    var text = String(d.text || "").trim();
    if (!text) return tw("lenh.mem_empty");
    var dong = [tw("lenh.mem_title", { ten: d.brain || "" })];
    if (d.facts) dong.push(tw("lenh.mem_facts", { n: d.facts }));
    dong.push("", vaLinkBoNho(text));
    if (d.cat_bot) dong.push("", tw("lenh.mem_cut"));
    return dong.join("\n");
  }

  // Bỏ mọi khối điều khiển <!-- JAVIS_...: ... --> khỏi tin của Javis trước khi xuất. Chúng vô
  // hình trong khung chat nhưng sẽ hiện nguyên hình trong file markdown.
  function boKhoiDieuKhien(s) {
    return String(s || "").replace(/<!--\s*JAVIS_[A-Z_]+:[\s\S]*?-->/g, "").replace(/\n{3,}/g, "\n\n").trim();
  }

  function dinhDangXuat(sess, gio, lamSachTinNguoi) {
    sess = sess || {};
    var sachNguoi = lamSachTinNguoi || function (x) { return x; };
    var dong = ["# " + (sess.title || "Javis"), "", "_" + tw("lenh.ex_head", { gio: gio || "" }) + "_"];
    (sess.messages || []).forEach(function (m) {
      var nguoi = m.role === "user";
      if (!nguoi && m.role !== "assistant") return;
      var noi = nguoi ? sachNguoi(m.content || "") : boKhoiDieuKhien(m.content || "");
      if (!String(noi).trim()) return;
      dong.push("", "## " + (nguoi ? tw("lenh.ex_you") : "Javis"), "", String(noi).trim());
    });
    return dong.join("\n") + "\n";
  }

  function tenFileXuat(title, ngay) {
    var slug = String(title || "").normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/[\u0111\u0110]/g, "d").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
    return "javis-" + (slug || "hoi-thoai") + "-" + (ngay || "") + ".md";
  }

  // Khớp tên theo hai bậc: đúng nguyên tên thì thắng, không thì khớp một phần. Ra nhiều hơn một
  // thì trả `nhieu` chứ KHÔNG đoán - đổi nhầm brain là làm việc trên bộ nhớ của người khác.
  function khopTen(ds, q, layTen) {
    var k = chuanSo(q);
    var dung = ds.filter(function (x) { return chuanSo(layTen(x)) === k; });
    var gan = dung.length ? dung : ds.filter(function (x) { return chuanSo(layTen(x)).indexOf(k) !== -1; });
    if (gan.length === 1) return { hit: gan[0], nhieu: [] };
    return { hit: null, nhieu: gan };
  }

  function laLenhTat(arg) {
    var k = chuanSo(arg).normalize("NFD").replace(/[̀-ͯ]/g, "");
    return ["clear", "off", "stop", "tat", "xoa", "huy"].indexOf(k) !== -1;
  }

  // ===================== PHẦN DOM / MẠNG (chỉ trình duyệt) =====================
  var goal = null;   // {sid, dk, vong, toiDa, left, ket} - MỘT mục tiêu đang chạy trong khung chat

  function chatApi() { return (typeof window !== "undefined" && window.JavisChatApi) || null; }
  function ghi(md) { var a = chatApi(); if (a) a.note(md); }

  async function layJson(url, opt) {
    var r = await fetch(url, opt);
    var d = null;
    try { d = await r.json(); } catch (e) { /* thân rỗng */ }
    return { ok: r.ok, status: r.status, d: d };
  }

  function brainHienTai() { var a = chatApi(); return a ? a.brain() : "brain"; }

  // Máy chủ là nguồn DUY NHẤT của khối chỉ dẫn (server/lenh_he_thong.py): Telegram dùng chung nó,
  // nên xin từ đó chứ không chép chữ sang đây rồi để hai bản lệch nhau.
  async function layKhoi(thamSo) {
    var fd = new FormData();
    Object.keys(thamSo).forEach(function (k) { fd.append(k, String(thamSo[k])); });
    var r = await layJson("/slash/block", { method: "POST", body: fd });
    return (r.ok && r.d && r.d.block) || "";
  }

  function lenhHelp() {
    var ds = window.JavisSlash ? window.JavisSlash.buildMenu([], [], []) : [];
    ds = ds.filter(function (x) { return x.kind === "session" || x.kind === "system"; });
    var dong = [tw("lenh.help_title")];
    ds.forEach(function (x) { dong.push("- `/" + x.cmd + "` - " + x.desc); });
    dong.push("", tw("lenh.help_foot"));
    ghi(dong.join("\n"));
  }

  async function lenhStatus() {
    var a = chatApi();
    var r = await layJson("/slash/status?session_id=" + encodeURIComponent(a.sid() || "")
      + "&brain=" + encodeURIComponent(brainHienTai()));
    if (!r.ok) return ghi(tw("lenh.err_net"));
    ghi(dinhDangTrangThai(r.d));
  }

  async function lenhModel(arg) {
    var mb = window.JavisModelBar;
    if (!mb) return ghi(tw("lenh.err_net"));
    if (!arg) {
      // Bảng chọn nằm ở thanh model dưới khung chat; ẩn (điện thoại, đang thu gọn) thì nói model
      // hiện tại thay vì im lặng.
      if (mb.open()) return;
      var ht = mb.hienTai();
      return ghi(tw("lenh.model_now", { nha: ht.label, model: ht.model || tw("lenh.st_default_model") }));
    }
    var r = await mb.chon(arg);
    if (r.kind === "one") return ghi(tw("lenh.model_set", { nha: r.label, model: r.model }));
    if (r.kind === "many") return ghi(tw("lenh.model_many", { q: arg, ds: r.ds.join(", ") }));
    ghi(tw("lenh.model_none", { q: arg }));
  }

  async function lenhBrain(arg) {
    var sel = document.getElementById("graphSource");
    var r = await layJson("/brains");
    var brains = (r.d && r.d.brains) || [];
    if (!r.ok || !sel) return ghi(tw("lenh.err_net"));
    var giaTri = function (b) { return b.is_default ? "brain" : "path:" + b.path; };
    if (!arg) {
      var dong = [tw("lenh.brain_title")];
      brains.forEach(function (b) {
        dong.push("- " + b.name + (giaTri(b) === sel.value ? " " + tw("lenh.brain_cur") : ""));
      });
      dong.push("", tw("lenh.brain_hint"));
      return ghi(dong.join("\n"));
    }
    var k = khopTen(brains, arg, function (b) { return b.name; });
    if (k.hit) {
      var v = giaTri(k.hit);
      sel.value = v;
      try { localStorage.setItem("javis.graphSource", v); } catch (e) { /* chế độ riêng tư */ }
      sel.dispatchEvent(new Event("change"));
      return ghi(tw("lenh.brain_set", { ten: k.hit.name }));
    }
    if (k.nhieu.length) {
      return ghi(tw("lenh.brain_many", { q: arg, ds: k.nhieu.slice(0, 6).map(function (b) { return b.name; }).join(", ") }));
    }
    ghi(tw("lenh.brain_none", { q: arg }));
  }

  function lenhRetry() {
    var a = chatApi();
    var t = a.lastUserText();
    if (!t) return ghi(tw("lenh.retry_none"));
    if (a.dangChay(a.sid())) return ghi(tw("lenh.busy"));
    a.send(t);
  }

  async function lenhUsage() {
    var r = await layJson("/usage");
    if (!r.ok) return ghi(tw("lenh.err_net"));
    ghi(dinhDangMucDung(r.d));
  }

  async function lenhTasks() {
    var r = await layJson("/kanban?brain=" + encodeURIComponent(brainHienTai()));
    if (!r.ok) return ghi(tw("lenh.err_net"));
    ghi(dinhDangViec(r.d));
  }

  async function lenhCompact() {
    var a = chatApi();
    var sid = a.sid();
    if (!sid) return ghi(tw("lenh.cp_none"));
    var r = await layJson("/sessions/" + encodeURIComponent(sid) + "/compact", { method: "POST" });
    var d = r.d || {};
    if (r.status === 404) return ghi(tw("lenh.cp_none"));
    if (r.status === 409) return ghi(tw("lenh.cp_busy"));
    if (!r.ok) return ghi(tw("lenh.err_net"));
    var nha = d.provider || "";
    if (d.ok) {
      if (d.cach === "tom_tat") return ghi(tw("lenh.cp_summary", { n: d.da_nen || 0 }));
      if (d.cach === "xoay_mach") return ghi(tw("lenh.cp_rotate", { nha: nha }));
      if (d.cach === "khong_co_mach") return ghi(tw("lenh.cp_nothread"));
      return ghi(tw("lenh.cp_already"));
    }
    if (d.ly_do === "ngan") return ghi(tw("lenh.cp_short", { n: d.so_tin || 0 }));
    if (d.ly_do === "khong_ho_tro") return ghi(tw("lenh.cp_unsupported", { nha: nha }));
    ghi(tw("lenh.cp_fail"));
  }

  async function lenhPlan(arg) {
    if (!arg) return ghi(tw("lenh.plan_need"));
    var khoi = await layKhoi({ kind: "plan" });
    if (!khoi) return ghi(tw("lenh.err_net"));
    chatApi().send(arg, { prefix: khoi });
  }

  async function lenhMemory() {
    var r = await layJson("/slash/memory?brain=" + encodeURIComponent(brainHienTai()));
    if (!r.ok) return ghi(tw("lenh.err_net"));
    ghi(dinhDangBoNho(r.d));
  }

  async function lenhExport() {
    var a = chatApi();
    var sid = a.sid();
    if (!sid) return ghi(tw("lenh.ex_none"));
    var r = await layJson("/sessions/" + encodeURIComponent(sid));
    if (!r.ok || !r.d || !(r.d.messages || []).length) return ghi(tw("lenh.ex_none"));
    var ngay = new Date().toISOString().slice(0, 10);
    var md = dinhDangXuat(r.d, new Date().toLocaleString(), a.sach);
    var ten = tenFileXuat(r.d.title, ngay);
    var url = URL.createObjectURL(new Blob([md], { type: "text/markdown;charset=utf-8" }));
    var link = document.createElement("a");
    link.href = url; link.download = ten;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
    ghi(tw("lenh.ex_done", { ten: ten }));
  }

  // ---- /goal ----
  async function lenhGoal(arg) {
    if (laLenhTat(arg)) {
      if (goal) { goal = null; return ghi(tw("lenh.goal_stopped")); }
      return ghi(tw("lenh.goal_none"));
    }
    if (!arg) {
      if (goal) return ghi(tw("lenh.goal_status", { dk: cat(goal.dk, 120), v: goal.vong, n: goal.toiDa }));
      return ghi(tw("lenh.goal_need", { n: GOAL_TOI_DA }));
    }
    var khoi = await layKhoi({ kind: "goal", dk: arg, vong: 1, toi_da: GOAL_TOI_DA });
    if (!khoi) return ghi(tw("lenh.err_net"));
    goal = { sid: null, dk: arg, vong: 1, toiDa: GOAL_TOI_DA, left: "", ket: null };
    ghi(tw("lenh.goal_start", { dk: cat(arg, 120), n: GOAL_TOI_DA }));
    chatApi().send(arg, { prefix: khoi, goal: true });
  }

  // app.js gọi ngay sau khi biết id phiên của tin vừa gửi: gắn mục tiêu vào ĐÚNG phiên đó.
  function daGui(sid, opts) {
    if (goal && opts && opts.goal && !goal.sid) goal.sid = sid;
  }

  // Người dùng gõ một tin thường (không phải vòng của /goal) trong lúc mục tiêu đang chạy: tin của
  // họ lên trước. Tiếp tục chạy vòng tự động ngay dưới một câu họ vừa nói là giành lời của họ.
  function chenNgang(sid) {
    if (goal && (!goal.sid || goal.sid === sid)) {
      goal = null;
      ghi(tw("lenh.goal_takeover"));
    }
  }

  function dungMucTieu() {
    if (!goal) return;
    goal = null;
    ghi(tw("lenh.goal_stopped"));
  }

  // Câu trả lời của một vòng đã về: ghi nhận marker + có chip hỏi ngược không. Việc QUYẾT ĐỊNH để
  // hetLuot làm, vì lúc này lượt chưa đóng (turn_done chưa tới).
  function ghiNhan(sid, marker, hoiLai) {
    if (goal && goal.sid === sid) goal.ket = { marker: marker, hoiLai: !!hoiLai };
  }
  function baoLoi(sid) {
    if (goal && goal.sid === sid) goal.ket = { loi: true };
  }

  async function tiepVong(sid) {
    var g = goal;
    if (!g || g.sid !== sid) return;
    g.vong += 1;
    var khoi = await layKhoi({ kind: "goal", dk: g.dk, vong: g.vong, toi_da: g.toiDa });
    if (goal !== g) return;   // bị huỷ trong lúc chờ khối chỉ dẫn
    if (!khoi) { goal = null; return ghi(tw("lenh.err_net")); }
    ghi(g.left ? tw("lenh.goal_round", { v: g.vong, n: g.toiDa, left: g.left })
               : tw("lenh.goal_round_noleft", { v: g.vong, n: g.toiDa }));
    chatApi().send(tw("lenh.goal_cont"), { prefix: khoi, goal: true });
  }

  // turn_done của phiên `sid`: đây là lúc duy nhất quyết định vòng tiếp.
  function hetLuot(sid) {
    var g = goal;
    var a = chatApi();
    if (!g || !a || g.sid !== sid) return;
    if (a.sid() !== sid) { goal = null; return; }   // người dùng đã sang hội thoại khác: thôi
    if (a.dangChay(sid)) return;                    // đã có lượt mới chạy (tin chen ngang)
    var qd = quyetDinhVongTiep(g, g.ket);
    g.ket = null;
    if (qd.act === "tiep") {
      g.left = qd.left;
      setTimeout(function () { tiepVong(sid); }, 300);
      return;
    }
    goal = null;
    var v = g.vong, n = g.toiDa;
    if (qd.ly === "dat") return ghi(tw("lenh.goal_done", { v: v }));
    if (qd.ly === "het_vong") return ghi(tw("lenh.goal_max", { n: n }));
    if (qd.ly === "khong_tien_trien") return ghi(tw("lenh.goal_stuck", { left: qd.left || "" }));
    if (qd.ly === "hoi_lai") return ghi(tw("lenh.goal_ask"));
    if (qd.ly === "loi") return ghi(tw("lenh.goal_err"));
    ghi(tw("lenh.goal_unknown", { v: v }));
  }

  async function chay(cmd, arg) {
    arg = String(arg || "").trim();
    try {
      switch (cmd) {
        case "help": return lenhHelp();
        case "status": return await lenhStatus();
        case "model": return await lenhModel(arg);
        case "brain": return await lenhBrain(arg);
        case "retry": return lenhRetry();
        case "usage": return await lenhUsage();
        case "tasks": return await lenhTasks();
        case "compact": return await lenhCompact();
        case "plan": return await lenhPlan(arg);
        case "memory": return await lenhMemory();
        case "export": return await lenhExport();
        case "goal": return await lenhGoal(arg);
        default: return;
      }
    } catch (e) {
      ghi(tw("lenh.err_net"));
    }
  }

  var api = {
    GOAL_TOI_DA: GOAL_TOI_DA,
    tachMucTieu: tachMucTieu,
    quyetDinhVongTiep: quyetDinhVongTiep,
    gonSo: gonSo,
    dinhDangTrangThai: dinhDangTrangThai,
    dinhDangMucDung: dinhDangMucDung,
    dinhDangViec: dinhDangViec,
    dinhDangBoNho: dinhDangBoNho,
    dinhDangXuat: dinhDangXuat,
    tenFileXuat: tenFileXuat,
    vaLinkBoNho: vaLinkBoNho,
    khopTen: khopTen,
    laLenhTat: laLenhTat,
    boKhoiDieuKhien: boKhoiDieuKhien,
    chay: chay,
    daGui: daGui,
    chenNgang: chenNgang,
    dungMucTieu: dungMucTieu,
    ghiNhan: ghiNhan,
    baoLoi: baoLoi,
    hetLuot: hetLuot,
    dangCoMucTieu: function () { return !!goal; },
  };

  if (typeof window !== "undefined") {
    window.JavisLenh = api;
    // Đổi sang hội thoại khác thì mục tiêu của hội thoại cũ hết nghĩa: dừng lặng lẽ.
    window.addEventListener("javis:sessions-changed", function () {
      var a = chatApi();
      if (goal && goal.sid && a && a.sid() !== goal.sid) goal = null;
    });
  }
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
