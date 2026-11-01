// An .html file opens on its preview, with a Code tab (0.430.2, dashboard/html-preview.js).
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const HP = require("../../dashboard/html-preview.js");
const read = (f) => fs.readFileSync(path.resolve(__dirname, "../../dashboard", f), "utf8");

function check(name, fn) {
  try { fn(); console.log("ok   " + name); }
  catch (e) { console.error("FAIL " + name + ": " + e.message); process.exitCode = 1; }
}
check("only .html / .htm files get the preview", () => {
  assert.equal(HP.isHtmlPath("exports/landing.html"), true);
  assert.equal(HP.isHtmlPath("a/B.HTM"), true);
  assert.equal(HP.isHtmlPath("notes/x.md"), false);
  assert.equal(HP.isHtmlPath("x.html.txt"), false);
});
check("only relative asset URLs are fetched from the brain", () => {
  for (const u of ["img/a.png", "./a.css", "../x.js", "/attachments/a.jpg", "a%20b.png"]) assert.equal(HP.isRelativeUrl(u), true, u);
  for (const u of ["https://cdn.x/a.png", "//cdn.x/a.js", "data:image/png;base64,x", "#top", "", "javascript:alert(1)", "mailto:a@b", "{{img}}", "${x}"]) {
    assert.equal(HP.isRelativeUrl(u), false, u);
  }
});
check("relative paths resolve against the file's folder", () => {
  assert.equal(HP.resolveRel("site", "img/a.png"), "site/img/a.png");
  assert.equal(HP.resolveRel("site/sub", "../css/s.css?v=2"), "site/css/s.css");
  assert.equal(HP.resolveRel("site", "./a%20b.png#x"), "site/a b.png");
  assert.equal(HP.resolveRel("site", "/attachments/a.jpg"), "attachments/a.jpg");
  assert.equal(HP.resolveRel("", "../../etc/passwd"), "etc/passwd");   // never climbs above the root
  assert.equal(HP.dirOf("exports/site/index.html"), "exports/site");
  assert.equal(HP.dirOf("index.html"), "");
});
check("the preview never shares Javis's origin", () => {
  assert.ok(!/allow-same-origin/.test(HP.SANDBOX));
  assert.ok(/allow-scripts/.test(HP.SANDBOX));
});
check("both file viewers open .html on the preview", () => {
  const fe = read("file-editor.js");
  assert.ok(fe.includes("JavisHtmlPreview.isHtmlPath(ceil)) renderHtmlEditor(b, ceil, d)"));
  assert.ok(fe.includes('<div class="jvfe-html mode-preview">'));
  const cs = read("console.js");
  assert.ok(cs.includes("JavisHtmlPreview.isHtmlPath(rel)) _neHtmlTabs(body, actions, ta, rel)"));
  assert.ok(cs.includes('body.className = "ne-body mode-preview"'));
});
check("html-preview.js loads before the viewers", () => {
  const html = read("index.html");
  const at = html.indexOf("/static/html-preview.js?v=");
  assert.ok(at > 0 && at < html.indexOf("/static/file-editor.js?v=") && at < html.indexOf("/static/console.js?v="));
});
if (process.exitCode) process.exit(process.exitCode);
