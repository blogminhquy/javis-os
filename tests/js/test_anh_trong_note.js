/* Chèn ảnh vào note: dán/thả/chọn tệp -> nén -> lưu vào images/ -> nhúng ![[..]], và tay kéo
   đổi cỡ ảnh.

       node tests/js/test_anh_trong_note.js

   Chủ repo yêu cầu (2026-09-11). Năm chỗ hỏng ÂM THẦM nên phải canh:

     1. Thư mục. Ảnh note KHÔNG được rơi vào attachments/: media_gc coi thư mục đó là vùng
        cache và mặc định xoá mọi thứ quá 30 ngày, tức là một tháng sau mở note ra thấy ô xám
        "ảnh không còn". Ảnh note nằm ở images/, ngoài tầm máy dọn. (Phía server có
        tests/python/test_anh_trong_note.py canh cùng chuyện này.)
     2. Tên file theo giờ MÁY, không phải UTC. Lấy giờ UTC thì buổi tối ở Việt Nam tên ảnh lùi
        về hôm trước.
     3. Nén ngược. Ảnh PNG nhỏ đã tối ưu sẵn thì bản "nén" còn NẶNG HƠN bản gốc; lúc đó phải
        giữ bản gốc, không thì tính năng tiết kiệm dung lượng lại làm phình.
     4. Vòng lưu ngược. Thẻ <img> phải mang data-vault-path, nếu không luật turndown "wikiimg"
        không bao giờ chạy và mỗi lần lưu note có ảnh là ![[a.png]] biến thành
        ![a.png](/files/raw?brain=...) - dính cứng tên brain vào note.
     5. Giữ đúng cú pháp gốc: ![](..) không được tự biến thành ![[..]] khi lưu. */
const fs = require("fs");
const path = require("path");
const NI = require("../../dashboard/note-images.js");
const R = require("../../dashboard/chat-render.js");
const EC = require("../../dashboard/editor-cmds.js");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const SRC = D("note-images.js");
const CON = D("console.js");
const HTML = D("index.html");
const VI = JSON.parse(D("i18n/vi.json"));
const EN = JSON.parse(D("i18n/en.json"));

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Tên ảnh theo thời gian
// ============================================================
const d = new Date(2026, 8, 11, 15, 4, 22);        // 11/09/2026 15:04:22 giờ MÁY
check("tên ảnh đúng khuôn yyyy-mm-dd-hh-mm-ss", NI.tenAnhTheoGio(d, ".webp") === "2026-09-11-15-04-22.webp");
check("số một chữ số được đệm 0", NI.tenAnhTheoGio(new Date(2026, 0, 2, 3, 4, 5), ".png") === "2026-01-02-03-04-05.png");
// Lấy giờ UTC là buổi tối ở Việt Nam (UTC+7) tên ảnh nhảy sang ngày mai.
check("CANARY: lấy theo giờ MÁY chứ không phải UTC", !/toISOString|getUTC/.test(SRC));
check("tên ảnh không có ký tự lạ", /^[\d-]+\.webp$/.test(NI.tenAnhTheoGio(d, ".webp")));

// ============================================================
// 2. Đuôi file và nhận dạng ảnh
// ============================================================
check("đuôi theo MIME", NI.duoiTheoLoai("image/webp") === ".webp" && NI.duoiTheoLoai("image/jpeg") === ".jpg");
check("MIME có charset vẫn đọc được", NI.duoiTheoLoai("image/png; charset=binary") === ".png");
// Clipboard của một số trình duyệt trả type rỗng: phải suy từ tên file, không thì ảnh .jpg
// dán vào bị đặt tên .png.
check("MIME rỗng thì suy từ tên file", NI.duoiTheoLoai("", "anh-chup.JPG") === ".jpg");
check("không biết gì thì mặc định .png", NI.duoiTheoLoai("", "") === ".png");
check("nhận ra ảnh theo MIME", NI.laAnh("image/png", "") === true);
check("nhận ra ảnh theo tên khi MIME rỗng", NI.laAnh("", "x.webp") === true);
check("file .pdf không phải ảnh", NI.laAnh("application/pdf", "a.pdf") === false);

// ============================================================
// 3. Nén: khung mới, và khi nào giữ bản gốc
// ============================================================
check("ảnh to bị thu về cạnh 1920", JSON.stringify(NI.khungMoi(4000, 3000, 1920)) === JSON.stringify({ w: 1920, h: 1440, doi: true }));
check("ảnh dọc cũng theo cạnh DÀI", JSON.stringify(NI.khungMoi(1000, 4000, 1920)) === JSON.stringify({ w: 480, h: 1920, doi: true }));
check("CANARY: ảnh nhỏ KHÔNG bị phóng to lên", JSON.stringify(NI.khungMoi(300, 200, 1920)) === JSON.stringify({ w: 300, h: 200, doi: false }));
check("đúng cạnh trần thì không đổi", NI.khungMoi(1920, 100, 1920).doi === false);
check("kích thước 0 không làm vỡ", NI.khungMoi(0, 0, 1920).w === 1);

