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
  /claudeOn = !!\(await \(await fetch\("\/claude\/status"\)\)\.json\(\)\)\.connected/.test(CONSOLE_JS));
check("provOn: provider cli lay theo claudeOn, con lai lay theo configured",
  /const provOn = \(p\) => \(p\.kind === "cli" \? claudeOn : !!p\.configured\)/.test(CONSOLE_JS));
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
  const provOn = (p) => (p.kind === "cli" ? claudeOn : !!p.configured);
  return list.map((p, i) => ({ p, i }))
    .sort((a, b) => (provOn(b.p) - provOn(a.p)) || (a.i - b.i))
    .map((x) => x.p.id);
}
const DEFS = [
  { id: "anthropic-cli", kind: "cli", configured: true },   // server LUON tra true (khong co key_field)
  { id: "openai-oauth", kind: "oauth", configured: false },
  { id: "openrouter", kind: "api", configured: false },
  { id: "anthropic-api", kind: "api", configured: false },
  { id: "openai", kind: "api", configured: false },
  { id: "gemini", kind: "api", configured: true },
  { id: "groq", kind: "api", configured: true },
];

check("da ket noi len dau, giu thu tu goc trong tung nhom",
  JSON.stringify(order(DEFS, true)) === JSON.stringify(
    ["anthropic-cli", "gemini", "groq", "openai-oauth", "openrouter", "anthropic-api", "openai"]));

// Day la ly do phai hoi /claude/status: tin theo configured thi Claude chua dang nhap van
// nam chem che tren cung.
check("Claude CHUA dang nhap thi tut xuong nhom duoi",
  JSON.stringify(order(DEFS, false)) === JSON.stringify(
    ["gemini", "groq", "openai-oauth", "openrouter", "anthropic-api", "openai"].slice(0, 2)
      .concat(["anthropic-cli", "openai-oauth", "openrouter", "anthropic-api", "openai"])));

check("chua ket noi cai nao thi giu nguyen thu tu goc",
  JSON.stringify(order(DEFS.map((p) => ({ ...p, configured: false })), false))
    === JSON.stringify(DEFS.map((p) => p.id)));

check("ket noi HET thi cung giu nguyen thu tu goc",
  JSON.stringify(order(DEFS.map((p) => ({ ...p, configured: true })), true))
    === JSON.stringify(DEFS.map((p) => p.id)));

if (fails.length) { console.log("\nFAIL - test_prov_order: " + fails.length + " loi"); process.exit(1); }
console.log("\nOK - test_prov_order: tat ca pass");
