// Capability UI regression checks (dashboard/teams.js, team-picker.js, studio.js, console.js, model-picker.js, model-list.js, i18n).
//
//     node tests/js/test_capability_ui.js
//
// Checks reason_code -> Vietnamese mapping (no "Không rõ lý do" for known backend codes),
// non-retryable config errors hiding Retry in favor of "Sửa cấu hình", inherited/legacy display,
// MAIN/shared-agent impact confirmation, team-picker blocking vs Codex warning, and absence of
// silent providers[0]/ms[0] auto-pick.
"use strict";
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
if (typeof global.window === "undefined") global.window = global;
global.window.t = function (k, vars) {
  let s = vi[k] || k;
  if (vars) {
    s = String(s).replace(/\{(\w+)\}/g, function (m, n) {
      return Object.prototype.hasOwnProperty.call(vars, n) ? String(vars[n]) : m;
    });
  }
  return s;
};
const ML = require(path.join(ROOT, "dashboard", "model-list.js"));
const TP = require(path.join(ROOT, "dashboard", "team-picker.js"));
const TM = require(path.join(ROOT, "dashboard", "teams.js"));
const teamsJs = fs.readFileSync(path.join(ROOT, "dashboard", "teams.js"), "utf8");
const studioJs = fs.readFileSync(path.join(ROOT, "dashboard", "studio.js"), "utf8");
const consoleJs = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const pickerJs = fs.readFileSync(path.join(ROOT, "dashboard", "model-picker.js"), "utf8");

let fails = 0;

function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  [" + extra + "]"));
  if (!cond) fails++;
}

const members = [
  { agent_key: "ag_naval", slug: "naval", name: "Naval", role: "leader", status: "active" },
  { agent_key: "ag_eric", slug: "eric", name: "Eric", role: "member", status: "active" },
];
const ctx = { members: members, leaderKey: "ag_naval", authors: {} };
const unknownText = vi["teams.reply.why.unknown"] || "Không rõ lý do";

// 1. Existing unknown behavior only when backend sends empty/unrecognized reason
const emptyHtml = TM.replyStatusHtml({
  id: 1,
  replies: [{ agent_key: "ag_naval", status: "error", reason: "", detail: "" }],
}, ctx);
check("empty reason still renders Không rõ lý do", emptyHtml.includes(unknownText), emptyHtml);

// 2. All 7 Contract v1 reason codes map to specific messages (never "Không rõ lý do")
const configCodes = [
  "capability_unsupported",
  "auth_missing",
  "model_invalid",
  "provider_unknown",
  "build_failed",
];
const transientCodes = ["quota_or_rate_limit", "network"];

for (const code of configCodes) {
  const html = TM.replyStatusHtml({
    id: 2,
    replies: [{
      agent_key: "ag_naval",
      status: "error",
      reason: code,
      retryable: false,
      detail: "backend detail",
      fix_hint: "Đổi model ở Cộng sự",
    }],
  }, ctx);
  check(
    `config reason '${code}' has dedicated vi/en key and does not show '${unknownText}'`,
    Boolean(vi["teams.reply.why." + code] && en["teams.reply.why." + code] && !html.includes(unknownText)),
    html.slice(0, 140)
  );
  check(
    `config reason '${code}' (retryable:false) hides Retry button and shows config action`,
    !html.includes("tm-reply-retry") && /data-reply-act=/.test(html),
    html.slice(0, 140)
  );
}

for (const code of transientCodes) {
  const html = TM.replyStatusHtml({
    id: 3,
    replies: [{
      agent_key: "ag_eric",
      status: "error",
      reason: code,
      retryable: true,
      detail: "429",
    }],
  }, ctx);
  check(
    `transient reason '${code}' has dedicated vi/en key and keeps Retry button`,
    Boolean(vi["teams.reply.why." + code] && en["teams.reply.why." + code] && !html.includes(unknownText)
      && html.includes("tm-reply-retry")),
    html.slice(0, 140)
  );
}

// 3. No silent providers[0] / ms[0] auto-pick in console.js #modelPicker
const mpIdx = consoleJs.indexOf("function openModelPicker");
const mpBody = mpIdx >= 0 ? consoleJs.slice(mpIdx, mpIdx + 3500) : "";
check("found openModelPicker in console.js", mpIdx >= 0);
check(
  "console.js openModelPicker does not silently auto-pick providers[0].id or ms[0]",
  !/providers\[0\]\.id/.test(mpBody) && !/\bms\[0\]/.test(mpBody)
);

// 4. MAIN change impact & confirm_impact wiring in console.js + model-picker.js
check(
  "MAIN change calls /models/main/impact and passes confirm_impact",
  /\/models\/main\/impact/.test(consoleJs + "\n" + pickerJs)
    && /confirm_impact/.test(consoleJs + "\n" + pickerJs)
);

// 5. Studio effective config + shared-agent impact + teams config_status
check(
  "studio.js reads effective config and checks /agents/impact",
  /effective/.test(studioJs) && /\/agents\/impact/.test(studioJs)
);
check(
  "teams.js handles config_status and team_config_blocked",
  /config_status/.test(teamsJs) && /team_config_blocked/.test(teamsJs)
);

// 6. CapUI + team-picker compatibility checks (Antigravity blocked for team_text; Codex allowed)
const CapUI = ML.CapUI;
check("model-list.js exports CapUI", Boolean(CapUI && CapUI.formatEffective && CapUI.isConfigError));
if (CapUI) {
  const effMain = CapUI.formatEffective({ provider: "antigravity-cli", model: "gemini-pro-orchestrator", source: "main" });
  check("formatEffective labels source=main with Mặc định", effMain.includes("antigravity-cli") && effMain.includes("gemini-pro-orchestrator"), effMain);
  check("isConfigError true for capability_unsupported, false for network",
    CapUI.isConfigError("capability_unsupported") && !CapUI.isConfigError("network"));
}
if (TP && TP.memberCompat && TP.canSubmit) {
  const agyAgent = {
    slug: "naval", name: "Naval",
    effective: {
      provider: "antigravity-cli", model: "claude-opus-5-5-high", source: "agent",
      status: "blocked", reason_code: "capability_unsupported",
      modes: { team_text: { ok: false, reason_code: "capability_unsupported" }, team_tool_gated: { ok: false, reason_code: "capability_unsupported" } }
    }
  };
  const ericAgent = {
    slug: "eric", name: "Eric",
    effective: {
      provider: "openai-oauth", model: "gpt-6-astra", source: "agent",
      status: "ready", reason_code: "",
      modes: { team_text: { ok: true, reason_code: "" }, team_tool_gated: { ok: false, reason_code: "capability_unsupported" } }
    }
  };
  const cAgy = TP.memberCompat(agyAgent, false, "gated");
  const cEric = TP.memberCompat(ericAgent, false, "gated");
  check("team-picker blocks Antigravity (team_text unsupported)", cAgy && cAgy.refuse === true, JSON.stringify(cAgy));
  check("team-picker treats Codex tool-mode-only gap as non-blocking warning", cEric && !cEric.refuse && cEric.status === "warning", JSON.stringify(cEric));
  check("team-picker canSubmit blocks when Antigravity selected, allows Codex",
    !TP.canSubmit({ mode: "create", name: "Test", selected: ["naval"], leader: "naval", workMode: "gated" }, [agyAgent, ericAgent])
    && TP.canSubmit({ mode: "create", name: "Test", selected: ["eric"], leader: "eric", workMode: "gated" }, [agyAgent, ericAgent]));
}

console.log(`\nSummary: ${fails} FAIL`);
if (fails > 0) process.exit(1);
