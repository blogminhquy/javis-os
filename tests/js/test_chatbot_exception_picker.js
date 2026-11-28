/* Per-chat exceptions of the bot form: nothing pre-picked, nothing added or removed by a stray tap.

       node tests/js/test_chatbot_exception_picker.js

   Owner, 28/11/2026: "cơ cấu lại ngoại lệ để không chọn nhầm, và khung tìm kiếm cũng phải thiết kế lại để dễ làm việc
   hơn". The old section was a <select> that always showed its first chat next to an Add button: it read as already
   picked, so one press of Add added the wrong person. Now (the 21/11 anti-misclick pattern of the repo picker):
     - "Add a chat" opens a search; nothing is listed or picked before that;
     - each result is a button with a +, one tap adds it and the search closes;
     - a saved row does nothing on tap, only its X removes it;
     - the search box is type="text" (type="search" draws a second X next to ours). */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const CB = fs.readFileSync(path.join(ROOT, "dashboard", "chatbots.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "style.css"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };
const between = (src, a, b) => { const i = src.indexOf(a); const j = src.indexOf(b, i + 1); return i < 0 || j < 0 ? "" : src.slice(i, j); };

// The section's markup and its code.
const HTML = between(CB, "// 6. Per-chat exceptions", "// No language picker");
const JS = between(CB, "// ---- Per-chat exceptions (0.172.0, rebuilt 2026-11-28)", "// ---- Chế độ lên tiếng trong nhóm");
check("the section and its code are found", HTML.length > 200 && JS.length > 1000);

// 1. Nothing pre-picked.
check("no <select> to pick a chat in the section (only the level of a saved row)",
  !/<select id=/.test(HTML) && !/cbNlPick/.test(CB));
check("no Add button next to a picker any more", !/cbNlAdd/.test(CB));
check("an Add a chat button opens the search", /id="cbNlOpen"/.test(HTML) && /#cbNlOpen"\)\.onclick = openExcSearch/.test(JS));
check("the search starts closed", /id="cbNlFind" hidden/.test(HTML));
check("the search box is type=text, so the browser draws no second X",
  /type="text" id="cbNlQ"/.test(HTML) && !/type="search" id="cbNlQ"/.test(HTML));
check("Esc closes the search, Enter never submits the form",
  /ev\.key === "Escape"[\s\S]{0,120}closeExcSearch\(\)/.test(JS) && /ev\.key === "Enter"\) ev\.preventDefault\(\)/.test(JS));

// 2. One tap on a result adds it, then the search closes.
check("each result is a button marked with a +", /class="cb-nl-hit"/.test(JS) && /cb-nl-plus/.test(JS));
check("a tap on a result adds that chat", /h\.onclick = function \(\) \{ addException\(h\.dataset\.k\); \}/.test(JS));
const ADD = between(JS, "function addException(", "async function loadExcChats(");
check("adding closes the search and outlines the new row",
  /closeExcSearch\(\)/.test(ADD) && /excFlash = k/.test(ADD) && /\.cb-nl-row\.is-new\s*\{/.test(CSS));
check("a chat already added is never added twice", /excRows\.some\(function \(e\) \{ return excKey\(e\) === k; \}\)\) return/.test(ADD));
check("a new row starts at the level the form shows, not a raised one", /muc_quyen: giaTri\("cbMuc"\)/.test(ADD));

// 3. Only the X removes a saved row.
const DRAW = between(JS, "function drawExceptions(", "function drawExcResults(");
check("a saved row has no tap handler of its own", !/r\.onclick|\.cb-nl-row"\)\.onclick/.test(DRAW));
check("its X removes it", /\.cb-nl-x"\)\.onclick = function/.test(DRAW) && /excRows\.splice/.test(DRAW));

// 4. Empty states say why, and every new word exists in both languages.
for (const k of ["cb.nl_add", "cb.nl_find_ph", "cb.nl_close", "cb.nl_muc", "cb.nl_no_acc", "cb.nl_none", "cb.nl_none_q",
                 "cb.nl_already", "cb.nl_all_added", "cb.nl_add_ten", "cb.nl_bo_ten"]) {
  check(`${k} is used and in vi.json and en.json`, CB.includes(`"${k}"`) && !!VI[k] && !!EN[k]);
}
check("the hint no longer says the wait is personal Zalo only",
  !/chỉ có tác dụng ở Zalo cá nhân/.test(VI["cb.hint_ngoai_le"]) && !/only works on personal Zalo/.test(EN["cb.hint_ngoai_le"]));

// 5. Phone sizes: 16px text in the search, rows and fields; 44px targets.
check("search box and row fields are 16px and 44px tall",
  /input\.cb-nl-q \{[^}]*min-height: 44px[^}]*font-size: 16px/.test(CSS) &&
  /\.cb-nl-f select, \.cb-form \.cb-nl-f input \{ min-height: 44px; font-size: 16px; \}/.test(CSS));
check("the X buttons are 44px", /\.cb-nl-x, \.cb-nl-close \{[^}]*width: 44px; height: 44px/.test(CSS));

if (fails.length) { console.log(`\nFAIL ${fails.length}: ${fails.join(", ")}`); process.exit(1); }
console.log("\nOK - test_chatbot_exception_picker: all pass");
