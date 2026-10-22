/* coding.js - trang Coding: chat với engine, gắn được vào một THƯ MỤC trên máy.

   Đổi hướng ở 0.63.1 sau khi chủ dự án dùng thử bản đầu và chỉ ra ba chỗ sai:

   1. **Vào là chat được ngay.** Bản đầu chặn bằng màn "Chưa có repo nào": chưa khai repo thì
      không nhắn được câu nào. Đó là dựng một bước cài đặt chắn trước một trang CHAT, tức là
      làm ngược chính cái spec của nó. Nay mở trang là có phiên, gõ là gửi; chưa gắn thư mục
      thì lượt chat chạy trong bộ não như mọi phiên thường.

   2. **THƯ MỤC chứ không phải REPO.** Bản đầu bắt phải có `.git`, không có thì từ chối kèm
      câu "chạy git init trước đi" - bắt người dùng làm việc vặt cho vừa mô hình dữ liệu của
      Javis. Nay nhận mọi thư mục; git là thứ ĐỌC RA, và ba chip phụ thuộc git (nhánh,
      worktree, điểm hồi) chỉ hiện khi thư mục đó thật sự là repo.

   3. **Cột trái là DANH SÁCH PHIÊN, không phải danh sách repo.** Câu hỏi người ta mở trang
      này để trả lời là "việc nào đang dở", không phải "mình đã khai những thư mục nào". Thư
      mục lùi về một menu ở chip.

   0.63.2 sửa tiếp hai chỗ nữa, cũng do chủ dự án chỉ ra khi dùng thử:

   4. **Cột trái là CHÍNH cột hội thoại của trang Trò chuyện**, mượn qua `JavisChatSide.mount`
      với bộ lọc kênh - nguyên hàng tab Hội thoại|Thư mục, thanh gom nhóm, ô tìm, ghim, nhóm
      theo ngày, đổi tên, xoá, "Xem thêm". Bản 0.63.1 tự vẽ một danh sách rút gọn: lại đúng
      cái lỗi "dựng bản thứ hai" mà chính file này chép lời cảnh báo ở trên.

   5. **Chip mức quyền đọc là Plan / Tự động / Toàn quyền**, và Plan không chỉ là chặn ghi mà
      còn BẢO engine lập kế hoạch rồi dừng (xem `coding_store.KHOI_PLAN`).

   0.63.4 sửa chỗ thứ sáu:

   6. **Thêm thư mục là DUYỆT rồi bấm chọn**, qua `JavisFolderPicker` (hộp dùng chung, chạy
      trên chính `GET /browse` mà hộp chọn brain vẫn dùng). Trước đó chỉ có một ô chữ trống:
      trên điện thoại là gõ tay cả đường dẫn tuyệt đối, sai một ký tự thì nhận câu "không phải
      thư mục" mà không biết sai ở đâu. Lại đúng cái lỗi "bắt người dùng khai dữ liệu cho vừa
      mô hình bên trong".

   Hai vùng: trái = phiên, giữa = khung chat MƯỢN của app. Không có cột Work Tree cố định -
   cây thư mục, trình sửa file và terminal đã có chỗ riêng, dựng bản thứ hai ở đây là chép lại
   từng đó thứ rồi để hai bản trôi lệch nhau.

   Dải chip ngữ cảnh nhét vào chính #modelBar đã mượn, đứng TRƯỚC chip Model của app.

   The pure function chipHtml is exported at the end of the file for node tests.
   KHÔNG dùng ký tự em dash. Chữ hiện ra lấy từ từ điển window.t. */
