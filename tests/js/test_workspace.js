/* Trang Cộng sự (dashboard/workspace.js): sắp xếp, chọn phiên, tiến độ quy trình.

       node tests/js/test_workspace.js

   Chạy dưới node với DOM giả tối thiểu: workspace.js phơi phần thuần qua window.JavisWorkspace. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");

// `removeEventListener` phải CÓ trong bộ giả: nhiều chỗ của trang gỡ listener lúc rời trang, và
// một trình duyệt thật luôn có hàm này - thiếu nó ở đây là bộ giả sai, không phải code sai.
global.window = { t: (k) => k, ic: () => "", addEventListener() {}, removeEventListener() {},
                  matchMedia: () => ({ matches: false }) };
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

// ============================================================
// PHÒNG BAN: gom cộng sự theo `group` khi xem "Tất cả" (0.59.46)
// ============================================================
// Chủ repo 20/09: gom nhiều agent thành phòng ban khác nhau, giống thư mục dự án bên Trò chuyện.
{
  const ds2 = [
    { slug: "a", name: "A", group: "Marketing" },
    { slug: "b", name: "B", group: "Chung" },
    { slug: "c", name: "C", group: "Finance", pinned: true },
    { slug: "d", name: "D" },                       // không khai group -> Chung
    { slug: "e", name: "E", group: "Ăn uống" },
    { slug: "f", name: "F", group: "Marketing" },
  ];
  const kh = W.gomNhom(ds2, "");
  check("khoi Da ghim dung dau", kh[0].ghim === true && kh[0].items.map(x => x.slug).join() === "c");
  check("moi phong ban mot khoi, xep theo ten tieng Viet, 'Chung' xuong cuoi",
    kh.slice(1).map(k => k.nhom).join("|") === "Ăn uống|Marketing|Chung", kh.map(k => k.nhom).join("|"));
  check("khoi phong ban co co phongBan (ve tieu de thu gon duoc)", kh.slice(1).every(k => k.phongBan === true));
  check("nguoi khong khai group roi vao Chung", kh[3].items.map(x => x.slug).join() === "b,d");
  check("giu thu tu trong phong ban", kh[2].items.map(x => x.slug).join() === "a,f");
  // Đang lọc MỘT phòng ban: không chia phòng ban nữa, chỉ còn "Đã ghim" + phần còn lại.
  const kl = W.gomNhom(ds2.filter(x => (x.group || "Chung") === "Marketing"), "Marketing");
  check("loc mot phong ban -> mot khoi, khong tieu de phong ban",
    kl.length === 1 && kl[0].phongBan === false && kl[0].tieuDe === false);
  check("khong co gi thi rong", W.gomNhom([], "").length === 0);
  const h = W.phongBanHtml("Marketing", 2, true);
  check("tieu de phong ban: co nut thu gon, ten, so nguoi, nut quan ly, va co thu khi dang thu",
    h.includes("ws-dept-tog") && h.includes("Marketing") && h.includes('ws-dept-n">2<')
    && h.includes("data-dmore") && h.includes("ws-dept thu") && h.includes('aria-expanded="false"'));
}

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
             // Khối trả khung chat về bộ não chính: roi() gọi vào nó.
             + src.slice(src.indexOf("  // ---------- trả khung chat về bộ não chính"),
                         src.indexOf("  // ---------- phiên ----------"))
             + src.slice(src.indexOf("  function roi() {"), src.indexOf("\n  window.JavisWorkspace ="));

  const lop = () => ({ _c: {}, toggle(c, on) { this._c[c] = !!on; }, co(c) { return !!this._c[c]; } });
  const oGia = () => ({ innerHTML: "", textContent: "", value: "", hidden: true, dataset: {},
    _attrs: {}, _focus: 0, scrollTop: 0, classList: lop(),
    setAttribute(k, v) { this._attrs[k] = v; }, focus() { this._focus++; },
    // querySelector: veDanhSach dò nút "Xem thêm" vừa vẽ. Trình duyệt thật luôn có hàm này -
    // thiếu nó ở đây là bộ giả sai, không phải code sai. Trả node giả khi HTML vừa vẽ CÓ id
    // đó, để phép thử phân trang bấm được vào nút.
    querySelector(sel) {
      if (sel === "#wsMore" && this.innerHTML.indexOf('id="wsMore"') !== -1) {
        if (!this._more) this._more = oGia();
        return this._more;
      }
      return null;
    },
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
    // `TRANG` (cỡ trang của danh sách trái) khai ở đầu module, ngoài đoạn được bóc - khai lại
    // ở đây y như S, cùng lý do.
    TRANG: 20,
    S: { loai: "agent", q: "", nhom: "", chon: { agent: "a" }, el: el, tienDo: {}, sessionCuaPhien: {},
         tabPhai: "cai", hien: 20, lanChay: {} },
    danhSach: () => ds, loc: W.loc, cacBuoc: () => [], dangChon: () => ds[0],
    // Khối phòng ban (0.59.46) khai ở đầu module, ngoài đoạn được bóc: mượn bản thật qua W,
    // riêng trạng thái thu gọn cho về "không thu" để danh sách vẽ đủ.
    gomNhom: W.gomNhom, phongBanHtml: W.phongBanHtml, daThu: () => false,
    TAB_PHAI: ["cai", "lichsu", "files"],
    luuChon() {}, moPhien() {}, heptLai: () => false, chatReady() {}, active: true, opening: 0,
    esc: (s) => String(s == null ? "" : s), t: (k) => k, ic: () => "<svg></svg>", avatar: () => "<i></i>",
    localStorage: { getItem: (k) => (k in kho ? kho[k] : null), setItem(k, v) { kho[k] = String(v); } },
    document: { getElementById: () => null },
    window: { JavisVaultPanel: { borrow(h) { goi.push("borrow"); ctx._into = h; return true; },
                                 giveBack() { goi.push("giveBack"); } },
              // Kho phiên giả: ghi lại lời gọi để đo việc trả khung chat lúc rời trang.
              JavisSessions: { _cur: null, _goi: [],
                               current() { return this._cur; },
                               new() { this._goi.push("new"); this._cur = null; },
                               open(id) { this._goi.push("open:" + id); this._cur = id; } },
              addEventListener() {}, removeEventListener() {} },
  };
  vm.createContext(ctx); vm.runInContext(doan, ctx);

  // ---- Bộ lọc nhóm là Ô CHỌN, không phải hàng chip ----
  ctx.veTrai();
  const html = nodes["#wsGroup"].innerHTML;
  check("bo loc nhom ve bang <option>, khong con chip", html.indexOf("<option") === 0 && !/ws-group-chip/.test(html));
  check("co dong Tat ca nhom dung dau", html.indexOf('<option value="">ws.all_groups (3)') === 0);
  check("moi nhom kem so dem", html.includes(">Marketing (2)<") && html.includes(">Finance (1)<"));
  check("o chon dung dang o mac dinh Tat ca", nodes["#wsGroup"].value === "");
  // "Tất cả": danh sách chia theo PHÒNG BAN có tiêu đề (0.59.46), Finance đứng trước Marketing.
  const dsHtml = nodes["#wsList"].innerHTML;
  check("xem Tat ca thi co tieu de phong ban Finance va Marketing",
    dsHtml.includes('data-dept="Finance"') && dsHtml.includes('data-dept="Marketing"')
    && dsHtml.indexOf('data-dept="Finance"') < dsHtml.indexOf('data-dept="Marketing"'));
  check("tieu de phong ban dung truoc nguoi trong phong ban do",
    dsHtml.indexOf('data-dept="Marketing"') < dsHtml.indexOf("Người viết"));
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

  // ---- Muc DA GHIM phai nhin ra duoc (0.59.20) ----
  // Chu du an bao 16/09: ghim roi ma danh sach trong y het chua ghim. Dau ghim nam TRONG the
  // <strong> cua cai ten, ma the do cat chu bang ellipsis -> ten dai mot chut la mat dau ghim.
  ds[1].pinned = true;
  ctx.veDanhSach();
  const htmlGhim = nodes["#wsList"].innerHTML;
  check("hang ghim mang lop rieng", /ws-item-wrap ghim/.test(htmlGhim));
  check("dau ghim nam NGOAI the ten (khong bi ellipsis cat)",
    /<\/strong>/.test(htmlGhim) && htmlGhim.indexOf("ws-item-pin") > htmlGhim.indexOf("</strong>"));
  check("CANARY: dau ghim khong con nam trong <strong>",
    !/<strong>[^<]*<span class="ws-item-pin"/.test(htmlGhim));
  // 0.59.46: ở "Tất cả", phần không ghim chia theo PHÒNG BAN chứ không gom thành "Còn lại"
  // nữa; nhãn "Còn lại" chỉ còn khi đang lọc MỘT phòng ban mà có mục ghim phía trên.
  check("co nhan Da ghim, phan con lai chia theo phong ban (khong con nhan Con lai)",
    htmlGhim.includes("ws.grp_pinned") && !htmlGhim.includes("ws.grp_rest")
    && htmlGhim.includes('data-dept="Marketing"'));
  ctx.S.nhom = "Finance"; ctx.veDanhSach();
  check("loc mot phong ban ma co ghim thi van co nhan Con lai, khong co tieu de phong ban",
    nodes["#wsList"].innerHTML.includes("ws.grp_pinned") === (ds[1].group === "Finance")
    && !nodes["#wsList"].innerHTML.includes("data-dept="));
  ctx.S.nhom = ""; ctx.veDanhSach();
  ds[1].pinned = false;
  ctx.veDanhSach();
  check("khong ghim gi thi KHONG doi them nhan nhom",
    !nodes["#wsList"].innerHTML.includes("ws.grp_pinned")
    && !nodes["#wsList"].innerHTML.includes("ws.grp_rest"));

  // ---- Phan trang danh sach trai: 20 muc, bam Xem them ra 20 nua (0.59.20) ----
  const dsGoc = ds.slice();
  ds.length = 0;
  for (let i = 0; i < 45; i++) ds.push({ slug: "t" + i, name: "Tro ly " + i, role: "r", group: "Chung" });
  ctx.S.hien = 20;
  ctx.veDanhSach();
  const dem = (h) => (h.match(/data-slug="/g) || []).length;
  check("chi ve 20 muc dau", dem(nodes["#wsList"].innerHTML) === 20);
  check("con muc phia sau thi co nut Xem them", nodes["#wsList"].innerHTML.includes('id="wsMore"')
    && nodes["#wsList"].innerHTML.includes("sess.more"));
  nodes["#wsList"]._more.onclick();
  check("bam Xem them ra them 20 muc", dem(nodes["#wsList"].innerHTML) === 40 && ctx.S.hien === 40);
  nodes["#wsList"]._more.onclick();
  check("het muc thi thoi ve nut Xem them",
    dem(nodes["#wsList"].innerHTML) === 45 && !nodes["#wsList"].innerHTML.includes('id="wsMore"'));
  check("CANARY: go chu tim la ve lai TRANG DAU", (() => {
    o.value = "Tro ly 4"; o.oninput({ target: o });
    return ctx.S.hien === 20;
  })());
  o.value = ""; o.oninput({ target: o });
  ds.length = 0; dsGoc.forEach((x) => ds.push(x));
  ctx.S.hien = 20;
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
    document: { getElementById: () => null },
    // Bộ giả phải có đủ cả hai hàm listener - trình duyệt thật luôn có.
    window: { addEventListener() {}, removeEventListener() {} },
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

// ============================================================
// Ghim / chuyen thu muc / sua / xoa tren TUNG dong danh sach (0.59.14)
// ============================================================
{
  const css = fs.readFileSync(path.join(root, "dashboard", "console.css"), "utf8");
  const ws = fs.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8");
  const vi = JSON.parse(fs.readFileSync(path.join(root, "dashboard", "i18n", "vi.json"), "utf8"));
  const en = JSON.parse(fs.readFileSync(path.join(root, "dashboard", "i18n", "en.json"), "utf8"));

  // Muc GHIM len dau, trong nhom ghim van xep theo moc gan nhat.
  const ds = [{ slug: "a", name: "Aa", last_chat_at: 99 },
              { slug: "b", name: "Bb", last_chat_at: 10, pinned: true },
              { slug: "c", name: "Cc", last_chat_at: 50, pinned: true },
              { slug: "d", name: "Dd", last_chat_at: 70 }];
  check("ghim len dau, trong nhom ghim van theo moc gan nhat",
    W.sapXep(ds, "last_chat_at").map(x => x.slug).join(",") === "c,b,a,d");
  check("khong co muc ghim thi thu tu y NHU CU",
    W.sapXep(ds.map(x => ({ ...x, pinned: false })), "last_chat_at")
      .map(x => x.slug).join(",") === "a,d,c,b");

  // Nut "..." KHONG duoc long trong nut chon muc (button trong button la HTML sai).
  check("nut quan ly nam NGOAI nut chon muc, trong mot khoi boc",
    /class="ws-item-wrap/.test(ws) && /class="ws-item-more"/.test(ws)
    && ws.indexOf('class="ws-item-more"') > ws.indexOf("</button>"));
  check("menu co du bon dong tac", /t\("ws.pin"\)/.test(ws) && /t\("ws.move_group"\)/.test(ws)
    && /t\("ws.edit"\)/.test(ws) && /data-act="xoa"/.test(ws));
  check("doi nhom/ghim di duong /capability/meta, KHONG POST /agents (endpoint do nhan ca prompt)",
    /api\("\/capability\/meta"/.test(ws) && !/api\("\/agents",/.test(ws));
  check("xoa co hoi lai truoc", /confirm\(hoi\)/.test(ws));
  check("menu dung position FIXED (cot danh sach co overflow rieng)",
    /\.ws-menu \{ position: fixed/.test(css));
  check("roi trang thi dong menu (menu song o body)", /function roi\(\)[\s\S]{0,240}dongMenu\(\);/.test(ws));
  check("man cam ung van thay nut quan ly (hover: none)",
    /@media \(hover: none\) \{ \.ws-item-more/.test(css));
  ["ws.manage", "ws.pin", "ws.unpin", "ws.pinned", "ws.move_group", "ws.group_new",
   "ws.group_ask", "ws.edit", "ws.err_meta"].forEach(k => {
    check("i18n co khoa " + k, !!vi[k] && !!en[k]);
  });
}

// ============================================================
// Thu tu tab cot phai: Lich su -> Thu muc -> Cai dat (0.59.14)
// ============================================================
// Chu du an chot 16/09: viec hang ngay la mo lai hoi thoai cu va mo file, con cai dat tro ly
// thi sua mot lan roi thoi.
{
  const ws = fs.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8");
  check("TAB_PHAI xep lichsu truoc, cai dat sau cung",
    /var TAB_PHAI = \["lichsu", "files", "cai"\]/.test(ws));
  check("tab mac dinh la Lich su", /tabPhai: "lichsu"/.test(ws)
    && /TAB_PHAI\.indexOf\(r\) >= 0 \? r : "lichsu"/.test(ws));
  const iTabs = ws.indexOf('class="cside-tabs ws-rtabs"');
  const khoi = ws.slice(iTabs, iTabs + 700);
  check("thu tu NUT ve ra cung khop (lichsu, files, cai)",
    khoi.indexOf('data-rtab="lichsu"') < khoi.indexOf('data-rtab="files"')
    && khoi.indexOf('data-rtab="files"') < khoi.indexOf('data-rtab="cai"'));
}

// ============================================================
// Mo file trong chat cong su: TAT HAN khung chat (0.59.16)
// ============================================================
// Chu du an chot 16/09 sau khi xem ban 0.59.14: "mo file trong hoi thoai cua agent van hien
// khung chat, dang nhe no phai tat het khung chat di". Ban truoc giu ca hai canh nhau roi tu
// canh bang JS (do khoang giua, thu cot phai, xep doc) - khoang giua trang nay chi con ~760px
// tren man 1600px nen chia doi thi ca hai ben deu hep.
// Khoi nay THAY hai khoi cu da bo: "xep NGANG khong de lai khoang trong" (0.59.4) va "khung
// chat khong bi bop con mot soi" (0.59.14). Ca hai deu la cach chia doi khoang giua.
{
  const css = fs.readFileSync(path.join(root, "dashboard", "console.css"), "utf8");
  check("mo file thi khung chat AN HAN (khong con @media rieng)",
    /\.ws-main\.edit-on > \.ws-slot \{ display: none; \}/.test(css));
  check("CANARY: khong con bo cuc hai cot khi sua file",
    !/\.ws-main\.edit-on \{ display: grid/.test(css) && !/edit-doc/.test(css));
  check("CANARY: khong con luat @media 860px cho .ws-slot luc edit-on",
    !/@media \(max-width: 860px\) \{ \.ws-main\.edit-on > \.ws-slot/.test(css));
  check("trinh sua van la con DUY NHAT hien ra cua khoang giua",
    /\.ws-main\.edit-on > \.ws-edit \{ display: flex; \}/.test(css));

  const ws = fs.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8");
  check("CANARY: JS khong con do khung / quan sat DOM de canh bo cuc sua file",
    !/quyetDinhKhungSua|canhKhungSua|theoKhungSua/.test(ws));
  check("workspace.js khong con phoi quyetDinhKhungSua", !W.quyetDinhKhungSua);
}

// ============================================================
// Roi trang Cong su: TRA khung chat ve bo nao chinh (0.59.15)
// ============================================================
// Khung chat la node MUON: trang Cong su, trang Tro chuyen va man Javis dung CHUNG mot khung.
// Roi trang ma khong lam gi thi doan chat voi tro ly con nam nguyen o hai cho kia, va
// savedSessionId van la phien agent:<slug> nen tin go tiep BAY VAO PHIEN CUA TRO LY. Chu du an
// bao 16/09: "2 chuc nang chat khac nhau, nguoi dung se hoi kho hieu".
{
  const fs2 = require("fs");
  const vm2 = require("node:vm");
  const src2 = fs2.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8");
  // `_phienTruoc` khai ở đầu module (cùng chỗ với `opening`, `ready`...), ngoài đoạn được
  // bóc, nên phải khai lại ở đây - y như ctx phải cấp S, window cho đoạn.
  const doan2 = "var _phienTruoc = null;\n"
    + src2.slice(src2.indexOf("  // ---------- trả khung chat về bộ não chính"),
                 src2.indexOf("  // ---------- phiên ----------"));
  const lamCtx = (cur, sessionCuaPhien) => {
    const kho = { _cur: cur, _goi: [],
                  current() { return this._cur; },
                  new() { this._goi.push("new"); this._cur = null; },
                  open(id) { this._goi.push("open:" + id); this._cur = id; } };
    const c = { S: { sessionCuaPhien: sessionCuaPhien }, window: { JavisSessions: kho }, kho };
    vm2.createContext(c); vm2.runInContext(doan2, c);
    return c;
  };

  // 1. Dang mo phien TRO LY + truoc do co cuoc cua bo nao chinh -> xoa trang roi mo lai cuoc do.
  let c = lamCtx("chat-cu", {});
  c.nhoPhienTruoc();                       // luc dung trang: khung con la cuoc cua bo nao chinh
  c.S.sessionCuaPhien["phien-agent"] = "coach";
  c.kho._cur = "phien-agent";              // moPhien da doi sang phien tro ly
  c.traKhungChat();
  check("roi trang: xoa trang TRUOC roi moi mo lai cuoc cu",
    c.kho._goi.join(",") === "new,open:chat-cu");
  check("roi trang: khung chat ve dung cuoc cua bo nao chinh", c.kho._cur === "chat-cu");

  // 2. Khong co cuoc nao truoc do (vao thang trang Cong su) -> chi xoa trang.
  c = lamCtx(null, {});
  c.nhoPhienTruoc();
  c.S.sessionCuaPhien["phien-agent"] = "coach";
  c.kho._cur = "phien-agent";
  c.traKhungChat();
  check("roi trang: khong co cuoc cu thi mo khung TRONG", c.kho._goi.join(",") === "new");

  // 3. Dang KHONG mo phien tro ly (vd chua chon cong su nao) -> khong dung gi vao khung chat.
  c = lamCtx("chat-cu", {});
  c.nhoPhienTruoc();
  c.traKhungChat();
  check("CANARY: khong mo phien tro ly thi KHONG dung vao khung chat", c.kho._goi.length === 0);

  // 4. Cuoc "truoc do" lai chinh la mot phien tro ly (F5 ngay tren trang Cong su) -> chi xoa
  //    trang, khong mo lai mot phien tro ly khac.
  c = lamCtx("phien-agent-cu", { "phien-agent-cu": "coach" });
  c.nhoPhienTruoc();
  c.S.sessionCuaPhien["phien-agent"] = "coach2";
  c.kho._cur = "phien-agent";
  c.traKhungChat();
  check("CANARY: khong mo lai mot phien tro ly khac", c.kho._goi.join(",") === "new");

  const ws2 = src2;
  check("roi() co goi traKhungChat", /function roi\(\)[\s\S]{0,200}traKhungChat\(\)/.test(ws2));
  check("nho cuoc dang do NGAY LUC dung trang", /chonTabPhai\(S\.tabPhai\);\s*\n\s*nhoPhienTruoc\(\);/.test(ws2));
}

// ============================================================
// Tab Lich su: MOT danh sach, khong phai hai (0.59.20)
// ============================================================
// Chu du an bao 16/09: "Lich su cua quy trinh hien dang co 2 lich su". Dung: moi lan chay quy
// trinh de ra dung MOT hoi thoai, nen "LAN CHAY" va "HOI THOAI" la cung mot viec ke hai lan.
// Nay chi con danh sach hoi thoai (ban muon cua trang Tro chuyen: co o tim, ghim, sua, xoa,
// Xem them), con thu RIENG cua lan chay - avatar cac tro ly da phoi hop va trang thai - gan
// thang vao hang hoi thoai do qua ham trang tri.
{
  const vm3 = require("node:vm");
  const src3 = fs.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8");
  const doan3 = src3.slice(src3.indexOf("  function veLichSu(item) {"),
                           src3.indexOf("  // ---------- sự kiện quy trình từ WebSocket"));
  const hostGia = { innerHTML: "", querySelector: () => ({}) };
  const goiMount = [];
  const ctx3 = {
    S: { loai: "workflow", el: { querySelector: (s) => (s === "#wsRightHistory" ? hostGia : null) },
         chon: { workflow: "wf" }, lanChay: {} },
    esc: (x) => String(x == null ? "" : x), t: (k) => k, avatar: (a, n) => '<i data-avatar="' + (a && a.slug) + '" data-n="' + n + '"></i>',
    agentOf: (sl) => ({ slug: sl }), kenh: () => "workflow:wf", dangChon: () => ({ slug: "wf" }),
    conDangXem: () => true, moPhien() {}, api: async () => ({ runs: [] }), brain: () => "b",
    window: { JavisChatSide: { mount: (h, o) => goiMount.push(o), refresh: () => goiMount.push("refresh") } },
  };
  vm3.createContext(ctx3); vm3.runInContext(doan3, ctx3);

  ctx3.veLichSu({ slug: "wf" });
  check("tab Lich su chi dung MOT khung danh sach", (hostGia.innerHTML.match(/<div /g) || []).length === 1
    && hostGia.innerHTML.includes('id="wsSess"'));
  check("CANARY: khong con danh sach LAN CHAY rieng", !hostGia.innerHTML.includes("wsRuns")
    && !src3.includes('id="wsRuns"'));
  check("CANARY: khong con tieu de nao day nut Hoi thoai moi xuong giua cot",
    !hostGia.innerHTML.includes("ws-rtitle"));
  check("quy trinh thi cot lich su nhan ham trang tri",
    typeof goiMount[0].trangTri === "function" && goiMount[0].chiHoiThoai === true);

  // Trang tri: avatar cac tro ly da phoi hop + trang thai lan chay, gan dung hang cua phien do.
  ctx3.S.lanChay = { s1: { session_id: "s1", status: "error", nhan: "lỗi",
                           steps: [{ agent: "a1" }, { agent: "a2" }, { agent: "a1" }] } };
  const tt = ctx3.trangTriHang({ id: "s1" });
  check("hang co lan chay thi deo avatar cac tro ly", /ws-run-avatars/.test(tt.dau)
    && (tt.dau.match(/data-avatar/g) || []).length === 2);
  check("trang thai lan chay thanh mot nhan nho", /ws-run-badge error/.test(tt.meta) && tt.meta.includes("lỗi"));
  check("CANARY: hang khong phai lan chay thi khong trang tri gi",
    ctx3.trangTriHang({ id: "khong-co" }) === null);

  // Tro ly khong co lan chay nao -> khong gan ham trang tri (khoi tra ve null cho tung hang).
  goiMount.length = 0; ctx3.S.loai = "agent";
  ctx3.veLichSu({ slug: "ag" });
  check("tro ly thi khong can ham trang tri", goiMount[0].trangTri === null);

  const ss = fs.readFileSync(path.join(root, "dashboard", "sessions-ui.js"), "utf8");
  check("sessions-ui nhan tuy chon trangTri", /hamTrangTri = typeof o\.trangTri === "function"/.test(ss));
  check("trang tri duoc chen vao ca tieu de lan hang meta",
    /\(tt\.dau \|\| ""\)/.test(ss) && /\(tt\.meta \|\| ""\)/.test(ss));
  check("CANARY: ham trang tri nem loi thi KHONG lam cut danh sach",
    /try \{ tt = hamTrangTri\(s\) \|\| \{\}; \} catch \(e\) \{ tt = \{\}; \}/.test(ss));
}

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - workspace");
