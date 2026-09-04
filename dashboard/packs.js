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
    // Ngôn ngữ hiện tại lấy bằng một lời GỌI HÀM, phải có cặp ngoặc. Thiếu ngoặc thì `v[lang]`
    // tra bằng một object hàm, luôn trượt, và mọi tên gói rơi về tiếng Anh trong giao diện
    // tiếng Việt - hỏng lặng lẽ, vì vẫn có chữ để hiện nên trông như gói thiếu bản dịch chứ
    // không như một lỗi. Đã sống trong file này từ 0.55.22 tới 0.55.28.
    const lang = (window.JavisI18n && JavisI18n.lang()) || "vi";
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

  // Loại năng lực, thứ chia lưới kho thành các tab. Thứ tự ở đây LÀ thứ tự chip trên màn
  // hình, đi từ thứ người dùng hiểu nhanh nhất (trợ lý) tới thứ kỹ thuật nhất (kết nối).
  //
  // `bundle` cố ý KHÔNG có chip riêng: nó là chỗ rơi của mục khai loại lạ, và một chip tên
  // "Khác" chỉ mời người ta bấm vào để thấy lưới rỗng. Mục bundle vẫn hiện ở tab Tất cả.
  //
  // Icon lấy ĐÚNG icon trang tương ứng ở thanh bên (`console.js` VIEW_ICON), không chọn lại
  // cho đẹp: người dùng nhận ra "cái này là kỹ năng" bằng hình họ đã thấy hàng ngày.
  const LOAI = {
    agent:     { nhan: "Trợ lý",    icon: "bot",      trang: "agents" },
    skill:     { nhan: "Kỹ năng",   icon: "puzzle",   trang: "skills" },
    workflow:  { nhan: "Quy trình", icon: "workflow", trang: "workflows" },
    tool:      { nhan: "Công cụ",   icon: "toolbox",  trang: "plugins" },
    connector: { nhan: "Kết nối",   icon: "plug",     trang: "mcp" },
    bundle:    { nhan: "Trọn bộ",   icon: "package",  trang: "" },
  };
  const THU_TU_LOAI = ["agent", "skill", "workflow", "tool", "connector"];

  // Loại được chọn sẵn khi mở kho. `moKho()` đặt, `render()` lấy rồi XOÁ ngay - nó là ý định
  // của MỘT lần bấm tab, không phải trạng thái của trang.
  let _loaiCho = "";

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

  function vaultTom(v) {
    // Tóm tắt "gói này thêm gì vào bộ não", dạng "2 trợ lý, 1 kỹ năng".
    const TEN = { agents: "trợ lý", workflows: "quy trình", skills: "kỹ năng" };
    return Object.keys(TEN)
      .filter(k => ((v || {})[k] || []).length)
      .map(k => (v[k].length + " " + TEN[k]));
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
      // Agent, workflow và skill ghi vào BRAIN của bạn - nơi bạn tự viết. Phải nói rõ hơn cả
      // connector, vì đây là thứ duy nhất trong gói đụng tới chỗ đó.
      + (vaultTom(d.vault).length
          ? '<p style="margin-top:10px">Thêm vào bộ não đang mở: ' + vaultTom(d.vault).join(", ")
            + '<br><span style="opacity:.6;font-size:.9em">Nếu bộ não đã có mục trùng tên, Javis '
            + 'giữ bản của bạn và bỏ qua bản trong gói. Gỡ gói cũng chỉ xoá thứ bạn chưa sửa.'
            + '</span></p>' : "")
      // Gói chưa qua review của người phát hành kho: nói dài hơn một dòng. Không chặn - ai tin
      // nguồn nào là lựa chọn của người cài - nhưng họ phải biết mình đang chọn gì.
      + ((d._tin && d._tin.verified === false)
          ? '<div class="conn-guide" style="border-left:3px solid var(--warn,#e0a33e);'
            + 'padding-left:10px;margin-top:12px">Gói này do <b>cộng đồng</b> gửi, chưa qua '
            + 'kiểm duyệt của người phát hành kho. Hãy xem kỹ phần bên dưới trước khi cài.</div>'
          : "")
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
        // Brain ĐANG MỞ. `currentBrainPath` là hàm toàn cục mà app.js phơi ra và cả
        // console.js lẫn chat-render.js đều dùng - đi qua nó thay vì tự đoán chỗ khác.
        brain: (typeof currentBrainPath === "function" ? currentBrainPath() : "") || "brain",
      });
      if (!r || !r.ok) { note.textContent = (r && r.error) || "Cài không được."; return; }
      dong();
      render(el);
    };
  }

  async function tuUrl(el, url, expect, tin) {
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
    d._tin = tin || null;
    manHinhDongY(d, el);
  }

  // ---- Ảnh đại diện của một mục ----
  // Ưu tiên icon THẬT của mục (connector đi kèm app đều có logo). Không có thì dựng một ô chữ
  // cái: đó là chỗ dựa của lưới - mắt nhận ra hàng nào là hàng nào trước khi kịp đọc chữ.
  const MAU_AVATAR = ["#2563eb", "#e8590c", "#0f766e", "#16a34a", "#7c3aed", "#0891b2",
                      "#ca8a04", "#dc2626", "#0d9488", "#db2777"];

  function chuCai(ten) {
    const w = String(ten || "?").trim().split(/\s+/).filter(Boolean);
    if (!w.length) return "?";
    if (w.length === 1) return w[0].slice(0, 2).replace(/^./, c => c.toUpperCase());
    return (w[0][0] + w[1][0]).toUpperCase();
  }

  function mauTheoId(id) {
    let h = 0;
    for (let i = 0; i < String(id).length; i++) h = (h * 31 + String(id).charCodeAt(i)) >>> 0;
    return MAU_AVATAR[h % MAU_AVATAR.length];
  }

  function veAvatar(g) {
    // Ba dạng, xử lý đúng thứ tự của `console.js iconInner` - trường `icon` của connector đã
    // mang cả ba từ lâu và không thể ép về một dạng:
    //   đường dẫn/URL ảnh (logo hãng)  -> <img>
    //   tên icon Lucide                -> SVG, đặt trên nền màu
    //   không có gì                    -> ô chữ cái
    //
    // `ic()` KHÔNG tự nhận đường dẫn (đó là việc của `iconInner`), nên bỏ nhánh <img> là mọi
    // logo hãng hiện thành dấu hỏi - đúng lỗi thấy trên màn hình bản dựng đầu.
    const src = String((g && g.icon) || "");
    if (/^(https?:|\/)/.test(src)) {
      return '<div class="kho-ava kho-ava-img"><img src="' + esc(src)
        + '" alt="" loading="lazy"></div>';
    }
    const nen = ' style="background:' + mauTheoId(g.id) + '"';
    if (src && window.Icons && window.Icons.has && window.Icons.has(src)) {
      return '<div class="kho-ava"' + nen + '>' + ic(src) + '</div>';
    }
    return '<div class="kho-ava"' + nen + '>' + esc(chuCai(nn(g.name, g.id))) + '</div>';
  }

  // ---- Nút trên thẻ ----
  // Bốn tình huống, và chúng KHÔNG cùng một hành động bên dưới. Mục tải từ kho thì cài là tải
  // về rồi qua màn hình xác nhận, gỡ là trình gỡ gói. Connector đi kèm app thì không tải gì cả,
  // "gỡ" chỉ là ghi vào sổ đã-gỡ (`core_off`) để nó biến khỏi kho Kết nối - tệp trong `system/`
  // không hề bị đụng, vì cây code là read-only trên Docker và bị `git pull` ghi đè trên bản
  // native. Trộn hai thứ này làm một là gỡ nhầm hoặc gỡ hụt.
  function nutThe(g) {
    const moi = g.installed && g.installed_version && g.version
                && g.installed_version !== g.version;
    if (g.nguon === "app") {
      return g.installed
        ? { nhan: "Gỡ khỏi Javis", lop: "kho-btn kho-btn-go", act: "coreoff" }
        : { nhan: "Cài lại", lop: "kho-btn kho-btn-chinh", act: "coreon" };
    }
    if (moi) return { nhan: "Có bản mới v" + esc(g.version), lop: "kho-btn kho-btn-chinh", act: "cai" };
    if (g.installed) return { nhan: "Gỡ cài đặt", lop: "kho-btn kho-btn-go", act: "go" };
    return { nhan: "Cài đặt", lop: "kho-btn kho-btn-chinh", act: "cai" };
  }

  function theKho(g) {
    const bac = BAC[g.tier] || BAC.data;
    const lo = LOAI[g.kind] || LOAI.bundle;
    const n = nutThe(g);
    const meta = [g.id, g.version ? "v" + g.version : "",
                  (g.author && g.author.name) || ""].filter(Boolean).map(esc).join(" · ");
    return '<div class="cat-card kho-the" data-loai="' + esc(g.kind || "bundle") + '"'
      + ' data-nhom="' + esc(g.nhom || "") + '" data-ng="' + (g.verified ? "1" : "0") + '">'
      + '<div class="kho-dau">' + veAvatar(g)
      + '<span class="kho-nhom">' + esc(g.nhom || lo.nhan) + '</span></div>'
      + '<div class="kho-ten">' + esc(nn(g.name, g.id))
      + ' <span class="prov-kind">' + esc(lo.nhan) + '</span>'
      + ' <span class="prov-kind" style="color:' + bac.mau + '">' + bac.nhan + '</span>'
      + (g.verified
          ? ' <span class="prov-kind" style="color:var(--ok-ink,#2f855a)">chính chủ</span>'
          : ' <span class="prov-kind">cộng đồng</span>')
      + '</div>'
      + '<div class="cat-desc">' + esc(nn(g.description)) + '</div>'
      + '<div class="prov-meta">' + meta + '</div>'
      + (g.installed
          ? '<div class="kho-daicai">' + ic("check") + ' Đã cài trên máy</div>' : "")
      + '<button class="' + n.lop + '" data-kho-act="' + n.act + '" data-kho-id="' + esc(g.id) + '">'
      + n.nhan + '</button>'
      + '</div>';
  }

  // Trạng thái lưới kho. Để ở module vì mọi lần bấm tab, bấm nhóm hay đổi trang đều chỉ VẼ LẠI
  // từ dữ liệu đã tải, không gọi lại mạng.
  let _kho = { dl: null, loai: "connector", nhom: "Tất cả", trang: 1, tim: "" };
  const MOI_TRANG = 20;

  async function veKho(el, host, lamMoi, loaiDau) {
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
    _kho.dl = d;
    _kho.trang = 1;
    _kho.tim = "";
    if (loaiDau && LOAI[loaiDau]) _kho.loai = loaiDau;
    _kho.nhom = "Tất cả";
    veLuoi(el, host);
  }

  function veLuoi(el, host) {
    const d = _kho.dl || { packs: [] };
    const ds = d.packs || [];
    const cungLoai = ds.filter(g => (g.kind || "bundle") === _kho.loai);
    const daCai = cungLoai.filter(g => g.installed);

    // Nhóm chỉ liệt kê nhóm THẬT SỰ có hàng trong loại đang xem. Một hàng bấm vào ra lưới rỗng
    // làm người ta tưởng kho hỏng, trong khi sự thật chỉ là loại đó chưa có mục nào thuộc nhóm.
    const dem = {};
    cungLoai.forEach(g => { const k = g.nhom || "Khác"; dem[k] = (dem[k] || 0) + 1; });
    const tenNhom = Object.keys(dem).sort((a, b) => a.localeCompare(b, "vi"));

    // Gói do người ngoài gửi vào kho. Chủ kho đọc mã trước khi trộn nên chúng KHÔNG phải hàng
    // lạ, nhưng người cài vẫn có quyền muốn xem riêng - và khi kho lớn dần thì đây là bộ lọc
    // họ tìm đầu tiên. Chỉ hiện hàng này khi thật sự có hàng cộng đồng.
    const congDong = cungLoai.filter(g => !g.verified);
    const laDaCai = _kho.nhom === "Đã cài";
    const laCongDong = _kho.nhom === "Cộng đồng";
    const q = _kho.tim.trim().toLowerCase();
    const hop = cungLoai.filter(g =>
      (_kho.nhom === "Tất cả"
        || (laDaCai ? g.installed
            : laCongDong ? !g.verified
            : (g.nhom || "Khác") === _kho.nhom))
      && (!q || (nn(g.name, g.id) + " " + nn(g.description) + " " + g.id).toLowerCase().includes(q)));

    const soTrang = Math.max(1, Math.ceil(hop.length / MOI_TRANG));
    const trang = Math.min(Math.max(1, _kho.trang), soTrang);
    _kho.trang = trang;
    const hienThi = hop.slice((trang - 1) * MOI_TRANG, trang * MOI_TRANG);

    const tabLoai = THU_TU_LOAI.map(k => {
      const on = k === _kho.loai;
      return '<button class="kho-tab' + (on ? " on" : "") + '" data-kho-loai="' + k + '">'
        + esc(LOAI[k].nhan)
        + ' <span class="kho-dem">' + ds.filter(g => (g.kind || "bundle") === k).length
        + '</span></button>';
    }).join("");

    const hangNhom = (ten, so, on, ngan) =>
      '<button class="kho-nav' + (on ? " on" : "") + (ngan ? " ngan" : "") + '" data-kho-nhom="'
      + esc(ten) + '"><span>' + esc(ten) + '</span><span class="kho-navdem">' + so + '</span></button>';

    host.innerHTML =
      (d.stale ? '<div class="conn-guide" style="border-left:3px solid var(--warn,#e0a33e);padding-left:10px;margin-bottom:12px">Đang xem danh mục đã lưu lần trước, vì lần này chưa lấy được bản mới.</div>' : "")
      + '<div class="kho-tabs">' + tabLoai + '</div>'
      + '<div class="kho-than">'
      + '<div class="kho-cot">'
      + '<div class="kho-cot-tieu">Nhóm</div>'
      + hangNhom("Tất cả", cungLoai.length, _kho.nhom === "Tất cả")
      + hangNhom("Đã cài", daCai.length, laDaCai)
      + (congDong.length ? hangNhom("Cộng đồng", congDong.length, laCongDong) : "")
      + tenNhom.map((t, i) => hangNhom(t, dem[t], _kho.nhom === t, i === 0)).join("")
      + '</div>'
      + '<div class="kho-chinh">'
      + '<div class="cat-tools">'
      + '<input class="js-input" id="pkQ" placeholder="Tìm trong ' + esc(LOAI[_kho.loai].nhan)
      + '…" value="' + esc(_kho.tim) + '" style="max-width:320px">'
      + '<span class="prov-meta">' + hop.length
      + (laDaCai ? ' mục đã cài' : laCongDong ? ' mục cộng đồng' : ' mục') + '</span>'
      + '<span style="flex:1"></span>'
      + '<button class="mp-btn" id="pkLamMoi">Làm mới</button>'
      + '<button class="mp-btn" id="pkChon2">Cài từ tệp .zip</button>'
      + '</div>'
      + '<div class="cat-grid" id="pkGrid">' + hienThi.map(theKho).join("") + '</div>'
      + (hienThi.length ? "" : '<div class="mp-empty">'
          + (laDaCai ? 'Chưa cài mục nào trong ' + esc(LOAI[_kho.loai].nhan) + '.'
                     : 'Không có mục nào khớp bộ lọc.') + '</div>')
      + (soTrang > 1
          ? '<div class="kho-trang"><span class="prov-meta">Hiển thị '
            + ((trang - 1) * MOI_TRANG + 1) + '-' + Math.min(trang * MOI_TRANG, hop.length)
            + ' / ' + hop.length + '</span><span style="flex:1"></span>'
            + Array.from({ length: soTrang }, (_, i) =>
                '<button class="kho-so' + (i + 1 === trang ? " on" : "") + '" data-kho-trang="'
                + (i + 1) + '">' + (i + 1) + '</button>').join("")
            + '</div>'
          : "");

    const lai = () => veLuoi(el, host);
    host.querySelectorAll("[data-kho-loai]").forEach(b => b.onclick = () => {
      _kho.loai = b.dataset.khoLoai; _kho.nhom = "Tất cả"; _kho.trang = 1; _kho.tim = ""; lai();
    });
    host.querySelectorAll("[data-kho-nhom]").forEach(b => b.onclick = () => {
      _kho.nhom = b.dataset.khoNhom; _kho.trang = 1; lai();
    });
    host.querySelectorAll("[data-kho-trang]").forEach(b => b.onclick = () => {
      _kho.trang = Number(b.dataset.khoTrang); lai();
    });
    const o = document.getElementById("pkQ");
    if (o) o.oninput = () => { _kho.tim = o.value; _kho.trang = 1; lai(); o.focus(); };
    const lm = document.getElementById("pkLamMoi");
    if (lm) lm.onclick = () => veKho(el, host, true, _kho.loai);
    const ct = document.getElementById("pkChon2");
    if (ct) ct.onclick = () => { const f = document.getElementById("pkFile"); if (f) f.click(); };

    const theo = {};
    ds.forEach(g => { theo[g.id] = g; });
    host.querySelectorAll("[data-kho-act]").forEach(b => b.onclick = () => {
      const g = theo[b.dataset.khoId];
      if (!g) return;
      const act = b.dataset.khoAct;
      if (act === "cai") return tuUrl(el, g.download.url, g.download.sha256, g);
      if (act === "go") return hopGo(el, g.id);
      // Connector của app: `core_off` ghi vào sổ, tệp trong system/ không bị đụng.
      const tat = act === "coreoff";
      if (tat && !confirm('Gỡ "' + nn(g.name, g.id) + '" khỏi kho Kết nối?\n\n'
          + 'Kết nối đang dùng nó sẽ dừng, nhưng KHÔNG bị xoá - cài lại là chạy tiếp.')) return;
      postJson("/connect/core-toggle", { id: g.id, off: tat, confirm: true }).then(r => {
        if (r && r.ok) veKho(el, host, false, _kho.loai);
        else alert((r && r.error) || "Không đổi được.");
      });
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
      + (((d.vault || {}).xoa || []).length
          ? '<li>' + d.vault.xoa.length + ' mục trong bộ não '
            + '<span style="opacity:.6">(' + d.vault.xoa.map(x => esc(x.slug)).join(", ") + ')</span></li>'
          : "")
      + '</ul>'
      // Thứ người dùng đã sửa thì KHÔNG bị xoá, và phải nói ra - nếu không họ sẽ tưởng mất.
      + (((d.vault || {}).giu || []).length
          ? '<p style="margin-top:10px;color:var(--ok-ink,#2f855a)">Giữ lại vì bạn đã sửa: '
            + d.vault.giu.map(x => esc(x.slug)).join(", ") + '</p>'
          : "")
      + '<ul style="margin:0 0 0 18px">'
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
    // KHO nằm TRÊN, "đã cài" nằm dưới. Người vào trang này gần như luôn để TÌM thêm thứ gì
    // đó; xem lại thứ mình đã cài là việc thỉnh thoảng. Thứ tự cũ (đã cài trước) là thứ tự
    // của một trình quản lý gói, mà đây không phải trình quản lý gói.
    el.innerHTML =
      '<div class="cview-section"><h3>◆ Kho cài đặt</h3>'
      + '<div class="gcard-meta" style="max-width:740px">Trợ lý, kỹ năng, quy trình và công cụ '
      + 'làm sẵn theo từng lĩnh vực. Bấm <b>Cài</b> là Javis tải về, mở ra cho bạn xem có gì '
      + 'rồi mới hỏi.</div>'
      + '<div id="pkKho" style="margin-top:12px"></div></div>'
      + '<div class="cview-section"><h3>◆ Đã cài <span style="opacity:.5">'
      + ds.length + '</span></h3>'
      + (d.disabled
        ? '<div class="conn-guide" style="border-left:3px solid var(--warn,#e0a33e);padding-left:10px;margin-bottom:12px">'
          + 'Biến môi trường <code>JAVIS_DISABLE_PACKS</code> đang bật, nên mọi thứ cài thêm bị tắt hết.</div>'
        : "")
      + '<div class="prov-list" id="pkList">'
      + (ds.length ? ds.map(theGoi).join("")
                   : '<div class="mp-empty">Chưa cài gì thêm.</div>')
      + '</div>'
      + '<div style="margin-top:14px"><button class="mp-btn" id="pkChon">Cài từ tệp .zip</button> '
      + '<input type="file" id="pkFile" accept=".zip" style="display:none">'
      + '<span style="opacity:.6;margin-left:8px">tối đa ' + (d.max_mb || 25) + 'MB</span></div>'
      + '<div class="gcard-meta" style="margin-top:10px;opacity:.7">Thứ cài thêm nằm ở <code>'
      + esc(d.dir || "") + '</code>. Thả thẳng một thư mục vào đó cũng được, không bắt buộc '
      + 'phải qua tệp nén.</div>'
      + '</div>';

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
    // Lấy rồi XOÁ ngay: `_loaiCho` là ý định của một lần bấm tab, không phải trạng thái của
    // trang. Giữ lại thì lần sau vào từ thanh bên vẫn thấy lưới bị lọc mà không hiểu vì sao.
    const loaiDau = _loaiCho;
    _loaiCho = "";
    if (hostKho) veKho(el, hostKho, false, loaiDau);
  }

  // Mở kho với một loại đã lọc sẵn. Tab "Kho cài đặt" trên trang Trợ lý / Kỹ năng / Quy
  // trình / Plugin gọi hàm này, nên bốn trang KHÔNG ai nhúng một bản sao của lưới kho: chỉ có
  // một kho, một chỗ sửa, và người dùng học một lần là xong.
  function moKho(loai) {
    _loaiCho = LOAI[loai] ? loai : "";
    if (window.Alpine && Alpine.store("nav")) Alpine.store("nav").go("packs");
  }

  window.JavisPacks = { render: render, moKho: moKho, LOAI: LOAI };
})();
