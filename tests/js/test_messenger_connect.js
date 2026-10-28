// Facebook Messenger card (0.301.0): pure render helpers of dashboard/messenger-connect.js.
//   node tests/js/test_messenger_connect.js
const path = require("path");
const assert = require("assert");
const M = require(path.join(__dirname, "..", "..", "dashboard", "messenger-connect.js"));

let fails = 0;
function check(name, fn) {
  try { fn(); console.log("ok   " + name); } catch (e) { fails++; console.log("FAIL " + name + "  [" + e.message + "]"); }
}

const chk = { ok: false, items: [
  { id: "token", ok: true, label: "Token is valid", detail: "", fix: "" },
  { id: "webhook_fields", ok: false, label: "Webhook receives messages", detail: "messages", fix: "Click Repair." },
  { id: "expiry", ok: null, label: "Does not expire", detail: "2027-01-01", fix: "Reconnect." },
] };

check("one row per item, with state classes", () => {
  const h = M.checklistHtml(chk);
  assert.strictEqual((h.match(/class="msc-row /g) || []).length, 3);
  assert.ok(h.includes('msc-row ok') && h.includes('msc-row bad') && h.includes('msc-row warn'));
});
check("fix shown only for rows that are not green", () => {
  const h = M.checklistHtml({ items: [{ ok: true, label: "a", fix: "SHOULD-NOT-SHOW" }, { ok: false, label: "b", fix: "do this" }] });
  assert.ok(!h.includes("SHOULD-NOT-SHOW") && h.includes("do this"));
});
check("summary counts red rows only", () => {
  const h = M.summaryHtml(chk);
  assert.ok(h.includes("msc-sum bad"));
  assert.ok(M.summaryHtml({ items: [{ ok: true }, { ok: null }] }).includes("msc-sum ok"));
});
check("labels are escaped", () => {
  const h = M.checklistHtml({ items: [{ ok: false, label: "<img src=x>", detail: "\"x\"", fix: "<b>" }] });
  assert.ok(!h.includes("<img") && !h.includes("<b>"));
});
check("account card lists bots and has the three actions", () => {
  const h = M.accountHtml({ id: "acc_1", page_id: "123", page_name: "Em Mi", app_id: "9",
                            bots: [{ id: "b", name: "Bot Mi", enabled: false }] });
  assert.ok(h.includes('data-id="acc_1"') && h.includes("Bot Mi") && h.includes("Page ID 123"));
  ["check", "repair", "renew"].forEach(a => assert.ok(h.includes('data-act="' + a + '"'), a));
});
check("form disables connect without HTTPS and has secret fields as password", () => {
  const off = M.formHtml({ https: false });
  assert.ok(/data-f="go" disabled/.test(off) && off.includes("msc-warn"));
  const on = M.formHtml({ https: true });
  assert.ok(!/data-f="go" disabled/.test(on) && !on.includes("msc-warn"));
  assert.ok(/data-f="app_secret" type="password"/.test(on) && /data-f="token" type="password"/.test(on));
});

// 0.332.0 (owner: "lạc quẻ"): Messenger follows the Connections page's own frame.
const fs = require("fs");
const con = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "console.js"), "utf8");
check("a card in the Available grid, filed under messaging, opening the form", () => {
  const h = M.catCard("Nhắn tin");
  assert.ok(/class="cat-card msc-cat" data-cat="Nhắn tin"/.test(h) && /data-msc-open="1"/.test(h));
  assert.ok(con.includes('window.JavisMessenger.catCard((cat.find(c => c.id === "zalo") || {}).category || "")'));
});
check("connected Pages are one card in the Connected list, nothing when none", () => {
  assert.strictEqual(M.groupHtml([]), "");
  const h = M.groupHtml([{ id: "a1", page_id: "1", page_name: "Shop", bots: [] }, { id: "a2", page_id: "2", page_name: "Kho", bots: [] }]);
  assert.ok(h.includes("prov-card conn-card msc-group") && /data-msc-open="1"/.test(h));
  // 0.367.0 (owner, 28/10/2026): the Pages open in a popup like the bot cards; the card shows only the count.
  assert.ok(h.includes("data-msc-pages") && h.includes("msc.pages_n") && !h.includes('data-id="a1"'), "pages are not inlined");
  assert.ok(M.accountHtml({ id: "a1", page_id: "1", bots: [] }).includes('data-id="a1"') && typeof M.openPages === "function");
  const i = con.indexOf('id="connList"'), j = con.indexOf('id="mcpMessenger"'), k = con.indexOf('id="connNone"');
  assert.ok(i > 0 && j > i && k > j, "slot sits right under the connected list, inside its section");
});
check("no section of its own, form in the shared dialog", () => {
  assert.ok(!con.includes("Facebook Messenger setup card (0.301.0)"));
  assert.ok(con.includes("window.JavisConnModal = { open: connModal, head: mHead, close: closeConnModal }"));
  const src = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "messenger-connect.js"), "utf8");
  assert.ok(src.includes("M.open(M.head(") && !src.includes('class="cview-section msc"'));
  assert.ok(!/class="lv-card lv-card-new msc-form"/.test(M.formHtml({ https: true })));
});

if (fails) { console.log("\n" + fails + " FAILED"); process.exit(1); }
console.log("\nall ok");
