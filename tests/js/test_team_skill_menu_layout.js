// Owner, 17/11/2026: the "/" skill list of a team chat overlapped. The suggestion box (.tm-sug) is a flex column with a
// max height, so with eight skills its rows shrank below their text and each row ran into the next; a long skill name
// also wrapped onto its description. Rows must keep their height and the name and description stay one line each.
//
//     node tests/js/test_team_skill_menu_layout.js
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");

let fails = 0;
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails++;
}

// Every rule body for a selector (exact selector inside a selector list), joined.
function rules(sel) {
  const out = [];
  const re = /([^{}]+)\{([^}]*)\}/g;
  let m;
  while ((m = re.exec(css)) !== null) {
    const sels = m[1].replace(/\/\*[\s\S]*?\*\//g, "").split(",").map(function (s) { return s.trim(); });
    if (sels.indexOf(sel) >= 0) out.push(m[2]);
  }
  return out.join(";");
}

check("the box is a column with a max height that scrolls", /flex-direction:\s*column/.test(rules(".tm-sug")) &&
  /max-height/.test(rules(".tm-sug")) && /overflow-y:\s*auto/.test(rules(".tm-sug")));
check("a suggestion row never shrinks below its text (flex: none)", /flex:\s*none/.test(rules(".tm-sug-item")));
const name = rules(".tm-sug-skill .tm-sug-name");
check("a long skill name stays on one line, cut with ...", /white-space:\s*nowrap/.test(name) && /text-overflow:\s*ellipsis/.test(name) &&
  /overflow:\s*hidden/.test(name));
const role = rules(".tm-sug-skill .tm-sug-role");
check("the skill description stays on one line, cut with ...", /white-space:\s*nowrap/.test(role) && /text-overflow:\s*ellipsis/.test(role));
check("the text column can shrink so the ... shows", /min-width:\s*0/.test(rules(".tm-sug-text")));

if (fails) { console.log(fails + " FAIL"); process.exit(1); }
console.log("all ok");
