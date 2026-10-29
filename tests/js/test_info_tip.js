// Nút "i" mở lời giải thích trong tab Cài đặt của trợ lý (0.175.0).
//   node tests/js/test_info_tip.js
// Chủ repo 16/10/2026: "ở phần cài đặt nhiều thông tin quá, có thể ẩn để gọn gàng lại và có một nút nhỏ nào đó kiểu nút i
// thì sẽ mở ra các thông tin để đọc không?". File này canh: câu giải thích ẩn mặc định, nút i mở đúng khối của mục mình (kể cả
// khi nút nằm trong thẻ con của tiêu đề), và các mục của tab Cài đặt thật sự đưa giải thích vào khối đó.
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "..", "..");
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
let fails = 0;
function check(name, cond, them) {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + String(them).slice(0, 300) + "]" : ""));
  if (!cond) fails++;
}

// DOM tối thiểu: phần tử có cha, anh em kế tiếp, lớp, thuộc tính; đủ để info-tip.js mở và đóng popup.
const attached = new Set();
function el(cls) {
  const e = { cls: new Set(cls ? cls.split(" ") : []), kids: [], parentElement: null, attrs: {}, hidden: false, style: {}, innerHTML: "",
    listeners: {}, focused: 0, offsetWidth: 300, offsetHeight: 120,
    classList: { contains: (c) => e.cls.has(c), toggle: (c, on) => (on ? e.cls.add(c) : e.cls.delete(c)), add: (c) => e.cls.add(c),
      remove: (c) => e.cls.delete(c) },
    get className() { return [...e.cls].join(" "); }, set className(v) { e.cls = new Set(v.split(" ")); },
    setAttribute: (k, v) => { e.attrs[k] = v; }, getAttribute: (k) => e.attrs[k],
    addEventListener: (k, f) => { e.listeners[k] = f; },
    append(...cs) { cs.forEach((c) => { c.parentElement = e; e.kids.push(c); attached.add(c); }); return e; },
    remove() { attached.delete(e); }, focus() { e.focused++; },
    getBoundingClientRect: () => ({ left: 100, top: 200, right: 120, bottom: 220, width: 20, height: 20 }),
    querySelector(sel) { if (sel === ".info-pop-x") { e._x = e._x || el("info-pop-x"); return e._x; } return null; },
    get nextElementSibling() { const p = e.parentElement; if (!p) return null; return p.kids[p.kids.indexOf(e) + 1] || null; },
    closest(sel) { let x = e; while (x) { if (sel === "button.info-i" && x.cls.has("info-i")) return x; if (sel === ".info-pop" && x.cls.has("info-pop")) return x; x = x.parentElement; } return null; } };
  return e;
}
const docListeners = {};
let phone = false;
const bodyEl = el("body");
bodyEl.appendChild = (c) => { attached.add(c); return c; };
bodyEl.contains = (c) => attached.has(c);
const ctx = { window: { innerWidth: 1280, innerHeight: 800, matchMedia: () => ({ matches: phone }), addEventListener() {} },
  document: { addEventListener: (k, f) => { docListeners[k] = f; }, createElement: () => el(""), body: bodyEl } };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(ROOT, "dashboard", "info-tip.js"), "utf8"), ctx);
const JI = ctx.window.JavisInfo;
const onClick = docListeners.click, onKey = docListeners.keydown;
check("có JavisInfo.btn / body và trình nghe bấm, phím", JI && typeof JI.btn === "function" && typeof JI.body === "function" && !!onClick && !!onKey);
const b = JI.btn('Xem <giải thích>');
check("nút: là button, nhãn đọc được, nhãn được escape, aria-expanded=false",
  /^<button type="button" class="info-i" aria-expanded="false"/.test(b) && b.includes('aria-label="Xem &lt;giải thích&gt;"'), b);
check("khối giải thích ẩn mặc định", JI.body("x") === '<div class="info-body" hidden>x</div>');

// Nút nằm trong span tiêu đề của một hàng tiêu đề; khối giải thích là anh em của HÀNG, không phải của span.
const sec = el("sec"), head = el("rsa-head"), title = el("rsa-title"), btn = el("info-i"), state = el("rsa-state");
const body = el("info-body"), body2 = el("info-body");
body.hidden = true; body2.hidden = true; body.innerHTML = "Giải thích <b>đúng mục</b>"; body2.innerHTML = "mục khác";
btn.attrs["aria-label"] = "Xem giải thích";
title.append(btn); head.append(title, state); sec.append(head, body, el("x"), el("sec2"), body2);
attached.add(btn);
const ev = (t) => ({ target: t, preventDefault() {}, stopPropagation() {} });
const pops = () => [...attached].filter((x) => x.cls.has("info-pop"));
onClick(ev(btn));
check("bấm i (0.399.0): mở POPUP với đúng khối của mục, khối trong trang vẫn ẩn", pops().length === 1 &&
  pops()[0].innerHTML.includes("Giải thích <b>đúng mục</b>") && !pops()[0].innerHTML.includes("mục khác") && body.hidden === true);
