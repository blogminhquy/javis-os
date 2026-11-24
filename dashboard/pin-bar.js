/* pin-bar.js - the pinned messages bar above a chat (2026-11-24).

   Owner, 2026-11-24, with three Zalo screenshots: "Trong cuộc hội thoại thì có thể ghim các tin lên trên đầu, để dễ
   dàng tìm lại các tin ghim", then "cả cộng sự cả hội thoại". Like Zalo:

   - One bar above the messages shows the first pin: a chat icon, "Message", then "Who: text" on one line. "+N pinned"
     opens the whole list when there is more than one; "..." beside a pin offers "Move to top" and "Unpin".
   - The open list ("Pinned messages (N)", "Collapse") lies over the messages, so opening it never pushes them down.
   - A tap on a pin goes to the message (the host loads older pages until it is there, then lights it up).

   Two hosts: the Chatbot page's customer chats (conversations.js, pins in `conversations` metadata.pins) and the main
   chat of Partners and Chat (chat-pins.js, the `message_pins` table of the session store). Both hand over a list,
   first = the one the bar shows; this file only builds HTML from it, so node tests can run it
   (tests/js/test_inbox_pins.js, tests/js/test_chat_pins.js). Looks: pin-bar.css. */
(function () {
  "use strict";

  function tw(k, v) {
    if (typeof window !== "undefined" && window.t) return window.t(k, v);
    try {
      var s = require("./i18n/vi.json")[k] || k;
      return String(s).replace(/\{(\w+)\}/g, function (m, n) { return (v && v[n] != null) ? String(v[n]) : m; });
    } catch (e) { return k; }
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function media() {
    if (typeof window !== "undefined" && window.JavisHtMedia) return window.JavisHtMedia;
    try { return require("./ht-media.js"); } catch (e) { return null; }
  }

  // What a pin says after "Who:": a photo reads "Photo" (with its caption), a file its name, text its first words on
  // one line. `icon` is drawn in front of the words (the photo icon Zalo puts before "Ảnh").
  function preview(p) {
    p = p || {};
    var M = media();
    var pt = M ? M.phanTich(p, p.conversation_id) : null;
    if (pt && pt.anh) return { icon: "image", text: tw("pin.photo") + (pt.chu ? ": " + oneLine(pt.chu) : "") };
    if (pt && pt.file) return { icon: "paperclip", text: pt.file.ten };
    var s = oneLine(M && M.tomTat ? M.tomTat(p.text || "", tw) : p.text || "");
    if (!s && p.message_type && p.message_type !== "text") {
      return { icon: p.message_type === "audio" ? "mic" : "paperclip", text: p.message_type };
    }
    return { icon: "", text: s };
  }
  function oneLine(s) { return String(s == null ? "" : s).replace(/\s+/g, " ").trim(); }

  // An answer of the main chat is markdown: the first line with words, without the marks around them (#, **, `, >,
  // list bullets, a link's address), so "## Báo cáo **tuần**" reads "Báo cáo tuần".
  function plain(md) {
    var lines = String(md == null ? "" : md).replace(/```[\s\S]*?```/g, " ").split(/\n/);
    for (var i = 0; i < lines.length; i++) {
      var s = lines[i].replace(/^\s{0,3}(#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)/, "")
        .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/(\*\*|__|\*|~~|`)/g, "").replace(/<[^>]+>/g, "");
      s = oneLine(s);
      if (s && !/^[-=|:\s]+$/.test(s)) return s;
    }
    return "";
  }

  // One pin: the part that goes to the message, then its "...". `who` names the sender (conversations.js knows the
  // chat, the agent's name and the generic names to skip). `menu`: this pin's menu is open; `first`: it is already on
  // top, so the menu has no "Move to top".
  function rowHtml(p, o) {
    var ic = o.ic || function () { return ""; };
    var pv = o.preview ? o.preview(p) : preview(p);
    var who = o.who ? o.who(p) : (p.sender_name || "");
    var mid = esc(p.message_id);
    var line = (who ? esc(who) + ": " : "") + (pv.icon ? '<span class="pb-mic">' + ic(pv.icon) + "</span>" : "") + esc(pv.text);
    var label = tw("pin.go", { text: (who ? who + ": " : "") + pv.text });
    var menu = o.menu ? '<div class="pb-menu" role="menu">' +
        (o.first ? "" : '<button type="button" role="menuitem" class="pb-mi" data-pin-act="top" data-mid="' + mid + '">' +
          esc(tw("pin.top")) + "</button>") +
        '<button type="button" role="menuitem" class="pb-mi danger" data-pin-act="unpin" data-mid="' + mid + '">' +
          esc(tw("pin.unpin")) + "</button></div>" : "";
    return '<div class="pb-row' + (p.gone ? " gone" : "") + (o.menu ? " menu-on" : "") + '">' +
      '<button type="button" class="pb-go" data-pin-go="' + mid + '" aria-label="' + esc(label) + '" title="' +
        esc(p.gone ? tw("pin.gone") : label) + '">' +
        '<span class="pb-ic" aria-hidden="true">' + ic("message-circle") + "</span>" +
        '<span class="pb-t"><b>' + esc(tw("pin.kind")) + '</b><span class="pb-line">' + line + "</span></span></button>" +
      (o.more || "") +
      '<button type="button" class="pb-dots" data-pin-menu="' + mid + '" aria-haspopup="menu" aria-expanded="' +
        (o.menu ? "true" : "false") + '" aria-label="' + esc(tw("pin.opts")) + '" title="' + esc(tw("pin.opts")) + '">' +
        ic("ellipsis") + "</button>" + menu + "</div>";
  }

  // The whole bar. `o`: {open, menu (message id whose menu is open), ic, who, preview}. Empty list = "" (no bar).
  function barHtml(pins, o) {
    pins = pins || [];
    o = o || {};
    if (!pins.length) return "";
    var ic = o.ic || function () { return ""; };
    var n = pins.length;
    var more = n > 1 ? '<button type="button" class="pb-more" aria-expanded="' + (o.open ? "true" : "false") + '">' +
      esc(tw("pin.more", { n: n - 1 })) + ic("chevron-down") + "</button>" : "";
    var row = function (p, i, extra) {
      return rowHtml(p, { ic: ic, who: o.who, preview: o.preview, menu: String(o.menu) === String(p.message_id), first: i === 0, more: extra });
    };
    var bar = '<div class="pb-bar">' + row(pins[0], 0, more) + "</div>";
    if (!o.open || n < 2) return bar;
    return bar + '<div class="pb-panel" role="region" aria-label="' + esc(tw("pin.title", { n: n })) + '">' +
      '<div class="pb-head"><b>' + esc(tw("pin.title", { n: n })) + "</b>" +
      '<button type="button" class="pb-less" aria-expanded="true">' + esc(tw("pin.less")) + ic("chevron-up") + "</button></div>" +
      '<div class="pb-list">' + pins.map(function (p, i) { return row(p, i, ""); }).join("") + "</div></div>";
  }

  // A cheap fingerprint of the list: the bar is redrawn only when it changes (the 5-second poll brings it every time).
  function sig(pins) {
    return (pins || []).map(function (p) { return p.message_id + ":" + (p.gone ? 1 : 0) + ":" + (p.sender_name || "") + ":" + String(p.text || "").slice(0, 80); }).join(",");
  }

  var api = { preview: preview, plain: plain, rowHtml: rowHtml, barHtml: barHtml, sig: sig };
  if (typeof window !== "undefined") window.JavisPinBar = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
