/* A session that expires while the dashboard is open now brings up the sign-in screen instead of failing silently.

       node tests/js/test_session_lost_signin.js

   Reported 2026-11-10: chat images went blank on the owner's PC tab. The 30-day session had expired; chat kept working
   over the open WebSocket while every HTTP call, images included, got 401 with no visible sign. fetch-gop.js now raises
   "javis:unauthorized" on a same-origin 401 outside /auth/*, and app.js answers it with the same /auth/status check it
   already runs when the socket is refused. */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const g = require(path.join(ROOT, "dashboard/fetch-gop.js"));
const O = "http://127.0.0.1:7777";
check("401 on a chat image means the session is lost", g.isSessionLost(401, "/files/raw?path=a.png", O) === true);
check("401 on an absolute same-origin URL counts too", g.isSessionLost(401, O + "/background", O) === true);
check("401 from /auth/* is the sign-in flow itself", g.isSessionLost(401, "/auth/status", O) === false);
check("401 from another origin is not ours", g.isSessionLost(401, "https://api.example.com/x", O) === false);
check("200 is fine", g.isSessionLost(200, "/files/raw?path=a.png", O) === false);
check("403 is a permission answer, not a lost session", g.isSessionLost(403, "/files/raw", O) === false);

const src = fs.readFileSync(path.join(ROOT, "dashboard/fetch-gop.js"), "utf8");
check("fetch-gop raises javis:unauthorized", /dispatchEvent\(new Event\("javis:unauthorized"\)\)/.test(src));
check("both fetch paths report it", (src.match(/reportSessionLost\(input, r\);/g) || []).length === 2);
const app = fs.readFileSync(path.join(ROOT, "dashboard/app.js"), "utf8");
check("app.js answers it with the throttled sign-in check",
  /addEventListener\("javis:unauthorized", \(\) => \{ _checkLoginAfterRefusal\(\); \}\)/.test(app));
const html = fs.readFileSync(path.join(ROOT, "dashboard/index.html"), "utf8");
check("index.html cache-busts fetch-gop.js", /fetch-gop\.js\?v=2"/.test(html));

if (fails.length) { console.error(fails.length + " check(s) failed"); process.exit(1); }
console.log("all ok");
