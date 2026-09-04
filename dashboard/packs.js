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
      + '<button class="mp-x" data-act="close" title="Đóng">' + ic("x") + '</button></div>';
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
      + '<div class="pkm-canh-tieu">' + ic("triangle-alert") + 'Không cài được</div>'
      + '<div>' + esc(loi) + '</div>'
      + (buoc ? '<div class="pkm-o-phu">Dừng ở bước: ' + esc(buoc) + '</div>' : "")
      + '</div></div>'
      + '<div class="pkm-chan">'
      + (lamLai ? '<button class="mp-btn" id="pkLai">Chọn tệp khác</button>' : "")
      + '<button class="mp-btn primary" data-act="close">Đóng</button></div>', true);
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
        + esc(o.canhTieu || "Bạn có chắc không?") + '</div>'
        + '<div>' + (o.than || "") + '</div></div>'
        + (o.themHtml || "") + '</div>'
        + '<div class="pkm-chan">'
        + '<button class="mp-btn" id="pkHoiKhong">' + esc(o.khong || "Huỷ") + '</button>'
        + '<button class="mp-btn ' + (o.mau === "do" ? "danger" : "primary") + '" id="pkHoiCo">'
        + esc(o.co || "Đồng ý") + '</button></div>', true);
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
  const LOAI = {
    agent:     { nhan: "Trợ lý",    icon: "bot",      trang: "agents" },
    skill:     { nhan: "Kỹ năng",   icon: "puzzle",   trang: "skills" },
    workflow:  { nhan: "Quy trình", icon: "workflow", trang: "workflows" },
    tool:      { nhan: "Công cụ",   icon: "toolbox",  trang: "plugins" },
    connector: { nhan: "Kết nối",   icon: "plug",     trang: "mcp" },
    bundle:    { nhan: "Trọn bộ",   icon: "package",  trang: "" },
  };
  const THU_TU_LOAI = ["agent", "skill", "workflow", "tool", "connector"];

  // Trần dung lượng tệp .zip, do server nói (`/packs` trả `max_mb`). Giữ ở module để hộp thoại
  // chọn tệp nói đúng con số ngay cả khi nó mở lại sau một lần lỗi, lúc không còn `d` trong tay.
  let _maxMb = 25;

  // Loại được chọn sẵn khi mở kho. `moKho()` đặt, `render()` lấy rồi XOÁ ngay - nó là ý định
  // của MỘT lần bấm tab, không phải trạng thái của trang.
  let _loaiCho = "";
  // Từ khoá điền sẵn vào ô tìm, cùng vòng đời với `_loaiCho`: đặt một lần rồi xoá ngay.
  let _timCho = "";
  // Trang đã dẫn người dùng sang kho, để vẽ nút quay lại. `null` = vào thẳng từ thanh bên.
  let _veTrang = null;

  const BAC = {
    data: { nhan: "Chỉ dữ liệu", mau: "var(--ok-ink,#2f855a)" },
    code: { nhan: "Có chạy mã", mau: "var(--warn-ink,#b7791f)" },
  };

  function vaultTom(v) {
    // Tóm tắt "gói này thêm gì vào bộ não", dạng "2 trợ lý, 1 kỹ năng".
    const TEN = { agents: "trợ lý", workflows: "quy trình", skills: "kỹ năng" };
    return Object.keys(TEN)
      .filter(k => ((v || {})[k] || []).length)
      .map(k => (v[k].length + " " + TEN[k]));
  }

  // ---- Màn hình xác nhận trước khi cài, vẽ hoàn toàn từ kết quả /packs/inspect ----
  //
  // Trật tự đọc được đặt cứng, vì đây là màn hình duy nhất trong app nơi người dùng đồng ý cho
  // mã lạ chạy trong máy chủ của họ: đây là gói gì → nó đến từ tệp nào và vân tay ra sao → nó
  // chạm vào đâu trong máy → cảnh báo → rồi mới tới hai cái nút.
  //
  // `tuTep` là hàm quay về bước chọn tệp. Có khi cài từ kho thì không có nó, và chân hộp hiện
  // "Huỷ" thay cho "Chọn tệp khác".
  function manHinhDongY(d, el, tuTep) {
    const coMa = d.tier === "code";
    const py = (d.py_files || []);
    const kn = (d.connectors || []);
    const vt = vaultTom(d.vault);
    // Mỗi ô trong bảng là MỘT câu hỏi người cài thật sự hỏi, nên ô nào không có câu trả lời
    // thì biến mất chứ không hiện một dòng trống.
    const o = (nhan, gt, phu, rong) =>
      '<div class="pkm-o' + (rong ? " rong" : "") + '"><div class="pkm-o-nhan">' + nhan + '</div>'
      + gt + (phu ? '<div class="pkm-o-phu">' + phu + '</div>' : "") + '</div>';
    const bang = [
      o("Tệp", '<div class="pkm-o-gt">' + esc(d.filename || "tệp bạn vừa chọn")
        + ' <span class="nhe">· ' + co(d.size) + '</span></div>'),
      o("Mã kiểm tra tệp", '<div class="pkm-o-ma">' + esc((d.sha256 || "").slice(0, 20)) + '…</div>',
        "Khớp với mã nhà phát hành công bố thì tệp là bản nguyên, chưa ai sửa dọc đường."),
      kn.length ? o("Thêm vào kho Kết nối",
        '<div class="pkm-o-gt">' + kn.length + ' dịch vụ: '
        + kn.map(x => '<code>' + esc(x) + '</code>').join(", ") + '</div>',
        "Mọi dịch vụ từ gói đều bắt đầu ở mức Chỉ đọc. Muốn cho ghi thì bạn tự nâng quyền từng "
        + "tài khoản.", true) : "",
      vt.length ? o("Thêm vào bộ não đang mở", '<div class="pkm-o-gt">' + vt.join(", ") + '</div>',
        "Bộ não đã có mục trùng tên thì Javis giữ bản của bạn và bỏ qua bản trong gói. Gỡ gói "
        + "cũng chỉ xoá thứ bạn chưa sửa.", true) : "",
    ].filter(Boolean).join("");

    modal(
      pkmDau(d, esc(nn(d.name, d.id))
          + (d.version ? '<span class="pkm-ver">v' + esc(d.version) + '</span>' : ""),
        '<code>' + esc(d.id) + '</code>'
          + (d.author && d.author.name ? ' · tác giả ' + esc(d.author.name) : ""))
      + '<div class="pkm-than">'
      + (nn(d.description) ? '<p class="pkm-mota">' + esc(nn(d.description)) + '</p>' : "")
      + '<div class="pkm-bang">' + bang + '</div>'
      + (d.da_cai
          ? '<div class="pkm-canh vang"><div class="pkm-canh-tieu">' + ic("info")
            + 'Máy đã có gói này</div><div>Đang chạy bản <b>' + esc(d.da_cai.version || "?")
            + '</b>. Cài tiếp là THAY bản cũ.</div></div>' : "")
      + (d.warning
          ? '<div class="pkm-canh vang"><div class="pkm-canh-tieu">' + ic("info")
            + 'Một phần của gói bị bỏ qua</div><div>' + esc(d.warning) + '</div></div>' : "")
      // Gói chưa qua review của người phát hành kho: nói dài hơn một dòng. Không chặn - ai tin
      // nguồn nào là lựa chọn của người cài - nhưng họ phải biết mình đang chọn gì.
      + ((d._tin && d._tin.verified === false)
          ? '<div class="pkm-canh vang"><div class="pkm-canh-tieu">' + ic("info")
            + 'Gói của cộng đồng</div><div>Gói này do người ngoài gửi vào kho, '
            + 'chưa qua kiểm duyệt của người phát hành. Đọc kỹ phần bên dưới trước khi '
            + 'cài.</div></div>' : "")
      // Khối cảnh báo cho gói có mã: KHÔNG gập được, không icon ổ khoá, không làm mềm chữ.
      // `permissions` trong manifest là lời khai của tác giả, không có tầng nào chặn, và
      // `min_mode` chỉ giới hạn cái MODEL được gọi chứ không giới hạn cái mã làm được.
      + (coMa
        ? '<div class="pkm-canh do"><div class="pkm-canh-tieu">' + ic("triangle-alert")
          + 'Gói này chạy Python thật trong máy chủ Javis</div>'
          + '<div>Nó đọc được mọi khoá API, token và tệp mà Javis đọc được. Không có lớp ngăn '
          + 'nào cả. Chỉ cài gói từ nguồn bạn tin.</div>'
          + (py.length
              ? '<div class="pkm-o-phu">Tệp mã trong gói: '
                + py.slice(0, 12).map(x => '<code>' + esc(x) + '</code>').join(", ")
                + (py.length > 12 ? " và " + (py.length - 12) + " tệp nữa" : "") + '</div>' : "")
          + '<label>Gõ đúng <b>' + esc(d.id) + '</b> để xác nhận:'
          + '<input class="mp-input" id="pkGo" placeholder="Gõ lại mã gói" autocomplete="off">'
          + '</label></div>' : "")
      // Mặc định của công tắc đi theo BẬC của gói, không phải một hằng số:
      //
      //   có mã   tắt. Người dùng nên mở tệp ra xem trước khi cho nó chạy trong máy chủ mình.
      //   dữ liệu bật. Gói chỉ-dữ-liệu không chạy gì cả - nó chỉ thêm một khuôn connector hay
      //           vài tệp vào bộ não - nên cài xong mà nó nằm im là một cái bẫy chứ không phải
      //           một lớp an toàn. Vấp thật khi thử đường di trú: kết nối đang chết, người dùng
      //           bấm cài đúng gói cần, và KHÔNG có gì xảy ra vì gói vào máy ở trạng thái tắt.
      + '<button class="pkm-gat" id="pkBat" type="button" aria-pressed="' + (coMa ? "false" : "true") + '">'
      + '<span><span class="pkm-gat-t">Bật ngay sau khi cài</span>'
      + '<span class="pkm-gat-s">'
      + (coMa ? "Mặc định tắt vì gói có chạy mã, để bạn xem lại trước."
              : "Gói chỉ có dữ liệu, bật là dùng được ngay.")
      + '</span></span>'
      + '<span class="pkm-cong"><span></span></span></button>'
      + '</div>'
      + '<div class="pkm-chan"><span class="mp-note" id="pkNote"></span>'
      + '<button class="mp-btn" ' + (tuTep ? 'id="pkKhac"' : 'data-act="close"') + '>'
      + (tuTep ? "Chọn tệp khác" : "Huỷ") + '</button>'
      + '<button class="mp-btn primary" id="pkCai">Cài</button></div>', true);

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
        enable: gat.getAttribute("aria-pressed") === "true",
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
    dangCho("Đang tải gói", "Tải về và kiểm tra tệp…");
    const d = await postJson("/packs/install-url", { url: url, expect_sha256: expect || "" });
    if (!d || !d.ok) {
      manHinhLoi("Cài từ kho", (d && d.error) || "Tải không được.", d && d.stage);
      return;
    }
    d._tin = tin || null;
    manHinhDongY(d, el);
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
    if (!p || !p.ok) return { ok: false, error: (p && p.error) || "Không đọc được dịch vụ này." };
    const kn = p.connections || [];
    const dongY = await hoi({
      tieu: "Gỡ " + ten + " khỏi kho Kết nối?",
      mau: "do", co: "Gỡ", khong: "Giữ lại",
      canhTieu: kn.length
        ? kn.length + " kết nối đang chạy sẽ DỪNG"
        : "Bạn chắc chắn muốn gỡ chứ?",
      than: (kn.length
        ? "<b>" + kn.map(x => esc(x.label)).join(", ") + "</b> ngừng hoạt động ngay khi gỡ. "
          + "Kết nối KHÔNG bị xoá: cài lại dịch vụ là chúng chạy tiếp như cũ."
        : "Dịch vụ này biến khỏi kho Kết nối và khỏi mọi engine. Tệp của nó vẫn nằm trong bản "
          + "cài - Javis không sửa mã nguồn của chính nó - nên cài lại lúc nào cũng được."),
    });
    if (!dongY) return { ok: false, huy: true };
    const r = await postJson("/connect/core-toggle", { id: id, off: true, confirm: true });
    return { ok: !!(r && r.ok), error: (r && r.error) || "Không gỡ được." };
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
    if (g.installed) return { nhan: "Gỡ cài đặt", lop: "kho-btn kho-btn-go", act: "go", tat: true };
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
      + '<div class="kho-nut">'
      // Bật/tắt tạm một gói đã cài. Trước 0.55.34 nút này chỉ có ở khối "Đã cài" dưới trang;
      // khối đó bỏ đi rồi nên nó về đây, chứ không được biến mất - tắt tạm KHÁC gỡ hẳn, và
      // người ta cần nó khi một gói đang gây phiền mà chưa muốn mất cấu hình.
      + (n.tat
          ? '<button class="kho-btn kho-btn-phu" data-kho-act="tat" data-kho-id="' + esc(g.id)
            + '">' + (g.enabled === false ? "Bật" : "Tắt") + '</button>'
          : "")
      + '<button class="' + n.lop + '" data-kho-act="' + n.act + '" data-kho-id="' + esc(g.id) + '">'
      + n.nhan + '</button></div>'
      + '</div>';
  }

  // Trạng thái lưới kho. Để ở module vì mọi lần bấm tab, bấm nhóm hay đổi trang đều chỉ VẼ LẠI
  // từ dữ liệu đã tải, không gọi lại mạng.
  let _kho = { dl: null, loai: "connector", nhom: "Tất cả", trang: 1, tim: "" };
  const MOI_TRANG = 20;

  async function veKho(el, host, lamMoi, loaiDau, timDau) {
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
    _kho.tim = timDau || "";
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
      // Bề rộng do CSS lo, không viết cứng ở đây: trên điện thoại ô này phải chiếm trọn hàng,
      // mà style nội tuyến thì media query không đè được nếu không kèm !important.
      + '<input class="js-input kho-tim" id="pkQ" placeholder="Tìm trong '
      + esc(LOAI[_kho.loai].nhan) + '…" value="' + esc(_kho.tim) + '">'
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
    if (ct) ct.onclick = () => manHinhChon(el, _maxMb);

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
          else alert((r && r.error) || "Không đổi được.");
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
        else alert((r && r.error) || "Không đổi được.");
      });
    });
  }


  // ---- Bước 1 của luồng "cài từ tệp": chọn tệp ----
  //
  // Trước 0.55.36 bước này không tồn tại - nút "Cài từ tệp .zip" bấm thẳng vào một <input>
  // ẩn, nên KHÔNG kéo thả được, mà kéo tệp vừa tải về vào cửa sổ lại đúng là thao tác quen tay
  // nhất. Tệ hơn: thả trượt ra ngoài thì trình duyệt MỞ tệp zip đó thay cho trang, mất sạch
  // trạng thái. Giờ có một vùng thả thật, và cả lớp phủ chặn thả trượt.
  function manHinhChon(el, maxMb) {
    const m = modal(
      pkmDau(null, "Cài từ tệp .zip",
        "Chọn gói đã tải về máy. Javis mở ra kiểm rồi cho bạn xem có gì trước khi cài.")
      + '<div class="pkm-than">'
      + '<label class="pkm-tha" id="pkTha">'
      + '<input type="file" accept=".zip" id="pkTepHop" style="display:none">'
      + '<span class="pkm-tha-ico">' + ic("upload-cloud") + '</span>'
      + '<span class="pkm-tha-t">Kéo tệp .zip vào đây</span>'
      + '<span class="pkm-tha-s">hoặc <u>chọn tệp trên máy</u></span>'
      + '<span class="pkm-tha-n">Tối đa ' + (maxMb || 25) + ' MB, chỉ nhận gói .zip của Javis</span>'
      + '</label>'
      + '<div class="pkm-luuy">' + ic("info")
      + '<span>Chỉ cài gói từ nguồn bạn tin. Bước sau Javis mở gói ra, liệt kê đúng những thứ '
      + 'nó thêm vào máy, rồi mới hỏi bạn có cài không.</span></div>'
      + '</div>'
      + '<div class="pkm-chan"><button class="mp-btn" data-act="close">Huỷ</button></div>', true);

    const tha = document.getElementById("pkTha");
    const inp = document.getElementById("pkTepHop");
    inp.onchange = () => { if (inp.files && inp.files[0]) chonTep(el, inp.files[0]); };
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
      if (f) chonTep(el, f);
    });
  }

  async function chonTep(el, file) {
    const lai = () => manHinhChon(el, _maxMb);
    // Chặn ngay ở trình duyệt thay vì tải hết vài chục MB lên rồi mới nghe server từ chối.
    if (!/\.zip$/i.test(file.name || "")) {
      manHinhLoi("Cài từ tệp .zip", "Chỉ nhận tệp .zip. Tệp bạn chọn là “" + (file.name || "?")
        + "”.", "", lai);
      return;
    }
    dangCho("Đang đọc gói", "Mở tệp ra và kiểm tra…");
    const fd = new FormData();
    fd.append("file", file);
    let d;
    try { d = await (await fetch("/packs/inspect", { method: "POST", body: fd })).json(); }
    catch (e) { d = { ok: false, error: String(e) }; }
    if (!d || !d.ok) {
      manHinhLoi("Cài từ tệp .zip", (d && d.error) || "Tệp không hợp lệ.", d && d.stage, lai);
      return;
    }
    manHinhDongY(d, el, lai);
  }

  async function hopGo(el, pid) {
    dangCho("Gỡ gói", "Xem gói này đang giữ những gì…");
    let d;
    try {
      d = await (await fetch("/packs/uninstall-plan?id=" + encodeURIComponent(pid))).json();
    } catch (e) { d = { ok: false, error: String(e) }; }
    if (!d || !d.ok) {
      manHinhLoi("Gỡ gói", (d && d.error) || "Không đọc được gói này.", d && d.stage);
      return;
    }
    const kn = d.connections || [];
    const xoa = (d.vault || {}).xoa || [];
    const giu = (d.vault || {}).giu || [];
    modal(pkmDau(d, "Gỡ " + esc(nn(d.name, d.id)), '<code>' + esc(d.id) + '</code>')
      + '<div class="pkm-than">'
      + '<div class="pkm-canh do"><div class="pkm-canh-tieu">' + ic("triangle-alert")
      + 'Những thứ sẽ mất</div>'
      + '<ul class="pkm-mat">'
      + '<li>Tệp của gói <span style="opacity:.65">(' + co(d.bytes) + ')</span></li>'
      + ((d.connectors || []).length
          ? '<li>' + d.connectors.length + ' dịch vụ khỏi kho Kết nối</li>' : "")
      // Kết nối theo gói bị xoá THEO, và nói thẳng ra chứ không giấu trong một ô tick: để lại
      // một hàng kết nối chết vẫn là để lại credential của nó trên đĩa.
      + (kn.length
          ? '<li><b>' + kn.length + ' kết nối bạn đã đấu</b>: '
            + kn.map(x => esc(x.label)).join(", ")
            + '<div class="pkm-o-phu">Chúng bị xoá theo, và nằm trong thùng rác 30 ngày.</div>'
            + '</li>' : "")
      + (xoa.length
          ? '<li>' + xoa.length + ' mục trong bộ não <span style="opacity:.65">('
            + xoa.map(x => esc(x.slug)).join(", ") + ')</span></li>' : "")
      + '</ul></div>'
      // Thứ người dùng đã sửa thì KHÔNG bị xoá, và phải nói ra - nếu không họ sẽ tưởng mất.
      + (giu.length
          ? '<div class="pkm-canh tin"><div class="pkm-canh-tieu">' + ic("check")
            + 'Giữ lại vì bạn đã sửa</div><div>' + giu.map(x => esc(x.slug)).join(", ")
            + '</div></div>' : "")
      + ((d.plugin_data || []).length
          ? '<button class="pkm-gat" id="pkData" type="button" aria-pressed="false">'
            + '<span><span class="pkm-gat-t">Xoá luôn dữ liệu plugin của gói này</span>'
            + '<span class="pkm-gat-s">Mặc định giữ lại, cài lại là có ngay.</span></span>'
            + '<span class="pkm-cong"><span></span></span></button>' : "")
      + '</div>'
      + '<div class="pkm-chan"><span class="mp-note" id="pkNote2"></span>'
      + '<button class="mp-btn" data-act="close">Huỷ</button>'
      + '<button class="mp-btn danger" id="pkGoOk">Gỡ</button></div>', true);
    const huy = document.querySelector("#packModal .pkm-chan .mp-btn");
    if (huy) huy.focus();
    const dl = document.getElementById("pkData");
    if (dl) dl.onclick = () => dl.setAttribute("aria-pressed",
      dl.getAttribute("aria-pressed") === "true" ? "false" : "true");
    const note = document.getElementById("pkNote2");
    document.getElementById("pkGoOk").onclick = async () => {
      note.textContent = "Đang gỡ…";
      const r = await postJson("/packs/uninstall", {
        id: pid, purge_data: !!(dl && dl.getAttribute("aria-pressed") === "true"),
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
    // Bộ lọc loại thì lấy rồi XOÁ NGAY: nó là ý định của MỘT lần bấm tab. Giữ lại thì lần sau
    // vào kho vẫn thấy lưới bị cắt còn một loại mà không có gì giải thích.
    //
    // Nút quay lại thì NGƯỢC LẠI, phải sống suốt lượt ở trong kho. Trang này tự vẽ lại sau mỗi
    // lần cài, gỡ hay bật tắt; xoá theo kiểu kia thì cài xong một món là nút biến mất - đúng
    // lúc người dùng cần nó nhất, và kho không nằm trên thanh bên nên họ thật sự bị lạc.
    // Rời kho rồi quay lại bằng tab khác thì `moKho` ghi đè, còn tải lại trang thì mọi biến
    // JS về rỗng - hai đường đó tự sạch, không cần xoá tay.
    const loaiDau = _loaiCho;
    const timDau = _timCho;
    const veTrang = _veTrang;
    _loaiCho = "";
    _timCho = "";

    el.innerHTML =
      // Nút quay lại: chỉ hiện khi VÀO TỪ một trang năng lực. Vào thẳng từ thanh bên thì không
      // có chỗ nào để quay về, và một cái nút dẫn đi đâu đó ngẫu nhiên còn tệ hơn không có.
      (veTrang
        ? '<button class="kho-quaylai" id="pkQuayLai">← Quay lại ' + esc(veTrang.nhan) + '</button>'
        : "")
      + '<div class="cview-section kho-khoi"><h3>◆ Javis Store</h3>'
      + '<div class="gcard-meta" style="max-width:740px">Trợ lý, kỹ năng, quy trình và công cụ '
      + 'làm sẵn theo từng lĩnh vực. Bấm <b>Cài</b> là Javis tải về, mở ra cho bạn xem có gì '
      + 'rồi mới hỏi.</div>'
      + (d.disabled
        ? '<div class="conn-guide" style="border-left:3px solid var(--warn,#e0a33e);padding-left:10px;margin-top:12px">'
          + 'Biến môi trường <code>JAVIS_DISABLE_PACKS</code> đang bật, nên mọi thứ cài thêm bị tắt hết.</div>'
        : "")
      + '<div id="pkKho" style="margin-top:12px"></div>'
      + '<div class="gcard-meta" style="margin-top:16px;opacity:.7">Thứ cài thêm nằm ở <code>'
      + esc(d.dir || "") + '</code>. Thả thẳng một thư mục vào đó cũng được, không bắt buộc '
      + 'phải qua tệp nén. Tệp .zip tối đa ' + (d.max_mb || 25) + 'MB.</div>'
      + '</div>';

    _maxMb = d.max_mb || 25;
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

  window.JavisPacks = { render: render, moKho: moKho, LOAI: LOAI, goApp: goApp, hoi: hoi };
})();
