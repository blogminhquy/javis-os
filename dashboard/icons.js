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

  // ---- Icon RIÊNG của Javis (không có trong Lucide) ----------------------------------
  // "javis-pet" là chính khuôn mặt linh vật: thân tròn cam, vành quỹ đạo mảnh, và đôi mắt
  // LIẾC chéo lên phải - đúng dáng của con pet ở mép màn hình và của dấu ấn trên thanh bên.
  // Trước đây trang Linh vật mượn mặt cười chung của Lucide, nên cái tab dẫn tới con pet lại
  // là thứ duy nhất trong app không giống con pet.
  //
  // Vẽ được bên trong khuôn ic() (fill="none" stroke="currentColor") vì mỗi hình con tự khai
  // fill/stroke của nó, và thuộc tính trên con luôn thắng giá trị thừa kế từ cha.
  // Toạ độ quy từ bản gốc 320x320 của pet.js (thân bán kính 78, mắt lệch +16/-12) về khung
  // 24x24, nên đổi dáng liếc bên đó thì đổi cả ở đây.
  var RIENG = {
    "javis-pet":
      '<circle cx="12" cy="12" r="11" fill="none" stroke="#F28C28" stroke-width="1.3" opacity=".55"/>' +
      '<circle cx="12" cy="12" r="8.2" fill="#F28C28" stroke="none"/>' +
      '<ellipse cx="12.1" cy="10.74" rx=".76" ry="1.84" fill="#201E1E" stroke="none"/>' +
      '<ellipse cx="15.26" cy="10.74" rx=".76" ry="1.84" fill="#201E1E" stroke="none"/>',
  };
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
    if (RIENG[name]) return RIENG[name];
    if (RAW[name]) return RAW[name];
    if (!missing[name]) {
      missing[name] = true;
      console.warn(
        "[icons] Missing icon '" + name + "'. Add the name to " +
        "dashboard/icons.manifest.json, then run: python tools/gen_icons.py"
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
    return !!(RAW[name] || RIENG[name]);
  }

  // ---- Dấu hiệu KÊNH nhắn tin (Telegram, Zalo) --------------------------------------
  //
  // Vì sao không dùng ic() như mọi icon khác: bộ Lucide vẽ bằng nét, một màu, tự đổi theo
  // màu chữ - đúng cho icon chức năng, và SAI cho dấu hiệu nhận biết nền tảng. Hai con bot
  // nằm cạnh nhau trong cùng một lưới thẻ mà chỉ khác nhau ở một chữ nhỏ thì người ta sẽ
  // bấm nhầm; MÀU mới là thứ mắt bắt được trước khi kịp đọc. Nên đây là hình khối đặc, giữ
  // đúng màu thương hiệu ở cả nền sáng lẫn nền tối.
  //
  // Vẽ tay theo mô tả của chủ repo (2026-08-08): Telegram là máy bay giấy TRẮNG trên nền
  // XANH DƯƠNG; Zalo là chữ Z trên nền xanh dương, bọc trong khung bong bóng trò chuyện.
  // Vẽ tay chứ không nhúng ảnh: SVG nội tuyến thì nét ở mọi độ phân giải, không thêm tệp
  // nhị phân vào repo, và không phải một lời gọi mạng nữa lúc vẽ lưới thẻ.
  var KENH = {
    telegram: {
      nhan: "Telegram",
      mau: "#229ED9",
      than:
        '<rect width="24" height="24" rx="7" fill="#229ED9"/>' +
        '<path fill="#fff" d="M18.75 5.6 4.6 11.25c-.62.25-.6.72.02.9l3.5 1.05 1.35 4.1c' +
        '.17.5.5.58.87.2l1.9-1.85 3.55 2.62c.42.31.86.14.97-.4L19.6 6.2c.11-.55-.24-.8-.85-.6z"/>' +
        '<path fill="#c8e6f7" d="M9.55 13.75 16.5 8.3c.3-.24.6.1.35.4l-5.55 6.2-.12 2.55z"/>',
    },
    zalo: {
      nhan: "Zalo",
      mau: "#0068FF",
      than:
        '<path fill="#0068FF" d="M12 2.6c-5.35 0-9.4 3.5-9.4 7.9 0 2.6 1.4 4.9 3.62 6.35' +
        '-.16 1.2-.78 2.28-1.55 3.05-.33.33-.1.87.36.8 2-.28 3.46-1 4.4-1.63.8.17 1.66.26 2.57.26' +
        ' 5.35 0 9.4-3.5 9.4-7.9S17.35 2.6 12 2.6z"/>' +
        '<path fill="#fff" d="M8.5 7.9h7.05v1.6l-4.7 4.75h4.8v1.7H8.3v-1.6l4.7-4.75H8.5z"/>',
    },
    // Slack (0.71.0): the four-colour pinwheel, drawn as four rounded bars.
    slack: {
      nhan: "Slack",
      mau: "#4A154B",
      than:
        '<rect x="8" y="3" width="3.2" height="9" rx="1.6" fill="#36C5F0"/>' +
        '<rect x="12" y="8" width="9" height="3.2" rx="1.6" fill="#2EB67D"/>' +
        '<rect x="12.8" y="12" width="3.2" height="9" rx="1.6" fill="#ECB22E"/>' +
        '<rect x="3" y="12.8" width="9" height="3.2" rx="1.6" fill="#E01E5A"/>',
    },
    // WhatsApp (0.71.0): green speech bubble with the handset.
    whatsapp: {
      nhan: "WhatsApp",
      mau: "#25D366",
      than:
        '<path fill="#25D366" d="M12 2.5a9.5 9.5 0 0 0-8.2 14.3L2.5 21.5l4.8-1.26A9.5 9.5 0 1 0 12 2.5z"/>' +
        '<path fill="#fff" d="M8.9 7.2c-.2-.45-.42-.46-.62-.47h-.53c-.18 0-.48.07-.73.34-.25.27-.96.94' +
        '-.96 2.29s.98 2.66 1.12 2.84c.14.18 1.9 3.03 4.68 4.13 2.31.91 2.78.73 3.28.68.5-.05 1.62-.66' +
        ' 1.85-1.3.23-.64.23-1.19.16-1.3-.07-.12-.25-.18-.53-.32-.27-.14-1.62-.8-1.87-.89-.25-.09-.43' +
        '-.14-.62.14-.18.27-.71.89-.87 1.07-.16.18-.32.21-.6.07-.27-.14-1.15-.42-2.19-1.35-.81-.72' +
        '-1.36-1.62-1.52-1.89-.16-.27-.02-.42.12-.56.12-.12.27-.32.41-.48.14-.16.18-.27.27-.46.09' +
        '-.18.05-.34-.02-.48-.07-.14-.6-1.5-.84-2.04z"/>',
    },
  };

  // kenh(id, opts) -> chuỗi SVG dấu hiệu nền tảng. opts.size (mặc định 1.15em), opts.cls.
  // Tên kênh lạ thì trả rỗng, KHÔNG vẽ dấu hỏi: chỗ gọi luôn đứng cạnh chữ nói rõ kênh nào,
  // nên một ô trống đọc nhẹ hơn một ký hiệu sai.
  function kenh(id, opts) {
    var k = KENH[String(id || "").toLowerCase()];
    if (!k) return "";
    var o = opts || {};
    var size = o.size || "1.15em";
    return '<svg class="kenh-logo ' + esc(o.cls || "") + '" viewBox="0 0 24 24" width="' +
      esc(size) + '" height="' + esc(size) + '" role="img" aria-label="' + esc(k.nhan) +
      '" focusable="false">' + k.than + "</svg>";
  }

  function kenhNhan(id) {
    var k = KENH[String(id || "").toLowerCase()];
    return k ? k.nhan : "";
  }

  function kenhMau(id) {
    var k = KENH[String(id || "").toLowerCase()];
    return k ? k.mau : "";
  }

  window.ic = ic;
  window.Icons = {
    ic: ic,
    kenh: kenh,
    kenhNhan: kenhNhan,
    kenhMau: kenhMau,
    kenhDS: function () { return Object.keys(KENH); },
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
