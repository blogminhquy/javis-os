/* Hộp chọn thư mục (JavisFolderPicker): NẠP THẬT module rồi GỌI THẬT open().
 *
 *     node tests/js/test_hop_chon_thu_muc.js
 *
 * Vì sao có file này: chủ dự án dùng thử 0.63.2 và chỉ ra "thêm thư mục nên MỞ RA CHỌN thư mục
 * chứ không phải điền đường dẫn". Một test quét chuỗi chỉ chứng minh trong mã CÓ chữ
 * JavisFolderPicker; nó không chứng minh bấm vào một thư mục thì đi vào được thư mục đó, hay
 * chọn xong thì đường dẫn giao ra đúng. Nên file này chạy thật cái hộp.
 *
 * Không có jsdom trong repo. Bản DOM giả dưới đây KHÔNG parse HTML: nó ghi nhớ chuỗi vừa gán
 * vào innerHTML, và querySelector trả về một thẻ stub cho mỗi bộ chọn. Bấy nhiêu là đủ, vì
 * hộp này tìm các thẻ của nó theo bộ chọn cố định, còn phần đáng kiểm là LUỒNG: gọi /browse
 * với tham số nào, dựng bao nhiêu hàng, bấm hàng thì đi đâu, bấm Dùng thì giao ra gì.
 *
 * Kiểu test: xem ghi chú dài ở test_go_ket_noi_hoi_lai.js. */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, them) {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
}

// ---- DOM giả ----------------------------------------------------------------------------
function theMoi(ten) {
  const el = {
    tagName: ten, id: "", className: "", disabled: false, value: "", textContent: "",
    parentNode: null, con: [], _sel: {},
    onclick: null, onkeydown: null,
    _html: "",
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = String(v); if (v === "") this.con = []; },
    appendChild(c) { this.con.push(c); c.parentNode = this; return c; },
    removeChild(c) { this.con = this.con.filter((x) => x !== c); c.parentNode = null; },
    querySelector(sel) { return (this._sel[sel] = this._sel[sel] || theMoi("div")); },
    querySelectorAll() { return []; },
    addEventListener(loai, fn) { this["on" + loai] = fn; },
    classList: { _t: new Set(), add(c) { this._t.add(c); }, remove(c) { this._t.delete(c); },
                 toggle(c, tren) { if (tren) this._t.add(c); else this._t.delete(c); },
                 contains(c) { return this._t.has(c); } },
    style: {}, focus() {}, getBoundingClientRect: () => ({ left: 0, top: 0 }),
    setAttribute() {}, getAttribute: () => null,
  };
  return el;
}

function moiTruong(traLoi) {
  const body = theMoi("body");
  const goiBrowse = [];
  global.document = {
    body,
    activeElement: null,
    createElement: (t) => theMoi(t),
    getElementById: () => null,
    addEventListener() {},
  };
  global.fetch = async (url) => {
    goiBrowse.push(url);
    return { json: async () => traLoi(url) };
  };
  global.window = {
    t: (k) => k,
    ic: (n) => "<svg data-ic=\"" + n + "\"></svg>",
    innerWidth: 1200,
  };
  return { body, goiBrowse };
}

const NHA = { path: "/home/me", parent: "/home", here_md: null, git: false, dirs: [
    { name: "du-an", path: "/home/me/du-an", md: null, git: true },
    { name: "tai-lieu", path: "/home/me/tai-lieu", md: null, git: false },
  ] };
const CAY = {
  // Server coi path rỗng là thư mục nhà, nên hai khoá này trỏ cùng một chỗ.
  "/home/me": NHA,
  "": { path: "/home/me", parent: "/home", here_md: null, git: false, dirs: [
    { name: "du-an", path: "/home/me/du-an", md: null, git: true },
    { name: "tai-lieu", path: "/home/me/tai-lieu", md: null, git: false },
  ] },
  "/home/me/du-an": { path: "/home/me/du-an", parent: "/home/me", here_md: null, git: true, dirs: [
    { name: "server", path: "/home/me/du-an/server", md: null, git: false },
  ] },
};
const DIEM = [
  { ten: "My Bullet Journal", duong_dan: "/home/me/brains/My Bullet Journal", ghi_chu: "brain", git: false },
  { ten: "brains", duong_dan: "/home/me/brains", ghi_chu: "brains", git: false },
  { ten: "~", duong_dan: "/home/me", ghi_chu: "home", git: false },
];
const traLoi = (url) => {
  if (url.indexOf("/browse/starts") === 0) return { diem: DIEM };
  const m = /[?&]path=([^&]*)/.exec(url);
  const p = decodeURIComponent(m ? m[1] : "");
  return CAY[p] || { error: "Không phải thư mục", path: p, parent: null, dirs: [] };
};
// Bản server KHÔNG có endpoint điểm xuất phát (bản cũ chưa cập nhật): phải suy biến êm.
const traLoiCu = (url) => {
  if (url.indexOf("/browse/starts") === 0) return { diem: [] };
  return traLoi(url);
};

