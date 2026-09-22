/* Đổi bộ não trong khi đang đứng ở trang Cộng sự.

       node tests/js/test_doi_bo_nao_trang_cong_su.js

   Chủ dự án báo 22/09/2026: "vào phần agent đang bị lag, load phần trợ lý và phần cài đặt rất
   chậm, thậm chí khi chuyển các não bộ còn bị đen màn hình luôn, nó bị trắng tinh không hiển
   thị, màn ở giữa khung chat thì hiển thị dữ liệu của hội thoại cũ".

   Ba gốc khác nhau, cùng đổ ra một cú bấm:

     1. ĐỨNG HÌNH. Ô chọn brain đổi là app.js nạp lại nguyên bộ số liệu của MÀN CHÍNH: cả một
        lượt /graph, rồi /agents + /skills + /workflows (loadBrainStats) lặp lại đúng những
        thứ trang Cộng sự đang tự gọi, cộng /memory/stats và /vault/check. Trình duyệt chỉ mở
        6 kết nối một lúc nên trang đang xem phải xếp hàng sau, còn thư viện đồ thị thì quay
        warmupTicks ĐỒNG BỘ trên toàn bộ node ngay khi nhận dữ liệu - màn hình trắng vài giây
        vì một đồ thị người dùng KHÔNG NHÌN THẤY (nó nằm ở màn chính). Hoãn tới lúc về màn
        chính là xong cả hai.

     2. HỘI THOẠI CŨ. app.js nhớ "phiên đang xem của từng brain" để quay lại brain cũ thì mở
        tiếp cuộc đang dở. Nhưng ở trang Cộng sự, phiên đang xem là phiên agent:<slug> của
        MỘT TRỢ LÝ, không phải cuộc chính; nhớ nó rồi khôi phục là đè thẳng lên phiên mà trang
        Cộng sự vừa mở cho brain mới.

     3. SÓT LẠI CỦA BRAIN CŨ. Đổi brain thì console.js gọi thẳng renderPage, KHÔNG đi qua
        navigateTo, nên roi() của trang không chạy: một moPhien đang chờ mạng vẫn mở phiên của
        brain cũ vào khung vừa dựng, và _phienTruoc vẫn trỏ vào cuộc chính của brain cũ.

   CI chỉ có node nên file này khoá phần hợp đồng đọc được từ mã nguồn. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const doc = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const APP = doc("app.js"), CON = doc("console.js"), WS = doc("workspace.js"), HTML = doc("index.html");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// Thân của handler đổi brain trong app.js.
const i = APP.indexOf('graphSource.addEventListener("change"');
const DOI = APP.slice(i, APP.indexOf("\n});", i));
check("tìm thấy handler đổi brain", i !== -1 && DOI.length > 0);

// ---- 1. Việc của màn chính phải hoãn khi đang ở trang quản lý ----
check("handler không còn gọi thẳng năm việc của màn chính",
  DOI.indexOf("reloadGraph()") === -1 && DOI.indexOf("loadBrainStats()") === -1
  && DOI.indexOf("checkVault()") === -1 && DOI.indexOf("loadMemStats()") === -1);
check("gọi qua capNhatManChinh()", DOI.indexOf("capNhatManChinh()") !== -1);
const CAP = APP.slice(APP.indexOf("function capNhatManChinh()"),
                      APP.indexOf("// console.js gọi mỗi lần đổi trang"));
check("capNhatManChinh hoãn lại khi không ở màn chính",
  /if \(!_oManChinh\(\)\) \{/.test(CAP) && /_cockpitCho = true;/.test(CAP));
check("hoãn thì xoá luôn số note của brain cũ (ô đó nhìn thấy được ở trang quản lý)",
  /graphStats\.textContent = "-";/.test(CAP));
check("về màn chính thì chạy đủ cả năm việc",
  ["reloadGraph()", "connectGraphWatch()", "loadMemStats()", "loadBrainStats()", "checkVault()"]
    .every(s => CAP.indexOf(s) !== -1));
check("app.js phơi JavisCockpit.veManChinh cho console.js gọi",
  /window\.JavisCockpit = \{ veManChinh\(\)/.test(APP));
check("_oManChinh hỏi JavisNav, thiếu thì chạy như cũ (không treo số liệu vĩnh viễn)",
  /window\.JavisNav\.active\(\) === "home"/.test(APP) && /catch \(e\) \{ return true; \}/.test(APP));
// Nợ phải được trả ĐÚNG lúc về màn chính, không thì đồ thị kẹt ở brain cũ mãi mãi.
const RE = CON.slice(CON.indexOf("function recomputeGraph()"), CON.indexOf("// ---- Chuyển trang"));
check("recomputeGraph trả nợ khi active === home",
  /active === "home"/.test(RE) && /JavisCockpit\.veManChinh\(\)/.test(RE));
check("trả nợ TRƯỚC khi thoát vì không có đồ thị (máy yếu / lite vẫn phải có số liệu đúng)",
  RE.indexOf("veManChinh()") < RE.indexOf("if (!g) return;"));

// ---- 2. Phiên của cộng sự không phải cuộc chính của brain ----
check("console.js biết trang nào đang giữ khung chat",
  /const TRANG_GIU_CHAT = \["workspace", "coding"\]/.test(CON)
  && /giuKhungChat\(\) \{ return _chatSlots\.length > 0/.test(CON));
check("trang Trò chuyện KHÔNG nằm trong đó (nó chính là cuộc chính)",
  /TRANG_GIU_CHAT = \[[^\]]*\]/.exec(CON)[0].indexOf('"chat"') === -1);
check("app.js hỏi trước khi nhớ phiên của brain cũ",
  /if \(savedSessionId && !muon\) _viewByBrain\[_lastBrain\] = savedSessionId;/.test(DOI));
check("app.js không khôi phục cuộc chính đè lên phiên trang kia vừa mở",
  /if \(!muon && _viewByBrain\[nb\]\) openStoredSession/.test(DOI));
check("vẫn xoá trắng khung của brain cũ trong mọi trường hợp", DOI.indexOf("resetChatView();") !== -1);

// ---- 3. Trang Cộng sự dựng lại là dựng LẠI, không nối tiếp brain cũ ----
const RENDER = WS.slice(WS.indexOf("function render(el, opts)"), WS.indexOf("el.innerHTML ="));
check("render() cắt mọi moPhien đang chờ mạng", /opening\+\+;/.test(RENDER));
check("render() quên phiên trước của brain cũ", /_phienTruoc = null;/.test(RENDER));
check("render() quên sổ phiên + tiến độ của brain cũ",
  /S\.sessionCuaPhien = \{\};/.test(RENDER) && /S\.tienDo = \{\};/.test(RENDER));
check("render() bỏ danh sách cũ và hạ cờ daTai (kẻo bày nhầm màn khởi đầu của brain mới)",
  /S\.agents = \[\]; S\.workflows = \[\];/.test(RENDER) && /daTai = false;/.test(RENDER));
check("render() đóng menu nổi còn neo vào body", /dongMenu\(\);/.test(RENDER));

// ---- 4. Chọn folder ngoài cũng là ĐỔI BRAIN ----
// Gán thẳng .value không sinh sự kiện change, nên bản cũ chỉ vẽ lại đồ thị còn khung chat,
// trang Cộng sự và cây thư mục vẫn ở não trước.
const fmI = APP.indexOf('document.getElementById("fmUse")');
const FM = APP.slice(fmI, APP.indexOf("\n});", fmI));
check("nút Dùng folder này báo đổi brain cho mọi chỗ nghe",
  /graphSource\.dispatchEvent\(new Event\("change"\)\)/.test(FM));

// ---- 5. Trình duyệt phải nhận bản mới ----
["app.js", "console.js", "workspace.js", "studio.js"].forEach((f) => {
  const m = new RegExp("/static/" + f.replace(".", "\\.") + "\\?v=(\\d+)").exec(HTML);
  check("index.html có ?v= cho " + f + " (đổi file là phải tăng, kẻo máy khách chạy bản cũ)", !!m);
});

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - doi bo nao o trang Cong su");
