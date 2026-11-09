/* Full paths to files OUTSIDE the brain become links that open on the owner's computer.

       node tests/js/test_link_file_outside_brain.js

   Owner request 2026-11-09: Javis builds teaching decks in ~/Documents and names them in chat, but
   the chat only linked brain paths, so the name was dead text. Now a full path in inline code or a
   markdown link renders as a.jv-flocal; a click POSTs it to /files/open-local. Paths inside the
   brain keep opening in the app, and relative, /files/raw and file:///wiki links keep their old rules. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
global.currentBrainPath = () => "brain";          // default brain -> name "Brain Default"
const { mdToHtml, localTarget, codeLocalTarget } = require(path.join(ROOT, "dashboard", "chat-render.js"));
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

const h1 = mdToHtml("Xong: `" + DECK + "`");
check("inline code renders a jv-flocal link", /class="jv-flocal jv-fcode"/.test(h1) && h1.includes('data-local-path="' + DECK + '"'), h1);
check("inline code shows just the file name", h1.includes("<code>06_Vocab_WordForms.html</code>"), h1);
const h2 = mdToHtml("[Navigator](</Users/a/Documents/U4/00_Navigator.html>)");
check("markdown link with <...> renders a jv-flocal link", /class="jv-flocal"/.test(h2) && />Navigator<\/a>/.test(h2), h2);
const h3 = mdToHtml("`wiki/log.md` and [x](file:///home/u/brains/Brain%20Default/wiki/a.md)");
check("brain links unchanged", !/jv-flocal/.test(h3) && /data-vault-path="wiki\/a.md"/.test(h3), h3);

check("click handler posts to /files/open-local", /closest\("a\.jv-flocal"\)/.test(CR) && /"\/files\/open-local"/.test(CR));
for (const k of ["crender.open_local", "crender.opened_local", "crender.revealed_local", "crender.open_local_fail"]) {
  check("i18n key " + k + " in vi and en", !!VI[k] && !!EN[k]);
}

if (fails.length) { console.log("\nFAIL - " + fails.length + " check(s)"); process.exit(1); }
console.log("\nOK - test_link_file_outside_brain: all pass");
