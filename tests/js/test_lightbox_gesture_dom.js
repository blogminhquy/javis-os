/* Chạy handler cảm ứng thật của lightbox trên DOM tối thiểu, không cần browser. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

function classes() {
  const names = new Set();
  return {
    add: name => names.add(name), remove: name => names.delete(name),
    contains: name => names.has(name),
    toggle: (name, force) => {
      if (force === undefined ? !names.has(name) : force) names.add(name);
      else names.delete(name);
    },
  };
}
function element(extra = {}) {
  const listeners = {};
  return Object.assign({ listeners, style: {}, classList: classes(),
    addEventListener(name, fn) { listeners[name] = fn; },
    closest() { return null; },
  }, extra);
}

const img = element({ offsetWidth: 200, offsetHeight: 200 });
const frame = element({ clientWidth: 300, clientHeight: 300,
  scrollLeft: 0, scrollTop: 0,
  getBoundingClientRect() { return { left: 0, top: 0 }; } });
const title = element();
const lb = element({
  querySelector(selector) {
    return { ".jv-lb-img": img, ".jv-lb-khung": frame, ".jv-lb-ten": title }[selector];
  },
  contains(node) { return node === img || node === frame || node === title; },
  remove() {},
});
const document = {
  body: element({ appendChild() {} }),
  createElement() { return lb; },
  addEventListener() {},
};
const window = { t: key => key, ic: () => "", addEventListener() {} };
let now = 1000;
const sandbox = { window, document, history: { pushState() {}, back() {} },
  getComputedStyle: () => ({ paddingLeft: "0px", paddingRight: "0px",
    paddingTop: "0px", paddingBottom: "0px" }), Date: { now: () => now }, console };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../../dashboard/chat-render.js"), "utf8"), sandbox);
window.JavisLightbox.open("data:image/png;base64,AA==", "ảnh thử");

let prevented = 0;
function touch(name, points) {
  frame.listeners[name]({ touches: points.map(([x, y]) => ({ clientX: x, clientY: y })),
    preventDefault() { prevented++; } });
}
const check = (label, ok) => {
  console.log((ok ? "ok   " : "FAIL ") + label);
  if (!ok) process.exitCode = 1;
};

touch("touchstart", [[100, 150], [200, 150]]);
touch("touchmove", [[50, 150], [250, 150]]);
check("chụm mở phóng ảnh 2x, không phóng cả trang",
  img.style.transform.includes("scale(2)") && lb.classList.contains("pinch") && prevented >= 2);
img.listeners.click({ stopPropagation() {}, preventDefault() {} });
check("click phát sinh sau pinch không bật chế độ cỡ thật", !lb.classList.contains("that"));

touch("touchend", [[150, 150]]);
touch("touchmove", [[190, 150]]);
check("một ngón kéo ảnh đã zoom", img.style.transform.includes("translate(40px, 0px)"));

touch("touchend", []);
touch("touchstart", [[100, 150], [200, 150]]);
touch("touchmove", [[125, 150], [175, 150]]);
check("chụm lại về ảnh vừa màn", img.style.transform === "" && !lb.classList.contains("pinch"));

now += 500;
img.listeners.click({ stopPropagation() {}, preventDefault() {} });
touch("touchstart", [[150, 150]]);
touch("touchmove", [[100, 150]]);
check("chế độ cỡ thật vẫn kéo được bằng cảm ứng", lb.classList.contains("that") && frame.scrollLeft === 50);

if (!process.exitCode) console.log("\nOK - test_lightbox_gesture_dom: tất cả pass");
