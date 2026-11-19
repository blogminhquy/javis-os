/* text-edit-dialog.js - one roomy box to write or fix a short text (2026-11-19).

   Owner, 19/11/2026: "popup làm lại khi sửa để mở rộng ra dễ sửa". Editing a learned note, an assistant lesson or the
   one line saying what a document holds used the browser's prompt(): a single cramped line where a 300 character note
   scrolls sideways and the start of the sentence is out of sight. This box gives the text a real area that grows with
   it, a character count, the note kinds as chips, and Cancel / Save buttons.

   Desktop: centred over the page. Phone (up to 600px): a sheet from the bottom, buttons in thumb reach, following the
   visible part of the screen while the keyboard is up (body.kb-open and --vv-* from mobile-chat.js).

   JavisTextEdit.open({
     title, value, max, placeholder, hint,
     kinds: [{value, label}], kind, kindLabel,     // optional: one-of chips under the text (radio group)
     saveLabel, allowEmpty,                        // allowEmpty: an empty text is a valid answer (removes a description)
     save(text, kind) -> Promise<"" | error text>  // the box stays open and shows the error when saving fails
   }) -> Promise<boolean>                          // true once saved, false when closed without saving

   Ctrl/Cmd+Enter saves, Escape closes. A tap outside closes only when nothing was changed, so a stray tap never throws
   away a long edit. Pure helpers are exported for node tests. No em dash here. */
