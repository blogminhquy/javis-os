// The composer's model chip shows the model REALLY answering (owner, 05/11/2026). Antigravity ran out of quota, the
// chat moved to ChatGPT then Claude Code, and the chip still said "Gemini 3.8 Flash" with a green dot.
//
//     node tests/js/test_model_chip_fallback.js
//
// Checks the route helpers of model-picker.js by running them, and the wiring in app.js, style.css and the i18n files.
"use strict";
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const mp = fs.readFileSync(path.join(D, "model-picker.js"), "utf8");
const app = fs.readFileSync(path.join(D, "app.js"), "utf8");
const css = fs.readFileSync(path.join(D, "style.css"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(D, "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(D, "i18n", "en.json"), "utf8"));
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

// ---- run the helpers between FALLBACK_BEGIN and FALLBACK_END with a small fake page ----
const block = /\/\/ FALLBACK_BEGIN\n([\s\S]*?)\/\/ FALLBACK_END/.exec(mp);
check("the route helpers are marked out", !!block);
const timers = [];
const window = { t: (k, v) => k + (v ? JSON.stringify(v) : "") };
const sandbox = new Function("window", "setTimeout", "clearTimeout", "defText", "refreshRoute", "renderBar",
  "let route = null; let routeTimer = null; const lastRoute = {};\n" + (block ? block[1] : "") +
  "\nreturn { setRoute, routeLine, routeTags, fallbackTitle, hhmm, get route() { return route; }, get timer() { return routeTimer; } };");
const H = sandbox(window, (f, ms) => { timers.push(ms); return timers.length; }, () => {},
  (pid) => "default of " + pid, async () => {}, () => {});

const fb = { provider: "anthropic-cli", model: "", name: "Claude Code", fallback: true, reason: "quota",
  until: Date.now() / 1000 + 3600, selected_provider: "antigravity-cli", selected_model: "gemini-3.8-flash",
  selected_name: "Antigravity", limited: { "antigravity-cli": Date.now() / 1000 + 3600, "openai-oauth": Date.now() / 1000 + 600 },
  content: "Antigravity hết lượt → đang dùng Claude Code." };
const ok = { provider: "antigravity-cli", model: "gemini-3.8-flash", name: "Antigravity", fallback: false,
  selected_provider: "antigravity-cli", selected_model: "gemini-3.8-flash", limited: {} };

check("first turn on a fallback card: one line saying who ran out and who answers", H.routeLine("s1", fb) === fb.content);
check("next turn on the same fallback card: no line again", H.routeLine("s1", fb) === "");
check("a turn on ANOTHER fallback card: a new line",
  H.routeLine("s1", Object.assign({}, fb, { provider: "groq", content: "x → Groq" })) === "x → Groq");
check("back on the chosen card: one line saying so", /^mpick\.route_back/.test(H.routeLine("s1", ok)));
check("still on the chosen card: no line", H.routeLine("s1", ok) === "");
check("a turn already rerouted mid-way: no second line (run_turn wrote it)",
  H.routeLine("s2", Object.assign({}, fb, { rerouted: true })) === "");
check("a chat that never left its card: no line", H.routeLine("s3", ok) === "");

H.setRoute(fb);
check("a resting card: the route is read again about when its quota is due back",
  timers.length === 1 && timers[0] > 3600 * 1000 && timers[0] < 3600 * 1000 + 10000, String(timers));
H.setRoute(ok);
check("on the chosen card: no timer", timers.length === 1 && H.timer === null);
H.setRoute(fb);
const tags = H.routeTags("antigravity-cli") + "|" + H.routeTags("anthropic-cli") + "|" + H.routeTags("openai-oauth") + "|" + H.routeTags("groq");
const parts = tags.split("|");
check("picker: the chosen card that ran out wears an Out of quota tag", /is-limited/.test(parts[0]) && !/is-running/.test(parts[0]));
check("picker: the fallback card answering wears a Running tag", /is-running/.test(parts[1]) && !/is-limited/.test(parts[1]));
check("picker: another resting card is tagged too", /is-limited/.test(parts[2]));
check("picker: a card with nothing to say has no tag", parts[3] === "");
const title = H.fallbackTitle(fb, { label: "Antigravity CLI" }, { label: "Claude Code" });
check("tooltip: the chosen model and why, then the model running",
  title.indexOf("mpick.route_chosen") === 0 && /Antigravity CLI · gemini-3.8-flash/.test(title)
  && /mpick\.route_quota_until/.test(title) && /\nmpick\.route_running/.test(title) && /Claude Code · default of anthropic-cli/.test(title), title);
check("tooltip: a card that cannot run for another reason says so",
  /mpick\.route_unavailable/.test(H.fallbackTitle(Object.assign({}, fb, { reason: "unavailable", until: 0 }), null, null)));
check("hh:mm of a reset today", /^\d\d:\d\d$/.test(H.hhmm(Date.now() / 1000)));

// ---- wiring ----
check("chip: the running model's name and an amber state while a fallback card answers",
  /const fb = route && route\.fallback \? route : null;/.test(mp)
  && /chip\.classList\.toggle\("is-fallback", !!fb\);/.test(mp)
  && /window\.t\("mpick\.fallback_aria"/.test(mp));
check("chip: the route comes from the chat's meta, or /chat/route for an empty chat",
  /setRoute\(\(d && d\.route\) \|\| null\);/.test(mp) && /"\/chat\/route"/.test(mp));
check("picking a model or following the main one reads the route again",
  (mp.match(/await refreshRoute\(\); renderBar\(\);/g) || []).length >= 2);
// Owner, 05/11/2026: "the chat that got switched must switch its model too": everything the composer shows follows the
// model really answering, while the owner's choice stays for when the quota returns.
check("composer follows the running model: shown() is the fallback card, else the choice",
  /const shown = \(\) => \(route && route\.fallback \? \{ provider: route\.provider, model: route\.model \|\| "" \} : effective\(\)\);/.test(mp));
check("picker tick, effort lock, Fast bolt, plan ring and /model use the running model",
  /selected: shown\(\),/.test(mp) && /const effM = shown\(\);/.test(mp)
  && /function renderFast\(\) \{\s*const eff = shown\(\);/.test(mp) && /function fastTitle\(on\) \{\s*const eff = shown\(\);/.test(mp)
  && /hienTai: function \(\) \{\s*const eff = shown\(\);/.test(mp) && /closeLimit\(\);\s*const eff = shown\(\);/.test(mp));
check("the choice itself is not rewritten by a fallback (only picking a model pins one)",
  (mp.match(/sessionPin = \{ provider:/g) || []).length === 2 && !/sessionPin = route/.test(mp) && !/saveModel\(\{ main: \{ provider: route/.test(mp));
check("picker rows carry the route tags", /\+ routeTags\(p\.id\),/.test(mp));
check("app.js hands each route frame to the chip and writes its line",
  /data\.type === "route"/.test(app) && /window\.JavisModelBar\.noteRoute\(sid, data\)/.test(app)
  && /if \(isActive && _dong\) ghiDoiDuong\(_dong\);/.test(app));
const KL = /const KHUNG_LUOT = \[([^\]]*)\]/.exec(app);
check("a route frame never starts a turn by itself", !!KL && !/"route"/.test(KL[1]));
check("css: amber dot for a fallback, tags for out of quota and running",
  css.includes(".mb-chip.is-fallback .mb-dot { background: var(--warn-ink); }")
  && css.includes(".mb-tag.is-limited { color: var(--warn-ink);") && css.includes(".mb-tag.is-running { color: var(--green);"));
const keys = ["mpick.route_chosen", "mpick.route_running", "mpick.route_quota", "mpick.route_quota_until",
  "mpick.route_unavailable", "mpick.route_back", "mpick.fallback_aria", "mpick.tag_limited", "mpick.tag_running"];
check("every new text is in vi.json and en.json", keys.every((k) => vi[k] && en[k]), keys.filter((k) => !vi[k] || !en[k]).join(","));
const dash = String.fromCharCode(0x2014), en2 = String.fromCharCode(0x2013);
check("no em or en dash in the new texts or code",
  !keys.some((k) => (vi[k] + en[k]).includes(dash) || (vi[k] + en[k]).includes(en2)) && !(block && (block[1].includes(dash) || block[1].includes(en2))));
process.exit(fails ? 1 : 0);
