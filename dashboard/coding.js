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

   Các hàm THUẦN (chipHtml, nhanHienThi) phơi ra cuối file để test bằng node.
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

  /** Nhãn ngắn của một thư mục trên chip. Đường dẫn dài trên điện thoại đẩy mọi chip khác ra
   *  khỏi màn hình, nên chip mang TÊN, còn đường dẫn đầy đủ nằm ở title. */
  function nhanHienThi(tm) {
    if (!tm) return "";
    return String(tm.ten || tm.duong_dan || "").split(/[\\/]/).pop();
  }

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
    if (!tm) {
      return chip("thumuc", ic("folder-plus") + " " + esc(t("coding.chip_pick_folder")),
                  " cd-chip-mo") + chipQuyen();
    }
    // Gắn nhiều thư mục thì chip mang tên thư mục CHÍNH kèm "+N": tên chính là thứ người
    // dùng cần thấy (engine đứng đó, git chạy đó), còn con số chỉ để biết còn thư mục khác.
    var them = Math.max(0, (Number(rb.so_thu_muc) || 1) - 1);
    var ra = '<button type="button" class="cd-chip cd-chip-tm" data-cd="thumuc" title="' +
      esc(tm.duong_dan || "") + '">' + ic("folder-open") + " " + esc(nhanHienThi(tm)) +
      (them ? ' <span class="cd-chip-them">+' + them + "</span>" : "") + "</button>";
    if (tm.la_git) {
      var wt = !!(rb.worktree || "").trim();
      ra += chip("nhanh", ic("git-branch") + " " + esc(rb.nhanh || tm.nhanh || t("coding.branch_unknown")));
      ra += chip("worktree", (wt ? ic("check") : ic("folder-tree")) + " worktree", wt ? " on" : "");
      ra += chip("diemhoi", ic("history") + " " + esc(t("coding.chip_ckpt")));
    }
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
            '<button class="cp-ico-btn cp-side-toggle" type="button" id="cdLeftBtn" title="' +
              esc(t("coding.toggle_list")) + '">' + ic("history") + "</button>" +
            '<div class="cd-id" id="cdIdentity"></div>' +
            // Chip gom nhóm hội thoại của trang Trò chuyện đậu vào đây, y như thanh tiêu đề
            // của trang đó. Thiếu ô này thì JavisChatSide.chip() không có chỗ để vẽ.
            '<span class="proj-chip-host"></span>' +
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
    await taiThuMuc();

    // CỘT TRÁI = chính cột hội thoại của trang Trò chuyện, lọc theo kênh Coding. Mượn nguyên
    // module nên có sẵn: tab Hội thoại|Thư mục, thanh gom nhóm, ô tìm, ghim, nhóm theo ngày,
    // đổi tên, xoá, "Xem thêm". `onNew` bắt buộc phải truyền, vì nút "Hội thoại mới" mặc định
    // mở một phiên chat THƯỜNG, mà phiên thường thì không chạy trong thư mục nào cả.
    if (W.JavisChatSide && W.JavisChatSide.mount) {
      W.JavisChatSide.mount(el.querySelector("#cdSide"), { kenh: S.kenh, onNew: moPhienMoi });
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

    bocMoPhien();
    await moPhienDau();
  }
  var _mqChip = null, _mqChipFn = null;

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
    active = false;
    dongMenu(); goChip(); traMoPhien(); traKhungChat();
    // Gỡ hẳn: rời trang rồi mà còn nghe thì mỗi lần xoay máy lại gọi veChip() cho một trang
    // không còn tồn tại, và mỗi lần vào lại trang là chồng thêm một người nghe nữa.
    try { if (_mqChip && _mqChipFn) _mqChip.removeEventListener("change", _mqChipFn); } catch (e) {}
    _mqChip = null; _mqChipFn = null;
  }

  // ============================================================
  // Dữ liệu
  // ============================================================
  async function taiThuMuc() {
    var r = await api("/coding/folders?brain=" + encodeURIComponent(brain()));
    if (!active) return;
    S.thuMuc = (r && r.thu_muc) || [];
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

  function veLoi(msg) {
    var el = S.el && S.el.querySelector("#cdIdentity");
    if (el) el.innerHTML = '<small class="ws-err">' + esc(msg) + "</small>";
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
    veChip();
    var idn = S.el && S.el.querySelector("#cdIdentity");
    if (idn) {
      idn.innerHTML = S.cwd
        ? '<span class="cd-cwd" title="' + esc(S.cwd) + '">' + esc(S.cwd) + "</span>"
        : '<span class="cd-cwd dim">' + esc(t("coding.in_brain")) + "</span>";
    }
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
    row.innerHTML = chipHtml({ nhanh: rb.nhanh, worktree: rb.worktree, muc_quyen: rb.muc_quyen,
                               so_thu_muc: (S.tmDs || []).length }, S.tm);
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
    if (loai === "thumuc") return menuThuMuc(node);
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
  }

  /** Menu thư mục: chọn cái đã khai, thêm cái mới, gỡ khỏi phiên, bỏ khỏi Javis.
   *
   *  Quản lý thư mục nằm TRONG menu này chứ không thành một cột riêng: cả trang chỉ có một
   *  chỗ nói về thư mục, và nó nằm đúng chỗ người dùng đang nhìn khi cần đổi. */
  /** Menu thư mục: TÍCH CHỌN, gắn được nhiều thư mục vào một việc (0.63.8).
   *
   *  Một việc thật hay đụng nhiều thư mục cùng lúc (mã nguồn với tài liệu, app với thư viện
   *  dùng chung), nên bắt chọn đúng một cái là bắt người dùng đổi qua đổi lại giữa chừng.
   *
   *  Thư mục ĐẦU danh sách là CHÍNH: engine đứng ở đó và mọi thao tác git chạy ở đó, vì một
   *  tiến trình chỉ đứng được ở một chỗ. Các thư mục còn lại đi vào prompt bằng đường dẫn
   *  tuyệt đối. Bỏ tích cái chính thì cái kế tiếp lên thay.
   *
   *  Menu KHÔNG đóng sau mỗi lần tích: chọn ba thư mục mà phải mở menu ba lần thì thà quay
   *  lại kiểu cũ. */
  function idDangGan() { return (S.tmDs || []).map(function (x) { return x.id; }); }

  function menuThuMuc(node) {
    var dang = idDangGan();
    var muc = S.thuMuc.map(function (x) {
      var co = dang.indexOf(x.id) >= 0;
      var laChinh = co && dang[0] === x.id;
      return {
        nhan: x.ten + (x.co_that ? "" : "  (" + t("coding.folder_gone") + ")"),
        phu: (laChinh ? t("coding.folder_main") + " · " : "") + x.duong_dan,
        chon: co,
        tich: true,
        giuMo: true,
        bam: async function () {
          var ids = idDangGan();
          var i = ids.indexOf(x.id);
          if (i >= 0) ids.splice(i, 1); else ids.push(x.id);
          await datRangBuoc({ thu_mucs: ids.join(",") });
        },
      };
    });
    muc.push({ nhan: t("coding.add_folder"), nhanMoi: true, bam: function () { moKhungThemThuMuc(); } });
    if (S.tm) {
      muc.push({ nhan: t("coding.detach_folder"), bam: function () { datRangBuoc({ thu_mucs: "" }); } });
      muc.push({ nhan: t("coding.forget_folder"), nguyHiem: true, bam: function () { boThuMuc(S.tm); } });
    }
    menu(node, muc, menuThuMuc);
  }

  async function boThuMuc(tm) {
    if (!W.confirm(t("coding.forget_confirm", { ten: tm.ten }))) return;
    await api("/coding/folders/" + encodeURIComponent(tm.id) + "/delete", { method: "POST" });
    await taiThuMuc();
    await datRangBuoc({ thu_muc: "" });
  }

  /** Thêm thư mục: MỞ HỘP DUYỆT để bấm chọn, không bắt gõ đường dẫn.
   *
   *  Bản 0.63.2 chỉ có một ô chữ trống. Trên máy để bàn thì còn dán được, nhưng trên điện
   *  thoại thì phải gõ tay một đường dẫn tuyệt đối không dấu gợi ý nào, gõ sai một ký tự là
   *  nhận câu "không phải thư mục" mà không biết sai ở đâu. Chọn thư mục là việc DUYỆT, nên
   *  phải bày ra cái cây để bấm.
   *
   *  Hộp duyệt là JavisFolderPicker, dùng chung với các trang khác, chạy trên chính endpoint
   *  GET /browse mà hộp chọn brain của app vẫn dùng. Truyền demMd=false: người chọn thư mục
   *  code không cần biết trong đó có bao nhiêu file .md, mà đếm nó là quét cả node_modules.
   *  Ô đường dẫn trong hộp vẫn gõ và dán được, nên ai đã có sẵn đường dẫn không mất gì. */
  function moKhungThemThuMuc() {
    dongMenu();
    if (!W.JavisFolderPicker) return;
    W.JavisFolderPicker.open({
      tieuDe: t("coding.add_folder"),
      nhanDung: t("coding.add_folder"),
      demMd: false,
      brain: brain(),
      // Mở sẵn ở thư mục cha của thư mục đang gắn: mấy dự án thường nằm cạnh nhau, nên đó là
      // chỗ gần đích nhất mà Javis biết chắc. Chưa gắn gì thì để rỗng, và hộp mở ra ở màn
      // ĐIỂM XUẤT PHÁT (bộ não đang mở, thư mục chứa các bộ não, thư mục nhà) chứ không đổ
      // thẳng vào thư mục nhà - trên VPS chỗ đó thường rỗng trơn.
      batDau: chaCuaThuMucDangGan(),
      chon: async function (duongDan) {
        var r = await api("/coding/folders", { method: "POST", body: fd({ duong_dan: duongDan, brain: brain() }) });
        // Trả về câu lỗi là hộp GIỮ NGUYÊN và in câu đó: người dùng đang đứng đúng chỗ vừa
        // chọn, chỉ cần bấm sang thư mục khác. Đóng hộp rồi báo lỗi ở đâu đó là bắt họ mở lại
        // và duyệt lại từ đầu.
        if (!r || r.error) return (r && r.error) || t("coding.add_err");
        await taiThuMuc();
        await datRangBuoc({ thu_muc: r.thu_muc.id });
        return "";
      },
    });
  }

  /** Thư mục mở sẵn khi bật hộp duyệt: cha của thư mục đang gắn, rỗng nếu chưa gắn gì. */
  function chaCuaThuMucDangGan() {
    var p = (S.tm && S.tm.duong_dan) || "";
    if (!p) return "";
    var cat = p.replace(/[\\/]+$/, "").split(/[\\/]/);
    cat.pop();
    return cat.length > 1 ? cat.join("/") : "";
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
  /** `veLai` (tuỳ chọn) = hàm dựng lại chính menu này, cho những mục mang `giuMo`. */
  function menu(anchor, muc, veLai) {
    dongMenu();
    var m = document.createElement("div");
    m.className = "cd-menu"; m.id = "cdMenu";
    m.innerHTML = muc.map(function (x, i) {
      // Mục TÍCH CHỌN mang thêm một ô vuông: dấu tích nói "đang gắn", chữ đậm thôi thì
      // người dùng không đoán ra là bấm vào sẽ THÊM hay THAY.
      var o = x.tich ? '<span class="cd-tich">' + (x.chon ? ic("check") : "") + "</span>" : "";
      return '<button type="button" data-i="' + i + '" class="' +
        (x.chon ? "on " : "") + (x.nguyHiem ? "nguy " : "") + (x.tich ? "tich " : "") +
        (x.nhanMoi ? "moi" : "") + '">' + o +
        "<span>" + esc(x.nhan) + (x.phu ? '<small>' + esc(x.phu) + "</small>" : "") + "</span>" +
        "</button>";
    }).join("");
    document.body.appendChild(m);
    // Đặt menu vào chỗ trống THẬT quanh chip. Trước đây chỉ kẹp top >= 8: menu dài hơn
    // khoảng trống phía trên thì tràn xuống đè cả chip lẫn thanh điều hướng (báo 22/09).
    // Nay: ưu tiên mở lên trên, chật quá thì lật xuống dưới, và cắt chiều cao theo chỗ trống
    // để menu tự cuộn thay vì tràn ra ngoài màn hình.
    var r = anchor.getBoundingClientRect();
    var vh = W.innerHeight || 800;
    var tren = Math.max(0, r.top - 14);
    var duoi = Math.max(0, vh - r.bottom - 14);
    var len = m.offsetHeight <= tren || tren >= duoi;
    m.style.maxHeight = Math.max(160, len ? tren : duoi) + "px";
    var cao = m.offsetHeight;
    m.style.left = Math.max(8, Math.min(r.left, (W.innerWidth || 1200) - m.offsetWidth - 8)) + "px";
    m.style.top = (len ? Math.max(8, r.top - cao - 6)
                       : Math.min(r.bottom + 6, Math.max(8, vh - cao - 8))) + "px";
    m.querySelectorAll("[data-i]").forEach(function (b) {
      b.onclick = async function (e) {
        var x = muc[Number(b.dataset.i)];
        if (x && x.giuMo && veLai) {
          e.stopPropagation();          // đừng để cú bấm này rơi xuống bộ đóng menu ở dưới
          if (x.bam) await x.bam();
          if (document.getElementById("cdMenu") === m) veLai(anchor);   // vẽ lại cho đúng dấu tích
          return;
        }
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

  W.JavisCoding = {
    render: render, roi: roi,
    // Phơi cho test node
    chipHtml: chipHtml, nhanHienThi: nhanHienThi,
  };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { chipHtml: chipHtml, nhanHienThi: nhanHienThi };
  }
})();
