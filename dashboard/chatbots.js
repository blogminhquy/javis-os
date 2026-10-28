// ============================================================
// Javis - Trang Chatbot: quản lý các Bot chuyên trách (mỗi bot một Agent, một brain,
// một token Telegram riêng). console.js gọi window.JavisChatbots.render(el).
//
// UX dựng theo hướng NHIỀU BOT ngay từ đầu dù lần đầu chỉ chạy một con: lưới thẻ, ô tìm,
// thêm/sửa/xoá, bật/tắt tại chỗ. Thêm bot thứ hai không phải sửa lại giao diện.
//
// Xem docs/dev/2026-08-bot-chuyen-trach-spec.md
// ============================================================
(function () {
  "use strict";

  // Locale để định dạng số/ngày. Lấy từ i18n chứ KHÔNG khoá "vi-VN": người dùng đổi
  // ngôn ngữ giao diện thì ngày giờ phải đổi theo, nếu không thì nửa màn hình tiếng Anh
  // mà ngày vẫn dd/mm/yyyy kiểu Việt.
  const LOC = () => (window.JavisI18n && JavisI18n.locale()) || "vi-VN";
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  // (i) button (info-tip.js, 0.214.0): explanations sit behind it; without the helper (Node tests) they draw open.
  function infoBtn() { var J = typeof window !== "undefined" && window.JavisInfo; return J ? J.btn(window.t("info.more")) : ""; }
  function infoBody(html) {
    var J = typeof window !== "undefined" && window.JavisInfo;
    return J ? J.body(html) : '<div class="info-body">' + html + "</div>";
  }
  function el(html) { var d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstChild; }
  function brain() { try { return (window.currentBrainPath && window.currentBrainPath()) || "brain"; } catch (e) { return "brain"; } }

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

  // Bốn trạng thái THẬT, không phải hai. "Bot chết âm thầm" là thứ chủ chỉ phát hiện khi
  // có người phàn nàn, nên lỗi phải là một ô màu nhìn thấy được chứ không phải sự vắng mặt.
  var TRANG_THAI = {
    running:  { nhan: "cb.tt_dang_chay", mau: "ok" },
    starting: { nhan: "cb.tt_khoi_dong", mau: "wait" },
    error:    { nhan: "cb.tt_loi", mau: "err" },
    off:      { nhan: "cb.tt_tat", mau: "off" },
  };

  // Nhãn + cảnh báo của từng mức quyền do SERVER cấp (kèm trong GET /chatbots). Không chép
  // cứng ở đây: chép rồi thì một hôm server siết thêm rào mà ô cảnh báo vẫn hứa như cũ, và
  // chủ bấm đồng ý dựa trên một câu đã sai.
  var _bots = [], _q = "", _host = null, _mucDS = [], _timer = null, _dauVet = "";
  // Danh sách kênh do SERVER cấp (kèm chỗ lấy token và kênh đó KHÔNG làm được gì). Không chép
  // cứng ở đây: hôm nào Zalo mở API gửi tài liệu thì server đổi một chỗ, giao diện theo ngay.
  var _kenhDS = [], _kenhLoc = "";
  // Tài khoản kênh chưa bot nào trực (server cấp kèm GET /chatbots). Form tạo bot cho CHỌN
  // trong danh sách này thay vì bắt dán token; dán token mới cũng được, và token đó thành một
  // tài khoản ở tab Tài khoản bot.
  var _tkRanh = [];
  // Tài khoản kênh đang do MỘT bot trực (0.65.9): form Bot mới hiện chúng mờ kèm tên bot giữ, thay vì giấu đi.
  var _tkBan = [];

  // Kênh KHÔNG đoán theo id: mọi thứ (nhãn, logo, năng lực) lấy từ danh sách server cấp. Kênh
  // lạ (server mới có kênh mà giao diện cũ) thì hiện tên trần, không vẽ nhầm logo kênh khác.
  function kenhCua(id) {
    for (var i = 0; i < _kenhDS.length; i++) if (_kenhDS[i].id === id) return _kenhDS[i];
    return { id: id || "", nhan: id || "", logo: "", lay_token: "", co_nhom: false, gui_tai_lieu: false,
             tien_to_ten: "", tom_tat: "", nang_luc: {} };
  }
  function logoKenh(id, size) {
    var k = kenhCua(id);
    return k.logo ? Icons.kenh(k.logo, { size: size || "13px" }) : "";
  }

  // Nhãn kênh: LOGO + tên. Đây là thứ phân biệt hai con bot trong cùng một lưới thẻ, nên nó
  // phải bắt mắt trước khi người ta kịp đọc chữ - xem khối chú thích ở Icons.kenh.
  function chipKenh(id, cls) {
    return '<span class="cb-kenh-chip ' + (cls || "") + '">' + logoKenh(id) +
           " " + esc(kenhCua(id).nhan) + "</span>";
  }
  // Chip MỘT tài khoản kênh trên thẻ bot: logo kênh + tên tài khoản phía nền tảng.
  function chipTK(a) {
    var k = kenhCua(a.channel);
    var ten = logoKenh(a.channel) + " " + esc(a.external_id ? (k.tien_to_ten || "") + a.external_id : (a.label || k.nhan));
    // Kênh kiểu "bot" (Telegram, Zalo Bot) sửa được ngay tại đây: bấm chip mở bảng sửa kênh (nhãn, token, brain, xoá). Kênh kiểu
    // "account" (Zalo cá nhân) là một kết nối ở trang Kết nối nên chip chỉ để đọc. Từ 0.65.9 không còn tab riêng cho kênh.
    if (k.kind === "bot") {
      return '<button type="button" class="cb-kenh-chip cb-kenh-sua" data-tk="' + esc(a.id) + '" title="' +
             esc(window.t("cb.sua_kenh_title", { kenh: k.nhan })) + '">' + ten + "</button>";
    }
    // 0.174.0: kênh nhập được tin cũ (Zalo cá nhân) thì chip là nút nhập tin cũ. Kênh đã có bot không hiện thẻ riêng ở mục
    // "Kênh chưa có bot", nên đây là chỗ duy nhất chủ bấm được.
    if ((k.nang_luc || {}).nhap_lich_su) {
      return '<button type="button" class="cb-kenh-chip cb-kenh-nhap-cu" data-tk="' + esc(a.id) + '" title="' +
             esc(window.t("cb.nhap_cu_title", { kenh: k.nhan })) + '">' + ten + ' ' + ic("history") + "</button>";
    }
    return '<span class="cb-kenh-chip" title="' + esc(k.nhan) + '">' + ten + "</span>";
  }
  // Bot có tài khoản nào đứng được trong nhóm không (quyết định khối cấu hình nhóm).
  function coNhom(b) {
    return (b.accounts || []).some(function (a) { return kenhCua(a.channel).co_nhom; });
  }

  // Trạng thái bot là thứ ĐỔI MÀ KHÔNG AI BẤM: bấm Bật xong server trả về "đang khởi động"
  // (poller mới tạo, chưa kịp hỏi Telegram), rồi vài giây sau nó thành "đang chạy" - nhưng
  // trang chỉ nạp lại khi người dùng bấm cái gì đó, nên thẻ đứng nguyên ở "Đang khởi động" cho
  // tới lúc rời trang rồi quay lại. Chủ repo dính đúng ca này: bot chạy thật, trả lời thật, mà
  // thẻ vẫn báo đang khởi động. Poller cũng là chỗ duy nhất thấy được bot vừa CHẾT.
  var NHIP = 5000;

  function mucCua(id) {
    for (var i = 0; i < _mucDS.length; i++) if (_mucDS[i].id === id) return _mucDS[i];
    return { id: id || "suggest", nhan: window.t("cb.muc_chi_doc"), canh_bao: [], can_xac_nhan: false };
  }

  // Nhịp tự làm mới. Dừng khi node của trang đã bị tháo khỏi DOM (console.js thay hẳn
  // #cviewBody mỗi lần đổi trang) và khi tab bị ẩn - không thì mỗi trang từng mở để lại một
  // vòng lặp gọi mạng mãi mãi.
  function nhipTuLamMoi() {
    if (_timer) { clearInterval(_timer); _timer = null; }
    _timer = setInterval(function () {
      if (!_host || !document.body.contains(_host)) { clearInterval(_timer); _timer = null; return; }
      if (document.hidden) return;
      if (document.querySelector(".cb-modal")) return;   // đang mở form: đừng vẽ lại dưới chân
      tai(true);
    }, NHIP);
  }

  function render(host) {
    _host = host;
    host.innerHTML =
      '<div class="cview-section cb-wrap">' +
        '<div class="cb-bar">' +
          '<input class="cb-search" placeholder="' + esc(window.t("cb.tim_ph")) + '">' +
          '<button class="s-btn cb-new" type="button">' + ic("plus") + ' ' +
            esc(window.t("cb.bot_moi")) + '</button>' +
        '</div>' +
        '<div class="cb-loc"></div>' +
        // One short line stays on the page; the rest of the intro folds behind (i) (0.214.0).
        '<div class="cb-intro">' + esc(window.t("cb.intro_1")) + ' <b>' + esc(brain()) + '</b>' + infoBtn() + '</div>' +
        infoBody(esc(window.t("cb.intro_2").replace(/^[.\s]+/, "")) + ' <b>Agent</b> ' +
          esc(window.t("cb.intro_3")) + esc(window.t("cb.intro_4")) +
          ' <b>' + esc(window.t("cb.intro_chi_doc")) + '</b>' + esc(window.t("cb.intro_5")) +
          ' <b>' + esc(window.t("cb.intro_lam_that")) + '</b> ' + esc(window.t("cb.intro_6")) + '<br>' +
          esc(window.t("cb.intro_7")) + '<br>' + esc(window.t("cb.intro_8"))) +
        '<div class="cb-grid"></div>' +
      '</div>';
    host.querySelector(".cb-new").onclick = function () { moForm(null); };
    var s = host.querySelector(".cb-search");
    s.oninput = function () { _q = s.value.trim().toLowerCase(); ve(); };
    tai();
    nhipTuLamMoi();
  }

  // `im` = lần nạp của nhịp tự động: KHÔNG được xoá lưới đang hiện để thay bằng "Đang tải…",
  // và mạng hỏng một nhịp thì giữ nguyên màn hình cũ chứ đừng thay bằng câu báo lỗi. Nhấp nháy
  // mỗi năm giây còn khó chịu hơn con số cũ vài giây.
  async function tai(im) {
    var box = _host && _host.querySelector(".cb-grid");
    if (!box) return;
    if (!im) box.innerHTML = '<div class="cb-empty">' + esc(window.t("common.loading")) + '</div>';
    try {
      // Lọc theo brain đang mở: trang này thuộc về một brain, y như trang Agents và Skills.
      // console.js tự gọi lại renderPage khi đổi brain nên không cần lắng nghe gì thêm.
      var d = await api("/chatbots?brain=" + encodeURIComponent(brain()));
      _bots = d.bots || [];
      _mucDS = d.muc_quyen || [];
      _langDS = d.lang_list || [];
      _kenhDS = d.kenh || [];
      _tkRanh = d.tai_khoan || [];
      _tkBan = d.tai_khoan_ban || [];
      var vet = JSON.stringify(_bots);
      // Nhịp ngầm mà không có gì đổi thì ĐỪNG dựng lại DOM. Không phải để tiết kiệm: dựng lại
      // mỗi 5 giây nghĩa là cứ 5 giây một lần có một khoảnh khắc nút vừa bị thay khỏi cây, và
      // cú bấm rơi đúng lúc đó thì mất.
      if (im && vet === _dauVet) return;
      _dauVet = vet;
    } catch (e) {
      if (!im) box.innerHTML = '<div class="cb-empty">' + esc(window.t("cb.loi_tai_ds")) + ' ' +
                               esc(e.message) + '</div>';
      return;
    }
    ve();
  }

  // Bộ lọc kênh chỉ hiện khi thật sự có từ HAI kênh trở lên. Người mới chỉ có bot Telegram mà
  // đã phải nhìn một hàng nút lọc thì đó là câu trả lời cho một câu hỏi họ chưa từng hỏi.
  function veLoc() {
    var hop = _host && _host.querySelector(".cb-loc");
    if (!hop) return;
    var dem = {};
    _bots.forEach(function (b) {
      var k = b.channel || "telegram";
      dem[k] = (dem[k] || 0) + 1;
    });
    var ks = Object.keys(dem);
    if (ks.length < 2) { hop.innerHTML = ""; _kenhLoc = ""; return; }
    hop.innerHTML =
      '<button class="cb-loc-o' + (_kenhLoc ? "" : " on") + '" data-k="" type="button">' +
        esc(window.t("studio.all")) + ' <span class="cb-loc-n">' + _bots.length + '</span></button>' +
      ks.map(function (k) {
        return '<button class="cb-loc-o' + (_kenhLoc === k ? " on" : "") + '" data-k="' + esc(k) +
          '" type="button">' + logoKenh(k, "14px") + " " + esc(kenhCua(k).nhan) +
          ' <span class="cb-loc-n">' + dem[k] + '</span></button>';
      }).join("");
    hop.querySelectorAll(".cb-loc-o").forEach(function (n) {
      n.onclick = function () { _kenhLoc = n.dataset.k || ""; ve(); };
    });
  }

  function ve() {
    var box = _host && _host.querySelector(".cb-grid");
    if (!box) return;
    veLoc();
    var ds = _bots.filter(function (b) {
      if (_kenhLoc && (b.channel || "telegram") !== _kenhLoc) return false;
      return !_q || String(b.name || "").toLowerCase().indexOf(_q) !== -1;
    });
    if (!_bots.length) {
      box.innerHTML =
        '<div class="cb-empty"><div class="cb-empty-ico">' + ic("headset", { cls: "ic-xl" }) + '</div>' +
        '<b>' + esc(window.t("cb.rong_tieu_de")) + infoBtn() + '</b>' +
        infoBody(esc(window.t("cb.rong_1")) + ' <b>' + esc(window.t("cb.rong_tat")) + '</b>' + esc(window.t("cb.rong_2"))) + '</div>';
      return;
    }
    if (!ds.length) { box.innerHTML = '<div class="cb-empty">' + esc(window.t("cb.khong_khop")) + '</div>'; return; }
    box.innerHTML = "";
    ds.forEach(function (b) { box.appendChild(the(b)); });
  }

  function the(b) {
    var st = b.status || {};
    var tt = TRANG_THAI[st.state] || TRANG_THAI.off;
    var loi = st.last_error ? '<div class="cb-err">' + esc(String(st.last_error).slice(0, 2000)) + '</div>' : "";
    // Agent bị xoá hay đổi slug: bot vẫn chạy nhưng trả lời bằng vai trò rỗng. Phải báo,
    // không được để im - đó đúng kiểu hỏng mà cả tính năng này đang cố tránh.
    var mat = b.agent_missing
      ? '<div class="cb-err">' + ic("triangle-alert") + ' ' +
        esc(window.t("cb.agent_mat", {
          // Bot thiếu hẳn object agent (hoặc agent không có slug) thì chỗ điền nhận undefined,
          // mà t() chỉ thay khi giá trị khác null - để nguyên là người dùng đọc thấy "{slug}".
          slug: (b.agent || {}).slug || window.t("cb.agent_khong_ro"),
        })) + '</div>' : "";
    // Poller sống KHÔNG có nghĩa là bot trả lời được: model gọi hỏng thì chấm vẫn xanh trong
    // khi người hỏi nhận toàn câu xin lỗi. Lỗi lượt gần nhất phải nằm ngay trên thẻ, không bắt chủ
    // mở Nhật ký mới thấy - vì chủ chỉ mở Nhật ký khi đã NGỜ là có chuyện.
    var lluot = b.loi_luot
      ? '<div class="cb-err">' + ic("triangle-alert") + ' ' + esc(window.t("cb.luot_loi")) + ' ' +
        esc(String(b.loi_luot).slice(0, 2000)) + '</div>' : "";
    // Lượt CHẠY ĐƯỢC nhưng không đúng mức đã đặt (engine không gọi nổi công cụ, hoặc chưa đấu
    // nguồn nào). Màu vàng chứ không đỏ: bot vẫn trả lời tử tế, chỉ là chạy thiếu quyền. Để im
    // thì chủ tưởng bot đang làm việc thật - đúng kiểu hỏng lặng lẽ mà cả trang này chống.
    var cbao = b.canh_bao_luot
      ? '<div class="cb-quyen ghi">' + ic("triangle-alert") + '<span class="cb-quyen-t">' +
        esc(String(b.canh_bao_luot).slice(0, 2000)) + '</span></div>' : "";
    // Mức quyền phải nhìn thấy TỪ NGOÀI THẺ, không phải mở form Sửa mới biết. Một con bot toàn
    // quyền lẫn giữa mấy con chỉ đọc mà nhìn giống hệt nhau là đúng kiểu hỏng im lặng: chủ nhớ
    // nhầm con nào là con nào rồi thả nhầm vào chỗ ai cũng nhắn được.
    //
    // Hiện CẢ mức chỉ đọc, dù nó là mặc định và không có rủi ro gì để cảnh báo. Bản trước bỏ
    // trống ô này cho mức đó, và "không có nhãn" đọc ra được hai nghĩa trái ngược nhau: bot
    // đang chỉ đọc, hay trang này không nói cho biết? Chủ repo hỏi đúng câu ấy. Một nhãn xám
    // rẻ hơn nhiều so với một lần đoán sai theo hướng ngược lại.
    var mq = b.muc_quyen || "suggest";
    var mqLoi = {
      suggest: " - " + window.t("cb.mq_suggest"),
      read_docs: " - " + window.t("cb.mq_read_docs"),
      auto: " - " + window.t("cb.mq_auto"),
      full: " - " + window.t("cb.mq_full"),
    };
    var quyen =
      '<span class="cb-quyen ' + (mq === "full" ? "full" : mq === "auto" ? "ghi" : "doc") +
      '" title="' + esc(String(mqLoi[mq] || "").replace(/^ - /, "")) + '">' +
        // "shield-alert" không có trong bộ icon đã vendor nên bản trước vẽ ra một ô trống ở
        // đúng chỗ đáng chú ý nhất. Test icon không bắt được vì nó chỉ dò tên viết thẳng trong
        // lời gọi, không dò lời gọi có biểu thức ở trong.
        ic(mq === "full" ? "shield" : mq === "auto" ? "pencil" : mq === "read_docs" ? "book-open" : "eye") +
        ' <b>' + esc(mucCua(mq).nhan) + '</b>' +
      '</span>';
    // Nhóm có người gọi bot mà chủ chưa cho phép. Đây là chỗ sửa cho lỗi "thả bot vào nhóm,
    // tag tên nó, không thấy gì": hành vi từ chối vẫn đúng, nhưng nay nó nổi lên đây kèm đúng
    // một nút bấm, thay vì bắt chủ đoán rằng mình phải đi khai id nhóm ở đáy form Sửa.
    var cho = (b.nhom_cho || []).map(function (g) {
      // Từ 0.64.85 hàng chờ có cả NGƯỜI chưa được chọn (bot trả lời "chỉ người và nhóm tôi chọn").
      var nguoi = g.loai === "private";
      return '<div class="cb-nhomcho" data-cid="' + esc(g.chat_id) + '" data-loai="' + (nguoi ? "private" : "group") + '">' +
        '<div class="cb-nhomcho-t">' + ic(nguoi ? "user" : "message-circle") + ' <b>' +
          esc(g.ten || ((nguoi ? window.t("cb2.pk_nguoi") : window.t("cb.nhom")) + " " + g.chat_id)) +
          '</b> <span class="cb-nhomcho-id">' + esc(g.chat_id) + '</span></div>' +
        '<div class="cb-nhomcho-d">' + esc(nguoi
          ? window.t(g.lan ? "cb2.nguoicho_goi" : "cb2.nguoicho_moi", { count: g.lan })
          : (g.lan ? window.t("cb.nhomcho_goi", { count: g.lan }) : window.t("cb.nhomcho_chua_bat"))) + '</div>' +
        '<div class="cb-nhomcho-a">' +
          '<button class="s-btn cb-ok-nhom" type="button">' + ic("check") + ' ' +
            esc(window.t(nguoi ? "cb2.cho_nguoi" : "cb.cho_phep_nhom")) + '</button>' +
          '<button class="s-btn-ghost cb-bo-nhom" type="button">' +
            esc(window.t("cb.bo_qua")) + '</button>' +
        '</div></div>';
    }).join("");
    // getMe hỏng: bot vẫn trả lời tin nhắn riêng hoàn hảo nhưng ĐIẾC trong mọi nhóm, vì không
    // biết @username của chính mình thì không nhận ra ai đang gọi tên. Chấm vẫn xanh, lượt vẫn
    // chạy, không có gì đỏ - nên nếu không có dòng này thì không ai đoán ra được.
    var loiTen = st.loi_danh_tinh
      ? '<div class="cb-err">' + ic("triangle-alert") + ' ' + esc(st.loi_danh_tinh) + '</div>' : "";
    // Cùng loại hỏng-âm-thầm: menu lệnh "/" đặt hụt thì khách gõ "/" không thấy gì để bấm,
    // trong khi thẻ vẫn xanh và bot vẫn trả lời bình thường.
    if (st.loi_menu_lenh)
      loiTen += '<div class="cb-err">' + ic("triangle-alert") + ' ' + esc(st.loi_menu_lenh) + '</div>';
    // Chế độ riêng tư của Telegram chặn Ở PHÍA TELEGRAM, trước khi Javis nhìn thấy tin nào.
    // Hiện cho MỌI bot có dùng nhóm, không riêng bot đặt "trả lời mọi tin": nó là nguyên nhân
    // số một của "nhắn riêng thì được, trong nhóm tag tên thì im re", và người dùng không có
    // cách nào đoán ra vì mọi dấu hiệu trên trang này đều xanh.
    var kenh = b.channel || "";
    var duNhom = (b.groups || []).length || (b.nhom_cho || []).length;
    // Cảnh báo chế độ riêng tư là chuyện RIÊNG của Telegram. Hiện nó trên một thẻ Zalo là dạy
    // người dùng đi mở @BotFather tìm một cài đặt không tồn tại cho con bot đó.
    var coTelegram = (b.accounts || []).some(function (a) { return a.channel === "telegram"; });
    var riengTu = (coTelegram && duNhom && st.da_hoi_telegram && !st.doc_moi_tin_nhom)
      ? '<div class="cb-quyen ghi">' + ic("triangle-alert") + '<span class="cb-quyen-t">' + esc(window.t("cb.rt_1")) +
        ' <b>' + esc(window.t("cb.rt_che_do")) + '</b> ' + esc(window.t("cb.rt_2")) +
        ' <b>' + esc(window.t("cb.rt_lenh")) + '</b> ' + esc(window.t("cb.rt_va")) +
        ' <b>' + esc(window.t("cb.rt_tra_thang")) + '</b>' +
        esc(b.reply_when === "always" || b.reply_when === "auto" ? window.t("cb.rt_always") : window.t("cb.rt_mention")) + '.' +
        // The problem stays visible; how to fix it opens from (i) (0.214.0).
        infoBtn() + '</span>' + infoBody(esc(window.t("cb.rt_fix_1")) + ' <b>@BotFather</b> ' + esc(window.t("cb.rt_go")) +
        ' <b>/setprivacy</b>' + esc(window.t("cb.rt_fix_2")) + ' <b>Disable</b>' +
        esc(window.t("cb.rt_fix_3")) + ' <b>' + esc(window.t("cb.rt_quan_tri")) + '</b>. ' +
        esc(window.t("cb.rt_fix_4"))) + '</div>' : "";
    var c = el(
      '<div class="cb-card">' +
        '<div class="cb-head">' +
          '<span class="cb-ico">' + ic(b.icon || "headset") +
            ((b.accounts || []).length === 1
              ? '<span class="cb-ico-kenh" title="' + esc(kenhCua(kenh).nhan) + '">' + logoKenh(kenh, "14px") + '</span>'
              : "") + '</span>' +
          '<span class="cb-name">' + esc(b.name) + '</span>' +
          '<span class="cb-dot ' + tt.mau + '" title="' + esc(st.last_error || window.t(tt.nhan)) + '"></span>' +
          '<span class="cb-state">' + esc(window.t(tt.nhan)) + '</span>' +
        '</div>' +
        // Không hiện brain trên thẻ nữa: mọi bot ở đây đều thuộc brain đang mở, nên nhắc lại
        // trên từng thẻ chỉ là nhiễu. Brain nói một lần ở đầu trang là đủ.
        // Tài khoản kênh bot đang trực (0.61.0: một bot trực được nhiều tài khoản). Chưa có
        // tài khoản nào thì nói thẳng, vì đó là lý do bot không bật được.
        '<div class="cb-meta">' +
          ((b.accounts || []).length
            ? (b.accounts || []).map(chipTK).join("")
            : '<span class="cb-warn">' + ic("triangle-alert") + ' ' + esc(window.t("cb.chua_token")) + '</span>') +
          // Thêm kênh ngay trên thẻ: mở form Sửa ở bước chọn kênh (kênh rảnh, kênh mới, hoặc sang trang Kết nối cho Zalo cá nhân).
          '<button type="button" class="cb-kenh-chip cb-kenh-them">' + ic("plus") + ' ' + esc(window.t("ht.them_tk")) + '</button>' +
          '<span>' + ic("user-round") + ' ' + esc(b.agent_name || (b.agent || {}).slug || "?") + '</span>' +
          // Model bot chạy ra ngoài. Nó là model của trợ lý (0.62.3), nên phải hiện ở đây - nếu không
          // thì chọn model cho trợ lý xong vẫn không biết bot đã theo hay chưa.
          '<span title="' + esc(window.t("cb.model_title")) + '">' + ic("cpu") + ' ' +
            esc(b.agent_model || window.t("cb.model_chinh")) + '</span>' +
          quyen +
        '</div>' +
        // Một dòng "bot trả lời ai" thay cho ba dòng meta cũ: đọc là biết bot đang nói chuyện với ai.
        '<div class="cb-meta cb-tt">' +
          '<span class="cb-tt-t">' + ic("users") + ' <b>' + esc(window.t("cb2.tra_loi")) + '</b> ' +
            esc(tomTatDoiTuong(b)) +
            (window.JavisReplyPolicy && window.JavisReplyPolicy.summary(b) && !(b.audience === "all" && b.reply_when === "auto")
              ? ' · ' + esc(window.JavisReplyPolicy.summary(b)) : '') + '</span>' +
        '</div>' +
        '<div class="cb-meta">' +
          '<span>' + esc(b.nguon_tra_loi === "tai_lieu" ? window.t("cb.nguon_tl_ngan")
                                                        : window.t("cb.nguon_ag_ngan")) + '</span>' +
          '<span>' + esc(window.t("cb.n_luot_tra_loi", { count: st.answered || 0 })) + '</span>' +
        '</div>' +
        // Hộp thư hội thoại: số cuộc chat khách hôm nay và số chưa đọc, ngay trên thẻ. Bấm nút
        // Hội thoại ở dưới là sang trang Hội thoại đã lọc sẵn theo bot này.
        (b.hoi_thoai && (b.hoi_thoai.tong || 0) > 0
          ? '<div class="cb-meta"><span>' + ic("messages-square") + ' ' +
            esc(window.t("cb.hoi_thoai_tom", { hom_nay: b.hoi_thoai.hom_nay || 0,
                                               chua_doc: b.hoi_thoai.chua_doc || 0 })) + '</span></div>'
          : "") +
        statusRow({ err: [loiTen, mat, lluot, loi], warn: [riengTu, cbao], wait: [cho] }) +
        // Bật/tắt và Sửa nằm ngoài, ba việc phụ (nhật ký, hội thoại, xoá) vào menu "...": thẻ có
        // năm nút ngang hàng thì không nút nào nổi bật, và Xoá đứng cạnh Sửa là chỗ bấm nhầm.
        '<div class="cb-acts">' +
          '<button class="s-btn-ghost cb-toggle" type="button">' +
            (b.enabled ? ic("circle-stop") + " " + esc(window.t("cb.tat"))
                       : ic("play") + " " + esc(window.t("cb.bat"))) + '</button>' +
          '<button class="s-btn-ghost cb-edit" type="button">' + ic("pencil") + ' ' +
            esc(window.t("common.edit")) + '</button>' +
          '<button class="s-btn-ghost cb-try" type="button">' + ic("play") + ' ' +
            esc(window.t("try.btn")) + '</button>' +
          '<span class="cb-mn">' +
            '<button class="s-btn-ghost cb-mn-b" type="button" aria-label="' + esc(window.t("cb2.mn")) +
              '" title="' + esc(window.t("cb2.mn")) + '">&#8943;</button>' +
            '<div class="cb-mn-l" hidden>' +
              '<button class="cb-log" type="button">' + ic("history") + ' ' + esc(window.t("cb.nhat_ky")) + '</button>' +
              // 0.309.0 (owner, 25/10/2026: "không thấy nút nào để nhập"): the account chip doubles as the import button,
              // which nobody recognised; the menu now names the action. One item per account that can import.
              (b.accounts || []).filter(function (a) { return (kenhCua(a.channel).nang_luc || {}).nhap_lich_su; })
                .map(function (a, i, ds) {
                  return '<button class="cb-nhap-cu" type="button" data-tk="' + esc(a.id) + '">' + ic("download") + ' ' +
                    esc(window.t("ht.nhap_cu")) + (ds.length > 1 ? ' (' + esc(a.label || a.external_id || a.id) + ')' : '') +
                    '</button>';
                }).join("") +
              (b.reply_when === "auto"
                ? '<button class="cb-rp" type="button">' + ic("brain") + ' ' + esc(window.t("rp.menu")) + '</button>' : '') +
              '<button class="cb-hoi-thoai" type="button">' + ic("messages-square") + ' ' +
                esc(window.t("cb.xem_hoi_thoai")) + '</button>' +
              '<button class="cb-del" type="button">' + ic("trash-2") + ' ' + esc(window.t("common.delete")) + '</button>' +
            '</div>' +
          '</span>' +
        '</div>' +
      '</div>');
    // Menu "...": mở/đóng bằng nút, tự đóng khi bấm ra ngoài hoặc chọn một việc.
    var mnB = c.querySelector(".cb-mn-b"), mnL = c.querySelector(".cb-mn-l");
    mnB.onclick = function (e) { e.stopPropagation(); mnL.hidden = !mnL.hidden; };
    mnL.onclick = function () { mnL.hidden = true; };
    document.addEventListener("click", function tat(e) {
      if (!document.body.contains(c)) { document.removeEventListener("click", tat); return; }
      if (!c.querySelector(".cb-mn").contains(e.target)) mnL.hidden = true;
    });
    c.querySelector(".cb-toggle").onclick = function () { bat(b, !b.enabled); };
    c.querySelector(".cb-log").onclick = function () { moNhatKy(b); };
    var nutRp = c.querySelector(".cb-rp");
    if (nutRp) nutRp.onclick = function () { window.JavisReplyPolicy.openPanel(b); };
    c.querySelector(".cb-hoi-thoai").onclick = function () {
      if (window.JavisConversations) window.JavisConversations.mo({ bot_id: b.id });
    };
    c.querySelector(".cb-edit").onclick = function () { moForm(b); };
    // Thử bot (0.78.0): chạy một tin giả, không gửi gì ra ngoài. Xem chatbots-try.js.
    c.querySelector(".cb-try").onclick = function () {
      // Bot chưa gắn kênh nào vẫn thử được "Trong nhóm": chỉnh bot cho ổn rồi mới gắn kênh.
      if (window.JavisTryBot) window.JavisTryBot.open(b, { groups: coNhom(b) || !(b.accounts || []).length });
    };
    c.querySelector(".cb-kenh-them").onclick = function () { moForm(b, { buoc: 1 }); };
    c.querySelectorAll(".cb-kenh-nhap-cu, .cb-nhap-cu").forEach(function (n) {
      n.onclick = function () {
        var fn = window.JavisConversations && window.JavisConversations.nhapTinCu;
        var a = (b.accounts || []).filter(function (x) { return x.id === n.dataset.tk; })[0];
        if (fn && a) fn(a, n);
      };
    });
    c.querySelectorAll(".cb-kenh-sua").forEach(function (n) {
      n.onclick = function () {
        var fn = window.JavisConversations && window.JavisConversations.suaKenh;
        if (fn) fn(n.dataset.tk);
      };
    });
    c.querySelector(".cb-del").onclick = function () { xoa(b); };
    var stBtn = c.querySelector(".cb-st");
    var stHtml = cho + loiTen + riengTu + mat + lluot + cbao + loi;
    if (stBtn) stBtn.onclick = function () { openStatus(b, stHtml); };
    return c;
  }

  // 0.309.0 (owner, 25/10/2026: long errors and the pending-group list overflowed the card): the card shows one
  // compact status row with counts and the most important line; the full text and the allow/ignore buttons open in
  // a popup.
  function statusRow(parts) {
    var n = function (list) { return list.filter(function (x) { return !!x; }).length; };
    var err = n(parts.err), warn = n(parts.warn);
    var wait = (parts.wait[0] || "").split('class="cb-nhomcho"').length - 1;
    if (!err && !warn && !wait) return "";
    var kind = err ? "err" : wait ? "wait" : "warn";
    var chips = (err ? '<span class="cb-st-chip err">' + ic("triangle-alert") + ' ' +
                   esc(window.t("cb.st_err", { count: err })) + '</span>' : "") +
                (wait ? '<span class="cb-st-chip wait">' + ic("users") + ' ' +
                   esc(window.t("cb.st_wait", { count: wait })) + '</span>' : "") +
                (warn ? '<span class="cb-st-chip warn">' + ic("triangle-alert") + ' ' +
                   esc(window.t("cb.st_warn", { count: warn })) + '</span>' : "");
    return '<button type="button" class="cb-st ' + kind + '" aria-haspopup="dialog">' +
      '<span class="cb-st-chips">' + chips + '</span>' +
      '<span class="cb-st-more">' + esc(window.t("cb.st_open")) + ' ' + ic("chevron-right") + '</span>' +
    '</button>';
  }

  function openStatus(b, html) {
    var box = el('<div class="cb-modal"><div class="cb-form cb-st-form" role="dialog" aria-modal="true">' +
      '<h3>' + esc(window.t("cb.st_title")) + ' - ' + esc(b.name) + '</h3>' +
      '<div class="cb-st-body">' + html + '</div>' +
      '<div class="cb-form-acts"><button class="s-btn" type="button" data-close>' +
        esc(window.t("common.close")) + '</button></div>' +
      '</div></div>');
    document.body.appendChild(box);
    var close = function () { if (box.parentNode) box.parentNode.removeChild(box); };
    box.onmousedown = function (e) { if (e.target === box) close(); };
    box.querySelector("[data-close]").onclick = close;
    box.querySelectorAll(".cb-nhomcho").forEach(function (n) {
      var cid = n.dataset.cid, loai = n.dataset.loai;
      n.querySelector(".cb-ok-nhom").onclick = function () { close(); choNhom(b, cid, true, loai); };
      n.querySelector(".cb-bo-nhom").onclick = function () { close(); choNhom(b, cid, false, loai); };
    });
  }

  // Một cú bấm thay cho: gõ /id trong nhóm, chép id, mở Sửa, kéo xuống đáy form, dán, Lưu.
  async function choNhom(b, cid, on, loai) {
    try {
      // Người (audience `chon`) đi đường /people, nhóm đi đường /groups.
      await api("/chatbots/" + encodeURIComponent(b.id) + (loai === "private" ? "/people" : "/groups"),
                { method: "POST", body: fd({ chat_id: cid, on: on ? "1" : "0" }) });
    } catch (e) {
      alert(window.t("cb.loi_cap_nhat_nhom") + " " + e.message);
    }
    tai();
  }

  // ---------------------------------------------------------------- nhật ký + lỗ hổng
  // Mở tab "Bot bí" TRƯỚC, không phải tab hội thoại. Hội thoại chỉ để soi lại khi nghi ngờ,
  // còn danh sách câu bot trả lời không nổi mới là thứ chủ cần LÀM GÌ ĐÓ với nó: mỗi dòng ở
  // đó là một chỗ tài liệu đang thiếu, viết bổ sung vào brain là lần sau bot trả lời được.
  async function moNhatKy(b) {
    var box = el('<div class="cb-modal"><div class="cb-form cb-log-form">' +
      '<h3>' + esc(window.t("cb.nhat_ky")) + ' - ' + esc(b.name) + '</h3>' +
      '<div class="cb-tabs">' +
        '<button class="cb-tab on" data-t="gaps" type="button">' + esc(window.t("cb.tab_bi")) + '</button>' +
        '<button class="cb-tab" data-t="turns" type="button">' + esc(window.t("cb.tab_hoi_thoai")) + '</button>' +
      '</div>' +
      '<div class="cb-log-body">' + esc(window.t("common.loading")) + '</div>' +
      '<div class="cb-form-acts"><button class="s-btn" id="cbLogClose" type="button">' +
        esc(window.t("common.close")) + '</button></div>' +
      '</div></div>');
    document.body.appendChild(box);
    var dong = function () { if (box.parentNode) box.parentNode.removeChild(box); };
    box.onmousedown = function (e) { if (e.target === box) dong(); };
    box.querySelector("#cbLogClose").onclick = dong;

    var than = box.querySelector(".cb-log-body"), d = null;
    try { d = await api("/chatbots/" + encodeURIComponent(b.id) + "/log?limit=60"); }
    catch (e) { than.textContent = window.t("cb.loi_tai_nhat_ky") + " " + e.message; return; }

    function ve(tab) {
      if (tab === "turns") { than.innerHTML = veLuot(d.turns || []); return; }
      than.innerHTML = veLoHong(d.gaps || [], d.tom_tat || {});
    }
    box.querySelectorAll(".cb-tab").forEach(function (t) {
      t.onclick = function () {
        box.querySelectorAll(".cb-tab").forEach(function (x) { x.classList.remove("on"); });
        t.classList.add("on");
        ve(t.dataset.t);
      };
    });
    ve("gaps");
  }

  function gio(ts) {
    if (!ts) return "";
    try { return new Date(ts * 1000).toLocaleString(LOC()); } catch (e) { return ""; }
  }

  function veLoHong(gaps, tt) {
    if (!gaps.length) {
      return '<div class="cb-empty">' + (tt.luot
        ? '<b>' + esc(window.t("cb.bi_rong")) + '</b><div>' +
          esc(window.t("cb.bi_rong_luot", { count: tt.luot })) + '</div>'
        : '<b>' + esc(window.t("cb.chua_luot")) + '</b><div>' +
          esc(window.t("cb.chua_luot_goi_y")) + '</div>') + '</div>';
    }
    return '<div class="cb-sum">' + esc(window.t("cb.tom_tat",
        { luot: tt.luot, bi: tt.bi, ty_le: tt.ty_le_bi })) + '</div>' +
      '<table class="cb-tbl"><thead><tr><th>' + esc(window.t("cb.th_hoi")) + '</th><th>' +
      esc(window.t("cb.th_so_lan")) + '</th><th>' + esc(window.t("cb.th_gan_nhat")) +
      '</th></tr></thead><tbody>' +
      gaps.map(function (g) {
        return '<tr><td>' + esc(g.hoi) + '</td><td class="cb-num">' + g.lan + '</td><td>' +
               esc(gio(g.lan_cuoi)) + '</td></tr>';
      }).join("") + '</tbody></table>';
  }

  function veLuot(turns) {
    if (!turns.length) return '<div class="cb-empty">' + esc(window.t("cb.chua_luot")) + '</div>';
    return turns.map(function (t) {
      // Nguồn hiện ra để chủ kiểm được bot lấy câu trả lời TỪ ĐÂU. Không có dòng này thì
      // "bot trả lời đúng chưa" là câu hỏi không kiểm chứng được, chỉ đoán.
      var ng = (t.nguon || []).length
        ? '<div class="cb-src">' + ic("file-text") + " " + esc(t.nguon.join(", ")) + '</div>'
        : '<div class="cb-src cb-warn">' + esc(window.t("cb.khong_tai_lieu")) + '</div>';
      // Lượt GÃY: người hỏi chỉ nhận một câu xin lỗi chung, nên đây là chỗ DUY NHẤT chủ đọc được
      // lý do thật. Thiếu nó thì "bot trả lời sai" và "bot đang hỏng" nhìn giống hệt nhau.
      if (t.loi) {
        return '<div class="cb-turn loi">' +
          '<div class="cb-turn-h">' + esc(t.user_name || t.chat_id) + ' · ' + esc(gio(t.ts)) + '</div>' +
          '<div class="cb-q">' + esc(t.hoi) + '</div>' +
          '<div class="cb-err">' + ic("triangle-alert") + ' ' + esc(window.t("cb.luot_nay_loi")) + ' ' +
          esc(t.loi) + '</div></div>';
      }
      return '<div class="cb-turn' + (t.bi ? " bi" : "") + '">' +
        '<div class="cb-turn-h">' + esc(t.user_name || t.chat_id) + ' · ' + esc(gio(t.ts)) +
        (t.chuyen_nguoi ? ' · <b>' + esc(window.t("cb.da_bao_nguoi_truc")) + '</b>' : "") + '</div>' +
        '<div class="cb-q">' + esc(t.hoi) + '</div>' +
        '<div class="cb-a">' + esc(t.dap) + '</div>' + ng + '</div>';
    }).join("");
  }

  async function bat(b, on) {
    // Bật là lúc bot bắt đầu nói chuyện với người thật. Với bot có quyền thao tác, nhắc lại
    // đúng ở đây - lúc tạo có thể là mấy hôm trước, và tay bấm Bật chưa chắc nhớ mình đã đặt
    // mức nào cho con này.
    var mq = b.muc_quyen || "suggest";
    if (on && mucCua(mq).can_xac_nhan &&
        !confirm(window.t("cb.xn_bat", { ten: b.name, muc: mucCua(mq).nhan }) + "\n\n" +
                 (mq === "full" ? window.t("cb.xn_bat_full") : window.t("cb.xn_bat_auto")))) return;
    try {
      await api("/chatbots/" + encodeURIComponent(b.id) + "/enable",
                { method: "POST", body: fd({ on: on ? "1" : "0" }) });
    } catch (e) {
      alert((on ? window.t("cb.loi_bat") : window.t("cb.loi_tat")) + " " + e.message);
    }
    tai();
  }

  async function xoa(b) {
    // Nói rõ cái gì MẤT và cái gì CÒN. Người dùng không đoán được hậu quả thì đừng bắt họ gánh.
    if (!confirm(window.t("cb.xn_xoa", { ten: b.name }) + "\n\n" +
                 window.t("cb.xn_xoa_giu"))) return;
    try { await api("/chatbots/" + encodeURIComponent(b.id) + "/delete", { method: "POST" }); }
    catch (e) { alert(window.t("cb.loi_xoa") + " " + e.message); }
    tai();
  }

  // ---------------------------------------------------------------- form tạo / sửa
  // Bot KHÔNG có brain riêng để chọn. Nó thuộc về brain đang mở, cùng chỗ với Agent nó dùng và
  // tài liệu nó đọc. Bản trước bắt chọn brain trong form, và chọn xong lại phải nhớ Agent nằm
  // ở brain nào - hai lớp phải khớp nhau mà không có gì bắt chúng khớp. Bỏ hẳn ô đó thì phạm
  // vi của trang chính là câu trả lời, và không còn gì để lệch.
  async function napAgent(br) {
    try {
      // Bản NHẸ: ô chọn chỉ hiện tên + vai trò, không đụng tới system prompt.
      var ad = await api("/agents?brain=" + encodeURIComponent(br || "brain") + "&prompt=0");
      return ad.agents || [];
    } catch (e) { return []; }
  }

  // Vai trò dài thì <option> tràn ngang khỏi hộp và không xuống dòng được (giới hạn của thẻ
  // select gốc). Cắt ngắn là cách duy nhất chắc chắn; tên Agent luôn giữ đủ.
  function optAgent(a, slugDangChon) {
    var vai = String(a.role || "").trim();
    if (vai.length > 34) vai = vai.slice(0, 34).trim() + "…";
    // data-name/data-desc carry the full text for the searchable picker (agent-picker.js), which replaces the
    // native list on screen; the short text above only shows if that script is missing.
    return '<option value="' + esc(a.slug) + '"' + (a.slug === slugDangChon ? " selected" : "") +
           ' data-name="' + esc(a.name || a.slug) + '" data-desc="' + esc(String(a.role || "").trim()) + '"' +
           '>' + esc(a.name) + (vai ? " - " + esc(vai) : "") + '</option>';
  }

  function htmlAgent(ds, slugDangChon) {
    return ds.length ? ds.map(function (a) { return optAgent(a, slugDangChon); }).join("")
                     : '<option value="">' + esc(window.t("cb.khong_agent")) + '</option>';
  }

  // Danh sách ngôn ngữ lấy từ /settings (sổ đăng ký phía server), KHÔNG khai lại ở đây.

  // Khai hai nơi thì thêm ngôn ngữ mới phải nhớ sửa cả hai chỗ.

  var _langDS = [];

  function htmlNgonNgu(cur) {

    var ra = '<option value="auto"' + (cur === "auto" || !cur ? " selected" : "") +

             '>' + esc(window.t("cb.lang_auto")) + '</option>';

    _langDS.forEach(function (l) {

      ra += '<option value="' + esc(l.ma) + '"' + (l.ma === cur ? " selected" : "") +

            '>' + esc(l.ten) + '</option>';

    });

    return ra;

  }


  // ===== Thành phần dùng chung của form và thẻ (0.64.85) =====================================
  // Form đi theo bốn phần: Bot là ai, Bot trả lời ai, Bot dựa vào đâu để trả lời, Bot được làm gì.
  // Mỗi phần một tiêu đề có icon, mỗi lựa chọn ngắn là một nút bấm chọn một thay cho ô xổ xuống kèm
  // đoạn giải thích: chủ thấy mọi phương án cùng lúc thì so sánh được, và đoạn chữ dài thành một dòng.
  function secH(bieuTuong, key) {
    return '<div class="cb-sec-h">' + ic(bieuTuong) + ' <span>' + esc(window.t(key)) + '</span></div>';
  }
  // Adds HTML (the (i) button of the section's folded explanation) at the end of a secH() title row.
  function voiInfo(tieuDe, them) { return tieuDe.replace(/<\/div>$/, (them || infoBtn()) + "</div>"); }

  // Thẻ chọn (radio card) cho "bot trả lời ai": tiêu đề + một dòng mô tả. Ba phương án đứng cạnh
  // nhau vì quyết định này là thứ chủ cần NHÌN THẤY cùng lúc để so sánh.
  function htmlThe(val, cur, tKey, dKey) {
    return '<label class="cb-rc' + (val === cur ? " on" : "") + '" data-v="' + val + '">' +
      '<input type="radio" name="cbAud" value="' + val + '"' + (val === cur ? " checked" : "") + '>' +
      '<span class="cb-rc-dot"></span>' +
      '<span class="cb-rc-t"><b>' + esc(window.t(tKey)) + '</b><small>' + esc(window.t(dKey)) +
      '</small></span></label>';
  }

  // Nút bấm chọn một (segmented) cho 2-3 lựa chọn ngắn. `ds` = [{ v, t }].
  function htmlSeg(id, name, ds, cur) {
    return '<div class="cb-seg" id="' + id + '" role="radiogroup">' + ds.map(function (d) {
      return '<label class="cb-sg' + (d.v === cur ? " on" : "") + '"><input type="radio" name="' + name +
        '" value="' + esc(d.v) + '"' + (d.v === cur ? " checked" : "") + '><span>' + esc(d.t) +
        '</span></label>';
    }).join("") + '</div>';
  }

  // Các mức quyền dựng từ danh sách SERVER cấp (nhãn Chỉ đọc / Được ghi / Toàn quyền), không chép
  // cứng ở đây. Ba nút bấm thay cho ô xổ xuống: mức quyền là quyết định nặng nhất của form nên cả ba
  // phải nằm phơi ra, không giấu sau một cú bấm.
  function htmlMuc(dangChon) {
    var ds = _mucDS.length ? _mucDS : [{ id: "suggest", nhan: window.t("cb.muc_chi_doc") }];
    return htmlSeg("cbMuc", "cbMuc", ds.map(function (m) { return { v: m.id, t: m.nhan }; }), dangChon);
  }

  // Khối cảnh báo dựng từ danh sách câu SERVER trả về. Mức chỉ đọc không có câu nào, và đúng như vậy:
  // nó không lấy đi thứ gì để mà cảnh báo. Nới quyền thì hiện HAI câu đầu (mất gì, ai điều khiển) và
  // gấp phần còn lại sau "Xem đủ rủi ro": cảnh báo phải chặn mắt lại nhưng không được chiếm cả màn
  // hình, và ô đồng ý nằm ngay trong khối để tick không tách rời khỏi thứ được đồng ý.
  function veCanhBao(id) {
    var m = mucCua(id);
    if (!(m.canh_bao || []).length) {
      // What this level allows: the level name stays, the description opens from (i) (0.214.0).
      return '<div class="cb-hint">' + esc(m.nhan) + infoBtn() + '</div>' +
        infoBody(esc(window.t(id === "read_docs" ? "cb2.mq_read_docs" : "cb2.mq_doc")));
    }
    var HIEN = 2;
    return '<div class="cb-canhbao ' + (id === "full" ? "full" : "ghi") + '">' +
      '<div class="cb-canhbao-h">' + ic("triangle-alert") + ' ' + esc(window.t("cb.canhbao_h1")) +
      ' <b>' + esc(m.nhan) + '</b> ' + esc(window.t("cb.canhbao_h2")) + '</div><ul>' +
      m.canh_bao.map(function (s, i) {
        return '<li' + (i >= HIEN ? ' class="cb-more" hidden' : "") + '>' + esc(s) + '</li>';
      }).join("") + '</ul>' +
      (m.canh_bao.length > HIEN
        ? '<button type="button" class="cb-xem-du">' + esc(window.t("cb2.xem_du")) + '</button>' : "") +
      '<label class="cb-ack"><input type="checkbox" id="cbAck"> ' + esc(window.t("cb.ack")) + '</label></div>';
  }

  // Một dòng "bot trả lời ai" cho thẻ: đọc là biết ngay bot đang nói chuyện với ai, không phải mở form.
  function tomTatDoiTuong(b) {
    var s = tomTatAi(b), g = b.gio_truc || {}, nl = (b.ngoai_le || []).length;
    if (g.tu && g.den) s += " · " + window.t("cb.tt_gio_truc", { tu: g.tu, den: g.den });
    // Per-chat exceptions (0.172.0) on the card: a chat running at another level must never be invisible.
    return nl ? s + " · " + window.t("cb.tt_ngoai_le", { n: nl }) : s;
  }

  function tomTatAi(b) {
    var aud = b.audience || "nhom";
    var nhom = (b.groups || []).length, nguoi = (b.people || []).length;
    var cn = coNhom(b);
    var s;
    if (aud === "all" && cn && b.reply_when === "auto") return window.t("cb2.tt_auto");
    if (aud === "all") s = window.t("cb2.tt_all");
    else if (aud === "chon") {
      s = cn ? window.t("cb2.tt_chon", { nguoi: nguoi, nhom: nhom })
             : window.t("cb2.tt_chon_ko_nhom", { nguoi: nguoi });
    } else {
      s = !cn ? window.t("cb2.tt_moi_nguoi")
              : (nhom ? window.t("cb2.tt_nhom", { nhom: nhom }) : window.t("cb2.tt_rieng"));
    }
    // Chế độ lên tiếng chỉ có nghĩa khi bot thật sự có nhóm để lên tiếng.
    if (cn && (aud === "all" || nhom)) {
      s += " · " + (b.reply_when === "always" ? window.t("cb.tl_moi_tin")
                    : b.reply_when === "auto" ? window.t("cb.tl_tu_danh_gia") : window.t("cb.tl_goi_ten"));
    }
    return s;
  }

  function gioNgan(ts) {
    if (!ts) return "";
    try {
      var d = new Date(ts * 1000), n = new Date();
      return d.toDateString() === n.toDateString()
        ? d.toLocaleTimeString(LOC(), { hour: "2-digit", minute: "2-digit" })
        : d.toLocaleDateString(LOC(), { day: "2-digit", month: "2-digit" });
    } catch (e) { return ""; }
  }

  // Danh sách tài khoản kênh để TÍCH CHỌN: tài khoản bot này đang trực (khi sửa) + tài khoản
  // chưa bot nào trực. Tài khoản đang do bot khác trực không hiện: mỗi token một poller.
  // `chinhXac`: khi vẽ LẠI giữa chừng (vừa nối thêm một kênh), `chonSan` là toàn bộ sự thật về
  // những gì đang được tích. Không có cờ này thì `b.accounts` luôn được tích lại, nên một tài
  // khoản vừa bị bỏ tích sẽ lặng lẽ quay về.
  function veChonTK(b, chonSan, chinhXac) {
    var ds = [];
    var da = {};
    ((b && b.accounts) || []).forEach(function (a) { ds.push(a); da[a.id] = true; });
    _tkRanh.forEach(function (a) { if (!da[a.id]) ds.push(a); });
    // Kênh đang do bot KHÁC trực: hiện mờ, không tick được, ghi rõ bot nào (và brain nào nếu khác brain đang mở).
    var khoa = _tkBan.filter(function (a) { return !da[a.id]; }).map(function (a) {
      var k = kenhCua(a.channel);
      var tb = window.JavisConversations && window.JavisConversations.tenBrain;
      var khac = a.bot_brain && a.bot_brain !== brain();
      return '<div class="cb-tk cb-tk-khoa" aria-disabled="true">' +
        '<span class="cb-tk-logo">' + logoKenh(a.channel, "18px") + '</span>' +
        '<span class="cb-tk-text"><b>' + esc(a.label || k.nhan) + '</b><small>' + esc(k.nhan) +
        (a.external_id ? ' · ' + esc((k.tien_to_ten || "") + a.external_id) : "") + '</small>' +
        '<small class="cb-tk-luu-y">' + ic("lock") + ' ' + esc(window.t("cb.tk_khoa", { bot: a.bot_name || "?" })) +
        (khac ? ' ' + esc(window.t("cb.tk_khoa_brain", { brain: tb ? tb(a.bot_brain) : a.bot_brain })) : "") + '</small>' +
        '</span></div>';
    }).join("");
    var khoaBox = khoa ? '<div class="cb-tk-list cb-tk-list-khoa">' + khoa + '</div>' : "";
    if (!ds.length) return '<div class="cb-trong-tk">' + esc(window.t("cb.tk_chua_co")) + '</div>' + khoaBox;
    var chon = {};
    if (!chinhXac) ((b && b.accounts) || []).forEach(function (a) { chon[a.id] = true; });
    (chonSan || []).forEach(function (id) { chon[id] = true; });
    return '<div class="cb-tk-list">' + ds.map(function (a) {
      var k = kenhCua(a.channel);
      var ten = a.label || k.nhan;
      return '<label class="cb-tk"><input type="checkbox" class="cb-tk-o" value="' + esc(a.id) + '"' +
        (chon[a.id] ? " checked" : "") + ' data-k="' + esc(a.channel) + '" data-ten="' + esc(ten) + '">' +
        '<span class="cb-tk-logo">' + logoKenh(a.channel, "18px") + '</span>' +
        '<span class="cb-tk-text"><b>' + esc(ten) + '</b><small>' + esc(k.nhan) +
        (a.external_id ? ' · ' + esc((k.tien_to_ten || "") + a.external_id) : "") + '</small>' +
        // Kênh kiểu "account" (Zalo cá nhân) là nick của CHÍNH chủ: bot trả lời dưới tên chủ nên
        // nói thẳng ngay lúc chọn. Đọc theo `kind` do server khai, không đoán theo id kênh.
        (k.kind === "account" ? '<small class="cb-tk-luu-y">' + esc(window.t("cb.tk_ca_nhan_luu_y")) + '</small>' : "") +
        '</span></label>';
    }).join("") + '</div>' + khoaBox;
  }

  // Mở modal "Thêm tài khoản" của tab Tài khoản bot (chatbots.js KHÔNG tự dựng lại form dán token: xem
  // chú thích ở `moThemTK` trong conversations.js). Xong thì nạp lại danh sách tài khoản rảnh
  // và tích sẵn con vừa nối - đường đi tự nhiên là nối kênh xong dùng luôn, không phải tự tìm
  // lại nó trong danh sách.
  function noiKenhMoi(xong) {
    var fn = window.JavisConversations && window.JavisConversations.themTaiKhoan;
    if (!fn) return alert(window.t("cb.chua_mo_duoc_kenh"));
    fn({ onXong: async function (tk) {
      try {
        var d = await api("/chatbots?brain=" + encodeURIComponent(brain()));
        _kenhDS = d.kenh || _kenhDS;
        _tkRanh = d.tai_khoan || [];
        _tkBan = d.tai_khoan_ban || _tkBan;
      } catch (e) {}
      // Ghép tay tài khoản vừa nối vào danh sách nếu lần nạp lại chưa thấy nó (mạng hỏng, hoặc
      // server trả về trước khi kho kịp thấy bản ghi mới). Không có bước này thì id vừa tích
      // rơi lặng lẽ: người dùng nối xong một kênh mà nó không hiện ra ở đâu cả.
      if (tk && tk.id && !_tkRanh.some(function (a) { return a.id === tk.id; })) _tkRanh.push(tk);
      xong(tk && tk.id ? tk.id : "");
    } });
  }

  // `truoc` (tuỳ chọn): { account_id } - tài khoản tích sẵn khi mở từ mục "Kênh chưa có bot" ("Tạo bot cho kênh này");
  // { buoc: 1 } - mở thẳng ở bước chọn kênh (chip "Thêm kênh" trên thẻ bot).
  //
  // Form tạo bot đi theo HAI BƯỚC, và đó là cả điểm của nó. Bước 1 hỏi đúng một câu - bot trả lời ở
  // đâu - bước 2 mới là cài đặt. Sửa bot thì vào thẳng bước 2: tài khoản đã chọn rồi.
  //
  // Bước 2 (0.64.85) là MỘT cuộn với bốn phần, mỗi phần một quyết định:
  //   1. Bot là ai            - tên và Agent.
  //   2. Bot trả lời ai       - phần quan trọng nhất: mọi cuộc chat / nhắn riêng thoải mái, nhóm thì
  //                             chọn / chỉ người và nhóm đã chọn, kèm ô chọn lấy từ Hộp thư.
  //   3. Bot dựa vào đâu      - Agent và tài liệu / chỉ tài liệu.
  //   4. Bot được làm gì      - ba mức quyền, cảnh báo chỉ hiện khi nâng.
  // Ngôn ngữ trả lời (hiếm khi đổi) gấp vào "Nâng cao". Trước đây nhóm nằm trong khối gấp dưới dạng ô
  // dán id, và không có cách chọn người: xem docs/superpowers/specs/2026-09-30-form-bot-va-doi-tuong-tra-loi-design.md.
  async function moForm(b, truoc) {
    var sua = !!b;
    var br = brain();                 // brain đang mở = brain của bot, không hỏi lại
    var agents = await napAgent(br);
    var chonSan = (truoc && truoc.account_id) ? [truoc.account_id] : [];
    var buoc = (truoc && truoc.buoc) || (sua ? 2 : 1);
    var aud0 = (b && b.audience) || "nhom";
    var muc0 = (b && b.muc_quyen) || "suggest";
    var rw0 = (b && (b.reply_when === "auto" || b.reply_when === "always")) ? b.reply_when : "mention";
    // "Tự động hóa tất cả" không phải một giá trị lưu riêng: nó là "mọi cuộc chat" cộng "tự đánh giá" gộp làm MỘT cú chọn
    // (lưu xuống vẫn là audience=all, reply_when=auto), nên bot đã cài như vậy từ trước tự hiện đúng thẻ này.
    var card0 = (aud0 === "all" && rw0 === "auto") ? "auto" : aud0;
    var RP = window.JavisReplyPolicy;      // bộ phán xử hội thoại nhóm (0.65.0), file chatbots-reply-policy.js
    // Người/nhóm ĐANG được chọn (sự thật của form). Danh sách cuộc chat từ server chỉ là nguồn để
    // chọn; tick hay bỏ tick sửa ở đây, và lúc Lưu mới đổ ra hai danh sách groups/people.
    var chon = { group: {}, private: {} };
    ((b && b.groups) || []).forEach(function (x) { chon.group[x] = true; });
    ((b && b.people) || []).forEach(function (x) { chon.private[x] = true; });
    var pkTab = "group", chats = [], pkQ = "", pkSeq = 0, pkHen = null;

    var box = el(
      '<div class="cb-modal"><div class="cb-form cb-wizard">' +
        '<div class="cb-form-h">' +
          '<h3>' + esc(sua ? window.t("cb.sua_bot") : window.t("cb.bot_moi")) + '</h3>' +
          (sua ? "" : '<span class="cb-buoc" id="cbBuoc"></span>') +
        '</div>' +

        // ---------------------------------------------------------------- BƯỚC 1: trả lời ở đâu
        '<div class="cb-b" id="cbB1">' +
          // for= points at the account list (not a form control), so the (i) inside never becomes the label's control.
          '<label for="cbTkBox">' + esc(window.t("cb.lb_tai_khoan")) + infoBtn() + '</label>' +
          '<div id="cbTkBox">' + veChonTK(b, chonSan) + '</div>' +
          infoBody(esc(window.t("cb.hint_tai_khoan"))) +
          '<button class="s-btn-ghost cb-noi-kenh" type="button">' + ic("plus") + ' ' +
            esc(window.t("cb.noi_kenh_moi")) + '</button>' +
        '</div>' +

        // ---------------------------------------------------------------- BƯỚC 2: cài đặt bot
        '<div class="cb-b" id="cbB2">' +
          '<div class="cb-tom" id="cbTom"></div>' +

          // 1. Bot là ai
          '<div class="cb-sec cb-sec0">' + secH("bot", "cb2.s_ai") +
            '<input id="cbName" value="' + esc(b ? b.name : "") + '" placeholder="' +
              esc(window.t("cb.ph_ten")) + '">' +
            '<div class="cb-row cb-row-ag">' +
              '<select id="cbAgent">' + htmlAgent(agents, (b && (b.agent || {}).slug) || "") + '</select>' +
              '<button class="s-btn-ghost" id="cbNewAgent" type="button">' + ic("plus") + ' ' +
                esc(window.t("cb.tao_agent")) + '</button>' +
            '</div>' +
            '<div class="cb-hint">' + esc(window.t("cb2.s_ai_hint", { brain: br })) + '</div>' +
          '</div>' +

          // 2. Bot trả lời ai
          '<div class="cb-sec">' + secH("users", "cb2.s_doituong") +
            // Why there are no group options (filled by apDoiTuong). Stays open: owners took a missing option for a bug (0.102.1).
            '<div class="cb-hint" id="cbKoNhom" hidden></div>' +
            '<div class="cb-rcs" id="cbRcs">' +
              htmlThe("auto", card0, "cb2.aud_auto_t", "cb2.aud_auto_d") +
              htmlThe("all", card0, "cb2.aud_all_t", "cb2.aud_all_d") +
              htmlThe("nhom", card0, "cb2.aud_nhom_t", "cb2.aud_nhom_d") +
              htmlThe("chon", card0, "cb2.aud_chon_t", "cb2.aud_chon_d") +
            '</div>' +
            '<label class="cb-ack cb-ack-aud" id="cbAckAudBox" style="display:none"><input type="checkbox" id="cbAckAud"> ' +
              '<span id="cbAckAudT">' + esc(window.t("cb2.aud_all_ack")) + '</span></label>' +
            '<div class="cb-pk" id="cbPk" style="display:none">' +
              '<div class="cb-pk-h">' +
                '<div class="cb-pk-tabs">' +
                  '<button type="button" class="cb-pk-tab" data-t="group"></button>' +
                  '<button type="button" class="cb-pk-tab" data-t="private"></button>' +
                '</div>' +
                '<input id="cbPkQ" class="cb-pk-q" placeholder="' + esc(window.t("cb2.pk_tim")) + '">' +
              '</div>' +
              '<div class="cb-pk-body" id="cbPkBody"></div>' +
              '<div class="cb-pk-add">' +
                '<input id="cbPkId" placeholder="' + esc(window.t("cb2.pk_them_id")) + '">' +
                '<button type="button" class="s-btn-ghost" id="cbPkAdd">' + esc(window.t("cb2.pk_them")) + '</button>' +
              '</div>' +
              '<div class="cb-hint cb-pk-hint" id="cbPkHint"></div>' +
            '</div>' +
            '<div id="cbRwBox" style="display:none">' +
              '<div id="cbRwSeg">' +
                '<div class="cb-sub">' + esc(window.t("cb2.rw_lb")) + infoBtn() + '</div>' +
                htmlSeg("cbRw", "cbRw", [
                  { v: "mention", t: window.t("cb2.rw_mention") },
                  { v: "auto", t: window.t("cb2.rw_auto") },
                  { v: "always", t: window.t("cb2.rw_always") }], rw0) +
                // What the picked mode does (filled by veRw), behind the (i) of the label above.
                '<div class="info-body" id="cbRwH" hidden></div>' +
              '</div>' +
              // A required fix (privacy off in BotFather), shown only when it applies: stays open (review 0.214.0).
              '<div class="cb-hint cb-chi-tg" id="cbRwTg">' + ic("triangle-alert") + ' <b>Telegram</b>: ' +
                esc(window.t("cb2.rw_tg")) + '</div>' +
              // Chỉ hiện khi chọn "Tự đánh giá": một dòng giải thích, không ô cài đặt nào (bộ phán xử tự vận hành).
              (RP ? RP.formHtml() : '') +
            '</div>' +
          '</div>' +

          // 0.352.0 (owner): no "what does the bot answer from" choice any more. Every bot answers from its Agent
          // and the brain's documents; the old "documents only" mode is no longer offered.

          // 4. Bot được làm gì. Mức quyền KHÔNG bao giờ nằm trong khối gấp: đây là quyết định nặng
          // nhất trong cả form, phải đọc trước khi bấm tạo chứ không phải một ô phải bấm mới thấy.
          '<div class="cb-sec">' + secH("shield", "cb2.s_quyen") +
            htmlMuc(muc0) +
            '<div class="cb-muc-note">' + veCanhBao(muc0) + '</div>' +
          '</div>' +

          // 5. Active hours (0.130.0). Both empty = all day. Outside them the bot stays silent and the message
          // still lands in the inbox; an end earlier than the start runs past midnight (08:00 to 02:00).
          '<div class="cb-sec">' + voiInfo(secH("alarm-clock", "cb.s_gio_truc")) +
            '<div class="cb-gio-truc">' +
              '<label>' + esc(window.t("cb.gio_tu")) +
                ' <input type="time" id="cbGioTu" value="' + esc(((b && b.gio_truc) || {}).tu || "") + '"></label>' +
              '<label>' + esc(window.t("cb.gio_den")) +
                ' <input type="time" id="cbGioDen" value="' + esc(((b && b.gio_truc) || {}).den || "") + '"></label>' +
            '</div>' +
            infoBody(esc(window.t("cb.hint_gio_truc"))) +
            // Owner yield (0.172.0, personal Zalo only): minutes the bot stays out of a chat after the owner types into it
            // by hand; 0 = never. Left blank = not set: the channel default (10 minutes, groups silent as before), shown
            // as a placeholder so saving the form does not turn an unset bot into an explicit 10.
            '<div class="cb-gio-truc">' +
              '<label for="cbNhuongTay">' + esc(window.t("cb.nhuong_tay")) + infoBtn() +
                ' <input type="number" id="cbNhuongTay" min="0" max="240" step="1" style="width:8em" placeholder="' + esc(window.t("cb.ph_nhuong_tay")) + '" value="' +
                esc(b && b.nhuong_tay_phut != null ? String(b.nhuong_tay_phut) : "") + '"></label>' +
            '</div>' +
            infoBody(esc(window.t("cb.hint_nhuong_tay"))) +
            // Friend-request intake (0.172.0): accept requests and hand their introduction to the bot. Shown only
            // while a personal Zalo account is ticked (`apDoiTuong`): no other channel has friend requests.
            '<div id="cbKbBox" style="display:none">' +
              '<label class="cb-gio-truc" for="cbNhanKetBan"><input type="checkbox" id="cbNhanKetBan"' +
                (b && b.nhan_ket_ban ? " checked" : "") + '> ' + esc(window.t("cb.nhan_ket_ban")) + infoBtn() + '</label>' +
              infoBody(esc(window.t("cb.hint_nhan_ket_ban"))) +
            '</div>' +
            // Never answer chats carrying these Zalo labels (0.281.0, personal Zalo only): the labels the owner set in the
            // Zalo app (Family, Friends...) are listed from the ticked accounts; one not listed can be typed below.
            '<div id="cbTagBox" style="display:none">' +
              '<label for="cbTagMore">' + esc(window.t("cb.skip_tags")) + infoBtn() + '</label>' +
              infoBody(esc(window.t("cb.hint_skip_tags"))) +
              '<div class="cb-tag-list" id="cbTagList"></div>' +
              '<input id="cbTagMore" placeholder="' + esc(window.t("cb.ph_skip_tags")) + '">' +
            '</div>' +
          '</div>' +

          // 6. Per-chat exceptions (0.172.0): one private chat (e.g. a family member on a personal Zalo nick) gets its
          // own level and wait, without raising the bot that also answers strangers.
          // Picked from the chats the inbox knows on the ticked accounts, never typed: each exception carries the
          // channel account it lives on, so the same id on another account or channel never matches.
          '<div class="cb-sec">' + voiInfo(secH("user", "cb.s_ngoai_le")) +
            '<div class="cb-pk">' +
              '<div class="cb-pk-body" id="cbNlList"></div>' +
              '<div class="cb-pk-add">' +
                '<input id="cbNlQ" class="cb-pk-q" placeholder="' + esc(window.t("cb2.pk_tim")) + '">' +
                '<select id="cbNlPick"></select>' +
                '<button type="button" class="s-btn-ghost" id="cbNlAdd">' + esc(window.t("cb2.pk_them")) + '</button>' +
              '</div>' +
            '</div>' +
            infoBody(esc(window.t("cb.hint_ngoai_le"))) +
          '</div>' +

          // Nâng cao: chỉ ngôn ngữ trả lời. Ngôn ngữ của bot ĐỘC LẬP với ngôn ngữ của chủ: bot nói
          // chuyện với NGƯỜI NGOÀI, và chủ dùng Javis bằng tiếng Việt mà người nhắn tới nói tiếng khác
          // là chuyện bình thường, nên suy ngôn ngữ của bot từ ngôn ngữ của chủ là suy sai.
          '<details class="cb-nangcao">' +
            '<summary>' + ic("settings") + ' ' + esc(window.t("cb.nang_cao")) + '</summary>' +
            '<label for="cbNgonNgu">' + esc(window.t("cb.lb_ngon_ngu")) + infoBtn() + '</label>' +
            '<select id="cbNgonNgu">' + htmlNgonNgu((b && b.ngon_ngu) || "auto") + '</select>' +
            infoBody(esc(window.t("cb.hint_ngon_ngu"))) +
          '</details>' +
        '</div>' +

        '<div class="cb-form-acts">' +
          '<button class="s-btn-ghost" id="cbLui" type="button"></button>' +
          '<button class="s-btn" id="cbTien" type="button"></button>' +
        '</div>' +
        (sua ? "" : '<div class="cb-hint" id="cbTaoXong">' + esc(window.t("cb.tao_xong_1")) + ' <b>' +
                    esc(window.t("cb.tao_xong_tat")) + '</b>' +
                    esc(window.t("cb.tao_xong_2")) + '</div>') +
      '</div></div>');

    document.body.appendChild(box);
    var dong = function () { if (box.parentNode) box.parentNode.removeChild(box); };
    box.onmousedown = function (e) { if (e.target === box) dong(); };

    // Searchable agent picker instead of the native list of "name - truncated role" lines (owner, 25/10/2026).
    if (window.JavisAgentPicker) {
      window.JavisAgentPicker.enhance(box.querySelector("#cbAgent"), { title: window.t("ap.title") });
    }

    // Sang thẳng trang Cộng sự. Đóng form trước để quay lại không bị hai lớp modal chồng nhau.
    box.querySelector("#cbNewAgent").onclick = function () {
      dong();
      try { window.JavisNav.go("workspace"); } catch (e) {}
    };

    function giaTri(ten) {
      var n = box.querySelector('input[name="' + ten + '"]:checked');
      return n ? n.value : "";
    }
    // Nút chọn một tô sáng theo lựa chọn hiện tại (không dùng :has để chạy được trên trình duyệt cũ).
    function dongBo(ten) {
      box.querySelectorAll('input[name="' + ten + '"]').forEach(function (i) {
        i.parentNode.classList.toggle("on", i.checked);
      });
    }

    // ---- Mức quyền: đổi mức là vẽ lại cảnh báo NGAY, và ô đồng ý luôn bắt đầu ở trạng thái chưa
    // tick. Giữ lại tick cũ khi đổi từ "Được ghi" sang "Toàn quyền" là để chủ đồng ý với một danh
    // sách rủi ro mà họ chưa đọc.
    var oNote = box.querySelector(".cb-muc-note");
    function noiCanhBao() {
      var nut = oNote.querySelector(".cb-xem-du");
      if (nut) nut.onclick = function () {
        oNote.querySelectorAll(".cb-more").forEach(function (li) { li.hidden = false; });
        nut.style.display = "none";
      };
    }
    box.querySelectorAll('input[name="cbMuc"]').forEach(function (i) {
      i.onchange = function () { dongBo("cbMuc"); oNote.innerHTML = veCanhBao(giaTri("cbMuc")); noiCanhBao(); };
    });
    noiCanhBao();

    // ---- Tài khoản đang tích
    function tkDangChon() {
      return Array.prototype.slice.call(box.querySelectorAll(".cb-tk-o:checked")).map(function (n) {
        return { id: n.value, channel: n.dataset.k, ten: n.dataset.ten || "" };
      });
    }
    // Khối nhóm chỉ hiện khi CÓ tài khoản đứng được trong nhóm. Hiện ra rồi để nó không có tác dụng là
    // hứa suông: người dùng ngồi chọn nhóm xong chờ mãi một con bot không bao giờ vào được nhóm nào.
    function coNhomForm() {
      return tkDangChon().some(function (a) { return kenhCua(a.channel).co_nhom; });
    }
    // Friend-request intake only exists on a personal Zalo account.
    function coZaloCaNhan() {
      return tkDangChon().some(function (a) { return a.channel === "zalo_personal"; });
    }

    // ---- Zalo labels the bot stays out of (0.281.0). `tagChon` is the truth of the form (name -> ticked); the list from
    // the server only offers names to tick, and a saved name the account no longer has stays shown so it can be unticked.
    var tagChon = {}, tagDs = [], tagCo = true, tagKhoa = "";
    ((b && b.skip_labels) || []).forEach(function (x) { tagChon[x] = true; });
    function veTag() {
      var el = box.querySelector("#cbTagList");
      var ten = tagDs.slice();
      Object.keys(tagChon).forEach(function (x) { if (ten.indexOf(x) < 0) ten.push(x); });
      if (!ten.length) {
        el.innerHTML = '<div class="cb-pk-rong">' + esc(window.t(tagCo ? "cb.skip_tags_none" : "cb.skip_tags_old")) + '</div>';
        return;
      }
      el.innerHTML = ten.map(function (x) {
        return '<label class="cb-pk-li"><input type="checkbox" data-tag="' + esc(x) + '"' + (tagChon[x] ? " checked" : "") +
          '><span class="cb-pk-n">' + esc(x) + '</span></label>';
      }).join("");
      el.querySelectorAll("input[type=checkbox]").forEach(function (i) {
        i.onchange = function () { tagChon[i.dataset.tag] = i.checked; };
      });
    }
    async function taiTag() {
      var ids = tkDangChon().map(function (a) { return a.id; }).join(",");
      if (ids === tagKhoa) return;      // same accounts: the list is already there
      tagKhoa = ids;
      try {
        var d = await api("/chatbots/zalo-labels?account_ids=" + encodeURIComponent(ids) +
          (sua ? "&bot_id=" + encodeURIComponent(b.id) : ""));
        if (ids !== tagKhoa) return;
        tagDs = d.labels || [];
        tagCo = d.supported !== false;
      } catch (e) { tagDs = []; tagCo = false; }
      veTag();
    }
    function tagLuu() {
      var ds = Object.keys(tagChon).filter(function (x) { return tagChon[x]; });
      ((box.querySelector("#cbTagMore") || {}).value || "").split(",").forEach(function (x) {
        x = x.trim();
        if (x && ds.indexOf(x) < 0) ds.push(x);
      });
      return JSON.stringify(ds);
    }

    // ---- Ô chọn người và nhóm (lấy từ Hộp thư)
    function demChon(loai) {
      return Object.keys(chon[loai]).filter(function (k) { return chon[loai][k]; }).length;
    }
    function veTabPk() {
      box.querySelectorAll(".cb-pk-tab").forEach(function (t) {
        var loai = t.dataset.t;
        t.textContent = window.t(loai === "group" ? "cb2.pk_nhom" : "cb2.pk_nguoi") + " " + demChon(loai);
        t.classList.toggle("on", loai === pkTab);
      });
    }
    function vePk() {
      var body = box.querySelector("#cbPkBody");
      var ds = chats.filter(function (c) { return c.loai === pkTab; });
      // Id vừa thêm bằng tay mà Hộp thư chưa biết vẫn phải hiện ra để bỏ tick được.
      Object.keys(chon[pkTab]).forEach(function (id) {
        if (chon[pkTab][id] && !ds.some(function (x) { return x.id === id; })) {
          ds.push({ id: id, ten: id, loai: pkTab, luc: 0, cho: false });
        }
      });
      veTabPk();
      if (!ds.length) {
        body.innerHTML = '<div class="cb-pk-rong">' + esc(window.t("cb2.pk_rong")) + '</div>';
        return;
      }
      body.innerHTML = ds.map(function (c) {
        return '<label class="cb-pk-li"><input type="checkbox" data-id="' + esc(c.id) + '"' +
          (chon[pkTab][c.id] ? " checked" : "") + '><span class="cb-pk-n">' + esc(c.ten || c.id) + '</span>' +
          (c.cho ? '<span class="cb-bd">' + esc(window.t("cb2.pk_cho")) + '</span>'
                 : '<small>' + esc(gioNgan(c.luc)) + '</small>') + '</label>';
      }).join("");
      body.querySelectorAll("input[type=checkbox]").forEach(function (i) {
        i.onchange = function () { chon[pkTab][i.dataset.id] = i.checked; veTabPk(); };
      });
    }
    async function taiChats() {
      var ids = tkDangChon().map(function (a) { return a.id; }).join(",");
      if (!ids && !sua) { chats = []; vePk(); return; }
      var lan = ++pkSeq;
      box.querySelector("#cbPkBody").innerHTML = '<div class="cb-pk-rong">' + esc(window.t("cb2.pk_dang_tai")) + '</div>';
      try {
        var d = await api("/chatbots/chats?account_ids=" + encodeURIComponent(ids) +
          (sua ? "&bot_id=" + encodeURIComponent(b.id) : "") +
          "&q=" + encodeURIComponent(pkQ) + "&limit=80");
        if (lan !== pkSeq) return;       // có lần tải mới hơn rồi
        chats = d.chats || [];
      } catch (e) { if (lan !== pkSeq) return; chats = []; }
      vePk();
    }
    box.querySelectorAll(".cb-pk-tab").forEach(function (t) {
      t.onclick = function () { pkTab = t.dataset.t; vePk(); apGoiY(); };
    });
    box.querySelector("#cbPkQ").oninput = function () {
      pkQ = this.value.trim();
      clearTimeout(pkHen);
      pkHen = setTimeout(taiChats, 250);
    };
    box.querySelector("#cbPkAdd").onclick = function () {
      var o = box.querySelector("#cbPkId");
      var id = o.value.trim();
      if (!id) return;
      chon[pkTab][id] = true;
      o.value = "";
      vePk();
    };

    // ---- Per-chat exceptions (0.172.0): rows {account_id, chat_id, ten, muc_quyen, cho_giay}
    var nlDs = ((b && b.ngoai_le) || []).map(function (e) { return Object.assign({}, e); });
    var nlChats = [], nlQ = "", nlSeq = 0, nlHen = null;
    function nlKhoa(e) { return e.account_id + "\n" + e.chat_id; }
    function nlTenTk(aid) {
      var a = tkDangChon().filter(function (x) { return x.id === aid; })[0];
      return a ? (a.ten || a.id) : aid;
    }
    function veNl() {
      var list = box.querySelector("#cbNlList");
      var muc = _mucDS.length ? _mucDS : [{ id: "suggest", nhan: window.t("cb.muc_chi_doc") }];
      list.innerHTML = nlDs.length ? nlDs.map(function (e, i) {
        return '<div class="cb-pk-li" data-i="' + i + '"><span class="cb-pk-n">' + esc(e.ten || e.chat_id) +
          ' <small>' + esc(nlTenTk(e.account_id)) + '</small></span>' +
          '<select class="cb-nl-muc">' + muc.map(function (m) {
            return '<option value="' + esc(m.id) + '"' + (m.id === e.muc_quyen ? " selected" : "") + '>' + esc(m.nhan) + '</option>';
          }).join("") + '</select>' +
          '<input class="cb-nl-cho" type="number" min="0" max="60" style="width:70px" placeholder="' +
            esc(window.t("cb.ph_nl_cho")) + '" value="' + (e.cho_giay == null ? "" : esc(String(e.cho_giay))) + '">' +
          '<button type="button" class="s-btn-ghost cb-nl-xoa">' + esc(window.t("cb.nl_bo")) + '</button></div>';
      }).join("") : '<div class="cb-pk-rong">' + esc(window.t("cb.nl_rong")) + '</div>';
      list.querySelectorAll(".cb-pk-li").forEach(function (r) {
        var e = nlDs[+r.dataset.i];
        r.querySelector(".cb-nl-muc").onchange = function () { e.muc_quyen = this.value; };
        r.querySelector(".cb-nl-cho").oninput = function () {
          var v = this.value.trim();
          e.cho_giay = v === "" ? null : +v;
        };
        r.querySelector(".cb-nl-xoa").onclick = function () { nlDs.splice(+r.dataset.i, 1); veNl(); veNlPick(); };
      });
    }
    function veNlPick() {
      var co = {};
      nlDs.forEach(function (e) { co[nlKhoa(e)] = true; });
      var ds = nlChats.filter(function (c) { return !co[nlKhoa({ account_id: c.tk, chat_id: c.id })]; });
      box.querySelector("#cbNlPick").innerHTML = ds.length ? ds.map(function (c) {
        return '<option value="' + esc(c.tk + "\n" + c.id) + '">' + esc((c.ten || c.id) + " · " + nlTenTk(c.tk)) + '</option>';
      }).join("") : '<option value="">' + esc(window.t("cb2.pk_rong")) + '</option>';
    }
    async function taiNl() {
      var ids = tkDangChon().map(function (a) { return a.id; }).join(",");
      var lan = ++nlSeq;
      if (!ids) { nlChats = []; veNlPick(); return; }
      try {
        var d = await api("/chatbots/chats?account_ids=" + encodeURIComponent(ids) +
          "&q=" + encodeURIComponent(nlQ) + "&limit=80");
        if (lan !== nlSeq) return;
        // Private chats only, and only rows the inbox ties to an account: an exception without one never matches.
        nlChats = (d.chats || []).filter(function (c) { return c.loai === "private" && c.tk; });
      } catch (e) { if (lan !== nlSeq) return; nlChats = []; }
      veNlPick();
    }
    box.querySelector("#cbNlQ").oninput = function () {
      nlQ = this.value.trim();
      clearTimeout(nlHen);
      nlHen = setTimeout(taiNl, 250);
    };
    box.querySelector("#cbNlAdd").onclick = function () {
      var v = box.querySelector("#cbNlPick").value;
      if (!v) return;
      var p = v.split("\n");
      var c = nlChats.filter(function (x) { return x.tk === p[0] && x.id === p[1]; })[0] || {};
      // A new row starts at the bot's own level: the owner raises or lowers it on purpose.
      nlDs.push({ account_id: p[0], chat_id: p[1], ten: c.ten && c.ten !== p[1] ? c.ten : "",
                  muc_quyen: (b && b.muc_quyen) || "suggest", cho_giay: null });
      veNl();
      veNlPick();
    };
    veNl();

    // ---- Chế độ lên tiếng trong nhóm
    var RW_H = { mention: "cb2.rw_mention_h", auto: "cb2.rw_auto_h", always: "cb2.rw_always_h" };
    function veRw() {
      var card = giaTri("cbAud") || card0;
      var tuDong = card === "auto";
      // Thẻ "mọi cuộc chat" chỉ còn Được gọi tên / Mọi tin: "Tự đánh giá" cho mọi cuộc chat CHÍNH là thẻ Tự động hóa tất cả.
      var nutAuto = box.querySelector('input[name="cbRw"][value="auto"]');
      if (nutAuto) nutAuto.parentNode.style.display = card === "all" ? "none" : "";
      if (card === "all" && giaTri("cbRw") === "auto") box.querySelector('input[name="cbRw"][value="mention"]').checked = true;
      dongBo("cbRw");
      // Thẻ Tự động hóa tất cả đã quyết chế độ lên tiếng: ẩn nút chọn, không để hai chỗ nói hai điều khác nhau.
      box.querySelector("#cbRwSeg").style.display = tuDong ? "none" : "";
      var v = tuDong ? "auto" : (giaTri("cbRw") || "mention");
      box.querySelector("#cbRwH").textContent = window.t(RW_H[v]);
      var coTg = tkDangChon().some(function (a) { return a.channel === "telegram"; });
      box.querySelector("#cbRwTg").style.display = coTg && v !== "mention" ? "" : "none";
      var rpBox = box.querySelector("#cbRpBox");
      if (rpBox) rpBox.style.display = v === "auto" ? "" : "none";
    }
    box.querySelectorAll('input[name="cbRw"]').forEach(function (i) { i.onchange = veRw; });

    // ---- Bot trả lời ai: ba thẻ quyết định ô chọn nào hiện, và chữ của ô đó
    function apGoiY() {
      var aud = giaTri("cbAud") || card0;
      box.querySelector("#cbPkHint").textContent = window.t(
        aud === "nhom" ? "cb2.pk_goi_nhom" : (pkTab === "group" ? "cb2.pk_goi_nhom" : "cb2.pk_goi_nguoi"));
    }
    function chuThe(v, tKey, dKey) {
      var th = box.querySelector('.cb-rc[data-v="' + v + '"]');
      th.querySelector("b").textContent = window.t(tKey);
      th.querySelector("small").textContent = window.t(dKey);
    }
    function apDoiTuong() {
      var co = coNhomForm();
      var aud = giaTri("cbAud") || card0;
      // Kênh không có nhóm (Zalo Bot) thì "mọi cuộc chat" và "nhắn riêng thoải mái" là MỘT: chỉ giữ hai
      // thẻ, chữ đổi cho đúng chuyện chỉ có người nhắn riêng. Thẻ Tự động hóa tất cả (bộ phán xử trong nhóm)
      // cũng vô nghĩa khi không có nhóm nào.
      box.querySelector('.cb-rc[data-v="all"]').style.display = co ? "" : "none";
      box.querySelector('.cb-rc[data-v="auto"]').style.display = co ? "" : "none";
      if (!co && (aud === "all" || aud === "auto")) {
        box.querySelector('input[name="cbAud"][value="nhom"]').checked = true;
        aud = "nhom";
      }
      if (co) {
        chuThe("nhom", "cb2.aud_nhom_t", "cb2.aud_nhom_d");
        chuThe("chon", "cb2.aud_chon_t", "cb2.aud_chon_d");
      } else {
        chuThe("nhom", "cb2.aud_moi_t", "cb2.aud_moi_d");
        chuThe("chon", "cb2.aud_chon_ko_t", "cb2.aud_chon_ko_d");
      }
      dongBo("cbAud");
      // Chọn "mọi cuộc chat" mở bot ra cho MỌI người nhắn tới, kể cả bạn bè và người nhà khi đó là
      // Zalo cá nhân: phải tick xác nhận (server cũng tự chặn lần nữa, xem chatbot_store).
      box.querySelector("#cbAckAudBox").style.display =
        (aud === "all" || aud === "auto") && !(sua && b.audience === "all") ? "" : "none";
      box.querySelector("#cbAckAudT").textContent = window.t(aud === "auto" ? "cb2.aud_auto_ack" : "cb2.aud_all_ack");
      var tabs = aud === "nhom" ? (co ? ["group"] : []) : aud === "chon" ? (co ? ["group", "private"] : ["private"]) : [];
      if (tabs.length && tabs.indexOf(pkTab) < 0) pkTab = tabs[0];
      box.querySelector("#cbPk").style.display = tabs.length ? "" : "none";
      box.querySelectorAll(".cb-pk-tab").forEach(function (t) {
        t.style.display = tabs.indexOf(t.dataset.t) >= 0 ? "" : "none";
      });
      box.querySelector("#cbRwBox").style.display = co ? "" : "none";
      box.querySelector("#cbKbBox").style.display = coZaloCaNhan() ? "" : "none";
      box.querySelector("#cbTagBox").style.display = coZaloCaNhan() ? "" : "none";
      if (coZaloCaNhan()) taiTag();
      // Không có nhóm thì nói vì sao, thay vì ẩn im lặng (0.102.1): chủ tưởng phải đưa bot vào nhóm mới hiện.
      var koNhom = box.querySelector("#cbKoNhom");
      var dsTk = tkDangChon();
      if (!co && dsTk.length) {
        var tenKenh = [];
        dsTk.forEach(function (a) {
          var n = kenhCua(a.channel).nhan;
          if (tenKenh.indexOf(n) < 0) tenKenh.push(n);
        });
        koNhom.textContent = window.t("cb2.ko_nhom", { kenh: tenKenh.join(", ") });
        koNhom.hidden = false;
      } else {
        koNhom.hidden = true;
      }
      apGoiY();
      veRw();
      if (tabs.length) taiChats();
    }
    box.querySelectorAll('input[name="cbAud"]').forEach(function (i) { i.onchange = apDoiTuong; });

    // Dòng tóm tắt ở đầu bước 2: bot này sẽ trả lời ở đâu, và lối quay lại đổi. Không có nó thì sang
    // bước 2 là mất dấu lựa chọn vừa làm.
    function veTom() {
      var t = box.querySelector("#cbTom");
      if (!t) return;
      var ds = tkDangChon();
      t.innerHTML = '<span class="cb-tom-l">' + esc(window.t("cb.tra_loi_o")) + '</span> ' +
        (ds.length ? ds.map(function (a) {
          // Tên KÊNH đi kèm tên tài khoản (0.102.1): Zalo Bot và Zalo cá nhân dùng chung một logo, mà hai kênh
          // khác nhau đúng ở chỗ có nhóm hay không, nên chỉ nhìn logo thì không hiểu vì sao mục nhóm biến mất.
          return '<span class="cb-kenh-chip">' + logoKenh(a.channel) + " " + esc(a.ten) +
                 ' <span class="cb-tom-kenh">· ' + esc(kenhCua(a.channel).nhan) + "</span></span>";
        }).join(" ") : '<span class="cb-warn">' + esc(window.t("cb.chua_chon_tk")) + '</span>') +
        ' <button type="button" class="cb-doi-tk">' + esc(window.t("cb.doi")) + '</button>';
      var nut = t.querySelector(".cb-doi-tk");
      if (nut) nut.onclick = function () { veBuoc(1); };
    }

    // Nối lại sự kiện cho danh sách tài khoản: nó được vẽ lại sau mỗi lần nối kênh mới.
    function noiTK() {
      box.querySelectorAll(".cb-tk-o").forEach(function (n) {
        n.onchange = function () { apDoiTuong(); veTom(); taiNl(); };
      });
      apDoiTuong();
      veTom();
      taiNl();
    }
    noiTK();

    box.querySelector(".cb-noi-kenh").onclick = function () {
      noiKenhMoi(function (aid) {
        var giu = tkDangChon().map(function (a) { return a.id; });
        if (aid) giu.push(aid);
        box.querySelector("#cbTkBox").innerHTML = veChonTK(b, giu, true);
        noiTK();
      });
    };

    // Hai nút ở chân form đổi vai theo bước. Một cặp nút cố định đọc dễ hơn hai hàng nút hiện ra rồi
    // biến đi, và trên điện thoại nó luôn nằm đúng một chỗ.
    function veBuoc(n) {
      buoc = n;
      box.querySelector("#cbB1").style.display = n === 1 ? "" : "none";
      box.querySelector("#cbB2").style.display = n === 2 ? "" : "none";
      var nhan = box.querySelector("#cbBuoc");
      if (nhan) nhan.textContent = window.t("cb.buoc_may", { n: n });
      // Form TẠO mở ở bước 1, form SỬA mở thẳng bước 2, nên nút trái đóng form ở bước khởi đầu và lùi
      // một bước ở bước kia. Không phân biệt thì ở form Sửa, bấm nút trái sau khi ghé bước 1 qua "Đổi"
      // là vứt hết những gì vừa sửa ở bước 2.
      var luiLaDong = sua ? n === 2 : n === 1;
      box.querySelector("#cbLui").textContent = luiLaDong ? window.t("common.cancel")
                                                          : window.t("cb.quay_lai");
      box.querySelector("#cbLui").onclick = luiLaDong ? dong : function () { veBuoc(sua ? 2 : 1); };
      box.querySelector("#cbTien").textContent = n === 1 ? window.t("cb.tiep_tuc")
                                                         : (sua ? window.t("common.save") : window.t("cb.tao_bot"));
      var xong = box.querySelector("#cbTaoXong");
      if (xong) xong.style.display = n === 2 ? "" : "none";
      if (n === 2) veTom();
      box.querySelector(".cb-form").scrollTop = 0;
    }
    box.querySelector("#cbTien").onclick = function () { if (buoc === 1) sangBuoc2(); else luu(); };
    veBuoc(buoc);

    // Không có tài khoản nào thì bước 2 vô nghĩa: bot tạo ra không có chỗ nào để trả lời.
    function sangBuoc2() {
      if (!tkDangChon().length) return alert(window.t("cb.chon_tai_khoan"));
      var ten = box.querySelector("#cbName");
      // Gợi tên từ tài khoản vừa chọn: gõ lại đúng cái tên vừa đọc ở bước trước là việc thừa.
      if (!ten.value.trim()) ten.value = (tkDangChon()[0] || {}).ten || "";
      veBuoc(2);
    }

    async function luu() {
      var ten = box.querySelector("#cbName").value.trim();
      var ag = box.querySelector("#cbAgent").value;
      var muc = giaTri("cbMuc") || "suggest";
      var ack = box.querySelector("#cbAck");
      var ids = tkDangChon().map(function (a) { return a.id; });
      if (!ids.length) { veBuoc(1); return alert(window.t("cb.chon_tai_khoan")); }
      if (!ten) return alert(window.t("cb.nhap_ten"));
      if (!ag) return alert(window.t("cb.chon_agent"));
      // Hai lớp, cố ý: ô tick ở đây để chủ ĐỌC, và server vẫn tự chặn lần nữa nên gỡ ô này bằng devtools
      // cũng không nâng được quyền hay mở bot ra cho mọi người.
      if (mucCua(muc).can_xac_nhan && !(ack && ack.checked)) {
        return alert(window.t("cb.can_ack", { muc: mucCua(muc).nhan }));
      }
      if (muc === "full" && !confirm(window.t("cb.xn_full", { ten: ten }))) return;
      var co = coNhomForm();
      var the = giaTri("cbAud") || "nhom";
      if (!co && (the === "all" || the === "auto")) the = "nhom";
      // Thẻ Tự động hóa tất cả lưu xuống thành audience=all + reply_when=auto, không thêm giá trị mới ở server.
      var aud = the === "auto" ? "all" : the;
      if (aud === "all" && !(sua && b.audience === "all") && !box.querySelector("#cbAckAud").checked) {
        return alert(window.t("cb2.can_ack_aud"));
      }
      function ds(loai) {
        return Object.keys(chon[loai]).filter(function (k) { return chon[loai][k]; });
      }
      var gioTu = ((box.querySelector("#cbGioTu") || {}).value || "").trim();
      var gioDen = ((box.querySelector("#cbGioDen") || {}).value || "").trim();
      if (!gioTu !== !gioDen) return alert(window.t("cb.gio_thieu"));
      var nhuong = ((box.querySelector("#cbNhuongTay") || {}).value || "").trim();
      if (nhuong !== "" && !(/^\d+$/.test(nhuong) && +nhuong <= 240)) return alert(window.t("cb.nhuong_tay_sai"));
      if (nlDs.some(function (e) { return e.cho_giay != null && !(e.cho_giay >= 0 && e.cho_giay <= 60 && e.cho_giay % 1 === 0); })) {
        return alert(window.t("cb.ngoai_le_sai"));
      }
      // Same rule as the server: an exception that RAISES a chat to Can write or Full power needs a conscious yes,
      // and only that yes sends the exception's own flag (`xac_nhan_ngoai_le`), separate from the bot-level one.
      var hang = { suggest: 0, read_docs: 1, auto: 2, full: 3 }, truoc = {};
      ((sua && b.ngoai_le) || []).forEach(function (e) { truoc[nlKhoa(e)] = e.muc_quyen; });
      var nang = nlDs.filter(function (e) {
        var k = nlKhoa(e);
        return hang[e.muc_quyen] >= 2 && hang[e.muc_quyen] > (truoc[k] in hang ? hang[truoc[k]] : -1);
      });
      if (nang.length && !confirm(window.t("cb.xn_ngoai_le", {
        ds: nang.map(function (e) { return (e.ten || e.chat_id) + ": " + mucCua(e.muc_quyen).nhan; }).join(", ") }))) return;
      // Không tài khoản nào đứng được trong nhóm thì gửi danh sách nhóm rỗng: bản ghi mang một danh
      // sách nhóm không bao giờ dùng tới là một lời hứa suông nằm lại trong dữ liệu.
      var chung = { name: ten, agent_slug: ag, agent_brain: br, brain: br,
                    nguon_tra_loi: "agent", muc_quyen: muc, xac_nhan_rui_ro: "1",
                    ngon_ngu: (document.getElementById("cbNgonNgu") || {}).value || "auto",
                    audience: aud, people: ds("private").join("\n"),
                    groups: co ? ds("group").join("\n") : "",
                    reply_when: co ? (the === "auto" ? "auto" : (giaTri("cbRw") || "mention")) : "mention",
                    account_ids: ids.join(","),
                    gio_truc: gioTu ? JSON.stringify({ tu: gioTu, den: gioDen }) : "",
                    nhuong_tay_phut: nhuong, ngoai_le: JSON.stringify(nlDs),
                    nhan_ket_ban: coZaloCaNhan() && (box.querySelector("#cbNhanKetBan") || {}).checked ? "1" : "0",
                    skip_labels: coZaloCaNhan() ? tagLuu() : "[]" };
      if (nang.length) chung.xac_nhan_ngoai_le = "1";
      try {
        if (sua) {
          await api("/chatbots/" + encodeURIComponent(b.id) + "/update", { method: "POST", body: fd(chung) });
        } else {
          await api("/chatbots", { method: "POST", body: fd(chung) });
        }
      } catch (e) { return alert(window.t("cb.loi_luu") + " " + e.message); }
      dong();
      tai();
    }
  }

  // Tab Kênh bấm "Tạo bot trực" trên một tài khoản: mở form với tài khoản đó tích sẵn. Đợi
  // trang nạp xong danh sách kênh (tai) rồi mới mở, để ô chọn có đủ dữ liệu.
  document.addEventListener("javis:chatbot-new", function (e) {
    var aid = (e.detail || {}).account_id;
    doiNap(function () { moForm(null, { account_id: aid }); });
  });

  // Chatbot v5 (2026-10-28): "Open the settings of bot X" in a chat's Info panel. The bot of a chat may belong to another
  // brain than the one open (this page only loads the open brain's bots); then say so instead of opening nothing.
  document.addEventListener("javis:chatbot-open", function (e) {
    var id = (e.detail || {}).bot_id;
    if (!id) return;
    var lan = 0;
    (function thu() {
      var b = _bots.filter(function (x) { return x.id === id; })[0];
      if (b && _kenhDS.length) return moForm(b);
      if (lan++ > 20) return b ? moForm(b) : alert(window.t("ib.bot_other_brain"));
      setTimeout(thu, 150);
    })();
  });

  // (0.62.2 đã bỏ tay bắt "javis:chatbot-edit" ở đây. Tab Kênh từng bấm Xoá là nhảy sang đây
  // mở form Sửa của con bot đang giữ tài khoản, nhưng trang này chỉ nạp bot của BRAIN ĐANG MỞ
  // còn tài khoản kênh thì toàn cục - nên với con bot ở brain khác, đường đó luôn kết thúc
  // bằng câu "đổi brain rồi thử lại" mà không nói đổi sang brain nào. Nay tab Tài khoản bot tự gỡ tài
  // khoản khỏi bot rồi xoá trong một lần hỏi, không phải đi vòng qua trang này nữa.)

  // Đợi trang nạp xong (kênh + danh sách bot) rồi mới mở form, để ô chọn có đủ dữ liệu. Bỏ cuộc
  // sau 3 giây: mở một form thiếu dữ liệu vẫn hơn là không mở gì và không nói gì.
  function doiNap(xong) {
    var cho = 0;
    (function thu() {
      if ((_kenhDS.length && _bots) || cho++ > 20) return xong();
      setTimeout(thu, 150);
    })();
  }

  window.JavisChatbots = { render: render };
})();
