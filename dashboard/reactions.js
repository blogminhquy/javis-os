/* Sáu reaction dùng chung (T2, 0.154.0): chat nhóm (teams.js) và chat riêng (chat-reactions.js, gọi từ app.js).

   Hợp đồng: docs/dev/team-chat-t2-contract.md mục 1, 2, 3 và 6. File này là NƠI DUY NHẤT của repo chứa bảng sáu emoji
   (test_icons.py cho phép đúng sáu ký tự đó, chỉ trong bảng EMOJI dưới đây).

   - Bỏ emoji gửi `value: "none"`. Từ 0.177.0 giao diện chỉ còn emoji (nút Thích ở góc bong bóng kiểu Zalo, cornerHtml); lý do, trục nói/im
     và góp ý vẫn được route nhận nhưng luôn gửi rỗng.
   - Trạng thái (`status`) do host ghi; giao diện chỉ hiện nhãn qua i18n và câu `status_reason` host viết sẵn.
   - Chống trùng: mỗi thao tác một `nonce`, giữ tới khi có kết quả; lỗi mạng (hay 5xx) thì gửi lại đúng nonce cũ, thành
     công hay lỗi 4xx thì thao tác sau dùng nonce mới (`nonceKeeper`).

   Các hàm *Html, nextReaction, payload, nonceKeeper thuần (không DOM, không mạng) để test chạy dưới node.
   `prefix` của opts đặt họ class: "tm" cho trang Nhóm (giữ nguyên markup cũ), mặc định "jr" cho chat riêng. */
