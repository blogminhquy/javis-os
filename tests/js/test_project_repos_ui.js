// 2026-11-15: GitHub repos in the create-team box (dashboard/team-picker.js) and the drawer of a project or an
// assistant (dashboard/sessions-ui.js).
//
//     node tests/js/test_project_repos_ui.js
//
// Owner: "ở chức năng project cũng có khả năng thêm repo để dễ dàng tạo các dự án code, hoặc cả trong tài liệu của agent
// và team cũng có khả năng thêm repo". The server side is tests/python/test_project_repos.py.
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(root, "dashboard", f), "utf8");
const vi = JSON.parse(read("i18n/vi.json"));
const P = require(path.join(root, "dashboard", "team-picker.js"));
P.setStrings(vi);

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  " + String(extra).slice(0, 500)));
  if (!cond) fails++;
}

const base = { mode: "create", selected: ["lan"], leader: "lan", docs: [], links: [] };

// ---- the create-team box ----
let st = P.setRepos(base, ["acme/app", "ACME/app", " acme/lib ", ""]);
check("repos are kept once each, whatever the case", JSON.stringify(st.repos) === '["acme/app","acme/lib"]', st.repos);
check("the old state is not changed", base.repos === undefined);
check("the summary counts repos with files and links", P.docsCount(st) === 2 && P.docsSummaryHtml(st).includes(">2<"));
check("a repo chip can be removed", P.docChipsHtml(st).includes('data-repo-del="1"') && P.removeRepo(st, 0).repos[0] === "acme/lib");
check("the chip shows the short name and keeps the full one in its title",
  /title="acme\/lib">lib</.test(P.repoChipsHtml(st)), P.repoChipsHtml(st));
check("a repo name with markup is shown as text", !P.repoChipsHtml({ repos: ["a/<img src=x>"] }).includes("<img"));
check("repos alone open the documents block", /<details class="tmp-desc tmp-docs" open/.test(P.docsHtml(st)));
const h = P.docsHtml(base);
check("the block has a button that opens the repo picker, closed at first",
  h.includes("tmp-repo-open") && h.includes('aria-expanded="false"') && /class="tmp-repo-box" hidden/.test(h));
check("an open picker opens the block and shows its box",
  /<details class="tmp-desc tmp-docs" open/.test(P.docsHtml(Object.assign({}, base, { repoOpen: true })))
  && !/class="tmp-repo-box" hidden/.test(P.docsHtml(Object.assign({}, base, { repoOpen: true }))));
check("the files and links sent to POST /teams are unchanged by repos",
  JSON.stringify(P.docPayload(st)) === JSON.stringify({ attachments: [], links: [] }));

// ---- the drawer ----
const SU = read("sessions-ui.js");
check("the documents tab counts the repos of a project or an assistant",
  /\(pdCoRepo\(\) \? \(p\.repos \|\| \[\]\)\.length : 0\)/.test(SU));
check("a repo row is wired by its own code, not as a file", /if \(row\.dataset\.kind === "repo"\) return;/.test(SU)
  && /function noiRepo\(pane\)/.test(SU));
check("removing a repo from the list keeps the others", /repoNames\(pdDuLieu\(\)\)\.filter\(function \(x\) \{ return x !== n; \}\)/.test(SU));
check("a fourth add mode lays the modes out two by two", /'<div class="pd-modes' \+ \(pdCoRepo\(\) \? " four" : ""\)/.test(SU)
  && read("style.css").includes(".pd-modes.four { display: grid; grid-template-columns: 1fr 1fr; }"));
check("the assistant's repos are read with its documents", /repos: d\.repos \|\| \[\]/.test(SU));

// ---- the "+" row of the picker (owner 15/11: "cần thêm nút + để thêm repo mới như ở hội thoại") ----
const G = require(path.join(root, "dashboard", "team-github.js"));
const TG = read("team-github.js");
check("signed in with the app, the + row opens the app's page on GitHub",
  G.addReposUrl({ source: "app", install_url: "https://github.com/apps/x/installations/new" }) === "https://github.com/apps/x/installations/new");
check("a pasted token gets no GitHub link", G.addReposUrl({ source: "token", install_url: "https://x" }) === "" && G.addReposUrl(null) === "");
check("the picker draws the + row under its list, like the chat composer",
  /'<div class="gh-foot"><div class="cp-pin-err" role="status"><\/div>' \+ footRow\(addUrl\)/.test(TG)
  && TG.includes('tw("gh.add_on_github")') && TG.includes('tw("gh.connect_more")'));
check("the list is fetched again on return from GitHub", /if \(away\) \{ away = false; fetchList\(\); \}/.test(TG));
check("the + row sits under the list in the drawer and the create box",
  read("style.css").includes(".pd-repo-box .gh-foot, .tmp-repo-box .gh-foot { position: static;"));

if (fails) { console.log(`\nFAIL - test_project_repos_ui: ${fails} lỗi`); process.exit(1); }
console.log("\nOK - test_project_repos_ui: tất cả pass");
