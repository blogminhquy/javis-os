// The brain picker drawn by Javis, in the owner's order (0.431.0, dashboard/brain-picker.js).
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const BP = require("../../dashboard/brain-picker.js");
const read = (f) => fs.readFileSync(path.resolve(__dirname, "../../dashboard", f), "utf8");

function check(name, fn) {
  try { fn(); console.log("ok   " + name); }
  catch (e) { console.error("FAIL " + name + ": " + e.message); process.exitCode = 1; }
}
check("moving a brain up or down keeps every other brain", () => {
  assert.deepEqual(BP.moveItem(["a", "b", "c", "d"], 3, 1), ["a", "d", "b", "c"]);
  assert.deepEqual(BP.moveItem(["a", "b", "c"], 0, 2), ["b", "c", "a"]);
  assert.deepEqual(BP.moveItem(["a", "b", "c"], 1, -5), ["b", "a", "c"]);   // clamped to the top
  assert.deepEqual(BP.moveItem(["a", "b"], 5, 0), ["a", "b"]);              // bad index: unchanged
});
check("the saved order is the list of folder names, no duplicates", () => {
  const order = BP.orderFromOptions([{ brainName: "OPC" }, { brainName: "Brain Default" }, { brainName: "" }, { brainName: "OPC" }]);
  assert.deepEqual(order, ["OPC", "Brain Default"]);
});
check("the native select stays the source of truth", () => {
  const src = read("brain-picker.js");
  assert.ok(src.includes('document.getElementById("graphSource")'));
  assert.ok(src.includes('sel.dispatchEvent(new Event("change", { bubbles: true }))'), "picking fires the select's change");
  assert.ok(src.includes('fetch("/brains/order"'), "the order is saved on the server, for every device");
});
check("brains-ui keeps the server's order, Brain Default included", () => {
  const src = read("brains-ui.js");
  assert.ok(src.includes("const opt = b.is_default && defOpt ? defOpt : document.createElement(\"option\");"));
  assert.ok(src.includes("opt.dataset.notes"));
});
check("brain-picker.js loads after brains-ui.js", () => {
  const html = read("index.html");
  const at = html.indexOf("/static/brain-picker.js?v=");
  assert.ok(at > html.indexOf("/static/brains-ui.js?v=") && at > html.indexOf("/static/app.js?v="));
});
check("every other brain has a star that makes it the default; the default shows a filled star", () => {
  const src = read("brain-picker.js");
  assert.ok(src.includes('actBtn("default", "star", t("bpick.make_default"'), "a star button on non-default rows");
  assert.ok(src.includes('icon("star", { cls: "ic-fill" })'), "a filled star mark on the default row");
  assert.ok(src.includes("root.JavisBrains.setDefault(edit.value)"), "the form calls brains-ui's setDefault");
  assert.ok(src.includes(': t("bpick.delete", null, "Delete"), isDefault);'), "the default row's delete stays disabled");
});
check("the delete form says what a delete would stop", () => {
  const src = read("brain-picker.js");
  assert.ok(src.includes('fetch("/brains/ties?brain=" + encodeURIComponent(mine.value))'));
  assert.ok(src.includes("tiesHtml(edit.ties)"));
});
check("brains-ui exposes setDefault and posts it to the server", () => {
  const src = read("brains-ui.js");
  assert.ok(src.includes('post("/brains/default", { brain: value })'));
  assert.ok(/window\.JavisBrains = \{[^}]*setDefault/.test(src));
});
if (process.exitCode) process.exit(process.exitCode);
