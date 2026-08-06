/* usage.js - Dashboard Token (nâng cấp trang "Mức dùng").
 * Đọc /usage/summary + /usage/insights (index log thô Claude + Codex + nhánh API).
 * Lọc theo kỳ (8 lựa chọn) và theo provider. Vẽ SVG/div thuần, không thêm thư viện.
 * Xuất window.JavisUsage.render(el); console.js renderUsage() ủy quyền sang đây.
 */
(function () {
  "use strict";

  var PERIODS = [
    ["today", "Hôm nay"], ["yesterday", "Hôm qua"],
    ["this_week", "Tuần này"], ["last_week", "Tuần trước"],
    ["this_month", "Tháng này"], ["last_month", "Tháng trước"],
    ["last_3_months", "3 tháng"], ["this_year", "Năm nay"],
  ];
  var PROVS = [["", "Tất cả"], ["claude", "Claude Code"], ["codex", "ChatGPT"], ["api", "API"]];
  var PROV_LABEL = { claude: "Claude Code", codex: "ChatGPT/Codex", api: "API (OpenRouter...)" };
  var SRC_LABEL = { manual: "Bạn gõ tay", javis: "Javis (tự chạy)" };
  var ACT_LABEL = { chat: "Chat", background: "Nền (loop/lịch)", subagent: "Subagent", manual: "Thủ công" };
  var PROV_COLOR = { claude: "var(--accent)", codex: "var(--green)", api: "var(--link-ink)" };

  var state = { period: "this_month", provider: "", el: null, busy: false, muc: null, toast: "" };

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
  function fCost(c) { c = +c || 0; return "$" + (c >= 100 ? c.toFixed(0) : c.toFixed(2)); }
  function model(m) { return String(m || "").split("/").pop().replace(/^(claude-|gpt-)/, "").slice(0, 26); }

  var _css = false;
  function injectCss() {
    if (_css) return; _css = true;
    var css = ""
      + ".tk-wrap{max-width:960px}"
      + ".tk-bar1{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:16px}"
      + ".tk-chips{display:flex;gap:6px;flex-wrap:wrap}"
      + ".tk-chip{padding:6px 12px;border-radius:20px;border:1px solid var(--glass-brd);background:var(--glass);color:var(--text2);font-size:13px;cursor:pointer;transition:.12s;white-space:nowrap}"
      + ".tk-chip:hover{color:var(--text)}"
      + ".tk-chip.on{background:var(--accent-solid);border-color:var(--accent-solid);color:var(--on-accent);font-weight:600}"
      + ".tk-seg{display:flex;border:1px solid var(--glass-brd);border-radius:9px;overflow:hidden}"
      + ".tk-seg button{padding:6px 12px;background:transparent;border:0;color:var(--text2);font-size:12.5px;cursor:pointer}"
      + ".tk-seg button.on{background:var(--glass);color:var(--text);font-weight:600}"
      + ".tk-refresh{margin-left:auto;padding:6px 13px;border-radius:9px;border:1px solid var(--glass-brd);background:var(--glass);color:var(--text2);font-size:13px;cursor:pointer}"
      + ".tk-refresh:hover{color:var(--text)}"
      + ".tk-cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:22px}"
      + ".tk-card{flex:1 1 140px;background:var(--glass);border:1px solid var(--glass-brd);border-radius:12px;padding:13px 15px}"
      + ".tk-card .k{font-size:11.5px;color:var(--text3);letter-spacing:.3px;text-transform:uppercase}"
      + ".tk-card .v{font-size:22px;font-weight:700;color:var(--text);margin-top:5px;font-variant-numeric:tabular-nums}"
      + ".tk-card .s{font-size:12px;color:var(--text2);margin-top:3px}"
      + ".tk-card.accent .v{color:var(--accent)}"
      + ".tk-up{color:var(--red)}.tk-down{color:var(--green)}"
      + ".tk-sec{font-size:11.5px;color:var(--text3);text-transform:uppercase;letter-spacing:1px;margin:22px 0 12px;font-weight:600}"
      + ".tk-chart{display:flex;align-items:flex-end;gap:3px;height:150px;padding:6px 2px 0;overflow-x:auto}"
      + ".tk-col{flex:0 0 auto;width:9px;display:flex;flex-direction:column-reverse;align-items:stretch;height:100%;cursor:default}"
      + ".tk-seg2{width:100%;min-height:0}"
      + ".tk-xrow{display:flex;gap:3px;border-top:1px solid var(--glass-brd);padding-top:5px;overflow-x:auto}"
      + ".tk-x{flex:0 0 auto;width:9px;text-align:center;font-size:8px;color:var(--text3)}"
      + ".tk-legend{display:flex;gap:14px;font-size:12px;color:var(--text2);margin-top:9px}"
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
      + ".tk-ins{margin-top:8px}"
      + ".tk-ins .item{display:flex;gap:10px;padding:11px 13px;border:1px solid var(--glass-brd);border-radius:10px;background:var(--glass);margin-bottom:9px}"
      + ".tk-ins .item.warn{border-left:3px solid var(--red)}"
      + ".tk-ins .item.info{border-left:3px solid var(--link-ink)}"
      + ".tk-ins .ico{font-size:16px;flex:0 0 auto}"
      + ".tk-ins .t{font-weight:600;color:var(--text);font-size:13.5px}"
      + ".tk-ins .d{color:var(--text2);font-size:12.5px;margin-top:2px;line-height:1.5}"
      + ".tk-note{margin-top:22px;font-size:12px;color:var(--text3);line-height:1.55;max-width:720px}"
      // Khối chọn mức tiết kiệm, đặt ở ĐẦU trang. Trước 0.24.7 nó là một trang riêng trong
      // rail; gộp vào đây vì "tôi tiêu bao nhiêu" và "tôi muốn tiêu ít đi" là cùng một câu
      // hỏi, tách hai chỗ thì người dùng thấy con số mà không thấy cái nút.
      + ".tk-muc{margin-bottom:22px}"
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

  function load(doRefresh) {
    var q = "?period=" + encodeURIComponent(state.period)
      + (state.provider ? "&provider=" + state.provider : "")
      + "&refresh=" + (doRefresh ? 1 : 0);
    Promise.all([
      fetch("/usage/summary" + q).then(function (r) { return r.json(); }),
      fetch("/usage/insights?period=" + encodeURIComponent(state.period)).then(function (r) { return r.json(); }).catch(function () { return { items: [] }; }),
      fetch("/usage").then(function (r) { return r.json(); }).catch(function () { return {}; }),
      loadMuc(false),
    ]).then(function (res) {
      paint(res[0] || {}, (res[1] || {}).items || [], res[2] || {});
    }).catch(function () {
      if (state.el) state.el.innerHTML = '<div class="tk-wrap"><div class="cview-placeholder"><div class="ph-ico">' + ic("chart-column", { cls: "ic-xl ic-dim" }) + '</div><div>Không tải được số liệu token.</div></div></div>';
    });
  }

  // ===== Mức tiết kiệm token =====
  // Khối này đứng ĐẦU trang Mức dùng, trước cả bộ lọc kỳ. Lý do: mọi con số bên dưới trả
  // lời "tôi đã tiêu bao nhiêu", còn đây là chỗ duy nhất trả lời "làm sao tiêu ít đi". Để
  // nó ở cuối trang, hay ở một trang riêng như trước, là bắt người dùng đọc hết hoá đơn rồi
  // mới tình cờ thấy cái công tắc.
  //
  // Chỉ vẽ những gì người dùng cuối quyết định được: tên mức, tiết kiệm bao nhiêu, và số đo
  // thật. Mọi thứ còn lại của trang chẩn đoán cũ (allocation tính bằng phần vạn, tên đường
  // canary, cửa sổ token 60 giây, execution_path từng lượt) là ngôn ngữ của người vận hành
  // máy, không phải của người đang trả tiền token.
  function mucHtml(d) {
    if (!d || !(d.danh_sach || []).length) return "";
    var uocMuc = ((d.uoc_tinh || {}).muc) || {};
    var dod = d.do_duoc || {};
    var btns = d.danh_sach.map(function (p) {
      var m = uocMuc[p.id] || {};
      var pct = (p.id !== "off" && m.phan_tram)
        ? '<span class="tk-muc-pct">-' + (+m.phan_tram || 0) + "% token</span>" : "";
      var tok = m.token_moi_request != null
        ? '<span class="tk-muc-tok">' + (+m.token_moi_request || 0).toLocaleString("vi-VN") + " token mỗi lượt</span>" : "";
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
      doHtml = '<div class="tk-muc-do">'
        + '<div><div class="k">Chế độ Đầy đủ</div><div class="v">' + fTok(dod.tb_cu) + '</div><div class="s">token mỗi lượt, ' + (dod.so_luot_cu || 0) + " lượt</div></div>"
        + '<div><div class="k">Khi tiết kiệm</div><div class="v">' + fTok(dod.tb_moi) + '</div><div class="s">token mỗi lượt, ' + (dod.so_luot_moi || 0) + " lượt</div></div>"
        + '<div class="pct"><div class="k">Giảm được</div><div class="v">' + (dod.phan_tram || 0) + '%</div><div class="s">số thật đo trong 24 giờ qua</div></div>'
        + "</div>";
    }

    var chuaChon = d.tu_chon ? "" : " Mức đang chạy là mặc định của bản này, bạn chưa tự chọn bao giờ."
      + " Bấm một mức bất kỳ là Javis ghim lại, từ đó không bản cập nhật nào đổi nữa.";
    return '<div class="tk-muc"><div class="tk-sec">Chế độ tiết kiệm token</div>'
      + '<div class="tk-muc-list">' + btns + "</div>"
      + (state.toast ? state.toast : "")
      + doHtml
      + '<div class="tk-muc-note">Đổi xong có hiệu lực ngay, không cần khởi động lại. Thấy Javis'
      + " trả lời tệ đi thì bấm <b>Tắt</b> là quay lại như cũ lập tức."
      + " Con số phần trăm là ước lượng đo trên chính bộ não và bộ nhớ của bạn."
      + esc(chuaChon) + "</div></div>";
  }

  function bindMuc() {
    var el = state.el; if (!el) return;
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

  function table(items, header) {
    if (!items || !items.length) return '<div style="color:var(--text3);font-size:13px">Chưa có dữ liệu.</div>';
    var rows = items.slice(0, 8).map(function (x) {
      return "<tr><td>" + esc(model(x.key) || x.key) + '</td><td class="num">' + fTok(x.tokens)
        + '</td><td class="num">' + (x.cost > 0 ? fCost(x.cost) : "-") + "</td></tr>";
    }).join("");
    return '<table class="tk-tbl"><thead><tr><th>' + esc(header) + '</th><th style="text-align:right">Token</th><th style="text-align:right">Quy đổi</th></tr></thead><tbody>' + rows + "</tbody></table>";
  }

  function paint(s, insights, extra) {
    var el = state.el; if (!el) return;
    var k = s.kpi || {};
    var chips = PERIODS.map(function (p) {
      return '<button class="tk-chip' + (p[0] === state.period ? " on" : "") + '" data-period="' + p[0] + '">' + esc(p[1]) + "</button>";
    }).join("");
    var seg = PROVS.map(function (p) {
      return '<button class="' + (p[0] === state.provider ? "on" : "") + '" data-prov="' + p[0] + '">' + esc(p[1]) + "</button>";
    }).join("");
    var bar1 = '<div class="tk-bar1"><div class="tk-chips">' + chips + '</div>'
      + '<div class="tk-seg">' + seg + '</div>'
      + '<button class="tk-refresh" data-act="refresh">' + (state.busy ? "Đang quét..." : "↻ Làm mới") + "</button></div>";

    // delta
    var deltaHtml = "";
    if (k.delta_pct != null) {
      var up = k.delta_pct >= 0;
      deltaHtml = '<span class="' + (up ? "tk-up" : "tk-down") + '">' + (up ? "▲" : "▼") + " " + Math.abs(k.delta_pct) + "%</span> vs kỳ trước";
    } else { deltaHtml = "kỳ trước chưa có số"; }

    var orb = (extra && extra.openrouter && extra.openrouter.remaining != null)
      ? card("OpenRouter còn", '<span style="color:var(--green)">' + fCost(extra.openrouter.remaining) + "</span>", "tiền thật đã dùng " + fCost(extra.openrouter.used || 0)) : "";

    var cards = '<div class="tk-cards">'
      + card("Tổng token", fTok(k.tokens), deltaHtml, true)
      + card("Token/ngày", fTok(k.per_day_avg), "trung bình trong kỳ")
      + card("Cache hit", Math.round((k.cache_hit || 0) * 100) + "%", "tái dùng ngữ cảnh (cao = rẻ)")
      + card("Phiên", (k.sessions || 0), "tb " + fTok(k.avg_per_session) + "/phiên")
      + card("Chi phí quy đổi", fCost(k.cost_est), "nếu tính giá API")
      + orb
      + "</div>";

    // timeseries stacked
    var ts = s.timeseries || [];
    var maxD = Math.max.apply(null, ts.map(function (d) { return d.total; })) || 1;
    var cols = ts.map(function (d) {
      function seg2(v, col) { return v > 0 ? '<div class="tk-seg2" style="height:' + (v / maxD * 100) + "%;background:" + col + '"></div>' : ""; }
      var tip = d.day + ": " + fTok(d.total) + " token";
      return '<div class="tk-col" title="' + esc(tip) + '">'
        + seg2(d.claude, PROV_COLOR.claude) + seg2(d.codex, PROV_COLOR.codex) + seg2(d.api, PROV_COLOR.api) + "</div>";
    }).join("");
    var xs = ts.map(function (d) { return '<div class="tk-x">' + esc(d.day.slice(8)) + "</div>"; }).join("");
    var legend = '<div class="tk-legend">'
      + '<span><span class="tk-dot" style="background:' + PROV_COLOR.claude + '"></span>Claude</span>'
      + '<span><span class="tk-dot" style="background:' + PROV_COLOR.codex + '"></span>ChatGPT</span>'
      + '<span><span class="tk-dot" style="background:' + PROV_COLOR.api + '"></span>API</span></div>';
    var chart = ts.length ? ('<div class="tk-sec">Token theo ngày</div><div class="tk-chart">' + cols + '</div><div class="tk-xrow">' + xs + "</div>" + legend) : "";

    // breakdowns
    var grid = '<div class="tk-grid">'
      + "<div><div class=\"tk-sec\">Nguồn tiêu (bạn vs Javis)</div>" + barList(s.by_source, SRC_LABEL, function () { return "var(--accent)"; })
      + "<div class=\"tk-sec\">Hoạt động</div>" + barList(s.by_activity, ACT_LABEL, function () { return "var(--link-ink)"; }) + "</div>"
      + "<div><div class=\"tk-sec\">Provider</div>" + barList(s.by_provider, PROV_LABEL, function (kk) { return PROV_COLOR[kk] || "var(--accent)"; }) + "</div>"
      + "</div>";

    var tables = '<div class="tk-grid" style="margin-top:6px">'
      + '<div><div class="tk-sec">Model ngốn nhất</div>' + table(s.by_model, "Model") + "</div>"
      + '<div><div class="tk-sec">Dự án ngốn nhất</div>' + tableProj(s.by_project) + "</div>"
      + "</div>";

    // insights
    var insHtml = "";
    if (insights && insights.length) {
      insHtml = '<div class="tk-sec">Đề xuất</div><div class="tk-ins">' + insights.map(function (i) {
        var ico = i.level === "warn" ? ic("triangle-alert", { cls: "ic-warn" }) : ic("lightbulb", { cls: "ic-accent" });
        return '<div class="item ' + (i.level === "warn" ? "warn" : "info") + '"><div class="ico">' + ico + '</div>'
          + '<div><div class="t">' + esc(i.title) + '</div><div class="d">' + esc(i.detail) + "</div></div></div>";
      }).join("") + "</div>";
    }

    var note = '<div class="tk-note">Số "Tổng token" gồm cả token đọc-cache (cache_read), nên rất lớn - cache hit cao nghĩa là phần lớn là đọc lại ngữ cảnh (rẻ), xem cột Cache hit. Chi phí là QUY ĐỔI theo giá API để tham khảo: với gói thuê bao Claude/ChatGPT đây không phải tiền thật, chỉ OpenRouter mới là tiền thật. Nguồn Claude và Codex dựng từ log thật (có lịch sử); nhánh API chỉ có số từ khi bật ghi log.</div>';

    el.innerHTML = '<div class="tk-wrap">' + mucHtml(state.muc) + bar1 + cards + chart + grid + tables + insHtml + note + "</div>";
    bind();
    bindMuc();
  }

  function tableProj(items) {
    if (!items || !items.length) return '<div style="color:var(--text3);font-size:13px">Chưa có dữ liệu.</div>';
    var rows = items.slice(0, 8).map(function (x) {
      return "<tr><td>" + esc(x.key) + '</td><td class="num">' + fTok(x.tokens) + '</td><td class="num">' + (x.sessions || 0) + "</td></tr>";
    }).join("");
    return '<table class="tk-tbl"><thead><tr><th>Dự án</th><th style="text-align:right">Token</th><th style="text-align:right">Phiên</th></tr></thead><tbody>' + rows + "</tbody></table>";
  }

  function bind() {
    var el = state.el; if (!el) return;
    el.querySelectorAll("[data-period]").forEach(function (b) {
      b.onclick = function () { state.period = b.getAttribute("data-period"); load(false); };
    });
    el.querySelectorAll("[data-prov]").forEach(function (b) {
      b.onclick = function () { state.provider = b.getAttribute("data-prov"); load(false); };
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
