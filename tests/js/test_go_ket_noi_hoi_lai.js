// Go mot dich vu CO SAN phai hoi lai truoc khi go - nap that packs.js roi goi that goApp().
//
//     node tests/js/test_go_ket_noi_hoi_lai.js
//
// Vi sao file nay ton tai:
//
// Truoc 0.55.36, duong go mot connector di kem app goi thang POST /connect/core-toggle voi
// {off:true}. Server chi tra 409 "can xac nhan" khi connector do DANG co ket noi chay; con
// truong hop thuong - chua ai dau tai khoan nao - thi lan goi dau tien GO LUON. Tuc la mot cu
// bam nham vao dau x be xiu o goc the la dich vu bien khoi kho, khong ai hoi cau nao.
//
// Sua bang cach them buoc `plan: true` (xem truoc, khong dung gi) roi moi hoi nguoi dung. Bat
// bien can canh la: KHONG duoc co lan ghi nao truoc khi nguoi dung bam dong y. Test nay ep
// dung bat bien do bang cach ghi lai moi loi goi fetch va kiem thu tu.
//
// Kieu test: NAP module va GOI ham, khong quet chuoi - xem ghi chu dai o test_kho_cai_dat.js.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, them) {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
}

// ---- DOM gia: du de modal() dung HTML va de test bam duoc nut ----
//
// Khong co jsdom trong repo. Ban gia nay khong parse HTML - no chi ghi nho chuoi vua gan vao
// innerHTML, roi getElementById tra ve mot the stub NEU id do co mat trong chuoi. Bay nhieu la
// du: hoi() tim dung hai nut theo id, gan onclick, va goi focus().
function moiTruong() {
  const nut = {};
  function theMoi(id) {
    return {
      id,
      onclick: null,
      _pressed: "false",
      focus() {},
      setAttribute(k, v) { if (k === "aria-pressed") this._pressed = v; },
      getAttribute(k) { return k === "aria-pressed" ? this._pressed : null; },
      classList: { add() {}, remove() {}, contains: () => false },
      querySelectorAll: () => [],
      addEventListener() {},
      appendChild() {},
      style: {},
    };
  }
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
  const doc = {
    getElementById(id) {
      if (id === "packModal") return hop;
      const trang = (doc._el && doc._el.innerHTML) || "";
      if (!hop._html.includes('id="' + id + '"') && !trang.includes('id="' + id + '"')) return null;
      nut[id] = nut[id] || theMoi(id);
      return nut[id];
    },
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: () => hop,
    body: { appendChild() {} },
  };
  return { doc, hop, nut };
}

const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "packs.js"), "utf8");

// Moi lan chay: mot ban packs.js moi, mot so ghi loi goi mang moi.
function nap(traLoi) {
  const { doc, hop, nut } = moiTruong();
  const goi = [];
  const win = { ic: () => "", Alpine: { store: () => ({ go() {} }) } };
  const fetchGia = (url, opt) => {
    const body = JSON.parse((opt && opt.body) || "{}");
    goi.push({ url, body });
    return Promise.resolve({ json: () => Promise.resolve(traLoi(url, body)) });
  };
  const alpineCu = globalThis.Alpine;
  globalThis.Alpine = win.Alpine;
  new Function("window", "document", "fetch", SRC)(win, doc, fetchGia);
  globalThis.Alpine = alpineCu;
  // `docEl` day them mot vung HTML nua cho getElementById soi: trang kho ve vao `el` chu khong
  // vao hop thoai, ma hai thu do dung chung mot ban DOM gia.
  return { P: win.JavisPacks || {}, goi, hop, nut, docEl: (x) => { doc._el = x; } };
}

check("packs.js phoi ra goApp", typeof nap(() => ({ ok: true })).P.goApp === "function");

