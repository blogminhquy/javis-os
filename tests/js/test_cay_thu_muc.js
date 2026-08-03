/* Cây thư mục trong cột trái khung chat + nút "Vị trí" xổ tới đúng chỗ file đang nằm.

       node tests/js/test_cay_thu_muc.js

   Yêu cầu thật của chủ repo: "ở trong khung lịch sử hội thoại để trò chuyện anh muốn có thêm
   tab để chuyển qua thư mục và lịch sử thoại, cây thư mục giống quản lý thư mục ở Vault. Và
   khung tìm kiếm trong quản lý thư mục thì khi tìm thấy file anh muốn có nút để ấn vào sẽ
   hiển thị luôn khung thư mục đang lưu trữ nó, sổ ra toàn thư mục đang lưu ở đâu."

   Chỗ dễ sai nhất KHÔNG phải phần vẽ, mà là ĐƯỜNG DẪN CÓ HAI HỆ:
     rootRel  - tương đối trần duyệt (thứ /files/list và /files/search nói)
     brainRel - tương đối gốc brain (thứ JavisEditFile nhận)
   Lẫn hai hệ thì cây vẫn vẽ đẹp, bấm vào vẫn có phản ứng, chỉ là mở nhầm file hoặc không mở
   được - loại lỗi nhìn code thấy "có xử lý rồi" nên rất khó ngờ. Nên phần lớn bài ở đây bắn
   thẳng vào hai hàm quy đổi, và bài cuối chạy cả cây thật trên DOM giả với fetch giả.  */
const fs = require("fs");
const path = require("path");
const vm = require("node:vm");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Quy đổi đường dẫn - chạy hàm THẬT lấy từ module (Node mode)
// ============================================================
const T = require(path.join(ROOT, "dashboard", "file-tree.js"));

const HOME = "brains/My Bullet Journal";
check("rootRel -> brainRel: cắt đúng tiền tố brain",
  T.toBrainRel(HOME + "/06 - Sources/ghi-chu.md", HOME) === "06 - Sources/ghi-chu.md");
check("file nằm ngay gốc brain", T.toBrainRel(HOME + "/README.md", HOME) === "README.md");
// Ngoài brain phải trả rỗng chứ KHÔNG trả bừa: cây này chỉ mở file trong brain, trả bừa là
// trình sửa mở nhầm sang thư mục khác trên ổ đĩa.
check("file ngoài brain -> rỗng, không đoán bừa",
  T.toBrainRel("brains/Brain Default/x.md", HOME) === "");
check("brain trùng tên làm tiền tố phải khớp CẢ dấu gạch chéo",
  T.toBrainRel("brains/My Bullet Journal 2/x.md", HOME) === "");
