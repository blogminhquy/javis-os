/* Bấm ảnh trong chat phải MỞ XEM PHÓNG TO, không phải tải file về.

       node tests/js/test_lightbox_anh.js

   Chủ repo (2026-07-31): "trên web chat khi yêu cầu tạo hình sau khi có hình bấm vào tự động
   download file chứ ko có mở zoom lên kiểu như trên chatgpt... Thêm chức năng view (default),
   và download".

   Bệnh: imgHtml bọc ảnh vault trong <a download href=...&dl=1>, nên bấm một cái là file rơi
   xuống máy; muốn xem cho rõ thì phải mở file vừa tải. Trớ trêu là CSS .chat-img đã để
   cursor:zoom-in từ lâu - con trỏ hứa phóng to mà hành vi lại là tải về.

   Hành vi đã đo trong app THẬT bằng Chromium (16 phép thử: bấm mở lightbox và KHÔNG tải file,
   nút Tải về tải đúng tên, bấm ảnh đổi qua lại vừa-màn/cỡ-thật, Esc và bấm nền đen đóng, bấm
   thanh công cụ không đóng nhầm, Ctrl+bấm vẫn mở tab mới). CI chỉ có node nên test này khoá
   phần hợp đồng: HTML sinh ra và các mảnh logic/CSS mà trình duyệt cần. */
const fs = require("fs");
const path = require("path");

global.currentBrainPath = () => "brains/B";
const { mdToHtml } = require("../../dashboard/chat-render.js");
const SRC = fs.readFileSync(path.join(__dirname, "../../dashboard/chat-render.js"), "utf8");
const CSS = fs.readFileSync(path.join(__dirname, "../../dashboard/style.css"), "utf8");

let fails = [];
function check(name, cond, them) {
  console.log((cond ? "ok   " : "FAIL ") + name + (them && !cond ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
}

// ---- 1. Ảnh trong vault: link XEM, không phải link TẢI ----
const h = mdToHtml("![ảnh sản phẩm](attachments/a.png)");
check("ảnh vault bọc trong a.jv-img-link", /<a class="jv-img-link"/.test(h), h.slice(0, 90));
check("CANARY: KHÔNG còn thuộc tính download trên link ảnh", !/<a[^>]*\sdownload[^>]*>\s*<img/.test(h), h);
check("CANARY: KHÔNG còn dl=1 trên link ảnh", !/dl=1/.test(h), h);
check("CANARY: không còn dùng class tải file cho ảnh", !/jv-fdownload[^>]*>\s*<img/.test(h), h);
check("giữ đường dẫn vault để lấy tên file", /data-vault-path="attachments\/a\.png"/.test(h), h);
check("href trỏ thẳng ảnh (Ctrl+bấm mở tab mới được)",
      /href="\/files\/raw\?brain=[^"]*path=attachments%2Fa\.png"/.test(h), h);
check("có title gợi ý hành vi", /title="Bấm để xem phóng to"/.test(h), h);

// ---- 2. Ảnh wikilink và ảnh ngoài cũng vào lightbox ----
// Chủ repo: "phần ảnh thì cũng nên như vậy cho phù hợp" -> mọi ảnh trong chat cùng một hành vi.
check("ảnh ![[...]] cũng vào lightbox", /jv-img-link/.test(mdToHtml("![[attachments/b.png]]")));
const ngoai = mdToHtml("![x](https://e.com/a.png)");
check("ảnh URL ngoài cũng vào lightbox", /jv-img-link/.test(ngoai), ngoai);
check("ảnh ngoài không bịa data-vault-path", !/data-vault-path/.test(ngoai), ngoai);

// ---- 3. File KHÔNG phải ảnh vẫn giữ nguyên hành vi tải về ----
const pdf = mdToHtml("[Báo cáo.pdf](exports/bc.pdf)");
check("CANARY: link file thường VẪN là tải về", /jv-fdownload/.test(pdf) && /dl=1/.test(pdf), pdf);
check("link file thường không bị biến thành link ảnh", !/jv-img-link/.test(pdf), pdf);

// ---- 4. Lightbox có đủ ba việc: xem, tải, đóng ----
check("có hàm mở lightbox", /function moLightbox\(/.test(SRC));
check("có hàm đóng lightbox", /function dongLightbox\(/.test(SRC));
check("có nút Tải về", /data-lb="tai"/.test(SRC) && /Tải về/.test(SRC));
check("có nút mở tab mới", /data-lb="tab"/.test(SRC));
check("có nút đóng", /data-lb="dong"/.test(SRC));
check("Esc đóng lightbox", /e\.key === "Escape"/.test(SRC) && /dongLightbox\(\)/.test(SRC));
// Nút Tải về phải đi đường dl=1 của server: đường đó ép tải kèm ĐÚNG tên file (cả tên tiếng
// Việt). Chỉ đặt thuộc tính download trên link cross-origin là trình duyệt bỏ qua tên.
check("nút Tải về dùng đường dl=1 của server", /_lbUrl \+ "&dl=1"/.test(SRC));

// ---- 5. Hai chỗ dễ làm hỏng ----
// Tên file do người dùng đặt -> phải đi textContent, nối vào innerHTML là mở đường HTML lạ.
check("CANARY: tên file đặt bằng textContent, không nối vào innerHTML",
      /querySelector\("\.jv-lb-ten"\)\.textContent = /.test(SRC));
// Ctrl/Cmd/giữa chuột phải để trình duyệt tự xử -> mở ảnh gốc ra tab mới như mọi link khác.
check("CANARY: Ctrl/Cmd/Shift/giữa chuột KHÔNG bị nuốt",
      /e\.ctrlKey \|\| e\.metaKey \|\| e\.shiftKey \|\| e\.altKey \|\| e\.button > 0/.test(SRC));
// Đang soạn note thì bấm ảnh là để sửa, không phải để xem.
check("không bung lightbox khi đang soạn trong editor",
      /contenteditable="true"\], \.jvfe-modal, \.note-editor/.test(SRC));
// Module còn phải require được dưới node -> mọi thứ chạm `window` phải nằm trong khối có DOM.
check("CANARY: gán window.JavisLightbox nằm TRONG khối kiểm tra DOM",
      SRC.indexOf('window.JavisLightbox') > SRC.indexOf('if (typeof document !== "undefined")'));

// ---- 6. CSS ----
function than(sel) {
  const re = new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*\\{[^}]*\\}");
  const m = CSS.match(re);
  return m ? m[0] : "";
}
check("lớp phủ toàn màn hình", /position:\s*fixed/.test(than(".jv-lb")) && /inset:\s*0/.test(than(".jv-lb")));
check("lớp phủ nằm trên mọi thứ", /z-index:\s*[45]\d{3}/.test(than(".jv-lb")), than(".jv-lb"));
check("ảnh mặc định vừa màn",
      /max-width:\s*100%/.test(than(".jv-lb-img")) && /max-height:\s*100%/.test(than(".jv-lb-img")));
check("có chế độ xem cỡ thật", /max-width:\s*none/.test(than(".jv-lb.that .jv-lb-img")));
check("khoá cuộn nền khi đang xem", /overflow:\s*hidden/.test(than("body.jv-lb-open")));
check("khung ảnh cuộn được khi xem cỡ thật", /overflow:\s*auto/.test(than(".jv-lb-khung")));
check("con trỏ zoom-in trên ảnh chat vẫn đúng nghĩa", /cursor:\s*zoom-in/.test(than(".chat-img")));

if (fails.length) {
  console.log("\nFAIL - test_lightbox_anh: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_lightbox_anh: tất cả pass");
