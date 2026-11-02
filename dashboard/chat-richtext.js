/* Conservative HTML clipboard to Markdown and quote-aware user bubble rendering. */
(function (root) {
  "use strict";

  function hasMarkdown(text) {
    text = String(text || "");
    return /(^|\n)[ \t]{0,3}(?:#{1,6}[ \t]|[-*+][ \t]|\d+[.)][ \t]|\x60{3}|>[ \t]?|\|[^\n]+\|[ \t]*$)/m.test(text) ||
      /(\*\*[^*\n]+\*\*|__[^_\n]+__|~~[^~\n]+~~|\x60[^\x60\n]+\x60|\[[^\]\n]+\]\(https?:\/\/[^)\n]+\))/m.test(text) ||
      /(^|[^*])\*[^*\n]+\*(?!\*)/.test(text);
  }
  function domToMarkdown(rootNode) {
    var changed = 0, unsupported = false, visited = 0;
    function tagOf(n) { return n && n.tagName ? String(n.tagName).toLowerCase() : ""; }
    function attr(n, key) { return n && n.getAttribute ? String(n.getAttribute(key) || "") : ""; }
    function kids(n) { return Array.prototype.slice.call((n && n.childNodes) || []); }
    function escapeText(s) {
      return String(s || "").replace(/\u00a0/g, " ").replace(/([\\\x60*_[\]{}!])/g, "\\$1");
    }
    function weight(style) {
      var match = /(?:^|;)\s*font-weight\s*:\s*([^;]+)/i.exec(style);
      return match ? match[1].trim().toLowerCase().replace(/\s*!important\s*$/, "") : "";
    }
    function isBold(n, tag) {
      var w = weight(attr(n, "style"));
      if (w) return w === "bold" || w === "bolder" || /^[6-9]00$/.test(w);
      return tag === "strong" || tag === "b";
    }
    function mark(text, token) {
      var m = /^(\s*)([\s\S]*?)(\s*)$/.exec(text);
      return m && m[2] ? m[1] + token + m[2] + token + m[3] : text;
    }
    function children(n) { return kids(n).map(render).join(""); }
    function line(s) { return String(s || "").replace(/\s*\n\s*/g, " ").trim(); }
    function list(n, depth) {
      changed++;
      var numbered = tagOf(n) === "ol";
      var index = parseInt(attr(n, "start"), 10);
      if (!Number.isFinite(index)) index = 1;
      var entries = [];
      kids(n).forEach(function (li) {
        if (tagOf(li) !== "li") return;
        if (numbered && attr(li, "value")) {
          var v = parseInt(attr(li, "value"), 10);
          if (Number.isFinite(v)) index = v;
        }
        var nested = [], before = [];
        kids(li).forEach(function (c) {
          if (/^(ol|ul)$/.test(tagOf(c))) nested.push(list(c, depth + 1));
          else before.push(render(c));
        });
        var primary = before.join("").replace(/\n{2,}/g, "\n").trim();
        var marker = numbered ? (index++) + ". " : "- ";
        var indent = "  ".repeat(depth);
        entries.push(indent + marker + primary.replace(/\n/g, "\n" + indent + "  ") +
          (nested.length ? "\n" + nested.join("\n") : ""));
      });
      return entries.join("\n");
    }
    function table(n) {
      changed++;
      var rows = [];
      function scan(parent) {
        kids(parent).forEach(function (c) {
          var t = tagOf(c);
          if (t === "tr") {
            var cells = kids(c).filter(function (x) { return /^(td|th)$/.test(tagOf(x)); });
            if (!cells.length) return;
            rows.push(cells.map(function (cell) {
              if ((attr(cell, "rowspan") && attr(cell, "rowspan") !== "1") ||
                  (attr(cell, "colspan") && attr(cell, "colspan") !== "1")) unsupported = true;
              var contents = line(children(cell));
              // Existing Markdown table parser cannot guarantee escaped pipes or
              // nested tables are lossless; keep the original plain text instead.
              if (contents.indexOf("|") >= 0 || kids(cell).some(function (x) { return tagOf(x) === "table"; })) {
                unsupported = true;
              }
              return contents;
            }));
          } else if (/^(thead|tbody|tfoot)$/.test(t)) scan(c);
        });
      }
      scan(n);
      if (!rows.length) return "";
      var cols = rows[0].length;
      if (rows.some(function (r) { return r.length !== cols; })) unsupported = true;
      function row(cells) { return "| " + cells.join(" | ") + " |"; }
      return "\n\n" + row(rows[0]) + "\n" + row(Array(cols).fill("---")) +
        (rows.length > 1 ? "\n" + rows.slice(1).map(row).join("\n") : "") + "\n\n";
    }
    function render(n) {
      if (++visited > 15000) { unsupported = true; return ""; }
      if (!n) return "";
      if (n.nodeType === 3) return escapeText(n.nodeValue);
      if (n.nodeType !== 1) return "";
      var t = tagOf(n);
      if (/^(script|style|svg|iframe|object|embed|noscript|meta|link|template)$/.test(t)) return "";
      if (/^(img|video|audio|canvas|math|picture)$/.test(t)) { unsupported = true; return ""; }
      if (t === "br") return "\n";
      if (/^h[1-6]$/.test(t)) {
        changed++; return "\n\n" + "#".repeat(+t[1]) + " " + line(children(n)) + "\n\n";
      }
      if (t === "ul" || t === "ol") return "\n" + list(n, 0) + "\n";
      if (t === "table") return table(n);
      if (t === "blockquote") {
        changed++;
        return "\n\n" + children(n).trim().split(/\n+/).map(function (s) { return "> " + s.trim(); }).join("\n") + "\n\n";
      }
      if (t === "hr") { changed++; return "\n\n---\n\n"; }
      var body = children(n);
      if ((t === "strong" || t === "b" || t === "span") && isBold(n, t)) {
        changed++; return mark(body, "**");
      }
      if (t === "em" || t === "i" ||
          (t === "span" && /font-style\s*:\s*italic/i.test(attr(n, "style")))) {
        changed++; return mark(body, "*");
      }
      if (t === "code") { changed++; return mark(body.replace(/\n/g, " "), String.fromCharCode(96)); }
      if (t === "a") {
        var href = attr(n, "href").trim();
        if (/^(https?:\/\/|mailto:)/i.test(href) && body.trim()) {
          changed++;
          return "[" + body.trim() + "](" + href.replace(/[\s()]/g, function (c) {
            return "%" + c.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0");
          }) + ")";
        }
        return body;
      }
      if (/^(p|div|section|article)$/.test(t)) return "\n\n" + body.trim() + "\n\n";
      return body;
    }
    var markdown = children(rootNode).replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
    return { markdown: changed && !unsupported ? markdown : "", unsupported: unsupported };
  }

  function prepare(plain, html) {
    plain = String(plain == null ? "" : plain).replace(/\r\n?/g, "\n");
    if (!plain || !html || html.length > 1000000 || hasMarkdown(plain) ||
        typeof DOMParser === "undefined") return plain;
    try {
      var doc = new DOMParser().parseFromString(html, "text/html");
      if (!doc || !doc.body) return plain;
      var out = domToMarkdown(doc.body);
      if (!out.markdown || out.unsupported) return plain;
      // Avoid "whole copy becomes bold" from a website or Google Docs wrappers.
      if (out.markdown === "**" + plain.trim() + "**") return plain;
      var rawText = (doc.body.textContent || "").replace(/[^\p{L}\p{N}]/gu, "");
      var plainText = plain.replace(/[^\p{L}\p{N}]/gu, "");
      if (plainText.length && (rawText.length < plainText.length * 0.78 ||
                               rawText.length > plainText.length * 1.5)) return plain;
      return out.markdown;
    } catch (_) { return plain; }
  }

  function renderUser(text, esc, md, quote) {
    var parts = quote && quote.tach ? quote.tach(text) : { quote: "", rest: String(text || "") };
    var rich = !!(md && hasMarkdown(parts.rest));
    var prefix = parts.quote ? '<span class="uquote">' + esc(parts.quote) + "</span>" : "";
    var body = rich ? '<div class="jv-user-md">' + md(parts.rest) + "</div>" : esc(parts.rest);
    return { html: prefix + body, rich: rich };
  }

  var api = { prepare: prepare, domToMarkdown: domToMarkdown, hasMarkdown: hasMarkdown,
              renderUser: renderUser };
  if (root) root.JavisRichText = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : null);