check("nén nhẹ hơn thì lấy bản nén", NI.chonBanNhe(900000, 200000, false) === "nen");
check("CANARY: nén NẶNG hơn thì giữ bản gốc", NI.chonBanNhe(3000, 5200, false) === "goc");
// Đã giảm số điểm ảnh thì vẫn lấy bản nén dù byte có nhích lên: giữ bản gốc 4000px là giữ
// một tấm ảnh không ai cần tới độ phân giải đó trong note.
check("đã thu nhỏ khung thì vẫn lấy bản nén", NI.chonBanNhe(3000, 5200, true) === "nen");
check("nén thất bại (không có blob) thì giữ bản gốc", NI.chonBanNhe(3000, 0, true) === "goc");
check("gif giữ nguyên, không qua canvas (mất ảnh động)", NI.khongNen("image/gif", "a.gif") === true);
check("svg giữ nguyên, không qua canvas (là vector)", NI.khongNen("image/svg+xml", "a.svg") === true);
check("png thì được nén", NI.khongNen("image/png", "a.png") === false);

// ============================================================
// 4. Tay kéo đổi cỡ
// ============================================================
check("kéo sang phải thì rộng ra", NI.coKhiKeo(300, 120, 900) === 420);
check("kéo sang trái thì hẹp lại", NI.coKhiKeo(300, -100, 900) === 200);
check("CANARY: không kéo nhỏ hơn 40px (ảnh biến thành hạt bụi không bắt lại được)", NI.coKhiKeo(300, -9999, 900) === 40);
check("không kéo rộng quá khung soạn", NI.coKhiKeo(300, 9999, 900) === 900);
check("khung soạn hẹp bất thường vẫn còn trần dùng được", NI.coKhiKeo(300, 9999, 10) === 80);

// ============================================================
// 5. Cú pháp cỡ ảnh kiểu Obsidian ![[a.png|300]]
// ============================================================
check("|300 là cỡ", JSON.stringify(R.coAnh("300")) === JSON.stringify({ w: 300, h: 0 }));
check("|300x200 là cỡ hai chiều", JSON.stringify(R.coAnh("300x200")) === JSON.stringify({ w: 300, h: 200 }));
check("chữ thì là alt text, không phải cỡ", JSON.stringify(R.coAnh("ảnh bìa")) === JSON.stringify({ alias: "ảnh bìa" }));
check("rỗng thì không có gì", R.coAnh("") === null && R.coAnh(null) === null);

const img = (md) => (R.mdToHtml(md).match(/<img[^>]*>/) || [""])[0];
check("![[a|320]] vẽ ra ảnh rộng 320", /style="width:320px"/.test(img("![[images/a.webp|320]]")));
check("cỡ được giữ trong data-img-size để lưu ngược", /data-img-size="320"/.test(img("![[images/a.webp|320]]")));
check("không có cỡ thì không gắn style", !/style=/.test(img("![[images/a.webp]]")));
check("CANARY: thẻ img mang data-vault-path (thiếu là vòng lưu ngược đứt)",
      /data-vault-path="images\/a\.webp"/.test(img("![[images/a.webp]]")));
check("ảnh viết bằng ![[..]] được đánh dấu data-img-wiki", /data-img-wiki="1"/.test(img("![[images/a.webp]]")));
check("CANARY: ảnh viết bằng ![](..) KHÔNG bị đánh dấu wiki", !/data-img-wiki/.test(img("![anh](images/a.webp)")));
check("ảnh URL ngoài không dính data-vault-path", !/data-vault-path/.test(img("![x](https://e.com/a.png)")));

// ============================================================
// 6. Vòng LƯU NGƯỢC: chạy thật hàm replacement của luật turndown "wikiimg"
// ============================================================
// Bóc nguyên hàm từ console.js ra chạy, không chỉ soi chuỗi: đây là chỗ quyết định note được
// ghi xuống đĩa ra hình gì, soi chuỗi không chứng minh được nó ra đúng chữ.
function bocReplacement(ten) {
  const i = CON.indexOf('_td.addRule("' + ten + '"');
  if (i < 0) return null;
  const j = CON.indexOf("replacement:", i);
  const k = CON.indexOf("{", CON.indexOf("=>", j));
  let sau = 0, e = k;
  for (; e < CON.length; e++) {
    if (CON[e] === "{") sau++;
    else if (CON[e] === "}") { sau--; if (!sau) break; }
  }
  return eval("(function (c, n) " + CON.slice(k, e + 1) + ")");
}
const luuAnh = bocReplacement("wikiimg");
check("bóc được hàm lưu ngược của ảnh", typeof luuAnh === "function");
const node = (o) => ({ getAttribute: (k) => (Object.prototype.hasOwnProperty.call(o, k) ? o[k] : null) });

