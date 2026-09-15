/* pet.js - LINH VẬT của Javis: một khuôn mặt nhỏ nép ở mép màn hình, lấp ló nửa người.

   Đây KHÔNG phải đồ trang trí. Nó là "sự hiện diện" của Javis ở mọi trang: nhìn theo con trỏ,
   chớp mắt, và đổi biểu cảm theo đúng trạng thái thật của lượt trả lời (nghe / nghĩ / nói /
   lỗi). Trạng thái không tự bịa: app.js gọi JavisPet.setState() ngay trong setOrbState(), tức
   là pet và chữ trên orb luôn nói cùng một điều.

   Hình học và bảng màu lấy nguyên từ bản mẫu javis-avatar-v3.html (chủ dự án chốt), rút gọn
   cho cỡ nhỏ: vành quỹ đạo ở đây là MỘT path có dash xoay, không phải 144 mảnh như bản mẫu.
   Ở 56px thì vệt mờ dần của bản mẫu không ai nhìn thấy, mà 576 lượt ghi style mỗi khung hình
   thì máy nào cũng thấy.

   Tương tác: bấm = trượt ra kèm menu nhanh, bấm lại = nép vào; kéo = đặt lại chỗ, thả ra thì
   tự hút về mép gần nhất. Chỗ đứng, hình dáng, bảng màu lưu ở localStorage (tức thì, khỏi
   nháy lúc mở trang) VÀ ở settings.dashboard.pet trên máy chủ (theo người, không theo máy).

   KHÔNG dùng ký tự em dash ở bất kỳ đâu trong file này. */
