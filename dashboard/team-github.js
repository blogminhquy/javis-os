/* team-github.js - GitHub repos of a team chat (0.449.0).
 *
 * The owner, 04/11/2026: a team could pin a working folder but not push to GitHub like a private chat. A team chat is a
 * conversation (team.session_id), so it uses the same server routes as the main composer (github-connect.js):
 *   GET  /github/session/{sid}?brain=       repos attached to the team chat, with branch and status icon
 *   POST /github/session/{sid}/repos        add=<name>: attach one more (clone it if missing, its own worktree)
 *   POST /github/session/{sid}/detach       full_name: take one off; refused while work would be lost, unless force
 * Work/Help steps of a job edit the team's worktree, and Javis checks, commits, pushes and opens the PR once the JOB is
 * done (server: main._team_job_done). This file draws the picker that teams.js opens from its "+" menu and the chip.
 * Pure helpers are exported for node tests. Never use the em dash character here.
 */
(function () {
  "use strict";

  // ---- pure helpers ----
  function shortName(full, max) {
    var s = String(full || "").split("/").pop();
    return s.length <= max ? s : s.slice(0, max - 1) + "…";
  }
  // Chip text: the first repo's short name, "+N" for the others.
  function chipText(names, max) {
    var list = (names || []).filter(Boolean);
    if (!list.length) return "";
    return shortName(list[0], max) + (list.length > 1 ? " +" + (list.length - 1) : "");
  }
  // Signed in with the Javis OS app, a repo is listed only once the app may see it: the "+" row opens the app's page on
  // GitHub to tick more (the same row as the main composer, github-connect.js). A pasted token already sees every repo,
  // so it gets no link and the row leads to Connections instead.
  function addReposUrl(st) { return st && st.source === "app" && st.install_url ? String(st.install_url) : ""; }
  var pure = { shortName: shortName, chipText: chipText, addReposUrl: addReposUrl };
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
  if (typeof document === "undefined") return;

  function tw(k, v) { return window.t ? window.t(k, v) : k; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function q(s) { return encodeURIComponent(s == null ? "" : String(s)); }
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

  // Repos attached to a team chat: {repos: [...], icon} or null when the server could not be reached.
  function load(sid, brain) {
    if (!sid) return Promise.resolve({ repos: [] });
    return api("/github/session/" + q(sid) + "?brain=" + q(brain)).then(function (d) {
      return d && d.ok !== false ? { repos: d.repos || [], icon: d.icon || null } : null;
    });
  }
  // One repo joins the chat and the others stay (the "+" of the list); one repo leaves it (its X). The server refuses
  // a removal while the chat's worktree holds unsaved work (code "work_at_risk"); `force` is "remove anyway".
  function add(sid, brain, name) {
    return api("/github/session/" + q(sid) + "/repos", { brain: brain, add: name });
  }
  function detach(sid, brain, name, force) {
    return api("/github/session/" + q(sid) + "/detach", { brain: brain, full_name: name, force: force ? "1" : "" });
  }

  // The picker inside `box`. opts: {sid(), brain(), current() -> [full names], changed(view), close(), connections()}.
  // The list itself is the one of the main chat (github-connect.js, JavisGithubRepos.list): a chosen repo has an X,
  // any other repo is one tap to add, each change is its own request.
  // 2026-11-15: `opts.save(names)` replaces the chat routes, so the same picker sets the repos of a PROJECT or an
  // ASSISTANT (sessions-ui.js drawer). It returns a promise of the server's answer ({ok, repos} or {ok: false, error}).
  // 2026-11-22: a failed check (network, an expired Javis session, a page that is not JSON) reads "Could not check" with
  // a retry, by the rule of the main composer (github-connect.js, JavisGithubRepos.statusState); before, it read "not
  // connected" like a real signed-out GitHub.
  function panel(box, opts, fresh) {
    box.innerHTML = '<div class="cp-empty pg-loading">' + esc(tw("gh.loading")) + "</div>";
    api(fresh ? "/github/status?refresh=1" : "/github/status").then(function (st) {
      if (!box.isConnected) return;
      var G = window.JavisGithubRepos;
      var state = G && G.statusState ? G.statusState(st) : "unknown";
      if (state === "unknown") {
        box.innerHTML = '<div class="cp-empty">' + esc(tw("gh.panel_unknown")) + "<br>" +
          esc(G && G.whyText ? G.whyText(st) : tw("gh.err_net")) + "</div>" +
          '<button type="button" class="cp-mi" data-tg-retry="1"><span class="cp-mi-lbl">' + esc(tw("common.retry")) + "</span></button>";
        box.querySelector("[data-tg-retry]").onclick = function () { panel(box, opts, true); };
        return;
      }
      if (state === "off") {
        box.innerHTML = '<div class="cp-empty">' + esc(tw("gh.panel_not_connected")) + "</div>" +
          '<button type="button" class="cp-mi" data-tg-conn="1"><span class="cp-mi-lbl">' + esc(tw("gh.open_connections")) + "</span></button>";
        box.querySelector("[data-tg-conn]").onclick = function () { opts.close(); if (opts.connections) opts.connections(); };
        return;
      }
      list(box, opts, addReposUrl(st));
    });
  }

  function list(box, opts, addUrl) {
    var G = window.JavisGithubRepos;
    if (!G || !G.list) { box.innerHTML = '<div class="cp-empty">' + esc(tw("gh.err_net")) + "</div>"; return; }
    function names() { return (opts.current() || []).slice(); }
    // A project or an assistant only keeps a list of names: no worktree, so nothing a removal could lose.
    function saveList(next) {
      return Promise.resolve(opts.save(next)).then(function (d) {
        if (d && d.ok !== false && opts.changed) opts.changed({ repos: d.repos || [], icon: d.icon || null });
        return d || { ok: false };
      });
    }
    // A chat: after the change, read the chat's repos again, so the chip and the list show what the server holds.
    function chat(call) {
      var sid = opts.sid();
      if (!sid) return Promise.resolve({ ok: false });
      return call(sid).then(function (d) {
        if (!d || d.ok === false) return d || { ok: false };
        return load(sid, opts.brain()).then(function (v) {
          if (v && opts.changed) opts.changed(v);
          return { ok: true };
        });
      });
    }
    G.list(box, {
      brain: opts.brain, current: names, addUrl: addUrl, ask: opts.ask || null,
      add: function (name) {
        if (opts.save) return saveList(names().concat(names().indexOf(name) < 0 ? [name] : []));
        return chat(function (sid) { return add(sid, opts.brain(), name); });
      },
      remove: function (name, force) {
        if (opts.save) return saveList(names().filter(function (x) { return x !== name; }));
        return chat(function (sid) { return detach(sid, opts.brain(), name, force); });
      },
      connections: function () { opts.close(); if (opts.connections) opts.connections(); }
    });
  }

  // The status of the team chat's pushed work, in the same detail box as a private chat (github-connect.js).
  function openStatus(sid) {
    if (window.JavisGithubRepos && window.JavisGithubRepos.openDetail) window.JavisGithubRepos.openDetail(sid);
  }

  window.JavisTeamGithub = { load: load, panel: panel, detach: detach, openStatus: openStatus, chipText: chipText, shortName: shortName };
})();