(function (root) {
  "use strict";

  // ---- pure helpers (node-testable) ----
  function counterText(len, max) { return max ? len + "/" + max : String(len); }
  function counterState(len, max) {
    if (!max) return "";
    if (len >= max) return "full";
    return len >= max * 0.9 ? "near" : "";
  }
  /** What a save would send, or null when there is nothing to save (unchanged, or empty where empty is not allowed). */
  function pending(start, text, startKind, kind, allowEmpty) {
    var v = String(text == null ? "" : text).trim();
    if (!v && !allowEmpty) return null;
    if (v === String(start == null ? "" : start).trim() && (kind || "") === (startKind || "")) return null;
    return { text: v, kind: kind || "" };
  }

  var api = { counterText: counterText, counterState: counterState, pending: pending };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (!root || typeof document === "undefined") return;
  root.JavisTextEdit = api;

  function t(key, vars) { try { return root.t ? root.t(key, vars) : key; } catch (e) { return key; } }
  function icon(name) { try { return root.ic ? root.ic(name) : ""; } catch (e) { return ""; } }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function isMac() { try { return /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || ""); } catch (e) { return false; } }

  var current = null;   // the open box: {wrap, finish}

  function open(o) {
    o = o || {};
    if (current) current.finish(false);
    return new Promise(function (resolve) {
      var start = String(o.value == null ? "" : o.value);
      var kinds = o.kinds || [];
      var startKind = kinds.length ? (o.kind || kinds[0].value) : "";
      var kind = startKind;
      var max = Number(o.max) || 0;
      var busy = false;
      var before = document.activeElement;

      var wrap = document.createElement("div");
      wrap.className = "ted-wrap";
      wrap.innerHTML =
        '<div class="ted-scrim"></div>' +
        '<div class="ted-box" role="dialog" aria-modal="true" aria-label="' + esc(o.title) + '">' +
          '<div class="ted-grip"></div>' +
          '<div class="ted-head"><span class="ted-title">' + esc(o.title) + "</span>" +
            '<button type="button" class="ted-x" aria-label="' + esc(t("ted.close")) + '" title="' + esc(t("ted.close")) + '">' +
              icon("x") + "</button></div>" +
          (o.hint ? '<div class="ted-hint">' + esc(o.hint) + "</div>" : "") +
          '<textarea class="ted-in" rows="6"' + (max ? ' maxlength="' + max + '"' : "") +
            ' placeholder="' + esc(o.placeholder || "") + '"></textarea>' +
          (kinds.length
            ? '<div class="ted-kinds" role="radiogroup" aria-label="' + esc(o.kindLabel || "") + '">' +
                kinds.map(function (k) {
                  var on = k.value === kind;
                  return '<button type="button" class="ted-kind' + (on ? " on" : "") + '" role="radio" aria-checked="' + on +
                    '" data-kind="' + esc(k.value) + '">' + esc(k.label) + "</button>";
                }).join("") + "</div>"
            : "") +
          '<div class="ted-err" role="status" hidden></div>' +
          '<div class="ted-foot">' +
            '<span class="ted-count" aria-live="polite"></span>' +
            '<span class="ted-keys">' + esc(t("ted.keys", { key: isMac() ? "Cmd" : "Ctrl" })) + "</span>" +
            '<button type="button" class="ted-cancel">' + esc(t("ted.cancel")) + "</button>" +
            '<button type="button" class="ted-save">' + esc(o.saveLabel || t("ted.save")) + "</button>" +
          "</div>" +
        "</div>";
      document.body.appendChild(wrap);

      var box = wrap.querySelector(".ted-in");
      var count = wrap.querySelector(".ted-count");
      var err = wrap.querySelector(".ted-err");
      var saveBtn = wrap.querySelector(".ted-save");
      box.value = start;

      function grow() {
        box.style.height = "auto";
        box.style.height = box.scrollHeight + 2 + "px";
      }
      function refresh() {
        var len = box.value.length;
        count.textContent = counterText(len, max);
        count.className = "ted-count" + (counterState(len, max) ? " " + counterState(len, max) : "");
        saveBtn.disabled = busy || !pending(start, box.value, startKind, kind, o.allowEmpty);
        grow();
      }
      function showErr(text) {
        err.hidden = !text;
        err.textContent = text || "";
      }
      function finish(saved) {
        if (current && current.wrap === wrap) current = null;
        document.removeEventListener("keydown", onKey, true);
        wrap.remove();
        try { if (before && document.body.contains(before)) before.focus(); } catch (e) {}
        resolve(saved);
      }
      async function save() {
        var p = pending(start, box.value, startKind, kind, o.allowEmpty);
        if (!p || busy) return;
        busy = true; refresh();
        saveBtn.textContent = t("ted.saving");
        var problem = "";
        try { problem = o.save ? await o.save(p.text, p.kind) : ""; } catch (e) { problem = String(e && e.message || e); }
        if (!wrap.isConnected) return;
        busy = false;
        saveBtn.textContent = o.saveLabel || t("ted.save");
        if (problem) { showErr(problem); refresh(); box.focus(); return; }
        finish(true);
      }
      function onKey(e) {
        if (!wrap.isConnected) return;
        if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); finish(false); return; }
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !e.isComposing) { e.preventDefault(); save(); }
      }

      wrap.querySelector(".ted-x").onclick = function () { finish(false); };
      wrap.querySelector(".ted-cancel").onclick = function () { finish(false); };
      wrap.querySelector(".ted-scrim").onclick = function () {
        if (!pending(start, box.value, startKind, kind, true)) finish(false);
        else box.focus();
      };
      saveBtn.onclick = save;
      box.addEventListener("input", function () { showErr(""); refresh(); });
      wrap.querySelectorAll(".ted-kind").forEach(function (b) {
        b.onclick = function () {
          kind = b.dataset.kind;
          wrap.querySelectorAll(".ted-kind").forEach(function (x) {
            var on = x === b;
            x.classList.toggle("on", on);
            x.setAttribute("aria-checked", String(on));
          });
          refresh();
        };
      });
      document.addEventListener("keydown", onKey, true);

      current = { wrap: wrap, finish: finish };
      refresh();
      // Caret at the end: the owner usually adds to or trims the tail of what is there.
      requestAnimationFrame(function () {
        if (!wrap.isConnected) return;
        try { box.focus(); box.setSelectionRange(box.value.length, box.value.length); } catch (e) {}
        grow();
      });
    });
  }

  api.open = open;
  api.close = function () { if (current) current.finish(false); };
})(typeof window !== "undefined" ? window : null);
