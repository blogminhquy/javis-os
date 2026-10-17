// 0.197.0: unread count, @ mark and muted bell on the team list; the Mute item in a team's row menu (dashboard/teams.js).
//
//     node tests/js/test_team_unread_ui.js
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(root, "dashboard", f), "utf8");
const vi = JSON.parse(read("i18n/vi.json"));
const en = JSON.parse(read("i18n/en.json"));
const TM = require(path.join(root, "dashboard", "teams.js"));
const css = read("console.css");
const src = read("teams.js");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 400)));
  if (!cond) fails++;
}

const t = { team_id: "a", name: "Web", unread: { n: 3, at: 1 }, last: { ts: 100 }, updated_at: 100 };
const h = TM.unreadHtml(t, "x");
check("a team with unread messages shows the count in the navbar bell's pill", /class="notification-badge tm-unread"[^>]*>3</.test(h), h);
check("a message calling the owner adds the @ mark", h.includes('class="tm-at-badge"') && h.includes(">@<"), h);
check("more than 99 reads 99+", TM.unreadHtml({ team_id: "a", unread: { n: 120, at: 0 } }, "").includes(">99+<"));
check("nothing unread draws nothing", TM.unreadHtml({ team_id: "a", unread: { n: 0, at: 0 } }, "") === "");
check("the team open on screen shows no badge (the owner is reading it)", TM.unreadHtml(t, "a") === "");
check("a muted team keeps its count, drawn grey", TM.unreadHtml(Object.assign({}, t, { muted: true }), "x").includes("tm-unread is-muted"));

const row = TM.teamListHtml([t], "x", 200, null, null, null);
check("the row is bold while unread and carries a copy of the marks for the logo strip",
  row.includes('class="tm-team has-unread"') && row.includes('class="tm-mini-unread"'), row);
const mrow = TM.teamListHtml([Object.assign({}, t, { muted: true })], "x", 200, "a", null, null);
check("a muted team shows the bell-off mark next to its name", mrow.includes('class="tm-muted"'), mrow);
check("the row menu turns notifications back on for a muted team", mrow.includes('data-mute-team="a" data-on="0"'), mrow);
const orow = TM.teamListHtml([t], "x", 200, "a", null, null);
check("and off for a team that notifies", orow.includes('data-mute-team="a" data-on="1"'), orow);
check("the strip shows the marks on the logo only when folded",
  css.includes(".tm-mini-unread { display: none; }") && css.includes(".tm-page.tm-mini .tm-mini-unread { display: flex;"));
check("the bell-off icon is vendored", read("vendor/lucide-icons.js").includes('"bell-off"'));
for (const k of ["teams.mute_team", "teams.unmute_team", "teams.muted", "teams.unread_n", "teams.calls_you"]) {
  check("i18n " + k, vi[k] && en[k] && !/[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệịỉĩọỏốồổỗộớờởỡợụủũứừửữựỳỷỹỵ]/i.test(en[k]));
}
check("no dynamic i18n key for the mute item", src.includes('tw(t.muted ? "teams.unmute_team" : "teams.mute_team")'));

// 0.204.0: the @ badge has its own class; sharing ".tm-at" with message mentions drew every mention as a 20px circle.
check("only one .tm-at rule (the mention style), the badge is .tm-at-badge",
  (css.match(/^\.tm-at \{/gm) || []).length === 1 && /^\.tm-at-badge \{/m.test(css));
console.log(fails ? "\nFAIL - " + fails + " check(s)" : "\nPASS - test_team_unread_ui");
process.exit(fails ? 1 : 0);
