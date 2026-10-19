/* Test anh va file khach gui trong Hop thu bot (ht-media.js, 0.171.0). Chay tay / CI:
       node tests/js/test_ht_media.js
   Chu repo 15/10/2026: khach gui anh thi Hop thu chi hien "image https://...jpg". Muon anh hien thang,
   file thi bam tai ve. Ghi chu: KHONG dung ky tu em dash o bat ky dau. */
const fs = require("fs");
const path = require("path");
const M = require("../../dashboard/ht-media.js");

const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const ic = (n) => "<i " + n + ">";
const tw = (k) => k;

// ---- 1. Zalo cá nhân: ảnh trơn, link nằm ở metadata.image_url và cả trong text ----
const ZL = "https://photo-stal-6.zdn.vn/no/jpg/e1a2/abc.jpg";
let p = M.phanTich({ message_type: "image", text: ZL, metadata: { image_url: ZL }, conversation_id: 7 });
check("ảnh Zalo: dùng link ảnh", p.anh === ZL, p.anh);
check("ảnh Zalo trơn: không lặp link thành chú thích", p.chu === "", p.chu);
let h = M.html(p, esc, ic, tw);
check("ảnh hiện bằng thẻ img", h.indexOf('<img src="' + ZL + '"') > 0, h);
check("ảnh không gửi referrer (máy chủ ảnh có thể chặn link ngoài)", h.indexOf('referrerpolicy="no-referrer"') > 0);
check("bấm ảnh mở cỡ thật ở thẻ mới", h.indexOf('target="_blank"') > 0 && h.indexOf("noopener") > 0);
check("ảnh hết hạn có dòng thay thế", h.indexOf("ht.anh_hong") > 0 && h.indexOf("onerror") > 0);

p = M.phanTich({ message_type: "image", text: "Mẫu này còn không shop", metadata: { image_url: ZL } });
check("ảnh có chú thích: giữ chú thích", p.anh === ZL && p.chu === "Mẫu này còn không shop", JSON.stringify(p));
p = M.phanTich({ message_type: "image", text: "[Zalo cá nhân: khách gửi image]", metadata: { image_url: ZL } });
check("chữ nền 'khách gửi image' không thành chú thích", p.chu === "", p.chu);
p = M.phanTich({ message_type: "image", text: ZL, metadata: {} });
check("không có metadata vẫn lấy link ảnh trong text", p.anh === ZL);

// ---- 2. Kênh bot tải về máy: đi qua /conversations/<id>/media ----
const DUONG = "/data/brains/b/inbox/khach/tg_1760_anh.jpg";
p = M.phanTich({ message_type: "image", conversation_id: 12,
                 text: "[Người dùng gửi ảnh qua Telegram, đã tải về: " + DUONG + "]\nÁo này size M còn không?" });
check("ảnh đã tải về: qua đường media của hội thoại", p.anh === "/conversations/12/media?p=" + encodeURIComponent(DUONG), p.anh);
check("CANARY: đường dẫn máy chủ không lọt vào chú thích", p.chu === "Áo này size M còn không?", p.chu);
p = M.phanTich({ message_type: "image", conversation_id: 3,
                 text: "[The user sent an image on Messenger, downloaded to: /x/inbox/khach/a.png]" });
check("bản tiếng Anh của dòng tải về cũng nhận", p.anh.indexOf("/conversations/3/media?p=") === 0 && p.chu === "", JSON.stringify(p));

// ---- 3. File ----
p = M.phanTich({ message_type: "file", text: "baogia.xlsx",
                 metadata: { attachment: { url: "https://f.zdn.vn/baogia.xlsx", name: "baogia.xlsx", size: 52300 } } });
