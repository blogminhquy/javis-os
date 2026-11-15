// 2026-11-15: a webhook can be edited after it is made (owner: "thêm nút sửa cho webhook đi. Cài xong ko sửa đc").
// The configuration part has an Edit button; it opens the create form's fields, prefilled, inside the popup, and saves
// through POST /webhooks/update with the revision edited.
//
//     node tests/js/test_webhooks_edit.js
"use strict";
const fs = require("fs");
const path = require("path");
const W = require(path.join(__dirname, "../../dashboard/webhooks.js"));
const js = fs.readFileSync(path.join(__dirname, "../../dashboard/webhooks.js"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(__dirname, "../../dashboard/i18n/vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(__dirname, "../../dashboard/i18n/en.json"), "utf8"));

let fails = 0;
function check(name, ok, extra) {
  console.log((ok ? "ok   " : "FAIL ") + name + (ok || extra === undefined ? "" : "  " + String(extra).slice(0, 400)));
  if (!ok) fails++;
}

const hook = { id: "h1", name: "Form <landing>", brain: "/b", target: "task", workflow: "", text: "Gọi lại khách",
  level: "auto", enabled: true, revision: 3, url: "https://x/hooks/h1", history: [], actions: [] };

const dlg = W.dialogHtml(hook, [{ path: "/b", name: "b" }], "cfg");
check("the configuration part has an Edit button, first in its row",
  /<div class="wh-acts wh-cfgacts"><button type="button" class="wh-btn whEdit">/.test(dlg), dlg);

const ed = W.editHtml(hook);
check("the edit panel has a way back to the configuration", ed.includes("whBack") && ed.includes("wh.back_cfg"));
check("the name is prefilled and escaped", ed.includes('value="Form &lt;landing&gt;"'));
check("the job text is prefilled", ed.includes(">Gọi lại khách</textarea>"));
check("the hook's target and level are the ones switched on",
  ed.includes('class="wh-segb on" data-t="task"') && !ed.includes('class="wh-segb on" data-t="workflow"')
  && ed.includes('class="wh-segb on" data-l="auto"') && !ed.includes('class="wh-segb on" data-l="full"'));
check("a written job shows the job label, not the workflow one", ed.includes(">wh.text_task</label>"));
check("the brain is not offered: the hook stays in its brain", !ed.includes('id="whBrain"'));
check("save and cancel are there", ed.includes('id="whSave"') && ed.includes("common.cancel"));

const wf = W.editHtml({ name: "a", target: "workflow", level: "weird" });
check("an unknown level falls back to full", wf.includes('class="wh-segb on" data-l="full"'));
check("a workflow hook switches the workflow button on", wf.includes('class="wh-segb on" data-t="workflow"'));

const form = W.formHtml([{ path: "/b", name: "b" }], "/b");
check("the create form still starts empty on a workflow at full level, with the brain picker",
  form.includes('id="whBrain"') && form.includes('value=""') && form.includes('class="wh-segb on" data-t="workflow"')
  && form.includes('class="wh-segb on" data-l="full"'));

check("saving sends the revision edited and the edited fields to /webhooks/update",
  /api\("\/webhooks\/update", body\)/.test(js) && /var body = \{ id: h\.id, revision: h\.revision, name:/.test(js));
check("a 409 says someone saved first", /if \(r\._status === 409\) \{ f\("#whMsg"\)\.textContent = r\.error \|\| tw\("wh\.conflict"\)/.test(js));
check("the edit panel lists the hook's own brain with its workflow picked", /loadWorkflows\(h\.brain, h\.workflow \|\| ""\)/.test(js));
check("both languages name the button and the panel",
  vi["wh.edit"] === "Sửa" && en["wh.edit"] === "Edit" && !!vi["wh.edit_title"] && !!en["wh.edit_title"]);
check("no long dash in the file", !/[–—]/.test(js));

if (fails) { console.log(`\nFAIL - test_webhooks_edit: ${fails} lỗi`); process.exit(1); }
console.log("\nOK - test_webhooks_edit: tất cả pass");
