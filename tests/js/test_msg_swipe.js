// 0.216.0: vuốt tin sang trái để trích dẫn trên điện thoại (dashboard/msg-swipe.js), khung chat chính.
//
//     node tests/js/test_msg_swipe.js
//
// Chủ repo 18/10/2026: "kéo sang trái 1 bong bóng trò chuyện thì sẽ thành quote lại tin đấy luôn".
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const SW = require(path.join(D, "msg-swipe.js"));

const fails = [];
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails.push(name); }

// ---- 1. Phân biệt vuốt ngang và cuộn dọc ----
check("chạm rung tay vài px: chưa quyết", SW.decide(-5, 3, false) === "wait");
check("kéo sang trái rõ ràng: là vuốt", SW.decide(-30, 6, false) === "swipe");
check("kéo dọc: là cuộn, bỏ vuốt", SW.decide(-8, 40, false) === "scroll");
check("kéo chéo nhiều dọc hơn ngang: là cuộn", SW.decide(-20, 25, false) === "scroll");
check("kéo sang phải: không làm gì", SW.decide(30, 2, false) === "ignore");
check("đã vuốt rồi thì cứ theo ngón tay, kể cả lệch dọc", SW.decide(-40, 30, true) === "swipe");
check("bong bóng không đi quá MAX_PULL và không sang phải", SW.pull(-300) === -SW.MAX_PULL && SW.pull(20) === 0);
check("đủ xa mới trích", SW.armed(-SW.SWIPE_AT) && !SW.armed(-SW.SWIPE_AT + 1));

// ---- 2. Gắn vào một DOM giả ----
function El(cls, parent) {
  this.className = cls; this.parentElement = parent || null; this.parentNode = parent || null; this.nodeType = 1;
  this.children = []; this.style = {}; this.listeners = {}; this.scrollWidth = 100; this.clientWidth = 100; this.attrs = {};
  if (parent) parent.children.push(this);
  const self = this;
  this.classList = {
    add: (...c) => { c.forEach((x) => { if (!self.has(x)) self.className += " " + x; }); },
    remove: (...c) => { self.className = self.className.split(" ").filter((x) => !c.includes(x)).join(" "); },
    contains: (c) => self.has(c),
    toggle: (c, on) => { if (on === undefined) on = !self.has(c); if (on) self.classList.add(c); else self.classList.remove(c); return on; },
  };
}
El.prototype.has = function (c) { return this.className.split(" ").includes(c); };
El.prototype.matches = function (sel) {
  return sel.split(",").some((one) => {
    one = one.trim();
    if (one.startsWith(".")) return this.has(one.slice(1).split("[")[0]);
    return this.className.split(" ")[0] === one;    // tag selectors: the first word stands for the tag in this fake DOM
  });
};
El.prototype.closest = function (sel) { for (let e = this; e; e = e.parentElement) if (e.matches(sel)) return e; return null; };
El.prototype.querySelector = function (sel) {
  for (const c of this.children) { if (c.matches(sel)) return c; const f = c.querySelector(sel); if (f) return f; }
  return null;
};
El.prototype.contains = function (x) { for (let e = x; e; e = e.parentElement) if (e === this) return true; return false; };
El.prototype.addEventListener = function (t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); };
El.prototype.removeEventListener = function (t, f) { this.listeners[t] = (this.listeners[t] || []).filter((x) => x !== f); };
El.prototype.appendChild = function (c) { c.parentElement = this; c.parentNode = this; this.children.push(c); return c; };
El.prototype.removeChild = function (c) { this.children = this.children.filter((x) => x !== c); c.parentNode = null; };
El.prototype.setAttribute = function (k, v) { this.attrs[k] = v; };
El.prototype.fire = function (t, ev) { (this.listeners[t] || []).forEach((f) => f(ev)); };

global.document = { createElement: () => new El("span"), querySelector: () => null };
global.getComputedStyle = (el) => ({ overflowX: el.ox || "visible" });
global.navigator = {};
global.setTimeout = (f) => f();

