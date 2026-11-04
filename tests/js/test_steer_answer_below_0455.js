// 0.455.0: a message sent while Javis works and read by the running turn (steer_read) gets its answer BELOW it.
// Before, the step block and answer bubble of that turn had been drawn above the message and stayed there, so the
// owner thought the add-on had not been done. The server stores the answer after the message, so a reload agrees.
const fs = require("fs");
const path = require("path");
const R = path.join(__dirname, "../..");
const app = fs.readFileSync(path.join(R, "dashboard/app.js"), "utf8");

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

const branch = app.slice(app.indexOf('if (data.type === "steer_ack" || data.type === "steer_read"'),
  app.indexOf('if (data.type === "agent_read")'));
check("steer_read on the open chat moves the running turn below the message",
  /data\.type === "steer_read" && isActive && t\) \{ try \{ moveTurnBelow\(t\); \} catch \(e\) \{\} \}/.test(branch));
check("steer_ack (only received, not read yet) does not move anything",
  !/steer_ack"[^\n]*moveTurnBelow/.test(branch));

// Run the real function against a tiny chat list: [user1, steps, answer, add-on, chip].
const src = app.slice(app.indexOf("function moveTurnBelow(t) {"), app.indexOf("// 0.173.1: one automatic /goal round"));
const area = [];
const node = (name) => ({ name, get isConnected() { return area.includes(this); } });
function chatAppend(el) { const i = area.indexOf(el); if (i >= 0) area.splice(i, 1); area.push(el); }
let scrolled = 0;
const scrollBottom = () => { scrolled++; };
const user1 = node("user1"), steps = node("steps"), answer = node("answer"), addOn = node("addon");
let activityEl = node("chip");
area.push(user1, steps, answer, addOn, activityEl);
const moveTurnBelow = new Function("chatAppend", "scrollBottom", "getChip",
  src.replace(/activityEl/g, "getChip()") + "\nreturn moveTurnBelow;")(chatAppend, scrollBottom, () => activityEl);
moveTurnBelow({ buocEl: steps, bubble: answer });
check("order after: first message, add-on, steps, answer, chip",
  area.map((n) => n.name).join(",") === "user1,addon,steps,answer,chip");
check("scrolls to follow", scrolled === 1);

// No bubble yet (still calling tools), no chip: only the step block moves, nothing detached is added.
area.length = 0; activityEl = null;
const loose = node("loose");
area.push(user1, steps, addOn);
moveTurnBelow({ buocEl: steps, bubble: loose });
check("a bubble not in the chat is not added, step block moves",
  area.map((n) => n.name).join(",") === "user1,addon,steps");

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
