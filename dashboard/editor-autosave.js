/* editor-autosave.js - every file editor saves by itself, like Google Docs (2026-11-09).

   Customer report (Star Global, 09/11/2026): while rewriting an email draft in the note editor, a stray two-finger
   swipe on the touchpad made the browser go Back, and every word typed since the last press of Save was gone. It
   happened several times in one evening. The editors only wrote the file when Save (or Ctrl+S) was pressed.

   What this module does for an open editor:
   - Writes the file about a second after typing stops (DELAY_MS). Toolbar commands that change the text without an
     input event call poke().
   - Keeps a copy of the unsaved text in this browser (localStorage) a moment after each change, so a tab closed or
     crashed before the write landed still has the words. Opening the same file again puts them back when the file
     on disk is still the one the copy was made from; a file changed since (Javis edited it) wins and the copy is
     dropped.
   - Writes once more with fetch keepalive when the page is hidden or unloaded, and asks the browser to confirm
     leaving while something is still unsaved.
   - While an editor is open, html gets the class jv-editing: style.css turns off horizontal overscroll there, which
     stops a touchpad swipe from becoming the browser's Back gesture (Chrome, Edge).

   The editor owns the actual write (save(content, {keepalive}) -> Promise<bool>) and the status display (onStatus:
   "idle", "dirty", "saving", "saved", "error"). hash and pickDraft are pure so node tests can run them. */
