// One button confirms Auto for all waiting assistants of a Store pack (owner report 2026-11-11).
//
//     python tests/run.py --js pack_confirm_ui -v
//
// The report: 17 assistants of one pack on "Auto: needs confirmation", one card at a time. The pure functions of
// resonance-agent.js run under node: grouping by pack, the line under the filter bar, the request it sends.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const RA = require(path.join(ROOT, "dashboard", "resonance-agent.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

function row(slug, status, pack, name) {
  return { slug: slug, name: slug, agent_key: "ag_" + slug, status: status, enabled: true, pack: pack || "",
           pack_name: name || "" };
}
const ECC = "javis.ecc-engineering-team";
const rows = [
  row("ecc-planner", "missing", ECC, "ECC: <b>Đội</b> lập trình"), row("ecc-architect", "missing", ECC, "ECC: <b>Đội</b> lập trình"),
  row("ecc-tdd-guide", "active", ECC, "ECC: <b>Đội</b> lập trình"),   // already fine: not counted
  row("own", "missing", ""),                                          // the user's own file: answered on its card
  row("solo", "missing", "acme.solo", "Solo"),                        // one waiting: its own card is enough
  row("gone", "retired", ECC, "ECC"),
];
const groups = RA.missingByPack(rows);
check("only packs with two or more waiting assistants get a group, with the count",
      groups.length === 1 && groups[0].pack === ECC && groups[0].n === 2, JSON.stringify(groups));
check("nothing waiting, nothing to draw", RA.missingByPack([]).length === 0 && RA.packConfirmHtml([]) === ""
      && RA.packConfirmHtml(RA.missingByPack([row("a", "active", ECC, "x"), row("b", "active", ECC, "x")])) === "");

let h = RA.packConfirmHtml(groups, {});
check("the line says how many and of which pack", h.includes(vi["resonance.pack_confirm_text"].replace("{n}", "2")
      .replace("{pack}", "ECC: &lt;b&gt;Đội&lt;/b&gt; lập trình")), h);
check("the pack name cannot inject HTML", !h.includes("<b>"));
check("one button, carrying the pack id", (h.match(/data-pack-confirm=/g) || []).length === 1
      && h.includes('data-pack-confirm="' + ECC + '"') && h.includes(">" + vi["resonance.pack_confirm_btn"] + "<"), h);
check("what confirming means is in the (i) block, not spread on the page",
      h.includes('class="info-body"') && h.includes(vi["resonance.pack_confirm_info"]));
h = RA.packConfirmHtml(groups, { [ECC]: true });
check("while saving the button is locked and says so", / disabled>/.test(h) && h.includes(vi["resonance.t0_saving"])
      && !h.includes(">" + vi["resonance.pack_confirm_btn"] + "<"), h);

const keys = ["resonance.pack_confirm_text", "resonance.pack_confirm_btn", "resonance.pack_confirm_info",
              "resonance.pack_confirm_failed"];
check("both languages carry the strings", keys.every(function (k) { return vi[k] && en[k] && vi[k] !== en[k]; }));
check("no em dash or en dash in them", keys.every(function (k) {
  return [0x2013, 0x2014].every(function (c) { return (vi[k] + en[k]).indexOf(String.fromCharCode(c)) < 0; });
}));
check("the line and the button stay short (the long text is in the (i))",
      [vi, en].every(function (d) { return d["resonance.pack_confirm_text"].length <= 100 && d["resonance.pack_confirm_btn"].length <= 40; }));

const events = [];
global.window = { dispatchEvent: function (e) { events.push(e.type); },
  JavisSessions: { brain: function () { return "brain"; } } };
global.CustomEvent = function (type) { this.type = type; };
let reply = { status: 200, body: { ok: true, confirmed: 2 } };
const sent = [];
global.fetch = function (url, init) {
  sent.push([url, JSON.parse(init.body)]);
  return Promise.resolve({ status: reply.status, json: function () { return Promise.resolve(reply.body); } });
};
(async function () {
  let r = await RA.confirmPack(ECC);
  check("200: ok, the existing confirm route, the pack id and same=true, no list of keys from the client", r.ok
        && r.confirmed === 2 && sent[0][0].indexOf("/resonance/agents/confirm?brain=brain") === 0
        && sent[0][1].pack === ECC && sent[0][1].same === true && !("agent_key" in sent[0][1]), JSON.stringify(sent));
  check("200: fires the reload event", events.indexOf("javis:resonance-agents-changed") >= 0);
  events.length = 0;
  reply = { status: 409, body: { ok: false, error: "no" } };
  r = await RA.confirmPack(ECC);
  check("an error: not ok, carries the reason, STILL reloads the real state", !r.ok && r.error === "no"
        && events.indexOf("javis:resonance-agents-changed") >= 0);
  events.length = 0;
  global.fetch = function () { return Promise.reject(new Error("net")); };
  r = await RA.confirmPack(ECC);
  check("network down: not ok, does not throw, still reloads", !r.ok && !!r.error
        && events.indexOf("javis:resonance-agents-changed") >= 0);

  const WS = fs.readFileSync(path.join(ROOT, "dashboard", "workspace.js"), "utf8");
  check("the Partners page draws the line under the filter bar and wires its button",
        WS.includes("RA.packConfirmHtml(RA.missingByPack(rows), S.packSaving)") && WS.includes('"[data-pack-confirm]"')
        && WS.includes("RA.confirmPack(packId)"));
  check("the line is redrawn when the Auto state arrives, not only the cards",
        (WS.match(/drawAutoState\(\); veAuto\(dangChon\(\)\)/g) || []).length === 2
        && /function drawAutoState\(\) \{\s*if \(S\.el\) veThanhNhom\(S\.el\);\s*veDanhSach\(\);/.test(WS));
  check("a failed confirmation says why under the bar", WS.includes('t("resonance.pack_confirm_failed"'));
  const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
  check("the button is a full-width 44px target on a phone", CSS.includes(".ws-pack-confirm-btn { min-height: 44px;"));

  if (fails) { console.log("FAIL test_pack_confirm_ui: " + fails); process.exit(1); }
  console.log("PASS test_pack_confirm_ui");
})();
