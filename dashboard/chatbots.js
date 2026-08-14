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
    if (!r.ok || d.ok === false) throw new Error((d && d.error) || ("Lỗi " + r.status));
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
    running:  { nhan: "Đang chạy", mau: "ok" },
    starting: { nhan: "Đang khởi động", mau: "wait" },
    error:    { nhan: "Lỗi", mau: "err" },
    off:      { nhan: "Đã tắt", mau: "off" },
  };

  // Nhãn + cảnh báo của từng mức quyền do SERVER cấp (kèm trong GET /chatbots). Không chép
  // cứng ở đây: chép rồi thì một hôm server siết thêm rào mà ô cảnh báo vẫn hứa như cũ, và
  // chủ bấm đồng ý dựa trên một câu đã sai.
  var _bots = [], _q = "", _host = null, _mucDS = [], _timer = null, _dauVet = "";
  // Danh sách kênh do SERVER cấp (kèm chỗ lấy token và kênh đó KHÔNG làm được gì). Không chép
  // cứng ở đây: hôm nào Zalo mở API gửi tài liệu thì server đổi một chỗ, giao diện theo ngay.
  var _kenhDS = [], _kenhLoc = "";

  function kenhCua(id) {
    for (var i = 0; i < _kenhDS.length; i++) if (_kenhDS[i].id === id) return _kenhDS[i];
    return { id: id || "telegram", nhan: Icons.kenhNhan(id) || "Telegram",
             lay_token: "", co_nhom: id !== "zalo", gui_tai_lieu: id !== "zalo" };
  }

  // Nhãn kênh: LOGO + tên. Đây là thứ phân biệt hai con bot trong cùng một lưới thẻ, nên nó
  // phải bắt mắt trước khi người ta kịp đọc chữ - xem khối chú thích ở Icons.kenh.
  function chipKenh(id, cls) {
    return '<span class="cb-kenh-chip ' + (cls || "") + '">' + Icons.kenh(id, { size: "13px" }) +
           " " + esc(kenhCua(id).nhan) + "</span>";
  }

  // Trạng thái bot là thứ ĐỔI MÀ KHÔNG AI BẤM: bấm Bật xong server trả về "đang khởi động"
  // (poller mới tạo, chưa kịp hỏi Telegram), rồi vài giây sau nó thành "đang chạy" - nhưng
  // trang chỉ nạp lại khi người dùng bấm cái gì đó, nên thẻ đứng nguyên ở "Đang khởi động" cho
  // tới lúc rời trang rồi quay lại. Chủ repo dính đúng ca này: bot chạy thật, trả lời thật, mà
  // thẻ vẫn báo đang khởi động. Poller cũng là chỗ duy nhất thấy được bot vừa CHẾT.
  var NHIP = 5000;

  function mucCua(id) {
    for (var i = 0; i < _mucDS.length; i++) if (_mucDS[i].id === id) return _mucDS[i];
    return { id: id || "suggest", nhan: "Chỉ đọc", canh_bao: [], can_xac_nhan: false };
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
          '<input class="cb-search" placeholder="Tìm bot theo tên…">' +
          '<button class="s-btn cb-new" type="button">' + ic("plus") + ' Bot mới</button>' +
        '</div>' +
        '<div class="cb-loc"></div>' +
        '<p class="cb-intro">Bot của brain <b>' + esc(brain()) + '</b>. Mỗi bot là một ' +
        '<b>Agent</b> trong brain này, đem ra trả lời người ngoài qua một bot nhắn tin riêng ' +
        'trên <b>Telegram</b> hoặc <b>Zalo</b>. ' +
        'Bot làm theo đúng quy định trong file Agent. Mặc định nó <b>chỉ đọc được brain này</b>: ' +
        'không ghi, không gọi nguồn dữ liệu, không có lệnh quản trị. Cần bot <b>làm việc thật</b> ' +
        'thì nâng mức quyền khi tạo hoặc sửa - đọc kỹ phần rủi ro ở đó, vì người điều khiển bot ' +
        'là người nhắn cho nó chứ không phải bạn.<br>' +
        'Hai rào giữ nguyên ở MỌI mức: bot không thấy brain khác, và không chạy được lệnh máy.<br>' +
        'Đổi brain ở đầu trang là thấy bot của brain đó.</p>' +
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
    if (!im) box.innerHTML = '<div class="cb-empty">Đang tải…</div>';
    try {
      // Lọc theo brain đang mở: trang này thuộc về một brain, y như trang Agents và Skills.
      // console.js tự gọi lại renderPage khi đổi brain nên không cần lắng nghe gì thêm.
      var d = await api("/chatbots?brain=" + encodeURIComponent(brain()));
      _bots = d.bots || [];
      _mucDS = d.muc_quyen || [];
      _langDS = d.lang_list || [];
      _kenhDS = d.kenh || [];
      var vet = JSON.stringify(_bots);
      // Nhịp ngầm mà không có gì đổi thì ĐỪNG dựng lại DOM. Không phải để tiết kiệm: dựng lại
      // mỗi 5 giây nghĩa là cứ 5 giây một lần có một khoảnh khắc nút vừa bị thay khỏi cây, và
      // cú bấm rơi đúng lúc đó thì mất.
      if (im && vet === _dauVet) return;
      _dauVet = vet;
    } catch (e) {
      if (!im) box.innerHTML = '<div class="cb-empty">Không tải được danh sách bot: ' + esc(e.message) + '</div>';
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
      '<button class="cb-loc-o' + (_kenhLoc ? "" : " on") + '" data-k="" type="button">Tất cả ' +
        '<span class="cb-loc-n">' + _bots.length + '</span></button>' +
      ks.map(function (k) {
        return '<button class="cb-loc-o' + (_kenhLoc === k ? " on" : "") + '" data-k="' + esc(k) +
          '" type="button">' + Icons.kenh(k, { size: "14px" }) + " " + esc(kenhCua(k).nhan) +
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
        '<b>Chưa có bot nào</b>' +
        '<div>Tạo một bot để Agent của bạn đứng ra trả lời người ngoài. Bot mới luôn ở trạng ' +
        'thái <b>tắt</b>, bạn tự bật sau khi đã nhắn thử.</div></div>';
      return;
    }
    if (!ds.length) { box.innerHTML = '<div class="cb-empty">Không có bot nào khớp.</div>'; return; }
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
      ? '<div class="cb-err">' + ic("triangle-alert") + ' Agent "' + esc((b.agent || {}).slug) +
        '" không còn. Bot đang trả lời mà không có hướng dẫn vai trò.</div>' : "";
    // Poller sống KHÔNG có nghĩa là bot trả lời được: model gọi hỏng thì chấm vẫn xanh trong
    // khi người hỏi nhận toàn câu xin lỗi. Lỗi lượt gần nhất phải nằm ngay trên thẻ, không bắt chủ
    // mở Nhật ký mới thấy - vì chủ chỉ mở Nhật ký khi đã NGỜ là có chuyện.
    var lluot = b.loi_luot
      ? '<div class="cb-err">' + ic("triangle-alert") + ' Lượt gần nhất LỖI: ' +
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
      suggest: " - bot chỉ đọc brain này rồi trả lời. Không ghi file, không gọi nguồn dữ liệu.",
      auto: " - bot ghi được file trong brain này và gọi được nguồn dữ liệu đã đấu.",
      full: " - bot tự gửi đi, thanh toán, đặt/huỷ, xoá được. Người điều khiển là người nhắn cho nó.",
    };
    var quyen =
      '<div class="cb-quyen ' + (mq === "full" ? "full" : mq === "auto" ? "ghi" : "doc") + '">' +
        // "shield-alert" không có trong bộ icon đã vendor nên bản trước vẽ ra một ô trống ở
        // đúng chỗ đáng chú ý nhất. Test icon không bắt được vì nó chỉ dò tên viết thẳng trong
        // lời gọi, không dò lời gọi có biểu thức ở trong.
        ic(mq === "full" ? "shield" : mq === "auto" ? "pencil" : "eye") +
        ' Mức <b>' + esc(mucCua(mq).nhan) + '</b>' + (mqLoi[mq] || "") +
      '</div>';
    // Nhóm có người gọi bot mà chủ chưa cho phép. Đây là chỗ sửa cho lỗi "thả bot vào nhóm,
    // tag tên nó, không thấy gì": hành vi từ chối vẫn đúng, nhưng nay nó nổi lên đây kèm đúng
    // một nút bấm, thay vì bắt chủ đoán rằng mình phải đi khai id nhóm ở đáy form Sửa.
    var cho = (b.nhom_cho || []).map(function (g) {
      return '<div class="cb-nhomcho" data-cid="' + esc(g.chat_id) + '">' +
        '<div class="cb-nhomcho-t">' + ic("message-circle") + ' <b>' + esc(g.ten || "Nhóm " + g.chat_id) +
          '</b> <span class="cb-nhomcho-id">' + esc(g.chat_id) + '</span></div>' +
        '<div class="cb-nhomcho-d">' + (g.lan
          ? 'Có người gọi bot ở đây ' + g.lan + ' lần mà bot chưa được bật cho nhóm này.'
          : 'Bot đang ở trong nhóm này nhưng chưa được bật cho nó.') + '</div>' +
        '<div class="cb-nhomcho-a">' +
          '<button class="s-btn cb-ok-nhom" type="button">' + ic("check") + ' Cho phép nhóm này</button>' +
          '<button class="s-btn-ghost cb-bo-nhom" type="button">Bỏ qua</button>' +
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
    var kenh = b.channel || "telegram";
    var duNhom = (b.groups || []).length || (b.nhom_cho || []).length;
    // Cảnh báo chế độ riêng tư là chuyện RIÊNG của Telegram. Hiện nó trên một thẻ Zalo là dạy
    // người dùng đi mở @BotFather tìm một cài đặt không tồn tại cho con bot đó.
    var riengTu = (kenh === "telegram" && duNhom && st.da_hoi_telegram && !st.doc_moi_tin_nhom)
      ? '<div class="cb-quyen ghi">' + ic("triangle-alert") + ' Telegram đang bật <b>chế độ riêng ' +
        'tư</b> cho bot này. Trong nhóm, thứ chắc chắn tới được nó là <b>lệnh /...</b> và <b>tin ' +
        'trả lời thẳng vào tin của nó</b>' +
        (b.reply_when === "always"
          ? '; đặt "trả lời mọi tin" cũng không có tác dụng chừng nào chế độ này còn bật'
          : '. Tag tên mà bot im thì gần như luôn là vì cái này') + '.<br>' +
        'Sửa bằng MỘT trong hai cách: mở <b>@BotFather</b> gõ <b>/setprivacy</b>, chọn bot này, ' +
        'chọn <b>Disable</b>; hoặc cho bot làm <b>quản trị viên</b> nhóm. Xong thì tắt bật lại ' +
        'bot ở đây.</div>' : "";
    var c = el(
      '<div class="cb-card">' +
        '<div class="cb-head">' +
          '<span class="cb-ico">' + ic(b.icon || "headset") +
            '<span class="cb-ico-kenh" title="' + esc(kenhCua(kenh).nhan) + '">' +
              Icons.kenh(kenh, { size: "14px" }) + '</span></span>' +
          '<span class="cb-name">' + esc(b.name) + '</span>' +
          '<span class="cb-dot ' + tt.mau + '" title="' + esc(st.last_error || tt.nhan) + '"></span>' +
          '<span class="cb-state">' + tt.nhan + '</span>' +
        '</div>' +
        // Không hiện brain trên thẻ nữa: mọi bot ở đây đều thuộc brain đang mở, nên nhắc lại
        // trên từng thẻ chỉ là nhiễu. Brain nói một lần ở đầu trang là đủ.
        '<div class="cb-meta">' +
          chipKenh(kenh) +
          (b.bot_username
            ? '<span>' + (kenh === "telegram" ? "@" : "") + esc(b.bot_username) + '</span>'
            : '<span class="cb-warn">chưa có token</span>') +
          '<span>' + ic("bot") + ' ' + esc(b.agent_name || (b.agent || {}).slug || "?") + '</span>' +
        '</div>' +
        '<div class="cb-meta">' +
          '<span>' + (!kenhCua(kenh).co_nhom ? 'chỉ tin nhắn riêng' : (b.groups || []).length
            ? ((b.groups.length + ' nhóm') + (b.reply_when === "always" ? ", trả lời mọi tin" : ", khi được gọi tên"))
            : 'chỉ tin nhắn riêng') + '</span>' +
          '<span>' + (b.nguon_tra_loi === "tai_lieu" ? "chỉ tài liệu" : "chuyên môn Agent") + '</span>' +
          '<span>' + (st.answered || 0) + ' lượt trả lời</span>' +
          (b.handoff_to ? '<span>' + ic("user") + ' có chuyển người trực</span>'
                        : '<span class="cb-warn">chưa đặt người nhận</span>') +
        '</div>' +
        cho + quyen + loiTen + riengTu + mat + lluot + cbao + loi +
        '<div class="cb-acts">' +
          '<button class="s-btn-ghost cb-toggle" type="button">' +
            (b.enabled ? ic("circle-stop") + " Tắt" : ic("play") + " Bật") + '</button>' +
          '<button class="s-btn-ghost cb-log" type="button">' + ic("history") + ' Nhật ký</button>' +
          '<button class="s-btn-ghost cb-edit" type="button">Sửa</button>' +
          '<button class="s-btn-ghost cb-del" type="button">Xoá</button>' +
        '</div>' +
      '</div>');
    c.querySelector(".cb-toggle").onclick = function () { bat(b, !b.enabled); };
    c.querySelector(".cb-log").onclick = function () { moNhatKy(b); };
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
      alert("Không cập nhật được nhóm: " + e.message);
    }
    tai();
  }

  // ---------------------------------------------------------------- nhật ký + lỗ hổng
  // Mở tab "Bot bí" TRƯỚC, không phải tab hội thoại. Hội thoại chỉ để soi lại khi nghi ngờ,
  // còn danh sách câu bot trả lời không nổi mới là thứ chủ cần LÀM GÌ ĐÓ với nó: mỗi dòng ở
  // đó là một chỗ tài liệu đang thiếu, viết bổ sung vào brain là lần sau bot trả lời được.
  async function moNhatKy(b) {
    var box = el('<div class="cb-modal"><div class="cb-form cb-log-form">' +
      '<h3>Nhật ký - ' + esc(b.name) + '</h3>' +
      '<div class="cb-tabs">' +
        '<button class="cb-tab on" data-t="gaps" type="button">Bot bí</button>' +
        '<button class="cb-tab" data-t="turns" type="button">Hội thoại gần đây</button>' +
      '</div>' +
      '<div class="cb-log-body">Đang tải…</div>' +
      '<div class="cb-form-acts"><button class="s-btn" id="cbLogClose" type="button">Đóng</button></div>' +
      '</div></div>');
    document.body.appendChild(box);
    var dong = function () { if (box.parentNode) box.parentNode.removeChild(box); };
    box.onmousedown = function (e) { if (e.target === box) dong(); };
    box.querySelector("#cbLogClose").onclick = dong;

    var than = box.querySelector(".cb-log-body"), d = null;
    try { d = await api("/chatbots/" + encodeURIComponent(b.id) + "/log?limit=60"); }
    catch (e) { than.textContent = "Không tải được nhật ký: " + e.message; return; }

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
        ? '<b>Chưa có câu nào bot bí.</b><div>' + tt.luot + ' lượt đã trả lời được hết.</div>'
        : '<b>Chưa có lượt nào.</b><div>Nhắn thử cho bot vài câu rồi quay lại đây.</div>') + '</div>';
    }
    return '<div class="cb-sum">' + tt.luot + ' lượt, ' + tt.bi + ' lượt bí (' + tt.ty_le_bi +
      '%). Mỗi dòng dưới đây là một chỗ tài liệu trong brain đang thiếu.</div>' +
      '<table class="cb-tbl"><thead><tr><th>Khách hỏi</th><th>Số lần</th><th>Gần nhất</th></tr></thead><tbody>' +
      gaps.map(function (g) {
        return '<tr><td>' + esc(g.hoi) + '</td><td class="cb-num">' + g.lan + '</td><td>' +
               esc(gio(g.lan_cuoi)) + '</td></tr>';
      }).join("") + '</tbody></table>';
  }

  function veLuot(turns) {
    if (!turns.length) return '<div class="cb-empty">Chưa có lượt nào.</div>';
    return turns.map(function (t) {
      // Nguồn hiện ra để chủ kiểm được bot lấy câu trả lời TỪ ĐÂU. Không có dòng này thì
      // "bot trả lời đúng chưa" là câu hỏi không kiểm chứng được, chỉ đoán.
      var ng = (t.nguon || []).length
        ? '<div class="cb-src">' + ic("file-text") + " " + esc(t.nguon.join(", ")) + '</div>'
        : '<div class="cb-src cb-warn">không tìm thấy tài liệu nào khớp</div>';
      // Lượt GÃY: người hỏi chỉ nhận một câu xin lỗi chung, nên đây là chỗ DUY NHẤT chủ đọc được
      // lý do thật. Thiếu nó thì "bot trả lời sai" và "bot đang hỏng" nhìn giống hệt nhau.
      if (t.loi) {
        return '<div class="cb-turn loi">' +
          '<div class="cb-turn-h">' + esc(t.user_name || t.chat_id) + ' · ' + esc(gio(t.ts)) + '</div>' +
          '<div class="cb-q">' + esc(t.hoi) + '</div>' +
          '<div class="cb-err">' + ic("triangle-alert") + ' Lượt này LỖI, không phải bot trả lời sai: ' +
          esc(t.loi) + '</div></div>';
      }
      return '<div class="cb-turn' + (t.bi ? " bi" : "") + '">' +
        '<div class="cb-turn-h">' + esc(t.user_name || t.chat_id) + ' · ' + esc(gio(t.ts)) +
        (t.chuyen_nguoi ? ' · <b>đã báo người trực</b>' : "") + '</div>' +
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
        !confirm('Bật bot "' + b.name + '" ở mức ' + mucCua(mq).nhan + '?\n\n' +
                 (mq === "full"
                   ? "Từ lúc này ai nhắn cho bot cũng có thể khiến nó gửi đi, thanh toán, "
                     + "đặt/huỷ, xoá hoặc công bố ra ngoài. Không hoàn tác được."
                   : "Từ lúc này bot ghi được file trong brain của nó và gọi được các nguồn dữ "
                     + "liệu bạn đã đấu, theo lời người nhắn."))) return;
    try {
      await api("/chatbots/" + encodeURIComponent(b.id) + "/enable",
                { method: "POST", body: fd({ on: on ? "1" : "0" }) });
    } catch (e) {
      alert("Không " + (on ? "bật" : "tắt") + " được: " + e.message);
    }
    tai();
  }

  async function xoa(b) {
    // Nói rõ cái gì MẤT và cái gì CÒN. Người dùng không đoán được hậu quả thì đừng bắt họ gánh.
    if (!confirm('Xoá bot "' + b.name + '"?\n\n' +
                 'Bot ngừng trả lời ngay. Brain và Agent của nó KHÔNG bị xoá.')) return;
    try { await api("/chatbots/" + encodeURIComponent(b.id) + "/delete", { method: "POST" }); }
    catch (e) { alert("Không xoá được: " + e.message); }
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
                     : '<option value="">(brain này chưa có Agent nào)</option>';
  }

  // Mô tả một dòng cho mỗi mức, hiện ngay trong ô chọn. Cảnh báo ĐẦY ĐỦ nằm ở khối dưới và do
  // server cấp; ba dòng này chỉ để chọn cho đúng ngay từ đầu.
  var MUC_TOM = {
    suggest: "Chỉ đọc - bot chỉ trả lời, không đụng được gì (mặc định)",
    auto: "Được ghi - ghi file trong brain này + gọi nguồn dữ liệu, KHÔNG thao tác ra ngoài",
    full: "Toàn quyền - làm được mọi thứ, kể cả gửi đi, thanh toán, đặt/huỷ, xoá",
  };

  // Danh sách ngôn ngữ lấy từ /settings (sổ đăng ký phía server), KHÔNG khai lại ở đây.

  // Khai hai nơi thì thêm ngôn ngữ mới phải nhớ sửa cả hai chỗ.

  var _langDS = [];

  function htmlNgonNgu(cur) {

    var ra = '<option value="auto"' + (cur === "auto" || !cur ? " selected" : "") +

             '>Tự động theo khách</option>';

    _langDS.forEach(function (l) {

      ra += '<option value="' + esc(l.ma) + '"' + (l.ma === cur ? " selected" : "") +

            '>' + esc(l.ten) + '</option>';

    });

    return ra;

  }


  function htmlMuc(dangChon) {
    var ds = _mucDS.length ? _mucDS : [{ id: "suggest", nhan: "Chỉ đọc" }];
    return ds.map(function (m) {
      return '<option value="' + esc(m.id) + '"' + (m.id === dangChon ? " selected" : "") + '>' +
             esc(MUC_TOM[m.id] || m.nhan) + '</option>';
    }).join("");
  }

  // Khối cảnh báo dựng từ danh sách câu SERVER trả về. Mức chỉ đọc không có câu nào, và đúng
  // như vậy: nó không lấy đi thứ gì để mà cảnh báo.
  function veCanhBao(id) {
    var m = mucCua(id);
    if (!(m.canh_bao || []).length) {
      return '<div class="cb-hint">Bot chỉ đọc tài liệu trong brain này rồi trả lời. Không ghi ' +
             'file, không gọi nguồn dữ liệu, không thao tác gì ra ngoài. An toàn nhất khi bot ' +
             'nói chuyện với người lạ.</div>';
    }
    return '<div class="cb-canhbao ' + (id === "full" ? "full" : "ghi") + '">' +
      '<div class="cb-canhbao-h">' + ic("triangle-alert") + ' Bật mức <b>' + esc(m.nhan) +
      '</b> nghĩa là:</div><ul>' +
      m.canh_bao.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") +
      '</ul><label class="cb-ack"><input type="checkbox" id="cbAck"> Tôi đã đọc và chấp nhận ' +
      'rủi ro trên</label></div>';
  }

  // Một dòng nói ĐÚNG cái người ta cần cân nhắc khi chọn kênh: ai sẽ nhắn cho bot, và kênh
  // đó KHÔNG làm được gì. Ưu nhược điểm phải nằm ngay trên nút bấm, không phải trong tài liệu.
  var KENH_TOM = {
    telegram: "Vào được nhóm, gửi được ảnh và tài liệu. Người Việt ít dùng.",
    zalo: "Khách Việt Nam đã có sẵn trên máy. Chỉ chat riêng, chưa gửi được tài liệu.",
  };

  function veKenhChon(dangChon, khoa) {
    var ds = _kenhDS.length ? _kenhDS : [{ id: "telegram", nhan: "Telegram" }, { id: "zalo", nhan: "Zalo" }];
    if (khoa) {
      // Đổi kênh của một bot đã tạo là đổi sang một CON BOT KHÁC (token khác, danh tính khác,
      // khách khác). Khoá lại và nói thẳng, chứ đừng cho bấm rồi báo lỗi token ở bước sau.
      return '<div class="cb-kenh-khoa">' + Icons.kenh(dangChon, { size: "18px" }) +
        ' <b>' + esc(kenhCua(dangChon).nhan) + '</b>' +
        '<span>Không đổi được kênh của bot đã tạo. Cần kênh khác thì tạo bot mới.</span></div>';
    }
    return '<div class="cb-kenh">' + ds.map(function (k) {
      return '<button class="cb-kenh-o' + (k.id === dangChon ? " on" : "") + '" data-k="' +
        esc(k.id) + '" type="button">' +
        '<span class="cb-kenh-logo">' + Icons.kenh(k.id, { size: "26px" }) + '</span>' +
        '<b>' + esc(k.nhan) + '</b>' +
        '<small>' + esc(KENH_TOM[k.id] || "") + '</small></button>';
    }).join("") + '</div>';
  }

  async function moForm(b) {
    var sua = !!b;
    var br = brain();                 // brain đang mở = brain của bot, không hỏi lại
    var agents = await nạpAgent(br);
    var kenh = (b && b.channel) || "telegram";
    var box = el(
      '<div class="cb-modal"><div class="cb-form">' +
        '<h3>' + (sua ? "Sửa bot" : "Bot mới") + '</h3>' +

        // Kênh đứng ĐẦU vì nó quyết định mọi thứ phía dưới: token lấy ở đâu, có dùng được
        // nhóm không, có gửi được tài liệu không. Hỏi sau cùng thì người dùng đã điền xong cả
        // form rồi mới biết mình chọn nhầm chỗ.
        '<label>Bot này nói chuyện ở đâu</label>' +
        '<div id="cbKenhBox">' + veKenhChon(kenh, sua) + '</div>' +

        '<label>Tên bot</label>' +
        '<input id="cbName" value="' + esc(b ? b.name : "") + '" placeholder="Ví dụ: Tư vấn sản phẩm">' +

        '<label>Agent làm bộ não</label>' +
        '<div class="cb-row">' +
          '<select id="cbAgent">' + htmlAgent(agents, (b && (b.agent || {}).slug) || "") + '</select>' +
          '<button class="s-btn-ghost" id="cbNewAgent" type="button">' + ic("plus") + ' Tạo Agent</button>' +
        '</div>' +
        '<div class="cb-hint">Agent trong brain <b>' + esc(br) + '</b>. Bot đọc tài liệu của ' +
        'chính brain này để trả lời. Sửa Agent là bot đổi theo ngay, không phải sửa hai chỗ. Bấm ' +
        '<b>Tạo Agent</b> để sang trang Agents, tạo xong quay lại đây chọn.</div>' +

        // Lựa chọn này quyết định bot "ăn nhập với Agent" hay không, nên đặt ngay dưới brain
        // chứ không giấu ở cuối form: nó là thứ người dùng cần hiểu TRƯỚC khi bấm tạo.
        '<label>Bot trả lời dựa trên gì</label>' +
        '<select id="cbNguon">' +
          '<option value="agent"' + (!b || b.nguon_tra_loi !== "tai_lieu" ? " selected" : "") + '>' +
            'Chuyên môn của Agent + tài liệu (mặc định)</option>' +
          '<option value="tai_lieu"' + (b && b.nguon_tra_loi === "tai_lieu" ? " selected" : "") + '>' +
            'CHỈ tài liệu trong brain</option>' +
        '</select>' +
        '<div class="cb-hint"><b>Chuyên môn của Agent</b>: bot làm đúng theo quy định bạn viết ' +
        'trong file Agent, tài liệu tra được là phần bổ sung. Javis không thêm luật nào của ' +
        'mình vào.<br>' +
        '<b>Chỉ tài liệu</b>: thêm một luật duy nhất là không tìm thấy tài liệu thì nói chưa ' +
        'có thông tin, không tự nói thêm. Hợp với bot đọc giá và chính sách, nơi một câu sai ' +
        'là thiệt hại thật.</div>' +

        // Đặt NGAY sau "trả lời dựa trên gì" và trước token: đây là quyết định nặng nhất trong
        // cả form, phải đọc trước khi bấm tạo chứ không phải một ô giấu ở cuối.
        '<label>Bot được làm gì</label>' +
        '<select id="cbMuc">' + htmlMuc((b && b.muc_quyen) || "suggest") + '</select>' +
        '<div class="cb-muc-note">' + veCanhBao((b && b.muc_quyen) || "suggest") + '</div>' +

        // Ngôn ngữ của bot ĐỘC LẬP với ngôn ngữ của chủ, và đó là cả lý do ô này tồn tại:
        // bot nói chuyện với NGƯỜI NGOÀI, không phải với chủ. Chủ dùng Javis bằng tiếng Việt
        // mà người nhắn cho bot lại nói tiếng khác là chuyện bình thường, nên lấy ngôn ngữ
        // của chủ suy ra ngôn ngữ của bot là suy sai.
        '<label>Bot trả lời khách bằng tiếng gì</label>' +
        '<select id="cbNgonNgu">' + htmlNgonNgu((b && b.ngon_ngu) || "auto") + '</select>' +
        '<div class="cb-muc-note">Tự động = bám theo thứ tiếng khách nhắn tới. ' +
          'Ghim một ngôn ngữ khi người nhắn tới đều dùng chung một thứ tiếng.</div>' +

        '<label id="cbTokenLabel">Token ' + esc(kenhCua(kenh).nhan) +
          (sua ? " (để trống nếu không đổi)" : "") + '</label>' +
        '<div class="cb-row">' +
          '<input id="cbToken" type="password" placeholder="Dạng 123456789:AbC-xyz">' +
          '<button class="s-btn-ghost" id="cbCheck" type="button">Kiểm tra</button>' +
        '</div>' +
        '<div class="cb-hint" id="cbTokenNote">' +
          (b && b.bot_username
            ? "Đang dùng " + (kenh === "telegram" ? "@" : "") + esc(b.bot_username)
            : esc(kenhCua(kenh).lay_token) +
              " Mỗi bot phải một token RIÊNG.") +
        '</div>' +

        '<label>Chat ID người trực nhận chuyển tiếp</label>' +
        '<input id="cbHandoff" value="' + esc(b ? (b.handoff_to || "") : "") + '" placeholder="Ví dụ: 123456789">' +
        '<div class="cb-hint">Bot bí <b>hai câu liên tiếp</b> với cùng một người thì nhắn vào ' +
        'đây, và người đang hỏi gõ /nhanvien thì báo ngay. Bí một câu lẻ không gọi - báo mọi câu ' +
        'vu vơ thì vài lần là người trực tắt thông báo.<br>' +
        'Bỏ trống thì bot <b>vẫn trả lời bình thường</b> theo Agent, chỉ là không có ai để ' +
        'chuyển tiếp. Muốn nó im khi thiếu căn cứ thì chọn chế độ <b>Chỉ tài liệu</b> ở trên.</div>' +

        // Khai được NGAY LÚC TẠO, không chỉ ở form Sửa. Đường đi tự nhiên nhất là tạo bot rồi
        // thả thẳng vào nhóm; bắt quay lại bấm Sửa mới khai được nhóm là bảo đảm lần thử đầu
        // tiên của mọi người dùng đều gặp một con bot im lặng.
        // Cả khối nhóm ẩn đi với kênh không vào được nhóm. Hiện ra rồi để nó không có tác dụng
        // là hứa suông: người dùng ngồi khai id nhóm xong chờ mãi một con bot không bao giờ
        // vào được nhóm nào, và không có gì nói cho họ biết.
        '<div id="cbNhomBox">' +
          '<label>Nhóm được phép (mỗi id một dòng)</label>' +
          '<textarea id="cbGroups" rows="2" placeholder="Ví dụ: -1001234567890">' +
            esc(((b && b.groups) || []).join("\n")) + '</textarea>' +
          '<div class="cb-hint">Bỏ trống thì bot <b>chỉ trả lời tin nhắn riêng</b>, trong nhóm nó ' +
          'im. Không cần chép tay: mời bot vào nhóm rồi nhắn cho nó một câu, nhóm đó sẽ hiện trên ' +
          'thẻ bot ở trang này kèm nút <b>Cho phép</b>. Hoặc gõ <b>/id</b> trong nhóm để lấy id ' +
          'rồi dán vào đây.</div>' +

          '<label>Trong nhóm thì khi nào bot lên tiếng</label>' +
          '<select id="cbReplyWhen">' +
            '<option value="mention"' + (!b || b.reply_when !== "always" ? " selected" : "") + '>' +
              'Chỉ khi được gọi tên hoặc trả lời vào nó (mặc định)</option>' +
            '<option value="always"' + (b && b.reply_when === "always" ? " selected" : "") + '>' +
              'Mọi tin trong nhóm đã cho phép</option>' +
          '</select>' +
          '<div class="cb-hint"><b>Mọi tin</b> chỉ hợp với nhóm nhỏ, và còn phải tắt chế độ riêng ' +
          'tư ở @BotFather (<b>/setprivacy</b> → Disable) thì Telegram mới chuyển hết tin cho bot. ' +
          'Bot chen vào mọi câu khách nói với nhau thì phiền hơn là giúp.</div>' +
        '</div>' +
        '<div class="cb-hint cb-khong-nhom" id="cbKhongNhom" style="display:none">' +
          'Bot Zalo <b>chỉ trả lời tin nhắn riêng</b>. Gói bot cơ bản của Zalo không cho bot vào ' +
          'nhóm, và Zalo cũng chưa có API gửi tài liệu nên file Javis tạo ra sẽ không gửi qua ' +
          'kênh này được (ảnh thì đang thử).</div>' +

        '<div class="cb-form-acts">' +
          '<button class="s-btn-ghost" id="cbCancel" type="button">Huỷ</button>' +
          '<button class="s-btn" id="cbSave" type="button">' + (sua ? "Lưu" : "Tạo bot") + '</button>' +
        '</div>' +
        (sua ? "" : '<div class="cb-hint">Bot tạo ra ở trạng thái <b>TẮT</b>. Nhắn thử riêng cho ' +
                    'nó trước, thấy ổn rồi mới bật.</div>') +
      '</div></div>');

    document.body.appendChild(box);
    var dong = function () { if (box.parentNode) box.parentNode.removeChild(box); };
    box.onmousedown = function (e) { if (e.target === box) dong(); };
    box.querySelector("#cbCancel").onclick = dong;

    // Sang thẳng trang Agents. Đóng form trước để quay lại không bị hai lớp modal chồng nhau.
    box.querySelector("#cbNewAgent").onclick = function () {
      dong();
      try { window.JavisNav.go("agents"); } catch (e) {}
    };

    // Đổi mức là vẽ lại cảnh báo NGAY, và ô đồng ý luôn bắt đầu ở trạng thái chưa tick. Giữ
    // lại tick cũ khi đổi từ "Được ghi" sang "Toàn quyền" là để chủ đồng ý với một danh sách
    // rủi ro mà họ chưa đọc.
    var oMuc = box.querySelector("#cbMuc");
    var oNote = box.querySelector(".cb-muc-note");
    oMuc.onchange = function () { oNote.innerHTML = veCanhBao(oMuc.value); };

    var uname = (b && b.bot_username) || "";

    // Đổi kênh là đổi CẢ form theo: nhãn token, chỗ lấy token, và khối nhóm còn dùng được hay
    // không. Token đã kiểm cũng phải bỏ đi - nó là danh tính ở nền tảng KIA, giữ lại thì lưu
    // xong bản ghi mang tên một con bot không tồn tại trên kênh vừa chọn.
    function apKenh(k) {
      // Chỉ bỏ token đã kiểm khi kênh THẬT SỰ đổi. Hàm này còn được gọi một lần lúc mở form
      // để dựng đúng trạng thái ban đầu; bỏ vô điều kiện thì mở form Sửa rồi bấm Lưu là xoá
      // trắng tên bot đang chạy, và thẻ quay ra báo "chưa có token" cho một con bot vẫn sống.
      if (k !== kenh) uname = "";
      kenh = k;
      var kc = kenhCua(k);
      var lb = box.querySelector("#cbTokenLabel");
      if (lb) lb.textContent = "Token " + kc.nhan + (sua ? " (để trống nếu không đổi)" : "");
      var note = box.querySelector("#cbTokenNote");
      // Giữ nguyên dòng "Đang dùng <tên bot>" khi mở form Sửa mà chưa đổi gì.
      if (note && !(sua && k === ((b && b.channel) || "telegram") && uname)) {
        note.textContent = kc.lay_token + " Mỗi bot phải một token RIÊNG.";
      }
      var nhomBox = box.querySelector("#cbNhomBox");
      var khong = box.querySelector("#cbKhongNhom");
      if (nhomBox) nhomBox.style.display = kc.co_nhom ? "" : "none";
      if (khong) khong.style.display = kc.co_nhom ? "none" : "";
      box.querySelectorAll(".cb-kenh-o").forEach(function (n) {
        n.classList.toggle("on", n.dataset.k === k);
      });
    }
    box.querySelectorAll(".cb-kenh-o").forEach(function (n) {
      n.onclick = function () { apKenh(n.dataset.k); };
    });
    apKenh(kenh);

    box.querySelector("#cbCheck").onclick = async function () {
      var t = box.querySelector("#cbToken").value.trim();
      var note = box.querySelector("#cbTokenNote");
      var kc = kenhCua(kenh);
      if (!t) { note.textContent = "Dán token vào đã."; return; }
      note.textContent = "Đang hỏi " + kc.nhan + "…";
      try {
        var r = await api("/chatbots/verify-token", {
          method: "POST",
          body: fd({ token: t, bot_id: (b && b.id) || "", channel: kenh }),
        });
        uname = r.username || "";
        note.innerHTML = ic("check", { cls: "ic-ok" }) + " Đúng bot <b>" +
          (kenh === "telegram" ? "@" : "") + esc(uname) + "</b> (" + esc(r.bot_name || "") + ")" +
          // Gói bot Zalo cơ bản không vào được nhóm. Nói NGAY tại đây, lúc người dùng còn đang
          // nhìn vào token, chứ không để họ phát hiện ra sau vài ngày bot im trong nhóm.
          (r.vao_duoc_nhom === false
            ? '<br><span class="cb-warn">Bot này không vào được nhóm Zalo (gói ' +
              esc(r.account_type || "cơ bản") + '), nên nó chỉ trả lời tin nhắn riêng.</span>'
            : "");
      } catch (e) { note.innerHTML = '<span class="cb-warn">' + esc(e.message) + '</span>'; }
    };

    box.querySelector("#cbSave").onclick = async function () {
      var ten = box.querySelector("#cbName").value.trim();
      var ag = box.querySelector("#cbAgent").value;
      var tok = box.querySelector("#cbToken").value.trim();
      var ho = box.querySelector("#cbHandoff").value.trim();
      var ngu = box.querySelector("#cbNguon").value;
      var muc = oMuc.value;
      var ack = box.querySelector("#cbAck");
      if (!ten) return alert("Nhập tên bot");
      if (!ag) return alert("Chọn Agent làm bộ não cho bot. Brain này chưa có Agent nào thì "
                            + "bấm Tạo Agent để tạo trước.");
      // Hai lớp, cố ý: ô tick ở đây để chủ ĐỌC, và server vẫn tự chặn lần nữa (can_force) nên
      // gỡ ô này bằng devtools cũng không nâng được quyền.
      if (mucCua(muc).can_xac_nhan && !(ack && ack.checked)) {
        return alert("Mức \"" + mucCua(muc).nhan + "\" cho bot làm việc thật ra ngoài, do "
                     + "người lạ điều khiển.\n\nĐọc phần rủi ro rồi tick vào ô đồng ý bên dưới "
                     + "ô chọn mức thì mới lưu được.");
      }
      if (muc === "full" &&
          !confirm("Bot \"" + ten + "\" sẽ chạy ở mức TOÀN QUYỀN.\n\n"
                   + "Ai nhắn cho bot cũng có thể khiến nó gửi đi, thanh toán, đặt hoặc huỷ, "
                   + "xoá, công bố ra ngoài. Những thao tác đó không hoàn tác được, và bot "
                   + "không hỏi lại bạn trước khi làm.\n\nChỉ nên dùng khi bạn kiểm soát được "
                   + "danh sách người nhắn vào. Vẫn muốn đặt mức này?")) return;
      // Kênh không dùng nhóm thì gửi rỗng, đừng gửi thứ người dùng gõ từ lúc còn chọn kênh
      // khác: bản ghi mang một danh sách nhóm không bao giờ dùng tới là một lời hứa suông
      // nằm lại trong dữ liệu.
      var coNhom = kenhCua(kenh).co_nhom;
      var gr = coNhom ? box.querySelector("#cbGroups").value : "";
      var rw = coNhom ? box.querySelector("#cbReplyWhen").value : "mention";
      try {
        if (sua) {
          await api("/chatbots/" + encodeURIComponent(b.id) + "/update", {
            method: "POST",
            body: fd({ name: ten, agent_slug: ag, agent_brain: br, brain: br,
                       handoff_to: ho, token: tok, bot_username: uname, nguon_tra_loi: ngu,
                       muc_quyen: muc, xac_nhan_rui_ro: "1",
                       ngon_ngu: (document.getElementById("cbNgonNgu") || {}).value || "auto",
                       groups: gr, reply_when: rw }),
          });
        } else {
          if (!tok) return alert("Dán token " + kenhCua(kenh).nhan + " của bot.\n\n" +
                                 kenhCua(kenh).lay_token);
          await api("/chatbots", {
            method: "POST",
            body: fd({ name: ten, agent_slug: ag, agent_brain: br, brain: br,
                       token: tok, bot_username: uname, handoff_to: ho, nguon_tra_loi: ngu,
                       muc_quyen: muc, xac_nhan_rui_ro: "1", channel: kenh,
                       groups: gr, reply_when: rw }),
          });
        }
      } catch (e) { return alert("Không lưu được: " + e.message); }
      dong();
      tai();
    };
  }

  window.JavisChatbots = { render: render };
})();
