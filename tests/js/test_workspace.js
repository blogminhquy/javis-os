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
// Bước HỎNG không được vẽ thành tích xanh (0.59.2)
// ============================================================
// Chuyện thật 15/09: cột phải hiện đủ 7 bước "Đã hoàn tất" cho một lần chạy đã chết giữa
// chừng, vì step_error chỉ ghi câu lỗi vào .loi rồi step_done/done đè trạng thái thành "xong".
{
  const s = W.tienDoMoi(2);
  W.apDung(s, { type: "step_start", i: 0, agent: "A" });
  W.apDung(s, { type: "step_error", i: 0, content: "engine chết" });
  check("step_error -> buoc thanh LOI chu khong con la dang lam",
    s.buoc[0].trang_thai === "loi" && s.buoc[0].loi === "engine chết");
  W.apDung(s, { type: "step_done", i: 0 });
  check("CANARY: step_done den sau KHONG doi buoc hong thanh xong", s.buoc[0].trang_thai === "loi");
  W.apDung(s, { type: "done" });
  check("CANARY: done cung KHONG xoa dau buoc hong", s.buoc[0].trang_thai === "loi"
    && s.buoc[1].trang_thai === "xong");

  // Lỗi mang sẵn số bước: đánh dấu ĐÚNG bước đó, không phải bước đang chạy.
  const s2 = W.tienDoMoi(3);
  W.apDung(s2, { type: "step_start", i: 0, agent: "A" });
  W.apDung(s2, { type: "step_done", i: 0 });
  W.apDung(s2, { type: "step_start", i: 1, agent: "B" });
  W.apDung(s2, { type: "error", i: 1, agent: "B", content: "Hết lượt gói Claude." });
  check("error mang i thi danh dau dung buoc do",
    s2.buoc[1].trang_thai === "loi" && s2.buoc[1].loi === "Hết lượt gói Claude."
    && s2.buoc[0].trang_thai === "xong" && s2.buoc[2].trang_thai === "cho");
}

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
  ["#wsGroup", "#wsNew", "#wsImport", "#wsList", "#wsSearch", "#wsSearchBtn", "#wsRightFiles",
   "#wsRightHistory", "#wsPage"]
    .forEach((s) => { nodes[s] = oGia(); });
  const tab = (v) => ({ dataset: { rtab: v }, classList: lop() });
  const pane = (v) => ({ dataset: { rpane: v }, classList: lop() });
  const tabs = [tab("cai"), tab("lichsu"), tab("files")];
  const panes = [pane("cai"), pane("lichsu"), pane("files")];
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
    TAB_PHAI: ["cai", "lichsu", "files"],
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
  // Icon quay thôi là chưa đủ: người tắt hiệu ứng và trình đọc màn hình không thấy nó quay.
  check("dang chay con noi BANG CHU o dong phu",
    (nodes["#wsList"].innerHTML.match(/ws\.running/g) || []).length === 1);
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
    panes[2].classList.co("on") && !panes[0].classList.co("on") && tabs[2].classList.co("active"));
  check("nho tab dang dung", kho["javis_ws_rtab"] === "files");
  ctx.chonTabPhai("cai");
  check("CANARY: quay ve tab Cai dat thi TRA cay Vault", goi[goi.length - 1] === "giveBack");
  // Tab LỊCH SỬ (0.59.3): tab thứ ba, và nó cũng KHÔNG được giữ cây Vault.
  ctx.chonTabPhai("lichsu");
  check("co tab Lich su rieng, khong con nam duoi day khung Cai dat",
    panes[1].classList.co("on") && !panes[0].classList.co("on") && tabs[1].classList.co("active"));
  check("CANARY: sang tab Lich su cung TRA cay Vault", goi[goi.length - 1] === "giveBack");
  check("nho tab Lich su", kho["javis_ws_rtab"] === "lichsu");
  ctx.chonTabPhai("tab-la-hoac");
  check("tab la thi lui ve Cai dat", ctx.S.tabPhai === "cai");
  ctx.chonTabPhai("files");
  ctx.roi();
  check("CANARY: roi trang cung TRA cay Vault", goi[goi.length - 1] === "giveBack");

  // ---- Rời trang thì XOÁ câu đang tìm ----
  // S.q sống ở mức module, còn ô nhập chết theo DOM của trang. Giữ lại câu tìm là lần sau quay
  // vào danh sách đã bị lọc mà ô tìm rỗng và đang thu: cộng sự biến mất, không lời giải thích.
  ctx.S.q = "ke toan";
  ctx.veDanhSach();
  check("CANARY: dang loc thi danh sach that su thieu nguoi",
    !nodes["#wsList"].innerHTML.includes("Người viết"));
  ctx.roi();
  check("roi trang thi xoa cau dang tim", ctx.S.q === "");
  ctx.veDanhSach();
  check("quay lai thi danh sach day du tro lai", nodes["#wsList"].innerHTML.includes("Người viết"));
}

