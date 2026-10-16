// T3 phần L (0.156.0), rút gọn 0.190.0: mục "Hạn mức tự chạy" trong bảng Nhịp (agent-lessons-ui.js).
//
//     python tests/run.py --js agent_lessons_ui -v
//
// 0.190.0 (chủ repo 16/10/2026): danh sách bài học theo phạm vi, nút Thu hồi / Dùng ở mọi nơi, "bài học cũ chưa có phạm
// vi", thay đổi của tự rà soát và đề xuất rời màn hình; bài học làm qua chat (tool javis_memory, test_memory_chat.py).
// Mục chỉ còn hạn mức lượt tự phát hôm nay và ô chọn. Hàm thuần dưới node, cộng chỗ nối: sổ JavisPulseParts, script
// trong index.html, CSS 16px, i18n hai thứ tiếng, dòng bảng giới hạn của teams.js.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const LUI = require(path.join(ROOT, "dashboard", "agent-lessons-ui.js"));
const P = require(path.join(ROOT, "dashboard", "agent-pulse.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const read = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 500)));
  if (!cond) fails++;
}

const lessons = {
  name: "lessons", agent_key: "ag_1", slug: "viet",
  scopes: [{ scope: "*", lessons: [{ id: 7, scope: "*", kind: "speak", text: "Hỏi lại khi mơ hồ", source: "owner" }] }],
  legacy: ["Bài học cũ trộn nhóm"],
  changes: [{ id: 1, kind: "offset_set", context_ref: "team:tm_a", status: "applied", policy_change_id: 11, can_revert: true }],
  proposals: [{ id: 1, area: "permissions", text: "Cho quyền mở việc" }],
  budget: { cap: 6, used: 2, reserved: 2, left: 4 },
  reviews: []
};
const view = { ok: true, agent_key: "ag_1", parts: { lessons: lessons } };
const h = LUI.partHtml(view, {});
check("tiêu đề Hạn mức tự chạy và hạn mức hôm nay", h.includes(vi["lessons.title"]) && vi["lessons.title"] === "Hạn mức tự chạy"
  && h.includes(vi["lessons.budget_line"].replace("{used}", "2").replace("{cap}", "6").replace("{reserved}", "2")), h);
check("0.190.0: không còn danh sách bài học, bài học cũ, thay đổi tự rà soát hay đề xuất",
  !h.includes("Hỏi lại khi mơ hồ") && !h.includes("Bài học cũ trộn nhóm") && !h.includes("Cho quyền mở việc")
  && !h.includes("data-lessons-act"), h);
check("ô chọn hạn mức có Không giới hạn, chọn đúng giá trị hiện tại",
  h.includes('value="unlimited"') && h.includes('<option value="6" selected>'));
const hu = LUI.partHtml({ parts: { lessons: Object.assign({}, lessons, { budget: { cap: null, used: 4 } }) } }, {});
check("Không giới hạn: dòng hạn mức và ô chọn", hu.includes(vi["lessons.budget_unlimited"].replace("{used}", "4")) &&
  hu.includes('value="unlimited" selected'));
const h7 = LUI.partHtml({ parts: { lessons: Object.assign({}, lessons, { budget: { cap: 7, used: 0 } }) } }, {});
check("giá trị hạn mức lạ (7) vẫn có trong ô chọn", h7.includes('<option value="7" selected>'));
// Review T3 L P3: ô chọn nhớ giá trị đang lưu để máy chủ từ chối thì về lại đúng giá trị đó.
const lsrc = read("agent-lessons-ui.js");
check("ô chọn hạn mức mang giá trị đang lưu (data-prev) và đặt lại khi lưu lỗi",
  h.includes('class="lessons-budget-sel" data-prev="6"') && hu.includes('data-prev="unlimited"')
  && /sel\.value = sel\.getAttribute\("data-prev"\)/.test(lsrc));
check("thông báo chỉ sau khi máy chủ xác nhận (msg/err do người gọi truyền)",
  LUI.partHtml(view, { msg: vi["lessons.done"] }).includes('role="status"') &&
  LUI.partHtml(view, { err: "x" }).includes('role="alert"') && !h.includes('role="status"'));
check("không có mục lessons thì không vẽ gì", LUI.partHtml({ parts: {} }, {}) === "");
check("mục lỗi phía máy chủ thì báo lỗi tải", LUI.partHtml({ parts: { lessons: { error: "x" } } }, {})
  .includes(vi["lessons.error_load"]));
const r = LUI.actionRequest("việt", "b", "unlimited");
check("Hạn mức -> POST /agents/{slug}/budget, Không giới hạn gửi 'unlimited', số gửi số",
  r.url === "/agents/vi%E1%BB%87t/budget?brain=b" && r.body.daily_calls === "unlimited"
  && LUI.actionRequest("viet", "b", "4").body.daily_calls === 4);

// Sổ JavisPulseParts: agent-pulse.js gọi render(view) và bọc trong .pulse-part
const wrapped = P.partsHtml(view, [LUI.part]);
check("góp vào bảng Nhịp qua sổ đăng ký (render(view) -> HTML)", wrapped.includes('data-part="lessons"') &&
  wrapped.includes(vi["lessons.title"]));

// Chỗ nối
check("index.html nạp agent-lessons-ui.js sau agent-pulse.js", read("index.html").indexOf("agent-lessons-ui.js") >
  read("index.html").indexOf("agent-pulse.js") && read("index.html").includes("/static/agent-lessons-ui.js"));
check("CSS: chữ 16px, ô chọn 44px", /\.lessons-part \{ font-size: 16px/.test(read("console.css"))
  && /\.lessons-budget select \{ min-height: 44px; font-size: 16px/.test(read("console.css")));
check("bảng giới hạn của teams.js có nhãn agent_daily_calls, chỉ đúng chỗ chỉnh mới", read("teams.js").includes(
  'agent_daily_calls: "teams.limits.agent_daily_calls"') && vi["teams.limits.agent_daily_calls"].includes(vi["lessons.title"]));
const keys = Array.from(new Set((lsrc.match(/"lessons\.[a-z_.]+"/g) || []).map((s) => s.slice(1, -1))));
const miss = keys.filter((k) => !(k in vi) || !(k in en));
check("mọi khoá lessons.* của file có ở vi và en", keys.length >= 9 && miss.length === 0, miss.join(", "));
check("không em dash / en dash", !/[\u2013\u2014]/.test(lsrc + vi["lessons.title"] + en["lessons.title"]));

// 0.190.0: bản gọn trong cột Cài đặt của trợ lý: một dòng lời thường, không số kỹ thuật.
const cap = LUI.capHtml(view);
check("bản gọn: 'Tự làm tối đa [6] lần mỗi ngày' và số lần hôm nay, không 'giữ lượt', không nút i",
  cap.includes(vi["lessons.cap_before"]) && cap.includes(vi["lessons.cap_after"]) && cap.includes('<option value="6" selected>')
  && cap.includes(vi["lessons.cap_today"].replace("{used}", "2")) && !cap.includes("info-body")
  && !cap.includes(vi["lessons.budget_line"].split("{")[0]), cap);
check("bản gọn dùng chung ô chọn và đường lưu, vẽ lại đúng bản gọn sau khi lưu",
  cap.includes('class="lessons-part lessons-cap" data-compact="1" data-slug="viet"') && cap.includes("lessons-budget-sel")
  && /data-compact"\) === "1"\) \{ box\.outerHTML = capHtml\(view, o\); return; \}/.test(lsrc));
const comp = P.compactHtml(Object.assign({}, view, { proposals: [
  { id: 1, title: "Mở việc tuần", status: "pending", context_ref: "dm:ag_1" },
  { id: 2, title: "Đã bác", status: "rejected", context_ref: "dm:ag_1" }], contexts: [{ context_ref: "dm:ag_1" }] }),
  { registry: [LUI.part] });
check("bảng Nhịp bản gọn: dòng hạn mức + đề xuất ĐANG CHỜ (nút Nhận/Bác), không nhịp, không đề xuất đã quyết",
  comp.includes(vi["lessons.cap_before"]) && comp.includes("Mở việc tuần") && comp.includes('data-pulse-act="proposal_accept"')
  && !comp.includes("Đã bác") && !comp.includes("pulse-max-sel") && !comp.includes(vi["pulse.title"]), comp);
check("cột Cài đặt gắn bảng Nhịp ở bản gọn", /JavisPulse\.mount\(ph, \{ slug: item\.slug, brain: brain\(\), compact: true \}\)/
  .test(read("workspace.js")) && /o\.compact \? compactHtml\(view, o\) : panelHtml\(view, o\)/.test(read("agent-pulse.js")));

// Smoke T3: Auto đang bật mà chưa có nhịp thì không khuyên bật Auto.
{
  const panel = P.panelHtml({ resonance: true, contexts: [], parts: {} }, { slug: "lan", registry: [] });
  check("smoke T3: Auto đang bật mà chưa có nhịp thì không khuyên bật Auto", panel.includes(vi["pulse.empty_waiting"])
    && !panel.includes(vi["pulse.empty"]) && !!en["pulse.empty_waiting"], panel);
}

console.log(fails ? `\n${fails} FAIL` : "\nALL OK");
process.exit(fails ? 1 : 0);
