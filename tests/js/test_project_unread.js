/* Run the real project picker logic with isolated network and page state. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.join(__dirname, "../..");
const source = fs.readFileSync(path.join(root, "dashboard/sessions-ui.js"), "utf8");

function harness() {
  const events = {}, timers = new Map(), requests = [], pending = [], storage = new Map();
  let nextTimer = 0;
  const barDot = { hidden: true };
  const menuDots = ["a", "b", "none"].map(id => ({
    getAttribute: () => id,
    dot: { hidden: true },
    querySelector() { return this.dot; },
  }));
  const bar = {
    draws: 0, html: "",
    get innerHTML() { return this.html; },
    set innerHTML(value) { this.html = value; this.draws++; },
    querySelector: selector => selector === ".cs-proj-unread" ? barDot : {},
  };
  const window = {
    addEventListener: (name, fn) => { (events[name] ||= []).push(fn); },
    JavisSessions: { brain: () => window.activeBrain, current: () => "" },
    activeBrain: "/b",
    t: key => key,
  };
  const context = vm.createContext({
    window, document: { readyState: "loading", addEventListener() {}, getElementById: () => null },
    localStorage: {
      getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value),
      removeItem: key => storage.delete(key),
    },
    setTimeout: fn => { const id = ++nextTimer; timers.set(id, fn); return id; },
    clearTimeout: id => timers.delete(id),
    fetch: url => { requests.push(url); return new Promise(resolve => pending.push(resolve)); },
    ic: () => "<svg></svg>",
  });
  const hooks = `
    window.test = {
      projectNeedsAttention, renderProjBar, openProjMenu, loadProjects, refreshProjects, refresh,
      select: setCurProject,
      state: () => projects,
      seed: function(items) {
        projects = items; projBar = window.bar; side = {}; lastBrain = brain();
        menuEl = window.menu;
        fillProjTags = function() {}; renderProjChip = function() {}; loadList = function() {};
        openMenu = function(anchor, rows) { window.menuRows = rows; };
      }
    };
  `;
  vm.runInContext(source.replace(/\}\)\(\);\s*$/, hooks + "\n})();"), context);
  window.bar = bar;
  window.menu = { querySelectorAll: () => menuDots };
  window.test.seed([{ id: "a", name: "A", unread_count: 1 }, { id: "b", name: "B", unread_count: 0 }]);
  return {
    api: window.test, window, bar, barDot, menuDots, requests,
    emit(name, detail) { for (const fn of events[name] || []) fn({ detail }); },
    flush() { const batch = [...timers.values()]; timers.clear(); for (const fn of batch) fn(); },
    respond(projects, index = 0, ungrouped = 0) {
      pending.splice(index, 1)[0]({ json: async () => ({ projects, ungrouped_unread: ungrouped }) });
    },
  };
}

async function main() {
  const h = harness();
  h.api.select("a");
  assert.equal(h.api.projectNeedsAttention(h.api.state()[0]), false, "The selected project does not duplicate row dots");
  h.api.renderProjBar();
  assert.match(h.bar.innerHTML, /cs-proj-unread[^>]*hidden/, "Only the selected project is unread: no folder alert");
  h.api.select("b");
  h.api.renderProjBar();
  assert.doesNotMatch(h.bar.innerHTML, /cs-proj-unread[^>]*hidden/, "Another project lights the selector");
  h.api.openProjMenu({});
  const rows = h.window.menuRows.filter(row => row.projectId);
  assert.equal(rows.find(row => row.projectId === "a").unread, true);
  assert.equal(rows.find(row => row.projectId === "b").unread, false);
  h.api.select("a");
  h.api.openProjMenu({});
  assert.equal(h.window.menuRows.find(row => row.projectId === "a").unread, false);

  h.api.select("b");
  const drawsBeforeReply = h.bar.draws;
  h.emit("javis:sessions-changed", { reason: "reply" });
  h.emit("javis:sessions-changed", { reason: "reply" });
  h.flush();
  h.flush();
  assert.equal(h.requests.length, 1, "Reply bursts fetch all project counts once");
  assert.match(h.requests[0], /^\/projects\?brain=/);
  h.respond([{ id: "a", name: "A", unread_count: 2 }, { id: "b", name: "B", unread_count: 1 }]);
  await new Promise(setImmediate);
  assert.equal(h.bar.draws, drawsBeforeReply, "Unread updates preserve the focused project selector");
  assert.equal(h.menuDots[0].dot.hidden, false, "An open picker updates when another project receives a reply");
  assert.equal(h.menuDots[1].dot.hidden, true, "The selected project's menu row stays quiet");

  h.emit("javis:session-read", { session_id: "outside-the-current-list" });
  h.flush();
  assert.equal(h.requests.length, 2, "Reading in another tab refreshes projects even for an unloaded chat");
  h.respond([{ id: "a", name: "A", unread_count: 0 }, { id: "b", name: "B", unread_count: 1 }]);
  await new Promise(setImmediate);
  assert.equal(h.menuDots[0].dot.hidden, true, "Reading the final reply clears the open picker dot");
  assert.equal(h.barDot.hidden, true);

  // 2026-11-20 (owner): unread chats in no project light "Chưa xếp nhóm" and the selector, like a project does.
  h.api.select("b");
  h.api.refreshProjects();
  h.flush();
  h.respond([{ id: "a", name: "A", unread_count: 0 }, { id: "b", name: "B", unread_count: 0 }], 0, 2);
  await new Promise(setImmediate);
  assert.equal(h.menuDots[2].dot.hidden, false, "An open picker lights the ungrouped row");
  assert.equal(h.barDot.hidden, false, "Ungrouped unread chats light the selector");
  h.api.openProjMenu({});
  const none = h.window.menuRows.find(row => row.projectId === "none");
  assert.ok(none && none.unread, "The ungrouped row carries the unread dot");
  h.api.select("none");
  h.api.openProjMenu({});
  assert.equal(h.window.menuRows.find(row => row.projectId === "none").unread, false,
    "Viewing the ungrouped chats: their own rows already have dots");
  h.api.renderProjBar();
  assert.match(h.bar.innerHTML, /cs-proj-unread[^>]*hidden/, "No folder alert for the list on screen");
  h.api.select("b");
  h.api.refreshProjects();
  h.flush();
  h.respond([{ id: "a", name: "A", unread_count: 0 }, { id: "b", name: "B", unread_count: 0 }], 0, 0);
  await new Promise(setImmediate);
  assert.equal(h.menuDots[2].dot.hidden, true, "Reading the last ungrouped chat clears its dot");
  assert.equal(h.barDot.hidden, true);

  // 2026-11-20 (owner): chats still running, and the chat open on screen, are skipped by the folder counts.
  h.window.JavisRunning = new Set(["run1", "run2"]);
  h.api.refreshProjects();
  h.flush();
  assert.match(h.requests[h.requests.length - 1], /&skip=run1%2Crun2$/, "Running chats are left out of folder counts");
  h.respond([{ id: "a", name: "A", unread_count: 0 }, { id: "b", name: "B", unread_count: 0 }], 0, 0);
  await new Promise(setImmediate);
  h.window.JavisRunning = new Set();
  h.api.refreshProjects();
  h.flush();
  assert.doesNotMatch(h.requests[h.requests.length - 1], /skip=/, "Nothing running: no skip list");
  h.respond([{ id: "a", name: "A", unread_count: 0 }, { id: "b", name: "B", unread_count: 0 }], 0, 0);
  await new Promise(setImmediate);

  const old = h.api.loadProjects();
  const latest = h.api.loadProjects();
  h.respond([{ id: "b", name: "Latest", unread_count: 0 }], 1);
  await latest;
  h.respond([{ id: "a", name: "Stale", unread_count: 4 }]);
  await old;
  assert.equal(h.api.state()[0].name, "Latest", "Late responses cannot restore stale unread badges");
  const previousBrain = h.api.loadProjects();
  h.window.activeBrain = "/other";
  h.respond([{ id: "a", name: "Wrong brain", unread_count: 4 }]);
  await previousBrain;
  assert.equal(h.api.state()[0].name, "Latest", "Previous brain responses are ignored");
  console.log("OK - project unread picker, reply events, cross-tab reads and stale requests");
}

main().catch(error => { console.error(error); process.exitCode = 1; });
