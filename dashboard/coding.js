/* coding.js - trang Coding: chat với engine NGAY TRONG một repo.

   Hai vùng, không phải ba: trái = repo + phiên của repo đó, giữa = khung chat MƯỢN của app.
   Không có cột Work Tree cố định - cây thư mục, trình sửa file và terminal đã có chỗ riêng,
   dựng bản thứ hai ở đây là chép lại từng đó thứ rồi để hai bản trôi lệch nhau.

   Thứ file này THÊM vào khung chat sẵn có đúng một dải: HÀNG CHIP NGỮ CẢNH, nhét vào chính
   #modelBar đã mượn, đứng TRƯỚC chip Model. Nên một hàng đọc từ trái sang là: repo, nhánh,
   worktree, mức quyền, rồi model. Chip Model không viết lại - nó là #mbOpen của app.

   Phiên coding là phiên chat bình thường, chỉ khác cái kênh `coding:<id repo>`. Nhờ vậy nó
   thừa hưởng sẵn: chạy nền khi đóng tab, thẻ hết lượt gói thuê bao, đính kèm, giọng nói,
   lịch sử, tìm kiếm. Server nhìn kênh mà đổi `cwd` của engine (main.py `_cwd_luot_chat`).

   Các hàm THUẦN (chipHtml, nhanHienThi, trangThaiPhien) phơi ra cuối file để test bằng node.
   KHÔNG dùng ký tự em dash. Chữ hiện ra lấy từ từ điển window.t. */
