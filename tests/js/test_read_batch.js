/* Batched reads in the dashboard (2026-11-08, performance stage 2). fetch-gop.js learns which reads each moment of the
   app makes (its start, a console page, a chat switch) and the next time sends them together to POST /batch; the
   modules' own reads then find their answers waiting. Server side: server/read_batch.py, tests/python/test_read_batch.py.

   Pinned here:
   - the first visit of a moment records its reads; the next one sends exactly those in one batch, and the modules'
     reads are served from it without a request of their own;
   - a chat switch is learned as a template: the next chat's own id is put in;
   - a failed batch, a read the batch left out, a read with its own headers all go to the server as before;
   - a write while a batch is in flight never strands a read already waiting on it (the cause of the report below);
   - a batch that never answers costs at most ANSWER_WAIT_MS, then the read goes to the server and the tab stops
     batching (customer report 2026-11-08: the Partners chat box stayed locked after the update, Ctrl+Shift+R or not);
   - a write drops the answers on their way; the batch itself never drops the page copies;
   - app.js starts a "chat" moment on each switch, console.js a page moment on each page draw, fetch-gop.js the "boot"
     moment as it loads.

    node tests/js/test_read_batch.js
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const fails = [];
const check = (name, cond, extra) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra !== undefined ? "  " + JSON.stringify(extra) : ""));
  if (!cond) fails.push(name);
};
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const O = "https://j.example";

function load(opts) {
  opts = opts || {};
  const net = [];
  const store = {};
  const win = new EventTarget();
  const json = (b, s) => new Response(JSON.stringify(b), { status: s || 200, headers: { "Content-Type": "application/json" } });
  Object.assign(win, {
    location: { origin: O },
    localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
    fetch: (url, init) => {
      const m = (init && init.method) || "GET";
      net.push(m + " " + url);
      if (url === "/batch") {
        if (opts.batchFails) return Promise.resolve(new Response("no", { status: 500 }));
        if (opts.batchHangs) return new Promise(() => {});   // a read stuck on the server, or a proxy holding the stream
        const paths = JSON.parse(init.body).paths.filter((p) => !(opts.leaveOut || []).includes(p));
        const body = paths.map((p) => "data: " + JSON.stringify({ p, s: 200, t: "application/json", b: JSON.stringify({ from: "batch", p }) }) + "\n\n").join("");
        return new Promise((r) => setTimeout(() => r(new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } })), 5));
      }
      return new Promise((r) => setTimeout(() => r(json({ from: "server", p: url })), 5));
    },
  });
  const ctx = vm.createContext({ window: win, location: win.location, localStorage: win.localStorage, Response, CustomEvent,
    URL, Promise, Date, setTimeout, clearTimeout, TextDecoder, document: {} });
  vm.runInContext(read("dashboard/fetch-gop.js"), ctx);
  return { win, F: win.JavisFetchGop, net, store };
}
const get = async (win, u, init) => (await win.fetch(u, init)).json();

async function learnAndSend() {
  const { win, F, net, store } = load();
  check("the app's start is a moment of its own", net.length === 0 && Object.keys(store).length === 0);
  F.visit("page:tasks");
  await get(win, "/kanban?brain=b"); await get(win, "/reminders?brain=b"); await get(win, "/version");
  await wait(2700);
  const man = JSON.parse(store["javis.batch.page:tasks"] || "[]");
  check("a moment records the reads it made (only those a batch may carry)",
    man.length === 2 && man.includes("/kanban?brain=b") && man.includes("/reminders?brain=b"), man);
  net.length = 0;
  F.visit("page:tasks");
  check("the next time, they leave together in one batch", net.length === 1 && net[0] === "POST /batch");
  const a = await get(win, "/kanban?brain=b"), b = await get(win, "/reminders?brain=b");
  check("the modules' reads are answered from the batch, no request of their own",
    a.from === "batch" && b.from === "batch" && net.length === 1, net);
  const h = await get(win, "/kanban?brain=b", { headers: { "X-Own": "1" } });
  check("a read with its own headers still goes to the server", h.from === "server");
}

async function chatTemplate() {
  const { win, F, net, store } = load();
  F.visit("chat", { sid: "aaaaaa111111" });
  await get(win, "/sessions/aaaaaa111111/meta");
  await get(win, "/background?brain=b&chat_id=web%3Aaaaaaa111111");
  await wait(2700);
  const man = JSON.parse(store["javis.batch.chat"] || "[]");
  check("a chat switch is learned with the chat id left open", man.includes("/sessions/{sid}/meta")
    && man.includes("/background?brain=b&chat_id=web%3A{sid}"), man);
  net.length = 0;
  F.visit("chat", { sid: "bbbbbb222222" });
  await wait(10);
  const m = await get(win, "/sessions/bbbbbb222222/meta");
  check("the next switch batches the reads of the NEW chat", m.from === "batch" && m.p === "/sessions/bbbbbb222222/meta" && net.length === 1);
}

async function fallbacks() {
  let t = load({ batchFails: true });
  t.F.visit("page:x"); await get(t.win, "/skills?brain=b"); await get(t.win, "/plugins?brain=b"); await wait(2700);
  t.net.length = 0;
  t.F.visit("page:x");
  const s = await get(t.win, "/plugins?brain=b");
  check("a failed batch: the read goes to the server", s.from === "server" && t.net.length === 2);

  t = load({ leaveOut: ["/teams?brain=b"] });
  t.F.visit("page:y"); await get(t.win, "/teams?brain=b"); await get(t.win, "/kanban?brain=b"); await wait(2700);
  t.net.length = 0;
  t.F.visit("page:y");
  const left = await get(t.win, "/teams?brain=b");
  check("a read the batch left out goes to the server", left.from === "server");

  t = load();
  t.F.visit("page:z"); await get(t.win, "/kanban?brain=b"); await get(t.win, "/reminders?brain=b"); await wait(2700);
  t.F.visit("page:z");
  await t.win.fetch("/kanban/move", { method: "POST", body: "x" });
  const after = await get(t.win, "/kanban?brain=b");
  check("a write drops the answers on their way: the read after it asks the server", after.from === "server");
}

// The real cause of the 2026-11-08 report: a partner click reads the chat's messages from the batch and, at the same
// moment, posts /seen. That write replaced `pending`, the batch's answers were looked up there and found no one, and the
// read already waiting never got its answer: the chat box stayed locked.
async function writeDuringBatch() {
  const t = load();
  t.F.visit("chat", { sid: "ffffff666666" });
  await get(t.win, "/sessions/ffffff666666?limit=30&tools=0"); await get(t.win, "/sessions/ffffff666666/meta");
  await wait(2700);
  t.F.visit("chat", { sid: "gggggg777777" });
  const t0 = Date.now();
  const waiting = get(t.win, "/sessions/gggggg777777?limit=30&tools=0");   // starts waiting on the batch
  await t.win.fetch("/seen", { method: "POST", body: "{}" });             // a write lands while the batch is in flight
  const s = await waiting;
  const took = Date.now() - t0;
  check("a write while the batch is in flight: the read already waiting still gets its batched answer at once",
    s.from === "batch" && s.p === "/sessions/gggggg777777?limit=30&tools=0" && took < 1000, { from: s.from, took });
  check("and batching stays on", t.F.batchOff() === false);
  const after = await get(t.win, "/sessions/gggggg777777/meta");
  check("a read that starts after the write still asks the server", after.from === "server");
}

async function hangingBatch() {
  const t = load({ batchHangs: true });
  t.F.visit("chat", { sid: "cccccc333333" });
  await get(t.win, "/sessions/cccccc333333?limit=30&tools=0"); await get(t.win, "/sessions/cccccc333333/meta");
  await wait(2700);
  t.F.visit("chat", { sid: "dddddd444444" });
  check("the next switch sends a batch (which will never answer)", t.net.includes("POST /batch"), t.net);
  const t0 = Date.now();
  const s = await get(t.win, "/sessions/dddddd444444?limit=30&tools=0");
  const took = Date.now() - t0;
  check("a batch that never answers: the read goes to the server after ANSWER_WAIT_MS, not never",
    s.from === "server" && took >= t.F.ANSWER_WAIT_MS - 50 && took < t.F.ANSWER_WAIT_MS + 1500, took);
  check("the wait is a few seconds at most", t.F.ANSWER_WAIT_MS > 0 && t.F.ANSWER_WAIT_MS <= 5000);
  check("after that the tab stops batching", t.F.batchOff() === true);
  t.net.length = 0;
  t.F.visit("chat", { sid: "eeeeee555555" });
  const t1 = Date.now();
  const n = await get(t.win, "/sessions/eeeeee555555/meta");
  check("the next switch sends no batch and reads straight from the server",
    !t.net.includes("POST /batch") && n.from === "server" && Date.now() - t1 < 500, t.net);

  const f = load({ batchFails: true });
  f.F.visit("page:q"); await get(f.win, "/skills?brain=b"); await get(f.win, "/plugins?brain=b"); await wait(2700);
  f.F.visit("page:q"); await get(f.win, "/plugins?brain=b");
  check("a failed batch also stops batching for the tab", f.F.batchOff() === true);
}

function wiring() {
  const g = read("dashboard/fetch-gop.js");
  check("the batch post itself never drops the page copies", /NO_CHANGE_POSTS = [^\n]*\|batch\)/.test(g)
    && /gocThat\("\/batch"/.test(g));
  check("fetch-gop starts the boot moment as it loads", /api\.visit\("boot"\);\s*\n\}\)\(\);\s*$/.test(g));
  check("every page draw is a moment", /api\.visit\("page:" \+ page\);/.test(g));
  check("every chat switch is a moment", /window\.JavisFetchGop\.visit\("chat", \{ sid: id \}\)/.test(read("dashboard/app.js")));
  for (const f of ["dashboard/fetch-gop.js", "tests/js/test_read_batch.js"]) {
    const s = read(f);
    check(f + " has no long dash", s.indexOf(String.fromCharCode(0x2014)) < 0 && s.indexOf(String.fromCharCode(0x2013)) < 0);
  }
}

// A read stranded for good leaves no timer behind, so node would just exit with code 0 halfway: count that as a fail.
let finished = false;
process.on("exit", () => { if (!finished) { console.log("FAIL - test_read_batch ended before all checks ran (a read never got its answer)"); process.exitCode = 1; } });
learnAndSend().then(chatTemplate).then(fallbacks).then(writeDuringBatch).then(hangingBatch).then(wiring).then(() => {
  if (fails.length) { console.log("\nFAIL - test_read_batch: " + fails.length); process.exit(1); }
  finished = true;
  console.log("\nOK - test_read_batch: all pass");
}, (e) => { console.log("FAIL crashed: " + (e && e.stack || e)); process.exit(1); });
