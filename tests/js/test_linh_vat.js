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
const railCss = read("dashboard/console.css");
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
// Chân dung nhận được hướng liếc KHÁC (ô xem thử lớn trong cài đặt trợ lý liếc trái-xuống),
// nhưng MẶC ĐỊNH vẫn phải là dáng liếc chữ ký - không thì mọi avatar đổi hướng nhìn một lượt.
check("chân dung tĩnh mặc định vẫn dùng đúng dáng liếc",
  /o\.liecX === undefined \? LIEC_X/.test(pet) && /o\.liecY === undefined \? LIEC_Y/.test(pet)
  && /var ex = 160 \+ lx, ey = 160 \+ ly;/.test(pet));

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
// Chữ "JAVIS OS" nằm CẠNH dấu ấn trong cùng khối .rail-brand. Nếu pet.js thay ruột của cả
// khối thì mỗi lần đổi hình dáng hay bảng màu là chữ bị xoá theo - nên nó phải nhắm vào ô
// con .brand-mark, và index.html phải có sẵn ô con đó.
check("dấu ấn thay ruột ô .brand-mark, không thay cả khối thương hiệu",
  /var LO_DAU_AN = "\.rail-brand \.brand-mark, \.brand \.brand-icon";/.test(pet));
check("index.html: .rail-brand có ô dấu ấn riêng và chữ JAVIS OS",
  /<div class="rail-brand"><span class="brand-mark">/.test(html)
  && /<span class="rail-brand-text">JAVIS <i>OS<\/i><\/span>/.test(html));
check("css: thu gọn thanh bên thì giấu chữ, chỉ còn dấu ấn",
  /\.rail\.collapsed \.rail-brand-text \{ display: none; \}/.test(railCss));
