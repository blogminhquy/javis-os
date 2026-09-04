/* Trang Gói: xem gói đã cài, cài từ tệp .zip, bật tắt, gỡ.
 *
 * File riêng thay vì nhét vào console.js (đã ~7k dòng), theo đúng cách studio.js và
 * chatbots.js đang làm: console.js dựng khung rồi gọi window.JavisPacks.render(el).
 *
 * Nguyên tắc của màn hình xác nhận: nó VẼ TỪ /packs/inspect chứ không tự đoán. Danh sách "gói
 * này chứa gì" viết tay trong JS thì sau vài tháng nó lệch khỏi thứ server thật sự cài, mà
 * lệch theo hướng nguy hiểm - người dùng đọc thấy ít hơn thực tế. Server mở tệp ra, kiểm, rồi
 * trả về đúng cái sắp xảy ra.
 */
(function () {
  "use strict";

  // Icon dùng chung của dashboard. KHÔNG emoji: `tests/python/test_icons.py` canh chuyện đó,
  // và lý do là emoji vẽ khác nhau theo hệ điều hành lẫn theo phông, nên giao diện lệch hẳn
  // giữa các máy.
  function ic(ten, opt) { return (window.ic ? window.ic(ten, opt) : ""); }

  const esc = (s) => (s || "").toString()
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  // name/description là map đa ngôn ngữ. Lấy theo ngôn ngữ giao diện, rơi về en, rồi về giá
  // trị đầu tiên có được - thiếu bản dịch thì hiện tiếng khác, không bao giờ hiện trống.
  function nn(v, mac) {
    if (!v) return mac || "";
    if (typeof v === "string") return v;
    const lang = (window.JavisI18n && window.JavisI18n.lang) || "vi";
    return v[lang] || v.en || Object.values(v)[0] || mac || "";
  }

  function co(b) {
    b = Number(b || 0);
    if (!b) return "";
    if (b < 1024) return b + " B";
    if (b < 1024 * 1024) return Math.round(b / 1024) + " KB";
    return (b / 1024 / 1024).toFixed(1) + " MB";
  }

  async function postJson(url, obj) {
    try {
      const r = await fetch(url, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(obj || {})
      });
      return await r.json();
    } catch (e) { return { ok: false, error: String(e) }; }
  }

  function modal(html, maxw) {
    let m = document.getElementById("packModal");
    if (!m) {
      m = document.createElement("div");
      m.id = "packModal"; m.className = "mp-overlay";
      document.body.appendChild(m);
    }
    m.innerHTML = '<div class="mp-box" style="max-width:' + (maxw || 560) + 'px">' + html + '</div>';
    m.classList.add("open");
    m.querySelectorAll('[data-act="close"]').forEach(b => b.onclick = dong);
    return m;
  }
  function dong() {
    const m = document.getElementById("packModal");
    if (m) m.classList.remove("open");
  }

  const BAC = {
    data: { nhan: "Chỉ dữ liệu", mau: "var(--ok-ink,#2f855a)" },
    code: { nhan: "Có chạy mã", mau: "var(--warn-ink,#b7791f)" },
  };

  function theGoi(p) {
    const ten = esc(nn(p.name, p.id));
    const bac = BAC[p.tier] || BAC.data;
    const tat = p.enabled === false;
    const loi = p.ok === false;
    return '<div class="prov-row' + (tat || loi ? " off" : "") + '">'
      + '<div class="prov-ico">' + ic("package") + '</div>'
      + '<div class="prov-main">'
      + '<div class="prov-name">' + ten
      + ' <span class="prov-kind" style="color:' + bac.mau + '">' + bac.nhan + '</span>'
      + (tat ? ' <span class="prov-kind">đang tắt</span>' : "")
      + '</div>'
      + '<div class="prov-meta">' + esc(p.id) + (p.version ? " · v" + esc(p.version) : "")
      + (p.connectors && p.connectors.length
          ? " · " + p.connectors.length + " dịch vụ" : "")
      + '</div>'
      + (loi ? '<div class="prov-meta" style="color:var(--danger-ink,#b3261e)">'
               + esc(p.error) + '</div>'
             : (p.error ? '<div class="prov-meta" style="color:var(--warn-ink,#b7791f)">'
                          + esc(p.error) + '</div>' : ""))
      + '</div>'
      + (loi ? "" : '<button class="mp-btn" data-pk-toggle="' + esc(p.id) + '" data-on="'
                    + (tat ? "1" : "0") + '">' + (tat ? "Bật" : "Tắt") + '</button>')
      + '<button class="mp-btn danger" data-pk-del="' + esc(p.id) + '">Gỡ</button>'
      + '</div>';
  }

  // ---- Màn hình xác nhận trước khi cài, vẽ hoàn toàn từ kết quả /packs/inspect ----
  function manHinhDongY(d, el) {
    const coMa = d.tier === "code";
    const py = (d.py_files || []);
    modal(
      '<div class="mp-head"><div class="mp-title">CÀI GÓI</div>'
      + '<button class="mp-x" data-act="close">×</button></div>'
      + '<div class="mp-body">'
      + '<p style="font-size:1.05em"><b>' + esc(nn(d.name, d.id)) + '</b>'
      + (d.version ? ' <span style="opacity:.6">v' + esc(d.version) + '</span>' : "") + '</p>'
      + (nn(d.description) ? '<p>' + esc(nn(d.description)) + '</p>' : "")
      + '<div class="prov-meta">Mã gói <code>' + esc(d.id) + '</code>'
      + (d.author && d.author.name ? ' · tác giả ' + esc(d.author.name) : "")
      + '</div>'
      + '<p style="margin-top:12px">Xuất xứ: <b>' + esc(d.filename || "tệp bạn vừa chọn")
      + '</b> · ' + co(d.size) + '<br>'
      + '<span style="opacity:.6;font-size:.9em">Dấu vân tay ' + esc((d.sha256 || "").slice(0, 16))
      + '…</span></p>'
      + (d.da_cai
          ? '<p style="color:var(--warn-ink,#b7791f)">Máy đã có gói này (bản '
            + esc(d.da_cai.version || "?") + '). Cài tiếp là THAY bản cũ.</p>' : "")
      + ((d.connectors || []).length
          ? '<p style="margin-top:10px">Thêm ' + d.connectors.length + ' dịch vụ vào Kho kết nối: '
            + d.connectors.map(x => '<code>' + esc(x) + '</code>').join(", ")
            + '<br><span style="opacity:.6;font-size:.9em">Mọi dịch vụ từ gói đều bắt đầu ở mức '
            + 'Chỉ đọc. Muốn cho ghi thì bạn tự nâng quyền từng tài khoản.</span></p>' : "")
      + (d.warning ? '<p style="color:var(--warn-ink,#b7791f)">Một phần của gói bị bỏ qua: '
                     + esc(d.warning) + '</p>' : "")
      // Khối cảnh báo cho gói có mã: KHÔNG gập được, không icon ổ khoá, không làm mềm chữ.
      // `permissions` trong manifest là lời khai của tác giả, không có tầng nào chặn, và
      // `min_mode` chỉ giới hạn cái MODEL được gọi chứ không giới hạn cái mã làm được.
      + (coMa
        ? '<div class="conn-guide" style="border-left:3px solid var(--danger-ink,#b3261e);'
          + 'padding-left:10px;margin-top:14px">'
          + '<b>Gói này chạy Python thật bên trong máy chủ Javis.</b><br>'
          + 'Nó đọc được mọi khoá API, token và tệp mà Javis đọc được. Không có lớp ngăn nào cả. '
          + 'Chỉ cài gói từ nguồn bạn tin.'
          + (py.length
              ? '<div style="margin-top:8px;font-size:.9em;opacity:.85">Tệp mã trong gói: '
                + py.slice(0, 12).map(x => '<code>' + esc(x) + '</code>').join(", ")
                + (py.length > 12 ? " và " + (py.length - 12) + " tệp nữa" : "") + '</div>' : "")
          + '<label style="display:block;margin-top:10px">Gõ đúng <b>' + esc(d.id)
          + '</b> để xác nhận:<br><input class="mp-input" id="pkGo" placeholder="Gõ lại mã gói">'
          + '</label></div>' : "")
      + '<label style="display:block;margin-top:14px"><input type="checkbox" id="pkBat"> '
      + 'Bật ngay sau khi cài <span style="opacity:.6">(mặc định tắt, để bạn xem lại trước)</span>'
      + '</label>'
      + '</div>'
      + '<div class="mp-foot"><span class="mp-note" id="pkNote"></span>'
      + '<button class="mp-btn" data-act="close">Huỷ</button>'
      + '<button class="mp-btn primary" id="pkCai">Cài</button></div>');

    // Nút Huỷ nhận tiêu điểm mặc định: Enter không được là "đồng ý cài mã lạ".
    const huy = document.querySelector('#packModal [data-act="close"].mp-btn');
    if (huy) huy.focus();
    const note = document.getElementById("pkNote");
    document.getElementById("pkCai").onclick = async () => {
      if (coMa) {
        const v = (document.getElementById("pkGo") || {}).value || "";
        if (v.trim() !== d.id) {
          note.textContent = "Gõ đúng mã gói thì mới cài được.";
          return;
        }
      }
      note.textContent = "Đang cài…";
      const r = await postJson("/packs/install", {
        staging_id: d.staging_id, consent_sha256: d.sha256,
        enable: !!(document.getElementById("pkBat") || {}).checked,
        source: d.source || { kind: "zip" },
      });
      if (!r || !r.ok) { note.textContent = (r && r.error) || "Cài không được."; return; }
      dong();
      render(el);
    };
  }

  async function tuUrl(el, url, expect) {
    // Tải từ kho hay từ link đều dừng ở bước SOI rồi mở đúng màn hình xác nhận như tệp tải
    // lên. Đường từ kho về máy không được phép ngắn hơn đường từ tệp: cùng một thứ để đọc,
    // cùng một chốt dấu vân tay.
    modal('<div class="mp-head"><div class="mp-title">ĐANG TẢI GÓI</div></div>'
      + '<div class="mp-body">Đang tải và kiểm tra…</div>');
    const d = await postJson("/packs/install-url", { url: url, expect_sha256: expect || "" });
    if (!d || !d.ok) {
      modal('<div class="mp-head"><div class="mp-title">KHÔNG CÀI ĐƯỢC</div>'
        + '<button class="mp-x" data-act="close">×</button></div>'
        + '<div class="mp-body"><p>' + esc((d && d.error) || "Tải không được.") + '</p>'
        + ((d && d.stage) ? '<div class="prov-meta">Dừng ở bước: ' + esc(d.stage) + '</div>' : "")
        + '</div><div class="mp-foot"><button class="mp-btn" data-act="close">Đóng</button></div>');
      return;
    }
    manHinhDongY(d, el);
  }

  function theKho(g) {
    const bac = BAC[g.tier] || BAC.data;
    const daCai = !!g.installed;
    const moi = daCai && g.installed_version && g.version && g.installed_version !== g.version;
    const nut = moi
      ? '<button class="gcard-btn" data-kho="' + esc(g.download.url) + '" data-sha="'
        + esc(g.download.sha256 || "") + '">Có bản mới v' + esc(g.version) + '</button>'
      : daCai
        ? '<button class="gcard-btn" disabled style="opacity:.55">Đã cài</button>'
        : '<button class="gcard-btn" data-kho="' + esc(g.download.url) + '" data-sha="'
          + esc(g.download.sha256 || "") + '">Cài</button>';
    return '<div class="cat-card" data-cat="' + esc(g.category || "") + '">'
      + '<div class="cat-ico">' + ic("package") + '</div>'
      + '<div class="cat-name">' + esc(nn(g.name, g.id))
      + ' <span class="prov-kind" style="color:' + bac.mau + '">' + bac.nhan + '</span>'
      + (g.verified ? ' <span class="prov-kind" style="color:var(--ok-ink,#2f855a)">chính chủ</span>' : "")
      + '</div>'
      + '<div class="cat-desc">' + esc(nn(g.description)) + '</div>'
      + '<div class="prov-meta">' + esc(g.id) + (g.version ? " · v" + esc(g.version) : "")
      + (g.author && g.author.name ? " · " + esc(g.author.name) : "") + '</div>'
      + nut + '</div>';
  }

  async function veKho(el, host, lamMoi) {
    host.innerHTML = '<div class="mp-empty">Đang tải danh mục…</div>';
    let d;
    try { d = await (await fetch("/packs/store" + (lamMoi ? "?refresh=1" : ""))).json(); }
    catch (e) { d = { ok: false, error: String(e) }; }
    if (!d || !d.ok) {
      // Kho không tới được thì KHÔNG phải là hỏng cả trang: cài từ tệp vẫn chạy như thường.
      host.innerHTML = '<div class="mp-empty">Chưa xem được danh mục ('
        + esc((d && d.error) || "không tải được") + ').<br>'
        + 'Bạn vẫn cài được gói từ tệp .zip như bình thường.</div>';
      return;
    }
    const ds = d.packs || [];
    const cats = Array.from(new Set(ds.map(g => g.category).filter(Boolean)));
    host.innerHTML =
      (d.stale ? '<div class="conn-guide" style="border-left:3px solid var(--warn,#e0a33e);padding-left:10px;margin-bottom:10px">Đang xem danh mục đã lưu lần trước, vì lần này chưa lấy được bản mới.</div>' : "")
      + '<div class="cat-tools"><input class="js-input" id="pkQ" placeholder="Tìm gói…" style="max-width:220px">'
      + '<span class="cat-filter"><button class="cat-chip on" data-pkf="">Tất cả</button>'
      + cats.map(c => '<button class="cat-chip" data-pkf="' + esc(c) + '">' + esc(c) + '</button>').join("")
      + '</span>'
      + '<button class="mp-btn" id="pkLamMoi" style="margin-left:auto">Làm mới</button></div>'
      + '<div class="cat-grid" id="pkGrid">'
      + (ds.length ? ds.map(theKho).join("") : '<div class="mp-empty">Kho chưa có gói nào.</div>')
      + '</div>';

    host.querySelectorAll("[data-kho]").forEach(b => b.onclick = () =>
      tuUrl(el, b.dataset.kho, b.dataset.sha));
    document.getElementById("pkLamMoi").onclick = () => veKho(el, host, true);
    const loc = () => {
      const q = (document.getElementById("pkQ").value || "").toLowerCase();
      const chip = host.querySelector(".cat-chip.on");
      const cf = chip ? (chip.dataset.pkf || "") : "";
      host.querySelectorAll("#pkGrid .cat-card").forEach(c => {
        const hop = (!cf || c.dataset.cat === cf) && (!q || c.textContent.toLowerCase().includes(q));
        c.style.display = hop ? "" : "none";
      });
    };
    document.getElementById("pkQ").oninput = loc;
    host.querySelectorAll("[data-pkf]").forEach(b => b.onclick = () => {
      host.querySelectorAll("[data-pkf]").forEach(x => x.classList.remove("on"));
      b.classList.add("on");
      loc();
    });
  }

  async function chonTep(el, file) {
    modal('<div class="mp-head"><div class="mp-title">ĐANG ĐỌC GÓI</div></div>'
      + '<div class="mp-body">Đang mở và kiểm tra tệp…</div>');
    const fd = new FormData();
    fd.append("file", file);
    let d;
    try { d = await (await fetch("/packs/inspect", { method: "POST", body: fd })).json(); }
    catch (e) { d = { ok: false, error: String(e) }; }
    if (!d || !d.ok) {
      modal('<div class="mp-head"><div class="mp-title">KHÔNG CÀI ĐƯỢC</div>'
        + '<button class="mp-x" data-act="close">×</button></div>'
        + '<div class="mp-body"><p>' + esc((d && d.error) || "Tệp không hợp lệ.") + '</p>'
        + ((d && d.stage) ? '<div class="prov-meta">Dừng ở bước: ' + esc(d.stage) + '</div>' : "")
        + '</div><div class="mp-foot"><button class="mp-btn" data-act="close">Đóng</button></div>');
      return;
    }
    manHinhDongY(d, el);
  }

  async function hopGo(el, pid) {
    modal('<div class="mp-head"><div class="mp-title">GỠ GÓI</div></div>'
      + '<div class="mp-body">Đang kiểm tra…</div>');
    let d;
    try {
      d = await (await fetch("/packs/uninstall-plan?id=" + encodeURIComponent(pid))).json();
    } catch (e) { d = { ok: false, error: String(e) }; }
    if (!d || !d.ok) {
      modal('<div class="mp-head"><div class="mp-title">GỠ GÓI</div>'
        + '<button class="mp-x" data-act="close">×</button></div>'
        + '<div class="mp-body">' + esc((d && d.error) || "Lỗi") + '</div>'
        + '<div class="mp-foot"><button class="mp-btn" data-act="close">Đóng</button></div>');
      return;
    }
    const kn = d.connections || [];
    modal('<div class="mp-head"><div class="mp-title">GỠ GÓI</div>'
      + '<button class="mp-x" data-act="close">×</button></div>'
      + '<div class="mp-body">'
      + '<p>Sắp gỡ <b>' + esc(nn(d.name, d.id)) + '</b>.</p>'
      + '<p>Những thứ sẽ mất:</p><ul style="margin:6px 0 0 18px">'
      + '<li>Tệp của gói <span style="opacity:.6">(' + co(d.bytes) + ')</span></li>'
      + ((d.connectors || []).length
          ? '<li>' + d.connectors.length + ' dịch vụ khỏi Kho kết nối</li>' : "")
      // Kết nối theo gói bị xoá THEO, và nói thẳng ra chứ không giấu trong một ô tick: để lại
      // một hàng kết nối chết vẫn là để lại credential của nó trên đĩa.
      + (kn.length
          ? '<li><b>' + kn.length + ' kết nối bạn đã đấu</b>: '
            + kn.map(x => esc(x.label)).join(", ")
            + '<br><span style="opacity:.6;font-size:.9em">Chúng bị xoá theo, và chuyển vào '
            + 'thùng rác giữ 30 ngày.</span></li>' : "")
      + '</ul>'
      + ((d.plugin_data || []).length
          ? '<label style="display:block;margin-top:12px"><input type="checkbox" id="pkData"> '
            + 'Xoá luôn dữ liệu plugin của gói này '
            + '<span style="opacity:.6">(mặc định giữ lại)</span></label>' : "")
      + '</div>'
      + '<div class="mp-foot"><span class="mp-note" id="pkNote2"></span>'
      + '<button class="mp-btn" data-act="close">Huỷ</button>'
      + '<button class="mp-btn danger" id="pkGoOk">Gỡ</button></div>');
    const note = document.getElementById("pkNote2");
    document.getElementById("pkGoOk").onclick = async () => {
      note.textContent = "Đang gỡ…";
      const r = await postJson("/packs/uninstall", {
        id: pid, purge_data: !!(document.getElementById("pkData") || {}).checked,
      });
      if (!r || !r.ok) { note.textContent = (r && r.error) || "Gỡ không được."; return; }
      dong();
      render(el);
    };
  }

  async function render(el) {
    el.innerHTML = '<div class="cview-placeholder">Đang tải…</div>';
    let d;
    try { d = await (await fetch("/packs")).json(); }
    catch (e) { el.innerHTML = '<div class="cview-placeholder">Không tải được.</div>'; return; }
    if (d && d.error) {
      el.innerHTML = '<div class="cview-placeholder">' + esc(d.error) + '</div>';
      return;
    }
    const ds = d.packs || [];
    el.innerHTML =
      '<div class="cview-section"><h3>◆ Gói đã cài <span style="opacity:.5">'
      + ds.length + '</span></h3>'
      + '<div class="gcard-meta" style="max-width:740px">Gói là cách thêm dịch vụ và công cụ '
      + 'cho Javis mà <b>không cần chờ bản cập nhật</b>. Chọn một tệp <code>.zip</code>, Javis mở '
      + 'ra cho bạn xem gói đó chứa gì rồi mới hỏi có cài không.</div>'
      + (d.disabled
        ? '<div class="conn-guide" style="border-left:3px solid var(--warn,#e0a33e);padding-left:10px;margin-top:12px">'
          + 'Biến môi trường <code>JAVIS_DISABLE_PACKS</code> đang bật, nên mọi gói bị tắt hết.</div>'
        : "")
      + '<div style="margin-top:12px"><button class="mp-btn primary" id="pkChon">Cài từ tệp .zip</button> '
      + '<input type="file" id="pkFile" accept=".zip" style="display:none">'
      + '<span style="opacity:.6;margin-left:8px">tối đa ' + (d.max_mb || 25) + 'MB</span></div>'
      + '<div class="prov-list" id="pkList" style="margin-top:14px">'
      + (ds.length ? ds.map(theGoi).join("")
                   : '<div class="mp-empty">Chưa có gói nào.</div>')
      + '</div>'
      + '<div class="gcard-meta" style="margin-top:14px;opacity:.7">Gói nằm ở <code>'
      + esc(d.dir || "") + '</code>. Thả thẳng một thư mục vào đó cũng được, không bắt buộc '
      + 'phải qua tệp nén.</div>'
      + '</div>'
      + '<div class="cview-section"><h3>◆ Kho gói</h3>'
      + '<div class="gcard-meta" style="max-width:740px">Danh mục gói do Javis phát hành. '
      + 'Bấm Cài là Javis tải về, mở ra cho bạn xem rồi mới hỏi, y như khi bạn tự chọn tệp.</div>'
      + '<div id="pkKho" style="margin-top:12px"></div></div>';

    const inp = document.getElementById("pkFile");
    document.getElementById("pkChon").onclick = () => inp.click();
    inp.onchange = () => { if (inp.files && inp.files[0]) chonTep(el, inp.files[0]); inp.value = ""; };
    el.querySelectorAll("[data-pk-toggle]").forEach(b => b.onclick = async () => {
      const r = await postJson("/packs/toggle",
        { id: b.dataset.pkToggle, enabled: b.dataset.on === "1" });
      if (r && r.ok) render(el); else alert((r && r.error) || "Không đổi được.");
    });
    el.querySelectorAll("[data-pk-del]").forEach(b => b.onclick = () => hopGo(el, b.dataset.pkDel));
    // Kho vẽ SAU và độc lập: kho không tới được thì phần "đã cài" ở trên vẫn dùng bình thường.
    const hostKho = document.getElementById("pkKho");
    if (hostKho) veKho(el, hostKho, false);
  }

  window.JavisPacks = { render: render };
})();