(function () {
  "use strict";

  // `W` thay cho `window` ở các chỗ chạm biến toàn cục: test node nạp thẳng file này để gọi
  // hàm thuần, mà trong node không có `window` và chạm biến CHƯA KHAI là ReferenceError.
  var W = (typeof window !== "undefined") ? window : {};
  var t = function (k, v) { return (W.t ? W.t(k, v) : k); };
  var ic = function (n, o) { return (W.ic ? W.ic(n, o) : ""); };
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }
  function brain() { try { return W.JavisSessions ? W.JavisSessions.brain() : "brain"; } catch (e) { return "brain"; } }
  async function api(url, opt) { var r = await fetch(url, opt); return r.json(); }
  function fd(o) {
    var f = new FormData();
    Object.keys(o).forEach(function (k) { if (o[k] !== undefined && o[k] !== null) f.append(k, o[k]); });
    return f;
  }

  // Khoá từ điển của ba mức quyền, viết ĐỦ CHỮ chứ không ghép `"coding.mode_" + m`: ghép chuỗi
  // thì bộ quét i18n không thấy khoá nào, nên xoá nhầm một dòng trong vi.json vẫn xanh và
  // người dùng là người đầu tiên thấy mã khoá trên màn hình.
  var MQ_KHOA = { suggest: "coding.mode_suggest", auto: "coding.mode_auto", full: "coding.mode_full" };
  var MQ_GHI = { suggest: "coding.mode_suggest_note", auto: "coding.mode_auto_note",
                 full: "coding.mode_full_note" };
  function nhanQuyen(m) { return t(MQ_KHOA[m] || MQ_KHOA.auto); }

  // Kênh của phiên Coding. Server là nguồn thật (coding_store.KENH) và trả về trong
  // /coding/folders; hằng này chỉ là phương án khi lời gọi đó hỏng.
  var KENH_MAC_DINH = "coding:phien";

  var S = {
    el: null, thuMuc: [], rb: {}, cwd: "", tm: null, tmDs: [],
    diemHoi: [], kenh: KENH_MAC_DINH, sidCoding: {}, phienTruoc: null,
  };
  var active = false, opening = 0;

  // ============================================================
  // Hàm thuần (test bằng node)
  // ============================================================

  /** HTML của hàng chip ngữ cảnh. Thuần để test được không cần DOM.
   *
   *  `rb` là ràng buộc phiên, `tm` là thư mục đang gắn (null khi chưa gắn).
   *
   *  Luật:
   *  - Chip THƯ MỤC và chip MỨC QUYỀN luôn có mặt. Mức quyền đã CÓ HIỆU LỰC ngay từ lượt
   *    chat đầu tiên kể cả khi chưa gắn thư mục (server đọc nó cho mọi phiên kênh coding,
   *    xem `_muc_quyen_luot_chat`), nên giấu chip đi là để người dùng chạy ở một mức quyền
   *    mà họ không nhìn thấy và không đổi được. 0.63.4 sửa đúng chỗ này.
   *  - Ba chip nhánh / worktree / điểm hồi chỉ hiện khi thư mục có git thật: bày một chip
   *    "nhánh" trên thư mục không có git là hứa một nút bấm vào chỉ để nhận lỗi. */
  function chipHtml(rb, tm) {
    rb = rb || {};
    var mq = rb.muc_quyen || "auto";
    var chip = function (loai, noiDung, them) {
      return '<button type="button" class="cd-chip' + (them || "") + '" data-cd="' + loai + '">' +
        noiDung + "</button>";
    };
    var chipQuyen = function () {
      return chip("quyen", ic("shield") + " " + esc(nhanQuyen(mq)), " cd-mq-" + esc(mq));
    };
    // 0.158.0: the folder itself is shown and changed by the composer chip (composer-folder.js),
    // so this row only carries the git chips and the permission level.
    if (!tm) return chipQuyen();
    var ra = "";
    if (tm.la_git) {
      var wt = !!(rb.worktree || "").trim();
      ra += chip("nhanh", ic("git-branch") + " " + esc(rb.nhanh || tm.nhanh || t("coding.branch_unknown")));
      ra += chip("worktree", (wt ? ic("check") : ic("folder-tree")) + " worktree", wt ? " on" : "");
      ra += chip("diemhoi", ic("history") + " " + esc(t("coding.chip_ckpt")));
    }
    // 0.256.0: Hoàn tác về mốc TỰ ĐỘNG. Không phụ thuộc git của thư mục (kho bóng của Javis lo),
    // nên có ở mọi thư mục đã gắn.
    ra += chip("hoantac", ic("undo-2") + " " + esc(t("coding.chip_undo")));
    return ra + chipQuyen();
  }

  // ============================================================
  // Khung trang
  // ============================================================
  /** Khung trang dùng ĐÚNG bộ lớp `.chatpage*` của trang Trò chuyện.
   *
   *  Không đặt bộ lớp riêng: toàn bộ luật xếp khung (bề rộng cột, min-height ở mọi tầng, thu
   *  gọn cột, ngăn kéo trên màn hẹp) đã nằm trong `_injectChatCss` của console.js, mà
   *  renderCoding gọi trước khi dựng trang này. Viết lại bộ lớp thứ hai là chép lại từng đó
   *  luật rồi để hai bản trôi lệch nhau ngay lần sửa đầu tiên. */
  function khung() {
    return '' +
      '<div class="chatpage" id="cdPage">' +
        '<aside class="chatpage-side" id="cdSide"></aside>' +
        '<div class="chatpage-main">' +
          '<div class="chatpage-bar">' +
            // Phone only, like the Chat page (0.243.0): opens the conversation drawer. On a
            // computer the column folds with the button in its own corner instead.
            '<button class="cp-ico-btn cp-side-toggle" type="button" id="cdLeftBtn" title="' +
              esc(t("coding.toggle_list")) + '" aria-label="' + esc(t("coding.toggle_list")) + '">' + ic("panel-left") + "</button>" +
            // 0.251.0: the open conversation's name, as on the Chat page (sessions-ui.js renderTitle).
            '<span class="cp-conv-host"></span>' +
            // Chip gom nhóm hội thoại của trang Trò chuyện đậu vào đây, y như thanh tiêu đề
            // của trang đó. Thiếu ô này thì JavisChatSide.chip() không có chỗ để vẽ.
            '<span class="proj-chip-host"></span>' +
            // 0.159.0: errors get their own slot, so a chip redraw cannot wipe them.
            '<small class="cd-err ws-err" id="cdErr" role="status"></small>' +
          "</div>" +
          // Chỗ đứng của dải chip trên MÀN HẸP. Trên máy tính dải chip nằm trong #modelBar
          // (một hàng đọc từ trái sang: thư mục, nhánh, worktree, điểm hồi, chế độ, model),
          // nhưng điện thoại ẩn hẳn #modelBar (`.model-bar{display:none}` trong console.css)
          // và JS dời chip model lên header. Dải chip ở lại trong một node display:none nên
          // chủ repo không thấy chỗ thêm thư mục lẫn chỗ đổi chế độ (báo 23/09, đã dựng lại
          // ở 390px: parent = modelBar, display = none). Nên màn hẹp cho nó hàng riêng.
          '<div class="cd-chips-hep" id="cdChipsHep"></div>' +
          '<div class="chatpage-slot" id="cdSlot"></div>' +
          // Chỗ đứng cho trình sửa khi mở một file từ tab Thư mục của cột trái, hoặc từ chip
          // "file đang mở" trên thanh đính kèm. `data-ne-host` là DẤU KHAI: thiếu nó thì
          // _borrowNoteEditor của console.js không tìm ra khung nào để mượn, và cú bấm vào
          // một file lặng lẽ không mở gì cả (đúng lỗi 0.63.4 chủ dự án báo).
          '<div class="chatpage-edit" id="cdEdit" data-ne-host></div>' +
        "</div>" +
      "</div>";
  }

  async function render(el, opts) {
    S.el = el; active = true;
    nhoPhienTruoc();
    el.innerHTML = khung();
    if (opts && opts.borrow) opts.borrow(el.querySelector("#cdSlot"));
    // Bật/tắt cột trái: gọi ĐÚNG hàm của console.js chứ không tự viết. Bản tự viết trước đây
    // chỉ `toggle("side-thu")` - lớp thu gọn của MÁY TÍNH - nên trên điện thoại bấm nút lịch
    // sử mà không có gì xảy ra (chủ repo báo 23/09; dựng lại ở 390px: sau cú bấm cột trái vẫn
    // nằm ở x = -315). Màn hẹp chỉ hiểu lớp `side-open`, và còn cần ba đường ĐÓNG nữa mà bản
    // tự viết cũng không có.
    var bat = W.JavisNeoCotTrai
      ? W.JavisNeoCotTrai(el.querySelector("#cdPage"), el.querySelector("#cdSide"),
                          el.querySelector("#cdSlot"))
      : function () { el.querySelector("#cdPage").classList.toggle("side-thu"); };
    el.querySelector("#cdLeftBtn").onclick = bat;
    await taiKenh();

    // CỘT TRÁI = chính cột hội thoại của trang Trò chuyện, lọc theo kênh Coding. Mượn nguyên
    // module nên có sẵn: tab Hội thoại|Thư mục, thanh gom nhóm, ô tìm, ghim, nhóm theo ngày,
    // đổi tên, xoá, "Xem thêm". `onNew` bắt buộc phải truyền, vì nút "Hội thoại mới" mặc định
    // mở một phiên chat THƯỜNG, mà phiên thường thì không chạy trong thư mục nào cả.
    if (W.JavisChatSide && W.JavisChatSide.mount) {
      W.JavisChatSide.mount(el.querySelector("#cdSide"), { kenh: S.kenh, onNew: moPhienMoi });
      // The collapse/expand pair in the column itself, the same as on the Chat page. Added
      // after mount, which rewrites the column and would drop them.
      if (W.JavisSideFoldButtons) W.JavisSideFoldButtons(el.querySelector("#cdPage"), el.querySelector("#cdSide"));
      try { W.JavisChatSide.chip(); } catch (e) {}
    }
    // Xoay ngang điện thoại, hoặc kéo cửa sổ qua ngưỡng 860px, là dải chip phải ĐỔI BÊN
    // (#modelBar <-> hàng riêng). Không nghe thì sau khi xoay nó nằm trong node đang bị ẩn và
    // biến mất y như lỗi gốc, chỉ khác là mất sau một thao tác thay vì mất ngay.
    try {
      _mqChip = W.matchMedia("(max-width: 860px)");
      _mqChipFn = function () { if (active) veChip(); };
      _mqChip.addEventListener("change", _mqChipFn);
    } catch (e) { _mqChip = null; }

    // The composer chip pins or unpins the working folder (0.158.0): reload the git chips.
    W.addEventListener("javis:pinned-folder-changed", onPinned);

    bocMoPhien();
    await moPhienDau();
  }
  var _mqChip = null, _mqChipFn = null;
  function onPinned(e) {
    var d = (e && e.detail) || {};
    if (active && d.sid && d.sid === sid()) taiRangBuoc(d.sid);
  }

  /** Bọc `JavisSessions.open` trong lúc ở trang này.
   *
   *  Bấm một hội thoại ở cột trái là module lịch sử gọi thẳng `JavisSessions.open`, không đi
   *  qua file này, nên dải chip vẫn nói về phiên CŨ: sai thư mục, sai mức quyền, và người
   *  dùng không có cách nào biết. Module đó không phát sự kiện nào, nên chỗ móc rẻ nhất là
   *  bọc chính hàm ấy lại, và trả về nguyên trạng khi rời trang. */
  var _openGoc = null;
  function bocMoPhien() {
    if (!W.JavisSessions || _openGoc) return;
    _openGoc = W.JavisSessions.open;
    W.JavisSessions.open = function (id, still) {
      var ra = _openGoc.apply(W.JavisSessions, arguments);
      if (id) { S.sidCoding[id] = 1; Promise.resolve(ra).then(function () { taiRangBuoc(id); }, function () {}); }
      return ra;
    };
  }
  function traMoPhien() {
    if (_openGoc && W.JavisSessions) { W.JavisSessions.open = _openGoc; }
    _openGoc = null;
  }

  function roi() {
    dongBangHoanTac();
    active = false;
    dongMenu(); goChip(); traMoPhien(); traKhungChat();
    // Gỡ hẳn: rời trang rồi mà còn nghe thì mỗi lần xoay máy lại gọi veChip() cho một trang
    // không còn tồn tại, và mỗi lần vào lại trang là chồng thêm một người nghe nữa.
    try { if (_mqChip && _mqChipFn) _mqChip.removeEventListener("change", _mqChipFn); } catch (e) {}
    _mqChip = null; _mqChipFn = null;
    W.removeEventListener("javis:pinned-folder-changed", onPinned);
  }

  // ============================================================
  // Dữ liệu
  // ============================================================
  // The Coding channel name comes from the server (coding_store.KENH). /coding/sessions returns
  // it with a one-row list, much lighter than reading the whole folder registry for one field.
  async function taiKenh() {
    var r = await api("/coding/sessions?brain=" + encodeURIComponent(brain()) + "&limit=1");
    if (!active) return;
    if (r && r.kenh) S.kenh = r.kenh;
  }

  /** Mở phiên để vào trang là gõ được ngay: lấy phiên gần nhất của kênh Coding, chưa có
   *  phiên nào thì tạo một cái mới. Danh sách thì module lịch sử tự tải lấy. */
  async function moPhienDau() {
    var r = await api("/coding/sessions?brain=" + encodeURIComponent(brain()) + "&limit=1");
    if (!active) return;
    var ds = (r && r.phien) || [];
    if (ds.length) await moPhien(ds[0].id);
    else await moPhienMoi();
  }

  // ============================================================
  // Phiên
  // ============================================================
  function laPhienCoding(id) { return !!(id && S.sidCoding[id]); }

  function nhoPhienTruoc() {
    try {
      var cur = W.JavisSessions && W.JavisSessions.current();
      if (cur && !laPhienCoding(cur)) S.phienTruoc = cur;
    } catch (e) {}
  }

  /** Rời trang: trả khung chat về cuộc của bộ não chính.
   *
   *  Không trả thì tin gõ tiếp ở trang Trò chuyện rơi vào phiên Coding, tức là chạy với cwd
   *  của một thư mục chứ không phải của brain. Đúng lỗi trang Cộng sự đã gặp và đã chữa. */
  function traKhungChat() {
    if (!W.JavisSessions) return;
    var cur = W.JavisSessions.current();
    if (!cur || (!laPhienCoding(cur) && cur === S.phienTruoc)) return;
    W.JavisSessions.new();
    if (S.phienTruoc && S.phienTruoc !== cur && !laPhienCoding(S.phienTruoc)) {
      try { W.JavisSessions.open(S.phienTruoc); } catch (e) {}
    }
  }

  async function moPhien(sid) {
    if (!sid) return false;
    var ticket = ++opening;
    var still = function () { return active && ticket === opening; };
    try {
      S.sidCoding[sid] = 1;
      if (W.JavisSessions) await W.JavisSessions.open(sid, still);
      if (!still()) return false;
      await taiRangBuoc(sid);
      return true;
    } catch (e) {
      if (still()) veLoi(t("coding.err_session"));
      return false;
    }
  }

  async function moPhienMoi() {
    var ticket = ++opening;
    try {
      var n = await api("/sessions/new", { method: "POST", body: fd({ brain: brain(), channel: S.kenh }) });
      if (!active || ticket !== opening) return false;
      // Câu lỗi của server nói về khuôn dữ liệu bên trong, không nói người dùng phải làm gì,
      // và không đi qua từ điển. Ghi console cho người sửa lỗi, màn hình dùng câu của mình.
      if (!n || !n.id) { try { console.warn("POST /sessions/new:", n && n.error); } catch (e2) {} throw new Error("session"); }
      S.sidCoding[n.id] = 1;
      if (W.JavisSessions) await W.JavisSessions.open(n.id);
      await taiRangBuoc(n.id);
      // Cột trái là module lịch sử: bảo NÓ vẽ lại, không tự dựng danh sách thứ hai.
      try { if (W.JavisChatSide && W.JavisChatSide.refresh) W.JavisChatSide.refresh(); } catch (e) {}
      return true;
    } catch (e) {
      veLoi(t("coding.err_session"));
      return false;
    }
  }

  // Errors go to the page bar slot #cdErr; an empty message clears it.
  function veLoi(msg) {
    var el = S.el && S.el.querySelector("#cdErr");
    if (el) el.textContent = msg || "";
  }

  function sid() { return W.JavisSessions ? W.JavisSessions.current() : ""; }

  async function taiRangBuoc(id) {
    var r = await api("/coding/session/" + encodeURIComponent(id));
    if (!active) return;
    S.rb = (r && r.rang_buoc) || {};
    S.tm = (r && r.thu_muc) || null;            // thư mục CHÍNH: engine đứng đó, git chạy đó
    S.tmDs = (r && r.thu_muc_ds) || (S.tm ? [S.tm] : []);
    S.cwd = (r && r.cwd) || "";
    S.diemHoi = (r && r.diem_hoi) || [];
    veLoi("");
    veChip();
  }

  // ============================================================
  // Hàng chip ngữ cảnh (nhét vào #modelBar đã mượn)
  // ============================================================
  /** Dải chip đứng ở ĐÂU, theo bề ngang màn hình.
   *
   *  Máy tính: trong #modelBar, để một hàng đọc từ trái sang là thư mục, nhánh, worktree,
   *  điểm hồi, chế độ, rồi model. Điện thoại: hàng riêng của trang này, vì #modelBar bị ẩn
   *  hẳn trên màn hẹp và dải chip nằm trong đó thì không ai thấy.
   *
   *  Tính lại MỖI LẦN vẽ chứ không nhớ một lần: người dùng xoay ngang điện thoại, hoặc kéo
   *  cửa sổ trình duyệt qua ngưỡng, là chỗ đúng đổi bên. */
  function hocChip() {
    var hep = W.matchMedia && W.matchMedia("(max-width: 860px)").matches;
    if (hep) return S.el && S.el.querySelector("#cdChipsHep");
    return document.getElementById("modelBar");
  }

  function veChip() {
    var bar = hocChip();
    if (!bar) return;
    var row = document.getElementById("cdChips");
    if (row && row.parentElement !== bar) row.remove(), (row = null);
    if (!row) {
      row = document.createElement("div");
      row.id = "cdChips";
      row.className = "cd-chips";
      bar.insertBefore(row, bar.firstChild);
    }
    var rb = S.rb || {};
    row.innerHTML = chipHtml({ nhanh: rb.nhanh, worktree: rb.worktree, muc_quyen: rb.muc_quyen }, S.tm);
    row.querySelectorAll("[data-cd]").forEach(function (n) {
      n.onclick = function () { bamChip(n.dataset.cd, n); };
    });
  }

  /** Gỡ dải chip khỏi #modelBar khi rời trang.
   *
   *  Bắt buộc: #modelBar là node MƯỢN của app, nó được trả về HUD nguyên vẹn. Để lại dải chip
   *  là trang Trò chuyện mọc thêm một hàng nói về một thư mục không còn liên quan. */
  function goChip() {
    var row = document.getElementById("cdChips");
    if (row && row.parentNode) row.parentNode.removeChild(row);
  }

  async function datRangBuoc(body) {
    var id = sid();
    if (!id) return;
    var r = await api("/coding/session/" + encodeURIComponent(id), { method: "POST", body: fd(body) });
    if (r && r.error) { veLoi(r.error); return; }
    await taiRangBuoc(id);
    try { if (W.JavisChatSide && W.JavisChatSide.refresh) W.JavisChatSide.refresh(); } catch (e) {}
  }

  function bamChip(loai, node) {
    if (loai === "nhanh") {
      var ds = (S.tm && S.tm.nhanh_ds) || [];
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
      // Kèm một dòng nói RÕ mức đó cho làm gì. Ba cái tên trần thì người dùng phải đoán
      // "Tự động" có push hộ không, mà đoán sai ở mức này là mất việc thật.
      return { nhan: nhanQuyen(m), phu: t(MQ_GHI[m]), chon: (S.rb.muc_quyen || "auto") === m,
               bam: function () { datRangBuoc({ muc_quyen: m }); } };
    }));
    if (loai === "diemhoi") return menuDiemHoi(node);
    if (loai === "hoantac") return menuHoanTac(node);
  }

  // ============================================================
  // Hoàn tác về mốc tự động (0.256.0, server/coding_checkpoint.py)
  // ============================================================
  function gioMoc(ts) {
    try { return new Date(Number(ts) * 1000).toLocaleString(); } catch (e) { return String(ts || ""); }
  }

  async function menuHoanTac(node) {
    var r = await api("/coding/session/" + encodeURIComponent(sid()) + "/undo");
    var ds = (r && r.moc) || [];
    if (!ds.length) return menu(node, [{ nhan: t("coding.undo_empty"), phu: t("coding.undo_empty_note") }]);
    menu(node, ds.map(function (m) {
      return { nhan: t("coding.undo_item", { gio: gioMoc(m.luc) }), phu: m.ly_do || "",
               bam: function () { moBangHoanTac(m); } };
    }));
  }

  var NHAN_TT = { A: "coding.undo_st_added", M: "coding.undo_st_modified", D: "coding.undo_st_deleted" };

  function dongBangHoanTac() {
    var b = document.getElementById("cdUndo");
    if (b && b.parentNode) b.parentNode.removeChild(b);
    document.removeEventListener("keydown", phimBangHoanTac);
  }
  function phimBangHoanTac(e) { if (e.key === "Escape") dongBangHoanTac(); }

  async function moBangHoanTac(m) {
    dongBangHoanTac();
    var url = "/coding/session/" + encodeURIComponent(sid()) + "/undo/" + encodeURIComponent(m.id);
    var b = document.createElement("div");
    b.className = "cd-undo"; b.id = "cdUndo";
    b.innerHTML = '<div class="cd-undo-box" role="dialog" aria-modal="true">' +
      '<div class="cd-undo-head"><b>' + esc(t("coding.undo_title", { gio: gioMoc(m.luc) })) + "</b>" +
      '<button type="button" class="cd-undo-x" aria-label="' + esc(t("coding.undo_close")) + '">' + ic("x") + "</button></div>" +
      '<div class="cd-undo-body">' + esc(t("coding.undo_loading")) + "</div></div>";
    document.body.appendChild(b);
    b.onclick = function (e) { if (e.target === b) dongBangHoanTac(); };
    b.querySelector(".cd-undo-x").onclick = dongBangHoanTac;
    document.addEventListener("keydown", phimBangHoanTac);
    var body = b.querySelector(".cd-undo-body");
    var r = await api(url);
    if (r && r.error) { body.textContent = r.error; return; }
    var files = (r && r.file) || [];
    if (!files.length) { body.textContent = t("coding.undo_nothing"); return; }
    body.innerHTML = '<p class="cd-undo-note">' + esc(t("coding.undo_note")) + "</p>" +
      '<ul class="cd-undo-list">' + files.map(function (f, i) {
        return "<li><div class=\"cd-undo-row\"><span class=\"cd-undo-st st-" + esc(f.trang_thai) + "\">" +
          esc(t(NHAN_TT[f.trang_thai] || NHAN_TT.M)) + "</span><code>" + esc(f.file) + "</code>" +
          '<button type="button" data-diff="' + i + '">' + esc(t("coding.undo_diff")) + "</button></div>" +
          '<pre class="cd-undo-diff" hidden></pre></li>';
      }).join("") + "</ul>" +
      '<div class="cd-undo-act"><button type="button" class="cd-undo-go">' + esc(t("coding.undo_restore")) +
      '</button></div><div class="cd-undo-kq"></div>';
    body.querySelectorAll("[data-diff]").forEach(function (nut) {
      nut.onclick = async function () {
        var f = files[Number(nut.dataset.diff)];
        var pre = nut.closest("li").querySelector("pre");
        if (!pre.hidden) { pre.hidden = true; return; }
        pre.hidden = false; pre.textContent = t("coding.undo_loading");
        var d = await api(url + "?file=" + encodeURIComponent(f.file));
        pre.textContent = (d && (d.diff || d.error)) || t("coding.undo_no_diff");
      };
    });
    body.querySelector(".cd-undo-go").onclick = async function () {
      if (!W.confirm(t("coding.undo_confirm"))) return;
      var kq = body.querySelector(".cd-undo-kq");
      kq.textContent = t("coding.undo_loading");
      var x = await api(url, { method: "POST", body: fd({}) });
      if (x && x.error) { kq.textContent = x.error; return; }
      var giu = (x && x.giu_nguyen) || [];
      kq.innerHTML = "<p>" + esc(t("coding.undo_done", { n: ((x && x.da_tra) || []).length })) + "</p>" +
        (giu.length ? "<p>" + esc(t("coding.undo_kept")) + "</p><ul>" +
          giu.map(function (g) { return "<li><code>" + esc(g) + "</code></li>"; }).join("") + "</ul>" : "");
      body.querySelector(".cd-undo-go").disabled = true;
    };
  }


  function menuDiemHoi(node) {
    var muc = [{
      nhan: t("coding.ckpt_make"),
      bam: async function () {
        var r = await api("/coding/session/" + encodeURIComponent(sid()) + "/checkpoint", { method: "POST" });
        if (r && r.error) veLoi(r.error); else await taiRangBuoc(sid());
      },
    }];
    S.diemHoi.slice().reverse().forEach(function (d) {
      muc.push({
        nhan: t("coding.ckpt_back", { tag: d.tag }),
        nguyHiem: true,
        bam: async function () {
          // `git reset --hard` không hỏi lại và không hoàn tác được, nên chỗ hỏi lại là đây.
          if (!W.confirm(t("coding.ckpt_confirm", { tag: d.tag }))) return;
          var r = await api("/coding/session/" + encodeURIComponent(sid()) + "/rollback",
                            { method: "POST", body: fd({ tag: d.tag }) });
          if (r && r.error) veLoi(r.error); else await taiRangBuoc(sid());
        },
      });
    });
    menu(node, muc);
  }

  // ============================================================
  // Menu bật lên từ một chip
  // ============================================================
  function menu(anchor, muc) {
    dongMenu();
    var m = document.createElement("div");
    m.className = "cd-menu"; m.id = "cdMenu";
    m.innerHTML = muc.map(function (x, i) {
      return '<button type="button" data-i="' + i + '" class="' +
        (x.chon ? "on " : "") + (x.nguyHiem ? "nguy" : "") + '">' +
        "<span>" + esc(x.nhan) + (x.phu ? '<small>' + esc(x.phu) + "</small>" : "") + "</span>" +
        "</button>";
    }).join("");
    document.body.appendChild(m);
    // Đặt menu vào chỗ trống THẬT quanh chip. Trước đây chỉ kẹp top >= 8: menu dài hơn
    // khoảng trống phía trên thì tràn xuống đè cả chip lẫn thanh điều hướng (báo 22/09).
    // Nay: ưu tiên mở lên trên, chật quá thì lật xuống dưới, và cắt chiều cao theo chỗ trống
    // để menu tự cuộn thay vì tràn ra ngoài màn hình.
    // Trần trên là ĐÁY HEADER chứ không phải mép màn hình. Trên điện thoại hàng chip nằm
    // ngay dưới header; kẹp ở 8px thì menu mở lên trên chui vào header, tên thư mục đè lên
    // chip model và không bấm được gì (chủ repo báo 27/09, kèm ảnh). Chỗ phía trên không đủ
    // thì menu tự lật xuống dưới chip.
    var r = anchor.getBoundingClientRect();
    var vv = W.visualViewport;
    var vh = vv ? vv.offsetTop + vv.height : (W.innerHeight || 800);   // bàn phím mở thì đáy thật là đáy vùng nhìn thấy
    var hdr = document.querySelector(".hud-top");
    var tran = 8;
    if (hdr) { var rh = hdr.getBoundingClientRect(); if (rh.height && rh.bottom < r.top) tran = Math.max(8, rh.bottom + 6); }
    var tren = Math.max(0, r.top - tran - 6);
    var duoi = Math.max(0, vh - r.bottom - 14);
    var len = m.offsetHeight <= tren || tren >= duoi;
    m.style.maxHeight = Math.max(160, len ? tren : duoi) + "px";
    var cao = m.offsetHeight;
    m.style.left = Math.max(8, Math.min(r.left, (W.innerWidth || 1200) - m.offsetWidth - 8)) + "px";
    m.style.top = (len ? Math.max(tran, r.top - cao - 6)
                       : Math.min(r.bottom + 6, Math.max(tran, vh - cao - 8))) + "px";
    m.querySelectorAll("[data-i]").forEach(function (b) {
      b.onclick = function () {
        var x = muc[Number(b.dataset.i)];
        dongMenu();
        if (x && x.bam) x.bam();
      };
    });
    // Bấm ra ngoài thì đóng. Phải NHỚ bộ nghe để gỡ: menu tích chọn vẽ lại sau mỗi lần tích,
    // mỗi lần lại gắn thêm một bộ nghe, và chúng không tự rụng vì cú bấm trong menu đã bị
    // chặn không cho lan ra document. Để đọng lại thì một menu mở sau đó bị đóng oan.
    goBoDong();
    _boDong = function () { dongMenu(); };
    setTimeout(function () { if (_boDong) document.addEventListener("click", _boDong, { once: true }); }, 0);
  }
  var _boDong = null;
  function goBoDong() {
    if (!_boDong) return;
    document.removeEventListener("click", _boDong, { once: true });
    _boDong = null;
  }
  function dongMenu() {
    goBoDong();
    var m = document.getElementById("cdMenu");
    if (m && m.parentNode) m.parentNode.removeChild(m);
  }

  // ============================================================
  // Hoàn tác ở MỌI khung chat (0.259.0)
  // ============================================================
  /** Từ 0.259.0 mọi khung chat của chủ đều có terminal và mốc khôi phục, không riêng trang Code.
   *  Trang Code có chip Hoàn tác; các khung chat còn lại nhận một mục trong menu "+" của ô soạn
   *  tin, mở đúng bảng Hoàn tác ở trên cho phiên đang mở. */
  function dangKyMenuHoanTac() {
    if (!W.JavisComposerMenu || !W.JavisComposerMenu.register) return;
    W.JavisComposerMenu.register({
      id: "undo", order: 25, icon: ic("undo-2"), label: "cp.undo", emptyKey: "coding.undo_empty",
      submenu: function () {
        var id = sid();
        if (!id) return Promise.resolve([]);
        return api("/coding/session/" + encodeURIComponent(id) + "/undo").then(function (r) {
          return ((r && r.moc) || []).map(function (m) {
            return { label: t("coding.undo_item", { gio: gioMoc(m.luc) }), hint: m.ly_do || "",
                     run: function () { moBangHoanTac(m); } };
          });
        }, function () { return []; });
      },
    });
  }
  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", dangKyMenuHoanTac);
    else dangKyMenuHoanTac();
  }

  W.JavisCoding = {
    render: render, roi: roi,
    // Exposed for node tests
    chipHtml: chipHtml,
  };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { chipHtml: chipHtml };
  }
})();
