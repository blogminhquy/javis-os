/* Nút "i" mở lời giải thích (0.175.0).
 *
 * Chủ repo 16/10/2026: tab Cài đặt của trợ lý "nhiều thông tin quá, quá rối, người dùng phải đọc nhiều", muốn ẩn đi và
 * có một nút nhỏ kiểu nút i để mở ra khi cần đọc. Mỗi mục giữ lại thứ cần nhìn và cần bấm (trạng thái, số liệu, ô chọn);
 * câu giải thích nằm trong một khối `.info-body` ẩn ngay dưới tiêu đề, nút `.info-i` cạnh tiêu đề mở hoặc đóng nó.
 *
 * Cách dùng trong một mô-đun vẽ HTML:
 *   tiêu đề: '<div class="...">Tên mục' + JavisInfo.btn(nhãn) + '</div>'
 *   ngay sau (anh em kế tiếp, có thể cách vài phần tử): JavisInfo.body(htmlĐãEscape)
 * Nút tìm khối `.info-body` ĐẦU TIÊN đứng sau phần tử chứa nó (hay sau tầng cha gần nhất có khối đó). Vẽ lại là đóng lại, đúng ý: giải thích là thứ đọc một lần.
 * Mô-đun nào chạy không có file này (test Node) thì tự vẽ lời giải thích ra luôn, không mất chữ. */
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
  // Nút có thể nằm trong một thẻ con của tiêu đề (span tên mục trong hàng tiêu đề): đi lên tối đa ba tầng, ở mỗi tầng tìm
  // khối giải thích đầu tiên đứng sau.
  function khoiCua(b) {
    for (var up = b.parentElement, n = 0; up && n < 3; up = up.parentElement, n++) {
      for (var el = up.nextElementSibling; el; el = el.nextElementSibling) {
        if (el.classList && el.classList.contains("info-body")) return el;
      }
    }
    return null;
  }
  if (typeof document !== "undefined") {
    document.addEventListener("click", function (ev) {
      var b = ev.target && ev.target.closest && ev.target.closest("button.info-i");
      if (!b) return;
      var k = khoiCua(b);
      if (!k) return;
      ev.preventDefault();
      ev.stopPropagation();
      var mo = k.hidden;
      k.hidden = !mo;
      b.setAttribute("aria-expanded", mo ? "true" : "false");
      b.classList.toggle("on", mo);
    });
  }
  window.JavisInfo = { btn: btn, body: body };
})();
