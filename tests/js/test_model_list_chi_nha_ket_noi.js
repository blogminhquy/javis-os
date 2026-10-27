/* The chat composer's model picker lists connected providers only (0.350.0).
 * docs/dev/2026-10-model-routing-spec.md 2.6: the owner asked to hide every provider that still needs a login or key.
 * The assistant's model list (studio.js) keeps the locked rows, so the option is opt-in.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.resolve(__dirname, "..", "..");
let hong = 0;
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) hong++; }

const sandbox = {
  window: { t: (k) => "T:" + k, ic: (n) => '<i data-ic="' + n + '"></i>' },
  fetch: async () => ({ json: async () => ({ models: ["m1", "m2"] }) }),
  console, Date, Promise, setTimeout,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(ROOT, "dashboard", "model-list.js"), "utf8"), sandbox);
const ML = sandbox.window.JavisModelList;
const PROVS = [
  { id: "a", label: "Connected A", configured: true },
  { id: "b", label: "Locked B", configured: false },
];

(async () => {
  let h = await ML.render({ providers: PROVS, expanded: "a", connectedOnly: true });
  check("connectedOnly: locked provider is not listed", !h.includes("Locked B") && !h.includes('data-goto="models"'));
  check("connectedOnly: connected provider still listed with its models", h.includes("Connected A") && h.includes('data-model="m1"'));
  h = await ML.render({ providers: PROVS, expanded: "", filter: "locked", connectedOnly: true });
  check("connectedOnly: searching a locked provider's name finds nothing", !h.includes("Locked B"));
  h = await ML.render({ providers: PROVS, expanded: "a" });
  check("default (assistant list): locked provider still shown with its way out", h.includes("Locked B") && h.includes('data-goto="models"'));
  const picker = fs.readFileSync(path.join(ROOT, "dashboard", "model-picker.js"), "utf8");
  check("the chat composer asks for connected providers only", /connectedOnly:\s*true/.test(picker));
  if (hong) { console.log("\nTHAT BAI " + hong); process.exit(1); }
  console.log("\nOK - test_model_list_chi_nha_ket_noi");
})();
