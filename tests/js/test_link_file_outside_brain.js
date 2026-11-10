/* Full paths to files OUTSIDE the brain become links that open on the owner's computer.

       node tests/js/test_link_file_outside_brain.js

   Owner request 2026-11-09: Javis builds teaching decks in ~/Documents and names them in chat, but
   the chat only linked brain paths, so the name was dead text. Now a full path in inline code or a
   markdown link renders as a.jv-flocal; a click POSTs it to /files/open-local. Paths inside the
   brain keep opening in the app, and relative, /files/raw and file:///wiki links keep their old rules.

   The link is drawn only where a click can work: a browser at a loopback address, unless the server says no
   (GET /files/open-local: Docker, a Linux box with no desktop). Anywhere else the path stays the text it was. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
global.currentBrainPath = () => "brain";          // default brain -> name "Brain Default"
const { mdToHtml, localTarget, codeLocalTarget, setLocalOpen } = require(path.join(ROOT, "dashboard", "chat-render.js"));
const CR = fs.readFileSync(path.join(ROOT, "dashboard", "chat-render.js"), "utf8");
const VI = require(path.join(ROOT, "dashboard", "i18n", "vi.json"));
const EN = require(path.join(ROOT, "dashboard", "i18n", "en.json"));

const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra == null ? "" : "  " + extra));
  if (!cond) fails.push(name);
}
const local = (s) => { const r = localTarget(s); return r && r.local; };
const DECK = "/Users/a/Documents/Documents - Minh Minh/Unit 4/06_Vocab_WordForms.html";

check("macOS full path is local", local(DECK) === DECK);
check("~/ path is local", local("~/Downloads/report.pdf") === "~/Downloads/report.pdf");
check("file:// with %20 is local and decoded", local("file:///Users/a/b%20c/x.html") === "/Users/a/b c/x.html");
check("Windows path is local", local("C:\\Users\\q\\a.docx") === "C:/Users/q/a.docx");
check("path inside the brain stays a vault link",
  JSON.stringify(localTarget("/Users/a/Javis OS/brains/Brain Default/wiki/x.md")) === JSON.stringify({ vault: "wiki/x.md" }));
check("relative vault path is not local", localTarget("wiki/x.md") === null);
check("file:///wiki/x.md keeps the old vault rule", localTarget("file:///wiki/x.md") === null);
check("/files/raw link is not local", localTarget("/files/raw?brain=brain&path=x.md") === null);
check("system path is not linked", localTarget("/etc/hosts") === null);
check(".. is refused", localTarget("/Users/a/../../etc/passwd") === null);
check("inline command with flags is not linked", codeLocalTarget("/Users/a/bin/tool --x") === null);
check("inline folder with trailing / is linked", (codeLocalTarget("/Users/a/_build/bak/") || {}).local === "/Users/a/_build/bak/");

// Node has no `location`: the page is not on the machine, so nothing is drawn as a local link.
const h0 = mdToHtml("Xong: `" + DECK + "` va [Navigator](</Users/a/Documents/U4/00_Navigator.html>)");
check("away from the machine: no local link at all", !/jv-flocal/.test(h0), h0);
check("away from the machine: the whole path stays readable in the code", h0.includes("<code>" + DECK + "</code>"), h0);

setLocalOpen(true);     // from here on: a browser on the machine that runs Javis
const h1 = mdToHtml("Xong: `" + DECK + "`");
check("inline code renders a jv-flocal link", /class="jv-flocal jv-fcode"/.test(h1) && h1.includes('data-local-path="' + DECK + '"'), h1);
check("inline code shows just the file name", h1.includes("<code>06_Vocab_WordForms.html</code>"), h1);
const h2 = mdToHtml("[Navigator](</Users/a/Documents/U4/00_Navigator.html>)");
check("markdown link with <...> renders a jv-flocal link", /class="jv-flocal"/.test(h2) && />Navigator<\/a>/.test(h2), h2);
const h3 = mdToHtml("`wiki/log.md` and [x](file:///home/u/brains/Brain%20Default/wiki/a.md)");
check("brain links unchanged", !/jv-flocal/.test(h3) && /data-vault-path="wiki\/a.md"/.test(h3), h3);

// ---- where the link is offered ----
function page(hostname, answer, stored) {
  const asked = [];
  const store = Object.assign({}, stored || {});
  global.location = { hostname: hostname };
  global.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; } };
  global.fetch = (url) => { asked.push(url); return Promise.resolve({ ok: true, json: () => Promise.resolve(answer) }); };
  setLocalOpen(null);
  return { asked: asked, store: store };
}
const settle = () => new Promise((r) => setImmediate(() => setImmediate(r)));
const linked = () => /jv-flocal/.test(mdToHtml("`" + DECK + "`"));

(async function () {
  let pg = page("javis.example.com", { available: true });
  check("on a domain: no link, and the server is not asked", !linked() && pg.asked.length === 0);
  pg = page("192.168.1.20", { available: true });
  check("on a LAN address: no link", !linked() && pg.asked.length === 0);

  pg = page("localhost", { available: true });
  check("on localhost: link drawn at once", linked());
  check("on localhost: the server is asked once, however many paths are drawn",
    linked() && pg.asked.length === 1 && pg.asked[0] === "/files/open-local", JSON.stringify(pg.asked));
  await settle();
  check("the server agrees: links stay", linked() && !("jv_local_open_off" in pg.store));

  pg = page("127.0.0.1", { available: false });
  check("on 127.0.0.1 before the answer: link drawn", linked());
  await settle();
  check("the server says no (Docker, no desktop): later paths are plain text", !linked());
  check("the no is remembered for the next visit", pg.store.jv_local_open_off === "1");

  pg = page("localhost", { available: false }, { jv_local_open_off: "1" });
  check("next visit after a no: plain text from the first paint", !linked());
  pg = page("localhost", { available: true }, { jv_local_open_off: "1" });
  linked();
  await settle();
  check("a yes later (moved out of Docker) brings the links back", linked() && !("jv_local_open_off" in pg.store));

  pg = page("localhost", { nonsense: 1 });
  linked();
  await settle();
  check("an answer with no verdict changes nothing", linked());

  delete global.location; delete global.localStorage; delete global.fetch;
  finish();
})();

check("click handler posts to /files/open-local", /closest\("a\.jv-flocal"\)/.test(CR) && /"\/files\/open-local"/.test(CR));
for (const k of ["crender.open_local", "crender.opened_local", "crender.revealed_local", "crender.open_local_fail"]) {
  check("i18n key " + k + " in vi and en", !!VI[k] && !!EN[k]);
}

function finish() {
  if (fails.length) { console.log("\nFAIL - " + fails.length + " check(s)"); process.exit(1); }
  console.log("\nOK - test_link_file_outside_brain: all pass");
}
