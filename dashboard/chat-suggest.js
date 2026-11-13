/* chat-suggest.js - the suggested next message in the chat box (2026-11-07, typing along 2026-11-13).
 *
 * Owner, 2026-11-07: after Claude answers, its empty chat box shows a likely next message in grey ("ok làm theo đề xuất
 * cho cả 2 PR đi") and Tab puts it in the box. Javis does the same:
 *   - when a turn ends the screen calls ctl.request(context); the server (POST /chat/suggest, server/next_prompt.py)
 *     guesses the owner's next message on the background model;
 *   - the guess shows as the placeholder of the EMPTY box, never as text in it, so nothing is sent by accident;
 *   - Tab (or the "Tab" chip next to the box, for a phone) fills the box with it; sending drops it.
 *
 * 2026-11-13, a user's wish passed on by the owner: the suggestion vanished at the first key typed. "Gõ đến chữ nào
 * thì đề xuất sau vẫn giữ nguyên để gõ tiếp", and better, "suy đoán tiếp nội dung gõ sau khi người dùng muốn điều
 * chỉnh, kiểu chức năng dự đoán thông minh trên iPhone". So:
 *   - typing ALONG the suggestion keeps the rest of it in grey right after the typed text (case and Vietnamese marks
 *     do not count, so a half typed "su" still follows "sửa"); Tab or the chip takes the rest, Right Arrow at the end
 *     of the text takes one word;
 *   - typing something ELSE asks the server, after a short pause, to finish that sentence ({draft, hint}); the answer
 *     shows the same way. The server says how patiently to ask (`live`: the pause and how many per turn).
 * The grey rest is a mirror layer over the box (same font, padding and width), the trick chat-slash.js uses for
 * command colours: a <textarea> cannot colour part of its own text.
 *
 * One module for every chat screen (owner rule of 2026-11-05): the main chat (app.js) and Teams (teams.js) attach it.
 * The switch lives in the composer "+" menu and is stored on the server (settings.chat.suggest_next).
 * Pure parts are exported for node tests.
 */
