/* The sign-in screen must fully hide the dashboard behind it.

       node tests/js/test_login_screen_opaque.js

   Reported 2026-10-03: the sign-in box sat over the dashboard behind a translucent scrim and a
   6px blur, so the app layout was still readable underneath (most visibly in the light theme,
   where the scrim alpha is 0.34). The server already answers 401 to every data endpoint for an
   anonymous client, so no user data was exposed; this only closes the visual leak.

   The fix is a solid backdrop on #authOverlay alone. Other modals keep the scrim on purpose:
   they are opened by a signed-in user who is meant to see the page behind them. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "style.css"), "utf8");
const HTML = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");

const fails = [];
const check = (name, cond, more) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && more ? "  [" + more + "]" : ""));
  if (!cond) fails.push(name);
};

// Every declaration block whose selector list mentions #authOverlay.
const blocks = [];
const re = /([^{}]*#authOverlay[^{}]*)\{([^{}]*)\}/g;
for (let m; (m = re.exec(CSS));) blocks.push({ sel: m[1].trim(), body: m[2] });
const all = blocks.map((b) => b.body).join("\n");

check("the stylesheet has a rule for #authOverlay", blocks.length > 0);
check("its backdrop is the solid page colour, not the translucent scrim",
  /background:\s*var\(--bg\)/.test(all) && !/--scrim/.test(all), all.trim());
// Read the declared value rather than lookahead-matching it: `\s*` backtracks to zero spaces and
// would make `(?!none)` match "backdrop-filter: none" itself.
const filters = [...all.matchAll(/backdrop-filter:\s*([^;}]+)/g)].map((m) => m[1].trim());
check("it does not blur: a blur lets the layout show through",
  filters.every((v) => v === "none"), filters.join(" | "));
check("the blur is switched off explicitly, so the shared .modal-overlay blur cannot come back",
  filters.length > 0 && filters.every((v) => v === "none"), filters.join(" | "));

// The solid colour only hides the page if --bg itself has no alpha, in both themes.
const bgValues = [...CSS.matchAll(/(^|[\s;{])--bg:\s*([^;]+);/g)].map((m) => m[2].trim());
check("--bg is defined for the dark and the light theme", bgValues.length >= 2, bgValues.join(" | "));
check("every --bg value is an opaque hex colour",
  bgValues.length > 0 && bgValues.every((v) => /^#[0-9a-f]{6}$/i.test(v)), bgValues.join(" | "));

// Scope: the shared modal rule must keep its scrim, or every other dialog loses the page behind it.
const shared = (CSS.match(/\.modal-overlay\s*\{[^}]*\}/) || [""])[0];
check("other modals keep the translucent scrim", /background:\s*var\(--scrim\)/.test(shared), shared);

// The element the rule targets must exist, and the overlay must still be a modal on top.
check("index.html still has the #authOverlay element", /id="authOverlay"/.test(HTML));
check("#authOverlay keeps the modal-overlay class so it keeps its stacking and layout",
  /class="modal-overlay"\s+id="authOverlay"/.test(HTML));

if (fails.length) {
  console.log("\n" + fails.length + " FAILED");
  process.exit(1);
}
console.log("\nall ok");
