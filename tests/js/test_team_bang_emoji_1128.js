/* Trang Team trên điện thoại (chủ dự án, 28/11/2026, kèm ảnh chụp):

       node tests/js/test_team_bang_emoji_1128.js

   1. Giữ một tin để mở hàng emoji và thẻ Trả lời / Sao chép / Ghim, rồi chạm ra ngoài: thẻ không tắt, màn
      hình như bị đơ. Nguyên nhân: trang Team vẽ lại danh sách tin trong lúc ngón tay đầu còn đặt trên tin, ô
      tin cũ rời trang nên sự kiện nhấc ngón đó không bao giờ tới document. msg-press.js vẫn tưởng ngón đầu
      còn đang trượt trên hàng emoji, nên cú chạm ra ngoài bị coi là "nhấc ngón sau khi trượt", bị chặn
      (preventDefault) và không thành cú bấm đóng thẻ. Nay một cú chạm mới khi thẻ đang mở nghĩa là ngón đầu
      đã nhấc: hết trượt, cú chạm đó là cú bấm bình thường. Chạm vào vùng tối thì đóng ngay khi nhấc ngón,
      không chờ cú bấm trình duyệt có thể không gửi.
   2. Nút "Ghim làm quyết định" xuống ba dòng trong thẻ. Chỉ ghi "Ghim"; câu dài vẫn ở chú thích khi rê chuột.

   Chạy được trên bản cũ bằng biến JAVIS_ROOT (thấy đỏ trước khi sửa). */
"use strict";
const fs = require("fs");
const path = require("path");

const ROOT = process.env.JAVIS_ROOT || path.join(__dirname, "..", "..");
const D = path.join(ROOT, "dashboard");
const fails = [];
function check(name, ok, extra) {
  console.log((ok ? "PASS " : "FAIL ") + name + (ok || !extra ? "" : "  " + extra));
  if (!ok) fails.push(name);
}

// ───────── DOM giả tối thiểu, đủ cho msg-press.js ─────────
function Cls(el) {
  const list = () => String(el.className || "").split(/\s+/).filter(Boolean);
  return {
    add(c) { const l = list(); if (!l.includes(c)) l.push(c); el.className = l.join(" "); },
    remove(c) { el.className = list().filter((x) => x !== c).join(" "); },
    toggle(c, on) { if (on === undefined) on = !list().includes(c); if (on) this.add(c); else this.remove(c); return on; },
    contains(c) { return list().includes(c); },
  };
}
function El(tag, cls, attrs) {
  this.tagName = String(tag || "div").toUpperCase();
  this.nodeType = 1;
  this.className = cls || "";
  this.attrs = Object.assign({}, attrs || {});
  this.children = [];
  this.parentNode = null;
  this.listeners = {};
  this.style = {};
  this.classList = Cls(this);
}
El.prototype.matches = function (sel) {
  return sel.split(",").map((s) => s.trim()).some((s) => {
    if (s[0] === ".") return this.classList.contains(s.slice(1));
    if (s[0] === "[") return Object.prototype.hasOwnProperty.call(this.attrs, s.slice(1, -1));
    return this.tagName === s.toUpperCase();
  });
};
El.prototype.closest = function (sel) {
  for (let n = this; n && n.nodeType === 1; n = n.parentNode) if (n.matches(sel)) return n;
  return null;
};
El.prototype.querySelector = function (sel) {
  for (const c of this.children) { if (c.matches(sel)) return c; const d = c.querySelector(sel); if (d) return d; }
  return null;
};
El.prototype.contains = function (o) { for (let n = o; n; n = n.parentNode) if (n === this) return true; return false; };
El.prototype.appendChild = function (c) { c.parentNode = this; this.children.push(c); return c; };
El.prototype.insertBefore = function (c, ref) {
  c.parentNode = this;
  const i = ref ? this.children.indexOf(ref) : -1;
  if (i < 0) this.children.push(c); else this.children.splice(i, 0, c);
  return c;
};
El.prototype.remove = function () {
  if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((x) => x !== this);
  this.parentNode = null;
};
El.prototype.hasAttribute = function (k) { return Object.prototype.hasOwnProperty.call(this.attrs, k); };
El.prototype.getAttribute = function (k) { return this.hasAttribute(k) ? this.attrs[k] : null; };
El.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
El.prototype.removeAttribute = function (k) { delete this.attrs[k]; };
El.prototype.addEventListener = function (type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); };
El.prototype.removeEventListener = function (type, fn) {
  this.listeners[type] = (this.listeners[type] || []).filter((x) => x !== fn);
};
El.prototype.getBoundingClientRect = function () { return { top: 0, left: 0, width: 0, height: 0, bottom: 0 }; };
Object.defineProperty(El.prototype, "firstChild", { get() { return this.children[0] || null; } });
Object.defineProperty(El.prototype, "nextSibling", {
  get() { const p = this.parentNode; return p ? p.children[p.children.indexOf(this) + 1] || null : null; },
});
Object.defineProperty(El.prototype, "offsetWidth", { get() { return 300; } });
Object.defineProperty(El.prototype, "offsetHeight", { get() { return 58; } });
Object.defineProperty(El.prototype, "offsetTop", { get() { return 600; } });
// innerHTML của lớp phủ: dựng đúng ba phần msg-press.js cần (vùng tối, hàng emoji, thẻ hành động).
Object.defineProperty(El.prototype, "innerHTML", {
  get() { return this._html || ""; },
  set(h) {
    this._html = h;
    this.children = [];
    if (h.includes('class="mp-scrim"')) this.appendChild(new El("div", "mp-scrim", { "data-mp-close": "1" }));
    if (h.includes('class="mp-bar"')) {
      const bar = this.appendChild(new El("div", "mp-bar"));
      bar.appendChild(new El("button", "mp-pick", { "data-mp-react": "like" }));
    }
    if (h.includes('class="mp-sheet"')) {
      const sheet = this.appendChild(new El("div", "mp-sheet"));
      sheet.appendChild(new El("button", "mp-act", { "data-mp-act": "0" }));
    }
  },
});

