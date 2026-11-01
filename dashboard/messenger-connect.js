/* Facebook Messenger card on the Connections page (0.311.0).
 *
 * The Messenger channel already answered a Page inbox; what owners got stuck on was the setup on Meta's side (user token
 * instead of Page token, short-lived token, webhook without the `messages` field, missing permissions). This card takes the
 * four things an owner can copy from developers.facebook.com and lets the server (server/messenger_setup.py) do the rest:
 * Page token, app webhook, Page subscription. It then shows a checklist, and each saved Page has Check and Repair buttons.
 *
 * 0.332.0 (owner, 2026-10-26: "lạc quẻ"): Messenger used to be its own section under the connected list, with the form
 * opening inside the page. It now follows the page's own frame like every other service: a card in the "Available" grid
 * (`catCard`), the form in the shared connection dialog (`window.JavisConnModal`, from console.js), and the connected
 * Pages as one card in the "Connected" list (`mount`), drawn only once a Page is connected.
 *
 * 0.434.0: Log in with Facebook. The form now asks for the App ID and App secret only; the button opens Facebook's login in
 * a new tab, the card polls /messenger/oauth/result until the Pages arrive, the owner ticks Pages and picks how comments
 * are handled, and /messenger/oauth/finish connects them (server/messenger_oauth.py). Facebook's COOP header cuts the
 * opener link, so the card polls instead of waiting for a postMessage. Pasting a token is still there, folded away.
 * Each connected Page has a comment mode: off, inbox (the owner answers) or reply (the bot answers publicly).
 *
 * The server never sends a token back; the form fields are cleared after a submit. Render helpers are pure (tested with node). */