// ---- 1. Nguoi dung bam GIU LAI: khong duoc co lan ghi nao ----
(async () => {
  const { P, goi, nut } = nap(() => ({ ok: true, plan: true, connections: [] }));
  const chay = P.goApp("Pancake POS", "pancake-pos");
  await new Promise(r => setTimeout(r, 0));   // cho lan fetch `plan` xong, hop thoai hien ra

  check("hoi truoc khi lam: lan goi dau tien la XEM TRUOC (plan), khong phai lenh go",
    goi.length === 1 && goi[0].body.plan === true, JSON.stringify(goi[0] && goi[0].body));

  const khong = nut.pkHoiKhong;
  check("hop thoai co nut tu choi", !!khong);
  if (khong) khong.onclick();
  const r = await chay;

  check("bam GIU LAI -> khong co lan ghi nao len server",
    goi.length === 1, JSON.stringify(goi.map(g => g.body)));
  check("bam GIU LAI -> tra ve huy, khong phai loi", r && r.huy === true && r.ok === false,
    JSON.stringify(r));

  // ---- 2. Nguoi dung bam GO: luc do moi ghi, va phai kem confirm ----
  const b = nap((url, body) => (body.plan ? { ok: true, plan: true, connections: [] } : { ok: true }));
  const chay2 = b.P.goApp("Pancake POS", "pancake-pos");
  await new Promise(r2 => setTimeout(r2, 0));
  b.nut.pkHoiCo.onclick();
  const r2 = await chay2;
  check("bam GO -> co dung hai lan goi: xem truoc roi moi go", b.goi.length === 2,
    JSON.stringify(b.goi.map(g => g.body)));
  check("lan go kem off:true va confirm:true",
    b.goi[1] && b.goi[1].body.off === true && b.goi[1].body.confirm === true,
    JSON.stringify(b.goi[1] && b.goi[1].body));
  check("tra ve ok", r2 && r2.ok === true, JSON.stringify(r2));

  // ---- 3. Co ket noi dang chay -> cau hoi phai NOI RA ten chung ----
  // Nguoi dung can biet cai gi sap dung, khong phai mot cau chung chung.
  const c = nap((url, body) => (body.plan
    ? { ok: true, plan: true, connections: [{ id: "a1", label: "Lang chai xua" }] }
    : { ok: true }));
  c.P.goApp("Pancake POS", "pancake-pos");
  await new Promise(r3 => setTimeout(r3, 0));
  check("cau hoi liet ke ten ket noi sap dung", c.hop.innerHTML.includes("Lang chai xua"),
    c.hop.innerHTML.slice(0, 200));
  check("cau hoi noi ro ket noi KHONG bi xoa", /không bị xoá|KHÔNG bị xoá/i.test(c.hop.innerHTML));
  c.nut.pkHoiKhong.onclick();

  // ---- 4. Server tu choi ngay o buoc xem truoc -> khong hoi, khong ghi ----
  const d = nap(() => ({ ok: false, error: "khong co connector nay" }));
  const rd = await d.P.goApp("La", "khong-co");
  check("xem truoc that bai -> khong ghi gi", d.goi.length === 1);
  check("xem truoc that bai -> bao loi cua server", rd && rd.ok === false && !rd.huy,
    JSON.stringify(rd));

  // ---- 5. Nut "Quay lai" khong duoc dinh sang luot sau ----
  //
  // `moKho()` dat duong ve khi nguoi dung bam tab tu mot trang nang luc. Duong ve do phai song
  // qua moi lan ve lai TRONG luot (trang tu ve lai sau moi lan cai/go), nhung phai CHET khi
  // nguoi dung roi di roi vao kho bang duong khac.
  //
  // Truoc 0.55.37 khong co ca thu hai: kho khong co mat tren thanh ben nen duong duy nhat vao
  // la cai tab, va tab nao cung ghi de duong ve. Dua kho ra thanh ben la mo ra ca do - vao tu
  // thanh ben ma van thay nut "Quay lai Ky nang" tro ve noi minh khong he di ra.
  const e = nap((url) => (url.startsWith("/packs/store")
    ? { ok: true, packs: [] }
    : { packs: [], dir: "/tmp/packs", max_mb: 25 }));

  // `el` gia: chi can ghi nho HTML de test doc lai, va de getElementById tim thay trong do.
  const el = {
    _html: "",
    set innerHTML(v) { this._html = v; },
    get innerHTML() { return this._html; },
    querySelectorAll: () => [],
  };
  e.docEl(el);

  // Trong trinh duyet `window.Alpine` va `Alpine` la mot; `nap()` tra global ve nhu cu sau khi
  // nap xong, nen dat lai o day cho `moKho` goi duoc `Alpine.store("nav").go`.
  const alpineCu = globalThis.Alpine;
  globalThis.Alpine = { store: () => ({ go() {} }) };
  e.P.moKho("skill", "skills", "Ky nang");     // vao kho bang TAB tu trang Ky nang
  await e.P.render(el);
  check("vao tu tab -> co nut quay lai", /id="pkQuayLai"/.test(el.innerHTML), el.innerHTML.slice(0, 80));

  await e.P.render(el);                        // dieu huong vao kho lan nua, lan nay tu THANH BEN
  check("CANARY: vao tu thanh ben -> KHONG con nut quay lai cua luot truoc",
    !/id="pkQuayLai"/.test(el.innerHTML), el.innerHTML.slice(0, 120));

  globalThis.Alpine = alpineCu;

  console.log("");
  if (fails.length) {
    console.log("FAIL - test_go_ket_noi_hoi_lai: " + fails.length + " loi: " + fails.join("; "));
    process.exit(1);
  }
  console.log("OK - test_go_ket_noi_hoi_lai: tat ca pass");
})();
