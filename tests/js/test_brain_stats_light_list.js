// The three counts on the home screen (agents, skills, workflows) only need the LENGTH of each list, so the agent list
// is asked for without system prompts (speed review 2026-11-23, item A4: the full list was 75 KB gzipped against 4 KB).
// Run: node tests/js/test_brain_stats_light_list.js
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");

let fails = 0;
function check(name, cond, info) { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && info ? "  [" + info + "]" : "")); if (!cond) fails++; }

const APP = read("app.js");
const start = APP.indexOf("async function loadBrainStats()");
const end = APP.indexOf("window.loadBrainStats = loadBrainStats", start);
check("loadBrainStats is found in app.js", start !== -1 && end > start);
const SRC = APP.slice(start, end);

// Run the real function body against a fake server.
const asked = [];
const shown = {};
const lists = {
  agents: { agents: [{ slug: "a" }, { slug: "b" }, { slug: "c" }] },
  skills: { skills: [{ slug: "s1" }, { slug: "s2" }] },
  workflows: { workflows: [{ slug: "w1" }] },
};
const fakeFetch = (url) => {
  asked.push(url);
  const kind = url.split("?")[0].slice(1);
  return Promise.resolve({ json: () => Promise.resolve(lists[kind] || {}) });
};
const load = new Function("fetch", "currentBrainPath", "_setStat", SRC + "\nreturn loadBrainStats;")(
  fakeFetch, () => "/brains/My Brain", (id, n) => { shown[id] = n; });

(async () => {
  await load();
  const agentUrl = asked.find((u) => u.startsWith("/agents")) || "";
  check("three reads, one per list", asked.length === 3, asked.join(" "));
  check("the agent list is asked for without system prompts", /[?&]prompt=0(&|$)/.test(agentUrl), agentUrl);
  check("no read of the full agent list is left", !asked.some((u) => u.startsWith("/agents") && !/[?&]prompt=0(&|$)/.test(u)));
  check("the brain is still sent, encoded", agentUrl.indexOf("brain=" + encodeURIComponent("/brains/My Brain")) !== -1, agentUrl);
  check("the counts shown are the list lengths",
    shown.statAgents === 3 && shown.statSkills === 2 && shown.statWorkflows === 1, JSON.stringify(shown));

  // The "/" menu and the + menu ask for the same list at start-up. The same address lets fetch-gop.js answer all of
  // them with one request instead of adding a second one.
  global.window = { location: { origin: "http://x" } };
  const gop = require(path.join(ROOT, "dashboard", "fetch-gop.js"));
  const slashUrl = "/agents" + "?prompt=0&brain=" + encodeURIComponent("/brains/My Brain");
  check("chat-slash.js still builds the address this test compares with",
    read("chat-slash.js").indexOf('"?prompt=0&brain="') !== -1);
  check("the address is one fetch-gop.js shares", gop.khoaGop(agentUrl, undefined, "http://x") !== "");
  check("it shares one request with the \"/\" menu",
    gop.khoaGop(agentUrl, undefined, "http://x") === gop.khoaGop(slashUrl, undefined, "http://x"),
    agentUrl + " vs " + slashUrl);

  // A failed read leaves a zero, never an exception that would stop the other two counts.
  asked.length = 0;
  const failing = new Function("fetch", "currentBrainPath", "_setStat", SRC + "\nreturn loadBrainStats;")(
    (url) => url.startsWith("/agents") ? Promise.reject(new Error("offline")) : fakeFetch(url),
    () => "brain", (id, n) => { shown[id] = n; });
  await failing();
  check("a failed agent read shows 0 and keeps the other counts", shown.statAgents === 0 && shown.statSkills === 2);

  console.log(fails ? "\n" + fails + " failed" : "\nall passed");
  process.exit(fails ? 1 : 0);
})();
