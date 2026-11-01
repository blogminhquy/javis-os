/* Dropping a file on the main chat (#936).

   Reported on 0.414.0: dragging a file from the computer onto the main chat did nothing, no overlay, no attachment.
   Cause: the Teams page marks #cviewBody data-localdrop (its own drop zone), and renderPage swaps #cviewBody for
   cloneNode(false), which keeps every attribute. The Chat page borrows the chat into that same node, so after one visit
   to Teams the main chat's drop handler treated the whole chat as someone else's drop zone and ignored the file.

   This test guards both halves: the document-level drop handler in app.js still exists and attaches the files, and a
   page swap clears the data-localdrop mark.

   Run: node tests/js/test_main_chat_drop.js */
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(root, "dashboard", f), "utf8");
const app = read("app.js");
const consoleJs = read("console.js");
const html = read("index.html");

const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

// ---- 1. The main chat's drop handler is wired ----
check("index.html still has the drop overlay", /id="dropOverlay"/.test(html));
check("app.js reads the overlay", /document\.getElementById\("dropOverlay"\)/.test(app));
for (const ev of ["dragenter", "dragover", "dragleave", "drop"]) {
  check("app.js listens for " + ev + " on the window", new RegExp('window\\.addEventListener\\("' + ev + '"').test(app));
}
const dropSrc = (app.match(/window\.addEventListener\("drop", \(e\) => \{[\s\S]*?\n\}\);/) || [""])[0];
check("the drop handler leaves data-localdrop zones alone", /if \(inLocalDrop\(e\)\) return;/.test(dropSrc));
check("the drop handler attaches the files like the paperclip", /uploadFile\(f\)/.test(dropSrc));

// ---- 2. A page swap does not carry the Teams page's drop mark ----
const renderSrc = (consoleJs.match(/async function renderPage\(id\) \{[\s\S]*?\n  \}\n/) || [""])[0];
check("found renderPage", renderSrc.length > 0);
const cloneAt = renderSrc.indexOf("el.cloneNode(false)");
const clearAt = renderSrc.indexOf('el.removeAttribute("data-localdrop")');
check("renderPage clears data-localdrop on the fresh #cviewBody", clearAt > 0);
check("... right after the clone, before any page renders", cloneAt > 0 && clearAt > cloneAt
  && renderSrc.indexOf('if (id === "chat")') > clearAt);

// ---- 3. Run the swap on a stub DOM: the mark does not survive ----
if (cloneAt > 0 && clearAt > cloneAt) {
  const attrs = new Map([["id", "cviewBody"], ["class", "cview-body"], ["data-localdrop", ""]]);
  const node = (a) => ({
    attrs: new Map(a),
    cloneNode() { return node(this.attrs); },
    removeAttribute(k) { this.attrs.delete(k); },
    hasAttribute(k) { return this.attrs.has(k); },
    parentNode: { replaceChild() {} },
  });
  let el = node(attrs);
  // The exact lines from renderPage, between the clone and the clear.
  const lines = renderSrc.slice(renderSrc.indexOf("const fresh"), clearAt) + 'el.removeAttribute("data-localdrop");';
  el = new Function("el", lines.replace(/\/\/[^\n]*/g, "") + "\nreturn el;")(el);
  check("after a swap the new node keeps its id", el.hasAttribute("id"));
  check("after a swap the new node has no data-localdrop", !el.hasAttribute("data-localdrop"));
}

// ---- 4. The Teams page still marks itself, so its own drop keeps working ----
check("teams.js still marks its page data-localdrop while it renders", /el\.setAttribute\("data-localdrop", ""\)/.test(read("teams.js")));

if (fails.length) { console.log("\n" + fails.length + " FAIL"); process.exit(1); }
console.log("\nAll passed.");
