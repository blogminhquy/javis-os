// 0.191.0: files, working folder and the info panel of a team (dashboard/teams.js), and the ">" of the folder picker
// (dashboard/composer-folder.js).
//
//     node tests/js/test_team_docs_ui.js
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(root, "dashboard", f), "utf8");
const vi = JSON.parse(read("i18n/vi.json"));
const en = JSON.parse(read("i18n/en.json"));
const CF = require(path.join(root, "dashboard", "composer-folder.js"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 400)));
  if (!cond) fails++;
}

// ---- folder picker: ">" goes inside, the name pins ----
const rows = CF.folderRows([{ name: "05 - Projects", type: "dir", dirs: true }, { name: "Shop", type: "dir" },
  { name: ".git", type: "dir", dirs: true }, { name: "a.md", type: "file" }], "Brain");
check("rows carry whether a folder has folders inside; hidden ones and files left out",
  JSON.stringify(rows) === JSON.stringify([{ name: "05 - Projects", path: "Brain/05 - Projects", dirs: true },
    { name: "Shop", path: "Brain/Shop", dirs: false }]), JSON.stringify(rows));
const cf = read("composer-folder.js");
check("the list asks the server which folders have subfolders, and lists inside the one gone into",
  cf.includes('"/files/list?subdirs=1&brain="') && cf.includes('"&path=" + encodeURIComponent(here.path)'));
