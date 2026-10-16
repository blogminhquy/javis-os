/* chat-nho.js - the "Đã nhớ · Hoàn tác" line under an answer (0.190.0).

   Owner, 16/10/2026: the memory list left the settings column, memory is handled in chat. So when a turn saves,
   changes or forgets a memory, the server pushes one small line into the chat (server/memory_receipt.py) carrying
   a hidden block:
       <!-- JAVIS_NHO: {"brain": "<brain key>", "items": [{"slug", "title", "act": "new|updated|forgot"}]} -->
   This file takes the block out and draws the line: what was kept, and for a NEW memory an Undo button that
   forgets it (POST /memory/forget, so it is not learnt again). The block is part of the stored message, so a
   refresh draws the same line.

   `tach` and `lineHtml` are pure for node tests. No em dash anywhere. */
(function () {
  "use strict";

  var RE = /<!--\s*JAVIS_NHO:\s*([\s\S]*?)\s*-->\s*/;
  var ACTS = { "new": "nho.saved", updated: "nho.updated", forgot: "nho.forgot" };

  function tw(khoa, bien) {
    if (typeof window !== "undefined" && window.t) return window.t(khoa, bien);
    try {
      var s = require("./i18n/vi.json")[khoa] || khoa;
      return String(s).replace(/\{(\w+)\}/g, function (m, ten) {
        return (bien && bien[ten] != null) ? String(bien[ten]) : m;
      });
    } catch (e) { return khoa; }
  }

  function esc(t) {
    return String(t == null ? "" : t)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  /* Takes the block out. ALWAYS returns `clean` without the block, even when the JSON is broken. */
  function tach(text) {
    var s = String(text == null ? "" : text);
    var m = s.match(RE);
    if (!m) return { clean: s, nho: null };
    var clean = (s.slice(0, m.index) + s.slice(m.index + m[0].length)).replace(/^\s+|\s+$/g, "");
    var v = null;
    try { v = JSON.parse(m[1]); } catch (e) { v = null; }
    if (!v || typeof v !== "object" || !Array.isArray(v.items) || !v.items.length) return { clean: clean, nho: null };
    return { clean: clean, nho: { brain: String(v.brain || ""), items: v.items.slice(0, 5).map(function (i) {
      var act = Object.prototype.hasOwnProperty.call(ACTS, i && i.act) ? i.act : "updated";
      return { slug: String((i && i.slug) || ""), title: String((i && i.title) || (i && i.slug) || ""), act: act };
    }) } };
  }

  function rowHtml(i) {
    var undo = i.act === "new" && i.slug
      ? '<button type="button" class="nho-undo" data-slug="' + esc(i.slug) + '">' + esc(tw("nho.undo")) + "</button>" : "";
    return '<div class="nho-row" data-slug="' + esc(i.slug) + '"><span class="nho-ic" aria-hidden="true">' +
      (typeof ic === "function" ? ic(i.act === "forgot" ? "eraser" : "brain") : "") + '</span><span class="nho-txt">' +
      esc(tw(ACTS[i.act])) + ": <strong>" + esc(i.title) + "</strong></span>" + undo + "</div>";
  }

  function lineHtml(nho) {
    return '<div class="nho-line" role="status">' + (nho.items || []).map(rowHtml).join("") + "</div>";
  }

  function undo(btn, brain) {
    var row = btn.closest(".nho-row");
    var slug = btn.getAttribute("data-slug");
    btn.disabled = true;
    fetch("/memory/forget", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ brain: brain || "brain", slug: slug }) }).then(function (r) {
      if (r.status !== 200 && r.status !== 404) throw new Error(String(r.status));
      // 404: already gone (forgotten in chat or another tab): the result the person wanted, say so the same way.
      var txt = row && row.querySelector(".nho-txt");
      if (txt) txt.textContent = tw("nho.undone");
      if (btn.parentNode) btn.parentNode.removeChild(btn);
    }).catch(function () {
      btn.disabled = false;
      btn.textContent = tw("nho.undo_err");
    });
  }

  /* Draws one pushed message (.msg-javis) as the receipt line instead of a chat bubble. */
  function ve(msgEl, nho) {
    if (!msgEl || !nho) return msgEl;
    msgEl.classList.add("msg-nho");
    var bubble = msgEl.querySelector(".bubble");
    if (bubble) bubble.innerHTML = lineHtml(nho);
    var acts = msgEl.querySelector(".msg-acts");
    if (acts && acts.parentNode) acts.parentNode.removeChild(acts);
    Array.prototype.forEach.call(msgEl.querySelectorAll(".nho-undo"), function (b) {
      b.addEventListener("click", function () { undo(b, nho.brain); });
    });
    return msgEl;
  }

  var API = { tach: tach, ve: ve, lineHtml: lineHtml };
  if (typeof window !== "undefined") window.JavisNho = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})();
