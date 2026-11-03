/* Wide tables on the Chat page get room, prose keeps its 72ch measure (0.444.0, idea from PR #958).

       node tests/js/test_chat_wide_tables.js

   PR #958 widened EVERY answer on the Chat page to 1200px. That undoes the 72ch line length the
   owner chose on purpose (0.26.1, locked by test_de_doc_bong_bong.js; 0.181.0 removed a 120ch
   widening). The kept version widens only an answer whose table has 4 or more columns, on a
   desktop, and clamps the prose inside it back to 72ch. Verified in Chromium: 6-column table
   answer 1200px, 2-column table and plain answers unchanged. */
const fs = require("fs");
const path = require("path");

const CSS = fs.readFileSync(path.join(__dirname, "../../dashboard/style.css"), "utf8");
const HTML = fs.readFileSync(path.join(__dirname, "../../dashboard/index.html"), "utf8");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

const WIDE = ".bubble:has(.md-table tr > :nth-child(4))";
const at = CSS.indexOf("#chatPage .msg-javis > " + WIDE + ",");
check("a widening rule exists for answers with a 4+ column table", at > 0);

const mediaStart = CSS.lastIndexOf("@media", at);
const media = CSS.slice(mediaStart, at);
check("the widening only applies on a desktop (min-width media query)", /@media\s*\(min-width:\s*861px\)\s*\{\s*$/.test(media));

const block = CSS.slice(at, CSS.indexOf("\n}\n", at));
check("the answer and its reaction row widen together",
  block.includes("#chatPage .msg-javis:has(> .bubble .md-table tr > :nth-child(4)) > .jr-chat"));
check("the cap is min(1200px, 100%) so a narrow pane never overflows", block.includes("max-width: min(1200px, 100%)"));
check("prose inside a widened answer keeps the 72ch measure",
  /#chatPage \.msg-javis > \.bubble:has\(\.md-table tr > :nth-child\(4\)\) > :not\(\.md-tablewrap\):not\(pre\):not\(\.code-wrap\) \{\s*max-width: 72ch;/.test(block));

// No rule widens every answer on the Chat page (the PR #958 shape).
check("no unconditional widening of .msg-javis .bubble on #chatPage",
  !/#chatPage \.msg-javis \.bubble\s*[,{]/.test(CSS) && !/#chatPage \.msg-javis > \.jr-chat\s*[,{]/.test(CSS));
check("the base answer bubble is still 72ch", /\.msg-javis \.bubble \{ max-width: min\(72ch, 100%\); \}/.test(CSS));
check("style.css cache key is past 156 so browsers fetch the new rule",
  (Number((HTML.match(/style\.css\?v=(\d+)/) || [])[1]) || 0) > 156);

console.log("");
if (fails.length) { console.log("FAIL: " + fails.length); process.exit(1); }
console.log("All checks passed.");
