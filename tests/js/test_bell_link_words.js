// Owner, 22/11/2026 (screenshot): a bell card's title read "Anh ơi, 20:00 tối nay là [Javis OS K8 Buổi 2](https://www.
// google.com/calendar/event?eid=a2E4dTM4...". The raw markdown link printed as text, and its unbroken URL ran past the
// card's right edge. The server now keeps a link's words only (server/notice_text.py plain_links), but notices already
// in the bell still carry the raw link, so the card does the same, and the card wraps any long word it still meets.
//   node tests/js/test_bell_link_words.js
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const D = path.join(__dirname, "..", "..", "dashboard");
const src = fs.readFileSync(path.join(D, "notifications.js"), "utf8");
const helper = src.match(/ {2}function plainLinks\(s\) \{[\s\S]*?\n {2}\}\n/);
assert.ok(helper, "plainLinks() is in notifications.js");
const line = src.match(/ {2}function dongPhu\(item\) \{[\s\S]*?\n {2}\}\n/);
assert.ok(line, "dongPhu() is in notifications.js");
const fns = new Function(helper[0] + line[0] + "; return { plainLinks: plainLinks, dongPhu: dongPhu };")();

const RAW = "Anh ơi, 20:00 tối nay là [Javis OS K8 Buổi 2](https://www.google.com/calendar/event?eid=a2E4dTM4Zm5zbDRk) nhé";
assert.strictEqual(fns.plainLinks(RAW), "Anh ơi, 20:00 tối nay là Javis OS K8 Buổi 2 nhé", "a link keeps its words");
// The server cuts a title at 120 characters, often in the middle of the URL: the cut link loses its URL too.
const CUT = "Anh ơi, 20:00 tối nay là [Javis OS K8 Buổi 2](https://www.google.com/calendar/event?eid=a2E4dTM4Zm5zbDRkYWkw";
assert.strictEqual(fns.plainLinks(CUT), "Anh ơi, 20:00 tối nay là Javis OS K8 Buổi 2", "a link cut at 120 characters");
assert.strictEqual(fns.plainLinks("![Ảnh bìa](https://x.io/a.png) xong"), "Ảnh bìa xong", "an image keeps its alt text");
assert.strictEqual(fns.plainLinks("Đơn [mới] (3 cái)"), "Đơn [mới] (3 cái)", "CANARY: brackets that are not a link stay");

// The line under the title: a body that opens with the same sentence as a plain title is still the same line.
assert.strictEqual(fns.dongPhu({ title: fns.plainLinks(RAW), body: RAW }), "", "a linked body equal to the title is hidden");
assert.strictEqual(fns.dongPhu({ title: "Nhắc lịch", body: "Nhắc lịch\nVào [phòng họp](https://meet.google.com/abc-defg)" }),
  "Vào phòng họp", "a detail line keeps a link's words");

// The title on both card kinds goes through plainLinks before it is printed.
assert.ok(/"<h4>" \+ esc\(plainLinks\(item\.title\)/.test(src), "a My notices card prints its title without the raw link");

// Anything still long and unbroken (a bare URL, a code) wraps inside the card instead of running past its edge.
const css = fs.readFileSync(path.join(D, "style.css"), "utf8");
const card = css.match(/\n\.noti-card \{[^}]*\}/);
assert.ok(card && /overflow-wrap: anywhere/.test(card[0]), "a bell card wraps a long unbroken word");
console.log("ok   bell card: a markdown link shows its words, a long word wraps inside the card");
