/* Trang Cộng sự: MỘT ngăn tài liệu, công tắc "của trợ lý / chỉ cuộc này" ở đầu.

       node tests/js/test_tai_lieu_cong_su_mot_ngan.js

   Chủ repo báo 23/09: trang Cộng sự có hai lối vào tài liệu trông giống hệt nhau (nút "File &
   link" trên thanh đầu = tài liệu của CUỘC, nút trong Cài đặt = tài liệu của TRỢ LÝ), cùng
   khung, cùng hai tab File/Link, chỉ khác một câu ghi chú nhỏ ở cuối. Gắn một chỗ rồi đi tìm
   ở chỗ kia. Nay cả hai nút mở chung một ngăn, phạm vi chọn bằng công tắc có số lượng. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const rd = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const SU = rd("dashboard/sessions-ui.js");
const WS = rd("dashboard/workspace.js");
const ST = rd("dashboard/studio.js");
const CSS = rd("dashboard/style.css");
const VI = JSON.parse(rd("dashboard/i18n/vi.json"));
const EN = JSON.parse(rd("dashboard/i18n/en.json"));

const fails = [];
const check = (ten, ok) => { console.log((ok ? "ok   " : "FAIL ") + ten); if (!ok) fails.push(ten); };

// ---- 1. Một lối vào chung ----
check("sessions-ui xuất moTaiLieu", /moTaiLieu: openTaiLieuCongSu/.test(SU));
check("nút trên thanh đầu trang Cộng sự mở ngăn có công tắc (tab Trợ lý)",
  /S\.loai === "agent" && x && window\.JavisChatSide\.moTaiLieu\) window\.JavisChatSide\.moTaiLieu\(x\.slug, x\.name\)/.test(WS));
check("nút trong Cài đặt trợ lý (trang Cộng sự) cũng đi đường đó, đứng sẵn ở phạm vi trợ lý",
  /opts\.host && window\.JavisChatSide && window\.JavisChatSide\.moTaiLieu\)\s*\n\s*window\.JavisChatSide\.moTaiLieu\(a\.slug, a\.name \|\| a\.slug, "agent"\)/.test(ST));
check("Studio (không có cuộc liên quan) vẫn mở ngăn riêng của trợ lý", /window\.JavisChatSide\.moKhungAgent\(a\.slug/.test(ST));

// ---- 2. Công tắc ----
check("khung ngăn kéo có chỗ cho công tắc", /'<div class="pd-scope" hidden><\/div>'/.test(SU));
check("veDrawer vẽ công tắc mỗi lần", /veThanhPhamVi\(\);/.test(SU.split("function veDrawer()")[1] || ""));
check("công tắc chỉ hiện khi mở từ trang Cộng sự",
  /if \(!pdCongSu \|\| !\(pdLaAgent\(\) \|\| pdLaCuoc\(\)\)\) \{ host\.hidden = true;/.test(SU));
check("mở project thì tắt công tắc", /pdCheDo = "project";\s*\n\s*pdCongSu = null;/.test(SU));
check("đóng ngăn thì tắt công tắc",
  /pdOnboard = false;\s*\n\s*pdCongSu = null;\s*\n\s*\}/.test(SU.split("function closeProjDrawer()")[1] || ""));
check("mở cuộc/trợ lý kiểu cũ (không từ Cộng sự) cũng tắt công tắc",
  /if \(!giuCongSu\) pdCongSu = null;[\s\S]*if \(!giuCongSu\) pdCongSu = null;/.test(SU));
check("chưa có cuộc thì nút Chỉ cuộc này bị khoá, không bấm ra lỗi",
  /if \(pv === "cuoc" && !currentId\(\)\) return;/.test(SU) && /coCuoc \? soTaiLieu\(cuocTS\) : null, !coCuoc\)/.test(SU));
check("nhớ phạm vi lần trước", /localStorage\.setItem\(KHOA_PHAM_VI, pv\)/.test(SU));
check("mặc định là của trợ lý", /=== "cuoc" \? "cuoc" : "agent"/.test(SU));
check("nạp phạm vi kia song song để công tắc có số ngay",
  /napCuocTS\(\)\.then\(function \(\) \{ if \(pdCongSu\) veThanhPhamVi\(\); \}\)/.test(SU)
  && /napAgentTS\(slug, ten\)\.then\(function \(\) \{ if \(pdCongSu\) veThanhPhamVi\(\); \}\)/.test(SU));
check("không nhắc lại ghi chú phạm vi ở cuối khi đã có công tắc", /if \(pdCongSu\) return "";/.test(SU));
check("icon dùng tên có trong bộ icon",
  /nut\("cuoc", "message-circle"/.test(SU) && rd("dashboard/icons.manifest.json").includes('"message-circle"'));

// ---- 3. Chữ ----
const KEYS = ["pds.agent", "pds.agent_sub", "pds.chat", "pds.chat_sub", "pds.chat_none_short",
  "pds.chat_none", "pds.hint_agent", "pds.hint_chat"];
check("đủ khoá tiếng Việt", KEYS.every((k) => VI[k]));
check("đủ khoá tiếng Anh", KEYS.every((k) => EN[k]));
check("câu gợi ý nói rõ gắn vào ĐÂU", /TRỢ LÝ/.test(VI["pds.hint_agent"]) && /RIÊNG CUỘC NÀY/.test(VI["pds.hint_chat"]));
check("nút trên thanh đầu đổi tên thành Tài liệu", VI["ws.files_links"] === "Tài liệu");
check("ghi chú của trợ lý không còn chỉ sang nút File & link cũ", !/File & link/.test(VI["ags.note"]));
check("không có gạch ngang dài trong chữ mới",
  KEYS.every((k) => !/[–—]/.test(VI[k] + EN[k])));

// ---- 4. CSS: chữ đọc được trên điện thoại ----
check("nhãn công tắc 16px", /\.pd-sc-txt b \{ font-size: 16px;/.test(CSS));
check("hai ô chia đều", /\.pd-sc-row \{ display: grid; grid-template-columns: 1fr 1fr;/.test(CSS));

console.log();
if (fails.length) { console.log("FAIL " + fails.length + ": " + fails.join("; ")); process.exit(1); }
console.log("Tất cả xanh.");
