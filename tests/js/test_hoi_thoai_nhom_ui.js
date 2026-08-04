/* Cột Lịch sử: ghim, Project, icon.

       node tests/js/test_hoi_thoai_nhom_ui.js

   Ba thứ file này canh, đều là loại chỉ lộ ra khi bấm thật:

   1. NÚT MỚI KHÔNG ĐƯỢC LÀM MỞ NHẦM HỘI THOẠI. Cả hàng .cside-item có onclick mở hội thoại;
      nút nằm bên trong nó. Đây chính xác là lỗi 0.12.3 (bấm Xoá lại mở hội thoại) mà
      test_chat_side_actions.js đang canh - ba nút mới thêm phải chặn nổi bọt, nếu không thì
      bấm Ghim là nhảy sang một hội thoại khác.

   2. HANDLER CŨ PHẢI GIỮ NGUYÊN CHỮ KÝ. test_chat_side_actions.js bóc CHÍNH khối
      item.onclick trong nguồn ra chạy với đúng năm tham số (e, s, delSession, renSession,
      openSession). Nhét tên hàm mới vào khối đó là test kia nổ ReferenceError. Nên nút mới
      phải gắn handler riêng, và file này canh đúng điều đó.

   3. "CHAT MỚI RƠI VÀO PROJECT ĐANG MỞ" phải móc vào ĐÚNG chỗ mint id trong app.js. Muộn hơn
      một nhịp là tin nhắn đầu tiên đã gửi mà hội thoại vẫn chưa có nhãn. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const SESS = D("sessions-ui.js");
const APP = D("app.js");
const CSS = D("style.css");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Thanh Project và các nút
// ============================================================
check("cột trái có thanh Project", SESS.indexOf('class="cside-proj"') !== -1);
check("gọi API danh sách project", /fetch\("\/projects\?brain=/.test(SESS));
check("tạo project qua POST /projects", SESS.indexOf('post("/projects"') !== -1);
check("xoá project qua endpoint riêng", SESS.indexOf('"/delete"') !== -1 || /projects\/.*\/delete/.test(SESS));
check("lọc danh sách theo project", SESS.indexOf('"&project=" + encodeURIComponent(p)') !== -1);
check("CSS có thanh project", /\.cside-proj \{/.test(CSS));
check("CSS có popover menu", /\.cs-menu \{/.test(CSS));
check("CSS có bộ chọn emoji", /\.cs-emo-grid \{/.test(CSS));

// Project đang mở là chỗ đứng trên MỘT máy -> localStorage, không đẩy lên server.
check("project đang mở nhớ ở localStorage theo brain",
  SESS.indexOf("PROJ_KEY") !== -1 && /function projKey\(\) \{ return PROJ_KEY \+ "\." \+ brain\(\); \}/.test(SESS));

// ============================================================
// 2. Xoá project phải NÓI RÕ hội thoại không mất
// ============================================================
// Đây là ràng buộc UX chứ không chỉ là chữ: người dùng sẽ không bấm nếu tưởng mất hội thoại,
// và tệ hơn là bấm rồi tưởng mất thật.
check("CANARY: hộp xác nhận xoá project nói rõ hội thoại KHÔNG bị xoá",
  /KHÔNG bị xoá/.test(SESS));

// ============================================================
// 3. Nút mới: có handler riêng + chặn nổi bọt
// ============================================================
["pin", "emo", "mov"].forEach((cls) => {
  // stopPropagation phải là việc ĐẦU TIÊN trong handler, không phải đâu đó ở giữa: chỉ cần
  // một nhánh return sớm nằm trước nó là cú bấm rơi xuống hàng cha và mở nhầm hội thoại.
  const re = new RegExp('item\\.querySelector\\("\\.' + cls + '"\\)\\.onclick = function \\(ev\\) \\{\\s*ev\\.stopPropagation\\(\\);');
  check(`nút .${cls} có handler riêng và chặn nổi bọt ngay đầu`, re.test(SESS));
});

// ============================================================
// 4. KHÔNG được nhét nhánh mới vào item.onclick
// ============================================================
// test_chat_side_actions.js chạy CHÍNH khối này với đúng 5 tham số. Thêm tên lạ vào là nó nổ.
const m = SESS.match(/item\.onclick = function \(e\) \{\n([\s\S]*?)\n      \};/);
check("vẫn tìm được khối item.onclick (test kia dựa vào nó)", !!m);
if (m) {
  const than = m[1];
  ["togglePin", "pickIcon", "moveMenu", "post(", "openMenu"].forEach((ten) => {
    check(`item.onclick KHÔNG gọi ${ten} (test_chat_side_actions bóc khối này ra chạy riêng)`,
      than.indexOf(ten) === -1);
  });
  check("item.onclick vẫn chỉ dò .ren/.del", than.indexOf('closest(".ren, .del")') !== -1);
}

// ============================================================
// 5. Ghim: nhóm riêng trên đầu, và server sắp trước
// ============================================================
check("mục đã ghim gom thành nhóm riêng", SESS.indexOf('"Đã ghim"') !== -1);
check("icon hội thoại hiện trước tên", SESS.indexOf('class="ci-icon"') !== -1);
// Ghim đổi THỨ TỰ danh sách, mà cache lại giữ thứ tự cũ -> phải bỏ cache rồi tải lại,
// không thì bấm ghim xong nhìn như không có gì xảy ra.
check("CANARY: ghim xong thì bỏ cache danh sách (nếu không thứ tự cũ còn nguyên trên màn hình)",
  /async function togglePin[\s\S]{0,320}cached = null;/.test(SESS));
check("cache phân biệt theo cả bộ lọc project, không chỉ brain",
  /cached\.project === curProject\(\)/.test(SESS));

// ============================================================
// 6. Chat mới rơi vào project đang mở
// ============================================================
check("sessions-ui phơi cầu nối JavisProjects", SESS.indexOf("window.JavisProjects = {") !== -1);
check("claim gửi kèm brain (để server tạo được hàng chưa tồn tại)",
  /claim: function \(sid\)[\s\S]{0,320}brain: brain\(\)/.test(SESS));
check("không claim khi đang xem 'Tất cả' hay 'Chưa xếp nhóm'",
  /if \(!sid \|\| !p \|\| p === "none"\) return;/.test(SESS));
// Phải gọi NGAY tại chỗ mint id: đó là nơi duy nhất biết "id này vừa sinh ra".
check("CANARY: app.js gọi claim ngay khi mint id hội thoại mới",
  /savedSessionId = newSid\(\);[\s\S]{0,400}JavisProjects\.claim\(savedSessionId\)/.test(APP));
check("claim bọc try/catch (thiếu module không được làm hỏng đường gửi tin)",
  /try \{ if \(window\.JavisProjects\) window\.JavisProjects\.claim/.test(APP));

// ============================================================
// 7. Đổi brain thì project đi theo
// ============================================================
check("đổi brain thì nạp lại danh sách project",
  /if \(b !== lastBrain\) \{[\s\S]{0,400}loadProjects\(\);/.test(SESS));

if (fails.length) {
  console.log("\nFAIL - test_hoi_thoai_nhom_ui: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_hoi_thoai_nhom_ui: tất cả pass");
