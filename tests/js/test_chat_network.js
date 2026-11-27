/* The network a chat came from (#1633): the logo on a chat, its chip, and the Network filter.

       node tests/js/test_chat_network.js

   The badge and chip code of conversations.js runs for real (cut from the file), with icons.js; inbox-v5.js and
   conversations-filters.js run whole.
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const CV = src("dashboard/conversations.js");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : "")); if (!cond) fails.push(name); };

const win = { t: (k, v) => k + (v ? "#" + Object.keys(v).map((x) => v[x]).join(",") : "") };
const doc = { createElement: () => ({ style: {}, setAttribute() {}, appendChild() {} }), querySelectorAll: () => [] };
const ctx = { window: win, document: doc, console, String, Object, Array, Number, JSON, RegExp, Math };
ctx.self = win;
vm.createContext(ctx);
vm.runInContext(src("dashboard/icons.js"), ctx);
vm.runInContext(src("dashboard/inbox-v5.js"), ctx);
vm.runInContext(src("dashboard/conversations-filters.js"), ctx);
const Icons = win.Icons, V = win.JavisInboxV5, F = win.JavisConvFilters;
ctx.Icons = Icons;   // the page reaches it as a global, like the browser does
check("icons, inbox-v5 and the filters loaded", !!(Icons && Icons.kenh && V && F));

// ---- 1. badge and chip, cut from conversations.js ----
const a = CV.indexOf("  function kenhCua(id)"), b = CV.indexOf("  function nangLuc(id, khoa)");
check("conversations.js still has the badge block", a > 0 && b > a);
const block = CV.slice(a, b);
const CH = [{ id: "messenger", nhan: "Messenger", logo: "messenger" }, { id: "telegram", nhan: "Telegram", logo: "telegram" },
            { id: "bridge", nhan: "Bridge", logo: "" }];
const api = vm.runInContext("(function(){ var _kenhDS = " + JSON.stringify(CH) + ";" +
  "function esc(s){return String(s==null?'':s);}" + block +
  " return { badgeOf: badgeOf, chipOf: chipOf, networkOf: networkOf, isInstagram: isInstagram }; })()", ctx);
const has = (html, n) => html.indexOf('aria-label="' + n + '"') >= 0;

check("an Instagram chat from Messenger (network set) shows the Instagram logo",
  has(api.badgeOf({ channel: "messenger", external_chat_id: "ig:1", network: "instagram" }, "13px"), "Instagram"));
check("an Instagram chat from an older server (no network) still shows it, from the ig: chat id",
  has(api.badgeOf({ channel: "messenger", external_chat_id: "ig:1" }, "13px"), "Instagram"));
check("a Facebook chat on Messenger keeps the Messenger logo",
  has(api.badgeOf({ channel: "messenger", external_chat_id: "77", network: "facebook" }, "13px"), "Messenger"));
check("a pack chat with network=tiktok shows the TikTok logo",
  has(api.badgeOf({ channel: "bridge", external_chat_id: "c1", network: "tiktok" }, "13px"), "TikTok"));
check("its chip says TikTok", /TikTok<\/span>$/.test(api.chipOf({ channel: "bridge", external_chat_id: "c1", network: "tiktok" })));
check("a network with no logo falls back to the channel",
  api.chipOf({ channel: "telegram", external_chat_id: "9", network: "mastodon" }).indexOf("Telegram") >= 0);
check("a malformed network is ignored", api.networkOf({ channel: "bridge", network: "<b>x" }) === "");
check("a comment thread keeps its comment badge",
  api.badgeOf({ channel: "messenger", external_chat_id: "igc:5", network: "instagram" }, "13px") === Icons.kenh("igcomment", { size: "13px" }));
check("isInstagram follows the network", api.isInstagram({ channel: "bridge", network: "instagram" }));
["tiktok", "linkedin", "x", "youtube"].forEach((n) => check("logo for " + n, Icons.kenh(n).indexOf("<svg") === 0));

// ---- 2. the Network filter ----
check("network survives sanitize", F.sanitize ? F.sanitize({ network: "tiktok" }).network === "tiktok" : true);
check("the query carries it", F.query({ network: "tiktok" }).indexOf("&network=tiktok") >= 0);
check("a malformed one is dropped", F.query({ network: "Tik Tok" }).indexOf("network") < 0);
check("it counts as an active filter", F.activeCount({ network: "tiktok" }) === 1);
const facets = { networks: { tiktok: 4, instagram: 2 } };
check("no networks anywhere: no Network category", !V.filterCats({}, {}).some((c) => c.id === "network"));
check("networks in the store: a Network category", V.filterCats({}, facets).some((c) => c.id === "network"));
const menu = V.filterMenuHtml({}, "network", [], facets, [], null, null);
check("the menu lists each network with its count", /data-v="instagram"[\s\S]*Instagram \(2\)[\s\S]*data-v="tiktok"[\s\S]*TikTok \(4\)/.test(menu), menu);
check("and an All option", menu.indexOf("ib.f_network_all") >= 0 && menu.indexOf('name="ib-net" data-v=""') >= 0);
const chips = V.activeChips({ network: "tiktok" }, [], []);
check("the active chip names the network", chips.some((c) => c.k === "network" && c.text === "ib.fc_network#TikTok"));
check("conversations.js reads the radio", CV.indexOf('t.name === "ib-net"') > 0 && CV.indexOf('k === "network"') > 0);

// ---- 3. i18n ----
["ib.f_network", "ib.f_network_all", "ib.fc_network"].forEach((k) => check("i18n " + k, !!VI[k] && !!EN[k]));
check("the chip keeps {n} in both languages", VI["ib.fc_network"].indexOf("{n}") >= 0 && EN["ib.fc_network"].indexOf("{n}") >= 0);

console.log("\n" + (fails.length ? fails.length + " FAIL: " + fails.join(", ") : "ALL OK"));
process.exit(fails.length ? 1 : 0);