check("file Zalo: link tải về", p.file && p.file.href === "https://f.zdn.vn/baogia.xlsx", JSON.stringify(p));
check("file Zalo: tên và dung lượng", p.file.ten === "baogia.xlsx" && p.file.coDung === "51 KB", JSON.stringify(p.file));
check("tên file không lặp thành chú thích", p.chu === "", p.chu);
h = M.html(p, esc, ic, tw);
check("thẻ file có thuộc tính download", h.indexOf(" download>") > 0 && h.indexOf("ht.tai_ve") > 0, h);
p = M.phanTich({ message_type: "other", conversation_id: 5,
                 text: "[Người dùng gửi file qua Slack, đã tải về: /b/inbox/khach/hop-dong.pdf]" });
check("file đã tải về: tải qua media với dl=1", p.file && p.file.href === "/conversations/5/media?p=" +
      encodeURIComponent("/b/inbox/khach/hop-dong.pdf") + "&dl=1" && p.file.ten === "hop-dong.pdf", JSON.stringify(p));
p = M.phanTich({ message_type: "file", metadata: { attachment: { url: "javascript:alert(1)", name: "x" } }, text: "x" });
check("CANARY: link file không phải https thì không thành nút tải", !p.file, JSON.stringify(p));

// ---- 4. Tin chữ thường: không đụng ----
p = M.phanTich({ message_type: "text", text: "chào shop" });
check("tin chữ: không có media", !p.anh && !p.file);

// ---- 5. Dòng xem trước trong danh sách hội thoại ----
check("xem trước: ảnh đã tải về thành nhãn ảnh kèm chú thích",
      M.tomTat("[Người dùng gửi ảnh qua Telegram, đã tải về: /b/inbox/khach/a.jpg]\nCòn size M?", tw) === "ht.anh: Còn size M?");
check("CANARY: xem trước không lộ đường dẫn máy chủ",
      M.tomTat("[Người dùng gửi file qua Slack, đã tải về: /data/b/inbox/khach/hop-dong.pdf]", tw) === "hop-dong.pdf");
check("xem trước: link ảnh Zalo trần thành nhãn ảnh", M.tomTat(ZL, tw) === "ht.anh");
check("xem trước: chữ thường giữ nguyên", M.tomTat("chào shop", tw) === "chào shop");

// ---- 6. Escape ----
h = M.html({ anh: 'https://a.b/x.jpg" onload="alert(1)', file: null }, esc, ic, tw);
check("CANARY: link ảnh được escape, không chèn được thuộc tính", h.indexOf('" onload="') < 0, h);

// ---- 7. 0.231.0: a photo opens inside Javis (lightbox), not in a new tab ----
const src = fs.readFileSync(path.join(__dirname, "../../dashboard/ht-media.js"), "utf8");
check("bấm ảnh mở lightbox trong Javis, Ctrl/Cmd/chuột giữa vẫn mở thẻ mới",
  /closest\("a\.ht-anh"\)/.test(src) && /window\.JavisLightbox\.open\(href, tenAnh\(href\)\)/.test(src)
  && /e\.ctrlKey \|\| e\.metaKey/.test(src) && /addEventListener\("click", function \(e\) \{[\s\S]*?\}, true\);/.test(src));
check("ảnh hỏng thì để link tự mở", /classList\.contains\("hong"\)/.test(src));
check("tên ảnh lấy từ ?p= của đường /media", M.tenAnh("/conversations/c1/media?p=%2Fdata%2Fb%2Finbox%2Fanh-khach.jpg") === "anh-khach.jpg");
check("tên ảnh Zalo lấy từ đường dẫn", M.tenAnh("https://s120-ava-talk.zadn.vn/a/b/photo.jpg?x=1") === "photo.jpg");
const cr = fs.readFileSync(path.join(__dirname, "../../dashboard/chat-render.js"), "utf8");
check("lightbox mở ảnh trang khác không gửi referrer (CDN Zalo chặn)", /img\.referrerPolicy = "no-referrer"/.test(cr));

console.log();
if (fails.length) {
  console.log("ĐỎ " + fails.length + " mục: " + fails.join(", "));
  process.exit(1);
}
console.log("Tất cả xanh.");
