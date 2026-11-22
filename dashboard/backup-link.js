/* backup-link.js - brain backup on the signed-in GitHub account (owner, 20/11/2026).
 *
 * The owner: "Javis signs in to GitHub directly now, but the two-way sync on the Self-learning page is still manual.
 * Once GitHub is connected, linking should be easy too." This draws the top of the "Sync brain with GitHub" box:
 *   connect  no GitHub, no repo: one "Connect GitHub" button (the same sign-in as the Connections page)
 *   pick     GitHub connected, no repo: "Create a private repo" or "Pick an existing one", one tap each
 *   linked   the repo, the account it syncs with, "Change" and "Stop syncing"
 *   lost     linked through GitHub but GitHub was disconnected: say so and offer to reconnect
 * A pasted token keeps working: "Use my own token" opens the old form (console.js, #bkManual).
 * The server never sends a token back. Pure helpers are exported for node tests. Never use the em dash here.
 */
(function () {
  "use strict";

  // ---- pure helpers ----
  // bk: GET /backup/status, gh: GET /github/status.
  function phase(bk, gh) {
    bk = bk || {}; gh = gh || {};
    if (bk.repo_url) return bk.token_source ? "linked" : "lost";
    return gh.connected ? "pick" : "connect";
  }
  // "owner/repo" of a GitHub URL, the last part of any other URL, "" when there is none.
  function repoName(url) {
    var u = String(url || "").trim().replace(/\/+$/, "").replace(/\.git$/, "");
    if (!u) return "";
    var m = u.match(/github\.com[/:]([^/]+\/[^/]+)$/i);
    if (m) return m[1];
    return u.split("/").pop();
  }
  function repoWeb(url) {
    var n = repoName(url);
    return /github\.com/i.test(String(url || "")) && n.indexOf("/") > 0 ? "https://github.com/" + n : "";
  }

  var pure = { phase: phase, repoName: repoName, repoWeb: repoWeb };
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
  if (typeof document === "undefined") return;

  function tw(k, v) { return window.t ? window.t(k, v) : k; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function ic(n) { return typeof window.ic === "function" ? window.ic(n) : ""; }
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

  // host: the #bkLink element. opts.onLinked(): run the first sync; opts.onChange(): reload the box;
  // opts.showManual(on): open or close the pasted-token form.
  function mount(host, bk, gh, opts) {
    opts = opts || {};
    var ph = phase(bk, gh);
    host.setAttribute("data-phase", ph);
    var manualBtn = '<button type="button" class="s-btn-ghost" data-bl="manual">' + ic("key-round") + " " + esc(tw("bl.own_token")) + "</button>";
    if (ph === "connect") {
      host.innerHTML = '<div class="lv-meta">' + esc(tw("bl.connect_sub")) + "</div>" +
        '<div class="si-actions"><button type="button" class="s-btn bl-gh" data-bl="connect">' + LOGO + "<span>" + esc(tw("bl.connect")) + "</span></button>" +
        manualBtn + "</div>";
    } else if (ph === "pick") {
      host.innerHTML = '<div class="bl-acc"><span class="conn-chip gh-acc"><span class="cdot hok">●</span> ' + esc(gh.login ? "@" + gh.login : "GitHub") + "</span>" +
        '<span class="lv-meta">' + esc(tw("bl.pick_sub")) + "</span></div>" +
        '<div class="si-actions"><button type="button" class="s-btn" data-bl="create">' + ic("plus") + " " + esc(tw("bl.create")) + "</button>" +
        '<button type="button" class="s-btn-ghost" data-bl="pick">' + ic("folder-git") + " " + esc(tw("bl.pick")) + "</button>" + manualBtn + "</div>" +
        '<div class="lv-msg" role="status" data-bl="msg"></div>';
    } else {
      var name = repoName(bk.repo_url), web = repoWeb(bk.repo_url);
      var who = bk.token_source === "github"
        ? '<span class="conn-chip gh-acc"><span class="cdot hok">●</span> ' + esc(gh.login ? "@" + gh.login : "GitHub") + "</span>"
        : bk.token_source === "token" ? '<span class="conn-chip gh-acc">' + ic("key-round") + " " + esc(tw("bl.own_token_chip")) + "</span>" : "";
      // A pasted token on a GitHub repo the signed-in account can also reach: one tap moves it onto the sign-in,
      // which never expires (a fine-grained token lasts a year at most).
      var swap = bk.token_source === "token" && gh.connected && name.indexOf("/") > 0
        ? '<button type="button" class="conn-chip add" data-bl="swap">' + esc(tw("bl.use_signin", { login: gh.login || "GitHub" })) + "</button>" : "";
      var lost = ph === "lost" ? '<div class="lv-note">' + esc(tw("bl.lost")) + "</div>" : "";
      host.innerHTML = '<div class="gh-rrow bl-repo"><span class="gh-rav">' + LOGO + "</span>" +
        '<div class="gh-rbody"><span class="gh-rti" title="' + esc(bk.repo_url) + '">' +
        (web ? '<a href="' + esc(web) + '" target="_blank" rel="noopener">' + esc(name) + "</a>" : esc(name)) + "</span>" +
        '<span class="gh-rmeta"><span>' + ic("lock") + esc(tw("bl.private")) + "</span><span>" + ic("git-branch") + esc(bk.branch || "main") + "</span></span></div>" +
        '<button type="button" class="bl-ib" data-bl="change" aria-label="' + esc(tw("bl.change")) + '" title="' + esc(tw("bl.change")) + '">' + ic("pencil") + "</button>" +
        '<button type="button" class="bl-ib danger" data-bl="unlink" aria-label="' + esc(tw("bl.unlink")) + '" title="' + esc(tw("bl.unlink")) + '">' + ic("unplug") + "</button></div>" +
        (who || swap ? '<div class="bl-acc">' + who + swap + "</div>" : "") + lost +
        (ph === "lost" ? '<div class="si-actions"><button type="button" class="s-btn bl-gh" data-bl="connect">' + LOGO + "<span>" + esc(tw("bl.connect")) + "</span></button></div>" : "") +
        '<div class="lv-msg" role="status" data-bl="msg"></div>';
    }
    var msg = host.querySelector('[data-bl="msg"]');
    function say(t) { if (msg) msg.textContent = t || ""; }
    function on(sel, fn) { var b = host.querySelector('[data-bl="' + sel + '"]'); if (b) b.onclick = fn; }
    // Returns "" when linked, or the reason it was not.
    async function linkTo(fullName) {
      var r = await api("/backup/github/link", { full_name: fullName });
      if (!r || r.ok === false) return (r && r.error) || tw("gh.err_net");
      if (opts.onLinked) opts.onLinked(r);
      return "";
    }
    on("connect", function () {
      if (window.JavisGithubRepos && window.JavisGithubRepos.connect) window.JavisGithubRepos.connect();
    });
    on("manual", function () { if (opts.showManual) opts.showManual(true); });
    on("create", async function () {
      var b = host.querySelector('[data-bl="create"]');
      b.disabled = true; say(tw("bl.creating"));
      var r = await api("/backup/github/create", {});
      b.disabled = false;
      if (!r || r.ok === false) { say((r && r.error) || tw("gh.err_net")); return; }
      if (r.manual) { say(""); manualCreate(r, gh, function () { openPicker(gh, linkTo); }); return; }
      if (opts.onLinked) opts.onLinked(r);
    });
    on("pick", function () { openPicker(gh, linkTo); });
    on("change", function () { openPicker(gh, linkTo); });
    on("swap", async function () { say(tw("bl.linking")); say(await linkTo(name)); });
    on("unlink", async function () {
      if (!window.confirm(tw("bl.unlink_q"))) return;
      await api("/backup/github/unlink", {});
      if (opts.onChange) opts.onChange();
    });
  }

  // GitHub refused to create the repo (a "Sign in with GitHub" token has no Administration permission): github.com/new
  // already filled in, the page that lets Javis see the new repo when the sign-in is the app, then back to the list.
  function manualCreate(r, gh, next) {
    var M = window.JavisConnModal;
    if (!M) return;
    var steps = '<li><a class="s-btn" target="_blank" rel="noopener" href="' + esc(r.new_url) + '">' + ic("external-link") + " " +
      esc(tw("bl.m_new", { name: r.name || "javis-brain-backup" })) + "</a></li>" +
      (r.install_url ? '<li><a class="s-btn-ghost" target="_blank" rel="noopener" href="' + esc(r.install_url) + '">' +
        ic("external-link") + " " + esc(tw("bl.m_access")) + "</a></li>" : "") +
      '<li><button type="button" class="s-btn-ghost" data-f="next">' + ic("folder-git") + " " + esc(tw("bl.pick")) + "</button></li>";
    var m = M.open(M.head(esc(tw("bl.m_head"))) + '<div class="conn-form bl-form"><div class="lv-meta">' + esc(tw("bl.m_why")) + "</div>" +
      '<ol class="bl-steps">' + steps + "</ol></div>", 560);
    m.querySelector('[data-f="next"]').onclick = function () { next(); };
  }

  // Private repos the account can push to, newest push first, with a search box when there are many.
  async function openPicker(gh, linkTo) {
    var M = window.JavisConnModal;
    if (!M) return;
    var m = M.open(M.head(esc(tw("bl.pick_head"))) + '<div class="conn-form bl-form"><div class="pg-loading" role="status">' +
      esc(tw("gh.loading")) + "</div></div>", 560);
    var form = m.querySelector(".bl-form");
    var r = await api("/backup/github/repos");
    if (!form.isConnected) return;
    if (!r || r.ok === false) { form.innerHTML = '<div class="lv-note">' + esc((r && r.error) || tw("gh.err_net")) + "</div>"; return; }
    var items = r.items || [];
    var foot = '<div class="lv-meta">' + esc(tw("bl.pick_foot")) + (gh.source === "app" && gh.install_url
      ? ' <a target="_blank" rel="noopener" href="' + esc(gh.install_url) + '">' + esc(tw("bl.m_access")) + "</a>" : "") + "</div>";
    if (!items.length) {
      form.innerHTML = '<div class="lv-meta">' + esc(tw("bl.pick_empty")) + "</div>" + foot;
      return;
    }
    form.innerHTML = (items.length > 6 ? '<input class="js-input bl-q" type="search" placeholder="' + esc(tw("bl.search")) + '">' : "") +
      '<div class="gh-rlist bl-list"></div><div class="lv-msg" role="status"></div>' + foot;
    var list = form.querySelector(".bl-list"), msg = form.querySelector(".lv-msg"), q = form.querySelector(".bl-q");
    function draw() {
      var term = q ? q.value.trim().toLowerCase() : "";
      var shown = items.filter(function (x) { return !term || x.full_name.toLowerCase().indexOf(term) >= 0; }).slice(0, 20);
      list.innerHTML = shown.map(function (x) {
        var p = x.full_name.split("/");
        return '<button type="button" class="gh-rrow bl-pick" data-fn="' + esc(x.full_name) + '"><span class="gh-rav">' + LOGO + "</span>" +
          '<span class="gh-rbody"><span class="gh-rti"><span class="gh-rown">' + esc(p[0]) + "/</span>" + esc(p[1] || x.full_name) + "</span>" +
          (x.description ? '<span class="gh-rmeta"><span>' + esc(x.description) + "</span></span>" : "") + "</span></button>";
      }).join("");
      list.querySelectorAll(".bl-pick").forEach(function (b) {
        b.onclick = async function () {
          list.querySelectorAll("button").forEach(function (x) { x.disabled = true; });
          msg.textContent = tw("bl.linking");
          var err = await linkTo(b.getAttribute("data-fn"));
          if (!err) { M.close(); return; }
          list.querySelectorAll("button").forEach(function (x) { x.disabled = false; });
          msg.textContent = err;
        };
      });
    }
    if (q) q.oninput = draw;
    draw();
  }

  window.JavisBackupLink = { mount: mount };
})();
