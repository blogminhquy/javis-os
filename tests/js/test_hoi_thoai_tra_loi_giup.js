/* "A.I. reply", the draft box and "Ask the A.I. to answer this" in the inbox: guarded by code structure, and the draft
   box builder of inbox-v5.js runs for real.

       node tests/js/test_hoi_thoai_tra_loi_giup.js

   0.65.5 had two buttons ("answer this message" and "suggest a reply") over the composer. Chatbot v5 (owner,
   2026-10-28: "nhiều khi anh gõ kiểu ra lệnh để nó trả lời khách") replaced them:
     1. The composer has Send (sent word for word) and "A.I. reply": what is typed is an ORDER for the A.I.; an empty box
        lets it read the chat and write on its own. The result is always a draft, never sent by itself.
     2. The draft (from the drafts mode or from an order) sits in a dashed box with Discard / Rewrite / Send; Rewrite asks
        again with the same order; the owner's edits survive the 5-second redraws; Send goes through POST /draft.
     3. Under a message the bot stayed silent on: "Ask the A.I. to answer this" answers and sends now.
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const CV = src("dashboard/conversations.js");
const V5SRC = src("dashboard/inbox-v5.js");
const CSS = src("dashboard/inbox-v5.css");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : "")); if (!cond) fails.push(name); };
const fnBody = (sig) => { const i = CV.indexOf(sig); if (i < 0) return ""; const j = CV.indexOf("\n  }\n", i); return CV.slice(i, j); };

const win = { t: (k, v) => k + (v ? "#" + Object.keys(v).map((x) => v[x]).join(",") : "") };
const ctx = { window: win, console, String, Object, Array, Number, JSON };
vm.createContext(ctx);
vm.runInContext(V5SRC, ctx);
const V = win.JavisInboxV5;

// ---- 1. composer ----
const COMP = fnBody("function veCompose(c) {");
check("composer: one box, 'A.I. reply' next to Send (only when a bot is on duty)", /class="ib-cin"/.test(COMP) &&
  /\(laBot \? '<button type="button" class="s-btn-ghost ib-ask"/.test(COMP) && /class="s-btn ht-send"/.test(COMP));
check("no notes around the reply box (owner, 2026-10-28); a personal account says 'Send as <name>' in the placeholder (0.397.0)",
  !/ib\.send_takes_over|ib\.cmd_hint|ht-compose-note/.test(COMP) && /var ten = k\.kind === "account" \? accLabel\(c\) \|\| k\.nhan : "";/.test(COMP) &&
  /t\(laBot \? "ib\.cin_ph_as_ai" : "ib\.cin_ph_as", \{ ten: ten \}\)/.test(COMP));
const AI = fnBody("async function aiReply(c, lenh, kind) {");
check("'A.I. reply' sends the typed text as the instruction, always as a draft", /\/ai-reply", \{ method: "POST", body: fd\(\{ mode: "draft", instruction: lenh \|\| "" \}\) \}/.test(AI));
check("the A.I. button passes what is typed; Rewrite passes the draft's own order", /aiReply\(c, ta\.value\.trim\(\), "ask"\)/.test(CV) &&
  /aiReply\(c, dr\.instruction \|\| "", "redo"\)/.test(CV));
check("while the A.I. writes, its buttons are locked and say so (no double press)", /if \(_aiBusy\) return;/.test(AI) &&
  /_aiBusy === "ask" \? "loader" : "sparkles"/.test(COMP) && /_aiBusy \? " disabled" : ""/.test(COMP));
check("after a good answer the order leaves the box; an error or a silent A.I. says it in one line", /if \(kind === "ask"\) \{ var ta = /.test(AI) &&
  /ta\.value = ""/.test(AI) && /ht\.act_fail/.test(AI) && /ib\.ai_silent/.test(AI));
check("lỗi mạng cũng được báo, không nuốt", /catch \(e\) \{ loi = e\.message; \}/.test(AI));

// ---- 2. draft box ----
const d1 = V.draftHtml({ text: "Dạ <b>", instruction: "báo giá sỉ" }, "", null);
check("draft box: the order in its title, the text editable and escaped, Discard / Rewrite / Send",
  /ib\.dr_cmd#báo giá sỉ/.test(d1) && /<textarea class="ib-draft-t" rows="3">Dạ &lt;b&gt;<\/textarea>/.test(d1) &&
  /ib-dr-drop/.test(d1) && /ib-dr-redo/.test(d1) && /ib-dr-send/.test(d1));
check("a draft of the drafts mode has no order in its title", /ib\.dr_ready/.test(V.draftHtml({ text: "x" })));
const d2 = V.draftHtml({ text: "x" }, "send", (n) => "[" + n + "]");
check("while sending, the three buttons are disabled and Send spins", (d2.match(/ disabled/g) || []).length === 3 && /\[loader\] ib\.dr_send/.test(d2));
check("the draft box shows whenever the chat has a waiting draft, whatever the mode", /var draft = c\.draft && String\(c\.draft\.text \|\| ""\)\.trim\(\) \? c\.draft : null;/.test(COMP) &&
  /\(draft && V \? V\.draftHtml\(draft/.test(COMP));
check("the owner's edits to the draft survive the 5-second redraw (same draft only)", /if \(_draftEdit && _draftEdit\.ts === dr\.ts\) dt\.value = _draftEdit\.text;/.test(CV) &&
  /dt\.oninput = function \(\) \{ _draftEdit = \{ ts: dr\.ts, text: dt\.value \}; \};/.test(CV));
const SEND = fnBody("async function sendDraft(c) {");
check("Send posts the edited text to /draft action=send", /\/draft", \{ method: "POST", body: fd\(\{ action: "send", text: txt \}\) \}/.test(SEND));
check("Discard posts action=discard and says so in a toast", /\/draft", \{ method: "POST", body: fd\(\{ action: "discard" \}\) \}/.test(fnBody("async function dropDraft(c) {")) &&
  /toast\(window\.t\("ib\.t_dropped"\)\)/.test(CV));

// ---- 3. ask the A.I. now ----
const NOW = fnBody("async function askNow(c) {");
check("'Ask the A.I. to answer this' answers and sends now (mode send)", /\/ai-reply", \{ method: "POST", body: fd\(\{ mode: "send" \}\) \}/.test(NOW));
check("gửi hỏng mà A.I. đã soạn: chữ đổ vào ô nhập để chủ gửi tay, kèm dòng báo lỗi", /if \(loi && d\.text\)/.test(NOW) && /ta\.value = d\.text/.test(NOW) &&
  /ht\.act_send_failed/.test(NOW));
check("gửi xong nói có dạy bot hay không (taught)", /d\.taught \? "ib\.t_sent_taught" : "ib\.t_sent"/.test(NOW));
check("giao diện đọc bot_running từ server", /_running = !!d\.bot_running/.test(CV));
check("đổi cuộc chat thì bỏ dòng ghi chú cũ và bản sửa nháp cũ", /_chon = id;\s*_dauVetTin = "";\s*_actNote = null;/.test(CV) &&
  /if \(id !== _chon\) \{[^}]*_draftEdit = null;/.test(CV));

// ---- CSS and dictionary ----
check("CSS: dashed draft box, composer row, phone layout puts the box on its own line", /\.ib-draft \{ border: 1\.5px dashed/.test(CSS) &&
  /\.ib-cin \{ display: flex;/.test(CSS) && /\.ib-cin textarea \{ flex-basis: 100%; \}/.test(CSS));
const keys = ["ib.ai_reply", "ib.ai_reply_t", "ib.ai_busy", "ib.cin_ph_ai", "ib.dr_cmd", "ib.dr_ready", "ib.dr_drop", "ib.dr_redo",
  "ib.dr_send", "ib.ask_ai_now", "ib.ai_silent", "ib.t_sent", "ib.t_sent_taught", "ib.t_dropped", "ht.act_fail", "ht.act_send_failed"];
check("khoá có ở cả vi và en", keys.every((k) => VI[k] && EN[k]), keys.filter((k) => !VI[k] || !EN[k]).join(","));
check("the old two buttons and their keys are gone", !/renderActions|onAction\(|setActionNote|ht\.act_answer|ht\.act_draft"|ht\.why_/.test(CV) &&
  ["ht.act_answer", "ht.act_draft", "ht.act_back", "ht.why_human", "ht.act_overwrite"].every((k) => !(k in VI) && !(k in EN)));
check("Vietnamese says A.I. with dots on these buttons", /A\.I\./.test(VI["ib.ai_reply"]) && /A\.I\./.test(VI["ib.ask_ai_now"]));
check("không dùng em dash trong test này", fs.readFileSync(__filename, "utf8").indexOf(String.fromCharCode(0x2014)) < 0);

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_hoi_thoai_tra_loi_giup: tất cả pass");
