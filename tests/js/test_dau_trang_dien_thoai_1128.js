/* Đầu trang trên điện thoại gọn lại (chủ dự án, 28/11/2026, kèm ba ảnh chụp):

       node tests/js/test_dau_trang_dien_thoai_1128.js

   1. Header điện thoại chỉ còn nút ba gạch bên trái và chuông bên phải. Nút "+" hội thoại mới ít người
      biết tới, hội thoại mới đã có sẵn trong ngăn hội thoại của trang Trò chuyện và Cộng sự.
   2. Thanh trên trang Trò chuyện bỏ nút "Thu nhỏ" về màn Javis: bộ não không còn là trang chính, có
      nhiều đường khác để vào, và nút này chiếm chỗ khiến nút mục lục "≡ 7/7" dính vào chip project.
   3. Cột phải trang Cộng sự trên màn hẹp: ba tab Lịch sử, Công việc, Cài đặt thiếu icon và nút X nằm
      lệch lên một hàng riêng. Nay X cùng hàng với tab, tab có icon, tab chưa chọn chỉ còn icon.

   ROOT đọc được từ biến môi trường JAVIS_ROOT để chạy thử trên bản cũ (thấy đỏ trước khi sửa). */
const fs = require("fs");
const path = require("path");

const ROOT = process.env.JAVIS_ROOT || path.join(__dirname, "..", "..");
const doc = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const HTML = doc("index.html"), MOB = doc("mobile-chat.js"), CCSS = doc("console.css");
const WS = doc("workspace.js"), CON = doc("console.js");
const VI = JSON.parse(doc("i18n/vi.json")), EN = JSON.parse(doc("i18n/en.json"));

const fails = [];
function check(name, ok) { console.log((ok ? "PASS " : "FAIL ") + name); if (!ok) fails.push(name); }

// Lấy thân các khối @media (max-width:...) có độ rộng cho trước, gộp lại thành một chuỗi.
function mediaBodies(css, px) {
  const re = new RegExp("@media\\s*\\(max-width:\\s*" + px + "px\\)\\s*\\{", "g");
  let out = "", m;
  while ((m = re.exec(css))) {
    let i = re.lastIndex, depth = 1;
    while (i < css.length && depth) { if (css[i] === "{") depth++; else if (css[i] === "}") depth--; i++; }
    out += css.slice(re.lastIndex, i - 1) + "\n";
  }
  return out;
}

// 1) Header: không còn nút +, chuông về góc phải.
check("index.html không còn nút + (#newChatBtn)", !/id="newChatBtn"/.test(HTML));
check("mobile-chat.js không còn đụng tới #newChatBtn", !/newChatBtn/.test(MOB));
check("mobile-chat.js đặt chuông làm con CUỐI của header (góc phải)",
  /headerRoot\.appendChild\(notificationTrigger\)/.test(MOB));
check("console.css không còn lớp .new-chat-btn", !/\.new-chat-btn/.test(CCSS));
const phone = mediaBodies(CCSS, 860);
check("chuông tự đẩy về mép phải header trên điện thoại (margin-left:auto)",
  /\.hud-top \.notification-trigger\s*\{[^}]*margin-left:\s*auto/.test(phone));
check("trang Cộng sự không còn bắt cú bấm của nút + cũ", !/bindHeaderNewChat|#newChatBtn/.test(WS));
check("thanh trang Cộng sự trên điện thoại vẫn ẩn nút Hội thoại mới riêng (đã có trong ngăn phải)",
  /\.ws-bar #wsNewChat\s*\{\s*display:\s*none;?\s*\}/.test(phone));
check("ngăn phải Cộng sự vẫn có nút Hội thoại mới (đường thay cho nút + đã bỏ)",
  /onNew\s*:/.test(WS) || /onNew\b/.test(WS));

// 2) Trang Trò chuyện: bỏ nút Thu nhỏ.
check("thanh trang Trò chuyện không còn nút Thu nhỏ (#cpMinBtn)", !/cpMinBtn|cp-min\b/.test(CON));
check("không còn khoá i18n cs.cp_min / cs.cp_min_title",
  !("cs.cp_min" in VI) && !("cs.cp_min_title" in VI) && !("cs.cp_min" in EN) && !("cs.cp_min_title" in EN));
const iBar = CON.indexOf('<div class="chatpage-bar">');
const bar = iBar >= 0 ? CON.slice(iBar, CON.indexOf("'</div>' +", iBar)) : "";
check("thanh vẫn giữ nút mở ngăn, tên cuộc chat và chip project",
  /cp-side-toggle/.test(bar) && /cp-conv-host/.test(bar) && /proj-chip-host/.test(bar));

// 3) Cột phải trang Cộng sự: tab có icon + nhãn trong span, X cùng hàng.
const iTabs = WS.indexOf('class="cside-tabs ws-rtabs"');
const tabs = iTabs >= 0 ? WS.slice(iTabs, WS.indexOf("'</div>' +", iTabs)) : "";
for (const [k, icon, label] of [["lichsu", "history", "ws.tab_history"], ["viec", "list-todo", "ws.tab_jobs"],
  ["cai", "settings", "ws.tab_settings"]]) {
  const i = tabs.indexOf('data-rtab="' + k + '"');
  const btn = i >= 0 ? tabs.slice(i, tabs.indexOf("</button>", i)) : "";
  const name = "esc(t(\"" + label + "\"))";
  check("tab " + k + " có icon " + icon, btn.includes('ic("' + icon + '")'));
  check("tab " + k + ": nhãn trong span ẩn được, còn aria-label và title khi chỉ còn icon",
    btn.includes("<span class=\"ws-rtab-lbl\">' + " + name) && btn.includes("aria-label=\"' + " + name)
    && btn.includes("title=\"' + " + name));
}
const narrow = mediaBodies(CCSS, 1060);
check("màn hẹp: icon tab hiện lại", /\.ws-rtabs \.cside-tab svg\s*\{[^}]*display:\s*block/.test(narrow));
check("màn hẹp: tab chưa chọn chỉ còn icon",
  /\.ws-rtabs \.cside-tab:not\(\.active\) \.ws-rtab-lbl\s*\{\s*display:\s*none/.test(narrow));
check("màn hẹp: nút X ghim góc trên phải, cùng hàng với tab",
  /\.ws-right > \.ws-panel-close\s*\{[^}]*position:\s*absolute/.test(narrow)
  && /\.ws-rtabs\s*\{[^}]*padding-right:/.test(narrow));
check("màn hẹp: X và tab cao bằng nhau (34px)",
  /\.ws-right > \.ws-panel-close\s*\{[^}]*height:\s*34px/.test(narrow)
  && /\.ws-rtabs \.cside-tab\s*\{[^}]*min-height:\s*34px/.test(narrow));
check("màn hẹp: X không còn nằm một hàng riêng (bỏ align-self:flex-end)",
  !/\.ws-panel-close\s*\{[^}]*align-self:\s*flex-end/.test(CCSS));

if (fails.length) { console.log("\n" + fails.length + " FAIL"); process.exit(1); }
console.log("\nALL PASS");
