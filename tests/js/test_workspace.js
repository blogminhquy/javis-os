/* Trang Cộng sự (dashboard/workspace.js): sắp xếp, chọn phiên, tiến độ quy trình.

       node tests/js/test_workspace.js

   Chạy dưới node với DOM giả tối thiểu: workspace.js phơi phần thuần qua window.JavisWorkspace. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");

global.window = { t: (k) => k, ic: () => "", addEventListener() {}, matchMedia: () => ({ matches: false }) };
global.document = { getElementById: () => null, createElement: () => ({ classList: { add() {}, remove() {} }, appendChild() {} }), body: { classList: { add() {}, remove() {} } } };
global.localStorage = { getItem: () => null, setItem() {} };
require(path.join(root, "dashboard", "workspace.js"));
const W = window.JavisWorkspace;

let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

// Sắp xếp: mốc gần nhất lên đầu, chưa có mốc xếp sau theo tên
const wfs = [{ slug: "a", name: "Bản tin", last_run_at: 0 }, { slug: "b", name: "Viết bài", last_run_at: 50 }, { slug: "c", name: "Ads", last_run_at: 99 }, { slug: "d", name: "Zalo", last_run_at: 0 }];
check("xep quy trinh theo lan chay gan nhat", W.sapXep(wfs, "last_run_at").map(x => x.slug).join(",") === "c,b,a,d");
const ags = [{ slug: "x", name: "Người viết", last_chat_at: 0 }, { slug: "y", name: "Javis", last_chat_at: 3 }];
check("xep tro ly theo lan chat gan nhat", W.sapXep(ags, "last_chat_at").map(x => x.slug).join(",") === "y,x");

// Lọc: tìm không dấu + nhóm
const ds = [{ slug: "a", name: "Người viết", role: "viết", group: "Marketing" }, { slug: "b", name: "Kế toán", role: "sổ sách", group: "Finance" }];
check("loc theo chu khong dau", W.loc(ds, "nguoi viet", "").map(x => x.slug).join() === "a");
check("loc theo nhom", W.loc(ds, "", "Finance").map(x => x.slug).join() === "b");

// Tiến độ quy trình từ wf_event
const st = W.tienDoMoi(3);
W.apDung(st, { type: "step_start", i: 0, agent: "A" });
check("step_start -> buoc 0 dang lam", st.buoc[0].trang_thai === "dang" && st.hien_tai === 0);
W.apDung(st, { type: "step_done", i: 0 });
W.apDung(st, { type: "step_start", i: 1, agent: "B" });
check("step_done -> xong, sang buoc 1", st.buoc[0].trang_thai === "xong" && st.buoc[1].trang_thai === "dang");
W.apDung(st, { type: "wait_user", node: "dang", task_id: "tk", code: "AB" });
check("wait_user -> cho duyet + giu code", st.cho_duyet && st.cho_duyet.code === "AB" && st.trang_thai === "cho");
W.apDung(st, { type: "done" });
check("done -> xong het", st.trang_thai === "xong" && st.buoc.every(b => b.trang_thai === "xong"));
const st2 = W.tienDoMoi(2);
W.apDung(st2, { type: "step_start", i: 0, agent: "A" });
W.apDung(st2, { type: "error", content: "chết" });
check("error -> buoc dang lam thanh loi", st2.trang_thai === "loi" && st2.buoc[0].trang_thai === "loi");
check("phan tram", W.phanTram(W.tienDoMoi(4)) === 0 && W.phanTram(st) === 100);

// ============================================================
// Icon QUAY ở hàng quy trình đang chạy (0.59.2)
// ============================================================
// Trước đây mọi hàng quy trình đều đeo icon tĩnh, nên bấm Chạy xong nhìn sang cột trái không
// biết cái nào đang chạy. Trạng thái đọc THẲNG từ S.tienDo chứ không nuôi cờ riêng - cờ riêng
// thì phải nhớ tắt ở cả ba đường kết thúc (xong / lỗi / dừng chờ duyệt), quên một đường là
// icon quay mãi.
{
  const S = W.state();
  S.sessionCuaPhien = { "s1": "viet-bai" };
  S.tienDo = { "s1": W.tienDoMoi(2) };
  check("chua chay thi khong quay", W.dangChay("viet-bai") === false);
  W.apDung(S.tienDo.s1, { type: "step_start", i: 0, agent: "A" });
  check("dang chay thi quay", W.dangChay("viet-bai") === true);
  check("quy trinh KHAC khong quay lay", W.dangChay("ban-tin") === false);
  W.apDung(S.tienDo.s1, { type: "wait_user", node: "x", code: "AB" });
  check("dung cho duyet thi thoi quay", W.dangChay("viet-bai") === false);
  W.apDung(S.tienDo.s1, { type: "step_start", i: 1, agent: "B" });
  W.apDung(S.tienDo.s1, { type: "error", content: "chết" });
  check("chay loi thi thoi quay", W.dangChay("viet-bai") === false);
  S.tienDo = { "s1": W.tienDoMoi(1) };
  W.apDung(S.tienDo.s1, { type: "step_start", i: 0, agent: "A" });
  W.apDung(S.tienDo.s1, { type: "done" });
  check("chay xong thi thoi quay", W.dangChay("viet-bai") === false);
  S.sessionCuaPhien = {}; S.tienDo = {};
}

// ============================================================
// Chạy THẬT cột trái + cột phải với DOM giả (0.59.2)
// ============================================================
// Ba thay đổi ở đây đều là thứ nhìn mã nguồn không ra: ô lọc nhóm phải là <select>, ô tìm chỉ
// bung khi bấm nút, và đổi tab cột phải phải TRẢ cây Vault về (node chỉ có một - quên trả là
// màn chính lẫn trang Trò chuyện mất hẳn panel Vault).
{
  const vm = require("node:vm");
  const src = fs.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8");
  const doan = src.slice(src.indexOf("  // ---------- ô tìm thu gọn ----------"),
                         src.indexOf("  function chonMacDinh("))
             + src.slice(src.indexOf("  function roi() {"), src.indexOf("\n  window.JavisWorkspace ="));

  const lop = () => ({ _c: {}, toggle(c, on) { this._c[c] = !!on; }, co(c) { return !!this._c[c]; } });
  const oGia = () => ({ innerHTML: "", textContent: "", value: "", hidden: true, dataset: {},
    _attrs: {}, _focus: 0, classList: lop(),
    setAttribute(k, v) { this._attrs[k] = v; }, focus() { this._focus++; },
    querySelectorAll() { return []; } });
  const nodes = {};
  ["#wsGroup", "#wsNew", "#wsImport", "#wsList", "#wsSearch", "#wsSearchBtn", "#wsRightFiles", "#wsPage"]
    .forEach((s) => { nodes[s] = oGia(); });
  const tab = (v) => ({ dataset: { rtab: v }, classList: lop() });
  const pane = (v) => ({ dataset: { rpane: v }, classList: lop() });
  const tabs = [tab("cai"), tab("files")], panes = [pane("cai"), pane("files")];
  const el = {
    querySelector: (s) => nodes[s] || null,
    querySelectorAll: (s) => (s === "[data-rtab]" ? tabs : s === "[data-rpane]" ? panes : []),
  };
  const ds = [{ slug: "a", name: "Người viết", role: "viết", group: "Marketing" },
              { slug: "b", name: "Kế toán", role: "sổ sách", group: "Finance" },
              { slug: "c", name: "Chạy ads", role: "ads", group: "Marketing" }];
  const goi = [], kho = {};
  const ctx = {
    S: { loai: "agent", q: "", nhom: "", chon: { agent: "a" }, el: el, tienDo: {}, sessionCuaPhien: {}, tabPhai: "cai" },
    danhSach: () => ds, loc: W.loc, cacBuoc: () => [], dangChon: () => ds[0],
    luuChon() {}, moPhien() {}, heptLai: () => false, chatReady() {}, active: true, opening: 0,
    esc: (s) => String(s == null ? "" : s), t: (k) => k, ic: () => "<svg></svg>", avatar: () => "<i></i>",
    localStorage: { getItem: (k) => (k in kho ? kho[k] : null), setItem(k, v) { kho[k] = String(v); } },
    document: { getElementById: () => null },
    window: { JavisVaultPanel: { borrow(h) { goi.push("borrow"); ctx._into = h; return true; },
                                 giveBack() { goi.push("giveBack"); } } },
  };
  vm.createContext(ctx); vm.runInContext(doan, ctx);

  // ---- Bộ lọc nhóm là Ô CHỌN, không phải hàng chip ----
  ctx.veTrai();
  const html = nodes["#wsGroup"].innerHTML;
  check("bo loc nhom ve bang <option>, khong con chip", html.indexOf("<option") === 0 && !/ws-group-chip/.test(html));
  check("co dong Tat ca nhom dung dau", html.indexOf('<option value="">ws.all_groups (3)') === 0);
  check("moi nhom kem so dem", html.includes(">Marketing (2)<") && html.includes(">Finance (1)<"));
  check("o chon dung dang o mac dinh Tat ca", nodes["#wsGroup"].value === "");
  nodes["#wsGroup"].value = "Finance"; nodes["#wsGroup"].onchange();
  check("doi dong trong o chon thi loc theo nhom do", ctx.S.nhom === "Finance"
    && nodes["#wsList"].innerHTML.includes("Kế toán") && !nodes["#wsList"].innerHTML.includes("Người viết"));
  ctx.S.nhom = ""; ctx.veTrai();

  // ---- Hàng quy trình ĐANG chạy đeo icon quay ----
  ctx.S.loai = "workflow"; ctx.S.chon.workflow = "a";
  ctx.S.sessionCuaPhien = { s1: "a" };
  ctx.S.tienDo = { s1: W.apDung(W.tienDoMoi(2), { type: "step_start", i: 0, agent: "X" }) };
  ctx.ic = (n, o) => '<svg data-ic="' + n + '" class="' + ((o && o.cls) || "") + '"></svg>';
  ctx.veDanhSach();
  check("hang quy trinh dang chay co lop ic-spin", /ic-spin/.test(nodes["#wsList"].innerHTML));
  check("hang quy trinh KHAC van icon tinh",
    (nodes["#wsList"].innerHTML.match(/ic-spin/g) || []).length === 1);
  W.apDung(ctx.S.tienDo.s1, { type: "done" });
  ctx.veDanhSach();
  check("chay xong thi ve lai la het quay", !/ic-spin/.test(nodes["#wsList"].innerHTML));
  ctx.S.loai = "agent"; ctx.S.tienDo = {}; ctx.S.sessionCuaPhien = {};

  // ---- Ô tìm: nút kính lúp bung ra, rỗng thì tự thu ----
  ctx.noiODoTim(el);
  const o = nodes["#wsSearch"], nut = nodes["#wsSearchBtn"];
  check("o tim dong san luc dung khung", o.hidden === true);
  nut.onclick();
  check("bam nut thi bung o tim va dua con tro vao", o.hidden === false && o._focus === 1
    && nut._attrs["aria-expanded"] === "true");
  o.value = "ke toan"; o.oninput({ target: o });
  check("go chu van loc nhu cu", ctx.S.nhom === "" && nodes["#wsList"].innerHTML.includes("Kế toán")
    && !nodes["#wsList"].innerHTML.includes("Người viết"));
  o.onblur();
  check("con chu thi mat tieu diem KHONG thu lai", o.hidden === false);
  o.value = ""; o.onblur();
  check("rong roi mat tieu diem thi thu lai", o.hidden === true);
  nut.onclick(); o.value = "ke toan"; o.oninput({ target: o });
  let chan = 0;
  o.onkeydown({ key: "Escape", preventDefault() { chan++; }, stopPropagation() {} });
  check("Esc xoa chu, tra lai danh sach day du va thu o tim",
    chan === 1 && o.value === "" && ctx.S.q === "" && o.hidden === true
    && nodes["#wsList"].innerHTML.includes("Người viết"));

  // ---- Tab cột phải: mượn cây khi sang Thư mục, TRẢ khi rời ----
  check("CANARY: chua bam sang Thu muc thi chua muon cay", goi.indexOf("borrow") < 0);
  ctx.chonTabPhai("files");
  check("bam sang Thu muc thi muon cay Vault", goi[goi.length - 1] === "borrow" && ctx._into === nodes["#wsRightFiles"]);
  check("khung Thu muc bat, khung Cai dat tat",
    panes[1].classList.co("on") && !panes[0].classList.co("on") && tabs[1].classList.co("active"));
  check("nho tab dang dung", kho["javis_ws_rtab"] === "files");
  ctx.chonTabPhai("cai");
  check("CANARY: quay ve tab Cai dat thi TRA cay Vault", goi[goi.length - 1] === "giveBack");
  ctx.chonTabPhai("files");
  ctx.roi();
  check("CANARY: roi trang cung TRA cay Vault", goi[goi.length - 1] === "giveBack");
}

// Dây nối
const app = fs.readFileSync(path.join(root, "dashboard", "app.js"), "utf8");
check("app.js chuyen wf_event sang JavisWorkspace", /data\.type === "wf_event"/.test(app) && /JavisWorkspace\.onWfEvent\(/.test(app));
const html = fs.readFileSync(path.join(root, "dashboard", "index.html"), "utf8");
// Dò theo ĐƯỜNG DẪN "/static/<ten>.js" chứ không theo tên trần: tên trần còn nằm trong hàng
// chục dòng chú thích ở nửa trên file, nên so vị trí kiểu đó là so nhầm với một chú thích.
const viTri = (ten) => html.indexOf('/static/' + ten + '.js');
check("index.html nap workspace.js sau studio.js, truoc console.js",
  viTri("studio") > 0 && viTri("studio") < viTri("workspace") && viTri("workspace") < viTri("console"));
const con = fs.readFileSync(path.join(root, "dashboard", "console.js"), "utf8");
check("console.js co renderWorkspace muon khung chat", /function renderWorkspace\(el\)/.test(con) && /JavisWorkspace\.render\(el, \{ borrow: _borrowChatNodes \}\)/.test(con));
const studio = fs.readFileSync(path.join(root, "dashboard", "studio.js"), "utf8");
check("studio.js editAgent nhan host + onSaved", /function editAgent\(a, opts\)/.test(studio) && /opts\.host/.test(studio) && /opts\.onSaved/.test(studio));

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - workspace");
