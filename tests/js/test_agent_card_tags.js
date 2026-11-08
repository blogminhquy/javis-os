// 2026-11-08 (owner): an assistant card on the Partners page carries a second line under the name, beside the avatar:
// the System badge (Javis Core) and the assistant's tags. The line ends where the time / Auto corner starts, so
// fitCardTags keeps as many WHOLE chips as fit and folds the rest into "+n".
//
//     node tests/js/test_agent_card_tags.js
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const root = path.join(__dirname, "..", "..");
const src = fs.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

// The chip, sub line and fit helpers, run as they are in the page.
const part = src.slice(src.indexOf("  var CHIP_TOI_DA = 3;"), src.indexOf("  // HTML của MỘT hàng."));
const agents = [{ slug: "w", name: "Writer", tags: ["Marketing", "Content writing", "Email"] },
                { slug: "core", name: "Javis Core", system: true, tags: [] }];
const ctx = vm.createContext({ t: (k, o) => (k === "ws.tag_more" ? "+" + o.n : k), esc: (s) => String(s),
  tagsCua: (x) => x.tags || [], danhSach: () => agents, S: {} });
vm.runInContext(part + "\nglobalThis.api = { cardSubHtml, fitCardTags };", ctx);
const { cardSubHtml, fitCardTags } = ctx.api;

check("an assistant with tags: one sub line with two chips and +1",
  cardSubHtml(agents[0], false) === '<span class="ws-item-sub"><span class="ws-tags" aria-label="ws.tags_aria">' +
    '<span class="ws-tag" title="Marketing">Marketing</span><span class="ws-tag" title="Content writing">Content writing</span>' +
    '<span class="ws-tag ws-tag-more" title="Email">+1</span></span></span>', cardSubHtml(agents[0], false));
check("Javis Core without tags: the System badge alone on the line",
  cardSubHtml(agents[1], true) === '<span class="ws-item-sub"><span class="ws-sys">ws.system_badge</span></span>');
check("no badge and no tags: no line at all", cardSubHtml({ slug: "z", name: "Z" }, false) === "");

// A fake row: each chip is as wide as its text in px (8px a letter + 14px padding), 4px gaps, and the time / Auto
// corner starts `room + 8` px to the right of where the line starts.
function fakeRow(slug, room) {
  const sub = { style: {}, cls: new Set(), innerHTML: "", clientWidth: 200,
    classList: { add(c) { sub.cls.add(c); }, remove(c) { sub.cls.delete(c); } },
    getBoundingClientRect: () => ({ left: 100 }),
    querySelector(sel) {
      if (sel !== ".ws-tags") return null;
      const chips = (sub.innerHTML.match(/<span class="ws-tag[^"]*"[^>]*>[^<]*<\/span>/g) || [])
        .map((h) => h.replace(/<[^>]+>/g, "").length * 8 + 14);
      const content = chips.reduce((a, b) => a + b, 0) + 4 * Math.max(0, chips.length - 1);
      return { scrollWidth: content, clientWidth: Math.min(content, room) };
    } };
  const wrap = { classList: { contains: (c) => c === "he" && slug === "core" },
    querySelector: (sel) => sel === "[data-slug]" ? { dataset: { slug } }
      : sel === ".ws-item-end" ? { getBoundingClientRect: () => ({ left: 100 + room + 8 }) } : null };
  sub.closest = () => wrap;
  return sub;
}
function fit(room) {
  const sub = fakeRow("w", room);
  sub.innerHTML = cardSubHtml(agents[0], false);
  fitCardTags({ querySelectorAll: () => [sub] });
  return sub;
}
const chipsOf = (sub) => (sub.innerHTML.match(/<span class="ws-tag[^"]*"[^>]*>([^<]*)<\/span>/g) || [])
  .map((h) => h.replace(/<[^>]+>/g, ""));

let s = fit(400);
check("wide column: all three tags show, nothing folded", chipsOf(s).join("|") === "Marketing|Content writing|Email",
  chipsOf(s).join("|"));
check("the line is sized up to the corner, the CSS 104px fallback dropped", s.style.maxWidth === "400px" && s.style.paddingRight === "0");
s = fit(260);
check("medium: two whole chips and +1", chipsOf(s).join("|") === "Marketing|Content writing|+1", chipsOf(s).join("|"));
s = fit(200);
check("a second chip that would be cut is folded, not shown cut", chipsOf(s).join("|") === "Marketing|+2", chipsOf(s).join("|"));
s = fit(110);
check("narrow (the default column): one whole chip and +2, the folded names in its title",
  chipsOf(s).join("|") === "Marketing|+2" && s.innerHTML.includes('title="Content writing, Email"'), chipsOf(s).join("|"));
s = fit(40);
check("very narrow: the first chip still stays (CSS lets only it shrink)", chipsOf(s).join("|") === "Marketing|+2");
check("measuring class is removed after the fit", !s.cls.has("measure"));

const hidden = fakeRow("w", 0);
hidden.clientWidth = 0;
hidden.innerHTML = cardSubHtml(agents[0], false);
const before = hidden.innerHTML;
fitCardTags({ querySelectorAll: () => [hidden] });
check("hidden page (no layout): the row is left as drawn, CSS fallback applies",
  hidden.innerHTML === before && hidden.style.maxWidth === undefined);

const core = fakeRow("core", 300);
core.innerHTML = cardSubHtml(agents[1], true);
const coreBefore = core.innerHTML;
fitCardTags({ querySelectorAll: () => [core] });
check("Javis Core without tags: the badge line is not touched", core.innerHTML === coreBefore);

check("the list refits after each draw and when the column is resized (ResizeObserver)",
  /noiDanhSach\(host\);\s*if \(laTag\) watchCardTags\(host\);/.test(src)
  && /S\.tagRo = new ResizeObserver\(function \(\) \{ fitCardTags\(host\); \}\);/.test(src));

if (fails) { console.log("\nFAIL " + fails); process.exit(1); }
console.log("\nOK test_agent_card_tags");
