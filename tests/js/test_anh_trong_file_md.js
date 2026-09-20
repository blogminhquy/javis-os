/* Ảnh trong file .md phải HIỆN, kể cả khi note nằm trong thư mục con (0.59.43).

       node tests/js/test_anh_trong_file_md.js

   Chủ dự án 18/09: "ở file .md hiện tại đang không hiển thị ảnh, nếu có chèn link ảnh hoặc là
   tham chiếu đến ảnh trong folder cũng nên hiển thị ảnh trong file .md nhé."

   Nguyên nhân: mdToHtml phân giải MỌI đường dẫn tương đối theo GỐC BRAIN. Note nằm ở
   "06 - Sources/Ghi chu/note.md" mà viết ![](anh.jpg) thì Javis đi tìm <brain>/anh.jpg - không
   bao giờ có - nên ảnh thành một ô xám. Obsidian, VS Code và GitHub đều hiểu đường dẫn đó là
   "cạnh chính file này".

   Test CHẠY THẬT mdToHtml (require thẳng chat-render.js) rồi soi URL nó sinh ra, và chạy thật
   jvImgGone trên một thẻ <img> giả để chắc chuỗi dự phòng có hoạt động. */
const assert = require("assert");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const CR = require(path.join(ROOT, "dashboard", "chat-render.js"));

const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

const THU_MUC = "06 - Sources/Ghi chu";
function ve(md, thuMuc) {
  return CR.mdToHtml(md, "brain", { trinhSua: true, thuMuc: thuMuc === undefined ? THU_MUC : thuMuc });
}
// path= trong URL đầu tiên của chuỗi html (đã giải mã).
function duongDan(html) {
  const m = /src="([^"]*)"/.exec(html);
  if (!m) return null;
  const q = /[?&]path=([^&"]*)/.exec(m[1].replace(/&amp;/g, "&"));
  return q ? decodeURIComponent(q[1]) : m[1];
}
// Danh sách chỗ dự phòng (data-jv-thu), đã giải mã thành đường dẫn.
function duPhong(html) {
  const m = /data-jv-thu="([^"]*)"/.exec(html);
  if (!m) return [];
  return m[1].replace(/&amp;/g, "&").split("|").map((u) => {
    const q = /[?&]path=([^&]*)/.exec(u);
    return q ? decodeURIComponent(q[1]) : u;
  });
}

// ---- 1. Ảnh cạnh chính file note (cái chủ dự án báo) ----
{
  const h = ve("![ảnh](anh.jpg)");
  check("ảnh cạnh note tìm theo THƯ MỤC CỦA NOTE trước",
    duongDan(h) === THU_MUC + "/anh.jpg", duongDan(h));
  check("vẫn còn đường lui về gốc brain (note cũ đang trỏ kiểu đó)",
    duPhong(h).indexOf("anh.jpg") >= 0, duPhong(h).join(", "));
  check("và đường lui vào attachments (nơi Javis cất ảnh nó sinh ra)",
    duPhong(h).indexOf("attachments/anh.jpg") >= 0, duPhong(h).join(", "));
  check("có dựng ra thẻ <img> thật, không phải chữ trơ", /<img[^>]*class="chat-img"/.test(h));
}

// ---- 2. Ảnh trong thư mục con cạnh note ----
{
  const h = ve("![x](./hinh/a2.png)");
  check("./hinh/a2.png tính theo thư mục note", duongDan(h) === THU_MUC + "/hinh/a2.png", duongDan(h));
}

// ---- 3. ".." phải được THU GỌN tại chỗ, không gửi thẳng cho server ----
{
  const h = ve("![x](../attachments/a3.png)");
  check("..  thu gọn thành đường dẫn thật", duongDan(h) === "06 - Sources/attachments/a3.png",
    duongDan(h));
  check('không còn chuỗi ".." nào trong URL (server sẽ từ chối nó)',
    (duongDan(h) || "").indexOf("..") < 0 && duPhong(h).every((p) => p.indexOf("..") < 0),
    duongDan(h) + " | " + duPhong(h).join(", "));
}

// ---- 4. Ảnh nhúng kiểu Obsidian ![[...]] ----
{
  const h = ve("![[anh4.png]]");
  check("![[anh4.png]] cũng tìm cạnh note trước", duongDan(h) === THU_MUC + "/anh4.png", duongDan(h));
  check("và cũng có đủ chỗ dự phòng", duPhong(h).length >= 2, duPhong(h).join(", "));
}

