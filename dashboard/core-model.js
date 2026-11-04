// core-model.js: the model row on the Javis Core card of the Agents page (0.461.0).
//
// Javis Core follows the main model until it is pinned. Before this row the card said nothing about its model, so an
// empty slot read as "Javis Core has no model" (owner, 04/11/2026). The row names what Core really runs on and lets
// the owner pin it, writing the SAME pin as the model bar of a Core chat (POST /javis-core/model on the server, which
// shares `_set_core_pin` with POST /sessions/{id}/model). Two places, one value: they can never disagree.
//
// The list body is model-list.js, the same as the chat model bar and the assistant editor; only the shell is here.
// After a change it fires `javis:core-model` so an open Core chat redraws its model chip, and it redraws itself when
// the model bar fires the same event.
(function () {
  "use strict";

  var t = function (k, v) { return (window.t ? window.t(k, v) : k); };
  var ic = function (n, o) { return (window.ic ? window.ic(n, o) : ""); };
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }
  var EVENT = "javis:core-model";

  // "Claude Code · Opus 5.5". No model means the provider's own default: the server tells which one when it knows.
  function label(providers, defaults, pid, model) {
    var p = (providers || []).find(function (x) { return x.id === pid; }) || {};
    var pretty = window.JavisModelBar && window.JavisModelBar.prettyModel
      ? window.JavisModelBar.prettyModel : function (m) { return m; };
    var m = model || (defaults || {})[pid] || "";
    return (p.label || pid || "") + (m ? " · " + pretty(m) : "");
  }

  // Pure: the button text and the short line under it, from GET /javis-core/model. Exported for the node test.
  function texts(v, providers, defaults) {
    v = v || {};
    var run = label(providers, defaults, v.run_provider, v.run_model);
    if (!v.pinned) {
      var main = label(providers, defaults, v.main_provider, v.main_model);
      return { button: t("ws.core_model_follow", { m: main }),
               sub: v.run_provider && v.run_provider !== v.main_provider ? t("ws.core_model_main_down", { m: run }) : "",
               follow: false };
    }
    var pin = label(providers, defaults, v.pinned_provider, v.pinned_model);
    return { button: pin,
             sub: v.pin_ok === false ? t("ws.core_model_broken", { m: run }) : t("ws.core_model_pinned"),
             follow: true };
  }

  var ROW_HTML = function () {
    var J = window.JavisInfo;
    return '<div class="ws-core-model agent-editor">' +
      '<label for="wsCoreModelBtn">Model' + (J ? J.btn(t("info.more")) : "") + "</label>" +
      (J ? J.body(esc(t("ws.core_model_info"))) : "") +
      '<div class="ag-model-pick" id="wsCoreModelPick">' +
      '<button type="button" class="ag-model-btn" id="wsCoreModelBtn"><span id="wsCoreModelTxt">' + esc(t("mpick.loading")) +
      "</span>" + ic("chevron-down") + "</button>" +
      '<div class="mb-pop ag-model-pop" id="wsCoreModelPop" hidden></div></div>' +
      '<div class="ws-core-model-sub" id="wsCoreModelSub" hidden><span></span>' +
      '<button type="button" class="ws-btn" id="wsCoreFollow" hidden>' + ic("rotate-cw") + " " +
      esc(t("mpick.follow_main")) + "</button></div></div>";
  };

  function mount(host) {
    if (!host) return;
    host.innerHTML = ROW_HTML();
    var btn = host.querySelector("#wsCoreModelBtn"), pop = host.querySelector("#wsCoreModelPop");
    var txt = host.querySelector("#wsCoreModelTxt"), sub = host.querySelector("#wsCoreModelSub");
    var follow = host.querySelector("#wsCoreFollow"), pick = host.querySelector("#wsCoreModelPick");
    var st = { view: null, providers: [], defaults: {}, expanded: "", filter: "" };

    function draw() {
      var x = texts(st.view, st.providers, st.defaults);
      txt.textContent = x.button;
      sub.hidden = !x.sub && !x.follow;
      sub.querySelector("span").textContent = x.sub;
      follow.hidden = !x.follow;
    }
    async function load() {
      try {
        var r = await Promise.all([fetch("/javis-core/model").then(function (q) { return q.json(); }),
                                   fetch("/settings").then(function (q) { return q.json(); })]);
        var m = (r[1] && r[1].model) || {};
        st.view = r[0]; st.providers = m.providers || []; st.defaults = (m.routing || {}).defaults || {};
      } catch (e) { /* keep what is drawn: a failed read must not blank the card */ }
      if (host.isConnected) draw();
    }
    async function save(prov, model) {
      var f = new FormData();
      f.append("provider", prov || "");
      f.append("model", model || "");
      try {
        var r = await fetch("/javis-core/model", { method: "POST", body: f });
        var d = await r.json();
        if (d && d.ok) st.view = d;
      } catch (e) {}
      draw();
      try { window.dispatchEvent(new CustomEvent(EVENT, { detail: { from: "agents" } })); } catch (e) {}
    }
    async function drawPop() {
      var v = st.view || {};
      var cur = !v.pinned;
      var top = '<div class="mb-item ' + (cur ? "cur" : "") + '" data-prov="" data-model="">' +
        '<span class="tick">' + (cur ? ic("check", { cls: "ic-ok" }) : "") + "</span>" +
        "<span>" + esc(t("mpick.follow_main")) + "</span></div>";
      var o = {
        providers: st.providers, expanded: st.expanded, filter: st.filter,
        selected: v.pinned ? { provider: v.pinned_provider, model: v.pinned_model || "" } : { provider: "", model: "" },
        searchId: "wsCoreModelSearch", extraTop: top, noWait: true,
        connectedOnly: true,   // same list as the chat model bar: a Core chat can only run on a connected provider
      };
      var f = st.filter;
      pop.innerHTML = await window.JavisModelList.render(o);
      if (o.cho && o.cho.length) Promise.all(o.cho).then(function () { if (!pop.hidden && f === st.filter) drawPop(); });
      var se = host.querySelector("#wsCoreModelSearch");
      if (se) {
        se.oninput = function () { st.filter = se.value; drawPop(); };
        var touch = false;
        try { touch = window.matchMedia("(pointer: coarse)").matches; } catch (e) {}
        if (!touch || document.activeElement === se) { se.focus(); se.selectionStart = se.selectionEnd = se.value.length; }
      }
    }
    btn.onclick = async function () {
      if (!pop.hidden) { pop.hidden = true; return; }
      if (!window.JavisModelList) return;
      var v = st.view || {};
      st.expanded = (v.pinned ? v.pinned_provider : v.main_provider) || "";
      st.filter = "";
      pop.hidden = false;
      await drawPop();
      try { pop.scrollIntoView({ block: "nearest" }); } catch (e) {}
    };
    pop.onclick = async function (e) {
      var go = e.target.closest("[data-goto]");
      if (go) {
        pop.hidden = true;
        try { if (window.Alpine) window.Alpine.store("nav").go(go.dataset.goto); } catch (er) {}
        return;
      }
      var it = e.target.closest(".mb-item");
      if (it) { pop.hidden = true; await save(it.dataset.prov || "", it.dataset.model || ""); return; }
      var pr = e.target.closest(".mb-prov");
      if (pr && pr.dataset.prov) { st.expanded = st.expanded === pr.dataset.prov ? "" : pr.dataset.prov; drawPop(); }
    };
    follow.onclick = function () { save("", ""); };
    // Click outside or Escape closes the list. Both listeners remove themselves once the card is redrawn.
    function outside(e) {
      if (!pop.isConnected) { document.removeEventListener("click", outside); return; }
      var path = e.composedPath ? e.composedPath() : [e.target];
      if (!pop.hidden && path.indexOf(pick) < 0) pop.hidden = true;
    }
    function onEsc(e) {
      if (!pop.isConnected) { document.removeEventListener("keydown", onEsc); return; }
      if (e.key === "Escape" && !pop.hidden) { pop.hidden = true; e.stopPropagation(); }
    }
    function onChange(e) {
      if (!host.isConnected || !host.contains(btn)) { window.removeEventListener(EVENT, onChange); return; }
      if (!(e && e.detail && e.detail.from === "agents")) load();
    }
    document.addEventListener("click", outside);
    document.addEventListener("keydown", onEsc);
    window.addEventListener(EVENT, onChange);
    load();
  }

  window.JavisCoreModel = { mount: mount, texts: texts, EVENT: EVENT };
})();
