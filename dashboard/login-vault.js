/* Cookies page, once "Kho đăng nhập" / Login vault (0.251.0; renamed and given a file upload in 0.261.0).
 *
 * The owner signs in on their own browser, exports that site's cookies and pastes them here. The server
 * (server/login_vault.py) encrypts them; Javis then opens pages behind that sign-in (tool javis_login) and
 * page watches can use it. This page adds, checks, updates, switches off and deletes sign-ins. It never
 * receives a cookie back from the server: the list carries names, domains and status only. A cookie file
 * (Cookie-Editor JSON, cookies.txt) is read in the browser and goes in as the same text a paste would.
 *
 * Render helpers are pure (tested with node); `mount` wires the API. No long dashes anywhere. */
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

  var STATUS = {
    ok: { key: "lv.st_ok", cls: "ok" },
    signed_out: { key: "lv.st_out", cls: "bad" },
    error: { key: "lv.st_err", cls: "warn" },
    unknown: { key: "lv.st_unknown", cls: "idle" },
  };

  function fmtDate(ts) {
    if (!ts) return "";
    var d = new Date(ts * 1000);
    var p = function (n) { return String(n).padStart(2, "0"); };
    return p(d.getDate()) + "/" + p(d.getMonth() + 1) + "/" + d.getFullYear();
  }
  function fmtTime(ts) {
    if (!ts) return "";
    var d = new Date(ts * 1000);
    var p = function (n) { return String(n).padStart(2, "0"); };
    return p(d.getHours()) + ":" + p(d.getMinutes()) + " " + p(d.getDate()) + "/" + p(d.getMonth() + 1);
  }

  /* The expiry line: past, soon (under 7 days) or a plain date. `now` in seconds, for tests. */
  function expiryText(lg, now) {
    now = now || Date.now() / 1000;
    if (!lg.expires_at) return tw("lv.exp_session");
    if (lg.expired || lg.expires_at <= now) return tw("lv.exp_past");
    var days = Math.floor((lg.expires_at - now) / 86400);
    if (days < 7) return tw("lv.exp_soon", { n: Math.max(days, 0) });
    return tw("lv.exp_date", { d: fmtDate(lg.expires_at) });
  }

  /* One card. Returns escaped HTML. */
  function cardHtml(lg, now) {
    var st = STATUS[lg.status] || STATUS.unknown;
    var stTxt = tw(st.key);
    var soon = !lg.expired && lg.expires_at && lg.expires_at - (now || Date.now() / 1000) < 7 * 86400;
    var meta = [
      esc(tw("lv.count", { n: lg.count || 0 })),
      '<span class="' + (lg.expired ? "lv-bad" : (soon ? "lv-warnt" : "")) + '">' + esc(expiryText(lg, now)) + "</span>",
    ];
    if (lg.uses) meta.push(esc(tw("lv.used", { n: lg.uses, t: fmtTime(lg.used_at) })));
    return '<div class="lv-card' + (lg.allow_ai ? "" : " off") + '" data-id="' + esc(lg.id) + '">'
      + '<div class="lv-top">'
      + '<div class="lv-name"><span class="lv-ic">' + ic("cookie") + "</span><b>" + esc(lg.name) + "</b></div>"
      + '<span class="lv-st ' + st.cls + '" title="' + esc(lg.status_note || stTxt) + '"><i></i>' + esc(stTxt) + "</span>"
      + "</div>"
      + '<div class="lv-dom">' + (lg.domains || []).slice(0, 6).map(function (d) { return "<span>" + esc(d) + "</span>"; }).join("")
      + ((lg.domains || []).length > 6 ? "<span>+" + ((lg.domains || []).length - 6) + "</span>" : "") + "</div>"
      + '<div class="lv-meta">' + meta.join(" · ") + "</div>"
      + (lg.status !== "ok" && lg.status_note ? '<div class="lv-note">' + esc(lg.status_note) + "</div>" : "")
      + '<label class="lv-allow"><input type="checkbox" data-act="toggle"' + (lg.allow_ai ? " checked" : "") + ">"
      + '<span class="lv-sw"></span>' + esc(tw("lv.allow")) + "</label>"
      + '<div class="lv-actions">'
      + '<button class="s-btn-ghost" data-act="check">' + ic("rotate-cw") + " " + esc(tw("lv.check")) + "</button>"
      + '<button class="s-btn-ghost" data-act="replace">' + ic("clipboard-paste") + " " + esc(tw("lv.update")) + "</button>"
      + '<button class="s-btn-ghost" data-act="more">' + ic("ellipsis") + "</button>"
      + "</div>"
      + '<div class="lv-slot"></div>'
      + "</div>";
  }

  function pasteFormHtml(withName) {
    return '<div class="lv-form">'
      + (withName ? '<div class="si-field"><label>' + esc(tw("lv.name")) + '</label><input data-f="name" maxlength="80" placeholder="'
        + esc(tw("lv.name_ph")) + '"></div>' : "")
      + '<div class="si-field"><div class="lv-paste-row"><label>' + esc(tw("lv.paste")) + "</label>"
      + '<button type="button" class="s-btn-ghost lv-file" data-f="file">' + ic("file-up") + " " + esc(tw("lv.file_pick"))
      + '</button><input type="file" data-f="filein" accept="' + FILE_ACCEPT + '" hidden></div><textarea data-f="text" rows="5" spellcheck="false" placeholder="'
      + esc(tw("lv.paste_ph")) + '"></textarea></div>'
      + '<div class="si-field lv-site" hidden><label>' + esc(tw("lv.site")) + '</label><input data-f="site" placeholder="'
      + esc(tw("lv.site_ph")) + '"></div>'
      + (withName ? '<div class="si-field"><label>' + esc(tw("lv.test_url")) + '</label><input data-f="test_url" placeholder="'
        + esc(tw("lv.test_url_ph")) + '"></div>' : "")
      + '<div class="lv-form-act"><button class="s-btn" data-f="save">' + esc(tw(withName ? "lv.save" : "lv.save_update")) + "</button>"
      + '<button class="s-btn-ghost" data-f="cancel">' + esc(tw("lv.cancel")) + "</button>"
      + '<span class="lv-msg" role="status"></span></div>'
      + "</div>";
  }

  /* A bare "name=value; ..." header has no domain in it, so the site field shows only then. */
  /* The (i) text, built here because the dictionaries hold plain text only (test_i18n). Every line of it
     goes into the (i) block (mount passes this to infoBody), so none of it stands open on the page. */
  var INTRO = [["p", "lv.intro_what"], ["h", "lv.intro_how"], ["li", "lv.intro_s1"], ["li", "lv.intro_s2"],
    ["li", "lv.intro_s3"], ["p", "lv.intro_formats"], ["hp", "lv.intro_safe_h", "lv.intro_safe"],
    ["hp", "lv.intro_note_h", "lv.intro_note"]];
  function introHtml() {
    var out = "", inList = false;
    INTRO.forEach(function (row) {
      if (row[0] === "li" && !inList) { out += "<ol>"; inList = true; }
      if (row[0] !== "li" && inList) { out += "</ol>"; inList = false; }
      if (row[0] === "p") out += "<p>" + esc(tw(row[1])) + "</p>";
      else if (row[0] === "h") out += "<p><b>" + esc(tw(row[1])) + ":</b></p>";
      else if (row[0] === "li") out += "<li>" + esc(tw(row[1])) + "</li>";
      else out += "<p><b>" + esc(tw(row[1])) + ":</b> " + esc(tw(row[2])) + "</p>";
    });
    return out + (inList ? "</ol>" : "");
  }

  function needsSite(text) {
    var s = String(text || "").trim();
    return !!s && s[0] !== "[" && s[0] !== "{" && s.indexOf("\t") < 0;
  }

  /* Cookie files are small (one site is a few KB); anything near the server's 400k-character cap is the
     whole browser's cookie jar, which the owner should not hand over anyway. */
  var MAX_FILE = 1024 * 1024;
  var FILE_ACCEPT = ".json,.txt,.cookies,text/plain,application/json";

  /* A name suggested by the file name: "shopee.vn.json" -> "shopee.vn". Generic export names give ""
     so the server names the entry after the cookies' domain instead. */
  function nameFromFile(fname) {
    var base = String(fname || "").replace(/^.*[\\/]/, "").replace(/\.(json|txt|cookies)$/i, "")
      .replace(/\s*\(\d+\)$/, "").trim();
    if (/^(cookies?|export|cookie[-_ ]?editor|storage[-_ ]?state)([-_ ]?\d+)?$/i.test(base)) return "";
    base = base.replace(/[-_ ]cookies?$/i, "");
    return base.slice(0, 80);
  }

  function readFile(file) {
    return new Promise(function (resolve) {
      if (!file) return resolve({ ok: false, error: tw("lv.file_err") });
      if (file.size > MAX_FILE) return resolve({ ok: false, error: tw("lv.file_big") });
      var fr = new FileReader();
      fr.onload = function () { resolve({ ok: true, text: String(fr.result || ""), name: file.name || "" }); };
      fr.onerror = function () { resolve({ ok: false, error: tw("lv.file_err") }); };
      fr.readAsText(file);
    });
  }

  async function api(url, body) {
    try {
      var r = await fetch(url, body === undefined ? undefined : {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      return await r.json();
    } catch (e) { return { ok: false, error: tw("lv.err_net") }; }
  }

  function wireForm(form, onSave, onCancel) {
    var ta = form.querySelector('[data-f="text"]');
    var site = form.querySelector(".lv-site");
    ta.addEventListener("input", function () { site.hidden = !needsSite(ta.value); });
    var fin = form.querySelector('[data-f="filein"]');
    async function useFile(file) {
      var msg = form.querySelector(".lv-msg");
      var r = await readFile(file);
      msg.classList.toggle("ok", !!r.ok);
      if (!r.ok) { msg.textContent = r.error; return; }
      ta.value = r.text;
      ta.dispatchEvent(new Event("input"));
      var nm = form.querySelector('[data-f="name"]');
      if (nm && !nm.value.trim()) nm.value = nameFromFile(r.name);
      msg.textContent = tw("lv.file_ok", { f: r.name });
    }
    form.querySelector('[data-f="file"]').onclick = function () { fin.click(); };
    fin.onchange = function () { if (fin.files && fin.files[0]) useFile(fin.files[0]); fin.value = ""; };
    ta.addEventListener("dragover", function (e) { e.preventDefault(); ta.classList.add("drop"); });
    ta.addEventListener("dragleave", function () { ta.classList.remove("drop"); });
    ta.addEventListener("drop", function (e) {
      ta.classList.remove("drop");
      var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (!f) return;
      e.preventDefault();
      useFile(f);
    });
    form.querySelector('[data-f="cancel"]').onclick = onCancel;
    form.querySelector('[data-f="save"]').onclick = async function () {
      var btn = this, msg = form.querySelector(".lv-msg");
      var val = function (k) { var el = form.querySelector('[data-f="' + k + '"]'); return el ? el.value.trim() : ""; };
      btn.disabled = true; msg.textContent = ""; msg.classList.remove("ok");
      var r = await onSave({ name: val("name"), text: ta.value, site: val("site"), test_url: val("test_url") });
      btn.disabled = false;
      if (!r.ok) { msg.textContent = r.error || tw("lv.err_net"); return; }
      ta.value = "";
    };
    setTimeout(function () { try { (form.querySelector('[data-f="name"]') || ta).focus(); } catch (e) {} }, 30);
  }

  function mount(el) {
    if (!el) return;
    el.innerHTML = '<div class="cview-section lv-page">'
      + '<div class="lv-head"><span class="lv-title">' + ic("cookie") + " " + esc(tw("lv.head")) + infoBtn() + "</span>"
      + '<div class="lv-head-act"><button class="s-btn-ghost lv-upload" type="button">' + ic("file-up") + " " + esc(tw("lv.upload")) + "</button>"
      + '<button class="s-btn lv-add" type="button">' + ic("plus") + " " + esc(tw("lv.add")) + "</button></div></div>"
      + infoBody(introHtml())
      + '<div class="lv-warn" hidden></div>'
      + '<div class="lv-new"></div>'
      + '<div class="lv-list"></div></div>';
    var q = function (s) { return el.querySelector(s); };
    var items = [];

    function closeNew() { q(".lv-new").innerHTML = ""; q(".lv-add").hidden = false; }
    // Upload = open the add form (if not open yet) and its file picker, in the same click so the browser allows it.
    q(".lv-upload").onclick = function () {
      if (!q(".lv-new .lv-form")) q(".lv-add").onclick();
      q('.lv-new [data-f="filein"]').click();
    };
    q(".lv-add").onclick = function () {
      q(".lv-add").hidden = true;
      q(".lv-new").innerHTML = '<div class="lv-card lv-card-new">' + pasteFormHtml(true) + "</div>";
      wireForm(q(".lv-new .lv-form"), async function (v) {
        var r = await api("/logins", v);
        if (r.ok) {
          closeNew();
          await load();
          // First check right away, so the card says whether the paste worked.
          act(r.login.id, "check");
        }
        return r;
      }, closeNew);
    };

    async function act(id, action, extra) {
      var card = el.querySelector('.lv-card[data-id="' + id + '"]');
      if (card) card.classList.add("busy");
      var body = Object.assign({ id: id, action: action }, extra || {});
      var r = await api("/logins/action", body);
      if (card) card.classList.remove("busy");
      if (!r.ok) { alert(r.error || tw("lv.err_net")); return r; }
      await load();
      return r;
    }

    function moreMenu(card, lg) {
      var slot = card.querySelector(".lv-slot");
      if (slot.dataset.open === "more") { slot.innerHTML = ""; slot.dataset.open = ""; return; }
      slot.dataset.open = "more";
      slot.innerHTML = '<div class="lv-more">'
        + '<button class="s-btn-ghost" data-m="rename">' + ic("pencil") + " " + esc(tw("lv.rename")) + "</button>"
        + '<button class="s-btn-ghost" data-m="test">' + ic("link") + " " + esc(tw("lv.set_test")) + "</button>"
        + '<button class="s-btn-ghost lv-del" data-m="delete">' + ic("trash-2") + " " + esc(tw("lv.delete")) + "</button>"
        + '<div class="lv-test">' + esc(tw("lv.test_now", { u: lg.test_url || "-" })) + "</div></div>";
      slot.querySelector('[data-m="rename"]').onclick = function () {
        var n = prompt(tw("lv.rename_q"), lg.name);
        if (n && n.trim() && n.trim() !== lg.name) act(lg.id, "rename", { name: n.trim() });
      };
      slot.querySelector('[data-m="test"]').onclick = function () {
        var u = prompt(tw("lv.test_q"), lg.test_url || "");
        if (u != null && u.trim()) act(lg.id, "test_url", { test_url: u.trim() });
      };
      slot.querySelector('[data-m="delete"]').onclick = function () {
        if (confirm(tw("lv.delete_q", { ten: lg.name }))) act(lg.id, "delete");
      };
    }

    function render() {
      var host = q(".lv-list");
      if (!items.length) {
        host.innerHTML = '<div class="lv-empty">' + ic("cookie") + "<p>" + esc(tw("lv.empty")) + "</p></div>";
        return;
      }
      host.innerHTML = items.map(function (lg) { return cardHtml(lg); }).join("");
      host.querySelectorAll(".lv-card[data-id]").forEach(function (card) {
        var lg = items.filter(function (x) { return x.id === card.dataset.id; })[0];
        card.querySelector('[data-act="toggle"]').onchange = function () {
          act(lg.id, this.checked ? "allow" : "deny");
        };
        card.querySelector('[data-act="check"]').onclick = function () { act(lg.id, "check"); };
        card.querySelector('[data-act="more"]').onclick = function () { moreMenu(card, lg); };
        card.querySelector('[data-act="replace"]').onclick = function () {
          var slot = card.querySelector(".lv-slot");
          if (slot.dataset.open === "replace") { slot.innerHTML = ""; slot.dataset.open = ""; return; }
          slot.dataset.open = "replace";
          slot.innerHTML = pasteFormHtml(false);
          wireForm(slot.querySelector(".lv-form"), async function (v) {
            var r = await api("/logins/action", { id: lg.id, action: "replace", text: v.text, site: v.site });
            if (r.ok) { await load(); act(lg.id, "check"); }
            return r;
          }, function () { slot.innerHTML = ""; slot.dataset.open = ""; });
        };
      });
    }

    async function load() {
      var d = await api("/logins");
      var warn = q(".lv-warn");
      if (!d.ok) {
        warn.hidden = false;
        warn.textContent = d.error || tw("lv.err_net");
        return;
      }
      warn.hidden = d.encryption !== false;
      warn.textContent = d.encryption === false ? tw("lv.no_crypto") : "";
      items = d.logins || [];
      render();
    }

    load();
  }

  var api_ = { mount: mount, introHtml: introHtml, cardHtml: cardHtml, expiryText: expiryText, needsSite: needsSite, pasteFormHtml: pasteFormHtml,
    nameFromFile: nameFromFile };
  if (typeof window !== "undefined") window.JavisLoginVault = api_;
  if (typeof module !== "undefined" && module.exports) module.exports = api_;
})();
