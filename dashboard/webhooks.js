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
  var STATUS_KEY = { done: "wh.st_done", failed: "wh.st_failed", waiting: "wh.st_waiting", silent: "wh.st_silent" };

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
    var hist = (h.history || []).slice(0, 5).map(function (r) {
      return '<div class="le">' + esc(fmtTime(r.at)) + " · " + esc(tw(STATUS_KEY[r.status] || "wh.st_done"))
        + (r.result ? " · " + esc(String(r.result).slice(0, 140)) : "") + "</div>";
    }).join("");
    return '<b>' + ic("webhook") + " " + esc(h.name) + "</b>"
      + (h.enabled ? "" : ' <span class="dim" style="font-size:12px;color:var(--text3)">' + esc(tw("wh.off")) + "</span>")
      + '<div class="dim" style="font-size:12px;color:var(--text3)">' + esc(targetLine(h)) + " · "
      + esc(tw(LEVEL_KEY[h.level] || "wh.level_full")) + " · " + esc(brainName(brains, h.brain)) + "</div>"
      + '<div style="font-size:12px;margin-top:4px;word-break:break-all"><code>' + esc(h.url) + "</code></div>"
      + '<div class="dim" style="font-size:12px;color:var(--text3);margin-top:2px">' + esc(last)
      + (h.count ? " · " + esc(tw("wh.count", { n: h.count })) : "") + "</div>"
      + (hist ? '<details style="margin-top:4px"><summary style="font-size:12px;cursor:pointer">' + esc(tw("wh.history"))
        + "</summary>" + hist + "</details>" : "")
      + '<div class="wf-actions" style="margin-top:8px">'
      + '<button class="s-btn-ghost whCopy">' + esc(tw("wh.copy_url")) + "</button>"
      + '<button class="s-btn-ghost whTest">' + esc(tw("wh.test")) + "</button>"
      + '<button class="s-btn-ghost whToggle">' + esc(tw(h.enabled ? "wh.turn_off" : "wh.turn_on")) + "</button>"
      + '<button class="s-btn-ghost whRotate">' + esc(tw("wh.rotate")) + "</button>"
      + '<button class="s-btn-ghost whDel" style="color:var(--red)">' + esc(tw("common.delete")) + "</button>"
      + "</div>";
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

  var api_ = { mount: mount, cardHtml: cardHtml, secretHtml: secretHtml, targetLine: targetLine };
  if (typeof window !== "undefined") window.JavisWebhooks = api_;
  if (typeof module !== "undefined" && module.exports) module.exports = api_;
})();
