// The owner's Team message shows at once as a pending bubble keyed by its client_msg_id, is replaced by the server's
// copy when that arrives (over the socket or the reload), and turns "Not sent" with Try again (same client id, so never
// twice) or Remove (the words go back into the composer) when the POST fails.
//
//     node tests/js/test_team_pending_send.js
"use strict";
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const T = require(path.join(D, "teams.js"));
const teamsJs = fs.readFileSync(path.join(D, "teams.js"), "utf8");
const css = fs.readFileSync(path.join(D, "console.css"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(D, "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(D, "i18n", "en.json"), "utf8"));
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}
function fnBody(name) {
  const i = teamsJs.indexOf("  function " + name + "(");
  return teamsJs.slice(i, teamsJs.indexOf("\n  }\n", i) + 4);
}

let h = T.pendingHtml({ cid: "c-1", text: "> Lan: câu cũ\n\nXin <chào>", ts: 1792000000, state: "sending", atts: [] });
check("sending: an owner bubble marked pending, keyed by the client id, the words escaped, the quote on top",
  /^<div class="tm-msg tm-msg-owner tm-msg-pending" data-cid="c-1">/.test(h) && h.includes("Xin &lt;chào&gt;")
  && h.includes('<div class="tm-quote">'), h);
check("sending: a quiet Sending... and no action buttons (nothing to reply to or pin yet)",
  h.includes(vi["app.sending"]) && !/data-reply=|data-copy=|data-decision=/.test(h));
h = T.pendingHtml({ cid: "c-2", text: "x", ts: 1, state: "failed", err: "No network", atts: [{ name: "a.png", url: "blob:1" }, { name: "b.txt" }] });
check("failed: Not sent (the reason in the tooltip), Try again and Remove for that client id",
  /tm-msg-pending is-failed/.test(h) && h.includes('title="No network">' + vi["teams.send_failed"])
  && h.includes('data-out-retry="c-2"') && h.includes('data-out-drop="c-2"') && h.includes(vi["teams.retry_action"]), h);
check("pending files show from the local preview", h.includes('<img src="blob:1"') && h.includes("b.txt"));
check("i18n: both languages", !!vi["teams.send_failed"] && !!en["teams.send_failed"] && !!vi["teams.send_remove"] && !!en["teams.send_remove"]);

const send = fnBody("send");
check("send: queues the message with a fresh client id and frees the composer before the POST",
  /var entry = \{ cid: newClientId\(\),/.test(send) && /client_msg_id: entry\.cid/.test(send) && /S\.outbox\.push\(entry\);/.test(send)
  && send.indexOf('input.value = "";') < send.indexOf("postEntry(entry);") && /drawMsgs\(true\);/.test(send));
const post = fnBody("postEntry");
check("POST ok: kept as sent until the server's copy is really in the list (0.358.0: a failed or late reload no longer "
  + "takes the owner's message away)", /entry\.state = "sent";/.test(post)
  && /loadMsgs\(false\)\.then\(function \(\) \{ pruneOutbox\(\); drawMsgs\(false\); \}\);/.test(post)
  && !/dropEntry\(entry, true\)/.test(post));
const prune = fnBody("pruneOutbox");
check("pruneOutbox drops only delivered entries whose copy is on screen", /p\.state === "sent" && \(have\[p\.cid\] \|\| \(p\.mid && ids\[Number\(p\.mid\)\]\)\)/.test(prune)
  && /dropEntry\(p, true\)/.test(prune));
h = T.pendingHtml({ cid: "c-3", text: "x", ts: 1, state: "sent", atts: [] });
check("delivered but not on screen yet: says Sent, never Sending... forever", h.includes(vi["teams.sent_ok"]) && !h.includes(vi["app.sending"])
  && vi["teams.sent_ok"] === "Đã gửi" && en["teams.sent_ok"] === "Sent", h);
check("sending while one job is filtered goes back to the whole chat, where the message lands",
  /if \(S\.filterTask\) \{ S\.filterTask = ""; S\.taskDetail = null; drawFilterbar\(\); \}/.test(send)
  && send.indexOf("S.filterTask = \"\"") < send.indexOf("postEntry(entry);"));
const lm = fnBody("loadMsgs");
check("only the latest load of the newest page replaces the list (a late older load is ignored)",
  /var seq = older \? S\.msgsSeq : \(S\.msgsSeq = \(S\.msgsSeq \|\| 0\) \+ 1\);/.test(lm) && /seq !== S\.msgsSeq\) return;/.test(lm));
check("messages the socket brought while the load was on its way are kept",
  /got = got\.concat\(S\.msgs\.filter\(function \(m\) \{ return Number\(m\.id\) > last; \}\)\);/.test(lm));
check("refused (4xx) with an empty composer: the draft goes back with the error, as before",
  /r\.code >= 400 && r\.code < 500 && inp && !inp\.value\.trim\(\)/.test(post) && /inp\.value = entry\.typed;/.test(post) && /fail\(r\); drawHint\(\);/.test(post));
check("network error, timeout or 5xx: Not sent", /failed\(tw\("teams\.err_network"\)\)/.test(post) && /entry\.state = "failed"; entry\.err = why;/.test(post));
check("the server's copy replaces the bubble as soon as it is in the list (socket or reload), matched by client id or id",
  /if \(m\.client_msg_id\) have\[m\.client_msg_id\] = true;/.test(fnBody("pendingEntries"))
  && /return S\.outbox\.filter\(function \(p\) \{ return !have\[p\.cid\] && !\(p\.mid && ids\[Number\(p\.mid\)\]\); \}\);/.test(fnBody("pendingEntries"))
  && /pendingEntries\(\)\.forEach\(function \(p\) \{ items\.push\(\{ key: "p" \+ p\.cid, html: pendingHtml\(p\) \}\); \}\);/.test(teamsJs));
check("Try again re-posts the same entry (same body, same client id)", /if \(oe && oe\.state === "failed"\) \{ postEntry\(oe\); drawMsgs\(false\); \}/.test(teamsJs));
check("Remove puts the words back into an empty composer", /oi\.value = od\.typed;/.test(teamsJs));
check("a team switch empties the outbox; a pending bubble is not swiped", /S\.outbox = \[\]; stopReveal\(\);/.test(teamsJs)
  && /!m\.classList\.contains\("tm-msg-pending"\)/.test(teamsJs));
check("CSS: pending faded, failed in red, 16px on phones", /\.tm-msg-pending \.tm-bubble \{ opacity: \.72; \}/.test(css)
  && /@media \(pointer: coarse\) \{ \.tm-pending-st \{ font-size: 16px; \} \}/.test(css));

if (fails) { console.log("\nFAIL - test_team_pending_send: " + fails); process.exit(1); }
console.log("\nOK - test_team_pending_send");
