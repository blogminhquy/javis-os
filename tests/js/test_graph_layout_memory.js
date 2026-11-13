/* The brain graph starts from where it last settled (graph.js, 2026-11-12).

       node tests/js/test_graph_layout_memory.js

   Owner: "tối ưu tốc độ tải và tốc độ khởi động ... để không gặp tình trạng giựt lag đơ". Measured with 2,600 notes on a
   simulated phone: opening the home screen blocked the page for 1.1 s in one go (the library's 24 warm-up steps over
   every dot) and then stuttered through five seconds of physics, 3.3 s blocked in all, on EVERY opening and again each
   time Javis wrote a note. Now where the dots came to rest is kept in the browser (numbers only: a hash of the note id
   and two coordinates) and the next opening starts from that picture: no warm-up, a short settle for new notes, and no
   physics at all once the layout is settled or the machine proved too slow to animate it. Same measurement: 0.5 s. */
const path = require("path");
const root = path.join(__dirname, "..", "..");

let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const store = {};
global.localStorage = {
  getItem: (k) => (Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: (k) => { delete store[k]; },
};
let clock = 1000;
global.performance = { now: () => clock };
global.window = global;
global.document = { createElement: () => ({ getContext: () => null }) };
global.window.dispatchEvent = () => {};
global.window.addEventListener = () => {};

require(path.join(root, "dashboard", "graph.js"));
const JavisGraph = window.JavisGraph;
const M = JavisGraph._layoutMemory;

// A stand-in for the force-graph library: records what the graph asks of it.
function fakeLib() {
  const g = { calls: [], data: { nodes: [], links: [] }, handlers: {} };
  const chain = (name) => function (v) { g.calls.push([name, v]); if (name === "onEngineStop" || name === "onEngineTick") g.handlers[name] = v; return api; };
  const api = {};
  ["backgroundColor", "autoPauseRedraw", "nodeId", "nodeRelSize", "nodeVal", "warmupTicks", "cooldownTime", "linkColor",
    "linkWidth", "nodeCanvasObjectMode", "nodeCanvasObject", "onNodeHover", "onNodeClick", "onNodeDrag", "onNodeDragEnd",
    "onBackgroundClick", "maxZoom", "onEngineStop", "onEngineTick", "width", "height", "zoomToFit"].forEach((n) => { api[n] = chain(n); });
  api.minZoom = function (v) { g.calls.push(["minZoom", v]); return api; };
  g.running = true;   // the library's own frame loop
  api.pauseAnimation = function () { g.running = false; g.calls.push(["pauseAnimation"]); return api; };
  api.resumeAnimation = function () { g.running = true; g.calls.push(["resumeAnimation"]); return api; };
  api.zoom = () => 1;
  api.d3Force = () => ({ strength() { return this; }, distance() { return this; } });
  api.graphData = function (d) { if (d === undefined) return g.data; g.data = d; g.calls.push(["graphData", d.nodes.length]); return api; };
  g.api = api;
  g.last = (name) => { const c = g.calls.filter((x) => x[0] === name); return c.length ? c[c.length - 1][1] : undefined; };
  return g;
}

function notes(n, from) {
  const out = [];
  for (let i = from || 0; i < (from || 0) + n; i++) out.push({ id: "wiki/note-" + i + ".md", label: "note " + i, links: 1 });
  return out;
}
function edges(list) { return list.slice(1).map((n, i) => ({ source: list[i].id, target: n.id })); }

async function open(nodeList, lib) {
  global.window.ForceGraph = () => () => lib.api;
  global.fetch = async () => ({ ok: true, json: async () => ({ nodes: nodeList.map((n) => ({ ...n })), edges: edges(nodeList) }) });
  const g = new JavisGraph({ clientWidth: 800, clientHeight: 600, style: {}, addEventListener() {} });
  await g.load("source=brain");
  return g;
}
// Let the physics "run": place every dot, tick, then stop after `ms`.
function run(g, lib, ticks, ms) {
  lib.data.nodes.forEach((n, i) => { if (typeof n.x !== "number") { n.x = i * 10; n.y = -i * 5; } });
  for (let i = 0; i < ticks; i++) lib.handlers.onEngineTick();
  clock += ms;
  lib.handlers.onEngineStop();
}

(async () => {
  // ───────── first opening: nothing remembered ─────────
  const list = notes(40);
  let lib = fakeLib();
  let g = await open(list, lib);
  check("nothing remembered: a small graph keeps its 24 warm-up steps and five seconds of physics",
    lib.last("warmupTicks") === 24 && lib.last("cooldownTime") === 5000);
  check("the warm-up shrinks as the graph grows (it runs in one go before the first frame)",
    JavisGraph.warmupFor(40, "") === 24 && JavisGraph.warmupFor(900, "") === 12 && JavisGraph.warmupFor(2600, "") === 6);
  check("nothing is kept before the physics has stopped", !store[M.KEY + "source=brain"]);
  run(g, lib, 191, 5000);   // a fast machine: 38 steps a second
  const rec = JSON.parse(store[M.KEY + "source=brain"] || "null");
  check("when the physics stops the layout is kept: three numbers per note, no name and no path",
    !!rec && rec.p.length === 40 * 3 && rec.p.every((v) => typeof v === "number") && !/note|wiki/.test(store[M.KEY + "source=brain"]));
  check("with the steps it has had (warm-up included) and the machine is not marked slow", rec.t === 24 + 191 && rec.s === 0);
  check("after a stop a drag reheats for the usual five seconds", lib.last("cooldownTime") === 5000);

  // ───────── second opening: remembered, not settled yet ─────────
  lib = fakeLib();
  g = await open(list, lib);
  check("remembered: the dots start where they stood", lib.data.nodes.every((n, i) => n.x === i * 10 && n.y === -i * 5));
  check("no warm-up, a short settle", lib.last("warmupTicks") === 0 && lib.last("cooldownTime") === 1500);
  check("while it settles the dots fade in as before", g._t0 > 0);
  check("and the picture is framed at once, not after the physics", lib.calls.some((c) => c[0] === "zoomToFit" && c[1] === 0));
  run(g, lib, 90, 1500);
  check("the steps add up over openings", JSON.parse(store[M.KEY + "source=brain"]).t === 24 + 191 + 90);

  // ───────── third opening: settled ─────────
  lib = fakeLib();
  g = await open(list, lib);
  check("a settled layout that did not change runs no physics at all", lib.last("warmupTicks") === 0 && lib.last("cooldownTime") === 0);
  // Drawn once and for good: no fade-in (it needs a redraw on every frame, and one frame caught mid-fade would stay
  // dim), and no second, animated framing when the library reports the stop of physics that never ran.
  check("it is drawn at full strength from the first frame (no fade-in)", g._t0 === 0);
  const fitsBefore = lib.calls.filter((c) => c[0] === "zoomToFit").length;
  lib.handlers.onEngineStop();
  check("and framed once: the stop does not frame it again", lib.calls.filter((c) => c[0] === "zoomToFit").length === fitsBefore && fitsBefore === 1);

  // ───────── a few new notes ─────────
  const more = list.concat(notes(2, 40));
  lib = fakeLib();
  g = await open(more, lib);
  const fresh = lib.data.nodes.filter((n) => /note-4[01]/.test(n.id));
  const prev = lib.data.nodes.find((n) => n.id === "wiki/note-39.md");
  check("new notes get a short settle, still no warm-up", lib.last("warmupTicks") === 0 && lib.last("cooldownTime") === 1500);
  check("a new note starts beside a note it links to, not in the middle",
    typeof fresh[0].x === "number" && Math.abs(fresh[0].x - prev.x) <= 20 && Math.abs(fresh[0].y - prev.y) <= 20);

  // ───────── a different graph: too little remembered ─────────
  lib = fakeLib();
  g = await open(notes(40, 500), lib);
  check("another set of notes is laid out from scratch", lib.last("warmupTicks") === 24 && lib.last("cooldownTime") === 5000
    && lib.data.nodes.every((n) => typeof n.x !== "number"));

  // ───────── a slow machine ─────────
  Object.keys(store).forEach((k) => delete store[k]);
  lib = fakeLib();
  g = await open(list, lib);
  run(g, lib, 36, 5000);   // a phone: 7 steps a second, each one a visible stutter
  check("a machine too slow to animate the settling is remembered as such", JSON.parse(store[M.KEY + "source=brain"]).s === 1
    && JavisGraph.slowRun(36, 5000) && !JavisGraph.slowRun(191, 5000));
  lib = fakeLib();
  g = await open(list, lib);
  check("it keeps the layout it ended on: no physics on the next opening", lib.last("cooldownTime") === 0);
  lib = fakeLib();
  g = await open(list, lib);
  clock += 60000;            // the page was left while the physics ran: the loop was paused, this says nothing
  lib.handlers.onEngineStop();
  check("a run that was paused does not change the verdict", JSON.parse(store[M.KEY + "source=brain"]).s === 1);

  // ───────── a note Javis writes while the graph is open ─────────
  lib = fakeLib();
  g = await open(list, lib);
  lib.calls.length = 0;
  g.addOrUpdate({ id: "wiki/new.md", label: "new", links: 1 }, ["wiki/note-3.md"], true);
  const added = lib.data.nodes.find((n) => n.id === "wiki/new.md"), near = lib.data.nodes.find((n) => n.id === "wiki/note-3.md");
  check("a new note joins without the warm-up over every dot", lib.last("warmupTicks") === 0 && lib.last("cooldownTime") === 1500);
  check("and appears beside the note it links to", Math.abs(added.x - near.x) <= 20 && Math.abs(added.y - near.y) <= 20);

  // ───────── the library's loop sleeps when nothing can change the picture ─────────
  {
    const timers = [];
    const realSet = global.setTimeout, realClear = global.clearTimeout;
    global.setTimeout = (fn, ms) => { const t = { fn, at: clock + (ms || 0), off: false }; timers.push(t); return t; };
    global.clearTimeout = (t) => { if (t) t.off = true; };
    const pass = (ms) => { clock += ms; for (;;) { const due = timers.filter((t) => !t.off && t.at <= clock); if (!due.length) break; due.forEach((t) => { t.off = true; t.fn(); }); } };
    lib = fakeLib();
    g = await open(list, lib);
    check("while the physics runs the loop runs", lib.running === true);
    lib.handlers.onEngineStop();
    check("right after the stop it still runs: the camera is gliding into place", lib.running === true);
    pass(2000);
    check("then, with nothing moving, the loop is paused", lib.running === false);
    g.setThinking(true);
    check("thinking wakes it", lib.running === true);
    g.setThinking(false);
    pass(JavisGraph.AN_HAN_MS + 100);
    check("and it sleeps again once the grace period is over", lib.running === false);
    g.resize();
    check("a new size wakes it for the redraw", lib.running === true);
    pass(1000);
    check("only for that redraw", lib.running === false);
    g.spotlightCategory("wiki");
    check("a highlighted category is drawn at once", lib.running === true);
    pass(1000);
    g.addOrUpdate({ id: "wiki/later.md", label: "later", links: 0 }, [], true);
    check("a new note wakes it until the physics stops again", lib.running === true);
    pass(3000);
    check("(still running: the library has not reported the stop)", lib.running === true);
    lib.handlers.onEngineStop(); pass(2000);
    check("stopped: asleep", lib.running === false);
    g.pause();
    g.resize();
    check("another page in front: nothing wakes it", lib.running === false);
    g.wake();
    check("back on the home screen: one redraw", lib.running === true);
    pass(1000);
    check("then asleep again", lib.running === false);
    global.setTimeout = realSet; global.clearTimeout = realClear;
  }

  // ───────── storage ─────────
  Object.keys(store).forEach((k) => delete store[k]);
  const pts = notes(3).map((n, i) => ({ ...n, x: i, y: i }));
  ["a", "b", "c", "d"].forEach((q) => M.save("source=" + q, pts, 300, false));
  check("at most " + M.KEEP + " graphs are kept per browser, the oldest goes",
    !store[M.KEY + "source=a"] && !!store[M.KEY + "source=d"] && JSON.parse(store[M.INDEX]).length === M.KEEP);
  global.localStorage.setItem = () => { throw new Error("quota"); };
  check("a full or blocked storage is not an error", M.save("source=z", pts, 1, false) === false);
  store[M.KEY + "source=bad"] = "{not json";
  check("a damaged record reads as nothing remembered", M.load("source=bad") === null);

  if (fails.length) { console.log("\nFAIL - test_graph_layout_memory: " + fails.length); process.exit(1); }
  console.log("\nOK - test_graph_layout_memory: all pass");
})();
