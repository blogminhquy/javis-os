/* GitHub inside chat, phase G1 (0.362.0): the built-in GitHub card, the "GitHub repo" item of the + menu, the chip.

       node tests/js/test_github_connect.js
*/
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const html = read("dashboard/index.html");
const js = read("dashboard/github-connect.js");
const consoleJs = read("dashboard/console.js");
const app = read("dashboard/app.js");
const vi = JSON.parse(read("dashboard/i18n/vi.json"));
const en = JSON.parse(read("dashboard/i18n/en.json"));
const gh = require(path.join(ROOT, "dashboard/github-connect.js"));
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

check("chip text: first repo name only, +N for the rest", gh.chipText(["acme/app", "acme/lib"], 18) === "app +1");
check("chip text: long names are cut", gh.chipText(["acme/a-very-long-repository-name"], 10).length === 10);
check("chip text: nothing attached means no chip", gh.chipText([], 18) === "");
check("toggle adds then removes", JSON.stringify(gh.toggle(gh.toggle([], "a/b"), "a/b")) === "[]");
check("sameSet ignores order", gh.sameSet(["a/b", "c/d"], ["c/d", "a/b"]) && !gh.sameSet(["a/b"], ["a/b", "c/d"]));

// Status icons (spec 12.1)
check("no GitHub work: no icon", gh.iconSpec({ state: "" }) === null && gh.iconSpec(null) === null);
check("working shows its count only when more than one job runs",
  gh.iconSpec({ state: "working", running: 2, sub: "waiting_ci" }).count === 2 && gh.iconSpec({ state: "working", running: 1 }).count === 0);
check("each of the four states has its own label", ["working", "ready", "merged", "broken"].every(s => {
  const k = gh.iconSpec({ state: s }).key; return vi[k] && en[k]; }));
check("merged with a red post-merge check carries the warning class and text",
  /gh-warn/.test(gh.iconSpec({ state: "merged", merged_warning: true }).cls) && gh.iconSpec({ state: "merged", merged_warning: true }).subKey === "gh.st_post_red");
check("secondary marks have labels", ["waiting_ci", "waiting_review", "stuck"].every(s => vi["gh.sub_" + s] && en["gh.sub_" + s]));
const sess = read("dashboard/sessions-ui.js");
check("the chat list rows carry their session id and ask for GitHub icons",
  /item\.setAttribute\("data-sid", s\.id\)/.test(sess) && /JavisGithubRepos\.decorate\(listEl\)/.test(sess));
check("the module loads after composer-folder.js",
  html.indexOf("/static/composer-folder.js") !== -1 && html.indexOf("/static/composer-folder.js") < html.indexOf("/static/github-connect.js"));
check("the Connections page always mounts the GitHub card, first in the connected list",
  consoleJs.indexOf('id="mcpGithub"') !== -1 && consoleJs.indexOf('id="mcpGithub"') < consoleJs.indexOf('id="connList"')
  && /JavisGithubRepos\.mount\(document\.getElementById\("mcpGithub"\)\)/.test(consoleJs));
check("the + menu gets a GitHub repo item right after the pinned folder (order 25)", /register\(\{ id: "github", order: 25/.test(js));
check("app.js attaches held repos after the pin, before the first turn",
  /_pinWait = \(_pinWait \|\| Promise\.resolve\(\)\)\.then\(\(\) => window\.JavisGithubRepos\.claimPending/.test(app));
check("the token field is cleared after a submit", /data-f="token"\]'\)\.value = ""/.test(js));
check("the card never asks the server for the token back", !/token\s*:\s*st\./.test(js));
check("no em dash in the module", js.indexOf("\u2014") === -1 && js.indexOf("\u2013") === -1);

const keys = Array.from(new Set((js.match(/tw\("(gh\.[a-z_]+)"/g) || []).map(m => m.slice(4, -1))));
check("every gh.* key used exists in vi.json and en.json", keys.length > 20 && keys.every(k => vi[k] && en[k]));
check("Vietnamese texts carry diacritics", /Kết nối/.test(vi["gh.connect"]) && /Gỡ khỏi brain/.test(vi["gh.remove_brain"]));
check("no em dash in the new texts", keys.every(k => !/[\u2013\u2014]/.test(vi[k] + en[k])));

if (fails.length) { console.log("\nFAIL " + fails.length + ": " + fails.join(", ")); process.exit(1); }
console.log("\nTẤT CẢ PASS");
