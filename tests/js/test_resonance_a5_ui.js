// Resonance A5: ô Người review ở trang trợ lý và dòng đội trên thẻ mục tiêu (thiết kế A5 mục 11).
//
//     python tests/run.py --js resonance_a5_ui -v
//
// Hàm thuần chạy dưới node: ô chọn chỉ liệt kê trợ lý đã bật Cộng hưởng (không theo tag), dòng đội theo dữ liệu
// `team` của goal view, hai nút của chủ dự án (Bật lại người review, Bỏ yêu cầu review) và request chúng gửi.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const RA = require(path.join(ROOT, "dashboard", "resonance-agent.js"));
const RS = require(path.join(ROOT, "dashboard", "chat-resonance.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

// ───────────── ô Người review ─────────────
const me = { slug: "", name: "Người làm", agent_key: "ag_m", enabled: true, status: "active",
  support: { goal: true, chat_output: true }, reviewer: null };
const all = [
  me,
  { slug: "duyet", name: "Người duyệt", enabled: true, status: "active", tags: ["Review"] },
  { slug: "tat", name: "Đang tắt", enabled: false, status: "active" },
  { slug: "mat", name: "Mất file", enabled: true, status: "missing" },
];
let h = RA.panelHtml(me, "ready", [], all);
check("bật Cộng hưởng: có ô Người review, mặc định Không có", h.includes("rsa-reviewer")
      && h.includes(vi["resonance.a5_reviewer_none"]) && h.includes(vi["resonance.a5_reviewer_note"]));
check("ô chỉ liệt kê trợ lý ĐÃ BẬT (không theo tag): có người duyệt; không có trợ lý tắt hay mất file",
      h.includes('value="duyet"') && !h.includes('value="tat"') && !h.includes('value="mat"'));
check("tag không xuất hiện trong ô chọn", !h.includes("Review</option>"));
h = RA.panelHtml(Object.assign({}, me, { enabled: false }), null, [], all);
check("trợ lý chưa bật Cộng hưởng: không có ô Người review", !h.includes("rsa-reviewer"));
h = RA.panelHtml(Object.assign({}, me, { reviewer: { slug: "duyet", status: "active", enabled: true } }), "ready", [], all);
check("người review đang chọn được đánh dấu selected", /value="duyet" selected/.test(h));
h = RA.panelHtml(Object.assign({}, me, { reviewer: { slug: "tat", status: "active", enabled: false } }), "ready", [], all);
check("người review đang chọn mà đã tắt vẫn hiện kèm nhãn để thấy vì sao bị chặn",
      /value="tat" selected/.test(h) && h.includes(vi["resonance.a5_reviewer_off_tag"]));

// ───────────── dòng đội trên thẻ ─────────────
const base = { goal_id: "g_1", revision: 1, status: "active", understanding: "Bản tóm tắt", criteria: [],
  budget_calls: 8, calls_used: 3 };
const team = { legacy: false, status: "active", maker: { slug: "lam", agent_key: "ag_l" },
  reviewer: { slug: "duyet", agent_key: "ag_d" },
  calls: { maker: { cap: 4, used: 2 }, reviewer: { cap: 4, used: 1 } }, max_rounds: 2, rounds_used: 1,
  latest: { verdict: "needs_changes", sha8: "abcd1234", criteria: [{ index: 0, ok: false, reason: "Thiếu kết luận" }],
            fixes: "Thêm mục Kết luận" } };
h = RS.viewHtml(Object.assign({}, base, { block_reason: "review_changes", run_state: "waiting", team: team }));
check("dòng đội: ai làm, ai review", h.includes("Làm: lam · Review: duyet"));
check("bản đã review: mã ngắn và kết luận kèm vòng", h.includes("Bản đã review: abcd1234 · Cần sửa (vòng 1/2)"));
check("lượt còn theo vai", h.includes("Lượt còn: làm 2/4 · review 3/4"));
check("đang chờ người làm sửa theo góp ý", h.includes("Đang chờ lam sửa theo góp ý"));
check("góp ý review trong phần mở rộng (thoát ký tự)", h.includes(vi["resonance.a5_fixes"])
      && h.includes("Thiếu kết luận") && h.includes("Thêm mục Kết luận"));
check("nhãn trạng thái dịch được, không lộ mã thô", h.includes(vi["resonance.st_review_changes"]));
check("đang sửa theo góp ý: không có nút Bỏ yêu cầu review (chưa bị chặn)", !h.includes('data-act="team_detach"'));
h = RS.viewHtml(Object.assign({}, base, { block_reason: "review_pending", run_state: "waiting",
  team: Object.assign({}, team, { latest: null }) }));
check("đang chờ review: nói rõ bản đã đăng chưa nghiệm thu", h.includes("Đang chờ duyet xem bản đã tiếp nhận"));
h = RS.viewHtml(Object.assign({}, base, { block_reason: "reviewer_off", run_state: "blocked", team: team }));
check("người review tắt: nút Bật lại người review ghim MÃ BỀN của reviewer (không phải slug) và Bỏ yêu cầu review",
      h.includes('data-act="reviewer_enable" data-key="ag_d"') && !h.includes('data-key="duyet"')
      && h.includes('data-act="team_detach"') && h.includes(vi["resonance.st_reviewer_off"]));
h = RS.viewHtml(Object.assign({}, base, { block_reason: "reviewer_off", run_state: "blocked",
  team: Object.assign({}, team, { reviewer: { slug: "duyet" } }) }));
check("thẻ không có mã bền của reviewer: không có nút Bật lại (không đoán theo slug)",
      !h.includes('data-act="reviewer_enable"') && h.includes('data-act="team_detach"'));
for (const code of ["review_rounds", "review_unknown", "review_input", "budget_maker", "budget_reviewer",
                    "reviewer_retired", "source_drift"]) {
  const x = RS.viewHtml(Object.assign({}, base, { block_reason: code, run_state: "blocked", team: team }));
  check("chặn " + code + ": có nút Bỏ yêu cầu review, không có nút Bật lại",
        x.includes('data-act="team_detach"') && !x.includes('data-act="reviewer_enable"'));
}
h = RS.viewHtml(Object.assign({}, base, { status: "succeeded", block_reason: "", team: team }));
check("mục tiêu đã kết thúc: không có nút đội", !h.includes('data-act="team_detach"'));
h = RS.viewHtml(Object.assign({}, base, { team: { legacy: true } }));
check("mục tiêu cũ gán lại: nói rõ không có người review", h.includes(vi["resonance.a5_legacy"]));
h = RS.viewHtml(Object.assign({}, base, { team: Object.assign({}, team, { status: "detached" }) }));
check("đã tách đội: dòng nói chốt theo luật thường, không có nút", h.includes(vi["resonance.a5_detached_line"])
      && !h.includes('data-act="team_detach"'));
check("không có đội: không có dòng đội", !RS.viewHtml(base).includes("rs-team"));

// ───────────── request của hai nút ─────────────
let r = RS.requestFor("team_detach", Object.assign({}, base, { team: team }));
check("Bỏ yêu cầu review: lệnh team_detach của chủ dự án trên đúng mục tiêu",
      r.url === "/goals/g_1/commands" && r.body.command === "team_detach");
r = RS.requestFor("reviewer_enable", Object.assign({}, base, { team: team }), null, { key: "ag_d" });
check("Bật lại người review: route của thẻ, gửi mã bền đang hiện (không gửi slug, không qua nút bật thông thường)",
      r.url === "/goals/g_1/reviewer/enable" && r.body.agent_key === "ag_d" && !("slug" in r.body)
      && r.body.expected_revision === 1);
r = RS.requestFor("reviewer_enable", Object.assign({}, base, { team: team }), null, {});
check("Bật lại người review: thiếu data-key thì lấy mã bền từ dữ liệu đội của thẻ", r.body.agent_key === "ag_d");
check("thẻ cũ nhận 409: câu báo trạng thái đã đổi (thẻ vẽ lại theo dữ liệu mới)",
      RS.noteFor("reviewer_enable", { code: 409, j: { ok: false } }) === vi["resonance.changed"]);
check("câu báo sau lệnh", RS.noteFor("team_detach", { code: 200, j: { ok: true } }) === vi["resonance.a5_detached"]
      && RS.noteFor("reviewer_enable", { code: 200, j: { ok: true } }) === vi["resonance.a5_reviewer_enabled"]);

// ───────────── từ điển ─────────────
const keys = Object.keys(vi).filter(function (k) { return /^resonance\.(a5_|st_review|st_budget_|st_reviewer|st_prepare|wake\.review|wake\.team|wake\.prepare|btn_reviewer|btn_team)/.test(k); });
check("mọi khoá A5 có cả tiếng Việt và tiếng Anh", keys.length >= 41 && keys.every(function (k) { return en[k]; }),
      keys.filter(function (k) { return !en[k]; }).join(","));
const DASH = String.fromCharCode(0x2014);
check("không có gạch dài trong chữ A5", keys.every(function (k) { return vi[k].indexOf(DASH) < 0
      && en[k].indexOf(DASH) < 0; }));
check("wake label của mã mới không lộ mã thô", RS.wakeLabel("review_due") === vi["resonance.wake.review_due"]
      && RS.wakeLabel("review_changes") === vi["resonance.wake.review_changes"]
      && RS.wakeLabel("prepare_recheck") === vi["resonance.wake.prepare_recheck"]);
h = RS.viewHtml(Object.assign({}, base, { block_reason: "prepare_error", run_state: "blocked" }));
check("lượt làm chưa chạy được (R1): nhãn trạng thái dịch được", h.includes(vi["resonance.st_prepare_error"]));

if (fails) { console.log("\n" + fails + " FAIL"); process.exit(1); }
console.log("\nOK");
