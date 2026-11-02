// Rich clipboard and formatted user bubbles: pure tree fixtures, no browser/network.
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Rich = require("../../dashboard/chat-richtext.js");

function text(s) { return { nodeType: 3, nodeValue: s, textContent: s }; }
function elem(tag, attrs, parts) {
  const children = (parts || []).map(x => typeof x === "string" ? text(x) : x);
  return { nodeType: 1, tagName: tag.toUpperCase(), childNodes: children,
    getAttribute(name) { return (attrs || {})[name] || null; },
    get textContent() { return children.map(x => x.textContent).join(""); }
  };
}
function htmlFixture(tree, plain, src) {
  const old = global.DOMParser;
  global.DOMParser = class { parseFromString(input, type) {
    assert.equal(input, src);
    assert.equal(type, "text/html");
    return { body: tree };
  } };
  try { return Rich.prepare(plain, src); }
  finally { if (old === undefined) delete global.DOMParser; else global.DOMParser = old; }
}
const body = (...children) => elem("body", {}, children);
function check(label, fn) {
  try { fn(); console.log("ok " + label); }
  catch (e) { console.error("FAIL " + label + ": " + e.message); process.exitCode = 1; }
}

check("Google Docs normal-weight <b> never bolds the entire paste", () => {
  const doc = body(elem("b", { style: "font-weight:normal" }, ["This is just ordinary text."]));
  assert.equal(htmlFixture(doc, "This is just ordinary text.", "<docs-normal>"),
    "This is just ordinary text.");
});
check("Docs normal wrapper retains only real bold inside", () => {
  const doc = body(elem("b", { style: "font-weight:normal" }, [
    "A ", elem("span", { style: "font-weight:700" }, ["bold"]), " word."
  ]));
  assert.equal(htmlFixture(doc, "A bold word.", "<docs-selection>"), "A **bold** word.");
});
check("A single short bold selection does not gain stray markers", () => {
  const doc = body(elem("b", {}, ["hello"]));
  assert.equal(htmlFixture(doc, "hello", "<web-short>"), "hello");
});
check("Ordered list preserves numbering, start, and explicit item values", () => {
  const doc = body(elem("ol", { start: "3" }, [
    elem("li", {}, ["first"]), elem("li", { value: "8" }, ["second"]),
    elem("li", {}, ["third"])
  ]));
  assert.equal(htmlFixture(doc, "3. first\n8. second\n9. third", "<ol>"),
    "3. first\n8. second\n9. third");
});
check("Table, heading, and mixed formatting are preserved", () => {
  const doc = body(elem("h2", {}, ["Summary"]), elem("table", {}, [
    elem("tbody", {}, [
      elem("tr", {}, [elem("th", {}, ["Item"]), elem("th", {}, ["Price"])]),
      elem("tr", {}, [elem("td", {}, ["A"]), elem("td", {}, ["20"])])
    ])
  ]));
  const md = htmlFixture(doc, "Summary\nItem Price\nA 20", "<table>");
  assert.match(md, /^## Summary/);
  assert.match(md, /\| Item \| Price \|\n\| --- \| --- \|\n\| A \| 20 \|/);
});
check("Unsafe media or merged cells retain plain text, not a misleading table", () => {
  const merged = body(elem("table", {}, [
    elem("tr", {}, [elem("td", { colspan: "2" }, ["A"])])
  ]));
  assert.equal(htmlFixture(merged, "A", "<merge>"), "A");
  const image = body(elem("p", {}, ["Photo ", elem("img", { src: "x" }, [])]));
  assert.equal(htmlFixture(image, "Photo", "<img>"), "Photo");
});
check("Unsafe links never become markdown link destinations", () => {
  const doc = body(elem("p", {}, [elem("a", { href: "javascript:alert(1)" }, ["Click me"])]));
  assert.equal(htmlFixture(doc, "Click me", "<js-link>"), "Click me");
});
check("Existing Markdown and plain pasted text never rewritten", () => {
  assert.equal(Rich.prepare("## Heading\n- a", "<b>different</b>"), "## Heading\n- a");
  assert.equal(Rich.prepare("hello", ""), "hello");
});
check("Quote button remains a quote block; only the following body gets Markdown", () => {
  const Q = require("../../dashboard/chat-quote.js");
  const seen = [];
  const out = Rich.renderUser("> quoted words\n\n**new detail**", s => s, s => {
    seen.push(s); return "<strong>new detail</strong>";
  }, Q);
  assert.deepEqual(seen, ["**new detail**"]);
  assert.equal(out.html, '<span class="uquote">quoted words</span><div class="jv-user-md"><strong>new detail</strong></div>');
  assert.equal(out.rich, true);
  const ordinary = Rich.renderUser("Normal text", s => s, () => "WRONG", Q);
  assert.equal(ordinary.html, "Normal text");
  assert.equal(ordinary.rich, false);
});
check("Both chat composers and bubble renderers use the shared helper", () => {
  const read = name => fs.readFileSync(path.resolve(__dirname, "../../dashboard", name), "utf8");
  for (const name of ["app.js", "teams.js"]) {
    const s = read(name);
    assert.match(s, /JavisRichText\.prepare\(plain, html\)/);
    assert.match(s, /jv-markdown/);
  }
  const index = read("index.html");
  assert.ok(index.indexOf("chat-richtext.js") > index.indexOf("chat-paste.js"));
  assert.ok(index.indexOf("chat-richtext.js") < index.indexOf("app.js?v="));
});
if (process.exitCode) process.exit(process.exitCode);
