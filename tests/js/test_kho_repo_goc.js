// Kho cai dat: tab "Repo khuyen dung" (0.370.0).
//
//     node tests/js/test_kho_repo_goc.js
//
// Goi theo repo goc (truong `upstream` trong danh muc) hien o mot tab rieng, bat ke loai, kem dong
// "Theo repo goc" tro ve repo GitHub cua tac gia. Kho khong co goi nao nhu vay thi tab khong hien.
// Test goi THAT `theKho` va `veKho` (ve ca luoi) chu khong quet chuoi ma nguon.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

const doc = {
  activeElement: null,
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: () => ({ style: {}, classList: { add() {}, remove() {} },
                          querySelectorAll: () => [], appendChild() {} }),
  body: { appendChild() {} },
};
const host = { innerHTML: "", querySelector: () => null, querySelectorAll: () => [] };

const goi = (o) => Object.assign({
  id: "javis.x", kind: "skill", name: { vi: "X" }, description: { vi: "mo ta" },
  tier: "data", verified: true, nguon: "kho", author: { name: "Javis" },
  version: "1.0.0", installed: false, download: { url: "https://x/y.zip", sha256: "a" }, nhom: "Sang tao",
  upstream: {},
}, o);
const REMOTION = goi({ id: "javis.remotion", name: { vi: "Remotion" },
  upstream: { repo: "remotion-dev/skills", ref: "main", commit: "30d4553", synced: "2026-10-28" } });
const LEMO = goi({ id: "javis.lemo", kind: "bundle", name: { vi: "Lemo" },
  upstream: { repo: "lemomo-ai/lemo-opuscar", ref: "main", commit: "413a6bd", synced: "2026-10-27" } });
const THUONG = goi({ id: "javis.thuong", name: { vi: "Thuong" } });
const KET_NOI = goi({ id: "javis.kn", kind: "connector", name: { vi: "Ket noi" } });

let danhMuc = { ok: true, fetched_at: Math.floor(Date.now() / 1000), packs: [REMOTION, LEMO, THUONG, KET_NOI] };
const win = { ic: (t) => "<svg data-ic=\"" + t + "\"></svg>", Alpine: { store: () => ({ go() {} }) } };
const _alpineCu = globalThis.Alpine;
globalThis.Alpine = win.Alpine;
new Function("window", "document", "fetch",
  fs.readFileSync(path.join(ROOT, "dashboard", "packs.js"), "utf8"))(
  win, doc, () => Promise.resolve({ json: () => Promise.resolve(danhMuc) }));
const P = win.JavisPacks || {};

// ---- 1. The card ----
const the = P.theKho(REMOTION);
check("the theo repo goc co link toi dung repo GitHub",
  the.includes('href="https://github.com/remotion-dev/skills"') && the.includes('rel="noopener noreferrer"'));
check("the theo repo goc noi ngay lay ban moi nhat", the.includes("2026-10-28"));
check("the theo repo goc co icon nhanh git", the.includes('data-ic="git-branch"'));
check("goi thuong khong co dong theo repo goc", !P.theKho(THUONG).includes("kho-goc"));
check("goi khong co truong upstream (kho cu) cung khong vo",
  !P.theKho(Object.assign({}, THUONG, { upstream: undefined })).includes("kho-goc"));
const doc_ = P.theKho(goi({ upstream: { repo: 'a/b"><script>', synced: "" } }));
check("ten repo duoc escape truoc khi vao HTML", !doc_.includes("<script>"));

(async () => {
  // ---- 2. The tab ----
  await P.veKho({}, host, false, "repo");
  const h = host.innerHTML;
  check("co tab Repo khuyen dung", h.includes('data-kho-loai="repo"'));
  check("tab Repo khuyen dung dung DAU hang tab",
    h.indexOf('data-kho-loai="repo"') < h.indexOf('data-kho-loai="agent"'));
  check("tab repo liet ke moi goi theo repo goc, bat ke loai",
    h.includes("javis.remotion") && h.includes("javis.lemo"));
  check("tab repo khong lan goi thuong", !h.includes("javis.thuong") && !h.includes("javis.kn"));
  // The lead line under the tab went in 0.384.0 (owner: the cards explain themselves).
  check("tab repo khong con dong gioi thieu thua", !h.includes("kho-goc-gt"));

  await P.veKho({}, host, false, "skill");
  const h2 = host.innerHTML;
  check("tab Ky nang van co goi theo repo goc cua no", h2.includes("javis.remotion") && h2.includes("javis.thuong"));
  check("tab khac khong hien dong gioi thieu cua tab repo", !h2.includes("kho-goc-gt"));

  // ---- 3. No upstream packs: no tab ----
  danhMuc = { ok: true, fetched_at: Math.floor(Date.now() / 1000), packs: [THUONG, KET_NOI] };
  await P.veKho({}, host, false, "repo");
  const h3 = host.innerHTML;
  check("kho khong co goi theo repo goc thi khong co tab repo", !h3.includes('data-kho-loai="repo"'));
  check("mo thang tab repo khi khong co goi nao thi roi ve tab Ky nang",
    /class="kho-tab on" data-kho-loai="skill"/.test(h3));

  globalThis.Alpine = _alpineCu;
  if (fails.length) {
    console.log(`FAIL - test_kho_repo_goc: ${fails.length} loi: ${fails.join("; ")}`);
    process.exit(1);
  }
  console.log("OK - test_kho_repo_goc: tat ca pass");
})();
