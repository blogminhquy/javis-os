// Issue 1534: a wikilink to a short note name ([[log]] -> wiki/log.md) missed even though the file exists. wkResolve
// searched /files/search without a mode, so the server ran mode=all: files that only MENTION "log" in their text
// filled the 200 results before the walk reached wiki/log.md. A link only needs file NAMES, so it asks mode=name.
//
// The test cuts wkResolve and its helpers out of chat-render.js and RUNS them with a fake fetch.
//
//     node tests/js/test_wikilink_name_search.js
"use strict";
const fs = require("fs");
const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "chat-render.js"), "utf8");

let fails = 0;
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails++;
}

const start = src.indexOf("  var wkHome = null;");
const end = src.indexOf("  function openWikilink(");
check("wkResolve and its helpers are found in chat-render.js", start > 0 && end > start);

const urls = [];
function fakeFetch(url) {
  urls.push(url);
  if (url.indexOf("/files/list") === 0) return Promise.resolve({ ok: true, json: () => Promise.resolve({ home: "" }) });
  const u = new URL(url, "http://x");
  // A big brain: 200 files mention "log" in their text, the real note comes later in the walk.
  const items = [];
  if (u.searchParams.get("mode") !== "name") {
    for (let i = 0; i < 200; i++) items.push({ path: "notes/n" + i + ".md", name: "n" + i + ".md", ext: ".md" });
  }
  if (items.length < 200) items.push({ path: "wiki/log.md", name: "log.md", ext: ".md" });
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: items }) });
}

const make = new Function("fetch", "brainPath",
  src.slice(start, end) + "\nreturn wkResolve;");
const wkResolve = make(fakeFetch, function () { return "brain"; });

wkResolve("log").then(function (hit) {
  const search = urls.filter(function (u) { return u.indexOf("/files/search") === 0; });
  check("the link asks the server for names only (mode=name)", search.length === 1 && /[?&]mode=name(&|$)/.test(search[0]));
  check("[[log]] opens wiki/log.md in a brain full of files that mention log", !!hit && hit.rel === "wiki/log.md");
  if (fails) { console.log(fails + " FAIL"); process.exit(1); }
  console.log("all ok");
}).catch(function (e) { console.log("FAIL " + e); process.exit(1); });
