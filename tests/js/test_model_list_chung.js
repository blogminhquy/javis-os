/* Thân bảng chọn model dùng CHUNG (dashboard/model-list.js).

       node tests/js/test_model_list_chung.js

   Trước 0.62.3 có hai bản: thanh model dưới khung chat (model-picker.js) vẽ đầy đủ ô tìm +
   ổ khoá, còn ô Model của trợ lý (studio.js) là một <select> thuần - không tìm được, và nhà
   chưa cắm key bị LỌC MẤT nên người dùng không biết là có nhà đó. Chủ repo báo 21/09.

   Gộp lại một thân thay vì chép markup sang, vì chép là hai bản trôi lệch nhau ngay lần sửa
   sau. Test này chạy THẬT hàm render với fetch giả, không chỉ soi chuỗi trong file. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- Sân khấu giả: window + t() + ic() + fetch ----
const goi = [];      // ghi lại mọi URL đã hỏi, để kiểm chuyện nạp LƯỜI + cache
const KHO = {
  "anthropic-cli": ["opus", "sonnet", "haiku"],
  "openai-oauth": ["gpt-5.6-codex", "gpt-5.5-codex"],
};
const sandbox = {
  window: {
    t: (k) => "T:" + k,
    ic: (n) => `<i data-ic="${n}"></i>`,
  },
  fetch: async (url) => {
    goi.push(url);
    const pid = decodeURIComponent((url.match(/provider=([^&]+)/) || [])[1] || "");
    if (pid === "no-net") throw new Error("mang hong");
    return { json: async () => ({ models: KHO[pid] || [] }) };
  },
  console,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(ROOT, "dashboard", "model-list.js"), "utf8"), sandbox);
const ML = sandbox.window.JavisModelList;
check("module tự gắn vào window.JavisModelList", !!(ML && ML.render && ML.models));

const PROVS = [
  { id: "anthropic-cli", label: "ANTHROPIC OAUTH (CLAUDE CODE)", configured: true },
  { id: "openai-oauth", label: "OPENAI OAUTH (CHATGPT)", configured: true },
  { id: "anthropic-api", label: "ANTHROPIC (API)", configured: false },
  { id: "no-net", label: "NHA HONG MANG", configured: true },
];

(async () => {
  // ---- 1. Ô tìm luôn có (đây là thứ ô <select> cũ không có) ----
  let h = await ML.render({ providers: PROVS, expanded: "anthropic-cli", searchId: "xSearch" });
  check("có ô tìm, đúng id người gọi đặt",
    h.includes('class="mb-search"') && h.includes('id="xSearch"'), h.slice(0, 120));
  check("ô tìm dùng đúng khoá i18n của bảng chọn chính", h.includes("T:mpick.search_ph"));

  // ---- 2. Nhà CHƯA cắm key: hiện ra, có ổ khoá, KHÔNG bấm sổ ra được ----
  check("nhà chưa cắm key vẫn hiện trong danh sách", h.includes("ANTHROPIC (API)"));
  check("nhà chưa cắm key mang lớp .off", /class="mb-prov off" data-prov=""/.test(h));
  check("nhà chưa cắm key vẽ ổ khoá", h.includes('data-ic="lock"'));
  check("nhà chưa cắm key kèm lối đi mở khoá", h.includes('data-goto="models"') && h.includes("T:mpick.add_key"));
  check("nhà chưa cắm key KHÔNG có data-prov (bấm vào không sổ ra)",
    h.indexOf('data-prov="anthropic-api"') === -1);

  // ---- 3. Nhà đang sổ ra thì liệt kê model; nhà khác thì không ----
  check("nhà đang sổ ra liệt kê model của nó", h.includes('data-model="sonnet"'));
  check("nhà chưa sổ ra KHÔNG nạp model (nạp lười, không hỏi cả lượt như bản cũ)",
    h.indexOf('data-model="gpt-5.6-codex"') === -1
    && !goi.some(u => u.includes("openai-oauth")), goi.join(" | "));

  // ---- 4. Model đang chọn được đánh dấu ----
  h = await ML.render({ providers: PROVS, expanded: "anthropic-cli",
                        selected: { provider: "anthropic-cli", model: "opus" } });
  check("model đang chọn có lớp .cur và dấu tick",
    /class="mb-item cur" data-prov="anthropic-cli" data-model="opus"/.test(h)
    && h.includes('data-ic="check"'));
  check("model KHÁC không bị đánh dấu nhầm",
    /class="mb-item " data-prov="anthropic-cli" data-model="sonnet"/.test(h));

  // ---- 5. Lọc theo chữ ----
  h = await ML.render({ providers: PROVS, expanded: "anthropic-cli", filter: "hai" });
  check("lọc giữ model khớp", h.includes('data-model="haiku"'));
  check("lọc bỏ model không khớp", h.indexOf('data-model="sonnet"') === -1);
  h = await ML.render({ providers: PROVS, expanded: "anthropic-cli", filter: "zzz" });
  check("lọc không ra gì thì nói 'không khớp', không để trống khó hiểu",
    h.includes("T:mpick.no_match"));

  // ---- 6. Một nhà hỏng mạng không kéo cả bảng chết ----
  h = await ML.render({ providers: PROVS, expanded: "no-net" });
  check("nhà hỏng mạng: bảng vẫn dựng được, chỉ nhà đó rỗng",
    h.includes("T:mpick.no_list") && h.includes("ANTHROPIC OAUTH (CLAUDE CODE)"));

  // ---- 7. Cache: hỏi lại cùng một nhà không gọi mạng lần nữa ----
  const truoc = goi.filter(u => u.includes("anthropic-cli")).length;
  await ML.render({ providers: PROVS, expanded: "anthropic-cli" });
  const sau = goi.filter(u => u.includes("anthropic-cli")).length;
  check("có cache: vẽ lại không gọi /provider/models thêm lần nào", truoc === sau, truoc + " -> " + sau);
  ML.clearCache();
  await ML.render({ providers: PROVS, expanded: "anthropic-cli" });
  check("clearCache() thì hỏi lại thật",
    goi.filter(u => u.includes("anthropic-cli")).length === sau + 1);

  // ---- 8. extraTop cho người gọi chèn hàng riêng (Studio chèn hàng "Mặc định") ----
  h = await ML.render({ providers: PROVS, expanded: "anthropic-cli", extraTop: "<b>HANG-RIENG</b>" });
  check("extraTop nằm NGAY DƯỚI ô tìm, trên danh sách nhà",
    h.indexOf("HANG-RIENG") > h.indexOf('class="mb-search"')
    && h.indexOf("HANG-RIENG") < h.indexOf('class="mb-prov'));

  // ---- 9. Thoát HTML cho tên model (tên lạ không được chui thành thẻ) ----
  KHO["anthropic-cli"] = ['a"><script>x</script>'];
  ML.clearCache();
  h = await ML.render({ providers: PROVS, expanded: "anthropic-cli" });
  check("tên model được thoát HTML", h.indexOf("<script>") === -1, h.slice(h.indexOf("mb-item"), 200));

  console.log();
  if (fails.length) {
    console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
    process.exit(1);
  }
  console.log("OK - test_model_list_chung: tat ca pass");
})();
