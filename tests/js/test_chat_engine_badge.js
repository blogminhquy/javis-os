/* Engine badge on each chat row of the history list (2026-11-09): the owner sees the brain's name ("Claude",
   "Codex"), not the internal id ("cli", "codex").

       node tests/js/test_chat_engine_badge.js
*/
const fs = require("fs");
const path = require("path");
const SRC = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard/sessions-ui.js"), "utf8");

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

const start = SRC.indexOf("  var ENGINE_BADGE = {");
const end = SRC.indexOf("  function renderList(items, hasMore) {");
check("the badge map sits before renderList", start > 0 && end > start);
const engineBadge = new Function(SRC.slice(start, end) + "\nreturn engineBadge;")();

const want = {
  cli: "Claude", codex: "Codex", "grok-cli": "Grok", "antigravity-cli": "Antigravity",
  openrouter: "OpenRouter", openai: "OpenAI", "anthropic-api": "Anthropic", gemini: "Gemini",
  groq: "Groq", deepseek: "DeepSeek", ollama: "Ollama",
};
Object.keys(want).forEach((id) => check(id + " shows as " + want[id], engineBadge(id) === want[id]));
check("an unknown id still shows, cut to 10 characters", engineBadge("some-new-provider") === "some-new-p");
check("no engine shows no badge", engineBadge("") === "" && engineBadge(null) === "");

const rl = SRC.slice(end, SRC.indexOf("async function doSearch(q)"));
check("the row uses the friendly name", rl.includes("var eng = engineBadge(s.engine);"));

if (fails) { console.log("\n" + fails + " FAIL"); process.exit(1); }
console.log("\nOK - chat_engine_badge");
