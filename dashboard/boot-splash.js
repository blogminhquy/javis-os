/* boot-splash.js - the start-up screen (2026-11-09).

   Owner: "ngay khi khởi động nếu làm một màn hình load đang khởi động đến khi nào toàn bộ giao diện load xong thì sẽ rất
   hợp lý cho trải nghiệm". The splash (#bootSplash) is plain HTML at the top of <body>, so it is on screen from the very
   first paint, before any script runs. This file takes it away once the app is really usable:

   - console.js calls JavisBoot.pageStarted() right after it opened the first page;
   - from then on the splash waits until no "Loading..." line (.pg-loading) is visible anywhere on the page: the page has
     its own data, not only its frame;
   - that wait is capped at DATA_MAX_MS (2026-11-12). A machine whose lists take long used to sit behind the splash for
     the whole MAX_MS and read it as "Javis loads slowly"; now the app shows after a few seconds and the slow list keeps
     its own "Loading..." line, as it does on every later page;
   - it never stays longer than MAX_MS, whatever happens (a script error, a page that never starts).

   Speed of the hand-over (2026-11-12, measured on a local server: data ready at 0.29 s, splash gone at 0.70 s): the page
   is checked every CHECK_MS and the splash goes after QUIET_MS without a loader (was 120 ms checks, two in a row), and
   the fade takes FADE_MS (was 250 ms; console.css carries the same number).

   When the server started less than JUST_STARTED_S ago (an update, a restart: `up` in the javis-fresh block), a second
   line says the first open takes a little longer: the server is still warming up. Pure helpers are exported for tests. */
(function () {
  "use strict";

  var MAX_MS = 12000;          // the splash never hides the app longer than this
  var DATA_MAX_MS = 4000;      // once the first page is open, its data gets this long before the app shows anyway
  var CHECK_MS = 40;           // how often the page is checked for a visible "Loading..." line
  var QUIET_MS = 80;           // this long with no visible loader before the splash goes (two lists loading in a row)
  var FADE_MS = 150;           // the fade, same as the transition of .boot-splash in console.css
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

  // Should the splash go now? `startedAt` is when the first page opened (0 = not yet), `quietSince` is since when no
  // loader has been visible (0 = one is visible right now). All three are milliseconds on the same clock.
  function shouldHide(now, startedAt, quietSince) {
    if (!startedAt) return false;
    if (now - startedAt >= DATA_MAX_MS) return true;
    return !!quietSince && now - quietSince >= QUIET_MS;
  }

  var api = { loaderVisible: loaderVisible, justStarted: justStarted, shouldHide: shouldHide, MAX_MS: MAX_MS,
              DATA_MAX_MS: DATA_MAX_MS, QUIET_MS: QUIET_MS, FADE_MS: FADE_MS, JUST_STARTED_S: JUST_STARTED_S };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window === "undefined" || typeof document === "undefined") return;

  var el = document.getElementById("bootSplash");
  var done = !el, startedAt = 0, quietSince = 0, timer = 0;

  function hide() {
    if (done) return;
    done = true;
    clearInterval(timer);
    el.classList.add("boot-out");
    el.setAttribute("aria-busy", "false");
    setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, FADE_MS + 10);
  }

  function check() {
    if (done || !startedAt) return;
    var now = Date.now();
    if (loaderVisible(document.querySelectorAll(".pg-loading"))) quietSince = 0;
    else if (!quietSince) quietSince = now;
    if (shouldHide(now, startedAt, quietSince)) hide();
  }

  api.pageStarted = function () {
    if (done || startedAt) return;
    startedAt = Date.now();
    check();                   // the quiet time counts from now when the page opened with nothing to load
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
