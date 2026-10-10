// Resonance A4: dòng quyền trên thẻ mục tiêu, thẻ chờ cho phép kèm bản nháp, nút Cho phép / Không / Thu hồi quyền.
//
//     python tests/run.py --js resonance_a4_ui -v
//
// Javis không cấp quyền ghi từ lời chat (D1): mọi đích mới hỏi trên thẻ. Request của Cho phép mang ĐÚNG yêu cầu, đường,
// mã và sha bản nháp đang hiện (thẻ cũ thì server trả 409). Khoá từ điển đủ hai thứ tiếng, không có gạch dài. Hàm thuần.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const RS = require(path.join(ROOT, "dashboard", "chat-resonance.js"));
const RA = require(path.join(ROOT, "dashboard", "resonance-agent.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "chat-resonance.js"), "utf8");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

const base = { goal_id: "g1", revision: 3, status: "active", budget_calls: 6, criteria: [] };
const pending = Object.assign({}, base, { block_reason: "scope_pending", scope: { state: "pending", path: "Inbox/x.md",
  request: { id: "sr_1", kind: "create", path: "Inbox/x.md", revision: 3 },
  draft: { submission_id: "sub_9", sha256: "abc", size: 2048 }, pending_publish: 0, conflict: false } });
const hp = RS.scopeHtml(pending);
check("chờ cho phép: hỏi đúng đường, có Cho phép, Không, Xem trước",
  hp.includes("Inbox/x.md") && hp.includes('data-act="approve_scope"') && hp.includes('data-act="deny_scope"')
  && hp.includes('data-act="draft_preview"'), hp);
check("chờ cho phép kèm bản nháp: nói rõ Cho phép đăng đúng bản này, không gọi model lại",
  hp.includes(vi["resonance.a4_scope_draft"].split("{kb}")[0].trim()));
const noDraft = RS.scopeHtml(Object.assign({}, pending, { scope: Object.assign({}, pending.scope, { draft: null }) }));
check("chờ cho phép không có bản nháp: không có nút Xem trước", !noDraft.includes("draft_preview"));
const evil = RS.scopeHtml(Object.assign({}, pending, { scope: Object.assign({}, pending.scope,
  { path: "<img src=x onerror=1>.md" }) }));
check("đường trên thẻ được escape", !evil.includes("<img") && evil.includes("&lt;img"));

const req = RS.requestFor("approve_scope", pending);
check("Cho phép gửi đúng yêu cầu, đường, mã và sha bản nháp đang hiện",
  req.url === "/goals/g1/commands" && req.body.command === "approve_scope" && req.body.request_id === "sr_1"
  && req.body.path === "Inbox/x.md" && req.body.submission_id === "sub_9" && req.body.sha256 === "abc"
  && req.body.expected_revision === 3, JSON.stringify(req));
const deny = RS.requestFor("deny_scope", pending);
check("Không gửi đúng yêu cầu", deny.body.command === "deny_scope" && deny.body.request_id === "sr_1");
const rev = RS.requestFor("revoke_grant", pending);
check("Thu hồi quyền mang revision đang hiện", rev.body.command === "revoke_grant" && rev.body.expected_revision === 3);

const granted = Object.assign({}, base, { scope: { state: "granted", path: "Inbox/x.md", source: "owner_approved",
  actions: ["publish", "read_deliverable", "submit"], pending_publish: 1, conflict: true } });
const hg = RS.scopeHtml(granted);
check("đã cho phép: dòng quyền có đường, số lượt, không giao tiếp, nút Thu hồi quyền",
  hg.includes("Inbox/x.md") && hg.includes("6") && hg.includes('data-act="revoke_grant"'), hg);
check("đã cho phép: hiện số bản nháp chờ đăng và xung đột", hg.includes(vi["resonance.a4_draft_conflict"]));
check("không cần phạm vi hay mục tiêu đã đóng: không có dòng quyền",
  RS.scopeHtml(Object.assign({}, base, { scope: { state: "none" } })) === ""
  && RS.scopeHtml(Object.assign({}, granted, { status: "succeeded" })) === "");
["revoked", "denied", "missing"].forEach((s) => {
  const h = RS.scopeHtml(Object.assign({}, base, { scope: { state: s, path: "Inbox/x.md" } }));
  check("trạng thái " + s + ": có câu giải thích, không có nút Cho phép", h.includes("Inbox/x.md")
    && !h.includes("approve_scope"));
});
check("thẻ đầy đủ có dòng quyền", RS.viewHtml(pending).includes('data-act="approve_scope"'));
check("tình trạng mới có nhãn", ["scope_pending", "scope_denied", "grant_revoked", "grant_missing"].every((r) =>
  RS.stateKey({ status: "active", block_reason: r }) === "resonance.st_" + r));
check("Thu hồi quyền hỏi xác nhận một lần trước khi gửi", /revoke_grant" && !window\.confirm/.test(SRC));
check("trang Cộng sự: engine nộp qua công cụ có dòng giải thích",
  RA.supportHtml({ goal: true, chat_output: true, submit_tool: true }).includes(vi["resonance.a4_engine_submit"])
  && RA.supportHtml({ goal: false }).indexOf(vi["resonance.a4_engine_submit"]) < 0);

const keys = Object.keys(vi).filter((k) => k.startsWith("resonance.a4_") || ["resonance.btn_approve_scope",
  "resonance.btn_deny_scope", "resonance.btn_preview", "resonance.btn_revoke_grant", "resonance.revoke_confirm",
  "resonance.wake.scope_granted", "resonance.st_scope_pending", "resonance.st_scope_denied",
  "resonance.st_grant_revoked", "resonance.st_grant_missing"].includes(k));
check("chuỗi A4 đủ hai thứ tiếng (" + keys.length + " khoá)", keys.length >= 22 && keys.every((k) => en[k] && vi[k]));
check("không có gạch dài trong chuỗi A4", keys.every((k) => !/\u2014/.test(vi[k] + en[k])));
check("bản tiếng Anh không lẫn chữ tiếng Việt có dấu", keys.every((k) =>
  !/[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/i.test(en[k])));

if (fails) {
  console.log("\n" + fails + " FAIL");
  process.exit(1);
}
console.log("\nOK");