const docListeners = {};
const html = new El("html");
const body = new El("body");
const document = {
  documentElement: html,
  body: body,
  createElement: (tag) => new El(tag),
  addEventListener(type, fn) { (docListeners[type] = docListeners[type] || []).push(fn); },
  removeEventListener(type, fn) { docListeners[type] = (docListeners[type] || []).filter((x) => x !== fn); },
  elementFromPoint: () => null,
};
global.document = document;
global.window = { innerWidth: 390, innerHeight: 800, getComputedStyle: () => ({ borderRadius: "0" }), getSelection: () => null };
// navigator có sẵn trong Node 22 (không có vibrate): msg-press.js bỏ qua rung.

delete require.cache[require.resolve(path.join(D, "msg-press.js"))];
const MP = require(path.join(D, "msg-press.js"));

// Một cú chạm tới document (cả root nếu nằm trong root), như trình duyệt lan sự kiện lên.
function touchEvent(target, touches) {
  return { target, touches, changedTouches: [{ clientX: 100, clientY: 100 }], cancelable: true, prevented: false,
    preventDefault() { this.prevented = true; }, stopPropagation() {} };
}
function fire(type, target, touches, rootEl) {
  const e = touchEvent(target, touches);
  if (rootEl && rootEl.contains(target)) (rootEl.listeners[type] || []).slice().forEach((fn) => fn(e));
  // Ô tin đã rời trang (vẽ lại): sự kiện của nó không lan lên document nữa.
  let attached = false;
  for (let n = target; n; n = n.parentNode) if (n === body) attached = true;
  if (attached) (docListeners[type] || []).slice().forEach((fn) => fn(e));
  return e;
}
// Trình duyệt chỉ gửi cú bấm (click) khi touchend không bị chặn.
function tap(target, rootEl) {
  fire("touchstart", target, [{ clientX: 100, clientY: 100 }], rootEl);
  const end = fire("touchend", target, [], rootEl);
  if (!end.prevented) {
    const layerEl = target.closest(".mp-layer");
    const c = { target, preventDefault() {}, stopPropagation() {} };
    if (layerEl) (layerEl.listeners.click || []).slice().forEach((fn) => fn(c));
  }
  return end;
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const layerOpen = () => !!body.querySelector(".mp-layer");

(async function () {
  const root = new El("div", "tm-msgs");
  body.appendChild(root);
  let msg = root.appendChild(new El("div", "tm-msg tm-msg-agent", { "data-mid": "7" }));
  const bubble = msg.appendChild(new El("div", "tm-bubble"));
  let reacted = null;
  const unbind = MP.bind(root, {
    selector: ".tm-msg", bubble: ".tm-bubble", holdOn: ".tm-rx-btn",
    emoji: [{ value: "like", key: "teams.react.like", emoji: "👍" }],
    canReact: () => true, current: () => "",
    react: (m, v) => { reacted = v; },
    actions: () => [{ icon: "copy", label: "Sao chép", run() {} }],
  });

  // Giữ tin: thẻ mở sau HOLD_MS.
  fire("touchstart", bubble, [{ clientX: 100, clientY: 100 }], root);
  await wait(MP.HOLD_MS + 60);
  check("giữ tin: lớp phủ emoji và thẻ hành động mở ra", layerOpen());

  // Trang Team vẽ lại danh sách (tin mới, trạng thái công việc): ô tin dưới ngón tay rời trang, lần nhấc ngón đầu
  // không bao giờ tới document.
  msg.remove();
  msg = root.appendChild(new El("div", "tm-msg tm-msg-agent", { "data-mid": "7" }));
  fire("touchend", bubble, [], root);
  check("ô tin cũ đã rời trang (tình huống tái hiện lỗi)", !body.contains(bubble));

  await wait(400);
  const scrim = body.querySelector(".mp-scrim");
  tap(scrim, root);
  check("chạm vùng tối một lần là thẻ đóng, không còn treo màn hình", !layerOpen());
  check("đóng thẻ thì trang hết khoá chọn chữ (html.mp-holding)", !html.classList.contains("mp-holding"));
  check("chạm ra ngoài không gửi nhầm cảm xúc", reacted === null);

  // Lần giữ thứ hai, vẫn trượt trên hàng emoji như cũ: nhấc trên emoji là thả cảm xúc.
  const bubble2 = msg.appendChild(new El("div", "tm-bubble"));
  fire("touchstart", bubble2, [{ clientX: 100, clientY: 100 }], root);
  await wait(MP.HOLD_MS + 60);
  check("giữ lần hai: thẻ mở lại", layerOpen());
  const pickBtn = body.querySelector(".mp-pick");
  document.elementFromPoint = () => pickBtn;
  fire("touchmove", bubble2, [{ clientX: 110, clientY: 40 }], root);
  fire("touchend", bubble2, [], root);
  document.elementFromPoint = () => null;
  check("trượt ngón đầu lên emoji rồi nhấc: vẫn thả đúng cảm xúc", reacted === "like" && !layerOpen());

  // Thẻ mở, ngón đầu đã nhấc đúng cách, rồi chạm vùng tối: đóng ngay khi nhấc ngón (không chờ click).
  const bubble3 = msg.appendChild(new El("div", "tm-bubble"));
  fire("touchstart", bubble3, [{ clientX: 100, clientY: 100 }], root);
  await wait(MP.HOLD_MS + 60);
  fire("touchend", bubble3, [], root);
  await wait(400);
  const scrim3 = body.querySelector(".mp-scrim");
  fire("touchstart", scrim3, [{ clientX: 100, clientY: 100 }], root);
  fire("touchend", scrim3, [], root);
  check("chạm vùng tối: đóng ngay khi nhấc ngón, kể cả khi trình duyệt không gửi click", !layerOpen());
  unbind();

  // ───────── 2) Nút Ghim chỉ ghi "Ghim" ─────────
  const VI = JSON.parse(fs.readFileSync(path.join(D, "i18n", "vi.json"), "utf8"));
  const EN = JSON.parse(fs.readFileSync(path.join(D, "i18n", "en.json"), "utf8"));
  const TM = fs.readFileSync(path.join(D, "teams.js"), "utf8");
  check("khoá ngắn teams.decision_pin_short: \"Ghim\" / \"Pin\"",
    VI["teams.decision_pin_short"] === "Ghim" && EN["teams.decision_pin_short"] === "Pin");
  check("thẻ giữ tin (msg-press) dùng nhãn ngắn cho nút Ghim",
    /icon: "pin", label: tw\("teams\.decision_pin_short"\)/.test(TM) && !/icon: "pin", label: tw\("teams\.decision_pin"\)/.test(TM));
  check("bảng tin trong danh sách (sheetHtml) cũng dùng nhãn ngắn",
    /"pin", "teams\.decision_pin_short"\)/.test(TM));
  check("chú thích rê chuột vẫn giữ câu đầy đủ \"Ghim làm quyết định\"",
    /title="' \+ esc\(tw\("teams\.decision_pin"\)\)/.test(TM));
  const CSS = fs.readFileSync(path.join(D, "style.css"), "utf8");
  check("nhãn trong thẻ hành động không xuống dòng (một dòng, gọn trong ô)",
    /\.mp-act > span:last-child \{[^}]*white-space: nowrap/.test(CSS));

  if (fails.length) { console.log("\n" + fails.length + " FAIL"); process.exit(1); }
  console.log("\nALL PASS");
})();
