/* Team list bar on one row (2026-11-19). Owner: "tạo team với nhập team ở trên 1 hàng thôi đừng xuống dòng 2 hàng nhìn
   rất lãng phí không gian, nếu kéo về thu nhỏ quá thì chỉ hiện icon thôi".

       node tests/js/test_team_list_bar_mot_hang.js */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const js = fs.readFileSync(path.join(ROOT, "dashboard", "teams.js"), "utf8");
let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

check("the bar never wraps", /\.tm-list-bar \{ flex-wrap: nowrap; \}/.test(css));
check("a label never breaks inside its button", /\.tm-list-bar \.ws-btn \{ white-space: nowrap; flex: none; \}/.test(css));
check("icon-only mode hides both labels",
  /\.tm-list-bar\.tm-chi-icon \.tm-new, \.tm-list-bar\.tm-chi-icon \.tm-import \{ font-size: 0;/.test(css));
check("the folded strip shows Import as an icon too", /\.tm-page\.tm-mini \.tm-new, \.tm-page\.tm-mini \.tm-import \{ font-size: 0;/.test(css));
check("the rule after it is the last word on the bar (not overridden by the phone rule that wrapped it)",
  css.lastIndexOf(".tm-list-bar { flex-wrap: nowrap; }") > css.lastIndexOf(".tm-list-bar { flex-wrap: wrap"));
check("teams.js measures the bar and toggles icon-only", /function fitListBar\(\)/.test(js) &&
  /bar\.scrollWidth > bar\.clientWidth \+ 1\) bar\.classList\.add\("tm-chi-icon"\)/.test(js));
check("it re-measures when the list column is resized", /new ResizeObserver\(fitListBar\)/.test(js) && /S\.barRO\.disconnect\(\)/.test(js));
check("Create keeps its name on hover when only the icon shows", /class="ws-btn tm-new" title="/.test(js));

// The measuring rule itself, on a fake bar.
const m = js.match(/function fitListBar\(\) \{[\s\S]*?\n  \}/);
function fakeBar(client, scroll) {
  const cls = new Set();
  return { clientWidth: client, scrollWidth: scroll,
           classList: { add: (c) => cls.add(c), remove: (c) => cls.delete(c), contains: (c) => cls.has(c) } };
}
function run(bar) {
  const S = { el: { querySelector: () => bar } };
  new Function("S", m[0] + "\nfitListBar();")(S);
  return bar.classList.contains("tm-chi-icon");
}
check("room for both labels: text stays", run(fakeBar(264, 264)) === false);
check("too narrow: icons only", run(fakeBar(200, 236)) === true);
const b = fakeBar(200, 236); run(b); b.clientWidth = 300; b.scrollWidth = 300;
check("widened again: text comes back", run(b) === false);
check("a hidden list (width 0) is left alone", run(fakeBar(0, 0)) === false);

console.log(fails ? "\nFAIL - test_team_list_bar_mot_hang" : "\nOK - test_team_list_bar_mot_hang: all pass");
process.exit(fails ? 1 : 0);
