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
check("no model set: the provider name stands in", /eff\.model \? prettyModel\(eff\.model\) : \(p \? provShort\(p\.label\) : "Model"\)/.test(mp));
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
check("scroll hold: only with a real mouse", /matchMedia\("\(hover: hover\) and \(pointer: fine\)"\)/.test(app));
check("scroll hold: on a message's button row or reaction, or while the mouse moves over a message",
  /querySelector\("\.msg-acts:hover, \.jr-chat:hover"\)/.test(app) && /const HOLD_MOVE_MS = 1200;/.test(app)
  && /Date\.now\(\) - _diChuotLuc < HOLD_MOVE_MS && !!chatArea\.querySelector\("\.msg:hover"\)/.test(app));
check("scroll hold: a forced jump still goes, and it catches up when the hold ends",
  /if \(stickBottom && !force && dangGiuCuon\(\)\) \{ choCuonTiep\(\); return; \}/.test(app) && /_treoCuon = null;\s*scrollBottom\(\);/.test(app));
const dash = String.fromCharCode(0x2014), en = String.fromCharCode(0x2013);
check("no em or en dash in the new code", ![mp, mobile].some((s) => s.includes(dash) || s.includes(en)));
process.exit(fails ? 1 : 0);
