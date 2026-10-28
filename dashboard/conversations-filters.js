/* Filter state and row-menu data of the Chatbot page's Conversations tab, used by conversations.js.
 *
 * Bộ lọc của Hộp thư (0.65.3, chủ dự án 2026-09-30: nhiều bot khác lĩnh vực thì hộp thư lẫn vào nhau). Since Chatbot v5
 * (2026-10-28, docs/dev/2026-10-chatbot-v5-spec.md) the controls are the channel picker, the quick "who is handling it"
 * filters and the two-level Filter menu (their HTML is in inbox-v5.js); this file keeps the state they share, what is
 * saved in the browser, the query sent to GET /conversations, the tag chips and the "..." menu of a row.
 *
 * Pure functions, testable under node without a DOM. Drawing and events stay in conversations.js. Ghi chú: KHÔNG dùng
 * ký tự em dash. */
(function () {
  "use strict";

  var KEY = "javis.inbox.filters";
  // 2026-10-25, from the owner's Pancake screenshots: "waiting" is "need reply" sorted waiting-longest first ("đợi phản hồi
  // lâu nhất"), one more choice in the status dropdown. "The customer left a phone number or email" is its own on/off
  // filter (`contact`), so it combines with a status such as "need reply" (owner: "tách ô lọc riêng").
  // "hidden" (2026-10-25, row menu "Hide conversation"): only the chats the owner hid; every other choice leaves them out.
  var STATUSES = ["", "unread", "need_reply", "waiting", "human", "hidden"];
  // Chatbot v5 (2026-10-28): the quick filters above the list say WHO is handling a chat (server `inbox_state`), and the
  // channel picker ticks several accounts. "need_reply" and "human" moved there ("Needs you", "You are handling");
  // a browser that saved them is moved over by `sanitize`.
  var WHOS = ["", "you", "ai", "owner"];
  var TYPES = ["", "group", "private"];
  // Owner, 2026-10-28 ("lọc như kia hơi ít"): when the last message came (a quick range or days picked on the calendar,
  // date-range.js), who wrote it, and pinned chats only.
  var LAST_BY = ["", "customer", "ai", "human"];
  var RANGES = ["today", "yesterday", "d7", "d30", "d90", "last_month", "week", "month"];
  function cleanWhen(w) {
    if (!w || typeof w !== "object") return null;
    if (RANGES.indexOf(w.preset) >= 0) return { preset: w.preset };
    var re = /^\d{4}-\d{2}-\d{2}$/;
    if (re.test(String(w.from || "")) && re.test(String(w.to || ""))) return w.from <= w.to ? { from: w.from, to: w.to } : { from: w.to, to: w.from };
    return null;
  }

  function tt(k, v) { return window.t(k, v); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // `contact`: "1" keeps only chats where the customer left a phone or email. `who`: the quick filter ("" = everyone),
  // `accs`: ticked channel account keys, `tagsAny` / `tagsNone`: tag ids (strings of digits) a chat must have / must not have.
  function emptyState() {
    return { bot: "", status: "", type: "", channel: "", contact: "", who: "", accs: [], tagsAny: [], tagsNone: [],
             when: null, lastBy: "", pinned: "" };
  }
  function idList(v, re, max) {
    return (Array.isArray(v) ? v : []).map(String).filter(function (x, i, a) { return re.test(x) && a.indexOf(x) === i; }).slice(0, max);
  }

  // Giá trị lạ (bản cũ còn lưu, trình duyệt bị sửa tay) thì về "không lọc", không bao giờ làm hòm thư trống trơn.
  function sanitize(raw) {
    var r = raw && typeof raw === "object" ? raw : {};
    var status = STATUSES.indexOf(r.status) >= 0 ? r.status : "";
    // A pre-v5 browser that saved "need reply" or "I handle it" as a status gets the matching quick filter.
    var who = WHOS.indexOf(r.who) >= 0 ? r.who : (status === "need_reply" ? "you" : status === "human" ? "owner" : "");
    if (status === "need_reply" || status === "human") status = "";
    var tagsAny = idList(r.tagsAny, /^\d{1,9}$/, 50);
    if (/^\d{1,9}$/.test(String(r.tag || "")) && tagsAny.indexOf(String(r.tag)) < 0) tagsAny.push(String(r.tag));
    return {
      bot: typeof r.bot === "string" ? r.bot.slice(0, 80) : "",
      status: status,
      type: TYPES.indexOf(r.type) >= 0 ? r.type : "",
      channel: typeof r.channel === "string" ? r.channel.slice(0, 40) : "",
      // A browser that saved "contact" as a status (the first 0.313.0 build) keeps the filter it chose.
      contact: r.contact === "1" || r.contact === true || r.status === "contact" ? "1" : "",
      who: who,
      accs: idList(r.accs, /^[A-Za-z0-9_.:@+-]{1,120}$/, 200),
      tagsAny: tagsAny,
      tagsNone: idList(r.tagsNone, /^\d{1,9}$/, 50),
      when: cleanWhen(r.when),
      lastBy: LAST_BY.indexOf(r.lastBy) >= 0 ? r.lastBy : "",
      pinned: r.pinned === "1" || r.pinned === true ? "1" : "",
    };
  }

  // Bộ nhớ trình duyệt có thể trống, bị chặn hay ném lỗi (cửa sổ riêng tư): không có nó vẫn phải chạy.
  // Nothing saved about "who" yet (first visit, or a browser from before v5): the list opens on "Needs you".
  function load() {
    var raw = null;
    try { raw = JSON.parse(window.localStorage.getItem(KEY) || "{}"); } catch (e) { raw = null; }
    var s = sanitize(raw);
    if (!(raw && typeof raw === "object" && "who" in raw) && !s.who) s.who = "you";
    return s;
  }
  function save(state) {
    try { window.localStorage.setItem(KEY, JSON.stringify(sanitize(state))); } catch (e) { /* không lưu được thì thôi */ }
  }

  // How many filters the "Filter" menu holds (the quick "who" filters and the channel picker have their own controls).
  function activeCount(state) {
    var s = sanitize(state);
    return ["bot", "status", "type", "channel", "contact", "when", "lastBy", "pinned"].filter(function (k) { return !!s[k]; }).length +
      s.tagsAny.length + s.tagsNone.length;
  }

  // Phần query cho GET /conversations. Chỉ gửi khoá đang lọc; giá trị đã qua sanitize nên an toàn để ghép.
  function query(state) {
    var s = sanitize(state), q = "";
    if (s.bot) q += "&bot_id=" + encodeURIComponent(s.bot);
    if (s.status === "waiting") q += "&status=need_reply&sort=waiting";
    else if (s.status) q += "&status=" + encodeURIComponent(s.status);
    if (s.type) q += "&chat_type=" + encodeURIComponent(s.type);
    if (s.channel) q += "&channel=" + encodeURIComponent(s.channel);
    if (s.contact) q += "&has_contact=1";
    if (s.who) q += "&who=" + s.who;
    if (s.accs.length) q += "&account_ids=" + encodeURIComponent(s.accs.join(","));
    if (s.tagsAny.length) q += "&tags_any=" + s.tagsAny.join(",");
    if (s.tagsNone.length) q += "&tags_none=" + s.tagsNone.join(",");
    // A quick range is turned into days at every request, so "last 7 days" moves with the calendar.
    var DR = window.JavisDateRange, d = s.when && (DR ? DR.dates(s.when) : s.when.from ? s.when : null);
    if (d && d.from && d.to) q += "&from=" + d.from + "&to=" + d.to;
    if (s.lastBy) q += "&last_by=" + s.lastBy;
    if (s.pinned) q += "&pinned=1";
    return q;
  }

  // The fixed tag palette (server conversations.TAG_COLORS); an unknown colour draws grey.
  var TAG_COLORS = ["gray", "red", "orange", "yellow", "green", "teal", "blue", "purple", "pink"];
  function tagColor(c) { return TAG_COLORS.indexOf(c) >= 0 ? c : "gray"; }
  function tagChip(g) {
    return '<span class="ht-tag" data-c="' + tagColor(g.color) + '" title="' + esc(g.name) + '">' + esc(g.name) + '</span>';
  }
  // Chips on a list row: the first `max` tags, then "+N" for the rest (named in its tooltip).
  function tagChips(tags, max) {
    var list = tags || [], m = max || 2;
    var html = list.slice(0, m).map(tagChip).join("");
    if (list.length > m) {
      var rest = list.slice(m).map(function (g) { return g.name; }).join(", ");
      html += '<span class="ht-tag-more" title="' + esc(rest) + '">+' + (list.length - m) + '</span>';
    }
    return html;
  }

  // ---- the "..." menu of a conversation row (owner, 2026-10-25, like Zalo's row menu) ----
  // What the menu offers for one conversation, in order. Pure data so node can test it; conversations.js draws it and
  // runs the actions. Item: {act, icon, key (i18n), sub (second line), on (true/false = a checkable row), more (opens a
  // second view)}; {sep: true, key} is a divider with an optional small heading.
  function rowMenuItems(c) {
    var x = c || {}, items = [];
    items.push(x.unread_count > 0 ? { act: "read", icon: "mail-open", key: "ht.rm_read" }
                                  : { act: "unread", icon: "mail", key: "ht.rm_unread" });
    items.push(x.pinned ? { act: "unpin", icon: "pin-off", key: "ht.rm_unpin" } : { act: "pin", icon: "pin", key: "ht.rm_pin" });
    var nTags = (x.tags || []).length;
    items.push({ act: "tags", icon: "tag", key: "ht.rm_tags", more: true, sub: nTags ? (x.tags || []).map(function (g) { return g.name; }).join(", ") : "" });
    if (x.bot_id && x.ai_allowed !== false) {
      // Same three modes as the "Who replies" bar of the chat (Chatbot v5): A.I. replies, A.I. drafts and I approve, I reply.
      var mode = x.mode === "human" ? "human" : x.mode === "draft" ? "draft" : "ai";
      items.push({ sep: true, key: "ht.rm_mode" });
      items.push({ act: "mode_ai", icon: "sparkles", key: "ht.rm_mode_ai", on: mode === "ai", radio: true });
      items.push({ act: "mode_draft", icon: "pen-line", key: "ib.m_draft", on: mode === "draft", radio: true });
      items.push({ act: "mode_human", icon: "hand", key: "ht.rm_mode_human", on: mode === "human", radio: true });
    }
    if (x.contact) {
      var mail = String(x.contact).indexOf("@") > 0;
      items.push({ sep: true });
      items.push({ act: "copy", icon: mail ? "mail" : "phone", key: mail ? "ht.rm_copy_email" : "ht.rm_copy_phone", sub: String(x.contact) });
    }
    items.push({ sep: true });
    items.push(x.hidden ? { act: "unhide", icon: "eye", key: "ht.rm_unhide" }
                        : { act: "hide", icon: "eye-off", key: "ht.rm_hide", sub: tt("ht.rm_hide_sub") });
    return items;
  }

  // HTML of the menu's rows. `icon(name)` draws a Lucide icon (window.ic); `done` is the act that just finished and
  // shows its confirmation instead of its label (copy: "Copied").
  function rowMenuHtml(items, icon, done) {
    var I = icon || function () { return ""; };
    return (items || []).map(function (it) {
      if (it.sep) return '<div class="ht-rm-sep" role="separator"></div>' + (it.key ? '<div class="ht-rm-h">' + esc(tt(it.key)) + '</div>' : "");
      var checkable = typeof it.on === "boolean";
      var role = checkable ? (it.radio ? "menuitemradio" : "menuitemcheckbox") : "menuitem";
      var ok = done && done === it.act;
      return '<button type="button" class="ht-rm-it' + (it.on ? " on" : "") + (ok ? " done" : "") + '" role="' + role + '" data-act="' + esc(it.act) + '"' +
        (checkable ? ' aria-checked="' + it.on + '"' : "") + (it.more ? ' aria-haspopup="menu"' : "") + '>' +
        '<span class="ht-rm-ic">' + I(ok ? "check" : it.icon) + '</span>' +
        '<span class="ht-rm-t"><span>' + esc(tt(ok ? "ht.rm_copied" : it.key)) + '</span>' +
          (it.sub && !ok ? '<small>' + esc(it.sub) + '</small>' : "") + '</span>' +
        (checkable ? '<span class="ht-rm-end">' + (it.on ? I("check") : "") + '</span>' : it.more ? '<span class="ht-rm-end">' + I("chevron-right") + '</span>' : "") +
      '</button>';
    }).join("");
  }

  // The "Tags" view of the menu: a back row, then one checkbox row per tag (the owner's order), then "New tag".
  function tagMenuHtml(tags, onTags, icon) {
    var I = icon || function () { return ""; }, on = {};
    (onTags || []).forEach(function (g) { on[g.id] = true; });
    var rows = (tags || []).map(function (g) {
      var y = !!on[g.id];
      return '<button type="button" class="ht-rm-it ht-rm-tag' + (y ? " on" : "") + '" role="menuitemcheckbox" aria-checked="' + y +
        '" data-act="tag" data-tag="' + esc(g.id) + '">' +
        '<span class="ht-tag-check">' + (y ? I("check") : "") + '</span>' + tagChip(g) + '</button>';
    }).join("");
    return '<button type="button" class="ht-rm-it ht-rm-back" role="menuitem" data-act="back">' +
        '<span class="ht-rm-ic">' + I("chevron-left") + '</span><span class="ht-rm-t"><span>' + esc(tt("ht.rm_back")) + '</span></span></button>' +
      '<div class="ht-rm-sep" role="separator"></div>' +
      (rows || '<div class="ht-rm-none">' + esc(tt("ht.rm_tags_none")) + '</div>') +
      '<div class="ht-rm-sep" role="separator"></div>' +
      '<button type="button" class="ht-rm-it" role="menuitem" data-act="tag_new"><span class="ht-rm-ic">' + I("plus") + '</span>' +
        '<span class="ht-rm-t"><span>' + esc(tt("ht.rm_tag_new")) + '</span></span></button>';
  }

  window.JavisConvFilters = {
    emptyState: emptyState, sanitize: sanitize, load: load, save: save, activeCount: activeCount, query: query,
    tagChips: tagChips, tagChip: tagChip, tagColor: tagColor,
    TAG_COLORS: TAG_COLORS, rowMenuItems: rowMenuItems, rowMenuHtml: rowMenuHtml, tagMenuHtml: tagMenuHtml, WHOS: WHOS,
  };
})();
