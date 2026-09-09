/* Link `file:///brains/Brain%20Default/wiki/x.md` trong chat phải bấm mở đúng file.

       node tests/js/test_link_file_uri.js

   Chủ repo báo (2026-09-09): bấm link wiki vừa ingest bằng Antigravity thì dashboard bật khung
   "Không tìm thấy file - Link trỏ tới file:///brains/Brain Default/wiki/... nhưng chỗ đó không
   có gì. Có lẽ là file này: wiki/...". Harness của Antigravity dặn model "dùng link markdown
   với giao thức file://", nên dạng này về đều.

   Gốc ở dashboard: appFileRef() chỉ nhận http(s), /files/raw, /brains/<brain>/, /brain/;
   isVaultRel() thì loại http/mailto/data/blob và "/" - chuỗi bắt đầu bằng "file:" không khớp
   nhánh nào nên bị coi là ĐƯỜNG TƯƠNG ĐỐI TRONG VAULT, ra data-vault-path="file:///brains/..."
   rồi console.js ghép tiền tố trần thành "brains/Brain Default/file:///brains/..." → 404.

   Nay: gỡ giao thức + giải mã %xx, tìm tên brain đang chat trong đường dẫn máy chủ rồi lấy
   phần sau nó (Docker /brains/<brain>/..., cài tay /home/x/brains/<brain>/..., Windows
   C:/.../<brain>/...). Không thấy tên brain → coi cả chuỗi là tương đối (model hay viết
   file:///wiki/x.md). Trỏ sang brain KHÁC → vẫn là link vault để cú bấm ra khung "không thấy
   file" có gợi ý, thay vì tab mới 404. console.js gỡ lại lần nữa ở openVaultPath/JavisOpenNote
   cho đường deep-link và chip file đang mở. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
global.currentBrainPath = () => "brain";          // brain mặc định → tên "Brain Default"
const { mdToHtml, appFileRef, fileUriPath } = require(path.join(ROOT, "dashboard", "chat-render.js"));
const CR = fs.readFileSync(path.join(ROOT, "dashboard", "chat-render.js"), "utf8");
const CONSOLE = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");

const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them != null ? "  [" + String(them).slice(0, 200) + "]" : ""));
  if (!cond) fails.push(name);
};
// data-vault-path là thứ cú bấm thật đem đi mở file (moFileVault) - soi đúng nó.
const vaultPath = (md, brain) => {
  const m = /data-vault-path="([^"]*)"/.exec(mdToHtml(md, brain));
  return m ? m[1] : null;
};
const TEN = "wiki/30 Ngày Làm Chủ Antigravity (CES Global).md";
const ENC = "wiki/30%20Ng%C3%A0y%20L%C3%A0m%20Ch%E1%BB%A7%20Antigravity%20(CES%20Global).md";

// ============================================================
// 1. CHÍNH cái link chủ repo báo
// ============================================================
check("CANARY: file:///brains/Brain%20Default/... → đường tương đối gốc brain, đã giải mã",
  vaultPath("[x](file:///brains/Brain%20Default/" + ENC + ")") === TEN,
  vaultPath("[x](file:///brains/Brain%20Default/" + ENC + ")"));
check("khoảng trắng trần trong file:// cũng ra đúng",
  vaultPath("[x](file:///brains/Brain Default/wiki/a b.md)") === "wiki/a b.md");
check("file://localhost/... cũng gỡ được",
  vaultPath("[x](file://localhost/brains/Brain%20Default/wiki/a.md)") === "wiki/a.md");
check("cài tay: /home/x/brains/<brain>/... → lấy phần sau tên brain",
  vaultPath("[x](file:///home/u/javis/brains/Brain%20Default/wiki/a.md)") === "wiki/a.md");
check("Windows: file:///C:/.../<brain>/... → lấy phần sau tên brain",
  vaultPath("[x](file:///C:/Users/q/brains/Brain%20Default/wiki/a.md)") === "wiki/a.md");
check("file:///wiki/x.md (không có tên brain) → coi là tương đối",
  vaultPath("[x](file:///wiki/a.md)") === "wiki/a.md");
check("brain khác đang chat: tên brain lấy theo hội thoại (tham số brain của mdToHtml)",
  vaultPath("[x](file:///brains/My%20Brain/wiki/a.md)", "brains/My Brain") === "wiki/a.md");
check("trỏ sang brain KHÁC: vẫn là link vault (bấm ra khung không-thấy-file có gợi ý), không mở nhầm file trùng tên",
  appFileRef("file:///brains/Khac/wiki/a.md") === null
  && /class="jv-floc/.test(mdToHtml("[x](file:///brains/Khac/wiki/a.md)")));
check("link file:// KHÔNG còn mang data-vault-path bắt đầu bằng file:",
  !/data-vault-path="file:/i.test(mdToHtml("[x](file:///brains/Brain%20Default/wiki/a.md) [y](file:///brains/Khac/b.md)")));

// ============================================================
// 2. Ảnh và backtick
// ============================================================
const anh = mdToHtml("![s](file:///brains/Brain%20Default/attachments/so%20do.png)");
check("ảnh file:// → src đi qua /files/raw đúng brain, data-vault-path tương đối",
  /src="\/files\/raw\?brain=brain&amp;path=attachments%2Fso%20do\.png"/.test(anh)
  && /data-vault-path="attachments\/so do\.png"/.test(anh), anh);
check("backtick chứa file:// → link mở file (chữ giữ nguyên)",
  vaultPath("`file:///brains/Brain%20Default/wiki/a.md`") === "wiki/a.md");

// ============================================================
// 3. Không phá những gì đang chạy
// ============================================================
check("link vault mã hoá %20 vẫn đúng", vaultPath("[x](07%20-%20Wiki/LLM%20Wiki.md)") === "07 - Wiki/LLM Wiki.md");
check("URL http không bị coi là file", vaultPath("[x](https://a.vn/b.md)") === null && fileUriPath("https://a.vn/b.md") === null);
check("fileUriPath: file: không có dấu / theo sau không phải URI", fileUriPath("file:a.md") === null && fileUriPath("file:") === null);
check("fileUriPath: /C:/x → C:/x", fileUriPath("file:///C:/x/y.md") === "C:/x/y.md");
check("isVaultRel loại file:", /isVaultRel[\s\S]{0,200}file:\|/.test(CR));

// ============================================================
// 4. console.js: deep-link và chip file đang mở cũng gỡ file://
// ============================================================
check("chat-render xuất JavisFileRef cho console.js gọi lại", /window\.JavisFileRef = appFileRef/.test(CR));
check("openVaultPath gỡ file:// trước khi ghép tiền tố trần",
  /function openVaultPath\(fullPath\) \{\s*fullPath = _goFileUri\(fullPath\);/.test(CONSOLE));
check("JavisOpenNote gỡ file:// trước khi ghép tiền tố trần",
  /window\.JavisOpenNote = function \(brainRel\) \{\s*brainRel = _goFileUri\(brainRel\);/.test(CONSOLE));
check("_goFileUri gọi JavisFileRef, có đường lui khi chat-render chưa nạp",
  /function _goFileUri\(p\)[\s\S]{0,400}window\.JavisFileRef[\s\S]{0,300}replace\(\/\^file:/.test(CONSOLE));

console.log("");
if (fails.length) { console.log(fails.length + " test HỎNG: " + fails.join(", ")); process.exit(1); }
console.log("Tất cả test link_file_uri đã qua.");
