/* chat-card.js - interactive cards inside a Javis answer (0.201.0).

   Idea borrowed from OpenMausBot's chat widgets. An answer may carry hidden blocks
       <!-- JAVIS_CARD: {"type": "chart" | "stats" | "buttons", ...} -->
   and the chat draws them in place:
     chart    {"title", "kind": "bar"|"line", "labels": [..], "series": [{"name", "data": [numbers]}]}
     stats    {"title", "items": [{"label", "value", "delta"}]}        a row of number tiles
     buttons  {"title", "buttons": [{"label", "reply"}]}               each sends `reply` (or its label) as your message
   The blocks are drawn by markdownToHtml (chat-render.js), so live answers, history and pushed messages
   look the same. Telegram and other text channels get a plain-text version (server/channel_context.py).

   Everything in a card is model output: escaped, numbers coerced, sizes capped, and strings that look like
   secrets are masked before drawing. A button press only sends a chat message; it grants nothing.

   `parse` and `html` are pure (tested under node). */
(function () {
  "use strict";

  var RE = /<!--\s*JAVIS_CARD:\s*([\s\S]*?)\s*-->/g;
  var MAX_POINTS = 24, MAX_SERIES = 3, MAX_TILES = 6, MAX_BUTTONS = 4, MAX_TEXT = 80;
  var SECRET = /\b(?:(?:sk|gsk|rk|xai)[_-][A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_-]{20,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|\d{8,}:[-A-Za-z0-9_]{30,})/g;

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function txt(s, max) {
    var v = String(s == null ? "" : s).replace(SECRET, "••••").replace(/\s+/g, " ").trim();
    var m = max || MAX_TEXT;
    return v.length > m ? v.slice(0, m - 1) + "…" : v;
  }
  function num(v) {
    var n = typeof v === "number" ? v : parseFloat(String(v == null ? "" : v).replace(/[^\d.\-]/g, ""));
    return isFinite(n) ? n : 0;
  }

  function parse(json) {
    var o;
    try { o = JSON.parse(json); } catch (e) { return null; }
    if (!o || typeof o !== "object") return null;
    var title = txt(o.title, 100);
    if (o.type === "chart") {
      var labels = (Array.isArray(o.labels) ? o.labels : []).slice(0, MAX_POINTS).map(function (l) { return txt(l, 24); });
      var series = (Array.isArray(o.series) ? o.series : []).slice(0, MAX_SERIES).map(function (s) {
        return { name: txt(s && s.name, 40), data: (Array.isArray(s && s.data) ? s.data : []).slice(0, labels.length).map(num) };
      }).filter(function (s) { return s.data.length; });
      if (!labels.length || !series.length) return null;
      return { type: "chart", title: title, kind: o.kind === "line" ? "line" : "bar", labels: labels, series: series };
    }
    if (o.type === "stats") {
      var items = (Array.isArray(o.items) ? o.items : []).map(function (i) {
        return { label: txt(i && i.label, 40), value: txt(i && i.value, 24), delta: txt(i && i.delta, 24) };
      }).filter(function (i) { return i.label && i.value; }).slice(0, MAX_TILES);
      return items.length ? { type: "stats", title: title, items: items } : null;
    }
    if (o.type === "buttons") {
      var buttons = (Array.isArray(o.buttons) ? o.buttons : []).map(function (b) {
        return { label: txt(b && b.label, 40), reply: txt((b && b.reply) || (b && b.label), 400) };
      }).filter(function (b) { return b.label; }).slice(0, MAX_BUTTONS);
      return buttons.length ? { type: "buttons", title: title, buttons: buttons } : null;
    }
    return null;
  }

  var COLORS = ["var(--accent, #4f8cff)", "var(--green, #34a853)", "var(--warn-ink, #e0a030)"];

  function chartSvg(c) {
    var W = 320, H = 160, P = 24, n = c.labels.length;
    var all = [];
    c.series.forEach(function (s) { all = all.concat(s.data); });
    var max = Math.max.apply(null, all.concat([0])), min = Math.min.apply(null, all.concat([0]));
    var span = (max - min) || 1;
    var y = function (v) { return H - P - ((v - min) / span) * (H - 2 * P); };
    var step = (W - 2 * P) / n;
    var body = "";
    if (c.kind === "bar") {
      var bw = Math.max(2, step / (c.series.length + 1));
      c.series.forEach(function (s, si) {
        s.data.forEach(function (v, i) {
          var x = P + i * step + si * bw + bw / 2, top = y(Math.max(v, 0)), base = y(Math.min(v, 0));
          body += '<rect x="' + x.toFixed(1) + '" y="' + top.toFixed(1) + '" width="' + bw.toFixed(1) + '" height="'
            + Math.max(1, base - top).toFixed(1) + '" fill="' + COLORS[si] + '"><title>' + esc(s.name + " " + c.labels[i] + ": " + v)
            + "</title></rect>";
        });
      });
    } else {
      c.series.forEach(function (s, si) {
        var pts = s.data.map(function (v, i) { return (P + i * step + step / 2).toFixed(1) + "," + y(v).toFixed(1); }).join(" ");
        body += '<polyline fill="none" stroke="' + COLORS[si] + '" stroke-width="2" points="' + pts + '"/>';
      });
    }
    var axis = '<line x1="' + P + '" y1="' + y(0).toFixed(1) + '" x2="' + (W - P) + '" y2="' + y(0).toFixed(1)
      + '" stroke="var(--hairline, #ccc)"/>';
    var every = Math.ceil(n / 6);
    var lbl = c.labels.map(function (l, i) {
      return i % every ? "" : '<text x="' + (P + i * step + step / 2).toFixed(1) + '" y="' + (H - 6) + '" font-size="10" text-anchor="middle" fill="currentColor">' + esc(l) + "</text>";
    }).join("");
    return '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(c.title || "chart") + '" style="width:100%;max-width:520px;height:auto">'
      + axis + body + lbl + "</svg>";
  }

  function html(card) {
    if (!card) return "";
    var head = card.title ? '<div class="jv-card-title" style="font-weight:600;margin-bottom:6px">' + esc(card.title) + "</div>" : "";
    var inner = "";
    if (card.type === "chart") {
      var legend = card.series.length > 1 ? '<div style="font-size:12px;display:flex;gap:10px;flex-wrap:wrap">' + card.series.map(function (s, i) {
        return '<span><span style="display:inline-block;width:10px;height:10px;background:' + COLORS[i] + ';margin-right:4px"></span>' + esc(s.name) + "</span>";
      }).join("") + "</div>" : "";
      inner = chartSvg(card) + legend;
    } else if (card.type === "stats") {
      inner = '<div style="display:flex;gap:8px;flex-wrap:wrap">' + card.items.map(function (i) {
        var neg = /^\s*-/.test(i.delta);
        return '<div style="flex:1 1 120px;padding:8px 10px;border:1px solid var(--hairline);border-radius:8px">'
          + '<div style="font-size:12px;color:var(--text3)">' + esc(i.label) + "</div>"
          + '<div style="font-size:18px;font-weight:600">' + esc(i.value) + "</div>"
          + (i.delta ? '<div style="font-size:12px;color:' + (neg ? "var(--red, #d33)" : "var(--green, #2a8)") + '">' + esc(i.delta) + "</div>" : "")
          + "</div>";
      }).join("") + "</div>";
    } else if (card.type === "buttons") {
      inner = '<div style="display:flex;gap:8px;flex-wrap:wrap">' + card.buttons.map(function (b) {
        return '<button type="button" class="s-btn-ghost jv-card-btn" data-reply="' + esc(b.reply) + '">' + esc(b.label) + "</button>";
      }).join("") + "</div>";
    }
    return '<div class="jv-card" style="margin:8px 0;padding:10px 12px;border:1px solid var(--hairline);border-radius:10px">' + head + inner + "</div>";
  }

  /* Replaces every JAVIS_CARD block in `raw` with put(html) (chat-render.js placeholder), keeping the rest. */
  function replaceIn(raw, put) {
    return String(raw == null ? "" : raw).replace(RE, function (_m, json) {
      var c = parse(json);
      return c ? "\n" + put(html(c)) + "\n" : "";
    });
  }

  if (typeof document !== "undefined") {
    document.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest(".jv-card-btn") : null;
      if (!b || b.disabled) return;
      e.preventDefault();
      var row = b.parentNode;
      Array.prototype.forEach.call(row.querySelectorAll(".jv-card-btn"), function (x) { x.disabled = true; });
      b.classList.add("jv-ask-picked");
      if (typeof window.JavisSend === "function") window.JavisSend(b.getAttribute("data-reply"));
    });
  }

  var API = { parse: parse, html: html, replaceIn: replaceIn };
  if (typeof window !== "undefined") window.JavisCard = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})();
