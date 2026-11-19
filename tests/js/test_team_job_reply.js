// 19/11/2026: a "Waiting for you" job can be answered, not only retried (dashboard/teams.js blockedCardHtml).
//
//     python tests/run.py --js team_job_reply -v
//
// The owner: "một số việc chờ như này không hỏi lại được cũng không tương tác được để làm rõ yêu cầu", "nó chỉ có nút thử
// lại thôi mà thử lại không được thì chỉ có ấn X để tắt thôi, phải tương tác phản hồi và trao đổi lại được".
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const TM = require(path.join(ROOT, "dashboard", "teams.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const src = fs.readFileSync(path.join(ROOT, "dashboard", "teams.js"), "utf8");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 900)));
  if (!cond) fails++;
}

const members = [{ agent_key: "ag_an", slug: "an", name: "An" }, { agent_key: "ag_vy", slug: "vy", name: "Vy" },
  { agent_key: "ag_old", slug: "old", name: "Cũ", status: "left" }];
const steps = [{ agent_key: "ag_an", kind: "plan", status: "done", brief: "Chia việc" },
  { agent_key: "ag_vy", kind: "work", status: "failed", brief: "Kiểm chứng bài" }];
const job = { id: "t_1", title: "Viết 2 bài", block_kind: "failed", block_reason: "Vy báo bước chưa làm được: chưa có <v2>", steps: steps };
const view = { members: members, leaderKey: "ag_an" };

// ───────────── the card ─────────────
let h = TM.queueHtml({ blocked: [job] }, view);
check("a stopped step: Reply sits next to Retry", /data-jr-open="t_1"/.test(h) && /data-unblock="t_1" data-action="retry"/.test(h)
  && h.indexOf("data-jr-open") < h.indexOf("data-unblock") && h.includes(vi["teams.jr.reply"]), h);
check("the box is closed until Reply is pressed", !h.includes("tm-jr-rp") && /data-jr-open="t_1" aria-expanded="false"/.test(h), h);
["no_progress", "interrupted", "auto_retry"].forEach(function (k) {
  check("Reply on a " + k + " stop too", /data-jr-open="t_1"/.test(TM.queueHtml({ blocked: [Object.assign({}, job, { block_kind: k })] }, view)));
});
["cap_reached", "waiting_user", "acceptance_review", "rejected", "no_leader"].forEach(function (k) {
  check("no Reply on " + k + " (its own button decides)",
    !/data-jr-open/.test(TM.queueHtml({ blocked: [Object.assign({}, job, { block_kind: k })] }, view)));
});
check("canAnswer follows the same list", TM.canAnswer(job) && !TM.canAnswer({ block_kind: "cap_reached" }) && TM.canAnswer({}));

const open = Object.assign({ reply: { id: "t_1", mode: "answer" } }, view);
h = TM.queueHtml({ blocked: [job] }, open);
check("open: one box under the reason, the Reply button shows it is open",
  (h.match(/class="tm-ap-rp tm-jr-rp"/g) || []).length === 1 && /data-jr-rp="t_1"/.test(h) && /data-jr-open="t_1" aria-expanded="true"/.test(h)
  && h.indexOf("tm-jb-why") < h.indexOf("tm-jr-rp"), h);
check("open: two modes, Answer chosen", /data-jr-mode="answer"/.test(h) && /data-jr-mode="ask"/.test(h)
  && /aria-checked="true" data-jr-mode="answer"/.test(h) && /aria-checked="false" data-jr-mode="ask"/.test(h), h);
check("open: the placeholder names the member whose step stopped",
  h.includes(vi["teams.jr.ph_answer"].replace("{name}", "Vy")), h);
check("open: its own textarea class (the approval box handlers never see it)", h.includes('class="tm-jr-ta"') && !h.includes("tm-ap-ta"), h);
check("open: Send answers, Cancel closes", /data-jr-send="answer" data-jr-task="t_1"/.test(h) && /class="ws-btn tm-ap-cancel" data-jr-open=""/.test(h), h);
check("open: suggestions of the mode", h.includes(vi["teams.jr.sug_skip"]) && !h.includes(vi["teams.jr.sug_need"]), h);
h = TM.queueHtml({ blocked: [job] }, Object.assign({ reply: { id: "t_1", mode: "ask" } }, view));
check("ask mode: its placeholder, suggestions and send", /data-jr-send="ask"/.test(h) && h.includes(vi["teams.jr.sug_need"])
  && h.includes(vi["teams.jr.ph_ask"].replace("{name}", "Vy")), h);
h = TM.queueHtml({ blocked: [job, Object.assign({}, job, { id: "t_2" })] }, open);
check("only the card being answered has a box", (h.match(/tm-jr-rp"/g) || []).length === 1 && /data-jr-rp="t_1"/.test(h), h);
h = TM.queueHtml({ blocked: [Object.assign({}, job, { steps: [] })] }, open);
check("no step listed: the placeholder still reads well", h.includes(vi["teams.jr.ph_answer"].replace("{name}", vi["teams.jr.member"])), h);

// ───────────── the pill above the composer ─────────────
const strip = TM.jobStripHtml({ blocked: [job] }, members, { open: true });
check("the pill's details: Reply next to Retry", /data-jr-open="t_1"/.test(strip) && /data-unblock="t_1"/.test(strip), strip);

// ───────────── what Send posts ─────────────
let p = TM.jobReplyPayload(job, "answer", "Dùng bản v1, bỏ qua kiểm chứng v2", members, "c1");
check("answer: the job's answer route, the words and the client id", p.mode === "answer" && p.path === "/tasks/t_1/answer"
  && p.body.answer === "Dùng bản v1, bỏ qua kiểm chứng v2" && p.body.client_msg_id === "c1", p);
check("answer: the chat text quotes why it stopped, then the words", /^> /.test(p.body.text)
  && p.body.text.includes("chưa có <v2>") && p.body.text.includes("Viết 2 bài") && /\n\nDùng bản v1, bỏ qua kiểm chứng v2$/.test(p.body.text), p.body.text);
p = TM.jobReplyPayload(Object.assign({}, job, { id: "a b" }), "answer", "x", members, "c");
check("answer: the job id is encoded in the path", p.path === "/tasks/a%20b/answer", p.path);
p = TM.jobReplyPayload(job, "ask", "Cần gì để làm tiếp?", members, "c2");
check("ask: a chat message to the member whose step stopped, not a job", p.mode === "ask" && p.path === "/messages"
  && JSON.stringify(p.body.mentions) === '["ag_vy"]' && p.body.as_job === false && p.body.client_msg_id === "c2"
  && /^> /.test(p.body.text) && /Cần gì để làm tiếp\?$/.test(p.body.text), p);
p = TM.jobReplyPayload(Object.assign({}, job, { steps: [{ agent_key: "ag_old", status: "failed" }] }), "ask", "?", members, "c3");
check("ask: that member left, the message goes to the leader (no @)", JSON.stringify(p.body.mentions) === "[]", p);

// ───────────── words, look, wiring ─────────────
const keys = ["teams.jr.reply", "teams.jr.mode_answer", "teams.jr.mode_ask", "teams.jr.ph_answer", "teams.jr.ph_ask", "teams.jr.member",
  "teams.jr.send_answer", "teams.jr.send_ask", "teams.jr.sug_skip", "teams.jr.sug_current", "teams.jr.sug_simpler", "teams.jr.sug_need",
  "teams.jr.sug_where", "teams.jr.sug_other", "teams.jr.quote", "teams.jr.asked", "teams.jr.answered"];
check("every word in Vietnamese and English", keys.every((k) => vi[k] && en[k]), keys.filter((k) => !vi[k] || !en[k]));
check("no long dash in the new words", keys.every((k) => !/[–—]/.test(vi[k] + en[k])));
check("textarea 16px like the approval box (no iPhone zoom)", /\.tm-jr-ta, \.tm-ap-ta \{[^}]*font-size: 16px/.test(css));
check("two modes, two equal columns", /\.tm-jr-seg \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); \}/.test(css));
check("Reply and Retry sit in one row with a gap", /\.tm-jb-go, \.tm-sr-go \{ display: flex; flex-wrap: wrap; gap: 8px; \}/.test(css));
check("Ctrl+Enter sends and Escape closes the box", /contains\("tm-jr-ta"\)\) \{\s*if \(e\.key === "Escape"\)/.test(src));
check("the draft is kept while typing and comes back after a redraw",
  /contains\("tm-jr-ta"\)\) \{ JOB_REPLY\.draft = e\.target\.value;/.test(src) && /hydrate\(side\);\s*jrRestore\(false\);/.test(src));
check("Send posts to the payload's path", /call\("POST", teamUrl\(p\.path\), p\.body\)/.test(src));
check("a press on Reply in the pill closes the pill", /t\.dataset\.openJobs \|\| t\.dataset\.viewTask \|\| t\.dataset\.jrOpen/.test(src));

if (fails) { console.log(fails + " failed"); process.exit(1); }
console.log("all ok");
