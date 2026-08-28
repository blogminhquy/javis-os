/* usage.js - Trang "Mức dùng".
 *
 * Bố cục đọc từ trên xuống như một câu trả lời, không phải như một bảng số liệu:
 *   1. Dải chế độ tiết kiệm, thu gọn một dòng (bấm mới bung ba nút ra).
 *   2. Bộ lọc kỳ.
 *   3. MỘT CÂU tiếng người: ai trả gì cho cái gì.
 *   4. Ba ô HÀNH ĐỘNG ĐƯỢC: tiền mặt so ngân sách, trần gói còn bao nhiêu, tiết kiệm.
 *   5. Các số phụ, biểu đồ có mốc sự kiện, thứ ngốn nhất kèm nút xử lý.
 *
 * Vì sao đảo lại so với bản trước: bản trước mở ra là ba thẻ chọn chế độ chiếm trọn màn hình
 * đầu, rồi tới sáu ô KPI ngang hàng nhau, trong đó ô số to nhất ("chi phí quy đổi $1.700")
 * lại KHÔNG phải tiền thật và đứng ngay cạnh số dư OpenRouter là tiền thật. Đọc lướt thì
 * thành một hoá đơn doạ người. Còn "cache hit 80%" thì là ngôn ngữ của người viết code.
 *
 * Nguồn: /usage/tong-quan (khối tiền + trần + tiết kiệm), /usage/summary (số liệu theo
 * chiều), /usage/insights, /usage (số dư OpenRouter), /runtime/muc (ba mức tiết kiệm).
 * Vẽ SVG/div thuần, không thêm thư viện. window.JavisUsage.render(el).
 */
