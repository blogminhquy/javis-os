// The waiting list on a bot card is settled in ONE press (owner, 13/11/2026: a bot with nine waiting groups took nine
// rounds of "open the popup, press Allow this group, the popup closes"). Each waiting chat is now a tick box, with
// "select all" and one Allow / Ignore bar for every ticked row; the server takes the whole batch in one request.
//
//     node tests/js/test_bot_pending_bulk.js
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
function cut(head) {
  const start = SRC.indexOf(head);
  const end = SRC.indexOf("\n  }\n", start) + 4;
  check("found: " + head.trim(), start > 0 && end > start);
  return SRC.slice(start, end);
}

// ---- 1. The rows: one tick box each, no button of their own -------------------------------------------------------
const calls = [];
const ctx = {
  window: { t: (k, o) => k + (o && o.count !== undefined ? ":" + o.count : "") },
  esc: (s) => String(s).replace(/</g, "&lt;"),
  ic: (n) => "<i " + n + ">",
  api: (url, opts) => { calls.push({ url, body: opts.body }); return Promise.resolve({ ok: true }); },
  fd: (o) => o,
  encodeURIComponent, JSON,
};
vm.createContext(ctx);
vm.runInContext(cut("  function pendingRows(list) {") + cut("  function statusRow(parts) {") +
  cut("  function settlePending(b, kind, ids, on) {") +
  "\nthis.pendingRows = pendingRows; this.statusRow = statusRow; this.settlePending = settlePending;", ctx);

const html = ctx.pendingRows([
  { chat_id: "-1001", loai: "group", ten: "Kho <A>", lan: 3 },
  { chat_id: "-1002", loai: "group", ten: "", lan: 0 },
  { chat_id: "77", loai: "private", ten: "Lan", lan: 2 },
  { chat_id: "78", loai: "private", ten: "Minh", lan: 0 },
]);
const rows = html.split("</label>").filter(Boolean);
check("one row per waiting chat", rows.length === 4, rows.length);
check("every row is a label holding one tick box, so the whole row is the tap target",
  rows.every((r) => r.startsWith('<label class="cb-nhomcho"') && (r.match(/type="checkbox" class="cb-pd-c"/g) || []).length === 1));
check("no row is ticked in the markup: allowing a chat is a choice, never the default", !/checked/.test(html));
check("a row carries no button of its own", !/<button/.test(html) && !/cb-ok-nhom|cb-bo-nhom/.test(SRC));
check("a row carries the chat id and its kind for the request",
  /data-cid="-1001" data-loai="group"/.test(html) && /data-cid="77" data-loai="private"/.test(html));
check("the name is escaped", html.includes("Kho &lt;A>") && !html.includes("Kho <A>"));
check("a group without a name falls back to its id", rows[1].includes("cb.nhom -1002"));
check("a group where the bot was called says how often; a quiet one says nothing more",
  rows[0].includes("cb.pd_called:3") && !rows[1].includes("cb-nhomcho-d"));
check("a person says how often they wrote, or that they just wrote",
  rows[2].includes("cb.pd_wrote:2") && rows[3].includes("cb.pd_new"));
check("the card's status row still counts these rows",
  ctx.statusRow({ err: [], warn: [], wait: [html] }).includes("cb.st_wait:4"));

