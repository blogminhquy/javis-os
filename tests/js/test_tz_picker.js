// Timezone picker shared by the first-run setup and Settings (dashboard/tz-picker.js, 0.443.0).
//   node tests/js/test_tz_picker.js
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..", "..");
let fails = 0;
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails++;
}

const ctx = { window: {}, Intl, Date, String, Math, isNaN, console };
ctx.window.t = (k) => k;   // no dictionary: the module must fall back to its English labels
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(ROOT, "dashboard", "tz-picker.js"), "utf8"), ctx);
const Tz = ctx.window.JavisTz;

check("exposes JavisTz", Tz && typeof Tz.options === "function");
check("detect returns the browser timezone", typeof Tz.detect() === "string");
check("Ho Chi Minh is UTC+07:00 (no daylight saving)", Tz.offsetLabel("Asia/Ho_Chi_Minh") === "UTC+07:00");
check("Kolkata keeps its half hour", Tz.offsetLabel("Asia/Kolkata") === "UTC+05:30");
check("UTC is UTC+00:00", Tz.offsetLabel("UTC") === "UTC+00:00");
check("an unknown name has no label", Tz.offsetLabel("Mars/Olympus") === "");

const html = Tz.options("Asia/Tokyo");
const selected = html.match(/<option value="[^"]+" selected>/g) || [];
check("exactly one option is selected", selected.length === 1 && selected[0].includes("Asia/Tokyo"));
check("starts with a suggested group", html.indexOf('<optgroup label="Suggested">') === 0);
check("then the full list", html.includes('<optgroup label="All timezones">'));
check("no option appears twice", (() => {
  const vals = (html.match(/<option value="([^"]+)"/g) || []);
  return vals.length > 20 && new Set(vals).size === vals.length;
})());
check("old browser spellings become the current IANA names",
  html.includes('value="Asia/Ho_Chi_Minh"') && !html.includes('value="Asia/Saigon"')
  && html.includes('value="Asia/Kolkata"') && !html.includes('value="Asia/Calcutta"'));
check("detect never returns an old spelling", !/Saigon|Calcutta|Kiev$/.test(Tz.detect()));
check("labels carry the offset", html.includes("(UTC+07:00) Asia/Ho Chi Minh"));

const odd = Tz.options("Mars/Olympus");
check("a saved name the browser does not know still shows as selected",
  /<option value="Mars\/Olympus" selected>Mars\/Olympus<\/option>/.test(odd));
check("labels are escaped", !Tz.options('x"><script>').includes("<script>"));
check("nowIn gives HH:MM", /^\d{2}:\d{2}$/.test(Tz.nowIn("Asia/Ho_Chi_Minh")));

if (fails) { console.log(`\nFAILED ${fails}`); process.exit(1); }
console.log("\nOK - test_tz_picker: all pass");
