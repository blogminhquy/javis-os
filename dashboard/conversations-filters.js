/* Bộ lọc dropdown của Hộp thư hội thoại (0.65.3), do conversations.js dùng.
 *
 * Chủ dự án (2026-09-30): chạy nhiều bot khác lĩnh vực thì hộp thư lẫn vào nhau, mà lọc bằng hàng nút bấm thì tốn
 * diện tích. Nên ba dropdown trên MỘT hàng chung với ô tìm: Bot, Tình trạng, Loại (nhóm hay chat riêng); dropdown
 * Kênh chỉ hiện khi hòm thư có từ 2 kênh. Số đếm nằm ngay trong từng lựa chọn, lấy từ `facets` của server (đếm trên
 * TOÀN hòm thư, không theo bộ lọc đang chọn) nên con số không nhảy mỗi lần lọc.
 *
 * File này chỉ giữ phần THUẦN (trạng thái, lưu trình duyệt, dựng chuỗi <option>, màu thẻ bot) để test được dưới node
 * mà không cần DOM. Vẽ và gắn sự kiện nằm ở conversations.js. Định danh mới đặt bằng tiếng Anh, chữ hiện ra lấy từ
 * từ điển (khoá `ht.f_*`). Ghi chú: KHÔNG dùng ký tự em dash. */
