/* "Reuse key" offers every Google account that holds a key the form takes, whatever card the service sits on.

       node tests/js/test_google_key_reuse.js

   Google shows an OAuth client secret only once, when it is made, so a key kept in another Javis connection is the
   only copy many owners have. The offer used to follow the display group: Google Ads and Analytics sit outside the
   Google card, so they could neither lend their key to Gmail nor borrow Calendar's. This runs the real functions of
   dashboard/console.js on fake catalog entries.
*/
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const src = fs.readFileSync(path.join(ROOT, "dashboard/console.js"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/en.json"), "utf8"));
let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

function cut(from, to) {
  const a = src.indexOf(from);
  const b = a === -1 ? -1 : src.indexOf(to, a);
  return a === -1 || b === -1 ? "" : src.slice(a, b);
}
const hasClient = cut("  function hasClientFields(con) {", "  function jsonDropHtml(con) {");
const jsonDrop = cut("  function jsonDropHtml(con) {", "  function wireJsonDrop(m) {");
const reuse = cut("  const REUSE_SETS = ", "  function openOauthFlow(");
check("the reuse block is found in console.js", !!(hasClient && jsonDrop && reuse));

const window = { t: (k) => k };
const esc = (s) => String(s);
const ic = () => "";
const infoBtn = () => "<i-btn>";
const infoBody = (h) => "<i-body>" + h + "</i-body>";
const CHECK_ICON = "";
const api = new Function("window", "esc", "ic", "infoBtn", "infoBody", "CHECK_ICON",
  hasClient + jsonDrop + reuse +
  "return { reuseDonors, reuseHtml, sharedReuseKeys, missingField, jsonDropHtml, reuseInfoKey, REUSE_SETS };")(
  window, esc, ic, infoBtn, infoBody, CHECK_ICON);

const pair = [{ key: "client_id" }, { key: "client_secret" }];
const cat = {
  gmail: { id: "gmail", key_family: "google", group: "google", auth_type: "oauth", fields: pair },
  "google-calendar": { id: "google-calendar", key_family: "google", group: "google", auth_type: "oauth", fields: pair },
  "google-ads": { id: "google-ads", key_family: "google", group: "", auth_type: "oauth",
                  fields: pair.concat([{ key: "developer_token", optional: true }]) },
  "google-tasks": { id: "google-tasks", key_family: "google", group: "google", auth_type: "apikey",
                    fields: pair.concat([{ key: "user_email", optional: true }]) },
  "google-sheets": { id: "google-sheets", key_family: "google", group: "google", auth_type: "apikey",
                     fields: [{ key: "service_account" }, { key: "folder_id" }] },
  "google-search-console": { id: "google-search-console", key_family: "google", group: "", auth_type: "apikey",
                             fields: [{ key: "service_account" }] },
  "google-keep": { id: "google-keep", key_family: "google", group: "google", auth_type: "apikey",
                   fields: [{ key: "google_email" }, { key: "master_token", optional: true }] },
  "meta-ads-graph": { id: "meta-ads-graph", key_family: "", group: "", auth_type: "oauth", fields: pair },
};
const conns = [
  { id: "c-ads", connector_id: "google-ads", label: "Google Ads" },
  { id: "c-sheets", connector_id: "google-sheets", label: "Sheets" },
  { id: "c-keep", connector_id: "google-keep", label: "Keep" },
  { id: "c-meta", connector_id: "meta-ads-graph", label: "Meta" },
];
const ctx = { conns, byId: cat };
const ids = (con) => api.reuseDonors(con, ctx).map((d) => d.id).sort().join(",");

check("Calendar borrows the key Google Ads holds (Ads sits outside the Google card)", ids(cat["google-calendar"]) === "c-ads");
check("Tasks borrows it too", ids(cat["google-tasks"]) === "c-ads");
check("Search Console borrows the service account Sheets holds", ids(cat["google-search-console"]) === "c-sheets");
check("Keep has no reusable key, so it is offered nothing", ids(cat["google-keep"]) === "");
check("a Meta app key is never offered to a Google form", !ids(cat.gmail).includes("c-meta"));
check("a Google key is never offered to a Meta form", ids(cat["meta-ads-graph"]) === "");
check("no context, no offer", api.reuseDonors(cat.gmail, null).length === 0);

check("the inputs to grey out are the shared pair",
  api.sharedReuseKeys(cat["google-tasks"], cat["google-ads"]).join(",") === "client_id,client_secret");
check("an OAuth key and a service account share nothing",
  api.sharedReuseKeys(cat["google-search-console"], cat["google-ads"]).length === 0);

// missingField: the reused inputs count as given, the others still have to be filled.
function fakeModal(values, reuseFrom, reuseKeys) {
  const inputs = Object.keys(values).map((k) => ({ dataset: { f: k }, value: values[k] }));
  return { _reuseFrom: reuseFrom, _reuseKeys: reuseKeys, querySelectorAll: () => inputs };
}
const sheetsForm = { fields: [{ key: "service_account", label: "SA" }, { key: "folder_id", label: "Folder" }] };
check("a borrowed service account counts as given",
  api.missingField(fakeModal({ service_account: "", folder_id: "F" }, "c-sheets", ["service_account"]), sheetsForm) === "");
check("without borrowing, the empty service account is reported",
  api.missingField(fakeModal({ service_account: "", folder_id: "F" }, "", []), sheetsForm) === "SA");
check("borrowing a key does not excuse an unrelated empty field",
  api.missingField(fakeModal({ service_account: "", folder_id: "" }, "c-sheets", ["service_account"]), sheetsForm) === "Folder");

check("the Google JSON drop zone follows the key family (Google Ads gets it)", api.jsonDropHtml(cat["google-ads"]) !== "");
check("no JSON drop zone on a Meta form", api.jsonDropHtml(cat["meta-ads-graph"]) === "");

const row = api.reuseHtml(api.reuseDonors(cat["google-calendar"], ctx), cat["google-calendar"]);
check("the reuse row carries its explanation behind (i)", row.includes("<i-btn>") && row.includes("<i-body>"));
check("an OAuth form explains the Javis redirect address", api.reuseInfoKey(cat.gmail) === "cs.cn_reuse_info_oauth");
check("a local-sign-in form (Tasks) explains the localhost:8000 address", api.reuseInfoKey(cat["google-tasks"]) === "cs.cn_reuse_info_local");
check("a service-account form explains sharing with its email", api.reuseInfoKey(cat["google-search-console"]) === "cs.cn_reuse_info_sa");
for (const k of ["cs.cn_reuse_info_oauth", "cs.cn_reuse_info_local", "cs.cn_reuse_info_sa"]) {
  check(k + " exists in vi and en", !!vi[k] && !!en[k]);
  check(k + " has no long dash", !/[\u2013\u2014]/.test((vi[k] || "") + (en[k] || "")));
}
check("the localhost address in the text is the one workspace-mcp listens on",
  vi["cs.cn_reuse_info_local"].includes("http://localhost:8000/oauth2callback")
  && en["cs.cn_reuse_info_local"].includes("http://localhost:8000/oauth2callback"));

// Where the row sits: first in the form, above the setup steps it makes unnecessary, in both sign-in flows.
for (const flow of ["function openApikeyFlow(", "function openOauthFlow("]) {
  const body = cut("  " + flow, "\n  }\n");
  const r = body.indexOf("reuseHtml(reuseDonors(con, ctx), con)"), st = body.indexOf("stepsHtml(con)");
  check(flow.slice(9, -1) + ": the reuse row comes before the setup steps", r !== -1 && st !== -1 && r < st);
}
const css = fs.readFileSync(path.join(ROOT, "dashboard/console.css"), "utf8");
check("the reuse sentence reads at 16px", /\.reuse-row > \.mp-note \{[^}]*font-size: 16px/.test(css));

// Same list on both sides: the server copies exactly what the dashboard greys out.
const py = fs.readFileSync(path.join(ROOT, "server/mcp_store.py"), "utf8");
check("REUSE_SETS matches REUSABLE_KEY_SETS in mcp_store.py",
  /REUSABLE_KEY_SETS = \(\("client_id", "client_secret"\), \("service_account",\)\)/.test(py)
  && JSON.stringify(api.REUSE_SETS) === JSON.stringify([["client_id", "client_secret"], ["service_account"]]));

if (fails.length) { console.log("\nFAIL - test_google_key_reuse: " + fails.length); process.exit(1); }
console.log("\nOK - test_google_key_reuse: all pass");
