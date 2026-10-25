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
  // lâu nhất") and "contact" is "the customer left a phone number or email" ("lọc có SĐT"). Both are one more choice in
  // the status dropdown, as in Pancake's single-choice filter list, so the filter row stays one row.
  var STATUSES = ["", "unread", "need_reply", "waiting", "human", "contact"];
  var TYPES = ["", "group", "private"];
  var BOT_COLORS = 4;          // c0..c3 trong console.css; không dùng màu cảnh báo vì nó dành cho "cần trả lời" và "tôi lo"

  function tt(k, v) { return window.t(k, v); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // `tag`: an inbox tag id (string of digits).
  function emptyState() { return { bot: "", status: "", type: "", channel: "", tag: "" }; }

  // Giá trị lạ (bản cũ còn lưu, trình duyệt bị sửa tay) thì về "không lọc", không bao giờ làm hòm thư trống trơn.
  function sanitize(raw) {
    var r = raw && typeof raw === "object" ? raw : {};
    return {
      bot: typeof r.bot === "string" ? r.bot.slice(0, 80) : "",
      status: STATUSES.indexOf(r.status) >= 0 ? r.status : "",
      type: TYPES.indexOf(r.type) >= 0 ? r.type : "",
      channel: typeof r.channel === "string" ? r.channel.slice(0, 40) : "",
      tag: /^\d{1,9}$/.test(String(r.tag || "")) ? String(r.tag) : "",
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
    return ["bot", "status", "type", "channel", "tag"].filter(function (k) { return !!s[k]; }).length;
  }

  // Phần query cho GET /conversations. Chỉ gửi khoá đang lọc; giá trị đã qua sanitize nên an toàn để ghép.
  function query(state) {
    var s = sanitize(state), q = "";
    if (s.bot) q += "&bot_id=" + encodeURIComponent(s.bot);
    if (s.status === "waiting") q += "&status=need_reply&sort=waiting";
    else if (s.status === "contact") q += "&has_contact=1";
    else if (s.status) q += "&status=" + encodeURIComponent(s.status);
    if (s.type) q += "&chat_type=" + encodeURIComponent(s.type);
    if (s.channel) q += "&channel=" + encodeURIComponent(s.channel);
    if (s.tag) q += "&tag=" + s.tag;
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
      opt("contact", tt("ht.f_st_contact", { n: num(facets && facets.has_contact) }), current);
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

  window.JavisConvFilters = {
    emptyState: emptyState, sanitize: sanitize, load: load, save: save, activeCount: activeCount, query: query,
    botColor: botColor, botOptions: botOptions, statusOptions: statusOptions, typeOptions: typeOptions,
    channelOptions: channelOptions, tagOptions: tagOptions, tagChips: tagChips, tagChip: tagChip, tagColor: tagColor,
    TAG_COLORS: TAG_COLORS,
  };
})();
