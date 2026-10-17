// 0.205.0: private partner chats behave like messenger threads: the list re-sorts by the newest message, each row
// shows its unread count, and a partner's notifications can be muted for 1h, 4h, until 8:00 or until turned back on.
const fs = require("fs");
const path = require("path");
const R = path.join(__dirname, "../..");
const read = (f) => fs.readFileSync(path.join(R, f), "utf8");
const ws = read("dashboard/workspace.js");
const app = read("dashboard/app.js");
const css = read("dashboard/console.css");
const vi = JSON.parse(read("dashboard/i18n/vi.json"));
const en = JSON.parse(read("dashboard/i18n/en.json"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

check("unread read with the list, one request per brain", /loadUnread\(\)\.then\(function \(ok\) \{ if \(ok && active && S\.loai === "agent"\) veDanhSach\(\); \}\);/.test(ws)
  && ws.includes('api("/agents/unread?brain=" + encodeURIComponent(b0))'));
const lu = ws.slice(ws.indexOf("async function loadUnread()"), ws.indexOf("function henUnread()"));
check("newest message moves a partner up (re-sort)", /a\.last_chat_at = Number\(u\.last_at\)/.test(lu) && /S\.agents = sapXep\(S\.agents, "last_chat_at"\);/.test(lu));
const td = ws.slice(ws.indexOf("function onTurnDone(sid) {"), ws.indexOf("function onTurnDone(sid) {") + 900);
check("a reply just written re-sorts too", /S\.agents = sapXep\(S\.agents, "last_chat_at"\);/.test(td) && /else if \(sid && S\.loai === "agent"\) henUnread\(\);/.test(td));
check("events read the counts again", /\["javis:sessions-changed", "javis:agent-read"\]\.forEach\(function \(ev\) \{ window\.addEventListener\(ev, henUnread\); \}\);/.test(ws)
  && /data\.type === "agent_read"/.test(app));
check("opening a partner's chat reads it", /if \(S\.loai === "agent"\) daDoc\(item\.slug\);/.test(ws) && ws.includes('api("/agents/opened"'));
check("unread pill and muted mark in the corner cluster", ws.includes("gioNhanHtml(x.last_chat_at) + tinHtml(x) +"));
check("the chat on screen shows no count", /function chuaDoc\(slug\) \{ var u = S\.un\[slug\]; return u && !dangXemCongSu\(slug\)/.test(ws));
check("menu item and the four lengths", /nutMenu\("bell-off", t\("ws\.mute"\), "tb"\)/.test(ws)
  && ["1h", "4h", "8am", "forever"].every((c) => ws.includes('["' + c + '", "ws.mute_')) && ws.includes('datTat(item, "off")'));
const keys = ["ws.mute", "ws.unmute", "ws.muted", "ws.muted_until", "ws.mute_1h", "ws.mute_4h", "ws.mute_8am", "ws.mute_forever",
  "ws.unread_n", "ws.mute_err"];
check("strings in both languages", keys.every((k) => vi[k] && en[k]));
check("no long dashes in the new strings", keys.every((k) => !/[–—]/.test(vi[k] + en[k])));
check("unread rows read in full ink", css.includes(".ws-item-wrap.has-unread .ws-item-top strong"));

// tinHtml renders from the state alone (no DOM): load the module under a tiny window stub.
global.window = { addEventListener() {}, t: (k, v) => (k === "ws.unread_n" ? v.n + " unread" : k) };
global.document = { hidden: false, addEventListener() {} };
require(path.join(R, "dashboard/workspace.js"));
const W = window.JavisWorkspace;
const S = W.state();
S.un = { a: { n: 3, last_at: 1, muted_until: 0 }, b: { n: 120, last_at: 1, muted_until: -1 }, c: { n: 0, muted_until: 0 } };
const a = W.tinHtml({ slug: "a" }), b = W.tinHtml({ slug: "b" }), c = W.tinHtml({ slug: "c" });
check("count pill", /notification-badge tm-unread"[^>]*>3</.test(a) && !a.includes("tm-muted"));
check("muted: grey pill, bell-off mark, 99+", b.includes("tm-unread is-muted") && b.includes("tm-muted") && b.includes(">99+<"));
check("nothing unread draws nothing", c === "");
check("mute until turned back on reads as muted", W.tatDen({ muted_until: -1 }) === -1 && W.tatDen({ muted_until: 1 }) === 0);

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
