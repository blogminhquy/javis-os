/* team-github.js - GitHub repos of a team chat (0.449.0).
 *
 * The owner, 04/11/2026: a team could pin a working folder but not push to GitHub like a private chat. A team chat is a
 * conversation (team.session_id), so it uses the same server routes as the main composer (github-connect.js):
 *   GET  /github/session/{sid}?brain=       repos attached to the team chat, with branch and status icon
 *   POST /github/session/{sid}/repos        set them (clone what is missing, one worktree each)
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
  function toggle(list, name) {
    var out = (list || []).slice(), i = out.indexOf(name);
    if (i >= 0) out.splice(i, 1); else out.push(name);
    return out;
  }
  function sameSet(a, b) {
    a = (a || []).slice().sort(); b = (b || []).slice().sort();
    return a.length === b.length && a.every(function (x, i) { return x === b[i]; });
  }
  // The list as drawn: chosen repos first ("Selected"), then the rest. A chosen repo the search hid stays listed while
  // the search box is empty, so it can be unticked.
  function split(items, chosen, query) {
    var list = (items || []).slice();
    if (!String(query || "").trim()) {
      (chosen || []).forEach(function (n) {
        if (!list.some(function (x) { return x.full_name === n; })) list.unshift({ full_name: n, cloned: true });
      });
    }
    var sel = [], rest = [];
    list.forEach(function (r) { ((chosen || []).indexOf(r.full_name) >= 0 ? sel : rest).push(r); });
    return { selected: sel, rest: rest, all: sel.concat(rest) };
  }

  var pure = { shortName: shortName, chipText: chipText, toggle: toggle, sameSet: sameSet, split: split };
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
  var CHECK = '<svg class="cp-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>';

  // Repos attached to a team chat: {repos: [...], icon} or null when the server could not be reached.
  function load(sid, brain) {
    if (!sid) return Promise.resolve({ repos: [] });
    return api("/github/session/" + q(sid) + "?brain=" + q(brain)).then(function (d) {
      return d && d.ok !== false ? { repos: d.repos || [], icon: d.icon || null } : null;
    });
  }
  function save(sid, brain, names) {
    return api("/github/session/" + q(sid) + "/repos", { brain: brain, repos: (names || []).join(",") });
  }

  // The picker inside `box`. opts: {sid(), brain(), current() -> [full names], changed(view), close(), connections()}.
  // Ticking attaches at once and unticking detaches (like the main composer); a tick made while a request is in flight
  // rides on the next one, so the server always ends on the last state shown.
  function panel(box, opts) {
    box.innerHTML = '<div class="cp-empty">' + esc(tw("gh.loading")) + "</div>";
    api("/github/status").then(function (st) {
      if (!box.isConnected) return;
      if (!st || !st.connected) {
        box.innerHTML = '<div class="cp-empty">' + esc(tw("gh.panel_not_connected")) + "</div>" +
          '<button type="button" class="cp-mi" data-tg-conn="1"><span class="cp-mi-lbl">' + esc(tw("gh.open_connections")) + "</span></button>";
        box.querySelector("[data-tg-conn]").onclick = function () { opts.close(); if (opts.connections) opts.connections(); };
        return;
      }
      list(box, opts);
    });
  }

  function list(box, opts) {
    var chosen = (opts.current() || []).slice(), sent = chosen.slice(), busy = false, items = [], timer = 0, n = 0;
    box.innerHTML = '<input type="search" class="cp-search" placeholder="' + esc(tw("gh.search_ph")) + '" aria-label="' + esc(tw("gh.search_ph")) + '">' +
      '<div class="cp-results gh-results" role="listbox" aria-multiselectable="true"></div>' +
      '<div class="cp-pin-err" role="status"></div>';
    var input = box.querySelector(".cp-search"), out = box.querySelector(".cp-results"), err = box.querySelector(".cp-pin-err");
    function row(r, i, on) {
      var parts = String(r.full_name).split("/");
      var tag = r.cloned ? tw("gh.cloned") : (r.private ? tw("gh.private") : "");
      return '<button type="button" class="cp-mi gh-repo" role="option" aria-selected="' + on + '" data-tg-i="' + i + '">' +
        '<span class="gh-two"><span class="gh-owner">' + esc(parts[0]) + (tag ? " · " + esc(tag) : "") + "</span>" +
        '<span class="gh-name">' + esc(parts[1] || r.full_name) + "</span></span>" +
        (on ? '<span class="gh-tick">' + CHECK + "</span>" : "") + "</button>";
    }
    var shown = [];
    function draw() {
      var v = split(items, chosen, input.value);
      shown = v.all;
      var i = 0;
      var sel = v.selected.map(function (r) { return row(r, i++, true); }).join("");
      var rest = v.rest.map(function (r) { return row(r, i++, false); }).join("");
      out.innerHTML = (sel ? '<div class="gh-sec">' + esc(tw("gh.sec_selected")) + '</div><div class="gh-group">' + sel + "</div>" : "") +
        (rest ? '<div class="gh-sec">' + esc(tw("gh.sec_repos")) + '</div><div class="gh-group">' + rest + "</div>" : "") +
        (!shown.length ? '<div class="cp-empty">' + esc(tw("gh.none_found")) + "</div>" : "");
    }
    function sync() {
      if (busy || sameSet(chosen, sent)) return;
      var want = chosen.slice(), adds = want.some(function (x) { return sent.indexOf(x) < 0; });
      var sid = opts.sid();
      if (!sid) return;
      busy = true;
      err.textContent = adds ? tw("gh.cloning") : "";
      save(sid, opts.brain(), want).then(function (d) {
        busy = false;
        if (!d || d.ok === false) {
          chosen = sent.slice();
          err.textContent = (d && d.error) || tw("gh.err_net");
          if (box.isConnected) draw();
          return;
        }
        sent = want;
        err.textContent = "";
        if (opts.changed) opts.changed({ repos: d.repos || [], icon: d.icon || null });
        sync();
      });
    }
    function fetchList() {
      var k = ++n;
      api("/github/repos?brain=" + q(opts.brain()) + "&q=" + q(input.value.trim())).then(function (d) {
        if (k !== n || !box.isConnected) return;
        if (!d || d.ok === false) { err.textContent = (d && d.error) || tw("gh.err_net"); items = []; draw(); return; }
        items = d.items || [];
        draw();
      });
    }
    out.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("[data-tg-i]") : null;
      if (!b) return;
      var r = shown[+b.getAttribute("data-tg-i")];
      if (!r) return;
      chosen = toggle(chosen, r.full_name);
      draw();
      sync();
    });
    input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(fetchList, 200); });
    input.focus();
    draw();
    fetchList();
  }

  // The status of the team chat's pushed work, in the same detail box as a private chat (github-connect.js).
  function openStatus(sid) {
    if (window.JavisGithubRepos && window.JavisGithubRepos.openDetail) window.JavisGithubRepos.openDetail(sid);
  }

  window.JavisTeamGithub = { load: load, panel: panel, openStatus: openStatus, chipText: chipText, shortName: shortName };
})();