// ---- 2. The request: the whole batch in one call per kind -----------------------------------------------------------
(async () => {
  await ctx.settlePending({ id: "b 1" }, "group", ["-1001", "-1002"], true);
  await ctx.settlePending({ id: "b 1" }, "private", ["77"], false);
  check("groups go to /groups as ONE request carrying every id",
    calls[0].url === "/chatbots/b%201/groups" && calls[0].body.chat_ids === '["-1001","-1002"]' && calls[0].body.on === "1", calls[0]);
  check("people go to /people, and Ignore sends on=0",
    calls[1].url === "/chatbots/b%201/people" && calls[1].body.chat_ids === '["77"]' && calls[1].body.on === "0", calls[1]);

  // ---- 3. The popup: select all, counts on the buttons, stays open ------------------------------------------------
  const pop = cut("  function openStatus(b, pending, rest) {");
  const whole = SRC.slice(SRC.indexOf("  function openStatus(b, pending, rest) {"), SRC.indexOf("  function settlePending("));
  check("the popup has a select-all box, a counter and one Allow / Ignore bar",
    pop.includes('class="cb-pd-all"') && pop.includes('class="cb-pd-n"') && pop.includes('class="s-btn cb-pd-ok"')
    && pop.includes('class="s-btn-ghost cb-pd-skip"'));
  check("select all ticks every row, and shows the half state when only some are ticked",
    /checked = all\.checked/.test(whole) && /all\.indeterminate = n > 0 && n < rs\.length/.test(whole));
  check("the buttons carry the number of ticked rows and are off when none is ticked",
    /window\.t\("cb\.pd_allow"\)\) \+ \(n \? " \(" \+ n \+ "\)" : ""\)/.test(whole) && /ok\.disabled = skip\.disabled = busy \|\| !n/.test(whole));
  check("nothing is ticked on opening, except when a single row waits",
    /if \(total === 1\) rows\(\)\[0\]\.querySelector\("\.cb-pd-c"\)\.checked = true/.test(whole));
  check("the select-all line hides when one row is left", /\.cb-pd-pick"\)\.hidden = rs\.length < 2/.test(whole));
  check("settling does not close the popup while rows or other status blocks are left",
    /if \(!rows\(\)\.length\) \{[\s\S]*?if \(!box\.querySelector\("\.cb-st-body"\)\.children\.length\) \{ close\(\); return; \}/.test(whole)
    && !/onclick = function \(\) \{ close\(\); /.test(whole));
  check("a failed request shows its error in the popup instead of an alert, and keeps the rows",
    /catch \(e\) \{ err = e\.message; \}/.test(whole) && /"cb\.loi_cap_nhat_nhom"/.test(whole) && !/alert\(/.test(whole));
  check("the cards behind are refreshed without the loading flash", /tai\(true\)/.test(whole));
  check("the long explanation sits behind (i)", /infoBody\(esc\(window\.t\("cb\.pd_info"\)\)\)/.test(whole));

  // ---- 4. Looks: a thumb-sized row, a bar that stays in view, text a phone can read --------------------------------
  check("a row is at least 48px tall and the buttons 44px",
    /label\.cb-nhomcho \{[^}]*min-height: 48px/.test(CSS) && /\.cb-pd-bar \.s-btn, \.cb-pd-bar \.s-btn-ghost \{ min-height: 44px/.test(CSS));
  check("the action bar sticks to the bottom of the popup", /\.cb-pd-bar \{ position: sticky; bottom: -18px/.test(CSS));
  check("names are 16px and may wrap", /\.cb-nhomcho-t \{ font-size: 16px/.test(CSS)
    && /\.cb-nhomcho-t, \.cb-nhomcho-d \{ overflow-wrap: anywhere/.test(CSS));
  check("on a phone the two buttons share the row without wrapping",
    /@media \(max-width: 600px\) \{[\s\S]*?\.cb-pd-bar \.s-btn, \.cb-pd-bar \.s-btn-ghost \{ flex: 1 1 0/.test(CSS)
    && /white-space: nowrap; \}/.test(CSS));

  // ---- 5. Words ----------------------------------------------------------------------------------------------------
  const keys = ["cb.pd_all", "cb.pd_count", "cb.pd_allow", "cb.pd_called", "cb.pd_called.one", "cb.pd_called.other",
    "cb.pd_wrote", "cb.pd_wrote.one", "cb.pd_wrote.other", "cb.pd_new", "cb.pd_done_allow", "cb.pd_done_allow.one",
    "cb.pd_done_allow.other", "cb.pd_done_skip", "cb.pd_done_skip.one", "cb.pd_done_skip.other", "cb.pd_info"];
  for (const k of keys) check("i18n key in vi and en: " + k, !!VI[k] && !!EN[k]);
  check("every key is used by the page", keys.filter((k) => !/\.(one|other)$/.test(k)).every((k) => SRC.includes('"' + k + '"')));
  check("the per-row wording of the old buttons is gone from both dictionaries",
    !["cb.cho_phep_nhom", "cb2.cho_nguoi", "cb.nhomcho_chua_bat", "cb.nhomcho_goi", "cb2.nguoicho_goi", "cb2.nguoicho_moi"]
      .some((k) => k in VI || k in EN));
  check("no em or en dash added", !keys.some((k) => /[–—]/.test(VI[k] + EN[k])) && !/[–—]/.test(whole));

  if (fails) { console.log("\nFAIL: " + fails); process.exit(1); }
  console.log("\nOK - test_bot_pending_bulk");
})();
