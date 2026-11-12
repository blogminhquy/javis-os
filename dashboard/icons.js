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
    // "neural-net" (2026-11-05, owner picked it from a side-by-side sheet): a 2-3-2 neural network for the home page
    // ("Mạng nơ-ron"). Lucide has no such icon. Lines stop at each node's edge, so the nodes stay hollow and crisp
    // at 19px on any background; thinner lines than the nodes keep the eye on the nodes.
    "neural-net":
      '<path d="M6.1 6.34L9.9 5.16M5.87 8.17L10.13 10.83M5.19 8.85L10.81 17.65M5.19 15.15L10.81 6.35M5.87 15.83L10.13 13.17M6.1 17.66L9.9 18.84M14.1 5.16L17.9 6.34M13.19 6.35L18.81 15.15M13.87 10.83L18.13 8.17M13.87 13.17L18.13 15.83M13.19 17.65L18.81 8.85M14.1 18.84L17.9 17.66" stroke-width="1.3"/>' +
      '<circle cx="4" cy="7" r="2.2" stroke-width="1.9"/><circle cx="4" cy="17" r="2.2" stroke-width="1.9"/><circle cx="12" cy="4.5" r="2.2" stroke-width="1.9"/><circle cx="12" cy="12" r="2.2" stroke-width="1.9"/><circle cx="12" cy="19.5" r="2.2" stroke-width="1.9"/><circle cx="20" cy="7" r="2.2" stroke-width="1.9"/><circle cx="20" cy="17" r="2.2" stroke-width="1.9"/>',
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
    // WeChat: two green speech bubbles, the large one behind and the small one in front, each with two eyes.
    wechat: {
      nhan: "WeChat",
      mau: "#07C160",
      than:
        '<path fill="#07C160" d="M9.2 3.6c-3.9 0-7 2.6-7 5.9 0 1.9 1.05 3.55 2.7 4.65l-.7 2.1 2.5-1.25c.8.22 ' +
        '1.63.35 2.5.35 3.9 0 7-2.6 7-5.85s-3.1-5.9-7-5.9z"/>' +
        '<circle cx="6.9" cy="8.3" r="1" fill="#fff"/><circle cx="11.5" cy="8.3" r="1" fill="#fff"/>' +
        '<path fill="#07C160" stroke="#fff" stroke-width="1" d="M16 10.4c-3.2 0-5.8 2.15-5.8 4.85s2.6 4.85 5.8 ' +
        '4.85c.68 0 1.33-.1 1.94-.27l2.06 1.07-.57-1.75c1.42-.9 2.37-2.3 2.37-3.9 0-2.7-2.6-4.85-5.8-4.85z"/>' +
        '<circle cx="14.1" cy="14.5" r=".85" fill="#fff"/><circle cx="17.9" cy="14.5" r=".85" fill="#fff"/>',
    },
    // Messenger (0.134.0): blue speech bubble with the lightning zigzag.
    messenger: {
      nhan: "Messenger",
      mau: "#0866FF",
      than:
        '<path fill="#0866FF" d="M12 2.2C6.5 2.2 2.2 6.2 2.2 11.6c0 2.8 1.15 5.25 3.03 6.95v3.25l2.9-1.6c1.18.33 ' +
        '2.48.5 3.87.5 5.5 0 9.8-4 9.8-9.4S17.5 2.2 12 2.2z"/>' +
        '<path fill="#fff" d="M6.4 14.3l3.06-4.86a1.2 1.2 0 0 1 1.74-.32l2.43 1.82 2.23-1.69c.3-.23.69.13.49.45' +
        'l-3.06 4.86a1.2 1.2 0 0 1-1.74.32l-2.43-1.82-2.23 1.69c-.3.23-.69-.13-.49-.45z"/>',
    },
    // Meta (0.438.0): the infinity mark. The Facebook Messenger card on the Connections page uses it, since one
    // connection there covers messages, comments and posting; the Messenger channel itself keeps its own bubble.
    // 0.438.2 (owner, 01/11/2026): the hand-drawn stroke looked wrong, so this is the official gradient mark from the
    // owner's file, background removed, as a 128px PNG inside the same 24x24 svg box.
    meta: {
      nhan: "Meta",
      mau: "#0866FF",
      than: '<image href="/static/logos/meta.png" x="0" y="0" width="24" height="24" preserveAspectRatio="xMidYMid meet"/>',
    },
    // 0.446.0: the Meta connection card names every app it covers (owner, 03/11/2026: "Kết nối Meta" with Facebook,
    // Messenger, Instagram, WhatsApp and Threads beside it). Facebook: white "f" on a blue disc.
    facebook: {
      nhan: "Facebook",
      mau: "#0866FF",
      than:
        '<circle cx="12" cy="12" r="10.5" fill="#0866FF"/>' +
        '<path fill="#fff" d="M13.4 22.4v-7.9h2.3l.35-2.7H13.4v-1.7c0-.78.22-1.3 1.33-1.3h1.42V6.4c-.25-.03-1.1-.1' +
        '-2.07-.1-2.05 0-3.45 1.25-3.45 3.55v2h-2.3v2.7h2.3v7.85z"/>',
    },
    // Instagram: the camera outline on the warm gradient square.
    instagram: {
      nhan: "Instagram",
      mau: "#D62976",
      than:
        '<defs><linearGradient id="kenh-ig-g" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#FEDA75"/>' +
        '<stop offset=".35" stop-color="#FA7E1E"/><stop offset=".65" stop-color="#D62976"/><stop offset="1" stop-color="#4F5BD5"/>' +
        '</linearGradient></defs><rect width="24" height="24" rx="7" fill="url(#kenh-ig-g)"/>' +
        '<rect x="5.5" y="5.5" width="13" height="13" rx="4" fill="none" stroke="#fff" stroke-width="1.7"/>' +
        '<circle cx="12" cy="12" r="3.1" fill="none" stroke="#fff" stroke-width="1.7"/><circle cx="15.8" cy="8.2" r=".95" fill="#fff"/>',
    },
    // Threads: a white "@" swirl on black.
    threads: {
      nhan: "Threads",
      mau: "#000000",
      than:
        '<rect width="24" height="24" rx="7" fill="#000"/>' +
        '<path fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" d="M15.2 11.1c-.4-1.9-1.7-2.9-3.5-2.9' +
        '-2.1 0-3.4 1.6-3.4 3.8s1.3 3.7 3.3 3.7c1.9 0 3.1-1.3 3.1-3.2 0-1.3-.9-2.1-2.3-2.1-1.5 0-2.4.9-2.2 2.1.2 1 1.1' +
        ' 1.5 2.1 1.4 2.2-.2 3.2-2.1 2.9-4.5-.3-2.6-2.5-4.4-5.2-4.3C6.9 5.3 5.2 8 5.2 11.8c0 3.9 2.3 6.7 6.4 6.7 2.1 0' +
        ' 3.8-.8 4.9-2.1"/>',
    },
    // A Facebook Page COMMENT in the inbox (0.446.0, owner: the comment and message icons looked the same). A square
    // amber comment box with lines, so it never reads as the round blue Messenger bubble of a private chat.
    fbcomment: {
      nhan: "Comment",
      mau: "#F2760B",
      than:
        '<path fill="#F2760B" d="M5.2 3h13.6A2.7 2.7 0 0 1 21.5 5.7v9.1a2.7 2.7 0 0 1-2.7 2.7H10l-4.6 3.6c-.4.3-.9 0-.9-.5' +
        'v-3.1A2.7 2.7 0 0 1 2.5 14.8V5.7A2.7 2.7 0 0 1 5.2 3z"/>' +
        '<rect x="6.3" y="7" width="11.4" height="1.7" rx=".85" fill="#fff"/>' +
        '<rect x="6.3" y="11.2" width="7.6" height="1.7" rx=".85" fill="#fff"/>',
    },
    // An Instagram COMMENT in the inbox (0.447.0): the same square comment box, in Instagram pink, so it reads as a
    // comment and as Instagram at a glance.
    igcomment: {
      nhan: "Instagram comment",
      mau: "#D62976",
      than:
        '<path fill="#D62976" d="M5.2 3h13.6A2.7 2.7 0 0 1 21.5 5.7v9.1a2.7 2.7 0 0 1-2.7 2.7H10l-4.6 3.6c-.4.3-.9 0-.9-.5' +
        'v-3.1A2.7 2.7 0 0 1 2.5 14.8V5.7A2.7 2.7 0 0 1 5.2 3z"/>' +
        '<rect x="6.3" y="7" width="11.4" height="1.7" rx=".85" fill="#fff"/>' +
        '<rect x="6.3" y="11.2" width="7.6" height="1.7" rx=".85" fill="#fff"/>',
    },
    // A Threads reply in the inbox (0.448.0): the same square comment box, in Threads black.
    thcomment: {
      nhan: "Threads reply",
      mau: "#000000",
      than:
        '<path fill="#111" d="M5.2 3h13.6A2.7 2.7 0 0 1 21.5 5.7v9.1a2.7 2.7 0 0 1-2.7 2.7H10l-4.6 3.6c-.4.3-.9 0-.9-.5' +
        'v-3.1A2.7 2.7 0 0 1 2.5 14.8V5.7A2.7 2.7 0 0 1 5.2 3z" stroke="#fff" stroke-width=".8"/>' +
        '<rect x="6.3" y="7" width="11.4" height="1.7" rx=".85" fill="#fff"/>' +
        '<rect x="6.3" y="11.2" width="7.6" height="1.7" rx=".85" fill="#fff"/>',
    },
    // Discord (0.85.0): the controller-face mark on blurple.
    discord: {
      nhan: "Discord",
      mau: "#5865F2",
      than:
        '<rect width="24" height="24" rx="7" fill="#5865F2"/>' +
        '<path fill="#fff" d="M17.3 7.4a12.3 12.3 0 0 0-3.05-.95l-.38.78a11.4 11.4 0 0 0-3.74 0' +
        'l-.39-.78c-1.07.18-2.1.5-3.05.95C4.76 10.3 4.24 13.1 4.5 15.88a12.4 12.4 0 0 0 3.74 1.9' +
        'l.8-1.3c-.44-.16-.86-.37-1.26-.6l.3-.24a8.8 8.8 0 0 0 7.84 0l.3.24c-.4.23-.82.44-1.26.6' +
        'l.8 1.3a12.4 12.4 0 0 0 3.74-1.9c.3-3.22-.53-6-2.2-8.48zM9.6 14.17c-.73 0-1.33-.68-1.33' +
        '-1.5s.58-1.52 1.33-1.52 1.34.68 1.33 1.52c0 .82-.59 1.5-1.33 1.5zm4.8 0c-.73 0-1.33-.68' +
        '-1.33-1.5s.58-1.52 1.33-1.52 1.34.68 1.33 1.52c0 .82-.58 1.5-1.33 1.5z"/>',
    },
    // Lark / Feishu (0.85.0): the swallow-tail wings, drawn as three overlapping shapes.
    lark: {
      nhan: "Lark",
      mau: "#3370FF",
      than:
        '<path fill="#00D6B9" d="M11.2 4.5h5.6c.5 0 .8.2 1 .6l1.6 3.3c-2.3-.3-4.3.2-6.1 1.5z"/>' +
        '<path fill="#3370FF" d="M3.3 9.6c3.4 2.7 6.7 4.7 10.2 5.4 2.5.5 4.6-.2 6.3-2.1l-1.2 3.3' +
        'c-1.4 3.3-5.2 4.6-9.2 3.1-3-1.1-5-3.6-6.1-6.6z"/>' +
        '<path fill="#133C9A" d="M11.3 10.4c2.5-2.3 5.6-3 8.6-1.8 1 .4 1.6 1 1.9 1.6-.7.2-1.4.7-2' +
        ' 1.3l-.9 1.4c-1.6 1.9-3.7 2.6-6.3 2.1-1.2-.2-2.4-.6-3.5-1.2z"/>',
    },
    // Internal API (0.459.0): a server you run asks a Chatbot over HTTP. Code brackets on slate.
    api: {
      nhan: "API",
      mau: "#475569",
      than:
        '<rect width="24" height="24" rx="7" fill="#475569"/>' +
        '<path fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"' +
        ' d="M9 8l-4 4 4 4M15 8l4 4-4 4M13.2 6.8l-2.4 10.4"/>',
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
