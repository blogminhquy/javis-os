// Thu tu card provider o trang Models: DA KET NOI len dau, chua ket noi xuong duoi.
// Trich dung bieu thuc sort tu console.js de test khong troi khi code doi (neu ai sua
// console.js ma quen file nay, doan grep ben duoi do ngay).
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const CONSOLE_JS = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");

const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- console.js phai co dung co che nay ----
check("renderModels hoi /claude/status de biet Claude co dang nhap that khong",
  /claudeOn = !!\(await \(await fetch\("\/claude\/status", \{ signal: ac\.signal \}\)\)\.json\(\)\)\.connected/.test(CONSOLE_JS));
// 06/09: luot goi nay CHAN net ve dau tien va truoc day khong co timeout, nen mot `claude`
// treo la trang Models ket o "Dang tai..." vinh vien (fetch treo thi catch khong cuu duoc vi
// no khong reject). freshSettings ngay tren da co AbortController tu lau; cho nay phai co.
check("va co TRAN CHO, khong de ket man hinh khi claude treo",
  /new AbortController\(\)[\s\S]{0,200}ac\.abort\(\)[\s\S]{0,400}\/claude\/status/.test(CONSOLE_JS));
// Luat doi tu 0.28.5: kind "cli" nay co HAI bo nao (Claude Code, Gemini CLI). /claude/status
// chi noi ve Claude, nen lay no cho ca hai la the Gemini bao "chua ket noi" du da dang nhap
// Google - hoac nguoc lai. So theo ID chu khong theo kind.
check("provOn: rieng anthropic-cli lay theo claudeOn, con lai lay theo configured",
  /const provOn = \(p\) => \(p\.id === "anthropic-cli" \? claudeOn : !!p\.configured\)/.test(CONSOLE_JS));
check("sort co tiebreak theo chi so goc (on dinh, khong phu thuoc engine)",
  /\.sort\(\(a, b\) => \(provOn\(b\.p\) - provOn\(a\.p\)\) \|\| \(a\.i - b\.i\)\)/.test(CONSOLE_JS));
check("danh sach card dung ban da sap xep", CONSOLE_JS.includes("${provList.map(provCard).join(\"\")}"));
check("hop Doi model chinh cung dung ban da sap xep",
  CONSOLE_JS.includes("openModelPicker(provList, main,"));
check("hop Doi model viec nen cung dung ban da sap xep",
  CONSOLE_JS.includes("openModelPicker(provList, { provider: auxProv, model: aux }"));
// Chi soi cho GOI, khong soi dong dinh nghia `function openModelPicker(providers, ...)`.
check("KHONG con cho nao render thang mang providers chua sap",
  !CONSOLE_JS.includes("providers.map(provCard)")
  && !/=>\s*openModelPicker\(providers,/.test(CONSOLE_JS));

// ---- Hanh vi sort (ban sao dung nguyen bieu thuc tren) ----
function order(list, claudeOn) {
  const provOn = (p) => (p.id === "anthropic-cli" ? claudeOn : !!p.configured);
  return list.map((p, i) => ({ p, i }))
    .sort((a, b) => (provOn(b.p) - provOn(a.p)) || (a.i - b.i))
    .map((x) => x.p.id);
}
const DEFS = [
  { id: "anthropic-cli", kind: "cli", configured: true },   // server LUON tra true (khong co key_field)
  { id: "openai-oauth", kind: "oauth", configured: false },
  // Cung kind "cli" nhung KHONG phai Claude: server da tinh `configured` that (doc file dang
  // nhap Google), nen no khong duoc dinh theo claudeOn.
  { id: "gemini-cli", kind: "cli", configured: true },
  { id: "openrouter", kind: "api", configured: false },
  { id: "anthropic-api", kind: "api", configured: false },
  { id: "openai", kind: "api", configured: false },
  { id: "gemini", kind: "api", configured: true },
  { id: "groq", kind: "api", configured: true },
];

check("da ket noi len dau, giu thu tu goc trong tung nhom",
  JSON.stringify(order(DEFS, true)) === JSON.stringify(
    ["anthropic-cli", "gemini-cli", "gemini", "groq",
     "openai-oauth", "openrouter", "anthropic-api", "openai"]));

// Day la ly do phai hoi /claude/status: tin theo configured thi Claude chua dang nhap van
// nam chem che tren cung.
check("Claude CHUA dang nhap thi tut xuong nhom duoi",
  JSON.stringify(order(DEFS, false)) === JSON.stringify(
    ["gemini-cli", "gemini", "groq",
     "anthropic-cli", "openai-oauth", "openrouter", "anthropic-api", "openai"]));

// CANARY cua chinh bug vua sua: Gemini CLI da dang nhap thi phai o nhom TREN, ke ca khi Claude
// chua dang nhap. Lay claudeOn cho ca kind "cli" la no bi day xuong duoi oan.
check("CANARY: Gemini CLI da dang nhap van len dau du Claude chua dang nhap",
  order(DEFS, false)[0] === "gemini-cli");

check("chua ket noi cai nao thi giu nguyen thu tu goc",
  JSON.stringify(order(DEFS.map((p) => ({ ...p, configured: false })), false))
    === JSON.stringify(DEFS.map((p) => p.id)));

check("ket noi HET thi cung giu nguyen thu tu goc",
  JSON.stringify(order(DEFS.map((p) => ({ ...p, configured: true })), true))
    === JSON.stringify(DEFS.map((p) => p.id)));

if (fails.length) { console.log("\nFAIL - test_prov_order: " + fails.length + " loi"); process.exit(1); }
console.log("\nOK - test_prov_order: tat ca pass");
