/* Nút "i" mở lời giải thích (0.175.0).
 *
 * Chủ repo 16/10/2026: tab Cài đặt của trợ lý "nhiều thông tin quá, quá rối, người dùng phải đọc nhiều", muốn ẩn đi và
 * có một nút nhỏ kiểu nút i để mở ra khi cần đọc. Mỗi mục giữ lại thứ cần nhìn và cần bấm (trạng thái, số liệu, ô chọn);
 * câu giải thích nằm trong một khối `.info-body` ẩn ngay dưới tiêu đề, nút `.info-i` cạnh tiêu đề mở hoặc đóng nó.
 *
 * Cách dùng trong một mô-đun vẽ HTML:
 *   tiêu đề: '<div class="...">Tên mục' + JavisInfo.btn(nhãn) + '</div>'
 *   ngay sau (anh em kế tiếp, có thể cách vài phần tử): JavisInfo.body(htmlĐãEscape)
 * Nút tìm khối `.info-body` ĐẦU TIÊN đứng sau phần tử chứa nó (hay sau tầng cha gần nhất có khối đó). Từ 0.399.0 khối đó luôn ẩn:
 * bấm nút là mở một popup cạnh nút (điện thoại: bảng từ dưới lên) với đúng nội dung khối, xem cuối file.
 * Mô-đun nào chạy không có file này (test Node) thì tự vẽ lời giải thích ra luôn, không mất chữ.
 *
 * 0.214.0, owner 2026-10-18: the rule now covers the whole dashboard ("các dòng giải thích gọn lại trong chữ (i) chứ không
 * để xổ hết ra bên ngoài"), written in docs/quy-uoc-dev.md and enforced by tests/python/test_info_tip_rule.py.
 *   JavisInfo.pair(html, label)  button and its hidden block side by side, for a spot with no title to sit next to.
 * In static HTML: <button type="button" class="info-i" aria-expanded="false" data-i18n-aria="info.more" data-i18n-title="info.more"><i data-ic="info"></i></button>
 * followed (as a sibling, or a sibling of a parent up to three levels) by <div class="info-body" hidden>...</div>. */
(function () {
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function btn(label) {
    var icon = typeof window.ic === "function" ? window.ic("info") : "i";
    return '<button type="button" class="info-i" aria-expanded="false" aria-label="' + esc(label) + '" title="' + esc(label) +
      '">' + icon + "</button>";
  }
  function body(html) { return '<div class="info-body" hidden>' + html + "</div>"; }
  // Standing alone, a bare round icon reads as decoration, so the pair's button also shows its label ("Xem giải thích").
  function pair(html, label) {
    var b = btn(label).replace('class="info-i"', 'class="info-i with-text"').replace("</button>", '<span>' + esc(label) + "</span></button>");
    return '<span class="info-pair">' + b + "</span>" + body(html);
  }
  // Nút có thể nằm trong một thẻ con của tiêu đề (span tên mục trong hàng tiêu đề): đi lên tối đa ba tầng, ở mỗi tầng tìm
  // khối giải thích đầu tiên đứng sau.
  function khoiCua(b) {
    for (var own = b.nextElementSibling; own; own = own.nextElementSibling) {
      if (own.classList && own.classList.contains("info-body")) return own;
    }
    for (var up = b.parentElement, n = 0; up && n < 3; up = up.parentElement, n++) {
      for (var el = up.nextElementSibling; el; el = el.nextElementSibling) {
        if (el.classList && el.classList.contains("info-body")) return el;
      }
    }
    return null;
  }
  // 0.399.0 (owner, 2026-10-29): "các nút chấm than này khi click vào phải hiện popup chứ không phải hiện tooltip bên dưới".
  // The explanation opens in ONE popup next to the button (a sheet from the bottom on a phone) instead of unfolding inside
  // the page and pushing everything down. The `.info-body` stays hidden in the page and is only the popup's source, so
  // every module keeps writing btn() + body() as before. Closes with its x, Escape (focus back on the button), a click
  // outside, or when the button leaves the page (a redraw).
  var _pop = null, _bg = null, _from = null;
  function isPhone() { try { return window.matchMedia("(max-width: 600px)").matches; } catch (e) { return false; } }
  function place() {
    if (!_pop || !_from) return;
    if (!document.body.contains(_from)) { close(false); return; }
    if (isPhone()) { _pop.classList.add("sheet"); _pop.style.left = _pop.style.top = ""; return; }
    _pop.classList.remove("sheet");
    var r = _from.getBoundingClientRect(), vw = window.innerWidth, vh = window.innerHeight;
    var w = _pop.offsetWidth, h = _pop.offsetHeight, gap = 8;
    var left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), vw - w - 8);
    var top = r.bottom + gap + h <= vh - 8 ? r.bottom + gap : Math.max(8, r.top - gap - h);
    _pop.style.left = Math.round(left) + "px";
    _pop.style.top = Math.round(top) + "px";
  }
  function close(refocus) {
    if (!_pop) return;
    var b = _from;
    _pop.remove(); if (_bg) _bg.remove();
    _pop = _bg = _from = null;
    if (b) { b.setAttribute("aria-expanded", "false"); b.classList.remove("on"); if (refocus && document.body.contains(b)) b.focus(); }
  }
  function open(b, k) {
    close(false);
    _from = b;
    var label = b.getAttribute("aria-label") || "";
    _bg = document.createElement("div");
    _bg.className = "info-pop-bg";
    _bg.addEventListener("click", function () { close(true); });
    _pop = document.createElement("div");
    _pop.className = "info-pop";
    _pop.setAttribute("role", "dialog");
    _pop.setAttribute("aria-label", label);
    _pop.tabIndex = -1;
    var x = typeof window.ic === "function" ? window.ic("x") : "x";
    _pop.innerHTML = '<button type="button" class="info-pop-x" aria-label="' + esc(window.t ? window.t("common.close") : "Close") + '">' + x +
      '</button><div class="info-pop-c">' + k.innerHTML + "</div>";
    _pop.querySelector(".info-pop-x").addEventListener("click", function () { close(true); });
    document.body.appendChild(_bg);
    document.body.appendChild(_pop);
    b.setAttribute("aria-expanded", "true");
    b.classList.add("on");
    place();
    try { _pop.focus({ preventScroll: true }); } catch (e) { _pop.focus(); }
  }
  if (typeof document !== "undefined") {
    document.addEventListener("click", function (ev) {
      var b = ev.target && ev.target.closest && ev.target.closest("button.info-i");
      if (!b) {
        // A click outside the popup closes it (the backdrop handles phones; this is the computer, which has none).
        if (_pop && !(ev.target && ev.target.closest && ev.target.closest(".info-pop"))) close(false);
        return;
      }
      var k = khoiCua(b);
      if (!k) return;
      ev.preventDefault();
      ev.stopPropagation();
      if (_pop && _from === b) { close(false); return; }
      open(b, k);
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && _pop) { ev.stopPropagation(); close(true); }
    }, true);
    window.addEventListener("resize", place);
    // Any scroll (the page or a panel inside it) moves the button: follow it, or close when it left the page.
    document.addEventListener("scroll", place, true);
  }
  window.JavisInfo = { btn: btn, body: body, pair: pair, close: close };
})();
