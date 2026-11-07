/* chat-suggest.js - the suggested next message in an empty chat box (2026-11-07).
 *
 * Owner, 2026-11-07: after Claude answers, its empty chat box shows a likely next message in grey ("ok làm theo đề xuất
 * cho cả 2 PR đi") and Tab puts it in the box. Javis does the same:
 *   - when a turn ends the screen calls ctl.request(context); the server (POST /chat/suggest, server/next_prompt.py)
 *     guesses the owner's next message on the background model;
 *   - the guess shows as the placeholder of the EMPTY box, never as text in it, so nothing is sent by accident;
 *   - Tab (or the "Tab" chip next to the box, for a phone) fills the box with it; typing hides it, sending drops it.
 * One module for every chat screen (owner rule of 2026-11-05): the main chat (app.js) and Teams (teams.js) attach it.
 * The switch lives in the composer "+" menu and is stored on the server (settings.chat.suggest_next).
 * Pure parts are exported for node tests.
 */
(function () {
  "use strict";

  // Tab with no modifier, not mid IME composition, the box empty and a suggestion waiting.
  function acceptsKey(e, value, suggestion, composing) {
    if (!e || e.key !== "Tab" || e.shiftKey || e.ctrlKey || e.altKey || e.metaKey || composing) return false;
    return !!suggestion && !String(value || "").trim();
  }

  // The last messages of a chat as the server reads them: oldest first, empty ones dropped, at most 6.
  function shapeContext(list) {
    var out = [];
    (Array.isArray(list) ? list : []).forEach(function (m) {
      if (!m) return;
      var text = String(m.text == null ? "" : m.text).trim();
      if (!text) return;
      out.push({ role: m.role === "user" || m.role === "owner" ? "user" : "assistant", text: text.slice(-4000) });
    });
    return out.slice(-6);
  }

  var pure = { acceptsKey: acceptsKey, shapeContext: shapeContext };
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
  if (typeof document === "undefined") return;

  function tw(k) { try { return window.t ? window.t(k) : k; } catch (e) { return k; } }

  // On/off, read once from the server and shared by every screen.
  var state = { enabled: true, loaded: null };
  var controllers = [];
  function load() {
    if (!state.loaded) {
      state.loaded = fetch("/chat/suggest", { credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { if (d && d.enabled === false) state.enabled = false; })
        .catch(function () {});
    }
    return state.loaded;
  }
  function setEnabled(on) {
    var fd = new FormData();
    fd.append("section", "chat");
    fd.append("data", JSON.stringify({ suggest_next: !!on }));
    return fetch("/settings", { method: "POST", body: fd, credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || d.ok === false) return false;
        state.enabled = !!on;
        if (!on) controllers.forEach(function (c) { c.clear(); });
        return true;
      })
      .catch(function () { return false; });
  }

  /* attach({ input: () => textarea, chipHost: () => [parent, beforeNode] | null, composing: () => bool })
   * returns { request(context), clear(), refresh(), onInput(), onKeydown(e) -> bool, accept() }.
   * `input` is a getter because Teams redraws its composer: refresh() after a redraw puts the suggestion back. */
  function attach(opts) {
    var sug = "", seq = 0, ctl = null, chip = null, shownOn = null, savedPh = "";

    function input() { try { return opts.input(); } catch (e) { return null; } }
    function ensureChip() {
      if (!opts.chipHost) return null;
      var host = null;
      try { host = opts.chipHost(); } catch (e) {}
      if (!host || !host[0]) return null;
      if (!chip) {
        chip = document.createElement("button");
        chip.type = "button";
        chip.className = "sug-tab";
        chip.hidden = true;
        chip.textContent = "Tab";
        // Keep the focus in the box: on a phone the keyboard stays up.
        chip.addEventListener("mousedown", function (e) { e.preventDefault(); });
        chip.addEventListener("click", function () { api.accept(); });
      }
      chip.title = tw("sug.use");
      chip.setAttribute("aria-label", tw("sug.use"));
      if (chip.parentNode !== host[0]) host[0].insertBefore(chip, host[1] || null);
      return chip;
    }
    function hide() {
      if (shownOn) {
        shownOn.placeholder = savedPh;
        shownOn.classList.remove("has-suggest");
        shownOn = null;
      }
      if (chip) chip.hidden = true;
    }
    function show() {
      var el = input();
      if (!el || !sug || !state.enabled || el.disabled || el.value) { hide(); return; }
      if (shownOn !== el) {
        hide();
        savedPh = el.placeholder;
        shownOn = el;
      }
      el.placeholder = sug;
      el.classList.add("has-suggest");
      var c = ensureChip();
      if (c) c.hidden = false;
    }

    var api = {
      request: function (context) {
        api.clear();
        var my = seq;
        var ctx = shapeContext(context);
        if (!ctx.length || ctx[ctx.length - 1].role !== "assistant") return Promise.resolve("");
        return load().then(function () {
          if (!state.enabled || my !== seq) return "";
          ctl = typeof AbortController !== "undefined" ? new AbortController() : null;
          return fetch("/chat/suggest", {
            method: "POST", credentials: "same-origin", signal: ctl ? ctl.signal : undefined,
            headers: { "Content-Type": "application/json" }, body: JSON.stringify({ context: ctx }),
          }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
            if (my !== seq) return "";
            if (d && d.off) state.enabled = false;
            sug = (d && d.text) || "";
            show();
            return sug;
          }).catch(function () { return ""; });
        });
      },
      clear: function () {
        seq++;
        if (ctl) { try { ctl.abort(); } catch (e) {} ctl = null; }
        sug = "";
        hide();
      },
      // After the screen redrew its composer, or switched the language of the placeholder.
      refresh: function () { if (shownOn && !shownOn.isConnected) shownOn = null; show(); },
      onInput: function () { show(); },
      onKeydown: function (e) {
        var el = input();
        var comp = false;
        try { comp = !!(opts.composing && opts.composing()); } catch (x) {}
        if (!el || !acceptsKey(e, el.value, sug, comp || e.isComposing)) return false;
        e.preventDefault();
        api.accept();
        return true;
      },
      accept: function () {
        var el = input();
        if (!el || !sug) return false;
        var text = sug;
        api.clear();
        el.value = text;
        try { el.focus(); el.setSelectionRange(text.length, text.length); } catch (e) {}
        el.dispatchEvent(new Event("input", { bubbles: true }));
        return true;
      },
      current: function () { return sug; },
    };
    // The language switched while a suggestion showed: keep the newly translated placeholder for later.
    window.addEventListener("javis:i18n", function () {
      if (!shownOn) return;
      var ph = shownOn.getAttribute("data-i18n-ph");
      savedPh = ph ? tw(ph) : savedPh;
      show();
    });
    controllers.push(api);
    return api;
  }

  // The switch in the composer "+" menu (one row, its hint says On or Off).
  function registerMenu() {
    if (!window.JavisComposerMenu || !window.JavisComposerMenu.register) return false;
    load();
    window.JavisComposerMenu.register({
      id: "suggest-next", order: 90, label: "sug.menu",
      icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12h12M12 6l6 6-6 6M20 5v14"/></svg>',
      hint: function () { return tw(state.enabled ? "sug.on" : "sug.off"); },
      run: function () { setEnabled(!state.enabled); },
    });
    return true;
  }
  if (!registerMenu()) document.addEventListener("DOMContentLoaded", registerMenu);

  window.JavisSuggest = { attach: attach, setEnabled: setEnabled, enabled: function () { return state.enabled; },
                          acceptsKey: acceptsKey, shapeContext: shapeContext };
})();
