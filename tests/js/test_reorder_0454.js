// 0.454.0: one Reorder box (drag or arrows) for projects, pinned chats and tags (reorder-dialog.js).
//
//     node tests/js/test_reorder_0454.js
"use strict";
const fs = require("fs");
const path = require("path");
const { napTruoc } = require("./_thu_tu_nap");
const ROOT = path.join(__dirname, "..", "..");
const R = require(path.join(ROOT, "dashboard", "reorder-dialog.js"));
const read = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const vi = JSON.parse(read("i18n/vi.json")), en = JSON.parse(read("i18n/en.json"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

check("moveItem moves one item", R.moveItem(["a", "b", "c"], 0, 2).join() === "b,c,a");
check("moveItem clamps past the ends", R.moveItem(["a", "b", "c"], 2, 9).join() === "a,b,c" && R.moveItem(["a", "b"], 1, -3).join() === "b,a");
check("moveItem ignores a bad index", R.moveItem(["a", "b"], 5, 0).join() === "a,b");
const tags = [{ key: "z", ten: "Zeta" }, { key: "a", ten: "Alpha" }, { key: "m", ten: "Mu" }];
const k = (g) => g.key, n = (g) => g.ten;
check("sortBy puts ordered keys first, in that order", R.sortBy(tags, ["m", "z"], k, n).map(k).join() === "m,z,a");
check("sortBy sorts the rest by name", R.sortBy(tags, [], k, n).map(k).join() === "a,m,z");
check("sortBy ignores keys that are gone", R.sortBy(tags, ["gone", "z"], k, n).map(k).join() === "z,a,m");
check("sortBy never mutates the list", tags.map(k).join() === "z,a,m");
R._setOrders({ tags_teams: ["m"] });
check("sortTags reads the saved order of its page", R.sortTags(tags, "tags_teams", k, n).map(k).join() === "m,a,z");
check("and another page's order is its own", R.sortTags(tags, "tags_agents", k, n).map(k).join() === "a,m,z");
check("rank says where a key sits", R.rank("tags_teams", "m") === 0 && R.rank("tags_teams", "a") === null);
check("sameOrder compares in order", R.sameOrder(["a", "b"], ["a", "b"]) && !R.sameOrder(["a", "b"], ["b", "a"]));

const ses = read("sessions-ui.js"), ws = read("workspace.js"), tm = read("teams.js"), html = read("index.html");
check("the project menu offers Reorder projects", ses.indexOf('window.t("reorder.menu_projects")') >= 0 && ses.indexOf('"/projects/order"') >= 0);
check("the pinned group has a Reorder button", ses.indexOf("cside-reorder") >= 0 && ses.indexOf('"/sessions/pin-order"') >= 0);
check("the Partners tag menu offers Reorder tags", ws.indexOf('t("reorder.menu_tags")') >= 0 && ws.indexOf('saveTags("tags_agents"') >= 0);
check("the Teams tag menu offers Reorder tags", tm.indexOf('tw("reorder.menu_tags")') >= 0 && tm.indexOf('saveTags("tags_teams"') >= 0);
check("both pages redraw when the order changes", ws.indexOf('"javis:order-changed"') >= 0 && tm.indexOf('"javis:order-changed"') >= 0);
check("reorder-dialog.js runs before the pages that use it",
  napTruoc("reorder-dialog.js", ["sessions-ui.js", "workspace.js", "teams.js"], html));
["reorder.menu_projects", "reorder.menu_tags", "reorder.title_projects", "reorder.title_pins", "reorder.title_tags",
  "reorder.hint", "reorder.drag", "reorder.up", "reorder.down", "reorder.done", "reorder.cancel", "reorder.save_err"]
  .forEach(function (key) { check("key " + key + " in vi and en", !!vi[key] && !!en[key]); });
check("no em dash in reorder-dialog.js", read("reorder-dialog.js").indexOf("—") < 0);

console.log(fails ? "\nĐỎ: " + fails : "\nXANH");
process.exit(fails ? 1 : 0);
