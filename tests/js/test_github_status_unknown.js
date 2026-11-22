/* A failed GitHub status check says "Could not check", never "Not connected" (owner, 22/11/2026).

       node tests/js/test_github_status_unknown.js

Owner incident 2026-11-22: after a stranger took over the Javis account, the GitHub card read "Not connected" and the
owner could not tell whether GitHub was really signed out or the check had failed. The card, the composer panel, the
team panel and the brain-backup box drew a network error, an expired Javis session (401) or a page that is not JSON
exactly like a real "not connected". Only a real answer of the server may say "not connected" now; anything else shows
"Could not check" with the reason and a retry.
*/
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const ghJs = read("dashboard/github-connect.js");
const tgJs = read("dashboard/team-github.js");
const blJs = read("dashboard/backup-link.js");
const vi = JSON.parse(read("dashboard/i18n/vi.json"));
const en = JSON.parse(read("dashboard/i18n/en.json"));
const gh = require(path.join(ROOT, "dashboard/github-connect.js"));
const bl = require(path.join(ROOT, "dashboard/backup-link.js"));
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

// What each failure looks like once api() or console.js has read it.
const FAILED = {
  "a network error": { ok: false, error: "Could not reach the Javis server." },
  "a page that is not JSON": { ok: false },
  "an expired Javis session (401)": { error: "unauthorized", auth_required: true, setup_required: false },
  "console.js after a failed fetch": {},
  "no answer at all": null,
};
const REAL = {
  on: { ok: true, connected: true, login: "tester", source: "app" },
  off: { ok: true, connected: false, source: "" },
};

// ---- the rule ----
check("statusState is exported", typeof gh.statusState === "function");
const st = gh.statusState || (() => "missing");
for (const [what, ans] of Object.entries(FAILED)) check(`${what} is "unknown"`, st(ans) === "unknown");
check("a real answer with GitHub signed in is \"on\"", st(REAL.on) === "on");
check("a real answer with GitHub signed out is \"off\"", st(REAL.off) === "off");

// ---- the reason under "Could not check" ----
const why = gh.unknownWhy || (() => ({}));
check("an expired session asks to sign in again", why(FAILED["an expired Javis session (401)"]).key === "gh.unknown_signed_out");
check("a network error names it", why(FAILED["a network error"]).text === "Could not reach the Javis server.");
check("no reason given falls back to the network line", why(FAILED["a page that is not JSON"]).key === "gh.err_net" &&
  why(null).key === "gh.err_net");

// ---- the brain-backup box ----
for (const [what, ans] of Object.entries(FAILED)) {
  check(`backup box with no repo after ${what}: "unknown", not "connect"`, bl.phase({}, ans) === "unknown");
}
check("backup box with no repo and GitHub signed out: connect", bl.phase({}, REAL.off) === "connect");
check("backup box with no repo and GitHub signed in: pick", bl.phase({}, REAL.on) === "pick");
check("a linked repo stays linked whatever the check said",
  bl.phase({ repo_url: "https://github.com/a/b", token_source: "github" }, FAILED["a network error"]) === "linked");
check("the backup box keeps the same rule as the GitHub card", typeof bl.statusState === "function" &&
  [...Object.values(FAILED), ...Object.values(REAL)].every(a => bl.statusState(a) === st(a)));
check("the backup box draws the unknown state with a retry", /ph === "unknown"/.test(blJs) && /data-bl="retry"/.test(blJs));

// ---- every screen goes through the rule ----
check("the Connections card goes through the rule", /statusState\(st\) === "unknown"/.test(ghJs.slice(ghJs.indexOf("async function loadCard"))));
check("the composer panel goes through the rule",
  /statusState\(st\)/.test(ghJs.slice(ghJs.indexOf("function panel(box, menuApi)"), ghJs.indexOf("var ghStatus = null"))));
check("the team panel goes through the same rule", /statusState\(st\)/.test(tgJs) && /G\.statusState|JavisGithubRepos\.statusState/.test(tgJs));
check("the rule is shared with other screens", /statusState: statusState/.test(ghJs.slice(ghJs.indexOf("window.JavisGithubRepos ="))));
check("no screen maps a missing answer straight to \"not connected\"",
  ![ghJs, tgJs].some(s => /if \(!st \|\| !st\.connected\)/.test(s)));
check("a retry asks the server again, past the kept copy", /github\/status\?refresh=1/.test(ghJs) && /github\/status\?refresh=1/.test(tgJs));
check("the composer panel adds its click handler once, not on every retry",
  (ghJs.slice(ghJs.indexOf("function panel(box, menuApi)"), ghJs.indexOf("var ghStatus = null")).match(/addEventListener\("click"/g) || []).length === 1 &&
  /function load\(fresh\)/.test(ghJs.slice(ghJs.indexOf("function panel(box, menuApi)"))));

// ---- words ----
const KEYS = ["gh.status_unknown", "gh.panel_unknown", "gh.unknown_signed_out"];
check("the new lines exist in both languages", KEYS.every(k => vi[k] && en[k]));
check("they stay short, so no (i) is needed", KEYS.every(k => (vi[k] || "").length <= 100 && (en[k] || "").length <= 100));
check("the Vietnamese says it could not check", /Không kiểm tra được/.test(vi["gh.status_unknown"] || ""));
check("no em dash or en dash", KEYS.every(k => !/[\u2013\u2014]/.test((vi[k] || "") + (en[k] || ""))) &&
  ![ghJs, tgJs, blJs].some(s => /[\u2013\u2014]/.test(s)));

if (fails.length) { console.log(`\n${fails.length} FAILED`); process.exit(1); }
console.log("\nall ok");
