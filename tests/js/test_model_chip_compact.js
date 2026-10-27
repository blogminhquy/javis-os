// 0.180.0: the model chip shows the model name only and stays in the composer on a phone; the chat stops following
// the answer while the mouse is on a message's buttons, so Copy does not slide away.
//
//     node tests/js/test_model_chip_compact.js
"use strict";
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const mp = fs.readFileSync(path.join(D, "model-picker.js"), "utf8");
const mobile = fs.readFileSync(path.join(D, "mobile-chat.js"), "utf8");
const app = fs.readFileSync(path.join(D, "app.js"), "utf8");
const css = fs.readFileSync(path.join(D, "style.css"), "utf8");
const ccss = fs.readFileSync(path.join(D, "console.css"), "utf8");
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

const body = /function prettyModel\(id\) \{[\s\S]*?\n  \}/.exec(mp);
check("prettyModel exists", !!body);
const pretty = body ? eval("(" + body[0] + ")") : () => "";
const cases = {
  "claude-opus-4-8-20260101": "Opus 4.8", "opus": "Opus", "claude-sonnet-4-5": "Sonnet 4.5", "claude-opus-5-5": "Opus 5.5",
  "anthropic/claude-sonnet-4.5": "Sonnet 4.5", "openai/gpt-4o": "GPT-4o", "gpt-5-mini": "GPT-5 mini",
  "gemini-2.5-pro": "Gemini 2.5 pro", "grok-4": "Grok 4", "qwen3:32b": "Qwen3 32b",
};
Object.keys(cases).forEach((id) => check("model name: " + id + " -> " + cases[id], pretty(id) === cases[id], pretty(id)));

check("chip text is the model name only, provider and pin move to the tooltip",
  /mt\.textContent = chipLabel\(eff, p\);/.test(mp) && !/mt\.textContent = \(p \? provShort/.test(mp)
  && /mt\.title = \(p \? p\.label/.test(mp));
// 0.355.0: no model set names the provider's default model when the server knows it, else the provider name stands in.
check("no model set: the default model's name, else the provider name",
  /\(state\.defaults \|\| \{\}\)\[eff\.provider\] \? prettyModel\(state\.defaults\[eff\.provider\]\) : \(p \? provShort\(p\.label\) : "Model"\)/.test(mp));
check("a broken pin still shows, as the dot colour", /classList\.toggle\("is-pin-broken", pinBroken\)/.test(mp)
  && css.includes(".mb-chip.is-pin-broken .mb-dot { background: var(--warn-ink); }"));
check("the per-session pin stays visible: a pin icon on the chip, in words for screen readers",
  /chip\.classList\.toggle\("is-pinned", !!sessionPin\)/.test(mp) && /pin\.hidden = !\(sessionPin \|\| pinBroken\);/.test(mp)
  && /pin\.innerHTML = typeof ic === "function" \? ic\("pin"\)/.test(mp) && /", " \+ window\.t\("mpick\.pin"\)/.test(mp)
  && css.includes(".mb-pin[hidden] { display: none; }") && css.includes(".mb-chip.is-pin-broken .mb-pin { color: var(--warn-ink); }"));
check("pinning itself is untouched: picking a model still pins it to the open session",
  /sessionPin = \{ provider: prov, model: model \};/.test(mp) && /await pinToSession\(sid, prov, model\);/.test(mp));
// 0.182.0: the owner reversed the phone move; the chip is back in the top bar (centred), still short and with the pin icon.
check("phone: the chip goes back up to the header, centred, with its picker under the bar",
  /headerRoot\.insertBefore\(mbOpen, headerCenter\.nextSibling\)/.test(mobile) && /headerRoot\.insertBefore\(mbPop, mbOpen\.nextSibling\)/.test(mobile)
  && ccss.includes(".hud-top #mbOpen { display: inline-flex; margin-left: auto; margin-right: auto; max-width: 56vw; }")
  && ccss.includes(".hud-top #mbPop { position: fixed;") && !ccss.includes(".hud-top .new-chat-btn { margin-left: auto; }"));
check("long model names end in ...", /#mbModelTxt \{ min-width: 0; overflow: hidden; text-overflow: ellipsis; \}/.test(css)
  && !css.includes("#cpChips .mb-chip { max-width: 42vw; }"));
// The hold lives in chat-scroll.js (shared with the Team chat): checked by behaviour on a fake chat area.
const CS = require(path.join(D, "chat-scroll.js"));
function holdCase(mouse) {
  let t = 10000;
  const ls = {};
  const hover = {};
  const area = { scrollHeight: 2000, clientHeight: 400, scrollTop: 1600,
    addEventListener(n, f) { ls[n] = f; }, querySelector: (q) => hover[q] || null };
  const btn = { parentNode: area, classList: { add() {}, remove() {}, toggle() {}, contains: () => false }, setAttribute() {}, addEventListener() {} };
  const win = { matchMedia: (q) => ({ matches: mouse && q === "(hover: hover) and (pointer: fine)" }) };
  const ctl = CS.attach(area, { button: btn, msg: ".msg", hold: ".msg-acts:hover, .jr-chat:hover", win, now: () => t });
  return { ctl, area, hover, ls, tick: (ms) => { t += ms; } };
}
let hc = holdCase(false);
hc.hover[".msg-acts:hover, .jr-chat:hover"] = {};
check("scroll hold: only with a real mouse", hc.ctl.holding() === false);
hc = holdCase(true);
hc.hover[".msg-acts:hover, .jr-chat:hover"] = {};
const onRow = hc.ctl.holding();
delete hc.hover[".msg-acts:hover, .jr-chat:hover"];
hc.hover[".msg:hover"] = {};
const resting = hc.ctl.holding();
hc.ls.mousemove({ target: { closest: (q) => (q === ".msg" ? {} : null) } });
const moving = hc.ctl.holding();
hc.tick(CS.HOLD_MOVE_MS + 1);
check("scroll hold: on a message's button row or reaction, or while the mouse moves over a message",
  onRow === true && resting === false && moving === true && hc.ctl.holding() === false && CS.HOLD_MOVE_MS === 1200);
hc = holdCase(true);
hc.hover[".msg-acts:hover, .jr-chat:hover"] = {};
hc.area.scrollHeight = 2300;
hc.ctl.toBottom();
const stayed = hc.area.scrollTop === 1600;
hc.ctl.toBottom(true);
check("scroll hold: a forced jump still goes, and it catches up when the hold ends",
  stayed && hc.area.scrollTop === 2300 && /st\.wait = null;\s*toBottom\(\);/.test(fs.readFileSync(path.join(D, "chat-scroll.js"), "utf8")));
const dash = String.fromCharCode(0x2014), en = String.fromCharCode(0x2013);
check("no em or en dash in the new code", ![mp, mobile].some((s) => s.includes(dash) || s.includes(en)));
process.exit(fails ? 1 : 0);
