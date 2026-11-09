/* editor-dictate.js - a mic in the file editors: speak, the words land where the cursor is (2026-11-09).

   Customer request (Star Global, 09/11/2026): rewriting an email draft by hand is slow, the editor should have the
   same "speak instead of type" mic as the chat box. This is that mic, not a new recognizer: the speech work is
   dictate.js (Web Speech live text, the server ear on stop, then POST /stt/fix rewrites the sentence in context), and
   this file only places the words in an editor.

   - Rendered (WYSIWYG) editor: the words go in at the caret, inside a marked span while speaking (a computer shows
     them live; a phone gets them at the end, as in the chat). The span becomes plain text when the recording ends.
   - Plain textarea (source view, .txt and other text files): the same, by selection offsets.
   - The editor is read-only while recording, so typing cannot land inside the words being written.
   - X is not needed: pressing the button again stops and keeps the words. Five minutes is the limit, as in the chat.

   insertPlain is pure so node tests can run it. */
(function () {
  "use strict";

  var MAX_MS = 300000;

  function tw(k) { return (typeof window !== "undefined" && window.t) ? window.t(k) : k; }
  function ic(n) { return (typeof window !== "undefined" && window.ic) ? window.ic(n) : ""; }

  // The textarea value with `spoken` placed between `before` and `after`, one space on each side where the words
  // would otherwise touch. Returns {value, caret}.
  function insertPlain(before, spoken, after) {
    before = String(before == null ? "" : before);
    after = String(after == null ? "" : after);
    spoken = String(spoken == null ? "" : spoken).trim();
    if (!spoken) return { value: before + after, caret: before.length };
    var head = before && !/\s$/.test(before) ? before + " " : before;
    var mid = head + spoken;
    var tail = after && !/^[\s.,!?;:)]/.test(after) ? " " + after : after;
    return { value: mid + tail, caret: mid.length };
  }

  // The last few lines of text before the cursor, for the rewrite's context.
  function contextLines(text) {
    return String(text || "").split(/\n+/).map(function (s) { return s.trim(); })
      .filter(Boolean).slice(-4).map(function (s) { return s.length > 300 ? s.slice(-300) : s; });
  }

  var toast = null, toastTimer = 0;
  function note(text, isError) {
    if (typeof document === "undefined") return;
    if (!toast) { toast = document.createElement("div"); toast.className = "ni-status"; document.body.appendChild(toast); }
    toast.textContent = text;
    toast.className = "ni-status show" + (isError ? " ni-err" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { if (toast) toast.className = "ni-status"; }, isError ? 6000 : 2500);
  }

  // o: host (where the button goes; placed before .ne-count when there is one), target() -> {kind: "wys"|"ta", el}
  // for the box in use now, onChange() after the words land (autosave, word count). Returns {button, stop, destroy}.
  function attach(o) {
    var D = typeof window !== "undefined" && window.JavisDictate;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ne-mic";
    var st = "idle", dict = null, heard = "", spot = null, limit = 0;

    function paint() {
      btn.classList.toggle("is-rec", st === "listening");
      btn.disabled = st === "transcribing";
      btn.innerHTML = ic(st === "idle" ? "mic" : st === "transcribing" ? "loader" : "square");
      var title = tw(st === "idle" ? "dict.btn" : st === "transcribing" ? "dict.busy" : "dict.stop");
      btn.title = title;
      btn.setAttribute("aria-label", title);
      btn.setAttribute("aria-pressed", st === "idle" ? "false" : "true");
    }

    // Where the words go, fixed at the press.
    function markSpot() {
      var t = o.target && o.target();
      if (!t || !t.el) return null;
      if (t.kind === "ta") {
        var ta = t.el, a = ta.selectionStart, b = ta.selectionEnd;
        if (a == null) { a = b = ta.value.length; }
        return { kind: "ta", el: ta, before: ta.value.slice(0, a), after: ta.value.slice(b), ro: ta.readOnly };
      }
      var el = t.el, sel = window.getSelection && window.getSelection();
      var range = null;
      if (sel && sel.rangeCount && el.contains(sel.getRangeAt(0).commonAncestorContainer)) range = sel.getRangeAt(0).cloneRange();
      if (!range) {
        // No caret in the note: the words start a new paragraph at the end.
        var p = document.createElement("p");
        el.appendChild(p);
        range = document.createRange();
        range.setStart(p, 0);
        range.collapse(true);
      }
      range.deleteContents();
      var span = document.createElement("span");
      span.className = "ne-dict-live";
      range.insertNode(span);
      var pre = document.createRange();
      pre.setStart(el, 0);
      pre.setEndBefore(span);
      var before = pre.toString();
      return { kind: "wys", el: el, span: span, before: before, ce: el.getAttribute("contenteditable") };
    }

    function show(text) {
      if (!spot) return;
      if (spot.kind === "ta") {
        var r = insertPlain(spot.before, text, spot.after);
        spot.el.value = r.value;
        return r;
      }
      if (spot.span.isConnected) {
        var lead = spot.before && !/\s$/.test(spot.before) && text ? " " : "";
        spot.span.textContent = text ? lead + String(text).trim() : "";
      }
      return null;
    }

    // The recording ended: the final words become ordinary text, the editor takes typing again.
    function commit(text) {
      var s = spot;
      spot = null;
      if (!s) return;
      if (s.kind === "ta") {
        s.el.readOnly = s.ro;
        var r = insertPlain(s.before, text, s.after);
        s.el.value = r.value;
        try { s.el.focus(); s.el.setSelectionRange(r.caret, r.caret); } catch (e) { /* ignore */ }
        try { s.el.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) { /* old browser */ }
      } else {
        if (s.ce == null) s.el.removeAttribute("contenteditable"); else s.el.setAttribute("contenteditable", s.ce);
        var span = s.span;
        if (span.isConnected) {
          var lead = s.before && !/\s$/.test(s.before) && text ? " " : "";
          var node = document.createTextNode(text ? lead + String(text).trim() : "");
          span.parentNode.replaceChild(node, span);
          try {
            var sel = window.getSelection(), rg = document.createRange();
            rg.setStartAfter(node); rg.collapse(true);
            sel.removeAllRanges(); sel.addRange(rg);
            s.el.focus();
          } catch (e) { /* ignore */ }
          try { s.el.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) { /* old browser */ }
        }
      }
      if (o.onChange) { try { o.onChange(); } catch (e) { /* ignore */ } }
    }

    function errorText(code) {
      var ios = D && D.isIOS && D.isIOS();
      return tw(code === "denied" ? (ios ? "dict.denied_ios" : "dict.denied")
        : code === "service" ? (ios ? "dict.service_ios" : "dict.service")
        : code === "unsupported" ? "dict.unsupported" : code === "nothing" ? "dict.nothing" : "dict.failed");
    }

    function start() {
      if (!D) { note(tw("dict.unsupported"), true); return; }
      spot = markSpot();
      if (!spot) return;
      if (spot.kind === "ta") spot.el.readOnly = true;
      else spot.el.setAttribute("contenteditable", "false");
      heard = "";
      var live = !(D.isPhoneUA && D.isPhoneUA());
      var run = D.create({
        context: function () { return contextLines(spot ? spot.before : ""); },
        onText: function (text, final) {
          if (dict !== run) return;
          heard = String(text || "");
          if (!final && live && st === "listening") show(heard);
        },
        onState: function (s) {
          if (dict !== run) return;
          var was = st;
          st = s;
          paint();
          if (s !== "idle") return;
          clearTimeout(limit);
          dict = null;
          if (was !== "idle") commit(heard);
          heard = "";
        },
        onError: function (code) { note(errorText(code), true); },
      });
      dict = run;
      clearTimeout(limit);
      limit = setTimeout(function () { if (dict === run) run.stop(); }, MAX_MS);
      run.start();
    }

    btn.onmousedown = function (e) { e.preventDefault(); };   // keep the caret where it is
    btn.onclick = function () {
      if (dict && st === "listening") { dict.stop(); return; }
      if (dict) return;
      start();
    };
    paint();

    var host = o.host;
    if (host) {
      var count = host.querySelector(".ne-count");
      if (count) host.insertBefore(btn, count); else host.appendChild(btn);
    }

    return {
      button: btn,
      stop: function () { if (dict) dict.stop(); },
      // The editor is going away: stop listening and keep what was heard.
      destroy: function () {
        clearTimeout(limit);
        var run = dict;
        dict = null;
        if (run) { try { run.cancel(); } catch (e) { /* ignore */ } }
        if (spot) commit(heard);
        st = "idle";
      },
    };
  }

  var api = { attach: attach, insertPlain: insertPlain, contextLines: contextLines };
  if (typeof window !== "undefined") window.JavisEditorDictate = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
