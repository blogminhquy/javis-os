/* vault-pins.js - pinned folders and folders open by default in the Vault tree (user request, 2026-11-11).
 *
 * "Let Javis pin a folder, and give an option to unfold a folder by default. I pin the wiki folder and keep it open."
 * Two lists per brain, kept on the server (GET/POST /files/tree-prefs, server/vault_tree_prefs.py) so the phone and
 * the laptop show the same tree:
 *   - pinned: these folders are listed first, above the rest of the tree, wherever they sit in the brain;
 *   - open:   these folders are already unfolded when the tree loads.
 * Paths in both lists are relative to the BRAIN ROOT. The tree itself works with paths relative to the browse ceiling
 * (`home` is the brain root in those terms, "" when the ceiling is the brain), so toTree / toBrain convert at the edge.
 * console.js draws the rows and the menu; this file holds the lists and the pure rules, exported for node tests.
 */
(function () {
  "use strict";

  var EMPTY = { pinned: [], open: [] };

  function cleanList(list) {
    var out = [], seen = {};
    (Array.isArray(list) ? list : []).forEach(function (x) {
      var p = String(x == null ? "" : x).replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
      if (!p || seen[p]) return;
      seen[p] = true;
      out.push(p);
    });
    return out;
  }

  function clean(prefs) {
    prefs = prefs || EMPTY;
    return { pinned: cleanList(prefs.pinned), open: cleanList(prefs.open) };
  }

  // A tree path (relative to the browse ceiling) as a brain path. null: the brain root itself, or outside the brain.
  function toBrain(rel, home) {
    rel = String(rel || "");
    if (!home) return rel || null;
    if (rel.indexOf(home + "/") === 0) return rel.slice(home.length + 1);
    return null;
  }

  function toTree(path, home) {
    return home ? home + "/" + path : path;
  }

  function has(list, path) {
    return !!path && (list || []).indexOf(path) !== -1;
  }

  // The prefs with `path` added to or taken out of one list ("pinned" or "open").
  function toggled(prefs, field, path) {
    var next = clean(prefs);
    var at = next[field].indexOf(path);
    if (at === -1) next[field].push(path); else next[field].splice(at, 1);
    return next;
  }

  // The root listing split in two: the pinned folders (in the order they were pinned, as rows `_vtRowEl` can draw
  // under `parent`), then the root items that are not already shown as a pin.
  function splitRoot(items, prefs, home) {
    var pinnedAtRoot = {};
    var pinned = cleanList(prefs && prefs.pinned).map(function (path) {
      var cut = path.lastIndexOf("/");
      if (cut === -1) pinnedAtRoot[path] = true;
      return {
        path: path,
        parent: cut === -1 ? (home || "") : toTree(path.slice(0, cut), home),
        item: { name: path.slice(cut + 1), type: "dir", ext: "" },
      };
    });
    var rest = (items || []).filter(function (it) { return !(it && it.type === "dir" && pinnedAtRoot[it.name]); });
    return { pinned: pinned, rest: rest };
  }

  // The folders to click open so that `path` (a brain path) shows, as tree paths from shallow to deep. The walk
  // starts at the nearest pinned folder on the way: that one is a row of its own at the top, so nothing above it has
  // to unfold.
  function chain(path, prefs, home) {
    var segs = String(path || "").split("/").filter(Boolean), out = [], acc = "";
    segs.forEach(function (seg) {
      acc = acc ? acc + "/" + seg : seg;
      if (has(prefs && prefs.pinned, acc)) out = [];
      out.push(toTree(acc, home));
    });
    return out;
  }

  // Every folder to unfold when the tree loads, parents before children, each once.
  function openPlan(prefs, home) {
    var out = [], seen = {};
    cleanList(prefs && prefs.open).forEach(function (path) {
      chain(path, prefs, home).forEach(function (rel) {
        if (!seen[rel]) { seen[rel] = true; out.push(rel); }
      });
    });
    return out.sort(function (a, b) { return a.split("/").length - b.split("/").length; });
  }

  var pure = { clean: clean, toBrain: toBrain, toTree: toTree, has: has, toggled: toggled, splitRoot: splitRoot,
    chain: chain, openPlan: openPlan };
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
  if (typeof window === "undefined") return;

  var cache = {};     // brain -> prefs, as last read from or saved to the server
  var pending = {};   // brain -> the read in flight, so two renders of the same tree share one request

  // What this brain has saved. Asked once per page load; `force` asks again (the Refresh button, after a rename).
  // A failed read answers what is already known, or empty lists: the tree must still draw.
  function load(brain, force) {
    if (cache[brain] && !force) return Promise.resolve(cache[brain]);
    if (pending[brain]) return pending[brain];
    var req = fetch("/files/tree-prefs?brain=" + encodeURIComponent(brain))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d && d.ok) cache[brain] = clean(d); })
      .catch(function () { /* offline or an older server: keep what we have */ })
      .then(function () { delete pending[brain]; return cache[brain] || clean(EMPTY); });
    pending[brain] = req;
    return req;
  }

  function current(brain) {
    return cache[brain] || clean(EMPTY);
  }

  // Save both lists. Resolves true when the server took them; on a refusal the lists go back to what they were.
  function save(brain, prefs) {
    var before = current(brain), next = clean(prefs);
    cache[brain] = next;
    var fd = new FormData();
    fd.append("brain", brain);
    fd.append("pinned", JSON.stringify(next.pinned));
    fd.append("open", JSON.stringify(next.open));
    return fetch("/files/tree-prefs", { method: "POST", body: fd })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d && d.ok) { cache[brain] = clean(d); return true; }
        cache[brain] = before;
        return false;
      })
      .catch(function () { cache[brain] = before; return false; });
  }

  window.JavisVaultPins = {
    clean: clean, toBrain: toBrain, toTree: toTree, has: has, toggled: toggled, splitRoot: splitRoot, chain: chain,
    openPlan: openPlan, load: load, current: current, save: save,
  };
})();