check("a folder with folders inside gets a separate '>' button; the name button pins",
  /\(r\.dirs \? '<button type="button" class="cp-in" data-in="'/.test(cf) && cf.includes('data-pin="\' + i + \'"'));
check("inside a folder: a back row and a row to pin the folder you are in",
  cf.includes('data-back="1"') && cf.includes('data-pin-here="1"') && /trail\.push\(\{ name: d\.name, path: d\.path \}\)/.test(cf));
check("the panel is reusable (team chat passes its own brain, folder and pin)", /panelFor: makePanel/.test(cf)
  && /var panel = makePanel\(\);/.test(cf));

// ---- team chat ----
const tm = read("teams.js");
check("'+' menu: attach a file, pin a working folder", tm.includes('data-plus-attach="1"') && tm.includes('data-plus-folder="1"'));
check("attachments upload to /upload and go out with the message; sending waits for uploads",
  tm.includes('fetch("/upload"') && tm.includes("body.attachments = atts.map(") && tm.includes('setNote(tw("teams.attach_wait"))'));
check("the team folder pins on the team's own conversation (same route as the main chat)",
  tm.includes('"/coding/session/" + q(sid) + "/pin"') && tm.includes("window.JavisPinnedFolder && window.JavisPinnedFolder.panelFor"));
check("the team picture opens the info panel", tm.includes('class="tm-ava-btn" data-team-info="1"')
  && /if \(d\.teamInfo\) return S\.side && S\.tab === "info" \? closeSide\(\) : openSide\("info", t\);/.test(tm));
check("the info panel: members, working folder, pictures, files with Add, links with Add, from the conversation assets",
  tm.includes("function infoTabHtml(t)") && tm.includes('"/sessions/" + q(sid) + "/assets?brain="') &&
  tm.includes("data-info-add-file") && tm.includes("data-info-add-link") && tm.includes("tm-info-imgs") && tm.includes('teamUrl("/files")'));
check("info is the first tab of the side panel", tm.includes('var tabs = ["info", "jobs", "team"]'));
check("files sent with a message show as chips, the stored names line is not repeated",
  tm.includes("((m.meta || {}).files || [])") && tm.includes("fileChipHtml"));
const keys = ["teams.tab_info", "teams.info_open", "teams.attach", "teams.attach_err", "teams.attach_wait", "teams.uploading",
  "teams.info_members", "teams.info_folder", "teams.info_files", "teams.info_links", "teams.info_add_file", "teams.info_no_files",
  "cp.pin_top", "cp.pin_here", "cp.pin_open", "cp.pin_no_sub"];
check("i18n vi/en", keys.every((k) => vi[k] && en[k]), keys.filter((k) => !vi[k] || !en[k]).join(","));
const css = read("console.css") + read("style.css");
check("CSS: chips, info panel, the '>' button 44px on touch", css.includes(".tm-attach-chips {") && css.includes(".tm-info-sec {")
  && /\(pointer: coarse\) \{ \.cp-in \{ width: 44px; height: 44px; \}/.test(css));
check("no em dash", !/[–—]/.test(cf + keys.map((k) => vi[k] + en[k]).join("")));

// ---- 0.191.0 follow-ups: avatar strip of the partner list, Javis Core's Jobs tab, the tab pill ----
const ws = read("workspace.js"), aj = read("agent-jobs.js");
check("dragging the list edge past the threshold snaps it to the avatar strip and marks the page",
  ws.includes("var MINI_W = 72, NGUONG_MINI = 160;") && ws.includes('if (ben === "left" && w < NGUONG_MINI) return MINI_W;')
  && ws.includes('page.classList.toggle("ws-mini", w === MINI_W)'));
check("a remembered strip width comes back as the strip; double-click restores the default list",
  ws.includes("if (v) datBeRong(page, ben, chanBeRong(ben, v, page));") && ws.includes("datBeRong(page, ben, 0);"));
check("hovering an avatar in the strip shows its name card, the card goes with the rows",
  ws.includes("hienTheMini(b)") && ws.includes('b.addEventListener("mouseleave", anTheMini)') && /function veDanhSach\(\) \{\n[^\n]*\n    anTheMini\(\);/.test(ws));
check("CSS: the strip hides the words on wide screens only, keeps a dot for waiting work",
  /@media \(min-width: 901px\) \{\n  \.wspage\.ws-mini > \.ws-left/.test(css) && css.includes(".wspage.ws-mini .ws-item-wrap[data-st]::after")
  && css.includes(".ws-mini-tip {"));
check("Javis Core's Jobs tab has no Assign button and its own empty line",
  ws.includes("noAssign: !!item.system,") && aj.includes('if (ui.noAssign) return "";') && vi["ajobs.empty_core"] && en["ajobs.empty_core"]);
check("the right column tabs leave room around the label of the selected one",
  css.includes(".ws-rtabs .cside-tab { flex: 1 1 auto; padding: 7px 10px;"));
check("no em dash in the new text", !/[–—]/.test(vi["ajobs.empty_core"] + en["ajobs.empty_core"] + vi["ajobs.empty"] + en["ajobs.empty"]));

// ---- 0.191.1: four-colour job state dot, solid hover card, readable dropdowns ----
const AJ = require(path.join(root, "dashboard", "agent-jobs.js"));
check("one state per assistant, most urgent first: red needs you or failed, blue working, orange waiting, green done",
  AJ.statusOf({ needs_you: 1, running: 2 }) === "need" && AJ.statusOf({ failed: 1, running: 1 }) === "need"
  && AJ.statusOf({ running: 1, waiting: 3 }) === "run" && AJ.statusOf({ waiting: 1, done: 4 }) === "wait"
  && AJ.statusOf({ done: 2 }) === "done" && AJ.statusOf({}) === "" && AJ.statusOf(undefined) === "");
check("the row carries the state for the dot, the hover card says it in words",
  ws.includes("(jst ? ' data-st=\"' + jst + '\"' : \"\")") && ws.includes("stText: tt, st: st") &&
  // 0.196.0: the card is drawn by the shared helper (col-resize.js), used by the Teams page too.
  read("col-resize.js").includes('class="ws-mini-tip-st" data-st="'));
check("CSS: the dot is 8px, each state has its colour, the card is solid",
  /\.ws-item-wrap\[data-st\]::after \{ content: ""; position: absolute; top: 6px; right: 10px; width: 8px;/.test(css)
  && ["need", "run", "wait", "done"].every((k) => css.includes('[data-st="' + k + '"] { --st-dot:'))
  && /\.ws-mini-tip \{[^}]*background: var\(--bg2\);/.test(css));
check("every dropdown list gets a solid theme background", css.includes("select option, select optgroup { background-color: var(--bg2); color: var(--text); }"));
const dk = ["ajobs.dot_need", "ajobs.dot_run", "ajobs.dot_wait", "ajobs.dot_done"];
check("state words vi/en, no em dash", dk.every((k) => vi[k] && en[k]) && !/[–—]/.test(dk.map((k) => vi[k] + en[k]).join("")));

// ---- 0.192.0: paste, drop, typing strip, @all, mentions, reply quotes, pins, job rows ----
const T = require(path.join(root, "dashboard", "teams.js"));
const tj = read("teams.js");
check("paste and drop on the team page land in the team, not the hidden main chat",
  tj.includes('el.setAttribute("data-localdrop", "")') && tj.includes('el.addEventListener("paste", onPaste)')
  && tj.includes('el.addEventListener("drop", onDrop)') && /e\.preventDefault\(\); e\.stopPropagation\(\);\n\s+attachGrabbed\(files\);/.test(tj));
check("a very long paste becomes a .txt document like the main chat",
  tj.includes("var PASTE_TXT_CHARS = 1500, PASTE_TXT_LINES = 25;") && tj.includes('"van-ban-dan-"'));
check("pasted bytes are copied while the event runs (phones)", tj.includes("function grabFile(f)") && tj.includes("f.arrayBuffer()"));
check("a picture chip shows the picture", tj.includes('<img class="tm-chip-thumb" src="') && tj.includes("URL.revokeObjectURL"));
const mem = [{ agent_key: "a", name: "Lan" }, { agent_key: "b", name: "Minh Anh" }, { agent_key: "c", name: "Hoa", status: "removed" }];
const ty = T.typingHtml([{ agent_key: "a", role: "member_reply" }, { agent_key: "b", role: "work" }, { agent_key: "a", role: "member_reply" }], mem);
check("typing strip: one entry per member, replying vs working, with the picture", (ty.match(/tm-typing-who/g) || []).length === 2
  && ty.includes("Lan đang trả lời") && ty.includes("Minh Anh đang làm việc") && T.typingHtml([], mem) === "", ty);
check("the typing strip sits above the input and follows team_typing events",
  tj.includes('<div class="tm-typing" role="status" aria-live="polite" hidden></div>') && tj.includes('d.type === "team_typing"'));
const sa = T.mentionScan("@all làm nhé", mem, []), sx = T.mentionScan("mail@allx @Lan", mem, []);
check("@all calls every active member; @allx is not @all", sa.all && sa.keys.join() === "a,b" && !sx.all && sx.keys.join() === "a",
  JSON.stringify([sa, sx]));
check("@all is offered first in the suggestions and sent as mention_all",
  tj.includes('agent_key: "*all"') && tj.includes("if (scan.all) body.mention_all = true;"));
const mk = T.markMentions('<p>@Lan xem, <a href="mailto:x@Lan">x</a></p>', mem);
check("assistant mentions are drawn as mentions, never inside a link", mk.html.includes('<span class="tm-at">@Lan</span>')
  && mk.html.includes('href="mailto:x@Lan"') && !mk.me, mk.html);
const byId = { 5: { id: 5, ts: 1, author_kind: "owner", content: "Làm landing <b> nhé" } };
const rq = T.replyRefHtml({ id: 6, reply_to: 5, author_kind: "agent" }, { members: mem, byId: byId });
check("an assistant's reply quotes the message it answers, as a button to it", rq.includes('data-jump="5"')
  && rq.includes("Làm landing &lt;b&gt; nhé") && rq.includes("tm-quote-ico") && T.replyRefHtml({ id: 7 }, { byId: byId }) === "", rq);
const am = T.messageHtml({ id: 8, author_kind: "agent", author_ref: "a", content: "Anh chọn mẫu nào?", meta: { asks_owner: true } },
  { members: mem, byId: {} });
check("a message calling the owner is flagged for the owner", am.includes("tm-msg-asks") && am.includes(vi["teams.asks_you"]), am);
const pins = T.pinsHtml([{ id: 1, ts: 1, author_kind: "owner", content: "Giá sỉ 50k" }, { id: 2, ts: 2, author_kind: "agent",
  author_ref: "a", content: "Chốt màu cam" }], false, { members: mem });
check("pinned strip: the newest pin, the count, and that the team follows them", pins.includes("Chốt màu cam")
  && !pins.includes("Giá sỉ 50k") && pins.includes("Đã ghim · 2") && pins.includes(vi["teams.pins_note"]), pins);
check("opening the strip lists every pin with an unpin button",
  (T.pinsHtml([{ id: 1, ts: 1, author_kind: "owner", content: "a" }, { id: 2, ts: 2, author_kind: "owner", content: "b" }], true,
    { members: mem }).match(/data-on="0"/g) || []).length === 2);
const css2 = read("console.css");
check("CSS: typing strip, drop target, quote mark, mention, owner flag, pinned strip, job rows",
  [".tm-typing {", ".tm-composer.is-drop", ".tm-quote-ico {", ".tm-at-me {", ".tm-msg-asks .tm-bubble", ".tm-pinbar {",
    ".tm-side-body .tm-qrow .tm-actions { flex: 1 1 100%;"].every((x) => css2.includes(x)));
const k192 = ["teams.typing_reply", "teams.typing_work", "teams.typing_more", "teams.hint_all", "teams.mention_all", "teams.asks_you",
  "teams.quote_open", "teams.pins_title", "teams.pins_note", "teams.pins_open", "teams.pins_close", "teams.owner_tags"];
check("0.192.0 words vi/en, no em dash", k192.every((k) => vi[k] && en[k]) && !/[–—]/.test(k192.map((k) => vi[k] + en[k]).join("")),
  k192.filter((k) => !vi[k] || !en[k]).join(","));
check("0.192.0: a new assistant message appears block by block, one member after another, history at once",
  tj.includes("{ S.msgs.push(nm); queueReveal(nm); }") && tj.includes('if (!m || m.author_kind !== "agent" || revealOff()) return;')
  && tj.includes("else S.rv.queue.push(Number(m.id));") && tj.includes("applyReveal(box);")
  && css2.includes(".tm-msg.tm-rv-wait { display: none; }") && css2.includes("prefers-reduced-motion"));
check("0.192.0: the assistant picture sits at the top next to its name", css2.includes(".tm-msg-agent { align-items: flex-start; }"));

if (fails) { console.log("\nFAIL " + fails); process.exit(1); }
console.log("\nOK test_team_docs_ui");
