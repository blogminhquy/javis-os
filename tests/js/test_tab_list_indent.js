/* Tab / Shift+Tab indentation in the .md editor, and typing "- " / "1. " to make a real list.

       node tests/js/test_tab_list_indent.js

   Requested by the owner (2026-10-20): Tab indents a line; typing a bullet, task or number and
   pressing Enter gives the next marker by itself (the Enter part is locked in
   test_enter_list_continuation.js).

   The DOM behavior was measured in real Edge (Chromium) through DevTools with real keys: 26 checks
   covering Enter continuing task/bullet/number, leaving an empty task, Tab/Shift+Tab nesting
   sub-items, typing "- " / "3. " into a list, and the Edit -> markdown round trip through Turndown
   + GFM. CI only has node, so this test locks the pure logic plus the spots that tend to drift in
   the source.

   Places that break SILENTLY:
     1. A sub-item must sit INSIDE its parent li. Chromium's execCommand("indent") puts the sub
        <ul> next to the <li>, which Turndown does not read as indentation: after saving the
        sub-item falls back a level.
     2. Tab in raw source must indent 4 spaces, the pattern Turndown writes sub-items with. Off
        pattern, switching between Edit and Source makes the nesting jump around.
     3. Typing "- " in the render pane without turning it into a list makes Turndown save
        "\- text", and Enter cannot continue anything (exactly the bug in the owner's daily log
        of 2026-10-20). */
