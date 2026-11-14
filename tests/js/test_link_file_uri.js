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

// ============================================================
// 5. IDE line suffix on a file link (issue 1390): `agents/x.md#L66-L75` opens agents/x.md
// ============================================================
const { splitLineSuffix } = require(path.join(ROOT, "dashboard", "chat-render.js"));
const vm = require("vm");
check("CANARY: [x](agents/x.md#L66-L75) opens agents/x.md, not a file named with the suffix",
  vaultPath("[x.md](agents/x.md#L66-L75)") === "agents/x.md", vaultPath("[x.md](agents/x.md#L66-L75)"));
check("the #open= deep link of that link carries the bare path too",
  /href="#open=agents%2Fx\.md"/.test(mdToHtml("[x.md](agents/x.md#L66-L75)")));
check("the cut suffix stays on the link for the editor's save",
  /data-vault-line="#L66-L75"/.test(mdToHtml("[x.md](agents/x.md#L66-L75)")));
for (const [inp, want] of [["a.md#L66", "a.md"], ["a.md#l66-l75", "a.md"], ["a.md#L66-75", "a.md"],
  ["a.md#L66C3", "a.md"], ["a.md#L66C3-L70C1", "a.md"], ["a.md#lien-he", "a.md#lien-he"],
  ["a.md#L5-intro", "a.md#L5-intro"], ["a.md#Lab", "a.md#Lab"], ["a#L5/b.md", "a#L5/b.md"]]) {
  check("splitLineSuffix(" + inp + ") -> " + want, splitLineSuffix(inp).path === want, splitLineSuffix(inp).path);
}
check("a heading anchor keeps the old link exactly (no data-vault-line)",
  vaultPath("[x](wiki/a.md#lien-he)") === "wiki/a.md#lien-he" && !/data-vault-line/.test(mdToHtml("[x](wiki/a.md#lien-he)")));
check("a line suffix on a download file (pdf) does not end up in the download URL",
  !/%23L/i.test(mdToHtml("[x](exports/a.pdf#L3)")) && vaultPath("[x](exports/a.pdf#L3)") === "exports/a.pdf");

// console.js openVaultPath: the deep link and the click both go through it. Run it for real.
const grabFn = (src, sig) => {
  const i = src.indexOf(sig);
  return i < 0 ? "" : src.slice(i, src.indexOf("\n  }\n", i) + 4);
};
const lineRe = (/\n  const LINE_SUFFIX_RE = [^\n]+/.exec(CONSOLE) || [""])[0];
const exts = ["VT_IMG_EXTS", "VT_TEXT_EXTS"].map((n) => (new RegExp("\\n  const " + n + " = \\[[^\\]]*\\];").exec(CONSOLE) || [""])[0]);
const ovp = grabFn(CONSOLE, "  function openVaultPath(fullPath) {");
check("console.js has LINE_SUFFIX_RE, the editor extension lists and openVaultPath", !!(lineRe && exts[0] && exts[1] && ovp));
const opened = [];
const vctx = {
  window: { JavisOpenNote: (p) => opened.push("note:" + p), JavisEditFile: (p) => opened.push("edit:" + p) },
  _goFileUri: (p) => p, isNarrow: () => false, _vtRaw: (p) => p,
  openFilesAt: (p) => opened.push("files:" + p),
};
vm.createContext(vctx);
vm.runInContext(lineRe + exts.join("") + "\n" + ovp + "\nthis.openVaultPath = openVaultPath;", vctx);
vctx.openVaultPath("agents/x.md#L66-L75");
check("CANARY: openVaultPath opens agents/x.md#L66-L75 in the editor as agents/x.md",
  opened[0] === "note:agents/x.md", opened);
opened.length = 0;
vctx.openVaultPath("Javis/loops#L5");
check("a folder with a stray suffix opens the folder on the Files page", opened[0] === "files:Javis/loops", opened);
opened.length = 0;
vctx.openVaultPath("wiki/a.md#lien-he");
check("openVaultPath leaves a heading anchor alone", /#lien-he$/.test(opened[0] || ""), opened);

// Saving a note from the editor's rendered view (turndown): the link is written back with its suffix.
const ruleSrc = (/_td\.addRule\("wikilink", (\{[\s\S]*?\n {8}\} \})\);/.exec(CONSOLE) || [])[1];
check("found the turndown rule for vault links", !!ruleSrc);
const rule = ruleSrc ? vm.runInNewContext("(" + ruleSrc + ")") : null;
const fakeA = (attrs) => ({ nodeName: "A", getAttribute: (k) => (k in attrs ? attrs[k] : null), querySelector: () => null });
check("CANARY: round trip keeps [x.md](agents/x.md#L66-L75)",
  rule && rule.replacement("x.md", fakeA({ "data-vault-path": "agents/x.md", "class": "jv-floc", "data-vault-line": "#L66-L75" }))
    === "[x.md](agents/x.md#L66-L75)");
check("a link without a suffix saves as before",
  rule && rule.replacement("x", fakeA({ "data-vault-path": "wiki/a.md", "class": "jv-floc" })) === "[x](wiki/a.md)");

console.log("");
// The default brain is a choice since 2026-11-09: "brain" is the folder the picker's default entry names, not always
// "Brain Default". brains-ui.js puts that folder on the entry (data-brain-name).
global.document = { querySelector: (q) => q === '#graphSource option[value="brain"]' ? { dataset: { brainName: "Shop" } } : null };
check("default brain chosen by the owner: its own folder is cut from the link",
  vaultPath("[x](file:///brains/Shop/wiki/a.md)") === "wiki/a.md");
delete global.document;

if (fails.length) { console.log(fails.length + " test HỎNG: " + fails.join(", ")); process.exit(1); }
console.log("Tất cả test link_file_uri đã qua.");
