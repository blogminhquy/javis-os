/* Disk cleanup page: scan drives, mapped network drives and a NAS, then tidy up identical duplicates and look-alike
 * photos by moving the extra copies into a quarantine the owner can restore.
 *
 * Server side is server/file_scan.py behind the /filescan/* routes, shared with the `javis_files` tool, so a scan
 * started from the chat shows its progress here. Nothing is deleted from this page except by "Delete for good" on a
 * quarantine batch, behind a confirm.
 *
 * Owner rules kept here: no repeated page title, long explanations behind the (i) button, text 16px, no long dashes.
 * Render helpers are pure (tested under node); `mount` loads data and wires the clicks.
 */
(function () {
  "use strict";

  var TABS = ["overview", "dups", "similar", "quarantine"];
  var TAB_ICON = { overview: "chart-pie", dups: "copy", similar: "image", quarantine: "shield" };
  var TAB_KEY = { overview: "cl.tab.overview", dups: "cl.tab.dups", similar: "cl.tab.similar", quarantine: "cl.tab.quarantine" };
  var CAT_KEY = { image: "cl.cat.image", video: "cl.cat.video", audio: "cl.cat.audio", document: "cl.cat.document",
    archive: "cl.cat.archive", installer: "cl.cat.installer", code: "cl.cat.code", other: "cl.cat.other" };
  var KIND_KEY = { local: "cl.kind.local", removable: "cl.kind.removable", network: "cl.kind.network",
    optical: "cl.kind.optical", ramdisk: "cl.kind.local", unknown: "cl.kind.local" };
  var REFUSED_KEY = { not_indexed: "cl.refused.not_indexed", changed: "cl.refused.changed", last_copy: "cl.refused.last_copy",
    outside_root: "cl.refused.outside_root", os_error: "cl.refused.os_error" };
  var STATE_KEY = { quarantined: "cl.state.quarantined", restored: "cl.state.restored", purged: "cl.state.purged" };
  var MIN_KB = [0, 100, 1024, 10240];
  var PAGE = 50;
  var POLL_MS = 1500;
  var PREF_KEY = "javis_cleanup_pref";

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
  function infoPair(html, label) {
    var J = typeof window !== "undefined" && window.JavisInfo;
    return J ? J.pair(html, label || tw("info.more")) : '<div class="info-body">' + html + "</div>";
  }
  function locale() {
    try { return (window.JavisI18n && window.JavisI18n.locale()) || "vi-VN"; } catch (e) { return "vi-VN"; }
  }
  function fmtInt(n) {
    try { return Number(n || 0).toLocaleString(locale()); } catch (e) { return String(n || 0); }
  }
  function fmtSize(n) {
    n = Number(n || 0);
    var units = ["B", "KB", "MB", "GB", "TB"];
    var i = 0;
    while (Math.abs(n) >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return (i === 0 ? String(Math.round(n)) : (Math.round(n * 10) / 10).toString()) + " " + units[i];
  }
  function fmtTime(sec) {
    if (!sec) return "-";
    try { return new Date(sec * 1000).toLocaleString(locale(), { dateStyle: "short", timeStyle: "short" }); }
    catch (e) { return String(sec); }
  }
  function baseName(p) {
    var s = String(p || "");
    var i = Math.max(s.lastIndexOf("\\"), s.lastIndexOf("/"));
    return i >= 0 ? s.slice(i + 1) : s;
  }

  // ---------- pure helpers ----------
  // The copies a duplicate group suggests removing: every copy except the one to keep.
  function suggestedDups(groups) {
    var out = [];
    (groups || []).forEach(function (g) { (g.copies || []).forEach(function (p) { out.push(p); }); });
    return out;
  }
  function suggestedSimilar(group) {
    return (group.files || []).filter(function (f) { return f.path !== group.keep; }).map(function (f) { return f.path; });
  }
  // Selected count and bytes, from the groups on screen. A group with every member selected is "unsafe": the server
  // would refuse its last copy, so the page warns before sending.
  function selectionInfo(groups, sel, similar) {
    var n = 0, bytes = 0, unsafe = 0;
    (groups || []).forEach(function (g) {
      var members = similar ? (g.files || []).map(function (f) { return { path: f.path, size: f.size }; })
        : [g.keep].concat(g.copies || []).map(function (p) { return { path: p, size: g.size }; });
      var picked = 0;
      members.forEach(function (m) { if (sel[m.path]) { picked++; n++; bytes += m.size || 0; } });
      if (members.length && picked === members.length) unsafe++;
    });
    return { count: n, bytes: bytes, unsafe: unsafe };
  }
  function progressText(st) {
    var p = (st && st.progress) || {};
    if (p.phase === "walk") return p.files != null ? tw("cl.prog.walk_n", { n: fmtInt(p.files), size: fmtSize(p.bytes) }) : tw("cl.prog.walk");
    if (p.phase === "edge") return tw("cl.prog.edge", { done: fmtInt(p.done), total: fmtInt(p.total) });
    if (p.phase === "full") return tw("cl.prog.full", { done: fmtInt(p.done), total: fmtInt(p.total) });
    if (p.phase === "image") return tw("cl.prog.image", { done: fmtInt(p.done), total: fmtInt(p.total) });
    return tw("cl.prog.start");
  }

  // ---------- render ----------
  function scanBar(st) {
    var s = st.status || {};
    var drives = (st.drives || []).filter(function (d) { return d.kind !== "optical"; });
    var chips = drives.map(function (d) {
      var on = st.roots.indexOf(d.path) >= 0;
      var sub = d.total ? fmtSize(d.free) + " / " + fmtSize(d.total) : "";
      return '<button class="cl-drive' + (on ? " on" : "") + '" data-act="drive" data-path="' + esc(d.path) + '" aria-pressed="' + on + '">' +
        ic(d.kind === "network" ? "database" : "folder") + "<b>" + esc(d.path) + "</b>" +
        '<span class="cl-muted">' + esc(tw(KIND_KEY[d.kind] || "cl.kind.local")) + (d.label ? " · " + esc(d.label) : "") + "</span>" +
        (d.unc || d.host ? '<span class="cl-muted cl-unc">' + esc(d.unc || d.host) + "</span>" : "") +
        (d.readonly ? '<span class="cl-chip">' + esc(tw("cl.readonly")) + "</span>" : "") +
        (sub ? '<span class="cl-muted">' + esc(sub) + "</span>" : "") + "</button>";
    }).join("");
    var extra = st.roots.filter(function (r) { return !drives.some(function (d) { return d.path === r; }); });
    var extraChips = extra.map(function (r) {
      return '<button class="cl-drive on" data-act="drive" data-path="' + esc(r) + '" aria-pressed="true">' + ic("folder-open") +
        "<b>" + esc(r) + "</b>" + ic("x") + "</button>";
    }).join("");
    var running = !!s.running;
    var line = "";
    if (running) {
      line = '<div class="cl-prog">' + ic("loader-circle") + "<span>" + esc(tw("cl.scanning", { roots: (s.roots || []).join(", ") })) +
        ": " + esc(progressText(s)) + "</span></div>";
    } else if (s.status === "done" && s.result) {
      line = '<div class="cl-muted">' + esc(tw("cl.last_scan", { n: fmtInt(s.result.files), size: fmtSize(s.result.bytes), sec: Math.round(s.result.seconds || 0) })) + "</div>";
    } else if (s.status === "error") {
      line = '<div class="cl-err">' + esc(s.error || "") + "</div>";
    }
    var help = infoPair("<p>" + esc(tw("cl.help.scan")) + "</p><p>" + esc(tw("cl.help.nas")) + "</p><p>" + esc(tw("cl.help.safe")) + "</p>", tw("cl.help.label"));
    return '<div class="cl-card cl-scan">' +
      '<div class="cl-drives">' + chips + extraChips + "</div>" +
      '<div class="cl-row">' +
      '<input class="cl-input" data-role="path" type="text" spellcheck="false" placeholder="' + esc(tw("cl.path_ph")) + '">' +
      '<button class="cl-btn" data-act="addpath">' + ic("folder-open") + esc(tw("cl.add")) + "</button>" +
      '<label class="cl-check"><input type="checkbox" data-role="images"' + (st.images ? " checked" : "") + "> " + esc(tw("cl.images_opt")) + "</label>" +
      '<span class="cl-sp"></span>' +
      (running ? '<button class="cl-btn" data-act="cancel">' + ic("circle-stop") + esc(tw("cl.stop")) + "</button>"
        : '<button class="cl-btn pri" data-act="scan"' + (st.roots.length ? "" : " disabled") + ">" + ic("search") + esc(tw("cl.scan")) + "</button>") +
      help + "</div>" + line + (st.msg ? '<div class="cl-msg">' + esc(st.msg) + "</div>" : "") + "</div>";
  }

  function tabsHtml(st) {
    var counts = {
      dups: st.overview ? st.overview.dup_groups : null,
      similar: st.sim ? st.sim.total : null,
      quarantine: st.batches ? st.batches.filter(function (b) { return b.state === "quarantined"; }).length : null,
    };
    return '<div class="cl-seg" role="tablist">' + TABS.map(function (t) {
      var c = counts[t];
      return '<button class="cl-segb' + (st.tab === t ? " on" : "") + '" role="tab" aria-selected="' + (st.tab === t) + '" data-act="tab" data-tab="' + t + '">' +
        ic(TAB_ICON[t]) + esc(tw(TAB_KEY[t])) + (c ? ' <span class="cl-count">' + fmtInt(c) + "</span>" : "") + "</button>";
    }).join("") + "</div>";
  }

  function overviewHtml(ov) {
    if (!ov) return '<div class="cl-muted">' + esc(tw("common.loading")) + "</div>";
    if (!ov.files) return '<div class="cl-empty">' + ic("search") + "<span>" + esc(tw("cl.empty_index")) + "</span></div>";
    var tiles = [
      [tw("cl.tile.files"), fmtInt(ov.files)], [tw("cl.tile.size"), fmtSize(ov.bytes)],
      [tw("cl.tile.groups"), fmtInt(ov.dup_groups)], [tw("cl.tile.wasted"), fmtSize(ov.dup_wasted)],
    ].map(function (x, i) {
      return '<div class="cl-tile' + (i === 3 && ov.dup_wasted ? " warn" : "") + '"><div class="cl-muted">' + esc(x[0]) + '</div><div class="cl-big">' + esc(x[1]) + "</div></div>";
    }).join("");
    var max = Math.max.apply(null, (ov.categories || []).map(function (c) { return c.bytes; }).concat([1]));
    var cats = (ov.categories || []).map(function (c) {
      return '<div class="cl-bar-row"><span class="cl-bar-l">' + esc(tw(CAT_KEY[c.category] || "cl.cat.other")) + '</span><span class="cl-bar"><i style="width:' +
        Math.max(1, Math.round(c.bytes / max * 100)) + '%"></i></span><span class="cl-bar-v">' + esc(fmtSize(c.bytes)) + '</span></div>';
    }).join("");
    var list = function (rows) {
      return '<ul class="cl-list">' + rows.map(function (r) {
        return '<li><span class="cl-path">' + esc(r.path) + '</span><b>' + esc(fmtSize(r.bytes != null ? r.bytes : r.size)) + "</b></li>";
      }).join("") + "</ul>";
    };
    var roots = (ov.roots || []).map(function (r) {
      return '<span class="cl-chip">' + esc(r.root) + " · " + esc(fmtTime(r.scanned_at)) + "</span>";
    }).join("");
    return '<div class="cl-tiles">' + tiles + "</div>" +
      (roots ? '<div class="cl-roots">' + roots + "</div>" : "") +
      '<div class="cl-2col"><div class="cl-card"><div class="cl-h">' + esc(tw("cl.by_type")) + "</div>" + cats + "</div>" +
      '<div class="cl-card"><div class="cl-h">' + esc(tw("cl.heavy_folders")) + "</div>" + list(ov.folders || []) + "</div></div>" +
      '<div class="cl-card"><div class="cl-h">' + esc(tw("cl.big_files")) + "</div>" + list(ov.biggest || []) + "</div>";
  }

  function selBar(st, groups, similar) {
    var info = selectionInfo(groups, st.sel, similar);
    return '<div class="cl-selbar">' +
      '<button class="cl-btn" data-act="' + (similar ? "simsuggest" : "suggest") + '">' + ic("sparkles") + esc(tw("cl.pick_suggested")) + "</button>" +
      '<button class="cl-btn" data-act="clearsel">' + esc(tw("cl.clear")) + "</button>" +
      '<span class="cl-sp"></span>' +
      '<span class="cl-selinfo">' + esc(tw("cl.selected", { n: fmtInt(info.count), size: fmtSize(info.bytes) })) + "</span>" +
      '<button class="cl-btn pri" data-act="quarantine" data-similar="' + (similar ? 1 : 0) + '"' + (info.count ? "" : " disabled") + ">" +
      ic("shield") + esc(tw("cl.to_quarantine")) + "</button></div>";
  }

  function dupsHtml(st) {
    var d = st.dups;
    if (!d) return '<div class="cl-muted">' + esc(tw("common.loading")) + "</div>";
    var filt = '<div class="cl-row">' + '<span class="cl-muted">' + esc(tw("cl.min_size")) + "</span>" + MIN_KB.map(function (k) {
      return '<button class="cl-chipb' + (st.minKb === k ? " on" : "") + '" data-act="minkb" data-kb="' + k + '">' + esc(k ? fmtSize(k * 1024) : tw("cl.all")) + "</button>";
    }).join("") + '<span class="cl-sp"></span><span class="cl-muted">' + esc(tw("cl.dup_total", { n: fmtInt(d.total), size: fmtSize(d.wasted) })) + "</span></div>";
    if (!d.groups.length) return filt + '<div class="cl-empty">' + ic("check") + "<span>" + esc(tw("cl.no_dups")) + "</span></div>";
    var groups = d.groups.map(function (g) {
      var rows = [g.keep].concat(g.copies).map(function (p) {
        var keep = p === g.keep;
        return '<label class="cl-file' + (st.sel[p] ? " on" : "") + '"><input type="checkbox" data-role="sel" data-path="' + esc(p) + '"' + (st.sel[p] ? " checked" : "") + ">" +
          '<span class="cl-path">' + esc(p) + "</span>" + (keep ? '<span class="cl-chip ok">' + esc(tw("cl.keep")) + "</span>" : "") + "</label>";
      }).join("");
      return '<div class="cl-card cl-group"><div class="cl-gh"><b>' + esc(baseName(g.keep)) + '</b><span class="cl-muted">' +
        esc(tw("cl.group_meta", { n: g.count, size: fmtSize(g.size), wasted: fmtSize(g.wasted) })) + "</span></div>" + rows + "</div>";
    }).join("");
    var more = d.groups.length < d.total ? '<button class="cl-btn cl-more" data-act="more">' + esc(tw("cl.more", { n: fmtInt(d.total - d.groups.length) })) + "</button>" : "";
    return filt + selBar(st, d.groups, false) + groups + more;
  }

  function similarHtml(st) {
    var s = st.sim;
    if (!s) return '<div class="cl-muted">' + esc(tw("common.loading")) + "</div>";
    if (s.pillow === false) return '<div class="cl-empty">' + ic("image") + "<span>" + esc(tw("cl.no_pillow")) + "</span></div>";
    if (!s.groups.length) return '<div class="cl-empty">' + ic("check") + "<span>" + esc(tw("cl.no_similar")) + "</span></div>";
    var note = '<div class="cl-row"><span class="cl-muted">' + esc(tw("cl.sim_total", { n: fmtInt(s.total) })) + "</span>" +
      infoPair("<p>" + esc(tw("cl.help.similar")) + "</p>", tw("cl.help.label")) + "</div>";
    var groups = s.groups.map(function (g) {
      var cells = g.files.map(function (f) {
        var keep = f.path === g.keep;
        return '<label class="cl-thumb' + (st.sel[f.path] ? " on" : "") + '"><img loading="lazy" alt="" src="/filescan/thumb?path=' + encodeURIComponent(f.path) + '">' +
          '<span class="cl-thumb-m"><input type="checkbox" data-role="sel" data-path="' + esc(f.path) + '"' + (st.sel[f.path] ? " checked" : "") + ">" +
          esc(f.w + "x" + f.h) + " · " + esc(fmtSize(f.size)) + (keep ? ' <span class="cl-chip ok">' + esc(tw("cl.keep")) + "</span>" : "") + "</span>" +
          '<span class="cl-path cl-muted" title="' + esc(f.path) + '">' + esc(f.path) + "</span></label>";
      }).join("");
      return '<div class="cl-card cl-group"><div class="cl-gh"><b>' + esc(tw("cl.sim_group", { n: g.count })) + "</b>" +
        '<span class="cl-muted">' + esc(tw("cl.sim_extra", { size: fmtSize(g.bytes) })) + "</span></div>" +
        '<div class="cl-thumbs">' + cells + "</div></div>";
    }).join("");
    var more = s.groups.length < s.total ? '<button class="cl-btn cl-more" data-act="simmore">' + esc(tw("cl.more", { n: fmtInt(s.total - s.groups.length) })) + "</button>" : "";
    return note + selBar(st, s.groups, true) + groups + more;
  }

  function quarantineHtml(st) {
    var bs = st.batches;
    if (!bs) return '<div class="cl-muted">' + esc(tw("common.loading")) + "</div>";
    if (!bs.length) return '<div class="cl-empty">' + ic("shield") + "<span>" + esc(tw("cl.no_batches")) + "</span></div>";
    var help = '<div class="cl-row">' + infoPair("<p>" + esc(tw("cl.help.quarantine")) + "</p>", tw("cl.help.label")) + "</div>";
    return help + bs.map(function (b) {
      var live = b.state === "quarantined";
      var items = (b.items || []).slice(0, 200).map(function (it) {
        return '<li><span class="cl-path">' + esc(it.src) + "</span><b>" + esc(fmtSize(it.size)) + "</b></li>";
      }).join("");
      return '<div class="cl-card cl-batch"><div class="cl-gh"><b>' + esc(fmtTime(b.at)) + "</b>" +
        '<span class="cl-chip' + (live ? " warn" : "") + '">' + esc(tw(STATE_KEY[b.state] || "cl.state.quarantined")) + "</span>" +
        '<span class="cl-muted">' + esc(tw("cl.batch_meta", { n: fmtInt(b.files), size: fmtSize(b.bytes) })) + "</span>" +
        (b.note ? '<span class="cl-muted">' + esc(b.note) + "</span>" : "") + '<span class="cl-sp"></span>' +
        (live ? '<button class="cl-btn" data-act="restore" data-batch="' + esc(b.id) + '">' + ic("undo-2") + esc(tw("cl.restore")) + "</button>" +
          '<button class="cl-btn danger" data-act="purge" data-batch="' + esc(b.id) + '">' + ic("trash-2") + esc(tw("cl.purge")) + "</button>" : "") +
        "</div>" + (items ? '<details><summary>' + esc(tw("cl.batch_files")) + '</summary><ul class="cl-list">' + items + "</ul></details>" : "") + "</div>";
    }).join("");
  }

  function pageHtml(st) {
    var body = st.tab === "dups" ? dupsHtml(st) : st.tab === "similar" ? similarHtml(st)
      : st.tab === "quarantine" ? quarantineHtml(st) : overviewHtml(st.overview);
    return '<div class="cl-root">' + scanBar(st) + tabsHtml(st) + '<div class="cl-main">' + body + "</div></div>";
  }

  // ---------- data + events ----------
  var _el = null, _st = null, _poll = null;

  function getJson(url) {
    return fetch(url).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  }
  function postJson(url, body) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })
      .then(function (r) { return r.json(); });
  }
  function render() {
    if (!_el || !_st) return;
    var inp = _el.querySelector('[data-role="path"]');
    var typed = inp ? inp.value : "";
    _el.innerHTML = pageHtml(_st);
    var again = _el.querySelector('[data-role="path"]');
    if (again && typed) again.value = typed;
  }
  function savePref() {
    try { localStorage.setItem(PREF_KEY, JSON.stringify({ tab: _st.tab, roots: _st.roots, images: _st.images, minKb: _st.minKb })); } catch (e) {}
  }
  function readPref() {
    try { return JSON.parse(localStorage.getItem(PREF_KEY) || "{}") || {}; } catch (e) { return {}; }
  }
  function loadOverview() {
    return getJson("/filescan/overview").then(function (d) { if (_st) { _st.overview = d; render(); } }).catch(function () {});
  }
  function loadDups(append) {
    var off = append && _st.dups ? _st.dups.groups.length : 0;
    return getJson("/filescan/duplicates?min_kb=" + _st.minKb + "&limit=" + PAGE + "&offset=" + off).then(function (d) {
      if (!_st) return;
      if (append && _st.dups) { _st.dups.groups = _st.dups.groups.concat(d.groups); _st.dups.total = d.total; }
      else _st.dups = d;
      render();
    }).catch(function () {});
  }
  function loadSimilar(append) {
    var off = append && _st.sim ? _st.sim.groups.length : 0;
    return getJson("/filescan/similar?limit=30&offset=" + off).then(function (d) {
      if (!_st) return;
      if (append && _st.sim) { _st.sim.groups = _st.sim.groups.concat(d.groups); _st.sim.total = d.total; }
      else _st.sim = d;
      render();
    }).catch(function () {});
  }
  function loadBatches() {
    return getJson("/filescan/quarantine").then(function (d) { if (_st) { _st.batches = d.batches || []; render(); } }).catch(function () {});
  }
  function loadTab() {
    if (_st.tab === "dups") return loadDups(false);
    if (_st.tab === "similar") return loadSimilar(false);
    if (_st.tab === "quarantine") return loadBatches();
    return loadOverview();
  }
  function refreshAll() {
    _st.dups = null; _st.sim = null;
    loadOverview(); loadBatches();
    if (_st.tab === "dups") loadDups(false);
    if (_st.tab === "similar" || _st.tab === "overview") loadSimilar(false);
  }
  function pollStatus() {
    return getJson("/filescan/status").then(function (s) {
      if (!_st) return;
      var was = _st.status && _st.status.running;
      _st.status = s;
      if (s.running && !_poll) _poll = setInterval(pollStatus, POLL_MS);
      if (!s.running && _poll) { clearInterval(_poll); _poll = null; }
      if (was && !s.running) refreshAll();
      render();
    }).catch(function () {});
  }

  function onClick(e) {
    var b = e.target.closest("[data-act]");
    if (!b || !_el.contains(b) || b.disabled) return;
    var act = b.getAttribute("data-act");
    if (act === "tab") { _st.tab = b.getAttribute("data-tab"); _st.msg = ""; savePref(); render(); loadTab(); return; }
    if (act === "drive") {
      var p = b.getAttribute("data-path");
      var i = _st.roots.indexOf(p);
      if (i >= 0) _st.roots.splice(i, 1); else _st.roots.push(p);
      savePref(); render(); return;
    }
    if (act === "addpath") {
      var inp = _el.querySelector('[data-role="path"]');
      var v = inp ? inp.value.trim() : "";
      if (v && _st.roots.indexOf(v) < 0) _st.roots.push(v);
      if (inp) inp.value = "";
      savePref(); render(); return;
    }
    if (act === "scan") {
      _st.msg = "";
      postJson("/filescan/scan", { roots: _st.roots, images: _st.images }).then(function (d) {
        if (!d.ok) { _st.msg = d.message || ""; render(); return; }
        _st.status = Object.assign({}, d, { running: true });
        render(); pollStatus();
      });
      return;
    }
    if (act === "cancel") { postJson("/filescan/cancel").then(pollStatus); return; }
    if (act === "minkb") { _st.minKb = +b.getAttribute("data-kb") || 0; savePref(); _st.dups = null; render(); loadDups(false); return; }
    if (act === "more") { loadDups(true); return; }
    if (act === "simmore") { loadSimilar(true); return; }
    if (act === "suggest") { suggestedDups(_st.dups ? _st.dups.groups : []).forEach(function (p) { _st.sel[p] = true; }); render(); return; }
    if (act === "simsuggest") {
      (_st.sim ? _st.sim.groups : []).forEach(function (g) { suggestedSimilar(g).forEach(function (p) { _st.sel[p] = true; }); });
      render(); return;
    }
    if (act === "clearsel") { _st.sel = {}; render(); return; }
    if (act === "quarantine") {
      var similar = b.getAttribute("data-similar") === "1";
      var groups = similar ? (_st.sim ? _st.sim.groups : []) : (_st.dups ? _st.dups.groups : []);
      var info = selectionInfo(groups, _st.sel, similar);
      var ask = tw("cl.confirm_q", { n: fmtInt(info.count), size: fmtSize(info.bytes) });
      if (info.unsafe) ask += "\n" + tw("cl.confirm_unsafe", { n: info.unsafe });
      if (!confirm(ask)) return;
      var paths = Object.keys(_st.sel).filter(function (k) { return _st.sel[k]; });
      b.disabled = true;
      postJson("/filescan/quarantine", { paths: paths, similar: similar }).then(function (d) {
        if (!d.ok) { _st.msg = d.message || ""; render(); return; }
        var lines = [tw("cl.done_q", { n: fmtInt((d.moved || []).length), size: fmtSize(d.bytes) })];
        (d.refused || []).slice(0, 5).forEach(function (r) { lines.push(baseName(r.path) + ": " + tw(REFUSED_KEY[r.reason] || "cl.refused.os_error")); });
        if ((d.refused || []).length > 5) lines.push(tw("cl.refused_more", { n: d.refused.length - 5 }));
        _st.msg = lines.join(" · ");
        _st.sel = {};
        refreshAll();
      });
      return;
    }
    if (act === "restore") {
      postJson("/filescan/restore", { batch: b.getAttribute("data-batch") }).then(function (d) {
        _st.msg = d.ok ? tw("cl.done_restore", { n: fmtInt((d.restored || []).length) }) + ((d.kept || []).length ? " · " + tw("cl.kept", { n: d.kept.length }) : "") : (d.message || "");
        refreshAll();
      });
      return;
    }
    if (act === "purge") {
      if (!confirm(tw("cl.confirm_purge"))) return;
      postJson("/filescan/purge", { batch: b.getAttribute("data-batch") }).then(function (d) {
        _st.msg = d.ok ? tw("cl.done_purge", { n: fmtInt(d.deleted), size: fmtSize(d.bytes) }) : (d.message || "");
        refreshAll();
      });
    }
  }
  function onChange(e) {
    var t = e.target;
    if (!t || !t.getAttribute) return;
    var role = t.getAttribute("data-role");
    if (role === "sel") {
      // Update only the row and the selection bar: a full redraw would reload every thumbnail.
      _st.sel[t.getAttribute("data-path")] = t.checked;
      var row = t.closest(".cl-file, .cl-thumb");
      if (row) row.classList.toggle("on", t.checked);
      var bar = _el.querySelector(".cl-selbar");
      var similar = _st.tab === "similar";
      var groups = similar ? (_st.sim ? _st.sim.groups : []) : (_st.dups ? _st.dups.groups : []);
      if (bar) bar.outerHTML = selBar(_st, groups, similar);
    }
    else if (role === "images") { _st.images = t.checked; savePref(); }
  }
  function onKey(e) {
    if (e.key === "Enter" && e.target && e.target.getAttribute && e.target.getAttribute("data-role") === "path") {
      var add = _el.querySelector('[data-act="addpath"]');
      if (add) add.click();
    }
  }

  function mount(el) {
    _el = el;
    var pref = readPref();
    _st = { tab: TABS.indexOf(pref.tab) >= 0 ? pref.tab : "overview", roots: Array.isArray(pref.roots) ? pref.roots : [],
      images: pref.images !== false, minKb: MIN_KB.indexOf(+pref.minKb) >= 0 ? +pref.minKb : 0,
      drives: [], status: null, overview: null, dups: null, sim: null, batches: null, sel: {}, msg: "" };
    el.addEventListener("click", onClick);
    el.addEventListener("change", onChange);
    el.addEventListener("keydown", onKey);
    render();
    getJson("/filescan/drives").then(function (d) { if (_st) { _st.drives = d.drives || []; render(); } }).catch(function () {});
    pollStatus();
    loadBatches();
    loadSimilar(false);
    return loadTab();
  }
  function unmount() {
    if (_poll) { clearInterval(_poll); _poll = null; }
    if (_el) { _el.removeEventListener("click", onClick); _el.removeEventListener("change", onChange); _el.removeEventListener("keydown", onKey); }
    _el = null; _st = null;
  }

  var api = {
    mount: mount, unmount: unmount,
    // pure helpers, for tests
    _fmtSize: fmtSize, _suggestedDups: suggestedDups, _suggestedSimilar: suggestedSimilar, _selectionInfo: selectionInfo,
    _progressText: progressText, _pageHtml: pageHtml, TABS: TABS,
  };
  if (typeof window !== "undefined") window.JavisCleanup = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
