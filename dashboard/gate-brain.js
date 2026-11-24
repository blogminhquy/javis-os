/* gate-brain.js - the Javis Gate card of the Connections page (#1726, owner 2026-11-24: "ô chọn brain cho Javis Gate
 * anh đồng ý").
 *
 * claude.ai and ChatGPT cannot say which brain they mean, so a call through Javis Gate that names no brain used the
 * brain of the chat touched last, and a user's personal notes landed in a secondary brain. The card holds one select:
 * the brain the Gate uses when the outside AI names none. Its first option, "Brain used last", is the behaviour before
 * the selector and the default, so nothing changes until the owner picks a brain. The rules live in
 * server/gate_brain.py; this file only draws the card (GET /gate/brains) and saves the choice (POST /gate/default-brain).
 * The card is drawn only while the Javis Gate package is installed. Pure helpers are exported for node tests.
 * Never use the em dash here.
 */
(function () {
  "use strict";

  // ---- pure helpers ----
  // The select's options: "Brain used last" (value "") first, then every brain by the name the owner sees. A saved
  // default whose brain was deleted stays listed and selected, marked as deleted, so the select never claims a choice
  // that is not the saved one (the server then falls back to the brain used last).
  function options(state, tr) {
    var st = state || {};
    var cur = String(st["default"] || "");
    var list = [{ value: "", label: tr("gate.brain_last"), selected: !cur }];
    (st.brains || []).forEach(function (b) {
      list.push({ value: String(b.folder), label: String(b.name || b.folder), selected: !!cur && b.folder === cur });
    });
    if (cur && !list.some(function (o) { return o.selected; })) {
      list.push({ value: cur, label: tr("gate.brain_gone", { name: cur }), selected: true });
    }
    return list;
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // `h` = { tr, ic, infoBtn, infoBody }: the page's helpers, passed in so node tests can draw the card.
  function cardHtml(state, h) {
    var tr = h.tr;
    var opts = options(state, tr).map(function (o) {
      return '<option value="' + esc(o.value) + '"' + (o.selected ? " selected" : "") + ">" + esc(o.label) + "</option>";
    }).join("");
    var open = state && state.page
      ? '<a class="gate-open" href="' + esc(state.page) + '" target="_blank" rel="noopener" aria-label="' +
        esc(tr("gate.open_page")) + '" title="' + esc(tr("gate.open_page")) + '">' + h.ic("external-link") + "</a>"
      : "";
    return '<div class="prov-card conn-card gate-card">' +
      '<div class="prov-head"><span class="conn-ico">' + h.ic("log-in") + "</span>" +
      '<div class="prov-info"><div class="prov-name">Javis Gate</div>' +
      '<div class="prov-status j-clamp2">' + esc(tr("gate.card_desc")) + "</div></div>" + open + "</div>" +
      '<div class="gate-brain-row"><span class="gate-brain-lbl"><label for="gateBrainSel">' + esc(tr("gate.brain_label")) +
      "</label>" + h.infoBtn() + "</span>" +
      '<select id="gateBrainSel" class="js-input gate-brain-sel" data-gate-brain>' + opts + "</select></div>" +
      h.infoBody(esc(tr("gate.brain_info"))) +
      '<div class="lv-msg gate-brain-msg" role="status" aria-live="polite" data-gate-msg></div></div>';
  }

  var pure = { options: options, cardHtml: cardHtml };
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
  if (typeof document === "undefined") return;

  function tw(k, v) { return window.t ? window.t(k, v) : k; }
  function ic(n) { return typeof window.ic === "function" ? window.ic(n) : ""; }
  function infoBtn() { return window.JavisInfo ? window.JavisInfo.btn(tw("info.more")) : ""; }
  function infoBody(html) { return window.JavisInfo ? window.JavisInfo.body(html) : '<div class="info-body">' + html + "</div>"; }
  var HELPERS = { tr: tw, ic: ic, infoBtn: infoBtn, infoBody: infoBody };

  var host = null;
  var msgTimer = 0;

  function load() {
    if (!host) return;
    var el = host;
    fetch("/gate/brains", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (st) { if (host === el) draw(st); })
      .catch(function () { if (host === el) el.innerHTML = ""; });
  }

  function draw(st) {
    // No Javis Gate package: nothing to set, so no card (the Store installs it).
    if (!st || !st.ok || !st.installed) { host.innerHTML = ""; return; }
    host.innerHTML = cardHtml(st, HELPERS);
    var sel = host.querySelector("[data-gate-brain]");
    var msg = host.querySelector("[data-gate-msg]");
    if (!sel) return;
    var saved = sel.value;
    // Applies at once, like a checkbox: no separate Save button (docs/dev/design-style.md, section 6).
    sel.onchange = function () {
      var want = sel.value;
      sel.disabled = true;
      fetch("/gate/default-brain", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ brain: want }) })
        .then(function (r) { return r.json().catch(function () { return { ok: false }; }); })
        .catch(function () { return { ok: false }; })
        .then(function (r) {
          sel.disabled = false;
          clearTimeout(msgTimer);
          if (r && r.ok) {
            saved = want;
            if (msg) { msg.className = "lv-msg gate-brain-msg ok"; msg.textContent = tw("gate.saved"); }
            // A confirmation, not an error: it may go once read. Errors stay until the next change.
            msgTimer = setTimeout(function () { if (msg) msg.textContent = ""; }, 2500);
          } else {
            sel.value = saved;
            if (msg) { msg.className = "lv-msg gate-brain-msg"; msg.textContent = (r && r.error) || tw("gate.err_save"); }
          }
        });
    };
  }

  function mount(el) {
    host = el || null;
    if (host) load();
  }

  window.JavisGateBrain = { mount: mount };
})();
