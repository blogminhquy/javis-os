// The "@" button of a team chat (owner, 18/11/2026).
//
//     python tests/run.py --js team_at_jump -v
//
// Owner: "nếu có tin được tag vào thì phải có 1 nút popup nhỏ để ấn vào sẽ lướt lên tin được tag chủ nhóm khi đó sẽ dễ
// đọc hơn rất nhiều", "kiểu có cái nút này, và nếu được tag thì sẽ có @ và ấn vào thì vào tin tag" (a round button with a
// count under it). Pure functions of teams.js under node, plus the page wiring read from the source.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const TM = require(path.join(ROOT, "dashboard", "teams.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const src = fs.readFileSync(path.join(ROOT, "dashboard", "teams.js"), "utf8");

// ic() draws nothing under node, so the icon name is read from the source.
function teamsSrcIcon() { return /function atJumpHtml\(n\) \{\s*return n \? ic\("chevrons-up"\)/.test(src); }

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 600)));
  if (!cond) fails++;
}

// ───────────── which messages still wait ─────────────
const asks = [{ id: 30, ts: 300 }, { id: 10, ts: 100 }, { id: 20, ts: 200 }];
check("every message calling the owner waits, oldest first", JSON.stringify(TM.atPending(asks, 0, {})) === "[10,20,30]",
  TM.atPending(asks, 0, {}));
check("a message the owner has seen on screen no longer waits", JSON.stringify(TM.atPending(asks, 0, { 10: true, 30: true })) === "[20]");
check("the owner wrote after it: it no longer waits (only the ones after the owner's last message)",
  JSON.stringify(TM.atPending(asks, 200, {})) === "[30]");
check("times in milliseconds count like seconds", JSON.stringify(TM.atPending([{ id: 5, ts: 1700000250000 }, { id: 6, ts: 1700000150000 }], 1700000200, {})) === "[5]");
check("nothing to show: an empty list", JSON.stringify(TM.atPending([], 0, {})) === "[]" && JSON.stringify(TM.atPending(null, 0, null)) === "[]");
check("the owner's last message comes from ownerSaidAt (a message that hands a job does not count as an answer)",
  TM.ownerSaidAt([{ author_kind: "owner", ts: 250 }, { author_kind: "owner", ts: 400, meta: { as_job: true } }]) === 250);

// ───────────── the button ─────────────
// 18/11/2026 (owner, a Zalo screenshot): "nút nó phải ở phía trên một chút và dấu mũi tên lên trên sẽ hợp lý hơn".
let h = TM.atJumpHtml(3);
check("an up arrow in the button, '@' and the count in a badge under it", h.includes('<span class="notification-badge tm-at-n">@3</span>')
  && teamsSrcIcon(), h);
check("a large count is cut to 99+", TM.atJumpHtml(140).includes(">@99+<"));
check("no message waiting: the button is empty", TM.atJumpHtml(0) === "");
check("words: a label in both languages with the count", vi["teams.at_jump"].includes("{n}") && en["teams.at_jump"].includes("{n}")
  && !/[–—]/.test(vi["teams.at_jump"] + en["teams.at_jump"]));

// ───────────── page wiring ─────────────
check("page: the messages counted are the ones drawn with the 'asks you' flag",
  src.includes('box.querySelectorAll(".tm-msg-asks[data-mid]")') && src.includes("atPending(asks, ownerSaidAt(S.msgs), atSeenMap())"));
check("page: the button is the list's first child (sticky top) and is refreshed on every draw of the list",
  /if \(S\.atBtn\) \{\s*if \(box\.firstChild !== S\.atBtn\) box\.insertBefore\(S\.atBtn, box\.firstChild\);\s*updateAtJump\(true\);/.test(src)
  && src.includes('box.firstChild.classList.contains("tm-at-jump") ? box.firstChild : null;'));
check("page: a press goes to the oldest waiting message, in the middle, flashing, and counts it read",
  /function atJump\(\) \{[^]*?\(S\.atPend \|\| \[\]\)\[0\][^]*?scrollIntoView\(\{ block: "center", behavior: "smooth" \}\)[^]*?tm-msg-flash[^]*?markAtSeen\(id\)/.test(src)
  && src.includes('if (t.classList.contains("tm-at-jump")) return atJump();'));
check("page: a message is read once half of it is on screen, watched with IntersectionObserver",
  src.includes("new IO(onAtSeen, { root: box") && src.includes("en.intersectionRatio < 0.5 && !tall"));
check("page: what was read is kept per team on this device, never throwing without storage",
  src.includes('var AT_SEEN_KEY = "javis.teams.atSeen";') && /function markAtSeen[^]*?try \{[^]*?localStorage\.setItem\(AT_SEEN_KEY/.test(src));
check("CSS: round, sticky at the TOP right, takes no room in the list, hidden until shown, 44px on a phone, red count",
  /\.tm-at-jump \{ position: sticky; top: 10px; align-self: flex-end; margin: 10px 12px -50px 0;[^}]*display: none;[^}]*border-radius: 50%;/.test(css)
  && css.includes(".tm-at-jump.show { display: inline-flex; }")
  && /@media \(max-width: 760px\) \{ \.tm-at-jump \{ width: 44px; height: 44px; margin-bottom: -54px; \} \}/.test(css)
  && /\.tm-at-jump \.tm-at-n \{[^}]*background: var\(--red\);/.test(css));

if (fails) { console.log("\nFAILED " + fails); process.exit(1); }
console.log("\nALL OK");
