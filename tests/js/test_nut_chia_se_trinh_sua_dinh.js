/* Nút Chia sẻ phải có ở CẢ HAI khung mở file, không riêng trình sửa modal (0.59.40).

       node tests/js/test_nut_chia_se_trinh_sua_dinh.js

   Chủ dự án 18/09, ngay sau khi nhận bản 0.59.39: "mở 1 file đây, không thấy nút chia sẻ file
   ở đâu". Đúng: Javis có HAI khung mở file khác hẳn nhau, và bản trước chỉ gắn nút vào một cái.

     - trình sửa modal  (dashboard/file-editor.js, bung giữa màn hình, mở từ link file trong chat)
     - trình sửa ĐỊNH   (dashboard/console.js #noteEditor, mở từ cây vault ở cột trái)

   Cây vault là đường mở file phổ biến nhất, nên bản 0.59.39 trên thực tế là "không có nút".

   Test CHẠY THẬT hai hàm chứ không soi mã nguồn bằng regex: _neCommonBtns của console.js phải
   ĐẺ RA nút Chia sẻ, và shareBtn của file-editor.js phải vẽ thanh link vào ĐÚNG ô được truyền
   vào (hostEl) chứ không cứ nhè thanh của modal mà vẽ - có vậy khung thứ hai mới dùng lại
   được. Lý do phải chạy thật nằm ở test_pet_trang_cai_dat.js: một phép thử regex từng báo xanh
   trong khi trang thật trắng trơn. */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- DOM giả: đủ để dựng nút và nhớ ai được gắn vào đâu ----
