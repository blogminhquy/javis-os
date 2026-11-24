/* JavisModelList.refresh: ask the server again even when a list is in hand.

       node tests/js/test_model_list_refresh.js

   Owner's report 23/11/2026, "the Models page shows only 3 GPT models": the Models page picker opened on `peek` and
   asked the server only when it had nothing, so a list kept from earlier (3 models of a switched-off account) stayed on
   screen while the account in use had 10. The picker now draws what `peek` has and redraws with `refresh`.

   Runs the real model-list.js with a fake fetch and a fake clock. */
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
let answer = { models: ["gpt-6-luna", "gpt-5.6-terra", "gpt-5.6-luna"], live: true };
let hold = null;   // when set, fetch waits for this promise before answering
const sandbox = {
  window: { t: (k) => "T:" + k, ic: () => "" },
  Date: { now: () => clock },
  fetch: async (url) => {
    asked.push(url);
    const a = answer;
    if (hold) await hold;
    return { json: async () => a };
  },
  console,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(ROOT, "dashboard", "model-list.js"), "utf8"), sandbox);
const ML = sandbox.window.JavisModelList;
const PID = "openai-oauth";

(async () => {
  check("refresh is exported", typeof ML.refresh === "function");

  // ---- the old list is in hand and still "fresh" (well inside the 5-minute window) ----
  await ML.models(PID);
  check("first open loads the old 3-model list", (ML.peek(PID) || []).length === 3);
  clock += 10 * 1000;
  answer = { models: ["gpt-6.2-sol", "gpt-6.2-astra", "gpt-6.1-terra", "gpt-6.1-sol", "gpt-6-astra",
                      "gpt-6-sol", "gpt-6-luna", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"], live: true };
  const before = asked.length;
  const viaModels = await ML.models(PID);
  check("CANARY: models() inside the window still hands out the kept list without asking",
    viaModels.length === 3 && asked.length === before);

  const fresh = await ML.refresh(PID);
  check("refresh asks the server even though a fresh-looking list is in hand", asked.length === before + 1);
  check("...and resolves with the list the server has now (10)", fresh.length === 10, fresh.length);
  check("...which replaces the kept one for every later reader", (ML.peek(PID) || []).length === 10);
  check("Codex is asked with refresh=1 so the server skips its own cache too", /refresh=1/.test(asked[asked.length - 1]));

  // ---- two opens at once share one request ----
  let release;
  hold = new Promise((r) => { release = r; });
  const n = asked.length;
  const a = ML.refresh(PID), b = ML.refresh(PID);
  check("two refreshes at once send one request", asked.length === n + 1, asked.length - n);
  release();
  hold = null;
  const [ra, rb] = await Promise.all([a, b]);
  check("...and both get the answer", ra.length === 10 && rb.length === 10);

  // ---- an account switch on the Models page (clearCache) drops an answer asked before it ----
  release = null;
  hold = new Promise((r) => { release = r; });
  answer = { models: ["old-account-model"], live: true };
  const stale = ML.refresh(PID);
  ML.clearCache();
  hold = null;
  answer = { models: ["new-account-model"], live: true };
  release();
  await stale;
  check("an answer asked before clearCache is not kept", ML.peek(PID) === null, String(ML.peek(PID)));
  const after = await ML.refresh(PID);
  check("the next refresh asks again and keeps the new account's list", after[0] === "new-account-model");

  console.log();
  if (fails.length) {
    console.log(fails.length + " FAIL");
    process.exit(1);
  }
  console.log("All model-list refresh tests passed.");
})();
