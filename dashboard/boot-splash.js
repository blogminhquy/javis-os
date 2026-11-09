/* boot-splash.js - the start-up screen (2026-11-09).

   Owner: "ngay khi khởi động nếu làm một màn hình load đang khởi động đến khi nào toàn bộ giao diện load xong thì sẽ rất
   hợp lý cho trải nghiệm". The splash (#bootSplash) is plain HTML at the top of <body>, so it is on screen from the very
   first paint, before any script runs. This file takes it away once the app is really usable:

   - console.js calls JavisBoot.pageStarted() right after it opened the first page;
   - from then on the splash waits until no "Loading..." line (.pg-loading) is visible anywhere on the page: the page has
     its own data, not only its frame;
   - it never stays longer than MAX_MS, whatever happens (a script error, a page that keeps loading forever).

   When the server started less than JUST_STARTED_S ago (an update, a restart: `up` in the javis-fresh block), a second
   line says the first open takes a little longer: the server is still warming up. Pure helpers are exported for tests. */
(function () {
  "use strict";

  var MAX_MS = 12000;          // the splash never hides the app longer than this
  var CHECK_MS = 120;          // how often the page is checked for a visible "Loading..." line
  var QUIET_CHECKS = 2;        // checks in a row with no visible loader before the splash goes
  var JUST_STARTED_S = 120;

  // Is any "Loading..." line visible outside the splash? `nodes` is a list of elements.
  function loaderVisible(nodes) {
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (n.closest && n.closest("#bootSplash")) continue;
      if (n.getClientRects && n.getClientRects().length) return true;
    }
    return false;
  }

  function justStarted(fresh) {
    var up = fresh && Number(fresh.up);
    return isFinite(up) && up >= 0 && up < JUST_STARTED_S;
  }

  var api = { loaderVisible: loaderVisible, justStarted: justStarted, MAX_MS: MAX_MS, JUST_STARTED_S: JUST_STARTED_S };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window === "undefined" || typeof document === "undefined") return;

  var el = document.getElementById("bootSplash");
  var done = !el, started = false, quiet = 0, timer = 0;

  function hide() {
    if (done) return;
    done = true;
    clearInterval(timer);
    el.classList.add("boot-out");
    el.setAttribute("aria-busy", "false");
    setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 260);
  }

  function check() {
    if (done || !started) return;
    if (loaderVisible(document.querySelectorAll(".pg-loading"))) { quiet = 0; return; }
    if (++quiet >= QUIET_CHECKS) hide();
  }

  api.pageStarted = function () {
    if (done || started) return;
    started = true;
    timer = setInterval(check, CHECK_MS);
  };
  api.hide = hide;
  window.JavisBoot = api;

  if (!done) {
    setTimeout(hide, MAX_MS);
    try {
      var fresh = JSON.parse((document.getElementById("javis-fresh") || {}).textContent || "{}");
      if (justStarted(fresh)) {
        var sub = document.getElementById("bootSub");
        if (sub) sub.hidden = false;
      }
    } catch (e) { /* no fingerprint block: say nothing more */ }
  }
})();
