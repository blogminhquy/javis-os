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

  var pure = { chipText: chipText, toggle: toggle, sameSet: sameSet };
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
  if (typeof document === "undefined") return;

  function tw(k, v) { return window.t ? window.t(k, v) : k; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
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
  var BOX = '<svg class="cp-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="3"/></svg>';

  // ============================================================
  // 1. Connections page card
  // ============================================================
  var cardHost = null;
  function cardHtml(st, local) {
    var head = '<div class="prov-head"><span class="conn-ico">' + LOGO + '</span><div class="prov-info"><div class="prov-name">GitHub' +
      infoBtn() + '</div><div class="prov-status j-clamp2">' + esc(st.connected ? tw("gh.connected_as", { login: st.login || "?" }) : tw("gh.not_connected")) +
      (st.connected && st.source === "backup" ? " · " + esc(tw("gh.uses_backup")) : "") + "</div>" + infoBody(esc(tw("gh.intro"))) + "</div></div>";
    var warn = st.connected && st.missing && st.missing.length
      ? '<div class="lv-note">' + esc(tw("gh.missing_scopes", { scopes: st.missing.join(", ") })) + "</div>" : "";
    var noGit = st.has_git === false ? '<div class="lv-note">' + esc(tw("gh.no_git")) + "</div>" : "";
    var repos = "";
    if (st.connected) {
      repos = '<div class="gh-local"><div class="gh-local-head">' + esc(tw("gh.local_head", { n: local.length })) + infoBtn() + "</div>" +
        infoBody(esc(tw("gh.local_how"))) +
        (local.length ? local.map(function (r) {
          return '<div class="gh-local-row"><span class="gh-local-name">' + esc(r.full_name) + "</span>" +
            '<span class="gh-local-meta">' + esc(tw("gh.local_chats", { n: r.chats || 0 })) + "</span>" +
            '<button class="s-btn-ghost" type="button" data-gh-remove="' + esc(r.full_name) + '">' + esc(tw("gh.remove_brain")) + "</button></div>";
        }).join("") : '<div class="mp-empty">' + esc(tw("gh.local_none")) + "</div>") +
        '<div class="lv-msg" role="status" data-gh-msg></div></div>';
    }
    var acts = '<div class="conn-accounts">' + (st.connected
      ? '<button class="conn-chip" type="button" data-gh-open>' + esc(tw("gh.change_token")) + "</button>" +
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
    // A connected GitHub counts as a connection: the "nothing connected yet" line must not sit under it.
    var empty = document.querySelector("#connList > .mp-empty");
    if (empty && st.connected) empty.hidden = true;
    var open = cardHost.querySelector("[data-gh-open]");
    if (open) open.onclick = function () { openForm(st); };
    var off = cardHost.querySelector("[data-gh-off]");
    if (off) off.onclick = async function () {
      if (!window.confirm(tw("gh.disconnect_q"))) return;
      await api("/github/disconnect", {});
      loadCard();
    };
    cardHost.querySelectorAll("[data-gh-remove]").forEach(function (b) {
      b.onclick = async function () {
        var name = b.getAttribute("data-gh-remove");
        if (!window.confirm(tw("gh.remove_q", { name: name }))) return;
        var msg = cardHost.querySelector("[data-gh-msg]");
        b.disabled = true;
        var r = await api("/github/local/remove", { brain: pageBrain(), full_name: name });
        b.disabled = false;
        if (!r || r.ok === false) { if (msg) msg.textContent = (r && r.error) || tw("gh.err_net"); return; }
        loadCard();
      };
    });
  }
  function openForm(st) {
    var M = window.JavisConnModal;
    if (!M) return;
    var html = M.head(esc(tw("gh.dialog_head"))) + '<div class="conn-form gh-form">' +
      '<div class="si-field"><label>' + esc(tw("gh.token")) + infoBtn() + "</label>" + infoBody(esc(tw("gh.token_how"))) +
      '<input class="js-input" data-f="token" type="password" autocomplete="off" spellcheck="false" placeholder="' + esc(tw("gh.token_ph")) + '"></div>' +
      '<div class="lv-form-act"><button class="s-btn" type="button" data-f="go">' + esc(tw("gh.connect")) + "</button>" +
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
    form.querySelector('[data-f="go"]').onclick = function () { go({ token: form.querySelector('[data-f="token"]').value.trim() }); };
    var bk = form.querySelector('[data-f="backup"]');
    if (bk) bk.onclick = function () { go({ use_backup: "1" }); };
    form.querySelector('[data-f="cancel"]').onclick = function () { M.close(); };
    setTimeout(function () { try { form.querySelector('[data-f="token"]').focus(); } catch (e) {} }, 30);
  }
  function mount(el) { cardHost = el || null; if (cardHost) loadCard(); }

  // ============================================================
  // 2 and 3. Repos of the open conversation: + menu panel and chip
  // ============================================================
  var attached = [], held = null, heldBrain = "", seq = 0;
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
    chip.title = list.join("\n") + (attached.length && attached[0].branch ? "\n" + tw("gh.chip_branch", { branch: attached[0].branch }) : "");
    chip.setAttribute("aria-label", tw("gh.chip_label", { names: list.join(", ") }));
    chip.innerHTML = LOGO + "<span>" + esc(chipText(list, narrow() ? 10 : 18)) + "</span>";
  }
  function apply(d) {
    attached = (d && d.repos) || [];
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
    var list = held, sameBrain = heldBrain === chatBrain();
    held = null; heldBrain = "";
    if (!sameBrain) { renderChip(); return null; }
    return api("/github/session/" + encodeURIComponent(newSid) + "/repos", { brain: chatBrain(), repos: list.join(",") }).then(function (d) {
      if (d && d.ok !== false) { apply(d); return; }
      apply(null);
      if (window.JavisAttach) window.JavisAttach.note((d && d.error) || tw("gh.err_net"));
    });
  }

  function panel(box, menuApi) {
    box.innerHTML = '<div class="cp-empty">' + esc(tw("gh.loading")) + "</div>";
    api("/github/status").then(function (st) {
      if (!st || !st.connected) {
        box.innerHTML = '<div class="cp-empty">' + esc(tw("gh.panel_not_connected")) + "</div>" +
          '<button type="button" class="cp-mi" data-go-connect="1">' + LOGO + '<span class="cp-mi-lbl">' + esc(tw("gh.open_connections")) + "</span></button>";
        box.querySelector("[data-go-connect]").onclick = function () {
          menuApi.close();
          try { window.Alpine.store("nav").go("mcp"); } catch (e) { location.hash = "#mcp"; }
        };
        return;
      }
      var chosen = held ? held.slice() : names(), start = chosen.slice(), items = [], timer = 0, n = 0;
      box.innerHTML = '<input type="search" class="cp-search" placeholder="' + esc(tw("gh.search_ph")) + '" aria-label="' + esc(tw("gh.search_ph")) + '">' +
        '<div class="cp-results" role="listbox" aria-multiselectable="true"></div><div class="cp-sep"></div>' +
        '<button type="button" class="cp-mi gh-apply" data-apply="1" disabled><span class="cp-mi-lbl"></span></button>' +
        '<div class="cp-pin-err" role="status"></div>';
      var input = box.querySelector(".cp-search"), out = box.querySelector(".cp-results"), applyBtn = box.querySelector("[data-apply]"),
        err = box.querySelector(".cp-pin-err");
      function drawApply() {
        var changed = !sameSet(chosen, start);
        applyBtn.disabled = !changed;
        applyBtn.querySelector(".cp-mi-lbl").textContent = chosen.length ? tw("gh.apply_n", { n: chosen.length })
          : (start.length ? tw("gh.apply_none") : tw("gh.apply_pick"));
      }
      function draw() {
        out.innerHTML = items.length ? items.map(function (r, i) {
          var on = chosen.indexOf(r.full_name) >= 0;
          return '<button type="button" class="cp-mi" role="option" aria-selected="' + on + '" data-i="' + i + '">' + (on ? CHECK : BOX) +
            '<span class="cp-mi-lbl">' + esc(r.full_name) + "</span>" +
            '<span class="cp-mi-hint">' + esc(r.cloned ? tw("gh.cloned") : (r.private ? tw("gh.private") : "")) + "</span></button>";
        }).join("") : '<div class="cp-empty">' + esc(tw("gh.none_found")) + "</div>";
        drawApply();
      }
      function load() {
        var q = input.value.trim(), k = ++n;
        api("/github/repos?brain=" + encodeURIComponent(chatBrain()) + "&q=" + encodeURIComponent(q)).then(function (d) {
          if (k !== n) return;
          if (!d || d.ok === false) { err.textContent = (d && d.error) || tw("gh.err_net"); items = []; draw(); return; }
          items = d.items || [];
          // Attached repos stay visible at the top even when the search hides them, so they can be unticked.
          chosen.forEach(function (name) {
            if (!items.some(function (x) { return x.full_name === name; }) && !q) items.unshift({ full_name: name, cloned: true });
          });
          draw();
        });
      }
      out.addEventListener("click", function (e) {
        var b = e.target.closest ? e.target.closest("[data-i]") : null;
        if (!b) return;
        var r = items[+b.getAttribute("data-i")];
        if (r) { chosen = toggle(chosen, r.full_name); draw(); }
      });
      applyBtn.onclick = function () {
        applyBtn.disabled = true;
        err.textContent = chosen.length ? tw("gh.cloning") : "";
        setRepos(chosen).then(function (msg) {
          if (msg) { err.textContent = msg; drawApply(); return; }
          menuApi.close();
          var i = document.getElementById("chatInput"); if (i) i.focus();
        });
      };
      input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(load, 200); });
      input.focus();
      load();
    });
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
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();

  window.JavisGithubRepos = { mount: mount, claimPending: claimPending, refresh: refresh, current: function () { return attached.slice(); } };
})();
