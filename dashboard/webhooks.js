/* Webhooks section of the Work page (0.198.0).
 *
 * A webhook is a secret URL: when an outside system (a landing page form, a payment, a sheet) calls it, Javis runs a
 * workflow or a written job with the event attached, then reports like a reminder. Server: server/webhook_triggers.py.
 *
 * The token is shown ONCE, right after creating or rotating, because the server keeps only its hash. Cards show the
 * URL (without the token), the target, the permission level, the last runs, and buttons: copy URL, send a test event,
 * switch on/off, new token, delete.
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
    filtered: "wh.st_filtered", invalid: "wh.st_invalid", duplicate: "wh.st_duplicate" };
  // 0.229.0: events are stored durably (server/webhook_store.py). A run that may have acted before the server stopped
  // is "unknown": only the owner decides, after checking outside, whether it happened (Mark done) or not (Retry).
  var RETRYABLE = { failed: 1, unknown: 1, dead: 1 };

  // One line of the event log: time, status, short result, and the owner's actions for that event.
  function eventRowHtml(r) {
    var st = r.status || "done";
    var acts = "";
    if (RETRYABLE[st]) acts += '<button class="s-btn-ghost whEvRetry" data-ev="' + esc(r.run_id || r.id) + '">' + esc(tw("wh.retry")) + "</button>";
    if (st === "unknown") {
      acts += '<button class="s-btn-ghost whEvDone" data-ev="' + esc(r.run_id || r.id) + '">' + esc(tw("wh.mark_done")) + "</button>";
    }
    return '<div class="le wh-ev wh-ev-' + esc(st) + '">' + esc(fmtTime(r.at || r.received_at)) + " · "
      + '<span class="wh-st">' + esc(tw(STATUS_KEY[st] || "wh.st_done")) + "</span>"
      + ((r.result || r.error) ? " · " + esc(String(r.result || r.error).slice(0, 140)) : "")
      + (acts ? '<span class="wh-ev-acts">' + acts + "</span>" : "") + "</div>";
  }

  // M2: what the hook's rules decided for a sample body (POST /webhooks/simulate). Nothing was stored or run.
  var SIM_KEY = { run: "wh.sim_run", filtered: "wh.sim_filtered", invalid: "wh.sim_invalid", duplicate: "wh.sim_duplicate" };
  function stepLine(ok, text) {
    return '<div class="wh-sim-step" style="color:' + (ok ? "var(--text2)" : "var(--warn-ink)") + '">'
      + (ok ? "✓ " : "✗ ") + esc(text) + "</div>";
  }
  function plain(v) { return v === null || v === undefined ? "∅" : (typeof v === "object" ? JSON.stringify(v) : String(v)); }
  function simHtml(sim) {
    if (!sim || !sim.ok) return '<div style="color:var(--warn-ink)">' + esc((sim && sim.error) || tw("wh.save_err")) + "</div>";
    var t = sim.trace || {};
    var out = '<div class="wh-sim-head"><b>' + esc(tw(SIM_KEY[sim.decision] || "wh.sim_run")) + "</b>"
      + (sim.reason ? " · " + esc(sim.reason) : "") + "</div>";
    (t.schema || []).forEach(function (s) { out += stepLine(s.pass, tw("wh.sim_schema") + " " + s.path + ": " + s.why); });
    (t.filter || []).forEach(function (s) {
      out += stepLine(s.pass, tw("wh.sim_filter") + " " + s.path + " " + s.op + ("value" in s ? " " + plain(s.value) : "")
        + " (" + plain(s.actual) + ")");
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
  function rulesPanelHtml(h) {
    var rules = h.rules && Object.keys(h.rules).length ? JSON.stringify(h.rules, null, 2) : "";
    return '<div class="wh-rules" style="margin-top:8px;padding:10px;border:1px solid var(--hairline);border-radius:8px">'
      + '<div class="dim" style="color:var(--text3)">' + esc(tw("wh.rules_hint")) + "</div>"
      + '<label style="display:block;margin-top:6px">' + esc(tw("wh.rules_label")) + "</label>"
      + '<textarea class="whRulesTxt" spellcheck="false" style="width:100%;min-height:140px;font-family:monospace">' + esc(rules) + "</textarea>"
      + '<label style="display:block;margin-top:6px">' + esc(tw("wh.sample_label")) + "</label>"
      + '<textarea class="whSample" spellcheck="false" style="width:100%;min-height:90px;font-family:monospace"></textarea>'
      + '<div class="wf-actions" style="margin-top:6px"><button class="s-btn-ghost whSim">' + esc(tw("wh.simulate")) + "</button>"
      + '<button class="s-btn whRulesSave">' + esc(tw("wh.rules_save")) + "</button></div>"
      + '<div class="whSimOut" style="margin-top:6px"></div></div>';
  }
  // The rules box as an object: "" means no rules; text that is not JSON is reported, not sent.
  function readRules(text) {
    var t = String(text || "").trim();
    if (!t) return { ok: true, rules: {} };
    try { return { ok: true, rules: JSON.parse(t) }; } catch (e) { return { ok: false }; }
  }

  // Error codes of the event actions, in words.
  var ERR_KEY = { not_found: "wh.err_not_found", not_retryable: "wh.err_not_retryable", not_unknown: "wh.err_not_unknown" };
  function errText(r) { return tw(ERR_KEY[r && r.error] || "wh.save_err"); }

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
    return h.target === "workflow"
      ? tw("wh.target_wf_line", { name: h.workflow })
      : tw("wh.target_task_line", { text: String(h.text || "").slice(0, 80) });
  }

  function cardHtml(h, brains) {
    var last = h.last_at ? tw("wh.last_run", { time: fmtTime(h.last_at), status: tw(STATUS_KEY[h.last_status] || "wh.st_done") })
      : tw("wh.never_run");
    var rows = (h.history || []).slice(0, 5);
    // The server counts unknown events over the WHOLE log, not just the newest rows drawn here.
    var needYou = (h.unknown || 0) > 0 || (h.history || []).some(function (r) { return r.status === "unknown"; });
    var hist = rows.map(eventRowHtml).join("");
    return '<b>' + ic("webhook") + " " + esc(h.name) + "</b>"
      + (h.enabled ? "" : ' <span class="dim" style="font-size:12px;color:var(--text3)">' + esc(tw("wh.off")) + "</span>")
      + '<div class="dim" style="font-size:12px;color:var(--text3)">' + esc(targetLine(h)) + " · "
      + esc(tw(LEVEL_KEY[h.level] || "wh.level_full")) + " · " + esc(brainName(brains, h.brain)) + "</div>"
      + '<div style="font-size:12px;margin-top:4px;word-break:break-all"><code>' + esc(h.url) + "</code></div>"
      + '<div class="dim" style="font-size:12px;color:var(--text3);margin-top:2px">' + esc(last)
      + (h.count ? " · " + esc(tw("wh.count", { n: h.count })) : "") + "</div>"
      + (needYou ? '<div class="wh-need" style="font-size:13px;color:var(--warn-ink);margin-top:4px">' + esc(tw("wh.unknown_hint")) + "</div>" : "")
      + (hist ? '<details class="whLog" style="margin-top:4px"' + (needYou ? " open" : "") + '><summary style="font-size:12px;cursor:pointer">'
        + esc(tw("wh.history")) + '</summary><div class="whLogRows">' + hist + "</div>"
        + '<button class="s-btn-ghost whMore" style="font-size:12px">' + esc(tw("wh.more")) + "</button></details>" : "")
      + '<div class="wf-actions" style="margin-top:8px">'
      + '<button class="s-btn-ghost whCopy">' + esc(tw("wh.copy_url")) + "</button>"
      + '<button class="s-btn-ghost whTest">' + esc(tw("wh.test")) + "</button>"
      + '<button class="s-btn-ghost whRules">' + esc(tw("wh.rules")) + (h.rules && Object.keys(h.rules).length ? " ✓" : "") + "</button>"
      + '<button class="s-btn-ghost whToggle">' + esc(tw(h.enabled ? "wh.turn_off" : "wh.turn_on")) + "</button>"
      + '<button class="s-btn-ghost whRotate">' + esc(tw("wh.rotate")) + "</button>"
      + '<button class="s-btn-ghost whDel" style="color:var(--red)">' + esc(tw("common.delete")) + "</button>"
      + "</div>"
      + '<div class="whRulesHost"></div>';
  }

  function secretHtml(url, token) {
    var curl = "curl -X POST '" + url + "' -H 'Authorization: Bearer " + token
      + "' -H 'Content-Type: application/json' -d '{\"name\":\"Lan\",\"phone\":\"0901\"}'";
    return '<div style="padding:10px 12px;border:1px solid var(--green);border-radius:8px;margin-bottom:10px;font-size:13px;line-height:1.5">'
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
      + '<span class="dim" id="whMsg" style="font-size:13px;color:var(--warn-ink)"></span></div>'
      + "</div></div>";
  }

  async function api(url, body) {
    try {
      var r = await fetch(url, body === undefined ? undefined : {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      return await r.json();
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
    box.innerHTML = '<div class="lp-group"><div style="display:flex;align-items:center;gap:8px;margin:22px 0 8px;font-size:15px;color:var(--text);font-weight:600;border-bottom:1px solid var(--hairline);padding-bottom:6px">'
      + "<span>" + ic("webhook") + " " + esc(tw("wh.head")) + infoBtn() + "</span>"
      + '<button class="s-btn-ghost" id="whNew" style="margin-left:auto;font-size:13px">+ ' + esc(tw("wh.add")) + "</button></div>"
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
      function bindRows(scope) {
        scope.querySelectorAll(".whEvRetry").forEach(function (b) {
          b.onclick = async function () {
            if (!confirm(tw("wh.retry_confirm"))) return;
            var r = await api("/webhooks/events/retry", { id: b.dataset.ev });
            b.textContent = r.ok ? tw("wh.retry_sent") : errText(r);
            setTimeout(load, 3000);
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
      if (!more || !rowsBox) return;
      more.onclick = async function () {
        var url = "/webhooks/events?hook=" + encodeURIComponent(h.id) + "&limit=20" + (cursor ? "&before=" + encodeURIComponent(cursor) : "");
        var d = await api(url);
        if (!d || !d.ok) { more.textContent = (d && d.error) || tw("wh.save_err"); return; }
        if (!cursor) rowsBox.innerHTML = "";
        var tmp = document.createElement("div");
        tmp.innerHTML = (d.items || []).map(eventRowHtml).join("");
        bindRows(tmp);
        while (tmp.firstChild) rowsBox.appendChild(tmp.firstChild);
        cursor = d.next || "";
        if (!cursor) more.style.display = "none";
      };
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
        div.querySelector(".whTest").onclick = async function (ev) {
          var r = await api("/webhooks/test", { id: h.id });
          ev.target.textContent = r.ok ? tw("wh.test_sent") : (r.error || tw("wh.save_err"));
          setTimeout(load, 4000);
        };
        div.querySelector(".whToggle").onclick = async function () {
          await api("/webhooks/update", { id: h.id, enabled: !h.enabled });
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
            if (!rr.ok) { out.innerHTML = simHtml({ ok: false, error: tw("wh.rules_bad_json") }); return; }
            var r = await api("/webhooks/update", { id: h.id, rules: rr.rules });
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
    simHtml: simHtml, rulesPanelHtml: rulesPanelHtml, readRules: readRules };
  if (typeof window !== "undefined") window.JavisWebhooks = api_;
  if (typeof module !== "undefined" && module.exports) module.exports = api_;
})();
