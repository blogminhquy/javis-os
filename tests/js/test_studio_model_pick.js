/* The assistant's Model list (studio.js) must not close when a provider name is clicked (0.348.0).

       node tests/js/test_studio_model_pick.js

   Clicking a provider redraws the list at once (veModelPop), so the clicked row has left the DOM before the
   document "click outside" listener runs. Judged by e.target and contains(), that click looked outside and the list
   closed instead of opening the provider (owner, 27/10/2026, Partners page). The listener has to follow the
   click's path (composedPath), like chat-goal.js. Checked in a real browser: old code closed, new code opens. */
const fs = require("fs");
const path = require("path");

const SRC = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "studio.js"), "utf8");
let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

const start = SRC.indexOf("const ngoaiKhung = (e) => {");
const body = start >= 0 ? SRC.slice(start, SRC.indexOf("\n    };", start)) : "";
check("the click-outside listener of the Model list exists", !!body);
check("it follows the click's path (composedPath), which survives the redraw", /e\.composedPath\(\)/.test(body));
check("it no longer decides with contains(e.target), which a redraw breaks", !/contains\(e\.target\)/.test(body));
check("a provider click still redraws the list (the reason the path is needed)",
  /const pr = e\.target\.closest\("\.mb-prov"\);[\s\S]{0,200}veModelPop\(\)/.test(SRC));

if (fails) { console.error(fails + " FAILED"); process.exit(1); }
console.log("studio model pick: all pass");
