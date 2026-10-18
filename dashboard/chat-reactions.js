/* Sáu reaction trên câu trả lời ở chat riêng (trang Trò chuyện chính và trang Cộng sự), T2 0.154.0.

   Hợp đồng: docs/dev/team-chat-t2-contract.md mục 4 và 6. Bảng emoji, chip, bộ chọn, trạng thái lấy từ reactions.js; file
   này chỉ nối chúng vào bong bóng trả lời của #chatArea (app.js gọi):

   - attach(el, info): bong bóng đã có mã tin (lịch sử: `m.id`) thì mang `data-mid`, `data-sid` và hàng reaction. Chưa có mã
     thì không có nút (không thả được lên tin chưa lưu).
   - expect(sid, el, entry): bong bóng vừa chốt của một lượt chờ gói `turn_saved` để nhận mã tin (gói tới TRƯỚC thì ghép ngay).
   - onFrame(data, hint): gói WS `turn_saved` (gắn mã cho bong bóng vừa chốt, hay giữ lại nếu bong bóng chưa có) và
     `chat_reaction` (vẽ lại mọi bong bóng của tin đó trong khung, kể cả khi đổi ở tab khác). turnDone(sid) khép lượt.
   - refresh(sid, items): sau F5 và khi socket nối lại, hỏi lại reaction của các tin đang hiện và gắn mã còn thiếu.

   Gửi: POST /sessions/{sid}/messages/{mid}/reaction?brain=..., nonce giữ theo thao tác (reactions.js nonceKeeper): rớt mạng
   thì nút Thử lại gửi đúng nonce cũ. Không gọi model, không mở lượt. Chỉ bong bóng trả lời (role assistant) mới gắn.

   rowHtml và reactionUrl thuần (không DOM, không mạng) để test chạy dưới node. */
