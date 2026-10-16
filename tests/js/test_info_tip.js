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

// DOM tối thiểu: phần tử có cha, anh em kế tiếp, lớp, thuộc tính.
function el(cls) {
  const e = { cls: new Set(cls ? cls.split(" ") : []), kids: [], parentElement: null, attrs: {}, hidden: false,
    classList: { contains: (c) => e.cls.has(c), toggle: (c, on) => (on ? e.cls.add(c) : e.cls.delete(c)) },
    setAttribute: (k, v) => { e.attrs[k] = v; }, getAttribute: (k) => e.attrs[k],
    append(...cs) { cs.forEach((c) => { c.parentElement = e; e.kids.push(c); }); return e; },
    get nextElementSibling() { const p = e.parentElement; if (!p) return null; return p.kids[p.kids.indexOf(e) + 1] || null; },
    closest(sel) { let x = e; while (x) { if (sel === "button.info-i" && x.cls.has("info-i")) return x; x = x.parentElement; } return null; } };
  return e;
}
let onClick = null;
const ctx = { window: {}, document: { addEventListener: (k, f) => { if (k === "click") onClick = f; } } };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(ROOT, "dashboard", "info-tip.js"), "utf8"), ctx);
const JI = ctx.window.JavisInfo;
check("có JavisInfo.btn / body và trình nghe bấm", JI && typeof JI.btn === "function" && typeof JI.body === "function" && !!onClick);
const b = JI.btn('Xem <giải thích>');
check("nút: là button, nhãn đọc được, nhãn được escape, aria-expanded=false",
  /^<button type="button" class="info-i" aria-expanded="false"/.test(b) && b.includes('aria-label="Xem &lt;giải thích&gt;"'), b);
check("khối giải thích ẩn mặc định", JI.body("x") === '<div class="info-body" hidden>x</div>');

// Nút nằm trong span tiêu đề của một hàng tiêu đề; khối giải thích là anh em của HÀNG, không phải của span.
const sec = el("sec"), head = el("rsa-head"), title = el("rsa-title"), btn = el("info-i"), state = el("rsa-state");
const body = el("info-body"), body2 = el("info-body");
body.hidden = true; body2.hidden = true;
title.append(btn); head.append(title, state); sec.append(head, body, el("x"), el("sec2"), body2);
const ev = { target: btn, preventDefault() {}, stopPropagation() {} };
onClick(ev);
check("bấm i: mở khối giải thích đầu tiên sau tiêu đề, đánh dấu aria-expanded", body.hidden === false && btn.attrs["aria-expanded"] === "true"
  && body2.hidden === true);
onClick(ev);
check("bấm lần nữa: đóng lại", body.hidden === true && btn.attrs["aria-expanded"] === "false");

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
const html = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");
check("index.html nạp info-tip.js sau icons.js và trước các bảng Cài đặt",
  html.indexOf("/static/info-tip.js") > html.indexOf("/static/icons.js") && html.indexOf("/static/info-tip.js") < html.indexOf("/static/resonance-agent.js"));

console.log(fails ? `\n${fails} FAIL` : "\nOK");
process.exit(fails ? 1 : 0);
