/* Ngăn kéo "File & link" mở được cho MỘT TRỢ LÝ, không chỉ cho project và cuộc trò chuyện.

       node tests/js/test_tai_san_tro_ly.js

   Chủ repo 21/09: "agent cũng sẽ thêm được file và link kiểu như bên gom project của trò
   chuyện ấy". Điều đáng canh KHÔNG phải là "có nút chưa" mà là CÓ ĐÚNG MỘT ngăn kéo: chép
   thêm một bản thứ hai cho trang Cộng sự thì hai bản trôi lệch nhau ngay lần sửa đầu (sửa
   luật ghim bên này, quên bên kia, và người dùng gặp hai cái khung trông y hệt nhau mà hành
   xử khác nhau).

   Ba bẫy IM LẶNG được canh riêng:
   - Thiếu `brain` trong lời gọi ghi: trợ lý là file trong brain, không như project và hội
     thoại (nằm trong DB, server tự tra ra brain). Thiếu là thao tác rơi vào brain mặc định.
   - Khoá từ điển theo chế độ: câu hỏi "gỡ khỏi project?" hiện lên khi đang gỡ khỏi trợ lý.
   - Trợ lý CHƯA LƯU thì chưa có slug để gắn vào, nút phải đứng im kèm lý do. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const SU = fs.readFileSync(path.join(ROOT, "dashboard", "sessions-ui.js"), "utf8");
const ST = fs.readFileSync(path.join(ROOT, "dashboard", "studio.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

const fails = [];
const check = (ten, ok, them) => {
  console.log((ok ? "ok   " : "FAIL ") + ten + (ok || them === undefined ? "" : "  [" + them + "]"));
  if (!ok) fails.push(ten);
};

// ============================================================
// 1. MỘT ngăn kéo, ba chế độ
// ============================================================
check("có chế độ agent", /function pdLaAgent\(\) \{ return pdCheDo === "agent"; \}/.test(SU));
check("mở khung cho một trợ lý", /async function openAgentDrawer\(slug, ten\)/.test(SU));
check("và nạp danh sách từ route của trợ lý",
  /fetch\("\/agents\/" \+ encodeURIComponent\(slug\) \+ "\/assets\?brain="/.test(SU));
check("pdApi trỏ đúng gốc của trợ lý",
  /pdLaAgent\(\)\) return "\/agents\/" \+ encodeURIComponent\(\(agentTS \|\| \{\}\)\.slug \|\| ""\) \+ "\/assets"/.test(SU));
// CANARY: không có bản ngăn kéo thứ hai cho trang Cộng sự.
check("CANARY: chỉ có MỘT hàm vẽ ngăn kéo", (SU.match(/function veDrawer\(/g) || []).length === 1);
check("CANARY: không dựng pane riêng cho trợ lý",
  !/function paneAgentFile/.test(SU) && !/function paneAgentLink/.test(SU));

// ============================================================
// 2. `brain` đi theo MỌI lời gọi ghi của chế độ trợ lý
// ============================================================
// Project và hội thoại nằm trong DB nên server tự tra ra brain của chúng. Trợ lý là một FILE,
// nên thiếu `brain` là mọi thao tác rơi vào brain mặc định - im lặng và sai.
check("có chỗ gắn trường đi kèm theo chế độ",
  /function pdKem\(\) \{ return pdLaAgent\(\) \? \{ brain: brain\(\) \} : \{\}; \}/.test(SU));
check("và mọi lời gọi ghi đi qua pdPost (đã gộp sẵn trường đó)",
  /function pdPost\(duoi, fields\)[\s\S]{0,220}post\(pdApi\(\) \+ duoi, body\)/.test(SU));
["themFile", "goNhanhFile", "ghimFile", "goFile", "themLink", "ghimLink", "goLink"].forEach((fn) => {
  const than = (SU.match(new RegExp("async function " + fn + "\\([\\s\\S]*?\\n  \\}")) || [""])[0];
  check(fn + " ghi qua pdPost", /pdPost\(/.test(than), than.slice(0, 80));
});

// ============================================================
// 3. Chữ trên màn hình nói ĐÚNG thứ đang thao tác
// ============================================================
check("khoá từ điển chọn theo chế độ",
  /function pdK\(ten\) \{ return \(pdLaCuoc\(\) \? "cts\." : pdLaAgent\(\) \? "ags\." : "proj\."\) \+ ten; \}/.test(SU));
// Mỗi khoá gọi qua pdK phải có ĐỦ ở cả ba tiền tố: thiếu một cái là chữ trên màn hình thành
// chính cái mã khoá, mà test i18n không bắt được (khoá dựng động, không phải chuỗi literal).
["files_empty", "links_empty", "pin_note", "err_load", "remove",
 "confirm_remove_file", "confirm_remove_link"].forEach((k) => {
  ["proj.", "cts.", "ags."].forEach((ns) => {
    check(`khoá ${ns}${k} có trong cả vi và en`, !!VI[ns + k] && !!EN[ns + k]);
  });
});
check("câu gỡ của trợ lý nói đúng là gỡ khỏi TRỢ LÝ, file vẫn còn trong brain",
  /trợ lý/.test(VI["ags.confirm_remove_file"] || "")
  && /vẫn còn trong brain/.test(VI["ags.confirm_remove_file"] || ""));
check("chú thích nói rõ phạm vi: tài liệu thuộc về trợ lý, không riêng một cuộc",
  /quy trình/.test(VI["ags.note"] || ""));
check("trần nạp trong chú thích khớp server",
  /2000/.test(VI["ags.pin_note"] || "")
  && /PROJECT_GHIM_FILE_MAX = 2000/.test(
       fs.readFileSync(path.join(ROOT, "server", "main.py"), "utf8")));

// ============================================================
// 4. Đầu khung và nút không nói chuyện của chế độ khác
// ============================================================
check("trợ lý không có tab Hướng dẫn (prompt của nó đã ở trình sửa)",
  /if \(pdLaCuoc\(\) \|\| pdLaAgent\(\)\) return \[tabFile, tabLink\];/.test(SU));
check("không bày nút đổi tên trong chế độ trợ lý",
  /\.pd-ren"\)\.style\.display = \(laCuoc \|\| pdLaAgent\(\)\) \? "none" : ""/.test(SU));
check("không bày nút ghim HỘI THOẠI trong chế độ trợ lý",
  /if \(pdLaAgent\(\)\) \{ b\.style\.display = "none"; return; \}/.test(SU));
check("chip số file/link chỉ nạp lại cho project",
  /function napLaiChip\(\) \{ if \(pdCheDo === "project"\) loadProjects\(\); \}/.test(SU));
check("đổi ngôn ngữ giữa chừng thì mở lại ĐÚNG chế độ trợ lý",
  /else if \(dangMo && ag && ag\.slug\) openAgentDrawer\(ag\.slug, ag\.name\);/.test(SU));

// ============================================================
// 5. Lối vào: nút trong Cài đặt trợ lý
// ============================================================
check("trang Cộng sự gọi được ngăn kéo của trợ lý",
  /moKhungAgent: openAgentDrawer/.test(SU));
check("trình sửa trợ lý có nút mở khung tài liệu", /id="agAssets"/.test(ST));
check("nút gọi đúng cầu nối, không dựng khung riêng",
  /window\.JavisChatSide\.moKhungAgent\(a\.slug, a\.name \|\| a\.slug\)/.test(ST));
// Trợ lý chưa lưu thì chưa có slug để gắn vào. Ẩn nút đi thì người dùng tưởng không có chức
// năng; để nút bấm được thì bấm vào không có gì xảy ra. Đứng im kèm một câu là đường thứ ba.
check("trợ lý chưa lưu thì nút đứng im", /a && a\.slug \? "" : " disabled"/.test(ST));
check("và nói rõ vì sao", /Lưu trợ lý/.test(VI["studio.assets_new"] || ""));
check("có kiểu cho hàng tài liệu trong form", /\.agent-editor \.ag-assets \{/.test(CSS));

// ============================================================
// 6. Viền tiêu điểm không bị cắt (lỗi chủ repo báo cùng lượt)
// ============================================================
// Ngăn phải `overflow:auto`, mà viền tiêu điểm của ô nhập nằm HẲN ngoài hộp viền (outline 2px
// + outline-offset 2px = 4px). Không chừa đệm thì bấm vào ô nào cũng thấy viền cam lẹm hai bên.
check("ngăn cột phải chừa đệm cho viền tiêu điểm",
  /\.ws-rpane \{ padding:4px; margin:0 -4px; \}/.test(CSS));
check("và đệm đó đủ cho đúng bề dày viền đang dùng",
  /\.agent-editor :is\(input,select,textarea\):focus-visible \{ outline:2px solid var\(--accent\); outline-offset:2px; \}/.test(CSS));

if (fails.length) {
  console.log(`\nFAIL ${fails.length} muc: ` + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_tai_san_tro_ly: tat ca pass");
