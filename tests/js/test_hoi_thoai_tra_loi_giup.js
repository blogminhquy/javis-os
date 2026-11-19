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
check("composer: one box, 'A.I. reply' next to Send (only when a bot is on duty, not while messaging a commenter privately)", /class="ib-cin"/.test(COMP) &&
  /\(laBot && !priv \? '<button type="button" class="s-btn-ghost ib-ask"/.test(COMP) && /class="s-btn ht-send"/.test(COMP));
check("no notes around the reply box (owner, 2026-10-28); a personal account says 'Send as <name>' in the placeholder (0.397.0)",
  !/ib\.send_takes_over|ib\.cmd_hint|ht-compose-note/.test(COMP) && /var ten = k\.kind === "account" \? accLabel\(c\) \|\| k\.nhan : "";/.test(COMP) &&
  /t\(laBot \? "ib\.cin_ph_as_ai" : "ib\.cin_ph_as", \{ ten: ten \}\)/.test(COMP));
const AI = fnBody("async function aiReply(c, lenh, kind) {");
check("'A.I. reply' sends the typed text as the instruction, always as a draft, and asks for the streamed stages",
  /\/ai-reply", \{ method: "POST", body: fd\(\{ mode: "draft", instruction: lenh \|\| "", stream: "1" \}\) \}/.test(AI));
check("the A.I. button passes what is typed; Rewrite passes the draft's own order", /aiReply\(c, ta\.value\.trim\(\), "ask"\)/.test(CV) &&
  /aiReply\(c, dr\.instruction \|\| "", "redo"\)/.test(CV));
check("while the A.I. writes, its buttons are locked and say so (no double press)", /if \(_aiBusy\) return;/.test(AI) &&
  /_aiBusy === "ask" \? spin\(\) : ic\("sparkles"\)/.test(COMP) && /_aiBusy \? " disabled" : ""/.test(COMP));
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
  /draft && V \? V\.draftHtml\(draft/.test(COMP));
check("the owner's edits to the draft survive the 5-second redraw (same draft only)", /if \(_draftEdit && _draftEdit\.ts === dr\.ts\) dt\.value = _draftEdit\.text;/.test(CV) &&
  /dt\.oninput = function \(\) \{ _draftEdit = \{ ts: dr\.ts, text: dt\.value \}; showLearn\(\); \};/.test(CV));
// "Bot học câu này" (owner 2026-11-19): ticked by default; shown with the owner's order, revealed once the owner rewrites.
check("draft box: a ticked 'Bot học câu này', shown when the draft carries the owner's order",
  /<label class="ib-dr-learn" title="ib\.dr_learn_t"><input type="checkbox" class="ib-dr-learn-c" checked> <span>ib\.dr_learn<\/span><\/label>/.test(d1));
check("draft box: hidden on a plain A.I. draft until the owner rewrites it",
  /<label class="ib-dr-learn" hidden/.test(V.draftHtml({ text: "x" })) &&
  /ll\.hidden = !\(String\(dr\.instruction \|\| ""\)\.trim\(\) \|\| dt\.value\.trim\(\) !== String\(dr\.text \|\| ""\)\.trim\(\)\)/.test(CV));
check("the tick survives the 5-second redraw (same draft only)",
  /if \(_draftLearn && _draftLearn\.ts === dr\.ts\) lc\.checked = _draftLearn\.on;/.test(CV));
const SEND = fnBody("async function sendDraft(c) {");
check("Send posts the edited text to /draft action=send, with learn only when the tick is shown and on",
  /\/draft", \{ method: "POST", body: fd\(\{ action: "send", text: txt, learn: learn \}\) \}/.test(SEND) &&
  /var learn = lc && ll && !ll\.hidden && lc\.checked \? "1" : "0";/.test(SEND));
check("a learned reply says so in a toast", /if \(r && r\.learned\) toast\(window\.t\("ib\.t_learned"\)\);/.test(SEND));
check("the learn keys are in vi and en, the label short", ["ib.dr_learn", "ib.dr_learn_t", "ib.t_learned"].every((k) => VI[k] && EN[k]) &&
  VI["ib.dr_learn"] === "Bot học câu này" && VI["ib.dr_learn_t"].length <= 100 && EN["ib.dr_learn_t"].length <= 100);
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

// ---- 4. "A.I. is writing" box (owner 2026-11-18: a still button made people think it had broken) ----
check("the page's icon helper passes options, so a loader can spin", /var ic = function \(n, o\) \{ return window\.ic \? window\.ic\(n, o\) : ""; \};/.test(CV) &&
  /var spin = function \(\) \{ return ic\("loader", \{ cls: "ic-spin" \}\); \};/.test(CV) && !/ic\("loader"\)/.test(CV));
check("while it writes for this chat, the live box stands where the draft lands", /var writing = \(_aiBusy === "ask" \|\| _aiBusy === "redo"\) && _aiWork && _aiWork\.conv === c\.id;/.test(COMP) &&
  /\(writing && V \? V\.workingHtml\(aiWorkView\(\), ic\) : draft && V \? V\.draftHtml\(/.test(COMP));
check("stages from the stream repaint only the box, a one-second ticker moves the seconds, the ticker stops at the end",
  /ev\.type === "stage"/.test(AI) && /paintAiWork\(\)/.test(AI) && /startAiTick\(\);/.test(AI) && /stopAiTick\(\);/.test(AI) &&
  /setInterval\(paintAiWork, 1000\)/.test(CV) && !/function startAiTick\(\) \{[^}]*stopAiTick/.test(CV) &&
  CV.indexOf("_aiWork = { stage:") < CV.indexOf("startAiTick();"));
const RS = fnBody("async function readAiStream(r, onEvent) {");
check("the stream reader keeps the final answer, falls back to plain JSON, and says when the stream was cut",
  /ev\.type === "done"/.test(RS) && /text\/event-stream/.test(RS) && /await r\.json\(\)/.test(RS) && /lost: true/.test(RS) && /ib\.aiw_lost/.test(AI));
win.t = (k, v) => k + (v ? "#" + Object.keys(v).map((x) => v[x]).join(",") : "");
const w1 = V.workingHtml({ stage: "Đang <viết>", secs: "7 giây", slow: false, order: "báo giá" }, (n, o) => "[" + n + (o ? "+" : "") + "]");
check("working box: pulsing sparkle, stage escaped and announced, seconds, the order, three moving lines, slow note hidden",
  /class="ib-draft ib-aiw"/.test(w1) && /\[sparkles\]/.test(w1) && /role="status" aria-live="polite">Đang &lt;viết&gt;</.test(w1) &&
  /class="ib-aiw-s">7 giây</.test(w1) && /ib\.aiw_order#báo giá/.test(w1) && (w1.match(/<span><\/span>/g) || []).length === 3 &&
  /class="ib-aiw-slow" hidden>/.test(w1));
check("past the slow mark the calm note shows; no order means no order line", /class="ib-aiw-slow">ib\.aiw_slow/.test(V.workingHtml({ slow: true })) &&
  !/ib-aiw-o/.test(V.workingHtml({ slow: true })));
check("sending the draft spins its loader", /\[loader\+\] ib\.dr_send/.test(V.draftHtml({ text: "x" }, "send", (n, o) => "[" + n + (o ? "+" : "") + "]")));
check("CSS: the box moves, and stays still under reduced motion", /@keyframes ib-aiw-shimmer/.test(CSS) && /@keyframes ib-aiw-pulse/.test(CSS) &&
  /prefers-reduced-motion: reduce\) \{ \.ib-aiw-ic, \.ib-aiw-lines span \{ animation: none; \} \}/.test(CSS) && /\.ib-aiw-slow\[hidden\] \{ display: none; \}/.test(CSS));
const wkeys = ["ib.aiw_read", "ib.aiw_docs", "ib.aiw_image", "ib.aiw_think", "ib.aiw_tool", "ib.aiw_write", "ib.aiw_send", "ib.aiw_secs",
  "ib.aiw_order", "ib.aiw_slow", "ib.aiw_lost"];
check("working box keys in vi and en", wkeys.every((k) => VI[k] && EN[k]), wkeys.filter((k) => !VI[k] || !EN[k]).join(","));

// ---- CSS and dictionary ----
check("CSS: dashed draft box, composer row, phone layout puts the box on its own line", /\.ib-draft \{ border: 1\.5px dashed/.test(CSS) &&
  /\.ib-cin \{ display: flex;/.test(CSS) && /\.ib-cin textarea \{ flex-basis: 100%; \}/.test(CSS));
const keys = ["ib.ai_reply", "ib.ai_reply_t", "ib.ai_busy", "ib.cin_ph_ai", "ib.dr_cmd", "ib.dr_ready", "ib.dr_drop", "ib.dr_redo",
  "ib.dr_send", "ib.ask_ai_now", "ib.ai_silent", "ib.t_sent", "ib.t_sent_taught", "ib.t_dropped", "ht.act_fail", "ht.act_send_failed"];
check("khoá có ở cả vi và en", keys.every((k) => VI[k] && EN[k]), keys.filter((k) => !VI[k] || !EN[k]).join(","));
check("the old two buttons and their keys are gone", !/renderActions|onAction\(|setActionNote|ht\.act_answer|ht\.act_draft"|ht\.why_/.test(CV) &&
  ["ht.act_answer", "ht.act_draft", "ht.act_back", "ht.why_human", "ht.act_overwrite"].every((k) => !(k in VI) && !(k in EN)));
check("Vietnamese says A.I. with dots on these buttons; the draft button is named Javis (owner 2026-11-19)",
  VI["ib.ai_reply"] === "Javis soạn" && /A\.I\./.test(VI["ib.ask_ai_now"]));
check("không dùng em dash trong test này", fs.readFileSync(__filename, "utf8").indexOf(String.fromCharCode(0x2014)) < 0);

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_hoi_thoai_tra_loi_giup: tất cả pass");
