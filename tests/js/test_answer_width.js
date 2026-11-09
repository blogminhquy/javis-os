/* Answers use the width of their chat column, up to 100ch, on every chat screen (owner, 2026-11-09).

       node tests/js/test_answer_width.js

   The owner sent an iPad screenshot of the Cộng sự page: answers stopped at 72ch (779px) while the pane ran on to 1064px,
   leaving a wide empty strip on the right, and asked to stretch them over it. The cap is now 100ch (about 120 letters
   of Vietnamese prose, the line length 0.26.1 named as where reading tires): it fills an iPad or laptop pane and only
   stops on a very wide monitor. Measured in Chromium at 1194x834 with the real CSS: Cộng sự answer 1064px, its right
   edge on the right edge of the owner's own message; Chat page answer 800px, the whole column; Teams answer 1082px at
   1600px wide (was 680px).

   Owner rule 2026-11-05: a chat frame change covers every chat screen in the same PR. Chat, Coding and Cộng sự share
   the .msg-javis rules in style.css; Teams has its own bubble caps in console.css. The customer inbox (Hội thoại) is a
   two-sided messenger of short customer messages and keeps its narrow bubbles on purpose. */
const fs = require("fs");
const path = require("path");

const D = path.join(__dirname, "../../dashboard");
const CSS = fs.readFileSync(path.join(D, "style.css"), "utf8");
const CCSS = fs.readFileSync(path.join(D, "console.css"), "utf8");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

check("an answer bubble may grow to its column, up to 100ch",
  CSS.includes(".msg-javis .bubble { max-width: min(100ch, 100%); }"));
check("the base answer rule carries the same 100ch cap",
  /\.msg-javis \.bubble \{[^}]*max-width: 100ch;[^}]*\}/.test(CSS));
check("the reaction row under an answer is exactly as wide as the answer (its corner sits on the bubble edge)",
  /\.msg-javis > \.jr-chat \{ display: block; max-width: min\(100ch, 100%\);/.test(CSS));
check("the background-work line under an answer uses the same measure",
  /\.msg-javis \.viec-giao \{[^}]*max-width: 100ch;/.test(CSS));
const answerRules = (css) => (css.replace(/\/\*[\s\S]*?\*\//g, "").match(/[^{}]*\.msg-javis[^{}]*\{[^}]*\}/g) || []);
check("no answer rule clamps back to the old 72ch",
  answerRules(CSS).concat(answerRules(CCSS)).every((r) => !/72ch/.test(r)) && answerRules(CSS).length > 10);

// The 0.444.0 special case (answers with a 4+ column table grew on the Chat page, their prose clamped to 72ch) is gone:
// every answer reaches the column now, and that clamp would have made table answers narrower to read than the others.
check("no wide-table special case left on the Chat page", !CSS.includes(".bubble:has(.md-table tr > :nth-child(4))"));
check("no page-only widening of answers on the Chat page or the Cộng sự page",
  !/#chatPage \.msg-javis[^{]*\{[^}]*max-width/.test(CSS) && !/\.(wspage|ws-slot|ws-main)[^{,]*\.msg-javis[^{]*\{[^}]*max-width/.test(CCSS));

// A full-width answer must not lose its reaction corner (right: -6px) to the chat's overflow-x: hidden.
check("the reaction corner still hangs 6px outside the answer on a computer", /\.jr-rx \{ position: absolute; right: -6px;/.test(CSS));
check("on a computer the chat keeps an 8px right gutter for that corner",
  /@media \(min-width: 861px\) \{ \.transcript \{ padding-right: 8px; \} \}/.test(CSS));
check("the outline bar's 34px gutter still wins when the bar shows",
  CSS.includes(".transcript.cm-co-thanh { padding-right: 34px; overflow-x: hidden; }"));
check("phones keep the corner inside the bubble", /@media \(max-width: 860px\) \{ \.jr-rx \{ right: 4px; \} \}/.test(CSS));

// Teams page: agent answers follow the same cap (their column inherits the 16px chat font, so 100ch is the same width).
check("Teams: an agent's answer column grows to 100ch", CCSS.includes(".tm-msg-agent .tm-col { align-items: flex-start; max-width: min(100ch, calc(100% - 40px)); }"));
check("Teams: an agent's bubble grows to 100ch", CCSS.includes(".tm-msg-agent .tm-bubble { border-bottom-left-radius: 6px; max-width: min(100ch, calc(100% - 86px)); }"));
check("Teams: the inner markdown bubble does not add a cap of its own", /\.tm-mdwrap\.msg-javis \.bubble \{[^}]*max-width: none;/.test(CCSS));

const dash = String.fromCharCode(0x2014), en = String.fromCharCode(0x2013);
check("no em or en dash in this test", !fs.readFileSync(__filename, "utf8").includes(dash) && !fs.readFileSync(__filename, "utf8").includes(en));

console.log("");
if (fails.length) { console.log("FAIL: " + fails.length); process.exit(1); }
console.log("All checks passed.");
