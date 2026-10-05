// ============================================================
// Javis - "Try bot" panel (0.78.0).
//
// The owner types a message as if a customer sent it (privately or in a group) and sees what the bot WOULD do:
// reply or stay silent, why (the same gate, reply judge and Agent the real message goes through), the answer
// text and the documents it used. Nothing is sent to Zalo or Telegram and nothing is written anywhere: see
// chatbot_runtime.try_message on the server. Every visible string comes from the dictionary (keys `try.*`).
//
// Called by chatbots.js: window.JavisTryBot.open(bot, { groups: bool }).
// ============================================================
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function el(html) { var d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstChild; }
  function tt(k, v) { return window.t(k, v); }
  function ic(name) { return window.Icons ? window.Icons.ic(name) : ""; }

  var NOTE_LB = {
    readonly_tools: "try.note_readonly",
    group_assumed_allowed: "try.note_group",
    person_assumed_allowed: "try.note_person",
    telegram_privacy: "try.note_tg",
  };

  function reasonOf(d) {
    var RP = window.JavisReplyPolicy;
    var code = d.stage === "judge" && RP ? RP.codeLabel(d.code) : "";
    var why = [code, d.reason].filter(Boolean).join(": ");
    if (d.score != null) {
      why += " (" + Number(d.score).toFixed(2) + (d.threshold != null ? " / " + Number(d.threshold).toFixed(2) : "") + ")";
    }
    return why;
  }

  function fileName(p) { return String(p || "").split(/[\\/]/).pop(); }

  function renderResult(d) {
    if (!d.ok) {
      return '<div class="cb-err">' + ic("triangle-alert") + ' ' + esc(d.error || tt("try.err")) + '</div>';
    }
    var h = '<div class="cb-try-verdict ' + (d.would_reply ? "yes" : "no") + '">' +
      ic(d.would_reply ? "message-circle" : "circle-stop") + ' <b>' +
      esc(tt(d.would_reply ? "try.would_reply" : "try.would_silent")) + '</b></div>';
    var why = reasonOf(d);
    if (why && !d.would_reply) h += '<div class="cb-try-why">' + esc(tt("try.why", { why: why })) + '</div>';
    if (d.would_reply && d.text) {
      h += '<div class="cb-try-ans">' + esc(d.text) + '</div>';
      if (why && d.stage === "answered" && d.score != null) {
        h += '<div class="cb-try-why">' + esc(tt("try.judge_said", { why: why })) + '</div>';
      }
    }
    if ((d.sources || []).length) {
      h += '<div class="cb-try-src">' + ic("file-text") + ' ' +
        esc(tt("try.sources", { list: d.sources.map(fileName).join(", ") })) + '</div>';
    }
    (d.notes || []).forEach(function (n) {
      if (NOTE_LB[n]) h += '<div class="cb-try-note' + (n === "telegram_privacy" ? " warn" : "") + '">' +
        ic(n === "telegram_privacy" ? "triangle-alert" : "info") + '<span>' + esc(tt(NOTE_LB[n])) + '</span></div>';
    });
    return h;
  }

  function open(bot, opts) {
    var groups = !!(opts && opts.groups);
    var box = el('<div class="cb-modal"><div class="cb-form cb-try-form">' +
      '<h3>' + esc(tt("try.title", { name: bot.name || "" })) + '</h3>' +
      '<div class="cb-hint">' + esc(tt("try.hint")) + '</div>' +
      (groups
        ? '<div class="cb-try-where">' +
            '<label><input type="radio" name="cbTryWhere" value="private" checked> ' + esc(tt("try.private")) + '</label>' +
            '<label><input type="radio" name="cbTryWhere" value="group"> ' + esc(tt("try.group")) + '</label>' +
          '</div>' +
          '<label class="cb-try-tag" hidden><input type="checkbox" id="cbTryTag"> ' + esc(tt("try.tagged")) + '</label>'
        : '') +
      '<textarea id="cbTryText" rows="3" maxlength="2000" placeholder="' + esc(tt("try.ph")) + '"></textarea>' +
      '<div class="cb-try-out" aria-live="polite"></div>' +
      '<div class="cb-form-acts">' +
        '<button class="s-btn-ghost" id="cbTryClose" type="button">' + esc(tt("common.close")) + '</button>' +
        '<button class="s-btn" id="cbTryGo" type="button">' + ic("play") + ' ' + esc(tt("try.go")) + '</button>' +
      '</div></div></div>');
    document.body.appendChild(box);
    var close = function () { if (box.parentNode) box.parentNode.removeChild(box); };
    box.onmousedown = function (e) { if (e.target === box) close(); };
    box.querySelector("#cbTryClose").onclick = close;
    var inp = box.querySelector("#cbTryText"), out = box.querySelector(".cb-try-out"), go = box.querySelector("#cbTryGo");
    var tagBox = box.querySelector(".cb-try-tag");
    function where() {
      var r = box.querySelector('input[name="cbTryWhere"]:checked');
      return r ? r.value : "private";
    }
    box.querySelectorAll('input[name="cbTryWhere"]').forEach(function (r) {
      r.onchange = function () { if (tagBox) tagBox.hidden = where() !== "group"; };
    });

    var busy = false;
    async function run() {
      var text = inp.value.trim();
      if (!text || busy) { if (!text) inp.focus(); return; }
      busy = true;
      go.disabled = true;
      out.innerHTML = '<div class="cb-try-wait">' + esc(tt("try.running")) + '</div>';
      var f = new FormData();
      f.append("text", text);
      f.append("chat_type", where());
      f.append("mentioned", tagBox && !tagBox.hidden && box.querySelector("#cbTryTag").checked ? "1" : "");
      var d;
      try {
        var r = await fetch("/chatbots/" + encodeURIComponent(bot.id) + "/try", { method: "POST", body: f });
        try { d = await r.json(); } catch (e) { d = { ok: false, error: tt("cb.loi_ma", { ma: r.status }) }; }
      } catch (e) {
        d = { ok: false, error: tt("app.err_net") };
      }
      out.innerHTML = renderResult(d || {});
      busy = false;
      go.disabled = false;
    }
    go.onclick = run;
    inp.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); run(); }
    });
    inp.focus();
  }

  window.JavisTryBot = { open: open };
})();
