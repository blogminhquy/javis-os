/* Enter in the .md editor continues a task/list line by itself.

       node tests/js/test_enter_list_continuation.js

   Requested by the owner (2026-09-11): pressing Enter while typing a task must give a new task
   right away, without reaching for the checkbox button on every line.

   Four places break SILENTLY, so they are guarded:

     1. Pattern order. "- [ ] x" also matches the bullet pattern "- x", so checking bullets first
        makes Enter produce a plain bullet and the checkbox is lost.
     2. Empty line. Without a way out of the list the user is stuck: Enter keeps spawning empty
        tasks. Enter on an empty task must REMOVE the marker.
     3. Checked box. Continuing from "- [x] done" must give an unchecked "- [ ] ", or the new task
        is born already marked done.
     4. Vietnamese IME. Enter while the IME is committing text (isComposing) is not a newline;
        hijacking it loses characters when typing Vietnamese in the editor. */
const fs = require("fs");
const path = require("path");
const EC = require("../../dashboard/editor-cmds.js");
const SRC = fs.readFileSync(path.join(__dirname, "../../dashboard/editor-cmds.js"), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Reading the marker of one line
// ============================================================
const P = EC.parseListLine;
check("reads an unchecked task", JSON.stringify(P("- [ ] mua sữa")) ===
      JSON.stringify({ kind: "task", indent: "", content: "mua sữa", marker: "- [ ] ", next: "- [ ] " }));
check("a checked task is still a task", P("- [x] xong").kind === "task");
check("CANARY: continuing from a checked task gives an UNCHECKED box", P("- [x] xong").next === "- [ ] ");
check("* and + make tasks too", P("* [ ] a").kind === "task" && P("+ [ ] a").kind === "task");
check("CANARY: tasks are checked before bullets, not read as a bullet", P("- [ ] a").kind !== "ul");

check("bullet", P("- việc").kind === "ul" && P("- việc").next === "- ");
check("a numbered list goes up by one", P("3. bước ba").next === "4. ");
check("a numbered list in the 2) style keeps its mark", P("2) hai").next === "3) ");
check("multi-digit numbers still go up right", P("9. chín").next === "10. ");
check("a sub-item keeps its indent", P("    - con").next === "    - ");

check("a plain text line is not a list", P("chỉ là chữ") === null);
check("an empty line is not a list", P("") === null);
check("a heading is not a list", P("## Tiêu đề") === null);
check("CANARY: a --- rule is not read as a bullet", P("---") === null);
check("the render pane's nbsp still matches", P("-\u00a0[ ]\u00a0việc").kind === "task");

// ============================================================
// 2. Enter in the raw source pane: the edit
// ============================================================
const E = EC.continueList;
// Apply the edit to the string to see the real result; "|" is where the caret ends up.
function apply(value, pos) {
  const ed = E(value, pos);
  if (!ed) return null;
  const v = value.slice(0, ed.s) + ed.text + value.slice(ed.e);
  const p = ed.s + ed.text.length;
  return v.slice(0, p) + "|" + v.slice(p);
}

check("Enter at the end of a task line -> new task", apply("- [ ] mua sữa", 13) === "- [ ] mua sữa\n- [ ] |");
check("Enter mid task line -> the text after moves down into the new task",
      apply("- [ ] mua sữa", 9) === "- [ ] mua\n- [ ] | sữa");
check("Enter at the end of a bullet line -> new bullet", apply("- việc", 6) === "- việc\n- |");
check("Enter at the end of a numbered line -> next number", apply("1. một", 6) === "1. một\n2. |");

// A line with only a marker: Enter REMOVES the marker and the user leaves the list.
check("Enter on an empty task -> marker removed", apply("- [ ] ", 6) === "|");
check("Enter on an empty bullet -> marker removed", apply("- ", 2) === "|");
check("removing the marker leaves the other lines alone",
      apply("- [ ] a\n- [ ] \n- [ ] b", 14) === "- [ ] a\n|\n- [ ] b");

check("a plain line gets a normal Enter", E("chỉ là chữ", 5) === null);
check("empty text gets a normal Enter", E("", 0) === null);
check("CANARY: caret still inside the marker does not nest markers", E("- [ ] a", 3) === null);
check("caret just past the marker continues", !!E("- [ ] a", 6));
check("a meaningless caret position returns null", E("- [ ] a", null) === null && E("- [ ] a", 99) === null);

// Inside a code fence "- a" is code, not a list: Enter must not continue it.
check("CANARY: no list continuation inside a ``` fence", E("```\n- a\n```", 7) === null);
check("CANARY: no list continuation inside a ~~~ fence", E("~~~\n- [ ] a\n~~~", 11) === null);
check("no continuation in an unclosed fence either", E("text\n```js\n1. a", 15) === null);
check("lists after a closed fence continue again", apply("```\ncode\n```\n- a", 16) === "```\ncode\n```\n- a\n- |");

// The line the caret is on, not the first line of the file
check("continues the caret's line in a multi-line file",
      apply("# Ghi chú\n\n- [ ] một\n", 20) === "# Ghi chú\n\n- [ ] một\n- [ ] |\n");
check("a sub-item's indent is kept when continuing",
      apply("- [ ] cha\n    - [ ] con", 23) === "- [ ] cha\n    - [ ] con\n    - [ ] |");

// ============================================================
// 3. The key listeners in the browser (reading the source)
// ============================================================
const iH = SRC.indexOf("Enter continues list / task lines");
check("there is an Enter listener in the DOM part", iH > 0);
const H = SRC.slice(iH);
check("CANARY: Enter while the Vietnamese IME is committing text is not hijacked",
      /e\.isComposing \|\| e\.keyCode === 229/.test(H));
check("Shift/Ctrl/Alt + Enter still belong to the browser",
      /e\.shiftKey \|\| e\.ctrlKey \|\| e\.metaKey \|\| e\.altKey/.test(H));
check("with the \"/\" menu or the task suggestion menu open, Enter goes to the menu",
      /if \(pop \|\| document\.querySelector\("\.ts-pop"\)\)/.test(H));
check("a selected range is left alone", /selectionStart !== ta\.selectionEnd/.test(H));
check("runs in both modes: raw source and render pane",
      /ctx\.mode\(\) === "source"/.test(H) && /liAtCaret\(ctx\.wys\)/.test(H));
check("render pane: an empty task leaves the list", /liIsEmpty\(li\)\) \{ if \(exitList\(li\)\)/.test(H));
check("render pane: the new li gets a checkbox", /fillNewTask/.test(H) && H.includes("insertAdjacentHTML(\"afterbegin\", CB_HTML)"));
check("CANARY: the new li does not carry the done strike-through", /classList\.remove\("task-done"\)/.test(H));
// Enter at the START of a line: Chromium pushes the new line ABOVE and the caret stays on the old
// one. Looking only at the caret's li would leave the line above as a plain bullet.
check("Enter at the start of a line: the new line ABOVE becomes a task too",
      /var above = li\.previousElementSibling/.test(H) && /addCheckbox\(above\)/.test(H));
check("editing the textarea prefers execCommand so it can be undone",
      /document\.execCommand\("insertText", false, ed\.text\)/.test(H));
check("the fallback still fires an input event", /dispatchEvent\(new Event\("input", \{ bubbles: true \}\)\)/.test(H));
// The checkbox button and Enter SHARE one li lookup, not two copies drifting apart.
check("one li lookup shared by the checkbox button and Enter",
      /function liAtCaret\(wys\)/.test(SRC) && !/function liHienTai\(/.test(SRC));
check("does NOT use the em dash character", !SRC.includes("\u2014"));

console.log(fails.length ? "\nFAIL: " + fails.length : "\nAll green");
process.exit(fails.length ? 1 : 0);
