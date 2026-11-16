// An assistant's own Auto runs in its Jobs tab (owner, 16/11/2026: the Auto block said "tự làm 1 lần" while the tab
// said "Chưa có công việc nào"). The server sends one card per run with codes; the tab reads them in words.
//
//     python tests/run.py --js agent_jobs_auto_runs -v
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const AJ = require(path.join(ROOT, "dashboard", "agent-jobs.js"));
AJ.setStrings(vi);

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 600)));
  if (!cond) fails++;
}

function run(over) {
  return Object.assign({ id: "run:7", source: "auto", source_id: "dm:k", title: "", title_code: "scan", status: "ok",
    bucket: "done", roles: [], kind: "auto_run", outcome: { code: "none" }, result: "", reason: "", next: null,
    failed: false, cancelled: false, updated_at: 1000, open: { kind: "chat", session_id: "s1" }, cancel: null,
    priority: null }, over || {});
}
const ui = { now: 1000 + 300, canVerify: true };

let h = AJ.jobHtml(run(), ui);
check("title in words, not an empty card", h.includes(">" + vi["ajobs.run.scan"] + "<") && !h.includes('title=""'), h);
check("found nothing: says so", h.includes(vi["ajobs.run.out.none"]), h);
check("Auto source, Done state, time", h.includes(vi["ajobs.src.auto"]) && h.includes(vi["ajobs.b.done"])
  && h.includes(vi["noti.ago_min"].replace("{count}", "5")), h);
check("no role chip on a self-run", !h.includes("aj-role"), h);
check("Open and Done buttons; no verify, cancel, resume or priority button",
  h.includes('data-aj-open="run:7"') && h.includes('data-aj-archive="run:7"') && !h.includes("data-aj-verify")
  && !h.includes("data-aj-cancel") && !h.includes("data-aj-resume") && !h.includes("data-aj-prio"), h);

h = AJ.jobHtml(run({ outcome: { code: "did" }, result: "Gửi báo giá cho anh Nam; Cập nhật bảng tồn kho" }), ui);
check("work it did on its own: label, then the work",
  h.includes(vi["ajobs.run.out.did"] + ": Gửi báo giá cho anh Nam; Cập nhật bảng tồn kho"), h);
h = AJ.jobHtml(run({ outcome: { code: "proposed" }, result: "Trả lời khách <b>sỉ</b>" }), ui);
check("a proposal: its title, escaped", h.includes(vi["ajobs.run.out.proposed"] + ": Trả lời khách &lt;b&gt;sỉ&lt;/b&gt;"), h);
check("each ending has its own words", ["said", "held", "enqueued"].every((c) =>
  AJ.jobHtml(run({ outcome: { code: c } }), ui).includes(vi["ajobs.run.out." + c])));
check("self-review: how many things it adjusted, or none",
  AJ.jobHtml(run({ title_code: "review", outcome: { code: "reviewed", n: 2 } }), ui)
    .includes(vi["ajobs.run.out.reviewed"].replace("{n}", "2"))
  && AJ.jobHtml(run({ title_code: "review", outcome: { code: "reviewed", n: 0 } }), ui).includes(vi["ajobs.run.out.reviewed_none"]));
check("each kind of run has its own title", ["scan", "review", "reaction_review", "judge"].every((c) =>
  AJ.titleText({ title_code: c }) === vi["ajobs.run." + c]));
check("an unknown code never shows raw", AJ.titleText({ title_code: "new_kind" }) === vi["ajobs.run.scan"]
  && AJ.outcomeText({ outcome: { code: "new_end" } }) === "");
check("a job with a real title is untouched", AJ.titleText({ title: "Viết bài" }) === "Viết bài"
  && AJ.resultText({ result: "xong" }) === "xong");

h = AJ.jobHtml(run({ status: "running", bucket: "running", outcome: null, updated_at: 1290 }), ui);
check("a run still going: In progress, no ending, no Done button",
  h.includes(vi["ajobs.b.running"]) && !h.includes("aj-result") && !h.includes("data-aj-archive"), h);
h = AJ.jobHtml(run({ status: "error", failed: true, outcome: null, reason: "TimeoutError" }), ui);
check("a run that broke: plain words, not the error class name",
  h.includes(vi["ajobs.run.failed"]) && !h.includes("TimeoutError") && h.includes(vi["ajobs.failed"]), h);
h = AJ.jobHtml(run({ open: null }), ui);
check("nothing to open: no Open button", !h.includes("data-aj-open"), h);

// The whole tab: one self-run, like the owner's assistant.
const data = { jobs: [run()], counts: { running: 0, waiting: 0, needs_you: 0, done: 1 },
  source_counts: { team: 0, chat: 0, auto: 1, workflow: 0 }, errors: [], archived: [] };
h = AJ.html(data, {});
check("the tab is not empty any more", !h.includes(vi["ajobs.empty"]) && h.includes(vi["ajobs.run.scan"]), h);
check("the source picker counts it under Auto", h.includes(vi["ajobs.srcf.auto"] + " (1)"), h);

// Archived run: title and ending in words there too.
h = AJ.archiveHtml([run({ archived_at: 5, outcome: { code: "did" }, result: "Dọn thư rác" })], { archOpen: true });
check("archive: title and ending in words", h.includes(vi["ajobs.run.scan"]) && h.includes(vi["ajobs.run.out.did"] + ": Dọn thư rác"), h);

// Dictionaries.
const keys = Object.keys(vi).filter((k) => k.indexOf("ajobs.run.") === 0);
check("thirteen new keys, in both languages", keys.length === 13 && keys.every((k) => en[k]), keys.length);
check("no em or en dash in the new text", !/[–—]/.test(keys.map((k) => vi[k] + en[k]).join("")));
check("placeholders match across languages", keys.every((k) =>
  String(vi[k].match(/\{\w+\}/g)) === String(en[k].match(/\{\w+\}/g))));

console.log(fails ? `\n${fails} FAILED` : "\nall ok");
process.exit(fails ? 1 : 0);
