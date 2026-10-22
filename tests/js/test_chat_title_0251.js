/* The open conversation's name sits next to the collapse button (0.251.0).

       node tests/js/test_chat_title_0251.js

   Owner's request: show the conversation's title beside "Shrink" on the Chat page. This runs
   the real renderTitle from sessions-ui.js against a stub DOM, so it checks behaviour, not just
   that some string exists. */
const fs = require("fs");
const path = require("path");

const D = (f) => fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", f), "utf8");
const SRC = D("sessions-ui.js");
const CONSOLE = D("console.js");
const CODING = D("coding.js");
const VI = JSON.parse(D("i18n/vi.json"));
const EN = JSON.parse(D("i18n/en.json"));

const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

const m = SRC.match(/function renderTitle\(\) \{\n([\s\S]*?)\n  \}\n/);
check("renderTitle exists in sessions-ui.js", !!m);
if (!m) { console.log("\nFAIL - test_chat_title_0251"); process.exit(1); }

// ---- Stub DOM: one host whose innerHTML we read back, with a querySelector that finds the button ----
function makeHost() {
  const host = { innerHTML: "", _btn: null };
  host.querySelector = (sel) => {
    if (sel !== ".cp-conv" || !/class="cp-conv/.test(host.innerHTML)) return null;
    if (!host._btn || host._btn._html !== host.innerHTML) host._btn = { dataset: {}, onclick: null, _html: host.innerHTML };
    return host._btn;
  };
  return host;
}

function run(state) {
  const host = state.host || makeHost();
  const doc = { querySelectorAll: () => [host] };
  const renamed = [];
  const fn = new Function("document", "currentId", "phienProj", "pdT", "esc", "ic", "renSession", m[1]);
  fn(doc, () => state.sid, state.cache,
     (k, v) => (k === "top.new_chat" ? "New conversation" : k + (v ? ":" + v.ten : "")),
     (s) => String(s).replace(/</g, "&lt;"), () => "<svg/>", (s) => renamed.push(s));
  return { host, renamed };
}

// A saved conversation shows its title, offers rename, and the click renames that session.
let r = run({ sid: "s1", cache: { sid: "s1", pid: "", title: "Doanh thu tháng 9" } });
check("saved conversation shows its title", r.host.innerHTML.includes("Doanh thu tháng 9"));
check("saved conversation shows the pencil", r.host.innerHTML.includes("<svg/>"));
check("saved conversation is not dimmed", !r.host.innerHTML.includes("is-new"));
r.host._btn.onclick();
check("clicking the title renames that session", r.renamed.length === 1 && r.renamed[0].id === "s1");

// The title is escaped (it is user text).
r = run({ sid: "s2", cache: { sid: "s2", pid: "", title: "<b>x" } });
check("title is HTML-escaped", !r.host.innerHTML.includes("<b>x"));

// No session yet, or a session the server has not saved: "New conversation", dimmed, no rename.
r = run({ sid: null, cache: { sid: "", pid: "", title: "" } });
check("empty chat says New conversation", r.host.innerHTML.includes("New conversation") && r.host.innerHTML.includes("is-new"));
check("empty chat has no pencil", !r.host.innerHTML.includes("<svg/>"));
r = run({ sid: "s3", cache: { sid: "s1", pid: "", title: "Old" } });
check("a stale cache for another session never shows the old title", !r.host.innerHTML.includes("Old"));

// Redrawing the same title keeps the same node (no flash from the fade-in animation).
const host = makeHost();
run({ host, sid: "s1", cache: { sid: "s1", pid: "", title: "A" } });
const first = host.innerHTML;
host.innerHTML = first + "";
const before = host._btn;
run({ host, sid: "s1", cache: { sid: "s1", pid: "", title: "A" } });
check("same title does not rebuild the button", host._btn === before);

// Both pages carry the slot, and the chip draw also draws the title.
check("Chat page has the title slot after the collapse button",
  /id="cpMinBtn"[\s\S]{0,700}cp-conv-host/.test(CONSOLE));
check("Code page has the title slot", CODING.includes('class="cp-conv-host"'));
check("renderProjChip draws the title", /async function renderProjChip\(\) \{[\s\S]{0,300}renderTitle\(\)/.test(SRC));
check("renaming clears the cached title", /async function renSession[\s\S]{0,500}quenPhienProj\(\);/.test(SRC));
check("title text is at least 16px", /\.cp-conv\{[^}]*font:500 16px/.test(CONSOLE));
check("long titles end in an ellipsis", /\.cp-conv-t\{[^}]*text-overflow:ellipsis/.test(CONSOLE));
check("rename tooltip in vi and en", !!VI["cs.cp_title_rename"] && !!EN["cs.cp_title_rename"]);

if (fails.length) { console.log("\nFAIL - test_chat_title_0251: " + fails.length); process.exit(1); }
console.log("\nOK - test_chat_title_0251");
