// 17/11/2026: the approval card can be answered, not only approved or rejected (dashboard/teams.js approvalCardHtml).
//
//     node tests/js/test_team_approval_reply.js
//
// The owner: "anh thấy cần phải trả lời được lại các yêu cầu này chứ không chỉ duyệt hoặc không duyệt ... rất nhiều lúc
// anh muốn hỏi rõ về phần yêu cầu duyệt và muốn chỉnh sửa thì nó rất khó với việc fix cứng như này".
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
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 500)));
  if (!cond) fails++;
}
function T(k) { return String(vi[k]).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }

const now = Date.now() / 1000;
const ap = { approval_id: "ap_9", team_rev: 4, kind: "action", title: "Mở khoá V03 và V02", requested_by: "ag_an",
  action: "Mở khoá V03 khi V03 đạt", impact: "Cần thuê thêm 1 VPS", status: "pending", deadline_at: now + 5 * 3600 + 60,
  evidence: ["/brains/My Bullet Journal/Javis/blog-v03-cham-v3.md", "/brains/x/blog-chon-vps.md (Điểm kẹt 9)", "ghi chú tay"],
  actions: [{ label: "x", call: "vps_create {}", used: false }] };
const msg = { id: 7, author_kind: "system", meta: { kind: "approval_request", approval: ap } };
const closed = { id: "", mode: "ask", quote: -1, draft: "" };

let h = TM.approvalCardHtml(msg, closed);
check("two big buttons: Approve (check icon) and Reply, closed by default",
  h.includes('class="ws-btn tm-ap-ok" data-ap-decide="approve"') && h.includes('data-ap-reply="ap_9" aria-expanded="false"')
  && h.includes(T("teams.ap.approve")) && h.includes(T("teams.ap.reply")) && !h.includes("tm-ap-rp"), h);
check("no more three equal buttons on the card", !h.includes('data-ap-decide="changes"') && !h.includes('data-ap-decide="reject"'));
check("head: title, a waiting pill and the time left, the title on its own line",
  h.includes(T("teams.ap.pill_wait")) && h.includes(T("teams.ap.due_h").replace("{n}", "5")) && h.includes('<p class="tm-ap-title">Mở khoá V03 và V02</p>'), h);
