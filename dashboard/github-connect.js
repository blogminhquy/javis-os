/* github-connect.js - GitHub inside chat, phase G1 (0.362.0, docs/dev/2026-10-github-trong-chat-spec.md).
 *
 * Three pieces, one module:
 *   1. The GitHub card on the Connections page. It is built into Javis (owner, 2026-10-27): always shown, connected
 *      or not, no Store pack. Connect with a token, or reuse the brain-backup token after the server checks it.
 *      The card also lists the repos cloned in this brain, each with "Remove from brain" (the clone only; GitHub
 *      is never touched, and the server refuses while work would be lost).
 *   2. "GitHub repo" in the composer's + menu: pick one or more repos for the open conversation. On an empty chat the
 *      choice is held until the first message mints the session id (app.js calls claimPending), like a pinned folder.
 *   3. A chip next to the pinned-folder chip naming the attached repos; it opens the same panel.
 * The server never sends a token back. Pure helpers are exported for node tests. Never use the em dash here.
 */
(function () {
  "use strict";

  // ---- pure helpers ----
  function chipText(names, max) {
    var list = (names || []).filter(Boolean);
    if (!list.length) return "";
    var first = String(list[0]).split("/").pop();
    if (first.length > max) first = first.slice(0, max - 1) + "…";
    return first + (list.length > 1 ? " +" + (list.length - 1) : "");
  }
  function toggle(list, name) {
    var out = (list || []).slice(), i = out.indexOf(name);
    if (i >= 0) out.splice(i, 1); else out.push(name);
    return out;
  }
  function sameSet(a, b) {
    a = (a || []).slice().sort(); b = (b || []).slice().sort();
    return a.length === b.length && a.every(function (x, i) { return x === b[i]; });
  }

  // Icon of a conversation (spec 12.1): server state -> what to draw. Pure so node tests can check every state.
  function iconSpec(ic) {
    if (!ic || !ic.state) return null;
    var key = { working: "gh.st_working", ready: "gh.st_ready", merged: "gh.st_merged", broken: "gh.st_broken" }[ic.state];
    if (!key) return null;
    return { cls: "gh-st gh-" + ic.state + (ic.merged_warning ? " gh-warn" : "") + (ic.sub ? " gh-sub-" + ic.sub : ""),
      key: key, count: ic.state === "working" && ic.running > 1 ? ic.running : 0,
      subKey: ic.merged_warning ? "gh.st_post_red" : (ic.sub ? "gh.sub_" + ic.sub : "") };
  }

  var pure = { chipText: chipText, toggle: toggle, sameSet: sameSet, iconSpec: iconSpec, addToConnCount: addToConnCount };
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
  if (typeof document === "undefined") return;

  function tw(k, v) { return window.t ? window.t(k, v) : k; }
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
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function ic(n) { return typeof window.ic === "function" ? window.ic(n) : ""; }
  function infoBtn() { return window.JavisInfo ? window.JavisInfo.btn(tw("info.more")) : ""; }
  function infoBody(html) { return window.JavisInfo ? window.JavisInfo.body(html) : '<div class="info-body">' + html + "</div>"; }
  function chatBrain() { try { return (window.JavisSessions && window.JavisSessions.brain()) || "brain"; } catch (e) { return "brain"; } }
  function pageBrain() { try { return (window.currentBrainPath && window.currentBrainPath()) || chatBrain(); } catch (e) { return chatBrain(); } }
  function sid() { try { return (window.JavisSessions && window.JavisSessions.current()) || ""; } catch (e) { return ""; } }
  function narrow() { return !!(window.matchMedia && window.matchMedia("(max-width: 860px)").matches); }
  function api(url, body) {
    var opt = { credentials: "same-origin" };
    if (body) {
      var fd = new FormData();
      Object.keys(body).forEach(function (k) { fd.append(k, body[k] == null ? "" : body[k]); });
      opt.method = "POST"; opt.body = fd;
    }
    return fetch(url, opt).then(function (r) { return r.json().catch(function () { return { ok: false }; }); })
      .catch(function () { return { ok: false, error: tw("gh.err_net") }; });
  }
  var LOGO = '<svg class="cp-ic" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 .5a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.37-3.88-1.37-.52-1.33-1.28-1.69-1.28-1.69-1.05-.71.08-.7.08-.7 1.16.08 1.77 1.2 1.77 1.2 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.78 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.84 1.19 3.1 0 4.42-2.69 5.39-5.26 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .5z"/></svg>';
  var CHECK = '<svg class="cp-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>';
  var BRANCH = '<svg class="cp-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="6" cy="5" r="2.2"/><circle cx="6" cy="19" r="2.2"/><circle cx="18" cy="7" r="2.2"/><path d="M6 7.2v9.6M18 9.2c0 5-6 4-11 7.6"/></svg>';
  var CHEV = '<svg class="cp-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>';
  var BACK = '<svg class="cp-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>';
  var PLUS = '<svg class="cp-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>';

  // ============================================================
  // 1. Connections page card
  // ============================================================
  var cardHost = null;
  function cardHtml(st, local) {
    var head = '<div class="prov-head"><span class="conn-ico">' + LOGO + '</span><div class="prov-info"><div class="prov-name">GitHub' +
      infoBtn() + '</div><div class="prov-status j-clamp2">' + esc(st.connected ? tw("gh.connected_as", { login: st.login || "?" }) : tw("gh.not_connected")) +
      (st.connected && st.source === "backup" ? " · " + esc(tw("gh.uses_backup")) : "") +
      (st.connected && st.source === "app" ? " · " + esc(tw("gh.uses_app")) : "") + "</div>" + infoBody(esc(tw("gh.intro"))) + "</div></div>";
    var warn = st.connected && st.missing && st.missing.length
      ? '<div class="lv-note">' + esc(tw("gh.missing_scopes", { scopes: st.missing.join(", ") })) + "</div>" : "";
    if (st.connected && st.source === "app" && st.installs === 0) warn += '<div class="lv-note">' + esc(tw("gh.no_install")) + "</div>";
    var noGit = st.has_git === false ? '<div class="lv-note">' + esc(tw("gh.no_git")) + "</div>" : "";
    // The repo list opens in a popup (owner, 28/10/2026, same as the bot cards on the Chatbot page): a brain can hold many
    // repos, and listing them inline stretched the Connections page. The card keeps one compact row with the counts.
    var repos = "";
    if (st.connected) {
      var chats = local.reduce(function (n, r) { return n + (r.chats || 0); }, 0);
      repos = local.length
        ? '<button type="button" class="cb-st gh-more" data-gh-repos aria-haspopup="dialog"><span class="cb-st-chips">' +
          '<span class="cb-st-chip">' + esc(tw("gh.repos_n", { n: local.length })) + "</span>" +
          (chats ? '<span class="cb-st-chip">' + esc(tw("gh.local_chats", { n: chats })) + "</span>" : "") + "</span>" +
          '<span class="cb-st-more">' + esc(tw("gh.view")) + " " + ic("chevron-right") + "</span></button>"
        : '<div class="lv-meta">' + esc(tw("gh.local_none")) + "</div>";
    }
    var acts = '<div class="conn-accounts">' + (st.connected
      ? (st.source === "app" && st.install_url ? '<a class="conn-chip' + (st.installs === 0 ? " add" : "") + '" target="_blank" rel="noopener" href="' +
          esc(st.install_url) + '">' + esc(tw("gh.pick_repos")) + "</a>" : "") +
        '<button class="conn-chip" type="button" data-gh-open>' + esc(tw(st.source === "app" ? "gh.change_account" : "gh.change_token")) + "</button>" +
        '<button class="conn-chip" type="button" data-gh-off>' + esc(tw("gh.disconnect")) + "</button>"
      : '<button class="conn-chip add" type="button" data-gh-open>＋ ' + esc(tw("gh.connect")) + "</button>") + "</div>";
    return '<div class="prov-card conn-card gh-card">' + head + warn + noGit + repos + acts + "</div>";
  }
  async function loadCard() {
    if (!cardHost) return;
    var st = await api("/github/status");
    if (!st || st.ok === false) { cardHost.innerHTML = '<div class="lv-note">' + esc((st && st.error) || tw("gh.err_net")) + "</div>"; return; }
    var local = [];
    if (st.connected) {
      var l = await api("/github/local?brain=" + encodeURIComponent(pageBrain()));
      local = (l && l.items) || [];
    }
    cardHost.innerHTML = cardHtml(st, local);
    // A connected GitHub counts as a connection: in the heading, and the "nothing connected yet" line must not sit
    // under it.
    var total = addToConnCount("gh", st.connected ? 1 : 0);
    var empty = document.querySelector("#connList > .mp-empty");
    if (empty) empty.hidden = total > 0;
    var open = cardHost.querySelector("[data-gh-open]");
    if (open) open.onclick = function () { openForm(st); };
    var off = cardHost.querySelector("[data-gh-off]");
    if (off) off.onclick = async function () {
      if (!window.confirm(tw("gh.disconnect_q"))) return;
      await api("/github/disconnect", {});
      loadCard();
    };
    var more = cardHost.querySelector("[data-gh-repos]");
    if (more) more.onclick = function () { openRepos(local); };
  }
  function reposHtml(local) {
    return local.map(function (r) {
      return '<div class="gh-local-row"><span class="gh-local-name">' + esc(r.full_name) + "</span>" +
        '<span class="gh-local-meta">' + esc(tw("gh.local_chats", { n: r.chats || 0 })) + "</span>" +
        '<label class="gh-auto"><input type="checkbox" data-gh-auto="' + esc(r.full_name) + '"' + (r.auto_merge !== false ? " checked" : "") + "> " +
        esc(tw("gh.auto_merge")) + "</label>" +
        '<button class="s-btn-ghost" type="button" data-gh-checks="' + esc(r.full_name) + '">' + esc(tw("gh.checks")) + "</button>" +
        '<button class="s-btn-ghost" type="button" data-gh-metrics="' + esc(r.full_name) + '">' + esc(tw("gh.metrics")) + "</button>" +
        '<button class="s-btn-ghost" type="button" data-gh-remove="' + esc(r.full_name) + '">' + esc(tw("gh.remove_brain")) + "</button></div>";
    }).join("");
  }
  // The repos of this brain, one row each with its switches. Checks and Numbers open in the same dialog and come back here.
  function openRepos(local) {
    var M = window.JavisConnModal;
    if (!M) return;
    var back = function () { openRepos(local); };
    var m = M.open(M.head(esc(tw("gh.local_head", { n: local.length })) + infoBtn()) + '<div class="conn-form gh-local">' +
      infoBody(esc(tw("gh.local_how"))) + reposHtml(local) +
      '<div class="lv-msg" role="status" data-gh-msg></div></div>', 720);
    m.querySelectorAll("[data-gh-auto]").forEach(function (b) {
      b.onchange = function () {
        var name = b.getAttribute("data-gh-auto");
        local.forEach(function (r) { if (r.full_name === name) r.auto_merge = b.checked; });
        api("/github/local/automerge", { brain: pageBrain(), full_name: name, on: b.checked ? "1" : "0" });
      };
    });
    m.querySelectorAll("[data-gh-metrics]").forEach(function (b) {
      b.onclick = function () { openMetrics(b.getAttribute("data-gh-metrics"), back); };
    });
    m.querySelectorAll("[data-gh-checks]").forEach(function (b) {
      b.onclick = function () { openChecks(b.getAttribute("data-gh-checks"), back); };
    });
    m.querySelectorAll("[data-gh-remove]").forEach(function (b) {
      b.onclick = async function () {
        var name = b.getAttribute("data-gh-remove");
        if (!window.confirm(tw("gh.remove_q", { name: name }))) return;
        var msg = m.querySelector("[data-gh-msg]");
        b.disabled = true;
        var r = await api("/github/local/remove", { brain: pageBrain(), full_name: name });
        b.disabled = false;
        if (!r || r.ok === false) { if (msg) msg.textContent = (r && r.error) || tw("gh.err_net"); return; }
        local = local.filter(function (x) { return x.full_name !== name; });
        loadCard();
        if (local.length) openRepos(local); else M.close();
      };
    });
  }
  // Local check commands of one repo (spec 7.2): suggested from its CI, editable, one command per line.
  async function openChecks(name, back) {
    var M = window.JavisConnModal;
    if (!M) return;
    var d = await api("/github/local/checks?brain=" + encodeURIComponent(pageBrain()) + "&full_name=" + encodeURIComponent(name));
    if (!d || d.ok === false) { window.alert((d && d.error) || tw("gh.err_net")); return; }
    var text = (d.checks || []).map(function (c) { return String(c.run).split("\n").join(" \\\n"); }).join("\n");
    var html = M.head(esc(tw("gh.checks_head", { name: name }))) + '<div class="conn-form gh-form">' +
      '<div class="si-field"><label>' + esc(tw("gh.checks_label")) + infoBtn() + "</label>" + infoBody(esc(tw("gh.checks_how"))) +
      '<textarea class="js-input gh-checks-box" data-f="cmds" rows="8" spellcheck="false"></textarea></div>' +
      '<div class="lv-meta">' + esc(d.custom ? tw("gh.checks_custom") : tw("gh.checks_suggested")) + "</div>" +
      '<div class="lv-form-act"><button class="s-btn" type="button" data-f="save">' + esc(tw("gh.save")) + "</button>" +
      '<button class="s-btn-ghost" type="button" data-f="reset">' + esc(tw("gh.checks_reset")) + "</button>" +
      '<button class="s-btn-ghost" type="button" data-f="cancel">' + esc(tw("gh.cancel")) + "</button>" +
      '<span class="lv-msg" role="status"></span></div></div>';
    var m = M.open(html, 640);
    var form = m.querySelector(".gh-form"), box = form.querySelector('[data-f="cmds"]'), msg = form.querySelector(".lv-msg");
    box.value = text;
    async function send(body) {
      msg.textContent = "";
      var r = await api("/github/local/checks", Object.assign({ brain: pageBrain(), full_name: name }, body));
      if (!r || r.ok === false) { msg.textContent = (r && r.error) || tw("gh.err_net"); return; }
      if (back) back(); else M.close();
    }
    form.querySelector('[data-f="save"]').onclick = function () { send({ commands: box.value }); };
    form.querySelector('[data-f="reset"]').onclick = function () { send({ reset: "1" }); };
    form.querySelector('[data-f="cancel"]').onclick = function () { if (back) back(); else M.close(); };
  }
  // Numbers per engine and model for one repo (spec 13.2): pick a model with data, not with a hunch.
  async function openMetrics(name, back) {
    var M = window.JavisConnModal;
    if (!M) return;
    var d = await api("/github/local/metrics?full_name=" + encodeURIComponent(name));
    var rows = (d && d.rows) || [];
    var body = rows.length ? '<div class="gh-table-wrap"><table class="gh-table"><thead><tr><th>' + esc(tw("gh.m_model")) + "</th><th>" +
      esc(tw("gh.m_jobs")) + "</th><th>" + esc(tw("gh.m_first")) + "</th><th>" + esc(tw("gh.m_rounds")) + "</th><th>" + esc(tw("gh.m_findings")) +
      "</th><th>" + esc(tw("gh.m_minutes")) + "</th></tr></thead><tbody>" + rows.map(function (r) {
        return "<tr><td>" + esc(r.engine + (r.model ? " · " + r.model : "")) + "</td><td>" + r.jobs + "</td><td>" + r.first_push_green_pct +
          "%</td><td>" + r.avg_fix_rounds + "</td><td>" + r.review_findings + "</td><td>" + r.avg_minutes + "</td></tr>";
      }).join("") + "</tbody></table></div>" : '<div class="mp-empty">' + esc(tw("gh.m_none")) + "</div>";
    var m = M.open(M.head(esc(tw("gh.metrics_head", { name: name }))) + '<div class="conn-form">' + infoBody(esc(tw("gh.metrics_how"))) + body +
      (back ? '<div class="lv-form-act"><button class="s-btn-ghost" type="button" data-f="back">' + esc(tw("gh.back")) + "</button></div>" : "") +
      "</div>", 680);
    var bk = m.querySelector('[data-f="back"]');
    if (bk) bk.onclick = back;
  }
  // The connect dialog (0.430.0): "Sign in with GitHub" first (the device flow of the Javis OS GitHub App, no token to
  // make or copy), a pasted token below it for whoever prefers that, and the brain-backup token when there is one.
  function openForm(st) {
    var M = window.JavisConnModal;
    if (!M) return;
    var html = M.head(esc(tw("gh.dialog_head"))) + '<div class="conn-form gh-form">' +
      '<div class="gh-signin"><button class="s-btn gh-signin-btn" type="button" data-f="signin">' + LOGO + "<span>" +
      esc(tw("gh.signin")) + "</span></button>" + infoBtn() + "</div>" + infoBody(esc(tw("gh.signin_how"))) +
      '<div class="lv-meta">' + esc(tw("gh.signin_sub")) + "</div>" +
      '<div class="gh-or"><span>' + esc(tw("gh.or_token")) + "</span></div>" +
      '<div class="si-field"><label>' + esc(tw("gh.token")) + infoBtn() + "</label>" + infoBody(esc(tw("gh.token_how"))) +
      '<input class="js-input" data-f="token" type="password" autocomplete="off" spellcheck="false" placeholder="' + esc(tw("gh.token_ph")) + '"></div>' +
      '<div class="lv-form-act"><button class="s-btn-ghost" type="button" data-f="go">' + esc(tw("gh.connect")) + "</button>" +
      (st && st.backup_token ? '<button class="s-btn-ghost" type="button" data-f="backup">' + esc(tw("gh.use_backup")) + "</button>" : "") +
      '<button class="s-btn-ghost" type="button" data-f="cancel">' + esc(tw("gh.cancel")) + "</button>" +
      '<span class="lv-msg" role="status"></span></div></div>';
    var m = M.open(html, 560);
    var form = m.querySelector(".gh-form"), msg = form.querySelector(".lv-msg");
    async function go(body) {
      msg.textContent = tw("gh.checking");
      form.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
      var r = await api("/github/connect", body);
      form.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
      form.querySelector('[data-f="token"]').value = "";   // the token has done its job; never keep it in the page
      if (!r || r.ok === false) { msg.textContent = (r && r.error) || tw("gh.err_net"); return; }
      M.close();
      loadCard();
    }
    form.querySelector('[data-f="signin"]').onclick = function () { signIn(); };
    form.querySelector('[data-f="go"]').onclick = function () { go({ token: form.querySelector('[data-f="token"]').value.trim() }); };
    var bk = form.querySelector('[data-f="backup"]');
    if (bk) bk.onclick = function () { go({ use_backup: "1" }); };
    form.querySelector('[data-f="cancel"]').onclick = function () { M.close(); };
  }

  // Device flow, step by step in the same dialog: get a code, show it with "Open GitHub" and "Copy", poll until the
  // person presses Authorize, then offer "Pick repos for Javis" when the app is not installed anywhere yet.
  async function signIn() {
    var M = window.JavisConnModal;
    if (!M) return;
    var m = M.open(M.head(esc(tw("gh.dialog_head"))) + '<div class="conn-form gh-form"><div class="lv-meta">' +
      esc(tw("gh.loading")) + "</div></div>", 560);
    var d = await api("/github/oauth/start", {});
    if (!d || d.ok === false) {
      m.querySelector(".gh-form").innerHTML = '<div class="lv-note">' + esc((d && d.error) || tw("gh.err_net")) + "</div>" +
        '<div class="lv-form-act"><button class="s-btn" type="button" data-f="retry">' + esc(tw("gh.signin")) + "</button></div>";
      m.querySelector('[data-f="retry"]').onclick = function () { signIn(); };
      return;
    }
    var url = d.verification_uri || "https://github.com/login/device";
    m = M.open(M.head(esc(tw("gh.dialog_head"))) + '<div class="conn-form gh-form gh-device">' +
      '<div class="lv-meta">' + esc(tw("gh.code_how")) + "</div>" +
      '<div class="gh-code" data-f="code" aria-label="' + esc(tw("gh.code_label")) + '">' + esc(d.user_code) + "</div>" +
      '<div class="lv-form-act"><a class="s-btn" data-f="open" target="_blank" rel="noopener" href="' + esc(url) + '">' + esc(tw("gh.open_github")) + "</a>" +
      '<button class="s-btn-ghost" type="button" data-f="copy">' + esc(tw("gh.copy")) + "</button>" +
      '<button class="s-btn-ghost" type="button" data-f="cancel">' + esc(tw("gh.cancel")) + "</button></div>" +
      '<div class="lv-msg" role="status" data-f="msg">' + esc(tw("gh.waiting")) + "</div></div>", 560);
    var form = m.querySelector(".gh-form"), msg = form.querySelector('[data-f="msg"]');
    function copy() {
      try {
        navigator.clipboard.writeText(d.user_code).then(function () { msg.textContent = tw("gh.copied"); }, function () {});
      } catch (e) {}
    }
    copy();
    // The code shows first and the link is a real tap, so no popup blocker gets in the way, and the tap copies the
    // code again (the first copy can fail when the page had no focus).
    form.querySelector('[data-f="open"]').addEventListener("click", copy);
    form.querySelector('[data-f="copy"]').onclick = copy;
    var alive = true;
    function open() { return alive && form.isConnected && m.closest(".mp-overlay.open"); }
    form.querySelector('[data-f="cancel"]').onclick = function () { alive = false; api("/github/oauth/cancel", {}); M.close(); };
    var wait = Math.max(1, d.interval || 5) * 1000;
    while (true) {
      await new Promise(function (res) { setTimeout(res, wait); });
      if (!open()) { if (alive) api("/github/oauth/cancel", {}); return; }
      var r = await api("/github/oauth/poll", {});
      if (!open()) return;
      if (r && r.status === "pending") continue;
      if (!r || r.ok === false || r.status === "error") {
        msg.textContent = (r && r.error) || tw("gh.err_net");
        form.querySelector('[data-f="open"]').remove();
        form.querySelector('[data-f="copy"]').textContent = tw("gh.signin");
        form.querySelector('[data-f="copy"]').onclick = function () { signIn(); };
        return;
      }
      loadCard();
      if (r.installs === 0) { pickRepos(r); return; }
      M.close();
      return;
    }
  }
  // Signed in but the app is on no account yet: the last step, picking repos on GitHub.
  function pickRepos(st) {
    var M = window.JavisConnModal;
    if (!M) return;
    var m = M.open(M.head(esc(tw("gh.signed_in", { login: st.login || "?" }))) + '<div class="conn-form gh-form">' +
      '<div class="lv-meta">' + esc(tw("gh.pick_repos_how")) + "</div>" +
      '<div class="lv-form-act"><a class="s-btn" target="_blank" rel="noopener" href="' + esc(st.install_url || "") + '">' + esc(tw("gh.pick_repos")) + "</a>" +
      '<button class="s-btn-ghost" type="button" data-f="done">' + esc(tw("gh.done")) + "</button></div></div>", 560);
    m.querySelector('[data-f="done"]').onclick = function () { M.close(); loadCard(); };
  }
  function mount(el) { cardHost = el || null; if (cardHost) loadCard(); }

  // ============================================================
  // 2 and 3. Repos of the open conversation: + menu panel and chip
  // ============================================================
  var attached = [], held = null, heldBrain = "", heldBase = {}, seq = 0;
  function names() { return attached.map(function (r) { return r.full_name; }); }
  function announce() {
    try { window.dispatchEvent(new CustomEvent("javis:github-repos-changed", { detail: { sid: sid(), repos: attached } })); } catch (e) {}
  }
  function renderChip() {
    var host = document.getElementById("cpChips");
    if (!host) return;
    var chip = document.getElementById("ghChip");
    var list = held ? held : names();
    if (!list.length) { if (chip) chip.remove(); return; }
    if (!chip) {
      chip = document.createElement("button");
      chip.type = "button"; chip.id = "ghChip"; chip.className = "cp-pin gh-chip";
      chip.addEventListener("click", function (e) { e.stopPropagation(); if (window.JavisComposerMenu) window.JavisComposerMenu.openItem("github"); });
    }
    var after = document.getElementById("pinChip") || document.getElementById("limitBtn");
    if (chip.parentElement !== host || chip.previousElementSibling !== after) host.insertBefore(chip, after ? after.nextSibling : null);
    var base = chipBase();
    chip.title = list.join("\n") + (base ? "\n" + tw("gh.chip_branch", { branch: base }) : "");
    chip.setAttribute("aria-label", tw("gh.chip_label", { names: list.join(", ") }) + (base ? ", " + tw("gh.chip_branch", { branch: base }) : ""));
    chip.innerHTML = LOGO + "<span>" + esc(chipText(list, narrow() ? 10 : 18)) + "</span>" +
      (base ? '<span class="gh-chip-br">' + BRANCH + esc(base) + "</span>" : "") + (chipIcon ? iconHtml(chipIcon) : "");
    var st = chip.querySelector(".gh-st");
    if (st) st.addEventListener("click", function (e) { e.stopPropagation(); openDetail(sid()); });
  }
  var chipIcon = null;
  // A base branch other than the default rides on the chip, so the chat shows where its work will land.
  function chipBase() {
    var r = chatRepos();
    if (r.length !== 1) return "";
    if (held) return r[0].base_branch;
    var a = attached[0] || {};
    return a.base_branch && a.base_branch !== a.default_branch ? a.base_branch : "";
  }
  function apply(d) {
    attached = (d && d.repos) || [];
    chipIcon = (d && d.icon && d.icon.state) ? d.icon : null;
    renderChip();
    announce();
  }
  function refresh() {
    var id = sid(), n = ++seq;
    if (!id) { if (held && heldBrain !== chatBrain()) { held = null; } attached = []; renderChip(); return Promise.resolve(); }
    held = null;
    return api("/github/session/" + encodeURIComponent(id) + "?brain=" + encodeURIComponent(chatBrain())).then(function (d) {
      if (n === seq && id === sid() && d && d.ok !== false) apply(d);
    });
  }
  function setRepos(list) {
    var id = sid();
    if (!id) {
      held = list.length ? list.slice() : null;
      heldBrain = chatBrain();
      Object.keys(heldBase).forEach(function (fn) { if (list.indexOf(fn) < 0) delete heldBase[fn]; });
      renderChip();
      return Promise.resolve("");
    }
    var n = ++seq;
    return api("/github/session/" + encodeURIComponent(id) + "/repos", { brain: chatBrain(), repos: list.join(",") }).then(function (d) {
      if (!d || d.ok === false) return (d && d.error) || tw("gh.err_net");
      if (n === seq && id === sid()) apply(d);
      return "";
    });
  }
  // app.js: the first message just minted a session id. Attach the repos held on the empty chat before the turn runs.
  function claimPending(newSid) {
    if (!newSid || !held) return null;
    var list = held, bases = heldBase, sameBrain = heldBrain === chatBrain();
    held = null; heldBrain = ""; heldBase = {};
    if (!sameBrain) { renderChip(); return null; }
    return api("/github/session/" + encodeURIComponent(newSid) + "/repos", { brain: chatBrain(), repos: list.join(",") }).then(function (d) {
      if (d && d.ok !== false) {
        // The branch picked on the empty chat applies before the first turn runs.
        var picks = Object.keys(bases).filter(function (fn) { return list.indexOf(fn) >= 0; });
        return picks.reduce(function (p, fn) {
          return p.then(function (last) {
            return api("/github/session/" + encodeURIComponent(newSid) + "/base", { brain: chatBrain(), full_name: fn, branch: bases[fn] })
              .then(function (r) { return r && r.ok !== false ? r : last; });
          });
        }, Promise.resolve(d)).then(apply);
      }
      apply(null);
      if (window.JavisAttach) window.JavisAttach.note((d && d.error) || tw("gh.err_net"));
    });
  }

  // The GitHub panel of the + menu, and of the repo chip (owner, 28/10/2026, after Claude Code's own picker): a short
  // menu "Change repo / Change branch" once repos are attached, a repo list split into "Selected" and "Repos", and a
  // branch list per repo. Three views in the same box; each one has a back row to the menu.
  function panel(box, menuApi) {
    box.innerHTML = '<div class="cp-empty">' + esc(tw("gh.loading")) + "</div>";
    // The + menu stops clicks from bubbling to the page, so the shared (i) handler of info-tip.js never sees them.
    box.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("button.info-i") : null;
      var k = b && b.parentElement && b.parentElement.nextElementSibling;
      if (!k || !k.classList.contains("info-body")) return;
      k.hidden = !k.hidden;
      b.setAttribute("aria-expanded", k.hidden ? "false" : "true");
      b.classList.toggle("on", !k.hidden);
    });
    api("/github/status").then(function (st) {
      if (!st || !st.connected) {
        box.innerHTML = '<div class="cp-empty">' + esc(tw("gh.panel_not_connected")) + "</div>" +
          '<button type="button" class="cp-mi" data-go-connect="1">' + LOGO + '<span class="cp-mi-lbl">' + esc(tw("gh.open_connections")) + "</span></button>";
        box.querySelector("[data-go-connect]").onclick = function () { menuApi.close(); goConnections(); };
        return;
      }
      (held || names().length) ? homeView(box, menuApi) : reposView(box, menuApi, false);
    });
  }
  function goConnections() { try { window.Alpine.store("nav").go("mcp"); } catch (e) { location.hash = "#mcp"; } }
  // Inside a sub view our own back row leads back to the GitHub menu; the + menu's back row above it would only
  // repeat "Repo GitHub", so it hides there and comes back on the menu view.
  function outerBack(box, show) {
    var host = box.parentElement;
    if (!host) return;
    var b = host.querySelector(":scope > [data-back]"), sep = b && b.nextElementSibling;
    if (b) b.hidden = !show;
    if (sep && sep.classList.contains("cp-sep")) sep.hidden = !show;
  }
  function backRow(label) {
    return '<button type="button" class="cp-mi cp-back gh-back" data-gh-back="1">' + BACK + "<span>" + esc(label) + "</span></button>";
  }
  // Repos of the chat with their base branch: attached ones from the server, or the ones held on an empty chat.
  function chatRepos() {
    if (held) return held.map(function (n) { return { full_name: n, base_branch: heldBase[n] || "" }; });
    return attached.map(function (r) { return { full_name: r.full_name, base_branch: r.base_branch || r.default_branch || "" }; });
  }
  function homeView(box, menuApi) {
    outerBack(box, true);
    var repos = chatRepos();
    var bases = repos.map(function (r) { return r.base_branch; }).filter(Boolean);
    var branchHint = repos.length === 1 ? (bases[0] || tw("gh.branch_default")) : tw("gh.repos_n", { n: repos.length });
    box.innerHTML =
      '<button type="button" class="cp-mi" data-gh-go="repos">' + LOGO + '<span class="cp-mi-lbl">' + esc(tw("gh.change_repo")) + "</span>" +
        '<span class="cp-mi-hint">' + esc(chipText(repos.map(function (r) { return r.full_name; }), 18)) + "</span>" + CHEV + "</button>" +
      '<button type="button" class="cp-mi" data-gh-go="branch">' + BRANCH + '<span class="cp-mi-lbl">' + esc(tw("gh.change_branch")) + "</span>" +
        '<span class="cp-mi-hint">' + esc(branchHint) + "</span>" + CHEV + "</button>" +
      (chipIcon && sid() ? '<button type="button" class="cp-mi" data-gh-go="status">' + iconHtml(chipIcon) +
        '<span class="cp-mi-lbl">' + esc(tw("gh.view_status")) + "</span>" + CHEV + "</button>" : "");
    box.querySelector('[data-gh-go="repos"]').onclick = function () { reposView(box, menuApi, true); };
    box.querySelector('[data-gh-go="branch"]').onclick = function () {
      var list = chatRepos();
      list.length === 1 ? branchView(box, menuApi, list[0]) : branchReposView(box, menuApi);
    };
    var stb = box.querySelector('[data-gh-go="status"]');
    if (stb) stb.onclick = function () { menuApi.close(); openDetail(sid()); };
    var first = box.querySelector(".cp-mi"); if (first) first.focus();
  }
  // One repo row: the owner small above, the name large, a check on the right when chosen.
  function repoRow(r, i, on) {
    var parts = String(r.full_name).split("/");
    var tag = r.cloned ? tw("gh.cloned") : (r.private ? tw("gh.private") : "");
    return '<button type="button" class="cp-mi gh-repo" role="option" aria-selected="' + on + '" data-gh-i="' + i + '">' +
      '<span class="gh-two"><span class="gh-owner">' + esc(parts[0]) + (tag ? " · " + esc(tag) : "") + "</span>" +
      '<span class="gh-name">' + esc(parts[1] || r.full_name) + "</span></span>" +
      (on ? '<span class="gh-tick">' + CHECK + "</span>" : "") + "</button>";
  }
  // Ticking a repo attaches it at once and unticking removes it (owner, 01/11/2026): no "Attach" button at the foot of
  // a long list that had to be scrolled to. Changes go to the server one at a time; ticks made while one is in flight
  // ride on the next request, so the server always ends on the last state the person sees.
  function reposView(box, menuApi, canBack) {
    outerBack(box, !canBack);
    var chosen = held ? held.slice() : names(), sent = chosen.slice(), busy = false, items = [], timer = 0, n = 0;
    box.innerHTML = (canBack ? backRow(tw("gh.menu")) + '<div class="cp-sep"></div>' : "") +
      '<input type="search" class="cp-search" placeholder="' + esc(tw("gh.search_ph")) + '" aria-label="' + esc(tw("gh.search_ph")) + '">' +
      '<div class="cp-results gh-results" role="listbox" aria-multiselectable="true"></div>' +
      '<div class="gh-foot"><div class="cp-pin-err" role="status"></div>' +
      '<button type="button" class="cp-mi gh-more-conn" data-gh-conn="1">' + PLUS + '<span class="cp-mi-lbl">' + esc(tw("gh.connect_more")) + "</span></button></div>";
    var input = box.querySelector(".cp-search"), out = box.querySelector(".cp-results"), err = box.querySelector(".cp-pin-err");
    var back = box.querySelector("[data-gh-back]");
    if (back) back.onclick = function () { homeView(box, menuApi); };
    box.querySelector("[data-gh-conn]").onclick = function () { menuApi.close(); goConnections(); };
    function draw() {
      var sel = [], rest = [];
      items.forEach(function (r, i) { (chosen.indexOf(r.full_name) >= 0 ? sel : rest).push(repoRow(r, i, chosen.indexOf(r.full_name) >= 0)); });
      out.innerHTML = (sel.length ? '<div class="gh-sec">' + esc(tw("gh.sec_selected")) + '</div><div class="gh-group">' + sel.join("") + "</div>" : "") +
        (rest.length ? '<div class="gh-sec">' + esc(tw("gh.sec_repos")) + '</div><div class="gh-group">' + rest.join("") + "</div>" : "") +
        (!items.length ? '<div class="cp-empty">' + esc(tw("gh.none_found")) + "</div>" : "");
    }
    function sync() {
      if (busy) return;
      if (sameSet(chosen, sent)) return;
      var list = chosen.slice(), adds = list.some(function (x) { return sent.indexOf(x) < 0; });
      busy = true;
      err.textContent = adds ? tw("gh.cloning") : "";
      setRepos(list).then(function (msg) {
        busy = false;
        if (msg) { chosen = sent.slice(); err.textContent = msg; draw(); return; }
        sent = list;
        err.textContent = "";
        sync();
      });
    }
    function load() {
      var q = input.value.trim(), k = ++n;
      api("/github/repos?brain=" + encodeURIComponent(chatBrain()) + "&q=" + encodeURIComponent(q)).then(function (d) {
        if (k !== n) return;
        if (!d || d.ok === false) { err.textContent = (d && d.error) || tw("gh.err_net"); items = []; draw(); return; }
        items = d.items || [];
        // Attached repos stay listed (in "Selected") even when the search hides them, so they can be unticked.
        chosen.forEach(function (name) {
          if (!items.some(function (x) { return x.full_name === name; }) && !q) items.unshift({ full_name: name, cloned: true });
        });
        draw();
      });
    }
    out.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("[data-gh-i]") : null;
      if (!b) return;
      var r = items[+b.getAttribute("data-gh-i")];
      if (r) { chosen = toggle(chosen, r.full_name); draw(); sync(); }
    });
    input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(load, 200); });
    input.focus();
    load();
  }
  // Several repos: pick the repo first, then its branch.
  function branchReposView(box, menuApi) {
    outerBack(box, false);
    var repos = chatRepos();
    box.innerHTML = backRow(tw("gh.menu")) + '<div class="cp-sep"></div><div class="gh-sec">' + esc(tw("gh.branch_which")) + '</div><div class="gh-group">' +
      repos.map(function (r, i) {
        var parts = String(r.full_name).split("/");
        return '<button type="button" class="cp-mi gh-repo" data-gh-r="' + i + '"><span class="gh-two"><span class="gh-owner">' + esc(parts[0]) + "</span>" +
          '<span class="gh-name">' + esc(parts[1] || r.full_name) + "</span></span>" +
          '<span class="cp-mi-hint">' + BRANCH + " " + esc(r.base_branch || tw("gh.branch_default")) + "</span>" + CHEV + "</button>";
      }).join("") + "</div>";
    box.querySelector("[data-gh-back]").onclick = function () { homeView(box, menuApi); };
    box.querySelectorAll("[data-gh-r]").forEach(function (b) {
      b.onclick = function () { branchView(box, menuApi, repos[+b.getAttribute("data-gh-r")], true); };
    });
  }
  function branchView(box, menuApi, repo, fromRepos) {
    outerBack(box, false);
    var all = [], def = "", cur = repo.base_branch || "";
    box.innerHTML = backRow(fromRepos ? tw("gh.change_branch") : tw("gh.menu")) + '<div class="cp-sep"></div>' +
      '<div class="gh-sec">' + esc(tw("gh.branch_of", { name: repo.full_name })) + infoBtn() + "</div>" + infoBody(esc(tw("gh.branch_how"))) +
      '<input type="search" class="cp-search" placeholder="' + esc(tw("gh.branch_search_ph")) + '" aria-label="' + esc(tw("gh.branch_search_ph")) + '">' +
      '<div class="cp-results gh-results"><div class="cp-empty">' + esc(tw("gh.loading")) + "</div></div>" +
      '<div class="cp-pin-err" role="status"></div>';
    var input = box.querySelector(".cp-search"), out = box.querySelector(".cp-results"), err = box.querySelector(".cp-pin-err");
    box.querySelector("[data-gh-back]").onclick = function () { fromRepos ? branchReposView(box, menuApi) : homeView(box, menuApi); };
    function draw() {
      var q = input.value.trim().toLowerCase();
      var list = all.filter(function (b) { return !q || b.toLowerCase().indexOf(q) >= 0; });
      out.innerHTML = list.length ? '<div class="gh-group">' + list.map(function (b) {
        var on = b === (cur || def);
        return '<button type="button" class="cp-mi gh-branch" role="option" aria-selected="' + on + '" data-gh-b="' + esc(b) + '">' + BRANCH +
          '<span class="cp-mi-lbl">' + esc(b) + "</span>" + (b === def ? '<span class="cp-mi-hint">' + esc(tw("gh.branch_default")) + "</span>" : "") +
          (on ? '<span class="gh-tick">' + CHECK + "</span>" : "") + "</button>";
      }).join("") + "</div>" : '<div class="cp-empty">' + esc(tw("gh.branch_none")) + "</div>";
    }
    out.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("[data-gh-b]") : null;
      if (!b) return;
      var name = b.getAttribute("data-gh-b");
      if (name === (cur || def)) return;
      err.textContent = tw("gh.branch_switching");
      setBase(repo.full_name, name === def ? "" : name, name).then(function (msg) {
        if (msg) { err.textContent = msg; return; }
        err.textContent = "";
        homeView(box, menuApi);
      });
    });
    input.addEventListener("input", draw);
    api("/github/branches?full_name=" + encodeURIComponent(repo.full_name)).then(function (d) {
      if (!d || d.ok === false) { out.innerHTML = ""; err.textContent = (d && d.error) || tw("gh.err_net"); return; }
      all = d.items || []; def = d.default || "";
      draw();
      input.focus();
    });
  }
  // Save the chat's base branch for one repo. An empty chat keeps it with the held repos until the first message.
  function setBase(fullName, heldValue, branch) {
    var id = sid();
    if (!id) {
      if (heldValue) heldBase[fullName] = heldValue; else delete heldBase[fullName];
      renderChip();
      return Promise.resolve("");
    }
    var n = ++seq;
    return api("/github/session/" + encodeURIComponent(id) + "/base", { brain: chatBrain(), full_name: fullName, branch: branch }).then(function (d) {
      if (!d || d.ok === false) return (d && d.error) || tw("gh.err_net");
      if (n === seq && id === sid()) apply(Object.assign({ icon: chipIcon }, d));
      return "";
    });
  }
  // ============================================================
  // 4. Status icons in the chat list, and the detail panel (spec 12)
  // ============================================================
  var SVG = {
    working: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="8" r="2.5"/><path d="M6 8.5v7M18 10.5c0 4-6 3.5-10 6"/></svg>',
    ready: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><path d="M6 8.5v7"/><path d="M13 13l3 3 6-6"/></svg>',
    merged: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="14" r="2.5"/><path d="M6 8.5v7M6 8.5c0 4 5 5.5 9.5 5.5"/></svg>',
    broken: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg>'
  };
  function iconHtml(ic) {
    var s = iconSpec(ic);
    if (!s) return "";
    var title = tw(s.key) + (s.subKey ? " · " + tw(s.subKey) : "");
    return '<span class="' + s.cls + '" role="button" tabindex="0" title="' + esc(title) + '" aria-label="' + esc(title) + '">' +
      SVG[ic.state] + (s.count ? "<b>" + s.count + "</b>" : "") + "</span>";
  }
  var decoSeq = 0, lastList = null;
  function decorate(listEl) {
    lastList = listEl || lastList;
    if (!lastList) return;
    var rows = Array.prototype.slice.call(lastList.querySelectorAll(".cside-item[data-sid]"));
    if (!rows.length) return;
    var n = ++decoSeq, sids = rows.map(function (r) { return r.getAttribute("data-sid"); });
    api("/github/icons?sids=" + encodeURIComponent(sids.join(","))).then(function (d) {
      if (n !== decoSeq || !d || d.ok === false) return;
      var icons = d.icons || {};
      rows.forEach(function (row) {
        var old = row.querySelector(".gh-st");
        if (old) old.remove();
        var html = iconHtml(icons[row.getAttribute("data-sid")]);
        row.classList.toggle("has-gh", !!html);
        if (!html) return;
        var tmp = document.createElement("div");
        tmp.innerHTML = html;
        var el = tmp.firstChild;
        el.addEventListener("click", function (e) { e.stopPropagation(); openDetail(row.getAttribute("data-sid")); });
        el.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); openDetail(row.getAttribute("data-sid")); } });
        row.appendChild(el);
      });
    });
  }
  var CI_KEY = { none: "gh.ci_none", pending: "gh.ci_pending", running: "gh.ci_running", green: "gh.ci_green", red: "gh.ci_red",
    no_ci: "gh.ci_no_ci", cancelled: "gh.ci_cancelled" };
  var INTEG_KEY = { no_pr: "gh.in_no_pr", pr_open: "gh.in_pr_open", ready: "gh.in_ready", merged: "gh.in_merged",
    conflict: "gh.in_conflict", merge_failed: "gh.in_merge_failed" };
  function closeDetail() { var m = document.getElementById("ghDetail"); if (m) m.remove(); }
  function detailHtml(d) {
    var work = d.work || [];
    var rows = work.length ? work.map(function (r) {
      var checks = (r.checks_summary || []).map(function (c) {
        return '<li class="gh-chk gh-chk-' + esc(c.conclusion || "") + '">' + (c.url ? '<a href="' + esc(c.url) + '" target="_blank" rel="noopener">' + esc(c.name) + "</a>" : esc(c.name)) +
          " · " + esc(c.conclusion || "") + "</li>";
      }).join("");
      var canMerge = (r.integ === "ready") && (r.ci === "green" || r.ci === "no_ci");
      return '<div class="gh-row" data-repo="' + esc(r.full_name) + '"><div class="gh-row-head"><b>' + esc(r.full_name) + "</b>" +
        (r.branch ? ' <code>' + esc(r.branch) + "</code>" : "") + "</div>" +
        '<div class="gh-row-state">' + esc(tw(CI_KEY[r.ci] || "gh.ci_none")) + " · " + esc(tw(INTEG_KEY[r.integ] || "gh.in_no_pr")) +
        (r.post_merge === "red" ? " · " + esc(tw("gh.st_post_red")) : "") + (r.fix_rounds ? " · " + esc(tw("gh.rounds", { n: r.fix_rounds })) : "") + "</div>" +
        (r.stuck_reason ? '<div class="lv-note">' + esc(r.stuck_reason) + "</div>" : "") +
        ((r.merge_block || []).length ? '<div class="lv-note">' + esc(tw("gh.needs_person")) + " " + r.merge_block.map(function (x) { return esc(x.path + " (" + x.kind + ")"); }).join(", ") + "</div>" : "") +
        (checks ? '<ul class="gh-checks">' + checks + "</ul>" : "") +
        '<div class="lv-form-act">' + (r.pr_url ? '<a class="s-btn-ghost" href="' + esc(r.pr_url) + '" target="_blank" rel="noopener">' + esc(tw("gh.open_pr", { n: r.pr_number })) + "</a>" : "") +
        (canMerge ? '<button class="s-btn" type="button" data-merge="' + esc(r.full_name) + '">' + esc(tw("gh.merge")) + "</button>" : "") +
        '<span class="lv-msg" role="status"></span></div></div>';
    }).join("") : '<div class="mp-empty">' + esc(tw("gh.no_work")) + "</div>";
    var queue = (d.queue || []).length ? '<div class="gh-queue"><div class="gh-local-head">' + esc(tw("gh.queue_head")) + "</div>" +
      d.queue.map(function (q) { return '<div class="gh-local-row"><span class="gh-local-meta">' + esc(q.text) + '</span><button class="s-btn-ghost" type="button" data-unqueue="' + q.id + '">' + esc(tw("gh.queue_cancel")) + "</button></div>"; }).join("") + "</div>" : "";
    return rows + queue;
  }
  function openDetail(id) {
    if (!id) return;
    closeDetail();
    var m = document.createElement("div");
    m.id = "ghDetail"; m.className = "mp-overlay open";
    m.innerHTML = '<div class="mp-box gh-detail" style="max-width:640px" role="dialog" aria-modal="true"><div class="mp-head"><div class="mp-title">' +
      esc(tw("gh.detail_head")) + '</div><button class="mp-x" type="button" data-x="1" aria-label="' + esc(tw("gh.cancel")) + '">×</button></div>' +
      '<div class="gh-detail-body"><div class="mp-empty">' + esc(tw("gh.loading")) + "</div></div></div>";
    document.body.appendChild(m);
    m.addEventListener("click", function (e) { if (e.target === m || (e.target.closest && e.target.closest("[data-x]"))) closeDetail(); });
    var body = m.querySelector(".gh-detail-body");
    function load() {
      api("/github/session/" + encodeURIComponent(id) + "?brain=" + encodeURIComponent(chatBrain())).then(function (d) {
        if (!d || d.ok === false) { body.innerHTML = '<div class="lv-note">' + esc((d && d.error) || tw("gh.err_net")) + "</div>"; return; }
        body.innerHTML = detailHtml(d);
        body.querySelectorAll("[data-merge]").forEach(function (b) {
          b.onclick = function () {
            var msg = b.parentElement.querySelector(".lv-msg");
            b.disabled = true; msg.textContent = tw("gh.merging");
            api("/github/session/" + encodeURIComponent(id) + "/merge", { full_name: b.getAttribute("data-merge") }).then(function (r) {
              if (!r || r.ok === false) { b.disabled = false; msg.textContent = (r && r.error) || tw("gh.err_net"); return; }
              load(); decorate();
            });
          };
        });
        body.querySelectorAll("[data-unqueue]").forEach(function (b) {
          b.onclick = function () { api("/github/session/" + encodeURIComponent(id) + "/next", { cancel: b.getAttribute("data-unqueue") }).then(load); };
        });
      });
    }
    load();
  }

  function init() {
    if (window.JavisComposerMenu) {
      window.JavisComposerMenu.register({ id: "github", order: 25, icon: LOGO, label: "gh.menu",
        hint: function () { return chipText(held || names(), 18); }, panel: panel });
    }
    window.addEventListener("javis:sessions-changed", refresh);
    window.addEventListener("resize", renderChip);
    window.addEventListener("javis:i18n", renderChip);
    window.addEventListener("javis:pinned-folder-changed", renderChip);
    refresh();
    // CI and merges move on their own: refresh the icons and the chip every 30 seconds while the page is visible.
    setInterval(function () {
      if (document.hidden) return;
      decorate();
      if (sid()) refresh();
    }, 30000);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();

  window.JavisGithubRepos = { mount: mount, claimPending: claimPending, refresh: refresh, decorate: decorate, openDetail: openDetail,
    current: function () { return attached.slice(); } };
})();