check("dấu gạch ngược của Windows vẫn hiểu",
  T.toBrainRel(HOME.replace(/\//g, "\\") + "\\a\\b.md", HOME) === "a/b.md");

// ============================================================
// 2. Danh sách thư mục cha cần xổ - trái tim của nút "Vị trí"
// ============================================================
const anc = T.ancestorsOf(HOME + "/06 - Sources/2026/ghi-chu.md", HOME);
check("xổ đủ mọi tầng cha, từ gốc brain đi xuống",
  JSON.stringify(anc) === JSON.stringify([HOME, HOME + "/06 - Sources", HOME + "/06 - Sources/2026"]));
check("file ngay gốc brain thì chỉ cần mở gốc",
  JSON.stringify(T.ancestorsOf(HOME + "/x.md", HOME)) === JSON.stringify([HOME]));
check("file ngoài brain: không xổ gì cả",
  T.ancestorsOf("brains/Khac/x.md", HOME).length === 0);
// Đường dẫn sâu: thiếu MỘT tầng là nhánh không mở tới nơi và nút Vị trí thành vô dụng.
check("đường dẫn sâu vẫn đủ tầng",
  T.ancestorsOf(HOME + "/a/b/c/d/e.md", HOME).length === 5);

// ============================================================
// 3. Cột trái phải có HAI tab và nhớ tab đã chọn
// ============================================================
const SESS = D("sessions-ui.js");
check("có tab Hội thoại", SESS.indexOf('data-tab="chat"') !== -1);
check("có tab Thư mục", SESS.indexOf('data-tab="files"') !== -1);
check("có khung riêng cho cây", SESS.indexOf('data-pane="files"') !== -1);
check("nhớ tab đã chọn qua localStorage", /localStorage\.setItem\(TAB_KEY/.test(SESS));
check("CANARY: đổi brain thì dựng lại cây (không treo cây brain cũ)",
  /cayCtl\.reload\(\)/.test(SESS));
// Mount LƯỜI: đa số lượt mở chat là để chat, không phải duyệt file.
check("cây chỉ mount khi thật sự bấm sang tab đó",
  /tabHienTai === "files"[\s\S]{0,200}JavisFileTree\.mount/.test(SESS));

const CSS = D("style.css");
check("pane không hoạt động bị ẩn hẳn", /\.cside-pane \{[^}]*display: none/.test(CSS));
check("có style cho node vừa được chỉ vị trí", /\.ftree-row\.hit/.test(CSS));

// ============================================================
// 4. Chạy CẢ CÂY trên DOM giả: bấm Vị trí phải xổ tới đúng nhánh
// ============================================================
// Ở đây mới lộ ra thứ mà đọc code không thấy: thứ tự nạp con, node nào được tô sáng, và
// cây có thật sự chứa file đó sau khi xổ hay không.
const KHO = {
  // path (rootRel) -> danh sách con
  [HOME]: [
    { name: "06 - Sources", type: "dir" },
    { name: "Memory", type: "dir" },
    { name: "README.md", type: "file", ext: ".md" },
  ],
  [HOME + "/06 - Sources"]: [
    { name: "2026", type: "dir" },
    { name: "cu.md", type: "file", ext: ".md" },
  ],
  [HOME + "/06 - Sources/2026"]: [
    { name: "ghi-chu.md", type: "file", ext: ".md" },
  ],
  [HOME + "/Memory"]: [{ name: "MEMORY.md", type: "file", ext: ".md" }],
};

/* Bộ phân tích HTML tí hon. Cần thật, không né được: module gán `innerHTML` bằng CHUỖI rồi
   mới querySelector ra các node con. Mock nào chỉ giữ nguyên chuỗi thì querySelector trả null
   và test chết ngay ở mount - tức là không đo được gì. Chỉ cần đủ cho thẻ mở/đóng và thẻ tự
   đóng có class, đúng những gì file-tree.js dựng. */
function parseHtml(html, tao) {
  const goc = [], ngan = [goc];
  const re = /<(\/?)([a-zA-Z][\w-]*)((?:\s+[\w-]+(?:="[^"]*")?)*)\s*(\/?)>|([^<]+)/g;
  let m;
  while ((m = re.exec(html))) {
    if (m[5] != null) {                       // chữ thường -> vào node đang mở
      const owner = ngan[ngan.length - 1].owner;
      if (owner) owner._text = (owner._text || "") + m[5];
      continue;
    }
    if (m[1]) { if (ngan.length > 1) ngan.pop(); continue; }   // thẻ đóng
    const el = tao(m[2]);
    const cls = /class="([^"]*)"/.exec(m[3] || "");
    if (cls) el.className = cls[1];
    ngan[ngan.length - 1].push(el);
    const tuDong = m[4] === "/" || /^(input|img|br|hr)$/i.test(m[2]);
    if (!tuDong) { const k = []; k.owner = el; k.parentEl = el; ngan.push(k); el._parsedKids = k; }
  }
  // Gắn con đã phân tích vào từng node.
  (function gan(ds) {
    ds.forEach((n) => { if (n._parsedKids) { n._kids = n._parsedKids; gan(n._parsedKids); } });
  })(goc);
  return goc;
}

function fakeEl(tag) {
  const el = {
    tagName: String(tag || "div").toUpperCase(),
    _kids: [], _html: "", _text: "", style: {}, dataset: {}, _cls: [],
    classList: {
      add: (c) => { if (el._cls.indexOf(c) < 0) el._cls.push(c); },
      remove: (c) => { el._cls = el._cls.filter((x) => x !== c); },
      toggle: (c, on) => { on ? el.classList.add(c) : el.classList.remove(c); },
      contains: (c) => el._cls.indexOf(c) >= 0,
    },
    get className() { return el._cls.join(" "); },
    set className(v) { el._cls = String(v || "").split(/\s+/).filter(Boolean); },
    get innerHTML() { return el._html + el._kids.map((k) => k.outerHTML).join(""); },
    set innerHTML(v) {
      el._html = ""; el._text = "";
      el._kids = parseHtml(String(v || ""), fakeEl);
    },
    get outerHTML() { return "<" + el.tagName + ">" + el.innerHTML + "</" + el.tagName + ">"; },
    get textContent() {
      return (el._text || "") + el._kids.map((k) => k.textContent).join("");
    },
    appendChild(c) { el._kids.push(c); return c; },
    _all() { return el._kids.reduce((a, k) => a.concat([k], k._all ? k._all() : []), []); },
    querySelector(sel) { return el.querySelectorAll(sel)[0] || null; },
    querySelectorAll(sel) {
      const cls = sel.replace(/^\./, "").split(".");
      return el._all().filter((k) => cls.every((c) => k._cls.indexOf(c) >= 0));
    },
    scrollIntoView() {},
  };
  return el;
}

const sandbox = {
  console,
  module: { exports: {} },
  setTimeout, clearTimeout,
  document: { createElement: fakeEl },
  window: {
    ic: () => "<svg></svg>",
    JavisEditFile: (p) => { sandbox.window._daMo = p; },
  },
  fetch: async (u) => {
    const url = String(u);
    if (url.indexOf("/files/list") === 0) {
      const m = url.match(/[?&]path=([^&]*)/);
      const p = m ? decodeURIComponent(m[1]) : null;
      const key = p === null ? HOME : p;
      return {
        json: async () => ({
          root: "brains", home: HOME, path: key, parent: "brains",
          items: KHO[key] || [],
        }),
      };
    }
    if (url.indexOf("/files/search") === 0) {
      return { json: async () => ({ items: [
        { name: "ghi-chu.md", path: HOME + "/06 - Sources/2026/ghi-chu.md", ext: ".md" },
      ] }) };
    }
    throw new Error("URL lạ: " + url);
  },
};
sandbox.window.window = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(D("file-tree.js"), sandbox);

check("module tự gắn vào window", typeof sandbox.window.JavisFileTree === "object");

(async () => {
  const box = fakeEl("div");
  const ctl = sandbox.window.JavisFileTree.mount(box, { brain: () => "My Bullet Journal" });
  check("mount trả về bộ điều khiển có reveal", ctl && typeof ctl.reveal === "function");
  await new Promise((r) => setTimeout(r, 10));

  const ten = () => box.querySelectorAll("ftree-name").map((n) => n.textContent);
  check("cây vẽ được tầng đầu", ten().indexOf("06 - Sources") >= 0);
  // Chưa xổ thì KHÔNG được vẽ sẵn con: nạp lười là lý do brain vài nghìn file vẫn mở tức thì.
  check("CANARY: chưa xổ thì chưa nạp con", ten().indexOf("ghi-chu.md") < 0);

  await ctl.reveal(HOME + "/06 - Sources/2026/ghi-chu.md");
  const sau = ten();
  check("Vị trí: xổ tới file cần tìm", sau.indexOf("ghi-chu.md") >= 0);
  check("Vị trí: xổ cả các thư mục cha trên đường đi",
    sau.indexOf("06 - Sources") >= 0 && sau.indexOf("2026") >= 0);
  // Nhánh KHÔNG nằm trên đường đi phải giữ nguyên trạng thái đóng, nếu không thì "xổ tới nơi"
  // thành "xổ tung cả cây" và người dùng vẫn phải đi dò.
  check("CANARY: nhánh không liên quan vẫn đóng", sau.indexOf("MEMORY.md") < 0);

  // Thu lại một nhánh ĐÃ nạp con thì con phải biến mất khỏi màn. Bài này canh chuyện khác với
  // "chưa xổ thì chưa nạp": ở đó con chưa có nên không vẽ gì là đương nhiên, còn ở đây con nằm
  // sẵn trong bộ nhớ đệm, chỉ cần vẽ theo trạng thái đóng/mở. Sai ở đây là bấm thu lại không
  // có tác dụng gì cả.
  const rowDir = box.querySelectorAll("ftree-row")
    .filter((r) => r.dataset.path === HOME + "/06 - Sources")[0];
  rowDir.onclick();
  await new Promise((r) => setTimeout(r, 5));
  check("CANARY: thu nhánh lại thì con biến mất dù đã nạp",
    ten().indexOf("ghi-chu.md") < 0 && ten().indexOf("cu.md") < 0);
  rowDir.onclick();
  await new Promise((r) => setTimeout(r, 5));
  check("xổ lại thì con hiện lại, không phải gọi mạng lần nữa",
    ten().indexOf("cu.md") >= 0);
  await ctl.reveal(HOME + "/06 - Sources/2026/ghi-chu.md");

  const hit = box.querySelectorAll("ftree-row").filter((r) => r._cls.indexOf("hit") >= 0);
  check("đúng MỘT node được tô sáng", hit.length === 1);
  check("và đó là đúng file vừa chỉ vị trí",
    hit[0] && hit[0].dataset.path === HOME + "/06 - Sources/2026/ghi-chu.md");

  // Bấm vào file phải mở bằng đường dẫn theo GỐC BRAIN, không phải theo trần.
  const rowFile = box.querySelectorAll("ftree-row")
    .filter((r) => r.dataset.path === HOME + "/06 - Sources/2026/ghi-chu.md")[0];
  rowFile.onclick();
  check("CANARY: mở file bằng đường dẫn theo gốc brain",
    sandbox.window._daMo === "06 - Sources/2026/ghi-chu.md");

  console.log("");
  if (fails.length) {
    console.log("THẤT BẠI " + fails.length + ": " + fails.join(", "));
    process.exit(1);
  }
  console.log("OK - test_cay_thu_muc: tất cả pass");
})();
