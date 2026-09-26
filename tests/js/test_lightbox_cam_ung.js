/* Ảnh trong lightbox phải zoom quanh hai ngón tay và không trôi khỏi khung. */
const fs = require("fs");
const path = require("path");
const lightbox = require("../../dashboard/chat-render.js");
const source = fs.readFileSync(path.join(__dirname, "../../dashboard/chat-render.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "../../dashboard/style.css"), "utf8");

const fails = [];
function check(name, value) {
  console.log((value ? "ok   " : "FAIL ") + name);
  if (!value) fails.push(name);
}
function near(actual, expected) { return Math.abs(actual - expected) < 0.001; }

check("có phép tính pinch dùng chung với trình xem ảnh", typeof lightbox.lightboxPinchStep === "function");
check("có giới hạn kéo ảnh trong khung", typeof lightbox.lightboxClampPan === "function");

if (typeof lightbox.lightboxPinchStep === "function") {
  const step = lightbox.lightboxPinchStep;
  let result = step({ scale: 1, x: 0, y: 0 },
    { x: 30, y: -10, distance: 100 }, { x: 30, y: -10, distance: 200 });
  check("zoom 2x giữ điểm giữa hai ngón đứng yên",
    near(result.scale, 2) && near(result.x, -30) && near(result.y, 10));
  result = step({ scale: 2, x: -30, y: 10 },
    { x: 30, y: -10, distance: 100 }, { x: 40, y: 5, distance: 100 });
  check("di chuyển hai ngón kéo ảnh theo đúng quãng đường",
    near(result.scale, 2) && near(result.x, -20) && near(result.y, 25));
  result = step({ scale: 2, x: 0, y: 0 },
    { x: 0, y: 0, distance: 100 }, { x: 0, y: 0, distance: 1000 });
  check("không phóng quá 4x", near(result.scale, 4));
  result = step({ scale: 2, x: 0, y: 0 },
    { x: 0, y: 0, distance: 100 }, { x: 0, y: 0, distance: 1 });
  check("không thu nhỏ hơn ảnh vừa màn", near(result.scale, 1));
}

if (typeof lightbox.lightboxClampPan === "function") {
  const result = lightbox.lightboxClampPan({ scale: 2, x: 1000, y: -1000 },
    { imageWidth: 200, imageHeight: 100, viewportWidth: 300, viewportHeight: 200 });
  check("kéo tới mép không làm ảnh biến mất khỏi màn", near(result.x, 50) && near(result.y, 0));
}

check("khung ảnh nhận thao tác cảm ứng và chặn zoom cả trang",
  /touchstart/.test(source) && /touchmove/.test(source) && /touchend/.test(source)
  && /touchcancel/.test(source) && /touch-action:\s*none/.test(css));
check("chế độ cỡ thật vẫn kéo được bằng một ngón trên điện thoại",
  /khung\.scrollLeft\s*-\=/.test(source) && /khung\.scrollTop\s*-\=/.test(source));

if (fails.length) {
  console.log("\nFAIL - test_lightbox_cam_ung: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_lightbox_cam_ung: tất cả pass");
