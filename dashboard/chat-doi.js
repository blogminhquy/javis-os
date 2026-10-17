/* chat-doi.js - the "Đã tạo lịch · Hoàn tác" line under an answer (0.200.0).

   When a chat turn creates, edits or removes a schedule, loop, partner, workflow or skill, the server pushes one small
   line into the chat (server/change_receipt.py) carrying a hidden block:
       <!-- JAVIS_DOI: {"brain": "<brain key>", "items": [{"kind", "id", "title", "act": "new|updated|removed"}]} -->
   This file takes the block out and draws the line. A NEW item gets an Undo button that calls the route that already
   removes that kind (cancel a reminder, delete a loop, partner, workflow or skill). The block is part of the stored
   message, so a refresh draws the same line.

   `tach` and `lineHtml` are pure for node tests. */
(function () {
  "use strict";

  var RE = /<!--\s*JAVIS_DOI:\s*([\s\S]*?)\s*-->\s*/;
  var KINDS = ["reminder", "loop", "agent", "workflow", "skill"];
  var ACTS = { "new": "doi.new", updated: "doi.updated", removed: "doi.removed" };
  var KIND_KEY = { reminder: "doi.k_reminder", loop: "doi.k_loop", agent: "doi.k_agent", workflow: "doi.k_workflow",
    skill: "doi.k_skill" };
  var ICON = { reminder: "alarm-clock", loop: "repeat", agent: "bot", workflow: "workflow", skill: "book-open" };
  // Undo for a new item: the existing delete/cancel route of that kind, form-encoded like the rest of the dashboard.
  var UNDO = { reminder: "/reminders/cancel", loop: "/loops/delete", agent: "/agents/delete",
    workflow: "/workflows/delete", skill: "/skills/delete" };

  function tw(key, vars) {
    if (typeof window !== "undefined" && window.t) return window.t(key, vars);
    try {
      var s = require("./i18n/vi.json")[key] || key;
      return String(s).replace(/\{(\w+)\}/g, function (m, name) {
        return (vars && vars[name] != null) ? String(vars[name]) : m;
      });
    } catch (e) { return key; }
  }
  function esc(t) {
    return String(t == null ? "" : t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function tach(text) {
    var s = String(text == null ? "" : text);
    var m = s.match(RE);
    if (!m) return { clean: s, doi: null };
    var clean = (s.slice(0, m.index) + s.slice(m.index + m[0].length)).replace(/^\s+|\s+$/g, "");
    var v = null;
    try { v = JSON.parse(m[1]); } catch (e) { v = null; }
    if (!v || typeof v !== "object" || !Array.isArray(v.items) || !v.items.length) return { clean: clean, doi: null };
    var items = v.items.filter(function (i) { return i && KINDS.indexOf(i.kind) >= 0; }).slice(0, 6).map(function (i) {
      var act = Object.prototype.hasOwnProperty.call(ACTS, i.act) ? i.act : "updated";
      return { kind: i.kind, id: String(i.id || ""), title: String(i.title || i.id || ""), act: act };
    });
    return { clean: clean, doi: items.length ? { brain: String(v.brain || ""), items: items } : null };
  }

  function rowHtml(i) {
    var undo = i.act === "new" && i.id
      ? '<button type="button" class="nho-undo doi-undo" data-kind="' + esc(i.kind) + '" data-id="' + esc(i.id) + '">'
        + esc(tw("nho.undo")) + "</button>" : "";
    return '<div class="nho-row"><span class="nho-ic" aria-hidden="true">'
      + (typeof ic === "function" ? ic(ICON[i.kind] || "check") : "") + '</span><span class="nho-txt">'
      + esc(tw(ACTS[i.act], { kind: tw(KIND_KEY[i.kind]) })) + ": <strong>" + esc(i.title) + "</strong></span>" + undo + "</div>";
  }

  function lineHtml(doi) {
    return '<div class="nho-line" role="status">' + (doi.items || []).map(rowHtml).join("") + "</div>";
  }

  function undo(btn, brain) {
    var kind = btn.getAttribute("data-kind"), id = btn.getAttribute("data-id");
    var url = UNDO[kind];
    if (!url) return;
    var f = new FormData();
    f.append(kind === "reminder" ? "id" : "slug", id);
    f.append("brain", brain || "brain");
    btn.disabled = true;
    fetch(url, { method: "POST", credentials: "same-origin", body: f }).then(function (r) {
      if (r.status !== 200 && r.status !== 404) throw new Error(String(r.status));
      var txt = btn.parentNode && btn.parentNode.querySelector(".nho-txt");
      if (txt) txt.textContent = tw("doi.undone");
      if (btn.parentNode) btn.parentNode.removeChild(btn);
    }).catch(function () {
      btn.disabled = false;
      btn.textContent = tw("nho.undo_err");
    });
  }

  function ve(msgEl, doi) {
    if (!msgEl || !doi) return msgEl;
    msgEl.classList.add("msg-nho");
    var bubble = msgEl.querySelector(".bubble");
    if (bubble) bubble.innerHTML = lineHtml(doi);
    var acts = msgEl.querySelector(".msg-acts");
    if (acts && acts.parentNode) acts.parentNode.removeChild(acts);
    Array.prototype.forEach.call(msgEl.querySelectorAll(".doi-undo"), function (b) {
      b.addEventListener("click", function () { undo(b, doi.brain); });
    });
    return msgEl;
  }

  var API = { tach: tach, ve: ve, lineHtml: lineHtml, UNDO: UNDO };
  if (typeof window !== "undefined") window.JavisDoi = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})();
