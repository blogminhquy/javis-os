/* A running turn is drawn again when the socket comes back (0.388.0).

   Bug: on a phone, switching to another app closes the dashboard socket. The "connection lost" note takes the chat's
   activity chip, and when `hello` arrives baoDutMang(false) removes that chip, the running turn's included. Frames sent
   while away never arrive, so the chat showed no sign of life until the answer landed and looked stopped, although
   the turn kept running on the server. redrawRunningTurn() puts the chip back and shows the text the server has so far.

   node tests/js/test_running_turn_redraw.js
*/
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const appJs = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "app.js"), "utf8");

function fn(name) {
  const start = appJs.indexOf("\nfunction " + name + "(");
  assert.ok(start >= 0, "missing " + name);
  const end = appJs.indexOf("\n}\n", start);
  return appJs.slice(start, end + 2);
}

// Minimal DOM: a bubble element whose inner `.bubble` keeps its HTML, attached until the chat is cleared.
function makeCtx(turnState, opts = {}) {
  const shown = [], appended = [];
  const ctx = {
    savedSessionId: "s1",
    turns: { s1: turnState },
    activityEl: opts.chip ? { id: "chip" } : null,
    window: { t: k => "T(" + k + ")" },
    Icons: { msg: (icon, text) => icon + ":" + text },
    dangTheoLoi: () => !!opts.voiceFollow,
    markdownToHtml: md => "<p>" + md + "</p>",
    createStreamingBubble() {
      const inner = { innerHTML: "" };
      const b = { isConnected: true, dataset: { anhV: "1" }, querySelector: () => inner, inner };
      ctx.created = (ctx.created || 0) + 1;
      return b;
    },
    showActivity(html) { shown.push(html); ctx.activityEl = { id: "chip" }; },
    chatAppend(el) { appended.push(el); },
    scrollBottom() {},
  };
  vm.createContext(ctx);
  vm.runInContext(fn("redrawRunningTurn"), ctx);
  return { ctx, shown, appended };
}

// 1. Running, nothing written yet, chip gone: the "thinking" chip comes back, no empty bubble.
{
  const { ctx, shown } = makeCtx({ text: "", bubble: null, running: true });
  ctx.redrawRunningTurn();
  assert.deepEqual(shown, ["T(app.act_thinking)"]);
  assert.equal(ctx.created || 0, 0, "no bubble for a turn that has written nothing");
}

// 2. Running with text the page never received (frames lost while away): a bubble shows the server's text.
{
  const t = { text: "Doan 1. Doan 2.", bubble: null, running: true };
  const { ctx, shown } = makeCtx(t);
  ctx.redrawRunningTurn();
  assert.equal(ctx.created, 1);
  assert.equal(t.bubble.inner.innerHTML, "<p>Doan 1. Doan 2.</p>");
  assert.equal(t.bubble.dataset.md, "Doan 1. Doan 2.");
  assert.deepEqual(shown, ["pen-line:T(app.act_writing)"]);
}

// 3. The bubble is still on screen: reuse it and fill in the full text, keep a chip that is already there.
{
  const inner = { innerHTML: "<p>Doan 1.</p>" };
  const bubble = { isConnected: true, dataset: { anhV: "9" }, querySelector: () => inner };
  const t = { text: "Doan 1. Doan 2.", bubble, running: true };
  const { ctx, shown, appended } = makeCtx(t, { chip: true });
  ctx.redrawRunningTurn();
  assert.equal(ctx.created || 0, 0, "an attached bubble is reused");
  assert.equal(inner.innerHTML, "<p>Doan 1. Doan 2.</p>");
  assert.deepEqual(shown, [], "an existing chip (a tool step) is not overwritten");
  assert.deepEqual(appended, [{ id: "chip" }], "the chip moves back under the bubble");
}

// 4. A bubble removed from the page (the chat was redrawn) is replaced, not written into while detached.
{
  const t = { text: "abc", bubble: { isConnected: false, dataset: {}, querySelector: () => ({}) }, running: true };
  const { ctx } = makeCtx(t);
  ctx.redrawRunningTurn();
  assert.equal(ctx.created, 1);
  assert.equal(t.bubble.isConnected, true);
}

// 5. Voice reading along: the text follows the speaker, so the bubble HTML is left alone.
{
  const inner = { innerHTML: "<p>da doc</p>" };
  const t = { text: "da doc va chua doc", bubble: { isConnected: true, dataset: {}, querySelector: () => inner }, running: true };
  const { ctx } = makeCtx(t, { voiceFollow: true });
  ctx.redrawRunningTurn();
  assert.equal(inner.innerHTML, "<p>da doc</p>");
  assert.equal(t.bubble.dataset.md, "da doc va chua doc");
}

// 6. Nothing running in the open chat: nothing is drawn.
{
  for (const t of [undefined, { text: "x", bubble: null, running: false }]) {
    const { ctx, shown } = makeCtx(t);
    ctx.redrawRunningTurn();
    assert.deepEqual(shown, []);
    assert.equal(ctx.created || 0, 0);
  }
}

// 7. `hello` redraws AFTER baoDutMang(false), which removes the shared chip.
{
  const i = appJs.indexOf('if (data.type === "hello") {');
  const hello = appJs.slice(i, appJs.indexOf("guiTinDutMang();", i));
  const a = hello.indexOf("baoDutMang(false);"), b = hello.indexOf("redrawRunningTurn();");
  assert.ok(a > 0 && b > a, "hello must call redrawRunningTurn() after baoDutMang(false)");
}

console.log("OK - running turn redrawn after reconnect");
