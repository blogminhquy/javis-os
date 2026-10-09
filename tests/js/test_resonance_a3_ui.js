// Resonance A3: hàng phản hồi dưới tin báo, dòng cách làm đã học trên thẻ, mục Bài học của trợ lý (ca A15).
//
//     python tests/run.py --js resonance_a3_ui -v
//
// Hàng phản hồi chỉ có trên tin báo do host ghi (khoá báo cáo outbox:); request mang nonce; bấm lại đúng nút đang
// sáng gửi `none` (luật của giao diện, API đặt giá trị); khoá từ điển nguyên văn, đủ ở hai thứ tiếng. Hàm thuần.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const RS = require(path.join(ROOT, "dashboard", "chat-resonance.js"));
const RA = require(path.join(ROOT, "dashboard", "resonance-agent.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "chat-resonance.js"), "utf8") +
  fs.readFileSync(path.join(ROOT, "dashboard", "resonance-agent.js"), "utf8");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

// ── hàng phản hồi ──
check("chỉ tin báo có khoá outbox:<số> mới có hàng phản hồi",
  RS.isNotice({ report: "outbox:12" }) && !RS.isNotice({ report: "" }) && !RS.isNotice({ report: "outbox:x" })
  && !RS.isNotice({}) && !RS.isNotice({ report: "chat:1" }));
const ctx = { session_id: "s1", report: "outbox:12", goal_id: "g1" };
const b1 = RS.reactBody({}, "down", null, ctx, "n1");
check("bấm Chưa ổn lần đầu: down, không lý do, mang nonce và bộ ba nguồn",
  b1.value === "down" && b1.reason === "" && b1.nonce === "n1" && b1.session_id === "s1" && b1.report === "outbox:12"
  && b1.goal_id === "g1");
const b2 = RS.reactBody({ value: "down", reason: "" }, "down", null, ctx, "n2");
check("bấm lại đúng nút đang sáng: gửi none (thu hồi)", b2.value === "none" && b2.reason === "");
const b3 = RS.reactBody({ value: "down", reason: "" }, "reason", "too_long", ctx);
check("chọn lý do Dài quá: down kèm lý do, nonce tự sinh", b3.value === "down" && b3.reason === "too_long" && b3.nonce);
const b4 = RS.reactBody({ value: "down", reason: "too_long" }, "reason", "too_long", ctx);
check("bấm lại đúng lý do đang chọn: none", b4.value === "none" && b4.reason === "");
const b5 = RS.reactBody({ value: "down", reason: "too_long" }, "up", null, ctx);
check("đang Chưa ổn bấm Hữu ích: up, bỏ lý do", b5.value === "up" && b5.reason === "");
check("mỗi lần bấm một nonce mới", RS.reactBody({}, "up", null, ctx).nonce !== RS.reactBody({}, "up", null, ctx).nonce);
const r0 = RS.reactHtml({}, false);
const r1 = RS.reactHtml({ value: "down", reason: "unclear" }, false);
check("hàng phản hồi: hai nút, lý do chỉ hiện khi đang Chưa ổn",
  (r0.match(/rs-react-b/g) || []).length === 2 && (r1.match(/rs-react-b/g) || []).length === 5
  && r1.includes(vi["resonance.react_unclear"]) && /rs-on[^>]*data-reason="unclear"/.test(r1));

// ── dòng cách làm đã học trên thẻ ──
const base = { goal_id: "g", revision: 2, status: "active", criteria: [], calls_used: 8, budget_calls: 9, timeline: [] };
const act = RS.viewHtml(Object.assign({}, base, { learning: { lesson_id: "ls_1", status: "active", to_label: "Rà đủ ý" } }));
check("bài học đang dùng: dòng cách làm và nút Quay lại cách cũ (lệnh revert_method)",
  act.includes("Rà đủ ý") && act.includes('data-act="revert_method"') && act.includes(vi["resonance.btn_revert_method"]));
const pend = RS.viewHtml(Object.assign({}, base, { learning: { lesson_id: "ls_2", status: "trialing", to_label: "X" } }));
check("đang thử: có nút Bỏ qua lần thử mang mã bài học",
  pend.includes('data-act="lesson_dismiss"') && pend.includes('data-lesson="ls_2"'));
const sk = RS.viewHtml(Object.assign({}, base, { learning: { status: "skipped", reason: "budget", to_label: "X" } }));
check("không thử vì hạn mức: nói đúng lý do", sk.includes(vi["resonance.a3_skip_budget"]));
const sk2 = RS.viewHtml(Object.assign({}, base, { learning: { status: "skipped", reason: "ma_la", to_label: "X" } }));
check("lý do lạ không lộ mã thô", sk2.includes(vi["resonance.a3_skip_other"]) && !sk2.includes("ma_la"));
check("hết phạm vi thì không hiện dòng cách làm",
  !RS.viewHtml(Object.assign({}, base, { learning: { status: "out_of_scope", to_label: "Rà đủ ý" } })).includes("Rà đủ ý"));
const req = RS.requestFor("lesson_dismiss", base, null, { lesson: "ls_2" }, "n");
check("nút Bỏ qua lần thử gọi route quyết định bài học",
  req.url === "/resonance/lessons/ls_2/decision" && req.body.action === "dismiss");
check("lệnh quay lại cách cũ đi đường lệnh của thẻ",
  RS.requestFor("revert_method", base, null, {}, "n").url === "/goals/g/commands");

// ── mục Bài học ──
const data = {
  lessons: [
    { id: "ls_p", lane: "presentation", key: "notice_detail", to_value: "brief", status: "proposed", updated_at: 1.5,
      evidence: { reactions: ["reaction:1@1", "reaction:2@1"] },
      preview: { kind: "detail", old: "Mục tiêu đã đạt: câu dài", new: "Đã đạt: câu ngắn" } },
    { id: "ls_a", lane: "presentation", key: "notice_ping", to_value: "quiet", status: "active", evidence_missing: 1 },
    { id: "ls_m", lane: "method", key: "method", to_value: "work.checklist.v1", status: "rejected" },
  ],
  stats: { up: 2, down: 3 },
};
const lh = RA.lessonsHtml(data);
check("đề xuất: câu cũ và câu mới xếp dọc, số tin căn cứ, nút Áp dụng mang updated_at, nút Bỏ qua",
  lh.includes("Mục tiêu đã đạt: câu dài") && lh.includes("Đã đạt: câu ngắn") && lh.includes('data-upd="1.5"')
  && lh.includes('data-act="dismiss"') && lh.includes(vi["resonance.a3_evidence"].replace("{n}", "2")));
check("bài học đang dùng: nút Thu hồi và cảnh báo nguồn đã xoá",
  lh.includes('data-act="revoke"') && lh.includes(vi["resonance.a3_evidence_missing"]));
check("lịch sử ngắn có bài học làn M đã thử thua", lh.includes(vi["resonance.a3_st_rejected"]));
check("tin bắt buộc luôn đầy đủ được nói rõ trên đề xuất", lh.includes(vi["resonance.a3_mandatory_note"]));
check("chưa có bài học: câu giải thích", RA.lessonsHtml({ lessons: [] }).includes(vi["resonance.a3_lessons_empty"]));

// ── khoá từ điển ──
const used = new Set();
const re = /tw\(\s*"([^"]+)"/g;
let m;
while ((m = re.exec(SRC))) used.add(m[1]);
const mapRe = /"(resonance\.[a-z0-9_.]+)"/g;
while ((m = mapRe.exec(SRC))) used.add(m[1]);
const a3 = [...used].filter((k) => k.startsWith("resonance.a3_") || k.startsWith("resonance.react") ||
  k === "resonance.btn_revert_method" || k === "resonance.btn_lesson_dismiss" || k.startsWith("resonance.wake.method"));
const miss = a3.filter((k) => !(k in vi) || !(k in en));
check(`mọi khoá A3 có ở cả vi và en (${a3.length} khoá)`, a3.length >= 40 && !miss.length, miss.join(", "));
check("không ghép khoá tw() bằng nối chuỗi", !/tw\(\s*"resonance\.[a-z0-9_.]*"\s*\+/.test(SRC));
check("không ký tự gạch dài", !SRC.includes("—"));
const enVals = a3.map((k) => en[k] || "").join(" ");
check("bản tiếng Anh không lẫn chữ Việt có dấu", !/[ạảãàáâậầấẩẫăặằắẳẵđẹẻẽèéêệềếểễịỉĩìíọỏõòóôộồốổỗơợờớởỡụủũùúưựừứửữỵỷỹỳý]/i.test(enVals));

if (fails) {
  console.log(`\n${fails} FAIL`);
  process.exit(1);
}
console.log("\nOK");
