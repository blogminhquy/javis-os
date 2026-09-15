/* Linh vật Javis (dashboard/pet.js) - khoá những dây nối hỏng LẶNG LẼ.

       node tests/js/test_linh_vat.js

   Con pet không có lỗi nào lên console khi nó sai: nó chỉ đơn giản là ngồi im, hay nhìn thẳng
   thay vì liếc, hay trơ ra một biểu cảm trong khi Javis đang nghĩ. Nên những thứ dưới đây phải
   có test, không thể trông vào việc nhìn màn hình:

     1. MỌI lớp trạng thái mà app.js có thể bắn qua setOrbState đều có mục trong STATES.
        Thiếu một mục là pet rơi về "idle" trong im lặng: đang lỗi mà mặt vẫn bình thản.
     2. Dáng liếc là CHỮ KÝ của nhân vật: lúc nghỉ mắt phải lệch lên trên bên phải, và biên
        đảo mắt phải nhỏ hơn chính dáng liếc (không thì có lúc nó gần như nhìn thẳng).
     3. Lúc nép ở mép, hai mắt phải né sang nửa thân CÒN NHÌN THẤY.
     4. Dấu ấn thay logo phải nhường chỗ cho logo riêng của người dùng.
     5. Trang "pet" phải được khai đủ ở cả bốn sổ đăng ký, không thì lệnh bằng lời gọi hụt.

   KHÔNG dùng ký tự em dash. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const pet = read("dashboard/pet.js");
const app = read("dashboard/app.js");
const html = read("dashboard/index.html");
const css = read("dashboard/style.css");
const console_js = read("dashboard/console.js");
const uiActions = read("dashboard/ui-actions.js");
const uiTargets = read("server/ui_targets.py");
const branding = read("dashboard/branding.js");
const vi = JSON.parse(read("dashboard/i18n/vi.json"));
const en = JSON.parse(read("dashboard/i18n/en.json"));

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- 1. Trạng thái: app.js bắn gì thì pet.js phải đỡ được cái đó ----
check("app.js đẩy trạng thái orb sang pet", /JavisPet\.setState\(state \|\| "idle"\)/.test(app));
// ORB_LABEL trong app.js là NGUỒN của mọi lớp trạng thái. Đọc thẳng từ đó thay vì chép lại:
// chép là tạo ra chỗ thứ ba để lệch.
const orbBlock = app.slice(app.indexOf("const ORB_LABEL = {"));
const orbClasses = [...orbBlock.slice(0, orbBlock.indexOf("\n};")).matchAll(/:\s*\["([a-z_]*)"/g)]
  .map(m => m[1] || "idle");
check("đọc được danh sách lớp orb từ app.js (" + orbClasses.length + ")", orbClasses.length >= 8);
const petStates = pet.slice(pet.indexOf("var STATES = {"));
orbClasses.forEach(c => {
  check("STATES của pet có '" + c + "'", new RegExp("^\\s*" + c + ":\\s*\\{", "m").test(petStates));
});

// ---- 2. Dáng liếc ----
const liecX = +(pet.match(/var LIEC_X = (-?[\d.]+)/) || [])[1];
const liecY = +(pet.match(/LIEC_Y = (-?[\d.]+)/) || [])[1];
const tamX = +(pet.match(/var TAM_X = (-?[\d.]+)/) || [])[1];
const tamY = +(pet.match(/TAM_Y = (-?[\d.]+)/) || [])[1];
check("có dáng liếc LIEC_X / LIEC_Y", Number.isFinite(liecX) && Number.isFinite(liecY));
check("lúc nghỉ mắt liếc sang PHẢI (LIEC_X > 0)", liecX > 0);
check("lúc nghỉ mắt liếc LÊN TRÊN (LIEC_Y < 0)", liecY < 0);
// Tầm đưa mắt phải RỘNG HƠN dáng liếc, không thì con trỏ kéo mắt sang trái không nổi và
// "nhìn theo con trỏ" thành lời nói suông.
check("tầm đưa mắt rộng hơn dáng liếc", tamX > Math.abs(liecX) && tamY > Math.abs(liecY));
// Mắt không được trôi ra ngoài thân: thân bán kính 78 quanh tâm 160, nửa khoảng cách hai mắt
// 15, bán trục ngang của mắt lớn nhất 9.2.
check("đưa mắt hết tầm vẫn nằm trong thân", tamX + 15 + 9.2 < 78 && tamY + 22.5 < 78);
const nghi = pet.match(/NGHI_X = LIEC_X \/ TAM_X, NGHI_Y = LIEC_Y \/ TAM_Y/);
check("dáng nghỉ quy từ dáng liếc, không gõ lại số", !!nghi);
const jitter = [...pet.matchAll(/liecDich[XY] = kep\(NGHI_[XY] \+ \(Math\.random\(\) \* 2 - 1\) \* ([\d.]+)/g)]
  .map(m => +m[1]);
check("biên đảo mắt nhỏ hơn dáng nghỉ (giữ được chữ ký)",
  jitter.length === 2 && jitter[0] < Math.abs(liecX / tamX) && jitter[1] < Math.abs(liecY / tamY));
check("rời chuột thì trôi về dáng liếc chứ không về giữa", /if \(ranh\) \{\s*\n\s*if \(now > liecLuc\)/.test(pet));
check("chân dung tĩnh dùng đúng dáng liếc", /var ex = 160 \+ LIEC_X, ey = 160 \+ LIEC_Y;/.test(pet));

// ---- 3. Nép ở mép: mắt né sang nửa còn nhìn thấy ----
check("nép bên phải thì mắt dồn sang TRÁI và ngược lại",
  /var tam = cfg\.side === "right" \? -34 : 34;/.test(pet));
check("nép thì ghìm tầm mắt lại", /var ghim = el\.dataset\.out === "1" \? 1 : 0\.45;/.test(pet));
check("biểu cảm tả MỘT con mắt quanh gốc, không phải cả cặp",
  !/EYES = \{[\s\S]{0,200}cx="145"/.test(pet));

// ---- 4. Trạng thái ra/vào tách rời khỏi menu ----
check("có hai trạng thái tách rời data-out và data-menu",
  /el\.dataset\.out = ra \? "1" : "0";/.test(pet) && /el\.dataset\.menu = mo \? "1" : "0";/.test(pet));
check("bấm ra chỗ khác CHỈ đóng menu, không kéo pet vào",
  /if \(!el \|\| el\.hidden \|\| el\.dataset\.menu !== "1"\) return;\s*\n\s*if \(!el\.contains\(e\.target\)\) moMenu\(false\);/.test(pet));
check("ném sát mép thì mới nép vào", /raNgoai\(mep > el\.getBoundingClientRect\(\)\.width \* 0\.5\);/.test(pet));
check("css: nép nửa người theo data-out", /\.pet\[data-out="0"\]\[data-side="right"\]/.test(css));
check("css: [hidden] thắng được display:flex", /\.pet\[hidden\], \.pet-menu\[hidden\] \{ display: none; \}/.test(css));
check("css: menu neo tuyệt đối, không nằm trong flex 56px", /\.pet-menu \{[^}]*position: absolute;/.test(css));

// ---- 5. Dấu ấn thay logo ----
check("bật linh vật + chưa có logo riêng thì mới thay logo",
  /function dungDauAn\(\) \{ return !!cfg\.enabled && !_logoRieng; \}/.test(pet));
check("tắt dấu ấn thì trả lại thẻ <img> nguyên bản", /o\.innerHTML = o\.dataset\.brandGoc;/.test(pet));
check("branding.js báo cho pet khi đổi logo", /JavisPet\.setLogoRieng\(rieng\)/.test(branding));
check("branding.js truyền đúng true khi tải lên, false khi khôi phục",
  /bustLogos\(true\);/.test(branding) && /bustLogos\(false\);/.test(branding));
check("css: chỗ logo mang mặt linh vật thì bỏ quầng sáng cam", /\.brand-pet \{ filter: none !important; \}/.test(css));

// ---- 6. Trang "pet" khai đủ ở mọi sổ đăng ký ----
check("console.js: pet trong RAIL_ITEMS", /"usage", "pet",\s*\n\s*\]\.map/.test(console_js));
check("console.js: pet trong nhóm Hệ thống", /ids: \["usage", "settings", "pet", "logs", "account"\]/.test(console_js));
check("console.js: pet có trong VIEW_META", /"usage", "pet"\]\.map\(id =>/.test(console_js));
check("console.js: renderPage định tuyến pet", /if \(id === "pet"\) return renderPetPage\(el\);/.test(console_js));
check("ui-actions.js: pet trong PAGES", /"usage", "pet"\];/.test(uiActions));
check("ui_targets.py: pet trong PAGES", /"usage", "pet",/.test(uiTargets));
check("ui_targets.py: bí danh 'linh vat' trỏ về pet", /"linh vat": "pet"/.test(uiTargets));
check("ui_targets.py: nhóm tro_ly đã bỏ", !/"tro_ly", "bo_nao"/.test(uiTargets));
check("ui_targets.py: bí danh 'tro ly' của NHÓM nay trỏ sang bo_nao", /"tro ly": "bo_nao"/.test(uiTargets));

// ---- 7. Thanh bên gọn một tầng ----
check("console.js: không còn nhóm tro_ly", !/id: "tro_ly"/.test(console_js));
check("console.js: home và chat nằm trong nhóm Bộ não",
  /ids: \["home", "chat", "files", "learn"\]/.test(console_js));
check("i18n: không còn khoá nhóm tro_ly", vi["nav.group.tro_ly"] === undefined && en["nav.group.tro_ly"] === undefined);
check("i18n: trang home đổi tên thành Đồ thị / Graph",
  vi["page.home.label"] === "Đồ thị" && en["page.home.label"] === "Graph");

// ---- 8. Nạp file và từ điển ----
const iApp = html.indexOf("/static/app.js"), iPet = html.indexOf("/static/pet.js");
const iConsole = html.indexOf("/static/console.js");
check("index.html nạp pet.js", iPet > 0);
check("index.html nạp pet.js SAU app.js và console.js", iPet > iApp && iPet > iConsole);
["page.pet.label", "page.pet.title", "page.pet.sub", "settings.pet", "settings.pet_desc",
 "settings.pet_hint", "settings.pet_on", "settings.pet_off", "settings.pet_shape",
 "settings.pet_color", "settings.pet_missing", "pet.menu.chat", "pet.menu.work",
 "pet.menu.settings", "pet.menu.hide"].forEach(k => {
  check("i18n vi+en có " + k, typeof vi[k] === "string" && typeof en[k] === "string");
});
// Mỗi hình dáng và mỗi bảng màu phải có nhãn dịch, không thì ô chọn hiện trần khoá.
const petSrc = pet.slice(pet.indexOf("var SHAPES = {"), pet.indexOf("var MAC_DINH"));
[...petSrc.matchAll(/key: "(pet\.(?:shape|color)\.[a-z]+)"/g)].forEach(m => {
  check("i18n vi+en có " + m[1], typeof vi[m[1]] === "string" && typeof en[m[1]] === "string");
});

// ---- 9. Cỡ pet ----
const sizes = [...pet.matchAll(/^\s+(\w+):\s*\{ key: "pet\.size\.\w+",\s*px: (\d+) \}/gm)];
check("có bảng cỡ pet (" + sizes.length + " cỡ)", sizes.length >= 3);
check("cỡ mặc định không phải cỡ nhỏ nhất", /size: "vua"/.test(pet));
// Bản đầu để 56px rồi CO XUỐNG 46px trên màn hẹp, chủ dự án báo nhìn bé quá trên iPhone.
// Ngón tay to hơn con trỏ chuột, nên màn hẹp không được thu nhỏ pet.
check("màn hẹp KHÔNG co pet nhỏ lại nữa", !/\.pet, \.pet-body \{ width: 46px/.test(css));
check("cỡ đi qua biến CSS --pet-size", /width: var\(--pet-size/.test(css)
  && /setProperty\("--pet-size"/.test(pet));
check("màn hẹp vẫn có trần theo bề ngang màn", /min\(var\(--pet-size[^)]*\), 24vw\)/.test(css));
check("server nhận khoá size", /for k in \("shape", "palette", "side", "size"\)/.test(read("server/main.py")));
[...pet.matchAll(/key: "(pet\.size\.\w+)"/g)].forEach(m => {
  check("i18n vi+en có " + m[1], typeof vi[m[1]] === "string" && typeof en[m[1]] === "string");
});

// ---- 10. Tin KHÔNG bốc hơi khi mất WebSocket ----
// Đây là lỗi thật chủ repo báo 15/09 trên iPhone: đổi khung chat, nói một câu, chữ nhận đúng
// mà không có gì vào khung chat. Nguyên nhân kép: sendMessage `return` trần khi socket đứt,
// và trạng thái "ĐANG KẾT NỐI LẠI" nằm trên orb - orb thì bị ẩn hẳn ở trang Trò chuyện.
check("socket đứt thì GIỮ tin lại, không return trần",
  /if \(!ws \|\| ws\.readyState !== WebSocket\.OPEN\) \{ giuTinKhiDutMang\(msg\); return; \}/.test(app));
check("không còn nhánh vứt tin lặng lẽ", !/WebSocket\.OPEN\) return;/.test(app));
check("nối lại được thì gửi hàng đợi",
  /guiTinDutMang\(\);/.test(app) && /turn\.wsUp\(\)\);[\s\S]{0,80}baoDutMang\(false\);/.test(app));
check("chờ mãi không nối lại thì TRẢ CHỮ về ô nhập",
  /function traTinDutMang\(\)[\s\S]{0,400}chatInput\.value = ds\.concat/.test(app));
check("hàng đợi có trần, không phình vô hạn", /if \(_tinDutMang\.length >= 5\) _tinDutMang\.shift\(\);/.test(app));
check("mất mạng được báo NGAY TRONG khung chat (orb bị ẩn ở trang Trò chuyện)",
  /function baoDutMang\(dut\)/.test(app) && /showActivity\(Icons\.warn\(window\.t\("app\.ws_mat_ket_noi"\)\)\)/.test(app));
check("chờ một nhịp mới báo, khỏi nhấp nháy khi iOS ẩn trang", /\}, 2500\);/.test(app));
check("ws.onclose gọi baoDutMang", /ws\.onclose = \(\) => \{[\s\S]{0,200}baoDutMang\(true\);/.test(app));
["app.ws_mat_ket_noi", "app.ws_giu_tin", "app.ws_tra_tin"].forEach(k => {
  check("i18n vi+en có " + k, typeof vi[k] === "string" && typeof en[k] === "string");
});

// ---- 11. Không có emoji trong menu (test_icons cũng bắt, nhưng bắt ở đây thì đọc ra lý do) ----
check("menu dùng icon lucide chứ không phải emoji",
  /var icon = function \(ten\) \{ return window\.ic \? window\.ic\(ten\) : ""; \};/.test(pet)
  && /ic: icon\("message-circle"\)/.test(pet));

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - linh vật Javis");
