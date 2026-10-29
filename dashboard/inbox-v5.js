/* Chatbot v5 inbox pieces (owner, 2026-10-28; docs/dev/2026-10-chatbot-v5-spec.md section 6), used by conversations.js.
 *
 * Pure HTML builders, so node can test them without a DOM: the channel picker (tick several accounts), the two-level
 * "Filter" menu, the "Who replies" bar of a chat, the draft box, the quick "who" filters and the sentence for each
 * "who is handling it" code the server sends (server/inbox_state.py). Drawing and events stay in conversations.js.
 *
 * Words on screen: "A.I." with dots and "bạn" in Vietnamese (owner, 2026-10-28); keys `ib.*` in dashboard/i18n. */
(function () {
  "use strict";

  function tt(k, v) { return window.t(k, v); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function noIcon() { return ""; }

  // The four colours of "who is handling it", and the label of each.
  var WHO = ["you", "ai", "owner", "log"];
  function whoLabel(who) { return tt("ib.who_" + (WHO.indexOf(who) >= 0 ? who : "log")); }

  // One sentence about the chat, for the coloured bar under its name. `khi` is the bot's "reply when" in groups.
  function whoSentence(c) {
    var x = c || {}, code = String(x.who_code || "");
    if (code === "pending") return tt("ib.wc_pending", { n: Number(x.ai_pending) || 1 });
    if (code === "ai" && x.chat_type === "group" && x.reply_when) return tt("ib.wc_ai_group", { khi: tt("ib.khi_" + x.reply_when) });
    var known = ["draft_ready", "waiting", "waiting_you", "bot_off_waiting", "ai", "draft_mode", "you", "not_allowed", "no_bot",
                 "no_bot_wanted", "bot_off"];
    return tt("ib.wc_" + (known.indexOf(code) >= 0 ? code : "not_allowed"));
  }

  // The "who" view of the list (owner, 2026-10-29): one dropdown instead of four chips that wrapped onto two lines in
  // the narrow list column. The button keeps the current view and its count in sight; the menu says what each one
  // means. `counts` = server who_counts; null on the first paint, when no number is shown yet.
  var WHO_VIEWS = ["you", "ai", "owner", ""];
  function whoCount(w, counts) {
    var n = counts || {};
    if (w) return Number(n[w]) || 0;
    return ["you", "ai", "owner", "log"].reduce(function (s, k) { return s + (Number(n[k]) || 0); }, 0);
  }
  function whoMark(w, I) { return w ? '<span class="ib-dot w-' + w + '"></span>' : I("inbox"); }
  function whoButtonHtml(current, counts, icon) {
    var I = icon || noIcon, w = WHO_VIEWS.indexOf(current || "") >= 0 ? current || "" : "";
    return whoMark(w, I) + '<span class="ib-who-t">' + esc(tt("ib.wq_" + (w || "all"))) + '</span>' +
      (counts ? '<span class="ib-qn' + (w === "you" ? " you" : "") + '">' + whoCount(w, counts) + '</span>' : "") + I("chevron-down");
  }
  function whoMenuHtml(current, counts, icon) {
    var I = icon || noIcon;
    return WHO_VIEWS.map(function (w) {
      var on = (current || "") === w;
      return '<button type="button" class="ib-wm-o' + (on ? " on" : "") + (w ? "" : " all") + '" role="menuitemradio" aria-checked="' + on +
        '" data-who="' + w + '">' + whoMark(w, I) + '<span class="ib-wm-t"><b>' + esc(tt("ib.wq_" + (w || "all"))) + '</b><small>' +
        esc(tt("ib.wq_" + (w || "all") + "_d")) + '</small></span>' + (counts ? '<span class="ib-qn">' + whoCount(w, counts) + '</span>' : "") +
        '<span class="ib-wm-ck">' + (on ? I("check") : "") + '</span></button>';
    }).join("");
  }

  // ---- the channel picker -------------------------------------------------------------------------------------------
  // `accounts`: the brain's channel accounts (GET /channels/accounts: account_key, channel, label, bot_name...).
  // `sel`: ticked account keys (empty = every channel). `you`: "Needs you" per account key. `logo(channel)`: the
  // channel's real logo (Icons.kenh). `labelOf(channel)`: the channel's name.
  function pickerSummary(accounts, sel) {
    var picked = (accounts || []).filter(function (a) { return (sel || []).indexOf(a.account_key) >= 0; });
    if (!picked.length) return { title: tt("ib.pk_all"), sub: tt("ib.pk_merge", { n: (accounts || []).length }), channels: [] };
    var chans = [];
    picked.forEach(function (a) { if (chans.indexOf(a.channel) < 0) chans.push(a.channel); });
    if (picked.length === 1) return { title: picked[0].label || "", sub: "", channels: chans, one: picked[0] };
    return { title: tt("ib.pk_n", { n: picked.length }), sub: picked.map(function (a) { return a.label; }).join(", "), channels: chans };
  }

  function pickerHtml(accounts, sel, you, q, logo, labelOf, icon) {
    var I = icon || noIcon, L = logo || noIcon, s = sel || [], y = you || {}, qq = String(q || "").toLowerCase();
    var total = Object.keys(y).reduce(function (n, k) { return n + (Number(y[k]) || 0); }, 0);
    var all = !s.length;
    var h = '<div class="ib-pk-search"><span class="ib-sicon">' + I("search") + '</span><input type="search" class="ib-pk-q" placeholder="' +
      esc(tt("ib.pk_search")) + '" value="' + esc(q || "") + '"></div>' +
      '<label class="ib-pk-it' + (all ? " on" : "") + '"><input type="checkbox" class="ib-pk-all"' + (all ? " checked" : "") + '>' +
        '<span class="ib-pk-logo">' + I("layers") + '</span><span class="ib-pk-t"><b>' + esc(tt("ib.pk_all")) + '</b><small>' +
        esc(tt("ib.pk_all_sub")) + '</small></span>' + (total ? '<span class="ib-cnt">' + total + '</span>' : "") + '</label>';
    var order = [];
    (accounts || []).forEach(function (a) { if (order.indexOf(a.channel) < 0) order.push(a.channel); });
    order.forEach(function (ch) {
      var ds = (accounts || []).filter(function (a) {
        return a.channel === ch && (!qq || String(a.label || "").toLowerCase().indexOf(qq) >= 0 ||
                                    String(a.bot_name || "").toLowerCase().indexOf(qq) >= 0);
      });
      if (!ds.length) return;
      var nOn = ds.filter(function (a) { return s.indexOf(a.account_key) >= 0; }).length;
      h += '<label class="ib-pk-grp"><input type="checkbox" class="ib-pk-ch" data-ch="' + esc(ch) + '"' +
        (nOn === ds.length ? " checked" : "") + (nOn && nOn < ds.length ? ' data-half="1"' : "") + '>' + L(ch) +
        '<span>' + esc(labelOf ? labelOf(ch) : ch) + '</span></label>';
      ds.forEach(function (a) {
        var on = s.indexOf(a.account_key) >= 0, n = Number(y[a.account_key]) || 0;
        h += '<label class="ib-pk-it' + (on ? " on" : "") + '"><input type="checkbox" class="ib-pk-acc" data-k="' + esc(a.account_key) + '"' +
          (on ? " checked" : "") + '><span class="ib-pk-logo">' + L(a.channel) + '</span><span class="ib-pk-t"><b>' + esc(a.label) + '</b><small>' +
          esc(a.bot_name ? tt("ib.pk_ai", { bot: a.bot_name }) : tt("ib.pk_no_ai")) + '</small></span>' +
          (n ? '<span class="ib-cnt">' + n + '</span>' : "") + '</label>';
      });
    });
    return h + '<div class="ib-pk-foot"><button type="button" class="ib-link ib-pk-manage">' + I("plus") + ' ' + esc(tt("ib.pk_manage")) + '</button>' +
      '<span class="ib-pk-acts">' + (s.length ? '<button type="button" class="s-btn-ghost ib-pk-clear">' + esc(tt("ib.pk_clear")) + '</button>' : "") +
      '<button type="button" class="s-btn ib-pk-done">' + esc(tt("ib.pk_done")) + (s.length ? " (" + s.length + ")" : "") + '</button></span></div>';
  }

  // ---- the "Filter" menu: categories on the left, the options of the open one on the right (like Pancake's) ----------
  // `st`: the sanitised filter state; `tags`: the owner's tags; `facets`, `bots`: from the list endpoint.
  function filterCats(st) {
    var s = st || {};
    return [
      { id: "time", icon: "calendar", key: "ib.f_time", n: s.when ? 1 : 0 },
      { id: "tagsAny", icon: "tag", key: "ib.f_tags_any", n: (s.tagsAny || []).length },
      { id: "tagsNone", icon: "tag", key: "ib.f_tags_none", n: (s.tagsNone || []).length },
      { id: "type", icon: "users", key: "ib.f_type", n: s.type ? 1 : 0 },
      { id: "bot", icon: "headset", key: "ib.f_bot", n: s.bot ? 1 : 0 },
      { id: "status", icon: "mail", key: "ib.f_status", n: s.status ? 1 : 0 },
      { id: "last", icon: "message-circle", key: "ib.f_last", n: s.lastBy ? 1 : 0 },
      { id: "contact", icon: "phone", key: "ib.f_info", n: (s.contact ? 1 : 0) + (s.pinned ? 1 : 0) },
    ];
  }

  function radio(name, value, cur, text) {
    var on = String(value) === String(cur || "");
    return '<label class="ib-fm-o"><input type="radio" name="' + name + '" data-v="' + esc(value) + '"' + (on ? " checked" : "") + '> <span>' +
      esc(text) + '</span></label>';
  }

  function filterMenuHtml(st, cat, tags, facets, bots, icon, tagChip) {
    var I = icon || noIcon, s = st || {}, f = facets || {}, c = cat || "time";
    var cats = filterCats(s).map(function (k) {
      return '<button type="button" class="ib-fm-cat' + (k.id === c ? " on" : "") + '" data-cat="' + k.id + '">' + I(k.icon) +
        '<span>' + esc(tt(k.key)) + '</span>' + (k.n ? '<span class="ib-fm-n">' + k.n + '</span>' : "") + '</button>';
    }).join("");
    var o = "";
    if (c === "tagsAny" || c === "tagsNone") {
      var on = s[c] || [];
      o = (tags || []).length ? (tags || []).map(function (g) {
        var y = on.indexOf(String(g.id)) >= 0;
        return '<label class="ib-fm-o"><input type="checkbox" data-tag="' + esc(g.id) + '"' + (y ? " checked" : "") + '> ' +
          (tagChip ? tagChip(g) : esc(g.name)) + '</label>';
      }).join("") : '<div class="ib-fm-none">' + esc(tt("ib.f_no_tags")) + '</div>';
    } else if (c === "type") {
      var t = f.type || {};
      o = radio("ib-type", "", s.type, tt("ht.f_type_all")) + radio("ib-type", "group", s.type, tt("ht.f_type_group", { n: Number(t.group) || 0 })) +
        radio("ib-type", "private", s.type, tt("ht.f_type_private", { n: Number(t.private) || 0 }));
    } else if (c === "bot") {
      o = radio("ib-bot", "", s.bot, tt("ht.f_bot_all", { n: Number(f.tong) || 0 }));
      (bots || []).slice().sort(function (a, b) { return String(a.name).localeCompare(String(b.name), "vi"); }).forEach(function (b) {
        o += radio("ib-bot", b.id, s.bot, b.name + " (" + (Number(b.tong) || 0) + ")");
      });
      var none = f.bots && f.bots[""];
      if (none) o += radio("ib-bot", "-", s.bot, tt("ht.f_bot_none", { n: Number(none.tong) || 0 }));
    } else if (c === "status") {
      var stt = f.status || {};
      o = radio("ib-st", "", s.status, tt("ht.f_st_all")) + radio("ib-st", "unread", s.status, tt("ht.f_st_unread", { n: Number(stt.unread) || 0 })) +
        radio("ib-st", "waiting", s.status, tt("ht.f_st_wait", { n: Number(stt.need_reply) || 0 })) +
        radio("ib-st", "hidden", s.status, tt("ht.f_st_hidden", { n: Number(stt.hidden) || 0 }));
    } else if (c === "time") {
      // The calendar for any days first (it is the one a long list would hide), then the quick ranges (date-range.js).
      var DR = window.JavisDateRange, cur = s.when && s.when.preset ? s.when.preset : s.when ? "custom" : "";
      o = '<button type="button" class="s-btn-ghost ib-fm-cal' + (cur === "custom" ? " on" : "") + '">' + I("calendar") + ' ' +
        esc(cur === "custom" && DR ? DR.label(s.when) : tt("ib.f_time_pick")) + '</button>' +
        radio("ib-time", "", cur, tt("dr.all")) + ((DR && DR.PRESETS) || []).map(function (p) {
          return radio("ib-time", p, cur, DR.label({ preset: p }));
        }).join("");
    } else if (c === "last") {
      o = radio("ib-last", "", s.lastBy, tt("ib.f_last_any")) + radio("ib-last", "customer", s.lastBy, tt("ib.f_last_customer")) +
        radio("ib-last", "ai", s.lastBy, tt("ib.f_last_ai")) + radio("ib-last", "human", s.lastBy, tt("ib.f_last_you"));
    } else {
      o = '<label class="ib-fm-o"><input type="checkbox" class="ib-fm-contact"' + (s.contact ? " checked" : "") + '> <span>' +
        esc(tt("ht.f_st_contact", { n: Number(f.has_contact) || 0 })) + '</span></label>' +
        '<label class="ib-fm-o"><input type="checkbox" class="ib-fm-pinned"' + (s.pinned ? " checked" : "") + '> <span>' +
        esc(tt("ib.f_pinned")) + '</span></label>';
    }
    return '<div class="ib-fm-cats"><div class="ib-fm-h">' + esc(tt("ib.f_title")) + '</div>' + cats + '</div>' +
      '<div class="ib-fm-opts" data-cat="' + c + '">' + o + '</div>' +
      '<div class="ib-fm-ft"><button type="button" class="ib-link ib-fm-clear">' + esc(tt("ib.f_clear")) + '</button>' +
      '<button type="button" class="s-btn ib-fm-done">' + esc(tt("ib.f_done")) + '</button></div>';
  }

  // Chips for the active filters under the quick filters, each with an "x". Returns [{k, v, text}].
  function activeChips(st, tags, bots) {
    var s = st || {}, out = [], DR = window.JavisDateRange;
    if (s.when) out.push({ k: "when", v: "", text: tt("ib.fc_time", { t: DR ? DR.label(s.when) : "" }) });
    var name = function (id) { var g = (tags || []).filter(function (x) { return String(x.id) === String(id); })[0]; return g ? g.name : "#" + id; };
    (s.tagsAny || []).forEach(function (id) { out.push({ k: "tagsAny", v: id, text: tt("ib.fc_tag", { t: name(id) }) }); });
    (s.tagsNone || []).forEach(function (id) { out.push({ k: "tagsNone", v: id, text: tt("ib.fc_notag", { t: name(id) }) }); });
    if (s.type) out.push({ k: "type", v: "", text: tt(s.type === "group" ? "ib.fc_group" : "ib.fc_private") });
    if (s.bot) {
      var b = (bots || []).filter(function (x) { return x.id === s.bot; })[0];
      out.push({ k: "bot", v: "", text: s.bot === "-" ? tt("ib.fc_nobot") : tt("ib.fc_bot", { bot: b ? b.name : s.bot }) });
    }
    if (s.status) out.push({ k: "status", v: "", text: tt("ib.fc_st_" + s.status) });
    var LAST = { customer: "ib.fc_last_customer", ai: "ib.fc_last_ai", human: "ib.fc_last_human" };
    if (LAST[s.lastBy]) out.push({ k: "lastBy", v: "", text: tt(LAST[s.lastBy]) });
    if (s.contact) out.push({ k: "contact", v: "", text: tt("ib.fc_contact") });
    if (s.pinned) out.push({ k: "pinned", v: "", text: tt("ib.fc_pinned") });
    return out;
  }

  // ---- "Who replies" bar of a chat ----------------------------------------------------------------------------------
  // `c`: the conversation with the who fields. Returns the controls; the sentence is `whoSentence(c)`.
  function modeBarHtml(c, icon) {
    var I = icon || noIcon, x = c || {};
    if (x.ai_pending && !x.ai_allowed && x.bot_id) {
      return '<button type="button" class="s-btn ib-allow" data-on="1">' + I("check") + ' ' + esc(tt("ib.allow")) + '</button>' +
        '<button type="button" class="s-btn-ghost ib-allow" data-on="0">' + esc(tt("ib.dismiss")) + '</button>';
    }
    if (!x.bot_id) return x.who_code === "no_bot_wanted" ? "" : '<button type="button" class="s-btn-ghost ib-make-bot">' + I("plus") + ' ' + esc(tt("ib.make_bot")) + '</button>';
    if (!x.ai_allowed) return '<button type="button" class="s-btn ib-allow" data-on="1">' + I("sparkles") + ' ' + esc(tt("ib.allow_here")) + '</button>';
    var mode = x.mode === "human" ? "human" : x.mode === "draft" ? "draft" : "ai";
    return '<span class="ib-mode-l">' + esc(tt("ib.ai_lbl")) + '</span><span class="ib-mode" role="group" aria-label="' + esc(tt("ib.ai_lbl")) + '">' +
      [["ai", "sparkles"], ["draft", "pen-line"], ["human", "hand"]].map(function (m) {
        var on = m[0] === mode;
        return '<button type="button" class="ib-m m-' + m[0] + (on ? " on" : "") + '" data-m="' + m[0] + '" aria-pressed="' + on + '">' + I(m[1]) +
          '<span class="ib-l-long">' + esc(tt("ib.m_" + m[0])) + '</span><span class="ib-l-short">' + esc(tt("ib.m_" + m[0] + "_s")) + '</span></button>';
      }).join("") + '</span>';
  }

  // ---- "Who replies" on a narrow chat column (phones): one chip with the current mode, opening a sheet ------------------
  // The sheet lists the three modes with a line each on what they do, then "Customer info" (the Info panel has no button
  // of its own on a phone: the chip is the one place for the chat's settings).
  var MODES = [["ai", "sparkles"], ["draft", "pen-line"], ["human", "hand"]];
  function modeChipHtml(c, icon) {
    var I = icon || noIcon, x = c || {};
    var mode = x.mode === "human" ? "human" : x.mode === "draft" ? "draft" : "ai";
    var m = MODES.filter(function (k) { return k[0] === mode; })[0];
    return '<button type="button" class="ib-mchip m-' + mode + '" aria-haspopup="dialog" aria-label="' +
      esc(tt("ib.mchip_aria", { mode: tt("ib.m_" + mode + "_s") })) + '">' + I(m[1]) + '<span>' + esc(tt("ib.m_" + mode + "_s")) + '</span>' +
      I("chevron-down") + '</button>';
  }
  function modeSheetHtml(c, icon) {
    var I = icon || noIcon, x = c || {};
    var mode = x.mode === "human" ? "human" : x.mode === "draft" ? "draft" : "ai";
    return '<div class="ib-msheet-bg" data-close="1"></div>' +
      '<div class="ib-msheet-box" role="dialog" aria-modal="true" aria-labelledby="ibMsheetH"><span class="ib-msheet-grip" aria-hidden="true"></span>' +
      '<h3 id="ibMsheetH">' + esc(tt("ib.msheet_h")) + '</h3>' +
      MODES.map(function (m) {
        var on = m[0] === mode;
        return '<button type="button" class="ib-mso m-' + m[0] + (on ? " on" : "") + '" role="menuitemradio" aria-checked="' + on + '" data-m="' +
          m[0] + '"><span class="ib-mso-ic">' + I(m[1]) + '</span><span class="ib-wm-t"><b>' + esc(tt("ib.m_" + m[0] + "_s")) + '</b><small>' +
          esc(tt("ib.m_" + m[0] + "_d")) + '</small></span><span class="ib-wm-ck">' + (on ? I("check") : "") + '</span></button>';
      }).join("") +
      '<button type="button" class="ib-mso-info">' + I("info") + '<span>' + esc(tt("ib.info_t")) + '</span></button></div>';
  }

  // ---- the draft box (a draft the bot wrote in "drafts" mode, or the answer to the owner's "A.I. reply") -------------
  function draftHtml(d, busy, icon) {
    var I = icon || noIcon, x = d || {};
    var head = x.instruction ? tt("ib.dr_cmd", { lenh: x.instruction }) : tt("ib.dr_ready");
    return '<div class="ib-draft"><div class="ib-draft-h">' + I("sparkles") + ' <span>' + esc(head) + '</span></div>' +
      '<textarea class="ib-draft-t" rows="3">' + esc(x.text || "") + '</textarea>' +
      '<div class="ib-draft-a"><button type="button" class="s-btn-ghost ib-dr-drop"' + (busy ? " disabled" : "") + '>' + I("x") + ' ' + esc(tt("ib.dr_drop")) + '</button>' +
      '<button type="button" class="s-btn-ghost ib-dr-redo"' + (busy ? " disabled" : "") + '>' + I(busy === "redo" ? "loader" : "rotate-cw") + ' ' +
        esc(tt(busy === "redo" ? "ib.ai_busy" : "ib.dr_redo")) + '</button>' +
      '<button type="button" class="s-btn ib-dr-send"' + (busy ? " disabled" : "") + '>' + I(busy === "send" ? "loader" : "send") + ' ' + esc(tt("ib.dr_send")) + '</button></div></div>';
  }

  window.JavisInboxV5 = {
    WHO: WHO, whoLabel: whoLabel, whoSentence: whoSentence, whoButtonHtml: whoButtonHtml, whoMenuHtml: whoMenuHtml,
    pickerSummary: pickerSummary, pickerHtml: pickerHtml, filterCats: filterCats, filterMenuHtml: filterMenuHtml, activeChips: activeChips,
    modeBarHtml: modeBarHtml, modeChipHtml: modeChipHtml, modeSheetHtml: modeSheetHtml, draftHtml: draftHtml,
  };
})();
