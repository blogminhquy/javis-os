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

// 0.367.0 (owner, 28/10/2026): the repo list opens in a popup like the bot cards on the Chatbot page, not inline.
{
  const card = js.slice(js.indexOf("function cardHtml"), js.indexOf("async function loadCard"));
  check("the card shows a compact repo row, not the repo rows themselves",
    card.includes("data-gh-repos") && card.includes("gh.repos_n") && !card.includes("data-gh-remove"));
  const pop = js.slice(js.indexOf("function openRepos"), js.indexOf("// Local check commands"));
  check("the popup carries every repo action and comes back from Checks and Numbers",
    /JavisConnModal/.test(pop) && pop.includes("reposHtml(local)") && pop.includes('openChecks(b.getAttribute("data-gh-checks"), back)') && pop.includes('openMetrics(b.getAttribute("data-gh-metrics"), back)'));
}

// Owner, 06/11/2026: the repo popup takes the look of the Tasks page: card rows, a switch for auto-merge, and a "..."
// sheet holding Checks, Numbers and Remove instead of a row of buttons.
{
  const row = js.slice(js.indexOf("function localRow(r)"), js.indexOf("// The repos of this brain"));
  check("each repo is a card row with a meta line", row.includes('class="gh-rrow') && row.includes("gh-rmeta") && row.includes("gh.local_chats"));
  check("auto-merge is a switch, its state written in the meta line",
    row.includes('class="gh-sw" role="switch" aria-checked="') && row.includes("gh.auto_merge_off") && !row.includes('type="checkbox"'));
  check("Checks, Numbers and Remove sit in the ... sheet, Remove in red",
    row.includes("data-gh-menu") && /function repoSheet[\s\S]*data-gh-checks[\s\S]*data-gh-metrics[\s\S]*gh-mi danger" data-gh-remove/.test(row));
  check("the sheet closes with Escape and on the scrim", row.includes('e.key === "Escape"') && row.includes("gh-sheet-scrim\" data-gh-close"));
  check("the row helper does not clash with the picker's repoRow", (js.match(/function localRow\(/g) || []).length === 1);
  const css = read("dashboard/style.css");
  check("the dialog carries its own Tasks-page styles (tasks.css loads only on that page)",
    /\.gh-rrow \{/.test(css) && /\.gh-sw\[aria-checked="true"\]/.test(css) && /\.gh-sheet \{/.test(css) && /\.gh-sheet-scrim \{[^}]*z-index: 210/.test(css));
  check("new texts exist in both languages", ["gh.auto_merge_off", "gh.more", "gh.close"].every(function (k) { return vi[k] && en[k]; }));
}

// 0.368.0 (owner, 28/10/2026, after Claude Code's picker): the chip and + menu open "Change repo / Change branch";
// the repo list has "Selected" and "Repos" sections; a branch list per repo.
{
  const pan = js.slice(js.indexOf("function panel(box, menuApi)"), js.indexOf("// 4. Status icons"));
  check("the GitHub panel opens on the short menu once repos are attached, else on the repo list",
    /\(held \|\| names\(\)\.length\) \? homeView\(box, menuApi\) : reposView\(box, menuApi, false\)/.test(pan));
  check("the menu offers Change repo and Change branch", pan.includes('data-gh-go="repos"') && pan.includes('data-gh-go="branch"'));
  check("the repo list splits Selected from the rest", pan.includes("gh.sec_selected") && pan.includes("gh.sec_repos"));
  check("several repos: pick the repo, then its branch", pan.includes("branchReposView") && pan.includes("branchView(box, menuApi, repos["));
  check("the branch pick goes to the server for a live chat, and waits with the held repos on an empty one",
    pan.includes('"/base"') && /heldBase\[fullName\] = heldValue/.test(pan));
  check("the held branch is applied right after the held repos, before the first turn",
    /claimPending[\s\S]*"\/base"/.test(js.slice(js.indexOf("function claimPending"), js.indexOf("function panel("))));
  check("a non-default base rides on the chip", js.includes("gh-chip-br") && js.includes("function chipBase()"));
}

// 0.432.4 (owner, 01/11/2026): ticking a repo attaches it at once; no Attach button at the foot of a long list, and
// the footer stays pinned while the list scrolls.
{
  const rv = js.slice(js.indexOf("function reposView(box, menuApi, canBack)"), js.indexOf("// Several repos: pick the repo first"));
  check("the repo list has no Attach button any more", !rv.includes("data-apply") && !rv.includes("gh.apply_"));
  check("a tick toggles the repo and syncs it to the chat right away", /chosen = toggle\(chosen, r\.full_name\); draw\(\); sync\(\);/.test(rv));
  check("only one change is in flight; later ticks ride on the next request", /if \(busy\) return;/.test(rv) && /sent = list;[\s\S]*sync\(\);/.test(rv));
  check("a refused change puts the ticks back and says why", /if \(msg\) \{ chosen = sent\.slice\(\); err\.textContent = msg; draw\(\);/.test(rv));
  const css = fs.readFileSync(path.join(ROOT, "dashboard/style.css"), "utf8");
  check("the picker footer is pinned to the bottom of the + menu", /\.gh-foot \{ position: sticky; bottom: -6px;/.test(css));
}

// 0.438.1 (owner, 01/11/2026): the card looks like the other connection cards and no longer asks to pick repos.
{
  const card = js.slice(js.indexOf("function cardHtml"), js.indexOf("async function loadCard"));
  check("a connected card shows the account as a chip with a green dot", /conn-chip gh-acc"><span class="cdot hok">●<\/span>/.test(card));
  check("Pick repos shows only while the app is on no account", /st\.installs === 0 \? '<a class="conn-chip add"[^]*gh\.pick_repos/.test(card));
  check("no 'no repo downloaded yet' line on the card", !card.includes("gh.local_none"));
  check("the status line no longer repeats the login", !card.includes("gh.connected_as") && card.includes("gh.card_desc"));
  const css = fs.readFileSync(path.join(ROOT, "dashboard/style.css"), "utf8");
  check("the GitHub logo is 32px like the other card logos", /\.gh-card \.conn-ico\.gh-logo \.cp-ic \{ width: 32px; height: 32px; \}/.test(css));
}

// 0.438.1 (owner, 01/11/2026): a shortcut to add repos on GitHub from the chat picker, for an app sign-in.
{
  const rv = js.slice(js.indexOf("function reposView(box, menuApi, canBack)"), js.indexOf("// Several repos: pick the repo first"));
  check("the picker footer offers Add repos on GitHub for an app sign-in, Connect more otherwise",
    /addUrl \? '<a class="cp-mi gh-more-conn" data-gh-add="1" target="_blank"[^]*gh\.add_on_github[^]*: '<button[^]*gh\.connect_more/.test(rv));
  check("only an app sign-in gets the shortcut", /ghStatus\.source === "app" && ghStatus\.install_url/.test(js));
  check("an empty list points to the same shortcut", /gh\.none_found"\)\) \+\s*\(addUrl \? ' <a data-gh-add="1"/.test(rv));
  check("coming back to the tab after GitHub reloads the list", /if \(away\) \{ away = false; load\(\); \}/.test(rv) && rv.includes('addEventListener("visibilitychange", onBack)'));
  check("the listeners go away with the panel", rv.includes('removeEventListener("visibilitychange", onBack)'));
}

// The "Connected" heading (0.367.0): MCP accounts plus GitHub plus Facebook Pages, whichever card loads last.
{
  const attrs = [{ name: "id", value: "connCount" }, { name: "style", value: "opacity:.5" }, { name: "data-n", value: "2" }];
  const cnt = { attributes: attrs, textContent: "",
    setAttribute(n, v) { const a = attrs.find(x => x.name === n); if (a) a.value = v; else attrs.push({ name: n, value: v }); } };
  global.document = { getElementById: id => (id === "connCount" ? cnt : null) };
  global.window = { t: (k, v) => (k === "cs.cn_account_n" ? v.so + " accounts" : k) };
  const fb = require(path.join(ROOT, "dashboard/messenger-connect.js"));
  check("a connected GitHub adds one to the MCP accounts", gh.addToConnCount("gh", 1) === 3 && cnt.textContent === "3 accounts");
  check("Pages loading after GitHub keep GitHub in the count", fb.addToConnCount("fb", 2) === 5 && cnt.textContent === "5 accounts");
  check("GitHub reloading after the Pages keeps the Pages", gh.addToConnCount("gh", 1) === 5);
  check("disconnecting GitHub takes only its own share off", gh.addToConnCount("gh", 0) === 4 && cnt.textContent === "4 accounts");
  delete global.document; delete global.window;
}

// Owner, 08/11/2026: cross review is the person's call. A per-repo switch (off by default) with a reviewer picker, and on
// the PR panel Review now, then Fix them / Skip and merge on the findings.
{
  const sheet = js.slice(js.indexOf("function repoSheet(name)"), js.indexOf("// The repos of this brain"));
  check("the ... sheet has a Cross review item", sheet.includes("data-gh-review") && sheet.includes("gh.review"));
  const dlg = js.slice(js.indexOf("async function openReview("), js.indexOf("// Local check commands"));
  check("the review dialog has a switch and a reviewer picker, the chat's model first",
    dlg.includes('role="switch"') && dlg.includes('data-f="prov"') && js.includes("gh.review_default") && dlg.includes('"/github/local/review"'));
  const det = js.slice(js.indexOf("function detailHtml(d)"), js.indexOf("function openDetail(id)"));
  check("Review now only on an open, unmerged PR that is not already being reviewed",
    /canReview = !!r\.pr_number && r\.integ !== "merged" && !r\.reviewing && !r\.merging/.test(det) && det.includes("data-rv-now"));
  check("findings come with Fix them and Skip and merge, and hide the plain Merge button",
    det.includes("data-rv-fix") && det.includes("data-rv-skip") && det.includes("canMerge && !found.length"));
  const od = js.slice(js.indexOf("function openDetail(id)"), js.indexOf("function init()"));
  check("the panel follows a running review", /r\.merging \|\| r\.reviewing/.test(od));
  check("the buttons call the review routes", od.includes('"/review"') && od.includes('"/review/fix"') && od.includes('"/review/skip"'));
  check("review texts exist in both languages", ["gh.review", "gh.review_how", "gh.review_now", "gh.review_fix", "gh.review_skip",
    "gh.reviewing", "gh.review_fixing", "gh.review_started", "gh.review_on_meta"].every(function (k) { return vi[k] && en[k]; }));
}

// Owner, 09/11/2026: check for git before connecting GitHub, and install it first when the machine has none.
{
  check("git step: an answer with git is ready", gh.gitPhase({ ok: true, has_git: true, install: "idle" }) === "ready");
  check("git step: a running install keeps polling",
    gh.gitPhase({ ok: true, has_git: false, install: "installing" }) === "installing" &&
    gh.gitPhase({ ok: true, has_git: false, install: "installing", wait_user: true }) === "wait_user");
  check("git step: a failed install shows retry", gh.gitPhase({ ok: true, has_git: false, install: "failed", can_install: true }) === "failed");
  check("git step: no way to install here shows the manual command", gh.gitPhase({ ok: true, has_git: false, install: "idle", can_install: false }) === "manual");
  check("git step: a network error is its own phase", gh.gitPhase(null) === "error" && gh.gitPhase({ ok: false }) === "error");
  const of = js.slice(js.indexOf("function openForm(st)"), js.indexOf("async function setupGit"));
  check("Connect goes through the git step when the machine has no git, then opens the sign-in form",
    /st\.has_git === false\) \{ setupGit\(function \(g\) \{ connectForm\(st, g\); \}\)/.test(of) && of.includes("connectForm(st);"));
  const sg = js.slice(js.indexOf("async function setupGit"), js.indexOf("function connectForm"));
  check("the git step asks the server to install, then polls GET /github/git",
    sg.includes('api("/github/git/install", {})') && sg.includes('api("/github/git")') && /setTimeout\(res, 2500\)/.test(sg));
  check("the git step stops polling once the dialog is closed or replaced", (sg.match(/if \(!open\(\)\) return;/g) || []).length >= 3);
  check("a failure offers Try again, the manual command and a way on", sg.includes('data-f="retry"') && sg.includes("g.manual") &&
    sg.includes('data-f="skip"') && sg.includes("then(null)"));
  check("the installing line uses the shared loading look", sg.includes('class="pg-loading"'));
  const card = js.slice(js.indexOf("function cardHtml"), js.indexOf("async function loadCard"));
  check("the card says Connect installs git first; a connected card gets an Install git button",
    card.includes('"gh.no_git_auto"') && card.includes("data-gh-git") && js.includes('cardHost.querySelector("[data-gh-git]")'));
  const gitKeys = ["gh.no_git", "gh.no_git_auto", "gh.git_install", "gh.git_head", "gh.git_checking", "gh.git_installing",
    "gh.git_wait_apple", "gh.git_bg", "gh.git_ok", "gh.git_failed", "gh.git_manual", "gh.git_cmd", "gh.git_retry",
    "gh.git_recheck", "gh.git_page", "gh.git_skip"];
  check("git step texts exist in both languages", gitKeys.every(k => vi[k] && en[k]));
  check("git step texts keep the {v} slot in both languages", vi["gh.git_ok"].includes("{v}") && en["gh.git_ok"].includes("{v}"));
  check("the manual-install line names the button actually shown", vi["gh.git_cmd"].includes("{btn}") && en["gh.git_cmd"].includes("{btn}") &&
    sg.includes('tw("gh.git_cmd", { btn: again })') && sg.includes("esc(again)"));
  check("git step texts have no em or en dash", gitKeys.every(k => !/[\u2013\u2014]/.test(vi[k] + en[k])));
}

const keys = Array.from(new Set((js.match(/tw\("(gh\.[a-z_]+)"/g) || []).map(m => m.slice(4, -1))));
check("every gh.* key used exists in vi.json and en.json", keys.length > 20 && keys.every(k => vi[k] && en[k]));
check("Vietnamese texts carry diacritics", /Kết nối/.test(vi["gh.connect"]) && /Gỡ khỏi brain/.test(vi["gh.remove_brain"]));
check("no em dash in the new texts", keys.every(k => !/[\u2013\u2014]/.test(vi[k] + en[k])));

if (fails.length) { console.log("\nFAIL " + fails.length + ": " + fails.join(", ")); process.exit(1); }
console.log("\nTẤT CẢ PASS");
