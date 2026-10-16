/* core-memory.js - what Javis remembers, on the Javis Core card (0.188.0, Javis Core spec sections 10.2, 12 and 13).

   Three things the person controls, on the brain open now:
   - the switch "save new memories" (off: what is remembered stays in use, nothing new is written);
   - the list of memories with their type, source and date, each one editable or forgettable;
   - their own profile, shared by every brain (how to address them, language, level of detail).

   Forgetting says its scope before it runs: this brain only, chats untouched, and a brain kept in git or a backup
   made earlier still holds the old text. All text on screen goes through i18n. */
(function () {
  "use strict";

  function tw(k, v) {
    if (typeof window !== "undefined" && window.t) return window.t(k, v);
    return k;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  async function getJson(url) { var r = await fetch(url, { cache: "no-store" }); return r.json(); }
  async function postJson(url, body) {
    var r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return r.json();
  }

  // One line under a memory's title: type, where it came from, when. Pure, for tests.
  function metaLine(m) {
    var parts = [];
    if (m.type) parts.push(m.type);
    if (m.origin === "owner-edited") parts.push(tw("core.mem_by_you"));
    else if (m.origin === "javis-learned") parts.push(tw("core.mem_learned"));
    if (m.source) parts.push(m.source);
    if (m.status === "inferred") parts.push(tw("core.mem_inferred"));
    var d = m.updated || m.created;
    if (d) parts.push(d);
    return parts.join(" · ");
  }

  function itemHtml(m) {
    return '<li class="cm-item" data-slug="' + esc(m.slug) + '">' +
      '<div class="cm-title">' + esc(m.title) + '</div>' +
      '<div class="cm-meta">' + esc(metaLine(m)) + '</div>' +
      '<div class="cm-body">' + esc(m.body) + '</div>' +
      '<div class="cm-acts"><button type="button" class="cm-btn" data-cm="edit">' + esc(tw("common.edit")) + '</button>' +
      '<button type="button" class="cm-btn danger" data-cm="forget">' + esc(tw("core.mem_forget")) + '</button></div>' +
      '</li>';
  }

  async function mount(host, brain) {
    if (!host) return;
    host.innerHTML = '<div class="cm-loading">' + esc(tw("common.loading")) + '</div>';
    var b = encodeURIComponent(brain || "brain");
    var data, prof;
    try { data = await getJson("/memory/items?brain=" + b); prof = await getJson("/profile"); }
    catch (e) { host.innerHTML = '<p class="cm-err">' + esc(tw("core.mem_load_err")) + '</p>'; return; }
    var items = (data && data.items) || [];
    host.innerHTML =
      '<div class="ws-rtitle">' + esc(tw("core.mem_title")) + '</div>' +
      '<label class="cm-switch"><input type="checkbox" id="cmLearn"' + (data.learning ? " checked" : "") + '> ' +
        '<span>' + esc(tw("core.mem_learning")) + '</span></label>' +
      '<p class="cm-hint" id="cmLearnHint">' + esc(tw(data.learning ? "core.mem_learning_on" : "core.mem_learning_off")) + '</p>' +
      (items.length
        ? '<ul class="cm-list">' + items.map(itemHtml).join("") + '</ul>'
        : '<p class="cm-hint">' + esc(tw("core.mem_empty")) + '</p>') +
      (data.forgotten ? '<p class="cm-hint">' + esc(tw("core.mem_forgotten_n", { n: data.forgotten })) + '</p>' : "") +
      '<div class="ws-rtitle">' + esc(tw("core.profile_title")) + '</div>' +
      '<p class="cm-hint">' + esc(tw("core.profile_hint")) + '</p>' +
      '<textarea class="cm-text" id="cmProfile" rows="4" maxlength="' + ((prof && prof.max) || 4000) + '" placeholder="' +
        esc(tw("core.profile_ph")) + '">' + esc((prof && prof.text) || "") + '</textarea>' +
      '<div class="cm-acts"><button type="button" class="cm-btn primary" id="cmProfileSave">' + esc(tw("common.save")) +
        '</button><span class="cm-note" id="cmProfileNote" role="status"></span></div>';

    host.querySelector("#cmLearn").onchange = async function (e) {
      var on = !!e.target.checked;
      await postJson("/memory/learning", { brain: brain, enabled: on });
      var h = host.querySelector("#cmLearnHint");
      if (h) h.textContent = tw(on ? "core.mem_learning_on" : "core.mem_learning_off");
    };
    host.querySelector("#cmProfileSave").onclick = async function () {
      var r = await postJson("/profile", { text: host.querySelector("#cmProfile").value });
      var n = host.querySelector("#cmProfileNote");
      if (n) n.textContent = r && r.ok ? tw("core.saved") : tw("core.save_err");
    };
    host.querySelectorAll(".cm-item").forEach(function (li) {
      var slug = li.dataset.slug;
      var m = items.find(function (x) { return x.slug === slug; }) || {};
      li.querySelector('[data-cm="forget"]').onclick = async function () {
        if (!confirm(tw("core.mem_forget_confirm", { title: m.title || slug, brain: data.brain || "" }))) return;
        var r = await postJson("/memory/forget", { brain: brain, slug: slug });
        if (r && r.ok) mount(host, brain);
      };
      li.querySelector('[data-cm="edit"]').onclick = function () {
        var body = li.querySelector(".cm-body");
        body.innerHTML = '<textarea class="cm-text" rows="4">' + esc(m.body || "") + '</textarea>' +
          '<div class="cm-acts"><button type="button" class="cm-btn primary" data-cm="save">' + esc(tw("common.save")) +
          '</button><button type="button" class="cm-btn" data-cm="cancel">' + esc(tw("common.cancel")) + '</button></div>';
        body.querySelector('[data-cm="cancel"]').onclick = function () { mount(host, brain); };
        body.querySelector('[data-cm="save"]').onclick = async function () {
          var r = await postJson("/memory/edit", { brain: brain, slug: slug, body: body.querySelector("textarea").value });
          if (r && r.ok) mount(host, brain);
        };
      };
    });
  }

  var api = { mount: mount, metaLine: metaLine, itemHtml: itemHtml };
  if (typeof window !== "undefined") window.JavisCoreMemory = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
