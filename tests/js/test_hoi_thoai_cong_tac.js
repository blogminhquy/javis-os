/* The "Who replies" bar of a chat, the "who is handling it" sentence and the "Bot im" line of the inbox.

       node tests/js/test_hoi_thoai_cong_tac.js

   0.65.4 put a two-state switch (Auto | I reply) in the thread head and the status on its own line. Chatbot v5
   (2026-10-28, docs/dev/2026-10-chatbot-v5-spec.md section 4 and 6) replaced both with ONE bar under the chat's name, in
   the colour of who is handling the chat: three modes (A.I. replies / A.I. drafts, I approve / I reply) when the A.I.
   may answer here, "Let the A.I. answer here" when not, Allow / Dismiss when someone called it in a chat not allowed
   yet, plus one sentence the server's who_code decides. Guarded here:
     1. inbox-v5.js runs for real: which controls the bar holds in each case, the sentence for every who_code.
     2. conversations.js: the bar sits right under the head, its buttons go through setWho (POST /ai then /mode),
        the old switch and status line are gone, the "Bot im" line stays under the last message.
     3. Dictionary and CSS.
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const CV = src("dashboard/conversations.js");
const V5SRC = src("dashboard/inbox-v5.js");
const RP = src("dashboard/chatbots-reply-policy.js");
const CSS = src("dashboard/inbox-v5.css");
const OLDCSS = src("dashboard/console.css");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : "")); if (!cond) fails.push(name); };

const win = { t: (k, v) => k + (v ? "#" + Object.keys(v).map((x) => v[x]).join(",") : "") };
const ctx = { window: win, console, String, Object, Array, Number, JSON };
vm.createContext(ctx);
vm.runInContext(V5SRC, ctx);
const V = win.JavisInboxV5;

// ---- 1. the bar's controls ----
const bar = (c) => V.modeBarHtml(c);
const three = bar({ bot_id: "b", ai_allowed: true, mode: "draft" });
check("A.I. allowed here: three modes, the current one pressed", (three.match(/class="ib-m /g) || []).length === 3 &&
  /data-m="draft" aria-pressed="true"/.test(three) && /data-m="ai" aria-pressed="false"/.test(three) && /data-m="human" aria-pressed="false"/.test(three));
check("each mode has a long label and a short one for phones", /ib\.m_ai<\/span><span class="ib-l-short">ib\.m_ai_s/.test(three) &&
  /ib\.m_draft_s/.test(three) && /ib\.m_human_s/.test(three));
check("an unknown mode counts as A.I. replies", /data-m="ai" aria-pressed="true"/.test(bar({ bot_id: "b", ai_allowed: true, mode: "waiting" })));
check("not allowed here: one button to let the A.I. answer", /class="s-btn ib-allow" data-on="1"/.test(bar({ bot_id: "b", ai_allowed: false })) &&
  !/ib-m /.test(bar({ bot_id: "b", ai_allowed: false })) && /ib\.allow_here/.test(bar({ bot_id: "b", ai_allowed: false })));
const pend = bar({ bot_id: "b", ai_allowed: false, ai_pending: 2 });
check("someone called the A.I. in a chat not allowed: Allow and Dismiss", /data-on="1"/.test(pend) && /data-on="0"/.test(pend) &&
  /ib\.allow</.test(pend) && /ib\.dismiss/.test(pend));
check("no bot: offer to create one, unless the owner said no bot is needed",
  /ib-make-bot/.test(bar({ who_code: "no_bot" })) && bar({ who_code: "no_bot_wanted" }) === "");

// ---- the sentence ----
const codes = ["pending", "draft_ready", "waiting", "waiting_you", "bot_off_waiting", "ai", "draft_mode", "you", "not_allowed", "no_bot",
  "no_bot_wanted", "bot_off"];
check("every who_code the server sends has its sentence", codes.every((k) => V.whoSentence({ who_code: k, ai_pending: 1 }).indexOf("ib.wc_") === 0));
check("an unknown code falls back to 'not allowed', never a raw key", V.whoSentence({ who_code: "x" }) === "ib.wc_not_allowed");
check("pending says how many times the A.I. was called", V.whoSentence({ who_code: "pending", ai_pending: 3 }) === "ib.wc_pending#3");
check("in a group the A.I. sentence says when it speaks up", V.whoSentence({ who_code: "ai", chat_type: "group", reply_when: "auto" }) ===
  "ib.wc_ai_group#ib.khi_auto");
check("the four who labels", ["you", "ai", "owner", "log"].every((w) => V.whoLabel(w) === "ib.who_" + w) && V.whoLabel("?") === "ib.who_log");

// ---- 2. conversations.js wiring ----
const vt = CV.slice(CV.indexOf("  function veThread() {"), CV.indexOf("  // ---------------------------------------------------------------- Info panel"));
check("the bar comes right after the head, before the messages, in the colour of who handles the chat",
  vt.indexOf('class="ht-head"') < vt.indexOf('class="ib-aibar') && vt.indexOf('class="ib-aibar') < vt.indexOf('class="ht-msgs"') &&
  /'<div class="ib-aibar w-' \+ who \+ '"' \+ \(calm \? " hidden" : ""\) \+ '>'/.test(vt));
check("0.397.0: the three modes sit in the head (a chip on a narrow column); the bar hides unless the chat needs the owner",
  /var calm = threeModes && who !== "you";/.test(vt) && /\(threeModes \? '<span class="ib-hmode" title="' \+ esc\(say\) \+ '">' \+ bar/.test(vt) &&
  /V\.modeChipHtml\(c, ic\)/.test(vt) && vt.indexOf('class="ib-hmode"') < vt.indexOf('class="ht-msgs"'));
check("Allow / Let the A.I. answer here / Create an A.I. stay in the bar, after the sentence", /: bar\) \+/.test(vt));
check("a mode button and the Allow buttons go through setWho; 'Hand back to the A.I.' when you reply yourself",
  /setWho\(c, b\.dataset\.m\)/.test(vt) && /setWho\(c, b\.dataset\.on === "1" \? modeOf\(c\) : "off"/.test(vt) && /ib-back-ai/.test(vt));
const sw = CV.slice(CV.indexOf("  async function setWho("), CV.indexOf("  function refreshChat()"));
check("setWho: switching the A.I. on first allows it in this chat, then sets the mode; off only switches it off",
  /if \(v === "off"\) await api\("\/conversations\/" \+ c\.id \+ "\/ai", \{ method: "POST", body: fd\(\{ on: "0" \}\) \}\)/.test(sw) &&
  /if \(!wasOn\) await api\("\/conversations\/" \+ c\.id \+ "\/ai", \{ method: "POST", body: fd\(\{ on: "1" \}\) \}\)/.test(sw) &&
  /if \(v !== wasMode\) await api\("\/conversations\/" \+ c\.id \+ "\/mode"/.test(sw));
check("setWho: pressing the mode already on does nothing", /\(v !== "off" && wasOn && v === wasMode\)\) return;/.test(sw));
check("setWho: a toast with Undo puts the old state back (not for Dismiss)", /toast\(window\.t\(msg/.test(sw) && /noUndo \|\| dismiss \? null/.test(sw) &&
  /setWho\(now, wasOn \? wasMode : "off", false, true\)/.test(sw));
check("the old two-state switch and status line are gone", !/ht-seg|renderStatusLine|renderActions|function doiMode|ht\.sw_|ht\.st_/.test(CV) &&
  !/\.ht-seg|\.ht-status|\.ht-act/.test(OLDCSS));
check("'Bot im: lý do' nằm TRONG vùng tin, ngay sau tin cuối", /_msgs\.map\(veTin\)\.join\(""\) \+ renderSilenceLine\(c\)/.test(CV));
check("lý do lấy nhãn từ bộ phán xử (codeLabel), kèm điểm/ngưỡng khi có; mã lạ thì hiện nguyên mã",
  /RP\.codeLabel\(s\.code\)/.test(CV) && /toFixed\(2\)/.test(CV) && /function codeLabel\(code\)/.test(RP) &&
  /CODE_LB\[code\] \? tt\(CODE_LB\[code\]\) : String\(code \|\| ""\)/.test(RP));
check("the silence line offers 'Ask the A.I. to answer this' only when it can (allowed, auto mode, bot running, customer last)",
  /var canAsk = c\.ai_allowed && modeOf\(c\) === "ai" && _running && last && last\.sender_type === "customer";/.test(CV) && /ib-silent-ask/.test(CV));
check("nút 'Vì sao' mở đúng bảng Bộ phán xử của bot đó", /JavisReplyPolicy\.openPanel\(\{ id: c\.bot_id, name: c\.bot_name \|\| "" \}\)/.test(CV));
check("nhịp tự làm mới vẽ lại phần đầu khung khi who, mode, draft hay bot_silence đổi (chữ ký metaSig)",
  /function metaSig\(\)/.test(CV) && /c\.who, c\.who_code, c\.ai_allowed, c\.ai_pending, c\.draft \|\| null/.test(CV) &&
  /_silence, _running, u\.sender_type/.test(CV) && /sig !== _vetMeta/.test(CV));
check("lý do do server trả được thoát HTML trước khi vẽ", /esc\(window\.t\("ht\.silent", \{ why: lyDo \+ diem \}\)\)/.test(CV));

const rp = { window: { t: (k) => k, JavisI18n: { locale: () => "vi-VN" } }, document: { createElement: () => ({}) },
  fetch: () => Promise.reject(new Error("no net")), console, Date };
vm.createContext(rp);
vm.runInContext(RP, rp);
check("codeLabel: mã biết thì ra khoá nhãn, mã lạ thì ra nguyên mã, rỗng thì rỗng",
  rp.window.JavisReplyPolicy.codeLabel("below_threshold") === "rp.code_below_threshold" &&
  rp.window.JavisReplyPolicy.codeLabel("ma_la_moi") === "ma_la_moi" && rp.window.JavisReplyPolicy.codeLabel("") === "");

// ---- 3. CSS and dictionary ----
check("CSS: the bar takes the colour of who handles the chat; each pressed mode has its own colour",
  ["you", "ai", "owner"].every((w) => CSS.indexOf(".ib-aibar.w-" + w) >= 0) &&
  /\.ib-m\.on\.m-ai/.test(CSS) && /\.ib-m\.on\.m-draft/.test(CSS) && /\.ib-m\.on\.m-human/.test(CSS));
check("CSS: a narrow chat column hides the label, then shows the short mode names (container query)",
  /\.ib-v5 \.ht-thread \{ container-type: inline-size; \}/.test(CSS) && /@container \(max-width: 640px\) \{ \.ib-mode-l \{ display: none; \} \}/.test(CSS) &&
  /@container \(max-width: 470px\)[\s\S]*?\.ib-l-short \{ display: inline; \}/.test(CSS));
const keys = ["ib.ai_lbl", "ib.m_ai", "ib.m_ai_s", "ib.m_draft", "ib.m_draft_s", "ib.m_human", "ib.m_human_s", "ib.allow", "ib.dismiss",
  "ib.allow_here", "ib.make_bot", "ib.back_ai", "ib.ask_ai_now", "ht.silent", "ht.silent_why"].concat(codes.map((k) => "ib.wc_" + k));
check("khoá có ở cả vi và en", keys.every((k) => VI[k] && EN[k]), keys.filter((k) => !VI[k] || !EN[k]).join(","));
check("the self-action buttons speak in the first person (owner, 2026-10-28)", VI["ib.m_human"] === "Tôi trả lời" &&
  VI["ib.m_draft"] === "A.I. soạn, tôi duyệt");
check("khoá của công tắc và dòng trạng thái cũ đã bỏ", ["ht.sw_auto", "ht.sw_mine", "ht.st_ai", "ht.st_off", "ht.tra_ai", "ht.tiep_quan"]
  .every((k) => !(k in VI) && !(k in EN)));
check("không dùng em dash trong test này", fs.readFileSync(__filename, "utf8").indexOf(String.fromCharCode(0x2014)) < 0);

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_hoi_thoai_cong_tac: tất cả pass");
