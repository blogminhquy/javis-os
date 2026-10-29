// Kho cai dat: o Sap xep va mo ta gon ba dong (0.407.0).
//
//     node tests/js/test_kho_sap_xep.js
//
// Chu kho (2026-10-29): mo ta dai bi cat ngang giua dong, muon dau "..." ; va muon sap xep kho.
// Chi lam cac kieu sap xep khong can may chu: De xuat (mac dinh, goi theo repo goc len dau), Moi cap
// nhat, Ten A-Z. Luot cai va sao cho may chu trung tam sau nay. Test goi THAT `veKho` va bam o chon.
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
// Each selector keeps one object, so the test can fire the handler packs.js attaches to it.
const nut = {};
const host = { innerHTML: "", querySelector: (s) => (nut[s] = nut[s] || { value: "" }), querySelectorAll: () => [] };

let kho = {};
globalThis.localStorage = { getItem: (k) => (k in kho ? kho[k] : null), setItem: (k, v) => { kho[k] = String(v); } };

const goi = (o) => Object.assign({
  kind: "agent", description: { vi: "mo ta" }, tier: "data", verified: true, nguon: "kho",
  author: { name: "Javis" }, version: "1.0.0", installed: false,
  download: { url: "https://x/y.zip", sha256: "a" }, nhom: "Lap trinh", upstream: {},
}, o);
const B = goi({ id: "javis.b", name: { vi: "Bao" }, updated: "2026-10-01" });
const A = goi({ id: "javis.a", name: { vi: "An" }, updated: "2026-10-20" });
const GOC = goi({ id: "javis.goc", name: { vi: "Cuong" }, updated: "2026-09-01",
  upstream: { repo: "tac-gia/repo", ref: "main", commit: "abc1234", synced: "2026-09-01" } });
const DAI = goi({ id: "javis.dai", name: { vi: "Dung" }, updated: "2026-10-20",
  description: { vi: "chu ".repeat(60) } });

const danhMuc = { ok: true, fetched_at: Math.floor(Date.now() / 1000), packs: [B, A, GOC, DAI] };
const win = { ic: (t) => "<svg data-ic=\"" + t + "\"></svg>", Alpine: { store: () => ({ go() {} }) } };
globalThis.Alpine = win.Alpine;
new Function("window", "document", "fetch",
  fs.readFileSync(path.join(ROOT, "dashboard", "packs.js"), "utf8"))(
  win, doc, () => Promise.resolve({ json: () => Promise.resolve(danhMuc) }));
const P = win.JavisPacks || {};

const thuTu = () => ["javis.b", "javis.a", "javis.goc", "javis.dai"]
  .map(id => [id, host.innerHTML.indexOf('data-kho-id="' + id + '"')])
  .filter(x => x[1] >= 0).sort((x, y) => x[1] - y[1]).map(x => x[0]);
const chon = (v) => { nut["#pkSap"].value = v; nut["#pkSap"].onchange(); };

(async () => {
  await P.veKho({}, host, false, "agent");
  const h = host.innerHTML;
  check("co o Sap xep voi ba lua chon", h.includes('id="pkSap"') && h.includes('value="de-xuat"')
    && h.includes('value="moi"') && h.includes('value="ten"'));
  check("chua co lua chon luot cai hay sao (cho may chu trung tam)", !/value="(cai|sao)"/.test(h));
  check("mac dinh De xuat: goi theo repo goc len dau, con lai giu thu tu kho",
    thuTu().join() === "javis.goc,javis.b,javis.a,javis.dai");

  chon("moi");
  check("Moi cap nhat: ngay moi truoc, cung ngay giu thu tu kho",
    thuTu().join() === "javis.a,javis.dai,javis.b,javis.goc");
  check("lua chon duoc nho tren may", kho["javis.kho.sap"] === "moi");

  chon("ten");
  check("Ten A-Z", thuTu().join() === "javis.a,javis.b,javis.goc,javis.dai");

  chon("<script>");
  check("gia tri la quay ve De xuat", thuTu()[0] === "javis.goc" && kho["javis.kho.sap"] === "de-xuat");

  // ---- Description clamp ----
  check("moi mo ta tren the deu gon ba dong (lop kho-mo-ta)",
    (P.theKho(A).match(/cat-desc kho-mo-ta/g) || []).length === 1
    && P.theKho(DAI).includes("cat-desc kho-mo-ta"));
  check("the khong con dung j-clamp2 (hai dong)", !P.theKho(DAI).includes("j-clamp2"));
  const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
  check("CSS kep ba dong co dau ba cham", /\.kho-mo-ta \{[^}]*-webkit-line-clamp: 3/.test(css));
  check("mo ta bi kep khong con gian het the (flex: none)",
    /\.cat-desc\.j-clamp2, \.cat-desc\.kho-mo-ta \{ flex: none; margin-bottom: auto; \}/.test(css));

  // ---- No localStorage (private window): still works, default order ----
  globalThis.localStorage = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
  chon("ten");
  check("khong co localStorage van sap xep duoc", thuTu()[0] === "javis.a");

  if (fails.length) {
    console.log("\nFAIL - test_kho_sap_xep: " + fails.length);
    process.exit(1);
  }
  console.log("\nOK - test_kho_sap_xep: all pass");
})();
