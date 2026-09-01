/* Tab "Thư mục" trong cột trái khung chat phải MƯỢN cây Vault có sẵn, không dựng cây thứ hai.

       node tests/js/test_tab_thu_muc.js

   Bản đầu của tính năng này viết hẳn một module cây riêng (dashboard/file-tree.js). Chủ repo
   chỉ ra ngay: "sao cái phần thư mục em không bê nguyên cái cây y hệt bên Javis sang mà phải
   dựng lại phức tạp thế, lại còn lỗi nữa chứ".

   Đúng. Javis đã có cây Vault ở cột trái màn chính, kèm tìm theo tên và theo nội dung, tạo
   file, tạo thư mục, làm mới, tô sáng file đang mở. Dựng bản thứ hai là chép lại từng đó thứ
   rồi để hai bản trôi lệch nhau - và bản mới thì chưa ai dùng thật nên lỗi nằm im ở đó.

   Nay tab Thư mục mượn ĐÚNG node đó, y như cách trang Trò chuyện vẫn mượn #chatArea. Node chỉ
   có MỘT, nên hai luật dưới đây là sống còn:
     - bấm sang tab Hội thoại  -> trả về, nếu không màn chính mất hẳn panel Vault;
     - rời trang Trò chuyện    -> cũng phải trả về.
   Quên một trong hai là panel biến mất và người dùng tưởng app hỏng. Đó là thứ file này canh. */
const fs = require("fs");
const path = require("path");
const vm = require("node:vm");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Không còn cây thứ hai trong mã nguồn
// ============================================================
check("module cây tự dựng đã bị gỡ",
  !fs.existsSync(path.join(ROOT, "dashboard", "file-tree.js")));
const HTML = D("index.html");
check("trang không còn nạp module đó", HTML.indexOf("file-tree.js") === -1);
const SESS = D("sessions-ui.js");
check("cột trái không còn gọi module đó", SESS.indexOf("JavisFileTree") === -1);
const CSS = D("style.css");
check("CSS của module đó cũng dọn theo", CSS.indexOf("ftree") === -1);

// ============================================================
// 2. Cây Vault cho mượn, và trả lại đúng chỗ cũ
// ============================================================
const CON = D("console.js");
check("có đường cho mượn panel Vault", /window\.JavisVaultPanel\s*=\s*\{[^}]*borrow/.test(CON));
// Nhớ chỗ cũ bằng parentNode + nextSibling: trả về cuối danh sách là panel Vault nhảy xuống
// dưới cột trái, khác hẳn chỗ nó vốn đứng.
check("mượn thì nhớ đúng chỗ cũ để trả",
  /_vaultSlot = \{ node: n, parent: n\.parentNode, next: n\.nextSibling \}/.test(CON));
check("CANARY: rời trang Trò chuyện thì trả panel Vault về",
  /function _returnChatNodes\(\)[\s\S]{0,700}_returnVaultPanel\(\)/.test(CON));

// ============================================================
// 2b. Mở file từ tab Thư mục: trình sửa CHIẾM CHỖ khung chat
// ============================================================
// Ở màn chính trình sửa là lớp nổi đè lên visual não - chỗ đó rỗng nên đè là hợp lý. Ở trang
// Trò chuyện thì bên dưới là khung chat đang có nội dung, đè lên vừa chật vừa rối. Yêu cầu:
// mở file thì khung chat biến mất hẳn, chỉ còn trình sửa.
check("có chỗ đứng riêng cho trình sửa trong trang Trò chuyện", /id="chatPageEdit"/.test(CON));
check("mở file khi đang ở trang Trò chuyện thì trình sửa dọn sang đó",
  /document\.body\.classList\.contains\("on-chat"\)\) _borrowNoteEditor\(\)/.test(CON));
check("CANARY: đóng trình sửa thì trả chỗ lại cho khung chat",
  /function closeNote\(\)[\s\S]{0,400}_returnNoteEditor\(\)/.test(CON));
// Rời trang mà không trả thì node trình sửa bị xoá theo khung, và mở file ở màn chính sau đó
// sẽ trắng trơn - hỏng ở MỘT NƠI KHÁC hẳn nơi gây ra, kiểu khó lần nhất.
check("CANARY: rời trang Trò chuyện cũng trả trình sửa về",
  /function _returnChatNodes\(\)[\s\S]{0,700}_returnNoteEditor\(\)/.test(CON));
check("trình sửa mượn chính #noteEditor, không dựng bản thứ hai",
  /_borrowNoteEditor[\s\S]{0,300}getElementById\("noteEditor"\)/.test(CON));
check("nhớ đúng chỗ cũ của trình sửa để trả",
  /_neSlot = \{ node: ed, parent: ed\.parentNode, next: ed\.nextSibling \}/.test(CON));