(function () {
  "use strict";

  function tw(key, vars) {
    var s = (typeof window !== "undefined" && window.t) ? window.t(key, vars) : key;
    if (vars) {
      s = String(s).replace(/\{(\w+)\}/g, function (m, name) {
        return Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : m;
      });
    }
    return s;
  }
  // The "Connected" heading counts MCP accounts (data-n, drawn by console.js) plus what the built-in cards add,
  // each under its own data-* key (github-connect.js: data-gh, messenger-connect.js: data-fb), so neither card
  // overwrites the other's share. Returns the new total.
  function addToConnCount(key, n) {
    var cnt = document.getElementById("connCount");
    if (!cnt) return 0;
    cnt.setAttribute("data-" + key, String(n));
    var total = 0;
    for (var i = 0; i < cnt.attributes.length; i++) {
      if (cnt.attributes[i].name.indexOf("data-") === 0) total += parseInt(cnt.attributes[i].value, 10) || 0;
    }
    cnt.textContent = tw("cs.cn_account_n", { so: total });
    return total;
  }
  function esc(t) {
    return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  var ic = function (n) { return (typeof window !== "undefined" && window.ic) ? window.ic(n) : ""; };
  function infoBtn() { var J = typeof window !== "undefined" && window.JavisInfo; return J ? J.btn(tw("info.more")) : ""; }
  function infoBody(html) {
    var J = typeof window !== "undefined" && window.JavisInfo;
    return J ? J.body(html) : '<div class="info-body">' + html + "</div>";
  }
  function icon(name) {
    return typeof window !== "undefined" && typeof window.ic === "function" ? window.ic(name) : "";
  }
  // Guides on GitHub (0.436.1): the Vietnamese interface opens docs/, every other language docs/en/.
  var GUIDE = { full: ["31-messenger.md", "31-messenger.md"], steps: ["31-messenger-tung-buoc.md", "31-messenger-step-by-step.md"] };
  function guideUrl(which) {
    var vi = typeof window !== "undefined" && window.JavisI18n && window.JavisI18n.lang() === "vi";
    var g = GUIDE[which];
    return "https://github.com/blogminhquy/javis-os/blob/main/docs/" + (vi ? g[0] : "en/" + g[1]);
  }
  function guideLink(which, key) {
    return '<a class="msc-guide" href="' + esc(guideUrl(which)) + '" target="_blank" rel="noopener">' + esc(tw(key)) + " ↗</a>";
  }
  function brain() {
    try { return (window.currentBrainPath && window.currentBrainPath()) || ""; } catch (e) { return ""; }
  }

  // One checklist row: ok true = green, false = red, null = warning that does not stop the bot.
  function checklistHtml(chk) {
    var items = (chk && chk.items) || [];
    if (!items.length) return "";
    return '<div class="msc-checks">' + items.map(function (i) {
      var cls = i.ok === true ? "ok" : (i.ok === false ? "bad" : "warn");
      var mark = icon(i.ok === true ? "check" : (i.ok === false ? "x" : "triangle-alert"));
      return '<div class="msc-row ' + cls + '"><span class="msc-mark">' + mark + "</span>"
        + '<div class="msc-row-main"><div class="msc-row-label">' + esc(i.label)
        + (i.detail ? ' <span class="msc-row-detail">' + esc(i.detail) + "</span>" : "") + "</div>"
        + (i.ok !== true && i.fix ? '<div class="msc-row-fix">' + esc(i.fix) + "</div>" : "")
        + "</div></div>";
    }).join("") + "</div>";
  }

  function summaryHtml(chk) {
    if (!chk || !chk.items) return "";
    var bad = chk.items.filter(function (i) { return i.ok === false; }).length;
    return '<div class="msc-sum ' + (bad ? "bad" : "ok") + '">'
      + esc(bad ? tw("msc.sum_bad", { n: bad }) : tw("msc.sum_ok")) + "</div>";
  }

  function accountHtml(a) {
    var bots = (a.bots || []);
    var botTxt = bots.length
      ? bots.map(function (b) { return esc(b.name) + (b.enabled ? "" : " (" + esc(tw("msc.bot_off")) + ")"); }).join(", ")
      : esc(tw("msc.no_bot"));
    return '<div class="lv-card msc-acc" data-id="' + esc(a.id) + '">'
      + '<div class="lv-top"><div class="lv-name"><span class="lv-ic">' + ic("message-circle") + "</span><b>"
      + esc(a.page_name || a.label || a.page_id) + "</b></div></div>"
      + '<div class="lv-meta">Page ID ' + esc(a.page_id) + (a.app_id ? " · App ID " + esc(a.app_id) : "")
      + " · " + esc(tw("msc.bots")) + ": " + botTxt + "</div>"
      + '<div class="si-field msc-field msc-cmt-row"><label>' + esc(tw("msc.cmt_label")) + infoBtn() + "</label>"
      + infoBody(esc(tw("msc.cmt_how")))
      + commentSelect(a.comments || "inbox", "data-act-mode") + "</div>"
      + '<div class="lv-actions"><button class="s-btn-ghost" type="button" data-act="check">' + esc(tw("msc.check")) + "</button>"
      + '<button class="s-btn-ghost" type="button" data-act="repair">' + esc(tw("msc.repair")) + "</button>"
      + '<button class="s-btn-ghost" type="button" data-act="renew">' + esc(tw("msc.renew")) + "</button></div>"
      + '<div class="msc-slot"></div></div>';
  }

  // Literal keys so the i18n test can see every one of them.
  var FIELD_TEXT = {
    page_id: ["msc.f_page_id", "msc.f_page_id_how"],
    app_id: ["msc.f_app_id", "msc.f_app_id_how"],
    app_secret: ["msc.f_app_secret", "msc.f_app_secret_how"],
    token: ["msc.f_token", "msc.f_token_how"],
  };
  function field(key, type, ph) {
    var txt = FIELD_TEXT[key];
    return '<div class="si-field msc-field"><label>' + esc(tw(txt[0])) + infoBtn() + "</label>"
      + infoBody(esc(tw(txt[1])))
      + '<input class="js-input" data-f="' + key + '" type="' + type + '" autocomplete="off" spellcheck="false"'
      + (ph ? ' placeholder="' + esc(ph) + '"' : "") + "></div>";
  }

  // How the Page's comments are handled. Literal keys so the i18n test can see every one of them.
  var CMT_TEXT = { off: "msc.cmt_off", inbox: "msc.cmt_inbox", reply: "msc.cmt_reply" };
  function commentSelect(value, attr) {
    return '<select class="js-input msc-cmt" ' + attr + '="1">' + ["inbox", "reply", "off"].map(function (k) {
      return '<option value="' + k + '"' + (k === value ? " selected" : "") + ">" + esc(tw(CMT_TEXT[k])) + "</option>";
    }).join("") + "</select>";
  }

  // An address the owner pastes into the Meta app, with a Copy button.
  function copyRow(labelKey, howKey, value) {
    return '<div class="si-field msc-field msc-copy"><label>' + esc(tw(labelKey)) + infoBtn() + "</label>"
      + infoBody(esc(tw(howKey)))
      + '<div class="msc-copy-row"><input class="js-input" type="text" readonly value="' + esc(value || "") + '">'
      + '<button class="s-btn-ghost" type="button" data-copy="' + esc(value || "") + '">' + esc(tw("msc.copy")) + "</button></div></div>";
  }

  function formHtml(setup, preset) {
    var https = setup && setup.https;
    return '<div class="msc-form">'
      + '<div class="msc-form-head"><b>' + esc(tw("msc.form_head")) + "</b>" + infoBtn() + guideLink("full", "msc.guide") + "</div>"
      + infoBody(esc(tw("msc.form_how_login")))
      + (https ? "" : '<div class="msc-warn">' + esc(tw("msc.need_https")) + infoBtn() + "</div>"
        + infoBody(esc(tw("msc.need_https_how"))))
      + copyRow("msc.redirect", "msc.redirect_how", setup && setup.oauth_redirect)
      + copyRow("msc.privacy", "msc.privacy_how", setup && setup.privacy_url)
      + '<div class="msc-grid">'
      + field("app_id", "text", "987654321098765")
      + field("app_secret", "password", "")
      + "</div>"
      + '<div class="si-field msc-field"><label>' + esc(tw("msc.cmt_label")) + infoBtn() + "</label>"
      + infoBody(esc(tw("msc.cmt_how")))
      + commentSelect("inbox", "data-f-cmt") + "</div>"
      + '<div class="lv-form-act"><button class="s-btn" type="button" data-f="login"' + (https ? "" : " disabled") + ">"
      + esc(tw("msc.login")) + "</button>"
      + '<button class="s-btn-ghost" type="button" data-f="cancel">' + esc(tw("msc.cancel")) + "</button>"
      + '<span class="lv-msg" role="status" data-f="login-msg"></span></div>'
      + '<div class="msc-pick"></div>'
      // The 0.311.0 paste flow, kept for anyone who already has a token. Folded so the login is the obvious path.
      + '<button class="s-btn-ghost msc-manual-toggle" type="button" data-f="manual">' + esc(tw("msc.manual")) + "</button>"
      + '<div class="msc-manual" hidden>'
      + '<div class="msc-form-head"><b>' + esc(tw("msc.manual_head")) + "</b>" + infoBtn() + guideLink("steps", "msc.guide_steps") + "</div>"
      + infoBody(esc(tw("msc.form_how")))
      + '<div class="msc-grid">'
      + field("page_id", "text", "123456789012345")
      + field("token", "password", "EAA...")
      + "</div>"
      + '<div class="si-field msc-field"><label>' + esc(tw("msc.f_label")) + "</label>"
      + '<input class="js-input" data-f="label" type="text" autocomplete="off" value="' + esc(preset && preset.label || "") + '"></div>'
      + '<div class="lv-form-act"><button class="s-btn" type="button" data-f="go"' + (https ? "" : " disabled") + ">"
      + esc(tw("msc.connect")) + "</button>"
      + '<span class="lv-msg" role="status" data-f="go-msg"></span></div></div>'
      + '<div class="msc-slot"></div></div>';
  }

  // The Pages Facebook returned, to tick. Every Page starts ticked: most owners connect all of them.
  function pickHtml(pages) {
    if (!pages || !pages.length) return "";
    return '<div class="msc-pick-list"><div class="msc-form-head"><b>' + esc(tw("msc.pick_head", { n: pages.length })) + "</b></div>"
      + pages.map(function (pg) {
        return '<label class="msc-pick-row"><input type="checkbox" data-page="' + esc(pg.id) + '" checked>'
          + (pg.picture ? '<img class="msc-pick-pic" alt="" src="' + esc(pg.picture) + '">' : '<span class="msc-pick-pic">' + logo("20px") + "</span>")
          + '<span class="msc-pick-name"><b>' + esc(pg.name || pg.id) + '</b><span class="lv-meta">Page ID ' + esc(pg.id) + "</span></span></label>";
      }).join("")
      + '<div class="lv-form-act"><button class="s-btn" type="button" data-f="finish">' + esc(tw("msc.finish")) + "</button>"
      + '<span class="lv-msg" role="status" data-f="finish-msg"></span></div></div>';
  }

  // One block per Page after finish: its checklist, or why it failed.
  function resultsHtml(results) {
    return (results || []).map(function (r) {
      return '<div class="msc-result"><div class="msc-form-head"><b>' + esc(r.page_name || r.page_id) + "</b></div>"
        + (r.ok ? summaryHtml(r.check) + checklistHtml(r.check)
          + (r.repair_errors && r.repair_errors.length ? '<div class="lv-note">' + r.repair_errors.map(esc).join("<br>") + "</div>" : "")
          : '<div class="lv-note">' + esc(r.error || tw("msc.err_net")) + "</div>") + "</div>";
    }).join("");
  }

  async function api(url, body) {
    try {
      var r = await fetch(url, body === undefined ? undefined : {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      return await r.json();
    } catch (e) { return { ok: false, error: tw("msc.err_net") }; }
  }

  function logo(size) {
    var I = typeof window !== "undefined" && window.Icons;
    return I && I.kenh ? I.kenh("messenger", { size: size }) : ic("message-circle");
  }

  // The card in the "Available" grid, same frame as the catalog cards. `category` is the catalog's own key for
  // messaging services (console.js passes the one Zalo carries), so the category filter keeps working.
  function catCard(category) {
    return '<div class="cat-card msc-cat" data-cat="' + esc(category || "") + '">'
      + '<div class="cat-ico">' + logo("28px") + "</div>"
      + '<div class="cat-name">' + esc(tw("msc.head")) + ' <span class="prov-kind">' + esc(tw("msc.badge")) + "</span>"
      + infoBtn() + "</div>"
      + '<div class="cat-desc j-clamp2">' + esc(tw("msc.card_desc")) + "</div>"
      + infoBody(esc(tw("msc.intro")))
      + '<button class="gcard-btn" type="button" data-msc-open="1">' + esc(tw("models.connect")) + "</button></div>";
  }

  // The connected Pages, as one card in the "Connected" list. Empty string when nothing is connected yet.
  function groupHtml(accounts) {
    if (!accounts || !accounts.length) return "";
    return '<div class="prov-card conn-card msc-group">'
      + '<div class="prov-head"><span class="conn-ico">' + logo("24px") + "</span>"
      + '<div class="prov-info"><div class="prov-name">' + esc(tw("msc.head")) + infoBtn() + "</div>"
      + '<div class="prov-status j-clamp2">' + esc(tw("msc.card_desc")) + "</div>"
      + infoBody(esc(tw("msc.intro"))) + "</div></div>"
      // The Pages open in a popup (owner, 28/10/2026, same as the bot cards on the Chatbot page): a shop can connect many
      // Pages, and one full card each stretched the Connections page. The card keeps one compact row with the count.
      + '<button type="button" class="cb-st msc-more" data-msc-pages aria-haspopup="dialog"><span class="cb-st-chips">'
      + '<span class="cb-st-chip">' + esc(tw("msc.pages_n", { n: accounts.length })) + "</span></span>"
      + '<span class="cb-st-more">' + esc(tw("msc.view")) + " " + icon("chevron-right") + "</span></button>"
      + '<div class="conn-accounts"><button class="conn-chip add" type="button" data-msc-open="1">＋ '
      + esc(tw("msc.add_more")) + "</button></div></div>";
  }

  var setup = null, host = null;

  async function load() {
    var b = brain();
    setup = await api("/messenger/setup" + (b ? "?brain=" + encodeURIComponent(b) : ""));
    if (!host) return setup;
    if (!setup || !setup.ok) {
      host.innerHTML = '<div class="lv-note">' + esc((setup && setup.error) || tw("msc.err_net")) + "</div>";
      return setup;
    }
    var accounts = setup.accounts || [];
    host.innerHTML = groupHtml(accounts);
    // A Page counts as a connection: in the heading, and the "nothing connected yet" line must not sit on top of it.
    var total = addToConnCount("fb", accounts.length);
    var empty = document.querySelector("#connList > .mp-empty");
    if (empty) empty.hidden = total > 0;
    host.querySelectorAll("[data-msc-open]").forEach(function (b) { b.onclick = function () { openForm(null); }; });
    var more = host.querySelector("[data-msc-pages]");
    if (more) more.onclick = function () { openPages(); };
    return setup;
  }

  // Every connected Page with its Check / Repair / Renew buttons, in the dialog this page opens for every service.
  function openPages() {
    var M = typeof window !== "undefined" && window.JavisConnModal;
    var accounts = (setup && setup.accounts) || [];
    if (!M || !accounts.length) return;
    var m = M.open(M.head(esc(tw("msc.pages_head", { n: accounts.length })))
      + '<div class="conn-form msc-list">' + accounts.map(accountHtml).join("") + "</div>", 680);
    m.querySelectorAll(".msc-acc").forEach(function (card) {
      card.querySelectorAll("[data-act]").forEach(function (btn) {
        btn.onclick = function () { act(card, card.dataset.id, btn.dataset.act); };
      });
      var sel = card.querySelector("[data-act-mode]");
      if (sel) sel.onchange = async function () {
        var slot = card.querySelector(".msc-slot");
        var r = await api("/messenger/comments", { account_id: card.dataset.id, mode: sel.value });
        slot.innerHTML = '<div class="lv-meta">' + esc(r.ok ? tw("msc.cmt_saved") : (r.error || tw("msc.err_net"))) + "</div>";
        if (r.ok) load();
      };
    });
  }

  function sleep(ms) { return new Promise(function (res) { setTimeout(res, ms); }); }

  function wireCopy(root) {
    root.querySelectorAll("[data-copy]").forEach(function (b) {
      b.onclick = function () {
        var v = b.getAttribute("data-copy") || "";
        try { navigator.clipboard.writeText(v); b.textContent = tw("msc.copied"); } catch (e) {}
        setTimeout(function () { b.textContent = tw("msc.copy"); }, 1500);
      };
    });
  }

  // Log in with Facebook: open the tab first (a tab opened after an await is blocked as a popup), then point it at
  // Facebook once the server has checked the app credentials, then poll until the Pages come back.
  async function login(form) {
    var msg = form.querySelector('[data-f="login-msg"]');
    var btn = form.querySelector('[data-f="login"]');
    var appId = (form.querySelector('[data-f="app_id"]').value || "").trim();
    var secret = (form.querySelector('[data-f="app_secret"]').value || "").trim();
    if (!appId || !secret) { msg.textContent = tw("msc.need_app"); return; }
    var win = null;
    try { win = window.open("about:blank", "_blank"); } catch (e) { win = null; }
    btn.disabled = true;
    msg.textContent = tw("msc.working");
    var r = await api("/messenger/oauth/start", { app_id: appId, app_secret: secret, brain: brain() });
    if (!r.ok) {
      btn.disabled = false;
      msg.textContent = r.error || tw("msc.err_net");
      if (win) try { win.close(); } catch (e) {}
      return;
    }
    form.querySelector('[data-f="app_secret"]').value = "";
    if (win) {
      try { win.location.href = r.url; } catch (e) { win = null; }
    }
    msg.innerHTML = esc(tw("msc.waiting")) + (win ? "" : ' <a href="' + esc(r.url) + '" target="_blank" rel="noopener">'
      + esc(tw("msc.open_fb")) + "</a>");
    var until = Date.now() + 15 * 60 * 1000;
    while (Date.now() < until && form.isConnected) {
      await sleep(2000);
      var st = await api("/messenger/oauth/result?state=" + encodeURIComponent(r.state));
      if (!st || st.status === "pending") continue;
      btn.disabled = false;
      if (st.status !== "ready") { msg.textContent = st.error || tw("msc.err_net"); return; }
      msg.textContent = tw("msc.signed_in");
      var pick = form.querySelector(".msc-pick");
      pick.innerHTML = pickHtml(st.pages);
      var fin = pick.querySelector('[data-f="finish"]');
      if (fin) fin.onclick = function () { finish(form, r.state); };
      return;
    }
    btn.disabled = false;
    if (form.isConnected) msg.textContent = tw("msc.expired");
  }

  async function finish(form, state) {
    var pick = form.querySelector(".msc-pick");
    var fmsg = pick.querySelector('[data-f="finish-msg"]');
    var ids = [];
    pick.querySelectorAll("[data-page]").forEach(function (c) { if (c.checked) ids.push(c.getAttribute("data-page")); });
    if (!ids.length) { fmsg.textContent = tw("msc.pick_none"); return; }
    var fin = pick.querySelector('[data-f="finish"]');
    fin.disabled = true;
    fmsg.textContent = tw("msc.working");
    var r = await api("/messenger/oauth/finish", { state: state, page_ids: ids,
      comments: form.querySelector("[data-f-cmt]").value });
    fin.disabled = false;
    if (!r.results) { fmsg.textContent = r.error || tw("msc.err_net"); return; }
    var good = r.results.filter(function (x) { return x.ok; }).length;
    fmsg.textContent = tw("msc.finished", { n: good, total: r.results.length });
    form.querySelector(".msc-slot").innerHTML = resultsHtml(r.results);
    load();
  }

  // The form, in the same dialog every other service opens from this page.
  async function openForm(preset) {
    var M = typeof window !== "undefined" && window.JavisConnModal;
    if (!M) return;
    if (!setup) await load();
    var m = M.open(M.head(esc(tw("msc.dialog_head"))) + '<div class="conn-form">' + formHtml(setup || {}, preset) + "</div>", 640);
    var form = m.querySelector(".msc-form");
    wireCopy(form);
    if (preset && preset.page_id) form.querySelector('[data-f="page_id"]').value = preset.page_id;
    if (preset && preset.app_id) form.querySelector('[data-f="app_id"]').value = preset.app_id;
    form.querySelector('[data-f="cancel"]').onclick = function () { M.close(); };
    form.querySelector('[data-f="login"]').onclick = function () { login(form); };
    form.querySelector('[data-f="manual"]').onclick = function () {
      var box = form.querySelector(".msc-manual");
      box.hidden = !box.hidden;
    };
    form.querySelector('[data-f="go"]').onclick = async function () {
      var v = {};
      ["page_id", "app_id", "app_secret", "token", "label"].forEach(function (k) {
        v[k] = (form.querySelector('[data-f="' + k + '"]').value || "").trim();
      });
      v.brain = brain();
      var msg = form.querySelector('[data-f="go-msg"]');
      var go = form.querySelector('[data-f="go"]');
      go.disabled = true;
      msg.textContent = tw("msc.working");
      var r = await api("/messenger/connect", v);
      go.disabled = false;
      if (!r.ok) { msg.textContent = r.error || tw("msc.err_net"); return; }
      // The secrets have done their job; do not leave them sitting in the page.
      form.querySelector('[data-f="app_secret"]').value = "";
      form.querySelector('[data-f="token"]').value = "";
      msg.textContent = tw(r.updated ? "msc.updated" : "msc.saved");
      form.querySelector(".msc-slot").innerHTML = summaryHtml(r.check) + checklistHtml(r.check)
        + (r.repair_errors && r.repair_errors.length ? '<div class="lv-note">' + r.repair_errors.map(esc).join("<br>") + "</div>" : "");
      load();
    };
    setTimeout(function () { try { form.querySelector('[data-f="app_id"]').focus(); } catch (e) {} }, 30);
  }

  async function act(card, id, what) {
    if (what === "renew") {
      var a = ((setup && setup.accounts) || []).filter(function (x) { return x.id === id; })[0] || {};
      openForm(a);
      return;
    }
    var slot = card.querySelector(".msc-slot");
    slot.innerHTML = '<div class="lv-meta">' + esc(tw("msc.working")) + "</div>";
    var r = await api("/messenger/check", { account_id: id, repair: what === "repair" });
    if (!r.ok) { slot.innerHTML = '<div class="lv-note">' + esc(r.error || tw("msc.err_net")) + "</div>"; return; }
    slot.innerHTML = summaryHtml(r.check) + checklistHtml(r.check)
      + (r.repair_errors && r.repair_errors.length ? '<div class="lv-note">' + r.repair_errors.map(esc).join("<br>") + "</div>" : "");
  }

  // `el` is the slot under the connected list. Draws the connected Pages there (nothing when there are none).
  function mount(el) {
    host = el || null;
    if (host) load();
  }

  var api_ = { mount: mount, openForm: openForm, catCard: catCard, groupHtml: groupHtml, checklistHtml: checklistHtml,
    summaryHtml: summaryHtml, accountHtml: accountHtml, formHtml: formHtml, addToConnCount: addToConnCount,
    openPages: openPages, pickHtml: pickHtml, resultsHtml: resultsHtml, commentSelect: commentSelect, guideUrl: guideUrl };
  if (typeof window !== "undefined") window.JavisMessenger = api_;
  if (typeof module !== "undefined" && module.exports) module.exports = api_;
})();