function el(tag) {
  const o = {
    tagName: String(tag || "div").toUpperCase(),
    _html: "", type: "", value: "", title: "", className: "", textContent: "",
    hidden: false, disabled: false, readOnly: false, href: "", target: "", rel: "",
    children: [], onclick: null, style: {},
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      contains(c) { return this._s.has(c); },
    },
    setAttribute() {}, addEventListener() {}, select() {},
    appendChild(c) { this.children.push(c); return c; },
    querySelector: () => null, querySelectorAll: () => [],
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = String(v); if (v === "") this.children.length = 0; },
  };
  return o;
}
// Chữ trong nút: innerHTML hoặc textContent, gộp cả con cháu.
function chu(n) {
  let s = String(n._html || "") + String(n.textContent || "") + " " + String(n.title || "");
  (n.children || []).forEach((c) => { s += " " + chu(c); });
  return s;
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

const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const tt = (k) => (typeof vi[k] === "string" ? vi[k] : "!!THIEU:" + k + "!!");
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const ic = (ten) => '<svg data-ic="' + ten + '"></svg>';

// ============================================================
// PHẦN 1 - console.js: _neCommonBtns phải gắn nút Chia sẻ
// ============================================================
const consoleSrc = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const thanCommon = bocHam(consoleSrc, "function _neCommonBtns(actions, rel, it) {");
check("bóc được _neCommonBtns khỏi console.js", !!thanCommon && thanCommon.length > 300,
  thanCommon ? thanCommon.length + " ký tự" : "không thấy");

function chayCommonBtns(coShareBtn) {
  const hopShare = el("div");
  hopShare.hidden = true;
  hopShare.innerHTML = "rác của file trước";
  const goiShare = [];
  const doc = {
    createElement: el,
    getElementById: (id) => (id === "neShare" ? hopShare : (id === "noteEditor" ? el("div") : null)),
  };
  const win = {
    t: tt,
    JavisShareBtn: coShareBtn
      ? (b, p, host, lop) => {
          goiShare.push({ b, p, host, lop });
          const n = el("button");
          n.innerHTML = ic("link");
          n.title = tt("fedit.share_title");
          return n;
        }
      : undefined,
  };
  const actions = el("span");
  const fn = new Function(
    "actions", "rel", "it", "document", "window", "ic", "esc",
    "_neRenameCur", "_neDeleteCur", "_vtRaw", "_dlFile", "_neSyncFull", "closeNote", "X_ICON", "fbrain",
    thanCommon);
  fn(actions, "Javis/AGENTS.md", { name: "AGENTS.md", ext: ".md", type: "file" },
     doc, win, ic, esc,
     () => {}, () => {}, (r) => "/files/raw?path=" + r, () => {}, () => {}, () => {}, "<svg></svg>",
     () => "brain");
  return { actions, hopShare, goiShare };
}

const r1 = chayCommonBtns(true);
const coNut = r1.actions.children.some((n) => /data-ic="link"/.test(chu(n)));
check("thanh nút của trình sửa định CÓ nút Chia sẻ", coNut,
  r1.actions.children.map((n) => chu(n).slice(0, 40)).join(" | "));
check("nút Chia sẻ mang đúng chú giải", r1.actions.children.some(
  (n) => chu(n).indexOf(tt("fedit.share_title")) >= 0));
check("gọi JavisShareBtn đúng 1 lần", r1.goiShare.length === 1, r1.goiShare.length);
check("truyền đúng đường dẫn file đang mở", r1.goiShare[0] && r1.goiShare[0].p === "Javis/AGENTS.md",
  r1.goiShare[0] && r1.goiShare[0].p);
check("truyền ô #neShare làm chỗ vẽ thanh link", r1.goiShare[0] && r1.goiShare[0].host === r1.hopShare);
// Mở file B ngay sau file A: thanh link của A không được dính lại.
check("dọn thanh link của file mở trước", r1.hopShare.innerHTML === "" && r1.hopShare.hidden === true,
  JSON.stringify(r1.hopShare.innerHTML) + " hidden=" + r1.hopShare.hidden);

// Bản cũ (chưa nạp file-editor.js, hoặc bản 0.59.39 chưa có hàm) không được nổ - các nút còn lại vẫn phải dựng.
const r0 = chayCommonBtns(false);
check("thiếu JavisShareBtn thì bỏ qua êm, không vỡ thanh nút", r0.actions.children.length >= 6,
  r0.actions.children.length + " nút");

// ============================================================
// PHẦN 2 - file-editor.js: shareBtn vẽ vào ĐÚNG ô được truyền vào
// ============================================================
const feSrc = fs.readFileSync(path.join(ROOT, "dashboard", "file-editor.js"), "utf8");
const thanShare = bocHam(feSrc, "function shareBtn(b, ceil, hostEl, lop) {");
check("shareBtn nhận được hostEl (ô vẽ thanh link) và lop", !!thanShare,
  thanShare ? "ok" : "chữ ký vẫn là shareBtn(b, ceil) - khung thứ hai không dùng lại được");

check("file-editor.js xuất window.JavisShareBtn", /window\.JavisShareBtn\s*=\s*shareBtn/.test(feSrc));

async function chayShareBtn() {
  // Chữ ký cũ (không có hostEl) thì bóc ra là null: báo FAIL ở trên rồi, đừng nổ thêm một
  // vệt stack che mất danh sách kết quả.
  if (!thanShare) return;
  const host = el("div");
  host.hidden = true;
  const goi = [];
  const fetchGia = async (url, o) => {
    goi.push({ url, body: o && o.body });
    if (url.indexOf("/share/of") === 0) return { json: async () => ({ ok: true, share: null }) };
    if (url === "/share/create") return { json: async () => ({ ok: true, token: "abc123", path: "/s/abc123" }) };
    return { json: async () => ({ ok: true }) };
  };
  const win = { isSecureContext: false, location: { origin: "https://javis.test" } };
  const fn = new Function(
    "b", "ceil", "hostEl", "lop",
    "document", "window", "fetch", "location", "navigator", "setTimeout",
    "ic", "esc", "tw", "injectCss", "elShareModal",
    thanShare + "\nreturn btn;");
  const btn = fn("brain", "Javis/AGENTS.md", host, "",
    { createElement: el }, win, fetchGia, win.location, {}, () => {},
    ic, esc, tt, () => {}, null);
  await new Promise((r) => setTimeout(r, 0));
  check("nút hỏi /share/of ngay khi mở file", goi.some((g) => g.url.indexOf("/share/of") === 0),
    goi.map((g) => g.url).join(", "));
  btn.onclick();
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
  check("bấm nút thì gọi /share/create", goi.some((g) => g.url === "/share/create"),
    goi.map((g) => g.url).join(", "));
  check("thanh link hiện ra ở ô ĐƯỢC TRUYỀN VÀO, không phải thanh của modal", host.hidden === false,
    "hidden=" + host.hidden);
  const noiDung = host.children.map(chu).join(" ") + " " +
    host.children.map((h) => (h.children || []).map((c) => String(c.value || "")).join(" ")).join(" ");
  check("thanh link chứa đường link đầy đủ", noiDung.indexOf("https://javis.test/s/abc123") >= 0,
    noiDung.slice(0, 160));
  check("thanh link có nút Thu hồi", noiDung.indexOf(tt("fedit.share_revoke")) >= 0, noiDung.slice(0, 160));
}

// ============================================================
// PHẦN 3 - khung HTML phải có sẵn ô #neShare, nếu không nút bấm xong không thấy gì
// ============================================================
const html = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");
check('index.html có ô id="neShare" trong #noteEditor', /id="neShare"/.test(html));
check("ô #neShare mặc định ẩn", /id="neShare"[^>]*hidden/.test(html));
check("ô #neShare dùng chung lớp .jvfe-share (để có CSS)", /id="neShare"[^>]*class="[^"]*jvfe-share|class="[^"]*jvfe-share[^"]*"[^>]*id="neShare"/.test(html));
const css = fs.readFileSync(path.join(ROOT, "dashboard", "style.css"), "utf8");
check(".ne-share không co giãn (không ăn mất chiều cao thân bài)", /\.ne-share\s*\{[^}]*flex:\s*none/.test(css));

chayShareBtn().then(() => {
  console.log("");
  if (fails.length) { console.log("FAILED: " + fails.length); process.exit(1); }
  console.log("Tất cả đều xanh.");
});
