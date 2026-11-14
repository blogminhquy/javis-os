/* quote-jump.js - tap a quote in a message to scroll back to the words it quotes.

   Owner, 2026-11-14: "Trong cả câu trả lời dài của AI có vài chỗ mình muốn hỏi thêm -> quote AI -> nếu mà tap vào cái
   quote đó xong nó autoscroll back tới cái câu trả lời gốc thì tiện", then "khi click vào cái quote thì tự cuộn đến câu
   mình đã quote". So a tap on the quote at the top of a sent message scrolls the chat to the exact sentence it quotes
   (not just the top of a long answer) and marks those words for a moment.

   Why it searches the text instead of following a stored id: a quote is plain words inside the message (chat-quote.js,
   a markdown "> ..." block), so it survives F5, reopening the chat and every engine. The search runs over the messages
   ABOVE the tapped one, nearest first: an exact match anywhere wins over a loose one. Exact means the same letters and
   digits in the same order; spaces, punctuation, markdown marks, case and accents do not count, because the quote is the
   answer's markdown while the screen shows it rendered. Loose means the first and last words of the quote are found
   (a long quote that was cut with "…", or the page shows a word the markdown did not have). Not on screen: older pages
   are loaded (the caller's loadOlder) a few times before giving up with a short note.

   Used by the main chat (app.js) and the Team chat (teams.js). The pure parts (fold, visible, findSpan) are tested with
   node: tests/js/test_quote_jump.js. */
