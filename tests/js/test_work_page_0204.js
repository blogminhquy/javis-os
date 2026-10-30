// 0.204.0: Webhooks get their own page under Work (the Scheduled page itself became the Tasks page in 0.422.0 and its
// code left console.js in 0.426.0); "Read all" in the notification panel reads both tabs and dims when done.
const fs = require("fs");
const path = require("path");
const R = path.join(__dirname, "../..");
const read = (f) => fs.readFileSync(path.join(R, f), "utf8");
const cons = read("dashboard/console.js");
const uia = read("dashboard/ui-actions.js");
const tgt = read("server/ui_targets.py");
const viec = read("dashboard/chat-viec.js");
const noti = read("dashboard/notifications.js");
const css = read("dashboard/style.css");
const vi = JSON.parse(read("dashboard/i18n/vi.json"));
const en = JSON.parse(read("dashboard/i18n/en.json"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

check("webhooks in the Work group", /ids: \["tasks", "webhooks"\]/.test(cons));
check("webhooks page has an icon, meta and a renderer",
  /webhooks: "webhook"/.test(cons) && /if \(id === "webhooks"\) return renderWebhooks\(el\);/.test(cons)
  && /"tasks", "webhooks", "chatbots"/.test(cons));
check("page lists agree (console, ui-actions, ui_targets)",
  /"tasks", "webhooks", "learn"/.test(cons) && /"tasks", "webhooks", "learn"/.test(uia) && /"tasks", "webhooks", "learn"/.test(tgt));
check("webhook cards in chat open the Webhooks page", /if \(kind === "webhook"\) return "webhooks";/.test(viec));
check("the Scheduled page no longer mounts webhooks", !/JavisWebhooks\.mount\(el\.querySelector\("#whSection"\),\s*\{ brains: \(\) => allBrains/.test(cons));
const keys = ["page.webhooks.label", "page.webhooks.sub"];
check("strings in both languages", keys.every((k) => vi[k] && en[k]));
check("no long dashes in the new strings", keys.every((k) => !/[–—]/.test(vi[k] + en[k])));

const ma = noti.slice(noti.indexOf("function markAll()"), noti.indexOf("function kindLabel"));
check("Read all reads both tabs", /docThu\(\{ all: true \}\)/.test(ma) && /guiDaDoc\(\{ all: true \}\)/.test(ma) && !/return;/.test(ma));
check("Read all is disabled when nothing is unread", /readAll\.disabled = tong === 0;/.test(noti));
check("Read all is a 14px button, dimmed when disabled", /#notificationReadAll \{[^}]*font-size: 14px/.test(css) && /#notificationReadAll \{[^}]*opacity: \.55/.test(css));
check("empty tab counts hide", /\.noti-tab-count\[hidden\] \{ display: none; \}/.test(css));

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
