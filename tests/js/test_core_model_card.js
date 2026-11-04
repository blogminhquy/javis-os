/* The model row on the Javis Core card of the Agents page (0.461.0, owner 04/11/2026: an empty model slot read as
 * "Javis Core has no model"). texts() turns GET /javis-core/model into the button text and the line under it.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.resolve(__dirname, "..", "..");
let fails = 0;
function check(name, cond, extra) { console.log((cond ? "ok   " : "FAIL ") + name + (cond ? "" : "  [" + extra + "]")); if (!cond) fails++; }

const sandbox = {
  window: { t: (k, v) => k + (v && v.m ? "(" + v.m + ")" : "") },
  console, Promise,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(ROOT, "dashboard", "core-model.js"), "utf8"), sandbox);
const CM = sandbox.window.JavisCoreModel;
const PROVS = [{ id: "anthropic-cli", label: "Claude Code" }, { id: "groq", label: "Groq" }];

let x = CM.texts({ pinned: false, main_provider: "anthropic-cli", main_model: "opus", run_provider: "anthropic-cli", run_model: "opus" }, PROVS, {});
check("no pin: the button names the main model it follows", x.button === "ws.core_model_follow(Claude Code · opus)", x.button);
check("no pin: no extra line, no follow button", !x.sub && !x.follow, JSON.stringify(x));
x = CM.texts({ pinned: false, main_provider: "anthropic-cli", main_model: "", run_provider: "anthropic-cli", run_model: "" },
             PROVS, { "anthropic-cli": "claude-opus-5-5" });
check("no model set: the provider's known default is named", x.button === "ws.core_model_follow(Claude Code · claude-opus-5-5)", x.button);
x = CM.texts({ pinned: false, main_provider: "anthropic-cli", main_model: "opus", run_provider: "groq", run_model: "m1" }, PROVS, {});
check("main model down: the line says what really runs", x.sub === "ws.core_model_main_down(Groq · m1)", x.sub);
x = CM.texts({ pinned: true, pinned_provider: "groq", pinned_model: "qwen3-32b", pin_ok: true, main_provider: "anthropic-cli",
               run_provider: "groq", run_model: "qwen3-32b" }, PROVS, {});
check("pinned: the button names the pin", x.button === "Groq · qwen3-32b", x.button);
check("pinned: says it is a Core pin and offers to follow the main model", x.sub === "ws.core_model_pinned" && x.follow, JSON.stringify(x));
x = CM.texts({ pinned: true, pinned_provider: "groq", pinned_model: "q", pin_ok: false, main_provider: "anthropic-cli",
               run_provider: "anthropic-cli", run_model: "opus" }, PROVS, {});
check("broken pin: the line says the main model runs instead", x.sub === "ws.core_model_broken(Claude Code · opus)" && x.follow, x.sub);

const src = fs.readFileSync(path.join(ROOT, "dashboard", "core-model.js"), "utf8");
check("the list shows connected providers only, like the chat model bar", /connectedOnly:\s*true/.test(src), "");
check("it saves through the Core endpoint", src.includes('"/javis-core/model"'), "");
const ws = fs.readFileSync(path.join(ROOT, "dashboard", "workspace.js"), "utf8");
check("the Core card mounts the row", ws.includes("JavisCoreModel.mount("), "");
const html = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");
check("core-model.js loads after model-list.js and before workspace.js",
      html.indexOf("/static/model-list.js") < html.indexOf("/static/core-model.js") && html.indexOf("/static/core-model.js") < html.indexOf("/static/workspace.js"), "");
const mp = fs.readFileSync(path.join(ROOT, "dashboard", "model-picker.js"), "utf8");
check("the chat model bar tells the card and listens to it", mp.includes('"javis:core-model"') && mp.includes("coreChanged()") &&
      mp.includes("addEventListener(CORE_EVENT"), "");
if (fails) { console.log("\nFAILED " + fails); process.exit(1); }
console.log("\nOK - test_core_model_card");