check("![[a]] lưu lại thành ![[a]]",
      luuAnh("", node({ "data-vault-path": "images/a.webp", "data-img-wiki": "1" })) === "![[images/a.webp]]");
check("kéo cỡ rồi lưu ra ![[a|320]]",
      luuAnh("", node({ "data-vault-path": "images/a.webp", "data-img-wiki": "1", "data-img-size": "320" })) === "![[images/a.webp|320]]");
check("alt text được giữ qua dấu |",
      luuAnh("", node({ "data-vault-path": "images/a.webp", "data-img-wiki": "1", "data-img-alias": "ảnh bìa" })) === "![[images/a.webp|ảnh bìa]]");
check("CANARY: ![](..) lưu lại VẪN là ![](..), không tự đổi cú pháp",
      luuAnh("", node({ "data-vault-path": "images/a.webp", alt: "anh" })) === "![anh](images/a.webp)");
// Cú pháp ![](..) không có chỗ ghi cỡ, nên kéo đổi cỡ một ảnh kiểu đó thì phải chuyển sang
// ![[..|cỡ]]; giữ nguyên là im lặng bỏ mất thao tác người dùng vừa làm.
check("![](..) bị kéo đổi cỡ thì chuyển sang ![[..|cỡ]] để giữ được cỡ",
      luuAnh("", node({ "data-vault-path": "images/a.webp", alt: "anh", "data-img-size": "500" })) === "![[images/a.webp|500]]");

// ============================================================
// 7. Nối vào ứng dụng
// ============================================================
check("ảnh lưu vào thư mục images (KHÔNG phải attachments)",
      /fd\.append\("folder", "images"\)/.test(SRC) && !/"folder", "attachments"/.test(SRC));
check("có giải thích vì sao không dùng attachments", /media_gc/.test(SRC));
check("dán (Ctrl+V) được nghe", /addEventListener\("paste"/.test(SRC));
check("thả tệp được nghe", /addEventListener\("drop"/.test(SRC) && /addEventListener\("dragover"/.test(SRC));
check("dán CHỮ thì không cướp (chỉ chặn khi có ảnh)", /if \(!anh\.length\) return;[\s\S]{0,40}e\.preventDefault\(\)/.test(SRC));
check("đọc cả clipboardData.items (Firefox trả files rỗng)", /dt\.items/.test(SRC));
check("nhiều ảnh một lượt thì làm TUẦN TỰ", /reduce\(/.test(SRC));
check("chặn ảnh quá lớn trước khi nén", /TRAN_MB \* 1024 \* 1024/.test(SRC));
check("chèn xong bắn input để bộ tự lưu chạy", /dispatchEvent\(new Event\("input", \{ bubbles: true \}\)\)/.test(SRC));
check("dùng CHUNG ctxTu của editor-cmds, không chép bản thứ hai",
      /EC\.ctxTu/.test(SRC) && typeof EC.ctxTu === "undefined");   // ctxTu chỉ có trong trình duyệt
check("tay kéo bám theo cuộn trang", /addEventListener\("scroll"/.test(SRC));
check("bấm đúp tay kéo thì về cỡ gốc", /dblclick/.test(SRC) && /removeAttribute\("data-img-size"\)/.test(SRC));
check("KHÔNG dùng ký tự em dash", !SRC.includes("\u2014"));

check("index.html nạp note-images.js", /note-images\.js/.test(HTML));
check("nạp SAU editor-cmds.js", HTML.indexOf("note-images.js") > HTML.indexOf("editor-cmds.js"));

const nutAnh = EC.CMDS.find((c) => c.id === "image");
check("thanh công cụ có nút chèn ảnh", !!nutAnh && nutAnh.btn.icon === "image");
check("nút ảnh chạy được ở CẢ hai chế độ (dùng run, không phải wys/src riêng)", !!(nutAnh && nutAnh.run));
check("nút ảnh có mặt trong menu gõ '/'", EC.menuCmds().some((c) => c.id === "image"));
check("lọc menu '/' theo chữ 'anh' ra nút ảnh", EC.filterCmds("chen anh").map((c) => c.id).join() === "image");
check("CANARY: phím tắt ảnh KHÔNG cướp Ctrl+Shift+I của devtools",
      EC.keyLabel(nutAnh) === "Ctrl+Alt+I");

["ecmd.image", "nimg.dang_xu_ly", "nimg.xong", "nimg.qua_lon", "nimg.loi", "nimg.tay_keo"].forEach((k) => {
  check("có khoá dịch " + k + " ở cả vi và en", !!VI[k] && !!EN[k] && VI[k] !== EN[k]);
});

console.log(fails.length ? "\nFAIL: " + fails.length : "\nTất cả đều xanh");
process.exit(fails.length ? 1 : 0);
