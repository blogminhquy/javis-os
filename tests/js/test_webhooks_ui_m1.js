// 0.274.0: webhook event log on the Work page (webhook platform M1). Each stored event shows its state; a failed,
// dead or unknown one offers Retry, and only an unknown one offers Mark done (the owner reconciles it after checking
// outside). Text from the event is escaped, and both languages carry every new string.
const path = require("path");
const fs = require("fs");
const W = require(path.join(__dirname, "../../dashboard/webhooks.js"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

// 0.432.0: a run's actions live on its own page inside the popup (eventActionsHtml); the row only opens it.
const row = (status, extra) => W.eventActionsHtml(Object.assign({ run_id: "ev_1", at: 1, status: status }, extra || {}));
const line = (status, extra) => W.eventRowHtml(Object.assign({ run_id: "ev_1", at: 1, status: status }, extra || {}));
check("done: no action buttons", !row("done").includes("whEvRetry") && !row("done").includes("whEvDone"));
check("failed: Retry, no Mark done", row("failed").includes("whEvRetry") && !row("failed").includes("whEvDone"));
check("dead: Retry", row("dead").includes("whEvRetry"));
check("unknown: Retry and Mark done", row("unknown").includes("whEvRetry") && row("unknown").includes("whEvDone"));
const acts = (h) => h.includes("whEvRetry") || h.includes("whEvDone");
check("queued and running: no actions (the worker owns them), only Details",
  !acts(row("queued")) && !acts(row("running")) && line("running").includes("whEvInfo"));
check("buttons carry the event id", row("unknown").includes('data-ev="ev_1"'));
check("error text is escaped", line("failed", { error: "<img src=x onerror=alert(1)>" }).includes("&lt;img"));
check("a row from the paged API (id, received_at) works too",
  W.eventRowHtml({ id: "ev_9", received_at: 2, status: "unknown" }).includes('data-ev="ev_9"')
  && W.eventActionsHtml({ id: "ev_9", received_at: 2, status: "unknown" }).includes('data-ev="ev_9"'));

const card = W.dialogHtml({ id: "wh_1", name: "Đơn", target: "task", text: "x", level: "full", brain: "/b", url: "/hooks/wh_1",
  enabled: true, history: [{ run_id: "ev_2", at: 3, status: "unknown", result: "" }] }, []);
check("a hook with an unknown event opens on its runs and says what to do", /whTab sel" data-tab="ev"/.test(card)
  && card.includes("wh-need"));
check("the card log has a button for older runs (pagination)", card.includes("whMore"));
const calm = W.dialogHtml({ id: "wh_2", name: "Ổn", target: "task", text: "x", level: "full", brain: "/b", url: "/hooks/wh_2",
  enabled: true, history: [{ run_id: "ev_3", at: 3, status: "done" }] }, []);
check("a hook with nothing to resolve says nothing to do", !calm.includes("wh-need"));

const older = W.dialogHtml({ id: "wh_3", name: "Cũ", target: "task", text: "x", level: "full", brain: "/b", url: "/hooks/wh_3",
  enabled: true, unknown: 1, history: [{ run_id: "ev_4", at: 3, status: "done" }] }, []);
check("an unknown event older than the rows drawn still raises the hint (server count)", older.includes("wh-need"));
check("error codes are shown in words", W.errText({ error: "not_retryable" }) === "wh.err_not_retryable"
  && W.errText({ error: "weird" }) === "wh.save_err");
const keys = ["wh.err_not_found", "wh.err_not_retryable", "wh.err_not_unknown", "wh.st_queued", "wh.st_running", "wh.st_unknown", "wh.st_dead", "wh.retry", "wh.retry_sent",
  "wh.retry_confirm", "wh.mark_done", "wh.more", "wh.unknown_hint"];
for (const lang of ["vi", "en"]) {
  const d = JSON.parse(fs.readFileSync(path.join(__dirname, `../../dashboard/i18n/${lang}.json`), "utf8"));
  check(`${lang}: every new string present`, keys.every(k => d[k] && d[k].length));
}
const js = fs.readFileSync(path.join(__dirname, "../../dashboard/webhooks.js"), "utf8");
check("retry asks first (it may repeat an outside effect)", /confirm\(tw\("wh\.retry_confirm"\)\)/.test(js));
check("older runs come from the paged event API with the cursor", js.includes("/webhooks/events?hook=") && js.includes("&before="));

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
