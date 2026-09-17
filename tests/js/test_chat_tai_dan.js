/* Khung chat tải dần + phân trang trang Kỹ năng.

       node tests/js/test_chat_tai_dan.js

   Hai việc đi chung một file vì cùng một bài toán: danh sách dài thì đừng đổ hết ra một lượt.

   Phần khung chat có ba cái bẫy, mỗi cái đều IM LẶNG khi làm sai:

   1. Chèn ngược mà quên chặn cuộn: appendUserMessage/appendJavisMessage đều gọi scrollBottom
      theo thói quen, nên chèn xong là màn quăng thẳng xuống đáy - người đọc đang xem giữa
      cuộc bị đá đi mà không hiểu vì sao.

   2. Giữ chỗ cuộn phải đo theo ĐÁY khung (scrollHeight - scrollTop), không phải theo
      scrollTop. Phần chèn nằm phía trên nên scrollTop cũ trỏ vào một chỗ khác hẳn.

   3. Mồi tải tin chỉ được chèn KHI CÒN tin cũ. `.transcript:empty::after` là câu mời "Nói
      hoặc gõ để bắt đầu"; một node con thường trực là câu đó biến mất lặng lẽ - đúng cái bẫy
      đã ghi sẵn trong app.js cho #newMsgBtn và trong chat-marks.js.

   Phần trang Kỹ năng canh chuyện chép khối: repo đã có sẵn pager() dùng chung cho nhật ký
   loop, trang Tự học và trang Tiết kiệm. Viết bản thứ hai cho trang Kỹ năng là hai bản trôi
   lệch nhau ngay lần sửa đầu tiên. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const APP = D("app.js");
const CONSOLE = D("console.js");
const STUDIO = D("studio.js");
const CSS = D("style.css");
const VI = JSON.parse(D("i18n/vi.json"));
const EN = JSON.parse(D("i18n/en.json"));

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// A. Khung chat chỉ dựng phần đuôi
// ============================================================
check("mở hội thoại cũ kèm limit, không kéo cả cuộc về",
  /\/sessions\/\$\{encodeURIComponent\(id\)\}\?limit=\$\{TIN_MOI_LUOT\}/.test(APP));
check("có hằng số số tin mỗi lượt", /const TIN_MOI_LUOT = \d+;/.test(APP));
check("vẫn rơi xuống đáy sau khi dựng xong",
  /scrollBottom\(true\);\s*\n\s*ghimDay\(ticket\);\s*\n\s*notifySessions\(\);/.test(APP));
// Đặt scrollTop MỘT LẦN là không đủ: thanh mốc hội thoại chèn vào rồi bật lề phải làm bong
// bóng xuống dòng, ảnh tải xong mới đẩy chiều cao ra. Đo thật trên cuộc 120 tin: mở xong
// đứng cách đáy 174px, câu trả lời gần nhất bị cắt. Nên phải ghim lại trong một quãng ngắn.
check("ghim lại đáy qua vài nhịp vẽ, vì khung còn cao thêm sau lượt mở",
  /function ghimDay\(ticket, ms\)/.test(APP) && /requestAnimationFrame\(nhip\)/.test(APP));
check("nhả ghim ngay khi người dùng tự cuộn",
  /addEventListener\("wheel", nhaTay/.test(APP) && /addEventListener\("touchmove", nhaTay/.test(APP));
check("và nhả luôn khi đổi sang hội thoại khác", /if \(thoi \|\| ticket !== sessionOpenSeq\)/.test(APP));
// Con trỏ lấy từ tin ĐẦU của khúc đang hiện, tức tin già nhất trên màn.
check("giữ con trỏ (ts, id) của tin già nhất đang hiện",
  /ts: ds\[0\]\.ts, id: ds\[0\]\.id, con: !!sess\.has_more/.test(APP));

// ============================================================
// B. Cuộn lên tải tiếp
// ============================================================
check("có hàm tải khúc cũ hơn", /async function taiTinCu\(\)/.test(APP));
check("gọi đúng đường /messages với cặp con trỏ",
  APP.indexOf("/messages?limit=") !== -1 &&
  APP.indexOf("before_ts=") !== -1 && APP.indexOf("before_id=") !== -1);
check("dùng IntersectionObserver để tự tải khi cuộn tới đầu khung",
  /new IntersectionObserver\(/.test(APP) && /root: chatArea/.test(APP));
check("còn nút bấm tay khi trình duyệt không có IntersectionObserver",
  /typeof IntersectionObserver !== "function"/.test(APP));
// Bẫy 1.
check("có cờ chặn cuộn trong lúc chèn ngược", /let _neoChenCu = null, _dangChenCu = false;/.test(APP));
check("scrollBottom thoát sớm khi đang chèn ngược",
  /function scrollBottom\(force\) \{[\s\S]{0,400}?if \(_dangChenCu\) return;/.test(APP));
check("chatAppend chèn trước cái neo khi có neo",
  /chatArea\.insertBefore\(el, _neoChenCu \|\| newMsgBtn\)/.test(APP));
// Bẫy 2.
check("giữ chỗ cuộn đo theo ĐÁY khung, không theo scrollTop",
  /const cachDay = chatArea\.scrollHeight - chatArea\.scrollTop;/.test(APP) &&
  /chatArea\.scrollTop = chatArea\.scrollHeight - cachDay;/.test(APP));
check("đặt lại chỗ cuộn SAU khi dựng lại mồi, không phải trước",
  APP.indexOf("datMoiTinCu();\n    chatArea.scrollTop = chatArea.scrollHeight - cachDay;") !== -1);
// Đổi phiên giữa chừng: khúc vừa về là của cuộc khác.
check("vứt khúc về muộn khi đã đổi phiên",
  /_tinCu !== st \|\| st\.sid !== savedSessionId/.test(APP));
check("khoá không cho hai lượt tải chồng nhau", /if \(!st \|\| !st\.con \|\| st\.dangTai\) return;/.test(APP));
// Bẫy 3.
check("chỉ chèn mồi khi CÒN tin cũ", /if \(!_tinCu \|\| !_tinCu\.con\) return;/.test(APP));
check("mở hội thoại mới thì dọn mồi và con trỏ",
  /_tinCu = null; goMoiTinCu\(\);/.test(APP));
// Neo theo bong bóng đầu tiên chứ không theo firstChild: đầu khung còn có đồ nội thất dán
// sẵn (thanh mốc hội thoại) tính là mình vẫn đứng đầu, chen lên trước là đẩy nó khỏi chỗ.
check("mồi neo theo bong bóng đầu tiên, không phải firstChild",
  /function dauKhungChat\(\)/.test(APP) &&
  /return chatArea\.querySelector\("\.msg"\);/.test(APP) &&
  !/dauKhungChat[\s\S]{0,200}chatArea\.firstChild/.test(APP));

// ============================================================
// C. Sống sót qua F5
// ============================================================
check("con trỏ tin cũ được lưu xuống localStorage", /tinCu: \(_tinCu && convo\.length <= 200\)/.test(APP));
check("khôi phục phiên thì dựng lại mồi", /_tinCu = \(s\.tinCu && savedSessionId\)/.test(APP));

// ============================================================
// D. Chữ hiển thị + CSS
// ============================================================
["app.older_load", "app.older_loading"].forEach(k => {
  check("có chuỗi " + k + " ở cả vi và en", !!VI[k] && !!EN[k]);
});
check("chuỗi tiếng Việt có dấu", /[ăâêôơưđáàảãạ]/i.test(VI["app.older_load"]));
check("có CSS cho mồi tải tin cũ", CSS.indexOf(".older-seed") !== -1 && CSS.indexOf(".older-btn") !== -1);

// ============================================================
// E. Phân trang trang Kỹ năng - dùng LẠI pager() sẵn có
// ============================================================
check("console.js xuất pager ra cho module khác", /window\.JavisPager = pager;/.test(CONSOLE));
check("pager nhận được cả Node lẫn chuỗi HTML", /if \(ruot && ruot\.nodeType\)/.test(CONSOLE));
check("trang Kỹ năng gọi pager dùng chung, không tự viết bản thứ hai",
  /window\.JavisPager\(box, list, SK_MOI_TRANG, veTrang\)/.test(STUDIO));
check("có hằng số số skill mỗi trang", /const SK_MOI_TRANG = \d+;/.test(STUDIO));
check("thẻ skill tách thành hàm riêng để mỗi trang dựng lại được",
  /function theSkill\(s\) \{/.test(STUDIO) && /phan\.forEach\(s => fr\.appendChild\(theSkill\(s\)\)\)/.test(STUDIO));
// Chọn tất cả phải gom CẢ danh sách đang lọc, không phải mỗi trang đang hiện - đúng bài học
// đã ghi trong test_chon_skill_va_phan_trang.js: lọc rồi đọc trạng thái từ DOM là mất tick.
check("Chọn tất cả vẫn gom cả danh sách đang lọc, không chỉ trang đang hiện",
  /_skFiltered\(\)\.filter\(s => !s\.system\)\.map\(s => s\.slug\)/.test(STUDIO));
check("tick phục hồi từ Set khi lật trang", /el\.checked = _sel\[kind\]\.has\(slug\);/.test(STUDIO));
check("hàng phân trang trong danh sách skill được căn giữa",
  /\.sk2-list \.jv-pager\{justify-content:center\}/.test(STUDIO));

console.log("");
if (fails.length) { console.log("ĐỎ " + fails.length + " mục"); process.exit(1); }
console.log("Tất cả xanh.");
