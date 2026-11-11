/* chat-list.js - a numbered list continues itself in every chat box (owner, 2026-11-11).
 *
 * Owner: "in every chat box, when the line above carries a number, Enter at the end of the line jumps to the next
 * number, like in Claude". So a NEW LINE typed under "1. first" opens with "2. ":
 *   - the new line is whatever key makes one in that box: Enter on a phone, Shift+Enter on a computer (plain Enter
 *     still sends there, see JavisActs.enterSends in chat-acts.js);
 *   - a new line on an item that is still empty ("2. " and nothing else) takes the number away, which ends the list;
 *   - a new line in the middle of a list pushes the numbers below it up by one.
 * It works AFTER the browser has put the line break in (the `input` event), not on keydown: a phone keyboard and an IME
 * report Enter as an unnamed key, while the line break they insert always arrives as an input event.
 * One delegated listener serves every chat screen (owner rule of 2026-11-05): the boxes are listed in BOXES.
 * The pure part is exported for node tests.
 */
(function () {
  "use strict";

  // The chat boxes: main chat, Team chat, customer reply and its AI draft, the answer under a background-job question,
  // the chatbot trial. A new chat screen adds its box here.
  var BOXES = "#chatInput, .tm-input, .ib-cin textarea, .ib-draft-t, .viec-tl-o, #cbTryText";

  // indent, number, "." or ")", the gap, the text of the item.
  var ITEM = /^([ \t]*)(\d{1,9})([.)])([ \t]+)(.*)$/;

  // `value` is the text of the box right after a line break was typed, `caret` the position just behind that break.
  // Returns the edit to make ({ start, end, text, caret }: replace [start, end) with text, then put the caret there), or
  // null when the line above is not a list item.
  function continueList(value, caret) {
    value = String(value == null ? "" : value);
    if (!(caret > 0) || caret > value.length || value.charAt(caret - 1) !== "\n") return null;
    var lineStart = value.lastIndexOf("\n", caret - 2) + 1;
    var m = ITEM.exec(value.slice(lineStart, caret - 1));
    if (!m) return null;
    var indent = m[1], num = Number(m[2]), mark = m[3];
    var restEnd = value.indexOf("\n", caret);
    if (restEnd < 0) restEnd = value.length;

    if (!m[5].trim()) {
      // An empty item: the list ends here. Only when the item above is the previous number (so this number came from
      // us, not from someone typing "1. " and thinking), and nothing follows the caret on its line.
      if (value.slice(caret, restEnd).trim() || lineStart === 0) return null;
      var above = ITEM.exec(value.slice(value.lastIndexOf("\n", lineStart - 2) + 1, lineStart - 1));
      if (!above || above[1] !== indent || above[3] !== mark || Number(above[2]) !== num - 1) return null;
      return { start: lineStart, end: caret, text: "", caret: lineStart };
    }

    var head = indent + (num + 1) + mark + " ";
    // Items below that carried on the count (num+1, num+2, ...) each move up by one.
    var tail = "", end = restEnd, expect = num + 1;
    while (end < value.length) {
      var next = value.indexOf("\n", end + 1);
      if (next < 0) next = value.length;
      var n = ITEM.exec(value.slice(end + 1, next));
      if (!n || n[1] !== indent || n[3] !== mark || Number(n[2]) !== expect) break;
      tail += "\n" + n[1] + (expect + 1) + n[3] + n[4] + n[5];
      expect++;
      end = next;
    }
    if (!tail) return { start: caret, end: caret, text: head, caret: caret + head.length };
    return { start: caret, end: end, text: head + value.slice(caret, restEnd) + tail, caret: caret + head.length };
  }

  // The input event of a line break the user just typed (not a paste, not an IME still composing).
  function isLineBreak(e) {
    if (!e || e.isComposing) return false;
    var type = e.inputType;
    return type === "insertLineBreak" || type === "insertParagraph" || (type === "insertText" && e.data === "\n");
  }

  var pure = { continueList: continueList, isLineBreak: isLineBreak, BOXES: BOXES };
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
  if (typeof document === "undefined" || !document.addEventListener) return;

  // Make the edit the way typing would, so Ctrl+Z takes it back; where the browser refuses, set the text directly and
  // tell the box's own listeners (auto-grow, drafts) with an input event. Neither event is a line break, so this never
  // loops.
  function apply(box, edit) {
    var before = box.value;
    box.setSelectionRange(edit.start, edit.end);
    try { document.execCommand(edit.text ? "insertText" : "delete", false, edit.text); } catch (e) { /* fall through */ }
    if (box.value === before) {
      box.setRangeText(edit.text, edit.start, edit.end, "end");
      box.dispatchEvent(new Event("input", { bubbles: true }));
    }
    box.setSelectionRange(edit.caret, edit.caret);
  }

  document.addEventListener("input", function (e) {
    var box = e.target;
    if (!isLineBreak(e) || !box || box.tagName !== "TEXTAREA" || !box.matches || !box.matches(BOXES)) return;
    if (box.selectionStart !== box.selectionEnd) return;
    var edit = continueList(box.value, box.selectionStart);
    if (edit) apply(box, edit);
  });

  window.JavisChatList = pure;
})();
