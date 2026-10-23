/* 0.298.0: male/female for every voice, the call/reading mismatch, the Edge voice synced from the server, and the
   agent editor's save bar. Run: node tests/js/test_giong_va_nut_luu.js
   Owner 23/10/2026: "cài đặt là nữ nhưng khi nói là giọng nói nam" and "nút lưu trong cài đặt agent nữa cũng không
   thể hiện rõ". No em dash in this file. */
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const VC = require("../../dashboard/voice-catalog.js");

const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

// ---- 1. voice-catalog.js ----
check("ChatGPT Live voices: juniper female, cove male", VC.gioiCua("juniper") === "f" && VC.gioiCua("cove") === "m");
check("Gemini voices are matched without case", VC.gioiCua("Kore") === "f" && VC.gioiCua("Puck") === "m");
check("the provider prefix of a list value is ignored", VC.gioiCua("edge:vi-VN-HoaiMyNeural") === "f" && VC.gioiCua("openai:onyx") === "m");
check("'auto' reads with female native voices", VC.gioiCua("edge:auto") === "f");
check("unknown or ElevenLabs voices are neither", VC.gioiCua("elevenlabs") === "n" && VC.gioiCua("") === "n" && VC.gioiCua(null) === "n");
check("display name is capitalised", VC.tenDep("juniper") === "Juniper" && VC.tenDep("") === "");
const g = VC.nhomTheoGioi(["juniper", "cove", "alloy", "maple"]);
check("grouping keeps the order inside each gender", g.f.join() === "juniper,maple" && g.m.join() === "cove" && g.n.join() === "alloy");
check("mismatch: male call voice, female reading voice", JSON.stringify(VC.lechGioi("cove", "vi-VN-HoaiMyNeural")) === '{"goi":"m","doc":"f"}');
check("no mismatch for the same gender or an unknown voice",
  VC.lechGioi("juniper", "vi-VN-HoaiMyNeural") === null && VC.lechGioi("cove", "elevenlabs") === null);
check("first voice of a gender", VC.giongCungGioi(["cove", "spruce", "juniper"], "f") === "juniper" && VC.giongCungGioi(["cove"], "f") === "");

// ---- 2. wiring ----
const html = read("dashboard/index.html"), app = read("dashboard/app.js"), cs = read("dashboard/console.js");
check("index.html loads voice-catalog.js before console.js",
  html.indexOf("/static/voice-catalog.js") > 0 && html.indexOf("/static/voice-catalog.js") < html.indexOf("/static/console.js"));
check("the voice card has the mismatch box and a saved mark beside each list",
  ["vcMismatch", "vcMismatchFix", "vcVoiceSaved", "vcReadSaved", "vcVoiceLbl", "vcVoiceSub"].every(id => html.includes(`id="${id}"`)));
check("app.js applies the server's Edge voice to this browser on load",
  /v\.edge_voice && v\.edge_voice !== vs\.value/.test(app) && /vs\.dispatchEvent\(new Event\("change"\)\)/.test(app));
check("console.js saves the Edge voice on the server", /edge_voice: val\.slice\(5\)/.test(cs));

// ---- 3. agent save bar (studio.js) ----
const st = read("dashboard/studio.js"), css = read("dashboard/console.css");
check("save button has an icon and says Save changes / Create agent",
  /id="saveAg"[^>]*>\$\{ic\("save"\)\} \$\{esc\(a \? t\("studio\.save_changes"\) : t\("studio\.create_agent"\)\)\}/.test(st));
check("the bar has a live state line", st.includes('id="agSaveState" aria-live="polite"'));
check("edits mark the form unsaved, a save says Saved", st.includes('datTrangThai("dirty")') && st.includes('datTrangThai("saved")'));
check("Ctrl/Cmd+S saves", /\(e\.ctrlKey \|\| e\.metaKey\) && \(e\.key === "s" \|\| e\.key === "S"\)\) \{ e\.preventDefault\(\); box\.querySelector\("#saveAg"\)\.click\(\); \}/.test(st));
check("the avatar picker's first report is not an edit", st.includes("if (avatarSan) danhDau()") && st.includes("avatarSan = true;"));
check("save button is the filled primary colour and the bar stays pinned",
  /\.agent-editor \.ag-save-btn \{[^}]*background:var\(--accent-solid\)/.test(css) && /#wsAgentForm\.agent-editor \.editor-actions \{ bottom:0; \}/.test(css));

const vi = JSON.parse(read("dashboard/i18n/vi.json")), en = JSON.parse(read("dashboard/i18n/en.json"));
for (const k of ["studio.save_changes", "studio.create_agent", "studio.unsaved", "studio.saving", "studio.saved_ok", "studio.save_hint",
  "settings.vc_g_f", "settings.vc_g_m", "settings.vc_grp_f", "settings.vc_grp_m", "settings.vc_grp_other", "settings.vc_voice_call",
  "settings.vc_voice_sub_basic", "settings.vc_voice_sub_live", "settings.vc_mismatch", "settings.vc_mismatch_fix", "settings.vc_saved_short",
  "settings.vc_read_sub"])
  check("i18n vi+en has " + k, typeof vi[k] === "string" && typeof en[k] === "string");
for (const f of ["dashboard/voice-catalog.js", "tests/js/test_giong_va_nut_luu.js"])
  check("no em or en dash in " + f, !read(f).includes(String.fromCharCode(0x2014)) && !read(f).includes(String.fromCharCode(0x2013)));

if (fails.length) { console.log("\nFAIL - " + fails.length); process.exit(1); }
console.log("\nOK - test_giong_va_nut_luu");
