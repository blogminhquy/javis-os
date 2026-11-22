/* Brain backup on the signed-in GitHub account (backup-link.js, owner 20/11/2026).

       node tests/js/test_backup_link.js

Once GitHub is connected, the sync box on the Self-learning page links a repo in one tap instead of asking for a URL
and a hand-made token. This pins the four states of the box, the repo name shown, and the wiring around it.
*/
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const html = read("dashboard/index.html");
const js = read("dashboard/backup-link.js");
const ghJs = read("dashboard/github-connect.js");
const consoleJs = read("dashboard/console.js");
const vi = JSON.parse(read("dashboard/i18n/vi.json"));
const en = JSON.parse(read("dashboard/i18n/en.json"));
const bl = require(path.join(ROOT, "dashboard/backup-link.js"));
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

// ---- the four states ----
check("no GitHub, no repo: connect", bl.phase({}, { connected: false }) === "connect");
check("GitHub connected, no repo: pick", bl.phase({ repo_url: "" }, { connected: true }) === "pick");
check("repo synced through GitHub: linked", bl.phase({ repo_url: "https://github.com/a/b", token_source: "github" }, { connected: true }) === "linked");
check("repo with a pasted token: linked even without GitHub",
  bl.phase({ repo_url: "https://github.com/a/b", token_source: "token" }, { connected: false }) === "linked");
check("repo but no token from anywhere: lost", bl.phase({ repo_url: "https://github.com/a/b", token_source: "" }, { connected: false }) === "lost");
// 22/11/2026: no GitHub answer is "could not check", not "connect" (tests/js/test_github_status_unknown.js).
check("missing answers do not throw, and say the check failed", bl.phase(null, null) === "unknown");

// ---- repo name ----
check("GitHub URL shows owner/repo", bl.repoName("https://github.com/acme/javis-brain-backup") === "acme/javis-brain-backup");
check(".git and a trailing slash are dropped", bl.repoName("https://github.com/acme/x.git/") === "acme/x");
check("ssh URL shows owner/repo", bl.repoName("git@github.com:acme/x.git") === "acme/x");
check("other hosts show the last part", bl.repoName("https://git.example.com/team/brain") === "brain");
check("GitHub repos link to their page", bl.repoWeb("https://github.com/acme/x.git") === "https://github.com/acme/x");
check("other hosts get no link", bl.repoWeb("https://git.example.com/team/brain") === "");

// ---- wiring ----
check("index.html loads backup-link.js after github-connect.js",
  html.indexOf("/static/backup-link.js") > html.indexOf("/static/github-connect.js") && html.indexOf("/static/backup-link.js") < html.indexOf("/static/console.js"));
check("the Connect button opens the same dialog as the Connections page", /JavisGithubRepos\.connect\(\)/.test(js) && /connect: connect/.test(ghJs));
check("a sign-in anywhere tells the backup box", (ghJs.match(/announceConnected\(\)/g) || []).length >= 3 && /javis:github-connected/.test(consoleJs));
check("console.js mounts the box", /JavisBackupLink\.mount\(/.test(consoleJs) && /id="bkLink"/.test(consoleJs));
check("a fresh link syncs right away", /onLinked:[^\n]*bkSyncNow/.test(consoleJs));
check("the pasted-token form stays, hidden by default", /id="bkManual" hidden/.test(consoleJs) && /id="bkToken"/.test(consoleJs));
check("switches save at once, no separate Save", /bkAutoBtn\.onclick = async[^\n]*bkSaveCfg\(\)/.test(consoleJs) && /bkAnhBtn\.onclick = async[^\n]*bkSaveCfg\(\)/.test(consoleJs));
check("only the routes of the server are called",
  ["/backup/github/repos", "/backup/github/link", "/backup/github/create", "/backup/github/unlink"].every(u => js.includes(u)));

// ---- words ----
const keys = (js.match(/tw\("(bl\.[a-z_]+)"/g) || []).map(m => m.slice(4, -1));
keys.push("bl.info_fast");
check("every bl.* key used exists in vi and en", keys.length > 10 && keys.every(k => vi[k] && en[k]));
check("no em dash or en dash in the new words", keys.every(k => !/[—–]/.test(vi[k] + en[k])) && !/[—–]/.test(js));
check("short lines on the box stay under 100 characters", keys.filter(k => k !== "bl.info_fast" && k !== "bl.unlink_q")
  .every(k => vi[k].length <= 100 && en[k].length <= 100));

if (fails.length) { console.log(`\n${fails.length} FAILED`); process.exit(1); }
console.log("\nall ok");
