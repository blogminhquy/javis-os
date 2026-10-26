/* PDF on a phone always has a way out (0.332.0).

       node tests/js/test_pdf_dong_tren_dien_thoai.js

Owner 2026-10-26: "ở điện thoại ấn vào file pdf không có nút để tắt". Safari on an iPhone grows a PDF iframe to the
whole document, so scrolling through it carried the toolbar (and its close button) off the top. The PDF now scrolls
in its own box, and on a phone a round close button floats over it, in both viewers (pinned editor and modal).
*/
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const con = fs.readFileSync(path.join(ROOT, "dashboard/console.js"), "utf8");
const fe = fs.readFileSync(path.join(ROOT, "dashboard/file-editor.js"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "dashboard/style.css"), "utf8");
let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const pdf = (con.match(/if \(VT_FRAME_EXTS\.includes\(ext\)\) \{[\s\S]*?return;\n    \}/) || [""])[0];
check("pinned editor: the PDF iframe sits in its own scrolling box", /<div class="ne-pdf"><iframe class="ne-frame"/.test(pdf));
check("pinned editor: a floating close button that closes the editor", /pdf-float-close/.test(pdf) && /\.onclick = closeNote/.test(pdf));
const rp = (fe.match(/function renderPdf\([\s\S]*?\n  \}/) || [""])[0];
check("modal: the PDF iframe sits in its own scrolling box", /class="jvfe-pdf"><iframe class="jvfe-frame"/.test(rp));
check("modal: a floating close button (the modal's own close)", /x = closeBtn\(\)/.test(rp) && /pdf-float-close/.test(rp));
check("modal CSS: the box scrolls, not the page", /\.jvfe-pdf\{max-height:72vh;overflow:auto/.test(fe));
check("CSS: the box scrolls (touch scrolling on iOS)", /\.ne-pdf \{[^}]*overflow: auto;[^}]*-webkit-overflow-scrolling: touch/.test(css));
check("CSS: floating close hidden by default (desktop keeps only the toolbar X)", /\.pdf-float-close \{ display: none; \}/.test(css));
const mq = (css.match(/@media \(max-width: 860px\), \(pointer: coarse\) \{\s*\.pdf-float-close \{[^}]*\}/) || [""])[0];
check("CSS: on a phone it is fixed on screen, clear of the home bar, big enough for a thumb",
  /position: fixed/.test(mq) && /safe-area-inset-bottom/.test(mq) && /width: 52px; height: 52px/.test(mq));

if (fails.length) { console.log("\nFAIL - test_pdf_dong_tren_dien_thoai: " + fails.length); process.exit(1); }
console.log("\nOK - test_pdf_dong_tren_dien_thoai: all pass");
