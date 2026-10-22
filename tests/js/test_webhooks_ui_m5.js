// 0.274.0: webhook operations on the Work page (webhook platform M5): the Rules panel holds the notification mode,
// limits, AI budget and retention; the card log has a filter and an Export link; an open breaker is announced on the
// card; both languages carry every new string.
const path = require("path");
const fs = require("fs");
const W = require(path.join(__dirname, "../../dashboard/webhooks.js"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

const s = W.settingsHtml({ notify: "daily_digest", limits: { per_hour: 40, per_day: 0, backlog: 6 }, ai_per_day: 7, retention_days: 60 });
check("settings: the four modes, the current one selected", (s.match(/<option/g) || []).length === 4
  && s.includes('value="daily_digest" selected'));
check("settings: limits, AI budget and retention prefilled", s.includes('class="whPerHour"') && s.includes('value="40"')
  && s.includes('class="whAiDay"') && s.includes('value="7"') && s.includes('value="60"'));
check("settings: number inputs are 16px (readable on a phone)", (s.match(/font-size:16px/g) || []).length >= 6);
const card = W.cardHtml({ id: "wh_1", name: "Đơn", target: "task", text: "x", level: "full", brain: "/b", url: "/hooks/wh_1",
  enabled: true, history: [{ run_id: "ev_1", at: 1, status: "done" }],
  breakers: [{ action: "crm", open_until: Date.now() / 1000 + 600, fails: 0 }] }, []);
check("card: log filter and export link for this hook", card.includes("whFilter") && card.includes('value="needs_you"')
  && card.includes("/webhooks/events/export?hook=wh_1&format=csv"));
check("card: an open breaker is announced with the action name", card.includes("wh.breaker_open"));
const closed = W.cardHtml({ id: "wh_2", name: "x", target: "task", text: "x", level: "full", brain: "/b", url: "/hooks/wh_2",
  enabled: true, history: [{ run_id: "ev_1", at: 1, status: "done" }], breakers: [{ action: "crm", open_until: 1, fails: 2 }] }, []);
check("card: a closed breaker says nothing", !closed.includes("wh.breaker_open"));
const keys = ["wh.notify_label", "wh.notify_all", "wh.notify_errors_only", "wh.notify_daily_digest", "wh.notify_none", "wh.lim_hour",
  "wh.lim_day", "wh.lim_backlog", "wh.ai_day", "wh.keep_days", "wh.f_all", "wh.f_needs_you", "wh.f_failed", "wh.f_ran",
  "wh.f_filtered", "wh.export", "wh.breaker_open"];
for (const lang of ["vi", "en"]) {
  const t = JSON.parse(fs.readFileSync(path.join(__dirname, `../../dashboard/i18n/${lang}.json`), "utf8"));
  check(`${lang}: every new string present, no long dashes`, keys.every(k => t[k] && t[k].length && !/[–—]/.test(t[k])));
}
const js = fs.readFileSync(path.join(__dirname, "../../dashboard/webhooks.js"), "utf8");
check("Save sends the settings with the rules", js.includes("readSettings(host)"));
check("the filter pages the log with its status", js.includes('"&status=" + encodeURIComponent(status)'));

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