(function () {
  "use strict";

  var HEAD = 32;            // folded characters used as the start and end anchors of a loose match
  var MAX_LOADS = 8;        // pages of older messages loaded at most while looking for the source
  var MARK = "jv-quote-hit"; // name of the CSS highlight (style.css: ::highlight(jv-quote-hit))
  var SHOW_MS = 2600;       // how long the quoted words stay marked
  // Never part of the words of a message: buttons, icons, the language label of a code block, form controls.
  var SKIP_BASE = 'button, script, style, svg, input, textarea, select, .code-head, [aria-hidden="true"]';

  function tw(key) {
    if (typeof window !== "undefined" && window.t) return window.t(key);
    try { return require("./i18n/vi.json")[key] || key; } catch (e) { return key; }
  }

  // ---- folding: only letters and digits count ----

  var cache = Object.create(null);
  function foldChar(ch) {
    var c = ch.charCodeAt(0);
    if (c < 128) {
      if ((c >= 48 && c <= 57) || (c >= 97 && c <= 122)) return ch;
      if (c >= 65 && c <= 90) return String.fromCharCode(c + 32);
      return "";
    }
    var f = cache[ch];
    if (f === undefined) f = cache[ch] = ch.toLowerCase().normalize("NFD").replace(/[^\p{L}\p{N}]/gu, "");
    return f;
  }
  function fold(s) {
    var out = "";
    for (var ch of String(s == null ? "" : s)) out += foldChar(ch);
    return out;
  }

  // The words a markdown quote shows on screen: what the renderer drops (hidden blocks, code fences, pictures, link
  // targets, list numbers and bullets, heading and quote marks) is dropped here too, so it does not break the match.
  function visible(md) {
    return String(md == null ? "" : md)
      .replace(/<!--[\s\S]*?(?:-->|$)/g, " ")
      .replace(/^[ \t]*(?:```|~~~).*$/gm, " ")
      .replace(/!\[\[[^\]]*\]\]/g, " ")
      .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
      .replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, function (all, note, label) { return label || note; })
      .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/^[ \t]*(?:>[ \t]?)*(?:#{1,6}[ \t]+|[-*+][ \t]+(?:\[[ xX]\][ \t]+)?|\d+[.)][ \t]+)?/gm, "");
  }

  // Where the folded quote sits in a folded message: {start, end, exact} (end excluded), or null.
  // `loose`: also accept the quote's first or last HEAD characters when the whole of it is not there.
  function findSpan(hay, needle, loose) {
    hay = String(hay || "");
    needle = String(needle || "");
    if (!needle || !hay) return null;
    var at = hay.indexOf(needle);
    if (at >= 0) return { start: at, end: at + needle.length, exact: true };
    if (!loose || needle.length <= HEAD) return null;
    var head = needle.slice(0, HEAD), tail = needle.slice(-HEAD);
    var s = hay.indexOf(head);
    if (s >= 0) {
      // Room for words the page shows that the quote does not (a code block's label, a list the renderer numbered).
      var reach = Math.round(needle.length * 1.5) + 200;
      var t = hay.indexOf(tail, s + 1);
      if (t >= 0 && t + HEAD - s <= reach) return { start: s, end: t + HEAD, exact: false };
      return { start: s, end: Math.min(hay.length, s + needle.length), exact: false };
    }
    var e = hay.indexOf(tail);
    if (e >= 0) return { start: Math.max(0, e + HEAD - needle.length), end: e + HEAD, exact: false };
    return null;
  }

  // ---- the DOM: folded text of a message, and where each folded character came from ----

  function textMap(roots, skip) {
    var parts = [], nodes = [], offs = [], lens = [];
    function walk(node) {
      for (var c = node.firstChild; c; c = c.nextSibling) {
        if (c.nodeType === 3) {
          var s = c.data, i = 0;
          while (i < s.length) {
            var code = s.codePointAt(i), w = code > 0xffff ? 2 : 1;
            var f = foldChar(s.substr(i, w));
            for (var k = 0; k < f.length; k++) { nodes.push(c); offs.push(i); lens.push(w); }
            if (f) parts.push(f);
            i += w;
          }
        } else if (c.nodeType === 1 && !(c.matches && c.matches(skip))) {
          walk(c);
        }
      }
    }
    (roots || []).forEach(function (r) { if (r) walk(r); });
    return { text: parts.join(""), nodes: nodes, offs: offs, lens: lens };
  }

  function rangeOf(map, span) {
    var first = map.nodes[span.start], last = map.nodes[span.end - 1];
    if (!first || !last) return null;
    var r = first.ownerDocument.createRange();
    r.setStart(first, map.offs[span.start]);
    r.setEnd(last, map.offs[span.end - 1] + map.lens[span.end - 1]);
    return r;
  }

  // The nearest message (in `cands`, nearest first) holding the folded quote: exact matches first, loose ones after.
  function locate(cands, needle, rootsOf, skip) {
    var maps = [];
    for (var pass = 0; pass < 2; pass++) {
      for (var i = 0; i < cands.length; i++) {
        var m = maps[i] || (maps[i] = textMap(rootsOf(cands[i]), skip));
        var span = findSpan(m.text, needle, pass === 1);
        if (span) {
          var range = rangeOf(m, span);
          if (range) return { el: cands[i], range: range, exact: span.exact };
        }
      }
    }
    return null;
  }

  // ---- showing it ----

  function reducedMotion() {
    try { return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches); } catch (e) { return false; }
  }

  function scrollParent(el) {
    for (var p = el && el.parentElement; p; p = p.parentElement) {
      var oy = "";
      try { oy = getComputedStyle(p).overflowY; } catch (e) { /* detached */ }
      if ((oy === "auto" || oy === "scroll") && p.scrollHeight > p.clientHeight) return p;
    }
    return document.scrollingElement || document.documentElement;
  }

  // Put the quoted words in the middle of the list; a quote taller than most of the list starts near its top.
  function scrollTo(scroller, range, el) {
    var r = range.getBoundingClientRect();
    if (!r || (!r.width && !r.height)) r = el.getBoundingClientRect();
    var box = scroller === document.scrollingElement || scroller === document.documentElement
      ? { top: 0 } : scroller.getBoundingClientRect();
    var h = scroller.clientHeight || window.innerHeight;
    var off = r.height > h * 0.6 ? 48 : Math.max(16, (h - r.height) / 2);
    var top = Math.max(0, scroller.scrollTop + (r.top - box.top) - off);
    if (scroller.scrollTo) scroller.scrollTo({ top: top, behavior: reducedMotion() ? "auto" : "smooth" });
    else scroller.scrollTop = top;
  }

  var timer = null, flashed = null, flashCls = "";
  function clearMark() {
    if (timer) { clearTimeout(timer); timer = null; }
    try { if (typeof CSS !== "undefined" && CSS.highlights) CSS.highlights.delete(MARK); } catch (e) { /* old browser */ }
    if (flashed) { flashed.classList.remove(flashCls); flashed = null; }
  }

  // Mark the words (CSS Custom Highlight API: nothing in the message is rewritten). A browser without it flashes the
  // whole message instead (opts.flashClass).
  function mark(range, el, opts) {
    clearMark();
    var done = false;
    try {
      if (typeof CSS !== "undefined" && CSS.highlights && typeof Highlight === "function") {
        CSS.highlights.set(MARK, new Highlight(range));
        done = true;
      }
    } catch (e) { done = false; }
    if (!done && el && opts.flashClass) {
      flashCls = opts.flashClass;
      el.classList.remove(flashCls);
      void el.offsetWidth;   // restart the animation when the same message is flashed twice in a row
      el.classList.add(flashCls);
      flashed = el;
    }
    timer = setTimeout(clearMark, SHOW_MS);
  }

  function note(text) {
    if (!text || typeof document === "undefined") return;
    var n = document.createElement("div");
    n.className = "mp-toast qj-note";   // the small floating note of msg-press.js, as wide as its words
    n.setAttribute("role", "status");
    n.textContent = text;
    document.body.appendChild(n);
    setTimeout(function () { n.remove(); }, 2200);
  }

  function show(hit, opts) {
    // A long user message collapsed to ten lines: open it first when the words sit in the hidden part.
    var node = hit.range.startContainer;
    var host = node && (node.nodeType === 1 ? node : node.parentElement);
    var clamped = host && host.closest && host.closest(".utext.clamped");
    if (clamped) {
      var more = hit.el.querySelector(".clamp-more");
      if (more) more.click();
    }
    if (opts.beforeScroll) { try { opts.beforeScroll(hit.el); } catch (e) { /* keep going */ } }
    var scroller = (typeof opts.scroller === "function" ? opts.scroller() : opts.scroller) || scrollParent(hit.el);
    scrollTo(scroller, hit.range, hit.el);
    mark(hit.range, hit.el, opts);
  }

  // Elements of `list` that come before `from` in the page, nearest first.
  function before(list, from) {
    var out = [];
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (el === from) break;
      if (from && from.compareDocumentPosition && !(from.compareDocumentPosition(el) & 2)) continue;   // 2: el precedes
      out.push(el);
    }
    return out.reverse();
  }

  var busy = false;
  // opts: quote (the quoted words, markdown), candidates() (message elements to search, nearest first), roots(el)
  // (the parts of a message holding its words; default its .bubble), skip (extra selector to leave out, e.g. the quote
  // block of another message), scroller (element or function), beforeScroll(el), loadOlder() (Promise of true when
  // older messages were added), flashClass, missingText. Returns a Promise of true when the words were found.
  function go(opts) {
    opts = opts || {};
    var needle = fold(visible(opts.quote));
    if (!needle || busy) return Promise.resolve(false);
    busy = true;
    var skip = SKIP_BASE + (opts.skip ? ", " + opts.skip : "");
    var rootsOf = opts.roots || function (el) { return [el.querySelector(".bubble") || el]; };
    var loads = 0;
    function end(ok) {
      busy = false;
      if (!ok) note(opts.missingText || tw("cact.quote_missing"));
      return ok;
    }
    function attempt() {
      var hit = null;
      try { hit = locate(opts.candidates ? opts.candidates() : [], needle, rootsOf, skip); } catch (e) { hit = null; }
      if (hit) {
        try { show(hit, opts); } catch (e) { /* found: a failed scroll is not "not found" */ }
        return Promise.resolve(end(true));
      }
      if (!opts.loadOlder || loads >= MAX_LOADS) return Promise.resolve(end(false));
      loads++;
      return Promise.resolve().then(opts.loadOlder).then(function (more) {
        return more ? attempt() : end(false);
      }, function () { return end(false); });
    }
    return attempt();
  }

  // True when the tap on a quote is really the end of selecting text in it (then it must not jump).
  function selecting(el) {
    try {
      var sel = window.getSelection && window.getSelection();
      return !!(sel && !sel.isCollapsed && el && el.contains(sel.anchorNode));
    } catch (e) { return false; }
  }

  var API = { HEAD: HEAD, MAX_LOADS: MAX_LOADS, MARK: MARK, fold: fold, visible: visible, findSpan: findSpan,
              textMap: textMap, locate: locate, before: before, go: go, clear: clearMark, selecting: selecting };
  if (typeof window !== "undefined") window.JavisQuoteJump = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})();
