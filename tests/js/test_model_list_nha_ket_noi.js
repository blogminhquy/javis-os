// Bảng chọn model (model-list.js), ba luật chủ repo chốt 27/09:
//  1. Nhà ĐÃ KẾT NỐI đứng đầu, nhà còn khoá xuống dưới.
//  2. expanded rỗng = thu hết (bấm lại tên nhà đang mở là thu).
//  3. Có chữ tìm thì tìm trên MỌI nhà đã kết nối; trùng tên nhà thì hiện cả nhà đó.
// Chạy: node tests/js/test_model_list_nha_ket_noi.js
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "model-list.js"), "utf8");
const DS = {
  "a-khoa": [],
  "anthropic": ["opus-5", "sonnet-5", "haiku-4-5"],
  "b-khoa": [],
  "openrouter": ["openai/gpt-5", "anthropic/sonnet-5", "meta/llama-4"],
};
let soLanFetch = 0;
const win = {
  t: (k) => ({ "mpick.more": "con {n}" }[k] || k),
  fetch: (url) => {
    soLanFetch++;
    const pid = decodeURIComponent(/provider=([^&]+)/.exec(url)[1]);
    return Promise.resolve({ json: () => Promise.resolve({ models: DS[pid] || [] }) });
  },
};
win.window = win;
vm.createContext(win);
vm.runInContext(SRC, win);
const ML = win.JavisModelList;

const PROVS = [
  { id: "a-khoa", label: "A Khoa", configured: false },
  { id: "anthropic", label: "Anthropic", configured: true },
  { id: "b-khoa", label: "B Khoa", configured: false },
  { id: "openrouter", label: "OpenRouter", configured: true },
];

let hong = 0;
function check(ten, dk) { console.log((dk ? "PASS " : "FAIL ") + ten); if (!dk) hong++; }
const nha = (html) => [...html.matchAll(/class="mb-prov[^"]*" data-prov="([^"]*)"><span>([^<]*)/g)].map((m) => m[2]);
const model = (html) => [...html.matchAll(/data-model="([^"]*)"/g)].map((m) => m[1]);

(async () => {
  // 1. Thứ tự: đã kết nối trước, giữ thứ tự gốc trong mỗi nhóm.
  let o = { providers: PROVS, expanded: "anthropic" };
  let h = await ML.render(o);
  check("nhà đã kết nối đứng đầu, nhà khoá xuống dưới",
    JSON.stringify(nha(h)) === JSON.stringify(["Anthropic", "OpenRouter", "A Khoa", "B Khoa"]));
  check("nhà đang mở hiện model của nó", JSON.stringify(model(h)) === JSON.stringify(DS.anthropic));

  // 2. Thu gọn: expanded rỗng thì không nhà nào sổ ra.
  h = await ML.render({ providers: PROVS, expanded: "" });
  check("expanded rỗng thì không hiện model nào", model(h).length === 0 && nha(h).length === 4);

  // 3. Tìm trên mọi nhà. Lần đầu openrouter chưa tải: hiện "đang tải" và trả Promise trong o.cho.
  o = { providers: PROVS, expanded: "anthropic", filter: "sonnet" };
  h = await ML.render(o);
  check("tìm kiếm không chặn chờ nhà chưa tải (o.cho có Promise)", o.cho.length === 1 && h.includes("mpick.loading"));
  await Promise.all(o.cho);
  o = { providers: PROVS, expanded: "anthropic", filter: "sonnet" };
  h = await ML.render(o);
  check("tìm 'sonnet' ra kết quả ở CẢ hai nhà",
    JSON.stringify(model(h)) === JSON.stringify(["sonnet-5", "anthropic/sonnet-5"]) && o.cho.length === 0);
  check("nhà không có kết quả thì không hiện đầu nhà", !nha(h).includes("A Khoa"));

  h = await ML.render({ providers: PROVS, expanded: "", filter: "openrouter" });
  check("chữ tìm trùng tên nhà thì hiện cả danh sách nhà đó",
    JSON.stringify(model(h)) === JSON.stringify(DS.openrouter));

  h = await ML.render({ providers: PROVS, expanded: "", filter: "b khoa" });
  check("tìm trúng tên nhà còn khoá thì hiện nhà đó kèm lối mở khoá",
    nha(h).includes("B Khoa") && h.includes('data-goto="models"'));

  h = await ML.render({ providers: PROVS, expanded: "", filter: "zzz" });
  check("không trúng gì thì báo không thấy", h.includes("mpick.no_match"));

  // Danh sách dài hơn trần: báo còn bao nhiêu thay vì cắt lặng lẽ.
  h = await ML.render({ providers: PROVS, expanded: "anthropic", limit: 2 });
  check("quá trần thì báo số model còn lại", model(h).length === 2 && h.includes("con 1"));

  if (hong) { console.log("\nTHAT BAI " + hong); process.exit(1); }
  console.log("\nOK - test_model_list_nha_ket_noi: tat ca pass");
})();
