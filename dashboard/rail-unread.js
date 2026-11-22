// Red dot on the rail (owner, 19/11/2026): "answers of partners, chats and teams do not need a notification, a red dot on
// the menu is enough, like the dot already on chat folders". Chat, Partners and Team each get a dot while something
// there is unread; the bell keeps only what needs the owner.
//
// Counts come from the server, which already knows what is unread: GET /sessions/unread-summary (chats of the Chat page,
// partner and workflow chats) and GET /teams/unread (teams with messages since the owner last read them). Refreshed
// when the page loads, when a chat or a team changes (events app.js dispatches), when the tab comes back, and once a
// minute as a safety net.
(function () {
  var timer = null;
  var busy = false;

  function brain() {
    try { return (window.JavisSessions && window.JavisSessions.brain()) || "brain"; } catch (e) { return "brain"; }
  }
  function nav() {
    try { return (window.Alpine && window.Alpine.store && window.Alpine.store("nav")) || null; } catch (e) { return null; }
  }
  function getJson(url) {
    return fetch(url, { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }

  function refresh() {
    if (busy) return;
    var st = nav();
    if (!st) return;
    busy = true;
    var b = encodeURIComponent(brain());
    // Chats still running or open on screen are not unread yet (sessions-ui.js unreadSkipQuery, owner 2026-11-20).
    var skip = "";
    try { skip = (window.JavisChatSide && window.JavisChatSide.unreadSkipQuery && window.JavisChatSide.unreadSkipQuery()) || ""; }
    catch (e) { skip = ""; }
    Promise.all([getJson("/sessions/unread-summary?brain=" + b + skip), getJson("/teams/unread?brain=" + b)]).then(function (res) {
      busy = false;
      var s = res[0] || {}, tm = res[1] || {};
      var next = { chat: Number(s.chat) > 0, workspace: Number(s.workspace) > 0, teams: Number(tm.teams) > 0 };
      // The page on screen is being read: no dot on the very entry the owner is looking at.
      if (document.visibilityState === "visible" && st.active && next[st.active] && st.active !== "workspace" &&
          st.active !== "teams") next[st.active] = false;
      var cur = st.unread || {};
      if (cur.chat !== next.chat || cur.workspace !== next.workspace || cur.teams !== next.teams) st.unread = next;
    });
  }

  // Many events can fire for one answer: they collapse into one request.
  function soon(ms) {
    clearTimeout(timer);
    timer = setTimeout(refresh, ms == null ? 600 : ms);
  }

  ["javis:session-read", "javis:agent-read", "javis:team-event", "javis:chat-activity"].forEach(function (name) {
    window.addEventListener(name, function () { soon(); });
  });
  // A chat turn that ends can leave an unread answer the counts skipped while it ran: count again when the set of
  // running chats changes (javis:chat-turn also fires on every step, so compare the set, not the event).
  var lastRunning = "";
  window.addEventListener("javis:chat-turn", function () {
    var now = "";
    try { now = window.JavisRunning ? Array.from(window.JavisRunning).sort().join(",") : ""; } catch (e) { now = ""; }
    if (now !== lastRunning) { lastRunning = now; soon(); }
  });
  document.addEventListener("visibilitychange", function () { if (document.visibilityState === "visible") soon(200); });
  document.addEventListener("change", function (e) { if (e.target && e.target.id === "graphSource") soon(800); });
  document.addEventListener("alpine:initialized", function () { soon(300); });
  setInterval(function () { if (document.visibilityState === "visible") refresh(); }, 60000);
  soon(1500);

  window.JavisRailUnread = { refresh: refresh };
})();