// ============================================================
// MÀN KHỞI ĐẦU khi chưa có cộng sự nào (0.59.9)
// ============================================================
// Chuyện thật 15/09: brain chưa có trợ lý lẫn quy trình thì cột giữa chỉ còn một dòng chữ,
// bấm vào đâu cũng không ra gì, còn nút "Thử lại" lúc tải hỏng thì xoá luôn câu lỗi mà không
// tải lại thứ vừa hỏng. Nay chỗ khung chat là hai nút tạo, và Thử lại tải lại DANH SÁCH.
{
  const vm = require("node:vm");
  const src = fs.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8");
  const doan = src.slice(src.indexOf("  function veLoi(msg) {"), src.indexOf("  function thuGonCaiDat() {"));

  const lop = () => ({ _c: {}, toggle(c, on) { this._c[c] = !!on; }, co(c) { return !!this._c[c]; } });
  const con = {};                                  // nút con moi ra từ khung, giữ lại để bấm
  const nutCon = (s) => (con[s] = con[s] || { onclick: null });
  const khung = { innerHTML: "", hidden: true, querySelector: nutCon };
  const idn = { innerHTML: "", querySelector: nutCon };
  const main = { classList: lop() };
  const nodes = { "#wsIdentity": idn, "#wsOnboard": khung, ".ws-main": main };
  const tao = [];
  const ctx = {
    S: { loai: "agent", agents: [], workflows: [], chon: {}, el: { querySelector: (s) => nodes[s] || null } },
    daTai: true, active: true,
    danhSach: () => (ctx.S.loai === "agent" ? ctx.S.agents : ctx.S.workflows),
    taoMoi: (loai) => tao.push(loai), dangChon: () => null, taiDanhSach: async () => {},
    veTrai() {}, chonMacDinh() {}, cacBuoc: () => [], avatar: () => "<i></i>",
    esc: (s) => String(s == null ? "" : s), t: (k) => k, ic: (n) => '<svg data-ic="' + n + '"></svg>',
    document: { getElementById: () => null }, window: {},
  };
  vm.createContext(ctx); vm.runInContext(doan, ctx);

  ctx.veGiua(null, "ws.none_yet");
  check("danh sach rong thi bay man khoi dau thay cho khung chat",
    khung.hidden === false && main.classList.co("onboard-on"));
  check("man khoi dau bay CA HAI nut tao",
    /id="wsObAgent"/.test(khung.innerHTML) && /id="wsObWf"/.test(khung.innerHTML)
    && khung.innerHTML.includes("ws.new_agent") && khung.innerHTML.includes("ws.new_workflow"));
  check("chua co gi ca thi dung loi chao brain moi", khung.innerHTML.includes("ws.start_title"));
  con["#wsObAgent"].onclick(); con["#wsObWf"].onclick();
  check("moi nut mo dung trinh tao cua LOAI cua no", tao.join(",") === "agent,workflow");

  ctx.veGiua({ slug: "a", name: "Người viết", role: "viết", group: "Marketing" });
  check("chon duoc cong su thi tat man khoi dau, tra lai khung chat",
    khung.hidden === true && !main.classList.co("onboard-on") && khung.innerHTML === "");

  // Chỉ TAB đang đứng rỗng (có trợ lý, chưa có quy trình): vẫn bày nút, nhưng nói đúng thứ thiếu.
  ctx.S.agents = [{ slug: "a", name: "Người viết" }]; ctx.S.loai = "workflow";
  ctx.veGiua(null, "ws.none_yet");
  check("tab Quy trinh rong thi noi la thieu quy trinh", khung.hidden === false
    && khung.innerHTML.includes("ws.start_no_workflow") && !khung.innerHTML.includes("ws.start_title"));

  // Tải danh sách HỎNG thì mảng cũng rỗng - nhưng đó là lỗi mạng, không phải brain mới tinh.
  ctx.daTai = false; ctx.S.agents = []; ctx.S.workflows = []; ctx.S.loai = "agent";
  ctx.veGiua(null);
  check("CANARY: tai danh sach hong thi KHONG bia ra 'chua co cong su nao'", khung.hidden === true);

  // Nút Thử lại: tải lại DANH SÁCH rồi mới mở phiên, không phải chỉ mở lại phiên.
  ctx.veLoi("ws.err_list");
  check("nut Thu lai goi lamLai (tai lai danh sach)", con["#wsRetry"].onclick === ctx.lamLai);
  check("cau loi cua tai danh sach khac cau loi mo hoi thoai", idn.innerHTML.includes("ws.err_list"));
}
{
  const ws = fs.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8");
  const css = fs.readFileSync(path.join(root, "dashboard", "console.css"), "utf8");
  check("khung man khoi dau nam san trong cot giua", ws.includes('id="wsOnboard"'));
  check("tai danh sach hong thi bao dung la hong DANH SACH", ws.includes('veLoi(t("ws.err_list"))'));
  check("bat man khoi dau thi AN khung chat muon",
    /\.ws-main\.onboard-on > \.ws-slot \{ display: none; \}/.test(css) && /\.ws-onboard\[hidden\]/.test(css));
  const vi = JSON.parse(fs.readFileSync(path.join(root, "dashboard", "i18n", "vi.json"), "utf8"));
  const en = JSON.parse(fs.readFileSync(path.join(root, "dashboard", "i18n", "en.json"), "utf8"));
  check("chu man khoi dau co ca hai thu tieng",
    ["ws.start_title", "ws.start_no_agent", "ws.start_no_workflow", "ws.start_desc", "ws.err_list"]
      .every((k) => vi[k] && en[k]));
}