(function () {
  "use strict";

  function tw(khoa, bien) {
    if (typeof window !== "undefined" && window.t) return window.t(khoa, bien);
    try {
      var s = require("./i18n/vi.json")[khoa] || khoa;
      return String(s).replace(/\{(\w+)\}/g, function (m, ten) {
        return (bien && bien[ten] != null) ? String(bien[ten]) : m;
      });
    } catch (e) { return khoa; }
  }

  function esc(t) {
    return String(t == null ? "" : t)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // Sáu reaction (spec 2026-10-13-team-chat-design mục 14.1, giữ đúng mã cũ để dữ liệu cũ còn đọc được). Emoji ở đây là
  // DỮ LIỆU sản phẩm (giá trị chủ chọn, lưu nguyên loại), không phải icon trang trí.
  var EMOJI = [
    { value: "like", emoji: "👍", key: "teams.react.like" },
    { value: "love", emoji: "❤️", key: "teams.react.love" },
    { value: "haha", emoji: "😂", key: "teams.react.haha" },
    { value: "wow", emoji: "😮", key: "teams.react.wow" },
    { value: "sad", emoji: "😢", key: "teams.react.sad" },
    { value: "angry", emoji: "😡", key: "teams.react.angry" }
  ];
  // Khoá viết TRỌN (không ghép chuỗi) để bộ kiểm i18n đọc được từng khoá đang dùng.
  var REASONS = [
    { value: "on_point", key: "teams.reason.on_point" },
    { value: "wrong_facts", key: "teams.reason.wrong_facts" },
    { value: "missing", key: "teams.reason.missing" },
    { value: "too_long", key: "teams.reason.too_long" },
    { value: "unclear", key: "teams.reason.unclear" },
    { value: "off_topic", key: "teams.reason.off_topic" }
  ];
  // Trục nói/im (spec 8.4): một nhóm chọn một, tách khỏi nhóm lý do chất lượng. "" là không chọn.
  var AXES = [
    { value: "should_speak", key: "react.axis.should_speak" },
    { value: "should_silent", key: "react.axis.should_silent" }
  ];
  var STATUS_KEY = { received: "react.status.received", pending_review: "react.status.pending_review",
    reviewing: "react.status.reviewing", adjusted: "react.status.adjusted", no_change: "react.status.no_change",
    waiting_quota: "react.status.waiting_quota", stored_only: "react.status.stored_only" };
  var COMMENT_MAX = 500;
  var LONG_PRESS_MS = 500;

  function find(list, value) {
    for (var i = 0; i < list.length; i++) if (list[i].value === value) return list[i];
    return null;
  }
  function emojiOf(value) { return find(EMOJI, value); }

  // Chọn lại emoji đang chọn là bỏ; chọn cái khác là đổi (spec 14.1).
  function nextReaction(cur, pick) {
    return cur === pick ? "none" : pick;
  }

  function pfx(opts) { return (opts && opts.prefix) || "jr"; }

  // Thân gửi lên route reaction (chưa có nonce). Giá trị lạ bị bỏ ở đây luôn để chữ ký chống trùng ổn định.
  function payload(value, reasons, axis, comment, seenSha) {
    var v = value && emojiOf(value) ? value : "none";
    var rs = [];
    (reasons || []).forEach(function (x) { if (find(REASONS, x) && rs.indexOf(x) < 0) rs.push(x); });
    var body = { value: v, reasons: rs, axis: find(AXES, axis) ? axis : "",
      comment: String(comment || "").trim().slice(0, COMMENT_MAX) };
    if (seenSha) body.seen_sha = String(seenSha);
    return body;
  }

  function newNonce() {
    try {
      if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
    } catch (e) { /* trình duyệt cũ: rơi xuống dưới */ }
    return "r" + Date.now().toString(36) + Math.random().toString(36).slice(2, 12);
  }

  // Giữ nonce theo thao tác. `take(key, body)`: cùng tin, cùng thân với lần gửi chưa có kết quả thì dùng lại nonce cũ
  // (thử lại sau lỗi mạng); thân khác là thao tác mới, nonce mới. `settle(key, code)`: code 0 (lỗi mạng) hay >= 500 thì
  // giữ để lần thử lại dùng đúng nonce đó; 2xx hay 4xx thì bỏ.
  function nonceKeeper(gen) {
    var pending = {};
    var make = gen || newNonce;
    return {
      take: function (key, body) {
        var sig = JSON.stringify(body || {});
        var cur = pending[key];
        if (cur && cur.sig === sig) return cur.nonce;
        pending[key] = { sig: sig, nonce: make() };
        return pending[key].nonce;
      },
      settle: function (key, code) {
        var c = Number(code) || 0;
        if (c === 0 || c >= 500) return;
        delete pending[key];
      },
      has: function (key) { return !!pending[key]; }
    };
  }

  // 0.177.0 (owner, 2026-10-16): reactions are plain emoji like Zalo, in BOTH chats. The reasons, talk/silent axis and
  // comment panel and the host status label are gone from the screen (the route still accepts them; the UI always sends
  // them empty). To correct an answer the owner replies to it.

  // Six emoji in one floating pill. opts: prefix.
  function barHtml(mid, cur, opts) {
    var p = pfx(opts), m = esc(mid);
    return '<div class="' + p + '-rx-bar" role="toolbar" aria-label="' + esc(tw("teams.react")) + '">' + EMOJI.map(function (r) {
      var on = cur === r.value;
      return '<button type="button" class="' + p + '-rx-pick" data-react="' + r.value + '" data-mid="' + m + '" aria-pressed="' +
        (on ? "true" : "false") + '" aria-label="' + esc(tw(r.key)) + '" title="' + esc(tw(r.key)) + '">' + r.emoji + "</button>";
    }).join("") + "</div>";
  }

  // Reaction corner at the bottom right of an answer bubble, like Zalo: the chosen emoji, or an outline thumbs-up. Press it:
  // like (or remove the reaction already there). Hover it (long press on a phone): the six emoji. opts: prefix, last (the
  // latest answer keeps its button visible), open (pill shown without hover), icon (outline thumbs-up html).
  function cornerHtml(mid, R, opts) {
    opts = opts || {};
    var p = pfx(opts), m = esc(mid);
    var cur = R && R.value && R.value !== "none" ? R.value : "";
    var e = cur ? emojiOf(cur) : null;
    var label = e ? tw("teams.react_remove", { what: tw(e.key) }) : tw("teams.react.like");
    return '<div class="' + p + '-rx' + (e ? " has" : "") + (opts.last ? " is-last" : "") + (opts.open ? " is-open" : "") + '">' +
      '<button type="button" class="' + p + '-rx-btn" data-rx-toggle="' + m + '" aria-label="' + esc(label) + '" title="' +
      esc(e ? tw(e.key) : tw("teams.react.like")) + '">' +
      (e ? '<span class="' + p + '-rx-emoji">' + e.emoji + "</span>" : (opts.icon || "")) + "</button>" +
      barHtml(mid, cur, opts) + "</div>";
  }

  // The value a press on the corner sends: like when nothing is there, "none" when a reaction is there.
  function cornerToggle(R) {
    return R && R.value && R.value !== "none" ? "none" : "like";
  }

  // Reaction của trưởng nhóm, thành viên (hợp đồng mục 5): chip CHỈ ĐỌC có tên agent, tách khỏi chip của chủ.
  function agentChipsHtml(list, opts) {
    var p = pfx(opts);
    var rows = (list || []).filter(function (a) {
      return a && (emojiOf(a.value) || (a.reasons || []).length || a.comment);
    });
    if (!rows.length) return "";
    return '<div class="' + p + '-react-agents">' + rows.map(function (a) {
      var r = emojiOf(a.value);
      var name = a.name || a.agent_key || "?";
      var what = [];
      if (r) what.push(tw(r.key));
      (a.reasons || []).forEach(function (x) { var rr = find(REASONS, x); if (rr) what.push(tw(rr.key)); });
      if (a.comment) what.push(String(a.comment).slice(0, COMMENT_MAX));
      var label = tw("react.agent_chip", { name: name, what: what.join(", ") });
      // Trình đọc màn hình đọc chữ ẩn (aria-label trên span trơn không chắc được đọc); phần nhìn thấy thì ẩn khỏi nó.
      return '<span class="' + p + '-react-agent" title="' + esc(label) + '"><span aria-hidden="true">' +
        (r ? '<span class="' + p + '-react-emoji">' + r.emoji + "</span>" : "") + esc(name) +
        ((a.reasons || []).length && !r ? " " + esc(tw("teams.react_reasons_n", { n: a.reasons.length })) : "") +
        '</span><span class="' + p + '-react-sr">' + esc(label) + "</span></span>";
    }).join("") + "</div>";
  }

  // Nhấn giữ 500 ms trên máy chạm (chuột thì bỏ qua, giữ chuột để bôi chữ như thường). Rung tay quá 10px là huỷ. Lần giữ đã
  // mở bảng thì chặn menu ngữ cảnh mặc định của máy chạm cho đúng lần đó. Trả hàm gỡ.
  function bindLongPress(root, selector, onOpen) {
    if (!root || !root.addEventListener) return function () {};
    var hold = null, hx = 0, hy = 0, held = false;
    var stop = function () { clearTimeout(hold); hold = null; };
    var down = function (e) {
      // iOS không bắn contextmenu sau lần giữ: hạ cờ ở lần chạm kế tiếp để không nuốt menu của lần sau.
      held = false;
      if (e.pointerType === "mouse") return;
      var el = e.target && e.target.closest && e.target.closest(selector);
      if (!el || e.target.closest("button, a, input, textarea, select, label")) return;
      stop();
      hx = e.clientX; hy = e.clientY;
      hold = setTimeout(function () { hold = null; held = true; onOpen(el, e); }, LONG_PRESS_MS);
    };
    var move = function (e) {
      if (hold && (Math.abs(e.clientX - hx) > 10 || Math.abs(e.clientY - hy) > 10)) stop();
    };
    var menu = function (e) { if (held) { e.preventDefault(); held = false; } };
    root.addEventListener("pointerdown", down);
    root.addEventListener("pointermove", move);
    root.addEventListener("contextmenu", menu);
    ["pointerup", "pointercancel", "pointerleave"].forEach(function (n) { root.addEventListener(n, stop); });
    return function () {
      stop();
      root.removeEventListener("pointerdown", down);
      root.removeEventListener("pointermove", move);
      root.removeEventListener("contextmenu", menu);
      ["pointerup", "pointercancel", "pointerleave"].forEach(function (n) { root.removeEventListener(n, stop); });
    };
  }

  var api = { EMOJI: EMOJI, REASONS: REASONS, AXES: AXES, STATUS_KEY: STATUS_KEY, COMMENT_MAX: COMMENT_MAX,
    LONG_PRESS_MS: LONG_PRESS_MS, emojiOf: emojiOf, nextReaction: nextReaction, payload: payload, newNonce: newNonce,
    nonceKeeper: nonceKeeper, agentChipsHtml: agentChipsHtml, barHtml: barHtml, cornerHtml: cornerHtml,
    cornerToggle: cornerToggle, bindLongPress: bindLongPress, esc: esc };
  if (typeof window !== "undefined") window.JavisReactions = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
