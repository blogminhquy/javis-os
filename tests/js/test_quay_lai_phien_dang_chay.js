// Back on a chat whose turn is still running (owner, 05/11/2026): "khi javis đang chat, anh back ra khung chat khác và
// truy cập lại thì nó hiện 1 bong bóng rỗng". Opening the chat again drew an empty answer bubble above the activity chip
// while Javis had not written a word yet. Now a bubble is drawn only when the turn has text.
//
//     node tests/js/test_quay_lai_phien_dang_chay.js
//
// Runs `_veLaiPhien` from dashboard/app.js against a fake chat area.
"use strict";
const fs = require("fs");
const path = require("path");
const app = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "app.js"), "utf8");
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

const m = /function _veLaiPhien\(id, sess, ticket, capNhat\) \{[\s\S]*?\n\}\n/.exec(app);
check("_veLaiPhien is found", !!m);

function run(turnState) {
  const area = [];   // what the chat shows, in order
  const el = (kind) => ({ kind, dataset: {}, isConnected: true, html: "",
    querySelector() { const self = this; return { set innerHTML(v) { self.html = v; } }; } });
  const env = {
    convo: [], savedSessionId: null, _dangDungLoat: false, _tinCu: null, _phienMoLuc: null,
    hideActivity() {}, goMoiTinCu() {}, chatArea: { innerHTML: "" }, ngoaiAlpine(f) { f(); },
    veTinDaLuu() { return null; }, datMoiTinCu() {}, veNhanBrain() {}, graphSource: { value: "brain" },
    window: { t: (k) => k, JavisResume: null, JavisInbox: null, JavisBackground: null },
    turns: { s1: turnState },
    createStreamingBubble() { const b = el("bubble"); area.push(b); return b; },
    markdownToHtml: (x) => "<p>" + x + "</p>",
    showActivity(x) { area.push({ kind: "chip", text: String(x) }); },
    Icons: { msg: (i, x) => x }, runActions() {}, turn: { turnStart() {}, turnDone() {} },
    persistSession() {}, scrollBottom() {}, ghimDay() {}, syncActiveUI() {}, notifySessions() {},
    chatAppend(x) { area.push(x); },
    _drawUnacked() {},   // messages still waiting for the server's ack: none here (test_chat_ack_resend.py)
  };
  const names = Object.keys(env);
  const fn = new Function(...names, m[0] + "\nreturn _veLaiPhien;");
  fn(...names.map((k) => env[k]))("s1", { messages: [], brain: "brain" }, 1, false);
  return area;
}

const steps = { kind: "steps" };
let a = run({ running: true, text: "", bubble: { kind: "old-bubble" }, buocEl: steps });
check("no text yet: no answer bubble is drawn", !a.some((x) => x.kind === "bubble"), JSON.stringify(a.map((x) => x.kind)));
check("no text yet: the steps so far, then the thinking chip",
  a.length === 2 && a[0] === steps && a[1].kind === "chip" && a[1].text === "app.act_thinking", JSON.stringify(a));

const t2 = { running: true, text: "Doanh thu tuần này", bubble: null };
a = run(t2);
check("with text: one bubble holding it, then the writing chip",
  a.length === 2 && a[0].kind === "bubble" && /Doanh thu/.test(a[0].html) && a[1].text === "app.act_writing", JSON.stringify(a));
check("with text: the bubble keeps its markdown for Copy", t2.bubble && t2.bubble.dataset.md === "Doanh thu tuần này");

const t3 = { running: true, text: "", bubble: { kind: "old-bubble" } };
run(t3);
check("the bubble of the earlier view is dropped, so the first words get a fresh one", t3.bubble === null);
check("the stream frame makes the bubble when words arrive",
  /if \(!t\.bubble\) \{ t\.bubble = createStreamingBubble\(\);/.test(app));

const dash = String.fromCharCode(0x2014), en = String.fromCharCode(0x2013);
check("no em or en dash in the changed function", m && !m[0].includes(dash) && !m[0].includes(en));
process.exit(fails ? 1 : 0);
