/* Trang Cộng sự kẹt "Đang tải cuộc trò chuyện…", bấm gửi không có gì xảy ra (chủ dự án, 28/11/2026, kèm ảnh
   chụp: vào trang Nhóm rồi quay lại trang Cộng sự):

       node tests/js/test_ws_tai_danh_sach_treo_1128.js

   Ô gửi của trang Cộng sự chỉ mở khi đã tải xong danh sách trợ lý VÀ mở xong một phiên (ready). Trước bản sửa,
   lượt tải danh sách lúc dựng trang:
     - không có hạn chờ: một lần đọc /agents không về (máy chủ bận, kết nối treo) để trang kẹt mãi ở dòng
       "Đang tải cuộc trò chuyện…", app.js thấy canSend() = false nên lặng lẽ bỏ qua cú bấm gửi;
     - bị BỎ LẶNG LẼ khi kết quả "cũ" (taiDanhSach trả false vì brain đổi giữa chừng) dù trang vẫn đang mở;
     - nút Thử lại gọi lại đúng lượt đọc đang treo (fetch-gop.js gộp mọi lần đọc cùng khoá vào một request).
   Nay: quá LIST_WAIT_MS thì hiện câu lỗi kèm Thử lại; kết quả cũ mà trang vẫn của lần dựng này thì tải lại;
   Thử lại xin bản MỚI (cache: no-store) chứ không xếp hàng sau lượt treo; lượt treo về muộn không mở lại phiên.

   ROOT đọc được từ biến môi trường JAVIS_ROOT để chạy thử trên bản cũ (thấy đỏ trước khi sửa). */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = process.env.JAVIS_ROOT || path.join(__dirname, "..", "..");
