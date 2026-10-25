// 0.309.0: the bot card no longer pours errors, warnings and pending groups onto the card (owner, 25/10/2026: a raw
// ChatGPT 429 reply and Google links ran out of the card). It shows one status row with counts; the full text and the
// allow/ignore buttons open in a popup. Runs `statusRow` itself in a vm.
//
//     node tests/js/test_bot_card_status.js
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "chatbots.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "style.css"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  " + JSON.stringify(extra)));
  if (!cond) fails++;
}

// Pull the function out of the IIFE and run it with tiny stand-ins for the page helpers.
const start = SRC.indexOf("  function statusRow(parts) {");
const end = SRC.indexOf("\n  }\n", start) + 4;
check("statusRow exists", start > 0 && end > start);
const ctx = {
  window: { t: (k, o) => k + (o && o.count !== undefined ? ":" + o.count : "") },
  esc: (s) => String(s).replace(/</g, "&lt;"),
  ic: (n) => "<i " + n + ">",
};
vm.createContext(ctx);
vm.runInContext(SRC.slice(start, end) + "\nthis.statusRow = statusRow;", ctx);
const row = ctx.statusRow;

check("nothing to report: no row at all", row({ err: ["", ""], warn: [""], wait: [""] }) === "");
const two = '<div class="cb-nhomcho" data-cid="1"></div><div class="cb-nhomcho" data-cid="2"></div>';
const r = row({ err: ['<div class="cb-err">x</div>', ""], warn: ['<div>w</div>'], wait: [two] });
check("counts errors, warnings and each waiting group",
  r.includes("cb.st_err:1") && r.includes("cb.st_warn:1") && r.includes("cb.st_wait:2"), r);
check("the row takes the colour of its most serious item", /class="cb-st err"/.test(r));
check("only waiting groups: info colour", /class="cb-st wait"/.test(row({ err: [], warn: [], wait: [two] })));
check("the long text itself is never on the card row", !r.includes("cb-err"));

check("the card renders the status row instead of the raw blocks",
  SRC.includes("statusRow({ err: [loiTen, mat, lluot, loi], warn: [riengTu, cbao], wait: [cho] })")
  && !SRC.includes("cho + loiTen + riengTu + mat + lluot + cbao + loi +\n"));
check("the popup gets the full blocks and wires allow/ignore",
  /function openStatus\(b, html\)/.test(SRC) && SRC.includes("choNhom(b, cid, true, loai)")
  && SRC.includes("choNhom(b, cid, false, loai)"));
check("errors are no longer cut at 160/200 characters for the popup",
  SRC.includes("String(b.loi_luot).slice(0, 2000)") && SRC.includes("String(st.last_error).slice(0, 2000)"));
check("long words and links wrap instead of running out of the card",
  /\.cb-err, \.cb-quyen-t, \.cb-nhomcho-t, \.cb-nhomcho-d \{ overflow-wrap: anywhere;/.test(CSS));
check("the row and the popup text are at least 16px", /\.cb-st \{[^}]*font-size: 16px/.test(CSS)
  && /\.cb-st-body \.cb-err[^{]*\{ font-size: 16px; \}/.test(CSS));
check("the bot menu names the import action for each account that can import old messages",
  SRC.includes('class="cb-nhap-cu"') && SRC.includes('window.t("ht.nhap_cu")')
  && SRC.includes('querySelectorAll(".cb-kenh-nhap-cu, .cb-nhap-cu")'));
for (const k of ["cb.st_title", "cb.st_open", "cb.st_err", "cb.st_warn", "cb.st_wait"])
  check("i18n key in vi and en: " + k, !!VI[k] && !!EN[k]);
check("no em or en dash added", ![SRC.slice(start, end), JSON.stringify(VI["cb.st_wait"])].some((s) => /[\u2013\u2014]/.test(s)));

if (fails) { console.log("\nFAIL: " + fails); process.exit(1); }
console.log("\nOK - test_bot_card_status");
