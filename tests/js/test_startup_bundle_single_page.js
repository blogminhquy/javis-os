/* Start-up bundle (2026-11-23): code that only one page uses does not load when the app opens.

       node tests/js/test_startup_bundle_single_page.js

   Measured 2026-11-23: the dashboard loaded 3,572 KB of JS before its first paint, and 364 KB of that was the Studio
   editors, the partners page and the Messenger card of the Connections page, none of which the chat screen runs. They
   now sit in the lazy groups that their pages already waited for (nap-cham.js). What this pins:

     - those files are in a lazy group and are no longer <script> tags;
     - every page that draws with them waits for the group, and every caller on another page loads it first;
     - the two things studio.js wired when the app opened (the Studio button, window.openStudio) live in app.js now;
     - the code loaded at start-up may only shrink (a ceiling in bytes). */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond, detail) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || detail === undefined ? "" : "  -> " + JSON.stringify(detail)));
  if (!cond) fails.push(name);
}
const read = rel => fs.readFileSync(path.join(ROOT, rel), "utf8");

const html = read("dashboard/index.html");
const lazy = JSON.parse((html.match(/<script id="javis-lazy" type="application\/json">([\s\S]*?)<\/script>/) || [])[1] || "{}");
const files = group => (lazy[group] || []).map(u => u.slice(8).split("?")[0]);
const eager = [];
html.replace(/<script (?:defer )?src="\/static\/([\w./-]+\.js)(?:\?v=[\w.]+)?"/g, (m, f) => { eager.push(f); return m; });

// 1. Where the files are.
const MOVED = {
  congviec: ["improvement-candidates.css", "improvement-experiments.js", "improvement-candidates.js", "studio.js", "workspace.js"],
  packs: ["messenger-connect.js"],
};
Object.keys(MOVED).forEach(group => MOVED[group].forEach(f => {
  check(f + " loads with the group \"" + group + "\"", files(group).includes(f), files(group));
  check(f + " is not loaded when the app opens",
    !eager.includes(f) && !new RegExp('<link rel="stylesheet" href="/static/' + f.replace(/[.]/g, "\\.")).test(html));
}));
const work = files("congviec");
const at = f => work.indexOf(f);
check("the group's CSS comes before its code", at("improvement-candidates.css") === 0, work);
check("studio.js runs after the files it calls at draw time, and before workspace.js, which borrows its editors",
  at("improvement-experiments.js") < at("improvement-candidates.js") && at("improvement-candidates.js") < at("studio.js")
  && at("studio.js") < at("workspace.js"), work);
check("workspace.js runs after the job tab it calls (agent-jobs.js)", at("agent-jobs.js") >= 0 && at("agent-jobs.js") < at("workspace.js"), work);
check("messenger-connect.js runs before packs.js", files("packs").indexOf("messenger-connect.js") < files("packs").indexOf("packs.js"), files("packs"));

// 2. Pages wait for the code they draw with.
const con = read("dashboard/console.js");
const map = (con.match(/const NHOM_TRANG = \{([\s\S]*?)\};/) || [])[1] || "";
check("the Skills page waits for studio.js", /skills: \["congviec"\]/.test(map), map);
check("the partners page and the Teams page still wait for the same group",
  /workspace: \["congviec"\]/.test(map) && /teams: \["congviec", "teams"\]/.test(map), map);
check("the Connections page waits for the Messenger card", /mcp: \["packs"\]/.test(map), map);
check("every page drawn by studio.js is mapped", (() => {
  const pages = JSON.parse(((con.match(/const STUDIO_PAGES = (\[[^\]]*\]);/) || [])[1] || "[]"));
  return pages.length > 0 && pages.every(p => new RegExp("\\b" + p + ": \\[\"congviec\"").test(map));
})());

// 3. What studio.js wired at start-up lives in a file that still loads at start-up.
const app = read("dashboard/app.js");
const studio = read("dashboard/studio.js");
check("app.js owns window.openStudio", /window\.openStudio = /.test(app) && !/window\.openStudio = /.test(studio));
check("app.js binds the Studio button", /getElementById\("studioOpenBtn"\)/.test(app) && !/studioOpenBtn/.test(studio));
check("the old page names still land on the partners page", /agents: "workspace", workflows: "workspace"/.test(app));
check("app.js loads at start-up", eager.includes("app.js"));

// 4. A caller on another page loads the group before it calls in.
// The call sits next to a JavisNapCham.goi(group, fn) or .cho(group) (or console.js's _goiNhom, the same thing).
const waits = (src, group, call) => {
  const at = src.search(new RegExp(call));
  if (at < 0) return false;
  const near = src.slice(Math.max(0, at - 900), at + 900);
  return new RegExp("(JavisNapCham\\.(goi|cho)|_goiNhom)\\(\"" + group + "\"").test(near);
};
check("a /agent or /workflow command in the main chat loads the partners page first",
  waits(app, "congviec", "JavisWorkspace\\.openCommand\\(_slash\\.type"));
check("...once: a second Enter while the code loads opens nothing twice",
  /if \(!window\.JavisWorkspace && \(!window\.JavisNapCham \|\| _partnerCodeLoad\)\) return;/.test(app)
  && /_partnerCodeLoad = window\.JavisNapCham\.cho\("congviec"\)\.then\(loaded, loaded\)/.test(app));
check("...and with the code already there it still opens inside the keypress",
  /const opening = window\.JavisWorkspace \? openPartner\(\)/.test(app));
check("a partner link in chat loads it first", waits(con, "congviec", "JavisWorkspace\\.openCommand\\(m\\[1\\]"));
const notif = read("dashboard/notifications.js");
check("a notice about a partner loads it first", waits(notif, "congviec", "JavisWorkspace\\.openCommand\\(cs\\.loai"));
check("asking Javis Core about a notice loads it first", waits(notif, "congviec", "JavisWorkspace\\.openCommand\\(\"agent\", \"javis-core\""));
check("the mascot menu loads it first", waits(read("dashboard/pet.js"), "congviec", "JavisWorkspace\\.openTab\\(id\\)"));
check("the Resonance settings link loads it first",
  waits(read("dashboard/resonance-agent.js"), "congviec", "JavisWorkspace\\.openTab\\(\"agent\"\\)"));
check("the Messenger hint on the Conversations page loads the card first",
  waits(read("dashboard/conversations.js"), "packs", "JavisMessenger\\.openForm\\(null\\)"));

// 5. The loader calls at once when the group is already there, so a click keeps its gesture.
const loader = read("dashboard/nap-cham.js");
check("goi() calls at once on a loaded group", /if \(daXong\(ten\)\) \{ try \{ return Promise\.resolve\(fn\(\)\)/.test(loader));
check("the partners group is first in the background load", /UU_TIEN = \["congviec"/.test(loader));

// 6. Start-up code may only shrink. Raise this number only with a measured reason; code that one page uses belongs in
//    a lazy group (the block <script id="javis-lazy"> in index.html).
const CEILING = 3260 * 1024;
const size = eager.reduce((sum, f) => sum + fs.statSync(path.join(ROOT, "dashboard", f)).size, 0);
check("start-up JS stays under " + Math.round(CEILING / 1024) + " KB (3,572 KB before 2026-11-23, 3,208 KB after)", size <= CEILING,
  Math.round(size / 1024) + " KB in " + eager.length + " files");
console.log("     start-up JS: " + Math.round(size / 1024) + " KB in " + eager.length + " files");

console.log(fails.length ? "\nFAILED (" + fails.length + ")" : "\nALL PASS");
process.exit(fails.length ? 1 : 0);
