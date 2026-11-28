// 2026-11-28 (owner): two fixes on the Partners page.
//   1. The name card shown on hover over the avatar strip no longer shows the unread number under its corner (the card
//      copied the avatar together with its unread pill).
//   2. The History and Jobs tabs of the right column show the same red dot as the partner row: History when another chat
//      of the chosen partner has unread replies, Jobs when one of its jobs waits for you or failed.
//
//     node tests/js/test_ws_rtab_dots_1128.js
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const R = path.join(__dirname, "../..");
const read = (f) => fs.readFileSync(path.join(R, f), "utf8");
const ws = read("dashboard/workspace.js");
const css = read("dashboard/console.css");
const vi = JSON.parse(read("dashboard/i18n/vi.json"));
const en = JSON.parse(read("dashboard/i18n/en.json"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

// 1. The hover card hides any unread pill it copied.
check("hover card hides the copied unread pill",
  /\.ws-mini-tip \.notification-badge, \.ws-mini-tip \.ws-av-unread[^{]*\{ display: none !important; \}/.test(css));

// 2. Both tabs carry a dot, drawn with the list and on a tab switch.
check("history tab has a dot", /data-rtab="lichsu"[^\n]*\n[^\n]*rtabDotHtml\("lichsu"\)/.test(ws));
check("jobs tab has a dot", /data-rtab="viec"[^\n]*\n[^\n]*rtabDotHtml\("viec"\)/.test(ws));
const ve = ws.slice(ws.indexOf("function veDanhSach()"), ws.indexOf("function veDanhSach()") + 400);
check("dots redrawn with the list (unread and job counts reload it)", ve.includes("drawRtabDots(el);"));
const ct = ws.slice(ws.indexOf("function chonTabPhai(tab)"), ws.indexOf("function chonTabPhai(tab)") + 1200);
check("dots redrawn on a tab switch", ct.includes("drawRtabDots(el);"));
check("jobs dot label in both languages", !!vi["ws.rtab_jobs_need"] && !!en["ws.rtab_jobs_need"]);

// Behaviour of the helpers, cut out of workspace.js and run against a tiny fake.
const start = ws.indexOf("  function rtabDotHtml(tab)"), end = ws.indexOf("  function unreadHidden()");
const doan = ws.slice(start, end);
const dots = { lichsu: { hidden: true, getAttribute: () => "lichsu" }, viec: { hidden: true, getAttribute: () => "viec" } };
const ctx = {
  S: { loai: "agent", jc: {}, un: {} },
  chon: { slug: "a" },
  dangChon() { return this.chon; },
  chuaDoc: (slug) => (ctx.S.un[slug] ? ctx.S.un[slug].n : 0),
  esc: (s) => String(s), t: (k) => k,
  window: { JavisAgentJobs: { statusOf: (c) => (!c ? "" : c.needs_you || c.failed ? "need" : c.running ? "run" : "") } },
};
ctx.dangChon = ctx.dangChon.bind(ctx);
vm.createContext(ctx);
vm.runInContext(doan, ctx);
const el = { querySelectorAll: () => [dots.lichsu, dots.viec] };

ctx.drawRtabDots(el);
check("nothing waiting: both dots hidden", dots.lichsu.hidden && dots.viec.hidden);
ctx.S.un.a = { n: 2 };
ctx.drawRtabDots(el);
check("unread in another chat: history dot shows", !dots.lichsu.hidden && dots.viec.hidden);
ctx.S.jc.a = { needs_you: 1 };
ctx.drawRtabDots(el);
check("a job needs you: jobs dot shows", !dots.viec.hidden);
ctx.S.jc.a = { running: 1 };
ctx.drawRtabDots(el);
check("a running job is not a red dot", dots.viec.hidden);
ctx.S.jc.a = { failed: 1 };
ctx.S.loai = "workflow";
ctx.drawRtabDots(el);
check("workflows have no jobs tab dot", dots.viec.hidden);
ctx.S.loai = "agent"; ctx.chon = null;
ctx.drawRtabDots(el);
check("no partner chosen: both dots hidden", dots.lichsu.hidden && dots.viec.hidden);
check("dot markup starts hidden and is labelled", /hidden><\/span>/.test(ctx.rtabDotHtml("viec")) && ctx.rtabDotHtml("viec").includes("ws.rtab_jobs_need"));

if (fails) { console.log("FAIL - " + fails + " check(s)"); process.exit(1); }
console.log("OK - ws rtab dots");
