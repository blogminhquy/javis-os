// Mời cài GÓI ĐI KÈM của một kết nối (0.73.0: quét QR Zalo xong mời cài `javis.zalo`).
//
//     node tests/js/test_cai_goi_di_kem.js
//
// Ba plugin Zalo (gửi ảnh, tag người, đọc ảnh trong nhóm) rời app sang Javis Store. Javis không có
// đường tự cài gói, nên lối vào là `JavisPacks.caiGoiKho(id, tuy)`: tìm gói trong kho rồi mở ĐÚNG màn
// hình đồng ý của đường cài từ kho. Những điều phải giữ:
//   1. Không có lần cài nào trước khi người dùng bấm Cài: lối vào mới không được ngắn hơn đường kho.
//   2. Vân tay đi kèm: tải bằng sha256 của kho, cài bằng sha256 của bản soi.
//   3. `batSan` bật sẵn công tắc "chạy ngay" (vừa tự tay đấu đúng dịch vụ này), nhưng màn hình vẫn hiện
//      khối cảnh báo mã; đường kho thường thì gói có mã vẫn mặc định TẮT.
//   4. Đã cài / đang tắt / kho không có thì không mở gì, và nói rõ trường hợp nào.
//
// Kiểu test: NẠP module và GỌI hàm, không quét chuỗi - xem ghi chú dài ở test_kho_cai_dat.js.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, them) {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
}

// DOM giả như test_go_ket_noi_hoi_lai.js, thêm một điều: công tắc đọc `aria-pressed` ban đầu từ
// chính HTML vừa vẽ, để biết màn hình bật sẵn hay tắt sẵn.
function moiTruong() {
  const nut = {};
  const hop = {
    id: "packModal", className: "", onclick: null, _html: "",
    set innerHTML(v) { this._html = v; },
    get innerHTML() { return this._html; },
    classList: { add() {}, remove() {}, contains: () => false },
    querySelectorAll: () => [],
    querySelector: () => null,
    addEventListener() {},
    style: {},
  };
  function theMoi(id) {
    const m = hop._html.match(new RegExp('id="' + id + '"[^>]*aria-pressed="(\\w+)"'));
    return {
      id, onclick: null, textContent: "", _pressed: m ? m[1] : "false",
      focus() {},
      setAttribute(k, v) { if (k === "aria-pressed") this._pressed = v; },
      getAttribute(k) { return k === "aria-pressed" ? this._pressed : null; },
      classList: { add() {}, remove() {}, contains: () => false },
      querySelectorAll: () => [], addEventListener() {}, appendChild() {}, style: {},
    };
  }
  const doc = {
    getElementById(id) {
      if (id === "packModal") return hop;
      if (!hop._html.includes('id="' + id + '"')) return null;
      nut[id] = nut[id] || theMoi(id);
      return nut[id];
    },
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: () => ({ innerHTML: "" }),
    body: { appendChild() {} },
  };
  return { doc, hop, nut };
}

const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "packs.js"), "utf8");
const KHO = (them) => ({ ok: true, packs: [
  { id: "javis.zalo", nguon: "kho", installed: false, enabled: true,
    download: { url: "dist/javis-zalo-1.0.0.zip", sha256: "a".repeat(64) }, ...(them || {}) },
  { id: "zalo", nguon: "app", installed: true, download: { url: "" } },
] });
const SOI = { ok: true, tier: "code", id: "javis.zalo", name: { vi: "Zalo mở rộng" }, staging_id: "b".repeat(64),
              sha256: "b".repeat(64), py_files: ["plugins/zalo-read-images/plugin.py"], plugins: ["zalo-read-images"] };

