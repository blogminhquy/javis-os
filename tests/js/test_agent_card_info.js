// 2026-11-07, owner: the grey role line under each assistant's name on the Partners list was cut off after a few words
// ("vừa xấu vừa không đọc được thông tin gì cả"). The role now opens whole from an (i) button on the name's row, top
// right, right above the Auto switch; the card itself shows only the name.
//
//     python tests/run.py --js agent_card_info -v
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "..", "..");
const src = fs.readFileSync(path.join(ROOT, "dashboard", "workspace.js"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const infoTip = fs.readFileSync(path.join(ROOT, "dashboard", "info-tip.js"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}
const cut = (from, to) => { const i = src.indexOf(from); return src.slice(i, src.indexOf(to, i + from.length)); };

// The card: no role line for an assistant, workflows keep their group and step count.
const muc = cut("  function mucHtml(x, chon) {", "  function agentInfoHtml(x, tg) {");
check("assistant card draws no role line", /var phu = S\.loai === "agent" \? "" :/.test(muc) && !/x\.role \|\| ""\) :/.test(muc));
check("the small line is drawn only when there is text", /\(phu \? '<small>' \+ esc\(phu\) \+ '<\/small>' : ""\)/.test(muc));
check("the (i) sits outside the select button, last in the wrap", /'<\/button>'\) \+\s*info \+ '<\/div>';/.test(muc));
check("the wrap carries has-info only when there is an (i)", /\(info \? " has-info" : ""\)/.test(muc));

// The (i) itself, rendered with the real info-tip.js.
const ctx = vm.createContext({ window: {} });
vm.runInContext(infoTip, ctx);
ctx.t = (k, v) => (vi[k] || k).replace(/\{(\w+)\}/g, (m, n) => (v && v[n] != null ? v[n] : m));
ctx.esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
vm.runInContext(cut("  function agentInfoHtml(x, tg) {", "  // Nối dây cho các nút vừa vẽ.") + "\nwindow.agentInfoHtml = agentInfoHtml;", ctx);
const h = ctx.window.agentInfoHtml({ slug: "vu", name: "Javis Vũ <b>", role: "Trợ lý chăm khách qua Zalo và Telegram, trả lời 24/7" },
  ["Bán hàng"]);
check("(i) button with a label naming the assistant", h.includes('class="info-i"') && h.includes("Mô tả Javis Vũ &lt;b&gt;"));
check("hidden block holds the whole role, the name and the tags",
  /<div class="info-body" hidden>/.test(h) && h.includes("Trợ lý chăm khách qua Zalo và Telegram, trả lời 24/7")
  && h.includes('<p class="ws-info-name"><strong>Javis Vũ &lt;b&gt;</strong></p>') && h.includes("Bán hàng"));
check("button and block are siblings, so info-tip.js finds the block",
  /^<span class="ws-item-info"><button[^]*<\/button><div class="info-body" hidden>/.test(h));
check("no role and no tags: no (i)", ctx.window.agentInfoHtml({ slug: "x", name: "X", role: "  " }, []) === "");
const ctx2 = vm.createContext({ window: {}, t: ctx.t, esc: ctx.esc });
vm.runInContext(cut("  function agentInfoHtml(x, tg) {", "  // Nối dây cho các nút vừa vẽ.") + "\nwindow.agentInfoHtml = agentInfoHtml;", ctx2);
check("without info-tip.js nothing is drawn (the role stays in the card's tooltip)",
  ctx2.window.agentInfoHtml({ slug: "x", name: "X", role: "R" }, []) === "" && /var title = laAgent \? \[x\.name, x\.role/.test(src));

// Collapsed column: the hover card still shows the role, read from the data now that the row has no small line.
check("mini card falls back to the role", /sub: phu \? phu\.textContent : \(x && x\.role\) \|\| ""/.test(src));

// CSS: top right on the name's row, left of the "..." slot, hidden in the collapsed column, small touch area.
// Owner: "căn dọc phải bằng với công tắc". Switch centre = pill right (8) + pill padding (4) + half the switch (12) = 24px
// from the card's edge; the (i) is 20px wide, so right 14px puts its centre on that line.
const num = (re) => { const m = css.match(re); return m ? Number(m[1]) : NaN; };
const pillRight = num(/\.ws-item-end \{ position: absolute; right: (\d+)px;/);
const pillPadRight = num(/\.ws-item-end > \.ws-auto \{ margin: 0; min-height: 20px; padding: 0 (\d+)px 0 7px;/);
const switchW = num(/\.ws-auto \.toggle-sm \{ width: (\d+)px;/);
const infoRight = num(/\.ws-item-info \{ position: absolute; right: (\d+)px; top: 8px; display: flex; \}/);
const styleCss = fs.readFileSync(path.join(ROOT, "dashboard", "style.css"), "utf8");
const infoWm = styleCss.match(/\n\.info-i \{ position: relative; display: inline-flex; align-items: center; justify-content: center; width: (\d+)px;/);
const infoW = infoWm ? Number(infoWm[1]) : NaN;
check("CSS: (i) centre on the same vertical line as the Auto switch centre",
  pillRight + pillPadRight + switchW / 2 === infoRight + infoW / 2, [pillRight, pillPadRight, switchW, infoRight, infoW].join(","));
check("CSS: the ... moves left of the (i), the name row keeps room for both",
  /\.ws-item-wrap\.has-info > \.ws-item-more \{ right: 36px; \}/.test(css)
  && /\.ws-item-wrap\.has-info \.ws-item-top \{ padding-right: 30px; \}/.test(css));
check("CSS: name on the top line, the Auto row keeps its own space",
  /\.ws-item-wrap\.has-end \.ws-item-text \{ align-self: flex-start; \}/.test(css)
  && /\.ws-item-wrap\.has-end \.ws-item-text > :last-child:not\(\.ws-item-top\) \{ padding-right: 104px; \}/.test(css));
check("CSS: touch area of the (i) does not reach the Auto switch", /\.ws-item-info > \.info-i::after \{ inset: -6px; \}/.test(css));
check("CSS: hidden in the collapsed column", /\.wspage\.ws-mini \.ws-item-info,/.test(css));

check("i18n: label in vi and en", vi["ws.about_agent"] === "Mô tả {ten}" && en["ws.about_agent"] === "About {ten}");

if (fails) { console.log(fails + " failed"); process.exit(1); }
console.log("all ok");
