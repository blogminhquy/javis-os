/* A connection still in its first start (health kind "starting", often an npx download) keeps
   ok=false on the server, but the message says it is not an error yet. The dashboard must not
   paint it red or count it as needing a reconnect (PR #714 review).

       node tests/js/test_conn_health_starting_dot.js
*/
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const consoleSrc = fs.readFileSync(path.join(ROOT, "dashboard/console.js"), "utf8");
const plusSrc = fs.readFileSync(path.join(ROOT, "dashboard/composer-plus.js"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "dashboard/console.css"), "utf8");
let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const start = consoleSrc.indexOf("async function refreshConnHealth(");
const body = start === -1 ? "" : consoleSrc.slice(start, consoleSrc.indexOf("\n  }\n", start));
check("refreshConnHealth exists in console.js", start !== -1);
check("a starting connection gets the amber dot (hunk), checked before the red branch",
  /kind === "starting"\)\s*\{[\s\S]{0,200}classList\.add\("hunk"\)/.test(body)
  && body.indexOf('kind === "starting"') < body.indexOf('classList.add("herr")'));
check("the amber dot class exists in console.css", /\.cdot\.hunk\s*\{[^}]*warn/.test(css));
check("the + menu does not count a starting connection as needing a reconnect",
  /ok === false && h\[k\]\.kind !== "starting"/.test(plusSrc));
check("the + menu shows a starting connection with the neutral (amber) dot, not the red one",
  /h\.kind === "starting" \? "unknown"/.test(plusSrc));

if (fails.length) { console.log("\nFAIL - test_conn_health_starting_dot: " + fails.length); process.exit(1); }
console.log("\nOK - test_conn_health_starting_dot: all pass");
