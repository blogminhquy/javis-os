/* Webhooks section of the Work page (0.198.0).
 *
 * A webhook is a secret URL: when an outside system (a landing page form, a payment, a sheet) calls it, Javis runs a
 * workflow or a written job with the event attached, then reports like a reminder. Server: server/webhook_triggers.py.
 *
 * The token is shown ONCE, right after creating or rotating, because the server keeps only its hash. Cards show the
 * URL (without the token), the target, the permission level, the last runs, and buttons: copy URL, send a test event,
 * switch on/off, new token, delete.
 *
 * 0.274.0 (spec §12): each card has three parts, Configuration / Events / Health. Two switches stay apart: "Stop
 * receiving" (enabled: new requests are refused) and "Pause processing" (paused: still received and stored within the
 * quotas). A real test send shows what each action would do before anything is sent. An event opens on its timeline;
 * its payload is masked, the raw view asks first and is recorded. "Process again with the current setup" previews
 * first and says which actions already succeeded. Saving sends the revision edited; a 409 says someone saved first.
 *
 * Render helpers are pure (tested under node); `mount` wires the API calls.
 */
(function () {
  "use strict";

  function tw(key, vars) {
    var s = (typeof window !== "undefined" && window.t) ? window.t(key, vars) : key;
    if (vars) {
      s = String(s).replace(/\{(\w+)\}/g, function (m, name) {
        return Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : m;
      });
    }
    return s;
  }
  function esc(t) {
    return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  var ic = function (n) { return (typeof window !== "undefined" && window.ic) ? window.ic(n) : ""; };
  // (i) button from info-tip.js; without it (node tests) the explanation is drawn inline.
  function infoBtn() { var J = typeof window !== "undefined" && window.JavisInfo; return J ? J.btn(tw("info.more")) : ""; }
  function infoBody(html) {
    var J = typeof window !== "undefined" && window.JavisInfo;
    return J ? J.body(html) : '<div class="info-body">' + html + "</div>";
  }

  var LEVEL_KEY = { suggest: "wh.level_suggest", auto: "wh.level_auto", full: "wh.level_full" };
  var STATUS_KEY = { done: "wh.st_done", failed: "wh.st_failed", waiting: "wh.st_waiting", silent: "wh.st_silent",
    queued: "wh.st_queued", running: "wh.st_running", unknown: "wh.st_unknown", dead: "wh.st_dead",
    filtered: "wh.st_filtered", invalid: "wh.st_invalid", duplicate: "wh.st_duplicate", received: "wh.st_received",
    blocked: "wh.st_blocked", cancelled: "wh.st_cancelled" };
  // The event's state in the spec's words (§7), from the server's `state`; the internal status adds detail.
  var STATE_KEY = { ignored: "wh.ss_ignored", quarantined: "wh.ss_quarantined", processing: "wh.ss_processing",
    waiting: "wh.ss_waiting", done: "wh.ss_done", partial_failed: "wh.ss_partial_failed", failed: "wh.ss_failed",
    cancelled: "wh.ss_cancelled" };
  var SAME = { done: "done", failed: "failed", waiting: "waiting", cancelled: "cancelled" };
  function stateWord(r) {
    var st = r.status || "done";
    var base = tw(STATUS_KEY[st] || "wh.st_done");
    if (!r.state || !STATE_KEY[r.state]) return base;
    return SAME[st] === r.state ? tw(STATE_KEY[r.state]) : tw(STATE_KEY[r.state]) + " (" + base + ")";
  }
  // 0.274.0: events are stored durably (server/webhook_store.py). A run that may have acted before the server stopped
  // is "unknown": only the owner decides, after checking outside, whether it happened (Mark done) or not (Retry).
  var RETRYABLE = { failed: 1, unknown: 1, dead: 1, blocked: 1 };

  // One line of the event log: time, status, short result, and the owner's actions for that event.
  function eventRowHtml(r) {
    var st = r.status || "done";
    var acts = "";
    if (RETRYABLE[st]) acts += '<button class="s-btn-ghost whEvRetry" data-ev="' + esc(r.run_id || r.id) + '">' + esc(tw("wh.retry")) + "</button>";
    if (st === "unknown" || st === "waiting") {
      acts += '<button class="s-btn-ghost whEvDone" data-ev="' + esc(r.run_id || r.id) + '">' + esc(tw("wh.mark_done")) + "</button>";
    }
    if (r.run_id || r.id) acts += '<button class="s-btn-ghost whEvInfo" data-ev="' + esc(r.run_id || r.id) + '">' + esc(tw("wh.details")) + "</button>";
    // A failed body is kept until the owner settles it or deletes it (spec §11).
    if (st === "failed" || st === "dead") {
      // Settle without resending (handled outside, or given up): its kept body then follows the normal retention.
      acts += '<button class="s-btn-ghost whEvSettle" data-ev="' + esc(r.run_id || r.id) + '">' + esc(tw("wh.ev_settle")) + "</button>";
      acts += '<button class="s-btn-ghost whEvDel" data-ev="' + esc(r.run_id || r.id) + '">' + esc(tw("wh.ev_delete")) + "</button>";
    }
    return '<div class="le wh-ev wh-ev-' + esc(st) + '">' + esc(fmtTime(r.at || r.received_at)) + " · "
      + '<span class="wh-st">' + esc(stateWord(r)) + "</span>"
      + ((r.result || r.error) ? " · " + esc(String(r.result || r.error).slice(0, 140)) : "")
      + (acts ? '<span class="wh-ev-acts">' + acts + "</span>" : "") + '<div class="whEvDetail"></div></div>';
  }

  // M3: one event in detail: each action's branch (state, what the receiver said, its delivery id) and why the
  // rules decided what they did.
  var BRANCH_KEY = { completed: "wh.br_completed", accepted: "wh.br_accepted", failed: "wh.br_failed", unknown: "wh.br_unknown",
    pending: "wh.br_pending", retry: "wh.br_retry", running: "wh.br_running", silent: "wh.br_silent", waiting: "wh.br_waiting",
    cancelled: "wh.br_cancelled", approval: "wh.br_approval" };
  function detailHtml(ev) {
    if (!ev) return "";
    var out = "";
    (ev.branches || []).forEach(function (b) {
      var bad = b.status === "failed" || b.status === "unknown";
      out += '<div class="wh-br wh-br-' + esc(b.status) + '" style="color:' + (bad ? "var(--warn-ink)" : "var(--text2)") + '">'
        + "<b>" + esc(b.action_id) + "</b> (" + esc(b.kind) + ") · " + esc(tw(BRANCH_KEY[b.status] || "wh.br_pending"))
        + (b.detail ? " · " + esc(b.detail) : "")
        + (b.receipt && b.receipt.ref ? " · " + esc(b.receipt.ref) : "")
        + '<div class="dim" style="color:var(--text3)">' + esc(tw("wh.delivery")) + " <code>" + esc(b.delivery_id) + "</code></div>"
        + (b.status === "approval" ? '<div class="wf-actions"><button class="s-btn whApprove" data-ev="' + esc(ev.id) + '" data-act="'
          + esc(b.action_id) + '" data-d="approve">' + esc(tw("wh.approve")) + '</button><button class="s-btn-ghost whApprove" data-ev="'
          + esc(ev.id) + '" data-act="' + esc(b.action_id) + '" data-d="reject">' + esc(tw("wh.reject")) + "</button></div>" : "")
        + "</div>";
    });
    var t = ev.trace || {};
    var stopped = ev.status === "filtered" || ev.status === "invalid" || ev.status === "duplicate";
    if (t.filter || t.schema || t.mapping || t.duplicate_of) out += simHtml({ ok: true, decision: stopped ? ev.status : "ran",
      reason: stopped ? ev.error || "" : "", trace: t, fields: ev.fields || {} });
    if (!out && !(ev.timeline || []).length) return '<div class="dim" style="color:var(--text3)">' + esc(tw("wh.no_detail")) + "</div>";
    return timelineHtml(ev.timeline) + out + payloadHtml(ev)
      + (ev.id ? '<div class="wf-actions" style="margin-top:6px"><button class="s-btn-ghost whReplay" data-ev="' + esc(ev.id) + '">'
        + esc(tw("wh.replay")) + '</button></div><div class="whReplayOut"></div>' : "");
  }

  // Spec §12: received, verified, parsed, filter, duplicate, dispatch, attempt, receipt, result, notice.
  var STEP_KEY = { received: "wh.tl_received", verified: "wh.tl_verified", parsed: "wh.tl_parsed", filter: "wh.tl_filter",
    duplicate: "wh.tl_duplicate", duplicate_delivery: "wh.tl_duplicate_delivery", ignored: "wh.tl_ignored",
    quarantined: "wh.tl_quarantined", dispatch: "wh.tl_dispatch", attempt: "wh.tl_attempt", receipt: "wh.tl_receipt",
    result: "wh.tl_result", notice: "wh.tl_notice" };
  function timelineHtml(tl) {
    if (!tl || !tl.length) return "";
    return '<div class="wh-tl" style="margin:4px 0 6px;font-size:16px"><b>' + esc(tw("wh.timeline")) + "</b>"
      + tl.map(function (x) {
        return '<div class="wh-tl-step" style="color:var(--text2)">' + esc(fmtTime(x.at)) + " · <b>"
          + esc(tw(STEP_KEY[x.step] || x.step)) + "</b>" + (x.detail ? " · " + esc(x.detail) : "") + "</div>";
      }).join("") + "</div>";
  }
  // The payload as the server sent it: masked unless the owner asked for the raw view (which the server records).
  function payloadHtml(ev) {
    if (ev.payload == null || ev.payload === "") return "";
    return '<details class="wh-payload" style="margin-top:4px"><summary style="cursor:pointer">' + esc(tw(ev.masked === false
      ? "wh.payload_raw" : "wh.payload_masked")) + "</summary>"
      + '<pre class="whPayload" style="white-space:pre-wrap;word-break:break-word;max-height:320px;overflow:auto;font-size:16px">'
      + esc(ev.payload) + "</pre>"
      + (ev.masked !== false && ev.id ? '<button class="s-btn-ghost whRaw" data-ev="' + esc(ev.id) + '">' + esc(tw("wh.view_raw"))
        + "</button>" : "") + "</details>";
  }
  // What the hook as it is now would do with this event; the actions that already succeeded would act again.
  function replayHtml(p) {
    if (!p || !p.ok) return '<div style="color:var(--warn-ink)">' + esc((p && p.error) || tw("wh.save_err")) + "</div>";
    if (p.decision !== "run") return '<div style="color:var(--warn-ink)">' + esc(tw("wh.replay_no_run", { why: p.reason || p.decision })) + "</div>";
    // Another event holds this order's business key: it ran there, so this one is not offered to run again.
    if (p.duplicate_of) return '<div style="color:var(--warn-ink)">' + esc(tw("wh.replay_dup", { id: p.duplicate_of })) + "</div>";
    return planHtml(p.deliveries)
      + ((p.may_repeat || []).length ? '<div class="wh-need" style="color:var(--warn-ink)">'
        + esc(tw("wh.replay_repeat", { names: p.may_repeat.join(", ") })) + "</div>" : "")
      + '<div class="wf-actions"><button class="s-btn whReplayGo" data-ev="' + esc(p.id || "") + '">' + esc(tw("wh.replay_go"))
      + "</button></div>";
  }
  // One line per action: will it run, against what, waiting for approval or another action, and why not.
  function planHtml(list) {
    if (!list || !list.length) return '<div class="dim" style="color:var(--text3)">' + esc(tw("wh.plan_none")) + "</div>";
    return '<div class="wh-plan">' + list.map(function (d) {
      return '<div class="wh-plan-row" style="color:' + (d.runs ? "var(--text2)" : "var(--text3)") + '">'
        + ic(d.runs ? "check" : "x") + " <b>" + esc(d.action) + "</b> (" + esc(d.kind) + ")"
        + (d.target ? " → <code>" + esc(d.target) + "</code>" : "")
        + (d.needs_approval ? " · " + esc(tw("wh.plan_approval")) : "")
        + ((d.depends_on || []).length ? " · " + esc(tw("wh.plan_after", { names: d.depends_on.map(function (x) {
          return typeof x === "string" ? x : x.action || x.id; }).join(", ") })) : "")
        + (d.already_succeeded ? " · " + esc(tw("wh.plan_done_before")) : "")
        + (!d.runs && d.why_not ? " · " + esc(d.why_not) : "")
        + (d.args ? '<div><code style="word-break:break-all">' + esc(JSON.stringify(d.args)) + "</code></div>" : "")
        + "</div>";
    }).join("") + "</div>";
  }

  // Spec §12 health. "Received" (202) is said apart from "processed": a 202 is not a finished order.
  function healthHtml(hh) {
    if (!hh) return "";
    var mb = function (b) { return ((b || 0) / 1048576).toFixed(1) + " MB"; };
    var dur = function (s) { return s == null ? "-" : (s < 120 ? Math.round(s) + " s" : Math.round(s / 60) + " min"); };
    var row = function (k, v, bad) {
      return '<div class="wh-hl"' + (bad ? ' style="color:var(--warn-ink)"' : "") + ">" + esc(tw(k)) + ": <b>" + esc(v) + "</b></div>";
    };
    var errs = (hh.errors_by_target || []).map(function (e) { return e.action_id + " (" + e.kind + ") " + e.n; }).join(", ");
    return '<div class="wh-health" style="font-size:16px">'
      + '<div class="dim" style="color:var(--text3)">' + esc(tw("wh.h_note")) + "</div>"
      + row("wh.h_received", hh.received || 0) + row("wh.h_matched", hh.matched || 0) + row("wh.h_ignored", hh.ignored || 0)
      + row("wh.h_quarantined", hh.quarantined || 0, hh.quarantined)
      + row("wh.h_duplicates", (hh.duplicate_deliveries || 0) + " / " + (hh.duplicate_business || 0))
      + row("wh.h_backlog", hh.backlog || 0) + row("wh.h_oldest", dur(hh.oldest_open_age_s), hh.oldest_open_age_s > 3600)
      + row("wh.h_ack", (hh.ack_p50_ms == null ? "-" : hh.ack_p50_ms + " / " + hh.ack_p95_ms + " ms"))
      + row("wh.h_processing", dur(hh.processing_p50_s) + " / " + dur(hh.processing_p95_s))
      + row("wh.h_retry", hh.retry_wait || 0) + row("wh.h_dead", hh.dead || 0, hh.dead)
      + row("wh.h_unknown", hh.unknown || 0, hh.unknown) + row("wh.h_blocked", hh.blocked || 0, hh.blocked)
      + row("wh.h_ai", hh.ai_calls || 0) + (errs ? row("wh.h_errors", errs, true) : "")
      + row("wh.h_sql_busy", hh.sql_busy || 0, hh.sql_busy)
      + row("wh.h_db", mb(hh.db_bytes) + " + WAL " + mb(hh.wal_bytes) + " / " + mb(hh.cap), hh.level && hh.level !== "ok")
      + "</div>";
  }

  // M2: what the hook's rules decided for a sample body (POST /webhooks/simulate). Nothing was stored or run.
  var SIM_KEY = { run: "wh.sim_run", ran: "wh.sim_ran", filtered: "wh.sim_filtered", invalid: "wh.sim_invalid",
    duplicate: "wh.sim_duplicate" };
  function stepLine(ok, text) {
    return '<div class="wh-sim-step ' + (ok ? "pass" : "fail") + '" style="color:' + (ok ? "var(--text2)" : "var(--warn-ink)") + '">'
      + ic(ok ? "check" : "x") + " " + esc(text) + "</div>";
  }
  function plain(v) { return v === null || v === undefined ? "∅" : (typeof v === "object" ? JSON.stringify(v) : String(v)); }
  function simHtml(sim) {
    if (!sim || !sim.ok) return '<div style="color:var(--warn-ink)">' + esc((sim && sim.error) || tw("wh.save_err")) + "</div>";
    var t = sim.trace || {};
    var out = '<div class="wh-sim-head"><b>' + esc(tw(SIM_KEY[sim.decision] || "wh.sim_run")) + "</b>"
      + (sim.reason ? " · " + esc(sim.reason) : "") + "</div>";
    (t.schema || []).forEach(function (s) { out += stepLine(s.pass, tw("wh.sim_schema") + " " + s.path + ": " + s.why); });
    (t.filter || []).forEach(function (s) {
      // A stored trace keeps no values (spec §7): the value seen is shown only by a simulation.
      out += stepLine(s.pass, tw("wh.sim_filter") + " " + s.path + " " + s.op + ("value" in s ? " " + plain(s.value) : "")
        + ("actual" in s ? " (" + plain(s.actual) + ")" : ""));
    });
    var f = sim.fields || {};
    var names = Object.keys(f);
    if (names.length) {
      out += '<div class="wh-sim-fields" style="margin-top:4px"><b>' + esc(tw("wh.sim_fields")) + "</b>"
        + names.map(function (k) { return "<div><code>" + esc(k) + "</code>: " + esc(plain(f[k])) + "</div>"; }).join("") + "</div>";
    }
    if (sim.business_key) out += "<div>" + esc(tw("wh.sim_key")) + " <code>" + esc(sim.business_key.scope + "/" + sim.business_key.key) + "</code></div>";
    if (sim.prompt) {
      out += '<details style="margin-top:4px"><summary style="cursor:pointer">' + esc(tw("wh.sim_prompt")) + "</summary>"
        + '<pre style="white-space:pre-wrap;word-break:break-word;max-height:320px;overflow:auto">' + esc(sim.prompt) + "</pre></details>";
    }
    return out;
  }
  // M5: how the owner is told, limits, AI budget, retention.
  var NOTIFY = ["all", "errors_only", "daily_digest", "none"];
  var NOTIFY_KEY = { all: "wh.notify_all", errors_only: "wh.notify_errors_only", daily_digest: "wh.notify_daily_digest",
    none: "wh.notify_none" };
  function settingsHtml(h) {
    var lim = h.limits || {};
    var num = function (cls, label, v, min, max) {
      return '<label style="display:inline-block;margin:4px 12px 0 0">' + esc(tw(label)) + ' <input class="' + cls
        + '" type="number" inputmode="numeric" min="' + min + '" max="' + max + '" value="' + esc(v == null ? "" : v)
        + '" style="width:96px;font-size:16px"></label>';
    };
    return '<div class="wh-settings" style="margin-top:6px">'
      + '<label style="display:block">' + esc(tw("wh.notify_label")) + ' <select class="whNotify loop-sel" style="font-size:16px">'
      + NOTIFY.map(function (m) { return '<option value="' + m + '"' + ((h.notify || "all") === m ? " selected" : "") + ">"
        + esc(tw(NOTIFY_KEY[m])) + "</option>"; }).join("") + "</select></label>"
      + num("whPerMin", "wh.lim_minute", lim.per_minute, 1, 6000)
      + num("whPerHour", "wh.lim_hour", lim.per_hour, 0, 100000) + num("whPerDay", "wh.lim_day", lim.per_day, 0, 1000000)
      + num("whBacklog", "wh.lim_backlog", lim.backlog, 1, 100000) + num("whAiHour", "wh.ai_hour", h.ai_per_hour, 0, 1000)
      + num("whAiDay", "wh.ai_day", h.ai_per_day, 0, 5000)
      + num("whKeep", "wh.keep_days", h.retention_days, 1, 365)
      + '<label style="display:block;margin-top:6px"><input type="checkbox" class="whAiTriage"' + (h.ai_triage ? " checked" : "")
      + "> " + esc(tw("wh.ai_triage")) + "</label>"
      + "</div>";
  }
  function readSettings(host) {
    var n = function (sel) { var v = host.querySelector(sel).value; return v === "" ? null : parseInt(v, 10); };
    var lim = {};
    [["per_minute", ".whPerMin"], ["per_hour", ".whPerHour"], ["per_day", ".whPerDay"], ["backlog", ".whBacklog"]].forEach(function (x) {
      var v = n(x[1]); if (v !== null && !isNaN(v)) lim[x[0]] = v;
    });
    var tri = host.querySelector(".whAiTriage");
    return { notify: host.querySelector(".whNotify").value, limits: lim, ai_per_hour: n(".whAiHour"), ai_per_day: n(".whAiDay"),
      retention_days: n(".whKeep"), ai_triage: tri ? tri.checked : undefined };
  }

  function rulesPanelHtml(h) {
    var rules = h.rules && Object.keys(h.rules).length ? JSON.stringify(h.rules, null, 2) : "";
    return '<div class="wh-rules" style="margin-top:8px;padding:10px;border:1px solid var(--hairline);border-radius:8px">'
      + settingsHtml(h)
      + '<div class="dim" style="color:var(--text3)">' + esc(tw("wh.rules_hint")) + "</div>"
      + '<label style="display:block;margin-top:6px">' + esc(tw("wh.rules_label")) + "</label>"
      + '<textarea class="whRulesTxt" spellcheck="false" style="width:100%;min-height:140px;font-family:monospace">' + esc(rules) + "</textarea>"
      + '<label style="display:block;margin-top:6px">' + esc(tw("wh.sample_label")) + "</label>"
      + '<textarea class="whSample" spellcheck="false" style="width:100%;min-height:90px;font-family:monospace"></textarea>'
      + '<div class="wf-actions" style="margin-top:6px"><button class="s-btn-ghost whSim">' + esc(tw("wh.simulate")) + "</button>"
      + '<button class="s-btn whRulesSave">' + esc(tw("wh.rules_save")) + "</button></div>"
      + '<label style="display:block;margin-top:6px">' + esc(tw("wh.actions_label")) + "</label>"
      + '<div class="dim" style="color:var(--text3)">' + esc(tw("wh.actions_hint")) + "</div>"
      + '<textarea class="whActsTxt" spellcheck="false" style="width:100%;min-height:110px;font-family:monospace">'
      + esc(h.actions && h.actions.length ? JSON.stringify(h.actions, null, 2) : "") + "</textarea>"
      + '<label style="display:block;margin-top:6px">' + esc(tw("wh.verify_label")) + "</label>"
      + '<div class="dim" style="color:var(--text3)">' + esc(tw("wh.verify_hint"))
      + (h.adapter_status === "unverified" ? " " + esc(tw("wh.adapter_unverified")) : "") + "</div>"
      + '<textarea class="whVerifyTxt" spellcheck="false" style="width:100%;min-height:60px;font-family:monospace">'
      + esc(h.verify && h.verify.provider && h.verify.provider !== "none" ? JSON.stringify(h.verify, null, 2) : "") + "</textarea>"
      + '<div class="whSimOut" style="margin-top:6px"></div></div>';
  }
  // The rules box as an object: "" means no rules; text that is not JSON is reported, not sent.
  function readRules(text) {
    var t = String(text || "").trim();
    if (!t) return { ok: true, rules: {} };
    try { return { ok: true, rules: JSON.parse(t) }; } catch (e) { return { ok: false }; }
  }

  // The actions box: "" = none (the webhook's own task or workflow runs). Masked header values ("••••") are sent back
  // as they are; the server keeps the stored key for those.
  function readActions(text) {
    var t = String(text || "").trim();
    if (!t) return { ok: true, actions: [] };
    try { var a = JSON.parse(t); return Array.isArray(a) ? { ok: true, actions: a } : { ok: false }; } catch (e) { return { ok: false }; }
  }

  function testText(r) {
    if (r && r.accepted && r.state === "received") return tw("wh.test_received");
    if (r && r.ok && r.ignored) return tw(STATUS_KEY[r.ignored] || "wh.st_filtered");
    if (r && r.ok && r.duplicate && r.reason === "business_key") return tw("wh.st_duplicate");
    if (r && r.ok) return tw("wh.test_sent");
    if (r && r.error === "invalid") return tw("wh.st_invalid") + (r.reason ? ": " + r.reason : "");
    return (r && r.error) || tw("wh.save_err");
  }

  // Error codes of the event actions, in words.
  var ERR_KEY = { not_found: "wh.err_not_found", not_retryable: "wh.err_not_retryable", not_unknown: "wh.err_not_unknown",
    key_taken: "wh.err_key_taken", not_waiting: "wh.err_not_waiting", body_pruned: "wh.err_body_pruned" };
  function errText(r) {
    if (r && r._status === 409 && !ERR_KEY[r.error] && r.error) return String(r.error);
    return tw(ERR_KEY[r && r.error] || "wh.save_err");
  }

  function fmtTime(ts) {
    if (!ts) return "";
    var d = new Date(ts * 1000);
    var p = function (n) { return String(n).padStart(2, "0"); };
    return p(d.getHours()) + ":" + p(d.getMinutes()) + " " + p(d.getDate()) + "/" + p(d.getMonth() + 1);
  }

  function brainName(brains, path) {
    var b = (brains || []).filter(function (x) { return x.path === path; })[0];
    return b ? (b.label || b.name) : (String(path || "").split(/[\\/]/).pop() || path);
  }

  function targetLine(h) {
    // A hook with only outside actions has no task or workflow of its own: name its actions instead.
    var outside = (h.actions || []).filter(function (a) { return a.kind !== "ai"; });
    if (outside.length && h.target !== "workflow" && !String(h.text || "").trim()) {
      return tw("wh.target_actions_line", { names: outside.map(function (a) { return a.id + " (" + a.kind + ")"; }).join(", ") });
    }
    return h.target === "workflow"
      ? tw("wh.target_wf_line", { name: h.workflow })
      : tw("wh.target_task_line", { text: String(h.text || "").slice(0, 80) });
  }

  function cardHtml(h, brains) {
    var last = h.last_at ? tw("wh.last_run", { time: fmtTime(h.last_at), status: tw(STATUS_KEY[h.last_status] || "wh.st_done") })
      : tw("wh.never_run");
    var rows = (h.history || []).slice(0, 5);
    // The server counts unknown events over the WHOLE log, not just the newest rows drawn here.
    var needYou = (h.unknown || 0) > 0 || (h.blocked || 0) > 0
      || (h.history || []).some(function (r) { return r.status === "unknown" || r.status === "blocked"; });
    var hist = rows.map(eventRowHtml).join("");
    var hasRules = h.rules && Object.keys(h.rules).length;
    var tab = needYou ? "ev" : "cfg";
    var pane = function (name, html) {
      return '<div class="whPane" data-pane="' + name + '"' + (tab === name ? "" : ' style="display:none"') + ">" + html + "</div>";
    };
    var openBreakers = (h.breakers || []).filter(function (b) { return b.open_until > Date.now() / 1000; });
    var cfg = '<div class="dim" style="font-size:16px;color:var(--text3)">' + esc(targetLine(h)) + " · "
      + esc(tw(LEVEL_KEY[h.level] || "wh.level_full")) + " · " + esc(brainName(brains, h.brain)) + "</div>"
      + '<div style="font-size:16px;margin-top:4px;word-break:break-all"><code>' + esc(h.url) + "</code></div>"
      + '<div class="dim" style="font-size:16px;color:var(--text3);margin-top:2px">'
      + esc(h.verify && h.verify.provider && h.verify.provider !== "none"
        ? tw("wh.key_where_signed", { provider: h.verify.provider })
        : tw(h.query_token ? "wh.key_where_legacy" : "wh.key_where", { header: h.token_header || "X-Javis-Token" })) + "</div>"
      + (h.ai_triage ? '<div class="dim" style="font-size:16px;color:var(--text3)">' + esc(tw("wh.ai_triage_on")) + "</div>" : "")
      + '<div class="wf-actions" style="margin-top:8px">'
      + '<button class="s-btn-ghost whCopy">' + esc(tw("wh.copy_url")) + "</button>"
      + '<button class="s-btn-ghost whTest">' + esc(tw("wh.test")) + "</button>"
      + '<button class="s-btn-ghost whRules' + (hasRules ? " has-rules" : "") + '">'
      + esc(tw("wh.rules")) + (hasRules ? " " + ic("check") : "") + "</button>"
      + '<button class="s-btn-ghost whRotate">' + esc(tw("wh.rotate")) + "</button>"
      + '<button class="s-btn-ghost whDel" style="color:var(--red)">' + esc(tw("common.delete")) + "</button>"
      + "</div>"
      // Two switches, never one (spec §12): receiving, and processing.
      + '<div class="wh-switches" style="margin-top:8px;font-size:16px">'
      + '<div><button class="s-btn-ghost whToggle">' + esc(tw(h.enabled ? "wh.turn_off" : "wh.turn_on")) + "</button> "
      + '<span class="dim" style="color:var(--text3)">' + esc(tw(h.enabled ? "wh.receiving_on" : "wh.receiving_off")) + "</span></div>"
      + '<div><button class="s-btn-ghost whPause">' + esc(tw(h.paused ? "wh.resume" : "wh.pause")) + "</button> "
      + '<span class="dim" style="color:var(--text3)">' + esc(tw(h.paused ? "wh.paused_on" : "wh.paused_off")) + "</span></div>"
      + "</div>"
      + '<div class="whTestHost"></div><div class="whRulesHost"></div>';
    var evs = (needYou ? '<div class="wh-need" style="font-size:16px;color:var(--warn-ink);margin-top:4px">' + esc(tw("wh.unknown_hint")) + "</div>" : "")
      + '<details class="whLog" style="margin-top:4px"' + (needYou ? " open" : "") + '><summary style="font-size:16px;cursor:pointer">'
      + esc(tw("wh.history")) + '</summary>'
      + '<div class="wh-filters" style="margin:6px 0;display:flex;flex-wrap:wrap;gap:6px;align-items:center">'
      + '<select class="whFilter loop-sel" style="font-size:16px">'
      + [["", "wh.f_all"], ["needs_you", "wh.f_needs_you"], ["failed,dead", "wh.f_failed"], ["ran", "wh.f_ran"],
        ["filtered,invalid,duplicate", "wh.f_filtered"]]
        .map(function (x) { return '<option value="' + x[0] + '">' + esc(tw(x[1])) + "</option>"; }).join("") + "</select>"
      + '<input class="whQ" type="search" placeholder="' + esc(tw("wh.f_q")) + '" style="font-size:16px;min-width:0;flex:1 1 140px">'
      + '<label style="font-size:16px">' + esc(tw("wh.f_since")) + ' <input class="whSince" type="date" style="font-size:16px"></label>'
      + '<label style="font-size:16px">' + esc(tw("wh.f_until")) + ' <input class="whUntil" type="date" style="font-size:16px"></label>'
      + "</div>"
      + '<div class="whLogRows">' + (hist || '<div class="dim" style="color:var(--text3)">' + esc(tw("wh.no_events")) + "</div>") + "</div>"
      + '<button class="s-btn-ghost whMore" style="font-size:16px">' + esc(tw("wh.more")) + "</button>"
      + ' <a class="s-btn-ghost" href="/webhooks/events/export?hook=' + encodeURIComponent(h.id) + '&format=csv" download>'
      + esc(tw("wh.export")) + "</a>"
      + ' <button class="s-btn-ghost whCloseFailed">' + esc(tw("wh.close_failed")) + "</button>"
      + ' <button class="s-btn-ghost whRetryBlocked">' + esc(tw("wh.retry_blocked")) + "</button></details>";
    return '<b>' + ic("webhook") + " " + esc(h.name) + "</b>"
      + (h.enabled ? "" : ' <span class="dim" style="font-size:16px;color:var(--text3)">' + esc(tw("wh.off")) + "</span>")
      + (h.paused ? ' <span class="dim" style="font-size:16px;color:var(--warn-ink)">' + esc(tw("wh.paused_badge")) + "</span>" : "")
      + '<div class="dim" style="font-size:16px;color:var(--text3);margin-top:2px">' + esc(last)
      + (h.count ? " · " + esc(tw("wh.count", { n: h.count })) : "") + "</div>"
      + (openBreakers.length ? '<div class="wh-need" style="color:var(--warn-ink);margin-top:4px">' + esc(tw("wh.breaker_open", {
        names: openBreakers.map(function (b) { return b.action; }).join(", ") })) + "</div>" : "")
      + '<div class="si-row wh-tabs" style="margin-top:8px">'
      + [["cfg", "wh.tab_cfg"], ["ev", "wh.tab_events"], ["health", "wh.tab_health"]].map(function (x) {
        return '<button class="si-chip whTab' + (x[0] === tab ? " sel" : "") + '" data-tab="' + x[0] + '">' + esc(tw(x[1])) + "</button>";
      }).join("") + "</div>"
      + pane("cfg", cfg) + pane("ev", evs) + pane("health", '<div class="whHealthHost"></div>');
  }

  // The real test send (spec §12): the owner's own payload, the list of what each action would do, then the send.
  function testPanelHtml() {
    return '<div class="wh-test" style="margin-top:8px;padding:10px;border:1px solid var(--hairline);border-radius:8px">'
      + '<div class="dim" style="color:var(--text3);font-size:16px">' + esc(tw("wh.test_hint")) + "</div>"
      + '<textarea class="whTestBody" spellcheck="false" style="width:100%;min-height:90px;font-family:monospace;font-size:16px">'
      + esc('{"test": true}') + "</textarea>"
      + '<div class="wf-actions" style="margin-top:6px"><button class="s-btn-ghost whTestPreview">' + esc(tw("wh.test_preview"))
      + '</button><button class="s-btn whTestGo" disabled>' + esc(tw("wh.test_go")) + "</button></div>"
      + '<div class="whTestOut" style="margin-top:6px"></div></div>';
  }

  function secretHtml(url, token) {
    var curl = "curl -X POST '" + url + "' -H 'Authorization: Bearer " + token
      + "' -H 'Content-Type: application/json' -d '{\"name\":\"Lan\",\"phone\":\"0901\"}'";
    return '<div style="padding:10px 12px;border:1px solid var(--green);border-radius:8px;margin-bottom:10px;font-size:16px;line-height:1.5">'
      + "<b>" + esc(tw("wh.secret_head")) + "</b><br>" + esc(tw("wh.secret_body"))
      + '<div style="margin-top:6px;word-break:break-all"><code>' + esc(token) + "</code></div>"
      + '<div class="dim" style="margin-top:6px;color:var(--text3)">' + esc(tw("wh.secret_curl")) + "</div>"
      + '<div style="word-break:break-all"><code>' + esc(curl) + "</code></div>"
      + '<button class="s-btn-ghost whCopyCurl" style="margin-top:6px">' + esc(tw("wh.copy_curl")) + "</button></div>";
  }

  function formHtml(brains, current) {
    var opts = (brains || []).map(function (b) {
      return '<option value="' + esc(b.path) + '"' + (b.path === current ? " selected" : "") + ">" + esc(b.label || b.name) + "</option>";
    }).join("");
    return '<div id="whForm" style="display:none;margin-bottom:12px;padding:14px;border:1px solid var(--hairline);border-radius:10px;background:var(--surface-1)">'
      + '<div class="si-grid">'
      + '<div class="si-field"><label>' + esc(tw("wh.name")) + '</label><input id="whName" placeholder="' + esc(tw("wh.name_ph")) + '"></div>'
      + '<div class="si-field"><label>' + esc(tw("wh.brain")) + '</label><select id="whBrain" class="loop-sel">' + opts + "</select></div>"
      + '<div class="si-field"><label>' + esc(tw("wh.target")) + '</label><div class="si-row" id="whTarget">'
      + '<button class="si-chip sel" data-t="workflow">' + esc(tw("wh.target_wf")) + "</button>"
      + '<button class="si-chip" data-t="task">' + esc(tw("wh.target_task")) + "</button></div></div>"
      + '<div class="si-field" id="whWfWrap"><label>' + esc(tw("wh.workflow")) + '</label><select id="whWorkflow" class="loop-sel"></select></div>'
      + '<div class="si-field"><label id="whTextLabel">' + esc(tw("wh.text_wf")) + '</label><textarea id="whText" placeholder="' + esc(tw("wh.text_ph")) + '"></textarea></div>'
      + '<div class="si-field"><label>' + esc(tw("wh.level")) + '</label><div class="si-row" id="whLevel">'
      + '<button class="si-chip" data-l="suggest">' + esc(tw("wh.level_suggest")) + "</button>"
      + '<button class="si-chip" data-l="auto">' + esc(tw("wh.level_auto")) + "</button>"
      + '<button class="si-chip sel" data-l="full">' + esc(tw("wh.level_full")) + "</button></div></div>"
      + '<div class="si-actions"><button class="s-btn" id="whSave">' + esc(tw("common.save")) + "</button>"
      + '<button class="s-btn-ghost" id="whCancel">' + esc(tw("common.cancel")) + "</button>"
      + '<span class="dim" id="whMsg" style="font-size:16px;color:var(--warn-ink)"></span></div>'
      + "</div></div>";
  }

  async function api(url, body) {
    try {
      var r = await fetch(url, body === undefined ? undefined : {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      var j = await r.json();
      // The status travels with the answer: a 409 on save means someone saved first (spec: revision check).
      if (j && typeof j === "object") j._status = r.status;
      return j;
    } catch (e) { return { ok: false, error: e.message }; }
  }

  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    var ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) { /* ignore */ }
    ta.remove();
    return Promise.resolve();
  }

  function mount(box, opts) {
    if (!box) return;
    var brains = function () { return (opts && opts.brains && opts.brains()) || []; };
    var current = function () { return (opts && opts.current && opts.current()) || ""; };
    var target = "workflow", level = "full";
    // Shared button and chip styles are smaller than 16px; inside this section nothing reads under 16px (owner rule).
    box.classList.add("wh-root");
    box.innerHTML = '<style>.wh-root :is(button,input,select,textarea,code,pre,label,span,div,a,summary,b,option)'
      + '{font-size:max(16px,1em)}</style>'
      + '<div class="lp-group"><div style="display:flex;align-items:center;gap:8px;margin:22px 0 8px;font-size:16px;color:var(--text);font-weight:600;border-bottom:1px solid var(--hairline);padding-bottom:6px">'
      + "<span>" + ic("webhook") + " " + esc(tw("wh.head")) + infoBtn() + "</span>"
      + '<button class="s-btn-ghost" id="whNew" style="margin-left:auto;font-size:16px">+ ' + esc(tw("wh.add")) + "</button></div>"
      + infoBody(esc(tw("wh.intro")))
      + '<div id="whSecret"></div><div id="whFormHost"></div><div id="whList"></div></div>';
    var q = function (s) { return box.querySelector(s); };

    async function loadWorkflows() {
      var sel = q("#whWorkflow");
      if (!sel) return;
      var d = await api("/workflows?brain=" + encodeURIComponent(q("#whBrain").value || current()));
      var wfs = (d && d.workflows) || [];
      sel.innerHTML = wfs.length
        ? wfs.map(function (w) { return '<option value="' + esc(w.slug) + '">' + esc(w.name || w.slug) + "</option>"; }).join("")
        : '<option value="">' + esc(tw("wh.no_workflow")) + "</option>";
    }
    function syncForm() {
      box.querySelectorAll("#whTarget .si-chip").forEach(function (c) { c.classList.toggle("sel", c.dataset.t === target); });
      box.querySelectorAll("#whLevel .si-chip").forEach(function (c) { c.classList.toggle("sel", c.dataset.l === level); });
      q("#whWfWrap").style.display = target === "workflow" ? "" : "none";
      q("#whTextLabel").textContent = tw(target === "workflow" ? "wh.text_wf" : "wh.text_task");
    }
    function showSecret(hook, token) {
      q("#whSecret").innerHTML = secretHtml(hook.url, token);
      var b = q(".whCopyCurl");
      if (b) b.onclick = function () {
        var code = q("#whSecret").querySelectorAll("code")[1];
        copy(code ? code.textContent : "").then(function () { b.textContent = tw("wh.copied"); });
      };
    }
    function openForm() {
      q("#whFormHost").innerHTML = formHtml(brains(), current());
      target = "workflow"; level = "full";
      box.querySelectorAll("#whTarget .si-chip").forEach(function (c) { c.onclick = function () { target = c.dataset.t; syncForm(); }; });
      box.querySelectorAll("#whLevel .si-chip").forEach(function (c) { c.onclick = function () { level = c.dataset.l; syncForm(); }; });
      q("#whBrain").onchange = loadWorkflows;
      q("#whCancel").onclick = function () { q("#whForm").style.display = "none"; };
      q("#whSave").onclick = async function () {
        var body = { name: q("#whName").value.trim(), brain: q("#whBrain").value, target: target, level: level,
          workflow: target === "workflow" ? q("#whWorkflow").value : "", text: q("#whText").value.trim() };
        if (!body.name) { q("#whMsg").textContent = tw("wh.need_name"); return; }
        var r = await api("/webhooks", body);
        if (!r.ok) { q("#whMsg").textContent = r.error || tw("wh.save_err"); return; }
        q("#whForm").style.display = "none";
        showSecret(r.hook, r.token);
        load();
      };
      syncForm();
      loadWorkflows();
      q("#whForm").style.display = "block";
      q("#whName").focus();
    }
    q("#whNew").onclick = openForm;

    // Retry / Mark done on an event, and "older events" paging through /webhooks/events (keyset cursor).
    function wireEvents(div, h) {
      var cursor = "", rowsBox = div.querySelector(".whLogRows"), more = div.querySelector(".whMore");
      var filter = div.querySelector(".whFilter"), status = "";
      var qBox = div.querySelector(".whQ"), sinceBox = div.querySelector(".whSince"), untilBox = div.querySelector(".whUntil");
      // A date box as epoch seconds, local midnight; "until" includes its whole day.
      function day(el, end) {
        if (!el || !el.value) return 0;
        var d = new Date(el.value + "T00:00:00");
        return isNaN(d.getTime()) ? 0 : d.getTime() / 1000 + (end ? 86400 : 0);
      }
      function filters() {
        var q = qBox ? qBox.value.trim() : "", since = day(sinceBox, false), until = day(untilBox, true);
        return (q ? "&q=" + encodeURIComponent(q) : "") + (since ? "&since=" + since : "") + (until ? "&until=" + until : "");
      }
      function bindRows(scope) {
        scope.querySelectorAll(".whEvRetry").forEach(function (b) {
          b.onclick = async function () {
            if (!confirm(tw("wh.retry_confirm"))) return;
            var r = await api("/webhooks/events/retry", { id: b.dataset.ev });
            b.textContent = r.ok ? tw("wh.retry_sent") : errText(r);
            setTimeout(load, 3000);
          };
        });
        scope.querySelectorAll(".whEvInfo").forEach(function (b) {
          b.onclick = async function () {
            var box = b.closest(".wh-ev").querySelector(".whEvDetail");
            if (box.innerHTML) { box.innerHTML = ""; return; }
            var d = await api("/webhooks/events/" + encodeURIComponent(b.dataset.ev));
            box.innerHTML = d && d.ok ? detailHtml(d.event) : esc(errText(d));
            wireDetail(box);
            box.querySelectorAll(".whApprove").forEach(function (x) {
              x.onclick = async function () {
                var r = await api("/webhooks/events/approve", { id: x.dataset.ev, action: x.dataset.act, decision: x.dataset.d });
                x.textContent = r.ok ? tw(x.dataset.d === "approve" ? "wh.approved" : "wh.rejected") : errText(r);
                if (r.ok) setTimeout(load, 2500);
              };
            });
          };
        });
        scope.querySelectorAll(".whEvSettle").forEach(function (b) {
          b.onclick = async function () {
            if (!confirm(tw("wh.ev_settle_confirm"))) return;
            var r = await api("/webhooks/events/resolve", { id: b.dataset.ev, outcome: "done", note: "settled by the owner" });
            if (r.ok) load(); else b.textContent = errText(r);
          };
        });
        scope.querySelectorAll(".whEvDel").forEach(function (b) {
          b.onclick = async function () {
            if (!confirm(tw("wh.ev_delete_confirm"))) return;
            var r = await api("/webhooks/events/delete", { id: b.dataset.ev });
            if (r.ok) load(); else b.textContent = errText(r);
          };
        });
        scope.querySelectorAll(".whEvDone").forEach(function (b) {
          b.onclick = async function () {
            var r = await api("/webhooks/events/resolve", { id: b.dataset.ev, outcome: "done" });
            if (r.ok) load(); else b.textContent = errText(r);
          };
        });
      }
      bindRows(div);
      var rb = div.querySelector(".whRetryBlocked");
      if (rb) rb.onclick = async function () {
        var r = await api("/webhooks/events/retry_blocked", { hook: h.id });
        rb.textContent = r.ok ? tw("wh.retried_n", { n: r.queued }) : errText(r);
        if (r.ok) setTimeout(load, 2500);
      };
      var closeAll = div.querySelector(".whCloseFailed");
      if (closeAll) closeAll.onclick = async function () {
        if (!confirm(tw("wh.close_failed_confirm"))) return;
        var r = await api("/webhooks/events/close_failed", { hook: h.id });
        closeAll.textContent = r.ok ? tw("wh.closed_n", { n: r.closed }) : errText(r);
        if (r.ok) setTimeout(load, 1500);
      };
      if (!more || !rowsBox) return;
      more.onclick = async function () {
        var url = "/webhooks/events?hook=" + encodeURIComponent(h.id) + "&limit=20" + (status ? "&status=" + encodeURIComponent(status) : "")
          + filters() + (cursor ? "&before=" + encodeURIComponent(cursor) : "");
        var d = await api(url);
        if (!d || !d.ok) { more.textContent = (d && d.error) || tw("wh.save_err"); return; }
        if (!cursor) rowsBox.innerHTML = "";
        var tmp = document.createElement("div");
        tmp.innerHTML = (d.items || []).map(eventRowHtml).join("");
        bindRows(tmp);
        while (tmp.firstChild) rowsBox.appendChild(tmp.firstChild);
        cursor = d.next || "";
        more.style.display = cursor ? "" : "none";
      };
      var refilter = function () { status = filter ? filter.value : ""; cursor = ""; more.style.display = ""; more.onclick(); };
      if (filter) filter.onchange = refilter;
      [qBox, sinceBox, untilBox].forEach(function (el) { if (el) el.onchange = refilter; });
    }

    // Raw payload (asks first; the server records the view) and "process again with the current setup".
    function wireDetail(box) {
      box.querySelectorAll(".whRaw").forEach(function (b) {
        b.onclick = async function () {
          if (!confirm(tw("wh.raw_confirm"))) return;
          var d = await api("/webhooks/events/" + encodeURIComponent(b.dataset.ev) + "?raw=1");
          var pre = b.closest(".wh-payload").querySelector(".whPayload");
          if (d && d.ok) { pre.textContent = d.event.payload || ""; b.remove(); } else b.textContent = errText(d);
        };
      });
      box.querySelectorAll(".whReplay").forEach(function (b) {
        b.onclick = async function () {
          var out = box.querySelector(".whReplayOut");
          var p = await api("/webhooks/events/replay", { id: b.dataset.ev });
          if (p && p.ok) p.id = b.dataset.ev;
          out.innerHTML = replayHtml(p);
          var go = out.querySelector(".whReplayGo");
          if (go) go.onclick = async function () {
            var r = await api("/webhooks/events/replay", { id: go.dataset.ev, confirm: true, revision: p.revision });
            go.textContent = r && r.ok ? tw("wh.replay_sent") : errText(r);
            if (r && r.ok) setTimeout(load, 2500);
          };
        };
      });
    }

    async function load() {
      var d = await api("/webhooks");
      var list = q("#whList");
      if (!list) return;
      var hooks = (d && d.hooks) || [];
      if (!hooks.length) { list.innerHTML = '<div class="empty">' + esc(tw("wh.empty")) + "</div>"; return; }
      list.innerHTML = "";
      hooks.forEach(function (h) {
        var div = document.createElement("div");
        div.className = "wf-card";
        div.innerHTML = cardHtml(h, brains());
        div.querySelector(".whCopy").onclick = function (ev) {
          copy(h.url).then(function () { ev.target.textContent = tw("wh.copied"); });
        };
        div.querySelectorAll(".whTab").forEach(function (t) {
          t.onclick = async function () {
            div.querySelectorAll(".whTab").forEach(function (x) { x.classList.toggle("sel", x === t); });
            div.querySelectorAll(".whPane").forEach(function (p) { p.style.display = p.dataset.pane === t.dataset.tab ? "" : "none"; });
            if (t.dataset.tab === "health") {
              var hd = await api("/webhooks/health?hook=" + encodeURIComponent(h.id));
              div.querySelector(".whHealthHost").innerHTML = hd && hd.ok ? healthHtml(hd.health) : esc(errText(hd));
            }
          };
        });
        div.querySelector(".whTest").onclick = function () {
          var host = div.querySelector(".whTestHost");
          if (host.innerHTML) { host.innerHTML = ""; return; }
          host.innerHTML = testPanelHtml();
          var out = host.querySelector(".whTestOut"), go = host.querySelector(".whTestGo");
          var body = function () { return host.querySelector(".whTestBody").value; };
          host.querySelector(".whTestBody").oninput = function () { go.disabled = true; };
          host.querySelector(".whTestPreview").onclick = async function () {
            // Nothing is sent here: the server only says what each action would do with this payload.
            var p = await api("/webhooks/test", { id: h.id, payload: body() });
            out.innerHTML = p && p.ok ? simHtml(p) + planHtml(p.deliveries) : simHtml(p);
            go.disabled = !(p && p.ok);
          };
          go.onclick = async function () {
            if (!confirm(tw("wh.test_confirm"))) return;
            var r = await api("/webhooks/test", { id: h.id, payload: body(), confirm: true });
            // With rules the sample event is often stopped by them: say so instead of "sent".
            out.textContent = testText(r);
            go.disabled = true;
            setTimeout(load, 4000);
          };
        };
        div.querySelector(".whToggle").onclick = async function () {
          if (h.enabled && !confirm(tw("wh.turn_off_confirm"))) return;
          await api("/webhooks/update", { id: h.id, enabled: !h.enabled });
          load();
        };
        div.querySelector(".whPause").onclick = async function () {
          await api("/webhooks/pause", { id: h.id, paused: !h.paused });
          load();
        };
        div.querySelector(".whRotate").onclick = async function () {
          if (!confirm(tw("wh.rotate_confirm", { name: h.name }))) return;
          var r = await api("/webhooks/rotate", { id: h.id });
          if (r.ok) showSecret(r.hook, r.token);
          load();
        };
        wireEvents(div, h);
        div.querySelector(".whRules").onclick = function () {
          var host = div.querySelector(".whRulesHost");
          if (host.innerHTML) { host.innerHTML = ""; return; }
          host.innerHTML = rulesPanelHtml(h);
          var out = host.querySelector(".whSimOut");
          host.querySelector(".whSim").onclick = async function () {
            var rr = readRules(host.querySelector(".whRulesTxt").value);
            if (!rr.ok) { out.innerHTML = simHtml({ ok: false, error: tw("wh.rules_bad_json") }); return; }
            var sample = host.querySelector(".whSample").value;
            out.innerHTML = simHtml(await api("/webhooks/simulate", { id: h.id, rules: rr.rules, payload: sample }));
          };
          host.querySelector(".whRulesSave").onclick = async function () {
            var rr = readRules(host.querySelector(".whRulesTxt").value);
            var ra = readActions(host.querySelector(".whActsTxt").value);
            var rv = readRules(host.querySelector(".whVerifyTxt").value);
            if (!rr.ok || !ra.ok || !rv.ok) { out.innerHTML = simHtml({ ok: false, error: tw("wh.rules_bad_json") }); return; }
            var r = await api("/webhooks/update", Object.assign({ id: h.id, rules: rr.rules, actions: ra.actions, verify: rv.rules },
              readSettings(host), { revision: h.revision }));
            if (r._status === 409) { out.innerHTML = simHtml({ ok: false, error: r.error || tw("wh.conflict") }); return; }
            if (!r.ok) { out.innerHTML = simHtml(r); return; }
            out.textContent = tw("wh.rules_saved");
            setTimeout(load, 1200);
          };
        };
        div.querySelector(".whDel").onclick = async function () {
          if (!confirm(tw("wh.del_confirm", { name: h.name }))) return;
          await api("/webhooks/delete", { id: h.id });
          load();
        };
        list.appendChild(div);
      });
    }
    load();
  }

  var api_ = { mount: mount, cardHtml: cardHtml, secretHtml: secretHtml, targetLine: targetLine, eventRowHtml: eventRowHtml, errText: errText,
    simHtml: simHtml, rulesPanelHtml: rulesPanelHtml, readRules: readRules, readActions: readActions, detailHtml: detailHtml, settingsHtml: settingsHtml,
    testText: testText, readSettings: readSettings, stateWord: stateWord, timelineHtml: timelineHtml, payloadHtml: payloadHtml,
    replayHtml: replayHtml, planHtml: planHtml, healthHtml: healthHtml, testPanelHtml: testPanelHtml };
  if (typeof window !== "undefined") window.JavisWebhooks = api_;
  if (typeof module !== "undefined" && module.exports) module.exports = api_;
})();