(function () {
  "use strict";

  var MAX_DRAFT = 200;   // mirrors next_prompt.MAX_DRAFT_CHARS

  function nfc(s) {
    s = String(s == null ? "" : s);
    try { return s.normalize("NFC"); } catch (e) { return s; }
  }
  // For comparing typed text with a suggestion: case and the marks of Latin letters do not count. One character in,
  // one out, so a position in the folded text is a position in the NFC text.
  function fold(s) {
    var t = nfc(s), out = "";
    for (var i = 0; i < t.length; i++) {
      var c = t[i], low = c.toLowerCase(), base = low;
      try { base = low.normalize("NFD").charAt(0); } catch (e) {}
      if (base === "\u0111") base = "d";   // d with stroke has no decomposition
      out += base >= "a" && base <= "z" ? base : (low.length === 1 ? low : c);
    }
    return out;
  }
  // What `full` adds after `value`, or "" when `value` is not the start of it. An empty box gets all of it.
  function restOf(value, full) {
    var v = nfc(value), f = nfc(full);
    if (!f || v.length >= f.length) return "";
    return fold(f).slice(0, v.length) === fold(v) ? f.slice(v.length) : "";
  }
  // The next word of the rest, with the space before it.
  function nextWord(rest) {
    var m = /^\s*\S+/.exec(String(rest || ""));
    return m ? m[0] : String(rest || "");
  }
  function plainKey(e, key) {
    return !!e && e.key === key && !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey;
  }

  // Tab with no modifier, not mid IME composition, and the suggestion continues what is in the box (or the box is
  // empty). Anything else is an ordinary Tab.
  function acceptsKey(e, value, suggestion, composing) {
    return plainKey(e, "Tab") && !composing && !!restOf(value, suggestion);
  }
  // Right Arrow takes ONE word, only with the caret at the very end of the text (where it could not move anyway).
  function acceptsWordKey(e, box, suggestion, composing) {
    if (!plainKey(e, "ArrowRight") || composing || !box) return false;
    var v = String(box.value || "");
    if (box.selectionStart != null && (box.selectionStart !== v.length || box.selectionEnd !== v.length)) return false;
    return !!restOf(v, suggestion);
  }
  // Worth asking the server to finish: one line, not too long, at least two letters.
  function liveDraft(value) {
    var v = String(value || "");
    return v.length <= MAX_DRAFT && v.trim().indexOf("\n") < 0 && v.replace(/\s/g, "").length >= 2;
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

  var pure = { acceptsKey: acceptsKey, acceptsWordKey: acceptsWordKey, shapeContext: shapeContext, fold: fold,
               restOf: restOf, nextWord: nextWord, liveDraft: liveDraft };
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
  if (typeof document === "undefined") return;

  function tw(k) { try { return window.t ? window.t(k) : k; } catch (e) { return k; } }

  // On/off and the pace of live completions ({wait_ms, max} or null), read once from the server and shared by every
  // screen. Each suggestion answer refreshes the pace (a key added on the Models page shows up without a reload).
  var state = { enabled: true, live: null, loaded: null };
  var controllers = [];
  function load() {
    if (!state.loaded) {
      state.loaded = fetch("/chat/suggest", { credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          if (d && d.enabled === false) state.enabled = false;
          if (d && d.live) state.live = d.live;
        })
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
  function post(body, signal) {
    return fetch("/chat/suggest", {
      method: "POST", credentials: "same-origin", signal: signal,
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }).then(function (r) { return r.ok ? r.json() : null; });
  }
  function aborter() { return typeof AbortController !== "undefined" ? new AbortController() : null; }

  // Copied from the box onto the mirror layer so both wrap the same way.
  var MIRROR = ["fontFamily", "fontSize", "fontWeight", "fontStyle", "lineHeight", "letterSpacing", "wordSpacing",
    "textIndent", "textTransform", "textAlign", "direction", "paddingTop", "paddingRight", "paddingBottom",
    "paddingLeft", "tabSize"];

  /* attach({ input: () => textarea, chipHost: () => [parent, beforeNode] | null, composing: () => bool,
   *          maxHeight: () => px (how tall the screen lets the box grow), quiet: () => bool (dictating: do not ask) })
   * returns { request(context), clear(), refresh(), onInput(), onKeydown(e) -> bool, accept(wordOnly) }.
   * `input` is a getter because Teams redraws its composer: refresh() after a redraw puts the suggestion back.
   * The screen calls onInput() AFTER it has sized the box to its text. */
  function attach(opts) {
    var sug = "";             // the guess made when the turn ended
    var live = "";            // the latest finished draft, as a whole sentence
    var seq = 0, ctl = null, chip = null, shownOn = null, savedPh = "";
    var ctx = null;           // the chat the guesses are about; null until a turn ends, and after a send
    var liveCtl = null, liveTimer = 0, liveBusy = false, liveUsed = 0, asked = {};
    var ghost = null, typedEl = null, restEl = null, ghostOn = null;
    var baseH = null, grownH = "";   // the box height before the grey rest made it taller, and the height we set

    function input() { try { return opts.input(); } catch (e) { return null; } }
    function isComposing() { try { return !!(opts.composing && opts.composing()); } catch (e) { return false; } }
    function isQuiet() { try { return !!(opts.quiet && opts.quiet()); } catch (e) { return false; } }
    // The sentence on offer for what is in the box: an empty box gets the turn's guess, text gets whichever
    // sentence it is the start of (the newest first).
    function pick(value) {
      if (!value) return sug;
      if (live && restOf(value, live)) return live;
      return sug && restOf(value, sug) ? sug : "";
    }

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

    // ---- the mirror layer: the grey rest after typed text, and room for a long suggestion ----
    function capOf(el) {
      var cap = 0;
      try { cap = Number(opts.maxHeight && opts.maxHeight()) || 0; } catch (e) {}
      if (!cap && typeof getComputedStyle === "function") cap = parseFloat(getComputedStyle(el).maxHeight) || 0;
      return cap || 1e6;
    }
    function shrinkBack(el) {
      // Only when the height is still the one set here: the screen may have sized the box again since.
      if (baseH !== null && el && el.style && el.style.height === grownH) el.style.height = baseH;
      baseH = null; grownH = "";
    }
    function hideGhost() {
      if (ghost) ghost.hidden = true;
      if (ghostOn) shrinkBack(ghostOn);
      ghostOn = null;
    }
    // The screen can change the box with no input event (it sets .value after a send, a resized window re-wraps the
    // text). Told right then, with no timer running while a suggestion just sits there: .value is wrapped on this one
    // element (what React does to follow an input), and a ResizeObserver watches its size.
    function follow(el) {
      if (el._sugFollow) return;
      el._sugFollow = true;
      if (el.addEventListener) {
        el.addEventListener("scroll", function () { if (ghost && ghostOn === el) ghost.scrollTop = el.scrollTop; });
      }
      try {
        var proto = Object.getPrototypeOf(el), d = proto && Object.getOwnPropertyDescriptor(proto, "value");
        if (d && d.get && d.set) {
          Object.defineProperty(el, "value", {
            configurable: true, enumerable: d.enumerable,
            get: function () { return d.get.call(this); },
            set: function (v) { d.set.call(this, v); if (sug || live || shownOn === el) show(); },
          });
        }
      } catch (e) {}
      if (typeof ResizeObserver === "function") {
        try {
          var seen = "";
          new ResizeObserver(function () {
            var now = el.clientWidth + "x" + el.clientHeight;
            if (now !== seen && shownOn === el) show();
            seen = el.clientWidth + "x" + el.clientHeight;
          }).observe(el);
        } catch (e) {}
      }
    }
    /* Lay `typed` + `rest` out exactly as the box would. With text in the box the rest shows in grey after it. In an
     * empty box the suggestion is the box's own placeholder, and the layer only measures it (`visible` false), so a
     * suggestion of several lines is not cut at the first one. */
    function drawGhost(el, typed, rest, visible) {
      var host = el.parentNode;
      if (!host) { hideGhost(); return; }
      if (!ghost) {
        ghost = document.createElement("div");
        ghost.setAttribute("aria-hidden", "true");
        typedEl = document.createElement("span");
        typedEl.className = "sug-ghost-typed";
        restEl = document.createElement("span");
        restEl.className = "sug-ghost-rest";
        ghost.appendChild(typedEl);
        ghost.appendChild(restEl);
      }
      ghost.className = visible ? "sug-ghost" : "sug-ghost sug-ghost-measure";
      // Right after the box, so it paints over a box that has its own background (Teams).
      if (ghost.parentNode !== host || ghost.previousSibling !== el) host.insertBefore(ghost, el.nextSibling || null);
      if (ghostOn && ghostOn !== el) shrinkBack(ghostOn);
      ghostOn = el;
      follow(el);
      typedEl.textContent = typed;
      restEl.textContent = rest;
      ghost.hidden = false;
      if (typeof getComputedStyle !== "function" || !ghost.style) return;
      var cs = getComputedStyle(el);
      MIRROR.forEach(function (p) { ghost.style[p] = cs[p]; });
      shrinkBack(el);
      ghost.style.width = el.clientWidth + "px";
      ghost.style.height = "auto";
      // The rest may wrap below the typed text: the box grows to show it, within the screen's own limit.
      var need = ghost.offsetHeight, edge = el.offsetHeight - el.clientHeight;
      if (need > el.clientHeight + 1) {
        var h = Math.min(need + edge, capOf(el));
        if (h > el.offsetHeight) {
          baseH = el.style.height;
          el.style.height = h + "px";
          grownH = el.style.height;
        }
      }
      ghost.style.top = (el.offsetTop + el.clientTop) + "px";
      ghost.style.left = (el.offsetLeft + el.clientLeft) + "px";
      ghost.style.width = el.clientWidth + "px";
      ghost.style.height = el.clientHeight + "px";
      ghost.scrollTop = el.scrollTop;
    }

    function hide() {
      if (shownOn) {
        shownOn.placeholder = savedPh;
        shownOn.classList.remove("has-suggest");
        shownOn = null;
      }
      if (chip) chip.hidden = true;
      hideGhost();
    }
    function show() {
      var el = input();
      var full = el && state.enabled && !el.disabled ? pick(el.value) : "";
      if (!full) { hide(); return; }
      if (shownOn !== el) {
        hide();
        savedPh = el.placeholder;
        shownOn = el;
      }
      el.classList.add("has-suggest");
      // The chip first: in Teams it shares the row with the box, so it changes the width the text wraps at.
      var c = ensureChip();
      if (c) c.hidden = false;
      if (el.value) {
        el.placeholder = savedPh;
        drawGhost(el, el.value, restOf(el.value, full), true);
      } else {
        el.placeholder = full;
        drawGhost(el, "", full, false);
      }
    }

    // ---- finishing a draft that left the suggestion ----
    function liveWanted(el) {
      if (!el || !state.enabled || !state.live || !ctx || el.disabled) return false;
      if (liveUsed >= (state.live.max || 0) || !liveDraft(el.value) || asked[el.value] || pick(el.value)) return false;
      if (el.selectionStart != null && el.selectionStart !== el.value.length) return false;
      return document.activeElement === el && !isQuiet();
    }
    function planLive() {
      clearTimeout(liveTimer);
      liveTimer = 0;
      if (liveWanted(input())) liveTimer = setTimeout(askLive, state.live.wait_ms || 600);
    }
    function askLive() {
      liveTimer = 0;
      var el = input();
      // One at a time: the answer on its way plans the next one itself.
      if (liveBusy || !liveWanted(el)) return;
      // Mid composition (a Vietnamese or Japanese IME) the text is not final yet: look again after the same pause.
      if (isComposing()) { planLive(); return; }
      var draft = el.value, my = seq;
      liveBusy = true;
      liveUsed++;
      asked[draft] = 1;
      liveCtl = aborter();
      post({ context: ctx, draft: draft, hint: sug }, liveCtl ? liveCtl.signal : undefined).then(function (d) {
        if (my !== seq) return;
        liveBusy = false;
        if (d && d.off) state.enabled = false;
        if (d && d.busy) liveUsed--;   // the server was finishing another draft: this one cost nothing
        // The server's own spelling of the whole sentence when it lines up with what was typed ("chi danh dau"
        // typed, "chỉ đánh dấu" written), else the typed text with the rest after it.
        if (d && d.text) live = d.full && restOf(draft, d.full) ? d.full : draft + d.text;
        show();
        planLive();
      }).catch(function () { if (my === seq) liveBusy = false; });
    }

    var api = {
      request: function (context) {
        api.clear();
        var my = seq;
        var shaped = shapeContext(context);
        if (!shaped.length || shaped[shaped.length - 1].role !== "assistant") return Promise.resolve("");
        return load().then(function () {
          if (!state.enabled || my !== seq) return "";
          ctx = shaped;
          ctl = aborter();
          return post({ context: shaped }, ctl ? ctl.signal : undefined).then(function (d) {
            if (my !== seq) return "";
            if (d && d.off) state.enabled = false;
            if (d && "live" in d) state.live = d.live || null;
            sug = (d && d.text) || "";
            show();
            planLive();
            return sug;
          }).catch(function () { return ""; });
        });
      },
      clear: function () {
        seq++;
        if (ctl) { try { ctl.abort(); } catch (e) {} ctl = null; }
        if (liveCtl) { try { liveCtl.abort(); } catch (e) {} liveCtl = null; }
        clearTimeout(liveTimer);
        liveTimer = 0; liveBusy = false; liveUsed = 0; asked = {};
        ctx = null; sug = ""; live = "";
        hide();
      },
      // After the screen redrew its composer, or switched the language of the placeholder.
      refresh: function () { if (shownOn && !shownOn.isConnected) shownOn = null; show(); },
      // The screen has just sized the box to its text, so a height set here earlier is gone.
      onInput: function () { baseH = null; grownH = ""; show(); planLive(); },
      onKeydown: function (e) {
        var el = input();
        if (!el) return false;
        var comp = isComposing() || !!e.isComposing;
        var full = pick(el.value);
        var word = !acceptsKey(e, el.value, full, comp) && acceptsWordKey(e, el, full, comp);
        if (!word && !acceptsKey(e, el.value, full, comp)) return false;
        e.preventDefault();
        api.accept(word);
        return true;
      },
      // Put the suggestion in the box: all of it, or (wordOnly) just its next word. Text typed along with other
      // marks or case ("em sua") becomes the suggestion's own spelling.
      accept: function (wordOnly) {
        var el = input();
        var full = el ? pick(el.value) : "";
        var rest = full ? restOf(el.value, full) : "";
        if (!rest) return false;
        var text = wordOnly ? full.slice(0, full.length - rest.length + nextWord(rest).length) : full;
        if (text.length >= full.length) {
          // Taken whole: nothing more to offer for this turn, but a draft typed after it can still be finished.
          sug = ""; live = "";
          hide();
        }
        el.value = text;
        try { el.focus(); el.setSelectionRange(text.length, text.length); } catch (e) {}
        show();
        // The screen sizes the box to the new text and calls onInput(), which lays the rest out again.
        el.dispatchEvent(new Event("input", { bubbles: true }));
        return true;
      },
      current: function () { return sug; },
      // What Tab would add right now ("" when nothing is on offer).
      showing: function () { var el = input(); return el ? restOf(el.value, pick(el.value)) : ""; },
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
                          acceptsKey: acceptsKey, acceptsWordKey: acceptsWordKey, shapeContext: shapeContext,
                          restOf: restOf };
})();
