// Tầng icon của dashboard - bọc quanh bộ Lucide đã vendor sẵn.
//
// Vì sao có file này: dashboard dựng HTML bằng template string khắp nơi
// (innerHTML = `...`), nên thứ cần nhất là một hàm TRẢ VỀ CHUỖI SVG để nhét
// thẳng vào chuỗi HTML. Bộ Lucide chính thức thì làm theo hướng quét DOM tìm
// thuộc tính data-lucide - không dùng được ở đây vì dashboard render lại liên
// tục, quét lại sau mỗi lần đổi innerHTML vừa chậm vừa dễ sót icon.
//
// Ba lối dùng:
//   1. Trong template string:  `<button>${ic("save")} Lưu</button>`
//   2. Trong HTML tĩnh:        <i data-ic="save"></i>   (Icons.render() thay hộ)
//   3. Chuỗi trạng thái:       el.innerHTML = Icons.msg("triangle-alert", err)
//
// Lối 3 QUAN TRỌNG về bảo mật: rất nhiều chỗ trước đây là
// el.textContent = "canh bao " + r.error. Đổi sang icon buộc phải dùng
// innerHTML, mà r.error là chuỗi từ server - nối thẳng là mở lỗ XSS.
// Icons.msg() tự escape phần chữ nên chặn hẳn rủi ro đó.
//
// Icon vẽ bằng stroke="currentColor" nên TỰ ĐỔI MÀU theo tông SÁNG/TỐI và theo
// màu chữ của chỗ nó đứng - việc emoji không bao giờ làm được.
(function () {
  "use strict";

  var RAW = window.LucideIcons || {};
  var FALLBACK = "circle-help";
  var missing = Object.create(null);
  var cache = Object.create(null);

  function esc(s) {
    return (s == null ? "" : String(s))
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Icon thiếu là icon VÔ HÌNH - lỗi rất khó thấy bằng mắt. Nên báo to ra
  // console và vẽ dấu hỏi thay chỗ để lộ ra ngay khi nhìn.
  function bodyOf(name) {
    if (RAW[name]) return RAW[name];
    if (!missing[name]) {
      missing[name] = true;
      console.warn(
        "[icons] Thiếu icon '" + name + "'. Thêm tên vào " +
        "dashboard/icons.manifest.json rồi chạy: python tools/gen_icons.py"
      );
    }
    return RAW[FALLBACK] || "";
  }

  // ic(name, opts) -> chuỗi SVG.
  //   opts.cls   thêm class (vd "ic-fill", "ic-lg", "ic-warn")
  //   opts.size  cỡ cụ thể dạng CSS (vd "18px"); bỏ trống thì icon theo cỡ chữ
  //   opts.title chú thích cho trình đọc màn hình; có title thì icon KHÔNG còn
  //              bị ẩn khỏi trình đọc nữa
  function ic(name, opts) {
    var o = opts || {};
    var key = name + "|" + (o.cls || "") + "|" + (o.size || "") + "|" + (o.title || "");
    if (cache[key]) return cache[key];

    var cls = "ic" + (o.cls ? " " + o.cls : "");
    var attrs =
      'class="' + esc(cls) + '"' +
      ' width="1em" height="1em" viewBox="0 0 24 24"' +
      ' fill="none" stroke="currentColor" stroke-width="2"' +
      ' stroke-linecap="round" stroke-linejoin="round"';
    if (o.size) attrs += ' style="width:' + esc(o.size) + ';height:' + esc(o.size) + '"';

    var inner = bodyOf(name);
    if (o.title) {
      attrs += ' role="img"';
      inner = "<title>" + esc(o.title) + "</title>" + inner;
    } else {
      attrs += ' aria-hidden="true" focusable="false"';
    }

    var out = "<svg " + attrs + ">" + inner + "</svg>";
    cache[key] = out;
    return out;
  }

  // msg(name, text) -> HTML an toàn: icon + chữ ĐÃ escape.
  // Dùng cho mọi chỗ hiện thông báo trạng thái có chuỗi từ server.
  function msg(name, text, opts) {
    return ic(name, opts) + " " + esc(text);
  }

  // Hai lối tắt cho hai chuỗi trạng thái dùng nhiều nhất trong dashboard.
  // CẢNH BÁO: chỉ dùng khi chữ CHƯA escape. Chỗ nào đã gọi esc() rồi thì tự
  // ghép ic() + chữ, kẻo escape hai lần và user thấy "&amp;lt;" trên màn hình.
  function warn(text) { return msg("triangle-alert", text, { cls: "ic-warn" }); }
  function okMsg(text) { return msg("circle-check", text, { cls: "ic-ok" }); }

  // Thay <i data-ic="save"></i> trong HTML tĩnh thành SVG thật.
  // Giữ lại class có sẵn trên thẻ gốc để CSS đang nhắm vào nó vẫn ăn.
  function render(root) {
    var scope = root || document;
    var nodes = scope.querySelectorAll ? scope.querySelectorAll("[data-ic]") : [];
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var name = el.getAttribute("data-ic");
      if (!name) continue;
      var keep = el.getAttribute("class") || "";
      var tmp = document.createElement("span");
      tmp.innerHTML = ic(name, {
        cls: keep,
        size: el.getAttribute("data-ic-size") || "",
        title: el.getAttribute("data-ic-title") || "",
      });
      var svg = tmp.firstElementChild;
      if (!svg) continue;
      if (el.id) svg.id = el.id;
      if (el.parentNode) el.parentNode.replaceChild(svg, el);
    }
  }

  function has(name) {
    return !!RAW[name];
  }

  window.ic = ic;
  window.Icons = {
    ic: ic,
    msg: msg,
    warn: warn,
    ok: okMsg,
    render: render,
    has: has,
    esc: esc,
    missing: function () { return Object.keys(missing); },
    count: function () { return Object.keys(RAW).length; },
    // Tên MỌI icon đang có, đã sắp. Dùng cho chỗ để NGƯỜI DÙNG tự chọn icon (bộ chọn icon
    // của hội thoại và project). Không đọc thẳng window.LucideIcons ở nơi khác: cả file này
    // sinh ra để làm tầng duy nhất đứng giữa dashboard và bộ icon đã vendor.
    names: function () { return Object.keys(RAW).sort(); },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { render(); });
  } else {
    render();
  }
})();
