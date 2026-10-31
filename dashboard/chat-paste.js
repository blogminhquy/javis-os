/* Chat paste UX. Pure policy + browser-only rich text/choice UI; no external dependencies. */
(function (root) {
  "use strict";
  var INLINE_CHARS = 12000;
  var INLINE_LINES = 150;

  function normalise(text) {
    return String(text == null ? "" : text).replace(/\r\n?/g, "\n");
  }
  function isLong(text) {
    text = normalise(text);
    return text.length > INLINE_CHARS || text.split("\n").length > INLINE_LINES;
  }
  function isMarkdown(text) {
    return /(^|\n)\s{0,3}(#{1,6}\s|[-*+]\s|\d+[.)]\s|>\s|\|[^\n]+\|\s*$)/m.test(text) ||
      /(\*\*[^*\n]+\*\*|~~[^~\n]+~~)/m.test(text) ||
      text.includes(String.fromCharCode(96).repeat(3));
  }
  function htmlToMarkdown(html) {
    if (!html || typeof DOMParser === "undefined" || html.length > 1000000) return "";
    var doc;
    try { doc = new DOMParser().parseFromString(html, "text/html"); }
    catch (_) { return ""; }
    if (!doc || !doc.body || !doc.body.querySelector(
      "h1,h2,h3,h4,h5,h6,b,strong,i,em,ul,ol,table,blockquote")) return "";
    var TICK = String.fromCharCode(96);
    function childText(node) {
      return Array.prototype.map.call(node.childNodes || [], walk).join("");
    }
    function walk(node) {
      if (node.nodeType === 3) return node.nodeValue.replace(/\u00a0/g, " ");
      if (node.nodeType !== 1) return "";
      var tag = node.tagName.toLowerCase();
      if (/^(script|style|svg|iframe|object|embed|meta|link|img|noscript)$/.test(tag)) return "";
      var body = childText(node);
      if (tag === "br") return "\n";
      if (/^h[1-6]$/.test(tag)) return "\n\n" + "#".repeat(Number(tag[1])) + " " + body.trim() + "\n\n";
      if (tag === "strong" || tag === "b") return body.trim() ? "**" + body.trim() + "**" : body;
      if (tag === "em" || tag === "i") return body.trim() ? "*" + body.trim() + "*" : body;
      if (tag === "code") return TICK + body.replace(/\n/g, " ") + TICK;
      if (tag === "a") {
        var href = (node.getAttribute("href") || "").trim();
        return /^(https?:\/\/|mailto:)/i.test(href) && body.trim()
          ? "[" + body.trim() + "](" + href.replace(/[()\s]/g, encodeURIComponent) + ")" : body;
      }
      if (tag === "table") {
        var rows = Array.prototype.slice.call(node.querySelectorAll("tr"));
        var lines = rows.map(function (row) {
          var cells = Array.prototype.slice.call(row.children).filter(function (c) {
            return /^(td|th)$/i.test(c.tagName);
          });
          return cells.map(function (c) {
            return walkCells(c).replace(/\|/g, "\\|").replace(/\s*\n\s*/g, " ").trim();
          });
        }).filter(function (cells) { return cells.length; });
        if (!lines.length) return "";
        var cols = Math.max.apply(null, lines.map(function (r) { return r.length; }));
        function row(cells) {
          var a = cells.slice();
          while (a.length < cols) a.push("");
          return "| " + a.join(" | ") + " |";
        }
        return "\n\n" + row(lines[0]) + "\n" +
          row(Array(cols).fill("---")) + "\n" + lines.slice(1).map(row).join("\n") + "\n\n";
      }
      if (tag === "li") return "\n- " + body.trim();
      if (tag === "ul" || tag === "ol") return "\n" + body.trim() + "\n";
      if (tag === "blockquote") return "\n\n" + body.trim().split("\n").map(function (s) {
        return "> " + s;
      }).join("\n") + "\n\n";
      if (/^(p|div|section|article)$/.test(tag)) return "\n\n" + body.trim() + "\n\n";
      return body;
    }
    function walkCells(node) {
      return Array.prototype.map.call(node.childNodes || [], walk).join("");
    }
    return normalise(childText(doc.body)).replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  }
  function prepare(plain, html) {
    plain = normalise(plain);
    // Explicit Markdown Copy buttons already contain the intended syntax.
    if (isMarkdown(plain)) return plain;
    // Markdown cannot represent merged table cells or embedded media faithfully.
    // Retain the source's text rather than silently dropping information.
    if (plain && /<(?:td|th)\b[^>]*\b(?:rowspan|colspan)\s*=|<img\b/i.test(html || "")) return plain;
    var rich = htmlToMarkdown(html);
    if (!rich) return plain;
    // Do not trade data completeness for styling when a source's HTML selection
    // omits a substantial part of its plain-text clipboard payload.
    var visible = rich.replace(/[\s#*|>\[\]()]/g, "").length;
    var original = plain.replace(/\s/g, "").length;
    if (original && visible < original * 0.75) return plain;
    return rich;
  }

  function offer(text, onInline, onFile) {
    if (typeof document === "undefined") return false;
    var oldFocus = document.activeElement;
    var layer = document.createElement("div");
    layer.className = "jv-paste-overlay";
    var dialog = document.createElement("div");
    dialog.className = "jv-paste-dialog";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", "Xem trước nội dung dán");
    var title = document.createElement("h2");
    title.textContent = "Xem trước nội dung dán";
    var note = document.createElement("p");
    note.textContent = text.length.toLocaleString("vi-VN") + " ký tự · " +
      text.split("\n").length.toLocaleString("vi-VN") +
      " dòng. Chọn dán vào chat hoặc đính kèm tệp, nội dung không bị cắt.";
    var preview = document.createElement("textarea");
    preview.className = "jv-paste-preview";
    preview.value = text;
    preview.readOnly = true;
    preview.setAttribute("aria-label", "Toàn bộ nội dung sẽ dán");
    var actions = document.createElement("div");
    actions.className = "jv-paste-actions";
    function close() {
      document.removeEventListener("keydown", keydown, true);
      layer.remove();
      if (oldFocus && oldFocus.focus) oldFocus.focus();
    }
    function btn(label, css, fn) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = css;
      b.textContent = label;
      b.addEventListener("click", function () { close(); if (fn) fn(text); });
      actions.appendChild(b);
      return b;
    }
    btn("Hủy", "gcard-btn ghost", null);
    btn("Đính kèm .txt", "gcard-btn ghost", onFile);
    var paste = btn("Dán vào chat", "gcard-btn", onInline);
    function keydown(e) {
      if (e.key === "Escape") { e.preventDefault(); close(); }
      if (e.key === "Tab") {
        var buttons = actions.querySelectorAll("button");
        var nodes = [preview].concat(Array.prototype.slice.call(buttons));
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
    paste.focus();
    return true;
  }

  var api = { INLINE_CHARS: INLINE_CHARS, INLINE_LINES: INLINE_LINES, isLong: isLong,
    isMarkdown: isMarkdown, prepare: prepare, offer: offer, htmlToMarkdown: htmlToMarkdown };
  if (typeof window !== "undefined") window.JavisPaste = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : null);
