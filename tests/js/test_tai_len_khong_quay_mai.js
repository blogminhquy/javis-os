/* Tải file lên khung chat không được quay mãi (0.64.43).

       node tests/js/test_tai_len_khong_quay_mai.js

   Chủ repo báo 2026-09-24: "thi thoảng gửi ảnh hoặc file lên nó cứ bị quay mãi", không biết do
   máy chủ hay do mạng. Bản cũ là một fetch trơn, chip chỉ ghi "đang tải..." rồi chờ đủ 3 phút.

   Phần 1 chạy CHÍNH `guiUpload` lấy từ source với XHR và đồng hồ giả: mạng đứng thì phải cắt,
   file to mà vẫn nhích thì KHÔNG được cắt, gửi xong mà máy chủ im thì báo đúng là máy chủ.
   Phần 2 soi chỗ gọi: tự thử lại, nút tải lại trên chip, và i18n đủ hai thứ tiếng. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const APP = D("app.js");
const CSS = D("style.css");
const VI = JSON.parse(D(path.join("i18n", "vi.json")));
const EN = JSON.parse(D(path.join("i18n", "en.json")));

const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
};

function catHam(ten) {
  const i = APP.indexOf("function " + ten + "(");
  if (i < 0) throw new Error("không thấy hàm " + ten + " trong app.js");
  const j = APP.indexOf("\n}\n", i);
  return APP.slice(i, j + 3);
}
const hang = ["TAI_KET_MS", "TAI_CHO_MAY_CHU_MS", "TAI_THU_LAI"]
  .map(k => (APP.match(new RegExp("const " + k + " = [^;]*;")) || [""])[0]).join("\n");
const { guiUpload } = new Function(hang + "\n" + catHam("guiUpload") + "\nreturn { guiUpload };")();

// Đồng hồ giả: tick(ms) đẩy thời gian và chạy bộ canh.
function dongHoGia() {
  let now = 0; const ds = new Map(); let id = 0;
  return {
    now: () => now,
    setInterval: (fn, ms) => { ds.set(++id, { fn, ms, next: ms }); return id; },
    clearInterval: (k) => ds.delete(k),
    tick(ms) {
      const het = now + ms;
      while (now < het) {
        now = Math.min(het, now + 1000);
        for (const t of [...ds.values()]) if (now >= t.next) { t.next += t.ms; t.fn(); }
      }
    },
    soBoCanh: () => ds.size,
  };
}
function xhrGia() {
  const inst = [];
  function XHR() {
    this.upload = {}; this.status = 0; this.responseText = ""; this.aborted = false;
    inst.push(this);
  }
  XHR.prototype.open = function (m, u) { this.method = m; this.url = u; };
  XHR.prototype.send = function (b) { this.body = b; };
  XHR.prototype.abort = function () { this.aborted = true; if (this.onabort) this.onabort(); };
  XHR.inst = inst;
  return XHR;
}
const cho = () => new Promise(r => setImmediate(r));

(async () => {
  // ---- 1a. Thành công, có tiến độ ----
  {
    const XHR = xhrGia(), dh = dongHoGia(), tien = [];
    const p = guiUpload("FD", (a, b) => tien.push([a, b]), { XHR, dongHo: dh });
    const x = XHR.inst[0];
    check("POST đúng /upload", x.method === "POST" && x.url === "/upload" && x.body === "FD");
    x.upload.onprogress({ lengthComputable: true, loaded: 50, total: 100 });
    x.upload.onload();
    x.status = 200; x.responseText = '{"ok":true}'; x.onload();
    const r = await p;
    check("trả status + text của máy chủ", r.status === 200 && r.text === '{"ok":true}');
    check("báo tiến độ ra ngoài (50/100)", tien.some(t => t[0] === 50 && t[1] === 100), JSON.stringify(tien));
    check("gửi xong 100% thì báo mốc -1 (chuyển sang 'máy chủ đang lưu')", tien.some(t => t[0] === -1));
    check("xong thì gỡ bộ canh (không rò timer)", dh.soBoCanh() === 0);
  }

  // ---- 1b. Mạng đứng giữa chừng -> cắt với kind=stall ----
  {
    const XHR = xhrGia(), dh = dongHoGia();
    let loi = null;
    guiUpload("FD", null, { XHR, dongHo: dh, ketMs: 30000 }).catch(e => { loi = e; });
    XHR.inst[0].upload.onprogress({ lengthComputable: true, loaded: 10, total: 100 });
    dh.tick(29000); await cho();
    check("chưa tới ngưỡng kẹt thì chưa cắt", loi === null && !XHR.inst[0].aborted);
    dh.tick(4000); await cho();
    check("đứng im quá ngưỡng thì cắt kết nối", XHR.inst[0].aborted);
    check("lỗi mang kind=stall", loi && loi.kind === "stall", loi && loi.kind);
    check("bộ canh đã gỡ sau khi cắt", dh.soBoCanh() === 0);
  }

  // ---- 1c. File to mạng chậm nhưng vẫn nhích: KHÔNG được cắt dù quá 3 phút ----
  {
    const XHR = xhrGia(), dh = dongHoGia();
    let loi = null, ok = null;
    const p = guiUpload("FD", null, { XHR, dongHo: dh, ketMs: 30000 }).then(r => { ok = r; }, e => { loi = e; });
    const x = XHR.inst[0];
    for (let s = 0; s < 40; s++) {           // 40 x 10 giây = gần 7 phút, lúc nào cũng nhích
      dh.tick(10000);
      x.upload.onprogress({ lengthComputable: true, loaded: s + 1, total: 41 });
    }
    await cho();
    check("vẫn nhích thì không bị cắt dù đã quá 3 phút", !x.aborted && loi === null);
    x.upload.onload(); x.status = 200; x.responseText = "{}"; x.onload();
    await p;
    check("và cuối cùng vẫn nhận được kết quả", ok && ok.status === 200);
  }

  // ---- 1d. Gửi xong 100% mà máy chủ im -> kind=server ----
  {
    const XHR = xhrGia(), dh = dongHoGia();
    let loi = null;
    guiUpload("FD", null, { XHR, dongHo: dh, ketMs: 30000, choMs: 90000 }).catch(e => { loi = e; });
    const x = XHR.inst[0];
    x.upload.onload();
    dh.tick(60000); await cho();
    check("gửi xong, máy chủ im 60 giây: chưa cắt (ngưỡng kẹt mạng không áp vào đây)", loi === null && !x.aborted);
    dh.tick(35000); await cho();
    check("máy chủ im quá ngưỡng chờ thì cắt với kind=server", loi && loi.kind === "server", loi && loi.kind);
  }

  // ---- 1e. Đứt kết nối -> kind=net ----
  {
    const XHR = xhrGia(), dh = dongHoGia();
    let loi = null;
    guiUpload("FD", null, { XHR, dongHo: dh }).catch(e => { loi = e; });
    XHR.inst[0].onerror(); await cho();
    check("đứt kết nối -> kind=net", loi && loi.kind === "net");
  }

  // ============================================================
  // 2. Chỗ gọi
  // ============================================================
  const than = catHam("_taiLen");
  check("_taiLen dùng guiUpload (có tiến độ) thay vì fetch trơn",
    /guiUpload\(fd, onTien\)/.test(than) && !/fetch\("\/upload"/.test(than));
  check("không còn trần cứng 3 phút", !/180000/.test(than));
  check("mạng đứng/đứt thì tự thử lại, máy chủ im thì không",
    /kind !== "server" && lan < TAI_THU_LAI/.test(than) && /continue;/.test(than));
  check("mỗi lần thử lại dựng FormData MỚI (FormData đã gửi không dùng lại được)",
    than.indexOf("for (let lan = 0") < than.indexOf("new FormData()"));
  check("hỏng thì đánh dấu att.loi để chip hiện nút tải lại", /att\.loi = true/.test(than));
  check("uploadFile giữ lại File để tải lại", /att\.file = file;/.test(catHam("uploadFile")));
  check("uploadFile tải lại vào CHÍNH chip cũ, không đẻ chip mới",
    /if \(moi\) pendingAttachments\.push\(att\)/.test(catHam("uploadFile")));
  check("taiLaiDinhKem không chạy chồng khi đang tải", /a\.uploading/.test(catHam("taiLaiDinhKem")));
  check("chip lỗi có nút .chip-retry gọi taiLaiDinhKem",
    /class="chip-retry"/.test(APP) && /taiLaiDinhKem\(\+b\.dataset\.i\)/.test(APP));
  // forEach(uploadFile) truyền INDEX làm tham số thứ hai -> bị hiểu nhầm thành chip cũ.
  check("không còn forEach(uploadFile) (index lọt vào tham số att)", !/forEach\(uploadFile\)/.test(APP));
  check("CSS có kiểu cho chip lỗi và nút tải lại",
    /\.attach-chip\.loi/.test(CSS) && /\.attach-chip \.chip-retry/.test(CSS));

  for (const k of ["app.att_progress", "app.att_progress_mb", "app.att_saving", "app.att_retrying",
                   "app.att_stalled", "app.att_server_slow", "app.att_retry"]) {
    check("i18n đủ vi + en: " + k, !!VI[k] && !!EN[k]);
  }
  const khongGach = Object.entries(VI).concat(Object.entries(EN))
    .filter(([k]) => k.startsWith("app.att_")).every(([, v]) => !/[\u2013\u2014]/.test(v));
  check("chữ mới không có gạch dài", khongGach);

  if (fails.length) { console.log("\n" + fails.length + " FAIL"); process.exit(1); }
  console.log("\nTất cả ok");
})();
