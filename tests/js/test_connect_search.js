// 0.312.0: the Connected tab has a search box, the green "your engine uses the store" notes are
// gone, and the built-in Claude Code / Codex sources list only the working ones (owner,
// 2026-10-25: "gãy thì thôi chỉ hiển thị cái nào xanh thôi"). Runs ambientName/ambientList in a vm.
//
//     node tests/js/test_connect_search.js
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  " + JSON.stringify(extra)));
  if (!cond) fails++;
}

function grab(sig) {
  const start = SRC.indexOf(sig);
  if (start < 0) return "";
  return SRC.slice(start, SRC.indexOf("\n  }\n", start) + 4);
}
const code = ["  function ambientName(", "  function ambientHost(", "  function ambientCard(", "  function ambientList("]
  .map(grab);
check("the four ambient helpers exist", code.every(Boolean));
const ctx = {
  window: { t: (k, o) => k + (o && o.count !== undefined ? ":" + o.count : "") },
  esc: (s) => String(s).replace(/</g, "&lt;"),
  ic: (n) => "<i " + n + ">",
  _shield: (on) => (on ? "<s on>" : "<s>"),
  WARN_ICON: "<w>",
  URL: URL,
};
vm.createContext(ctx);
vm.runInContext(code.join("\n") + "\nthis.ambientName = ambientName; this.ambientList = ambientList;", ctx);

check("claude.ai prefix dropped", ctx.ambientName("claude.ai Meta ADS") === "Meta ADS");
check("plugin:x:y reads as y", ctx.ambientName("plugin:engineering:slack") === "slack");
check("other names unchanged", ctx.ambientName("my-server") === "my-server");

const list = [
  { name: "claude.ai Supabase", connected: true, status: "✓ Connected", url: "https://mcp.supabase.com/mcp" },
  { name: "plugin:engineering:slack", connected: false, status: "! Needs authentication", url: "https://mcp.slack.com/mcp" },
  { name: "plugin:engineering:linear", connected: false, status: "! Needs authentication", url: "https://mcp.linear.app/mcp" },
];
const html = ctx.ambientList(list, "claude code", "cs.cn_amb_none_claude");
const shown = html.split('<div class="amb-off-list" hidden>')[0];
check("a working source is shown with the localized status and its host",
  shown.includes("Supabase") && shown.includes("cs.cn_amb_ok") && shown.includes("mcp.supabase.com"), shown);
check("sources waiting for sign-in are not in the visible list", !shown.includes("slack") && !shown.includes("linear"));
check("they are counted in one line with a Show button",
  shown.includes("cs.cn_amb_off_n:2") && shown.includes("data-amb-show"));
check("and kept in a hidden list for that button", /<div class="amb-off-list" hidden>[\s\S]*slack[\s\S]*linear/.test(html));
check("nothing working: says so instead of an empty box",
  ctx.ambientList(list.slice(1), "codex", "x").includes("cs.cn_amb_none_ok"));
check("empty list keeps its own message", ctx.ambientList([], "codex", "cs.cn_amb_none_codex").includes("cs.cn_amb_none_codex"));
check("the hidden attribute really hides the list (CSS display:grid would beat it)",
  /\.amb-off-list\[hidden\][^{]*\{ display: none; \}/.test(CSS));

check("Connected tab has a search box once there are more than 3 accounts",
  SRC.includes('conns.length > 3 ? \'<input class="js-input conn-search" id="connQ"'));
check("the search covers accounts and built-in sources",
  SRC.includes('#connList .conn-card') && SRC.includes('#ambWrap .amb-card'));
check("green notices about the engine are gone", !SRC.includes("cs.cn_w_chatgpt") && !SRC.includes("cs.cn_w_hub"));
check("the yellow warning for an engine without tool calls stays", SRC.includes("cs.cn_w_notool_a"));
check("search input is at least 16px", /\.conn-search \{[^}]*font-size: 16px/.test(CSS));
for (const k of ["cs.cn_amb_ok", "cs.cn_amb_none_ok", "cs.cn_amb_off_n", "cs.cn_amb_show", "cs.cn_amb_hide",
                 "cs.cn_conn_search_ph", "cs.cn_conn_search_none"])
  check("i18n key in vi and en: " + k, !!VI[k] && !!EN[k]);
check("no em or en dash added", !/[–—]/.test(code.join("") + JSON.stringify(VI["cs.cn_amb_off_n"])));

if (fails) { console.log("\nFAIL: " + fails); process.exit(1); }
console.log("\nOK - test_connect_search");