const WS = fs.readFileSync(path.join(ROOT, "dashboard", "workspace.js"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

const fails = [];
function check(name, ok, info) { console.log((ok ? "PASS " : "FAIL ") + name + (ok || !info ? "" : "  " + info)); if (!ok) fails.push(name); }

// Bóc một hàm theo tên (đếm ngoặc nhọn từ dấu { đầu tiên).
function fn(name) {
  const re = new RegExp("(async\\s+)?function " + name + "\\s*\\(");
  const m = re.exec(WS);
  if (!m) return "";
  let i = WS.indexOf("{", m.index), depth = 0, j = i;
  for (; j < WS.length; j++) { if (WS[j] === "{") depth++; else if (WS[j] === "}" && !--depth) break; }
  return WS.slice(m.index, j + 1);
}

const src = ["loadFirstList", "lamLai", "showListError"].map(fn);
check("workspace.js có loadFirstList, lamLai, showListError", src.every(Boolean));
check("render() tải danh sách qua loadFirstList (có hạn chờ), không còn chuỗi .then bỏ lặng lẽ",
  /loadFirstList\(lanDung\)/.test(fn("render")) && !/taiDanhSach\(\)\.then\(function \(moi\) \{ if \(moi === false/.test(WS));
check("có câu lỗi tải lâu ws.err_list_slow (vi + en)",
  typeof VI["ws.err_list_slow"] === "string" && typeof EN["ws.err_list_slow"] === "string"
  && VI["ws.err_list_slow"] !== EN["ws.err_list_slow"]);
const wait = /var LIST_WAIT_MS = (\d+);/.exec(WS);
check("có hạn chờ LIST_WAIT_MS hợp lý (10-30 s)", !!wait && +wait[1] >= 10000 && +wait[1] <= 30000);

if (src.every(Boolean)) {
  // Đồng hồ giả: chạy hẹn giờ bằng tay.
  let timers = [], now = 0;
  const clock = {
    setTimeout(f, ms) { const t = { f, at: now + ms, id: timers.length + 1 }; timers.push(t); return t.id; },
    clearTimeout(id) { timers = timers.filter((t) => t.id !== id); },
    tick(ms) { now += ms; const due = timers.filter((t) => t.at <= now); timers = timers.filter((t) => t.at > now); due.forEach((t) => t.f()); },
  };
  const flush = () => new Promise((r) => setImmediate(r));
  const ident = { innerHTML: "LOADING", querySelectorAll() { return []; }, querySelector() { return null; } };
  const ctx = {
    setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout, console,
    S: { el: { querySelector: (s) => (s === "#wsIdentity" ? ident : null) } },
    active: true, lanDung: 1, pendingCommand: null, OPEN_RECHECK_MS: 2000, LIST_WAIT_MS: +(wait ? wait[1] : 16000),
    t: (k) => k, errs: [], draws: 0, loads: [], reconnect: false,
    reconnecting() { return ctx.reconnect; },
    veLoi(msg) { ctx.errs.push(msg); },
    clearOpenError() {},
    veGiua() {}, dangChon: () => null,
    chonSan() {}, veTrai() {}, chonMacDinh() { ctx.draws++; },
    selectCommand() { ctx.draws++; },
    // Mỗi lượt tải trả về một promise do test quyết định khi nào xong.
    taiDanhSach() { return ctx.load(false); },
    loadListFresh() { return ctx.load(true); },
    load(fresh) { let res, rej; const p = new Promise((a, b) => { res = a; rej = b; }); ctx.loads.push({ fresh, res, rej }); return p; },
  };
  vm.createContext(ctx);
  vm.runInContext("var drawnFor = 0;\n" + src.join("\n") + "\nthis.loadFirstList = loadFirstList; this.lamLai = lamLai;", ctx);

  (async () => {
    // 1) Lượt tải treo: quá hạn chờ thì có câu lỗi + Thử lại, không im lặng.
    ctx.loadFirstList(1);
    await flush();
    clock.tick(ctx.LIST_WAIT_MS - 1);
    check("chưa tới hạn chờ thì chưa báo lỗi", ctx.errs.length === 0);
    ctx.reconnect = true; clock.tick(1);
    check("đang có dải kết nối lại thì hoãn câu lỗi", ctx.errs.length === 0);
    ctx.reconnect = false; clock.tick(ctx.OPEN_RECHECK_MS);
    check("treo quá hạn chờ thì hiện câu lỗi tải lâu (kèm nút Thử lại của veLoi)",
      ctx.errs.length === 1 && ctx.errs[0] === "ws.err_list_slow");
    check("dòng Đang tải được thay bằng câu lỗi, không để vòng xoay quay mãi", ident.innerHTML === "");

    // 2) Thử lại xin bản MỚI, không xếp hàng sau lượt đang treo; xong thì vẽ và mở phiên.
    const retry = ctx.lamLai();
    await flush();
    check("Thử lại gọi taiDanhSach với cờ lấy bản mới", ctx.loads.length === 2 && ctx.loads[1].fresh === true);
    ctx.loads[1].res(true); await retry; await flush();
    check("Thử lại xong thì vẽ danh sách và mở phiên", ctx.draws === 1);
    // Lượt treo về muộn: không mở lại phiên lần nữa (người dùng có thể đang gõ).
    ctx.loads[0].res(true); await flush(); await flush();
    check("lượt treo về muộn không vẽ lại lần hai", ctx.draws === 1);

    // 3) Kết quả cũ (brain đổi giữa chừng) mà trang vẫn là lần dựng này: tải lại, không bỏ lặng lẽ.
    ctx.lanDung = 2; ctx.draws = 0; ctx.loads = []; ctx.errs = []; timers = [];
    ctx.loadFirstList(2);
    ctx.loads[0].res(false); await flush(); await flush();
    check("kết quả cũ mà trang vẫn đang mở thì tải lại", ctx.loads.length === 2);
    ctx.loads[1].res(true); await flush(); await flush();
    check("tải lại xong thì vẽ và mở phiên", ctx.draws === 1);
    check("đã xong thì hẹn giờ chờ được gỡ, không báo lỗi muộn", (clock.tick(60000), ctx.errs.length === 0));

    // 4) Trang đã dựng lại (lanDung đổi) hay đã rời trang: lượt cũ im lặng, không vẽ đè, không báo lỗi.
    ctx.draws = 0; ctx.loads = []; ctx.errs = [];
    ctx.loadFirstList(2); ctx.lanDung = 3;
    ctx.loads[0].res(true); await flush(); await flush();
    clock.tick(60000);
    check("lần dựng cũ về muộn thì không vẽ, không báo lỗi", ctx.draws === 0 && ctx.errs.length === 0);
    ctx.lanDung = 4; ctx.active = false; ctx.loadFirstList(4); ctx.loads[1].res(false); await flush(); await flush();
    check("đã rời trang thì kết quả cũ không kéo tải lại", ctx.loads.length === 2);

    // 5) Lỗi mạng thật: câu lỗi danh sách, không im lặng.
    ctx.active = true; ctx.lanDung = 5; ctx.loads = []; ctx.errs = [];
    ctx.loadFirstList(5); ctx.loads[0].rej(new Error("x")); await flush(); await flush();
    check("lỗi mạng thì hiện ws.err_list", ctx.errs.length === 1 && ctx.errs[0] === "ws.err_list");

    done();
  })().catch((e) => { console.log("FAIL exception " + e.stack); fails.push("exception"); done(); });
} else done();

function done() {
  // loadListFresh chạy THẬT taiDanhSach + api với fetch giả: cả hai lượt đọc mang cache: "no-store", lượt thường thì không.
  const parts = ["taiDanhSach", "loadListFresh", "api"].map(fn);
  const ok = parts.every(Boolean) && /var wantFresh = false;/.test(WS);
  check("có loadListFresh và cờ wantFresh", ok);
  if (ok) {
    const seen = [];
    const c = { lanDung: 1, brain: () => "b", seen,
      fetch(url, init) { seen.push({ url, cache: init && init.cache }); return new Promise(() => {}); } };
    vm.createContext(c);
    vm.runInContext("var wantFresh = false;\n" + parts.join("\n") + "\nthis.moi = loadListFresh; this.thuong = taiDanhSach;", c);
    c.moi();
    check("Thử lại: /agents và /workflows đều xin bản mới (no-store)",
      seen.length === 2 && seen.every((x) => x.cache === "no-store"), JSON.stringify(seen));
    c.thuong();
    check("lượt tải thường sau đó không mang no-store (cờ đã tắt)",
      seen.length === 4 && seen.slice(2).every((x) => x.cache === undefined), JSON.stringify(seen));
  }
  if (fails.length) { console.log("\n" + fails.length + " FAIL"); process.exit(1); }
  console.log("\nALL PASS");
}
