/* Work page (Kanban): a reply typed into a card must survive the 3-second poll.

       node tests/js/test_kanban_reply_box.js

   Owner report 30/10/2026: "nhiều khi vào ấn nó còn không trả lời được trong đó". Every poll
   rebuilt each list with innerHTML, so the card's reply box was replaced by an empty one while
   the owner was typing. fillList now skips a list that did not change, and a list holding a reply
   being typed; post() no longer throws on a non-JSON reply (which left buttons grey for good). */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const JS = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");

const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
};

const src = (JS.match(/\n    function fillList\(node, items, area\) \{[\s\S]*?\n    \}\n/) || [""])[0];
check("fillList found in console.js", src.length > 50);

// A minimal list node: innerHTML writes are counted, and the reply inputs are whatever the test puts there.
function makeNode() {
  return { writes: 0, inputs: [], _html: "",
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = v; this.writes++; this.inputs = []; },
    querySelectorAll() { return this.inputs; } };
}
const document = { activeElement: null };
const fillList = new Function("document", "taskHtml", "esc", "t",
  src + "\nreturn fillList;")(document, (x) => `<div>${x.id}</div>`, (s) => s, (k) => k);

const node = makeNode();
fillList(node, [{ id: "a" }], "attention");
check("first fill writes the list", node.writes === 1);
fillList(node, [{ id: "a" }], "attention");
check("an unchanged list is not rebuilt", node.writes === 1);

const input = { value: "Use the blue" };
node.inputs = [input];
fillList(node, [{ id: "a" }, { id: "b" }], "attention");
check("a list with a reply being typed is not rebuilt", node.writes === 1 && node.inputs[0] === input);

input.value = "";
document.activeElement = input;
fillList(node, [{ id: "a" }, { id: "b" }], "attention");
check("a focused empty reply box is kept too", node.writes === 1);

document.activeElement = null;
fillList(node, [{ id: "a" }, { id: "b" }], "attention");
check("once the box is empty and unfocused the list refreshes", node.writes === 2);

check("a sent reply empties its box so the list can refresh",
  /input\.value = "";\s*input\.blur\(\);\s*closeDrawer\(\);/.test(JS));
const post = (JS.match(/const post = async \(url, extra\) => \{[\s\S]*?\n    \};/) || [""])[0];
check("post() catches a non-JSON reply instead of throwing", /try \{ return await r\.json\(\); \} catch/.test(post), post.slice(0, 80));

if (fails.length) { console.log(`\nFAIL ${fails.length}: ${fails.join(", ")}`); process.exit(1); }
console.log("\nOK - test_kanban_reply_box");
