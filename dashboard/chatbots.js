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
  // tài khoản ở tab Kênh.
  var _tkRanh = [];

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
    return '<span class="cb-kenh-chip" title="' + esc(k.nhan) + '">' + logoKenh(a.channel) + " " +
           esc(a.external_id ? (k.tien_to_ten || "") + a.external_id : (a.label || k.nhan)) + "</span>";
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
        '<p class="cb-intro">' + esc(window.t("cb.intro_1")) + ' <b>' + esc(brain()) + '</b>' +
        esc(window.t("cb.intro_2")) + ' <b>Agent</b> ' + esc(window.t("cb.intro_3")) +
        esc(window.t("cb.intro_4")) + ' <b>' + esc(window.t("cb.intro_chi_doc")) + '</b>' +
        esc(window.t("cb.intro_5")) + ' <b>' + esc(window.t("cb.intro_lam_that")) + '</b> ' +
        esc(window.t("cb.intro_6")) + '<br>' +
        esc(window.t("cb.intro_7")) + '<br>' +
        esc(window.t("cb.intro_8")) + '</p>' +
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
        '<div class="cb-empty"><div class="cb-empty-ico">' + ic("bot", { cls: "ic-xl" }) + '</div>' +
        '<b>' + esc(window.t("cb.rong_tieu_de")) + '</b>' +
        '<div>' + esc(window.t("cb.rong_1")) + ' <b>' + esc(window.t("cb.rong_tat")) + '</b>' +
        esc(window.t("cb.rong_2")) + '</div></div>';
      return;
    }
    if (!ds.length) { box.innerHTML = '<div class="cb-empty">' + esc(window.t("cb.khong_khop")) + '</div>'; return; }
    box.innerHTML = "";
    ds.forEach(function (b) { box.appendChild(the(b)); });
  }

  function the(b) {
    var st = b.status || {};
    var tt = TRANG_THAI[st.state] || TRANG_THAI.off;
    var loi = st.last_error ? '<div class="cb-err">' + esc(String(st.last_error).slice(0, 160)) + '</div>' : "";
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
        esc(String(b.loi_luot).slice(0, 200)) + '</div>' : "";
    // Lượt CHẠY ĐƯỢC nhưng không đúng mức đã đặt (engine không gọi nổi công cụ, hoặc chưa đấu
    // nguồn nào). Màu vàng chứ không đỏ: bot vẫn trả lời tử tế, chỉ là chạy thiếu quyền. Để im
    // thì chủ tưởng bot đang làm việc thật - đúng kiểu hỏng lặng lẽ mà cả trang này chống.
    var cbao = b.canh_bao_luot
      ? '<div class="cb-quyen ghi">' + ic("triangle-alert") + ' ' +
        esc(String(b.canh_bao_luot).slice(0, 300)) + '</div>' : "";
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
      auto: " - " + window.t("cb.mq_auto"),
      full: " - " + window.t("cb.mq_full"),
    };
    var quyen =
      '<div class="cb-quyen ' + (mq === "full" ? "full" : mq === "auto" ? "ghi" : "doc") + '">' +
        // "shield-alert" không có trong bộ icon đã vendor nên bản trước vẽ ra một ô trống ở
        // đúng chỗ đáng chú ý nhất. Test icon không bắt được vì nó chỉ dò tên viết thẳng trong
        // lời gọi, không dò lời gọi có biểu thức ở trong.
        ic(mq === "full" ? "shield" : mq === "auto" ? "pencil" : "eye") +
        ' ' + esc(window.t("cb.muc_nhan")) + ' <b>' + esc(mucCua(mq).nhan) + '</b>' +
        esc(mqLoi[mq] || "") +
      '</div>';
    // Nhóm có người gọi bot mà chủ chưa cho phép. Đây là chỗ sửa cho lỗi "thả bot vào nhóm,
    // tag tên nó, không thấy gì": hành vi từ chối vẫn đúng, nhưng nay nó nổi lên đây kèm đúng
    // một nút bấm, thay vì bắt chủ đoán rằng mình phải đi khai id nhóm ở đáy form Sửa.
    var cho = (b.nhom_cho || []).map(function (g) {
      return '<div class="cb-nhomcho" data-cid="' + esc(g.chat_id) + '">' +
        '<div class="cb-nhomcho-t">' + ic("message-circle") + ' <b>' +
          esc(g.ten || (window.t("cb.nhom") + " " + g.chat_id)) +
          '</b> <span class="cb-nhomcho-id">' + esc(g.chat_id) + '</span></div>' +
        '<div class="cb-nhomcho-d">' + esc(g.lan
          ? window.t("cb.nhomcho_goi", { count: g.lan })
          : window.t("cb.nhomcho_chua_bat")) + '</div>' +
        '<div class="cb-nhomcho-a">' +
          '<button class="s-btn cb-ok-nhom" type="button">' + ic("check") + ' ' +
            esc(window.t("cb.cho_phep_nhom")) + '</button>' +
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
      ? '<div class="cb-quyen ghi">' + ic("triangle-alert") + ' ' + esc(window.t("cb.rt_1")) +
        ' <b>' + esc(window.t("cb.rt_che_do")) + '</b> ' + esc(window.t("cb.rt_2")) +
        ' <b>' + esc(window.t("cb.rt_lenh")) + '</b> ' + esc(window.t("cb.rt_va")) +
        ' <b>' + esc(window.t("cb.rt_tra_thang")) + '</b>' +
        esc(b.reply_when === "always" ? window.t("cb.rt_always") : window.t("cb.rt_mention")) + '.<br>' +
        esc(window.t("cb.rt_fix_1")) + ' <b>@BotFather</b> ' + esc(window.t("cb.rt_go")) +
        ' <b>/setprivacy</b>' + esc(window.t("cb.rt_fix_2")) + ' <b>Disable</b>' +
        esc(window.t("cb.rt_fix_3")) + ' <b>' + esc(window.t("cb.rt_quan_tri")) + '</b>. ' +
        esc(window.t("cb.rt_fix_4")) + '</div>' : "";
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
          '<span>' + ic("bot") + ' ' + esc(b.agent_name || (b.agent || {}).slug || "?") + '</span>' +
        '</div>' +
        '<div class="cb-meta">' +
          '<span>' + esc(!coNhom(b) ? window.t("cb.chi_rieng") : (b.groups || []).length
            ? (window.t("cb.n_nhom", { count: b.groups.length }) + ", " +
               (b.reply_when === "always" ? window.t("cb.tl_moi_tin") : window.t("cb.tl_goi_ten")))
            : window.t("cb.chi_rieng")) + '</span>' +
          '<span>' + esc(b.nguon_tra_loi === "tai_lieu" ? window.t("cb.nguon_tl_ngan")
                                                        : window.t("cb.nguon_ag_ngan")) + '</span>' +
          '<span>' + esc(window.t("cb.n_luot_tra_loi", { count: st.answered || 0 })) + '</span>' +
          (b.handoff_to ? '<span>' + ic("user") + ' ' + esc(window.t("cb.co_chuyen_nguoi")) + '</span>'
                        : '<span class="cb-warn">' + esc(window.t("cb.chua_nguoi_nhan")) + '</span>') +
        '</div>' +
        // Hộp thư hội thoại: số cuộc chat khách hôm nay và số chưa đọc, ngay trên thẻ. Bấm nút
        // Hội thoại ở dưới là sang trang Hội thoại đã lọc sẵn theo bot này.
        (b.hoi_thoai && (b.hoi_thoai.tong || 0) > 0
          ? '<div class="cb-meta"><span>' + ic("messages-square") + ' ' +
            esc(window.t("cb.hoi_thoai_tom", { hom_nay: b.hoi_thoai.hom_nay || 0,
                                               chua_doc: b.hoi_thoai.chua_doc || 0 })) + '</span></div>'
          : "") +
        cho + quyen + loiTen + riengTu + mat + lluot + cbao + loi +
        '<div class="cb-acts">' +
          '<button class="s-btn-ghost cb-toggle" type="button">' +
            (b.enabled ? ic("circle-stop") + " " + esc(window.t("cb.tat"))
                       : ic("play") + " " + esc(window.t("cb.bat"))) + '</button>' +
          '<button class="s-btn-ghost cb-log" type="button">' + ic("history") + ' ' +
            esc(window.t("cb.nhat_ky")) + '</button>' +
          '<button class="s-btn-ghost cb-hoi-thoai" type="button">' + ic("messages-square") + ' ' +
            esc(window.t("cb.xem_hoi_thoai")) + '</button>' +
          '<button class="s-btn-ghost cb-edit" type="button">' + esc(window.t("common.edit")) + '</button>' +
          '<button class="s-btn-ghost cb-del" type="button">' + esc(window.t("common.delete")) + '</button>' +
        '</div>' +
      '</div>');
    c.querySelector(".cb-toggle").onclick = function () { bat(b, !b.enabled); };
    c.querySelector(".cb-log").onclick = function () { moNhatKy(b); };
    c.querySelector(".cb-hoi-thoai").onclick = function () {
      if (window.JavisConversations) window.JavisConversations.mo({ bot_id: b.id });
    };
    c.querySelector(".cb-edit").onclick = function () { moForm(b); };
    c.querySelector(".cb-del").onclick = function () { xoa(b); };
    c.querySelectorAll(".cb-nhomcho").forEach(function (n) {
      var cid = n.dataset.cid;
      n.querySelector(".cb-ok-nhom").onclick = function () { choNhom(b, cid, true); };
      n.querySelector(".cb-bo-nhom").onclick = function () { choNhom(b, cid, false); };
    });
    return c;
  }

  // Một cú bấm thay cho: gõ /id trong nhóm, chép id, mở Sửa, kéo xuống đáy form, dán, Lưu.
  async function choNhom(b, cid, on) {
    try {
      await api("/chatbots/" + encodeURIComponent(b.id) + "/groups",
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
  async function nạpAgent(br) {
    try {
      var ad = await api("/agents?brain=" + encodeURIComponent(br || "brain"));
      return ad.agents || [];
    } catch (e) { return []; }
  }

  // Vai trò dài thì <option> tràn ngang khỏi hộp và không xuống dòng được (giới hạn của thẻ
  // select gốc). Cắt ngắn là cách duy nhất chắc chắn; tên Agent luôn giữ đủ.
  function optAgent(a, slugDangChon) {
    var vai = String(a.role || "").trim();
    if (vai.length > 34) vai = vai.slice(0, 34).trim() + "…";
    return '<option value="' + esc(a.slug) + '"' + (a.slug === slugDangChon ? " selected" : "") +
           '>' + esc(a.name) + (vai ? " - " + esc(vai) : "") + '</option>';
  }

  function htmlAgent(ds, slugDangChon) {
    return ds.length ? ds.map(function (a) { return optAgent(a, slugDangChon); }).join("")
                     : '<option value="">' + esc(window.t("cb.khong_agent")) + '</option>';
  }

  // Mô tả một dòng cho mỗi mức, hiện ngay trong ô chọn. Cảnh báo ĐẦY ĐỦ nằm ở khối dưới và do
  // server cấp; ba dòng này chỉ để chọn cho đúng ngay từ đầu.
  var MUC_TOM = {
    suggest: "cb.muctom_suggest",
    auto: "cb.muctom_auto",
    full: "cb.muctom_full",
  };

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


  function htmlMuc(dangChon) {
    var ds = _mucDS.length ? _mucDS : [{ id: "suggest", nhan: window.t("cb.muc_chi_doc") }];
    return ds.map(function (m) {
      return '<option value="' + esc(m.id) + '"' + (m.id === dangChon ? " selected" : "") + '>' +
             esc(MUC_TOM[m.id] ? window.t(MUC_TOM[m.id]) : m.nhan) + '</option>';
    }).join("");
  }

  // Khối cảnh báo dựng từ danh sách câu SERVER trả về. Mức chỉ đọc không có câu nào, và đúng
  // như vậy: nó không lấy đi thứ gì để mà cảnh báo.
  function veCanhBao(id) {
    var m = mucCua(id);
    if (!(m.canh_bao || []).length) {
      return '<div class="cb-hint">' + esc(window.t("cb.canhbao_chi_doc")) + '</div>';
    }
    return '<div class="cb-canhbao ' + (id === "full" ? "full" : "ghi") + '">' +
      '<div class="cb-canhbao-h">' + ic("triangle-alert") + ' ' + esc(window.t("cb.canhbao_h1")) +
      ' <b>' + esc(m.nhan) + '</b> ' + esc(window.t("cb.canhbao_h2")) + '</div><ul>' +
      m.canh_bao.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") +
      '</ul><label class="cb-ack"><input type="checkbox" id="cbAck"> ' +
      esc(window.t("cb.ack")) + '</label></div>';
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
    if (!ds.length) return '<div class="cb-trong-tk">' + esc(window.t("cb.tk_chua_co")) + '</div>';
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
        (a.external_id ? ' · ' + esc((k.tien_to_ten || "") + a.external_id) : "") + '</small></span></label>';
    }).join("") + '</div>';
  }

  // Mở modal "Thêm tài khoản" của tab Kênh (chatbots.js KHÔNG tự dựng lại form dán token: xem
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
      } catch (e) {}
      // Ghép tay tài khoản vừa nối vào danh sách nếu lần nạp lại chưa thấy nó (mạng hỏng, hoặc
      // server trả về trước khi kho kịp thấy bản ghi mới). Không có bước này thì id vừa tích
      // rơi lặng lẽ: người dùng nối xong một kênh mà nó không hiện ra ở đâu cả.
      if (tk && tk.id && !_tkRanh.some(function (a) { return a.id === tk.id; })) _tkRanh.push(tk);
      xong(tk && tk.id ? tk.id : "");
    } });
  }

  // `truoc` (tuỳ chọn): { account_id } - tài khoản tích sẵn khi mở từ tab Kênh ("Tạo bot trực").
  //
  // Form đi theo HAI BƯỚC, và đó là cả điểm của nó. Bước 1 hỏi đúng một câu - bot trả lời ở
  // đâu - bước 2 mới là cài đặt. Trước 0.61.1 cả hai nằm chung một màn, kèm luôn một form dán
  // token với hướng dẫn riêng của từng kênh (lấy token ở đâu, kênh nào không vào được nhóm);
  // trên điện thoại người dùng phải cuộn qua một trang chú thích trước khi thấy ô Tên bot. Nó
  // cũng không mở rộng được: mỗi kênh thêm vào là màn hình dài thêm một khối chú thích nữa.
  // Nay hướng dẫn của một kênh chỉ hiện khi người dùng thật sự chọn kênh đó, trong modal Thêm
  // tài khoản của tab Kênh - một chỗ duy nhất cho mọi kênh.
  //
  // Sửa bot thì vào thẳng bước 2: tài khoản đã chọn rồi, bắt đi lại từ đầu chỉ để sửa một dòng
  // chữ là phiền. Dòng tóm tắt ở đầu bước 2 vẫn dẫn ngược về bước 1 khi cần đổi.
  async function moForm(b, truoc) {
    var sua = !!b;
    var br = brain();                 // brain đang mở = brain của bot, không hỏi lại
    var agents = await nạpAgent(br);
    var chonSan = (truoc && truoc.account_id) ? [truoc.account_id] : [];
    var buoc = sua ? 2 : 1;
    var box = el(
      '<div class="cb-modal"><div class="cb-form cb-wizard">' +
        '<div class="cb-form-h">' +
          '<h3>' + esc(sua ? window.t("cb.sua_bot") : window.t("cb.bot_moi")) + '</h3>' +
          (sua ? "" : '<span class="cb-buoc" id="cbBuoc"></span>') +
        '</div>' +

        // ---------------------------------------------------------------- BƯỚC 1: trả lời ở đâu
        '<div class="cb-b" id="cbB1">' +
          '<label>' + esc(window.t("cb.lb_tai_khoan")) + '</label>' +
          '<div id="cbTkBox">' + veChonTK(b, chonSan) + '</div>' +
          '<div class="cb-hint">' + esc(window.t("cb.hint_tai_khoan")) + '</div>' +
          '<button class="s-btn-ghost cb-noi-kenh" type="button">' + ic("plus") + ' ' +
            esc(window.t("cb.noi_kenh_moi")) + '</button>' +
        '</div>' +

        // ---------------------------------------------------------------- BƯỚC 2: cài đặt bot
        '<div class="cb-b" id="cbB2">' +
          '<div class="cb-tom" id="cbTom"></div>' +

          '<label>' + esc(window.t("cb.lb_ten")) + '</label>' +
          '<input id="cbName" value="' + esc(b ? b.name : "") + '" placeholder="' +
            esc(window.t("cb.ph_ten")) + '">' +

          '<label>' + esc(window.t("cb.lb_agent")) + '</label>' +
          '<div class="cb-row">' +
            '<select id="cbAgent">' + htmlAgent(agents, (b && (b.agent || {}).slug) || "") + '</select>' +
            '<button class="s-btn-ghost" id="cbNewAgent" type="button">' + ic("plus") + ' ' +
              esc(window.t("cb.tao_agent")) + '</button>' +
          '</div>' +
          '<div class="cb-hint">' + esc(window.t("cb.hint_agent_1")) + ' <b>' + esc(br) + '</b>' +
          esc(window.t("cb.hint_agent_2")) + ' <b>' + esc(window.t("cb.tao_agent")) + '</b> ' +
          esc(window.t("cb.hint_agent_3")) + '</div>' +

          // Lựa chọn này quyết định bot "ăn nhập với Agent" hay không, nên đặt ngay dưới Agent
          // chứ không giấu trong khối Cài đặt thêm: nó là thứ người dùng cần hiểu TRƯỚC khi
          // bấm tạo.
          '<label>' + esc(window.t("cb.lb_nguon")) + '</label>' +
          '<select id="cbNguon">' +
            '<option value="agent"' + (!b || b.nguon_tra_loi !== "tai_lieu" ? " selected" : "") + '>' +
              esc(window.t("cb.nguon_agent")) + '</option>' +
            '<option value="tai_lieu"' + (b && b.nguon_tra_loi === "tai_lieu" ? " selected" : "") + '>' +
              esc(window.t("cb.nguon_tai_lieu")) + '</option>' +
          '</select>' +
          '<div class="cb-hint"><b>' + esc(window.t("cb.nguon_agent_b")) + '</b>' +
          esc(window.t("cb.hint_nguon_1")) + '<br>' +
          '<b>' + esc(window.t("cb.nguon_tl_b")) + '</b>' + esc(window.t("cb.hint_nguon_2")) + '</div>' +

          // Mức quyền KHÔNG bao giờ nằm trong khối gấp lại: đây là quyết định nặng nhất trong
          // cả form, phải đọc trước khi bấm tạo chứ không phải một ô phải bấm mới thấy.
          '<label>' + esc(window.t("cb.lb_muc")) + '</label>' +
          '<select id="cbMuc">' + htmlMuc((b && b.muc_quyen) || "suggest") + '</select>' +
          '<div class="cb-muc-note">' + veCanhBao((b && b.muc_quyen) || "suggest") + '</div>' +

          // Ba thứ còn lại gấp vào đây vì đều có mặc định dùng được ngay: ngôn ngữ tự nhận,
          // không chuyển người thật, chưa khai nhóm nào. Ai cần mới mở.
          '<details class="cb-nangcao">' +
            '<summary>' + ic("settings") + ' ' + esc(window.t("cb.nang_cao")) + '</summary>' +

            // Ngôn ngữ của bot ĐỘC LẬP với ngôn ngữ của chủ, và đó là cả lý do ô này tồn tại:
            // bot nói chuyện với NGƯỜI NGOÀI, không phải với chủ. Chủ dùng Javis bằng tiếng
            // Việt mà người nhắn cho bot lại nói tiếng khác là chuyện bình thường, nên lấy
            // ngôn ngữ của chủ suy ra ngôn ngữ của bot là suy sai.
            '<label>' + esc(window.t("cb.lb_ngon_ngu")) + '</label>' +
            '<select id="cbNgonNgu">' + htmlNgonNgu((b && b.ngon_ngu) || "auto") + '</select>' +
            '<div class="cb-muc-note">' + esc(window.t("cb.hint_ngon_ngu")) + '</div>' +

            '<label>' + esc(window.t("cb.lb_handoff")) + '</label>' +
            '<input id="cbHandoff" value="' + esc(b ? (b.handoff_to || "") : "") + '" placeholder="' +
              esc(window.t("cb.ph_handoff")) + '">' +
            '<div class="cb-hint">' + esc(window.t("cb.hint_ho_1")) + ' <b>' +
            esc(window.t("cb.hint_ho_hai_cau")) + '</b> ' + esc(window.t("cb.hint_ho_2")) + '<br>' +
            esc(window.t("cb.hint_ho_3")) + ' <b>' + esc(window.t("cb.hint_ho_binh_thuong")) + '</b> ' +
            esc(window.t("cb.hint_ho_4")) + ' <b>' + esc(window.t("cb.nguon_tl_b")) + '</b> ' +
            esc(window.t("cb.hint_ho_5")) + '</div>' +

            // Khai được NGAY LÚC TẠO, không chỉ ở form Sửa. Đường đi tự nhiên nhất là tạo bot
            // rồi thả thẳng vào nhóm; bắt quay lại bấm Sửa mới khai được nhóm là bảo đảm lần
            // thử đầu tiên của mọi người dùng đều gặp một con bot im lặng.
            // Cả khối nhóm ẩn đi với kênh không vào được nhóm. Hiện ra rồi để nó không có tác
            // dụng là hứa suông: người dùng ngồi khai id nhóm xong chờ mãi một con bot không
            // bao giờ vào được nhóm nào, và không có gì nói cho họ biết.
            '<div id="cbNhomBox">' +
              '<label>' + esc(window.t("cb.lb_nhom")) + '</label>' +
              '<textarea id="cbGroups" rows="2" placeholder="' + esc(window.t("cb.ph_nhom")) + '">' +
                esc(((b && b.groups) || []).join("\n")) + '</textarea>' +
              '<div class="cb-hint">' + esc(window.t("cb.hint_ho_3")) + ' <b>' +
              esc(window.t("cb.hint_nhom_rieng")) + '</b>' + esc(window.t("cb.hint_nhom_1")) +
              ' <b>' + esc(window.t("cb.cho_phep")) + '</b>' + esc(window.t("cb.hint_nhom_2")) +
              ' <b>/id</b> ' + esc(window.t("cb.hint_nhom_3")) + '</div>' +

              '<label>' + esc(window.t("cb.lb_reply_when")) + '</label>' +
              '<select id="cbReplyWhen">' +
                '<option value="mention"' + (!b || b.reply_when !== "always" ? " selected" : "") + '>' +
                  esc(window.t("cb.rw_mention")) + '</option>' +
                '<option value="always"' + (b && b.reply_when === "always" ? " selected" : "") + '>' +
                  esc(window.t("cb.rw_always")) + '</option>' +
              '</select>' +
              '<div class="cb-hint"><b>' + esc(window.t("cb.rw_moi_tin")) + '</b> ' +
              esc(window.t("cb.hint_rw_1")) + '<b>/setprivacy</b> ' +
              esc(window.t("cb.hint_rw_2")) + '</div>' +
            '</div>' +
            '<div class="cb-hint cb-khong-nhom" id="cbKhongNhom" style="display:none">' +
              esc(window.t("cb.khong_nhom_1")) + ' <b>' + esc(window.t("cb.hint_nhom_rieng")) + '</b>' +
              esc(window.t("cb.khong_nhom_2")) + '</div>' +
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

    // Sang thẳng trang Cộng sự. Đóng form trước để quay lại không bị hai lớp modal chồng nhau.
    box.querySelector("#cbNewAgent").onclick = function () {
      dong();
      try { window.JavisNav.go("workspace"); } catch (e) {}
    };

    // Đổi mức là vẽ lại cảnh báo NGAY, và ô đồng ý luôn bắt đầu ở trạng thái chưa tick. Giữ
    // lại tick cũ khi đổi từ "Được ghi" sang "Toàn quyền" là để chủ đồng ý với một danh sách
    // rủi ro mà họ chưa đọc.
    var oMuc = box.querySelector("#cbMuc");
    var oNote = box.querySelector(".cb-muc-note");
    oMuc.onchange = function () { oNote.innerHTML = veCanhBao(oMuc.value); };

    // Khối nhóm chỉ hiện khi CÓ tài khoản đứng được trong nhóm. Hiện ra rồi để nó không có tác
    // dụng là hứa suông: người dùng ngồi khai id nhóm xong chờ mãi một con bot không bao giờ
    // vào được nhóm nào.
    function tkDangChon() {
      return Array.prototype.slice.call(box.querySelectorAll(".cb-tk-o:checked")).map(function (n) {
        return { id: n.value, channel: n.dataset.k, ten: n.dataset.ten || "" };
      });
    }
    function coNhomForm() {
      return tkDangChon().some(function (a) { return kenhCua(a.channel).co_nhom; });
    }
    function apNhom() {
      var co = coNhomForm();
      var nhomBox = box.querySelector("#cbNhomBox");
      var khong = box.querySelector("#cbKhongNhom");
      if (nhomBox) nhomBox.style.display = co ? "" : "none";
      if (khong) khong.style.display = co ? "none" : "";
    }

    // Dòng tóm tắt ở đầu bước 2: bot này sẽ trả lời ở đâu, và lối quay lại đổi. Không có nó thì
    // sang bước 2 là mất dấu lựa chọn vừa làm.
    function veTom() {
      var t = box.querySelector("#cbTom");
      if (!t) return;
      var ds = tkDangChon();
      t.innerHTML = '<span class="cb-tom-l">' + esc(window.t("cb.tra_loi_o")) + '</span> ' +
        (ds.length ? ds.map(function (a) {
          return '<span class="cb-kenh-chip">' + logoKenh(a.channel) + " " + esc(a.ten) + "</span>";
        }).join(" ") : '<span class="cb-warn">' + esc(window.t("cb.chua_chon_tk")) + '</span>') +
        ' <button type="button" class="cb-doi-tk">' + esc(window.t("cb.doi")) + '</button>';
      var nut = t.querySelector(".cb-doi-tk");
      if (nut) nut.onclick = function () { veBuoc(1); };
    }

    // Nối lại sự kiện cho danh sách tài khoản: nó được vẽ lại sau mỗi lần nối kênh mới.
    function noiTK() {
      box.querySelectorAll(".cb-tk-o").forEach(function (n) {
        n.onchange = function () { apNhom(); veTom(); };
      });
      apNhom();
      veTom();
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

    // Hai nút ở chân form đổi vai theo bước. Một cặp nút cố định đọc dễ hơn hai hàng nút hiện
    // ra rồi biến đi, và trên điện thoại nó luôn nằm đúng một chỗ.
    function veBuoc(n) {
      buoc = n;
      box.querySelector("#cbB1").style.display = n === 1 ? "" : "none";
      box.querySelector("#cbB2").style.display = n === 2 ? "" : "none";
      var nhan = box.querySelector("#cbBuoc");
      if (nhan) nhan.textContent = window.t("cb.buoc_may", { n: n });
      // Form TẠO mở ở bước 1, form SỬA mở thẳng bước 2, nên nút trái đóng form ở bước khởi
      // đầu và lùi một bước ở bước kia. Không phân biệt thì ở form Sửa, bấm nút trái sau khi
      // ghé bước 1 qua "Đổi" là vứt hết những gì vừa sửa ở bước 2.
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
      var ho = box.querySelector("#cbHandoff").value.trim();
      var ngu = box.querySelector("#cbNguon").value;
      var muc = oMuc.value;
      var ack = box.querySelector("#cbAck");
      var ids = tkDangChon().map(function (a) { return a.id; });
      if (!ids.length) { veBuoc(1); return alert(window.t("cb.chon_tai_khoan")); }
      if (!ten) return alert(window.t("cb.nhap_ten"));
      if (!ag) return alert(window.t("cb.chon_agent"));
      // Hai lớp, cố ý: ô tick ở đây để chủ ĐỌC, và server vẫn tự chặn lần nữa (can_force) nên
      // gỡ ô này bằng devtools cũng không nâng được quyền.
      if (mucCua(muc).can_xac_nhan && !(ack && ack.checked)) {
        return alert(window.t("cb.can_ack", { muc: mucCua(muc).nhan }));
      }
      if (muc === "full" && !confirm(window.t("cb.xn_full", { ten: ten }))) return;
      // Không tài khoản nào đứng được trong nhóm thì gửi rỗng, đừng gửi thứ người dùng gõ
      // lúc còn tích tài khoản khác: bản ghi mang một danh sách nhóm không bao giờ dùng tới
      // là một lời hứa suông nằm lại trong dữ liệu.
      var coNhomLuu = coNhomForm();
      var gr = coNhomLuu ? box.querySelector("#cbGroups").value : "";
      var rw = coNhomLuu ? box.querySelector("#cbReplyWhen").value : "mention";
      var chung = { name: ten, agent_slug: ag, agent_brain: br, brain: br,
                    handoff_to: ho, nguon_tra_loi: ngu, muc_quyen: muc, xac_nhan_rui_ro: "1",
                    ngon_ngu: (document.getElementById("cbNgonNgu") || {}).value || "auto",
                    groups: gr, reply_when: rw, account_ids: ids.join(",") };
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
    var cho = 0;
    (function thu() {
      if (_kenhDS.length || cho++ > 20) return moForm(null, { account_id: aid });
      setTimeout(thu, 150);
    })();
  });

  window.JavisChatbots = { render: render };
})();
