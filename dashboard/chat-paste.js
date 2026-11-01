/* chat-paste.js - long text pasted into a chat box (0.430.1).

   Before this, the main chat and the team chat turned any paste over 1,500 characters or 25 lines into a
   van-ban-dan-*.txt chip without asking. A Vietnamese report hits that limit fast, and the owner could no
   longer see what they had pasted. Now text up to INLINE_CHARS and INLINE_LINES pastes as normal text; only
   past one of the two limits does a dialog show the whole text and ask: paste into chat, attach as .txt,
   or cancel. Nothing is converted silently.

   Shared by app.js (main chat) and teams.js (team chat). The pure part (isLong) is tested in node by
   tests/js/test_chat_paste.js. Idea from @hwangrin (PR 937). No em dash in this file. */
(function (root) {
  "use strict";
  var INLINE_CHARS = 12000;
  var INLINE_LINES = 150;

  function normalise(text) {
    return String(text == null ? "" : text).replace(/\r\n?/g, "\n");
  }
  function lineCount(text) {
    return normalise(text).split("\n").length;
  }
  function isLong(text) {
    var s = normalise(text);
    return s.length > INLINE_CHARS || lineCount(s) > INLINE_LINES;
  }

  function tr(key, vars) {
    if (typeof window !== "undefined" && typeof window.t === "function") {
      var got = window.t(key, vars);
      if (got && got !== key) return got;
    }
    var fallback = {
      "paste.title": "Preview pasted text",
      "paste.note": "{chars} characters · {lines} lines. Paste it into the chat or attach it as a file. Nothing is cut.",
      "paste.preview": "Full pasted text",
      "paste.cancel": "Cancel",
      "paste.attach": "Attach .txt",
      "paste.inline": "Paste into chat"
    };
    return String(fallback[key] || key).replace(/\{(\w+)\}/g, function (_, k) {
      return vars && vars[k] != null ? String(vars[k]) : "";
    });
  }

  // Show the whole text and let the owner choose. onInline(text) / onFile(text) run after the dialog
  // closes; Cancel, Escape or a click outside closes it and does nothing.
  function offer(text, onInline, onFile) {
    if (typeof document === "undefined") return false;
    text = normalise(text);
    var oldFocus = document.activeElement;
    var layer = document.createElement("div");
    layer.className = "jv-paste-overlay";
    var dialog = document.createElement("div");
    dialog.className = "jv-paste-dialog";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", tr("paste.title"));
    var title = document.createElement("h2");
    title.textContent = tr("paste.title");
    var note = document.createElement("p");
    note.textContent = tr("paste.note", { chars: text.length.toLocaleString(),
      lines: lineCount(text).toLocaleString() });
    // A read-only textarea: the text is shown exactly as pasted, never read as HTML.
    var preview = document.createElement("textarea");
    preview.className = "jv-paste-preview";
    preview.value = text;
    preview.readOnly = true;
    preview.setAttribute("aria-label", tr("paste.preview"));
    var actions = document.createElement("div");
    actions.className = "jv-paste-actions";
    function close() {
      document.removeEventListener("keydown", keydown, true);
      layer.remove();
      if (oldFocus && oldFocus.focus) oldFocus.focus();
    }
    function button(label, css, fn) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = css;
      b.textContent = label;
      b.addEventListener("click", function () { close(); if (fn) fn(text); });
      actions.appendChild(b);
      return b;
    }
    button(tr("paste.cancel"), "gcard-btn ghost", null);
    button(tr("paste.attach"), "gcard-btn ghost", onFile);
    var pasteBtn = button(tr("paste.inline"), "gcard-btn", onInline);
    function keydown(e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); return; }
      if (e.key === "Tab") {
        // Keep focus inside the dialog.
        var nodes = [preview].concat(Array.prototype.slice.call(actions.querySelectorAll("button")));
        var first = nodes[0], last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }
    dialog.appendChild(title);
    dialog.appendChild(note);
    dialog.appendChild(preview);
    dialog.appendChild(actions);
    layer.appendChild(dialog);
    layer.addEventListener("click", function (e) { if (e.target === layer) close(); });
    document.body.appendChild(layer);
    document.addEventListener("keydown", keydown, true);
    pasteBtn.focus();
    return true;
  }

  // Put text where the caret was when the paste happened, as if the browser had pasted it.
  function insertAt(input, range, value) {
    if (!input || !input.isConnected) return;
    input.focus();
    input.setRangeText(value, range.start, range.end, "end");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // One .txt File for the "Attach .txt" choice, named like before (van-ban-dan-HHMMSS.txt).
  function textFile(text) {
    var d = new Date(), p = function (n) { return String(n).padStart(2, "0"); };
    var name = "van-ban-dan-" + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds()) + ".txt";
    return new File([new Blob([text], { type: "text/plain" })], name, { type: "text/plain" });
  }

  var api = { INLINE_CHARS: INLINE_CHARS, INLINE_LINES: INLINE_LINES, isLong: isLong,
    lineCount: lineCount, offer: offer, insertAt: insertAt, textFile: textFile };
  if (root) root.JavisPaste = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : null);