const cho = () => new Promise((r) => setImmediate(r));
const nap = () => {
  delete require.cache[require.resolve(path.join(ROOT, "dashboard", "folder-picker.js"))];
  return require(path.join(ROOT, "dashboard", "folder-picker.js"));
};

(async function () {
  // ---- 1. Mở hộp: gọi /browse, dựng hàng cho từng thư mục con ----
  {
    const mt = moiTruong(traLoi);
    const FP = nap();
    let giaoRa = null;
    FP.open({ demMd: false, chon: async (p) => { giaoRa = p; return ""; } });
    await cho(); await cho();

    const lop = mt.body.con[0];
    check("hộp được gắn vào body", !!lop && lop.id === "fpModal");
    // Mở ra là màn ĐIỂM XUẤT PHÁT, không đổ thẳng vào thư mục nhà: trên VPS thư mục nhà chỉ
    // có file ẩn nên hộp hiện ra trống trơn, người dùng lại phải gõ tay đường dẫn.
    check("mở hộp thì hỏi điểm xuất phát, chưa duyệt thư mục nào",
      mt.goiBrowse.length === 1 && mt.goiBrowse[0].indexOf("/browse/starts") === 0,
      mt.goiBrowse.join(" "));
    const dsD = lop.querySelector(".fm-list");
    check("bày đúng các điểm xuất phát server trả về", dsD.con.length === DIEM.length,
      "có " + dsD.con.length);
    check("mỗi điểm nói rõ nó là chỗ nào",
      dsD.con[0]._html.includes("fp.start_brain") && dsD.con[2]._html.includes("fp.start_home"));
    check("mỗi điểm mang đường dẫn đầy đủ ở tooltip", dsD.con[0].title === DIEM[0].duong_dan);
    check("chưa đứng ở thư mục nào thì chưa bấm Dùng được",
      lop.querySelector("[data-dung]").disabled === true);

    // ---- 2. Bấm một điểm xuất phát là DUYỆT vào đó ----
    dsD.con[2].onclick();          // "~" -> /home/me
    await cho(); await cho();
    check("bấm một điểm thì duyệt vào đúng đường dẫn của nó",
      /\/browse\?md=0&path=%2Fhome%2Fme$/.test(mt.goiBrowse[1] || ""), mt.goiBrowse.join(" "));
    check("gọi với md=0: chọn thư mục CODE thì đừng quét đếm .md",
      /\/browse\?md=0&/.test(mt.goiBrowse[1] || ""), mt.goiBrowse[1]);

    const ds = lop.querySelector(".fm-list");
    check("dựng đủ hàng: một hàng 'lên trên' cộng hai thư mục con", ds.con.length === 3,
      "có " + ds.con.length);
    check("hàng đầu là 'lên trên'", ds.con[0].className.includes("up"));
    check("thư mục là repo git thì mang dấu riêng",
      ds.con[1]._html.includes("folder-git") && ds.con[1]._html.includes("fp.git"));
    check("thư mục thường thì không mang dấu git",
      !ds.con[2]._html.includes("folder-git") && !ds.con[2]._html.includes("fp.git"));
    check("KHÔNG in nhãn .md khi md=0", !/\.md/.test(ds.con[1]._html + ds.con[2]._html));

    // ---- 3. Bấm một thư mục là ĐI VÀO nó ----
    ds.con[1].onclick();
    await cho(); await cho();
    check("bấm thư mục con thì duyệt tiếp vào đó",
      /path=%2Fhome%2Fme%2Fdu-an$/.test(mt.goiBrowse[2] || ""), (mt.goiBrowse[2] || "") + "");
    const ds2 = lop.querySelector(".fm-list");
    check("danh sách vẽ lại theo thư mục mới", ds2.con.length === 2, "có " + ds2.con.length);
    check("ô đường dẫn hiện chỗ đang đứng",
      lop.querySelector(".fp-go").value === "/home/me/du-an", lop.querySelector(".fp-go").value);

    // ---- 3. Bấm "Dùng thư mục này" là giao ra đúng đường dẫn rồi ĐÓNG ----
    await lop.querySelector("[data-dung]").onclick();
    await cho();
    check("giao ra đúng đường dẫn đang đứng", giaoRa === "/home/me/du-an", String(giaoRa));
    check("chọn xong thì đóng hộp", mt.body.con.length === 0);
  }

  // ---- 4. Dán đường dẫn rồi Enter ----
  {
    const mt = moiTruong(traLoi);
    const FP = nap();
    FP.open({ demMd: false, chon: async () => "" });
    await cho(); await cho();
    const lop = mt.body.con[0];
    const o = lop.querySelector(".fp-go");
    o.value = "/home/me/du-an";
    o.onkeydown({ key: "Enter", preventDefault() {} });
    await cho(); await cho();
    check("dán đường dẫn rồi Enter thì nhảy thẳng tới đó",
      /path=%2Fhome%2Fme%2Fdu-an$/.test(mt.goiBrowse[1] || ""), mt.goiBrowse.join(" "));
  }

  // ---- 5. Lỗi thì GIỮ hộp mở và báo tại chỗ ----
  {
    const mt = moiTruong(traLoi);
    const FP = nap();
    FP.open({ batDau: "/home/me/du-an", demMd: false,
              chon: async () => "Thư mục này không đọc được" });
    await cho(); await cho();
    const lop = mt.body.con[0];
    await lop.querySelector("[data-dung]").onclick();
    await cho();
    check("chọn lỗi thì KHÔNG đóng hộp", mt.body.con.length === 1);
    check("và in câu lỗi tại chỗ",
      lop.querySelector(".fm-hint").textContent === "Thư mục này không đọc được",
      lop.querySelector(".fm-hint").textContent);
    check("dòng gợi ý đổi sang dạng lỗi",
      lop.querySelector(".fm-hint").classList.contains("fm-hint-loi"));
  }

  // ---- 6. Đường dẫn sai thì nói ra, không im lặng ----
  {
    const mt = moiTruong(traLoi);
    const FP = nap();
    FP.open({ demMd: false, chon: async () => "" });
    await cho(); await cho();
    const lop = mt.body.con[0];
    const o = lop.querySelector(".fp-go");
    o.value = "/khong-co-that";
    o.onkeydown({ key: "Enter", preventDefault() {} });
    await cho(); await cho();
    check("path sai thì in câu lỗi của server",
      lop.querySelector(".fm-hint").textContent === "Không phải thư mục",
      lop.querySelector(".fm-hint").textContent);
    check("hộp vẫn mở để chọn lại", mt.body.con.length === 1);
  }

  // ---- 7. demMd=true vẫn là đường cũ của hộp chọn brain ----
  {
    const mt = moiTruong(() => ({ path: "/x", parent: null, here_md: 3, git: false,
                                  dirs: [{ name: "brain", path: "/x/brain", md: 7, git: false }] }));
    const FP = nap();
    FP.open({ batDau: "/x", demMd: true, chon: async () => "" });
    await cho(); await cho();
    check("demMd=true thì gọi md=1", /md=1&/.test(mt.goiBrowse[0]), mt.goiBrowse[0]);
    check("và in con số .md như hộp chọn brain",
      mt.body.con[0].querySelector(".fm-list").con[0]._html.includes("7 .md"));
  }

  // ---- 8. Không đẻ endpoint mới, không tự vẽ kiểu dáng ----
  {
    const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "folder-picker.js"), "utf8");
    // Bóc cả chú thích CUỐI DÒNG: giải thích bằng tiếng Việt là quy ước của repo này, chỉ
    // chữ HIỆN RA MÀN HÌNH mới phải đi qua từ điển.
    const MA = SRC.replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "")
      .replace(/(^|[^:])\/\/.*$/gm, "$1");
    check("chỉ đứng trên hai đường /browse có sẵn, không đẻ endpoint thứ ba",
      (MA.match(/fetch\(/g) || []).length === 2
      && /fetch\("\/browse\?/.test(MA) && /fetch\("\/browse\/starts\?/.test(MA));
    check("mặc bộ lớp .folder-modal/.fm-* có sẵn của style.css",
      /class="folder-modal"/.test(MA) && /class="fm-head"/.test(MA)
      && /class="fm-list"/.test(MA) && /class="fm-foot"/.test(MA));
    check("không nhúng style vào mã", !/<style|\.style\.(width|background|border)/.test(MA));
    check("chữ hiện ra đi qua từ điển", !/[ăâđêôơưáàảãạéèẻ]/i.test(MA));
  }

  // ---- 9. Server CHƯA có endpoint điểm xuất phát: suy biến về hành vi cũ ----
  {
    const mt = moiTruong(traLoiCu);
    const FP = nap();
    FP.open({ demMd: false, chon: async () => "" });
    await cho(); await cho(); await cho();
    const lop = mt.body.con[0];
    check("không có điểm nào thì vẫn duyệt thư mục nhà, KHÔNG bày màn rỗng",
      /\/browse\?md=0&path=$/.test(mt.goiBrowse[1] || ""), mt.goiBrowse.join(" "));
    check("và vẫn dựng được danh sách", lop.querySelector(".fm-list").con.length === 3);
  }

  // ---- 10. Đường VỀ màn điểm xuất phát sau khi đã duyệt sâu ----
  {
    const mt = moiTruong(traLoi);
    const FP = nap();
    FP.open({ batDau: "/home/me/du-an", demMd: false, chon: async () => "" });
    await cho(); await cho();
    const lop = mt.body.con[0];
    check("mở thẳng vào thư mục chỉ định thì KHÔNG hỏi điểm xuất phát",
      mt.goiBrowse.length === 1 && mt.goiBrowse[0].indexOf("/browse?") === 0,
      mt.goiBrowse.join(" "));
    lop.querySelector("[data-nha]").onclick();
    await cho(); await cho();
    check("bấm nút nhà thì quay về màn điểm xuất phát",
      lop.querySelector(".fm-list").con.length === DIEM.length);
    check("và nút Dùng khoá lại vì chưa đứng ở thư mục nào",
      lop.querySelector("[data-dung]").disabled === true);
  }

  console.log();
  if (fails.length) { console.log("FAIL " + fails.length + " test: " + fails.join(", ")); process.exit(1); }
  console.log("TẤT CẢ PASS");
})();
