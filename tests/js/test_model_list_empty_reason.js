/* The shared model list (dashboard/model-list.js) when a provider has NO list to show.

       node tests/js/test_model_list_empty_reason.js

   13/11/2026: a user's picker said "Could not load the model list" under OpenAI Compatible and nothing else. The
   server had the reason all along (`error` of /provider/models: wrong address, refused key, a seller that lists
   nothing) and the picker threw it away. Worse, the empty answer was kept for five minutes and then handed out once
   more, so the picker stayed empty long after the card was fixed on the Models page.

   Runs the real render with a fake fetch and a fake clock. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

let clock = 1000000;
const asked = [];
const ANSWER = {};   // provider id -> what /provider/models answers now
const sandbox = {
  window: { t: (k) => "T:" + k, ic: (n) => `<i data-ic="${n}"></i>` },
  Date: { now: () => clock },
  fetch: async (url) => {
    const pid = decodeURIComponent((url.match(/provider=([^&]+)/) || [])[1] || "");
    asked.push(pid);
    const a = ANSWER[pid];
    if (a === "down") throw new Error("network down");
    return { json: async () => a };
  },
  console,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(ROOT, "dashboard", "model-list.js"), "utf8"), sandbox);
const ML = sandbox.window.JavisModelList;
const PROVS = [
  { id: "openai-compat", label: "OPENAI COMPATIBLE", configured: true },
  { id: "anthropic-compat", label: "CLAUDE COMPATIBLE", configured: true },
];
const count = (pid) => asked.filter((x) => x === pid).length;

(async () => {
  for (const pid of ["openai-compat", "anthropic-compat"]) {
    const WHY = "api.example.com did not return a model list (HTTP 404). <b>Open</b> the Models page.";
    // ---- 1. an empty list shows the server's reason and the way to the Models page ----
    ANSWER[pid] = { models: [], live: false, error: WHY };
    let h = await ML.render({ providers: PROVS, expanded: pid });
    check(pid + ": the empty list still says there is no list", h.includes("T:mpick.no_list"));
    check(pid + ": ...followed by the server's reason, escaped",
      h.includes("api.example.com did not return a model list (HTTP 404). &lt;b&gt;Open&lt;/b&gt;"), h);
    check(pid + ": ...and a link to the Models page",
      /class="mb-link" data-goto="models">T:mpick\.fix_on_models</.test(h), h);
    check(pid + ": why() gives the reason to a caller", ML.why(pid) === WHY, ML.why(pid));

    // ---- 2. a redraw right after does not ask again (one popup draws several times) ----
    const n1 = count(pid);
    await ML.render({ providers: PROVS, expanded: pid });
    check(pid + ": a redraw within seconds reuses the answer", count(pid) === n1, count(pid) - n1);

    // ---- 3. the next open asks AGAIN instead of repeating the old empty list ----
    clock += 10 * 1000;
    ANSWER[pid] = { models: ["fixed-model"], live: true };
    check(pid + ": an old empty answer counts as not loaded", ML.peek(pid) === null);
    h = await ML.render({ providers: PROVS, expanded: pid });
    check(pid + ": opened again later, the picker shows the list that is there now",
      h.includes('data-model="fixed-model"') && !h.includes("T:mpick.no_list"), h);
    check(pid + ": ...and the reason is gone", ML.why(pid) === "");

    // noWait (the chat composer): an old empty answer draws "loading" and waits, never the stale empty line
    ANSWER[pid] = { models: [], live: false, error: WHY };
    ML.clearCache();
    await ML.models(pid);
    clock += 10 * 1000;
    ANSWER[pid] = { models: ["late-model"], live: true };
    const o = { providers: PROVS, expanded: pid, noWait: true };
    h = await ML.render(o);
    check(pid + ": noWait draws 'loading' for an old empty answer", h.includes("T:mpick.loading") && o.cho.length === 1, h);
    await Promise.all(o.cho);
    h = await ML.render({ providers: PROVS, expanded: pid, noWait: true });
    check(pid + ": ...then the list", h.includes('data-model="late-model"'), h);

    // ---- 4. a list in hand survives a network failure ----
    clock += 6 * 60 * 1000;   // past the five-minute refresh
    ANSWER[pid] = "down";
    await ML.models(pid);                       // returns the old list, refreshes behind
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    check(pid + ": a failed refresh keeps the list in hand",
      JSON.stringify(await ML.models(pid)) === JSON.stringify(["late-model"]), JSON.stringify(ML.peek(pid)));

    // ---- 5. a first load that fails outright: empty, no reason invented, link still there ----
    ML.clearCache();
    h = await ML.render({ providers: PROVS, expanded: pid });
    check(pid + ": a failed first load shows the plain line and the link",
      h.includes("T:mpick.no_list") && h.includes('data-goto="models"') && ML.why(pid) === "", h);
    ML.clearCache();
  }

  // ---- 6. search reads what is in hand: a dead gateway is not asked again on every keystroke ----
  ANSWER["openai-compat"] = { models: [], live: false, error: "x" };
  ANSWER["anthropic-compat"] = { models: ["claude-x"], live: true };
  await ML.models("openai-compat");
  await ML.models("anthropic-compat");
  clock += 60 * 1000;
  const before = count("openai-compat");
  const o = { providers: PROVS, filter: "claude" };
  const h = await ML.render(o);
  check("search does not ask the empty provider again", count("openai-compat") === before && o.cho.length === 0, o.cho.length);
  check("search still finds the other provider's model", h.includes('data-model="claude-x"'), h);

  // ---- 7. the Models page drops the kept lists after it changes a key or a gateway ----
  const cs = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
  check("console.js has forgetModelLists() calling clearCache", /function forgetModelLists\(\)[\s\S]{0,160}JavisModelList\.clearCache\(\)/.test(cs));
  check("saving the model section forgets the lists", /if \(section === "model"\) \{ forgetModelLists\(\);/.test(cs));
  const connects = cs.split("forgetModelLists();").length - 1;
  check("each gateway connect (old card forms and the key sheet) forgets them too", connects >= 4, connects);
  for (const lang of ["vi", "en"]) {
    const d = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", lang + ".json"), "utf8"));
    check(lang + ".json has mpick.fix_on_models", !!d["mpick.fix_on_models"]);
  }

  if (fails.length) { console.log("\n" + fails.length + " FAILED:\n  - " + fails.join("\n  - ")); process.exit(1); }
  console.log("\nAll green.");
})();
