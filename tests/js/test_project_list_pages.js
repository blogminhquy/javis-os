/* Pages, search and the roomy edit box of the project drawer (2026-11-19).

       node tests/js/test_project_list_pages.js

   Owner, 19/11/2026: "thêm phân trang giúp anh ở tài liệu và đã học nếu mà nó quá nhiều, hiển thị đẹp hơn và popup làm
   lại khi sửa để mở rộng ra dễ sửa". Guards:
   - the Learned and Documents tabs cut a long list into pages of 20 with a search box (design-style section 5), and the
     search ignores Vietnamese marks;
   - editing a note, a lesson or a document description opens text-edit-dialog.js, not the browser's one-line prompt();
   - the edit box is loaded before the pages that open it, and saves nothing when nothing changed. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const SU = D("sessions-ui.js");
const TM = D("teams.js");
const HTML = D("index.html");
const CSS = D("style.css");
const DLG_SRC = D("text-edit-dialog.js");
const DLG = require(path.join(ROOT, "dashboard", "text-edit-dialog.js"));
const VI = JSON.parse(D(path.join("i18n", "vi.json")));
const EN = JSON.parse(D(path.join("i18n", "en.json")));

const fails = [];
const check = (name, cond, extra) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : ""));
  if (!cond) fails.push(name);
};

// ---- 1. Edit box: pure helpers ----
check("counter shows used/max", DLG.counterText(12, 300) === "12/300" && DLG.counterText(5, 0) === "5");
check("counter warns near the cap and at it",
  DLG.counterState(100, 300) === "" && DLG.counterState(280, 300) === "near" && DLG.counterState(300, 300) === "full");
check("nothing to save when the text is unchanged", DLG.pending("abc", " abc ", "fact", "fact", false) === null);
check("a new kind alone is a change", JSON.stringify(DLG.pending("abc", "abc", "fact", "term", false)) ===
  JSON.stringify({ text: "abc", kind: "term" }));
check("an empty text is refused unless allowed", DLG.pending("abc", "  ", "", "", false) === null &&
  JSON.stringify(DLG.pending("abc", "", "", "", true)) === JSON.stringify({ text: "", kind: "" }));
check("the edited text is trimmed", DLG.pending("a", "  b c  ", "", "", false).text === "b c");

// ---- 2. Edit box: loaded and used ----
const at = (s) => HTML.indexOf(s);
check("text-edit-dialog.js loads before sessions-ui.js",
  at('src="/static/text-edit-dialog.js') > 0 && at('src="/static/text-edit-dialog.js') < at('src="/static/sessions-ui.js'));
// Project name and chat title still ask one short line with prompt(); the drawer's texts (pdT keys) never do.
const drawerPrompts = SU.split("\n").filter((l) => /\bprompt\(pdT\(/.test(l));
check("no drawer text is edited with prompt() any more", drawerPrompts.length === 0, drawerPrompts.join(" | "));
check("prompt() stays only as the fallback inside editText", /if \(E && E\.open\) return E\.open\(o\);\s*var text = prompt\(o\.title/.test(SU));
check("note, lesson and description edits go through editText",
  /async function editNote[\s\S]{0,80}editText\(/.test(SU) && /async function suaBaiHoc[\s\S]{0,80}editText\(/.test(SU) &&
  /async function editAssetDescription[\s\S]{0,80}editText\(/.test(SU));
check("adding a note or a lesson opens the same box",
  /async function addNote[\s\S]{0,120}editText\(/.test(SU) && /async function themBaiHoc[\s\S]{0,80}editText\(/.test(SU));
check("the note box offers the kinds", /kinds: noteKinds\(\), kind: noteKindOf\(n\)/.test(SU));
check("a description may be emptied (removes it)", /editAssetDescription[\s\S]{0,400}allowEmpty: true/.test(SU));
check("the team panel's description uses the same box", /function describeDoc[\s\S]{0,700}JavisTextEdit/.test(TM));
check("the box sits above the project drawer", /\.ted-wrap \{[^}]*z-index: 6000/.test(CSS) && /\.pd-wrap \{[^}]*z-index: 5000/.test(CSS));
check("the box's text is 16px (no iPhone zoom) and a phone sheet follows the keyboard",
  /\.ted-in \{[^}]*font-size: 16px/.test(CSS) && /body\.kb-open \.ted-wrap/.test(CSS));
check("Ctrl or Cmd+Enter saves, Escape closes", /e\.key === "Enter" && \(e\.ctrlKey \|\| e\.metaKey\)/.test(DLG_SRC) &&
  /e\.key === "Escape"/.test(DLG_SRC));
check("a tap outside never throws away a change", /ted-scrim"\)\.onclick = function \(\) \{\s*if \(!pending\(/.test(DLG_SRC));

// ---- 3. Pages and search ----
const grab = (name) => {
  const m = SU.match(new RegExp("  function " + name + "\\([\\s\\S]*?\\n  \\}\\n"));
  return m ? m[0] : "";
};
const lib = new Function("var LIST_PAGE = 20;\n" + grab("pageSlice") + grab("foldText") + grab("matchesQuery") +
  "return { pageSlice: pageSlice, matchesQuery: matchesQuery };")();
check("20 rows a page", /var LIST_PAGE = 20;/.test(SU));
const s1 = lib.pageSlice(30, 1);
check("page two of 30 rows shows rows 21 to 30", s1.page === 1 && s1.pages === 2 && s1.from === 20 && s1.to === 30);
const s2 = lib.pageSlice(20, 1);
check("a page past the end is pulled back (a removal emptied it)", s2.page === 0 && s2.pages === 1);
check("an empty list is one empty page", JSON.stringify(lib.pageSlice(0, 3)) === JSON.stringify({ page: 0, pages: 1, from: 0, to: 0 }));
check("search ignores Vietnamese marks", lib.matchesQuery("su that ha noi", ["Sự thật về Hà Nội"]) &&
  lib.matchesQuery("đã HỌC", ["da hoc"]));
check("every word must match", !lib.matchesQuery("hosting zalo", ["Hosting của langchaixua.vn"]));
check("both tabs draw the search box and the pager",
  /findHtml\("learned"/.test(SU) && /findHtml\("files"/.test(SU) && /pagerHtml\(sl\)/.test(SU.split("function noteRowsHtml")[1] || "") &&
  /pagerHtml\(sl\)/.test(SU.split("function dsFileHtml")[1] || "") && /pagerHtml\(sl\)/.test(SU.split("function hocRowsHtml")[1] || ""));
check("a group title is repeated at the top of a page that starts inside it",
  /if \(h\.group !== nhom\) \{ nhom = h\.group; if \(nhom\) ds \+= nhomHtml\(nhom\); \}/.test(SU));
check("lighting up a row turns to its page first", /v\.page = Math\.floor\(at \/ LIST_PAGE\);/.test(SU));
check("each drawer opens on page one", (SU.match(/resetListViews\(\);/g) || []).length === 3);
check("the learned list filters by kind", /function noteChipsHtml/.test(SU) && /\.pd-chip\.on/.test(CSS));
check("styles for the search box and pager", /\.pd-find\[hidden\] \{ display: none; \}/.test(CSS) && /\.pd-pager \{/.test(CSS));

// ---- 4. Words ----
const keys = ["proj.note_add", "proj.note_kind", "proj.desc_ph", "proj.find_notes", "proj.find_docs", "proj.find_none",
  "proj.kind_all", "proj.page_of", "proj.page_prev", "proj.page_next", "ags.lesson_add",
  "ted.save", "ted.saving", "ted.cancel", "ted.close", "ted.keys"];
for (const [lang, d] of [["vi", VI], ["en", EN]]) {
  const missing = keys.filter((k) => !d[k]);
  check(lang + ": every new key is there", !missing.length, missing.join(", "));
  check(lang + ": no long dash in the new text", keys.every((k) => !/[\u2013\u2014]/.test(d[k] || "")));
}
check("no long dash in the new code", !/[\u2013\u2014]/.test(DLG_SRC) && !/[\u2013\u2014]/.test(grab("pageSlice")));

console.log();
if (fails.length) { console.log("FAIL " + fails.length + ": " + fails.join("; ")); process.exit(1); }
console.log("ALL PASS");
