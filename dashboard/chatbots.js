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
  // khách phàn nàn, nên lỗi phải là một ô màu nhìn thấy được chứ không phải sự vắng mặt.
  var TRANG_THAI = {
    running:  { nhan: "Đang chạy", mau: "ok" },
    starting: { nhan: "Đang khởi động", mau: "wait" },
    error:    { nhan: "Lỗi", mau: "err" },
    off:      { nhan: "Đã tắt", mau: "off" },
  };

  var _bots = [], _q = "", _host = null;

  function render(host) {
    _host = host;
    host.innerHTML =
      '<div class="cview-section cb-wrap">' +
        '<div class="cb-bar">' +
          '<input class="cb-search" placeholder="Tìm bot theo tên…">' +
          '<button class="s-btn cb-new" type="button">' + ic("plus") + ' Bot mới</button>' +
        '</div>' +
        '<p class="cb-intro">Mỗi bot là một <b>Agent</b> bạn đã tạo, đem ra trả lời khách qua ' +
        'một bot Telegram riêng và một <b>brain riêng</b>. Bot chỉ <b>đọc</b> brain của nó, ' +
        'không ghi được gì, không gọi được nguồn dữ liệu nào, và không có lệnh quản trị.</p>' +
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
      var d = await api("/chatbots");
      _bots = d.bots || [];
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
        '<div>Tạo một bot để Agent của bạn đứng ra trả lời khách. Bot mới luôn ở trạng thái ' +
        '<b>tắt</b>, bạn tự bật sau khi đã nhắn thử.</div></div>';
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
    var c = el(
      '<div class="cb-card">' +
        '<div class="cb-head">' +
          '<span class="cb-ico">' + ic(b.icon || "headset") + '</span>' +
          '<span class="cb-name">' + esc(b.name) + '</span>' +
          '<span class="cb-dot ' + tt.mau + '" title="' + esc(st.last_error || tt.nhan) + '"></span>' +
          '<span class="cb-state">' + tt.nhan + '</span>' +
        '</div>' +
        '<div class="cb-meta">' +
          (b.bot_username ? '<span>@' + esc(b.bot_username) + '</span>' : '<span class="cb-warn">chưa có token</span>') +
          '<span>' + ic("bot") + ' ' + esc(b.agent_name || (b.agent || {}).slug || "?") + '</span>' +
          '<span>' + ic("brain") + ' ' + esc(b.brain) + '</span>' +
        '</div>' +
        '<div class="cb-meta">' +
          '<span>' + ((b.groups || []).length ? (b.groups.length + ' nhóm') : 'chỉ tin nhắn riêng') + '</span>' +
          '<span>' + (b.nguon_tra_loi === "tai_lieu" ? "chỉ tài liệu" : "chuyên môn Agent") + '</span>' +
          '<span>' + (st.answered || 0) + ' lượt trả lời</span>' +
          (b.handoff_to ? '<span>' + ic("user") + ' có chuyển nhân viên</span>'
                        : '<span class="cb-warn">chưa đặt người nhận</span>') +
        '</div>' +
        mat + loi +
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
      return '<div class="cb-turn' + (t.bi ? " bi" : "") + '">' +
        '<div class="cb-turn-h">' + esc(t.user_name || t.chat_id) + ' · ' + esc(gio(t.ts)) +
        (t.chuyen_nguoi ? ' · <b>đã báo nhân viên</b>' : "") + '</div>' +
        '<div class="cb-q">' + esc(t.hoi) + '</div>' +
        '<div class="cb-a">' + esc(t.dap) + '</div>' + ng + '</div>';
    }).join("");
  }

  async function bat(b, on) {
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
                 'Bot ngừng trả lời ngay. Brain "' + b.brain + '" và Agent của nó KHÔNG bị xoá.')) return;
    try { await api("/chatbots/" + encodeURIComponent(b.id) + "/delete", { method: "POST" }); }
    catch (e) { alert("Không xoá được: " + e.message); }
    tai();
  }

  // ---------------------------------------------------------------- form tạo / sửa
  async function moForm(b) {
    var sua = !!b;
    var agents = [], brains = [];
    try {
      var ad = await api("/agents?brain=" + encodeURIComponent(brain()));
      agents = ad.agents || [];
    } catch (e) {}
    try {
      var bd = await api("/brains");
      brains = (bd.brains || []).map(function (x) { return typeof x === "string" ? x : (x.name || x.path); });
    } catch (e) {}

    var goiY = "bot-" + String((b && b.name) || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    var box = el(
      '<div class="cb-modal"><div class="cb-form">' +
        '<h3>' + (sua ? "Sửa bot" : "Bot mới") + '</h3>' +

        '<label>Tên bot</label>' +
        '<input id="cbName" value="' + esc(b ? b.name : "") + '" placeholder="Ví dụ: Tư vấn sản phẩm">' +

        '<label>Agent làm bộ não</label>' +
        '<select id="cbAgent">' +
          (agents.length
            ? agents.map(function (a) {
                var sel = b && (b.agent || {}).slug === a.slug ? " selected" : "";
                return '<option value="' + esc(a.slug) + '"' + sel + '>' + esc(a.name) +
                       (a.role ? " - " + esc(String(a.role).slice(0, 50)) : "") + '</option>';
              }).join("")
            : '<option value="">(brain này chưa có Agent nào)</option>') +
        '</select>' +
        '<div class="cb-hint">Chưa có Agent phù hợp? Tạo ở trang <b>Agents</b> rồi quay lại đây ' +
        'chọn. Sửa Agent là bot đổi theo ngay, không phải sửa hai chỗ.</div>' +

        '<label>Brain riêng của bot</label>' +
        '<div class="cb-row">' +
          '<select id="cbBrain">' +
            (b ? '<option value="' + esc(b.brain) + '" selected>' + esc(b.brain) + '</option>' : "") +
            brains.filter(function (x) { return !b || x !== b.brain; })
                  .map(function (x) { return '<option value="' + esc(x) + '">' + esc(x) + '</option>'; }).join("") +
          '</select>' +
          (sua ? "" : '<button class="s-btn-ghost" id="cbNewBrain" type="button">' + ic("plus") + ' Tạo brain mới</button>') +
        '</div>' +
        '<div class="cb-hint">Bot đọc tài liệu trong brain này để trả lời. Nên dùng một brain ' +
        'riêng chứa đúng tài liệu người ngoài được xem, đừng trỏ vào brain chính của bạn.</div>' +

        // Lựa chọn này quyết định bot "ăn nhập với Agent" hay không, nên đặt ngay dưới brain
        // chứ không giấu ở cuối form: nó là thứ người dùng cần hiểu TRƯỚC khi bấm tạo.
        '<label>Bot trả lời dựa trên gì</label>' +
        '<select id="cbNguon">' +
          '<option value="agent"' + (!b || b.nguon_tra_loi !== "tai_lieu" ? " selected" : "") + '>' +
            'Chuyên môn của Agent + tài liệu (mặc định)</option>' +
          '<option value="tai_lieu"' + (b && b.nguon_tra_loi === "tai_lieu" ? " selected" : "") + '>' +
            'CHỈ tài liệu trong brain</option>' +
        '</select>' +
        '<div class="cb-hint"><b>Chuyên môn của Agent</b>: bot trả lời như chính Agent bạn chọn, ' +
        'tài liệu là phần bổ sung. Hợp với bot tư vấn, coach, đào tạo, giải đáp nghiệp vụ.<br>' +
        '<b>Chỉ tài liệu</b>: không có tài liệu thì bot nói chưa có thông tin, không tự nói thêm. ' +
        'Hợp với bot đọc giá và chính sách, nơi một câu sai là thiệt hại thật.<br>' +
        'Cả hai chế độ đều bắt buộc phải có tài liệu mới được nói về giá, chính sách, tồn kho.</div>' +

        '<label>Token Telegram' + (sua ? " (để trống nếu không đổi)" : "") + '</label>' +
        '<div class="cb-row">' +
          '<input id="cbToken" type="password" placeholder="Lấy từ @BotFather, dạng 123456:AA...">' +
          '<button class="s-btn-ghost" id="cbCheck" type="button">Kiểm tra</button>' +
        '</div>' +
        '<div class="cb-hint" id="cbTokenNote">' +
          (b && b.bot_username ? "Đang dùng @" + esc(b.bot_username) : "Mỗi bot phải một token RIÊNG. Đừng dùng token bot chính của bạn.") +
        '</div>' +

        '<label>Chat ID nhân viên nhận chuyển tiếp</label>' +
        '<input id="cbHandoff" value="' + esc(b ? (b.handoff_to || "") : "") + '" placeholder="Ví dụ: 123456789">' +
        '<div class="cb-hint">Bot bí <b>hai câu liên tiếp</b> với cùng một người thì nhắn vào ' +
        'đây, và khách gõ /nhanvien thì báo ngay. Bí một câu lẻ không gọi - báo mọi câu vu vơ ' +
        'thì vài lần là nhân viên tắt thông báo. Bỏ trống thì bot chỉ nói chưa có thông tin rồi dừng.</div>' +

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

    var nut = box.querySelector("#cbNewBrain");
    if (nut) nut.onclick = async function () {
      var ten = prompt("Tên brain mới cho bot:", goiY || "bot-moi");
      if (!ten) return;
      try {
        var r = await api("/brains/new", { method: "POST", body: fd({ name: ten }) });
        var sel = box.querySelector("#cbBrain");
        sel.insertAdjacentHTML("afterbegin", '<option value="' + esc(r.name) + '" selected>' + esc(r.name) + '</option>');
        sel.value = r.name;
      } catch (e) { alert("Không tạo được brain: " + e.message); }
    };

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
      var br = box.querySelector("#cbBrain").value;
      var tok = box.querySelector("#cbToken").value.trim();
      var ho = box.querySelector("#cbHandoff").value.trim();
      var ngu = box.querySelector("#cbNguon").value;
      if (!ten) return alert("Nhập tên bot");
      if (!ag) return alert("Chọn Agent làm bộ não cho bot");
      if (!br) return alert("Chọn hoặc tạo brain riêng cho bot");
      try {
        if (sua) {
          var gr = box.querySelector("#cbGroups");
          await api("/chatbots/" + encodeURIComponent(b.id) + "/update", {
            method: "POST",
            body: fd({ name: ten, agent_slug: ag, agent_brain: brain(), brain: br,
                       handoff_to: ho, token: tok, bot_username: uname, nguon_tra_loi: ngu,
                       groups: gr ? gr.value : undefined }),
          });
        } else {
          if (!tok) return alert("Dán token Telegram của bot (lấy ở @BotFather)");
          await api("/chatbots", {
            method: "POST",
            body: fd({ name: ten, agent_slug: ag, agent_brain: brain(), brain: br,
                       token: tok, bot_username: uname, handoff_to: ho, nguon_tra_loi: ngu }),
          });
        }
      } catch (e) { return alert("Không lưu được: " + e.message); }
      dong();
      tai();
    };
  }

  window.JavisChatbots = { render: render };
})();
