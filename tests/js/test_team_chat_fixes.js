// Four Team chat fixes ported from the main chat:
//  (a) a revealed answer does not pull the reader down when they are up in the history;
//  (b) uploads use the main chat's progress and stall watch (chat-upload.js), retry, and say why they failed, so the
//      composer is never blocked forever;
//  (c) JAVIS_CARD buttons in the Team chat answer in the team (chat-card.js onSend registry), not in the hidden main chat;
//  (d) with the phone keyboard open the composer drops the safe-area gap (body.kb-open).
//
//     node tests/js/test_team_chat_fixes.js
"use strict";
const fs = require("fs");
const { napTruoc, coNap } = require("./_thu_tu_nap");   // load order that understands lazy groups (0.417.0)
const path = require("path");
const vm = require("vm");
const D = path.join(__dirname, "..", "..", "dashboard");
const T = require(path.join(D, "teams.js"));
const teamsJs = fs.readFileSync(path.join(D, "teams.js"), "utf8");
const cardJs = fs.readFileSync(path.join(D, "chat-card.js"), "utf8");
const css = fs.readFileSync(path.join(D, "console.css"), "utf8");
const indexHtml = fs.readFileSync(path.join(D, "index.html"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(D, "i18n", "vi.json"), "utf8"));
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}
function fnBody(name) {
  const i = teamsJs.indexOf("  function " + name + "(");
  return teamsJs.slice(i, teamsJs.indexOf("\n  }\n", i) + 4);
}

// (a)
const nr = fnBody("nextReveal");
check("(a) nextReveal asks whether the reader is at the end (chat-scroll.js) before revealing the next answer",
  /var atEnd = !S\.scroll \|\| S\.scroll\.stuck\(\);/.test(nr) && nr.indexOf("var atEnd") < nr.indexOf("applyReveal(msgs)"));
check("(a) and scrolls only then", /if \(atEnd\) toLatest\(false\);/.test(nr) && !/msgs\.scrollTop = msgs\.scrollHeight;/.test(nr));

// (b)
const up = fnBody("upload");
check("(b) Team upload goes through the shared JavisUpload.send (progress + stall watch)", /U\.send\(fd, function \(loaded, total\)/.test(up));
check("(b) a stall or a dropped connection is retried, the server's silence is not",
  /\(kind === "stall" \|\| kind === "net"\) && tries < U\.RETRIES/.test(up));
check("(b) progress updates the chip in place (no composer redraw that would steal the input focus)",
  /drawAttStatus\(a\);/.test(up) && !/drawComposer\(\)/.test(up));
const err = (k, extra) => T.uploadError(Object.assign(new Error(k), { kind: k }, extra || {}));
check("(b) failure words: stall, server silence, browser error, network",
  err("stall") === vi["app.att_stalled"] && err("server") === vi["app.att_server_slow"]
  && err("client", { detail: "boom" }) === vi["app.att_client_err"].replace("{msg}", "boom") && err("net") === vi["teams.err_network"]);
check("(b) a failed chip keeps its File and offers Retry", /file: f \};/.test(teamsJs) && /data-att-retry="' \+ i \+ '"/.test(teamsJs)
  && /if \(ra && ra\.file && !ra\.busy\) \{ startUpload\(ra\); drawComposer\(\); \}/.test(teamsJs));
check("(b) Send with a failed file says so instead of dropping it silently",
  /if \(S\.atts\.some\(function \(a\) \{ return a\.err; \}\)\) \{ setNote\(tw\("app\.att_failed_send"\)\); return; \}/.test(teamsJs));
check("(b) chat-upload.js loads before app.js and teams.js",
  napTruoc("chat-upload.js", ["app.js", "teams.js"], indexHtml));

// (c) chat-card.js with a fake document: presses inside a registered root go to that root's sender.
const listeners = [];
const sentMain = [];
const ctx = { window: { JavisSend: (t) => sentMain.push(t) }, document: { addEventListener: (n, fn) => { if (n === "click") listeners.push(fn); } } };
vm.createContext(ctx);
vm.runInContext(cardJs, ctx);
const JC = ctx.window.JavisCard;
function btn(reply, inside) {
  const row = { querySelectorAll: () => [] };
  const b = { disabled: false, parentNode: row, classList: { add() {} }, getAttribute: (k) => (k === "data-reply" ? reply : null),
    closest: (s) => (s === ".jv-card-btn" ? b : null), _in: inside };
  return b;
}
function press(b) { listeners.forEach((fn) => fn({ target: b, preventDefault() {} })); }
const team = { contains: (n) => n._in === "team" };
const got = [];
const off = JC.onSend(team, (text, b) => got.push(text));
press(btn("Làm tiếp đi", "team"));
press(btn("Main chat answer", "main"));
check("(c) a card button inside the Team page answers in the team", got.join("|") === "Làm tiếp đi", got.join("|"));
check("(c) a card button elsewhere still answers in the main chat", sentMain.join("|") === "Main chat answer", sentMain.join("|"));
off();
press(btn("After leave", "team"));
check("(c) leaving the page removes the registration", sentMain.join("|") === "Main chat answer|After leave");
check("(c) Team registers its root, unregisters on leave, and sends the press as a reply quoting that message",
  /S\.uncard = JC\.onSend\(el, function \(text, btn\) \{ sendCardReply\(btn, text\); \}\);/.test(teamsJs)
  && /if \(S\.uncard\) \{ S\.uncard\(\); S\.uncard = null; \}/.test(teamsJs)
  && /text: Q \? Q\.ghep\(target\.quote, text\) : text, mentions: target\.key \? \[target\.key\] : \[\]/.test(teamsJs));
check("(c) the Team click handler leaves card buttons to chat-card.js (their data-reply is words, not an id)",
  /if \(t\.classList && t\.classList\.contains\("jv-card-btn"\)\) return;/.test(teamsJs));
check("(c) hidden blocks never show in a preview or a quote",
  T.plainPreview('Chọn một:\n\n<!-- JAVIS_CARD: {"type":"buttons"} -->', 160) === "Chọn một:");

// (d)
check("(d) keyboard open: the Team composer drops the safe-area padding", /body\.kb-open \.tm-composer \{ padding-bottom: 8px; \}/.test(css));

if (fails) { console.log("\nFAIL - test_team_chat_fixes: " + fails); process.exit(1); }
console.log("\nOK - test_team_chat_fixes");
