/* Facebook Messenger card on the Connections page (0.301.0).
 *
 * The Messenger channel already answered a Page inbox; what owners got stuck on was the setup on Meta's side (user token
 * instead of Page token, short-lived token, webhook without the `messages` field, missing permissions). This card takes the
 * four things an owner can copy from developers.facebook.com and lets the server (server/messenger_setup.py) do the rest:
 * Page token, app webhook, Page subscription. It then shows a checklist, and each saved Page has Check and Repair buttons.
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
  function brain() {
    try { return (window.currentBrainPath && window.currentBrainPath()) || ""; } catch (e) { return ""; }
  }

  // One checklist row: ok true = green, false = red, null = warning that does not stop the bot.
  function checklistHtml(chk) {
    var items = (chk && chk.items) || [];
    if (!items.length) return "";
    return '<div class="msc-checks">' + items.map(function (i) {
      var cls = i.ok === true ? "ok" : (i.ok === false ? "bad" : "warn");
      var mark = i.ok === true ? "✓" : (i.ok === false ? "✕" : "!");
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

  function formHtml(setup, preset) {
    var https = setup && setup.https;
    return '<div class="lv-card lv-card-new msc-form">'
      + '<div class="msc-form-head"><b>' + esc(tw("msc.form_head")) + "</b>" + infoBtn() + "</div>"
      + infoBody(esc(tw("msc.form_how")))
      + (https ? "" : '<div class="msc-warn">' + esc(tw("msc.need_https")) + infoBtn() + "</div>"
        + infoBody(esc(tw("msc.need_https_how"))))
      + '<div class="msc-grid">'
      + field("page_id", "text", "1253287447877254")
      + field("app_id", "text", "1411749634467481")
      + field("app_secret", "password", "")
      + field("token", "password", "EAA...")
      + "</div>"
      + '<div class="si-field msc-field"><label>' + esc(tw("msc.f_label")) + "</label>"
      + '<input class="js-input" data-f="label" type="text" autocomplete="off" value="' + esc(preset && preset.label || "") + '"></div>'
      + '<div class="lv-form-act"><button class="s-btn" type="button" data-f="go"' + (https ? "" : " disabled") + ">"
      + esc(tw("msc.connect")) + "</button>"
      + '<button class="s-btn-ghost" type="button" data-f="cancel">' + esc(tw("msc.cancel")) + "</button>"
      + '<span class="lv-msg" role="status"></span></div>'
      + '<div class="msc-slot"></div></div>';
  }

  async function api(url, body) {
    try {
      var r = await fetch(url, body === undefined ? undefined : {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      return await r.json();
    } catch (e) { return { ok: false, error: tw("msc.err_net") }; }
  }

  function mount(el) {
    if (!el) return;
    el.innerHTML = '<div class="cview-section msc">'
      + '<h3>◆ ' + esc(tw("msc.head")) + infoBtn() + "</h3>"
      + infoBody(esc(tw("msc.intro")))
      + '<div class="msc-list"></div><div class="msc-new"></div>'
      + '<button class="mp-btn primary msc-add" type="button" style="margin-left:0">' + ic("plus") + " "
      + esc(tw("msc.add")) + "</button></div>";
    var q = function (s) { return el.querySelector(s); };
    var setup = null;

    function openForm(preset) {
      q(".msc-add").hidden = true;
      q(".msc-new").innerHTML = formHtml(setup, preset);
      var form = q(".msc-new .msc-form");
      if (preset && preset.page_id) form.querySelector('[data-f="page_id"]').value = preset.page_id;
      if (preset && preset.app_id) form.querySelector('[data-f="app_id"]').value = preset.app_id;
      form.querySelector('[data-f="cancel"]').onclick = function () { q(".msc-new").innerHTML = ""; q(".msc-add").hidden = false; };
      form.querySelector('[data-f="go"]').onclick = async function () {
        var v = {};
        ["page_id", "app_id", "app_secret", "token", "label"].forEach(function (k) {
          v[k] = (form.querySelector('[data-f="' + k + '"]').value || "").trim();
        });
        v.brain = brain();
        var msg = form.querySelector(".lv-msg");
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
      setTimeout(function () { try { form.querySelector('[data-f="page_id"]').focus(); } catch (e) {} }, 30);
    }

    async function act(card, id, what) {
      if (what === "renew") {
        var a = (setup.accounts || []).filter(function (x) { return x.id === id; })[0] || {};
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

    async function load() {
      var b = brain();
      setup = await api("/messenger/setup" + (b ? "?brain=" + encodeURIComponent(b) : ""));
      if (!setup || !setup.ok) { q(".msc-list").innerHTML = '<div class="lv-note">' + esc((setup && setup.error) || tw("msc.err_net")) + "</div>"; return; }
      var list = q(".msc-list");
      list.innerHTML = (setup.accounts || []).map(accountHtml).join("");
      list.querySelectorAll(".msc-acc").forEach(function (card) {
        card.querySelectorAll("[data-act]").forEach(function (btn) {
          btn.onclick = function () { act(card, card.dataset.id, btn.dataset.act); };
        });
      });
    }

    q(".msc-add").onclick = function () { openForm(null); };
    load();
  }

  var api_ = { mount: mount, checklistHtml: checklistHtml, summaryHtml: summaryHtml, accountHtml: accountHtml, formHtml: formHtml };
  if (typeof window !== "undefined") window.JavisMessenger = api_;
  if (typeof module !== "undefined" && module.exports) module.exports = api_;
})();
