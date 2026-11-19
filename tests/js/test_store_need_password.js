// Javis Store: with no sign-in password the page says so and offers a button to the Account page.
//
//     node tests/js/test_store_need_password.js
//
// Owner report 2026-11-17: on a local install with no password the Store stayed empty. Every other page
// is open there, but the Store needs a real session (installing a pack runs someone else's code), and
// none can exist until a password is set. The server now answers `need_password`; this checks the page
// turns that into the server's message plus one button that goes to Account.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

function node(tag) {
  return { tag: tag, children: [], style: {}, appendChild(c) { this.children.push(c); return c; } };
}
const doc = {
  activeElement: null,
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: (tag) => node(tag),
  body: { appendChild() {} },
};
let wentTo = "";
const win = { ic: () => "<svg></svg>", Alpine: { store: () => ({ go(id) { wentTo = id; } }) } };
globalThis.Alpine = win.Alpine;

const REFUSED = { ok: false, need_password: true,
                  error: "Javis Store needs a sign-in password. Set one on the Account page, then sign in." };
new Function("window", "document", "fetch",
  fs.readFileSync(path.join(ROOT, "dashboard", "packs.js"), "utf8"))(
  win, doc, () => Promise.resolve({ json: () => Promise.resolve(REFUSED) }));
const P = win.JavisPacks || {};

check("packs.js exposes render and showNeedPassword",
  typeof P.render === "function" && typeof P.showNeedPassword === "function");

(async () => {
  const msg = node("div");
  const el = { _html: "", firstElementChild: msg,
               set innerHTML(v) { this._html = v; }, get innerHTML() { return this._html; } };
  await P.render(el);
  check("the page shows the server's message", el.innerHTML.includes("needs a sign-in password"));
  const btn = msg.children.find(c => c.tag === "button");
  check("a button is added under the message", !!btn && btn.id === "pkSetPassword");
  check("the button has a label", !!btn && !!btn.textContent);
  if (btn) btn.onclick();
  check("clicking it opens the Account page", wentTo === "account");

  // A refusal WITHOUT need_password (a password exists, the session ran out) adds no button.
  const msg2 = node("div");
  const el2 = { firstElementChild: msg2, innerHTML: "" };
  const P2win = { ic: () => "", Alpine: win.Alpine };
  new Function("window", "document", "fetch",
    fs.readFileSync(path.join(ROOT, "dashboard", "packs.js"), "utf8"))(
    P2win, doc, () => Promise.resolve({ json: () => Promise.resolve({ ok: false, error: "Sign in to Javis to manage packs." }) }));
  await P2win.JavisPacks.render(el2);
  check("with a password set, no Set-a-password button", !msg2.children.some(c => c.tag === "button"));

  // The companion-pack offer after a Zalo QR sign-in says a password is missing instead of "not found".
  const P3win = { ic: () => "", Alpine: win.Alpine };
  new Function("window", "document", "fetch",
    fs.readFileSync(path.join(ROOT, "dashboard", "packs.js"), "utf8"))(
    P3win, doc, () => Promise.resolve({ json: () => Promise.resolve({ ok: false, need_password: true, error: "x" }) }));
  check("installing a companion pack without a password reports need_password",
    (await P3win.JavisPacks.caiGoiKho("javis.zalo")) === "need_password");

  console.log();
  if (fails.length) { console.log("FAIL - test_store_need_password: " + fails.join(", ")); process.exit(1); }
  console.log("OK - test_store_need_password: all pass");
})();
