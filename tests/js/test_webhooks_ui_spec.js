// 0.274.0 (spec §12): the webhook card has three parts (Configuration / Events / Health), two separate switches
// (stop receiving vs pause processing), a real test send that previews before sending, an event timeline, a masked
// payload whose raw view asks first, "process again with the current setup" that previews and names what would act
// again, health that never presents a 202 as a finished order, and a save that carries the revision (409 handled).
const fs = require("fs");
const path = require("path");
const W = require(path.join(__dirname, "../../dashboard/webhooks.js"));
const js = fs.readFileSync(path.join(__dirname, "../../dashboard/webhooks.js"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(__dirname, "../../dashboard/i18n/vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(__dirname, "../../dashboard/i18n/en.json"), "utf8"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

const base = { id: "wh_1", name: "Đơn", target: "task", text: "x", level: "full", brain: "/b", url: "https://x/hooks/wh_1",
  enabled: true, paused: false, revision: 3, history: [], token_header: "X-Javis-Token" };
const calm = W.cardHtml(base, []);
check("three parts: Configuration, Events, Health", ["wh.tab_cfg", "wh.tab_events", "wh.tab_health"].every((k) => calm.includes(k))
  && (calm.match(/class="whPane"/g) || []).length === 3);
check("a calm card opens on Configuration", /whTab sel" data-tab="cfg"/.test(calm) && calm.includes('data-pane="ev" style="display:none"'));
const busy = W.cardHtml(Object.assign({}, base, { blocked: 1 }), []);
check("a card with a blocked event opens on Events with the hint", /whTab sel" data-tab="ev"/.test(busy) && busy.includes("wh-need"));
check("two switches, never one: stop receiving and pause processing", calm.includes("whToggle") && calm.includes("whPause")
  && calm.includes("wh.receiving_on") && calm.includes("wh.paused_off"));
const paused = W.cardHtml(Object.assign({}, base, { paused: true, enabled: false }), []);
check("paused and stopped are shown apart", paused.includes("wh.paused_badge") && paused.includes("wh.resume")
  && paused.includes("wh.turn_on") && paused.includes("wh.receiving_off"));
check("events part: status, order or correlation id, time range, export, older runs", ["whFilter", "whQ", "whSince", "whUntil",
  "/webhooks/events/export?hook=wh_1", "whMore"].every((c) => calm.includes(c)));
check("the card says where the key goes (never the key)", calm.includes("wh.key_where") && !/tok_|Bearer [a-z0-9]/i.test(calm));
check("a legacy hook says ?token= still works for it", W.cardHtml(Object.assign({}, base, { query_token: true }), []).includes("wh.key_where_legacy"));
check("AI incident sorting is shown when on", W.cardHtml(Object.assign({}, base, { ai_triage: true }), []).includes("wh.ai_triage_on")
  && !calm.includes("wh.ai_triage_on"));

check("a hook with only outside actions names them instead of an empty job line",
  W.targetLine({ target: "", text: "", actions: [{ id: "crm", kind: "http" }] }) === "wh.target_actions_line"
  && W.targetLine({ target: "task", text: "Gọi lại", actions: [{ id: "ai", kind: "ai" }] }) === "wh.target_task_line");
const ran = W.detailHtml({ id: "ev_2", status: "failed", error: "crm: dead", branches: [], trace: { filter: [{ path: "status", op: "eq", pass: true }] } });
check("a stored trace (no values) shows no placeholder value, and a run event says it passed, not 'would run'",
  !ran.includes("∅") && ran.includes("wh.sim_ran") && !ran.includes("wh.sim_run"));
check("state words: the spec state, with the internal status when it adds something",
  W.stateWord({ status: "unknown", state: "waiting" }) === "wh.ss_waiting (wh.st_unknown)"
  && W.stateWord({ status: "done", state: "done" }) === "wh.ss_done"
  && W.stateWord({ status: "failed", state: "partial_failed" }) === "wh.ss_partial_failed (wh.st_failed)"
  && W.stateWord({ status: "filtered" }) === "wh.st_filtered");
check("a blocked event can be run again", W.eventRowHtml({ id: "ev_1", status: "blocked", state: "waiting" }).includes("whEvRetry"));

const tl = W.timelineHtml([{ at: 1, step: "received", detail: "10 bytes" }, { at: 2, step: "receipt", detail: "crm: <x>" }]);
check("timeline: steps in words, details escaped", tl.includes("wh.tl_received") && tl.includes("wh.tl_receipt") && tl.includes("&lt;x&gt;"));
const masked = W.payloadHtml({ id: "ev_1", payload: '{"phone": "•••"}', masked: true });
check("payload: masked by default, with a raw view button", masked.includes("wh.payload_masked") && masked.includes("whRaw"));
check("payload: the raw view has no second raw button", !W.payloadHtml({ id: "ev_1", payload: "{}", masked: false }).includes("whRaw"));
const det = W.detailHtml({ id: "ev_1", status: "done", branches: [], trace: {}, timeline: [{ at: 1, step: "received" }], payload: "{}", masked: true });
check("event detail: timeline, payload and process-again", det.includes("wh-tl") && det.includes("wh-payload") && det.includes("whReplay"));

const rp = W.replayHtml({ ok: true, id: "ev_1", decision: "run", deliveries: [{ action: "crm", kind: "http", runs: true,
  target: "https://crm/x", already_succeeded: true }, { action: "zalo", kind: "plugin", runs: true, depends_on: ["crm"] }],
  may_repeat: ["crm"] });
check("process again: the plan, what would act again, then a confirm button", rp.includes("<b>crm</b>") && rp.includes("wh.plan_done_before")
  && rp.includes("wh.replay_repeat") && rp.includes("wh.plan_after") && rp.includes('whReplayGo" data-ev="ev_1"'));
check("process again: an order that already ran as another event is named and not offered to run",
  (function () { const h = W.replayHtml({ ok: true, decision: "run", duplicate_of: "ev_9", deliveries: [] });
    return h.includes("wh.replay_dup") && !h.includes("whReplayGo"); })());
check("process again: the current rules would not run it", W.replayHtml({ ok: true, decision: "filtered", reason: "status_mismatch" })
  .includes("wh.replay_no_run") && !W.replayHtml({ ok: true, decision: "filtered" }).includes("whReplayGo"));
check("plan: an action that would not run says why", W.planHtml([{ action: "t", kind: "tool", runs: false, why_not: "not sent: <m>" }])
  .includes("not sent: &lt;m&gt;") && W.planHtml([]).includes("wh.plan_none"));

const hh = W.healthHtml({ received: 5, matched: 3, ignored: 1, quarantined: 1, duplicate_deliveries: 2, duplicate_business: 1,
  backlog: 0, oldest_open_age_s: 0, ack_p50_ms: 3, ack_p95_ms: 9, processing_p50_s: 1, processing_p95_s: 4, retry_wait: 0, dead: 0,
  unknown: 1, blocked: 0, ai_calls: 0, errors_by_target: [{ action_id: "crm", kind: "http", n: 2 }], sql_busy: 0, db_bytes: 1048576,
  wal_bytes: 0, cap: 1073741824, level: "ok" });
check("health: every §12 figure, and 202 is said to be received, not processed", ["wh.h_note", "wh.h_received", "wh.h_matched",
  "wh.h_ignored", "wh.h_duplicates", "wh.h_backlog", "wh.h_oldest", "wh.h_ack", "wh.h_processing", "wh.h_retry", "wh.h_dead",
  "wh.h_unknown", "wh.h_ai", "wh.h_errors", "wh.h_sql_busy", "wh.h_db"].every((k) => hh.includes(k)) && hh.includes("crm (http) 2"));
check("vi: the health note says 202 is not a finished order", /chưa phải đã xử lý xong/.test(vi["wh.h_note"])
  && /not processed/.test(en["wh.h_note"]));

const s = W.settingsHtml({ limits: { per_minute: 300, backlog: 10000 }, ai_per_hour: 30, ai_triage: true });
check("settings: per-minute limit, backlog up to the server bound, AI per hour, AI incident sorting", s.includes("whPerMin")
  && s.includes('value="300"') && s.includes('max="100000"') && s.includes("whAiHour") && /whAiTriage" checked/.test(s));
const fake = { querySelector: (sel) => ({ ".whNotify": { value: "errors_only" }, ".whPerMin": { value: "120" }, ".whPerHour": { value: "" },
  ".whPerDay": { value: "" }, ".whBacklog": { value: "500" }, ".whAiHour": { value: "0" }, ".whAiDay": { value: "" },
  ".whKeep": { value: "30" }, ".whAiTriage": { checked: false } })[sel] };
const rs = W.readSettings(fake);
check("settings are read back with their types", rs.notify === "errors_only" && rs.limits.per_minute === 120 && rs.limits.backlog === 500
  && rs.ai_per_hour === 0 && rs.ai_triage === false && rs.retention_days === 30 && !("per_hour" in rs.limits));
check("test send result: a 202 is 'received, processing', not 'done'", W.testText({ ok: true, accepted: true, state: "received" }) === "wh.test_received");
check("a 409 answer shows the server's words", W.errText({ ok: false, error: "changed elsewhere (revision 4)", _status: 409 }).includes("revision 4"));

check("wiring: the answer carries its HTTP status", js.includes("j._status = r.status"));
check("wiring: save sends the revision edited and stops on 409", js.includes("{ revision: h.revision }") && js.includes("r._status === 409"));
check("wiring: pause uses its own route", js.includes('api("/webhooks/pause", { id: h.id, paused: !h.paused })'));
check("wiring: test send previews without confirm, then sends with confirm", js.includes('api("/webhooks/test", { id: h.id, payload: body() })')
  && js.includes('api("/webhooks/test", { id: h.id, payload: body(), confirm: true })'));
check("wiring: raw view asks first and reads raw=1", js.includes('confirm(tw("wh.raw_confirm"))') && js.includes('"?raw=1"'));
check("wiring: process again previews, then confirms the previewed revision", js.includes('api("/webhooks/events/replay", { id: b.dataset.ev })')
  && js.includes('api("/webhooks/events/replay", { id: go.dataset.ev, confirm: true, revision: p.revision })'));
check("wiring: event filters by correlation and time range", js.includes('"&q=" + encodeURIComponent(q)') && js.includes('"&since=" + since')
  && js.includes('"&until=" + until'));
check("wiring: Retry all blocked posts the hook and reports how many were queued",
  js.includes('api("/webhooks/events/retry_blocked", { hook: h.id })') && js.includes('tw("wh.retried_n", { n: r.queued })')
  && !!vi["wh.retry_blocked"] && !!en["wh.retry_blocked"]);
check("wiring: health part reads /webhooks/health", js.includes('api("/webhooks/health?hook=" + encodeURIComponent(h.id))'));
check("stop receiving asks first and points to pause", js.includes('confirm(tw("wh.turn_off_confirm"))') && /Tạm dừng xử lý/.test(vi["wh.turn_off_confirm"]));
check("no text under 16px in the webhook section", !/font-size:\s*1[0-5]px/.test(js));
const keys = new Set((js.match(/"wh\.[a-z0-9_]+"/g) || []).map((k) => k.slice(1, -1)));
const missing = [...keys].filter((k) => !(k in vi) || !(k in en));
check("every wh.* key has vi and en text", missing.length === 0);
if (missing.length) console.log("  missing:", missing.join(", "));
check("no long dash in the new texts", [...keys].every((k) => !/[—–]/.test((vi[k] || "") + (en[k] || ""))));

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
