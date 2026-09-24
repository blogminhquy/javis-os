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
    // NGÔI SAO MŨM MĨM. Sao tiêu chuẩn có bán kính trong bằng 0,38 bán kính ngoài, ra năm cái
    // gai nhọn; ở đây là 52/86 tức 0,60, nên cánh ngắn và bè, thân phình ra như một cục bông.
    // Cả mười góc đều bo bằng cung Q, đỉnh cánh bo mềm và chỗ hõm giữa hai cánh bo sâu hơn.
    // Đừng đẩy bán kính trong lên nữa: dựng thử tới 0,65 thì cánh tan hết, nhìn ra ngũ giác
    // mọc bướu chứ không còn là ngôi sao (đã dựng ảnh so từng bước trước khi chốt con số này).
    // CỠ (0.64.40): cả đường đã phóng 1,17 lần quanh tâm 160/160. Bản đầu có đầu cánh chạm bán
    // kính 86 như vòng tròn, nhưng sao thì hõm vào giữa các cánh nên chỉ phủ được 13.120 điểm
    // ảnh, trong khi tròn 19.116, ngũ giác 18.438. Mắt cùng một cỡ cho mọi hình, nên trên sao
    // mắt trông to quá khổ (chủ dự án báo 24/09). Phóng 1,17 thì diện tích xấp xỉ ngũ giác, và
    // đầu cánh (bán kính khoảng 100) vẫn nằm trong khung chân dung kể cả khi có vành 1,14 lần.
    // Đừng phóng quá 1,17: vành của ô chọn hình dáng bắt đầu chạm mép khung (bán kính 118).
    star:     { key: "pet.shape.star",     d: "M145 81 Q160 59.4 175 81 L177.9 85.1 Q195.8 110.7 225.8 119.9 L230.6 121.3 Q255.7 128.9 239.8 149.8 L236.8 153.8 Q217.9 178.8 218.5 210.1 L218.6 215.1 Q219.1 241.4 194.3 232.8 L189.6 231.1 Q160 220.8 130.4 231.1 L125.7 232.8 Q100.9 241.4 101.4 215.1 L101.5 210.1 Q102.1 178.8 83.2 153.8 L80.2 149.8 Q64.3 128.9 89.4 121.3 L94.2 119.9 Q124.2 110.7 142.1 85.1 Z" },
  };

  // Mỗi bảng màu tự mang cả hai tông: [thân, vành quỹ đạo, dự phòng]. Tông theo giao diện đang bật
  // (javisTheme), nên pet không bao giờ chói lên giữa nền tối.
  //
  // TÔNG TỐI SUY TỪ TÔNG SÁNG, GIỮ NGUYÊN SẮC (0.59.36). Bản cũ đặt tay từng cặp, và tay thì
  // trôi: tông tối của `amber` rơi từ 30 độ (cam) sang 43 độ (vàng), nên chọn "Hổ phách" ở
  // giao diện tối lại ra một con pet vàng. Tệ hơn, cả 12 tông tối đều bị đẩy lên dải sáng
  // 63-83% và độ bão hoà bị gọt, thành ra màu nào cũng hoá pastel nhợt na ná nhau. Người dùng
  // báo 18/09 đúng hai câu: "bảng màu hơi đơn điệu, các màu sắc không thay đổi rõ rệt" và
  // "rất thích linh vật màu cam mà không có" - màu cam CÓ SẴN, chỉ là giao diện tối nuốt mất.
  //
  // Nay tông tối tính bằng công thức từ chính tông sáng: GIỮ NGUYÊN SẮC, hạ bão hoà 12%, đưa
  // độ sáng về dải 58-78%. Nhờ giữ sắc mà cam ra cam; nhờ dải sáng THẤP HƠN bản cũ mà nó còn
  // đỡ chói hơn trước, tức nỗi lo cũ không bị đánh đổi. Tông SÁNG giữ nguyên không đụng tới,
  // nên ai đang dùng giao diện sáng không thấy gì đổi khác.
  //
  // Đổi một ô màu ở đây thì SỬA CẢ HAI TÔNG cho khớp công thức, đừng chỉ sửa một bên.
  var PALETTES = {
    amber:      { key: "pet.color.amber",      sun: ["#F28C28", "#F7C98F", "#F7E3CF"], moon: ["#EBA35D", "#EEC297", "#2D251D"] },
    pearl:      { key: "pet.color.pearl",      sun: ["#E3DCCF", "#B8AA95", "#EAE4D9"], moon: ["#D4CBBA", "#E7E2DA", "#2D271D"] },
    clay:       { key: "pet.color.clay",       sun: ["#B76A4B", "#E5AA87", "#EEDDD2"], moon: ["#BF8771", "#D0AC9D", "#2D221D"] },
    rose:       { key: "pet.color.rose",       sun: ["#CB6576", "#F2ABAE", "#F2DCE0"], moon: ["#D28C98", "#E1BAC0", "#2D1D20"] },
    honey:      { key: "pet.color.honey",      sun: ["#D5A32D", "#F3D381", "#F2E7C8"], moon: ["#D4B05B", "#DEC68F", "#2D281D"] },
    sage:       { key: "pet.color.sage",       sun: ["#639574", "#AAD2A9", "#DDE9DC"], moon: ["#81A78E", "#A6BFAF", "#1E2C23"] },
    jade:       { key: "pet.color.jade",       sun: ["#379E90", "#8FD6C5", "#D7EBE4"], moon: ["#66C1B5", "#95D0C8", "#1D2D2B"] },
    blue:       { key: "pet.color.blue",       sun: ["#548EC5", "#A4CDEB", "#DCE7F0"], moon: ["#7CA5CB", "#AAC3DA", "#1D252D"] },
    lavender:   { key: "pet.color.lavender",   sun: ["#9272C2", "#C9B2E7", "#E8DFF1"], moon: ["#AC96CC", "#CDC0DF", "#231D2D"] },
    pink:       { key: "pet.color.pink",       sun: ["#C67FAB", "#EDB9D6", "#F0DFE9"], moon: ["#D1A2BF", "#E4CCDB", "#2D1D27"] },
    slate:      { key: "pet.color.slate",      sun: ["#7B8794", "#B8C4CD", "#E0E4E8"], moon: ["#969EA7", "#B7BDC3", "#222528"] },
    cocoa:      { key: "pet.color.cocoa",      sun: ["#79604F", "#BFA38A", "#E8DFD5"], moon: ["#A89080", "#C0B0A5", "#2C241E"] },
    // CAM là màu THƯƠNG HIỆU từ 0.64.47: trùng đúng logo (thân #FD6100, viền #FBBA9C, xem
    // dashboard/logo.svg). Tông tối đặt tay rực hơn công thức chung (công thức ra #F59C65, nhạt
    // lệch hẳn logo) nhưng vẫn đúng luật test_pet_bang_mau: cùng sắc, không chói, không nhạt.
    cam:        { key: "pet.color.cam",        sun: ["#FD6100", "#FBBA9C", "#F6DBD0"], moon: ["#F76F1C", "#F2AD8D", "#2D221D"] },
    nang:       { key: "pet.color.nang",       sun: ["#F5D014", "#F6E27E", "#F6EFD0"], moon: ["#ECD14B", "#EDDC87", "#2D2A1D"] },
    chanh:      { key: "pet.color.chanh",      sun: ["#93B12F", "#C0D775", "#E9EFD7"], moon: ["#B1CB5D", "#C6D68F", "#292D1D"] },
    bacha:      { key: "pet.color.bacha",      sun: ["#38B286", "#81D4B6", "#D8EDE6"], moon: ["#63C5A2", "#92D3BB", "#1D2D27"] },
    thanhthien: { key: "pet.color.thanhthien", sun: ["#1EA3C8", "#6BCBE5", "#D4EBF2"], moon: ["#4EBBDA", "#85CCE0", "#1D2A2D"] },
    cham:       { key: "pet.color.cham",       sun: ["#4052C9", "#969FDF", "#D8DBEE"], moon: ["#6A77CC", "#9BA3D9", "#1D1F2D"] },
    tim:        { key: "pet.color.tim",        sun: ["#AD55C3", "#D3A6DE", "#E9D9ED"], moon: ["#BA7CCA", "#D0AAD9", "#2A1D2D"] },
    ruby:       { key: "pet.color.ruby",       sun: ["#D83137", "#E78E91", "#F1D5D6"], moon: ["#D76064", "#E09497", "#2D1D1D"] },
  };

  // Cỡ pet. Từ 0.64.39 cỡ là MỘT CON SỐ px do thanh trượt đặt (chủ dự án muốn kéo cho vừa ý
  // thay vì chọn một trong bốn nấc). Bốn nấc dưới đây vẫn giữ làm MỐC: cấu hình cũ lưu "vua",
  // "rat_lon"... được quy về đúng số px của nấc đó, nên không ai thấy pet mình đổi cỡ sau cập
  // nhật; và thanh trượt đọc tên nấc gần nhất ra làm nhãn.
  // Mặc định 72 (nấc "vua") chứ không phải nấc nhỏ nhất: bản đầu để 56px và trên điện thoại
  // còn co xuống 46px, chủ dự án báo nhìn bé quá, nhất là trên iPhone.
  var CO_MIN = 44, CO_MAX = 150;
  var SIZES = {
    nho:  { key: "pet.size.nho",  px: 52 },
    vua:  { key: "pet.size.vua",  px: 72 },
    lon:  { key: "pet.size.lon",  px: 96 },
    rat_lon: { key: "pet.size.rat_lon", px: 124 },
  };
  // Màn hẹp KHÔNG thu nhỏ nữa. Ngược lại: ngón tay to hơn con trỏ chuột, và màn hình bé thì
  // một chấm 52px còn khó thấy hơn trên màn rộng. Giữ nguyên cỡ đã chọn.

  // MÀU MẮT do người dùng chọn. Trước đây con số này suy tự động từ độ chói của thân (xem
  // mauMatTuDong), nhưng chủ dự án muốn tự quyết - "tự động" thì không ai đoán được nó ra gì.
  // Avatar trợ lý KHÔNG theo lựa chọn này: chúng là nhân dạng khác, vẫn suy tự động.
  //
  // Từ 0.59.36 có bảy màu thay vì hai. Mắt là TOÀN BỘ chỗ diễn cảm xúc của nhân vật này (không
  // có miệng), nên màu mắt đổi tính cách mạnh hơn cả màu thân. Năm màu thêm đều ĐẬM và bão hoà
  // cao: con ngươi phải đọc ra là con ngươi trên mọi thân, kể cả thân sẫm nhất (cocoa). Thêm
  // màu nhạt vào đây thì trên thân sáng nó biến mất và khuôn mặt thành trống trơn.
  // Mỗi màu mang theo KHOÁ i18n của nó, đúng cấu trúc của SHAPES/SIZES/PALETTES. Giao diện
  // tra `mats[k].key` chứ KHÔNG ghép `"pet.eye." + k`: bộ quét i18n chỉ nhận ra khoá khi nó
  // được viết nguyên văn ngay trong lời gọi dịch, nên khoá ghép chuỗi lọt lưới và một màu
  // thiếu nhãn sẽ đi thẳng ra mắt người dùng mà không test nào kêu.
  //
  // Từ 0.64.39 rút về HAI màu sẵn (đen, trắng) cộng một ô MÀU TỰ CHỌN theo mã màu. Năm màu
  // đậm của 0.59.36 thành thừa khi người dùng gõ được mã bất kỳ, và bảy chấm tròn làm hàng
  // chọn rối hơn giá trị chúng mang lại. Ai đang dùng một trong năm màu đó thì được quy sang
  // "custom" mang đúng mã cũ (xem MAT_CU), nên con pet của họ không đổi màu mắt sau cập nhật.
  var MAU_MAT = {
    den:   { key: "pet.eye.den",   mau: "#201e1e" },
    trang: { key: "pet.eye.trang", mau: "#ffffff" },
  };
  var MAT_CU = { nau: "#5a3a28", xanh: "#2a62b0", ngoc: "#16806f", tim: "#6f45a8", vang: "#c2870f" };

  // CỠ MẮT. Hệ số nhân vào bán kính con mắt, áp cho MỌI hình dáng chứ không riêng hình nào.
  // Mắt là toàn bộ chỗ diễn cảm xúc của nhân vật này (không có miệng), nên cho người dùng
  // kéo to lên là đổi hẳn tính cách: mắt thường thì điềm đạm, mắt rất to thì ngây thơ.
  // Đừng vượt quá 1,5: bản dựng thử ở 1,7 thì hai con mắt chạm nhau ở giữa mặt, và lúc pet
  // nép vào mép màn hình (hai mắt dồn sang nửa thân còn thấy) chúng chồng lên nhau hẳn.
  //
  // Từ 0.64.39 cũng là thanh trượt: cỡ mắt là MỘT HỆ SỐ trong [MAT_MIN, MAT_MAX]. Ba nấc dưới
  // đây còn lại làm mốc quy đổi cấu hình cũ và làm nhãn. Cho xuống 0,8 (mắt nhỏ, điềm tĩnh);
  // trần vẫn 1,5 vì lý do ở trên.
  var MAT_MIN = 0.8, MAT_MAX = 1.5;
  var EYE_SIZES = {
    thuong:  { key: "pet.eyesize.thuong", k: 1 },
    to:      { key: "pet.eyesize.to",     k: 1.25 },
    rat_to:  { key: "pet.eyesize.rat_to", k: 1.5 },
  };
  // `color` / `eyeColor` là mã màu của ô TỰ CHỌN. Chúng nằm sẵn trong cấu hình kể cả khi đang
  // dùng màu có sẵn, để bấm lại ô tự chọn là ra đúng màu lần trước chứ không về một màu lạ.
  // Mặc định là LINH VẬT CHÍNH THỨC: ngôi sao màu cam, trùng logo (chủ dự án chốt 24/09, 0.64.47).
  var MAC_DINH = { enabled: true, shape: "star", palette: "cam", side: "right", pos: 0.62, size: 72, eye: "den", eyeSize: 1, color: "#fd6100", eyeColor: "#2a62b0" };

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
  var NGHI_Y = LIEC_Y / TAM_Y;
  // Hướng liếc lúc nghỉ đi theo MÉP đang nép: nép mép phải thì liếc sang TRÁI, nép mép trái
  // thì liếc sang PHẢI, tức luôn nhìn VÀO TRONG màn hình. Trước 0.59.11 chỗ này là một hằng số
  // luôn dương, nên con pet nép ở mép phải lại nhìn trổ ra ngoài viền màn hình, trông như đang
  // quay lưng lại với trang đang đọc.
  function nghiX() { return (cfg.side === "left" ? LIEC_X : -LIEC_X) / TAM_X; }

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
    // ---- Thêm ở 0.64.39: cho pet sống động hơn khi không bật mic ----
    // ĐÃ BẮT ĐƯỢC GIỌNG: mắt mở to và tròn hơn cả "curious". Trước đây đang chờ nghe với đang
    // nghe thấy người ta nói là CÙNG một dáng, nên nói xong một câu mà không biết pet có nghe.
    hearing:    '<ellipse cy="-2" rx="9.6" ry="23.5"/>',
    // Đang VIẾT câu trả lời (chữ đang chảy về): hai mắt nhìn xuống như đang cắm cúi ghi.
    viet:       '<ellipse cy="7" rx="7" ry="14.5"/>',
    // Nháy mắt: mắt trái cong như cười, mắt phải vẫn mở.
    wink:       ['<path class="pet-line" d="M-9 3 Q0 -7 9 3"/>', '<ellipse rx="7.2" ry="17.5"/>'],
    // Ngạc nhiên: hai mắt tròn xoe.
    surprised:  '<ellipse rx="10.5" ry="12.5"/>',
    // Mắt tim: bấm vuốt ve liên tục.
    love:       '<path d="M0 11 C-15 0 -13 -13 -5.5 -13 C-2 -13 0 -10 0 -7.5 C0 -10 2 -13 5.5 -13 C13 -13 15 0 0 11 Z"/>',
    // GỒNG SỨC ><: nhắm tịt hai mắt thành hai mũi nhọn chụm vào giữa, như đang rặn ra câu trả
    // lời (chủ dự án xin 24/09). Mắt trái ">" , mắt phải "<". Đi kèm cú rung nhẹ (data-mat).
    gang:       ['<path class="pet-line" d="M-8 -9 L6 0 L-8 9"/>', '<path class="pet-line" d="M8 -9 L-6 0 L8 9"/>'],
    // Chóng mặt: bấm dồn dập quá.
    dizzy:      '<path class="pet-line" d="M-8 -8 L8 8 M8 -8 L-8 8"/>',
  };

  // ĐANG NGHĨ thì hai con mắt ĐỔI QUA ĐỔI LẠI giữa hai dáng, không đứng yên một dáng:
  //   "thinking" = liếc chéo lên, như đang lục trí nhớ;
  //   "nghi"     = hai gạch ngang, dáng lim dim nghĩ ngợi (chủ dự án chốt 15/09 là thích dáng
  //                này nhất, và đồng ý để nó luân phiên với dáng trên).
  // Mỗi dáng giữ chừng một giây rưỡi rồi đổi. Muốn nó ĐỨNG YÊN ở hai gạch ngang thì bỏ mảng
  // này còn một phần tử "nghi" - vòng vẽ tự thôi đổi, không phải sửa chỗ nào khác.
  //   "gang"     = >< gồng sức như đang rặn (0.64.40, chủ dự án xin). Giữ NGẮN nhất: gồng lâu
  //                trông như đau chứ không còn là cố gắng.
  var NGHI_MAT = ["thinking", "nghi", "gang"];
  var NGHI_LAU = [1500, 1200, 1000];   // mỗi dáng giữ bao lâu (ms), cộng thêm một chút ngẫu nhiên

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
    // Mic ĐÃ BẮT được tiếng nói (voice-turn: user_speaking). Vành quay nhanh gấp rưỡi và dày
    // vệt hơn lúc chờ nghe, cộng mắt mở to, cộng một cú gật nhẹ mỗi lần có chữ mới (xem nghe()).
    hearing:      { eye: "hearing",    ring: 64,  dash: "30 15",   mo: 1 },      // 8 vệt, dồn dập
    // Đang VIẾT câu trả lời: chữ đã bắt đầu chảy về nhưng lượt chưa xong.
    writing:      { eye: "viet",       ring: 30,  dash: "72 18",   mo: 1 },      // 4 vệt dài
    waiting:      { eye: "curious",    ring: 12,  dash: "30 60",   mo: 1 },      // 4 vệt, thưa hơn
    thinking:     { eye: "thinking",   ring: 108, dash: "100 80",  mo: 1 },      // 2 vệt dài, quay nhanh
    speaking:     { eye: "happy",      ring: 18,  dash: "56 34",   mo: 1 },      // 4 vệt, dày dặn
    paused:       { eye: "sleepy",     ring: 4,   dash: "286 74",  mo: 0.35 },
    reconnecting: { eye: "suspicious", ring: 40,  dash: "24 36",   mo: 1 },      // 6 vệt ngắn: bồn chồn
    error:        { eye: "sad",        ring: 0,   dash: "286 74",  mo: 1 },
  };

  // ---- PHẢN ỨNG TẠM (0.64.39) ----
  // Mỗi phản ứng là một biểu cảm giữ trong `ms` rồi trả về đúng trạng thái thật, kèm một cú
  // cử động của cả thân (`anim`, xem .pet[data-anim] trong style.css). Không phản ứng nào đổi
  // trạng thái thật: pet vẫn nói đúng điều orb nói, chỉ là nói có cảm xúc hơn.
  //   click   = bấm vào pet khi nó đã đứng ngoài (bốc ngẫu nhiên một trong mấy dáng vui)
  //   xong    = vừa trả lời xong một lượt: cười tít và nhảy lên một cái
  //   choang  = bấm dồn dập: chóng mặt, lắc lư
  //   thuc    = đang ngủ gật thì có người động vào
  var PHAN_UNG = {
    click:  { mat: ["happy", "wink", "surprised", "love", "gang"], ms: 1300, anim: "squish" },
    xong:   { mat: ["happy"],     ms: 1700, anim: "hop" },
    choang: { mat: ["dizzy"],     ms: 1500, anim: "shake" },
    thuc:   { mat: ["surprised"], ms: 700,  anim: "squish" },
  };
  // Ngồi yên bao lâu thì ngủ gật (ms). Chỉ khi ĐANG NGHỈ: đang nghe, nghĩ, nói thì không ngủ.
  var NGU_SAU = 90000;

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
  var phanUngTen = "";                      // mắt của phản ứng đang diễn, "" = không có
  var choXong = false;                      // đã trả lời xong nhưng còn đang đọc: vui khi đọc xong
  var hoatDongLuc = 0, nguGat = false;      // lần cuối có người động vào, và đang ngủ gật không
  var gatLuc = 0;                           // mốc cú gật khi nghe thấy chữ mới
  var bamLuc = [];                          // mốc mấy cú bấm gần nhất (bắt bấm dồn dập)
  var diChuot = false;                      // con trỏ đang nằm trên thân pet
  var animTimer = 0;
  var giamChuyenDong = null;

  function t(k, d) {
    try {
      var v = window.t ? window.t(k) : k;
      return (!v || v === k) ? (d || k) : v;
    } catch (e) { return d || k; }
  }
  function kep(n, a, b) { return Math.max(a, Math.min(b, n)); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  // Mã màu hợp lệ thì trả về dạng chuẩn "#rrggbb" (chữ thường), không thì "". Nhận cả "#abc"
  // và thiếu dấu "#", vì người ta hay dán mã màu từ chỗ khác sang theo đủ kiểu.
  function hex(v) {
    var s = String(v == null ? "" : v).trim().replace(/^#/, "").toLowerCase();
    if (/^[0-9a-f]{3}$/.test(s)) s = s.replace(/./g, "$&$&");
    return /^[0-9a-f]{6}$/.test(s) ? "#" + s : "";
  }
  // Cỡ thân: nhận số px hoặc tên nấc cũ ("vua"...), trả về số px đã kẹp.
  function coThan(v) {
    if (typeof v === "string" && SIZES[v]) return SIZES[v].px;
    var n = Number(v);
    return isFinite(n) && n > 0 ? Math.round(kep(n, CO_MIN, CO_MAX)) : MAC_DINH.size;
  }
  // Cỡ mắt: nhận hệ số hoặc tên nấc cũ ("to"...), trả về hệ số đã kẹp, làm tròn 2 chữ số để
  // so sánh với bản máy chủ đọc lại không lệch vì sai số dấu phẩy động.
  function heSo(v) {
    if (typeof v === "string" && EYE_SIZES[v]) return EYE_SIZES[v].k;
    var n = Number(v);
    return isFinite(n) && n > 0 ? Math.round(kep(n, MAT_MIN, MAT_MAX) * 100) / 100 : 1;
  }

  // ---- Màu TỰ CHỌN: suy đủ hai tông từ MỘT mã màu ----
  // Dùng đúng luật đã khoá cho bảng màu có sẵn (test_pet_bang_mau.js): tông tối GIỮ NGUYÊN SẮC,
  // hạ bão hoà 12%, đưa độ sáng về dải 58-78%. Nhờ vậy một màu gõ tay cũng không chói lên giữa
  // nền tối, và cam gõ tay vẫn ra cam ở cả hai giao diện.
  function hsl(h6) {
    var r = parseInt(h6.slice(1, 3), 16) / 255, g = parseInt(h6.slice(3, 5), 16) / 255, b = parseInt(h6.slice(5, 7), 16) / 255;
    var mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, h = 0, s = 0;
    if (mx !== mn) {
      var d = mx - mn;
      s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
      h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
      h *= 60;
    }
    return [h, s, l];
  }
  function tuHsl(h, s, l) {
    s = kep(s, 0, 1); l = kep(l, 0, 1);
    var c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = l - c / 2;
    var v = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
    return "#" + v.map(function (n) { return ("0" + Math.round((n + m) * 255).toString(16)).slice(-2); }).join("");
  }
  function toneTuMau(h6) {
    var c = hsl(h6), sm = c[1] * 0.88, lm = 0.58 + 0.2 * c[2];
    return {
      sun: [h6, tuHsl(c[0], c[1] * 0.85, Math.min(0.8, c[2] + 0.22)), tuHsl(c[0], c[1] * 0.5, 0.9)],
      moon: [tuHsl(c[0], sm, lm), tuHsl(c[0], sm * 0.75, Math.min(0.8, lm + 0.08)), tuHsl(c[0], Math.min(sm, 0.22), 0.15)],
    };
  }
  // Tông [thân, vành, dự phòng] của một bảng màu ở giao diện đang bật. `mau` chỉ dùng khi
  // bảng màu là "custom". Bảng màu lạ rơi về amber, đúng như mọi chỗ vẽ trước nay.
  function toneCua(palette, mau) {
    var tong = sang() ? "sun" : "moon";
    if (palette === "custom" && hex(mau)) return toneTuMau(hex(mau))[tong];
    return (PALETTES[palette] || PALETTES.amber)[tong];
  }
  // Màu mắt từ khoá ("den" / "trang" / "custom" kèm mã). Không khớp gì thì trả "" để chỗ
  // gọi tự quyết (con pet về đen, avatar trợ lý suy tự động theo thân).
  function mauMatCua(eye, mauRieng) {
    if (eye === "custom") return hex(mauRieng);
    return (MAU_MAT[eye] || {}).mau || "";
  }
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
  function mauMatCfg() { return mauMatCua(cfg.eye, cfg.eyeColor) || MAU_MAT.den.mau; }
  // Hệ số cỡ mắt đang chọn.
  function heSoMat() { return heSo(cfg.eyeSize); }
  // Khoảng cách từ tâm cặp mắt ra mỗi con. Mắt to thì NỚI RA, nhưng nới ít hơn mức mắt phình:
  // nới đủ hệ số thì hai con mắt dạt hẳn ra hai bên thái dương, nhìn như một con vật khác.
  // Dựng ảnh so ba cỡ rồi chốt: mũi tên 1 -> 1,5 thì khoảng cách chỉ đi 15 -> 18,5.
  function cachMat(goc) { return goc * (1 + (heSoMat() - 1) * 0.47); }

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
          if (typeof muon[k] === "number") return Math.abs(Number(da[k]) - muon[k]) > 0.001;
          return da[k] !== muon[k];
        });
        return { ok: !lech.length, lech: lech };
      })
      .catch(function () { return { ok: false, lech: [] }; });
  }
  function chuanHoa(o) {
    var c = Object.assign({}, MAC_DINH, o || {});
    if (!SHAPES[c.shape]) c.shape = MAC_DINH.shape;
    c.color = hex(c.color) || MAC_DINH.color;
    c.eyeColor = hex(c.eyeColor) || MAC_DINH.eyeColor;
    if (!PALETTES[c.palette] && c.palette !== "custom") c.palette = MAC_DINH.palette;
    if (c.side !== "left" && c.side !== "right") c.side = MAC_DINH.side;
    c.size = coThan(c.size);
    // Màu mắt cũ (nâu, xanh...) quy sang ô tự chọn mang đúng mã cũ, không rơi về đen.
    if (MAT_CU[c.eye]) { c.eyeColor = MAT_CU[c.eye]; c.eye = "custom"; }
    if (!MAU_MAT[c.eye] && c.eye !== "custom") c.eye = MAC_DINH.eye;
    c.eyeSize = heSo(c.eyeSize);
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
    var tone = toneCua(cfg.palette, cfg.color);
    el.style.setProperty("--pet-face", tone[0]);
    el.style.setProperty("--pet-ring", tone[1]);
    el.style.setProperty("--pet-eye", mauMatCfg());
    el.dataset.side = cfg.side;
    // Cỡ đi bằng BIẾN CSS chứ không phải style.width trực tiếp: menu, viền focus và luật màn
    // hẹp đều ăn theo cùng một con số, khai một chỗ thì không có chỗ nào lệch.
    el.style.setProperty("--pet-size", cfg.size + "px");
    veMat(dangChop ? "blink" : mood);   // đổi mép thì hai mắt dồn sang phía kia
    liecLuc = 0;                        // và chọn lại hướng liếc ngay, xem nghiX()
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

  // Khoảng hở tối thiểu giữa hai mắt (đơn vị viewBox), và bề ngang một con mắt tính từ tâm
  // của nó ra mép xa nhất, kể cả nửa bề dày nét vẽ. Đọc thẳng từ markup trong EYES nên thêm
  // dáng mắt mới là tự được tính, không phải khai bề ngang lần thứ hai.
  var KHE_MAT = 6;
  var _nuaRong = {};
  function nuaRongMat(m) {
    if (_nuaRong[m] !== undefined) return _nuaRong[m];
    var r = 0;
    var el2 = /<ellipse([^>]*)>/.exec(m);
    if (el2) {
      var cx = /cx="(-?[\d.]+)"/.exec(el2[1]), rx = /rx="([\d.]+)"/.exec(el2[1]);
      r = Math.abs(cx ? +cx[1] : 0) + (rx ? +rx[1] : 0);
    }
    var d = /d="([^"]+)"/.exec(m);
    if (d) {
      // Lệnh H chỉ mang toạ độ x; các lệnh còn lại mang cặp (x, y).
      (d[1].match(/[A-Za-z][^A-Za-z]*/g) || []).forEach(function (lenh) {
        var so = (lenh.slice(1).match(/-?[\d.]+/g) || []).map(Number);
        so.forEach(function (v, i) { if (lenh[0] === "H" || i % 2 === 0) r = Math.max(r, Math.abs(v)); });
      });
      if (/pet-line/.test(m)) r += 3.5;   // nửa stroke-width 7 của .pet-line
    }
    return (_nuaRong[m] = r || 10);
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
      var c = cachMat(14);
      a = [tam - c, 0]; b = [tam + c, 0];
    } else {
      var c2 = cachMat(15);
      a = [-c2, 0]; b = [c2, 0];
    }
    var nua = (b[0] - a[0]) / 2;
    // Cỡ mắt đi bằng scale trên chính nhóm đã dịch chuyển, chứ không sửa từng con số trong
    // bảng EYES: mỗi biểu cảm ở đó là một hình riêng (ellipse, path cong, gạch ngang), nhân
    // tay thì phải nhân đúng chín chỗ và cứ thêm một biểu cảm là thêm một chỗ để quên.
    // Dáng mắt đang vẽ gắn lên phần tử để CSS diễn theo (gồng sức thì rung nhẹ).
    if (el) el.dataset.mat = ten;
    // KHÔNG ĐỂ HAI MẮT DÍNH NHAU (0.64.42). Mắt tròn thường chỉ rộng 7,2 mỗi bên nên thừa chỗ,
    // nhưng các dáng NÉT NGANG (chớp mắt, lim dim, ngủ, cười) rộng 9 cộng nửa nét 3,5, mắt tim
    // rộng 15. Lúc nép mép hai mắt dồn sát lại, cỡ mắt to thì phóng thêm, nên hai nét nhắm
    // chạm nhau thành một vạch dài (chủ dự án gửi ảnh 24/09). Đo bề ngang THẬT của từng dáng
    // rồi chỉ co riêng dáng nào không vừa, đủ để còn hở KHE_MAT; dáng vừa thì giữ nguyên cỡ.
    var k = heSoMat();
    var kMax = Math.max(0.5, (nua - KHE_MAT / 2) / Math.max(nuaRongMat(trai), nuaRongMat(phai)));
    var kv = Math.min(k, kMax);
    var co = kv === 1 ? "" : " scale(" + (Math.round(kv * 1000) / 1000) + ")";
    gEyes.innerHTML =
      '<g transform="translate(' + (160 + a[0]) + " " + (160 + a[1]) + ")" + co + '">' + trai + "</g>" +
      '<g transform="translate(' + (160 + b[0]) + " " + (160 + b[1]) + ")" + co + '">' + phai + "</g>";
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
        liecDichX = kep(nghiX() + (Math.random() * 2 - 1) * 0.17, -1, 1);
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

    // Cú GẬT khi nghe thấy chữ mới: phình nhẹ rồi xẹp trong 260ms. Là dấu hiệu "mình đang nghe
    // đây" mà mắt không cần đổi dáng liên tục.
    var gat = gatLuc > now ? (gatLuc - now) / 260 : 0;
    var phinh = gat > 0 ? " scale(" + (1 + Math.sin(gat * Math.PI) * 0.07).toFixed(3) + ")" : "";
    gRig.style.transform = "translate(" + (nhinX * 3.4).toFixed(2) + "px," +
      (nhinY * 2.4 + tho * 0.5 - gat * 3).toFixed(2) + "px)" + phinh;

    // Ngồi không lâu quá thì NGỦ GẬT: mắt lim dim, vành gần như đứng. Có ai động vào (rê
    // chuột, gõ phím) là giật mình tỉnh dậy, xem thucDay().
    if (!nguGat && state === "idle" && !phanUngTen && hoatDongLuc && now - hoatDongLuc > NGU_SAU) {
      nguGat = true; mood = "sleepy"; if (!dangChop) veMat(mood);
      tocDoDich = 2; pRing.style.opacity = "0.3";
      el.dataset.ngu = "1";
    }
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
    if (now > chopLuc && !dangChop && vuiDen < now && !nguGat) {
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
    phanUngTen = "";
    // Đang nghỉ mà con trỏ nằm trên thân: tò mò nhìn lại, không ngồi trơ.
    if (state === "idle" && diChuot) mood = "curious";
    if (state === "idle" && nguGat) mood = "sleepy";
    // Vào lại trạng thái nghĩ thì bắt đầu từ dáng ĐẦU của NGHI_MAT và chờ đủ một nhịp mới đổi.
    // Không đặt lại thì mốc cũ đã trôi qua từ lâu, nên vừa bắt đầu nghĩ là mắt nháy sang dáng
    // kia ngay lập tức, trông như giật.
    nghiPha = 0;
    nghiLuc = (typeof performance !== "undefined" ? performance.now() : 0) + NGHI_LAU[0];
    if (!dangChop) veMat(mood);
    tocDoDich = nguGat && state === "idle" ? 2 : s.ring;
    pRing.style.strokeDasharray = s.dash;
    pRing.style.opacity = String(nguGat && state === "idle" ? 0.3 : s.mo);
    el.dataset.state = state;
  }

  // Diễn một phản ứng tạm (xem PHAN_UNG). Giảm chuyển động thì vẫn đổi mắt, chỉ bỏ cú nhún.
  function dienPhanUng(ten) {
    var p = PHAN_UNG[ten];
    if (!p || !el || el.hidden) return;
    var now = typeof performance !== "undefined" ? performance.now() : 0;
    phanUngTen = p.mat[Math.floor(Math.random() * p.mat.length)];
    mood = phanUngTen;
    if (!dangChop) veMat(mood);
    vuiDen = now + p.ms;                 // vòng vẽ trả về trạng thái thật khi hết giờ
    chopLuc = Math.max(chopLuc, now + p.ms);
    if (p.anim && !(giamChuyenDong && giamChuyenDong.matches)) {
      // Gỡ rồi gắn lại qua một khung hình để hai phản ứng liền nhau vẫn chạy lại hoạt ảnh.
      delete el.dataset.anim;
      clearTimeout(animTimer);
      requestAnimationFrame(function () {
        if (!el) return;
        el.dataset.anim = p.anim;
        animTimer = setTimeout(function () { if (el) delete el.dataset.anim; }, 900);
      });
    }
    chay();
  }

  // Có người động vào (rê chuột, gõ, bấm). Đang ngủ gật thì giật mình tỉnh.
  function thucDay() {
    hoatDongLuc = typeof performance !== "undefined" ? performance.now() : 0;
    if (!nguGat) return;
    nguGat = false;
    if (el) delete el.dataset.ngu;
    if (!el) return;
    tocDoDich = (STATES[state] || STATES.idle).ring;
    if (state === "idle") dienPhanUng("thuc"); else apDungTrangThai();
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
      // Sang mép khác là đổi luôn hướng liếc; chờ hết nhịp đảo mắt (3,6 đến 6,8 giây) thì
      // vừa thả tay ra con pet còn nhìn trổ ra ngoài màn hình một lúc lâu.
      if (el.dataset.side !== cfg.side) { el.dataset.side = cfg.side; veMat(mood); liecLuc = 0; }
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
      // Bấm DỒN DẬP (4 cú trong 1,6 giây) thì chóng mặt. Đếm cả lượt bấm lúc đang nép.
      var bayGio = performance.now();
      bamLuc = bamLuc.filter(function (m) { return bayGio - m < 1600; }).concat(bayGio);
      var choang = bamLuc.length >= 4;
      if (choang) bamLuc = [];
      if (!dangRa) {                       // đang nép: trượt hẳn ra và mở menu, chào một nhịp
        raNgoai(true); moMenu(true);
        mood = "excited"; veMat(mood); vuiDen = bayGio + 1500;
      } else {
        moMenu(el.dataset.menu !== "1");   // đã ở ngoài: bấm chỉ bật tắt menu, không chui vào
        // Và PHẢN ỨNG với cú bấm, không chỉ mở menu im lìm: cười, nháy mắt, tròn mắt, mắt tim.
        // Chỉ khi pet đang rảnh; đang nghe/nghĩ/nói thì giữ nguyên để không nói dối trạng thái.
        if (choang) dienPhanUng("choang");
        else if (state === "idle") dienPhanUng("click");
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
      thucDay();
    }, { passive: true });

    // Con trỏ nằm TRÊN thân: đang rảnh thì tò mò nhìn lại (mắt to hơn một chút).
    nutBody.addEventListener("pointerenter", function () {
      diChuot = true;
      if (state === "idle" && !phanUngTen && !nguGat) { mood = "curious"; if (!dangChop) veMat(mood); }
    });
    nutBody.addEventListener("pointerleave", function () {
      diChuot = false;
      if (state === "idle" && !phanUngTen && !nguGat) apDungTrangThai();
    });

    // Người dùng GÕ vào ô chat: pet quay sang nhìn ô đó, như đang chờ đọc. Nghe ở document
    // (uỷ quyền) vì ô chat có thể được dựng lại, và không cần app.js phải báo gì.
    document.addEventListener("input", function (e) {
      var o = e.target;
      if (!el || el.hidden || !o || o.id !== "chatInput") return;
      thucDay();
      var r = el.getBoundingClientRect(), q = o.getBoundingClientRect();
      if (!r.width || !q.width) return;
      tx = kep((q.left + q.width / 2 - (r.left + r.width / 2)) / 420, -1, 1);
      ty = kep((q.top + q.height / 2 - (r.top + r.height / 2)) / 320, -1, 1);
      chuotLuc = performance.now();
      if (state === "idle" && !phanUngTen && mood !== "curious") { mood = "curious"; if (!dangChop) veMat(mood); vuiDen = chuotLuc + 1800; }
    }, true);
    document.addEventListener("keydown", function () { thucDay(); }, true);

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
    if (s === "error") choXong = false;
    if (s !== "idle" && nguGat) { nguGat = false; if (el) delete el.dataset.ngu; }
    if (el) apDungTrangThai();
    // Trả lời xong trong lúc còn đang đọc thành tiếng: đợi đọc xong (về nghỉ / chờ nghe) mới
    // vui, không thì cú nhảy chen ngang giữa câu đang nói.
    if (choXong && (s === "idle" || s === "listening")) { choXong = false; dienPhanUng("xong"); }
  }
  // app.js báo những việc KHÔNG phải trạng thái orb:
  //   "xong"  = một lượt vừa có câu trả lời (không tính lượt lỗi, lượt bị dừng)
  //   "viet"  = chữ trả lời bắt đầu chảy về (đang nghĩ -> đang viết)
  //   "nghe"  = mic vừa bắt thêm chữ: gật nhẹ một cái
  function react(ten) {
    if (ten === "nghe") {
      gatLuc = (typeof performance !== "undefined" ? performance.now() : 0) + 260;
      thucDay(); chay();
      return;
    }
    if (ten === "viet") {
      if (state === "thinking") setState("writing");
      return;
    }
    if (ten === "xong") {
      if (state === "idle" || state === "listening") dienPhanUng("xong");
      else choXong = true;
      return;
    }
    if (PHAN_UNG[ten]) dienPhanUng(ten);
  }
  // `tam`: đổi TẠM lúc đang kéo thanh trượt hay rê trong bảng chọn màu. Con pet đổi ngay cho
  // người ta thấy, nhưng chưa ghi đi đâu: một lượt kéo bắn vài chục sự kiện input, ghi máy chủ
  // từng cái là vài chục request. Lúc thả tay (sự kiện change) mới gọi lại không có `tam`.
  function setCfg(patch, tam) {
    cfg = chuanHoa(Object.assign({}, cfg, patch || {}));
    if (!tam) { ghiLocal(); ghiServer(); }
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
    hoatDongLuc = performance.now();
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
  //   mau   - mã màu thân khi bảng màu là "custom".
  //   mat   - khoá MÀU MẮT ("den" / "trang" / "custom"), đi cùng `mauMat` là mã của ô tự chọn.
  //           Bỏ trống (avatar trợ lý cũ chưa chọn màu mắt) thì suy tự động từ độ chói thân.
  //   coMat - HỆ SỐ cỡ mắt (hay tên nấc cũ). Bỏ trống thì cỡ thường.
  function chanDung(shape, palette, opts) {
    var o = opts || {};
    var d = (SHAPES[shape] || SHAPES.circle).d;
    var tone = toneCua(palette, o.mau);
    var mat = mauMatCua(o.mat, o.mauMat) || mauMatTuDong(tone[0]);
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
    // Cỡ mắt: cùng hệ số và cùng luật nới khoảng cách với con pet sống, để ô xem thử không
    // bao giờ nói khác cái đang đứng ở mép màn hình.
    // GIỮ NGUYÊN KIỂU SỐ tới lúc nối chuỗi. Bản 0.59.30 làm tròn ngay ở đây bằng toFixed() nên
    // `cach` thành CHUỖI, và `ex + cach` không còn là phép cộng mà là phép nối: con mắt phải
    // nhảy ra toạ độ 17615, tức ngoài khung, nên mọi chân dung tĩnh (ô chọn ở trang Linh vật,
    // dấu ấn thanh bên, avatar trợ lý) chỉ còn MỘT con mắt. Mắt trái vẫn đúng vì phép trừ tự
    // ép chuỗi về số, nên nhìn qua tưởng là cố ý.
    var k = heSo(o.coMat);
    var cach = 15 * (1 + (k - 1) * 0.47);
    var rx = 7.2 * k, ry = 17.5 * k;
    return '<svg viewBox="' + (o.vanh ? "42 42 236 236" : "58 58 204 204") + '" aria-hidden="true">' + vanh +
      '<path d="' + d + '" fill="' + tone[0] + '"/>' +
      '<ellipse cx="' + (ex - cach) + '" cy="' + ey + '" rx="' + rx + '" ry="' + ry + '" fill="' + mat + '"/>' +
      '<ellipse cx="' + (ex + cach) + '" cy="' + ey + '" rx="' + rx + '" ry="' + ry + '" fill="' + mat + '"/></svg>';
  }

  // ---- BỘ CHỈNH DIỆN MẠO, dùng chung cho trang Linh vật và avatar trợ lý (0.64.39) ----
  // Chủ dự án muốn cài đặt avatar trợ lý "lấy nguyên cách triển khai" của linh vật. Nên chỉ có
  // MỘT bộ chỉnh ở đây, hai chỗ cùng gọi: thêm một nút ở linh vật là avatar trợ lý có luôn,
  // không có chuyện hai bản lệch nhau dần theo thời gian.
  //
  // `v`: { shape, palette, color, eye, eyeColor, eyeSize, size }.
  // `opts.size`: có thanh trượt CỠ THÂN không. Avatar trợ lý thì không: cỡ của nó do chỗ vẽ
  //   quyết (26px ở danh sách, 100px ở ô xem thử), người dùng đặt cỡ ở đây là vô nghĩa.
  // `opts.vanh`: ô chọn hình dáng có vẽ vành quỹ đạo không (chỉ linh vật có vành).
  function nacGan(bang, truong, v) {
    var ten = null, lech = Infinity;
    Object.keys(bang).forEach(function (k) {
      var d = Math.abs(bang[k][truong] - v);
      if (d < lech) { lech = d; ten = k; }
    });
    return bang[ten];
  }
  function nhanCo(px) { return t(nacGan(SIZES, "px", px).key) + " · " + px + "px"; }
  function nhanCoMat(k) { return t(nacGan(EYE_SIZES, "k", k).key) + " · " + Math.round(k * 100) + "%"; }
  function nhanMau(v) { return v.palette === "custom" ? t("pet.color.custom", "Tùy chọn") : t((PALETTES[v.palette] || PALETTES.amber).key); }
  function nhanMat(v) { return v.eye === "custom" ? t("pet.eye.custom", "Tùy chọn") : t((MAU_MAT[v.eye] || MAU_MAT.den).key); }
  function chuanLook(v) {
    var c = Object.assign({}, v || {});
    if (!SHAPES[c.shape]) c.shape = MAC_DINH.shape;
    if (!PALETTES[c.palette] && c.palette !== "custom") c.palette = MAC_DINH.palette;
    c.color = hex(c.color) || MAC_DINH.color;
    c.eyeColor = hex(c.eyeColor) || MAC_DINH.eyeColor;
    if (MAT_CU[c.eye]) { c.eyeColor = MAT_CU[c.eye]; c.eye = "custom"; }
    if (!MAU_MAT[c.eye] && c.eye !== "custom") c.eye = MAC_DINH.eye;
    c.eyeSize = heSo(c.eyeSize);
    c.size = coThan(c.size);
    return c;
  }
  function anhCua(v) { return { mau: v.color, mat: v.eye, mauMat: v.eyeColor, coMat: v.eyeSize }; }
  function hinhHtml(v, o) {
    return Object.keys(SHAPES).map(function (k) {
      return '<button type="button" class="pet-pick" data-pet-shape="' + esc(k) + '" aria-pressed="' + (k === v.shape) + '">' +
        chanDung(k, v.palette, Object.assign({ vanh: !!o.vanh }, anhCua(v))) + '<span>' + esc(t(SHAPES[k].key)) + '</span></button>';
    }).join("");
  }
  // Ô MÀU TỰ CHỌN: một chấm tròn bọc <input type="color"> trong suốt phủ kín, bấm vào là bảng
  // chọn màu của hệ điều hành mở ra. Chưa chọn thì chấm là vòng cầu vồng (CSS), đã chọn thì
  // mang đúng màu đó. Kèm ô gõ MÃ MÀU ngay dưới, vì bảng chọn màu trên điện thoại không phải
  // máy nào cũng cho gõ mã, mà chủ dự án cần dán được đúng mã màu thương hiệu.
  function oTuChon(loai, dangChon, mauNen, mauGiaTri, nhan) {
    return '<label class="pet-swatch pet-swatch-custom" data-pet-custom="' + loai + '" aria-pressed="' + dangChon + '" title="' + esc(nhan) + '">' +
      '<i style="' + (dangChon ? "background:" + esc(mauNen) : "") + '"></i>' +
      '<input type="color" data-pet-' + (loai === "eye" ? "eye-color" : "color") + ' value="' + esc(mauGiaTri) + '" aria-label="' + esc(nhan) + '"></label>';
  }
  function oMa(loai, giaTri) {
    return '<label class="pet-hex"><span>' + esc(t("settings.pet_hex", "Mã màu")) + '</span>' +
      '<input type="text" data-pet-' + (loai === "eye" ? "eye-color" : "color") + '-hex value="' + esc(giaTri.toUpperCase()) + '" maxlength="7" ' +
      'spellcheck="false" autocomplete="off" autocapitalize="off"></label>';
  }
  function editorHtml(v0, opts) {
    var o = opts || {}, v = chuanLook(v0);
    var dau = function (tieuDe, the, nhan) {
      return '<div class="settings-card-head pet-ed-head"><b>' + esc(tieuDe) + '</b>' +
        (the ? '<span class="gcard-tag" data-pet-tag="' + the + '">' + esc(nhan) + '</span>' : "") + '</div>';
    };
    var truot = function (attr, min, max, step, gt, nhanDau, nhanCuoi, nhan) {
      return '<div class="pet-range-row"><span>' + esc(nhanDau) + '</span>' +
        '<input type="range" class="pet-range" ' + attr + ' min="' + min + '" max="' + max + '" step="' + step + '" value="' + gt + '" aria-label="' + esc(nhan) + '">' +
        '<span>' + esc(nhanCuoi) + '</span></div>';
    };
    var h = dau(t("settings.pet_shape", "Hình dáng")) +
      '<div class="pet-picker" role="group" data-pet-part="shapes">' + hinhHtml(v, o) + '</div>';
    if (o.size) {
      h += dau(t("settings.pet_size", "Kích cỡ"), "size", nhanCo(v.size)) +
        truot("data-pet-size", CO_MIN, CO_MAX, 2, v.size, t("pet.size.nho", "Nhỏ"), t("pet.size.rat_lon", "Rất lớn"), t("settings.pet_size", "Kích cỡ"));
    }
    var nhanTuChon = t("pet.color.custom", "Tùy chọn");
    h += dau(t("settings.pet_color", "Bảng màu"), "palette", nhanMau(v)) +
      '<div class="pet-picker" role="group">' + Object.keys(PALETTES).map(function (k) {
        var ten = t(PALETTES[k].key);
        return '<button type="button" class="pet-swatch" data-pet-palette="' + esc(k) + '" aria-pressed="' + (k === v.palette) + '" title="' + esc(ten) + '" aria-label="' + esc(ten) + '">' +
          '<i style="background:' + esc(toneCua(k)[0]) + '"></i></button>';
      }).join("") + oTuChon("palette", v.palette === "custom", toneCua("custom", v.color)[0], v.color, nhanTuChon) + '</div>' +
      oMa("palette", v.palette === "custom" ? v.color : (PALETTES[v.palette] || PALETTES.amber).sun[0]);
    h += dau(t("settings.pet_eye", "Màu mắt"), "eye", nhanMat(v)) +
      '<div class="pet-picker" role="group">' + Object.keys(MAU_MAT).map(function (k) {
        var ten = t(MAU_MAT[k].key);
        return '<button type="button" class="pet-swatch" data-pet-eye="' + esc(k) + '" aria-pressed="' + (k === v.eye) + '" title="' + esc(ten) + '" aria-label="' + esc(ten) + '">' +
          '<i style="background:' + esc(MAU_MAT[k].mau) + '"></i></button>';
      }).join("") + oTuChon("eye", v.eye === "custom", v.eyeColor, v.eyeColor, t("pet.eye.custom", "Tùy chọn")) + '</div>' +
      oMa("eye", mauMatCua(v.eye, v.eyeColor) || MAU_MAT.den.mau);
    h += dau(t("settings.pet_eye_size", "Cỡ mắt"), "eyeSize", nhanCoMat(v.eyeSize)) +
      truot("data-pet-eye-size", MAT_MIN, MAT_MAX, 0.05, v.eyeSize, t("pet.eyesize.nho", "Nhỏ"), t("pet.eyesize.rat_to", "Rất to"), t("settings.pet_eye_size", "Cỡ mắt"));
    return h;
  }
  // Lúc KÉO (sự kiện input) chỉ sửa đúng mấy chỗ cần đổi, không vẽ lại cả bộ: vẽ lại là thay
  // luôn cái thanh trượt đang nằm dưới ngón tay, và cú kéo đứt giữa chừng.
  function capNhatNhe(host, v, o) {
    var q = function (s) { return host.querySelector(s); };
    var hinh = q('[data-pet-part="shapes"]');
    if (hinh) hinh.innerHTML = hinhHtml(v, o);
    var nhan = { size: nhanCo(v.size), palette: nhanMau(v), eye: nhanMat(v), eyeSize: nhanCoMat(v.eyeSize) };
    Object.keys(nhan).forEach(function (k) { var e = q('[data-pet-tag="' + k + '"]'); if (e) e.textContent = nhan[k]; });
    host.querySelectorAll("[data-pet-palette]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.petPalette === v.palette)); });
    host.querySelectorAll("[data-pet-eye]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.petEye === v.eye)); });
    [["palette", v.palette === "custom", toneCua("custom", v.color)[0]], ["eye", v.eye === "custom", v.eyeColor]].forEach(function (x) {
      var o2 = q('[data-pet-custom="' + x[0] + '"]');
      if (!o2) return;
      o2.setAttribute("aria-pressed", String(x[1]));
      o2.querySelector("i").style.background = x[1] ? x[2] : "";
    });
    var dangGo = document.activeElement;
    var o3 = q("[data-pet-color-hex]"), o4 = q("[data-pet-eye-color-hex]");
    if (o3 && o3 !== dangGo) o3.value = (v.palette === "custom" ? v.color : (PALETTES[v.palette] || PALETTES.amber).sun[0]).toUpperCase();
    if (o4 && o4 !== dangGo) o4.value = (mauMatCua(v.eye, v.eyeColor) || MAU_MAT.den.mau).toUpperCase();
  }
  var THUOC_TINH_ED = ["data-pet-shape", "data-pet-palette", "data-pet-eye", "data-pet-size", "data-pet-eye-size",
    "data-pet-color", "data-pet-eye-color", "data-pet-color-hex", "data-pet-eye-color-hex"];
  // Gắn bộ chỉnh vào `host` (chỗ đã đổ editorHtml vào). `onChange(patch, tam)`: `tam` = đang
  // kéo / đang rê trong bảng chọn màu, chưa phải lựa chọn cuối (xem setCfg).
  // Nghe bằng ỦY QUYỀN trên host chứ không gắn từng nút: phần hình dáng được vẽ lại liên tục
  // lúc kéo thanh trượt cỡ mắt, gắn từng nút thì mỗi lần vẽ lại là mất hết.
  function editorBind(host, v0, onChange, opts) {
    if (!host || !host.addEventListener) return;
    var st = { v: chuanLook(v0), onChange: onChange, o: opts || {} };
    var daGan = !!host._petEd;
    host._petEd = st;
    if (daGan) return;
    function doi(patch, tam) {
      st.v = chuanLook(Object.assign({}, st.v, patch));
      try { st.onChange && st.onChange(patch, !!tam, Object.assign({}, st.v)); } catch (e) {}
      if (tam) { capNhatNhe(host, st.v, st.o); return; }
      // Lựa chọn cuối: vẽ lại cả bộ cho mọi ô xem thử khớp, rồi trả focus về đúng ô vừa dùng
      // (người dùng bàn phím không bị ném về đầu trang sau mỗi lần chọn).
      var dang = document.activeElement, chon = null;
      if (dang && host.contains(dang)) {
        THUOC_TINH_ED.some(function (a) {
          if (!dang.hasAttribute(a)) return false;
          var gt = dang.getAttribute(a);
          chon = gt ? "[" + a + '="' + gt + '"]' : "[" + a + "]";
          return true;
        });
      }
      host.innerHTML = editorHtml(st.v, st.o);
      if (chon) { var lai = host.querySelector(chon); if (lai) try { lai.focus(); } catch (e) {} }
    }
    function docMa(o5, khoaMau, patchChon, tam) {
      var m = hex(o5.value);
      o5.setAttribute("aria-invalid", m ? "false" : "true");
      if (!m) return;
      var p = {}; p[khoaMau] = m;
      doi(Object.assign(p, patchChon), tam);
    }
    host.addEventListener("click", function (e) {
      var b = e.target.closest("[data-pet-shape], [data-pet-palette], [data-pet-eye]");
      if (!b || !host.contains(b)) return;
      if (b.dataset.petShape) doi({ shape: b.dataset.petShape });
      else if (b.dataset.petPalette) doi({ palette: b.dataset.petPalette });
      else if (b.dataset.petEye) doi({ eye: b.dataset.petEye });
    });
    function nghe(e, tam) {
      var x = e.target;
      if (!x || !x.hasAttribute) return;
      if (x.hasAttribute("data-pet-size")) doi({ size: Number(x.value) }, tam);
      else if (x.hasAttribute("data-pet-eye-size")) doi({ eyeSize: Number(x.value) }, tam);
      else if (x.hasAttribute("data-pet-color")) doi({ palette: "custom", color: x.value }, tam);
      else if (x.hasAttribute("data-pet-eye-color")) doi({ eye: "custom", eyeColor: x.value }, tam);
      // Ô gõ mã: đang gõ thì chỉ xem thử khi mã đã đủ; rời ô (change) mới chốt. Mã sai thì
      // viền đỏ (aria-invalid) và giữ nguyên màu cũ, không đoán bừa.
      else if (x.hasAttribute("data-pet-color-hex")) docMa(x, "color", { palette: "custom" }, tam);
      else if (x.hasAttribute("data-pet-eye-color-hex")) docMa(x, "eyeColor", { eye: "custom" }, tam);
    }
    host.addEventListener("input", function (e) { nghe(e, true); });
    host.addEventListener("change", function (e) { nghe(e, false); });
    // Enter trong ô mã màu thì chốt luôn, khỏi phải bấm ra ngoài.
    host.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && e.target && e.target.matches && e.target.matches("[data-pet-color-hex], [data-pet-eye-color-hex]")) {
        e.preventDefault(); nghe(e, false);
      }
    });
  }

  // ---- DẤU ẤN trên thanh bên ----
  // Bật linh vật thì chỗ logo hiện chính khuôn mặt ấy, để cả app nói cùng một nhân dạng.
  // TẮT linh vật, HOẶC người dùng đã tải logo riêng lên, thì trả lại thẻ <img src="/brand-logo">
  // nguyên bản: logo của người ta thì người ta quyết, một con vật không được đè lên.
  // Chỉ thay RUỘT của ô dấu ấn, không thay cả khối thương hiệu: chữ "JAVIS OS" nằm cạnh đó
  // trong cùng khối, thay cả khối là mỗi lần đổi hình dáng hay bảng màu lại xoá mất chữ.
  var LO_DAU_AN = ".rail-brand .brand-mark, .brand .brand-icon";
  var _logoRieng = false;      // người dùng đã tải logo riêng lên chưa
  // Tuỳ chọn chân dung khớp đúng con pet đang sống: màu thân tự chọn, màu mắt, cỡ mắt.
  function optsCfg() { return { mau: cfg.color, mat: cfg.eye, mauMat: cfg.eyeColor, coMat: cfg.eyeSize }; }
  function dungDauAn() { return !!cfg.enabled && !_logoRieng; }
  function veDauAn() {
    var dung = dungDauAn();
    document.querySelectorAll(LO_DAU_AN).forEach(function (o) {
      if (o.dataset.brandGoc === undefined) o.dataset.brandGoc = o.innerHTML;
      if (dung) {
        o.classList.add("brand-pet");
        o.innerHTML = chanDung(cfg.shape, cfg.palette, optsCfg());
      } else if (o.classList.contains("brand-pet")) {
        o.classList.remove("brand-pet");
        o.innerHTML = o.dataset.brandGoc;
      }
    });
  }

  window.JavisPet = {
    setState: setState,
    react: react,
    setCfg: setCfg,
    setEnabled: setEnabled,
    get: function () { return Object.assign({}, cfg); },
    shapes: function () { return SHAPES; },
    sizes: function () { return SIZES; },
    palettes: function () { return PALETTES; },
    // `mau` chỉ dùng cho bảng màu "custom". Tên lạ trả null, như trước.
    toneOf: function (ten, mau) {
      if (ten === "custom") return hex(mau) ? toneCua(ten, mau) : null;
      return PALETTES[ten] ? PALETTES[ten][sang() ? "sun" : "moon"] : null;
    },
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
    markSvg: function () { return chanDung(cfg.shape, cfg.palette, optsCfg()); },
    // Danh sách màu mắt cho ô chọn ở trang Linh vật. Trả khoá + mã màu để chỗ vẽ khỏi phải
    // khai lại bảng màu lần thứ hai.
    eyeColors: function () { return Object.assign({}, MAU_MAT); },   // {ten: {key, mau}}
    // Các NẤC cỡ mắt (mốc quy đổi + nhãn cho thanh trượt).
    eyeSizes: function () { return EYE_SIZES; },
    // Bộ chỉnh diện mạo DÙNG CHUNG: trang Linh vật và cài đặt avatar trợ lý vẽ cùng một bộ.
    editorHtml: editorHtml,
    editorBind: editorBind,
    // Chuẩn hoá mã màu ("#abc", "ABCDEF" -> "#aabbcc"; sai -> "").
    hex: hex,
    // Thanh bên có đang dùng khuôn mặt linh vật thay cho logo không.
    usingMark: function () { return dungDauAn(); },
    // Lưu NGAY lên máy chủ rồi đọc lại để chắc chắn đã vào (nút Lưu trang Linh vật).
    luu: luu,
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
