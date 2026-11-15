// The Team chat's file picker is put IN the page before it opens and stays there until the pick is done. Owner,
// 2026-11-15, on an iPhone: several photos picked in a team chat attached nothing. The input was clicked without
// joining the page, so iOS Safari could drop it while it prepared the photos and its change event never fired.
//
//     node tests/js/test_team_file_picker.js
"use strict";
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const src = fs.readFileSync(path.join(D, "teams.js"), "utf8");
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

// A tiny DOM: enough for one <input type="file"> and document.body.
const log = [];
function fakeInput() {
  const on = {};
  const el = {
    tagName: "INPUT", type: "", accept: "", multiple: false, className: "", style: {}, files: [], parentNode: null,
    addEventListener: (ev, fn) => { (on[ev] = on[ev] || []).push(fn); },
    fire: (ev) => (on[ev] || []).forEach((fn) => fn({ target: el })),
    click: () => log.push(["click", el, el.parentNode === body]),
  };
  return el;
}
const body = {
  kids: [],
  appendChild(el) { el.parentNode = body; this.kids.push(el); log.push(["append", el]); return el; },
  removeChild(el) { this.kids = this.kids.filter((k) => k !== el); el.parentNode = null; log.push(["remove", el]); return el; },
};
global.document = { body, createElement: (tag) => (tag === "input" ? fakeInput() : {}) };

const T = require(path.join(D, "teams.js"));
check("pickFiles is exported for tests", typeof T.pickFiles === "function");

// 1. Several photos: the input is in the page when it opens, takes many files, and hands every one over.
let got = null;
const a = T.pickFiles((files) => { got = files; });
const clicked = log.filter((x) => x[0] === "click")[0];
check("the picker joins the page BEFORE it opens", clicked && clicked[1] === a && clicked[2] === true, JSON.stringify(log.map((x) => x[0])));
check("the picker takes several files", a.type === "file" && a.multiple === true && !a.accept);
check("the picker is hidden", a.style.display === "none");
a.files = [{ name: "IMG_1.jpeg" }, { name: "IMG_2.jpeg" }, { name: "IMG_3.jpeg" }];
a.fire("change");
check("every picked photo reaches the composer", got && got.length === 3 && got[2].name === "IMG_3.jpeg", JSON.stringify(got));
check("the picker stays in the page after the pick (its files may still be uploading)", a.parentNode === body);

// 2. An empty change (some browsers fire one) adds nothing.
got = null;
a.files = [];
a.fire("change");
check("an empty pick calls nothing", got === null);

// 3. The next pick replaces the previous picker: one hidden input at a time.
const b = T.pickFiles(() => {});
check("the next pick removes the previous picker", a.parentNode === null && b.parentNode === body && body.kids.length === 1);

// 4. Closing the picker without a pick removes it.
b.fire("cancel");
check("cancel removes the picker", b.parentNode === null && body.kids.length === 0);

// 5. A picker for one kind of file (importing a team .zip) takes one file.
const c = T.pickFiles(() => {}, ".zip,application/zip");
check("a typed picker takes one file of that kind", c.accept === ".zip,application/zip" && c.multiple === false);
c.fire("cancel");

// 6. No detached picker comes back: pickFiles is the only place teams.js makes an input, and every picker goes through it.
check("teams.js makes an <input> in one place only", (src.match(/createElement\("input"\)/g) || []).length === 1);
check("attaching in chat uses pickFiles", /d\.plusAttach\) \{ setPlus\(false\); return pickFiles\(attachFiles\); \}/.test(src));
check("adding team documents uses pickFiles", /d\.infoAddFile\) return pickFiles\(addTeamFiles\)/.test(src));
check("documents in the create box use pickFiles", /tmp-doc-upload"\)\) return pickFiles\(pickUploadDocs\)/.test(src));
check("importing a team uses pickFiles", /pickFiles\(function \(files\) \{\s*var f = files\[0\];/.test(src));

delete global.document;
if (fails) { console.log("\nFAIL - test_team_file_picker: " + fails); process.exit(1); }
console.log("\nOK - test_team_file_picker");
