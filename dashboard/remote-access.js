/* remote-access.js - Settings block "Remote access" (0.242.0).
   Turns the built-in Cloudflare Tunnel on or off: a quick trycloudflare.com link, or a fixed link on the owner's own
   domain from a pasted tunnel token. 0.244.0 adds Tailscale: a private ts.net link that only the owner's own devices
   can open, through `tailscale serve` on a Tailscale install the owner made. The server downloads and supervises cloudflared (server/remote_tunnel.py); this
   file only draws /remote-access/status and posts the form. Vanilla DOM, same style family as branding.js. */
(function () {
  "use strict";

  var POLL_STATES = { installing: 1, starting: 1, waiting: 1 };
  var BADGE = { off: "", installing: "warn", starting: "warn", running: "ok", waiting: "warn", error: "bad" };

  var _st = null;        // last /remote-access/status
  var _mode = null;      // mode picked on screen; null = follow the server
  var _token = "";       // what the owner typed, kept across redraws
  var _msg = "";         // result line after a click
  var _msgErr = false;
  var _busy = false;
  var _timer = null;

  function $(id) { return document.getElementById(id); }
  function t(k, v) { return typeof window.t === "function" ? window.t(k, v) : k; }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function icon(name) { return typeof window.ic === "function" ? window.ic(name) : ""; }
  // The (i) helpers; without info-tip.js (Node tests) the text is drawn open so nothing is lost.
  function infoBtn() { return window.JavisInfo ? window.JavisInfo.btn(t("info.more")) : ""; }
  function infoBody(html) { return window.JavisInfo ? window.JavisInfo.body(html) : "<div>" + html + "</div>"; }

  function injectCss() {
    if ($("raCss")) return;
    var s = document.createElement("style");
    s.id = "raCss";
    // 16px text and inputs: easy to read on a phone, and iOS does not zoom into a 16px field.
    s.textContent =
      ".ra{display:flex;flex-direction:column;gap:10px;margin-top:8px;font-size:16px;line-height:1.5}" +
      ".ra-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}" +
      ".ra-modes{display:flex;gap:6px}.ra-modes .gcard-btn{flex:1 1 0;width:auto;font-size:16px;white-space:normal;line-height:1.25;padding-left:6px;padding-right:6px}" +
      ".ra-modes .gcard-btn[aria-pressed=false]{background:var(--surface-2);color:var(--text2);border:1px solid var(--border)}" +
      ".ra-modes .gcard-btn[aria-pressed=true]{background:var(--accent);color:#fff;border:1px solid var(--accent);font-weight:600}" +
      ".ra .info-body ol{margin:6px 0;padding-left:22px}.ra .info-body li{margin:3px 0}" +
      ".ra-hint{color:var(--text3);font-size:16px}" +
      ".ra-warn{color:var(--warn-ink);background:var(--warn-wash);border:1px solid var(--warn-line);border-radius:8px;padding:8px 10px}" +
      ".ra-err{color:var(--red)}" +
      ".ra input{width:100%;box-sizing:border-box;background:var(--field-bg);border:1px solid var(--border);color:var(--text);" +
      "border-radius:7px;padding:9px 10px;font-size:16px}.ra input:focus{outline:none;border-color:var(--accent)}" +
      ".ra-lbl{display:flex;align-items:center;gap:6px;font-weight:600}" +
      ".ra code{background:var(--info-wash);padding:3px 7px;border-radius:5px;font-size:16px;overflow-wrap:anywhere}" +
      ".ra-link{color:var(--green);text-decoration:none;overflow-wrap:anywhere}.ra-link:hover{text-decoration:underline}" +
      ".ra-copy{padding:4px 10px;border:1px solid var(--hairline);border-radius:7px;background:var(--surface-2);color:var(--text);cursor:pointer;font-size:16px}" +
      ".ra-actions{display:flex;gap:6px}.ra-actions .gcard-btn{flex:1 1 0;width:auto;font-size:16px}" +
      ".ra .dom-badge{font-size:16px}" +
      "@media(max-width:600px){.ra-actions{flex-direction:column}.ra-actions .gcard-btn{width:100%}}";
    document.head.appendChild(s);
  }

  function stateLabel(st) {
    var keys = { off: "ra.state_off", installing: "ra.state_installing", starting: "ra.state_starting",
      running: "ra.state_running", waiting: "ra.state_waiting", error: "ra.state_error" };
    return t(keys[st.state] || "ra.state_off");
  }

  function render() {
    var box = $("raBox");
    if (!box) return;
    var inp = $("raToken");
    if (inp) _token = inp.value;
    var st = _st || { state: "off", mode: "quick", password_set: true, can_download: true };
    var mode = _mode || st.mode || "quick";
    var h = "";

    h += '<div class="ra-row"><span class="dom-badge ' + (BADGE[st.state] || "") + '">' + esc(stateLabel(st)) + "</span>";
    if (st.state === "running" && st.url) {
      h += '<a class="ra-link" href="' + esc(st.url) + '" target="_blank" rel="noopener">' + esc(st.url) + " ↗</a>" +
        '<button type="button" class="ra-copy" data-copy="' + esc(st.url) + '">' + esc(t("ra.copy")) + "</button>";
    }
    h += "</div>";
    if (st.state === "running" && !st.url && st.mode === "token") h += '<div class="ra-hint">' + esc(t("ra.no_hostname")) + "</div>";
    (st.service_mismatch || []).forEach(function (svc) {
      h += '<div class="ra-warn">' + esc(t("ra.mismatch", { svc: svc })) + "</div>";
    });

    if (!st.password_set) h += '<div class="ra-warn">' + esc(t("ra.need_password")) + "</div>";
    if (!st.binary && st.can_download === false && mode !== "tailscale") h += '<div class="ra-warn">' + esc(t("ra.no_build")) + "</div>";

    h += '<div class="ra-modes" role="group">' +
      '<button type="button" class="gcard-btn" data-mode="quick" aria-pressed="' + (mode === "quick") + '">' + esc(t("ra.mode_quick")) + "</button>" +
      '<button type="button" class="gcard-btn" data-mode="token" aria-pressed="' + (mode === "token") + '">' + esc(t("ra.mode_token")) + "</button>" +
      '<button type="button" class="gcard-btn" data-mode="tailscale" aria-pressed="' + (mode === "tailscale") + '">' + esc(t("ra.mode_tailscale")) + "</button></div>";
    var hints = { quick: "ra.quick_hint", token: "ra.token_hint", tailscale: "ra.ts_hint" };
    h += '<div class="ra-hint">' + esc(t(hints[mode] || "ra.quick_hint")) + "</div>";

    if (mode === "token") {
      h += '<div class="ra-lbl"><label for="raToken">' + esc(t("ra.token_label")) + "</label>" + infoBtn() + "</div>" +
        infoBody("<b>" + esc(t("ra.steps_title")) + "</b><ol><li>" + esc(t("ra.step1")) + "</li><li>" + esc(t("ra.step2")) +
          "</li><li>" + esc(t("ra.step3")) + "</li><li>" + esc(t("ra.step4")) + "</li></ol>" +
          '<a href="https://one.dash.cloudflare.com" target="_blank" rel="noopener">one.dash.cloudflare.com ↗</a>') +
        '<input id="raToken" type="password" autocomplete="off" spellcheck="false" placeholder="' + esc(t("ra.token_ph")) + '">';
      if (st.has_token) h += '<div class="ra-hint">' + esc(t("ra.token_saved", { id: st.tunnel_id || "" })) + "</div>";
      if (st.target) {
        var addr = String(st.target).replace(/^https?:\/\//, "");
        h += '<div class="ra-hint">' + esc(t("ra.target_label")) + "</div>" +
          '<div class="ra-row"><code>' + esc(addr) + '</code><button type="button" class="ra-copy" data-copy="' + esc(addr) + '">' +
          esc(t("ra.copy")) + "</button></div>";
      }
    }

    var ts = st.tailscale || {};
    if (mode === "tailscale") {
      h += '<div class="ra-lbl"><span>' + esc(t("ra.ts_title")) + "</span>" + infoBtn() + "</div>" +
        infoBody("<b>" + esc(t("ra.ts_steps_title")) + "</b><ol><li>" + esc(t("ra.ts_step1")) + "</li><li>" + esc(t("ra.ts_step2")) +
          "</li><li>" + esc(t("ra.ts_step3")) + "</li><li>" + esc(t("ra.ts_step4")) + "</li></ol>" +
          '<a href="https://tailscale.com/download" target="_blank" rel="noopener">tailscale.com/download ↗</a>');
      if (!ts.installed) {
        h += '<div class="ra-warn">' + esc(t("ra.ts_missing")) + ' <a href="https://tailscale.com/download" target="_blank" rel="noopener">' +
          esc(t("ra.ts_download")) + " ↗</a></div>";
      } else if (ts.backend !== "Running") {
        h += '<div class="ra-warn">' + esc(t("ra.ts_login")) + "</div>";
      } else if (ts.dns_name) {
        h += '<div class="ra-hint">' + esc(t("ra.ts_device", { name: ts.dns_name })) + "</div>";
      }
      if (st.enable_url && st.mode === "tailscale") {
        h += '<div class="ra-warn">' + esc(t("ra.ts_enable_https")) + ' <a href="' + esc(st.enable_url) +
          '" target="_blank" rel="noopener">' + esc(t("ra.ts_open_enable")) + " ↗</a></div>";
      }
      if (st.state === "running" && st.mode === "tailscale") h += '<div class="ra-hint">' + esc(t("ra.ts_only_tailnet")) + "</div>";
    }

    var err = st.error && (st.state === "error" || st.state === "waiting") ? st.error : "";
    var line = _msg || err;
    if (line) h += '<div class="' + (_msgErr || (!_msg && err) ? "ra-err" : "ra-hint") + '" role="status">' + esc(line) + "</div>";

    var tsBlocked = mode === "tailscale" && (!ts.installed || ts.backend !== "Running") && !st.enabled;
    var disabled = _busy || !st.password_set || tsBlocked ? " disabled" : "";
    if (st.enabled) {
      h += '<div class="ra-actions"><button type="button" class="gcard-btn" id="raOn"' + disabled + ">" + esc(t("ra.reconnect")) + "</button>" +
        '<button type="button" class="gcard-btn ghost" id="raOff"' + (_busy ? " disabled" : "") + ">" + esc(t("ra.disable")) + "</button></div>";
    } else {
      h += '<div class="ra-actions"><button type="button" class="gcard-btn" id="raOn"' + disabled + ">" + esc(t("ra.enable")) + "</button></div>";
    }

    box.innerHTML = h;
    var ni = $("raToken");
    if (ni) ni.value = _token;
  }

  function schedule() {
    clearTimeout(_timer);
    if (_st && POLL_STATES[_st.state] && !document.hidden) _timer = setTimeout(load, 2500);
  }

  async function load() {
    try {
      var r = await fetch("/remote-access/status");
      var j = await r.json().catch(function () { return null; });
      if (r.ok && j) _st = j;
    } catch (e) { /* offline: keep the last drawing */ }
    render();
    schedule();
  }

  async function post(url, fd) {
    _busy = true; _msg = t("ra.working"); _msgErr = false;
    render();
    try {
      var r = await fetch(url, { method: "POST", body: fd || new FormData() });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok || !j.ok) { _msg = j.error || t("ra.net_err"); _msgErr = true; return false; }
      _st = j; _msg = ""; _msgErr = false;
      return true;
    } catch (e) {
      _msg = t("ra.net_err"); _msgErr = true;
      return false;
    } finally {
      _busy = false;
      render();
      schedule();
    }
  }

  async function turnOn() {
    var mode = _mode || (_st && _st.mode) || "quick";
    var fd = new FormData();
    fd.append("mode", mode);
    var inp = $("raToken");
    if (mode === "token" && inp && inp.value.trim()) fd.append("token", inp.value.trim());
    if (await post("/remote-access/enable", fd)) { _token = ""; render(); }
  }

  async function turnOff() {
    if (await post("/remote-access/disable")) { _msg = t("ra.disabled_ok"); render(); }
  }

  function bind() {
    injectCss();
    var box = $("raBox");
    if (!box) return;
    box.addEventListener("click", async function (e) {
      var m = e.target.closest("[data-mode]");
      if (m) { _mode = m.getAttribute("data-mode"); _msg = ""; render(); return; }
      if (e.target.closest("#raOn")) { turnOn(); return; }
      if (e.target.closest("#raOff")) { turnOff(); return; }
      var c = e.target.closest("[data-copy]");
      if (c) {
        try {
          await navigator.clipboard.writeText(c.getAttribute("data-copy") || "");
          var old = c.textContent;
          c.innerHTML = esc(t("ra.copied")) + " " + icon("check");
          setTimeout(function () { c.textContent = old; }, 1300);
        } catch (err) { /* clipboard blocked: the text stays visible to copy by hand */ }
      }
    });
    box.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && e.target && e.target.id === "raToken") { e.preventDefault(); turnOn(); }
    });
    document.addEventListener("visibilitychange", function () { if (!document.hidden) schedule(); });
    // Settings calls __javisRefreshExtras (branding.js) when its General tab opens: refresh this block with it.
    var prev = window.__javisRefreshExtras;
    window.__javisRefreshExtras = function () {
      try { if (prev) prev.apply(this, arguments); } finally { load(); }
    };
    load();
  }

  window.addEventListener("javis:i18n", function () { if (_st) render(); });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
  else bind();
})();