// Dựng khung: ô nhập phải được GIEO LẠI từ S.q, và nút kính lúp phải trỏ tới nó bằng
// aria-controls. render() nằm ngoài khối bóc ở trên nên canh bằng mã nguồn.
{
  const ws = fs.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8");
  check("o tim gieo lai gia tri tu S.q", ws.includes('(S.q ? "" : " hidden")') && ws.includes("esc(S.q)"));
  check("nut kinh lup co aria-controls tro toi o nhap", ws.includes('aria-controls="wsSearch"'));
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
// Bảng chạy của Studio: bước đã báo lỗi thì TẮT vòng quay của chính nó. Trước đây chỉ
// `step_done` mới thay được .rs-spin, mà bước hỏng thì không bao giờ có step_done nữa (server
// dừng ngay), nên bước ấy quay mãi trong khi cả lần chạy đã kết thúc.
{
  const nhanh = studio.slice(studio.indexOf('d.type === "step_error"'),
                             studio.indexOf('d.type === "step_model"'));
  check("studio.js: step_error thay .rs-spin bang dau bao loi",
    /querySelector\("\.rs-spin"\)/.test(nhanh) && /rs-fail/.test(nhanh));
  const css = fs.readFileSync(path.join(root, "dashboard", "style.css"), "utf8");
  check("co kieu cho dau bao loi cua buoc", /\.rs-fail \{/.test(css));
}

// ============================================================
// Bấm DỪNG thì vòng quay phải dừng theo (0.59.3)
// ============================================================
// Chuyện thật 15/09: bấm Dừng, khung chat hiện "Đã dừng lần chạy này theo yêu cầu", nhưng hàng
// bên trái vẫn quay và cột phải vẫn ghi "Đang chạy - Bước 1/3". Lý do: lượt bị huỷ nên không
// có sự kiện `done`/`error` nào, máy trạng thái đứng nguyên ở "dang" mãi mãi.
{
  const st = W.tienDoMoi(3);
  W.apDung(st, { type: "step_start", i: 0, agent: "A" });
  W.apDung(st, { type: "stopped" });
  check("stopped -> khong con la dang chay", st.trang_thai === "dung");
  check("stopped -> buoc dang lam tra ve cho, KHONG bi danh dau hong",
    st.buoc[0].trang_thai === "cho" && !st.buoc.some(b => b.trang_thai === "loi"));
  const st2 = W.tienDoMoi(2);
  W.apDung(st2, { type: "step_start", i: 0, agent: "A" });
  W.apDung(st2, { type: "step_error", i: 0, content: "chết" });
  W.apDung(st2, { type: "stopped" });
  check("CANARY: stopped KHONG xoa dau hong cua buoc da loi", st2.buoc[0].trang_thai === "loi");

  const S = W.state();
  S.loai = "workflow"; S.sessionCuaPhien = { s9: "viet-bai" };
  S.tienDo = { s9: W.apDung(W.tienDoMoi(2), { type: "step_start", i: 0, agent: "A" }) };
  check("CANARY: truoc khi dung thi hang van dang quay", W.dangChay("viet-bai") === true);
  W.onTurnDone("s9");
  check("luot dong ma tien do con ket 'dang' thi tu dong lai", W.dangChay("viet-bai") === false);
  S.tienDo = {}; S.sessionCuaPhien = {}; S.loai = "agent";
  check("nhan tien do co nhan rieng cho lan chay bi dung",
    /ws\.stopped/.test(fs.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8")));
}
// Hai đầu dây của chuyện dừng: server phải BẮN sự kiện, app.js phải gọi onTurnDone (lưới an
// toàn cho những kiểu chết không kịp bắn gì).
{
  const mainPy = fs.readFileSync(path.join(root, "server", "main.py"), "utf8");
  check("server ban wf_event stopped khi luot bi huy",
    /asyncio\.CancelledError[\s\S]{0,900}"event": \{"type": "stopped"\}/.test(mainPy));
  check("app.js goi JavisWorkspace.onTurnDone o khung turn_done",
    /data\.type === "turn_done"[\s\S]{0,900}JavisWorkspace\.onTurnDone\(sid\)/.test(app));
}

// ============================================================
// Gọi cộng sự từ khung Trò chuyện thì kết quả phải quay VỀ khung đó (0.59.3)
// ============================================================
{
  const mainPy = fs.readFileSync(path.join(root, "server", "main.py"), "utf8");
  const render = fs.readFileSync(path.join(root, "dashboard", "chat-render.js"), "utf8");
  check("app.js nho khung Tro chuyen da goi cong su",
    /_gocCongSu\[savedSessionId\] = goc;/.test(app) && /origin_chat: _goc,/.test(app));
  check("chi bao MOT lan: gui xong thi quen khung goc di",
    /delete _gocCongSu\[sid\];/.test(app));
  check("server nhan origin_chat va truyen xuong hai duong chay",
    /payload\.get\("origin_chat"\)/.test(mainPy) && /goc_chat=_goc/.test(mainPy));
  check("server day ket qua nguoc ve khung goc (ca khi hong)",
    (mainPy.match(/_bao_ve_khung_goc\(/g) || []).length >= 4);
  check("link #cs= duoc ve thanh nut bam duoc trong chat", /class="jv-cs"/.test(render));
  check("bam link #cs= mo dung cong su", /window\.JavisOpenCongSu\(cs\.getAttribute\("data-cs"\)\)/.test(render));
  check("console.js co JavisOpenCongSu + deep-link #cs=",
    /window\.JavisOpenCongSu = moCongSu/.test(con) && /\/\^#cs=\(\.\+\)\$\//.test(con));
}

// ============================================================
// Lịch sử hội thoại = ĐÚNG cột lịch sử của trang Trò chuyện (0.59.4)
// ============================================================
// Chủ dự án yêu cầu "bê nguyên cách làm trong phần trò chuyện vào": ô tìm, nhóm theo ngày,
// ghim / đổi tên / xoá, nút Xem thêm. Gắn chính module đó ở chế độ lọc kênh, không dựng bản
// thứ hai - bản thứ hai lệch khỏi bản gốc ngay từ lần sửa đầu tiên.
{
  const ws = fs.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8");
  const sess = fs.readFileSync(path.join(root, "dashboard", "sessions-ui.js"), "utf8");
  check("trang Cong su gan chinh cot lich su cua trang Tro chuyen",
    /JavisChatSide\.mount\(host\.querySelector\("#wsSess"\), \{/.test(ws)
    && /kenh: kenh\(item\), chiHoiThoai: true/.test(ws));
  check("nut Hoi thoai moi o do mo dung KENH cua cong su",
    /onNew: function \(\) \{ var x = dangChon\(\); if \(x\) moPhien\(x, true\); \}/.test(ws));
  check("KHONG con ban danh sach hoi thoai thu hai trong workspace.js",
    !/taiPhienGanDay/.test(ws));
  check("sessions-ui: mount nhan tuy chon loc theo kenh", /function mount\(container, opts\)/.test(sess));
  check("sessions-ui: danh sach va o tim deu loc theo kenh",
    /kenhLoc \? "&channel=" \+ encodeURIComponent\(kenhLoc\)/.test(sess)
    && /kenhLoc \? "&channel=" \+ encodeURIComponent\(kenhLoc\) : ""\) \+ "&limit=40"/.test(sess));
  const mainPy = fs.readFileSync(path.join(root, "server", "main.py"), "utf8");
  check("server: /sessions/search nhan channel", /async def sessions_search[\s\S]{0,200}channel: str = Query\(""\)/.test(mainPy));
  const css2 = fs.readFileSync(path.join(root, "dashboard", "console.css"), "utf8");
  check("co kieu cho che do gon cua cot lich su", /\.cside-gon \.cside-pane \{/.test(css2)
    && /side\.classList\.add\("cside-gon"\)/.test(sess));
}

// ============================================================
// Mở một file trong lúc chat: XẾP NGANG, không để lại khoảng trống (0.59.4)
// ============================================================
// Lỗi thật chủ dự án chụp lại: trình sửa bị bóp còn vài dòng, dưới nó là một khoảng trống cao
// gần nửa màn hình (khung hội thoại rỗng) với mỗi cái chip file ghim lơ lửng giữa.
{
  const css = fs.readFileSync(path.join(root, "dashboard", "console.css"), "utf8");
  const khoi = css.slice(css.indexOf("@media (min-width: 861px) {\n  .ws-main.edit-on"));
  check("man rong: trinh sua va hoi thoai xep NGANG bang grid hai cot",
    /\.ws-main\.edit-on \{ display: grid;/.test(khoi) && /grid-template-columns: minmax\(0, 1fr\)/.test(khoi));
  check("cum nhap trai het be ngang duoi day",
    ["bg-strip", "attach-bar", "model-bar", "hud-voice"].every(c =>
      new RegExp("\\." + c + " \\{ grid-row: \\d; grid-column: 1 / -1; \\}").test(khoi)));
  check("slot tan vao luoi de tung node nhan o rieng", /\.ws-slot \{ display: contents; \}/.test(khoi));
  check("man hep van giu cach cu (an khung chat)",
    /@media \(max-width: 860px\) \{ \.ws-main\.edit-on > \.ws-slot \{ display: none; \} \}/.test(css));
}

// ============================================================
// Màn điện thoại: thanh đầu trang xếp HAI DÒNG (0.59.11)
// ============================================================
// Lỗi thật chủ dự án chụp lại trên iPhone: nút mở danh sách, "File & link", "Hội thoại mới" và
// nút mở cột phải chen hết một dòng, ô tên cộng sự bị bóp còn ĐÚNG MỘT CHỮ CÁI ("C" và "C.").
// Dòng trên phải là khuôn mặt cùng tên cộng sự, dòng dưới mới là các nút.
{
  const css = fs.readFileSync(path.join(root, "dashboard", "console.css"), "utf8");
  const i = css.indexOf("@media (max-width:600px) {");
  check("tim duoc khoi man dien thoai cua trang Cong su", i !== -1);
  const khoi = css.slice(i, i + 900);
  check("thanh dau trang duoc phep xuong dong", /\.ws-bar \{[^}]*flex-wrap:\s*wrap/.test(khoi));
  check("o ten chiem het be ngang, thanh mot dong rieng",
    /\.ws-id \{[^}]*flex:\s*1 0 100%/.test(khoi));
  check("o ten duoc keo len dong TREN du DOM de sau nut mo danh sach",
    /\.ws-id \{[^}]*order:\s*-1/.test(khoi));
  check("CANARY: khong con bop chu 'Hoi thoai moi' cho vua mot dong",
    !/#wsNewChat \{[^}]*max-width:\s*110px/.test(khoi));
  check("nut mo cot phai dat ve mep phai cua dong duoi",
    /#wsRightBtn \{[^}]*margin-left:\s*auto/.test(khoi));
  // veLoi() nhoi cau bao loi va nut Thu lai vao CHINH o ten, nen o ten cung phai xuong dong
  // duoc, khong thi cau loi bi cat giua chu va chu tren nut be lam hai dong.
  check("cau bao loi va nut Thu lai xuong dong rieng trong o ten",
    /\.ws-id \{[^}]*flex-wrap:\s*wrap/.test(khoi) && /\.ws-id \.ws-err \{[^}]*flex:\s*1 0 100%/.test(khoi));
}

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - workspace");
