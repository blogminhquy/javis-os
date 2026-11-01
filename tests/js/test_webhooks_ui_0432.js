// 0.432.0: the redesigned Webhook page. The owner asked (2026-11-01) for a page that is easy to follow, a popup that
// opens on press instead of a section that drops down, a popup that stays put until it is closed, and no title that
// repeats the page header.
const fs = require("fs");
const path = require("path");
const W = require(path.join(__dirname, "../../dashboard/webhooks.js"));
const js = fs.readFileSync(path.join(__dirname, "../../dashboard/webhooks.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "../../dashboard/webhooks.css"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "../../dashboard/index.html"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(__dirname, "../../dashboard/i18n/vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(__dirname, "../../dashboard/i18n/en.json"), "utf8"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

const now = Date.now() / 1000;
const hook = { id: "wh_1", name: "POS -> Zalo", target: "workflow", workflow: "don", level: "full", brain: "/b", url: "https://x/hooks/wh_1",
  enabled: true, paused: false, count: 477, last_at: now - 60, last_status: "silent", unknown: 0, blocked: 0, failed: 0,
  history: [{ run_id: "ev_3", at: now - 60, status: "silent", state: "done", result: "[SILENT]" },
    { run_id: "ev_2", at: now - 120, status: "failed", result: "crm 500" },
    { run_id: "ev_1", at: now - 86400 * 3, status: "done", result: "sent" }] };

// The list row: folded, opens the popup, shows the last runs as a strip.
const row = W.cardHtml(hook);
check("a hook is one folded row that opens a popup", row.includes('class="wh-row whOpen" data-hook="wh_1"') && row.includes('aria-haspopup="dialog"'));
check("the row shows its count and its last run", row.includes("477") && row.includes("wh.last_short"));
check("the strip draws one bar per run, oldest first", (W.stripHtml(hook).match(/<i /g) || []).length === 3
  && /<i [^>]*title="[^"]*wh\.st_done"/.test(W.stripHtml(hook).split("</i>")[0]));
check("the strip marks the failed run", W.stripHtml(hook).includes('<i class="wh-t-bad"'));
check("a hook with no runs draws no strip", W.stripHtml(Object.assign({}, hook, { history: [] })) === "");

// The overview: one compact row, the banner only when something waits for the owner.
const st = W.statsHtml([hook, Object.assign({}, hook, { id: "wh_2", paused: true, unknown: 2 })], { received: 42, dead: 1, errors_by_target: [] });
check("overview: running count, events in 24 h, need you, errors", st.includes("1/2") && st.includes(">42<") && /wh-stat ask"><b>2</.test(st)
  && /wh-stat bad"><b>1</.test(st));
check("overview without health shows a dash, not zero", W.statsHtml([hook], null).includes("<b>-</b>"));
check("no banner when nothing waits", W.alertHtml([hook]) === "");
const al = W.alertHtml([hook, Object.assign({}, hook, { id: "wh_2", name: "Form <x>", blocked: 1 })]);
check("the banner names the hook (escaped) and opens it on its runs", al.includes("Form &lt;x&gt;") && al.includes('data-hook="wh_2" data-tab="ev"'));

// Runs: grouped by day, the agent's [SILENT] marker hidden, actions on the run's own page.
const rows = W.rowsHtml(hook.history, "", now);
check("runs are grouped under a day line", (rows.match(/class="wh-day"/g) || []).length === 2 && rows.includes("wh.today"));
check("paging appends under the last day without repeating its line",
  !W.rowsHtml([hook.history[0]], rows.match(/data-day="([^"]+)"/)[1], now).includes("wh-day"));
check("the [SILENT] marker is not shown", !rows.includes("[SILENT]"));
check("a run's page has a way back, its actions and a host for the detail",
  W.eventViewHtml(hook.history[1], null).includes("whBack") && W.eventViewHtml(hook.history[1], null).includes("whEvRetry")
  && W.eventViewHtml(hook.history[1], null).includes("whEvDetail"));

// The popup: three parts, two switches, bulk actions only when they apply.
const dlg = W.dialogHtml(hook, []);
check("the popup has a close button and its own title", dlg.includes("whClose") && dlg.includes('id="whDlgTitle"'));
check("bulk close and retry only when there is something to close or retry", !dlg.includes("whCloseFailed") && !dlg.includes("whRetryBlocked")
  && W.dialogHtml(Object.assign({}, hook, { failed: 2, blocked: 1 }), []).includes("whCloseFailed")
  && W.dialogHtml(Object.assign({}, hook, { failed: 2, blocked: 1 }), []).includes("whRetryBlocked"));
check("the switches are real switches", (dlg.match(/role="switch"/g) || []).length === 2);
check("health is drawn as tiles in groups", W.healthHtml({ received: 3 }).includes("wh-hgrid") && W.healthHtml({ received: 3 }).includes("wh.hg_flow"));

// Wiring: the popup is built once and only its inside changes; it closes only by the owner.
check("the popup shell is built in one place (openShell)", (js.match(/class="wh-scrim whClose"/g) || []).length === 1);
check("switching a tab does not rebuild the popup", /function switchTab[\s\S]*?\n {4}\}/.exec(js)[0].indexOf("innerHTML") === -1);
check("Esc steps back from a run before it closes", js.includes("if (sub && !sub.hidden) { hideSub(); return; }"));
check("a refresh keeps the popup open and redraws its head in place", js.includes('M.el.querySelector(".wh-dhead").innerHTML = headHtml(h, M.tab)'));
check("leaving the page closes the popup", js.includes("function unmount()") && fs.readFileSync(path.join(__dirname, "../../dashboard/console.js"), "utf8")
  .includes("window.JavisWebhooks.unmount()"));

// The page draws no title of its own: the page header already says Webhook.
check("no in-page title", !js.includes('"wh.head"') && !("wh.head" in vi) && !("wh.head" in en));
check("the stylesheet loads with the page", html.includes('"/static/webhooks.css?v=') && html.includes('"/static/webhooks.js?v=8"'));
check("nothing in the stylesheet is under 16px", !/font-size:\s*1[0-5](\.\d+)?px/.test(css));
const used = new Set((js.match(/"wh\.[a-z0-9_]+"/g) || []).map((k) => k.slice(1, -1)));
const missing = [...used].filter((k) => !(k in vi) || !(k in en));
check("every key in both languages" + (missing.length ? ": " + missing.join(", ") : ""), !missing.length);

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
