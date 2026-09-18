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

// Chạy hàm với danh sách link giả và fetch giả.
async function chay(items, opts) {
  const goi = [];
  const nutTheoChon = {};
  const el = nut();
  el.querySelectorAll = (sel) => nutTheoChon[sel] || [];
  const fetchGia = async (url, o) => {
    goi.push({ url, body: o && o.body });
    if (url === "/share/list") {
      if (opts && opts.loi) throw new Error("mat mang");
      return { json: async () => ({ ok: true, items }) };
    }
    return { json: async () => ({ ok: true }) };
  };
  await new Function("el", "_renderGen", "ic", "t", "esc", "fetch", "location",
    "navigator", "window", "document",
    "return (async () => {" + than + "})();")(
    el, 1, ic, t, esc, fetchGia, { origin: "https://nas.vi.du" },
    { clipboard: null }, { isSecureContext: false },
    { createElement: () => nut(), body: { appendChild() {} } });
  return { el, goi, nutTheoChon, fetchGia };
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
    const goi = [];
    const el = nut();
    const nutRevoke = [];
    el.querySelectorAll = (sel) => (sel === "[data-share-revoke]" ? nutRevoke : []);
    const fetchGia = async (url, o) => {
      goi.push({ url, body: o && o.body });
      if (url === "/share/list") return { json: async () => ({ ok: true, items: MAU }) };
      return { json: async () => ({ ok: true }) };
    };
    // Bắt nút mà hàm gắn onclick vào: dựng sẵn một nút mang token của link thứ nhất.
    const b = nut(); b.dataset.shareRevoke = "tok1";
    nutRevoke.push(b);
    await new Function("el", "_renderGen", "ic", "t", "esc", "fetch", "location",
      "navigator", "window", "document",
      "return (async () => {" + than + "})();")(
      el, 1, ic, t, esc, fetchGia, { origin: "https://nas.vi.du" },
      { clipboard: null }, { isSecureContext: false },
      { createElement: () => nut(), body: { appendChild() {} } });
    check("hàm có gắn xử lý vào nút Thu hồi", typeof b.onclick === "function");
    if (typeof b.onclick === "function") {
      await b.onclick();
      const rv = goi.find(g => g.url === "/share/revoke");
      check("bấm Thu hồi gọi /share/revoke", !!rv, goi.map(g => g.url).join(", "));
      check("và gửi ĐÚNG token của hàng đó",
        !!rv && JSON.parse(rv.body).token === "tok1", rv && rv.body);
      check("link đã thu hồi biến khỏi danh sách ngay, khỏi phải tải lại trang",
        !el.innerHTML.includes("tok1") && el.innerHTML.includes("tok2"));
    }
  }

  // ---- 5. Trang phải được khai ở ĐỦ các sổ đăng ký, không thì lệnh bằng lời gọi hụt ----
  {
    const ui = fs.readFileSync(path.join(ROOT, "dashboard", "ui-actions.js"), "utf8");
    const py = fs.readFileSync(path.join(ROOT, "server", "ui_targets.py"), "utf8");
    check("console.js: có icon cho trang", /share: "link"/.test(consoleSrc));
    check("console.js: nằm trong nhóm Hệ thống của rail",
      /ids: \["usage", "settings", "pet", "share", "logs", "account"\]/.test(consoleSrc));
    check("console.js: bộ định tuyến biết trang share",
      /if \(id === "share"\) return renderSharePage\(el\);/.test(consoleSrc));
    check("ui-actions.js khai trang share", /"pet", "share"\]/.test(ui));
    check("ui_targets.py khai trang share", /"pet", "share",/.test(py));
    check("ui_targets.py có tên gọi tiếng Việt để ra lệnh bằng lời",
      /"chia se": "share"/.test(py));
    for (const k of ["page.share.label", "page.share.title", "page.share.sub",
                     "share.heading", "share.warn", "share.empty"]) {
      const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
      check("nhãn " + k + " có ở CẢ hai ngôn ngữ",
        typeof vi[k] === "string" && typeof en[k] === "string");
    }
  }

  console.log(fails.length ? "\nFAIL: " + fails.join(", ") : "\nTat ca OK");
  process.exit(fails.length ? 1 : 0);
})();
