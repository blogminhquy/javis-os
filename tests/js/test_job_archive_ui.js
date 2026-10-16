// 0.193.0: finished jobs, Done to the archive, delete only from the archive (an assistant's Jobs tab and a team's), job
// state colours, each assistant's reasoning level, and "Message privately" from a team.
//
//     node tests/js/test_job_archive_ui.js
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(root, "dashboard", f), "utf8");
const vi = JSON.parse(read("i18n/vi.json"));
const en = JSON.parse(read("i18n/en.json"));
global.window = { t: (k, p) => { let s = vi[k] || k; Object.keys(p || {}).forEach((x) => { s = s.split("{" + x + "}").join(p[x]); }); return s; } };
const AJ = require(path.join(root, "dashboard", "agent-jobs.js"));
const T = require(path.join(root, "dashboard", "teams.js"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 400)));
  if (!cond) fails++;
}

// ---- an assistant's Jobs tab ----
const done = AJ.jobHtml({ id: "kanban:1", title: "Viết bài", bucket: "done", source: "chat", roles: [], result: "Xong" }, {});
const run = AJ.jobHtml({ id: "kanban:2", title: "Đang viết", bucket: "running", source: "chat", roles: [] }, {});
check("a finished job has a Done button; a running one does not", done.includes('data-aj-archive="kanban:1"')
  && done.includes(vi["ajobs.mark_done"]) && !run.includes("data-aj-archive"), done);
check("each card carries its state as a coloured label", done.includes('aj-state aj-state-done') && run.includes('aj-state aj-state-running'));
const arch = AJ.archiveHtml([{ id: "kanban:3", title: "Cũ", result: "kq" }], { archOpen: true });
check("the archive lists jobs with Restore and Delete, and Delete all", arch.includes('data-aj-unarchive="kanban:3"')
  && arch.includes('data-aj-delete="kanban:3"') && arch.includes("aj-arch-clear"), arch);
check("the archive starts folded and is absent when empty", !AJ.archiveHtml([{ id: "x", title: "t" }], {}).includes("data-aj-delete")
  && AJ.archiveHtml([], {}) === "");
const aj = read("agent-jobs.js");
check("Done, Restore and Delete go through /jobs/marks", aj.includes('jsonPost("/jobs/marks", { brain: opts.brain(), ids: ids, state: state })')
  && aj.includes('markJobs([d.ajArchive], "archived")') && aj.includes('markJobs([d.ajDelete], "deleted")'));

// ---- a team's Jobs tab ----
const q = { finished: [{ id: "team:9", task_id: "9", title: "Landing", result: "Xong, link https://x.test", updated_at: 1,
  steps: [{ agent_key: "a", kind: "work" }] }], archived: [{ id: "team:8", title: "Cũ" }] };
const shut = T.queueHtml(q, { members: [{ agent_key: "a", name: "Lan" }] });
check("finished team jobs show with Open and Done; the archive is folded", shut.includes(vi["teams.queue_finished"])
  && shut.includes('data-fin-open="team:9"') && shut.includes('data-job-archive="team:9"') && !shut.includes("data-job-delete"), shut);
const opened = T.queueHtml(q, { openFin: "team:9", archOpen: true, members: [{ agent_key: "a", name: "Lan" }] });
check("Open shows the report: who did what and the result", opened.includes("tm-report") && opened.includes("Lan")
  && opened.includes("x.test") && opened.includes('data-view-task="9"'), opened);
check("in the open archive: Restore, Delete and Delete all", opened.includes('data-job-unarchive="team:8"')
  && opened.includes('data-job-delete="team:8"') && opened.includes('data-job-delete-all="1"'));
check("no finished and nothing queued still says the queue is empty", T.queueHtml({}, {}).includes(vi["teams.queue_empty"]));
const tj = read("teams.js");
check("team Done / Delete use the same marks, Delete all asks first",
  tj.includes('call("POST", "/jobs/marks", { brain: brain(), ids: ids, state: state })') && tj.includes('tw("teams.archive_clear_confirm"'));

// ---- reasoning and private chat ----
const st = read("studio.js");
check("the assistant editor has a reasoning select, medium by default, saved with the form",
  st.includes('const curReason = (a && a.reasoning) || "medium";') && st.includes('<select id="agReasoning">')
  && st.includes('reasoning: (box.querySelector("#agReasoning") || {}).value || "medium",'));
check("from a team the editor has Message privately", st.includes("opts.chatButton && a && a.slug") &&
  tj.includes("St.editAgent({ slug: slug }, { chatButton: true,") && tj.includes('data-agent-chat="'));
const mp = read("model-picker.js");
check("in an assistant's chat the effort chip shows and sets that assistant's level",
  mp.includes("agentEff = d && d.agent_slug ?") && mp.includes("await saveAgentEffort(agentEff.slug, v)")
  && mp.includes("`/agents/${encodeURIComponent(slug)}/reasoning`"));
const css = read("console.css");
check("CSS: four job colours, state labels, report and archive",
  [".aj-job.aj-needs_you { border-left-color: var(--red); }", ".aj-job.aj-running { border-left-color: #3b82f6; }",
    ".aj-state-done {", ".tm-report {", ".tm-arch-toggle {", ".agent-editor .ag-head {"].every((x) => css.includes(x)));
const keys = ["ajobs.mark_done", "ajobs.archive", "ajobs.archive_back", "ajobs.archive_delete", "ajobs.archive_clear",
  "ajobs.archive_clear_confirm", "ajobs.mark_err", "teams.queue_finished", "teams.fin_open", "teams.fin_done", "teams.archive",
  "teams.archive_clear", "teams.archive_clear_confirm", "studio.reasoning", "studio.reasoning_hint", "studio.chat_private",
  "teams.chat_private", "mpick.eff_agent"];
check("i18n vi/en, no em dash", keys.every((k) => vi[k] && en[k]) && !/[–—]/.test(keys.map((k) => vi[k] + en[k]).join("")),
  keys.filter((k) => !vi[k] || !en[k]).join(","));

if (fails) { console.log("\nFAIL " + fails); process.exit(1); }
console.log("\nOK test_job_archive_ui");
