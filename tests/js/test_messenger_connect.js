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

// 0.434.0: Log in with Facebook and Page comments.
check("form leads with the login: App ID, App secret, addresses to copy, comment mode", () => {
  const h = M.formHtml({ https: true, oauth_redirect: "https://j.example/messenger/oauth/callback",
                         privacy_url: "https://j.example/messenger/privacy" });
  assert.ok(/data-f="login"/.test(h) && !/data-f="login" disabled/.test(h));
  assert.ok(h.includes('data-copy="https://j.example/messenger/oauth/callback"') && h.includes('data-copy="https://j.example/messenger/privacy"'));
  assert.ok(/data-f="app_id"/.test(h) && /data-f-cmt="1"/.test(h));
  assert.ok(h.indexOf('data-f="login"') < h.indexOf('data-f="page_id"'), "the paste flow comes after the login");
  assert.ok(/class="msc-manual" hidden/.test(h), "the paste flow is folded");
  assert.ok(/data-f="login" disabled/.test(M.formHtml({ https: false })), "no login without HTTPS");
});
check("comment mode select defaults to inbox and marks the current mode", () => {
  assert.ok(/value="inbox" selected/.test(M.commentSelect("inbox", "data-x")));
  assert.ok(/value="reply" selected/.test(M.commentSelect("reply", "data-x")));
  assert.ok(/value="reply" selected/.test(M.accountHtml({ id: "a", page_id: "1", bots: [], comments: "reply" })));
  assert.ok(/data-act-mode="1"/.test(M.accountHtml({ id: "a", page_id: "1", bots: [] })));
});
check("Page picker: one ticked row per Page, names escaped, a connect button", () => {
  const h = M.pickHtml([{ id: "1", name: "Shop <b>", picture: "https://x/p.jpg" }, { id: "2", name: "Kho" }]);
  assert.strictEqual((h.match(/data-page="/g) || []).length, 2);
  assert.strictEqual((h.match(/ checked>/g) || []).length, 2);
  assert.ok(h.includes("Shop &lt;b&gt;") && !h.includes("Shop <b>") && h.includes('data-f="finish"') && h.includes('src="https://x/p.jpg"'));
  assert.strictEqual(M.pickHtml([]), "");
});
check("results: checklist for a connected Page, the error for a failed one", () => {
  const h = M.resultsHtml([{ ok: true, page_name: "Shop", check: chk }, { ok: false, page_id: "2", error: "lỗi <210>" }]);
  assert.ok(h.includes("msc-checks") && h.includes("lỗi &lt;210&gt;") && !h.includes("<210>"));
});

// 0.436.1: GitHub guides on the form, and the Zalo group note kept to Zalo.
check("form links the full guide and, in the paste section, the step-by-step guide", () => {
  const h = M.formHtml({ https: true });
  assert.ok(h.includes("docs/en/31-messenger.md") && h.includes("docs/en/31-messenger-step-by-step.md"));
  assert.ok(h.indexOf("31-messenger-step-by-step.md") > h.indexOf('class="msc-manual"'), "step guide sits in the paste section");
  for (const f of ["docs/31-messenger.md", "docs/31-messenger-tung-buoc.md", "docs/en/31-messenger.md", "docs/en/31-messenger-step-by-step.md"]) {
    assert.ok(fs.existsSync(path.join(__dirname, "..", "..", f)), f);
  }
});
check("the add-channel form shows the Zalo group note only for Zalo Bot", () => {
  const conv = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "conversations.js"), "utf8");
  assert.ok(conv.includes('r.vao_duoc_nhom === false && chon === "zalo"'));
  assert.ok(conv.includes("guideUrl(k)") && conv.includes('window.t("ht.huong_dan")'));
});

// 0.436.2: one place to connect. The card shows the webhook and verify token; the Chatbot form points to the card.
check("card shows the webhook address and verify token to copy", () => {
  const h = M.formHtml({ https: true, webhook_url: "https://j.example/messenger/webhook", verify_token: "vt-123" });
  assert.ok(h.includes('data-copy="https://j.example/messenger/webhook"') && h.includes('data-copy="vt-123"'));
});
check("the add-channel form points a channel with a Connections card to it", () => {
  const conv = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "conversations.js"), "utf8");
  assert.ok(conv.includes("hint.hidden = !k.the_ket_noi") && conv.includes('window.t("ht.the_ket_noi"'));
  assert.ok(conv.includes("window.JavisMessenger.openForm(null)"));
});

// 0.438.3 (owner, 01/11/2026): picking such a channel shows only the way to its card, no token field, webhook or Save.
check("a channel with a Connections card hides the token part and Save", () => {
  const conv = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "conversations.js"), "utf8");
  assert.ok(conv.includes("'<div id=\"htTokenPart\">' +"));
  assert.ok(conv.includes('box.querySelector("#htTokenPart").hidden = !!k.the_ket_noi;'));
  assert.ok(conv.includes('box.querySelector(".ht-save").hidden = !!k.the_ket_noi;'));
  assert.ok(conv.includes('window.t("ht.mo_the", { kenh: k.nhan })'));
  const css = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "console.css"), "utf8");
  assert.ok(css.includes("#htTokenPart[hidden], .ht-form-acts .ht-save[hidden] { display: none; }"));
});

if (fails) { console.log("\n" + fails + " FAILED"); process.exit(1); }
console.log("\nall ok");