(function () {
  "use strict";

  // `W` thay cho `window` ở BỐN chỗ: hai hàm dịch/icon dưới đây và khối phơi ra cuối file.
  // Lý do: test node nạp thẳng file này để gọi các hàm thuần (chipHtml, nhanHienThi,
  // trangThaiPhien) thay vì bắt regex trên mã nguồn - kiểm hành vi thật thì đổi cách viết mà
  // giữ nguyên hành vi vẫn xanh, còn regex thì đỏ oan. Trong node không có `window`, mà chạm
  // vào một biến toàn cục CHƯA KHAI là ReferenceError chứ không phải undefined.
  var W = (typeof window !== "undefined") ? window : {};
  var t = function (k, v) { return (W.t ? W.t(k, v) : k); };
  var ic = function (n, o) { return (W.ic ? W.ic(n, o) : ""); };
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }
  function brain() { try { return window.JavisSessions ? window.JavisSessions.brain() : "brain"; } catch (e) { return "brain"; } }
  async function api(url, opt) { var r = await fetch(url, opt); return r.json(); }
  function fd(o) {
    var f = new FormData();
    Object.keys(o).forEach(function (k) { if (o[k] !== undefined && o[k] !== null) f.append(k, o[k]); });
    return f;
  }

  // Khoá từ điển của ba mức quyền, viết ĐỦ CHỮ chứ không ghép `"coding.mode_" + m`.
  // Ghép chuỗi thì bộ quét i18n (tests/js/test_i18n.mjs) không thấy khoá nào cả, nên xoá nhầm
  // một dòng trong vi.json vẫn xanh và người dùng là người đầu tiên thấy mã khoá trên màn hình.
  var MQ_KHOA = { suggest: "coding.mode_suggest", auto: "coding.mode_auto", full: "coding.mode_full" };
  function nhanQuyen(m) { return t(MQ_KHOA[m] || MQ_KHOA.auto); }

  var S = {
    el: null, repos: [], repoChon: "", phien: [], rb: {}, cwd: "",
    diemHoi: [], sessionCoding: {}, phienTruoc: null,
  };
  var active = false, opening = 0;

  // ============================================================
  // Hàm thuần (test bằng node)
  // ============================================================

  /** Nhãn ngắn của một repo trên chip. Đường dẫn dài trên điện thoại đẩy mọi chip khác ra
   *  khỏi màn hình, nên chip mang TÊN, còn đường dẫn đầy đủ nằm ở title. */
  function nhanHienThi(repo) {
    if (!repo) return "";
    return String(repo.ten || repo.duong_dan || "").split(/[\\/]/).pop();
  }

  /** Trạng thái một phiên coding cho cột trái.
   *
   *  Bốn mức, suy từ thứ ĐÃ CÓ chứ không đoán: `dang` khi app báo lượt đang chạy, `het_luot`
   *  khi kho hạn mức còn một mục chờ của phiên này, `loi` khi lượt cuối hỏng, còn lại `xong`.
   *  Mức thứ năm "cần trả lời" CỐ Ý chưa có: nhận ra nó phải đoán ý cuối lượt, mà đoán sai thì
   *  hoặc báo động giả hoặc bỏ sót - cả hai đều làm người dùng thôi tin cái badge. */
  function trangThaiPhien(p, dangChay, choHanMuc) {
    var id = p && p.id;
    if (!id) return "xong";
    if (choHanMuc && choHanMuc[id]) return "het_luot";
    if (dangChay && dangChay === id) return "dang";
    if (p.loi) return "loi";
    return "xong";
  }

  /** HTML của hàng chip ngữ cảnh. Thuần để test được không cần DOM.
   *
   *  `rb` là ràng buộc phiên từ /coding/session/<sid>, `repo` là bản ghi repo. Chưa có repo
   *  thì chỉ vẽ chip mời chọn: vẽ chip nhánh rỗng cạnh chip mức quyền làm người ta tưởng đã
   *  gắn repo rồi mà nhánh không đọc được. */
  function chipHtml(rb, repo) {
    rb = rb || {};
    if (!repo) {
      return '<button type="button" class="cd-chip cd-chip-repo" data-cd="repo">' +
        ic("folder-tree") + " " + esc(t("coding.chip_pick_repo")) + "</button>";
    }
    var wt = !!(rb.worktree || "").trim();
    var mq = rb.muc_quyen || "auto";
    return '' +
      '<button type="button" class="cd-chip cd-chip-repo" data-cd="repo" title="' + esc(repo.duong_dan || "") + '">' +
        ic("folder-tree") + " " + esc(nhanHienThi(repo)) + '</button>' +
      '<button type="button" class="cd-chip" data-cd="nhanh" title="' + esc(t("coding.chip_branch")) + '">' +
        ic("git-branch") + " " + esc(rb.nhanh || repo.nhanh || t("coding.branch_unknown")) + '</button>' +
      '<button type="button" class="cd-chip' + (wt ? " on" : "") + '" data-cd="worktree" title="' +
        esc(t("coding.chip_worktree_tip")) + '">' + (wt ? ic("check") : ic("folder-open")) +
        " worktree</button>" +
      '<button type="button" class="cd-chip cd-mq-' + esc(mq) + '" data-cd="quyen" title="' +
        esc(t("coding.chip_mode_tip")) + '">' + ic("shield") + " " + esc(nhanQuyen(mq)) + '</button>' +
      '<button type="button" class="cd-chip" data-cd="diemhoi" title="' + esc(t("coding.chip_ckpt_tip")) + '">' +
        ic("history") + " " + esc(t("coding.chip_ckpt")) + '</button>';
  }

  // ============================================================
  // Khung trang
  // ============================================================
  function khung() {
    return '' +
      '<div class="cd-page" id="cdPage">' +
        '<aside class="cd-left" id="cdLeft">' +
          '<div class="cd-left-head">' + ic("file-code") + " <b>" + esc(t("page.coding.label")) + "</b></div>" +
          '<div class="cd-repos" id="cdRepos"></div>' +
          '<div class="cd-left-foot">' +
            '<button type="button" class="ws-btn" id="cdAddRepo">' + ic("plus") + " " + esc(t("coding.add_repo")) + "</button>" +
          "</div>" +
        "</aside>" +
        '<div class="cd-main">' +
          '<div class="cd-bar">' +
            '<button type="button" class="ws-ico" id="cdLeftBtn" title="' + esc(t("coding.toggle_list")) + '">' + ic("panel-left") + "</button>" +
            '<div class="cd-id" id="cdIdentity"></div>' +
            '<button type="button" class="ws-btn" id="cdNewChat">' + esc(t("sess.new_chat")) + "</button>" +
          "</div>" +
          '<div class="cd-onboard" id="cdOnboard" hidden></div>' +
          '<div class="cd-slot" id="cdSlot"></div>' +
        "</div>" +
      "</div>";
  }

  async function render(el, opts) {
    S.el = el; active = true;
    nhoPhienTruoc();
    el.innerHTML = khung();
    if (opts && opts.borrow) opts.borrow(el.querySelector("#cdSlot"));
    el.querySelector("#cdAddRepo").onclick = themRepo;
    el.querySelector("#cdNewChat").onclick = function () { moPhien(S.repoChon, true); };
    el.querySelector("#cdLeftBtn").onclick = function () {
      // Cùng một nút, hai nghĩa ngược nhau theo bề rộng: trên desktop cột trái hiện sẵn nên
      // nút để ẨN nó (`left-off`); trên điện thoại cột trái là ngăn kéo đóng sẵn nên nút để
      // MỞ ra (`left-on`). Dùng chung một lớp thì một trong hai màn hình bấm nút không thấy
      // gì xảy ra, và đó là kiểu hỏng người dùng tưởng máy đơ.
      var hep = window.matchMedia && window.matchMedia("(max-width: 900px)").matches;
      el.querySelector("#cdPage").classList.toggle(hep ? "left-on" : "left-off");
    };
    await taiRepos();
  }

  function roi() {
    active = false;
    goChip();
    traKhungChat();
  }

  // ============================================================
  // Sổ repo
  // ============================================================
  async function taiRepos() {
    var r = await api("/coding/repos?brain=" + encodeURIComponent(brain()));
    if (!active) return;
    S.repos = (r && r.repos) || [];
    if (!S.repoChon || !S.repos.some(function (x) { return x.id === S.repoChon; })) {
      S.repoChon = S.repos.length ? S.repos[0].id : "";
    }
    veTrai();
    if (!S.repos.length) { veOnboard(); return; }
    an(S.el.querySelector("#cdOnboard"), true);
    await moPhien(S.repoChon, false);
  }

  function an(node, an_) { if (node) node.hidden = !!an_; }

  /** Màn khởi đầu: chưa khai repo nào thì không có gì để chat, nên chỗ khung chat là lời mời
   *  thêm repo. Khung chat ẩn đi bằng lớp .onboard-on, đúng cách trang Cộng sự làm. */
  function veOnboard() {
    var box = S.el.querySelector("#cdOnboard");
    if (!box) return;
    box.innerHTML = '<div class="cd-ob"><div class="cd-ob-ic">' + ic("file-code", { cls: "ic-xl" }) + "</div>" +
      "<h3>" + esc(t("coding.ob_title")) + "</h3>" +
      "<p>" + esc(t("coding.ob_note")) + "</p>" +
      '<button type="button" class="ws-btn primary" id="cdObAdd">' + ic("plus") + " " + esc(t("coding.add_repo")) + "</button></div>";
    box.hidden = false;
    S.el.querySelector("#cdPage").classList.add("onboard-on");
    box.querySelector("#cdObAdd").onclick = themRepo;
  }

  function veTrai() {
    var box = S.el.querySelector("#cdRepos");
    if (!box) return;
    if (!S.repos.length) { box.innerHTML = ""; return; }
    box.innerHTML = S.repos.map(function (r) {
      var chon = r.id === S.repoChon;
      return '<div class="cd-repo' + (chon ? " on" : "") + '" data-repo="' + esc(r.id) + '">' +
        '<div class="cd-repo-top">' + ic("folder-tree") + " <b>" + esc(r.ten) + "</b>" +
          (r.co_that ? "" : '<span class="cd-warn" title="' + esc(t("coding.repo_gone")) + '">!</span>') +
          '<button type="button" class="cd-x" data-xoa="' + esc(r.id) + '" title="' + esc(t("coding.remove_repo")) + '">' + ic("x") + "</button>" +
        "</div>" +
        '<div class="cd-repo-sub">' + esc(r.duong_dan) + "</div>" +
        (chon ? vePhienDs() : "") + "</div>";
    }).join("");
    box.querySelectorAll("[data-repo]").forEach(function (n) {
      n.onclick = function (e) {
        if (e.target.closest("[data-xoa]") || e.target.closest("[data-phien]")) return;
        if (S.repoChon === n.dataset.repo) return;
        S.repoChon = n.dataset.repo; veTrai(); moPhien(S.repoChon, false);
      };
    });
    box.querySelectorAll("[data-xoa]").forEach(function (n) {
      n.onclick = function (e) { e.stopPropagation(); xoaRepo(n.dataset.xoa); };
    });
    box.querySelectorAll("[data-phien]").forEach(function (n) {
      n.onclick = function (e) { e.stopPropagation(); moPhien(S.repoChon, false, n.dataset.phien); };
    });
  }

  function vePhienDs() {
    if (!S.phien.length) return '<div class="cd-phien-trong">' + esc(t("coding.no_session")) + "</div>";
    var cur = window.JavisSessions ? window.JavisSessions.current() : "";
    return '<div class="cd-phien-ds">' + S.phien.map(function (p) {
      var tt = trangThaiPhien(p, null, null);
      return '<div class="cd-phien' + (p.id === cur ? " on" : "") + '" data-phien="' + esc(p.id) + '">' +
        '<span class="cd-tt cd-tt-' + tt + '"></span>' +
        '<span class="cd-phien-ten">' + esc(p.title || p.preview || t("coding.session_untitled")) + "</span></div>";
    }).join("") + "</div>";
  }

  async function themRepo() {
    var p = window.prompt(t("coding.ask_path"));
    if (!p) return;
    var r = await api("/coding/repos", { method: "POST", body: fd({ duong_dan: p, brain: brain() }) });
    if (!r || r.error) { window.alert(r && r.error ? r.error : t("coding.add_err")); return; }
    S.repoChon = r.repo.id;
    S.el.querySelector("#cdPage").classList.remove("onboard-on");
    an(S.el.querySelector("#cdOnboard"), true);
    await taiRepos();
  }

  async function xoaRepo(rid) {
    // Nói rõ cái gì mất và cái gì còn. Bỏ một repo khỏi Javis mà người dùng sợ mất mã nguồn
    // thì họ không bấm, và cái nút đó coi như không tồn tại.
    if (!window.confirm(t("coding.remove_confirm"))) return;
    await api("/coding/repos/" + encodeURIComponent(rid) + "/delete", { method: "POST" });
    if (S.repoChon === rid) S.repoChon = "";
    await taiRepos();
  }

  // ============================================================
  // Phiên
  // ============================================================
  function kenh(rid) { return "coding:" + rid; }
  function laPhienCoding(id) { return !!(id && S.sessionCoding[id]); }

  function nhoPhienTruoc() {
    try {
      var cur = window.JavisSessions && window.JavisSessions.current();
      if (cur && !laPhienCoding(cur)) S.phienTruoc = cur;
    } catch (e) {}
  }

  /** Rời trang: trả khung chat về cuộc của bộ não chính.
   *
   *  Không trả thì tin gõ tiếp ở trang Trò chuyện rơi vào phiên coding - tức là chạy với cwd
   *  của một repo chứ không phải của brain. Đúng lỗi trang Cộng sự đã gặp và đã chữa. */
  function traKhungChat() {
    if (!window.JavisSessions) return;
    var cur = window.JavisSessions.current();
    if (!cur || (!laPhienCoding(cur) && cur === S.phienTruoc)) return;
    window.JavisSessions.new();
    if (S.phienTruoc && S.phienTruoc !== cur && !laPhienCoding(S.phienTruoc)) {
      try { window.JavisSessions.open(S.phienTruoc); } catch (e) {}
    }
  }

  async function moPhien(rid, moiHan, sidChiDinh) {
    if (!rid) return false;
    var ticket = ++opening;
    var still = function () { return active && ticket === opening && S.repoChon === rid; };
    try {
      var b = encodeURIComponent(brain()), ch = kenh(rid), id = sidChiDinh || null;
      var ds = await api("/sessions?brain=" + b + "&channel=" + encodeURIComponent(ch) + "&limit=30");
      if (!still()) return false;
      S.phien = (ds && ds.sessions) || [];
      if (!id && !moiHan && S.phien[0]) id = S.phien[0].id;
      if (!id) {
        var n = await api("/sessions/new", { method: "POST", body: fd({ brain: brain(), channel: ch }) });
        if (!still()) return false;
        // Câu lỗi của server nói về khuôn dữ liệu bên trong, không nói người dùng phải làm gì,
        // và không đi qua từ điển. Ghi console cho người sửa lỗi, màn hình dùng câu của mình.
        if (!n.id) { try { console.warn("POST /sessions/new:", n.error); } catch (e2) {} throw new Error("session"); }
        id = n.id;
      }
      S.sessionCoding[id] = rid;
      if (window.JavisSessions) await window.JavisSessions.open(id, still);
      if (!still()) return false;
      await taiRangBuoc(id);
      veTrai();
      return true;
    } catch (e) {
      if (still()) veLoi(t("coding.err_session"));
      return false;
    }
  }

  function veLoi(msg) {
    var el = S.el && S.el.querySelector("#cdIdentity");
    if (el) el.innerHTML = '<small class="ws-err">' + esc(msg) + "</small>";
  }

  async function taiRangBuoc(sid) {
    var r = await api("/coding/session/" + encodeURIComponent(sid));
    if (!active) return;
    S.rb = (r && r.rang_buoc) || {};
    S.cwd = (r && r.cwd) || "";
    S.diemHoi = (r && r.diem_hoi) || [];
    veChip();
    var idn = S.el && S.el.querySelector("#cdIdentity");
    if (idn) idn.innerHTML = '<span class="cd-cwd" title="' + esc(S.cwd) + '">' + esc(S.cwd || t("coding.no_repo")) + "</span>";
  }

  // ============================================================
  // Hàng chip ngữ cảnh (nhét vào #modelBar đã mượn)
  // ============================================================
  function veChip() {
    var bar = document.getElementById("modelBar");
    if (!bar) return;
    var row = bar.querySelector("#cdChips");
    if (!row) {
      row = document.createElement("div");
      row.id = "cdChips";
      row.className = "cd-chips";
      bar.insertBefore(row, bar.firstChild);
    }
    var repo = S.repos.filter(function (x) { return x.id === (S.rb.repo || S.repoChon); })[0] || null;
    row.innerHTML = chipHtml(S.rb, repo);
    row.querySelectorAll("[data-cd]").forEach(function (n) {
      n.onclick = function () { bamChip(n.dataset.cd, n); };
    });
  }

  /** Gỡ dải chip khỏi #modelBar khi rời trang.
   *
   *  Bắt buộc: #modelBar là node MƯỢN của app, nó được trả về HUD nguyên vẹn. Để lại dải chip
   *  là trang Trò chuyện mọc thêm một hàng nói về một repo không còn liên quan gì. */
  function goChip() {
    var row = document.getElementById("cdChips");
    if (row && row.parentNode) row.parentNode.removeChild(row);
  }

  function sid() { return window.JavisSessions ? window.JavisSessions.current() : ""; }

  async function datRangBuoc(body) {
    var id = sid();
    if (!id) return;
    var r = await api("/coding/session/" + encodeURIComponent(id), { method: "POST", body: fd(body) });
    if (r && r.error) { window.alert(r.error); return; }
    await taiRangBuoc(id);
  }

  function bamChip(loai, node) {
    if (loai === "repo") return menu(node, S.repos.map(function (r) {
      return { nhan: r.ten, bam: function () { S.repoChon = r.id; veTrai(); moPhien(r.id, false); } };
    }));
    if (loai === "nhanh") {
      var repo = S.repos.filter(function (x) { return x.id === (S.rb.repo || S.repoChon); })[0];
      var ds = (repo && repo.nhanh_ds) || [];
      if (!ds.length) return;
      return menu(node, ds.map(function (b) {
        return { nhan: b, bam: function () { datRangBuoc({ nhanh: b }); } };
      }));
    }
    if (loai === "worktree") {
      var dangCo = !!(S.rb.worktree || "").trim();
      return datRangBuoc({ worktree: dangCo ? "0" : "1" });
    }
    if (loai === "quyen") return menu(node, ["suggest", "auto", "full"].map(function (m) {
      return { nhan: nhanQuyen(m), bam: function () { datRangBuoc({ muc_quyen: m }); } };
    }));
    if (loai === "diemhoi") return menuDiemHoi(node);
  }

  function menu(anchor, muc) {
    dongMenu();
    var m = document.createElement("div");
    m.className = "cd-menu"; m.id = "cdMenu";
    m.innerHTML = muc.map(function (x, i) {
      return '<button type="button" data-i="' + i + '">' + esc(x.nhan) + "</button>";
    }).join("");
    document.body.appendChild(m);
    var r = anchor.getBoundingClientRect();
    m.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 240)) + "px";
    m.style.top = (r.top - m.offsetHeight - 6) + "px";
    m.querySelectorAll("[data-i]").forEach(function (b) {
      b.onclick = function () { var x = muc[Number(b.dataset.i)]; dongMenu(); if (x && x.bam) x.bam(); };
    });
    setTimeout(function () { document.addEventListener("click", dongMenuMot, { once: true }); }, 0);
  }
  function dongMenuMot() { dongMenu(); }
  function dongMenu() { var m = document.getElementById("cdMenu"); if (m && m.parentNode) m.parentNode.removeChild(m); }

  function menuDiemHoi(node) {
    var muc = [{
      nhan: t("coding.ckpt_make"),
      bam: async function () {
        var r = await api("/coding/session/" + encodeURIComponent(sid()) + "/checkpoint", { method: "POST" });
        if (r && r.error) window.alert(r.error); else await taiRangBuoc(sid());
      },
    }];
    S.diemHoi.slice().reverse().forEach(function (d) {
      muc.push({
        nhan: t("coding.ckpt_back", { tag: d.tag }),
        bam: async function () {
          // `git reset --hard` không hỏi lại và không hoàn tác được, nên chỗ hỏi lại là đây.
          if (!window.confirm(t("coding.ckpt_confirm", { tag: d.tag }))) return;
          var r = await api("/coding/session/" + encodeURIComponent(sid()) + "/rollback",
                            { method: "POST", body: fd({ tag: d.tag }) });
          if (r && r.error) window.alert(r.error); else await taiRangBuoc(sid());
        },
      });
    });
    menu(node, muc);
  }

  W.JavisCoding = {
    render: render, roi: roi,
    // Phơi cho test node
    chipHtml: chipHtml, nhanHienThi: nhanHienThi, trangThaiPhien: trangThaiPhien,
  };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { chipHtml: chipHtml, nhanHienThi: nhanHienThi, trangThaiPhien: trangThaiPhien };
  }
})();