(function () {
  "use strict";

  var JR = (typeof window !== "undefined" && window.JavisReactions) || require("./reactions.js");
  var P = { prefix: "jr" };

  function tw(khoa, bien) {
    if (typeof window !== "undefined" && window.t) return window.t(khoa, bien);
    try {
      var s = require("./i18n/vi.json")[khoa] || khoa;
      return String(s).replace(/\{(\w+)\}/g, function (m, ten) {
        return (bien && bien[ten] != null) ? String(bien[ten]) : m;
      });
    } catch (e) { return khoa; }
  }
  var esc = JR.esc;
  var ic = function (n, o) { return (typeof window !== "undefined" && window.ic) ? window.ic(n, o) : ""; };

  function reactionUrl(sid, mid, brain) {
    return "/sessions/" + encodeURIComponent(sid) + "/messages/" + encodeURIComponent(mid) + "/reaction?brain=" +
      encodeURIComponent(brain || "brain");
  }

  // Reaction corner of one answer (0.177.0, owner 2026-10-16: like Zalo). A zero-height anchor placed right after the
  // bubble holds the corner at the bubble's bottom right: the chosen emoji or an outline thumbs-up. Pressing it likes (or
  // removes the reaction); hovering it, or a long press on a phone, shows the six emoji. Under it, an error line with Retry.
  // st: {mid, reaction, open, busy, error: {text, retry}}
  function rowHtml(st) {
    var mid = esc(st.mid);
    var err = st.error ? '<div class="jr-react-err" role="alert"><span>' + esc(st.error.text) + "</span>" +
      (st.error.retry ? '<button type="button" class="ws-btn" data-react-retry="' + mid + '">' + esc(tw("react.retry")) +
        "</button>" : "") + "</div>" : "";
    return '<div class="jr-chat' + (st.busy ? " is-busy" : "") + '" data-jr-mid="' + mid + '"><div class="jr-anchor">' +
      JR.cornerHtml(st.mid, st.reaction, { prefix: "jr", open: !!st.open, icon: ic("thumbs-up") }) + "</div>" + err + "</div>";
  }

  var root = null;
  var cfg = {};
  var keeper = JR.nonceKeeper();
  // Thứ tự gói không cố định: lượt thường gửi `response` rồi mới `turn_saved`, còn làn giọng và chat quy trình lưu TRƯỚC
  // (turn_saved tới trước response). Nên giữ cả hai phía, ai tới sau thì ghép:
  //   pending[sid]: bong bóng vừa chốt đang chờ mã tin; early[sid]: mã tin tới trước khi có bong bóng.
  // Mỗi mục có `at` và `doneAt` (lúc turn_done của lượt đó tới): quá GRACE_MS sau turn_done là của lượt cũ, bỏ.
  var pending = {};
  var early = {};
  var GRACE_MS = 3000;
  var EARLY_MAX_MS = 60000;
  var PENDING_MAX_MS = 120000;
  // Lần ghi có thẩm quyền gần nhất của từng tin (POST xong, gói chat_reaction): refresh() hỏi từ TRƯỚC mốc đó thì bỏ kết quả.
  var seq = 0;
  var stamp = {};

  function now() { return Date.now(); }
  function live(x, maxAge) {
    var t = now();
    return !!x && t - x.at < maxAge && (!x.doneAt || t - x.doneAt < GRACE_MS);
  }
  function keyOf(sid, mid) { return String(sid) + "|" + String(mid); }
  function midValue(x) { return /^\d+$/.test(String(x)) ? Number(x) : x; }

  function changed() { try { if (cfg.onChange) cfg.onChange(); } catch (e) {} }

  function brainOf(st) {
    if (st.brain) return st.brain;
    try { return (cfg.brain && cfg.brain()) || "brain"; } catch (e) { return "brain"; }
  }

  function render(el) {
    var st = el && el._jr;
    if (!st) return;
    var old = el.querySelector(".jr-chat");
    var wrap = document.createElement("div");
    wrap.innerHTML = rowHtml(st);
    var node = wrap.firstChild;
    if (old) old.parentNode.replaceChild(node, old);
    else {
      // Right after the bubble, so the corner sits on the bubble's bottom edge (not under the row of small buttons).
      var bubble = null;
      for (var c = el.firstElementChild; c; c = c.nextElementSibling) if (c.classList.contains("bubble")) { bubble = c; break; }
      if (bubble) el.insertBefore(node, bubble.nextSibling); else el.appendChild(node);
    }
  }

  function attach(el, info) {
    if (!el || !info || info.mid == null || info.mid === "" || !info.sid) return false;
    el.dataset.mid = String(info.mid);
    el.dataset.sid = String(info.sid);
    if (info.sha) el.dataset.sha = String(info.sha);
    el._jr = { sid: String(info.sid), mid: String(info.mid), sha: info.sha || "", brain: info.brain || "",
      reaction: info.reaction || null, entry: info.entry || null, open: false, busy: false, error: null };
    render(el);
    return true;
  }

  // Gắn mã tin cho bong bóng vừa chốt (tin mới: chưa có reaction), ghi cả vào convo để F5 còn nút.
  function bindNew(el, sid, mid, sha, entry) {
    if (entry) { entry.mid = mid; entry.sha = sha || ""; entry.reaction = null; }
    attach(el, { sid: sid, mid: mid, sha: sha || "", reaction: null, entry: entry || null });
    changed();
  }

  function expect(sid, el, entry) {
    if (!sid || !el) return;
    // Lượt có hai khung response (bản sửa lại sau khi bóc JAVIS_LESSON): bong bóng đã có mã thì chỉ chép mã vào convo.
    if (el.dataset.mid) {
      if (entry && entry.mid == null && el._jr) { entry.mid = midValue(el._jr.mid); entry.sha = el._jr.sha || ""; changed(); }
      return;
    }
    var e = early[sid];
    delete early[sid];
    if (live(e, EARLY_MAX_MS)) { delete pending[sid]; bindNew(el, sid, e.mid, e.sha, entry); return; }
    pending[sid] = { el: el, entry: entry || null, at: now() };
  }

  // turn_done của phiên: mục còn chờ chỉ sống thêm GRACE_MS (gói turn_saved có thể tới cùng lúc), sau đó là của lượt cũ.
  function turnDone(sid) {
    if (pending[sid] && !pending[sid].doneAt) pending[sid].doneAt = now();
    if (early[sid] && !early[sid].doneAt) early[sid].doneAt = now();
  }

  function bubbles(sid, mid) {
    if (!root) return [];
    return Array.prototype.filter.call(root.querySelectorAll('.msg-javis[data-mid="' + String(mid).replace(/"/g, "") + '"]'),
      function (el) { return el._jr && el._jr.sid === String(sid); });
  }

  // Ghi reaction cho mọi bong bóng của tin (một tab có thể đang hiện cùng tin hai lần). `fromRefresh`: kết quả của refresh(),
  // bỏ qua nếu tin đã có lần ghi có thẩm quyền mới hơn lúc refresh bắt đầu (`since`).
  function apply(sid, mid, R, quiet, since) {
    var k = keyOf(sid, mid);
    if (since != null) {
      if ((stamp[k] || 0) > since) return 0;
    } else stamp[k] = ++seq;
    var list = bubbles(sid, mid);
    list.forEach(function (el) {
      el._jr.reaction = R || null;
      if (since == null) el._jr.error = null;   // host vừa xác nhận: dòng lỗi cũ không còn đúng
      if (el._jr.entry) el._jr.entry.reaction = R || null;
      render(el);
    });
    if (list.length && !quiet) changed();
    return list.length;
  }

  function onFrame(data, hint) {
    if (!data) return false;
    if (data.type === "turn_saved") {
      var sid = data.session_id;
      if (!sid || data.message_id == null) return false;
      var p = pending[sid];
      delete pending[sid];
      var sha = data.content_sha || "";
      // Bong bóng chờ còn hợp lệ và chưa có mã; không thì bong bóng stream của lượt (gợi ý từ app.js).
      if (live(p, PENDING_MAX_MS) && p.el && !p.el.dataset.mid) { bindNew(p.el, sid, data.message_id, sha, p.entry); return true; }
      var hb = hint && hint.bubble;
      if (hb && !hb.dataset.mid) { bindNew(hb, sid, data.message_id, sha, null); return true; }
      // Chưa có bong bóng (làn giọng, chat quy trình lưu trước khi gửi response): giữ lại, expect() ghép sau.
      early[sid] = { mid: data.message_id, sha: sha, at: now() };
      return false;
    }
    if (data.type === "chat_reaction") return apply(data.session_id, data.message_id, data.reaction || null) > 0;
    return false;
  }

  function stateOf(t) {
    var box = t && t.closest && t.closest(".jr-chat");
    var el = box && box.closest(".msg-javis");
    return el && el._jr ? el : null;
  }

  function focusBtn(el) {
    var b = el.querySelector(".jr-rx-btn");
    if (b) { try { b.focus(); } catch (e) {} }
  }

  var openEl = null;   // the answer whose six-emoji pill is open by long press (phones)

  function setOpen(el, open) {
    if (openEl && openEl !== el && openEl._jr) { openEl._jr.open = false; render(openEl); }
    el._jr.open = open;
    openEl = open ? el : null;
    render(el);
    var f = open ? el.querySelector(".jr-rx-pick") : null;
    if (f) { try { f.focus({ preventScroll: true }); } catch (e) {} }
  }

  function send(el, value) {
    var st = el._jr;
    var body = JR.payload(value, [], "", "", st.sha);
    var key = keyOf(st.sid, st.mid);
    body.nonce = keeper.take(key, body);
    st.last = { value: value };
    st.busy = true;
    st.error = null;
    render(el);
    var done = function (code, j) {
      keeper.settle(key, code);
      st.busy = false;
      if (code === 200 && j && j.ok !== false) {
        st.open = false;
        if (openEl === el) openEl = null;
        if (!apply(st.sid, st.mid, j.reaction || null)) { st.reaction = j.reaction || null; render(el); }
        return;
      }
      st.error = code === 0 ? { text: tw("react.err_network"), retry: true }
        : { text: tw("react.err", { e: (j && j.error) || code }), retry: code >= 500 };
      render(el);
    };
    return fetch(reactionUrl(st.sid, st.mid, brainOf(st)), {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { done(r.status, j || {}); });
    }, function () { done(0, null); });
  }

  function onClick(e) {
    // A press anywhere else closes the pill opened by long press.
    if (openEl && openEl._jr && openEl.contains && !(e.target && openEl.contains(e.target))) { openEl._jr.open = false; render(openEl); openEl = null; }
    var t = e.target && e.target.closest && e.target.closest("[data-rx-toggle],[data-react],[data-react-retry]");
    var el = t && stateOf(t);
    if (!el) return;
    var st = el._jr;
    var d = t.dataset;
    if (st.busy) return;
    if (d.reactRetry != null) return st.last ? send(el, st.last.value) : undefined;
    if (d.rxToggle != null) return send(el, JR.cornerToggle(st.reaction));
    if (d.react != null) return send(el, JR.nextReaction((st.reaction || {}).value, d.react));
  }

  // Esc closes the pill and STOPS there: the page's own Esc (app.js) also turns the speaker and hands-free mode off.
  function onKey(e) {
    if (e.key !== "Escape") return;
    var el = stateOf(e.target);
    if (el && el._jr.open) { e.preventDefault(); e.stopPropagation(); setOpen(el, false); focusBtn(el); }
  }

  // Actions of the phone menu for one message: only the ones its own button row offers.
  var PRESS_ACTS = [
    { act: "quote", icon: "reply", key: "mpress.reply" },
    { act: "copy", icon: "copy", key: "mpress.copy", done: "teams.copied" },
    { act: "edit", icon: "pencil", key: "mpress.edit" },
    { act: "retry", icon: "rotate-cw", key: "mpress.resend" }
  ];
  function pressActions(el) {
    return PRESS_ACTS.filter(function (a) { return el.querySelector('.msg-act[data-act="' + a.act + '"]'); }).map(function (a) {
      return { icon: a.icon, label: tw(a.key), done: a.done ? tw(a.done) : "", run: function (m) {
        var b = m && m.querySelector('.msg-act[data-act="' + a.act + '"]');
        if (b) b.click();
      } };
    });
  }

  function norm(s) {
    return String(s || "").replace(/<!--[\s\S]*?-->/g, "").replace(/\s+/g, " ").trim();
  }

  // Bong bóng khôi phục từ bản lưu cục bộ mà chưa có mã tin (lưu trước 0.154.0, hay turn_saved bị lỡ): ghép với câu trả lời
  // của server từ cuối lên. Tin đã có mã là mốc neo; tin chưa mã thì khớp theo nội dung (bỏ khối ẩn, gộp khoảng trắng), cho
  // lệch tối đa hai tin. Không khớp thì thôi, bong bóng đó vẫn không có nút (không gán bừa mã của tin khác).
  function backfill(sid, items, msgs) {
    var n = 0;
    var j = msgs.length - 1;
    for (var i = items.length - 1; i >= 0 && j >= 0; i--) {
      var it = items[i] || {};
      var entry = it.entry || null;
      if (entry && entry.mid != null) {
        for (var a = msgs.length - 1; a >= 0; a--) if (String(msgs[a].id) === String(entry.mid)) { j = a - 1; break; }
        continue;
      }
      var want = norm(entry && entry.text);
      if (!want || !it.el || it.el.dataset.mid) continue;
      var hit = -1;
      for (var s = j; s >= 0 && s >= j - 2; s--) if (norm(msgs[s].content) === want) { hit = s; break; }
      if (hit < 0) continue;
      var m = msgs[hit];
      j = hit - 1;
      if (bubbles(sid, m.id).length) continue;
      if (entry) { entry.mid = m.id; entry.sha = m.content_sha || ""; entry.reaction = m.reaction || null; }
      attach(it.el, { sid: sid, mid: m.id, sha: m.content_sha || "", reaction: m.reaction || null, entry: entry });
      n++;
    }
    return n;
  }

  // Sau F5 (và khi socket nối lại): khung dựng từ bản lưu cục bộ, reaction có thể đã đổi ở máy khác hay trong lúc mất kết
  // nối. Hỏi đủ số tin đang hiện (tối đa 200), sửa reaction theo server và gắn mã cho bong bóng còn thiếu.
  // items: [{el, entry}] các câu trả lời vừa khôi phục, theo thứ tự (tuỳ chọn; không có thì chỉ sửa bong bóng đã có mã).
  function refresh(sid, items) {
    if (!root || !sid || typeof fetch !== "function") return Promise.resolve(0);
    var sel = '.msg-javis[data-mid][data-sid="' + String(sid).replace(/"/g, "") + '"]';
    var shown = items ? items.length : root.querySelectorAll(sel).length;
    if (!shown) return Promise.resolve(0);
    var limit = Math.min(200, shown * 2 + 10);
    var since = seq;
    return fetch("/sessions/" + encodeURIComponent(sid) + "/messages?limit=" + limit, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var msgs = ((d && d.messages) || []).filter(function (m) { return m.role === "assistant" && m.id != null; });
        var n = items ? backfill(sid, items, msgs) : 0;
        msgs.forEach(function (m) {
          if ("reaction" in m) n += apply(sid, m.id, m.reaction || null, true, since);
        });
        if (n) changed();
        return n;
      }).catch(function () { return 0; });
  }

  function rerenderAll() {
    if (!root) return;
    Array.prototype.forEach.call(root.querySelectorAll(".msg-javis[data-mid]"), function (el) { render(el); });
  }

  function init(opts) {
    cfg = opts || {};
    if (root || !cfg.root) return;
    root = cfg.root;
    root.addEventListener("click", onClick);
    root.addEventListener("keydown", onKey);
    // Phone (0.179.0): long press any message opens the menu of msg-press.js, emoji above the finger (slide to pick)
    // and Reply / Copy / Edit / Send again at the bottom. The actions press the message's own hidden buttons
    // (app.js runMsgAct), so they behave exactly like the desktop row.
    var MP = typeof window !== "undefined" && window.JavisMsgPress;
    if (MP) {
      MP.bind(root, {
        selector: ".msg-javis, .msg-user",
        bubble: ".bubble",
        holdOn: ".jr-rx-btn",
        emoji: JR.EMOJI,
        canReact: function (el) { return !!(el._jr && el.classList.contains("msg-javis")); },
        current: function (el) { return el._jr && el._jr.reaction ? el._jr.reaction.value : ""; },
        react: function (el, value) {
          if (el._jr && !el._jr.busy) send(el, JR.nextReaction((el._jr.reaction || {}).value, value));
        },
        actions: function (el) { return pressActions(el); }
      });
    }
    // Phone (0.216.0, owner): swipe a message to the left to quote it, like Zalo. It presses the message's own Quote
    // button, so the quote is exactly what that button takes (the whole message, Javis's original markdown).
    var SW = typeof window !== "undefined" && window.JavisMsgSwipe;
    if (SW) {
      SW.bind(root, {
        selector: ".msg-javis, .msg-user",
        bubble: ".bubble",
        can: function (el) { return !!el.querySelector('.msg-act[data-act="quote"]'); },
        run: function (el) { var b = el.querySelector('.msg-act[data-act="quote"]'); if (b) b.click(); }
      });
    }
    // Đổi ngôn ngữ giao diện: vẽ lại nhãn của mọi hàng reaction.
    if (typeof window !== "undefined" && window.addEventListener) window.addEventListener("javis:i18n", rerenderAll);
  }

  var api = { init: init, attach: attach, expect: expect, turnDone: turnDone, onFrame: onFrame, apply: apply,
    refresh: refresh, rowHtml: rowHtml, reactionUrl: reactionUrl, norm: norm };
  if (typeof window !== "undefined") window.JavisChatReactions = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
