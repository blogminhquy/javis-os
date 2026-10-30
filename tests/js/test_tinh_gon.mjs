/* The server minifies dashboard JS/CSS before sending it (server/tinh_gon.py, 0.416.0). This pins that it never
   changes what the code means.

       node tests/js/test_tinh_gon.mjs

   rjsmin, tried first, broke 3 of these files silently: it ate spaces INSIDE template strings, so
   `" target="_blank"` became `"target="_blank"` and the HTML broke. So for EVERY JS file the dashboard has, this test
   minifies it with the server's own code and compares the token stream with the original, token by token, using
   acorn (vendored next to this test, MIT). Comments and whitespace may go; every string, template, regex, name and
   punctuator must stay exactly as it was, on the same line number. A file that fails here is served unminified until the minifier is fixed,
   never broken. CSS is checked for its invariants (strings kept, comments gone). */
import { tokenizer } from "./vendor/acorn-8.14.0.mjs";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const out = fs.mkdtempSync(path.join(os.tmpdir(), "tinh-gon-"));
const py = process.platform === "win32" ? "python" : "python3";
execFileSync(py, [path.join(ROOT, "server/tinh_gon.py"), "--all", path.join(ROOT, "dashboard"), out]);

function toks(code) {
  let last;
  for (const sourceType of ["script", "module"]) {
    try {
      const list = [];
      for (const t of tokenizer(code, { ecmaVersion: "latest", sourceType, allowHashBang: true, locations: true })) {
        const v = t.value instanceof RegExp ? String(t.value) : (t.value && typeof t.value === "object" ? JSON.stringify(t.value) : t.value);
        // The line is part of the token: the minified file keeps every token on its source line, so error reports from
        // the browser (loi-may-khach.js) and devtools point at the right line of the source.
        list.push(t.loc.start.line + "|" + t.type.label + ":" + (v === undefined ? "" : v));
      }
      return list;
    } catch (e) { last = e; }
  }
  throw last;
}

function walk(dir, acc = []) {
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f);
    if (fs.statSync(p).isDirectory()) walk(p, acc); else acc.push(p);
  }
  return acc;
}

const minified = walk(out);
const jsFiles = minified.filter(f => f.endsWith(".js"));
const cssFiles = minified.filter(f => f.endsWith(".css"));
check("the minifier produced every dashboard JS file (more than 100)", jsFiles.length > 100);
check("files already minified (.min.) are left alone", !minified.some(f => /\.min\./.test(path.basename(f))));

let same = 0, saved = 0, total = 0;
const broken = [];
for (const m of jsFiles) {
  const rel = path.relative(out, m);
  const src = fs.readFileSync(path.join(ROOT, "dashboard", rel), "utf8");
  const min = fs.readFileSync(m, "utf8");
  total += src.length; saved += src.length - min.length;
  let a, b;
  try { a = toks(src); } catch (e) { broken.push(rel + " (source does not tokenize: " + e.message + ")"); continue; }
  try { b = toks(min); } catch (e) { broken.push(rel + " (minified does not tokenize: " + e.message + ")"); continue; }
  const i = a.findIndex((x, k) => x !== b[k]);
  if (a.length !== b.length || i >= 0) { broken.push(rel + " (token " + i + ": " + a[i] + " became " + b[i] + ")"); continue; }
  same++;
}
broken.forEach(b => console.log("     " + b));
check("every minified JS file has exactly the tokens of its source, each on its source line (" + same + "/" + jsFiles.length + ")", !broken.length);
check("minifying actually saves a lot (over 30% of the JS)", saved / total > 0.3);

for (const m of cssFiles) {
  const rel = path.relative(out, m);
  const min = fs.readFileSync(m, "utf8");
  const src = fs.readFileSync(path.join(ROOT, "dashboard", rel), "utf8");
  const strings = s => (s.replace(/\/\*[\s\S]*?\*\//g, "").match(/"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g) || []);
  check("CSS " + rel + ": no comment left, every string kept, braces balanced",
    !/\/\*/.test(min) && JSON.stringify(strings(src)) === JSON.stringify(strings(min))
    && (min.match(/\{/g) || []).length === (min.match(/\}/g) || []).length);
}

// Server wiring: the cache key and the freshness guard hash the bytes that are SENT, not the file on disk.
const main = fs.readFileSync(path.join(ROOT, "server/main.py"), "utf8");
check("static files go through _TinhGonStatic", /app\.mount\("\/static", _TinhGonStatic\(directory=str\(DASHBOARD_PATH\)\), name="static"\)/.test(main));
check("the ?v= key is the crc of the served bytes", /_data, crc = tinh_gon\.ban_phuc_vu\(f, rel\)/.test(main));
const tg = fs.readFileSync(path.join(ROOT, "server/tinh_gon.py"), "utf8");
check("any minifier error falls back to the original file", /except Exception:[^\n]*\n\s+data = goc/.test(tg));
check("JAVIS_MINIFY=0 turns it off", /JAVIS_MINIFY/.test(tg));

fs.rmSync(out, { recursive: true, force: true });
if (fails.length) { console.log("\nFAIL - test_tinh_gon: " + fails.length); process.exit(1); }
console.log("\nOK - test_tinh_gon: all pass");