check("each line has a quote button to ask about that exact line", (h.match(/data-ap-quote="/g) || []).length === 2
  && h.includes('data-ap-quote="1" data-ap="ap_9"'), h);
check("evidence and calls fold away with a count; a path shows its file name, the full path in the tooltip",
  /<details class="tm-ap-more"><summary>[\s\S]*?Bằng chứng<\/span><span class="tm-ap-n">3<\/span>/.test(h)
  && h.includes(">blog-v03-cham-v3.md<") && h.includes('title="/brains/My Bullet Journal/Javis/blog-v03-cham-v3.md"')
  && h.includes(">blog-chon-vps.md (Điểm kẹt 9)<") && h.includes(">ghi chú tay<"), h);

h = TM.approvalCardHtml(msg, { id: "ap_9", mode: "ask", quote: 1, draft: "" });
check("Reply open: the button shows it, the box has Ask / Change / Reject with Ask picked",
  h.includes('aria-expanded="true"') && h.includes('data-ap-mode="ask"') && h.includes('data-ap-mode="changes"')
  && h.includes('data-ap-mode="reject"') && /aria-checked="true" data-ap-mode="ask"/.test(h), h);
check("the quoted line is marked and shown as a chip that can be removed",
  h.includes("tm-ap-row tm-ap-row-sel") && h.includes('class="tm-ap-qchip"') && h.includes(T("teams.ap.impact"))
  && h.includes('data-ap-unquote="1"'), h);
check("Ask sends a question and offers quick questions", h.includes('data-ap-send="ask"') && h.includes(T("teams.ap.send_ask"))
  && h.includes(T("teams.ap.sug_ask_why")) && h.includes('placeholder="' + T("teams.ap.ph_ask") + '"'), h);
check("the typed words are not in the html (a redraw does not wipe or duplicate them)", !/<textarea[^>]*>[^<]+<\/textarea>/.test(h));
const rej = TM.approvalCardHtml(msg, { id: "ap_9", mode: "reject", quote: -1, draft: "" });
check("Reject: red send button that says Reject, carries the request and its revision",
  rej.includes('tm-ap-send tm-ap-send-rej" data-ap-send="reject" data-ap="ap_9" data-ap-rev="4"') && !rej.includes("tm-ap-qchip"), rej);
const fix = TM.approvalCardHtml(msg, { id: "ap_9", mode: "changes", quote: -1, draft: "" });
check("Change: sends the old 'changes' decision with the words as its note", fix.includes('data-ap-send="changes"')
  && fix.includes(T("teams.ap.send_changes")) && /if \(d\.apSend !== "ask"\) return apDecide\(btn, d\.ap, d\.apRev, d\.apSend, words\);/.test(src), fix);
check("another card's reply box stays closed", !TM.approvalCardHtml(msg, { id: "ap_other", mode: "ask", quote: -1 }).includes("tm-ap-rp"));
const done = TM.approvalCardHtml({ id: 7, meta: { approval: Object.assign({}, ap, { status: "approved" }) } }, { id: "ap_9", mode: "ask", quote: 0 });
check("a decided card has no reply box, no quote buttons, no pill", !done.includes("tm-ap-rp") && !done.includes("data-ap-quote")
  && !done.includes("tm-ap-pill") && done.includes(T("teams.ap.st.approved")), done);

check("Ask is a chat message quoting the card or the picked line, calling the member who asked, the card keeps waiting",
  /tw\("teams\.ap\.title"\) \+ " · " \+ tw\(row\[0\]\) \+ ": "/.test(src) && /Q\.ghep\(quote, words\)/.test(src)
  && /who\.indexOf\("mandate:"\) !== 0 \? memberOf\(S\.team\.members, who\)/.test(src) && /call\("POST", teamUrl\("\/messages"\), body\)/.test(src));
check("a retry of the same question sends the same client id (never twice)", /client_msg_id: AP_REPLY\.cid \|\| \(AP_REPLY\.cid = newClientId\(\)\)/.test(src));
check("the words typed survive a redraw of the card", /if \(AP_REPLY\.id\) apRestore\(false\);/.test(src)
  && /classList\.contains\("tm-ap-ta"\)\) \{ AP_REPLY\.draft = e\.target\.value; return; \}/.test(src));
check("Ctrl or Cmd+Enter sends, Escape closes", /e\.key === "Enter" && \(e\.ctrlKey \|\| e\.metaKey\)/.test(src) && /e\.key === "Escape"\) \{ e\.preventDefault\(\); apOpen\(""/.test(src));
check("no browser prompt() for reject or changes any more", !/prompt\(tw\(dec === "reject"/.test(src));

check("time left reads in minutes, hours, days, and past the deadline", TM.apDueText(now + 600, now) === "còn 10 phút"
  && TM.apDueText(now + 3 * 3600, now) === "còn 3 giờ" && TM.apDueText(now + 3 * 86400, now) === "còn 3 ngày"
  && TM.apDueText(now - 5, now) === "hết hạn");
check("short refs: a path keeps its file name and what follows, plain words stay", TM.apShortRef("/a/b/c.md") === "c.md"
  && TM.apShortRef("C:\\x\\y.csv (dòng 2)") === "y.csv (dòng 2)" && TM.apShortRef("khach.csv") === "khach.csv"
  && TM.apShortRef("ghi chú") === "ghi chú");

const keys = ["teams.ap.reply", "teams.ap.mode_ask", "teams.ap.mode_changes", "teams.ap.mode_reject", "teams.ap.ph_ask",
  "teams.ap.send_ask", "teams.ap.send_changes", "teams.ap.send_reject", "teams.ap.unquote", "teams.ap.quote_row",
  "teams.ap.pill_wait", "teams.ap.due_over", "teams.ap.due_min", "teams.ap.due_h", "teams.ap.due_d", "teams.ap.need_words",
  "teams.ap.sug_ask_why", "teams.ap.sug_ask_cost", "teams.ap.sug_ask_other", "teams.ap.sug_fix_smaller", "teams.ap.sug_fix_show",
  "teams.ap.sug_fix_later", "teams.ap.sug_rej_notnow", "teams.ap.sug_rej_cost", "teams.ap.sug_rej_wrong"];
check("every new word exists in Vietnamese and English", keys.every(function (k) { return vi[k] && en[k]; }),
  keys.filter(function (k) { return !vi[k] || !en[k]; }).join(", "));
check("the card says cộng sự, never trợ lý", !/trợ lý/i.test(["teams.ap.prose", "teams.ap.reject_prompt", "teams.ap.st.approved"]
  .map(function (k) { return vi[k]; }).join(" ")));

check("buttons are 48px and the box fits a phone", /\.tm-ap-acts \.ws-btn \{[^}]*min-height: 48px/.test(css)
  && /\.tm-ap-seg \{[^}]*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/.test(css) && /\.tm-ap-ta \{[^}]*font-size: 16px/.test(css));

if (fails) { console.log("\nFAILED " + fails); process.exit(1); }
console.log("\nALL OK");
