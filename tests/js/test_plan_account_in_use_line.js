// A plan card's status line names the account a turn runs on NOW (owner's video, 10/11/2026).
//
//     node tests/js/test_plan_account_in_use_line.js
//
// The Claude Code card held two accounts, "TuanFernel-Max100" first (chat was using it) and account 1 "Kinken-Pro".
// The status line kept reading "Kinken-Pro · kinken2178@... · Pro": account 1's name, e-mail and plan, whatever
// account was in use. Loads the REAL helpers out of console.js into a vm.
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");

const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : ""));
  if (!cond) fails.push(name);
}

const a = SRC.indexOf("  const acctNameTag = (pid) =>");
const b = SRC.indexOf("  // A subscription CLI with nothing set picks its own model", a);
check("the status line helpers are in console.js", a > 0 && b > a);
const ctx = { t: (k, v) => (k === "models.pacct_n" ? "Account " + v.n : k), Date, out: {} };
vm.createContext(ctx);
vm.runInContext("let ACCT_NAMES = {}, ACCT_ITEMS = {}, ACCT_KEYED = {};\n" + SRC.slice(a, b)
  + "\nout.line = acctLine; out.set = (n, i, k) => { ACCT_NAMES = n; ACCT_ITEMS = i; ACCT_KEYED = k || {}; };", ctx);
const { line, set } = ctx.out;

const P = "anthropic-cli";
const soon = Date.now() / 1000 + 3600;
const main = { id: "main", main: true, label: "Kinken-Pro", enabled: true, signed_in: true, resting_until: 0 };
const extra = { id: "acc_b", main: false, label: "TuanFernel-Max100", enabled: true, signed_in: true, resting_until: 0,
                email: "tuan@example.com", plan: "Max" };
const OWN = ["kinken@example.com", "Pro"];

set({ [P]: "Kinken-Pro" }, { [P]: [main] });
check("one account: account 1's name, e-mail and plan, as before", line(P, OWN) === " · Kinken-Pro · kinken@example.com · Pro", line(P, OWN));
set({}, { [P]: [{ ...main, label: "" }] });
check("one account without a name: e-mail and plan only", line(P, OWN) === " · kinken@example.com · Pro", line(P, OWN));

set({ [P]: "Kinken-Pro" }, { [P]: [main, extra] });
check("two accounts, account 1 first: account 1's line", line(P, OWN) === " · Kinken-Pro · kinken@example.com · Pro", line(P, OWN));

set({ [P]: "Kinken-Pro" }, { [P]: [extra, main] });
check("the owner's case: the extra account runs first, the line names IT, with its own e-mail and plan",
  line(P, OWN) === " · TuanFernel-Max100 · tuan@example.com · Max", line(P, OWN));
check("account 1's e-mail and plan are not shown for another account", !/kinken|Pro$/.test(line(P, OWN)), line(P, OWN));

set({ [P]: "Kinken-Pro" }, { [P]: [main, extra].map((x, i) => (i === 0 ? { ...x, resting_until: soon } : x)) });
check("account 1 resting: the line moves to the account that runs", line(P, OWN) === " · TuanFernel-Max100 · tuan@example.com · Max", line(P, OWN));

set({ [P]: "Kinken-Pro" }, { [P]: [{ ...extra, resting_until: soon }, main] });
check("the extra account resting: back to account 1's line", line(P, OWN) === " · Kinken-Pro · kinken@example.com · Pro", line(P, OWN));
set({ [P]: "Kinken-Pro" }, { [P]: [{ ...extra, enabled: false }, main] });
check("the extra account switched off: account 1's line", line(P, OWN) === " · Kinken-Pro · kinken@example.com · Pro");
set({ [P]: "Kinken-Pro" }, { [P]: [{ ...extra, signed_in: false }, main] });
check("the extra account signed out: account 1's line", line(P, OWN) === " · Kinken-Pro · kinken@example.com · Pro");

set({ [P]: "Kinken-Pro" }, { [P]: [{ ...extra, email: "", plan: "" }, main] });
check("an extra account whose e-mail and plan are unknown shows its name alone, never account 1's",
  line(P, OWN) === " · TuanFernel-Max100", line(P, OWN));
set({ [P]: "Kinken-Pro" }, { [P]: [{ ...extra, label: "", email: "", plan: "" }, main] });
check("an extra account without a name gets its number", line(P, OWN) === " · Account 1", line(P, OWN));

set({ [P]: "Kinken-Pro" }, { [P]: [extra, main] }, { [P]: true });
check("Claude Code on an API key: no plan account is in use, the card's own line stays",
  line(P, OWN) === " · Kinken-Pro · kinken@example.com · Pro", line(P, OWN));

console.log(fails.length ? "\nRED: " + fails.length : "\nGREEN");
process.exit(fails.length ? 1 : 0);