(function () {
  "use strict";

  var DELAY_MS = 1200;        // pause in typing before the file is written
  var DRAFT_DELAY_MS = 500;   // pause before the local copy is refreshed
  var RETRY_MS = 5000;        // a failed write is tried again after this long
  var DRAFT_PREFIX = "javis.draft.";
  var DRAFT_MAX_AGE_MS = 7 * 24 * 3600 * 1000;
  var KEEPALIVE_MAX_BYTES = 60000;   // browsers refuse a keepalive body above 64 KB

  // Short fingerprint of a text (length + FNV-1a), to tell whether the file on disk is still the one a draft was
  // made from without keeping a second copy of the whole file.
  function hash(s) {
    s = String(s == null ? "" : s);
    var h = 0x811c9dc5;
    for (var i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    return s.length + ":" + h.toString(16);
  }

  // The text to restore when a file opens: the stored draft when it was made from exactly what is on disk now, is
  // recent, and differs from it. Otherwise null.
  function pickDraft(stored, disk, now) {
    if (!stored || typeof stored.text !== "string" || typeof stored.base !== "string") return null;
    if (stored.base !== hash(disk)) return null;
    if (!(now - Number(stored.ts) < DRAFT_MAX_AGE_MS)) return null;
    if (stored.text === String(disk == null ? "" : disk)) return null;
    return stored.text;
  }

  function store() {
    try { return typeof localStorage !== "undefined" ? localStorage : null; } catch (e) { return null; }
  }
  function readDraft(key) {
    var s = store();
    if (!s || !key) return null;
    try { return JSON.parse(s.getItem(DRAFT_PREFIX + key) || "null"); } catch (e) { return null; }
  }
  function writeDraft(key, rec) {
    var s = store();
    if (!s || !key) return;
    try { s.setItem(DRAFT_PREFIX + key, JSON.stringify(rec)); } catch (e) { /* full or blocked: the server write still runs */ }
  }
  function dropDraft(key) {
    var s = store();
    if (!s || !key) return;
    try { s.removeItem(DRAFT_PREFIX + key); } catch (e) { /* ignore */ }
  }

  // Whether a body this size may go out with keepalive.
  function keepaliveOk(text) {
    try { return new Blob([String(text || "")]).size < KEEPALIVE_MAX_BYTES; } catch (e) { return String(text || "").length < KEEPALIVE_MAX_BYTES / 3; }
  }

  var live = [];   // editors open right now

  function syncPageLock() {
    try { document.documentElement.classList.toggle("jv-editing", live.length > 0); } catch (e) { /* node */ }
  }

  // o: key (brain + path), original (the file as read from disk), get() -> the text being edited,
  //    baseline (the text that counts as saved now, defaults to get()), save(content, {keepalive}) -> Promise<bool>,
  //    sources (elements whose input events mean a change), apply(text) (puts a restored draft into the editor),
  //    onStatus(state), onRestored(), delay.
  function attach(o) {
    o = o || {};
    var closed = false, timer = 0, draftTimer = 0, inflight = null, state = "";
    var base = hash(o.original);
    var saved;
    try { saved = o.baseline != null ? String(o.baseline) : String(o.get()); } catch (e) { saved = null; }

    function status(s) {
      if (s === state) return;
      state = s;
      if (o.onStatus) { try { o.onStatus(s); } catch (e) { /* display only */ } }
    }
    function current() {
      try { var c = o.get(); return c == null ? null : String(c); } catch (e) { return null; }
    }
    function isDirty() { var c = current(); return c != null && saved != null && c !== saved; }

    function keepDraft() {
      clearTimeout(draftTimer); draftTimer = 0;
      var c = current();
      if (c == null) return;
      if (c === saved) dropDraft(o.key);
      else writeDraft(o.key, { base: base, text: c, ts: Date.now() });
    }

    function write(c, keepalive) {
      status("saving");
      var p = Promise.resolve()
        .then(function () { return o.save(c, { keepalive: !!keepalive && keepaliveOk(c) }); })
        .then(function (ok) { return ok !== false; }, function () { return false; })
        .then(function (ok) {
          if (inflight === p) inflight = null;
          if (ok) {
            saved = c;
            base = hash(c);
            if (current() === c) { dropDraft(o.key); status("saved"); }
            else if (!closed) { status("dirty"); keepDraft(); schedule(DELAY_MS); }
          } else {
            status("error");
            if (!closed) { keepDraft(); schedule(RETRY_MS); }
          }
          return ok;
        });
      inflight = p;
      return p;
    }

    // Write now if anything changed. Waits for a write already on its way, then writes what is newer.
    function flush(keepalive) {
      clearTimeout(timer); timer = 0;
      if (inflight) {
        return inflight.then(function (ok) {
          var c = current();
          return c != null && c !== saved ? write(c, keepalive) : ok;
        });
      }
      var c = current();
      if (c == null || saved == null) return Promise.resolve(true);
      if (c === saved) { dropDraft(o.key); return Promise.resolve(true); }
      return write(c, keepalive);
    }

    function schedule(ms) {
      clearTimeout(timer);
      timer = setTimeout(function () { timer = 0; if (!closed) flush(false); }, ms || o.delay || DELAY_MS);
    }

    function poke() {
      if (closed) return;
      if (!isDirty()) { clearTimeout(timer); timer = 0; return; }
      status("dirty");
      clearTimeout(draftTimer);
      draftTimer = setTimeout(keepDraft, DRAFT_DELAY_MS);
      schedule(o.delay || DELAY_MS);
    }

    var sources = (o.sources || []).filter(Boolean);
    sources.forEach(function (el) { el.addEventListener("input", poke); });

    // The editor goes away (closed, another file opened): the last words are written, and kept locally until then.
    // `discard` (the file was just deleted) writes nothing and forgets the local copy, so the file is not recreated.
    function close(discard) {
      if (closed) return Promise.resolve(true);
      var dirty = !discard && isDirty();
      if (dirty) keepDraft();
      if (discard) dropDraft(o.key);
      closed = true;
      clearTimeout(timer); clearTimeout(draftTimer);
      sources.forEach(function (el) { el.removeEventListener("input", poke); });
      var i = live.indexOf(ctl);
      if (i >= 0) live.splice(i, 1);
      syncPageLock();
      if (discard || (!dirty && !inflight)) return Promise.resolve(true);
      var c = current();
      return (inflight || Promise.resolve(true)).then(function () {
        if (c == null || c === saved) return true;
        return Promise.resolve()
          .then(function () { return o.save(c, { keepalive: keepaliveOk(c) }); })
          .then(function (ok) { ok = ok !== false; if (ok) dropDraft(o.key); return ok; }, function () { return false; });
      });
    }

    var ctl = {
      flush: function () { return flush(false); },
      poke: poke,
      close: close,
      dirty: function () { return !closed && (isDirty() || !!inflight); },
      status: function () { return state; },
      // The page is going away: keep the words locally and send them with keepalive.
      leaving: function () { if (closed || !isDirty()) return; keepDraft(); flush(true); },
    };
    live.push(ctl);
    syncPageLock();
    status("idle");

    // A draft left from a tab that closed before its last write landed.
    var back = pickDraft(readDraft(o.key), o.original, Date.now());
    if (back != null && o.apply && back !== current()) {
      try {
        o.apply(back);
        if (o.onRestored) o.onRestored();
        poke();
      } catch (e) { /* the editor keeps the file as read */ }
    } else if (back == null) {
      var stale = readDraft(o.key);
      if (stale && stale.base !== hash(o.original)) dropDraft(o.key);
    }
    return ctl;
  }

  if (typeof window !== "undefined" && window.addEventListener) {
    var leaveAll = function () { live.slice().forEach(function (c) { c.leaving(); }); };
    window.addEventListener("pagehide", leaveAll);
    document.addEventListener("visibilitychange", function () { if (document.hidden) leaveAll(); });
    // Unsaved words: the browser asks before leaving (a Back swipe, a reload) while the write goes out.
    window.addEventListener("beforeunload", function (e) {
      var pending = live.some(function (c) { return c.dirty(); });
      leaveAll();
      if (pending) { e.preventDefault(); e.returnValue = ""; }
    });
  }

  var api = { attach: attach, hash: hash, pickDraft: pickDraft, DELAY_MS: DELAY_MS, DRAFT_PREFIX: DRAFT_PREFIX };
  if (typeof window !== "undefined") window.JavisAutosave = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