// Quầng sáng cam phải ở ô DẤU ẤN chứ không ở cả khối: filter của cha ăn xuống cả cây con và
// con không gỡ được, để ở .rail-brand là chữ cũng phát sáng cam theo.
check("css: quầng sáng nằm trên .brand-mark, không trên .rail-brand",
  /\.rail-brand \.brand-mark \{[\s\S]{0,120}drop-shadow/.test(railCss)
  && !/\.rail-brand \{[^}]*drop-shadow/.test(railCss));
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
 "settings.pet_color", "settings.pet_missing", "settings.pet_save", "settings.pet_saved",
 "settings.pet_save_fail", "settings.pet_saving", "pet.menu.chat", "pet.menu.agent",
 "pet.menu.workflow", "pet.menu.mic_on", "pet.menu.mic_off", "pet.menu.settings"].forEach(k => {
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
const mainPy = read("server/main.py");
check("server nhận khoá size và khoá màu mắt", /for k in \("shape", "palette", "side", "size", "eye"\)/.test(mainPy));
// "rat_lon" có GẠCH DƯỚI. Luật lọc cũ chỉ tha dấu gạch ngang nên cỡ lớn nhất bị bỏ trong im
// lặng: chọn xong màn hình đổi ngay (localStorage), F5 là về cỡ cũ, không một dòng lỗi nào.
check("server không loại cỡ có gạch dưới (rat_lon)",
  /v\.replace\("-", ""\)\.replace\("_", ""\)\.isalnum\(\)/.test(mainPy));
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

// ---- 9b. MÀU MẮT do người dùng chọn (0.59.6) ----
// Trước đây màu mắt suy tự động từ độ chói của thân. Chủ dự án muốn tự quyết: đen hay trắng,
// mặc định đen. Đường tự động vẫn còn, nhưng chỉ cho AVATAR TRỢ LÝ - chúng là nhân dạng khác.
{
  check("có bảng hai màu mắt", /var MAU_MAT = \{ den: "#201e1e", trang: "#ffffff" \};/.test(pet));
  check("mặc định là ĐEN", /size: "vua", eye: "den" \}/.test(pet));
  check("khoá lạ rơi về mặc định", /if \(!MAU_MAT\[c\.eye\]\) c\.eye = MAC_DINH\.eye;/.test(pet));
  check("con pet đeo màu mắt ĐÃ CHỌN, không suy từ thân nữa",
    /setProperty\("--pet-eye", mauMatCfg\(\)\)/.test(pet));
  check("dấu ấn trên thanh bên cũng theo màu mắt đã chọn",
    /markSvg: function \(\) \{ return chanDung\(cfg\.shape, cfg\.palette, \{ mat: cfg\.eye \}\); \}/.test(pet));
  // Avatar trợ lý KHÔNG truyền `mat`, nên vẫn đi đường tự động. Mất chốt này là đổi màu mắt
  // pet kéo theo cả danh sách trợ lý đổi theo.
  check("avatar trợ lý vẫn suy tự động (không truyền mat)",
    /var mat = MAU_MAT\[o\.mat\] \|\| mauMatTuDong\(tone\[0\]\);/.test(pet)
    && !/previewSvg\(a\.shape, a\.palette, [^)]*mat:/.test(read("dashboard/agent-avatar.js")));
  check("trang Linh vật có ô chọn màu mắt", /data-pet-eye="/.test(console_js)
    && /P\.setCfg\(\{ eye: b\.dataset\.petEye \}\)/.test(console_js));
  check("ô xem thử hình dáng vẽ đúng màu mắt đang chọn",
    /\{ vanh: true, mat: cur\.eye \}/.test(console_js));
  check("Đặt lại trả màu mắt về đen", /eye: "den", enabled: true/.test(console_js));
  ["settings.pet_eye", "pet.eye.den", "pet.eye.trang"].forEach(k => {
    check("i18n vi+en có " + k, typeof vi[k] === "string" && typeof en[k] === "string");
  });
}

// ---- 9c. Trang Linh vật xếp MỘT CỘT (0.59.6) ----
// Chủ dự án chốt 15/09: kiểu hai hàng hai ô rất khó xem trên điện thoại, mà đây là trang hay
// mở trên điện thoại nhất. Hình dáng lên trước, khối nút Lưu xuống cuối.
{
  check("không còn dùng lưới hai cột ở trang Linh vật",
    /pet-page-body" id="petPageBody"/.test(console_js)
    && !/settings-two-col" id="petPageBody"/.test(console_js));
  check("css: một cột ở mọi khổ màn", /\.pet-page-body \{ display: flex; flex-direction: column;/.test(railCss));
  // Thứ tự đọc: thẻ HÌNH DÁNG phải đứng TRƯỚC thẻ có nút Lưu.
  const than = console_js.slice(console_js.indexOf("const ve = () => {", console_js.indexOf("function renderPetCard")));
  check("hình dáng lên trước, khối nút Lưu xuống cuối",
    than.indexOf("settings.pet_shape") > 0
    && than.indexOf("settings.pet_shape") < than.indexOf("setPetSave"));
}

// ---- 10a. Vành quỹ đạo phải ĐẬP VÀO MẮT khi đang làm việc (0.59.4) ----
// Chủ dự án báo 15/09: vành "nhỏ và mờ quá", đổi trạng thái nhìn không ra. Lúc nghỉ nó cố ý
// mảnh và nhạt; mọi trạng thái KHÁC nghỉ phải đổi sang màu chính và dày hẳn lên.
{
  const luat = css.slice(css.indexOf('.pet[data-state]:not([data-state="idle"])'));
  const than = luat.slice(0, luat.indexOf("}"));
  check("css: trạng thái khác nghỉ thì vành đổi sang MÀU CHÍNH", /stroke: var\(--pet-face/.test(than));
  check("css: và dày hơn hẳn nét lúc nghỉ (7)", /stroke-width: 1[0-9]/.test(than));
  check("css: loại trừ cả 'paused' - đó là lúc pet đang ngủ, không phải đang làm",
    /:not\(\[data-state="paused"\]\)/.test(luat.slice(0, luat.indexOf("{"))));
  // Độ mờ đi kèm: nét đậm mà opacity 0,6 thì vẫn là một vệt mờ.
  const st = pet.slice(pet.indexOf("var STATES = {"), pet.indexOf("var el = null"));
  const mo = [...st.matchAll(/^\s+(\w+):\s*\{[^}]*mo: ([\d.]+)/gm)].map(m => [m[1], +m[2]]);
  check("mọi trạng thái đang làm việc đều đục hẳn (mo = 1)",
    mo.filter(([k]) => k !== "idle" && k !== "paused").every(([, v]) => v === 1));
  check("trạng thái nghỉ vẫn nhạt, để còn thấy sự khác biệt",
    mo.filter(([k]) => k === "idle" || k === "paused").every(([, v]) => v < 0.5));
}

// ---- 10b. Menu nhanh: đúng 5 mục, đúng thứ tự chủ dự án chốt (0.59.3, sửa 0.59.5) ----
// Menu cũ chỉ có Trò chuyện / Việc / Cài đặt / Ẩn, và "Cài đặt pet" lại mở trang Cài đặt
// chung chứ không phải trang Linh vật - bấm xong phải tự đi tìm. 0.59.5: "Ẩn pet" nhường chỗ
// cho công tắc MIC (tắt pet vẫn làm được ở trang Linh vật, ngay trong menu này một bước).
{
  const menu = pet.slice(pet.indexOf("var muc = ["), pet.indexOf("];", pet.indexOf("var muc = [")));
  const ids = [...menu.matchAll(/\{ id: "([a-z]+)"/g)].map(m => m[1]);
  check("menu nhanh đúng 5 mục theo thứ tự chốt",
    ids.join(",") === "chat,agent,workflow,mic,pet");
  check("Trợ lý / Quy trình đi qua openTab của trang Cộng sự",
    /window\.JavisWorkspace\.openTab\(id\)/.test(pet));
  // Mic: BẤM HỘ nút mic thật, không dựng đường thứ hai. Nút đó còn kéo theo loa, chế độ Live
  // và các câu báo lỗi mic - hai đường song song là sớm muộn nói hai chuyện khác nhau.
  check("mục mic bấm hộ chính nút mic của ô nhập",
    /var nutMic = document\.getElementById\("voiceBtn"\);\s*\n\s*if \(nutMic\) nutMic\.click\(\);/.test(pet));
  check("trạng thái mic đọc từ lớp của nút thật, không nuôi cờ riêng",
    /b\.classList\.contains\("handsfree"\)/.test(pet));
  check("nhãn mic đổi theo trạng thái (Bật mic / Tắt mic)",
    /mic \? t\("pet\.menu\.mic_off"[\s\S]{0,60}pet\.menu\.mic_on/.test(pet));
  // Nhãn chỉ đúng nếu menu được VẼ LẠI mỗi lần mở: mic còn bật tắt được từ nút dưới ô nhập.
  check("mở menu là vẽ lại, không chỉ vẽ lần đầu",
    /if \(mo\) veMenu\(\);/.test(pet) && !/if \(mo && !menu\.childElementCount\)/.test(pet));
  check("không còn mục Ẩn pet trong menu", ids.indexOf("hide") < 0);
  // ...nhưng đường TẮT linh vật phải còn: nút "Tắt linh vật" ở trang Linh vật gọi setEnabled.
  check("vẫn tắt được linh vật ở trang Linh vật",
    /setEnabled: setEnabled,/.test(pet) && /P\.setEnabled\(!cur\.enabled\)/.test(console_js));
  // Năm mục cao hơn 200px, mà pet đứng được sát mép trên/dưới: phải ghìm menu lại trong màn
  // hình, không thì mục đầu hay mục cuối nằm ngoài màn và không bấm được.
  check("menu được ghìm lại trong màn hình khi pet đứng sát mép",
    /function ghimMenuTrongMan\(\)/.test(pet) && /menu\.style\.marginTop = Math\.round\(dich\)/.test(pet));
  check("workspace.js có openTab và phơi ra ngoài",
    /function openTab\(kind\)/.test(read("dashboard/workspace.js"))
    && /openTab: openTab/.test(read("dashboard/workspace.js")));
}

// ---- 10c. Nút Lưu của trang Linh vật ----
// Không phải nút trang trí: nó POST rồi ĐỌC LẠI /settings và so từng khoá, vì nhánh lưu bên
// server lọc từng khoá một và bỏ khoá lạ trong im lặng.
{
  check("pet.js có hàm luu() đọc lại để kiểm chứng",
    /function luu\(\)/.test(pet) && /return fetch\("\/settings"\);/.test(pet) && /luu: luu,/.test(pet));
  check("trang Linh vật có nút Lưu và ô trạng thái",
    /id="setPetSave"/.test(console_js) && /id="setPetStatus"/.test(console_js));
  check("lưu hỏng thì GỌI TÊN khoá không vào được", /r\.lech\.join\(", "\)/.test(console_js));
}

// ---- 10d. Icon trang Linh vật là chính khuôn mặt linh vật ----
{
  const icons = read("dashboard/icons.js");
  check("icons.js có icon riêng javis-pet", /"javis-pet":/.test(icons));
  check("javis-pet có vành cam + mắt liếc lên phải",
    /stroke="#F28C28"/.test(icons) && /cy="10\.74"/.test(icons));
  check("bodyOf tra bảng icon riêng trước Lucide", /if \(RIENG\[name\]\) return RIENG\[name\];/.test(icons));
  check("console.js: trang pet dùng icon đó chứ không phải mặt cười chung",
    /pet: "javis-pet",/.test(console_js));
}

// ---- 11. Không có emoji trong menu (test_icons cũng bắt, nhưng bắt ở đây thì đọc ra lý do) ----
check("menu dùng icon lucide chứ không phải emoji",
  /var icon = function \(ten\) \{ return window\.ic \? window\.ic\(ten\) : ""; \};/.test(pet)
  && /ic: icon\("message-circle"\)/.test(pet));

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - linh vật Javis");
