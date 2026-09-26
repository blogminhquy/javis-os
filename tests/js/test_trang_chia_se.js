/* Trang quản lý link chia sẻ: phải VẼ RA ĐƯỢC và phải thu hồi được (0.59.39).

       node tests/js/test_trang_chia_se.js

   Chủ dự án 18/09, ngay sau khi xem xong nút Chia sẻ: "anh cần phải có thêm phần quản lý các
   link share để có thể chủ động thu hồi nếu quên." Đúng chỗ thiếu: link không hết hạn và
   không mật khẩu, nên chỉ tạo được mà không có chỗ nhìn lại toàn bộ thì một link lỡ gửi nhầm
   sẽ sống mãi mà chủ nhân không nhớ nó tồn tại.

   Test này CHẠY THẬT hàm renderSharePage: bóc nó khỏi console.js bằng cách đếm ngoặc, cho một
   DOM giả và một fetch giả, rồi soi HTML nhận được cùng các lời gọi mạng nó phát ra.

   Không soi mã nguồn bằng regex. Hôm qua một phép thử kiểu đó báo xanh trong khi trang Cài đặt
   linh vật trắng trơn vì một biến ngoài tầm với (xem test_pet_trang_cai_dat.js). Trang này
   cũng dựng chuỗi template dài y như vậy, nên nó cần đúng loại canh gác đó. */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

function nut() {
  const o = {
    _html: "", disabled: false, textContent: "", dataset: {}, onclick: null,
    classList: { add() {}, remove() {}, contains: () => false }, style: {},
    setAttribute() {}, addEventListener() {}, appendChild() {}, remove() {}, select() {},
    querySelector: () => nut(), querySelectorAll: () => [],
    get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  };
  return o;
}

function bocHam(src, khai) {
  const i = src.indexOf(khai);
  if (i < 0) return null;
  let d = 0, j = src.indexOf("{", i);
  const dau = j;
  for (; j < src.length; j++) {
    if (src[j] === "{") d++;
    else if (src[j] === "}" && !--d) break;
  }
  return src.slice(dau + 1, j);
}

const consoleSrc = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const than = bocHam(consoleSrc, "async function renderSharePage(el) {");
check("bóc được renderSharePage khỏi console.js", !!than && than.length > 1200,
  than ? than.length + " ký tự" : "không thấy");

const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const t = (k) => (typeof vi[k] === "string" ? vi[k] : "!!THIEU:" + k + "!!");
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const ic = () => "<svg></svg>";

// Nút con dò RA TỪ HTML thật mà hàm vừa dựng, thay vì cắm sẵn bằng tay: cắm tay thì test vẫn
// xanh kể cả khi hàm quên in nút ra. Đây đúng là việc trình duyệt làm khi gặp querySelectorAll.
function stub(tenId) {
  const o = nut();
  o.id = tenId || "";
  // Nút con NHỚ theo (thuộc tính, giá trị) và quên hết mỗi lần innerHTML bị ghi đè. Đây chính
  // là điều trình duyệt làm, và nó là điều kiện để test kiểm được "hàm có gắn onclick chưa":
  // dựng nút mới mỗi lần hỏi thì nút mà test cầm không phải nút mà hàm vừa gắn tay vào.
  let kho = new Map();
  o._ghi = (v) => { o._html = String(v); kho = new Map(); };
  Object.defineProperty(o, "innerHTML", {
    configurable: true,
    get() { return o._html; },
    set(v) { o._ghi(v); },
  });
  o.querySelectorAll = (sel) => {
    // Hai dạng chọn tử mà mã thật dùng: [data-x] và [data-x="giá trị"].
    const m = /^\[data-([a-z-]+)(?:="([^"]*)")?\]$/.exec(sel);
    if (!m) return [];
    const camel = m[1].replace(/-([a-z])/g, (x, c) => c.toUpperCase());
    const re = new RegExp('data-' + m[1] + '="([^"]*)"', "g");
    const ra = [];
    let g;
    while ((g = re.exec(o._html))) {
      if (m[2] !== undefined && g[1] !== m[2]) continue;
      const khoa = m[1] + "=" + g[1];
      if (!kho.has(khoa)) { const b = nut(); b.dataset[camel] = g[1]; kho.set(khoa, b); }
      ra.push(kho.get(khoa));
    }
    return ra;
  };
  o.querySelector = (sel) => o.querySelectorAll(sel)[0] || null;
  o.insertAdjacentHTML = (vitri, h) => { o._ghi(o._html + String(h)); };   // pager() gắn thanh lật trang
  return o;
}

