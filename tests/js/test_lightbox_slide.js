/* 0.358.0 (chủ repo 27/10/2026): xem ảnh trong chat phải vuốt trái, phải được sang các ảnh khác của cùng khung chat,
   như trình xem ảnh của điện thoại ("2 / 4"). Áp cho mọi khung chat: chat chính, Nhóm, Hội thoại khách hàng.

       node tests/js/test_lightbox_slide.js */
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "../../dashboard");
const lb = require(path.join(D, "chat-render.js"));
const src = fs.readFileSync(path.join(D, "chat-render.js"), "utf8");
const htSrc = fs.readFileSync(path.join(D, "ht-media.js"), "utf8");
const css = fs.readFileSync(path.join(D, "style.css"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(D, "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(D, "i18n", "en.json"), "utf8"));

const fails = [];
function check(name, value) {
  console.log((value ? "ok   " : "FAIL ") + name);
  if (!value) fails.push(name);
}

const step = lb.lightboxGalleryStep, swipe = lb.lightboxSwipe;
check("có phép tính đổi ảnh và nhận vuốt", typeof step === "function" && typeof swipe === "function");
check("ảnh sau, ảnh trước", step(4, 1, 1) === 2 && step(4, 1, -1) === 0);
check("ảnh đầu và ảnh cuối đứng yên (không quay vòng)", step(4, 0, -1) === 0 && step(4, 3, 1) === 3);
check("một ảnh: không đổi", step(1, 0, 1) === 0 && step(0, 0, 1) === 0);
check("vuốt sang trái là ảnh sau, sang phải là ảnh trước", swipe(-120, 5) === 1 && swipe(120, -5) === -1);
check("chạm nhẹ hay kéo dọc không đổi ảnh", swipe(30, 0) === 0 && swipe(-80, 100) === 0 && swipe(0, 0) === 0);

check("bấm ảnh trong chat mở cả thư viện ảnh của khung chat đó", /moTuLink\(a\);\n    \}, true\);/.test(src)
  && /var LB_LINKS = "a\.jv-img-link, a\.ht-anh";/.test(src));
check("khung chat là danh sách cuộn gần nhất (chat chính, Nhóm, hộp thư khách...)",
  /\[data-lb-scope\], \.transcript, \.tm-msgs, \.tm-info-imgs/.test(src) && /oy === "auto" \|\| oy === "scroll"/.test(src));
check("ảnh trùng chỉ tính một lần, ảnh hỏng bị bỏ", /if \(thay\[m\.url\] !== undefined\) return;/.test(src)
  && /if \(l\.classList\.contains\("hong"\)\) return;/.test(src));
check("ảnh khách hàng ở trang Hội thoại cũng mở theo thư viện", /window\.JavisLightbox\.openFrom\(a\)/.test(htSrc)
  && /openFrom: moTuLink/.test(src));
check("phím mũi tên trái, phải đổi ảnh", /e\.key === "ArrowLeft" \|\| e\.key === "ArrowRight"/.test(src));
check("vuốt chỉ đổi ảnh khi ảnh đang vừa màn (đang phóng to thì kéo ảnh)",
  /zoom\.scale <= 1 && !_lb\.classList\.contains\("that"\)/.test(src) && /lightboxSwipe\(ev\.changedTouches\[0\]\.clientX - vuot\.x/.test(src));
check("vuốt xong không đóng nhầm lightbox", /if \(buoc\) \{ vuaKeoLuc = Date\.now\(\); chuyen\(buoc\); \}/.test(src));
check("ảnh trước, sau được tải sẵn", /\[i - 1, i \+ 1\]\.forEach/.test(src));
check("nút Mở tab mới mở đúng ảnh đang xem", /window\.open\(_lbUrl, "_blank", "noopener"\)/.test(src));
check("CSS: nút tròn hai bên, bộ đếm 16px, ẩn nút khi đang phóng to",
  /\.jv-lb-di \{ position: absolute;/.test(css) && /\.jv-lb-dem \{ color: #fff; font-size: 16px;/.test(css)
  && /\.jv-lb\.that \.jv-lb-di, \.jv-lb\.pinch \.jv-lb-di \{ display: none; \}/.test(css));
check("chữ hai thứ tiếng", vi["crender.lb_count"] === "{i} / {n}" && en["crender.lb_count"] === "{i} of {n}"
  && !!vi["crender.lb_prev"] && !!en["crender.lb_next"]);

if (fails.length) { console.log("\nFAIL - test_lightbox_slide: " + fails.length); process.exit(1); }
console.log("\nOK - test_lightbox_slide");