function nap(kho) {
  const { doc, hop, nut } = moiTruong();
  const goi = [];
  const win = { ic: () => "", Alpine: { store: () => ({ go() {} }) } };
  const fetchGia = (url, opt) => {
    const body = JSON.parse((opt && opt.body) || "{}");
    goi.push({ url, body });
    let r = { ok: true };
    if (url.startsWith("/packs/store")) r = kho;
    else if (url === "/packs/install-url") r = SOI;
    else if (url === "/packs/install") r = { ok: true, id: "javis.zalo", enabled: body.enable };
    return Promise.resolve({ json: () => Promise.resolve(r) });
  };
  const alpineCu = globalThis.Alpine;
  globalThis.Alpine = win.Alpine;
  new Function("window", "document", "fetch", SRC)(win, doc, fetchGia);
  globalThis.Alpine = alpineCu;
  return { P: win.JavisPacks || {}, goi, hop, nut };
}
const nghi = () => new Promise(r => setTimeout(r, 0));

check("packs.js phơi ra caiGoiKho", typeof nap(KHO()).P.caiGoiKho === "function");

(async () => {
  // ---- 1-3. Lối vào sau khi quét QR ----
  const a = nap(KHO());
  let xong = null;
  const kq = await a.P.caiGoiKho("javis.zalo", { batSan: true, sauKhiCai: (r) => { xong = r; } });
  await nghi();
  check("mở màn hình đồng ý", kq === "mo", kq);
  check("tải đúng tệp của kho, kèm vân tay của kho",
    a.goi.some(g => g.url === "/packs/install-url" && g.body.url === "dist/javis-zalo-1.0.0.zip"
      && g.body.expect_sha256 === "a".repeat(64)), JSON.stringify(a.goi));
  check("CHƯA cài gì trước khi bấm Cài", !a.goi.some(g => g.url === "/packs/install"));
  check("màn hình vẫn hiện khối cảnh báo mã kèm tên tệp", a.hop.innerHTML.includes("pkm-canh do")
    && a.hop.innerHTML.includes("plugins/zalo-read-images/plugin.py"));
  check("công tắc chạy ngay được bật sẵn", a.nut.pkBat && a.nut.pkBat.getAttribute("aria-pressed") === "true");
  a.nut.pkCai.onclick();
  await nghi(); await nghi();
  const cai = a.goi.find(g => g.url === "/packs/install");
  check("bấm Cài: gửi đúng vân tay của bản soi và bật luôn", cai && cai.body.consent_sha256 === "b".repeat(64)
    && cai.body.staging_id === "b".repeat(64) && cai.body.enable === true, JSON.stringify(cai && cai.body));
  check("cài xong gọi lại người mời (vẽ lại trang Kết nối), không vẽ trang kho", xong && xong.ok === true);

  // ---- 3b. Đường kho thường không đổi: gói có mã vẫn tắt sẵn ----
  const b = nap(KHO());
  await b.P.caiGoiKho("javis.zalo", {});
  await nghi();
  check("không có batSan: gói có mã vẫn TẮT sẵn", b.nut.pkBat && b.nut.pkBat.getAttribute("aria-pressed") === "false");

  // ---- 4. Không mở gì khi không cần hoặc không được ----
  const c = nap(KHO({ installed: true, enabled: true }));
  check("đã cài và đang bật: trả da_cai, không tải gì", await c.P.caiGoiKho("javis.zalo") === "da_cai"
    && !c.goi.some(g => g.url === "/packs/install-url"));
  const d = nap(KHO({ installed: true, enabled: false }));
  check("đã cài nhưng tắt: trả da_tat", await d.P.caiGoiKho("javis.zalo") === "da_tat");
  const e = nap({ ok: true, packs: [] });
  check("kho không có gói: trả khong_co", await e.P.caiGoiKho("javis.zalo") === "khong_co");
  const f = nap(KHO());
  check("thẻ connector của app trùng id không bị coi là gói", await f.P.caiGoiKho("zalo") === "khong_co");

  if (fails.length) {
    console.log("\nFAIL - test_cai_goi_di_kem: " + fails.length + " lỗi");
    process.exit(1);
  }
  console.log("\nOK - test_cai_goi_di_kem: tất cả pass");
})();