check("popup: là hộp thoại mang nhãn của nút, có nút đóng, nhận focus, aria-expanded=true",
  pops()[0].attrs.role === "dialog" && pops()[0].attrs["aria-label"] === "Xem giải thích" && /class="info-pop-x"/.test(pops()[0].innerHTML) &&
  pops()[0].focused === 1 && btn.attrs["aria-expanded"] === "true");
check("máy tính: popup đặt ngay dưới nút, không phải bảng dưới đáy", pops()[0].style.top === "228px" && pops()[0].style.left === "8px" &&
  !pops()[0].cls.has("sheet"), JSON.stringify(pops()[0].style));
onClick(ev(btn));
check("bấm lần nữa: đóng popup", pops().length === 0 && btn.attrs["aria-expanded"] === "false");
onClick(ev(btn));
onKey({ key: "Escape", stopPropagation() {} });
check("Esc đóng popup và trả focus về nút", pops().length === 0 && btn.focused === 1);
onClick(ev(btn));
onClick(ev(el("x")));
check("bấm ra ngoài: đóng popup", pops().length === 0);
phone = true;
onClick(ev(btn));
check("điện thoại: popup thành bảng từ dưới lên", pops().length === 1 && pops()[0].cls.has("sheet"));
JI.close(false);

// Các mục của tab Cài đặt: câu giải thích nằm trong khối i, ngoài mặt không còn.
ctx.window.JavisInfo = JI;
global.window = ctx.window;
const RAX = require(path.join(ROOT, "dashboard", "resonance-agent.js"));
const ph = RAX.panelHtml({ slug: "a", status: "active", enabled: true }, "ready", [], []);
const ngoai = ph.split('<div class="info-body" hidden>')[0];
check("Auto: đầu mục có nút i, mô tả và lưu ý nằm trong khối ẩn",
  ph.includes('class="info-i"') && ph.includes(vi["resonance.auto_desc"]) && !ngoai.includes(vi["resonance.auto_desc"])
  && !ngoai.includes(vi["resonance.auto_not_full"]), ngoai);
const PU = require(path.join(ROOT, "dashboard", "agent-pulse.js"));
const hp = PU.panelHtml({ agent_key: "a", resonance: true, contexts: [], aggregate: { max_tier: 1 } }, {});
check("Nhịp chủ động: giới thiệu và lưu ý mức nhanh nhất nằm trong khối ẩn, ô chọn vẫn ở ngoài",
  hp.includes('class="info-i"') && /<div class="info-body" hidden>[\s\S]*pulse-note/.test(hp) && hp.includes("pulse-max-sel")
  && hp.indexOf(vi["pulse.intro"]) > hp.indexOf('class="info-body"'), hp);
check("chuỗi nút có ở cả hai thứ tiếng", !!vi["info.more"] && !!en["info.more"]);
const css = fs.readFileSync(path.join(ROOT, "dashboard", "style.css"), "utf8");
check("CSS: khối ẩn thật sự ẩn, nút có vùng chạm 44px trên cảm ứng",
  /\.info-body\[hidden\] \{ display: none; \}/.test(css) && /\.info-i::after \{ content: ""; position: absolute; inset: -12px; \}/.test(css));
check("CSS: popup nổi trên mọi hộp thoại (3210), điện thoại là bảng từ dưới lên có nền mờ",
  /\.info-pop \{ position: fixed; z-index: 3401;/.test(css) && /\.info-pop\.sheet \{ left: 0; right: 0; bottom: 0;/.test(css) &&
  /\.info-pop-bg \{ position: fixed; inset: 0; z-index: 3400;/.test(css));
const html = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");
check("index.html nạp info-tip.js sau icons.js và trước các bảng Cài đặt",
  html.indexOf("/static/info-tip.js") > html.indexOf("/static/icons.js") && html.indexOf("/static/info-tip.js") < html.indexOf("/static/resonance-agent.js"));

console.log(fails ? `\n${fails} FAIL` : "\nOK");
process.exit(fails ? 1 : 0);