const root = new El("transcript");
function makeMsg(withQuote) {
  const msg = new El("msg msg-javis", root);
  const bubble = new El("bubble", msg);
  const text = new El("p", bubble);
  if (withQuote) new El("msg-act", msg).dataAct = "quote";
  return { msg, bubble, text };
}
const quoted = [];
SW.bind(root, {
  selector: ".msg-javis, .msg-user", bubble: ".bubble",
  can: (el) => !!el.querySelector(".msg-act"),
  run: (el) => quoted.push(el),
});
function swipe(target, path, type) {
  root.fire("pointerdown", { pointerType: type || "touch", target, clientX: 300, clientY: 200 });
  for (const [x, y] of path) root.fire("pointermove", { clientX: 300 + x, clientY: 200 + y });
}

const a = makeMsg(true);
swipe(a.text, [[-20, 2], [-50, 4], [-75, 5]]);
check("bong bóng đi theo ngón tay", a.bubble.style.transform === "translateX(-75px)");
check("đủ xa thì hiện dấu sẵn sàng trích", a.msg.has("is-armed") && a.msg.children.some((c) => c.className === "msg-swipe-mark"));
root.fire("pointerup", {});
check("nhấc tay: trích đúng tin đó", quoted.length === 1 && quoted[0] === a.msg);
check("bong bóng về chỗ cũ, dấu biến mất", a.bubble.style.transform === "" && !a.msg.has("is-swiping")
  && !a.msg.children.some((c) => c.className === "msg-swipe-mark"));

swipe(a.text, [[-20, 2], [-40, 3]]);
root.fire("pointerup", {});
check("vuốt chưa đủ xa: không trích", quoted.length === 1 && a.bubble.style.transform === "");

swipe(a.text, [[-4, 20], [-6, 60]]);
root.fire("pointerup", {});
check("cuộn dọc: không trích, bong bóng không xê dịch", quoted.length === 1 && !a.bubble.style.transform);

swipe(a.text, [[-20, 2], [-80, 4]], "mouse");
root.fire("pointerup", {});
check("chuột: không vuốt (kéo chuột là bôi chữ)", quoted.length === 1);

swipe(a.text, [[-20, 2], [-80, 4]]);
root.fire("pointercancel", {});
check("trình duyệt huỷ cú chạm: không trích", quoted.length === 1 && a.bubble.style.transform === "");

const b = makeMsg(false);
swipe(b.text, [[-20, 2], [-80, 4]]);
root.fire("pointerup", {});
check("tin không có nút Trích dẫn: không vuốt", quoted.length === 1 && !b.bubble.style.transform);

const c = makeMsg(true);
const pre = new El("pre", c.bubble);
pre.scrollWidth = 600; pre.clientWidth = 280; pre.ox = "auto";
const code = new El("code", pre);
swipe(code, [[-20, 2], [-80, 4]]);
root.fire("pointerup", {});
check("chạm trong khối code cuộn ngang: cuộn khối đó, không trích", quoted.length === 1 && !c.bubble.style.transform);

const btn = new El("button", c.bubble);
swipe(btn, [[-20, 2], [-80, 4]]);
root.fire("pointerup", {});
check("chạm bắt đầu trên nút: không vuốt", quoted.length === 1);

// ---- 3. Gắn vào khung chat chính ----
const cr = fs.readFileSync(path.join(D, "chat-reactions.js"), "utf8");
check("khung chat chính gắn vuốt cho tin Javis lẫn tin người dùng",
  /SW\.bind\(root, \{\s*selector: "\.msg-javis, \.msg-user"/.test(cr));
check("vuốt bấm chính nút Trích dẫn của tin (cùng đường với nút)", cr.includes("el.querySelector('.msg-act[data-act=\"quote\"]'); if (b) b.click();"));
const html = fs.readFileSync(path.join(D, "index.html"), "utf8");
check("index.html nạp msg-swipe.js trước chat-reactions.js",
  html.indexOf("msg-swipe.js?v=") > 0 && html.indexOf("/static/msg-swipe.js") < html.indexOf("/static/chat-reactions.js"));
const css = fs.readFileSync(path.join(D, "style.css"), "utf8");
check("máy chạm: tin chỉ để trình duyệt cuộn dọc, chiều ngang cho cú vuốt",
  css.includes("@media (hover: none) { .msg-javis, .msg-user { touch-action: pan-y; } }"));
check("không em dash trong file mới", !/[\u2013\u2014]/.test(fs.readFileSync(path.join(D, "msg-swipe.js"), "utf8")));

if (fails.length) { console.log("\nFAIL " + fails.length + ": " + fails.join(", ")); process.exit(1); }
console.log("\nOK - test_msg_swipe: all pass");