(function () {
  "use strict";

  // Locale để định dạng số/ngày. Lấy từ i18n chứ KHÔNG khoá "vi-VN": người dùng đổi
  // ngôn ngữ giao diện thì ngày giờ phải đổi theo, nếu không thì nửa màn hình tiếng Anh
  // mà ngày vẫn dd/mm/yyyy kiểu Việt.
  const LOC = () => (window.JavisI18n && JavisI18n.locale()) || "vi-VN";
  var PERIODS = [
    ["today", "Hôm nay"], ["yesterday", "Hôm qua"],
    ["this_week", "Tuần này"], ["last_week", "Tuần trước"],
    ["this_month", "Tháng này"], ["last_month", "Tháng trước"],
    ["last_3_months", "3 tháng"], ["this_year", "Năm nay"],
  ];
  var PROVS = [["", "Tất cả"], ["claude", "Claude Code"], ["codex", "ChatGPT"], ["api", "API"]];
  var PROV_LABEL = { claude: "Claude Code", codex: "ChatGPT/Codex", api: "API (OpenRouter...)", "gemini-cli": "Gemini CLI", "grok-cli": "Grok Build" };
  var SRC_LABEL = { manual: "Bạn gõ tay", javis: "Javis (tự chạy)" };
  var ACT_LABEL = { chat: "Chat", background: "Nền (loop/lịch)", subagent: "Subagent", manual: "Thủ công" };
  var PROV_COLOR = { claude: "var(--accent)", codex: "var(--green)", api: "var(--link-ink)" };
  var MOC_ICO = { muc: "zap", model: "brain", ngan_sach: "shield" };

  var state = {
    period: "this_month", provider: "", el: null, busy: false,
    muc: null, tq: null, viec: null, toast: "", nsToast: "", nsForm: null,
    moMuc: false, moNganSach: false,
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function fTok(n) {
    n = +n || 0;
    if (n >= 1e9) return (n / 1e9).toFixed(n >= 1e10 ? 0 : 1) + "B";
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "k";
    return "" + n;
  }
  // Mọi con số tiền trên trang này đều là USD. Giá của các nhà cung cấp đều niêm yết bằng
  // USD, nên quy đổi thêm một lần nữa bằng tỉ giá gõ cứng chỉ tạo ra một chỗ để sai.
  function fCost(c) {
    c = +c || 0;
    if (c > 0 && c < 0.01) return "<$0.01";     // làm tròn thành $0.00 thì đọc như bằng không
    return "$" + (c >= 1000 ? Math.round(c).toLocaleString("en-US") : c.toFixed(2));
  }
  function model(m) { return String(m || "").split("/").pop().replace(/^(claude-|gpt-)/, "").slice(0, 26); }
  function pct(x) { return Math.round((+x || 0) * 100) + "%"; }

  var _css = false;
  function injectCss() {
    if (_css) return; _css = true;
    var css = ""
      + ".tk-wrap{max-width:1000px}"
      + ".tk-bar1{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:18px}"
      + ".tk-chips{display:flex;gap:6px;flex-wrap:wrap}"
      + ".tk-chip{padding:6px 12px;border-radius:20px;border:1px solid var(--glass-brd);background:var(--glass);color:var(--text2);font-size:13px;cursor:pointer;transition:.12s;white-space:nowrap}"
      + ".tk-chip:hover{color:var(--text)}"
      + ".tk-chip.on{background:var(--accent-solid);border-color:var(--accent-solid);color:var(--on-accent);font-weight:600}"
      + ".tk-seg{display:flex;border:1px solid var(--glass-brd);border-radius:9px;overflow:hidden}"
      + ".tk-seg button{padding:6px 12px;background:transparent;border:0;color:var(--text2);font-size:12.5px;cursor:pointer}"
      + ".tk-seg button.on{background:var(--glass);color:var(--text);font-weight:600}"
      + ".tk-refresh{margin-left:auto;padding:6px 13px;border-radius:9px;border:1px solid var(--glass-brd);background:var(--glass);color:var(--text2);font-size:13px;cursor:pointer}"
      + ".tk-refresh:hover{color:var(--text)}"
      // --- Câu mở đầu: to hơn chữ thường, nhẹ hơn tiêu đề. Nó là phần TÓM TẮT, phải đọc
      // được mà không cần nhìn số nào bên dưới.
      + ".tk-hero{border:1px solid var(--glass-brd);background:var(--glass);border-radius:14px;padding:16px 18px;margin-bottom:14px}"
      + ".tk-hero p{margin:0;font-size:15px;line-height:1.65;color:var(--text)}"
      + ".tk-hero b{color:var(--accent)}"
      + ".tk-hero .sub{margin-top:8px;font-size:12.5px;color:var(--text3);line-height:1.55}"
      // --- Ba ô hành động: to hơn ô KPI thường, mỗi ô có một thanh tiến độ hoặc một nút.
      + ".tk-act{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-bottom:18px}"
      + ".tk-a{border:1px solid var(--glass-brd);background:var(--glass);border-radius:14px;padding:15px 17px;display:flex;flex-direction:column;gap:7px}"
      + ".tk-a .h{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--text3);text-transform:uppercase;letter-spacing:.4px}"
      + ".tk-a .big{font-size:27px;font-weight:700;color:var(--text);font-variant-numeric:tabular-nums;line-height:1.1}"
      + ".tk-a .big.ok{color:var(--green)}.tk-a .big.warn{color:var(--accent)}.tk-a .big.bad{color:var(--red)}"
      + ".tk-a .s{font-size:12.5px;color:var(--text2);line-height:1.5}"
      + ".tk-a .track{height:8px;border-radius:5px;background:var(--surface-2);overflow:hidden}"
      + ".tk-a .fill{height:100%;border-radius:5px;background:var(--accent-solid);transition:width .3s}"
      + ".tk-a .fill.warn{background:var(--accent)}.tk-a .fill.bad{background:var(--red)}"
      + ".tk-a .fill.ok{background:var(--green)}"
      + ".tk-mini{align-self:flex-start;margin-top:2px;padding:5px 11px;border-radius:8px;border:1px solid var(--glass-brd);background:transparent;color:var(--text2);font-size:12px;cursor:pointer}"
      + ".tk-mini:hover{color:var(--text);border-color:var(--accent)}"
      // --- Form ngân sách (bung ra từ ô tiền)
      + ".tk-ns{margin:-6px 0 18px;padding:14px 16px;border:1px solid var(--glass-brd);border-radius:12px;background:var(--glass)}"
      + ".tk-ns .row{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}"
      + ".tk-ns label{display:block;font-size:12px;color:var(--text2);margin-bottom:4px}"
      // Chỉ ô nhập SỐ mới giãn hết hàng. Viết trơn `.tk-ns input{width:100%}` là ô tick cũng
      // ăn luật đó, nó phình ra chiếm nửa hàng và đẩy chữ sang tận mép phải.
      + ".tk-ns input[type=number]{width:100%;padding:7px 10px;border-radius:8px;border:1px solid var(--glass-brd);background:var(--surface-2);color:var(--text);font-size:13px}"
      + ".tk-ns .chk{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--text2);margin-top:11px;cursor:pointer}"
      + ".tk-ns .chk input{flex:0 0 auto;width:15px;height:15px;margin:0;accent-color:var(--accent-solid)}"
      + ".tk-ns .acts{display:flex;gap:8px;margin-top:12px;align-items:center}"
      + ".tk-ns button.save{padding:7px 15px;border-radius:9px;border:0;background:var(--accent-solid);color:var(--on-accent);font-size:13px;font-weight:600;cursor:pointer}"
      + ".tk-ns .hint{font-size:11.5px;color:var(--text3);line-height:1.6;margin-top:10px}"
      // --- Ô số phụ
      + ".tk-cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:22px}"
      + ".tk-card{flex:1 1 140px;background:var(--glass);border:1px solid var(--glass-brd);border-radius:12px;padding:13px 15px}"
      + ".tk-card .k{font-size:11.5px;color:var(--text3);letter-spacing:.3px;text-transform:uppercase}"
      + ".tk-card .v{font-size:22px;font-weight:700;color:var(--text);margin-top:5px;font-variant-numeric:tabular-nums}"
      + ".tk-card .s{font-size:12px;color:var(--text2);margin-top:3px}"
      + ".tk-card.accent .v{color:var(--accent)}"
      + ".tk-up{color:var(--red)}.tk-down{color:var(--green)}"
      + ".tk-sec{font-size:11.5px;color:var(--text3);text-transform:uppercase;letter-spacing:1px;margin:22px 0 12px;font-weight:600}"
      // --- Biểu đồ ngày + hàng mốc sự kiện ngay dưới trục
      + ".tk-chart{display:flex;align-items:flex-end;gap:3px;height:160px;padding:6px 2px 0;overflow-x:auto}"
      + ".tk-col{flex:0 0 auto;width:9px;display:flex;flex-direction:column-reverse;align-items:stretch;height:100%;cursor:default}"
      + ".tk-seg2{width:100%;min-height:0}"
      + ".tk-xrow{display:flex;gap:3px;border-top:1px solid var(--glass-brd);padding-top:5px;overflow-x:auto}"
      + ".tk-x{flex:0 0 auto;width:9px;text-align:center;font-size:8px;color:var(--text3)}"
      + ".tk-mrow{display:flex;gap:3px;overflow-x:auto;margin-top:2px;height:14px}"
      + ".tk-m{flex:0 0 auto;width:9px;text-align:center;line-height:1;color:var(--accent);cursor:default}"
      + ".tk-m svg{width:11px;height:11px;vertical-align:top}"
      + ".tk-legend{display:flex;gap:14px;font-size:12px;color:var(--text2);margin-top:9px;flex-wrap:wrap}"
      + ".tk-dot{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;vertical-align:middle}"
      + ".tk-grid{display:grid;grid-template-columns:1fr 1fr;gap:26px}"
      + "@media(max-width:640px){.tk-grid{grid-template-columns:1fr}}"
      + ".tk-blist .row{display:flex;align-items:center;gap:9px;margin-bottom:9px;font-size:13px}"
      + ".tk-blist .lab{width:120px;color:var(--text2);flex:0 0 auto;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}"
      + ".tk-blist .track{flex:1;height:9px;background:var(--surface-2);border-radius:5px;overflow:hidden}"
      + ".tk-blist .fill{height:100%;border-radius:5px}"
      + ".tk-blist .val{width:56px;text-align:right;color:var(--text);font-variant-numeric:tabular-nums;flex:0 0 auto}"
      + ".tk-tbl{width:100%;border-collapse:collapse;font-size:13px}"
      + ".tk-tbl th{text-align:left;color:var(--text3);font-weight:600;font-size:11.5px;padding:5px 8px;border-bottom:1px solid var(--glass-brd)}"
      + ".tk-tbl td{padding:7px 8px;border-bottom:1px solid var(--surface-2);font-variant-numeric:tabular-nums}"
      + ".tk-tbl td.num{text-align:right;color:var(--link-ink)}"
      + ".tk-tbl td.act{text-align:right;width:1%;white-space:nowrap}"
      + ".tk-go{padding:3px 10px;border-radius:7px;border:1px solid var(--glass-brd);background:transparent;color:var(--text2);font-size:11.5px;cursor:pointer}"
      + ".tk-go:hover{color:var(--text);border-color:var(--accent)}"
      + ".tk-go.on{color:var(--green);border-color:var(--green)}"
      + ".tk-ins{margin-top:8px}"
      + ".tk-ins .item{display:flex;gap:10px;padding:11px 13px;border:1px solid var(--glass-brd);border-radius:10px;background:var(--glass);margin-bottom:9px}"
      + ".tk-ins .item.warn{border-left:3px solid var(--red)}"
      + ".tk-ins .item.info{border-left:3px solid var(--link-ink)}"
      + ".tk-ins .ico{font-size:16px;flex:0 0 auto}"
      + ".tk-ins .t{font-weight:600;color:var(--text);font-size:13.5px}"
      + ".tk-ins .d{color:var(--text2);font-size:12.5px;margin-top:2px;line-height:1.5}"
      + ".tk-note{margin-top:22px;font-size:12px;color:var(--text3);line-height:1.55;max-width:760px}"
      // Dải chế độ tiết kiệm. Vẫn nằm ĐẦU trang (chủ repo chốt vậy), nhưng thu về MỘT DÒNG:
      // đây là cái công tắc chỉnh vài tháng một lần, không đáng chiếm trọn màn hình đầu mỗi
      // lần mở trang. Bấm vào mới bung ba nút với đầy đủ số liệu.
      + ".tk-muc{margin-bottom:14px}"
      + ".tk-muc-strip{display:flex;align-items:center;gap:9px;width:100%;text-align:left;padding:9px 14px;border-radius:11px;border:1px solid var(--glass-brd);background:var(--glass);color:var(--text2);font-size:13px;cursor:pointer}"
      + ".tk-muc-strip:hover{border-color:var(--accent)}"
      + ".tk-muc-strip b{color:var(--text)}"
      + ".tk-muc-strip .pc{color:var(--accent);font-weight:700}"
      + ".tk-muc-strip .sp{margin-left:auto;display:flex;align-items:center;gap:5px;color:var(--text3);font-size:12px}"
      + ".tk-muc-body{margin-top:10px}"
      + ".tk-muc-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}"
      + ".tk-muc-b{position:relative;text-align:left;cursor:pointer;padding:13px 15px;border-radius:12px;border:1px solid var(--glass-brd);background:var(--glass);color:var(--text);transition:.12s}"
      + ".tk-muc-b:hover:not(:disabled){border-color:var(--accent)}"
      + ".tk-muc-b:disabled{opacity:.55;cursor:default}"
      + ".tk-muc-b.on{border-color:var(--accent);background:var(--accent-wash-2,var(--glass))}"
      + ".tk-muc-b b{display:block;font-size:14px}"
      + ".tk-muc-top{display:flex;align-items:baseline;gap:8px;justify-content:space-between}"
      + ".tk-muc-pct{font-size:13px;font-weight:700;color:var(--accent);white-space:nowrap}"
      + ".tk-muc-tok{display:block;font-size:11.5px;color:var(--text3);margin:2px 0 5px;font-variant-numeric:tabular-nums}"
      + ".tk-muc-b small{display:block;font-size:12px;line-height:1.5;color:var(--text2)}"
      + ".tk-muc-now{display:inline-block;margin-top:8px;font-size:11px;padding:1px 8px;border-radius:999px;background:var(--accent-solid);color:var(--on-accent)}"
      + ".tk-muc-na{display:inline-block;margin-top:8px;font-size:11px;color:var(--text3)}"
      + ".tk-muc-note{font-size:12px;color:var(--text3);line-height:1.55;margin-top:10px;max-width:720px}"
      + ".tk-muc-do{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-top:14px;padding:13px 15px;border:1px solid var(--glass-brd);border-radius:12px;background:var(--glass)}"
      + ".tk-muc-do .k{font-size:12px;color:var(--text2)}"
      + ".tk-muc-do .v{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:3px}"
      + ".tk-muc-do .s{font-size:11px;color:var(--text3);margin-top:2px}"
      + ".tk-muc-do .pct .v{color:var(--accent)}"
      + ".tk-tien{margin-top:10px;padding:13px 15px;border:1px solid var(--glass-brd);border-radius:12px;background:var(--glass)}"
      + ".tk-tien-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}"
      + ".tk-tien .k{font-size:12px;color:var(--text2)}"
      + ".tk-tien .v{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:3px}"
      + ".tk-tien .s{font-size:11px;color:var(--text3);margin-top:2px}"
      + ".tk-tien .tien .v{color:var(--accent2,var(--accent))}"
      + ".tk-tien-note{font-size:11.5px;color:var(--text3);line-height:1.65;margin-top:11px}"
      + ".tk-muc-toast{padding:9px 13px;border-radius:10px;font-size:13px;margin-top:10px;border:1px solid var(--glass-brd)}"
      + ".tk-muc-toast.ok{border-color:var(--accent)}"
      + ".tk-muc-toast.err{color:var(--red)}";
    var s = document.createElement("style"); s.textContent = css; document.head.appendChild(s);
  }

  function render(el) {
    injectCss();
    state.el = el;
    el.innerHTML = '<div class="tk-wrap"><div class="cview-placeholder" style="min-height:220px"><div class="ph-ico">' + ic("loader", { cls: "ic-xl ic-spin" }) + '</div><div class="dim">Đang dựng chỉ số token...</div></div></div>';
    load(true);
  }

  // Mức tiết kiệm không đổi theo kỳ hay theo provider, nên chỉ gọi lại khi thật sự cần
  // (lần đầu mở trang, và sau khi người dùng bấm đổi mức).
  function loadMuc(force) {
    if (state.muc && !force) return Promise.resolve(state.muc);
    return fetch("/runtime/muc").then(function (r) { return r.json(); })
      .then(function (d) { state.muc = d || {}; return state.muc; })
      .catch(function () { return state.muc || null; });
  }

  // Danh sách loop của mọi brain. Chỉ nạp một lần: nó dùng cho khối "việc nền đang chạy",
  // và người dùng bấm tắt loop thì ta tự cập nhật tại chỗ chứ không nạp lại cả trang.
  function loadViec(force) {
    if (state.viec && !force) return Promise.resolve(state.viec);
    return fetch("/viec/all").then(function (r) { return r.json(); })
      .then(function (d) { state.viec = d || {}; return state.viec; })
      .catch(function () { return state.viec || null; });
  }

  // fetch KHÔNG reject với status 4xx/5xx, mà middleware đăng nhập của Javis lại trả 401 kèm
  // một THÂN JSON. Nên `.then(r => r.json())` trơn sẽ resolve ngon lành với {error:...}, khối
  // .catch không bao giờ chạy, và trang vẽ ra "0 token / $0.00 / Chưa có dữ liệu" ở mọi ô -
  // trông y hệt một tháng chưa dùng gì. Phiên hết hạn mà báo là "bạn chưa tiêu đồng nào" là
  // kiểu sai tệ nhất: nó không giống lỗi.
  function jsonOk(r) {
    if (!r.ok) {
      var e = new Error(r.status === 401 || r.status === 403
        ? "Phiên đăng nhập đã hết hạn. Tải lại trang để đăng nhập lại."
        : "Máy chủ trả lỗi " + r.status + ".");
      e.httpStatus = r.status;
      throw e;
    }
    return r.json();
  }

  function loi(msg) {
    if (!state.el) return;
    state.el.innerHTML = '<div class="tk-wrap"><div class="cview-placeholder">'
      + '<div class="ph-ico">' + ic("chart-column", { cls: "ic-xl ic-dim" }) + "</div>"
      + "<div>" + esc(msg || "Không tải được số liệu token.") + "</div>"
      + '<button class="tk-mini" data-act="thu-lai" style="margin:12px auto 0">Thử lại</button>'
      + "</div></div>";
    var b = state.el.querySelector('[data-act="thu-lai"]');
    if (b) b.onclick = function () { render(state.el); };
  }

  // Mọi thao tác trên trang đều kết thúc bằng load() -> paint() -> gán đè innerHTML, nên form
  // ngân sách bị dựng lại từ đầu và số người dùng đang gõ dở biến mất. Nhặt lại trước khi vẽ.
  function nhoForm() {
    var el = state.el; if (!el) return;
    var o = el.querySelector("#tk-ns-goi");
    if (!o) return;                       // form đang đóng, không có gì để nhớ
    function v(id) { var e = el.querySelector("#" + id); return e ? e.value : ""; }
    function c(id) { var e = el.querySelector("#" + id); return !!(e && e.checked); }
    state.nsForm = { goi: v("tk-ns-goi"), tran: v("tk-ns-tran"), h5: v("tk-ns-5h"),
                     phanh: c("tk-ns-phanh"), tuan: c("tk-ns-tuan") };
  }

  function load(doRefresh) {
    nhoForm();
    var q = "?period=" + encodeURIComponent(state.period)
      + (state.provider ? "&provider=" + state.provider : "")
      + "&refresh=" + (doRefresh ? 1 : 0);
    Promise.all([
      fetch("/usage/summary" + q).then(jsonOk),
      fetch("/usage/insights?period=" + encodeURIComponent(state.period)).then(jsonOk).catch(function () { return { items: [] }; }),
      fetch("/usage/tong-quan?period=" + encodeURIComponent(state.period)).then(jsonOk).catch(function () { return null; }),
      loadMuc(false),
      loadViec(false),
    ]).then(function (res) {
      state.tq = res[2] || null;
      paint(res[0] || {}, (res[1] || {}).items || []);
    }).catch(function (e) {
      loi(e && e.message ? e.message : "");
    });
  }

  // ===== Mức tiết kiệm token =====
  // Chỉ vẽ những gì người dùng cuối quyết định được: tên mức, tiết kiệm bao nhiêu, và số đo
  // thật. Mọi thứ còn lại của trang chẩn đoán cũ (allocation tính bằng phần vạn, tên đường
  // canary, cửa sổ token 60 giây, execution_path từng lượt) là ngôn ngữ của người vận hành
  // máy, không phải của người đang trả tiền token.
  //
  // Khối `do_duoc` bên dưới là phép đo A/B: so trung bình token của lượt đi đường đầy đủ với
  // lượt đi đường tiết kiệm trong cùng cửa sổ. Chính xác hơn phép đối chứng ở ô lớn phía
  // trên, nhưng chỉ có số khi cả hai đường cùng chạy - tức là quanh lúc vừa đổi mức. Nên nó
  // ở ĐÂY, trong phần bung ra, chứ không phải là chỗ duy nhất báo tiết kiệm như bản trước.
  //
  // Ba mức tin cậy khác nhau, và phải nói rõ cái nào là cái nào, không thì con số to nhất
  // (tiền mỗi tháng) bị đọc như một hoá đơn:
  //   - token tiết kiệm trong cửa sổ vừa đo: ĐO ĐƯỢC, chắc nhất
  //   - token mỗi tháng: PHÉP CHIẾU theo đúng nhịp đó, đúng khi cách dùng không đổi
  //   - tiền: ƯỚC LƯỢNG, phụ thuộc bảng giá tham khảo và tỉ giá
  // Người đang dùng GÓI THUÊ BAO còn một lớp nữa: họ trả tiền gói chứ không trả theo token,
  // nên tiền ở đây là "nếu tính theo giá API" chứ không phải tiền mặt tiết kiệm được. Nói
  // dối chỗ này thì cả trang mất tin cậy.
  function tienHtml(dod, d) {
    var t = dod.tien || {};
    if (!dod.token_tiet_kiem) return "";
    var eng = d.engine || {};
    var thueBao = eng.loai === "Gói thuê bao";
    var usdThang = fCost(t.usd_thang || 0);
    var cachTinh = t.nguon_gia === "tay"
      ? "theo đơn giá bạn tự đặt"
      : (t.nguon_gia === "bang"
        ? "theo giá tham khảo của model đang dùng"
        : "theo một mức giá phổ biến, vì chưa nhận ra model đang dùng");
    return '<div class="tk-tien">'
      + '<div class="tk-tien-row">'
      + '<div><div class="k">Đã tiết kiệm</div><div class="v">' + fTok(dod.token_tiet_kiem)
      + '</div><div class="s">token, trong ' + (dod.gio_do || 24) + ' giờ qua</div></div>'
      + '<div><div class="k">Theo nhịp này</div><div class="v">' + fTok(dod.token_thang)
      + '</div><div class="s">token mỗi tháng</div></div>'
      + '<div class="tien"><div class="k">Quy ra tiền</div><div class="v">~' + usdThang + "</div>"
      + '<div class="s">mỗi tháng, theo giá API</div></div>'
      + "</div>"
      + '<div class="tk-tien-note">Số token là <b>đo được</b>; phần mỗi tháng là phép chiếu'
      + ' theo đúng nhịp dùng của ' + (dod.gio_do || 24) + ' giờ vừa rồi. Tiền là <b>ước lượng</b> '
      + esc(cachTinh) + ' ($' + (t.gia_1m_usd || 0) + ' cho 1 triệu token vào).'
      + (thueBao
        ? ' Bạn đang dùng <b>gói thuê bao</b> nên không trả theo token: con số này là mức tiết kiệm'
        + ' quy đổi nếu tính theo giá API, và trên thực tế nó thể hiện thành việc lâu chạm trần gói hơn.'
        : '')
      + " Muốn con số đúng với hợp đồng của bạn thì đặt <code>gia_input_1m</code> trong"
      + " <code>settings.json</code> (mục <code>model</code>)."
      + "</div></div>";
  }

  function mucHtml(d) {
    if (!d || !(d.danh_sach || []).length) return "";
    var uocMuc = ((d.uoc_tinh || {}).muc) || {};
    var dod = d.do_duoc || {};
    var dangDung = null;
    var btns = d.danh_sach.map(function (p) {
      var m = uocMuc[p.id] || {};
      if (p.id === d.muc) dangDung = { nhan: p.nhan, m: m };
      var pct = (p.id !== "off" && m.phan_tram)
        ? '<span class="tk-muc-pct">-' + (+m.phan_tram || 0) + "% token</span>" : "";
      var tok = m.token_moi_request != null
        ? '<span class="tk-muc-tok">' + (+m.token_moi_request || 0).toLocaleString(LOC()) + " token mỗi lượt</span>" : "";
      // Bộ não đang chạy không ăn được mức này thì phải nói NGAY trên nút. Khoe một con số
      // không bao giờ tới là dạy người dùng thôi tin cả trang.
      var na = m.ap_dung === false ? '<span class="tk-muc-na">không áp cho bộ não đang dùng</span>' : "";
      var now = p.id === d.muc ? '<span class="tk-muc-now">đang dùng</span>' : "";
      return '<button class="tk-muc-b' + (p.id === d.muc ? " on" : "") + '" data-muc="' + esc(p.id) + '">'
        + '<span class="tk-muc-top"><b>' + esc(p.nhan) + "</b>" + pct + "</span>"
        + tok + "<small>" + esc(m.ghi_chu || p.mo_ta) + "</small>" + na + now + "</button>";
    }).join("");

    var doHtml = "";
    if (dod.du_du_lieu) {
      var gio = dod.gio_do || 24;
      doHtml = '<div class="tk-muc-do">'
        + '<div><div class="k">Chế độ Đầy đủ</div><div class="v">' + fTok(dod.tb_cu) + '</div><div class="s">token mỗi lượt, ' + (dod.so_luot_cu || 0) + " lượt</div></div>"
        + '<div><div class="k">Khi tiết kiệm</div><div class="v">' + fTok(dod.tb_moi) + '</div><div class="s">token mỗi lượt, ' + (dod.so_luot_moi || 0) + " lượt</div></div>"
        + '<div class="pct"><div class="k">Giảm được</div><div class="v">' + (dod.phan_tram || 0) + '%</div><div class="s">số thật đo trong ' + gio + ' giờ qua</div></div>'
        + "</div>";
      doHtml += tienHtml(dod, d);
    }

    var chuaChon = d.tu_chon ? "" : " Mức đang chạy là mặc định của bản này, bạn chưa tự chọn bao giờ."
      + " Bấm một mức bất kỳ là Javis ghim lại, từ đó không bản cập nhật nào đổi nữa.";

    // Dải một dòng luôn hiện; phần thân chỉ dựng khi người dùng bung ra.
    var mm = (dangDung && dangDung.m) || {};
    var strip = '<button class="tk-muc-strip" data-act="mo-muc">'
      + ic("zap", { cls: "ic-sm ic-accent" })
      + "<span>Chế độ tiết kiệm token: <b>" + esc((dangDung && dangDung.nhan) || d.muc || "?") + "</b>"
      + (mm.phan_tram ? ' <span class="pc">-' + (+mm.phan_tram || 0) + "%</span>" : "")
      + (mm.token_moi_request != null
        ? " · " + (+mm.token_moi_request || 0).toLocaleString(LOC()) + " token mỗi lượt" : "")
      + "</span>"
      + '<span class="sp">' + (state.moMuc ? "Thu lại" : "Đổi")
      + ic(state.moMuc ? "chevron-up" : "chevron-down", { cls: "ic-sm" }) + "</span></button>";

    var body = state.moMuc
      ? '<div class="tk-muc-body"><div class="tk-muc-list">' + btns + "</div>"
      + (state.toast ? state.toast : "")
      + doHtml
      + '<div class="tk-muc-note">Đổi xong có hiệu lực ngay, không cần khởi động lại. Thấy Javis'
      + " trả lời tệ đi thì bấm <b>Tắt</b> là quay lại như cũ lập tức."
      + " Con số phần trăm là ước lượng đo trên chính bộ não và bộ nhớ của bạn."
      + esc(chuaChon) + "</div></div>"
      : (state.toast || "");

    return '<div class="tk-muc">' + strip + body + "</div>";
  }

  function bindMuc() {
    var el = state.el; if (!el) return;
    var mo = el.querySelector('[data-act="mo-muc"]');
    if (mo) mo.onclick = function () { state.moMuc = !state.moMuc; load(false); };
    el.querySelectorAll("[data-muc]").forEach(function (b) {
      b.onclick = function () {
        var id = b.getAttribute("data-muc");
        el.querySelectorAll("[data-muc]").forEach(function (x) { x.disabled = true; });
        var fd = new FormData(); fd.append("level", id);
        fetch("/runtime/preset", { method: "POST", body: fd })
          .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
          .then(function (res) {
            if (!res.ok || !res.j || res.j.ok === false) {
              state.toast = '<div class="tk-muc-toast err">' + esc((res.j && res.j.error) || "Đổi mức thất bại.") + "</div>";
            } else {
              var cb = (res.j.canh_bao || []).join(" ");
              state.toast = '<div class="tk-muc-toast ok">Đã chuyển sang mức "' + esc(res.j.nhan) + '". Có hiệu lực ngay.'
                + (cb ? " " + esc(cb) : "") + "</div>";
            }
            return loadMuc(true);
          })
          .catch(function (e) {
            state.toast = '<div class="tk-muc-toast err">Đổi mức thất bại: ' + esc(e && e.message ? e.message : e) + "</div>";
          })
          .then(function () { load(false); });
      };
    });
  }

  // ===== Câu mở đầu + ba ô hành động =====
  function heroHtml() {
    var t = state.tq; if (!t) return "";
    var phu = [];
    if ((t.tiet_kiem || {}).suy_doan && (t.tiet_kiem || {}).token) {
      phu.push("Chưa có nhật ký đổi mức nên phần tiết kiệm giả định cả kỳ chạy cùng một chế độ.");
    }
    if (!((t.tien || {}).goi || {}).gia_thang_usd) {
      phu.push("Khai giá gói mỗi tháng ở ô Tiền mặt bên dưới thì Javis tính được gói đang lời hay lỗ.");
    }
    return '<div class="tk-hero"><p>' + esc(t.cau || "") + "</p>"
      + (phu.length ? '<div class="sub">' + esc(phu.join(" ")) + "</div>" : "")
      + "</div>";
  }

  function oTien() {
    var t = state.tq; if (!t) return "";
    var ns = t.ngan_sach || {};
    var that = (t.tien || {}).that || {};
    var orb = that.openrouter;
    var body, thanh = "";
    if (ns.co) {
      var cls = ns.muc_do === "het" ? "bad" : (ns.muc_do === "sap_het" ? "warn" : "ok");
      thanh = '<div class="track"><div class="fill ' + cls + '" style="width:'
        + Math.min(100, Math.round((ns.ty_le || 0) * 100)) + '%"></div></div>';
      body = '<div class="big ' + cls + '">' + fCost(ns.da_tieu) + "</div>"
        + thanh
        + '<div class="s">trên trần ' + fCost(ns.tran) + " tháng này, còn " + fCost(ns.con)
        + (ns.du_bao_vuot ? ". Theo nhịp này sẽ vượt trần." : "") + "</div>";
    } else {
      // Chưa đặt trần thì ô này nói về ĐÚNG kỳ đang chọn, nên phải gọi tên kỳ ra. Đặt trần
      // rồi thì nó chuyển sang nói về THÁNG, vì trần là trần tháng - hai nghĩa khác nhau
      // trong cùng một ô, không nói rõ là người đọc so nhầm.
      body = '<div class="big">' + fCost(that.usd) + "</div>"
        + '<div class="s">' + esc((t.ten_ky || "Kỳ này").toLowerCase()) + ", tiền mặt thật"
        + (that.usd ? " (nhánh dùng API key)" : ", chưa đặt trần tháng") + "</div>";
    }
    if (orb && orb.remaining != null) {
      body += '<div class="s">OpenRouter còn <b style="color:var(--green)">' + fCost(orb.remaining) + "</b></div>";
    }
    if ((ns.dang_phanh || {}).bat) {
      body += '<div class="s" style="color:var(--accent)">Đang phanh: việc nền đã chuyển sang đường không tốn tiền.</div>';
    }
    return '<div class="tk-a"><div class="h">' + ic("shield", { cls: "ic-sm" }) + "Tiền mặt tháng này</div>"
      + body
      + '<button class="tk-mini" data-act="ns">' + (state.moNganSach ? "Đóng" : "Đặt ngân sách") + "</button></div>";
  }

  // Gói Claude/ChatGPT tính hạn mức theo CỬA SỔ vài giờ chứ không theo ngày, nên "hôm nay
  // dùng bao nhiêu" không trả lời được câu "tôi sắp bị chặn chưa".
  //
  // Hai ca hoàn toàn khác nhau, và tô cùng một màu là nói dối:
  //   - Người dùng ĐÃ KHAI trần: phần trăm là phần trăm của một hạn mức thật. Gần 100% thì
  //     đỏ là đúng, vì sắp bị chặn thật.
  //   - Chưa khai: ta so với ĐỈNH của chính họ, mà đỉnh thì không bao giờ vượt được - đang
  //     bận nhất từ trước tới nay là tự khắc 100%. Tô đỏ ở đây là doạ người vì một chuyện
  //     không có gì nguy hiểm. Ca này để số token làm con số chính, phần trăm chỉ là ngữ cảnh.
  function oTran() {
    var t = state.tq; if (!t) return "";
    var c = t.cua_so || {};
    var eng = t.engine || {};
    var thueBao = eng.loai === "Gói thuê bao";
    var body;
    if (c.tran_khai) {
      var tl = Math.min(1, c.ty_le || 0);
      var cls = tl >= 0.9 ? "bad" : (tl >= 0.7 ? "warn" : "ok");
      body = '<div class="big ' + cls + '">' + pct(tl) + "</div>"
        + '<div class="track"><div class="fill ' + cls + '" style="width:' + Math.round(tl * 100) + '%"></div></div>'
        + '<div class="s">' + fTok(c.tokens) + " token trong 5 giờ qua, trên trần bạn khai "
        + fTok(c.tran_khai) + ".</div>";
    } else {
      body = '<div class="big">' + fTok(c.tokens) + "</div>";
      if (c.dinh) {
        var tl2 = Math.min(1, c.ty_le || 0);
        body += '<div class="track"><div class="fill" style="width:' + Math.round(tl2 * 100) + '%"></div></div>'
          + '<div class="s">token trong 5 giờ qua. '
          + (tl2 >= 0.99
            ? "Đây đang là 5 giờ bận nhất của bạn từ trước tới nay."
            : "Bằng " + pct(tl2) + " mức cao nhất bạn từng chạm (" + fTok(c.dinh) + ").")
          + "</div>";
      } else {
        body += '<div class="s">token trong 5 giờ qua. Chưa đủ lịch sử để biết mốc của bạn ở đâu.</div>';
      }
      body += '<div class="s">Khai trần gói ở ô Tiền mặt thì Javis báo được lúc sắp bị chặn.</div>';
    }
    if (!thueBao) {
      body += '<div class="s">Bạn đang dùng API key nên không có trần gói; số này chỉ để thấy nhịp dùng.</div>';
    }
    return '<div class="tk-a"><div class="h">' + ic("chart-column", { cls: "ic-sm" }) + "Cửa sổ 5 giờ</div>"
      + body + "</div>";
  }

  function oTietKiem() {
    var t = state.tq; if (!t) return "";
    var k = t.tiet_kiem || {};
    if (!k.du_du_lieu) {
      // Hai lý do khác hẳn nhau, và gộp làm một là nói dối theo hướng làm người ta tắt chế độ
      // tiết kiệm đi: "chưa chạy lượt nào" với "bạn đang chỉnh tay nên Javis không biết cấu
      // hình đó tốn bao nhiêu".
      return '<div class="tk-a"><div class="h">' + ic("sparkles", { cls: "ic-sm" }) + "Đã tiết kiệm</div>"
        + '<div class="big">-</div><div class="s">'
        + (k.khong_do_duoc
          ? "Bạn đang tự chỉnh tay từng đường nên Javis không biết cấu hình này tốn bao nhiêu mỗi lượt. Chọn một mức có sẵn là đo được."
          : "Chưa có lượt nào của Javis trong kỳ này để tính.")
        + "</div></div>";
    }
    var ti = k.tien || {};
    return '<div class="tk-a"><div class="h">' + ic("sparkles", { cls: "ic-sm" }) + "Đã tiết kiệm</div>"
      + '<div class="big warn">' + fTok(k.token) + "</div>"
      + '<div class="s">token không phải gửi, qua ' + (k.so_luot || 0) + " lượt của Javis. "
      + "Chế độ <b>" + esc(k.nhan_muc || "") + "</b> cắt " + (k.phan_tram || 0)
      + "% chi phí cố định mỗi lượt.</div>"
      + '<div class="s">Quy theo giá API khoảng <b>' + fCost(ti.usd) + "</b>.</div></div>";
  }

  function nganSachHtml() {
    if (!state.moNganSach) return "";
    var t = state.tq || {};
    var ns = t.ngan_sach || {};
    var g = ((t.tien || {}).goi || {});
    var c = t.cua_so || {};
    // Giá trị đang gõ dở thắng giá trị đã lưu: người dùng vừa gõ 30 rồi bấm chip kỳ mà thấy ô
    // trắng lại thì lần sau họ không tin cái form nữa.
    var f = state.nsForm || {};
    function val(dangGo, daLuu) { return dangGo != null && dangGo !== "" ? dangGo : (daLuu || ""); }
    var tick = function (k, mac_dinh) { return (f[k] != null ? f[k] : mac_dinh) ? " checked" : ""; };
    return '<div class="tk-ns"><div class="row">'
      + '<div><label>Giá gói mỗi tháng (USD)</label><input id="tk-ns-goi" type="number" min="0" step="1" value="'
      + esc(val(f.goi, g.gia_thang_usd)) + '" placeholder="Ví dụ 200"></div>'
      + '<div><label>Trần tiền API mỗi tháng (USD)</label><input id="tk-ns-tran" type="number" min="0" step="1" value="'
      + esc(val(f.tran, ns.tran)) + '" placeholder="Ví dụ 30"></div>'
      + '<div><label>Trần token cửa sổ 5 giờ</label><input id="tk-ns-5h" type="number" min="0" step="1000" value="'
      + esc(val(f.h5, c.tran_khai)) + '" placeholder="Để trống thì Javis tự đo"></div>'
      + "</div>"
      + '<label class="chk"><input id="tk-ns-phanh" type="checkbox"' + tick("phanh", ns.tu_phanh) + ">"
      + "Chạm trần thì tự đẩy việc nền sang đường không tốn tiền</label>"
      + '<label class="chk"><input id="tk-ns-tuan" type="checkbox"' + tick("tuan", !!t.bao_cao_tuan) + ">"
      + "Gửi báo cáo token về chat mỗi sáng thứ Hai</label>"
      + '<div class="acts"><button class="save" data-act="ns-luu">Lưu</button>'
      + '<button class="tk-mini" data-act="ns">Huỷ</button></div>'
      + '<div class="hint">Bốn con số này Javis không tự biết được: nhà cung cấp không cho lấy giá gói'
      + " hay hạn mức gói qua API. Để trống thì trang chỉ nói được cái nó đo được."
      + " Tự phanh chỉ đụng tới <b>việc chạy nền</b>, chat của bạn không bị hạ model.</div></div>";
  }

  function card(k, v, sub, accent) {
    return '<div class="tk-card' + (accent ? " accent" : "") + '"><div class="k">' + esc(k) + '</div><div class="v">' + v + '</div><div class="s">' + (sub || "") + "</div></div>";
  }

  function barList(items, labelMap, colorFn) {
    if (!items || !items.length) return '<div style="color:var(--text3);font-size:13px">Chưa có dữ liệu.</div>';
    var max = Math.max.apply(null, items.map(function (x) { return x.tokens; })) || 1;
    return '<div class="tk-blist">' + items.map(function (x) {
      var lab = (labelMap && labelMap[x.key]) || model(x.key) || x.key;
      var w = Math.max(2, Math.round(x.tokens / max * 100));
      var col = colorFn ? colorFn(x.key) : "var(--accent)";
      return '<div class="row"><div class="lab" title="' + esc(lab) + '">' + esc(lab) + '</div>'
        + '<div class="track"><div class="fill" style="width:' + w + "%;background:" + col + '"></div></div>'
        + '<div class="val">' + fTok(x.tokens) + "</div></div>";
    }).join("") + "</div>";
  }

  // Bảng "ngốn nhất" kèm NÚT XỬ LÝ. Bảng chỉ để ngắm thì người đọc biết cái gì đắt mà vẫn
  // phải tự đi tìm chỗ chỉnh - và đa số sẽ không đi.
  function table(items, header, actFn) {
    if (!items || !items.length) return '<div style="color:var(--text3);font-size:13px">Chưa có dữ liệu.</div>';
    var rows = items.slice(0, 8).map(function (x) {
      return "<tr><td>" + esc(model(x.key) || x.key) + '</td><td class="num">' + fTok(x.tokens)
        + '</td><td class="num">' + (x.cost > 0 ? fCost(x.cost) : "-") + "</td>"
        + (actFn ? '<td class="act">' + actFn(x) + "</td>" : "") + "</tr>";
    }).join("");
    return '<table class="tk-tbl"><thead><tr><th>' + esc(header) + '</th><th style="text-align:right">Token</th><th style="text-align:right">Quy đổi</th>'
      + (actFn ? "<th></th>" : "") + "</tr></thead><tbody>" + rows + "</tbody></table>";
  }

  function tableProj(items) {
    if (!items || !items.length) return '<div style="color:var(--text3);font-size:13px">Chưa có dữ liệu.</div>';
    var rows = items.slice(0, 8).map(function (x) {
      return "<tr><td>" + esc(x.key) + '</td><td class="num">' + fTok(x.tokens) + '</td><td class="num">' + (x.sessions || 0) + "</td></tr>";
    }).join("");
    return '<table class="tk-tbl"><thead><tr><th>Brain / dự án</th><th style="text-align:right">Token</th><th style="text-align:right">Phiên</th></tr></thead><tbody>' + rows + "</tbody></table>";
  }

  // Loop đang bật, kèm nút tắt ngay tại chỗ. Đây là hành động DUY NHẤT trên trang này vừa
  // đáng làm vừa làm được một cách rõ ràng: việc nền là phần tiêu token lúc không ai ngồi
  // nhìn, và tắt một loop là quyết định đảo ngược được trong một cú bấm.
  function loopHtml() {
    var v = state.viec; if (!v || !(v.brains || []).length) return "";
    var rows = [];
    (v.brains || []).forEach(function (b) {
      (b.loops || []).forEach(function (lp) {
        rows.push({ brain: b.path, brainName: b.name, slug: lp.slug, name: lp.name || lp.slug,
                    enabled: !!lp.enabled, interval: lp.interval_min || 0, mode: lp.mode || "" });
      });
    });
    if (!rows.length) return "";
    rows.sort(function (a, b) { return (b.enabled ? 1 : 0) - (a.enabled ? 1 : 0); });
    var tr = rows.slice(0, 8).map(function (r) {
      return "<tr><td>" + esc(r.name) + '<div style="font-size:11px;color:var(--text3)">'
        + esc(r.brainName || "") + (r.interval ? " · mỗi " + r.interval + " phút" : "")
        + (r.mode ? " · " + esc(r.mode) : "") + "</div></td>"
        + '<td class="num">' + (r.enabled ? "đang chạy" : "đã tắt") + "</td>"
        + '<td class="act"><button class="tk-go' + (r.enabled ? " on" : "") + '" data-loop="'
        + esc(r.slug) + '" data-brain="' + esc(r.brain) + '">'
        + (r.enabled ? "Tắt" : "Bật") + "</button></td></tr>";
    }).join("");
    return '<div class="tk-sec">Việc nền đang chạy</div>'
      + '<table class="tk-tbl"><thead><tr><th>Loop</th><th style="text-align:right">Trạng thái</th><th></th></tr></thead><tbody>'
      + tr + "</tbody></table>";
  }

  // So NHỊP giữa các engine: token mỗi lượt, tách theo loại việc. Tổng token không so được
  // vì engine chạy nhiều việc hơn thì đương nhiên tốn hơn.
  function engineHtml() {
    var t = state.tq; if (!t || !(t.nhip_engine || []).length) return "";
    var rows = t.nhip_engine.slice(0, 6).map(function (x) {
      return "<tr><td>" + esc(PROV_LABEL[x.provider] || x.provider) + "</td>"
        + "<td>" + esc(ACT_LABEL[x.activity] || x.activity) + "</td>"
        + '<td class="num">' + fTok(x.moi_luot) + "</td>"
        + '<td class="num">' + (x.turns || 0) + "</td>"
        + '<td class="num">' + (x.cost_moi_luot > 0 ? "$" + (+x.cost_moi_luot).toFixed(3) : "-") + "</td></tr>";
    }).join("");
    return '<div class="tk-sec">Cùng một loại việc thì bộ não nào đắt hơn</div>'
      + '<table class="tk-tbl"><thead><tr><th>Bộ não</th><th>Việc</th>'
      + '<th style="text-align:right">Token/lượt</th><th style="text-align:right">Lượt</th>'
      + '<th style="text-align:right">Quy đổi/lượt</th></tr></thead><tbody>' + rows + "</tbody></table>";
  }

  function paint(s, insights) {
    var el = state.el; if (!el) return;
    var k = s.kpi || {};
    var t = state.tq || {};
    var chips = PERIODS.map(function (p) {
      return '<button class="tk-chip' + (p[0] === state.period ? " on" : "") + '" data-period="' + p[0] + '">' + esc(p[1]) + "</button>";
    }).join("");
    var seg = PROVS.map(function (p) {
      return '<button class="' + (p[0] === state.provider ? "on" : "") + '" data-prov="' + p[0] + '">' + esc(p[1]) + "</button>";
    }).join("");
    var bar1 = '<div class="tk-bar1"><div class="tk-chips">' + chips + '</div>'
      + '<div class="tk-seg">' + seg + '</div>'
      + '<button class="tk-refresh" data-act="refresh">' + (state.busy ? "Đang quét..." : "↻ Làm mới") + "</button></div>";

    var deltaHtml = "";
    if (k.delta_pct != null) {
      var up = k.delta_pct >= 0;
      deltaHtml = '<span class="' + (up ? "tk-up" : "tk-down") + '">' + (up ? "▲" : "▼") + " " + Math.abs(k.delta_pct) + "%</span> vs kỳ trước";
    } else { deltaHtml = "kỳ trước chưa có số"; }

    var act = '<div class="tk-act">' + oTien() + oTran() + oTietKiem() + "</div>"
      + (state.nsToast || "") + nganSachHtml();

    var cache = t.cache || {};
    var db = t.du_bao || {};
    var cards = '<div class="tk-cards">'
      + card("Tổng token", fTok(k.tokens), deltaHtml, true)
      + card("Số lượt", (k.turns || 0).toLocaleString(LOC()), fTok(k.avg_per_turn) + " token mỗi lượt")
      + card("Cache đỡ cho", fCost(cache.usd), "nhờ dùng lại ngữ cảnh (" + pct(cache.ty_le) + ")")
      + card("Phiên", (k.sessions || 0), "tb " + fTok(k.avg_per_session) + "/phiên")
      + (db.co ? card("Hết kỳ ước chừng", fTok(db.tokens), "còn " + (db.con_ngay || 0) + " ngày nữa") : "")
      + "</div>";

    // Biểu đồ theo ngày + hàng MỐC ngay dưới trục. Không có mốc thì tháng sau nhìn lại chỉ
    // thấy một cái bậc thang không ai giải thích được.
    var ts = s.timeseries || [];
    var mocTheoNgay = {};
    (t.moc || []).forEach(function (m) {
      (mocTheoNgay[m.day] = mocTheoNgay[m.day] || []).push(m);
    });
    var maxD = Math.max.apply(null, ts.map(function (d) { return d.total; })) || 1;
    var cols = ts.map(function (d) {
      function seg2(v, col) { return v > 0 ? '<div class="tk-seg2" style="height:' + (v / maxD * 100) + "%;background:" + col + '"></div>' : ""; }
      var tip = d.day + ": " + fTok(d.total) + " token, " + (d.turns || 0) + " lượt";
      return '<div class="tk-col" title="' + esc(tip) + '">'
        + seg2(d.claude, PROV_COLOR.claude) + seg2(d.codex, PROV_COLOR.codex) + seg2(d.api, PROV_COLOR.api) + "</div>";
    }).join("");
    var xs = ts.map(function (d) { return '<div class="tk-x">' + esc(d.day.slice(8)) + "</div>"; }).join("");
    var ms = ts.map(function (d) {
      var mm = mocTheoNgay[d.day];
      if (!mm || !mm.length) return '<div class="tk-m"></div>';
      var nhan = mm.map(function (x) { return x.nhan || x.loai; }).join(" · ");
      return '<div class="tk-m" title="' + esc(d.day + ": " + nhan) + '">'
        + ic(MOC_ICO[mm[0].loai] || "info", { cls: "ic-sm ic-accent" }) + "</div>";
    }).join("");
    var legend = '<div class="tk-legend">'
      + '<span><span class="tk-dot" style="background:' + PROV_COLOR.claude + '"></span>Claude</span>'
      + '<span><span class="tk-dot" style="background:' + PROV_COLOR.codex + '"></span>ChatGPT</span>'
      + '<span><span class="tk-dot" style="background:' + PROV_COLOR.api + '"></span>API</span>'
      + "<span>" + ic("zap", { cls: "ic-sm ic-accent" }) + " đổi chế độ · "
      + ic("brain", { cls: "ic-sm ic-accent" }) + " đổi bộ não</span></div>";
    var chart = ts.length ? ('<div class="tk-sec">Token theo ngày</div><div class="tk-chart">' + cols + '</div><div class="tk-xrow">' + xs + '</div><div class="tk-mrow">' + ms + "</div>" + legend) : "";

    var grid = '<div class="tk-grid">'
      + "<div><div class=\"tk-sec\">Nguồn tiêu (bạn vs Javis)</div>" + barList(s.by_source, SRC_LABEL, function () { return "var(--accent)"; })
      + "<div class=\"tk-sec\">Hoạt động</div>" + barList(s.by_activity, ACT_LABEL, function () { return "var(--link-ink)"; }) + "</div>"
      + "<div><div class=\"tk-sec\">Provider</div>" + barList(s.by_provider, PROV_LABEL, function (kk) { return PROV_COLOR[kk] || "var(--accent)"; }) + "</div>"
      + "</div>";

    var tables = '<div class="tk-grid" style="margin-top:6px">'
      + '<div><div class="tk-sec">Model ngốn nhất</div>' + table(s.by_model, "Model", function () {
        return '<button class="tk-go" data-goto="models">Đổi model</button>';
      }) + "</div>"
      + '<div><div class="tk-sec">Brain ngốn nhất</div>' + tableProj(s.by_project) + "</div>"
      + "</div>";

    var insHtml = "";
    if (insights && insights.length) {
      insHtml = '<div class="tk-sec">Đề xuất</div><div class="tk-ins">' + insights.map(function (i) {
        var ico = i.level === "warn" ? ic("triangle-alert", { cls: "ic-warn" }) : ic("lightbulb", { cls: "ic-accent" });
        return '<div class="item ' + (i.level === "warn" ? "warn" : "info") + '"><div class="ico">' + ico + '</div>'
          + '<div><div class="t">' + esc(i.title) + '</div><div class="d">' + esc(i.detail) + "</div></div></div>";
      }).join("") + "</div>";
    }

    var note = '<div class="tk-note">Số "Tổng token" gồm cả token đọc-cache, nên rất lớn - phần lớn là đọc lại ngữ cảnh đã có, rẻ hơn token mới nhiều lần, xem ô "Cache đỡ cho". Tiền chia làm hai loại và trang này không trộn chúng: <b>tiền mặt</b> chỉ phát sinh ở nhánh dùng API key, còn với gói thuê bao thì mọi con số tiền chỉ là <b>quy đổi</b> theo bảng giá tham khảo để biết gói có đáng không. Nguồn Claude và Codex dựng từ log thật (có lịch sử); nhánh API chỉ có số từ khi bật ghi log.</div>';

    el.innerHTML = '<div class="tk-wrap">' + mucHtml(state.muc) + bar1 + heroHtml() + act + cards + chart + grid + tables + loopHtml() + engineHtml() + insHtml + note + "</div>";
    // Thông báo đã hiện xong thì thôi. Không xoá ở đây thì câu "Đã chuyển sang mức Tối ưu"
    // bám vào trang qua mọi lần đổi chip kỳ, mọi lần Làm mới, cho tới khi người dùng F5 -
    // và một thông báo nói về việc xảy ra mười phút trước thì chỉ gây hiểu nhầm.
    state.toast = "";
    state.nsToast = "";
    bind();
    bindMuc();
  }

  function bind() {
    var el = state.el; if (!el) return;
    el.querySelectorAll("[data-period]").forEach(function (b) {
      b.onclick = function () { state.period = b.getAttribute("data-period"); load(false); };
    });
    el.querySelectorAll("[data-prov]").forEach(function (b) {
      b.onclick = function () { state.provider = b.getAttribute("data-prov"); load(false); };
    });
    el.querySelectorAll("[data-goto]").forEach(function (b) {
      b.onclick = function () {
        try { Alpine.store("nav").go(b.getAttribute("data-goto")); } catch (e) { /* trang chưa sẵn sàng */ }
      };
    });
    var nsBtns = el.querySelectorAll('[data-act="ns"]');
    nsBtns.forEach(function (b) {
      b.onclick = function () {
        state.moNganSach = !state.moNganSach;
        if (!state.moNganSach) state.nsForm = null;   // đóng form là bỏ luôn số gõ dở
        load(false);
      };
    });
    var luu = el.querySelector('[data-act="ns-luu"]');
    if (luu) luu.onclick = function () {
      luu.disabled = true;
      var fd = new FormData();
      function val(id) { var e = el.querySelector("#" + id); return e ? e.value : ""; }
      function chk(id) { var e = el.querySelector("#" + id); return e && e.checked ? "1" : "0"; }
      // Ô để trống nghĩa là "xoá", nên gửi "0" chứ không gửi chuỗi rỗng: server hiểu rỗng là
      // "giữ nguyên" để lưu một ô không xoá mất ba ô kia.
      fd.append("gia_goi_thang_usd", val("tk-ns-goi") || "0");
      fd.append("ngan_sach_thang_usd", val("tk-ns-tran") || "0");
      fd.append("tran_5h", val("tk-ns-5h") || "0");
      fd.append("tu_phanh", chk("tk-ns-phanh"));
      fd.append("bao_cao_tuan", chk("tk-ns-tuan") === "1" ? "auto" : "off");
      fetch("/usage/ngan-sach", { method: "POST", body: fd })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j || {} }; }); })
        .then(function (res) {
          // Đóng form lại rồi im lặng khi server từ chối là kiểu hỏng tệ nhất: người dùng
          // tưởng đã đặt xong trần tiền, và cái trần đó không tồn tại. Phiên hết hạn trả 401
          // kèm thân JSON nên `r.json()` vẫn resolve - phải soi `r.ok` chứ không soi mỗi body.
          if (!res.ok || res.j.ok === false) {
            state.nsToast = '<div class="tk-muc-toast err">Chưa lưu được: '
              + esc(res.j.error || "máy chủ từ chối. Thử tải lại trang rồi đăng nhập lại.")
              + "</div>";
            luu.disabled = false;
            load(false);
            return;
          }
          // Server trả về những thứ sẽ KHÔNG chạy được như người dùng tưởng (chưa đấu kênh
          // báo, tự phanh đang tắt). Nuốt mất là để họ yên tâm về một cái không chạy.
          var cb = (res.j.canh_bao || []).join(" ");
          state.nsToast = cb ? '<div class="tk-muc-toast">' + esc(cb) + "</div>" : "";
          state.moNganSach = false;
          state.nsForm = null;
          load(false);
        })
        .catch(function (e) {
          state.nsToast = '<div class="tk-muc-toast err">Chưa lưu được: '
            + esc(e && e.message ? e.message : e) + "</div>";
          luu.disabled = false;
          load(false);
        });
    };
    el.querySelectorAll("[data-loop]").forEach(function (b) {
      b.onclick = function () {
        b.disabled = true;
        var fd = new FormData();
        fd.append("slug", b.getAttribute("data-loop"));
        fd.append("brain", b.getAttribute("data-brain"));
        fetch("/loops/toggle", { method: "POST", body: fd })
          .then(function (r) { return r.json(); })
          .then(function () { return loadViec(true); })
          .then(function () { load(false); })
          .catch(function () { b.disabled = false; });
      };
    });
    var rb = el.querySelector('[data-act="refresh"]');
    if (rb) rb.onclick = function () {
      if (state.busy) return; state.busy = true; rb.textContent = "Đang quét...";
      fetch("/usage/refresh", { method: "POST" }).then(function (r) { return r.json(); })
        .then(function () { state.busy = false; load(false); })
        .catch(function () { state.busy = false; load(false); });
    };
  }

  window.JavisUsage = { render: render };
})();
