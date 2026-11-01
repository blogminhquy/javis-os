// 0.432.3: the workflow picker of the new webhook form has a search box (owner 2026-11-01: "cần có tìm kiếm workflow
// ở trong webhook tránh việc nhiều workflow quá mà ko tìm ra").
const fs = require("fs");
const path = require("path");
const W = require(path.join(__dirname, "../../dashboard/webhooks.js"));
const js = fs.readFileSync(path.join(__dirname, "../../dashboard/webhooks.js"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(__dirname, "../../dashboard/i18n/vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(__dirname, "../../dashboard/i18n/en.json"), "utf8"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

const wfs = [
  { slug: "chan-doan-pheu-dang-ro", name: "Chẩn đoán phễu đang rò" },
  { slug: "chuoi-email-sau-tai-lieu", name: "Chuỗi email sau tài liệu miễn phí" },
  { slug: "kich-hoat-lai-danh-sach-nguoi", name: "Kích hoạt lại danh sách nguội" },
  { slug: "viet-blog", name: "Quy trình viết bài blog chất lượng cao" },
  { slug: "don_hang_moi" },
];
const slugs = (q) => W.filterWorkflows(wfs, q).map((w) => w.slug);

check("an empty search keeps every workflow in order", slugs("").join() === wfs.map((w) => w.slug).join());
check("matching ignores case", slugs("EMAIL").join() === "chuoi-email-sau-tai-lieu");
check("matching ignores Vietnamese accents both ways", slugs("phieu").length === 0 && slugs("pheu").join() === "chan-doan-pheu-dang-ro"
  && slugs("phễu").join() === "chan-doan-pheu-dang-ro");
check("đ folds to d", slugs("đanh sach").join() === "kich-hoat-lai-danh-sach-nguoi");
check("every word must match, in any order", slugs("blog viết").join() === "viet-blog" && slugs("blog email").length === 0);
check("the slug counts, with dashes or underscores read as spaces", slugs("don hang").join() === "don_hang_moi" && slugs("viet-blog").join() === "viet-blog");

const opts = W.workflowOptionsHtml(wfs, "email", "");
check("options list only the matches", (opts.match(/<option /g) || []).length === 1 && opts.includes('value="chuoi-email-sau-tai-lieu"'));
check("the chosen workflow stays selected while it matches", W.workflowOptionsHtml(wfs, "ch", "chuoi-email-sau-tai-lieu")
  .includes('value="chuoi-email-sau-tai-lieu" selected'));
check("no match says so with an empty, disabled option", /<option value="" disabled selected>wh\.wf_no_match</.test(W.workflowOptionsHtml(wfs, "zzz", "")));
check("a brain without workflows keeps its own message", W.workflowOptionsHtml([], "x", "").includes("wh.no_workflow"));
check("names are escaped", W.workflowOptionsHtml([{ slug: "a", name: "<b>" }], "", "").includes("&lt;b&gt;"));

const form = W.formHtml([{ path: "/b", name: "b" }], "/b");
check("the form has a search box tied to the picker", form.includes('id="whWfQ"') && form.includes('type="search"')
  && form.includes('aria-controls="whWorkflow"') && form.indexOf('id="whWfQ"') < form.indexOf('id="whWorkflow"'));
check("the search box starts hidden until there are workflows to search", /id="whWfQ"[^>]*hidden>/.test(form));
check("typing redraws the picker", js.includes('f("#whWfQ").oninput = drawWorkflows'));
check("saving with no workflow picked is refused in the form", js.includes('tw("wh.need_workflow")'));
for (const k of ["wh.wf_search_ph", "wh.wf_no_match", "wh.wf_count", "wh.need_workflow"]) {
  check("i18n key " + k + " in vi and en", typeof vi[k] === "string" && typeof en[k] === "string");
}
check("the count names both numbers", vi["wh.wf_count"].includes("{n}") && en["wh.wf_count"].includes("{total}"));

if (fails) { console.log(fails + " failed"); process.exit(1); }
console.log("all ok");