check("khung chat bị ẩn khi trình sửa đang chiếm chỗ",
  /\.chatpage-main\.edit-on > \.chatpage-slot\{ display:none/.test(CON));
// Ẩn bằng display:none chứ không xoá: đóng trình sửa ra phải còn nguyên đoạn chat đang dở.
check("CANARY: khung chat chỉ bị ẩn chứ không bị dựng lại",
  !/edit-on[\s\S]{0,200}innerHTML\s*=\s*""/.test(CON));
// Nút phóng to trình sửa (.ne-full) phải còn tác dụng: hai selector cùng độ ưu tiên, khối CSS
// của trang chat nạp sau nên sẽ THẮNG và vô hiệu hoá nút đó nếu quên :not().
check("CANARY: không vô hiệu hoá nút phóng to trình sửa",
  /\.chatpage-edit > \.note-editor:not\(\.ne-full\)/.test(CON));

// ============================================================
// 3. Nút "Vị trí" ở kết quả tìm kiếm
// ============================================================
check("kết quả tìm kiếm có nút Vị trí", /class="vr-loc"/.test(CON));
// stopPropagation là bắt buộc: thiếu nó thì bấm Vị trí cũng kích luôn onclick của cả dòng và
// note bị mở ra - đúng thứ người dùng KHÔNG muốn khi họ chỉ hỏi "file này nằm đâu".
check("CANARY: bấm Vị trí không mở luôn note",
  /vr-loc"\)\.onclick = \(e\) => \{ e\.stopPropagation\(\); _vtRevealInTree/.test(CON));
check("Vị trí xổ cây bằng cơ chế sẵn có, không đẻ cơ chế thứ hai",
  /_vtRevealInTree[\s\S]{0,900}await _vtRebuildReExpand\(dir\)/.test(CON));
check("và tô sáng đúng file đó", /_vtRevealInTree[\s\S]{0,1000}_vtMarkActive\(p\)/.test(CON));
check("xổ xong thì tắt khung kết quả để thấy cây",
  /_vtRevealInTree[\s\S]{0,600}results\.hidden = true/.test(CON));
check("có style cho nút Vị trí", /\.vr-loc \{/.test(CSS));
check("panel Vault được gỡ bề rộng cột khi nằm trong cột chat",
  /\.cside-pane > \.hud-left \{[^}]*width: auto/.test(CSS));

// ============================================================
// 4. Chạy THẬT hàm đổi tab: mượn khi sang Thư mục, trả khi về Hội thoại
// ============================================================
// Bộ phân tích HTML tí hon - cần thật, không né được: module gán innerHTML bằng CHUỖI rồi mới
// querySelector ra node con. Mock nào giữ nguyên chuỗi thì querySelector trả null và test chết
// ngay ở mount, tức là không đo được gì.
function parseHtml(html, tao) {
  const goc = [], ngan = [goc];
  const re = /<(\/?)([a-zA-Z][\w-]*)((?:\s+[\w-]+(?:="[^"]*")?)*)\s*(\/?)>|([^<]+)/g;
  let m;
  while ((m = re.exec(html))) {
    if (m[5] != null) {
      const owner = ngan[ngan.length - 1].owner;
      if (owner) owner._text = (owner._text || "") + m[5];
      continue;
    }
    if (m[1]) { if (ngan.length > 1) ngan.pop(); continue; }
    const el = tao(m[2]);
    const attrs = m[3] || "";
    const cls = /class="([^"]*)"/.exec(attrs);
    if (cls) el.className = cls[1];
    let a; const re2 = /data-([\w-]+)="([^"]*)"/g;
    while ((a = re2.exec(attrs))) el.dataset[a[1]] = a[2];
    ngan[ngan.length - 1].push(el);
    const tuDong = m[4] === "/" || /^(input|img|br|hr)$/i.test(m[2]);
    if (!tuDong) { const k = []; k.owner = el; ngan.push(k); el._parsedKids = k; }
  }
  (function gan(ds) {
    ds.forEach((n) => { if (n._parsedKids) { n._kids = n._parsedKids; gan(n._parsedKids); } });
  })(goc);
  return goc;
}

function fakeEl(tag) {
  const el = {
    tagName: String(tag || "div").toUpperCase(),
    _kids: [], _text: "", style: {}, dataset: {}, _cls: [], value: "",
    classList: {
      add: (c) => { if (el._cls.indexOf(c) < 0) el._cls.push(c); },
      remove: (c) => { el._cls = el._cls.filter((x) => x !== c); },
      toggle: (c, on) => { on ? el.classList.add(c) : el.classList.remove(c); },
      contains: (c) => el._cls.indexOf(c) >= 0,
    },
    get className() { return el._cls.join(" "); },
    set className(v) { el._cls = String(v || "").split(/\s+/).filter(Boolean); },
    get innerHTML() { return el._kids.map((k) => k.outerHTML).join(""); },
    set innerHTML(v) { el._text = ""; el._kids = parseHtml(String(v || ""), fakeEl); },
    get outerHTML() { return "<" + el.tagName + ">" + el.innerHTML + "</" + el.tagName + ">"; },
    get firstChild() { return el._kids[0] || null; },
    appendChild(c) { el._kids.push(c); return c; },
    _all() { return el._kids.reduce((a, k) => a.concat([k], k._all ? k._all() : []), []); },
    querySelector(sel) { return el.querySelectorAll(sel)[0] || null; },
    querySelectorAll(sel) {
      const attr = /^\[([\w-]+)="([^"]*)"\]$/.exec(sel.trim());
      if (attr) {
        const key = attr[1].replace(/^data-/, "");
        return el._all().filter((k) => k.dataset[key] === attr[2]);
      }
      const cls = sel.replace(/^\./, "").split(".");
      return el._all().filter((k) => cls.every((c) => k._cls.indexOf(c) >= 0));
    },
    addEventListener() {}, focus() {},
  };
  return el;
}

