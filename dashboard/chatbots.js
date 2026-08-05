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
  var _bots = [], _q = "", _host = null, _mucDS = [];

  function mucCua(id) {
    for (var i = 0; i < _mucDS.length; i++) if (_mucDS[i].id === id) return _mucDS[i];
    return { id: id || "suggest", nhan: "Chỉ đọc", canh_bao: [], can_xac_nhan: false };
  }

  function render(host) {
    _host = host;
    host.innerHTML =
      '<div class="cview-section cb-wrap">' +
        '<div class="cb-bar">' +
          '<input class="cb-search" placeholder="Tìm bot theo tên…">' +
          '<button class="s-btn cb-new" type="button">' + ic("plus") + ' Bot mới</button>' +
        '</div>' +
        '<p class="cb-intro">Bot của brain <b>' + esc(brain()) + '</b>. Mỗi bot là một ' +
        '<b>Agent</b> trong brain này, đem ra trả lời người ngoài qua một bot Telegram riêng. ' +
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
  }

  async function tai() {
    var box = _host && _host.querySelector(".cb-grid");
    if (!box) return;
    box.innerHTML = '<div class="cb-empty">Đang tải…</div>';
    try {
      // Lọc theo brain đang mở: trang này thuộc về một brain, y như trang Agents và Skills.
      // console.js tự gọi lại renderPage khi đổi brain nên không cần lắng nghe gì thêm.
      var d = await api("/chatbots?brain=" + encodeURIComponent(brain()));
      _bots = d.bots || [];
      _mucDS = d.muc_quyen || [];
    } catch (e) {
      box.innerHTML = '<div class="cb-empty">Không tải được danh sách bot: ' + esc(e.message) + '</div>';
      return;
    }
    ve();
  }

  function ve() {
    var box = _host && _host.querySelector(".cb-grid");
    if (!box) return;
    var ds = _bots.filter(function (b) {
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
    var mq = b.muc_quyen || "suggest";
    var quyen = mq === "suggest" ? "" :
      '<div class="cb-quyen ' + (mq === "full" ? "full" : "ghi") + '">' +
        ic(mq === "full" ? "shield-alert" : "pencil") + ' Mức <b>' + esc(mucCua(mq).nhan) +
        '</b>' + (mq === "full"
          ? ' - bot tự gửi đi, thanh toán, đặt/huỷ, xoá được. Người điều khiển là người nhắn cho nó.'
          : ' - bot ghi được file trong brain này và gọi được nguồn dữ liệu đã đấu.') +
      '</div>';
    var c = el(
      '<div class="cb-card">' +
        '<div class="cb-head">' +
          '<span class="cb-ico">' + ic(b.icon || "headset") + '</span>' +
          '<span class="cb-name">' + esc(b.name) + '</span>' +
          '<span class="cb-dot ' + tt.mau + '" title="' + esc(st.last_error || tt.nhan) + '"></span>' +
          '<span class="cb-state">' + tt.nhan + '</span>' +
        '</div>' +
        // Không hiện brain trên thẻ nữa: mọi bot ở đây đều thuộc brain đang mở, nên nhắc lại
        // trên từng thẻ chỉ là nhiễu. Brain nói một lần ở đầu trang là đủ.
        '<div class="cb-meta">' +
          (b.bot_username ? '<span>@' + esc(b.bot_username) + '</span>' : '<span class="cb-warn">chưa có token</span>') +
          '<span>' + ic("bot") + ' ' + esc(b.agent_name || (b.agent || {}).slug || "?") + '</span>' +
        '</div>' +
        '<div class="cb-meta">' +
          '<span>' + ((b.groups || []).length ? (b.groups.length + ' nhóm') : 'chỉ tin nhắn riêng') + '</span>' +
          '<span>' + (b.nguon_tra_loi === "tai_lieu" ? "chỉ tài liệu" : "chuyên môn Agent") + '</span>' +
          '<span>' + (st.answered || 0) + ' lượt trả lời</span>' +
          (b.handoff_to ? '<span>' + ic("user") + ' có chuyển người trực</span>'
                        : '<span class="cb-warn">chưa đặt người nhận</span>') +
        '</div>' +
        quyen + mat + lluot + cbao + loi +
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
    return c;
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
    try { return new Date(ts * 1000).toLocaleString("vi-VN"); } catch (e) { return ""; }
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

  async function moForm(b) {
    var sua = !!b;
    var br = brain();                 // brain đang mở = brain của bot, không hỏi lại
    var agents = await nạpAgent(br);
    var box = el(
      '<div class="cb-modal"><div class="cb-form">' +
        '<h3>' + (sua ? "Sửa bot" : "Bot mới") + '</h3>' +

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

        '<label>Token Telegram' + (sua ? " (để trống nếu không đổi)" : "") + '</label>' +
        '<div class="cb-row">' +
          '<input id="cbToken" type="password" placeholder="Lấy từ @BotFather, dạng 123456:AA...">' +
          '<button class="s-btn-ghost" id="cbCheck" type="button">Kiểm tra</button>' +
        '</div>' +
        '<div class="cb-hint" id="cbTokenNote">' +
          (b && b.bot_username ? "Đang dùng @" + esc(b.bot_username) : "Mỗi bot phải một token RIÊNG. Đừng dùng token bot chính của bạn.") +
        '</div>' +

        '<label>Chat ID người trực nhận chuyển tiếp</label>' +
        '<input id="cbHandoff" value="' + esc(b ? (b.handoff_to || "") : "") + '" placeholder="Ví dụ: 123456789">' +
        '<div class="cb-hint">Bot bí <b>hai câu liên tiếp</b> với cùng một người thì nhắn vào ' +
        'đây, và người đang hỏi gõ /nhanvien thì báo ngay. Bí một câu lẻ không gọi - báo mọi câu ' +
        'vu vơ thì vài lần là người trực tắt thông báo.<br>' +
        'Bỏ trống thì bot <b>vẫn trả lời bình thường</b> theo Agent, chỉ là không có ai để ' +
        'chuyển tiếp. Muốn nó im khi thiếu căn cứ thì chọn chế độ <b>Chỉ tài liệu</b> ở trên.</div>' +

        (sua ? '<label>Nhóm được phép (mỗi id một dòng, mời bot vào nhóm rồi gõ /id để lấy)</label>' +
               '<textarea id="cbGroups" rows="2">' + esc((b.groups || []).join("\n")) + '</textarea>' : "") +

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
    box.querySelector("#cbCheck").onclick = async function () {
      var t = box.querySelector("#cbToken").value.trim();
      var note = box.querySelector("#cbTokenNote");
      if (!t) { note.textContent = "Dán token vào đã."; return; }
      note.textContent = "Đang hỏi Telegram…";
      try {
        var r = await api("/chatbots/verify-token",
                          { method: "POST", body: fd({ token: t, bot_id: (b && b.id) || "" }) });
        uname = r.username || "";
        note.innerHTML = ic("check", { cls: "ic-ok" }) + " Đúng bot <b>@" + esc(uname) + "</b> (" + esc(r.bot_name || "") + ")";
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
      try {
        if (sua) {
          var gr = box.querySelector("#cbGroups");
          await api("/chatbots/" + encodeURIComponent(b.id) + "/update", {
            method: "POST",
            body: fd({ name: ten, agent_slug: ag, agent_brain: br, brain: br,
                       handoff_to: ho, token: tok, bot_username: uname, nguon_tra_loi: ngu,
                       muc_quyen: muc, xac_nhan_rui_ro: "1",
                       groups: gr ? gr.value : undefined }),
          });
        } else {
          if (!tok) return alert("Dán token Telegram của bot (lấy ở @BotFather)");
          await api("/chatbots", {
            method: "POST",
            body: fd({ name: ten, agent_slug: ag, agent_brain: br, brain: br,
                       token: tok, bot_username: uname, handoff_to: ho, nguon_tra_loi: ngu,
                       muc_quyen: muc, xac_nhan_rui_ro: "1" }),
          });
        }
      } catch (e) { return alert("Không lưu được: " + e.message); }
      dong();
      tai();
    };
  }

  window.JavisChatbots = { render: render };
})();
