/* Load-order helper for tests that pin "file A runs before file B" in dashboard/index.html (0.417.0).

   Since nap-cham.js, the large page modules are not <script> tags any more: they sit in <script id="javis-lazy"> and run
   after every eager file (in the background once the page is idle, or when their page opens), in the order they are
   listed. So "A before B" holds when A is eager and B is lazy, when both are eager in that order, or when both are lazy
   in that order. Not a test file itself (no `test_` prefix): the CI loop does not run it. */
const fs = require("fs");
const path = require("path");

function docIndex(html) {
  return html || fs.readFileSync(path.join(__dirname, "../../dashboard/index.html"), "utf8");
}

// Position of a file in run order: eager tags by their place in index.html, lazy files after all of them.
function viTri(file, html) {
  html = docIndex(html);
  const ten = String(file).replace(/^\/?static\//, "").replace(/^\//, "");
  const tag = new RegExp('<(?:script src|link rel="stylesheet" href)="/static/' + ten.replace(/[.]/g, "\\.") + '\\?');
  const m = tag.exec(html);
  if (m) return m.index;
  const blk = /<script id="javis-lazy" type="application\/json">([\s\S]*?)<\/script>/.exec(html);
  if (!blk) return -1;
  const ds = Object.values(JSON.parse(blk[1])).flat().map(u => u.slice(8).split("?")[0]);
  const i = ds.indexOf(ten);
  return i < 0 ? -1 : 1e9 + i;
}

function coNap(file, html) { return viTri(file, html) >= 0; }
function napCham(file, html) { return viTri(file, html) >= 1e9; }
// A runs before every one of the others.
function napTruoc(a, others, html) {
  const pa = viTri(a, html);
  return pa >= 0 && [].concat(others).every(b => { const pb = viTri(b, html); return pb >= 0 && pa < pb; });
}

module.exports = { viTri, coNap, napCham, napTruoc };
