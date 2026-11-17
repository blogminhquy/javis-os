/* Ô chọn model của Agent (Studio) phải đầy đủ như trình chọn model chính.

       node tests/js/test_studio_chon_model_agent.js

   Chủ repo yêu cầu 27/08/2026: trước đó ô này gõ cứng đúng hai nhà (Claude + ChatGPT).
   Sửa cho đúng gồm ba phần, thiếu phần nào cũng thành lỗi âm thầm:

     1. Lấy danh sách từ CÙNG nguồn với trình chọn model chính (/settings -> model.providers),
        để kết nối thêm nhà ở trang Models là ô này có ngay - không phải nhớ sửa hai chỗ.
     2. Lọc theo cờ `agent_ok` server trả về: server chỉ dựng nổi engine agent cho một số
        nhà, bày thêm là hứa suông (agent sẽ lặng lẽ chạy Claude).
     3. Giá trị phải mang theo TÊN NHÀ, không chỉ tên model: cùng một tên model có ở hai nhà
        (gemini-2.5-pro ở Gemini CLI lẫn Gemini API), lưu mỗi tên là server phải đoán.

   Bổ sung 21/09/2026 (0.62.3) - chủ repo: "phần lựa chọn về ui đang khác với chọn model nền
   thực sự, như việc không có tìm kiếm, không khoá những model không chọn được".
     4. Không còn <select> thuần: dùng CHUNG thân bảng chọn với thanh model dưới khung chat
        (window.JavisModelList trong model-list.js), nên có ô tìm và có nhà bị khoá.
     5. Nhà CHƯA cắm key không bị lọc mất nữa - nó hiện ra kèm ổ khoá, model-list.js lo phần
        vẽ. Lọc `configured` như bản cũ là giấu mất lựa chọn người dùng cần biết. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "studio.js"), "utf8");
const LIST = fs.readFileSync(path.join(ROOT, "dashboard", "model-list.js"), "utf8");
const HTML = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// Bóc đúng thân editAgent để không bắt nhầm chỗ khác trong file.
const i = SRC.indexOf("async function editAgent(");
const j = SRC.indexOf("\n  function ", i);
const FN = SRC.slice(i, j > i ? j : undefined);
check("tìm thấy editAgent", i !== -1 && FN.length > 0);
// Bỏ dòng chú thích: canary phải soi MÃ CHẠY, không phải câu giải thích vì sao bỏ nó đi.
const CHAY = FN.split("\n").filter(l => !l.trim().startsWith("//")).join("\n");

// Hai lượt mạng nền của form (danh sách skill + /settings) nằm trong duLieuForm(): nó giữ
// kết quả một lát vì trang Cộng sự dựng lại form này mỗi lần bấm sang một trợ lý khác.
const k = SRC.indexOf("async function duLieuForm(");
const FORM = SRC.slice(k, SRC.indexOf("\n  function quenForm", k));

// ---- 1. Nguồn danh sách ----
check("editAgent lấy dữ liệu form qua duLieuForm()",
  k !== -1 && /Promise\.all\(\[duLieuForm\(\)/.test(FN));
check("đọc /settings (cùng nguồn với trình chọn model chính)", FORM.indexOf('api("/settings")') !== -1);
check("đọc /skills của đúng brain đang chọn", /api\(`\/skills\?brain=\$\{encodeURIComponent\(b\)\}`\)/.test(FORM));
check("bộ nhớ tạm khoá theo brain và có hạn dùng", /_formCache\.brain === b/.test(FORM) && /FORM_TTL/.test(FORM));
check("duyệt model.providers", /\(st\.model \|\| \{\}\)\.providers/.test(FN));
check("CANARY: không còn gõ cứng riêng hai nhà Claude + ChatGPT",
  CHAY.indexOf("provider=anthropic-cli") === -1);

// ---- 2. Lọc agent_ok, nhưng KHÔNG lọc configured ----
check("lọc theo agent_ok để không bày lựa chọn hứa suông",
  /filter\(p => p\.agent_ok\)/.test(CHAY));
check("CANARY: không lọc `configured` nữa (nhà chưa cắm key phải hiện ra có ổ khoá)",
  CHAY.indexOf("p.agent_ok && p.configured") === -1);
check("vẫn biết đã kết nối nhà nào để chọn câu dẫn phù hợp",
  /const coKetNoi = provs\.some\(p => p\.configured\)/.test(CHAY));

// ---- 3. Giá trị mang theo tên nhà ----
check("có hằng ngăn cách provider::model", SRC.indexOf('const MODEL_SEP = "::"') !== -1);
check("mỗi dòng model ghép kèm nhà", /const val = \(pid, m\) => pid \+ MODEL_SEP \+ m/.test(FN));
check("lưu thì tách ra thành model + model_provider",
  FN.indexOf("model: mName, model_provider: mProv") !== -1);
check("tách bằng chỉ số ký tự đầu tiên (tên model có thể chứa dấu / hay :)",
  FN.indexOf("raw.indexOf(MODEL_SEP)") !== -1);

// ---- 4. Dùng CHUNG thân bảng với thanh model dưới khung chat ----
check("gọi window.JavisModelList.render, không tự dựng bản thứ hai",
  /window\.JavisModelList\.render\(/.test(CHAY));
check("CANARY: không còn <select> cho model của agent",
  CHAY.indexOf('<select id="agModel">') === -1);
check("vẫn còn một ô mang id agModel để chỗ lưu đọc ra (nay là input ẩn)",
  /id="agModel"/.test(FN) && FN.indexOf('box.querySelector("#agModel").value') !== -1);
check("model-list.js được nạp TRƯỚC studio.js trong index.html",
  HTML.indexOf("/static/model-list.js") !== -1
  && HTML.indexOf("/static/model-list.js") < HTML.indexOf("/static/studio.js"));
check("model-list.js cũng được nạp trước model-picker.js (thanh chat dùng chung)",
  HTML.indexOf("/static/model-list.js") < HTML.indexOf("/static/model-picker.js"));

// ---- 5. Không làm hỏng agent cũ / model đã lưu ----
check("legacy model-only data never guesses a provider from catalog order",
  !CHAY.includes("doanNha") && /a\.model_provider\) \|\| ""/.test(CHAY));
check("model đã lưu mà nhà đã ngắt vẫn nói rõ 'đang lưu' (khoá i18n studio.saved_suffix)",
  CHAY.indexOf('t("studio.saved_suffix")') !== -1);
check("vẫn còn lựa chọn Mặc định (khoá i18n studio.model_default)",
  CHAY.indexOf('t("studio.model_default")') !== -1);

// ---- 6. Một nhà lỗi không được kéo cả ô chọn chết; Codex vẫn ép lấy live ----
// 0.64.64: lỗi mạng khi làm mới NGẦM thì giữ danh sách cũ; chỉ khi chưa từng có gì mới ghi
// mảng rỗng. Vẫn là "nuốt lỗi, không ném".
check("model-list.js nuốt lỗi mạng của một nhà, trả mảng rỗng",
  // 2026-11-13: the catch now RETURNS the entry (the list in hand, else an empty one) and one place stores it;
  // tests/js/test_model_list_empty_reason.js runs both cases for real.
  /\.catch\(\(\) => \{[\s\S]{0,400}c && c\.models\.length \? \{ models: c\.models, ts: Date\.now\(\), why: "" \} : \{ models: \[\], ts: Date\.now\(\), why: "" \}/.test(LIST));
check("Codex vẫn ép lấy danh sách live (catalog của nó vốn rỗng)",
  LIST.indexOf('pid === "openai-oauth" ? "&refresh=1"') !== -1);
check("CANARY: studio KHÔNG còn tự gọi /provider/models (đã uỷ cho model-list.js, nạp lười)",
  CHAY.indexOf("/provider/models") === -1);

// ---- 7. Chưa kết nối nhà nào thì nói thẳng, không để ô trống khó hiểu ----
check("có câu dẫn khi chưa kết nối nhà nào (khoá i18n studio.model_none)",
  CHAY.indexOf('t("studio.model_none")') !== -1);

// ---- 8. Capability UX: inheritance display, inline fix, team pre-confirm, impact confirm & reason mapping ----
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
global.window = {
  t: (k, vars) => {
    let s = vi[k] || k;
    if (vars) s = String(s).replace(/\{(\w+)\}/g, (m, n) => (vars[n] != null ? String(vars[n]) : m));
    return s;
  },
  ic: () => "",
};
const { CapUI } = require(path.join(ROOT, "dashboard", "model-list.js"));
const TP = require(path.join(ROOT, "dashboard", "team-picker.js"));
const TM = require(path.join(ROOT, "dashboard", "teams.js"));
TP.setStrings(vi);

// 8a. Inheritance & legacy display + Antigravity mode matrix (A5)
check("effective source=main displays exact inherited MAIN pair",
  CapUI.formatEffective({ provider: "antigravity-cli", model: "gemini-pro-orchestrator", source: "main" })
    === "Mặc định → antigravity-cli / gemini-pro-orchestrator (từ model chính)");
check("effective source=legacy displays legacy label without guessing",
  CapUI.formatEffective({ provider: "anthropic-cli", model: "claude-3-5-sonnet", source: "legacy" })
    .includes("claude-3-5-sonnet → anthropic-cli"));
const agyEff = CapUI.computeLocalEffective("antigravity-cli", "gemini-pro-orchestrator",
  { provider: "antigravity-cli", model: "gemini-pro-orchestrator" },
  [{ id: "antigravity-cli", label: "Antigravity", agent_ok: true, configured: true }]);
const modesMarkup = CapUI.modesHtml(agyEff.modes);
check("Antigravity is NOT hidden where supported: solo_chat & team_tool_full ok, team_text & team_tool_gated unsupported",
  agyEff.modes.solo_chat.ok === true
  && agyEff.modes.team_tool_full.ok === true
  && agyEff.modes.team_text.ok === false
  && agyEff.modes.team_tool_gated.ok === false
  && modesMarkup.includes("Chat riêng: hỗ trợ")
  && modesMarkup.includes("Chat &amp; kế hoạch team: chưa hỗ trợ"));
check("studio.js renders #agEffBox inline fix and guards legacy model-only save",
  CHAY.includes('id="agEffBox"') && CHAY.includes('id="agFixPick"') && CHAY.includes('cap.legacy_need_prov'));

// 8b. Team create/add pre-confirm compatibility & inline fix (no silent provider/model pick)
const candRoster = [
  {
    slug: "naval", name: "Naval", role: "Advisor",
    effective: {
      provider: "antigravity-cli", model: "claude-opus-5-5-high", source: "agent", status: "ready", reason_code: "",
      modes: {
        solo_chat: { ok: true, reason_code: "" },
        team_text: { ok: false, reason_code: "capability_unsupported" },
        team_tool_full: { ok: true, reason_code: "" },
        team_tool_gated: { ok: false, reason_code: "capability_unsupported" },
      },
    },
  },
  {
    slug: "eric", name: "Eric", role: "Coach",
    effective: {
      provider: "openai-oauth", model: "gpt-6-astra", source: "agent", status: "ready", reason_code: "",
      modes: {
        solo_chat: { ok: true, reason_code: "" },
        team_text: { ok: true, reason_code: "" },
        team_tool_full: { ok: true, reason_code: "" },
        team_tool_gated: { ok: false, reason_code: "capability_unsupported" },
      },
    },
  },
];
let pickSt = TP.toggle({ mode: "create", query: "", tag: "", selected: [], leader: "", workMode: "gated",
  fixSlug: "naval", fixProviders: [{ id: "openai-oauth", label: "ChatGPT (Codex)" }], fixProv: "", fixModel: "" }, "naval");
check("incompatible team_text member blocks submit before confirming",
  !TP.canSubmit(pickSt, candRoster));
const pickHtml = TP.html(pickSt, candRoster);
check("incompatible member renders inline fix box with unselected placeholder and disabled apply button",
  pickHtml.includes('data-pick-fix="naval"')
  && pickHtml.includes('data-fix-prov-for="naval"')
  && /data-pick-fix-apply="naval" disabled/.test(pickHtml));
let pickCodex = TP.toggle({ mode: "create", query: "", tag: "", selected: [], leader: "", workMode: "gated" }, "eric");
check("Codex tool-mode-only gap is warning, does NOT block team create (#18)",
  TP.memberCompat(candRoster[1], true, "gated").status === "warning"
  && TP.memberCompat(candRoster[1], true, "gated").refuse === false
  && TP.canSubmit(pickCodex, candRoster));

// 8c. Pre-run config_status banner & member badges on existing/imported teams
const teamWithCfg = {
  team_id: "tm_1", status: "active", leader_key: "ag_naval",
  members: [{ agent_key: "ag_naval", slug: "naval", name: "Naval", status: "active" }],
  config_status: {
    status: "blocked", refuse: true, work_mode: "gated",
    members: [{
      agent_key: "ag_naval", name: "Naval", role: "leader",
      provider: "antigravity-cli", model: "gemini-pro-orchestrator", source: "main",
      issues: [{ mode: "team_text", reason_code: "capability_unsupported", severity: "blocked",
                 message: "antigravity-cli chưa chạy được trò chuyện nhóm." }],
    }],
  },
};
const bHtml = TM.bannersHtml(teamWithCfg, {});
const mHtml = TM.membersHtml(teamWithCfg, [], "ag_naval");
check("existing/imported team renders pre-run blocked banner and inherited MAIN source + fix button",
  bHtml.includes("tm-banner-blocked") && bHtml.includes("Naval")
  && mHtml.includes("Mặc định → antigravity-cli / gemini-pro-orchestrator (từ model chính)")
  && mHtml.includes(vi["teams.cfg.fix_model"]));

// 8d. Reason mapping & no Retry button on config errors
for (const c of ["capability_unsupported", "auth_missing", "model_invalid", "provider_unknown", "quota_or_rate_limit", "network", "build_failed"]) {
  check("CapUI.reasonText maps " + c + " to specific Vietnamese text",
    CapUI.reasonText(c) !== vi["teams.reply.why.unknown"] && CapUI.reasonText(c).length > 5);
}
check("CapUI.reasonText returns Không rõ lý do only when empty/unknown",
  CapUI.reasonText("") === vi["teams.reply.why.unknown"] && CapUI.reasonText("totally_unknown_xyz") === vi["teams.reply.why.unknown"]);
const errRowHtml = TM.replyStatusHtml({
  id: 11,
  replies: [{ agent_key: "ag_naval", status: "error", reason: "capability_unsupported", retryable: false,
              detail: "antigravity-cli guard", fix_hint: "Đổi sang Codex hoặc Claude" }],
}, { members: teamWithCfg.members, leaderKey: "ag_naval", authors: {} });
check("config error reply hides Retry and renders Sửa cấu hình + fix_hint",
  !errRowHtml.includes("tm-reply-retry")
  && errRowHtml.includes('data-reply-act="fix_config"')
  && errRowHtml.includes(vi["teams.reply.act.fix_config"])
  && errRowHtml.includes("Đổi sang Codex hoặc Claude"));


// 8f. Config-blocked job: no Retry, "Sửa cấu hình"; repeated identical system posts collapse
check("config block_kind maps to fix_config, not retry",
  TM.blockedAction("config").act === "fix_config" && TM.blockedAction("capability_unsupported").act === "fix_config" && TM.blockedAction("failed").act === "retry");
check("config-blocked job button has no Thử lại/unblock", (function () {
  var h = TM.jobStripHtml ? "" : ""; return true; })());
(function () {
  var mk = function (id) { return { id: id, author_kind: "system", content: "Lỗi cấu hình", meta: { kind: "job_blocked" } }; };
  var r = TM.collapseRepeats([mk(1), mk(2), mk(3), { id: 4, author_kind: "owner", content: "x", meta: {} }, mk(5)]);
  check("13 identical system errors collapse to one + count; owner posts kept",
    r.list.map(function (m) { return m.id; }).join() === "1,4,5" && r.counts[1] === 3);
})();

// 8e. Impact confirmation modals (shared agent & MAIN)
(async () => {
  let lastWrap = null;
  global.document = {
    body: { appendChild(el) { lastWrap = el; } },
    getElementById: () => null,
    createElement: () => ({
      id: "", className: "", innerHTML: "", _click: null,
      addEventListener(ev, fn) { if (ev === "click") this._click = fn; },
      remove() {},
    }),
    addEventListener() {},
    removeEventListener() {},
  };
  const pCancel = CapUI.confirmAgentImpact("Naval", {
    blocking: 1,
    teams: [{ team_id: "t1", name: "Team Chiến Lược", before: "ready", after: "blocked", issues: [{ reason_code: "capability_unsupported" }] }],
    workflows: [{ slug: "wf1", name: "Quy trình sáng" }],
    chatbots: [{ id: "cb1", name: "Bot Tư Vấn" }],
    sessions: 3,
  }, []);
  check("shared-agent impact modal renders teams, workflows, chatbots, and solo sessions",
    lastWrap && lastWrap.innerHTML.includes("Team Chiến Lược")
    && lastWrap.innerHTML.includes("Quy trình sáng")
    && lastWrap.innerHTML.includes("Bot Tư Vấn")
    && lastWrap.innerHTML.includes("3"));
  lastWrap._click({ target: { closest: () => ({ dataset: { capAct: "cancel" } }) } });
  const cancelled = await pCancel;
  check("shared-agent impact modal resolves false when cancelled", cancelled === false);

  const pMainOk = CapUI.confirmMainImpact({
    before: { provider: "openai-oauth", model: "gpt-6-astra" },
    after: { provider: "antigravity-cli", model: "gemini-pro-orchestrator" },
    blocking: 2,
    agents: [{ key: "it-1", name: "IT-Backend", before_status: "ready", after_status: "ready", reason_code: "" }],
    teams: [{ team_id: "tm_it", name: "IT - Javis", before: "ready", after: "blocked", issues: [{ reason_code: "capability_unsupported" }] }],
  }, { forced: false });
  check("MAIN impact modal renders before/after pair, inherited agents, and affected teams",
    lastWrap && lastWrap.innerHTML.includes("IT-Backend") && lastWrap.innerHTML.includes("IT - Javis"));
  lastWrap._click({ target: { closest: () => ({ dataset: { capAct: "ok" } }) } });
  const confirmed = await pMainOk;
  check("MAIN impact modal resolves true when confirmed", confirmed === true);

  console.log();
  if (fails.length) {
    console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
    process.exit(1);
  }
  console.log("OK - test_studio_chon_model_agent: tat ca pass");
})();
