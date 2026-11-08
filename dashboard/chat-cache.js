/* chat-cache.js - the last part of recently opened chats, kept in this browser (2026-11-08).

   Owner, 2026-11-08: "load lịch sử chuyển từ hội thoại này sang hội thoại khác bị delay mấy giây". app.js already keeps
   the tail of a few chats in memory so going back to one draws at once, but that memory is empty after every reload and
   on every phone that has just woken the tab, so the first switch to each chat waited for the server again (one trip
   through Cloudflare, more while the server was busy).

   This file is the durable copy: IndexedDB, one record per chat ({id, sess, at}), at most MAX chats (the ones opened
   least recently go first), none older than MAX_AGE. app.js reads them all into its memory map at start and writes
   every fresh copy it gets. It is only ever a first paint: app.js always asks the server again and redraws when the
   answer differs.

   It holds chat text on this device, so signing out clears it (console.js), and every failure (private mode, storage
   blocked, quota) degrades to the old behaviour: nothing kept, nothing thrown. */
(function () {
  "use strict";

  var DB = "javis-chat-cache";
  var STORE = "chats";
  var MAX = 50;
  var MAX_AGE = 7 * 24 * 3600 * 1000;

  var dbp = null;

  function open() {
    if (dbp) return dbp;
    dbp = new Promise(function (ok) {
      try {
        if (typeof indexedDB === "undefined" || !indexedDB) { ok(null); return; }
        var r = indexedDB.open(DB, 1);
        r.onupgradeneeded = function () {
          var d = r.result;
          if (!d.objectStoreNames.contains(STORE)) d.createObjectStore(STORE, { keyPath: "id" });
        };
        r.onsuccess = function () { ok(r.result); };
        r.onerror = function () { ok(null); };
        r.onblocked = function () { ok(null); };
      } catch (e) { ok(null); }
    });
    return dbp;
  }

  // One transaction; resolves with fn's result (or null on any failure).
  function tx(mode, fn) {
    return open().then(function (db) {
      if (!db) return null;
      return new Promise(function (ok) {
        try {
          var t = db.transaction(STORE, mode);
          var out = { v: null };
          fn(t.objectStore(STORE), out);
          t.oncomplete = function () { ok(out.v); };
          t.onerror = function () { ok(null); };
          t.onabort = function () { ok(null); };
        } catch (e) { ok(null); }
      });
    }, function () { return null; });
  }

  // Which records to drop so that at most `max` remain, none older than `maxAge`. Pure, for the node test.
  function toDrop(records, now, max, maxAge) {
    var live = [], drop = [];
    (records || []).forEach(function (r) {
      if (!r || !r.id || !(now - (r.at || 0) <= maxAge)) drop.push(r && r.id); else live.push(r);
    });
    live.sort(function (a, b) { return (b.at || 0) - (a.at || 0); });
    live.slice(max).forEach(function (r) { drop.push(r.id); });
    return drop.filter(Boolean);
  }

  // Every kept chat, newest first: [{id, sess, at}].
  function all() {
    return tx("readonly", function (st, out) {
      var r = st.getAll();
      r.onsuccess = function () { out.v = r.result || []; };
    }).then(function (rows) {
      var now = Date.now();
      return (rows || []).filter(function (x) { return x && x.id && x.sess && now - (x.at || 0) <= MAX_AGE; })
        .sort(function (a, b) { return (b.at || 0) - (a.at || 0); });
    });
  }

  var pruneTimer = 0;
  function pruneSoon() {
    if (pruneTimer) return;
    pruneTimer = setTimeout(function () {
      pruneTimer = 0;
      tx("readwrite", function (st) {
        var r = st.getAll();
        r.onsuccess = function () {
          toDrop(r.result, Date.now(), MAX, MAX_AGE).forEach(function (id) { try { st.delete(id); } catch (e) {} });
        };
      });
    }, 2000);
  }

  function put(id, sess, at) {
    if (!id || !sess || sess.error) return Promise.resolve(null);
    return tx("readwrite", function (st) { st.put({ id: String(id), sess: sess, at: at || Date.now() }); })
      .then(function (v) { pruneSoon(); return v; });
  }

  function del(id) {
    if (!id) return Promise.resolve(null);
    return tx("readwrite", function (st) { st.delete(String(id)); });
  }

  function clear() {
    return tx("readwrite", function (st) { st.clear(); });
  }

  var api = { all: all, put: put, del: del, clear: clear, toDrop: toDrop, MAX: MAX, MAX_AGE: MAX_AGE };
  if (typeof window !== "undefined") window.JavisChatCache = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