(function () {
  "use strict";

  var KHOA = "javis.pet";
  var NGUONG_KEO = 16;   // px di chuyển tối thiểu mới coi là KÉO chứ không phải bấm

  // ---- Hình dáng (path trong viewBox 320x320, tâm 160/160) ----
  var SHAPES = {
    circle:   { key: "pet.shape.circle",   d: "M160 82 A78 78 0 1 1 160 238 A78 78 0 1 1 160 82 Z" },
    square:   { key: "pet.shape.square",   d: "M111 85 H209 Q235 85 235 111 V209 Q235 235 209 235 H111 Q85 235 85 209 V111 Q85 85 111 85 Z" },
    triangle: { key: "pet.shape.triangle", d: "M147 85 Q160 64 173 85 L244 211 Q256 234 230 234 H90 Q64 234 76 211 Z" },
    cloud:    { key: "pet.shape.cloud",    d: "M105 224 C62 224 54 171 84 155 C71 119 102 92 131 106 C149 66 209 81 214 118 C255 110 273 160 246 182 C258 219 219 244 191 226 C167 249 127 246 105 224 Z" },
    pentagon: { key: "pet.shape.pentagon", d: "M150 80 Q160 73 170 80 L235 127 Q244 133 240 145 L216 222 Q213 232 201 232 H119 Q107 232 104 222 L80 145 Q76 133 85 127 Z" },
  };

  // Mỗi bảng màu tự mang cả hai tông: [thân, vành quỹ đạo, dự phòng]. Tông theo giao diện đang bật
  // (javisTheme), nên pet không bao giờ chói lên giữa nền tối.
  var PALETTES = {
    amber:    { key: "pet.color.amber",    sun: ["#F28C28", "#F7C98F", "#F7E3CF"], moon: ["#E8C97A", "#F3DEAA", "#2B241D"] },
    pearl:    { key: "pet.color.pearl",    sun: ["#E3DCCF", "#B8AA95", "#EAE4D9"], moon: ["#DDD7CA", "#FFF0D4", "#292720"] },
    clay:     { key: "pet.color.clay",     sun: ["#B76A4B", "#E5AA87", "#EEDDD2"], moon: ["#CEA58C", "#F1CFB5", "#30231E"] },
    rose:     { key: "pet.color.rose",     sun: ["#CB6576", "#F2ABAE", "#F2DCE0"], moon: ["#DCA4B0", "#F4CBD2", "#30212A"] },
    honey:    { key: "pet.color.honey",    sun: ["#D5A32D", "#F3D381", "#F2E7C8"], moon: ["#DCC888", "#F6E7B6", "#2D291C"] },
    sage:     { key: "pet.color.sage",     sun: ["#639574", "#AAD2A9", "#DDE9DC"], moon: ["#A5C5A6", "#D3E6C5", "#202D25"] },
    jade:     { key: "pet.color.jade",     sun: ["#379E90", "#8FD6C5", "#D7EBE4"], moon: ["#8BC6BA", "#C2E9D9", "#1D2C29"] },
    blue:     { key: "pet.color.blue",     sun: ["#548EC5", "#A4CDEB", "#DCE7F0"], moon: ["#9DBBDB", "#CDDEF1", "#212A35"] },
    lavender: { key: "pet.color.lavender", sun: ["#9272C2", "#C9B2E7", "#E8DFF1"], moon: ["#BBA9D7", "#E0CEF1", "#292333"] },
    pink:     { key: "pet.color.pink",     sun: ["#C67FAB", "#EDB9D6", "#F0DFE9"], moon: ["#D3AEC7", "#F1D3E4", "#30232D"] },
    slate:    { key: "pet.color.slate",    sun: ["#7B8794", "#B8C4CD", "#E0E4E8"], moon: ["#ADB7C2", "#D6E0E8", "#252A30"] },
    cocoa:    { key: "pet.color.cocoa",    sun: ["#79604F", "#BFA38A", "#E8DFD5"], moon: ["#B9A38A", "#E3CDB0", "#2B2620"] },
  };

  // Cỡ pet. Số là bề ngang tính bằng px trên MÀN RỘNG; màn hẹp nhân thêm hệ số ở dưới.
  // Mặc định "vua" chứ không phải "nho": bản đầu để 56px và trên điện thoại còn co xuống 46px,
  // chủ dự án báo nhìn bé quá, nhất là trên iPhone.
  var SIZES = {
    nho:  { key: "pet.size.nho",  px: 52 },
    vua:  { key: "pet.size.vua",  px: 72 },
    lon:  { key: "pet.size.lon",  px: 96 },
    rat_lon: { key: "pet.size.rat_lon", px: 124 },
  };
  // Màn hẹp KHÔNG thu nhỏ nữa. Ngược lại: ngón tay to hơn con trỏ chuột, và màn hình bé thì
  // một chấm 52px còn khó thấy hơn trên màn rộng. Giữ nguyên cỡ đã chọn.

  // MÀU MẮT do người dùng chọn, hai lựa chọn thôi: đen hoặc trắng. Trước đây con số này suy
  // tự động từ độ chói của thân (xem mauMatTuDong), nhưng chủ dự án muốn tự quyết - bảng màu
  // sáng thì mắt trắng nhìn cũng có nét riêng, và "tự động" thì không ai đoán được nó sẽ ra gì.
  // Avatar trợ lý KHÔNG theo lựa chọn này: chúng là nhân dạng khác, vẫn suy tự động.
  var MAU_MAT = { den: "#201e1e", trang: "#ffffff" };
  var MAC_DINH = { enabled: true, shape: "circle", palette: "amber", side: "right", pos: 0.62, size: "vua", eye: "den" };

  // DÁNG LIẾC - chữ ký của nhân vật. Linh vật KHÔNG nhìn thẳng lúc nghỉ: nó liếc chéo lên
  // phía trên bên phải, đúng như hình logo tĩnh. Nhìn thẳng thì ra một cái mặt cười vô hồn;
  // liếc đi thì nó thành một thực thể đang để ý tới cái gì đó ngoài khung.
  //
  // Đơn vị của LIEC_* là đơn vị viewBox (320x320, thân bán kính 78). NGHI_* là cùng dáng ấy
  // quy về thang -1..1 của tầm đưa mắt, để lúc rời chuột con mắt TRÔI VỀ dáng này chứ không
  // trôi về giữa. TAM_* là tầm đưa mắt tối đa: đủ rộng để con trỏ kéo được mắt sang hẳn bên
  // kia, chứ không phải chỉ nhúc nhích quanh dáng liếc.
  var LIEC_X = 16, LIEC_Y = -12;      // dáng chân dung (ảnh tĩnh, không có con trỏ)
  var TAM_X = 24, TAM_Y = 18;
  var NGHI_X = LIEC_X / TAM_X, NGHI_Y = LIEC_Y / TAM_Y;

  // ---- Biểu cảm: TOÀN BỘ cảm xúc nằm ở đôi mắt, không có miệng ----
  // Chủ dự án chốt: mắt to nhỏ đổi cỡ là đủ diễn, đừng thêm chi tiết.
  //
  // Mỗi mục tả MỘT con mắt quanh gốc toạ độ (0,0), không phải cả cặp ở vị trí cố định. Nhờ
  // vậy veMat() xếp lại được hai mắt theo hàng NGANG (lúc trượt ra) hay theo cột DỌC (lúc
  // nép ở mép, chỉ còn nửa thân nhìn thấy) mà không phải khai hai bộ biểu cảm song song.
  // Mục là mảng [trái, phải] khi hai mắt KHÁC nhau.
  var EYES = {
    neutral:    '<ellipse rx="7.2" ry="17.5"/>',
    curious:    '<ellipse cy="-2" rx="8.4" ry="21"/>',
    excited:    '<ellipse cy="-1" rx="9.2" ry="22.5"/>',
    // Đang nghĩ: hai tròng nhìn chéo lên, một bên hẹp hơn một chút cho ra vẻ đang lục trí nhớ.
    thinking:   ['<ellipse cx="2" cy="-8" rx="6.4" ry="15"/>', '<ellipse cx="2" cy="-9" rx="7.6" ry="18"/>'],
    happy:      '<path class="pet-line" d="M-9 6 Q0 -7 9 6"/>',
    // Hai gạch ngang lúc ĐANG NGHĨ. Cố ý NGẮN hơn dáng chớp mắt và hơi nhếch lên: chớp mắt là
    // mắt NHẮM (vệt kéo hết bề ngang con mắt), còn đây là mắt lim dim nghĩ ngợi - hai thứ đó
    // trông giống nhau thì một cú chớp giữa lúc nghĩ nhìn như máy bị khựng.
    nghi:       '<path class="pet-line" d="M-7 -1 H7"/>',
    sleepy:     '<path class="pet-line" d="M-9 6 H9"/>',
    sad:        '<path class="pet-line" d="M-9 -2 Q0 -10 9 -2"/>',
    suspicious: ['<path class="pet-line" d="M-9 -3 H9"/>', '<path class="pet-line" d="M-9 2 H9"/>'],
    blink:      '<path class="pet-line" d="M-9 0 H9"/>',
  };

  // ĐANG NGHĨ thì hai con mắt ĐỔI QUA ĐỔI LẠI giữa hai dáng, không đứng yên một dáng:
  //   "thinking" = liếc chéo lên, như đang lục trí nhớ;
  //   "nghi"     = hai gạch ngang, dáng lim dim nghĩ ngợi (chủ dự án chốt 15/09 là thích dáng
  //                này nhất, và đồng ý để nó luân phiên với dáng trên).
  // Mỗi dáng giữ chừng một giây rưỡi rồi đổi. Muốn nó ĐỨNG YÊN ở hai gạch ngang thì bỏ mảng
  // này còn một phần tử "nghi" - vòng vẽ tự thôi đổi, không phải sửa chỗ nào khác.
  var NGHI_MAT = ["thinking", "nghi"];
  var NGHI_LAU = [1500, 1200];   // mỗi dáng giữ bao lâu (ms), cộng thêm một chút ngẫu nhiên

  // Trạng thái thật của lượt (app.js bắn sang) -> biểu cảm + nhịp vành quỹ đạo.
  //   ring: tốc độ xoay (độ/giây); 0 = đứng yên. dash: hình dải. mo: độ mờ của vành.
  // Độ mờ: trạng thái NGHỈ (idle/paused) cố ý nhạt, mọi trạng thái đang làm việc thì ĐỤC HẲN.
  // Nét vẽ và màu của vành do CSS lo theo data-state (xem .pet-ring trong style.css), ở đây
  // chỉ còn nhịp xoay + hình dải. Trước 0.59.4 các trạng thái đang làm để 0,6-0,95 nên cộng
  // với nét mảnh màu nhạt là nhìn không ra pet có đang chạy hay không.
  //
  // HÌNH DẢI: ÍT VỆT, VỆT DÀI. Đơn vị tính trên pathLength 360, nên "44 46" là chu kỳ 90, tức
  // đúng 4 vệt chạy quanh người. Bản trước để "4 11" (24 vệt) và "8 14" (16 vệt): ở cỡ lớn nó
  // thành một vòng chấm lấm tấm chạy vòng vòng, chủ dự án nhìn bản thật rồi bảo rối mắt. Vài
  // vệt dài trông như một quỹ đạo thật; hai chục chấm trông như đèn trang trí.
  // Đổi số ở đây thì nhớ: tổng một chu kỳ nên chia hết 360, không thì chỗ khép vòng có một vệt
  // cụt dài ngắn khác hẳn các vệt còn lại.
  var STATES = {
    idle:         { eye: "neutral",    ring: 7,   dash: "286 74",  mo: 0.45 },   // 1 vệt dài, hở một quãng
    listening:    { eye: "curious",    ring: 26,  dash: "44 46",   mo: 1 },      // 4 vệt
    waiting:      { eye: "curious",    ring: 12,  dash: "30 60",   mo: 1 },      // 4 vệt, thưa hơn
    thinking:     { eye: "thinking",   ring: 108, dash: "100 80",  mo: 1 },      // 2 vệt dài, quay nhanh
    speaking:     { eye: "happy",      ring: 18,  dash: "56 34",   mo: 1 },      // 4 vệt, dày dặn
    paused:       { eye: "sleepy",     ring: 4,   dash: "286 74",  mo: 0.35 },
    reconnecting: { eye: "suspicious", ring: 40,  dash: "24 36",   mo: 1 },      // 6 vệt ngắn: bồn chồn
    error:        { eye: "sad",        ring: 0,   dash: "286 74",  mo: 1 },
  };

  var el = null, svg = null, nutBody = null, menu = null;
  var pRing = null, pFace = null, gEyes = null, gRig = null;
  var cfg = Object.assign({}, MAC_DINH);
  var state = "idle", mood = "neutral", dangChop = false;
  var raf = 0, truoc = 0, gocRing = 0, tocDo = STATES.idle.ring, tocDoDich = STATES.idle.ring;
  var chopLuc = 0, liecLuc = 0, vuiDen = 0;
  // Nhịp ĐỔI MẮT lúc đang nghĩ (xem NGHI_MAT). nghiPha = đang ở dáng nào.
  var nghiLuc = 0, nghiPha = 0;
  var tx = 0, ty = 0, px = 0, py = 0;      // hướng nhìn: đích và giá trị đang nội suy
  var liecX = 0, liecY = 0, liecDichX = 0, liecDichY = 0;
  var chuotLuc = 0;
  var keo = null;                           // { id, dx, dy, di } khi đang kéo
  var giamChuyenDong = null;

  function t(k, d) {
    try {
      var v = window.t ? window.t(k) : k;
      return (!v || v === k) ? (d || k) : v;
    } catch (e) { return d || k; }
  }
  function kep(n, a, b) { return Math.max(a, Math.min(b, n)); }
  function noiSuy(a, b, k) { return a + (b - a) * k; }
  function sang() { try { return !!(window.javisTheme && window.javisTheme.isLight()); } catch (e) { return false; } }
  // Mắt phải tương phản với THÂN, không với nền trang: thân sáng thì mắt than chì, thân tối
  // thì mắt trắng. Tính bằng độ chói tương đối (WCAG) chứ không đoán bằng mắt.
  // Đây là đường TỰ ĐỘNG, nay chỉ còn dùng cho avatar trợ lý; con pet đi theo cfg.eye.
  function mauMatTuDong(than) {
    var rgb = than.slice(1).match(/../g).map(function (x) {
      var v = parseInt(x, 16) / 255;
      return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return (rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722) > 0.179 ? "#201e1e" : "#ffffff";
  }
  // Màu mắt của CON PET: lựa chọn của người dùng, không suy từ thân nữa.
  function mauMatCfg() { return MAU_MAT[cfg.eye] || MAU_MAT.den; }

  // ---- Lưu / nạp ----
  function docLocal() {
    try {
      var o = JSON.parse(localStorage.getItem(KHOA) || "null");
      if (o && typeof o === "object") return o;
    } catch (e) {}
    return null;
  }
  function ghiLocal() { try { localStorage.setItem(KHOA, JSON.stringify(cfg)); } catch (e) {} }
  function ghiServer() {
    // Gửi lên máy chủ để pet theo NGƯỜI chứ không theo máy. Hỏng mạng thì thôi: localStorage
    // ở trên đã giữ lựa chọn rồi, không được để một lượt fetch lỗi làm mất cài đặt.
    try {
      // POST /settings nhận FormData (section + data), KHÔNG nhận JSON body. Gửi JSON thì
      // FastAPI trả 422 và cài đặt lặng lẽ không bao giờ tới máy chủ.
      var fd = new FormData();
      fd.append("section", "dashboard");
      fd.append("data", JSON.stringify({ pet: cfg }));
      return fetch("/settings", { method: "POST", body: fd }).catch(function () {});
    } catch (e) { return Promise.resolve(); }
  }

  // Nút Lưu của trang Linh vật. KHÔNG chỉ POST rồi báo xanh: POST xong ĐỌC LẠI /settings và
  // so từng khoá với thứ vừa gửi. Vì sao phải khổ thế: nhánh lưu bên server lọc từng khoá một
  // (xem section "dashboard" trong main.py), nên một giá trị không qua được bộ lọc sẽ bị bỏ
  // TRONG IM LẶNG - request vẫn 200, màn hình vẫn đúng nhờ localStorage, và chỉ tới lần F5 sau
  // người dùng mới thấy lựa chọn của mình biến mất. Đúng lỗi cỡ "Rất lớn" đã dính.
  // Trả về Promise {ok, lech: [khoá lệch]}.
  function luu() {
    var muon = Object.assign({}, cfg);
    return ghiServer()
      .then(function () { return fetch("/settings"); })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        var da = (j.dashboard || {}).pet || {};
        var lech = Object.keys(muon).filter(function (k) {
          if (k === "pos") return Math.abs(Number(da[k]) - Number(muon[k])) > 0.001;
          return da[k] !== muon[k];
        });
        return { ok: !lech.length, lech: lech };
      })
      .catch(function () { return { ok: false, lech: [] }; });
  }
  function chuanHoa(o) {
    var c = Object.assign({}, MAC_DINH, o || {});
    if (!SHAPES[c.shape]) c.shape = MAC_DINH.shape;
    if (!PALETTES[c.palette]) c.palette = MAC_DINH.palette;
    if (c.side !== "left" && c.side !== "right") c.side = MAC_DINH.side;
    if (!SIZES[c.size]) c.size = MAC_DINH.size;
    if (!MAU_MAT[c.eye]) c.eye = MAC_DINH.eye;
    c.pos = kep(Number(c.pos) || MAC_DINH.pos, 0.05, 0.95);
    c.enabled = c.enabled !== false;
    return c;
  }

  // ---- Dựng DOM ----
  function dung() {
    if (el) return;
    el = document.createElement("div");
    el.id = "javisPet";
    el.className = "pet";
    el.dataset.out = "0";
    el.dataset.menu = "0";
    el.innerHTML =
      '<button type="button" class="pet-body" aria-label="Javis">' +
        '<svg viewBox="0 0 320 320" aria-hidden="true">' +
          '<g class="pet-rig">' +
            '<path class="pet-ring" pathLength="360"></path>' +
            '<path class="pet-face"></path>' +
            '<g class="pet-eyes"></g>' +
          '</g>' +
        '</svg>' +
      '</button>' +
      '<div class="pet-menu" hidden></div>';
    document.body.appendChild(el);
    svg = el.querySelector("svg");
    nutBody = el.querySelector(".pet-body");
    menu = el.querySelector(".pet-menu");
    gRig = el.querySelector(".pet-rig");
    pRing = el.querySelector(".pet-ring");
    pFace = el.querySelector(".pet-face");
    gEyes = el.querySelector(".pet-eyes");
    noiTuongTac();
  }

  // Mic ĐANG bật hay không. Hỏi thẳng lớp CSS của nút mic thật (#voiceBtn) chứ không nuôi một
  // cờ riêng: trạng thái rảnh tay tắt ở nhiều đường (bấm nút, mic hỏng, phiên Live đóng) và
  // đường nào cũng gỡ đúng lớp này, nên đây là chỗ duy nhất không bao giờ nói dối.
  function micDangBat() {
    var b = document.getElementById("voiceBtn");
    return !!(b && b.classList.contains("handsfree"));
  }

  function veMenu() {
    // Icon lấy từ tầng icon chung (window.ic), KHÔNG dùng emoji: dashboard này cấm emoji
    // trong giao diện, vì emoji mỗi hệ điều hành vẽ một kiểu và trình đọc màn hình đọc ra
    // một cái tên vô nghĩa. Thiếu window.ic (nạp lỗi) thì để trống chứ không thay bằng chữ.
    var icon = function (ten) { return window.ic ? window.ic(ten) : ""; };
    var mic = micDangBat();
    var muc = [
      { id: "chat", ic: icon("message-circle"), nhan: t("pet.menu.chat", "Trò chuyện") },
      { id: "agent", ic: icon("bot"), nhan: t("pet.menu.agent", "Trợ lý") },
      { id: "workflow", ic: icon("workflow"), nhan: t("pet.menu.workflow", "Quy trình") },
      // Mic là CÔNG TẮC, nên nhãn phải nói việc sắp xảy ra chứ không phải trạng thái hiện tại:
      // đang tắt thì mời "Bật mic", đang bật thì mời "Tắt mic". Nhãn tính lại mỗi lần mở menu
      // (xem moMenu), vì mic còn bật tắt được từ nút mic dưới ô nhập và từ phiên Live.
      { id: "mic", ic: icon("mic"), nhan: mic ? t("pet.menu.mic_off", "Tắt mic") : t("pet.menu.mic_on", "Bật mic") },
      { id: "pet", ic: icon("settings"), nhan: t("pet.menu.settings", "Cài đặt pet") },
    ];
    menu.innerHTML = muc.map(function (m) {
      return '<button type="button" data-pet-go="' + m.id + '"><span aria-hidden="true">' + m.ic + '</span>' +
             '<b></b></button>';
    }).join("");
    // Nhãn gán bằng textContent chứ không nối chuỗi: nó tới từ từ điển, và từ điển là dữ liệu.
    menu.querySelectorAll("button").forEach(function (b, i) { b.querySelector("b").textContent = muc[i].nhan; });
  }

  // ---- Diện mạo ----
  function apDung() {
    if (!el) return;
    var d = SHAPES[cfg.shape].d;
    pFace.setAttribute("d", d);
    pRing.setAttribute("d", d);
    var tone = PALETTES[cfg.palette][sang() ? "sun" : "moon"];
    el.style.setProperty("--pet-face", tone[0]);
    el.style.setProperty("--pet-ring", tone[1]);
    el.style.setProperty("--pet-eye", mauMatCfg());
    el.dataset.side = cfg.side;
    // Cỡ đi bằng BIẾN CSS chứ không phải style.width trực tiếp: menu, viền focus và luật màn
    // hẹp đều ăn theo cùng một con số, khai một chỗ thì không có chỗ nào lệch.
    el.style.setProperty("--pet-size", SIZES[cfg.size].px + "px");
    veMat(dangChop ? "blink" : mood);   // đổi mép thì hai mắt dồn sang phía kia
    el.style.top = (cfg.pos * 100).toFixed(2) + "%";
    el.style.left = cfg.side === "left" ? "0px" : "";
    el.style.right = cfg.side === "right" ? "0px" : "";
    el.hidden = !cfg.enabled || dangChanCua();
  }

  // Màn đăng nhập là một CỔNG: chưa qua thì chưa có gì để linh vật hiện diện cùng, và một
  // khuôn mặt nhấp nháy cạnh ô mật khẩu chỉ làm người ta phân tâm. Theo dõi bằng
  // MutationObserver vì lớp `.open` do app.js gắn sau một lượt gọi mạng, không có sự kiện nào.
  function dangChanCua() {
    var g = document.getElementById("authOverlay");
    return !!(g && g.classList.contains("open"));
  }
  function ngoCongDangNhap() {
    var g = document.getElementById("authOverlay");
    if (!g || !window.MutationObserver) return;
    new MutationObserver(function () {
      if (!el) return;
      el.hidden = !cfg.enabled || dangChanCua();
      if (el.hidden) { moMenu(false); raNgoai(false); dung_lai(); } else chay();
    }).observe(g, { attributes: true, attributeFilter: ["class"] });
  }

  // Xếp hai con mắt. Lúc nép ở mép, hai mắt vẫn đứng CẠNH NHAU theo hàng ngang nhưng NÉ hẳn
  // sang nửa thân còn nhìn thấy, và xích lại gần nhau một chút cho vừa chỗ. Đừng để chúng
  // đứng yên giữa mặt: một nửa mặt bị mép màn hình cắt mất thì con mắt bên kia cũng mất theo,
  // và cái thò ra chỉ còn một con mắt rưỡi.
  function veMat(ten) {
    if (!gEyes) return;
    var e = EYES[ten] || EYES.neutral;
    var trai = typeof e === "string" ? e : e[0];
    var phai = typeof e === "string" ? e : e[1];
    var a, b;
    if (el && el.dataset.out !== "1") {
      var tam = cfg.side === "right" ? -34 : 34;   // tâm của cặp mắt, lệch về phía còn thấy
      a = [tam - 13, 0]; b = [tam + 13, 0];
    } else {
      a = [-15, 0]; b = [15, 0];
    }
    gEyes.innerHTML =
      '<g transform="translate(' + (160 + a[0]) + " " + (160 + a[1]) + ')">' + trai + "</g>" +
      '<g transform="translate(' + (160 + b[0]) + " " + (160 + b[1]) + ')">' + phai + "</g>";
  }

  // ---- Vòng vẽ ----
  function nhip(now) {
    raf = 0;
    if (!el || el.hidden) return;
    var dt = Math.min((now - (truoc || now)) / 1000, 0.05);
    truoc = now;

    if (giamChuyenDong && giamChuyenDong.matches) {
      // Tôn trọng prefers-reduced-motion: đứng yên hoàn toàn, chỉ giữ biểu cảm.
      gRig.style.transform = "";
      pRing.style.strokeDashoffset = "0";
      return;
    }

    // Nhìn theo con trỏ; rời chuột hơn 1,6 giây thì trôi về DÁNG LIẾC (không phải về giữa)
    // rồi thi thoảng đảo mắt quanh dáng đó.
    var ranh = now - chuotLuc > 1600;
    if (ranh) { tx = 0; ty = 0; }
    var muot = 1 - Math.exp(-dt * 7);
    px = noiSuy(px, tx, muot); py = noiSuy(py, ty, muot);
    if (ranh) {
      if (now > liecLuc) {
        // Biên đảo mắt phải NHỎ so với dáng liếc, không thì có lúc nó gần như nhìn thẳng và
        // dáng liếc thôi không còn là chữ ký nữa, chỉ còn là một trong các hướng ngẫu nhiên.
        liecDichX = kep(NGHI_X + (Math.random() * 2 - 1) * 0.17, -1, 1);
        liecDichY = kep(NGHI_Y + (Math.random() * 2 - 1) * 0.13, -1, 1);
        liecLuc = now + 3600 + Math.random() * 3200;
      }
      var cham = 1 - Math.exp(-dt * 1.2);
      liecX = noiSuy(liecX, liecDichX, cham); liecY = noiSuy(liecY, liecDichY, cham);
    } else {
      var ve = 1 - Math.exp(-dt * 4);
      liecX = noiSuy(liecX, 0, ve); liecY = noiSuy(liecY, 0, ve);
    }
    var nhinX = kep(px + liecX, -1, 1), nhinY = kep(py + liecY, -1, 1);
    var tho = Math.sin(now * 0.00135) * 0.8;

    // Lúc nép ở mép thì ghìm tầm mắt lại: nửa thân bị màn hình cắt mất, đưa mắt hết tầm là
    // một con trôi ra ngoài phần còn nhìn thấy.
    var ghim = el.dataset.out === "1" ? 1 : 0.45;

    gRig.style.transform = "translate(" + (nhinX * 3.4).toFixed(2) + "px," +
      (nhinY * 2.4 + tho * 0.5).toFixed(2) + "px)";
    gEyes.style.transform = "translate(" + (nhinX * TAM_X * ghim).toFixed(2) + "px," +
      (nhinY * TAM_Y * ghim).toFixed(2) + "px)";

    tocDo += (tocDoDich - tocDo) * (1 - Math.exp(-dt * 2));
    gocRing = (gocRing + tocDo * dt) % 360;
    pRing.style.strokeDashoffset = (-gocRing).toFixed(2);

    // Đang NGHĨ: đảo giữa dáng lục trí nhớ và hai gạch ngang. Đứng yên một dáng suốt ba chục
    // giây thì con mắt thành hai cái hình dán; đảo qua lại là nó đang thật sự nghĩ.
    if (state === "thinking" && NGHI_MAT.length > 1 && !dangChop && now > nghiLuc) {
      nghiPha = (nghiPha + 1) % NGHI_MAT.length;
      mood = NGHI_MAT[nghiPha];
      veMat(mood);
      nghiLuc = now + NGHI_LAU[nghiPha % NGHI_LAU.length] + Math.random() * 500;
    }

    // Chớp mắt: ngắn và KHÔNG đều nhịp. Đều nhịp là cảm giác máy móc.
    if (now > chopLuc && !dangChop && vuiDen < now) {
      dangChop = true; veMat("blink");
      setTimeout(function () { dangChop = false; veMat(mood); }, 130);
      chopLuc = now + 2800 + Math.random() * 3200;
    }
    if (vuiDen && now > vuiDen) { vuiDen = 0; apDungTrangThai(); }

    raf = requestAnimationFrame(nhip);
  }
  function chay() {
    if (raf || !el || el.hidden) return;
    truoc = 0;
    raf = requestAnimationFrame(nhip);
  }
  function dung_lai() { if (raf) cancelAnimationFrame(raf); raf = 0; }

  function apDungTrangThai() {
    var s = STATES[state] || STATES.idle;
    mood = s.eye;
    // Vào lại trạng thái nghĩ thì bắt đầu từ dáng ĐẦU của NGHI_MAT và chờ đủ một nhịp mới đổi.
    // Không đặt lại thì mốc cũ đã trôi qua từ lâu, nên vừa bắt đầu nghĩ là mắt nháy sang dáng
    // kia ngay lập tức, trông như giật.
    nghiPha = 0;
    nghiLuc = (typeof performance !== "undefined" ? performance.now() : 0) + NGHI_LAU[0];
    if (!dangChop) veMat(mood);
    tocDoDich = s.ring;
    pRing.style.strokeDasharray = s.dash;
    pRing.style.opacity = String(s.mo);
    el.dataset.state = state;
  }

  // ---- Tương tác ----
  // HAI trạng thái TÁCH RỜI, đừng gộp lại làm một:
  //   data-out  = pet đang đứng hẳn ra ngoài mép hay còn nép nửa người vào trong.
  //   data-menu = khung menu nhanh đang mở hay đóng.
  // Gộp chung thì bấm ra chỗ khác là pet bị hút ngược vào mép cùng lúc menu đóng, trong khi
  // chủ dự án muốn nó ĐỨNG NGUYÊN ngoài đó cho tới khi bị ném trở vào (kéo sát mép rồi thả).
  function raNgoai(ra) {
    el.dataset.out = ra ? "1" : "0";
    veMat(dangChop ? "blink" : mood);   // nép thì hai mắt né sang nửa còn thấy
  }
  function moMenu(mo) {
    // Vẽ lại MỖI LẦN mở, không chỉ lần đầu: nhãn mục mic đổi theo trạng thái mic, mà mic thì
    // bật tắt được từ chỗ khác (nút dưới ô nhập, phím Space, phiên Live đóng lại).
    if (mo) veMenu();
    menu.hidden = !mo;
    el.dataset.menu = mo ? "1" : "0";
    if (mo) ghimMenuTrongMan();
  }
  // Menu neo giữa thân pet, mà pet thì đứng được sát mép trên hoặc mép dưới. Với năm mục nó
  // cao hơn 200px, nên ở hai đầu màn hình phần thò ra bị cắt mất và mục đầu (hay mục cuối)
  // không bấm được. Đo xong đẩy vào bằng marginTop: không đụng tới `transform`, nên hoạt ảnh
  // mở menu (petMenuVao, cũng ghi transform) vẫn chạy nguyên.
  function ghimMenuTrongMan() {
    menu.style.marginTop = "";
    var r = menu.getBoundingClientRect();
    if (!r.height) return;
    var le = 8, dich = 0;
    if (r.top < le) dich = le - r.top;
    else if (r.bottom > window.innerHeight - le) dich = (window.innerHeight - le) - r.bottom;
    if (dich) menu.style.marginTop = Math.round(dich) + "px";
  }

  function noiTuongTac() {
    nutBody.addEventListener("pointerdown", function (e) {
      if (e.button !== undefined && e.button !== 0) return;
      var r = el.getBoundingClientRect();
      keo = { id: e.pointerId, x0: e.clientX, y0: e.clientY, dy: e.clientY - (r.top + r.height / 2), di: false };
      try { nutBody.setPointerCapture(e.pointerId); } catch (err) {}
    });
    nutBody.addEventListener("pointermove", function (e) {
      if (!keo || e.pointerId !== keo.id) return;
      // Mất pointerup (con trỏ rời cửa sổ, setPointerCapture không ăn, hộp thoại của hệ điều
      // hành xen vào) thì `keo` kẹt lại và pet sẽ bám theo chuột dù không ai bấm nút nào.
      // `buttons === 0` là bằng chứng chắc chắn rằng nút đã nhả: bỏ lượt kéo ngay.
      if (e.buttons === 0) { keo = null; delete el.dataset.dragging; return; }
      if (!keo.di && Math.abs(e.clientX - keo.x0) + Math.abs(e.clientY - keo.y0) < NGUONG_KEO) return;
      if (!keo.di) { keo.di = true; el.dataset.dragging = "1"; moMenu(false); raNgoai(true); }
      var y = kep((e.clientY - keo.dy) / Math.max(window.innerHeight, 1), 0.06, 0.94);
      cfg.pos = y;
      cfg.side = e.clientX < window.innerWidth / 2 ? "left" : "right";
      el.style.top = (y * 100).toFixed(2) + "%";
      if (el.dataset.side !== cfg.side) { el.dataset.side = cfg.side; veMat(mood); }
      el.style.left = cfg.side === "left" ? "0px" : "";
      el.style.right = cfg.side === "right" ? "0px" : "";
    });
    function thaKeo(e) {
      if (!keo || (e && e.pointerId !== keo.id)) return;
      var daKeo = keo.di;
      var x = e ? e.clientX : 0;
      keo = null;
      delete el.dataset.dragging;
      if (daKeo) {
        // NÉM VÀO MÉP thì nó mới chui vào. Thả ở giữa màn hình thì nó hút về mép gần nhất
        // nhưng vẫn đứng nguyên cả người ngoài đó. Ngưỡng tính theo bề ngang pet chứ không
        // phải một số px cứng, để trên màn hẹp (pet 46px) không phải ném chính xác hơn.
        var mep = Math.min(x, window.innerWidth - x);
        raNgoai(mep > el.getBoundingClientRect().width * 0.5);
        ghiLocal(); ghiServer();
        return;
      }
      var dangRa = el.dataset.out === "1";
      if (!dangRa) {                       // đang nép: trượt hẳn ra và mở menu, chào một nhịp
        raNgoai(true); moMenu(true);
        mood = "excited"; veMat(mood); vuiDen = performance.now() + 1500;
      } else {
        moMenu(el.dataset.menu !== "1");   // đã ở ngoài: bấm chỉ bật tắt menu, không chui vào
      }
    }
    nutBody.addEventListener("pointerup", thaKeo);
    nutBody.addEventListener("pointercancel", thaKeo);

    menu.addEventListener("click", function (e) {
      var b = e.target.closest("[data-pet-go]");
      if (!b) return;
      var id = b.dataset.petGo;
      moMenu(false);
      // Mic: BẤM HỘ cái nút mic thật chứ không gọi lại API giọng nói. Nút đó còn kéo theo cả
      // loa, chế độ Live và mấy câu báo lỗi mic (xem voiceBtn trong app.js); dựng đường thứ
      // hai là sớm muộn hai đường nói hai chuyện khác nhau.
      if (id === "mic") {
        var nutMic = document.getElementById("voiceBtn");
        if (nutMic) nutMic.click();
        return;
      }
      // Trợ lý và Quy trình là HAI TAB của cùng trang Cộng sự, không phải hai trang: đi qua
      // openTab() để mở đúng tab, chứ JavisNav.go("workspace") thì rơi vào tab đang nhớ dở
      // từ lần trước và cú bấm "Quy trình" có khi mở ra danh sách trợ lý.
      if (id === "agent" || id === "workflow") {
        try { if (window.JavisWorkspace) { window.JavisWorkspace.openTab(id); return; } } catch (err) {}
        id = "workspace";
      }
      try { window.JavisNav && window.JavisNav.go(id); } catch (err) {}
    });

    // Bấm ra chỗ khác thì ĐÓNG MENU, và chỉ đóng menu. Pet đứng nguyên chỗ nó đang đứng.
    // Cũng không có đồng hồ tự nép: một con vật tự bỏ đi giữa lúc người ta đang định bấm
    // là kiểu khó chịu nhất của mấy widget nổi.
    document.addEventListener("pointerdown", function (e) {
      if (!el || el.hidden || el.dataset.menu !== "1") return;
      if (!el.contains(e.target)) moMenu(false);
    }, true);

    window.addEventListener("pointermove", function (e) {
      if (!el || el.hidden || keo) return;
      var r = el.getBoundingClientRect();
      if (!r.width) return;
      var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      // Chia cho một bán kính RỘNG hơn thân pet: chia cho chính bề rộng thân thì chỉ cần
      // chuột ra khỏi pet vài chục px là mắt đã chạm biên và đứng im.
      tx = kep((e.clientX - cx) / 420, -1, 1);
      ty = kep((e.clientY - cy) / 320, -1, 1);
      chuotLuc = performance.now();
    }, { passive: true });

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) dung_lai(); else chay();
    });
  }

  // ---- API công khai ----
  function setState(s) {
    if (!STATES[s]) s = "idle";
    if (s === state) return;
    state = s;
    vuiDen = 0;
    if (el) apDungTrangThai();
  }
  function setCfg(patch) {
    cfg = chuanHoa(Object.assign({}, cfg, patch || {}));
    ghiLocal(); ghiServer();
    if (el) { apDung(); chay(); }
    veDauAn();
    try { window.dispatchEvent(new CustomEvent("javis:pet", { detail: Object.assign({}, cfg) })); } catch (e) {}
  }
  function setEnabled(on) { setCfg({ enabled: !!on }); }

  function init() {
    cfg = chuanHoa(docLocal());
    dung();
    veMenu();
    apDung();
    apDungTrangThai();
    giamChuyenDong = window.matchMedia("(prefers-reduced-motion: reduce)");
    try { giamChuyenDong.addEventListener("change", function () { chay(); }); } catch (e) {}
    chopLuc = performance.now() + 2600;
    ngoCongDangNhap();
    chay();
    veDauAn();
    try { window.javisTheme && window.javisTheme.on(function () { apDung(); veDauAn(); }); } catch (e) {}
    window.addEventListener("javis:i18n", function () { veMenu(); });
    // Logo riêng của người dùng thắng linh vật, nên phải hỏi máy chủ một lượt. Hỏi SAU khi
    // đã vẽ bằng localStorage: chờ mạng xong mới vẽ thì thanh bên nháy một nhịp lúc mở trang.
    fetch("/settings").then(function (r) { return r.json(); }).then(function (j) {
      _logoRieng = !!((j.branding || {}).logo_ext);
      var petMayChu = (j.dashboard || {}).pet;
      if (petMayChu) {
        cfg = chuanHoa(Object.assign({}, cfg, petMayChu));
        ghiLocal(); apDung(); apDungTrangThai(); chay();
      }
      veDauAn();
    }).catch(function () {});
  }

  // Chân dung TĨNH: cùng hình dáng, cùng bảng màu, cùng dáng liếc với con pet đang sống.
  // Dùng cho ô xem thử trên trang Linh vật, cho dấu ấn trên thanh bên và cho avatar trợ lý.
  //
  // `opts`:
  //   vanh  - vẽ thêm VÀNH QUỸ ĐẠO bao ngoài (mặc định không). Bật ở ô chọn Hình dáng trang
  //           Linh vật để mấy hình đó trông đúng con pet thật; TẮT ở avatar trợ lý và ở dấu
  //           ấn cỡ nhỏ, vì dưới 30px cái vành chỉ còn là một vệt bẩn quanh hình.
  //   liecX / liecY - đổi HƯỚNG LIẾC (đơn vị viewBox, gốc là chéo lên phải). Ô xem thử lớn
  //           trong cài đặt trợ lý liếc sang trái và hơi xuống, theo yêu cầu của chủ dự án.
  //   mat   - khoá MÀU MẮT ("den" / "trang"). Chỗ nào vẽ CON PET thì truyền vào để chân dung
  //           khớp với con pet sống; bỏ trống (avatar trợ lý) thì suy tự động từ độ chói thân.
  function chanDung(shape, palette, opts) {
    var o = opts || {};
    var d = (SHAPES[shape] || SHAPES.circle).d;
    var tone = (PALETTES[palette] || PALETTES.amber)[sang() ? "sun" : "moon"];
    var mat = MAU_MAT[o.mat] || mauMatTuDong(tone[0]);
    var lx = o.liecX === undefined ? LIEC_X : Number(o.liecX);
    var ly = o.liecY === undefined ? LIEC_Y : Number(o.liecY);
    var ex = 160 + lx, ey = 160 + ly;
    // Vành dùng CHUNG path với thân rồi phóng 1,1 lần quanh tâm, y hệt con pet sống (xem
    // .pet-ring trong style.css). Khai một hình, hai chỗ không bao giờ lệch dáng nhau.
    var vanh = o.vanh
      ? '<path d="' + d + '" fill="none" stroke="' + tone[1] + '" stroke-width="5" ' +
        'stroke-linecap="round" transform="translate(160 160) scale(1.14) translate(-160 -160)"/>'
      : "";
    // Khung NỚI RA khi có vành, giữ nguyên khi không: hình tam giác phóng 1,14 lần cộng nửa
    // nét vẽ chạm tới 274, tràn khỏi khung cũ (58..262). Nới cho mọi chân dung thì avatar trợ
    // lý và dấu ấn đang dùng tự nhiên bé lại, đổi diện mạo một chỗ không ai yêu cầu.
    return '<svg viewBox="' + (o.vanh ? "42 42 236 236" : "58 58 204 204") + '" aria-hidden="true">' + vanh +
      '<path d="' + d + '" fill="' + tone[0] + '"/>' +
      '<ellipse cx="' + (ex - 15) + '" cy="' + ey + '" rx="7.2" ry="17.5" fill="' + mat + '"/>' +
      '<ellipse cx="' + (ex + 15) + '" cy="' + ey + '" rx="7.2" ry="17.5" fill="' + mat + '"/></svg>';
  }

  // ---- DẤU ẤN trên thanh bên ----
  // Bật linh vật thì chỗ logo hiện chính khuôn mặt ấy, để cả app nói cùng một nhân dạng.
  // TẮT linh vật, HOẶC người dùng đã tải logo riêng lên, thì trả lại thẻ <img src="/brand-logo">
  // nguyên bản: logo của người ta thì người ta quyết, một con vật không được đè lên.
  // Chỉ thay RUỘT của ô dấu ấn, không thay cả khối thương hiệu: chữ "JAVIS OS" nằm cạnh đó
  // trong cùng khối, thay cả khối là mỗi lần đổi hình dáng hay bảng màu lại xoá mất chữ.
  var LO_DAU_AN = ".rail-brand .brand-mark, .brand .brand-icon";
  var _logoRieng = false;      // người dùng đã tải logo riêng lên chưa
  function dungDauAn() { return !!cfg.enabled && !_logoRieng; }
  function veDauAn() {
    var dung = dungDauAn();
    document.querySelectorAll(LO_DAU_AN).forEach(function (o) {
      if (o.dataset.brandGoc === undefined) o.dataset.brandGoc = o.innerHTML;
      if (dung) {
        o.classList.add("brand-pet");
        o.innerHTML = chanDung(cfg.shape, cfg.palette, { mat: cfg.eye });
      } else if (o.classList.contains("brand-pet")) {
        o.classList.remove("brand-pet");
        o.innerHTML = o.dataset.brandGoc;
      }
    });
  }

  window.JavisPet = {
    setState: setState,
    setCfg: setCfg,
    setEnabled: setEnabled,
    get: function () { return Object.assign({}, cfg); },
    shapes: function () { return SHAPES; },
    sizes: function () { return SIZES; },
    palettes: function () { return PALETTES; },
    toneOf: function (ten) { return PALETTES[ten] ? PALETTES[ten][sang() ? "sun" : "moon"] : null; },
    // Cho trang Cài đặt hoà cấu hình từ máy chủ vào (localStorage chỉ là bản nhớ tạm cho
    // lần mở đầu, máy chủ mới là nguồn theo NGƯỜI).
    hydrate: function (o) {
      if (!o || typeof o !== "object") return;
      cfg = chuanHoa(Object.assign({}, cfg, o));
      ghiLocal();
      if (el) { apDung(); apDungTrangThai(); chay(); }
      veDauAn();
    },
    // branding.js gọi khi người dùng tải logo riêng lên hay khôi phục logo mặc định.
    setLogoRieng: function (rieng) { _logoRieng = !!rieng; veDauAn(); },
    // Ô xem thử trên trang Linh vật, và DẤU ẤN thay cho logo trên thanh bên: cùng một hàm,
    // vì hai chỗ đó phải là cùng một khuôn mặt.
    previewSvg: chanDung,
    markSvg: function () { return chanDung(cfg.shape, cfg.palette, { mat: cfg.eye }); },
    // Danh sách màu mắt cho ô chọn ở trang Linh vật. Trả khoá + mã màu để chỗ vẽ khỏi phải
    // khai lại bảng màu lần thứ hai.
    eyeColors: function () { return Object.assign({}, MAU_MAT); },
    // Thanh bên có đang dùng khuôn mặt linh vật thay cho logo không.
    usingMark: function () { return dungDauAn(); },
    // Lưu NGAY lên máy chủ rồi đọc lại để chắc chắn đã vào (nút Lưu trang Linh vật).
    luu: luu,
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
