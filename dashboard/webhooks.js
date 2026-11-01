/* Webhooks page (0.198.0, redesigned 0.432.0).
 *
 * A webhook is a secret URL: when an outside system (a landing page form, a payment, a sheet) calls it, Javis runs a
 * workflow or a written job with the event attached, then reports like a reminder. Server: server/webhook_triggers.py.
 *
 * The token is shown ONCE, right after creating or rotating, because the server keeps only its hash.
 *
 * 0.274.0 (spec §12): each hook has three parts, Configuration / Events / Health. Two switches stay apart: "Stop
 * receiving" (enabled: new requests are refused) and "Pause processing" (paused: still received and stored within the
 * quotas). A real test send shows what each action would do before anything is sent. An event opens on its timeline;
 * its payload is masked, the raw view asks first and is recorded. "Process again with the current setup" previews
 * first and says which actions already succeeded. Saving sends the revision edited; a 409 says someone saved first.
 *
 * 0.432.0 (owner 2026-11-01: "trang này chán", then "bấm vào thì popup lên chứ không drop xuống", "giữ nguyên tới khi
 * khách tắt"): the page is a short overview (one compact row of numbers, a banner when something needs the owner) and
 * one folded row per hook with a strip of its last runs. Pressing a row opens ONE popup (centred on a computer, a sheet
 * from the bottom on a phone) that stays open until the owner closes it: tabs, filters, an event's detail, the test
 * send and the advanced rules all swap what is inside it, never re-open it. The page draws no title of its own: the
 * page header already says "Webhook" (owner: a repeated title only costs space).
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

  // 0.432.0: each status has a tone (its colour) and an icon, so a run reads at a glance: green ran, grey skipped,
  // blue in flight, amber needs the owner, red failed.
  var TONE = { done: "ok", silent: "ok", failed: "bad", dead: "bad", invalid: "bad", waiting: "ask", unknown: "ask",
    blocked: "ask", queued: "run", running: "run", received: "run", filtered: "calm", duplicate: "calm", cancelled: "calm" };
  var TONE_ICON = { ok: "check", bad: "x", ask: "circle-help", run: "loader-circle", calm: "minus" };
  function tone(st) { return TONE[st || "done"] || "ok"; }

  // The agent's "[SILENT]" marker means "nothing to report"; the state word already says so, the marker is noise.
  function resultText(r) {
    var t = String(r.result || r.error || "").trim();
    return /^\[SILENT\]$/i.test(t) ? "" : t;
  }
  function pad(n) { return String(n).padStart(2, "0"); }
  function dayKey(ts) { var d = new Date(ts * 1000); return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  // "Today 01/11", "Yesterday 31/10", or the date alone.
  function dayLabel(ts, now) {
    var d = new Date(ts * 1000), n = new Date((now || Date.now() / 1000) * 1000);
    var dm = pad(d.getDate()) + "/" + pad(d.getMonth() + 1);
    var y = new Date(n.getFullYear(), n.getMonth(), n.getDate() - 1);
    var same = function (a, b) { return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate(); };
    var word = same(d, n) ? tw("wh.today") : same(d, y) ? tw("wh.yesterday") : "";
    return { word: word || dm, date: word ? dm : "" };
  }
  function hm(ts) { if (!ts) return ""; var d = new Date(ts * 1000); return pad(d.getHours()) + ":" + pad(d.getMinutes()); }

  // One run in the list: status icon, time, state in words and its short result. The whole row opens the run's detail
  // inside the popup (whEvInfo); the actions for that run live in the detail (eventActionsHtml).
  function eventRowHtml(r) {
    var st = r.status || "done", tn = tone(st), id = r.run_id || r.id || "", res = resultText(r);
    var inner = '<span class="wh-st wh-t-' + tn + '">' + ic(TONE_ICON[tn]) + "</span>"
      + '<span class="wh-tm">' + esc(hm(r.at || r.received_at)) + "</span>"
      + '<span class="wh-eb"><span class="wh-w wh-w-' + tn + '">' + esc(stateWord(r)) + "</span>"
      + (res ? '<span class="wh-r">' + esc(res.slice(0, 240)) + "</span>" : "") + "</span>"
      + (id ? '<span class="wh-chev">' + ic("chevron-right") + "</span>" : "");
    return id
      ? '<button type="button" class="wh-ev wh-ev-' + esc(st) + ' whEvInfo" data-ev="' + esc(id) + '" data-st="' + esc(st) + '">' + inner + "</button>"
      : '<div class="wh-ev wh-ev-' + esc(st) + '">' + inner + "</div>";
  }
  // Runs grouped under a day line; `prev` is the day of the last row already drawn (paging appends under it).
  function rowsHtml(list, prev, now) {
    var out = "", day = prev || "";
    (list || []).forEach(function (r) {
      var ts = r.at || r.received_at;
      if (ts && dayKey(ts) !== day) {
        day = dayKey(ts);
        var l = dayLabel(ts, now);
        out += '<div class="wh-day" data-day="' + day + '">' + esc(l.word) + (l.date ? " <span>" + esc(l.date) + "</span>" : "") + "</div>";
      }
      out += eventRowHtml(r);
    });
    return out;
  }
  // What the owner can do with one run, by its status.
  function eventActionsHtml(r) {
    var st = r.status || "done", id = esc(r.run_id || r.id || ""), acts = "";
    if (RETRYABLE[st]) acts += '<button class="wh-btn whEvRetry" data-ev="' + id + '">' + esc(tw("wh.retry")) + "</button>";
    if (st === "unknown" || st === "waiting") acts += '<button class="wh-btn whEvDone" data-ev="' + id + '">' + ic("check") + " " + esc(tw("wh.mark_done")) + "</button>";
    // A failed body is kept until the owner settles it or deletes it (spec §11).
    if (st === "failed" || st === "dead") {
      // Settle without resending (handled outside, or given up): its kept body then follows the normal retention.
      acts += '<button class="wh-btn ghost whEvSettle" data-ev="' + id + '">' + esc(tw("wh.ev_settle")) + "</button>";
      acts += '<button class="wh-btn ghost danger whEvDel" data-ev="' + id + '">' + esc(tw("wh.ev_delete")) + "</button>";
    }
    return acts ? '<div class="wh-acts">' + acts + "</div>" : "";
  }
  // The run's own page inside the popup: back, what happened, what the owner can do, then the server's detail.
  function eventViewHtml(r, ev) {
    var st = r.status || (ev && ev.status) || "done", tn = tone(st), ts = r.at || r.received_at || (ev && ev.received_at);
    var l = ts ? dayLabel(ts) : null, res = resultText(r);
    return '<button type="button" class="wh-back whBack">' + ic("chevron-left") + " " + esc(tw("wh.back_events")) + "</button>"
      + '<div class="wh-evhead"><span class="wh-st wh-t-' + tn + '">' + ic(TONE_ICON[tn]) + "</span><div>"
      + '<b class="wh-w wh-w-' + tn + '">' + esc(stateWord(r)) + "</b>"
      + (l ? "<span>" + esc(hm(ts)) + " · " + esc(l.word) + (l.date ? " " + esc(l.date) : "") + "</span>" : "") + "</div></div>"
      + (res ? '<div class="wh-evres">' + esc(res) + "</div>" : "")
      + eventActionsHtml(Object.assign({}, r, { status: st }))
      + '<div class="whEvDetail">' + (ev ? detailHtml(ev) : '<div class="wh-dim">' + ic("loader-circle") + "</div>") + "</div>";
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
  // 0.432.0: a vertical line of dots; a step whose detail says it failed is drawn amber by the server's own words.
  function timelineHtml(tl) {
    if (!tl || !tl.length) return "";
    return '<div class="wh-tl"><div class="wh-subh">' + esc(tw("wh.timeline")) + '</div><ol class="wh-tl-list">'
      + tl.map(function (x) {
        var bad = /fail|error|unknown|timeout/i.test(String(x.detail || "")) || x.step === "quarantined";
        return '<li class="wh-tl-step' + (bad ? " ask" : "") + '"><span class="wh-tl-t">' + esc(fmtTime(x.at)) + "</span> <b>"
          + esc(tw(STEP_KEY[x.step] || x.step)) + "</b>" + (x.detail ? " · " + esc(x.detail) : "") + "</li>";
      }).join("") + "</ol></div>";
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
    // 0.432.0: tiles in four groups instead of one long list; a figure that needs the owner is amber.
    var tile = function (k, v, bad) {
      return '<div class="wh-h' + (bad ? " ask" : "") + '"><span>' + esc(tw(k)) + "</span><b>" + esc(v) + "</b></div>";
    };
    var group = function (k, tiles) { return '<div class="wh-hsec">' + esc(tw(k)) + '</div><div class="wh-hgrid">' + tiles + "</div>"; };
    var errs = (hh.errors_by_target || []).map(function (e) { return e.action_id + " (" + e.kind + ") " + e.n; }).join(", ");
    return '<div class="wh-health">'
      + '<div class="wh-hint">' + esc(tw("wh.h_note")) + "</div>"
      + group("wh.hg_flow", tile("wh.h_received", hh.received || 0) + tile("wh.h_matched", hh.matched || 0) + tile("wh.h_ignored", hh.ignored || 0)
        + tile("wh.h_quarantined", hh.quarantined || 0, hh.quarantined)
        + tile("wh.h_duplicates", (hh.duplicate_deliveries || 0) + " / " + (hh.duplicate_business || 0)))
      + group("wh.hg_wait", tile("wh.h_backlog", hh.backlog || 0) + tile("wh.h_oldest", dur(hh.oldest_open_age_s), hh.oldest_open_age_s > 3600)
        + tile("wh.h_retry", hh.retry_wait || 0) + tile("wh.h_dead", hh.dead || 0, hh.dead)
        + tile("wh.h_unknown", hh.unknown || 0, hh.unknown) + tile("wh.h_blocked", hh.blocked || 0, hh.blocked))
      + group("wh.hg_speed", tile("wh.h_ack", (hh.ack_p50_ms == null ? "-" : hh.ack_p50_ms + " / " + hh.ack_p95_ms + " ms"))
        + tile("wh.h_processing", dur(hh.processing_p50_s) + " / " + dur(hh.processing_p95_s))
        + tile("wh.h_ai", hh.ai_calls || 0) + (errs ? tile("wh.h_errors", errs, true) : ""))
      + group("wh.hg_store", tile("wh.h_sql_busy", hh.sql_busy || 0, hh.sql_busy)
        + tile("wh.h_db", mb(hh.db_bytes) + " + WAL " + mb(hh.wal_bytes) + " / " + mb(hh.cap), hh.level && hh.level !== "ok"))
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

  // ---- 0.432.0: the list row, the overview and the popup ----

  // Something on this hook waits for the owner (an unknown or blocked event, counted by the server over the whole log).
  function needsYou(h) {
    return (h.unknown || 0) > 0 || (h.blocked || 0) > 0
      || (h.history || []).some(function (r) { return r.status === "unknown" || r.status === "blocked"; });
  }
  function dotClass(h) { return !h.enabled ? "off" : h.paused ? "paused" : "on"; }
  function stateChip(h) {
    if (needsYou(h)) return '<span class="wh-chip wh-t-ask">' + ic("triangle-alert") + " " + esc(tw("wh.chip_need")) + "</span>";
    if (h.failed) return '<span class="wh-chip wh-t-bad">' + esc(tw("wh.chip_failed", { n: h.failed })) + "</span>";
    if (!h.enabled) return '<span class="wh-chip">' + esc(tw("wh.chip_off")) + "</span>";
    if (h.paused) return '<span class="wh-chip wh-t-ask">' + esc(tw("wh.chip_paused")) + "</span>";
    return '<span class="wh-chip wh-t-ok">' + esc(tw("wh.chip_on")) + "</span>";
  }
  // The last runs as small bars, oldest on the left: one look says whether this hook is healthy.
  function stripHtml(h) {
    var runs = (h.history || []).slice(0, 20).reverse();
    if (!runs.length) return "";
    var bad = 0, ask = 0;
    var bars = runs.map(function (r) {
      var tn = tone(r.status);
      if (tn === "bad") bad++;
      if (tn === "ask") ask++;
      return '<i class="wh-t-' + tn + '" title="' + esc(hm(r.at) + " " + stateWord(r)) + '"></i>';
    }).join("");
    var lg = tw("wh.strip", { n: runs.length, what: bad ? tw("wh.strip_bad", { n: bad }) : ask ? tw("wh.strip_need", { n: ask }) : tw("wh.strip_ok") });
    return '<span class="wh-strip"><span class="wh-bars" role="img" aria-label="' + esc(lg) + '">' + bars + '</span><span class="wh-lg">'
      + esc(lg) + "</span></span>";
  }

  // One hook in the list, folded: pressing it opens the popup (whOpen).
  function cardHtml(h) {
    var last = h.last_at ? tw("wh.last_short", { time: fmtTime(h.last_at) }) : tw("wh.never_run");
    return '<button type="button" class="wh-row whOpen" data-hook="' + esc(h.id) + '" aria-haspopup="dialog">'
      + '<span class="wh-dot ' + dotClass(h) + '"></span>'
      + '<span class="wh-name">' + esc(h.name) + " " + stateChip(h) + "</span>"
      + '<span class="wh-right"><span class="wh-num"><b>' + esc(h.count || 0) + "</b><span>" + esc(tw("wh.runs_word")) + "</span></span>"
      + '<span class="wh-chev">' + ic("chevron-right") + "</span></span>"
      + '<span class="wh-meta"><span>' + ic("zap") + " " + esc(targetLine(h)) + "</span><span>" + ic("clock") + " " + esc(last) + "</span>"
      + '<span class="wh-cnt">' + esc(tw("wh.count", { n: h.count || 0 })) + "</span></span>"
      + stripHtml(h) + "</button>";
  }

  // The overview: one compact row (owner: save space). `hh` is the 24 h health of all hooks, when it came back.
  function statsHtml(hooks, hh) {
    var on = hooks.filter(function (h) { return h.enabled && !h.paused; }).length;
    var need = hooks.reduce(function (a, h) { return a + (h.unknown || 0) + (h.blocked || 0); }, 0);
    var err = hh ? (hh.dead || 0) + (hh.errors_by_target || []).reduce(function (a, e) { return a + (e.n || 0); }, 0) : null;
    var tile = function (cls, v, label) {
      return '<div class="wh-stat' + (cls ? " " + cls : "") + '"><b>' + esc(v) + "</b><span>" + esc(tw(label)) + "</span></div>";
    };
    return tile("", on + "/" + hooks.length, "wh.s_on")
      + tile("", hh ? hh.received || 0 : "-", "wh.s_24h")
      + tile(need ? "ask" : "", need, "wh.s_need")
      + tile(err ? "bad" : "", err == null ? "-" : err, "wh.s_err");
  }
  // A banner when a run waits for the owner: names the hook, and "See" opens it on its events.
  function alertHtml(hooks) {
    var waiting = hooks.filter(needsYou);
    if (!waiting.length) return "";
    var n = waiting.reduce(function (a, h) { return a + Math.max(1, (h.unknown || 0) + (h.blocked || 0)); }, 0);
    return '<div class="wh-alert">' + ic("triangle-alert") + '<div class="wh-alert-t"><b>' + esc(tw("wh.alert_need", { n: n })) + "</b><span>"
      + esc(waiting.map(function (h) { return h.name; }).join(", ")) + '</span></div><button type="button" class="wh-btn sm warn whOpen" data-hook="'
      + esc(waiting[0].id) + '" data-tab="ev">' + esc(tw("wh.see")) + "</button></div>";
  }
  var VIEWS = [["all", "wh.v_all"], ["need", "wh.v_need"], ["paused", "wh.v_paused"]];
  function inView(h, v) {
    return v === "need" ? needsYou(h) || (h.failed || 0) > 0 : v === "paused" ? !h.enabled || !!h.paused : true;
  }
  function viewsHtml(hooks, v) {
    return VIEWS.map(function (x) {
      var n = hooks.filter(function (h) { return inView(h, x[0]); }).length;
      return '<button type="button" class="wh-segb whView' + (v === x[0] ? " on" : "") + '" data-v="' + x[0] + '">' + esc(tw(x[1]))
        + ' <span class="wh-n' + (x[0] === "need" && n ? " ask" : "") + '">' + n + "</span></button>";
    }).join("");
  }

  // The popup's head: name, state, last run, the tabs. Redrawn on refresh; the body below keeps its place.
  function headHtml(h, tab) {
    var openBreakers = (h.breakers || []).filter(function (b) { return b.open_until > Date.now() / 1000; });
    return '<span class="wh-grab"></span><div class="wh-dtop"><span class="wh-dot ' + dotClass(h) + '"></span><div class="wh-dtitle">'
      + '<h2 id="whDlgTitle">' + ic("webhook") + " " + esc(h.name) + "</h2>"
      + '<div class="wh-meta">' + stateChip(h)
      + "<span>" + ic("clock") + " " + esc(h.last_at ? tw("wh.last_run", { time: fmtTime(h.last_at), status: tw(STATUS_KEY[h.last_status] || "wh.st_done") })
        : tw("wh.never_run")) + "</span>"
      + (h.count ? "<span>" + esc(tw("wh.count", { n: h.count })) + "</span>" : "") + "</div></div>"
      + '<button type="button" class="wh-x whClose" aria-label="' + esc(tw("wh.close")) + '" title="' + esc(tw("wh.close")) + '">' + ic("x") + "</button></div>"
      + (openBreakers.length ? '<div class="wh-need">' + esc(tw("wh.breaker_open", {
        names: openBreakers.map(function (b) { return b.action; }).join(", ") })) + "</div>" : "")
      + '<div class="wh-seg wh-tabs">'
      + [["ev", "wh.tab_events"], ["cfg", "wh.tab_cfg"], ["health", "wh.tab_health"]].map(function (x) {
        return '<button type="button" class="wh-segb whTab' + (x[0] === tab ? " sel" : "") + '" data-tab="' + x[0] + '">' + esc(tw(x[1])) + "</button>";
      }).join("") + "</div>";
  }
  // A hook with something to resolve, or with runs to follow, opens on Events; a new one on Configuration (its URL).
  function firstTab(h) { return needsYou(h) || (h.history || []).length || h.count ? "ev" : "cfg"; }

  var FILTERS = [["", "wh.f_all"], ["needs_you", "wh.f_needs_you"], ["failed,dead", "wh.f_failed"], ["ran", "wh.f_ran"],
    ["filtered,invalid,duplicate", "wh.f_filtered"]];
  function eventsPaneHtml(h) {
    var hist = h.history || [];
    return (needsYou(h) ? '<div class="wh-need">' + ic("triangle-alert") + " " + esc(tw("wh.unknown_hint")) + "</div>" : "")
      + '<div class="wh-fchips">' + FILTERS.map(function (x, i) {
        return '<button type="button" class="wh-fchip whFilter' + (i ? "" : " on") + '" data-f="' + x[0] + '">' + esc(tw(x[1])) + "</button>";
      }).join("") + "</div>"
      + '<div class="wh-tools"><label class="wh-search">' + ic("search") + '<input class="whQ" type="search" placeholder="' + esc(tw("wh.f_q"))
      + '"></label><button type="button" class="wh-ibtn whDates" aria-expanded="false" title="' + esc(tw("wh.f_dates")) + '" aria-label="'
      + esc(tw("wh.f_dates")) + '">' + ic("calendar") + "</button>"
      + '<a class="wh-ibtn" href="/webhooks/events/export?hook=' + encodeURIComponent(h.id) + '&format=csv" download title="' + esc(tw("wh.export"))
      + '" aria-label="' + esc(tw("wh.export")) + '">' + ic("download") + "</a></div>"
      + '<div class="wh-dates" hidden><label>' + esc(tw("wh.f_since")) + ' <input class="whSince" type="date"></label><label>'
      + esc(tw("wh.f_until")) + ' <input class="whUntil" type="date"></label></div>'
      + '<div class="whLogRows">' + (hist.length ? rowsHtml(hist) : '<div class="wh-empty">' + esc(tw("wh.no_events")) + "</div>") + "</div>"
      + '<div class="wh-foot"><button type="button" class="wh-btn ghost whMore">' + esc(tw("wh.more")) + "</button>"
      + (h.failed ? '<button type="button" class="wh-btn ghost whCloseFailed">' + esc(tw("wh.close_failed")) + "</button>" : "")
      + (h.blocked ? '<button type="button" class="wh-btn ghost whRetryBlocked">' + esc(tw("wh.retry_blocked")) + "</button>" : "") + "</div>";
  }
  function switchRow(cls, on, title, state, label) {
    return '<div class="wh-swrow"><div class="wh-swt"><b>' + esc(tw(title)) + "</b><span>" + esc(tw(state)) + "</span></div>"
      + '<button type="button" class="wh-sw ' + cls + '" role="switch" aria-checked="' + (on ? "true" : "false") + '" aria-label="' + esc(tw(label))
      + '" title="' + esc(tw(label)) + '"><span></span></button></div>';
  }
  function configPaneHtml(h, brains) {
    var hasRules = h.rules && Object.keys(h.rules).length;
    return '<div class="wh-field"><div class="wh-lbl">' + esc(tw("wh.lbl_target")) + '</div><div class="wh-chips">'
      + '<span class="wh-chip">' + ic("zap") + " " + esc(targetLine(h)) + "</span>"
      + '<span class="wh-chip">' + ic("shield") + " " + esc(tw(LEVEL_KEY[h.level] || "wh.level_full")) + "</span>"
      + '<span class="wh-chip">' + ic("brain") + " " + esc(brainName(brains, h.brain)) + "</span></div></div>"
      + '<div class="wh-field"><div class="wh-lbl">' + esc(tw("wh.lbl_url")) + '</div><div class="wh-url"><code>' + esc(h.url) + "</code>"
      + '<button type="button" class="wh-btn sm whCopy">' + ic("copy") + " " + esc(tw("wh.copy_url")) + "</button></div>"
      + '<div class="wh-hint">' + ic("key") + " " + esc(h.verify && h.verify.provider && h.verify.provider !== "none"
        ? tw("wh.key_where_signed", { provider: h.verify.provider })
        : tw(h.query_token ? "wh.key_where_legacy" : "wh.key_where", { header: h.token_header || "X-Javis-Token" })) + "</div>"
      + (h.ai_triage ? '<div class="wh-hint">' + esc(tw("wh.ai_triage_on")) + "</div>" : "") + "</div>"
      // Two switches, never one (spec §12): receiving, and processing.
      + switchRow("whToggle", h.enabled, "wh.sw_recv", h.enabled ? "wh.receiving_on" : "wh.receiving_off", h.enabled ? "wh.turn_off" : "wh.turn_on")
      + switchRow("whPause", !h.paused, "wh.sw_proc", h.paused ? "wh.paused_on" : "wh.paused_off", h.paused ? "wh.resume" : "wh.pause")
      + '<div class="wh-acts wh-cfgacts">'
      + '<button type="button" class="wh-btn whTest">' + ic("play") + " " + esc(tw("wh.test")) + "</button>"
      + '<button type="button" class="wh-btn whRules' + (hasRules ? " has-rules" : "") + '">' + ic("sliders-horizontal") + " "
      + esc(tw("wh.rules")) + (hasRules ? " " + ic("check") : "") + "</button>"
      + '<button type="button" class="wh-btn ghost whRotate">' + ic("key-round") + " " + esc(tw("wh.rotate")) + "</button>"
      + '<span class="wh-sp"></span><button type="button" class="wh-btn ghost danger whDel">' + ic("trash-2") + " " + esc(tw("common.delete")) + "</button>"
      + "</div>";
  }
  // Everything inside the popup for one hook: the head, then the three parts. Only one part shows at a time; a run's
  // detail, the test send and the rules open in `.wh-sub` over them, with a way back.
  function dialogHtml(h, brains, tab) {
    tab = tab || firstTab(h);
    var pane = function (name, html) {
      return '<div class="whPane" data-pane="' + name + '"' + (tab === name ? "" : ' style="display:none"') + ">" + html + "</div>";
    };
    return '<div class="wh-dhead">' + headHtml(h, tab) + "</div>"
      + '<div class="wh-dbody"><div class="wh-main">'
      + pane("cfg", configPaneHtml(h, brains)) + pane("ev", eventsPaneHtml(h)) + pane("health", '<div class="whHealthHost"></div>')
      + '</div><div class="wh-sub" hidden></div></div>';
  }

  // The real test send (spec §12): the owner's own payload, the list of what each action would do, then the send.
  function testPanelHtml() {
    return '<button type="button" class="wh-back whBack">' + ic("chevron-left") + " " + esc(tw("wh.back_cfg")) + "</button>"
      + '<h3 class="wh-subh">' + esc(tw("wh.test")) + "</h3>"
      + '<div class="wh-hint">' + esc(tw("wh.test_hint")) + "</div>"
      + '<textarea class="whTestBody wh-code" spellcheck="false">' + esc('{"test": true}') + "</textarea>"
      + '<div class="wh-acts"><button type="button" class="wh-btn whTestPreview">' + esc(tw("wh.test_preview"))
      + '</button><button type="button" class="wh-btn pri whTestGo" disabled>' + esc(tw("wh.test_go")) + "</button></div>"
      + '<div class="whTestOut"></div>';
  }

  function secretHtml(url, token) {
    var curl = "curl -X POST '" + url + "' -H 'Authorization: Bearer " + token
      + "' -H 'Content-Type: application/json' -d '{\"name\":\"Lan\",\"phone\":\"0901\"}'";
    return '<div class="wh-secret">'
      + "<b>" + esc(tw("wh.secret_head")) + "</b><br>" + esc(tw("wh.secret_body"))
      + '<div class="wh-mono"><code>' + esc(token) + "</code></div>"
      + '<div class="wh-hint">' + esc(tw("wh.secret_curl")) + "</div>"
      + '<div class="wh-mono"><code>' + esc(curl) + "</code></div>"
      + '<button type="button" class="wh-btn sm whCopyCurl">' + ic("copy") + " " + esc(tw("wh.copy_curl")) + "</button></div>";
  }

  // The new-webhook form, drawn inside the popup.
  function formHtml(brains, current) {
    var opts = (brains || []).map(function (b) {
      return '<option value="' + esc(b.path) + '"' + (b.path === current ? " selected" : "") + ">" + esc(b.label || b.name) + "</option>";
    }).join("");
    return '<div class="wh-dhead"><span class="wh-grab"></span><div class="wh-dtop"><div class="wh-dtitle"><h2 id="whDlgTitle">' + ic("webhook") + " "
      + esc(tw("wh.add")) + '</h2></div><button type="button" class="wh-x whClose" aria-label="' + esc(tw("wh.close")) + '">' + ic("x") + "</button></div></div>"
      + '<div class="wh-dbody"><div id="whForm" class="wh-form">'
      + '<div class="wh-fld"><label for="whName">' + esc(tw("wh.name")) + '</label><input id="whName" placeholder="' + esc(tw("wh.name_ph")) + '"></div>'
      + '<div class="wh-fld"><label for="whBrain">' + esc(tw("wh.brain")) + '</label><select id="whBrain">' + opts + "</select></div>"
      + '<div class="wh-fld"><label>' + esc(tw("wh.target")) + '</label><div class="wh-seg" id="whTarget">'
      + '<button type="button" class="wh-segb on" data-t="workflow">' + esc(tw("wh.target_wf")) + "</button>"
      + '<button type="button" class="wh-segb" data-t="task">' + esc(tw("wh.target_task")) + "</button></div></div>"
      + '<div class="wh-fld" id="whWfWrap"><label for="whWorkflow">' + esc(tw("wh.workflow")) + '</label><select id="whWorkflow"></select></div>'
      + '<div class="wh-fld"><label id="whTextLabel" for="whText">' + esc(tw("wh.text_wf")) + '</label><textarea id="whText" placeholder="'
      + esc(tw("wh.text_ph")) + '"></textarea></div>'
      + '<div class="wh-fld"><label>' + esc(tw("wh.level")) + '</label><div class="wh-seg" id="whLevel">'
      + '<button type="button" class="wh-segb" data-l="suggest">' + esc(tw("wh.level_suggest")) + "</button>"
      + '<button type="button" class="wh-segb" data-l="auto">' + esc(tw("wh.level_auto")) + "</button>"
      + '<button type="button" class="wh-segb on" data-l="full">' + esc(tw("wh.level_full")) + "</button></div></div>"
      + '<div class="wh-acts"><button type="button" class="wh-btn pri" id="whSave">' + esc(tw("common.save")) + "</button>"
      + '<button type="button" class="wh-btn ghost whClose" id="whCancel">' + esc(tw("common.cancel")) + "</button>"
      + '<span id="whMsg" class="wh-warn"></span></div>'
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

  var current_ = null;   // the mounted page, so unmount() can close its popup and let go of the keyboard listener

  function mount(box, opts) {
    if (!box) return;
    unmount();
    var brains = function () { return (opts && opts.brains && opts.brains()) || []; };
    var current = function () { return (opts && opts.current && opts.current()) || ""; };
    var hooks = [], view = "all", health = null;
    // The open popup: which hook, which tab, and the element. Built once on open; never rebuilt until it closes.
    var M = { id: "", tab: "", el: null, form: false };
    box.classList.add("wh-root");
    box.innerHTML = '<div class="wh-stats" id="whStats"></div><div id="whAlert"></div>'
      + '<div class="wh-bar"><div class="wh-seg" id="whViews"></div><span class="wh-sp"></span>' + infoBtn()
      + '<button type="button" class="wh-btn pri" id="whNew" aria-label="' + esc(tw("wh.add")) + '">' + ic("plus")
      + ' <span class="wh-newl">' + esc(tw("wh.add")) + "</span></button></div>"
      + infoBody(esc(tw("wh.intro")))
      + '<div id="whSecret"></div><div id="whList"></div>';
    var q = function (s) { return box.querySelector(s); };
    // The popup hangs off <body>, above the app's top bar and rail; it carries wh-root for the page's colours and sizes.
    var modal = document.createElement("div");
    modal.className = "wh-root wh-modal";
    modal.id = "whModal";
    modal.hidden = true;
    document.body.appendChild(modal);

    function showSecret(hook, token) {
      q("#whSecret").innerHTML = secretHtml(hook.url, token);
      var b = q(".whCopyCurl");
      if (b) b.onclick = function () {
        var code = q("#whSecret").querySelectorAll("code")[1];
        copy(code ? code.textContent : "").then(function () { b.textContent = tw("wh.copied"); });
      };
    }

    // ---- popup shell: open once, close only by the owner (X, the dimmed area, Esc) ----
    function openShell() {
      modal.innerHTML = '<div class="wh-scrim whClose"></div><div class="wh-dlg" role="dialog" aria-modal="true" aria-labelledby="whDlgTitle"></div>';
      modal.hidden = false;
      document.body.classList.add("wh-locked");
      M.el = modal.querySelector(".wh-dlg");
      M.back = document.activeElement;
      return M.el;
    }
    function closeModal() {
      modal.hidden = true; modal.innerHTML = ""; M = { id: "", tab: "", el: null, form: false };
      document.body.classList.remove("wh-locked");
    }
    modal.addEventListener("click", function (ev) {
      var c = ev.target.closest(".whClose");
      if (c && modal.contains(c)) { var back = M.back; closeModal(); if (back && back.focus) try { back.focus(); } catch (e) { /* gone */ } }
    });
    function onKey(ev) {
      if (ev.key !== "Escape" || modal.hidden) return;
      var sub = modal.querySelector(".wh-sub");
      if (sub && !sub.hidden) { hideSub(); return; }
      closeModal();
    }
    document.addEventListener("keydown", onKey);
    current_ = { close: closeModal, key: onKey, modal: modal };

    function hook(id) { return hooks.filter(function (x) { return x.id === id; })[0]; }

    // ---- the add form ----
    var target = "workflow", level = "full";
    async function loadWorkflows() {
      var sel = modal.querySelector("#whWorkflow");
      if (!sel) return;
      var d = await api("/workflows?brain=" + encodeURIComponent(modal.querySelector("#whBrain").value || current()));
      var wfs = (d && d.workflows) || [];
      sel.innerHTML = wfs.length
        ? wfs.map(function (w) { return '<option value="' + esc(w.slug) + '">' + esc(w.name || w.slug) + "</option>"; }).join("")
        : '<option value="">' + esc(tw("wh.no_workflow")) + "</option>";
    }
    function syncForm() {
      modal.querySelectorAll("#whTarget .wh-segb").forEach(function (c) { c.classList.toggle("on", c.dataset.t === target); });
      modal.querySelectorAll("#whLevel .wh-segb").forEach(function (c) { c.classList.toggle("on", c.dataset.l === level); });
      modal.querySelector("#whWfWrap").style.display = target === "workflow" ? "" : "none";
      modal.querySelector("#whTextLabel").textContent = tw(target === "workflow" ? "wh.text_wf" : "wh.text_task");
    }
    function openForm() {
      var dlg = openShell();
      M.form = true;
      dlg.innerHTML = formHtml(brains(), current());
      target = "workflow"; level = "full";
      var f = function (s) { return dlg.querySelector(s); };
      dlg.querySelectorAll("#whTarget .wh-segb").forEach(function (c) { c.onclick = function () { target = c.dataset.t; syncForm(); }; });
      dlg.querySelectorAll("#whLevel .wh-segb").forEach(function (c) { c.onclick = function () { level = c.dataset.l; syncForm(); }; });
      f("#whBrain").onchange = loadWorkflows;
      f("#whSave").onclick = async function () {
        var body = { name: f("#whName").value.trim(), brain: f("#whBrain").value, target: target, level: level,
          workflow: target === "workflow" ? f("#whWorkflow").value : "", text: f("#whText").value.trim() };
        if (!body.name) { f("#whMsg").textContent = tw("wh.need_name"); return; }
        var r = await api("/webhooks", body);
        if (!r.ok) { f("#whMsg").textContent = r.error || tw("wh.save_err"); return; }
        closeModal();
        showSecret(r.hook, r.token);
        load();
      };
      syncForm();
      loadWorkflows();
      f("#whName").focus();
    }
    q("#whNew").onclick = openForm;

    // ---- the hook popup ----
    function openHook(id, tab) {
      var h = hook(id);
      if (!h) return;
      var dlg = openShell();
      M.id = id; M.tab = tab || firstTab(h);
      dlg.innerHTML = dialogHtml(h, brains(), M.tab);
      wireHead(h);
      wireConfig(h);
      wireEvents(h);
      if (M.tab === "health") showHealth(h);
      var x = dlg.querySelector(".wh-x");
      if (x) x.focus();
    }
    function switchTab(tab) {
      var h = hook(M.id);
      if (!h || !M.el) return;
      M.tab = tab;
      hideSub();
      M.el.querySelectorAll(".whTab").forEach(function (x) { x.classList.toggle("sel", x.dataset.tab === tab); });
      M.el.querySelectorAll(".whPane").forEach(function (p) { p.style.display = p.dataset.pane === tab ? "" : "none"; });
      M.el.querySelector(".wh-dbody").scrollTop = 0;
      if (tab === "health") showHealth(h);
    }
    function wireHead() {
      M.el.querySelectorAll(".whTab").forEach(function (t) { t.onclick = function () { switchTab(t.dataset.tab); }; });
    }
    async function showHealth(h) {
      var hd = await api("/webhooks/health?hook=" + encodeURIComponent(h.id));
      var host = M.el && M.el.querySelector(".whHealthHost");
      if (host) host.innerHTML = hd && hd.ok ? healthHtml(hd.health) : esc(errText(hd));
    }
    // A run's detail, the test send and the rules open over the parts; Back (or Esc) returns to where the owner was.
    var mainTop = 0;
    function showSub(html) {
      var body = M.el.querySelector(".wh-dbody"), main = M.el.querySelector(".wh-main"), sub = M.el.querySelector(".wh-sub");
      mainTop = body.scrollTop;
      sub.innerHTML = html; sub.hidden = false; main.hidden = true; body.scrollTop = 0;
      var b = sub.querySelector(".whBack");
      if (b) b.onclick = hideSub;
      return sub;
    }
    function hideSub() {
      if (!M.el) return;
      var body = M.el.querySelector(".wh-dbody"), main = M.el.querySelector(".wh-main"), sub = M.el.querySelector(".wh-sub");
      if (!sub || sub.hidden) return;
      sub.hidden = true; sub.innerHTML = ""; main.hidden = false; body.scrollTop = mainTop;
    }

    // After an action: refresh the list and the popup in place (head, configuration, the first page of runs).
    function refreshSoon(ms) { setTimeout(function () { load(true); }, ms || 0); }
    function refreshOpen() {
      var h = hook(M.id);
      if (!h || !M.el || M.form) return;
      M.el.querySelector(".wh-dhead").innerHTML = headHtml(h, M.tab);
      wireHead(h);
      var cfg = M.el.querySelector('.whPane[data-pane="cfg"]');
      cfg.innerHTML = configPaneHtml(h, brains());
      wireConfig(h);
      if (M.events) M.events.reload();
    }

    function wireConfig(h) {
      var p = M.el.querySelector('.whPane[data-pane="cfg"]');
      var b = function (s) { return p.querySelector(s); };
      b(".whCopy").onclick = function (ev) {
        var btn = ev.currentTarget;
        copy(h.url).then(function () { btn.textContent = tw("wh.copied"); });
      };
      b(".whToggle").onclick = async function () {
        if (h.enabled && !confirm(tw("wh.turn_off_confirm"))) return;
        await api("/webhooks/update", { id: h.id, enabled: !h.enabled });
        refreshSoon();
      };
      b(".whPause").onclick = async function () {
        await api("/webhooks/pause", { id: h.id, paused: !h.paused });
        refreshSoon();
      };
      b(".whRotate").onclick = async function () {
        if (!confirm(tw("wh.rotate_confirm", { name: h.name }))) return;
        var r = await api("/webhooks/rotate", { id: h.id });
        if (r.ok) { closeModal(); showSecret(r.hook, r.token); }
        load();
      };
      b(".whDel").onclick = async function () {
        if (!confirm(tw("wh.del_confirm", { name: h.name }))) return;
        await api("/webhooks/delete", { id: h.id });
        closeModal();
        load();
      };
      b(".whTest").onclick = function () {
        var host = showSub(testPanelHtml());
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
          refreshSoon(4000);
        };
      };
      b(".whRules").onclick = function () {
        var host = showSub('<button type="button" class="wh-back whBack">' + ic("chevron-left") + " " + esc(tw("wh.back_cfg")) + "</button>"
          + '<h3 class="wh-subh">' + esc(tw("wh.rules")) + "</h3>" + rulesPanelHtml(h));
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
          refreshSoon(1200);
        };
      };
    }

    // The Events part: filter chips, search and dates, the runs by day, older pages (keyset cursor), the bulk actions.
    function wireEvents(h) {
      var p = M.el.querySelector('.whPane[data-pane="ev"]');
      var rowsBox = p.querySelector(".whLogRows"), more = p.querySelector(".whMore");
      var cursor = "", status = "", known = {};
      (h.history || []).forEach(function (r) { known[r.run_id || r.id] = r; });
      var qBox = p.querySelector(".whQ"), sinceBox = p.querySelector(".whSince"), untilBox = p.querySelector(".whUntil");
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
      async function page(first) {
        if (first) cursor = "";
        var url = "/webhooks/events?hook=" + encodeURIComponent(h.id) + "&limit=20" + (status ? "&status=" + encodeURIComponent(status) : "")
          + filters() + (cursor ? "&before=" + encodeURIComponent(cursor) : "");
        var d = await api(url);
        if (!d || !d.ok) { more.textContent = (d && d.error) || tw("wh.save_err"); return; }
        var items = d.items || [];
        items.forEach(function (r) { known[r.run_id || r.id] = r; });
        if (!cursor) rowsBox.innerHTML = items.length ? "" : '<div class="wh-empty">' + esc(tw("wh.no_events")) + "</div>";
        var lastDay = rowsBox.querySelectorAll(".wh-day");
        var tmp = document.createElement("div");
        tmp.innerHTML = rowsHtml(items, lastDay.length ? lastDay[lastDay.length - 1].dataset.day : "");
        while (tmp.firstChild) rowsBox.appendChild(tmp.firstChild);
        cursor = d.next || "";
        more.style.display = cursor ? "" : "none";
      }
      more.onclick = function () { page(false); };
      var refilter = function () { page(true); };
      p.querySelectorAll(".whFilter").forEach(function (c) {
        c.onclick = function () {
          p.querySelectorAll(".whFilter").forEach(function (x) { x.classList.toggle("on", x === c); });
          status = c.dataset.f;
          refilter();
        };
      });
      [qBox, sinceBox, untilBox].forEach(function (el) { if (el) el.onchange = refilter; });
      var dates = p.querySelector(".whDates");
      if (dates) dates.onclick = function () {
        var row = p.querySelector(".wh-dates");
        row.hidden = !row.hidden;
        dates.setAttribute("aria-expanded", row.hidden ? "false" : "true");
      };
      // A run opens on its own page inside the popup.
      rowsBox.addEventListener("click", function (ev) {
        var b = ev.target.closest(".whEvInfo");
        if (b) openEvent(b, known[b.dataset.ev] || { id: b.dataset.ev, status: b.dataset.st });
      });
      var rb = p.querySelector(".whRetryBlocked");
      if (rb) rb.onclick = async function () {
        var r = await api("/webhooks/events/retry_blocked", { hook: h.id });
        rb.textContent = r.ok ? tw("wh.retried_n", { n: r.queued }) : errText(r);
        if (r.ok) refreshSoon(2500);
      };
      var closeAll = p.querySelector(".whCloseFailed");
      if (closeAll) closeAll.onclick = async function () {
        if (!confirm(tw("wh.close_failed_confirm"))) return;
        var r = await api("/webhooks/events/close_failed", { hook: h.id });
        closeAll.textContent = r.ok ? tw("wh.closed_n", { n: r.closed }) : errText(r);
        if (r.ok) refreshSoon(1500);
      };
      // Refresh keeps the owner's filter: it reloads the first page under it.
      M.events = { reload: function () { if (status || filters()) page(true); else {
        var fresh = hook(h.id) || h;
        (fresh.history || []).forEach(function (r) { known[r.run_id || r.id] = r; });
        rowsBox.innerHTML = (fresh.history || []).length ? rowsHtml(fresh.history) : '<div class="wh-empty">' + esc(tw("wh.no_events")) + "</div>";
        cursor = ""; more.style.display = "";
      } } };
    }

    // One run: its page inside the popup, then the server's detail (timeline, actions' branches, payload, replay).
    var evTok = 0;
    async function openEvent(b, r) {
      var sub = showSub(eventViewHtml(r, null)), tok = ++evTok;
      wireEventActions(sub);
      var d = await api("/webhooks/events/" + encodeURIComponent(b.dataset.ev));
      // The owner went back, or opened another run, while this one was loading: drop it.
      if (sub.hidden || tok !== evTok || !sub.isConnected) return;
      var box = sub.querySelector(".whEvDetail");
      box.innerHTML = d && d.ok ? detailHtml(d.event) : esc(errText(d));
      wireDetail(box);
      box.querySelectorAll(".whApprove").forEach(function (x) {
        x.onclick = async function () {
          var r = await api("/webhooks/events/approve", { id: x.dataset.ev, action: x.dataset.act, decision: x.dataset.d });
          x.textContent = r.ok ? tw(x.dataset.d === "approve" ? "wh.approved" : "wh.rejected") : errText(r);
          if (r.ok) refreshSoon(2500);
        };
      });
    }
    // Retry / Mark done / Close / Delete on one run; done, the owner goes back to the list, refreshed.
    function wireEventActions(scope) {
      var after = function () { hideSub(); refreshSoon(); };
      scope.querySelectorAll(".whEvRetry").forEach(function (b) {
        b.onclick = async function () {
          if (!confirm(tw("wh.retry_confirm"))) return;
          var r = await api("/webhooks/events/retry", { id: b.dataset.ev });
          b.textContent = r.ok ? tw("wh.retry_sent") : errText(r);
          if (r.ok) setTimeout(after, 1500);
        };
      });
      scope.querySelectorAll(".whEvSettle").forEach(function (b) {
        b.onclick = async function () {
          if (!confirm(tw("wh.ev_settle_confirm"))) return;
          var r = await api("/webhooks/events/resolve", { id: b.dataset.ev, outcome: "done", note: "settled by the owner" });
          if (r.ok) after(); else b.textContent = errText(r);
        };
      });
      scope.querySelectorAll(".whEvDel").forEach(function (b) {
        b.onclick = async function () {
          if (!confirm(tw("wh.ev_delete_confirm"))) return;
          var r = await api("/webhooks/events/delete", { id: b.dataset.ev });
          if (r.ok) after(); else b.textContent = errText(r);
        };
      });
      scope.querySelectorAll(".whEvDone").forEach(function (b) {
        b.onclick = async function () {
          var r = await api("/webhooks/events/resolve", { id: b.dataset.ev, outcome: "done" });
          if (r.ok) after(); else b.textContent = errText(r);
        };
      });
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
            if (r && r.ok) refreshSoon(2500);
          };
        };
      });
    }

    function drawList() {
      var list = q("#whList");
      if (!list) return;
      q("#whStats").innerHTML = statsHtml(hooks, health);
      q("#whAlert").innerHTML = alertHtml(hooks);
      q("#whViews").innerHTML = viewsHtml(hooks, view);
      var shown = hooks.filter(function (h) { return inView(h, view); });
      if (!hooks.length) { list.innerHTML = '<div class="wh-empty">' + esc(tw("wh.empty")) + "</div>"; return; }
      list.innerHTML = shown.length ? shown.map(function (h) {
        return '<div class="wh-card' + (needsYou(h) ? " need" : "") + '">' + cardHtml(h) + "</div>";
      }).join("") : '<div class="wh-empty">' + esc(tw("wh.v_empty")) + "</div>";
    }
    box.addEventListener("click", function (ev) {
      var o = ev.target.closest(".whOpen");
      if (o) { openHook(o.dataset.hook, o.dataset.tab); return; }
      var v = ev.target.closest(".whView");
      if (v) { view = v.dataset.v; drawList(); }
    });

    async function load(keepOpen) {
      var res = await Promise.all([api("/webhooks"), api("/webhooks/health")]);
      if (!q("#whList")) return;
      hooks = (res[0] && res[0].hooks) || [];
      health = res[1] && res[1].ok ? res[1].health : null;
      drawList();
      if (keepOpen && M.id) { if (hook(M.id)) refreshOpen(); else closeModal(); }
    }
    load();
  }

  function unmount() {
    if (!current_) return;
    try { current_.close(); } catch (e) { /* page already gone */ }
    document.removeEventListener("keydown", current_.key);
    if (current_.modal && current_.modal.parentNode) current_.modal.parentNode.removeChild(current_.modal);
    current_ = null;
  }

  var api_ = { mount: mount, unmount: unmount, cardHtml: cardHtml, dialogHtml: dialogHtml, statsHtml: statsHtml, alertHtml: alertHtml,
    rowsHtml: rowsHtml, stripHtml: stripHtml, eventActionsHtml: eventActionsHtml, eventViewHtml: eventViewHtml,
    secretHtml: secretHtml, targetLine: targetLine, eventRowHtml: eventRowHtml, errText: errText,
    simHtml: simHtml, rulesPanelHtml: rulesPanelHtml, readRules: readRules, readActions: readActions, detailHtml: detailHtml, settingsHtml: settingsHtml,
    testText: testText, readSettings: readSettings, stateWord: stateWord, timelineHtml: timelineHtml, payloadHtml: payloadHtml,
    replayHtml: replayHtml, planHtml: planHtml, healthHtml: healthHtml, testPanelHtml: testPanelHtml, formHtml: formHtml };
  if (typeof window !== "undefined") window.JavisWebhooks = api_;
  if (typeof module !== "undefined" && module.exports) module.exports = api_;
})();
