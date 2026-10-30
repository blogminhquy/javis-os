/* Health section of the Work page (0.199.0): incidents Javis Core is handling, and the read-only health scan.
 *
 * Incidents (server/incident_desk.py): a background run broke, Javis Core retried it once or said what only you can
 * fix. Each row has "Done" to close it. Health scan (server/sentinel.py): failures of the last 24 hours from every
 * store, grouped by cause and sorted by count. Nothing here starts or changes a job.
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

  var STATUS_KEY = { open: "hp.st_open", retrying: "hp.st_retrying", needs_you: "hp.st_needs_you", resolved: "hp.st_resolved" };
  var SOURCE_KEY = { kanban: "hp.src_kanban", loop: "hp.src_loop", reminder: "hp.src_reminder", webhook: "hp.src_webhook",
    workflow: "hp.src_workflow" };

  function fmtTime(ts) {
    if (!ts) return "";
    var d = new Date(ts * 1000);
    var p = function (n) { return String(n).padStart(2, "0"); };
    return p(d.getHours()) + ":" + p(d.getMinutes()) + " " + p(d.getDate()) + "/" + p(d.getMonth() + 1);
  }

  function incidentHtml(i) {
    var open = i.status !== "resolved";
    return '<div class="wf-card" data-id="' + esc(i.id) + '"><b>' + ic(i.status === "needs_you" ? "triangle-alert" : "rotate-cw")
      + " " + esc(i.title || i.source) + "</b>"
      + '<div class="dim" style="font-size:12px;color:var(--text3)">' + esc(tw(SOURCE_KEY[i.source] || "hp.src_kanban"))
      + " · " + esc(tw(STATUS_KEY[i.status] || "hp.st_open")) + " · " + esc(fmtTime(i.last_at || i.at))
      + (i.count > 1 ? " · " + esc(tw("hp.times", { n: i.count })) : "") + "</div>"
      + (i.message ? '<div style="font-size:13px;margin-top:4px">' + esc(i.message) + "</div>" : "")
      + (i.error ? '<div class="dim" style="font-size:12px;color:var(--warn-ink);margin-top:4px">' + esc(String(i.error).slice(0, 220)) + "</div>" : "")
      + (open ? '<div class="wf-actions" style="margin-top:8px"><button class="s-btn-ghost hpDone">' + esc(tw("hp.done")) + "</button></div>" : "")
      + "</div>";
  }

  function issueHtml(g) {
    var ex = (g.examples || []).map(function (e) {
      return esc(tw(SOURCE_KEY[e.source] || "hp.src_kanban")) + ": " + esc(e.title || e.ref);
    }).join(" · ");
    return '<div class="le"><b>' + esc(tw("hp.times", { n: g.count })) + "</b> " + esc(g.error)
      + (ex ? '<div class="dim" style="font-size:12px;color:var(--text3)">' + ex + "</div>" : "") + "</div>";
  }

  // Lỗi giao diện gửi về từ trình duyệt (loi-may-khach.js, 0.416.0): mỗi nhóm một dòng, cùng thông điệp, file, dòng.
  function clientErrorHtml(g) {
    var where = (g.src ? g.src.replace(/^\/static\//, "") : "") + (g.dong ? ":" + g.dong : "");
    var meta = [tw("hp.times", { n: g.count || 1 }), fmtTime(g.last_at), g.version ? "v" + g.version : "", g.trang || "",
      shortUa(g.ua)].filter(Boolean).join(" · ");
    return '<div class="le"><b>' + esc(String(g.msg || "").slice(0, 300)) + "</b>"
      + (where ? ' <code style="font-size:12px">' + esc(where) + "</code>" : "")
      + '<div class="dim" style="font-size:12px;color:var(--text3)">' + esc(meta) + "</div></div>";
  }
  // "iPhone · Safari" thay cho cả chuỗi User-Agent dài.
  function shortUa(ua) {
    ua = String(ua || "");
    if (!ua) return "";
    var may = /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) ? "iPad" : /Android/.test(ua) ? "Android"
      : /Mac OS X/.test(ua) ? "Mac" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "";
    var tdd = /Edg\//.test(ua) ? "Edge" : /CriOS|Chrome\//.test(ua) ? "Chrome" : /FxiOS|Firefox\//.test(ua) ? "Firefox"
      : /Safari\//.test(ua) ? "Safari" : "";
    return [may, tdd].filter(Boolean).join(" ");
  }

  async function getJson(url, body) {
    try {
      var r = await fetch(url, body === undefined ? undefined : {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      return await r.json();
    } catch (e) { return {}; }
  }

  function mount(box) {
    if (!box) return;
    box.innerHTML = '<div class="lp-group"><div style="display:flex;align-items:center;gap:8px;margin:22px 0 8px;font-size:15px;color:var(--text);font-weight:600;border-bottom:1px solid var(--hairline);padding-bottom:6px">'
      + "<span>" + ic("shield") + " " + esc(tw("hp.head")) + infoBtn() + "</span>"
      + '<button class="s-btn-ghost" id="hpScan" style="margin-left:auto;font-size:13px">' + esc(tw("hp.scan")) + "</button></div>"
      + infoBody(esc(tw("hp.intro")))
      + '<div id="hpInc"></div><div id="hpIssues" class="si-log"></div>'
      + '<div style="display:flex;align-items:center;gap:8px;margin:18px 0 6px"><h3 style="font-size:14px;color:var(--text);margin:0">'
      + esc(tw("hp.cerr_head")) + "</h3>" + infoBtn()
      + '<button class="s-btn-ghost" id="hpCerrClear" style="margin-left:auto;font-size:13px" hidden>' + esc(tw("hp.cerr_clear")) + "</button></div>"
      + infoBody(esc(tw("hp.cerr_intro")))
      + '<div id="hpCerr" class="si-log"></div></div>';
    var q = function (s) { return box.querySelector(s); };

    async function loadIncidents() {
      var d = await getJson("/incidents");
      var list = (d.incidents || []).filter(function (i) { return i.status !== "resolved"; });
      var host = q("#hpInc");
      if (!host) return;
      host.innerHTML = list.length ? list.map(incidentHtml).join("")
        : '<div class="empty">' + esc(tw("hp.no_incidents")) + "</div>";
      host.querySelectorAll(".hpDone").forEach(function (b) {
        b.onclick = async function () {
          var id = b.closest("[data-id]").dataset.id;
          await getJson("/incidents/resolve", { id: id });
          loadIncidents();
        };
      });
    }
    async function scan() {
      var host = q("#hpIssues");
      if (!host) return;
      host.innerHTML = '<div class="dim">' + esc(tw("common.loading")) + "</div>";
      var d = await getJson("/sentinel/scan");
      var issues = d.issues || [];
      host.innerHTML = '<h3 style="font-size:14px;color:var(--text)">' + esc(tw("hp.issues_head", { h: d.window_h || 24 })) + "</h3>"
        + (issues.length ? issues.map(issueHtml).join("") : '<div class="dim" style="color:var(--text3)">' + esc(tw("hp.no_issues")) + "</div>");
    }
    async function loadClientErrors() {
      var host = q("#hpCerr"), clr = q("#hpCerrClear");
      if (!host) return;
      var d = await getJson("/client-errors");
      var list = d.errors || [];
      host.innerHTML = list.length ? list.map(clientErrorHtml).join("")
        : '<div class="dim" style="color:var(--text3)">' + esc(tw("hp.cerr_none")) + "</div>";
      if (clr) clr.hidden = !list.length;
    }
    q("#hpScan").onclick = scan;
    var clr = q("#hpCerrClear");
    if (clr) clr.onclick = async function () { await getJson("/client-errors/clear", {}); loadClientErrors(); };
    loadIncidents();
    scan();
    loadClientErrors();
  }

  var api_ = { mount: mount, incidentHtml: incidentHtml, issueHtml: issueHtml, clientErrorHtml: clientErrorHtml, shortUa: shortUa };
  if (typeof window !== "undefined") window.JavisHealthPanel = api_;
  if (typeof module !== "undefined" && module.exports) module.exports = api_;
})();