const luuTru = {};
const goi = [];
const sandbox = {
  console, setTimeout, clearTimeout,
  ic: () => "<svg></svg>",
  localStorage: {
    getItem: (k) => (k in luuTru ? luuTru[k] : null),
    setItem: (k, v) => { luuTru[k] = String(v); },
  },
  document: {
    readyState: "complete",
    createElement: fakeEl,
    getElementById: () => null,
    querySelector: () => null,
    // Chip project (sessions-ui.js renderProjChip) tìm chỗ đứng của nó bằng hàm này. Thiếu
    // nó thì module ném lỗi trong một microtask SAU khi test đã in "pass", và node chết -
    // trông như test hỏng ngẫu nhiên chứ không chỉ ra được gì.
    querySelectorAll: () => [],
    addEventListener() {},
    body: fakeEl("body"),
  },
  fetch: async () => ({ json: async () => ({ sessions: [] }) }),
  window: {
    innerWidth: 1400,
    ic: () => "<svg></svg>",
    addEventListener() {},
    JavisSessions: { brain: () => "My Bullet Journal", current: () => null },
    JavisVaultPanel: {
      borrow: (into) => { goi.push("borrow"); sandbox.window._into = into; return true; },
      giveBack: () => { goi.push("giveBack"); },
    },
  },
};
sandbox.window.window = sandbox.window;
sandbox.window.document = sandbox.document;
sandbox.window.localStorage = sandbox.localStorage;
vm.createContext(sandbox);
vm.runInContext(SESS, sandbox);

check("module phơi được hàm đổi tab", typeof sandbox.window.JavisChatSide.tab === "function");

const cot = fakeEl("aside");
sandbox.window.JavisChatSide.mount(cot);

check("cột trái có đủ hai tab", cot.querySelectorAll("cside-tab").length === 2);
check("mặc định đứng ở tab Hội thoại",
  cot.querySelectorAll('[data-pane="chat"]')[0]._cls.indexOf("on") >= 0);
// Chưa bấm sang thì KHÔNG được mượn: mượn sớm là màn chính mất panel dù người dùng chưa cần.
check("CANARY: chưa bấm sang thì chưa mượn panel", goi.indexOf("borrow") < 0);

sandbox.window.JavisChatSide.tab("files");
check("bấm sang Thư mục thì mượn panel Vault", goi[goi.length - 1] === "borrow");
check("mượn vào đúng khung của tab đó",
  sandbox.window._into === cot.querySelectorAll('[data-pane="files"]')[0]);
check("khung Thư mục được bật, khung Hội thoại tắt",
  cot.querySelectorAll('[data-pane="files"]')[0]._cls.indexOf("on") >= 0
  && cot.querySelectorAll('[data-pane="chat"]')[0]._cls.indexOf("on") < 0);

sandbox.window.JavisChatSide.tab("chat");
check("CANARY: quay về Hội thoại thì TRẢ panel Vault", goi[goi.length - 1] === "giveBack");

// Nhớ lựa chọn: dựng lại cột (đổi trang rồi quay lại) phải về đúng tab cũ.
sandbox.window.JavisChatSide.tab("files");
const cot2 = fakeEl("aside");
sandbox.window.JavisChatSide.mount(cot2);
check("dựng lại cột thì về đúng tab đang dùng",
  cot2.querySelectorAll('[data-pane="files"]')[0]._cls.indexOf("on") >= 0);

console.log("");
if (fails.length) {
  console.log("THẤT BẠI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_tab_thu_muc: tất cả pass");
