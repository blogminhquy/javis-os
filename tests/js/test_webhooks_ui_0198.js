// 0.198.0: Work page webhook cards. The token must never be drawn on a card (only in the one-time secret
// box), the card escapes user text, and the secret box carries a working curl line with the Bearer header.
const path = require("path");
const W = require(path.join(__dirname, "../../dashboard/webhooks.js"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

const hook = { id: "wh_1", name: "<b>Lead</b>", target: "workflow", workflow: "cham-soc", level: "auto",
  brain: "/b/shop", url: "https://x/hooks/wh_1", enabled: true, count: 2, last_at: 1, last_status: "done",
  history: [{ at: 1, status: "failed", result: "engine <timeout>" }] };
// 0.432.0: the list row (cardHtml) opens a popup (dialogHtml) that carries the URL, the runs and the actions.
const row = W.cardHtml(hook);
const html = W.dialogHtml(hook, [{ path: "/b/shop", name: "Shop" }]);
check("the list row escapes the name", row.includes("&lt;b&gt;Lead") && !row.includes("<b>Lead"));
check("the list row never carries the URL or a token", !row.includes("https://x/hooks/wh_1") && !/token/i.test(row));
check("card escapes the name", html.includes("&lt;b&gt;Lead") && !html.includes("<b>Lead"));
check("card shows the URL", html.includes("https://x/hooks/wh_1"));
check("card escapes history text", html.includes("engine &lt;timeout&gt;"));
check("card names the brain", html.includes("Shop"));
check("card has the five actions", ["whCopy", "whTest", "whToggle", "whRotate", "whDel"].every(c => html.includes(c)));
check("card never carries a token field", !/token/i.test(html));
const sec = W.secretHtml("https://x/hooks/wh_1", "tok123");
check("secret box shows the token", sec.includes("tok123"));
check("secret box gives a curl with Bearer", sec.includes("Authorization: Bearer tok123") && sec.includes("curl -X POST"));
check("task target line", W.targetLine({ target: "task", text: "Gọi lại" }).length > 0);

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
