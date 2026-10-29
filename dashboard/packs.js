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

  // Từ điển vi.json khi file này chạy DƯỚI NODE (test nạp nó bằng `new Function`). Trong thân
  // một `new Function` thì `require` KHÔNG tồn tại - nó là biến của module, không phải biến
  // toàn cục - nên mượn `process.mainModule.require`. Ba đường dò vì lối nạp đó không để lại
  // vị trí của chính file này. Trong trình duyệt không có `process`, cả khối rơi vào catch.
  let _tuVi = null;
  function tuDienVi() {
    if (_tuVi) return _tuVi;
    _tuVi = {};
    try {
      const req = process.mainModule.require;
      const p = req("path");
      const goc = p.dirname(process.mainModule.filename);
      [p.join(process.cwd(), "dashboard/i18n/vi.json"),
       p.join(goc, "../../dashboard/i18n/vi.json"),
       p.join(goc, "i18n/vi.json")].forEach((d) => {
        if (Object.keys(_tuVi).length) return;
        try { _tuVi = req(d) || {}; } catch (e) { /* thử đường kế tiếp */ }
      });
    } catch (e) { /* trình duyệt: không có process, và cũng không cần */ }
    return _tuVi;
  }

  // Chữ hiện ra lấy từ từ điển. Trong trình duyệt là window.t (i18n/index.js nạp trước file
  // này); dưới node là vi.json ở trên, để hàm trả về chữ THẬT chứ không phải mã khoá trần -
  // mấy test kho so đúng câu hiện ra trên thẻ.
  function tw(khoa, bien) {
    if (typeof window !== "undefined" && window.t) return window.t(khoa, bien);
    const s = tuDienVi()[khoa];
    if (s == null) return khoa;
    return String(s).replace(/\{(\w+)\}/g, (m, ten) =>
      (bien && bien[ten] != null) ? String(bien[ten]) : m);
  }
  // (i) button from info-tip.js; without it (node tests) the explanation is drawn inline.
  function infoBtn() { var J = typeof window !== "undefined" && window.JavisInfo; return J ? J.btn(tw("info.more")) : ""; }
  function infoBody(html) {
    var J = typeof window !== "undefined" && window.JavisInfo;
    return J ? J.body(html) : '<div class="info-body">' + html + "</div>";
  }
  // Tên nhóm của gói là tiếng Việt và là KHOÁ lọc (`data-kho-nhom`), nên chỉ dịch lúc vẽ; xem
  // `JavisI18n.catLabel`. Tên lạ do gói cộng đồng tự đặt thì giữ nguyên.
  function nhanNhom(ten) {
    const i = (typeof window !== "undefined") && window.JavisI18n;
    return i && typeof i.catLabel === "function" ? i.catLabel(ten) : (ten || "");
  }

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

  // Một cái khung cho MỌI hộp thoại của trang gói. `pkm=true` là biến thể dựng riêng cho luồng
  // cài: trên máy tính là thẻ giữa màn hình, trên điện thoại là tờ trượt từ đáy. CSS lo phần
  // hình, chỗ này chỉ gắn lớp.
  function modal(html, pkm) {
    let m = document.getElementById("packModal");
    if (!m) {
      m = document.createElement("div");
      m.id = "packModal";
      document.body.appendChild(m);
    }
    // Gán lại CẢ className chứ không add thêm: một hộp thoại mở tiếp sau hộp thoại khác phải
    // xoá sạch biến thể của lượt trước, nếu không hộp báo lỗi ngắn vẫn dính bố cục tờ trượt.
    m.className = "mp-overlay open" + (pkm ? " pkm-lop" : "");
    m.innerHTML = '<div class="mp-box' + (pkm ? " pkm" : "") + '">'
      + (pkm ? '<div class="pkm-nam"></div>' : "") + html + '</div>';
    m.querySelectorAll('[data-act="close"]').forEach(b => b.onclick = dong);
    // Bấm ra NGOÀI hộp là đóng - thói quen của mọi tờ trượt trên điện thoại. Đóng ở đây luôn
    // an toàn vì nó chỉ huỷ, không có nhánh nào "đóng tức là đồng ý".
    m.onclick = (e) => { if (e.target === m) dong(); };
    return m;
  }
  function dong() {
    const m = document.getElementById("packModal");
    if (m) { m.classList.remove("open"); m.onclick = null; }
  }

  // Đầu hộp thoại cài: ảnh đại diện, tên, dòng phụ, nút đóng. `ten` và `phu` là HTML đã escape
  // sẵn ở chỗ gọi - vài chỗ cần chèn <code> nên không escape lại ở đây.
  function pkmDau(g, ten, phu) {
    return '<div class="pkm-dau">' + (g ? veAvatar(g) : "")
      + '<div class="pkm-chu"><div class="pkm-ten">' + ten + '</div>'
      + (phu ? '<div class="pkm-phu">' + phu + '</div>' : "") + '</div>'
      + '<button class="mp-x" data-act="close" title="' + esc(tw("common.close")) + '">'
      + ic("x") + '</button></div>';
  }

  function dangCho(ten, dong2) {
    modal(pkmDau(null, esc(ten), "")
      + '<div class="pkm-danh"><div class="pkm-quay"></div><div>' + esc(dong2) + '</div></div>', true);
  }

  // Hỏng thì hiện đúng một khối đỏ nói ra chuyện gì, kèm bước dừng nếu server có trả. `lamLai`
  // là đường quay về chọn tệp khác - thiếu nó thì người dùng phải đóng hộp rồi mò lại từ đầu.
  function manHinhLoi(ten, loi, buoc, lamLai) {
    modal(pkmDau(null, esc(ten), "")
      + '<div class="pkm-than"><div class="pkm-canh do">'
      + '<div class="pkm-canh-tieu">' + ic("triangle-alert") + tw("store.err.title") + '</div>'
      + '<div>' + esc(loi) + '</div>'
      + (buoc ? '<div class="pkm-o-phu">' + tw("store.err.stage", { buoc: esc(buoc) })
          + '</div>' : "")
      + '</div></div>'
      + '<div class="pkm-chan">'
      + (lamLai ? '<button class="mp-btn" id="pkLai">' + tw("store.pick_other_file")
          + '</button>' : "")
      + '<button class="mp-btn primary" data-act="close">' + tw("common.close")
      + '</button></div>', true);
    const b = document.getElementById("pkLai");
    if (b) b.onclick = lamLai;
  }

  // Hộp hỏi lại dùng chung. Trả về Promise<bool>: gọi xong `await` là biết người dùng bấm gì.
  //
  // Vì sao không dùng `confirm()` của trình duyệt: nó không xuống dòng được, không in đậm được,
  // không liệt kê được cái gì sắp mất, và trên điện thoại nó là một hộp hệ thống bé xíu mà
  // người ta bấm OK theo phản xạ. Việc gỡ một dịch vụ đang có kết nối chạy thì đáng một câu
  // hỏi đọc được.
  function hoi(o) {
    return new Promise(resolve => {
      let xong = false;
      const tra = (v) => { if (!xong) { xong = true; resolve(v); } };
      const m = modal(pkmDau(o.icon ? { id: o.id || "", name: o.ten, icon: o.icon } : null,
          esc(o.tieu), o.phu ? esc(o.phu) : "")
        + '<div class="pkm-than">'
        + '<div class="pkm-canh ' + (o.mau || "vang") + '">'
        + '<div class="pkm-canh-tieu">' + ic(o.mau === "do" ? "triangle-alert" : "info")
        + esc(o.canhTieu || tw("store.confirm.title")) + '</div>'
        + '<div>' + (o.than || "") + '</div></div>'
        + (o.themHtml || "") + '</div>'
        + '<div class="pkm-chan">'
        + '<button class="mp-btn" id="pkHoiKhong">'
        + esc(o.khong || tw("common.cancel")) + '</button>'
        + '<button class="mp-btn ' + (o.mau === "do" ? "danger" : "primary") + '" id="pkHoiCo">'
        + esc(o.co || tw("store.confirm.yes")) + '</button></div>', true);
      // Nút HUỶ giữ tiêu điểm: gõ Enter theo quán tính không được phép là "đồng ý xoá".
      const k = document.getElementById("pkHoiKhong");
      k.focus();
      k.onclick = () => { dong(); tra(false); };
      document.getElementById("pkHoiCo").onclick = () => { dong(); tra(true); };
      m.querySelectorAll('[data-act="close"]').forEach(b => b.onclick = () => { dong(); tra(false); });
      m.onclick = (e) => { if (e.target === m) { dong(); tra(false); } };
    });
  }

  // Loại năng lực, thứ chia lưới kho thành các tab. Thứ tự ở đây LÀ thứ tự chip trên màn
  // hình, đi từ thứ người dùng hiểu nhanh nhất (trợ lý) tới thứ kỹ thuật nhất (kết nối).
  //
  // `bundle` cố ý KHÔNG có chip riêng: nó là chỗ rơi của mục khai loại lạ, và một chip tên
  // "Khác" chỉ mời người ta bấm vào để thấy lưới rỗng. Mục bundle vẫn hiện ở tab Tất cả.
  //
  // Icon lấy ĐÚNG icon trang tương ứng ở thanh bên (`console.js` VIEW_ICON), không chọn lại
  // cho đẹp: người dùng nhận ra "cái này là kỹ năng" bằng hình họ đã thấy hàng ngày.
  // `nhan` giữ KHOÁ từ điển chứ không giữ chữ: bảng này dựng lúc nạp file, sớm hơn lúc từ
  // điển về, nên chỗ VẼ mới tra bằng tw().
  const LOAI = {
    agent:     { nhan: "store.kind.agent",     icon: "bot",      trang: "workspace" },
    skill:     { nhan: "store.kind.skill",     icon: "puzzle",   trang: "skills" },
    workflow:  { nhan: "store.kind.workflow",  icon: "workflow", trang: "workspace" },
    tool:      { nhan: "store.kind.tool",      icon: "toolbox",  trang: "plugins" },
    connector: { nhan: "store.kind.connector", icon: "plug",     trang: "mcp" },
    bundle:    { nhan: "store.kind.bundle",    icon: "package",  trang: "" },
    // Recommended (0.370.0, "Recommended repos" until 0.376.0): not a kind but a tab of its own, listing every Store entry that follows
    // its author's GitHub repo (`upstream`), whatever its kind. It only shows when the Store has one.
    repo:      { nhan: "store.kind.repo",      icon: "git-branch", trang: "" },
  };
  const THU_TU_LOAI = ["agent", "skill", "workflow", "tool", "connector"];
  const theoGoc = g => !!(g && g.upstream && g.upstream.repo);
  const trongTab = (g, loai) => loai === "repo" ? theoGoc(g) : (g.kind || "bundle") === loai;

  // Trần dung lượng tệp .zip, do server nói (`/packs` trả `max_mb`). Giữ ở module để hộp thoại
  // chọn tệp nói đúng con số ngay cả khi nó mở lại sau một lần lỗi, lúc không còn `d` trong tay.
  let _maxMb = 25;
  // Folder the installs land in (`/packs` returns `dir`), told in the (i) of the .zip dialog.
  let _thuMuc = "";

  // Loại được chọn sẵn khi mở kho. `moKho()` đặt, `render()` lấy rồi XOÁ ngay - nó là ý định
  // của MỘT lần bấm tab, không phải trạng thái của trang.
  let _loaiCho = "";
  // Từ khoá điền sẵn vào ô tìm, cùng vòng đời với `_loaiCho`: đặt một lần rồi xoá ngay.
  let _timCho = "";
  // Trang đã dẫn người dùng sang kho, để vẽ nút quay lại. `null` = vào thẳng từ thanh bên.
  //
  // HAI biến chứ không một, và đây là lý do: `_veTrang` là ý định của MỘT lần bấm tab, còn
  // `_veLuot` là đường về của LƯỢT đang mở - nó phải sống qua mọi lần vẽ lại, vì trang tự vẽ
  // lại sau mỗi lần cài, gỡ hay bật tắt.
  //
  // Gộp làm một thì hoặc nút biến mất ngay sau khi cài xong một món (đúng lúc cần nó nhất),
  // hoặc nó dính lại: bấm tab từ trang Kỹ năng, rời đi, rồi vào kho từ THANH BÊN - và thấy
  // một cái nút "Quay lại Kỹ năng" trỏ về nơi mình không hề đi ra. Ca thứ hai trước 0.55.37
  // không xảy ra được vì kho không có mặt trên thanh bên; giờ có rồi.
  let _veTrang = null;
  let _veLuot = null;


  function vaultTom(v) {
    // Tóm tắt "gói này thêm gì vào bộ não", dạng "2 trợ lý, 1 kỹ năng".
    const TEN = { agents: "store.vault.agents", workflows: "store.vault.workflows",
                  skills: "store.vault.skills" };
    return Object.keys(TEN)
      .filter(k => ((v || {})[k] || []).length)
      .map(k => tw(TEN[k], { count: v[k].length }));
  }

  // ---- Màn hình xác nhận trước khi cài, vẽ hoàn toàn từ kết quả /packs/inspect ----
  //
  // Trật tự đọc được đặt cứng, vì đây là màn hình duy nhất trong app nơi người dùng đồng ý cho
  // mã lạ chạy trong máy chủ của họ: đây là gói gì → nó đến từ tệp nào và vân tay ra sao → nó
  // chạm vào đâu trong máy → cảnh báo → rồi mới tới hai cái nút.
  //
  // `tuTep` là hàm quay về bước chọn tệp. Có khi cài từ kho thì không có nó, và chân hộp hiện
  // "Huỷ" thay cho "Chọn tệp khác".
  //
  // `tuy` (0.73.0) cho lối vào từ chỗ khác ngoài trang kho, như "vừa quét QR Zalo xong thì mời cài gói
  // Zalo": `batSan` bật sẵn công tắc chạy ngay (người dùng vừa tự tay đấu đúng dịch vụ này, gói tắt thì
  // cài xong không có gì xảy ra), `sauKhiCai(r)` thay cho việc vẽ lại trang kho vào `el`.
  function manHinhDongY(d, el, tuTep, tuy) {
    tuy = tuy || {};
    const coMa = d.tier === "code";
    const batSan = !coMa || !!tuy.batSan;
    const py = (d.py_files || []);
    const kn = (d.connectors || []);
    const vt = vaultTom(d.vault);
    // Mỗi ô trong bảng là MỘT câu hỏi người cài thật sự hỏi, nên ô nào không có câu trả lời
    // thì biến mất chứ không hiện một dòng trống.
    const o = (nhan, gt, phu, rong) =>
      '<div class="pkm-o' + (rong ? " rong" : "") + '"><div class="pkm-o-nhan">' + nhan + '</div>'
      + gt + (phu ? '<div class="pkm-o-phu">' + phu + '</div>' : "") + '</div>';
    const bang = [
      o(tw("store.inspect.file"), '<div class="pkm-o-gt">'
        + esc(d.filename || tw("store.inspect.file_fallback"))
        + ' <span class="nhe">· ' + co(d.size) + '</span></div>'),
      o(tw("store.inspect.sha"),
        '<div class="pkm-o-ma">' + esc((d.sha256 || "").slice(0, 20)) + '…</div>',
        tw("store.inspect.sha_note")),
      kn.length ? o(tw("store.inspect.add_conn"),
        '<div class="pkm-o-gt">' + tw("store.inspect.conn_count", { count: kn.length }) + ' '
        + kn.map(x => '<code>' + esc(x) + '</code>').join(", ") + '</div>',
        tw("store.inspect.conn_note"), true) : "",
      // How name clashes and uninstall are handled: behind the (i) on the label.
      vt.length ? o(tw("store.inspect.add_vault") + infoBtn(),
        '<div class="pkm-o-gt">' + vt.join(", ") + '</div>'
        + infoBody(esc(tw("store.inspect.vault_note"))), "", true) : "",
    ].filter(Boolean).join("");

    modal(
      pkmDau(d, esc(nn(d.name, d.id))
          + (d.version ? '<span class="pkm-ver">v' + esc(d.version) + '</span>' : ""),
        '<code>' + esc(d.id) + '</code>'
          + (d.author && d.author.name
              ? ' · ' + tw("store.inspect.author", { ten: esc(d.author.name) }) : ""))
      + '<div class="pkm-than">'
      + (nn(d.description) ? '<p class="pkm-mota">' + esc(nn(d.description)) + '</p>' : "")
      + '<div class="pkm-bang">' + bang + '</div>'
      + (d.da_cai
          ? '<div class="pkm-canh vang"><div class="pkm-canh-tieu">' + ic("info")
            + tw("store.inspect.already.title") + '</div><div>'
            + tw("store.inspect.already.body",
                 { ver: '<b>' + esc(d.da_cai.version || "?") + '</b>' })
            + '</div></div>' : "")
      + (d.warning
          ? '<div class="pkm-canh vang"><div class="pkm-canh-tieu">' + ic("info")
            + tw("store.inspect.skipped.title") + '</div><div>' + esc(d.warning)
            + '</div></div>' : "")
      // Gói chưa qua review của người phát hành kho: nói dài hơn một dòng. Không chặn - ai tin
      // nguồn nào là lựa chọn của người cài - nhưng họ phải biết mình đang chọn gì.
      + ((d._tin && d._tin.verified === false)
          ? '<div class="pkm-canh vang"><div class="pkm-canh-tieu">' + ic("info")
            + tw("store.inspect.community.title") + '</div><div>'
            + tw("store.inspect.community.body") + '</div></div>' : "")
      // Khối cảnh báo cho gói có mã: KHÔNG gập được, không icon ổ khoá, không làm mềm chữ.
      // `permissions` trong manifest là lời khai của tác giả, không có tầng nào chặn, và
      // `min_mode` chỉ giới hạn cái MODEL được gọi chứ không giới hạn cái mã làm được.
      //
      // Từ 0.64.70 bỏ ô "gõ đúng mã gói": chủ app thấy nó chỉ thêm một bước gõ máy móc mỗi lần
      // cập nhật mà không làm ai đọc cảnh báo kỹ hơn. Cảnh báo vẫn hiện nguyên, nút Huỷ vẫn
      // nhận tiêu điểm mặc định, và công tắc "bật ngay" của gói có mã vẫn mặc định tắt.
      + (coMa
        ? '<div class="pkm-canh do"><div class="pkm-canh-tieu">' + ic("triangle-alert")
          + tw("store.inspect.code.title") + '</div>'
          + '<div>' + tw("store.inspect.code.body") + '</div>'
          + (py.length
              ? '<div class="pkm-o-phu">' + tw("store.inspect.code.files") + ' '
                + py.slice(0, 12).map(x => '<code>' + esc(x) + '</code>').join(", ")
                + (py.length > 12
                    ? " " + tw("store.inspect.code.more", { count: py.length - 12 }) : "")
                + '</div>' : "")
          + '</div>' : "")
      // Mặc định của công tắc đi theo BẬC của gói, không phải một hằng số:
      //
      //   có mã   tắt. Người dùng nên mở tệp ra xem trước khi cho nó chạy trong máy chủ mình.
      //   dữ liệu bật. Gói chỉ-dữ-liệu không chạy gì cả - nó chỉ thêm một khuôn connector hay
      //           vài tệp vào bộ não - nên cài xong mà nó nằm im là một cái bẫy chứ không phải
      //           một lớp an toàn. Vấp thật khi thử đường di trú: kết nối đang chết, người dùng
      //           bấm cài đúng gói cần, và KHÔNG có gì xảy ra vì gói vào máy ở trạng thái tắt.
      + '<button class="pkm-gat" id="pkBat" type="button" aria-pressed="' + (batSan ? "true" : "false") + '">'
      + '<span><span class="pkm-gat-t">' + tw("store.inspect.enable.title") + '</span>'
      + '<span class="pkm-gat-s">'
      + (batSan ? tw("store.inspect.enable.on_note")
                : tw("store.inspect.enable.off_note"))
      + '</span></span>'
      + '<span class="pkm-cong"><span></span></span></button>'
      + '</div>'
      + '<div class="pkm-chan"><span class="mp-note" id="pkNote"></span>'
      + '<button class="mp-btn" ' + (tuTep ? 'id="pkKhac"' : 'data-act="close"') + '>'
      + (tuTep ? tw("store.pick_other_file") : tw("common.cancel")) + '</button>'
      + '<button class="mp-btn primary" id="pkCai">' + tw("store.inspect.install_btn")
      + '</button></div>', true);

    // Nút bên TRÁI (huỷ / chọn tệp khác) nhận tiêu điểm mặc định: Enter theo quán tính không
    // được phép là "đồng ý cài mã lạ".
    const trai = document.querySelector("#packModal .pkm-chan .mp-btn");
    if (trai) trai.focus();
    const khac = document.getElementById("pkKhac");
    if (khac) khac.onclick = tuTep;
    const gat = document.getElementById("pkBat");
    gat.onclick = () => gat.setAttribute("aria-pressed",
      gat.getAttribute("aria-pressed") === "true" ? "false" : "true");
    const note = document.getElementById("pkNote");
    document.getElementById("pkCai").onclick = async () => {
      note.textContent = tw("store.installing");
      const r = await postJson("/packs/install", {
        staging_id: d.staging_id, consent_sha256: d.sha256,
        enable: gat.getAttribute("aria-pressed") === "true",
        source: d.source || { kind: "zip" },
        // Brain ĐANG MỞ. `currentBrainPath` là hàm toàn cục mà app.js phơi ra và cả
        // console.js lẫn chat-render.js đều dùng - đi qua nó thay vì tự đoán chỗ khác.
        brain: (typeof currentBrainPath === "function" ? currentBrainPath() : "") || "brain",
      });
      if (!r || !r.ok) {
        note.textContent = (r && r.error) || tw("store.install_failed");
        return;
      }
      dong();
      if (typeof tuy.sauKhiCai === "function") tuy.sauKhiCai(r);
      else veLai(el);
    };
  }

  async function tuUrl(el, url, expect, tin, tuy) {
    // Tải từ kho hay từ link đều dừng ở bước SOI rồi mở đúng màn hình xác nhận như tệp tải
    // lên. Đường từ kho về máy không được phép ngắn hơn đường từ tệp: cùng một thứ để đọc,
    // cùng một chốt dấu vân tay.
    dangCho(tw("store.downloading.title"), tw("store.downloading.body"));
    const d = await postJson("/packs/install-url", { url: url, expect_sha256: expect || "" });
    if (!d || !d.ok) {
      manHinhLoi(tw("store.install_from_store"),
        (d && d.error) || tw("store.download_failed"), d && d.stage);
      return;
    }
    d._tin = tin || null;
    manHinhDongY(d, el, null, tuy);
  }

  // Mở thẳng màn hình đồng ý cài của MỘT gói trong kho, theo id, từ bất kỳ trang nào (0.73.0).
  // Lối vào đầu tiên: quét QR Zalo xong thì mời cài `javis.zalo`, vì ba tool Zalo mở rộng đã rời
  // app sang kho. Đi qua ĐÚNG đường cài từ kho (`tuUrl`: tải, soi, hiện mã, chốt vân tay), không
  // có đường tắt nào cài mà người dùng chưa thấy màn hình này.
  //
  // Trả "da_cai" khi gói đã cài và đang bật (không mở gì), "da_tat" khi đã cài nhưng đang tắt
  // (bật lại là việc của người dùng ở trang kho), "khong_co" khi kho không có gói đó, "mo" khi
  // đã mở màn hình đồng ý.
  async function caiGoiKho(id, tuy) {
    tuy = tuy || {};
    let ds;
    try { ds = await (await fetch("/packs/store")).json(); } catch (e) { ds = null; }
    const g = ((ds && ds.packs) || []).find(x => x && x.id === id && x.nguon !== "app");
    if (!g || !g.download || !g.download.url) return "khong_co";
    if (g.installed) return g.enabled === false ? "da_tat" : "da_cai";
    const el = tuy.el || document.createElement("div");
    await tuUrl(el, g.download.url, g.download.sha256, g, tuy);
    return "mo";
  }

  // ---- Gỡ một connector ĐI KÈM APP khỏi kho Kết nối ----
  //
  // Ba bước, và bước nào cũng cần thiết: hỏi server xem cái gì sắp dừng (`plan`), hỏi NGƯỜI
  // DÙNG một câu đọc được, rồi mới gỡ.
  //
  // Trước 0.55.36 đường này gỡ THẲNG khi connector chưa có kết nối nào - một cú bấm nhầm vào
  // dấu × bé ở góc thẻ là dịch vụ biến khỏi kho, không ai hỏi câu nào. Câu hỏi chỉ hiện đúng
  // trong ca đã có kết nối chạy, tức là ca hiếm hơn, còn ca thường thì im lặng.
  //
  // Dùng chung cho cả thẻ trong kho lẫn dấu × trên trang Kết nối - hai lối vào một hành động
  // thì phải hỏi y hệt nhau. Vì thế nó nằm ở `window.JavisPacks`.
  async function goApp(ten, id) {
    const p = await postJson("/connect/core-toggle", { id: id, off: true, plan: true });
    if (!p || !p.ok) {
      return { ok: false, error: (p && p.error) || tw("store.conn.read_failed") };
    }
    const kn = p.connections || [];
    const dongY = await hoi({
      tieu: tw("store.conn.remove_title", { ten: ten }),
      mau: "do", co: tw("proj.remove_short"), khong: tw("store.conn.keep"),
      canhTieu: kn.length
        ? tw("store.conn.will_stop", { count: kn.length })
        : tw("store.conn.sure"),
      than: (kn.length
        ? tw("store.conn.stop_body",
             { ten: "<b>" + kn.map(x => esc(x.label)).join(", ") + "</b>" })
        : tw("store.conn.gone_body")),
    });
    if (!dongY) return { ok: false, huy: true };
    const r = await postJson("/connect/core-toggle", { id: id, off: true, confirm: true });
    return { ok: !!(r && r.ok), error: (r && r.error) || tw("store.conn.remove_failed") };
  }

  // ---- Ảnh đại diện của một mục ----
  // Ưu tiên icon THẬT của mục (connector đi kèm app đều có logo). Không có thì icon của loại trên
  // ô màu riêng theo id: đó là chỗ dựa của lưới, mắt nhận ra hàng nào là hàng nào trước khi đọc chữ.
  const MAU_AVATAR = ["#2563eb", "#e8590c", "#0f766e", "#16a34a", "#7c3aed", "#0891b2",
                      "#ca8a04", "#dc2626", "#0d9488", "#db2777"];

  function mauTheoId(id) {
    let h = 0;
    for (let i = 0; i < String(id).length; i++) h = (h * 31 + String(id).charCodeAt(i)) >>> 0;
    return MAU_AVATAR[h % MAU_AVATAR.length];
  }

  function veAvatar(g) {
    // Thứ tự, đúng như `console.js iconInner` cho phần logo:
    //   đường dẫn/URL ảnh (logo hãng)  -> <img>
    //   tên icon Lucide                -> SVG trên ô màu nhạt
    //   trợ lý (agent)                 -> chân dung trợ lý y như trang Cộng sự (`JavisAvatar`)
    //   còn lại                        -> icon của LOẠI (skill = mảnh ghép, quy trình, công cụ...)
    //
    // `ic()` KHÔNG tự nhận đường dẫn (đó là việc của `iconInner`), nên bỏ nhánh <img> là mọi
    // logo hãng hiện thành dấu hỏi - đúng lỗi thấy trên màn hình bản dựng đầu.
    //
    // 0.376.0: ô chữ cái đậm màu ("Su", "LP") bị chủ repo chê là xấu và không nói lên gì. Giờ ô là
    // icon của đúng loại năng lực, màu riêng theo id nhưng nhạt nền, nên lưới đọc ra ngay đâu là
    // skill, đâu là trợ lý, mà các thẻ cạnh nhau vẫn khác màu.
    const src = String((g && g.icon) || "");
    if (/^(https?:|\/)/.test(src)) {
      return '<div class="kho-ava kho-ava-img"><img src="' + esc(src)
        + '" alt="" loading="lazy"></div>';
    }
    const kind = (g && g.kind) || "bundle";
    const A = typeof window !== "undefined" && window.JavisAvatar;
    if (kind === "agent" && A && A.html && window.JavisPet) {
      try { return '<div class="kho-ava kho-ava-agent">' + A.html({ slug: g.id || "" }, 40) + '</div>'; }
      catch (e) { /* the mascot library is not ready: fall back to the kind icon */ }
    }
    const coIcon = src && window.Icons && window.Icons.has && window.Icons.has(src);
    const ten = coIcon ? src : (LOAI[kind] || LOAI.bundle).icon;
    return '<div class="kho-ava kho-ava-ic" style="--kho-mau:' + mauTheoId(g.id) + '">' + ic(ten) + '</div>';
  }

  // ---- Nút trên thẻ ----
  // Bốn tình huống, và chúng KHÔNG cùng một hành động bên dưới. Mục tải từ kho thì cài là tải
  // về rồi qua màn hình xác nhận, gỡ là trình gỡ gói. Connector đi kèm app thì không tải gì cả,
  // "gỡ" chỉ là ghi vào sổ đã-gỡ (`core_off`) để nó biến khỏi kho Kết nối - tệp trong `system/`
  // không hề bị đụng, vì cây code là read-only trên Docker và bị `git pull` ghi đè trên bản
  // native. Trộn hai thứ này làm một là gỡ nhầm hoặc gỡ hụt.
  // Gói ĐÃ CÀI mà kho đang công bố số hiệu khác. Một hàm dùng chung cho cả nút, thẻ, bộ đếm
  // và bộ lọc: trước 0.55.42 phép so này chỉ nằm trong `nutThe`, nên cái nút "Có bản mới" là
  // thứ DUY NHẤT trong toàn giao diện biết chuyện đó - không đếm được, không lọc được, và
  // không thấy được từ tab khác.
  //
  // So bằng KHÁC chứ không phải LỚN HƠN, có chủ ý: kho là nguồn sự thật về bản đang phát
  // hành, nên một gói bị RÚT về bản cũ (bản mới hỏng) cũng phải kéo lại được. So kiểu lớn hơn
  // sẽ khoá người dùng ở đúng cái bản vừa bị rút.
  //
  // Connector đi kèm app không bao giờ tính: chúng không tải từ đâu cả (`download.url` rỗng).
  function coBanMoi(g) {
    return !!(g && g.nguon !== "app" && g.installed && g.installed_version && g.version
              && g.installed_version !== g.version);
  }

  function nutThe(g) {
    const moi = coBanMoi(g);
    if (g.nguon === "app") {
      return g.installed
        ? { nhan: tw("store.btn.remove_from_javis"), lop: "kho-btn kho-btn-go", act: "coreoff" }
        : { nhan: tw("store.btn.reinstall"), lop: "kho-btn kho-btn-chinh", act: "coreon" };
    }
    if (moi) {
      return { nhan: tw("store.btn.update_to", { ver: esc(g.version) }),
               lop: "kho-btn kho-btn-chinh", act: "cai" };
    }
    if (g.installed) {
      return { nhan: tw("store.btn.uninstall"), lop: "kho-btn kho-btn-go", act: "go", tat: true };
    }
    return { nhan: tw("store.btn.install"), lop: "kho-btn kho-btn-chinh", act: "cai" };
  }

  // Dòng trạng thái dưới mô tả. Nói ĐỦ HAI SỐ khi có bản mới, vì "đang chạy cái gì" và "kho
  // có cái gì" là hai câu hỏi khác nhau và người dùng cần cả hai để quyết định có bấm không.
  function dongDaCai(g) {
    if (!g.installed) return "";
    if (g.nguon === "app" || !g.installed_version) {
      return '<div class="kho-daicai">' + ic("check") + ' ' + tw("store.installed_here")
        + '</div>';
    }
    if (coBanMoi(g)) {
      return '<div class="kho-daicai moi">' + ic("arrow-up") + ' '
        + tw("store.running_store_has",
             { cai: esc(g.installed_version), kho: esc(g.version) }) + '</div>';
    }
    return '<div class="kho-daicai">' + ic("check") + ' '
      + tw("store.installed_latest", { ver: esc(g.installed_version) }) + '</div>';
  }

  // "Updated from the author" line: the author's GitHub repo as a link, and the day the Store last took a new
  // version from it. The repo is a plain owner/name (checked server-side in `packs_store._upstream`).
  function dongGoc(g) {
    if (!theoGoc(g)) return "";
    const u = g.upstream;
    return '<div class="prov-meta kho-goc">' + ic("git-branch") + ' ' + tw("store.upstream_follows")
      + ' <a href="https://github.com/' + esc(u.repo) + '" target="_blank" rel="noopener noreferrer">'
      + esc(u.repo) + '</a>'
      + (u.synced ? ' · ' + esc(tw("store.upstream_synced", { ngay: u.synced })) : "") + '</div>';
  }

  function theKho(g) {
    const lo = LOAI[g.kind] || LOAI.bundle;
    const n = nutThe(g);
    // Số hiệu KHÔNG nằm ở đây khi gói đã cài. Dòng meta lấy `g.version` (số của KHO), nên thẻ
    // của một gói đã cài bản cũ hiện "v1.0.1" ngay trên dòng "Đã cài trên máy" - tức là nói
    // với người dùng rằng họ đang chạy 1.0.1, đúng lúc họ chạy 1.0.0. Gói đã cài thì để dòng
    // "Đã cài" kể chuyện phiên bản, một chỗ duy nhất và nói đủ cả hai số.
    const meta = [g.id, g.installed ? "" : (g.version ? "v" + g.version : ""),
                  (g.author && g.author.name) || ""].filter(Boolean).map(esc).join(" · ");
    // A description shows at most three lines and an ellipsis (`.kho-mo-ta`, 0.407.0); a long one
    // also gets the (i) on the name, which holds the full text.
    const moTa = nn(g.description);
    const dai = moTa.length > 90;
    return '<div class="cat-card kho-the" data-loai="' + esc(g.kind || "bundle") + '"'
      + ' data-nhom="' + esc(g.nhom || "") + '" data-ng="' + (g.verified ? "1" : "0") + '">'
      // Tags (0.390.0, owner): no kind tag (the open tab already says it) and no official/community
      // tag (community packs keep their own filter and their own warning on the confirm screen).
      // Of the tier only the exception shows: "Runs code", a small amber chip beside the group one.
      // "Data only" is most packs and the safe case, so a tag on every card would say nothing.
      // The title line keeps just the name and the (i).
      + '<div class="kho-dau">' + veAvatar(g)
      + '<span class="kho-chips">'
      + (g.tier === "code" ? '<span class="kho-chip-ma">' + tw("store.tier.code") + '</span>' : "")
      + '<span class="kho-nhom">' + esc(g.nhom ? nhanNhom(g.nhom) : tw(lo.nhan)) + '</span>'
      + '</span></div>'
      + '<div class="kho-ten">' + esc(nn(g.name, g.id))
      + (dai ? infoBtn() : "")
      + '</div>'
      + '<div class="cat-desc kho-mo-ta">' + esc(moTa) + '</div>'
      + (dai ? infoBody(esc(moTa)) : "")
      + '<div class="prov-meta">' + meta + '</div>'
      + dongGoc(g)
      + dongDaCai(g)
      + '<div class="kho-nut">'
      // Bật/tắt tạm một gói đã cài. Trước 0.55.34 nút này chỉ có ở khối "Đã cài" dưới trang;
      // khối đó bỏ đi rồi nên nó về đây, chứ không được biến mất - tắt tạm KHÁC gỡ hẳn, và
      // người ta cần nó khi một gói đang gây phiền mà chưa muốn mất cấu hình.
      + (n.tat
          ? '<button class="kho-btn kho-btn-phu" data-kho-act="tat" data-kho-id="' + esc(g.id)
            + '">' + (g.enabled === false ? tw("cb.bat") : tw("cb.tat")) + '</button>'
          : "")
      + '<button class="' + n.lop + '" data-kho-act="' + n.act + '" data-kho-id="' + esc(g.id) + '">'
      + n.nhan + '</button></div>'
      + '</div>';
  }

  // Trạng thái lưới kho. Để ở module vì mọi lần bấm tab, bấm nhóm hay đổi trang đều chỉ VẼ LẠI
  // từ dữ liệu đã tải, không gọi lại mạng.
  let _kho = { dl: null, loai: "connector", nhom: "Tất cả", trang: 1, tim: "", sap: "" };
  // Sort box (owner, 0.407.0). Only orders that need no server: install counts and stars wait for
  // a central server (owner, 2026-10-29: later, with the business edition). The choice is a
  // per-device convenience, so it lives in localStorage and the page works without it.
  const SAP = { "de-xuat": "store.sort.recommended", "moi": "store.sort.recent", "ten": "store.sort.name" };
  function docSap() {
    try { const v = localStorage.getItem("javis.kho.sap"); return SAP[v] ? v : "de-xuat"; }
    catch (e) { return "de-xuat"; }
  }
  // Stable: ties keep the catalog's own order, which is how the Store owner lays it out.
  // Recommended = packs that follow their author's repo first, then catalog order.
  function sapXep(ds, kieu) {
    const co = ds.map((g, i) => [g, i]);
    const theoThu = (a, b) => a[1] - b[1];
    if (kieu === "moi") {
      co.sort((a, b) => String(b[0].updated || "").localeCompare(String(a[0].updated || "")) || theoThu(a, b));
    } else if (kieu === "ten") {
      co.sort((a, b) => nn(a[0].name, a[0].id).localeCompare(nn(b[0].name, b[0].id), "vi") || theoThu(a, b));
    } else {
      co.sort((a, b) => (theoGoc(b[0]) ? 1 : 0) - (theoGoc(a[0]) ? 1 : 0) || theoThu(a, b));
    }
    return co.map(x => x[0]);
  }
  // 18, not 20 (owner, 2026-10-28): it splits evenly into the 3 and 2 column grids, so the last
  // row of a full page is never left half empty.
  const MOI_TRANG = 18;
  // Danh mục cũ hơn ngần này (giây) thì trang Kho tự lấy lại một lần ở nền. Xem `veKho`.
  const CU_QUA = 30 * 60;

  async function veKho(el, host, lamMoi, loaiDau, timDau) {
    host.innerHTML = '<div class="mp-empty">' + tw("store.catalog_loading") + '</div>';
    let d;
    try { d = await (await fetch("/packs/store" + (lamMoi ? "?refresh=1" : ""))).json(); }
    catch (e) { d = { ok: false, error: String(e) }; }
    if (!d || !d.ok) {
      // Kho không tới được thì KHÔNG phải là hỏng cả trang: cài từ tệp vẫn chạy như thường.
      host.innerHTML = '<div class="mp-empty">'
        + tw("store.catalog_failed", { loi: esc((d && d.error) || tw("store.catalog_failed_reason")) })
        + '<br>' + tw("store.catalog_failed_hint") + '</div>';
      return;
    }
    _kho.dl = d;
    _kho.trang = 1;
    _kho.tim = timDau || "";
    if (loaiDau && LOAI[loaiDau]) _kho.loai = loaiDau;
    _kho.nhom = "Tất cả";
    veLuoi(el, host);

    // Danh mục cache 6 giờ ở phía server (`packs_store.TTL`). Với việc TÌM một gói mới thì 6
    // giờ là hợp lý. Với việc BIẾT gói mình đã cài có bản mới chưa thì nó sai một cách im
    // lặng: mở trang ra vẫn là danh mục của sáng nay, không dấu hiệu gì, và người dùng kết
    // luận là Javis không có tính năng cập nhật.
    //
    // Nên khi bản đang cầm đã quá cũ, lấy lại MỘT lần ở nền rồi vẽ lại. Không đụng TTL của
    // server (các nơi khác vẫn hưởng cache), chỉ trang Kho mới trả cái giá một request nhỏ.
    // Chốt `_kho.dl === d` để nếu người dùng đã bấm Làm mới hay đổi trang trong lúc chờ thì
    // bản về sau không đè lên thứ mới hơn.
    const tuoi = d.fetched_at ? (Date.now() / 1000 - Number(d.fetched_at)) : 0;
    if (!lamMoi && tuoi > CU_QUA) {
      fetch("/packs/store?refresh=1")
        .then(r => r.json())
        .then(d2 => {
          if (d2 && d2.ok && _kho.dl === d) { _kho.dl = d2; veLuoi(el, host); }
        })
        .catch(() => {});
    }
  }

  // Vẽ lại lưới kho = thay sạch `host.innerHTML`, nên Ô TÌM cũng bị vứt đi và dựng lại. Gõ một
  // chữ là ô đang gõ rời khỏi trang, con trỏ rơi về `body`, phải bấm chuột vào ô mới gõ được
  // chữ thứ hai - đúng lỗi chủ repo báo (2026-09-07): "tìm kiếm chỉ viết được 1 chữ cái 1 lần".
  // Gọi `focus()` trên ô CŨ không cứu được gì vì nó không còn nằm trong trang nữa; phải trả con
  // trỏ cho ô MỚI. Tách thành cặp ghi/trả để bọc quanh đúng một lần thay `innerHTML`.
  function ghiConTro(host) {
    const cu = host.querySelector ? host.querySelector("#pkQ") : null;
    if (!cu || document.activeElement !== cu) return null;
    return { cu: cu, dau: cu.selectionStart, cuoi: cu.selectionEnd };
  }

  function traConTro(host, nho) {
    if (!nho) return;
    const moi = host.querySelector ? host.querySelector("#pkQ") : null;
    if (!moi || moi === nho.cu) return;
    try { moi.focus(); } catch (e) {}
    // Gõ chèn vào GIỮA chuỗi thì con trỏ phải ở lại giữa. Ô mới dựng từ `value=` nên mặc định
    // con trỏ nhảy xuống cuối, làm mấy chữ gõ tiếp bị lộn chỗ.
    try {
      if (nho.dau !== null && nho.dau !== undefined) moi.setSelectionRange(nho.dau, nho.cuoi);
    } catch (e) {}
  }

  // A new page starts at its first card. The pager sits under the last row, so without this the
  // next page opens at its bottom. Only scrolls UP, and stops below the pinned navbar.
  function lenDauLuoi(host) {
    try {
      const than = host.querySelector(".kho-than");
      const thanh = host.querySelector(".kho-thanh");
      let sc = than && than.parentElement;
      while (sc && sc !== document.body && !/(auto|scroll)/.test(getComputedStyle(sc).overflowY)) sc = sc.parentElement;
      if (!than || !sc) return;
      const lech = than.getBoundingClientRect().top - sc.getBoundingClientRect().top
        - (thanh ? thanh.offsetHeight : 0) - 8;
      if (lech < 0) sc.scrollTop += lech;
    } catch (e) { /* no layout (node tests): nothing to scroll */ }
  }

  function veLuoi(el, host) {
    const d = _kho.dl || { packs: [] };
    const ds = d.packs || [];
    if (_kho.loai === "repo" && !ds.some(theoGoc)) _kho.loai = "skill";
    const cungLoai = ds.filter(g => trongTab(g, _kho.loai));
    const daCai = cungLoai.filter(g => g.installed);
    // Đếm bản mới trên MỌI loại, không chỉ tab đang mở. Đây là chỗ sửa cái lỗi nặng nhất của
    // tầng này: lưới lọc theo `_kho.loai` và tab mặc định là "Kết nối", nên một gói Kỹ năng có
    // bản mới thì không có gì trong giao diện nói ra - phải tình cờ bấm đúng tab mới thấy.
    const capNhat = ds.filter(coBanMoi);
    const capNhatLoai = cungLoai.filter(coBanMoi);

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
    const laMoi = _kho.nhom === "Có bản mới";
    const q = _kho.tim.trim().toLowerCase();
    if (!SAP[_kho.sap]) _kho.sap = docSap();
    const hop = sapXep(cungLoai, _kho.sap).filter(g =>
      (_kho.nhom === "Tất cả"
        || (laDaCai ? g.installed
            : laMoi ? coBanMoi(g)
            : laCongDong ? !g.verified
            : (g.nhom || "Khác") === _kho.nhom))
      && (!q || (nn(g.name, g.id) + " " + nn(g.description) + " " + g.id).toLowerCase().includes(q)));

    let gioLay = "";
    try {
      if (d.fetched_at) {
        gioLay = new Date(d.fetched_at * 1000)
          .toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
      }
    } catch (e) { gioLay = ""; }

    const soTrang = Math.max(1, Math.ceil(hop.length / MOI_TRANG));
    const trang = Math.min(Math.max(1, _kho.trang), soTrang);
    _kho.trang = trang;
    const hienThi = hop.slice((trang - 1) * MOI_TRANG, trang * MOI_TRANG);

    const dsLoai = (ds.some(theoGoc) ? ["repo"] : []).concat(THU_TU_LOAI);
    // The same kinds as a <select> for phones (owner, 2026-10-28: a dropdown fits a phone better
    // than six squeezed buttons). Each option keeps its count and its "N new" badge as text.
    const chonLoai = dsLoai.map(k => {
      const trong = ds.filter(g => trongTab(g, k));
      const nMoi = trong.filter(coBanMoi).length;
      return '<option value="' + k + '"' + (k === _kho.loai ? " selected" : "") + '>'
        + esc(tw(LOAI[k].nhan)) + ' (' + trong.length + ')'
        + (nMoi ? ' · ' + esc(tw("store.tab_new_count", { count: nMoi })) : "") + '</option>';
    }).join("");
    const tabLoai = dsLoai.map(k => {
      const on = k === _kho.loai;
      const trong = ds.filter(g => trongTab(g, k));
      const nMoi = trong.filter(coBanMoi).length;
      return '<button class="kho-tab' + (on ? " on" : "") + '" data-kho-loai="' + k + '">'
        + esc(tw(LOAI[k].nhan))
        + ' <span class="kho-dem">' + trong.length + '</span>'
        // Huy hiệu ngay trên TAB, không chỉ trong lưới: mục đích là thấy được bản mới nằm ở
        // tab nào mà không phải bấm thử từng tab một.
        + (nMoi ? ' <span class="kho-dem moi">' + tw("store.tab_new_count", { count: nMoi })
                  + '</span>' : "")
        + '</button>';
    }).join("");

    const hangNhom = (ten, so, on, ngan, nhan) =>
      '<button class="kho-nav' + (on ? " on" : "") + (ngan ? " ngan" : "") + '" data-kho-nhom="'
      + esc(ten) + '"><span>' + esc(nhan || ten) + '</span><span class="kho-navdem">' + so + '</span></button>';

    // Băng báo bản mới, đặt TRÊN tabs vì nó nói chuyện của cả kho chứ không riêng tab nào.
    // Mỗi chip nhảy thẳng sang đúng tab và lọc sẵn, nên từ lúc thấy tới lúc bấm Cập nhật là
    // một cú bấm.
    const bangMoi = capNhat.length
      ? '<div class="kho-bao-moi">' + ic("arrow-up")
        + '<span><b>' + tw("store.updates_count", { count: capNhat.length }) + '</b> '
        + tw("store.updates_tail") + '</span>'
        + THU_TU_LOAI.filter(k => capNhat.some(g => (g.kind || "bundle") === k))
            .map(k => '<button class="kho-chip" data-kho-moi="' + k + '">'
              + esc(tw(LOAI[k].nhan)) + ' ('
              + capNhat.filter(g => (g.kind || "bundle") === k).length + ')</button>').join("")
        + '</div>'
      : "";

    // Group filter as a native <select> in the pinned bar, shown on phones in place of the column:
    // a wrapped row of ten pills pushed the cards a full screen down, and a sideways strip hides
    // the groups at its end. The select shows every group and costs one row.
    // One list feeds both: [filter key, count, label, starts the field groups].
    const dsNhom = [["Tất cả", cungLoai.length, tw("studio.all")], ["Đã cài", daCai.length, tw("ol.installed")]]
      .concat(capNhatLoai.length ? [["Có bản mới", capNhatLoai.length, tw("cs.upd_have_new")]] : [])
      .concat(congDong.length ? [["Cộng đồng", congDong.length, tw("store.community")]] : [])
      .concat(tenNhom.map((t, i) => [t, dem[t], nhanNhom(t), i === 0]));
    const chonNhom = dsNhom.map(([ten, so, nhan]) => '<option value="' + esc(ten) + '"'
      + (_kho.nhom === ten ? " selected" : "") + '>' + esc(nhan) + ' (' + so + ')</option>').join("");

    // Refresh and Install from .zip, drawn twice: in the navbar (computer) and beside the search
    // box (phone), CSS shows one. Hence data attributes rather than ids. The catalog time rides on
    // the Refresh tooltip: without it "why don't I see the new version" has no answer, but as
    // text in the navbar it pushed Refresh past the edge (0.390.0).
    const nutHd = '<button class="mp-btn kho-hd-btn" data-kho-lammoi="1"'
      + (gioLay ? ' title="' + esc(tw("store.catalog_at", { luc: gioLay })) + '"' : "")
      + ' aria-label="' + esc(tw("store.refresh")) + '">'
      + ic("rotate-cw") + '<span>' + tw("store.refresh") + '</span></button>'
      + '<button class="mp-btn kho-hd-btn" data-kho-zip="1" aria-label="' + esc(tw("store.from_zip")) + '">'
      + ic("upload-cloud") + '<span>' + tw("store.from_zip") + '</span></button>';

    const nhoConTro = ghiConTro(host);
    host.innerHTML =
      (d.stale ? '<div class="conn-guide" style="border-left:3px solid var(--warn,#e0a33e);padding-left:10px;margin-bottom:12px">' + tw("store.stale") + '</div>' : "")
      + bangMoi
      // The Store's own navbar: kind tabs on the left, Refresh and Install from .zip on the right,
      // one row that stays pinned while the cards scroll (owner, 2026-10-28). On phones the six
      // tabs need the whole row, so the two buttons move next to the search box as icons.
      + '<div class="kho-thanh">'
      + '<div class="kho-tabs">' + tabLoai + '</div>'
      + '<select class="js-input kho-chon-loai" id="pkLoai" aria-label="' + esc(tw("store.kind_label")) + '">'
      + chonLoai + '</select>'
      + '<select class="js-input kho-chon-nhom" id="pkNhom" aria-label="' + esc(tw("studio.groups")) + '">'
      + chonNhom + '</select>'
      + '<div class="kho-hd">'
      + nutHd
      + '</div></div>'
      + '<div class="kho-than">'
      + '<div class="kho-chinh">'
      + '<div class="cat-tools kho-loc">'
      // Width comes from CSS, not written here: on a phone this box takes the whole row, and an
      // inline style cannot be overridden by a media query without !important.
      + '<input class="js-input kho-tim" id="pkQ" placeholder="'
      + esc(tw("store.search_ph", { loai: tw(LOAI[_kho.loai].nhan) }))
      + '" value="' + esc(_kho.tim) + '">'
      + '<span class="kho-hd kho-hd-dt">' + nutHd + '</span>'
      + '<label class="kho-sap"><span>' + tw("store.sort_label") + '</span>'
      + '<select class="js-input" id="pkSap">'
      + Object.keys(SAP).map(k => '<option value="' + k + '"' + (k === _kho.sap ? " selected" : "") + '>'
          + esc(tw(SAP[k])) + '</option>').join("")
      + '</select></label>'
      + '<span class="prov-meta kho-so-muc">'
      + (laDaCai ? tw("store.count_installed", { count: hop.length })
         : laMoi ? tw("store.count_updates", { count: hop.length })
         : laCongDong ? tw("store.count_community", { count: hop.length })
         : tw("store.count_items", { count: hop.length })) + '</span>'
      + '</div>'
      + '<div class="cat-grid" id="pkGrid">' + hienThi.map(theKho).join("") + '</div>'
      + (hienThi.length ? "" : '<div class="mp-empty">'
          + (laDaCai ? tw("store.empty_installed", { loai: esc(tw(LOAI[_kho.loai].nhan)) })
             : laMoi ? tw("store.empty_updates", { loai: esc(tw(LOAI[_kho.loai].nhan)) })
             : tw("store.empty_filter")) + '</div>')
      + (soTrang > 1
          ? '<div class="kho-trang"><span class="prov-meta">'
            + tw("store.paging", { tu: ((trang - 1) * MOI_TRANG + 1),
                                   den: Math.min(trang * MOI_TRANG, hop.length),
                                   tong: hop.length })
            + '</span><span class="kho-trang-so">'
            + '<button class="kho-so" data-kho-trang="' + (trang - 1) + '"' + (trang === 1 ? " disabled" : "")
            + ' aria-label="' + esc(tw("store.page_prev")) + '">' + ic("chevron-left") + '</button>'
            + Array.from({ length: soTrang }, (_, i) =>
                '<button class="kho-so' + (i + 1 === trang ? " on" : "") + '" data-kho-trang="'
                + (i + 1) + '">' + (i + 1) + '</button>').join("")
            + '<button class="kho-so" data-kho-trang="' + (trang + 1) + '"' + (trang === soTrang ? " disabled" : "")
            + ' aria-label="' + esc(tw("store.page_next")) + '">' + ic("chevron-right") + '</button>'
            + '</span></div>'
          : "")
      + '</div>'
      // Group column on the RIGHT (owner, 2026-10-28): the app sidebar is already on the left,
      // and two menus side by side read as one long menu.
      + '<div class="kho-cot">'
      + '<div class="kho-cot-tieu">' + tw("studio.groups") + '</div>'
      + dsNhom.map(([ten, so, nhan, ngan]) => hangNhom(ten, so, _kho.nhom === ten, !!ngan, nhan)).join("")
      + '</div>'
      + '</div>';

    traConTro(host, nhoConTro);

    const lai = () => veLuoi(el, host);
    const doiLoai = (k) => { _kho.loai = k; _kho.nhom = "Tất cả"; _kho.trang = 1; _kho.tim = ""; lai(); };
    host.querySelectorAll("[data-kho-loai]").forEach(b => b.onclick = () => doiLoai(b.dataset.khoLoai));
    const sl = host.querySelector ? host.querySelector("#pkLoai") : null;
    if (sl) sl.onchange = () => doiLoai(sl.value);
    host.querySelectorAll("[data-kho-nhom]").forEach(b => b.onclick = () => {
      _kho.nhom = b.dataset.khoNhom; _kho.trang = 1; lai();
    });
    // Chip trên băng báo: nhảy sang tab đó VÀ lọc sẵn còn mỗi gói có bản mới.
    host.querySelectorAll("[data-kho-moi]").forEach(b => b.onclick = () => {
      _kho.loai = b.dataset.khoMoi; _kho.nhom = "Có bản mới";
      _kho.trang = 1; _kho.tim = ""; lai();
    });
    host.querySelectorAll("[data-kho-trang]").forEach(b => b.onclick = () => {
      _kho.trang = Number(b.dataset.khoTrang); lai(); lenDauLuoi(host);
    });
    const ss = host.querySelector ? host.querySelector("#pkSap") : null;
    if (ss) ss.onchange = () => {
      _kho.sap = SAP[ss.value] ? ss.value : "de-xuat"; _kho.trang = 1;
      try { localStorage.setItem("javis.kho.sap", _kho.sap); } catch (e) {}
      lai();
    };
    const sn = host.querySelector ? host.querySelector("#pkNhom") : null;
    if (sn) sn.onchange = () => { _kho.nhom = sn.value; _kho.trang = 1; lai(); };
    const o = document.getElementById("pkQ");
    if (o) {
      const loc = () => { _kho.tim = o.value; _kho.trang = 1; lai(); };
      // Bộ gõ tiếng Việt (Gboard telex, bộ gõ sẵn của macOS/iOS) dựng một chữ qua nhiều nhịp
      // composition. Vẽ lại giữa chừng là ô đang dựng chữ bị vứt đi và dấu thanh mất theo, nên
      // đợi bộ gõ chốt chữ xong (`compositionend`) rồi mới lọc.
      o.oninput = (ev) => { if (!(ev && ev.isComposing)) loc(); };
      o.oncompositionend = loc;
    }
    host.querySelectorAll("[data-kho-lammoi]").forEach(b => b.onclick = () => veKho(el, host, true, _kho.loai));
    host.querySelectorAll("[data-kho-zip]").forEach(b => b.onclick = () => manHinhChon(el, _maxMb));
    // The active tab in view: on a narrow phone the tab strip can scroll sideways.
    // Sets scrollLeft by hand: scrollIntoView would also move the page vertically.
    // One frame later: the page is drawn off screen first and has no width yet.
    const tabOn = host.querySelector ? host.querySelector(".kho-tab.on") : null;
    const dai = tabOn && tabOn.parentElement;
    if (dai && typeof requestAnimationFrame === "function") requestAnimationFrame(() => {
      if (dai.scrollWidth <= dai.clientWidth) return;
      const t = tabOn.offsetLeft, w = tabOn.offsetWidth;
      if (t < dai.scrollLeft) dai.scrollLeft = t;
      else if (t + w > dai.scrollLeft + dai.clientWidth) dai.scrollLeft = t + w - dai.clientWidth;
    });

    const theo = {};
    ds.forEach(g => { theo[g.id] = g; });
    host.querySelectorAll("[data-kho-act]").forEach(b => b.onclick = () => {
      const g = theo[b.dataset.khoId];
      if (!g) return;
      const act = b.dataset.khoAct;
      if (act === "cai") return tuUrl(el, g.download.url, g.download.sha256, g);
      if (act === "go") return hopGo(el, g.id);
      if (act === "tat") {
        return postJson("/packs/toggle", { id: g.id, enabled: g.enabled === false }).then(r => {
          if (r && r.ok) veKho(el, host, false, _kho.loai);
          else alert((r && r.error) || tw("store.toggle_failed"));
        });
      }
      // Connector của app: `core_off` ghi vào sổ, tệp trong system/ không bị đụng.
      if (act === "coreoff") {
        return goApp(nn(g.name, g.id), g.id).then(r => {
          if (r.ok) veKho(el, host, false, _kho.loai);
          else if (!r.huy) alert(r.error);
        });
      }
      postJson("/connect/core-toggle", { id: g.id, off: false, confirm: true }).then(r => {
        if (r && r.ok) veKho(el, host, false, _kho.loai);
        else alert((r && r.error) || tw("store.toggle_failed"));
      });
    });
  }


  // ---- Bước 1 của luồng "cài từ tệp": chọn tệp ----
  //
  // Trước 0.55.36 bước này không tồn tại - nút "Cài từ tệp .zip" bấm thẳng vào một <input>
  // ẩn, nên KHÔNG kéo thả được, mà kéo tệp vừa tải về vào cửa sổ lại đúng là thao tác quen tay
  // nhất. Tệ hơn: thả trượt ra ngoài thì trình duyệt MỞ tệp zip đó thay cho trang, mất sạch
  // trạng thái. Giờ có một vùng thả thật, và cả lớp phủ chặn thả trượt.
  // `tuy` (Plugins page, 2026-10-25): the same drop zone with other words and another handler, so a
  // plugin zip is picked exactly like a pack zip. {tieu, phu, tinHtml (an infoBody block),
  // gioiHan(mb), khiChon(file)}.
  function manHinhChon(el, maxMb, tuy) {
    tuy = tuy || {};
    const m = modal(
      pkmDau(null, (tuy.tieu || tw("store.from_zip")) + infoBtn(), tuy.phu || tw("store.pick.body"))
      // Trust note and what the next step shows: behind the (i) on the title; the next screen shows the real warning.
      + (tuy.tinHtml || infoBody(esc(tw("store.pick.trust"))
          + (_thuMuc ? "<br><br>" + tw("store.dir_note", { duong: "<code>" + esc(_thuMuc) + "</code>" }) : "")))
      + '<div class="pkm-than">'
      + '<label class="pkm-tha" id="pkTha">'
      + '<input type="file" accept=".zip" id="pkTepHop" style="display:none">'
      + '<span class="pkm-tha-ico">' + ic("upload-cloud") + '</span>'
      + '<span class="pkm-tha-t">' + tw("store.pick.drop") + '</span>'
      + '<span class="pkm-tha-s">' + tw("store.pick.or") + ' <u>' + tw("store.pick.browse")
      + '</u></span>'
      + '<span class="pkm-tha-n">' + (tuy.gioiHan ? tuy.gioiHan(maxMb || 25)
          : tw("store.pick.limit", { mb: (maxMb || 25) })) + '</span>'
      + '</label>'
      + '</div>'
      + '<div class="pkm-chan"><button class="mp-btn" data-act="close">'
      + tw("common.cancel") + '</button></div>', true);

    const tha = document.getElementById("pkTha");
    const inp = document.getElementById("pkTepHop");
    const chon = tuy.khiChon || ((f) => chonTep(el, f));
    inp.onchange = () => { if (inp.files && inp.files[0]) chon(inp.files[0]); };
    // Thả TRƯỢT ra ngoài vùng nhận cũng phải bị nuốt: mặc định của trình duyệt là điều hướng
    // sang chính tệp vừa thả, tức là mất trang và mất luôn việc đang làm.
    ["dragenter", "dragover", "drop"].forEach(ev =>
      m.addEventListener(ev, e => e.preventDefault()));
    ["dragenter", "dragover"].forEach(ev =>
      tha.addEventListener(ev, () => tha.classList.add("dang-keo")));
    ["dragleave", "drop"].forEach(ev =>
      tha.addEventListener(ev, () => tha.classList.remove("dang-keo")));
    tha.addEventListener("drop", e => {
      const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) chon(f);
    });
  }

  async function chonTep(el, file) {
    const lai = () => manHinhChon(el, _maxMb);
    // Chặn ngay ở trình duyệt thay vì tải hết vài chục MB lên rồi mới nghe server từ chối.
    if (!/\.zip$/i.test(file.name || "")) {
      manHinhLoi(tw("store.from_zip"), tw("store.not_zip", { ten: (file.name || "?") }), "", lai);
      return;
    }
    dangCho(tw("store.reading.title"), tw("store.reading.body"));
    const fd = new FormData();
    fd.append("file", file);
    let d;
    try { d = await (await fetch("/packs/inspect", { method: "POST", body: fd })).json(); }
    catch (e) { d = { ok: false, error: String(e) }; }
    if (!d || !d.ok) {
      manHinhLoi(tw("store.from_zip"), (d && d.error) || tw("store.bad_zip"), d && d.stage, lai);
      return;
    }
    manHinhDongY(d, el, lai);
  }

  // ---- Plugins page: install ONE plugin from a .zip (owner request 2026-10-25) ----
  //
  // Same machinery as a pack zip: the drop zone above, `/plugins/inspect` (which runs the pack
  // zip rules on the server), a confirmation drawn ONLY from that result, then `/plugins/install`
  // with the inspected sha256. A full store pack zip dropped here gets the PACK confirmation and
  // `/packs/install`, not a second copy of it.
  const MM_KEY = { readonly: "cs.pl_mm_readonly", safe: "cs.pl_mm_safe", full: "cs.pl_mm_full" };
  const PL_FILES_SHOWN = 12;

  // Pure: what the confirmation shows, from the inspect result alone. Exposed for the node test.
  function pluginZipView(d) {
    d = d || {};
    const files = d.files || [];
    const notes = ["off"];
    if (d.existing) notes.push("exists");
    if (d.vault_shadow) notes.push("vault");
    if (d.user_gate === false) notes.push("gate");
    return {
      tools: (d.tools || []).map(x => ({ name: String((x && x.name) || ""),
                                         mm: MM_KEY[x && x.min_mode] ? x.min_mode : "readonly" })),
      hooks: (d.hooks || []).map(String),
      files: files.slice(0, PL_FILES_SHOWN).map(f => String(f.path || "")),
      moreFiles: Math.max(0, (d.file_count || files.length) - PL_FILES_SHOWN),
      needsReplace: !!d.existing,
      zipAskedOn: !!d.enabled_in_zip,
      notes: notes,
    };
  }

  // o = {brain, maxMb, xong(result)}: `xong` redraws the Plugins page after an install.
  function caiPluginZip(o) {
    o = o || {};
    const lai = () => manHinhChon(null, o.maxMb || _maxMb, {
      tieu: tw("plzip.pick_title"), phu: tw("plzip.pick_body"),
      tinHtml: infoBody(esc(tw("plzip.pick_trust"))),
      gioiHan: (mb) => tw("plzip.pick_limit", { mb: mb }),
      khiChon: (f) => chonTepPlugin(f, o, lai),
    });
    lai();
  }

  async function chonTepPlugin(file, o, lai) {
    const tieu = tw("plzip.pick_title");
    if (!/\.zip$/i.test(file.name || "")) {
      manHinhLoi(tieu, tw("store.not_zip", { ten: (file.name || "?") }), "", lai);
      return;
    }
    dangCho(tieu, tw("plzip.reading"));
    const fd = new FormData();
    fd.append("file", file);
    fd.append("brain", o.brain || "brain");
    let d;
    try { d = await (await fetch("/plugins/inspect", { method: "POST", body: fd })).json(); }
    catch (e) { d = { ok: false, error: String(e) }; }
    if (!d || !d.ok) {
      manHinhLoi(tieu, (d && d.error) || tw("store.bad_zip"), d && d.stage, lai);
      return;
    }
    if (d.kind === "pack") {
      manHinhDongY(d, document.createElement("div"), lai, {
        sauKhiCai: (r) => { if (typeof o.xong === "function") o.xong({ kind: "pack", ok: !!(r && r.ok), id: r && r.id }); },
      });
      return;
    }
    manHinhPlugin(d, o, lai);
  }

  function manHinhPlugin(d, o, lai) {
    const v = pluginZipView(d);
    const oBang = (nhan, gt, phu, rong) =>
      '<div class="pkm-o' + (rong ? " rong" : "") + '"><div class="pkm-o-nhan">' + nhan + '</div>'
      + gt + (phu ? '<div class="pkm-o-phu">' + phu + '</div>' : "") + '</div>';
    const canh = (mau, icon, tieu, than) => '<div class="pkm-canh ' + mau + '"><div class="pkm-canh-tieu">'
      + ic(icon) + tieu + '</div><div>' + than + '</div></div>';
    const bang = [
      oBang(tw("store.inspect.file"), '<div class="pkm-o-gt">'
        + esc(d.filename || tw("store.inspect.file_fallback"))
        + ' <span class="nhe">· ' + co(d.size) + '</span></div>'),
      oBang(tw("store.inspect.sha"),
        '<div class="pkm-o-ma">' + esc((d.sha256 || "").slice(0, 20)) + '…</div>',
        tw("store.inspect.sha_note")),
      oBang(tw("plzip.tools"), '<div class="pkm-o-gt">'
        + (v.tools.length
          ? v.tools.map(x => '<div><code>' + esc(x.name) + '</code> <span class="pkm-nhe">· '
              + esc(tw("cs.pl_minmode", { muc: tw(MM_KEY[x.mm]) })) + '</span></div>').join("")
          : esc(tw("plzip.no_tools")))
        + '</div>', v.tools.length ? tw("plzip.tools_note") : "", true),
      v.hooks.length ? oBang(tw("plzip.hooks"), '<div class="pkm-o-gt">'
        + v.hooks.map(h => '<code>' + esc(h) + '</code>').join(", ") + '</div>', "", true) : "",
      oBang(tw("plzip.files"), '<div class="pkm-o-gt">'
        + esc(tw("plzip.files_sum", { count: d.file_count || v.files.length, size: co(d.unpacked) || "0 B" }))
        + '</div>', v.files.map(f => '<code>' + esc(f) + '</code>').join(", ")
        + (v.moreFiles ? " " + esc(tw("plzip.files_more", { count: v.moreFiles })) : ""), true),
      oBang(tw("plzip.target"), '<div class="pkm-o-ma">' + esc(d.target || "") + '</div>',
        tw("plzip.target_note"), true),
    ].filter(Boolean).join("");

    const ghiChu = v.notes.map(k => {
      if (k === "off") return canh("tin", "info", esc(tw("plzip.off_title")),
        esc(tw("plzip.off_body")) + (v.zipAskedOn ? " " + esc(tw("plzip.off_zip")) : ""));
      if (k === "vault") return canh("vang", "info", esc(tw("plzip.vault_title")), esc(tw("plzip.vault_body")));
      if (k === "gate") return canh("vang", "triangle-alert", esc(tw("plzip.gate_title")),
        tw("plzip.gate_body", { bien: "<code>JAVIS_ENABLE_USER_PLUGINS=false</code>" }));
      return "";
    }).join("");

    // The replace question sits right under the description: it is what keeps Install disabled,
    // so it must be seen without scrolling.
    const thayHtml = v.needsReplace
      ? canh("vang", "info", esc(tw("plzip.exists_title")),
          esc(tw("plzip.exists_body", { ver: (d.existing && d.existing.version) || "?" })))
        + '<button class="pkm-gat" id="pzThay" type="button" aria-pressed="false">'
        + '<span><span class="pkm-gat-t">' + esc(tw("plzip.replace")) + '</span>'
        + '<span class="pkm-gat-s">' + esc(tw("plzip.replace_note")) + '</span></span>'
        + '<span class="pkm-cong"><span></span></span></button>'
      : "";

    modal(
      pkmDau({ id: d.slug || "", name: d.name || d.slug || "", icon: "puzzle" }, esc(d.name || d.slug)
          + (d.version ? '<span class="pkm-ver">v' + esc(d.version) + '</span>' : ""),
        '<code>' + esc(d.slug) + '</code>'
          + (d.author ? ' · ' + tw("store.inspect.author", { ten: esc(d.author) }) : ""))
      + '<div class="pkm-than">'
      + (d.description ? '<p class="pkm-mota">' + esc(d.description) + '</p>' : "")
      + thayHtml
      + '<div class="pkm-bang">' + bang + '</div>'
      // Not foldable, not softened: this is the screen where foreign code is let in.
      + canh("do", "triangle-alert", esc(tw("plzip.code_title")), esc(tw("plzip.code_body")))
      + ghiChu
      + '</div>'
      + '<div class="pkm-chan"><span class="mp-note" id="pzNote"></span>'
      + '<button class="mp-btn" id="pzKhac">' + tw("store.pick_other_file") + '</button>'
      + '<button class="mp-btn primary" id="pzCai"' + (v.needsReplace ? " disabled" : "") + '>'
      + esc(tw(v.needsReplace ? "plzip.install_replace" : "plzip.install")) + '</button></div>', true);

    // Focus on the LEFT button: an Enter out of habit must not mean "install foreign code".
    const khac = document.getElementById("pzKhac");
    if (khac) { khac.focus(); khac.onclick = lai; }
    const nut = document.getElementById("pzCai");
    const thay = document.getElementById("pzThay");
    if (thay) thay.onclick = () => {
      const on = thay.getAttribute("aria-pressed") !== "true";
      thay.setAttribute("aria-pressed", on ? "true" : "false");
      nut.disabled = !on;
    };
    const note = document.getElementById("pzNote");
    nut.onclick = async () => {
      const replace = !!(thay && thay.getAttribute("aria-pressed") === "true");
      if (v.needsReplace && !replace) return;
      nut.disabled = true;
      note.textContent = tw("store.installing");
      const r = await postJson("/plugins/install", {
        staging_id: d.staging_id, consent_sha256: d.sha256, replace: replace,
        brain: o.brain || "brain",
      });
      if (!r || !r.ok) {
        note.textContent = (r && r.error) || tw("store.install_failed");
        nut.disabled = false;
        return;
      }
      dong();
      if (typeof o.xong === "function") o.xong(Object.assign({ kind: "plugin" }, r));
    };
  }

  async function hopGo(el, pid) {
    dangCho(tw("store.rm.title"), tw("store.rm.checking"));
    let d;
    try {
      d = await (await fetch("/packs/uninstall-plan?id=" + encodeURIComponent(pid))).json();
    } catch (e) { d = { ok: false, error: String(e) }; }
    if (!d || !d.ok) {
      manHinhLoi(tw("store.rm.title"), (d && d.error) || tw("store.rm.read_failed"), d && d.stage);
      return;
    }
    const kn = d.connections || [];
    const xoa = (d.vault || {}).xoa || [];
    const giu = (d.vault || {}).giu || [];
    modal(pkmDau(d, tw("store.rm.heading", { ten: esc(nn(d.name, d.id)) }),
                 '<code>' + esc(d.id) + '</code>')
      + '<div class="pkm-than">'
      + '<div class="pkm-canh do"><div class="pkm-canh-tieu">' + ic("triangle-alert")
      + tw("store.rm.lose") + '</div>'
      + '<ul class="pkm-mat">'
      + '<li>' + tw("store.rm.files") + ' <span style="opacity:.65">(' + co(d.bytes) + ')</span></li>'
      + ((d.connectors || []).length
          ? '<li>' + tw("store.rm.services", { count: d.connectors.length }) + '</li>' : "")
      // Kết nối theo gói bị xoá THEO, và nói thẳng ra chứ không giấu trong một ô tick: để lại
      // một hàng kết nối chết vẫn là để lại credential của nó trên đĩa.
      + (kn.length
          ? '<li><b>' + tw("store.rm.conns", { count: kn.length }) + '</b>: '
            + kn.map(x => esc(x.label)).join(", ")
            + '<div class="pkm-o-phu">' + tw("store.rm.conns_note") + '</div>'
            + '</li>' : "")
      + (xoa.length
          ? '<li>' + tw("store.rm.vault", { count: xoa.length })
            + ' <span style="opacity:.65">('
            + xoa.map(x => esc(x.slug)).join(", ") + ')</span></li>' : "")
      + '</ul></div>'
      // Thứ người dùng đã sửa thì KHÔNG bị xoá, và phải nói ra - nếu không họ sẽ tưởng mất.
      + (giu.length
          ? '<div class="pkm-canh tin"><div class="pkm-canh-tieu">' + ic("check")
            + tw("store.rm.kept") + '</div><div>' + giu.map(x => esc(x.slug)).join(", ")
            + '</div></div>' : "")
      + ((d.plugin_data || []).length
          ? '<button class="pkm-gat" id="pkData" type="button" aria-pressed="false">'
            + '<span><span class="pkm-gat-t">' + tw("store.rm.purge") + '</span>'
            + '<span class="pkm-gat-s">' + tw("store.rm.purge_note") + '</span></span>'
            + '<span class="pkm-cong"><span></span></span></button>' : "")
      + '</div>'
      + '<div class="pkm-chan"><span class="mp-note" id="pkNote2"></span>'
      + '<button class="mp-btn" data-act="close">' + tw("common.cancel") + '</button>'
      + '<button class="mp-btn danger" id="pkGoOk">' + tw("proj.remove_short")
      + '</button></div>', true);
    const huy = document.querySelector("#packModal .pkm-chan .mp-btn");
    if (huy) huy.focus();
    const dl = document.getElementById("pkData");
    if (dl) dl.onclick = () => dl.setAttribute("aria-pressed",
      dl.getAttribute("aria-pressed") === "true" ? "false" : "true");
    const note = document.getElementById("pkNote2");
    document.getElementById("pkGoOk").onclick = async () => {
      note.textContent = tw("store.rm.working");
      const r = await postJson("/packs/uninstall", {
        id: pid, purge_data: !!(dl && dl.getAttribute("aria-pressed") === "true"),
      });
      if (!r || !r.ok) { note.textContent = (r && r.error) || tw("store.rm.failed"); return; }
      dong();
      veLai(el);
    };
  }

  // console.js gọi hàm này MỖI LẦN điều hướng vào trang kho, và chỉ lúc đó. Nên đây là chỗ
  // đúng để chốt đường về của lượt mới: lấy thứ `moKho` vừa đặt (nếu vào bằng tab), hoặc
  // không có gì (nếu vào từ thanh bên).
  async function render(el) {
    _veLuot = _veTrang;
    _veTrang = null;
    return veLai(el);
  }

  async function veLai(el) {
    el.innerHTML = '<div class="cview-placeholder">' + tw("sess.loading") + '</div>';
    let d;
    try { d = await (await fetch("/packs")).json(); }
    catch (e) {
      el.innerHTML = '<div class="cview-placeholder">' + tw("cs.cn_load_err") + '</div>';
      return;
    }
    if (d && d.error) {
      el.innerHTML = '<div class="cview-placeholder">' + esc(d.error) + '</div>';
      return;
    }
    // Bộ lọc loại thì lấy rồi XOÁ NGAY: nó là ý định của MỘT lần bấm tab. Giữ lại thì lần sau
    // vào kho vẫn thấy lưới bị cắt còn một loại mà không có gì giải thích.
    //
    // Nút quay lại thì đọc `_veLuot` - đã chốt ở `render()` cho cả lượt - nên nó sống qua mọi
    // lần vẽ lại mà không dính sang lượt sau.
    const loaiDau = _loaiCho;
    const timDau = _timCho;
    const veTrang = _veLuot;
    _loaiCho = "";
    _timCho = "";

    el.innerHTML =
      // Nút quay lại: chỉ hiện khi VÀO TỪ một trang năng lực. Vào thẳng từ thanh bên thì không
      // có chỗ nào để quay về, và một cái nút dẫn đi đâu đó ngẫu nhiên còn tệ hơn không có.
      (veTrang
        ? '<button class="kho-quaylai" id="pkQuayLai">← '
          + tw("store.back_to", { trang: esc(veTrang.nhan) }) + '</button>'
        : "")
      // No heading and no intro here (owner, 2026-10-28): the page header right above already says
      // "Javis Store" and what it holds, and the cards explain themselves. Where installs land on
      // disk moved into the (i) of the Install from .zip dialog, the one place it matters.
      + '<div class="kho-khoi">'
      + (d.disabled
        ? '<div class="conn-guide" style="border-left:3px solid var(--warn,#e0a33e);padding-left:10px;margin-bottom:12px">'
          + tw("store.disabled_env", { bien: '<code>JAVIS_DISABLE_PACKS</code>' }) + '</div>'
        : "")
      + '<div id="pkKho"></div>'
      + '</div>';

    _maxMb = d.max_mb || 25;
    _thuMuc = d.dir || "";
    const nutVe = document.getElementById("pkQuayLai");
    if (nutVe) nutVe.onclick = () => {
      const s = window.Alpine && Alpine.store("nav");
      if (s && s.go) s.go(veTrang.id);
    };
    const hostKho = document.getElementById("pkKho");
    if (hostKho) veKho(el, hostKho, false, loaiDau, timDau);
  }

  // Mở kho với một loại đã lọc sẵn. Tab "Kho cài đặt" trên trang Trợ lý / Kỹ năng / Quy
  // trình / Plugin gọi hàm này, nên bốn trang KHÔNG ai nhúng một bản sao của lưới kho: chỉ có
  // một kho, một chỗ sửa, và người dùng học một lần là xong.
  //
  // `tim` là từ khoá điền sẵn vào ô tìm. Dùng cho đường "kết nối này đang dừng vì dịch vụ của
  // nó đã ra kho" trên trang Kết nối: bấm một nút là tới thẳng đúng gói cần cài, thay vì thả
  // người dùng vào một kho vài chục mục rồi bảo họ tự tìm cái vừa biến mất.
  function moKho(loai, tuTrang, nhanTrang, tim) {
    _loaiCho = LOAI[loai] ? loai : "";
    _veTrang = tuTrang ? { id: tuTrang, nhan: nhanTrang || tuTrang } : null;
    _timCho = tim || "";
    if (window.Alpine && Alpine.store("nav")) Alpine.store("nav").go("packs");
  }

  // `coBanMoi` và `nutThe` phơi ra để test GỌI THẬT chứ không quét chuỗi: phép so phiên bản là
  // thứ quyết định người dùng có thấy nút cập nhật hay không, và một canary đọc chữ thì vẫn
  // xanh y nguyên khi phép so bị đảo ngược. `veKho` phơi ra cùng lý do: ô tìm trong kho
  // chỉ gõ được đúng một chữ rồi văng con trỏ, và chỉ có gõ THẬT qua đường vẽ lại mới bắt
  // được lỗi đó.
  window.JavisPacks = { render: render, moKho: moKho, LOAI: LOAI, goApp: goApp, hoi: hoi,
                        coBanMoi: coBanMoi, nutThe: nutThe, theKho: theKho,
                        ghiConTro: ghiConTro, traConTro: traConTro, veKho: veKho,
                        caiGoiKho: caiGoiKho, caiPluginZip: caiPluginZip,
                        pluginZipView: pluginZipView };
})();