(function () {
  "use strict";

  var KEY = "javis.inbox.filters";
  // 2026-10-25, from the owner's Pancake screenshots: "waiting" is "need reply" sorted waiting-longest first ("đợi phản hồi
  // lâu nhất"), one more choice in the status dropdown. "The customer left a phone number or email" is its own on/off
  // filter (`contact`), so it combines with a status such as "need reply" (owner: "tách ô lọc riêng").
  // "hidden" (2026-10-25, row menu "Hide conversation"): only the chats the owner hid; every other choice leaves them out.
  var STATUSES = ["", "unread", "need_reply", "waiting", "human", "hidden"];
  var TYPES = ["", "group", "private"];
  var BOT_COLORS = 4;          // c0..c3 trong console.css; không dùng màu cảnh báo vì nó dành cho "cần trả lời" và "tôi lo"

  function tt(k, v) { return window.t(k, v); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // `tag`: an inbox tag id (string of digits). `contact`: "1" keeps only chats where the customer left a phone or email.
  function emptyState() { return { bot: "", status: "", type: "", channel: "", tag: "", contact: "" }; }

  // Giá trị lạ (bản cũ còn lưu, trình duyệt bị sửa tay) thì về "không lọc", không bao giờ làm hòm thư trống trơn.
  function sanitize(raw) {
    var r = raw && typeof raw === "object" ? raw : {};
    return {
      bot: typeof r.bot === "string" ? r.bot.slice(0, 80) : "",
      status: STATUSES.indexOf(r.status) >= 0 ? r.status : "",
      type: TYPES.indexOf(r.type) >= 0 ? r.type : "",
      channel: typeof r.channel === "string" ? r.channel.slice(0, 40) : "",
      tag: /^\d{1,9}$/.test(String(r.tag || "")) ? String(r.tag) : "",
      // A browser that saved "contact" as a status (the first 0.313.0 build) keeps the filter it chose.
      contact: r.contact === "1" || r.contact === true || r.status === "contact" ? "1" : "",
    };
  }

  // Bộ nhớ trình duyệt có thể trống, bị chặn hay ném lỗi (cửa sổ riêng tư): không có nó vẫn phải chạy.
  function load() {
    try { return sanitize(JSON.parse(window.localStorage.getItem(KEY) || "{}")); } catch (e) { return emptyState(); }
  }
  function save(state) {
    try { window.localStorage.setItem(KEY, JSON.stringify(sanitize(state))); } catch (e) { /* không lưu được thì thôi */ }
  }

  function activeCount(state) {
    var s = sanitize(state);
    return ["bot", "status", "type", "channel", "tag", "contact"].filter(function (k) { return !!s[k]; }).length;
  }

  // Phần query cho GET /conversations. Chỉ gửi khoá đang lọc; giá trị đã qua sanitize nên an toàn để ghép.
  function query(state) {
    var s = sanitize(state), q = "";
    if (s.bot) q += "&bot_id=" + encodeURIComponent(s.bot);
    if (s.status === "waiting") q += "&status=need_reply&sort=waiting";
    else if (s.status) q += "&status=" + encodeURIComponent(s.status);
    if (s.type) q += "&chat_type=" + encodeURIComponent(s.type);
    if (s.channel) q += "&channel=" + encodeURIComponent(s.channel);
    if (s.tag) q += "&tag=" + s.tag;
    if (s.contact) q += "&has_contact=1";
    return q;
  }

  // Màu thẻ tên bot: băm id nên một bot luôn cùng màu dù thêm hay bớt bot khác.
  function botColor(id) {
    var h = 0, s = String(id || "");
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return h % BOT_COLORS;
  }

  function opt(value, text, current) {
    return '<option value="' + esc(value) + '"' + (String(value) === String(current || "") ? " selected" : "") + '>' +
      esc(text) + '</option>';
  }
  function num(v) { return Number(v) || 0; }

  // `bots`: [{id, name, tong, ...}] do server cấp (chỉ bot có hội thoại). Sắp theo tên để thứ tự không đổi khi số đếm đổi.
  function botOptions(bots, facets, current) {
    var f = facets || {};
    var html = opt("", tt("ht.f_bot_all", { n: num(f.tong) }), current);
    var seen = {};
    (bots || []).slice().sort(function (a, b) {
      return String(a.name).localeCompare(String(b.name), "vi");
    }).forEach(function (b) {
      seen[b.id] = true;
      html += opt(b.id, b.name + " (" + num(b.tong) + ")", current);
    });
    var none = f.bots && f.bots[""];
    if (none) html += opt("-", tt("ht.f_bot_none", { n: num(none.tong) }), current);
    // Mở từ thẻ bot chưa có hội thoại nào: vẫn phải có lựa chọn ấy, kẻo dropdown hiện "Tất cả" mà danh sách đang lọc.
    if (current && current !== "-" && !seen[current]) html += opt(current, tt("ht.f_bot_picked"), current);
    return html;
  }

  function statusOptions(facets, current) {
    var s = (facets && facets.status) || {};
    return opt("", tt("ht.f_st_all"), current) +
      opt("unread", tt("ht.f_st_unread", { n: num(s.unread) }), current) +
      opt("need_reply", tt("ht.f_st_need", { n: num(s.need_reply) }), current) +
      opt("waiting", tt("ht.f_st_wait", { n: num(s.need_reply) }), current) +
      opt("human", tt("ht.f_st_human", { n: num(s.human) }), current) +
      opt("hidden", tt("ht.f_st_hidden", { n: num(s.hidden) }), current);
  }

  // Label of the "has phone/email" toggle, with the inbox-wide count like the dropdown options.
  function contactLabel(facets) {
    return tt("ht.f_st_contact", { n: num(facets && facets.has_contact) });
  }

  // Tag dropdown (2026-10-25). `tags`: [{id, name, color, count}] from the server, in the owner's order. A tag that was
  // deleted while selected still gets an option, so the dropdown never says "all" while the list is filtered.
  function tagOptions(tags, current) {
    var html = opt("", tt("ht.f_tag_all"), current), seen = false;
    (tags || []).forEach(function (g) {
      if (String(g.id) === String(current || "")) seen = true;
      html += opt(g.id, g.name + " (" + num(g.count) + ")", current);
    });
    if (current && !seen) html += opt(current, tt("ht.f_tag_gone"), current);
    return html;
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

  function typeOptions(facets, current) {
    var t = (facets && facets.type) || {};
    return opt("", tt("ht.f_type_all"), current) +
      opt("group", tt("ht.f_type_group", { n: num(t.group) }), current) +
      opt("private", tt("ht.f_type_private", { n: num(t.private) }), current);
  }

  // `byChannel`: {kênh: số hội thoại} (stats.theo_kenh); `labelOf(id)`: nhãn đọc được do server cấp.
  function channelOptions(byChannel, current, labelOf) {
    var by = byChannel || {};
    var ids = Object.keys(by);
    if (current && ids.indexOf(current) < 0) ids.push(current);
    var html = opt("", tt("ht.f_kenh_all"), current);
    ids.forEach(function (id) {
      html += opt(id, (labelOf ? labelOf(id) : id) + " (" + num(by[id]) + ")", current);
    });
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
    if (x.bot_id) {
      // Same two modes as the switch in the thread header: anything but "human" means the bot answers.
      var human = x.mode === "human";
      items.push({ sep: true, key: "ht.rm_mode" });
      items.push({ act: "mode_ai", icon: "sparkles", key: "ht.rm_mode_ai", on: !human, radio: true });
      items.push({ act: "mode_human", icon: "hand", key: "ht.rm_mode_human", on: human, radio: true });
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
    botColor: botColor, botOptions: botOptions, statusOptions: statusOptions, typeOptions: typeOptions,
    channelOptions: channelOptions, tagOptions: tagOptions, contactLabel: contactLabel, tagChips: tagChips, tagChip: tagChip, tagColor: tagColor,
    TAG_COLORS: TAG_COLORS, rowMenuItems: rowMenuItems, rowMenuHtml: rowMenuHtml, tagMenuHtml: tagMenuHtml,
  };
})();
