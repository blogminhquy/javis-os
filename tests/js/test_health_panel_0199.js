// 0.199.0: Work page health section. Incident rows escape model and error text; a closed incident has no button.
const path = require("path");
const H = require(path.join(__dirname, "../../dashboard/health-panel.js"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

const open = H.incidentHtml({ id: "inc_1", source: "kanban", status: "needs_you", title: "<i>Đăng bài</i>",
  message: "Cần đăng nhập lại Zalo", error: "401 <script>", count: 3, at: 1, last_at: 2 });
check("title escaped", open.includes("&lt;i&gt;Đăng bài") && !open.includes("<i>Đăng"));
check("error escaped", open.includes("401 &lt;script&gt;"));
check("open incident has Done", open.includes("hpDone") && open.includes('data-id="inc_1"'));
check("closed incident has no Done", !H.incidentHtml({ id: "x", source: "loop", status: "resolved" }).includes("hpDone"));
const issue = H.issueHtml({ count: 5, error: "zalo token expired <b>", examples: [{ source: "reminder", title: "Báo cáo" }] });
check("issue escaped with examples", issue.includes("zalo token expired &lt;b&gt;") && issue.includes("Báo cáo"));

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