// Hai hằng số nằm NGOÀI hàm được bóc ra, nên phải đọc từ chính nguồn - chép số vào test là
// hai chỗ trôi khỏi nhau ngay lần chỉnh đầu tiên.
function hangSo(ten, macDinh) {
  const m = new RegExp("const\\s+" + ten + "\\s*=\\s*(\\d+)").exec(consoleSrc);
  return m ? Number(m[1]) : macDinh;
}
const MOI_TRANG = hangSo("SHARE_MOI_TRANG", 20);
const NGUONG_TIM = hangSo("SHARE_NGUONG_TIM", 8);

// pager() THẬT của console.js, không phải bản giả: phân trang của trang Chia sẻ chạy đúng bộ
// máy dùng chung với trang Kỹ năng, nên test phải chạy đúng bộ máy đó.
const thanPager = bocHam(consoleSrc, "function pager(box, items, perPage, renderPage, emptyHtml) {");
const pagerThat = new Function("box", "items", "perPage", "renderPage", "emptyHtml", "window",
  thanPager)
  ;

// Chạy hàm với danh sách link giả và fetch giả.
async function chay(items, opts) {
  const goi = [];
  const el = stub("");
  const list = stub("shareList");
  const oTim = stub("shareSearch");
  // Ô tìm và danh sách là con của el. Trả về đúng khi hàm đi tìm chúng, và chỉ trả ô tìm khi
  // hàm THẬT SỰ có in ô đó ra (dưới ngưỡng thì nó không in, và test phải thấy được điều đó).
  el.querySelector = (sel) => {
    if (sel === "#shareList") return el._html.indexOf('id="shareList"') >= 0 ? list : null;
    if (sel === "#shareSearch") return el._html.indexOf('id="shareSearch"') >= 0 ? oTim : null;
    return null;
  };
  el.querySelectorAll = () => [];
  // innerHTML của el như trình duyệt thấy: ô danh sách rỗng được thay bằng ruột thật của nó.
  Object.defineProperty(el, "innerHTML", {
    configurable: true,
    get() {
      return String(this._html).replace('<div class="share-list" id="shareList"></div>',
        '<div class="share-list" id="shareList">' + list._html + "</div>");
    },
    set(v) { el._ghi(v); },
  });
  const fetchGia = async (url, o) => {
    goi.push({ url, body: o && o.body });
    if (url === "/share/list") {
      if (opts && opts.loi) throw new Error("mat mang");
      return { json: async () => ({ ok: true, items }) };
    }
    return { json: async () => ({ ok: true }) };
  };
  const win = {
    isSecureContext: false,
    JavisPager: (box, arr, per, ve, trong) => pagerThat(box, arr, per, ve, trong, win),
    t: t,
  };
  await new Function("el", "_renderGen", "ic", "t", "esc", "fetch", "location",
    "navigator", "window", "document", "SHARE_MOI_TRANG", "SHARE_NGUONG_TIM",
    "return (async () => {" + than + "})();")(
    el, 1, ic, t, esc, fetchGia, { origin: "https://nas.vi.du" },
    { clipboard: null }, win,
    { createElement: () => nut(), body: { appendChild() {} } },
    MOI_TRANG, NGUONG_TIM);
  return { el, list, oTim, goi, fetchGia };
}

