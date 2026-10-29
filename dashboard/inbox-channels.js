/* Channels tab of the Chatbot page (Chatbot v5, owner 2026-10-28; docs/dev/2026-10-chatbot-v5-spec.md section 7).
 *
 * Left: every nick and Page of the open brain grouped by channel with its real logo, "Connect a new channel", and per
 * channel "Put an A.I. on several ..." (tick, pick a bot, Save). Right: the picked nick or Page with ONE dropdown
 * "A.I. on duty here" (Cancel / Save appear only after a change; "No A.I. needed" is a choice too), an Info button that
 * opens its account card in a popup (record switch, import history, edit, delete, bot settings), and its chats, each with a
 * switch "A.I. here" (POST /conversations/{id}/ai), who is handling it, Allow when someone called the A.I., Open chat.
 *
 * conversations.js owns the page and hands this file a context object (helpers, the account list, actions), so the
 * channel logic is not written twice. Words on screen: "A.I." and "bạn" in Vietnamese, keys `ib.kn_*`. */
(function () {
  "use strict";

  var C = null;                 // context from conversations.js
  var _body = null;
  var _sel = "";                // account key on the right
  var _det = false;             // phones: showing the right side
  var _pend = null;             // {key, val}: the dropdown changed but not saved
  var _chats = [], _chatsFor = "", _chatQ = "", _busy = false;
  // The chats of the picked nick or Page, one page at a time (owner, 2026-10-28: a nick with 289 chats drew them all).
  // The search asks the server, so it finds a chat on any page.
  var PAGE = 20, _page = 0, _total = 0, _qTimer = null;
  var _treeQ = "";              // the search over the channel list on the left (owner, 2026-10-28)
  var _bots = null;             // [{id, name, enabled}] of the open brain

  function t(k, v) { return window.t(k, v); }
  function esc(s) { return C.esc(s); }
  function ic(n) { return C.ic(n); }

  function render(body, ctx) {
    C = ctx; _body = body;
    body.innerHTML = '<div class="ib-v5 kn-wrap"><div class="kn-grid"><div class="kn-tree"></div><div class="kn-pane"></div></div></div>';
    body.addEventListener("click", onClick);
    body.addEventListener("change", onChange);
    body.addEventListener("input", onInput);
    paint();
    loadBots();
    C.reloadAccounts().then(paint, paint);
  }

  async function loadBots() {
    try {
      var d = await C.api("/chatbots?brain=" + encodeURIComponent(C.brain()));
      _bots = (d.bots || []).map(function (b) { return { id: b.id, name: b.name, enabled: !!b.enabled }; });
    } catch (e) { _bots = []; }
    paintPane();
  }

  // ---- helpers ----
  function accs() { return C.accounts().filter(function (a) { return a && a.account_key; }); }
  function acc(key) { return accs().filter(function (a) { return a.account_key === key; })[0] || null; }
  function unit(ch) { return t(C.channel(ch).kind === "account" ? "ib.kn_unit_nick" : "ib.kn_unit_page"); }
  function current(a) { return a.bot_id || (a.no_bot ? "__none" : ""); }
  // Something to do on this account: an error, or no bot and the owner did not say none is needed.
  function needsWork(a) { return !!a.loi || (!a.bot_id && !a.no_bot); }

  function paint() {
    if (!_body || !document.body.contains(_body)) return;
    var list = accs();
    if (!_sel || !acc(_sel)) _sel = list.length ? list[0].account_key : "";
    var grid = _body.querySelector(".kn-grid");
    if (grid) grid.classList.toggle("det", _det);
    paintTree();
    paintPane();
  }

  function paintTree() {
    var box = _body.querySelector(".kn-tree");
    if (!box) return;
    var list = accs();
    var html = '<div class="kn-top"><button type="button" class="s-btn kn-add">' + ic("plus") + ' ' + esc(t("ib.kn_add")) + '</button>' +
      '<label class="kn-allbr"><input type="checkbox" class="kn-allbr-cb"' + (C.allBrains() ? " checked" : "") + '> <span>' +
      esc(t("ht.tk_xem_moi_brain")) + '</span></label>' +
      // Say which brain the list is filtered by: a shorter list must have a reason on screen (0.62.4).
      '<span class="kn-brain">' + ic("brain") + ' ' + esc(C.allBrains() ? t("ht.tk_loc_tat_ca") : t("ht.tk_loc_brain", { brain: C.brainName() })) +
      '</span></div>';
    if (list.length) html += '<input type="search" class="kn-tq" placeholder="' + esc(t("ib.kn_tree_q")) + '" aria-label="' + esc(t("ib.kn_tree_q")) + '">';
    html += '<div class="kn-secs">' + sectionsHtml(list) + '</div>';
    box.innerHTML = html;
    var q = box.querySelector(".kn-tq");
    if (q) q.value = _treeQ;
  }

  // Lower case without Vietnamese marks, so "zalo vu" finds "Zalo Vũ".
  function fold(v) { return String(v || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\u0111/g, "d"); }

  // The channel sections, narrowed by the search: a nick or Page matches on its name, its channel or the bot on duty.
  function sectionsHtml(list) {
    if (!list.length) return '<div class="ht-empty">' + ic("plug") + '<b>' + esc(t("ht.tk_rong")) + '</b></div>';
    var q = fold(_treeQ).trim();
    var shown = q ? list.filter(function (a) {
      return [a.label, C.channelName(a.channel), a.bot_name].some(function (v) { return fold(v).indexOf(q) >= 0; });
    }) : list;
    if (!shown.length) return '<div class="ht-empty small">' + esc(t("ib.kn_tree_none")) + '</div>';
    var order = [], you = C.youByAcc(), html = "";
    shown.forEach(function (a) { if (order.indexOf(a.channel) < 0) order.push(a.channel); });
    order.forEach(function (ch) {
      var ds = shown.filter(function (a) { return a.channel === ch; });
      html += '<section class="kn-sec"><div class="kn-sh">' + C.logo(ch, "22px") + '<b>' + esc(C.channelName(ch)) + '</b><small>' +
        esc(t("ib.kn_count", { n: ds.length, unit: unit(ch) })) + '</small></div>' +
        (ds.length > 1 && !q ? '<button type="button" class="ib-link kn-bulk" data-ch="' + esc(ch) + '">' + ic("sparkles") + ' ' +
          esc(t("ib.kn_bulk", { unit: unit(ch) })) + '</button>' : "") +
        ds.map(function (a) {
          var n = Number(you[a.account_key]) || 0;
          var dot = a.loi ? "w-you" : a.bot_id ? (a.bot_enabled ? "w-ai" : "w-log") : a.no_bot ? "w-log" : "w-you";
          var sub = a.bot_id ? t("ib.pk_ai", { bot: a.bot_name }) + (a.bot_enabled ? "" : " · " + t("ib.kn_bot_off_s"))
            : a.no_bot ? t("ib.kn_no_ai") : t("ib.pk_no_ai");
          return '<button type="button" class="kn-row' + (a.account_key === _sel ? " on" : "") + '" data-k="' + esc(a.account_key) + '">' +
            '<span class="kn-rt"><b>' + esc(a.label) + '</b><small>' + esc(sub) + (n ? ' · <span class="kn-you">' + esc(t("ib.kn_you_n", { n: n })) + '</span>' : "") +
            (a.loi ? ' · <span class="kn-err">' + esc(t("ht.tk_loi")) + '</span>' : "") + '</small></span><span class="ib-dot ' + dot + '"></span></button>';
        }).join("") + '</section>';
    });
    return html;
  }

  function botOptions(cur) {
    var o = '<option value=""' + (cur === "" ? " selected" : "") + '>' + esc(t("ib.kn_none_yet")) + '</option>' +
      '<option value="__none"' + (cur === "__none" ? " selected" : "") + '>' + esc(t("ib.kn_no_ai")) + '</option>';
    var seen = false;
    (_bots || []).forEach(function (b) {
      if (b.id === cur) seen = true;
      o += '<option value="' + esc(b.id) + '"' + (b.id === cur ? " selected" : "") + '>' + esc(b.name) + '</option>';
    });
    // The bot on duty may live in another brain (accounts are global): keep it selectable so Save never moves it silently.
    var a = acc(_sel);
    if (cur && cur !== "__none" && !seen && a) o += '<option value="' + esc(cur) + '" selected>' + esc(a.bot_name || cur) + '</option>';
    return o;
  }

  function paintPane() {
    var box = _body && _body.querySelector(".kn-pane");
    if (!box) return;
    var a = acc(_sel);
    if (!a) { box.innerHTML = '<div class="ht-empty">' + ic("plug") + '<b>' + esc(t("ib.kn_pick")) + '</b></div>'; return; }
    var cur = current(a);
    var val = _pend && _pend.key === a.account_key ? _pend.val : cur;
    var changed = val !== cur;
    box.innerHTML =
      '<div class="kn-ph"><button type="button" class="s-btn-ghost kn-back" aria-label="' + esc(t("ib.back")) + '">' + ic("arrow-left") + '</button>' +
        '<h3>' + C.logo(a.channel, "24px") + ' <span>' + esc(a.label) + '</span></h3>' +
        '<div class="kn-assign"><label for="knBot">' + esc(t("ib.kn_duty", { unit: unit(a.channel) })) + '</label>' +
          '<select id="knBot" class="kn-bot">' + botOptions(val) + '</select>' +
          (changed ? '<span class="kn-unsaved">' + esc(t("ib.kn_unsaved")) + '</span>' +
            '<button type="button" class="s-btn-ghost kn-cancel">' + esc(t("common.cancel")) + '</button>' +
            '<button type="button" class="s-btn kn-save"' + (_busy ? " disabled" : "") + '>' + ic("check") + ' ' + esc(t("common.save")) + '</button>'
          : "") +
          // The account card lives behind this button (owner, 2026-10-29: it took the top of the pane). A red dot when
          // the account has an error, so hiding the card does not hide the error.
          '<button type="button" class="s-btn-ghost kn-info" aria-haspopup="dialog"' + (a.loi ? ' title="' + esc(a.loi) + '"' : "") + '>' +
            ic("info") + ' ' + esc(t("ib.kn_info")) + (a.loi ? '<span class="kn-info-bad" aria-hidden="true"></span>' : "") + '</button>' +
        '</div></div>' +
      '<div class="kn-ch"><div class="kn-chh"><b>' + esc(t("ib.kn_chats")) + '</b>' +
        '<input type="search" class="kn-q" placeholder="' + esc(t("ib.kn_q")) + '" aria-label="' + esc(t("ib.kn_q")) + '"></div>' +
        '<div class="kn-list">' + chatRows(a) + '</div></div>';
    var q = box.querySelector(".kn-q");
    q.value = _chatQ;
    if (_chatsFor !== a.account_key) loadChats(a.account_key, _page);
  }

  function chatRows(a) {
    if (_chatsFor !== a.account_key) return '<div class="ht-empty small">' + esc(t("common.loading")) + '</div>';
    var V = window.JavisInboxV5;
    if (!_chats.length) return '<div class="ht-empty small">' + esc(t(_chatQ ? "ht.khong_khop" : "ib.kn_no_chats")) + '</div>';
    return _chats.map(function (c) {
      var ten = c.title || c.customer_name || c.external_chat_id;
      var who = V && V.WHO.indexOf(c.who) >= 0 ? c.who : "log";
      var on = !!c.ai_allowed;
      return '<div class="kn-chat w-' + who + '">' + C.avatar(c, ten) +
        '<span class="kn-ct"><b>' + esc(ten) + '</b><small><span class="ib-dot w-' + who + '"></span> ' + esc(V ? V.whoSentence(c) : "") +
          ' · ' + esc(t(c.chat_type === "group" ? "ht.nhom" : "ib.kn_private")) + '</small>' +
          '<span class="kn-ca">' + (c.ai_pending && !on && a.bot_id ? '<button type="button" class="s-btn kn-allow" data-id="' + c.id + '">' +
            esc(t("ib.allow")) + '</button>' : "") +
          '<button type="button" class="ib-link kn-open" data-id="' + c.id + '">' + esc(t("ib.kn_open")) + '</button></span></span>' +
        '<label class="kn-sw"><span>' + esc(t("ib.kn_ai_here")) + '</span><button type="button" class="ib-tg' + (on ? " on" : "") +
          '" role="switch" aria-checked="' + on + '" data-id="' + c.id + '"' + (a.bot_id ? "" : ' aria-disabled="true"') + ' aria-label="' +
          esc(t("ib.kn_ai_here") + ": " + ten) + '"></button></label></div>';
    }).join("") + pagerHtml();
  }

  // "21-40 of 289" with Previous / Next; nothing when everything fits on one page.
  function pagerHtml() {
    var pages = Math.max(1, Math.ceil(_total / PAGE));
    if (pages <= 1) return "";
    var from = _page * PAGE + 1, to = Math.min(_total, from + _chats.length - 1);
    return '<nav class="kn-pager" aria-label="' + esc(t("ib.kn_pages")) + '">' +
      '<button type="button" class="s-btn-ghost kn-pg" data-pg="' + (_page - 1) + '"' + (_page ? "" : " disabled") + '>' +
        ic("chevron-left") + '<span>' + esc(t("ib.kn_prev")) + '</span></button>' +
      '<span class="kn-pg-n" aria-live="polite">' + esc(t("ib.kn_range", { from: from, to: to, n: _total })) + '</span>' +
      '<button type="button" class="s-btn-ghost kn-pg" data-pg="' + (_page + 1) + '"' + (_page + 1 < pages ? "" : " disabled") + '>' +
        '<span>' + esc(t("ib.kn_next")) + '</span>' + ic("chevron-right") + '</button></nav>';
  }

  // One page of the account's chats. Page 0 also brings the count of every match, kept for the later pages.
  async function loadChats(key, page) {
    var pg = Math.max(0, page || 0), q = _chatQ;
    _chatsFor = "";
    try {
      var d = await C.api("/conversations?limit=" + PAGE + "&offset=" + pg * PAGE + "&account_ids=" + encodeURIComponent(key) +
                          (q ? "&q=" + encodeURIComponent(q) : ""));
      if (key !== _sel || q !== _chatQ) return;
      _chats = d.items || [];
      _page = pg;
      if (d.total != null) _total = d.total;
      else if (!pg) _total = _chats.length;
      _chatsFor = key;
    } catch (e) { _chats = []; _chatsFor = key; }
    var l = _body && _body.querySelector(".kn-list");
    var a = acc(key);
    if (l && a) l.innerHTML = chatRows(a);
  }

  function refreshChats() { var l = _body && _body.querySelector(".kn-list"); var a = acc(_sel); if (l && a) l.innerHTML = chatRows(a); }

  // ---- events ----
  function onClick(e) {
    var b = e.target.closest && e.target.closest("button");
    if (!b || !_body.contains(b)) return;
    if (b.classList.contains("kn-row")) { _sel = b.dataset.k; _pend = null; _chatQ = ""; _page = 0; _det = true; paint(); return; }
    if (b.classList.contains("kn-pg")) {
      loadChats(_sel, parseInt(b.dataset.pg, 10)).then(function () {
        var top = _body.querySelector(".kn-ch"); if (top && top.scrollIntoView) top.scrollIntoView({ block: "start" });
      });
      return;
    }
    if (b.classList.contains("kn-back")) { _det = false; paint(); return; }
    if (b.classList.contains("kn-add")) return C.addAccount();
    if (b.classList.contains("kn-bulk")) return openBulk(b.dataset.ch);
    if (b.classList.contains("kn-cancel")) { _pend = null; paintPane(); return; }
    if (b.classList.contains("kn-save")) return saveDuty();
    if (b.classList.contains("kn-info")) { var a = acc(_sel); if (a) openInfo(a, b); return; }
    if (b.classList.contains("kn-open")) return C.openChat(parseInt(b.dataset.id, 10));
    if (b.classList.contains("kn-allow")) return setAi(parseInt(b.dataset.id, 10), true);
    if (b.classList.contains("ib-tg")) {
      // No bot on duty yet: the dimmed switch says so when pressed, instead of a hint line above the list (owner, 2026-10-29).
      var ac = acc(_sel);
      if (ac && !ac.bot_id) {
        C.toast(t("ib.kn_need_bot", { unit: unit(ac.channel) }));
        var sb = _body.querySelector(".kn-bot"); if (sb) sb.focus();
        return;
      }
      var c = _chats.filter(function (x) { return x.id === parseInt(b.dataset.id, 10); })[0];
      if (c) setAi(c.id, !c.ai_allowed);
    }
  }

  function onChange(e) {
    var el = e.target;
    if (el.classList.contains("kn-bot")) { _pend = { key: _sel, val: el.value }; paintPane(); var s = _body.querySelector(".kn-bot"); if (s) s.focus(); }
    else if (el.classList.contains("kn-allbr-cb")) { C.setAllBrains(el.checked).then(paint, paint); }
  }

  function onInput(e) {
    // The server searches every chat of the account; a short pause so each key press does not ask again.
    if (e.target.classList.contains("kn-tq")) {
      _treeQ = e.target.value;
      var secs = _body.querySelector(".kn-secs");
      if (secs) secs.innerHTML = sectionsHtml(accs());
      return;
    }
    if (e.target.classList.contains("kn-q")) {
      _chatQ = e.target.value.trim();
      clearTimeout(_qTimer);
      _qTimer = setTimeout(function () { loadChats(_sel, 0); }, 300);
    }
  }

  // Save the dropdown: a bot, no bot yet, or "No A.I. needed" (no bot, and the account stops counting as a job).
  async function saveDuty() {
    var a = acc(_sel);
    if (!a || !_pend || _busy) return;
    var val = _pend.val, before = current(a);
    _busy = true;
    paintPane();
    var r = await duty(a, val);
    _busy = false;
    if (!r.ok) { C.toast(t("ht.act_fail", { err: r.error })); paintPane(); return; }
    _pend = null;
    C.toast(r.bot_tat ? t("ib.kn_saved_off", { bot: r.bot_tat }) : t("ib.kn_saved"), function () { duty(a, before).then(after); });
    after();
  }

  async function duty(a, val) {
    try {
      var r = await C.api("/channels/accounts/" + encodeURIComponent(a.id) + "/bot",
                          { method: "POST", body: C.fd({ bot_id: val === "__none" ? "" : val }) });
      if (!val || val === "__none") {
        await C.api("/channels/no-bot", { method: "POST", body: C.fd({ account_key: a.account_key, on: val === "__none" ? "1" : "0" }) });
      }
      return { ok: true, bot_tat: r.bot_tat || "" };
    } catch (e) { return { ok: false, error: e.message }; }
  }

  function after() {
    _chatsFor = "";
    C.reloadAccounts().then(paint, paint);
  }

  async function setAi(id, on) {
    try { await C.api("/conversations/" + id + "/ai", { method: "POST", body: C.fd({ on: on ? "1" : "0" }) }); }
    catch (e) { C.toast(t("ht.act_fail", { err: e.message })); return; }
    C.toast(t(on ? "ib.kn_on" : "ib.kn_off"), function () {
      C.api("/conversations/" + id + "/ai", { method: "POST", body: C.fd({ on: on ? "0" : "1" }) }).then(function () { loadChats(_sel, _page); });
    });
    loadChats(_sel, _page);
  }

  // The account card of the picked nick or Page in a popup: the same card the pane used to show above the chats, plus
  // "Bot settings". A button on the card that leads elsewhere (view chats, Connections, edit) closes the popup first.
  function openInfo(a, from) {
    var box = document.createElement("div");
    box.className = "ht-modal";
    box.innerHTML = '<div class="ht-form ib-v5 kn-infobox" role="dialog" aria-modal="true" aria-label="' + esc(t("ib.kn_info_title", { unit: unit(a.channel) })) + '">' +
      '<div class="kn-ih"><h3>' + esc(t("ib.kn_info_title", { unit: unit(a.channel) })) + '</h3>' +
        '<button type="button" class="s-btn-ghost kn-ix" aria-label="' + esc(t("common.close")) + '">' + ic("x") + '</button></div>' +
      '<div class="kn-card"></div>' +
      (a.bot_id ? '<div class="ht-form-acts"><button type="button" class="s-btn-ghost kn-botset">' + ic("settings") + ' ' +
        esc(t("ib.kn_bot_settings")) + '</button></div>' : "") + '</div>';
    var card = C.accountCard(a);
    if (card) box.querySelector(".kn-card").appendChild(card);
    document.body.appendChild(box);
    var close = function () {
      if (!box.parentNode) return;
      box.parentNode.removeChild(box);
      if (from && document.body.contains(from)) from.focus();
    };
    box.onmousedown = function (e) { if (e.target === box) close(); };
    box.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
    box.querySelector(".kn-ix").onclick = close;
    var bs = box.querySelector(".kn-botset");
    if (bs) bs.onclick = function () { close(); C.openBot(a.bot_id); };
    // Card buttons run their own handler first (bubbling reaches the box after the button), then the popup goes.
    box.querySelector(".kn-card").addEventListener("click", function (e) {
      if (e.target.closest && e.target.closest(".ht-acc-acts button")) setTimeout(close, 0);
    });
    box.querySelector(".kn-ix").focus();
  }

  // "Put an A.I. on several Pages": tick the accounts, pick a bot, Save. One request per account, in order.
  function openBulk(ch) {
    var ds = accs().filter(function (a) { return a.channel === ch; });
    var box = document.createElement("div");
    box.className = "ht-modal";
    box.innerHTML = '<div class="ht-form ib-v5 kn-bulkbox" role="dialog" aria-label="' + esc(t("ib.kn_bulk", { unit: unit(ch) })) + '">' +
      '<h3>' + esc(t("ib.kn_bulk", { unit: unit(ch) })) + '</h3><p class="ib-hint">' + esc(t("ib.kn_bulk_hint")) + '</p>' +
      ds.map(function (a) {
        return '<label class="kn-bl"><input type="checkbox" value="' + esc(a.id) + '"' + (a.bot_id ? "" : " checked") + '> ' + C.logo(a.channel) +
          ' <span>' + esc(a.label) + '</span><small>' + esc(a.bot_id ? t("ib.pk_ai", { bot: a.bot_name }) : t("ib.pk_no_ai")) + '</small></label>';
      }).join("") +
      '<label class="kn-bl-l" for="knBulkBot">' + esc(t("ib.kn_bulk_bot")) + '</label><select id="knBulkBot">' +
        (_bots || []).map(function (b) { return '<option value="' + esc(b.id) + '">' + esc(b.name) + '</option>'; }).join("") + '</select>' +
      (!(_bots || []).length ? '<p class="ib-hint">' + esc(t("ib.kn_bulk_nobot")) + '</p>' : "") +
      '<div class="ht-form-acts"><button type="button" class="s-btn-ghost kn-bl-x">' + esc(t("common.cancel")) + '</button>' +
      '<button type="button" class="s-btn kn-bl-ok"' + ((_bots || []).length ? "" : " disabled") + '>' + ic("check") + ' ' + esc(t("common.save")) + '</button></div></div>';
    document.body.appendChild(box);
    var close = function () { if (box.parentNode) box.parentNode.removeChild(box); };
    box.onmousedown = function (e) { if (e.target === box) close(); };
    box.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
    box.querySelector(".kn-bl-x").onclick = close;
    box.querySelector(".kn-bl-ok").onclick = async function () {
      var bot = box.querySelector("#knBulkBot").value;
      var ids = [].map.call(box.querySelectorAll("input[type=checkbox]:checked"), function (x) { return x.value; });
      if (!bot || !ids.length) return close();
      this.disabled = true;
      var bad = [];
      for (var i = 0; i < ids.length; i++) {
        var a = ds.filter(function (x) { return x.id === ids[i]; })[0];
        var r = await duty(a, bot);
        if (!r.ok) bad.push(a.label + ": " + r.error);
      }
      close();
      C.toast(bad.length ? t("ib.kn_bulk_some", { n: ids.length - bad.length, err: bad[0] }) : t("ib.kn_bulk_done", { n: ids.length }));
      after();
    };
    var first = box.querySelector("input, select");
    if (first) first.focus();
  }

  // Number on the Channels tab: nicks and Pages that need something (an error, or no bot and none was declined).
  function jobs(list) { return (list || []).filter(needsWork).length; }

  window.JavisInboxChannels = { render: render, jobs: jobs, paint: paint, openInfo: openInfo };
})();