// ---- 5. Không được đụng vào ảnh ngoài ----
{
  const h = ve("![web](https://vi.du/a.png)");
  check("ảnh URL ngoài giữ nguyên", /src="https:\/\/vi\.du\/a\.png"/.test(h), h.slice(0, 120));
  check("ảnh ngoài KHÔNG bị gắn chỗ dự phòng", !/data-jv-thu/.test(h));
  const h2 = ve("![d](data:image/png;base64,iVBOR)");
  check("ảnh data: giữ nguyên", /src="data:image\/png/.test(h2));
}

// ---- 6. Không truyền thư mục thì giữ ĐÚNG hành vi cũ (gốc brain) ----
{
  const h = ve("![x](anh.jpg)", "");
  check("không có thư mục thì vẫn phân giải theo gốc brain như trước",
    duongDan(h) === "anh.jpg", duongDan(h));
  const h2 = CR.mdToHtml("![x](anh.jpg)", "brain");
  check("gọi mdToHtml kiểu cũ (2 tham số) không đổi hành vi", duongDan(h2) === "anh.jpg",
    duongDan(h2));
}

// ---- 7. Thư mục KHÔNG được rò sang lần render sau ----
{
  ve("![x](anh.jpg)");
  const h = CR.mdToHtml("![x](anh.jpg)", "brain");
  check("render xong thì trả thư mục về như cũ, không dính sang tin nhắn chat",
    duongDan(h) === "anh.jpg", duongDan(h));
}

// ---- 8. jvImgGone: phải THỬ chỗ kế tiếp trước khi bỏ cuộc ----
{
  // Thẻ <img> giả, đủ những gì imgGone đụng tới.
  function imgGia(src, thu) {
    const attrs = { src: src, "data-jv-thu": thu };
    return {
      attrs: attrs,
      parentNode: { tagName: "A", className: "jv-img-link", href: src,
        setAttribute(k, v) { if (k === "href") this.href = v; } },
      getAttribute: (k) => (k in attrs ? attrs[k] : null),
      setAttribute(k, v) { attrs[k] = v; },
      removeAttribute(k) { delete attrs[k]; },
      replaceWith() { attrs._dathay = true; },
    };
  }
  const el = imgGia("/files/raw?path=A", "/files/raw?path=B|/files/raw?path=C");
  CR.imgGone(el);
  check("hỏng lần 1 thì đổi sang chỗ thứ hai, KHÔNG hiện ô xám",
    el.attrs.src === "/files/raw?path=B" && !el.attrs._dathay, el.attrs.src);
  check("thẻ <a> bọc ngoài đi theo, bấm vào không mở URL vừa hỏng",
    el.parentNode.href === "/files/raw?path=B", el.parentNode.href);
  check("danh sách còn lại ngắn đi một", el.attrs["data-jv-thu"] === "/files/raw?path=C",
    el.attrs["data-jv-thu"]);
  CR.imgGone(el);
  check("hỏng lần 2 thì sang chỗ cuối", el.attrs.src === "/files/raw?path=C" && !el.attrs._dathay,
    el.attrs.src);
  check("hết chỗ thử thì bỏ thuộc tính đi", el.attrs["data-jv-thu"] === undefined);
}

// ---- 9. HAI trình sửa .md đều phải TRUYỀN thư mục vào, không thì bản vá trên vô nghĩa ----
// Javis có hai khung mở file .md khác hẳn nhau (xem test_nut_chia_se_trinh_sua_dinh.js). Quên
// một cái là ảnh vẫn không hiện ở khung đó, mà mọi phép thử trên vẫn xanh.
{
  const fs = require("fs");
  const csrc = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
  const fsrc = fs.readFileSync(path.join(ROOT, "dashboard", "file-editor.js"), "utf8");
  const goiCon = csrc.match(/mdToHtml\(ta\.value[^)]*\)/g) || [];
  check("trình sửa định (console.js) gọi mdToHtml ở cả 2 chỗ và chỗ nào cũng truyền thuMuc",
    goiCon.length >= 2 && goiCon.every((g) => g.indexOf("thuMuc") >= 0),
    goiCon.join("  ||  "));
  const goiFe = fsrc.match(/mdToHtml\(ta\.value[^)]*\)/g) || [];
  check("trình sửa modal (file-editor.js) cũng vậy",
    goiFe.length >= 2 && goiFe.every((g) => g.indexOf("thuMuc") >= 0),
    goiFe.join("  ||  "));
  check("console.js lấy thư mục từ đường dẫn file đang mở",
    /neThuMuc\s*=\s*rel\.includes\("\/"\)/.test(csrc));
  check("file-editor.js lấy thư mục từ đường dẫn file đang mở",
    /thuMuc\s*=\s*ceil\.indexOf\("\/"\)/.test(fsrc));
}

console.log("");
if (fails.length) { console.log("FAILED: " + fails.length); process.exit(1); }
console.log("Tất cả đều xanh.");