(async () => {
  const MAU = [
    { token: "tok1", brain: "brain", path: "thu-muc/app.html", tao_luc: 1789000000, url: "/s/tok1" },
    { token: "tok2", brain: "brain", path: "ghi-chu.md", tao_luc: 1789000100, url: "/s/tok2" },
  ];

  // ---- 1. Có link: vẽ đủ, không ném lỗi ----
  {
    let loi = null, r = null;
    try { r = await chay(MAU); } catch (e) { loi = e; }
    check("VẼ ĐƯỢC, không ném lỗi giữa chừng", loi === null,
      loi && loi.constructor.name + ": " + loi.message);
    const html = r.el.innerHTML;
    check("trang KHÔNG rỗng", html.length > 400, html.length + " ký tự");
    check("gọi đúng /share/list", r.goi.some(g => g.url === "/share/list"));
    check("hiện ĐỦ mọi link đang sống",
      (html.match(/data-token=/g) || []).length === MAU.length,
      (html.match(/data-token=/g) || []).length + "/" + MAU.length);
    check("mỗi link có nút Thu hồi", (html.match(/data-share-revoke=/g) || []).length === MAU.length);
    check("mỗi link có nút Chép", (html.match(/data-share-copy=/g) || []).length === MAU.length);
    check("hiện URL ĐẦY ĐỦ ghép từ origin, không phải đường dẫn cụt",
      html.includes("https://nas.vi.du/s/tok1") && html.includes("https://nas.vi.du/s/tok2"));
    check("hiện tên file cho dễ nhận ra", html.includes("app.html") && html.includes("ghi-chu.md"));
    check("hiện CẢ đường dẫn đầy đủ, để phân biệt hai file trùng tên",
      html.includes("thu-muc/app.html"));
    check("có câu cảnh báo link là công khai", html.includes(vi["share.warn"]));
    check("không nhãn nào thiếu bản dịch", !html.includes("!!THIEU:"),
      (html.match(/!!THIEU:[^!]+!!/g) || []).slice(0, 4).join(", "));
  }

  // ---- 2. Chưa có link nào: nói rõ cách tạo, không để trang trống ----
  {
    const r = await chay([]);
    const html = r.el.innerHTML;
    check("chưa có link thì hiện lời chỉ dẫn, không bỏ trang trống",
      html.includes(vi["share.empty"]) && html.length > 100);
  }

  // ---- 3. Mất mạng: báo lỗi chứ không treo vòng xoay mãi ----
  {
    const r = await chay([], { loi: true });
    check("mất mạng thì báo lỗi, không kẹt ở vòng xoay",
      r.el.innerHTML.includes(vi["app.err_net"]) && !r.el.innerHTML.includes("ic-spin"),
      r.el.innerHTML.slice(0, 80));
  }

  // ---- 4. Nút Thu hồi gọi đúng endpoint với đúng token ----
  {
    const r = await chay(MAU);
    const b = r.list.querySelectorAll("[data-share-revoke]")[0];
    check("hàm có gắn xử lý vào nút Thu hồi", !!b && typeof b.onclick === "function");
    check("nút Thu hồi mang token của ĐÚNG hàng đó", !!b && b.dataset.shareRevoke === "tok1",
      b && b.dataset.shareRevoke);
    if (b && typeof b.onclick === "function") {
      await b.onclick();
      const rv = r.goi.find(g => g.url === "/share/revoke");
      check("bấm Thu hồi gọi /share/revoke", !!rv, r.goi.map(g => g.url).join(", "));
      check("và gửi ĐÚNG token của hàng đó",
        !!rv && JSON.parse(rv.body).token === "tok1", rv && rv.body);
      check("link đã thu hồi biến khỏi danh sách ngay, khỏi phải tải lại trang",
        !r.el.innerHTML.includes("tok1") && r.el.innerHTML.includes("tok2"));
    }
  }

  // ---- 6. TÌM KIẾM (chủ dự án 18/09: "làm thêm phân trang và tìm kiếm ở phần link chia sẻ") ----
  function nhieuLink(n, tenHam) {
    const ra = [];
    for (let i = 0; i < n; i++) {
      ra.push({ token: "t" + i, brain: "brain", path: (tenHam ? tenHam(i) : "thu-muc/note-" + i + ".md"),
        tao_luc: 1789000000 + i, url: "/s/t" + i });
    }
    return ra;
  }
  const demHang = (h) => (h.match(/class="share-row"/g) || []).length;

  {
    // Danh sách ngắn thì KHÔNG hiện ô tìm: một ô trống chiếm chỗ mà mắt vẫn quét nhanh hơn gõ.
    const it = await chay(nhieuLink(NGUONG_TIM));
    check("danh sách ngắn thì chưa hiện ô tìm", it.el.innerHTML.indexOf('id="shareSearch"') < 0,
      "ngưỡng = " + NGUONG_TIM);

    const r = await chay(nhieuLink(NGUONG_TIM + 1, (i) =>
      (i === 0 ? "ke-hoach/Báo cáo quý.md" : "thu-muc/note-" + i + ".md")));
    check("danh sách dài thì hiện ô tìm", r.el.innerHTML.indexOf('id="shareSearch"') >= 0);
    check("ô tìm có chỗ gợi ý bằng tiếng người", r.el.innerHTML.includes(vi["share.search_ph"]));
    check("hàm có gắn xử lý gõ vào ô tìm", typeof r.oTim.oninput === "function");

    // Gõ tìm: chỉ còn hàng khớp.
    r.oTim.value = "bao cao";
    r.oTim.oninput();
    check("gõ KHÔNG DẤU vẫn tìm ra file CÓ DẤU", demHang(r.list._html) === 1, demHang(r.list._html));
    check("và đúng là file đó", r.list._html.includes("Báo cáo quý.md"));
    // 0.59.49: ô tìm hiện từ link thứ hai (ngưỡng 1), và có dòng đếm "Khớp x / y link" khi gõ.
    check("ngưỡng hiện ô tìm là 1 (có từ 2 link là thấy ô tìm)", NGUONG_TIM === 1, NGUONG_TIM);
    check("gõ tìm thì có dòng đếm số link khớp", r.el.innerHTML.includes('id="shareCount"'));

    // Nhiều từ = thu hẹp dần, phải khớp HẾT.
    r.oTim.value = "ke-hoach bao cao";
    r.oTim.oninput();
    check("gõ nhiều từ thì phải khớp HẾT", demHang(r.list._html) === 1, demHang(r.list._html));
    r.oTim.value = "ke-hoach note";
    r.oTim.oninput();
    check("nhiều từ không cùng một hàng thì ra rỗng", demHang(r.list._html) === 0);
    check("và nói rõ là không khớp, không bỏ khoảng trống câm",
      r.list._html.includes(vi["share.no_match"]));

    // Tìm theo THƯ MỤC, không chỉ tên file.
    r.oTim.value = "thu-muc";
    r.oTim.oninput();
    check("tìm được theo tên thư mục", demHang(r.list._html) === NGUONG_TIM, demHang(r.list._html));

    // Gõ mà vẽ lại CẢ thẻ thì con trỏ nhảy về đầu ô sau mỗi chữ. Vỏ thẻ phải đứng yên,
    // chỉ ruột danh sách đổi.
    const voTruoc = r.el._html;
    r.oTim.value = "note-1";
    r.oTim.oninput();
    check("gõ tìm KHÔNG vẽ lại vỏ thẻ (ô tìm giữ nguyên tiêu điểm)", r.el._html === voTruoc);

    // Xoá từ khoá thì danh sách trở lại đầy đủ (giới hạn bởi một trang).
    r.oTim.value = "";
    r.oTim.oninput();
    check("xoá từ khoá thì danh sách trở lại", demHang(r.list._html) === NGUONG_TIM + 1);
  }

  // ---- 7. PHÂN TRANG ----
  {
    const tong = MOI_TRANG * 2 + 3;
    const r = await chay(nhieuLink(tong));
    check("một trang chỉ vẽ tối đa " + MOI_TRANG + " link",
      demHang(r.list._html) === MOI_TRANG, demHang(r.list._html));
    check("có thanh lật trang", r.list._html.includes("jv-pager"));
    check("nút Lùi bị khoá ở trang đầu", /data-pg="prev"[^>]*disabled/.test(r.list._html));
    check("nút Tiếp KHÔNG bị khoá ở trang đầu", !/data-pg="next"[^>]*disabled/.test(r.list._html));
    check("số tổng vẫn hiện đủ ở đầu thẻ, không phải số của một trang",
      r.el.innerHTML.includes(">" + tong + "<"), tong);

    // Bấm Tiếp cho tới trang cuối: trang giữa đầy, trang cuối còn đúng phần dư.
    const tiep = r.list.querySelector('[data-pg="next"]');
    check("thanh lật trang có nút bấm thật", !!tiep && typeof tiep.onclick === "function");
    if (tiep && typeof tiep.onclick === "function") {
      tiep.onclick();
      check("bấm Tiếp sang trang 2, vẫn đầy " + MOI_TRANG + " link",
        demHang(r.list._html) === MOI_TRANG, demHang(r.list._html));
      const tiep2 = r.list.querySelector('[data-pg="next"]');
      if (tiep2 && typeof tiep2.onclick === "function") tiep2.onclick();
      check("trang cuối còn đúng phần dư", demHang(r.list._html) === tong - MOI_TRANG * 2,
        demHang(r.list._html) + " (chờ " + (tong - MOI_TRANG * 2) + ")");
      check("tới trang cuối thì nút Tiếp bị khoá",
        /data-pg="next"[^>]*disabled/.test(r.list._html));
      const lui = r.list.querySelector('[data-pg="prev"]');
      if (lui && typeof lui.onclick === "function") lui.onclick();
      check("bấm Lùi quay lại được", demHang(r.list._html) === MOI_TRANG, demHang(r.list._html));
    }

    // Lọc rồi mới phân trang: tìm xong thì số trang phải tính trên KẾT QUẢ LỌC.
    const r2 = await chay(nhieuLink(tong, (i) =>
      (i < 3 ? "rieng/bao-cao-" + i + ".md" : "thu-muc/note-" + i + ".md")));
    r2.oTim.value = "rieng";
    r2.oTim.oninput();
    check("lọc xong thì KHÔNG còn thanh lật trang (kết quả lọt một trang)",
      !r2.list._html.includes("jv-pager"), demHang(r2.list._html) + " hàng");
    check("và chỉ còn đúng số hàng khớp", demHang(r2.list._html) === 3, demHang(r2.list._html));
  }

  // ---- 5. Trang phải được khai ở ĐỦ các sổ đăng ký, không thì lệnh bằng lời gọi hụt ----
  {
    const ui = fs.readFileSync(path.join(ROOT, "dashboard", "ui-actions.js"), "utf8");
    const py = fs.readFileSync(path.join(ROOT, "server", "ui_targets.py"), "utf8");
    // Ghim CÓ icon, không ghim icon NÀO: đổi icon là chuyện thẩm mỹ bình thường (18/09 nó đã
    // đổi từ "link" sang "share-2" vì trùng nút Chèn liên kết), mà ghim tên thì mỗi lần đổi là
    // một phép thử đỏ oan. Việc canh icon đừng trùng nhau nằm ở test_nut_chia_se_trinh_sua_dinh.js.
    check("console.js: có icon cho trang", /\n\s*share: "[^"]+",/.test(consoleSrc));
    // System menu membership is exercised in test_settings_tabs.js.
    check("console.js: bộ định tuyến biết trang share",
      /if \(id === "share"\) return renderSharePage\(el\);/.test(consoleSrc));
    check("ui-actions.js khai trang share", /"pet", "share"\]/.test(ui));
    check("ui_targets.py khai trang share", /"pet", "share",/.test(py));
    check("ui_targets.py có tên gọi tiếng Việt để ra lệnh bằng lời",
      /"chia se": "share"/.test(py));
    for (const k of ["page.share.label", "page.share.title", "page.share.sub",
                     "share.heading", "share.warn", "share.empty",
                     "share.search_ph", "share.no_match"]) {
      const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
      check("nhãn " + k + " có ở CẢ hai ngôn ngữ",
        typeof vi[k] === "string" && typeof en[k] === "string");
    }
  }

  console.log(fails.length ? "\nFAIL: " + fails.join(", ") : "\nTat ca OK");
  process.exit(fails.length ? 1 : 0);
})();