const fs = require("fs");
const path = require("path");
const EC = require("../../dashboard/editor-cmds.js");
const SRC = fs.readFileSync(path.join(__dirname, "../../dashboard/editor-cmds.js"), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// Apply the edit to the string; "[" "]" mark the selection, "|" is the caret with no selection.
function apply(value, s, e, outdent) {
  const ed = EC.indentLines(value, s, e, outdent);
  if (!ed) return null;
  const v = value.slice(0, ed.s) + ed.text + value.slice(ed.e);
  if (ed.selS === ed.selE) return v.slice(0, ed.selS) + "|" + v.slice(ed.selS);
  return v.slice(0, ed.selS) + "[" + v.slice(ed.selS, ed.selE) + "]" + v.slice(ed.selE);
}

// ============================================================
// 1. Tab in raw source
// ============================================================
check("Tab on a bullet line -> the whole line indents 4 spaces, the caret follows",
      apply("- a\n- b", 7, 7, false) === "- a\n    - b|");
check("Tab on a task line -> the whole line indents", apply("- [ ] viec", 10, 10, false) === "    - [ ] viec|");
check("Tab on a numbered line -> the whole line indents", apply("1. a\n2. b", 9, 9, false) === "1. a\n    2. b|");
check("Shift+Tab -> outdent 4 spaces", apply("    - b", 7, 7, true) === "- b|");
check("Shift+Tab outdents at most 4 spaces", apply("        - b", 11, 11, true) === "    - b|");
check("Shift+Tab outdents a real tab character", apply("\t- b", 4, 4, true) === "- b|");
check("Shift+Tab on an unindented line does nothing", EC.indentLines("- b", 3, 3, true) === null);
check("CANARY: Shift+Tab does not pull the caret onto the line above",
      apply("- a\n  - b", 6, 6, true) === "- a\n|- b");

check("Tab on a plain text line -> 4 spaces at the caret", apply("abc", 1, 1, false) === "a    |bc");
check("Tab on an empty line -> 4 spaces", apply("", 0, 0, false) === "    |");

check("several lines selected -> all indent, the selection is kept",
      apply("- a\n- b\nc", 0, 7, false) === "[    - a\n    - b]\nc");
check("several lines selected -> Shift+Tab outdents all",
      apply("    - a\n    - b", 0, 15, true) === "[- a\n- b]");
check("CANARY: a selection ending at the next line start does NOT indent that line",
      apply("- a\n- b\n- c", 0, 4, false) === "[    - a\n]- b\n- c");
check("meaningless positions return null",
      EC.indentLines("abc", 5, 5, false) === null && EC.indentLines("abc", 2, 1, false) === null &&
      EC.indentLines("abc", null, null, false) === null);

// A freshly indented item must read back as a sub-item, so the next Enter continues at that level
const after = "- a\n    - b";
const ed = EC.continueList(after, after.length);
check("Enter after Tab continues a sub-item at the same level",
      ed && after.slice(0, ed.s) + ed.text === "- a\n    - b\n    - ");

// ============================================================
// 2. Typing a marker at the start of a paragraph in the render pane
// ============================================================
const G = EC.typedListMarker;
check("'- ' -> bullet", G("- ").kind === "ul");
check("'* ' and '+ ' -> bullet", G("* ").kind === "ul" && G("+ ").kind === "ul");
check("'1. ' -> numbered list from 1", G("1. ").kind === "ol" && G("1. ").start === 1);
check("'3) ' -> numbered list from 3", G("3) ").start === 3);
check("contenteditable's nbsp still matches", G("-\u00a0").kind === "ul" && G("2.\u00a0").start === 2);
check("CANARY: text being typed is not changed", G("- viec") === null && G("ab- ") === null);
check("CANARY: '-' without a space is not changed yet", G("-") === null && G("1.") === null);
check("plain text is not a marker", G("") === null && G("x ") === null && G("1 ") === null);

// ============================================================
// 3. The DOM part (reading the source)
// ============================================================
const iT = SRC.indexOf("Enter continues list / task lines");
const H = SRC.slice(iT);
check("there is a Tab listener", /e\.key !== "Tab"/.test(H));
check("CANARY: Ctrl+Tab / Alt+Tab still belong to the browser and the OS",
      /if \(e\.ctrlKey \|\| e\.metaKey \|\| e\.altKey \|\| yieldKey\(e\)\) return;/.test(H));
check("Tab yields to the Vietnamese IME and to an open menu",
      /function yieldKey\(e\)/.test(H) && /e\.isComposing \|\| e\.keyCode === 229/.test(H) &&
      /pop \|\| document\.querySelector\("\.ts-pop"\)/.test(H));
check("CANARY: a sub-item goes INSIDE its parent li, execCommand indent is not used",
      /above\.appendChild\(sub\)/.test(H) && !/execCommand\("indent"\)/.test(SRC) && !/execCommand\("outdent"\)/.test(SRC));
check("Shift+Tab takes the items after it down as children, keeping the order",
      /while \(li\.nextSibling\) sub\.appendChild\(li\.nextSibling\)/.test(H));
check("hand-made DOM changes fire input to mark the note edited", /function markEdited\(wys\)/.test(H) &&
      /markEdited\(ctx\.wys\)/.test(H));
check("typed markers only count in plain paragraphs, not in li/code/quotes",
      /el\.closest\("li,pre,code,blockquote"\)/.test(H));
check("a numbered list typed from a number other than 1 keeps its start", /setAttribute\("start"/.test(H));
check("INDENT is 4 spaces", /var INDENT = " {4}";/.test(SRC));
// Render pane, Tab outside a list: nothing is inserted (non-breaking spaces would end up in the
// saved markdown), but the key is still swallowed so focus stays in the editor.
const tabHandler = H.slice(H.indexOf('e.key !== "Tab"'), H.indexOf("}, true);", H.indexOf('e.key !== "Tab"')));
check("CANARY: Tab outside a list inserts no non-breaking spaces",
      tabHandler.length > 0 && !/\u00a0|\\u00a0|&nbsp;/i.test(tabHandler) &&
      !/insertText/.test(tabHandler.slice(tabHandler.indexOf("if (e.shiftKey) return;"))));
check("Tab outside a list still keeps focus in the editor",
      /if \(e\.shiftKey\) return;[\s\S]*e\.preventDefault\(\);\s*$/.test(tabHandler));
check("does NOT use the em dash character", !SRC.includes("\u2014"));

console.log(fails.length ? "\nFAIL: " + fails.length : "\nAll green");
process.exit(fails.length ? 1 : 0);
